"""Selos de integridade na imagem (0.99.22): compressão com perdas (grave na mamografia), Modality
LUT não aplicada, pixel não quadrado, imagem derivada."""
from dataclasses import replace

import numpy as np
import pydicom
import pytest
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from PySide6.QtWidgets import QApplication

from ipe.imaging import selos as SL


def test_mamografia_com_perdas_e_grave():
    s = SL.selos({"Modality": "MG", "LossyImageCompression": "01", "LossyImageCompressionRatio": "15.2",
                  "LossyImageCompressionMethod": "ISO_10918_1"})
    assert len(s) == 1 and s[0].grave and s[0].chave == "perdas"
    assert "JPEG, 15:1" in s[0].texto and "imprópria" in s[0].texto


def test_outras_modalidades_com_perdas_so_avisam():
    s = SL.selos({"Modality": "CT", "_ts": "1.2.840.10008.1.2.4.91"})
    assert [x.chave for x in s] == ["perdas"] and not s[0].grave
    assert "JPEG 2000" in s[0].texto


def test_sem_perdas_nao_tem_selo():
    assert SL.selos({"Modality": "MG", "_ts": "1.2.840.10008.1.2.4.90", "LossyImageCompression": "00"}) == []
    assert SL.selos({"Modality": "MG", "_ts": "1.2.840.10008.1.2.1"}) == []


def test_taxas_em_serie_se_multiplicam():
    assert SL._taxa({"LossyImageCompressionRatio": "['5', '2']"}) == "10:1"
    assert SL._taxa({"LossyImageCompressionRatio": "2.5"}) == "2.5:1"


def test_pixel_nao_quadrado_e_derivada():
    s = SL.selos({"ImageType": "['DERIVED', 'SECONDARY', 'MPR']"}, (0.5, 0.7))
    assert {x.chave for x in s} == {"pixel", "derivada"}
    assert SL.selos({"ImageType": "DERIVED\\PRIMARY"}, (0.5, 0.5)) == []   # mamografia para apresentação


def test_graves_primeiro():
    s = SL.selos({"Modality": "CT", "_ts": "1.2.840.10008.1.2.4.50", "_modality_lut": "1"})
    assert [x.chave for x in s] == ["lut", "perdas"]


def _dcm(path, **extra):
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.1.2"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID, ds.SOPInstanceUID = meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID
    ds.Modality = "MG"
    ds.Rows = ds.Columns = 8
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.PixelData = np.arange(64, dtype=np.uint16).tobytes()
    for k, v in extra.items():
        setattr(ds, k, v)
    ds.save_as(path, enforce_file_format=True)
    return path


def test_a_leitura_traz_o_que_os_selos_precisam(tmp_path):
    from ipe.imaging.series import Frame, read_frame
    p = _dcm(tmp_path / "a.dcm", LossyImageCompression="01", LossyImageCompressionRatio=[10, 2],
             LossyImageCompressionMethod=["ISO_10918_1"])
    lut = pydicom.Dataset()
    lut.LUTDescriptor = [64, 0, 16]
    lut.add_new(0x00283006, "US", list(range(64)))
    lut.ModalityLUTType = "US"
    ds = pydicom.dcmread(p)
    ds.ModalityLUTSequence = [lut]
    ds.save_as(p)
    img = read_frame(Frame(str(p), 0, "1", 1, None, None, ""))
    assert img.header["_ts"] == ExplicitVRLittleEndian and img.header["_modality_lut"] == "1"
    s = SL.selos(img.header, img.pixel_spacing)
    assert [x.chave for x in s][:2] == ["perdas", "lut"] and "20:1" in s[0].texto


def test_reconstrucao_herda_as_perdas():
    from ipe.imaging.volume import _header_de_origem
    h = _header_de_origem({"Modality": "MG", "LossyImageCompression": "01", "ImageType": "ORIGINAL",
                           "_ts": "1.2.840.10008.1.2.4.50", "SliceThickness": "1"})
    assert "ImageType" not in h and "SliceThickness" not in h
    assert SL.selos(h)[0].grave


# ------------------------------------------------------------------ na tela
@pytest.fixture()
def tc(env, sample_dir):
    from test_pedidos_29_10 import _sem_protocolos
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, _sem_protocolos(Settings(paths.settings_file)))
    w.resize(1200, 800)
    w.show()
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 1)
    app.processEvents()
    yield app, w, tab, tab.viewports[0]
    w.close()


