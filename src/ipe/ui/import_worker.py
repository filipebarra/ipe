"""Importação em thread separada, com barra de progresso e cancelamento.

A thread (QThread) vive na thread principal; só o método run() roda em segundo
plano. Os sinais chegam à interface pela fila de eventos (conexão enfileirada),
então a barra de progresso é sempre atualizada pela thread principal.
Quem cria a ImportThread precisa guardar uma referência a ela até terminar.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ipe.db.repository import Repository
from ipe.importer.scanner import Importer, ImportResult
from ipe.importer.thumbnails import generate_thumbnails

log = logging.getLogger(__name__)


class ImportThread(QThread):
    progress = Signal(int, int, str)
    status = Signal(str)
    done = Signal(object)          # ImportResult

    def __init__(self, importer: Importer, repo: Repository, paths: list[Path], parent=None):
        super().__init__(parent)
        self.importer, self.repo, self.paths = importer, repo, paths

    def run(self) -> None:  # executa em segundo plano
        try:
            self.status.emit("Procurando arquivos…")
            result = self.importer.import_paths(
                self.paths, progress=lambda d, t, c: self.progress.emit(d, t, c),
                on_scan=lambda n: self.status.emit(f"Procurando arquivos… {n} encontrados"))
            if result.new_series:
                self.status.emit("Gerando miniaturas…")
                generate_thumbnails(self.repo, result.new_series)
        except Exception as e:  # noqa: BLE001
            log.exception("Falha na importação")
            result = ImportResult(errors=1, error_files=[f"{type(e).__name__}: {e}"])
        self.done.emit(result)

    def cancel(self) -> None:
        self.importer.cancel()
