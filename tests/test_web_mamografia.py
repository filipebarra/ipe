"""0.99.98 (W4): mamografia no visualizador web, com uma e duas telas. O servidor resolve o protocolo do Ipê
(imaging/mammo.py) — a imagem de cada quadro, o exame anterior, o espelho para a parede torácica ficar no centro,
a caixa da mama e o mamilo — e o navegador põe a câmera. Com duas telas, a segunda janela abre e as duas
mudam de etapa juntas."""
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pytest
from pydicom.uid import DigitalMammographyXRayImageStorageForPresentation as MG_SOP
from pydicom.uid import generate_uid

sys.path.insert(0, str(Path(__file__).parent))
from test_web_mpr import _esperar  # noqa: E402

from ipe.central import web as WEB  # noqa: E402

TOMO_SOP = "1.2.840.10008.5.1.4.1.1.13.1.3"
H, W = 512, 400
PAT = {"name": "EXEMPLO^MAMOGRAFIA", "id": "MGWEB1", "birth": "19700101", "sex": "F"}


def _mama(lado: str, parede: str, largura=0.42, brilho=900.0) -> np.ndarray:
    """MG sintética: a mama encostada na borda `parede` ("left"/"right"), o resto é ar."""
    img = np.full((H, W), 30.0)
    yy, xx = np.mgrid[0:H, 0:W]
    bw = int(W * largura)
    cx = 0 if parede == "left" else W - 1
    cy = H * (0.45 if lado == "R" else 0.55)                 # mamilos em alturas diferentes
    r = np.sqrt(((xx - cx) / bw) ** 2 + ((yy - cy) / (H * 0.40)) ** 2)
    m = r <= 1.0
    img[m] = brilho + 120 * np.sin(xx[m] / 11) * np.cos(yy[m] / 13)
    return img


def _serie(out, study, lado, view, numero, parede, tomo=False):
    from ipe.core.sample_data import _base, _mono, _save
    series = {"uid": generate_uid(), "number": numero, "description": f"{view}{'D' if lado == 'R' else 'E'}"
              + (" TOMO" if tomo else "")}
    ds = _base(TOMO_SOP if tomo else MG_SOP, PAT, study, series, "MG")
    ds.InstanceNumber = 1
    ds.ImageLaterality = lado
    ds.ViewPosition = view
    ds.PixelSpacing = [0.1, 0.1]
    ds.ImagerPixelSpacing = [0.1, 0.1]
    ds.PresentationIntentType = "FOR PRESENTATION"
    img = _mama(lado, parede)
    if tomo:
        cortes = np.stack([img * (0.8 + 0.02 * k) for k in range(9)])
        _mono(ds, cortes[0], signed=False)
        ds.NumberOfFrames = len(cortes)
        ds.PixelData = cortes.astype(np.uint16).tobytes()
    else:
        _mono(ds, img, signed=False)
    return _save(ds, out)


@pytest.fixture()
def servidor_mg(env, tmp_path):
    from ipe.auth.backend import LocalAuth
    from ipe.central.server import CentralServer
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    atual = {"uid": generate_uid(), "date": "20261108", "accession": "MGW2", "description": "MAMOGRAFIA DIGITAL",
             "for": generate_uid()}
    anterior = {"uid": generate_uid(), "date": "20251020", "accession": "MGW1", "description": "MAMOGRAFIA DIGITAL",
                "for": generate_uid()}
    d = tmp_path / "mg"
    # o exame de hoje: a direita com a parede à direita (como deve ficar), a esquerda com a parede à direita
    # também (precisa espelhar); e a tomossíntese da CC direita
    for k, (lado, view, parede) in enumerate((("R", "CC", "right"), ("L", "CC", "right"),
                                              ("R", "MLO", "right"), ("L", "MLO", "left"))):
        _serie(d / "atual", atual, lado, view, k + 1, parede)
    _serie(d / "atual", atual, "R", "CC", 9, "right", tomo=True)
    for k, (lado, view) in enumerate((("R", "CC"), ("L", "CC"), ("R", "MLO"), ("L", "MLO"))):
        _serie(d / "anterior", anterior, lado, view, k + 1, "right" if lado == "R" else "left")
    Importer(db, paths.storage).import_paths([d])
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    srv.estudos = (atual["uid"], anterior["uid"])
    yield srv
    srv.stop()


def _token(srv):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/login", method="POST",
                                 data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())["token"]


def _mg(srv, study, token, extra=""):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/web/mamografia?study={study}{extra}",
                                 headers={"Authorization": f"Bearer {token}"})
    return json.loads(urllib.request.urlopen(req).read())


