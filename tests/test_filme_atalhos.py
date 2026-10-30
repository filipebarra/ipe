"""Filme (0.76): F1 e F2 no visualizador, e arrastar a imagem para mudar a ordem do filme.

Pedido dele (13/10/2026): *"atalhos (funcionam somente no viewer): F1 adicionar imagem ao filme,
F2 série do quadro. no filme, ao clicar e arrastar quero mover as imagens dele, mudando a ordem
dentro do filme"*.
"""
import json

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.ui.viewer.actions import shortcut_for
from test_printing import _window


# ------------------------------------------------------------------ teclas de fábrica e migração
def test_f1_e_f2_de_fabrica(tmp_path):
    st = Settings(tmp_path / "s.json")
    assert shortcut_for(st, "film.add") == "F1" and shortcut_for(st, "film.series") == "F2"


def _gravado(tmp_path, atalhos, versao=2):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"shortcuts": atalhos, "shortcuts_versao": versao}), encoding="utf-8")
    return Settings(p)


def test_quem_ja_salvou_preferencias_ganha_f1_e_f2(tmp_path):
    """A janela de Preferências grava todas as ações, inclusive vazias: sem a migração, o vazio
    gravado mandaria sobre o padrão novo e ele ficaria sem F1/F2."""
    st = _gravado(tmp_path, {"film.add": "", "film.series": "", "mg.next": "Right", "tool.wl": ""})
    assert shortcut_for(st, "film.add") == "F1" and shortcut_for(st, "film.series") == "F2"
    assert shortcut_for(st, "mg.next") == "Right"
    assert st.get("shortcuts_versao") == Settings.ATALHOS_VERSAO


def test_a_migracao_nao_passa_por_cima_do_que_ele_escolheu(tmp_path):
    st = _gravado(tmp_path, {"film.add": "Ctrl+F", "film.series": "", "view.fit": "F2"})
    assert shortcut_for(st, "film.add") == "Ctrl+F", "tecla escolhida por ele fica"
    assert shortcut_for(st, "film.series") == "", "F2 já é de outra ação dele: não duplica"
    assert shortcut_for(st, "view.fit") == "F2"


def test_a_migracao_vale_uma_vez(tmp_path):
    p = tmp_path / "s.json"
    st = _gravado(tmp_path, {"film.add": ""})
    st.set("shortcuts", {"film.add": ""})        # ele tirou o F1 depois
    st.save()
    assert shortcut_for(Settings(p), "film.add") == ""


def test_a_camada_do_usuario_tambem_ganha(tmp_path):
    st = Settings(tmp_path / "s.json")
    st.attach_user({"shortcuts": {"film.add": "", "film.series": ""}, "shortcuts_versao": 2})
    assert shortcut_for(st, "film.add") == "F1" and shortcut_for(st, "film.series") == "F2"


# ------------------------------------------------------------------ F1/F2 só no visualizador
@pytest.fixture()
def janela(env, sample_dir, monkeypatch):
    from PySide6.QtGui import QDesktopServices
    app, w, repo = _window(env, sample_dir)
    ajuda = []
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda url: ajuda.append(url) or True))
    w.resize(1200, 800)
    w.show()
    yield app, w, ajuda
    comp = getattr(w, "_film_composer", None)
    if comp is not None:
        comp.dirty = False
    w.close()


def _foco_no_quadro(app, w):
    bar = w.tabs.tabBar()
    QTest.mouseClick(bar, Qt.LeftButton, pos=bar.tabRect(1).center())
    app.processEvents()
    tab = w.tabs.currentWidget()
    tab.viewports[0].setFocus()
    app.processEvents()
    return tab


def test_f1_no_visualizador_manda_a_imagem_ao_filme_e_nao_abre_a_ajuda(janela):
    app, w, ajuda = janela
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    tab = _foco_no_quadro(app, w)
    QTest.keyClick(QApplication.focusWidget(), Qt.Key_F1)
    app.processEvents()
    comp = w.film_composer()
    assert comp.film.image_count() == 1, "F1 não mandou a imagem ao filme"
    assert not ajuda, "F1 no visualizador abriu a ajuda"
    assert comp.film.sheets[0].cells[0].series_uid == tab.viewports[0].series_uid


def test_f2_no_visualizador_pede_a_serie_do_quadro(janela, monkeypatch):
    from ipe.ui.film.composer import FilmComposer
    app, w, ajuda = janela
    pedidos = []
    monkeypatch.setattr(FilmComposer, "add_series_range",
                        lambda self, uid, *a, **k: pedidos.append(uid) or 0)
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    tab = _foco_no_quadro(app, w)
    QTest.keyClick(QApplication.focusWidget(), Qt.Key_F2)
    app.processEvents()
    assert pedidos == [tab.viewports[0].series_uid]


def test_f1_no_banco_de_dados_continua_abrindo_a_ajuda(janela):
    app, w, ajuda = janela
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    _foco_no_quadro(app, w)
    bar = w.tabs.tabBar()
    QTest.mouseClick(bar, Qt.LeftButton, pos=bar.tabRect(0).center())
    w.browser.table.setFocus()
    app.processEvents()
    QTest.keyClick(QApplication.focusWidget(), Qt.Key_F1)
    app.processEvents()
    assert ajuda and ajuda[-1].toLocalFile().endswith(".pdf")


# ------------------------------------------------------------------ arrastar muda a ordem
def _filme_com(app, w, n):
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    tab = w.tabs.currentWidget()
    app.processEvents()
    tab.film_add_current()
    comp = w.film_composer()
    vp = tab.viewports[0]
    comp.place_cells([comp._cell_for(vp.series_uid, i) for i in range(1, n)])
    app.processEvents()
    return comp


def test_trocar_pela_alca_troca_as_duas(janela):
    """0.78: soltar uma imagem sobre outra troca as duas de lugar; as outras não se mexem."""
    app, w, _ = janela
    comp = _filme_com(app, w, 5)
    a, b, c, d, e = comp.film.sheets[0].cells[:5]
    assert comp.swap_cells((0, 0), (0, 3))
    assert comp.film.sheets[0].cells[:5] == [d, b, c, a, e]
    assert comp.dirty and comp.selected == (0, 3)
    assert not comp.swap_cells((0, 2), (0, 2))
    comp._dropped(comp.view.cells[2], "cell", "0,1")
    assert comp.film.sheets[0].cells[:5] == [d, c, b, a, e]


def test_trocar_entre_folhas(janela):
    app, w, _ = janela
    comp = _filme_com(app, w, 14)                # 3x4 de fábrica: 12 + 2 na segunda folha
    ultima = comp.film.sheets[1].cells[1]
    primeira = comp.film.sheets[0].cells[0]
    assert comp.swap_cells((1, 1), (0, 0))
    assert comp.film.sheets[0].cells[0] is ultima and comp.film.sheets[1].cells[1] is primeira
    assert comp.film.image_count() == 14
