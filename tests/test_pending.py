"""Pendências: protocolos de exibição, DICOM SR, SUV, registro automático, listas inteligentes,
reconstrução como série, tarja de texto gravado."""
import json

import numpy as np
import pydicom
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer


def _load(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    return paths, db, repo, {r.accession: r.study_uid for r in repo.search_studies()}


def _window(paths):
    QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    w.browser.refresh()
    return w


def test_hanging_protocol_mammo(env, sample_dir):
    from ipe.ui.viewer.hanging import assign, pattern_match
    assert pattern_match("R CC", {"R", "CC"}, "R CC") and not pattern_match("R CC", {"L", "CC"}, "L CC")
    assert pattern_match("T2|STIR", {"STIR"}, "STIR") and pattern_match("DIN", {"DINAMICO"}, "DINAMICO")
    assert assign(["A", "B"], [("1", {"B"}, "B"), ("2", {"A"}, "A")]) == ["2", "1"]
    paths, db, repo, st = _load(env, sample_dir)
    w = _window(paths)
    assert w.handle_external({"accession": "ACC3001"}) == "aberto"
    tab = w.tabs.currentWidget()
    assert tab._layout == (2, 2) and "Mamografia" in tab.hanging_name
    labels = [tab._series_row(v.frames[0].series_uid).description for v in tab.viewports[:4]]
    assert labels == ["R CC", "L CC", "R MLO", "L MLO"]
    w.close()


def test_sr_export(env, sample_dir, tmp_path):
    from ipe.exporter.sr import build_sr, summarize
    from ipe.imaging.series import build_frames
    paths, db, repo, st = _load(env, sample_dir)
    se = repo.series_for_study(st["ACC1001"])[0]
    f = build_frames(repo.instances_for_series(se.series_uid), se.series_uid)[30]
    repo.save_annotation(db_id=None, study_uid=st["ACC1001"], series_uid=se.series_uid, sop_uid=f.sop_uid,
                         frame_index=0, kind="line", data='{"points": [[100, 100], [200, 100]], "text": "lesão"}')
    repo.save_annotation(db_id=None, study_uid=st["ACC1001"], series_uid=se.series_uid, sop_uid=f.sop_uid,
                         frame_index=0, kind="ellipse", data='{"points": [[120, 120], [180, 160]], "text": ""}')
    ds, n = build_sr(repo, st["ACC1001"])
    lines = summarize(ds)
    assert n >= 6 and any(l.startswith("Length") for l in lines) and any(l.startswith("Area") for l in lines)
    assert any("Comment: lesão" == l for l in lines)
    length = float(next(l for l in lines if l.startswith("Length")).split()[1])
    cs = float(pydicom.dcmread(f.path, stop_before_pixels=True).PixelSpacing[1])
    assert abs(length - 100 * cs) < 0.5
    out = tmp_path / "sr.dcm"
    ds.save_as(out, enforce_file_format=True)
    back = pydicom.dcmread(out)
    assert back.SOPClassUID == "1.2.840.10008.5.1.4.1.1.88.33" and back.StudyInstanceUID == st["ACC1001"]
    ref = back.ContentSequence[0].ContentSequence[0].ContentSequence[0].ReferencedSOPSequence[0]
    assert ref.ReferencedSOPInstanceUID == f.sop_uid
    # guardado no exame: não aparece como série de imagem no visualizador
    Importer(db, paths.storage).import_paths([out])
    assert any(s.modality == "SR" for s in repo.series_for_study(st["ACC1001"]))
    from ipe.ui.viewer.viewer_tab import _image_series
    assert all(s.modality != "SR" for s in _image_series(repo.series_for_study(st["ACC1001"])))


def test_suv():
    from pydicom.dataset import Dataset
    from ipe.imaging import measure as M
    from ipe.imaging.suv import suv_factor
    ds = Dataset()
    ds.Modality, ds.Units, ds.PatientWeight = "PT", "BQML", "70"
    ds.SeriesDate, ds.SeriesTime, ds.DecayCorrection = "20260101", "110000", "START"
    rp = Dataset()
    rp.RadionuclideTotalDose, rp.RadionuclideHalfLife, rp.RadiopharmaceuticalStartTime = "370000000", "6586.2", "100000"
    ds.RadiopharmaceuticalInformationSequence = [rp]
    f, why = suv_factor(ds)
    dose = 370e6 * np.exp(-np.log(2) * 3600 / 6586.2)
    assert why == "SUVbw" and abs(f - 70000 / dose) < 1e-9
    ds.PatientWeight = ""
    assert suv_factor(ds)[0] is None
    ann = M.Annotation("probe", ("x", 0), [(1.0, 1.0)])
    px = np.full((4, 4), 5000.0, np.float32)
    assert M.labels(ann, px, (1, 1), "PT", suv=f)[0].startswith("SUV ")


def test_auto_registration():
    from ipe.imaging.register import register_translation
    from ipe.imaging.volume import Volume
    z, y, x = np.mgrid[0:60, 0:160, 0:160]
    v = np.where(((x - 80) / 60) ** 2 + ((y - 80) / 45) ** 2 < 1, 40, -1000)
    v = v + np.where((x - 105) ** 2 + (y - 80) ** 2 + ((z - 30) * 2.5) ** 2 < 14 ** 2, 600, 0)
    v = v.astype(np.int16)

    def vol(origin):
        return Volume(v, np.array(origin, float), np.array([1., 0, 0]), np.array([0, 1., 0]),
                      np.array([0, 0, 2.5]), 1.5, 1.5, None, "")
    t, score = register_translation(vol([-120, -120, -80]), vol([-120 + 9.0, -120 - 6.0, -80 + 15.0]))
    assert np.allclose(t, [9.0, -6.0, 15.0], atol=2.0) and score > 0.1


def test_smart_list(env, sample_dir):
    paths, db, repo, st = _load(env, sample_dir)
    q = json.dumps({"modality": "MR"})
    lid = repo.create_case_list("Todas as RM", "smart", smart_query=q)
    assert repo.study_uids_in_list(lid) == [st["ACC2001"]]
    assert repo.case_list_info(lid)["count"] == 1 and not repo.add_to_case_list(lid, st["ACC1001"])
    items = repo.list_items(lid)
    assert items[0]["study_uid"] == st["ACC2001"] and items[0]["present"]
    repo.update_case_list(lid, smart_query=json.dumps({"modality": "CT"}))
    assert set(repo.study_uids_in_list(lid)) == {st["ACC1001"], st["ACC0901"]}
    assert all(k != "smart" for _i, _n, k, _c in repo.case_lists())
    w = _window(paths)
    b = w.browser
    b.tree.rebuild(select=lid)
    b._list_selected(lid)
    assert b.model.rowCount() == 2
    w.close()


def test_reconstruction_as_series_goes_to_film(env, sample_dir):
    paths, db, repo, st = _load(env, sample_dir)
    w = _window(paths)
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    tab = w.tabs.currentWidget()
    QApplication.processEvents()
    n0 = len(repo.series_for_study(st["ACC1001"]))
    assert tab.reconstruct_plane("Coronal")
    vp = tab.active
    vp.go_to(100)
    tab.film_add_current()
    comp = w.film_composer()
    cell = comp.film.sheets[0].cells[0]
    series = repo.series_for_study(st["ACC1001"])
    assert len(series) == n0 + 1 and cell is not None
    new = next(s for s in series if s.series_uid == cell.series_uid)
    assert new.num_images == vp.mpr_plane.n and "Coronal" in new.description
    ds = pydicom.dcmread(repo.instances_for_series(new.series_uid)[0]["path"])
    assert "MPR" in list(ds.ImageType) and ds.StudyInstanceUID == st["ACC1001"]
    assert abs(float(ds.ImageOrientationPatient[5]) + 1) < 1e-3 or abs(float(ds.ImageOrientationPatient[5]) - 1) < 1e-3
    # salvar de novo a mesma reconstrução não duplica
    tab.film_add_current()
    assert len(repo.series_for_study(st["ACC1001"])) == n0 + 1
    comp.dirty = False
    w.close()


def test_burned_in_redaction(env, sample_dir):
    from pydicom.dataset import Dataset
    from ipe.exporter.anonymize import AnonOptions, anonymize, burned_in_plan, redact_burned_in
    paths, db, repo, st = _load(env, sample_dir)
    us = repo.files_for_study(st["ACC4001"])
    ds = pydicom.dcmread(us[0])
    assert burned_in_plan(ds, "auto") in ("top", "regions")
    before = ds.pixel_array.copy()
    anonymize(ds, AnonOptions(enabled=True), 1, "s")
    after = ds.pixel_array
    rows = int(ds.Rows)
    band = max(1, int(round(rows * 0.08)))
    assert after.shape == before.shape and not after[..., :band, :, ...].any() if after.ndim == 2 else True
    assert ds.BurnedInAnnotation == "NO"
    # com regiões de US: apaga tudo fora da região
    ds2 = pydicom.dcmread(us[0])
    r = Dataset()
    r.RegionLocationMinX0, r.RegionLocationMinY0, r.RegionLocationMaxX1, r.RegionLocationMaxY1 = 10, 20, 50, 60
    ds2.SequenceOfUltrasoundRegions = [r]
    assert redact_burned_in(ds2, "auto")
    a = ds2.pixel_array
    img = a if a.ndim == 3 and a.shape[-1] == 3 else a[0]
    assert not img[:20].any() and not img[61:].any()
    # CT comum: não mexe
    ct = pydicom.dcmread(repo.files_for_study(st["ACC1001"])[0])
    assert burned_in_plan(ct, "auto") is None
