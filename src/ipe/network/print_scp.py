"""Impressora DICOM (Print Management SCP): recebe os filmes das modalidades.

A modalidade fala como se fôssemos uma impressora de filme: cria a sessão (N-CREATE),
cria cada folha (N-CREATE, e devolvemos as caixas de imagem), manda os pixels de cada
caixa (N-SET) e manda imprimir (N-ACTION). Guardamos tudo em vez de imprimir.

Detalhe que faz diferença na vida real: muita modalidade pergunta o estado da impressora
(N-GET no Printer) antes de mandar a primeira imagem e desiste se ninguém responder — por
isso respondemos sempre NORMAL.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from pydicom.dataset import Dataset
from pydicom.uid import generate_uid
from pynetdicom import AE, evt
from pynetdicom.sop_class import (
    BasicAnnotationBox, BasicColorImageBox, BasicColorPrintManagementMeta, BasicFilmBox,
    BasicFilmSession, BasicGrayscaleImageBox, BasicGrayscalePrintManagementMeta, PresentationLUT,
    Printer, PrinterConfigurationRetrieval, Verification,
)

from ipe.printing import jobs as J

log = logging.getLogger(__name__)

DEFAULT_AE = "DICOMPRINT"
DEFAULT_PORT = 11113


class _Association:
    """O que uma modalidade mandou numa conexão: vira um trabalho de impressão."""

    def __init__(self, root: Path, calling: str, called: str, host: str, server: str = ""):
        self.job = J.PrintJob(uid=generate_uid(), received_at=datetime.now().isoformat(timespec="seconds"),
                              calling_ae=calling, called_ae=called, remote_host=host, server=server)
        self.folder = J.job_dir(root, self.job.uid)
        self.films: dict[str, J.FilmBox] = {}          # uid da folha -> folha
        self.boxes: dict[str, tuple[J.FilmBox, int]] = {}   # uid da caixa -> (folha, índice)
        self.notes: dict[str, tuple[J.FilmBox, int]] = {}   # uid da anotação -> (folha, posição)
        self.order: list[J.FilmBox] = []
        self.images = 0
        # imagens comuns (C-STORE) mandadas à porta da impressão: (estudo, série, SOP, quadros)
        self.stored: list[tuple[str, str, str, int]] = []

    def film_for(self, uid: str) -> J.FilmBox | None:
        return self.films.get(str(uid))


class PrintScpServer:
    """Nó que se apresenta como impressora DICOM. `on_job(job, folder)` recebe cada trabalho."""

    def __init__(self, config: dict, root: Path | str, on_job: Callable[[J.PrintJob, Path], None],
                 allowed: Callable[[], list[str]] | None = None,
                 on_store: Callable | None = None, on_images: Callable | None = None):
        """`on_store(ds, file_meta)` grava uma imagem comum recebida nesta porta (C-STORE) e
        `on_images(imagens, calling_ae, host)` recebe, no fim da conexão, a lista do que chegou
        — é o que vira filme (0.81). Sem `on_store`, a porta só aceita impressão."""
        self.config = dict(config or {})
        self.root = Path(root)
        self.on_job = on_job
        self.allowed = allowed
        self.on_store = on_store
        self.on_images = on_images
        self._server = None
        self._ae = None
        self._lock = threading.Lock()
        self._live: dict[int, _Association] = {}
        self.error = ""

    # ------------------------------------------------------------ ciclo de vida
    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def name(self) -> str:
        return self.config.get("name", "") or self.ae_title

    @property
    def ae_title(self) -> str:
        return self.config.get("ae_title", DEFAULT_AE) or DEFAULT_AE

    @property
    def port(self) -> int:
        return int(self.config.get("port", DEFAULT_PORT) or DEFAULT_PORT)

    def status_text(self) -> str:
        if self.running:
            return f"{self.name}: AE {self.ae_title}, porta {self.port}"
        return f"{self.name} desligada{(' — ' + self.error) if self.error else ''}"

    def start(self) -> bool:
        self.stop()
        self.root.mkdir(parents=True, exist_ok=True)
        ae = AE(ae_title=self.ae_title)
        t = int(self.config.get("timeout", 60) or 60)
        ae.acse_timeout = ae.dimse_timeout = ae.network_timeout = t
        ae.maximum_associations = 8
        for cx in (Verification, BasicGrayscalePrintManagementMeta, BasicColorPrintManagementMeta,
                   BasicFilmSession, BasicFilmBox, BasicGrayscaleImageBox, BasicColorImageBox,
                   BasicAnnotationBox, PresentationLUT, Printer, PrinterConfigurationRetrieval):
            ae.add_supported_context(cx)
        if self.on_store is not None:
            # modalidade que manda imagem (e não impressão) para a impressora: aceita e monta filme
            from pynetdicom import ALL_TRANSFER_SYNTAXES, StoragePresentationContexts
            from ipe.network.contexts import STORAGE_CLASSES
            for uid in {cx.abstract_syntax for cx in StoragePresentationContexts} | set(STORAGE_CLASSES):
                ae.add_supported_context(uid, ALL_TRANSFER_SYNTAXES)
        self._ae = ae
        self.refresh_acl()
        handlers = [(evt.EVT_C_ECHO, self._on_echo), (evt.EVT_C_STORE, self._on_store), (evt.EVT_N_CREATE, self._on_create),
                    (evt.EVT_N_SET, self._on_set), (evt.EVT_N_ACTION, self._on_action),
                    (evt.EVT_N_DELETE, self._on_delete), (evt.EVT_N_GET, self._on_get),
                    (evt.EVT_RELEASED, self._on_closed), (evt.EVT_ABORTED, self._on_closed),
                    (evt.EVT_CONN_CLOSE, self._on_closed)]
        try:
            self._server = ae.start_server(("", self.port), block=False, evt_handlers=handlers)
            self.error = ""
            log.info("Impressora DICOM “%s” ligada: %s na porta %d", self.name, self.ae_title, self.port)
            return True
        except OSError as e:
            self._server = None
            self.error = f"porta {self.port} ocupada ou bloqueada ({e.strerror or e})"
            log.error("Não foi possível ligar a impressora DICOM: %s", e)
            return False

    def stop(self) -> None:
        if self._server is not None:
            try:
                self._server.shutdown()
            except Exception:  # noqa: BLE001
                pass
            self._server = None
            log.info("Impressora DICOM desligada")

    def refresh_acl(self) -> None:
        ae = self._ae
        if ae is None:
            return
        if self.config.get("accept", "any") == "any" or self.allowed is None:
            ae.require_calling_aet = []
        else:
            known = [x for x in self.allowed() if x]
            ae.require_calling_aet = known or ["-NENHUM-"]

    # ------------------------------------------------------------ estado da conexão
    def _session(self, event) -> _Association:
        key = id(event.assoc)
        with self._lock:
            s = self._live.get(key)
            if s is None:
                req = event.assoc.requestor
                addr = getattr(req, "address", "") or ""
                s = _Association(self.root, str(req.ae_title or "").strip(), self.ae_title, str(addr),
                                 self.name)
                self._live[key] = s
            return s

    def _on_echo(self, event) -> int:
        return 0x0000

    def _on_store(self, event) -> int:
        if self.on_store is None:
            return 0xA700
        try:
            ds = event.dataset
            ds.file_meta = event.file_meta
            self.on_store(ds, event.file_meta)
            quadros = int(str(ds.get("NumberOfFrames", 1) or 1) or 1)
            self._session(event).stored.append((str(ds.get("StudyInstanceUID", "")),
                                                str(ds.get("SeriesInstanceUID", "")),
                                                str(ds.get("SOPInstanceUID", "")), quadros))
            return 0x0000
        except Exception as e:  # noqa: BLE001
            log.error("Falha ao gravar imagem recebida na porta da impressão: %s", e)
            return 0xA700

    def _on_closed(self, event) -> None:
        with self._lock:
            s = self._live.pop(id(event.assoc), None)
        if s is None:
            return
        if s.stored and self.on_images is not None:
            try:
                self.on_images(list(s.stored), s.job.calling_ae, s.job.remote_host)
            except Exception:  # noqa: BLE001
                log.exception("Falha ao montar o filme das imagens recebidas")
        if not s.order or not s.images:
            return                          # conexão sem nada impresso: não vira trabalho
        job = s.job
        job.films = list(s.order)
        nome, ident, de_onde = J.guess_patient(job)
        if nome or ident:
            job.patient_name, job.patient_id, job.id_source = nome, ident, de_onde
        try:
            J.save(job, self.root)
            self.on_job(job, s.folder)
            log.info("Trabalho de impressão de %s: %d folha(s), %d imagem(ns)",
                     job.calling_ae, job.sheets, job.images)
        except Exception:  # noqa: BLE001
            log.exception("Falha ao guardar o trabalho de impressão")

    # ------------------------------------------------------------ N-CREATE
    def _on_create(self, event):
        s = self._session(event)
        req = event.request
        cls = str(req.AffectedSOPClassUID)
        ds = event.attribute_list or Dataset()
        uid = str(req.AffectedSOPInstanceUID or "") or generate_uid()
        out = Dataset()
        if cls == BasicFilmSession:
            j = s.job
            j.copies = int(str(ds.get("NumberOfCopies", "1") or 1) or 1)
            j.priority = str(ds.get("PrintPriority", "") or "")
            j.medium = str(ds.get("MediumType", "") or "")
            j.destination = str(ds.get("FilmDestination", "") or "")
            j.label = str(ds.get("FilmSessionLabel", "") or "")
            j.owner_id = str(ds.get("OwnerID", "") or "")
            out.AffectedSOPInstanceUID = uid
            return 0x0000, out
        if cls == BasicFilmBox:
            film = J.FilmBox(
                display_format=str(ds.get("ImageDisplayFormat", "STANDARD\\1,1") or "STANDARD\\1,1"),
                orientation=str(ds.get("FilmOrientation", "PORTRAIT") or "PORTRAIT"),
                film_size=str(ds.get("FilmSizeID", "") or ""),
                magnification=str(ds.get("MagnificationType", "") or ""),
                border=str(ds.get("BorderDensity", "") or ""),
                empty=str(ds.get("EmptyImageDensity", "") or ""),
                min_density=int(ds.get("MinDensity", 0) or 0),
                max_density=int(ds.get("MaxDensity", 0) or 0),
                trim=str(ds.get("Trim", "") or ""),
                config=str(ds.get("ConfigurationInformation", "") or ""),
                annotation_format=str(ds.get("AnnotationDisplayFormatID", "") or ""))
            n = max(1, J.box_count(film.display_format))
            color = any(cx.abstract_syntax == BasicColorPrintManagementMeta
                        for cx in event.assoc.accepted_contexts)
            box_class = BasicColorImageBox if color else BasicGrayscaleImageBox
            refs = []
            for i in range(n):
                box_uid = generate_uid()
                film.boxes.append(J.ImageBox(position=i + 1))
                s.boxes[box_uid] = (film, i)
                r = Dataset()
                r.ReferencedSOPClassUID = box_class
                r.ReferencedSOPInstanceUID = box_uid
                refs.append(r)
            s.films[uid] = film
            s.order.append(film)
            out.update(ds)
            out.ReferencedImageBoxSequence = refs
            if film.annotation_format:
                notes = []
                for i in range(n):
                    note_uid = generate_uid()
                    s.notes[note_uid] = (film, i + 1)
                    r = Dataset()
                    r.ReferencedSOPClassUID = BasicAnnotationBox
                    r.ReferencedSOPInstanceUID = note_uid
                    notes.append(r)
                out.ReferencedBasicAnnotationBoxSequence = notes
            out.AffectedSOPInstanceUID = uid
            return 0x0000, out
        if cls == PresentationLUT:
            out.AffectedSOPInstanceUID = uid
            return 0x0000, out
        log.warning("N-CREATE de classe desconhecida: %s", cls)
        return 0x0122, None                 # SOP Class não suportada

    # ------------------------------------------------------------ N-SET
    def _on_set(self, event):
        s = self._session(event)
        req = event.request
        uid = str(req.RequestedSOPInstanceUID or "")
        ds = event.attribute_list or Dataset()
        out = Dataset()
        if uid in s.boxes:
            film, i = s.boxes[uid]
            item = None
            for name in ("BasicGrayscaleImageSequence", "BasicColorImageSequence"):
                seq = ds.get(name, None)
                if seq:
                    item = seq[0]
                    break
            if item is None:
                return 0x0120, None          # falta o atributo obrigatório (a imagem)
            s.images += 1
            box = J.write_box(s.folder, item, s.images, s.job)
            box.position = int(ds.get("ImageBoxPosition", i + 1) or (i + 1))
            box.polarity = str(ds.get("Polarity", "") or "")
            box.magnification = str(ds.get("MagnificationType", "") or "")
            try:
                box.requested_size = float(ds.get("RequestedImageSize", 0) or 0)
            except (TypeError, ValueError):
                box.requested_size = 0.0
            film.boxes[i] = box
            out.ImageBoxPosition = box.position
            return 0x0000, out
        if uid in s.notes:
            film, pos = s.notes[uid]
            texto = str(ds.get("TextString", "") or "")
            if texto:
                film.annotations.append({"position": int(ds.get("AnnotationPosition", pos) or pos),
                                         "text": texto})
            return 0x0000, ds
        film = s.film_for(uid)
        if film is not None:                 # ajuste de parâmetros da folha já criada
            if "FilmSizeID" in ds:
                film.film_size = str(ds.FilmSizeID)
            if "FilmOrientation" in ds:
                film.orientation = str(ds.FilmOrientation)
            if "MagnificationType" in ds:
                film.magnification = str(ds.MagnificationType)
            return 0x0000, ds
        if "NumberOfCopies" in ds or "MediumType" in ds or "FilmSessionLabel" in ds:
            j = s.job
            j.copies = int(str(ds.get("NumberOfCopies", j.copies) or j.copies) or 1)
            j.medium = str(ds.get("MediumType", j.medium) or j.medium)
            j.label = str(ds.get("FilmSessionLabel", j.label) or j.label)
            return 0x0000, ds
        log.warning("N-SET para instância desconhecida: %s", uid)
        return 0x0112, None                  # No such SOP Instance

    # ------------------------------------------------------------ N-ACTION / N-DELETE / N-GET
    def _on_action(self, event):
        self._session(event)
        return 0x0000, None                  # "imprimir": aceitamos e guardamos ao fechar a conexão

    def _on_delete(self, event) -> int:
        return 0x0000

    def _on_get(self, event):
        req = event.request
        cls = str(req.RequestedSOPClassUID or "")
        ds = Dataset()
        if cls == PrinterConfigurationRetrieval:
            item = Dataset()
            item.PrinterName = self.ae_title
            ds.PrinterConfigurationSequence = [item]
            return 0x0000, ds
        ds.PrinterStatus = "NORMAL"
        ds.PrinterStatusInfo = "NORMAL"
        ds.PrinterName = self.ae_title
        ds.Manufacturer = "Ipe"
        ds.ManufacturerModelName = "Impressora virtual"
        ds.DeviceSerialNumber = self.ae_title
        from ipe import __version__
        ds.SoftwareVersions = __version__
        now = datetime.now()
        ds.DateOfLastCalibration = now.strftime("%Y%m%d")
        ds.TimeOfLastCalibration = now.strftime("%H%M%S")
        return 0x0000, ds
