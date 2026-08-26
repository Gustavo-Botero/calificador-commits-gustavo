# Clasificador de mensajes de commit

Servicio de inferencia local que clasifica mensajes de commit en las categorías de
[Conventional Commits](https://www.conventionalcommits.org/) — `feat`, `fix`, `docs`,
`test`, `chore` y `refactor` — usando un modelo de lenguaje ejecutado en la propia
máquina, sin enviar datos a terceros.

Cada clasificación queda registrada en PostgreSQL junto con su latencia, de modo que
el servicio es también su propia bitácora de medición.

Proyecto integrador de la formación **Implementación de Soluciones de Inteligencia
Artificial** (SENA, ficha 21730210).

## Cómo funciona

La API expone dos motores de clasificación intercambiables:

| Motor | Cómo decide | Latencia típica | Para qué sirve |
|---|---|---|---|
| `eco` | Expresiones regulares | ~0 ms | Línea base. Funciona sin modelo y sin GPU |
| `ollama` | Modelo de lenguaje local | ~110 ms | El objeto de estudio del proyecto |

El motor `eco` no es un relleno: es el patrón de comparación contra el cual se mide
si el modelo aporta valor. En las pruebas de la semana 2 hubo casos donde las reglas
acertaron y el modelo falló.

El detalle de arquitectura, puertos y seguridad está en
[`docs/manual-tecnico.md`](docs/manual-tecnico.md).

## Requisitos previos

- **Linux** (probado en Arch Linux; ver notas para Ubuntu más abajo)
- **Docker** con el servicio activo y el usuario en el grupo `docker`
- **Python 3.12 o superior**
- **Ollama** con un modelo descargado
- **8 GB de RAM** o más

Para instalarlos automáticamente en Arch Linux:

```bash
./setup.sh
```

El script es idempotente: si algo ya está instalado lo informa y continúa. Detecta la
GPU y elige el backend de Ollama adecuado (`ollama-cuda` desde *compute capability*
7.5, `ollama-vulkan` por debajo).

> **En Ubuntu/Debian** `setup.sh` no funciona, porque usa `pacman`. Siga el paso 2 y 3
> de la guía del curso, que instalan lo mismo con `apt`.

Para verificar el estado del entorno en cualquier momento:

```bash
./diagnostico.sh
```

## Instalación

### 1. Clonar el repositorio

```bash
git clone git@github.com:Gustavo-Botero/calificador-commits-gustavo.git
cd calificador-commits-gustavo
```

### 2. Configurar las variables de entorno

```bash
cp .env.example .env
```

El archivo `.env` **nunca se sube al repositorio**. Revise que `MODELO_OLLAMA`
corresponda a su perfil de hardware:

| RAM | Perfil | Modelo |
|---|---|---|
| 16 GB o más | A | `qwen2.5-coder:1.5b` |
| 8 GB | B | `qwen2.5:0.5b` |
| 4 GB | C | `gemma3:270m` |

### 3. Descargar el modelo

```bash
ollama pull qwen2.5-coder:1.5b     # el de su perfil
ollama list                         # confirmar que quedó
```

### 4. Levantar la base de datos

```bash
docker run -d \
  --name db-ia \
  -e POSTGRES_PASSWORD=claveAdmin123 \
  -e POSTGRES_DB=iadb \
  -p 127.0.0.1:5432:5432 \
  -v pgdata:/var/lib/postgresql/data \
  postgres:16-alpine \
  -c shared_buffers=32MB -c max_connections=20
```

Cree la tabla y el rol de aplicación:

```bash
docker exec -i db-ia psql -U postgres -d iadb < db/init.sql
```

Debe imprimir `CREATE TABLE`, `CREATE ROLE` y cuatro `GRANT`.

### 5. Instalar las dependencias de Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> En Arch y Debian modernos, instalar sin el entorno virtual falla con
> `externally-managed-environment`. Es una protección del sistema, no un error:
> la solución es activar el `.venv`, nunca `sudo pip`.

## Uso

### Levantar el servicio

```bash
source .venv/bin/activate          # en cada terminal nueva
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

La terminal queda mostrando los registros. Abra otra para hacer pruebas.

Si el equipo se reinició, primero reviva la base con `docker start db-ia`
(`start`, no `run`: `run` intentaría crear un contenedor nuevo con un nombre
que ya existe).

### Documentación interactiva

Abra **http://localhost:8000/docs**. FastAPI genera esa página a partir del código;
desde ahí puede ejecutar los tres endpoints sin escribir comandos.

### Endpoints

#### `GET /health`

Indica si el servicio y la base de datos responden.

```bash
curl -s http://localhost:8000/health
```
```json
{"estado": "ok", "base_datos": "ok"}
```

Devuelve **503** si la base no está disponible.

#### `POST /clasificar`

Clasifica un mensaje y registra la inferencia.

```bash
curl -s -X POST http://localhost:8000/clasificar \
  -H 'Content-Type: application/json' \
  -d '{"texto":"corrige el error de conexion","motor":"eco"}'
```
```json
{
  "motor": "eco",
  "modelo": "reglas-v1",
  "entrada": "corrige el error de conexion",
  "tipo": "fix",
  "latencia_ms": 0
}
```

`motor` es opcional: si se omite se usa `MOTOR_POR_DEFECTO` del `.env`.

> La primera petición con `motor: ollama` puede tardar unos segundos porque el
> modelo debe cargarse en memoria. Las siguientes son mucho más rápidas.

#### `GET /inferencias`

Devuelve el historial, más reciente primero. Acepta `?limite=N` (20 por omisión).

```bash
curl -s 'http://localhost:8000/inferencias?limite=5'
```

### Consultar la base de datos

```bash
docker exec -it db-ia psql -U postgres -d iadb
```

```sql
SELECT motor, salida, latencia_ms FROM inferencias ORDER BY id DESC LIMIT 10;
\q
```

### Detener el servicio

`Ctrl + C` en la terminal de la API. Para la base de datos:

```bash
docker stop db-ia
```

Los datos sobreviven en el volumen `pgdata`. Solo se pierden con
`docker volume rm pgdata`.

## Verificar que la instalación quedó bien

```bash
# 1. La base responde
curl -s http://localhost:8000/health

# 2. Los dos motores clasifican
curl -s -X POST http://localhost:8000/clasificar -H 'Content-Type: application/json' \
  -d '{"texto":"agrega el endpoint de usuarios","motor":"eco"}'
curl -s -X POST http://localhost:8000/clasificar -H 'Content-Type: application/json' \
  -d '{"texto":"agrega el endpoint de usuarios","motor":"ollama"}'

# 3. Quedaron registradas
curl -s 'http://localhost:8000/inferencias?limite=5'

# 4. La aplicación NO puede borrar el historial
docker exec -i -e PGPASSWORD=claveApp456 db-ia \
  psql -U app_ia -d iadb -c "DELETE FROM inferencias;"
# esperado: ERROR: permission denied for table inferencias
```

El punto 4 no es un error: es la comprobación de que el rol de la aplicación tiene
privilegios mínimos y no puede alterar el historial de auditoría.

## Solución de problemas

| Síntoma | Causa | Solución |
|---|---|---|
| `ModuleNotFoundError: No module named 'fastapi'` | El entorno virtual no está activo | `source .venv/bin/activate` |
| `/health` devuelve `503` | El contenedor está detenido | `docker start db-ia` |
| `address already in use` | Ya hay una API en el puerto 8000 | `fuser -k 8000/tcp` |
| El motor `ollama` devuelve error 500 | Ollama detenido o modelo ausente | `systemctl status ollama` y `ollama list` |
| `permission denied ... docker daemon socket` | Falta reabrir sesión tras `usermod -aG docker` | Cerrar sesión y volver a entrar |
| `externally-managed-environment` | Se instaló fuera del `.venv` | Activar el entorno virtual |
| `port is already allocated` | Otro contenedor ocupa el 5432 | `docker ps` para identificarlo |

Si nada de lo anterior aplica, ejecute `./diagnostico.sh` y adjunte la salida al
reportar el problema.

## Estructura del proyecto

```
.
├── app/main.py            API FastAPI: endpoints y motores de clasificación
├── db/init.sql            Tabla inferencias y rol de privilegios mínimos
├── docs/
│   ├── informe-tecnico.md   Caracterización del modelo y decisiones de entorno
│   └── manual-tecnico.md    Arquitectura, puertos y seguridad
├── tests/                 Pruebas automatizadas (semana 4)
├── setup.sh               Aprovisionamiento del entorno (Arch Linux)
├── diagnostico.sh         Reporte del estado del entorno
├── requirements.txt       Dependencias fijadas
└── .env.example           Plantilla de configuración
```

## Estado del proyecto

| Semana | Entregable | Estado |
|---|---|---|
| 1 | Entorno, scripts y caracterización del modelo | ✅ |
| 2 | Backend con PostgreSQL y clasificador | ✅ |
| 3 | Dockerfile multietapa, Compose y CI | ⏳ |
| 4 | Pruebas automatizadas y de carga | ⏳ |
| 5 | Documentación, respaldo y release v1.0.0 | ⏳ |

> A partir de la semana 3 el proyecto se levantará con un solo comando
> (`docker compose up -d --build`) y esta sección de instalación se simplificará.

## Licencia

Proyecto formativo sin licencia de distribución.
