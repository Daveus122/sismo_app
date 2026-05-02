"""
api.py  — Backend API de Desastres Globales  (FastAPI)
Puerto: 8000
Docs:   http://localhost:8000/docs   ← Swagger UI automático
"""

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
import requests as req, os, psycopg2
from database import (init_db, guardar_sismos, obtener_sismos_db, DB_CONFIG,
                      guardar_desastres, obtener_desastres_db, desastre_row_to_dict,
                      get_conn)
from dotenv import load_dotenv
from datetime import datetime, timezone
from typing import Optional
import xml.etree.ElementTree as ET

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULER — actualización automática cada 10 minutos
# ─────────────────────────────────────────────────────────────────────────────

def _actualizar_todas():
    """Descarga y guarda datos de todas las fuentes. Se llama automáticamente."""
    print(f"[scheduler] Actualizando fuentes — {datetime.now().strftime('%H:%M:%S')}")
    for nombre, fn in FETCHERS.items():
        try:
            eventos = fn()
            guardar_desastres(eventos)
            print(f"[scheduler]   {nombre}: {len(eventos)} eventos")
        except Exception as e:
            print(f"[scheduler]   {nombre} ERROR: {e}")
    # tabla legacy sismos Chile
    try:
        data = req.get("https://api.xor.cl/sismo/recent", timeout=10).json()
        guardar_sismos(data.get("events", []))
    except Exception as e:
        print(f"[scheduler]   sismos_legacy ERROR: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Arranca la BD y el scheduler al iniciar; los detiene al cerrar."""
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(_actualizar_todas, "interval", minutes=10, id="auto_update")
    scheduler.start()
    print("[scheduler] Actualización automática cada 10 min activada.")
    _actualizar_todas()   # primera carga inmediata al arrancar
    yield
    scheduler.shutdown()


app = FastAPI(
    title="API Desastres Globales",
    description="Sismos · Volcanes · Incendios · Ciclones · Tsunamis · Inundaciones",
    version="2.0.0",
    lifespan=lifespan,
)

# ─────────────────────────────────────────────────────────────────────────────
# FETCHERS
# ─────────────────────────────────────────────────────────────────────────────

def fetch_sismos_chile():
    eventos = []
    try:
        data = req.get("https://api.xor.cl/sismo/recent", timeout=10).json()
        for s in data.get("events", []):
            mag = s.get("magnitude")
            if isinstance(mag, dict):
                mag = mag.get("value") or 0
            eventos.append({
                "id":       f"chile-{s.get('id', '')}",
                "tipo":     "sismo",
                "fecha":    s.get("utc_date") or s.get("local_date"),
                "magnitud": float(mag or 0),
                "lat":      s.get("latitude"),
                "lon":      s.get("longitude"),
                "lugar":    s.get("geo_reference", "Chile"),
                "detalle":  f"Profundidad: {s.get('depth', '?')} km",
                "fuente":   "xor.cl",
                "url":      "https://api.xor.cl/sismo/recent"
            })
    except Exception as e:
        print(f"[sismos-chile] {e}")
    return eventos


def fetch_sismos_usgs():
    eventos = []
    try:
        url  = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_week.geojson"
        data = req.get(url, timeout=15).json()
        for f in data.get("features", []):
            p   = f["properties"]
            geo = f["geometry"]["coordinates"]
            ts  = p.get("time")
            fecha = (datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                     .strftime("%Y-%m-%d %H:%M:%S") if ts else None)
            eventos.append({
                "id":       f"usgs-{f['id']}",
                "tipo":     "sismo",
                "fecha":    fecha,
                "magnitud": float(p.get("mag") or 0),
                "lat":      float(geo[1]),
                "lon":      float(geo[0]),
                "lugar":    p.get("place", "Desconocido"),
                "detalle":  f"Profundidad: {geo[2]} km | Tipo: {p.get('type','')}",
                "fuente":   "USGS",
                "url":      p.get("url", "")
            })
    except Exception as e:
        print(f"[usgs] {e}")
    return eventos


def fetch_volcanes_usgs():
    eventos = []
    try:
        url  = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.geojson"
        data = req.get(url, timeout=15).json()
        for f in data.get("features", []):
            p = f["properties"]
            if p.get("type", "").lower() in ("volcanic eruption", "quarry blast"):
                geo   = f["geometry"]["coordinates"]
                ts    = p.get("time")
                fecha = (datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                         .strftime("%Y-%m-%d %H:%M:%S") if ts else None)
                eventos.append({
                    "id":       f"volc-{f['id']}",
                    "tipo":     "volcan",
                    "fecha":    fecha,
                    "magnitud": float(p.get("mag") or 0),
                    "lat":      float(geo[1]),
                    "lon":      float(geo[0]),
                    "lugar":    p.get("place", "Desconocido"),
                    "detalle":  p.get("title", ""),
                    "fuente":   "USGS",
                    "url":      p.get("url", "")
                })
    except Exception as e:
        print(f"[volcanes] {e}")
    return eventos


def fetch_incendios_nasa():
    eventos = []
    try:
        MAP_KEY = os.getenv("NASA_FIRMS_KEY", "DEMO_KEY")
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/world/1"
        r = req.get(url, timeout=20)
        lines = r.text.strip().split("\n")
        if len(lines) < 2:
            raise ValueError("Sin datos FIRMS")
        headers = [h.strip() for h in lines[0].split(",")]
        for i, line in enumerate(lines[1:], 1):
            row = dict(zip(headers, line.split(",")))
            eventos.append({
                "id":       f"firms-{i}-{row.get('acq_date','')}-{row.get('latitude','')}-{row.get('longitude','')}",
                "tipo":     "incendio",
                "fecha":    f"{row.get('acq_date','')} {row.get('acq_time','')}",
                "magnitud": float(row.get("frp", 0) or 0),
                "lat":      float(row.get("latitude", 0)),
                "lon":      float(row.get("longitude", 0)),
                "lugar":    f"Lat {row.get('latitude')}, Lon {row.get('longitude')}",
                "detalle":  f"Brillo: {row.get('bright_ti4','?')} K | FRP: {row.get('frp','?')} MW | Confianza: {row.get('confidence','?')}",
                "fuente":   "NASA FIRMS",
                "url":      "https://firms.modaps.eosdis.nasa.gov/"
            })
            if i > 500:
                break
    except Exception as e:
        print(f"[nasa-firms] {e}")
    return eventos


def fetch_ciclones_noaa():
    eventos = []
    feeds = [
        "https://www.nhc.noaa.gov/index-at.xml",
        "https://www.nhc.noaa.gov/index-ep.xml",
        "https://www.nhc.noaa.gov/index-cp.xml",
    ]
    for feed_url in feeds:
        try:
            r    = req.get(feed_url, timeout=10)
            root = ET.fromstring(r.text)
            ns   = {"geo": "http://www.w3.org/2003/01/geo/wgs84_pos#"}
            for item in root.iter("item"):
                title  = (item.findtext("title") or "").strip()
                desc   = (item.findtext("description") or "").strip()
                lat_el = item.find("geo:lat", ns)
                lon_el = item.find("geo:long", ns)
                if lat_el is None or lon_el is None:
                    continue
                eventos.append({
                    "id":       f"nhc-{feed_url[-6:-4]}-{title[:30].replace(' ','')}",
                    "tipo":     "ciclon",
                    "fecha":    item.findtext("pubDate") or "",
                    "magnitud": None,
                    "lat":      float(lat_el.text),
                    "lon":      float(lon_el.text),
                    "lugar":    title,
                    "detalle":  desc[:300],
                    "fuente":   "NOAA NHC",
                    "url":      item.findtext("link") or ""
                })
        except Exception as ex:
            print(f"[nhc-feed] {ex}")
    return eventos


def fetch_gdacs():
    eventos = []
    try:
        root = ET.fromstring(req.get("https://www.gdacs.org/xml/rss.xml", timeout=15).text)
        ns   = {"geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
                "gdacs": "http://www.gdacs.org"}
        tipo_map = {"EQ":"sismo","TC":"ciclon","FL":"inundacion",
                    "VO":"volcan","DR":"sequia","WF":"incendio","TS":"tsunami"}
        for item in root.iter("item"):
            lat_el = item.find("geo:lat", ns)
            lon_el = item.find("geo:long", ns)
            if lat_el is None or lon_el is None:
                continue
            etype  = (item.findtext("gdacs:eventtype", namespaces=ns) or "")
            mag_el = item.findtext("gdacs:severity", namespaces=ns) or ""
            try:
                mag = float(mag_el.split()[0]) if mag_el else None
            except Exception:
                mag = None
            title = (item.findtext("title") or "").strip()
            eid   = (item.findtext("gdacs:eventid", namespaces=ns) or title[:20].replace(" ",""))
            eventos.append({
                "id":       f"gdacs-{etype}-{eid}",
                "tipo":     tipo_map.get(etype.upper(), "otro"),
                "fecha":    item.findtext("pubDate") or "",
                "magnitud": mag,
                "lat":      float(lat_el.text),
                "lon":      float(lon_el.text),
                "lugar":    title,
                "detalle":  (item.findtext("description") or "")[:300],
                "fuente":   "GDACS",
                "url":      item.findtext("link") or ""
            })
    except Exception as e:
        print(f"[gdacs] {e}")
    return eventos


def fetch_tsunamis_noaa():
    eventos = []
    try:
        root = ET.fromstring(req.get("https://ptwc.weather.gov/feeds/ptwc_rss_pacific.xml", timeout=10).text)
        for i, item in enumerate(root.iter("item")):
            pub = item.findtext("pubDate") or ""
            eventos.append({
                "id":       f"ptwc-{i}-{pub[:10].replace(' ','')}",
                "tipo":     "tsunami",
                "fecha":    pub,
                "magnitud": None,
                "lat":      None,
                "lon":      None,
                "lugar":    (item.findtext("title") or "").strip(),
                "detalle":  (item.findtext("description") or "")[:300],
                "fuente":   "NOAA PTWC",
                "url":      item.findtext("link") or ""
            })
    except Exception as e:
        print(f"[tsunami] {e}")
    return eventos


FETCHERS = {
    "sismos":     fetch_sismos_usgs,
    "sismos_cl":  fetch_sismos_chile,
    "volcanes":   fetch_volcanes_usgs,
    "incendios":  fetch_incendios_nasa,
    "ciclones":   fetch_ciclones_noaa,
    "gdacs":      fetch_gdacs,
    "tsunamis":   fetch_tsunamis_noaa,
}

# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS — Desastres globales
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/v1/desastres", summary="Listar desastres", tags=["Desastres"])
def listar_desastres(
    tipo:  Optional[str] = Query(None, description="sismo|volcan|incendio|ciclon|tsunami|inundacion|otro"),
    limit: int           = Query(100,  ge=1, le=2000, description="Máximo de resultados"),
):
    rows = obtener_desastres_db(tipo=tipo, limit=limit)
    return [desastre_row_to_dict(r) for r in rows]


@app.get("/api/v1/desastres/{did}", summary="Desastre por ID", tags=["Desastres"])
def obtener_desastre(did: str):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM desastres WHERE id = %s", (did,))
    r = cur.fetchone(); cur.close(); conn.close()
    if not r:
        raise HTTPException(status_code=404, detail="No encontrado")
    return desastre_row_to_dict(r)


@app.post("/api/v1/desastres", status_code=201, summary="Insertar desastre manual", tags=["Desastres"])
def insertar_desastre(datos: dict):
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("""
            INSERT INTO desastres (id,tipo,fecha,magnitud,latitud,longitud,lugar,detalle,fuente,url)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (datos["id"], datos["tipo"], datos.get("fecha"), datos.get("magnitud"),
              datos.get("lat"), datos.get("lon"), datos.get("lugar"),
              datos.get("detalle"), datos.get("fuente"), datos.get("url")))
        conn.commit(); cur.close(); conn.close()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/actualizar", summary="Actualizar fuentes ahora", tags=["Admin"])
def actualizar_todo(fuente: Optional[str] = Query(None, description="Nombre de fuente específica")):
    """Dispara la descarga de datos manualmente. Con ?fuente=sismos actualiza solo una."""
    fuentes    = [fuente] if fuente and fuente in FETCHERS else list(FETCHERS.keys())
    resultados = {}
    errores    = {}
    for nombre in fuentes:
        try:
            eventos = FETCHERS[nombre]()
            guardar_desastres(eventos)
            resultados[nombre] = len(eventos)
        except Exception as e:
            errores[nombre] = str(e)
    if "sismos_cl" in fuentes or fuente is None:
        try:
            data = req.get("https://api.xor.cl/sismo/recent", timeout=10).json()
            guardar_sismos(data.get("events", []))
        except Exception as e:
            errores["sismos_legacy"] = str(e)
    return {"fuentes": fuentes, "insertados": resultados, "errores": errores}


@app.get("/api/v1/estadisticas", summary="Estadísticas globales", tags=["Desastres"])
def estadisticas_globales():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*), MAX(magnitud), AVG(magnitud) FROM desastres")
    total, mag_max, mag_avg = cur.fetchone()
    cur.execute("SELECT tipo, COUNT(*) FROM desastres GROUP BY tipo ORDER BY COUNT(*) DESC")
    por_tipo = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute("SELECT * FROM desastres ORDER BY magnitud DESC NULLS LAST LIMIT 1")
    fuerte = cur.fetchone(); cur.close(); conn.close()
    return {
        "total":          total or 0,
        "por_tipo":       por_tipo,
        "mag_maxima":     float(mag_max) if mag_max else None,
        "mag_promedio":   round(float(mag_avg), 2) if mag_avg else None,
        "el_mas_intenso": desastre_row_to_dict(fuerte) if fuerte else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS LEGACY — Sismos Chile
# ─────────────────────────────────────────────────────────────────────────────

def _row_sismo(s):
    return {
        "id": s[0], "fecha": str(s[1]),
        "mag": float(s[2]), "lat": float(s[3]), "lon": float(s[4]),
        "lugar": s[5] or "Sin referencia",
        "hora": s[1].strftime("%H:%M") if s[1] else "--:--"
    }

@app.get("/api/v1/sismos",        summary="Últimos 15 sismos Chile",  tags=["Sismos Chile"])
def listar_sismos():
    return [_row_sismo(s) for s in obtener_sismos_db()]

@app.get("/api/v1/sismos/todos",  summary="Todos los sismos Chile",   tags=["Sismos Chile"])
def todos_los_sismos():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM sismos ORDER BY fecha DESC")
    rows = cur.fetchall(); cur.close(); conn.close()
    return [_row_sismo(s) for s in rows]

@app.get("/api/v1/sismos/fuertes",summary="Sismos Chile M≥4.0",       tags=["Sismos Chile"])
def sismos_fuertes():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM sismos WHERE magnitud >= 4.0 ORDER BY fecha DESC")
    rows = cur.fetchall(); cur.close(); conn.close()
    return [_row_sismo(s) for s in rows]

@app.get("/api/v1/sismos/{sid}", summary="Sismo Chile por ID",        tags=["Sismos Chile"])
def obtener_por_id(sid: str):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT * FROM sismos WHERE id = %s", (sid,))
    s = cur.fetchone(); cur.close(); conn.close()
    if not s:
        raise HTTPException(status_code=404, detail="Sismo no encontrado")
    return _row_sismo(s)

@app.post("/api/v1/sismos", status_code=201, summary="Insertar sismo manual", tags=["Sismos Chile"])
def insertar_sismo(datos: dict):
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("""
            INSERT INTO sismos (id, fecha, magnitud, latitud, longitud, referencia)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (datos["id"], datos["fecha"], datos["mag"],
              datos["lat"], datos["lon"], datos["lugar"]))
        conn.commit(); cur.close(); conn.close()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# ARRANQUE LOCAL
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)