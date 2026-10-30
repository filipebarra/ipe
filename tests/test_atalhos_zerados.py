"""A lista de atalhos nasce vazia, e a janela deixa achar a ação (busca + ordenação).

Pedido dele: *"remova todos os atalhos (com exceção de 2). eu vou ajustar aos poucos… configure
'q' para zoom por quadrante na mamografia e setas (direita e esquerda) para avançar e retroceder
etapas nos protocolos de mamografia"*, mais *"permita que eu possa organizar (ASC/DESC) no grupo e
na ação"* e *"crie opção de busca nesse menu"*.

Duas armadilhas que estes testes guardam:

1. **Mudar o padrão não desliga o que já está gravado.** Quem abriu Preferências uma vez tem as
   ~70 teclas antigas no settings.json, e o gravado manda sobre o padrão. Por isso existe a
   migração — e ela tem de valer **uma** vez, senão apagaria o que ele configurar depois.
2. **QTableWidget apaga o widget da célula quando a linha sai.** A tabela é remontada a cada busca
   e a cada troca de ordem; se os editores de tecla não forem soltos antes, o que ele digitou
   desaparece ao filtrar — ou o programa cai ao salvar.
"""
import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QMessageBox

from ipe.core.config import Settings
from ipe.ui.viewer.actions import ACTIONS, PADROES, shortcut_for


# -------------------------------------------------------------------- o catálogo e os 3 atalhos
def test_so_o_que_ele_pediu_vem_com_tecla():
    assert PADROES == {"mg.quad_next": "Q", "mg.next": "Right", "mg.prev": "Left",
                       "film.add": "F1", "film.series": "F2",      # F1/F2 do filme: pedido de 13/10
                       "view.copy": "Ctrl+C"}                     # copiar o quadro: pedido de 29/10
    com_tecla = {a[0]: a[2] for a in ACTIONS if a[2]}
    assert com_tecla == PADROES, f"atalho de fábrica que ele não pediu: {com_tecla}"
    assert len(ACTIONS) > 70                      # o catálogo continua inteiro
    ids = {a[0] for a in ACTIONS}
    assert {"phase.next", "phase.prev"} <= ids    # a fase ficou sem tecla, mas com ação própria


def test_as_acoes_das_etapas_e_do_quadrante_existem():
    nomes = {a[0]: a[1] for a in ACTIONS}
    assert "etapa" in nomes["mg.next"].lower() and "etapa" in nomes["mg.prev"].lower()
    assert "quadrante" in nomes["mg.quad_next"].lower()


# ------------------------------------------------------------------------------ a migração
def _settings_com_atalhos_antigos(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"shortcuts": {"tool.wl": "W", "view.fit": "F", "mg.next": "N",
                                           "mg.quad_next": "Q"}}), encoding="utf-8")
    return p


def test_migracao_zera_uma_vez_e_respeita_o_que_ele_configurar(tmp_path):
    p = _settings_com_atalhos_antigos(tmp_path)
    st = Settings(p)
    assert shortcut_for(st, "tool.wl") == "", "o atalho antigo sobreviveu"
    assert shortcut_for(st, "view.fit") == ""
    assert shortcut_for(st, "mg.next") == "Right"      # agora vale o padrão novo
    assert shortcut_for(st, "mg.prev") == "Left"
    assert shortcut_for(st, "mg.quad_next") == "Q"
    assert st.get("shortcuts_versao") == Settings.ATALHOS_VERSAO
    # o que ele configurar depois não é apagado na abertura seguinte
    st.set("shortcuts", {"tool.wl": "Ctrl+W"})
    st.save()
    assert shortcut_for(Settings(p), "tool.wl") == "Ctrl+W"


def test_migracao_tambem_limpa_as_preferencias_do_usuario(tmp_path):
    st = Settings(tmp_path / "s.json")
    st.attach_user({"shortcuts": {"tool.wl": "W"}})
    assert shortcut_for(st, "tool.wl") == "", "o atalho antigo do usuário sobreviveu"
    st.attach_user({"shortcuts": {"tool.wl": "Ctrl+W"}, "shortcuts_versao": Settings.ATALHOS_VERSAO})
    assert shortcut_for(st, "tool.wl") == "Ctrl+W"


