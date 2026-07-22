#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root_dir="$(cd "${script_dir}/.." && pwd)"

package_name="tonefinish"
version_file="${root_dir}/VERSION"
version="0.0.0"
if [[ -f "${version_file}" ]]; then
  version="$(cat "${version_file}")"
fi

source_tar_name="${package_name}-${version}.tar.gz"

create_source_tarball() {
  local dest_dir="$1"
  mkdir -p "${dest_dir}"
  local dest="${dest_dir}/${source_tar_name}"
  tar \
    --exclude=".venv" \
    --exclude=".flatpak-builder" \
    --exclude=".codex" \
    --exclude="__pycache__" \
    --exclude="releases" \
    --exclude="packaging/build_*" \
    --exclude="packaging/appimage/AppDir" \
    --exclude=".git" \
    --exclude="*.wav" \
    -czf "${dest}" \
    -C "${root_dir}" \
    --transform "s,^,${package_name}-${version}/," \
    .
  echo "${dest}"
}

deps_deb=(dpkg-deb)
deps_rpm=(rpmbuild)
deps_pacman=(makepkg)
deps_snap=(snapcraft)
deps_flatpak=(flatpak-builder)
deps_appimage=(appimagetool)

missing_tools=()

tool_to_pkg_apt() {
  case "$1" in
    rpmbuild) echo "rpm" ;;
    snapcraft) echo "" ;;
    flatpak-builder) echo "flatpak-builder" ;;
    appimagetool) echo "" ;;
    makepkg) echo "" ;;
    dpkg-deb) echo "dpkg" ;;
    *) echo "" ;;
  esac
}

has_tool() {
  local cmd="$1"
  if command -v "${cmd}" >/dev/null 2>&1; then
    return 0
  fi
  if [[ "${cmd}" == "appimagetool" ]]; then
    if [[ -x "${script_dir}/appimage/appimagetool" ]]; then
      return 0
    fi
  fi
  return 1
}

check_deps() {
  local name="$1"; shift
  local missing=()
  for cmd in "$@"; do
    if ! has_tool "$cmd"; then
      missing+=("$cmd")
      missing_tools+=("$cmd")
    fi
  done
  if [[ "${#missing[@]}" -gt 0 ]]; then
    printf "%s: faltan %s\n" "$name" "${missing[*]}"
    return 1
  fi
  printf "%s: OK\n" "$name"
  return 0
}

show_info() {
  echo "Paquete: ${package_name}"
  echo "Version: ${version}"
  echo "Ruta: ${root_dir}"
  echo "Salida: ${root_dir}/releases"
}

build_deb() {
  mkdir -p "${root_dir}/releases"
  "${script_dir}/build_deb.sh"
}

build_rpm() {
  if ! check_deps "RPM" "${deps_rpm[@]}"; then
    return 0
  fi
  local spec="${script_dir}/rpm/${package_name}.spec"
  if [[ ! -f "${spec}" ]]; then
    echo "RPM: falta ${spec}"
    return 0
  fi
  local rpm_root="${script_dir}/build_rpm"
  rm -rf "${rpm_root}"
  mkdir -p "${rpm_root}"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
  cp -f "${spec}" "${rpm_root}/SPECS/${package_name}.spec"
  sed -i -E "s/^Version:[[:space:]]+.*/Version:        ${version}/" \
    "${rpm_root}/SPECS/${package_name}.spec"
  create_source_tarball "${rpm_root}/SOURCES" >/dev/null
  rpmbuild -bb "${rpm_root}/SPECS/${package_name}.spec" --define "_topdir ${rpm_root}"
  find "${rpm_root}/RPMS" -type f -name "*.rpm" ! -name "*-debuginfo-*" \
    -exec cp -f {} "${root_dir}/releases/" \;
  echo "RPM: listo"
}

build_pacman() {
  if ! check_deps "Pacman" "${deps_pacman[@]}"; then
    return 0
  fi
  local pkgbuild_dir="${script_dir}/arch"
  if [[ ! -f "${pkgbuild_dir}/PKGBUILD" ]]; then
    echo "Pacman: falta ${pkgbuild_dir}/PKGBUILD"
    return 0
  fi
  create_source_tarball "${pkgbuild_dir}" >/dev/null
  (cd "${pkgbuild_dir}" && makepkg -f --noconfirm)
  find "${pkgbuild_dir}" -maxdepth 1 -type f -name "*.pkg.tar.zst" -exec cp -f {} "${root_dir}/releases/" \;
  echo "Pacman: listo"
}

