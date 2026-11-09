"""0.99.96: cópia de envio do visualizador web — HTJ2K (ou JPEG-LS) sem perda, conferida, em cache; o arquivo
guardado não muda."""
from pathlib import Path

import numpy as np
import pydicom
import pytest

from ipe.central import envio
from ipe.central import web as WEB


def _arquivo(tmp_path, arr, signed, nome="a.dcm", jpegls=False, rgb=False):
    from pydicom.uid import generate_uid

    from ipe.core.sample_data import _base, _mono
    pat = {"name": "E^E", "id": "E1", "birth": "19700101", "sex": "F"}
    st = {"uid": generate_uid(), "date": "20261108", "accession": "E1", "description": "X", "for": generate_uid()}
    se = {"uid": generate_uid(), "number": 1, "description": "X"}
    ds = _base("1.2.840.10008.5.1.4.1.1.2", pat, st, se, "CT")
    _mono(ds, arr, signed=signed)
    if rgb:
        ds.SamplesPerPixel, ds.PhotometricInterpretation, ds.PlanarConfiguration = 3, "RGB", 0
        ds.BitsAllocated = ds.BitsStored = 8
        ds.HighBit, ds.PixelRepresentation = 7, 0
        ds.PixelData = np.repeat(arr.astype(np.uint8)[..., None], 3, axis=2).tobytes()
    if jpegls:
        ds.compress("1.2.840.10008.1.2.4.80", encoding_plugin="pyjpegls")
    p = tmp_path / nome
    ds.save_as(p, enforce_file_format=True)
    return str(p)


@pytest.fixture()
def cache(tmp_path):
    envio.configurar(tmp_path / "acervo" / "Storage")
    yield tmp_path / "acervo" / "CacheWeb"
    envio._pasta = None


@pytest.mark.parametrize("dtype,signed", [(np.int16, True), (np.uint16, False), (np.uint8, False)])
def test_htj2k_sem_perda_e_em_cache(tmp_path, cache, dtype, signed):
    rng = np.random.default_rng(1)
    lo, hi = (-1024, 3000) if signed else (0, 250 if dtype == np.uint8 else 4000)
    arr = rng.integers(lo, hi, (64, 80)).astype(dtype)
    p = _arquivo(tmp_path, arr, signed)
    antes = Path(p).read_bytes()
    [(dados, ts)] = WEB.quadros_para_web(p, [1])
    import imagecodecs
    assert ts == envio.HTJ2K_RPCL
    assert np.array_equal(np.asarray(imagecodecs.htj2k_decode(dados)).reshape(arr.shape).astype(dtype), arr)
    assert len(list(cache.rglob("*.jph"))) == 1                                # ficou no cache
    assert Path(p).read_bytes() == antes                                       # o arquivo guardado não mudou
    # a segunda vez vem do cache, igual
    assert WEB.quadros_para_web(p, [1]) == [(dados, ts)]


def test_jpegls_guardado_vira_htj2k(tmp_path, cache):
    arr = (np.arange(64 * 64).reshape(64, 64) % 3000).astype(np.uint16)
    p = _arquivo(tmp_path, arr, False, jpegls=True)
    assert str(pydicom.dcmread(p).file_meta.TransferSyntaxUID) == envio.JPEG_LS
    [(dados, ts)] = WEB.quadros_para_web(p, [1])
    import imagecodecs
    assert ts == envio.HTJ2K_RPCL and np.array_equal(imagecodecs.htj2k_decode(dados).reshape(arr.shape), arr)


def test_sem_htj2k_vai_jpegls_e_sem_codificador_vai_o_original(tmp_path, cache, monkeypatch):
    arr = (np.arange(48 * 48).reshape(48, 48) % 900 - 200).astype(np.int16)
    p = _arquivo(tmp_path, arr, True)
    monkeypatch.setattr(envio, "codec", lambda: "jpegls")
    [(dados, ts)] = WEB.quadros_para_web(p, [1])
    import jpeg_ls
    assert ts == envio.JPEG_LS
    assert np.array_equal(np.asarray(jpeg_ls.decode(np.frombuffer(dados, np.uint8))).view(np.int16), arr)
    monkeypatch.setattr(envio, "codec", lambda: "")
    p2 = _arquivo(tmp_path, arr, True, nome="b.dcm")
    [(dados, ts)] = WEB.quadros_para_web(p2, [1])
    assert ts == "1.2.840.10008.1.2.1" and dados == pydicom.dcmread(p2).PixelData


