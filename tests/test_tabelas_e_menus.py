"""Colunas arrastáveis em toda tabela, e o menu do botão esquerdo dividido em Mouse e Medidas.

Pedidos dele: *"'Ferramentas do botão esquerdo' mude para Mouse (botão esquerdo)"*, *"crie uma
outra: Medidas com opção de escolher as medidas (régua, segmentar, seta…)"* e *"um ajuste em tudo
que tem tabela no programa: dimensões ajustáveis das colunas (sei que em configurações de nós dicom
hoje não tem como ajustar)"*.
"""
from _menus import submenu, todas  # noqa: F401
import io
import pathlib
import re

import pytest
from PySide6.QtWidgets import QApplication, QHeaderView, QTableWidget, QTreeWidget

from ipe.ui.tabelas import colunas_ajustaveis
from ipe.ui.viewer.annotate import TOOLS, ferramentas_divididas

RAIZ = pathlib.Path(__file__).resolve().parents[1] / "src" / "ipe"
CRIA = re.compile(r"=\s*(QTableWidget|QTableView|QTreeWidget)\s*\(")


def _app():
    return QApplication.instance() or QApplication([])


def test_a_coluna_fica_arrastavel_mesmo_depois_de_stretch():
    _app()
    t = QTableWidget(2, 3)
    t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
    colunas_ajustaveis(t)
    cab = t.horizontalHeader()
    for i in range(3):
        assert cab.sectionResizeMode(i) == QHeaderView.Interactive, f"coluna {i} travada"
    assert cab.stretchLastSection(), "a última coluna tem de ocupar a sobra"
    assert cab.minimumSectionSize() >= 20, "coluna some e o usuário não acha de volta"


def test_vale_para_arvore_tambem():
    _app()
    a = QTreeWidget()
    a.setColumnCount(2)
    a.header().setSectionResizeMode(QHeaderView.ResizeToContents)
    colunas_ajustaveis(a)
    assert a.header().sectionResizeMode(0) == QHeaderView.Interactive
    assert colunas_ajustaveis(object()) is not None    # objeto sem cabeçalho não quebra


def test_a_largura_calculada_nao_se_perde():
    _app()
    t = QTableWidget(1, 2)
    t.setColumnWidth(0, 180)
    colunas_ajustaveis(t)
    assert t.columnWidth(0) == 180


def test_toda_tabela_do_programa_passa_pelo_ajuste():
    """Varredura: tabela nova sem o ajuste reprova aqui, não na tela do médico."""
    faltando = []
    for arq in sorted(RAIZ.rglob("*.py")):
        texto = io.open(arq, encoding="utf-8").read()
        n_tabelas = len(CRIA.findall(texto))
        if not n_tabelas:
            continue
        n_ajustes = texto.count("colunas_ajustaveis(")
        if n_ajustes < n_tabelas:
            faltando.append(f"{arq.name}: {n_tabelas} tabela(s), {n_ajustes} ajuste(s)")
    assert not faltando, "tabela sem colunas ajustáveis: " + "; ".join(faltando)


def test_os_nos_dicom_tambem(env):
    """O caso que ele citou: Rede ▸ configurar nós."""
    paths, db, repo = env
    from ipe.core.config import Settings
    from ipe.network.service import NetworkService
    from ipe.ui.network_dialog import NetworkDialog
    _app()
    st = Settings(paths.settings_file)
    d = NetworkDialog(st, repo, NetworkService(db, repo, paths.storage, st), None)
    cab = d.t_nodes.horizontalHeader()
    for i in range(cab.count()):
        assert cab.sectionResizeMode(i) == QHeaderView.Interactive, f"coluna {i} dos nós travada"
    d.close()


# ------------------------------------------------------------------ menu do botão esquerdo
def test_as_ferramentas_se_dividem_sem_perder_nenhuma():
    mouse, medidas = ferramentas_divididas()
    assert set(mouse) | set(medidas) == set(TOOLS), "ferramenta sumiu na divisão"
    assert not (set(mouse) & set(medidas)), "ferramenta em dois lugares"
    for k in ("wl", "zoom", "pan", "scroll", "cross", "loupe"):
        assert k in mouse, k
    for k in ("measure", "grow", "arrow", "ellipse", "angle", "calibration", "pick"):
        assert k in medidas, k
    assert list(medidas)[:2] == ["pick", "measure"], "a ordem do menu de medidas mudou"


def test_o_menu_do_quadro_tem_os_dois(env, sample_dir, monkeypatch):
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = _app()
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.show()
    w.open_study(repo.search_studies()[0].study_uid)
    app.processEvents()
    vp = w.all_viewer_tabs()[-1].viewports[0]
    menu = vp.build_context_menu()
    titulos = [a.text() for a in menu.actions()]
    # 0.99.78: um submenu só, com navegar, medir e desenhar
    assert "Ferramenta do botão esquerdo" in titulos, titulos
    assert "Mouse (botão esquerdo)" not in titulos and "Medidas" not in titulos
    sub = {"Medidas": submenu(menu, "Ferramenta do botão esquerdo/Medir"),
           "Mouse (botão esquerdo)": submenu(menu, "Ferramenta do botão esquerdo/Navegar")}
    nomes_medidas = [x.text() for x in sub["Medidas"].actions()]
    assert TOOLS["measure"] in nomes_medidas and TOOLS["grow"] in nomes_medidas
    assert TOOLS["arrow"] in [x.text() for x in submenu(menu, "Ferramenta do botão esquerdo/Desenhar").actions()]
    nomes_mouse = [x.text() for x in sub["Mouse (botão esquerdo)"].actions()]
    assert TOOLS["zoom"] in nomes_mouse and TOOLS["measure"] not in nomes_mouse
    # escolher no menu troca a ferramenta de verdade
    pedidos = []
    vp.sig.tool_requested.connect(pedidos.append)
    next(x for x in sub["Medidas"].actions() if x.text() == TOOLS["measure"]).trigger()
    assert pedidos == ["measure"]
    w.close()


def test_o_ajuste_nao_caiu_dentro_de_uma_expressao():
    """A inserção foi automática em 34 tabelas: uma caiu no meio de uma tupla e o Python aceitou.

    Sintaxe válida não quer dizer código certo — a chamada tem de ser um comando, não um item de
    lista. Este teste é a guarda que faltou naquele dia.
    """
    import ast
    ruins = []
    for arq in sorted(RAIZ.rglob("*.py")):
        if arq.name == "tabelas.py":
            continue
        texto = io.open(arq, encoding="utf-8").read()
        if "colunas_ajustaveis(" not in texto:
            continue
        comandos = {n.lineno for n in ast.walk(ast.parse(texto))
                    if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                    and getattr(n.value.func, "id", "") == "colunas_ajustaveis"}
        for i, ln in enumerate(texto.split("\n"), 1):
            if "colunas_ajustaveis(" in ln and "import" not in ln and i not in comandos:
                ruins.append(f"{arq.name}:{i}")
    assert not ruins, "chamada embutida numa expressão: " + ", ".join(ruins)
