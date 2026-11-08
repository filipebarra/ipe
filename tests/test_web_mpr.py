"""0.99.92 (W1): MPR no visualizador web — os três planos com as linhas, mudar o plano com um clique, espessura,
oblíquo por dois pontos e o MIP girando, cujo clique leva os cortes ao ponto mais claro. Fantoma de TC com uma
esfera clara num lugar conhecido; o Chromium do Playwright abre o site num servidor central de teste."""
import time

import numpy as np
import pytest

from ipe.central import web as WEB

pytestmark = pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")

NX, NY, NZ, PX, DZ = 64, 64, 40, 2.0, 2.5
ESFERA = (40, 22, 28)               # (i, j, k) do centro da esfera clara
MM = (ESFERA[0] * PX, ESFERA[1] * PX, ESFERA[2] * DZ)


def _fantoma():
    k, j, i = np.mgrid[0:NZ, 0:NY, 0:NX]
    v = np.full((NZ, NY, NX), -1000, np.int16)
    corpo = ((i - 32) / 28.0) ** 2 + ((j - 32) / 22.0) ** 2 <= 1
    v[corpo] = 40 + (k[corpo] % 7) * 3                          # partes moles com um pouco de textura
    d2 = ((i - ESFERA[0]) * PX) ** 2 + ((j - ESFERA[1]) * PX) ** 2 + ((k - ESFERA[2]) * DZ) ** 2
    esf = d2 <= 6 ** 2
    v[esf] = (1500 - 30 * np.sqrt(d2[esf])).astype(np.int16)    # o ponto mais claro do volume: o centro
    return v


