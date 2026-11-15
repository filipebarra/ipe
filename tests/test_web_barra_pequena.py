"""0.100.53: a barra de cima do Ipê Web em telas menores — o que não cabe vai para o "»" (nada fica escondido sem
aviso). Exame fabricado."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_web_mamografia import _abrir, _prontas, servidor_mg  # noqa: E402,F401
from test_web_mpr import _esperar  # noqa: E402

from ipe.central import web as WEB  # noqa: E402

ESTADO = """() => {
  const nav = document.querySelector('nav.barra'); const b = nav.getBoundingClientRect();
  const bts = [...nav.querySelectorAll('button')].filter(x => !x.closest('.so-cel') && getComputedStyle(x).display !== 'none');
  const cortados = bts.filter(x => { const c = x.getBoundingClientRect(); return c.right > b.right + 1; })
    .map(x => x.getAttribute('aria-label'));
  const mais = nav.querySelector('.mais');
  return { cortados, mais: !!mais && !mais.hidden, escondidos: nav.querySelectorAll('.transbordou').length,
           rolagem: nav.scrollWidth > nav.clientWidth + 1 };
}"""


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_barra_em_telas_menores(servidor_mg):
    pw = pytest.importorskip("playwright.sync_api")
    atual, _ant = servidor_mg.estudos
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        _abrir(pg, servidor_mg, atual)
        assert _prontas(pg, 4)
        e = pg.evaluate(ESTADO)
        assert not e["mais"] and e["escondidos"] == 0 and not e["cortados"], pg.evaluate("() => { const n = document.querySelector('nav.barra'); return [n.scrollWidth, n.clientWidth, innerWidth, [...n.querySelectorAll('.transbordou')].map(x => x.getAttribute('aria-label') || x.className)]; }")
        for w, h in ((1600, 900), (1366, 768), (1280, 720), (1024, 768)):
            pg.set_viewport_size({"width": w, "height": h})
            assert _esperar(lambda: pg.evaluate(ESTADO)["mais"], 10)
            pg.wait_for_timeout(200)
            e = pg.evaluate(ESTADO)
            assert not e["cortados"] and not e["rolagem"] and e["escondidos"] > 0, (w, e)
        # 1366 × 768: o Laudo está no "»" e abre de lá
        pg.set_viewport_size({"width": 1366, "height": 768})
        pg.wait_for_timeout(300)
        pg.click("nav.barra .mais")
        itens = pg.locator(".menu .menu-item").all_inner_texts()
        assert any("Laudo" in t for t in itens) and any("CAD/IA" in t for t in itens)
        pg.locator(".menu .menu-item:has-text('Laudo')").click()
        assert _esperar(lambda: pg.evaluate("() => !!window.__ipeLaudo"), 30)
        # um painel de botão escondido abre embaixo do "»": a Densidade
        pg.click("nav.barra .mais")
        pg.locator(".menu .menu-item:has-text('Densidade mamária')").click()
        assert _esperar(lambda: pg.locator(".menu.painel .painel-densidade").count() == 1, 10)
        caixa = pg.locator(".menu.painel").bounding_box()
        mais = pg.locator("nav.barra .mais").bounding_box()
        assert caixa["y"] >= mais["y"] + mais["height"] - 1 and caixa["x"] + caixa["width"] <= 1366 + 1
        # volta a tela grande: o "»" some e os botões voltam
        pg.keyboard.press("Escape")
        pg.set_viewport_size({"width": 1920, "height": 1080})
        assert _esperar(lambda: not pg.evaluate(ESTADO)["mais"], 10)
        assert pg.evaluate(ESTADO)["escondidos"] == 0
        b.close()
    assert not erros, erros
