"""0.100.39: a barra de ferramentas saiu do `viewer_tab.py` para `ui/viewer/barra.py` (BarraMixin), sem mudar nada
para quem usa o ViewerTab."""


def test_a_barra_e_parte_do_viewer_tab():
    from ipe.ui.viewer import viewer_tab as VT
    from ipe.ui.viewer.barra import BarraMixin
    assert issubclass(VT.ViewerTab, BarraMixin)
    for nome in ("_build_toolbar", "_button", "_encher_menu_ia", "agrupar_ia", "set_button_tool", "eventFilter",
                 "set_anotacoes", "copiar_quadro", "set_left_tool"):
        assert nome in vars(BarraMixin), nome
        assert getattr(VT.ViewerTab, nome) is vars(BarraMixin)[nome], nome


def test_nenhum_metodo_da_barra_e_encoberto():
    """Um método com o mesmo nome no ViewerTab (ou no OncoMixin) esconderia o da barra em silêncio."""
    from ipe.ui.viewer import viewer_tab as VT
    from ipe.ui.viewer.barra import BarraMixin
    from ipe.ui.viewer.onco import OncoMixin
    barra = {n for n in vars(BarraMixin) if not n.startswith("__")}
    assert not barra & set(vars(VT.ViewerTab)), barra & set(vars(VT.ViewerTab))
    assert not barra & set(vars(OncoMixin)), barra & set(vars(OncoMixin))


def test_os_nomes_antigos_continuam_no_viewer_tab():
    from ipe.ui.viewer import viewer_tab as VT
    from ipe.ui.viewer import barra as B
    for nome in ("LAYOUTS", "SLAB_CHOICES", "MEASURE_TOOLS", "TOOL_ICONS", "TOOL_SHORT"):
        assert getattr(VT, nome) is getattr(B, nome)
