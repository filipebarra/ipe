"""0.99.96: desempenho da carga no visualizador web — os quadros chegam em HTJ2K sem perda (menos bytes), o
cronômetro da carga mostra rede × decodificação, e reabrir o exame usa o cache do navegador (304)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_web_mpr import NX, NY, NZ, _esperar, servidor  # noqa: E402,F401  (fixture)
from test_web_tira import _abrir  # noqa: E402

from ipe.central import web as WEB  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from _web_ui import aba, botoes, espessura, ferramenta, icone, layout, menu, quadros  # noqa: E402,F401  # noqa: E402

pytestmark = pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")


def test_htj2k_cronometro_e_cache_do_navegador(servidor):
    pw = pytest.importorskip("playwright.sync_api")
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        ctx = b.new_context(viewport={"width": 1400, "height": 900})
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: erros.append(str(e)))
        _abrir(pg, servidor)
        assert _esperar(lambda: pg.evaluate("() => window.__ipeDisp.geral()")["porcentagem"] == 100, 60)
        r = pg.evaluate("() => window.__ipeCarga.resumo()")
        # todas as imagens vieram em HTJ2K, e pela rede veio menos que os pixels crus (40 × 64 × 64 × 2 bytes)
        assert r["sintaxes"].get("HTJ2K", 0) >= NZ, r
        assert 0 < r["bytesRede"] < (NZ + 1) * NX * NY * 2, r
        assert r["decodificacaoMediaMs"] >= 0 and r["mbPorSegundo"] > 0
        # o painel mostra o resumo
        pg.click(".rodape button:has-text('Carga')")
        assert _esperar(lambda: "HTJ2K" in pg.inner_text(".painel-carga") and "MB/s" in pg.inner_text(".painel-carga"))
        # reabrir o exame (na mesma aba, cache do Cornerstone esvaziado): o navegador revalida e recebe 304
        pg.evaluate("() => window.__ipeCs.cache.purgeCache()")
        icone(pg, 'Voltar à lista')
        pg.wait_for_selector("table.lista tbody tr")
        pg.locator("table.lista tbody tr").first.dblclick()
        pg.wait_for_selector(".quadro canvas")
        assert _esperar(lambda: pg.evaluate("() => window.__ipeDisp.geral()")["porcentagem"] == 100, 60)
        r2 = pg.evaluate("() => window.__ipeCarga.resumo()")
        assert r2["pedidos"] > 0 and r2["doCache"] >= r2["pedidos"] * 0.9, r2
        assert r2["bytesRede"] < r["bytesRede"] * 0.2, (r, r2)
        b.close()
    assert not erros, erros
