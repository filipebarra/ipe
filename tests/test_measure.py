"""Medidas: cálculos (sem interface) e desenho/persistência no viewer."""
import math

import numpy as np
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.imaging import measure as M
from ipe.importer.scanner import Importer


def test_length_and_angle_use_spacing():
    assert M.length_mm((0, 0), (10, 0), (0.5, 2.0)) == pytest.approx(20.0)
    assert M.length_mm((0, 0), (0, 10), (0.5, 2.0)) == pytest.approx(5.0)
    assert M.angle_deg((10, 0), (0, 0), (0, 10), None) == pytest.approx(90.0)
    # pixel não quadrado muda o ângulo físico
    assert M.angle_deg((1, 0), (0, 0), (1, 1), (2.0, 1.0)) == pytest.approx(math.degrees(math.atan(2)))


def test_roi_stats_ellipse_and_polygon():
    px = np.zeros((100, 100), np.float32)
    px[:, 50:] = 100.0
    # elipse (círculo r=20) toda na metade esquerda
    st = M.roi_stats(px, "ellipse", [(5, 30), (45, 70)], (0.5, 0.5))
    assert st.mean == pytest.approx(0.0) and st.sd == pytest.approx(0.0)
    assert st.n == pytest.approx(math.pi * 400, rel=0.03)
    assert st.area_mm2 == pytest.approx(math.pi * 400 * 0.25)
    # quadrado metade/metade
    sq = [(40, 40), (60, 40), (60, 60), (40, 60)]
    st = M.roi_stats(px, "polygon", sq, None)
    assert st.n == 400 and st.mean == pytest.approx(50.0)
    assert st.minimum == 0 and st.maximum == 100
    assert st.area_px == pytest.approx(400) and st.area_mm2 is None
    # triângulo (côncavo não é necessário para testar a regra par-ímpar)
    tri = [(0, 0), (20, 0), (0, 20)]
    assert M.roi_stats(px, "polygon", tri, None).n == pytest.approx(200, rel=0.1)
    # fora da imagem
    assert M.roi_stats(px, "ellipse", [(200, 200), (220, 220)], None).n == 0


def test_hit_and_handles():
    a = M.Annotation("line", ("1.2", 0), [(0, 0), (10, 0)])
    assert M.hit(a, (5, 0.5), 1.0) and not M.hit(a, (5, 3), 1.0)
    assert M.nearest_handle(a, (9.5, 0.2), 1.0) == 1
    e = M.Annotation("ellipse", ("1.2", 0), [(0, 0), (10, 10)])
    assert M.hit(e, (5, 5), 0.5)
    r = M.Annotation.from_record({"id": 3, "kind": "text", "sop_uid": "1.2", "frame_index": 0,
                                  "data": a.data_json().replace('"text": ""', '"text": "oi"')})
    assert r.db_id == 3 and r.text == "oi" and r.points == [(0, 0), (10, 0)]


@pytest.fixture()
def viewer(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1200, 800)
    w.show()
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 1)
    app.processEvents()
    yield app, w, tab, tab.viewports[0]
    w.close()


def _drag(vp, a, b, steps=6):
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, steps + 1):
        QTest.mouseMove(vp, a + (b - a) * i / steps)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, b)


def _w(vp, x, y):
    return vp.image_to_widget(QPointF(x, y)).toPoint()


def test_draw_and_persist_measurements(viewer):
    app, w, tab, vp = viewer
    tab.set_left_tool("measure")
    _drag(vp, _w(vp, 50, 50), _w(vp, 150, 50))
    tab.set_left_tool("ellipse")
    _drag(vp, _w(vp, 100, 100), _w(vp, 140, 140))
    tab.set_left_tool("angle")
    _drag(vp, _w(vp, 60, 200), _w(vp, 100, 200))            # primeiro braço
    QTest.mouseMove(vp, _w(vp, 100, 160))
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, _w(vp, 100, 160))   # terceiro ponto
    tab.set_left_tool("polygon")
    for x, y in ((20, 20), (40, 20), (40, 40)):
        QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, _w(vp, x, y))
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, _w(vp, 20, 20))   # fecha no 1º ponto
    anns = vp.frame_annotations()
    kinds = sorted(a.kind for a in anns)
    assert kinds == ["angle", "ellipse", "line", "polygon"] and all(a.done for a in anns)
    line = next(a for a in anns if a.kind == "line")
    assert M.length_mm(*line.points, vp._img.pixel_spacing) == pytest.approx(150, abs=1.5)  # 1,5 mm/px
    ang = next(a for a in anns if a.kind == "angle")
    assert M.angle_deg(*ang.points, (1.5, 1.5)) == pytest.approx(90, abs=2)
    roi = next(a for a in anns if a.kind == "ellipse")
    lab = M.labels(roi, vp._img.pixels, vp._img.pixel_spacing, vp.modality)
    assert "HU" in lab[0] and lab[-1].startswith("Área")
    poly = next(a for a in anns if a.kind == "polygon")
    assert len(poly.points) == 3
    assert w.repo.count_annotations(tab.study_uid) == 4
    # recarregar a série traz as medidas do banco
    idx = vp.index
    tab.load_series_into(vp, vp.series_uid)
    vp.set_index_silently(idx)
    assert len(vp.frame_annotations()) == 4
    # clicar numa medida seleciona; Del apaga só ela
    tab.set_left_tool("measure")
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, _w(vp, 100, 50))
    assert vp.selected is not None and vp.selected.kind == "line"
    QTest.keyClick(vp, Qt.Key_Delete)
    assert w.repo.count_annotations(tab.study_uid) == 3
    # arrastar uma alça edita e grava
    e = next(a for a in vp.frame_annotations() if a.kind == "ellipse")
    _drag(vp, _w(vp, 140, 140), _w(vp, 160, 160))
    assert e.points[1][0] == pytest.approx(160, abs=1.5)
    saved = [M.Annotation.from_record(r) for r in w.repo.annotations_for_series([vp.series_uid])]
    assert any(a.kind == "ellipse" and abs(a.points[1][0] - 160) < 1.5 for a in saved)
    # medidas não vão para outro corte
    vp.step(1)
    assert vp.frame_annotations() == []


def test_freehand_and_escape(viewer):
    app, w, tab, vp = viewer
    tab.set_left_tool("polygon")
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, _w(vp, 50, 50))
    for x, y in ((80, 50), (100, 70), (100, 100), (70, 110), (50, 90)):
        QTest.mouseMove(vp, _w(vp, x, y))
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, _w(vp, 50, 90))
    (poly,) = vp.frame_annotations()
    assert poly.done and len(poly.points) >= 5
    # ângulo começado e cancelado com Esc não fica salvo
    tab.set_left_tool("angle")
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, _w(vp, 150, 150))
    assert vp._draft is not None
    QTest.keyClick(vp, Qt.Key_Escape)
    assert vp._draft is None and len(vp.frame_annotations()) == 1
