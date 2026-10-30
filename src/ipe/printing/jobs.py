"""Trabalhos de impressão recebidos pela impressora DICOM (Print SCP).

O que chega da modalidade é a folha já pronta: os parâmetros do filme (grade, tamanho,
polaridade…) e os pixels de cada caixa de imagem. Não vem nome nem ID do paciente — o
padrão não manda nada disso (fica queimado nos pixels). O pouco que às vezes vem está no
rótulo da sessão (Film Session Label) e no Owner ID.

Cada trabalho fica numa pasta: `trabalho.json` + uma imagem DICOM por caixa (os pixels
originais, sem mexer). A folha montada é desenhada na hora, a partir dessas caixas.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

FOLDER = "Impressoes"                  # pasta dos trabalhos, dentro dos dados do programa
SC_CLASS = "1.2.840.10008.5.1.4.1.1.7"     # Secondary Capture Image Storage

# tamanho de cada filme em mm (retrato), pelo FilmSizeID do padrão
FILM_MM: dict[str, tuple[float, float]] = {
    "8INX10IN": (203.2, 254.0), "8_5INX11IN": (215.9, 279.4), "10INX12IN": (254.0, 304.8),
    "10INX14IN": (254.0, 355.6), "11INX14IN": (279.4, 355.6), "11INX17IN": (279.4, 431.8),
    "14INX14IN": (355.6, 355.6), "14INX17IN": (355.6, 431.8), "24CMX24CM": (240.0, 240.0),
    "24CMX30CM": (240.0, 300.0), "A4": (210.0, 297.0), "A3": (297.0, 420.0),
}


# ---------------------------------------------------------------------------
# modelo
# ---------------------------------------------------------------------------

@dataclass
class ImageBox:
    """Uma caixa de imagem da folha (Basic Grayscale/Color Image Box)."""
    position: int = 1
    polarity: str = ""                 # NORMAL | REVERSE
    magnification: str = ""
    requested_size: float = 0.0        # largura pedida em mm (tamanho real)
    rows: int = 0
    columns: int = 0
    samples: int = 1
    photometric: str = "MONOCHROME2"
    bits_stored: int = 8
    file: str = ""                     # arquivo dentro da pasta do trabalho

    @staticmethod
    def from_dict(d: dict) -> "ImageBox":
        known = ImageBox.__dataclass_fields__
        return ImageBox(**{k: v for k, v in (d or {}).items() if k in known})


@dataclass
class FilmBox:
    """Uma folha (Basic Film Box) com suas caixas de imagem."""
    display_format: str = "STANDARD\\1,1"
    orientation: str = "PORTRAIT"
    film_size: str = ""
    magnification: str = ""
    border: str = ""                   # BLACK | WHITE | densidade
    empty: str = ""
    min_density: int = 0
    max_density: int = 0
    trim: str = ""
    config: str = ""
    annotation_format: str = ""
    boxes: list[ImageBox] = field(default_factory=list)
    annotations: list[dict] = field(default_factory=list)   # {"position": n, "text": "..."}

    @property
    def landscape(self) -> bool:
        return self.orientation.upper().startswith("LAND")

    def filled(self) -> list[ImageBox]:
        return [b for b in self.boxes if b.file]

    def grid(self) -> tuple[int, int]:
        """(linhas, colunas) quando o formato é uma grade regular."""
        r = re.match(r"STANDARD\\?(\d+),(\d+)", self.display_format.replace("\\\\", "\\"))
        if r:
            return int(r.group(2)), int(r.group(1))       # STANDARD\colunas,linhas
        n = max(1, len(self.boxes))
        cols = int(np.ceil(np.sqrt(n)))
        return int(np.ceil(n / cols)), cols

    @staticmethod
    def from_dict(d: dict) -> "FilmBox":
        known = FilmBox.__dataclass_fields__
        opts = {k: v for k, v in (d or {}).items() if k in known and k not in ("boxes", "annotations")}
        return FilmBox(boxes=[ImageBox.from_dict(b) for b in (d or {}).get("boxes", [])],
                       annotations=list((d or {}).get("annotations", [])), **opts)


@dataclass
class PrintJob:
    """Uma sessão de impressão inteira (o que a modalidade mandou de uma vez)."""
    uid: str = ""
    received_at: str = ""              # ISO
    calling_ae: str = ""
    called_ae: str = ""
    remote_host: str = ""
    server: str = ""                   # nome do servidor de impressão que recebeu
    copies: int = 1
    priority: str = ""
    medium: str = ""
    destination: str = ""
    label: str = ""                    # Film Session Label — às vezes traz nome/ID
    owner_id: str = ""
    films: list[FilmBox] = field(default_factory=list)
    patient_name: str = ""
    patient_id: str = ""
    id_source: str = ""                # label | manual | exame | (vazio = desconhecido)
    study_uid: str = ""                # exame criado no banco com as folhas montadas
    modality: str = ""                 # 0.84: do exame do paciente ou da origem (printing.modalidade)
    ultima_folha_em: str = ""          # 0.99.6: ISO da última folha juntada (printing.juntar)
    juntados: list = field(default_factory=list)   # uids dos trabalhos que viraram páginas deste

    # -------------------------------------------------------------- resumo
    @property
    def sheets(self) -> int:
        return len(self.films)

    @property
    def images(self) -> int:
        return sum(len(f.filled()) for f in self.films)

    @property
    def film_size(self) -> str:
        for f in self.films:
            if f.film_size:
                return f.film_size
        return ""

    def when(self) -> datetime:
        try:
            return datetime.fromisoformat(self.received_at)
        except ValueError:
            return datetime.now()

    def title(self) -> str:
        who = self.patient_name or self.label or "(sem identificação)"
        return f"{who}, de {self.calling_ae or '?'}"

    # -------------------------------------------------------------- json
    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "PrintJob":
        known = PrintJob.__dataclass_fields__
        opts = {k: v for k, v in (d or {}).items() if k in known and k != "films"}
        return PrintJob(films=[FilmBox.from_dict(f) for f in (d or {}).get("films", [])], **opts)


# ---------------------------------------------------------------------------
# grade da folha
# ---------------------------------------------------------------------------

def box_count(display_format: str) -> int:
    """Quantas caixas de imagem a folha tem, pelo Image Display Format."""
    return len(cell_rects(display_format, 1))


def cell_rects(display_format: str, n_boxes: int = 1) -> list[tuple[float, float, float, float]]:
    """Retângulos (x, y, largura, altura) de cada caixa, em fração da folha, na ordem das posições."""
    fmt = (display_format or "").replace("\\\\", "\\").strip().upper()
    head, _sep, rest = fmt.partition("\\")
    nums = [int(x) for x in re.findall(r"\d+", rest)]
    out: list[tuple[float, float, float, float]] = []
    if head == "STANDARD" and len(nums) >= 2:
        cols, rows = max(1, nums[0]), max(1, nums[1])
        for r in range(rows):
            for c in range(cols):
                out.append((c / cols, r / rows, 1 / cols, 1 / rows))
        return out
    if head == "ROW" and nums:
        rows = len(nums)
        for r, cols in enumerate(nums):
            cols = max(1, cols)
            for c in range(cols):
                out.append((c / cols, r / rows, 1 / cols, 1 / rows))
        return out
    if head == "COL" and nums:
        cols = len(nums)
        for c, rows in enumerate(nums):
            rows = max(1, rows)
            for r in range(rows):
                out.append((c / cols, r / rows, 1 / cols, 1 / rows))
        return out
    if head in ("SLIDE", "SUPERSLIDE") or not nums:
        return [(0.0, 0.0, 1.0, 1.0)]
    # CUSTOM\i e o que não conhecemos: grade quadrada com o que veio
    n = max(1, nums[0] if head == "CUSTOM" else n_boxes)
    cols = int(np.ceil(np.sqrt(n)))
    rows = int(np.ceil(n / cols))
    for r in range(rows):
        for c in range(cols):
            out.append((c / cols, r / rows, 1 / cols, 1 / rows))
    return out[:n]


# ---------------------------------------------------------------------------
# pasta do trabalho
# ---------------------------------------------------------------------------

def job_dir(root: Path | str, uid: str) -> Path:
    return Path(root) / _safe(uid)


def _safe(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(name))[:96] or "trabalho"


def save(job: PrintJob, root: Path | str) -> Path:
    d = job_dir(root, job.uid)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "trabalho.part"
    tmp.write_text(json.dumps(job.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(d / "trabalho.json")
    return d


def load(folder: Path | str) -> PrintJob | None:
    p = Path(folder) / "trabalho.json"
    if not p.exists():
        return None
    try:
        return PrintJob.from_dict(json.loads(p.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001
        log.exception("Trabalho de impressão ilegível: %s", p)
        return None


# ---------------------------------------------------------------------------
# pixels
# ---------------------------------------------------------------------------

def write_box(folder: Path | str, item, index: int, job: PrintJob | None = None) -> ImageBox:
    """Grava o item da sequência de imagem (o que a modalidade mandou) como DICOM na pasta.

    Guardamos os pixels exatamente como vieram, dentro de um Secondary Capture, para poder
    reimprimir sem perda e remontar a folha depois.
    """
    import pydicom
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    ds = Dataset()
    for tag in ("SamplesPerPixel", "PhotometricInterpretation", "Rows", "Columns", "PixelAspectRatio",
                "BitsAllocated", "BitsStored", "HighBit", "PixelRepresentation", "PlanarConfiguration"):
        if tag in item:
            setattr(ds, tag, getattr(item, tag))
    ds.PixelData = item.PixelData
    ds.SOPClassUID = SC_CLASS
    ds.SOPInstanceUID = generate_uid()
    ds.Modality = "OT"
    ds.ConversionType = "WSD"
    ds.PatientName = (job.patient_name if job and job.patient_name else "IMPRESSAO") or "IMPRESSAO"
    ds.PatientID = (job.patient_id if job and job.patient_id else "") or ""
    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    name = f"caixa_{index:03d}.dcm"
    path = folder / name
    pydicom.dcmwrite(path, ds, enforce_file_format=True)
    return ImageBox(rows=int(getattr(ds, "Rows", 0)), columns=int(getattr(ds, "Columns", 0)),
                    samples=int(getattr(ds, "SamplesPerPixel", 1)),
                    photometric=str(getattr(ds, "PhotometricInterpretation", "MONOCHROME2")),
                    bits_stored=int(getattr(ds, "BitsStored", 8)), file=name)


def box_pixels(folder: Path | str, box: ImageBox) -> np.ndarray | None:
    """Pixels da caixa já em cinza/RGB de 8 bits, prontos para desenhar (0 = preto)."""
    import pydicom
    if not box.file:
        return None
    path = Path(folder) / box.file
    if not path.exists():
        return None
    ds = pydicom.dcmread(path)
    a = ds.pixel_array
    if a.ndim == 3 and a.shape[-1] == 3:
        return a.astype(np.uint8) if a.dtype == np.uint8 else (a >> max(0, box.bits_stored - 8)).astype(np.uint8)
    a = a.astype(np.float32)
    top = float((1 << max(1, int(box.bits_stored))) - 1)
    g = np.clip(a / top, 0.0, 1.0)
    if str(box.photometric).upper() == "MONOCHROME1":
        g = 1.0 - g
    if str(box.polarity).upper() == "REVERSE":
        g = 1.0 - g
    return (g * 255.0 + 0.5).astype(np.uint8)


def sheet_mm(film: FilmBox) -> tuple[float, float]:
    """Tamanho da folha em mm, já na orientação certa (padrão: A4)."""
    w, h = FILM_MM.get(str(film.film_size or "").upper().strip(), FILM_MM["A4"])
    return (h, w) if film.landscape else (w, h)


def _background(film: FilmBox) -> int:
    return 255 if str(film.border or film.empty).upper().startswith("WHITE") else 0


def compose_sheet(folder: Path | str, film: FilmBox, width: int = 1240) -> np.ndarray:
    """Monta a folha como a impressora montaria: a grade do Image Display Format, cada imagem
    encaixada na sua célula sem distorcer. Devolve cinza de 8 bits (ou RGB se houver cor)."""
    rects = cell_rects(film.display_format, len(film.boxes))
    mm_w, mm_h = sheet_mm(film)
    w = max(64, int(width))
    h = max(64, int(round(w * mm_h / mm_w)))
    color = any(b.samples == 3 for b in film.boxes)
    page = np.full((h, w, 3) if color else (h, w), _background(film), dtype=np.uint8)
    for i, box in enumerate(film.boxes):
        px = box_pixels(folder, box)
        if px is None:
            continue
        pos = int(box.position or (i + 1)) - 1
        if not 0 <= pos < len(rects):
            pos = min(i, len(rects) - 1)
        x0, y0, cw, ch = rects[pos]
        cx, cy = int(x0 * w), int(y0 * h)
        cwp, chp = max(1, int(cw * w)), max(1, int(ch * h))
        if color and px.ndim == 2:
            px = np.stack([px] * 3, axis=-1)
        if not color and px.ndim == 3:
            px = px[..., :3].mean(axis=2).astype(np.uint8)
        k = min(cwp / px.shape[1], chp / px.shape[0])
        nw, nh = max(1, int(px.shape[1] * k)), max(1, int(px.shape[0] * k))
        ys = (np.arange(nh) * px.shape[0] / nh).astype(int).clip(0, px.shape[0] - 1)
        xs = (np.arange(nw) * px.shape[1] / nw).astype(int).clip(0, px.shape[1] - 1)
        small = px[ys][:, xs]
        oy, ox = cy + (chp - nh) // 2, cx + (cwp - nw) // 2
        page[oy:oy + nh, ox:ox + nw] = small
    return page


# ---------------------------------------------------------------------------
# virar exame no banco (Secondary Capture)
# ---------------------------------------------------------------------------

def sheet_dataset(job: PrintJob, index: int, pixels: np.ndarray, study_uid: str, series_uid: str):
    """A folha montada como imagem DICOM, para entrar na lista de exames."""
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid

    when = job.when()
    ds = Dataset()
    ds.SOPClassUID = SC_CLASS
    ds.SOPInstanceUID = generate_uid()
    ds.StudyInstanceUID, ds.SeriesInstanceUID = study_uid, series_uid
    ds.PatientName = job.patient_name or f"IMPRESSAO^{job.calling_ae or 'DICOM'}"
    ds.PatientID = job.patient_id or job.uid[-16:]
    ds.StudyDate = ds.SeriesDate = ds.ContentDate = when.strftime("%Y%m%d")
    ds.StudyTime = ds.SeriesTime = ds.ContentTime = when.strftime("%H%M%S")
    ds.AccessionNumber = ""
    ds.Modality = "OT"
    ds.ConversionType = "WSD"
    ds.StudyDescription = f"Impressão recebida de {job.calling_ae or '?'}"
    ds.SeriesDescription = (job.label or "Trabalho de impressão")[:64]
    ds.StudyID = "PRINT"
    ds.SeriesNumber = 1
    ds.InstanceNumber = index + 1
    ds.Manufacturer = "Ipe"
    if pixels.ndim == 3:
        ds.SamplesPerPixel, ds.PhotometricInterpretation, ds.PlanarConfiguration = 3, "RGB", 0
        ds.Rows, ds.Columns = int(pixels.shape[0]), int(pixels.shape[1])
    else:
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.Rows, ds.Columns = int(pixels.shape[0]), int(pixels.shape[1])
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 8, 8, 7, 0
    ds.PixelData = np.ascontiguousarray(pixels.astype(np.uint8)).tobytes()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.SourceApplicationEntityTitle = (job.calling_ae or "DICOMPRINT")[:16]
    return ds


# ---------------------------------------------------------------------------
# identificação do paciente (o que dá para tirar do que chegou)
# ---------------------------------------------------------------------------

_ID_RE = re.compile(r"(?P<id>\b\d{4,}\b)")


def guess_patient(job: PrintJob) -> tuple[str, str, str]:
    """Tenta nome e ID a partir do rótulo da sessão e do Owner ID.

    Algumas modalidades escrevem ali o nome, o ID ou o accession; a maioria não escreve nada.
    Devolve (nome, id, de onde veio).
    """
    texto = " ".join(x for x in (job.label, job.owner_id) if x).strip()
    if not texto:
        return "", "", ""
    partes = [p.strip() for p in re.split(r"[|;,/]+", texto) if p.strip()]
    nome, ident = "", ""
    for p in partes:
        if not ident:
            m = _ID_RE.search(p)
            if m and not any(ch.isalpha() for ch in p.replace(" ", "")):
                ident = m.group("id")
                continue
        if not nome and any(ch.isalpha() for ch in p) and len(p) > 2:
            nome = p
    if not nome and not ident:
        return "", "", ""
    return nome, ident, "label"
