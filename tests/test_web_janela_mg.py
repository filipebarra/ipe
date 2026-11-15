"""0.100.52: no Ipê Web, a mamografia fica com a janela do arquivo, e a janela que o médico põe num corte da
tomossíntese vale para os outros cortes da série (não para a 2D da mesma pilha). Exames fabricados."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_web_mamografia import _abrir, _celulas, _prontas, servidor_mg  # noqa: E402,F401
from test_web_mpr import _esperar  # noqa: E402

from ipe.central import web as WEB  # noqa: E402

VOI = "() => { const v = window.__ipeGrade.viewport(0).getProperties().voiRange; return v ? [v.lower, v.upper] : null; }"


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_janela_da_tomo_fica_na_serie(servidor_mg):
    pw = pytest.importorskip("playwright.sync_api")
    atual, _ant = servidor_mg.estudos
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        _abrir(pg, servidor_mg, atual)
        assert _prontas(pg, 4)
        assert _celulas(pg)["quadros"][0]["cortes"] == 10                     # a 2D e os 9 cortes da tomo
        pg.locator(".quadro").nth(0).click()
        assert _esperar(lambda: _celulas(pg)["quadros"][0]["pronto"])
        voi_2d = pg.evaluate(VOI)
        pg.evaluate("() => window.__ipeGrade.viewport(0).setImageIdIndex(4)")
        assert _esperar(lambda: _celulas(pg)["quadros"][0]["corte"] == 4 and _celulas(pg)["quadros"][0]["tomo"])
        pg.wait_for_timeout(400)
        voi_tomo = pg.evaluate(VOI)
        # janela à mão (botão esquerdo = janela) num corte da tomo
        caixa = pg.locator(".quadro .tela").first.bounding_box()
        x, y = caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2
        pg.mouse.move(x, y)
        pg.mouse.down()
        pg.mouse.move(x + 80, y + 60, steps=8)
        pg.mouse.up()
        pg.wait_for_timeout(200)
        voi_mao = pg.evaluate(VOI)
        assert voi_mao != voi_tomo
        for k in (7, 2, 9):                                                    # outros cortes: a mesma janela
            pg.evaluate(f"() => window.__ipeGrade.viewport(0).setImageIdIndex({k})")
            assert _esperar(lambda k=k: _celulas(pg)["quadros"][0]["corte"] == k)
            pg.wait_for_timeout(300)
            assert pg.evaluate(VOI) == pytest.approx(voi_mao, abs=1e-3)
        pg.evaluate("() => window.__ipeGrade.viewport(0).setImageIdIndex(0)")   # a 2D: a janela do arquivo
        assert _esperar(lambda: _celulas(pg)["quadros"][0]["corte"] == 0)
        pg.wait_for_timeout(300)
        assert pg.evaluate(VOI) == pytest.approx(voi_2d, abs=1e-3)
        pg.evaluate("() => window.__ipeGrade.viewport(0).setImageIdIndex(5)")   # e de volta à tomo: a do médico
        assert _esperar(lambda: _celulas(pg)["quadros"][0]["corte"] == 5)
        pg.wait_for_timeout(300)
        assert pg.evaluate(VOI) == pytest.approx(voi_mao, abs=1e-3)
        b.close()
    assert not erros, erros
