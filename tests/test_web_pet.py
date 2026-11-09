from pathlib import Path
import sys
"""0.99.94 (W3): PET/CT no visualizador web — fusão com as cores do Ipê, o PET em SUV pela conta do Ipê, a leitura
fusão + PET + MIP com os axiais juntos, o SUV máximo perto do cursor e a SEG do Ipê como máscara. Fantoma de TC e
de PET no mesmo referencial, com uma lesão quente num lugar conhecido."""
import json
import re
import time
from types import SimpleNamespace

import numpy as np
import pytest

from ipe.central import web as WEB  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from _web_ui import aba, botoes, espessura, ferramenta, icone, layout, menu, quadros  # noqa: E402,F401

pytestmark = pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")

# TC 64×64×40 (2 × 2 × 2,5 mm) e PET 32×32×20 (4 × 4 × 5 mm): os dois cobrem 128 × 128 × 100 mm
CT_N, CT_PX, CT_DZ = (64, 64, 40), 2.0, 2.5
PT_N, PT_PX, PT_DZ = (32, 32, 20), 4.0, 5.0
LESAO = (20, 12, 10)                                  # (i, j, k) no PET: o centro da lesão
MM = (LESAO[0] * PT_PX, LESAO[1] * PT_PX, LESAO[2] * PT_DZ)
PICO = 36000                                          # Bq/ml no centro da lesão


def _tc():
    k, j, i = np.mgrid[0:CT_N[2], 0:CT_N[1], 0:CT_N[0]]
    v = np.full((CT_N[2], CT_N[1], CT_N[0]), -1000, np.int16)
    v[((i - 32) / 28.0) ** 2 + ((j - 32) / 24.0) ** 2 <= 1] = 40
    return v