build_snap() {
  if ! check_deps "Snap" "${deps_snap[@]}"; then
    return 0
  fi
  local snap_dir="${script_dir}/snap"
  if [[ ! -f "${snap_dir}/snapcraft.yaml" ]]; then
    echo "Snap: falta ${snap_dir}/snapcraft.yaml"
    return 0
  fi
  (cd "${snap_dir}" && snapcraft)
  find "${snap_dir}" -maxdepth 1 -type f -name "*.snap" -exec cp -f {} "${root_dir}/releases/" \;
  echo "Snap: listo"
}

build_flatpak() {
  if ! check_deps "Flatpak" "${deps_flatpak[@]}"; then
    return 0
  fi
  local manifest="${script_dir}/flatpak/com.sabe.ToneFinish.json"
  if [[ ! -f "${manifest}" ]]; then
    echo "Flatpak: falta ${manifest}"
    return 0
  fi
  local wheels_dir="${script_dir}/flatpak/wheels"
  if ! ls "${wheels_dir}"/*.whl >/dev/null 2>&1; then
    echo "Flatpak: faltan wheels en ${wheels_dir}"
    echo "Usa: ${script_dir}/flatpak/download_wheels.sh"
    return 0
  fi
  local build_dir="${script_dir}/build_flatpak"
  local repo_dir="${script_dir}/build_flatpak_repo"
  rm -rf "${build_dir}" "${repo_dir}"
  flatpak-builder --force-clean --repo="${repo_dir}" "${build_dir}" "${manifest}"
  flatpak build-bundle "${repo_dir}" "${root_dir}/releases/${package_name}_${version}.flatpak" com.sabe.ToneFinish
  echo "Flatpak: listo"
}

ensure_appimagetool() {
  if command -v appimagetool >/dev/null 2>&1; then
    command -v appimagetool
    return 0
  fi
  local tool="${script_dir}/appimage/appimagetool"
  if [[ -x "${tool}" ]]; then
    echo "${tool}"
    return 0
  fi
  local url="https://github.com/AppImage/AppImageKit/releases/latest/download/appimagetool-x86_64.AppImage"
  mkdir -p "$(dirname "${tool}")"
  echo "Descargando appimagetool..."
  if command -v curl >/dev/null 2>&1; then
    curl -L -o "${tool}" "${url}"
  elif command -v wget >/dev/null 2>&1; then
    wget -O "${tool}" "${url}"
  else
    echo "No se encontro curl ni wget para descargar appimagetool."
    return 1
  fi
  chmod 0755 "${tool}"
  echo "${tool}"
}

build_appimage() {
  local appimagetool_bin
  if ! appimagetool_bin="$(ensure_appimagetool)"; then
    echo "AppImage: no se pudo obtener appimagetool."
    return 0
  fi
  local appdir="${script_dir}/appimage/AppDir"
  rm -rf "${appdir}"
  mkdir -p "${appdir}/usr/bin" "${appdir}/usr/lib/${package_name}" "${appdir}/usr/share/icons/hicolor/scalable/apps"
  install -m 0644 "${root_dir}/assets/tonefinish.svg" "${appdir}/tonefinish.svg"
  install -m 0644 "${script_dir}/deb/tonefinish.desktop" "${appdir}/tonefinish.desktop"
  for file in audio_analysis.py audio_processing.py audio_tools.py resource_monitor.py config.py ui_app.py main.py requirements.txt VERSION README.md; do
    install -m 0644 "${root_dir}/${file}" "${appdir}/usr/lib/${package_name}/${file}"
  done
  cp -a "${root_dir}/ui" "${appdir}/usr/lib/${package_name}/"
  cat > "${appdir}/AppRun" <<'EOF'
#!/usr/bin/env bash
set -e
APPDIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="${HOME}/.tonefinish/appimage-venv"
if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
  "${VENV_DIR}/bin/pip" install -r "${APPDIR}/usr/lib/tonefinish/requirements.txt"
fi
exec "${VENV_DIR}/bin/python" "${APPDIR}/usr/lib/tonefinish/main.py"
EOF
  chmod 0755 "${appdir}/AppRun"
  cat > "${appdir}/usr/bin/tonefinish" <<'EOF'
#!/usr/bin/env bash
exec "$(dirname "$(readlink -f "$0")")/../../AppRun"
EOF
  chmod 0755 "${appdir}/usr/bin/tonefinish"
  "${appimagetool_bin}" "${appdir}" "${root_dir}/releases/${package_name}_${version}.AppImage"
  echo "AppImage: listo"
}

check_all() {
  missing_tools=()
  check_deps "DEB" "${deps_deb[@]}" || true
  check_deps "RPM" "${deps_rpm[@]}" || true
  check_deps "Pacman" "${deps_pacman[@]}" || true
  check_deps "Snap" "${deps_snap[@]}" || true
  check_deps "Flatpak" "${deps_flatpak[@]}" || true
  check_deps "AppImage" "${deps_appimage[@]}" || true
  if [[ "${#missing_tools[@]}" -gt 0 ]]; then
    echo ""
    echo "Dependencias faltantes: ${missing_tools[*]}"
    offer_install
  fi
}

build_all() {
  build_deb
  build_rpm
  build_pacman
  build_snap
  build_flatpak
  build_appimage
}

offer_install() {
  if command -v apt >/dev/null 2>&1; then
    local pkgs=()
    local notes=()
    for tool in "${missing_tools[@]}"; do
      pkg="$(tool_to_pkg_apt "$tool")"
      if [[ -n "$pkg" ]]; then
        pkgs+=("$pkg")
      else
        if [[ "$tool" == "snapcraft" ]]; then
          notes+=("snapcraft -> snap install snapcraft")
        elif [[ "$tool" == "makepkg" ]]; then
          notes+=("makepkg -> Arch/Manjaro")
        elif [[ "$tool" == "appimagetool" ]]; then
          notes+=("appimagetool -> descarga desde AppImageKit")
        fi
      fi
    done
    if [[ "${#pkgs[@]}" -gt 0 ]]; then
      echo "En Debian/Ubuntu puedes instalar con:"
      echo "  sudo apt update && sudo apt install ${pkgs[*]}"
      read -r -p "¿Instalar ahora? [y/N] " answer
      if [[ "${answer:-N}" =~ ^[Yy]$ ]]; then
        sudo apt update
        sudo apt install "${pkgs[@]}"
      fi
    else
      echo "No hay paquetes instalables por apt para las herramientas faltantes."
    fi
    if [[ "${#notes[@]}" -gt 0 ]]; then
      echo ""
      echo "Notas:"
      for note in "${notes[@]}"; do
        echo "  - ${note}"
      done
    fi
  else
    echo "No se detecto apt. Instala manualmente:"
    echo "  - rpm (rpmbuild)"
    echo "  - snapcraft"
    echo "  - flatpak-builder"
    echo "  - appimagetool"
  fi
}

menu() {
  echo "=== ToneFinish Builder ==="
  echo "1) Chequear dependencias"
  echo "2) Ver datos del paquete"
  echo "3) Construir paquetes"
  echo "4) Instalar dependencias faltantes"
  echo "5) Salir"
  read -r -p "Selecciona una opcion: " choice
  case "$choice" in
    1) check_all ;;
    2) show_info ;;
    3) build_all ;;
    4) check_all ;;
    5) exit 0 ;;
    *) echo "Opcion invalida" ;;
  esac
}

if [[ "${1:-}" == "--check" ]]; then
  check_all
  exit 0
fi
if [[ "${1:-}" == "--info" ]]; then
  show_info
  exit 0
fi
if [[ "${1:-}" == "--build" ]]; then
  build_all
  exit 0
fi
if [[ "${1:-}" == "--build-rpm" ]]; then
  build_rpm
  exit 0
fi
if [[ "${1:-}" == "--build-flatpak" ]]; then
  build_flatpak
  exit 0
fi

while true; do
  menu
  echo ""
done