def test_protocolo_resolvido_no_servidor(servidor_mg):
    atual, anterior = servidor_mg.estudos
    r = _mg(servidor_mg, atual, _token(servidor_mg))
    assert r["protocolo"] == "Mamografia (4 incidências, com anterior)"
    assert [p["nome"] for p in r["passos"]][:3] == ["4 incidências", "CC", "MLO"]
    assert r["anteriores"] == [{"n": 1, "study": anterior, "data": "20251020"}]
    quatro = r["passos"][0]["telas"]
    # uma tela: 2 × 2; duas telas: uma linha em cada (as CC numa, as MLO na outra)
    assert (quatro["1"][0]["rows"], quatro["1"][0]["cols"]) == (2, 2)
    assert [(t["rows"], t["cols"]) for t in quatro["2"]] == [(1, 2), (1, 2)]
    assert [c["codigo"] for c in quatro["2"][0]["celulas"]] == ["CCD", "CCE"]
    assert [c["codigo"] for c in quatro["2"][1]["celulas"]] == ["MLOD", "MLOE"]
    cel = quatro["1"][0]["celulas"]
    # costas com costas: a direita com a parede à direita, a esquerda à esquerda
    assert [c["quer"] for c in cel] == ["right", "left", "right", "left"]
    im = {c["codigo"]: r["imagens"][c["sop"]] for c in cel}
    assert im["CCD"]["parede"] == "right" and im["CCE"]["parede"] == "right"   # a CCE espelha
    assert im["MLOE"]["parede"] == "left"
    for x in im.values():
        assert (x["largura"], x["altura"]) == (W, H)
        x0, y0, x1, y1 = x["caixa"]
        assert x1 - x0 < W * 0.6                       # a caixa da mama descarta o ar
        assert x["mamilo"] is not None
    assert im["CCD"]["mamilo"][0] == pytest.approx(W * 0.58, abs=8)   # parede à direita: o mamilo à esquerda dela
    # a 2D da CC direita tem a tomossíntese como alternativa
    assert r["imagens"][cel[0]["alt"]]["tomo"] and r["imagens"][cel[0]["alt"]]["quadros"] == 9
    assert r["imagens"][cel[0]["alt"]]["inicio"] == 4
    # a etapa "CC atual × anterior" puxa o exame anterior
    cc_ant = next(p for p in r["passos"] if p["nome"] == "CC atual × anterior")["telas"]["1"][0]["celulas"]
    assert [r["imagens"][c["sop"]]["study"] for c in cc_ant] == [atual, atual, anterior, anterior]
    assert cc_ant[2]["data"] == "20251020"


def test_sem_anterior_e_exame_que_nao_e_mg(servidor_mg):
    atual, anterior = servidor_mg.estudos
    tk = _token(servidor_mg)
    r = _mg(servidor_mg, anterior, tk)
    cc_ant = next(p for p in r["passos"] if p["nome"] == "CC atual × anterior")["telas"]["1"][0]["celulas"]
    assert "sop" not in cc_ant[2] and "sem exame anterior" in cc_ant[2]["nota"]
    # escolher o protocolo pelo número (o de CEM também casa com qualquer exame quando escolhido à mão)
    r2 = _mg(servidor_mg, atual, tk, "&protocolo=0")
    assert r2["indice"] == 0 and r2["protocolo"].startswith("Mamografia com contraste")
    assert _mg(servidor_mg, "1.2.3.4", tk)["protocolo"] is None      # exame que não é de mamografia


def test_analise_guardada():
    """A mesma imagem não é lida duas vezes (o protocolo passa por ela em várias etapas)."""
    assert hasattr(WEB, "_ANALISE")


# ------------------------------------------------------------------ no navegador
def _abrir(pg, srv, study):
    pg.goto(f"http://127.0.0.1:{srv.port}/web/")
    pg.fill("#usuario", "admin")
    pg.fill("#senha", "admin123")
    pg.click("button[type=submit]")
    pg.wait_for_selector("table.lista tbody tr")
    pg.evaluate(f"() => {{ location.hash = '#/exame/{study}'; }}")
    pg.wait_for_selector(".barra-mg")


def _celulas(pg):
    return pg.evaluate("() => window.__ipeMg.estado()")


