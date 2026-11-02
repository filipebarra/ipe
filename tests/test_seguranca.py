"""0.99.24: revisão de segurança — link sem token, AE + IP, impressora só da rede local, senha errada
no servidor central.

Pedido dele, depois da revisão: "sim" para corrigir o link ipe:// sem token, o servidor central, a
impressora DICOM e o AE Title que se imita.
"""
import json
import time
import urllib.error
import urllib.request

import pytest

from ipe.network import acesso as A
from ipe.network.external import parse_url, token_confere


# ------------------------------------------------------------------ regras
def test_rede_local():
    for ip in ("10.0.3.47", "172.20.1.1", "192.168.1.216", "127.0.0.1", "100.101.1.2", "::1", "::ffff:10.1.1.1"):
        assert A.ip_da_rede_local(ip), ip
    for ip in ("8.8.8.8", "200.160.2.3", "", "lixo"):
        assert not A.ip_da_rede_local(ip), ip


def test_ip_do_no_confere():
    nodes = [{"ae_title": "TC1", "host": "10.0.3.47"}, {"ae_title": "RM1", "host": ""}]
    assert A.ip_do_no_confere(nodes, "TC1", "10.0.3.47")
    assert not A.ip_do_no_confere(nodes, "TC1", "10.0.3.99")           # outro computador dizendo ser o TC1
    assert not A.ip_do_no_confere(nodes, "RM1", "10.0.3.50")           # nó sem IP: não há com o que comparar
    assert not A.ip_do_no_confere(nodes, "DESCONHECIDO", "10.0.3.47")
    assert A.ip_do_no_confere(nodes, "TC1", "127.0.0.1")               # o próprio computador


def test_tentativas_bloqueiam_e_acerto_zera():
    t = A.Tentativas(maximo=3, janela_s=60, bloqueio_s=60)
    t.errou("1.2.3.4")
    t.errou("1.2.3.4")
    t.acertou("1.2.3.4")
    t.errou("1.2.3.4")
    t.errou("1.2.3.4")
    assert t.bloqueado("1.2.3.4") == 0
    t.errou("1.2.3.4")
    assert t.bloqueado("1.2.3.4") > 0 and t.bloqueado("5.6.7.8") == 0


def test_link_traz_o_token_e_comparacao_em_tempo_constante():
    p = parse_url("ipe://open?accession=123&token=abc%2Bdef")
    assert p["accession"] == "123" and p["link_token"] == "abc+def"
    assert "link_token" not in parse_url("ipe://open?accession=123")
    assert token_confere("x", "x") and not token_confere("x", "y") and not token_confere("", "")


# ------------------------------------------------------------------ link na janela principal
@pytest.fixture()
def janela(env):
    from PySide6.QtWidgets import QApplication

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    cfg = dict(w.settings.get("dicom", {}) or {})
    cfg["http_token"] = "segredo"
    w.settings.set("dicom", cfg)
    yield w
    w.close()


def _modo(w, modo):
    cfg = dict(w.settings.get("dicom", {}) or {})
    cfg["link_sem_token"] = modo
    w.settings.set("dicom", cfg)


def test_link_sem_token_pergunta_recusa_ou_aceita(janela, monkeypatch):
    w = janela
    perguntas = []
    monkeypatch.setattr(type(w), "perguntar_link", lambda self, a, o: perguntas.append(o) or False)
    assert w.settings.get("dicom", {}).get("link_sem_token", "perguntar") == "perguntar"
    assert w.handle_external({"command": "open", "accession": "X1", "source": "link"}) == "recusado"
    assert perguntas == ["X1"]
    # com o token certo, nem pergunta
    r = w.handle_external({"command": "open", "accession": "X1", "source": "link", "link_token": "segredo"})
    assert r != "recusado" and perguntas == ["X1"]
    # token errado: é como sem token
    assert w.handle_external({"command": "open", "accession": "X1", "source": "link",
                              "link_token": "errado"}) == "recusado"
    _modo(w, "recusar")
    assert w.handle_external({"command": "open", "accession": "X1", "source": "link"}) == "recusado"
    assert len(perguntas) == 2
    _modo(w, "aceitar")
    assert w.handle_external({"command": "open", "accession": "X1", "source": "link"}) != "recusado"
    # chamada da API HTTP (com token na API) não passa por isto
    _modo(w, "recusar")
    assert w.handle_external({"command": "open", "accession": "X1", "source": "http:127.0.0.1"}) != "recusado"


def test_tela_de_rede_grava_a_escolha_do_link_e_o_ip(janela):
    from ipe.ui.network_dialog import NetworkDialog
    dlg = NetworkDialog(janela.settings, janela.repo, janela.net, janela)
    assert dlg.link_sem.currentData() == "perguntar"
    assert dlg.accept_c.findData("known_ip") >= 0
    dlg.link_sem.setCurrentIndex(dlg.link_sem.findData("recusar"))
    dlg.accept_c.setCurrentIndex(dlg.accept_c.findData("known_ip"))
    dlg._save()
    c = janela.settings.get("dicom", {})
    assert c["link_sem_token"] == "recusar" and c["accept"] == "known_ip"
    dlg.close()


# ------------------------------------------------------------------ nó DICOM: AE + IP
def test_no_dicom_conferindo_o_ip_recusa_quem_imita_o_ae(tmp_path, sample_dir, monkeypatch):
    from test_network import Node

    from ipe.network.client import DicomClient, Target
    me = Node(tmp_path / "me", "DICOMVIEWER", accept="known_ip")
    me.repo.save_node({"name": "TC1", "ae_title": "TC1", "host": "127.0.0.1", "port": 104, "retrieve": "get",
                       "move_destination": "", "use_in_search": False})
    assert me.server.start()
    try:
        c = DicomClient(timeout=5)
        alvo = Target.build(me.as_node(), "TC1")
        assert c.echo(alvo)[0]                          # 127.0.0.1 é o endereço cadastrado
        # o mesmo AE vindo de outro endereço (simulado): a conexão cai
        monkeypatch.setattr(A, "ip_do_no_confere", lambda nodes, ae, ip: False)
        ok, _msg = c.echo(alvo)
        assert not ok and me.server.recusados and me.server.recusados[-1][1] == "TC1"
    finally:
        me.close()


# ------------------------------------------------------------------ impressora: rede local
def test_impressora_nova_aceita_so_a_rede_local():
    from ipe.network.print_scp import PrintScpServer as PrintServer
    from ipe.printing.config import ServerConfig
    assert ServerConfig().accept == "rede"
    srv = PrintServer.__new__(PrintServer)
    srv.config = {"accept": "rede"}
    assert srv.aceita_endereco("10.0.3.47") and not srv.aceita_endereco("200.160.2.3")
    srv.config = {"accept": "any"}
    assert srv.aceita_endereco("200.160.2.3")


# ------------------------------------------------------------------ servidor central: senha errada
def test_servidor_central_bloqueia_depois_de_cinco_senhas_erradas(env):
    from ipe.auth.backend import LocalAuth
    from ipe.central.server import CentralServer
    paths, db, repo = env
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    try:
        url = f"http://127.0.0.1:{srv.port}/api/login"

        def login(pw):
            req = urllib.request.Request(url, data=json.dumps({"username": "admin", "password": pw}).encode(),
                                         method="POST", headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                return e.code
        assert login("admin123") == 200
        assert [login("errada") for _ in range(5)] == [401] * 5
        assert login("admin123") == 429                      # até a certa, enquanto durar o bloqueio
        srv.tentativas._ate.clear()
        assert login("admin123") == 200
    finally:
        srv.stop()
