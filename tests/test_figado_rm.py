"""0.99.49: gordura (PDFF) e ferro (R2*) do fígado na RM.

Fantoma com o arranjo da RM de abdome do acervo (GE, IDEAL IQ): uma série anatômica "WATER: 3D Ax LAVA S/C"
onde o simulador acha o fígado (600) e o baço (500); o mapa "FatFrac: IDEAL IQ (R2*)" (ImageType
…\\FAT_FRACTION, em %) e o "R2*: IDEAL IQ (R2*)" (…\\R2_STAR_MAP, s⁻¹), numa grade **mais grossa** (pixel
3 mm, cortes a cada 8 mm), a 1,5 T; e a dupla eco "3D Ax IN/OUT" com as duas ecos na mesma série.
"""
import time

import numpy as np
import pytest

from ipe.ai import achados as AC
from ipe.ai import figado_rm as F

# grade anatômica: 1,5 mm, 48 cortes de 2 mm (z de 0 a 94)
N, NZ, PX, DZ = 96, 48, 1.5, 2.0
O = -(N / 2) * PX
FIG = (-40, 40, -40, 20, 20, 75)       # caixa do fígado (x0, x1, y0, y1, z0, z1), mm
BACO = (48, 68, 0, 30, 30, 60)


def _dentro(x, y, z, cx):
    x0, x1, y0, y1, z0, z1 = cx
    return (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1) & (z >= z0) & (z <= z1)


def _grade(n, nz, px, dz, o, z0=0.0):
    c = o + np.arange(n) * px
    zz = z0 + np.arange(nz) * dz
    z, y, x = np.meshgrid(zz, c, c, indexing="ij")
    return x, y, z


def _serie(pasta, pat, study, desc, numero, vol, px, dz, o, z0=0.0, extra=None, te=None):
    from pydicom.uid import generate_uid

    from ipe.core.sample_data import _base, _mono, _save
    series = {"uid": generate_uid(), "number": numero, "description": desc}
    for k in range(vol.shape[0]):
        ds = _base("1.2.840.10008.5.1.4.1.1.4", pat, study, series, "MR")
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [o, o, z0 + dz * k]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [px, px]
        ds.SliceThickness = dz
        ds.MagneticFieldStrength = 1.5
        if te is not None:
            ds.EchoTime = te
        for kk, vv in (extra or {}).items():
            setattr(ds, kk, vv)
        _mono(ds, vol[k], signed=True)
        _save(ds, pasta / f"{numero}_{te or 0}")
    return series["uid"]


