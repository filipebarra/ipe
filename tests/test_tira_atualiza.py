"""0.99.4: a tira de séries do exame aberto se atualiza sozinha quando chega série nova."""
import shutil

import pydicom
from pydicom.uid import generate_uid
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer


def _uids_na_tira(tab):
    return {tab.strip.item(i).data(Qt.UserRole) for i in range(tab.strip.count())}


def test_tira_pega_serie_nova_e_imagens_novas(env, sample_dir, tmp_path):
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    files = sorted((sample_dir / "CT_ACC1001").glob("*.dcm"))
    p1, p2, p3 = (tmp_path / n for n in ("p1", "p2", "p3"))
    for p in (p1, p2, p3):
        p.mkdir()
    for f in files[:10]:
        shutil.copy(f, p1)
    for f in files[10:]:
        shutil.copy(f, p2)
    nova = generate_uid()
    for i, f in enumerate(files[:3]):          # uma série nova no mesmo exame (como a tabela dos discos)
        ds = pydicom.dcmread(f)
        ds.SeriesInstanceUID, ds.SOPInstanceUID = nova, generate_uid()
        ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
        ds.SeriesNumber, ds.SeriesDescription = 973, "Discos: medidas"
        ds.save_as(p3 / f"n{i}.dcm")
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w._vigia_timer.stop()
    w.show()
    Importer(db, paths.storage).import_paths([p1])
    uid = repo.search_studies()[0].study_uid
    w.open_study(uid)
    app.processEvents()
    tab = w.all_viewer_tabs()[-1]
    w._vigiar_series()                         # primeira passada: só anota
    assert nova not in _uids_na_tira(tab)
    Importer(db, paths.storage).import_paths([p2, p3])
    w._vigiar_series()
    app.processEvents()
    assert nova in _uids_na_tira(tab)
    assert len(tab.viewports[0].frames) == 60
    n = tab.strip.count()
    w._vigiar_series()                         # nada mudou: não refaz
    assert tab.strip.count() == n
    w.close()
