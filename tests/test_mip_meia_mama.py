"""0.90: etapa da RM de mama com 4 MIPs de meia mama — 1ª e 3ª fase pós, mama direita com o
mamilo para a esquerda e mama esquerda com o mamilo para a direita.

Pedido dele: "em RM de mama eu queria uma etapa com layout 2×2 com 4 MIPs. Dois da 1ª fase pós
contraste e dois da 3ª fase. Os MIPs serão só de meia mama, direita com mamilo virado para a esquerda
e esquerda virado para a direita. Queria que isso tudo fosse configurado na parte de protocolos de
exibição, como se fosse escolher uma sequência."

Fantoma: dinâmica axial em 4 séries (pré + 3 pós). Uma lesão na mama DIREITA acende só na 1ª pós;
outra na mama ESQUERDA acende só na 3ª pós. O MIP de cada metade tem que achar a lesão da sua
metade, na fase certa, e nunca a da outra metade.
"""
import numpy as np
import pytest
from pydicom.uid import MRImageStorage, generate_uid
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.core.sample_data import _base, _mono, _save
from ipe.importer.scanner import Importer
from ipe.ui.viewer import etapas as E
from ipe.ui.viewer import hanging as H

N, CORTES = 64, 24
# x do paciente: −63 … 0 (direita do paciente, x negativo) e 0 … +63 (esquerda)
X0 = -64.0


def _dinamica(pasta):
    pat = {"name": "MAMA^Teste", "id": "MM1", "birth": "19700101", "sex": "F"}
    estudo = {"uid": generate_uid(), "date": "20261022", "accession": "MM001",
              "description": "RM DAS MAMAS", "for": generate_uid()}
    yy, xx = np.mgrid[0:N, 0:N]
    # mamas: frente do paciente é y pequeno (−y = anterior em LPS); lesões perto do mamilo
    mama_d = ((xx - 16) ** 2 + (yy - 22) ** 2) < 150
    mama_e = ((xx - 48) ** 2 + (yy - 22) ** 2) < 150
    lesao_d = ((xx - 16) ** 2 + (yy - 14) ** 2) < 9
    lesao_e = ((xx - 48) ** 2 + (yy - 14) ** 2) < 9
    uids = []
    for fase in range(4):
        serie = {"uid": generate_uid(), "number": 10 + fase,
                 "description": "VIBRANT pre" if fase == 0 else f"VIBRANT pos {fase}"}
        uids.append(serie["uid"])
        for k in range(CORTES):
            ds = _base(MRImageStorage, pat, estudo, serie, "MR")
            ds.InstanceNumber = k + 1
            ds.ImagePositionPatient = [X0, -40.0, 3.0 * k]
            ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
            ds.PixelSpacing = [2.0, 2.0]
            ds.SliceThickness = 3.0
            ds.AcquisitionTime = f"10{fase:02d}00"
            img = np.full((N, N), 10.0)
            img[mama_d | mama_e] = 100
            if 8 <= k <= 14:
                if fase == 1:
                    img[lesao_d] = 900
                if fase == 3:
                    img[lesao_e] = 700
            _mono(ds, img, signed=False)
            _save(ds, pasta / f"f{fase}")
    return estudo["uid"], uids


def _abrir(env, tmp_path, steps):
    paths, db, repo = env
    estudo, uids = _dinamica(tmp_path / "d")
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    repo.save_series_group(estudo, uids, "Dinâmica")
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    s = Settings(paths.settings_file)
    s.set("hanging_protocols", [{"name": "RM de mama", "modality": "MR", "description": "MAMA", "enabled": True,
                                 "steps": steps}])
    w = MainWindow(paths, s)
    w.resize(1200, 900)
    w.show()
    w.browser.refresh()
    w.open_study(estudo)
    app.processEvents()
    return app, w, w.all_viewer_tabs()[-1]


