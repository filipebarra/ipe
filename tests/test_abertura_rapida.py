"""0.99.86: abertura dos exames — decodificador mais rápido para JPEG-LS, cronômetro no registro."""
import logging

import numpy as np
import pydicom
import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, JPEGLSLossless, generate_uid

from ipe.core import cronometro as CR
from ipe.imaging import series as SE


def _jls(path, shape=(256, 200)):
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.1.2"
    ds.SOPInstanceUID = generate_uid()
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.Modality = "MG"
    ds.Rows, ds.Columns = shape
    ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 12, 11, 0
    yy, xx = np.mgrid[:shape[0], :shape[1]]
    a = ((np.sin(xx / 17) + np.cos(yy / 11)) * 800 + 1500).clip(0, 4095).astype(np.uint16)
    ds.PixelData = a.tobytes()
    ds.compress(JPEGLSLossless, encoding_plugin="pyjpegls")
    ds.save_as(path, enforce_file_format=True)
    return a


def test_jpeg_ls_usa_o_pyjpegls_e_da_a_mesma_imagem(tmp_path, monkeypatch):
    pytest.importorskip("jpeg_ls")
    assert SE.decodificador_preferido(str(JPEGLSLossless)) == "pyjpegls"
    assert SE.decodificador_preferido("1.2.840.10008.1.2.1") is None
    p = tmp_path / "mg.dcm"
    original = _jls(p)
    usados = []
    real = Dataset.pixel_array_options

    def espia(self, **k):
        usados.append(k.get("decoding_plugin"))
        return real(self, **k)
    monkeypatch.setattr(Dataset, "pixel_array_options", espia)
    # 0.100.38: primeiro o imagecodecs (o mesmo CharLS, sem segurar a trava do Python) — a mesma imagem
    img = SE.read_frame(SE.Frame(str(p), 0, "x", 1))
    assert usados == [] and np.array_equal(img.pixels, original.astype(np.float32))
    # sem ele (ou quando ele não serve), o pyjpegls, como antes
    monkeypatch.setattr(SE, "_jpegls_rapido", lambda ds: None)
    img = SE.read_frame(SE.Frame(str(p), 0, "x", 1))
    assert usados == ["pyjpegls"]
    assert np.array_equal(img.pixels, original.astype(np.float32))


def test_sem_o_pyjpegls_fica_o_padrao(tmp_path, monkeypatch):
    monkeypatch.setattr(SE, "_DISPONIVEL", {str(JPEGLSLossless): None})
    assert SE.decodificador_preferido(str(JPEGLSLossless)) is None
    p = tmp_path / "mg.dcm"
    original = _jls(p)
    img = SE.read_frame(SE.Frame(str(p), 0, "x", 1))
    assert np.array_equal(img.pixels, original.astype(np.float32))


def test_preaquecer_nao_quebra():
    SE.preaquecer()


def test_cronometro_escreve_uma_linha_por_abertura(caplog):
    caplog.set_level(logging.INFO, logger="ipe.abertura")
    CR.iniciar("CT TC ABDOME")
    CR.marca("banco")
    CR.marca("barra")
    CR.primeira_imagem()
    CR.primeira_imagem()                       # só a primeira pintura conta
    CR.marca("depois de fechada")              # não entra
    CR.depois("sobreposições", 0.5)
    CR.depois("sobreposições", 0.5)            # uma vez só
    linhas = [r.getMessage() for r in caplog.records if r.name == "ipe.abertura"]
    assert len(linhas) == 2
    assert linhas[0].startswith("Abertura (CT TC ABDOME): primeira imagem em ") and "imagem" in linhas[0]
    assert "depois de fechada" not in linhas[0]
    assert "sobreposições pronto em" in linhas[1] and "(0,50 s)" in linhas[1]
    CR.cancelar()
    CR.marca("nada")                           # sem abertura em curso: não faz nada
    CR.primeira_imagem()


def test_abrir_um_exame_deixa_a_linha_no_registro(env, sample_dir, caplog):
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    caplog.set_level(logging.INFO, logger="ipe.abertura")
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1200, 800)
    w.show()
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    for _ in range(20):
        app.processEvents()
    linhas = [r.getMessage() for r in caplog.records if r.name == "ipe.abertura"]
    assert linhas and "primeira imagem em" in linhas[0] and "barra" in linhas[0] and "protocolo" in linhas[0]
    w.close()
