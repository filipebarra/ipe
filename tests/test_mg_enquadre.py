"""Mamografia: ao abrir a etapa, a **mama** enche o quadro — não o detector.

O relato: "em mamografia, quero que seja aplicado um zoom para ajustar a imagem para o monitor ao
abrir o exame. isso vai variar por monitor por isso nao pode ser algo fixo".

Medido no acervo dele antes de escrever a conta: nas imagens CESM de 2394 × 2850 a mama ocupa 33 a
55% da largura — metade do campo é ar. Enquadrar pela imagem inteira é enquadrar o ar. Em 100
imagens MG reais o ganho mediano foi 1,18 a 1,23× e o máximo 1,85×; nas séries ROUTINE3D_VOL, que o
aparelho já entrega recortadas, o ganho é 1,00 — e tem de ser 1,00, não 0,94.
"""
import numpy as np
import pytest
from pydicom.uid import DigitalMammographyXRayImageStorageForPresentation as MG_SOP
from pydicom.uid import generate_uid
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.core.sample_data import _base, _mono, _save
from ipe.imaging import mammo as M
from ipe.importer.scanner import Importer


# ----------------------------------------------------------------- a conta, com números reais
def test_conta_do_zoom_com_os_numeros_do_acervo():
    # CESM 2394 × 2850, mama de 845 × 2055 px (35% da largura, 72% da altura), quadro retrato
    z = M.zoom_da_caixa((960, 1200), (2394, 2850), (0, 0, 845, 2055))
    assert z == pytest.approx(1.37, abs=0.02)
    # mesma imagem, quadro maior: o zoom muda porque o quadro mudou — é o que se quer
    assert M.zoom_da_caixa((1280, 1440), (2394, 2850), (0, 0, 845, 2055)) == pytest.approx(1.31, abs=0.02)
    # tomo VOL, já recortada pelo aparelho: não há nada a ganhar, e **não pode encolher**
    assert M.zoom_da_caixa((960, 1200), (1277, 2781), (15, 0, 1277, 2781)) == 1.0
    assert M.zoom_da_caixa((960, 1200), (998, 2781), (0, 0, 985, 2760)) == 1.0
    # mama estreita: amplia bastante, mas com teto
    assert M.zoom_da_caixa((960, 1200), (2000, 2000), (0, 0, 100, 100)) == 8.0
    # entradas sem sentido não explodem nem encolhem
    assert M.zoom_da_caixa((0, 0), (10, 10), (0, 0, 5, 5)) == 1.0
    assert M.zoom_da_caixa((100, 100), (10, 10), (0, 0, 0, 0)) >= 1.0


def test_margem_folga_nao_vira_reducao():
    """Com a mama ocupando a altura inteira, a folga pediria zoom < 1: tem de virar 1,0."""
    assert M.zoom_da_caixa((900, 1200), (900, 1200), (0, 0, 900, 1200), margem=0.05) == 1.0
    assert M.zoom_da_caixa((900, 1200), (900, 1200), (0, 0, 900, 1200), margem=0.0) == 1.0


def test_modo_da_etapa():
    assert M.enquadre_da_etapa(None) == "mama"            # sem a chave, enquadra a mama
    assert M.enquadre_da_etapa({}) == "mama"
    assert M.enquadre_da_etapa({"enquadre": "pixel"}) == "pixel"
    assert M.enquadre_da_etapa({"enquadre": "sei la"}) == "mama"   # valor estranho não quebra
    assert set(M.ENQUADRES) == {"mama", "imagem", "pixel"}
    for rotulo in M.ENQUADRES.values():
        assert rotulo and not rotulo.startswith("{")


