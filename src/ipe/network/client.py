"""Cliente DICOM (SCU): C-ECHO, C-FIND, C-GET, C-MOVE e C-STORE contra nós remotos.

Toda operação pode usar uma "identidade": outro AE Title de origem (calling AE),
como se a consulta viesse de outra estação. O uso de identidade fica na auditoria.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable

import pydicom
from pydicom.dataset import Dataset
from pynetdicom import AE, build_context, build_role, evt
from pynetdicom.sop_class import (
    StudyRootQueryRetrieveInformationModelFind, StudyRootQueryRetrieveInformationModelGet,
    StudyRootQueryRetrieveInformationModelMove, Verification,
)

from ipe.network.contexts import ALL_TS, STORAGE_CLASSES, UNCOMPRESSED

log = logging.getLogger(__name__)

Progress = Callable[[int, int, str], None]      # feitos, total, mensagem


class DicomError(Exception):
    pass


@dataclass
class Target:
    """Para onde e como: nó remoto + AE de origem + destino do C-MOVE."""
    name: str
    host: str
    port: int
    called_ae: str
    calling_ae: str
    move_destination: str
    retrieve: str = "get"

    @staticmethod
    def build(node: dict, local_ae: str, identity: dict | None = None) -> "Target":
        calling = (identity or {}).get("ae_title") or local_ae
        move_dest = ((identity or {}).get("move_destination") or node.get("move_destination")
                     or local_ae)
        return Target(node["name"], node["host"], int(node["port"]), node["ae_title"], calling,
                      move_dest, node.get("retrieve", "get"))


def display_pn(v) -> str:
    raw = str(v or "")
    parts = [p.strip() for p in raw.split("=")[0].split("^")]
    if len(parts) > 1 and parts[1]:
        return f"{parts[0]}, {' '.join(p for p in parts[1:] if p)}".strip(", ")
    return parts[0] if parts else ""


class DicomClient:
    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def _ae(self, calling: str) -> AE:
        ae = AE(ae_title=calling)
        ae.acse_timeout = ae.dimse_timeout = ae.network_timeout = self.timeout
        ae.maximum_pdu_size = 0
        return ae

    def _associate(self, ae: AE, t: Target, **kw):
        assoc = ae.associate(t.host, t.port, ae_title=t.called_ae, **kw)
        if not assoc.is_established:
            if assoc.is_rejected:
                raise DicomError(f"{t.name} recusou a conexão (AE {t.calling_ae} não autorizado "
                                 f"ou AE de destino {t.called_ae} errado).")
            raise DicomError(f"Sem resposta de {t.name} ({t.host}:{t.port}). Confira IP, porta e firewall.")
        return assoc

    # ------------------------------------------------------------ C-ECHO
    def echo(self, t: Target) -> tuple[bool, str]:
        ae = self._ae(t.calling_ae)
        ae.add_requested_context(Verification)
        try:
            assoc = self._associate(ae, t)
        except DicomError as e:
            return False, str(e)
        try:
            st = assoc.send_c_echo()
            ok = bool(st) and st.Status == 0x0000
            return ok, "C-ECHO ok" if ok else f"C-ECHO falhou (status {getattr(st, 'Status', '?')})"
        finally:
            assoc.release()

    # ------------------------------------------------------------ C-FIND
    def find(self, t: Target, query: Dataset, cancel: threading.Event | None = None,
             limit: int = 1000) -> list[Dataset]:
        ae = self._ae(t.calling_ae)
        ae.add_requested_context(StudyRootQueryRetrieveInformationModelFind)
        assoc = self._associate(ae, t)
        out: list[Dataset] = []
        try:
            for status, ident in assoc.send_c_find(query, StudyRootQueryRetrieveInformationModelFind):
                if not status:
                    raise DicomError(f"{t.name} não respondeu à busca (tempo esgotado).")
                code = status.Status
                if code in (0xFF00, 0xFF01) and ident is not None:
                    out.append(ident)
                    if len(out) >= limit or (cancel is not None and cancel.is_set()):
                        assoc.abort()
                        return out
                elif code not in (0x0000, 0xFF00, 0xFF01):
                    raise DicomError(f"{t.name} devolveu erro na busca (status 0x{code:04X}).")
        finally:
            if assoc.is_established:
                assoc.release()
        return out

    def find_studies(self, t: Target, *, name: str = "", patient_id: str = "", accession: str = "",
                     date_from: str = "", date_to: str = "", modality: str = "", description: str = "",
                     study_uid: str = "", limit: int = 500,
                     cancel: threading.Event | None = None) -> list[dict]:
        q = query_estudos(name=name, patient_id=patient_id, accession=accession, date_from=date_from,
                          date_to=date_to, modality=modality, description=description,
                          study_uid=study_uid)
        out = [linha_estudo(ds) for ds in self.find(t, q, cancel=cancel, limit=limit)]
        return [r for r in out if r["study_uid"]]

    def find_series(self, t: Target, study_uid: str) -> list[dict]:
        out = [linha_serie(ds) for ds in self.find(t, query_series(study_uid))]
        return sorted([s for s in out if s["series_uid"]], key=lambda s: s["series_number"] or 0)

    # ------------------------------------------------------------ C-GET / C-MOVE
    @staticmethod
    def _retrieve_query(study_uid: str, series_uids: list[str] | None) -> Dataset:
        q = Dataset()
        q.QueryRetrieveLevel = "SERIES" if series_uids else "STUDY"
        q.StudyInstanceUID = study_uid
        if series_uids:
            q.SeriesInstanceUID = series_uids if len(series_uids) > 1 else series_uids[0]
        return q

    def get(self, t: Target, study_uid: str, series_uids: list[str] | None, sink,
            progress: Progress | None = None, cancel: threading.Event | None = None) -> int:
        """C-GET: as imagens voltam pela mesma conexão (não precisa o PACS conhecer este AE)."""
        ae = self._ae(t.calling_ae)
        ae.add_requested_context(StudyRootQueryRetrieveInformationModelGet)
        for uid in STORAGE_CLASSES[:127]:
            ae.add_requested_context(uid, ALL_TS)
        roles = [build_role(uid, scp_role=True) for uid in STORAGE_CLASSES[:127]]
        received = [0]

        def on_store(event) -> int:
            if cancel is not None and cancel.is_set():
                return 0xA700
            try:
                sink.store(event.dataset, event.file_meta, origin="retrieved")
                received[0] += 1
                return 0x0000
            except Exception as e:  # noqa: BLE001
                log.error("Falha ao gravar imagem do C-GET: %s", e)
                return 0xA700

        assoc = self._associate(ae, t, ext_neg=roles, evt_handlers=[(evt.EVT_C_STORE, on_store)])
        try:
            return self._run_retrieve(
                assoc.send_c_get(self._retrieve_query(study_uid, series_uids),
                                 StudyRootQueryRetrieveInformationModelGet),
                t, assoc, progress, cancel, received)
        finally:
            if assoc.is_established:
                assoc.release()

    def move(self, t: Target, study_uid: str, series_uids: list[str] | None,
             progress: Progress | None = None, cancel: threading.Event | None = None) -> int:
        """C-MOVE: o PACS abre outra conexão e envia para `move_destination`."""
        ae = self._ae(t.calling_ae)
        ae.add_requested_context(StudyRootQueryRetrieveInformationModelMove)
        assoc = self._associate(ae, t)
        try:
            return self._run_retrieve(
                assoc.send_c_move(self._retrieve_query(study_uid, series_uids), t.move_destination,
                                  StudyRootQueryRetrieveInformationModelMove),
                t, assoc, progress, cancel, None)
        finally:
            if assoc.is_established:
                assoc.release()

    @staticmethod
    def _run_retrieve(responses, t: Target, assoc, progress, cancel, received) -> int:
        done = failed = total = 0
        for status, _ident in responses:
            if cancel is not None and cancel.is_set():
                assoc.abort()
                raise DicomError("Cancelado")
            if not status:
                raise DicomError(f"{t.name} parou de responder (tempo esgotado).")
            code = status.Status
            rem = _int(status.get("NumberOfRemainingSuboperations"))
            done = _int(status.get("NumberOfCompletedSuboperations"))
            failed = _int(status.get("NumberOfFailedSuboperations"))
            warn = _int(status.get("NumberOfWarningSuboperations"))
            total = max(total, done + failed + warn + rem)
            if progress:
                got = received[0] if received is not None else done
                progress(got, total, f"{got} de {total} imagens")
            if code in (0xFF00, 0xFF01):
                continue
            if code == 0xA801:
                raise DicomError(f"{t.name} não conhece o destino {t.move_destination}. Peça à TI para "
                                 f"cadastrar esse AE (IP e porta deste computador) ou use C-GET.")
            if code == 0xFE00:
                raise DicomError("Cancelado")
            if code not in (0x0000, 0xB000) and not (code & 0xF000 == 0xB000):
                raise DicomError(f"{t.name} devolveu erro no download (status 0x{code:04X}).")
        n = received[0] if received is not None else done
        if failed and not n:
            raise DicomError(f"{t.name} não conseguiu enviar as {failed} imagens.")
        return n

    # ------------------------------------------------------------ C-STORE
    def store(self, t: Target, paths: list[str], progress: Progress | None = None,
              cancel: threading.Event | None = None) -> tuple[int, int]:
        """Envia arquivos. Devolve (enviados, falhas)."""
        by_class: dict[str, set[str]] = defaultdict(set)
        heads = []
        for p in paths:
            try:
                h = pydicom.dcmread(p, stop_before_pixels=True, specific_tags=["SOPClassUID"])
                ts = str(getattr(getattr(h, "file_meta", None), "TransferSyntaxUID", "") or UNCOMPRESSED[0])
                cls = str(h.SOPClassUID)
                by_class[cls].add(ts)
                heads.append((p, cls, ts))
            except Exception as e:  # noqa: BLE001
                log.warning("Ignorando %s: %s", p, e)
        ae = self._ae(t.calling_ae)
        contexts = []
        for cls, tss in by_class.items():
            for ts in tss:
                contexts.append(build_context(cls, [ts]))
            contexts.append(build_context(cls, UNCOMPRESSED))
        if len(contexts) > 128:
            contexts = contexts[:128]
        ae.requested_contexts = contexts
        assoc = self._associate(ae, t)
        sent = failed = 0
        try:
            for i, (p, _cls, _ts) in enumerate(heads, 1):
                if cancel is not None and cancel.is_set():
                    raise DicomError("Cancelado")
                try:
                    ds = pydicom.dcmread(p)
                    try:
                        st = assoc.send_c_store(ds)
                    except ValueError:
                        # 0.100.0: o destino não aceitou a sintaxe do arquivo (HTJ2K do cache do cliente, JPEG-LS):
                        # vai descomprimido, que todo nó aceita
                        ds.decompress()
                        st = assoc.send_c_store(ds)
                    if st and st.Status in (0x0000, 0xB000, 0xB007, 0xB006):
                        sent += 1
                    else:
                        failed += 1
                except Exception as e:  # noqa: BLE001
                    log.warning("Falha ao enviar %s: %s", p, e)
                    failed += 1
                if progress:
                    progress(i, len(heads), f"{i} de {len(heads)} imagens")
        finally:
            if assoc.is_established:
                assoc.release()
        return sent, failed


# ---------------------------------------------------------------- perguntas e respostas
# Fonte única do que se pergunta num C-FIND e de como a resposta vira dicionário: a busca do PACS
# e a gestão de exames (network/gestao.py), que mantém a associação aberta, usam as mesmas.

def query_estudos(*, name: str = "", patient_id: str = "", accession: str = "", date_from: str = "",
                  date_to: str = "", modality: str = "", description: str = "",
                  study_uid: str = "") -> Dataset:
    q = Dataset()
    q.QueryRetrieveLevel = "STUDY"
    name = name.strip()
    if name and "*" not in name and "?" not in name:
        name = name.replace(", ", "^") + "*"
    q.PatientName = name
    q.PatientID = patient_id.strip()
    q.PatientBirthDate = ""
    q.PatientSex = ""
    q.StudyDate = f"{date_from}-{date_to}" if (date_from or date_to) and date_from != date_to \
        else (date_from or "")
    q.StudyTime = ""
    q.AccessionNumber = accession.strip()
    q.StudyDescription = description.strip()
    q.ModalitiesInStudy = modality.strip()
    q.ReferringPhysicianName = ""
    q.StudyInstanceUID = study_uid.strip()
    q.NumberOfStudyRelatedSeries = ""
    q.NumberOfStudyRelatedInstances = ""
    return q


def linha_estudo(ds: Dataset) -> dict:
    mods = ds.get("ModalitiesInStudy", "")
    if not isinstance(mods, str):
        mods = "\\".join(str(m) for m in mods)
    return {
        "study_uid": str(ds.get("StudyInstanceUID", "")),
        "patient_name": display_pn(ds.get("PatientName", "")),
        "patient_id": str(ds.get("PatientID", "")),
        "birth_date": str(ds.get("PatientBirthDate", "")),
        "sex": str(ds.get("PatientSex", "")),
        "study_date": str(ds.get("StudyDate", "")),
        "study_time": str(ds.get("StudyTime", "")),
        "accession": str(ds.get("AccessionNumber", "")),
        "description": str(ds.get("StudyDescription", "")),
        "modalities": mods,
        "num_series": _int(ds.get("NumberOfStudyRelatedSeries")),
        "num_images": _int(ds.get("NumberOfStudyRelatedInstances")),
    }


def query_series(study_uid: str) -> Dataset:
    q = Dataset()
    q.QueryRetrieveLevel = "SERIES"
    q.StudyInstanceUID = study_uid
    q.SeriesInstanceUID = ""
    q.Modality = ""
    q.SeriesNumber = ""
    q.SeriesDescription = ""
    q.BodyPartExamined = ""
    q.NumberOfSeriesRelatedInstances = ""
    return q


def linha_serie(ds: Dataset) -> dict:
    return {"series_uid": str(ds.get("SeriesInstanceUID", "")),
            "modality": str(ds.get("Modality", "")),
            "series_number": _int(ds.get("SeriesNumber")),
            "description": str(ds.get("SeriesDescription", "")),
            "num_images": _int(ds.get("NumberOfSeriesRelatedInstances"))}


def _int(v) -> int:
    try:
        return int(v) if v not in (None, "") else 0
    except (TypeError, ValueError):
        return 0
