
import json
import asyncio
import sqlite3
from pathlib import Path

import joblib
import pandas as pd
import paho.mqtt.client as mqtt

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(title="IoT Middleware - Monitoreo y Random Forest")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# CONFIGURACIÓN
# ==========================================

BASE_DIR = Path(__file__).resolve().parent

MQTT_BROKER = "localhost"
MQTT_TOPIC = "tanque/1/lecturas"

DB_NAME = str(BASE_DIR / "iot_sensores.db")

MODEL_PATH = BASE_DIR / "RandomForest_IoT" / "modelo_random_forest.pkl"

# Cargar modelo entrenado
try:
    modelo = joblib.load(MODEL_PATH)
    print("Random Forest cargado correctamente.")
except Exception as e:
    modelo = None
    print(f"ERROR al cargar el modelo: {e}")


# ==========================================
# BASE DE DATOS
# ==========================================

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS telemetria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT,
            distancia_cm REAL,
            nivel_pct REAL,
            temperatura REAL,
            turbidez REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Agregar columna a bases existentes, sin borrar registros
    columnas = [
        row[1] for row in cursor.execute(
            "PRAGMA table_info(telemetria)"
        ).fetchall()
    ]

    if "clasificacion" not in columnas:
        cursor.execute(
            "ALTER TABLE telemetria ADD COLUMN clasificacion TEXT"
        )

    conn.commit()
    conn.close()


init_db()


# ==========================================
# RANDOM FOREST
# ==========================================

def predecir_estado(nivel, temperatura, turbidez):

    if modelo is None:
        return "Sin clasificar"

    # Evitar predecir con lecturas inválidas
    if temperatura == -127 or nivel is None or temperatura is None or turbidez is None:
        return "Sin clasificar"

    muestra = pd.DataFrame(
        [[nivel, temperatura, turbidez]],
        columns=["nivel_pct", "temperatura", "turbidez"]
    )

    resultado = modelo.predict(muestra)[0]

    return str(resultado)


# ==========================================
# WEBSOCKET
# ==========================================

class ConnectionManager:

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections.copy():
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)


manager = ConnectionManager()
loop = None


# ==========================================
# MQTT
# ==========================================

def on_message(client, userdata, msg):

    payload = msg.payload.decode("utf-8")
    print(f"[MQTT Recibido]: {payload}")

    try:
        data_json = json.loads(payload)

        node_id = data_json.get("node_id", "ESP32_AGUA_01")
        data = data_json.get("data", {})

        distancia_cm = float(data.get("distancia_cm", 0.0))
        nivel_pct = float(data.get("nivel_pct", 0.0))
        temperatura = float(data.get("temperatura", -127))
        turbidez = float(data.get("turbidez", 0.0))

        # Ejecutar Random Forest
        clasificacion = predecir_estado(
            nivel_pct,
            temperatura,
            turbidez
        )

        # Agregar clasificación al mensaje para el dashboard
        data["clasificacion"] = clasificacion
        data_json["data"] = data

        # Guardar mediciones y clasificación
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO telemetria (
                node_id,
                distancia_cm,
                nivel_pct,
                temperatura,
                turbidez,
                clasificacion
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            node_id,
            distancia_cm,
            nivel_pct,
            temperatura,
            turbidez,
            clasificacion
        ))

        conn.commit()
        conn.close()

        print(f"[RANDOM FOREST]: {clasificacion}")

        # Enviar datos actualizados al dashboard
        mensaje_dashboard = json.dumps(data_json)

        if loop is not None and loop.is_running():
            asyncio.run_coroutine_threadsafe(
                manager.broadcast(mensaje_dashboard),
                loop
            )

    except Exception as e:
        print(f"Error procesando lectura MQTT: {e}")


mqtt_client = mqtt.Client()
mqtt_client.on_message = on_message


# ==========================================
# INICIO Y CIERRE
# ==========================================

@app.on_event("startup")
def startup_event():

    global loop
    loop = asyncio.get_running_loop()

    try:
        mqtt_client.connect(MQTT_BROKER, 1883, 60)
        mqtt_client.subscribe(MQTT_TOPIC)
        mqtt_client.loop_start()

        print("Conectado al broker MQTT.")

    except Exception as e:
        print(f"Error MQTT: {e}")


@app.on_event("shutdown")
def shutdown_event():

    mqtt_client.loop_stop()
    mqtt_client.disconnect()


# ==========================================
# HISTORIAL
# ==========================================

@app.get("/api/historial")
def get_historial():

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM telemetria
        ORDER BY id DESC
        LIMIT 15
    """)

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


# ==========================================
# WEBSOCKET ENDPOINT
# ==========================================

@app.websocket("/ws")
@app.websocket("/ws/telemetria")
async def websocket_endpoint(websocket: WebSocket):

    await manager.connect(websocket)

    try:
        while True:
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket)
