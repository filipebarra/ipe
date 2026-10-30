"""Mamografia: protocolos por etapas, zoom por quadrante, lupa e botão Monitor."""
import numpy as np
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMenu

from ipe.core.config import Settings
from ipe.imaging import mammo as M

_mask_real = M.implant_mask          # guardado no import: o teste do clique troca M.implant_mask
from ipe.importer.scanner import Importer


def test_codes_and_steps():
    assert M.parse_code("CCD") == M.Cell("CC", "R", 0)
    assert M.parse_code("mloe ant") == M.Cell("MLO", "L", 1)
    assert M.parse_code("XCCLD ant2") == M.Cell("XCCL", "R", 2)
    assert M.parse_code("E").view == "ANY" and M.parse_code("xyz") is None
    for text, rows, cols, cells in (("1x2 (CCD,xCCE)", 1, 2, ["CCD", "CCE"]),
                                    ("1x2 (MLOD,xMLOE)", 1, 2, ["MLOD", "MLOE"]),
                                    ("2x2 (CCD,MLODxCCE,MLOE)", 2, 2, ["CCD", "CCE", "MLOD", "MLOE"]),
                                    ("CCD, CCD ant x CCE, CCE ant", 2, 2, ["CCD", "CCE", "CCD ant", "CCE ant"]),
                                    ("XCCLD x XCCLE", 1, 2, ["XCCLD", "XCCLE"])):
        st = M.parse_step(text)
        assert (st["rows"], st["cols"], st["cells"]) == (rows, cols, cells), text
        assert M.parse_step(M.step_text(st)) == st
    img = np.zeros((100, 80))
    img[:, 40:] = 1000
    assert M.chest_wall_side(img) == "right" and M.chest_wall_side(img[:, ::-1]) == "left"


def _window(env, sample_dir):
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    st = Settings(paths.settings_file)
    w = MainWindow(paths, st, repo=repo, db=db)
    w.resize(1400, 850)
    w.show()
    w.browser.refresh()
    return w, repo, st


