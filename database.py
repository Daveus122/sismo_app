import psycopg2
import os
from dotenv import load_dotenv
load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "127.0.0.1"),
    "database": os.getenv("DB_NAME", "desastres_db"),
    "user":     os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASS", "123"),
}


def get_conn():
    """Abre conexion y fuerza UTF-8 correctamente."""
    conn = psycopg2.connect(**DB_CONFIG)
    conn.set_client_encoding("UTF8")
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sismos (
            id         VARCHAR(50) PRIMARY KEY,
            fecha      TIMESTAMP,
            magnitud   DECIMAL(3,1),
            latitud    DECIMAL(9,6),
            longitud   DECIMAL(9,6),
            referencia TEXT
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS desastres (
            id         VARCHAR(100) PRIMARY KEY,
            tipo       VARCHAR(30) NOT NULL,
            fecha      TIMESTAMP,
            magnitud   DECIMAL(6,2),
            latitud    DECIMAL(9,6),
            longitud   DECIMAL(9,6),
            lugar      TEXT,
            detalle    TEXT,
            fuente     VARCHAR(50),
            url        TEXT
        );
    """)
    conn.commit()
    cur.close()
    conn.close()


def guardar_sismos(data):
    conn = get_conn()
    cur = conn.cursor()
    for s in data:
        fecha = s.get("utc_date") or s.get("local_date")
        mag = s.get("magnitude")
        if isinstance(mag, dict):
            mag = mag.get("value") or mag.get("Magnitude") or 0
        elif mag is None:
            mag = 0
        referencia = s.get("geo_reference") or "Sin referencia"
        try:
            cur.execute("""
                INSERT INTO sismos (id, fecha, magnitud, latitud, longitud, referencia)
                VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING
            """, (
                s.get("id", str(fecha)),
                fecha,
                float(mag),
                s.get("latitude"),
                s.get("longitude"),
                referencia
            ))
        except Exception as e:
            print(f"Error insertando sismo: {e}")
    conn.commit()
    cur.close()
    conn.close()


def obtener_sismos_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sismos ORDER BY fecha DESC LIMIT 15")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def guardar_desastres(eventos):
    conn = get_conn()
    cur = conn.cursor()
    for e in eventos:
        try:
            cur.execute("""
                INSERT INTO desastres
                    (id, tipo, fecha, magnitud, latitud, longitud, lugar, detalle, fuente, url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, (
                e.get("id"),
                e.get("tipo"),
                e.get("fecha"),
                e.get("magnitud"),
                e.get("lat"),
                e.get("lon"),
                e.get("lugar"),
                e.get("detalle"),
                e.get("fuente"),
                e.get("url")
            ))
        except Exception as ex:
            print(f"Error insertando desastre: {ex}")
    conn.commit()
    cur.close()
    conn.close()


def obtener_desastres_db(tipo=None, limit=100):
    conn = get_conn()
    cur = conn.cursor()
    if tipo:
        cur.execute(
            "SELECT * FROM desastres WHERE tipo = %s ORDER BY fecha DESC NULLS LAST LIMIT %s",
            (tipo, limit)
        )
    else:
        cur.execute(
            "SELECT * FROM desastres ORDER BY fecha DESC NULLS LAST LIMIT %s",
            (limit,)
        )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def desastre_row_to_dict(r):
    return {
        "id":       r[0],
        "tipo":     r[1],
        "fecha":    str(r[2]) if r[2] else None,
        "magnitud": float(r[3]) if r[3] else None,
        "lat":      float(r[4]) if r[4] else None,
        "lon":      float(r[5]) if r[5] else None,
        "lugar":    r[6] or "Sin referencia",
        "detalle":  r[7],
        "fuente":   r[8],
        "url":      r[9]
    }