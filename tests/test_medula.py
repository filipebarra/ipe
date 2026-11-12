"""0.100.26: medula e canal por nível (TotalSpineSeg) — área, diâmetros, MSCC e MCC no plano perpendicular.

Fantoma de 1 mm: uma medula elíptica (8 × 13 mm) dentro de um canal (14 × 20 mm), **inclinada 15°** no plano
sagital (para o corte axial não servir de régua), com um estreitamento em C5-C6 (medula 5 mm, canal 9 mm).
Os discos e os corpos vertebrais são blocos à frente do canal, com os rótulos do TotalSpineSeg.
O trabalhador roda simulado (valor do voxel = 1000 + rótulo).
"""
import numpy as np
import pytest

from ipe.ai import medula as MD
from ipe.imaging.volume import Volume

INCL = np.radians(15.0)
X = np.arange(-25, 26, 1.0)
Y = np.arange(-40, 41, 1.0)
Z = np.arange(60, -61, -1.0)                 # de cima para baixo
#: z do centro de cada disco e de cada corpo (mm)
DISCOS_Z = {63: 48.0, 64: 32.0, 65: 16.0, 66: 0.0, 67: -16.0, 71: -32.0}
CORPOS_Z = {12: 56.0, 13: 40.0, 14: 24.0, 15: 8.0, 16: -8.0, 17: -24.0, 21: -40.0}
AP, RL, C_AP, C_RL = 8.0, 13.0, 14.0, 20.0
AP_EST, C_AP_EST = 5.0, 9.0                  # em C5-C6 (rótulo 66)


def fantoma():
    zz, yy, xx = np.meshgrid(Z, Y, X, indexing="ij")
    yc = np.tan(INCL) * zz                                  # a medula vai para trás ao subir
    # a "altura" medida ao longo da medula (no eixo dela vale z): discos e corpos ficam perpendiculares a ela
    ww = (yy * np.sin(INCL) + zz * np.cos(INCL)) * np.cos(INCL)
    perto = np.clip((7.0 - np.abs(ww - DISCOS_Z[66])) / 4.0, 0.0, 1.0)    # 1 até 3 mm do disco, 0 a 7 mm
    ap = AP - (AP - AP_EST) * perto
    cap = C_AP - (C_AP - C_AP_EST) * perto
    # o AP "verdadeiro" é perpendicular à medula: no corte axial ele aparece dividido por cos(15°)
    dy = (yy - yc) * np.cos(INCL)
    lab = np.zeros(xx.shape, np.uint8)
    lab[(dy / (cap / 2)) ** 2 + (xx / (C_RL / 2)) ** 2 <= 1] = MD.CANAL
    lab[(dy / (ap / 2)) ** 2 + (xx / (RL / 2)) ** 2 <= 1] = MD.MEDULA
    frente = (yy - yc < -9) & (yy - yc > -27) & (np.abs(xx) < 14)
    for cod, z0 in DISCOS_Z.items():
        lab[frente & (np.abs(ww - z0) <= 2)] = cod
    for cod, z0 in CORPOS_Z.items():
        lab[frente & (np.abs(ww - z0) <= 5)] = cod
    vol = Volume(np.where(lab > 0, 1000 + lab.astype(np.int16), 0).astype(np.int16),
                 np.array([X[0], Y[0], Z[0]], float), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
                 np.array([0, 0, -1.0]), 1.0, 1.0, None, "")
    return vol, lab


class _T:
    """O mínimo de um Trabalho para a conta."""
    def __init__(self, vol):
        self.vol, self.series_uid, self.descricao_serie, self.versao = vol, "1.2.3", "SAG 3D T2", "teste"


@pytest.fixture(scope="module")
def res():
    vol, lab = fantoma()
    return MD.calcular(_T(vol), {"totalspineseg": (lab, {})})


def test_linha_central_inclinada():
    vol, lab = fantoma()
    linha = MD.linha_central(lab == MD.MEDULA, vol)
    assert len(linha) > 100 and linha[0][2] > linha[-1][2]
    d = linha[10] - linha[-10]
    assert np.degrees(np.arctan2(d[1], d[2])) == pytest.approx(15.0, abs=1.0)


