"""Cópia anonimizada **dentro do banco**, como outro exame.

O mesmo anonimizador da exportação, mas o destino é o próprio banco: os arquivos anonimizados
vão para uma pasta temporária, são importados (copiados para o armazenamento) e a pasta some.
O original não é tocado.

Duas coisas são obrigatórias aqui e não na exportação:

* **UIDs novos.** Com os mesmos Study/Series/SOP Instance UID, o importador acharia que é o
  mesmo exame e as imagens anonimizadas cairiam *dentro do original* (ou seriam ignoradas como
  repetidas). Fora da máquina isso é escolha; dentro do banco, não.
* **ID de paciente que não repete.** O {n} da exportação conta de 1 a cada vez; no banco,
  duas cópias feitas em dias diferentes virariam o mesmo paciente "ANON001". Aqui o {n}
  continua de onde o banco parou.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

from sqlalchemy import select

from ipe.exporter.anonymize import AnonOptions, _fmt
from ipe.exporter.core import ExportItem, export_dicom

log = logging.getLogger(__name__)

ORIGEM = "anonymized"


@dataclass
class ResultadoCopia:
    estudos: list[str] = field(default_factory=list)     # Study UIDs novos, no banco
    imagens: int = 0
    arquivos: int = 0
    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def opcoes_do_banco(opts: AnonOptions) -> AnonOptions:
    """O que a cópia no banco exige, por cima do que o médico escolheu."""
    return replace(opts, enabled=True, new_uids=True)


def primeiro_livre(db, modelo: str, quantos: int) -> int:
    """Menor n ≥ 1 tal que n, n+1, … n+quantos−1 não sejam IDs de paciente já no banco."""
    from ipe.db.models import Patient
    if _fmt(modelo, 1) == _fmt(modelo, 2):
        return 1                    # modelo sem {n}: todos iguais de propósito
    with db.session() as s:
        usados = set(s.scalars(select(Patient.patient_id)))
    n = 1
    while any(_fmt(modelo, k) in usados for k in range(n, n + max(1, quantos))):
        n += 1
    return n


def copiar_anonimizado(repo, db, storage_root, items: list[ExportItem], opts: AnonOptions,
                       progress=None, cancel=None) -> ResultadoCopia:
    from ipe.importer.scanner import Importer
    from ipe.importer.thumbnails import generate_thumbnails
    opts = opcoes_do_banco(opts)
    n0 = primeiro_livre(db, opts.patient_id, len({it.study_uid for it in items}))
    tmp = Path(tempfile.mkdtemp(prefix="dv_anon_"))
    try:
        ex = export_dicom(repo, items, tmp / "copia", opts, dicomdir=False, viewer=False,
                          zip_output=False, progress=progress, cancel=cancel, primeiro=n0)
        out = ResultadoCopia(arquivos=ex.files, erros=list(ex.errors), avisos=list(ex.warnings))
        if not ex.files:
            return out
        if progress:
            progress(0, ex.files, "Guardando no banco…")
        imp = Importer(db, storage_root, copy_to_storage=True, origin=ORIGEM).import_paths(
            [tmp / "copia"], progress=(lambda d, t, _x: progress(d, t, f"Guardando no banco: {d}/{t}"))
            if progress else None)
        out.imagens = imp.added
        out.estudos = sorted(imp.new_studies)
        out.erros += imp.error_files
        try:
            generate_thumbnails(repo, imp.new_series)
        except Exception as e:  # noqa: BLE001
            log.warning("miniaturas da cópia anonimizada: %s", e)
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
