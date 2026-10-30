"""Shift e Ctrl emprestam o botão esquerdo, sem trocar a ferramenta da barra."""
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from PySide6.QtCore import QEvent
from PySide6.QtGui import QKeyEvent, QMouseEvent

from ipe.core.config import Settings
from ipe.importer.scanner import Importer


def _w2(vp, x, y):
    return vp.image_to_widget(QPointF(x, y)).toPoint()


def _arrasta(vp, a, b, steps=6):
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, steps + 1):
        QTest.mouseMove(vp, a + (b - a) * i / steps)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, b)


def _evento_mover(vp, ponto, mods):
    """QTest.mouseMove não leva modificador: o evento é montado à mão."""
    return QMouseEvent(QEvent.MouseMove, QPointF(ponto), QPointF(ponto),
                       Qt.NoButton, Qt.NoButton, mods)


@pytest.fixture()
def viewer(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1200, 800)
    w.show()
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 1)
    app.processEvents()
    yield app, w, tab, tab.viewports[0]
    w.close()


def test_ctrl_esquerdo_rola_os_cortes(viewer):
    app, w, tab, vp = viewer
    tab.set_left_tool("wl")
    i0, larg = vp.index, vp.state.width
    a = QPoint(200, 200)
    QTest.mousePress(vp, Qt.LeftButton, Qt.ControlModifier, a)
    for y in range(200, 280, 8):
        QTest.mouseMove(vp, QPoint(200, y), 10)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.ControlModifier, QPoint(200, 280))
    app.processEvents()
    assert vp.index != i0, "com Ctrl apertado o esquerdo rola"
    assert vp.state.width == larg, "e não mexe na janela"
    assert tab.left_tool == "wl", "a ferramenta da barra não muda"


def test_soltar_o_ctrl_devolve_a_ferramenta(viewer):
    app, w, tab, vp = viewer
    tab.set_left_tool("wl")
    a = QPoint(200, 200)
    QTest.mousePress(vp, Qt.LeftButton, Qt.ControlModifier, a)
    QTest.mouseMove(vp, QPoint(200, 240), 10)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.ControlModifier, QPoint(200, 240))
    app.processEvents()
    larg = vp.state.width
    i0 = vp.index
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, a)      # agora sem tecla nenhuma
    QTest.mouseMove(vp, QPoint(260, 200), 10)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, QPoint(260, 200))
    app.processEvents()
    assert vp.state.width != larg and vp.index == i0, "voltou a ser janela/nível"


def test_shift_esquerdo_e_o_cursor_3d(viewer):
    app, w, tab, vp = viewer
    tab.set_left_tool("wl")
    pedidos = []
    vp.sig.cursor_moved.connect(lambda _v, p: pedidos.append(p))
    larg = vp.state.width
    QTest.mousePress(vp, Qt.LeftButton, Qt.ShiftModifier, QPoint(200, 200))
    for x in range(200, 260, 10):
        QTest.mouseMove(vp, QPoint(x, 220), 10)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.ShiftModifier, QPoint(260, 220))
    app.processEvents()
    assert len(pedidos) >= 2, "segurar Shift e mexer o mouse leva o ponto junto"
    assert vp.state.width == larg and tab.left_tool == "wl"


def test_dá_para_desligar_as_teclas(viewer):
    app, w, tab, vp = viewer
    w.settings.set("viewer.teclas_emprestadas", {})
    tab.set_left_tool("wl")
    larg = vp.state.width
    QTest.mousePress(vp, Qt.LeftButton, Qt.ControlModifier, QPoint(200, 200))
    QTest.mouseMove(vp, QPoint(260, 200), 10)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.ControlModifier, QPoint(260, 200))
    app.processEvents()
    assert vp.state.width != larg, "desligado, Ctrl não empresta nada"
    w.settings.set("viewer.teclas_emprestadas", dict(type(vp).PADRAO_TECLAS))


def test_o_balao_do_mouse_conta_as_teclas(viewer):
    app, w, tab, vp = viewer
    linhas = dict(vp.mouse_actions())
    assert linhas.get("Shift (segurar)") and linhas.get("Ctrl (segurar)")


def test_shift_sem_clicar_ja_leva_o_ponto(viewer):
    """Segurar o Shift e mexer o mouse basta: não precisa clicar."""
    app, w, tab, vp = viewer
    tab.set_left_tool("wl")
    pontos = []
    vp.sig.cursor_moved.connect(lambda _v, p: pontos.append(p))
    larg = vp.state.width
    for x in range(200, 280, 20):
        QTest.mouseMove(vp, QPoint(x, 210), 10)
        vp.mouseMoveEvent(_evento_mover(vp, QPoint(x, 210), Qt.ShiftModifier))
    app.processEvents()
    assert len(pontos) >= 3, "o ponto 3D acompanha o mouse com o Shift apertado"
    assert vp.state.width == larg and tab.left_tool == "wl"
    assert vp.cursor().shape() == Qt.CrossCursor, "o ponteiro avisa que o Shift está valendo"


