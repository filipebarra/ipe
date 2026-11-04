"""0.99.61 — rodada mama P2: eixo de simetria à mão (ROI espelhada), inverter só a mama (PV 17), alinhamento
vertical pelo mamilo + zoom/pan espelhado (PV 16), corte da DBT como imagem-chave (PV 18) e quadros "última US /
última RM" no protocolo da mamografia (PV 19)."""
from types import SimpleNamespace as NS

import numpy as np
import pytest
from pydicom.uid import DigitalMammographyXRayImageStorageForPresentation as MG_SOP
from pydicom.uid import generate_uid
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.core.sample_data import _base, _mono, _save
from ipe.imaging import mammo as M
from ipe.importer.scanner import Importer

US_SOP = "1.2.840.10008.5.1.4.1.1.6.1"
MR_SOP = "1.2.840.10008.5.1.4.1.1.4"


def _fantoma(h=1024, w=800, lado="L", cy=0.5, cauda=False):
    """Mama em meia elipse encostada na borda (parede torácica à esquerda se lado == "L"), centro em cy·h.
    `cauda`: tecido junto da parede descendo até embaixo (a caixa da mama deixa de ter o mamilo no meio)."""
    img = np.full((h, w), 30.0)
    yy, xx = np.mgrid[0:h, 0:w]
    cx = 0 if lado == "L" else w - 1
    r = np.sqrt(((xx - cx) / (w * 0.42)) ** 2 + ((yy - cy * h) / (h * 0.36)) ** 2)
    m = r <= 1.0
    if cauda:
        perto = (xx < 0.08 * w) if lado == "L" else (xx > 0.92 * w)
        m |= perto & (yy > cy * h) & (yy < 0.97 * h)
    img[m] = 900 + 120 * np.sin(xx[m] / 11) * np.cos(yy[m] / 13)
    return img, m


def test_mascara_e_mamilo():
    img, m = _fantoma(lado="L", cy=0.4)
    mm = M.mascara_da_mama(img)
    assert mm is not None and mm.shape == img.shape
    assert (mm == m).mean() > 0.98
    x, y = M.mamilo(img)
    assert x == pytest.approx(0.42 * 800, abs=6) and y == pytest.approx(0.4 * 1024, abs=8)
    img2, _ = _fantoma(lado="R", cy=0.6)
    x2, y2 = M.mamilo(img2)
    assert x2 == pytest.approx(799 - 0.42 * 800, abs=6) and y2 == pytest.approx(0.6 * 1024, abs=8)
    assert M.mamilo(np.zeros((64, 64))) is None
    assert M.alinhamento_do_protocolo({}) == "mamilo" and M.alinhamento_do_protocolo({"alinhar": "meio"}) == "meio"
    assert M.alinhamento_do_protocolo({"alinhar": "xx"}) == "mamilo"


def test_codigos_e_escolhas_de_outro_exame():
    assert M.parse_outro("US") == ("US", "") and M.parse_outro("rm") == ("MR", "")
    assert M.parse_outro("RM: SUB") == ("MR", "SUB") and M.parse_outro("CCD") is None
    assert M.parse_code("US") is None
    r = lambda uid, d, mods, desc: NS(study_uid=uid, study_date=d, modalities=mods, description=desc)  # noqa: E731
    rows = [r("a", "20240101", "US", "US MAMAS"), r("b", "20250601", "US", "US ABDOME"),
            r("c", "20250301", "US", "ULTRASSONOGRAFIA MAMARIA"), r("d", "20270101", "US", "US MAMA"),
            r("e", "20250101", "MR", "RM DAS MAMAS"), r("f", "20250201", "CT\\MR", "RM CRANIO")]
    est, da_mama = M.estudo_outro(rows, "US", "20260101")
    assert est.study_uid == "c" and da_mama                       # a da mama, a mais recente até a data
    est, _ = M.estudo_outro(rows, "MR", "20260101")
    assert est.study_uid == "e"
    est, da_mama = M.estudo_outro([rows[1]], "US", "20260101")
    assert est.study_uid == "b" and not da_mama                    # sem nenhuma da mama, aceita outra
    assert M.estudo_outro(rows, "US", "20231231") == (None, False)
    s = lambda d, n, mod="MR": NS(description=d, num_images=n, modality=mod)  # noqa: E731
    series = [s("AX T2", 40), s("DYN T1", 300), s("SUB 1", 60), s("DWI", 80)]
    assert M.serie_outra(series, "MR").description == "SUB 1"
    assert M.serie_outra(series, "MR", "DWI").description == "DWI"
    assert M.serie_outra([s("AXIAL", 3, "US"), s("MAMA D", 12, "US")], "US").description == "MAMA D"


