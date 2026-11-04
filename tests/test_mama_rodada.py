"""0.99.48 — rodada da mama: fases fora da conta e linha de base pela média das pré (plano AW M4),
descritores da curva (BAT, lavagem, iAUC90, MRT; M8 / MITK) e ROI espelhada (M14)."""
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.imaging import dynamic as D
from ipe.imaging.dynamic import DynamicMaps, DynamicSet
from ipe.imaging.measure import Annotation
from ipe.imaging.series import FrameCache, build_frames
from ipe.importer.scanner import Importer
from test_measure_tools import make_dynamic


def _dset(env, tmp_path):
    paths, db, repo = env
    uid = make_dynamic(tmp_path / "d", one_series=False)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    ss = sorted(repo.series_for_study(uid), key=lambda s: s.series_number)
    phases = [build_frames(repo.instances_for_series(s.series_uid), s.series_uid) for s in ss]
    return DynamicSet(phases, [s.description for s in ss]), uid


# ------------------------------------------------------------------ descritores
def test_descritores_numa_curva_conhecida():
    e = np.array([0, 100, 150, 120], np.float32)
    t = np.array([0, 1, 2, 3], np.float32)
    d = D.descritores(e, t)
    assert float(d["bat"]) == pytest.approx(9.0)                    # 15% em 0,15 min
    assert float(d["wash"]) == pytest.approx(30.0)                  # 150 → 120 em 1 min
    assert float(d["iauc"]) == pytest.approx(50 + 0.5 * (100 + 125) * 0.5)
    assert float(d["mrt"]) == pytest.approx(580 / 310 * 60, rel=1e-4)


def test_descritores_sem_realce_dao_zero():
    d = D.descritores(np.zeros((4, 3, 3), np.float32), np.array([0, 1, 2, 3], np.float32))
    for k in D.DESCRITORES:
        assert np.all(d[k] == 0)


def test_mapas_novos_e_colunas(env, tmp_path):
    dset, _uid = _dset(env, tmp_path)
    mp = DynamicMaps(dset, FrameCache(64))
    m = mp.compute(1)
    for k in D.DESCRITORES:
        assert k in m and k in D.MAPS
    # lesão: [100, 260, 280, 250, 220] → realce [0, 160, 180, 150, 120]; fora: 50 constante
    assert m["wash"][32, 32] == pytest.approx(30.0)
    assert m["bat"][32, 32] == pytest.approx(0.18 / 1.6 * 60, rel=1e-3)   # 18% em 160%/min
    assert m["bat"][2, 2] == 0 and m["wash"][2, 2] == 0
    st = mp.curve_stats(mp.curve(1, point=(32, 32)))
    assert st["wash"] == pytest.approx(30.0) and st["mrt"] > 0 and st["iauc"] > 0
    from ipe.ui.viewer.dynamic import DynamicPanel
    assert DynamicPanel.COLS[-4:] == ["BAT", "Lavagem", "iAUC90", "MRT"]


# ------------------------------------------------------------------ fases fora da conta
def test_fase_fora_da_conta_muda_a_conta(env, tmp_path):
    dset, _uid = _dset(env, tmp_path)
    mp = DynamicMaps(dset, FrameCache(64))
    assert mp.compute(1)["msi"][32, 32] == pytest.approx(160, rel=1e-3)
    assert mp.set_excluidas([1]) == ""
    m = mp.compute(1)
    assert m["msi"][32, 32] == pytest.approx(90, rel=1e-3)          # 0 → 180 em 2 min
    st = mp.curve_stats(mp.curve(1, point=(32, 32)))
    assert len(st["enh"]) == 5                                     # o gráfico continua com as 5
    assert "fase 2" in mp.avisos_das_fases()[-1]
    for ruim, pedaco in (([2], "inicial"), ([4], "tardia"), ([0], "pré-contraste"), ([9], "fora")):
        assert pedaco in mp.validar_exclusao(ruim)
    mp2 = DynamicMaps(dset, FrameCache(64), excluidas=[3])
    assert mp2.excluidas == {3}
    with pytest.raises(ValueError):
        DynamicMaps(dset, FrameCache(64), excluidas=[2])


def test_duas_seguidas_nao():
    from ipe.ui.viewer.dynamic import validar_exclusao
    assert "seguidas" in validar_exclusao(8, 0, 3, 7, [0], [4, 5])
    assert validar_exclusao(8, 0, 3, 7, [0], [4, 6]) == ""
    assert "duas fases" in validar_exclusao(4, 0, 2, 3, [0], [1]) or validar_exclusao(4, 0, 2, 3, [0], [1]) == ""


