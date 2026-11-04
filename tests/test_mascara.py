"""0.99.42: perfis de ocultação (Tela, Ensino, Publicação) na tela, na lista do banco e na exportação."""
import sys
from pathlib import Path

import numpy as np
import pydicom
import pytest
from pydicom.uid import generate_uid

from ipe.core import mascara as MK
from ipe.imaging.volume import Volume

sys.path.insert(0, str(Path(__file__).parent))


def test_pseudonimo_e_datas():
    a, b = MK.pseudonimo("P1"), MK.pseudonimo("P2")
    assert a == MK.pseudonimo("P1") and a != b and a.startswith("PACIENTE-") and len(a) == 15
    d = MK.dias_de_deslocamento("P1")
    assert 30 <= d <= 329 and d == MK.dias_de_deslocamento("P1")
    assert MK.deslocar_data("20260310", 40) == "20260129" and MK.deslocar_data("", 40) == ""
    info1 = {"patient_name": "SILVA^ANA", "patient_id": "P1", "birth_date": "19700101", "sex": "F",
             "patient_age": "056Y", "study_date": "20261101", "institution": "Clínica", "accession": "A1"}
    info2 = dict(info1, study_date="20250901")
    e1, e2 = MK.mascarar_info(info1, "ensino"), MK.mascarar_info(info2, "ensino")
    assert e1["patient_name"] == a and not e1["patient_id"] and not e1["birth_date"] and e1["sex"] == "F"
    assert e1["study_date"] != info1["study_date"] and not e1["institution"] and not e1["accession"]
    from datetime import date
    dd = lambda s: date(int(s[:4]), int(s[4:6]), int(s[6:]))  # noqa: E731
    assert (dd(e1["study_date"]) - dd(e2["study_date"])) == (dd("20261101") - dd("20250901"))   # o intervalo fica
    t = MK.mascarar_info(info1, "tela")
    assert t["study_date"] == "20261101" and t["patient_id"].startswith("PACIENTE-")
    p = MK.mascarar_info(info1, "publicacao")
    assert p["patient_name"] == "Paciente" and not p["study_date"] and p["patient_age"] == "056Y"
    o = MK.mascarar_info(info1, "oculto", "Caso 3")
    assert o["patient_name"] == "Caso 3" and not o["sex"]
    assert MK.normalizar("xyz") == "oculto"


def test_exportacao_desloca_as_datas_do_mesmo_paciente():
    from ipe.exporter.anonymize import AnonOptions, anonymize
    op = AnonOptions(enabled=True, shift_dates=True)
    out = []
    for data in ("20261101", "20250901"):
        ds = pydicom.Dataset()
        ds.PatientName, ds.PatientID, ds.StudyDate, ds.SeriesDate = "SILVA^ANA", "P1", data, data
        anonymize(ds, op, 1, "sal")
        out.append(ds.StudyDate)
        assert ds.SeriesDate == ds.StudyDate and ds.PatientID != "P1"
    d = MK.dias_de_deslocamento("P1")
    assert out == [MK.deslocar_data("20261101", d), MK.deslocar_data("20250901", d)]


def test_tela_mostra_o_perfil(env, tmp_path):
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    from test_registro_rigido import _serie
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    d = np.zeros((4, 32, 32), np.float32)
    v = Volume(d, np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 2.0]), 1.0, 1.0, None, "")
    estudo = generate_uid()
    _serie(tmp_path / "a", v, estudo, generate_uid(), "Ax T1", "20261101")
    Importer(db, paths.storage).import_paths([tmp_path / "a"])
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        w.open_study(estudo)
        QApplication.processEvents()
        tab = next(iter(w.all_viewer_tabs()))
        vp = next(x for x in tab.viewports if x.study_uid == estudo)
        tab.set_perfil_de_ocultacao("ensino")
        assert tab.anonymize and w.settings.get(MK.CHAVE) == "ensino"
        linhas = vp._text_lines()
        tl = " | ".join(t for t, _h in linhas["tl"])
        tr = " | ".join(t for t, _h in linhas["tr"])
        pseud = MK.pseudonimo("REG1")
        assert pseud in tl and "Ensino" in tl and "REGISTRO" not in tl
        assert "01/11/2026" not in tr and "/20" in tr                      # data deslocada, mas há data
        assert pseud in tab.title() and "[Ensino]" in tab.title()
        tab.set_perfil_de_ocultacao("publicacao")
        tr = " | ".join(t for t, _h in vp._text_lines()["tr"])
        assert "/20" not in tr and "Paciente" in " ".join(t for t, _h in vp._text_lines()["tl"])
        # a lista do banco com o Ocultar da tela inicial segue o perfil
        w.set_privacy(True)
        m = w.browser.model
        col = next(i for i, c in enumerate(__import__("ipe.ui.browser", fromlist=["COLUMNS"]).COLUMNS)
                   if c[0] == "patient_name")
        assert m.data(m.index(0, col)) == "Paciente"
        tab.set_perfil_de_ocultacao("tela")
        assert m.data(m.index(0, col)) == pseud
        w.set_privacy(False)
        # na reunião (nome do caso) é sempre "ocultar tudo"
        tab.case_label = "Caso 7"
        tab.set_anonymize(True)
        assert vp.perfil_de_ocultacao() == "oculto"
        assert "Caso 7" in " ".join(t for t, _h in vp._text_lines()["tl"])
    finally:
        w._really_quit = True
        w.settings.set("ui.confirmar_sair", False)
        w.close()
