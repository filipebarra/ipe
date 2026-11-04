"""0.99.60 — item 7 (parte 2): SUL, referências do fígado e do mediastino, limiar do PERCIST, Deauville e
Q.Check do cabeçalho do PET."""
import json
import math

import numpy as np
import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.imaging import lesions as L
from ipe.imaging import pet_onco as PO
from ipe.importer.scanner import Importer

N, NZ, PX = 40, 24, 4.0
DOSE, MEIA = 370e6, 6586.2


def _pet_ds(**kw) -> Dataset:
    ds = Dataset()
    ds.Modality, ds.Units, ds.DecayCorrection = "PT", "BQML", "START"
    ds.CorrectedImage = ["ATTN", "DECY", "SCAT"]
    ds.PatientWeight, ds.PatientSize, ds.PatientSex = 70, 1.75, "M"
    ds.StudyDate = ds.SeriesDate = ds.AcquisitionDate = "20250101"
    ds.SeriesTime = ds.AcquisitionTime = "100000"
    it = Dataset()
    it.Radiopharmaceutical = "Fluorodeoxyglucose"
    it.RadionuclideTotalDose, it.RadionuclideHalfLife, it.RadiopharmaceuticalStartTime = DOSE, MEIA, "090000"
    ds.RadiopharmaceuticalInformationSequence = Sequence([it])
    ds.Rows = ds.Columns = N
    ds.PixelSpacing, ds.SliceThickness = [PX, PX], PX
    ds.Manufacturer, ds.ManufacturerModelName, ds.SoftwareVersions = "GE", "Discovery", "4.0"
    ds.ReconstructionMethod = "VPFX"
    for k, v in kw.items():
        setattr(ds, k, v)
    return ds


def test_sul_e_massa_magra():
    assert PO.massa_magra_kg(70, 1.75, "M") == pytest.approx(9270 * 70 / (6680 + 216 * 70 / 1.75 ** 2))
    assert PO.massa_magra_kg(60, 165, "F") == pytest.approx(9270 * 60 / (8780 + 244 * 60 / 1.65 ** 2))
    assert PO.massa_magra_kg(70, 1.75, "O") is None
    r, m = PO.razao_sul(_pet_ds())
    assert r == pytest.approx(55.857 / 70, rel=1e-3) and "Janmahasatian" in m
    assert PO.razao_sul(_pet_ds(PatientSize=0))[0] is None
    f = PO.fatores(_pet_ds())
    esperado = 70000 / (DOSE * math.exp(-math.log(2) * 3600 / MEIA))
    assert f["suv"] == pytest.approx(esperado) and f["sul_razao"] == pytest.approx(r)
    v = L.measure_values("ellipse", [(10, 10), (20, 20)], np.full((40, 40), 1000.0), (4.0, 4.0), 0.001, 0.8)
    assert v["sulmax"] == pytest.approx(0.8) and v["sulpeak"] == pytest.approx(0.8)


def test_referencia_procura_o_lugar_homogeneo():
    rng = np.random.default_rng(0)
    data = rng.normal(100, 30, (30, 40, 40))
    data[5:25, 5:35, 20:35] = rng.normal(100, 1, (20, 30, 15))        # região homogênea à direita
    r = PO.referencia(data, (4, 4, 4), (15, 20, 20), 30.0, busca_mm=30, fator=0.01)
    assert r is not None and r["dp"] < 0.05 and r["media"] == pytest.approx(1.0, abs=0.02)
    assert r["centro"][2] >= 23                                         # a esfera inteira na parte homogênea
    m = np.zeros(data.shape, bool)
    m[2:28, 2:38, 2:38] = True
    c = PO.centro_da_mascara(m)
    assert c[2] <= 20                                                   # lobo direito: colunas menores
    assert PO.referencia(data, (4, 4, 4), (1, 1, 1), 30.0, mascara=np.zeros(data.shape, bool)) is None


def test_limiar_deauville_e_lugano():
    fig = {"media": 2.0, "dp": 0.25, "max": 2.6}
    med = {"media": 1.5, "dp": 0.2, "max": 1.8}
    assert PO.limiar_percist(fig)[0] == pytest.approx(3.5)
    assert PO.limiar_percist(None, med)[0] == pytest.approx(3.4)
    assert PO.comparar_figado(fig, {"media": 2.5})[0] == "aviso"
    assert PO.comparar_figado(fig, {"media": 2.1})[0] == "ok"
    assert PO.em_sul({**fig, "sul_razao": 0.5})["media"] == 1.0
    assert [PO.deauville(v, fig, med) for v in (1.2, 1.8, 2.4, 6.0)] == ["2", "3", "4", "5"]
    assert PO.deauville(1.0, fig, med, ausente=True) == "1" and PO.deauville(None, fig, med, nova=True) == "5"
    assert PO.deauville(3.0, None, None) == ""
    assert PO.resposta_lugano(["2", "3"], 10, 3, False) == "RMC"
    assert PO.resposta_lugano(["4"], 10, 5, False) == "RMP"
    assert PO.resposta_lugano(["5"], 10, 14, False) == "DMP"
    assert PO.resposta_lugano(["4"], 10, 10, False) == "DME"
    assert PO.resposta_lugano(["3"], 10, 3, True) == "DMP"


