#!/bin/bash
# setup.sh - Aprovisionamiento del entorno del proyecto
# Adaptado de Ubuntu/apt (guia SENA) a Arch Linux/pacman.
# Es idempotente: si algo ya esta instalado, lo informa y sigue sin error.
set -euo pipefail

if ! command -v pacman &>/dev/null; then
  echo "ERROR: este script es para Arch Linux (pacman)." >&2
  echo "En Ubuntu/Debian use la version con apt de la guia." >&2
  exit 1
fi

echo ">>> Actualizando el sistema..."
sudo pacman -Syu --noconfirm --needed

echo ">>> Instalando utilidades base..."
# En Arch: python ya es Python 3 y trae venv incluido; no existe python3-venv.
sudo pacman -S --noconfirm --needed curl git ca-certificates nano python python-pip

echo ">>> Instalando Docker Engine..."
if ! command -v docker &>/dev/null; then
  # En Arch, Docker esta en el repo oficial: no hay que agregar llaves ni repos.
  # docker-compose y docker-buildx son los plugins v2 ("docker compose", "docker buildx").
  sudo pacman -S --noconfirm --needed docker docker-compose docker-buildx
else
  echo "Docker ya estaba instalado."
fi

echo ">>> Habilitando el servicio de Docker..."
if systemctl is-enabled --quiet docker; then
  echo "El servicio docker ya estaba habilitado."
else
  sudo systemctl enable --now docker
fi

echo ">>> Configurando el grupo docker..."
if id -nG "$USER" | grep -qw docker; then
  echo "El usuario $USER ya pertenece al grupo docker."
else
  sudo usermod -aG docker "$USER"
  echo "Usuario agregado al grupo docker: cierre sesion y vuelva a entrar."
fi

echo ">>> Instalando Ollama..."
sudo pacman -S --noconfirm --needed ollama

# El backend de aceleracion depende de la GPU:
#  - NVIDIA con compute capability >= 7.5 (Turing en adelante): ollama-cuda.
#    CUDA 13 elimino el soporte para Pascal (GTX 10xx, cc 6.x) y anteriores.
#  - NVIDIA Pascal o anterior: ollama-vulkan, que si funciona en esas tarjetas.
#  - AMD: ollama-rocm.  Sin GPU: solo ollama, que corre en CPU.
if command -v nvidia-smi &>/dev/null; then
  cc=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1 | tr -d '.')
  if [[ "${cc:-0}" -ge 75 ]]; then
    echo "GPU NVIDIA con compute capability ${cc:0:1}.${cc:1}: instalando ollama-cuda."
    sudo pacman -S --noconfirm --needed ollama-cuda
  else
    echo "GPU NVIDIA antigua (cc ${cc:0:1}.${cc:1}): CUDA 13 no la soporta, se usa Vulkan."
    sudo pacman -S --noconfirm --needed ollama-vulkan
  fi
else
  echo "Sin GPU NVIDIA: Ollama correra en CPU."
fi

echo ">>> Habilitando el servicio de Ollama..."
if systemctl is-enabled --quiet ollama; then
  echo "El servicio ollama ya estaba habilitado."
else
  sudo systemctl enable --now ollama
fi

echo ">>> Entorno listo. Cierre y reabra la terminal para usar docker sin sudo."
