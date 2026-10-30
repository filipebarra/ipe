"""Fase 5: filmes (modelo, desenho, compositor, saídas e impressora DICOM)."""
import numpy as np
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer
from ipe.printing.film import Cell, Film, Sheet, parse_layout, pick_frames


def _c(i):
    return Cell("st", "se", f"sop{i}", 0)


def test_film_model():
    f = Film(sheets=[Sheet(2, 2)])
    last = f.add_cells([_c(i) for i in range(10)])
    assert len(f.sheets) == 3 and last == 2 and f.image_count() == 10
    assert f.sheets[2].cells[:2] == [_c(8), _c(9)] and f.sheets[2].cells[2] is None
    # grade menor: o que sobra vai para uma folha nova, nada se perde
    f.set_layout(0, 1, 2)
    assert f.image_count() == 10 and f.sheets[0].capacity == 2 and f.sheets[1].cells[0] == _c(2)
    g = Film.from_dict(f.to_dict())
    assert g.to_dict() == f.to_dict()
    assert parse_layout("3x4") == (3, 4) and parse_layout("2×5") == (2, 5)
    assert pick_frames(60, count=5) == [0, 15, 30, 44, 59]
    assert pick_frames(10, 2, 8, every=3) == [2, 5, 8]
    assert pick_frames(3, count=10) == [0, 1, 2]
    assert Sheet(1, 1, "A4", landscape=True).page_mm() == (297, 210)


def _window(env, sample_dir):
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    Importer(db, paths.storage).import_paths([sample_dir])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1300, 850)
    w.show()
    w.browser.refresh()
    return app, w, repo


def test_viewer_to_film_and_outputs(env, sample_dir, tmp_path):
    app, w, repo = _window(env, sample_dir)
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    tab = w.tabs.currentWidget()
    app.processEvents()
    vp = tab.viewports[0]
    vp.set_window(800, 100)
    tab.film_add_current()                     # botão Filme / Ctrl+F
    comp = w.film_composer()
    # o filme abre como painel ao lado dos quadros (não é aba) e o exame continua na frente
    assert w.tabs.indexOf(comp) < 0 and w.tabs.currentWidget() is tab
    assert tab.film_panel_visible() and comp.parentWidget() is tab.film_holder
    c0 = comp.film.sheets[0].cells[0]
    assert c0 is not None and c0.width == 800 and c0.level == 100 and c0.series_uid == vp.series_uid
    assert c0.sop_uid == vp.current_frame().sop_uid and "TESTE" in comp.film.name
    # série inteira/intervalo: 13 imagens numa grade 3x4 -> 2 folhas
    frames = comp.src.frames(vp.series_uid)
    comp.place_cells([comp._cell_for(vp.series_uid, i) for i in pick_frames(len(frames), count=13)])
    assert comp.film.image_count() == 14 and len(comp.film.sheets) == 2
    # imagens-chave
    st = tab.study_uid
    f5 = frames[5]
    repo.toggle_key_image(st, vp.series_uid, f5.sop_uid, f5.frame_index)
    assert comp.add_key_images(st) == 1
    # expandir o filme (como 1x1) e voltar
    comp.expand_requested.emit()
    assert tab.film_expanded and not tab.grid_host.isVisible()
    comp.expand_requested.emit()
    assert not tab.film_expanded and tab.grid_host.isVisible()
    # edição por célula (na tela)
    comp.go_to_sheet(0)
    app.processEvents()
    cw = comp.view.cells[1]
    cw.rotate(90)
    cw.toggle_flip()
    assert comp.film.sheets[0].cells[1].rotation == 90 and comp.film.sheets[0].cells[1].flip_h
    # trocar de lugar arrastando pela alça ⠿ (0.78: troca as duas; as outras não se mexem)
    a, b = comp.film.sheets[0].cells[0], comp.film.sheets[0].cells[3]
    comp._dropped(comp.view.cells[3], "cell", "0,0")
    assert comp.film.sheets[0].cells[3] is a and comp.film.sheets[0].cells[0] is b
    comp.remove_cell((0, 3))
    assert comp.film.sheets[0].cells[3] is None
    # salvar e reabrir
    comp.film.name = "Filme teste"
    fid = comp.film_id = repo.save_film(comp.film.name, comp.film.to_dict(), comp.film.study_uids(), "x")
    comp.dirty = False
    data = repo.film_data(fid)
    assert repo.films(st)[0]["images"] == comp.film.image_count()
    comp.new_film()
    assert comp.film.image_count() == 0
    assert comp.load_film(fid) and comp.film.to_dict() == Film.from_dict(data).to_dict()
    # estudo em filme salvo fica protegido da limpeza automática
    prot = {s.study_uid: s.protected for s in repo.retention_stats()}
    assert "em filme salvo" in prot[st]
    # saídas: PDF e imagens
    pdf = comp.export_pdf(str(tmp_path / "f.pdf"))
    assert pdf and (tmp_path / "f.pdf").read_bytes()[:4] == b"%PDF"
    pngs = comp.export_images(str(tmp_path / "f.png"), dpi=60)
    assert len(pngs) == len(comp.film.sheets)
    from PySide6.QtGui import QImage
    im = QImage(pngs[0])
    assert abs(im.width() - round(210 / 25.4 * 60)) <= 1
    # layout menor em todas as folhas não perde imagens
    n = comp.film.image_count()
    comp.all_sheets.setChecked(True)
    comp.set_layout(1, 2)
    assert comp.film.image_count() == n and all(s.capacity == 2 for s in comp.film.sheets)
    comp.dirty = False
    w.close()