def _pet():
    k, j, i = np.mgrid[0:PT_N[2], 0:PT_N[1], 0:PT_N[0]]
    v = np.zeros((PT_N[2], PT_N[1], PT_N[0]), np.uint16)
    v[((i - 16) / 14.0) ** 2 + ((j - 16) / 12.0) ** 2 <= 1] = 2000
    d = np.sqrt(((i - LESAO[0]) * PT_PX) ** 2 + ((j - LESAO[1]) * PT_PX) ** 2 + ((k - LESAO[2]) * PT_DZ) ** 2)
    les = d <= 12
    v[les] = (PICO - 2000 * d[les]).astype(np.uint16)  # o máximo do PET: o centro
    return v


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
    pat = {"name": "PET^FANTOMA", "id": "PET1", "birth": "19700101", "sex": "M"}
    study = {"uid": generate_uid(), "date": "20261108", "accession": "PET1", "description": "PET-CT FDG",
             "for": generate_uid()}
    sct = {"uid": generate_uid(), "number": 2, "description": "TC AC"}
    spt = {"uid": generate_uid(), "number": 3, "description": "PET AC"}
    tc, pet = _tc(), _pet()
    for kk in range(CT_N[2]):
        ds = _base("1.2.840.10008.5.1.4.1.1.2", pat, study, sct, "CT")
        ds.InstanceNumber = kk + 1
        ds.ImagePositionPatient, ds.ImageOrientationPatient = [0.0, 0.0, kk * CT_DZ], [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing, ds.SliceThickness = [CT_PX, CT_PX], CT_DZ
        ds.RescaleSlope, ds.RescaleIntercept, ds.WindowCenter, ds.WindowWidth = 1, 0, 40, 400
        _mono(ds, tc[kk], signed=True)
        _save(ds, tmp_path / "d")
    for kk in range(PT_N[2]):
        ds = _base("1.2.840.10008.5.1.4.1.1.128", pat, study, spt, "PT")
        ds.InstanceNumber = kk + 1
        ds.ImagePositionPatient, ds.ImageOrientationPatient = [0.0, 0.0, kk * PT_DZ], [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing, ds.SliceThickness = [PT_PX, PT_PX], PT_DZ
        ds.RescaleSlope, ds.RescaleIntercept = 1, 0
        ds.Units, ds.DecayCorrection, ds.PatientWeight = "BQML", "START", 70
        ds.SeriesDate, ds.SeriesTime = "20261108", "110000"
        rp = Dataset()
        rp.RadiopharmaceuticalStartTime = "100000"
        rp.RadionuclideTotalDose, rp.RadionuclideHalfLife = 370e6, 6586.2
        ds.RadiopharmaceuticalInformationSequence = Sequence([rp])
        _mono(ds, pet[kk], signed=False)
        _save(ds, tmp_path / "d")
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    # a SEG da lesão sobre o PET (como a carga tumoral do Ipê grava)
    from ipe.imaging import estruturas as ES
    from ipe.imaging.seg_writer import build_seg
    from ipe.imaging.series import FrameCache, build_frames
    from ipe.imaging.volume import build_volume
    frames = build_frames(repo.instances_for_series(spt["uid"]), spt["uid"])
    vol = build_volume(frames, FrameCache(64))
    g = ES.Grade.do_volume(vol)
    les = ES.Estrutura("Lesão 1", (255, 80, 80), tipo="lesão")
    ES.pintar(les, g, np.array(MM, float), 9.0)
    seg = build_seg(vol, [(SimpleNamespace(mask=les.mascara, offset=les.offset), les.nome, les.cor, les.tipo)],
                    vol.source_path, frames, description="Carga tumoral (Ipe)")
    (tmp_path / "s").mkdir()
    seg.save_as(tmp_path / "s" / "seg.dcm", enforce_file_format=True)
    Importer(db, paths.storage).import_paths([tmp_path / "s"])
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    seg_serie = next(r.series_uid for r in repo.series_for_study(study["uid"], ocultas=True) if r.modality == "SEG")
    yield repo, srv, {"study": study["uid"], "ct": sct["uid"], "pt": spt["uid"], "seg": seg_serie,
                      "voxels": int(np.count_nonzero(les.mascara))}
    srv.stop()


def _esperar(cond, segundos=30):
    fim = time.time() + segundos
    while time.time() < fim:
        try:
            if cond():
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.25)
    return False


def _fator(repo, serie):
    from ipe.imaging.suv import suv_factor_for_file
    return suv_factor_for_file(repo.instances_for_series(serie)[0]["path"])[0]


def _get(srv, caminho, token):
    import urllib.error
    import urllib.request
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}{caminho}",
                                 headers={"Authorization": f"Bearer {token}", "X-Ipe-Web": "1"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


def _token(srv):
    import urllib.request
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/login", method="POST",
                                 data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["token"]


def test_servidor_suv_e_seg(servidor):
    repo, srv, ids = servidor
    tok = _token(srv)
    st, r = _get(srv, f"/api/web/suv?study={ids['study']}&series={ids['pt']}", tok)
    assert st == 200 and r["fator"] == pytest.approx(_fator(repo, ids["pt"])) and r["motivo"] == "SUVbw"
    st, r = _get(srv, f"/api/web/suv?study={ids['study']}&series={ids['ct']}", tok)
    assert st == 200 and r["fator"] is None
    st, r = _get(srv, f"/api/web/seg?study={ids['study']}&series={ids['seg']}", tok)
    assert st == 200 and r["ref_series"] == ids["pt"]
    assert [s["nome"] for s in r["segmentos"]] == ["Lesão 1"] and r["segmentos"][0]["cor"] == [255, 80, 80]
    import base64
    import zlib
    total = sum(int(np.count_nonzero(np.frombuffer(zlib.decompress(base64.b64decode(f["dados"])), np.uint8)))
                for f in r["fatias"])
    assert total == ids["voxels"] > 0
    # série de outro exame, ou uma que não é SEG: não
    assert _get(srv, f"/api/web/seg?study={ids['study']}&series=1.2.3", tok)[0] == 403
    assert _get(srv, f"/api/web/seg?study={ids['study']}&series={ids['ct']}", tok)[0] == 400
    assert _get(srv, f"/api/web/suv?study=1.2.3&series={ids['pt']}", tok)[0] == 403
    # as tabelas de cores do Ipê vão na configuração
    st, cfg = _get(srv, "/api/web/config", tok)
    assert "hot" in cfg["tabelas_cores"] and cfg["tabelas_cores"]["hot"]["pontos"][-1] == [1.0, 1.0, 1.0, 1.0]


def _abrir(pg, srv):
    pg.goto(f"http://127.0.0.1:{srv.port}/web/")
    pg.fill("#usuario", "admin")
    pg.fill("#senha", "admin123")
    pg.click("button[type=submit]")
    pg.wait_for_selector("table.lista tbody tr")
    pg.locator("table.lista tbody tr").first.dblclick()
    pg.wait_for_selector(".quadro canvas")


def _carregado(pg, serie):
    return pg.evaluate(f"""() => {{ const v = window.__ipeCs.cache.getVolume('cornerstoneStreamingImageVolume:{serie}');
        return !!(v && v.loadStatus && v.loadStatus.loaded); }}""")


def _textos(pg):
    return pg.evaluate("""() => Array.from(document.querySelectorAll('.quadro svg text tspan'))
        .map((t) => (t.textContent || '').trim()).filter(Boolean)""")


def test_fusao_suv_maximo_e_seg(servidor):
    repo, srv, ids = servidor
    fator = _fator(repo, ids["pt"])
    pw = pytest.importorskip("playwright.sync_api")
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1500, "height": 900})
        pg.on("pageerror", lambda e: erros.append(str(e) + " " + str(getattr(e, "stack", ""))[:1500]))
        _abrir(pg, srv)
        icone(pg, 'PET/CT')
        assert _esperar(lambda: pg.locator(".quadro").count() == 3)
        assert _esperar(lambda: [t.split("\n")[-1] for t in pg.locator(".canto.sd").all_inner_texts()]
                        == ["Fusão PT · Axial", "Axial", "MIP"]), pg.locator(".canto.sd").all_inner_texts()
        assert quadros(pg) == "1x3"
        assert _esperar(lambda: _carregado(pg, ids["pt"]) and _carregado(pg, ids["ct"]))
        pt_id = f"cornerstoneStreamingImageVolume:{ids['pt']}"
        # a fusão: dois volumes, o PET em cima com a tabela do Ipê e a janela em SUV
        props = lambda: pg.evaluate(f"""() => {{ const vp = window.__ipeGrade.viewport(0);
            const p = vp.getProperties('{pt_id}'); return {{ n: vp.getActors().length, cor: p.colormap && p.colormap.name,
            voi: p.voiRange }}; }}""")
        assert _esperar(lambda: props()["n"] == 2 and props()["cor"] == "ipe-hot"), props()
        assert props()["voi"]["lower"] == pytest.approx(0) and props()["voi"]["upper"] == pytest.approx(6)
        assert "SUV 0–6" in pg.locator(".canto.id").first.inner_text()
        # o PET chega em SUV: o voxel do centro da lesão vale PICO × fator
        v = pg.evaluate(f"""() => {{ const v = window.__ipeCs.cache.getVolume('{pt_id}');
            return v.voxelManager.getAtIJK({LESAO[0]}, {LESAO[1]}, {LESAO[2]}); }}""")
        assert v == pytest.approx(PICO * fator, rel=1e-4)
        # cor, opacidade e topo da janela
        pg.select_option("select[title='Cor da fusão']", "rainbow")
        assert _esperar(lambda: props()["cor"] == "ipe-rainbow")
        pg.select_option("select[title='Opacidade da fusão']", "0.8")
        pg.select_option("select[title='Topo da janela de SUV']", "10")
        assert _esperar(lambda: props()["voi"]["upper"] == pytest.approx(10))
        assert _esperar(lambda: "80%" in pg.locator(".canto.id").first.inner_text()
                        and "SUV 0–10" in pg.locator(".canto.id").nth(1).inner_text())
        # os dois axiais andam juntos
        pg.evaluate("""() => { const vp = window.__ipeGrade.viewport(0); const c = vp.getCamera();
            vp.setCamera({ focalPoint: [c.focalPoint[0], c.focalPoint[1], 20], position: [c.position[0], c.position[1],
            c.position[2] - c.focalPoint[2] + 20] }); vp.render(); }""")
        assert _esperar(lambda: abs(pg.evaluate("() => window.__ipeGrade.viewport(1).getCamera().focalPoint[2]") - 20) < 0.01)
        # SUV máximo perto do cursor: um clique a 14 mm da lesão leva os cortes ao centro dela
        ferramenta(pg, "suvmax")
        alvo = [MM[0] + 14, MM[1], 20.0]
        c = pg.evaluate(f"() => window.__ipeGrade.viewport(0).worldToCanvas({alvo})")
        bb = pg.locator(".quadro .tela").first.bounding_box()
        pg.mouse.click(bb["x"] + c[0], bb["y"] + c[1])
        assert _esperar(lambda: pg.evaluate("() => window.__ipeGrade.ultimoMaximo") is not None)
        m = pg.evaluate("() => window.__ipeGrade.ultimoMaximo")
        # o clique está em z = 20 e a lesão em z = 50: 30 mm, no limite da esfera — então o máximo da esfera é o
        # ponto da lesão mais perto do clique, não o centro; o que importa é que é o máximo da esfera
        assert m["valor"] > 2000 * fator
        pg.evaluate(f"() => window.__ipeGrade.irAoPonto({list(MM)})")
        c = pg.evaluate(f"() => window.__ipeGrade.viewport(0).worldToCanvas({[MM[0] + 14, MM[1], MM[2]]})")
        pg.mouse.click(bb["x"] + c[0], bb["y"] + c[1])
        assert _esperar(lambda: abs(pg.evaluate("() => window.__ipeGrade.ultimoMaximo.valor") - PICO * fator) < 1e-3)
        m = pg.evaluate("() => window.__ipeGrade.ultimoMaximo")
        assert np.allclose(m["ponto"], MM, atol=0.01)
        assert f"{PICO * fator:.2f}" in pg.locator(".canto.ie").first.inner_text()
        for i in (0, 1):
            assert pg.evaluate(f"() => window.__ipeGrade.viewport({i}).getCamera().focalPoint[2]") == pytest.approx(MM[2])
        # a fusão aparece de verdade (arco-íris, 80%, SUV 0–10): na borda da lesão (SUV ~5,5) o PET pinta a TC; no
        # corpo (SUV ~0,55, abaixo de 8% do topo) fica só a TC, cinza, como no Ipê; fora do corpo, preto
        import io

        from PIL import Image
        vp0 = "window.__ipeGrade.viewport(0)"
        borda = pg.evaluate(f"() => {vp0}.worldToCanvas([{MM[0] - 8}, {MM[1]}, {MM[2]}])")
        corpo = pg.evaluate(f"() => {vp0}.worldToCanvas([30, 64, {MM[2]}])")
        fora = pg.evaluate(f"() => {vp0}.worldToCanvas([2, 2, {MM[2]}])")
        foto = Image.open(io.BytesIO(pg.locator(".quadro .tela").first.screenshot())).convert("RGB")
        px = lambda c: foto.getpixel((int(c[0]), int(c[1])))
        assert max(px(borda)) - min(px(borda)) > 60, px(borda)          # colorido
        assert max(px(corpo)) - min(px(corpo)) < 8 and max(px(corpo)) > 80, px(corpo)   # a TC, cinza
        assert max(px(fora)) < 30
        # a SEG do Ipê como máscara nos quadros de volume, com o número de voxels da lesão
        pg.select_option("select[title='Segmentação (SEG)']", ids["seg"])
        assert _esperar(lambda: pg.evaluate("() => window.__ipeGrade.seg && window.__ipeGrade.seg.voxels") == ids["voxels"])
        reps = pg.evaluate("""() => [0, 1, 2].map((i) => window.__ipeCs.segmentation.state
            .getSegmentationRepresentations(window.__ipeGrade.quadros[i].id).length)""")
        assert reps == [1, 1, 1], reps
        assert "Lesão 1" in pg.locator(".area .estado").inner_text()
        b.close()
    assert not erros, erros


