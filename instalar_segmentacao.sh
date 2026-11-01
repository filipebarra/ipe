#!/usr/bin/env bash
# Linux: o mesmo do instalar_segmentacao.bat — ambiente próprio com PyTorch (CPU) e TotalSegmentator.
set -e
BASE="${XDG_DATA_HOME:-$HOME/.local/share}/DicomViewer/segmentacao"
VENV="$BASE/venv"
export TOTALSEG_HOME_DIR="$BASE/pesos"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
"$VENV/bin/python" -m pip install "TotalSegmentator>=2.18"
for t in total_fast total_fast_mr liver_segments liver_segments_mr vertebrae_mr vertebrae_body total_mr head_glands_cavities headneck_bones_vessels craniofacial_structures head_muscles headneck_muscles; do
  "$VENV/bin/totalseg_download_weights" -t "$t"
done
# SynthSeg pela DIPY (encéfalo: Evans, 3º ventrículo, ângulo calosal, hipocampos)
"$VENV/bin/python" -m pip install "dipy>=1.12"
DIPY_HOME="$BASE/pesos/dipy" "$VENV/bin/python" -c "from dipy.data import get_fnames; print(get_fnames(name='synthseg_torch_weights'))"
"$VENV/bin/python" -c "import torch, totalsegmentator, dipy; print('ok', torch.__version__, dipy.__version__)"
echo "Pronto: $BASE"