# ------------------------------------------------------------------- a janela: busca e ordem
@pytest.fixture()
def dlg(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    from ipe.ui import preferences as P
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail(f"aviso: {a[1:3]}"))
    d = P.PreferencesDialog(Settings(tmp_path / "s.json"))
    yield d
    d.close()


def _coluna(d, col):
    return [d.t_keys.item(r, col).text() for r in range(d.t_keys.rowCount())]


def _ordenado(textos, reverse=False):
    """A ordem que a janela usa: sem acento e sem diferenciar maiúsculas ("Séries" < "Sincronização")."""
    from ipe.ui.table_filter import fold
    return sorted(textos, key=fold, reverse=reverse)


def test_a_tabela_abre_inteira_e_diz_quantas_tem_tecla(dlg):
    assert dlg.t_keys.rowCount() == len(ACTIONS)
    assert f"{len(PADROES)} com atalho" in dlg.l_keys_conta.text(), dlg.l_keys_conta.text()


def test_busca_filtra_por_grupo_acao_e_tecla(dlg):
    dlg.e_busca_atalho.setText("quadrante")
    assert 0 < dlg.t_keys.rowCount() < len(ACTIONS)
    assert all("quadrante" in n.lower() for n in _coluna(dlg, 1))
    dlg.e_busca_atalho.setText("mamografia")           # busca por grupo
    assert set(_coluna(dlg, 0)) == {"Mamografia"}
    dlg.e_busca_atalho.setText("dinamica")             # sem acento acha "Dinâmica"
    assert dlg.t_keys.rowCount() >= 2 and any("Dinâmica" in n for n in _coluna(dlg, 1))
    dlg.e_busca_atalho.setText("Right")                # busca pela tecla
    assert dlg.t_keys.rowCount() == 1
    dlg.e_busca_atalho.setText("zzzz")                 # nada combina: a tela diz o que isso é
    assert dlg.t_keys.rowCount() == 0 and "Nenhuma" in dlg.l_keys_conta.text()
    dlg.e_busca_atalho.clear()
    assert dlg.t_keys.rowCount() == len(ACTIONS)


def test_cabecalho_ordena_asc_e_desc(dlg):
    cab = dlg.t_keys.horizontalHeader()
    grupos = _coluna(dlg, 0)
    assert grupos == _ordenado(grupos), "não abriu ordenada por grupo"
    cab.sectionClicked.emit(0)                          # segundo clique no grupo: inverte
    assert _coluna(dlg, 0) == _ordenado(grupos, reverse=True)
    assert cab.sortIndicatorOrder() == Qt.DescendingOrder
    cab.sectionClicked.emit(1)                          # agora por ação, crescente
    nomes = _coluna(dlg, 1)
    assert nomes == _ordenado(nomes)
    assert cab.sortIndicatorSection() == 1 and cab.sortIndicatorOrder() == Qt.AscendingOrder
    cab.sectionClicked.emit(1)
    assert _coluna(dlg, 1) == _ordenado(nomes, reverse=True)


def test_ordenar_por_atalho_junta_as_vazias_no_fim(dlg):
    dlg.t_keys.horizontalHeader().sectionClicked.emit(2)
    teclas = [dlg.t_keys.cellWidget(r, 2).keySequence().toString() for r in range(dlg.t_keys.rowCount())]
    assert [x for x in teclas if x] == _ordenado([x for x in teclas if x])
    assert teclas[:len(PADROES)] == _ordenado(list(PADROES.values()))
    assert not teclas[-1], "ação sem tecla deveria ficar no fim"


def test_filtrar_nao_perde_a_tecla_que_ele_digitou(dlg):
    """A armadilha do QTableWidget: linha que sai da tabela leva o widget da célula com ela.

    Por isso a tecla mora no dicionário, não no editor — e o editor volta preenchido quando a
    linha reaparece.
    """
    dlg.key_edits["tool.wl"].setKeySequence(QKeySequence("Ctrl+Alt+W"))
    dlg.e_busca_atalho.setText("lápis")                 # tool.wl sai da tela
    assert "tool.wl" not in dlg.key_edits              # o editor foi apagado com a linha
    assert dlg.key_values["tool.wl"] == "Ctrl+Alt+W"   # e a tecla continua lá
    dlg.t_keys.horizontalHeader().sectionClicked.emit(1)
    dlg.e_busca_atalho.clear()
    assert dlg.key_edits["tool.wl"].keySequence().toString() == "Ctrl+Alt+W"
    dlg._save()                                         # e vai para as preferências
    assert dlg.settings.get("shortcuts")["tool.wl"] == "Ctrl+Alt+W"
    assert dlg.settings.get("shortcuts")["tool.zoom"] == ""


