"""Anonimizar pelo botão direito na lista do banco: um exame ou vários, perguntando o que manter.

Anonimizar é sempre cópia: o pedido vem da lista, mas nenhum arquivo do acervo é tocado.
"""
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer


@pytest.fixture()
def janela(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    w.browser.refresh()
    yield app, w
    w.close()


def _textos(menu):
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def _acao(menu, prefixo: str):
    return next(a for a in menu.actions() if a.text().startswith(prefixo))


def test_o_menu_da_lista_oferece_anonimizar(janela, monkeypatch):
    app, w = janela
    b = w.browser
    b.table.selectRow(0)
    guardado = {}
    monkeypatch.setattr(type(b), "export_rows",
                        lambda self, rows, anonimizar=False: guardado.update(n=len(rows), anon=anonimizar))
    menu = b.menu_do_exame(b.selected_rows())
    assert "Anonimizar uma cópia deste exame…" in _textos(menu)
    _acao(menu, "Anonimizar").trigger()
    assert guardado == {"n": 1, "anon": True}


def test_varios_exames_de_uma_vez(janela, monkeypatch):
    app, w = janela
    b = w.browser
    b.table.selectAll()
    rows = b.selected_rows()
    assert len(rows) > 1
    guardado = {}
    monkeypatch.setattr(type(b), "export_rows",
                        lambda self, rr, anonimizar=False: guardado.update(n=len(rr), anon=anonimizar))
    menu = b.menu_do_exame(rows)
    acao = _acao(menu, "Anonimizar")
    assert acao.text().startswith("Anonimizar cópias destes") and str(len(rows)) in acao.text()
    acao.trigger()
    assert guardado == {"n": len(rows), "anon": True}


def test_a_janela_abre_marcada_e_deixa_escolher(janela):
    """Marcada por padrão, mas editável: quem pediu anonimizar escolhe o que manter."""
    app, w = janela
    from ipe.exporter.core import ExportItem
    from ipe.ui.export_dialog import ExportDialog
    uid = w.repo.search_studies()[0].study_uid
    scopes = [("1 exame", [ExportItem(uid)])]
    d = ExportDialog(w.repo, w.settings, scopes, w, anonimizar=True)
    assert d.windowTitle() == "Anonimizar cópias"
    assert d.g_anon.isChecked() and d.g_anon.isEnabled()
    assert d.mode() == "dicom", "JPG/PNG não guardam tag: anonimizar é sobre o DICOM"
    assert d.anon_options().enabled
    d.a_dates.setChecked(True)
    d.a_inst.setChecked(False)
    o = d.anon_options()
    assert o.keep_dates and not o.keep_institution
    d.g_anon.setChecked(False)          # pode desmarcar: a janela é a de exportar
    assert not d.anon_options().enabled
    d.close()


def test_perfil_sem_direito_a_exportar_identificado_nao_desmarca(janela, monkeypatch):
    app, w = janela
    from ipe.auth import session as S
    from ipe.exporter.core import ExportItem
    from ipe.ui.export_dialog import ExportDialog
    monkeypatch.setattr(S, "can", lambda perm: perm != "export_identified")
    uid = w.repo.search_studies()[0].study_uid
    d = ExportDialog(w.repo, w.settings, [("1 exame", [ExportItem(uid)])], w)
    assert d.g_anon.isChecked() and not d.g_anon.isEnabled()
    d.close()