def _exame(env, tmp_path, com_mapas=True, com_dupla=True):
    from pydicom.uid import generate_uid

    from ipe.importer.scanner import Importer
    paths, db, repo = env
    pat = {"name": "FIGADO^Teste", "id": "FIG1", "birth": "19700101", "sex": "M"}
    study = {"uid": generate_uid(), "date": "20261104", "accession": "FIG01", "description": "RM ABDOME TOTAL",
             "for": generate_uid()}
    pasta = tmp_path / "fig"
    x, y, z = _grade(N, NZ, PX, DZ, O)
    anat = np.full(x.shape, 100, np.int16)
    anat[_dentro(x, y, z, FIG)] = 600
    anat[_dentro(x, y, z, BACO)] = 500
    uid_anat = _serie(pasta, pat, study, "WATER: 3D Ax LAVA S/C", 20, anat, PX, DZ, O)
    # uma série da pelve com mais cortes, que não pode ser a escolhida
    _serie(pasta, pat, study, "WATER: 3D Ax LAVA PRE PELVE", 11, np.full((60, 32, 32), 100, np.int16), 4.5, 2.0, O)
    if com_mapas:
        mx, my, mz = _grade(48, 12, 3.0, 8.0, O)
        ff = np.full(mx.shape, -50, np.int16)
        fig = _dentro(mx, my, mz, FIG)
        ff[fig & (mx < 0)] = 18                   # metade da direita do paciente (x < 0): 18%
        ff[fig & (mx >= 0)] = 6
        _serie(pasta, pat, study, "FatFrac: IDEAL IQ (R2*)", 19, ff, 3.0, 8.0, O,
               extra={"ImageType": ["DERIVED", "PRIMARY", "DIXON", "FAT_FRACTION"]})
        r2 = np.zeros(mx.shape, np.int16)
        r2[fig] = 80
        r2[_dentro(mx, my, mz, BACO)] = 40
        _serie(pasta, pat, study, "R2*: IDEAL IQ (R2*)", 1900, r2, 3.0, 8.0, O,
               extra={"ImageType": ["DERIVED", "PRIMARY", "DIXON", "R2_STAR_MAP"]})
        # 0.100.86: a água do IDEAL IQ vem depois do mapa e tem "(R2*)" no nome — não pode virar o R2*
        _serie(pasta, pat, study, "WATER: IDEAL IQ (R2*)", 1901, np.full(mx.shape, 900, np.int16), 3.0, 8.0, O)
    if com_dupla:
        op = np.full(x.shape, 100, np.int16)
        ip = np.full(x.shape, 120, np.int16)
        op[_dentro(x, y, z, FIG)] = 400
        ip[_dentro(x, y, z, FIG)] = 500
        from pydicom.uid import generate_uid as g
        uid = g()
        for te, v in ((2.084, op), (4.168, ip)):
            from ipe.core.sample_data import _base, _mono, _save
            series = {"uid": uid, "number": 18, "description": "3D Ax IN/OUT"}
            for k in range(v.shape[0]):
                ds = _base("1.2.840.10008.5.1.4.1.1.4", pat, study, series, "MR")
                ds.InstanceNumber = k + 1 + (0 if te < 3 else NZ)
                ds.ImagePositionPatient = [O, O, DZ * k]
                ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
                ds.PixelSpacing = [PX, PX]
                ds.SliceThickness = DZ
                ds.EchoTime = te
                ds.MagneticFieldStrength = 1.5
                _mono(ds, v[k], signed=True)
                _save(ds, pasta / f"io_{te}")
    Importer(db, paths.storage).import_paths([pasta])
    return study["uid"], uid_anat


def test_tipo_do_mapa():
    assert F.tipo_do_mapa("qualquer", ["DERIVED", "PRIMARY", "DIXON", "FAT_FRACTION"]) == "ff"
    assert F.tipo_do_mapa("qualquer", ["DERIVED", "PRIMARY", "DIXON", "R2_STAR_MAP"]) == "r2"
    assert F.tipo_do_mapa("FatFrac: IDEAL IQ (R2*)", None) == "ff"
    assert F.tipo_do_mapa("R2*: IDEAL IQ (R2*)", None) == "r2"
    assert F.tipo_do_mapa("T2* map", None) == "t2"
    assert F.tipo_do_mapa("Ax T2 SSFSE", None) == ""
    # 0.100.86: as imagens de água e de gordura do IDEAL IQ não são mapa de R2* (o "(R2*)" é a sequência)
    assert F.tipo_do_mapa("WATER: IDEAL IQ (R2*)", None) == ""
    assert F.tipo_do_mapa("FAT: IDEAL IQ (R2*)", None) == ""
    assert F.tipo_do_mapa("WATER: IDEAL IQ (R2*)", ["DERIVED", "PRIMARY", "DIXON", "WATER"]) == ""
    assert F.tipo_do_mapa("R2 * ( Hz )", ["DERIVED", "SECONDARY", "PROCESSED"]) == "r2"
    assert F.tipo_do_mapa("T2 * ( ms )", None) == "t2"


