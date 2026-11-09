from pathlib import Path
import sys
"""0.99.93 (W2): medidas no visualizador web — o número do Ipê (escala, ROI, texto), gravadas no banco no formato
do Ipê (aparecem no Ipê; as do Ipê aparecem no site), com quem fez; calibração do ultrassom pelas regiões e à mão."""
import json
import re
import time

import numpy as np
import pytest

from ipe.central import web as WEB  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from _web_ui import aba, botoes, espessura, ferramenta, icone, layout, menu, quadros  # noqa: E402,F401

pytestmark = pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")

PX = 0.7


def _ct():
    a = np.zeros((128, 128), np.int16)
    a[30:90, 40:100] = 100
    a[60:70, 60:70] = 300
    return a


def _us():
    a = (np.arange(200 * 300, dtype=np.uint16).reshape(200, 300) % 200).astype(np.uint8)
    return a


@pytest.fixture()
def servidor(env, tmp_path):
    from pydicom.dataset import Dataset
    from pydicom.sequence import Sequence
    from pydicom.uid import generate_uid

    from ipe.auth.backend import LocalAuth
    from ipe.central.server import CentralServer
    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    pat = {"name": "MEDIDA^TESTE", "id": "MED1", "birth": "19700101", "sex": "F"}
    st1 = {"uid": generate_uid(), "date": "20261108", "accession": "MEDCT", "description": "TC ABDOME",
           "for": generate_uid()}
    se1 = {"uid": generate_uid(), "number": 2, "description": "AX"}
    ds = _base("1.2.840.10008.5.1.4.1.1.2", pat, st1, se1, "CT")
    ds.ImagePositionPatient, ds.ImageOrientationPatient, ds.PixelSpacing = [0, 0, 0], [1, 0, 0, 0, 1, 0], [PX, PX]
    ds.RescaleSlope, ds.RescaleIntercept, ds.WindowCenter, ds.WindowWidth = 1, 0, 100, 400
    _mono(ds, _ct(), signed=True)
    _save(ds, tmp_path / "d")
    ct_sop = str(ds.SOPInstanceUID)
    st2 = {"uid": generate_uid(), "date": "20261108", "accession": "MEDUS", "description": "US ABDOME",
           "for": generate_uid()}
    se2 = {"uid": generate_uid(), "number": 1, "description": "US"}
    us = _base("1.2.840.10008.5.1.4.1.1.6.1", pat, st2, se2, "US")
    _mono(us, _us(), signed=False)

    def regiao(x0, y0, x1, y1, ux, uy, dx, dy, tipo):
        r = Dataset()
        r.RegionSpatialFormat, r.RegionDataType, r.RegionFlags = 1, tipo, 0
        r.RegionLocationMinX0, r.RegionLocationMinY0, r.RegionLocationMaxX1, r.RegionLocationMaxY1 = x0, y0, x1, y1
        r.PhysicalUnitsXDirection, r.PhysicalUnitsYDirection = ux, uy
        r.PhysicalDeltaX, r.PhysicalDeltaY = dx, dy
        return r
    # 2D (cm, 0,01 cm/px = 0,1 mm/px) à esquerda; Doppler (s × cm/s) embaixo à direita: não é régua
    us.SequenceOfUltrasoundRegions = Sequence([regiao(0, 0, 149, 199, 3, 3, 0.01, 0.01, 1),
                                               regiao(150, 100, 299, 199, 4, 7, 0.005, 0.5, 3)])
    _save(us, tmp_path / "d")
    us_sop = str(us.SOPInstanceUID)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    # uma medida feita no Ipê (a régua de 20 px) e uma ROI livre: têm de aparecer no site
    repo.save_annotation(db_id=None, study_uid=st1["uid"], series_uid=se1["uid"], sop_uid=ct_sop, frame_index=0,
                         kind="line", data=json.dumps({"points": [[10, 110], [30, 110]], "text": ""}))
    repo.save_annotation(db_id=None, study_uid=st1["uid"], series_uid=se1["uid"], sop_uid=ct_sop, frame_index=0,
                         kind="polygon", data=json.dumps({"points": [[45, 35], [95, 35], [95, 85], [45, 85]], "text": ""}))
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    yield repo, srv, {"ct": (st1["uid"], se1["uid"], ct_sop), "us": (st2["uid"], se2["uid"], us_sop)}
    srv.stop()


