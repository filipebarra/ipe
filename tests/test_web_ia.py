"""0.100.10: pedir CAD/IA pelo visualizador web e acompanhar — as ferramentas que servem para o exame (com a série),
o pedido entrando na fila de IA do servidor (o TotalSegmentator simulado), as tarefas com a etapa até o "Pronto",
o cancelamento e a permissão de pedir CAD/IA (o residente não pede)."""
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_cad_ia import _Rede, _exame_ct, _settings  # noqa: E402

from ipe.ai import tarefas as TA  # noqa: E402
from ipe.ai import totalseg as TS  # noqa: E402
from ipe.central import web as WEB  # noqa: E402


@pytest.fixture()
def servidor(env, tmp_path):
    from PySide6.QtWidgets import QApplication
    from ipe.auth.backend import LocalAuth
    from ipe.automation.engine import AutomationEngine
    from ipe.central.server import CentralServer
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie = _exame_ct(env, tmp_path)
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    repo.save_user({"username": "res", "full_name": "Residente", "role": "residente", "password": "resid123"})
    st = _settings(paths)
    st.set(TS.CHAVE_COUINAUD, False)
    eng = AutomationEngine(repo, db, _Rede(), st, paths)
    eng._seg_simular = True
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.settings, srv.auto = st, eng
    srv.start()
    TA.REGISTRO.limpar_feitas()
    srv.app, srv.estudo, srv.serie, srv.repo_ = app, uid, serie["AX PORTAL"], repo
    yield srv
    srv.stop()


def _token(srv, u="admin", p="admin123"):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/login", method="POST",
                                 data=json.dumps({"username": u, "password": p}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())["token"]


