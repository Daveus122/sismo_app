# -*- coding: utf-8 -*-
"""
app.py  — Frontend Flask: Monitor Global de Desastres
Puerto: 5000
"""

import sys
import os

# ── Forzar UTF-8 en Windows ────────────────────────────────────────────────
if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from flask import Flask, render_template_string, jsonify, request
import requests
import json
import folium
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

API_BASE = os.getenv("API_BASE", "http://localhost:8000")

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN VISUAL POR TIPO
# ─────────────────────────────────────────────────────────────────────────────

TIPO_CONFIG = {
    "sismo":      {"color": "#e74c3c", "glow": "#ff6b6b", "icon": "🌋", "label": "Sismo"},
    "volcan":     {"color": "#e67e22", "glow": "#ffaa55", "icon": "🌋", "label": "Volcán"},
    "incendio":   {"color": "#f39c12", "glow": "#ffd166", "icon": "🔥", "label": "Incendio"},
    "ciclon":     {"color": "#9b59b6", "glow": "#c77dff", "icon": "🌀", "label": "Ciclón"},
    "tsunami":    {"color": "#1abc9c", "glow": "#48e5c2", "icon": "🌊", "label": "Tsunami"},
    "inundacion": {"color": "#3498db", "glow": "#74b9ff", "icon": "💧", "label": "Inundación"},
    "sequia":     {"color": "#795548", "glow": "#a1887f", "icon": "🏜️", "label": "Sequía"},
    "otro":       {"color": "#95a5a6", "glow": "#b2bec3", "icon": "⚠️",  "label": "Otro"},
}

# ─────────────────────────────────────────────────────────────────────────────
# MAPA
# ─────────────────────────────────────────────────────────────────────────────

def _pulse_css():
    colores = " ".join(
        f".pulse-{tipo} {{ background:{cfg['color']}; box-shadow: 0 0 0 0 {cfg['glow']}88; }}"
        for tipo, cfg in TIPO_CONFIG.items()
    )
    return f"""
    <style>
    @keyframes ripple {{
        0%   {{ box-shadow: 0 0 0 0 var(--glow); opacity: 1; }}
        70%  {{ box-shadow: 0 0 0 12px transparent; opacity: 0.6; }}
        100% {{ box-shadow: 0 0 0 0 transparent; opacity: 0; }}
    }}
    .pulse-marker {{
        border-radius: 50%;
        animation: ripple 2s ease-out infinite;
    }}
    {colores}
    .popup-dark .leaflet-popup-content-wrapper {{
        background: #0f0f0f !important;
        border: 1px solid #2a2a2a !important;
        border-radius: 12px !important;
        box-shadow: 0 8px 32px rgba(0,0,0,.7) !important;
        padding: 0 !important;
        overflow: hidden;
    }}
    .popup-dark .leaflet-popup-tip {{ background: #1a1a1a !important; }}
    .popup-dark .leaflet-popup-content {{ margin: 0 !important; min-width: 220px; }}
    .popup-dark .leaflet-popup-close-button {{ color: #666 !important; top: 8px !important; right: 8px !important; }}
    </style>
    """


def _popup_html(d, cfg):
    mag      = d.get("magnitud")
    mag_str  = f"{mag:.1f}" if mag is not None else "—"
    tipo     = d.get("tipo", "otro")
    lugar    = d.get("lugar", "")
    fecha    = (d.get("fecha") or "")[:16]
    detalle  = (d.get("detalle") or "")[:100]
    url      = d.get("url", "")
    fuente   = d.get("fuente", "")
    unidad   = "Mw" if tipo == "sismo" else ("MW" if tipo == "incendio" else "")
    link_html = (
        f'<a href="{url}" target="_blank" '
        f'style="display:inline-block;margin-top:10px;padding:4px 10px;'
        f'background:{cfg["color"]}22;color:{cfg["color"]};border:1px solid {cfg["color"]}44;'
        f'border-radius:6px;font-size:11px;text-decoration:none;font-weight:600">Ver más →</a>'
    ) if url else ""
    emoji = cfg.get("icon", "⚠️")
    return f"""
    <div style="font-family:'Segoe UI',sans-serif;background:#0f0f0f;border-radius:12px;overflow:hidden">
      <div style="background:{cfg['color']}18;border-bottom:1px solid {cfg['color']}33;padding:12px 14px 10px">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span style="font-size:11px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:{cfg['color']}">{emoji} {cfg['label']}</span>
          <span style="font-size:10px;color:#555">{fuente}</span>
        </div>
        <div style="margin-top:4px;font-size:22px;font-weight:800;color:#fff;line-height:1">
          {mag_str}<span style="font-size:11px;font-weight:400;color:#888">{unidad}</span>
        </div>
      </div>
      <div style="padding:10px 14px 12px">
        <div style="font-size:12px;color:#ccc;line-height:1.4">{lugar}</div>
        <div style="font-size:10px;color:#555;margin-top:4px">{fecha}</div>
        {'<div style="font-size:11px;color:#888;margin-top:8px;line-height:1.5;border-top:1px solid #1e1e1e;padding-top:8px">' + detalle + '...</div>' if detalle else ''}
        {link_html}
      </div>
    </div>
    """


