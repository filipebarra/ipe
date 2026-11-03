"""0.99.39 (plano AW M3): correção de movimento rígida da dinâmica — rotação além da translação."""
import numpy as np
from PySide6.QtWidgets import QApplication

from ipe.imaging import registro_rigido as RR
from ipe.imaging.dynamic import LIMIAR_ROTACAO, DynamicMaps, DynamicSet
from ipe.imaging.series import FrameCache, build_frames
from ipe.imaging.volume import Volume
from ipe.importer.scanner import Importer

NZ, NY, NX, DZ, DXY = 24, 80, 80, 2.0, 1.5


def _textura():
    rng = np.random.default_rng(7)
    v = rng.random((NZ, NY, NX))
    for _ in range(4):
        v = (v + np.roll(v, 1, 0) + np.roll(v, 1, 1) + np.roll(v, 1, 2)
             + np.roll(v, -1, 1) + np.roll(v, -1, 2)) / 6
    v = (v - v.min()) / (v.max() - v.min())
    z, y, x = np.mgrid[0:NZ, 0:NY, 0:NX]
    corpo = ((x - NX / 2) / 34) ** 2 + ((y - NY / 2) / 34) ** 2 + ((z - NZ / 2) / 14) ** 2 < 1
    return np.where(corpo, v * 400 + 100, 0.0).astype(np.float32)


def _girar(dados, params):
    A = Volume(dados, np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, DZ]),
               DXY, DXY, None, "")
    M = RR.matriz(params, RR._cantos(A).mean(0))
    K, J, I = np.mgrid[0:NZ, 0:NY, 0:NX]
    pts = np.stack([I.ravel(), J.ravel(), K.ravel()], 1) @ A.matrix().T
    return np.nan_to_num(RR.amostrar(A, RR.aplicar(np.linalg.inv(M), pts), fora=0)).reshape(dados.shape)


def _gravar(pasta, params_movida):
    from pydicom.uid import MRImageStorage, generate_uid
    from ipe.core.sample_data import _base, _mono, _save
    base = _textura()
    girada = _girar(base, params_movida)
    pat = {"name": "ROT^Teste", "id": "ROT1", "birth": "19800101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20260101", "accession": "ROT001", "description": "RM",
             "for": generate_uid()}
    for ph in range(4):
        series = {"uid": generate_uid(), "number": 10 + ph, "description": f"fase {ph}"}
        vol = (girada if ph >= 2 else base) * (1 + 0.1 * ph)
        for k in range(NZ):
            ds = _base(MRImageStorage, pat, study, series, "MR")
            ds.InstanceNumber = k + 1
            ds.ImagePositionPatient = [0.0, 0.0, DZ * k]
            ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
            ds.PixelSpacing = [DXY, DXY]
            ds.AcquisitionTime = f"10{ph:02d}00"
            _mono(ds, vol[k], signed=False)
            _save(ds, pasta / f"p{ph}")
    return study["uid"]


def _dset(env, tmp_path, params):
    paths, db, repo = env
    uid = _gravar(tmp_path / "d", params)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    ss = sorted(repo.series_for_study(uid), key=lambda s: s.series_number)
    phases = [build_frames(repo.instances_for_series(s.series_uid), s.series_uid) for s in ss]
    return DynamicSet(phases, [s.description for s in ss])


def _espalhamento(mp, fase, esperado):
    """Desvio da razão fase/pré no miolo (deveria ser constante se alinhado)."""
    devs = []
    for k in (8, 12, 16):
        st = mp.stack(k)
        miolo = st[0] > 200
        devs.append(float(np.std(st[fase][miolo] / st[0][miolo] - esperado)))
    return float(np.mean(devs))


def test_rigida_acha_a_rotacao_e_alinha_melhor_que_a_translacao(env, tmp_path):
    dset = _dset(env, tmp_path, (0.0, 0.0, 5.0, 2.0, -3.0, 0.0))
    cache = FrameCache(512)
    so_t = DynamicMaps(dset, cache, motion=True)
    rig = DynamicMaps(dset, cache, motion="rigido")
    assert abs(rig.rotacoes[2] - 5.0) < 0.6 and abs(rig.rotacoes[3] - 5.0) < 0.6
    assert 2 in rig.matrizes and 3 in rig.matrizes and 1 not in rig.matrizes   # a fase 1 não mexeu
    assert rig.motion_corrected and abs(rig.rotacao_maxima - 5.0) < 0.6
    e_rig, e_t = _espalhamento(rig, 3, 1.3), _espalhamento(so_t, 3, 1.3)
    assert e_rig < 0.1 and e_rig < 0.5 * e_t
    # o volume da fase (a anatomia da captura da lesão) também sai girado de volta
    v = rig.volume_da_fase(3)
    assert np.allclose(v.data[12], rig.stack(12)[3])


def test_sem_rotacao_fica_na_translacao(env, tmp_path):
    dset = _dset(env, tmp_path, (0.0, 0.0, 0.0, 3.0, 0.0, 0.0))
    rig = DynamicMaps(dset, FrameCache(512), motion="rigido")
    assert not rig.matrizes and max(rig.rotacoes) < LIMIAR_ROTACAO
    dz, dy, dx = rig.shifts[3]
    assert abs(dx * DXY - 3.0) < 0.5 and abs(dy) < 0.4
    assert rig.rotacao_maxima == 0.0


def test_cancelar_no_rigido_nao_aplica_nada(env, tmp_path):
    dset = _dset(env, tmp_path, (0.0, 0.0, 5.0, 0.0, 0.0, 0.0))
    chamadas = []

    def progresso(feito, total):
        chamadas.append((feito, total))
        return feito < total // 2 + 2      # na 2ª passada (a rígida, total = 2 × fases), depois da 1ª fase
    sem = DynamicMaps(dset, FrameCache(512), motion="rigido")
    assert set(sem.matrizes) == {2, 3}
    mp = DynamicMaps(dset, FrameCache(512), motion="rigido", progress=progresso)
    assert not mp.matrizes and not mp.motion_corrected
    assert any(t == 2 * len(dset.phases) for _f, t in chamadas)


def test_janela_e_configuracao_levam_a_opcao(env):
    from ipe.ui.viewer import dinamica_config as DC
    QApplication.instance() or QApplication([])
    assert DC.PARAMETROS_FABRICA["motion_rigido"] is False
    from ipe.core.config import Settings
    from ipe.ui.viewer.dinamica_editor import DinamicaMamaEditor
    paths, _db, _repo = env
    ed = DinamicaMamaEditor(Settings(paths.settings_file))
    ed.c_origem.setCurrentIndex(max(0, ed.c_origem.findData("padrao")))
    ed.c_motion.setChecked(False)
    assert not ed.c_rigido.isEnabled()
    ed.c_motion.setChecked(True)
    ed.c_rigido.setChecked(True)
    assert ed.c_rigido.isEnabled() and ed.parametros()["motion_rigido"] is True
    ed.c_motion.setChecked(False)
    assert ed.parametros()["motion_rigido"] is False
