"""Impressora DICOM (Print SCP): receber os filmes das modalidades e guardar."""
import socket
import time

import numpy as np
import pytest
from pydicom.dataset import Dataset
from pydicom.uid import generate_uid
from pynetdicom import AE
from pynetdicom.sop_class import (
    BasicFilmBox, BasicFilmSession, BasicGrayscaleImageBox, BasicGrayscalePrintManagementMeta,
)

from ipe.network.print_scp import PrintScpServer
from ipe.printing import jobs as J
from ipe.printing.dicom_print import PageImage, PrinterConfig, dicom_print, printer_status


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Printer:
    """A impressora DICOM do programa, ligada numa porta livre."""

    def __init__(self, tmp_path, ae="DICOMPRINT", accept="any"):
        self.root = tmp_path / "Impressoes"
        self.jobs = []
        self.port = free_port()
        self.server = PrintScpServer({"ae_title": ae, "port": self.port, "accept": accept,
                                      "timeout": 15}, self.root, self._got)
        assert self.server.start(), self.server.error

    def _got(self, job, folder):
        self.jobs.append((job, folder))

    def wait(self, n=1, timeout=10.0):
        fim = time.monotonic() + timeout
        while len(self.jobs) < n and time.monotonic() < fim:
            time.sleep(0.05)
        assert len(self.jobs) >= n, "o trabalho de impressão não chegou"
        return self.jobs[n - 1]

    def config(self, **kw) -> PrinterConfig:
        c = PrinterConfig(name="Impressora do programa", ae_title=self.server.ae_title,
                          host="127.0.0.1", port=self.port)
        for k, v in kw.items():
            setattr(c, k, v)
        return c

    def stop(self):
        self.server.stop()


def _pagina(valor: int, h=120, w=90) -> PageImage:
    px = np.full((h, w), valor, dtype=np.uint8)
    px[10:20, 10:40] = 255 - valor            # uma marca para conferir os pixels
    return PageImage(pixels=px, film_size="14INX17IN")


def test_recebe_filme_de_duas_folhas(tmp_path):
    prn = Printer(tmp_path)
    try:
        assert "NORMAL" in printer_status(prn.config(), local_ae="TC1")
        pages = [_pagina(60), _pagina(180)]
        res = dicom_print(prn.config(medium="BLUE FILM", copies=2), pages, local_ae="TC1")
        assert res.pages == 2
        job, folder = prn.wait()
        assert job.calling_ae == "TC1" and job.sheets == 2 and job.images == 2
        assert job.medium == "BLUE FILM" and job.copies == 2 and job.film_size == "14INX17IN"
        # o que foi gravado em disco é o que dá para reler depois
        lido = J.load(folder)
        assert lido is not None and lido.uid == job.uid and lido.sheets == 2
        # os pixels chegaram sem mexer
        for i, page in enumerate(pages):
            px = J.box_pixels(folder, lido.films[i].boxes[0])
            assert px is not None and px.shape == page.pixels.shape
            assert np.array_equal(px, page.pixels)
        folha = J.compose_sheet(folder, lido.films[0], width=200)
        assert folha.shape[0] > folha.shape[1] and folha.max() > 0      # retrato, com imagem
    finally:
        prn.stop()


def test_grade_2x2_e_identificacao_pelo_rotulo(tmp_path):
    """Uma modalidade que manda 4 imagens numa folha 2×2, com nome/ID no rótulo da sessão."""
    prn = Printer(tmp_path)
    try:
        ae = AE(ae_title="MG1")
        ae.add_requested_context(BasicGrayscalePrintManagementMeta)
        assoc = ae.associate("127.0.0.1", prn.port, ae_title=prn.server.ae_title)
        assert assoc.is_established
        meta = BasicGrayscalePrintManagementMeta
        fs = Dataset()
        fs.NumberOfCopies = "1"
        fs.FilmSessionLabel = "MARIA DA SILVA | 998877"
        fs_uid = generate_uid()
        st, _ = assoc.send_n_create(fs, BasicFilmSession, fs_uid, meta_uid=meta)
        assert st.Status == 0x0000
        fb = Dataset()
        fb.ImageDisplayFormat = "STANDARD\\2,2"
        fb.FilmSizeID = "8INX10IN"
        fb.FilmOrientation = "PORTRAIT"
        ref = Dataset()
        ref.ReferencedSOPClassUID = BasicFilmSession
        ref.ReferencedSOPInstanceUID = fs_uid
        fb.ReferencedFilmSessionSequence = [ref]
        fb_uid = generate_uid()
        st, attrs = assoc.send_n_create(fb, BasicFilmBox, fb_uid, meta_uid=meta)
        assert st.Status == 0x0000
        caixas = attrs.ReferencedImageBoxSequence
        assert len(caixas) == 4                      # a folha 2×2 tem quatro caixas
        for i, caixa in enumerate(caixas):
            img = Dataset()
            img.SamplesPerPixel = 1
            img.PhotometricInterpretation = "MONOCHROME2"
            img.Rows, img.Columns = 40, 30
            img.BitsAllocated = img.BitsStored = 8
            img.HighBit, img.PixelRepresentation = 7, 0
            img.PixelData = np.full((40, 30), 40 * (i + 1), dtype=np.uint8).tobytes()
            ds = Dataset()
            ds.ImageBoxPosition = i + 1
            ds.BasicGrayscaleImageSequence = [img]
            st, _ = assoc.send_n_set(ds, BasicGrayscaleImageBox, caixa.ReferencedSOPInstanceUID,
                                     meta_uid=meta)
            assert st.Status == 0x0000
        st, _ = assoc.send_n_action(None, 1, BasicFilmBox, fb_uid, meta_uid=meta)
        assert st.Status == 0x0000
        assoc.release()
        job, folder = prn.wait()
        assert job.sheets == 1 and job.images == 4
        film = job.films[0]
        assert film.display_format == "STANDARD\\2,2" and film.film_size == "8INX10IN"
        # o rótulo trouxe nome e ID — é o único lugar de onde isso pode vir
        assert job.patient_name == "MARIA DA SILVA" and job.patient_id == "998877"
        assert job.id_source == "label"
        folha = J.compose_sheet(folder, film, width=200)
        h, w = folha.shape[:2]
        # cada quadrante da folha ficou com o seu tom (quanto mais tarde a caixa, mais claro)
        tons = [int(folha[:h // 2, :w // 2].max()), int(folha[:h // 2, w // 2:].max()),
                int(folha[h // 2:, :w // 2].max()), int(folha[h // 2:, w // 2:].max())]
        assert tons == sorted(tons) and tons[0] > 0 and tons == [40, 80, 120, 160]
    finally:
        prn.stop()


def test_grade_do_formato():
    assert len(J.cell_rects("STANDARD\\2,3")) == 6
    assert J.cell_rects("STANDARD\\1,1") == [(0.0, 0.0, 1.0, 1.0)]
    assert len(J.cell_rects("ROW\\1,2")) == 3 and len(J.cell_rects("COL\\2,2")) == 4
    assert J.box_count("STANDARD\\4,5") == 20
    # ROW\1,2: a primeira linha tem uma imagem (largura cheia), a segunda tem duas
    assert J.cell_rects("ROW\\1,2")[0] == (0.0, 0.0, 1.0, 0.5)
    assert J.cell_rects("ROW\\1,2")[2][2] == pytest.approx(0.5)
