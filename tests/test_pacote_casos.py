"""0.100.56: pacote de casos — a lista exportada com o Ipê Web em modo caso (exames de exemplo, nada de paciente)."""
import functools
import json
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_web_mamografia import servidor_mg  # noqa: E402,F401
from test_web_mpr import _esperar  # noqa: E402

from ipe.central import web as WEB  # noqa: E402


@pytest.fixture()
def pacote(env, sample_dir, tmp_path):
    from ipe.casos import pacote as PC
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    estudos = sorted(repo.search_studies(), key=lambda r: r.study_date)
    lid = repo.create_case_list("Aula de tórax")
    a, b = estudos[0].study_uid, estudos[1].study_uid
    repo.add_to_case_list(lid, a, friendly_name="Nódulo pulmonar", clinical_summary="Tosse há 3 meses. Tabagista.",
                          hidden_diagnosis="Adenocarcinoma", pathology="Adenocarcinoma acinar", tags=["tórax"])
    repo.add_to_case_list(lid, b, friendly_name="Segundo caso")
    series_a = repo.series_for_study(a)
    # a segunda série do caso 1 só aparece no resultado; uma seta do Ipê vai para o resultado
    repo.update_list_item(lid, a, result_series=[series_a[-1].series_uid] if len(series_a) > 1 else [])
    inst = repo.instances_for_series(series_a[0].series_uid)[0]
    repo.save_annotation(db_id=None, study_uid=a, series_uid=series_a[0].series_uid, sop_uid=inst["sop_uid"],
                         frame_index=0, kind="arrow", data=json.dumps({"points": [[10, 10], [40, 40]], "text": "nódulo",
                                                                        "meta": {"autor": "dr.fulano"}}), owner="dr.fulano")
    destino = tmp_path / "pacote"
    r = PC.exportar(repo, lid, destino, settings=None)
    return repo, lid, destino, r, (a, b, series_a)


