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
    assert res.l3["smi"]["v"] is None and any("sem a altura" in x for x in res.avisos_l3)


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
    assert C.frase(b) == ("Atenuação hepática média de 61 HU, esplênica de 51 HU (fígado − baço 10 HU). "
                          + C.EST_SEM + ".")
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
        ds.PatientWeight = "58"
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


# ------------------------------------------------------------------ 0.99.80: peso, IMC e resultado da esteatose
def test_resultado_da_esteatose():
    R = C.resultado_esteatose
    assert R(61, 10, 1.2) == C.EST_SEM
    assert R(50, -2, 0.96) == C.EST_LEVE                 # fígado menos denso que o baço, sem critério de ≥ 30%
    assert R(47, 5, 1.1) == C.EST_MOD                    # Pickhardt: fígado < 48 HU
    assert R(55, -10, 0.85) == C.EST_MOD                 # Park: fígado − baço < −9
    assert R(55, -5, 0.79) == C.EST_MOD                  # Park: fígado / baço < 0,8
    assert R(30, -20, 0.6, contraste=True) == C.EST_CONTRASTE
    assert R(None) is None


def test_figado_gorduroso_no_fantoma_e_correcao_refaz_o_resultado():
    t = _T()
    hu = t.vol.data
    rot = _rotulos(hu)                                      # o simulador acha o fígado pelo código 61
    m = _cortes()
    for k in range(NZ):
        hu[k][m["fig"] & m["cav"]] = 31                     # depois, o fígado vira gorduroso
    res = C.calcular(t, rot)
    assert res.figado["figado_hu"]["v"] == pytest.approx(31, abs=0.5)
    assert res.figado["resultado"]["v"] == C.EST_MOD
    a = {**C.itens_para_o_banco(res, t, "x")[1], "estado": "confirmado", "corrigidos": {}}
    assert C.frase(a).endswith(C.EST_MOD + ".")
    # o médico corrige o HU do fígado: o resultado acompanha
    a["corrigidos"] = {"figado_hu": 62.0, "f_menos_b": 11.0, "f_sobre_b": 1.22}
    assert C.resultado_do_achado(a) == C.EST_SEM
    a["corrigidos"]["resultado"] = "Esteatose focal poupando o segmento IV"
    assert C.resultado_do_achado(a) == "Esteatose focal poupando o segmento IV"


def test_peso_da_o_imc_e_as_referencias_de_martin(monkeypatch):
    t = _T()
    monkeypatch.setattr(C, "_biometria", lambda _t: {"altura_m": 1.70, "peso_kg": 86.7, "sexo": "M"})
    res = C.calcular(t, _rotulos(t.vol.data))
    assert res.l3["imc"]["v"] == 30.0 and res.l3["peso_kg"]["v"] == 86.7 and res.l3["altura_m"]["v"] == 1.7
    martin = next(x for x in res.avisos_l3 if "Martin" in x)
    assert "< 53" in martin and "< 33 HU" in martin          # homem com IMC ≥ 25
    # sem peso: sem IMC, e avisa
    monkeypatch.setattr(C, "_biometria", lambda _t: {"altura_m": 1.70, "peso_kg": None, "sexo": "F"})
    res = C.calcular(t, _rotulos(t.vol.data))
    assert res.l3["imc"]["v"] is None and any("sem o peso" in x for x in res.avisos_l3)


def test_atualizar_biometria_refaz_indice_e_avisos():
    t = _T()
    res = C.calcular(t, _rotulos(t.vol.data))
    a = {**C.itens_para_o_banco(res, t, "x")[0], "corrigidos": {}}
    assert "sem a altura" in a["elegibilidade"]
    nums, eleg = C.atualizar_biometria(a, 1.60, 50.0, "F")
    sma = a["numeros"]["sma_cm2"]["v"]
    assert nums["smi"]["v"] == pytest.approx(sma / 1.6 ** 2, abs=0.1)
    assert nums["imc"]["v"] == pytest.approx(19.5, abs=0.05)
    assert "sem a altura" not in eleg and "38,5" in eleg and "< 41 HU" in eleg
    assert eleg.startswith(a["elegibilidade"].partition(". Atenção: ")[0])
    # trocar de novo não acumula avisos repetidos
    a2 = {**a, "numeros": nums, "elegibilidade": eleg}
    _n, eleg2 = C.atualizar_biometria(a2, 1.60, 50.0, "F")
    assert eleg2.count("Prado") == 1 and eleg2.count("Martin") == 1


