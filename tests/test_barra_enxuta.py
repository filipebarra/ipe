"""A barra do visualizador: menos botões, e nada perdido.

Eram 31 numa linha só. Quatro saíram para o menu "Mais" — e o teste existe para garantir que
sair da barra não é sumir: a ação tem de continuar alcançável, e dá para trazer de volta.
"""
import pytest
from PySide6.QtWidgets import QApplication, QToolBar

from ipe.core.config import Settings
from ipe.importer.scanner import Importer
from ipe.ui.viewer.viewer_tab import ViewerTab


@pytest.fixture()
def aba(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    w.browser.refresh()
    w.open_study(repo.search_studies()[0].study_uid)
    app.processEvents()
    yield app, w, w.all_viewer_tabs()[-1]
    w.close()


def _barra(tab):
    return tab.findChildren(QToolBar)[1]


def _visiveis(tab) -> list[str]:
    tb = _barra(tab)
    out = []
    for a in tb.actions():
        if a.isSeparator() or not a.isVisible():
            continue
        wd = tb.widgetForAction(a)
        t = (wd.text() if hasattr(wd, "text") else "") or a.text()
        if t:
            out.append(t)
    return out


def test_os_quatro_sairam_da_barra(aba):
    app, w, tab = aba
    nomes = _visiveis(tab)
    assert "Inverter" not in nomes and "Girar" not in nomes
    assert "Cine" not in nomes and "Ocultar" not in nomes
    assert len(nomes) <= 24, f"ainda são muitos: {len(nomes)}"
    # o que importa continua lá
    for essencial in ("Janela", "Zoom", "Rolar", "Layout", "Medidas", "Laudo", "Mais"):
        assert essencial in nomes, f"sumiu o {essencial}"


def test_o_que_saiu_esta_no_menu_mais(aba):
    """Botão escondido não pode virar função perdida."""
    app, w, tab = aba
    tb = _barra(tab)
    botao = next(tb.widgetForAction(a) for a in tb.actions()
                 if tb.widgetForAction(a) is not None
                 and getattr(tb.widgetForAction(a), "text", lambda: "")() == "Mais")
    textos = [a.text() for a in botao.menu().actions()]
    for aid in ViewerTab.FORA_POR_PADRAO:
        acao = tab.actions_by_id.get(aid)
        assert acao is not None and acao.text() in textos, f"{aid} não está no menu Mais"


def test_da_para_trazer_de_volta(env, sample_dir):
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    st = Settings(paths.settings_file)
    st.set("viewer.botoes_fora", [])              # ele marcou todos de volta nas preferências
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, st)
    w.show()
    w.browser.refresh()
    w.open_study(repo.search_studies()[0].study_uid)
    app.processEvents()
    nomes = _visiveis(w.all_viewer_tabs()[-1])
    assert "Inverter" in nomes and "Cine" in nomes and "Ocultar" in nomes
    w.close()


def test_a_caixa_das_preferencias_grava(env, tmp_path):
    from ipe.ui import preferences as P
    QApplication.instance() or QApplication([])
    st = Settings(tmp_path / "s.json")
    dlg = P.PreferencesDialog(st)
    assert set(dlg.c_botoes) == set(ViewerTab.NOME_DOS_OPCIONAIS)
    assert not dlg.c_botoes["view.cine"].isChecked()      # fora da barra de fábrica
    dlg.c_botoes["view.cine"].setChecked(True)
    dlg._save()
    dlg.close()
    assert "view.cine" not in st.get("viewer.botoes_fora")
    assert "view.invert" in st.get("viewer.botoes_fora")