def test_janela_do_pet_e_arranjo(servidor):
    """0.100.2: a janela do PET no arrasto (topo e piso, em todos os quadros do mesmo PET; Shift na fusão mexe na
    TC) e o arranjo do PET/CT escolhido no painel (grade, conteúdo e plano de cada quadro), lembrado."""
    repo, srv, ids = servidor
    pw = pytest.importorskip("playwright.sync_api")
    erros = []
    pt_id = f"cornerstoneStreamingImageVolume:{ids['pt']}"
    ct_id = f"cornerstoneStreamingImageVolume:{ids['ct']}"
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1500, "height": 900})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        _abrir(pg, srv)
        icone(pg, 'PET/CT')
        assert _esperar(lambda: pg.locator(".quadro").count() == 3)
        assert _esperar(lambda: _carregado(pg, ids["pt"]) and _carregado(pg, ids["ct"]))
        voi = lambda i, vid="": pg.evaluate(f"() => window.__ipeGrade.viewport({i}).getProperties({json.dumps(vid) if vid else ''}).voiRange")  # noqa: E731
        assert _esperar(lambda: voi(1)["upper"] == pytest.approx(6))
        # arrastar para baixo no PET sobe o topo (6 → 9 em 60 px); para a direita, o piso
        bb = pg.locator(".quadro .tela").nth(1).bounding_box()
        x, y = bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
        pg.mouse.move(x, y)
        pg.mouse.down()
        pg.mouse.move(x + 20, y + 30)
        pg.mouse.move(x + 40, y + 60)
        pg.mouse.up()
        assert _esperar(lambda: voi(1)["upper"] == pytest.approx(9, abs=0.02)), voi(1)
        assert voi(1)["lower"] == pytest.approx(1.0, abs=0.02)
        assert voi(0, pt_id)["upper"] == pytest.approx(9, abs=0.02)                 # a fusão acompanha
        assert voi(2)["upper"] == pytest.approx(9, abs=0.02)                        # e o MIP
        assert "SUV 1–9" in pg.locator(".canto.id").nth(1).inner_text()
        assert pg.input_value("select[title='Topo da janela de SUV']") == "9"
        # na fusão, com Shift, a janela é da TC
        ct0 = voi(0, ct_id)
        bb = pg.locator(".quadro .tela").nth(0).bounding_box()
        x, y = bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
        pg.keyboard.down("Shift")
        pg.mouse.move(x, y)
        pg.mouse.down()
        pg.mouse.move(x + 30, y + 30)
        pg.mouse.move(x + 60, y + 60)
        pg.mouse.up()
        pg.keyboard.up("Shift")
        assert _esperar(lambda: voi(0, ct_id) != ct0)
        assert voi(0, pt_id)["upper"] == pytest.approx(9, abs=0.02)
        # o arranjo: 2 × 2, o quarto quadro só a TC, o primeiro no coronal
        pg.select_option("select[aria-label='Grade do PET/CT']", "2x2")
        assert _esperar(lambda: pg.locator(".quadro").count() == 4)
        pg.select_option("select[aria-label='Quadro 4']", "tc")
        assert _esperar(lambda: pg.evaluate("() => window.__ipeGrade.arranjoPet()[3].v") == "tc")
        pg.select_option("select[aria-label='Plano do quadro 1']", "CORONAL")
        arr = lambda: pg.evaluate("() => window.__ipeGrade.arranjoPet()")  # noqa: E731
        assert _esperar(lambda: arr()[0] == {"v": "fusao", "plano": "CORONAL"}), arr()
        assert [q["v"] for q in arr()] == ["fusao", "pet", "mip", "tc"]
        # a janela de SUV continua a escolhida
        assert _esperar(lambda: voi(1)["upper"] == pytest.approx(9, abs=0.02))
        # lembrado para o próximo PET/CT
        icone(pg, 'PET/CT')
        assert _esperar(lambda: pg.locator(".quadro").count() == 4 and [q["v"] for q in arr()] == ["fusao", "pet", "mip", "tc"])
        pg.click("button:has-text('Arranjo padrão')")
        assert _esperar(lambda: pg.locator(".quadro").count() == 3)
        b.close()
    assert not erros, erros


