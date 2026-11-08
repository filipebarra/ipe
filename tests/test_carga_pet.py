"""0.99.89: carga tumoral no PET (limiar + órgãos do TotalSegmentator), miTNM e miPSMA."""
from types import SimpleNamespace

import numpy as np
import pytest
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from pydicom.uid import generate_uid

from test_modelos_extras import DZ, N, NZ, PX, _esfera, _serie

from ipe.ai import carga_pet as CP


def _codigo(nome):
    from ipe.ai.totalseg_worker import CARGA_SIM
    for tarefa in CARGA_SIM.values():
        for _cid, (cod, n) in tarefa.items():
            if n == nome:
                return 4000 + cod
    raise KeyError(nome)


def _fantoma(tracador: str):
    """TC com os órgãos codificados (HU = 4000 + código) e PET com focos conhecidos, na mesma grade."""
    ct = np.full((NZ, N, N), 40, np.int16)
    pet = np.full((NZ, N, N), 1.0)

    def org(nome, fatia, suv=None):
        ct[fatia] = _codigo(nome)
        if suv is not None:
            pet[fatia] = suv
    org("hip_left", np.s_[5:11, 30:36, 6:12])
    org("hip_right", np.s_[5:11, 30:36, 36:42])            # crista ilíaca: k = 10 → z = 20 mm
    org("urinary_bladder", np.s_[4:8, 18:26, 20:28], 20)    # fisiológico em todos os traçadores
    org("prostate", np.s_[1:3, 20:26, 20:28], 1.2)
    org("vertebrae_L3", np.s_[14:19, 30:38, 20:28], 1.2)
    org("liver", np.s_[20:29, 6:22, 4:20], 2.0)
    org("aorta", np.s_[12:30, 26:30, 30:34], 1.5)
    org("kidney_left", np.s_[16:20, 30:36, 36:42], 15)
    org("lung_upper_lobe_left", np.s_[30:34, 8:20, 30:42], 0.5)
    org("brain", np.s_[35:40, 14:34, 14:34], 10 if tracador == "fdg" else 1)
    org("parotid_gland_left", np.s_[33:35, 30:34, 10:14], 12)
    org("parotid_gland_right", np.s_[33:35, 30:34, 34:38], 12)
    pet[1:3, 20:26, 21:27] = 6.0                     # lesão na próstata (T)
    pet[15:18, 31:37, 21:27] = 7.0                   # lesão óssea (L3)
    pet[_esfera((7, 12, 40), 7)] = 8.0               # linfonodo pélvico (abaixo da crista, fora dos órgãos)
    pet[_esfera((24, 36, 44), 7)] = 6.0              # linfonodo extrapélvico
    pet[_esfera((24, 14, 12), 7)] = 9.0              # lesão hepática (no PSMA o fígado é tirado)
    pet[_esfera((31, 14, 36), 6)] = 5.0              # nódulo pulmonar (víscera)
    return ct, pet


def _exame(tmp_path, env, tracador: str, nome: str):
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    ct, pet = _fantoma(tracador)
    pat = {"name": f"CARGA^{nome}", "id": f"CG{nome}", "birth": "19550101", "sex": "M"}
    study = {"uid": generate_uid(), "date": "20261108", "accession": f"CG{nome}",
             "description": "PET-CT " + ("PSMA" if tracador == "psma" else "ONCO"), "for": generate_uid()}
    rf = Dataset()
    rf.Radiopharmaceutical = "Ga-68 PSMA-11" if tracador == "psma" else "Fluorodeoxyglucose"
    _serie(tmp_path / nome, pat, study, "CT STD", "CT", ct, 2)
    uid_pet = _serie(tmp_path / nome, pat, study, "PET AC", "PT", np.rint(pet * 100).astype(np.int16), 3,
                     {"Units": "GML", "RescaleSlope": 0.01, "RadiopharmaceuticalInformationSequence": Sequence([rf])})
    Importer(db, paths.storage).import_paths([tmp_path / nome])
    return study["uid"], uid_pet, pet


def _rodar(env, study):
    from ipe.ai import ferramentas as FE
    from ipe.ai import totalseg as TS
    from ipe.imaging.series import FrameCache
    paths, db, repo = env
    serie, motivo = CP.escolher_serie(repo, study)
    assert serie, motivo
    t = TS.Trabalho(repo, FrameCache(64), None, study, serie, simular=True)
    FE.preparar_trabalho(t, CP)
    t.preparar()
    t.rodar_aqui()
    res, versao = FE.rodar_conta(t, CP, None)
    return t, res, versao


