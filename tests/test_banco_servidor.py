"""0.99.28: banco pessoal no servidor ou neste computador (etapa 4 do plano do modo de uso).

Pedido dele: no modo servidor, o banco pessoal fica no computador da pessoa (sem internet/VPN, banco de
casos) **ou** no servidor — as duas opções. E as migrações: o banco de um computador que passou a ser
cliente vai para o servidor; trocar de modo não perde nada. Laudos, medidas e anotações acompanham o exame.
"""
from _menus import submenu, todas  # noqa: F401
import pytest
from PySide6.QtWidgets import QApplication

from ipe.auth import modo as MODO
from ipe.auth import session as S
from ipe.auth.backend import LocalAuth
from ipe.central import transferir as T
from ipe.central.client_repo import ClientRepository
from ipe.central.remote import RemoteClient, RemoteError
from ipe.central.server import CentralServer
from ipe.db import pacote as P
from ipe.db.repository import Repository
from ipe.db.session import Database
from ipe.importer.scanner import Importer

SENHA = "uma senha comprida"


@pytest.fixture(autouse=True)
def _sessao_volta():
    antes = S.get()
    yield
    S.set_current(antes)


@pytest.fixture()
def grupo(env, sample_dir):
    """Servidor com os exames de exemplo (compartilhados) e três usuários."""
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    LocalAuth(repo).create_first_admin("adm", "Administrador", SENHA)
    for n in ("ana", "bia"):
        repo.save_user({"username": n, "full_name": n.title(), "role": "medico", "password": SENHA})
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    yield paths, db, repo, srv
    srv.stop()


def _cli(srv, nome):
    c = RemoteClient(f"http://127.0.0.1:{srv.port}")
    c.login(nome, SENHA)
    return c


def _anotar(repo, uid):
    se = repo.series_for_study(uid)[0]
    sop = repo.instances_for_series(se.series_uid)[0]["sop_uid"]
    repo.save_report({"study_uid": uid, "title": "TC", "text": "Laudo de teste", "author": "ana"})
    repo.save_annotation(db_id=None, study_uid=uid, series_uid=se.series_uid, sop_uid=sop, frame_index=0,
                         kind="ruler", data='{"p": [1, 2]}')
    repo.toggle_key_image(uid, se.series_uid, sop, 0)
    return se.series_uid, sop


# ------------------------------------------------------------------ pacote do exame
def test_pacote_leva_laudo_medida_e_imagem_chave_sem_duplicar(env, sample_dir, tmp_path):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    uid = repo.search_studies(banco="todos")[0].study_uid
    _anotar(repo, uid)
    repo.set_study_scope([uid], "ana", "bia")
    pac = P.exportar(db, uid)
    assert pac["dono"] == "ana" and len(pac["report"]) == 1 and len(pac["annotation"]) == 1
    outro_db = Database(tmp_path / "outro.sqlite")
    outro = Repository(outro_db)
    Importer(outro_db, tmp_path / "st").import_paths([sample_dir])
    assert P.importar(outro_db, pac) == {"key_image": 1, "annotation": 1, "report": 1}
    assert P.importar(outro_db, pac) == {}                       # de novo: nada duplica
    assert outro.study_info(uid)["dono"] == "ana" and outro.reports(uid)[0]["text"] == "Laudo de teste"
    outro_db.close()


# ------------------------------------------------------------------ regras no servidor
def test_servidor_nao_entrega_exame_do_banco_de_outro(grupo, tmp_path):
    _p, _db, repo, srv = grupo
    uid = repo.search_studies(banco="todos")[0].study_uid
    repo.set_study_scope([uid], "ana")
    ana, bia, adm = _cli(srv, "ana"), _cli(srv, "bia"), _cli(srv, "adm")
    assert ana.rpc("study_info", uid)["dono"] == "ana"
    with pytest.raises(RemoteError, match="banco pessoal"):
        bia.rpc("study_info", uid)
    with pytest.raises(RemoteError, match="banco pessoal"):
        bia.rpc("reports", uid)
    with pytest.raises(RemoteError):                                # WADO também
        bia.retrieve(uid, tmp_path / "x")
    assert uid not in {r.study_uid for r in bia.rpc("search_studies", banco="todos")}   # "todos" não vale
    assert uid not in {s["0020000D"]["Value"][0] for s in bia.qido("/studies")}         # QIDO idem
    assert adm.rpc("study_info", uid) is not None                   # o administrador vê
    assert uid in {r.study_uid for r in adm.rpc("search_studies", banco="usuario:ana")}
    # mudar de banco pelo servidor: as regras do botão direito
    outro = repo.search_studies(banco="todos")[1].study_uid
    assert bia.rpc("set_study_scope", [uid], "") == 0               # não mexe no da Ana
    assert bia.rpc("set_study_scope", [outro], "bia") == 0          # tirar do compartilhado pede configurar
    with pytest.raises(RemoteError, match="administrador"):
        bia.rpc("set_study_scope", [outro], "ana")
    assert ana.rpc("set_study_scope", [uid], "ana", "bia") == 1     # a Ana compartilha com a Bia
    assert bia.rpc("study_info", uid) is not None
    assert adm.rpc("donos_de_exames") == {"ana": 1}
    assert "bia" in bia.rpc("nomes_de_usuarios")                    # sem a permissão de usuários
    with pytest.raises(RemoteError, match="dono"):
        bia.rpc("retirar_do_servidor", uid)


