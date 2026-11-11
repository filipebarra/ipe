"""0.100.11: o filme montado fora do compositor (o do navegador) saindo pelos mesmos caminhos do Ipê.

As folhas são desenhadas pelo mesmo código do compositor (`ui/film/render.render_sheet_image`: célula a célula,
com janela, zoom, deslocamento, giro, espelho, medidas, textos e cabeçalho) e vão para: PDF (baixado ou numa pasta),
imagens numa pasta, uma impressora do computador (pelo nome, sem janela) ou uma impressora DICOM (Basic Print).

Usa Qt de interface (QWidget, QPrinter): tudo aqui roda na linha principal (pelo servidor, via `central/ponte`).
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from ipe.printing.film import PAPERS, Film, Sheet

log = logging.getLogger(__name__)


def _layout(sheet: Sheet):
    from PySide6.QtCore import QMarginsF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize
    w, h, _id = PAPERS.get(sheet.paper, PAPERS["A4"])
    size = QPageSize(QSizeF(w, h), QPageSize.Millimeter, sheet.paper, QPageSize.ExactMatch)
    return QPageLayout(size, QPageLayout.Landscape if sheet.landscape else QPageLayout.Portrait,
                       QMarginsF(0, 0, 0, 0))


class Saida:
    """As folhas de um filme: imagens, PDF, impressora do computador e páginas para a impressora DICOM."""

    def __init__(self, film: Film, repo, settings, cache=None):
        from ipe.imaging.series import FrameCache
        from ipe.ui.film.render import FrameSource
        self.film, self.repo, self.settings = film, repo, settings
        self.cache = cache if cache is not None else FrameCache(256)
        self.src = FrameSource(repo)

    def indices(self, folhas: list[int] | None) -> list[int]:
        n = len(self.film.sheets)
        return [i for i in (folhas if folhas else range(n)) if 0 <= i < n]

    def imagem(self, i: int, dpi: float, cinza: bool = False):
        from ipe.ui.film.render import render_sheet_image
        return render_sheet_image(self.film, i, self.src, self.cache, self.settings, dpi, cinza)

    def png(self, i: int, dpi: float = 60) -> bytes:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        img = self.imagem(i, dpi)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        buf.close()
        return bytes(ba)

    def _pintar(self, device, dpi: float, folhas: list[int]) -> int:
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainter
        p = None
        n = 0
        try:
            for i in self.indices(folhas):
                device.setPageLayout(_layout(self.film.sheets[i]))
                if p is None:
                    p = QPainter(device)
                    if not p.isActive():
                        raise RuntimeError("Não foi possível iniciar a impressão.")
                else:
                    device.newPage()
                img = self.imagem(i, dpi)
                alvo = QRectF(p.viewport())
                k = min(alvo.width() / img.width(), alvo.height() / img.height())
                w, h = img.width() * k, img.height() * k
                p.drawImage(QRectF(alvo.x() + (alvo.width() - w) / 2, alvo.y() + (alvo.height() - h) / 2, w, h), img)
                n += 1
        finally:
            if p is not None:
                p.end()
        return n

    def pdf(self, folhas: list[int] | None = None, dpi: int | None = None) -> bytes:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtGui import QPdfWriter
        dpi = int(dpi or self.settings.get("printing.pdf_dpi", 200) or 200)
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        w = QPdfWriter(buf)
        w.setResolution(dpi)
        w.setTitle(self.film.name)
        w.setCreator("Ipê")
        self._pintar(w, dpi, folhas or [])
        del w
        buf.close()
        return bytes(ba)

    def impressora(self, nome: str, folhas: list[int] | None = None) -> int:
        """Numa impressora deste computador, pelo nome (sem a janela de imprimir)."""
        from PySide6.QtPrintSupport import QPrinter, QPrinterInfo
        if nome not in QPrinterInfo.availablePrinterNames():
            raise KeyError(f"impressora não encontrada neste computador: {nome}")
        pr = QPrinter(QPrinterInfo.printerInfo(nome), QPrinter.HighResolution)
        pr.setDocName(self.film.name)
        dpi = min(300, max(150, pr.resolution()))
        return self._pintar(pr, dpi, folhas or [])

    def paginas_dicom(self, cfg, folhas: list[int] | None = None):
        from ipe.printing.dicom_print import PageImage
        pages = []
        for i in self.indices(folhas):
            img = self.imagem(i, cfg.dpi, cinza=not cfg.color)
            sheet = self.film.sheets[i]
            if cfg.color:
                img = img.convertToFormat(img.Format.Format_RGB888)
                arr = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())
                arr = arr[:, :img.width() * 3].reshape(img.height(), img.width(), 3).copy()
            else:
                arr = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())
                arr = arr[:, :img.width()].copy()
            pages.append(PageImage(arr, PAPERS.get(sheet.paper, PAPERS["A4"])[2], sheet.landscape))
        return pages

    def numa_pasta(self, pasta: str, tipo: str, fmt: str = "png", dpi: int = 150,
                   folhas: list[int] | None = None) -> list[str]:
        """PDF (tipo "pdf") ou imagens ("images") na pasta de um destino de impressão."""
        from datetime import datetime
        p = Path(pasta)
        p.mkdir(parents=True, exist_ok=True)
        base = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in self.film.name).strip() or "filme"
        base = f"{base}_{datetime.now():%Y%m%d_%H%M%S}"
        if tipo == "pdf":
            alvo = p / f"{base}.pdf"
            alvo.write_bytes(self.pdf(folhas))
            return [str(alvo)]
        ext = ".jpg" if str(fmt).lower() in ("jpg", "jpeg") else ".png"
        out = []
        for i in self.indices(folhas):
            alvo = p / f"{base}_{i + 1:02d}{ext}"
            self.imagem(i, dpi).save(str(alvo), quality=92)
            out.append(str(alvo))
        return out
