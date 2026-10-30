"""Os atalhos padrão não podem se repetir.

Defeito real da 0.53.2: a ação nova `view.strip` nasceu com **Shift+T**, que já era da
`mg.tomo`. Resultado: Preferências ▸ Atalhos recusava **qualquer** gravação com "Atalho
repetido" — o usuário não conseguia salvar configuração nenhuma, inclusive a de monitores, que
fica na mesma janela. Um atalho repetido não é incômodo de atalho: tranca a janela inteira.
"""
from collections import Counter

from ipe.ui.viewer.actions import ACTIONS


def test_nenhum_atalho_padrao_repetido():
    teclas = [a[2] for a in ACTIONS if a[2]]
    repetidos = [k for k, n in Counter(teclas).items() if n > 1]
    donos = {k: [a[0] for a in ACTIONS if a[2] == k] for k in repetidos}
    assert not repetidos, f"atalho em mais de uma ação: {donos}"


def test_ids_unicos():
    ids = [a[0] for a in ACTIONS]
    assert len(ids) == len(set(ids))


def test_a_janela_de_preferencias_salva(tmp_path, monkeypatch):
    """Com os padrões de fábrica, `_save()` tem que gravar — não cair no aviso."""
    from PySide6.QtWidgets import QApplication, QMessageBox
    QApplication.instance() or QApplication([])
    from ipe.core.config import Settings
    from ipe.ui import preferences as P
    avisos = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: avisos.append(a[1:3]))
    st = Settings(tmp_path / "s.json")
    dlg = P.PreferencesDialog(st)
    dlg._save()
    dlg.close()
    assert not avisos, f"a janela recusou os padrões: {avisos}"
    assert st.get("shortcuts")
