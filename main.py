import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.responses import FileResponse
import paho.mqtt.client as mqtt

app = FastAPI(title="Monitor de Agua IoT - FullStack")

@app.get("/")
async def leer_dashboard():
    return FileResponse("index.html")

# Configuración del Broker MQTT local
MQTT_BROKER = "localhost"
MQTT_TOPIC = "tanque/1/lecturas"

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()
loop = asyncio.get_event_loop()

# Cuando llega un mensaje de la ESP32 por MQTT
def on_message(client, userdata, msg):
    payload = msg.payload.decode('utf-8')
    print(f"[MQTT Recibido]: {payload}")
    # Reenviar a todos los clientes web conectados por WebSocket
    asyncio.run_coroutine_threadsafe(manager.broadcast(payload), loop)

mqtt_client = mqtt.Client()
mqtt_client.on_message = on_message

@app.on_event("startup")
def startup_event():
    mqtt_client.connect(MQTT_BROKER, 1883, 60)
    mqtt_client.subscribe(MQTT_TOPIC)
    mqtt_client.loop_start()

@app.on_event("shutdown")
def shutdown_event():
    mqtt_client.loop_stop()
    mqtt_client.disconnect()

# CORREGIDO: Ahora apunta exactamente a "/ws" para coincidir con la página web
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)