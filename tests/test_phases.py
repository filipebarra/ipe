"""Fases dinâmicas em séries separadas (agrupar, navegar, subtrair, curva) e escolher séries ao abrir."""
import numpy as np
import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from ipe.core.config import Settings
from ipe.imaging import phases as PH
from ipe.imaging.series import build_frames
from ipe.importer.scanner import Importer
from test_measure_tools import make_dynamic


@pytest.fixture()
def dyn(env, sample_dir, tmp_path):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    uid = make_dynamic(tmp_path / "dyn", one_series=False)
    Importer(db, paths.storage).import_paths([tmp_path / "dyn"])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1400, 850)
    w.show()
    w.browser.refresh()
    yield app, w, uid
    w.close()


def _series(w, uid):
    return sorted(w.repo.series_for_study(uid), key=lambda s: s.series_number)


def _drop(app, vp, uid, where):
    m = QMimeData()
    m.setData("application/x-dicomviewer-series", uid.encode())
    app.sendEvent(vp, QDragEnterEvent(where.toPoint(), Qt.CopyAction, m, Qt.LeftButton, Qt.NoModifier))
    app.sendEvent(vp, QDropEvent(where, Qt.CopyAction, m, Qt.LeftButton, Qt.NoModifier))


def test_detect_and_order(dyn):
    app, w, uid = dyn
    ss = _series(w, uid)
    cands = [(s.series_uid, build_frames(w.repo.instances_for_series(s.series_uid), s.series_uid),
              s.series_number, s.modality, s.description) for s in reversed(ss)]
    found = PH.detect(cands)
    assert found == [[s.series_uid for s in ss]]          # em ordem de aquisição
    ct = w.repo.series_for_study(w.repo.find_study_uids(accession="ACC1001")[0])[0]
    ok, why = PH.compatible(cands[0][1], build_frames(w.repo.instances_for_series(ct.series_uid)))
    assert not ok and "número de imagens" in why


def test_drag_to_corner_joins_phases(dyn):
    app, w, uid = dyn
    ss = _series(w, uid)
    w.open_study(uid, [ss[0].series_uid])
    tab = w.all_viewer_tabs()[-1]
    vp = tab.viewports[0]
    assert tab._layout == (1, 1) and vp.series_uid == ss[0].series_uid
    vp.go_to(1)
    corner = vp.join_rect().center()
    _drop(app, vp, ss[2].series_uid, corner)
    assert vp.series_uid.startswith("group:") and len(vp.phases) == 2
    assert vp.phase == 1 and vp.index == 1                 # mostra a fase que chegou, mesmo corte
    _drop(app, vp, ss[1].series_uid, corner)
    assert len(vp.phases) == 3
    g = tab.groups[int(vp.series_uid[6:])]
    assert g["series_uids"] == [s.series_uid for s in ss[:3]]    # reordenado pelo horário
    # soltar no meio troca a série (comportamento de antes)
    _drop(app, vp, ss[4].series_uid, QPointF(20, 20))
    assert vp.series_uid == ss[4].series_uid and vp.phases is None


def test_group_navigation_subtraction_and_curve(dyn, monkeypatch):
    app, w, uid = dyn
    ss = _series(w, uid)
    w.open_study(uid)
    tab = w.all_viewer_tabs()[-1]
    vp = tab.viewports[0]
    gid = tab.group_series([s.series_uid for s in reversed(ss)], "Dinâmica mama", vp)
    assert vp.series_uid == f"group:{gid}" and len(vp.phases) == 5 and vp.phase == 0
    vp.setFocus()
    # As setas ← → saíram da navegação na 0.65 (são o atalho das etapas da mamografia): a fase
    # anda pela ação "Dinâmica: próxima fase", que nasce sem tecla, e pelo canto clicável.
    tab.active = vp
    tab.actions_by_id["phase.next"].trigger()
    tab.actions_by_id["phase.next"].trigger()
    assert vp.phase == 2
    onde = vp.index
    QTest.keyClick(vp, Qt.Key_Right)
    assert (vp.phase, vp.index) == (2, onde), "a seta voltou a mexer no quadro"
    QTest.keyClick(vp, Qt.Key_Down)                        # ↓ continua rolando cortes
    assert vp.index == onde + 1 and vp.phase == 2
    lesion = vp._img.pixels[32, 32]
    vp.set_subtract(True)
    assert vp._img.pixels[32, 32] == pytest.approx(lesion - 100)   # fase − pré
    assert vp._img.pixels[5, 5] == pytest.approx(0)
    assert "subtração" in vp.phase_text()
    vp.set_subtract(False)
    # curva tempo-intensidade usa as fases do grupo
    from ipe.ui.viewer import tic
    shown = {}
    monkeypatch.setattr(tic.TicDialog, "exec", lambda self: shown.update(r=self.result) or 0)
    tab.set_left_tool("tic")
    a = vp.image_to_widget(QPointF(27, 27)).toPoint()
    b = vp.image_to_widget(QPointF(37, 37)).toPoint()
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, a)
    for i in range(1, 6):
        QTest.mouseMove(vp, a + (b - a) * i / 5)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, b)
    assert shown["r"]["curve_type"].startswith("III") and len(shown["r"]["enhancement"]) == 5
    # o grupo fica salvo: reabrindo, a dinâmica já aparece num quadro só
    w._close_tab(w.tabs.indexOf(tab))
    w.open_study(uid)
    tab2 = w.all_viewer_tabs()[-1]
    assert tab2.viewports[0].series_uid == f"group:{gid}"
    assert any(tab2.strip.item(i).data(Qt.UserRole) == f"group:{gid}" for i in range(tab2.strip.count()))
    # tirar uma fase e desfazer
    vp2 = tab2.viewports[0]
    vp2.set_phase(4)
    tab2._group_action(vp2, "remove_phase")
    assert len(vp2.phases) == 4
    tab2.ungroup(gid)
    assert not vp2.series_uid.startswith("group:") and not w.repo.series_groups(uid)