# ------------------------------------------------------------------ servidor ⇄ este computador
def test_trazer_e_enviar(grupo, tmp_path):
    paths, _db, repo, srv = grupo
    uid = repo.search_studies(banco="todos")[0].study_uid
    _anotar(repo, uid)
    repo.set_study_scope([uid], "ana")
    ana = _cli(srv, "ana")
    cache_db = Database(tmp_path / "cache.sqlite")
    cliente = ClientRepository(Repository(cache_db), ana, tmp_path / "cache")
    aqui_db = Database(tmp_path / "aqui.sqlite")
    aqui = Repository(aqui_db)
    # copiar para este computador: imagens + laudo + medida, no banco pessoal da Ana
    r = T.trazer(cliente, [uid], aqui_db, tmp_path / "aqui", "ana")
    assert r.exames == 1 and r.imagens > 0 and r.dados >= 3 and not r.erros
    assert aqui.study_info(uid)["dono"] == "ana" and aqui.reports(uid)[0]["text"] == "Laudo de teste"
    assert repo.study_info(uid) is not None                         # copiar não tira do servidor
    # mover: sai do servidor (com cadeado, não sai — fica só copiado)
    repo.set_locked(uid, True)
    r = T.trazer(cliente, [uid], aqui_db, tmp_path / "aqui", "ana", mover=True)
    assert r.recusados == [uid] and repo.study_info(uid) is not None
    repo.set_locked(uid, False)
    r = T.trazer(cliente, [uid], aqui_db, tmp_path / "aqui", "ana", mover=True)
    assert r.exames == 1 and repo.study_info(uid) is None
    assert repo.access_log(action="retirou_do_servidor")
    # enviar de volta, no banco pessoal: chega com o laudo e já marcado como da Ana
    aqui.save_report({"study_uid": uid, "title": "Adendo", "text": "feito offline", "author": "ana"})
    r = T.enviar(ana, aqui, [uid], True, "ana")
    assert r.exames == 1 and r.imagens > 0 and not r.erros and not r.recusados
    assert repo.study_info(uid)["dono"] == "ana"
    assert {x["text"] for x in repo.reports(uid)} == {"Laudo de teste", "feito offline"}
    # o administrador migra um banco local "como está": cada exame no banco do dono
    outro = repo.search_studies(banco="todos")[0].study_uid
    Importer(aqui_db, tmp_path / "aqui").import_paths([p for p in repo.files_for_study(outro)])
    aqui.set_study_scope([outro], "bia")
    r = T.enviar(_cli(srv, "adm"), aqui, [outro], "como_estao", "adm")
    assert r.exames == 1 and repo.study_info(outro)["dono"] == "bia"
    cache_db.close()
    aqui_db.close()


def test_stow_no_meu_banco_marca_so_os_exames_novos(grupo, tmp_path, sample_dir):
    _p, _db, repo, srv = grupo
    from pydicom.uid import generate_uid
    import pydicom
    arq = next(p for p in sorted(sample_dir.rglob("*")) if p.is_file())
    ds = pydicom.dcmread(arq)
    ds.StudyInstanceUID, ds.SeriesInstanceUID, ds.SOPInstanceUID = generate_uid(), generate_uid(), generate_uid()
    novo = tmp_path / "novo.dcm"
    ds.save_as(novo)
    ja = repo.search_studies(banco="todos")[0].study_uid
    bia = _cli(srv, "bia")
    bia.store([novo, *repo.files_for_study(ja)[:1]], banco="meu")
    assert repo.study_info(ds.StudyInstanceUID)["dono"] == "bia"
    assert repo.study_info(ja)["dono"] == ""                        # o que já estava continua compartilhado


