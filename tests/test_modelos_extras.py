"""Modelos extras (0.99.83; itens 1, 2 e 4 da lista do MedMLX): MedSAM2 (caixa), autoPET (PET-FDG) e BraTS (glioma).

Os modelos de verdade rodam no ambiente da segmentação do computador dele; aqui, o trabalhador simulado
(geometria conhecida) testa todo o caminho do programa: a caixa, os canais extras (TC no PET, sequências
registradas), a conta, os achados, a SEG e a tela.
"""
import time

import numpy as np
import pytest
from pydicom.uid import generate_uid

from ipe.ai import autopet as AP
from ipe.ai import brats as BR
from ipe.ai import extras as EX
from ipe.ai import medsam2 as MS

N, NZ, PX, DZ = 48, 40, 2.0, 2.0


def _serie(pasta, pat, study, desc, mod, vol, numero, extra=None):
    from ipe.core.sample_data import _base, _mono, _save
    series = {"uid": generate_uid(), "number": numero, "description": desc}
    sop = {"CT": "1.2.840.10008.5.1.4.1.1.2", "MR": "1.2.840.10008.5.1.4.1.1.4",
           "PT": "1.2.840.10008.5.1.4.1.1.128"}[mod]
    for k in range(vol.shape[0]):
        ds = _base(sop, pat, study, series, mod)
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [0, 0, DZ * k]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [PX, PX]
        ds.SliceThickness = DZ
        ds.RescaleSlope, ds.RescaleIntercept = 1, 0
        for kk, vv in (extra or {}).items():
            setattr(ds, kk, vv)
        _mono(ds, vol[k].astype(np.int16), signed=True)
        _save(ds, pasta / series["uid"])
    return series["uid"]


def _esfera(c, r):
    z, y, x = np.mgrid[0:NZ, 0:N, 0:N]
    return ((z - c[0]) * DZ) ** 2 + ((y - c[1]) * PX) ** 2 + ((x - c[2]) * PX) ** 2 <= r * r


def _janela(env):
    from PySide6.QtWidgets import QApplication

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1300, 800)
    w.show()
    return app, w


def _esperar(app, cond, seg=120):
    fim = time.time() + seg
    while not cond() and time.time() < fim:
        app.processEvents()
        time.sleep(0.05)
    return cond()


# ------------------------------------------------------------------ prontidão e instalador
def test_prontidao_e_instalador(tmp_path, monkeypatch):
    from ipe.ai import totalseg as TS
    monkeypatch.setattr(TS, "pasta_base", lambda: tmp_path / "seg")
    assert all(not EX.prontidao(m).pronto for m in EX.MODELOS)
    assert "segmentação" in EX.prontidao("medsam2").falta
    assert EX.comando_do_instalador(("medsam2",)) is None
    py = tmp_path / "seg" / "venv" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("")
    sp = tmp_path / "seg" / "venv" / "lib" / "python3.12" / "site-packages"
    (sp / "sam2").mkdir(parents=True)
    assert EX.prontidao("medsam2").falta.startswith("faltam os pesos")
    (tmp_path / "seg" / "pesos" / "medsam2").mkdir(parents=True)
    (tmp_path / "seg" / "pesos" / "medsam2" / "MedSAM2_latest.pt").write_bytes(b"x")
    assert EX.prontidao("medsam2").pronto
    (sp / "monai").mkdir()
    (tmp_path / "seg" / "pesos" / "brats").mkdir()
    (tmp_path / "seg" / "pesos" / "brats" / "model.pt").write_bytes(b"x")
    assert EX.prontidao("brats").pronto
    (sp / "nnunetv2").mkdir()
    assert not EX.prontidao("autopet").pronto
    f = tmp_path / "seg" / "pesos" / "autopet" / "Dataset221" / "nnUNetTrainer__nnUNetPlans__3d_fullres_resenc_bs80"
    (f / "fold_0").mkdir(parents=True)
    (f / "fold_0" / "checkpoint_final.pth").write_bytes(b"x")
    assert EX.prontidao("autopet").pronto
    assert "pronto" in EX.texto_prontidao()
    cmd = EX.comando_do_instalador(("medsam2", "nada"))
    assert cmd[0] == str(py) and cmd[1].endswith("instalar_modelos_extras.py") and cmd[2:] == ["medsam2"]
    # o instalador em si: não importa nada do Ipê e sabe os três passos
    src = EX.caminho_do_instalador().read_text(encoding="utf-8")
    assert "import ipe" not in src and "from ipe" not in src
    from ipe.ai import instalar_modelos_extras as IN
    assert set(IN.PASSOS) == set(EX.MODELOS)
    assert IN.URL_MEDSAM2_PESOS.endswith("MedSAM2_latest.pt") and "8362371" in IN.ZENODO_AUTOPET
    assert IN.URL_BRATS.endswith("model.pt")


