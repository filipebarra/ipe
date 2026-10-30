#!/usr/bin/env bash
# Instalação no Linux (Ubuntu/Fedora). Requer python3 >= 3.10 e python3-venv.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m ipe register-url || true
echo "Instalação concluída. Use ./executar.sh"
