from flask import Flask, render_template, jsonify, request
import requests
import folium
import psycopg2
import json
from database import init_db, guardar_sismos, obtener_sismos_db, DB_CONFIG

app = Flask(__name__)

def actualizar_datos():
    url = "https://api.xor.cl/sismo/recent"
    try:
        response = requests.get(url, timeout=10)
        json_data = response.json()
        events = json_data.get("events", [])
        print(f"=== API devolvio {len(events)} eventos ===")
        if events:
            print("Estructura del primer evento:")
            print(events[0])
        guardar_sismos(events)
    except Exception as e:
        print(f"Error al actualizar: {e}")

@app.route("/")
def index():
    actualizar_datos()
    sismos = obtener_sismos_db()

    mapa = folium.Map(
        location=[-35.6, -71.5],
        zoom_start=5,
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery"
    )

    # Capa de nombres de ciudades encima del satélite
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
        attr="Esri Labels",
        name="Etiquetas",
        overlay=True,
        control=False
    ).add_to(mapa)

    for s in sismos:
        mag = float(s[2])
        if mag >= 6:
            color = "#e74c3c"
            fill = "#e74c3c"
        elif mag >= 4:
            color = "#e67e22"
            fill = "#e67e22"
        else:
            color = "#3498db"
            fill = "#3498db"

        folium.CircleMarker(
            location=[s[3], s[4]],
            radius=mag * 2.5,
            color=color,
            fill=True,
            fill_color=fill,
            fill_opacity=0.7,
            weight=2,
            popup=folium.Popup(
                f"""
                <div style='font-family:Arial;min-width:150px'>
                    <b style='font-size:15px;color:#e74c3c'>{mag} Mw</b><br>
                    <span style='color:#555'>{s[5]}</span><br>
                    <small style='color:#999'>{s[1].strftime('%d/%m/%Y %H:%M') if s[1] else '--'}</small>
                </div>
                """,
                max_width=200
            )
        ).add_to(mapa)

    sismos_json = json.dumps([{
        "mag": float(s[2]),
        "lat": float(s[3]),
        "lon": float(s[4]),
        "lugar": s[5] or "Sin referencia",
        "hora": s[1].strftime('%H:%M') if s[1] else "--:--"
    } for s in sismos], ensure_ascii=False)

    return render_template("index.html", mapa=mapa._repr_html_(), sismos=sismos, sismos_json=sismos_json)

@app.route("/api/v1/sismos", methods=['GET', 'POST'])
def api_sismos():
    if request.method == 'GET':
        sismos = obtener_sismos_db()
        return jsonify([{"id": s[0], "fecha": str(s[1]), "mag": float(s[2]), "lugar": s[5]} for s in sismos])

    if request.method == 'POST':
        datos = request.get_json()
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO sismos (id, fecha, magnitud, latitud, longitud, referencia)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (datos['id'], datos['fecha'], datos['mag'], datos['lat'], datos['lon'], datos['lugar']))
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({"status": "Sismo registrado en Postgres"}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)