def test_volta_que_nao_bate_manda_o_original(tmp_path, cache, monkeypatch):
    import imagecodecs
    arr = (np.arange(32 * 32).reshape(32, 32)).astype(np.uint16)
    p = _arquivo(tmp_path, arr, False)
    monkeypatch.setattr(imagecodecs, "htj2k_decode", lambda b: np.zeros((32, 32), np.uint16))
    [(dados, ts)] = WEB.quadros_para_web(p, [1])
    assert ts == "1.2.840.10008.1.2.1" and dados == pydicom.dcmread(p).PixelData
    assert list(cache.rglob("*.nao"))                       # lembra que não deu (não tenta de novo a cada pedido)


def test_cor_vai_como_esta(tmp_path, cache):
    arr = (np.arange(16 * 16).reshape(16, 16) % 200).astype(np.uint8)
    p = _arquivo(tmp_path, arr, False, rgb=True)
    [(dados, ts)] = WEB.quadros_para_web(p, [1])
    assert ts == "1.2.840.10008.1.2.1" and len(dados) == 16 * 16 * 3


def test_preparar_serie_em_segundo_plano(tmp_path, cache):
    import time
    ps = [_arquivo(tmp_path, (np.arange(32 * 32).reshape(32, 32) + k).astype(np.uint16), False, nome=f"{k}.dcm")
          for k in range(5)]
    envio.preparar_serie(ps)
    fim = time.time() + 20
    while time.time() < fim and len(list(cache.rglob("*.jph"))) < 5:
        time.sleep(0.1)
    assert len(list(cache.rglob("*.jph"))) == 5


def test_fundo_espera_os_quadros_pedidos(tmp_path, cache):
    """0.99.99: um trabalhador só, e ele espera enquanto o navegador está pedindo quadros."""
    import threading
    import time
    ps = [_arquivo(tmp_path, (np.arange(32 * 32).reshape(32, 32) + k).astype(np.uint16), False, nome=f"e{k}.dcm")
          for k in range(4)]
    with envio.atendendo():
        envio.preparar_serie(ps[:2])
        envio.preparar_serie(ps[2:])
        time.sleep(0.8)
        assert len(list(cache.rglob("*.jph"))) == 0           # parado: há um pedido de quadro em andamento
        assert len([t for t in threading.enumerate() if t.name == "ipe-envio"]) == 1
    fim = time.time() + 20
    while time.time() < fim and len(list(cache.rglob("*.jph"))) < 4:
        time.sleep(0.1)
    assert len(list(cache.rglob("*.jph"))) == 4               # as duas séries, em fila, depois do pedido


def test_arquivo_inteiro_em_htj2k_para_o_cliente(tmp_path, cache):
    """0.100.0: o arquivo vai ao cliente com os pixels em HTJ2K sem perda; o programa lê a mesma imagem
    (pelo caminho rápido do imagecodecs), com o sinal certo, e o acervo não muda."""
    import pydicom

    from ipe.imaging.series import Frame, read_frame
    for sinal in (True, False):
        arr = (np.random.default_rng(1).normal(0 if sinal else 1500, 300, (64, 48))).astype(np.int16 if sinal else np.uint16)
        p = _arquivo(tmp_path, arr, sinal, nome=f"arq{sinal}.dcm")
        antes = Path(p).read_bytes()
        q = envio.arquivo_para_rede(p)
        assert q != p and Path(p).read_bytes() == antes
        ds = pydicom.dcmread(q)
        assert str(ds.file_meta.TransferSyntaxUID) == envio.HTJ2K_RPCL
        assert ds.SOPInstanceUID == pydicom.dcmread(p).SOPInstanceUID
        assert np.array_equal(ds.pixel_array, arr)
        a = read_frame(Frame(path=q, frame_index=0, sop_uid=ds.SOPInstanceUID, instance_number=1, position=None,
                             orientation=None))
        b = read_frame(Frame(path=p, frame_index=0, sop_uid=ds.SOPInstanceUID, instance_number=1, position=None,
                             orientation=None))
        assert np.array_equal(a.pixels, b.pixels)
        assert envio.arquivo_para_rede(p) == q                 # a segunda vez: do cache


def test_arquivo_ja_comprimido_vai_como_esta(tmp_path, cache):
    arr = (np.arange(16 * 16).reshape(16, 16) % 200).astype(np.uint8)
    p = _arquivo(tmp_path, arr, False, rgb=True, nome="cor.dcm")
    assert envio.arquivo_para_rede(p) == p
