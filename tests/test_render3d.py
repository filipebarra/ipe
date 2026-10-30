"""3D: clique que devolve o ponto, plano de corte oblíquo, escultura, maca e 3D no layout."""
import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.imaging.render3d import Renderer3D, polygon_mask
from ipe.importer.scanner import Importer


class _Vol:
    """Volume isotrópico simples, alinhado ao paciente."""

    def __init__(self, dados):
        self.data = dados.astype(np.float32)
        self.shape = dados.shape
        self.dx = self.dy = self.dz = 1.0
        self.origin = np.zeros(3)
        self.row_dir = np.array([1.0, 0, 0])
        self.col_dir = np.array([0, 1.0, 0])
        self.slice_vec = np.array([0, 0, 1.0])
        self.window = None
        self.source_path = ""

    def matrix(self):
        return np.column_stack([self.row_dir * self.dx, self.col_dir * self.dy, self.slice_vec])

    def voxel_to_patient(self, i, j, k):
        return self.origin + self.matrix() @ np.array([i, j, k], float)


def _fantoma(com_maca: bool = True):
    """Esfera de 'osso' e, opcionalmente, uma laje fina atrás dela — a maca."""
    z, y, x = np.mgrid[0:60, 0:60, 0:60]
    d = np.full((60, 60, 60), -900.0)
    d[((z - 30.0) ** 2 + (y - 25.0) ** 2 + (x - 30.0) ** 2) < 144] = 800.0
    if com_maca:
        d[:, 50:53, :] = 300.0
    return Renderer3D(_Vol(d), max_dim=60)


def _acesos(img):
    return int((img > 0).sum())


# ------------------------------------------------------------------ motor
def test_clique_devolve_o_ponto():
    r = _fantoma(com_maca=False)
    r.render("surf", 0, 0, (120, 120), lo=200)
    p = r.point_at(60, 60)
    assert p is not None
    # visto de frente, o raio do meio bate na face anterior da esfera (y = 25 − 12)
    assert p[0] == pytest.approx(30, abs=2) and p[2] == pytest.approx(30, abs=2)
    assert p[1] == pytest.approx(13, abs=2)
    j, i = r.screen_of(p)
    assert j == pytest.approx(60, abs=1) and i == pytest.approx(60, abs=1)
    # fora do objeto não há ponto nenhum
    assert r.point_at(2, 2) is None


def test_clique_acompanha_o_giro():
    r = _fantoma(com_maca=False)
    r.render("surf", 90, 0, (120, 120), lo=200)
    p = r.point_at(60, 60)
    assert p is not None
    # de perfil o raio entra pelo lado: x vai para a borda da esfera, y e z ficam no meio da grade
    assert p[1] == pytest.approx(29.5, abs=2) and p[2] == pytest.approx(29.5, abs=2)
    assert p[0] > 38


def test_clique_precisa_de_desenho_antes():
    r = _fantoma(com_maca=False)
    assert r.point_at(10, 10) is None            # nada renderizado ainda


def test_plano_obliquo_corta_e_arrasta():
    r = _fantoma(com_maca=False)
    inteiro = _acesos(r.render("surf", 0, 0, (80, 80), lo=200))
    r.cut_plane(r.point_of((30, 30, 30)), [0, 1, 0], keep="front")
    cortado = _acesos(r.render("surf", 0, 0, (80, 80), lo=200))
    assert 0 < cortado < inteiro
    assert r.nudge_plane(10) is True
    mais = _acesos(r.render("surf", 0, 0, (80, 80), lo=200))
    assert mais > cortado                        # empurrar o plano para trás descobre mais volume
    assert r.nudge_plane(-30) is True
    menos = _acesos(r.render("surf", 0, 0, (80, 80), lo=200))
    assert menos < cortado                       # e para a frente tira mais
    assert not r.untouched()
    r.restore_all()
    assert r.untouched() and _acesos(r.render("surf", 0, 0, (80, 80), lo=200)) == inteiro
    assert r.nudge_plane(5) is False             # sem plano não há o que empurrar


def test_plano_em_qualquer_angulo():
    r = _fantoma(com_maca=False)
    r.cut_plane(r.point_of((30, 30, 30)), [1, 1, 0])
    n, _c = r.plane
    assert np.linalg.norm(n) == pytest.approx(1.0, abs=1e-6)      # normal sempre unitária
    r.cut_plane(r.point_of((30, 30, 30)), [0, 0, 0])              # direção sem sentido: ignora
    assert r.plane is not None


def test_mascara_de_poligono():
    m = polygon_mask([(2, 2), (8, 2), (8, 8), (2, 8)], (10, 10))
    assert m.shape == (10, 10) and m.sum() == 36
    assert m[5, 5] and not m[0, 0]
    assert polygon_mask([(1, 1), (2, 2)], (10, 10)).sum() == 0    # menos de 3 pontos não é laço


def test_escultura_apaga_e_guarda():
    r = _fantoma(com_maca=False)
    laco = [(0, 0), (60, 0), (60, 60), (0, 60)]                   # um quarto da tela
    apagados = r.sculpt(laco, (120, 120), 0, 0)
    assert apagados > 0 and r.mask is not None
    assert int(r.mask.sum()) == 60 ** 3 - apagados
    r.restore_all()
    guardados = r.sculpt(laco, (120, 120), 0, 0, keep_inside=True)
    assert int(r.mask.sum()) == 60 ** 3 - guardados
    assert guardados > apagados                                   # guardar só um quarto tira o resto
    assert r.sculpt([(1, 1)], (120, 120), 0, 0) == 0              # laço curto não faz nada


