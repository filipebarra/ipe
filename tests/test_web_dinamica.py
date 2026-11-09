"""0.99.98 (W5): dinâmica da mama no visualizador web. O servidor acha as fases (a mesma detecção do Ipê); o
navegador calcula os mapas corte a corte com as fórmulas de imaging/dynamic.py — conferidos aqui contra o próprio
DynamicMaps —, mostra o mapa cinético, o SER e a subtração, põe um mapa (calculado ou salvo pelo Ipê) por cima da
fase e faz a curva tempo-intensidade da ROI, com a classe e os descritores."""
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pytest
from pydicom.uid import MRImageStorage, generate_uid

sys.path.insert(0, str(Path(__file__).parent))
from _web_ui import ferramenta, icone  # noqa: E402
from test_web_mpr import _esperar  # noqa: E402

from ipe.central import web as WEB  # noqa: E402

N, NZ, PX = 40, 6, 2.0
TEMPOS = ["100000", "100130", "100300", "100500", "100700"]          # 0, 90, 180, 300, 420 s
PAT = {"name": "EXEMPLO^DINAMICA", "id": "DINWEB1", "birth": "19700101", "sex": "F"}
# lesões (linha, coluna, raio) e o sinal de cada fase
LESOES = {
    "washout": ((12, 12, 5), [400, 1000, 980, 820, 760]),
    "persistente": ((12, 28, 5), [400, 640, 720, 800, 880]),
    "plato": ((28, 20, 5), [400, 900, 930, 920, 910]),
}


def _fase(f: int) -> np.ndarray:
    yy, xx, zz = np.mgrid[0:N, 0:N, 0:NZ]
    v = np.full((NZ, N, N), 6.0)                                    # ar
    corpo = ((yy - 20) / 17.0) ** 2 + ((xx - 20) / 17.0) ** 2 <= 1
    corpo = np.moveaxis(corpo, 2, 0)
    v[corpo] = 400 + 30 * f + np.moveaxis((xx * 3 + yy * 2) % 17, 2, 0)[corpo]   # tecido realça pouco
    for (r, c, raio), sinais in LESOES.values():
        m = ((np.arange(N)[:, None] - r) ** 2 + (np.arange(N)[None, :] - c) ** 2) <= raio ** 2
        v[:, m] = sinais[f]
    return v


@pytest.fixture()
def servidor_din(env, tmp_path):
    from ipe.auth.backend import LocalAuth
    from ipe.central.server import CentralServer
    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    study = {"uid": generate_uid(), "date": "20261108", "accession": "DIN1", "description": "RM MAMAS",
             "for": generate_uid()}
    for f, hora in enumerate(TEMPOS):
        series = {"uid": generate_uid(), "number": 10 + f, "description": f"T1 DIN {f + 1}"}
        vol = _fase(f)
        for k in range(NZ):
            ds = _base(MRImageStorage, PAT, study, series, "MR")
            ds.InstanceNumber = k + 1
            ds.ImageType = ["ORIGINAL", "PRIMARY", "M", "ND"]
            ds.ImagePositionPatient = [0.0, 0.0, k * 3.0]
            ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
            ds.PixelSpacing = [PX, PX]
            ds.SliceThickness = 3.0
            ds.AcquisitionTime = hora
            ds.FrameOfReferenceUID = study["for"]
            _mono(ds, vol[k], signed=False)
            _save(ds, tmp_path / "din")
    Importer(db, paths.storage).import_paths([tmp_path / "din"])
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    srv.estudo = study
    srv.repo_ = repo
    yield srv
    srv.stop()


def _token(srv):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/login", method="POST",
                                 data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())["token"]


def _din(srv):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/web/dinamica?study={srv.estudo['uid']}",
                                 headers={"Authorization": f"Bearer {_token(srv)}"})
    return json.loads(urllib.request.urlopen(req).read())


def _maps_do_ipe(srv, d):
    """Os mapas do Ipê (DynamicMaps) nas mesmas fases que o servidor mandou."""
    from ipe.imaging.dynamic import DynamicMaps, DynamicSet
    from ipe.imaging.series import FrameCache, build_frames
    repo = srv.repo_
    fases = []
    for f in d["fases"]:
        uid = f["quadros"][0]["series"]
        fr = {x.sop_uid: x for x in build_frames(repo.instances_for_series(uid), uid)}
        fases.append([fr[q["sop"]] for q in f["quadros"]])
    dset = DynamicSet(fases, [f["rotulo"] for f in d["fases"]], times=[f["tempo"] for f in d["fases"]])
    return DynamicMaps(dset, FrameCache(256), pre=d["pre"], early=d["inicial"], late=d["tardia"])


