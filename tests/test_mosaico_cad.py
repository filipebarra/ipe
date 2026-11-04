"""0.99.43: mosaico de cortes no quadro e CAD oculto até o leitor revelar."""
import sys
from pathlib import Path

import numpy as np
import pytest
from pydicom.uid import generate_uid

from ipe.imaging import measure as M
from ipe.imaging.volume import Volume

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture
def janela(env, tmp_path):
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    from test_registro_rigido import _serie
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    d = np.zeros((10, 32, 32), np.float32)
    for k in range(10):
        d[k, 4:28, 4:28] = 100 + 10 * k
    v = Volume(d, np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 2.0]), 1.0, 1.0, None, "")
    estudo = generate_uid()
    serie = _serie(tmp_path / "a", v, estudo, generate_uid(), "Ax T1", "20261101")
    Importer(db, paths.storage).import_paths([tmp_path / "a"])
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    yield w, paths, db, repo, estudo, serie
    w._really_quit = True
    w.settings.set("ui.confirmar_sair", False)
    w.close()


def test_mosaico(janela):
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent, QWheelEvent
    from PySide6.QtWidgets import QApplication
    w, *_r = janela
    w.open_study(_r[3])
    QApplication.processEvents()
    tab = next(iter(w.all_viewer_tabs()))
    vp = tab.viewports[0]
    vp.resize(400, 400)
    vp.go_to(0)
    vp.set_mosaico((2, 2))
    assert vp.em_mosaico()
    img = vp.grab()                                         # pinta as 4 imagens sem erro
    assert not img.isNull()
    W, H = vp.width(), vp.height()
    assert vp.mosaico_indice_em(QPointF(W * 0.75, H * 0.75)) == 3 and vp.mosaico_indice_em(QPointF(W * 0.25, H * 0.25)) == 0
    ev = QWheelEvent(QPointF(200, 200), QPointF(200, 200), QPoint(0, 0), QPoint(0, -120), Qt.NoButton,
                     Qt.NoModifier, Qt.NoScrollPhase, False)
    vp.wheelEvent(ev)
    assert vp.index == 4                                    # a roda vira a página (4 imagens)
    # medir no mosaico não cria medida
    tab.set_left_tool("measure")
    n = len(vp.annotations)
    QTestPress = QMouseEvent(QEvent.MouseButtonPress, QPointF(50, 50), QPointF(50, 50), Qt.LeftButton,
                             Qt.LeftButton, Qt.NoModifier)
    vp.mousePressEvent(QTestPress)
    assert len(vp.annotations) == n and vp._press is None
    # duplo clique na 2ª imagem: sai do mosaico nela
    dc = QMouseEvent(QEvent.MouseButtonDblClick, QPointF(W * 0.75, H * 0.25), QPointF(W * 0.75, H * 0.25), Qt.LeftButton,
                     Qt.LeftButton, Qt.NoModifier)
    vp.mouseDoubleClickEvent(dc)
    assert vp.mosaico is None and vp.index == 5
    # o atalho anda pelos tamanhos
    vp.proximo_mosaico()
    assert vp.mosaico == (2, 2)
    vp.proximo_mosaico()
    vp.proximo_mosaico()
    vp.proximo_mosaico()
    assert vp.mosaico is None
    assert "view.mosaico" in tab.actions_by_id


def test_cad_oculto_ate_revelar(janela, tmp_path):
    from PySide6.QtWidgets import QApplication
    from ipe.exporter.sr import build_sr
    from ipe.importer.scanner import Importer
    w, paths, db, repo, estudo, serie = janela
    sop = repo.instances_for_series(serie)[0]["sop_uid"]
    a = M.Annotation("ellipse", (sop, 0), [(8.0, 8.0), (20.0, 20.0)], "", estudo, serie)
    repo.save_annotation(db_id=None, study_uid=estudo, series_uid=serie, sop_uid=sop, frame_index=0,
                         kind="ellipse", data=a.data_json())
    ds, _n = build_sr(repo, estudo)
    ds.SOPClassUID = ds.file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.88.50"   # CAD de mamografia
    ds.Manufacturer, ds.SeriesDescription = "CAD Fulano", "CAD"
    d = tmp_path / "cad"
    d.mkdir()
    ds.save_as(d / "cad.dcm", enforce_file_format=True)
    Importer(db, paths.storage).import_paths([d])
    repo.delete_annotation(next(r["id"] for r in repo.annotations_for_studies([estudo])))
    w.settings.set("cad.ler_antes", True)
    w.open_study(estudo)
    QApplication.processEvents()
    tab = next(iter(w.all_viewer_tabs()))
    tab.load_overlay_objects()
    cads = [o for o in tab.overlay_objects if o.source == "CAD"]
    assert cads and not any(o.enabled for o in cads)
    assert tab.revelar_cad() == len(cads) and all(o.enabled for o in cads)
    assert tab.revelar_cad() == 0
    assert "cad.revelar" in tab.actions_by_id
