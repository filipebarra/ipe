"""0.99.47: composição corporal em L3 e atenuação hepática (TotalSegmentator + limiares de HU).

Fantoma axial (pixel 1,5 mm, cortes de 2,5 mm): corpo em elipse com gordura subcutânea (−100 HU),
parede muscular (40 HU), cavidade abdominal com gordura visceral (−101 HU), fígado (61 HU), baço
(51 HU) e alça (21 HU); vértebra posterior (701 HU nos cortes de L3, 700 nos outros) e uma ilha de
gordura intermuscular (−100 HU) dentro da parede. O simulador do trabalhador lê esses códigos.
"""
import time

import numpy as np
import pytest

from ipe.ai import achados as AC
from ipe.ai import composicao as C
from ipe.imaging.volume import Volume

PX = 1.5
N = 160
NZ = 40
L3 = range(15, 26)


def _cortes():
    c = (np.arange(N) - N / 2 + 0.5) * PX
    yy, xx = np.meshgrid(c, c, indexing="ij")
    corpo = (xx / 110) ** 2 + (yy / 85) ** 2 <= 1
    dentro = (xx / 95) ** 2 + (yy / 70) ** 2 <= 1
    cav = (xx / 75) ** 2 + ((yy + 10) / 45) ** 2 <= 1
    vert = xx ** 2 + (yy - 50) ** 2 <= 14 ** 2
    imat = (xx - 60) ** 2 + (yy - 40) ** 2 <= 5 ** 2
    fig = (xx + 40) ** 2 + (yy + 10) ** 2 <= 20 ** 2
    baco = (xx - 45) ** 2 + yy ** 2 <= 12 ** 2
    alca = (xx - 10) ** 2 + (yy + 30) ** 2 <= 8 ** 2
    return dict(corpo=corpo, dentro=dentro, cav=cav, vert=vert, imat=imat, fig=fig, baco=baco, alca=alca)


def _hu():
    m = _cortes()
    hu = np.full((NZ, N, N), -1000, np.int16)
    for k in range(NZ):
        s = hu[k]
        s[m["corpo"]] = -100
        s[m["dentro"]] = 40
        s[m["imat"]] = -100
        s[m["cav"]] = -101
        s[m["fig"] & m["cav"]] = 61
        s[m["baco"] & m["cav"]] = 51
        s[m["alca"] & m["cav"]] = 21
        s[m["vert"]] = 701 if k in L3 else 700
    return hu


