"""0.100.60: a tomossíntese (multiframe JPEG-LS) abre pelo caminho rápido — cabeçalho e lugar dos quadros lidos uma
vez por arquivo, decodificação sem a trava do Python — e a fila automática da mama não quebra a conta das
calcificações (o `stop` era um Event e a rede esperava uma função)."""
import threading

import numpy as np
import pytest
from pydicom.uid import JPEGLSLossless, generate_uid


def _tomo(tmp_path, n=7, com_sinal=False):
    from ipe.core.sample_data import _base, _mono, tomo_geometry
    pat = {"name": "TOMO^Rapida", "id": "TR1", "birth": "19700101", "sex": "F"}
    st = {"uid": generate_uid(), "date": "20261116", "accession": "TR1", "description": "MAMOGRAFIA", "for": generate_uid()}
    ds = _base("1.2.840.10008.5.1.4.1.1.13.1.3", pat, st, {"uid": generate_uid(), "number": 2, "description": "TOMO"}, "MG")
    ds.InstanceNumber, ds.ImageLaterality, ds.ViewPosition = 1, "R", "CC"
    ds.PixelSpacing = [0.1, 0.1]
    rng = np.random.default_rng(1)
    vol = (rng.integers(0, 4000, (n, 96, 64)) + np.arange(n)[:, None, None] * 10).astype(np.uint16)
    _mono(ds, vol[0], signed=False)
    ds.BitsStored = 12
    ds.HighBit = 11
    if com_sinal:
        ds.PixelRepresentation = 1
    ds.NumberOfFrames = n
    ds.PixelData = vol.tobytes()
    tomo_geometry(ds, n)
    ds.compress(JPEGLSLossless)
    p = tmp_path / f"tomo{int(com_sinal)}.dcm"
    ds.save_as(p)
    return p, vol


def test_tomo_jpegls_pelo_caminho_rapido(tmp_path, monkeypatch):
    pytest.importorskip("imagecodecs")
    import pydicom

    from ipe.imaging import series as S
    p, vol = _tomo(tmp_path)
    S._MULTI.clear()
    ds, onde = S._indice_multiframe(str(p))
    assert onde is not None and len(onde) == 7 and int(ds.NumberOfFrames) == 7 and "PixelData" not in ds
    # igual ao pydicom, quadro a quadro; o cabeçalho é lido uma vez só
    leituras = []
    real = pydicom.dcmread
    monkeypatch.setattr(S.pydicom, "dcmread", lambda *a, **k: leituras.append(1) or real(*a, **k))
    for k in (0, 3, 6):
        d2, arr = S._quadro_jpegls_rapido(str(p), k)
        assert d2 is ds and arr is not None and arr.dtype == np.uint16
        assert np.array_equal(arr, vol[k])
    assert not leituras
    assert S._quadro_jpegls_rapido(str(p), 7)[1] is None            # fora do arquivo: caminho de sempre
    # o read_frame usa esse caminho (sem o pydicom decodificar)
    from pydicom import pixels as PX
    monkeypatch.setattr(PX, "pixel_array", lambda *a, **k: (_ for _ in ()).throw(AssertionError("caminho lento")))
    fr = S.build_frames([{"path": str(p), "sop_uid": "1.2.3", "frames": 7, "instance_number": 1}])
    img = S.read_frame(next(f for f in fr if f.frame_index == 3))
    assert np.array_equal(np.asarray(img.pixels), vol[3].astype(np.float32))
    # arquivo regravado (outro tamanho/data): o índice é refeito
    p2, vol2 = _tomo(tmp_path, n=5)
    assert len(S._indice_multiframe(str(p2))[1]) == 5


def test_tomo_com_sinal_em_12_bits_vai_pelo_pydicom(tmp_path):
    pytest.importorskip("imagecodecs")
    from ipe.imaging import series as S
    p, _vol = _tomo(tmp_path, com_sinal=True)
    ds, arr = S._quadro_jpegls_rapido(str(p), 1)
    assert ds is not None and arr is None


def test_calcificacao_aceita_event_como_stop(monkeypatch):
    from ipe.ai import calc_vascular as C

    class Rede:
        def run(self, _saidas, entradas):
            x = entradas["imagem"]
            return [np.zeros((x.shape[0], 1, x.shape[2], x.shape[3]), np.float32)]
    monkeypatch.setattr(C, "sessao", lambda dados=None: Rede())
    img = np.zeros((C.PEDACO, C.PEDACO), np.uint8)
    ev = threading.Event()
    assert C.mapa(img, None, ev).shape == img.shape               # era: TypeError: 'Event' object is not callable
    assert C.mapa(img, None, lambda: False).shape == img.shape
    ev.set()
    with pytest.raises(InterruptedError):
        C.mapa(img, None, ev)


def test_linha_de_abertura_do_navegador():
    from ipe.central.server import log_abertura_web
    a = log_abertura_web({"tipo": "primeira", "modalidades": "MR\\SR", "series": 14, "versao": "0.100.60", "total": 1.923,
                          "etapas": {"series": 0.21, "exame": 0.05, "imagem": 1.36, "<b>": "x"},
                          "navegador": "Firefox 160", "tela": "1628x1064"})
    assert a == ("Abertura web (MR\\SR, 14 séries): primeira imagem em 1,92 s — series 0,21 · exame 0,05 · imagem 1,36 · "
                 "b ? | Firefox 160 1628x1064 | 0.100.60")
    t = log_abertura_web({"tipo": "tudo", "modalidades": "CT", "series": 3, "total": 12.4, "imagens": 1830, "mb": 85.23,
                          "mb_s": 9.14, "decod_ms": 6.21, "do_cache": 0, "navegador": "Chrome 150", "tela": "1920x1080",
                          "versao": "0.100.60"})
    assert "tudo disponível em 12,40 s — 1830 imagens · 85,2 MB a 9,1 MB/s · decodificação 6,2 ms" in t
    # nada do que o navegador manda vira texto livre no registro
    ruim = log_abertura_web({"modalidades": "MR\n2026 INFO falso: <uid>", "series": "x" and 2, "total": "abc", "navegador": "a\nb"})
    assert "\n" not in ruim and "em ? s" in ruim


