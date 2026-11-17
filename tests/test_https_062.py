"""0.100.62: o servidor HTTPS negocia cada conexão na linha dela — uma conexão que abre e não diz nada não para
mais o servidor (o Ipê Web "sumia" até reiniciar) — e o http:// do mesmo endereço leva ao https://."""
import http.client
import socket
import ssl
import time

import pytest

pytest.importorskip("cryptography")

from ipe.central.remote import RemoteClient  # noqa: E402
from ipe.central.server import CentralServer  # noqa: E402
from ipe.core import certificados as CE  # noqa: E402


@pytest.fixture()
def https(env, tmp_path):
    paths, db, repo = env
    r = CE.gerar(tmp_path / "c", ["localhost"], ["127.0.0.1"])
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1", certfile=r["certfile"], keyfile=r["keyfile"])
    srv.start()
    srv.ac = r["ac_pem"]
    yield srv
    srv.stop()


def test_conexao_muda_nao_para_o_servidor(https):
    srv = https
    url = f"https://127.0.0.1:{srv.port}"
    mudas = [socket.create_connection(("127.0.0.1", srv.port)) for _ in range(3)]      # abrem e não dizem nada
    try:
        t0 = time.time()
        assert RemoteClient(url, ca_pem=srv.ac).ping()["ok"]            # antes: ficava esperando a primeira muda
        assert time.time() - t0 < 5
        # uma que manda lixo no lugar da negociação também não atrapalha as outras
        lixo = socket.create_connection(("127.0.0.1", srv.port))
        lixo.sendall(b"\x16\x03\x01\x00\x05lixo!")
        assert RemoteClient(url, ca_pem=srv.ac).ping()["ok"]
        lixo.close()
    finally:
        for m in mudas:
            m.close()
    assert RemoteClient(url, ca_pem=srv.ac).ping()["ok"]


def test_muda_e_desligada_no_prazo(https):
    srv = https
    srv._httpd.ESPERA_TLS = 0.5
    m = socket.create_connection(("127.0.0.1", srv.port))
    m.settimeout(5)
    assert m.recv(1) == b""                                             # o servidor desligou a conexão parada
    m.close()


def test_http_puro_leva_ao_https(https):
    srv = https
    c = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    c.request("GET", "/web/?x=1", headers={"Host": f"servidor-imeb:{srv.port}"})
    r = c.getresponse()
    assert r.status == 308 and r.getheader("Location") == f"https://servidor-imeb:{srv.port}/web/?x=1"
    assert r.getheader("Strict-Transport-Security") is None
    r.read()
    c.close()
    c = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    c.request("POST", "/api/login", body=b'{"username":"a","password":"b"}', headers={"Content-Type": "application/json"})
    r = c.getresponse()
    assert r.status == 308 and r.getheader("Location").startswith("https://127.0.0.1:")
    c.close()
    # e o HTTPS segue atendendo várias conexões ao mesmo tempo, com a conexão guardada entre pedidos
    ctx = ssl.create_default_context(cadata=srv.ac)
    c = http.client.HTTPSConnection("127.0.0.1", srv.port, timeout=5, context=ctx)
    for _ in range(3):
        c.request("GET", "/api/ping")
        r = c.getresponse()
        assert r.status == 200 and b'"ok"' in r.read()
    c.close()


def test_servidor_http_segue_igual(env):
    paths, db, repo = env
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    try:
        assert srv._httpd.tls is None
        assert RemoteClient(f"http://127.0.0.1:{srv.port}").ping()["ok"]
    finally:
        srv.stop()
