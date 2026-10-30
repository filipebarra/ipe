"""Acompanhamento de lesões, CAD/IA (SR, SEG, RTSTRUCT, GSPS), laudo, segmentação 3D e extras de mama."""
import json
import tempfile
from pathlib import Path

import numpy as np
import pydicom
import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from PySide6.QtWidgets import QApplication, QMessageBox

from ipe.core.config import Settings
from ipe.imaging import lesions as L
from ipe.imaging import mammo as MG
from ipe.imaging import overlays as O
from ipe.imaging import segment as SG
from ipe.importer.scanner import Importer


# ---------------------------------------------------------------------------- lesões (sem Qt)
def _ann(lid, study, mm=None, **extra):
    meta = {"lesion": lid}
    if mm is not None:
        meta["mm"] = mm
    meta.update(extra)
    return {"id": 1, "study_uid": study, "series_uid": "se", "sop_uid": "so", "frame_index": 0, "kind": "line",
            "data": json.dumps({"points": [], "meta": meta})}


def test_recist_and_percist():
    lesions = [{"id": 1, "name": "Fígado", "kind": "target", "nodal": False, "data": {"status": {"s4": "absent"}}},
               {"id": 2, "name": "LN", "kind": "target", "nodal": True, "data": {}},
               {"id": 3, "name": "NT", "kind": "nontarget", "data": {"status": {"s4": "absent"}}}]
    anns = [_ann(1, "s1", 30), _ann(2, "s1", 20), _ann(2, "s1", 15),     # linfonodo: 2 medidas -> menor eixo
            _ann(1, "s2", 18), _ann(2, "s2", 12),
            _ann(1, "s3", 40), _ann(2, "s3", 14),
            _ann(2, "s4", 8)]
    studies = [("s3", "20250701"), ("s1", "20250101"), ("s2", "20250401"), ("s4", "20251001")]
    cells = L.collect_cells(lesions, anns, "recist")
    assert cells[(2, "s1")].value == 15 and cells[(1, "s4")].value == 0
    ev = L.evaluate("recist", lesions, studies, cells)
    assert [e.study_uid for e in ev] == ["s1", "s2", "s3", "s4"]
    assert [e.response for e in ev] == ["BASE", "RP", "DP", "RC"]
    assert ev[0].total == 45 and ev[1].pct_base == pytest.approx(-33.3, abs=0.1)
    assert ev[2].pct_nadir == pytest.approx(80)
    txt = L.summary_text("recist", lesions, studies, cells, ev, "s2")
    assert "RECIST 1.1" in txt and "Resposta parcial" in txt and "Fígado" in txt
    # lesão nova -> progressão
    lesions.append({"id": 4, "name": "Nova", "kind": "new", "data": {"status": {"s2": "present"}}})
    ev = L.evaluate("recist", lesions, studies, L.collect_cells(lesions, anns, "recist"))
    assert ev[1].response == "DP"
    # PERCIST: SUVpeak da lesão mais ávida
    les = [{"id": 1, "name": "A", "kind": "target", "data": {}}, {"id": 2, "name": "B", "kind": "target", "data": {}}]
    anns = [_ann(1, "p1", suvpeak=10.0), _ann(2, "p1", suvpeak=4.0), _ann(1, "p2", suvpeak=6.0),
            _ann(2, "p2", suvpeak=3.0), _ann(1, "p3", suvpeak=14.0), _ann(2, "p3", suvpeak=3.0)]
    st = [("p1", "20250101"), ("p2", "20250301"), ("p3", "20250601")]
    ev = L.evaluate("percist", les, st, L.collect_cells(les, anns, "percist"))
    assert [e.response for e in ev] == ["BASE", "RMP", "DMP"] and ev[0].total == 10
    # valores das medidas: régua e ROI com SUV
    px = np.zeros((40, 40), np.float32)
    px[10:20, 10:20] = 1000
    v = L.measure_values("ellipse", [(8, 8), (22, 22)], px, (1.0, 1.0), 0.01)
    assert v["mm"] == 14 and v["suvmax"] == pytest.approx(10) and 0 < v["suvpeak"] <= 10
    assert L.measure_values("line", [(0, 0), (3, 4)], None, (2, 2))["mm"] == 10


