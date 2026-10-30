"""Girar e espelhar a imagem no visualizador."""
import numpy as np
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.imaging.windowing import orientation_labels
from ipe.importer.scanner import Importer


def test_rotate_flip(env, sample_dir):
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    Importer(db, paths.storage).import_paths([sample_dir])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1200, 800)
    w.show()
    w.browser.refresh()
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 2)
    app.processEvents()
    a, b = tab.viewports[:2]
    tab._activate(a)
    before = orientation_labels(a.display_orientation())
    ip = QPointF(40.0, 70.0)                      # ponto da imagem
    wp = a.image_to_widget(ip)
    a.rotate_view(90)
    wp2 = a.image_to_widget(ip)
    back = a.widget_to_image(wp2)
    assert abs(back.x() - 40) < 1e-6 and abs(back.y() - 70) < 1e-6
    c = QPointF(a.width() / 2, a.height() / 2)
    d2 = wp2 - c                                  # 90° horário: o ponto gira em volta do centro
    assert d2.x() < 0 or d2.y() != (wp - c).y()
    after = orientation_labels(a.display_orientation())
    assert after != before and after["top"] == before["left"]      # o que estava à esquerda sobe
    # espelhar na tela com giro de 90°: vira espelho vertical da imagem
    a.flip_view(True)
    assert a.state.flip_v and not a.state.flip_h
    assert a.film_orientation() == (270, True)
    a.flip_view(False)                           # dois espelhos = 180°
    assert not a.state.flip_h and not a.state.flip_v and a.state.rot == 270
    a.grab()                                      # desenha sem erro
    assert "↻270°" in a.orientation_text()
    # medida desenhada com o mouse cai no pixel certo da imagem
    tab.set_left_tool("probe")
    target = a.image_to_widget(QPointF(100.0, 60.0)).toPoint()
    QTest.mouseClick(a, Qt.LeftButton, Qt.NoModifier, target)
    ann = a.frame_annotations()[-1]
    assert abs(ann.points[0][0] - 100) < 1.5 and abs(ann.points[0][1] - 60) < 1.5
    # pan arrasta na direção do mouse mesmo girada
    p0 = a.image_to_widget(QPointF(128.0, 128.0))
    a._apply_drag("pan", 30, 0, {"pos": QPointF(10, 10)})
    p1 = a.image_to_widget(QPointF(128.0, 128.0))
    assert abs((p1 - p0).x() - 30) < 1e-6 and abs((p1 - p0).y()) < 1e-6
    # aplicar a todos e filme
    tab.orientation_to_all()
    assert b.state.rot == 270
    item = tab._film_item(a)
    assert item["rotation"] == 270 and item["flip_h"] is False
    a.reset_orientation()
    assert not a.is_transformed() and orientation_labels(a.display_orientation()) == before
    tab.actions_by_id["view.flip_h"].trigger()
    assert a.state.flip_h
    w.film_composer().dirty = False
    w.close()