def test_o_quadro_mostra_o_selo_e_o_grave_resiste_ao_nivel(tc):
    app, w, tab, vp = tc
    assert vp.selos() == []                         # o exame de teste é sem perdas
    vp._img = replace(vp._img, header={**vp._img.header, "Modality": "MG", "LossyImageCompression": "01"})
    vp.grab()
    assert "selos" in vp._hotspots
    w.settings.set("viewer.anotacoes_itens", {"completa": ["janela"], "parcial1": ["janela"], "parcial2": []})
    assert [s.chave for s in vp._selos_visiveis()] == ["perdas"]      # grave fica mesmo fora da lista
    vp._img = replace(vp._img, header={**vp._img.header, "Modality": "CT"})
    assert vp._selos_visiveis() == []                                  # o informativo segue a lista
    vp._img = replace(vp._img, header={**vp._img.header, "Modality": "MG"})
    tab.set_anotacoes("ausente")
    assert vp._selos_visiveis() == []


# ------------------------------------------------------------------ mistura de pacientes (item 2)
def _outro_paciente(w, uid_aberto):
    a = w.repo.study_info(uid_aberto)
    for acc in ("ACC2001", "ACC3001", "ACC4001", "ACC5001"):
        u = w.repo.find_study_uids(accession=acc)
        if u and w.repo.study_info(u[0])["patient_id"] != a["patient_id"]:
            return acc, u[0]
    raise AssertionError("sem outro paciente nos dados de teste")


def test_pacientes_diferentes_so_por_nome_ou_id():
    from ipe.ui import compare_studies as CS
    a = {"patient_name": "SILVA^ANA", "patient_id": "1", "birth_date": "19700101"}
    assert not CS.pacientes_diferentes([a, {**a, "birth_date": ""}])
    assert not CS.pacientes_diferentes([a, {**a, "patient_name": "silva  ana"}])
    assert CS.pacientes_diferentes([a, {**a, "patient_id": "2"}])


@pytest.mark.parametrize("modo,abertas", [("fechar", 1), ("manter", 2), ("cancelar", 1)])
def test_chamada_com_outro_paciente(tc, monkeypatch, modo, abertas):
    app, w, tab, vp = tc
    acc, uid = _outro_paciente(w, tab.study_uid)
    monkeypatch.setattr(w, "perguntar_outro_paciente", lambda novo, outros: modo)
    w.handle_external({"accession": acc})
    app.processEvents()
    tabs = w.all_viewer_tabs()
    assert len(tabs) == abertas
    if modo == "fechar":
        assert tabs[0].study_uid == uid
    if modo == "cancelar":
        assert tabs[0] is tab


def test_preferencia_decide_sem_perguntar(tc, monkeypatch):
    app, w, tab, vp = tc
    acc, uid = _outro_paciente(w, tab.study_uid)
    w.settings.set("viewer.outro_paciente_externo", "fechar")
    monkeypatch.setattr(w, "perguntar_outro_paciente", lambda *a: pytest.fail("perguntou"))
    w.handle_external({"accession": acc})
    assert [t.study_uid for t in w.all_viewer_tabs()] == [uid]


def test_mesmo_paciente_nao_pergunta(tc, monkeypatch):
    app, w, tab, vp = tc
    monkeypatch.setattr(w, "perguntar_outro_paciente", lambda *a: pytest.fail("perguntou"))
    w.handle_external({"accession": "ACC0901"})          # anterior do mesmo paciente
    assert len(w.all_viewer_tabs()) == 2


def test_selo_de_mistura_no_layout(tc):
    app, w, tab, vp = tc
    acc, uid = _outro_paciente(w, tab.study_uid)
    assert all(s.chave != "paciente" for s in vp.selos())
    tab.set_layout(1, 2)
    app.processEvents()
    vp, outro = tab.viewports[0], tab.viewports[1]
    if not outro.frames:
        outro.frames = list(vp.frames)
    outro.study_info = w.repo.study_info(uid)       # como se uma série de outro paciente caísse ali
    assert vp.selos()[0].chave == "paciente" and vp.selos()[0].grave
    tab.anonymize = vp.anonymize = True
    vp.case_label = "Caso 3"
    assert vp.selos()[0].texto.endswith("Caso 3")


def test_filme_pergunta_antes_de_juntar_pacientes(tc, monkeypatch):
    app, w, tab, vp = tc
    from ipe.printing.film import Cell
    acc, uid = _outro_paciente(w, tab.study_uid)
    comp = w.film_composer() if hasattr(w, "film_composer") else None
    if comp is None:
        pytest.skip("sem compositor")
    serie_a = w.repo.series_for_study(tab.study_uid)[0].series_uid
    serie_b = w.repo.series_for_study(uid)[0].series_uid
    assert comp.place_cells([comp._cell_for(serie_a, 0, tab.study_uid)]) == 1
    perguntas = []
    monkeypatch.setattr(comp, "confirmar_mistura", lambda infos: perguntas.append(infos) or False)
    assert comp.place_cells([comp._cell_for(serie_b, 0, uid)]) == 0
    assert len(perguntas) == 1
    assert comp.place_cells([comp._cell_for(serie_a, 1, tab.study_uid)]) == 1     # mesmo paciente: sem pergunta
    assert len(perguntas) == 1