def test_sem_shift_passar_o_mouse_nao_mexe_em_nada(viewer):
    app, w, tab, vp = viewer
    tab.set_left_tool("wl")
    pontos = []
    vp.sig.cursor_moved.connect(lambda _v, p: pontos.append(p))
    for x in range(200, 280, 20):
        vp.mouseMoveEvent(_evento_mover(vp, QPoint(x, 210), Qt.NoModifier))
    app.processEvents()
    assert pontos == []


def test_soltar_o_shift_devolve_o_ponteiro(viewer):
    app, w, tab, vp = viewer
    vp.mouseMoveEvent(_evento_mover(vp, QPoint(220, 210), Qt.ShiftModifier))
    assert vp.cursor().shape() == Qt.CrossCursor
    vp.keyReleaseEvent(QKeyEvent(QKeyEvent.KeyRelease, Qt.Key_Shift, Qt.NoModifier))
    assert vp.cursor().shape() == Qt.ArrowCursor


def test_trocar_as_teclas_nas_preferencias(viewer):
    """Elas moraram numa caixa de liga/desliga; agora são escolha na aba de atalhos."""
    from ipe.ui.preferences import PreferencesDialog
    app, w, tab, vp = viewer
    dlg = PreferencesDialog(w.settings)
    assert set(dlg.teclas_emprestadas().items()) == {("cross", "shift"), ("scroll", "ctrl")}
    dlg.c_teclas["cross"].setCurrentIndex(dlg.c_teclas["cross"].findData("alt"))
    dlg.c_teclas["scroll"].setCurrentIndex(dlg.c_teclas["scroll"].findData("shift"))
    w.settings.set("viewer.teclas_emprestadas", dlg.teclas_emprestadas())
    dlg.close()
    # agora Shift rola e Alt é o cursor 3D
    tab.set_left_tool("wl")
    i0 = vp.index
    QTest.mousePress(vp, Qt.LeftButton, Qt.ShiftModifier, QPoint(200, 200))
    QTest.mouseMove(vp, QPoint(200, 260), 10)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.ShiftModifier, QPoint(200, 260))
    app.processEvents()
    assert vp.index != i0
    pontos = []
    vp.sig.cursor_moved.connect(lambda _v, p: pontos.append(p))
    vp.mouseMoveEvent(_evento_mover(vp, QPoint(240, 210), Qt.AltModifier))
    assert pontos, "o cursor 3D passou para o Alt"
    w.settings.set("viewer.teclas_emprestadas", dict(type(vp).PADRAO_TECLAS))


def test_a_mesma_tecla_para_duas_ferramentas_e_recusada(viewer, monkeypatch):
    from ipe.ui.preferences import PreferencesDialog
    from PySide6.QtWidgets import QMessageBox
    app, w, tab, vp = viewer
    dlg = PreferencesDialog(w.settings)
    for f in ("cross", "scroll"):
        dlg.c_teclas[f].setCurrentIndex(dlg.c_teclas[f].findData("shift"))
    ditos = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: ditos.append(a[1] if len(a) > 1 else ""))
    dlg._save()
    assert ditos and dlg.isVisible() is False or ditos, "tem de avisar, não salvar calado"
    dlg.close()


def test_ctrl_sem_clicar_tambem_rola(viewer):
    """Igual ao Shift: a tecla segurada já basta, sem clique."""
    app, w, tab, vp = viewer
    tab.set_left_tool("wl")
    i0, larg = vp.index, vp.state.width
    for y in range(200, 290, 10):
        vp.mouseMoveEvent(_evento_mover(vp, QPoint(240, y), Qt.ControlModifier))
    app.processEvents()
    assert vp.index != i0, "com Ctrl segurado, mexer o mouse rola os cortes"
    assert vp.state.width == larg and tab.left_tool == "wl"
    assert vp.cursor().shape() == Qt.SizeVerCursor
    vp.keyReleaseEvent(QKeyEvent(QKeyEvent.KeyRelease, Qt.Key_Control, Qt.NoModifier))
    assert vp.cursor().shape() == Qt.ArrowCursor


def test_subir_e_descer_rolam_para_os_dois_lados(viewer):
    app, w, tab, vp = viewer
    vp.go_to(30)
    for y in range(200, 280, 10):
        vp.mouseMoveEvent(_evento_mover(vp, QPoint(240, y), Qt.ControlModifier))
    desceu = vp.index
    for y in range(280, 200, -10):
        vp.mouseMoveEvent(_evento_mover(vp, QPoint(240, y), Qt.ControlModifier))
    assert desceu > 30 and vp.index < desceu


def test_o_menu_do_botao_direito_monta(viewer):
    """A linha de corte entrou no menu com o sinal errado e derrubava o menu inteiro."""
    app, w, tab, vp = viewer
    m = vp.build_context_menu(None)
    textos = [a.text() for a in m.actions()]
    assert len(textos) > 5
    assert any("Linhas de corte" in t for t in textos)
    m.deleteLater()


