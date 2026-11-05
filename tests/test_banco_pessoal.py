"""0.99.27: banco pessoal × compartilhado (etapa 3 do plano do modo de uso).

Pedido dele: banco compartilhado e "do meu usuário", com botão direito como nas listas (mover para o
compartilhado, compartilhar com…, mover para o pessoal). Decisões: o administrador vê o banco dos
outros, e cada exame pessoal alheio que ele abre fica no registro de acesso.
"""
from _menus import submenu, todas  # noqa: F401
import pytest
from pydicom.uid import generate_uid
from PySide6.QtWidgets import QApplication

from ipe.auth import session as S
from ipe.auth.session import UserSession
from ipe.db import banco as B


@pytest.fixture(autouse=True)
def _sessao_volta():
    antes = S.get()
    yield
    S.set_current(antes)


def entra(nome, papel="medico"):
    from ipe.auth.permissions import permissions_for
    S.set_current(UserSession(username=nome, full_name=nome, role=papel, perms=permissions_for(papel)))


def _exames(env, sample_dir):
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    return [r.study_uid for r in repo.search_studies(banco="todos")]


def test_quem_ve_qual_banco(env, sample_dir):
    _p, _db, repo = env
    uids = _exames(env, sample_dir)
    assert len(uids) >= 4
    a, b, c = uids[:3]
    repo.set_study_scope([a], "ana")
    repo.set_study_scope([b], "ana", "bia")
    repo.set_study_scope([c], "bia")
    vistos = lambda banco="visivel": {r.study_uid for r in repo.search_studies(banco=banco)}  # noqa: E731
    S.set_current(UserSession())                        # "só eu": sem filtro
    assert vistos() == set(uids)
    entra("ana")
    assert a in vistos() and b in vistos() and c not in vistos()
    assert vistos("meu") == {a, b} and c not in vistos("compartilhado") and a not in vistos("compartilhado")
    entra("bia")
    assert vistos("comigo") == {b} and vistos("meu") == {c} and a not in vistos()
    assert vistos("usuario:ana") == set()               # só o administrador abre o banco dos outros
    entra("adm", "admin")
    assert a not in vistos()                            # no dia a dia, nem o administrador vê
    assert vistos("usuario:ana") == {a, b}
    assert repo.donos_de_exames() == {"ana": 2, "bia": 1}
    row = next(r for r in repo.search_studies(banco="usuario:ana") if r.study_uid == b)
    assert B.rotulo_do_banco(row) == "de ana + bia"
    assert B.rotulo_do_banco(row, __import__("ipe.auth.visibilidade", fromlist=["Visao"]).Visao("ana")) == "Meu + bia"


def test_transferir_o_banco_de_quem_saiu(env, sample_dir):
    _p, _db, repo = env
    uids = _exames(env, sample_dir)
    repo.set_study_scope(uids[:2], "ana", "bia")
    assert repo.transferir_banco("ANA", "") == 2
    assert repo.donos_de_exames() == {}
    repo.set_study_scope(uids[:1], "ana")
    assert repo.transferir_banco("ana", "carla") == 1 and repo.donos_de_exames() == {"carla": 1}


def test_exame_que_chega_no_ae_pessoal_vai_para_o_banco_do_dono(env, sample_dir):
    paths, db, repo = env
    repo.save_identity({"name": "AE da Ana", "ae_title": "DRANA", "dono": "ana"})
    assert B.dono_da_chegada(repo, "drana") == "ana" and B.dono_da_chegada(repo, "IPE") == ""
    import pydicom

    from ipe.network.sink import IncomingSink
    sink = IncomingSink(db, repo, paths.storage)
    try:
        arq = next(p for p in sorted(sample_dir.rglob("*")) if p.is_file())
        ds = pydicom.dcmread(arq)
        ds.StudyInstanceUID = generate_uid()
        ds.SeriesInstanceUID = generate_uid()
        ds.SOPInstanceUID = generate_uid()
        sink.store(ds, ds.file_meta, remetente={"calling_ae": "TC1", "remote_host": "10.0.0.2", "my_ae": "DRANA"})
        assert sink.flush(60)
        assert repo.study_info(ds.StudyInstanceUID)["dono"] == "ana"
        # no AE do serviço: compartilhado
        ds.StudyInstanceUID, ds.SeriesInstanceUID, ds.SOPInstanceUID = generate_uid(), generate_uid(), generate_uid()
        sink.store(ds, ds.file_meta, remetente={"calling_ae": "TC1", "remote_host": "10.0.0.2", "my_ae": "IPE"})
        assert sink.flush(60)
        assert repo.study_info(ds.StudyInstanceUID)["dono"] == ""
    finally:
        sink.stop()


