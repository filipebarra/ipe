"""Fase 8 — servidor central (login, RPC, DICOMweb) e cliente com cache local."""
import base64
import json
import urllib.request

import pytest
from PySide6.QtWidgets import QApplication

from ipe.auth.backend import LocalAuth, RemoteAuth, AuthError
from ipe.central.client_repo import ClientRepository
from ipe.central.remote import RemoteClient, RemoteError, Unauthorized
from ipe.central.server import CentralServer
from ipe.core.config import Settings
from ipe.db.repository import Repository
from ipe.db.session import Database
from ipe.importer.scanner import Importer
from test_measure_tools import make_dynamic


@pytest.fixture()
def central(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    auth = LocalAuth(repo)
    auth.create_first_admin("admin", "Administrador", "admin123")
    repo.save_user({"username": "res", "full_name": "Residente", "role": "residente", "password": "resid123"})
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    yield paths, db, repo, srv
    srv.stop()


def _client(srv, user="admin", pw="admin123"):
    c = RemoteClient(f"http://127.0.0.1:{srv.port}")
    c.login(user, pw)
    return c


def test_server_rpc_and_dicomweb(central, tmp_path):
    paths, db, repo, srv = central
    c = RemoteClient(f"127.0.0.1:{srv.port}")
    assert c.ping()["app"] == "Ipê"
    with pytest.raises(Unauthorized):
        c.rpc("counts")
    with pytest.raises(Unauthorized):
        c.login("admin", "errada")
    c.login("admin", "admin123")
    rows = c.rpc("search_studies")
    assert rows and type(rows[0]).__name__ == "StudyRow"
    uid = repo.find_study_uids(accession="ACC1001")[0]
    ss = c.rpc("series_for_study", uid)
    assert ss[0].thumbnail is None or isinstance(ss[0].thumbnail, bytes)
    assert isinstance(c.rpc("key_image_set", uid), set)
    # permissões conferidas no servidor
    r = _client(srv, "res", "resid123")
    with pytest.raises(RemoteError, match="perfil"):
        r.rpc("users")
    with pytest.raises(RemoteError):
        r.rpc("delete_study", uid)
    with pytest.raises(RemoteError, match="não permitido"):
        r.rpc("save_node", {})
    r.rpc("audit", "abrir", "teste", study_uid=uid)
    assert repo.access_log(user="res", action="abrir")[0]["study_uid"] == uid
    # QIDO
    st = c.qido("/studies")
    assert any(s["0020000D"]["Value"][0] == uid for s in st)
    se = c.qido(f"/studies/{uid}/series")
    se_uid = se[0]["0020000E"]["Value"][0]
    inst = c.qido(f"/studies/{uid}/series/{se_uid}/instances")
    assert len(inst) == len(repo.instances_for_series(se_uid))
    # Basic auth (outros visualizadores DICOMweb)
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/dicomweb/studies",
                                 headers={"Authorization": "Basic " + base64.b64encode(b"admin:admin123").decode()})
    assert json.loads(urllib.request.urlopen(req).read())
    # WADO
    files = c.retrieve(uid, tmp_path / "wado")
    assert len(files) == sum(s.num_images for s in ss)
    import pydicom
    assert pydicom.dcmread(files[0]).StudyInstanceUID == uid
    # STOW
    new_uid = make_dynamic(tmp_path / "dyn", one_series=True)
    before = repo.study_uids_present([new_uid])
    res = c.store(sorted((tmp_path / "dyn").rglob("*.dcm")))
    assert not before and res["sent"] == 15 and new_uid in res["studies"]
    assert repo.study_uids_present([new_uid])
    with pytest.raises(RemoteError):          # residente não importa por padrão? (pode) -> perm import
        _client(srv, "res", "resid123").rpc("set_app_setting", "roles", {})


