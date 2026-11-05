"""0.99.64 — mama: fusão de qualquer mapa por arrastar (AW M6), mapas de tempo em cor (AW M9) e achados BI-RADS
por marcadores CC/MLO com a distância ao mamilo (PV 20)."""
import numpy as np
import pytest
from pydicom.uid import generate_uid
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.imaging import dynamic as D
from ipe.imaging.dynamic import DynamicMaps
from ipe.imaging.series import FrameCache
from ipe.importer.scanner import Importer
from ipe.reporting import marcadores_mama as MM


# ------------------------------------------------------------------ marcadores (sem Qt)
def test_posicao_hora_e_quadrante():
    # CC direita, parede à direita da imagem (x = 800), mamilo em (300, 500), 0,1 mm/pixel
    p = MM.posicao("CC", "R", (400, 300), (300, 500), (0.1, 0.1), "right", 800)
    assert p["plano"] == "CC" and p["dist_mm"] == pytest.approx(22.4, abs=0.1)
    assert p["desloc_mm"] == pytest.approx(20.0)                # acima do mamilo = lateral
    assert p["prof_frac"] == pytest.approx(0.2)                  # 10 mm de 50 até a parede
    # o PatientOrientation pode dizer que para baixo é lateral (direita: lateral = R)
    p2 = MM.posicao("CC", "R", (400, 300), (300, 500), (0.1, 0.1), "right", 800, ["A", "R"])
    assert p2["desloc_mm"] == pytest.approx(-20.0)
    m = MM.posicao("MLO", "R", (420, 300), (300, 500), (0.1, 0.1), "right", 800)
    assert m["plano"] == "MLO" and m["desloc_mm"] == pytest.approx(20.0)     # acima = superior
    loc = MM.localizar([p, m])
    assert loc["quadrante"] == "quadrante superolateral" and loc["hora"] in (10, 11)
    assert loc["terco"] == "terço anterior" and not loc["so_uma_vista"] and loc["vistas"] == "CC+MLO"
    assert loc["local"].startswith("quadrante superolateral, às ")
    # a mesma posição na mama esquerda fica do outro lado do relógio
    assert MM.hora(20, 20, "L") in (1, 2) and MM.hora(-20, -20, "L") in (7, 8) and MM.hora(0, 30, "R") == 12
    assert MM.quadrante(3, 2, 12) == "região retroareolar"
    assert MM.quadrante(3, 25, 40) == "união dos quadrantes superiores"
    assert MM.quadrante(-25, -25, 40) == "quadrante inferomedial"
    so = MM.localizar([p])
    assert so["so_uma_vista"] and so["hora"] is None and so["quadrante"] == "metade lateral"
    f = MM.achado_birads(1, loc)
    assert f["side"] == "D" and f["distance"].endswith("cm") and f["location"] == loc["local"]
    from ipe.reporting import birads as B
    assert "do mamilo" in B.finding_text(f) and "Mama direita" in B.finding_text(f)


# ------------------------------------------------------------------ mapas em cor
def test_mapas_em_cor(env, tmp_path):
    from test_mama_rodada import _dset
    dset, _uid = _dset(env, tmp_path)
    mp = DynamicMaps(dset, FrameCache(64))
    assert {"tcor", "fases"} <= set(D.MAPS) and set(D.COMPOSTOS) == {"tcor", "fases"}
    img = mp.image("tcor", 1)
    assert img.is_color and img.pixels.shape[-1] == 3 and img.pixels.dtype == np.uint8
    lesao, fora = img.pixels[32, 32], img.pixels[2, 2]
    assert lesao.max() > 100 and fora.max() == 0                    # o tecido que não realça fica preto
    # o pico da lesão é na 3ª fase (de 5): matiz entre o vermelho e o azul, não vermelho puro
    assert not (lesao[0] > 200 and lesao[1] < 30 and lesao[2] < 30)
    fz = mp.image("fases", 1).pixels[32, 32]
    assert fz.max() > 100
    assert mp.window("tcor") == (256.0, 128.0)
    with pytest.raises(KeyError):                                   # não entra nas contas por ROI
        mp.compute(1)["tcor"]
    from ipe.imaging.dynamic import _hsv_para_rgb
    rgb = _hsv_para_rgb(np.array([0.0, 1 / 3, 2 / 3]), np.ones(3), np.ones(3))
    assert np.allclose(rgb, np.eye(3), atol=1e-6)


def test_fusao_por_arrastar_e_de_quadro(env, tmp_path):
    from test_mama_rodada import _dset
    from ipe.ui.main_window import MainWindow
    from ipe.ui.viewer.dynamic import DynamicDialog
    paths, db, repo = env
    _d, uid = _dset(env, tmp_path)
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1400, 850)
    w.show()
    try:
        w.open_study(uid)
        tab = w.all_viewer_tabs()[-1]
        app.processEvents()
        dlg = DynamicDialog(tab)
        p = dlg.params()
        dlg.close()
        assert tab.start_dynamic(dlg.dset, p)
        sess = tab.dyn
        a = tab.viewports[0]
        if len(tab._shown()) < 2:
            tab.set_layout(1, 2)
            app.processEvents()
        b = tab.viewports[1]
        sess.show_view(a, "ph:0")
        sess.show_view(b, "ser")
        app.processEvents()
        assert tab._dyn_do_quadro(b) is not None
        fu = tab.fundir_quadro(b, a)                     # o SER por cima do outro quadro
        assert fu is not None and a.fusion is fu and fu.label == "SER"
        tab.remove_fusion(a)
        sess.show_view(b, "tcor")
        app.processEvents()
        assert b._img.is_color
        assert tab.fundir_quadro(b, a) is None           # o mapa em cor não se funde
        # a zona de soltar e a série de verdade
        assert a._zone_for(a.fuse_rect().center()) == "fuse" and a._zone_for(a.join_rect().center()) == "join"
        serie = next(s for s in tab.series if s.study_uid == uid)
        tab.close_dynamic()
        app.processEvents()
        v0 = tab.viewports[0]
        assert tab.fundir_por_arrastar(v0, serie.series_uid) is not None and v0.fusion is not None
        assert tab.fundir_por_arrastar(v0, f"key:{uid}") is None
        menu = v0.build_context_menu(v0.rect().center())
        assert any(a_.text() == "Fundir este quadro sobre…" for a_ in menu.actions()) or len(tab._shown()) == 1
    finally:
        w.close()