def test_sr_da_mama_regravado_pelo_cliente_apaga_no_servidor():
    """O cliente pede ao servidor para apagar as séries "(Ipê)" anteriores (só elas) antes de mandar as novas."""
    from ipe.ai import mama_sr as MS
    from ipe.central.rpc import POR_EXAME, RPC_METHODS
    assert RPC_METHODS["apagar_series_da_mama"] == "view" and "apagar_series_da_mama" in POR_EXAME
    pedidos, apagadas = [], []

    class Serie:
        def __init__(self, uid, desc):
            self.series_uid, self.description = uid, desc

    class Repo:
        def series_for_study(self, uid):
            return [Serie("1", "R CC"), Serie("2", MS.DESC_SR), Serie("3", MS.DESC_RESUMO)]

        def delete_series(self, uid, raiz):
            apagadas.append(uid)

    class Cliente(Repo):
        class client:                                                # noqa: N801
            @staticmethod
            def rpc(metodo, *a):
                pedidos.append((metodo, *a))
    assert MS._apagar_anteriores(Repo(), "9.9", "/tmp") == 2 and apagadas == ["2", "3"] and not pedidos
    assert MS._apagar_anteriores(Cliente(), "9.9", "/tmp") == 2 and pedidos == [("apagar_series_da_mama", "9.9")]

    class Antigo(Repo):                                              # servidor de versão anterior: segue como antes
        class client:                                                # noqa: N801
            @staticmethod
            def rpc(metodo, *a):
                raise RuntimeError("método desconhecido")
    assert MS._apagar_anteriores(Antigo(), "9.9", "/tmp") == 2


def test_abertura_do_cliente_vai_para_o_registro_do_servidor(monkeypatch):
    """0.100.61: no modo cliente, a linha "Abertura (…)" do Ipê de mesa também é mandada ao servidor."""
    import logging
    import time

    from ipe.central.server import log_abertura_cliente
    from ipe.core import cronometro as CR
    a = log_abertura_cliente("Abertura (MG MAMOGRAFIA DIGITAL): primeira imagem em 2,90 s — servidor 0,63 · banco 0,08",
                             "dra.ana", "192.168.1.20", "0.100.61")
    assert a == ("Abertura cliente (MG MAMOGRAFIA DIGITAL): primeira imagem em 2,90 s — servidor 0,63 · banco 0,08"
                 " | dra.ana@192.168.1.20 | 0.100.61")
    assert log_abertura_cliente("2026 INFO falso", "x", "y", "z") == ""                  # só a linha da abertura
    assert "\n" not in log_abertura_cliente("Abertura (CT): a\nb", "u\nv", "h", "1")
    # o cronômetro manda a primeira imagem e o que chega depois; sem servidor (ou com erro), só o registro local
    mandadas = []
    monkeypatch.setattr(CR, "enviar", mandadas.append)
    c = CR.iniciar("CT TORAX")
    c.marca("servidor")
    CR.primeira_imagem()
    CR.depois("download", 1.5)
    fim = time.time() + 3
    while len(mandadas) < 2 and time.time() < fim:
        time.sleep(0.02)
    assert len(mandadas) == 2 and mandadas[0].startswith("Abertura (CT TORAX): primeira imagem em ")
    assert "download pronto em " in mandadas[1]
    monkeypatch.setattr(CR, "enviar", lambda t: (_ for _ in ()).throw(RuntimeError("servidor antigo")))
    CR.iniciar("CT")
    CR.primeira_imagem()
    monkeypatch.setattr(CR, "enviar", None)
    CR.iniciar("CT")
    CR.primeira_imagem()
    assert logging.getLogger("ipe.abertura") is CR.log


def test_rpc_da_abertura_do_cliente(env):
    import logging

    from ipe.auth.session import UserSession
    from ipe.central.rpc import RPC_METHODS
    from ipe.central.server import CentralServer
    assert RPC_METHODS["abertura_cliente"] == ""
    linhas = []

    class H(logging.Handler):
        def emit(self, rec):
            linhas.append(rec.getMessage())
    h = H()
    reg = logging.getLogger("ipe.abertura")
    nivel = reg.level
    reg.addHandler(h)
    reg.setLevel(logging.INFO)
    try:
        s = UserSession.__new__(UserSession)
        s.username, s.perms, s.role, s.user_id, s.full_name = "dr.teste", set(), "medico", 0, ""
        CentralServer.rpc(CentralServer.__new__(CentralServer), s, "abertura_cliente",
                          ["Abertura (MR CRANIO): primeira imagem em 1,10 s — servidor 0,40", "0.100.61"], {}, "10.0.0.7")
    finally:
        reg.removeHandler(h)
        reg.setLevel(nivel)
    assert linhas == ["Abertura cliente (MR CRANIO): primeira imagem em 1,10 s — servidor 0,40 | dr.teste@10.0.0.7 | 0.100.61"]