class _T:
    def __init__(self, contraste=False):
        hu = _hu()
        o = -(N / 2 - 0.5) * PX
        self.vol = Volume(hu, np.array([o, o, 0.0]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
                          np.array([0, 0, 2.5]), PX, PX, None, "")
        self.frames = []
        self.series_uid = "1.2.3"
        self.study_uid = "1.2"
        self.descricao_serie = "AX PORTAL" if contraste else "AX SEM CONTRASTE"
        self.versao = "simulado"


def _rotulos(hu):
    from ipe.ai import totalseg_worker as W
    return W._simular(hu, C.tarefas())


def test_l3_e_compartimentos():
    t = _T()
    res = C.calcular(t, _rotulos(t.vol.data))
    assert res.k_l3 == 20
    m = _cortes()
    a = PX * PX / 100
    sat = (m["corpo"] & ~m["dentro"]).sum() * a
    vat = (m["cav"] & ~m["fig"] & ~m["baco"] & ~m["alca"]).sum() * a
    musc = (m["dentro"] & ~m["cav"] & ~m["vert"] & ~m["imat"]).sum() * a
    imat = m["imat"].sum() * a
    assert res.l3["sat_cm2"]["v"] == pytest.approx(sat, rel=0.02)
    assert res.l3["vat_cm2"]["v"] == pytest.approx(vat, rel=0.02)
    assert res.l3["imat_cm2"]["v"] == pytest.approx(imat, rel=0.05)
    # o anel de 1 pixel em volta da vértebra sai do músculo (volume parcial com o osso)
    assert res.l3["sma_cm2"]["v"] == pytest.approx(musc, rel=0.05)
    assert res.l3["musculo_hu"]["v"] == 40
    assert res.l3["vat_sat"]["v"] == pytest.approx(vat / sat, rel=0.04)
    assert res.l3["smi"]["v"] is None and any("PatientSize" in x for x in res.avisos_l3)


def test_figado_e_baco_sem_contraste():
    t = _T()
    res = C.calcular(t, _rotulos(t.vol.data))
    f = res.figado
    assert f["figado_hu"]["v"] == 61 and f["baco_hu"]["v"] == 51
    assert f["f_menos_b"]["v"] == 10 and f["f_sobre_b"]["v"] == pytest.approx(1.2, abs=0.01)
    assert any("Park" in x for x in res.avisos_figado) and not res.contraste


def test_com_contraste_avisa():
    t = _T(contraste=True)
    res = C.calcular(t, _rotulos(t.vol.data))
    assert res.contraste and any("contraste" in x for x in res.avisos_figado)
    assert not any("Park" in x for x in res.avisos_figado)


def test_serie_nao_axial_nao_mede_l3():
    t = _T()
    t.vol.slice_vec = np.array([2.5, 0, 0])
    res = C.calcular(t, _rotulos(t.vol.data))
    assert not res.l3 and "axial" in res.avisos_l3[0] and res.figado


def test_frases():
    t = _T()
    res = C.calcular(t, _rotulos(t.vol.data))
    itens = C.itens_para_o_banco(res, t, "x")
    assert [i["tipo"] for i in itens] == [C.TIPO_L3, C.TIPO_FIGADO]
    a = {**itens[0], "estado": "confirmado", "corrigidos": {}}
    txt = C.frase(a)
    assert txt.startswith("Composição corporal em L3: área muscular de") and "gordura visceral" in txt
    b = {**itens[1], "estado": "confirmado", "corrigidos": {}}
    assert C.frase(b) == "Atenuação hepática média de 61 HU, esplênica de 51 HU (fígado − baço 10 HU)."
    assert AC.texto_do_laudo([{**b, "estado": "sugerido"}], C.frase) == ""


def test_altura_da_o_indice(monkeypatch):
    t = _T()
    monkeypatch.setattr(C, "_altura_sexo", lambda _t: (1.70, "M"))
    res = C.calcular(t, _rotulos(t.vol.data))
    assert res.l3["smi"]["v"] == pytest.approx(res.l3["sma_cm2"]["v"] / 1.7 ** 2, abs=0.1)
    assert any("52,4" in x and "Prado" in x for x in res.avisos_l3)


# ------------------------------------------------------------------ na tela
def _exame(env, tmp_path):
    from pydicom.uid import generate_uid

    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    hu = _hu()
    pat = {"name": "ABDOME^Teste", "id": "COMP1", "birth": "19600101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20261104", "accession": "COMP01", "description": "TC ABDOME TOTAL",
             "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 2, "description": "AX SEM CONTRASTE"}
    pasta = tmp_path / "comp"
    o = -(N / 2 - 0.5) * PX
    for k in range(NZ):
        ds = _base("1.2.840.10008.5.1.4.1.1.2", pat, study, series, "CT")
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [o, o, 2.5 * k]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [PX, PX]
        ds.SliceThickness = 2.5
        ds.PatientSize = "1.60"
        ds.RescaleSlope, ds.RescaleIntercept = 1, 0
        _mono(ds, hu[k], signed=True)
        _save(ds, pasta)
    Importer(db, paths.storage).import_paths([pasta])
    return study["uid"], series["uid"]


def test_tela_composicao(env, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, _s = _exame(env, tmp_path)
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(msg))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, msg, *a, **k: avisos.append("ERRO " + msg))
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1300, 800)
    w.show()
    try:
        assert w.handle_external({"accession": "COMP01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        assert tab.app_na_barra("composicao")
        vp = next(v for v in tab.viewports if v.frames)
        tab.composicao_automatica(vp, simular=True)
        fim = time.time() + 120
        while not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert avisos and avisos[-1].startswith("Composição corporal pronta"), avisos
        assert C.ja_feita(repo, uid)
        ach = repo.achados(uid, "composicao")
        assert [a["tipo"] for a in ach] == [C.TIPO_L3, C.TIPO_FIGADO]
        l3 = ach[0]["numeros"]
        assert l3["smi"]["v"] == pytest.approx(l3["sma_cm2"]["v"] / 1.6 ** 2, abs=0.1)
        assert "38,5" in ach[0]["elegibilidade"]                    # mulher: a referência dela
        p = tab.achados_painel
        assert p.t.rowCount() == 2 and "cm²" in p.t.item(0, 2).text() and "HU" in p.t.item(1, 2).text()
        p.t.selectRow(0)
        assert p.ir_ate() and vp.index == 20
        # o SEG no corte de L3 entrou nas sobreposições
        nomes = {o.label for o in tab.overlay_objects}
        assert any("Músculo" in n for n in nomes), nomes
        tab.composicao_botao()                                      # com resultado, abre a lista
        assert tab.achados_painel.isVisible()
    finally:
        w.close()


def test_registrada_no_contrato_e_na_aba(env):
    from PySide6.QtWidgets import QApplication

    from ipe.ai import ferramentas as FE
    from ipe.core.config import Settings
    from ipe.ui.cad_ia import CadIaTab
    QApplication.instance() or QApplication([])
    assert FE.modulo("composicao") is C
    paths, db, repo = env
    t = CadIaTab(Settings(paths.settings_file), repo)
    nomes = [t.l_ferramentas.item(k).text().split("\n")[0] for k in range(t.l_ferramentas.count())]
    assert C.NOME_CADIA in nomes


def test_instalador_baixa_trunk_cavities():
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    for nome in ("instalar_segmentacao.sh", "instalar_segmentacao.bat"):
        assert "trunk_cavities" in (raiz / nome).read_text(encoding="utf-8", errors="replace")
