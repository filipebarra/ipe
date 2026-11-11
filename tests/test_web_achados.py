"""0.100.16: revisar os achados de IA pelo navegador (enfisema, nódulos…) — confirmar, corrigir, descartar, voltar a
sugerido, ir até e mandar ao laudo. Pergunta dele: "as IAs que precisam de confirmação, como o enfisema — hoje eu
não consigo confirmar pelo web, certo?"."""
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_coluna import _exame  # noqa: E402

from ipe.ai import achados as AC  # noqa: E402
from ipe.central import web as WEB  # noqa: E402


def _enfisema(repo, uid, serie):
    itens = [{"rotulo": "Enfisema", "tipo": "%LAA−950", "local": "pulmões (predomínio nos lobos superiores)",
              "series_uid": serie, "posicao": [0.0, 0.0, 20.0],
              "numeros": {"laa_total": AC.numero(12.4, "%", "LAA total"), "laa_D": AC.numero(13.0, "%", "LAA direito"),
                          "laa_E": AC.numero(11.8, "%", "LAA esquerdo"),
                          "perc15_total": AC.numero(-948.0, "HU", "Perc15")},
              "modelo": "TotalSegmentator", "versao": "2.x", "elegibilidade": "TC de tórax"}]
    return repo.gravar_achados(uid, "enfisema", itens)


@pytest.fixture()
def servidor(env, tmp_path):
    from PySide6.QtWidgets import QApplication
    from ipe.auth.backend import LocalAuth
    from ipe.central.server import CentralServer
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie = _exame(env, tmp_path, descricao="TC TORAX", serie="AX PULMAO")
    ids = _enfisema(repo, uid, serie)
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    repo.save_user({"username": "tec", "full_name": "Técnico", "role": "tecnico", "password": "tecnico123"})
    repo.save_user({"username": "res", "full_name": "Residente", "role": "residente", "password": "resid123"})
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    srv.app, srv.estudo, srv.serie, srv.repo_, srv.achado = app, uid, serie, repo, ids[0]
    yield srv
    srv.stop()


def _token(srv, u="admin", p="admin123"):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/login", method="POST",
                                 data=json.dumps({"username": u, "password": p}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())["token"]


