"""0.100.7: o fibroglandular e o realce de fundo de um exame — a escolha da série pelo protocolo do serviço, o T1 sem
saturação medido, a máscara levada para a grade da dinâmica (outra resolução) e a SEG gravada (e trocada)."""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from pydicom.uid import generate_uid

sys.path.insert(0, str(Path(__file__).parent))
from test_mama_fgt import VOX, _fantoma, _verdade  # noqa: E402

from ipe.imaging import mama_fgt as F  # noqa: E402
from ipe.imaging import mama_fgt_exame as FE  # noqa: E402


def _s(desc, n=40):
    return SimpleNamespace(series_uid=desc, description=desc, modality="MR", num_images=n)


def test_escolhe_a_serie_pelo_protocolo():
    # o protocolo do serviço: VIBRANT 1+3 com saturação, fases Ph1..., e o T1 axial sem saturação
    e = FE.escolher_series([_s("VIBRANT 1+3", 200), _s("Ph1/VIBRANT 1+3"), _s("Sag T1 FS"), _s("Ax T2 FS"),
                            _s("A T1"), _s("Sag T1"), _s("MIP Ph1 (Ipe)")])
    assert e.fonte == F.FONTE_T1 and e.series == ["A T1"]
    assert FE.escolher_series([_s("Ax T1 FSE")]).series == ["Ax T1 FSE"]
    d = FE.escolher_series([_s("VIBRANT 1+3"), _s("FAT: VIBRANT FLEX 1+3"), _s("WATER: VIBRANT FLEX 1+3"),
                            _s("Ax T1 FS")])
    assert d.fonte == F.FONTE_DIXON and d.series == ["FAT: VIBRANT FLEX 1+3", "WATER: VIBRANT FLEX 1+3"]
    assert FE.escolher_series([_s("t1_dixon_F"), _s("t1_dixon_W")]).fonte == F.FONTE_DIXON
    assert FE.escolher_series([_s("VIBRANT 1+3"), _s("Ph1/VIBRANT 1+3")]).fonte == F.FONTE_FS


def _vol(data, dz, dy, dx):
    from ipe.imaging.volume import Volume
    return Volume(data=data, origin=np.zeros(3), row_dir=np.array([1.0, 0, 0]), col_dir=np.array([0, 1.0, 0]),
                  slice_vec=np.array([0, 0, dz]), dx=dx, dy=dy, window=None, source_path="")


@pytest.fixture
def exame(env, tmp_path):
    from test_registro_rigido import _serie
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    vol, gl, mamas, _ = _fantoma(campo=0.2)
    estudo, quadro = generate_uid(), generate_uid()
    _serie(tmp_path / "t1", _vol(vol, *VOX), estudo, quadro, "A T1")
    # a dinâmica: pixel de 2 mm (a máscara tem de ser levada de uma grade à outra), gordura escura (saturada)
    rng = np.random.default_rng(5)
    g2, m2 = gl[:, ::2, ::2], mamas[:, ::2, ::2]
    pre = np.where(g2, 300.0, np.where(m2, 120.0, 0.0)).astype(np.float32)
    pos = pre.copy()
    dire = np.zeros_like(g2)
    dire[:, :, :55] = True                                # a mama direita (colunas baixas; +x é a esquerda)
    sel_d, sel_e = g2 & dire, g2 & ~dire
    pos[sel_d] = pre[sel_d] * 1.6                         # direita realça 60%; esquerda, 5%
    pos[sel_e] = pre[sel_e] * 1.05
    pre += rng.normal(0, 3, pre.shape).astype(np.float32)
    pos += rng.normal(0, 3, pos.shape).astype(np.float32)
    _serie(tmp_path / "d0", _vol(np.clip(pre, 0, None), VOX[0], 2.0, 2.0), estudo, quadro, "VIBRANT 1+3")
    _serie(tmp_path / "d1", _vol(np.clip(pos, 0, None), VOX[0], 2.0, 2.0), estudo, quadro, "Ph1/VIBRANT 1+3")
    Importer(db, paths.storage).import_paths([tmp_path])
    return paths, db, repo, estudo, gl


def _maps(repo, estudo):
    from ipe.imaging.dynamic import DynamicMaps, DynamicSet
    from ipe.imaging.series import FrameCache, build_frames
    ss = sorted([s for s in repo.series_for_study(estudo) if "VIBRANT" in (s.description or "")],
                key=lambda s: s.description.startswith("Ph1"))
    fases = [build_frames(repo.instances_for_series(s.series_uid), s.series_uid) for s in ss]
    return DynamicMaps(DynamicSet(fases, [s.description for s in ss]), FrameCache(64), pre=0, early=1)


def test_mede_no_t1_e_realce_na_dinamica(exame):
    from ipe.imaging.series import FrameCache
    paths, db, repo, estudo, gl = exame
    r, esc, vol, frames = FE.medir(repo, FrameCache(64), estudo, _maps(repo, estudo))
    assert esc.fonte == F.FONTE_T1 and r.serie == "A T1"
    v = _verdade(r, gl)
    lado = {l.nome: l for l in r.lados}
    assert lado["direita"].fgt_pct == pytest.approx(v["direita"], abs=4)
    assert lado["esquerda"].fgt_pct == pytest.approx(v["esquerda"], abs=4)
    # o realce veio da dinâmica, só no FGT, cada lado com o seu
    assert lado["direita"].bpe_realce_mediana == pytest.approx(60, abs=8)
    assert lado["esquerda"].bpe_realce_mediana == pytest.approx(5, abs=5)
    nomes = [n for n, _ in FE.linhas(r)]
    assert "Mama direita" in nomes and "Realce · esquerda" in nomes
    # a SEG é gravada e, na segunda vez, trocada (não duplicada)
    for _ in range(2):
        novas = FE.gravar_seg(r, vol, frames, db, paths.storage, repo, estudo)
        assert len(novas) == 1
    segs = [s for s in repo.series_for_study(estudo) if s.description == FE.DESC_SEG]
    assert len(segs) == 1 and segs[0].modality == "SEG"


def test_sem_t1_usa_a_pre_da_dinamica(exame):
    from ipe.imaging.series import FrameCache
    paths, db, repo, estudo, _gl = exame
    t1 = [s.series_uid for s in repo.series_for_study(estudo) if s.description == "A T1"]
    repo.delete_series(t1[0], Path(paths.storage))
    r, esc, vol, _ = FE.medir(repo, FrameCache(64), estudo, _maps(repo, estudo))
    assert esc.fonte == F.FONTE_FS and vol is None and any("menos confiável" in a for a in r.avisos)
    assert r.total.bpe_realce_mediana is not None
    with pytest.raises(ValueError, match="Abra a dinâmica"):
        FE.medir(repo, FrameCache(64), estudo, None)
