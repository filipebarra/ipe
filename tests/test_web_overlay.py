"""0.100.2: overlay no visualizador web — o botão que liga e desliga o CAD/IA (SR), as anotações de outro sistema
(GSPS) e os contornos RTSTRUCT, lidos no servidor com o leitor do Ipê; os textos dos cantos; e as linhas de
referência entre as pilhas (o plano do quadro ativo cortando o scout) com o localizador (clicar no scout leva o axial
ao corte do ponto)."""
import json
import sys
import urllib.request
from pathlib import Path

import pydicom
import pytest
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence
from pydicom.uid import generate_uid

sys.path.insert(0, str(Path(__file__).parent))
from _web_ui import ferramenta, layout  # noqa: E402
from test_onco import _cad_sr  # noqa: E402
from test_web_mpr import DZ, NZ, PX, _esperar, servidor  # noqa: E402,F401  (fixture)

from ipe.central import web as WEB  # noqa: E402
from ipe.imaging import overlays as O  # noqa: E402

K = 20                       # o corte do axial com os objetos


def _preparar(srv, env, tmp_path):
    from ipe.core.sample_data import _base, _save
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    st = repo.search_studies()[0]
    study = st.study_uid
    ax = next(r for r in repo.series_for_study(study) if r.description == "AX 2.5")
    insts = sorted(repo.instances_for_series(ax.series_uid), key=lambda i: int(i.get("instance_number") or 0))
    alvo = pydicom.dcmread(insts[K]["path"], stop_before_pixels=True)
    sop = str(alvo.SOPInstanceUID)
    pat = {"name": str(alvo.PatientName), "id": str(alvo.PatientID), "birth": str(alvo.PatientBirthDate), "sex": "F"}
    est = {"uid": study, "date": str(alvo.StudyDate), "accession": str(alvo.AccessionNumber),
           "description": str(alvo.StudyDescription)}
    pasta = tmp_path / "ov"
    # GSPS de outro sistema: uma linha e um texto no corte K
    ds = _base("1.2.840.10008.5.1.4.1.1.11.1", pat, est, {"uid": generate_uid(), "number": 90, "description": "PACS X"}, "PR")
    ga = Dataset()
    ri = Dataset()
    ri.ReferencedSOPClassUID, ri.ReferencedSOPInstanceUID = alvo.SOPClassUID, sop
    ga.ReferencedImageSequence = Sequence([ri])
    go = Dataset()
    go.GraphicAnnotationUnits, go.GraphicType, go.GraphicData = "PIXEL", "POLYLINE", [10.0, 10.0, 30.0, 30.0]
    go.GraphicDimensions, go.NumberOfGraphicPoints, go.GraphicFilled = 2, 2, "N"
    to = Dataset()
    to.UnformattedTextValue, to.AnchorPoint, to.AnchorPointAnnotationUnits = "Achado X", [20.0, 20.0], "PIXEL"
    ga.GraphicObjectSequence = Sequence([go])
    ga.TextObjectSequence = Sequence([to])
    ga.GraphicLayer = "L1"
    ds.GraphicAnnotationSequence = Sequence([ga])
    _save(ds, pasta)
    # CAD em SR (o achado com o círculo) no mesmo corte
    sr = _cad_sr(sop, study)
    base = _base(sr.SOPClassUID, pat, est, {"uid": generate_uid(), "number": 91, "description": "CAD IA"}, "SR")
    for el in sr:
        base[el.tag] = el
    base.SOPInstanceUID = base.file_meta.MediaStorageSOPInstanceUID
    _save(base, pasta)
    # RTSTRUCT: um quadrado no plano do corte K
    rt = _base(O.RTSTRUCT_CLASS, pat, est, {"uid": generate_uid(), "number": 92, "description": "RT"}, "RTSTRUCT")
    r = Dataset()
    r.ROINumber, r.ROIName = 1, "GTV"
    rt.StructureSetROISequence = Sequence([r])
    rc = Dataset()
    rc.ReferencedROINumber, rc.ROIDisplayColor = 1, [255, 0, 0]
    c = Dataset()
    z = K * DZ
    c.ContourGeometricType = "CLOSED_PLANAR"
    c.ContourData = [40, 40, z, 80, 40, z, 80, 80, z, 40, 80, z]
    rc.ContourSequence = Sequence([c])
    rt.ROIContourSequence = Sequence([rc])
    _save(rt, pasta)
    Importer(db, paths.storage).import_paths([pasta])
    return study, sop


def _token(srv):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/login", method="POST",
                                 data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())["token"]