# ------------------------------------------------------------------ na tela
def _mg(out, lado, view, study, pat, numero, cy):
    img, _ = _fantoma(lado=lado, cy=cy, cauda=(lado == "R" and view == "CC"))
    series = {"uid": generate_uid(), "number": 10 + numero, "description": f"{view}_{lado}"}
    ds = _base(MG_SOP, pat, study, series, "MG")
    ds.InstanceNumber, ds.ImageLaterality, ds.ViewPosition = numero, lado, view
    ds.PixelSpacing = [0.1, 0.1]
    _mono(ds, img, signed=False)
    return _save(ds, out / f"MG_{view}_{lado}")


def _outro(out, sop, mod, pat, data, desc, series_desc, n=3):
    study = {"uid": generate_uid(), "date": data, "accession": f"{mod}{data}", "description": desc,
             "for": generate_uid()}
    for sd in series_desc:
        series = {"uid": generate_uid(), "number": 1 + series_desc.index(sd), "description": sd}
        for k in range(n):
            ds = _base(sop, pat, study, series, mod)
            ds.InstanceNumber = k + 1
            ds.PixelSpacing = [0.5, 0.5]
            if mod == "MR":
                ds.ImagePositionPatient = [-60.0, -60.0, float(k * 3)]
                ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
            yy, xx = np.mgrid[0:64, 0:64]
            corpo = ((xx - 32) / 26.0) ** 2 + ((yy - 32) / 18.0) ** 2 <= 1
            _mono(ds, np.where(corpo, 300 + 10 * k, 5), signed=False)
            _save(ds, out / f"{mod}_{sd}")
    return study["uid"]


@pytest.fixture()
def janela(env, tmp_path):
    paths, db, repo = env
    pat = {"name": "MAMA^P2", "id": "MP2", "birth": "19700101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20260101", "accession": "MP2001",
             "description": "MAMOGRAFIA RASTREAMENTO", "for": generate_uid()}
    d = tmp_path / "mg"
    d.mkdir()
    # a mama direita mais alta que a esquerda: o alinhamento pelo mamilo tem trabalho a fazer
    for k, (lado, view, cy) in enumerate((("R", "CC", 0.38), ("L", "CC", 0.62), ("R", "MLO", 0.45),
                                          ("L", "MLO", 0.55))):
        _mg(d, lado, view, study, pat, k + 1, cy)
    us = _outro(d, US_SOP, "US", pat, "20251201", "US DAS MAMAS", ["MAMA DIREITA"], n=4)
    mr = _outro(d, MR_SOP, "MR", pat, "20251101", "RM DAS MAMAS", ["AX T2", "SUB 1"], n=3)
    Importer(db, paths.storage).import_paths([d])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1500, 950)
    w.show()
    assert w.handle_external({"accession": "MP2001"}) == "aberto"
    tab = w.tabs.currentWidget()
    QApplication.processEvents()
    yield app, w, tab, us, mr
    w.close()


def _etapa(tab, cells, rows=1, cols=2):
    s = tab.mg_session
    s.proto.setdefault("steps", M.passos_do_protocolo(s.proto))
    s.proto["steps"][s.step] = {"name": "teste", "rows": rows, "cols": cols, "cells": cells}
    s.apply_step(s.step)
    QApplication.processEvents()


def test_alinhamento_pelo_mamilo(janela):
    app, w, tab, _us, _mr = janela
    _etapa(tab, ["CCD", "CCE"])
    a, b = tab.viewports[0], tab.viewports[1]
    ya, yb = a.mamilo_na_tela(), b.mamilo_na_tela()
    assert ya == pytest.approx(yb, abs=3) and abs(a.mg_dy) > 5
    # a parede torácica continua encostada
    assert a.align_edge == "right" and b.align_edge == "left"
    # pelo meio da mama: os mamilos ficam desalinhados, como as mamas estão
    tab.mg_session.proto["alinhar"] = "meio"
    tab.mg_session.enquadrar()
    assert abs(a.mamilo_na_tela() - b.mamilo_na_tela()) > 20 and a.mg_dy == 0
    tab.mg_session.proto["alinhar"] = "mamilo"
    tab.mg_session.enquadrar()
    # trocar de imagem pelo enquadramento guardado mantém o deslocamento
    a.reapply_anat()
    assert a.mamilo_na_tela() == pytest.approx(b.mamilo_na_tela(), abs=3)
    # o zoom/pan espelhado está na barra (o mesmo botão de sincronia)
    assert tab.sync_zoom_action in tab.mg_bar.actions()


