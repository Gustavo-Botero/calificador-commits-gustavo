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
