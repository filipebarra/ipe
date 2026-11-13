"""0.100.38: abrir e baixar mais rápido — o que mudou no servidor central (conexões abertas, sem Nagle, permissões e
"quem vê" guardados por segundos, quadros direto das cópias prontas, metadados em disco) e na leitura das imagens
(JPEG-LS em paralelo, regiões conectadas rápidas). Cada atalho tem que dar o mesmo resultado do caminho de sempre."""
import http.client
import json

import numpy as np
import pytest
from pydicom.uid import JPEGLSLossless, generate_uid

from test_central import central  # noqa: F401  (fixture)
from ipe.central.remote import RemoteClient, RemoteError


# ---------------------------------------------------------------------------------------------- servidor
def _http(srv, tok=None):
    c = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=30)
    h = {"X-Ipe-Web": "1"}
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    return c, h


def _login(srv, u="admin", p="admin123"):
    c, h = _http(srv)
    c.request("POST", "/api/login", json.dumps({"username": u, "password": p}), {"Content-Type": "application/json"})
    return json.loads(c.getresponse().read())["token"]


def test_conexao_fica_aberta_e_sem_nagle(central):  # noqa: F811
    """O cliente reaproveita a conexão (uma só para vários pedidos); o servidor responde sem o atraso da confirmação
    (antes, 40 ms no Linux e até 200 ms no Windows por resposta pequena numa conexão aberta)."""
    import time

    from ipe.central import server as SRV
    paths, db, repo, srv = central
    assert SRV._Handler.disable_nagle_algorithm and SRV._Handler.timeout == 300
    abertas = []
    aceitar = srv._httpd.get_request

    def contar():
        r = aceitar()
        abertas.append(r[1])
        return r
    srv._httpd.get_request = contar
    c = RemoteClient(f"http://127.0.0.1:{srv.port}")
    c.login("admin", "admin123")
    t = time.perf_counter()
    for _ in range(20):
        c.rpc("counts")
    dt = (time.perf_counter() - t) / 20
    assert len(abertas) == 1, abertas                        # login + 20 chamadas numa conexão só
    assert dt < 0.03, f"{dt*1000:.0f} ms por chamada"       # com o Nagle, eram 40 ms ou mais
    # erro do servidor não estraga a conexão guardada
    with pytest.raises(RemoteError):
        c.rpc("metodo_que_nao_existe")
    assert c.rpc("counts") and len(abertas) == 1
    # pedido recusado antes de o servidor ler o corpo (sem login): o corpo que sobrou não vira o pedido seguinte
    from ipe.central.remote import Unauthorized
    anon = RemoteClient(f"http://127.0.0.1:{srv.port}")
    for _ in range(3):
        with pytest.raises(Unauthorized):
            anon.rpc("counts")
    with pytest.raises(Unauthorized):
        anon.login("admin", "errada")
    anon.login("admin", "admin123")
    assert anon.rpc("counts") and len(abertas) == 2          # tudo na mesma conexão do segundo cliente
    # o servidor fechou a conexão parada (reiniciou): o próximo pedido abre outra, sem erro
    for k, _q in c._reserva:
        k.sock.close()
    assert c.rpc("counts") and len(abertas) == 3
    c.fechar_conexoes()
    assert c.ping()["app"] == "Ipê" and len(abertas) == 4


def test_permissoes_guardadas_valem_na_hora_quando_mudam(central):  # noqa: F811
    paths, db, repo, srv = central
    c = RemoteClient(f"http://127.0.0.1:{srv.port}")
    c.login("res", "resid123")
    consultas = []
    ler = repo.get_app_setting
    repo.get_app_setting = lambda k, d=None: (consultas.append(k), ler(k, d))[1]
    for _ in range(10):
        assert c.rpc("counts")
    assert consultas.count("roles") <= 1                    # não uma consulta por pedido
    repo.set_app_setting("roles", {"residente": []})        # o administrador tirou tudo do residente
    with pytest.raises(RemoteError, match="perfil"):
        c.rpc("counts")                                     # vale já, sem esperar o guardado vencer
    repo.set_app_setting("roles", {"residente": ["view"]})
    assert c.rpc("counts")


def test_quem_ve_o_exame_guardado_vale_na_hora_quando_muda(central):  # noqa: F811
    paths, db, repo, srv = central
    uid = repo.find_study_uids(accession="ACC1001")[0]
    tok = _login(srv, "res", "resid123")
    c, h = _http(srv, tok)
    consultas = []
    info = repo.study_info
    repo.study_info = lambda u: (consultas.append(u), info(u))[1]

    def series():
        c.request("GET", f"/dicomweb/studies/{uid}/series", headers=h)
        r = c.getresponse()
        r.read()
        return r.status
    assert [series() for _ in range(6)] == [200] * 6
    assert consultas.count(uid) == 1                        # uma consulta, não seis
    repo.set_study_scope([uid], "admin")                    # foi para o banco pessoal de outro
    assert series() == 404
    repo.set_study_scope([uid], "")
    assert series() == 200


