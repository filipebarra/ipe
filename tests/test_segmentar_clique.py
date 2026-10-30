"""O clique da ferramenta Segmentar.

O defeito que estes testes guardam: o crescimento de região só era tratado no *mover* o mouse,
depois da linha que marca o arrasto — ou seja, nunca. No *soltar* não havia ramo nenhum, então o
clique na lesão não emitia nada e a tela não dizia por quê. O teste antigo chamava
`tab.segment_at` direto e passava: testava o contrato errado.
"""
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from ipe.core.config import Settings
from ipe.importer.scanner import Importer


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


def _w(vp, x, y):
    return vp.image_to_widget(QPointF(x, y)).toPoint()


def test_o_clique_pede_a_segmentacao(viewer):
    app, w, tab, vp = viewer
    pedidos = []
    vp.sig.segment_requested.connect(lambda v, u, y: pedidos.append((u, y)))
    tab.set_left_tool("grow")
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, _w(vp, 100, 120))
    app.processEvents()
    assert len(pedidos) == 1
    assert pedidos[0][0] == pytest.approx(100, abs=2) and pedidos[0][1] == pytest.approx(120, abs=2)


def test_o_clique_demorado_tambem_vale(viewer):
    """Mirar numa lesão demora mais que um clique rápido: o limite de tempo não se aplica aqui."""
    app, w, tab, vp = viewer
    pedidos = []
    vp.sig.segment_requested.connect(lambda v, u, y: pedidos.append((u, y)))
    tab.set_left_tool("grow")
    alvo = _w(vp, 100, 120)
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, alvo)
    QTest.qWait(400)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, alvo)
    app.processEvents()
    assert len(pedidos) == 1


def test_arrastar_com_a_ferramenta_nao_segmenta(viewer):
    app, w, tab, vp = viewer
    pedidos = []
    vp.sig.segment_requested.connect(lambda v, u, y: pedidos.append((u, y)))
    tab.set_left_tool("grow")
    a, b = _w(vp, 60, 60), _w(vp, 160, 160)
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, 7):
        QTest.mouseMove(vp, a + (b - a) * i / 6)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, b)
    app.processEvents()
    assert pedidos == []


def test_o_clique_abre_a_janela_da_medida(viewer):
    app, w, tab, vp = viewer
    tab.set_left_tool("grow")
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, _w(vp, 100, 120))
    app.processEvents()
    janelas = [d for d in getattr(tab, "_seg_dialogs", []) if d.isVisible()]
    assert janelas, "o clique na imagem tem que abrir a janela de segmentação"
    janelas[-1].discard()


def test_quando_nao_da_a_tela_diz_o_motivo(viewer, monkeypatch):
    """Nenhum retorno mudo: era isso que fazia o clique parecer “não acontece nada”."""
    app, w, tab, vp = viewer
    ditos = []
    monkeypatch.setattr(QMessageBox, "information",
                        lambda *a, **k: ditos.append(a[2] if len(a) > 2 else ""))
    tab.segment_at(vp, 1e6, 1e6)
    assert ditos and ditos[0].strip()
