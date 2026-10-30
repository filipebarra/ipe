"""0.99.11: exames do paciente em cima da tira e quadro vazio que pede a série."""
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer


def _sem_protocolos(s):
    from ipe.ui.viewer import hanging as H
    s.set("hanging_protocols", [dict(p, enabled=False) for p in H.DEFAULT_PROTOCOLS])
    s.set("hanging_fabrica", H.FABRICA_VERSAO)
    return s


@pytest.fixture()
def win(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, _sem_protocolos(Settings(paths.settings_file)))
    w.resize(1400, 800)
    w.show()
    w.browser.refresh()
    yield app, w
    w.close()


def _aba(w, app):
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    app.processEvents()
    tab._encher_filtro_de_exames()
    return tab


def _estudos_na_tira(tab):
    uids = []
    for i in range(tab.strip.count()):
        d = tab.strip.item(i).data(Qt.UserRole)
        s = tab._series_row(d) if isinstance(d, str) else None
        if s is not None and s.study_uid not in uids:
            uids.append(s.study_uid)
    return uids


def test_escolha_de_exames_aparece_com_anterior(win):
    app, w = win
    tab = _aba(w, app)
    anterior = w.repo.find_study_uids(accession="ACC0901")[0]
    c = tab.filtro_exames
    assert c.isVisibleTo(tab)
    dados = [c.itemData(i) for i in range(c.count())]
    assert dados[0] == "atual" and anterior in dados and dados[-1] == "todos"
    assert c.currentData() == "atual"


def test_escolher_anterior_mostra_so_ele_sem_mexer_nos_quadros(win):
    app, w = win
    tab = _aba(w, app)
    antes = [vp.series_uid for vp in tab.viewports]
    anterior = w.repo.find_study_uids(accession="ACC0901")[0]
    tab.mostrar_exames_na_tira(anterior)
    assert anterior in tab.study_order
    assert _estudos_na_tira(tab) == [anterior]
    assert [vp.series_uid for vp in tab.viewports] == antes       # os quadros não mudaram
    assert tab.filtro_exames.currentData() == anterior
    tab.mostrar_exames_na_tira("todos")
    assert set(_estudos_na_tira(tab)) >= {tab.study_uid, anterior}
    tab.mostrar_exames_na_tira("atual")
    assert _estudos_na_tira(tab) == [tab.study_uid]


def test_anterior_pelo_botao_aparece_mesmo_com_filtro(win):
    app, w = win
    tab = _aba(w, app)
    tab.mostrar_exames_na_tira("atual")
    anterior = w.repo.find_study_uids(accession="ACC0901")[0]
    tab.add_study(anterior)
    assert anterior in _estudos_na_tira(tab)


def test_sem_anterior_nao_aparece(win, monkeypatch):
    app, w = win
    tab = _aba(w, app)
    monkeypatch.setattr(tab.repo, "other_studies_same_patient", lambda uid: [])
    tab._encher_filtro_de_exames()
    assert not tab.filtro_exames.isVisibleTo(tab)


def _clique(vp):
    p = QPointF(vp.width() / 2, vp.height() / 2)
    ev = QMouseEvent(QMouseEvent.MouseButtonPress, p, vp.mapToGlobal(p.toPoint()),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    vp.mousePressEvent(ev)


def test_quadro_vazio_mostra_as_series_e_poe_so_ali(win):
    app, w = win
    tab = _aba(w, app)
    tab.set_layout(1, 2)
    app.processEvents()
    vazio = next(vp for vp in tab.viewports if vp.vazio())
    pedidos = []
    vazio.sig.empty_clicked.connect(lambda vp, pos: pedidos.append(vp))
    protocolos = w.settings.get("hanging_protocols", None)
    _clique(vazio)
    assert pedidos == [vazio]
    menu = tab._menu_do_vazio
    acoes = [a for a in menu.actions() if a.isCheckable()]
    assert acoes, "a lista tem as séries do exame"
    menu.hide()
    acoes[0].trigger()
    app.processEvents()
    assert not vazio.vazio() and vazio.series_uid
    assert w.settings.get("hanging_protocols", None) == protocolos     # o protocolo não mudou


def test_quadro_com_imagem_nao_abre_lista(win):
    app, w = win
    tab = _aba(w, app)
    cheio = next(vp for vp in tab.viewports if not vp.vazio())
    pedidos = []
    cheio.sig.empty_clicked.connect(lambda vp, pos: pedidos.append(vp))
    _clique(cheio)
    assert pedidos == []