def test_repository_lesions_reports(env):
    _paths, _db, repo = env
    lid = repo.save_lesion({"patient_id": "P1", "name": "L1", "location": "Fígado", "kind": "target"})
    repo.save_lesion({"id": lid, "data": {"status": {"x": "absent"}}})
    les = repo.lesions("P1")
    assert les[0]["name"] == "L1" and les[0]["data"]["status"]["x"] == "absent"
    repo.save_lesion_track("P1", criterion="percist")
    assert repo.lesion_track("P1")["criterion"] == "percist"
    repo.delete_lesion(lid)
    assert repo.lesions("P1") == []
    rid = repo.save_report({"study_uid": "S1", "title": "TC", "text": "abc", "fields": {"kind": "mg"}})
    assert repo.report(rid)["status"] == "draft"
    r = repo.sign_report(rid, "Dr. X")
    assert r["status"] == "final" and r["signed_by"] == "Dr. X"
    with pytest.raises(ValueError):
        repo.save_report({"id": rid, "study_uid": "S1", "text": "mudou"})
    assert repo.report_counts(["S1"]) == {"S1": "final"}
    tpl = repo.report_templates()
    assert len(tpl) >= 12 and {"CT", "MG", "MR", "PT"} <= {m for t in tpl for m in t["modalities"]}
    repo.save_report_templates(tpl[:2])
    assert len(repo.report_templates()) == 2
    from ipe.central.rpc import RPC_METHODS
    assert RPC_METHODS["sign_report"] == "sign_report" and RPC_METHODS["lesions"] == "view"


# ---------------------------------------------------------------------------- laudo (sem janela)
def test_report_fill_birads_and_dicom(tmp_path):
    from ipe.reporting import birads as B
    from ipe.reporting import dicom_out as D
    from ipe.reporting.fill import fill
    from ipe.reporting.templates import best_template, default_templates
    t = default_templates()
    assert best_template(t, "MG", "MAMOGRAFIA BILATERAL")["birads"] == "mg"
    assert best_template(t, "CT", "TC TÓRAX")["id"] == "tc_torax"
    assert best_template(t, "PT\\CT", "PET-CT FDG")["id"] == "pet_fdg"
    assert best_template(t, "MR", "RM MAMAS")["id"] == "rm_mamas"
    assert fill("A\n{medidas}\nB {x}\n", {"medidas": ""}) == "A\nB {x}\n"
    f = {"kind": "mg", "composition": "c", "cat_right": "2", "cat_left": "4B",
         "findings": [{"side": "E", "type": "Nódulo", "desc": "forma irregular", "size": "12", "location":
                       "quadrante superolateral", "category": "4B"}]}
    assert B.final_category(f) == "4B"
    assert "heterogeneamente densas" in B.composition_text(f)
    assert "Mama esquerda: nódulo, forma irregular, medindo 12 mm" in B.findings_text(f)
    txt = B.category_text(f)
    assert "Categoria final: BI-RADS® 4B" in txt and "histopatológico" in txt
    assert B.worst(["2", "0", "3"]) == "0" and B.worst(["0", "4A"]) == "4A"
    # DICOM
    src = tmp_path / "src.dcm"
    ds = Dataset()
    ds.PatientName, ds.PatientID, ds.StudyInstanceUID = "X^Y", "1", generate_uid()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.save_as(src, enforce_file_format=True)
    pdf = D.encapsulated_pdf(b"%PDF-1.4 teste", str(src), "Laudo TC")
    pdf.save_as(tmp_path / "p.dcm", enforce_file_format=True)
    back = pydicom.dcmread(tmp_path / "p.dcm")
    assert back.Modality == "DOC" and bytes(back.EncapsulatedDocument).startswith(b"%PDF")
    sr = D.text_sr("TÉCNICA\nachados aqui\n\nIMPRESSÃO:\nnormal", str(src), "Laudo", "Dr A", True, "Dr A", "2")
    sr.save_as(tmp_path / "s.dcm", enforce_file_format=True)
    back = pydicom.dcmread(tmp_path / "s.dcm")
    names = [i.ConceptNameCodeSequence[0].CodeMeaning for i in back.ContentSequence]
    assert "Finding" in names and "Impression" in names and back.VerificationFlag == "VERIFIED"
    assert back.StudyInstanceUID == ds.StudyInstanceUID