def test_qcheck():
    a = PO.cabecalho(_pet_ds())
    assert a["captacao_min"] == pytest.approx(60) and a["dose_mbq"] == pytest.approx(370)
    niveis = {item: n for n, item, _t in PO.conferir(a)}
    assert niveis["Tempo de captação"] == "ok" and niveis["Unidade"] == "ok" and niveis["Correções"] == "ok"
    b = PO.cabecalho(_pet_ds(SeriesTime="102000", AcquisitionTime="102000", PatientSize=0, Units="CNTS",
                             ManufacturerModelName="Biograph", PatientWeight=60))
    nb = {item: n for n, item, _t in PO.conferir(b)}
    assert nb["Tempo de captação"] == "aviso" and nb["Altura e sexo"] == "aviso" and nb["Unidade"] == "erro"
    cmp = {item: (n, t) for n, item, t in PO.comparar(a, b)}
    assert cmp["Tempo de captação"][0] == "aviso" and "80 min" in cmp["Tempo de captação"][1]
    assert cmp["Modelo"][0] == "aviso" and cmp["Peso"][0] == "aviso"
    assert PO.comparar(a, a)[0][1] == "Comparáveis"
    assert "✓ Tempo de captação: 60 min" in PO.texto(PO.conferir(a))


def _a(st, lid, **meta):
    return {"study_uid": st, "id": hash((st, lid)) % 9999, "series_uid": "s", "sop_uid": "i", "frame_index": 0,
            "data": json.dumps({"meta": {"lesion": lid, **meta}})}


def test_percist_com_sul_e_deauville_no_acompanhamento():
    lesoes = [{"id": 1, "name": "Linfonodo", "kind": "target"}, {"id": 2, "name": "Baço", "kind": "nontarget"}]
    anns = [_a("B", 1, suvmax=10.0, suvpeak=8.0, sulmax=7.0, sulpeak=5.6), _a("B", 2, suvmax=4.0),
            _a("A", 1, suvmax=3.0, suvpeak=2.5, sulmax=2.1, sulpeak=1.75), _a("A", 2, suvmax=1.6)]
    studies = [("B", "20250101"), ("A", "20250401")]
    refs = {"B": {"figado": {"media": 2.0, "dp": 0.2, "max": 2.5, "sul_razao": 0.7},
                  "mediastino": {"media": 1.4, "dp": 0.1, "max": 1.6}},
            "A": {"figado": {"media": 2.6, "dp": 0.2, "max": 3.0, "sul_razao": 0.7},
                  "mediastino": {"media": 1.5, "dp": 0.1, "max": 1.7}}}
    cells = L.collect_cells(lesoes, anns, "percist")
    assert cells[(1, "B")].value == 5.6 and cells[(1, "B")].text("percist") == "SULpk 5.60"
    ev = L.evaluate("percist", lesoes, studies, cells, refs=refs)
    assert ev[1].response == "RMP"
    assert any("fígado" in n and "não são comparáveis" in n for n in ev[1].notes)   # 1,40 → 1,82 SUL: +30%
    cells = L.collect_cells(lesoes, anns, "deauville")
    L.aplicar_deauville(lesoes, cells, refs)
    assert cells[(1, "B")].deauville == "5" and cells[(1, "A")].deauville == "4" and cells[(2, "A")].deauville == "3"
    lesoes[0]["data"] = {"deauville": {"A": "3"}}
    L.aplicar_deauville(lesoes, cells, refs)
    assert cells[(1, "A")].deauville == "3" and cells[(1, "A")].deauville_manual
    ev = L.evaluate("deauville", lesoes, studies, cells, refs=refs)
    assert ev[0].response == "BASE" and ev[0].total == 10.0 and ev[1].response == "RMC"
    txt = L.summary_text("deauville", lesoes, studies, cells, ev, "A")
    assert "Deauville (maior escore): 3" in txt and "Resposta metabólica completa" in txt


