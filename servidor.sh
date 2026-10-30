#!/usr/bin/env bash
cd "$(dirname "$0")"
# Servidor central sem janela. Na primeira vez: ./servidor.sh --create-admin admin
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
exec .venv/bin/python -m ipe server "$@"