def test_salva_o_que_esta_filtrado(dlg):
    """Ação escondida pela busca continua valendo: o que vale é o editor, não a linha visível."""
    dlg.key_edits["mg.slab"].setKeySequence(QKeySequence("Ctrl+Alt+J"))
    dlg.e_busca_atalho.setText("histograma")
    dlg._save()
    assert dlg.settings.get("shortcuts")["mg.slab"] == "Ctrl+Alt+J"
    assert dlg.settings.get("shortcuts")["mg.next"] == "Right"


# ------------------------------------------- as três teclas, vivas numa aba recém-aberta
def test_as_tres_teclas_valem_assim_que_a_aba_abre(env, sample_dir):
    """Defeito achado aqui: `apply_shortcuts()` rodava no meio da montagem da barra.

    As ações da mamografia nascem **depois** dessa linha, então as teclas delas (Q, ←, →,
    Alt+Q, Shift+T…) ficavam sem atalho até ele abrir Preferências e salvar — é de lá que vem a
    outra chamada. Com a lista zerada, as três teclas que restaram são todas desse bloco: o
    defeito deixaria o teclado inteiro morto numa instalação nova.
    """
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    Importer(db, paths.storage).import_paths([sample_dir])
    st = Settings(paths.settings_file)
    w = MainWindow(paths, st, repo=repo, db=db)
    w.resize(1200, 800)
    w.show()
    try:
        w.open_study(repo.find_study_uids(accession="ACC3001")[0])
        tab = w.tabs.currentWidget()
        app.processEvents()
        for aid, tecla in PADROES.items():
            a = tab.actions_by_id[aid]
            assert a.shortcut().toString() == tecla, f"{aid} abriu sem tecla"
            assert a.isEnabled()
        assert tab.actions_by_id["tool.wl"].shortcut().toString() == ""
    finally:
        w.close()


def test_setas_andam_nas_etapas_e_nao_nas_abas(env, sample_dir):
    """Relato dele (0.73): ← → trocavam entre os exames abertos e o banco de dados.

    Clicar na aba deixava o foco na barra de abas, que usa as setas para trocar de aba; o atalho
    das etapas só vale com o foco dentro do visualizador, então nem disparava.
    """
    from PySide6.QtTest import QTest
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    Importer(db, paths.storage).import_paths([sample_dir])
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1200, 800)
    w.show()
    try:
        w.open_study(repo.find_study_uids(accession="ACC3001")[0])      # mamografia, aba 1
        w.open_study(repo.find_study_uids(accession="ACC1001")[0])      # outro exame, aba 2
        assert w.tabs.count() == 3
        bar = w.tabs.tabBar()
        QTest.mouseClick(bar, Qt.LeftButton, pos=bar.tabRect(1).center())
        app.processEvents()
        mg = w.tabs.currentWidget()
        assert w.tabs.currentIndex() == 1 and mg.mg_session is not None
        foco = QApplication.focusWidget()
        assert foco is not bar and mg.isAncestorOf(foco), "o teclado tem de ir para o exame"
        QTest.keyClick(foco, Qt.Key_Right)
        app.processEvents()
        assert w.tabs.currentIndex() == 1, "→ trocou de aba"
        assert mg.mg_session.step == 1
        QTest.keyClick(QApplication.focusWidget(), Qt.Key_Left)
        app.processEvents()
        assert w.tabs.currentIndex() == 1 and mg.mg_session.step == 0
        # no banco de dados as setas também não trocam de aba
        QTest.mouseClick(bar, Qt.LeftButton, pos=bar.tabRect(0).center())
        app.processEvents()
        QTest.keyClick(QApplication.focusWidget() or w, Qt.Key_Right)
        app.processEvents()
        assert w.tabs.currentIndex() == 0
    finally:
        w.close()