def test_dicom_print(env, sample_dir):
    from print_scp import FakePrinter
    from test_network import free_port
    from ipe.printing.dicom_print import PrinterConfig, dicom_print, printer_status
    app, w, repo = _window(env, sample_dir)
    st = next(r for r in repo.search_studies() if r.accession == "ACC1001")
    comp = w.film_composer()
    se = repo.series_for_study(st.study_uid)[0].series_uid
    comp.set_layout(2, 2)
    comp.place_cells([comp._cell_for(se, i) for i in range(5)])
    comp.film.sheets[1].landscape = True
    port = free_port()
    fp = FakePrinter(port)
    try:
        cfg = PrinterConfig(ae_title="FAKEPRN", host="127.0.0.1", port=port, dpi=40, film_size="")
        assert "NORMAL" in printer_status(cfg, "TESTE")
        pages = comp.dicom_pages(cfg, [0, 1])
        assert pages[0].pixels.dtype == np.uint8 and pages[0].pixels.ndim == 2
        assert pages[1].landscape and pages[1].pixels.shape[1] > pages[1].pixels.shape[0]
        res = dicom_print(cfg, pages, "TESTE")
        assert res.pages == 2 and len(fp.printed) == 2
        assert fp.film_boxes[0].FilmSizeID == "A4" and fp.film_boxes[1].FilmOrientation == "LANDSCAPE"
        img = fp.images[0].BasicGrayscaleImageSequence[0]
        assert img.Rows == pages[0].pixels.shape[0] and img.Columns == pages[0].pixels.shape[1]
        cfg.color = True
        res = dicom_print(cfg, comp.dicom_pages(cfg, [0]), "TESTE")
        assert res.pages == 1 and fp.images[-1].BasicColorImageSequence[0].SamplesPerPixel == 3
    finally:
        fp.stop()
    comp.dirty = False
    w.close()