def construir_mapa(desastres):
    mapa = folium.Map(
        location=[20, 0],
        zoom_start=2,
        tiles=None,
        prefer_canvas=True,
    )
    # Oscuro primero (no activo por defecto)
    folium.TileLayer(
        tiles="CartoDB dark_matter",
        name="Oscuro",
        overlay=False,
        control=True,
    ).add_to(mapa)
    # Satelital al final = activo por defecto en Leaflet
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Satelite",
        overlay=False,
        control=True,
    ).add_to(mapa)

    mapa.get_root().html.add_child(folium.Element(_pulse_css()))

    grupos = {}
    for tipo, cfg in TIPO_CONFIG.items():
        emoji = cfg.get("icon", "")
        fg = folium.FeatureGroup(name=f"{emoji} {cfg['label']}", show=True)
        grupos[tipo] = fg

    for d in desastres:
        lat = d.get("lat")
        lon = d.get("lon")
        if lat is None or lon is None:
            continue
        tipo = d.get("tipo", "otro")
        cfg  = TIPO_CONFIG.get(tipo, TIPO_CONFIG["otro"])
        mag  = d.get("magnitud")
        radius = min(max(5, float(mag) * 2.5), 30) if mag else 6
        icon_html = f"""
        <div class="pulse-marker pulse-{tipo}"
             style="width:{int(radius*2)}px;height:{int(radius*2)}px;
                    --glow:{cfg['glow']}88;
                    border:2px solid {cfg['color']};
                    animation-delay:{hash(str(lat)) % 20 * 0.1}s">
        </div>"""
        marker = folium.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(
                html=icon_html,
                icon_size=(int(radius*2), int(radius*2)),
                icon_anchor=(int(radius), int(radius)),
                class_name="",
            ),
            popup=folium.Popup(
                folium.IFrame(
                    html=_popup_html(d, cfg),
                    width=250,
                    height=220 if d.get("detalle") else 160,
                ),
                max_width=260,
                class_name="popup-dark",
            ),
            tooltip=folium.Tooltip(
                f"{cfg['icon']} {(d.get('lugar') or '')[:40]}",
                style="background:#111;color:#eee;border:1px solid #333;font-size:12px;border-radius:6px"
            ),
        )
        marker.add_to(grupos.get(tipo, grupos["otro"]))

    for fg in grupos.values():
        fg.add_to(mapa)

    folium.LayerControl(collapsed=False, position="topright").add_to(mapa)
    return mapa._repr_html_()