def _api(srv, rota, corpo=None, tok=None):
    """O pedido numa linha à parte, com a linha principal girando o laço de eventos (a fila de IA mora nela)."""
    tok = tok or _token(srv)
    caixa = {}

    def ir():
        req = urllib.request.Request(f"http://127.0.0.1:{srv.port}{rota}", method="POST" if corpo is not None else "GET",
                                     data=json.dumps(corpo).encode() if corpo is not None else None,
                                     headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        try:
            caixa["r"] = json.loads(urllib.request.urlopen(req).read())
        except urllib.error.HTTPError as e:
            caixa["e"] = e
    t = threading.Thread(target=ir)
    t.start()
    while t.is_alive():
        srv.app.processEvents()
        time.sleep(0.02)
    if "e" in caixa:
        raise caixa["e"]
    return caixa["r"]


def _esperar(srv, f, t=30.0):
    fim = time.time() + t
    while time.time() < fim:
        srv.app.processEvents()
        if f():
            return True
        time.sleep(0.05)
    return f()


def test_ferramentas_pedir_e_acompanhar(servidor):
    srv = servidor
    q = f"?study={srv.estudo}"
    d = _api(srv, "/api/web/ia" + q)
    assert d["instalado"]
    abd = next(f for f in d["ferramentas"] if f["tipo"] == "abdome")
    assert abd["serie"] == srv.serie and "AX PORTAL" in abd["serie_rotulo"] and not abd["ja_feita"]
    assert any(f["tipo"] == "cefalometria" for f in d["ferramentas"])
    r = _api(srv, "/api/web/ia/pedir", {"study": srv.estudo, "tipo": "abdome"})
    assert r["ok"] and r["tarefa"]

    def estado():
        ts = _api(srv, "/api/web/ia/tarefas" + q)["tarefas"]
        return ts[0]["estado"] if ts else ""
    assert _esperar(srv, lambda: estado() == TA.PRONTO, 60), _api(srv, "/api/web/ia/tarefas" + q)
    t = _api(srv, "/api/web/ia/tarefas" + q)["tarefas"][0]
    assert t["ferramenta"] == "Órgãos abdominais" and t["origem"] == "manual · admin" and not t["ativa"]
    assert len(TS.series_locais(srv.repo_, srv.estudo)) == 2
    d2 = _api(srv, "/api/web/ia" + q)
    assert next(f for f in d2["ferramentas"] if f["tipo"] == "abdome")["ja_feita"]
    assert srv.repo_.access_log(limit=5, action="ia", study_uid=srv.estudo)
    # série de outro exame e ferramenta desconhecida
    for corpo in ({"study": srv.estudo, "tipo": "abdome", "serie": "1.2.3"}, {"study": srv.estudo, "tipo": "xyz"}):
        with pytest.raises(urllib.error.HTTPError) as e:
            _api(srv, "/api/web/ia/pedir", corpo)
        assert e.value.code == 400


def test_cancelar_na_fila_e_permissao(servidor):
    srv = servidor
    TS.EM_CURSO.add("outro-exame")          # outra segmentação rodando: a pedida fica na fila
    try:
        r = _api(srv, "/api/web/ia/pedir", {"study": srv.estudo, "tipo": "abdome"})
        ts = _api(srv, f"/api/web/ia/tarefas?study={srv.estudo}")["tarefas"]
        assert ts[0]["estado"] == TA.FILA and ts[0]["pode_cancelar"]
        # o residente não pede nem cancela
        tok = _token(srv, "res", "resid123")
        for rota, corpo in (("/api/web/ia/pedir", {"study": srv.estudo, "tipo": "abdome"}),
                            ("/api/web/ia/cancelar", {"id": r["tarefa"]})):
            with pytest.raises(urllib.error.HTTPError) as e:
                _api(srv, rota, corpo, tok)
            assert e.value.code == 403
        # pedir de novo a mesma enquanto está na fila: não duplica
        with pytest.raises(urllib.error.HTTPError) as e:
            _api(srv, "/api/web/ia/pedir", {"study": srv.estudo, "tipo": "abdome"})
        assert e.value.code == 400
        assert _api(srv, "/api/web/ia/cancelar", {"id": r["tarefa"]})["ok"]
        assert _api(srv, f"/api/web/ia/tarefas?study={srv.estudo}")["tarefas"][0]["estado"] == TA.CANCELADO
        assert not srv.auto._seg_fila
    finally:
        TS.EM_CURSO.discard("outro-exame")


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_pelo_navegador(servidor):
    pw = pytest.importorskip("playwright.sync_api")
    srv = servidor
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        for usuario, senha, pode in (("res", "resid123", False), ("admin", "admin123", True)):
            pg = b.new_page(viewport={"width": 1500, "height": 950})
            pg.on("pageerror", lambda e: erros.append(str(e)))
            pg.goto(f"http://127.0.0.1:{srv.port}/web/")
            pg.fill("#usuario", usuario)
            pg.fill("#senha", senha)
            pg.click("button[type=submit]")
            pg.wait_for_selector("table.lista tbody tr")
            pg.locator("table.lista tbody tr").first.dblclick()
            pg.wait_for_selector(".quadro canvas")
            botao = pg.locator("nav.barra button[aria-label='CAD/IA neste exame']")
            assert botao.is_visible() == pode
            if not pode:
                pg.close()
                continue
            botao.click()
            assert _esperar(srv, lambda: pg.locator(".painel-ia .ferramenta-ia[data-tipo='abdome'] button").count() == 1, 20)
            linha = pg.locator(".painel-ia .ferramenta-ia[data-tipo='abdome']")
            assert "AX PORTAL" in linha.inner_text()
            linha.locator("button").click()
            assert _esperar(srv, lambda: pg.locator(".painel-ia").count() == 0, 20)
            assert _esperar(srv, lambda: "Recarregar o exame" in pg.inner_text(".area"), 60), pg.inner_text(".area")
            pg.click(".rodape button:has-text('IA')")
            assert _esperar(srv, lambda: pg.locator(".tarefas-ia .tarefa.pronto").count() == 1, 15)
            assert "Órgãos abdominais" in pg.inner_text(".tarefas-ia")
            pg.click(".area button:has-text('Recarregar o exame')")
            assert _esperar(srv, lambda: pg.locator(".tira .serie").count() >= 1, 20)
            pg.close()
        b.close()
    assert not erros, erros
