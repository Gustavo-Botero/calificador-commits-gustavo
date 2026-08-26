# Informe técnico

## Caracterización del modelo local (Semana 1 · AA1)

Medición realizada el 2026-08-21 sobre el entorno descrito abajo.

| Dato | Cómo se obtuvo | Valor |
|---|---|---|
| Perfil de hardware | Sección 2 de la guía | **A** (16 GB de RAM o más) |
| RAM total del equipo | `free -h` | 31 GiB |
| Modelo y etiqueta | `ollama list` | `qwen2.5-coder:1.5b` |
| Tamaño en disco | `ollama list` | 986 MB |
| Latencia de 5 ejecuciones (ms) | `time curl ...` cinco veces | 22, 21, 41, 23, 23 |
| Latencia promedio | Promedio de las cinco | **26 ms** |
| RAM usada durante la inferencia | `free -h` mientras responde | Sin variación apreciable (~18 GiB usados, igual que en reposo): el modelo reside en VRAM, no en RAM |
| Calidad percibida (1 a 5) | Criterio propio | **4** — responde correctamente a instrucciones simples de clasificación y a peticiones cortas de código, que es el uso que le dará el proyecto; se degrada en razonamiento largo o contexto extenso, comportamiento esperado por debajo de 2 000 millones de parámetros |

### Comando de medición

```bash
time curl -s http://localhost:11434/api/generate -d '{
  "model": "qwen2.5-coder:1.5b",
  "prompt": "Responde solo con una palabra: hola",
  "stream": false
}'
```

Las latencias reportadas corresponden al campo `total_duration` de la respuesta JSON,
convertido de nanosegundos a milisegundos. La **primera** ejecución tras arrancar el
servicio tomó **250 ms** porque incluye la carga del modelo a memoria de video
(`load_duration`); las cinco mediciones de la tabla son con el modelo ya cargado.

> **Alcance de esta medición.** Los 26 ms miden únicamente la inferencia dentro de
> Ollama, consultando su API directamente desde el equipo. No incluyen el recorrido
> completo que sí atraviesa una petición real a la solución: cliente → contenedor
> `api-ia` → `host.docker.internal` → Ollama → vuelta → `INSERT` en PostgreSQL. Esa
> latencia de extremo a extremo se midió en la semana 4 (prueba P-09) y resultó de
> **116 ms de mediana**. Ambas cifras son correctas y describen tramos distintos:
> la de esta sección caracteriza el modelo, la de P-09 caracteriza el servicio.

### Uso de GPU durante la inferencia

| Métrica | Valor |
|---|---|
| Utilización de GPU | 97 % |
| VRAM en uso | 2 543 MiB de 6 144 MiB (incluye el escritorio) |

## Entorno de ejecución

| Componente | Versión / valor |
|---|---|
| Sistema operativo | Arch Linux (EndeavourOS), kernel 7.1.8-arch1-3 |
| CPU / RAM | x86_64, 31 GiB |
| GPU | NVIDIA GeForce GTX 1060 6GB (Pascal, compute capability 6.1) |
| Driver NVIDIA | 580.178.04 |
| Ollama | 0.32.15 |
| Backend de inferencia | **Vulkan** |
| Docker | 29.7.2 |
| Docker Compose | 5.5.0 |
| Git | 2.55.0 |
| Python | 3.14.7 |

### Nota sobre la adaptación a Arch Linux

La guía está escrita para Ubuntu con el gestor de paquetes `apt`. Este equipo usa
Arch Linux, por lo que `setup.sh` se reescribió con `pacman`. Las diferencias
relevantes son:

- Docker está en el repositorio oficial de Arch: no hay que registrar la llave GPG
  ni agregar el repositorio de Docker. Los plugins v2 son los paquetes
  `docker-compose` y `docker-buildx`.
- En Arch, `python` ya es Python 3 e incluye `venv`; no existe `python3-venv`.
- Ollama se instala desde el repositorio oficial (`pacman -S ollama`) en lugar del
  script `install.sh` del sitio web.

### Elección del backend de aceleración

El paquete `ollama-cuda` de Arch está compilado contra CUDA 13, que eliminó el
soporte para la arquitectura Pascal. Con la GTX 1060 (compute capability 6.1) el
servicio registraba:

```
skipping CUDA device — compute capability not in compiled architectures
  device="NVIDIA GeForce GTX 1060 6GB" cc=610 archs="[750 800 860 ...]"
inference compute: id=cpu library=cpu
```

es decir, caía a CPU. Se sustituyó por `ollama-vulkan`, que sí soporta Pascal, y el
servicio pasó a reconocer la GPU:

```
inference compute: id=0 library=Vulkan name=Vulkan0
  description="NVIDIA GeForce GTX 1060 6GB" type=discrete total="6.2 GiB"
```

Por eso `setup.sh` selecciona el backend según la *compute capability* reportada por
`nvidia-smi`: `ollama-cuda` desde 7.5 en adelante, `ollama-vulkan` por debajo.

## Plan de pruebas del despliegue (Semana 4 · AA4)