def test_exames_que_eu_trago(env):
    from ipe.core.config import Settings
    paths, _db, _repo = env
    cfg = Settings(paths.settings_file)
    entra("ana")
    assert B.dono_dos_novos(cfg) == ""                  # de fábrica: compartilhado
    cfg.set(B.CHAVE_NOVOS, "meu")
    assert B.dono_dos_novos(cfg) == "ana"
    S.set_current(UserSession())
    assert B.dono_dos_novos(cfg) == ""                  # "só eu": não há banco pessoal


def test_registro_quando_o_administrador_abre_exame_pessoal(env, sample_dir):
    _p, _db, repo = env
    uids = _exames(env, sample_dir)
    repo.set_study_scope([uids[0]], "ana")
    entra("adm", "admin")
    assert B.precisa_registrar(repo.study_info(uids[0])) == "ana"
    assert B.precisa_registrar(repo.study_info(uids[1])) == ""
    entra("ana")
    assert B.precisa_registrar(repo.study_info(uids[0])) == ""


# ------------------------------------------------------------------ telas
def test_botao_direito_e_painel_locais(env, sample_dir, monkeypatch):
    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uids = _exames(env, sample_dir)
    for n in ("ana", "bia"):
        repo.save_user({"username": n, "full_name": n.title(), "role": "medico", "active": True,
                        "password": "uma senha comprida"})
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        from ipe.auth.permissions import permissions_for
        w.start_session(UserSession(username="ana", full_name="Ana", role="medico", perms=permissions_for("medico")))
        textos = [w.locations.tree.topLevelItem(i).text(0) for i in range(w.locations.tree.topLevelItemCount())]
        assert "Banco" in textos and "Meu banco" in textos and "Compartilhado" in textos
        b = w.browser
        rows = [r for r in b.model.rows if r.study_uid == uids[0]]
        m = b.menu_do_exame(rows)
        sub = submenu(m, "Organizar/Banco")
        acoes = {a.text(): a for a in sub.actions()}
        # médico não tira exame do compartilhado (esconderia dos outros)
        assert not acoes["Mover para o meu banco (pessoal)"].isEnabled()
        # o administrador tira, e passa para a Ana
        w.start_session(UserSession(username="adm", role="admin", perms=permissions_for("admin")))
        rows = [r for r in b.model.rows if r.study_uid == uids[0]]
        sub = submenu(b.menu_do_exame(rows), "Organizar/Banco")
        passar = next(a.menu() for a in sub.actions() if a.text() == "Passar para o banco de")
        next(a for a in passar.actions() if a.text() == "ana").trigger()
        assert repo.study_info(uids[0])["dono"] == "ana"
        assert uids[0] not in {r.study_uid for r in b.model.rows}       # sumiu da lista do admin
        w.locations.rebuild()
        textos = [w.locations.tree.topLevelItem(i).text(0) for i in range(w.locations.tree.topLevelItemCount())]
        assert "Banco de ana (1)" in textos
        w.escolher_banco("usuario:ana")
        assert {r.study_uid for r in b.model.rows} == {uids[0]}
        assert w.registrar_abertura_alheia(uids[0]) == "ana"
        acoes_log = [a for _at, _u, a, _d in repo.audit_entries(50)]
        assert "abriu_exame_pessoal" in acoes_log and "viu_banco_de" in acoes_log and "moveu_banco" in acoes_log
        # a Ana vê no banco dela e devolve para o compartilhado
        w.start_session(UserSession(username="ana", full_name="Ana", role="medico", perms=permissions_for("medico")))
        w.escolher_banco("meu")
        assert {r.study_uid for r in b.model.rows} == {uids[0]}
        rows = [r for r in b.model.rows if r.study_uid == uids[0]]
        sub = submenu(b.menu_do_exame(rows), "Organizar/Banco")
        next(a for a in sub.actions() if a.text() == "Mover para o compartilhado").trigger()
        assert repo.study_info(uids[0])["dono"] == ""
    finally:
        w.close()


def test_coluna_banco_existe():
    from ipe.ui.browser import COLUMNS
    assert any(c[0] == "banco" for c in COLUMNS)
