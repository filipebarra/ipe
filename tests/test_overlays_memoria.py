"""Ligar e desligar os overlays de CAD/IA — e o programa lembrar da escolha.

O relato: "criei overlays com uma IA. Eles estão aparecendo na imagem e me atrapalham".
Desligar já existia (botão CAD/IA, Shift+I); o que faltava era não ter de desligar de novo
a cada exame. A memória é por tipo (SEG, GSPS, SR…): quem não quer ver a segmentação da IA
continua querendo ver as anotações que o técnico deixou no aparelho.
"""
import pytest

from ipe.core.config import Settings
from ipe.imaging import overlays as O


class _Obj:
    def __init__(self, source, enabled=True):
        self.source, self.enabled = source, enabled


class _Aba:
    """Só o que a memória dos overlays usa da aba do viewer."""
    from ipe.ui.viewer.onco import OncoMixin as _Mix
    lembrar_tipos = _Mix.lembrar_tipos
    mostrar_tipo = _Mix.mostrar_tipo
    mostrar_todos = _Mix.mostrar_todos
    toggle_overlays = _Mix.toggle_overlays

    def __init__(self, settings, objs):
        self.settings = settings
        self.overlay_objects = objs
        self.recados = []

    def _apply_overlays(self):
        pass

    @property
    def status_message(self):
        aba = self

        class _Sinal:
            @staticmethod
            def emit(t):
                aba.recados.append(t)
        return _Sinal


def _settings(tmp_path):
    return Settings(tmp_path / "settings.json")


def test_nada_oculto_por_padrao(tmp_path):
    s = _settings(tmp_path)
    assert O.tipos_ocultos(s) == set()
    O.guardar_tipos_ocultos(s, {"SEG"})
    assert O.tipos_ocultos(s) == {"SEG"}
    assert O.tipos_ocultos(None) == set()
    # a escolha sobrevive ao fechar o programa
    assert O.tipos_ocultos(Settings(tmp_path / "settings.json")) == {"SEG"}


def test_desligar_um_tipo_nao_desliga_os_outros(tmp_path):
    s = _settings(tmp_path)
    aba = _Aba(s, [_Obj("SEG"), _Obj("SEG"), _Obj("GSPS")])
    aba.mostrar_tipo("SEG", False)
    assert [o.enabled for o in aba.overlay_objects] == [False, False, True]
    assert O.tipos_ocultos(s) == {"SEG"}
    aba.mostrar_tipo("SEG", True)
    assert all(o.enabled for o in aba.overlay_objects) and O.tipos_ocultos(s) == set()


def test_o_botao_lembra_dos_tipos_do_exame(tmp_path):
    s = _settings(tmp_path)
    aba = _Aba(s, [_Obj("SEG"), _Obj("GSPS")])
    aba.toggle_overlays()                       # algum visível -> oculta todos
    assert not any(o.enabled for o in aba.overlay_objects)
    assert O.tipos_ocultos(s) == {"GSPS", "SEG"}
    assert "próximos exames" in aba.recados[-1]
    aba.toggle_overlays()                       # mostra todos -> para de lembrar
    assert all(o.enabled for o in aba.overlay_objects) and O.tipos_ocultos(s) == set()


def test_todo_tipo_tem_nome_na_tela():
    """Menu com o código cru (SEG, PR) não diz nada a quem lê: todo tipo precisa de rótulo."""
    for t in ("SEG", "GSPS", "SR", "RTSTRUCT", "CAD"):
        assert O.TIPOS.get(t) and not O.TIPOS[t].startswith("{")
