#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root_dir="$(cd "${script_dir}/../.." && pwd)"
wheels_dir="${script_dir}/wheels"

mkdir -p "${wheels_dir}"
# El runtime KDE 6.7 incluye CPython 3.11. Fijar plataforma/ABI evita
# descargar por accidente wheels incompatibles con la version Python del host.
python3 -m pip download \
  --only-binary=:all: \
  --implementation cp \
  --python-version 311 \
  --abi cp311 \
  --platform manylinux_2_34_x86_64 \
  --platform manylinux_2_28_x86_64 \
  --platform manylinux_2_27_x86_64 \
  --platform manylinux2014_x86_64 \
  --platform manylinux_2_17_x86_64 \
  -r "${root_dir}/requirements.txt" \
  -d "${wheels_dir}"
echo "Wheels descargados en ${wheels_dir}"