# ------------------------------------------------------------------ tamanho da letra
def test_tamanho_da_letra_das_anotacoes(viewer):
    from PySide6.QtGui import QPixmap, QPainter
    app, w, tab, vp = viewer
    tab.set_left_tool("measure")
    _arrasta(vp, _w2(vp, 50, 50), _w2(vp, 150, 50))
    app.processEvents()

    def pontos():
        pm = QPixmap(vp.size())
        p = QPainter(pm)
        vp._draw_measurements(p)
        tam = p.font().pointSizeF()
        p.end()
        return tam
    base = pontos()
    w.settings.set("viewer.measure_font_scale", 2.0)
    assert pontos() == pytest.approx(base * 2, rel=0.01)
    w.settings.set("viewer.measure_font_scale", 1.0)


def test_tamanho_da_letra_dos_cantos(viewer):
    from PySide6.QtGui import QPixmap, QPainter
    app, w, tab, vp = viewer

    def pontos():
        pm = QPixmap(vp.size())
        p = QPainter(pm)
        vp._draw_overlay(p)
        tam = p.font().pointSizeF()
        p.end()
        return tam
    base = pontos()
    w.settings.set("viewer.overlay_font_scale", 1.8)
    assert pontos() == pytest.approx(base * 1.8, rel=0.01)
    w.settings.set("viewer.overlay_font_scale", 1.0)


def test_valor_maluco_na_escala_nao_derruba(viewer):
    app, w, tab, vp = viewer
    for ruim in ("", "abc", None, 99.0, 0.0):
        w.settings.set("viewer.measure_font_scale", ruim)
        assert 0.6 <= vp.escala_da_letra("viewer.measure_font_scale") <= 2.5
    w.settings.set("viewer.measure_font_scale", 1.0)


def test_as_preferencias_guardam_a_letra(viewer):
    from ipe.ui.preferences import PreferencesDialog
    app, w, tab, vp = viewer
    dlg = PreferencesDialog(w.settings)
    dlg.s_letra_med.setValue(140)
    dlg.s_letra_ov.setValue(80)
    dlg._save()
    assert w.settings.get("viewer.measure_font_scale") == 1.4
    assert w.settings.get("viewer.overlay_font_scale") == 0.8
    w.settings.set("viewer.measure_font_scale", 1.0)
    w.settings.set("viewer.overlay_font_scale", 1.0)


def test_ctrl_comeca_a_rolar_do_corte_em_que_esta(viewer):
    """0.99.7: segurar o Ctrl de novo (ou em outro lugar) não pula cortes no primeiro movimento."""
    app, w, tab, vp = viewer
    vp.go_to(30)
    for y in range(200, 240, 10):                               # rola um pouco com Ctrl
        vp.mouseMoveEvent(_evento_mover(vp, QPoint(240, y), Qt.ControlModifier))
    vp.keyReleaseEvent(QKeyEvent(QKeyEvent.KeyRelease, Qt.Key_Control, Qt.NoModifier))
    for y in range(240, 560, 40):                               # mexe o mouse sem Ctrl, para longe
        vp.mouseMoveEvent(_evento_mover(vp, QPoint(240, y), Qt.NoModifier))
    i0 = vp.index
    vp.keyPressEvent(QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Control, Qt.ControlModifier))
    vp.mouseMoveEvent(_evento_mover(vp, QPoint(240, 560), Qt.ControlModifier))
    assert abs(vp.index - i0) <= 1, "o primeiro movimento com Ctrl não pula"
    # saiu do quadro com Ctrl e voltou em outra altura: começa do zero
    vp.leaveEvent(None)
    vp.mouseMoveEvent(_evento_mover(vp, QPoint(240, 150), Qt.ControlModifier))
    assert abs(vp.index - i0) <= 1
    # salto grande de uma vez (ponteiro que voltou de outro monitor) não rola
    vp.mouseMoveEvent(_evento_mover(vp, QPoint(240, 600), Qt.ControlModifier))
    assert abs(vp.index - i0) <= 1
    # e continua rolando normalmente depois
    for y in range(600, 640, 8):
        vp.mouseMoveEvent(_evento_mover(vp, QPoint(240, y), Qt.ControlModifier))
    assert vp.index > i0


def test_ctrl_clique_na_barra_de_posicao_nao_pula(viewer):
    app, w, tab, vp = viewer
    vp.go_to(5)
    r = vp.posbar_rect()
    perto_do_fim = QPoint(int(r.center().x()), int(r.bottom() - 2))
    QTest.mousePress(vp, Qt.LeftButton, Qt.ControlModifier, perto_do_fim)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.ControlModifier, perto_do_fim)
    assert vp.index == 5, "com Ctrl o clique é o começo do rolar, não um pulo pela barra"
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, perto_do_fim)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, perto_do_fim)
    assert vp.index > 5, "sem Ctrl a barra continua levando ao corte"