@pytest.fixture()
def aba(env, tmp_path):
    """A etapa de fábrica: quatro MIPs 3D de meia mama."""
    app, w, t = _abrir(env, tmp_path, [H.ETAPA_MIP_MEIA_MAMA])
    yield app, w, t
    w.close()


#: a mesma etapa com MIP de espessura (sagital), em vez do 3D
ETAPA_ESPESSURA = {"name": "MIP de espessura", "rows": 2, "cols": 2, "cells": [
    dict(c, recon="mip") for c in H.ETAPA_MIP_MEIA_MAMA["cells"]]}


@pytest.fixture()
def aba_espessura(env, tmp_path):
    app, w, t = _abrir(env, tmp_path, [ETAPA_ESPESSURA])
    yield app, w, t
    w.close()


def _tela(vp):
    """A imagem como aparece na tela (com o espelho do quadro)."""
    px = np.asarray(vp._img.pixels, float)
    if vp.state.flip_h:
        px = px[:, ::-1]
    if vp.state.flip_v:
        px = px[::-1, :]
    return px


def _lado_da_lesao(vp, minimo):
    px = _tela(vp)
    colunas = np.where(px.max(axis=0) >= minimo)[0]
    assert colunas.size, "lesão (perto do mamilo) não aparece"
    return "esquerda" if colunas.mean() < px.shape[1] / 2 else "direita"


def test_quatro_mips_3d_de_meia_mama_nas_fases_certas(aba):
    app, w, t = aba
    assert t.exib is not None and t._layout == (2, 2), "a etapa não abriu"
    d1, e1, d3, e3 = t.viewports[:4]
    for vp in (d1, e1, d3, e3):
        assert vp.render3d is not None and vp.render3d.mode == "mip", vp.empty_note
    # cada quadro é um 3D próprio, como o do botão 3D: renderizadores diferentes
    assert len({id(vp.render3d.r) for vp in (d1, e1, d3, e3)}) == 4
    assert "Mama direita" in d1.series_label and "pós-contraste 1" in d1.series_label
    assert "Mama esquerda" in e3.series_label and "pós-contraste 3" in e3.series_label
    # a lesão da direita só acende na 1ª pós e só no MIP da metade direita (e a esquerda na 3ª)
    alto = lambda vp: float(np.asarray(vp._img.pixels, float).max())  # noqa: E731
    assert alto(d1) > 2 * alto(e1) and alto(e3) > 2 * alto(d3)
    # vista Esquerda na mama direita (mamilo à esquerda), Direita na esquerda (mamilo à direita)
    assert (d1.render3d.az, e1.render3d.az) == (90, 270)
    assert not any(vp.state.flip_h or vp.state.flip_v or vp.state.rot for vp in (d1, e1, d3, e3))
    assert _lado_da_lesao(d1, 0.6 * alto(d1)) == "esquerda"
    assert _lado_da_lesao(e3, 0.6 * alto(e3)) == "direita"


def test_cada_quadro_tem_a_barra_do_3d_inteira(aba):
    app, w, t = aba
    d1, e1 = t.viewports[:2]
    t._activate(e1)
    t._activate(d1)
    barra = t.render3d_bar
    assert barra.isVisibleTo(t) and barra.view() is d1.render3d
    barra.c_mode.setCurrentIndex(barra.c_mode.findData("vr"))
    barra._modo()
    assert d1.render3d.mode == "vr" and e1.render3d.mode == "mip"      # só o quadro ativo mudou
    t._activate(e1)
    assert barra.view() is e1.render3d and barra.c_mode.currentData() == "mip"
    from ipe.ui.viewer.render3d_view import VISTAS
    az, el = next((a, e) for n, a, e in VISTAS if n == "Anterior")
    e1.render3d.set_view(az, el)                                      # as Vistas da barra, quadro a quadro
    assert e1.render3d.az == az and d1.render3d.az == 90


