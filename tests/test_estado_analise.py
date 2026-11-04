"""0.99.58 — item 6 do backlog: estado salvo da análise (reabrir como deixou; montagem do anterior)."""
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QMessageBox

from ipe.core.config import Settings
from ipe.importer.scanner import Importer
from ipe.ui.viewer import estado_analise as EA


@pytest.fixture()
def janela(env, sample_dir):
    from test_pedidos_29_10 import _sem_protocolos
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, _sem_protocolos(Settings(paths.settings_file)))
    w.resize(1300, 800)
    w.show()
    yield app, w, repo
    w.close()


def _exame_com_series(repo, n=2):
    for r in repo.search_studies():
        ss = [s for s in repo.series_for_study(r.study_uid) if s.num_images and s.modality in ("CT", "MR")]
        if len(ss) >= n:
            return r.study_uid, ss
    pytest.skip("sem exame de TC/RM com duas séries no fantoma")


def _abrir(app, w, uid):
    w.open_study(uid)
    app.processEvents()
    return next(t for t in w.all_viewer_tabs() if t.study_uid == uid)


def test_guardar_e_reabrir_como_deixou(janela):
    app, w, repo = janela
    uid, ss = _exame_com_series(repo)
    tab = _abrir(app, w, uid)
    tab.set_layout(1, 2)
    a, b = tab.viewports[0], tab.viewports[1]
    tab.load_series_into(a, ss[1].series_uid)
    tab.load_series_into(b, ss[0].series_uid)
    a.set_index_silently(min(3, len(a.frames) - 1))
    a.set_window(123, 45, emit=False)
    a.set_zoom_pan(1.7, QPointF(12, -8))
    a.state.invert, a.state.rot, a.state.flip_h = True, 90, True
    tab._activate(b)
    dados = EA.capturar(tab)
    assert dados["layout"] == [1, 2] and dados["ativo"] == 1 and dados["quadros"][0]["series"] == ss[1].series_uid
    assert dados["quadros"][0]["vista"]["width"] == 123 and dados["quadros"][0]["vista"]["zoom"] == 1.7
    w.fechar_exame(uid)
    app.processEvents()
    assert repo.estado(uid, EA.usuario_atual())["dados"]["quadros"][0]["index"] == a.index
    # reabre como estava
    tab2 = _abrir(app, w, uid)
    a2 = tab2.viewports[0]
    assert tab2._layout == (1, 2) and a2.series_uid == ss[1].series_uid
    assert a2.index == dados["quadros"][0]["index"] and a2.state.width == 123 and a2.state.level == 45
    assert a2.state.zoom == pytest.approx(1.7) and a2.state.pan == QPointF(12, -8)
    assert a2.state.invert and a2.state.rot == 90 and a2.state.flip_h
    assert tab2.active is tab2.viewports[1]
    # esquecer: volta ao de fábrica e não guarda ao fechar
    tab2.esquecer_estado()
    assert repo.estado(uid, EA.usuario_atual()) is None
    w.fechar_exame(uid)
    app.processEvents()
    assert repo.estado(uid, EA.usuario_atual()) is None


def test_modos_ao_abrir(janela, monkeypatch):
    app, w, repo = janela
    uid, ss = _exame_com_series(repo)
    repo.salvar_estado(uid, {"layout": [1, 2], "quadros": [{"series": ss[1].series_uid, "index": 0},
                                                           {"series": "serie-que-sumiu"}], "ativo": 0},
                       EA.usuario_atual())
    w.settings.set(EA.CHAVE_AO_ABRIR, "nunca")
    tab = _abrir(app, w, uid)
    assert tab.viewports[0].series_uid != ss[1].series_uid or tab._layout != (1, 2)
    w.fechar_exame(uid)
    repo.salvar_estado(uid, {"layout": [1, 2], "quadros": [{"series": ss[1].series_uid, "index": 0},
                                                           {"series": "serie-que-sumiu", "index": 0}], "ativo": 0},
                       EA.usuario_atual())
    w.settings.set(EA.CHAVE_AO_ABRIR, "perguntar")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    msgs = []
    from ipe.ui.viewer.viewer_tab import ViewerTab
    tab = _abrir(app, w, uid)
    assert tab._layout == (1, 2) and tab.viewports[0].series_uid == ss[1].series_uid
    assert EA.restaurar(tab, {"layout": [1, 1], "quadros": [{"series": "x", "index": 0}]}) == \
        ["1 série(s) não estão mais no exame"]
    del msgs, ViewerTab