# ---------------------------------------------------------------------------- segmentação 3D
def _sphere_volume(r=10, n=40, val=100.0):
    from ipe.imaging.volume import Volume
    z, y, x = np.mgrid[0:n, 0:n, 0:n]
    data = np.zeros((n, n, n), np.float32)
    data[(z - n / 2) ** 2 + (y - n / 2) ** 2 + (x - n / 2) ** 2 <= r * r] = val
    return Volume(data=data, origin=np.zeros(3), row_dir=np.array([1.0, 0, 0]), col_dir=np.array([0, 1.0, 0]),
                  slice_vec=np.array([0, 0, 1.0]), dx=1.0, dy=1.0, window=None, source_path="")


def test_segmentation_volume_and_pet():
    vol = _sphere_volume()
    res = SG.segment(vol, (20, 20, 20), "range")
    assert res.ml == pytest.approx(4 / 3 * np.pi * 1000 / 1000, rel=0.05)
    assert res.max_diam_mm == pytest.approx(21, abs=1.5)
    res = SG.segment(vol, (20, 20, 20), "pet_pct", suv=0.05, modality="PT")
    assert res.lo == pytest.approx(41) and res.suvmax == pytest.approx(5) and res.suvpeak == pytest.approx(5)
    assert res.tlg == pytest.approx(res.suvmean * res.ml)
    res2 = SG.segment(vol, (20, 20, 20), "pet_abs", suv=0.05, abs_suv=2.5)
    assert res2.voxels == res.voxels
    assert SG.tmtv([res.meta(), {"ml": 3.0}]) == (pytest.approx(res.ml, abs=0.01), pytest.approx(res.tlg, abs=0.01))
    # semente fora da faixa
    assert SG.segment(vol, (0, 0, 0), "range", 50, 150).voxels == 0
    frames = SG.mask_frames(vol, res, (255, 0, 0), "x")
    assert len(frames) == 21 and frames[0].position[2] == res.offset[0]


