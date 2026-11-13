"""0.100.40: o pincel abre o painel Estruturas sozinho; a letra das anotações maior ou menor pela barra."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_estruturas import exame  # noqa: E402,F401  (fixture)


def _janela(paths, db, repo, estudo):
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.open_study(estudo)
    QApplication.processEvents()
    tab = next(iter(w.all_viewer_tabs()))
    vp = next(x for x in tab.viewports if x.study_uid == estudo)
    tab._activate(vp)
    return w, tab, vp


def test_pincel_sem_painel_abre_as_estruturas_e_pinta(exame):  # noqa: F811
    paths, db, repo, estudo, _serie, _v = exame
    w, tab, vp = _janela(paths, db, repo, estudo)
    try:
        assert getattr(tab, "_estruturas", None) is None
        msgs = []
        tab.status_message.connect(msgs.append)
        vp.go_to(10)
        tab.set_left_tool("pincel")
        vp.sig.pincel.emit(vp, 32.5, 32.5, "ini")
        vp.sig.pincel.emit(vp, 32.5, 28.5, "meio")
        vp.sig.pincel.emit(vp, 32.5, 28.5, "fim")
        painel = tab._estruturas
        assert painel.isVisible() and painel.grade is not None
        assert len(painel.estruturas) == 1 and painel.estruturas[0].voxels > 0      # a estrutura nova, já pintada
        assert any("painel Estruturas aberto" in m for m in msgs)
        assert not any("3D ▸ Estruturas" in m for m in msgs)
        painel._gravado = True
        painel.close()
    finally:
        w.close()


def test_letra_das_anotacoes(exame):  # noqa: F811
    paths, db, repo, estudo, _serie, _v = exame
    w, tab, vp = _janela(paths, db, repo, estudo)
    try:
        assert {"view.letra_maior", "view.letra_menor", "view.letra_normal"} <= set(tab.actions_by_id)
        assert tab.letra_info in tab.anot_menu.actions()
        base = vp.escala_da_letra("viewer.overlay_font_scale")
        assert tab.mudar_letra(+1) == round(base + 0.1, 2)
        assert vp.escala_da_letra("viewer.overlay_font_scale") == round(base + 0.1, 2)
        assert tab.letra_info.text().endswith(f"{round((base + 0.1) * 100)}%")
        for _ in range(40):
            tab.mudar_letra(+1)
        assert tab.settings.get("viewer.overlay_font_scale") == 2.5                 # o limite de cima
        for _ in range(40):
            tab.mudar_letra(-1)
        assert tab.settings.get("viewer.overlay_font_scale") == 0.6                 # o de baixo
        tab.actions_by_id["view.letra_normal"].trigger()
        assert tab.settings.get("viewer.overlay_font_scale") == 1.0
        from ipe.core.config import Settings
        assert Settings(paths.settings_file).get("viewer.overlay_font_scale") == 1.0   # gravado
    finally:
        w.close()
