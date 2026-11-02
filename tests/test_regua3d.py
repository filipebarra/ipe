"""Régua 3D: ponto A num corte, ponto B em outro; distância com dx/dy/dz (0.99.22, plano AW 8)."""
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from ipe.imaging import measure as M


@pytest.fixture()
def tc(env, sample_dir):
    from test_pedidos_29_10 import _sem_protocolos
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, _sem_protocolos(Settings(paths.settings_file)))
    w.resize(1200, 800)
    w.show()
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 1)
    app.processEvents()
    yield app, w, tab, tab.viewports[0]
    w.close()


def _ponto(vp, xy):
    a = vp._new_annotation("ponto3d", [xy])
    vp._finish(a)
    return a


def test_dois_cortes_dao_distancia_3d(tc):
    app, w, tab, vp = tc
    assert "ruler3d" in tab.tool_actions
    pa = vp.pixel_to_patient(100, 100)
    a = _ponto(vp, (100, 100))
    assert M.labels(a, None, None)[0].startswith("Régua 3D: ponto A")
    vp.go_to(vp.index + 4)
    pb = vp.pixel_to_patient(110, 100)
    b = _ponto(vp, (110, 100))
    esperado = float(np.linalg.norm(np.asarray(pb) - np.asarray(pa)))
    assert b.meta["dist"] == pytest.approx(esperado) and b.meta["plano"] == "3D"
    assert a.meta["dist"] == pytest.approx(esperado)
    lab = M.labels(b, None, None)
    assert "(3D)" in lab[0] and "C-C" in lab[1]
    c = _ponto(vp, (50, 50))                       # o terceiro clique começa uma régua nova
    assert c.meta["papel"] == "A"


def test_mesmo_corte_e_2d(tc):
    app, w, tab, vp = tc
    _ponto(vp, (10, 10))
    b = _ponto(vp, (40, 50))
    assert b.meta["plano"] == "2D"


def test_ponto_a_apagado_recomeca(tc):
    app, w, tab, vp = tc
    a = _ponto(vp, (10, 10))
    vp.delete_annotation(a)
    b = _ponto(vp, (40, 50))
    assert b.meta["papel"] == "A"