def test_niveis_e_nomes(res):
    assert res.calculado and [n.nome for n in res.discos()] == ["C2-C3", "C3-C4", "C4-C5", "C5-C6", "C6-C7", "C7-T1"]
    assert not res.aproximado


def test_medidas_perpendiculares(res):
    n = {x.nome: x for x in res.niveis}
    normal = n["C3-C4"]
    assert normal.ap == pytest.approx(AP, abs=0.8) and normal.rl == pytest.approx(RL, abs=0.8)   # máscara de 1 mm
    assert normal.area == pytest.approx(np.pi * AP * RL / 4, rel=0.08)
    assert normal.razao == pytest.approx(AP / RL, abs=0.06)
    assert normal.canal_ap == pytest.approx(C_AP, abs=0.9)
    assert normal.ocupacao == pytest.approx(100 * (AP * RL) / (C_AP * C_RL), abs=4)
    est = n["C5-C6"]
    assert est.ap == pytest.approx(AP_EST, abs=0.8) and est.canal_ap == pytest.approx(C_AP_EST, abs=0.9)
    assert est.razao == pytest.approx(AP_EST / RL, abs=0.06)
    assert normal.ap < AP + 0.1                         # o corte axial daria AP/cos(15°) = 8,3 mm


def test_mscc_e_mcc(res):
    n = {x.nome: x for x in res.niveis}
    assert n["C5-C6"].mscc == pytest.approx(100 * (1 - AP_EST / AP), abs=6)          # 37,5%
    assert n["C5-C6"].mcc == pytest.approx(100 * (1 - C_AP_EST / C_AP), abs=6)       # 35,7%
    assert abs(n["C3-C4"].mscc) < 6 and abs(n["C3-C4"].mcc) < 6
    assert res.pior().nome == "C5-C6"
    assert "C5-C6" in MD.resumo(res) and "MSCC" in MD.resumo(res)


def test_serie_sagital_grossa_avisa():
    vol, lab = fantoma()
    # a mesma anatomia vista como sagital de 4 mm: o eixo dos cortes passa a ser o x
    lab_s = np.ascontiguousarray(lab[:, :, ::4].transpose(2, 0, 1))          # (corte x, linha z, coluna y)
    vol_s = Volume(np.where(lab_s > 0, 1000 + lab_s.astype(np.int16), 0).astype(np.int16),
                   np.array([X[0], Y[0], Z[0]], float), np.array([0, 1.0, 0]), np.array([0, 0, -1.0]),
                   np.array([4.0, 0, 0]), 1.0, 1.0, None, "")
    r = MD.calcular(_T(vol_s), {"totalspineseg": (lab_s, {})})
    assert r.calculado and r.aproximado and any("aproximados" in a for a in r.avisos)
    n = {x.nome: x for x in r.niveis}
    assert n["C5-C6"].ap == pytest.approx(AP_EST, abs=0.8)                   # o AP continua valendo
    assert n["C5-C6"].mscc == pytest.approx(37.5, abs=8)


def test_sem_medula():
    vol, lab = fantoma()
    r = MD.calcular(_T(vol), {"totalspineseg": (np.zeros_like(lab), {})})
    assert not r.calculado and r.avisos and MD.itens_para_o_banco(r, _T(vol), "") == []
    assert not MD.calcular(_T(vol), {}).calculado


