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
Depends: python3 (>= 3.9), python3-venv, python3-pip, ffmpeg
Maintainer: ${maintainer}
Description: ${description}
EOF

install -m 0644 "${script_dir}/deb/tonefinish.desktop" \
  "${pkg_dir}/usr/share/applications/tonefinish.desktop"

install -m 0644 "${root_dir}/assets/tonefinish.svg" \
  "${pkg_dir}/usr/share/icons/hicolor/scalable/apps/tonefinish.svg"

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

for file in audio_analysis.py audio_processing.py audio_tools.py config.py ui_app.py main.py normalize_audio.py; do
  install -m 0644 "${root_dir}/${file}" "${pkg_dir}/usr/lib/${package_name}/${file}"
done

mkdir -p "${build_root}"
dpkg-deb --root-owner-group --build "${pkg_dir}" "${build_root}/${package_name}_${version}.deb"

echo "Paquete creado: ${build_root}/${package_name}_${version}.deb"
