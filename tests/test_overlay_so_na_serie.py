"""0.99.65 — pedido dele: a segmentação dos órgãos abdominais e os níveis linfonodais aparecem só na série em que
foram calculados (em outra série a mesma posição em mm não cai no mesmo lugar)."""
from types import SimpleNamespace as NS

import numpy as np
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence

from ipe.imaging import overlays as O
from ipe.ui.viewer.overlay_draw import active_overlays


def _vp(series_uid, study="E1", frame_series=None):
    f = NS(series_uid=frame_series if frame_series is not None else series_uid)
    return NS(overlays=[], study_uid=study, series_uid=series_uid, current_frame=lambda: f)


def test_filtro_e_serie_do_quadro():
    so = O.OverlayObject("a", "SEG", "Fígado", study_uid="E1", so_series="S1")
    livre = O.OverlayObject("b", "SEG", "Nódulos", study_uid="E1")
    outro_exame = O.OverlayObject("c", "SEG", "x", study_uid="E2")
    vp = _vp("S1")
    vp.overlays = [so, livre, outro_exame]
    assert active_overlays(vp) == [so, livre]
    vp2 = _vp("S2")
    vp2.overlays = [so, livre]
    assert active_overlays(vp2) == [livre]                      # outra série: a máscara do órgão não aparece
    vp3 = _vp("mpr:S1:axial", frame_series="")
    vp3.overlays = [so]
    assert O.serie_do_quadro(vp3) == "S1" and active_overlays(vp3) == [so]   # o MPR da mesma série, sim
    so.enabled = False
    assert active_overlays(vp) == [livre]


def test_serie_referenciada_e_por_segmento():
    ds = Dataset()
    rs = Dataset()
    rs.SeriesInstanceUID = "1.2.3"
    ds.ReferencedSeriesSequence = Sequence([rs])
    assert O.serie_referenciada(ds) == "1.2.3" and O.serie_referenciada(Dataset()) == ""
    obj = O.OverlayObject("k", "SEG", "Órgãos", study_uid="E", series_ref="1.2.3", so_series="1.2.3")
    m = np.ones((2, 2), bool)
    obj.masks = [O.MaskFrame(m, (1, 2, 3), "Fígado", None, None, None), O.MaskFrame(m, (3, 2, 1), "Baço", None, None, None)]
    partes = O.por_segmento(obj)
    assert len(partes) == 2 and all(p.so_series == "1.2.3" and p.series_ref == "1.2.3" for p in partes)


def test_seg_dos_orgaos_fica_na_serie_ao_abrir(env, tmp_path):
    from PySide6.QtWidgets import QApplication

    from ipe.ai import totalseg as TS
    from ipe.ai import totalseg_saida as SAIDA
    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    from test_totalseg import _rodar, _serie
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie = _serie(env, tmp_path)
    t, res = _rodar(env, uid, serie)
    try:
        SAIDA.gravar(t, res, db, paths.storage)
    finally:
        t.limpar()
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.show()
    try:
        assert w.handle_external({"accession": "ORG01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        tab.load_overlay_objects()
        segs = [o for o in tab.overlay_objects if o.source == "SEG"]
        assert segs and all(o.so_series == serie for o in segs), [(o.label, o.so_series) for o in segs]
        vp = next(v for v in tab.viewports if v.series_uid == serie)
        assert any(o in active_overlays(vp) for o in segs)
        vp_falso = _vp("outra", study=uid)
        vp_falso.overlays = list(vp.overlays)
        assert not any(o in active_overlays(vp_falso) for o in segs)
        assert TS.DESC_SEG in __import__("ipe.ui.viewer.onco", fromlist=["SO_NA_SERIE"]).SO_NA_SERIE
    finally:
        w.close()