def test_na_grade_com_e_sem_registro():
    from ipe.imaging.volume import Volume
    d = np.zeros((10, 20, 20), np.float32)
    d[5, 10, 12] = 100
    a = Volume(d, np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0]), 1.0, 1.0, None, "")
    b = Volume(d, np.array([2.0, 0, 0]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0]), 1.0, 1.0,
               None, "")
    out = EX.na_grade(a, b)
    assert out[5, 10, 14] == pytest.approx(100)              # b começa 2 mm à frente em x
    M = np.eye(4)
    M[0, 3] = 2.0                                            # p_A → p_B: +2 mm em x
    assert EX.na_grade(a, b, M)[5, 10, 12] == pytest.approx(100)


# ------------------------------------------------------------------ MedSAM2
def test_medsam2_caixa_e_resultado():
    from ipe.ai import totalseg_worker as W
    from ipe.imaging.volume import Volume
    vol = np.full((NZ, N, N), 40, np.int16)
    les = _esfera((20, 24, 24), 10)
    vol[les] = 120
    v = Volume(vol, np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, DZ]), PX, PX, None, "")
    caixa = MS.caixa_no_volume(v, [v.voxel_to_patient(i, j, 20) for i, j in ((17, 17), (31, 17), (17, 31), (31, 31))])
    assert caixa == (20, 17.0, 17.0, 31.0, 31.0)
    assert MS.caixa_no_volume(v, [v.voxel_to_patient(10, 10, 20)] * 4) is None          # pequena demais
    t = MS.tarefa(caixa, (-100, 300))
    assert t["nome"] == "medsam2" and t["janela"] == [-100.0, 300.0]
    lab, _c = W._sim_medsam2(vol, t)
    res = MS.resultado(v, lab, caixa)
    voxel_ml = PX * PX * DZ / 1000
    assert res.voxels == les.sum() and res.ml == pytest.approx(les.sum() * voxel_ml)
    assert res.method == "medsam2" and res.mean == pytest.approx(120) and res.max_diam_mm > 15
    # só os cortes contíguos ao da caixa: uma "lesão" separada embaixo não entra
    vol2 = vol.copy()
    vol2[2:4, 20:28, 20:28] = 120
    lab2, _ = W._sim_medsam2(vol2, t)
    assert lab2[2:4].sum() == 0


