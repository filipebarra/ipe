"""Painel de medidas e a ferramenta Selecionar."""
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
    w.resize(1300, 850)
    w.show()
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 1)
    app.processEvents()
    yield app, w, tab, tab.viewports[0]
    w.close()


def _w(vp, x, y):
    return vp.image_to_widget(QPointF(x, y)).toPoint()


def _drag(vp, a, b, steps=6):
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, steps + 1):
        QTest.mouseMove(vp, a + (b - a) * i / steps)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, b)


def _uma_regua(tab, vp):
    tab.set_left_tool("measure")
    _drag(vp, _w(vp, 50, 50), _w(vp, 150, 50))
    return vp.frame_annotations()[-1]


# ------------------------------------------------------------------ ferramenta Selecionar
def test_selecionar_nao_cria_medida(viewer):
    app, w, tab, vp = viewer
    a = _uma_regua(tab, vp)
    n = len(vp.frame_annotations())
    tab.set_left_tool("pick")
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, _w(vp, 300, 300))   # no vazio
    app.processEvents()
    assert len(vp.frame_annotations()) == n, "a ferramenta de selecionar não cria nada"
    assert vp.selected is None
    del a


def test_selecionar_escolhe_e_move_a_medida(viewer):
    app, w, tab, vp = viewer
    a = _uma_regua(tab, vp)
    tab.set_left_tool("pick")
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, _w(vp, 100, 50))    # no meio da régua
    app.processEvents()
    assert vp.selected is a
    antes = list(a.points)
    _drag(vp, _w(vp, 100, 50), _w(vp, 100, 90))
    app.processEvents()
    assert a.points != antes, "arrastar a selecionada move a medida inteira"
    assert len(vp.frame_annotations()) == 1


def test_selecionar_edita_pela_ponta(viewer):
    app, w, tab, vp = viewer
    a = _uma_regua(tab, vp)
    tab.set_left_tool("pick")
    fim = tuple(a.points[1])
    _drag(vp, _w(vp, *fim), _w(vp, 200, 50))
    app.processEvents()
    assert a.points[1] != fim and len(vp.frame_annotations()) == 1


def test_selecionar_avisa_quem_mostra_a_lista(viewer):
    app, w, tab, vp = viewer
    a = _uma_regua(tab, vp)
    escolhidas = []
    vp.sig.annotation_picked.connect(lambda _v, ann: escolhidas.append(ann))
    tab.set_left_tool("pick")
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, _w(vp, 100, 50))
    app.processEvents()
    assert escolhidas and escolhidas[-1] is a
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, _w(vp, 300, 300))
    app.processEvents()
    assert escolhidas[-1] is None


# ------------------------------------------------------------------ painel
def test_o_painel_lista_as_medidas_do_exame(viewer):
    app, w, tab, vp = viewer
    _uma_regua(tab, vp)
    tab.set_left_tool("ellipse")
    _drag(vp, _w(vp, 100, 100), _w(vp, 140, 140))
    app.processEvents()
    tab.measures_action.setChecked(True)
    app.processEvents()
    p = tab.measures_panel
    assert p is not None and p.isVisible()
    p.refresh()
    assert len(p.linhas) == 2
    tipos = sorted(d["tipo"] for d in p.linhas)
    assert "Régua" in tipos and any("elíptica" in t for t in tipos)
    regua = next(d for d in p.linhas if d["tipo"] == "Régua")
    assert "mm" in regua["valor"] or "px" in regua["valor"]


def test_clicar_no_painel_leva_ate_a_medida(viewer):
    app, w, tab, vp = viewer
    a = _uma_regua(tab, vp)
    vp.go_to(0)
    vp.selected = None
    tab.measures_action.setChecked(True)
    app.processEvents()
    p = tab.measures_panel
    p.refresh()
    p.table.selectRow(0)
    app.processEvents()
    assert vp.selected is not None and vp.selected.db_id == a.db_id
    assert (vp.frames[vp.index].sop_uid, vp.frames[vp.index].frame_index) == a.frame_key


def test_o_painel_apaga_a_medida(viewer, monkeypatch):
    app, w, tab, vp = viewer
    _uma_regua(tab, vp)
    tab.measures_action.setChecked(True)
    app.processEvents()
    p = tab.measures_panel
    p.refresh()
    p.table.selectRow(0)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    p._apagar()
    app.processEvents()
    assert p.linhas == [] and vp.frame_annotations() == []


def test_o_painel_vazio_diz_o_que_isso_significa(viewer):
    app, w, tab, vp = viewer
    tab.measures_action.setChecked(True)
    app.processEvents()
    p = tab.measures_panel
    p.refresh()
    assert p.linhas == [] and p.vazio.isVisible() and "Nenhuma medida" in p.vazio.text()


# ------------------------------------------------------------------ 0.53: eixos e janela
def test_a_segmentacao_guardada_mostra_os_tres_eixos(viewer):
    """Ele marcou a lesão e os três eixos não apareciam: o rótulo da medida só dizia o volume."""
    from ipe.imaging import measure as M
    app, w, tab, vp = viewer
    h, wd = vp._img.pixels.shape[:2]
    tab.segment_at(vp, wd / 2, h / 2)
    app.processEvents()
    dlg = [d for d in getattr(tab, "_seg_dialogs", []) if d.isVisible()][-1]
    assert dlg.res is not None and dlg.res.eixos_mm, "a conta dos eixos tem de sair"
    assert "eixos" in dlg.res.summary()
    meta = dlg.res.meta()
    assert len(meta["eixos_mm"]) == 3
    ann = M.Annotation("seg", ("x", 0), [], meta=meta)
    linhas = M.labels(ann, None, None, "CT")
    assert any(t.startswith("Eixos") and "×" in t for t in linhas), linhas
    dlg.discard()


def test_sem_eixos_guardados_sobra_o_maior(viewer):
    from ipe.imaging import measure as M
    ann = M.Annotation("seg", ("x", 0), [], meta={"ml": 3.0, "mm": 21.5})
    assert "Maior eixo 21.5 mm" in M.labels(ann, None, None, "CT")


def test_o_painel_de_medidas_e_uma_janela(viewer):
    from PySide6.QtWidgets import QDialog
    app, w, tab, vp = viewer
    tab.measures_action.setChecked(True)
    app.processEvents()
    p = tab.measures_panel
    assert isinstance(p, QDialog) and p.isWindow(), "é janela própria, não painel preso à direita"
    assert p.isVisible() and not p.isModal()
    assert p not in [tab._body.itemAt(i).widget() for i in range(tab._body.count())]
    p.close()
    app.processEvents()
    assert not tab.measures_action.isChecked(), "fechar pelo X desmarca o botão"