def test_nao_guarda_com_series_escolhidas(janela):
    app, w, repo = janela
    uid, ss = _exame_com_series(repo)
    w.open_study(uid, [ss[0].series_uid])
    app.processEvents()
    tab = next(t for t in w.all_viewer_tabs() if t.study_uid == uid)
    assert not tab.estado_pode() and not tab.guardar_estado()


def test_montagem_e_fundir_do_anterior(janela):
    from sqlalchemy import select
    from ipe.db.models import Study
    app, w, repo = janela
    uid, ss = _exame_com_series(repo)
    outro = next(r.study_uid for r in repo.search_studies() if r.study_uid != uid)
    # faz do outro um exame posterior do mesmo paciente
    with repo.db.session() as s:
        a = s.scalar(select(Study).where(Study.study_uid == uid))
        b = s.scalar(select(Study).where(Study.study_uid == outro))
        b.patient_fk = a.patient_fk
        a.study_date, b.study_date = "20240101", "20250101"
    dados = {"layout": [1, 2], "quadros": [
        {"series": ss[1].series_uid, "index": 2, "n": len(repo.instances_for_series(ss[1].series_uid)),
         "modality": ss[1].modality, "desc": ss[1].description, "vista": {"width": 77, "level": 7, "window_set": True,
                                                                          "zoom": 2.0, "pan": [0, 0]}},
        {"series": ss[0].series_uid, "index": 0, "modality": ss[0].modality, "desc": ss[0].description}]}
    repo.salvar_estado(uid, dados, EA.usuario_atual())
    assert repo.estados_anteriores(outro, EA.usuario_atual()) == [{"study_uid": uid, "study_date": "20240101",
                                               "modalidades": repo.study_info(uid)["modalities"]}]
    assert repo.estados_anteriores(uid, EA.usuario_atual()) == []
    w.settings.set(EA.CHAVE_AO_ABRIR, "nunca")
    tab = _abrir(app, w, outro)
    n_antes = tab._layout[0] * tab._layout[1]
    k = EA.fundir_anterior(tab, uid, dados)
    assert k == 2 and uid in tab.study_order
    carregados = [v.series_uid for v in tab.viewports[: tab._layout[0] * tab._layout[1]]]
    assert ss[1].series_uid in carregados and ss[0].series_uid in carregados
    vp = next(v for v in tab.viewports if v.series_uid == ss[1].series_uid)
    assert vp.state.width == 77 and vp.state.zoom == 2.0
    assert n_antes >= 1
    # menu do Exibir
    w.tabs.setCurrentWidget(tab)
    from PySide6.QtWidgets import QMenu
    m = QMenu()
    w._encher_menu_estado(m)
    textos = [a.text() for a in m.actions()]
    assert "Usar a montagem do exame anterior" in textos and "Voltar ao arranjo de fábrica (esquecer o estado deste exame)" in textos


def test_pelo_servidor_cada_um_tem_o_seu(env, sample_dir):
    from ipe.auth.backend import LocalAuth
    from ipe.central.remote import RemoteClient
    from ipe.central.server import CentralServer
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    repo.save_user({"username": "ana", "full_name": "Ana", "role": "medico", "password": "anaana123"})
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    try:
        uid = repo.search_studies()[0].study_uid
        adm, ana = RemoteClient(f"http://127.0.0.1:{srv.port}"), RemoteClient(f"http://127.0.0.1:{srv.port}")
        adm.login("admin", "admin123")
        ana.login("ana", "anaana123")
        adm.rpc("salvar_estado", uid, {"layout": [2, 2], "quadros": []}, "ana")    # o usuário mandado não vale
        assert ana.rpc("estado", uid, "admin") is None
        assert adm.rpc("estado", uid)["dados"]["layout"] == [2, 2]
        assert repo.estado(uid, "admin") is not None and repo.estado(uid, "ana") is None
        assert adm.rpc("esquecer_estado", uid) is True
    finally:
        srv.stop()
