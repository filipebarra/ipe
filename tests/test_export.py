"""Fase 7: exportação (DICOM + DICOMDIR + visualizador HTML, imagens, anonimização)."""
import zipfile
from pathlib import Path

import pydicom
import pytest
from PySide6.QtWidgets import QApplication

from ipe.exporter.anonymize import AnonOptions
from ipe.exporter.core import ExportError, ExportItem, export_dicom, export_images
from ipe.importer.scanner import Importer


def _setup(env, sample_dir):
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    st = {r.accession: r.study_uid for r in repo.search_studies()}
    return paths, db, repo, st


def test_export_dicom_dicomdir_viewer(env, sample_dir, tmp_path):
    paths, db, repo, st = _setup(env, sample_dir)
    dest = tmp_path / "cd"
    opts = AnonOptions(enabled=True, name="ENSINO^{n}", keep_dates=False)
    calls = []
    r = export_dicom(repo, [ExportItem(st["ACC3001"]), ExportItem(st["ACC2001"])], dest, opts,
                     progress=lambda d, t, _x: calls.append((d, t)))
    n_files = len(repo.files_for_study(st["ACC3001"])) + len(repo.files_for_study(st["ACC2001"]))
    assert r.files == n_files and r.dicomdir and not r.errors and calls[-1][0] == calls[-1][1]
    assert (dest / "DICOMDIR").exists() and (dest / "ABRIR_VISUALIZADOR.html").exists()
    # o DICOMDIR é legível e aponta para os arquivos, todos anonimizados
    fs = pydicom.fileset.FileSet(pydicom.dcmread(dest / "DICOMDIR"))
    assert len(fs) == n_files
    names = set()
    for inst in fs:
        ds = inst.load()
        names.add(str(ds.PatientName))
        assert ds.AccessionNumber == "" and ds.get("PatientBirthDate", "") == "" and ds.StudyDate in ("", "19000101")
        assert "InstitutionName" not in ds and ds.StudyInstanceUID not in (st["ACC3001"], st["ACC2001"])
    assert names == {"ENSINO^1", "ENSINO^2"}
    html = (dest / "ABRIR_VISUALIZADOR.html").read_text(encoding="utf-8")
    assert "Exame 1" in html and "TESTE" not in html.upper() and "DecompressionStream" in html
    assert list((dest / "VISUALIZADOR" / "dados").glob("*.js"))
    # o original não mudou
    orig = pydicom.dcmread(repo.files_for_study(st["ACC3001"])[0])
    assert "ENSINO" not in str(orig.PatientName)
    # pasta não vazia é recusada
    with pytest.raises(ExportError):
        export_dicom(repo, [ExportItem(st["ACC3001"])], dest)


def test_export_zip_and_selection(env, sample_dir, tmp_path):
    paths, db, repo, st = _setup(env, sample_dir)
    se = repo.series_for_study(st["ACC1001"])[0]
    inst = repo.instances_for_series(se.series_uid)
    frames = [(inst[3]["sop_uid"], 0), (inst[7]["sop_uid"], 0)]
    r = export_dicom(repo, [ExportItem(st["ACC1001"], [se.series_uid], frames)], tmp_path / "x.zip",
                     dicomdir=True, viewer=True, zip_output=True)
    assert r.zip_path and r.files == 2
    with zipfile.ZipFile(r.zip_path) as zf:
        n = zf.namelist()
    assert "DICOMDIR" in n and "ABRIR_VISUALIZADOR.html" in n and sum(x.endswith(".js") for x in n) == 1
    # visualizador leve: só prévias JPG
    r3 = export_dicom(repo, [ExportItem(st["ACC1001"], [se.series_uid], frames)], tmp_path / "leve", viewer="light")
    assert len(list((tmp_path / "leve" / "VISUALIZADOR" / "img").rglob("*.jpg"))) == 2
    # sem anonimizar: dados preservados
    out = tmp_path / "plain"
    export_dicom(repo, [ExportItem(st["ACC1001"], [se.series_uid])], out, viewer=False, dicomdir=False)
    f = next((out / "DICOM").iterdir())
    ds = pydicom.dcmread(f)
    assert "TESTE" in str(ds.PatientName).upper() and ds.StudyInstanceUID == st["ACC1001"]


def test_export_images(env, sample_dir, tmp_path):
    from PySide6.QtGui import QImage
    paths, db, repo, st = _setup(env, sample_dir)
    se = repo.series_for_study(st["ACC1001"])[0]
    r = export_images(repo, [ExportItem(st["ACC1001"], [se.series_uid])], tmp_path / "img", "png",
                      window=(400, 40), every=10, anonymous_names=True)
    files = sorted((tmp_path / "img").rglob("*.png"))
    assert r.images == len(files) == 6 and "exame01" in str(files[0])
    im = QImage(str(files[0]))
    assert im.width() > 0
    inst = repo.instances_for_series(se.series_uid)[0]
    r2 = export_images(repo, [ExportItem(st["ACC1001"], None, [(inst["sop_uid"], 0)])], tmp_path / "one", "jpg",
                       max_size=128)
    one = list((tmp_path / "one").glob("*.jpg"))
    assert r2.images == 1 and len(one) == 1 and max(QImage(str(one[0])).width(), QImage(str(one[0])).height()) <= 128


