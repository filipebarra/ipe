"""Abrir enquanto baixa (streaming), teste de rede, histograma e medidas em planilha."""
import shutil

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer
from ipe.network import probe


def test_probe_estimate_and_learn(tmp_path):
    st = Settings(tmp_path / "s.json")
    # sem histórico: usa o tamanho típico por modalidade
    e = probe.estimate(st, 1, 200, "CT")
    assert e["mb"] == pytest.approx(104, abs=1) and not e["known"]
    assert probe.estimate(st, 1, 4, "MG")["mb"] == pytest.approx(48)
    # aprende com um download: 100 MB em 50 s, 200 imagens
    probe.learn(st, 1, 100, 50, 200)
    e = probe.estimate(st, 1, 400, "CT")
    assert e["known"] and e["mbps"] == pytest.approx(2.0)
    assert e["mb"] == pytest.approx(200) and e["seconds"] == pytest.approx(100)
    probe.learn(st, 1, 100, 25, 200)             # rede ficou mais rápida: média móvel
    assert 2.0 < probe.node_stats(st, 1)["mbps"] < 4.0
    probe.learn_latency(st, 1, 210)
    assert "lenta" in probe.summary(st, 1) and "210" in probe.summary(st, 1)     # 210 ms = rede lenta
    probe.learn_latency(st, 1, 40)
    assert "lenta" not in probe.summary(st, 1)
    # perguntar ou não
    assert probe.should_ask(st, 40) and not probe.should_ask(st, 5)
    st.set("network.stream_ask", False)
    assert not probe.should_ask(st, 400)
    # padrão e opção do nó
    st.set("network.stream_default", True)
    assert probe.stream_enabled({"stream_open": None}, st)
    assert not probe.stream_enabled({"stream_open": False}, st)
    assert probe.stream_enabled({"stream_open": True}, Settings(tmp_path / "t.json"))
    assert probe.fmt_time(30) == "30 s" and probe.fmt_time(180) == "3 min"
    assert probe.fmt_size(2048) == "2.0 GB"


def test_stream_open_and_rescan(env, sample_dir, tmp_path):
    """Exame chegando aos poucos: abre no primeiro lote e vai acrescentando as imagens."""
    from ipe.network.service import Job
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    files = sorted((sample_dir / "CT_ACC1001").glob("*.dcm"))
    part1, part2 = tmp_path / "p1", tmp_path / "p2"
    part1.mkdir()
    part2.mkdir()
    for f in files[:10]:
        shutil.copy(f, part1)
    for f in files[10:]:
        shutil.copy(f, part2)
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1200, 800)
    w.show()
    Importer(db, paths.storage).import_paths([part1])
    w.browser.refresh()
    uid = repo.search_studies()[0].study_uid
    job = Job("retrieve", "TC tórax", {"id": 1, "name": "PACS"}, None, [uid], None, True, True)
    job.status = "running"
    w.net.jobs.append(job)
    w._stream_progress({uid})
    assert job.opened and w.all_viewer_tabs()
    tab = w.all_viewer_tabs()[-1]
    vp = tab.viewports[0]
    app.processEvents()
    assert len(vp.frames) == 10
    idx0, win0 = vp.index, (vp.state.width, vp.state.level)
    # chega o resto: a lista cresce, o corte continua o mesmo e a janela não muda
    sop0 = vp.frames[vp.index].sop_uid
    Importer(db, paths.storage).import_paths([part2])
    assert tab.rescan(uid)
    assert len(vp.frames) == 60
    assert vp.frames[vp.index].sop_uid == sop0 and (vp.state.width, vp.state.level) == win0
    assert not tab.rescan(uid)                   # nada novo: não mexe
    # ao terminar, o job aprende a velocidade do nó
    job.status, job.started, job.finished = "done", 0.0, 10.0
    import time as _t
    job.started, job.finished = _t.time() - 10, _t.time()
    w._learn_network(job)
    assert probe.node_stats(w.settings, 1).get("mbps", 0) > 0
    w.close()


def test_histogram_and_measures_table(env, sample_dir, tmp_path):
    from ipe.imaging.measure import Annotation
    from ipe.ui.main_window import MainWindow
    from ipe.ui.viewer.histogram import HistogramDialog
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    Importer(db, paths.storage).import_paths([sample_dir])
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1200, 800)
    w.show()
    w.browser.refresh()
    w.handle_external({"accession": "ACC1001"})
    tab = w.all_viewer_tabs()[-1]
    tab.set_layout(1, 1)
    vp = tab.viewports[0]
    app.processEvents()
    # histograma da imagem inteira
    dlg = HistogramDialog(vp, tab)
    assert dlg.view.counts.sum() == vp._img.pixels.size
    assert "pixels" in dlg.info.text() and "janela atual" in dlg.info.text()
    dlg.apply_window(5, 95)
    assert vp.state.window_set and vp.state.width > 0
    w95 = vp.state.width
    # com uma ROI selecionada, mostra só o que está dentro dela
    roi = Annotation("ellipse", vp.frame_key(), [(100.0, 100.0), (140.0, 140.0)], study_uid=vp.study_uid,
                     series_uid=vp.series_uid)
    vp.annotations.append(roi)
    vp._store("save", roi)
    vp.selected = roi
    dlg.refresh()
    dlg.source.setCurrentIndex(1)
    dlg.refresh()
    assert 0 < dlg.view.counts.sum() < vp._img.pixels.size
    dlg.apply_window(1, 99)
    assert vp.state.width != w95
    dlg.copy()
    assert QApplication.clipboard().text().startswith("valor;contagem")
    dlg.close()
    # medidas em planilha
    line = Annotation("line", vp.frame_key(), [(10.0, 10.0), (30.0, 10.0)], study_uid=vp.study_uid,
                      series_uid=vp.series_uid)
    vp.annotations.append(line)
    vp._store("save", line)
    from ipe.exporter.measures_table import export_measures, rows_for_studies
    rows = rows_for_studies(repo, [vp.study_uid])
    kinds = {r[8] for r in rows}
    assert {"Régua", "ROI elíptica"} <= kinds
    reg = next(r for r in rows if r[8] == "Régua")
    assert reg[0].startswith("TESTE") and reg[9] == "30.0 mm" and reg[6] == "CT"
    out = tmp_path / "medidas.csv"
    assert export_measures(repo, [vp.study_uid], out) == len(rows)
    text = out.read_text(encoding="utf-8-sig")
    assert text.splitlines()[0].startswith("Paciente;ID;") and "30.0 mm" in text
    anon = rows_for_studies(repo, [vp.study_uid], anonymize=True)
    assert all(not r[0] and not r[1] for r in anon)
    w.close()
