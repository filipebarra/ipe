"""Tabelas de cores (pseudocor)."""
import numpy as np
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.imaging import colormaps as CM
from ipe.imaging.series import FrameImage
from ipe.imaging.windowing import to_display
from ipe.importer.scanner import Importer


def test_luts():
    for key in CM.COLORMAPS:
        t = CM.lut(key)
        assert t.shape == (256, 3) and t.dtype == np.uint8
    assert (CM.lut("inverse")[:, 0] == 255 - np.arange(256)).all()
    assert tuple(CM.lut("hot")[0]) == (0, 0, 0) and tuple(CM.lut("hot")[255]) == (255, 255, 255)
    img = FrameImage(np.linspace(-1000, 1000, 64 * 64).reshape(64, 64).astype(np.float32), False, None,
                     (1, 1), "PixelSpacing", "MONOCHROME2", {})
    g = to_display(img, 2000, 0)
    c = to_display(img, 2000, 0, cmap="gold")
    assert g.ndim == 2 and c.shape == (64, 64, 3)
    assert (c == CM.lut("gold")[g]).all()


def test_viewer_colormap(env, sample_dir, tmp_path):
    from ipe.exporter.core import ExportItem, export_images
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    Importer(db, paths.storage).import_paths([sample_dir])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    w.browser.refresh()
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 2)
    app.processEvents()
    a, b = tab.viewports[0], tab.viewports[1]
    tab.load_series_into(b, a.series_uid)
    tab._activate(a)
    a.set_colormap("pet")
    assert a._qimage_for_current().format() == QImage.Format_RGB888
    tab.colormap_to_all()
    assert b.state.cmap == "pet"
    # reconstrução da mesma série mantém a cor; outra série volta ao cinza
    assert tab.reconstruct_plane("Coronal") and a.state.cmap == "pet"
    item = tab._film_item(b)
    assert item["cmap"] == "pet"
    a.reset_view()
    assert a.state.cmap == "pet"
    uid = b.series_uid
    a.set_colormap("")
    assert a._qimage_for_current().format() == QImage.Format_Grayscale8
    s = repo.series_info(uid)
    res = export_images(repo, [ExportItem(s["study_uid"], [uid], None)], tmp_path / "img", "png", every=30,
                        cmap="hot")
    assert res.images >= 1
    png = next((tmp_path / "img").rglob("*.png"))
    q = QImage(str(png))
    assert not q.isGrayscale()
    w.close()