def test_inverter_so_a_mama(janela):
    app, w, tab, _us, _mr = janela
    _etapa(tab, ["CCD", "CCE"])
    a = tab.viewports[0]
    antes = a._qimage_for_current().copy()
    assert tab.mg_set_inverter_mama(True) == 2 and tab.mg_bar.a_inv.isChecked()
    q = a._qimage_for_current()
    h, w_ = a._img.pixels.shape
    m = M.mascara_da_mama(a._img.pixels)
    ys, xs = np.nonzero(m)
    dentro = (int(xs[len(xs) // 2]), int(ys[len(ys) // 2]))
    fora = next((x, y) for x, y in ((5, 5), (w_ - 5, 5), (5, h - 5), (w_ - 5, h - 5)) if not m[y, x])
    assert q.pixelColor(*fora).value() == 0                         # o fundo continua preto
    assert q.pixelColor(*dentro).value() == 255 - antes.pixelColor(*dentro).value()
    # a etapa seguinte nasce invertida também
    _etapa(tab, ["MLOD", "MLOE"])
    assert all(v.inverter_mama for v in tab.viewports[:2])
    tab.mg_set_inverter_mama(False)
    assert not tab.viewports[0].inverter_mama


def test_ultima_us_e_rm_no_protocolo(janela):
    app, w, tab, us, mr = janela
    _etapa(tab, ["CCD", "CCE", "US", "RM"], rows=2, cols=2)
    c, d = tab.viewports[2], tab.viewports[3]
    assert c.study_uid == us and c.mg_cell is None and "Última US — 01/12/2025" in c.series_label
    assert d.study_uid == mr and "SUB 1" in d.series_label and "Última RM" in d.series_label
    # o filtro escolhe a série
    _etapa(tab, ["CCD", "RM:T2"])
    assert "AX T2" in tab.viewports[1].series_label
    # paciente sem RM: o quadro diz por quê
    tab.mg_session._studies["outro:MR"] = None
    _etapa(tab, ["CCD", "RM"])
    assert "nenhum exame" in tab.viewports[1].empty_note
    # o editor aceita os códigos
    from ipe.ui.viewer.mammo_view import CELL_CHOICES
    assert "US" in CELL_CHOICES and "RM" in CELL_CHOICES


def test_corte_chave_e_navegacao(janela, monkeypatch):
    app, w, tab, _us, _mr = janela
    _etapa(tab, ["CCD", "CCE"])
    vp = tab.viewports[0]
    tab._activate(vp)
    assert tab.mg_corte_chave() is True
    f = vp.current_frame()
    assert (f.sop_uid, f.frame_index) in tab.key_set
    assert tab.mg_proximo_chave(1) is True and tab.mg_proximo_chave(-1) is True
    # numa tomo de vários cortes, vai ao corte marcado
    vp.tomo_range = (0, len(vp.frames))
    assert tab.mg_corte_chave() is False                       # desmarca
    assert tab.mg_proximo_chave(1) is False


def test_eixo_de_simetria_a_mao(janela, env):
    from ipe.imaging import clonar_roi as CR
    app, w, tab, _us, mr = janela
    tab.add_study(mr)
    QApplication.processEvents()
    serie = next(s for s in tab.series if s.study_uid == mr and "SUB" in (s.description or ""))
    vp = tab.viewports[0]
    tab.close_mg()
    tab.set_layout(1, 1)
    tab.load_series_into(vp, serie.series_uid, como_serie=True)
    QApplication.processEvents()
    auto, como = CR.eixo_de_simetria(vp)
    assert auto is not None and como != "eixo marcado à mão"
    pos = vp.image_to_widget(QPointF(20.5, 32.0))
    x = vp.marcar_eixo(pos)
    assert x == pytest.approx(-60 + 20 * 0.5, abs=0.6)
    assert CR.eixo_de_simetria(vp) == (pytest.approx(x), "eixo marcado à mão")
    linha = vp._linha_do_eixo()
    assert linha is not None and linha[0].x() == pytest.approx(pos.x(), abs=vp.state.zoom * 2 + 2)
    menu = vp.build_context_menu(pos)
    nomes = [a.text() for a in menu.actions()]
    assert "Eixo de simetria (ROI espelhada)" in nomes
    vp.esquecer_eixo()
    assert vp.eixo_manual() is None and CR.eixo_de_simetria(vp)[1] != "eixo marcado à mão"