def test_amostrar_entre_grades():
    from ipe.imaging.volume import Volume
    a = Volume(np.zeros((10, 20, 20)), np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
               np.array([0, 0, 1.0]), 1.0, 1.0, None, "")
    m = np.zeros((10, 20, 20), bool)
    m[2:8, 4:12, 6:14] = True
    b = Volume(np.zeros((5, 10, 10)), np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
               np.array([0, 0, 2.0]), 2.0, 2.0, None, "")
    out = F._amostrar(a, m, b)
    assert out[1:4, 2:6, 3:7].all() and out.sum() == 3 * 4 * 4


def test_escolhe_a_serie_do_abdome_nao_a_da_pelve(env, tmp_path):
    paths, db, repo = env
    uid, uid_anat = _exame(env, tmp_path)
    assert F.escolher_serie(repo, uid)[0] == uid_anat
    m = F.mapas_do_exame(repo, uid)
    assert set(m) == {"ff", "r2"}
    ff, ef, desc = F.dupla_eco(repo, uid)
    assert len(ff) == len(ef) == NZ and "TE 2.08" in desc


def _rodar(env, tmp_path, **kw):
    from ipe.ai import ferramentas as FE
    from ipe.ai import totalseg as TS
    from ipe.imaging.series import FrameCache
    paths, db, repo = env
    uid, uid_anat = _exame(env, tmp_path, **kw)
    t = TS.Trabalho(repo, FrameCache(256), None, uid, uid_anat, simular=True)
    FE.preparar_trabalho(t, F)
    t.preparar()
    t.rodar_aqui()
    res, versao = FE.rodar_conta(t, F, None)
    return t, res, versao, repo, paths, db


def test_gordura_ferro_e_dupla_eco(env, tmp_path):
    t, res, versao, repo, paths, db = _rodar(env, tmp_path)
    try:
        g = res.gordura
        assert g["pdff_p25"]["v"] == pytest.approx(6, abs=0.5) and g["pdff_p75"]["v"] == pytest.approx(18, abs=0.5)
        assert 6 <= g["pdff_mediana"]["v"] <= 18
        assert "S7 18,0" in g["pdff_segmentos"]["v"] and "S2 6,0" in g["pdff_segmentos"]["v"]
        f = res.ferro
        assert f["r2_mediana"]["v"] == 80 and f["t2_ms"]["v"] == 12.5 and f["baco_r2"]["v"] == 40
        assert f["lic"]["v"] == pytest.approx(0.0254 * 80 + 0.202, abs=0.01)
        assert f["lic_grau"]["v"].startswith("acima do normal (1,8–3,2)") and "r2_15" not in f
        assert any("Wood" in a for a in res.avisos_ferro) and any("Tang" in a for a in res.avisos_gordura)
        d = res.dixon
        assert d["ff_sinal"]["v"] == pytest.approx(10.0) and d["razao_ef_ff"]["v"] == 1.25
        saida = F.gravar(t, res, versao, db, paths.storage, repo=repo)
        ach = repo.achados(t.study_uid, F.FERRAMENTA)
        assert [a["tipo"] for a in ach] == [F.TIPO_GORDURA, F.TIPO_FERRO, F.TIPO_DIXON]
        assert saida["seg_path"] and F.ja_feita(repo, t.study_uid)
        txt = F.frase({**ach[1], "estado": "confirmado"})
        assert txt.startswith("R2* hepático mediano de 80 s⁻¹ (T2* 12,5 ms)") and "mg Fe/g" in txt
        assert AC.texto_do_laudo(ach, F.frase) == ""          # tudo sugerido: nada vai ao laudo
    finally:
        t.limpar()


def test_sem_mapas_so_dupla_eco_e_ferro_aparece(env, tmp_path):
    t, res, _v, *_r = _rodar(env, tmp_path, com_mapas=False)
    try:
        assert not res.gordura and not res.ferro and res.dixon
    finally:
        t.limpar()


def test_sem_nada_avisa(env, tmp_path):
    t, res, _v, *_r = _rodar(env, tmp_path, com_mapas=False, com_dupla=False)
    try:
        assert not (res.gordura or res.ferro or res.dixon)
        assert any("não tem mapa" in a for a in res.avisos_gordura)
    finally:
        t.limpar()