Las pruebas se ejecutaron el 2026-08-25 sobre la solución levantada con
`docker compose up -d`, contra la imagen `api-ia:1.0.0` y `postgres:16-alpine`.

| ID | Tipo | Qué se verifica | Resultado esperado | Obtenido | Estado |
|---|---|---|---|---|---|
| P-01 | Funcional | `GET /health` responde | Código 200 y estado `ok` | `200` · `{"estado":"ok","base_datos":"ok"}` | ✅ |
| P-02 | Funcional | `POST /clasificar` con motor `eco` | Código 200 y tipo correcto | `200` · `"corrige el error de login"` → `fix` | ✅ |
| P-03 | Funcional | Motor inválido | Código 400 | `400` · `{"detail":"motor debe ser eco u ollama"}` | ✅ |
| P-04 | Acceso | Rol `app_ia` intenta `DROP TABLE` | Error de permisos | `ERROR: must be owner of table inferencias` | ✅ |
| P-05 | Conectividad | La API resuelve el host `db` | Devuelve una IP interna | `db → 172.22.0.2` | ✅ |
| P-06 | Disponibilidad | Reinicio del contenedor de BD | La API se recupera sola | `503` → `200` en **1 s**, sin intervención | ✅ |
| P-07 | Persistencia | `down` y `up` conservan los datos | Los registros siguen existiendo | 64 → 64 registros, mismos `id` y fechas | ✅ |
| P-08 | Carga | 10 usuarios sobre el motor `eco` | p95 < 800 ms y errores < 5 % | p95 **11,7 ms** · **0,00 %** · 657 peticiones | ✅ |
| P-09 | Caracterización | 10 inferencias con modelo | Promedio, mediana y p95 | prom. 151 ms · mediana **116 ms** · p95 122 ms | ✅ |

### Detalle de P-04 · privilegios del rol de aplicación

El rol `app_ia` recibe en `db/init.sql` únicamente `SELECT, INSERT` sobre
`inferencias`. Se comprobaron cinco operaciones; las de escritura destructiva se
lanzaron dentro de una transacción con `ROLLBACK` para no perder los registros
existentes en caso de que la configuración estuviera mal.

| Operación | Resultado | Bloqueada por |
|---|---|---|
| `SELECT` | `count = 64` | — (permitida) |
| `INSERT` | `INSERT 0 1` | — (permitida, la API la necesita) |
| `DELETE` | `ERROR: permission denied for table inferencias` | ausencia de `GRANT` |
| `UPDATE` | `ERROR: permission denied for table inferencias` | ausencia de `GRANT` |
| `DROP TABLE` | `ERROR: must be owner of table inferencias` | propiedad de la tabla |

La diferencia entre los dos mensajes de error es relevante: `DELETE` y `UPDATE` los
bloquea el sistema de privilegios, mientras que `DROP` lo bloquea la propiedad de la
tabla —la creó `postgres`—, de modo que `app_ia` no podría eliminarla ni aunque se
le concedieran todos los privilegios. Son dos capas independientes de defensa.

### Detalle de P-08 · prueba de carga sobre el servicio

Ejecutada con k6 (`tests/carga/prueba_carga.js`): rampa de 30 s hasta 5 usuarios
virtuales, 1 minuto sosteniendo 10 y 30 s de descenso, contra el motor `eco`.

| Métrica | Umbral | Obtenido |
|---|---|---|
| `http_req_duration` p(95) | < 800 ms | **11,7 ms** |
| `http_req_failed` | < 5 % | **0,00 %** (0 de 657) |
| Checks superados | — | 1 314 de 1 314 |
| Throughput | — | 5,46 peticiones/s |
| `http_req_duration` media / mín / máx | — | 10,4 ms / 6,8 ms / 15,9 ms |

Consumo de recursos medido con `docker stats` durante la prueba:

| Contenedor | CPU (pico) | Memoria |
|---|---|---|
| `api-ia` | 3,98 % | 48 MiB |
| `db-ia` | 6,04 % | 15 MiB |

La prueba **no encontró el techo del servicio**: ningún recurso se acercó a
saturarse. El resultado acota el rendimiento por abajo, no lo agota.

### Detalle de P-09 · caracterización de la latencia del modelo

Ejecutada con `tests/carga/caracterizar_modelo.py`: 10 mensajes distintos, de forma
secuencial, contra el motor `ollama`. El modelo no se somete a concurrencia porque
Ollama serializa las peticiones.

| Métrica | Valor |
|---|---|
| Arranque en frío (incluye carga a VRAM) | **3 796 ms** |
| Primera petición en caliente | 467 ms |
| Promedio de las 10 mediciones | 151 ms |
| **Mediana** | **116 ms** |
| p95 | 122 ms |
| Mínimo / máximo | 110 ms / 467 ms |

`ollama ps` durante la prueba reporta `100% GPU` con contexto 2 048: el modelo de
1,1 GB cabe entero en los 6 GiB de VRAM y no hay descarga parcial a CPU.

