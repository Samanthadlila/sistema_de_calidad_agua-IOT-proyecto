import asyncio, json, time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import paho.mqtt.client as mqtt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

MQTT_HOST = "localhost"                      # Mosquitto instalado en tu computadora
T_CONTROL = "dispositivos/esp32/control"     # tópico para mandar órdenes a la ESP32

# ---------- Base de datos: SQLite se guarda en el archivo iot.db (se crea solo) ----------
engine = create_async_engine("sqlite+aiosqlite:///iot.db")
Session = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class LecturaIoT(Base):
    __tablename__ = "lecturas_iot"
    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[str]
    valor: Mapped[Optional[float]]            # distancia_cm (la señal principal)
    nivel_pct: Mapped[Optional[float]]
    temperatura: Mapped[Optional[float]]
    turbidez: Mapped[Optional[float]]
    heap_free: Mapped[Optional[int]]
    sequence_id: Mapped[Optional[int]]
    latencia: Mapped[Optional[float]]         # ms
    fecha_registro: Mapped[datetime] = mapped_column(default=datetime.now)

# ---------- Estado en memoria ----------
clientes: set[WebSocket] = set()
loop = None
offset = None        # solo se usa si timestamp_ms viene de millis() y no de hora real
ultimo_seq = None

async def procesar(d: dict):
    global offset, ultimo_seq
    data = d["data"]
    seq = d.get("sequence_id")
    ts = d.get("timestamp_ms")
    ahora = time.time() * 1000

    lat = None
    if ts is not None:
        if seq is not None and ultimo_seq is not None and seq < ultimo_seq:
            offset = None                    # la ESP32 se reinició
        if ts > 1e12:                        # hora real (NTP): latencia exacta
            lat = max(0, ahora - ts)
        else:                                # millis(): latencia relativa al mejor caso
            diff = ahora - ts
            offset = diff if offset is None else min(offset, diff)
            lat = max(0, diff - offset)
    if seq is not None:
        ultimo_seq = seq

    async with Session() as s:
        s.add(LecturaIoT(
            node_id=d.get("node_id", "?"),
            valor=data.get("distancia_cm"),
            nivel_pct=data.get("nivel_pct"),
            temperatura=data.get("temperatura"),
            turbidez=data.get("turbidez"),
            heap_free=d.get("heap_free"),
            sequence_id=seq,
            latencia=None if lat is None else round(lat, 1),
        ))
        await s.commit()

    msg = {
        "node_id": d.get("node_id"),
        "data": data,
        "sequence_id": seq,
        "latencia_ms": None if lat is None else round(lat, 1),
        "heap_free": d.get("heap_free"),
    }
    for ws in list(clientes):
        try:
            await ws.send_json(msg)
        except Exception:
            clientes.discard(ws)

# ---------- MQTT en un hilo aparte (no bloquea FastAPI) ----------
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def on_connect(client, userdata, flags, reason_code, properties=None):
    client.subscribe("#")                    # escucha todo y filtra abajo

def on_message(client, userdata, msg):
    try:
        d = json.loads(msg.payload)
        if isinstance(d, dict) and isinstance(d.get("data"), dict):   # solo telemetría
            print("[MQTT Recibido]:", d)
            asyncio.run_coroutine_threadsafe(procesar(d), loop)
    except Exception as e:
        print("Mensaje ignorado:", e)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global loop
    loop = asyncio.get_running_loop()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect_async(MQTT_HOST, 1883)
    mqtt_client.loop_start()
    yield
    mqtt_client.loop_stop()

app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ---------- Historial para la tabla del dashboard ----------
@app.get("/api/historial")
async def historial(limite: int = 15):
    async with Session() as s:
        res = await s.execute(select(LecturaIoT).order_by(LecturaIoT.id.desc()).limit(limite))
        return [{
            "id": r.id, "node_id": r.node_id, "distancia_cm": r.valor,
            "temperatura": r.temperatura, "turbidez": r.turbidez,
            "sequence_id": r.sequence_id, "latencia": r.latencia,
            "timestamp": r.fecha_registro.strftime("%Y-%m-%d %H:%M:%S"),
        } for r in res.scalars()]

# ---------- WebSocket: telemetría hacia la web y órdenes hacia la ESP32 ----------
@app.websocket("/ws")
@app.websocket("/ws/telemetria")
async def ws_telemetria(ws: WebSocket):
    await ws.accept()
    clientes.add(ws)
    try:
        while True:
            orden = await ws.receive_json()                       
            mqtt_client.publish(T_CONTROL, json.dumps(orden))
    except WebSocketDisconnect:
        clientes.discard(ws)