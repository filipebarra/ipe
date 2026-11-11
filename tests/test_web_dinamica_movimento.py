"""0.100.8: correção de movimento na dinâmica do visualizador web — o servidor faz a conta do Ipê
(`DynamicMaps.estimate_motion`, translação ou rígida) e o navegador a aplica ao montar a pilha de cada corte; a
pilha do navegador é conferida, pixel a pixel, contra o `stack()` do Ipê com a mesma correção."""
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _web_ui import icone  # noqa: E402
from test_dinamica_rigida import _gravar  # noqa: E402
from test_web_mpr import _esperar  # noqa: E402

from ipe.central import web as WEB  # noqa: E402

K = 12


@pytest.fixture()
def servidor(env, tmp_path):
    from ipe.auth.backend import LocalAuth
    from ipe.central.server import CentralServer
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    uid = _gravar(tmp_path / "d", (0.0, 0.0, 5.0, 2.0, -3.0, 0.0))     # fases 2 e 3 giradas 5° e deslocadas
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    srv.estudo, srv.repo_ = uid, repo
    WEB._MOVIMENTO.clear()
    yield srv
    srv.stop()


def _get(srv, rota):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/login", method="POST",
                                 data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
                                 headers={"Content-Type": "application/json"})
    tok = json.loads(urllib.request.urlopen(req).read())["token"]
    r = urllib.request.Request(f"http://127.0.0.1:{srv.port}{rota}", headers={"Authorization": f"Bearer {tok}"})
    return json.loads(urllib.request.urlopen(r).read())


def _ipe(srv, d, modo):
    from ipe.imaging.dynamic import DynamicMaps, DynamicSet
    from ipe.imaging.series import FrameCache, build_frames
    fases = []
    for f in d["fases"]:
        uid = f["quadros"][0]["series"]
        fr = {x.sop_uid: x for x in build_frames(srv.repo_.instances_for_series(uid), uid)}
        fases.append([fr[q["sop"]] for q in f["quadros"]])
    dset = DynamicSet(fases, [f["rotulo"] for f in d["fases"]], times=[f["tempo"] for f in d["fases"]])
    return DynamicMaps(dset, FrameCache(512), pre=d["pre"], motion="rigido" if modo == "rigido" else True)


def test_servidor_faz_a_conta_do_ipe(servidor):
    d = _get(servidor, f"/api/web/dinamica?study={servidor.estudo}")
    assert d["motivo"] == "" and len(d["fases"]) == 4 and d["movimento"] == ""
    m = _get(servidor, f"/api/web/dinamica_movimento?study={servidor.estudo}&pre=0&modo=rigido")
    assert m["modo"] == "rigido" and set(m["matrizes"]) == {"2", "3"}
    assert abs(m["rotacoes"][2] - 5.0) < 0.6 and m["shifts"][0] == [0, 0, 0]
    assert "rotação até" in m["resumo"]
    ipe = _ipe(servidor, d, "rigido")
    assert np.allclose(np.asarray(m["matrizes"]["3"]), ipe.matrizes[3], atol=1e-6)
    t = _get(servidor, f"/api/web/dinamica_movimento?study={servidor.estudo}&pre=0&modo=translacao")
    assert t["matrizes"] == {} and any(t["shifts"][3]) and not any(t["shifts"][1])
    assert np.allclose(t["shifts"], _ipe(servidor, d, "translacao").shifts)
    # a conta fica guardada (a segunda vez não refaz)
    assert len(WEB._MOVIMENTO) == 2


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_navegador_aplica_igual_ao_ipe(servidor):
    pw = pytest.importorskip("playwright.sync_api")
    d = _get(servidor, f"/api/web/dinamica?study={servidor.estudo}")
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
        icone(pg, "Dinâmica da mama")
        assert _esperar(lambda: pg.locator(".camada-din").count() == 1, 30), pg.inner_text(".area")
        assert pg.evaluate("() => window.__ipeDin.estado().movimento") == ""

        def pilha():
            return np.asarray(pg.evaluate(f"""async () => (await window.__ipeDin.pilhaDoCorte({K})).map((f) => Array.from(f))"""))

        sem = pilha()
        for modo, rotulo in (("rigido", "Rígida"), ("translacao", "Translação")):
            pg.select_option(".barra-din select[aria-label='Correção de movimento']", label=rotulo)
            assert _esperar(lambda: pg.evaluate("() => window.__ipeDin.estado().movimento") == modo, 120), modo
            nav = pilha()
            ref = _ipe(servidor, d, modo).stack(K)
            assert nav.reshape(ref.shape).shape == ref.shape
            dif = np.abs(nav.reshape(ref.shape) - ref)
            assert dif.max() < 0.05 * ref.max(), (modo, dif.max(), ref.max())
            assert "Movimento corrigido" in pg.get_attribute(".barra-din select[aria-label='Correção de movimento']", "title")
        # a fase que mexeu aparece corrigida no quadro da fase, e desligar volta ao original
        assert not np.allclose(sem[3], nav[3])
        pg.select_option(".barra-din select[aria-label='Correção de movimento']", label="Sem correção")
        assert _esperar(lambda: pg.evaluate("() => window.__ipeDin.estado().movimento") == "", 30)
        assert np.allclose(pilha(), sem)
        b.close()
    assert not erros, erros
