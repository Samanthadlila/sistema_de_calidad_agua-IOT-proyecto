import sqlite3
import pandas as pd
import numpy as np

import matplotlib.pyplot as plt
import seaborn as sns

# --------------------------------
# Cargar datos
# --------------------------------

conn = sqlite3.connect("iot.db")

df = pd.read_sql_query("""
SELECT *
FROM lecturas_iot
ORDER BY id ASC
""", conn)

conn.close()

print("\nPRIMEROS REGISTROS")
print(df.head())

# --------------------------------
# Limpieza
# --------------------------------

df["fecha_registro"] = pd.to_datetime(
    df["fecha_registro"]
)

df = df.dropna()

# --------------------------------
# Estadísticos
# --------------------------------

print("\nESTADISTICOS GENERALES")
print(df.describe())

# --------------------------------
# Media
# --------------------------------

print("\nMEDIA")

print("Distancia:",
      df["valor"].mean())

print("Temperatura:",
      df["temperatura"].mean())

print("Latencia:",
      df["latencia"].mean())

# --------------------------------
# Mediana
# --------------------------------

print("\nMEDIANA")

print("Distancia:",
      df["valor"].median())

print("Temperatura:",
      df["temperatura"].median())

print("Latencia:",
      df["latencia"].median())

# --------------------------------
# Moda
# --------------------------------

print("\nMODA")

print(df["latencia"].mode())

# --------------------------------
# Desviacion estandar
# --------------------------------

print("\nDESVIACION ESTANDAR")

print(df["latencia"].std())

# --------------------------------
# Varianza
# --------------------------------

print("\nVARIANZA")

print(df["latencia"].var())

# --------------------------------
# OUTLIERS IQR
# --------------------------------

Q1 = df["latencia"].quantile(0.25)

Q3 = df["latencia"].quantile(0.75)

IQR = Q3 - Q1

print("\nIQR LATENCIA")
print(IQR)

lim_sup = Q3 + (1.5 * IQR)

outliers = df[
    df["latencia"] > lim_sup
]

print("\nTOTAL OUTLIERS")

print(len(outliers))


# --------------------------------
# PERDIDA DE PAQUETES
# --------------------------------

seq_min = df["sequence_id"].min()

seq_max = df["sequence_id"].max()

esperados = seq_max - seq_min + 1

recibidos = len(df)

perdida = (
    1 - (recibidos / esperados)
) * 100

print("\nPERDIDA DE PAQUETES")

print(
    f"{perdida:.2f}%"
)

# --------------------------------
# FRECUENCIA REAL
# --------------------------------

df["delta_t_ms"] = (
    df["fecha_registro"]
    .diff()
    .dt.total_seconds()
    * 1000
)

print("\nFRECUENCIA REAL")

print(
    df["delta_t_ms"].mean()
)

# --------------------------------
# GRAFICA TEMPORAL
# --------------------------------

plt.figure(figsize=(12,5))

plt.plot(
    df["fecha_registro"],
    df["valor"]
)

plt.title(
    "Distancia vs Tiempo"
)

plt.xlabel("Tiempo")

plt.ylabel("Distancia (cm)")

plt.grid()

plt.show()

# --------------------------------
# BOXPLOT LATENCIA
# --------------------------------

plt.figure(figsize=(8,6))

sns.boxplot(
    y=df["latencia"]
)

plt.title(
    "Boxplot Latencia"
)

plt.show()

# --------------------------------
# HISTOGRAMA LATENCIA
# --------------------------------

plt.figure(figsize=(8,6))

sns.histplot(
    df["latencia"],
    kde=True
)

plt.title(
    "Distribucion de Latencia"
)

plt.show()

# --------------------------------
# HEATMAP
# --------------------------------

corr = df[
    [
        "valor",
        "temperatura",
        "turbidez",
        "latencia",
        "nivel_pct"
    ]
].corr()

plt.figure(figsize=(8,6))

sns.heatmap(
    corr,
    annot=True,
    cmap="coolwarm"
)

plt.title(
    "Matriz de Correlacion"
)

plt.show()