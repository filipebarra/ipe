#!/usr/bin/env bash
# Linux: o mesmo do instalar_segmentacao.bat — ambiente próprio com PyTorch (CPU) e TotalSegmentator.
set -e
unset PYTHONHOME PYTHONPATH PYTHONSTARTUP VIRTUAL_ENV   # 0.99.69: variáveis de outro Python quebram o novo
BASE="${XDG_DATA_HOME:-$HOME/.local/share}/DicomViewer/segmentacao"
VENV="$BASE/venv"
export TOTALSEG_HOME_DIR="$BASE/pesos"
# 0.100.22: o TotalSegmentator e o PyTorch atuais pedem Python 3.10 ou mais novo. Em sistemas
# antigos (Ubuntu 20.04 traz o 3.8) o python3 não serve: procura outro e, se não houver, baixa
# um Python próprio com o uv (não mexe no Python do sistema).
case "${1:-${IPE_LANG:-${LANG:-pt}}}" in
  en*) M_PROCURA="Looking for Python 3.10 or newer..."; M_USA="Using"; M_BAIXA="No suitable Python found: downloading Python 3.12 (uv)..."
       M_VELHO="The existing environment uses an old Python: rebuilding it."
       M_FALTA="Could not get Python 3.10+. Install it (for example: conda create -n ipe python=3.12) and run again with: PYTHON=/path/to/python $0" ;;
  es*) M_PROCURA="Buscando Python 3.10 o más nuevo..."; M_USA="Usando"; M_BAIXA="No hay un Python adecuado: descargando Python 3.12 (uv)..."
       M_VELHO="El entorno existente usa un Python antiguo: se rehace."
       M_FALTA="No se pudo obtener Python 3.10+. Instálelo (por ejemplo: conda create -n ipe python=3.12) y ejecute de nuevo con: PYTHON=/ruta/al/python $0" ;;
  *)   M_PROCURA="Procurando Python 3.10 ou mais novo..."; M_USA="Usando"; M_BAIXA="Não há Python adequado: baixando o Python 3.12 (uv)..."
       M_VELHO="O ambiente existente usa um Python antigo: refazendo."
       M_FALTA="Não consegui um Python 3.10+. Instale um (por exemplo: conda create -n ipe python=3.12) e rode de novo com: PYTHON=/caminho/do/python $0" ;;
esac
serve() { "$1" -c 'import sys, venv, ensurepip; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)' >/dev/null 2>&1; }
if [ -x "$VENV/bin/python" ] && ! serve "$VENV/bin/python"; then
  echo "$M_VELHO"; rm -rf "$VENV"
fi
if [ ! -x "$VENV/bin/python" ]; then
  echo "$M_PROCURA"
  PY=""
  for c in "$PYTHON" python3.12 python3.11 python3.13 python3.10 python3 python; do
    [ -n "$c" ] || continue
    if command -v "$c" >/dev/null 2>&1 && serve "$c"; then PY="$c"; break; fi
  done
  if [ -n "$PY" ]; then
    echo "$M_USA $("$PY" --version 2>&1) ($(command -v "$PY"))"
    "$PY" -m venv "$VENV"
  else
    echo "$M_BAIXA"
    UV="$(command -v uv || true)"
    if [ -z "$UV" ]; then
      export UV_INSTALL_DIR="$BASE/uv" UV_NO_MODIFY_PATH=1
      if command -v curl >/dev/null 2>&1; then curl -LsSf https://astral.sh/uv/install.sh | sh
      elif command -v wget >/dev/null 2>&1; then wget -qO- https://astral.sh/uv/install.sh | sh
      fi || true
      UV="$BASE/uv/uv"
    fi
    if [ ! -x "$UV" ] || ! UV_PYTHON_INSTALL_DIR="$BASE/python" "$UV" venv --seed --python 3.12 "$VENV"; then
      echo "$M_FALTA" >&2; exit 1
    fi
  fi
fi
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
"$VENV/bin/python" -m pip install "TotalSegmentator>=2.18"
for t in total_fast total_fast_mr liver_segments liver_segments_mr vertebrae_mr vertebrae_body total_mr head_glands_cavities headneck_bones_vessels craniofacial_structures head_muscles headneck_muscles total lung_nodules trunk_cavities; do
  "$VENV/bin/totalseg_download_weights" -t "$t"
done
# SynthSeg pela DIPY (encéfalo: Evans, 3º ventrículo, ângulo calosal, hipocampos)
"$VENV/bin/python" -m pip install "dipy>=1.12"
DIPY_HOME="$BASE/pesos/dipy" "$VENV/bin/python" -c "from dipy.data import get_fnames; print(get_fnames(name='synthseg_torch_weights'))"
"$VENV/bin/python" -c "import torch, totalsegmentator, dipy; print('ok', torch.__version__, dipy.__version__)"
echo "Pronto: $BASE"
