"""0.100.104: "Manter conectado neste computador (1 dia)" no Ipê Web — vale nas outras abas e nos links de abertura;
o servidor segura o login por 1 dia mesmo parado, e o administrador pode desligar."""
import json
import sys
import time
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_pacs_pelo_servidor import servidor  # noqa: E402,F401

from ipe.central import server as SV  # noqa: E402


def _login(srv, lembrar):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/login", method="POST",
                                 data=json.dumps({"username": "admin", "password": "admin123",
                                                  "lembrar": lembrar}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def test_servidor_segura_por_um_dia(servidor, monkeypatch):
    srv = servidor
    comum, lembrado = _login(srv, False), _login(srv, True)
    assert comum["lembrar_ate"] == 0
    assert abs(lembrado["lembrar_ate"] - (time.time() + SV.LEMBRAR_S)) < 60
    cab = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731
    agora = time.time()
    monkeypatch.setattr(SV.time, "time", lambda: agora + 13 * 3600)      # 13 h parado
    assert srv.session_for(cab(comum["token"])) is None                  # o comum caiu (12 h)
    assert srv.session_for(cab(lembrado["token"])) is not None           # o lembrado não
    monkeypatch.setattr(SV.time, "time", lambda: agora + 25 * 3600)
    assert srv.session_for(cab(lembrado["token"])) is None               # depois de 1 dia, cai
    monkeypatch.undo()
    srv.settings.set("web.manter_conectado", False)                      # o administrador desligou
    assert _login(srv, True)["lembrar_ate"] == 0
    acoes = [a["action"] for a in srv.repo_.access_log(limit=50)]
    assert "login_lembrar" in acoes


def test_outra_aba_entra_sem_senha(servidor):
    pw = pytest.importorskip("playwright.sync_api")
    srv = servidor
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        ctx = b.new_context(viewport={"width": 1300, "height": 850})
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(f"http://127.0.0.1:{srv.port}/web/")
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.check("#lembrar")
        pg.click("button[type=submit]")
        pg.wait_for_selector("form.filtros")
        # outra aba (o link de um sistema externo): entra direto
        pg2 = ctx.new_page()
        pg2.on("pageerror", lambda e: erros.append(str(e)))
        pg2.goto(f"http://127.0.0.1:{srv.port}/web/#/abrir?acesso=NAOEXISTE")
        pg2.wait_for_selector(".tela-abrir")
        assert pg2.locator("#senha").count() == 0
        # sair esquece em todas
        pg2.click("header button.sair")                     # na tela de abertura: sai do Ipê Web
        pg2.wait_for_selector("#senha")
        pg3 = ctx.new_page()
        pg3.goto(f"http://127.0.0.1:{srv.port}/web/")
        pg3.wait_for_selector("#senha")
        # sem marcar: outra aba pede a senha
        pg3.fill("#usuario", "admin")
        pg3.fill("#senha", "admin123")
        pg3.click("button[type=submit]")
        pg3.wait_for_selector("form.filtros")
        pg4 = ctx.new_page()
        pg4.goto(f"http://127.0.0.1:{srv.port}/web/")
        pg4.wait_for_selector("#senha")
        b.close()
    assert not erros, erros