def test_mip_de_espessura_com_vista(aba_espessura):
    app, w, t = aba_espessura
    d1, e1, d3, e3 = t.viewports[:4]
    for vp in (d1, e1, d3, e3):
        assert vp.mpr_plane is not None and vp.mpr_plane.name == "Sagital" and vp.mpr_plane.mode == "mip", \
            vp.empty_note
    assert _tela(d1).max() == 900 and _tela(e1).max() == 100
    assert _tela(e3).max() == 700 and _tela(d3).max() == 100
    assert 50 <= d1.mpr_plane.slab_mm <= 64
    assert _lado_da_lesao(d1, 700) == "esquerda" and _lado_da_lesao(e3, 700) == "direita"
    o = np.asarray(d1.display_orientation(), float)
    assert o[5] < 0                                                    # cabeça para cima


def test_fase_que_nao_existe_avisa(env, tmp_path):
    paths, db, repo = env
    estudo, uids = _dinamica(tmp_path / "d")
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    repo.save_series_group(estudo, uids, "Dinâmica")
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    s = Settings(paths.settings_file)
    s.set("hanging_protocols", [{"name": "RM de mama", "modality": "MR", "description": "MAMA", "enabled": True,
                                 "steps": [{"name": "x", "rows": 1, "cols": 2, "cells": [
                                     {"series": "VIBRANT", "fase": "5"}, {"series": "VIBRANT", "fase": "ult"}]}]}])
    w = MainWindow(paths, s)
    w.show()
    w.browser.refresh()
    w.open_study(estudo)
    app.processEvents()
    t = w.all_viewer_tabs()[-1]
    a, b = t.viewports[:2]
    assert "4 fase(s)" in a.empty_note and not a.frames
    assert b.phases and b.phase == 3 and "última fase" in b.series_label
    w.close()


def test_modelo_e_editor():
    q = H.quadro({"series": "VIBRANT", "fase": 3, "metade": "esquerda", "anterior": "direita"})
    assert (q["fase"], q["plane"], q["recon"]) == ("3", "Sagital", "mip")
    assert q["vista"] == "direita"                                   # o "anterior" da 0.90 vira vista
    assert H.quadro({"metade": "direita", "recon": "mip3d"})["plane"] == ""
    assert H.quadro({"metade": "direita", "recon": "mpr"})["recon"] == "mip"
    assert H.quadro({"vista": "lateral"})["vista"] == ""
    assert H.quadro({"fase": "x", "metade": "meio"})["fase"] == "" and H.quadro({"metade": "meio"})["metade"] == ""
    assert H.fase_indice("1", 4) == 1 and H.fase_indice("pre", 4) == 0 and H.fase_indice("ult", 4) == 3
    assert H.fase_indice("4", 4) is None
    assert "pós-contraste 3" in H.descrever_quadro(q) and "mama esquerda" in H.descrever_quadro(q)


def test_editor_escolhe_fase_metade_e_frente(env):
    paths, _db, _repo = env
    _app = QApplication.instance() or QApplication([])
    from ipe.ui.viewer.protocolos_editor import ProtocolosEditor
    e = ProtocolosEditor(Settings(paths.settings_file))
    e.novo_protocolo()
    e.e_rows.setValue(2)
    e.e_cols.setValue(2)
    e._escolheu_quadro(2)
    e.q_serie.setText("DYN")
    e.q_serie.textEdited.emit("DYN")
    e.q_fase.setCurrentIndex(e.q_fase.findData("3"))
    e.q_metade.setCurrentIndex(e.q_metade.findData("direita"))
    assert e.q_recon.currentData() == "mip3d"                        # meia mama: o 3D da metade
    assert not e.q_slab.isEnabled() and not e.q_plano.isEnabled()
    e.q_vista.setCurrentIndex(e.q_vista.findData("esquerda"))
    q = e.protocolos()[-1]["steps"][0]["cells"][2]
    assert (q["series"], q["fase"], q["metade"], q["vista"], q["recon"]) == \
        ("DYN", "3", "direita", "esquerda", "mip3d")
    assert [e.q_vista.itemData(i) for i in range(e.q_vista.count())] == \
        ["", "anterior", "posterior", "direita", "esquerda", "superior", "inferior"]
    assert e.q_recon.findData("vr") >= 0 and e.q_recon.findData("mpr") >= 0
    e.q_recon.setCurrentIndex(e.q_recon.findData("mip"))              # de espessura: sagital
    q = e.protocolos()[-1]["steps"][0]["cells"][2]
    assert (q["recon"], q["plane"]) == ("mip", "Sagital")
    assert "pós-contraste 3" in e.botoes_quadro[2].text()


