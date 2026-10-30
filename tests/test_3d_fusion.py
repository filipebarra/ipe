"""Fusão, renderização 3D e MPR curvo."""
import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.imaging.curved import CurvedPlane
from ipe.imaging.fusion import Fusion
from ipe.imaging.render3d import Renderer3D, rotation
from ipe.imaging.series import FrameCache, build_frames
from ipe.imaging.volume import MPRPlane, build_volume, sample_trilinear
from ipe.importer.scanner import Importer


@pytest.fixture()
def vol(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    uid = repo.find_study_uids(accession="ACC1001")[0]
    s = repo.series_for_study(uid)[0]
    return build_volume(build_frames(repo.instances_for_series(s.series_uid), s.series_uid), FrameCache(512))


def test_fusion_resample(vol):
    fu = Fusion(vol, "CT", cmap="hot", alpha=0.6)
    ax = MPRPlane(vol, 0)
    k = 30
    img = ax.image(k).pixels
    vals, stride = fu.values(ax.position(k), ax.orientation[:3], ax.orientation[3:], ax.row_spacing,
                             ax.col_spacing, *img.shape, max_side=512)
    assert stride == 1 and np.allclose(vals, img, atol=1e-3)
    rgba = fu.rgba(vals)
    assert rgba.shape == img.shape + (4,)
    assert (rgba[..., 3][vals <= fu.lo] == 0).all() and (rgba[..., 3][vals > fu.lo] == 153).all()
    assert fu.value_at(ax.position(k)) == pytest.approx(float(img[0, 0]), abs=1e-3)


def test_render3d(vol):
    u, v, d = rotation(0, 0)
    assert np.allclose(u, [1, 0, 0]) and np.allclose(v, [0, 0, -1]) and np.allclose(d, [0, 1, 0])
    assert np.allclose(rotation(90, 0)[2], [-1, 0, 0], atol=1e-9)
    r = Renderer3D(vol, max_dim=96)
    mip = r.render("mip", 0, 0, (96, 96))
    assert mip.shape == (96, 96) and abs(float(mip.max()) - float(vol.data.max())) < 60
    minip = r.render("minip", 30, 20, (64, 64), fast=True)
    assert minip.max() <= mip.max()
    vr = r.render("vr", 45, 15, (80, 80), lo=150, hi=900, cmap="vr_bone", opacity=0.35)
    assert vr.shape == (80, 80, 3) and vr.dtype == np.uint8 and vr.max() > 100


def test_curved_straight_line(vol):
    ax = MPRPlane(vol, 0)
    z = ax.position(30)[2]
    p0, p1 = np.array([-100.0, 0.0, z]), np.array([100.0, 0.0, z])
    cpr = CurvedPlane(vol, [p0, (p0 + p1) / 2, p1], ax.normal)
    assert cpr.length_mm == pytest.approx(200, abs=2)
    img = cpr.image(0).pixels
    mid = img[:, cpr.cols // 2]
    ijk = ((cpr.path - vol.origin) @ np.linalg.inv(vol.matrix()).T).astype(np.float32)
    direct = sample_trilinear(vol.data, ijk)
    assert np.allclose(mid, direct, atol=1e-2)
    assert np.allclose(cpr.image(18).pixels[:, cpr.cols // 2], direct, atol=1e-2)   # gira em volta do caminho


def test_gui_fusion_3d_curved(env, sample_dir):
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    Importer(db, paths.storage).import_paths([sample_dir])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1300, 800)
    w.show()
    w.browser.refresh()
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 1)
    app.processEvents()
    a = tab.viewports[0]
    tab._activate(a)
    prior = repo.find_study_uids(accession="ACC0901")[0]
    tab.add_study(prior)
    puid = repo.series_for_study(prior)[0].series_uid
    tab.set_layout(1, 1)
    a = tab.viewports[0]
    tab._activate(a)
    app.processEvents()
    fu = tab.set_fusion(a, puid)
    assert fu is not None and a.fusion is fu and tab.fusion_bar.isVisibleTo(tab)
    q, stride = a._fusion_image()
    assert q.width() > 10
    tab.fusion_alpha.setValue(30)
    assert fu.alpha == pytest.approx(0.3)
    a.grab()
    tab.remove_fusion(a)
    assert a.fusion is None
    # MPR curvo com cliques
    tab.set_left_tool("curve")
    c = a.rect().center()
    for dx in (-120, 0, 120):
        QTest.mouseClick(a, Qt.LeftButton, Qt.NoModifier, c + QPoint(dx, dx // 4))
    assert len(a._curve_pts) == 3
    QTest.mouseDClick(a, Qt.LeftButton, Qt.NoModifier, c + QPoint(120, 30))
    app.processEvents()
    b = tab.viewports[1]
    assert tab._layout == (1, 2) and isinstance(b.mpr_plane, CurvedPlane) and len(b.frames) == 36
    assert a.curve_paths and b._img is not None
    res = tab.save_reconstruction(b)
    assert res and len(res[1]) == 36
    # 3D
    tab._activate(a)
    tab.set_left_tool("wl")
    v3 = tab.open_3d("mip")
    assert v3 is not None and a.render3d is v3 and a._img is not None
    assert tab.render3d_bar.isVisibleTo(tab)
    v3.set_mode("vr")
    assert a._img is not None and a._img.is_color            # VR sai colorido
    recado = v3.to_film(a)
    assert recado
    w.film_composer().dirty = False
    tab.close_3d(a)
    assert a.render3d is None and a.frames
    w.close()