def _api(srv, rota, corpo=None, tok=None):
    tok = tok or _token(srv)
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}{rota}", method="POST" if corpo is not None else "GET",
                                 data=json.dumps(corpo).encode() if corpo is not None else None,
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def test_revisar_pela_api(servidor):
    srv = servidor
    d = _api(srv, f"/api/web/achados?study={srv.estudo}")
    assert d["pode_revisar"] and d["contagem"]["sugerido"] == 1 and d["texto_laudo"] == ""   # nada sem revisão
    a = d["achados"][0]
    assert a["titulo"] and a["estado"] == "sugerido" and a["posicao"] == [0.0, 0.0, 20.0]
    assert {c["chave"] for c in a["campos"]} == {"laa_total", "laa_D", "laa_E", "perc15_total"}
    # confirmar: vai ao laudo
    r = _api(srv, "/api/web/achados/revisar", {"id": a["id"], "estado": "confirmado"})
    assert r["achado"]["estado"] == "confirmado" and "Administrador" in r["achado"]["revisao"]
    d = _api(srv, f"/api/web/achados?study={srv.estudo}")
    assert "12,4%" in d["texto_laudo"] and d["texto_laudo"] == WEB.texto_dos_achados(srv.repo_, srv.estudo)
    # corrigir (vírgula decimal): fica "corrigido" e o laudo leva o número do médico
    r = _api(srv, "/api/web/achados/revisar", {"id": a["id"], "corrigidos": {"laa_total": "10,5", "laa_D": "13"},
                                               "nota": "conferido"})
    assert r["achado"]["estado"] == "corrigido" and r["achado"]["nota"] == "conferido"
    assert srv.repo_.achado(a["id"])["corrigidos"] == {"laa_total": 10.5}            # igual ao da IA não conta
    assert "10,5%" in _api(srv, f"/api/web/achados?study={srv.estudo}")["texto_laudo"]
    # número inválido: 400, nada muda
    with pytest.raises(urllib.error.HTTPError) as e:
        _api(srv, "/api/web/achados/revisar", {"id": a["id"], "corrigidos": {"laa_total": "abc"}})
    assert e.value.code == 400 and srv.repo_.achado(a["id"])["estado"] == "corrigido"
    # descartar e voltar a sugerido
    assert _api(srv, "/api/web/achados/revisar", {"id": a["id"], "estado": "descartado"})["achado"]["estado"] == "descartado"
    assert _api(srv, f"/api/web/achados?study={srv.estudo}")["texto_laudo"] == ""
    assert _api(srv, "/api/web/achados/revisar", {"id": a["id"], "estado": "sugerido"})["achado"]["estado"] == "sugerido"
    assert srv.repo_.access_log(user="admin", action="ia_revisar")
    # o técnico vê, mas não revisa; o residente (escreve laudos) revisa
    tec = _token(srv, "tec", "tecnico123")
    assert not _api(srv, f"/api/web/achados?study={srv.estudo}", tok=tec)["pode_revisar"]
    with pytest.raises(urllib.error.HTTPError) as e:
        _api(srv, "/api/web/achados/revisar", {"id": a["id"], "estado": "confirmado"}, tok=tec)
    assert e.value.code == 403
    res = _token(srv, "res", "resid123")
    assert _api(srv, "/api/web/achados/revisar", {"id": a["id"], "estado": "confirmado"}, tok=res)["achado"]["estado"] == "confirmado"


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_revisar_no_navegador_e_mandar_ao_laudo(servidor):
    pw = pytest.importorskip("playwright.sync_api")
    srv = servidor
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1500, "height": 950})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(f"http://127.0.0.1:{srv.port}/web/")
        pg.fill("#usuario", "res")              # o residente: sem pedir IA, mas revisa (a aba aparece só com a revisão)
        pg.fill("#senha", "resid123")
        pg.click("button[type=submit]")
        pg.wait_for_selector("table.lista tbody tr")
        pg.locator("table.lista tbody tr").first.dblclick()
        pg.wait_for_selector(".quadro canvas")
        pg.click(".lateral .abas button[data-aba='IA']")
        linha = pg.locator(f".achados-ia .achado[data-id='{srv.achado}']")
        linha.wait_for(timeout=15000)
        assert pg.locator(".aba-ia .ferramenta-ia").count() == 0          # sem a permissão de pedir IA
        assert "Sugerido" in linha.inner_text() and "LAA total" in linha.inner_text()
        # ir até: o quadro vai ao corte do achado (z = 20 mm; a pilha vai de baixo para cima: índice 23; abre no 33)
        linha.locator("button:has-text('Ir até')").click()
        pg.wait_for_function("() => window.__ipeGrade.viewport(0).getCurrentImageIdIndex() === 23", timeout=10000)
        # corrigir
        linha.locator("button:has-text('Corrigir')").click()
        import os
        if os.environ.get("IPE_SHOT_DIR"):
            pg.screenshot(path=os.path.join(os.environ["IPE_SHOT_DIR"], "achados_web.png"))
        pg.fill(f".achados-ia .achado[data-id='{srv.achado}'] input[name='laa_total']", "9,9")
        pg.click(f".achados-ia .achado[data-id='{srv.achado}'] button[type=submit]")
        pg.wait_for_function(f"() => document.querySelector(\".achados-ia .achado[data-id='{srv.achado}']\")?.classList.contains('corrigido')", timeout=10000)
        assert srv.repo_.achado(srv.achado)["corrigidos"] == {"laa_total": 9.9}
        # mandar ao laudo: abre o laudo e o texto entra
        pg.click(".achados-ia button:has-text('Mandar ao laudo')")
        pg.wait_for_function("() => (document.querySelector('.painel-laudo textarea, .laudo textarea')?.value || '').includes('9,9%')", timeout=15000)
        b.close()
    assert not erros, erros
