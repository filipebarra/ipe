"""O que fazer com o trabalho de impressão que acabou de chegar.

Registra na lista de impressões e (se quiser) monta cada folha e guarda como exame no
banco, para você poder abrir no viewer como qualquer outro estudo.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydicom.uid import generate_uid

from ipe.printing import jobs as J

log = logging.getLogger(__name__)


def to_database(sink, job: J.PrintJob, folder: Path | str, width: int = 1240) -> str:
    """Monta as folhas e manda para o banco como Secondary Capture. Devolve o UID do estudo."""
    if not job.films:
        return ""
    study_uid, series_uid = generate_uid(), generate_uid()
    n = 0
    for i, film in enumerate(job.films):
        if not film.filled():
            continue
        try:
            px = J.compose_sheet(folder, film, width=width)
            ds = J.sheet_dataset(job, i, px, study_uid, series_uid)
            sink.store(ds, ds.file_meta, origin="received")
            n += 1
        except Exception:  # noqa: BLE001
            log.exception("Falha ao montar a folha %d do trabalho %s", i + 1, job.uid)
    return study_uid if n else ""


def store_job(repo, sink, job: J.PrintJob, folder: Path | str, root: Path | str,
              to_db: bool = True, settings=None) -> dict | None:
    """Grava o trabalho na lista de impressões (e no banco, se pedido). Devolve a linha.

    Com `settings`, também anota a **origem** (AE + endereço + servidor) no cadastro: é o que
    faz um aparelho novo aparecer na lista de pendentes em vez de passar despercebido.
    """
    folder = Path(folder)
    if to_db and sink is not None:
        job.study_uid = to_database(sink, job, folder)
    try:                                   # 0.84: a modalidade do exame do paciente, ou a da origem
        from ipe.printing.modalidade import descobrir
        job.modality = job.modality or descobrir(repo, settings, {
            "patient_id": job.patient_id, "received_at": job.when(), "study_uid": job.study_uid,
            "calling_ae": job.calling_ae, "remote_host": job.remote_host, "server": job.server})
    except Exception:  # noqa: BLE001 - modalidade é ajuda, não pode derrubar o recebimento
        log.exception("Modalidade do trabalho %s", job.uid)
    if to_db and sink is not None:
        J.save(job, root)
    job_id = repo.add_print_job(
        uid=job.uid, source="scp", calling_ae=job.calling_ae, remote_host=job.remote_host,
        server=job.server,
        label=job.label, medium=job.medium, film_size=job.film_size, sheets=job.sheets,
        images=job.images, patient_name=job.patient_name, patient_id=job.patient_id,
        id_source=job.id_source, study_uid=job.study_uid, folder=str(folder), status="new",
        modality=job.modality,
        received_at=job.when())
    if settings is not None:
        try:
            from ipe.printing import origins as O
            O.see(settings, job.calling_ae, job.remote_host, job.server,
                  job.received_at or "")
        except Exception:  # noqa: BLE001 - cadastro não pode derrubar o recebimento
            log.exception("Origem do trabalho %s", job.uid)
    return repo.print_job(job_id)
