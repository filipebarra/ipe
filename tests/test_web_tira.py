"""0.99.95: tira de séries do visualizador web — arrastar a série até o quadro e a porcentagem de imagens
disponíveis no navegador enquanto o exame abre (pré-carga em segundo plano)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_web_mpr import NZ, _esperar, servidor  # noqa: E402,F401  (fixture)

from ipe.central import web as WEB  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from _web_ui import aba, botoes, espessura, ferramenta, icone, layout, menu, quadros  # noqa: E402,F401  # noqa: E402

pytestmark = pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")


def _abrir(pg, srv):
    pg.goto(f"http://127.0.0.1:{srv.port}/web/")
    pg.evaluate("() => localStorage.setItem('ipe.web.painelDir', 'true')")     # 0.100.19: vem recolhido; estes testes o usam aberto
    pg.fill("#usuario", "admin")
    pg.fill("#senha", "admin123")
    pg.click("button[type=submit]")
    pg.wait_for_selector("table.lista tbody tr")
    pg.locator("table.lista tbody tr").first.dblclick()
    pg.wait_for_selector(".quadro canvas")


def _series_dos_quadros(pg):
    return [t.split("\n")[1] if "\n" in t else t for t in pg.locator(".canto.sd").all_inner_texts()]


def test_arrastar_serie_e_imagens_disponiveis(servidor):
    pw = pytest.importorskip("playwright.sync_api")
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        _abrir(pg, servidor)
        # as duas séries: 40 cortes e o scout (1); a pré-carga leva o exame inteiro ao navegador
        assert _esperar(lambda: pg.evaluate("() => window.__ipeDisp.geral()")["total"] == NZ + 1)
        assert _esperar(lambda: pg.evaluate("() => window.__ipeDisp.geral()")["porcentagem"] == 100, 60), \
            pg.evaluate("() => window.__ipeDisp.geral()")
        # com tudo pronto, o cabeçalho e as barras da tira somem
        assert _esperar(lambda: pg.inner_text(".rodape .disponiveis") == "")
        assert pg.locator("aside.tira .serie.baixando").count() == 0
        assert pg.evaluate("() => window.__ipeDisp.porcentagem(document.querySelector('aside.tira .serie').dataset.serie)") == 100
        # arrastar: o scout para o primeiro quadro, a série de 40 para o segundo
        layout(pg, "1x2")
        assert _esperar(lambda: pg.locator(".quadro").count() == 2)
        tira = pg.locator("aside.tira .serie")
        scout = tira.filter(has_text="SCOUT")
        ax = tira.filter(has_text="AX 2.5")
        scout.drag_to(pg.locator(".quadro").nth(0))
        assert _esperar(lambda: _series_dos_quadros(pg)[0] == "SCOUT"), _series_dos_quadros(pg)
        assert pg.evaluate("() => window.__ipeGrade.ativo") == 0
        ax.drag_to(pg.locator(".quadro").nth(1))
        assert _esperar(lambda: _series_dos_quadros(pg) == ["SCOUT", "AX 2.5"]), _series_dos_quadros(pg)
        assert pg.evaluate("() => window.__ipeGrade.ativo") == 1
        # o destaque de alvo não fica para trás
        assert pg.locator(".quadro.alvo").count() == 0
        b.close()
    assert not erros, erros


def test_porcentagem_enquanto_baixa(servidor):
    """Com a rede lenta, a porcentagem aparece no cabeçalho e na miniatura antes de chegar a 100%."""
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        import time

        def devagar(route):
            time.sleep(0.15)
            route.continue_()
        pg.route("**/frames/**", devagar)
        _abrir(pg, servidor)
        vistos = set()

        def parcial():
            t = pg.inner_text(".rodape .disponiveis")
            if t and "%" in t and not t.strip().endswith("100%"):
                vistos.add("cab")
            if pg.locator("aside.tira .serie.baixando b").count():
                vistos.add("tira")
            return {"cab", "tira"} <= vistos
        assert _esperar(parcial, 30), vistos
        pg.unroute("**/frames/**")
        assert _esperar(lambda: pg.evaluate("() => window.__ipeDisp.geral()")["porcentagem"] == 100, 90)
        b.close()
