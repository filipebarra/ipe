"""Grupos de sincronização, ajuste fino, alinhamento salvo e sincronização entre janelas."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer
from ipe.ui.viewer import sync as sync_mod



def _sem_protocolos(s):
    """Estes testes conferem o layout e a sincronia **sem** protocolo de exibição. Desde a 0.88 a TC
    de tórax tem protocolo de fábrica (com coronal e grupos de sincronia próprios), então ele fica
    desligado aqui."""
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


def _with_prior(w):
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    tab.add_study(w.repo.find_study_uids(accession="ACC0901")[0])
    return tab, tab._shown()[0], tab._shown()[1]


def test_group_icon_cycles_and_colors(win):
    app, w = win
    tab, a, b = _with_prior(w)
    assert a.sync_color is None
    tab._cycle_group(a)
    tab._cycle_group(b)
    assert tab.hub.group_of(a) == tab.hub.group_of(b) == 1
    assert a.sync_color is not None and a.sync_label == "1"
    a.go_to(20)
    b.go_to(20)          # entrou antes no grupo: deslocamento guardado era o da hora da entrada
    tab.hub.unlink([a, b])
    a.go_to(20)
    b.go_to(23)
    tab._cycle_group(a)
    tab._cycle_group(b)
    a.step(4)
    assert b.index == 27
    # segundo grupo convive com o primeiro
    tab._cycle_group(b)
    assert tab.hub.group_of(b) == 2 and tab.hub.group_of(a) == 1
    a.step(1)
    assert b.index == 27
    for _ in range(3):
        tab._cycle_group(b)            # 2 -> 3 -> 4 -> nenhum
    assert tab.hub.group_of(b) is None and b.sync_color is None


def test_fine_adjust_with_alt(win, monkeypatch):
    app, w = win
    tab, a, b = _with_prior(w)
    a.go_to(20)
    b.go_to(22)
    tab.escolher_modo_sync("manual")      # exames diferentes: ligados mantendo a diferença
    monkeypatch.setattr(sync_mod, "alt_pressed", lambda: True)
    b.step(3)                                   # só o anterior anda
    assert (a.index, b.index) == (20, 25)
    monkeypatch.setattr(sync_mod, "alt_pressed", lambda: False)
    a.step(2)
    assert b.index == 27                        # novo deslocamento (5) passa a valer


def test_saved_alignment_is_reused(win):
    app, w = win
    tab, a, b = _with_prior(w)
    a.go_to(20)
    b.go_to(26)
    tab.escolher_modo_sync("manual")      # exames diferentes: ligados mantendo a diferença
    tab.hub.flush_registrations()
    reg = w.repo.get_registration(a.study_uid, b.study_uid)
    assert reg is not None and abs(reg[0][2]) == pytest.approx(18.0)      # 6 cortes × 3 mm
    w._close_tab(w.tabs.currentIndex())
    tab2, a2, b2 = _with_prior(w)
    assert tab2.hub.group_of(a2) is not None and tab2.hub.group_of(a2) == tab2.hub.group_of(b2)
    a2.go_to(10)
    assert b2.index == 16


def test_sync_mode_cycle(win):
    app, w = win
    tab, a, b = _with_prior(w)
    hub = tab.hub
    assert hub.mode == "study"
    assert "todos" in hub.cycle_mode(tab)
    assert hub.group_of(a) == hub.group_of(b) == 1 and tab.link_action.isChecked()
    assert "desligada" in hub.cycle_mode(tab)
    assert not hub.members and not hub.sync_auto and not tab.link_action.isChecked()
    hub.cycle_mode(tab)
    assert hub.sync_auto and hub.mode == "study"


def test_sync_between_windows(win):
    """Estudo atual numa janela e anterior em outra (outro monitor): rolam juntos."""
    app, w = win
    w.handle_external({"accession": "ACC1001"})
    cur = w.tabs.currentWidget()
    w.handle_external({"accession": "ACC0901"})
    prior = w.tabs.currentWidget()
    w.detach_tab(prior)
    w.tabs.setCurrentWidget(cur)
    app.processEvents()
    a, b = cur._shown()[0], prior._shown()[0]
    a.go_to(30)
    b.go_to(30)
    cur._cycle_group(a)
    prior._cycle_group(b)
    a.step(-5)
    assert b.index == 25
    # a outra janela também mostra a corrente colorida
    assert b.sync_color is not None