# ------------------------------------------------------------------ na tela
def _gravar_pet(pasta, acc="PET001", hora="100000", fator_figado=1.0):
    pasta.mkdir(parents=True, exist_ok=True)
    study, serie, forr = generate_uid(), generate_uid(), generate_uid()
    rng = np.random.default_rng(1)
    vol = rng.normal(1000, 150, (NZ, N, N))
    vol[4:20, 8:32, 4:22] = rng.normal(5000 * fator_figado, 60, (16, 24, 18))   # fígado (lado direito)
    vol[10:14, 30:33, 28:31] = 3000                                          # aorta
    vol[12, 20, 30] = 40000                                                  # lesão
    for k in range(NZ):
        ds = _pet_ds(SeriesTime=hora, AcquisitionTime=hora)
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.128"
        meta.MediaStorageSOPInstanceUID = generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.file_meta = meta
        ds.SOPClassUID, ds.SOPInstanceUID = meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID
        ds.PatientName, ds.PatientID, ds.PatientBirthDate = "PET^TESTE", "PETPAT", "19600101"
        ds.StudyInstanceUID, ds.SeriesInstanceUID, ds.FrameOfReferenceUID = study, serie, forr
        ds.AccessionNumber, ds.StudyDescription, ds.SeriesDescription = acc, "PET-CT FDG", "PET AC"
        ds.SeriesNumber, ds.InstanceNumber = 3, k + 1
        ds.ImagePositionPatient = [-80.0, -80.0, float(k * PX)]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.BitsAllocated = ds.BitsStored = 16
        ds.HighBit, ds.PixelRepresentation = 15, 0
        ds.RescaleSlope, ds.RescaleIntercept = 1.0, 0.0
        ds.PixelData = np.clip(vol[k], 0, 65535).astype(np.uint16).tobytes()
        ds.save_as(pasta / f"{k:03d}.dcm", enforce_file_format=True)
    return study


@pytest.fixture()
def janela(env, tmp_path):
    from test_pedidos_29_10 import _sem_protocolos
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    st = _gravar_pet(tmp_path / "pet")
    Importer(db, paths.storage).import_paths([tmp_path / "pet"])
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, _sem_protocolos(Settings(paths.settings_file)))
    w.resize(1300, 800)
    w.show()
    yield app, w, repo, st
    w.close()


def test_janela_pet(janela):
    from ipe.imaging import overlays as O
    from ipe.ui.viewer.pet_dialog import PetDialog
    app, w, repo, st = janela
    w.handle_external({"accession": "PET001"})
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 1)
    app.processEvents()
    vp = tab.viewports[0]
    assert vp.suv_factor and vp.sul_razao == pytest.approx(55.857 / 70, rel=1e-3)
    tab.lesions_action.trigger()
    app.processEvents()
    painel = tab.lesion_panel
    d = PetDialog(tab, painel)
    d.show()
    assert "SUL = SUV ×" in d.fatores.text() and "✓ Tempo de captação: 60 min" in d.qc.toPlainText()
    # clique no fígado: esfera de 3 cm no lugar homogêneo
    d.pedir_clique("figado")
    assert tab.left_tool == "grow" and tab._ref_pet_pendente is not None
    vp.go_to(12)
    tab.segment_at(vp, 13.5, 20.5)                                 # coluna 13, linha 20: dentro do fígado
    r = d.refs()["figado"]
    assert r["media"] == pytest.approx(5000 * vp.suv_factor, rel=0.02) and r["dp"] < 0.05
    assert "1,5 × fígado + 2 DP" in d.l_limiar.text() and tab._ref_pet_pendente is None
    # mediastino na aorta
    d.pedir_clique("mediastino")
    tab.segment_at(vp, 29.5, 31.5)
    rm = d.refs()["mediastino"]
    assert rm["media"] == pytest.approx(3000 * vp.suv_factor, rel=0.05)
    # automático pela máscara do fígado de outra série (aqui, a própria grade do PET)
    vol = d._volume(vp)
    m = np.zeros(vol.data.shape, bool)
    m[4:20, 8:32, 4:22] = True
    mv = O.MaskVolume.do_volume(vol, m, (0, 0, 0), (200, 100, 50), "liver")
    obj = O.OverlayObject("seg-teste", "SEG", "Órgãos abdominais · TotalSegmentator", study_uid=st, volumes=[mv])
    tab.overlay_objects.append(obj)
    ra = d.figado_automatico()
    assert ra is not None and ra["como"] == "auto" and ra["dp"] < 0.05
    k, j, i = ra["centro"]
    assert m[k, j, i]
    # Deauville no painel
    painel.repo.save_lesion_track(painel.pid, criterion="deauville")
    painel.refresh()
    rows = [painel.table.item(r, 0).text() for r in range(painel.table.rowCount())]
    assert "Deauville" in rows and "Fígado (ref.)" in rows
    d.close()