La mediana (116 ms) describe mejor el comportamiento en régimen que el promedio
(151 ms), que arrastra la primera petición en caliente. Aun así, el resultado queda
unas **9 veces por debajo** de la latencia de 1 a 3 segundos que el Anexo A espera
del perfil A.

### Precisión comparada de los dos motores

Sobre los mismos 10 mensajes de P-09 se comparó la salida de ambos motores contra la
categoría esperada:

| Motor | Latencia mediana | Aciertos |
|---|---|---|
| `eco` (reglas) | < 1 ms | **10 / 10** |
| `ollama` (`qwen2.5-coder:1.5b`) | 116 ms | **8 / 10** |

El modelo falló en dos casos, ambos hacia la misma categoría: clasificó *"actualiza
las dependencias del proyecto"* como `refactor` en lugar de `chore`, e *"implementa
el healthcheck del contenedor"* como `refactor` en lugar de `feat`.

Este resultado debe leerse con una salvedad: los diez mensajes propuestos por la
guía contienen justamente las raíces verbales que el motor `eco` busca
(`actualiz`, `implement`, `renombr`, `simplific`), por lo que el conjunto de prueba
favorece a las reglas por construcción y no demuestra que generalicen mejor ante
mensajes redactados libremente. Lo que sí queda establecido es que, **en este
conjunto, el modelo cuesta 116 ms adicionales sin mejorar la precisión**.

### Análisis del cuello de botella

La comparación entre P-08 y P-09 permite descomponer el tiempo de una petición:

| Tramo | Tiempo | Cómo se obtiene |
|---|---|---|
| Clasificación por reglas | < 1 ms | La API registra `latencia_ms = 0` para las 719 filas del motor `eco` |
| Serialización HTTP + `INSERT` en PostgreSQL | ≈ 11 ms | p95 de P-08 (11,7 ms) menos el tramo anterior |
| Inferencia del modelo | ≈ 105 ms | Mediana de P-09 (116 ms) menos el p95 de P-08 |

El tiempo se pierde **en la inferencia**, no en la API ni en la base de datos: ese
único tramo vale unas diez veces todo el resto del recorrido sumado. La base de
datos y el servicio web son, en comparación, prácticamente gratuitos.

Igual de relevante es lo que **no** es el cuello de botella. Con 10 usuarios
concurrentes la CPU no pasó del 6 % y la memoria de ambos contenedores sumó 63 MiB
sobre 31 GiB disponibles; no hubo un solo error en 657 peticiones. El límite del
sistema no es de capacidad —CPU, memoria o conexiones—, sino de **latencia del
modelo**.

Esa distinción determina cómo escala la solución. El motor `eco` es concurrente: la
API atiende varias peticiones a la vez y PostgreSQL admite hasta las 20 conexiones
configuradas en `docker-compose.yml`. El motor `ollama`, en cambio, **serializa**:
Ollama procesa una inferencia a la vez, de modo que la latencia no se diluye
repartiendo peticiones entre usuarios, sino que se acumula en cola. A 5,46
peticiones por segundo —el ritmo que sostuvo P-08— el motor `eco` ni se inmutó,
mientras que el motor `ollama`, a 116 ms por inferencia, satura en torno a 8,6
peticiones por segundo y a partir de ahí la cola crece sin límite.

### Propuestas de mejora

**1. Usar `eco` como filtro previo del modelo.** Las reglas resolvieron 10 de 10
casos en menos de 1 ms, frente a 8 de 10 en 116 ms del modelo. La versión actual
elige un motor u otro para toda la petición; bastaría con encadenarlos: aplicar
primero el regex y llamar al modelo **solo cuando ningún patrón coincida**. Hoy esos
mensajes caen a `chore` por defecto (`app/main.py`, última línea de
`clasificar_eco`), que es precisamente el caso ambiguo donde el modelo aporta. El
efecto sobre la latencia media es directo: la mayoría de las peticiones dejaría de
pagar los 105 ms de inferencia.

**2. Mantener el modelo cargado en memoria (`OLLAMA_KEEP_ALIVE`).** El arranque en
frío costó 3 796 ms frente a los 116 ms en caliente: un factor de **33**. Con 31 GiB
de RAM y el modelo ocupando 1,1 GB de VRAM, este equipo (perfil A) puede permitirse
mantenerlo residente. En los perfiles B y C la guía recomienda lo contrario
(`OLLAMA_KEEP_ALIVE=0`) porque allí la memoria es el recurso escaso: es una decisión
que depende del hardware, no una mejora universal.

**3. Registrar la latencia con precisión sub-milisegundo.** La columna
`latencia_ms` está declarada como `INTEGER` en `db/init.sql`, de modo que trunca a
`0` todo lo que dure menos de un milisegundo. Las 719 filas del motor `eco`
registran `0 ms`, lo que hace ese motor **inmedible desde la propia base de datos**
y obliga a inferir su coste por diferencia con k6, como se hizo en el análisis
anterior. Cambiar la columna a `NUMERIC(10,3)` —o almacenar microsegundos— permitiría
sostener el análisis del cuello de botella con datos propios del sistema en lugar de
una herramienta externa.
