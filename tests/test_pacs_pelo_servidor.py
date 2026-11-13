"""0.100.37: o servidor central compartilha nós de busca com os clientes. O Ipê cliente e o Ipê Web buscam no PACS e
baixam pelo servidor; o exame entra no banco do servidor. O "PACS" é um nó de teste em loopback."""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_network import Node  # noqa: E402


@pytest.fixture()
def servidor(env, tmp_path, sample_dir):
    from PySide6.QtWidgets import QApplication

    from ipe.auth.backend import LocalAuth
    from ipe.central.server import CentralServer
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.network.service import NetworkService
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    repo.save_user({"username": "res", "full_name": "Residente", "role": "residente", "password": "resid123"})
    repo.save_user({"username": "med", "full_name": "Médica", "role": "medico", "password": "medic123"})
    pacs = Node(tmp_path / "pacs", "PACS")
    Importer(pacs.db, pacs.storage).import_paths([sample_dir])
    assert pacs.server.start()
    # o PACS conhece o servidor (C-MOVE não; o servidor baixa por C-GET)
    no = repo.save_node(pacs.as_node())
    st = Settings(paths.settings_file)
    net = NetworkService(db, repo, paths.storage, st)
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.settings, srv.net = st, net
    srv.start()
    srv.app, srv.no, srv.pacs, srv.repo_, srv.paths = app, no, pacs, repo, paths
    estudo = next(r for r in pacs.repo.search_studies() if r.accession == "ACC1001")
    srv.estudo = estudo.study_uid
    yield srv
    srv.stop()
    net.shutdown()
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
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def _esperar(srv, f, t=60.0):
    fim = time.time() + t
    while time.time() < fim:
        srv.app.processEvents()             # a resposta da fila de rede volta pela linha da tela
        if f():
            return True
        time.sleep(0.1)
    return f()


def _compartilhar(srv, sim=True):
    srv.repo_.save_node({"id": srv.no, "compartilhar_clientes": sim})


def test_no_so_aparece_quando_compartilhado(servidor):
    assert _api(servidor, "/api/web/pacs/nos")["nos"] == []
    _compartilhar(servidor)
    r = _api(servidor, "/api/web/pacs/nos")
    assert [n["nome"] for n in r["nos"]] == ["PACS"] and r["baixar"]
    assert set(r["nos"][0]) == {"id", "nome", "busca", "anteriores", "dicomweb"}    # sem endereço, AE nem senha


def test_navegador_busca_e_baixa_para_o_banco_do_servidor(servidor):
    _compartilhar(servidor)
    tok = _token(servidor, "res", "resid123")
    with pytest.raises(urllib.error.HTTPError) as e:
        _api(servidor, "/api/web/pacs/buscar", {"no": servidor.no, "filtros": {}}, tok)
    assert e.value.code == 400                                                  # sem filtro: não pesa no PACS
    r = _api(servidor, "/api/web/pacs/buscar", {"no": servidor.no, "filtros": {"accession": "ACC1001"}}, tok)
    assert len(r["estudos"]) == 1 and r["estudos"][0]["study_uid"] == servidor.estudo
    assert not r["estudos"][0]["no_servidor"]
    se = _api(servidor, "/api/web/pacs/series", {"no": servidor.no, "study": servidor.estudo}, tok)
    assert len(se["series"]) == 1 and se["series"][0]["num_images"] == 60
    with pytest.raises(urllib.error.HTTPError) as e:                           # o banco de outro: não
        _api(servidor, "/api/web/pacs/baixar", {"no": servidor.no, "study": servidor.estudo, "banco": ["med", ""]},
             tok)
    assert e.value.code == 403
    d = _api(servidor, "/api/web/pacs/baixar", {"no": servidor.no, "study": servidor.estudo, "rotulo": "TC",
                                                 "banco": ["res", ""]}, tok)["download"]
    assert _esperar(servidor, lambda: _api(servidor, "/api/web/pacs/downloads", tok=tok)["downloads"][0]["estado"]
                    in ("done", "error"))
    feito = _api(servidor, "/api/web/pacs/downloads", tok=tok)["downloads"][0]
    assert feito["id"] == d["id"] and feito["estado"] == "done", feito
    assert servidor.repo_.counts()["instances"] >= 60
    info = servidor.repo_.study_info(servidor.estudo)
    assert info is not None and info.get("dono") == "res"                      # no banco de quem pediu
    r = _api(servidor, "/api/web/pacs/buscar", {"no": servidor.no, "filtros": {"accession": "ACC1001"}}, tok)
    assert r["estudos"][0]["no_servidor"]
    # outro usuário não vê os downloads dele
    assert _api(servidor, "/api/web/pacs/downloads", tok=_token(servidor, "med", "medic123"))["downloads"] == []
    acoes = [a["action"] for a in servidor.repo_.access_log(limit=50)]
    assert "busca" in acoes and "baixar" in acoes


