"""Para onde vai um trabalho de impressão: PDF, impressora do computador, impressora DICOM
ou imagens numa pasta.

O mesmo caminho serve para o que chegou das modalidades e para os filmes montados aqui.
Nada sai sozinho: quem manda é você (ou, mais adiante, uma regra).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ipe.printing import jobs as J
from ipe.printing import layout as L
from ipe.printing.dicom_print import PrintError, PrinterConfig

log = logging.getLogger(__name__)

KINDS = {"pdf": "PDF numa pasta", "system": "Impressora do computador",
         "dicom": "Impressora DICOM", "images": "Imagens numa pasta"}


@dataclass
class Destination:
    """Um destino configurado (fica em Preferências → Impressões)."""
    name: str = "Destino"
    kind: str = "pdf"                 # pdf | system | dicom | images
    folder: str = ""                  # pdf, images
    printer: str = ""                 # system: nome da impressora ("" = a padrão)
    dicom_printer: str = ""           # dicom: nome da impressora DICOM cadastrada
    dpi: int = 150
    fmt: str = "png"                  # images: png | jpg
    template: str = ""                # modelo de folha ("" = a folha como veio)

    def label(self) -> str:
        detalhe = {"pdf": self.folder, "images": self.folder,
                   "system": self.printer or "impressora padrão",
                   "dicom": self.dicom_printer}.get(self.kind, "")
        return f"{self.name} — {KINDS.get(self.kind, self.kind)}" + (f" ({detalhe})" if detalhe else "")

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "folder": self.folder, "printer": self.printer,
                "dicom_printer": self.dicom_printer, "dpi": self.dpi, "fmt": self.fmt,
                "template": self.template}

    @staticmethod
    def from_dict(d: dict) -> "Destination":
        known = Destination.__dataclass_fields__
        return Destination(**{k: v for k, v in (d or {}).items() if k in known})


def all_destinations(settings) -> list[Destination]:
    return [Destination.from_dict(d) for d in (settings.get("printing.destinations", []) or [])]


def save_destinations(settings, dests: list[Destination]) -> None:
    settings.set("printing.destinations", [d.to_dict() for d in dests])
    settings.save()


def find_destination(settings, name: str) -> Destination | None:
    for d in all_destinations(settings):
        if d.name == name:
            return d
    return None


# ---------------------------------------------------------------------------
# desenho
# ---------------------------------------------------------------------------

def sheet_qimage(folder: Path | str, film: J.FilmBox, dpi: int = 150):
    """A folha montada como QImage, na resolução pedida."""
    from PySide6.QtGui import QImage

    mm_w, mm_h = J.sheet_mm(film)
    largura = max(200, int(round(mm_w / 25.4 * max(50, int(dpi)))))
    px = J.compose_sheet(folder, film, width=largura)
    if px.ndim == 3:
        h, w, _ = px.shape
        img = QImage(px.tobytes(), w, h, 3 * w, QImage.Format_RGB888)
    else:
        h, w = px.shape
        img = QImage(px.tobytes(), w, h, w, QImage.Format_Grayscale8)
    img = img.copy()                       # solta do buffer do numpy
    img.setDotsPerMeterX(round(dpi / 0.0254))
    img.setDotsPerMeterY(round(dpi / 0.0254))
    return img


def job_sheet(job: J.PrintJob, folder, index: int, dpi: int = 150, template=None):
    """A folha pronta para sair: com o modelo aplicado, ou como veio da modalidade."""
    if template is not None:
        return L.render_job_sheet(job, folder, index, template, dpi)
    return sheet_qimage(folder, job.films[index], dpi)


def base_name(job: J.PrintJob) -> str:
    quem = job.patient_name or job.label or job.calling_ae or "impressao"
    quem = "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in quem).strip()
    return f"{job.when().strftime('%Y-%m-%d_%H%M')}_{quem or 'impressao'}"[:80]


def _page_layout(film: J.FilmBox):
    from PySide6.QtCore import QMarginsF, QSizeF
    from PySide6.QtGui import QPageLayout, QPageSize

    mm_w, mm_h = J.sheet_mm(film)
    if film.landscape:
        mm_w, mm_h = mm_h, mm_w            # o QPageSize é sempre em retrato; a orientação vai à parte
    size = QPageSize(QSizeF(mm_w, mm_h), QPageSize.Millimeter, film.film_size or "Filme",
                     QPageSize.ExactMatch)
    return QPageLayout(size, QPageLayout.Landscape if film.landscape else QPageLayout.Portrait,
                       QMarginsF(0, 0, 0, 0))


def _paint(device, job: J.PrintJob, folder: Path | str, dpi: int, template=None) -> None:
    """Desenha as folhas num QPdfWriter/QPrinter (uma página por folha)."""
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPainter

    pintor = None
    try:
        for i, film in enumerate(job.films):
            if not film.filled():
                continue
            device.setPageLayout(_page_layout(film))
            if pintor is None:
                pintor = QPainter(device)
                if not pintor.isActive():
                    raise PrintError("Não foi possível iniciar a impressão.")
            else:
                device.newPage()
            img = job_sheet(job, folder, i, dpi, template)
            alvo = QRectF(pintor.viewport())
            k = min(alvo.width() / img.width(), alvo.height() / img.height())
            w, h = img.width() * k, img.height() * k
            pintor.drawImage(QRectF(alvo.x() + (alvo.width() - w) / 2, alvo.y() + (alvo.height() - h) / 2,
                                    w, h), img)
    finally:
        if pintor is not None:
            pintor.end()


# ---------------------------------------------------------------------------
# envio
# ---------------------------------------------------------------------------

def to_pdf(job: J.PrintJob, folder: Path | str, dest: Destination, template=None) -> str:
    from PySide6.QtGui import QPdfWriter

    pasta = Path(dest.folder or Path.home())
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = _livre(pasta / f"{base_name(job)}.pdf")
    escritor = QPdfWriter(str(caminho))
    escritor.setResolution(int(dest.dpi or 150))
    escritor.setTitle(job.title())
    escritor.setCreator("Ipê")
    _paint(escritor, job, folder, int(dest.dpi or 150), template)
    return str(caminho)


def to_images(job: J.PrintJob, folder: Path | str, dest: Destination, template=None) -> str:
    pasta = Path(dest.folder or Path.home())
    pasta.mkdir(parents=True, exist_ok=True)
    ext = "jpg" if str(dest.fmt).lower().startswith("j") else "png"
    saidas = []
    for i, film in enumerate(job.films):
        if not film.filled():
            continue
        img = job_sheet(job, folder, i, int(dest.dpi or 150), template)
        caminho = _livre(pasta / f"{base_name(job)}_folha{i + 1}.{ext}")
        if not img.save(str(caminho)):
            raise PrintError(f"Não foi possível gravar {caminho.name}.")
        saidas.append(str(caminho))
    if not saidas:
        raise PrintError("O trabalho não tem imagens.")
    return saidas[0] if len(saidas) == 1 else f"{len(saidas)} arquivos em {pasta}"


def to_system_printer(job: J.PrintJob, folder: Path | str, dest: Destination, template=None) -> str:
    """Imprime numa impressora comum. Precisa rodar na thread da interface."""
    from PySide6.QtPrintSupport import QPrinter, QPrinterInfo

    impressora = QPrinter(QPrinter.HighResolution)
    if dest.printer:
        info = QPrinterInfo.printerInfo(dest.printer)
        if info.isNull():
            raise PrintError(f"A impressora “{dest.printer}” não está instalada neste computador.")
        impressora.setPrinterName(dest.printer)
    if not impressora.isValid():
        raise PrintError("Não há impressora instalada neste computador.")
    impressora.setDocName(job.title())
    dpi = min(300, max(150, int(dest.dpi or impressora.resolution())))
    _paint(impressora, job, folder, dpi, template)
    return impressora.printerName() or "impressora padrão"


def to_dicom_printer(job: J.PrintJob, folder: Path | str, dest: Destination, settings,
                     local_ae: str = "", template=None) -> str:
    from ipe.printing.dicom_print import PageImage, dicom_print, dicom_print_job

    cfgs = [PrinterConfig.from_dict(d) for d in (settings.get("printing.dicom_printers", []) or [])]
    alvo = next((c for c in cfgs if c.name == dest.dicom_printer), None)
    if alvo is None:
        raise PrintError(f"A impressora DICOM “{dest.dicom_printer}” não está cadastrada.")
    if template is None:
        r = dicom_print_job(alvo, job, folder, local_ae=local_ae)      # como veio, caixa por caixa
    else:
        paginas = []
        for i, film in enumerate(job.films):
            if not film.filled():
                continue
            img = job_sheet(job, folder, i, int(dest.dpi or 150), template)
            paginas.append(PageImage(pixels=_cinza(img), film_size=film.film_size or "14INX17IN",
                                     landscape=film.landscape))
        r = dicom_print(alvo, paginas, local_ae=local_ae)
    extra = f" ({'; '.join(r.warnings)})" if r.warnings else ""
    return f"{alvo.name}: {r.pages} folha(s){extra}"


def _cinza(img):
    """QImage -> numpy 8 bits em escala de cinza (para mandar à impressora DICOM)."""
    import numpy as np
    from PySide6.QtGui import QImage

    g = img.convertToFormat(QImage.Format_Grayscale8)
    largura, altura, passo = g.width(), g.height(), g.bytesPerLine()
    a = np.frombuffer(bytes(g.constBits()), dtype=np.uint8)[:altura * passo]
    return np.ascontiguousarray(a.reshape(altura, passo)[:, :largura])


def send(job: J.PrintJob, folder: Path | str, dest: Destination, settings=None,
         local_ae: str = "", template: str = "") -> str:
    """Manda o trabalho para o destino; devolve uma frase curta do que aconteceu.

    `template` (ou o modelo do próprio destino) põe logo, nome da clínica e cabeçalho na folha.
    """
    modelo = None
    nome_modelo = template or dest.template
    if nome_modelo and settings is not None:
        modelo = L.find_template(settings, nome_modelo)
        if modelo is None:
            log.warning("Modelo de folha “%s” não existe mais; saindo como veio", nome_modelo)
    if dest.kind == "pdf":
        return f"PDF salvo: {to_pdf(job, folder, dest, modelo)}"
    if dest.kind == "images":
        return f"Imagem salva: {to_images(job, folder, dest, modelo)}"
    if dest.kind == "system":
        return f"Enviado para {to_system_printer(job, folder, dest, modelo)}."
    if dest.kind == "dicom":
        if settings is None:
            raise PrintError("Sem as configurações das impressoras DICOM.")
        return f"Enviado para {to_dicom_printer(job, folder, dest, settings, local_ae, modelo)}."
    raise PrintError(f"Destino desconhecido: {dest.kind}")


def needs_gui(dest: Destination) -> bool:
    """A impressora do computador (e o PDF, pelo Qt) desenha na thread da interface."""
    return dest.kind in ("system", "pdf", "images")


def _livre(caminho: Path) -> Path:
    """Não sobrescreve nada: acrescenta (2), (3)… se já existir."""
    if not caminho.exists():
        return caminho
    for n in range(2, 500):
        alt = caminho.with_name(caminho.stem + " (" + str(n) + ")" + caminho.suffix)
        if not alt.exists():
            return alt
    return caminho.with_name(caminho.stem + "_" + datetime.now().strftime("%H%M%S") + caminho.suffix)
