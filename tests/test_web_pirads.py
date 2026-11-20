"""0.100.79: o PI-RADS no Ipê Web — o botão só na RM de próstata, o toque no mapa cria a lesão no setor, as
pontuações dão a categoria (calculada pelo servidor), o volume e a densidade do PSA, mandar ao laudo e gravar o SR."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_pirads import _exame_mr  # noqa: E402
from test_web_laudo import _entrar  # noqa: E402,F401
from test_web_mpr import _esperar, servidor  # noqa: E402,F401  (fixture)

from ipe.central import web as WEB  # noqa: E402
from ipe.reporting import pirads as P  # noqa: E402
from ipe.reporting import pirads_saida as PS  # noqa: E402


def _abrir(pg, srv, texto):
    pg.goto(f"http://127.0.0.1:{srv.port}/web/")
    pg.wait_for_selector("#usuario, table.lista tbody tr")
    if pg.locator("#usuario").count():                    # a sessão da aba já pode estar aberta
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
    pg.wait_for_selector("table.lista tbody tr")
    pg.locator("table.lista tbody tr", has_text=texto).first.dblclick()
    pg.wait_for_selector(".quadro canvas")


def _botao(pg):
    """O botão PI-RADS (pode estar no "»" quando a barra não cabe)."""
    pg.locator("nav.barra button[aria-label='PI-RADS (RM de próstata)']").evaluate("b => b.click()")


def _campo(pg, rotulo):
    return pg.locator(f"dialog.pirads-janela .pir-campo:has(> span:text-is('{rotulo}'))").locator("select, input").first


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_pirads_no_navegador(servidor, env, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    srv, repo = servidor, servidor.repo
    uid, _s, _g, _f = _exame_mr(env, tmp_path)
    erros = []
    foto = os.environ.get("IPE_PIRADS_FOTO")
    jan = "dialog.pirads-janela"
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        # na TC de tórax o botão não aparece
        _abrir(pg, srv, "TC TORAX")
        assert pg.locator("nav.barra button[aria-label='PI-RADS (RM de próstata)']").is_hidden()
        _abrir(pg, srv, "PROSTATA")
        _botao(pg)
        pg.wait_for_selector(f"{jan} canvas.pir-mapa")
        assert pg.locator(f"{jan} .pir-pesquisa").is_hidden()
        # o toque no setor (sem lesão) cria a lesão nele
        x, y = P.centro_do_setor("medio_PZpl_D")
        cv = pg.locator(f"{jan} canvas.pir-mapa").bounding_box()
        pg.mouse.click(cv["x"] + x * cv["width"], cv["y"] + y * cv["height"])
        assert _esperar(lambda: (P.ler(repo, uid) or {}).get("lesoes"))
        assert P.ler(repo, uid)["lesoes"][0]["setores"] == ["medio_PZpl_D"]
        assert P.ler(repo, uid)["lesoes"][0]["zona"] == "PZ"
        _campo(pg, "Difusão").select_option("3")
        assert _esperar(lambda: pg.inner_text(f"{jan} .pir-cat-calc") == "PI-RADS 3")
        _campo(pg, "DCE").select_option("+")
        assert _esperar(lambda: pg.inner_text(f"{jan} .pir-cat-calc") == "PI-RADS 4")
        _campo(pg, "Maior diâmetro (mm)").fill("12")
        _campo(pg, "Maior diâmetro (mm)").dispatch_event("change")
        _campo(pg, "PSA (ng/mL)").fill("6,5")
        _campo(pg, "PSA (ng/mL)").dispatch_event("change")
        for rot, v in (("AP", "40"), ("Transverso", "45"), ("Craniocaudal", "35")):
            _campo(pg, rot).fill(v)
            _campo(pg, rot).dispatch_event("change")
        if not _esperar(lambda: "Densidade do PSA: 0,20" in pg.inner_text(f"{jan} .pir-volume")):
            pg.screenshot(path="/tmp/claude-0/-home-claude/17517496-92d1-5d02-96c2-645763e6bf90/scratchpad/pir_falha.png")
            raise AssertionError(pg.inner_text(f"{jan} .pir-volume") + " | " + str(P.ler(repo, uid)))
        d = P.calcular(P.ler(repo, uid))
        assert d["geral"] == "4" and d["psa"] == 6.5 and d["volume_ml"] == pytest.approx(32.8, abs=0.1)
        assert "PI-RADS geral: 4" in pg.inner_text(f"{jan} .pir-geral")
        if foto:
            pg.screenshot(path=foto + ".png")
        # para o laudo
        pg.click(f"{jan} button:has-text('Mandar ao laudo')")
        pg.wait_for_selector("aside.laudo textarea.texto-laudo")
        assert _esperar(lambda: "PI-RADS 4: probabilidade alta" in pg.input_value("aside.laudo textarea.texto-laudo"))
        # e o SR no exame
        pg.click(f"{jan} button:has-text('Gravar no exame (SR e mapa)')")
        assert _esperar(lambda: "Gravado no exame" in pg.inner_text(f"{jan} .esq-msg"))
        assert PS.DESCRICAO in [s.description for s in repo.series_for_study(uid, True)]
        # sugestão de pesquisa: a faixa vermelha
        P.aplicar_candidatos(repo, uid, [{"zona": "TZ", "setores": ["base_TZa_E"], "probabilidade": 0.5}])
        pg.click(f"{jan} button:has-text('Fechar')")
        _botao(pg)
        pg.wait_for_selector(f"{jan} .pir-pesquisa:visible")
        assert "a conferir" in pg.inner_text(f"{jan} .pir-pesquisa")
        assert pg.locator(f"{jan} .pir-tabela tbody tr").count() == 2
        b.close()
    assert not erros, erros
