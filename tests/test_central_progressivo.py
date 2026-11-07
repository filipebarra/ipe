"""0.99.85: no modo cliente, o exame abre com as primeiras imagens e o resto chega em segundo plano."""
import threading
import time

from PySide6.QtWidgets import QApplication

from test_central import central  # noqa: F401  (fixture)
from ipe.auth.backend import RemoteAuth
from ipe.central.client_repo import ClientRepository
from ipe.central.remote import RemoteClient
from ipe.core.config import Settings
from ipe.db.repository import Repository
from ipe.db.session import Database


def _cliente(srv, paths, tmp_path):
    client = RemoteClient(f"http://127.0.0.1:{srv.port}")
    auth = RemoteAuth(client)
    s = auth.login("admin", "admin123")
    cache_db = Database(tmp_path / "c" / "cache.sqlite")
    storage = tmp_path / "c" / "Storage"
    st = Settings(paths.settings_file)
    return ClientRepository(Repository(cache_db), client, storage, st), auth, s, cache_db, storage, st


def _esperar(cond, app=None, s=20.0):
    fim = time.monotonic() + s
    while time.monotonic() < fim:
        if app is not None:
            app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_so_o_exame_aberto_e_baixado_em_lotes(central, tmp_path, monkeypatch):  # noqa: F811
    paths, db, repo, srv = central
    cr, *_ = _cliente(srv, paths, tmp_path)
    uid = repo.find_study_uids(accession="ACC1001")[0]
    remotas = {s.series_uid: s.num_images for s in repo.series_for_study(uid)}
    monkeypatch.setattr(ClientRepository, "LOTE_IMAGENS", 2)
    lotes = []
    original = cr.local.db
    from ipe.importer import scanner
    imp = scanner.Importer.import_paths

    def contar(self, paths_, *a, **k):
        lotes.append(len(list(paths_)) if not isinstance(paths_, list) else len(paths_))
        return imp(self, paths_, *a, **k)
    monkeypatch.setattr(scanner.Importer, "import_paths", contar)
    primeiro = threading.Event()
    n = cr.download(uid, primeiro_lote=primeiro)
    assert primeiro.is_set() and n == sum(remotas.values())
    assert len(lotes) > 1                                   # chegou em mais de um lote
    assert lotes[0] == len(remotas)                         # o primeiro: uma imagem de cada série
    assert {s.series_uid: s.num_images for s in cr.local.series_for_study(uid)} == remotas
    assert len(cr.local.search_studies(limit=100)) == 1     # só o exame pedido
    assert original is cr.local.db


def test_abre_antes_de_terminar_e_vai_crescendo(central, tmp_path, monkeypatch):  # noqa: F811
    from ipe.ui.main_window import MainWindow
    paths, db, repo, srv = central
    app = QApplication.instance() or QApplication([])
    cr, auth, s, cache_db, storage, st = _cliente(srv, paths, tmp_path)
    uid = repo.find_study_uids(accession="ACC1001")[0]
    remotas = {x.series_uid: x.num_images for x in repo.series_for_study(uid)}
    # segura o download das séries depois das amostras, para ver o exame aberto pela metade
    solta = threading.Event()
    retrieve = cr.client.retrieve

    def devagar(study_uid, dest, series_uid=None, progress=None, sop_uid=None):
        if not sop_uid:
            solta.wait(20)
        return retrieve(study_uid, dest, series_uid, progress=progress, sop_uid=sop_uid)
    monkeypatch.setattr(cr.client, "retrieve", devagar)
    msgs = []
    cr.on_download_status = msgs.append
    w = MainWindow(paths, st, auth=auth, repo=cr, db=cache_db, storage=storage)
    w.start_session(s)
    w.show()
    t0 = time.monotonic()
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    assert time.monotonic() - t0 < 15
    tab = w.tabs.currentWidget()
    assert tab.study_uid == uid and cr.baixando(uid)
    parcial = {x.series_uid: x.num_images for x in cr.local.series_for_study(uid)}
    assert set(parcial) == set(remotas)                     # todas as séries já na tira
    assert sum(parcial.values()) < sum(remotas.values())    # mas ainda não todas as imagens
    w._vigiar_series()                                      # a vigia (de 3 em 3 s) vê o exame pela metade
    solta.set()
    assert _esperar(lambda: not cr.baixando(uid), app)
    w._vigiar_series()                                      # e depois completo: a aba acrescenta
    assert {x.series_uid: x.num_images for x in tab.series} == {
        k: v for k, v in remotas.items() if k in {x.series_uid for x in tab.series}}
    vp = next(v for v in tab.viewports if v.series_uid in remotas)
    assert len(vp.frames) == remotas[vp.series_uid]          # o quadro aberto cresceu
    assert any("Exame baixado" in m for m in msgs)
    w.close()
