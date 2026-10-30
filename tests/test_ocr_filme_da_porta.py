"""0.89: OCR na chegada também para o filme montado com as imagens mandadas à porta da impressora.

Pedido dele: "OCR de exames DICOM recebidos pelo DICOM Print está funcionando. Implemente também
para filmes montados recebidos prontos" — as imagens que a modalidade manda à porta da impressora
e que o programa monta em filme. Aqui o nome do cabeçalho das imagens é genérico ("ANONIMO") e o
nome de verdade está gravado na imagem, como no ultrassom.

Sem nada trocado: C-STORE de verdade, RapidOCR de verdade, banco com os fantomas.
"""
import time
from pathlib import Path

import numpy as np
import pydicom
import pytest
from PIL import Image, ImageDraw, ImageFont
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid
from PySide6.QtWidgets import QApplication, QDialog

from ipe.core.config import Settings
from ipe.printing import arrival as A
from ipe.printing import config as C
from ipe.printing import dispatch as D
from ipe.printing import ocr
from ipe.printing import rules as R
from tests.test_print_port_images import _mandar, _porta

pytestmark = pytest.mark.skipif(not ocr.available(), reason="leitor de OCR não instalado")
FONTE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _imagens(pasta: Path, com_nome: bool, n: int = 2) -> list[Path]:
    """Imagens de "ultrassom" (captura secundária) com nome genérico no cabeçalho."""
    estudo, serie = generate_uid(), generate_uid()
    saida = []
    for k in range(n):
        img = Image.new("L", (800, 600), 0)
        d = ImageDraw.Draw(img)
        f = ImageFont.truetype(FONTE, 22)
        if com_nome:
            d.text((15, 10), "TESTE, ANA MARIA   ID FANT001   21/10/2026", fill=255, font=f)
        d.ellipse((250, 200, 550, 450), fill=120)
        px = np.array(img)
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
        meta.MediaStorageSOPInstanceUID = generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = Dataset()
        ds.file_meta = meta
        ds.SOPClassUID, ds.SOPInstanceUID = SecondaryCaptureImageStorage, meta.MediaStorageSOPInstanceUID
        ds.StudyInstanceUID, ds.SeriesInstanceUID = estudo, serie
        ds.PatientName, ds.PatientID = "ANONIMO", "0"
        ds.Modality, ds.StudyDescription, ds.SeriesDescription = "US", "US MAMAS", "US"
        ds.StudyDate, ds.StudyTime = "20261021", "101500"
        ds.InstanceNumber, ds.SeriesNumber = k + 1, 1
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.Rows, ds.Columns = px.shape
        ds.BitsAllocated = ds.BitsStored = 8
        ds.HighBit, ds.PixelRepresentation = 7, 0
        ds.PixelData = px.tobytes()
        p = pasta / f"img{k}.dcm"
        ds.save_as(p, enforce_file_format=True)
        saida.append(p)
    return saida


@pytest.fixture()
def estacao(env, sample_dir, tmp_path):
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([sample_dir])
    s = Settings(paths.settings_file)
    porta = _porta()
    pasta = tmp_path / "pdf"
    C.save_servers(s, [C.ServerConfig(name="Ultrassom", enabled=True, ae_title="PRNUS", port=porta,
                                      to_database=False)])
    D.save_destinations(s, [D.Destination(name="PDF", kind="pdf", folder=str(pasta), dpi=72)])
    R.save_rules(s, [R.Rule(name="US", servers=["Ultrassom"], destination="PDF")])
    s.set("dicom", dict(s.get("dicom", {}), enabled=False, http_enabled=False))
    s.set("printing.hold_unknown_origin", False)
    s.set(A.CHAVE, True)
    s.save()
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, s)
    w.start_services()

    def esperar(cond, segundos=90):
        fim = time.monotonic() + segundos
        while time.monotonic() < fim:
            app.processEvents()
            if cond():
                return True
            time.sleep(0.1)
        return cond()
    try:
        yield app, w, repo, pasta, porta, esperar
    finally:
        w.net.shutdown()
        w.close()


def test_nome_gravado_na_imagem_identifica_e_o_filme_sai(estacao, tmp_path):
    app, w, repo, pasta, porta, esperar = estacao
    (tmp_path / "in").mkdir()
    assert _mandar(porta, _imagens(tmp_path / "in", com_nome=True)) == 2
    assert esperar(lambda: list(pasta.glob("*.pdf"))), "identificado e não saiu"
    f = repo.films()[0]
    assert (f["patient_id"], f["id_source"]) == ("FANT001", "ocr") and f["patient_name"] == "TESTE, Ana Maria"
    # a folha impressa leva o nome achado, e não o "ANONIMO" do cabeçalho das imagens
    from ipe.printing.film import Film
    from ipe.ui.film.render import FrameSource, header_lines
    filme = Film.from_dict(repo.film_data(f["id"]))
    esquerda, _dir = header_lines(filme, filme.sheets[0], FrameSource(repo))
    assert esquerda[0] == "TESTE, Ana Maria" and "FANT001" in esquerda[1]


def test_sem_nome_na_imagem_espera_e_sai_depois_de_confirmar(estacao, tmp_path, monkeypatch):
    app, w, repo, pasta, porta, esperar = estacao
    (tmp_path / "in").mkdir()
    assert _mandar(porta, _imagens(tmp_path / "in", com_nome=False)) == 2
    assert esperar(lambda: bool(repo.films()))
    for _ in range(20):
        app.processEvents()
        time.sleep(0.05)
    f = repo.films()[0]
    assert f["id_source"] == "aguardando" and not list(pasta.glob("*.pdf")), "saiu sem paciente"
    aba = w.show_prints()
    aba.refresh()
    i = next(k for k, r in enumerate(aba.rows) if r["kind"] == "film" and r["id"] == f["id"])
    assert aba._situacao(aba.rows[i]) == "Esperando paciente"
    aba.table.selectRow(i)
    assert aba.b_id.isEnabled()
    from ipe.ui import prints_tab as PT

    def aceitar(dlg):
        dlg.nome.setText("TESTE^ANA MARIA")
        dlg.ident.setText("FANT001")
        return QDialog.Accepted
    monkeypatch.setattr(PT.IdentifyDialog, "exec", aceitar)
    aba.identify_selected()
    assert esperar(lambda: list(pasta.glob("*.pdf"))), "confirmado e não saiu pela regra"
    f = repo.films()[0]
    assert (f["patient_id"], f["id_source"]) == ("FANT001", "manual")


def test_ocr_desligado_volta_ao_de_antes(estacao, tmp_path):
    app, w, repo, pasta, porta, esperar = estacao
    w.settings.set(A.CHAVE, False)
    (tmp_path / "in").mkdir()
    assert _mandar(porta, _imagens(tmp_path / "in", com_nome=False)) == 2
    assert esperar(lambda: list(pasta.glob("*.pdf")))
    assert repo.films()[0]["id_source"] == ""
