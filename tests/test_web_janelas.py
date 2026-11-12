"""0.100.18: várias janelas, uma por monitor — a lista numa, o exame em uma ou duas janelas de visualização."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_web_mpr import _esperar, servidor  # noqa: E402,F401

from ipe.central import web as WEB  # noqa: E402


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_lista_numa_janela_e_exame_em_duas(servidor):
    pw = pytest.importorskip("playwright.sync_api")
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        ctx = b.new_context(viewport={"width": 1400, "height": 900})
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(f"http://127.0.0.1:{servidor.port}/web/")
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        pg.wait_for_selector("table.lista tbody tr")
        # 0.100.19: o painel Monitores — janelas separadas; Janela 1 e 2 em uso, a 3 não; layout 1×1 na Janela 2
        pg.click("button.janelas")
        pg.select_option(".painel-monitores select[aria-label='Onde os exames abrem']", "1")
        assert pg.input_value(".painel-monitores select[aria-label='Apresenta: Janela 2']") == "off"   # de início, uma janela
        pg.select_option(".painel-monitores select[aria-label='Apresenta: Janela 2']", "viewer")
        pg.select_option(".painel-monitores select[aria-label='Layout: Janela 2']", "1,1")
        assert "posição fica guardada" in pg.inner_text(".painel-monitores") or pg.locator(".painel-monitores button:has-text('Detectar')").count() == 1
        pg.keyboard.press("Escape")
        pg.mouse.click(700, 600)
        assert "2 janelas" in pg.inner_text("button.janelas")
        pg.locator("table.lista tbody tr").first.dblclick()
        # (o `ctx.pages` é consultado a cada volta: os eventos do Playwright só andam dentro das chamadas dele)
        for _ in range(100):
            if len(ctx.pages) == 3:
                break
            pg.wait_for_timeout(100)
        novas = [x for x in ctx.pages if x is not pg]
        assert len(novas) == 2, ([x.url[-12:] for x in ctx.pages], pg.inner_text(".estado"))
        for w in novas:
            w.on("pageerror", lambda e: erros.append(str(e)))
            w.wait_for_selector(".quadro canvas", timeout=30000)        # entrou sem pedir a senha
        # a lista continua na primeira janela, com o exame marcado
        assert pg.evaluate("() => location.hash") in ("", "#/lista")
        assert pg.locator("table.lista tbody tr.ultimo").count() == 1
        j1 = next(w for w in novas if w.url.endswith("/j1"))
        j2 = next(w for w in novas if w.url.endswith("/j2"))
        # cada janela é um visualizador completo (a 2ª começa nas séries seguintes, quando há)
        assert _esperar(lambda: "AX 2.5" in j1.locator(".quadro").first.inner_text())
        s1 = j1.evaluate("() => window.__ipeGrade.quadros.map(q => q.serie && q.serie.series)")
        assert _esperar(lambda: j2.evaluate("() => !!window.__ipeGrade.quadros[0].serie"))
        s2 = j2.evaluate("() => window.__ipeGrade.quadros.map(q => q.serie && q.serie.series)")
        assert s1[0] and s2[0]            # (o fantoma só tem duas séries: as duas janelas mostram as mesmas)
        assert j1.title().endswith("1") and j2.title().endswith("2")
        assert j2.locator(".quadro").count() == 1 and j1.locator(".quadro").count() == 2      # o layout de cada janela
        # fechar o exame numa janela fecha nas duas: ficam à espera, sem fechar
        j1.click("header button.sair")
        assert _esperar(lambda: j1.locator(".espera").count() == 1 and j2.locator(".espera").count() == 1)
        # abrir de novo pela lista: as mesmas janelas recebem o exame (nenhuma nova)
        pg.locator("table.lista tbody tr").first.dblclick()
        assert _esperar(lambda: j1.locator(".quadro canvas").count() >= 1 and j2.locator(".quadro canvas").count() >= 1, 30)
        assert len(ctx.pages) == 3
        # sair do Ipê Web fecha as janelas de visualização
        pg.click("header button.sair")
        pg.wait_for_selector("#usuario")
        assert _esperar(lambda: j1.is_closed() and j2.is_closed())
        b.close()
    # (um desenho do vtk.js que chega depois de o quadro ser desmontado, ao fechar o exame ainda carregando: sem efeito)
    erros = [e for e in erros if "isAttributeUsed" not in e]
    assert not erros, erros