@pytest.fixture()
def servidor(env, tmp_path):
    from pydicom.uid import generate_uid

    from ipe.auth.backend import LocalAuth
    from ipe.central.server import CentralServer
    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    pat = {"name": "MPR^FANTOMA", "id": "MPR1", "birth": "19700101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20261108", "accession": "MPR1", "description": "TC TORAX",
             "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 2, "description": "AX 2.5"}
    vol = _fantoma()
    for kk in range(NZ):
        ds = _base("1.2.840.10008.5.1.4.1.1.2", pat, study, series, "CT")
        ds.InstanceNumber = kk + 1
        ds.ImagePositionPatient = [0.0, 0.0, kk * DZ]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [PX, PX]
        ds.SliceThickness = DZ
        ds.RescaleSlope, ds.RescaleIntercept = 1, 0
        ds.WindowCenter, ds.WindowWidth = 40, 400
        _mono(ds, vol[kk], signed=True)
        _save(ds, tmp_path / "mpr")
    # e uma série de imagem única (sem volume)
    s2 = {"uid": generate_uid(), "number": 3, "description": "SCOUT"}
    ds = _base("1.2.840.10008.5.1.4.1.1.2", pat, study, s2, "CT")
    ds.ImagePositionPatient, ds.ImageOrientationPatient, ds.PixelSpacing = [0, 0, 0], [1, 0, 0, 0, 0, -1], [1, 1]
    _mono(ds, vol[20], signed=True)
    _save(ds, tmp_path / "mpr")
    Importer(db, paths.storage).import_paths([tmp_path / "mpr"])
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    yield srv
    srv.stop()


def _esperar(cond, segundos=30):
    fim = time.time() + segundos
    while time.time() < fim:
        try:
            if cond():
                return True
        except Exception:  # noqa: BLE001 - a página ainda montando
            pass
        time.sleep(0.25)
    return False


def _cam(pg, i):
    return pg.evaluate(f"() => {{ const c = window.__ipeGrade.viewport({i}).getCamera();"
                       f" return {{n: c.viewPlaneNormal, f: c.focalPoint, up: c.viewUp}}; }}")


def test_mpr_planos_espessura_obliquo_e_mip(servidor):
    pw = pytest.importorskip("playwright.sync_api")
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
        pg.locator(".quadro").first.click()
        # MPR: quatro quadros, os três planos e o MIP
        pg.click("nav.barra button:has-text('MPR')")
        assert _esperar(lambda: pg.locator(".quadro").count() == 4)
        assert _esperar(lambda: [t.split("\n")[-1] for t in pg.locator(".canto.sd").all_inner_texts()]
                        == ["Axial", "Coronal", "Sagital", "MIP"]), pg.locator(".canto.sd").all_inner_texts()
        assert pg.input_value("select[title='Botão esquerdo:']") == "linhas"
        assert _esperar(lambda: pg.evaluate(
            "() => window.__ipeGrade.viewport(0).getNumberOfSlices()") == NZ)
        # o clique no MIP leva os cortes à esfera (o ponto mais claro da linha de visão)
        alvo = pg.evaluate(f"() => window.__ipeGrade.viewport(3).worldToCanvas({list(MM)})")
        caixa = pg.locator(".quadro .tela").nth(3).bounding_box()
        pg.mouse.click(caixa["x"] + alvo[0], caixa["y"] + alvo[1])
        assert _esperar(lambda: abs(_cam(pg, 0)["f"][2] - MM[2]) <= DZ), _cam(pg, 0)
        f1 = _cam(pg, 1)["f"]                                       # coronal: y da esfera
        assert abs(f1[1] - MM[1]) <= 2 * PX, f1
        # mudar o plano com um clique: o axial vira coronal e volta; "Original" volta à pilha
        q0 = pg.locator(".quadro").nth(0)
        q0.locator(".planos button[title='Coronal']").click()
        assert _esperar(lambda: pg.locator(".canto.sd").nth(0).inner_text().endswith("Coronal"))
        q0.locator(".planos button[title='Axial']").click()
        assert _esperar(lambda: pg.locator(".canto.sd").nth(0).inner_text().endswith("Axial"))
        # espessura: MIP de 10 mm no axial
        pg.select_option("select[title='Espessura (quadros A, C, S)']", "10")
        assert _esperar(lambda: "MIP 10 mm" in pg.locator(".canto.sd").nth(0).inner_text())
        assert pg.evaluate("() => window.__ipeGrade.viewport(0).getSlabThickness()") == pytest.approx(10)
        pg.select_option("select[title='Projeção da espessura']", "minip")
        assert _esperar(lambda: "MinIP 10 mm" in pg.locator(".canto.sd").nth(0).inner_text())
        pg.select_option("select[title='Espessura (quadros A, C, S)']", "0")
        # oblíquo por dois pontos: uma reta diagonal no axial; o coronal vira o plano que a contém
        pg.click("nav.barra button:has-text('Oblíquo')")
        cx = pg.locator(".quadro .tela").nth(0).bounding_box()
        pg.mouse.click(cx["x"] + cx["width"] * 0.35, cx["y"] + cx["height"] * 0.35)
        pg.mouse.click(cx["x"] + cx["width"] * 0.65, cx["y"] + cx["height"] * 0.65)
        assert _esperar(lambda: "Oblíquo" in pg.locator(".canto.sd").nth(1).inner_text())
        n1 = np.array(_cam(pg, 1)["n"])
        n0 = np.array(_cam(pg, 0)["n"])
        assert abs(n1 @ n0) < 1e-3                       # perpendicular ao axial
        w0, w1 = (np.array(pg.evaluate(f"() => window.__ipeGrade.viewport(0).canvasToWorld([{cx['width'] * f}, "
                                        f"{cx['height'] * f}])")) for f in (0.35, 0.65))
        assert abs(n1 @ (w1 - w0)) < 1e-2 * np.linalg.norm(w1 - w0)    # o plano contém a reta
        assert min(abs(n1[0]), abs(n1[1])) > 0.2                      # e é oblíquo de verdade
        # o MIP gira (botão e roda)
        n_antes = np.array(_cam(pg, 3)["n"])
        pg.click("nav.barra button:has-text('Girar MIP')")
        assert _esperar(lambda: abs(np.array(_cam(pg, 3)["n"]) @ n_antes) < 0.99)
        pg.click("nav.barra button:has-text('Parar o giro')")
        n_antes = np.array(_cam(pg, 3)["n"])
        pg.locator(".quadro .tela").nth(3).hover()
        pg.mouse.wheel(0, 120)
        assert _esperar(lambda: abs(np.array(_cam(pg, 3)["n"]) @ n_antes) < 0.9999)
        assert abs(np.array(_cam(pg, 3)["n"])[2]) < 1e-6                    # gira em volta do eixo crânio-caudal
        # série sem volume: o aviso, e o quadro continua em pilha
        pg.select_option("select[title=Layout]", "1x1")
        pg.locator(".tira .serie:has-text('SCOUT')").click()
        assert _esperar(lambda: "SCOUT" in pg.locator(".quadro").first.inner_text())
        pg.click("nav.barra button:has-text('MPR')")
        assert _esperar(lambda: "Sem volume" in pg.inner_text(".area > .estado"))
        b.close()
    assert not erros, erros


def test_contas_do_plano_obliquo_e_do_giro(servidor):
    """As contas do site (expostas em window.__ipeGeo) contra as mesmas contas em Python."""
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page()
        pg.goto(f"http://127.0.0.1:{servidor.port}/web/")
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        pg.wait_for_selector("table.lista tbody tr")
        r = pg.evaluate("() => window.__ipeGeo.planoPorDoisPontos([0,0,0],[10,10,0],[0,0,1])")
        d = np.array([10, 10, 0]) / np.linalg.norm([10, 10, 0])
        esperado = np.cross(d, [0, 0, 1])
        assert np.allclose(r["normal"], esperado / np.linalg.norm(esperado)) and np.allclose(r["cima"], [0, 0, 1])
        g = pg.evaluate("() => window.__ipeGeo.girarVetor([0,-1,0],[0,0,1], Math.PI/2)")
        assert np.allclose(g, [1, 0, 0], atol=1e-9)
        b.close()
