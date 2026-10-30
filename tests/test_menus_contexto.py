"""Os menus mostram só o que serve na tela em que ele está.

O relato: "tem coisa que não faz sentido, como o menu de layout no banco de dados". Eram onze
linhas "Layout N × M" no menu Exibir que, fora de um exame, caíam num `return` calado.
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


def _menu(w, titulo: str):
    return next(a.menu() for a in w.menuBar().actions() if a.text().replace("&", "") == titulo)


def _visiveis(menu) -> list[str]:
    return [a.text() for a in menu.actions() if a.isVisible() and not a.isSeparator()]


def test_no_banco_de_dados_nao_ha_layout_nem_monitor(janela):
    app, w = janela
    exibir = _menu(w, "Exibir")
    w.ajustar_menu_exibir(exibir)
    itens = _visiveis(exibir)
    assert not any("Layout" in t for t in itens), f"layout aparecendo no banco: {itens}"
    assert not any("monitor" in t for t in itens if "Calibração" not in t)
    assert "Voltar ao banco de dados" not in itens, "ele já está no banco"
    assert "Preferências…" in itens and "Calibração GSDF do monitor…" in itens


def test_com_exame_aberto_o_layout_aparece(janela):
    app, w = janela
    w.open_study(w.repo.search_studies()[0].study_uid)
    app.processEvents()
    exibir = _menu(w, "Exibir")
    w.ajustar_menu_exibir(exibir)
    itens = _visiveis(exibir)
    assert "Layout dos quadros" in itens
    assert "Mover estudo atual para o monitor" in itens
    assert "Voltar ao banco de dados" in itens


def test_o_layout_virou_um_submenu_so(janela):
    app, w = janela
    exibir = _menu(w, "Exibir")
    sub = next(a.menu() for a in exibir.actions() if a.text() == "Layout dos quadros")
    nomes = [a.text() for a in sub.actions()]
    assert nomes[:3] == ["1 × 1", "1 × 2", "2 × 1"] and len(nomes) >= 8
    assert sum(1 for a in exibir.actions() if "×" in a.text()) == 0, "layout solto no menu de cima"


def test_trazer_de_volta_so_com_monitor_aberto(janela):
    app, w = janela
    exibir = _menu(w, "Exibir")
    w.ajustar_menu_exibir(exibir)
    assert "Trazer todos os estudos de volta" not in _visiveis(exibir)


def test_densidade_so_com_exame_na_tela(janela):
    app, w = janela
    arquivo = _menu(w, "Arquivo")
    w.ajustar_menu_arquivo(arquivo)
    assert not any("Densidade" in t for t in _visiveis(arquivo))
    w.open_study(w.repo.search_studies()[0].study_uid)
    app.processEvents()
    w.ajustar_menu_arquivo(arquivo)
    assert any("Densidade" in t for t in _visiveis(arquivo))


def test_fantomas_saiu_do_menu_arquivo(janela):
    """Ferramenta de teste no meio das ações clínicas: foi para a Ajuda."""
    app, w = janela
    assert not any("fantoma" in t.lower() for t in _visiveis(_menu(w, "Arquivo")))
    assert any("fantoma" in t.lower() for t in _visiveis(_menu(w, "Ajuda")))