def test_biometria_do_arquivo_e_digitada(env, tmp_path):
    from ipe.ai import biometria as B
    paths, db, repo = env
    uid, _s = _exame(env, tmp_path)
    se = repo.series_for_study(uid)[0]
    arq = repo.instances_for_series(se.series_uid)[0]["path"]
    from pathlib import Path
    caminho = Path(arq) if Path(arq).is_absolute() else Path(paths.storage) / arq
    v = B.ler(repo, uid, caminho)
    assert v["altura_m"] == 1.6 and v["peso_kg"] == 58.0 and v["sexo"] == "F"
    assert v["fonte"] == {"altura_m": "arquivo", "peso_kg": "arquivo", "sexo": "arquivo"}
    B.guardar(repo, uid, 1.62, 61.5, "F")
    v = B.ler(repo, uid, caminho)
    assert v["altura_m"] == 1.62 and v["peso_kg"] == 61.5 and v["fonte"]["peso_kg"] == "digitado"
    assert B.imc(1.62, 61.5) == 23.4
    assert B.do_arquivo(None)["peso_kg"] is None


def test_janela_de_altura_e_peso_antes_e_no_painel(env, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

    from ipe.ai import biometria as B
    from ipe.core.config import Settings
    from ipe.ui import biometria_dialog as BD
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, _s = _exame(env, tmp_path)
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(msg))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, msg, *a, **k: avisos.append("ERRO " + msg))
    vistos = []

    def exec_(self):
        vistos.append({"altura": self.altura.value(), "peso": self.peso.value(), "sexo": self.sexo.currentData()})
        if len(vistos) == 1:
            return QDialog.Rejected                         # cancelar não calcula
        self.altura.setValue(165)
        self.peso.setValue(70)
        return QDialog.Accepted
    monkeypatch.setattr(BD.BiometriaDialog, "exec", exec_)
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1300, 800)
    w.show()
    try:
        assert w.handle_external({"accession": "COMP01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        vp = next(v for v in tab.viewports if v.frames)
        assert tab.composicao_automatica(vp, simular=True, perguntar=True) is None
        assert vistos[0] == {"altura": 160, "peso": 58.0, "sexo": "F"}        # do arquivo
        assert not repo.achados(uid, "composicao")
        tab.composicao_automatica(vp, simular=True, perguntar=True)
        fim = time.time() + 120
        while not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert avisos and avisos[-1].startswith("Composição corporal pronta"), avisos
        l3 = next(a for a in repo.achados(uid, "composicao") if a["tipo"] == C.TIPO_L3)
        assert l3["numeros"]["altura_m"]["v"] == 1.65 and l3["numeros"]["peso_kg"]["v"] == 70.0
        assert l3["numeros"]["imc"]["v"] == pytest.approx(25.7, abs=0.05)
        fig = next(a for a in repo.achados(uid, "composicao") if a["tipo"] == C.TIPO_FIGADO)
        assert fig["numeros"]["resultado"]["v"] == C.EST_SEM
        # no painel: o botão aparece e refaz os números sem rodar a IA
        p = tab.achados_painel
        assert p.b_bio.isVisibleTo(p)
        r_fig = next(i for i, a in enumerate(p.achados) if a["tipo"] == C.TIPO_FIGADO)
        p.t.selectRow(r_fig)
        assert "Resultado" in p.l_origem.text()
        assert p.aplicar_biometria(uid, {"altura_m": 1.80, "peso_kg": 100.0, "sexo": "F"})
        l3 = next(a for a in repo.achados(uid, "composicao") if a["tipo"] == C.TIPO_L3)
        assert l3["numeros"]["imc"]["v"] == pytest.approx(30.9, abs=0.05)
        assert l3["numeros"]["smi"]["v"] == pytest.approx(l3["numeros"]["sma_cm2"]["v"] / 1.8 ** 2, abs=0.1)
        assert B.ler(repo, uid)["peso_kg"] == 100.0
    finally:
        w.close()