def test_film_dialogs(env, sample_dir):
    from ipe.ui.film.dialogs import DicomPrintDialog, FilmsDialog, SeriesRangeDialog
    app, w, repo = _window(env, sample_dir)
    d = SeriesRangeDialog("Axial", 60, 10)
    assert len(d.indices()) == 12                    # > 24 imagens: 12 espalhadas por padrão
    d.r_range.setChecked(True)
    d.first.setValue(11)
    d.last.setValue(20)
    d.every.setValue(5)
    assert d.indices() == [10, 15]
    d.r_all.setChecked(True)
    assert len(d.indices()) == 60
    s = Settings(env[0].settings_file)
    p = DicomPrintDialog(s, "TESTE", 3, 1)
    p.f_name.setText("Dry")
    p.f_ae.setText("DRY")
    p.f_host.setText("10.0.0.5")
    p.f_color.setChecked(True)
    p.save()
    assert s.get("printing.dicom_printers")[0]["ae_title"] == "DRY" and s.get("printing.dicom_printers")[0]["color"]
    p2 = DicomPrintDialog(s, "TESTE", 3, 1)
    assert p2.config().host == "10.0.0.5" and p2.config().name == "Dry"
    comp = w.film_composer()
    st = next(r for r in repo.search_studies() if r.accession == "ACC1001")
    se = repo.series_for_study(st.study_uid)[0].series_uid
    comp.place_cells([comp._cell_for(se, 3)])
    fid = repo.save_film("A", comp.film.to_dict(), comp.film.study_uids(), "P")
    fd = FilmsDialog(repo, st.study_uid)
    assert fd.table.rowCount() == 1
    fd.table.selectRow(0)
    fd._open()
    assert fd.chosen == fid
    # menu da célula monta sem erro
    from PySide6.QtCore import QTimer
    w.show_film()
    app.processEvents()
    QTimer.singleShot(50, lambda: QApplication.activePopupWidget() and QApplication.activePopupWidget().close())
    comp.cell_menu(comp.view.cells[0], comp.view.cells[0].mapToGlobal(comp.view.cells[0].rect().center()))
    comp.dirty = False
    w.close()


def test_qprinter_pages(env, sample_dir, tmp_path):
    """O mesmo caminho do botão Imprimir, com o QPrinter gravando PDF (sem diálogo)."""
    from PySide6.QtPrintSupport import QPrinter
    app, w, repo = _window(env, sample_dir)
    comp = w.film_composer()
    st = next(r for r in repo.search_studies() if r.accession == "ACC1001")
    se = repo.series_for_study(st.study_uid)[0].series_uid
    comp.place_cells([comp._cell_for(se, i) for i in range(3)])
    comp.add_sheet()
    comp.sheet.paper, comp.sheet.landscape = "Filme 14×17 pol", True
    pr = QPrinter(QPrinter.HighResolution)
    pr.setOutputFormat(QPrinter.PdfFormat)
    out = tmp_path / "p.pdf"
    pr.setOutputFileName(str(out))
    comp._paint_pages(pr, 100)
    data = out.read_bytes()
    assert data[:4] == b"%PDF" and data.count(b"/Type /Page\n") + data.count(b"/Type/Page\n") + \
        data.count(b"/Type /Page ") >= 1
    comp.dirty = False
    w.close()


