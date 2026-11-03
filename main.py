import json
import asyncio
import sqlite3
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import paho.mqtt.client as mqtt

app = FastAPI(title="IoT Middleware - Práctica 3 con Persistencia")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MQTT_BROKER = "localhost"
MQTT_TOPIC = "tanque/1/lecturas"

DB_NAME = "iot_sensores.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS telemetria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT,
            distancia_cm REAL,
            nivel_pct REAL,
            temperatura REAL,
            turbidez REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

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
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()
loop = asyncio.get_event_loop()

def on_message(client, userdata, msg):
    payload = msg.payload.decode('utf-8')
    print(f"[MQTT Recibido]: {payload}")
    
    try:
        data_json = json.loads(payload)
        node_id = data_json.get("node_id", "ESP32_AGUA_01")
        data = data_json.get("data", {})
        
        distancia_cm = data.get("distancia_cm", 0.0)
        nivel_pct = data.get("nivel_pct", 0.0)
        temperatura = data.get("temperatura", 0.0)
        turbidez = data.get("turbidez", 0.0)

        # guardado en SQLite
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO telemetria (node_id, distancia_cm, nivel_pct, temperatura, turbidez)
            VALUES (?, ?, ?, ?, ?)
        ''', (node_id, distancia_cm, nivel_pct, temperatura, turbidez))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"No se pudo guardan en la base de datos: {e}")

    asyncio.run_coroutine_threadsafe(manager.broadcast(payload), loop)

mqtt_client = mqtt.Client()
mqtt_client.on_message = on_message

@app.on_event("startup")
def startup_event():
    try:
        mqtt_client.connect(MQTT_BROKER, 1883, 60)
        mqtt_client.subscribe(MQTT_TOPIC)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"⚠️ Error MQTT: {e}")

@app.on_event("shutdown")
def shutdown_event():
    mqtt_client.loop_stop()
    mqtt_client.disconnect()

# ruta de la telemetria
@app.get("/api/historial")
def get_historial():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM telemetria ORDER BY id DESC LIMIT 15")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.websocket("/ws")
@app.websocket("/ws/telemetria")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)