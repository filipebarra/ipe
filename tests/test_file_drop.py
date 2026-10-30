"""Arrastar arquivos/pastas/ZIP para as janelas do programa importa e abre os exames."""
import time
import zipfile

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings


def _mime(paths):
    m = QMimeData()
    m.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    return m


def _drop(app, widget, mime):
    pos = widget.rect().center()
    enter = QDragEnterEvent(pos, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    app.sendEvent(widget, enter)
    accepted = enter.isAccepted()
    drop = QDropEvent(QPointF(pos), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    app.sendEvent(widget, drop)
    return accepted, drop.isAccepted()


def _wait_import(app, w, timeout=30):
    for _ in range(3):
        app.processEvents()           # a importação começa no próximo ciclo de eventos
    t0 = time.time()
    while (w._import_thread is not None or w._pending_imports) and time.time() - t0 < timeout:
        app.processEvents()
        time.sleep(0.02)
    for _ in range(5):
        app.processEvents()


def _window(env):
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1300, 800)
    w.show()
    return app, w


def test_drop_folder_on_browser_imports_and_opens(env, sample_dir):
    app, w = _window(env)
    table = w.browser.table
    ct = sample_dir / "CT_atual" if (sample_dir / "CT_atual").exists() else None
    target = [p for p in sample_dir.iterdir() if p.is_dir()][0] if ct is None else ct
    acc, dacc = _drop(app, table.viewport(), _mime([target]))
    assert acc and dacc
    _wait_import(app, w)
    assert w.repo.counts()["instances"] > 0
    from ipe.ui.viewer.viewer_tab import ViewerTab
    assert isinstance(w.tabs.currentWidget(), ViewerTab)             # exame aberto
    w.close()


def test_drop_files_and_zip_on_viewer_and_queue(env, sample_dir, tmp_path):
    app, w = _window(env)
    us_files = sorted((sample_dir / "US").glob("*.dcm"))
    # primeiro: um arquivo solto
    _drop(app, w.tabs, _mime(us_files[:1]))
    # enquanto importa, chega um ZIP com o resto: vai para a fila
    z = tmp_path / "exame.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in (sample_dir / "MG").glob("*.dcm"):
            zf.write(f, f.name)
    tab = w.tabs.currentWidget()
    _drop(app, tab, _mime([z]))
    _wait_import(app, w)
    mods = {t.study_info.get("modalities", "") for t in w.all_viewer_tabs()}
    assert any("US" in m for m in mods) and any("MG" in m for m in mods)
    # soltar de novo o mesmo arquivo (já no banco) só abre o exame, sem aviso de "nada novo"
    n = w.tabs.count()
    vp = w.tabs.currentWidget().viewports[0]
    _drop(app, vp, _mime(us_files[:1]))
    _wait_import(app, w)
    assert w.tabs.count() == n and "US" in w.tabs.currentWidget().study_info.get("modalities", "")
    w.close()


def test_internal_series_drag_still_works(env, sample_dir):
    from ipe.importer.scanner import Importer
    app, w = _window(env)
    Importer(w.db, w.paths.storage).import_paths([sample_dir])
    w.browser.refresh()
    w.handle_external({"accession": "ACC2001"})
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 2)
    vp = tab.viewports[1]
    uid = tab.series[-1].series_uid
    m = QMimeData()
    m.setData("application/x-dicomviewer-series", uid.encode())
    _drop(app, vp, m)
    assert vp.series_uid == uid
    w.close()


def test_drop_on_monitor_window(env, sample_dir):
    app, w = _window(env)
    from ipe.importer.scanner import Importer
    Importer(w.db, w.paths.storage).import_paths([sample_dir / "US"])
    w.browser.refresh()
    w.handle_external({"accession": "ACC4001"})
    w.detach_tab(w.tabs.currentWidget())
    win = w.detached[0]
    acc, _ = _drop(app, win.tab.viewports[0], _mime([sample_dir / "MG"]))
    assert acc
    _wait_import(app, w)
    assert any("MG" in (t.study_info.get("modalities") or "") for t in w.all_viewer_tabs())
    w.close()
