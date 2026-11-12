"""0.100.19: a aparência do visualizador web é do usuário — séries à esquerda, embaixo ou em cima; botões em cima ou
numa coluna à esquerda; modo leitura (só as imagens); o painel da direita vem recolhido."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_web_mpr import _esperar, servidor  # noqa: E402,F401

from ipe.central import web as WEB  # noqa: E402


def _caixa(pg, sel):
    return pg.locator(sel).first.bounding_box()


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_series_botoes_e_modo_leitura(servidor):
    pw = pytest.importorskip("playwright.sync_api")
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1500, "height": 900})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(f"http://127.0.0.1:{servidor.port}/web/")
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        pg.wait_for_selector("table.lista tbody tr")
        pg.locator("table.lista tbody tr").first.dblclick()
        pg.wait_for_selector(".quadro canvas")
        # o painel da direita vem recolhido (o trilho o reabre)
        assert not pg.locator(".lateral").is_visible()
        grade0 = _caixa(pg, ".grade")
        tira0 = _caixa(pg, ".tira")
        assert tira0["x"] < grade0["x"] and tira0["height"] > 400                 # à esquerda, de pé
        menu = "nav.barra button[aria-label='Aparência: posição das séries e dos botões']"
        # séries embaixo
        pg.click(menu)
        pg.locator(".menu button:has-text('Embaixo')").click()
        assert _esperar(lambda: _caixa(pg, ".tira")["y"] > _caixa(pg, ".grade")["y"] + 300)
        t = _caixa(pg, ".tira")
        assert t["width"] > 900 and t["height"] < 200
        assert _caixa(pg, ".grade")["width"] > grade0["width"] + 150              # a imagem ganhou a largura da coluna
        # séries em cima
        pg.click(menu)
        pg.locator(".menu button:has-text('Em cima')").first.click()
        assert _esperar(lambda: _caixa(pg, ".tira")["y"] < _caixa(pg, ".grade")["y"])
        # botões numa coluna à esquerda: a barra fica de pé, ao lado da imagem
        pg.click(menu)
        pg.locator(".menu button:has-text('À esquerda')").last.click()
        assert _esperar(lambda: _caixa(pg, "nav.barra")["height"] > 500 and _caixa(pg, "nav.barra")["width"] < 80)
        assert _caixa(pg, "nav.barra")["x"] < _caixa(pg, ".grade")["x"]
        # fica lembrado ao reabrir o exame
        pg.click("header button.sair")
        pg.wait_for_selector("table.lista tbody tr")
        pg.locator("table.lista tbody tr").first.dblclick()
        pg.wait_for_selector(".quadro canvas")
        assert _esperar(lambda: _caixa(pg, "nav.barra")["width"] < 80 and _caixa(pg, ".tira")["y"] < _caixa(pg, ".grade")["y"])
        # modo leitura: só as imagens; Esc volta
        antes = _caixa(pg, ".grade")
        pg.locator(".quadro .tela").first.click()
        pg.keyboard.press("f")
        assert _esperar(lambda: not pg.locator("header").is_visible() and not pg.locator(".tira").is_visible()
                        and not pg.locator("nav.barra").is_visible())
        cheia = _caixa(pg, ".grade")
        assert cheia["width"] > antes["width"] and cheia["height"] > antes["height"] and cheia["height"] > 880
        pg.keyboard.press("Escape")
        assert _esperar(lambda: pg.locator("header").is_visible() and pg.locator("nav.barra").is_visible())
        b.close()
    assert not erros, erros
