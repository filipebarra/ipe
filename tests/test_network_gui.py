"""Rede na interface: aba PACS, fila, envio, chamada externa (link e API HTTP)."""
import json
import threading
import time
import urllib.request

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer
from ipe.network.external import ExternalError, parse_url
from test_network import Node, free_port


def wait(app, cond, timeout=30):
    t0 = time.time()
    while not cond() and time.time() - t0 < timeout:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()
    return cond()


@pytest.fixture()
def setup(env, sample_dir, tmp_path):
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    pacs = Node(tmp_path / "pacs", "PACS")
    Importer(pacs.db, pacs.storage).import_paths([sample_dir])
    settings = Settings(paths.settings_file)
    port, http_port = free_port(), free_port()
    settings.set("dicom", {**settings.get("dicom"), "port": port, "http_port": http_port,
                           "http_token": "segredo", "ae_title": "DICOMVIEWER"})
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, settings)
    w.resize(1300, 800)
    w.show()
    pacs.repo.save_node({"name": "EU", "ae_title": "DICOMVIEWER", "host": "127.0.0.1", "port": port})
    nid = w.repo.save_node(pacs.as_node())
    assert pacs.server.start()
    w.start_services()
    w.pacs.refresh_nodes()
    assert w.net.server.running and w.http.server.isListening()
    yield app, w, pacs, nid, http_port
    w.close()
    pacs.close()


def test_search_retrieve_and_open(setup):
    app, w, pacs, nid, _ = setup
    panel = w.pacs
    panel.acc.setText("ACC1001")
    panel.period.setCurrentIndex(5)            # qualquer data
    panel.search()
    assert wait(app, lambda: panel.results.topLevelItemCount() == 1)
    item = panel.results.topLevelItem(0)
    assert item.text(10) == "—"
    item.setExpanded(True)
    assert wait(app, lambda: item.childCount() == 1)
    panel.results.setCurrentItem(item)
    panel.retrieve_selected(open_after=True)
    assert wait(app, lambda: not w.net.active_jobs() and w.all_viewer_tabs(), 60)
    job = w.net.jobs[-1]
    assert job.status == "done" and "60 imagens" in job.message
    assert item.text(10).startswith("✓")
    assert len(w.all_viewer_tabs()[0].viewports[0].frames) == 60
    assert "PACS" in w.net_label.text() or "Nó DICOM" in w.net_label.text()


def test_move_retrieve_and_send(setup):
    app, w, pacs, nid, _ = setup
    node = w.repo.node(nid)
    node["retrieve"] = "move"
    w.repo.save_node(node)
    uid = pacs.repo.find_study_uids(accession="ACC3001")[0]
    w.net.retrieve(w.repo.node(nid), None, uid, "MG")
    assert wait(app, lambda: not w.net.active_jobs(), 60)
    assert w.net.jobs[-1].status == "done", w.net.jobs[-1].message
    assert w.repo.study_info(uid)["modalities"] == "MG"
    # envio de volta para um PACS vazio
    pacs2 = Node(w.paths.data.parent / "pacs2", "PACS2")
    try:
        assert pacs2.server.start()
        n2 = w.repo.save_node(pacs2.as_node())
        w.send_studies([uid], n2, None)
        assert wait(app, lambda: not w.net.active_jobs(), 60)
        assert w.net.jobs[-1].status == "done", w.net.jobs[-1].message
        assert pacs2.sink.flush(30) and pacs2.repo.study_info(uid) is not None
    finally:
        pacs2.close()


def test_identity_used_and_audited(setup):
    app, w, pacs, nid, _ = setup
    pacs.server.config["accept"] = "known"
    pacs.repo.save_node({"name": "WS", "ae_title": "WS-MAMA2", "host": "127.0.0.1", "port": 1})
    pacs.server.refresh_acl()
    iid = w.repo.save_identity({"name": "Estação mama", "ae_title": "WS-MAMA2",
                                "allowed_nodes": str(nid)})
    res = {}
    w.net.search([w.repo.node(nid)], w.repo.identity(iid), {"accession": "ACC3001"},
                 lambda r, e: res.update(r=r, e=e))
    assert wait(app, lambda: "r" in res)
    assert res["e"] is None and len(res["r"][0]) == 1
    assert any("WS-MAMA2" in a[3] for a in w.repo.audit_entries())
    # identidade não liberada para outro nó
    other = w.repo.save_node({"name": "X", "ae_title": "X", "host": "127.0.0.1", "port": 1})
    from ipe.network.client import DicomError
    with pytest.raises(DicomError):
        w.net.target(w.repo.node(other), w.repo.identity(iid))


def test_external_open_fetches_from_pacs(setup):
    app, w, pacs, nid, _ = setup
    assert w.handle_external({"command": "open", "accession": "ACC2001"}) == "buscando"
    assert wait(app, lambda: w.all_viewer_tabs(), 60)
    assert w.all_viewer_tabs()[0].study_info["accession"] == "ACC2001"
    assert w.handle_external({"command": "retrieve", "accession": "ACC2001"}) == "ja_no_banco"
    assert w.handle_external({"command": "open", "accession": "NAOEXISTE", "node": "nenhum"}) == \
        "nao_encontrado"


def test_http_api(setup):
    app, w, pacs, nid, http_port = setup
    out = {}

    def call(path, key):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{http_port}{path}", timeout=10) as r:
                out[key] = (r.status, json.loads(r.read()))
        except urllib.error.HTTPError as e:
            out[key] = (e.code, json.loads(e.read()))

    for path, key in (("/api/status?token=segredo", "status"), ("/api/open?accession=ACC1001", "notoken"),
                      ("/api/open?accession=ACC1001&token=segredo", "open"),
                      ("/api/open?accession=ACC1001;rm&token=segredo", "bad")):
        th = threading.Thread(target=call, args=(path, key))
        th.start()
        assert wait(app, lambda: key in out, 20)
        th.join()
    assert out["status"][0] == 200 and "Nó DICOM" in out["status"][1]["status"]
    assert out["notoken"][0] == 401
    assert out["open"] == (200, {"ok": True, "resultado": "buscando"})
    assert out["bad"][0] == 400
    assert wait(app, lambda: w.all_viewer_tabs(), 60)


def test_parse_url():
    assert parse_url("dicomviewer://open?accession=123&node=PACS") == \
        {"command": "open", "accession": "123", "node": "PACS"}
    assert parse_url("dicomviewer://retrieve/?studyuid=1.2.3")["study_uid"] == "1.2.3"
    for bad in ("dicomviewer://delete?accession=1", "http://x/open?accession=1",
                "dicomviewer://open?accession=1%26calc", "dicomviewer://open"):
        with pytest.raises(ExternalError):
            parse_url(bad)