def test_mg_protocol_in_viewer(env, sample_dir):
    app = QApplication.instance() or QApplication([])
    w, repo, st = _window(env, sample_dir)
    uid = repo.find_study_uids(accession="ACC3001")[0]
    imgs = M.read_images(repo, uid)
    assert {(i.side, i.view) for i in imgs} == {("R", "CC"), ("L", "CC"), ("R", "MLO"), ("L", "MLO")}
    assert w.handle_external({"accession": "ACC3001"}) == "aberto"
    tab = w.tabs.currentWidget()
    s = tab.mg_session
    assert s is not None and tab.mg_bar.isVisibleTo(tab) and tab._layout == (2, 2)
    labels = [v.series_label.split()[0:2] for v in tab.viewports[:4]]
    assert labels == [["CC", "D"], ["CC", "E"], ["MLO", "D"], ["MLO", "E"]]
    assert all(len(v.frames) == 1 for v in tab.viewports[:4])
    # parede torácica para o centro e encostada na borda
    a, b = tab.viewports[0], tab.viewports[1]
    assert a.align_edge == "right" and b.align_edge == "left"
    ra, rb = a._image_rect(), b._image_rect()
    assert abs(ra.right() - a.width()) < 1.5 and abs(rb.left()) < 1.5
    # próxima etapa: 1×2 CC
    tab.actions_by_id["mg.next"].trigger()
    assert s.step == 1 and tab._layout == (1, 2)
    assert [v.series_label.split()[0] for v in tab.viewports[:2]] == ["CC", "CC"]
    tab.mg_next(1)
    assert [v.series_label.split()[0] for v in tab.viewports[:2]] == ["MLO", "MLO"]
    # etapa com anterior (não há anterior de MG): quadro vazio avisando
    tab.mg_session.apply_step(3)
    assert "não encontrada" in tab.viewports[2].empty_note and not tab.viewports[2].frames
    tab.mg_next(-1)
    assert s.step == 2
    # zoom por quadrante sincronizado, em quadrantes da mama (não da tela)
    tab.mg_session.apply_step(1)
    a, b = tab.viewports[:2]
    assert a.align_edge == "right" and b.align_edge == "left"

    def parede_na_tela(v):
        """Onde a parede torácica da mama cai na tela (0 = borda esquerda, 1 = direita)."""
        bx0, by0, bx1, by1 = v.anat_box()
        x = bx1 if v.chest_image_side() == "right" else bx0
        return v.image_to_widget(QPointF(x, (by0 + by1) / 2)).x() / v.width()

    for idx in (0, 1):                 # quadrantes posteriores
        tab.mg_quadrant(a, idx)
        assert a.state.zoom >= 2 and b.state.zoom >= 2
        # o alinhamento da mamografia continua: a parede torácica fica na borda em que já estava
        assert a.chest_screen_side() == "right" and b.chest_screen_side() == "left"
        assert parede_na_tela(a) == pytest.approx(1.0, abs=0.02)
        assert parede_na_tela(b) == pytest.approx(0.0, abs=0.02)
        # os dois mostram o mesmo lugar da mama (metade de cima no 0, de baixo no 1)
        fa, fb = a.anat_center(), b.anat_center()
        assert fa[0] == pytest.approx(fb[0], abs=0.05) and fa[1] == pytest.approx(fb[1], abs=0.05)
        assert (fa[1] < 0.5) == (idx == 0)
    a.fit(); b.fit()
    # um só comando: cada clique vai para o próximo quadrante e, no fim, volta à imagem inteira
    tab.set_left_tool("quadzoom")
    seen = []
    for _ in range(3):                # só duas etapas: superior, inferior e volta à imagem inteira
        QTest.mouseClick(a, Qt.LeftButton, Qt.NoModifier, a.rect().center())
        seen.append((a.quad_idx, round(a.state.zoom, 2) >= 2, b.quad_idx))
    assert seen == [(0, True, 0), (1, True, 1), (-1, False, -1)]
    tab.actions_by_id["mg.quad_next"].trigger()
    assert a.quad_idx == 0 and b.state.zoom >= 2
    tab.actions_by_id["mg.quad_prev"].trigger()
    assert a.quad_idx == -1 and a.state.zoom == pytest.approx(1)
    # 1:1 e lupa
    a.zoom_actual_pixels()
    assert a.fit_scale() * a.state.zoom == pytest.approx(1)
    a.fit()
    tab.set_left_tool("loupe")
    c = a.rect().center()
    QTest.mousePress(a, Qt.LeftButton, Qt.NoModifier, c)
    assert a._loupe is not None
    a.grab()
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtCore import QPoint as P
    ev = QWheelEvent(QPointF(c), QPointF(a.mapToGlobal(c)), P(0, 0), P(0, 120), Qt.LeftButton, Qt.NoModifier,
                     Qt.ScrollUpdate, False)
    z0 = a.loupe_zoom
    a.wheelEvent(ev)
    assert a.loupe_zoom == z0 + 0.5
    QTest.mouseRelease(a, Qt.LeftButton, Qt.NoModifier, c)
    assert a._loupe is None
    # "Editar protocolos…" é a última linha da lista de etapas (não um botão à parte)
    barra = tab.mg_bar
    assert not any(x.text().startswith("Editar protocolos") for x in barra.actions())
    combo, n = barra.c_step, len(tab.mg_session.steps)
    assert combo.count() == n + 2                       # etapas + separador + editar
    assert combo.itemText(n + 1).startswith("Editar protocolos")
    etapa = tab.mg_session.step
    abriu = []
    tab.edit_mg_protocols = lambda: abriu.append(True)
    combo.setCurrentIndex(n + 1)
    barra._step_chosen(n + 1)
    assert abriu == [True] and tab.mg_session.step == etapa    # abre o editor e não troca de etapa
    assert combo.currentIndex() == etapa
    barra._step_chosen(0)                               # e continua trocando de etapa normalmente
    assert tab.mg_session.step == 0
    tab.close_mg()
    assert not tab.mg_bar.isVisibleTo(tab)
    w.close()