def _campo(monkeypatch, tesla):
    real = F._cabecalho

    def outro_campo(repo, uid):
        ds = real(repo, uid)
        if ds is not None:
            ds.MagneticFieldStrength = tesla
        return ds
    monkeypatch.setattr(F, "_cabecalho", outro_campo)


def test_3t_converte_por_alam(env, tmp_path, monkeypatch):
    """0.99.50 — a 3 T: R2* ÷ 2,05 (Alam, JCMR 2016) e depois Wood."""
    _campo(monkeypatch, 3.0)
    t, res, _v, *_r = _rodar(env, tmp_path)
    try:
        f = res.ferro
        assert f["r2_15"]["v"] == pytest.approx(80 / 2.05, abs=0.06)
        assert f["lic"]["v"] == pytest.approx(0.0254 * 80 / 2.05 + 0.202, abs=0.01)
        assert any("Alam" in a for a in res.avisos_ferro)
        txt = F.frase({"tipo": F.TIPO_FERRO, "numeros": f, "estado": "confirmado"})
        assert "equivalente a 39 s⁻¹ a 1,5 T" in txt
    finally:
        t.limpar()


def test_outro_campo_nao_estima(env, tmp_path, monkeypatch):
    _campo(monkeypatch, 0.35)
    t, res, _v, *_r = _rodar(env, tmp_path)
    try:
        assert "lic" not in res.ferro and any("0,35 T" in a for a in res.avisos_ferro)
    finally:
        t.limpar()


def test_faixas_do_lic():
    assert F.grau_do_ferro(2.2).startswith("acima do normal") and F.grau_do_ferro(1.2) == "normal (< 1,8)"
    assert "leve" in F.grau_do_ferro(3.2) and "moderada" in F.grau_do_ferro(7.0)
    assert "grave" in F.grau_do_ferro(15.0) and F.grau_do_ferro(None) == ""
    assert F.r2_para_15t(80, 1.5) == (80, "1,5 T") and F.r2_para_15t(80, None)[0] is None


