"""Incerteza ao lado da medida, aviso de cortes grossos e ROI de referência (0.99.22, plano AW 6 e 7)."""
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from ipe.imaging import measure as M
from ipe.imaging.measure import Annotation


def test_resolucao_na_direcao_da_linha():
    sp = (5.0, 0.7)                       # sagital de um axial de 5 mm: linha 5 mm, coluna 0,7 mm
    assert M.resolucao_na_direcao((0, 0), (10, 0), sp) == pytest.approx(0.7)       # horizontal
    assert M.resolucao_na_direcao((0, 0), (0, 4), sp) == pytest.approx(5.0)        # vertical
    assert 0.7 < M.resolucao_na_direcao((0, 0), (10, 2), sp) < 5.0


def test_aviso_de_cortes_grossos_e_de_espessura():
    v = Annotation("line", ("x", 0), [(0, 0), (0, 4)])
    assert any("cortes grossos" in t for t in M.linhas_extras(v, None, (5.0, 0.7)))
    h = Annotation("line", ("x", 0), [(0, 0), (10, 0)])
    assert M.linhas_extras(h, None, (5.0, 0.7)) == []
    curta = Annotation("line", ("x", 0), [(0, 0), (5, 0)])                    # 3,5 mm num corte de 5
    assert any("espessura" in t for t in M.linhas_extras(curta, None, (0.7, 0.7), espessura=5.0))
    assert M.linhas_extras(curta, None, (0.7, 0.7), espessura=1.0) == []
    assert M.linhas_extras(h, None, (0.5, 0.5), incerteza=True) == ["± 0.5 mm"]


def test_incerteza_da_area():
    r = Annotation("rect", ("x", 0), [(0, 0), (10, 10)])
    t = M.linhas_extras(r, None, (1.0, 1.0), incerteza=True)
    assert t == ["Área ± 20.0 mm²"]                   # perímetro 40 × pixel 1 / 2
    e = Annotation("ellipse", ("x", 0), [(0, 0), (10, 10)])
    assert M.perimetro_mm("ellipse", e.points, (1.0, 1.0)) == pytest.approx(np.pi * 10, rel=1e-3)


def test_percentual_da_referencia():
    pix = np.zeros((40, 40), np.float32)
    pix[0:10, 0:10] = 200
    pix[20:30, 20:30] = 100
    ref = Annotation("rect", ("x", 0), [(0, 0), (10, 10)], meta={"referencia": True})
    les = Annotation("rect", ("x", 0), [(20, 20), (30, 30)])
    assert M.linhas_extras(ref, pix, (1.0, 1.0)) == ["Referência (100%)"]
    assert M.linhas_extras(les, pix, (1.0, 1.0), ref_media=200.0) == ["50% da referência"]
    assert M.linhas_extras(les, pix, (1.0, 1.0), ref_media=-5.0) == []


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


def test_marcar_a_referencia_no_quadro(tc):
    app, w, tab, vp = tc
    fk = vp.frame_key()
    a = Annotation("ellipse", fk, [(100, 100), (120, 120)], study_uid=tab.study_uid, series_uid=vp.series_uid)
    b = Annotation("ellipse", fk, [(30, 30), (50, 50)], study_uid=tab.study_uid, series_uid=vp.series_uid)
    vp.annotations += [a, b]
    vp.marcar_referencia(a)
    assert vp.roi_de_referencia() is a and a.meta["ref_media"] == pytest.approx(
        M.media_da_roi(a, vp._img.pixels, vp.measure_spacing(a)))
    vp.marcar_referencia(b)                                   # só uma por série
    assert vp.roi_de_referencia() is b and "referencia" not in a.meta
    vp.link_lesion(b, None)                                   # desligar lesão não tira a referência
    assert b.meta.get("referencia")
    vp.grab()
    vp.marcar_referencia(None)
    assert vp.roi_de_referencia() is None
    m = vp.build_context_menu(None)
    assert m is not None
