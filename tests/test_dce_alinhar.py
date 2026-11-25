"""0.100.119: Dinâmica da mama — alinhar as fases (elastix, ambiente próprio) e gravar séries novas.

O ambiente do elastix (`venv_dce`) é pesado e não existe em toda máquina: os testes que o usam rodam com o Python
indicado em `IPE_DCE_PYTHON` e são pulados sem ele. O resto (nomes, regras, gravação dos DICOMs) roda sempre."""
import os
from pathlib import Path

import numpy as np
import pydicom
import pytest
from pydicom.uid import MRImageStorage, generate_uid

from ipe.ai import dce_alinhar as DCE
from ipe.core.config import Settings
from ipe.core.sample_data import _base, _mono, _save
from ipe.importer.scanner import Importer

PY = os.environ.get("IPE_DCE_PYTHON", "")
precisa_elastix = pytest.mark.skipif(not (PY and Path(PY).is_file()), reason="sem o ambiente do elastix (IPE_DCE_PYTHON)")


def _exame(pasta, deslocamentos=((0, 0), (3, 2), (5, -3), (2, 4)), cortes=12, n=96):
    """RM dinâmica sintética: textura fixa + um 'seio' + uma lesão que realça; cada fase deslocada no plano."""
    from scipy.ndimage import gaussian_filter, shift
    rng = np.random.default_rng(1)
    base = gaussian_filter(rng.random((cortes, n, n)).astype(np.float32), 2) * 100 + 20
    zz, yy, xx = np.mgrid[:cortes, :n, :n]
    base += 300 * (((zz - cortes / 2) ** 2 / 30 + (yy - n / 2) ** 2 / 500 + (xx - n / 2) ** 2 / 500) < 1)
    lesao = ((zz - cortes / 2) ** 2 + (yy - n / 2 - 4) ** 2 + (xx - n / 2 + 8) ** 2) < 16
    pat = {"name": "ALINHA^Teste", "id": "DCE1", "birth": "19800101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20260101", "accession": "DCE001",
             "description": "RM MAMAS COM CONTRASTE", "for": generate_uid()}
    for ph, (dy, dx) in enumerate(deslocamentos):
        serie = {"uid": generate_uid(), "number": 10 + ph, "description": f"DYN fase {ph}"}
        vol = base + (250 * ph / 3 * lesao if ph else 0)
        vol = shift(vol, (0, dy, dx), order=1) + rng.normal(0, 2, vol.shape)
        for k in range(cortes):
            ds = _base(MRImageStorage, pat, study, serie, "MR")
            ds.InstanceNumber = ph * cortes + k + 1
            ds.ImagePositionPatient = [-60.0, -60.0, 3.0 * k]
            ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
            ds.PixelSpacing = [1.4, 1.4]
            ds.SliceThickness = 3.0
            ds.AcquisitionTime = f"10{ph:02d}00"
            _mono(ds, np.clip(vol[k], 0, 4000), signed=False)
            _save(ds, pasta / f"dyn_{ph}")
    return study["uid"]


def test_nomes_e_marcas():
    from ipe.ai import series_ia as SI
    assert DCE.e_nossa(DCE.DESC_FASE.format(1)) and DCE.e_nossa(DCE.DESC_SUB.format(2))
    assert not DCE.e_nossa("Dinâmica alinhada pela estação") and not DCE.e_nossa("DYN fase 1")
    assert SI.e_resultado("MR", DCE.DESC_FASE.format(1))                  # o selo "IA" nas miniaturas
    assert DCE.config(None, DCE.CHAVE_AUTO) is False and DCE.config(None, DCE.CHAVE_MIN_PCT) == 12.0
    assert DCE.exame_serve({"modalities": "MR"}) and not DCE.exame_serve({"modalities": "MG"})


def test_sem_o_ambiente_diz_o_que_falta(env, tmp_path, monkeypatch):
    paths, db, repo = env
    monkeypatch.delenv("IPE_DCE_PYTHON", raising=False)
    monkeypatch.setattr(DCE, "python_do_ambiente", lambda: None)
    uid = _exame(tmp_path / "d")
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    serie, motivo = DCE.escolher_serie(repo, uid)
    assert serie is None and "elastix" in motivo
    with pytest.raises(RuntimeError):
        DCE.processar(repo, db, paths.storage, uid)


