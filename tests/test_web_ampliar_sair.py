"""0.100.5: duplo clique num quadro amplia (1×1) e outro volta ao arranjo de antes, cada quadro como estava; "Sair"
com o exame aberto volta à lista (na lista, sai); fechar a aba com o exame aberto pede confirmação."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _web_ui import layout  # noqa: E402
from test_web_mpr import _esperar, servidor  # noqa: E402,F401  (fixture)

from ipe.central import web as WEB  # noqa: E402


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_duplo_clique_sair_e_fechar(servidor):
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
        pg.click(".series button.serie[title='SCOUT']")
        assert _esperar(lambda: "SCOUT" in pg.locator(".quadro").nth(1).inner_text())
        pg.evaluate("() => window.__ipeGrade.viewport(0).setImageIdIndex(7)")
        pg.wait_for_timeout(500)
        largura = lambda i: pg.locator(".quadro .tela").nth(i).bounding_box()["width"]  # noqa: E731
        w0 = largura(0)
        # duplo clique no axial: ele ocupa a tela; o scout some
        pg.locator(".quadro .tela").nth(0).dblclick()
        assert _esperar(lambda: pg.evaluate("() => window.__ipeGrade.ampliado") == 0)
        assert _esperar(lambda: largura(0) > w0 * 1.7)
        assert not pg.locator(".quadro").nth(1).is_visible()
        assert pg.evaluate("() => window.__ipeGrade.viewport(0).getCurrentImageIdIndex()") == 7
        # outro duplo clique volta ao 1×2, cada um como estava
        pg.locator(".quadro .tela").nth(0).dblclick()
        assert _esperar(lambda: pg.evaluate("() => window.__ipeGrade.ampliado") is None)
        assert _esperar(lambda: abs(largura(0) - w0) < 3)
        assert pg.locator(".quadro").nth(1).is_visible() and "SCOUT" in pg.locator(".quadro").nth(1).inner_text()
        assert pg.evaluate("() => window.__ipeGrade.viewport(0).getCurrentImageIdIndex()") == 7
        assert (pg.evaluate("() => [window.__ipeGrade.linhas, window.__ipeGrade.colunas]")) == [1, 2]
        # sair da página (fechar, recarregar, ir a outro endereço) com o exame aberto pede confirmação;
        # recusar deixa o exame aberto
        dialogos = []
        pg.on("dialog", lambda d: (dialogos.append(d.type), d.dismiss()))
        url = pg.url
        with pytest.raises(Exception):
            pg.goto("about:blank", timeout=3000)
        assert dialogos == ["beforeunload"] and pg.url == url
        assert pg.locator(".quadro canvas").count() >= 1
        # "Sair" com o exame aberto: volta à lista, sem sair do Ipê Web
        pg.click("header button.sair")
        pg.wait_for_selector("table.lista tbody tr")
        assert pg.evaluate("() => location.hash") == "#/lista"
        # na lista, sair da página não pede nada, e "Sair" sai do Ipê Web
        pg.click("header button.sair")
        pg.wait_for_selector("#usuario")
        b.close()
    assert not erros, erros
