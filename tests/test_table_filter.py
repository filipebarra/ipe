"""Filtros por coluna na lista do banco de dados."""
from datetime import date

from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer
from ipe.ui.table_filter import match

TODAY = date(2026, 9, 18)


def m(f, kind, raw, shown=None):
    return match(f, kind, raw, shown if shown is not None else str(raw), TODAY)


def test_text_syntax():
    assert m("silva", "text", "JOAO^SILVA")
    assert m("joão", "text", "JOAO SILVA")                  # sem acento / maiúscula
    assert m("MG|US", "text", "US")
    assert not m("!CT", "text", "CT") and m("!CT", "text", "MR")
    assert m("RM*MAMA", "text", "RM MAMAS") and not m("=RM", "text", "RM MAMAS")
    assert m("=rm mamas", "text", "RM MAMAS")


def test_number_date_bool_syntax():
    assert m(">10", "int", 12) and not m(">10", "int", 10) and m(">=10", "int", 10)
    assert m("5..20", "int", 7) and not m("5..20", "int", 21)
    assert m("2025", "date", "20250310", "10/03/2025") and not m("2024", "date", "20250310", "10/03/2025")
    assert m("03/2025", "date", "20250310", "10/03/2025")
    assert m("01/01/2025..30/06/2025", "date", "20250310", "10/03/2025")
    assert m("30d", "date", "20260901", "01/09/2026") and not m("30d", "date", "20250101", "01/01/2025")
    assert m("hoje", "date", "20260918", "18/09/2026")
    assert m("sim", "bool", True, "🔒") and m("não", "bool", False, "")


def test_browser_filters(env, sample_dir):
    paths, db, repo = env
    QApplication.instance() or QApplication([])
    from ipe.ui.browser import KEY_INDEX
    from ipe.ui.main_window import MainWindow
    Importer(db, paths.storage).import_paths([sample_dir])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1400, 800)
    w.show()
    b = w.browser
    b.refresh()
    total = b.proxy.rowCount()
    assert total >= 4 and not b.btn_clear_filters.isEnabled()
    b.set_column_filter("modalities", "MG|US")
    mods = {b.proxy.data(b.proxy.index(r, KEY_INDEX["modalities"])) for r in range(b.proxy.rowCount())}
    assert mods and mods <= {"MG", "US"}
    assert "de" in b.count_label.text() and b.btn_clear_filters.isEnabled()
    # a caixa digitada também filtra (com atraso de digitação)
    b.clear_filters()
    assert b.proxy.rowCount() == total
    b.filter_header.editor(KEY_INDEX["accession"]).setText("ACC1001")
    b.filter_header._timers[KEY_INDEX["accession"]].timeout.emit()
    assert b.proxy.rowCount() == 1
    # filtro por valores (estilo Excel) soma com o de texto
    b.clear_filters()
    col = KEY_INDEX["description"]
    vals = b.column_values(col)
    b.proxy.set_value_filter(col, {vals[0]})
    assert 1 <= b.proxy.rowCount() < total
    # o filtro continua valendo após atualizar a lista
    n = b.proxy.rowCount()
    b.refresh()
    assert b.proxy.rowCount() == n
    # ocultar a coluna remove o filtro dela
    b._toggle_column("description", False)
    assert b.proxy.rowCount() == total
    # as caixas acompanham as colunas visíveis
    ed = b.filter_header.editor(KEY_INDEX["patient_name"])
    assert ed.isVisible() and not b.filter_header.editor(KEY_INDEX["description"]).isVisible()
    w.close()