def test_quadro_sai_da_copia_pronta_sem_abrir_o_original(central, monkeypatch):  # noqa: F811
    from ipe.central import envio
    from ipe.central import web as WEB
    paths, db, repo, srv = central
    uid = repo.find_study_uids(accession="ACC1001")[0]
    se = repo.series_for_study(uid)[0].series_uid
    inst = repo.instances_for_series(se)[0]
    tok = _login(srv)
    c, h = _http(srv, tok)
    url = f"/dicomweb/studies/{uid}/series/{se}/instances/{inst['sop_uid']}/frames/1"

    def quadro():
        c.request("GET", url, headers=h)
        r = c.getresponse()
        return r.status, r.read()
    assert envio.quadros_prontos(inst["path"], [1]) is None       # ainda sem a cópia
    s1, b1 = quadro()                                              # o caminho completo faz a cópia
    assert s1 == 200 and envio.quadros_prontos(inst["path"], [1]) is not None
    chamadas = []
    completo = WEB.quadros_para_web
    monkeypatch.setattr(WEB, "quadros_para_web", lambda *a: (chamadas.append(a), completo(*a))[1])
    s2, b2 = quadro()
    assert s2 == 200 and not chamadas                              # direto do cache, sem ler o original

    def partes(b):
        return [x.split(b"\r\n\r\n", 1)[1] for x in b.split(b"\r\n--")[:-1] if b"\r\n\r\n" in x]
    assert partes(b1) == partes(b2)                                # os mesmos bytes
    assert envio.quadros_prontos(inst["path"], [0]) is None and envio.quadros_prontos(inst["path"], [2]) is None


def test_metadados_ficam_em_disco(central, monkeypatch):  # noqa: F811
    from ipe.central import envio
    from ipe.central import web as WEB
    paths, db, repo, srv = central
    uid = repo.find_study_uids(accession="ACC1001")[0]
    se = repo.series_for_study(uid)[0].series_uid
    a = WEB.metadados_prontos(repo, uid, se, "/dicomweb")
    assert a and list((envio.pasta() / "meta").rglob("*.json.gz"))
    WEB._META.clear()                                              # como depois de o servidor reiniciar
    lidos = []
    ler = WEB.metadados_da_serie
    monkeypatch.setattr(WEB, "metadados_da_serie", lambda *x: (lidos.append(x), ler(*x))[1])
    b = WEB.metadados_prontos(repo, uid, se, "/dicomweb")
    assert b[0] == a[0] and not lidos                              # do disco, sem reler os cabeçalhos
    # os exames recentes ficam prontos sem ocupar a memória
    WEB._META.clear()
    outra = repo.series_for_study(uid)[-1].series_uid
    assert WEB.metadados_prontos(repo, uid, se, "/dicomweb", guardar=False) == (b"", b"")
    assert not WEB._META
    if outra != se:
        WEB.metadados_prontos(repo, uid, outra, "/dicomweb", guardar=False)
        assert lidos and not WEB._META


def test_amostras_num_pedido_so_respeita_o_banco_pessoal(central, tmp_path):  # noqa: F811
    paths, db, repo, srv = central
    uid = repo.find_study_uids(accession="ACC1001")[0]
    series = repo.series_for_study(uid)
    c = RemoteClient(f"http://127.0.0.1:{srv.port}")
    c.login("res", "resid123")
    metas = []
    fs = c.retrieve(uid, tmp_path / "a", amostras=True, metas=metas)
    assert len(fs) == len(series) and {m["series_uid"] for m in metas} == {s.series_uid for s in series}
    assert all(set(m) >= {"sop_uid", "rows", "columns", "transfer_syntax"} and "file_path" not in m for m in metas)
    repo.set_study_scope([uid], "admin")
    with pytest.raises(RemoteError):
        c.retrieve(uid, tmp_path / "b", amostras=True)


