#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

PYTHON_BIN=""
PYENV_PYTHON_VERSION="3.12.3"

echo "Usando pyenv para instalar/gestionar Python ${PYENV_PYTHON_VERSION}..."
sudo apt update
sudo apt install -y \
  make build-essential libssl-dev zlib1g-dev libbz2-dev \
  libreadline-dev libsqlite3-dev wget curl llvm \
  libncursesw5-dev xz-utils tk-dev libffi-dev liblzma-dev \
  python3-openssl git

export PYENV_ROOT="${HOME}/.pyenv"
if [ ! -d "${PYENV_ROOT}" ]; then
  git clone https://github.com/pyenv/pyenv.git "${PYENV_ROOT}"
fi
export PATH="${PYENV_ROOT}/bin:${PATH}"
eval "$(pyenv init -)"

pyenv install -s "${PYENV_PYTHON_VERSION}"
pyenv local "${PYENV_PYTHON_VERSION}"
PYTHON_BIN="${PYENV_ROOT}/versions/${PYENV_PYTHON_VERSION}/bin/python"

echo "Recreando .venv..."
rm -rf .venv
"$PYTHON_BIN" -m venv .venv

source .venv/bin/activate
pip install --upgrade pip

# PySide6 estable con Python 3.11/3.12
pip install "PySide6==6.7.2"

# Guardar dependencias
pip freeze > requirements.txt

echo "Listo. Ejecutando GUI..."
python main.py
