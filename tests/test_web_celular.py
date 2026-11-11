"""0.100.18: o visualizador web no celular e no tablet."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_web_mpr import _esperar, servidor  # noqa: E402,F401

from ipe.central import web as WEB  # noqa: E402

APARELHOS = [("chromium", "Pixel 7"), ("webkit", "iPhone 13"), ("chromium", "Galaxy Tab S4")]


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
@pytest.mark.parametrize("motor,aparelho", APARELHOS)
def test_login_e_exame_no_celular(servidor, motor, aparelho, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    erros, console = [], []
    with pw.sync_playwright() as p:
        try:
            b = getattr(p, motor).launch(**({"args": ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--host-resolver-rules=MAP ipe.teste 127.0.0.1"]} if motor == "chromium" else {}))
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"{motor} não instalado: {e}")
        ctx = b.new_context(**p.devices[aparelho])
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
        # pelo nome (como pelo IP da rede, sem HTTPS): o navegador trata como contexto **não seguro**
        pg.goto(f"http://{'ipe.teste' if motor == 'chromium' else '127.0.0.1'}:{servidor.port}/web/")
        assert motor != "chromium" or pg.evaluate("() => window.isSecureContext") is False
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.tap("button[type=submit]")
        try:
            pg.wait_for_selector("table.lista tbody tr, .lista-cartoes .cartao", timeout=20000)
        except Exception:
            import os
            if os.environ.get("IPE_SHOT_DIR"):
                pg.screenshot(path=os.path.join(os.environ["IPE_SHOT_DIR"], f"cel_{aparelho.replace(' ', '_')}.png"))
            raise AssertionError(f"não passou do login: {pg.inner_text('body')[:300]!r} erros={erros} console={console[:5]}")
        cel = aparelho != "Galaxy Tab S4" or pg.viewport_size["width"] <= 760
        assert pg.evaluate("() => document.documentElement.classList.contains('cel')") == cel
        # recarregar a página (o celular faz isso sozinho) não volta ao login: a sessão é da aba
        pg.reload()
        pg.wait_for_selector("table.lista tbody tr", timeout=20000)
        assert pg.locator("#usuario").count() == 0
        # um toque abre o exame (no toque não há duplo clique)
        pg.locator("table.lista tbody tr").first.tap()
        pg.wait_for_selector(".quadro canvas", timeout=30000)
        if cel:
            # uma imagem por vez, painéis fechados (gavetas), barra de ferramentas visível
            assert pg.locator(".quadro").count() == 1
            assert not pg.locator(".tira").is_visible() and not pg.locator(".lateral").is_visible()
            assert pg.locator("nav.barra button[aria-label='Voltar à lista']").is_visible()
            pg.locator("nav.barra button[aria-label='Séries']").tap()
            assert pg.locator(".tira").is_visible()
            pg.locator(".tira .serie").nth(1).tap()                     # escolher a série fecha a gaveta
            assert _esperar(lambda: not pg.locator(".tira").is_visible())
            assert _esperar(lambda: "SCOUT" in pg.locator(".quadro").first.inner_text())
            pg.locator("nav.barra button[aria-label='Painel de ferramentas']").tap()
            assert pg.locator(".lateral").is_visible()
            largura = pg.viewport_size["width"]
            assert pg.evaluate("() => document.documentElement.scrollWidth") <= largura + 1     # nada vaza para o lado
        # um dedo rola os cortes (sem escolha guardada)
        assert pg.evaluate("() => window.__ipeBotoes().esq") == "rolar"
        pg.locator("header button.sair").tap()
        pg.wait_for_selector("table.lista tbody tr")
        b.close()
    assert not erros, erros
