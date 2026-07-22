#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root_dir="$(cd "${script_dir}/.." && pwd)"

version_file="${root_dir}/VERSION"
version="0.1.0"
if [[ -f "${version_file}" ]]; then
  version="$(cat "${version_file}")"
fi

package_name="tonefinish"
build_root="${root_dir}/releases"
pkg_dir="${build_root}/${package_name}_${version}"
maintainer="${DEB_MAINTAINER:-Martin <martin@local>}"
description="${DEB_DESCRIPTION:-Audio finisher con analisis y normalizacion}"

rm -rf "${pkg_dir}"
mkdir -p "${pkg_dir}/DEBIAN"
mkdir -p "${pkg_dir}/usr/bin"
mkdir -p "${pkg_dir}/usr/lib/${package_name}"
mkdir -p "${pkg_dir}/usr/share/applications"
mkdir -p "${pkg_dir}/usr/share/icons/hicolor/scalable/apps"

cat > "${pkg_dir}/DEBIAN/control" <<EOF
Package: ${package_name}
Version: ${version}
Section: sound
Priority: optional
Architecture: all
Depends: python3 (>= 3.9), python3-venv, python3-pip, ffmpeg, spasm (>= 0.2.10), spasm-skill-ffmpeg-subset (>= 0.2.10)
Maintainer: ${maintainer}
Description: ${description}
EOF

install -m 0644 "${script_dir}/deb/tonefinish.desktop" \
  "${pkg_dir}/usr/share/applications/tonefinish.desktop"

install -m 0644 "${root_dir}/assets/tonefinish.svg" \
  "${pkg_dir}/usr/share/icons/hicolor/scalable/apps/tonefinish.svg"

icon_sizes=(16 32 48 64 128 256 512)
svg_src="${root_dir}/assets/tonefinish.svg"
for size in "${icon_sizes[@]}"; do
  out_dir="${pkg_dir}/usr/share/icons/hicolor/${size}x${size}/apps"
  mkdir -p "${out_dir}"
  if command -v rsvg-convert >/dev/null 2>&1; then
    rsvg-convert -w "${size}" -h "${size}" "${svg_src}" -o "${out_dir}/tonefinish.png"
  elif command -v convert >/dev/null 2>&1; then
    convert "${svg_src}" -resize "${size}x${size}" "${out_dir}/tonefinish.png"
  fi
done

cat > "${pkg_dir}/DEBIAN/postinst" <<'EOF'
#!/usr/bin/env bash
set -e

APP_DIR="/usr/lib/tonefinish"
VENV_DIR="${APP_DIR}/.venv"

if [ ! -d "${VENV_DIR}" ]; then
  python3 -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/pip" install --upgrade pip >/dev/null 2>&1 || true
"${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt"

exit 0
EOF
chmod 0755 "${pkg_dir}/DEBIAN/postinst"

cat > "${pkg_dir}/usr/bin/tonefinish" <<'EOF'
#!/usr/bin/env python3
import os
import sys

BASE_DIR = "/usr/lib/tonefinish"
VENV_PY = os.path.join(BASE_DIR, ".venv", "bin", "python")
if os.path.exists(VENV_PY):
    os.execv(VENV_PY, [VENV_PY, os.path.join(BASE_DIR, "main.py")])
sys.path.insert(0, BASE_DIR)

from main import main

if __name__ == "__main__":
    raise SystemExit(main())
EOF
chmod 0755 "${pkg_dir}/usr/bin/tonefinish"

install -m 0644 "${root_dir}/README.md" "${pkg_dir}/usr/lib/${package_name}/README.md"
install -m 0644 "${root_dir}/VERSION" "${pkg_dir}/usr/lib/${package_name}/VERSION"
install -m 0644 "${root_dir}/requirements.txt" "${pkg_dir}/usr/lib/${package_name}/requirements.txt"
install -m 0644 "${root_dir}/requirements-lock.txt" "${pkg_dir}/usr/lib/${package_name}/requirements-lock.txt"
install -m 0644 "${root_dir}/runtime_lock.json" "${pkg_dir}/usr/lib/${package_name}/runtime_lock.json"

py_files=(
  logic_backend.py
  audio_analysis.py
  audio_processing.py
  audio_tools.py
  analysis_mts.py
  compute_backend.py
  resource_governor.py
  resource_monitor.py
  audio_preview.py
  spectrum_analyzer.py
  auto_master_intelligence.py
  event_detection.py
  section_detection.py
  master_decision_engine.py
  adaptive_master_shadow.py
  adaptive_master_renderer.py
  adaptive_rollout_safety.py
  adaptive_rollout_phase8.py
  alternative_tools.py
  diagnostics.py
  cache.py
  config.py
  filter_graph_builder.py
  mastering_config.py
  ui_app.py
  main.py
  runtime_reproducibility.py
  bandcamp_bok.py
  ia_mastering.py
  output_naming.py
)

for file in "${py_files[@]}"; do
  install -m 0644 "${root_dir}/${file}" "${pkg_dir}/usr/lib/${package_name}/${file}"
done

# Copiar directorios completos
cp -a "${root_dir}/ui" "${pkg_dir}/usr/lib/${package_name}/"
cp -a "${root_dir}/processes" "${pkg_dir}/usr/lib/${package_name}/"
cp -a "${root_dir}/mastering_modules" "${pkg_dir}/usr/lib/${package_name}/"
cp -a "${root_dir}/assets" "${pkg_dir}/usr/lib/${package_name}/"
cp -a "${root_dir}/docs" "${pkg_dir}/usr/lib/${package_name}/"
cp -a "${root_dir}/scripts" "${pkg_dir}/usr/lib/${package_name}/"
cp -a "${root_dir}/spasm_cli" "${pkg_dir}/usr/lib/${package_name}/"

# Limpiar artefactos de desarrollo
find "${pkg_dir}/usr/lib/${package_name}" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "${pkg_dir}/usr/lib/${package_name}" -type f -name "*.pyc" -delete

mkdir -p "${build_root}"
deb_path="${build_root}/${package_name}_${version}.deb"
if command -v dpkg-deb >/dev/null 2>&1; then
  dpkg-deb --root-owner-group --build "${pkg_dir}" "${deb_path}"
else
  # Constructor Debian estándar para entornos mínimos sin dpkg-deb.
  deb_tmp="$(mktemp -d)"
  trap 'rm -rf "${deb_tmp}"' EXIT
  printf '2.0\n' > "${deb_tmp}/debian-binary"
  (
    cd "${pkg_dir}/DEBIAN"
    tar --owner=0 --group=0 -czf "${deb_tmp}/control.tar.gz" .
  )
  (
    cd "${pkg_dir}"
    tar --owner=0 --group=0 --exclude='./DEBIAN' -czf "${deb_tmp}/data.tar.gz" .
  )
  rm -f "${deb_path}"
  (
    cd "${deb_tmp}"
    ar r "${deb_path}" debian-binary control.tar.gz data.tar.gz >/dev/null
  )
fi

latest_link="${build_root}/${package_name}_latest.deb"
rm -f "${latest_link}"
ln -s "${package_name}_${version}.deb" "${latest_link}"

echo "Paquete creado: ${deb_path}"
echo "Enlace actualizado -> ${latest_link} -> ${package_name}_${version}.deb"
