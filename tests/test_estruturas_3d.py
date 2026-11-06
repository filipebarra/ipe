"""Estruturas segmentadas como superfícies coloridas no 3D (0.99.82; item 5 da lista do MedMLX).

Pedido dele (06/11/2026): "faça então as etapas 1 a 5" — a 5 é a figura (a) do MedMLX: os órgãos do
TotalSegmentator em superfície, junto com o osso.
"""
import numpy as np
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.imaging import overlays as O
from ipe.imaging.render3d import Renderer3D, compor_estruturas, rotulos_na_grade
from ipe.importer.scanner import Importer
from test_render3d import _Vol


def _cena():
    """'Osso' numa laje na frente (y pequeno = anterior) e um 'órgão' esférico atrás dela."""
    d = np.full((60, 60, 60), -900.0)
    d[:, 8:11, 20:40] = 800.0                         # laje de osso, anterior, só no meio
    r = Renderer3D(_Vol(d), max_dim=60)
    z, y, x = np.mgrid[0:60, 0:60, 0:60]
    esfera = ((z - 30.0) ** 2 + (y - 30.0) ** 2 + (x - 30.0) ** 2) < 100       # raio 10
    rim = ((z - 30.0) ** 2 + (y - 30.0) ** 2 + (x - 48.0) ** 2) < 25           # raio 5, à esquerda
    mv1 = O.MaskVolume(esfera, np.zeros(3), np.eye(3), (200, 60, 60), "fígado")
    mv2 = O.MaskVolume(rim, np.zeros(3), np.eye(3), (60, 200, 60), "rim")
    return r, mv1, mv2


def test_mascaras_na_grade_do_3d():
    r, mv1, mv2 = _cena()
    lab, cores = rotulos_na_grade(r, [mv1, mv2])
    assert cores == [(200, 60, 60), (60, 200, 60)]
    assert set(np.unique(lab)) == {0, 1, 2}
    # o volume (em voxels da grade, passo 1 mm) bate com o da máscara
    assert abs(int((lab == 1).sum()) - int(mv1.mascara.sum())) < 0.03 * mv1.mascara.sum()
    # máscara deslocada e com passo diferente: cai no lugar certo
    pequena = np.ones((4, 4, 4), bool)
    mv3 = O.MaskVolume(pequena, np.array([10.0, 12.0, 14.0]), np.eye(3) * 2, (1, 2, 3), "x")
    lab3, _ = rotulos_na_grade(r, [mv3])
    zz, yy, xx = np.nonzero(lab3)
    assert xx.min() >= 9 and xx.max() <= 18 and yy.min() >= 11 and zz.min() >= 13


def test_superficie_colorida_e_escondida_atras_do_osso():
    r, mv1, mv2 = _cena()
    assert r.set_labels([mv1, mv2]) == 2
    rgb, cob, prof = r.render_labels(0, 0, (60, 60))           # vista anterior
    assert cob.sum() > 80                          # ~1,7 mm por pixel: esfera de 10 mm ≈ 100 px
    # no centro, a cor é a do fígado (vermelho domina)
    c = rgb[30, 30].astype(int)
    assert c[0] > c[1] and c[0] > 60
    # o rim aparece do lado esquerdo do paciente = direita da tela na vista anterior
    verde = (rgb[..., 1].astype(int) > rgb[..., 0].astype(int) + 30) & (cob > 0)
    assert verde.any()
    xs = np.nonzero(verde)[1]
    assert abs(xs.mean() - 30) > 6                      # ~18 mm do centro ≈ 10 px
    # com o VR do osso na frente, o fígado fica apagado (atrás); fora da laje, forte
    base = r.render("vr", 0, 0, (60, 60), 180.0, 900.0, "vr_bone", 0.35)
    junto = compor_estruturas(base, 180, 900, (rgb, cob, prof), r.last_depth, r._last["st"], 0.85, 0.3)
    so_cor = compor_estruturas(np.zeros_like(base), 180, 900, (rgb, cob, prof), None, 1.0, 0.85, 0.3)
    assert junto.shape == base.shape and junto.dtype == np.uint8
    atras = np.isfinite(r.last_depth) & (cob > 0)
    if atras.any():
        yy, xx = np.nonzero(atras)
        assert abs(int(junto[yy[0], xx[0], 0]) - int(base[yy[0], xx[0], 0])) <= \
            abs(int(so_cor[yy[0], xx[0], 0]) - 0)
    # MIP (cinza) vira RGB com as estruturas por cima
    mip = r.render("mip", 0, 0, (60, 60))
    out = compor_estruturas(mip, -900, 800, (rgb, cob, prof))
    assert out.ndim == 3 and out[30, 30, 0] > out[30, 30, 2]


def test_respeita_o_corte_do_volume():
    r, mv1, mv2 = _cena()
    r.set_labels([mv1, mv2])
    antes = r.render_labels(0, 0, (60, 60))[1].sum()
    r.clip[4] = 45                                     # z de 45 para cima: some tudo
    depois = r.render_labels(0, 0, (60, 60))[1].sum()
    assert antes > 0 and depois == 0
    r.clip_reset()
    r.set_labels([])
    assert r.labels is None and r.render_labels(0, 0, (60, 60))[1].sum() == 0


def test_no_quadro_3d(env, sample_dir):
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    Importer(db, paths.storage).import_paths([sample_dir])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1200, 800)
    w.show()
    try:
        assert w.handle_external({"accession": "ACC1001"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        a = tab.viewports[0]
        tab._activate(a)
        uid = a.series_uid
        vol = tab.volume_for(uid) if hasattr(tab, "volume_for") else None
        v = tab.open_3d("vr")
        assert v is not None
        assert not v.ha_estruturas()
        assert v.mostrar_estruturas(True).startswith("Não há estrutura")
        assert not tab.render3d_bar.a_estr.isEnabled()
        # uma "segmentação" no meio do volume
        r = v.r
        gz, gy, gx = r.shape
        m = np.zeros((gz, gy, gx), bool)
        m[gz // 3:2 * gz // 3, gy // 3:2 * gy // 3, gx // 3:2 * gx // 3] = True
        mv = O.MaskVolume(m, r.lo.copy(), np.eye(3) * r.step, (255, 0, 0), "teste")
        obj = O.OverlayObject(key="x", source="Segmentação", label="teste", study_uid=v.study_uid, volumes=[mv])
        tab.overlay_objects.append(obj)
        tab.render3d_bar.sync()
        assert tab.render3d_bar.a_estr.isEnabled()
        tab.render3d_bar.a_estr.trigger()
        app.processEvents()
        assert v.estruturas and r.labels is not None
        img = v.image()
        assert img.is_color
        px = np.asarray(img.pixels)
        assert (px[..., 0].astype(int) - px[..., 2].astype(int)).max() > 80     # vermelho apareceu
        # o objeto desligado some do 3D na próxima vez que liga
        tab.render3d_bar.a_estr.trigger()
        assert not v.estruturas
        obj.enabled = False
        assert not v.ha_estruturas()
        _ = vol
    finally:
        w.close()