def test_seg_writer_roundtrip(tmp_path):
    from ipe.imaging.seg_writer import build_seg
    vol = _sphere_volume()
    src = tmp_path / "ct.dcm"
    ds = Dataset()
    ds.PatientName, ds.PatientID, ds.StudyInstanceUID = "X", "1", generate_uid()
    ds.SeriesInstanceUID, ds.FrameOfReferenceUID = generate_uid(), generate_uid()
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.save_as(src, enforce_file_format=True)
    res = SG.segment(vol, (20, 20, 20), "range")
    seg = build_seg(vol, [(res, "Nódulo", (255, 80, 80))], str(src))
    seg.save_as(tmp_path / "seg.dcm", enforce_file_format=True)
    obj = O.load_object(str(tmp_path / "seg.dcm"))
    assert obj is not None and obj.source == "SEG" and obj.findings == ["Nódulo"]
    assert len(obj.masks) == 21 and sum(int(m.mask.sum()) for m in obj.masks) == res.voxels
    assert obj.masks[0].color[0] > 200
    # posição de uma máscara num plano axial igual
    mf = obj.masks[10]
    r = O.mask_rect(mf, np.array([0, 0, mf.position[2]]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
                    np.array([0, 0, 1.0]), (1.0, 1.0), 0.5, "", 0)
    # 0.98: a máscara vem recortada na caixa do segmento — o retângulo é a caixa, no lugar certo
    k = round(mf.position[2]) - res.offset[0]
    corte = res.mask[k]
    rs, cs = np.flatnonzero(corte.any(axis=1)), np.flatnonzero(corte.any(axis=0))
    assert r == (float(res.offset[2] + cs[0]), float(res.offset[1] + rs[0]), float(len(cs)), float(len(rs)))
    assert mf.mask.shape == (len(rs), len(cs))


# ---------------------------------------------------------------------------- objetos de CAD / anotações
def _cad_sr(img_sop: str, study: str) -> Dataset:
    def code(v, s, m):
        c = Dataset()
        c.CodeValue, c.CodingSchemeDesignator, c.CodeMeaning = v, s, m
        return c
    img = Dataset()
    img.RelationshipType, img.ValueType = "SELECTED FROM", "IMAGE"
    ref = Dataset()
    ref.ReferencedSOPClassUID, ref.ReferencedSOPInstanceUID = "1.2.840.10008.5.1.4.1.1.1.2", img_sop
    img.ReferencedSOPSequence = Sequence([ref])
    sc = Dataset()
    sc.RelationshipType, sc.ValueType = "HAS PROPERTIES", "SCOORD"
    sc.ConceptNameCodeSequence = Sequence([code("111010", "DCM", "Center")])
    sc.GraphicType, sc.GraphicData = "CIRCLE", [100.0, 120.0, 110.0, 120.0]
    sc.ContentSequence = Sequence([img])
    typ = Dataset()
    typ.RelationshipType, typ.ValueType = "CONTAINS", "CODE"
    typ.ConceptNameCodeSequence = Sequence([code("111059", "DCM", "Single Image Finding Type")])
    typ.ConceptCodeSequence = Sequence([code("F-01796", "SRT", "Mammography breast density")])
    typ.ConceptCodeSequence = Sequence([code("M-8000", "SRT", "Mass")])
    num = Dataset()
    num.RelationshipType, num.ValueType = "CONTAINS", "NUM"
    num.ConceptNameCodeSequence = Sequence([code("111047", "DCM", "Certainty of Finding")])
    mv = Dataset()
    mv.NumericValue = "87"
    mv.MeasurementUnitsCodeSequence = Sequence([code("%", "UCUM", "percent")])
    num.MeasuredValueSequence = Sequence([mv])
    find = Dataset()
    find.RelationshipType, find.ValueType = "CONTAINS", "CONTAINER"
    find.ConceptNameCodeSequence = Sequence([code("111059", "DCM", "Single Image Finding")])
    find.ContentSequence = Sequence([typ, num, sc])
    ds = Dataset()
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.88.50"
    ds.SOPInstanceUID = generate_uid()
    ds.StudyInstanceUID = study
    ds.Modality = "SR"
    ds.ValueType = "CONTAINER"
    ds.ConceptNameCodeSequence = Sequence([code("111036", "DCM", "Mammography CAD Report")])
    ds.ContentSequence = Sequence([find])
    return ds


def test_parse_cad_sr_gsps_rtstruct():
    obj = O.parse_sr(_cad_sr("1.2.3", "9.9"))
    assert obj.source == "CAD" and obj.label == "Mammography CAD Report"
    g = obj.by_frame[("1.2.3", -1)][0]
    assert g.kind == "polygon" and "Mass" in g.text and "87" in g.text
    assert any("Mass" in f for f in obj.findings)
    xs = [p[0] for p in g.points]
    assert min(xs) == pytest.approx(90, abs=0.5) and max(xs) == pytest.approx(110, abs=0.5)
    # GSPS
    ds = Dataset()
    ds.SOPClassUID, ds.SOPInstanceUID, ds.Modality = "1.2.840.10008.5.1.4.1.1.11.1", generate_uid(), "PR"
    ga = Dataset()
    ri = Dataset()
    ri.ReferencedSOPInstanceUID = "1.2.3"
    ga.ReferencedImageSequence = Sequence([ri])
    go = Dataset()
    go.GraphicAnnotationUnits, go.GraphicType, go.GraphicData = "PIXEL", "POLYLINE", [1.0, 1.0, 5.0, 5.0]
    to = Dataset()
    to.UnformattedTextValue, to.AnchorPoint, to.AnchorPointAnnotationUnits = "Achado", [3.0, 3.0], "PIXEL"
    ga.GraphicObjectSequence = Sequence([go])
    ga.TextObjectSequence = Sequence([to])
    ds.GraphicAnnotationSequence = Sequence([ga])
    obj = O.parse_gsps(ds)
    kinds = sorted(g.kind for g in obj.graphics_for("1.2.3", 0))
    assert kinds == ["polyline", "text"] and obj.findings == ["Achado"]
    # RTSTRUCT
    ds = Dataset()
    ds.SOPClassUID, ds.SOPInstanceUID, ds.Modality = O.RTSTRUCT_CLASS, generate_uid(), "RTSTRUCT"
    r = Dataset()
    r.ROINumber, r.ROIName = 1, "GTV"
    ds.StructureSetROISequence = Sequence([r])
    rc = Dataset()
    rc.ReferencedROINumber, rc.ROIDisplayColor = 1, [255, 0, 0]
    c = Dataset()
    c.ContourGeometricType = "CLOSED_PLANAR"
    c.ContourData = [0, 0, 5, 10, 0, 5, 10, 10, 5]
    rc.ContourSequence = Sequence([c])
    ds.ROIContourSequence = Sequence([rc])
    obj = O.parse_rtstruct(ds)
    assert obj.findings == ["GTV"] and obj.planar[0].color == (255, 0, 0)
    pts = O.project(obj.planar[0].points3d, np.array([0, 0, 5.0]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
                    np.array([0, 0, 1.0]), (2.0, 2.0), 1.0)
    assert pts[1] == (5.5, 0.5)
    assert O.project(obj.planar[0].points3d, np.array([0, 0, 9.0]), np.array([1.0, 0, 0]),
                     np.array([0, 1.0, 0]), np.array([0, 0, 1.0]), (2.0, 2.0), 1.0) is None
    assert O.lab_to_rgb([65535, 32896, 32896])[0] > 250


# ---------------------------------------------------------------------------- mama
def test_mammo_cem_implant_bbox():
    c = MG.parse_code("CCD rec")
    assert c.rec and not c.tomo and c.code == "CCD rec" and MG.parse_code(c.code) == c
    assert MG.parse_code("MLOE tomo ant").with_rec(True).code == "MLOE tomo rec ant"
    st = MG.parse_step("CCD, CCD rec x CCE, CCE rec")
    assert st["cells"] == ["CCD", "CCE", "CCD rec", "CCE rec"]
    ds = Dataset()
    ds.ImageType = ["ORIGINAL", "PRIMARY", "", "RECOMBINED"]
    assert MG.energy_of(ds, []) == "rec"
    ds.ImageType = ["ORIGINAL", "PRIMARY", "", "LOW_ENERGY"]
    assert MG.energy_of(ds, []) == "low"
    assert MG.energy_of(Dataset(), ["CESM SUB"]) == "rec"
    assert MG.find_mg_protocol(None, "MAMOGRAFIA CONTRASTADA")["name"].startswith("Mamografia com contraste")
    assert MG.find_mg_protocol(None, "MAMOGRAFIA BILATERAL")["name"].startswith("Mamografia (4")
    ims = [MG.MgImage("s", "se", "a", 0, "", "R", "CC", energy="low"), MG.MgImage("s", "se", "b", 0, "", "R", "CC",
                                                                                   energy="rec")]
    assert MG.pick_image(ims, MG.parse_code("CCD")).sop_uid == "a"
    assert MG.pick_image(ims, MG.parse_code("CCD rec")).sop_uid == "b"
    # mama com implante: janela calculada fora do implante
    h, w = 300, 240
    yy, xx = np.mgrid[0:h, 0:w]
    img = np.full((h, w), 100.0)
    breast = ((xx - w) / (w * 0.9)) ** 2 + ((yy - h / 2) / (h * 0.42)) ** 2 < 1
    img[breast] = 1500 + 200 * np.sin(yy[breast] / 9)
    implant = ((xx - w * 0.85) / 50) ** 2 + ((yy - h / 2) / 60) ** 2 < 1
    img[implant] = 4000
    box = MG.breast_bbox(img)
    assert box is not None and box[0] > 10 and box[2] == w
    res = MG.implant_window(img)
    assert res is not None
    (ww, lev), m = res
    assert m[int(h / 2), int(w * 0.85)] and not m[int(h / 2), int(w * 0.55)]
    assert lev + ww / 2 < 2000                       # a janela não se estica até o implante
    # sem prótese (só o tecido com textura), não inventa implante — o que separa é a falta de textura,
    # não a densidade: uma área grande, clara e lisa É um implante, mesmo sem ser a mais densa
    img2 = np.full((h, w), 100.0)
    img2[breast] = 1500 + 200 * np.sin(yy[breast] / 9) + 150 * np.cos(xx[breast] / 7)
    assert MG.implant_window(img2) is None


# ---------------------------------------------------------------------------- interface
@pytest.fixture()
def win(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1400, 850)
    w.show()
    yield app, w, repo, paths
    for t in w.all_viewer_tabs():
        for rw in getattr(t, "_report_windows", {}).values():
            rw._dirty = False
            rw.close()
    w.close()


def _open(w, acc):
    w.handle_external({"accession": acc})
    tab = w.all_viewer_tabs()[-1]
    tab.set_layout(1, 1)
    QApplication.processEvents()
    return tab, tab.viewports[0]


def test_gui_lesions_segmentation_overlays(win, monkeypatch):
    app, w, repo, paths = win
    from ipe.imaging.measure import Annotation
    tab, vp = _open(w, "ACC1001")
    assert {"lesion.panel", "report.open", "overlay.toggle", "tool.grow"} <= set(tab.actions_by_id)
    # nódulo sintético: centro (179, 115) no corte do meio
    vp.go_to(30)
    ann = Annotation("line", vp.frame_key(), [(170.0, 115.0), (188.0, 115.0)], study_uid=vp.study_uid,
                     series_uid=vp.series_uid)
    vp.annotations.append(ann)
    vp._store("save", ann)
    lid = repo.save_lesion({"patient_id": "FANT001", "name": "Nódulo LSD", "location": "Pulmão direito"})
    vp.link_lesion(ann, lid, "Nódulo LSD")
    assert ann.meta["mm"] == pytest.approx(27)
    tab.lesions_action.setChecked(True)
    panel = tab.lesion_panel
    assert panel.isVisible() and panel.lesions[0]["name"] == "Nódulo LSD"
    assert panel.cells[(lid, vp.study_uid)].value == pytest.approx(27)
    assert "Nódulo LSD" in panel.text_for(vp.study_uid) and vp.lesion_names[lid] == "Nódulo LSD"
    vp.grab()
    # segmentação 3D por clique no nódulo
    tab.segment_at(vp, 179.5, 115.5)
    dlg = tab._seg_dialogs[-1]
    # desde a 0.68 a máscara é em mm (aparece em qualquer plano), não por imagem
    assert 7 < dlg.res.ml < 13 and dlg.obj in tab.overlay_objects and dlg.obj.volumes
    vp.grab()
    dlg.save()
    segs = [r for r in repo.annotations_for_studies([vp.study_uid]) if r["kind"] == "seg"]
    assert len(segs) == 1 and json.loads(segs[0]["data"])["meta"]["ml"] == pytest.approx(dlg.res.ml, abs=0.01)
    n_series = len(repo.series_for_study(vp.study_uid))
    dlg.save_dicom()
    assert len(repo.series_for_study(vp.study_uid)) == n_series + 1
    dlg.close()
    tab._reload_overlays()
    seg_objs = [o for o in tab.overlay_objects if o.source == "SEG"]
    assert seg_objs and seg_objs[0].masks
    assert tab.overlay_action.iconText().startswith("CAD/IA (")
    tab.toggle_overlays()
    assert not any(o.enabled for o in tab.overlay_objects)
    tab.toggle_overlays()
    vp.go_to(30)
    vp.grab()
    # layout das lesões
    tab.lesion_layout()
    assert tab.viewports[0].frames[tab.viewports[0].index].sop_uid == ann.frame_key[0]


def test_gui_report_window(win, monkeypatch):
    app, w, repo, paths = win
    tab, vp = _open(w, "ACC1001")
    ann = __import__("ipe.imaging.measure", fromlist=["Annotation"]).Annotation(
        "line", vp.frame_key(), [(10.0, 10.0), (30.0, 10.0)], study_uid=vp.study_uid, series_uid=vp.series_uid)
    vp.annotations.append(ann)
    vp._store("save", ann)
    tab.open_report()
    rw = tab._report_windows[vp.study_uid]
    assert rw.template.currentData() == "tc_torax"
    text = rw.editor.toPlainText()
    assert "TOMOGRAFIA COMPUTADORIZADA DO TÓRAX" in text and "Exames anteriores:" in text
    assert "Régua: 30.0 mm" in text                      # {medidas} com o espaçamento do arquivo (1,5 mm)
    assert "{" not in text
    rw.editor.appendPlainText("Nota final.")
    assert rw.save_draft()
    assert repo.reports(vp.study_uid)[0]["status"] == "draft"
    data = rw.pdf_bytes()
    assert data.startswith(b"%PDF")
    n_series = len(repo.series_for_study(vp.study_uid))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    rw.sign()
    reps = repo.reports(vp.study_uid)
    assert reps[-1]["status"] == "final" and rw.editor.isReadOnly()
    mods = sorted(s.modality for s in repo.series_for_study(vp.study_uid))
    assert len(mods) == n_series + 2 and "DOC" in mods and "SR" in mods
    # retificação cria um laudo novo
    rw.amend()
    assert not rw.editor.isReadOnly() and rw.report.get("id") is None
    rw.editor.appendPlainText("Correção.")
    rw.sign()
    reps = repo.reports(vp.study_uid)
    assert [r["status"] for r in reps] == ["final", "amended"]
    # BI-RADS e modelos
    rw.birads.set_fields({"kind": "mg", "composition": "b", "cat_right": "1", "cat_left": "3"})
    assert rw.context()["birads"].startswith("Mama direita: BI-RADS® 1")
    from ipe.ui.report_window import TemplatesDialog
    dlg = TemplatesDialog(repo, rw)
    n = dlg.list.count()
    dlg._new()
    dlg.name.setText("Meu modelo")
    dlg._save()
    assert len(repo.report_templates()) == n + 1


def test_gui_tomo_slab_and_implant(win):
    app, w, repo, paths = win
    tab, vp = _open(w, "ACC4001")
    cine = next(s for s in tab.series if s.description == "Cine multiframe")
    tab.load_series_into(vp, cine.series_uid)
    assert len(vp.frames) == 10
    vp.go_to(5)
    vp.mg_tomo = True
    vp.set_tomo_slab(5)
    manual = np.max([tab.cache.get(vp.frames[i]).pixels for i in range(3, 8)], axis=0)
    assert np.array_equal(vp._img.pixels, manual)
    vp.set_tomo_slab(5, "avg")
    assert vp._img.pixels.mean() == pytest.approx(np.mean([tab.cache.get(vp.frames[i]).pixels
                                                           for i in range(3, 8)]), rel=1e-4)
    vp.set_tomo_slab(1)
    assert np.array_equal(vp._img.pixels, tab.cache.get(vp.frames[5]).pixels)
    # mamografia: botões da barra e máscara de implante (sem implante nas imagens de exemplo)
    tab2, vp2 = _open(w, "ACC3001")
    assert tab2.mg_session is not None
    tab2.mg_set_implant(True)
    assert all(v.implant_mask for v in tab2._shown() if v.frames)
    tab2.mg_set_implant(False)
    tab2.actions_by_id["mg.slab"].trigger()
    assert tab2.mg_slab == 5
    tab2.mg_toggle_cem()          # sem imagens de CEM: só avisa


def test_gui_report_birads_updates_text_and_reopens(win, monkeypatch):
    app, w, repo, paths = win
    tab, vp = _open(w, "ACC3001")
    tab.open_report()
    rw = tab._report_windows[vp.study_uid]
    assert rw.template.currentData() == "mg_rastreamento" and rw.birads.kind.currentData() == "mg"
    txt = rw.editor.toPlainText()
    assert "Composição mamária: ___" in txt and "BI-RADS®: ___" in txt
    # o formulário muda o texto sozinho
    rw.birads.comp.setCurrentIndex(rw.birads.comp.findData("c"))
    rw.birads.findings.append({"side": "E", "type": "Nódulo", "desc": "forma oval", "size": "8",
                               "location": "quadrante superolateral", "category": "3"})
    rw.birads._render_list()
    rw.birads._emit()
    rw.birads.cat_l.setCurrentIndex(rw.birads.cat_l.findData("3"))
    rw.birads.cat_r.setCurrentIndex(rw.birads.cat_r.findData("1"))
    txt = rw.editor.toPlainText()
    assert "heterogeneamente densas" in txt and "Mama esquerda: nódulo, forma oval, medindo 8 mm" in txt
    assert "Categoria final: BI-RADS® 3" in txt and "6 meses" in txt and "___" not in txt
    assert "Não há nódulos" not in txt
    # texto editado à mão num bloco: o botão insere no cursor
    rw.editor.setPlainText(rw.editor.toPlainText().replace("Categoria final", "Cat. final"))
    rw.birads.cat_l.setCurrentIndex(rw.birads.cat_l.findData("4A"))
    assert "Levar ao texto" in rw.status.text()
    rw.editor.moveCursor(rw.editor.textCursor().MoveOperation.End)
    rw.birads.b_apply.click()
    assert "Categoria final: BI-RADS® 4A" in rw.editor.toPlainText()
    assert rw.save_draft(notify=True)
    rw.close()
    QApplication.processEvents()
    # coluna Laudo no banco e reabrir pelo banco (sem aba) e pelo visualizador
    w.browser.refresh()
    row = next(r for r in repo.search_studies() if r.study_uid == vp.study_uid)
    assert row.report == "rascunho"
    tab.open_report()
    rw2 = tab._report_windows[vp.study_uid]
    assert rw2 is not rw and "Mama esquerda: nódulo" in rw2.editor.toPlainText()
    assert rw2.birads.findings and rw2.versions.count() == 1
    # mudar o formulário do rascunho reaberto continua trocando o texto
    rw2.birads.comp.setCurrentIndex(rw2.birads.comp.findData("b"))
    assert "áreas esparsas" in rw2.editor.toPlainText()
    rw2._dirty = False
    rw2.close()
    w.close_tab = getattr(w, "close_tab", None)
    for t in w.all_viewer_tabs():
        w.tabs.removeTab(w.tabs.indexOf(t))
    w.open_report(vp.study_uid)
    rw3 = w._report_windows[vp.study_uid]
    assert "Mama esquerda: nódulo" in rw3.editor.toPlainText()
    rw3._dirty = False
    rw3.close()
    assert "report" in w.home_bar.buttons


def test_comment_column_updates(win, monkeypatch):
    app, w, repo, paths = win
    b = w.browser
    b.refresh()
    b.table.selectRow(0)
    row = b.selected_rows()[0]
    from ipe.ui import browser as BR
    texts = iter(["primeiro", "segundo comentário"])

    class FakeDlg:
        def __init__(self, *a, **k):
            self.v = next(texts)

        def exec(self):
            return True

        def value(self):
            return self.v
    monkeypatch.setattr(BR, "TextInputDialog", FakeDlg)
    b._add_comment()
    assert row.comment == "primeiro"
    b._add_comment()
    assert row.comment == "segundo comentário  (+1)"
    b.refresh()
    again = next(r for r in repo.search_studies() if r.study_uid == row.study_uid)
    assert again.comment == "segundo comentário  (+1)" and again.has_comment


def test_report_key_images_show_annotations(win):
    app, w, repo, paths = win
    from ipe.imaging.measure import Annotation
    tab, vp = _open(w, "ACC1001")
    vp.go_to(30)
    tab.toggle_key_image()
    arrow = Annotation("arrow", vp.frame_key(), [(40.0, 40.0), (120.0, 120.0)], text="achado",
                       study_uid=vp.study_uid, series_uid=vp.series_uid)
    vp.annotations.append(arrow)
    vp._store("save", arrow)
    tab.open_report()
    rw = tab._report_windows[vp.study_uid]
    imgs = rw.key_images()
    assert len(imgs) == 1
    q = imgs[0]
    import numpy as np
    buf = np.frombuffer(q.constBits(), np.uint8, count=q.sizeInBytes()).reshape(q.height(), q.bytesPerLine())
    bgra = buf[:, : q.width() * 4].reshape(q.height(), q.width(), 4)
    yellow = (bgra[..., 2] > 230) & (bgra[..., 1] > 190) & (bgra[..., 0] < 120)
    assert yellow.sum() > 50                      # a seta (amarela) está desenhada na imagem do laudo
    assert rw.pdf_bytes().startswith(b"%PDF")
    rw._dirty = False


def test_tomo_voi_window_and_sigmoid():
    from ipe.imaging.series import voi_window
    from ipe.imaging.windowing import apply_window, tissue_window
    ds = Dataset()
    sh = Dataset()
    fv = Dataset()
    fv.WindowCenter, fv.WindowWidth, fv.VOILUTFunction = 2000, 1000, "SIGMOID"
    sh.FrameVOILUTSequence = Sequence([fv])
    ds.SharedFunctionalGroupsSequence = Sequence([sh])
    pf = []
    for k in range(3):
        g = Dataset()
        if k == 2:
            v = Dataset()
            v.WindowCenter, v.WindowWidth = 2500, 800
            g.FrameVOILUTSequence = Sequence([v])
        pf.append(g)
    ds.PerFrameFunctionalGroupsSequence = Sequence(pf)
    assert voi_window(ds, 0) == ((1000.0, 2000.0), "SIGMOID")
    assert voi_window(ds, 2)[0] == (800.0, 2500.0)
    lut = Dataset()
    item = Dataset()
    item.LUTDescriptor = [4096, 0, 12]
    lut.VOILUTSequence = Sequence([item])
    assert voi_window(lut) == ((4096.0, 2048.0), "")
    assert voi_window(Dataset()) == (None, "")
    px = np.array([[1000.0, 2000.0, 3000.0]], np.float32)
    sig = apply_window(px, 1000, 2000, function="SIGMOID")
    assert sig[0, 1] in (127, 128) and 0 < sig[0, 0] < 10 and sig[0, 2] > 245
    # janela no tecido: não se estica até o fundo nem até o letreiro
    img = np.full((200, 160), 50.0)
    img[20:180, 40:] = 1000 + np.random.default_rng(1).normal(0, 60, (160, 120))
    img[5:10, 5:15] = 4095
    w, l = tissue_window(img)
    assert 700 < l - w / 2 < 1000 and l + w / 2 < 1400
