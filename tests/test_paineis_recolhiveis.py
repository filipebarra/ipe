"""0.99.29: recolher Locais/listas e Séries/comentários para uma tira na borda, como no Weasis."""
from PySide6.QtWidgets import QApplication


def test_paineis_do_banco_recolhem_e_voltam(env):
    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    from ipe.ui.painel_recolhivel import LARGURA_TIRA
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    cfg = Settings(paths.settings_file)
    w = MainWindow(paths, cfg, repo=repo, db=db)
    try:
        w.resize(1400, 800)
        w.show()
        QApplication.processEvents()
        b = w.browser
        esq, dir_ = b.painel_esq, b.painel_dir
        assert not esq.recolhido and not dir_.recolhido
        largura_tabela = b.split.sizes()[1]
        # o botão do título recolhe para a tira
        esq.b_recolher.click()
        dir_.b_recolher.click()
        QApplication.processEvents()
        assert esq.recolhido and dir_.recolhido
        assert esq.width() <= LARGURA_TIRA + 4 and dir_.width() <= LARGURA_TIRA + 4
        assert b.split.sizes()[1] > largura_tabela                  # a lista de exames ganha o espaço
        assert not w.home_bar.buttons["list"].isChecked()          # o botão Listas acompanha
        assert cfg.get("browser.show_lists") is False and cfg.get("browser.painel_dir_recolhido") is True
        # clique na tira traz de volta
        dir_.tira.clicked.emit()
        QApplication.processEvents()
        assert not dir_.recolhido and dir_.width() > 100
        # o botão Listas abre o da esquerda
        w.home_bar.buttons["list"].defaultAction().trigger()
        QApplication.processEvents()
        assert not esq.recolhido and esq.width() > 100
        # menu Exibir, no banco
        from PySide6.QtWidgets import QMenu
        exibir = next(a.menu() for a in w.menuBar().actions() if a.text() == "&Exibir")
        w.ajustar_menu_exibir(exibir)
        a_esq, a_dir = exibir._paineis
        assert a_esq.isVisible() and a_esq.isChecked()
        a_dir.trigger()                                              # desmarca: recolhe
        assert dir_.recolhido
    finally:
        w.close()
    # reabrir guarda o estado
    w2 = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        assert w2.browser.painel_dir.recolhido and not w2.browser.painel_esq.recolhido
    finally:
        w2.close()
