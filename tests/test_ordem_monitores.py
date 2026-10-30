"""A ordem dos monitores é do usuário, não do sistema.

Na mamografia o número importa: a etapa diz "com 2 telas, mostrar no Monitor 2". Se o Monitor 2
do programa não for o monitor 2 da mesa, o arranjo sai espelhado.
"""
import pytest
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.ui import monitors as M


class _Tela:
    def __init__(self, nome, x=0, w=1920, h=1080):
        self._n, self._g = nome, QRect(x, 0, w, h)

    def name(self):
        return self._n

    def model(self):
        return ""

    def serialNumber(self):
        return ""

    def geometry(self):
        return self._g


@pytest.fixture()
def telas(monkeypatch):
    QApplication.instance() or QApplication([])
    t = [_Tela("DP-1", 0), _Tela("DP-2", 1920), _Tela("DP-3", 3840)]
    monkeypatch.setattr(M.QGuiApplication, "screens", staticmethod(lambda: list(t)))
    return t


def test_sem_configurar_vale_a_ordem_do_sistema(telas, tmp_path):
    st = Settings(tmp_path / "s.json")
    assert [s.name() for s in M.telas_ordenadas(st)] == ["DP-1", "DP-2", "DP-3"]
    assert M.numero_da_tela(st, telas[1]) == 2


def test_a_ordem_escolhida_manda(telas, tmp_path):
    st = Settings(tmp_path / "s.json")
    st.set("monitors", {"DP-1": {"ordem": 3}, "DP-2": {"ordem": 1}, "DP-3": {"ordem": 2}})
    assert [s.name() for s in M.telas_ordenadas(st)] == ["DP-2", "DP-3", "DP-1"]
    assert M.numero_da_tela(st, telas[0]) == 3


def test_os_monitores_viewer_saem_na_ordem_escolhida(telas, tmp_path):
    """É esta lista que a mamografia reparte: a tela i vira o Monitor i+1."""
    st = Settings(tmp_path / "s.json")
    st.set("monitors", {"DP-1": {"role": "viewer", "ordem": 2},
                        "DP-2": {"role": "browser", "ordem": 3},
                        "DP-3": {"role": "viewer", "ordem": 1}})
    assert [s.name() for s in M.screens_with_role(st, "viewer")] == ["DP-3", "DP-1"]


def test_ordem_invalida_nao_derruba(telas, tmp_path):
    st = Settings(tmp_path / "s.json")
    st.set("monitors", {"DP-1": {"ordem": "abc"}, "DP-2": {}})
    assert len(M.telas_ordenadas(st)) == 3


# ------------------------------------------------------------------ preferências
def test_a_tabela_guarda_a_ordem_e_recusa_repetida(telas, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from ipe.ui import preferences as P
    monkeypatch.setattr(P.QGuiApplication, "screens", staticmethod(lambda: list(telas)))
    st = Settings(tmp_path / "s.json")
    dlg = P.PreferencesDialog(st)
    assert dlg.t_mon.rowCount() == 3
    # inverter a ordem das duas primeiras
    dlg.mon_rows[0][3].setValue(2)
    dlg.mon_rows[1][3].setValue(1)
    dlg._save()
    guardado = st.get("monitors")
    assert guardado["DP-1"]["ordem"] == 2 and guardado["DP-2"]["ordem"] == 1
    assert [s.name() for s in M.telas_ordenadas(st)] == ["DP-2", "DP-1", "DP-3"]
    # repetida: avisa e não salva
    dlg2 = P.PreferencesDialog(st)
    dlg2.mon_rows[0][3].setValue(1)
    dlg2.mon_rows[1][3].setValue(1)
    ditos = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: ditos.append(a[1] if len(a) > 1 else ""))
    dlg2._save()
    assert ditos and st.get("monitors")["DP-1"]["ordem"] == 2, "nada mudou"
    dlg2.close()


def test_ordenar_pela_posicao(telas, tmp_path, monkeypatch):
    from ipe.ui import preferences as P
    monkeypatch.setattr(P.QGuiApplication, "screens", staticmethod(lambda: list(telas)))
    st = Settings(tmp_path / "s.json")
    st.set("monitors", {"DP-1": {"ordem": 3}, "DP-2": {"ordem": 2}, "DP-3": {"ordem": 1}})
    dlg = P.PreferencesDialog(st)
    dlg._ordenar_pela_posicao()
    nomes = {dlg.mon_rows[i][0]: dlg.mon_rows[i][3].value() for i in range(3)}
    assert nomes["DP-1"] == 1 and nomes["DP-2"] == 2 and nomes["DP-3"] == 3
    dlg.close()
