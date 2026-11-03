#!/usr/bin/env bash
# Ipê installation on Linux (Ubuntu/Fedora). Needs python3 >= 3.10 and python3-venv.
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
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m ipe set-language "$LANG_IPE"
.venv/bin/python -m ipe register-url || true
case "$LANG_IPE" in
  pt-BR) echo "Instalação concluída. Use ./executar.sh" ;;
  es) echo "Instalación terminada. Use ./executar.sh" ;;
  *) echo "Installation complete. Run ./executar.sh" ;;
esac