def _esperar(cond, segundos=20):
    fim = time.time() + segundos
    while time.time() < fim:
        try:
            if cond():
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.2)
    return False


def _abrir(pg, srv, acesso):
    pg.goto(f"http://127.0.0.1:{srv.port}/web/")
    if pg.locator("#usuario").count():
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
    pg.wait_for_selector("table.lista tbody tr")
    pg.fill("#busca", "")
    linhas = pg.locator("table.lista tbody tr")
    alvo = next(i for i in range(linhas.count()) if acesso in linhas.nth(i).inner_text())
    linhas.nth(alvo).dblclick()
    pg.wait_for_selector(".quadro canvas")
    layout(pg, "1x1")
    assert _esperar(lambda: pg.locator(".quadro").count() == 1)
    # a imagem já desenhada (a carga é progressiva desde a 0.99.96)
    assert _esperar(lambda: pg.evaluate("""() => { const vp = window.__ipeGrade.viewport(0);
        const im = vp && vp.getCornerstoneImage && vp.getCornerstoneImage(); return !!(im && im.imageQualityStatus >= 8); }"""))


def _tela(pg, x, y):
    """Ponto da imagem (coluna, linha; o canto do pixel 0 em 0,0) -> ponto da página."""
    c = pg.evaluate(f"""() => {{ const vp = window.__ipeGrade.viewport(0);
        const id = vp.getCurrentImageId(); const m = window.__ipeCs.imageToWorldCoords(id, [{x}, {y}]);
        return vp.worldToCanvas(m); }}""")
    b = pg.locator(".quadro .tela").first.bounding_box()
    return b["x"] + c[0], b["y"] + c[1]


def _mms(pg):
    return [float(m) for t in _textos(pg) for m in re.findall(r"^(\d+\.\d) mm$", t)]


def _arrastar(pg, a, b):
    ini, fim = np.array(_tela(pg, *a)), np.array(_tela(pg, *b))
    pg.mouse.move(*ini)
    time.sleep(0.15)
    pg.mouse.down()
    time.sleep(0.15)
    for t in np.linspace(0.1, 1.0, 8):
        pg.mouse.move(*(ini * (1 - t) + fim * t))
        time.sleep(0.03)
    time.sleep(0.15)
    pg.mouse.up()
    time.sleep(0.2)


def _textos(pg):
    return pg.evaluate("""() => Array.from(document.querySelectorAll('.quadro svg text tspan'))
        .map((t) => (t.textContent || '').trim()).filter(Boolean)""")


def _labels_do_ipe(kind, pontos, pixels, esp, mod):
    from ipe.imaging.measure import Annotation, labels
    return labels(Annotation(kind, ("x", 0), [tuple(p) for p in pontos]), pixels, esp, mod)