def test_exporta(pacote):
    repo, _lid, destino, r, (a, _b, series_a) = pacote
    assert r.casos == 2 and r.series >= 2 and r.imagens > 0
    c = json.loads((destino / "casos" / "casos.json").read_text(encoding="utf-8"))
    assert c["titulo"] == "Aula de tórax" and len(c["casos"]) == 2
    k1 = c["casos"][0]
    assert k1["titulo"] == "Nódulo pulmonar" and k1["historia"].startswith("Tosse")
    assert k1["resultado"]["diagnostico"] == "Adenocarcinoma" and k1["resultado"]["patologia"].startswith("Adeno")
    assert k1["study"] != a                                          # UIDs novas
    if len(series_a) > 1:
        assert list(k1["series"].values()).count("resultado") == 1
    # nada do paciente nem das UIDs originais em lugar nenhum do pacote (fora o site)
    info = repo.study_info(a)
    proibidos = [info["patient_name"].split("^")[0], info["patient_id"], a, series_a[0].series_uid]
    for p in (destino / "casos").rglob("*"):
        if p.is_file() and p.suffix != ".pdf" and "frames" not in p.parts:
            t = p.read_bytes().decode("utf-8", "ignore")
            for x in proibidos:
                assert x not in t, (x, p)
            assert "dr.fulano" not in t
    # a seta foi para as marcações do resultado, sem o autor
    regs = []
    for p in (destino / "casos" / "api" / "medidas").glob("*.json"):
        regs += json.loads(p.read_text())
    assert len(regs) == 1 and regs[0]["resposta"] and regs[0]["kind"] == "arrow"
    # o site, o leia-me e o QIDO
    assert (destino / "index.html").is_file() and (destino / "LEIA-ME.txt").is_file()
    estudos = json.loads((destino / "casos" / "dw" / "studies.json").read_text())
    assert {e["00100010"]["Value"][0]["Alphabetic"] for e in estudos} == {"Caso 1", "Caso 2"}
    # um quadro: corpo multipart com a sintaxe da parte
    q = next((destino / "casos" / "dw").rglob("frames/1")).read_bytes()
    assert q.startswith(b"--ipecasoframe\r\nContent-Type: application/octet-stream; transfer-syntax=")


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_no_navegador(pacote):
    pw = pytest.importorskip("playwright.sync_api")
    _repo, _lid, destino, _r, (_a, _b, series_a) = pacote

    class Quieto(SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    # um site estático qualquer, numa subpasta (como uma hospedagem de arquivos)
    raiz = destino.parent
    srv = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quieto, directory=str(raiz)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    erros = []
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            pg = b.new_page(viewport={"width": 1920, "height": 1080})
            pg.on("pageerror", lambda e: erros.append(str(e)))
            msgs = []
            pg.on("console", lambda m: msgs.append(m.text))
            pg.on("response", lambda r: msgs.append(f"404 {r.url}") if r.status == 404 else None)
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/pacote/")
            pg.wait_for_selector(".cartao-caso")
            assert pg.locator(".cartao-caso").count() == 2
            assert "Aula de tórax" in pg.text_content(".topo-casos")
            pg.fill(".telacasos input", "tabagista")
            assert pg.locator(".cartao-caso").count() == 1
            pg.click(".cartao-caso")
            assert _esperar(lambda: pg.locator(".painel-caso").count() > 0, 30), msgs[-5:]
            assert "Tosse há 3 meses" in pg.text_content(".painel-caso")
            assert "Adenocarcinoma" not in pg.text_content(".painel-caso")
            # nada do que precisa do servidor
            for rot in ("Laudo", "CAD/IA neste exame", "Enviar a um destino DICOM"):
                assert not pg.locator(f"nav.barra button[aria-label='{rot}']").is_visible()
            assert _esperar(lambda: pg.evaluate("() => window.__ipeGrade && window.__ipeGrade.quadros.some(q => q.serie)"), 30)
            assert _esperar(lambda: pg.evaluate(
                "() => { const g = window.__ipeGrade; const v = g.viewport(0); return !!v && !!v.getCurrentImageId() &&"
                " !!v.getImageData(); }"), 30)
            n_series = pg.locator(".tira .series button.serie").count()
            # a seta do Ipê está na primeira imagem da série: só aparece com o resultado
            sop = next(json.loads(p_.read_text()) for p_ in (destino / "casos" / "api" / "medidas").glob("*.json")
                       if json.loads(p_.read_text()))[0]["sop_uid"]
            pg.evaluate("""(sop) => { const g = window.__ipeGrade; const k = g.quadros[0].serie.imageIds.findIndex(i => i.includes(sop));
                                      g.viewport(0).setImageIdIndex(k); }""", sop)
            setas = "() => document.querySelectorAll('.quadro svg line').length"
            pg.wait_for_timeout(800)
            assert pg.evaluate(setas) == 0
            pg.click(".painel-caso button.revelar")
            assert _esperar(lambda: "Adenocarcinoma acinar" in (pg.text_content(".painel-caso") or ""), 5)
            assert _esperar(lambda: pg.evaluate(setas) > 0, 10)
            if len(series_a) > 1:
                assert _esperar(lambda: pg.locator(".tira .series button.serie").count() == n_series + 1, 15)
            # esconder volta ao caso sem o resultado; o próximo caso
            pg.click(".painel-caso button.revelar")
            assert _esperar(lambda: "Adenocarcinoma" not in (pg.text_content(".painel-caso") or ""), 15)
            pg.click(".nav-caso button:has-text('Próximo')")
            assert _esperar(lambda: "Segundo caso" in (pg.text_content(".painel-caso") or ""), 15)
            pg.click("nav.barra button[aria-label='Voltar à lista']")
            pg.wait_for_selector(".cartao-caso")
            b.close()
    finally:
        srv.shutdown()
    assert not erros, erros


@pytest.mark.skipif(sys.platform != "linux", reason="o lançador de Linux")
def test_lancador(pacote):
    """O lançador do pacote (Go) serve a pasta em 127.0.0.1 e acha os casos."""
    import re
    import subprocess
    import urllib.request
    _repo, _lid, destino, _r, _x = pacote
    exe = destino / "Abrir casos (Linux)"
    if not exe.exists():
        pytest.skip("lançadores não compilados (tools/lancador/build.sh)")
    for nome in ("Abrir casos (Windows).exe", "Abrir casos (Mac Apple)", "Abrir casos (Mac Intel)"):
        assert (destino / nome).is_file()
    p = subprocess.Popen([str(exe), "-sem-navegador"], stdout=subprocess.PIPE, text=True)
    try:
        url = None
        for _ in range(5):
            m = re.search(r"(http://127\.0\.0\.1:\d+/)", p.stdout.readline())
            if m:
                url = m.group(1)
                break
        assert url
        c = json.loads(urllib.request.urlopen(url + "casos/casos.json", timeout=5).read())
        assert len(c["casos"]) == 2
        assert b"<div id=\"app\">" in urllib.request.urlopen(url, timeout=5).read()
    finally:
        p.terminate()
        p.wait(5)


def test_editor_do_caso(qtbot, env, sample_dir):
    """Organizar lista: laudo/resultado, biópsia e séries do resultado gravam no caso."""
    from ipe.importer.scanner import Importer
    from ipe.ui.caselists import ListEditorDialog
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    st = repo.search_studies()[0].study_uid
    lid = repo.create_case_list("L")
    repo.add_to_case_list(lid, st)
    d = ListEditorDialog(repo, lid)
    qtbot.addWidget(d)
    d.f_result.setPlainText("Nódulo espiculado no lobo superior direito.")
    d.f_path.setPlainText("Adenocarcinoma")
    from PySide6.QtCore import Qt
    d.f_res_series.item(0).setCheckState(Qt.Checked)
    d.save_all()
    it = repo.list_items(lid)[0]
    assert it["result_text"].startswith("Nódulo") and it["pathology"] == "Adenocarcinoma"
    assert it["result_series"] == [d.f_res_series.item(0).data(Qt.UserRole)]
    d.reject()


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_mamografia_no_pacote(servidor_mg, tmp_path):
    """Uma mamografia no pacote: o protocolo (sem os anteriores) vai junto e o modo de mamografia abre."""
    from ipe.casos import pacote as PC
    pw = pytest.importorskip("playwright.sync_api")
    repo = servidor_mg.repo
    atual, _ant = servidor_mg.estudos
    lid = repo.create_case_list("Mama")
    repo.add_to_case_list(lid, atual, friendly_name="Calcificações", clinical_summary="Rastreamento.")
    destino = tmp_path / "pmg"
    PC.exportar(repo, lid, destino, settings=servidor_mg.settings)
    mg = list((destino / "casos" / "api" / "mamografia").glob("*.json"))
    assert len(mg) == 1
    d = json.loads(mg[0].read_text())
    assert d["protocolo"] and d["anteriores"] == []
    assert atual not in mg[0].read_text()

    class Quieto(SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quieto, directory=str(destino)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    erros = []
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            pg = b.new_page(viewport={"width": 1920, "height": 1080})
            pg.on("pageerror", lambda e: erros.append(str(e)))
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}/")
            pg.click(".cartao-caso")
            assert _esperar(lambda: pg.evaluate("() => !!window.__ipeMg"), 30)
            assert _esperar(lambda: pg.evaluate(
                "() => window.__ipeGrade.quadros.filter(q => q.serie).length >= 2"), 30)
            b.close()
    finally:
        srv.shutdown()
    assert not erros, erros