def test_psma_regioes_mitnm_e_mipsma(env, tmp_path):
    from ipe.ai import ferramentas as FE
    paths, db, repo = env
    study, uid_pet, pet = _exame(tmp_path, env, "psma", "P")
    assert CP.exame_serve({"modalities": "CT\\PT", "description": "PET-CT PSMA"})
    assert not CP.exame_serve({"modalities": "PT", "description": "PET-CT PSMA"})
    t, res, versao = _rodar(env, study)
    assert t.tracador == "psma" and any(x["nome"] == "head_glands_cavities" for x in t.lista_tarefas)
    assert res.tracador == "psma" and res.limiar == pytest.approx(3.0)
    regioes = sorted(x.regiao for x in res.lesoes)
    # próstata, osso, linfonodo pélvico, linfonodo extrapélvico, pulmão; o fígado é tirado; bexiga e rim também
    assert regioes == sorted(["prost", "osso", "lnp", "lne", "visc"]), [(x.regiao, x.local) for x in res.lesoes]
    osso = next(x for x in res.lesoes if x.regiao == "osso")
    assert "L3" in osso.local and osso.suvmax == pytest.approx(7.0)
    assert res.mitnm == "miT+ miN1 miM1a, M1b (uni), M1c"
    # referências e escore: pool 1,5, fígado 2,0, parótida 12
    assert res.refs["pool"] == pytest.approx(1.5) and res.refs["figado"] == pytest.approx(2.0, abs=0.01)
    assert res.refs["parotida"] == pytest.approx(12.0)
    assert {x.regiao: x.mipsma for x in res.lesoes}["osso"] == 2          # 7 está entre o fígado e a parótida
    assert any("fígado está entre os órgãos tirados" in a for a in res.avisos)
    voxel_ml = PX * PX * DZ / 1000
    assert res.mtv == pytest.approx(sum(x.vol_ml for x in res.lesoes))
    assert osso.vol_ml == pytest.approx(3 * 6 * 6 * voxel_ml)
    # banco, SEG e laudo pelos confirmados (descartar tira do total)
    out = FE.gravar(t, CP, res, versao, db, paths.storage, repo, None)
    assert CP.ja_feita(repo, study) and len(out["achados"]) == 1 + len(res.lesoes)
    achados = repo.achados(study, "carga_pet")
    resumo = next(a for a in achados if a["tipo"] == CP.TIPO_RESUMO)
    assert resumo["local"].startswith("PSMA · miT+")
    lesoes = [a for a in achados if a["tipo"] == CP.TIPO_LESAO]
    for a in lesoes:
        repo.revisar_achado(a["id"], "descartado" if a["local"].startswith("pulmão") else "confirmado", "teste")
    achados = repo.achados(study, "carga_pet")
    txt = CP.laudo(achados)
    assert "4 foco(s) confirmado(s)" in txt and "1 próstata" in txt and "1 osso" in txt
    assert "miT+ miN1 miM1a, M1b (uni)" in txt and "M1c" not in txt         # o pulmão foi descartado
    assert "Escore miPSMA máximo" in txt
    t.limpar()


def test_fdg_percist_e_fisiologico(env, tmp_path):
    study, uid_pet, pet = _exame(tmp_path, env, "fdg", "F")
    t, res, versao = _rodar(env, study)
    assert res.tracador == "fdg" and "PERCIST" in res.limiar_como
    assert res.limiar == pytest.approx(1.5 * 2.0 + 2 * 0.0, abs=0.05)          # fígado homogêneo (DP ≈ 0)
    locais = [x.local for x in res.lesoes]
    assert any(x.startswith("fígado") for x in locais)                          # no FDG o fígado entra
    assert not any("encéfalo" in x for x in locais)                             # cérebro é fisiológico
    assert res.mitnm == "" and all(x.mipsma is None for x in res.lesoes)
    assert "FDG" in CP.resumo(res)
    t.limpar()


def test_tracador_pelo_cabecalho():
    def ds(rf="", estudo="", serie=""):
        d = Dataset()
        if rf:
            it = Dataset()
            it.Radiopharmaceutical = rf
            d.RadiopharmaceuticalInformationSequence = Sequence([it])
        d.StudyDescription, d.SeriesDescription = estudo, serie
        return d
    assert CP.tracador_do_cabecalho(ds("Fludeoxyglucose F^18^")) == "fdg"
    assert CP.tracador_do_cabecalho(ds("Ga-68 PSMA-11")) == "psma"
    assert CP.tracador_do_cabecalho(ds("", "PET CT 18F-DCFPyL")) == "psma"
    assert CP.tracador_do_cabecalho(ds("Ga68 DOTATATE")) == "sstr"
    assert CP.tracador_do_cabecalho(ds("", "PTCT GALIO")) == ""


def test_mitnm_e_escore():
    L = [SimpleNamespace(regiao=r) for r in ("osso", "osso", "osso", "osso", "lnp")]
    assert CP.mitnm(L) == "miT0 miN1 miM1b (dissem.)"
    assert CP.mitnm([]) == "miT0 miN0 miM0"
    refs = {"pool": 1.5, "figado": 5.0, "parotida": 15.0}
    assert [CP.escore_mipsma(v, refs) for v in (1.0, 3.0, 8.0, 20.0)] == [0, 1, 2, 3]
    assert CP.escore_mipsma(3.0, {}) is None


def test_rotulos_na_grade_vizinho_mais_proximo():
    from ipe.imaging.volume import Volume
    fino = np.zeros((8, 8, 8), np.uint8)
    fino[2:6, 2:6, 2:6] = 7
    v_fino = Volume(fino, np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0]),
                    1.0, 1.0, None, "")
    grosso = Volume(np.zeros((4, 4, 4)), np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
                    np.array([0, 0, 2.0]), 2.0, 2.0, None, "")
    r = CP.rotulos_na_grade(grosso, v_fino, fino)
    assert r.shape == (4, 4, 4) and r[1:3, 1:3, 1:3].all() and r[0, 0, 0] == 0 and r[3, 3, 3] == 0
