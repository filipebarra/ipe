"""0.100.20: a lista de exames do navegador — filtros rápidos (período, modalidade, situação) e a prévia do exame
selecionado à direita (séries, IA, laudo, anteriores)."""
import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_web_achados import _api, servidor  # noqa: E402,F401
from test_web_mpr import _esperar  # noqa: E402

from ipe.central import web as WEB  # noqa: E402


def test_situacoes_e_previa_pela_api(servidor):
    srv = servidor
    d = _api(srv, "/api/web/lista/situacoes", {"studies": [srv.estudo, "1.2.3.nao.existe"]})
    assert d["estudos"][srv.estudo] == {"laudo": "", "achados": 1, "revisar": 1}
    rid = srv.repo_.save_report({"study_uid": srv.estudo, "title": "TC", "text": "Enfisema centrolobular leve.", "author": "admin"})
    assert _api(srv, "/api/web/lista/situacoes", {"studies": [srv.estudo]})["estudos"][srv.estudo]["laudo"] == "draft"
    p = _api(srv, f"/api/web/lista/previa?study={srv.estudo}")
    assert p["paciente"] and p["series"] and p["series"][0]["uid"] == srv.serie
    assert p["ia"]["contagem"]["sugerido"] == 1
    assert p["laudo"]["estado"] == "draft" and "Enfisema" in p["laudo"]["trecho"]
    srv.repo_.sign_report(rid, "Administrador")
    assert _api(srv, "/api/web/lista/situacoes", {"studies": [srv.estudo]})["estudos"][srv.estudo]["laudo"] == "final"


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_filtros_rapidos_e_previa_no_navegador(servidor):
    pw = pytest.importorskip("playwright.sync_api")
    srv = servidor
    srv.repo_.save_report({"study_uid": srv.estudo, "title": "TC", "text": "Enfisema centrolobular leve.", "author": "admin"})
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1500, "height": 900})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(f"http://127.0.0.1:{srv.port}/web/")
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        pg.wait_for_selector("table.lista tbody tr")
        # os selos chegam com a situação: IA para revisar e laudo em rascunho
        pg.wait_for_selector("table.lista tbody tr .selo-ia.revisar")
        assert pg.locator("table.lista tbody tr .selo-laudo.rascunho").count() == 1
        assert pg.inner_text(".contagem-lista").startswith("1 exame")
        # situação: assinado → nenhum; rascunho e IA para revisar → o exame
        sit = ".pilulas[aria-label='Situação'] button[data-valor='{}']"
        pg.click(sit.format("final"))
        assert _esperar(lambda: pg.locator("table.lista tbody tr").count() == 0)
        assert "Nenhum exame com esta situação" in pg.inner_text(".estado")
        pg.click(sit.format("ia"))
        assert _esperar(lambda: pg.locator("table.lista tbody tr").count() == 1)
        pg.click(sit.format(""))
        # período: Hoje esconde o exame (é de outro dia) e preenche as datas; Tudo traz de volta
        per = ".pilulas[aria-label='Período'] button[data-valor='{}']"
        pg.click(per.format("hoje"))
        assert _esperar(lambda: pg.locator("table.lista tbody tr").count() == 0)
        hoje = dt.date.today().isoformat()
        pg.click(per.format("outro"))
        assert pg.input_value(".outro-periodo input >> nth=0") == hoje
        pg.click(per.format("tudo"))
        assert _esperar(lambda: pg.locator("table.lista tbody tr").count() == 1)
        # modalidade
        pg.click(".pilulas[aria-label='Modalidade'] button[data-valor='MR']")
        assert _esperar(lambda: pg.locator("table.lista tbody tr").count() == 0)
        pg.click(".pilulas[aria-label='Modalidade'] button[data-valor='']")
        assert _esperar(lambda: pg.locator("table.lista tbody tr").count() == 1)
        # um clique seleciona e mostra a prévia; o botão abre
        assert not pg.locator(".previa").is_visible()
        pg.locator("table.lista tbody tr").first.click()
        pg.wait_for_selector(".previa .previa-series figure")
        t = pg.inner_text(".previa")
        assert "1 achado(s)" in t and "Rascunho" in t and "Enfisema centrolobular" in t
        assert pg.locator(".previa .previa-series .selo-ia").count() == 0 or True
        import os
        if os.environ.get("IPE_SHOT_DIR"):
            pg.wait_for_timeout(600)
            pg.screenshot(path=os.path.join(os.environ["IPE_SHOT_DIR"], "lista_nova.png"))
        pg.click(".previa button:has-text('Abrir o exame')")
        pg.wait_for_selector(".quadro canvas")
        # ao fechar, a lista volta com os filtros e o exame selecionado na prévia
        pg.click("header button.sair")
        pg.wait_for_selector(".previa .previa-series figure")
        b.close()
    assert not erros, erros