def test_sem_permissao_de_buscar(servidor):
    _compartilhar(servidor)
    roles = {"residente": ["view"]}
    servidor.repo_.set_app_setting("roles", roles)
    tok = _token(servidor, "res", "resid123")
    for rota in ("/api/web/pacs/nos",):
        with pytest.raises(urllib.error.HTTPError) as e:
            _api(servidor, rota, None, tok)
        assert e.value.code == 403


def test_cliente_busca_e_baixa_pelo_servidor(servidor, tmp_path):
    """O Ipê cliente: os nós do servidor entram na lista de busca, e o download vai para o servidor."""
    from ipe.central.client_repo import ClientRepository
    from ipe.central.remote import RemoteClient
    from ipe.core.config import Settings
    from ipe.db.repository import Repository
    from ipe.db.session import Database
    from ipe.network import nodes as NODES
    from ipe.network.service import NetworkService
    _compartilhar(servidor)
    cli = RemoteClient(f"http://127.0.0.1:{servidor.port}")
    cli.login("med", "medic123")
    cache = Database(tmp_path / "cache" / "cache.sqlite")
    repo = ClientRepository(Repository(cache), cli, tmp_path / "cache" / "Storage")
    assert repo.nodes(gerenciar=True) == []                                    # a configuração não mostra
    nos = [n for n in repo.nodes(only_active=True) if n["kind"] in NODES.CONSULTA]
    assert len(nos) == 1 and nos[0]["kind"] == "servidor" and nos[0]["id"] == -servidor.no
    assert repo.node(-servidor.no)["name"] == "PACS (pelo servidor)"
    assert NODES.search_nodes(repo) == nos and NODES.prior_candidates(repo) == nos
    net = NetworkService(cache, repo, tmp_path / "cache" / "Storage", Settings(tmp_path / "c.json"))
    try:
        assert net.identities_for(nos[0]) == []
        achou = {}
        net.search(nos, None, {"accession": "ACC1001"}, lambda r, e: achou.update(r=r, e=e))
        assert _esperar(servidor, lambda: "r" in achou)
        resultados, erros = achou["r"]
        assert not erros and [x["study_uid"] for x in resultados] == [servidor.estudo]
        assert resultados[0]["node_id"] == -servidor.no
        series = {}
        net.series(nos[0], None, servidor.estudo, lambda r, e: series.update(r=r))
        assert _esperar(servidor, lambda: "r" in series) and series["r"][0]["num_images"] == 60
        job = net.retrieve(nos[0], None, servidor.estudo, "TC pelo servidor")
        assert _esperar(servidor, lambda: not job.active, 90)
        assert job.status == "done", job.message
        assert "banco do servidor" in job.message
        assert servidor.repo_.study_info(servidor.estudo) is not None           # no servidor
        assert not repo.local.study_uids_present([servidor.estudo])             # e não no cache
    finally:
        net.shutdown()


def test_pelo_navegador(servidor):
    """Ipê Web: o botão "Buscar no PACS…" na lista, a busca, o download pelo servidor e abrir o exame baixado."""
    pw = pytest.importorskip("playwright.sync_api")
    srv = servidor
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1500, "height": 950})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(f"http://127.0.0.1:{srv.port}/web/")
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        pg.wait_for_selector("form.filtros")
        botao = pg.locator("form.filtros button:has-text('Buscar no PACS')")
        pg.wait_for_timeout(800)
        assert not botao.is_visible()                                  # nada compartilhado: sem o botão
        _compartilhar(srv)
        pg.reload()
        pg.wait_for_selector("form.filtros button:has-text('Buscar no PACS'):visible")
        botao.click()
        pg.wait_for_selector(".tela-pacs")
        pg.fill(".tela-pacs input[aria-label='Acesso']", "ACC1001")
        pg.click(".tela-pacs button.primario")
        pg.wait_for_selector(".lista-pacs tbody tr")
        assert pg.locator(".lista-pacs tbody tr").count() == 1
        pg.click(".lista-pacs button.baixar")
        assert _esperar(srv, lambda: pg.locator(".downloads-pacs .envio.done").count() == 1, 60), \
            pg.inner_text(".tela-pacs")
        assert srv.repo_.study_info(srv.estudo) is not None
        pg.click(".downloads-pacs button:has-text('Abrir o exame')")
        pg.wait_for_selector(".quadro canvas")
        b.close()
    assert not erros, erros