def _exame(env, tmp_path):
    from pydicom.uid import generate_uid

    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    vol, lab = fantoma()
    hu = vol.data
    pat = {"name": "EXEMPLO^Medula", "id": "MD1", "birth": "19700101", "sex": "M"}
    study = {"uid": generate_uid(), "date": "20261112", "accession": "MD01", "description": "RM COLUNA CERVICAL",
             "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 3, "description": "AX 3D T2"}
    d = tmp_path / "md"
    for k in range(hu.shape[0]):
        ds = _base("1.2.840.10008.5.1.4.1.1.4", pat, study, series, "MR")
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [float(X[0]), float(Y[0]), float(Z[k])]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [1.0, 1.0]
        ds.SliceThickness = 1.0
        _mono(ds, hu[k], signed=True)
        _save(ds, d)
    Importer(db, paths.storage).import_paths([d])
    return study["uid"], series["uid"]


def test_do_exame_aos_achados(env, tmp_path):
    from PySide6.QtWidgets import QApplication

    from ipe.ai import ferramentas as FE
    from ipe.ai import totalseg as TS
    from ipe.imaging.series import FrameCache
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie = _exame(env, tmp_path)
    assert FE.modulo("medula") is MD and MD.escolher_serie(repo, uid)[0] == serie
    assert MD.exame_serve({"modalities": "MR", "description": "RM COLUNA CERVICAL"})
    assert not MD.exame_serve({"modalities": "MR", "description": "RM CRANIO"})
    t = TS.Trabalho(repo, FrameCache(256), None, uid, serie, simular=True)
    FE.preparar_trabalho(t, MD)
    t.preparar()
    try:
        t.rodar_aqui()
        res, versao = FE.rodar_conta(t, MD, None)
        saida = FE.gravar(t, MD, res, versao, db, paths.storage, repo, None)
    finally:
        t.limpar()
    ach = repo.achados(uid, "medula")
    assert len(ach) == 7 and ach[0]["tipo"] == MD.TIPO_RESUMO and MD.ja_feita(repo, uid)
    c56 = next(a for a in ach if a.get("local") == "C5-C6")
    txt = MD.frase(c56)
    assert txt.startswith("C5-C6: medula com") and "MSCC" in txt and "canal com" in txt
    assert "maior compressão medular (MSCC)" in MD.frase(ach[0])
    assert MD.laudo(ach) == ""                                   # nada vai ao laudo sem revisão
    confirmados = [dict(a, estado="confirmado") for a in ach]
    linhas = MD.laudo(confirmados).splitlines()
    assert len(linhas) == 7 and linhas[0].startswith("- Medula e canal medidos em 6 níveis")
    assert [x.split(":")[0] for x in linhas[1:]] == ["- C2-C3", "- C3-C4", "- C4-C5", "- C5-C6", "- C6-C7", "- C7-T1"]
    descs = [s.description for s in repo.series_for_study(uid)]
    assert descs.count(MD.DESC_SEG) == 1 and saida["seg_path"]
    assert "Medula pronta" in MD.mensagem(res, 3.0)


def test_modelo_extra_ambiente_proprio(tmp_path, monkeypatch):
    from ipe import creditos
    from ipe.ai import extras as EX
    from ipe.ai import instalar_modelos_extras as IM
    from ipe.ai import totalseg as TS
    from ipe.ai import totalseg_worker as W
    assert "medula" in EX.MODELOS and "medula" in IM.PASSOS
    assert any(c.nome == "TotalSpineSeg" and c.licenca == "LGPL-3.0" for c in creditos.CREDITOS)
    monkeypatch.setattr(TS, "instalado", lambda _s=None: True)
    monkeypatch.setattr(TS, "pasta_base", lambda: tmp_path / "seg")
    assert "ambiente" in EX.prontidao("medula").falta
    sp = tmp_path / "seg" / "venv_medula" / "lib" / "python3.12" / "site-packages"
    (sp / "totalspineseg").mkdir(parents=True)
    (tmp_path / "seg" / "venv_medula" / "bin").mkdir()
    (tmp_path / "seg" / "venv_medula" / "bin" / "python").write_text("")
    assert EX.prontidao("medula").pronto
    monkeypatch.setenv("IPE_PESOS", str(tmp_path / "seg" / "pesos"))
    assert W._python_da_medula() == tmp_path / "seg" / "venv_medula" / "bin" / "python"
    import inspect
    fonte = inspect.getsource(IM.medula)
    assert "kornia==0.8.1" in fonte and "venv_medula" in fonte      # o kornia 0.9 quebra o auglab (12/11/2026)
