"""0.100.3: a medida que ficou pela metade não trava o mouse. As medidas do Cornerstone3D desenham também em "clique,
move, clique": um clique só começa a linha, e enquanto ela não termina a biblioteca ignora todas as ferramentas em
todos os botões. Clicar noutro quadro, trocar de ferramenta ou apertar Esc desfaz o desenho pela metade."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _web_ui import ferramenta, layout  # noqa: E402
from test_web_mpr import _esperar, servidor  # noqa: E402,F401  (fixture)

from ipe.central import web as WEB  # noqa: E402


def _centro(pg, i):
    bb = pg.locator(".quadro .tela").nth(i).bounding_box()
    return bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2


def _voi(pg, i):
    return pg.evaluate(f"() => JSON.stringify(window.__ipeGrade.viewport({i}).getProperties().voiRange)")


def _arrastar(pg, x, y, botao="left"):
    pg.mouse.move(x, y)
    pg.mouse.down(button=botao)
    pg.mouse.move(x + 40, y + 30, steps=5)
    pg.mouse.move(x + 80, y + 60, steps=5)
    pg.mouse.up(button=botao)
    pg.wait_for_timeout(500)                      # o Cornerstone3D espera o duplo clique


def _meio_clique(pg, x, y):
    """Um clique só com a régua: a linha começa e fica presa ao cursor."""
    ferramenta(pg, "regua")
    pg.mouse.move(x - 50, y)
    pg.mouse.down()
    pg.mouse.up()
    pg.mouse.move(x - 20, y + 5, steps=4)
    pg.wait_for_timeout(600)
    assert pg.evaluate("() => window.__ipeDesenhando()") is True


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_medida_pela_metade_nao_trava_o_mouse(servidor):
    pw = pytest.importorskip("playwright.sync_api")
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1500, "height": 950})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(f"http://127.0.0.1:{servidor.port}/web/")
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        pg.wait_for_selector("table.lista tbody tr")
        pg.locator("table.lista tbody tr").first.dblclick()
        pg.wait_for_selector(".quadro canvas")
        assert _esperar(lambda: "AX 2.5" in pg.locator(".quadro").first.inner_text())
        layout(pg, "1x2")
        pg.locator(".quadro").nth(1).click()
        pg.click(".series button.serie[title='AX 2.5']")
        pg.wait_for_timeout(1500)
        x0, y0 = _centro(pg, 0)
        x1, y1 = _centro(pg, 1)
        medidas = "() => window.__ipeMed.DB.size"
        # 1) começa a régua no quadro 1, troca para a janela e usa no quadro 2: a janela funciona
        _meio_clique(pg, x0, y0)
        ferramenta(pg, "janela")
        assert pg.evaluate("() => window.__ipeDesenhando()") is False
        v = _voi(pg, 1)
        _arrastar(pg, x1, y1)
        assert _voi(pg, 1) != v
        pg.wait_for_timeout(500)
        # 2) sem trocar de ferramenta: clicar noutro quadro desfaz a linha pela metade
        ferramenta(pg, "janela", "meio")              # o botão do meio é a janela; o esquerdo vai ser a régua
        _meio_clique(pg, x0, y0)
        v = _voi(pg, 1)
        _arrastar(pg, x1, y1, "middle")
        assert _voi(pg, 1) != v and pg.evaluate("() => window.__ipeDesenhando()") is False
        # 3) Esc desfaz; a medida pela metade não vai para o banco
        n = pg.evaluate(medidas)
        _meio_clique(pg, x0, y0)
        pg.keyboard.press("Escape")
        assert pg.evaluate("() => window.__ipeDesenhando()") is False
        pg.wait_for_timeout(500)
        assert pg.evaluate(medidas) == n
        # 4) e a régua continua medindo: arrastar faz a medida
        _arrastar(pg, x0 - 60, y0 - 40)
        assert _esperar(lambda: pg.evaluate(medidas) == n + 1)
        b.close()
    assert not erros, erros


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_trocar_a_funcao_do_botao_vale_no_mouse(servidor):
    """0.100.3: a função que sai de um botão sai mesmo (o Cornerstone3D somava os botões e só tirava o esquerdo):
    a janela no direito, depois o zoom no direito — o arrasto com o direito faz zoom e não mexe mais na janela."""
    pw = pytest.importorskip("playwright.sync_api")
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1500, "height": 950})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(f"http://127.0.0.1:{servidor.port}/web/")
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        pg.wait_for_selector("table.lista tbody tr")
        pg.locator("table.lista tbody tr").first.dblclick()
        pg.wait_for_selector(".quadro canvas")
        assert _esperar(lambda: "AX 2.5" in pg.locator(".quadro").first.inner_text())
        pg.wait_for_timeout(800)
        x, y = _centro(pg, 0)
        zoom = lambda: pg.evaluate("() => window.__ipeGrade.viewport(0).getZoom()")  # noqa: E731
        pan = lambda: pg.evaluate("() => JSON.stringify(window.__ipeGrade.viewport(0).getPan())")  # noqa: E731
        for botao, mb in (("dir", "right"), ("meio", "middle")):
            ferramenta(pg, "janela", botao)
            v, z = _voi(pg, 0), zoom()
            _arrastar(pg, x, y, mb)
            assert _voi(pg, 0) != v and zoom() == z, botao              # a janela
            ferramenta(pg, "zoom", botao)
            v, z = _voi(pg, 0), zoom()
            _arrastar(pg, x, y, mb)
            assert zoom() != z and _voi(pg, 0) == v, botao              # agora só o zoom
            ferramenta(pg, "mover", botao)
            v, z, m = _voi(pg, 0), zoom(), pan()
            _arrastar(pg, x, y, mb)
            assert pan() != m and zoom() == z and _voi(pg, 0) == v, botao  # e agora só mover
        # o esquerdo, que era a janela, vira régua e mede (sem mexer na janela)
        ferramenta(pg, "janela")
        ferramenta(pg, "regua")
        n, v = pg.evaluate("() => window.__ipeMed.DB.size"), _voi(pg, 0)
        _arrastar(pg, x - 60, y - 40)
        assert _esperar(lambda: pg.evaluate("() => window.__ipeMed.DB.size") == n + 1) and _voi(pg, 0) == v
        b.close()
    assert not erros, erros
