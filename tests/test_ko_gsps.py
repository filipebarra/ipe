"""0.99.41: imagens-chave (KO) e anotações (GSPS) em DICOM, medida rascunho e trazer medidas de outro sistema."""
import json
import sys
from pathlib import Path

import numpy as np
import pydicom
import pytest
from pydicom.uid import generate_uid

from ipe.exporter import ko_gsps as KG
from ipe.imaging import measure as M
from ipe.imaging import overlays as O
from ipe.imaging.volume import Volume

sys.path.insert(0, str(Path(__file__).parent))


def _vol():
    d = np.zeros((10, 64, 64), np.float32)
    d[:, 20:44, 20:44] = 300
    return Volume(d, np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 2.0]),
                  1.0, 1.0, None, "")


@pytest.fixture
def exame(env, tmp_path):
    from test_registro_rigido import _serie
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    estudo = generate_uid()
    serie = _serie(tmp_path / "a", _vol(), estudo, generate_uid(), "Ax T1", "20261101")
    Importer(db, paths.storage).import_paths([tmp_path / "a"])
    insts = sorted(repo.instances_for_series(serie), key=lambda i: i["instance_number"])
    return paths, db, repo, estudo, serie, insts


def _medida(repo, estudo, serie, sop, kind, pts, texto="", meta=None):
    a = M.Annotation(kind, (sop, 0), pts, texto, estudo, serie, meta=meta or {})
    return repo.save_annotation(db_id=None, study_uid=estudo, series_uid=serie, sop_uid=sop, frame_index=0,
                                kind=kind, data=a.data_json())


def test_ko_ida_e_volta(exame):
    paths, _db, repo, estudo, serie, insts = exame
    for i in (2, 5):
        repo.toggle_key_image(estudo, serie, insts[i]["sop_uid"], 0)
    ko = KG.build_ko(repo, estudo, "para a reunião")
    assert ko.SOPClassUID == KG.KO_CLASS and ko.Modality == "KO"
    assert ko.ConceptNameCodeSequence[0].CodeValue == "113000"
    assert set(KG.ler_ko(ko)) == {(insts[2]["sop_uid"], 0), (insts[5]["sop_uid"], 0)}
    ev = ko.CurrentRequestedProcedureEvidenceSequence[0].ReferencedSeriesSequence[0]
    assert ev.SeriesInstanceUID == serie and len(ev.ReferencedSOPSequence) == 2
    # grava no exame; num banco "sem" as marcas (outro computador), o KO as traz de volta, uma vez só
    KG.gravar_no_exame(repo, paths.storage, ko)
    assert any(s.modality == "KO" for s in repo.series_for_study(estudo))
    for i in (2, 5):
        repo.toggle_key_image(estudo, serie, insts[i]["sop_uid"], 0)      # desmarca
    assert not repo.key_images(estudo)

    class S(dict):
        def get(self, k, d=None):
            return super().get(k, d)

        def set(self, k, v):
            self[k] = v
    cfg = S()
    assert KG.marcar_kos_do_exame(repo, estudo, cfg) == 2
    assert {k["sop_uid"] for k in repo.key_images(estudo)} == {insts[2]["sop_uid"], insts[5]["sop_uid"]}
    repo.toggle_key_image(estudo, serie, insts[2]["sop_uid"], 0)
    assert KG.marcar_kos_do_exame(repo, estudo, cfg) == 0                   # já lido: não volta


