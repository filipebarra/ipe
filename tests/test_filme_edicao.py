"""Painel do filme (0.78): função do botão esquerdo, troca pela alça, anotações editáveis,
liga/desliga das anotações, botões renomeados e "também no exame" no Salvar.

Pedido dele (19/10/2026).
"""
import numpy as np
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QInputDialog, QMenu, QPushButton

from test_printing import _window


@pytest.fixture()
def comp(env, sample_dir, monkeypatch):
    app, w, repo = _window(env, sample_dir)
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    tab = w.tabs.currentWidget()
    app.processEvents()
    tab.film_add_current()
    c = w.film_composer()
    vp = tab.viewports[0]
    c.place_cells([c._cell_for(vp.series_uid, i) for i in range(1, 4)])
    c.set_layout(2, 2)
    app.processEvents()
    yield app, w, repo, c
    c.dirty = False
    w.close()


def _menu_mouse(c, cw):
    """A primeira linha do menu da célula (montado sem abrir)."""
    return c.build_cell_menu(cw).actions()[0]


def _arrastar(cw, a, b, botao=Qt.LeftButton, mod=Qt.NoModifier, passos=8):
    QTest.mousePress(cw, botao, mod, a)
    for k in range(1, passos + 1):
        QTest.mouseMove(cw, a + (b - a) * k / passos)
    QTest.mouseRelease(cw, botao, mod, b)


# ------------------------------------------------------------------ função do botão esquerdo
def test_primeira_linha_do_menu_e_a_funcao_do_mouse(comp):
    app, w, repo, c = comp
    cw = c.view.cells[0]
    primeira = _menu_mouse(c, cw)
    assert primeira.text() == "Mouse (botão esquerdo)" and primeira.menu() is not None
    opcoes = [a.text() for a in primeira.menu().actions()]
    assert opcoes == ["Janela", "Mover", "Zoom"]
    primeira.menu().actions()[1].trigger()
    assert c.left_tool == "pan" and all(x.left_tool == "pan" for x in c.view.cells)
    assert w.settings.get("printing.left_tool") == "pan", "a escolha fica para a próxima vez"
    assert c.btn_mouse.text() == "Mouse: Mover"


def test_esquerdo_faz_a_funcao_escolhida(comp):
    app, w, repo, c = comp
    cw = c.view.cells[1]
    meio = cw.rect().center()
    c.set_left_tool("wl")
    largura = cw.state.width
    _arrastar(cw, meio, meio + QPoint(60, 0))
    assert cw.state.width != largura, "janela"
    c.set_left_tool("pan")
    pan = QPointF(cw.pan_frac)
    _arrastar(cw, meio, meio + QPoint(30, 20))
    assert cw.pan_frac != pan, "mover a imagem dentro do quadro"
    c.set_left_tool("zoom")
    z = cw.state.zoom
    _arrastar(cw, meio, meio + QPoint(0, -60))
    assert cw.state.zoom > z, "zoom"


def test_a_alca_troca_de_lugar_com_qualquer_funcao(comp, monkeypatch):
    from ipe.ui.film.cell import FilmCell
    app, w, repo, c = comp
    comecou = []
    monkeypatch.setattr(FilmCell, "_start_drag", lambda self: comecou.append(self.slot))
    cw = c.view.cells[2]
    alca = cw._grip_rect().center().toPoint()
    for tool in ("wl", "pan", "zoom"):
        c.set_left_tool(tool)
        QTest.mousePress(cw, Qt.LeftButton, Qt.NoModifier, alca)
        QTest.mouseRelease(cw, Qt.LeftButton, Qt.NoModifier, alca)
    assert comecou == [(0, 2)] * 3
    _arrastar(cw, cw.rect().center(), cw.rect().center() + QPoint(50, 0))
    assert len(comecou) == 3, "arrastar no meio da imagem não muda de lugar"


# ------------------------------------------------------------------ anotações
def _seta(c, cw, de, ate):
    c.set_note_tool("arrow")
    _arrastar(cw, de, ate)


def test_depois_de_anotar_o_mouse_volta_a_funcao(comp, monkeypatch):
    app, w, repo, c = comp
    c.set_left_tool("zoom")
    cw = c.view.cells[0]
    centro = cw.rect().center()
    _seta(c, cw, centro, centro + QPoint(-50, -40))
    assert len(cw.cell.notes) == 1 and cw.cell.notes[0]["kind"] == "arrow"
    assert c.note_tool == "" and cw.note_tool == "" and c.left_tool == "zoom"
    assert c.btn_mouse.isChecked() and not c.note_buttons["arrow"].isChecked()
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("nódulo", True)))
    c.set_note_tool("text")
    QTest.mouseClick(cw, Qt.LeftButton, Qt.NoModifier, centro + QPoint(20, 30))
    assert cw.cell.notes[-1]["text"] == "nódulo" and c.note_tool == ""