def test_escultura_muda_o_desenho():
    r = _fantoma(com_maca=False)
    antes = _acesos(r.render("surf", 0, 0, (80, 80), lo=200))
    r.sculpt([(0, 0), (120, 0), (120, 60), (0, 60)], (120, 120), 0, 0)   # metade de cima
    depois = _acesos(r.render("surf", 0, 0, (80, 80), lo=200))
    assert depois < antes


def test_tira_a_maca():
    r = _fantoma()
    n = r.remove_table()
    assert n == 60 * 60 * 3                                        # a laje inteira
    assert int((r.data[:, 50:53, :] > -300)[r.mask[:, 50:53, :]].sum()) == 0
    assert int((r.mask & (r.data > 700)).sum()) == int((r.data > 700).sum())   # a esfera fica


def test_maca_so_em_tc_deitado():
    r = _fantoma(com_maca=False)
    assert r.remove_table() == 0                                   # sem maca, nada a tirar
    z, y, x = np.mgrid[0:40, 0:40, 0:40]
    rm = Renderer3D(_Vol(np.where(((z - 20.) ** 2 + (y - 20.) ** 2 + (x - 20.) ** 2) < 64, 500.0, 5.0)),
                    max_dim=40)
    assert rm.remove_table() == 0                                  # não parece TC em HU: não mexe


def test_caixa_do_conteudo_e_desenho_rapido():
    r = _fantoma(com_maca=False)
    caixa = r.content_box(200)
    assert caixa is not None
    x0, x1, y0, y1, z0, z1 = caixa
    assert 15 <= x0 <= 20 and 40 <= x1 <= 45                       # só onde a esfera está
    assert r.content_box(5000) is None                             # limiar acima de tudo
    vazio = r.render("surf", 0, 0, (50, 50), lo=5000)
    assert vazio.shape == (50, 50, 3) and vazio.max() == 0
    rapido = r.render("surf", 0, 0, (81, 81), lo=200, fast=True)
    assert rapido.shape == (81, 81, 3)                             # amplia de volta ao tamanho pedido


# ------------------------------------------------------------------ no layout
def test_3d_no_layout(env, sample_dir):
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    Importer(db, paths.storage).import_paths([sample_dir])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1200, 800)
    w.show()
    w.browser.refresh()
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 2)
    app.processEvents()
    a, b = tab.viewports[0], tab.viewports[1]
    uid = a.series_uid
    tab.load_series_into(b, uid)
    app.processEvents()
    tab._activate(a)
    v = tab.open_3d("surf")
    assert v is not None and a.render3d is v
    assert a.frames and a.frames[0].is_virtual and a._img is not None
    assert tab.render3d_bar.isVisibleTo(tab)
    assert tab._source_series(a) == uid                     # o 3D sabe de que série veio

    # arrastar com o esquerdo gira
    c = a.rect().center()
    QTest.mousePress(a, Qt.LeftButton, Qt.NoModifier, c)
    QTest.mouseMove(a, c + QPoint(60, 10))
    app.processEvents()
    QTest.mouseRelease(a, Qt.LeftButton, Qt.NoModifier, c + QPoint(60, 10))
    app.processEvents()
    assert v.az != 0.0

    # a roda aproxima a câmera, não o quadro
    zoom_quadro = a.state.zoom
    v.wheel(2)
    assert v.zoom > 1.0 and a.state.zoom == zoom_quadro

    # trocar de modo troca o tipo de imagem
    v.set_mode("vr")
    assert a._img is not None and a._img.is_color
    v.set_mode("mip")
    assert not a._img.is_color

    # clique leva o cursor dos outros quadros até o ponto
    v.set_view(0, 0)
    v.set_mode("surf")
    from PySide6.QtCore import QPointF
    ponto = v.point_at(a, QPointF(c))
    assert ponto is not None
    tab.cursor_from_3d(a, np.asarray(ponto, float))
    assert b.cursor_point is not None

    # a barra reflete o estado
    tab.render3d_bar.sync()
    assert tab.render3d_bar.c_mode.currentData() == "surf"
    assert tab.render3d_bar.a_inteiro.isEnabled() is False        # nada cortado ainda
    v.cut_box("anterior")
    tab.render3d_bar.sync()
    assert tab.render3d_bar.a_inteiro.isEnabled() is True
    v.cut_reset()

    # escultura pelo laço, com o estado aparecendo na tela
    v.sculpt_mode = "remove"
    assert "laço" in v.state_text()
    QTest.mousePress(a, Qt.LeftButton, Qt.NoModifier, c + QPoint(-40, -40))
    for d in ((40, -40), (40, 40), (-40, 40)):
        QTest.mouseMove(a, c + QPoint(*d))
        app.processEvents()
    QTest.mouseRelease(a, Qt.LeftButton, Qt.NoModifier, c + QPoint(-40, 40))
    app.processEvents()
    assert v.sculpt_mode == "" and v.r.mask is not None
    a.grab()

    # voltar à série devolve o quadro ao normal
    tab.close_3d(a)
    assert a.render3d is None and a.series_uid == uid and a.frames
    assert not tab.render3d_bar.isVisible()
    w.close()