def _prontas(pg, n):
    return _esperar(lambda: (lambda e: len(e["quadros"]) == n and all(q["pronto"] for q in e["quadros"]))(_celulas(pg)), 60)


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_mamografia_uma_tela(servidor_mg):
    pw = pytest.importorskip("playwright.sync_api")
    atual, anterior = servidor_mg.estudos
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        _abrir(pg, servidor_mg, atual)
        assert _prontas(pg, 4)
        e = _celulas(pg)
        assert e["passo"] == 0 and e["telas"] == 1 and e["nome"] == "4 incidências"
        q = {x["codigo"]: x for x in e["quadros"]}
        # a CCE veio com a parede à direita: espelhou; a CCD e a MLOE não
        assert q["CCE"]["espelhado"] and not q["CCD"]["espelhado"] and not q["MLOE"]["espelhado"]
        # a parede encostada na borda certa da tela (CCD à direita, CCE à esquerda), sem o ar no meio
        assert q["CCD"]["parede_x"] == pytest.approx(1.0, abs=0.02)
        assert q["CCE"]["parede_x"] == pytest.approx(0.0, abs=0.02)
        # zoom junto: as duas da mesma linha na mesma escala; e a mama ocupa o quadro (mais que o ajuste)
        assert q["CCD"]["escala"] == pytest.approx(q["CCE"]["escala"], rel=0.01)
        assert q["CCD"]["zoom"] > 1.1
        # alinhadas pelo mamilo: na mesma altura da tela
        assert q["CCD"]["mamilo_y"] == pytest.approx(q["CCE"]["mamilo_y"], abs=0.02)
        assert "4 incidências" in pg.inner_text(".barra-mg")
        # próxima etapa: CC (1 × 2)
        pg.click(".barra-mg button[aria-label='Próxima etapa']")
        assert _prontas(pg, 2)
        assert [x["codigo"] for x in _celulas(pg)["quadros"]] == ["CCD", "CCE"]
        # escolher a etapa pela lista: CC atual × anterior
        pg.click(".barra-mg button.etapa")
        pg.locator(".menu .menu-item:has-text('CC atual × anterior')").click()
        assert _prontas(pg, 4)
        e = _celulas(pg)
        assert [x["study"] for x in e["quadros"]] == [atual, atual, anterior, anterior]
        assert "2025" in pg.inner_text(".quadro >> nth=2")
        # tomossíntese no quadro da CCD: vira a pilha de cortes no meio
        for _ in range(3):
            pg.click(".barra-mg button[aria-label='Etapa anterior']")
        assert _esperar(lambda: _celulas(pg)["passo"] == 0)
        assert _prontas(pg, 4)
        pg.locator(".quadro").nth(0).click()
        pg.click(".barra-mg button[aria-label='Tomossíntese do quadro']")
        assert _esperar(lambda: _celulas(pg)["quadros"][0]["cortes"] == 9 and _celulas(pg)["quadros"][0]["pronto"])
        assert _celulas(pg)["quadros"][0]["corte"] == 4
        # duplo clique amplia o quadro; outro duplo clique volta
        pg.locator(".quadro").nth(1).dblclick()
        assert _esperar(lambda: pg.locator(".quadro:visible").count() == 1)
        assert _esperar(lambda: _celulas(pg)["quadros"][1]["parede_x"] == pytest.approx(0.0, abs=0.02))
        pg.locator(".quadro").nth(1).dblclick()
        assert _esperar(lambda: pg.locator(".quadro:visible").count() == 4)
        # sair do modo mamografia: volta ao visualizador comum
        pg.click(".barra-mg button[aria-label='Sair do modo mamografia']")
        assert _esperar(lambda: pg.locator(".barra-mg").count() == 0)
        b.close()
    assert not erros, erros


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_mamografia_duas_telas(servidor_mg):
    pw = pytest.importorskip("playwright.sync_api")
    atual, _anterior = servidor_mg.estudos
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        ctx = b.new_context(viewport={"width": 1200, "height": 800})
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: erros.append(str(e)))
        _abrir(pg, servidor_mg, atual)
        assert _prontas(pg, 4)
        with ctx.expect_page() as nova:
            pg.click(".barra-mg button[aria-label='Duas telas']")
        p2 = nova.value
        p2.on("pageerror", lambda e: erros.append("2: " + str(e)))
        # a segunda janela entra sem pedir a senha (o token vem da primeira) e mostra a outra metade da etapa
        p2.wait_for_selector(".barra-mg", timeout=30000)
        assert _prontas(pg, 2) and _prontas(p2, 2)
        assert [x["codigo"] for x in _celulas(pg)["quadros"]] == ["CCD", "CCE"]
        assert [x["codigo"] for x in _celulas(p2)["quadros"]] == ["MLOD", "MLOE"]
        assert _celulas(p2)["tela"] == 2 and _celulas(p2)["telas"] == 2
        assert p2.locator("#senha").count() == 0
        # mudar a etapa numa janela muda a outra
        pg.click(".barra-mg button[aria-label='Próxima etapa']")
        assert _esperar(lambda: _celulas(p2)["passo"] == 1)
        # etapa CC (1 × 2) em duas telas: uma imagem em cada
        assert _prontas(pg, 1) and _prontas(p2, 1)
        assert [x["codigo"] for x in _celulas(pg)["quadros"]] == ["CCD"]
        assert [x["codigo"] for x in _celulas(p2)["quadros"]] == ["CCE"]
        # com uma imagem por tela, a parede continua voltada para o centro do conjunto
        assert _celulas(pg)["quadros"][0]["parede_x"] == pytest.approx(1.0, abs=0.02)
        assert _celulas(p2)["quadros"][0]["parede_x"] == pytest.approx(0.0, abs=0.02)
        p2.click(".barra-mg button[aria-label='Próxima etapa']")
        assert _esperar(lambda: _celulas(pg)["passo"] == 2)
        # fechar a segunda: a primeira volta a uma tela
        p2.close()
        assert _esperar(lambda: _celulas(pg)["telas"] == 1)
        assert _prontas(pg, 2)
        b.close()
    assert not erros, erros
