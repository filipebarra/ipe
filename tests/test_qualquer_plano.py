"""0.99.16: as marcações de IA e segmentação aparecem em qualquer plano reformatado.

Pedido dele: *"aplique a opção de ver as marcações quando reformatar para todas as IAs e
segmentações que já temos e que teremos"*. SEG (órgãos, cefalometria, CAD de fora) e RTSTRUCT
são guardados corte a corte, no plano da aquisição; agora viram um volume em mm na hora de
desenhar num plano que não é o deles.
"""
import numpy as np
import pytest

from ipe.imaging import overlays as O


def _sagital(x):
    """Plano sagital em x: pos do pixel (0,0), linha = +y (posterior), coluna = −z (para baixo)."""
    return (np.array([x, -60.0, 120.0]), np.array([0, 1.0, 0]), np.array([0, 0, -1.0]), np.array([1.0, 0, 0]))


def test_mascaras_axiais_viram_volume_e_cortam_no_sagital():
    # um cilindro vertical (raio 10 mm, z de 20 a 60) em cortes axiais de 2 mm, recortados como o parse_seg faz
    ori = np.array([1.0, 0, 0, 0, 1.0, 0])
    masks = []
    for z in np.arange(20, 61, 2.0):
        yy, xx = np.mgrid[0:21, 0:21]
        m = np.hypot(xx - 10, yy - 10) <= 10
        masks.append(O.MaskFrame(m, (255, 0, 0), "baço", np.array([-10.0, -10.0, z]), ori, (1.0, 1.0)))
    vols = O.volumes_das_mascaras(masks)
    assert len(vols) == 1
    mv = vols[0]
    pos, row, col, n = _sagital(0.0)
    corte = mv.fatia(pos, row, col, n, (1.0, 1.0), (180, 120))
    assert corte is not None
    x0, y0, mf = corte
    ys, xs = np.nonzero(mf.mask)
    altura = (ys.max() - ys.min() + 1) * 1.0
    largura = (xs.max() - xs.min() + 1) * 1.0
    assert altura == pytest.approx(42, abs=2.5) and largura == pytest.approx(21, abs=1.5)
    assert mv.fatia(*_sagital(30.0), (1.0, 1.0), (180, 120)) is None     # fora do cilindro: nada
    # o paralelo continua sendo desenhado pela máscara do corte
    assert O.paralela(masks[0], np.array([0, 0, 1.0])) and not O.paralela(masks[0], np.array([1.0, 0, 0]))


def test_contornos_rtstruct_viram_volume():
    planar = []
    t = np.linspace(0, 2 * np.pi, 40, endpoint=False)
    for z in np.arange(0, 31, 3.0):
        pts = np.column_stack([8 * np.cos(t), 8 * np.sin(t), np.full_like(t, z)])
        planar.append(O.Graphic("polygon", [], "GTV", pts, (0, 255, 0)))
    planar.append(O.Graphic("polyline", [], "linha", np.array([[0, 0, 0], [5, 5, 5]], float)))
    vols = O.volumes_dos_contornos(planar)
    assert len(vols) == 1 and vols[0].label == "GTV"
    corte = vols[0].fatia(*_sagital(0.0)[:4], (1.0, 1.0), (200, 160))
    assert corte is not None
    ys, xs = np.nonzero(corte[2].mask)
    assert (xs.max() - xs.min() + 1) == pytest.approx(16, abs=2)              # diâmetro
    assert (ys.max() - ys.min() + 1) == pytest.approx(31, abs=4)              # 0 a 30 mm


def test_cache_e_objeto():
    ori = np.array([1.0, 0, 0, 0, 1.0, 0])
    m = np.ones((5, 5), bool)
    obj = O.OverlayObject("k", "SEG", "x", masks=[O.MaskFrame(m, (1, 2, 3), "a", np.array([0, 0, float(z)]), ori,
                                                              (1.0, 1.0)) for z in range(5)])
    v1 = O.volumes_derivados(obj)
    assert v1 and O.volumes_derivados(obj) is v1                              # não refaz a cada desenho


def test_seg_da_cefalometria_no_sagital_reformatado(env, tmp_path):
    """Ponta a ponta: a SEG gravada (cortes axiais) aparece no quadro reformatado em sagital."""
    from PySide6.QtWidgets import QApplication

    from ipe.ai import cefalometria as CF
    from ipe.ai import cefalometria_saida as CS
    from ipe.ai import totalseg as TS
    from ipe.core.config import Settings
    from ipe.imaging.series import FrameCache
    from ipe.ui.main_window import MainWindow
    from ipe.ui.viewer import overlay_draw as D
    from test_cefalometria import _exame
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie = _exame(env, tmp_path)
    t = TS.Trabalho(repo, FrameCache(256), None, uid, serie, simular=True)
    t.tarefas_proprias, t.min_cortes, t.modalidades = CF.tarefas, CF.MIN_CORTES, ("CT",)
    t.preparar()
    try:
        t.rodar_aqui()
        rot, versao, _s = t.ler_rotulos()
        CS.gravar(t, CF.calcular(t.vol, rot), versao, db, paths.storage, repo=repo)
    finally:
        t.limpar()
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.show()
    try:
        assert w.handle_external({"accession": "CAV01"}) == "aberto"
        tab = w.tabs.currentWidget()
        for _ in range(20):
            app.processEvents()
        palato = next(o for o in tab.overlay_objects if o.source == "SEG" and o.label == "Palato mole")
        vp = next(v for v in tab.viewports if v.frames)
        tab.active = vp
        assert tab.reformatar(vp, "Sagital")
        vp.go_to_point(np.array([0.0, -10.0, 80.0]))
        pos, row, col, n = vp.plane()
        assert not any(O.paralela(mf, n) for mf in palato.masks)            # SEG axial, quadro sagital
        h, w_ = vp._img.pixels.shape[:2]
        cortes = [mv.fatia(pos, row, col, n, vp._spacing(), (h, w_)) for mv in O.volumes_derivados(palato)]
        assert any(c is not None and c[2].mask.sum() > 50 for c in cortes)
        # e o desenho de verdade passa por ele sem erro
        from PySide6.QtGui import QImage, QPainter
        img = QImage(vp.width(), vp.height(), QImage.Format_ARGB32)
        pt = QPainter(img)
        D.draw_masks(vp, pt)
        D.draw_graphics(vp, pt)
        pt.end()
    finally:
        w.close()
