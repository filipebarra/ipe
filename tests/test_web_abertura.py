"""0.100.60: o Ipê Web manda ao servidor o tempo de abertura do exame (primeira imagem e tudo disponível), e o servidor
escreve no registro a linha "Abertura web (…)" — para comparar versões, como a "Abertura (…)" do Ipê de mesa."""
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_web_dinamica import servidor_din  # noqa: E402,F401
from test_web_mpr import _esperar  # noqa: E402

from ipe.central import web as WEB  # noqa: E402


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_navegador_registra_o_tempo_de_abertura(servidor_din):
    pw = pytest.importorskip("playwright.sync_api")
    linhas = []

    class H(logging.Handler):
        def emit(self, rec):
            linhas.append(rec.getMessage())
    h = H()
    reg = logging.getLogger("ipe.abertura")
    nivel = reg.level
    reg.addHandler(h)
    reg.setLevel(logging.INFO)
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            pg.goto(f"http://127.0.0.1:{servidor_din.port}/web/")
            pg.fill("#usuario", "admin")
            pg.fill("#senha", "admin123")
            pg.click("button[type=submit]")
            pg.wait_for_selector("table.lista tbody tr")
            pg.locator("table.lista tbody tr").first.dblclick()
            pg.wait_for_selector(".quadro canvas")
            assert _esperar(lambda: any("primeira imagem" in x for x in linhas), 30), linhas
            assert _esperar(lambda: any("tudo disponível" in x for x in linhas), 60), linhas
            b.close()
    finally:
        reg.removeHandler(h)
        reg.setLevel(nivel)
    primeira = [x for x in linhas if "primeira imagem" in x]
    tudo = [x for x in linhas if "tudo disponível" in x]
    assert len(primeira) == 1 and len(tudo) == 1, linhas
    assert primeira[0].startswith("Abertura web (MR, 5 séries): primeira imagem em ")
    for etapa in ("series ", "exame ", "tela ", "protocolo ", "imagem "):
        assert etapa in primeira[0], primeira[0]
    assert "Chrome" in primeira[0] and "1400x" in primeira[0]
    assert "30 imagens" in tudo[0] and "MB/s" in tudo[0], tudo[0]