def test_quem_ja_tinha_a_rm_de_mama_ganha_a_etapa_uma_vez(env):
    paths, _db, _repo = env
    s = Settings(paths.settings_file)
    meu = {"name": "RM de mama", "modality": "MR", "description": "MAMA", "enabled": True,
           "steps": [{"name": "Minha", "rows": 1, "cols": 1, "cells": ["T2"]}]}
    s.set("hanging_protocols", [meu])
    s.set("hanging_fabrica", "0.88")
    novos = H.acrescentar_os_de_fabrica(s)
    assert "RM de mama ▸ MIP das fases (meia mama)" in novos
    rm = next(p for p in H.protocols(s) if p["name"] == "RM de mama")
    assert [st["name"] for st in rm["steps"]] == ["Minha", "MIP das fases (meia mama)", "Avaliação dinâmica"]
    assert H.acrescentar_os_de_fabrica(s) == []
    assert len(next(p for p in H.protocols(s) if p["name"] == "RM de mama")["steps"]) == 3


# ----------------------------------------------------------------------------- 0.93
def test_reconstrucao_da_etapa_tem_a_barra_do_3d_e_vira_3d(aba_espessura):
    """Pedido dele: "acrescente a barra 3D — modo sempre que a etapa usar alguma reconstrução.
    Trate as reconstruções como se fossem volumes 3D"."""
    app, w, t = aba_espessura
    d1, e1, d3, e3 = t.viewports[:4]
    t._activate(e1)
    t._activate(d1)
    barra = t.render3d_bar
    assert d1.render3d is None and barra.isVisibleTo(t), "a barra do 3D tinha que aparecer no MIP da etapa"
    assert barra.c_mode.currentData() == "mip" and "vira 3D" in barra.info.text()
    antes = float(np.asarray(d1._img.pixels, float).max())
    barra._girar(True)                     # qualquer ferramenta da barra: vira 3D e gira
    v = d1.render3d
    assert v is not None and v.mode == "mip" and v.cine_on()
    v.cine(False)
    # olhando do mesmo lado do corte (mamilo à esquerda = vista Esquerda) e só a fatia do MIP
    assert (v.az, v.el) == (90, 0) or v.az != 0
    assert not v.r.untouched()
    v.set_view(90, 0)
    depois = float(np.asarray(d1._img.pixels, float).max())
    assert depois > 0.5 * antes, "a lesão da metade direita sumiu do 3D"
    # os outros quadros continuam como estavam
    assert e1.render3d is None and e1.mpr_plane is not None
    # mudar o modo de outro quadro também converte só aquele
    t._activate(e3)
    barra.c_mode.setCurrentIndex(barra.c_mode.findData("vr"))
    barra._modo()
    assert e3.render3d is not None and e3.render3d.mode == "vr" and d3.render3d is None


def test_mip_de_espessura_fora_do_protocolo_nao_ganha_a_barra(aba_espessura):
    app, w, t = aba_espessura
    d1 = t.viewports[0]
    t._activate(t.viewports[1])
    t._activate(d1)
    assert t.render3d_bar.isVisibleTo(t)
    t.load_series_into(d1, t.series[0].series_uid)               # o quadro passou a mostrar outra coisa
    t._activate(t.viewports[1])
    t._activate(d1)
    assert not t.render3d_bar.isVisibleTo(t)


