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


def test_visual_cpp_no_programa_e_no_instalador():
    from ipe.ui import segmentacao as SEG
    assert SEG.tem_visual_cpp("linux") is True
    iss = (BAT.parent / "installer" / "ipe.iss").read_bytes().decode("utf-8-sig")
    assert "TemVisualCpp" in iss and "AvisarVisualCpp();" in iss and SEG.URL_VCREDIST in iss
    for lang in ("english", "brazilianportuguese", "spanish"):
        assert f"{lang}.VcTexto=" in iss


def test_bat_no_idioma_do_ipe_e_sem_o_atalho_do_uv():
    """0.100.13: com o Ipê em inglês o instalador falava português; e o atalho de pasta que o uv cria para o
    Python 3.12 ("os error 448") quebrava o ambiente."""
    import re
    t = BAT.read_bytes().decode("utf-8")
    usadas = set(re.findall(r"!(M_[A-Z0-9_]+)!", t))
    for lang in ("pt", "en", "es"):
        bloco = t.split(f":textos_{lang}\r\n")[1].split("goto :eof")[0]
        assert set(re.findall(r'set "(M_[A-Z0-9_]+)=', bloco)) == usadas, lang
    assert "IPE_LANG" in t and "call :textos_%L%" in t
    assert 'cpython-3.12-*' in t and 'rmdir "%%~D"' in t          # tira o atalho
    assert '"!PYREAL!" -m venv' in t                              # ambiente do python.exe de verdade
    src = (BAT.parent / "src" / "ipe" / "ui" / "segmentacao.py").read_text(encoding="utf-8")
    assert 'os.environ["IPE_LANG"]' in src


def test_mensagem_montada_em_paragrafos_se_traduz():
    from ipe.core import i18n
    try:
        i18n.load("en")
        k = next(x for x in i18n._state["strings"] if x.startswith("A segmentação de órgãos usa"))
        out = i18n.tr(k + "\n\nAbrir o instalador agora?")
        assert out.startswith("Organ segmentation") and out.endswith("Open the installer now?")
    finally:
        i18n.load(i18n.BASE_LANG)
