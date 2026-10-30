"""Monitores (papéis, janela de comparação), layouts 4×4, botões laterais e memória."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.core.sysinfo import auto_cache_mb, process_ram_mb, total_ram_mb
from ipe.importer.scanner import Importer
from ipe.ui.monitors import screen_key



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
    w.show_on_configured_screen()
    w.browser.refresh()
    yield app, w
    w.close()


def test_prior_opens_on_compare_monitor_and_syncs(win):
    app, w = win
    key = screen_key(QGuiApplication.primaryScreen())
    w.settings.set("monitors", {key: {"role": "compare", "layout": [1, 1]}})
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    a = tab.active
    a.go_to(20)
    prior_uid = w.repo.find_study_uids(accession="ACC0901")[0]
    tab.open_prior(prior_uid)
    assert len(w.detached) == 1
    (ptab,) = w.detached[0].viewer_tabs()
    assert ptab.study_uid == prior_uid and ptab._layout == (1, 1)
    b = ptab.viewports[0]
    assert b.frames and b.modality == "CT"
    w.tabs.setCurrentWidget(tab)
    app.processEvents()
    b.go_to(25)
    tab._cycle_group(a)
    ptab._cycle_group(b)
    a.step(3)
    assert b.index == 28
    # abrir de novo o mesmo anterior não duplica a aba
    tab.open_prior(prior_uid)
    assert len(w.detached[0].viewer_tabs()) == 1
    # o X da janela do monitor fecha o exame em todas as telas e devolve o banco de dados
    w.detached[0].close()
    app.processEvents()
    assert not w.detached and not w.all_viewer_tabs()
    assert w.isVisible()


def test_viewer_role_without_second_screen_stays_in_main(win):
    app, w = win
    key = screen_key(QGuiApplication.primaryScreen())
    w.settings.set("monitors", {key: {"role": "viewer", "layout": [2, 2]}})
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    assert not w.detached and tab._layout == (2, 2)     # único monitor: fica na principal


def test_layout_4x4_and_side_buttons(win):
    app, w = win
    w.handle_external({"accession": "ACC2001"})         # RM com várias séries
    tab = w.tabs.currentWidget()
    tab.set_layout(4, 4)
    assert len(tab._shown()) == 16
    tab.set_layout(1, 1)
    vp = tab.viewports[0]
    first = vp.series_uid
    QTest.mouseClick(vp, Qt.ForwardButton, Qt.NoModifier, vp.rect().center())
    assert vp.series_uid != first
    QTest.mouseClick(vp, Qt.BackButton, Qt.NoModifier, vp.rect().center())
    assert vp.series_uid == first
    w.settings.set("viewer.mouse.forward", "frame_next")
    i = vp.index
    QTest.mouseClick(vp, Qt.ForwardButton, Qt.NoModifier, vp.rect().center())
    assert vp.index == i + 1


def test_memory_controls(win):
    app, w = win
    assert total_ram_mb() > 0 and auto_cache_mb() >= 512
    assert process_ram_mb() is None or process_ram_mb() > 10
    from ipe.ui.preferences import PreferencesDialog
    dlg = PreferencesDialog(w.settings, w)
    dlg.s_cache.setValue(640)
    dlg.s_vol.setValue(1)                      # qualquer volume passa do limite
    dlg._save()
    assert w.settings.get("performance.cache_mb") == 640
    w.cache.set_limit(w.cache_limit_mb())
    assert w.cache.max_bytes == 640 * 1024 * 1024
    w._update_status()
    assert "Cache de imagens" in w.cache_label.text()
    # limite de volume: MPR pergunta; respondendo "não", não monta
    from PySide6.QtWidgets import QMessageBox
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    orig = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
    try:
        tab.mpr_action.setChecked(True)
    finally:
        QMessageBox.question = orig
    assert not tab.mpr_active and not tab._volumes
    w.settings.set("performance.max_volume_mb", 0)
    tab.mpr_action.setChecked(True)
    assert tab.mpr_active
    w._update_status()
    assert "Volumes MPR" in w.cache_label.text()