def test_objetos_no_servidor(servidor, env, tmp_path):
    study, sop = _preparar(servidor, env, tmp_path)
    req = urllib.request.Request(f"http://127.0.0.1:{servidor.port}/api/web/overlays?study={study}",
                                 headers={"Authorization": f"Bearer {_token(servidor)}"})
    d = json.loads(urllib.request.urlopen(req).read())
    fontes = sorted(o["fonte"] for o in d["objetos"])
    assert fontes == ["CAD", "GSPS", "RTSTRUCT"], fontes
    gsps = next(o for o in d["objetos"] if o["fonte"] == "GSPS")
    tipos = sorted(g["tipo"] for g in gsps["por_sop"][sop])
    assert tipos == ["polyline", "text"]
    linha = next(g for g in gsps["por_sop"][sop] if g["tipo"] == "polyline")
    assert linha["pontos"] == [[10.0, 10.0], [30.0, 30.0]]
    cad = next(o for o in d["objetos"] if o["fonte"] == "CAD")
    assert any("Mass" in a for a in cad["achados"]) and cad["por_sop"][sop][0]["tipo"] == "polygon"
    rt = next(o for o in d["objetos"] if o["fonte"] == "RTSTRUCT")
    assert rt["planos"][0]["pontos3d"][0] == [40.0, 40.0, K * DZ] and rt["achados"] == ["GTV"]
    assert d["tipos"]["SR"] and d["ocultos"] == []


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_overlay_e_linhas_no_navegador(servidor, env, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    _preparar(servidor, env, tmp_path)
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1500, "height": 950})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(f"http://127.0.0.1:{servidor.port}/web/")
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        pg.wait_for_selector("table.lista tbody tr")
        pg.locator("table.lista tbody tr").first.dblclick()
        pg.wait_for_selector(".quadro canvas")
        assert _esperar(lambda: "AX 2.5" in pg.locator(".quadro").first.inner_text())
        ov = lambda: pg.evaluate("() => window.__ipeOverlay.estado()")  # noqa: E731
        assert _esperar(lambda: len(ov()["objetos"]) == 3)
        # no corte K, os três objetos (GSPS: linha e texto; CAD; o contorno RTSTRUCT)
        pg.evaluate(f"() => window.__ipeGrade.viewport(0).setImageIdIndex({K})")
        assert _esperar(lambda: ov()["desenhados"][0] == 4), ov()
        # outro corte: nada
        pg.evaluate("() => window.__ipeGrade.viewport(0).setImageIdIndex(3)")
        assert _esperar(lambda: ov()["desenhados"][0] == 0), ov()
        pg.evaluate(f"() => window.__ipeGrade.viewport(0).setImageIdIndex({K})")
        assert _esperar(lambda: ov()["desenhados"][0] == 4)
        # o botão desliga tudo: o CAD, os textos dos cantos
        pg.click("nav.barra button[aria-label='Overlay (CAD/IA, textos, medidas)']")
        assert _esperar(lambda: ov()["desenhados"][0] == 0 and not ov()["ligado"])
        assert not pg.locator(".quadro .textos").first.is_visible()
        pg.click("nav.barra button[aria-label='Overlay (CAD/IA, textos, medidas)']")
        assert _esperar(lambda: ov()["desenhados"][0] == 4 and ov()["ligado"])
        assert pg.locator(".quadro .textos").first.is_visible()
        # pela seta: esconder só o GSPS (e fica lembrado)
        pg.click("nav.barra button[aria-label='Opções do overlay']")
        pg.locator(".menu .menu-item", has_text="Anotações de outro sistema").first.click()
        assert _esperar(lambda: ov()["desenhados"][0] == 2 and ov()["ocultos"] == ["GSPS"])
        assert pg.evaluate("() => localStorage.getItem('ipe.web.overlayOcultos')") == '["GSPS"]'
        # linhas de referência: o axial e o scout (coronal) lado a lado; o plano do quadro ativo corta o outro
        layout(pg, "1x2")
        pg.locator(".quadro").nth(1).click()
        pg.click(".series button.serie[title='SCOUT']")
        assert _esperar(lambda: "SCOUT" in pg.locator(".quadro").nth(1).inner_text())
        pg.locator(".quadro").nth(0).click(position={"x": 5, "y": 300})
        linhas_no_scout = "() => document.querySelectorAll('.quadro:nth-child(2) svg line, .quadro:nth-child(2) svg polyline').length"
        assert _esperar(lambda: pg.evaluate(linhas_no_scout) >= 1), pg.evaluate(linhas_no_scout)
        # desligar pelas opções
        pg.click("nav.barra button[aria-label='Opções do overlay']")
        pg.locator(".menu .menu-item", has_text="Linhas de referência").first.click()
        assert _esperar(lambda: pg.evaluate(linhas_no_scout) == 0 and not ov()["linhas"])
        pg.click("nav.barra button[aria-label='Opções do overlay']")
        pg.locator(".menu .menu-item", has_text="Linhas de referência").first.click()
        assert _esperar(lambda: ov()["linhas"])
        # o localizador: clicar no scout leva o axial ao corte do ponto
        ferramenta(pg, "linhas")
        alvo = pg.evaluate(f"""() => {{ const vp = window.__ipeGrade.viewport(1);
            return vp.worldToCanvas([60, 0, {30 * DZ}]); }}""")
        caixa = pg.locator(".quadro .tela").nth(1).bounding_box()
        pg.mouse.click(caixa["x"] + alvo[0], caixa["y"] + alvo[1])
        assert _esperar(lambda: pg.evaluate("() => window.__ipeGrade.viewport(0).getCurrentImageIdIndex()") == 30)
        b.close()
    assert not erros, erros
    assert NZ > 30 and PX