def test_medsam2_na_tela(env, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from ipe.importer.scanner import Importer
    paths, db, repo = env
    vol = np.full((NZ, N, N), 40, np.int16)
    vol[_esfera((20, 24, 24), 10)] = 120
    pat = {"name": "CAIXA^Teste", "id": "MS1", "birth": "19600101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20261106", "accession": "MS01", "description": "TC ABDOME",
             "for": generate_uid()}
    _serie(tmp_path / "ms", pat, study, "AX PORTAL", "CT", vol, 3)
    Importer(db, paths.storage).import_paths([tmp_path / "ms"])
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(msg))
    app, w = _janela(env)
    try:
        assert w.handle_external({"accession": "MS01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        vp = next(v for v in tab.viewports if v.frames)
        vp.set_index_silently(20)
        app.processEvents()
        assert "caixa_ia" in __import__("ipe.ui.viewer.annotate", fromlist=["TOOLS"]).TOOLS
        seg = tab.caixa_ia(vp, 17, 17, 31, 31, simular=True)
        assert seg is not None
        assert _esperar(app, lambda: any(d.isVisible() for d in getattr(tab, "_seg_dialogs", []))), avisos
        dlg = [d for d in tab._seg_dialogs if d.isVisible()][-1]
        assert dlg.method.currentData() == "medsam2" and dlg.res is not None and dlg.res.voxels > 500
        assert dlg.obj.volumes                                   # aparece em qualquer plano e no 3D
        dlg.close()
    finally:
        w.close()


# ------------------------------------------------------------------ autoPET
def _pet_ct(tmp_path, env):
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    ct = np.full((NZ, N, N), 40, np.int16)
    ct[30:36, 18:30, 18:30] = 37                       # "cérebro" (captação fisiológica que o modelo ignora)
    pet = np.full((NZ, N, N), 1, np.int16)
    pet[_esfera((15, 24, 16), 6)] = 8                  # lesão 1 (SUV 8)
    pet[_esfera((15, 24, 34), 4)] = 5                  # lesão 2 (SUV 5)
    pet[30:36, 18:30, 18:30] = 9                       # cérebro quente
    pat = {"name": "PET^Teste", "id": "AP1", "birth": "19600101", "sex": "M"}
    study = {"uid": generate_uid(), "date": "20261106", "accession": "AP01", "description": "PET-CT FDG",
             "for": generate_uid()}
    _serie(tmp_path / "pet", pat, study, "CT AC", "CT", ct, 2)
    uid_pet = _serie(tmp_path / "pet", pat, study, "PET WB AC", "PT", pet, 3, {"Units": "GML"})
    Importer(db, paths.storage).import_paths([tmp_path / "pet"])
    return study["uid"], uid_pet, pet


def test_autopet_conta_e_achados(env, tmp_path):
    from ipe.ai import ferramentas as FE
    from ipe.ai import totalseg as TS
    from ipe.imaging.series import FrameCache
    paths, db, repo = env
    study, uid_pet, pet = _pet_ct(tmp_path, env)
    assert AP.escolher_serie(repo, study)[0] == uid_pet
    assert AP.serie_ct(repo, study) is not None
    assert AP.exame_serve({"modalities": "CT\\PT", "description": "PET-CT FDG"})
    assert not AP.exame_serve({"modalities": "CT", "description": "PET-CT FDG"})
    t = TS.Trabalho(repo, FrameCache(64), None, study, uid_pet, simular=True)
    FE.preparar_trabalho(t, AP)
    assert t.canais_extras is AP.canais_extras
    t.preparar()
    assert (t.pasta / "canal_ct.npy").exists() and (t.pasta / "canal_suv.npy").exists()
    t.rodar_aqui()
    res, versao = FE.rodar_conta(t, AP, None)
    assert len(res.lesoes) == 2 and res.fator == 1.0
    a, b = res.lesoes                                   # a de maior TLG primeiro
    assert a.suvmax == pytest.approx(8) and b.suvmax == pytest.approx(5)
    voxel_ml = PX * PX * DZ / 1000
    assert res.mtv == pytest.approx(((pet == 8) | (pet == 5)).sum() * voxel_ml)
    assert res.tlg == pytest.approx(8 * (pet == 8).sum() * voxel_ml + 5 * (pet == 5).sum() * voxel_ml, rel=1e-4)
    itens = AP.itens_para_o_banco(res, t, versao)
    assert [i["rotulo"] for i in itens] == ["T", "P1", "P2"]
    f = AP.frase({**itens[0], "corrigidos": {}})
    assert f.startswith("Volume metabólico tumoral total (MTV)") and "2 lesão(ões)" in f
    assert "SUVmáx 8,0" in AP.frase({**itens[1], "corrigidos": {}})
    out = FE.gravar(t, AP, res, versao, db, paths.storage, repo, None)
    assert AP.ja_feita(repo, study) and len(out["achados"]) == 3
    t.limpar()


def test_autopet_sem_tc_ou_sem_suv(env, tmp_path):
    from ipe.ai import ferramentas as FE
    from ipe.ai import totalseg as TS
    from ipe.importer.scanner import Importer
    from ipe.imaging.series import FrameCache
    paths, db, repo = env
    pet = np.full((NZ, N, N), 1, np.int16)
    pat = {"name": "PET^SoPET", "id": "AP2", "birth": "19600101", "sex": "M"}
    study = {"uid": generate_uid(), "date": "20261106", "accession": "AP02", "description": "PET FDG",
             "for": generate_uid()}
    uid = _serie(tmp_path / "p2", pat, study, "PET WB AC", "PT", pet, 3, {"Units": "GML"})
    Importer(db, paths.storage).import_paths([tmp_path / "p2"])
    t = TS.Trabalho(repo, FrameCache(64), None, study["uid"], uid, simular=True)
    FE.preparar_trabalho(t, AP)
    with pytest.raises(TS.Falhou, match="TC"):
        t.preparar()


# ------------------------------------------------------------------ BraTS
def test_brats_tipos_de_serie():
    T = BR.tipo_da_serie
    assert T("AX T1 POS GD") == "t1c" and T("3D T1 MPRAGE +C") == "t1c" and T("T1 PÓS") == "t1c"
    assert T("AX T1 SE") == "t1" and T("SAG T1 3D") == "t1"
    assert T("AX T2 TSE") == "t2" and T("AX T2 FLAIR") == "flair" and T("COR FLAIR 3D") == "flair"
    assert T("AX T2* GRE") == "" and T("SWI") == "" and T("DWI b1000") == "" and T("ADC") == ""


def _cranio(tmp_path, env, sem=()):
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    cab = _esfera((20, 24, 24), 40)
    t1c = np.where(cab, 500, 0).astype(np.int16)
    t1c[_esfera((20, 24, 30), 8)] = 950                # captante
    t1c[_esfera((20, 24, 30), 4)] = 350                # necrose central
    flair = np.where(cab, 400, 0).astype(np.int16)
    flair[_esfera((20, 24, 30), 14)] = 750             # edema em volta
    pat = {"name": "GLIOMA^Teste", "id": "BR1", "birth": "19700101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20261106", "accession": "BR01", "description": "RM CRANIO TUMOR",
             "for": generate_uid()}
    uid = _serie(tmp_path / "br", pat, study, "AX T1 POS GD", "MR", t1c, 10)
    for i, (desc, v) in enumerate((("AX T1 SE", np.where(cab, 450, 0)), ("AX T2 TSE", np.where(cab, 600, 0)),
                                   ("AX T2 FLAIR", flair)), start=1):
        if desc.split()[-1].lower() in sem or desc.split()[1].lower() in sem:
            continue
        _serie(tmp_path / "br", pat, study, desc, "MR", np.asarray(v, np.int16), 10 + i)
    Importer(db, paths.storage).import_paths([tmp_path / "br"])
    return study["uid"], uid


def test_brats_conta_registro_e_achado(env, tmp_path):
    from ipe.ai import ferramentas as FE
    from ipe.ai import totalseg as TS
    from ipe.imaging.series import FrameCache
    paths, db, repo = env
    study, uid = _cranio(tmp_path, env)
    assert BR.escolher_serie(repo, study) == (uid, "")
    assert [t["nome"] for t in BR.tarefas()] == ["total_mr", "brats"]
    t = TS.Trabalho(repo, FrameCache(64), None, study, uid, simular=True)
    FE.preparar_trabalho(t, BR)
    t.preparar()
    for n in ("t1", "t2", "flair"):
        assert (t.pasta / f"canal_{n}.npy").exists()
    assert set(t.brats_registro) == {"t1", "t2", "flair"}
    t.rodar_aqui()
    res, versao = FE.rodar_conta(t, BR, None)
    v = res.vols
    voxel_ml = PX * PX * DZ / 1000
    assert v["et"] == pytest.approx((_esfera((20, 24, 30), 8) & ~_esfera((20, 24, 30), 4)).sum() * voxel_ml, rel=0.05)
    assert v["ncr"] > 0 and v["ed"] > v["et"] and v["wt"] == pytest.approx(v["tc"] + v["ed"])
    assert res.diam_et == pytest.approx(16 + PX, abs=2 * PX)
    it = BR.itens_para_o_banco(res, t, versao)
    assert len(it) == 1 and it[0]["tipo"] == BR.TIPO
    f = BR.frase({**it[0], "corrigidos": {}})
    assert f.startswith("Lesão expansiva com componente captante de") and "FLAIR" in f
    out = FE.gravar(t, BR, res, versao, db, paths.storage, repo, None)
    assert BR.ja_feita(repo, study) and out["achados"]
    t.limpar()


def test_brats_falta_sequencia(env, tmp_path):
    from ipe.ai import ferramentas as FE
    from ipe.ai import totalseg as TS
    from ipe.imaging.series import FrameCache
    paths, db, repo = env
    study, uid = _cranio(tmp_path, env, sem=("flair",))
    assert BR.escolher_serie(repo, study)[0] is None
    t = TS.Trabalho(repo, FrameCache(64), None, study, uid, simular=True)
    FE.preparar_trabalho(t, BR)
    with pytest.raises(TS.Falhou, match="FLAIR"):
        t.preparar()


def test_botoes_na_tela(env, tmp_path):
    study, uid_pet, _pet = _pet_ct(tmp_path, env)
    app, w = _janela(env)
    try:
        assert w.handle_external({"accession": "AP01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        for a in ("autopet.auto", "brats.auto", "figado_lesoes.auto"):
            assert a in tab.actions_by_id
        assert hasattr(w, "instalar_modelos_extras")
    finally:
        w.close()
