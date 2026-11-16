"""0.100.58: na dinâmica do Ipê Web o médico escolhe as séries que entram na conta, o layout e o que vai em cada
quadro (fase, subtração, mapa ou qualquer série do exame); a subtração muda de fase no próprio quadro (◂ ▸); e a
ferramenta de correlação marca o ponto clicado nos outros quadros (como o Shift do Ipê de mesa)."""
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pytest
from pydicom.uid import MRImageStorage, generate_uid

sys.path.insert(0, str(Path(__file__).parent))
from _web_ui import ferramenta, icone, menu  # noqa: E402
from test_web_dinamica import NZ, PAT, PX, _token, servidor_din  # noqa: E402,F401
from test_web_mpr import _esperar  # noqa: E402

from ipe.central import web as WEB  # noqa: E402


def _din(srv, series=None):
    url = f"http://127.0.0.1:{srv.port}/api/web/dinamica?study={srv.estudo['uid']}"
    if series:
        url += "&series=" + ",".join(series)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {_token(srv)}"})
    return json.loads(urllib.request.urlopen(req).read())


def _por_t2(srv, tmp_path):
    """Uma série que não é da dinâmica: o dobro de cortes, a 1,5 mm (outra geometria)."""
    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    st = srv.estudo
    series = {"uid": generate_uid(), "number": 5, "description": "T2 STIR"}
    for k in range(NZ * 2):
        ds = _base(MRImageStorage, PAT, st, series, "MR")
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [0.0, 0.0, k * 1.5]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [PX, PX]
        ds.SliceThickness = 1.5
        ds.FrameOfReferenceUID = st["for"]
        _mono(ds, np.full((40, 40), 100 + k * 10, np.uint16), signed=False)
        _save(ds, tmp_path / "t2")
    Importer(srv.repo_.db, Path(srv.storage)).import_paths([tmp_path / "t2"])
    return series["uid"]


def _sagital(srv, tmp_path):
    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    st = srv.estudo
    series = {"uid": generate_uid(), "number": 6, "description": "T2 SAG"}
    for k in range(20):
        ds = _base(MRImageStorage, PAT, st, series, "MR")
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [k * 1.0, 0.0, 0.0]
        ds.ImageOrientationPatient = [0, 1, 0, 0, 0, 1]
        ds.PixelSpacing = [0.5, PX]
        ds.SliceThickness = 1.0
        ds.FrameOfReferenceUID = st["for"]
        _mono(ds, np.full((40, 40), 100 + k * 10, np.uint16), signed=False)
        _save(ds, tmp_path / "sag")
    Importer(srv.repo_.db, Path(srv.storage)).import_paths([tmp_path / "sag"])



