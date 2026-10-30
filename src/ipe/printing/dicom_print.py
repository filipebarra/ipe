"""Impressão DICOM (Print Management SCU): cada folha do filme vai como uma imagem
(formato STANDARD\\1,1) numa Film Box, em escala de cinza ou colorida."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

import numpy as np
from pydicom.dataset import Dataset
from pydicom.uid import generate_uid
from pynetdicom import AE
from pynetdicom.sop_class import (
    BasicColorImageBox, BasicColorPrintManagementMeta, BasicFilmBox, BasicFilmSession,
    BasicGrayscaleImageBox, BasicGrayscalePrintManagementMeta, Printer, PrinterInstance, Verification,
)

log = logging.getLogger(__name__)

MEDIUMS = ["BLUE FILM", "CLEAR FILM", "PAPER", "MAMMO CLEAR FILM", "MAMMO BLUE FILM"]
DESTINATIONS = ["MAGAZINE", "PROCESSOR"]
MAGNIFICATIONS = ["CUBIC", "BILINEAR", "REPLICATE", "NONE"]
FILM_SIZES = ["", "8INX10IN", "8_5INX11IN", "10INX12IN", "10INX14IN", "11INX14IN", "11INX17IN",
              "14INX14IN", "14INX17IN", "24CMX24CM", "24CMX30CM", "A4", "A3"]


class PrintError(Exception):
    pass


@dataclass
class PrinterConfig:
    name: str = "Impressora DICOM"
    ae_title: str = ""
    host: str = ""
    port: int = 104
    calling_ae: str = ""            # vazio = AE deste programa
    film_size: str = ""             # vazio = o tamanho de cada folha
    medium: str = "BLUE FILM"
    destination: str = "MAGAZINE"
    magnification: str = "CUBIC"
    copies: int = 1
    dpi: int = 150                  # resolução da imagem enviada
    color: bool = False
    min_density: int | None = None
    max_density: int | None = None

    @staticmethod
    def from_dict(d: dict) -> "PrinterConfig":
        known = PrinterConfig.__dataclass_fields__
        return PrinterConfig(**{k: v for k, v in (d or {}).items() if k in known})


@dataclass
class PageImage:
    pixels: np.ndarray               # uint8, HxW (cinza) ou HxWx3 (RGB)
    film_size: str = "14INX17IN"
    landscape: bool = False


@dataclass
class PrintResult:
    pages: int = 0
    warnings: list[str] = field(default_factory=list)


_OK_WARN = {0x0000, 0x0107, 0x0116, 0xB600, 0xB602, 0xB603, 0xB604, 0xB605, 0xB609, 0xB60A}


def _check(status: Dataset, what: str, result: PrintResult) -> None:
    if status is None or "Status" not in status:
        raise PrintError(f"A impressora não respondeu ({what}).")
    code = int(status.Status)
    if code not in _OK_WARN:
        comment = str(status.get("ErrorComment", "") or "")
        raise PrintError(f"A impressora recusou: {what} (status 0x{code:04X}) {comment}".strip())
    if code != 0:
        result.warnings.append(f"{what}: aviso 0x{code:04X}")


def _ae(calling: str, color: bool, timeout: int) -> AE:
    ae = AE(ae_title=calling or "DICOMVIEWER")
    ae.acse_timeout = ae.dimse_timeout = ae.network_timeout = timeout
    ae.add_requested_context(BasicColorPrintManagementMeta if color else BasicGrayscalePrintManagementMeta)
    ae.add_requested_context(Verification)
    return ae


def _associate(cfg: PrinterConfig, local_ae: str, timeout: int):
    ae = _ae(cfg.calling_ae or local_ae, cfg.color, timeout)
    assoc = ae.associate(cfg.host, int(cfg.port), ae_title=cfg.ae_title)
    if not assoc.is_established:
        if assoc.is_rejected:
            raise PrintError(f"{cfg.name} recusou a conexão (AE de origem não autorizado ou AE da impressora "
                             f"“{cfg.ae_title}” errado).")
        raise PrintError(f"Sem resposta de {cfg.name} ({cfg.host}:{cfg.port}).")
    meta = BasicColorPrintManagementMeta if cfg.color else BasicGrayscalePrintManagementMeta
    ok = any(cx.abstract_syntax == meta for cx in assoc.accepted_contexts)
    if not ok:
        assoc.release()
        raise PrintError(f"{cfg.name} não aceita impressão {'colorida' if cfg.color else 'em escala de cinza'}.")
    return assoc, meta


def printer_status(cfg: PrinterConfig, local_ae: str = "", timeout: int = 15) -> str:
    """Testa a impressora: associação + estado (N-GET no Printer, se ela responder)."""
    assoc, meta = _associate(cfg, local_ae, timeout)
    try:
        try:
            status, attrs = assoc.send_n_get([0x21100010, 0x21100020, 0x21100030], Printer, PrinterInstance,
                                             meta_uid=meta)
            if status is not None and int(status.get("Status", 0xFFFF)) == 0 and attrs is not None:
                st = str(attrs.get("PrinterStatus", "") or "?")
                info = str(attrs.get("PrinterStatusInfo", "") or "")
                name = str(attrs.get("PrinterName", "") or "")
                return f"Conectou. Estado: {st} {info} {name}".strip()
        except Exception as e:  # noqa: BLE001
            log.debug("N-GET Printer falhou: %s", e)
        return "Conectou (a impressora não informou o estado)."
    finally:
        assoc.release()


def _image_item(pix: np.ndarray, color: bool) -> Dataset:
    img = Dataset()
    if color:
        rgb = pix if pix.ndim == 3 else np.stack([pix] * 3, axis=-1)
        img.SamplesPerPixel = 3
        img.PhotometricInterpretation = "RGB"
        img.PlanarConfiguration = 1                     # exigido pelo Basic Color Image Box
        data = np.ascontiguousarray(rgb.transpose(2, 0, 1)).tobytes()
        h, w = rgb.shape[:2]
    else:
        g = pix if pix.ndim == 2 else (pix[..., :3] @ np.array([0.299, 0.587, 0.114])).astype(np.uint8)
        img.SamplesPerPixel = 1
        img.PhotometricInterpretation = "MONOCHROME2"
        data = np.ascontiguousarray(g).tobytes()
        h, w = g.shape
    img.Rows, img.Columns = int(h), int(w)
    img.PixelAspectRatio = ["1", "1"]
    img.BitsAllocated, img.BitsStored, img.HighBit, img.PixelRepresentation = 8, 8, 7, 0
    img.PixelData = data
    return img


def dicom_print(cfg: PrinterConfig, pages: list[PageImage], local_ae: str = "", timeout: int = 60,
                progress=None, cancel: threading.Event | None = None) -> PrintResult:
    """Envia as páginas. `progress(i, n)` é chamado a cada folha."""
    if not pages:
        raise PrintError("Nada para imprimir.")
    result = PrintResult()
    assoc, meta = _associate(cfg, local_ae, timeout)
    try:
        fs = Dataset()
        fs.NumberOfCopies = str(max(1, int(cfg.copies)))
        fs.PrintPriority = "MED"
        fs.MediumType = cfg.medium
        fs.FilmDestination = cfg.destination
        fs.FilmSessionLabel = "Ipe"
        fs_uid = generate_uid()
        status, _ = assoc.send_n_create(fs, BasicFilmSession, fs_uid, meta_uid=meta)
        _check(status, "criar a sessão de filme", result)
        fs_uid = str(status.get("AffectedSOPInstanceUID", "") or fs_uid)
        for i, page in enumerate(pages):
            if cancel is not None and cancel.is_set():
                result.warnings.append("Cancelado.")
                break
            fb = Dataset()
            fb.ImageDisplayFormat = "STANDARD\\1,1"
            fb.FilmOrientation = "LANDSCAPE" if page.landscape else "PORTRAIT"
            fb.FilmSizeID = cfg.film_size or page.film_size
            fb.MagnificationType = cfg.magnification
            fb.BorderDensity = "BLACK"
            fb.EmptyImageDensity = "BLACK"
            fb.Trim = "NO"
            if cfg.min_density is not None:
                fb.MinDensity = int(cfg.min_density)
            if cfg.max_density is not None:
                fb.MaxDensity = int(cfg.max_density)
            ref = Dataset()
            ref.ReferencedSOPClassUID = BasicFilmSession
            ref.ReferencedSOPInstanceUID = fs_uid
            fb.ReferencedFilmSessionSequence = [ref]
            fb_uid = generate_uid()
            status, attrs = assoc.send_n_create(fb, BasicFilmBox, fb_uid, meta_uid=meta)
            _check(status, f"criar a folha {i + 1}", result)
            fb_uid = str(status.get("AffectedSOPInstanceUID", "") or fb_uid)
            boxes = getattr(attrs, "ReferencedImageBoxSequence", None) if attrs is not None else None
            if not boxes:
                raise PrintError("A impressora não devolveu a caixa de imagem da folha.")
            box = boxes[0]
            ds = Dataset()
            ds.ImageBoxPosition = 1
            item = _image_item(page.pixels, cfg.color)
            if cfg.color:
                ds.BasicColorImageSequence = [item]
                box_class = BasicColorImageBox
            else:
                ds.BasicGrayscaleImageSequence = [item]
                box_class = BasicGrayscaleImageBox
            status, _ = assoc.send_n_set(ds, box.get("ReferencedSOPClassUID", box_class),
                                         box.ReferencedSOPInstanceUID, meta_uid=meta)
            _check(status, f"enviar a imagem da folha {i + 1}", result)
            status, _ = assoc.send_n_action(None, 1, BasicFilmBox, fb_uid, meta_uid=meta)
            _check(status, f"imprimir a folha {i + 1}", result)
            result.pages += 1
            if progress is not None:
                progress(i + 1, len(pages))
        try:
            assoc.send_n_delete(BasicFilmSession, fs_uid, meta_uid=meta)
        except Exception as e:  # noqa: BLE001
            log.debug("N-DELETE da sessão falhou: %s", e)
    finally:
        if assoc.is_established:
            assoc.release()
    return result


def dicom_print_job(cfg: PrinterConfig, job, folder, local_ae: str = "", timeout: int = 60,
                    progress=None, cancel: threading.Event | None = None) -> PrintResult:
    """Reenvia um trabalho recebido para uma impressora DICOM **como ele veio**: a mesma grade,
    o mesmo tamanho de filme e as mesmas imagens, caixa por caixa (sem remontar nada)."""
    from ipe.printing import jobs as J

    films = [f for f in job.films if f.filled()]
    if not films:
        raise PrintError("O trabalho não tem imagens.")
    result = PrintResult()
    assoc, meta = _associate(cfg, local_ae, timeout)
    try:
        fs = Dataset()
        fs.NumberOfCopies = str(max(1, int(cfg.copies or job.copies or 1)))
        fs.PrintPriority = job.priority or "MED"
        fs.MediumType = cfg.medium or job.medium or "BLUE FILM"
        fs.FilmDestination = cfg.destination or job.destination or "MAGAZINE"
        fs.FilmSessionLabel = (job.label or "Ipe")[:64]
        fs_uid = generate_uid()
        status, _ = assoc.send_n_create(fs, BasicFilmSession, fs_uid, meta_uid=meta)
        _check(status, "criar a sessão de filme", result)
        fs_uid = str(status.get("AffectedSOPInstanceUID", "") or fs_uid)
        for i, film in enumerate(films):
            if cancel is not None and cancel.is_set():
                result.warnings.append("Cancelado.")
                break
            fb = Dataset()
            fb.ImageDisplayFormat = film.display_format
            fb.FilmOrientation = film.orientation or "PORTRAIT"
            fb.FilmSizeID = cfg.film_size or film.film_size or "14INX17IN"
            fb.MagnificationType = cfg.magnification or film.magnification or "CUBIC"
            fb.BorderDensity = film.border or "BLACK"
            fb.EmptyImageDensity = film.empty or "BLACK"
            fb.Trim = film.trim or "NO"
            if cfg.min_density is not None:
                fb.MinDensity = int(cfg.min_density)
            if cfg.max_density is not None:
                fb.MaxDensity = int(cfg.max_density)
            ref = Dataset()
            ref.ReferencedSOPClassUID = BasicFilmSession
            ref.ReferencedSOPInstanceUID = fs_uid
            fb.ReferencedFilmSessionSequence = [ref]
            fb_uid = generate_uid()
            status, attrs = assoc.send_n_create(fb, BasicFilmBox, fb_uid, meta_uid=meta)
            _check(status, f"criar a folha {i + 1}", result)
            fb_uid = str(status.get("AffectedSOPInstanceUID", "") or fb_uid)
            caixas = list(getattr(attrs, "ReferencedImageBoxSequence", None) or [])
            if not caixas:
                raise PrintError("A impressora não devolveu as caixas de imagem da folha.")
            for box in film.filled():
                pos = max(1, int(box.position or 1))
                if pos > len(caixas):
                    result.warnings.append(f"A impressora só aceitou {len(caixas)} imagem(ns) na folha "
                                           f"{i + 1}.")
                    break
                alvo = caixas[pos - 1]
                px = J.box_pixels(folder, box)
                if px is None:
                    continue
                ds = Dataset()
                ds.ImageBoxPosition = pos
                if box.polarity:
                    ds.Polarity = box.polarity
                if box.requested_size:
                    ds.RequestedImageSize = str(box.requested_size)
                item = _image_item(px, cfg.color)
                if cfg.color:
                    ds.BasicColorImageSequence = [item]
                else:
                    ds.BasicGrayscaleImageSequence = [item]
                status, _ = assoc.send_n_set(ds, alvo.get("ReferencedSOPClassUID", BasicGrayscaleImageBox),
                                             alvo.ReferencedSOPInstanceUID, meta_uid=meta)
                _check(status, f"enviar a imagem {pos} da folha {i + 1}", result)
            status, _ = assoc.send_n_action(None, 1, BasicFilmBox, fb_uid, meta_uid=meta)
            _check(status, f"imprimir a folha {i + 1}", result)
            result.pages += 1
            if progress is not None:
                progress(i + 1, len(films))
        try:
            assoc.send_n_delete(BasicFilmSession, fs_uid, meta_uid=meta)
        except Exception as e:  # noqa: BLE001
            log.debug("N-DELETE da sessão falhou: %s", e)
    finally:
        if assoc.is_established:
            assoc.release()
    return result
