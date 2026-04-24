import psycopg2, os
from dotenv import load_dotenv
load_dotenv()

DB_CONFIG = {
    "host":            os.getenv("DB_HOST", "127.0.0.1"),
    "database":        os.getenv("DB_NAME", "sismos_db"),
    "user":            os.getenv("DB_USER", "postgres"),
    "password":        os.getenv("DB_PASS", "123"),
    "client_encoding": "utf8"
}

def init_db():
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()
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
    conn.commit(); cur.close(); conn.close()

def guardar_sismos(data):
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()
    for s in data:
        fecha = s.get("utc_date") or s.get("local_date")
        mag   = s.get("magnitude")
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
                fecha, float(mag),
                s.get("latitude"),
                s.get("longitude"),
                referencia
            ))
        except Exception as e:
            print(f"Error insertando: {e}")
    conn.commit(); cur.close(); conn.close()

def obtener_sismos_db():
    conn = psycopg2.connect(**DB_CONFIG)
    cur  = conn.cursor()
    cur.execute("SELECT * FROM sismos ORDER BY fecha DESC LIMIT 15")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows