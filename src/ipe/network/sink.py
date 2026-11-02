"""Grava e indexa as imagens que chegam pela rede (C-STORE recebido ou C-GET).

Cada imagem é gravada em Storage/<Estudo>/<Série>/<SOP>.dcm assim que chega; uma
thread de fundo indexa em lotes no banco (mesmo código da importação de pastas)
e gera as miniaturas. Assim a rede nunca espera pelo banco.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

from pydicom.dataset import Dataset, FileMetaDataset

from ipe.db.repository import Repository
from ipe.db.session import Database
from ipe.importer.scanner import Importer, ImportResult, safe_name
from ipe.importer.thumbnails import generate_thumbnails

log = logging.getLogger(__name__)


class IncomingSink:
    def __init__(self, db: Database, repo: Repository, storage: Path,
                 on_indexed: Callable[[ImportResult, str], None] | None = None):
        self.db, self.repo, self.storage = db, repo, Path(storage)
        self.on_indexed = on_indexed
        self._pending: list[tuple[Path, str]] = []
        self._cond = threading.Condition()
        self._busy = False
        self._stop = False
        self.expected_studies: set[str] = set()     # estudos pedidos por nós (C-MOVE): origem "retrieved"
        # 0.86: quem mandou cada estudo recebido e qual AE nosso foi chamado (regras do filme automático)
        self.remetentes: dict[str, dict] = {}
        self._thread = threading.Thread(target=self._run, name="dicom-indexer", daemon=True)
        self._thread.start()

    # ------------------------------------------------------------ gravação
    def store(self, ds: Dataset, file_meta: FileMetaDataset | None, origin: str = "received",
              remetente: dict | None = None) -> Path:
        study = str(ds.get("StudyInstanceUID", "")) or "unknown"
        if remetente:
            if len(self.remetentes) > 5000:          # memória curta: só serve aos próximos minutos
                self.remetentes.clear()
            self.remetentes[study] = dict(remetente)
        series = str(ds.get("SeriesInstanceUID", "")) or "unknown"
        sop = str(ds.get("SOPInstanceUID", ""))
        if not sop:
            raise ValueError("Imagem sem SOPInstanceUID")
        if origin == "received" and study in self.expected_studies:
            origin = "retrieved"
        path = self.storage / safe_name(study) / safe_name(series) / f"{safe_name(sop)}.dcm"
        path.parent.mkdir(parents=True, exist_ok=True)
        if file_meta is not None:
            ds.file_meta = file_meta
        tmp = path.with_suffix(".part")
        ds.save_as(tmp, enforce_file_format=True)
        tmp.replace(path)
        with self._cond:
            self._pending.append((path, origin))
            self._cond.notify()
        return path

    # ------------------------------------------------------------ indexação
    def _run(self) -> None:
        while True:
            with self._cond:
                while not self._pending and not self._stop:
                    self._cond.wait()
                if self._stop and not self._pending:
                    return
                self._busy = True
            time.sleep(0.3)                      # junta as imagens que estão chegando
            with self._cond:
                batch, self._pending = self._pending, []
            try:
                by_origin: dict[str, list[Path]] = {}
                for p, o in batch:
                    by_origin.setdefault(o, []).append(p)
                for origin, paths in by_origin.items():
                    r = Importer(self.db, self.storage, copy_to_storage=True,
                                 origin=origin).import_paths(paths)
                    if r.new_series:
                        generate_thumbnails(self.repo, r.new_series)
                    self._banco_dos_novos(r)
                    if self.on_indexed is not None:
                        try:
                            self.on_indexed(r, origin)
                        except Exception:  # noqa: BLE001
                            log.exception("Falha no aviso de imagens recebidas")
            except Exception:  # noqa: BLE001
                log.exception("Falha ao indexar imagens recebidas")
            finally:
                with self._cond:
                    self._busy = False
                    self._cond.notify_all()

    def _banco_dos_novos(self, r) -> None:
        """0.99.27: exame novo que chegou no AE de uma identidade pessoal vai para o banco do dono."""
        from ipe.db import banco as B
        for uid in getattr(r, "new_studies", ()) or ():
            rem = self.remetentes.get(uid) or {}
            dono = B.dono_da_chegada(self.repo, rem.get("my_ae", ""))
            if dono:
                B.marcar_novos(self.repo, [uid], dono)

    def flush(self, timeout: float = 60.0) -> bool:
        """Espera até tudo o que chegou estar no banco."""
        end = time.monotonic() + timeout
        with self._cond:
            while self._pending or self._busy:
                left = end - time.monotonic()
                if left <= 0:
                    return False
                self._cond.wait(left)
        return True

    def stop(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify_all()
        self._thread.join(timeout=5)
