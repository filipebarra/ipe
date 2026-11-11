"""0.100.9: enviar do visualizador web para um destino DICOM — o exame, séries ou a imagem do quadro ativo, pela
fila de envios do servidor (NetworkService), com o andamento, as medidas como GSPS junto e a permissão de enviar
(o residente não envia). O "PACS" é um nó de teste em loopback."""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from pydicom.uid import generate_uid

sys.path.insert(0, str(Path(__file__).parent))
from _web_ui import icone  # noqa: E402
from test_ko_gsps import _medida, _vol  # noqa: E402
from test_network import Node  # noqa: E402

from ipe.central import web as WEB  # noqa: E402


@pytest.fixture()
def servidor(env, tmp_path):
    from PySide6.QtWidgets import QApplication
    from test_registro_rigido import _serie
    from ipe.auth.backend import LocalAuth
    from ipe.central.server import CentralServer
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.network.service import NetworkService
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    estudo = generate_uid()
    serie = _serie(tmp_path / "a", _vol(), estudo, generate_uid(), "Ax T1", "20261101")
    Importer(db, paths.storage).import_paths([tmp_path / "a"])
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    repo.save_user({"username": "res", "full_name": "Residente", "role": "residente", "password": "resid123"})
    pacs = Node(tmp_path / "pacs", "PACS")
    assert pacs.server.start()
    no = repo.save_node(pacs.as_node())
    st = Settings(paths.settings_file)
    net = NetworkService(db, repo, paths.storage, st)
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.settings, srv.net = st, net
    srv.start()
    srv.app, srv.estudo, srv.serie, srv.no, srv.pacs, srv.repo_ = app, estudo, serie, no, pacs, repo
    yield srv
    srv.stop()
    pacs.close()


def _token(srv, u="admin", p="admin123"):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/login", method="POST",
                                 data=json.dumps({"username": u, "password": p}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())["token"]


def _api(srv, rota, corpo=None, tok=None):
    tok = tok or _token(srv)
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}{rota}", method="POST" if corpo is not None else "GET",
                                 data=json.dumps(corpo).encode() if corpo is not None else None,
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def _esperar(srv, f, t=30.0):
    fim = time.time() + t
    while time.time() < fim:
        srv.app.processEvents()             # a resposta da fila de rede volta pela linha da tela
        if f():
            return True
        time.sleep(0.1)
    return f()


def _no_pacs(srv):
    return sorted((s.modality, s.num_images) for s in srv.pacs.repo.series_for_study(srv.estudo))


def test_destinos_e_permissao(servidor):
    d = _api(servidor, "/api/web/destinos")
    assert d["fila"] and [x["nome"] for x in d["destinos"]] == ["PACS"]
    tok = _token(servidor, "res", "resid123")
    for rota, corpo in (("/api/web/destinos", None), ("/api/web/enviar", {"study": servidor.estudo, "destino": servidor.no})):
        with pytest.raises(urllib.error.HTTPError) as e:
            _api(servidor, rota, corpo, tok)
        assert e.value.code == 403


def test_envia_imagem_serie_e_medidas(servidor):
    srv = servidor
    insts = sorted(srv.repo_.instances_for_series(srv.serie), key=lambda i: i["instance_number"])
    # uma imagem
    r = _api(srv, "/api/web/enviar", {"study": srv.estudo, "destino": srv.no, "series": [srv.serie],
                                      "sops": [insts[2]["sop_uid"]], "objetos": False})
    assert r["ok"] and "1 imagem(ns)" in r["envios"][0]["rotulo"]
    assert _esperar(srv, lambda: _api(srv, "/api/web/envios")["envios"][0]["estado"] == "done")
    assert _esperar(srv, lambda: _no_pacs(srv) == [("MR", 1)]), _no_pacs(srv)
    # a série inteira, com as medidas como GSPS
    _medida(srv.repo_, srv.estudo, srv.serie, insts[3]["sop_uid"], "line", [(10, 10), (30, 30)])
    r = _api(srv, "/api/web/enviar", {"study": srv.estudo, "destino": srv.no, "series": [srv.serie], "objetos": True})
    assert r["objetos"] == 1
    assert _esperar(srv, lambda: all(e["estado"] == "done" for e in _api(srv, "/api/web/envios")["envios"]))
    assert _esperar(srv, lambda: _no_pacs(srv) == [("MR", len(insts)), ("PR", 1)]), _no_pacs(srv)
    lista = _api(srv, "/api/web/envios")["envios"]
    assert len(lista) == 2 and lista[0]["feitas"] == lista[0]["total"] == len(insts) + 1
    assert srv.repo_.access_log(limit=5, action="enviar", study_uid=srv.estudo)
    # os envios são de quem pediu
    assert _api(srv, "/api/web/envios", tok=_token(srv, "res", "resid123"))["envios"] == []
    # série de outro exame não vai
    with pytest.raises(urllib.error.HTTPError) as e:
        _api(srv, "/api/web/enviar", {"study": srv.estudo, "destino": srv.no, "series": ["1.2.3"]})
    assert e.value.code == 400


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_pelo_navegador(servidor):
    pw = pytest.importorskip("playwright.sync_api")
    srv = servidor
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        for usuario, senha, pode in (("res", "resid123", False), ("admin", "admin123", True)):
            pg = b.new_page(viewport={"width": 1500, "height": 950})
            pg.on("pageerror", lambda e: erros.append(str(e)))
            pg.goto(f"http://127.0.0.1:{srv.port}/web/")
            pg.fill("#usuario", usuario)
            pg.fill("#senha", senha)
            pg.click("button[type=submit]")
            pg.wait_for_selector("table.lista tbody tr")
            pg.locator("table.lista tbody tr").first.dblclick()
            pg.wait_for_selector(".quadro canvas")
            botao = pg.locator("nav.barra button[aria-label='Enviar a um destino DICOM']")
            assert botao.is_visible() == pode
            if not pode:
                pg.close()
                continue
            icone(pg, "Enviar a um destino DICOM")
            pg.wait_for_selector(".painel-envio")
            assert pg.locator(".painel-envio select[aria-label='Destino'] option").all_inner_texts()[0].startswith("PACS")
            # a série do quadro já vem marcada; mandar só a imagem do quadro
            assert pg.locator(".lista-series-envio input:checked").count() == 1
            pg.check(".painel-envio input[value='imagem']")
            pg.uncheck(".painel-envio input[type=checkbox]:not([value])")       # sem GSPS/KO
            pg.click(".painel-envio button.primario")
            pg.wait_for_selector(".painel-envio", state="detached")
            assert _esperar(srv, lambda: _no_pacs(srv) == [("MR", 1)]), _no_pacs(srv)
            assert _esperar(srv, lambda: "Envios" in (pg.inner_text(".rodape") or ""))
            pg.click(".rodape button:has-text('Envios')")
            assert _esperar(srv, lambda: pg.locator(".envios .envio.done").count() == 1, 15), pg.inner_text(".envios")
            assert "1/1" in pg.inner_text(".envios .envio.done")
            pg.close()
        b.close()
    assert not erros, erros
