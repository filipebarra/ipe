"""Corrigir tags DICOM (cópia) e filtros de nitidez/suavização."""
import numpy as np
import pydicom
from PySide6.QtWidgets import QApplication

from ipe.core import tag_edit as T
from ipe.imaging import filters as F


# ---------------------------------------------------------------- tags
def test_corrige_tags_gravando_copia(env, sample_dir, tmp_path):
    paths, db, repo = env
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([sample_dir])
    estudo = repo.search_studies()[0]
    serie = repo.series_for_study(estudo.study_uid)[0]
    arquivos = [i["path"] for i in repo.instances_for_series(serie.series_uid)]
    antes = T.read_values(arquivos[0])
    assert "PatientName" in antes and "ViewPosition" in antes

    # correção só de imagem/série: fica no mesmo exame
    saida = tmp_path / "corrigido"
    alguns = arquivos[:2]
    feitos = T.apply_to_files(alguns, {"ImageLaterality": "L", "ViewPosition": "MLO"}, saida)
    assert len(feitos) == len(alguns)
    ds = pydicom.dcmread(feitos[0])
    assert ds.ImageLaterality == "L" and ds.ViewPosition == "MLO"
    assert str(ds.StudyInstanceUID) == estudo.study_uid          # mesmo exame
    assert str(ds.SeriesInstanceUID) != serie.series_uid         # série nova
    assert ds.SOPInstanceUID != pydicom.dcmread(arquivos[0]).SOPInstanceUID
    assert ds.SourceImageSequence[0].ReferencedSOPInstanceUID    # aponta para a original
    assert "corrigido" in str(ds.SeriesDescription).lower()
    # todas as imagens corrigidas ficam na mesma série nova
    assert all(pydicom.dcmread(f).SeriesInstanceUID == ds.SeriesInstanceUID for f in feitos)
    # o arquivo original não foi tocado
    assert pydicom.dcmread(arquivos[0]).get("ImageLaterality", "") != "L" or antes.get("ImageLaterality") == "L"

    # correção de paciente: exame novo
    assert T.needs_new_study({"PatientName": "X"}) and not T.needs_new_study({"ViewPosition": "CC"})
    feitos2 = T.apply_to_files(arquivos[:1], {"PatientName": "SOUZA^MARIA", "PatientID": "999"},
                               tmp_path / "c2")
    ds2 = pydicom.dcmread(feitos2[0])
    assert str(ds2.PatientName) == "SOUZA^MARIA" and str(ds2.StudyInstanceUID) != estudo.study_uid
    assert T.describe({"ViewPosition": "MLO"}, antes)[0].startswith("Incidência:")


def test_dialogo_de_tags_corrige(env, sample_dir, tmp_path, monkeypatch):
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([sample_dir])
    estudo = repo.search_studies()[0]
    serie = repo.series_for_study(estudo.study_uid)[0]
    arquivos = [i["path"] for i in repo.instances_for_series(serie.series_uid)]
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    recebidos = []
    from ipe.ui.dialogs import TagDialog
    dlg = TagDialog(arquivos[0], None, files_for=lambda escopo: arquivos[:1],
                    on_fixed=recebidos.extend)
    assert dlg.tabs.count() == 2
    dlg.campos["ViewPosition"].setText("CC")
    dlg.campos["BodyPartExamined"].setText("BREAST")
    assert set(dlg._mudancas()) == {"ViewPosition", "BodyPartExamined"} - set(
        k for k in ("ViewPosition", "BodyPartExamined") if dlg.antes.get(k) == dlg.campos[k].text())
    dlg._gravar()
    app.processEvents()
    assert recebidos and pydicom.dcmread(recebidos[0]).ViewPosition == "CC"
    dlg.deleteLater()


# ---------------------------------------------------------------- filtros
def test_filtros_nitidez_e_suavizacao():
    rng = np.random.default_rng(3)
    base = np.zeros((80, 80), np.float32)
    base[30:50, 30:50] = 1000.0                       # quadrado com borda nítida
    ruido = base + rng.normal(0, 40, base.shape).astype(np.float32)

    suave = F.apply(ruido, "smooth2")
    assert suave.std() < ruido.std()                  # suavizar tira ruído
    assert abs(float(suave.mean()) - float(ruido.mean())) < 5      # e não muda o brilho médio

    nitido = F.apply(base, "sharp2")
    borda_antes = float(np.abs(np.diff(base[40, 25:55])).max())
    borda_depois = float(np.abs(np.diff(nitido[40, 25:55])).max())
    assert borda_depois > borda_antes                 # nitidez realça a borda
    assert F.apply(base, "").shape == base.shape and np.array_equal(F.apply(base, ""), base)
    assert F.label("sharp1") and F.label("") == "Sem filtro"

    # inteiros não estouram, e a colorida filtra os três canais
    inteiro = (base).astype(np.int16)
    saida = F.apply(inteiro, "sharp3")
    assert saida.dtype == np.int16 and saida.max() <= np.iinfo(np.int16).max
    cor = np.stack([base.astype(np.uint8)] * 3, axis=-1)
    assert F.apply(cor, "smooth1").shape == cor.shape


def test_filtro_no_viewer_no_filme_e_na_exportacao(env, sample_dir, tmp_path):
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([sample_dir])
    settings = Settings(paths.settings_file)
    settings.set("dicom", dict(settings.get("dicom", {}), enabled=False, http_enabled=False))
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, settings)
    w.browser.refresh()
    estudo = repo.search_studies()[0]
    w.open_study(estudo.study_uid)
    app.processEvents()
    tab = w.tabs.currentWidget()
    vp = tab.viewports[0]
    antes = vp._qimage_for_current()
    assert antes is not None
    vp.set_filter("sharp2")
    app.processEvents()
    assert vp.state.filter == "sharp2"
    depois = vp._qimage_for_current()
    assert depois is not None and depois.bits() != antes.bits()
    # o filtro vai junto para o filme
    item = tab._film_item(vp)
    assert item and item["filter"] == "sharp2"
    # e sai na exportação de imagens
    from ipe.exporter.core import ExportItem, export_images
    saida = tmp_path / "img"
    r = export_images(repo, [ExportItem(estudo.study_uid)], saida, fmt="png", every=999,
                      image_filter="sharp2")
    assert r.images >= 1 and list(saida.rglob("*.png"))
    w.net.shutdown()
    w.close()
