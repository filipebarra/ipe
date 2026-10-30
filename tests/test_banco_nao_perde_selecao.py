"""0.99.7: a lista do banco se refaz quando chegam exames sem tirar você do exame escolhido."""
import shutil

from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer


def test_chegar_exame_nao_tira_a_selecao(env, sample_dir, tmp_path):
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    pastas = sorted(p for p in sample_dir.iterdir() if p.is_dir())
    primeira, resto = pastas[0], pastas[1:]
    Importer(db, paths.storage).import_paths([primeira] + resto[:-1])
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.show()
    try:
        b = w.browser
        b.refresh()
        assert b.model.rowCount() >= 2
        b.table.selectRow(1)
        app.processEvents()
        uid = b.selected_rows()[0].study_uid
        n_series = b.series_list.count()
        assert n_series > 0
        item0 = b.series_list.item(0)
        refeitas = []
        orig = b._fill_series
        b._fill_series = lambda u: (refeitas.append(u), orig(u))
        # chega um exame novo e a lista se refaz
        Importer(db, paths.storage).import_paths([resto[-1]])
        b.refresh()
        app.processEvents()
        assert [r.study_uid for r in b.selected_rows()] == [uid], "continua no mesmo exame"
        cur = b.table.currentIndex()
        assert b.model.row(b.proxy.mapToSource(cur).row()).study_uid == uid
        assert b.series_list.count() == n_series and b.series_list.item(0) is item0 and not refeitas, \
            "as séries do exame escolhido não piscam"
        # chegaram imagens novas DESTE exame: as séries dele se refazem (e a seleção fica)
        b.refresh()
        assert not refeitas
    finally:
        w.close()