def test_cliente_guarda_o_banco_do_exame_que_ainda_vai_subir(grupo, tmp_path, sample_dir):
    """Exame importado no cliente com "o meu banco no servidor": sobe já no banco pessoal."""
    _p, _db, repo, srv = grupo
    from pydicom.uid import generate_uid
    import pydicom
    ana = _cli(srv, "ana")
    cache_db = Database(tmp_path / "cache.sqlite")
    cliente = ClientRepository(Repository(cache_db), ana, tmp_path / "cache")
    arq = next(p for p in sorted(sample_dir.rglob("*")) if p.is_file())
    ds = pydicom.dcmread(arq)
    ds.StudyInstanceUID, ds.SeriesInstanceUID, ds.SOPInstanceUID = generate_uid(), generate_uid(), generate_uid()
    (tmp_path / "in").mkdir()
    ds.save_as(tmp_path / "in" / "a.dcm")
    Importer(cache_db, tmp_path / "cache").import_paths([tmp_path / "in"])
    assert cliente.set_study_scope([ds.StudyInstanceUID], "ana") == 0     # ainda não está no servidor
    cliente.upload_study(ds.StudyInstanceUID, wait=True)
    assert repo.study_info(ds.StudyInstanceUID)["dono"] == "ana"
    cache_db.close()


# ------------------------------------------------------------------ modos e locais
def test_aviso_da_troca_de_modo():
    assert MODO.aviso_da_troca("varios", "varios") == ""
    t = MODO.aviso_da_troca("varios", "um", {"ana": 3, "bia": 1})
    assert "4 exame(s)" in t and "ana, bia" in t
    assert "compartilhado" in MODO.aviso_da_troca("um", "varios")
    assert "Enviar este banco" in MODO.aviso_da_troca("um", "cliente")
    assert "continuam aqui" in MODO.aviso_da_troca("cliente", "um")


def test_servidor_aparece_nos_locais_no_modo_cliente(env):
    from ipe.core import locations as LOC
    from ipe.core.config import Settings
    paths, _db, _repo = env
    cfg = Settings(paths.settings_file)
    assert all(not loc.is_central for loc in LOC.all_locations(cfg, paths))
    cfg.set("central.mode", "client")
    cfg.set("central.url", "http://10.0.0.5:8043")
    locs = LOC.all_locations(cfg, paths)
    assert locs[0].is_central and "10.0.0.5" in locs[0].name and locs[1].is_default


def test_janela_do_cliente_troca_entre_servidor_e_este_computador(grupo, tmp_path, monkeypatch):
    """Locais ▸ Banco deste computador abre sem o servidor; Locais ▸ Servidor central volta; o botão
    direito ▸ Banco oferece copiar/mover para cá ou enviar ao servidor."""
    from ipe.core.config import Settings
    from ipe.auth.permissions import permissions_for
    from ipe.auth.session import UserSession
    from ipe.central.client_mode import cache_paths
    from ipe.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    avisos = []
    for nome in ("information", "warning"):
        monkeypatch.setattr(f"PySide6.QtWidgets.QMessageBox.{nome}", lambda *a, **k: avisos.append(a[2]))
    _sp, _db, repo, srv = grupo
    monkeypatch.setenv("DICOMVIEWER_HOME", str(tmp_path / "estacao"))        # o computador cliente
    from ipe.core.config import get_paths
    paths = get_paths()
    cfg = Settings(paths.settings_file)
    cfg.set("central.mode", "client")
    cfg.set("central.url", f"http://127.0.0.1:{srv.port}")
    ana = _cli(srv, "ana")
    cdb_path, cstorage = cache_paths(paths)
    cdb = Database(cdb_path)
    cliente = ClientRepository(Repository(cdb), ana, cstorage, cfg)
    w = MainWindow(paths, cfg, repo=cliente, db=cdb, storage=cstorage)
    try:
        w.start_session(UserSession(username="ana", full_name="Ana", role="medico", perms=permissions_for("medico")))
        assert w.location.is_central and w.repo is cliente
        rows = list(w.browser.model.rows)
        assert rows
        sub = submenu(w.browser.menu_do_exame(rows[:1]), "Organizar/Banco")
        textos = [a.text() for a in sub.actions()]
        assert "Copiar para este computador" in textos
        mover = next(a for a in sub.actions() if a.text().startswith("Mover para este computador"))
        assert not mover.isEnabled()                                 # exame do compartilhado
        uid = rows[0].study_uid
        res = w.trazer_do_servidor([uid])
        assert res.exames == 1
        # Locais ▸ Banco deste computador
        assert w.switch_location("default")
        assert not getattr(w.repo, "remote", False)
        assert uid in {r.study_uid for r in w.browser.model.rows}
        sub = submenu(w.browser.menu_do_exame(
            [r for r in w.browser.model.rows if r.study_uid == uid]), "Organizar/Banco")
        assert "Enviar ao servidor central…" in [a.text() for a in sub.actions()]
        monkeypatch.setattr(w, "_perguntar_banco_do_envio", lambda n, como_estao=False: True)
        repo.set_study_scope([uid], "")
        r = w.enviar_local_ao_servidor("default")
        assert r.exames == 1 and r.recusados == [uid]                # compartilhado → pessoal: precisa configurar
        assert "ficaram de fora" in avisos[-1]
        # de volta ao servidor, sem fechar o banco do cache
        assert w.switch_location("central") and w.repo is cliente
        assert w.browser.model.rows
    finally:
        w.close()
        cdb.close()