def test_arrastar_a_anotacao_move_e_a_ponta_estica(comp):
    app, w, repo, c = comp
    cw = c.view.cells[0]
    centro = cw.rect().center()
    ponta, cauda = centro, centro + QPoint(-50, -40)
    _seta(c, cw, ponta, cauda)
    n = cw.cell.notes[0]
    orig = [list(p) for p in n["points"]]
    janela = (cw.state.width, cw.state.level)
    # meio da seta: move tudo
    meio = (ponta + cauda) / 2
    assert cw.note_at(QPointF(meio))[1] == "all"
    _arrastar(cw, meio, meio + QPoint(20, 10))
    d0 = np.subtract(n["points"][0], orig[0])
    d1 = np.subtract(n["points"][1], orig[1])
    assert np.allclose(d0, d1) and np.abs(d0).sum() > 0, "a seta inteira andou junto"
    assert len(cw.cell.notes) == 1 and c.left_tool == "wl"
    # a ponta: só ela muda (a seta estica)
    p_tip = cw._note_pt(n["points"][0]).toPoint()
    assert cw.note_at(QPointF(p_tip))[1] == "tip"
    antes_cauda = list(n["points"][1])
    _arrastar(cw, p_tip, p_tip + QPoint(15, 15))
    assert n["points"][1] == antes_cauda and n["points"][0] != orig[0]
    assert (cw.state.width, cw.state.level) == janela, "arrastar a anotação não mexe na janela"


def test_duplo_clique_no_texto_edita(comp, monkeypatch):
    app, w, repo, c = comp
    cw = c.view.cells[0]
    respostas = iter([("massa", True), ("massa espiculada", True)])
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: next(respostas)))
    c.set_note_tool("text")
    pos = cw.rect().center()
    QTest.mouseClick(cw, Qt.LeftButton, Qt.NoModifier, pos)
    r = cw._text_rect(cw.cell.notes[0])
    expandiu = []
    c.expand_requested.connect(lambda: expandiu.append(1))
    QTest.mouseDClick(cw, Qt.LeftButton, Qt.NoModifier, r.center().toPoint())
    assert cw.cell.notes[0]["text"] == "massa espiculada" and not expandiu


def test_botao_liga_e_desliga_as_anotacoes(comp):
    from ipe.ui.film.render import render_sheet_image
    app, w, repo, c = comp
    cw = c.view.cells[0]
    centro = cw.rect().center()
    _seta(c, cw, centro, centro + QPoint(-60, -50))
    com = render_sheet_image(c.film, 0, c.src, c.cache, c.settings, 60, False)
    c.btn_notes.setChecked(False)
    assert not c.film.notes_visible and not c.view.cells[0].show_notes
    assert c.view.cells[0].note_at(QPointF(centro)) is None, "escondida não se edita"
    sem = render_sheet_image(c.film, 0, c.src, c.cache, c.settings, 60, False)
    a, b = (np.asarray(x.convert("RGB") if hasattr(x, "convert") else x) for x in (com, sem))
    assert a.shape == b.shape and (a != b).any(), "a impressão também esconde"
    assert c.film.to_dict()["notes_visible"] is False
    c.set_note_tool("arrow")                     # anotar religa, para não desenhar no escuro
    assert c.btn_notes.isChecked() and c.film.notes_visible


# ------------------------------------------------------------------ botões
def test_nomes_dos_botoes(comp):
    app, w, repo, c = comp
    textos = {b.text() for b in c.findChildren(QPushButton)}
    # 0.99.6: a barra ficou com Novo, Abrir, Salvar… e Imprimir…; o resto mora nas duas janelas
    assert {"Novo", "Abrir…", "Salvar…", "Imprimir…"} <= textos
    assert not textos & {"Imagens…", "DICOM…", "No exame", "JPG/PNG…", "DICOM Print…", "PDF…", "Salvar como…"}
    assert c.chk_no_exame.text() == "também no exame"


# ------------------------------------------------------------------ também no exame
def _series_do_filme(repo, study_uid):
    return {s.series_uid for s in repo.series_for_study(study_uid, ocultas=True)
            if s.description in ("AW electronic film", "AW electronic pages")}


def test_salvar_tambem_no_exame_sem_empilhar_copias(comp, monkeypatch):
    app, w, repo, c = comp
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Filme", True)))
    st = c.film.study_uids()[0]
    c.chk_no_exame.setChecked(True)
    assert w.settings.get("printing.salvar_no_exame") is True
    assert c.save()
    primeira = _series_do_filme(repo, st)
    assert len(primeira) == 3 and set(c.film.no_exame["series"]) == primeira
    # salvar de novo sem mudar nada: não grava outra cópia
    assert c.save()
    assert _series_do_filme(repo, st) == primeira
    # mudou e escolheu substituir: a anterior sai, a nova entra
    c.view.cells[0].rotate(90)
    monkeypatch.setattr(type(c), "perguntar_substituir_no_exame", lambda self: "substituir")
    assert c.save()
    segunda = _series_do_filme(repo, st)
    assert len(segunda) == 3 and not segunda & primeira
    # o registro da cópia volta com o filme salvo
    dados = repo.film_data(c.film_id)
    assert set(dados["no_exame"]["series"]) == segunda
    # mudou e escolheu guardar as duas
    c.view.cells[0].rotate(90)
    monkeypatch.setattr(type(c), "perguntar_substituir_no_exame", lambda self: "nova")
    c.save()
    assert len(_series_do_filme(repo, st)) == 6
    # "agora não": salva o filme e não grava no exame
    c.view.cells[0].rotate(90)
    monkeypatch.setattr(type(c), "perguntar_substituir_no_exame", lambda self: None)
    c.save()
    assert len(_series_do_filme(repo, st)) == 6 and not c.dirty


