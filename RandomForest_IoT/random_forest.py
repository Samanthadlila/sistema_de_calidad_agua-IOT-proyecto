
import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import joblib

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    ConfusionMatrixDisplay
)


conexion = sqlite3.connect("iot_sensores.db")

df = pd.read_sql_query("""
    SELECT nivel_pct, temperatura, turbidez
    FROM telemetria
""", conexion)

conexion.close()

print("Registros originales:", len(df))


df = df.replace([np.inf, -np.inf], np.nan)
df = df.dropna(
    subset=["nivel_pct", "temperatura", "turbidez"]
)

# Eliminar error del sensor DS18B20
df = df[df["temperatura"] != -127]

# Eliminar lecturas de turbidez cero provisionalmente
df = df[df["turbidez"] > 0]

print("Registros después de limpieza:", len(df))

# ==========================================
# 3. DEFINIR RANGOS OPERATIVOS
# ==========================================

def clasificar_estado(fila):

    nivel = fila["nivel_pct"]
    temperatura = fila["temperatura"]
    turbidez = fila["turbidez"]

    # Condiciones críticas
    if (
        nivel < 20 or nivel > 90 or
        temperatura < 18 or temperatura > 28 or
        turbidez > 60
    ):
        return "Critica"

    # Condiciones de precaución
    elif (
        nivel < 30 or nivel > 80 or
        temperatura < 20 or temperatura > 28 or
        turbidez > 45
    ):
        return "Precaucion"

    # Todas las variables están en rango óptimo
    else:
        return "Optima"


df["clasificacion"] = df.apply(
    clasificar_estado,
    axis=1
)

print("\nDistribución de clasificaciones:")
print(df["clasificacion"].value_counts())



X = df[[
    "nivel_pct",
    "temperatura",
    "turbidez"
]]

y = df["clasificacion"]


# Estratificar si hay suficientes ejemplos
# de cada categoría.
estratificar = y if y.value_counts().min() >= 2 else None

if estratificar is None:
    print("\nAdvertencia: hay una categoría con menos de 2 registros.")
    print("La división no será estratificada.")

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.20,
    random_state=42,
    stratify=estratificar
)

print("\nRegistros de entrenamiento:", len(X_train))
print("Registros de prueba:", len(X_test))

# ENTRENAR RANDOM FOREST
modelo = RandomForestClassifier(
    n_estimators=100,
    max_depth=10,
    random_state=42,
    class_weight="balanced"
)

modelo.fit(X_train, y_train)

predicciones = modelo.predict(X_test)

print("\n========== RESULTADOS ==========")

print(
    "Exactitud:",
    round(accuracy_score(y_test, predicciones) * 100, 2),
    "%"
)

print("\nReporte de clasificación:")

print(classification_report(
    y_test,
    predicciones,
    zero_division=0
))

# ==========================================
# 8. MATRIZ DE CONFUSIÓN
# ==========================================

ConfusionMatrixDisplay.from_predictions(
    y_test,
    predicciones,
    cmap="Blues"
)

plt.title("Random Forest - Estado del tanque")
plt.tight_layout()
plt.savefig("matriz_confusion.png")
plt.show()

# ==========================================
# 9. IMPORTANCIA DE VARIABLES
# ==========================================

importancias = pd.Series(
    modelo.feature_importances_,
    index=X.columns
).sort_values(ascending=False)

print("\nImportancia de variables:")
print(importancias)

importancias.plot(kind="bar")
plt.title("Importancia de variables - Random Forest")
plt.ylabel("Importancia")
plt.tight_layout()
plt.savefig("importancia_variables.png")
plt.show()

joblib.dump(modelo, "modelo_random_forest.pkl")

print("\nModelo guardado correctamente.")
print("Proceso finalizado.")
