from flask import Flask, jsonify, request
import requests as req, os, psycopg2
from database import init_db, guardar_sismos, obtener_sismos_db, DB_CONFIG
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

@app.route("/api/v1/sismos", methods=["GET"])
def listar_sismos():
    sismos = obtener_sismos_db()
    return jsonify([{
        "id":    s[0],
        "fecha": str(s[1]),
        "mag":   float(s[2]),
        "lat":   float(s[3]),
        "lon":   float(s[4]),
        "lugar": s[5] or "Sin referencia",
        "hora":  s[1].strftime("%H:%M") if s[1] else "--:--"
    } for s in sismos])

@app.route("/api/v1/actualizar", methods=["POST"])
def actualizar():
    try:
        data   = req.get("https://api.xor.cl/sismo/recent", timeout=10).json()
        events = data.get("events", [])
        guardar_sismos(events)
        return jsonify({"insertados": len(events)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/v1/sismos", methods=["POST"])
def insertar_sismo():
    datos = request.get_json()
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO sismos (id, fecha, magnitud, latitud, longitud, referencia)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (datos["id"], datos["fecha"], datos["mag"],
              datos["lat"], datos["lon"], datos["lugar"]))
        conn.commit(); cur.close(); conn.close()
        return jsonify({"status": "ok"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    init_db()
    app.run(port=8000, debug=True)