"""Novas medidas, navegação até as medidas, curva tempo-intensidade e barra com ícones."""
import math

import numpy as np
import pytest
from pydicom.uid import MRImageStorage, generate_uid
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog, QToolButton

from ipe.core.config import Settings
from ipe.core.sample_data import _base, _mono, _save
from ipe.imaging import measure as M
from ipe.importer.scanner import Importer


def test_pure_calculations():
    assert M.cobb_deg((0, 0), (10, 0), (0, 5), (10, 15), None) == pytest.approx(45)
    assert M.cobb_deg((0, 0), (10, 0), (0, 5), (-10, 0), None) == pytest.approx(26.565, abs=0.01)
    assert M.polyline_mm([(0, 0), (3, 4), (3, 10)], (2, 2)) == pytest.approx(22)
    cal = M.Annotation("calibration", ("x", 0), [(0, 0), (0, 50)], text="100")
    assert M.calibration_spacing(cal) == (2.0, 2.0)
    px = np.arange(100, dtype=np.float32).reshape(10, 10)
    assert M.pixel_value(px, (3.7, 2.2)) == 23
    st = M.roi_stats(px, "rect", [(2, 2), (4, 4)], None)
    assert st.n == 4 and st.mean == pytest.approx((22 + 23 + 32 + 33) / 4)
    ctr = M.Annotation("ctr", ("x", 0), [(10, 5), (40, 5), (0, 8), (80, 8)])
    assert M.labels(ctr, None, (1, 1))[-1] == "ICT 0.38"
    h = M.Annotation("height", ("x", 0), [(0, 0), (4, 10)])
    assert M.labels(h, None, (0.5, 0.5))[0] == "Δ vertical 5.0 mm"
    assert M.spine_label("T12", 1) == "L1" and M.spine_label("S5", 3) == "Cóccix"
    r = M.tic_analysis([0, 60, 120, 240, 360], [100, 200, 220, 250, 280])
    assert r["curve_type"].startswith("I ") and r["initial_class"] == "rápido"
    r = M.tic_analysis([0, 60, 120, 240, 360], [100, 130, 140, 141, 139])
    assert r["curve_type"].startswith("II") and r["initial_class"] == "lento"


def make_dynamic(folder, phases=5, slices=3, one_series=True):
    """RM dinâmica sintética: lesão que realça rápido e lava (washout)."""
    pat = {"name": "DINAMICA^Teste", "id": "DYN1", "birth": "19800101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20260101", "accession": "DYN001",
             "description": "RM MAMA DINAMICA", "for": generate_uid()}
    curve = [100, 260, 280, 250, 220][:phases]
    yy, xx = np.mgrid[0:64, 0:64]
    lesion = ((xx - 32) ** 2 + (yy - 32) ** 2) < 64
    series = {"uid": generate_uid(), "number": 10, "description": "DYN"}
    for ph in range(phases):
        if not one_series:
            series = {"uid": generate_uid(), "number": 10 + ph, "description": f"DYN fase {ph}"}
        for k in range(slices):
            ds = _base(MRImageStorage, pat, study, series, "MR")
            ds.InstanceNumber = ph * slices + k + 1
            ds.ImagePositionPatient = [-50.0, -50.0, 10.0 * k]
            ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
            ds.PixelSpacing = [1.0, 1.0]
            ds.SliceThickness = 3.0
            ds.AcquisitionTime = f"1000{ph:02d}".replace(f"00{ph:02d}", f"{ph:02d}00")  # 10:00, 10:01…
            img = np.full((64, 64), 50.0)
            img[lesion] = curve[ph]
            _mono(ds, img, signed=False)
            _save(ds, folder / f"dyn_{ph}")
    return study["uid"]


@pytest.fixture()
def viewer(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1400, 850)
    w.show()
    yield app, w
    w.close()


def _open(w, acc):
    w.handle_external({"accession": acc})
    tab = w.all_viewer_tabs()[-1]
    tab.set_layout(1, 1)
    QApplication.processEvents()
    return tab, tab.viewports[0]


def _w(vp, x, y):
    return vp.image_to_widget(QPointF(x, y)).toPoint()


def _drag(vp, a, b, steps=6):
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, steps + 1):
        QTest.mouseMove(vp, a + (b - a) * i / steps)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, b)