def test_na_tela(env, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, uid_anat = _exame(env, tmp_path)
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(msg))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, msg, *a, **k: avisos.append("ERRO " + msg))
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1300, 800)
    w.show()
    try:
        assert w.handle_external({"accession": "FIG01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        assert tab.app_na_barra("figado_rm")
        tab.figado_rm_automatico(tab.active or tab.viewports[0], simular=True)
        fim = time.time() + 120
        while not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert avisos and avisos[-1].startswith("Fígado na RM pronto"), avisos
        p = tab.achados_painel
        assert p.t.rowCount() == 3 and "%" in p.t.item(0, 2).text()
        tab.figado_rm_botao()
        assert tab.achados_painel.isVisible()
        # 0.100.88: refazer no exame, mesmo com achados (o botão só abre a revisão)
        primeiro = repo.achados(uid, F.FERRAMENTA)
        repo.revisar_achado(primeiro[0]["id"], "confirmado", "Dr. Teste")
        n = len(avisos)
        tab.refazer_ia("figado_rm", simular=True, descartar_revisados=True)
        fim = time.time() + 120
        while len(avisos) == n and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert avisos[-1].startswith("Fígado na RM pronto"), avisos
        depois = repo.achados(uid, F.FERRAMENTA)
        assert [a["estado"] for a in depois if a["id"] == primeiro[0]["id"]] == ["descartado"]
        assert sum(a["estado"] == "sugerido" for a in depois) == 3
    finally:
        w.close()


def test_contrato_e_aba(env):
    from PySide6.QtWidgets import QApplication

    from ipe.ai import ferramentas as FE
    from ipe.core.config import Settings
    from ipe.ui.cad_ia import CadIaTab
    QApplication.instance() or QApplication([])
    assert FE.modulo("figado_rm") is F
    paths, db, repo = env
    t = CadIaTab(Settings(paths.settings_file), repo)
    nomes = [t.l_ferramentas.item(k).text().split("\n")[0] for k in range(t.l_ferramentas.count())]
    assert F.NOME_CADIA in nomes
    assert [x["nome"] for x in F.tarefas()] == ["total_mr", "liver_segments_mr"]


def test_troca_agua_gordura_sai_da_conta():
    """0.100.86: num exame do acervo, 10% no fígado e 92–98% nos cortes da cúpula (troca do Dixon)."""
    v = np.r_[np.full(800, 10.0), np.full(200, 95.0)]
    fica, tirou = F.sem_troca(v)
    assert np.median(fica) == 10 and tirou == pytest.approx(0.2)
    gordo = np.r_[np.full(500, 40.0), np.full(500, 65.0)]        # esteatose grave de verdade: não mexe
    assert F.sem_troca(gordo)[1] == 0
    assert F.sem_troca(np.full(100, 8.0))[1] == 0


def test_classificacao_sugerida_de_gordura_e_ferro():
    """0.100.87: a classificação sugerida (como a das calcificações vasculares da mama)."""
    assert F.classificar_gordura(3.0) == "Sem esteatose (PDFF < 5%)"
    assert F.classificar_gordura(5.5).startswith("Esteatose discreta")
    assert F.classificar_gordura(16.0) == "Esteatose leve (grau 1)"
    assert F.classificar_gordura(20.0) == "Esteatose moderada (grau 2)"
    assert F.classificar_gordura(30.0) == "Esteatose acentuada (grau 3)"
    assert F.classificar_ferro(1.5) == "Sem sobrecarga de ferro"
    assert F.classificar_ferro(2.5).startswith("Ferro acima do normal")
    assert F.classificar_ferro(4.85) == "Sobrecarga de ferro leve"
    assert F.classificar_ferro(14.4) == "Sobrecarga de ferro moderada"
    assert F.classificar_ferro(20) == "Sobrecarga de ferro grave"
    g = {"tipo": F.TIPO_GORDURA, "numeros": {"pdff_mediana": {"v": 16.0, "u": "%", "n": "PDFF"}}, "corrigidos": {}}
    assert F.resultado_do_achado(g) == "Esteatose leve (grau 1)"
    esc = F.escalas_do_achado(g)
    assert esc[0][1].startswith("Sim") and esc[1][1] == "1 — leve" and "Tang" in esc[1][2]
    assert "compatível" not in F.frase(g) and F.frase(g).endswith("— esteatose leve (grau 1).")
    # corrigida pelo médico: vale a dele (também na frase do laudo)
    g2 = {**g, "corrigidos": {"pdff_mediana": 25.0, "classificacao": "Esteatose acentuada"}}
    assert F.resultado_do_achado(g2) == "Esteatose acentuada" and "esteatose acentuada" in F.frase(g2)
    fe = {"tipo": F.TIPO_FERRO, "corrigidos": {}, "numeros": {"lic": {"v": 14.38, "u": "mg Fe/g", "n": "LIC"},
          "r2_mediana": {"v": 558.0, "u": "s⁻¹", "n": "R2*"}, "baco_r2": {"v": 19.0, "u": "s⁻¹", "n": "baço"}}}
    assert F.resultado_do_achado(fe) == "Sobrecarga de ferro moderada"
    nomes = [e[0] for e in F.escalas_do_achado(fe)]
    assert nomes == ["Ferro estimado (LIC)", "R2*"] and "baço 19" in F.escalas_do_achado(fe)[1][1]


# ---------------------------------------------------------------------------------------------- 0.100.94
def _exame_com_elastografia(env, tmp_path):
    """O fantoma de cima e uma elastografia como a do MR-Touch (GE): a série de origem "Ax MR-Touch Standard" (12;
    fase de −π a π e magnitude ≥ 0 na mesma série), o elastograma inteiro "STGRY (Pa)" (1257) e o mascarado
    "STGRYM (Pa)" (1250), com o xadrez de zeros na área de baixa confiança, e a atenuação (1252)."""
    from pydicom.uid import generate_uid

    from ipe.core.sample_data import _base, _mono, _save
    uid, uid_anat = _exame(env, tmp_path, com_mapas=False, com_dupla=False)
    paths, db, repo = env
    info = repo.study_info(uid)
    pat = {"name": "FIGADO^Teste", "id": "FIG1", "birth": "19700101", "sex": "M"}
    study = {"uid": uid, "date": info["study_date"], "accession": "FIG01", "description": "RM ABDOME TOTAL",
             "for": generate_uid()}
    pasta = tmp_path / "mre"
    n, nz, px, dz, z0 = 64, 5, 2.0, 10.0, 25.0
    o = -(n / 2) * px
    mx, my, mz = _grade(n, nz, px, dz, o, z0)
    fig = _dentro(mx, my, mz, FIG)
    inteiro = np.full(mx.shape, 1500, np.int16)                # fora do fígado: 1,5 kPa
    inteiro[fig] = 3000                                        # fígado: 3,0 kPa
    ruim = fig & (my > 5)                                      # a parte de trás do fígado: baixa confiança
    inteiro[ruim] = 9000
    vaso = fig & (np.abs(mx - 0) < 3) & (my < 0)               # um vaso grande (vazio de fluxo) no meio
    inteiro[vaso] = 20000
    xadrez = ((np.indices(mx.shape[1:]).sum(axis=0) % 2) == 0)[None]
    mascarado = inteiro.copy()
    mascarado[ruim & xadrez] = 0
    mag = np.full(mx.shape, 400, np.int16)
    mag[vaso] = 40
    fase = np.full(mx.shape, -1000, np.int16)
    it = {"ImageType": ["DERIVED", "PRIMARY", "MR_ELASTOGRAPHY", "ELASTOGRAM"]}
    _serie(pasta, pat, study, "STGRY (Pa)", 1257, inteiro, px, dz, o, z0, extra=it)
    _serie(pasta, pat, study, "STGRYM (Pa)", 1250, mascarado, px, dz, o, z0, extra=it)
    _serie(pasta, pat, study, "Atten (m-1)", 1252, np.full(mx.shape, 10, np.int16), px, dz, o, z0,
           extra={"ImageType": ["DERIVED", "PRIMARY", "MR_ELASTOGRAPHY", "ATTENUATION"]})
    series = {"uid": generate_uid(), "number": 12, "description": "Ax MR-Touch Standard"}
    for k in range(nz):
        for j, img in enumerate((fase[k], mag[k])):
            ds = _base("1.2.840.10008.5.1.4.1.1.4", pat, study, series, "MR")
            ds.InstanceNumber = k * 2 + j + 1
            ds.ImagePositionPatient = [o, o, z0 + dz * k]
            ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
            ds.PixelSpacing = [px, px]
            ds.SliceThickness = 8
            ds.ImageType = ["ORIGINAL", "PRIMARY", "OTHER"]
            _mono(ds, img, signed=True)
            _save(ds, pasta / f"touch_{j}")
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([pasta])
    return uid, uid_anat


def test_rigidez_da_elastografia(env, tmp_path):
    from ipe.ai import elastografia_rm as EL
    from ipe.ai import ferramentas as FE
    from ipe.ai import totalseg as TS
    from ipe.imaging.series import FrameCache
    paths, db, repo = env
    uid, uid_anat = _exame_com_elastografia(env, tmp_path)
    aqs = EL.aquisicoes(repo, uid, F._cabecalho)
    assert len(aqs) == 1 and len(aqs[0]["elastogramas"]) == 2 and aqs[0]["descricao"] == "Ax MR-Touch Standard"
    assert aqs[0]["atenuacao"]
    t = TS.Trabalho(repo, FrameCache(256), None, uid, uid_anat, simular=True)
    FE.preparar_trabalho(t, F)
    t.preparar()
    t.rodar_aqui()
    res, versao = FE.rodar_conta(t, F, None)
    try:
        r = res.rigidez
        # só o fígado bom: nem a parte de baixa confiança (9 kPa) nem o vaso (20 kPa) entram
        assert r["kpa_media"]["v"] == pytest.approx(3.0, abs=0.01) and r["kpa_mediana"]["v"] == pytest.approx(3.0)
        assert r["faixa"]["v"] == "fibrose estágio 1–2" and r["cortes"]["v"] >= 3
        assert r["classificacao"]["v"] == "Rigidez compatível com fibrose estágio 1–2"
        assert 0 < r["fracao_confiavel"]["v"] < 100
        assert any("Venkatesh" in a for a in res.avisos_rigidez)
        saida = F.gravar(t, res, versao, db, paths.storage, repo=repo)
        ach = repo.achados(uid, F.FERRAMENTA)
        rig = [a for a in ach if a["tipo"] == F.TIPO_RIGIDEZ][0]
        assert F.frase(rig).startswith("Rigidez hepática média na elastografia por RM de 3,00 kPa")
        assert F.resultado_do_achado(rig) == "Rigidez compatível com fibrose estágio 1–2"
        assert F.escalas_do_achado(rig)[0][1] == "3,00 kPa — fibrose estágio 1–2"
        descs = [s.description for s in repo.series_for_study(uid)]
        assert any(d.startswith(F.DESC_RIGIDEZ) for d in descs) and len(saida["series"]) >= 2
    finally:
        t.limpar()


def test_confianca_pelo_xadrez_e_faixas():
    from ipe.ai import elastografia_rm as EL
    inteiro = np.full((1, 40, 40), 3000.0)
    masc = inteiro.copy()
    xadrez = (np.indices((40, 40)).sum(axis=0) % 2) == 0
    masc[0, 20:, :][xadrez[20:, :]] = 0
    v = EL.confianca(masc, inteiro)
    assert v[0, :17].all() and not v[0, 22:].any()
    assert EL.faixa(2.0) == "normal" and EL.faixa(2.7) == "normal ou inflamação" and EL.faixa(6.0).endswith("cirrose")
    assert EL.classificar(2.0) == "Rigidez hepática normal"
    assert EL.eh_elastograma(["DERIVED", "PRIMARY", "MR_ELASTOGRAPHY", "ELASTOGRAM"])
    assert not EL.eh_elastograma(["DERIVED", "SECONDARY", "SCREEN SAVE"], "ST8KM (Pa)")


def test_elastografia_sem_scipy(monkeypatch):
    """0.100.95: o programa não leva o SciPy — a rigidez caía com ModuleNotFoundError na máquina do usuário."""
    import sys
    monkeypatch.setitem(sys.modules, "scipy", None)
    monkeypatch.setitem(sys.modules, "scipy.ndimage", None)
    from ipe.ai import elastografia_rm as EL
    z, h, w = 3, 64, 64
    rig = np.full((z, h, w), 3000.0)
    inteiro = rig.copy()
    masc = rig.copy()
    masc[:, :20, :20][::1, ::2, ::2] = 0          # xadrez de baixa confiança num canto
    fig = np.zeros((z, h, w), bool)
    fig[:, 10:60, 10:60] = True
    valido = EL.confianca(masc, inteiro)
    assert not valido[0, 5, 5] and valido[0, 40, 40]
    m = EL.medir(rig, valido, fig, 1.0)
    assert m["cortes"] == 3 and abs(m["kpa_media"] - 3.0) < 1e-6
    img = EL.imagem_de_conferencia(rig, valido, fig, m["roi"], m, "teste")
    assert img.ndim == 3 and img.shape[2] == 3
