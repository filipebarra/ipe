"""0.99.84: abrir um exame com SEG de IA — leitura rápida dos quadros, cache entre aberturas, índice por plano."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_estruturas import _volume_do_banco, exame  # noqa: E402,F401  (fixture)

from ipe.imaging import estruturas as ES  # noqa: E402
from ipe.imaging import overlays as O  # noqa: E402


@pytest.fixture
def seg(exame, tmp_path):  # noqa: F811
    from ipe.imaging.seg_writer import build_seg
    _paths, _db, repo, _estudo, serie, _v = exame
    vol, frames = _volume_do_banco(repo, serie)
    g = ES.Grade.do_volume(vol)
    a = ES.Estrutura("Tumor", (255, 80, 80), tipo="lesão")
    ES.pintar(a, g, g.para_mm([32, 32, 10])[0], 7.0)
    b = ES.Estrutura("Fígado", (80, 200, 80), tipo="órgão")
    ES.pintar(b, g, g.para_mm([20, 20, 6])[0], 5.0)
    ds = build_seg(vol, [(SimpleNamespace(mask=e.mascara, offset=e.offset), e.nome, e.cor, e.tipo) for e in (a, b)],
                   vol.source_path, frames)
    p = tmp_path / "seg.dcm"
    ds.save_as(p, enforce_file_format=True)
    O.esquecer_lidos()
    yield ds, p
    O.esquecer_lidos()


def _iguais(xs, ys):
    assert len(xs) == len(ys) > 0
    for x, y in zip(xs, ys):
        assert x.label == y.label and np.array_equal(x.mask, y.mask) and x.spacing == y.spacing and x.ref == y.ref
        assert np.allclose(x.position, y.position) and np.allclose(x.orientation, y.orientation)


@pytest.mark.parametrize("implicito", [False, True])
def test_leitura_rapida_igual_a_do_pydicom(seg, tmp_path, monkeypatch, implicito):
    ds, p = seg
    if implicito:
        import pydicom
        from pydicom.uid import ImplicitVRLittleEndian
        d2 = pydicom.dcmread(p)
        d2.file_meta.TransferSyntaxUID = ImplicitVRLittleEndian
        p = tmp_path / "seg_implicita.dcm"
        d2.save_as(p, implicit_vr=True, little_endian=True)
    import pydicom
    d = pydicom.dcmread(p)
    assert O._por_quadro_rapido(d, int(d.NumberOfFrames)) is not None
    rapido = O._ler_objeto(str(p))
    monkeypatch.setattr(O, "_por_quadro_rapido", lambda ds, n: None)
    lento = O._ler_objeto(str(p))
    _iguais(rapido.masks, lento.masks)


def test_sem_um_atributo_por_quadro_volta_ao_pydicom(seg):
    ds, p = seg
    import pydicom
    d = pydicom.dcmread(p)
    assert O._por_quadro_rapido(d, int(d.NumberOfFrames) + 1) is None      # contagem não bate
    d.PerFrameFunctionalGroupsSequence                                    # já lida: não há bytes crus
    assert O._por_quadro_rapido(d, int(d.NumberOfFrames)) is None


def test_reabrir_usa_o_que_ja_foi_lido(seg, monkeypatch):
    _ds, p = seg
    a = O.load_object(str(p))
    assert O.ja_lido(p)
    lidas = []
    original = O._ler_objeto
    monkeypatch.setattr(O, "_ler_objeto", lambda c: lidas.append(c) or original(c))
    b = O.load_object(str(p))
    assert lidas == [] and a is not b and a.masks is not b.masks
    _iguais(a.masks, b.masks)
    b.enabled = False
    b.masks.clear()
    c = O.load_object(str(p))
    assert c.enabled and len(c.masks) == len(a.masks)     # uma aba não mexe na outra
    st = os.stat(p)
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))      # o arquivo mudou: lê de novo
    assert not O.ja_lido(p)
    O.load_object(str(p))
    assert lidas == [str(p)]


def test_indice_por_plano_igual_a_varrer_tudo(seg):
    _ds, p = seg
    obj = O.load_object(str(p))
    m0 = obj.masks[0]
    n = O._normal(m0.orientation)
    row, col = np.asarray(m0.orientation[:3]), np.asarray(m0.orientation[3:])
    for mf in obj.masks:
        tol = 0.5
        pos = np.asarray(mf.position, float) - 0.2 * n
        perto, outro = O.mascaras_no_plano(obj, pos, n, tol)
        todos = [x for x in obj.masks if O.mask_rect(x, pos, row, col, n, x.spacing, tol, "", 0) is not None]
        assert not outro
        assert [id(x) for x in todos] == [id(x) for x in perto if
                                          O.mask_rect(x, pos, row, col, n, x.spacing, tol, "", 0) is not None]
        assert {id(x) for x in todos} <= {id(x) for x in perto}
    # num plano perpendicular nenhuma máscara entra, e o desenho vai para o volume derivado
    perto, outro = O.mascaras_no_plano(obj, obj.masks[0].position, row, 0.5)
    assert perto == [] and outro
    # sem plano (imagem sem posição): todas, como antes
    assert len(O.mascaras_no_plano(obj, None, None, 0.5)[0]) == len(obj.masks)