def test_mg_editor_and_monitor_button(env, sample_dir):
    from ipe.ui.viewer.mammo_view import MgProtocolsEditor
    app = QApplication.instance() or QApplication([])
    w, repo, st = _window(env, sample_dir)
    ed = MgProtocolsEditor(st)
    assert ed.l_protos.count() == 2          # CEM (com filtro na descrição) e o geral
    ed.l_protos.setCurrentRow(1)
    assert ed.l_steps.count() == 7           # uma lista de etapas só, do conjunto
    ed._new_step()
    ed.e_text.setText("2x2 (CCD,MLODxCCE,MLOE)")
    ed._text_edited()
    assert (ed.s_rows.value(), ed.s_cols.value()) == (2, 2) and len(ed.cells) == 4
    ed.cells[1].setCurrentText("XCCLE")
    ed.save()
    steps = M.mg_protocols(st)[1]["steps"]
    assert steps[-1]["cells"] == ["CCD", "XCCLE", "MLOD", "MLOE"]
    # só um protocolo novo com uma etapa
    ed._new_proto()
    ed.e_name.setText("Rastreamento rápido")
    ed._store_proto()
    ed.save()
    assert [p["name"] for p in M.mg_protocols(st)] == ["Mamografia com contraste (CEM)",
                                                       "Mamografia (4 incidências, com anterior)", "Rastreamento rápido"]
    # botão Monitor na tela inicial
    hb = w.home_bar
    assert "monitor" in hb.buttons
    w.browser.table.selectRow(0)
    m = QMenu()
    hb._monitor_menu(m)
    assert any(a.text().startswith("Abrir o exame selecionado no monitor 1") for a in m.actions())
    rows = w.browser.selected_rows()
    assert w.open_on_monitor(rows[0].study_uid)
    assert w.detached and w.detached[0].viewer_tabs()
    w.reattach_all()
    w.close()