def test_medidas_na_tc_banco_e_numero_do_ipe(servidor):
    repo, srv, ids = servidor
    study, series, sop = ids["ct"]
    pw = pytest.importorskip("playwright.sync_api")
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        _abrir(pg, srv, "TC ABDOME")
        # as medidas do Ipê aparecem: a régua (20 px × 0,7 = 14,0 mm) e a ROI livre com as contas do Ipê
        assert _esperar(lambda: "14.0 mm" in _textos(pg)), _textos(pg)
        poli = [[45, 35], [95, 35], [95, 85], [45, 85]]
        esperado = _labels_do_ipe("polygon", poli, _ct().astype(float), (PX, PX), "CT")
        assert _esperar(lambda: all(t in _textos(pg) for t in esperado)), (esperado, _textos(pg))
        # régua nova: 40 px × 0,7 = 28,0 mm, gravada no banco com quem fez
        ferramenta(pg, "regua")
        _arrastar(pg, (10, 10), (50, 10))
        # o mouse cai em pixels inteiros da tela: a régua sai com 28,0 mm ± um décimo
        assert _esperar(lambda: any(abs(v - 28.0) <= 0.15 for v in _mms(pg))), _textos(pg)
        assert _esperar(lambda: len([r for r in repo.annotations_for_series([series]) if r["kind"] == "line"]) == 2)
        nova = [r for r in repo.annotations_for_series([series]) if r["kind"] == "line"][-1]
        d = json.loads(nova["data"])
        assert np.allclose(d["points"], [[10, 10], [50, 10]], atol=0.6) and nova["sop_uid"] == sop
        assert d["meta"]["autor"] == "admin" and nova["owner"] == "admin" and nova["frame_index"] == 0
        # ROI elíptica: o texto do site é o do Ipê (média, DP, mín/máx e área) para os mesmos pontos
        ferramenta(pg, "elipse")
        _arrastar(pg, (55, 55), (75, 75))
        assert _esperar(lambda: any(r["kind"] == "ellipse" for r in repo.annotations_for_series([series])))
        assert _esperar(lambda: json.loads(next(r for r in repo.annotations_for_series([series])
                                                if r["kind"] == "ellipse")["data"])["points"][1][0] > 70)
        el = next(r for r in repo.annotations_for_series([series]) if r["kind"] == "ellipse")
        pts = json.loads(el["data"])["points"]
        esperado = _labels_do_ipe("ellipse", pts, _ct().astype(float), (PX, PX), "CT")
        assert _esperar(lambda: all(t in _textos(pg) for t in esperado)), (esperado, _textos(pg))
        # mexer na régua (arrastar a ponta) atualiza o banco
        ferramenta(pg, "regua")
        pg.mouse.move(*_tela(pg, 50, 10))
        pg.mouse.down()
        pg.mouse.move(*_tela(pg, 60, 10))
        pg.mouse.move(*_tela(pg, 70, 10))
        pg.mouse.up()
        def comp_editada():                       # 60 px a mais ou menos um pixel da tela: ~42 mm
            return [t for t in _textos(pg) if t.endswith(" mm") and 41.5 <= float(t.split()[0]) <= 42.5]
        assert _esperar(lambda: comp_editada()), _textos(pg)
        assert _esperar(lambda: abs(json.loads(repo.annotation_by_id(nova["id"])["data"])["points"][1][0] - 70) < 0.6)
        editada = comp_editada()[0]
        # reabrir: as medidas voltam do banco
        pg.reload()
        _abrir(pg, srv, "TC ABDOME")
        assert _esperar(lambda: editada in _textos(pg) and "14.0 mm" in _textos(pg)), _textos(pg)
        # apagar (0.99.97): o botão direito sobre a régua abre o menu da imagem, que começa pela medida
        ferramenta(pg, "janela")
        pg.mouse.click(*_tela(pg, 40, 10), button="right")
        assert _esperar(lambda: "Régua" in pg.inner_text(".menu .menu-titulo"))
        menu(pg, "Apagar esta medida")
        assert _esperar(lambda: repo.annotation_by_id(nova["id"]) is None)
        assert _esperar(lambda: editada not in _textos(pg)), _textos(pg)
        b.close()
    assert not erros, erros


