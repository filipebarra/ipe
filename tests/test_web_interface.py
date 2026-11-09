"""0.99.97: interface nova do visualizador web — barra de ícones com a função de cada botão do mouse (como no
Ipê, com a marca embaixo do ícone), menu do botão direito (clicar e soltar; segurar e arrastar faz a função),
painéis laterais recolhíveis e abas."""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _web_ui import aba, botoes, layout, menu  # noqa: E402
from test_web_mpr import NZ, _esperar, servidor  # noqa: E402,F401  (fixture)
from test_web_tira import _abrir  # noqa: E402

from ipe.central import web as WEB  # noqa: E402

pytestmark = pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")


def _marcas(pg, ferr):
    return pg.evaluate(f"""() => [...document.querySelector("nav.barra button[data-ferramenta='{ferr}'] .marcas").children]
        .map((s) => s.classList.contains('on'))""")


def test_botoes_do_mouse_menu_e_paineis(servidor):
    pw = pytest.importorskip("playwright.sync_api")
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        _abrir(pg, servidor)
        # o padrão: janela no esquerdo, mover no meio, zoom no direito — e as marcas embaixo dos ícones
        assert botoes(pg) == {"esq": "janela", "meio": "mover", "dir": "zoom"}
        assert _marcas(pg, "janela") == [True, False, False]
        assert _marcas(pg, "mover") == [False, True, False]
        assert _marcas(pg, "zoom") == [False, False, True]
        # clicar no ícone da régua com o botão direito: a régua vai para o direito
        regua = pg.locator("nav.barra button[data-ferramenta='regua']")
        regua.click(button="right")
        assert botoes(pg)["dir"] == "regua" and _marcas(pg, "regua") == [False, False, True]
        assert _marcas(pg, "zoom") == [False, False, False]
        # com o do meio, a régua também fica no meio (duas marcas)
        regua.click(button="middle")
        assert botoes(pg) == {"esq": "janela", "meio": "regua", "dir": "regua"}
        assert _marcas(pg, "regua") == [False, True, True]
        # o zoom de volta no direito e o mover no meio, pelo botão esquerdo/do meio/direito nos ícones
        pg.locator("nav.barra button[data-ferramenta='zoom']").click(button="right")
        pg.locator("nav.barra button[data-ferramenta='mover']").click(button="middle")
        assert botoes(pg) == {"esq": "janela", "meio": "mover", "dir": "zoom"}
        # família: a setinha das ROIs escolhe a retangular, que vai para o esquerdo
        roi = pg.locator("nav.barra button[data-ferramenta='elipse']")
        bb = roi.bounding_box()
        pg.mouse.click(bb["x"] + bb["width"] - 5, bb["y"] + bb["height"] / 2)
        menu(pg, "ROI retangular")
        assert botoes(pg)["esq"] == "retangulo"
        assert pg.locator("nav.barra button[data-ferramenta='retangulo']").count() == 1
        # o rodapé diz a função de cada botão
        assert "ROI retangular" in pg.inner_text(".rodape .botoes-mouse")
        # menu do botão direito: clicar e soltar abre; Esc fecha
        tela = pg.locator(".quadro .tela").first.bounding_box()
        cx, cy = tela["x"] + tela["width"] / 2, tela["y"] + tela["height"] / 2
        pg.mouse.click(cx, cy, button="right")
        assert _esperar(lambda: pg.locator(".menu[aria-label='Menu da imagem']").count() == 1)
        rotulos = pg.locator(".menu .menu-item .menu-rotulo").all_inner_texts()
        for r in ("Janela", "Zoom", "Girar e espelhar", "Plano", "Funções dos botões", "Série", "Restaurar"):
            assert r in rotulos, rotulos
        # submenu: Funções dos botões › Botão do meio › Régua
        pg.hover(".menu .menu-item:has-text('Funções dos botões')")
        pg.hover(".menu .menu-item:has-text('Botão do meio')")
        menu(pg, "Régua")
        assert botoes(pg)["meio"] == "regua" and pg.locator(".menu").count() == 0
        # segurar e arrastar com o direito faz a função (zoom) e não abre o menu
        zoom0 = pg.evaluate("() => window.__ipeGrade.viewport(0).getCamera().parallelScale")
        pg.mouse.move(cx, cy)
        pg.mouse.down(button="right")
        for k in range(1, 9):
            pg.mouse.move(cx, cy + 10 * k)
            time.sleep(0.02)
        pg.mouse.up(button="right")
        time.sleep(0.3)
        assert pg.locator(".menu").count() == 0
        assert pg.evaluate("() => window.__ipeGrade.viewport(0).getCamera().parallelScale") != pytest.approx(zoom0)
        # menu › Girar e espelhar › Girar 90° à direita
        pg.mouse.click(cx, cy, button="right")
        pg.hover(".menu .menu-item:has-text('Girar e espelhar')")
        menu(pg, "Girar 90° à direita")
        assert _esperar(lambda: pg.evaluate("() => window.__ipeGrade.viewport(0).getViewPresentation().rotation") == 90)
        # menu › Quadros e cine › 2 × 2
        pg.mouse.click(cx, cy, button="right")
        pg.hover(".menu .menu-item:has-text('Quadros e cine')")
        menu(pg, "2 × 2")
        assert _esperar(lambda: pg.locator(".quadro").count() == 4)
        # painéis: recolher e abrir de novo; a escolha fica gravada
        pg.click("button[aria-label='Recolher o painel de séries']")
        assert pg.locator("aside.tira").is_hidden()
        pg.click("button[aria-label='Abrir o painel de séries']")
        assert pg.locator("aside.tira").is_visible()
        pg.click("button[aria-label='Recolher o painel de ferramentas']")
        assert pg.locator("aside.lateral").is_hidden()
        pg.click("button[aria-label='Abrir o painel de ferramentas']")
        assert pg.locator("aside.lateral").is_visible()
        # abas: DICOM mostra as tags da imagem do quadro ativo
        aba(pg, "DICOM")
        assert _esperar(lambda: "SeriesDescription" in pg.inner_text(".corpo-aba"))
        pg.fill(".corpo-aba input[type=search]", "Modality")
        assert _esperar(lambda: pg.locator("table.tags tr:visible").count() >= 1)
        aba(pg, "Imagem")
        assert "Ajustar" in pg.inner_text(".corpo-aba")
        layout(pg, "1x1")
        assert _esperar(lambda: pg.locator(".quadro").count() == 1)
        b.close()
    assert not erros, erros