def test_client_repository_cache(central, tmp_path):
    paths, db, repo, srv = central
    c = _client(srv)
    cache_db = Database(tmp_path / "cache" / "cache.sqlite")
    storage = tmp_path / "cache" / "Storage"
    st = Settings(paths.settings_file)
    cr = ClientRepository(Repository(cache_db), c, storage, st)
    uid = repo.find_study_uids(accession="ACC1001")[0]
    assert not cr.is_cached(uid)
    assert cr.series_for_study(uid)                       # do servidor
    assert cr.missing_series(uid)
    assert cr.ensure_local(uid)
    assert cr.is_cached(uid) and not cr.missing_series(uid)
    se = cr.series_for_study(uid)[0]
    inst = cr.instances_for_series(se.series_uid)
    assert inst and str(storage) in inst[0]["path"]      # arquivos do cache
    # imagem-chave e medida ficam no servidor
    assert cr.toggle_key_image(uid, se.series_uid, inst[0]["sop_uid"], 0)
    assert repo.key_image_set(uid) == {(inst[0]["sop_uid"], 0)}
    k = cr.key_images(uid)
    assert k and str(storage) in k[0]["path"]
    aid = cr.save_annotation(db_id=None, study_uid=uid, series_uid=se.series_uid, sop_uid=inst[0]["sop_uid"],
                             frame_index=0, kind="line", data="{}")
    assert repo.annotations_for_series([se.series_uid])[0]["id"] == aid
    # algo novo no cache sobe para o servidor
    new_uid = make_dynamic(tmp_path / "dyn", one_series=True)
    Importer(cache_db, storage).import_paths([tmp_path / "dyn"])
    cr.upload_study(new_uid, wait=True)
    assert repo.study_uids_present([new_uid]) and len(repo.sop_uids_for_study(new_uid)) == 15
    # limite do cache
    st.set("central.cache_gb", 0.000001)
    removed = cr.evict(keep={new_uid})
    assert uid in removed and not cr.is_cached(uid) and cr.is_cached(new_uid)
    # apagar (admin) apaga no servidor e no cache
    cr.delete_study(new_uid)
    assert not repo.study_uids_present([new_uid]) and not cr.is_cached(new_uid)


def test_remote_auth_prefs(central):
    paths, db, repo, srv = central
    auth = RemoteAuth(RemoteClient(f"http://127.0.0.1:{srv.port}"))
    with pytest.raises(AuthError):
        auth.login("res", "x")
    s = auth.login("res", "resid123")
    assert s.role == "residente" and s.can("view") and not s.can("delete") and s.token
    auth.save_prefs(s, {"viewer": {"mouse": {"right": "pan"}}})
    uid = repo.user_by_name("res")["id"]
    assert repo.user_prefs(uid)["viewer"]["mouse"]["right"] == "pan"
    assert auth.prefs(s)["viewer"]["mouse"]["right"] == "pan"
    auth.change_password(s, "resid123", "novasenha")
    with pytest.raises(AuthError):
        auth.change_password(s, "errada", "outra123")
    assert auth.login("res", "novasenha").username == "res"


def test_gui_client_mode(central, tmp_path):
    from ipe.ui.main_window import MainWindow
    from ipe.auth import session as S
    paths, db, repo, srv = central
    app = QApplication.instance() or QApplication([])
    client = RemoteClient(f"http://127.0.0.1:{srv.port}")
    auth = RemoteAuth(client)
    s = auth.login("admin", "admin123")
    cache_db = Database(tmp_path / "c" / "cache.sqlite")
    storage = tmp_path / "c" / "Storage"
    st = Settings(paths.settings_file)
    cr = ClientRepository(Repository(cache_db), client, storage, st)
    w = MainWindow(paths, st, auth=auth, repo=cr, db=cache_db, storage=storage)
    w.start_session(s)
    w.show()
    w.browser.refresh()
    assert w.browser.model.rowCount() >= 3                 # exames do servidor
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    tab = w.tabs.currentWidget()
    uid = repo.find_study_uids(accession="ACC1001")[0]
    assert tab.study_uid == uid and cr.is_cached(uid)
    vp = tab.viewports[0]
    tab._activate(vp)
    tab.toggle_key_image()
    assert repo.key_image_set(uid)                           # marcou no servidor
    assert any(e["action"] == "abrir" and e["user"] == "admin" for e in repo.access_log())
    w.close()


def test_server_mode_in_gui_and_dialog(env, sample_dir):
    from ipe.ui.central_dialog import CentralDialog
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    st = Settings(paths.settings_file)
    w = MainWindow(paths, st, repo=repo, db=db)
    dlg = CentralDialog(st, w)
    dlg.r_server.setChecked(True)
    dlg.port.setValue(0 or 18043)
    dlg._ok()
    assert st.get("central.mode") == "server"
    w.start_central_server()
    assert w.central is not None and w.central.running
    LocalAuth(repo).create_first_admin("admin", "A", "admin123")
    c = _client(w.central)
    assert c.rpc("counts")["studies"] == 0
    dlg2 = CentralDialog(st, w)
    dlg2.url.setText(f"http://127.0.0.1:{w.central.port}")
    dlg2.r_client.setChecked(True)
    assert dlg2.test() and "OK" in dlg2.test_label.text()
    st.set("central.mode", "local")
    w.start_central_server()
    assert w.central is None
    w.close()


def test_cli_parser():
    from ipe.__main__ import _parser
    a = _parser().parse_args(["server", "--port", "9000", "--no-dicom"])
    assert a.cmd == "server" and a.port == 9000 and a.no_dicom
