"""0.100.108: link de exame do Ipê Web — abre só aquele exame, sem senha, com as permissões escolhidas."""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_pacs_pelo_servidor import _esperar, servidor  # noqa: E402,F401

from ipe.central import links_exame as LE  # noqa: E402
from ipe.importer.scanner import Importer  # noqa: E402


def _req(srv, caminho, corpo=None, tok=None, metodo=None):
    h = {"Content-Type": "application/json", "X-Ipe-Web": "1"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    r = urllib.request.Request(f"http://127.0.0.1:{srv.port}{caminho}", headers=h,
                               data=None if corpo is None else json.dumps(corpo).encode(),
                               method=metodo or ("GET" if corpo is None else "POST"))
    return json.loads(urllib.request.urlopen(r).read() or b"null")


def _codigo(srv, caminho, corpo=None, tok=None):
    try:
        _req(srv, caminho, corpo, tok)
        return 200
    except urllib.error.HTTPError as e:
        return e.code


@pytest.fixture()
def dois_exames(servidor, sample_dir):
    srv = servidor
    Importer(srv.db, srv.paths.storage).import_paths([sample_dir])
    rows = srv.repo_.search_studies(limit=10)
    assert len(rows) >= 2
    return srv, rows[0].study_uid, rows[1].study_uid


def test_o_link_so_ve_o_exame_dele(dois_exames):
    srv, uid, outro = dois_exames
    tok, link = LE.criar(srv.repo_, uid, ["ia"], 24, "Dr. Teste", "admin")
    assert "hash" not in link and link["ativo"] and link["perms"] == ["ia"]
    assert tok not in json.dumps(srv.repo_.get_app_setting(LE.CHAVE))       # o servidor guarda só o hash
    d = _req(srv, "/api/link/entrar", {"token": tok})
    assert d["study"] == uid and "ai" in d["perms"] and "send" not in d["perms"]
    t = d["token"]
    # o exame do link: sim
    assert _codigo(srv, f"/dicomweb/studies/{uid}/series", tok=t) == 200
    assert _codigo(srv, f"/dicomweb/studies?StudyInstanceUID={uid}", tok=t) == 200
    assert _codigo(srv, f"/api/web/ia?study={uid}", tok=t) in (200, 503)      # 503: este servidor de teste não tem IA
    se = srv.repo_.series_for_study(uid)[0].series_uid
    assert _codigo(srv, f"/dicomweb/studies/{uid}/series/{se}/metadata", tok=t) == 200
    # outro exame, a lista, o banco, o RPC, o que não foi liberado: não
    assert _codigo(srv, f"/dicomweb/studies/{outro}/series", tok=t) == 403
    assert _codigo(srv, "/dicomweb/studies", tok=t) == 403
    outra_serie = srv.repo_.series_for_study(outro)[0].series_uid
    assert _codigo(srv, f"/dicomweb/studies/{uid}/series/{outra_serie}/metadata", tok=t) == 403
    assert _codigo(srv, f"/api/web/ia?study={outro}", tok=t) == 403
    assert _codigo(srv, "/api/web/lista/situacoes", tok=t) == 403
    assert _codigo(srv, "/api/rpc", {"method": "search_studies", "args": []}, tok=t) == 403
    assert _codigo(srv, "/api/web/enviar", {"study": uid, "destino": 1}, tok=t) == 403     # sem "enviar"
    assert _codigo(srv, "/api/web/anexos", {"study": uid, "arquivos": []}, tok=t) == 403    # sem "anexar"
    assert _codigo(srv, "/api/web/pacs/buscar", {"no": 1, "filtros": {}}, tok=t) == 403
    # revogado: cai na hora
    LE.revogar(srv.repo_, link["id"], "admin")
    assert _codigo(srv, f"/dicomweb/studies/{uid}/series", tok=t) == 401
    assert _codigo(srv, "/api/link/entrar", {"token": tok}) == 403
    acoes = [a["action"] for a in srv.repo_.access_log(limit=50)]
    assert {"link_exame_criado", "link_exame_usado", "link_exame_revogado", "link_exame_negado"} <= set(acoes)


def test_link_vencido_e_token_errado(dois_exames, monkeypatch):
    srv, uid, _outro = dois_exames
    tok, _link = LE.criar(srv.repo_, uid, [], 1, "", "admin")
    assert _codigo(srv, "/api/link/entrar", {"token": "x" * 43}) == 403
    agora = time.time()
    monkeypatch.setattr(LE.time, "time", lambda: agora + 2 * 3600)
    assert _codigo(srv, "/api/link/entrar", {"token": tok}) == 403


def test_criar_pelo_rpc_do_cliente(dois_exames):
    srv, uid, _outro = dois_exames
    from ipe.auth.session import UserSession
    admin = UserSession(username="admin", role="admin")
    r = srv.rpc(admin, "links_exame_criar", [uid], {"perms": ["anexar", "xyz"], "horas": 72, "rotulo": "Cirurgião"}, "")
    assert r["caminho"] == f"/web/#/link/{r['token']}" and r["link"]["perms"] == ["anexar"]
    assert [x["id"] for x in srv.rpc(admin, "links_exame_listar", [uid], {}, "")] == [r["link"]["id"]]
    assert srv.rpc(admin, "links_exame_revogar", [r["link"]["id"]], {}, "")
    sem = UserSession(username="res", role="residente", perms={"view"})       # sem "export": não cria
    with pytest.raises(PermissionError):
        srv.rpc(sem, "links_exame_criar", [uid], {}, "")


def test_navegador_abre_so_o_exame(dois_exames):
    pw = pytest.importorskip("playwright.sync_api")
    srv, uid, outro = dois_exames
    tok, _link = LE.criar(srv.repo_, uid, ["enviar"], 24, "Dr. Teste", "admin")
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(f"http://127.0.0.1:{srv.port}/web/#/link/{tok}")
        pg.wait_for_selector(".quadro canvas")                    # sem tela de senha
        pg.wait_for_timeout(1500)
        assert not erros, erros
        assert pg.locator("#senha").count() == 0
        h = pg.evaluate("location.hash")
        assert h == f"#/exame/{uid}" and tok not in pg.evaluate("location.href")
        pg.evaluate(f"location.hash = '#/exame/{outro}'")          # tentar outro exame: volta ao do link
        assert _esperar(srv, lambda: pg.evaluate("location.hash") == f"#/exame/{uid}", 10)
        pg.evaluate("location.hash = '#/lista'")
        assert _esperar(srv, lambda: pg.evaluate("location.hash") == f"#/exame/{uid}", 10)
        pg.wait_for_selector(".quadro canvas")
        pg.click("header button.sair")                             # sair: fim, sem lista
        pg.wait_for_selector(".link-invalido")
        pg.goto(f"http://127.0.0.1:{srv.port}/web/#/link/{'y' * 43}")
        pg.wait_for_selector(".link-invalido")
        b.close()
    assert not erros, erros


def test_janela_do_link(env, sample_dir):
    """A janela do botão direito: cria, copia, lista e revoga."""
    from types import SimpleNamespace

    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.ui.link_exame_dialogo import Fonte, LinkExameDialog
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    uid = repo.search_studies(limit=1)[0].study_uid
    assert Fonte(repo).disponivel()                                  # sem servidor: explica
    fonte = Fonte(repo, SimpleNamespace(scheme="https", port=8053))
    assert fonte.disponivel() == ""
    d = LinkExameDialog(fonte, uid, "EXEMPLO")
    d.e_rotulo.setText("Cirurgião")
    d.k_perm["ia"].setChecked(True)
    d.criar()
    assert d.e_link.text().startswith("https://") and "/web/#/link/" in d.e_link.text()
    assert app.clipboard().text() == d.e_link.text()
    assert d.tabela.rowCount() == 1 and d.tabela.item(0, 0).text() == "Cirurgião"
    d.tabela.selectRow(0)
    orig = QMessageBox.question
    QMessageBox.question = lambda *a, **k: QMessageBox.Yes
    try:
        d.revogar()
    finally:
        QMessageBox.question = orig
    assert not LE.listar(repo, uid)[0]["ativo"]
    d.close()
