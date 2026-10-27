#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// WIFI
const char* ssid = "dinero";
const char* password = "123456789-";

// IP del ESP32 MQTT
const char* mqtt_server = "192.168.137.229"; 

WiFiClient espClient;
PubSubClient client(espClient);

// Pines
#define TRIG 18
#define ECHO 5
#define ONE_WIRE_BUS 4 // Pin digital donde va el cable amarillo del DS18B20
#define PIN_TURBIDEZ 34

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

unsigned long previousMillis = 0;
const long interval = 500;

void setup_wifi() {
  delay(10);
  Serial.println();
  Serial.print("Conectando a Wi-Fi: ");
  Serial.println(ssid);

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi conectado.");
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Intentando conexión MQTT...");
    if (client.connect("ESP32_Agua_Client")) {
      Serial.println("¡Conectado al Broker MQTT!");
    } else {
      Serial.print("falló, rc=");
      Serial.print(client.state());
      Serial.println(" intentando de nuevo en 2 segundos");
      delay(2000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  
  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);
  pinMode(PIN_TURBIDEZ, INPUT);

  // Iniciar sensor de temperatura
  sensors.begin();

  setup_wifi();
  client.setServer(mqtt_server, 1883);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  unsigned long currentMillis = millis();
  if (currentMillis - previousMillis >= interval) {
    previousMillis = currentMillis;

    // 1. Ultrasonico
    digitalWrite(TRIG, LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG, LOW);

    long duracion = pulseIn(ECHO, HIGH);
    float distancia_cm = duracion * 0.0343 / 2;
    float nivel_pct = max(0.0, min(100.0, (1.0 - (distancia_cm / 50.0)) * 100.0));

    // Temperatur
    sensors.requestTemperatures(); 
    float temperatura_c = sensors.getTempCByIndex(0);

    // 3. Turbidez
    float raw_turbidez = analogRead(PIN_TURBIDEZ);
    float valor_turbidez = (raw_turbidez / 4095.0) * 100.0;

    // JSON
    StaticJsonDocument<384> doc;
    doc["node_id"] = "ESP32_AGUA_01";
    
    JsonObject data = doc.createNestedObject("data");
    data["distancia_cm"] = round(distancia_cm * 100.0) / 100.0;
    data["nivel_cm"] = round(distancia_cm * 100.0) / 100.0; 
    data["nivel_pct"] = round(nivel_pct * 100.0) / 100.0;
    data["temperatura"] = round(temperatura_c * 100.0) / 100.0; 
    data["turbidez"] = round(valor_turbidez * 100.0) / 100.0;

    doc["heap_free"] = ESP.getFreeHeap();

    char buffer[384];
    serializeJson(doc, buffer);
    
    client.publish("tanque/1/lecturas", buffer);
    Serial.println(buffer);
  }
}