# ----------------------------------------------------------------- fantoma com ar, como a real
def _mama_com_ar(out, lado: str, view: str, study, pat, numero: int, largura_mama=0.42):
    """MG sintética com a mama ocupando ~42% da largura — o resto é ar, como na CESM real."""
    h, w = 1024, 800
    img = np.full((h, w), 30.0)
    yy, xx = np.mgrid[0:h, 0:w]
    bw = int(w * largura_mama)
    cx = 0 if lado == "L" else w - 1                      # parede torácica na borda
    r = np.sqrt(((xx - cx) / bw) ** 2 + ((yy - h / 2) / (h * 0.44)) ** 2)
    mama = r <= 1.0
    img[mama] = 900 + 120 * np.sin(xx[mama] / 11) * np.cos(yy[mama] / 13)
    series = {"uid": generate_uid(), "number": 10 + numero, "description": f"{view}_{lado}"}
    ds = _base(MG_SOP, pat, study, series, "MG")
    ds.InstanceNumber = numero
    ds.ImageLaterality = lado
    ds.ViewPosition = view
    ds.PixelSpacing = [0.1, 0.1]
    ds.Rows, ds.Columns = h, w
    _mono(ds, img, signed=False)
    return _save(ds, out / f"MG_{view}_{lado}")


@pytest.fixture()
def janela(env, tmp_path):
    paths, db, repo = env
    pat = {"name": "ENQUADRE^Teste", "id": "ENQ1", "birth": "19700101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20260101", "accession": "ENQ001",
             "description": "MAMOGRAFIA RASTREAMENTO", "for": generate_uid()}
    d = tmp_path / "mg"
    d.mkdir()
    for k, (lado, view) in enumerate((("R", "CC"), ("L", "CC"), ("R", "MLO"), ("L", "MLO"))):
        _mama_com_ar(d, lado, view, study, pat, k + 1)
    Importer(db, paths.storage).import_paths([d])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1500, 950)
    w.show()
    assert w.handle_external({"accession": "ENQ001"}) == "aberto"
    tab = w.tabs.currentWidget()
    QApplication.processEvents()
    yield app, w, tab
    w.close()


def _dentro_do_quadro(vp) -> bool:
    """A caixa da mama cabe no quadro (nada de mama cortada pela borda)."""
    from PySide6.QtCore import QPointF
    bx0, by0, bx1, by1 = vp.quadrant_box()
    pts = [vp.image_to_widget(QPointF(x, y)) for x, y in ((bx0, by0), (bx1, by0), (bx0, by1), (bx1, by1))]
    folga = 2.0
    return all(-folga <= p.x() <= vp.width() + folga and -folga <= p.y() <= vp.height() + folga
               for p in pts)


def test_ao_abrir_a_mama_enche_o_quadro(janela):
    app, w, tab = janela
    assert tab.mg_session is not None
    vps = [v for v in tab.viewports if v.mg_cell is not None and v._img is not None]
    assert len(vps) >= 2
    for vp in vps:
        assert vp.state.zoom > 1.02, "a mama continuou do tamanho do detector"
        assert _dentro_do_quadro(vp), "enquadrou cortando a mama"
        assert vp.anat_lock and vp.anat_lock[0] == "mama"
        # o quadro passou a ser mais mama e menos ar do que no ajuste da imagem inteira
        bx0, by0, bx1, by1 = vp.quadrant_box()
        h, w = vp._img.pixels.shape[:2]
        parte = ((bx1 - bx0) / w) * ((by1 - by0) / h)
        assert parte * vp.state.zoom ** 2 > parte * 1.04
    # zoom sincronizado: duas mamas na mesma etapa ficam na mesma escala
    assert len({round(v.state.zoom, 4) for v in vps}) == 1


def test_a_parede_toracica_continua_encostada(janela):
    """Regra de ouro da mamografia: o alinhamento do hanging não se perde no enquadramento."""
    from PySide6.QtCore import QPointF
    app, w, tab = janela
    a, b = tab.viewports[0], tab.viewports[1]
    assert a.align_edge == "right" and b.align_edge == "left"
    for vp in (a, b):
        bx0, by0, bx1, by1 = vp.quadrant_box()
        lado_img = vp.chest_image_side()
        x = bx1 if lado_img == "right" else bx0
        na_tela = vp.image_to_widget(QPointF(x, (by0 + by1) / 2)).x()
        esperado = vp.width() if vp.align_edge == "right" else 0.0
        assert na_tela == pytest.approx(esperado, abs=2), vp.align_edge


