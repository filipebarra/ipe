#!/usr/bin/env bash
# Ipê installation on Linux (Ubuntu/Fedora). Needs glibc >= 2.34 (Ubuntu 22.04+), python3 >= 3.10 and python3-venv.
# Instalação no Linux · Instalación en Linux
set -e
cd "$(dirname "$0")"
echo "=== Ipê: installation ==="
echo "Language / Idioma:  1) English (default)   2) Português (Brasil)   3) Español"
LANG_IPE=en
if [ -t 0 ]; then
  read -r -p "[1] " op || op=""
  case "$op" in
    2) LANG_IPE=pt-BR ;;
    3) LANG_IPE=es ;;
    *) LANG_IPE=en ;;
  esac
fi
msg() {  # msg "english" "português" "español"
  case "$LANG_IPE" in pt-BR) echo "$2" ;; es) echo "$3" ;; *) echo "$1" ;; esac
}

# 0.99.85: the Qt used by Ipê (PySide6 6.11) only has Linux packages for glibc 2.34 or newer
GLIBC=$(ldd --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+$' || echo "0.0")
if [ "$(printf '%s\n2.34\n' "$GLIBC" | sort -V | head -1)" != "2.34" ]; then
  msg "This Linux is too old (glibc $GLIBC). Ipê needs glibc 2.34 or newer: Ubuntu 22.04, Debian 12, Fedora 35 or later." \
      "Este Linux é antigo demais (glibc $GLIBC). O Ipê precisa da glibc 2.34 ou mais nova: Ubuntu 22.04, Debian 12, Fedora 35 ou depois." \
      "Este Linux es demasiado antiguo (glibc $GLIBC). Ipê necesita glibc 2.34 o más nueva: Ubuntu 22.04, Debian 12, Fedora 35 o posterior."
  exit 1
fi

# 0.99.85: a Python 3.10+ from the system — not the one from Anaconda/conda, which is often older and comes first in PATH
PY=""
if [ -x .venv/bin/python ] && .venv/bin/python -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
  PY=.venv/bin/python
else
  rm -rf .venv
  for c in /usr/bin/python3.13 /usr/bin/python3.12 /usr/bin/python3.11 /usr/bin/python3.10 /usr/bin/python3 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
      PY="$c"; break
    fi
  done
  if [ -z "$PY" ]; then
    msg "Python 3.10 or newer was not found. On Ubuntu: sudo apt install python3 python3-venv" \
        "Não achei o Python 3.10 ou mais novo. No Ubuntu: sudo apt install python3 python3-venv" \
        "No encontré Python 3.10 o más nuevo. En Ubuntu: sudo apt install python3 python3-venv"
    exit 1
  fi
  if ! "$PY" -m venv .venv; then
    msg "Could not create the environment. On Ubuntu: sudo apt install python3-venv" \
        "Não deu para criar o ambiente. No Ubuntu: sudo apt install python3-venv" \
        "No se pudo crear el entorno. En Ubuntu: sudo apt install python3-venv"
    exit 1
  fi
fi
msg "Python: $(.venv/bin/python --version)" "Python: $(.venv/bin/python --version)" "Python: $(.venv/bin/python --version)"

# 0.99.85: libraries the Qt window needs (Qt 6.5+ asks for libxcb-cursor0, which Ubuntu does not install by default)
if command -v dpkg >/dev/null 2>&1; then
  FALTAM=""
  for p in libxcb-cursor0 libxcb-xinerama0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 libxcb-render-util0 libxcb-image0 libegl1; do
    dpkg -s "$p" >/dev/null 2>&1 || FALTAM="$FALTAM $p"
  done
  if [ -n "$FALTAM" ]; then
    msg "Installing libraries for the window:$FALTAM" "Instalando bibliotecas da janela:$FALTAM" "Instalando bibliotecas de la ventana:$FALTAM"
    sudo apt-get install -y $FALTAM || msg "Install them by hand: sudo apt install$FALTAM" \
      "Instale à mão: sudo apt install$FALTAM" "Instálelas a mano: sudo apt install$FALTAM"
  fi
elif command -v rpm >/dev/null 2>&1; then
  rpm -q xcb-util-cursor >/dev/null 2>&1 || sudo dnf install -y xcb-util-cursor || true
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m ipe set-language "$LANG_IPE"
.venv/bin/python -m ipe register-url || true
msg "Installation complete. Run ./executar.sh" "Instalação concluída. Use ./executar.sh" "Instalación terminada. Use ./executar.sh"
