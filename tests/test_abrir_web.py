"""0.100.103: abrir um exame no Ipê Web por chamada externa — #/abrir?acesso=… ou #/abrir?id=…&data=…&mod=…; o que
não está no servidor vem do PACS (pelos nós compartilhados) e abre quando chega. O login continua obrigatório."""
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_pacs_pelo_servidor import _api, _compartilhar, _esperar, _token, servidor  # noqa: E402,F401

from ipe.central import abrir_web as AW  # noqa: E402


def test_criterios():
    assert AW.criterios({"acesso": " 123 "})["acesso"] == "123"
    k = AW.criterios({"id": "9", "data": "2026-11-23", "mod": "mr"})
    assert k["data"] == "20261123" and k["mod"] == "MR"
    assert AW.criterios({"id": "9", "data": "23/11/2026"})["data"] == "20261123"
    assert AW.criterios({"AccessionNumber": "77"})["acesso"] == "77"
    with pytest.raises(ValueError):
        AW.criterios({"data": "20261123"})
    with pytest.raises(ValueError):
        AW.criterios({"id": "9", "data": "ontem"})


def test_procura_no_servidor_e_no_pacs(servidor):
    srv = servidor
    est = next(r for r in srv.pacs.repo.search_studies() if r.study_uid == srv.estudo)
    tok = _token(srv, "res", "resid123")
    r = _api(srv, "/api/web/abrir", {"acesso": "ACC1001"}, tok)
    assert r["servidor"] == [] and r["pacs"] == []                    # nada compartilhado ainda
    _compartilhar(srv)
    r = _api(srv, "/api/web/abrir", {"acesso": "ACC1001"}, tok)
    assert [e["study_uid"] for e in r["pacs"]] == [srv.estudo] and r["pacs"][0]["no"] == srv.no and r["baixar"]
    r = _api(srv, "/api/web/abrir", {"id": est.patient_id, "data": est.study_date, "mod": "CT"}, tok)
    assert [e["study_uid"] for e in r["pacs"]] == [srv.estudo]
    r = _api(srv, "/api/web/abrir", {"id": est.patient_id, "data": est.study_date, "mod": "MG"}, tok)
    assert r["pacs"] and all("MG" in e["modalities"] for e in r["pacs"])      # a mamografia da mesma paciente
    r = _api(srv, "/api/web/abrir", {"id": est.patient_id, "data": est.study_date, "mod": "XA"}, tok)
    assert r["pacs"] == []
    with pytest.raises(urllib.error.HTTPError) as e:
        _api(srv, "/api/web/abrir", {"mod": "CT"}, tok)
    assert e.value.code == 400


def test_link_externo_baixa_e_abre(servidor):
    pw = pytest.importorskip("playwright.sync_api")
    srv = servidor
    _compartilhar(srv)
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(f"http://127.0.0.1:{srv.port}/web/#/abrir?acesso=ACC1001")
        pg.fill("#usuario", "admin")                                       # o login continua obrigatório
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        pg.wait_for_selector(".tela-abrir")
        assert _esperar(srv, lambda: "#/exame/" in pg.evaluate("location.hash"), 90), pg.inner_text("body")
        assert srv.estudo in pg.url
        pg.wait_for_selector(".quadro canvas")
        assert srv.repo_.study_info(srv.estudo) is not None
        # de novo: agora está no servidor e abre direto
        pg.goto(f"http://127.0.0.1:{srv.port}/web/#/lista")
        pg.goto(f"http://127.0.0.1:{srv.port}/web/#/abrir?acesso=ACC1001")
        assert _esperar(srv, lambda: "#/exame/" in pg.evaluate("location.hash"), 30)
        pg.wait_for_selector(".quadro canvas")
        # não achou: avisa
        pg.goto(f"http://127.0.0.1:{srv.port}/web/#/abrir?acesso=NAOEXISTE")
        assert _esperar(srv, lambda: "Nenhum exame" in pg.inner_text("body"), 40), pg.inner_text("body")[:600]
        b.close()
    assert not erros, erros