def test_barra_do_mpr_mostra_a_espessura_da_etapa(aba_espessura):
    app, w, t = aba_espessura
    assert t.slab_combo.currentData() == t.viewports[0].mpr_plane.slab_mm and t.slab_combo.currentText() != "fino"


# ----------------------------------------------------------------------------- 0.94
def test_etapa_que_abre_a_avaliacao_dinamica(env, tmp_path):
    """Pedido dele: "tem como acrescentar uma etapa ativando o dinâmico da RM de mama?"."""
    app, w, t = _abrir(env, tmp_path, [{"name": "T", "rows": 1, "cols": 1, "cells": ["VIBRANT PRE"]},
                                       H.ETAPA_DINAMICA])
    assert t.dyn is None
    t.mg_next(1)
    assert t.exib.indice == 1 and t.dyn is not None, t.viewports[0].empty_note
    assert t.dyn.maps.n == CORTES and len(t.dyn.maps.dset.phases) == 4
    assert t.dyn.params["layout"] == 0                               # o layout dos mapas da etapa
    t.mg_next(-1)                                                    # sair da etapa fecha a dinâmica
    assert t.dyn is None and t.exib.indice == 0 and t.viewports[0].frames
    t.mg_next(1)
    assert t.dyn is not None                                          # e volta a abrir
    w.close()


def test_etapa_dinamica_usa_os_ultimos_parametros(env, tmp_path):
    paths, _db, _repo = env
    s = Settings(paths.settings_file)
    s.set("dyn.ultimos", {"threshold_pct": 70, "pre": 0, "layout": 3})
    s.save()
    passo = dict(H.ETAPA_DINAMICA, dinamica={"layout": 2, "series": H.DINAMICA})
    app, w, t = _abrir(env, tmp_path, [passo])
    assert t.dyn is not None and t.dyn.params["threshold_pct"] == 70 and t.dyn.params["layout"] == 2
    w.close()


def test_sem_dinamica_no_exame_avisa(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    s = Settings(paths.settings_file)
    s.set("hanging_protocols", [{"name": "RM", "modality": "MR", "description": "", "enabled": True,
                                 "steps": [{"name": "T", "rows": 1, "cols": 1, "cells": ["T1|T2|MR"]},
                                           H.ETAPA_DINAMICA]}])
    w = MainWindow(paths, s)
    w.show()
    estudo = next(e for e in repo.search_studies() if e.modalities == "MR")
    w.open_study(estudo.study_uid)
    app.processEvents()
    t = w.all_viewer_tabs()[-1]
    t.mg_next(1)
    assert t.dyn is None and "dinâmica" in t.viewports[0].empty_note.lower()
    w.close()


def test_editor_liga_a_dinamica_na_etapa(env):
    paths, _db, _repo = env
    _app = QApplication.instance() or QApplication([])
    from ipe.ui.viewer.protocolos_editor import ProtocolosEditor
    e = ProtocolosEditor(Settings(paths.settings_file))
    e.novo_protocolo()
    e.e_din.setChecked(True)
    e.e_din_layout.setCurrentIndex(1)
    st = e.protocolos()[-1]["steps"][0]
    assert st["dinamica"] == {"layout": 1, "layout_nome": "Mapa cinético, subtração e fase inicial + curva",
                              "series": H.DINAMICA}
    assert not e.painel_quadro.isEnabled() and not e.e_rows.isEnabled()
    e.e_din.setChecked(False)
    assert "dinamica" not in e.protocolos()[-1]["steps"][0] and e.painel_quadro.isEnabled()
    # a RM de mama de fábrica tem a etapa
    assert any(st.get("dinamica") for p in H.DEFAULT_PROTOCOLS for st in p.get("steps", []))