def test_export_dialog_scopes(env, sample_dir, tmp_path, monkeypatch):
    from ipe.core.config import Settings
    from ipe.ui.export_dialog import ExportDialog
    from ipe.ui.main_window import MainWindow
    paths, db, repo, st = _setup(env, sample_dir)
    app = QApplication.instance()
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    tab = w.tabs.currentWidget()
    app.processEvents()
    vp = tab.viewports[0]
    vp.set_window(500, 50)
    seen = {}

    def fake_exec(dlg):
        seen["scopes"] = [label for label, _ in dlg.scopes]
        seen["window"] = dlg.win.currentData()
        dlg.r_img.setChecked(True)
        dlg.dest.setText(str(tmp_path / "img"))
        dlg.scope.setCurrentIndex(0)                       # imagem do quadro ativo
        seen["res"] = dlg.job()
        dlg.r_dicom.setChecked(True)
        dlg.g_anon.setChecked(True)
        dlg.dest.setText(str(tmp_path / "dcm"))
        dlg.scope.setCurrentIndex(1)                       # série do quadro
        seen["res2"] = dlg.job()
        return 0
    monkeypatch.setattr(ExportDialog, "exec", fake_exec)
    tab.export_dialog()
    assert seen["scopes"][0] == "Imagem do quadro ativo" and "Exame inteiro" in seen["scopes"]
    assert seen["window"] == "current" and seen["res"].images == 1
    assert seen["res2"].files == len(repo.instances_for_series(vp.series_uid)) and seen["res2"].dicomdir
    ds = pydicom.dcmread(next(p for p in (tmp_path / "dcm").rglob("*") if p.is_file() and p.parent != tmp_path / "dcm"
                              and p.suffix == "" and p.name != "DICOMDIR" and "VISUALIZADOR" not in str(p)))
    assert str(ds.PatientName).startswith("ANON")
    # banco: exportar os exames selecionados
    w.tabs.setCurrentWidget(w.browser)
    b = w.browser
    b.table.selectRow(0)
    seen.clear()
    monkeypatch.setattr(ExportDialog, "exec", lambda dlg: seen.setdefault("scopes", [l for l, _ in dlg.scopes]) and 0)
    w.export_current()
    assert seen["scopes"][0].startswith("1 exame")
    w.close()


def test_full_viewer_data(env, sample_dir, tmp_path):
    """Os pixels voltam iguais (HU), com geometria de MPR, medidas e imagens-chave."""
    import base64
    import json
    import re
    import zlib
    import numpy as np
    from ipe.imaging.series import build_frames, read_frame
    paths, db, repo, st = _setup(env, sample_dir)
    se = repo.series_for_study(st["ACC1001"])[0]
    fr = build_frames(repo.instances_for_series(se.series_uid), se.series_uid)
    mid = fr[30]
    repo.save_annotation(db_id=None, study_uid=st["ACC1001"], series_uid=se.series_uid, sop_uid=mid.sop_uid,
                         frame_index=0, kind="line", data='{"points": [[10, 20], [110, 20]], "text": ""}')
    repo.toggle_key_image(st["ACC1001"], se.series_uid, mid.sop_uid, 0)
    dest = tmp_path / "v"
    export_dicom(repo, [ExportItem(st["ACC1001"])], dest, dicomdir=False)
    html = (dest / "ABRIR_VISUALIZADOR.html").read_text(encoding="utf-8")
    data = json.loads(re.search(r"const DATA = (.*?);\n", html).group(1).replace("<\\/", "</"))
    meta = data["studies"][0]["series"][0]
    assert meta["n"] == 60 and meta["mpr"] and abs(meta["mpr"]["slice"] - 3.0) < 0.01
    assert meta["annotations"][0]["k"] == 30 and meta["keys"] == [30] and meta["spacing"]
    js = (dest / meta["chunks"][0]["file"]).read_text()
    b = zlib.decompress(base64.b64decode(re.search(r'"([A-Za-z0-9+/=]+)"\);$', js).group(1)))
    n = meta["rows"] * meta["cols"]
    k = 30 - meta["chunks"][0]["k0"]
    hi = np.frombuffer(b[k * 2 * n:k * 2 * n + n], np.uint8).astype(np.int32)
    lo = np.frombuffer(b[k * 2 * n + n:(k + 1) * 2 * n], np.uint8).astype(np.int32)
    raw = ((hi << 8) | lo).astype(np.uint16).view(np.int16).astype(np.float64)
    vals = raw * meta["scale"] + meta["offset"]
    orig = read_frame(mid).pixels.ravel()
    assert np.allclose(vals, orig, atol=meta["scale"] + 1e-6)