def test_copy_cut_paste(env, sample_dir):
    from PySide6.QtCore import Qt
    app, w, repo = _window(env, sample_dir)
    comp = w.film_composer()
    w.dock_film()
    st = next(r for r in repo.search_studies() if r.accession == "ACC1001")
    se = repo.series_for_study(st.study_uid)[0].series_uid
    comp.set_layout(2, 2)
    cells = [comp._cell_for(se, i) for i in range(4)]
    comp.place_cells(cells)
    sops = [c.sop_uid for c in cells]
    cw = comp.view.cells
    comp.select_cell(cw[0])
    comp.select_cell(cw[1], Qt.ControlModifier)
    assert comp.copy_selection() == 2
    # colar numa célula ocupada: insere e empurra; sem vaga, cria folha
    assert comp.paste((0, 1)) == 2
    flat = [c.sop_uid if c else None for sh in comp.film.sheets for c in sh.cells]
    assert flat[:6] == [sops[0], sops[0], sops[1], sops[1], sops[2], sops[3]] and len(comp.film.sheets) == 2
    assert comp.film.sheets[0].cells[1] is not cells[0]          # cópia independente
    # recortar deixa a vaga; colar numa vaga só preenche (empurra até a próxima vaga)
    comp.go_to_sheet(0)
    comp.select_cell(comp.view.cells[3])
    assert comp.cut_selection() == 1 and comp.film.sheets[0].cells[3] is None
    comp.paste((0, 3))
    assert comp.film.sheets[0].cells[3].sop_uid == sops[1] and comp.film.image_count() == 6
    # colar antes, empurrando até a vaga que existir
    comp.film.sheets[1].cells[3] = None
    n = comp.film.image_count()
    comp.clipboard = [comp._cell_for(se, 9)]
    comp.paste((1, 0))
    assert comp.film.image_count() == n + 1 and len(comp.film.sheets) == 2
    # Shift = intervalo, Del apaga a seleção
    comp.go_to_sheet(0)
    comp.select_cell(comp.view.cells[0])
    comp.select_cell(comp.view.cells[2], Qt.ShiftModifier)
    assert comp.selection == [(0, 0), (0, 1), (0, 2)]
    comp.delete_selection()
    assert comp.film.sheets[0].cells[:3] == [None, None, None]
    comp.dirty = False
    w.close()


def test_film_panel_follows_study(env, sample_dir):
    app, w, repo = _window(env, sample_dir)
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    t1 = w.tabs.currentWidget()
    w.show_film()                                  # Ctrl+P: mostra no estudo atual
    comp = w.film_composer()
    assert t1.film_panel_visible()
    w.show_film()                                  # de novo: esconde
    assert not t1.film_panel_visible()
    assert w.handle_external({"accession": "ACC2001"}) == "aberto"
    t2 = w.tabs.currentWidget()
    t2.film_add_current()                          # pedido do outro estudo leva o filme para lá
    assert t2.film_panel_visible() and comp.parentWidget() is t2.film_holder
    w._close_tab(w.tabs.indexOf(t2))               # fechar o estudo não apaga o filme
    app.processEvents()
    assert comp.film.image_count() == 1 and w._film_host is None
    w.show_film()                                  # sem estudo aberto: janela própria
    assert w._film_window is not None and w._film_window.isVisible()
    comp.dirty = False
    w.close()


def test_mouse_button_tools(env, sample_dir):
    """Clique direito/meio num ícone atribui a ferramenta a esse botão; ferramenta Filme envia ao filme."""
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest
    app, w, repo = _window(env, sample_dir)
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    tab = w.tabs.currentWidget()
    app.processEvents()
    from PySide6.QtWidgets import QToolButton
    btn = next(b for b in tab.toolbar.findChildren(QToolButton)
               if b.defaultAction() is not None and b.defaultAction().data() == "tool.pan")
    QTest.mouseClick(btn, Qt.RightButton)
    assert w.settings.get("viewer.mouse")["right"] == "pan"
    fbtn = next(b for b in tab.toolbar.findChildren(QToolButton) if b.defaultAction() is tab.film_action)
    QTest.mouseClick(fbtn, Qt.MiddleButton)
    assert w.settings.get("viewer.mouse")["middle"] == "film"
    # o esquerdo continua o mesmo
    assert tab.left_tool == "wl"
    vp = tab.viewports[0]
    # clique do meio na imagem manda para o filme
    QTest.mouseClick(vp, Qt.MiddleButton, Qt.NoModifier, QPoint(150, 150))
    comp = w.film_composer()
    assert comp.film.image_count() == 1 and tab.film_panel_visible()
    # medida no botão direito: arrastar com o direito desenha a régua
    tab.set_button_tool("right", "measure")
    n0 = len(vp.annotations)
    QTest.mousePress(vp, Qt.RightButton, Qt.NoModifier, QPoint(100, 100))
    for x in range(100, 200, 10):
        QTest.mouseMove(vp, QPoint(x, 120))
    QTest.mouseRelease(vp, Qt.RightButton, Qt.NoModifier, QPoint(200, 120))
    assert len(vp.annotations) == n0 + 1 and vp.annotations[-1].kind == "line"
    assert vp.left_tool == "wl"
    # menu dos ícones de medida: clique direito numa ferramenta do menu também atribui
    menu = tab.measure_menu
    menu.popup(tab.mapToGlobal(QPoint(10, 10)))
    app.processEvents()
    act = tab.tool_actions["angle"]
    pos = menu.actionGeometry(act).center()
    QTest.mouseClick(menu, Qt.RightButton, Qt.NoModifier, pos)
    assert w.settings.get("viewer.mouse")["right"] == "angle"
    comp.dirty = False
    w.close()