def test_sem_a_caixa_o_salvar_nao_mexe_no_exame(comp, monkeypatch):
    app, w, repo, c = comp
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Filme", True)))
    c.chk_no_exame.setChecked(False)
    st = c.film.study_uids()[0]
    c.save()
    assert not _series_do_filme(repo, st) and c.film_id


# ------------------------------------------------------------------ 0.99.6: janelas Salvar e Imprimir
def test_paginas_do_texto():
    from ipe.ui.film.dialogs import paginas_do_texto
    assert paginas_do_texto("1-3, 5", 6) == [0, 1, 2, 4]
    assert paginas_do_texto("3-1;9;x;2", 4) == [0, 1, 2]
    assert paginas_do_texto("", 4) == []


def test_janela_salvar_salva_e_salva_como_novo(comp, monkeypatch):
    app, w, repo, c = comp
    from ipe.ui.film import dialogs as D
    escolha = {"acao": "salvar", "nome": "Primeiro"}

    def exec_falso(dlg):
        dlg.e_nome.setText(escolha["nome"])
        dlg.c_exame.setChecked(False)
        dlg._fim(escolha["acao"])
        return 1
    monkeypatch.setattr(D.SalvarFilmeDialog, "exec", exec_falso)
    assert c.save_dialog()
    primeiro = c.film_id
    assert primeiro is not None and c.film.name == "Primeiro"
    escolha.update(acao="salvar", nome="Renomeado")              # Salvar: o mesmo filme, nome novo
    assert c.save_dialog() and c.film_id == primeiro and c.film.name == "Renomeado"
    escolha.update(acao="novo", nome="Cópia")                     # Salvar como novo: outro registro
    assert c.save_dialog() and c.film_id != primeiro and c.film.name == "Cópia"


def test_janela_imprimir_escolhe_destino_e_folhas(comp, monkeypatch, tmp_path):
    app, w, repo, c = comp
    from PySide6.QtWidgets import QFileDialog

    from ipe.ui.film import dialogs as D
    c.add_sheet()
    c.add_sheet()
    assert len(c.film.sheets) == 3
    pedido = {}

    def exec_falso(dlg):
        assert {k for k in dlg.r_dest} == {"local", "pdf", "imagem", "dicom"}
        dlg.r_dest[pedido["destino"]].setChecked(True)
        dlg.r_escolher.setChecked(True)
        dlg.e_paginas.setText(pedido["folhas"])
        dlg._ok()
        return dlg.result()
    monkeypatch.setattr(D.ImprimirFilmeDialog, "exec", exec_falso)
    # imagens: só as folhas 1 e 3
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(tmp_path / "f.png"), "PNG (*.png)")))
    pedido.update(destino="imagem", folhas="1,3")
    c.imprimir()
    assert sorted(p.name for p in tmp_path.glob("f_*.png")) == ["f_01.png", "f_03.png"]
    # PDF com a folha 2
    monkeypatch.setattr(QFileDialog, "getSaveFileName",
                        staticmethod(lambda *a, **k: (str(tmp_path / "f.pdf"), "PDF (*.pdf)")))
    chamadas = []
    orig = c._paint_pages
    monkeypatch.setattr(c, "_paint_pages", lambda dev, dpi, idx=None: (chamadas.append(idx), orig(dev, dpi, idx)))
    pedido.update(destino="pdf", folhas="2")
    c.imprimir()
    assert chamadas == [[1]] and (tmp_path / "f.pdf").exists()
    # DICOM sem impressora cadastrada: não fecha a janela, não envia
    enviados = []
    monkeypatch.setattr(c, "enviar_dicom", lambda cfg, idx: enviados.append((cfg, idx)))
    monkeypatch.setattr(D.QMessageBox, "information", staticmethod(lambda *a, **k: 0))
    pedido.update(destino="dicom", folhas="1-2")
    c.imprimir()
    assert enviados == []
    # com impressora: manda as folhas pedidas, com as cópias
    w.settings.set("printing.dicom_printers", [{"name": "Dry", "ae_title": "DRY", "host": "10.0.0.5"}])
    c.imprimir()
    (cfg, idx), = enviados
    assert cfg.name == "Dry" and idx == [0, 1] and w.settings.get("printing.ultimo_destino_filme") == "dicom"