def test_new_tools_draw_and_persist(viewer, monkeypatch):
    app, w = viewer
    tab, vp = _open(w, "ACC1001")
    tab.set_left_tool("rect")
    _drag(vp, _w(vp, 60, 60), _w(vp, 100, 90))
    tab.set_left_tool("probe")
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, _w(vp, 128, 128))
    tab.set_left_tool("polyline")
    for x, y in ((20, 200), (60, 200), (60, 240)):
        QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, _w(vp, x, y))
    QTest.keyClick(vp, Qt.Key_Return)
    tab.set_left_tool("cobb")
    _drag(vp, _w(vp, 150, 20), _w(vp, 220, 20))
    _drag(vp, _w(vp, 150, 60), _w(vp, 220, 130))
    tab.set_left_tool("height")
    _drag(vp, _w(vp, 30, 30), _w(vp, 40, 70))
    tab.set_left_tool("ctr")
    _drag(vp, _w(vp, 100, 150), _w(vp, 160, 150))
    _drag(vp, _w(vp, 40, 170), _w(vp, 220, 170))
    tab.set_left_tool("pencil")
    _drag(vp, _w(vp, 10, 10), _w(vp, 50, 20))
    monkeypatch.setattr(QInputDialog, "getItem", staticmethod(lambda *a, **k: ("L3", True)))
    tab.set_left_tool("spine")
    for y in (100, 120, 140):
        QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, _w(vp, 240, y))
    QTest.keyClick(vp, Qt.Key_Escape)                  # Esc termina a rotulagem (mantém)
    kinds = sorted(a.kind for a in vp.frame_annotations())
    assert kinds == sorted(["rect", "probe", "polyline", "cobb", "height", "ctr", "pencil", "spine"])
    assert all(a.done for a in vp.frame_annotations())
    by = {a.kind: a for a in vp.frame_annotations()}
    sp = vp.measure_spacing()
    assert M.labels(by["cobb"], None, sp)[0].startswith("Cobb 4")          # ~45°
    assert M.polyline_mm(by["polyline"].points, sp) == pytest.approx(120, abs=1.5)   # 80 px × 1,5 mm
    assert M.labels(by["ctr"], None, sp)[-1] == "ICT 0.33"
    assert "HU" in M.labels(by["probe"], vp._img.pixels, sp, vp.modality)[0]
    assert len(by["spine"].points) == 3 and by["spine"].text == "L3"
    assert w.repo.count_annotations(tab.study_uid) == 8
    vp.grab()                                            # desenha tudo sem erro


def test_calibration_changes_measurements(viewer, monkeypatch):
    app, w = viewer
    tab, vp = _open(w, "ACC1001")
    tab.set_left_tool("measure")
    _drag(vp, _w(vp, 20, 20), _w(vp, 120, 20))
    line = vp.frame_annotations()[0]
    assert M.length_mm(*line.points, vp.measure_spacing()) == pytest.approx(150, abs=1.5)
    from ipe.ui.viewer import annotate as ANN
    monkeypatch.setattr(ANN, "pedir_calibracao", lambda *a, **k: (50.0, "serie"))
    tab.set_left_tool("calibration")
    _drag(vp, _w(vp, 20, 60), _w(vp, 70, 60))          # 50 px = 50 mm -> 1 mm/px
    assert vp.is_calibrated() and vp.measure_spacing() == pytest.approx((1.0, 1.0), rel=0.03)
    assert M.length_mm(*line.points, vp.measure_spacing()) == pytest.approx(100, abs=3)
    assert vp.escala_texto() == "Escala: calibrada nesta imagem"
    vp.go_to(vp.index + 1)                             # no corte seguinte, vale pela série
    assert vp.is_calibrated() and vp.escala_texto() == "Escala: calibrada na série"
    # a mesma calibração marcada como "só esta imagem" para de valer nos outros cortes
    for a in vp.annotations:
        if a.kind == "calibration":
            a.meta["escopo"] = "imagem"
    assert not vp.is_calibrated()


def test_continuous_off_returns_to_window(viewer):
    app, w = viewer
    tab, vp = _open(w, "ACC1001")
    tab.continuous_action.setChecked(False)
    tab.set_left_tool("ellipse")
    _drag(vp, _w(vp, 60, 60), _w(vp, 100, 90))
    assert tab.left_tool == "wl"
    tab.continuous_action.setChecked(True)


