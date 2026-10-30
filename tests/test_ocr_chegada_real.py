"""OCR na chegada sem nada trocado (0.86): impressão DICOM de verdade, leitor de verdade, banco de
verdade. Pedido dele: "em uma versão antiga, quando o filme chegava o OCR, mesmo configurado, não
estava sendo automático. Faça o teste."

Os outros testes do OCR na chegada trocam o leitor por um texto pronto; este passa pela folha
montada e pelo RapidOCR, e cobre os três lugares onde o nome pode estar: o alto da folha, o rodapé
e uma caixa de anotação (texto que a modalidade manda à parte, sem gravar na imagem)."""
import socket
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.printing import arrival as A
from ipe.printing import config as C
from ipe.printing import dispatch as D
from ipe.printing import jobs as J
from ipe.printing import ocr
from ipe.printing import rules as R
from ipe.printing.dicom_print import PageImage, PrinterConfig, dicom_print

pytestmark = pytest.mark.skipif(not ocr.available(), reason="leitor de OCR não instalado")
FONTE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _porta():
    with socket.socket() as so:
        so.bind(("127.0.0.1", 0))
        return so.getsockname()[1]


def _folha(onde: str = "cima", w: int = 1400, h: int = 1700) -> np.ndarray:
    img = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONTE, max(12, w // 50))
    y = 15 if onde == "cima" else h - 80
    if onde != "nenhum":
        d.text((20, y), "TESTE, ANA MARIA     ID: FANT001     F 56A", fill=255, font=f)
        d.text((20, y + w // 40), "IMEB  MAMOGRAFIA DIGITAL  21/10/2026 09:12", fill=255, font=f)
    d.ellipse((w // 4, h // 3, 3 * w // 4, 5 * h // 6), fill=150)
    return np.array(img)


@pytest.fixture()
def estacao(env, sample_dir, tmp_path):
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([sample_dir])
    s = Settings(paths.settings_file)
    porta = _porta()
    pasta = tmp_path / "pdf"
    C.save_servers(s, [C.ServerConfig(name="Mamografia", enabled=True, ae_title="PRNMG", port=porta)])
    D.save_destinations(s, [D.Destination(name="PDF", kind="pdf", folder=str(pasta), dpi=72)])
    R.save_rules(s, [R.Rule(name="Mamo", servers=["Mamografia"], destination="PDF")])
    s.set("dicom", dict(s.get("dicom", {}), enabled=False, http_enabled=False))
    s.set(A.CHAVE, True)                      # como no computador dele (o padrão de fábrica)
    s.save()
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, s)
    w.start_services()

    def imprimir(px):
        assert dicom_print(PrinterConfig(name="p", ae_title="PRNMG", host="127.0.0.1", port=porta),
                           [PageImage(pixels=px)], local_ae="MG_SELENIA").pages == 1

    def esperar(cond, segundos=90):
        fim = time.monotonic() + segundos
        while time.monotonic() < fim:
            app.processEvents()
            if cond():
                return True
            time.sleep(0.1)
        return cond()
    try:
        yield app, w, s, repo, pasta, imprimir, esperar
    finally:
        w.net.shutdown()
        w.close()


@pytest.mark.parametrize("onde", ["cima", "baixo"])
def test_filme_chega_e_o_ocr_de_verdade_identifica_e_encaminha(estacao, onde):
    app, w, s, repo, pasta, imprimir, esperar = estacao
    s.set("printing.hold_unknown_origin", False)
    s.save()
    imprimir(_folha(onde))
    assert esperar(lambda: list(pasta.glob("*.pdf"))), f"nome no {onde} da folha: não saiu sozinho"
    j = repo.print_jobs()[0]
    assert (j["patient_id"], j["id_source"], j["status"]) == ("FANT001", "ocr", "sent")
    # a modalidade é a do exame feito **até** a chegada; os fantomas são de hoje às 10:15, então
    # antes dessa hora o exame "ainda não aconteceu" e a modalidade fica vazia (como deve)
    from datetime import datetime
    mg = next(e for e in repo.search_studies() if e.patient_id == "FANT001" and "MG" in (e.modalities or ""))
    feito = datetime.strptime(mg.study_date + mg.study_time[:6], "%Y%m%d%H%M%S") <= datetime.now()
    assert j["modality"] == ("MG" if feito else "")


def test_aparelho_sem_cadastro_identifica_mas_diz_por_que_parou(estacao):
    app, w, s, repo, pasta, imprimir, esperar = estacao      # hold_unknown_origin: o padrão (segura)
    imprimir(_folha("cima"))
    assert esperar(lambda: bool(repo.print_jobs()) and repo.print_jobs()[0]["id_source"] == "ocr")
    for _ in range(20):
        app.processEvents()
        time.sleep(0.05)
    j = repo.print_jobs()[0]
    assert j["status"] == "new" and not list(pasta.glob("*.pdf"))
    aba = w.show_prints()
    aba.refresh()
    assert aba._situacao(dict(j, kind="scp")) == "Parado: aparelho sem cadastro"


def test_nome_so_na_caixa_de_anotacao(env, sample_dir, tmp_path, monkeypatch):
    """Sem nome na imagem, e mesmo sem o leitor de OCR: o texto da anotação basta."""
    paths, db, repo = env
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([sample_dir])
    monkeypatch.setattr(ocr, "available", lambda: False)
    job = J.PrintJob(uid="an1", label="MAMO")
    job.films.append(J.FilmBox(annotations=[{"position": 1, "text": "TESTE^ANA MARIA  FANT001"}]))
    pasta = tmp_path / "an1"
    pasta.mkdir()
    achado = A.identify(job, pasta, repo)
    assert achado is not None and job.patient_id == "FANT001" and job.id_source == "ocr"
    assert "FANT001" in A.texto_sem_ocr(job) and "MAMO" in A.texto_sem_ocr(job)