def test_datasets_mesma_geometria_e_marca(env, tmp_path):
    paths, db, repo = env
    uid = _exame(tmp_path / "d", cortes=4, n=32)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    fases = DCE.fases_do_exame(repo, uid)
    assert len(fases) == 4
    vol, esp = DCE.ler_fase(fases[1][1])
    assert vol.shape == (4, 32, 32) and esp == pytest.approx((1.4, 1.4, 3.0))
    sub = np.clip(vol - DCE.ler_fase(fases[0][1])[0], 0, None)
    dss = list(DCE.datasets_da_serie(fases[1][1], sub, DCE.DESC_SUB.format(1), 8101, generate_uid(), "0.0", subtracao=True))
    assert len(dss) == 4
    ds = dss[0]
    assert "SUBTRACT" in ds.ImageType and "SECONDARY" in ds.ImageType and ds.SeriesDescription.endswith("· Ipê")
    orig = pydicom.dcmread(fases[1][1][0].path)
    assert list(ds.ImagePositionPatient) == list(orig.ImagePositionPatient) and ds.Rows == 32
    assert ds.SOPInstanceUID != orig.SOPInstanceUID and ds.StudyInstanceUID == orig.StudyInstanceUID
    # e a detecção da dinâmica do visualizador não as toma por fases
    from ipe.imaging import phases as P
    assert P.fora_das_fases([str(x) for x in ds.ImageType])


@precisa_elastix
def test_de_ponta_a_ponta_com_o_elastix(env, tmp_path, monkeypatch):
    paths, db, repo = env
    monkeypatch.setenv("IPE_DCE_PYTHON", PY)
    uid = _exame(tmp_path / "d")
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    etapas = []
    res = DCE.processar(repo, db, paths.storage, uid, Settings(paths.settings_file), progresso=etapas.append)
    assert not res["sem_movimento"] and res["movimento_pct"] > 12, res
    assert res["geradas"] == 4 + 3 and any("registro conjunto" in e for e in etapas)
    descs = sorted(s.description for s in repo.series_for_study(uid) if DCE.e_nossa(s.description))
    assert descs == ["Dinâmica alinhada 1 · Ipê", "Dinâmica alinhada 2 · Ipê", "Dinâmica alinhada 3 · Ipê",
                     "Dinâmica alinhada 4 · Ipê", "Subtração alinhada 1 · Ipê", "Subtração alinhada 2 · Ipê",
                     "Subtração alinhada 3 · Ipê"]
    assert DCE.ja_feita(repo, uid)
    # a dinâmica das originais segue sendo a mesma: 4 fases (as derivadas não entram)
    assert len(DCE.fases_do_exame(repo, uid)) == 4
    # o desalinhamento caiu: pré × fase 3 (a que mais se mexeu)
    ser = {s.description: s.series_uid for s in repo.series_for_study(uid)}
    from ipe.imaging.series import build_frames
    def vol(desc):
        q = build_frames(repo.instances_for_series(ser[desc]), ser[desc])
        return DCE.ler_fase(q)[0]
    orig = [DCE.ler_fase(q)[0] for _u, q in DCE.fases_do_exame(repo, uid)]
    novo = [vol(DCE.DESC_FASE.format(k)) for k in (1, 3)]
    assert np.abs(novo[1] - novo[0]).mean() < 0.8 * np.abs(orig[2] - orig[0]).mean()
    # refazer (à mão) troca as séries, não duplica
    res2 = DCE.processar(repo, db, paths.storage, uid, forcar=True)
    assert len([s for s in repo.series_for_study(uid) if DCE.e_nossa(s.description)]) == 7
    # já tem e não é à mão: não refaz
    assert "já tem" in DCE.processar(repo, db, paths.storage, uid)["aviso"]
    assert res2["geradas"] == 7


@precisa_elastix
def test_porta_do_movimento_nao_grava_nada(env, tmp_path, monkeypatch):
    paths, db, repo = env
    monkeypatch.setenv("IPE_DCE_PYTHON", PY)
    uid = _exame(tmp_path / "d", deslocamentos=((0, 0),) * 4)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    antes = len(repo.series_for_study(uid))
    res = DCE.processar(repo, db, paths.storage, uid)
    assert res["sem_movimento"] and res["geradas"] == 0 and "sem movimento" in DCE.resumo(res)
    assert len(repo.series_for_study(uid)) == antes
