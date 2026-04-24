from flask import Flask, render_template, jsonify, request
import requests, folium, psycopg2, json, os
from database import init_db, DB_CONFIG
from dotenv import load_dotenv
load_dotenv()

app      = Flask(__name__)
API_BASE = os.getenv("API_BASE", "http://localhost:8000")

@app.route("/")
def index():
    try:
        requests.post(f"{API_BASE}/api/v1/actualizar", timeout=10)
    except:
        pass

    try:
        sismos = requests.get(f"{API_BASE}/api/v1/sismos", timeout=5).json()
    except:
        sismos = []

    mapa = folium.Map(location=[-35.6, -71.5], zoom_start=5)

    for s in sismos:
        mag   = s["mag"]
        color = "#e74c3c" if mag >= 6 else "#e67e22" if mag >= 4 else "#3498db"
        folium.CircleMarker(
            location=[s["lat"], s["lon"]],
            radius=mag * 2.5,
            color=color, fill=True, fill_color=color,
            fill_opacity=0.7, weight=2,
            popup=folium.Popup(
                f"<b>{mag} Mw</b><br>{s['lugar']}<br><small>{s['hora']} hrs</small>",
                max_width=200
            )
        ).add_to(mapa)

    sismos_json = json.dumps(sismos, ensure_ascii=False)
    return render_template("index.html",
                           mapa=mapa._repr_html_(),
                           sismos=sismos,
                           sismos_json=sismos_json)

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)