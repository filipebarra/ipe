"""0.100.0: o programa ligado ao servidor central recebe os pixels em HTJ2K sem perda (menos bytes na rede), o
acervo do servidor não muda, e o que chega é a mesma imagem. Quem já está pronto vai comprimido; o que não está
vai como está (sem esperar) e fica pronto para a próxima vez."""
import threading

import numpy as np
import pydicom

from test_central import central  # noqa: F401  (fixture)
from test_central_progressivo import _cliente
from ipe.central import envio
from ipe.imaging.series import build_frames, read_frame


def _iguais(cr, repo, uid):
    for s in repo.series_for_study(uid):
        loc = {f.sop_uid: f for f in build_frames(cr.local.instances_for_series(s.series_uid), s.series_uid)}
        for f in build_frames(repo.instances_for_series(s.series_uid), s.series_uid):
            a, b = read_frame(f), read_frame(loc[f.sop_uid])
            assert np.array_equal(a.pixels, b.pixels) and a.is_color == b.is_color


def test_cliente_recebe_htj2k_e_a_mesma_imagem(central, tmp_path):  # noqa: F811
    paths, db, repo, srv = central
    uid = repo.find_study_uids(accession="ACC1001")[0]
    originais = {f: open(f, "rb").read() for f in repo.files_for_study(uid)}
    for f in originais:                                    # as cópias prontas (o que a varredura faz)
        envio.arquivo_para_rede(f)
    cr, *_ = _cliente(srv, paths, tmp_path)
    assert cr.rede_htj2k()
    n = cr.download(uid, primeiro_lote=threading.Event())
    assert n == len(originais)
    ts = {str(pydicom.dcmread(f, stop_before_pixels=True).file_meta.TransferSyntaxUID)
          for f in cr.local.files_for_study(uid)}
    assert envio.HTJ2K_RPCL in ts
    assert all(open(f, "rb").read() == b for f, b in originais.items())   # o acervo não mudou
    _iguais(cr, repo, uid)


def test_sem_copia_pronta_vai_o_original_e_desligado_tambem(central, tmp_path):  # noqa: F811
    paths, db, repo, srv = central
    uid = repo.find_study_uids(accession="ACC1001")[0]
    cr, *_ = _cliente(srv, paths, tmp_path)
    cr.settings.set("central.rede_htj2k", False)
    cr.download(uid, primeiro_lote=threading.Event())
    ts = {str(pydicom.dcmread(f, stop_before_pixels=True).file_meta.TransferSyntaxUID)
          for f in cr.local.files_for_study(uid)}
    assert envio.HTJ2K_RPCL not in ts
    _iguais(cr, repo, uid)


def test_varredura_dos_recentes(central):  # noqa: F811
    import time
    paths, db, repo, srv = central
    assert envio.varrer_recentes(repo, 36500) >= 1
    fim = time.time() + 60
    while time.time() < fim and not all(envio.pronto_para_rede(f) for f in repo.files_for_study(
            repo.find_study_uids(accession="ACC1001")[0])):
        time.sleep(0.2)
    assert all(envio.pronto_para_rede(f) for f in repo.files_for_study(repo.find_study_uids(accession="ACC1001")[0]))
    assert envio.varrer_recentes(repo, 0) == 0


def test_enviar_htj2k_a_no_que_so_aceita_sem_compressao(tmp_path, sample_dir):
    """Um arquivo do cache do cliente (HTJ2K) mandado a um nó antigo que só aceita sem compressão vai
    descomprimido (a mesma imagem)."""
    import socket

    from pynetdicom import AE, evt
    from pynetdicom.sop_class import CTImageStorage
    from pydicom.uid import ExplicitVRLittleEndian, ImplicitVRLittleEndian

    from ipe.network.client import DicomClient, Target
    envio.configurar(tmp_path / "acervo" / "Storage")
    try:
        fonte = next(p for p in sorted(sample_dir.rglob("*")) if p.is_file()
                     and pydicom.dcmread(p, stop_before_pixels=True, force=True).get("Modality") == "CT")
        q = envio.arquivo_para_rede(str(fonte))
        assert q != str(fonte)
        recebidos = []

        def guardar(event):
            ds = event.dataset
            ds.file_meta = event.file_meta
            recebidos.append(ds)
            return 0x0000
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            porta = s.getsockname()[1]
        ae = AE("VELHO")
        ae.add_supported_context(CTImageStorage, [ImplicitVRLittleEndian, ExplicitVRLittleEndian])
        scp = ae.start_server(("127.0.0.1", porta), block=False, evt_handlers=[(evt.EVT_C_STORE, guardar)])
        try:
            no = {"name": "VELHO", "ae_title": "VELHO", "host": "127.0.0.1", "port": porta}
            enviados, falhas = DicomClient(timeout=10).store(Target.build(no, "IPE"), [q])
        finally:
            scp.shutdown()
        assert (enviados, falhas) == (1, 0)
        assert np.array_equal(recebidos[0].pixel_array, pydicom.dcmread(fonte).pixel_array)
    finally:
        envio._pasta = None
