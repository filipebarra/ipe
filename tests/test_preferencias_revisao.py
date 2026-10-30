"""Revisão das preferências: nada morto, nada escondido, e o que tem porta grava.

Três guardas:
1. toda opção que a janela grava é lida por alguém (opção morta não entra);
2. toda chave que o programa lê tem porta em algum lugar da tela (exceções nomeadas);
3. a janela abre, grava com os padrões e não reclama.
"""
import re
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from ipe.core.config import Settings

SRC = Path(__file__).resolve().parents[1] / "src" / "ipe"

# Chaves que o programa lê e que **não** têm (nem devem ter) controle nas Preferências.
SEM_PORTA_DE_PROPOSITO = {
    "viewer.teclas_do_mouse",          # chave antiga, lida só para quem vem da 0.52
    "viewer.mouse.left",               # parte do bloco "viewer.mouse", que tem porta própria
    "meeting.fullscreen",              # modo reunião: a porta é o próprio botão do modo
    "printing.pdf_dpi",                # moram na janela de impressão, não aqui
    "printing.hold_unknown_origin",
    "segment.pet_pct", "segment.pet_abs", "segment.pet_method", "segment.realce_pct",
    "dyn.ultimos", "dyn.regras",       # guardados pelo próprio uso (último usado)
    "viewer.cmap_padrao", "viewer.botoes_fora",
    # a porta é o próprio controle no compositor do filme (menu Mouse e a caixa "também no
    # exame"), gravado pela _remember dele com f"printing.{chave}" — o padrão daqui não vê
    "printing.left_tool", "printing.salvar_no_exame",
}


def _texto(nome: str) -> str:
    return (SRC / nome).read_text(encoding="utf-8")


def _chaves(padrao: str, texto: str) -> set:
    return set(re.findall(padrao, texto))


def test_nenhuma_opcao_morta_nas_preferencias():
    """Opção que a janela grava e ninguém lê é botão que não faz nada."""
    pref = _texto("ui/preferences.py")
    escritas = _chaves(r'\bs\.set\(\s*"([\w.]+)"', pref)
    assert escritas, "não achei nenhuma gravação; o teste perdeu o alvo"
    lidas = set()
    for f in SRC.rglob("*.py"):
        t = f.read_text(encoding="utf-8")
        lidas |= _chaves(r'settings\.get\(\s*"([\w.]+)"', t)
    mortas = sorted(k for k in escritas if k not in lidas)
    assert not mortas, f"opção gravada que ninguém lê: {mortas}"


def test_toda_chave_lida_tem_porta():
    lidas = set()
    for f in SRC.rglob("*.py"):
        t = f.read_text(encoding="utf-8")
        lidas |= _chaves(r'settings\.get\(\s*"([\w.]+)"', t)
    com_porta = set()
    for f in SRC.rglob("*.py"):
        t = f.read_text(encoding="utf-8")
        com_porta |= _chaves(r'settings\.set\(\s*"([\w.]+)"', t)
        com_porta |= _chaves(r'\bs\.set\(\s*"([\w.]+)"', t)
    sem = sorted(k for k in lidas if k not in com_porta and k not in SEM_PORTA_DE_PROPOSITO
                 and not k.startswith(("central.", "auth.", "network.", "monitors", "hanging")))
    assert not sem, f"chave lida que ninguém escreve (opção sem porta): {sem}"


@pytest.fixture()
def janela(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    from ipe.ui import preferences as P
    avisos = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: avisos.append(a[1:3]))
    st = Settings(tmp_path / "s.json")
    dlg = P.PreferencesDialog(st)
    yield st, dlg, avisos
    dlg.close()


def test_o_3d_e_a_lupa_ganharam_porta(janela):
    """Estavam só no settings.json: quem não edita JSON nunca soube que dava para mexer."""
    st, dlg, avisos = janela
    dlg.s_3d.setValue(320)
    dlg.s_lupa.setValue(300)
    dlg._save()
    assert not avisos
    assert st.get("viewer.render3d_size") == 320 and st.get("viewer.loupe_size") == 300


def test_a_aba_geral_esta_em_secoes(janela):
    """Era uma pilha: importação, letra, bandeja e idioma na mesma lista."""
    from PySide6.QtWidgets import QGroupBox, QTabWidget
    st, dlg, avisos = janela
    tabs = dlg.findChild(QTabWidget)
    geral = next(tabs.widget(i) for i in range(tabs.count()) if tabs.tabText(i) == "Geral")
    titulos = [g.title() for g in geral.findChildren(QGroupBox)]
    assert {"Ao abrir o programa", "Texto e marcas sobre a imagem", "Importação",
            "Idioma"} <= set(titulos), titulos
