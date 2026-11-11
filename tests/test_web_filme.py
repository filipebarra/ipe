"""0.100.11: o filme do visualizador web — a receita (o JSON do compositor) desenhada pelo servidor com o código do
Ipê: a prévia (PNG), o PDF baixado, os destinos de impressão do Ipê (PDF e imagens numa pasta), a impressora DICOM
(uma impressora falsa em loopback) e a permissão de imprimir. No navegador: pôr o quadro no filme, a prévia, o
ajuste do quadro (janela, zoom, deslocamento) indo e voltando da célula, e imprimir."""
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _web_ui import icone  # noqa: E402,F401

from ipe.central import web as WEB  # noqa: E402


@pytest.fixture()
def servidor(env, sample_dir, tmp_path):
    from PySide6.QtWidgets import QApplication
    from print_scp import FakePrinter
    from test_network import free_port
    from ipe.auth.backend import LocalAuth
    from ipe.central.server import CentralServer
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    repo.save_user({"username": "res", "full_name": "Residente", "role": "residente", "password": "resid123"})
    repo.set_app_setting("roles", {"residente": ["view"]})                  # este residente não imprime
    porta = free_port()
    fp = FakePrinter(porta)
    st = Settings(paths.settings_file)
    st.set("printing.dicom_printers", [{"name": "Dry", "ae_title": "FAKEPRN", "host": "127.0.0.1", "port": porta,
                                        "dpi": 40}])
    st.set("printing.destinations", [
        {"name": "Pasta PDF", "kind": "pdf", "folder": str(tmp_path / "pdfs")},
        {"name": "Pasta imagens", "kind": "images", "folder": str(tmp_path / "imgs"), "dpi": 40, "fmt": "png"}])
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.settings = st
    srv.start()
    estudo = next(r for r in repo.search_studies() if r.accession == "ACC1001")
    serie = repo.series_for_study(estudo.study_uid)[0]
    insts = sorted(repo.instances_for_series(serie.series_uid), key=lambda i: i["instance_number"])
    srv.app, srv.repo_, srv.fp, srv.tmp = app, repo, fp, tmp_path
    srv.estudo, srv.serie, srv.insts = estudo.study_uid, serie.series_uid, insts
    yield srv
    srv.stop()
    fp.stop()


def _token(srv, u="admin", p="admin123"):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/login", method="POST",
                                 data=json.dumps({"username": u, "password": p}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())["token"]


