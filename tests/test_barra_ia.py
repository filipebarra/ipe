"""0.100.37: as IAs da barra num botão só ("IA"), com a lista das que valem para o exame — como a lista das medidas.
O botão de cada IA sai da barra; a escolha de mostrar cada uma com o seu botão continua no menu."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_achados_nodulos import _exame  # noqa: E402


def test_botao_ia_junta_as_ias(env, tmp_path):
    from PySide6.QtWidgets import QApplication

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    from ipe.ui.viewer import aplicacoes as AP
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    _exame(env, tmp_path)
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1300, 800)
    w.show()
    try:
        assert w.handle_external({"accession": "NOD01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        assert tab._acao_ia.isVisible()
        # os botões das IAs saíram da barra; as que não são de IA continuam
        assert not any(tab._apps[a][1].isVisible() for a in AP.IA if a in tab._apps)
        assert tab._apps["mpr"][1].isVisible()
        valem, outras = tab.ias_do_exame()
        assert "nodulos" in valem and "enfisema" in valem and "brats" in dict(outras)
        assert tab.app_na_barra("nodulos")
        tab._encher_menu_ia()
        textos = [a.text() for a in tab.ia_menu.actions()]
        assert "Nódulos" in textos and "Achados de IA (revisar, confirmar, descartar)…" in textos
        assert any(t.startswith("Outras IAs") for t in textos)
        sub = next(a.menu() for a in tab.ia_menu.actions() if a.text() == "Nódulos")
        itens = [a.text() for a in sub.actions()]
        assert itens == ["Procurar nódulos pulmonares nesta série (IA)…"]      # os achados vão no fim da lista
        # cada uma com o seu botão, como antes
        tab.agrupar_ia(False)
        app.processEvents()
        assert not tab._acao_ia.isVisible() and tab._apps["nodulos"][1].isVisible()
        assert w.settings.get(AP.CHAVE_IA_AGRUPADA) is False
        tab.agrupar_ia(True)
        assert tab._acao_ia.isVisible() and not tab._apps["nodulos"][1].isVisible()
    finally:
        w._really_quit = True
        w.settings.set("ui.confirmar_sair", False)
        w.close()
