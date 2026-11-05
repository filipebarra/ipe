"""0.99.57 — PDF e imagens anexados ao exame, convertidos para DICOM (Encapsulated PDF e Secondary Capture)."""
from _menus import submenu, todas  # noqa: F401
from pathlib import Path

import numpy as np
import pydicom
import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QMessageBox

from ipe.core.config import Settings
from ipe.importer import anexos as AX


def _pdf(p: Path) -> Path:
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(p))
    c.drawString(100, 750, "Pedido medico")
    c.save()
    return p


def _img(p: Path, w=40, h=30, cor=(200, 10, 30)) -> Path:
    img = QImage(w, h, QImage.Format_RGB888)
    img.fill(QColor(*cor))
    assert img.save(str(p))
    return p


def test_separar_e_converter(tmp_path, sample_dir):
    QApplication.instance() or QApplication([])
    pdf, png = _pdf(tmp_path / "pedido.pdf"), _img(tmp_path / "foto.png")
    (tmp_path / "laudo.docx").write_bytes(b"PK")
    (tmp_path / "x.dcm").write_bytes(b"")
    docs, resto, recusados = AX.separar([pdf, png, tmp_path / "laudo.docx", tmp_path / "x.dcm", tmp_path])
    assert docs == [pdf, png] and [p.name for p in recusados] == ["laudo.docx"] and len(resto) == 2
    fonte = next(Path(sample_dir).rglob("*.dcm"))
    src = pydicom.dcmread(fonte, stop_before_pixels=True)
    dss, avisos = AX.criar([pdf, png, tmp_path / "laudo.docx"], str(fonte), "Dr. Teste")
    assert len(dss) == 2 and "salve como PDF" in avisos[0]
    d, im = dss
    assert d.SOPClassUID == AX.ENCAPSULATED_PDF and d.Modality == "DOC" and d.DocumentTitle == "pedido"
    assert bytes(d.EncapsulatedDocument).startswith(b"%PDF")
    assert d.StudyInstanceUID == src.StudyInstanceUID and d.PatientID == src.PatientID
    assert im.SOPClassUID == AX.SECONDARY_CAPTURE and im.Modality == "OT" and (im.Rows, im.Columns) == (30, 40)
    assert d.SeriesInstanceUID != im.SeriesInstanceUID
    out = AX.gravar(dss, tmp_path / "out")
    lido = pydicom.dcmread(out[1])
    assert lido.pixel_array.shape == (30, 40, 3) and tuple(lido.pixel_array[0, 0]) == (200, 10, 30)
    dados, mime, titulo = AX.documento_de(str(out[0]))
    assert dados.startswith(b"%PDF") and dados.rstrip().endswith(b"%%EOF") and titulo == "pedido"
    falso = tmp_path / "falso.pdf"
    falso.write_bytes(b"nada")
    assert "não parece um PDF" in AX.criar([falso], src)[1][0]               # Dataset como fonte também vale


def test_tiff(tmp_path):
    QApplication.instance() or QApplication([])
    from PySide6.QtGui import QImageWriter
    if b"tiff" not in [bytes(f) for f in QImageWriter.supportedImageFormats()]:
        pytest.skip("sem escritor de TIFF")
    p = tmp_path / "scan.tif"
    a = QImage(10, 8, QImage.Format_RGB888)
    a.fill(QColor(1, 2, 3))
    assert a.save(str(p))
    pags = AX.paginas_da_imagem(p)
    assert len(pags) == 1 and pags[0].shape == (8, 10, 3) and tuple(pags[0][0, 0]) == (1, 2, 3)


def test_na_janela_principal(env, sample_dir, tmp_path, monkeypatch):
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    try:
        uid = repo.search_studies()[0].study_uid
        n0 = len(repo.series_for_study(uid, ocultas=True))
        pdf, png = _pdf(tmp_path / "termo.pdf"), _img(tmp_path / "pedido.jpg")
        # pergunta no banco de dados; "não" não grava nada
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
        assert w.anexar_ao_exame(uid, [pdf], confirmar=True)["n"] == 0
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
        r = w.anexar_ao_exame(uid, [pdf, png], confirmar=True)
        assert r["n"] == 2 and len(r["series"]) == 2
        series = repo.series_for_study(uid, ocultas=True)
        assert len(series) == n0 + 2
        mods = {s.description: s.modality for s in series}
        assert mods[AX.DESC_DOC] == "DOC" and mods[AX.DESC_IMG] == "OT"
        assert any(a["action"] == "anexou_documento" for a in repo.access_log(limit=20))
        # alvo do arrasto: exame selecionado no banco
        w.browser.refresh()
        app.processEvents()
        w.browser.select_study(uid)
        app.processEvents()
        assert w.alvo_dos_anexos(w.browser.table.viewport()) == (uid, True)
        # recusado avisa; sem exame selecionado avisa e não grava
        avisos = []
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: avisos.append(a[2]))
        doc = tmp_path / "x.docx"
        doc.write_bytes(b"PK")
        assert w.anexar_soltos([], [doc], w.browser) is None and "salve como PDF" in avisos[-1]
        w.browser.table.clearSelection()
        assert w.anexar_soltos([pdf], [], w.browser) is None and "selecione um exame" in avisos[-1]
        # documentos do exame: lista e abre o PDF
        d = w.abrir_documentos(uid)
        assert d.lista.count() == 1 and d.docs[0]["titulo"] == "termo"
        from PySide6.QtPdf import QPdfDocument
        app.processEvents()
        assert d.pdf.status() in (QPdfDocument.Status.Ready, QPdfDocument.Status.Loading)
        d.close()
        # menu do exame e da série no visualizador
        textos = [a.text() for a in todas(w.browser.menu_do_exame([w.browser.selected_rows()[0]]
                                                              if w.browser.selected_rows() else
                                                              [repo.search_studies()[0]]))]
        assert "Anexar documento (PDF ou imagem)…" in textos and "Documentos do exame…" in textos
        w.open_study(uid)
        app.processEvents()
        tab = w.all_viewer_tabs()[-1]
        assert any(s.description == AX.DESC_IMG for s in tab.series)            # a foto aparece como imagem
        assert w.alvo_dos_anexos(tab.viewports[0]) == (uid, False)
        txt = [a.text() for a in tab.menu_de_series(tab.viewports[0]).actions()]
        assert any(t.startswith("📄 Documentos do exame (1 série(s))") for t in txt)
    finally:
        w.close()


def test_anexo_segue_o_roteamento(env, sample_dir, tmp_path, monkeypatch):
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    QApplication.instance() or QApplication([])
    nid = repo.save_node({"name": "PACS", "kind": "dimse", "ae_title": "PACS", "host": "127.0.0.1", "port": 104})
    repo.save_rule({"kind": "route", "name": "tudo ao PACS", "active": True,
                    "config": {"node_id": nid, "origins": ["received"]}})
    w = MainWindow(paths, Settings(paths.settings_file))
    try:
        enviados = []
        monkeypatch.setattr(w.net, "send", lambda node, ident, uids, label, series_uids=None:
                            enviados.append((node["name"], uids, series_uids)))
        uid = repo.search_studies()[0].study_uid
        r = w.anexar_ao_exame(uid, [_pdf(tmp_path / "a.pdf")])
        assert r["enviados"] == 1 and enviados[0][0] == "PACS" and enviados[0][2] == r["series"]
    finally:
        w.close()
