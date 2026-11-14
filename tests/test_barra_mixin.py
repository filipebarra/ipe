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


def test_nenhum_metodo_dos_mixins_e_encoberto():
    """Um método com o mesmo nome em duas partes do ViewerTab (a classe e os mixins: barra, MPR, fusão, mamografia,
    IA, oncologia) faz uma esconder a outra em silêncio (0.100.39 e 0.100.41)."""
    from ipe.ui.viewer import viewer_tab as VT
    partes = [VT.ViewerTab] + [c for c in VT.ViewerTab.__mro__[1:] if c.__module__.startswith("ipe.")]
    assert len(partes) >= 7
    vistos = {}
    for c in partes:
        for n in vars(c):
            if n.startswith("__"):
                continue
            assert n not in vistos, f"{n} em {vistos.get(n)} e em {c.__name__}"
            vistos[n] = c.__name__


def test_os_nomes_antigos_continuam_no_viewer_tab():
    from ipe.ui.viewer import viewer_tab as VT
    from ipe.ui.viewer import barra as B
    for nome in ("LAYOUTS", "SLAB_CHOICES", "MEASURE_TOOLS", "TOOL_ICONS", "TOOL_SHORT"):
        assert getattr(VT, nome) is getattr(B, nome)
