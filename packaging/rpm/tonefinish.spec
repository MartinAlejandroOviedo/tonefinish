Name:           tonefinish
Version:        4.2.1
Release:        1%{?dist}
Summary:        Audio finisher con analisis y normalizacion (ToneFinish)

License:        Proprietary
URL:            https://github.com/MartinAlejandroOviedo/tonefinish
BuildArch:      x86_64
Requires:       python3, ffmpeg, spasm >= 0.2.10, spasm-skill-ffmpeg-subset >= 0.2.10
Source0:        %{name}-%{version}.tar.gz

%description
ToneFinish es una aplicacion de audio para analizar, normalizar y finalizar audio.

%prep
%setup -q

%build

%install
mkdir -p %{buildroot}/usr/lib/tonefinish
mkdir -p %{buildroot}/usr/bin
mkdir -p %{buildroot}/usr/share/applications
mkdir -p %{buildroot}/usr/share/icons/hicolor/scalable/apps

find . -maxdepth 1 -type f -name '*.py' ! -name 'test_*.py' \
  -exec cp -a -t %{buildroot}/usr/lib/tonefinish/ {} +
cp -a ui processes mastering_modules assets docs scripts spasm_cli %{buildroot}/usr/lib/tonefinish/
cp -a requirements.txt requirements-lock.txt runtime_lock.json VERSION README.md %{buildroot}/usr/lib/tonefinish/
find %{buildroot}/usr/lib/tonefinish -type d -name __pycache__ -prune -exec rm -rf {} +
find %{buildroot}/usr/lib/tonefinish -type f -name '*.pyc' -delete
cp -a assets/tonefinish.svg %{buildroot}/usr/share/icons/hicolor/scalable/apps/tonefinish.svg
cp -a packaging/deb/tonefinish.desktop %{buildroot}/usr/share/applications/tonefinish.desktop

cat > %{buildroot}/usr/bin/tonefinish <<'EOF'
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
chmod 0755 %{buildroot}/usr/bin/tonefinish

%files
/usr/bin/tonefinish
/usr/lib/tonefinish
/usr/share/applications/tonefinish.desktop
/usr/share/icons/hicolor/scalable/apps/tonefinish.svg

%post
if [ ! -d /usr/lib/tonefinish/.venv ]; then
  python3 -m venv /usr/lib/tonefinish/.venv
fi
/usr/lib/tonefinish/.venv/bin/pip install -r /usr/lib/tonefinish/requirements.txt