# ------------------------------------------------------------------ marcadores na tela
@pytest.fixture()
def janela(env, tmp_path):
    from test_mama_p2 import _mg
    paths, db, repo = env
    pat = {"name": "MAMA^P3", "id": "MP3", "birth": "19700101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20260101", "accession": "MP3001",
             "description": "MAMOGRAFIA RASTREAMENTO", "for": generate_uid()}
    d = tmp_path / "mg"
    d.mkdir()
    for k, (lado, view) in enumerate((("R", "CC"), ("L", "CC"), ("R", "MLO"), ("L", "MLO"))):
        _mg(d, lado, view, study, pat, k + 1, 0.5)
    Importer(db, paths.storage).import_paths([d])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1500, 950)
    w.show()
    assert w.handle_external({"accession": "MP3001"}) == "aberto"
    tab = w.tabs.currentWidget()
    QApplication.processEvents()
    yield app, w, tab, study["uid"]
    for t in w.all_viewer_tabs():
        for rw in getattr(t, "_report_windows", {}).values():
            rw._dirty = False
            rw.close()
    w.close()


def test_marcadores_cc_mlo_e_laudo(janela):
    from ipe.imaging import mammo as M
    from PySide6.QtCore import QPointF
    app, w, tab, st = janela
    s = tab.mg_session
    s.proto.setdefault("steps", M.passos_do_protocolo(s.proto))
    s.proto["steps"][s.step] = {"name": "t", "rows": 1, "cols": 2, "cells": ["CCD", "MLOD"]}
    s.apply_step(s.step)
    app.processEvents()
    cc, mlo = tab.viewports[0], tab.viewports[1]
    mx, my = cc.mamilo_imagem()
    # um ponto 150 px (15 mm) para dentro da mama e 200 px acima do mamilo
    dentro = -150 if cc.chest_image_side() == "left" else 150
    menu = cc.build_context_menu(cc.image_to_widget(QPointF(mx + dentro, my - 200)))
    assert any(a.text() == "Achado BI-RADS aqui" for a in menu.actions())
    ann = tab.marcar_achado_mama(cc, (mx + dentro, my - 200))
    assert ann is not None and ann.text == "A1" and ann.meta["plano"] == "CC"
    assert ann.meta["dist_mm"] == pytest.approx(25.0, abs=0.5) and ann.meta["desloc_mm"] == pytest.approx(20.0)
    mx2, my2 = mlo.mamilo_imagem()
    dentro2 = -150 if mlo.chest_image_side() == "left" else 150
    assert tab.marcar_achado_mama(mlo, (mx2 + dentro2, my2 - 200), 1) is not None
    d = tab.abrir_marcadores_mama()
    assert d.t.rowCount() == 1
    loc = d.locs[1]
    assert loc["quadrante"] == "quadrante superolateral" and loc["vistas"] == "CC+MLO" and loc["dist_mm"] == 25.0
    # marcar de novo na mesma vista troca a marca (não duplica)
    tab.marcar_achado_mama(cc, (mx + dentro, my - 100), 1)
    d.recarregar()
    assert len(d.marcas[1]) == 2
    d.tipos[1].setCurrentText("Calcificações")
    assert d.mandar_ao_laudo() == 1
    rw = tab._report_windows[st]
    fs = rw.birads.findings
    assert len(fs) == 1 and fs[0]["type"] == "Calcificações" and fs[0]["location"].startswith("quadrante superolateral")
    assert d.mandar_ao_laudo() == 1 and len(rw.birads.findings) == 1     # mandar de novo troca, não duplica
    d.close()


def test_duplo_clique_amplia_e_reenquadra(janela):
    """0.99.76 — pedido dele: no 1x1 do duplo clique a mama ficava alta e cortada (o zoom e o alinhamento pelo
    mamilo vinham dos quadros escondidos)."""
    from ipe.imaging import mammo as M
    app, w, tab, st = janela
    s = tab.mg_session
    s.proto.setdefault("steps", M.passos_do_protocolo(s.proto))
    s.proto["steps"][s.step] = {"name": "t", "rows": 1, "cols": 2, "cells": ["CCD", "CCE"]}
    s.apply_step(s.step)
    for _ in range(5):
        app.processEvents()
    cc = tab.viewports[0]
    tab.toggle_maximize(cc)
    import time
    for _ in range(20):
        app.processEvents()
        time.sleep(0.01)
    tab._refazer_enquadre()
    app.processEvents()
    assert tab._maximized is cc and cc.mg_dy == 0.0
    h, wi = cc._img.pixels.shape[:2]
    x0, y0, x1, y1 = cc.quadrant_box()
    from PySide6.QtCore import QPointF
    topo, base = cc.image_to_widget(QPointF(x0, y0)), cc.image_to_widget(QPointF(x1, y1))
    assert -2 <= min(topo.y(), base.y()) and max(topo.y(), base.y()) <= cc.height() + 2   # a mama inteira na tela
    tab.toggle_maximize(cc)
    app.processEvents()
    assert tab._maximized is None
