"""API REST del clasificador de mensajes de commit."""
import os
import re
import time
from contextlib import closing

import psycopg2
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="Clasificador de commits", version="1.0.0")

TIPOS = ["feat", "fix", "docs", "test", "chore", "refactor"]

REGLAS = {
    "fix": r"\b(fix|corrig|arregl|error|bug|falla)",
    "docs": r"\b(doc|readme|manual|coment)",
    "test": r"\b(test|prueba|pytest|cobertura)",
    "chore": r"\b(actualiz|dependenc|version|limpi|config)",
    "refactor": r"\b(refactor|reorganiz|renombr|simplific)",
    "feat": r"\b(agreg|add|nuev|implement|crear|feature)",
}


def conexion():
    """Abre una conexion a PostgreSQL usando las variables de entorno."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def registrar(motor, modelo, entrada, salida, latencia_ms):
    """Guarda la inferencia en la base de datos."""
    with closing(conexion()) as con, con, con.cursor() as cur:
        cur.execute(
            "INSERT INTO inferencias (motor, modelo, entrada, salida, latencia_ms)"
            " VALUES (%s, %s, %s, %s, %s)",
            (motor, modelo, entrada, salida, int(latencia_ms)),
        )


def clasificar_eco(texto: str) -> str:
    """Motor por reglas: linea base sin modelo, no consume memoria."""
    minusculas = texto.lower()
    for tipo, patron in REGLAS.items():
        if re.search(patron, minusculas):
            return tipo
    return "chore"


def clasificar_ollama(texto: str) -> str:
    """Motor con el modelo de lenguaje local."""
    prompt = (
        "Clasifica el siguiente mensaje de commit en UNA de estas categorias: "
        + ", ".join(TIPOS)
        + ". Responde unicamente con la palabra de la categoria, sin explicaciones.\n"
        + f"Mensaje: {texto}\nCategoria:"
    )
    respuesta = requests.post(
        os.getenv("OLLAMA_URL"),
        json={
            "model": os.getenv("MODELO_OLLAMA"),
            "prompt": prompt,
            "stream": False,
            "options": {"num_ctx": 2048, "num_predict": 8, "temperature": 0},
        },
        timeout=180,
    )
    respuesta.raise_for_status()
    texto_salida = respuesta.json()["response"].strip().lower()
    for tipo in TIPOS:
        if tipo in texto_salida:
            return tipo
    return "desconocido"


class Peticion(BaseModel):
    texto: str
    motor: str | None = None


@app.get("/health")
def health():
    """Indica si el servicio y la base de datos estan disponibles."""
    try:
        with closing(conexion()) as con, con.cursor() as cur:
            cur.execute("SELECT 1")
        return {"estado": "ok", "base_datos": "ok"}
    except psycopg2.Error as e:
        raise HTTPException(status_code=503, detail="Base de datos no disponible") from e


@app.post("/clasificar")
def clasificar(p: Peticion):
    """Clasifica un mensaje de commit y registra la inferencia."""
    motor = p.motor or os.getenv("MOTOR_POR_DEFECTO", "eco")
    inicio = time.time()

    if motor == "eco":
        modelo = "reglas-v1"
        salida = clasificar_eco(p.texto)
    elif motor == "ollama":
        modelo = os.getenv("MODELO_OLLAMA")
        salida = clasificar_ollama(p.texto)
    else:
        raise HTTPException(status_code=400, detail="motor debe ser eco u ollama")

    latencia_ms = (time.time() - inicio) * 1000
    registrar(motor, modelo, p.texto, salida, latencia_ms)
    return {
        "motor": motor,
        "modelo": modelo,
        "entrada": p.texto,
        "tipo": salida,
        "latencia_ms": round(latencia_ms),
    }


@app.get("/inferencias")
def inferencias(limite: int = 20):
    """Devuelve las ultimas inferencias registradas."""
    with closing(conexion()) as con, con.cursor() as cur:
        cur.execute(
            "SELECT id, fecha, motor, modelo, entrada, salida, latencia_ms"
            " FROM inferencias ORDER BY id DESC LIMIT %s",
            (limite,),
        )
        filas = cur.fetchall()
    columnas = ["id", "fecha", "motor", "modelo", "entrada", "salida", "latencia_ms"]
    return [dict(zip(columnas, f)) for f in filas]