def test_linha_de_base_pela_media_das_pre(env, tmp_path):
    dset, _uid = _dset(env, tmp_path)
    so_uma = DynamicMaps(dset, FrameCache(64), pre=1, early=2, late=4)
    media = DynamicMaps(dset, FrameCache(64), pre=1, early=2, late=4, fases_pre=[0, 1])
    v = so_uma.curve(1, point=(32, 32))
    assert so_uma.curve_stats(v)["initial"] == pytest.approx((280 - 260) / 260 * 100, rel=1e-3)
    assert media.curve_stats(v)["initial"] == pytest.approx((280 - 180) / 180 * 100, rel=1e-3)
    assert any("uma fase pré" in a for a in so_uma.avisos_das_fases())
    assert not any("uma fase pré" in a for a in media.avisos_das_fases())


def test_dialogo_e_aba(env, sample_dir, tmp_path):
    from ipe.ui.main_window import MainWindow
    from ipe.ui.viewer.dynamic import DynamicDialog
    paths, db, repo = env
    _dset_, uid = _dset(env, tmp_path)
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1400, 850)
    w.show()
    try:
        w.browser.refresh()
        w.open_study(uid)
        tab = w.all_viewer_tabs()[-1]
        app.processEvents()
        dlg = DynamicDialog(tab)
        dlg.e_excluir.setText("4")
        dlg.c_base_media.setChecked(True)
        p = dlg.params()
        assert p["excluidas"] == [3] and p["fases_pre"] == [0]
        dlg.e_excluir.setText("x")
        assert dlg.excluidas() is None
        dlg.close()
        assert tab.start_dynamic(dlg.dset, p)
        mp = tab.dyn.maps
        assert mp.excluidas == {3}
        assert "fora da conta: fase 4" in tab.dyn.summary_line()
        assert "uma fase pré" in tab.dyn.panel.title.text()
        tab.dyn.panel.fill_views("msi")
        textos = [tab.dyn.panel.c_view.itemText(i) for i in range(tab.dyn.panel.c_view.count())]
        assert any("(fora da conta)" in t for t in textos) and any(t.startswith("Lavagem") for t in textos)
        tab.close_dynamic()
    finally:
        w.close()


# ------------------------------------------------------------------ ROI espelhada
@pytest.fixture()
def aba(env, sample_dir):
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


def test_espelhar_no_axial(aba):
    from ipe.imaging import clonar_roi as CR
    app, w, repo = aba
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 1)
    app.processEvents()
    vp = tab.viewports[0]
    vp.go_to(30)
    xm, como = CR.eixo_de_simetria(vp)
    assert xm is not None and abs(xm) < 15 and "corpo" in como
    roi = vp._new_annotation("ellipse", [(60.0, 120.0), (80.0, 140.0)])
    vp._finish(roi)
    cp = vp.espelhar_roi(roi)
    assert cp is not None and vp.index == 30 and cp.text == "Contralateral"
    a = [vp.pixel_to_patient(x, y) for x, y in roi.points]
    b = [vp.pixel_to_patient(x, y) for x, y in cp.points]
    for p, q in zip(a, b):
        assert q[0] == pytest.approx(2 * xm - p[0], abs=0.01) and q[1] == pytest.approx(p[1], abs=0.01)
    assert roi.meta["contralateral"]["media"] is not None
    from ipe.imaging import measure as M
    linhas = M.linhas_extras(roi, vp._img.pixels, vp.measure_spacing(roi))
    assert any(x.startswith("lesão / contralateral") for x in linhas)
    from PySide6.QtCore import QPointF
    c = vp.image_to_widget(QPointF(70.0, 120.0))
    assert any(x.text().startswith("Espelhar no outro lado") for x in vp.build_context_menu(c).actions())


def test_espelhar_no_sagital_vai_ao_outro_corte(aba):
    from ipe.imaging import clonar_roi as CR
    app, w, repo = aba
    w.handle_external({"accession": "ACC2001"})
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 1)
    app.processEvents()
    vp = tab.viewports[0]
    sag = next(s for s in tab.series if "sagital" in (s.description or "").lower())
    tab.load_series_into(vp, sag.series_uid)
    app.processEvents()
    xs = sorted(float(f.position[0]) for f in vp.frames)
    xm, como = CR.eixo_de_simetria(vp)
    assert xm == pytest.approx((xs[0] + xs[-1]) / 2) and "sagitais" in como
    alvo = int(np.argmin([abs(float(f.position[0]) - (-40.0)) for f in vp.frames]))
    vp.go_to(alvo)
    roi = vp._new_annotation("rect", [(60.0, 60.0), (90.0, 90.0)])
    vp._finish(roi)
    cp = vp.espelhar_roi(roi)
    assert cp is not None
    assert float(vp.current_frame().position[0]) == pytest.approx(2 * xm + 40.0, abs=2.6)
