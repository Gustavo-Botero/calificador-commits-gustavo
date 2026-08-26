"""Mide la latencia del motor ollama de forma secuencial."""
import statistics
import time

import requests

URL = "http://localhost:8000/clasificar"

MENSAJES = [
    "agrega el endpoint de historial",
    "corrige el error de conexion a la base de datos",
    "actualiza el manual de instalacion",
    "agrega pruebas del clasificador",
    "renombra las variables del modulo de conexion",
    "actualiza las dependencias del proyecto",
    "implementa el healthcheck del contenedor",
    "arregla el calculo de la latencia",
    "documenta la politica de seguridad",
    "simplifica la funcion de registro",
]


def medir(texto):
    """Envia un mensaje y devuelve (milisegundos, tipo clasificado)."""
    inicio = time.time()
    r = requests.post(URL, json={"texto": texto, "motor": "ollama"}, timeout=300)
    ms = (time.time() - inicio) * 1000
    return ms, r.json()["tipo"]


# Calentamiento: la primera peticion incluye la carga del modelo a memoria de
# video. Se mide y se reporta aparte para no contaminar el promedio.
frio_ms, _ = medir("calentamiento del modelo")
print(f"Arranque en frio (no se promedia): {frio_ms:.0f} ms\n")

tiempos = []
for i, texto in enumerate(MENSAJES, start=1):
    ms, tipo = medir(texto)
    tiempos.append(ms)
    print(f"{i:2d}. {ms:8.0f} ms -> {tipo:10s} | {texto[:45]}")

tiempos.sort()
print(f"\nPromedio: {statistics.mean(tiempos):.0f} ms")
print(f"Mediana:  {statistics.median(tiempos):.0f} ms")
print(f"p95:      {tiempos[int(len(tiempos) * 0.95) - 1]:.0f} ms")
print(f"Minimo:   {tiempos[0]:.0f} ms")
print(f"Maximo:   {tiempos[-1]:.0f} ms")