# ---------------------------------------------------------------------------------------------- leitura
def _arquivo(tmp_path, dt, bits, sinal, lo, hi):
    from ipe.core.sample_data import _base, _mono, _save
    rng = np.random.default_rng(bits + sinal)
    pat = {"name": "X^Y", "id": "1", "birth": "19700101", "sex": "F"}
    st = {"uid": generate_uid(), "date": "20261108", "accession": "a", "description": "x", "for": generate_uid()}
    ds = _base("1.2.840.10008.5.1.4.1.1.2", pat, st, {"uid": generate_uid(), "number": 1, "description": "s"}, "CT")
    a = rng.integers(lo, hi, (64, 80)).astype(dt)
    _mono(ds, a.astype(np.int16 if sinal else np.uint16), signed=sinal)
    ds.BitsAllocated = 8 if dt == np.uint8 else 16
    ds.BitsStored, ds.HighBit, ds.PixelData = bits, bits - 1, a.tobytes()
    ds.compress(JPEGLSLossless)
    return _save(ds, tmp_path / f"{bits}{int(sinal)}{np.dtype(dt).name}"), a


@pytest.mark.parametrize("dt,bits,sinal,lo,hi,rapido", [
    (np.uint16, 12, False, 0, 4095, True), (np.uint16, 16, False, 0, 65535, True),
    (np.int16, 16, True, -2000, 3000, True), (np.int16, 12, True, -2000, 2000, False),
    (np.uint8, 8, False, 0, 255, True)])
def test_jpegls_rapido_da_a_mesma_imagem(tmp_path, dt, bits, sinal, lo, hi, rapido):
    import pydicom

    from ipe.imaging import series as S
    f, a = _arquivo(tmp_path, dt, bits, sinal, lo, hi)
    r = S._jpegls_rapido(pydicom.dcmread(f))
    assert (r is not None) == rapido                     # com sinal em menos de 16 bits: o caminho de sempre
    if r is not None:
        assert r.dtype == np.dtype(dt) and np.array_equal(r, a)
    img = S.read_frame(S.Frame(str(f), 0, "x", 1, n_frames=1))
    slope = float(pydicom.dcmread(f, stop_before_pixels=True).get("RescaleSlope", 1) or 1)
    inter = float(pydicom.dcmread(f, stop_before_pixels=True).get("RescaleIntercept", 0) or 0)
    assert np.allclose(img.pixels, a.astype(np.float32) * slope + inter)


def test_quadros_do_banco_nao_reabrem_o_cabecalho(tmp_path, monkeypatch):
    from ipe.imaging import series as S
    f, _a = _arquivo(tmp_path, np.uint16, 12, False, 0, 4095)
    vistos = []
    monkeypatch.setattr(S, "_is_multiframe", lambda p: (vistos.append(p), False)[1])
    frames = S.build_frames([{"path": str(f), "sop_uid": "1", "instance_number": 1, "frames": 1}])
    assert frames[0].n_frames == 1
    S.read_frame(frames[0])
    assert not vistos                                    # o banco já disse que é um quadro só
    S.read_frame(S.Frame(str(f), 0, "1", 1))             # sem a informação: pergunta ao arquivo, como antes
    assert vistos


def test_aquecer_decodifica_em_paralelo(tmp_path):
    from ipe.imaging import series as S
    arquivos = [_arquivo(tmp_path / str(i), np.uint16, 12, False, 0, 4095)[0] for i in range(4)]
    cache = S.FrameCache(64)
    frames = [S.Frame(str(f), 0, str(i), i, n_frames=1) for i, f in enumerate(arquivos)]
    cache.aquecer(frames + frames[:1] + [S.Frame(str(tmp_path / "nao_existe.dcm"), 0, "z", 9, n_frames=1)])
    assert all(cache.contains(f) for f in frames)        # todos prontos na volta; o que falha não derruba


def test_regiao_conectada_rapida_igual_a_dilatacao(monkeypatch):
    from ipe.imaging import segment as SG
    rng = np.random.default_rng(3)
    for forma in ((1, 120, 90), (1, 300, 220), (9, 40, 40)):
        for _ in range(5):
            m = rng.random(forma) > 0.42
            pts = np.argwhere(m)
            seed = tuple(int(v) for v in pts[rng.integers(len(pts))])
            rapida = SG._grow(m, seed)
            with monkeypatch.context() as mp:
                mp.setattr(SG, "_componente_rapida", lambda *a: None)
                assert np.array_equal(rapida, SG._grow(m, seed)), forma
    vazio = np.zeros((1, 8, 8), bool)
    assert not SG._grow(vazio, (0, 1, 1)).any()


def test_desligar_o_servidor_fecha_as_conexoes_abertas(central):  # noqa: F811
    paths, db, repo, srv = central
    c = RemoteClient(f"http://127.0.0.1:{srv.port}")
    c.login("admin", "admin123")
    assert c.rpc("counts") and c._reserva                    # uma conexão guardada
    srv.stop()
    with pytest.raises(RemoteError):
        c.rpc("counts")                                     # não é atendida por um servidor desligado