def test_cada_modo_da_etapa_faz_o_que_diz(janela):
    app, w, tab = janela
    s = tab.mg_session
    vp = next(v for v in tab.viewports if v.mg_cell is not None)
    def modo(v):                      # `steps` é derivada do protocolo: a escolha mora no protocolo
        s.proto.setdefault("steps", M.passos_do_protocolo(s.proto))[s.step]["enquadre"] = v
    modo("imagem")
    assert s.enquadrar() == "imagem"
    assert vp.state.zoom == pytest.approx(1.0)
    modo("pixel")
    assert s.enquadrar() == "pixel"
    assert vp.state.zoom == pytest.approx(1.0 / vp.fit_scale(), rel=0.01)
    modo("mama")
    assert s.enquadrar() == "mama" and vp.state.zoom > 1.02


def test_alt_q_reenquadra_depois_do_zoom_na_mao(janela):
    app, w, tab = janela
    vp = next(v for v in tab.viewports if v.mg_cell is not None)
    antes = vp.state.zoom
    vp.state.zoom = 3.7
    vp.update()
    tab.mg_enquadrar()
    assert vp.state.zoom == pytest.approx(antes, rel=0.01)


def test_a_forma_do_quadro_manda_no_zoom(janela):
    """O tamanho na tela já acompanha o monitor pelo ajuste à janela; o **fator** muda com a
    forma do quadro — num quadro estreito o que limita passa a ser a largura, e aí o ganho é
    muito maior. Por isso o enquadramento não pode ser um número fixo no código."""
    app, w, tab = janela
    vp = next(v for v in tab.viewports if v.mg_cell is not None)
    largo = vp.zoom_da_mama()
    vp.resize(max(80, vp.width() // 5), vp.height())
    QApplication.processEvents()
    estreito = vp.zoom_da_mama()
    assert largo and estreito and estreito > largo * 1.3


def test_o_editor_guarda_o_modo_por_etapa(env, monkeypatch):
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.ui.viewer.mammo_view import MgProtocolsEditor
    st = Settings(paths.settings_file)
    d = MgProtocolsEditor(st)
    assert d.l_steps.count() >= 1
    d.l_steps.setCurrentRow(0)
    assert d.c_enquadre.currentData() == "mama"
    i = d.c_enquadre.findData("pixel")
    assert i >= 0
    d.c_enquadre.setCurrentIndex(i)
    assert d._cur_step()["enquadre"] == "pixel"
    d.l_steps.setCurrentRow(0)
    assert d.c_enquadre.currentData() == "pixel"
    d.close()


def test_o_enquadre_segue_o_tamanho_do_quadro(janela):
    """O defeito: ao abrir o exame o zoom não era aplicado; mudando de etapa, era.

    A causa é que ao montar a etapa o quadro ainda não tem o tamanho final — e o enquadramento
    sai do tamanho do quadro. Agora o quadro avisa quando muda de tamanho e a conta é refeita.
    A invariante que se confere aqui é a que estava quebrada ao abrir: o zoom que está na tela é
    o zoom que o tamanho atual do quadro pede.
    """
    from PySide6.QtTest import QTest
    app, w, tab = janela
    vp = next(v for v in tab.viewports if v.mg_cell is not None)
    assert vp.anat_lock and vp.anat_lock[0] == "mama"
    assert vp.state.zoom == pytest.approx(vp.zoom_da_mama(), rel=0.01)
    antes = vp.state.zoom
    w.resize(700, 1300)                    # outra forma de quadro: o enquadramento muda
    QTest.qWait(200)
    app.processEvents()
    pedido = vp.zoom_da_mama()
    assert pedido != pytest.approx(antes, rel=0.02), "o quadro não mudou de forma: teste inútil"
    assert vp.state.zoom == pytest.approx(pedido, rel=0.01), \
        "o enquadramento não acompanhou o tamanho do quadro"
    assert _dentro_do_quadro(vp)


def test_zoom_na_mao_nao_e_desfeito_por_um_redimensionamento(janela):
    from PySide6.QtTest import QTest
    app, w, tab = janela
    vp = next(v for v in tab.viewports if v.mg_cell is not None)
    vp.state.zoom = 3.3
    vp.relock_free()                       # é o que o programa faz depois do zoom à mão
    w.resize(760, 1240)
    QTest.qWait(200)
    app.processEvents()
    assert vp.state.zoom == pytest.approx(3.3), "o reenquadramento atropelou o zoom do médico"


# --------------------------------------------------- imagem arrastada para o quadro, à mão
def _uma_serie_mg(tab, vp) -> str:
    """Uma série MG do exame que **não** é a que já está no quadro."""
    for s in tab.repo.series_for_study(tab.study_uid):
        if s.modality == "MG" and s.series_uid != vp.series_uid:
            return s.series_uid
    raise AssertionError("o exame de teste tem só uma série MG")


def test_imagem_arrastada_entra_enquadrada(janela):
    """O relato: "quando arrastar uma imagem, aplique o zoom na tela".

    Arrastar uma incidência para o quadro é pedir para olhar aquela mama, não o ar em volta.
    O caminho do arraste é `load_series_into`, o mesmo do duplo clique na lista de séries.
    """
    app, w, tab = janela
    vp = next(v for v in tab.viewports if v.mg_cell is not None)
    uid = _uma_serie_mg(tab, vp)
    tab.load_series_into(vp, uid)
    app.processEvents()
    assert vp._img is not None and vp.series_uid == uid
    assert vp.state.zoom > 1.02, "a imagem solta abriu do tamanho do detector"
    assert vp.state.zoom == pytest.approx(vp.zoom_da_mama(), rel=0.01)
    assert _dentro_do_quadro(vp), "enquadrou cortando a mama"
    # no protocolo o conjunto continua na mesma escala: comparar em escalas diferentes não compara
    cheios = [v for v in tab.viewports if v.mg_cell is not None and v._img is not None]
    assert len({round(v.state.zoom, 4) for v in cheios}) == 1


def test_defeito_volta_sem_o_enquadre_do_arraste(janela, monkeypatch):
    app, w, tab = janela
    vp = next(v for v in tab.viewports if v.mg_cell is not None)
    uid = _uma_serie_mg(tab, vp)
    monkeypatch.setattr(type(tab), "enquadrar_imagem_solta", lambda self, _vp: None)
    tab.load_series_into(vp, uid)
    app.processEvents()
    assert vp.state.zoom == pytest.approx(1.0, abs=0.02), "teste inútil: enquadrou sem a correção"


def test_arraste_fora_do_protocolo_enquadra_o_quadro(janela):
    """Modo de reserva: sem protocolo (quadro avulso), enquadra o quadro em que a imagem caiu."""
    app, w, tab = janela
    vp = next(v for v in tab.viewports if v.mg_cell is not None)
    uid = _uma_serie_mg(tab, vp)
    tab.mg_session = None
    for v in tab.viewports:
        v.mg_cell = None
    tab.load_series_into(vp, uid)
    app.processEvents()
    assert vp.state.zoom > 1.02 and vp.anat_lock and vp.anat_lock[0] == "mama"
    assert _dentro_do_quadro(vp)


@pytest.mark.parametrize("cells, esperado", [
    (["CCD", "CCE", "MLOD", "MLOE"], ["right", "left", "right", "left"]),     # o caso relatado (0.96.1)
    (["CCD", "MLOD", "CCE", "MLOE"], ["right", "right", "left", "left"]),
    (["CCD", "CCE"], ["right", "left"]),
])
def test_etapa_em_uma_linha_segue_a_mama(janela, cells, esperado):
    """Na tela, a parede torácica de cada quadro fica do lado da mama — não da metade da tela."""
    app, _w, tab = janela
    s = tab.mg_session
    s.proto["steps"] = [{"name": "linha", "rows": 1, "cols": len(cells), "cells": cells}]
    s.apply_step(0)
    app.processEvents()
    lados = [vp.chest_screen_side() for vp in tab.viewports[:len(cells)]]
    assert lados == esperado