def test_group_selected_and_incompatible(dyn, monkeypatch):
    app, w, uid = dyn
    ss = _series(w, uid)
    w.open_study(uid)
    tab = w.all_viewer_tabs()[-1]
    tab.add_study(w.repo.find_study_uids(accession="ACC1001")[0])      # outra geometria
    msgs = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a: msgs.append(a[2])))
    ct = next(s for s in tab.series if s.modality == "CT")
    assert tab.group_series([ss[0].series_uid, ct.series_uid]) is None and msgs
    # detectar e confirmar
    from ipe.ui.viewer import viewer_tab as VT
    monkeypatch.setattr(VT.PhaseGroupDialog, "exec", lambda self: 1)
    tab.detect_groups()
    assert len(tab.groups) == 1 and len(next(iter(tab.groups.values()))["series_uids"]) == 5


def test_choose_series_to_open(dyn):
    app, w, uid = dyn
    study = w.repo.find_study_uids(accession="ACC2001")[0]         # RM com 2 séries
    ss = w.repo.series_for_study(study)
    w.open_study(study, [ss[1].series_uid])
    tab = w.all_viewer_tabs()[-1]
    assert tab._layout == (1, 1) and tab.viewports[0].series_uid == ss[1].series_uid
    uids = [tab.strip.item(i).data(Qt.UserRole) for i in range(tab.strip.count())]
    assert ss[0].series_uid not in uids and "action:toggle_all" in uids
    toggle = next(tab.strip.item(i) for i in range(tab.strip.count())
                  if tab.strip.item(i).data(Qt.UserRole) == "action:toggle_all")
    tab._strip_clicked(toggle)
    uids = [tab.strip.item(i).data(Qt.UserRole) for i in range(tab.strip.count())]
    assert ss[0].series_uid in uids
    # estudo já aberto: escolher de novo põe as séries nos quadros
    w.open_study(study, [ss[0].series_uid, ss[1].series_uid])
    assert tab._layout == (1, 2) and [v.series_uid for v in tab._shown()] == [ss[0].series_uid, ss[1].series_uid]
    # diálogo de escolha
    from ipe.ui.series_chooser import SeriesChooserDialog
    dlg = SeriesChooserDialog(w.repo, study, [ss[0].series_uid])
    assert dlg.chosen() == [ss[0].series_uid]
    dlg._set_all(Qt.Checked)
    assert len(dlg.chosen()) == 2
    # banco: duplo clique numa série abre só ela
    w._close_tab(w.tabs.indexOf(tab))
    b = w.browser
    row = next(i for i, r in enumerate(b.model.rows) if r.study_uid == study)
    b.table.selectRow(b.proxy.mapFromSource(b.model.index(row, 0)).row())
    app.processEvents()
    item = next(b.series_list.item(i) for i in range(b.series_list.count())
                if b.series_list.item(i).data(Qt.UserRole) == ss[0].series_uid)
    b._open_series_item(item)
    tab = w.all_viewer_tabs()[-1]
    assert tab.study_uid == study and [v.series_uid for v in tab._shown()] == [ss[0].series_uid]
