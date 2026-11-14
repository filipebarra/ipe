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


def _sem_repeticao(cls, minimo):
    partes = [cls] + [c for c in cls.__mro__[1:] if c.__module__.startswith("ipe.")]
    assert len(partes) >= minimo, [c.__name__ for c in partes]
    vistos = {}
    for c in partes:
        for n, v in vars(c).items():
            if n.startswith("__"):
                continue
            # só o que foi escrito na própria classe (o conftest troca alguns métodos por lambdas nos testes)
            f = getattr(v, "__func__", v)
            if not getattr(f, "__qualname__", "").startswith(c.__name__ + "."):
                continue
            if n in vistos and vistos[n][1] is not v:
                raise AssertionError(f"{n} em {vistos[n][0]} e em {c.__name__}")
            vistos.setdefault(n, (c.__name__, v))


def test_viewport_e_janela_principal_sem_metodo_encoberto():
    """0.100.42: o Viewport (desenho, mouse e teclado, menus, mamografia) e a janela principal (impressões, bancos,
    filme do US, documentos) também foram divididos; nenhuma parte pode esconder outra."""
    from ipe.ui.main_window import MainWindow
    from ipe.ui.viewer.viewport import HOTSPOTS_DOS_DOIS_BOTOES, Viewport
    from ipe.ui.viewer.viewport_eventos import HOTSPOTS_DOS_DOIS_BOTOES as H2
    _sem_repeticao(Viewport, 6)
    _sem_repeticao(MainWindow, 5)
    assert HOTSPOTS_DOS_DOIS_BOTOES is H2