def test_fases_detectadas_no_servidor(servidor_din):
    d = _din(servidor_din)
    assert d["motivo"] == ""
    assert [round(f["tempo"]) for f in d["fases"]] == [0, 90, 180, 300, 420]
    assert d["com_horario"] and d["pre"] == 0 and d["tardia"] == 4
    assert d["inicial"] == 1                     # a mais perto de 2 min depois da pré (90 s; a de 180 s está a 60)
    assert all(len(f["quadros"]) == NZ for f in d["fases"])
    assert d["parametros"]["threshold_pct"] == 50 and d["parametros"]["relative"] is True
    assert d["classes"][3] == "médio/washout" and d["mapas"]["ser"]["cores"] == "ser"


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_mapas_curvas_e_fusao(servidor_din, tmp_path):
    pw = pytest.importorskip("playwright.sync_api")
    d = _din(servidor_din)
    ipe = _maps_do_ipe(servidor_din, d)
    k = NZ // 2
    esperado = ipe.compute(k)
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1400, "height": 950})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.on("console", lambda m: print("CONSOLE", m.type, m.text) if m.type in ("error", "warning") else None)
        pg.goto(f"http://127.0.0.1:{servidor_din.port}/web/")
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        pg.wait_for_selector("table.lista tbody tr")
        pg.locator("table.lista tbody tr").first.dblclick()
        pg.wait_for_selector(".quadro canvas")
        icone(pg, "Dinâmica da mama")
        ok = _esperar(lambda: pg.locator(".camada-din").count() == 1, 30)
        assert ok, pg.inner_text(".area")
        # os níveis de ruído e de referência como no Ipê
        par = pg.evaluate("() => window.__ipeDin.estado().par")
        assert par["referencia"] == pytest.approx(ipe.reference_level(), rel=1e-4)
        assert par["ruido"] == pytest.approx(ipe.noise_level(), rel=1e-4)
        # os mapas do corte, pixel a pixel, contra o DynamicMaps
        nav = pg.evaluate(f"""async () => {{ const m = await window.__ipeDin.mapasDoCorte({k});
            return Object.fromEntries(Object.entries(m).map(([c, v]) => [c, Array.from(v)])); }}""")
        for chave in ("cin", "ser", "msi", "pei", "ei", "sub", "ttp", "mipt", "medt"):
            a = np.asarray(nav[chave], np.float64).reshape(N, N)
            assert np.allclose(a, esperado[chave], rtol=1e-4, atol=1e-3), (chave, np.abs(a - esperado[chave]).max())
        cin = np.asarray(nav["cin"]).reshape(N, N)
        assert cin[12, 12] in (3, 6) and cin[12, 28] in (1, 4) and cin[28, 20] in (2, 5)   # washout, persistente, platô
        # os quadros: fase inicial, cinético (com a tabela do Ipê), SER e subtração
        assert pg.evaluate("() => window.__ipeDin.estado().quadros") == ["fase", "cin", "ser", "sub"]
        assert "Cinética" in pg.inner_text(".quadro >> nth=1")
        # o mapa cinético por cima da fase
        pg.select_option(".barra-din select[aria-label='Sobre a fase']", label="Cinética")
        assert _esperar(lambda: pg.evaluate("() => window.__ipeDin.estado().desenhado") == str(k))
        # rolar um quadro leva os outros ao mesmo corte
        pg.evaluate("() => window.__ipeGrade.viewport(2).setImageIdIndex(1)")
        assert _esperar(lambda: pg.evaluate("() => window.__ipeGrade.viewport(0).getCurrentImageIdIndex()") == 1)
        assert _esperar(lambda: pg.evaluate("() => window.__ipeDin.estado().desenhado") == "1")
        pg.evaluate(f"() => window.__ipeGrade.viewport(0).setImageIdIndex({k})")
        assert _esperar(lambda: pg.evaluate("() => window.__ipeGrade.viewport(3).getCurrentImageIdIndex()") == k)
        # a curva: uma elipse dentro da lesão que lava (no quadro da fase; a elipse sai do centro)
        ferramenta(pg, "elipse")
        pts = pg.evaluate("""() => { const vp = window.__ipeGrade.viewport(0); const id = vp.getCurrentImageId();
            const r = vp.canvas.getBoundingClientRect();
            return [[12.5, 12.5], [15, 15]].map(([x, y]) => { const c = vp.worldToCanvas(window.__ipeCs.imageToWorldCoords(id, [x, y]));
              return [r.left + c[0], r.top + c[1]]; }); }""")
        pg.mouse.move(*pts[0])
        pg.mouse.down()
        pg.mouse.move((pts[0][0] + pts[1][0]) / 2, (pts[0][1] + pts[1][1]) / 2)
        pg.mouse.move(*pts[1])
        pg.mouse.up()
        assert _esperar(lambda: len(pg.evaluate("() => window.__ipeDin.resumoDasCurvas()")) == 1, 20)
        c = pg.evaluate("() => window.__ipeDin.resumoDasCurvas()")[0]
        sinais = LESOES["washout"][1]
        assert c["valores"] == pytest.approx(sinais, abs=1e-3)
        assert c["classe"] == ipe.classe_cinetica(np.asarray(sinais, float)) == "rápido/washout"
        assert c["inicial"] == pytest.approx(150.0, abs=0.01)
        assert c["ser"] == pytest.approx(600 / 360, abs=1e-3)
        from ipe.imaging.dynamic import descritores
        e = (np.asarray(sinais, float) - 400) / 400 * 100
        e[0] = 0
        ref = descritores(e, np.asarray([0, 1.5, 3, 5, 7]))
        for chave in ("bat", "wash", "iauc", "mrt"):
            assert c[chave] == pytest.approx(float(ref[chave]), rel=1e-3, abs=1e-3), chave
        assert "rápido/washout" in pg.inner_text(".painel-din")
        assert pg.locator(".painel-din svg polyline").count() == 1
        # trocar a fase tardia refaz os mapas e a curva
        pg.select_option(".barra-din select[aria-label='Fase tardia']", index=2)
        assert _esperar(lambda: pg.evaluate("() => window.__ipeDin.estado().par.tardia") == 2)
        # fechar a dinâmica volta ao visualizador comum
        pg.click(".barra-din button:has-text('Fechar a dinâmica')")
        assert _esperar(lambda: pg.locator(".barra-din").count() == 0)
        b.close()
    assert not erros, erros


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_mapa_salvo_pelo_ipe_por_cima(servidor_din, tmp_path):
    """O SER gravado pelo Ipê como série ("SER (dinâmica)") aparece na lista e vai por cima da fase."""
    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    d = _din(servidor_din)
    ipe = _maps_do_ipe(servidor_din, d)
    st = servidor_din.estudo
    series = {"uid": generate_uid(), "number": 900, "description": "SER (dinâmica)"}
    for k in range(NZ):
        ds = _base(MRImageStorage, PAT, st, series, "MR")
        ds.InstanceNumber = k + 1
        ds.ImageType = ["DERIVED", "SECONDARY", "MPR"]
        ds.ImagePositionPatient = [0.0, 0.0, k * 3.0]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [PX, PX]
        ds.RescaleSlope, ds.RescaleIntercept = 0.01, 0
        _mono(ds, np.round(ipe.compute(k)["ser"] * 100), signed=True)
        _save(ds, tmp_path / "salvo")
    Importer(servidor_din.repo_.db, Path(servidor_din.storage)).import_paths([tmp_path / "salvo"])
    d2 = _din(servidor_din)
    assert [m["descricao"] for m in d2["mapas_salvos"]] == ["SER (dinâmica)"]
    assert d2["mapas_salvos"][0]["chave"] == "ser" and len(d2["fases"]) == 5      # o mapa não vira fase
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1400, "height": 950})
        pg.goto(f"http://127.0.0.1:{servidor_din.port}/web/")
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        pg.wait_for_selector("table.lista tbody tr")
        pg.locator("table.lista tbody tr").first.dblclick()
        pg.wait_for_selector(".quadro canvas")
        icone(pg, "Dinâmica da mama")
        pg.wait_for_selector(".camada-din", state="attached", timeout=30000)
        pg.select_option(".barra-din select[aria-label='Sobre a fase']", label="Salvo: SER (dinâmica)")
        assert _esperar(lambda: pg.evaluate("() => window.__ipeDin.estado().desenhado") == str(NZ // 2), 30)
        # algum pixel colorido na camada (a lesão com realce)
        assert pg.evaluate("""() => { const c = document.querySelector('.camada-din'); const d = c.getContext('2d')
            .getImageData(0, 0, c.width, c.height).data; for (let i = 3; i < d.length; i += 4) if (d[i] > 0) return true; return false; }""")
        b.close()