def test_film_notes(env, sample_dir, monkeypatch):
    """Seta, texto e lápis desenhados na célula ficam só no filme e seguem a imagem."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QInputDialog
    from ipe.ui.film.render import render_sheet_image
    app, w, repo = _window(env, sample_dir)
    comp = w.film_composer()
    w.dock_film()
    comp.set_layout(1, 2)
    st = next(r for r in repo.search_studies() if r.accession == "ACC1001")
    se = repo.series_for_study(st.study_uid)[0].series_uid
    comp.place_cells([comp._cell_for(se, 30)])
    app.processEvents()
    cw = comp.view.cells[0]
    cw.resize(300, 300)
    base = render_sheet_image(comp.film, 0, comp.src, comp.cache, comp.settings, dpi=50)
    comp.set_note_tool("arrow")
    QTest.mousePress(cw, Qt.LeftButton, Qt.NoModifier, QPoint(150, 150))
    for x in range(150, 230, 10):
        QTest.mouseMove(cw, QPoint(x, 200))
    QTest.mouseRelease(cw, Qt.LeftButton, Qt.NoModifier, QPoint(230, 200))
    comp.set_note_tool("pencil")
    QTest.mousePress(cw, Qt.LeftButton, Qt.NoModifier, QPoint(60, 60))
    for x in range(60, 120, 6):
        QTest.mouseMove(cw, QPoint(x, 60 + (x % 20)))
    QTest.mouseRelease(cw, Qt.LeftButton, Qt.NoModifier, QPoint(120, 70))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("nódulo", True)))
    comp.set_note_tool("text")
    QTest.mouseClick(cw, Qt.LeftButton, Qt.NoModifier, QPoint(100, 250))
    notes = comp.film.sheets[0].cells[0].notes
    assert [n["kind"] for n in notes] == ["arrow", "pencil", "text"] and notes[2]["text"] == "nódulo"
    # a janela não mudou ao anotar
    assert comp.film.sheets[0].cells[0].width is None
    # aparece na impressão
    img = render_sheet_image(comp.film, 0, comp.src, comp.cache, comp.settings, dpi=50)
    assert img != base
    # não vai para o banco de medidas do exame
    assert repo.annotation_counts([se]).get(se, 0) == 0
    # desfazer, salvar/reabrir e copiar levam as anotações
    comp.select_cell(cw)
    comp.undo_note()
    assert len(comp.film.sheets[0].cells[0].notes) == 2
    fid = repo.save_film("n", comp.film.to_dict(), comp.film.study_uids(), "")
    comp.dirty = False
    comp.load_film(fid)
    assert len(comp.film.sheets[0].cells[0].notes) == 2
    comp.select_cell(comp.view.cells[0])
    comp.copy_selection()
    comp.paste((0, 1))
    assert len(comp.film.sheets[0].cells[1].notes) == 2
    comp.set_note_tool("")
    comp.dirty = False
    w.close()
