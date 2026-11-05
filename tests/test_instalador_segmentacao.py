"""0.99.69 — o instalador da segmentação no Windows não se deixa enganar por um Python quebrado."""
from pathlib import Path

BAT = Path(__file__).resolve().parents[1] / "instalar_segmentacao.bat"


def test_bat_limpa_o_ambiente_e_testa_o_python_de_verdade():
    t = BAT.read_bytes().decode("utf-8")
    assert "\r\n" in t                                       # o cmd do Windows quer CRLF
    for v in ("PYTHONHOME", "PYTHONPATH"):
        assert f'set "{v}="' in t
    assert t.index('set "PYTHONHOME="') < t.index("call :testa")
    assert "IPE_PY_OK" in t and "for /f" in t                # a resposta da sonda, não o código de saída
    assert ":apagar_venv" in t and "ren " in t               # ambiente preso: tira do caminho
    assert "totalseg_download_weights.exe\" (" in t or 'totalseg_download_weights.exe" (' in t


def test_bat_confere_o_pytorch_e_o_visual_cpp():
    t = BAT.read_bytes().decode("utf-8")
    assert t.index('-c "import torch"') < t.index("[2/3] TotalSegmentator")
    assert ":vcredist" in t and "vc_redist.x64.exe" in t and "/install /passive /norestart" in t
