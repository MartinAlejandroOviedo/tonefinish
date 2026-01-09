Name:           tonefinish
Version:        1.0.3
Release:        1%{?dist}
Summary:        Audio finisher con analisis y normalizacion (ToneFinish)

License:        Proprietary
URL:            https://github.com/MartinAlejandroOviedo/tonefinish
BuildArch:      noarch
Requires:       python3, ffmpeg
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

cp -a audio_analysis.py audio_processing.py audio_tools.py config.py ui_app.py main.py normalize_audio.py %{buildroot}/usr/lib/tonefinish/
cp -a requirements.txt VERSION README.md %{buildroot}/usr/lib/tonefinish/
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