def test_servidor_usa_as_series_escolhidas(servidor_din, tmp_path):
    t2 = _por_t2(servidor_din, tmp_path)
    d = _din(servidor_din)
    assert d["motivo"] == "" and len(d["fases"]) == 5 and not d["escolha_do_medico"]
    cands = [c["series"] for c in d["candidatas"]]
    assert len(cands) == 6 and cands[0] == t2                       # pela ordem do número da série
    assert t2 not in d["escolhidas"] and len(d["escolhidas"]) == 5
    # só a pré e as três primeiras pós (na ordem do número, qualquer que seja a ordem pedida)
    quatro = d["escolhidas"][:4]
    d4 = _din(servidor_din, list(reversed(quatro)))
    assert d4["motivo"] == "" and d4["escolha_do_medico"] and d4["escolhidas"] == quatro
    assert [f["quadros"][0]["series"] for f in d4["fases"]] == quatro
    # duas séries não fazem a dinâmica: o motivo, com as candidatas para escolher de novo
    d2 = _din(servidor_din, quatro[:2])
    assert d2["motivo"] and len(d2["candidatas"]) == 6 and d2["fases"] == []
    # série de outro exame não entra
    d0 = _din(servidor_din, ["1.2.3.4"])
    assert d0["motivo"] and d0["escolhidas"] == []


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_quadros_layout_series_e_ponto(servidor_din, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    t2 = _por_t2(servidor_din, tmp_path)
    d = _din(servidor_din)
    fase3 = d["escolhidas"][2]
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1600, "height": 950})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(f"http://127.0.0.1:{servidor_din.port}/web/")
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        pg.wait_for_selector("table.lista tbody tr")
        pg.locator("table.lista tbody tr").first.dblclick()
        pg.wait_for_selector(".quadro canvas")
        icone(pg, "Dinâmica da mama")
        assert _esperar(lambda: pg.locator(".camada-din").count() == 1, 30)
        est = lambda: pg.evaluate("() => window.__ipeDin.estado()")  # noqa: E731
        # o 4º quadro é a subtração da fase inicial — com ◂ ▸ para mudar a fase ali mesmo
        e = est()
        assert e["quadros"] == ["fase", "cin", "ser", "sub"]
        ini = e["par"]["inicial"]
        assert e["detalhe"][3]["sub"] and e["detalhe"][3]["fase"] == ini
        pg.click(".quadro >> nth=3 >> .rotulo-din button[aria-label^='Próxima fase']")
        assert _esperar(lambda: est()["detalhe"][3]["fase"] == ini + 1)
        assert "subtração" in est()["rotulos"][3]
        assert _esperar(lambda: pg.evaluate("() => window.__ipeGrade.viewport(3).getCurrentImageId()")
                        .startswith(f"ipedin:fs{ini + 1}p0:"))
        # um mapa vira subtração pelo menu do quadro (Mostrar ▸ Subtração), com ◂ ▸
        pg.click(".quadro >> nth=2 >> .rotulo-din .texto-rotulo")
        menu(pg, "Mostrar")
        menu(pg, "Subtração (fase − pré)")
        assert _esperar(lambda: est()["quadros"][2] == "sub")
        assert pg.locator(".quadro >> nth=2 >> .rotulo-din button[aria-label^='Fase anterior']").count() == 1
        # o layout: 2 × 3 — os quadros de antes ficam, os novos vêm de fábrica (a tardia, a subtração da tardia)
        pg.select_option(".barra-din select[aria-label='Layout da dinâmica']", label="2 × 3")
        assert _esperar(lambda: len(est()["quadros"]) == 6 and pg.locator(".quadro").count() == 6)
        e = est()
        assert e["layout"] == [2, 3] and e["quadros"][:4] == ["fase", "cin", "sub", "sub"]
        assert e["detalhe"][4]["fase"] == e["par"]["tardia"] and not e["detalhe"][4]["sub"]
        # uma série do exame que é fase da dinâmica vira a fase (com ◂ ▸)
        pg.click(".quadro >> nth=1 >> .rotulo-din .texto-rotulo")
        menu(pg, "Mostrar")
        menu(pg, "Séries do exame")
        menu(pg, "Se 12 · T1 DIN 3")
        assert _esperar(lambda: est()["detalhe"][1]["v"] == "fase" and est()["detalhe"][1]["fase"] == 2)
        # e uma que não é (o T2, com outra geometria): anda junto pela posição
        pg.click(".quadro >> nth=5 >> .rotulo-din .texto-rotulo")
        menu(pg, "Mostrar")
        menu(pg, "Séries do exame")
        menu(pg, "Se 5 · T2 STIR")
        assert _esperar(lambda: est()["detalhe"][5]["v"] == "serie" and est()["detalhe"][5]["serie"] == t2)
        assert "T2 STIR" in est()["rotulos"][5]
        assert pg.locator(".quadro >> nth=5 >> .rotulo-din button[aria-label^='Próxima fase']").count() == 0
        idx = lambda i: pg.evaluate(f"() => window.__ipeGrade.viewport({i}).getCurrentImageIdIndex()")  # noqa: E731
        pg.evaluate("() => window.__ipeGrade.viewport(0).setImageIdIndex(1)")       # z = 3 mm → T2 corte 2
        assert _esperar(lambda: idx(5) == 2 and idx(4) == 1)
        pg.evaluate("() => window.__ipeGrade.viewport(5).setImageIdIndex(8)")       # z = 12 mm → dinâmica corte 4
        assert _esperar(lambda: idx(0) == 4 and idx(3) == 4)
        assert idx(5) == 8                                                         # sem eco: o T2 fica onde está
        # a correlação: clicar com a ferramenta marca o ponto em todos os quadros que passam por ele
        ferramenta(pg, "linhas")
        pt = pg.evaluate("""() => { const vp = window.__ipeGrade.viewport(0); const id = vp.getCurrentImageId();
            const r = vp.canvas.getBoundingClientRect();
            const c = vp.worldToCanvas(window.__ipeCs.imageToWorldCoords(id, [12.5, 12.5]));
            return [r.left + c[0], r.top + c[1]]; }""")
        pg.mouse.click(*pt)
        assert _esperar(lambda: pg.locator("canvas.ponto-marcado[data-ponto='1']").count() == 6)
        # a cruz cai no mesmo pixel da imagem nos outros quadros
        noutro = pg.evaluate("""() => { const c = document.querySelectorAll('.quadro')[3].querySelector('canvas.ponto-marcado');
            const vp = window.__ipeGrade.viewport(3); const ij = window.__ipeCs.worldToImageCoords(vp.getCurrentImageId(),
            vp.canvasToWorld([Number(c.dataset.x), Number(c.dataset.y)])); return ij; }""")
        assert noutro[0] == pytest.approx(12.5, abs=1) and noutro[1] == pytest.approx(12.5, abs=1)
        import os
        if os.environ.get("IPE_DIN_FOTO"):
            pg.screenshot(path=os.environ["IPE_DIN_FOTO"])
        # rolar para longe do ponto apaga a cruz; Esc tira
        pg.evaluate("() => window.__ipeGrade.viewport(0).setImageIdIndex(0)")
        assert _esperar(lambda: pg.locator("canvas.ponto-marcado[data-ponto='1']").count() == 0)
        pg.evaluate("() => window.__ipeGrade.viewport(0).setImageIdIndex(4)")
        assert _esperar(lambda: pg.locator("canvas.ponto-marcado[data-ponto='1']").count() == 6)
        pg.keyboard.press("Escape")
        assert _esperar(lambda: pg.locator("canvas.ponto-marcado[data-ponto='1']").count() == 0)
        # as séries da dinâmica: o médico tira uma pós e a dinâmica abre de novo com quatro fases
        pg.click(".barra-din button[aria-label='Séries da dinâmica']")
        pg.wait_for_selector(".escolha-series-din")
        assert pg.locator(".escolha-series-din input[type=checkbox]").count() == 6
        assert not pg.is_checked(f".escolha-series-din input[value='{t2}']")
        pg.uncheck(f".escolha-series-din input[value='{d['escolhidas'][4]}']")
        pg.click(".escolha-series-din button:has-text('Usar estas séries')")
        assert _esperar(lambda: pg.evaluate("() => window.__ipeDin && window.__ipeDin.estado().par.tempos.length") == 4, 30)
        assert _esperar(lambda: pg.locator(".barra-din").count() == 1)
        # e com séries que não servem, a lista volta para escolher de novo
        pg.click(".barra-din button[aria-label='Séries da dinâmica']")
        for c in pg.locator(".escolha-series-din input[type=checkbox]").all():
            c.uncheck()
        pg.check(f".escolha-series-din input[value='{fase3}']")
        pg.check(f".escolha-series-din input[value='{t2}']")
        pg.click(".escolha-series-din button:has-text('Usar estas séries')")
        assert _esperar(lambda: pg.locator(".escolha-series-din").count() == 1 and pg.locator(".barra-din").count() == 0, 30)
        assert "Dinâmica:" in pg.inner_text(".area")
        pg.click(".escolha-series-din button:has-text('Detectar sozinho')")
        assert _esperar(lambda: pg.evaluate("() => window.__ipeDin && window.__ipeDin.estado().par.tempos.length") == 5, 30)
        b.close()
    assert not erros, erros


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_serie_de_outro_plano_nao_volta_ao_rolar(servidor_din, tmp_path):
    """0.100.59: uma série sagital num quadro da dinâmica axial: o clique das linhas de referência a leva ao ponto, e
    rolar a dinâmica não a devolve (de outro plano ela não anda pela rolagem); rolar a sagital não mexe na dinâmica."""
    pw = pytest.importorskip("playwright.sync_api")
    _sagital(servidor_din, tmp_path)
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1600, "height": 950})
        pg.goto(f"http://127.0.0.1:{servidor_din.port}/web/")
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        pg.wait_for_selector("table.lista tbody tr")
        pg.locator("table.lista tbody tr").first.dblclick()
        pg.wait_for_selector(".quadro canvas")
        icone(pg, "Dinâmica da mama")
        assert _esperar(lambda: pg.locator(".camada-din").count() == 1, 30)
        pg.click(".quadro >> nth=3 >> .rotulo-din .texto-rotulo")
        menu(pg, "Mostrar")
        menu(pg, "Séries do exame")
        menu(pg, "Se 6 · T2 SAG")
        assert _esperar(lambda: pg.evaluate("() => window.__ipeDin.estado().detalhe[3].v") == "serie")
        idx = lambda: [pg.evaluate(f"() => window.__ipeGrade.viewport({i}).getCurrentImageIdIndex()") for i in range(4)]  # noqa: E731
        ferramenta(pg, "linhas")
        box = pg.locator(".quadro").nth(0).bounding_box()
        cx, cy = box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.6
        pg.mouse.click(cx, cy)
        assert _esperar(lambda: idx()[3] not in (-1, 19))
        sag = idx()[3]
        for _ in range(3):
            pg.mouse.wheel(0, 120)
            pg.wait_for_timeout(300)
        assert _esperar(lambda: idx()[0] != 3)
        pg.wait_for_timeout(500)
        i = idx()
        assert i[0] == i[1] == i[2] and i[3] == sag, i
        box = pg.locator(".quadro").nth(3).bounding_box()
        pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        for _ in range(2):
            pg.mouse.wheel(0, 120)
            pg.wait_for_timeout(300)
        assert _esperar(lambda: idx()[3] != sag)
        pg.wait_for_timeout(500)
        assert idx()[:3] == i[:3]
        b.close()
