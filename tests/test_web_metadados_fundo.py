"""0.100.83: a preparação de fundo dos metadados não toma a vez da janela, e um elemento inválido não derruba a instância."""
import threading

import pydicom
from pydicom.dataset import FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from ipe.central import web as W


def _arquivo(pasta, n, ruim=False):
    ds = pydicom.Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.SOPInstanceUID = generate_uid()
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    ds.PatientName = "EXEMPLO^FUNDO"
    ds.Rows = ds.Columns = 2
    if ruim:
        from pydicom.dataelem import RawDataElement
        from pydicom.tag import Tag
        # PixelSpacing que não é número (gravado cru, como vem de alguns aparelhos): não vira JSON
        ds._dict[Tag(0x00280030)] = RawDataElement(Tag(0x00280030), "DS", 8, b"abc\\def", 0, False, True)
    c = pasta / f"{n}.dcm"
    ds.save_as(c, enforce_file_format=True)
    return ds.SOPInstanceUID, str(c)


def test_elemento_invalido_fica_de_fora(tmp_path, caplog):
    sop, c = _arquivo(tmp_path, 1, ruim=True)
    d = W._meta_da_instancia(sop, c, "/dicomweb/studies/1/series/2")
    assert d is not None and "00100010" in d and "00280030" not in d
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


def test_em_fundo_le_um_por_vez(tmp_path, monkeypatch):
    itens = dict(_arquivo(tmp_path, i) for i in range(6))
    monkeypatch.setattr(W.CAMINHOS, "da_serie", lambda repo, uid: itens)
    threads, pausas = set(), []
    orig = W._meta_da_instancia

    def conta(*a):
        threads.add(threading.current_thread().name)
        return orig(*a)
    monkeypatch.setattr(W, "_meta_da_instancia", conta)
    monkeypatch.setattr(W.time, "sleep", lambda s: pausas.append(s))
    r = W.metadados_da_serie(None, "1", "2", "/dicomweb", em_fundo=True)
    assert len(r) == 6 and threads == {threading.current_thread().name} and len(pausas) == 6
    threads.clear()
    assert len(W.metadados_da_serie(None, "1", "2", "/dicomweb")) == 6
    assert all(t.startswith("ipe-meta") for t in threads)      # o pedido do navegador continua em paralelo


def test_enfisema_sem_scipy(monkeypatch):
    """0.100.83: o Ipê instalado não traz o scipy; o filtro de ruído do enfisema não pode depender dele."""
    import builtins

    import numpy as np

    from ipe.ai import enfisema as E
    orig = builtins.__import__

    def sem_scipy(nome, *a, **k):
        if nome.startswith("scipy"):
            raise ModuleNotFoundError("No module named 'scipy'")
        return orig(nome, *a, **k)
    monkeypatch.setattr(builtins, "__import__", sem_scipy)

    class V:
        dz, dy, dx = 1.0, 0.7, 0.7
    d = np.random.default_rng(1).normal(-850, 60, (12, 20, 20)).astype(np.float32)
    out = E.reduzir_ruido(d, (2, 10, 3, 17, 3, 17), V())
    assert out[2:10, 3:17, 3:17].std() < d[2:10, 3:17, 3:17].std() * 0.6
    assert np.array_equal(out[0], d[0])
