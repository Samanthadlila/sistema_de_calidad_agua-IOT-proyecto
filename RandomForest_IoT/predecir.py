
import joblib
import pandas as pd

# Cargar modelo
modelo = joblib.load("modelo_random_forest.pkl")

print("================================")
print(" SISTEMA DE CLASIFICACION DE AGUA")
print("================================")

# Solicitar mediciones
nivel = float(input("Nivel del tanque (%): "))
temperatura = float(input("Temperatura del agua (°C): "))
turbidez = float(input("Lectura de turbidez: "))

# Preparar muestra
muestra = pd.DataFrame(
    [[nivel, temperatura, turbidez]],
    columns=["nivel_pct", "temperatura", "turbidez"]
)

# Predicción
resultado = modelo.predict(muestra)[0]

print("\n================================")
print("ESTADO GENERAL DEL TANQUE")
print("================================")

print("Clasificacion:", resultado)

if resultado == "Optima":
    print("El tanque se encuentra dentro de los rangos operativos.")

elif resultado == "Precaucion":
    print("Advertencia: revisar las condiciones del tanque.")

else:
    print("Alerta: una o mas variables estan fuera de rango critico.")

print("================================")