def test_new_folder_names(env, sample_dir, tmp_path):
    from ipe.core.config import Settings
    from ipe.ui.export_dialog import ExportDialog, first_name, unique_path
    assert first_name("SILVA^JOAO CARLOS") == "Joao" and first_name("TESTE, Ana Maria") == "Ana"
    assert first_name("FILIPE RAMOS BARRA") == "Filipe" and first_name("") == ""
    paths, db, repo, st = _setup(env, sample_dir)
    (tmp_path / "Ana").mkdir()
    (tmp_path / "Ana" / "x.txt").write_text("x")
    assert unique_path(tmp_path / "Ana").name == "Ana_2"
    dlg = ExportDialog(repo, Settings(paths.settings_file), [("Exame", [ExportItem(st["ACC1001"])])])
    info = repo.study_info(st["ACC1001"])
    assert dlg.c_newdir.isChecked() and dlg.newdir.text() == first_name(info["patient_name"])
    dlg.g_anon.setChecked(True)
    assert dlg.newdir.text() == "ANONIMO"
    dlg.g_anon.setChecked(False)
    dlg.dest.setText(str(tmp_path))
    dlg.c_viewer.setCurrentIndex(dlg.c_viewer.findData(""))
    r = dlg.job()
    assert r.dest.parent == tmp_path and r.dest.name == dlg.newdir.text() + "_2" and (r.dest / "DICOMDIR").exists()
    r2 = dlg.job()                                      # de novo: não sobrescreve
    assert r2.dest.name == dlg.newdir.text() + "_3"
    dlg.c_zip.setChecked(True)
    r3 = dlg.job()
    assert r3.zip_path.parent == tmp_path and r3.zip_path.name == dlg.newdir.text() + ".zip"


def test_visualizador_html_mamografia(env, tmp_path):
    """A exportação leva lado/incidência, caixa da mama, parede torácica e janela do tecido — é o que o
    visualizador do navegador usa para o protocolo, o zoom por quadrante e a janela."""
    import json
    import re
    import numpy as np
    from pydicom.uid import generate_uid
    from ipe.core.sample_data import _base, _mono, _save
    from ipe.exporter.core import ExportItem, export_dicom
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    pat = {"name": "EXPORT^Mama", "id": "EXP1", "birth": "19700101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20260901", "accession": "EXPMG1",
             "description": "MAMOGRAFIA BILATERAL", "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 1, "description": "MAMOGRAFIA 2D"}
    h, w = 400, 320
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    base = np.where(((xx - w) / (w * 0.95)) ** 2 + ((yy - h / 2) / (h * 0.45)) ** 2 < 1, 1500, 80)
    src = tmp_path / "mg"
    for k, (lat, view) in enumerate((("R", "CC"), ("L", "CC"), ("R", "MLO"), ("L", "MLO")), start=1):
        ds = _base("1.2.840.10008.5.1.4.1.1.1.2", pat, study, series, "MG")
        ds.InstanceNumber, ds.ImageLaterality, ds.ViewPosition = k, lat, view
        ds.ImagerPixelSpacing = [0.07, 0.07]
        img = base if lat == "R" else base[:, ::-1].copy()
        _mono(ds, img.astype(np.uint16), signed=False)
        _save(ds, src)
    Importer(db, paths.storage).import_paths([src])
    res = export_dicom(repo, [ExportItem(study_uid=study["uid"])], tmp_path / "saida", viewer=True)
    html = Path(res.viewer).read_text(encoding="utf-8")
    data = json.loads(re.search(r"const DATA = (\{.*?\});\n", html, re.S).group(1))
    mg = data["studies"][0]["series"][0]["mg"]
    assert [(x["side"], x["view"]) for x in mg] == [("R", "CC"), ("L", "CC"), ("R", "MLO"), ("L", "MLO")]
    assert [x["chest"] for x in mg] == ["right", "left", "right", "left"]
    for x in mg:
        x0, y0, x1, y1 = x["bbox"]
        assert 0 <= x0 < x1 <= data["studies"][0]["series"][0]["cols"]
        assert 0 <= y0 < y1 <= data["studies"][0]["series"][0]["rows"]
        assert x["tissue"][0] > 0
    # a página traz os botões da mamografia
    for botao in ('id="mg"', 'id="mgq"', 'id="mgw"', "function mgLayout", "quadZoom"):
        assert botao in html


def test_visualizador_html_traduzido(env, tmp_path):
    """A página exportada sai no idioma em uso (mesmo catálogo do programa)."""
    from ipe.core import i18n
    from ipe.exporter.full_viewer_page import page
    dados = {"title": "Exames", "full": True, "studies": []}
    try:
        i18n.load("en")
        html = page(dados)
        assert ">Mammography<" in html and ">Quadrant<" in html and ">Ruler<" in html
        assert "Not intended for diagnostic use." in html
        assert ">Mamografia<" not in html
        i18n.load("es")
        assert ">Mamografía<" in html.replace("Mammography", "") or ">Regla<" in page(dados)
    finally:
        i18n.load(i18n.BASE_LANG)
    assert ">Mamografia<" in page(dados)          # em português, nada muda