def test_navigation_and_strip_marks(viewer):
    app, w = viewer
    tab, vp = _open(w, "ACC1001")
    tab.set_left_tool("measure")
    for idx in (10, 40):
        vp.go_to(idx)
        _drag(vp, _w(vp, 20, 20), _w(vp, 80, 20))
    assert vp.annotated_indices() == [10, 40]
    vp.go_to(0)
    tab.actions_by_id["annot.next"].trigger()
    assert vp.index == 10
    tab.actions_by_id["annot.next"].trigger()
    assert vp.index == 40
    tab.actions_by_id["annot.prev"].trigger()
    assert vp.index == 10
    items = vp.annotation_summary()
    assert [i for i, _t in items] == [10, 40] and "Régua" in items[0][1]
    # a tira de séries mostra a marca
    item = next(tab.strip.item(i) for i in range(tab.strip.count())
                if tab.strip.item(i).data(Qt.UserRole) == vp.series_uid)
    assert item.toolTip().startswith("2 imagem(ns) com medida")
    # abrir a série de outro lugar direto na medida
    vp.go_to(30)
    tab.open_series_at_annotation(vp.series_uid)
    assert vp.index == 10
    # barra de posição: clique vai para a imagem
    r = vp.posbar_rect()
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, r.center().toPoint())
    assert abs(vp.index - 30) <= 1
    # o banco lembra das marcas
    assert w.repo.annotation_counts([vp.series_uid]) == {vp.series_uid: 2}


@pytest.mark.parametrize("one_series", [True, False])
def test_time_intensity_curve(viewer, tmp_path, monkeypatch, one_series):
    app, w = viewer
    uid = make_dynamic(tmp_path / "dyn", one_series=one_series)
    Importer(w.db, w.paths.storage).import_paths([tmp_path / "dyn"])
    w.browser.refresh()
    w.open_study(uid)
    tab = w.all_viewer_tabs()[-1]
    tab.set_layout(1, 1)
    vp = tab.viewports[0]
    if not one_series:
        tab.load_series_into(vp, tab.series[0].series_uid)
    vp.go_to(0)
    shown = {}
    from ipe.ui.viewer import tic
    monkeypatch.setattr(tic.TicDialog, "exec", lambda self: shown.update(r=self.result) or 0)
    tab.set_left_tool("tic")
    _drag(vp, _w(vp, 26, 26), _w(vp, 38, 38))
    assert "r" in shown, "a curva deveria abrir ao terminar a ROI"
    res = shown["r"]
    assert len(res["enhancement"]) == 5
    assert res["curve_type"].startswith("III") and res["initial_class"] == "rápido"
    ann = next(a for a in vp.frame_annotations() if a.kind == "tic")
    assert "washout" in ann.text


def test_toolbar_with_icons(viewer):
    app, w = viewer
    tab, vp = _open(w, "ACC1001")
    buttons = tab.toolbar.findChildren(QToolButton)
    styled = [b for b in buttons if b.toolButtonStyle() == Qt.ToolButtonTextUnderIcon]
    assert len(styled) >= 14 and all(not b.icon().isNull() for b in styled)
    # o botão Medidas mostra a última ferramenta escolhida e mantém o menu
    tab.set_left_tool("cobb")
    assert tab.measure_button.defaultAction() is tab.tool_actions["cobb"]
    assert tab.measure_button.menu() is tab.measure_menu
    texts = [a.text() for a in tab.measure_menu.actions()]
    for name in ("Ângulo de Cobb", "ROI retangular", "Curva tempo-intensidade", "Linha de calibração",
                 "Intensidade (valor do pixel)", "Lápis", "Polilinha"):
        assert name in texts
    # Desde a 0.65 nenhuma ferramenta tem tecla de fábrica (ele zerou a lista); o que tem de
    # continuar funcionando é aplicar a tecla que ele escolher.
    assert tab.tool_actions["probe"].shortcut().toString() == ""
    tab.settings.set("shortcuts", {"tool.probe": "V"})
    tab.apply_shortcuts()
    assert tab.tool_actions["probe"].shortcut().toString() == "V"


def test_icone_do_mouse_no_lugar_do_texto_azul(viewer):
    """O overlay traz o ícone do mouse (hotspot) e o balão lista o que cada botão faz."""
    app, w = viewer
    tab, vp = _open(w, "ACC1001")
    vp.grab()                                   # força um paint para registrar os hotspots
    assert "mouse" in vp._hotspots
    rect = vp._hotspots["mouse"]
    assert rect.width() < 30 and rect.height() < 40      # é um ícone, não um texto comprido
    assert vp._hotspot_at(QPointF(rect.center())) == "mouse"
    pares = dict(vp.mouse_actions())
    assert pares["Esquerdo"] == "Janela/nível"
    assert "Zoom" in pares["Direito"] and "Pan" in pares["Meio"]
    assert "Rolar cortes" in pares["Roda"] and "Zoom" in pares["Ctrl+roda"]
    tab.set_left_tool("measure")
    assert dict(vp.mouse_actions())["Esquerdo"] == "Régua"
    vp._hover = "mouse"
    vp.grab()                                   # com o balão aberto, não pode quebrar