def test_gsps_leva_as_medidas_e_deixa_o_rascunho(exame, tmp_path):
    _paths, _db, repo, estudo, serie, insts = exame
    s0, s1 = insts[3]["sop_uid"], insts[4]["sop_uid"]
    _medida(repo, estudo, serie, s0, "line", [(10.0, 10.0), (40.0, 10.0)])
    _medida(repo, estudo, serie, s0, "ellipse", [(20.0, 20.0), (40.0, 36.0)])
    _medida(repo, estudo, serie, s1, "arrow", [(30.0, 30.0), (50.0, 50.0)], "nódulo")
    _medida(repo, estudo, serie, s1, "text", [(5.0, 5.0)], "comparar")
    _medida(repo, estudo, serie, s1, "line", [(1.0, 1.0), (9.0, 1.0)], meta={"rascunho": True})
    ds, n = KG.build_gsps(repo, estudo)
    assert n == 4 and ds.SOPClassUID == KG.GSPS_CLASS and ds.Modality == "PR"
    ds.save_as(tmp_path / "pr.dcm", enforce_file_format=True)
    obj = O.parse_gsps(pydicom.dcmread(tmp_path / "pr.dcm"))
    g0 = obj.by_frame[(s0, -1)] if (s0, -1) in obj.by_frame else obj.by_frame[(s0, 0)]
    textos = [g.text for g in g0 if g.kind == "text"]
    assert any("30.0 mm" in t for t in textos)                          # o número da régua vai junto
    assert any("Média 300" in t for t in textos)                        # a ROI leva a média
    assert sum(1 for g in g0 if g.kind != "text") == 2
    g1 = obj.by_frame.get((s1, -1)) or obj.by_frame.get((s1, 0))
    assert {"nódulo", "comparar"} <= {g.text for g in g1 if g.kind == "text"}
    assert not any(g.kind != "text" and len(g.points) == 2 and g.points[0] == (1.0, 1.0) for g in g1)
    # a régua do rascunho também não vai ao SR, ao laudo nem à planilha
    from ipe.exporter.sr import build_sr
    from ipe.reporting.fill import measurements_text
    _sr, nsr = build_sr(repo, estudo)
    assert "8.0 mm" not in measurements_text(repo, estudo) and nsr > 0


def test_tela_grava_le_o_mais_recente_e_traz_medidas(exame, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    paths, db, repo, estudo, serie, insts = exame
    s0 = insts[3]["sop_uid"]
    _medida(repo, estudo, serie, s0, "line", [(10.0, 10.0), (40.0, 10.0)])
    repo.toggle_key_image(estudo, serie, insts[6]["sop_uid"], 0)
    # dois GSPS de "outro sistema": o mais novo fica ligado
    for k, quando in enumerate(("20250101", "20260101")):
        ds, _n = KG.build_gsps(repo, estudo)
        ds.SeriesDescription = f"Estação X {k}"
        ds.ContentDescription = f"Estação X {k}"
        ds.ContentLabel = f"OUTRO{k}"
        ds.PresentationCreationDate = quando
        ds.Manufacturer = "Outro"
        d = tmp_path / f"pr{k}"
        d.mkdir()
        ds.save_as(d / "pr.dcm", enforce_file_format=True)
        Importer(db, paths.storage).import_paths([d])
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        w.open_study(estudo)
        QApplication.processEvents()
        tab = next(iter(w.all_viewer_tabs()))
        tab.load_overlay_objects()
        prs = [o for o in tab.overlay_objects if o.source == "GSPS"]
        assert len(prs) == 2
        assert [o.enabled for o in sorted(prs, key=lambda o: o.quando)] == [False, True]
        # trazer as medidas do mais novo: viram medidas do Ipê
        novo = max(prs, key=lambda o: o.quando)
        antes = len(repo.annotations_for_studies([estudo]))
        assert tab.hidratar_medidas(novo) >= 1 and not novo.enabled
        assert len(repo.annotations_for_studies([estudo])) > antes
        # rascunho pelo menu da medida
        vp = next(v for v in tab.viewports if v.study_uid == estudo)
        a = vp.annotations[0] if vp.annotations else M.Annotation.from_record(repo.annotations_for_studies([estudo])[0])
        vp.marcar_rascunho(a, True)
        assert M.e_rascunho(next(r for r in repo.annotations_for_studies([estudo]) if r["id"] == a.db_id))
        # gravar KO + GSPS pelo botão
        uids = tab.gravar_ko_gsps(perguntar=False)
        mods = {s.series_uid: s.modality for s in repo.series_for_study(estudo)}
        assert sorted(mods[u] for u in uids) == ["KO", "PR"]
        # o nosso GSPS, ao reler o exame, nasce desligado (as medidas já estão no banco)
        tab._overlay_studies = set()
        tab.overlay_objects[:] = []
        tab.load_overlay_objects()
        nossos = [o for o in tab.overlay_objects if getattr(o, "nosso", False)]
        assert nossos and not any(o.enabled for o in nossos)
        # a preferência faz a medida nova nascer rascunho
        w.settings.set("viewer.medidas_rascunho", True)
        b = vp._new_annotation("line", [(1.0, 1.0), (2.0, 2.0)])
        assert M.e_rascunho(b)
    finally:
        w._really_quit = True
        w.settings.set("ui.confirmar_sair", False)
        w.close()
