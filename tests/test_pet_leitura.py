"""0.99.88: SUV corrigido pela glicemia, leitura PET (fusão + PET + MIP girando) e ir ao SUV máximo."""
import numpy as np
import pytest

from test_pet_onco import janela  # noqa: F401  (fixture)

from ipe.ai import biometria as B
from ipe.imaging import measure as M
from ipe.imaging import pet_onco as PO
from ipe.imaging.lesions import measure_values


def test_glicemia_conta_e_conferencia():
    assert B._glicemia("110") == 110 and B._glicemia("6,1") == pytest.approx(109.8)   # mmol/L vira mg/dL
    assert B._glicemia(5) == 90 and B._glicemia(900) is None and B._glicemia("x") is None
    assert B.fator_glicemia(150) == 1.5 and B.fator_glicemia(None) is None
    assert PO.conferir_glicemia(None)[0] == "info"
    assert PO.conferir_glicemia(95)[0] == "ok" and "× 0.95" in PO.conferir_glicemia(95)[2]
    assert PO.conferir_glicemia(180)[0] == "info" and PO.conferir_glicemia(230)[0] == "aviso"


def test_glicemia_guardada_no_exame_sem_apagar_altura_e_peso(env):
    _p, _db, repo = env
    B.guardar(repo, "1.2.3", altura_m=1.70, peso_kg=70, sexo="F")
    assert B.guardar_glicemia(repo, "1.2.3", 140) == 140
    lido = B.ler(repo, "1.2.3")
    assert lido["glicemia_mgdl"] == 140 and lido["peso_kg"] == 70
    B.guardar(repo, "1.2.3", altura_m=1.71, peso_kg=71, sexo="F")       # editar o peso não perde a glicemia
    assert B.glicemia(repo, "1.2.3") == 140
    B.guardar_glicemia(repo, "1.2.3", None)
    assert B.glicemia(repo, "1.2.3") is None and B.ler(repo, "1.2.3")["peso_kg"] == 71


def test_suvglic_nas_medidas():
    pix = np.zeros((40, 40), float)
    pix[15:25, 15:25] = 10.0
    pts = [(14.0, 14.0), (26.0, 26.0)]
    v = measure_values("rect", pts, pix, (1.0, 1.0), suv=0.5, glic=1.4)
    assert v["suvmax"] == 5.0 and v["suvgmax"] == pytest.approx(7.0)
    a = M.Annotation(kind="rect", points=pts, frame_key=("x", 0))
    lab = M.labels(a, pix, (1.0, 1.0), "PT", 0.5, 1.4)
    assert any(t.startswith("SUVglic máx 7.00") for t in lab)
    assert not any("SUVglic" in t for t in M.labels(a, pix, (1.0, 1.0), "PT", 0.5))


def test_maximo_perto():
    from types import SimpleNamespace
    data = np.zeros((20, 30, 30), float)
    data[10, 12, 18] = 9.0                       # dentro de 15 mm
    data[10, 12, 29] = 50.0                      # longe: fora da esfera
    vol = SimpleNamespace(data=data, shape=data.shape, dx=1.0, dy=1.0, dz=1.0,
                          patient_to_voxel=lambda p: np.asarray(p, float),
                          voxel_to_patient=lambda i, j, k: np.array([i, j, k], float))
    p = PO.maximo_perto(vol, np.array([15.0, 12.0, 10.0]), 6.0)
    assert list(p) == [18, 12, 10]


def test_leitura_pet_e_glicemia_na_tela(janela):  # noqa: F811
    from ipe.ui.viewer.pet_dialog import PetDialog
    app, w, repo, st = janela
    w.handle_external({"accession": "PET001"})
    tab = w.tabs.currentWidget()
    app.processEvents()
    ct, pt = tab.series_da_leitura_pet()
    assert pt and ct is None                      # este exame só tem o PET
    assert tab.leitura_pet()
    for _ in range(10):
        app.processEvents()
    vps = [v for v in tab._shown() if v.frames]
    assert len(vps) == 2 and getattr(vps[-1], "render3d", None) is not None
    assert vps[-1].render3d.mode == "mip" and vps[-1].render3d.cine_on()
    vps[-1].render3d.cine(False)
    # ir ao máximo: a lesão (40000) está em k=12, linha 20, coluna 30
    v0 = vps[0]
    v0.go_to(12)
    tab.active = v0
    from ipe.imaging.series import build_frames  # noqa: F401
    vol = tab._volume_for(v0, tab._source_series(v0), perguntar=False)
    perto = vol.voxel_to_patient(28, 20, 12)
    for v in tab._shown():
        v.cursor_point = None
    v0.cursor_point = np.asarray(perto, float)
    p = tab.ir_ao_maximo()
    i, j, k = (int(round(x)) for x in vol.patient_to_voxel(p))
    assert (i, j, k) == (30, 20, 12)
    # glicemia na janela PET: SUVglic e Q.Check
    d = PetDialog(tab, None)
    d.glicemia.setValue(160)
    assert B.glicemia(repo, st) == 160 and v0.glic == pytest.approx(1.6)
    assert "160 mg/dL" in d.qc.toPlainText()
    d.close()
