"""Conferência de protocolo de RM (0.100.93): parâmetros do cabeçalho, referência do exame e do acervo, conferência,
coluna do banco e a chegada."""
from __future__ import annotations

import copy

import numpy as np
import pydicom
import pytest
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid

from ipe.imaging import protocolo_rm as PR

AX = [1, 0, 0, 0, 1, 0]
SAG = [0, 1, 0, 0, 0, -1]
COR = [1, 0, 0, 0, 0, -1]


def _ds(desc="Ax T2 FSE", iop=AX, tr=4000.0, te=100.0, esp=4.0, estacao="RM1", tipo=("ORIGINAL", "PRIMARY"),
        b=None, study=None, serie=None, numero=1, inst=1, exame="RM CRANIO"):
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = MRImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset("x", {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID, ds.SOPInstanceUID = MRImageStorage, meta.MediaStorageSOPInstanceUID
    ds.Modality, ds.SeriesDescription, ds.StudyDescription = "MR", desc, exame
    ds.PatientName, ds.PatientID, ds.StudyDate = "TESTE^RM", "RM001", "20261120"
    ds.StudyInstanceUID = study or generate_uid()
    ds.SeriesInstanceUID = serie or generate_uid()
    ds.SeriesNumber, ds.InstanceNumber = numero, inst
    ds.ImageType = list(tipo)
    ds.ImageOrientationPatient = iop
    ds.ImagePositionPatient = [0, 0, float(inst) * esp]
    ds.RepetitionTime, ds.EchoTime, ds.FlipAngle = tr, te, 90
    ds.SliceThickness, ds.SpacingBetweenSlices = esp, esp + 1
    ds.Rows = ds.Columns = 16
    ds.PixelSpacing = [15.0, 15.0]
    ds.AcquisitionMatrix = [0, 320, 224, 0]
    ds.MagneticFieldStrength, ds.MRAcquisitionType = 1.5, "2D"
    ds.ScanningSequence, ds.SequenceVariant = "SE", "SK"
    ds.StationName, ds.Manufacturer = estacao, "GE"
    if b is not None:
        ds.add_new((0x0018, 0x9087), "FD", float(b))
    ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit, ds.PixelRepresentation = 15, 0
    ds.PixelData = np.zeros((16, 16), np.uint16).tobytes()
    return ds


def _exame(series, aparelho="RM1", exame="rm cranio"):
    return {"study_uid": "1", "descricao": exame.upper(), "exame": exame, "aparelho": aparelho, "data": "20261120",
            "series": [{"uid": f"s{i}", "numero": i, "descricao": d, "nome": PR.normalizar(d), "params": p}
                       for i, (d, p) in enumerate(series)]}


def _p(**k):
    base = PR.parametros_da_serie(_ds(), 20)
    base.update(k)
    return base


def test_parametros_do_cabecalho():
    p = PR.parametros_da_serie(_ds(desc="Sag T1", iop=SAG, tr=500, te=10), 24)
    assert p["tr"] == 500 and p["te"] == 10 and p["plano"] == "SAG" and p["tipo"] == "2D"
    assert p["matriz"] == "320×224" and p["fov"] == 240.0 and p["espessura"] == 4.0 and p["espaco"] == 5.0
    assert p["campo"] == 1.5 and p["sequencia"] == "SE SK" and p["contraste"] == "pré" and p["imagens"] == 24
    assert PR.plano(COR) == "COR" and PR.plano([1, 0, 0, 0, 0.7, -0.7]) == "OBL"
    pb = PR.parametros_da_serie(_ds(), 40, [0, 1000, 0, 1000])
    assert pb["b"] == "0,1000"


def test_o_que_nao_e_aquisicao_fica_de_fora():
    assert PR.eh_aquisicao(_ds())
    assert not PR.eh_aquisicao(_ds(desc="3-pl T2* FGRE-XL"))
    assert not PR.eh_aquisicao(_ds(desc="ASSET Cal"))
    assert not PR.eh_aquisicao(_ds(desc="ADC (10^-6 mm²/s)", tipo=("DERIVED", "PRIMARY", "ADC")))
    assert not PR.eh_aquisicao(_ds(tipo=("ORIGINAL", "PRIMARY", "LOCALIZER")))


def test_conferencia_contra_o_exame_de_referencia():
    ref = PR.referencia_do_exame(_exame([("Ax T2", _p()), ("Sag T1", _p(plano="SAG", tr=500.0, te=10.0))]))
    assert all(s["obrigatoria"] for s in ref.series) and ref.aparelho == "RM1"
    # igual: conforme
    r = PR.conferir(_exame([("Ax T2", _p()), ("Sag T1", _p(plano="SAG", tr=500.0, te=10.0))]), ref)
    assert r["estado"] == "conforme" and r["resumo"] == "conforme"
    # TR 20% acima: aviso
    r = PR.conferir(_exame([("Ax T2", _p(tr=4800.0)), ("Sag T1", _p(plano="SAG", tr=500.0, te=10.0))]), ref)
    assert r["estado"] == "avisos" and r["series"][0]["difs"][0]["param"] == "tr"
    # TR 5%: dentro
    r = PR.conferir(_exame([("Ax T2", _p(tr=4200.0)), ("Sag T1", _p(plano="SAG", tr=500.0, te=10.0))]), ref)
    assert r["estado"] == "conforme"
    # plano errado: divergência
    r = PR.conferir(_exame([("Ax T2", _p(plano="COR")), ("Sag T1", _p(plano="SAG", tr=500.0, te=10.0))]), ref)
    assert r["estado"] == "divergente" and r["series"][0]["situacao"] == "erro"
    # série faltando e série a mais
    r = PR.conferir(_exame([("Ax T2", _p()), ("Cor FLAIR", _p(plano="COR"))]), ref)
    assert r["estado"] == "divergente" and r["series"][1]["situacao"] == "falta"
    assert [x["descricao"] for x in r["extras"]] == ["Cor FLAIR"]
    assert "falta(m) 1 série(s)" in r["resumo"] and "1 aviso(s)" in r["resumo"]
    # repetida: vale a última
    r = PR.conferir(_exame([("Ax T2", _p(tr=9000.0)), ("Ax T2", _p()),
                            ("Sag T1", _p(plano="SAG", tr=500.0, te=10.0))]), ref)
    assert r["estado"] == "conforme" and r["series"][0]["repeticoes"] == 1
    # tolerância própria da referência
    ref.tolerancias = {"tr": ["rel", 30.0]}
    r = PR.conferir(_exame([("Ax T2", _p(tr=4800.0)), ("Sag T1", _p(plano="SAG", tr=500.0, te=10.0))]), ref)
    assert r["estado"] == "conforme"


def test_serie_com_outro_nome_achada_pelo_plano_e_sequencia():
    ref = PR.referencia_do_exame(_exame([("Ax T2 FSE", _p())]))
    r = PR.conferir(_exame([("AXIAL T2 PROPELLER", _p())]), ref)
    assert r["series"][0]["achada"] == "AXIAL T2 PROPELLER" and r["estado"] == "conforme"


def test_referencia_pelo_acervo_e_o_protocolo_dominante():
    exames = []
    for i in range(5):
        s = [("Ax T2", _p(tr=4000.0 + 10 * i)), ("Sag T1", _p(plano="SAG"))]
        if i < 3:
            s.append(("Cor FLAIR", _p(plano="COR")))           # 60%: opcional
        if i < 2:
            s.append(("Ax SWI", _p()))                          # 40%: fora
        exames.append(_exame(s))
    ref = PR.referencia_pelo_acervo(exames)
    nomes = {s["nome"]: s for s in ref.series}
    assert set(nomes) == {"ax t2", "sag t1", "cor flair"}
    assert nomes["ax t2"]["obrigatoria"] and not nomes["cor flair"]["obrigatoria"]
    assert nomes["ax t2"]["params"]["tr"] == 4020.0
    assert ref.origem.startswith("acervo: 5") and ref.aparelho == "RM1"
    r = PR.conferir(_exame([("Ax T2", _p()), ("Sag T1", _p(plano="SAG"))]), ref)
    assert r["estado"] == "avisos"                              # só a opcional faltando


def test_escolhe_a_referencia_do_aparelho():
    ex = _exame([("Ax T2", _p())], aparelho="RM2")
    geral = PR.Referencia(nome="geral", exame="rm cranio", series=[], id="g")
    rm2 = PR.Referencia(nome="rm2", exame="rm cranio", aparelho="RM2", series=[], id="r2")
    rm1 = PR.Referencia(nome="rm1", exame="rm cranio", aparelho="RM1", series=[], id="r1")
    outro = PR.Referencia(nome="joelho", exame="rm joelho", series=[], id="j")
    assert PR.escolher_referencia(ex, [geral, rm1, rm2, outro]).id == "r2"
    assert PR.escolher_referencia(ex, [geral, rm1, outro]).id == "g"
    assert PR.escolher_referencia(ex, [rm1, outro]) is None
    assert PR.conferir(ex, None)["estado"] == "sem_referencia"


def test_referencias_nas_configuracoes(env):
    from ipe.core.config import Settings
    paths, _db, _repo = env
    s = Settings(paths.settings_file)
    ref = PR.referencia_do_exame(_exame([("Ax T2", _p())]), "Crânio RM1")
    PR.gravar_referencias(s, [ref])
    lidas = PR.referencias(Settings(paths.settings_file))
    assert len(lidas) == 1 and lidas[0].nome == "Crânio RM1" and lidas[0].series[0]["params"]["tr"] == 4000.0
    assert lidas[0].tolerancia("tr") == ("rel", 10.0)


def _gravar_exame(pasta, series, estacao="RM1", exame="RM CRANIO"):
    study = generate_uid()
    for n, (desc, kw, imgs) in enumerate(series, 1):
        serie = generate_uid()
        for i in range(imgs):
            extra = dict(kw)
            if "bs" in extra:
                extra["b"] = extra.pop("bs")[i % 2]
            ds = _ds(desc=desc, study=study, serie=serie, numero=n, inst=i + 1, estacao=estacao, exame=exame,
                     **extra)
            ds.save_as(str(pasta / f"{study[-6:]}_{n}_{i}.dcm"), enforce_file_format=True)
    return study


def test_exame_do_banco_conferido_e_na_coluna(env, tmp_path):
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    pasta = tmp_path / "rm"
    pasta.mkdir()
    bom = _gravar_exame(pasta, [("3-pl loc", {}, 3), ("Ax T2", {}, 4), ("Ax DWI", {"bs": [0, 1000]}, 4),
                                ("Sag T1", {"iop": SAG, "tr": 500, "te": 10}, 3)])
    ruim = _gravar_exame(pasta, [("Ax T2", {"tr": 6000}, 4), ("Ax DWI", {"bs": [0, 800]}, 4)])
    Importer(db, paths.storage).import_paths([pasta])
    ex = PR.series_do_exame(repo, bom)
    assert [s["descricao"] for s in ex["series"]] == ["Ax T2", "Ax DWI", "Sag T1"]   # o localizador fica de fora
    assert ex["aparelho"] == "RM1" and ex["exame"] == "rm cranio"
    assert ex["series"][1]["params"]["b"] == "0,1000"
    s = Settings(paths.settings_file)
    PR.gravar_referencias(s, [PR.referencia_do_exame(ex, "Crânio")])
    r = PR.conferir_exame(repo, s, ruim)
    assert r["estado"] == "divergente"
    nomes = {x["nome"]: x for x in r["series"]}
    assert nomes["sag t1"]["situacao"] == "falta"
    assert {d["param"] for d in nomes["ax dwi"]["difs"]} == {"b"}
    assert {d["param"] for d in nomes["ax t2"]["difs"]} == {"tr"}
    assert PR.guardado(repo, ruim)["estado"] == "divergente"
    assert PR.conferir_exame(repo, s, bom)["estado"] == "conforme"
    linhas = {r.study_uid: r for r in repo.search_studies()}
    assert linhas[ruim].protocolo.startswith("⚠ falta(m) 1 série(s)")
    assert linhas[bom].protocolo == "✓ conforme"
    csv = PR.para_csv([PR.guardado(repo, ruim)])
    assert "falta" in csv and ";tr;6000.0;4000.0" in csv


def test_na_chegada_confere_sozinho(env, tmp_path, monkeypatch):
    import threading

    from ipe.automation.engine import AutomationEngine
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    pasta = tmp_path / "rm"
    pasta.mkdir()
    a = _gravar_exame(pasta, [("Ax T2", {}, 2)])
    b = _gravar_exame(pasta, [("Ax T2", {"te": 150}, 2)])
    Importer(db, paths.storage).import_paths([pasta])
    s = Settings(paths.settings_file)
    eng = AutomationEngine.__new__(AutomationEngine)
    eng.repo, eng.settings = repo, s

    class _Sinal:
        def emit(self):
            pass
    eng.changed = _Sinal()
    assert eng.conferir_protocolo(b) is False                     # sem referência: nada
    PR.gravar_referencias(s, [PR.referencia_do_exame(PR.series_do_exame(repo, a), "Crânio")])
    feitos = []
    monkeypatch.setattr(threading, "Thread", lambda target, **_k: type("T", (), {
        "start": lambda self: (target(), feitos.append(1))})())
    assert eng.conferir_protocolo(b) is True and feitos
    assert PR.guardado(repo, b)["estado"] == "avisos"
    s.set(PR.CHAVE_LIGADO, False)
    assert eng.conferir_protocolo(b) is False


def test_tela_da_conferencia_e_das_referencias(env, tmp_path, qtbot=None):
    pytest.importorskip("PySide6")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.ui import protocolo_rm_ui as UI
    paths, db, repo = env
    pasta = tmp_path / "rm"
    pasta.mkdir()
    a = _gravar_exame(pasta, [("Ax T2", {}, 2), ("Sag T1", {"iop": SAG}, 2)])
    b = _gravar_exame(pasta, [("Ax T2", {"tr": 7000}, 2)])
    Importer(db, paths.storage).import_paths([pasta])
    s = Settings(paths.settings_file)
    d = UI.ConferenciaDialog(repo, s, b)
    assert "sem referência" in d.l_estado.text() or "no reference" in d.l_estado.text()
    PR.gravar_referencias(s, [PR.referencia_do_exame(PR.series_do_exame(repo, a), "Crânio")])
    d.carregar(True)
    assert d.resultado["estado"] == "divergente" and d.tabela.rowCount() == 2
    assert d.c_ref.currentData() == PR.referencias(s)[0].id
    p = UI.ProtocolosDialog(repo, s)
    assert p.t_refs.rowCount() == 1
    e = UI.EditarReferenciaDialog(PR.referencias(s)[0])
    e.t_tol.item(0 + UI.PR.ORDEM.index("tr"), 2).setText("50")
    nova = e.resultado()
    assert nova.tolerancias["tr"] == ["rel", 50.0] and len(nova.series) == 2
    p.d_de.setDate(p.d_de.date().fromString("20000101", "yyyyMMdd"))
    p.listar()
    assert p.t_ex.rowCount() == 1                                  # o exame conferido na tela
    copia = copy.deepcopy(PR.referencias(s)[0])
    assert copia.nome == "Crânio"
    d.close(), p.close(), e.close()
    app.processEvents()