def test_ultrassom_regioes_e_calibracao_a_mao(servidor):
    repo, srv, ids = servidor
    study, series, sop = ids["us"]
    pw = pytest.importorskip("playwright.sync_api")
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        _abrir(pg, srv, "US ABDOME")
        ferramenta(pg, "regua")
        # dentro da região 2D: 100 px × 0,1 mm = 10,0 mm
        _arrastar(pg, (20, 50), (120, 50))
        assert _esperar(lambda: any(abs(v - 10.0) <= 0.15 for v in _mms(pg))), _textos(pg)
        # atravessa da região 2D para o Doppler: não é distância, fica em pixels
        _arrastar(pg, (100, 150), (200, 150))
        assert _esperar(lambda: "100 px" in _textos(pg)), _textos(pg)
        # calibração à mão: 50 px = 20 mm nesta imagem; vale mais que a região
        pg.once("dialog", lambda d: d.accept("20"))
        ferramenta(pg, "calibracao")
        _arrastar(pg, (20, 100), (70, 100))
        assert _esperar(lambda: any("20 mm (só esta imagem)" in t for t in _textos(pg))), _textos(pg)
        # a régua de 100 px agora (40 mm, com o arredondamento do mouse na calibração)
        assert _esperar(lambda: any(abs(v - 40.0) <= 0.3 for v in _mms(pg))), _textos(pg)
        cal = _esperar(lambda: any(r["kind"] == "calibration" for r in repo.annotations_for_series([series])))
        assert cal
        c = next(r for r in repo.annotations_for_series([series]) if r["kind"] == "calibration")
        d = json.loads(c["data"])
        assert d["text"] == "20" and d["meta"]["escopo"] == "imagem"
        # as contas de região do site são as do Ipê
        from ipe.imaging import us_regioes as US
        import pydicom
        caminho = next(i["path"] for i in repo.instances_for_series([series][0]) if i["sop_uid"] == sop)
        regs = US.regioes(pydicom.dcmread(caminho, stop_before_pixels=True))
        assert len(regs) == 1 and US.espacamento_dos_pontos(regs, [(20, 50), (120, 50)]) == (0.1, 0.1)
        assert US.espacamento_dos_pontos(regs, [(100, 150), (200, 150)]) is None
        b.close()
    assert not erros, erros


def test_servidor_medidas_permissoes(servidor):
    """O servidor põe quem fez pelo login, recusa tipo desconhecido e medida de outro exame."""
    import urllib.error
    import urllib.request
    repo, srv, ids = servidor
    study, series, sop = ids["ct"]
    base = f"http://127.0.0.1:{srv.port}"
    tok = json.loads(urllib.request.urlopen(urllib.request.Request(
        base + "/api/login", data=json.dumps({"username": "admin", "password": "admin123"}).encode())).read())["token"]
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json", "X-Ipe-Web": "1"}

    def post(p, corpo):
        return json.loads(urllib.request.urlopen(urllib.request.Request(base + p, data=json.dumps(corpo).encode(),
                                                                        headers=h)).read())
    r = post("/api/web/medidas", {"study_uid": study, "series_uid": series, "sop_uid": sop, "frame_index": 0,
                                  "kind": "line", "data": {"points": [[1, 1], [2, 2]], "meta": {"autor": "outro"}}})
    reg = repo.annotation_by_id(r["id"])
    assert json.loads(reg["data"])["meta"]["autor"] == "admin"            # o navegador não escolhe o autor
    with pytest.raises(urllib.error.HTTPError) as e:
        post("/api/web/medidas", {"study_uid": study, "series_uid": series, "sop_uid": sop, "kind": "seg",
                                  "data": {"points": []}})
    assert e.value.code == 400
    with pytest.raises(urllib.error.HTTPError) as e:
        post("/api/web/medidas", {"db_id": r["id"], "study_uid": ids["us"][0], "series_uid": series, "sop_uid": sop,
                                  "kind": "line", "data": {"points": [[1, 1], [3, 3]]}})
    assert e.value.code == 403
    lista = json.loads(urllib.request.urlopen(urllib.request.Request(
        base + f"/api/web/medidas?study={study}&series={series}", headers=h)).read())
    assert any(x["id"] == r["id"] for x in lista)
    post("/api/web/medidas/apagar", {"db_id": r["id"]})
    assert repo.annotation_by_id(r["id"]) is None
