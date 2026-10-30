"""Teste de fumaça da interface (roda sem tela, QT_QPA_PLATFORM=offscreen)."""
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer


def test_open_and_interact(env, sample_dir):
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1200, 800)
    w.show()
    Importer(w.db, paths.storage).import_paths([sample_dir])
    w.browser.refresh()
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    assert w.handle_external({"accession": "NAOEXISTE"}) == "nao_encontrado"
    tab = w.tabs.currentWidget()
    vp = tab.viewports[0]
    app.processEvents()
    assert len(vp.frames) == 60
    # clique na área "Im x/y" troca o botão esquerdo para rolar
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, vp._hotspots["scroll"].center().toPoint())
    assert tab.left_tool == "scroll"
    i0 = vp.index
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, QPoint(200, 200))
    for y in range(200, 260, 5):
        QTest.mouseMove(vp, QPoint(200, y))
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, QPoint(200, 260))
    assert vp.index > i0
    # direito segurado e arrastado = zoom (não abre menu)
    z0 = vp.state.zoom
    QTest.mousePress(vp, Qt.RightButton, Qt.NoModifier, QPoint(200, 200))
    for y in range(200, 150, -5):
        QTest.mouseMove(vp, QPoint(200, y))
    QTest.mouseRelease(vp, Qt.RightButton, Qt.NoModifier, QPoint(200, 150))
    assert vp.state.zoom > z0
    vp.apply_preset("1")
    assert (vp.state.width, vp.state.level) == (1500.0, -600.0)
    tab.anon_action.setChecked(True)
    assert "TESTE" not in w.tabs.tabText(w.tabs.currentIndex())
    w.close()


def test_import_thread_from_gui(env, sample_dir):
    """Regressão: a importação pela interface ficava parada em 'Procurando arquivos…'."""
    import gc
    import time
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    w.start_import([sample_dir])
    t0 = time.time()
    while w._import_thread is not None and time.time() - t0 < 30:
        app.processEvents()
        gc.collect()
        time.sleep(0.02)
    assert w._import_thread is None
    assert w.repo.counts()["instances"] == 180
    w.close()


def test_raw_dicom_without_preamble(env, sample_dir, tmp_path):
    """Arquivos sem o preâmbulo 'DICM' (comuns em CDs antigos) também são importados."""
    import pydicom
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    src = next((sample_dir / "US").glob("*.dcm"))
    ds = pydicom.dcmread(src)
    del ds.file_meta
    from pydicom.filebase import DicomBytesIO
    from pydicom.filewriter import write_dataset
    fp = DicomBytesIO()
    fp.is_little_endian, fp.is_implicit_VR = True, True
    write_dataset(fp, ds)
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "IM0001").write_bytes(fp.getvalue())    # sem preâmbulo nem "DICM"
    assert (raw_dir / "IM0001").read_bytes()[128:132] != b"DICM"
    r = Importer(db, paths.storage).import_paths([raw_dir])
    assert r.added == 1
    from ipe.imaging.series import build_frames, read_frame
    uid = repo.search_studies()[0].study_uid
    img = read_frame(build_frames(repo.instances_for_series(repo.series_for_study(uid)[0].series_uid))[0])
    assert img.is_color and img.pixels.shape == (300, 400, 3)


def test_tab_order_and_back_to_database(env, sample_dir):
    """PACS à esquerda; o programa abre no banco de dados e volta para ele ao fechar um exame."""
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    Importer(w.db, paths.storage).import_paths([sample_dir])
    w.browser.refresh()
    assert w.tabs.tabText(0) == "Banco de dados" and w.tabs.count() == 1     # PACS virou janela
    assert w.tabs.currentWidget() is w.browser
    w.show_pacs()
    assert w.pacs_window.isVisible()
    w.handle_external({"accession": "ACC1001"})
    w._close_tab(w.tabs.currentIndex())
    assert w.tabs.currentWidget() is w.browser
    for a in w.findChildren(QAction):
        if a.text() == "Voltar ao banco de dados":
            a.trigger()
    assert w.tabs.currentWidget() is w.browser
    w.close()


def test_browser_columns(env, sample_dir):
    """Escolher colunas (inclusive as novas), ordem e larguras ficam salvas."""
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.ui.browser import COLUMNS, DEFAULT_COLUMNS, KEY_INDEX
    from ipe.ui.main_window import MainWindow
    Importer(db, paths.storage).import_paths([sample_dir])
    s = Settings(paths.settings_file)
    w = MainWindow(paths, s)
    w.show()
    b = w.browser
    b.refresh()
    shown = [k for k, i in KEY_INDEX.items() if not b.table.isColumnHidden(i)]
    assert sorted(shown) == sorted(DEFAULT_COLUMNS)
    b._toggle_column("size_mb", True)
    b._toggle_column("origin", True)
    b._toggle_column("birth_date", False)
    assert not b.table.isColumnHidden(KEY_INDEX["size_mb"]) and b.table.isColumnHidden(KEY_INDEX["birth_date"])
    # valores das colunas novas
    row = next(i for i, r in enumerate(b.model.rows) if r.accession == "ACC1001")
    val = lambda key: b.model.data(b.model.index(row, KEY_INDEX[key]))  # noqa: E731
    assert float(val("size_mb")) > 0 and val("origin") == "importado"
    assert val("study_time") == "10:15" and val("date_added").count("/") == 2
    # mudar a ordem arrastando o título é lembrado
    hh = b.table.horizontalHeader()
    hh.moveSection(hh.visualIndex(KEY_INDEX["size_mb"]), 1)
    w.close()
    s2 = Settings(paths.settings_file)
    assert s2.get("browser.columns")[1] == "size_mb" and "origin" in s2.get("browser.columns")
    w2 = MainWindow(paths, s2)
    hh2 = w2.browser.table.horizontalHeader()
    assert hh2.visualIndex(KEY_INDEX["size_mb"]) == 1 and w2.browser.table.isColumnHidden(KEY_INDEX["birth_date"])
    w2.browser._reset_columns()
    assert w2.browser.visible_columns() == DEFAULT_COLUMNS
    assert len(COLUMNS) >= 20
    w2.close()