# ─────────────────────────────────────────────────────────────────────────────
# TEMPLATE HTML
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>Monitor Global de Desastres</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background:#0f0f0f; color:#e0e0e0; font-family:'Segoe UI',sans-serif; }
        .navbar-brand { letter-spacing:.5px; font-size:1.1rem; }
        .map-container { height:520px; border-radius:12px; overflow:hidden; }
        .stat-card { background:#1a1a1a; border:1px solid #2a2a2a; border-radius:10px; padding:12px 16px; text-align:center; }
        .stat-card .num { font-size:1.6rem; font-weight:700; }
        .stat-card .lbl { font-size:.72rem; color:#888; text-transform:uppercase; letter-spacing:.5px; }
        .tipo-badge { display:inline-flex; align-items:center; gap:5px; padding:3px 9px; border-radius:20px; font-size:.75rem; font-weight:600; cursor:pointer; border:none; color:#fff; }
        .tipo-badge.active { outline:2px solid #fff; }
        .evento-item { background:#1a1a1a; border:1px solid #2a2a2a; border-radius:8px; padding:10px 12px; margin-bottom:8px; transition:border-color .2s; }
        .evento-item:hover { border-color:#444; }
        .evento-item .mag { font-size:1.1rem; font-weight:700; }
        .evento-item .hora { font-size:.72rem; color:#888; }
        .evento-item .lugar { font-size:.8rem; color:#aaa; margin-top:2px; }
        #alerta-sismo { border-radius:10px; overflow:hidden; }
        ::-webkit-scrollbar { width:5px; }
        ::-webkit-scrollbar-track { background:#111; }
        ::-webkit-scrollbar-thumb { background:#333; border-radius:3px; }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
    </style>
</head>
<body>

<nav class="navbar navbar-dark mb-4 shadow" style="background:#111;border-bottom:1px solid #222">
    <div class="container-fluid px-4">
        <span class="navbar-brand mb-0 h1">🌍 Monitor Global de Desastres</span>
        <span class="text-muted" style="font-size:.8rem">USGS · NASA FIRMS · NOAA · GDACS</span>
    </div>
</nav>

<div class="container-fluid px-4">

    <div id="alerta-sismo" style="display:none" class="mb-3">
        <div id="alerta-box" class="p-3" style="border-radius:10px;border:1px solid #333">
            <div class="d-flex align-items-center gap-2 mb-2">
                <span id="alerta-dot" style="width:10px;height:10px;border-radius:50%;display:inline-block"></span>
                <strong id="alerta-titulo" style="font-size:.9rem"></strong>
            </div>
            <div id="alerta-texto" style="font-size:.8rem"></div>
            <div id="alerta-detalle" style="display:none;margin-top:10px;font-size:.8rem;background:#111;border-radius:6px;padding:10px">
                <div class="row g-2">
                    <div class="col-4"><small class="text-muted d-block">Tipo</small><strong id="d-tipo"></strong></div>
                    <div class="col-4"><small class="text-muted d-block">Magnitud</small><strong id="d-mag"></strong></div>
                    <div class="col-4"><small class="text-muted d-block">Distancia</small><strong id="d-dist"></strong></div>
                    <div class="col-12"><small class="text-muted d-block">Lugar</small><span id="d-lugar"></span></div>
                </div>
            </div>
        </div>
    </div>

    <div class="row g-2 mb-3">
        <div class="col-6 col-md-2">
            <div class="stat-card">
                <div class="num text-warning">{{ estadisticas.get('total', 0) }}</div>
                <div class="lbl">Total eventos</div>
            </div>
        </div>
        {% for tipo, cnt in por_tipo.items() %}
        {% set cfg = tipo_config.get(tipo, tipo_config['otro']) %}
        <div class="col-6 col-md-2">
            <div class="stat-card">
                <div class="num" style="color:{{ cfg['color'] }}">{{ cnt }}</div>
                <div class="lbl">{{ cfg['icon'] }} {{ cfg['label'] }}</div>
            </div>
        </div>
        {% endfor %}
    </div>

    <div class="d-flex flex-wrap gap-2 mb-3" id="filtros">
        <button class="tipo-badge active" data-tipo="todos" style="background:#444">🌐 Todos</button>
        {% for tipo, cfg in tipo_config.items() %}
        <button class="tipo-badge" data-tipo="{{ tipo }}"
            style="background:{{ cfg['color'] }}88;border:1px solid {{ cfg['color'] }}">
            {{ cfg['icon'] }} {{ cfg['label'] }}
        </button>
        {% endfor %}
    </div>

    <div class="row g-3">
        <div class="col-lg-8">
            <div class="card p-2 shadow-sm" style="background:#1a1a1a;border:1px solid #2a2a2a;border-radius:12px">
                <div class="map-container">{{ mapa|safe }}</div>
            </div>
        </div>
        <div class="col-lg-4">
            <h6 class="text-muted mb-2" style="font-size:.8rem;text-transform:uppercase;letter-spacing:.5px">Últimos eventos</h6>
            <div id="lista-eventos" style="max-height:520px;overflow-y:auto">
                {% for d in desastres %}
                {% set cfg = tipo_config.get(d['tipo'], tipo_config['otro']) %}
                <div class="evento-item" data-tipo="{{ d['tipo'] }}"
                     data-lat="{{ d['lat'] }}" data-lon="{{ d['lon'] }}"
                     style="cursor:{% if d['lat'] %}pointer{% else %}default{% endif %}">
                    <div class="d-flex justify-content-between align-items-start">
                        <span class="mag" style="color:{{ cfg['color'] }}">
                            {{ cfg['icon'] }}
                            {% if d['magnitud'] %}{{ "%.1f"|format(d['magnitud']) }}{% endif %}
                        </span>
                        <span class="hora">{{ (d['fecha'] or '')[:16] }}</span>
                    </div>
                    <div class="lugar">{{ d['lugar'] }}</div>
                    <div class="mt-1">
                        <span class="badge" style="background:{{ cfg['color'] }}22;color:{{ cfg['color'] }};font-size:.68rem">{{ cfg['label'] }}</span>
                        <span class="text-muted" style="font-size:.7rem"> · {{ d['fuente'] }}</span>
                        {% if d['lat'] %}<span style="font-size:.65rem;color:#555;margin-left:4px">📍 ver en mapa</span>{% endif %}
                    </div>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>

</div>

<script id="desastres-data" type="application/json">{{ desastres_json|safe }}</script>
<script>
    const RADIO_KM = 150;
    const desastres = JSON.parse(document.getElementById('desastres-data').textContent);

    // ── Filtros ───────────────────────────────────────────────────────────────
    document.querySelectorAll('.tipo-badge').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tipo-badge').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const tipo = btn.dataset.tipo;
            document.querySelectorAll('#lista-eventos .evento-item').forEach(item => {
                item.style.display = (tipo === 'todos' || item.dataset.tipo === tipo) ? '' : 'none';
            });
        });
    });

    // ── Click en evento → volar al marcador en el mapa ───────────────────────
    // El mapa Folium vive dentro de un <iframe> generado automáticamente.
    // Esperamos a que cargue y luego controlamos su leaflet map object.
    function getLeafletMap() {
        // Folium inserta un <div id="map_XXXX"> con el objeto window.map_XXXX
        // Buscamos en el iframe del mapa
        try {
            const iframe = document.querySelector('.map-container iframe');
            if (!iframe) return null;
            const iwin = iframe.contentWindow;
            // Leaflet guarda los mapas en L.Map._instances o en variables globales
            // Folium los expone como variables globales tipo map_XXXXXXXX
            const keys = Object.keys(iwin).filter(k => k.startsWith('map_'));
            return keys.length ? iwin[keys[0]] : null;
        } catch(e) { return null; }
    }

    document.querySelectorAll('#lista-eventos .evento-item').forEach(item => {
        item.addEventListener('click', () => {
            const lat = parseFloat(item.dataset.lat);
            const lon = parseFloat(item.dataset.lon);
            if (isNaN(lat) || isNaN(lon)) return;

            // Highlight del item clickeado
            document.querySelectorAll('.evento-item').forEach(i => i.style.outline = 'none');
            item.style.outline = '1px solid #e74c3c';
            item.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

            // Volar al marcador en el mapa
            const lmap = getLeafletMap();
            if (lmap) {
                lmap.flyTo([lat, lon], 6, { animate: true, duration: 1.2 });
                // Buscar el marcador más cercano a esas coords y abrir su popup
                setTimeout(() => {
                    let closest = null, minD = Infinity;
                    lmap.eachLayer(layer => {
                        if (layer.getLatLng) {
                            const ll = layer.getLatLng();
                            const d = Math.abs(ll.lat - lat) + Math.abs(ll.lng - lon);
                            if (d < minD) { minD = d; closest = layer; }
                        }
                    });
                    if (closest && minD < 0.01) closest.openPopup();
                }, 1400);
            } else {
                // Fallback: scroll al mapa si el iframe aún no está listo
                document.querySelector('.map-container').scrollIntoView({ behavior: 'smooth' });
            }
        });
    });

    function dist(lat1, lon1, lat2, lon2) {
        const R = 6371, dLat = (lat2-lat1)*Math.PI/180, dLon = (lon2-lon1)*Math.PI/180;
        const a = Math.sin(dLat/2)**2 + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)**2;
        return R*2*Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    }

    function verificarCercania(userLat, userLon) {
        const caja = document.getElementById('alerta-sismo');
        const box = document.getElementById('alerta-box');
        const dot = document.getElementById('alerta-dot');
        const titulo = document.getElementById('alerta-titulo');
        const texto = document.getElementById('alerta-texto');
        const detalle = document.getElementById('alerta-detalle');
        let cercano = null, minDist = Infinity;
        for (const d of desastres) {
            if (d.lat == null || d.lon == null) continue;
            const km = dist(userLat, userLon, d.lat, d.lon);
            if (km < minDist) { minDist = km; cercano = {...d, distancia: Math.round(km)}; }
        }
        caja.style.display = 'block';
        if (cercano && minDist <= RADIO_KM) {
            box.style.background = '#2a0a0a'; box.style.borderColor = '#e74c3c';
            dot.style.background = '#e74c3c'; dot.style.animation = 'pulse 1.4s ease-in-out infinite';
            titulo.textContent = `⚠️ Evento cercano: ${cercano.tipo}`; titulo.style.color = '#e74c3c';
            texto.textContent = `Hay un ${cercano.tipo} a ${cercano.distancia} km de tu ubicación.`;
            detalle.style.display = 'block';
            document.getElementById('d-tipo').textContent = cercano.tipo;
            document.getElementById('d-mag').textContent = cercano.magnitud ? cercano.magnitud.toFixed(1) : '—';
            document.getElementById('d-dist').textContent = cercano.distancia + ' km';
            document.getElementById('d-lugar').textContent = cercano.lugar;
        } else {
            box.style.background = '#0a1a0a'; box.style.borderColor = '#27ae60';
            dot.style.background = '#27ae60'; dot.style.animation = 'none';
            titulo.textContent = '✅ Sin eventos cercanos'; titulo.style.color = '#27ae60';
            texto.textContent = `Radio de ${RADIO_KM} km despejado.`;
            detalle.style.display = 'none';
        }
    }

    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            pos => verificarCercania(pos.coords.latitude, pos.coords.longitude),
            () => {
                document.getElementById('alerta-sismo').style.display = 'block';
                document.getElementById('alerta-box').innerHTML =
                    '<p style="font-size:.8rem;color:#666;margin:0">📍 No se pudo obtener tu ubicación.</p>';
            }
        );
    }
</script>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# RUTAS
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    # Obtener desastres desde la API — si falla, usa lista vacía (no crashea)
    desastres = []
    try:
        resp = requests.get(f"{API_BASE}/api/v1/desastres?limit=500", timeout=10)
        resp.raise_for_status()
        desastres = resp.json()
    except Exception as e:
        print(f"[app] No se pudo conectar a la API: {e}")
        print(f"[app] Asegurate de que api.py está corriendo en {API_BASE}")

    # Estadísticas
    estadisticas = {"total": len(desastres)}
    por_tipo = {}
    try:
        resp2 = requests.get(f"{API_BASE}/api/v1/estadisticas", timeout=5)
        if resp2.ok:
            stats = resp2.json()
            estadisticas = stats
            por_tipo = stats.get("por_tipo", {})
    except Exception:
        # Calcular localmente si la API falla
        for d in desastres:
            t = d.get("tipo", "otro")
            por_tipo[t] = por_tipo.get(t, 0) + 1

    # Construir mapa
    try:
        mapa_html = construir_mapa(desastres)
    except Exception as e:
        print(f"[app] Error construyendo mapa: {e}")
        mapa_html = "<div style='color:#e74c3c;padding:20px'>Error cargando mapa</div>"

    return render_template_string(
        TEMPLATE,
        mapa=mapa_html,
        desastres=desastres,
        desastres_json=json.dumps(desastres, ensure_ascii=False),
        estadisticas=estadisticas,
        por_tipo=por_tipo,
        tipo_config=TIPO_CONFIG,
    )


@app.route("/api/mapa")
def api_mapa():
    """Endpoint para refrescar solo el mapa vía AJAX."""
    tipo = request.args.get("tipo")
    try:
        url = f"{API_BASE}/api/v1/desastres?limit=500"
        if tipo:
            url += f"&tipo={tipo}"
        desastres = requests.get(url, timeout=10).json()
        return jsonify({"html": construir_mapa(desastres), "count": len(desastres)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# ARRANQUE
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  Monitor Global de Desastres — Frontend")
    print(f"  API esperada en: {API_BASE}")
    print("  Abre: http://localhost:5000")
    print("=" * 55)
    app.run(debug=True, port=5000, use_reloader=True)