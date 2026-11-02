"""Paisagem na subtração (dinâmica e DSA) e MIP/média temporal da dinâmica (0.99.22, plano AW M10/M11)."""
import numpy as np
import pytest

from ipe.imaging import dsa as D
from ipe.imaging.dynamic import MAPS, DynamicMaps, DynamicSet
from ipe.imaging.series import FrameCache
from ipe.importer.scanner import Importer
from test_dynamic import _sets
from test_measure_tools import make_dynamic
from test_phases import _series, dyn  # noqa: F401


def test_mip_e_media_temporal(env, tmp_path):
    paths, db, repo = env
    uid = make_dynamic(tmp_path / "d", one_series=False)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    ss, phases = _sets(repo, uid)
    mp = DynamicMaps(DynamicSet(phases, [s.description for s in ss]), FrameCache(64))
    m = mp.compute(1)
    assert m["mipt"][32, 32] == pytest.approx(180)            # 280 − 100: o pico, em qualquer fase
    assert m["medt"][32, 32] == pytest.approx(152.5)          # média de 260, 280, 250, 220 − 100
    assert m["mipt"][2, 2] == pytest.approx(0) and m["medt"][2, 2] == pytest.approx(0)
    assert "mipt" in MAPS and mp.window("mipt")[0] >= 180
    from ipe.ui.viewer import dinamica_config as DC
    assert "mipt" in DC.VISTAS and "mipt" in DC.MAPAS


def test_paisagem_da_dsa():
    live = np.full((20, 20), 100.0)
    live[5:8, 5:8] = 40                     # um osso (absorve mais)
    mask = live.copy()
    sub = D.subtract(live, mask, "lin")
    assert np.allclose(sub, 0)
    p = D.paisagem(sub, live, 0.3)
    assert p[6, 6] > 0 and abs(p[0, 0]) < 1e-6     # o osso volta, o fundo continua no zero
    assert np.allclose(D.paisagem(sub, live, 0.0), sub)
    assert D.paisagem(sub, live, 0.3, invert=True)[6, 6] < 0


def test_paisagem_na_subtracao_da_dinamica(dyn):  # noqa: F811
    app, w, uid = dyn
    ss = _series(w, uid)
    w.open_study(uid)
    tab = w.all_viewer_tabs()[-1]
    vp = tab.viewports[0]
    tab.group_series([s.series_uid for s in ss], "Dinâmica mama", vp)
    vp.set_phase(2)
    vp.set_subtract(True)
    assert vp._img.pixels[32, 32] == pytest.approx(180) and vp._img.pixels[5, 5] == pytest.approx(0)
    vp.set_paisagem(0.2)
    assert vp._img.pixels[32, 32] == pytest.approx(280 - 0.8 * 100)
    assert vp._img.pixels[5, 5] == pytest.approx(50 * 0.2)      # o fundo ganha 20% da anatomia
    assert "20% anatomia" in vp.fase_texto()
    vp.set_phase(3)                                              # vale nas outras fases
    assert vp._img.pixels[5, 5] == pytest.approx(10)
    vp.set_paisagem(0)
    assert vp._img.pixels[5, 5] == pytest.approx(0)


def test_paisagem_no_menu_da_dsa(dyn):  # noqa: F811
    app, w, uid = dyn
    ss = _series(w, uid)
    w.open_study(uid, [ss[0].series_uid])
    vp = w.all_viewer_tabs()[-1].viewports[0]
    vp.set_dsa(on=True, mask=0, avg=1, mode="lin")
    vp.set_dsa(paisagem=0.3)
    assert "paisagem 30%" in vp.dsa_status()