def _make_mg_single_series(folder):
    """MG com as 4 incidências numa série só, uma CC D repetida e uma tomossíntese da CC D (10 cortes)."""
    from pydicom.uid import generate_uid
    from ipe.core.sample_data import _base, _mono, _save
    pat = {"name": "TOMO^Teste", "id": "TOMO1", "birth": "19700101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20260915", "accession": "TOMO001", "description": "MAMOGRAFIA",
             "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 1, "description": "MAMOGRAFIA 2D"}
    h, w = 256, 200
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    k = 0
    for lat, view, t in (("R", "CC", "100000"), ("L", "CC", "100100"), ("R", "MLO", "100200"),
                         ("L", "MLO", "100300"), ("R", "CC", "100400")):
        k += 1
        ds = _base("1.2.840.10008.5.1.4.1.1.1.2", pat, study, series, "MG")
        ds.InstanceNumber, ds.ImageLaterality, ds.ViewPosition, ds.AcquisitionTime = k, lat, view, t
        ds.ImagerPixelSpacing = [0.1, 0.1]
        cx = w if lat == "R" else 0
        img = np.where(((xx - cx) / (w * 0.95)) ** 2 + ((yy - h / 2) / (h * 0.45)) ** 2 < 1, 1500 + k * 50, 100)
        _mono(ds, img, signed=False)
        _save(ds, folder / "mg2d")
    rseries = {"uid": generate_uid(), "number": 3, "description": "CESM SUB CC"}
    ds = _base("1.2.840.10008.5.1.4.1.1.1.2", pat, study, rseries, "MG")
    ds.InstanceNumber, ds.ImageLaterality, ds.ViewPosition, ds.AcquisitionTime = 1, "R", "CC", "100500"
    ds.ImagerPixelSpacing = [0.1, 0.1]
    img = np.where(((xx - w) / (w * 0.95)) ** 2 + ((yy - h / 2) / (h * 0.45)) ** 2 < 1, 900, 60)
    _mono(ds, img, signed=False)
    _save(ds, folder / "rec")
    tseries = {"uid": generate_uid(), "number": 2, "description": "TOMO R CC"}
    ds = _base("1.2.840.10008.5.1.4.1.1.13.1.3", pat, study, tseries, "MG")
    ds.InstanceNumber, ds.ImageLaterality, ds.ViewPosition = 1, "R", "CC"
    ds.PixelSpacing = [0.1, 0.1]
    vol = np.stack([np.where(((xx - w) / (w * 0.95)) ** 2 + ((yy - h / 2) / (h * 0.45)) ** 2 < 1, 1000 + 20 * z, 50)
                    for z in range(10)]).astype(np.uint16)
    _mono(ds, vol[0], signed=False)
    ds.NumberOfFrames = 10
    ds.PixelData = vol.tobytes()
    from ipe.core.sample_data import tomo_geometry
    tomo_geometry(ds, 10, thickness_mm=55.0, force_n=80.0, angle_deg=0.0, side="R")
    _save(ds, folder / "tomo")
    return study["uid"]


def test_scroll_same_view_and_tomo(env, tmp_path):
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    uid = _make_mg_single_series(tmp_path / "mg")
    Importer(db, paths.storage).import_paths([tmp_path / "mg"])
    imgs = M.read_images(repo, uid)
    tomo = [i for i in imgs if i.tomo]
    assert len(tomo) == 1 and tomo[0].frames == 10 and (tomo[0].side, tomo[0].view) == ("R", "CC")
    st = Settings(paths.settings_file)
    w = MainWindow(paths, st, repo=repo, db=db)
    w.resize(1300, 800)
    w.show()
    w.open_study(uid)
    tab = w.tabs.currentWidget()
    app.processEvents()
    assert tab.mg_session is not None and tab._layout == (2, 2)
    a = tab.viewports[0]                      # CC D: 2 imagens 2D + os 10 cortes da tomo, numa lista só
    assert len(a.frames) == 12 and "2 imagens + tomo 10 cortes" in a.series_label
    assert a.tomo_range == (2, 12) and a.index == 1          # começa na 2D mais recente
    assert not a.in_tomo() and a.mg_tomo and a.cine_bounce
    assert len(tab.viewports[1].frames) == 1  # CC E (sem tomo)
    assert tab.viewports[1].tomo_range is None
    # a janela ajustada na 2D não vai para a tomo (e volta ao retornar para a 2D)
    a.set_window(1234, 567)
    a.state.window_set = True
    a.step(1)
    assert a.in_tomo() and (a.state.width, a.state.level) != (1234, 567)
    tomo_win = (a.state.width, a.state.level)
    a.step(3)
    assert (a.state.width, a.state.level) == tomo_win          # mesma janela em todos os cortes
    a.go_to(1)
    assert (a.state.width, a.state.level) == (1234, 567)
    # rolar passa da 2D para a tomo sem botão
    a.step(1)
    assert a.index == 2 and a.in_tomo()
    assert "Tomo corte 1/10" in a._text_lines()["bl"][0][0]
    a.go_to(7)                                 # 6º corte da tomo
    assert a._img is not None and float(a._img.pixels.max()) == pytest.approx(1100)
    # cine só nos cortes da tomo, indo e voltando
    a.go_to(11)
    a._cine_tick()
    assert a.index == 10
    a.go_to(2)
    a._cine_dir = -1
    a._cine_tick()
    assert a.index == 3
    # espessura só vale nos cortes da tomo
    a.go_to(7)
    a.set_tomo_slab(5)
    assert float(a._img.pixels.max()) > 1100
    a.go_to(0)
    assert float(a._img.pixels.max()) < 1100 or not a.in_tomo()
    a.set_tomo_slab(1)
    # Shift+T só pula entre a 2D e o meio da tomo (sem botão na barra)
    tab._activate(a)
    tab.actions_by_id["mg.tomo"].trigger()
    assert a.index == 7 and len(a.frames) == 12
    tab.mg_toggle_tomo()
    assert a.index == 1
    assert not any(x.text() == "2D ⇄ Tomo" for x in tab.mg_bar.actions())
    # zoom por quadrante: a tomo cai no mesmo lugar da 2D ao rolar
    a.go_to(1)                                 # 2D
    tab.mg_quadrant(a, 0)                      # posterior e superior
    alvo = a.anat_center()
    assert a.state.zoom >= 2 and alvo[1] < 0.5
    zoom_2d = a.state.zoom
    a.go_to(7)                                 # corte da tomo
    assert a.in_tomo()
    assert a.state.zoom == pytest.approx(zoom_2d)
    fx, fy = a.anat_center()                   # mesmo ponto da mama, sem pular
    assert fx == pytest.approx(alvo[0], abs=0.03) and fy == pytest.approx(alvo[1], abs=0.03)
    # o outro quadrante continua valendo ao voltar para a 2D
    tab.mg_quadrant(a, 1)
    inferior = a.anat_center()
    assert inferior[1] > 0.5
    a.go_to(1)
    fx, fy = a.anat_center()
    assert fx == pytest.approx(inferior[0], abs=0.03) and fy == pytest.approx(inferior[1], abs=0.03)
    a.fit()
    assert a.anat_lock is None and a.quad_idx == -1

    # sincronização do zoom com o mouse (0.97.1): só com o botão "Zoom e pan", como nos outros exames
    b = tab.viewports[1]
    tab.mg_quadrant(a, -1)
    tab.hub.set_flag("sync_zoom", False)
    zoom_b = b.state.zoom
    a.state.zoom = 3.0
    a.sig.view_changed.emit(a, "zoom")
    assert b.state.zoom == pytest.approx(zoom_b)          # botão desligado: o outro não anda
    tab.hub.set_flag("sync_zoom", True)                   # ligado: acompanha no mesmo lugar da mama
    a.sig.view_changed.emit(a, "zoom")
    assert b.state.zoom == pytest.approx(3.0)
    pa, pb = a.anat_center(), b.anat_center()
    assert pa[0] == pytest.approx(pb[0], abs=0.05) and pa[1] == pytest.approx(pb[1], abs=0.05)

    # baixa energia ⇄ recombinada mantém o quadrante e o zoom
    tab.mg_quadrant(a, 1)                      # posterior e inferior
    antes, zoom = a.anat_center(), a.state.zoom
    assert a.quad_idx == 1 and zoom >= 2
    tab._activate(a)
    assert tab.mg_session.toggle_rec(a)
    assert a.mg_spec.rec and a.quad_idx == 1
    assert a.state.zoom == pytest.approx(zoom, rel=0.35)      # continua ampliado
    fx, fy = a.anat_center()
    assert fx == pytest.approx(antes[0], abs=0.05) and fy == pytest.approx(antes[1], abs=0.05)
    assert tab.mg_session.toggle_rec(a)                        # e volta para a baixa energia igual
    assert not a.mg_spec.rec and a.anat_center()[0] == pytest.approx(antes[0], abs=0.05)

    # código "tomo" no protocolo
    assert M.parse_code("CCD tomo").tomo
    w.close()


def _mama_com_implante(h=760, w=620, seed=1, densa=False, gordurosa=False, implante=True,
                       saturado=False, mono1=False):
    """Mamografia sintética com textura fibroglandular e prótese retromamária (parede torácica à direita)."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    px = np.full((h, w), 40.0, np.float32)
    corpo = ((xx - w) / (w * 0.96)) ** 2 + ((yy - h / 2) / (h * 0.46)) ** 2 < 1
    px[corpo] = (1500 if densa else 500 if gordurosa else 800) + rng.normal(0, 40, int(corpo.sum()))
    for _ in range(120 if gordurosa else 500):                    # traves fibroglandulares
        cx, cy = rng.uniform(0.1, 0.98) * w, rng.uniform(0.08, 0.92) * h
        ang, ln = rng.uniform(0, np.pi), rng.uniform(25, 150)
        t = np.linspace(-ln, ln, 300)
        X = np.clip((cx + t * np.cos(ang)).astype(int), 0, w - 1)
        Y = np.clip((cy + t * np.sin(ang)).astype(int), 0, h - 1)
        ok = corpo[Y, X]
        px[Y[ok], X[ok]] += rng.uniform(200, 900 if densa else 600)
    prot = np.zeros((h, w), bool)
    if implante:
        prot = ((xx - w * 0.93) / (w * 0.47)) ** 2 + ((yy - h / 2) / (h * 0.32)) ** 2 < 1
        px[prot] = (4095 if saturado else 2600) + rng.normal(0, 8 if saturado else 25, int(prot.sum()))
    px = np.clip(px, 0, 4095)
    return (-px if mono1 else px), corpo, prot


def test_acha_o_implante():
    """Acha a prótese (borda e forma, 0.95) em mamas de vários tipos, e não inventa sem ela."""
    casos = {"normal": {}, "mama densa": {"densa": True}, "gordurosa": {"gordurosa": True},
             "saturado": {"saturado": True}, "MONOCHROME1": {"mono1": True}}
    for nome, kw in casos.items():
        px, _mama, prot = _mama_com_implante(**kw)
        m = M.implant_mask(px, kw.get("mono1", False))
        assert m is not None, f"não achou a prótese: {nome}"
        assert (m & prot).sum() / prot.sum() > 0.9, nome          # pega quase todo o implante
        assert (m & ~prot).sum() / prot.sum() < 0.1, nome         # e quase nada de tecido
    for nome, kw in (("sem implante", {"implante": False}),
                     ("gordurosa sem implante", {"gordurosa": True, "implante": False})):
        px, _mama, _p = _mama_com_implante(**kw)
        assert M.implant_mask(px, False) is None, nome            # não inventa prótese

    # ponto escolhido à mão (quando a busca automática não acerta)
    px, _mama, prot = _mama_com_implante()
    ys, xs = np.nonzero(prot)
    m = M.implant_mask(px, False, seed=(int(np.median(ys)), int(np.median(xs))))
    assert m is not None and (m & prot).sum() / prot.sum() > 0.9

    # janela do tecido (ainda usada fora do botão, ex.: densidade); o "apagar" saiu na 0.96
    (largura, nivel), masc = M.implant_window(px, False)
    assert nivel < float(np.median(px[prot])) and largura > 0
    assert not hasattr(M, "blank_implant")


def test_botao_apagar_implante_no_viewer(env, tmp_path):
    from ipe.core.sample_data import _base, _mono, _save
    from ipe.ui.main_window import MainWindow
    from pydicom.uid import generate_uid
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    pat = {"name": "IMPLANTE^Teste", "id": "IMP1", "birth": "19750101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20260901", "accession": "IMP001",
             "description": "MAMOGRAFIA", "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 1, "description": "MG IMPLANTE"}
    px, _mama, prot = _mama_com_implante()
    for k, (lat, view) in enumerate((("R", "CC"), ("L", "CC")), start=1):
        ds = _base("1.2.840.10008.5.1.4.1.1.1.2", pat, study, series, "MG")
        ds.InstanceNumber, ds.ImageLaterality, ds.ViewPosition = k, lat, view
        ds.ImagerPixelSpacing = [0.1, 0.1]
        img = px if lat == "R" else px[:, ::-1].copy()
        _mono(ds, img.astype(np.uint16), signed=False)
        _save(ds, tmp_path / "imp")
    Importer(db, paths.storage).import_paths([tmp_path / "imp"])
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1200, 800)
    w.show()
    w.open_study(study["uid"])
    tab = w.tabs.currentWidget()
    app.processEvents()
    try:
        vp = tab.viewports[0]
        bruto = vp._img.pixels.copy()
        assert float(bruto.max()) > 2500
        janela = (vp.state.width, vp.state.level)
        tab.mg_set_implant(True)
        app.processEvents()
        assert vp.implant_mask and vp.implant_found
        # 0.96: só "corrigir" — o silicone desce ao nível do tecido, o detalhe (o ruído do fantoma) fica
        miolo = prot & (np.abs(np.arange(prot.shape[1])[None, :] - prot.shape[1] * 0.93) < 150) & \
            (np.abs(np.arange(prot.shape[0])[:, None] - prot.shape[0] / 2) < 120)
        corrigido = vp._img.pixels[miolo]
        assert float(np.median(corrigido)) < 1600                    # no nível do tecido
        assert float(corrigido.std()) > 5                            # e não liso: o detalhe ficou
        # a janela é a de antes de tirar o silicone (pedido dele, 0.96)
        assert (vp.state.width, vp.state.level) == pytest.approx(janela)
        # o quadro cacheado (o "arquivo") continua intacto
        assert float(vp.cache.get(vp.frames[vp.index]).pixels.max()) > 2500
        # janela mexida à mão também fica
        vp.set_window(1234, 567)
        tab.mg_set_implant(False)
        tab.mg_set_implant(True)
        app.processEvents()
        assert (vp.state.width, vp.state.level) == pytest.approx((1234, 567))
        tab.mg_set_implant(False)
        app.processEvents()
        assert not vp.implant_mask and float(vp._img.pixels.max()) > 2500
    finally:
        w.close()


def _degraus(m):
    """Quanto a borda esquerda da máscara anda em degraus, linha a linha."""
    xs = [np.nonzero(m[y])[0][0] for y in range(m.shape[0]) if m[y].any()]
    d = np.abs(np.diff(np.array(xs, float)))
    return float(d.max()), float((d > 3).mean())


def test_contorno_do_implante_sem_serrilhado():
    """A prótese é procurada numa imagem reduzida (rápido); a borda é refeita na resolução cheia, então
    o contorno fica igual ao de verdade — sem os degraus de quem só amplia a máscara."""
    px, _mama, prot = _mama_com_implante(h=1600, w=1300)
    fino = M.implant_mask(px, False)
    assert fino is not None
    grosso = M.implant_mask.__globals__["refine_border"]
    try:                                   # desliga o refino: é como era antes
        M.refine_border = lambda p, r, s, m=False: r
        M.implant_mask.__globals__["refine_border"] = M.refine_border
        blocos = M.implant_mask(px, False)
    finally:
        M.implant_mask.__globals__["refine_border"] = grosso
        M.refine_border = grosso
    real_max, real_ruins = _degraus(prot)
    fino_max, fino_ruins = _degraus(fino)
    bloco_max, bloco_ruins = _degraus(blocos)
    assert fino_max <= real_max + 2 and fino_ruins <= real_ruins + 0.02   # igual ao contorno real
    assert bloco_max > fino_max + 5                                       # e bem melhor que em blocos
    assert (fino & prot).sum() / prot.sum() > 0.97


def test_apagar_implante_pelo_ponto_clicado(env, tmp_path, monkeypatch):
    """Quando a busca automática não acerta, o botão direito no silicone resolve."""
    from ipe.core.sample_data import _base, _mono, _save
    from ipe.ui.main_window import MainWindow
    from pydicom.uid import generate_uid
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    pat = {"name": "IMPLANTE^Ponto", "id": "IMP2", "birth": "19700101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20260902", "accession": "IMP002",
             "description": "MAMOGRAFIA", "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 1, "description": "MG"}
    px, _mama, prot = _mama_com_implante()
    ds = _base("1.2.840.10008.5.1.4.1.1.1.2", pat, study, series, "MG")
    ds.InstanceNumber, ds.ImageLaterality, ds.ViewPosition = 1, "R", "CC"
    ds.ImagerPixelSpacing = [0.1, 0.1]
    _mono(ds, px.astype(np.uint16), signed=False)
    _save(ds, tmp_path / "imp2")
    Importer(db, paths.storage).import_paths([tmp_path / "imp2"])
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1100, 800)
    w.show()
    w.open_study(study["uid"])
    tab = w.tabs.currentWidget()
    app.processEvents()
    try:
        vp = tab.viewports[0]
        bruto = vp._img.pixels.copy()
        # finge que o automático falhou, para exercitar o caminho do clique
        monkeypatch.setattr(M, "implant_mask",
                            lambda p, m=False, seed=None: None if seed is None else _mask_real(p, m, seed))
        tab.mg_set_implant(True)
        app.processEvents()
        assert not vp.implant_found and float(vp._img.pixels.max()) > 2000
        ys, xs = np.nonzero(prot)
        centro = vp.image_to_widget(QPointF(float(np.median(xs)), float(np.median(ys))))
        vp.blank_implant_at(centro)
        app.processEvents()
        assert vp.implant_found and vp.implant_seed is not None
        denso = bruto > 2000
        agora = vp._img.pixels[denso]
        assert float((agora < vp.state.level * 1.5).mean()) > 0.85     # miolo apagado
        assert tab.mg_bar.a_implant.isChecked()                        # o botão acompanhou
    finally:
        w.close()




def test_o_que_cada_tela_mostra_se_define_na_etapa(env, sample_dir):
    """O pedido do usuário: "as etapas são únicas, não variam por monitor… o que aparece em cada
    monitor eu defino nas etapas, não nos protocolos".

    Então: uma lista de etapas só, e dentro da etapa o que vai em cada tela.
    """
    from ipe.ui.viewer.mammo_view import MgProtocolsEditor
    QApplication.instance() or QApplication([])
    _w, _repo, st = _window(env, sample_dir)
    ed = MgProtocolsEditor(st)
    ed.l_protos.setCurrentRow(1)
    ed.l_steps.setCurrentRow(0)                       # "4 incidências"
    antes = ed.l_steps.count()
    # sem definir nada, a etapa se reparte sozinha: as CC numa tela, as MLO na outra
    ed.c_telas.setCurrentIndex(1)                     # 2 telas
    assert ed.c_monitor.count() == 2
    assert [c.currentText() for c in ed.cells] == ["CCD", "CCE"]
    ed.c_monitor.setCurrentIndex(1)
    assert [c.currentText() for c in ed.cells] == ["MLOD", "MLOE"]
    # e o que o médico escreve manda
    ed.e_text.setText("1x2 (MLOE x MLOD)")
    ed._text_edited()
    ed.save()
    from ipe.imaging import mammo as MM
    passos = MM.passos_do_protocolo(MM.mg_protocols(st)[1])
    assert len(passos) == antes, "o número de etapas não muda: a lista é uma só"
    assert MM.quadro_da_etapa(passos[0], 2, 1)["cells"] == ["MLOE", "MLOD"]
    assert MM.quadro_da_etapa(passos[0], 2, 0)["cells"] == ["CCD", "CCE"]   # a outra tela, intacta
    assert MM.quadro_da_etapa(passos[0], 1, 0)["cells"] == ["CCD", "CCE", "MLOD", "MLOE"]


def test_repartir_sozinho_desfaz_o_que_foi_definido(env, sample_dir):
    from ipe.ui.viewer.mammo_view import MgProtocolsEditor
    QApplication.instance() or QApplication([])
    _w, _repo, st = _window(env, sample_dir)
    ed = MgProtocolsEditor(st)
    ed.l_protos.setCurrentRow(1)
    ed.l_steps.setCurrentRow(0)
    ed.c_telas.setCurrentIndex(1)
    ed.e_text.setText("1x1 (CCD)")
    ed._text_edited()
    assert ed.protos[1]["steps"][0].get("telas", {}).get("2")
    ed._repartir_sozinho()
    assert "telas" not in ed.protos[1]["steps"][0]
    assert [c.currentText() for c in ed.cells] == ["CCD", "CCE"]
