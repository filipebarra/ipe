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
        ctx = b.new_context(viewport={"width": 1920, "height": 1080})
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
        # 0.100.55: sem a lista dos monitores (o navegador não deu a permissão), escolhe-se quantas janelas
        assert pg.input_value(".painel-monitores select[aria-label='Quantas janelas de visualização']") == "1"
        pg.select_option(".painel-monitores select[aria-label='Quantas janelas de visualização']", "2")
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
        # 0.100.20: janelas ligadas — rolar, janela e zoom numa janela seguem para a outra
        idx = "() => window.__ipeGrade.viewport(0).getCurrentImageIdIndex()"
        j2.locator(".tira .serie").first.click()            # (a Janela 2 começou na série seguinte: põe a mesma da 1)
        for _ in range(60):
            if j2.evaluate("() => window.__ipeGrade.viewport(0).getImageIds().length") > 1:
                break
            j2.wait_for_timeout(100)
        j1.wait_for_timeout(800)
        j1.evaluate("() => window.__ipeGrade.viewport(0).setImageIdIndex(7)")
        for _ in range(60):
            if j2.evaluate(idx) == 7:
                break
            j2.wait_for_timeout(100)
        assert j2.evaluate(idx) == 7
        j1.evaluate("() => { const v = window.__ipeGrade.viewport(0); v.setProperties({voiRange: {lower: -100, upper: 300}}); v.render(); }")
        for _ in range(60):
            if j2.evaluate("() => Math.round(window.__ipeGrade.viewport(0).getProperties().voiRange.upper)") == 300:
                break
            j2.wait_for_timeout(100)
        assert j2.evaluate("() => Math.round(window.__ipeGrade.viewport(0).getProperties().voiRange.lower)") == -100
        # 0.100.21: linha de referência entre janelas — com a Janela 2 no SCOUT (outro plano), o corte da Janela 1
        # aparece nela como uma linha tracejada; na mesma série (planos paralelos) não há linha
        linha = "() => [...document.querySelectorAll('canvas.linha-fora')].some(c => c.dataset.linha === '1')"
        assert not j2.evaluate(linha)
        j2.locator(".tira .serie").nth(1).click()
        for _ in range(60):
            if j2.evaluate("() => window.__ipeGrade.viewport(0).getImageIds().length") == 1:
                break
            j2.wait_for_timeout(100)
        j1.evaluate("() => window.__ipeGrade.viewport(0).setImageIdIndex(9)")
        for _ in range(60):
            if j2.evaluate(linha):
                break
            j2.wait_for_timeout(100)
        assert j2.evaluate(linha)
        # arrastar uma série da tira da Janela 1 e soltar num quadro da Janela 2 (o exame vai junto no arrasto)
        dados = j1.evaluate("""() => { const dt = new DataTransfer();
            document.querySelector('.tira .serie').dispatchEvent(new DragEvent('dragstart', {dataTransfer: dt, bubbles: true}));
            return Object.fromEntries(dt.types.map(t => [t, dt.getData(t)])); }""")
        assert dados["application/x-ipe-estudo"] and dados["application/x-ipe-serie"]
        j2.evaluate("""(d) => { const dt = new DataTransfer(); for (const [k, v] of Object.entries(d)) dt.setData(k, v);
            document.querySelector('.grade > *').dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true})); }""", dados)
        for _ in range(80):
            if j2.evaluate("() => window.__ipeGrade.viewport(0).getImageIds().length") > 1:
                break
            j2.wait_for_timeout(100)
        assert j2.evaluate("() => window.__ipeGrade.quadros[0].serie.series") == dados["application/x-ipe-serie"]
        j1.evaluate("() => window.__ipeGrade.viewport(0).setImageIdIndex(7)")
        for _ in range(60):
            if j2.evaluate(idx) == 7:
                break
            j2.wait_for_timeout(100)
        # desligando na segunda janela, ela para de seguir
        j2.set_viewport_size({"width": 1920, "height": 1080})   # 0.100.53: na janela pequena o botão vai para o "»"
        j2.wait_for_timeout(300)
        j2.click("nav.barra button[aria-label^='Ligar os quadros']")
        assert _esperar(lambda: j2.get_attribute("nav.barra button[aria-label^='Ligar os quadros']", "aria-pressed") == "false")
        j2.wait_for_timeout(500)          # os recados que já estavam a caminho chegam antes
        antes = j2.evaluate(idx)
        j1.evaluate("() => window.__ipeGrade.viewport(0).setImageIdIndex(12)")
        j1.wait_for_timeout(1200)
        assert j2.evaluate(idx) == antes
        j2.click("nav.barra button[aria-label^='Ligar os quadros']")
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


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_monitores_detectados(servidor):
    """0.100.55: com a permissão do navegador, uma linha por monitor (resolução e orientação), quantos houver."""
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        ctx = b.new_context(viewport={"width": 1600, "height": 900})
        # quatro monitores (um em retrato), como o navegador os daria pela API de várias telas
        ctx.add_init_script("""(() => {
          const t = (l, w, h, nome, pri) => ({availLeft: l, availTop: 0, availWidth: w, availHeight: h, width: w, height: h,
                                              label: nome, isPrimary: pri});
          const telas = [t(0, 1920, 1080, 'A', true), t(1920, 1080, 1920, 'B', false), t(3000, 2048, 2560, 'C', false),
                         t(5048, 2048, 2560, 'D', false)];
          window.getScreenDetails = async () => ({screens: telas, currentScreen: telas[0]});
          const q = navigator.permissions.query.bind(navigator.permissions);
          navigator.permissions.query = (d) => d && d.name === 'window-management' ? Promise.resolve({state: 'granted'}) : q(d);
        })()""")
        pg = ctx.new_page()
        pg.goto(f"http://127.0.0.1:{servidor.port}/web/")
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        pg.wait_for_selector("table.lista tbody tr")
        pg.click("button.janelas")
        pg.select_option(".painel-monitores select[aria-label='Onde os exames abrem']", "1")
        assert _esperar(lambda: pg.locator(".tabela-monitores.por-monitor").count() == 1, 10)
        texto = pg.inner_text(".tabela-monitores")
        assert "1080×1920 (retrato)" in texto and "1920×1080 (paisagem)" in texto and "4 —" in texto
        assert pg.locator(".tabela-monitores select[aria-label^='Apresenta']").count() == 4
        # cada outro monitor virou uma janela de visualização; o primeiro é o da lista
        assert pg.evaluate("() => JSON.parse(localStorage.getItem('ipe.web.monitores')).janelas.length") == 3
        pg.select_option(".tabela-monitores select[aria-label='Apresenta: Monitor 3']", "off")
        assert pg.evaluate("() => JSON.parse(localStorage.getItem('ipe.web.monitores')).janelas.length") == 2
        pg.select_option(".tabela-monitores select[aria-label='Apresenta: Monitor 4']", "compare")
        js = pg.evaluate("() => JSON.parse(localStorage.getItem('ipe.web.monitores')).janelas")
        assert [j["papel"] for j in js] == ["viewer", "compare"] and js[1]["tela"].startswith("5048,")
        b.close()


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_ligar_quadros_numa_janela(servidor):
    """0.100.55: com um monitor só, o botão Ligar faz os quadros desta janela rolarem juntos."""
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        pg.goto(f"http://127.0.0.1:{servidor.port}/web/")
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        pg.wait_for_selector("table.lista tbody tr")
        pg.locator("table.lista tbody tr").first.dblclick()
        assert _esperar(lambda: pg.evaluate("() => window.__ipeGrade && window.__ipeGrade.quadros.length >= 2 && "
                                            "window.__ipeGrade.quadros.every(q => !!q.serie)"), 30)
        # a mesma série nos dois quadros
        pg.evaluate("""async () => { const g = window.__ipeGrade; const s = g.quadros[0].serie;
                       if (g.quadros[1].serie.series !== s.series) await g.mostrar(1, s); }""")
        idx = "(i) => window.__ipeGrade.viewport(i).getCurrentImageIdIndex()"
        bt = "nav.barra button[aria-label^='Ligar os quadros']"
        assert pg.get_attribute(bt, "aria-pressed") == "false"        # numa janela só, começa desligado
        pg.evaluate("() => { window.__ipeGrade.ativar(0); window.__ipeGrade.viewport(0).setImageIdIndex(3); }")
        pg.wait_for_timeout(800)
        antes = pg.evaluate(idx, 1)
        assert antes != 3
        pg.click(bt)
        pg.evaluate("() => { window.__ipeGrade.ativar(0); window.__ipeGrade.viewport(0).setImageIdIndex(9); }")
        assert _esperar(lambda: pg.evaluate(idx, 1) == 9, 10), pg.evaluate(idx, 1)
        b.close()