def test_medidas_no_pet_em_suv(servidor):
    """A ROI e o valor do pixel no PET (cortes originais) trazem o SUV como no Ipê."""
    from ipe.imaging.measure import Annotation, labels
    repo, srv, ids = servidor
    fator = _fator(repo, ids["pt"])
    pw = pytest.importorskip("playwright.sync_api")
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        pg.on("pageerror", lambda e: erros.append(str(e) + " " + str(getattr(e, "stack", ""))[:1500]))
        _abrir(pg, srv)
        layout(pg, "1x1")
        assert _esperar(lambda: pg.locator(".quadro").count() == 1)
        pg.locator("aside.tira button.serie", has_text="PT").click()
        assert _esperar(lambda: "PET AC" in pg.locator(".canto.sd").first.inner_text())
        # vai ao corte da lesão
        pg.evaluate(f"() => window.__ipeGrade.viewport(0).setImageIdIndex({LESAO[2]})")
        assert _esperar(lambda: pg.evaluate("() => window.__ipeGrade.viewport(0).getCurrentImageIdIndex()") == LESAO[2])

        def tela(x, y):
            c = pg.evaluate(f"""() => {{ const vp = window.__ipeGrade.viewport(0);
                const m = window.__ipeCs.imageToWorldCoords(vp.getCurrentImageId(), [{x}, {y}]);
                return vp.worldToCanvas(m); }}""")
            bb = pg.locator(".quadro .tela").first.bounding_box()
            return bb["x"] + c[0], bb["y"] + c[1]
        ferramenta(pg, "pixel")
        pg.mouse.click(*tela(LESAO[0] + 0.5, LESAO[1] + 0.5))
        fatia = _pet()[LESAO[2]].astype(float)
        esperado = labels(Annotation("probe", ("x", 0), [(LESAO[0] + 0.5, LESAO[1] + 0.5)]), fatia, (PT_PX, PT_PX),
                          "PT", suv=fator)
        assert esperado[0].startswith("SUV ")
        assert _esperar(lambda: all(t in _textos(pg) for t in esperado)), (esperado, _textos(pg))
        # ROI elíptica: SUVmáx/SUVméd e a média em Bq/ml, como o Ipê
        ferramenta(pg, "elipse")
        a, z = tela(16, 8), tela(25, 17)
        pg.mouse.move(*a)
        pg.mouse.down()
        for t in np.linspace(0.1, 1, 8):
            pg.mouse.move(a[0] * (1 - t) + z[0] * t, a[1] * (1 - t) + z[1] * t)
            time.sleep(0.03)
        pg.mouse.up()
        assert _esperar(lambda: any(r["kind"] == "ellipse" for r in repo.annotations_for_series([ids["pt"]])))
        reg = next(r for r in repo.annotations_for_series([ids["pt"]]) if r["kind"] == "ellipse")
        pts = json.loads(reg["data"])["points"]
        esperado = labels(Annotation("ellipse", ("x", 0), [tuple(q) for q in pts]), fatia, (PT_PX, PT_PX), "PT",
                          suv=fator)
        assert re.match(r"SUVmáx \d", esperado[0])
        assert _esperar(lambda: all(t in _textos(pg) for t in esperado)), (esperado, _textos(pg))
        b.close()
    assert not erros, erros
