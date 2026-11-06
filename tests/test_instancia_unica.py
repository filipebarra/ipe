"""Um Ipê só por usuário (0.99.79).

Pedido dele: *"vários programas são abertos se eu clicar mais de uma vez no atalho. isso acontece também
quando escolho minimizar o programa ao fechar e deixar ele aberto no tray"*.
"""
import json
import subprocess
import sys
import time
import uuid

from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalServer

from ipe import app as A

SEGURA = """
import sys, time
from PySide6.QtCore import QLockFile
t = QLockFile(sys.argv[1]); t.setStaleLockTime(0)
assert t.tryLock(1000)
print("OK", flush=True)
time.sleep(60)
"""


def _qapp():
    return QCoreApplication.instance() or QCoreApplication([])


def test_segundo_programa_nao_pega_a_vez_e_a_trava_de_quem_caiu_se_solta(tmp_path, monkeypatch):
    arq = str(tmp_path / "ipe.lock")
    monkeypatch.setattr(A, "_arquivo_da_trava", lambda: arq)
    outro = subprocess.Popen([sys.executable, "-c", SEGURA, arq], stdout=subprocess.PIPE, text=True)
    try:
        assert outro.stdout.readline().strip() == "OK"
        assert A.pegar_a_vez() is None                 # o primeiro está aberto
    finally:
        outro.kill()
        outro.wait()
    trava = A.pegar_a_vez()                            # caiu sem soltar: a trava velha não prende
    assert trava is not None
    trava.unlock()


def test_mesmo_processo_segunda_trava_falha(tmp_path, monkeypatch):
    arq = str(tmp_path / "ipe.lock")
    monkeypatch.setattr(A, "_arquivo_da_trava", lambda: arq)
    t1 = A.pegar_a_vez()
    assert t1 is not None
    assert A.pegar_a_vez() is None
    t1.unlock()
    t2 = A.pegar_a_vez()
    assert t2 is not None
    t2.unlock()


def test_o_pedido_chega_ao_programa_aberto_mesmo_se_ele_ainda_esta_abrindo(monkeypatch):
    app = _qapp()
    nome = f"ipe-teste-{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(A, "SERVER_NAME", nome)
    assert A.avisar_a_instancia_aberta({"command": "mostrar"}, espera_s=0.4) is False
    recebidos = []
    srv = QLocalServer()
    QLocalServer.removeServer(nome)
    assert srv.listen(nome)

    def conexao():
        c = srv.nextPendingConnection()
        c.readyRead.connect(lambda: recebidos.append(json.loads(bytes(c.readAll()).decode())))
    srv.newConnection.connect(conexao)
    import threading
    res = {}
    th = threading.Thread(target=lambda: res.setdefault("ok", A.avisar_a_instancia_aberta(
        {"command": "mostrar", "minimizado": False}, espera_s=5)))
    th.start()
    fim = time.monotonic() + 5
    while (th.is_alive() or not recebidos) and time.monotonic() < fim:
        app.processEvents()
        time.sleep(0.02)
    th.join(1)
    srv.close()
    assert res.get("ok") is True
    assert recebidos == [{"command": "mostrar", "minimizado": False}]


def test_run_gui_trava_antes_do_login_e_traz_a_janela():
    import inspect
    fonte = inspect.getsource(A.run_gui)
    i_trava = fonte.index("pegar_a_vez()")
    assert i_trava < fonte.index("open_main_window(")      # antes do login: dois cliques rápidos
    assert i_trava < fonte.index("MB.pendente(")           # e antes de mexer no banco
    assert '"command": "mostrar"' in fonte
    assert "trazer_para_a_frente" in fonte                 # traz da bandeja (esconde ≠ fecha)
    assert "IPE_VARIAS_INSTANCIAS" in fonte