def _api(srv, rota, corpo=None, tok=None, cru=False):
    """O pedido numa linha à parte; a principal gira o laço (o desenho das folhas roda nela)."""
    tok = tok or _token(srv)
    caixa = {}

    def ir():
        req = urllib.request.Request(f"http://127.0.0.1:{srv.port}{rota}", method="POST" if corpo is not None else "GET",
                                     data=json.dumps(corpo).encode() if corpo is not None else None,
                                     headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        try:
            r = urllib.request.urlopen(req)
            caixa["r"] = (r.read(), r.headers.get("Content-Type"))
        except urllib.error.HTTPError as e:
            caixa["e"] = e
    t = threading.Thread(target=ir)
    t.start()
    while t.is_alive():
        srv.app.processEvents()
        time.sleep(0.01)
    if "e" in caixa:
        raise caixa["e"]
    corpo_r, tipo = caixa["r"]
    return (corpo_r, tipo) if cru else json.loads(corpo_r)


def _filme(srv, n=3, **kw):
    cells = [{"study_uid": srv.estudo, "series_uid": srv.serie, "sop_uid": i["sop_uid"], "frame_index": 0,
              "width": 400, "level": 40, "zoom": 1.5, "pan_x": 0.1, "pan_y": 0.0, "label": "teste"}
             for i in srv.insts[:n]]
    return {"name": "Filme web", "sheets": [{"rows": 2, "cols": 2, "paper": "A4", "landscape": False,
                                             "cells": cells + [None] * (4 - n)}], **kw}


def test_opcoes_previa_pdf_e_destinos(servidor):
    srv = servidor
    o = _api(srv, "/api/web/filme/opcoes")
    ids = [d["id"] for d in o["destinos"]]
    assert ids[:2] == ["baixar", "navegador"] and "dicom:Dry" in ids
    assert "dest:Pasta PDF" in ids and "dest:Pasta imagens" in ids
    assert "A4" in o["papeis"] and o["tamanhos"]["A4"] == [210, 297] and "2×2" in o["layouts"]
    png, tipo = _api(srv, "/api/web/filme/previa", {"film": _filme(srv), "folha": 0, "dpi": 40}, cru=True)
    assert tipo == "image/png" and png[:8] == b"\x89PNG\r\n\x1a\n"
    from PySide6.QtGui import QImage
    img = QImage.fromData(png)
    assert abs(img.width() - 210 / 25.4 * 40) < 3 and abs(img.height() - 297 / 25.4 * 40) < 3
    pdf, tipo = _api(srv, "/api/web/filme/pdf", {"film": _filme(srv)}, cru=True)
    assert tipo == "application/pdf" and pdf.startswith(b"%PDF")
    r = _api(srv, "/api/web/filme/imprimir", {"film": _filme(srv), "destino": "dest:Pasta PDF"})
    assert r["ok"] and list((srv.tmp / "pdfs").glob("*.pdf"))
    r = _api(srv, "/api/web/filme/imprimir", {"film": _filme(srv, 4), "destino": "dest:Pasta imagens"})
    assert len(list((srv.tmp / "imgs").glob("*.png"))) == 1
    # o filme conta no painel de filmes
    filmes = srv.repo_.films()
    assert any(f.get("name") == "Filme web" for f in filmes)
    assert srv.repo_.access_log(limit=10, action="imprimir", study_uid=srv.estudo)


def test_impressora_dicom(servidor):
    srv = servidor
    film = _filme(srv, 4)
    film["sheets"].append({"rows": 1, "cols": 1, "paper": "A4", "landscape": True,
                           "cells": [film["sheets"][0]["cells"][0]]})
    r = _api(srv, "/api/web/filme/imprimir", {"film": film, "destino": "dicom:Dry"})
    assert "2 folha(s)" in r["mensagem"] and len(srv.fp.printed) == 2
    assert srv.fp.film_boxes[1].FilmOrientation == "LANDSCAPE"
    r = _api(srv, "/api/web/filme/imprimir", {"film": film, "destino": "dicom:Dry", "folhas": [1]})
    assert "1 folha(s)" in r["mensagem"] and len(srv.fp.printed) == 3


def test_permissao_e_validacao(servidor):
    srv = servidor
    tok = _token(srv, "res", "resid123")
    for rota, corpo in (("/api/web/filme/opcoes", None), ("/api/web/filme/previa", {"film": _filme(srv)}),
                        ("/api/web/filme/imprimir", {"film": _filme(srv), "destino": "dest:Pasta PDF"})):
        with pytest.raises(urllib.error.HTTPError) as e:
            _api(srv, rota, corpo, tok)
        assert e.value.code == 403
    vazio = {"name": "x", "sheets": [{"rows": 1, "cols": 1, "cells": [None]}]}
    for corpo in ({"film": vazio}, {"film": _filme(srv), "destino": "dest:Nao existe"},
                  {"film": _filme(srv), "destino": "qualquer"}):
        with pytest.raises(urllib.error.HTTPError) as e:
            _api(srv, "/api/web/filme/imprimir", corpo)
        assert e.value.code == 400


def _esperar(srv, f, t=30.0):
    fim = time.time() + t
    while time.time() < fim:
        srv.app.processEvents()
        try:
            if f():
                return True
        except Exception:  # noqa: BLE001 - a página ainda montando
            pass
        time.sleep(0.05)
    return f()


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_pelo_navegador(servidor):
    pw = pytest.importorskip("playwright.sync_api")
    srv = servidor
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1500, "height": 950})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(f"http://127.0.0.1:{srv.port}/web/")
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        assert _esperar(srv, lambda: pg.locator("table.lista tbody tr").count() > 0)
        pg.evaluate(f"() => {{ location.hash = '#/exame/{srv.estudo}'; }}")
        assert _esperar(srv, lambda: pg.locator(".quadro canvas").count() > 0)
        pg.click(".abas button[data-aba='Filme']")
        assert _esperar(srv, lambda: pg.locator(".painel-filme button:has-text('+ Quadro ativo')").count() == 1, 30)
        # ajuste do quadro: janela, zoom 2 e um deslocamento
        pg.evaluate("""() => { const vp = window.__ipeGrade.viewport(0);
            vp.setProperties({ voiRange: { lower: -100, upper: 300 } }); vp.setZoom(vp.getZoom() * 2);
            const c = vp.getCamera(); vp.setCamera({ focalPoint: [c.focalPoint[0] + 5, c.focalPoint[1], c.focalPoint[2]],
              position: [c.position[0] + 5, c.position[1], c.position[2]] }); vp.render(); }""")
        pg.click(".painel-filme button:has-text('+ Quadro ativo')")
        assert _esperar(srv, lambda: pg.evaluate("() => document.querySelector('.previa-filme')?.naturalWidth || 0") > 0, 60)
        import os
        if os.environ.get("IPE_FILME_FOTO"):
            pg.select_option(".painel-filme select[aria-label='Grade']", "1×1")
            assert _esperar(srv, lambda: pg.evaluate("() => document.querySelector('.previa-filme')?.naturalWidth || 0") > 0, 60)
            time.sleep(1.5)
            for _ in range(20):
                srv.app.processEvents(); time.sleep(0.05)
            pg.locator(".quadro").first.screenshot(path=os.environ["IPE_FILME_FOTO"] + "_web.png")
            pg.locator(".previa-filme").screenshot(path=os.environ["IPE_FILME_FOTO"] + "_previa.png")
            pg.select_option(".painel-filme select[aria-label='Grade']", "2×2")
        cel = pg.evaluate("() => JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k => k.startsWith('ipe.web.filme.')))).celulas[0]")
        assert cel["width"] == 400 and cel["level"] == 100 and cel["sop_uid"]
        assert cel["zoom"] == pytest.approx(2.0, rel=0.05), cel
        assert cel["pan_x"] != 0
        # a célula de volta num quadro: o mesmo ajuste
        pg.evaluate("() => { const vp = window.__ipeGrade.viewport(0); vp.resetCamera(); vp.render(); }")
        pg.click(".previa-filme", position={"x": 60, "y": 90})
        assert _esperar(srv, lambda: pg.locator(".painel-filme button:has-text('Editar no quadro ativo')").count() == 1)
        pg.click(".painel-filme button:has-text('Editar no quadro ativo')")
        assert _esperar(srv, lambda: "Atualizar a célula" in pg.inner_text(".painel-filme .nota"))
        pg.click(".painel-filme button:has-text('Atualizar a célula')")
        assert _esperar(srv, lambda: True, 0.5)
        de_novo = pg.evaluate("() => JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k => k.startsWith('ipe.web.filme.')))).celulas[0]")
        for k in ("zoom", "pan_x", "pan_y", "width", "level"):
            assert de_novo[k] == pytest.approx(cel[k], abs=0.02), (k, de_novo, cel)
        # imprimir num destino do Ipê (PDF numa pasta)
        pg.select_option(".painel-filme select[aria-label='Saída']", "dest:Pasta PDF")
        pg.click(".painel-filme button.primario:has-text('Imprimir')")
        assert _esperar(srv, lambda: list((srv.tmp / "pdfs").glob("*.pdf")), 60)
        assert _esperar(srv, lambda: "arquivo(s)" in pg.inner_text(".painel-filme .nota"))
        b.close()
    assert not erros, erros
