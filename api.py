from flask import Flask, jsonify, request
import requests as req, os, psycopg2
from database import init_db, guardar_sismos, obtener_sismos_db, DB_CONFIG
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

@app.route("/")
def docs():
    return """
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>API Sismos Chile</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            pre { background:#000; color:#00ff88; padding:12px; border-radius:6px; font-size:13px; overflow-x:auto; }
        </style>
    </head>
    <body class="bg-dark text-light p-4">
        <div class="container">
            <h1 class="text-danger mb-1">🌋 API Sismos Chile</h1>
            <p class="text-muted mb-4">Documentación de endpoints disponibles — puerto 8000</p>

            <div class="card bg-secondary mb-3">
                <div class="card-body">
                    <span class="badge bg-success me-2">GET</span>
                    <strong>/api/v1/sismos</strong>
                    <p class="mt-2 mb-1">Retorna los últimos 15 sismos.</p>
                    <pre>[{ "id":"358722", "fecha":"2026-04-23 01:31:21", "mag":2.8, "lat":-22.232, "lon":-68.723, "lugar":"34 km al NE de Calama", "hora":"01:31" }]</pre>
                </div>
            </div>

            <div class="card bg-secondary mb-3">
                <div class="card-body">
                    <span class="badge bg-success me-2">GET</span>
                    <strong>/api/v1/sismos/todos</strong>
                    <p class="mt-2 mb-1">Retorna TODOS los sismos en la base de datos.</p>
                    <pre>[{ "id":"...", "mag":3.1, ... }]</pre>
                </div>
            </div>

            <div class="card bg-secondary mb-3">
                <div class="card-body">
                    <span class="badge bg-success me-2">GET</span>
                    <strong>/api/v1/sismos/&lt;id&gt;</strong>
                    <p class="mt-2 mb-1">Retorna un sismo específico por su ID.</p>
                    <pre>GET /api/v1/sismos/358722
{ "id":"358722", "mag":2.8, "lugar":"34 km al NE de Calama" }</pre>
                </div>
            </div>

            <div class="card bg-secondary mb-3">
                <div class="card-body">
                    <span class="badge bg-success me-2">GET</span>
                    <strong>/api/v1/sismos/fuertes</strong>
                    <p class="mt-2 mb-1">Retorna solo sismos con magnitud mayor o igual a 4.0.</p>
                    <pre>[{ "id":"...", "mag":4.5, "lugar":"..." }]</pre>
                </div>
            </div>

            <div class="card bg-secondary mb-3">
                <div class="card-body">
                    <span class="badge bg-success me-2">GET</span>
                    <strong>/api/v1/estadisticas</strong>
                    <p class="mt-2 mb-1">Retorna estadísticas generales de los sismos.</p>
                    <pre>{ "total":150, "mag_maxima":6.2, "mag_promedio":2.8, "el_mas_fuerte":{ "mag":6.2, "lugar":"..." } }</pre>
                </div>
            </div>

            <div class="card bg-secondary mb-3">
                <div class="card-body">
                    <span class="badge bg-warning text-dark me-2">POST</span>
                    <strong>/api/v1/actualizar</strong>
                    <p class="mt-2 mb-1">Consulta la API externa y guarda nuevos sismos.</p>
                    <pre>{ "insertados": 15 }</pre>
                </div>
            </div>

            <div class="card bg-secondary mb-3">
                <div class="card-body">
                    <span class="badge bg-warning text-dark me-2">POST</span>
                    <strong>/api/v1/sismos</strong>
                    <p class="mt-2 mb-1">Inserta un sismo manualmente.</p>
                    <pre>// Body:
{ "id":"123", "fecha":"2026-04-23 10:00:00", "mag":3.5, "lat":-33.4, "lon":-70.6, "lugar":"Santiago" }
// Respuesta:
{ "status": "ok" }</pre>
                </div>
            </div>

            <p class="text-muted mt-4">Fuente: <a href="https://api.xor.cl/sismo/recent" class="text-danger">api.xor.cl</a></p>
        </div>
    </body>
    </html>
    """, 200, {"Content-Type": "text/html"}


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


@app.route("/api/v1/sismos/todos", methods=["GET"])
def todos_los_sismos():
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()
    cur.execute("SELECT * FROM sismos ORDER BY fecha DESC")
    sismos = cur.fetchall()
    cur.close(); conn.close()
    return jsonify([{
        "id":    s[0],
        "fecha": str(s[1]),
        "mag":   float(s[2]),
        "lat":   float(s[3]),
        "lon":   float(s[4]),
        "lugar": s[5] or "Sin referencia",
        "hora":  s[1].strftime("%H:%M") if s[1] else "--:--"
    } for s in sismos])


@app.route("/api/v1/sismos/<string:sismo_id>", methods=["GET"])
def obtener_por_id(sismo_id):
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()
    cur.execute("SELECT * FROM sismos WHERE id = %s", (sismo_id,))
    s = cur.fetchone()
    cur.close(); conn.close()
    if not s:
        return jsonify({"error": "Sismo no encontrado"}), 404
    return jsonify({
        "id":    s[0],
        "fecha": str(s[1]),
        "mag":   float(s[2]),
        "lat":   float(s[3]),
        "lon":   float(s[4]),
        "lugar": s[5] or "Sin referencia",
        "hora":  s[1].strftime("%H:%M") if s[1] else "--:--"
    })


@app.route("/api/v1/sismos/fuertes", methods=["GET"])
def sismos_fuertes():
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()
    cur.execute("SELECT * FROM sismos WHERE magnitud >= 4.0 ORDER BY fecha DESC")
    sismos = cur.fetchall()
    cur.close(); conn.close()
    return jsonify([{
        "id":    s[0],
        "fecha": str(s[1]),
        "mag":   float(s[2]),
        "lat":   float(s[3]),
        "lon":   float(s[4]),
        "lugar": s[5] or "Sin referencia",
        "hora":  s[1].strftime("%H:%M") if s[1] else "--:--"
    } for s in sismos])


@app.route("/api/v1/estadisticas", methods=["GET"])
def estadisticas():
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()
    cur.execute("SELECT COUNT(*), MAX(magnitud), AVG(magnitud) FROM sismos")
    total, mag_max, mag_avg = cur.fetchone()
    cur.execute("SELECT * FROM sismos ORDER BY magnitud DESC LIMIT 1")
    fuerte = cur.fetchone()
    cur.close(); conn.close()
    return jsonify({
        "total":         total,
        "mag_maxima":    float(mag_max or 0),
        "mag_promedio":  round(float(mag_avg or 0), 2),
        "el_mas_fuerte": {
            "id":    fuerte[0],
            "mag":   float(fuerte[2]),
            "lugar": fuerte[5]
        } if fuerte else None
    })


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