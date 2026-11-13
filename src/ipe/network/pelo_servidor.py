"""0.100.37: o "cliente DICOM" dos nós que o servidor central compartilha.

Tem os mesmos métodos que os clientes DIMSE e DICOMweb usados pela fila de rede (`echo`, `find_studies`,
`find_series`), mais `baixar`: em vez de receber as imagens aqui, pede ao servidor que baixe para o banco dele e
acompanha o andamento. Quem fala com o PACS é o servidor (`central/pacs_servidor.py`).
"""
from __future__ import annotations

import time

from ipe.network.client import DicomError

FIM = ("done", "error", "cancelled")


class ClienteDoServidor:
    def __init__(self, remoto):
        self.remoto = remoto
        self.timeout = getattr(remoto, "timeout", 30)

    def _rpc(self, metodo, *a):
        try:
            return self.remoto.rpc(metodo, *a)
        except Exception as e:  # noqa: BLE001
            raise DicomError(f"servidor central: {e}") from e

    @staticmethod
    def _id(t) -> int:
        return abs(int((t or {}).get("id") or 0))

    def echo(self, t) -> tuple[bool, str]:
        r = self._rpc("pacs_nos") or {}
        if not any(n["id"] == self._id(t) for n in r.get("nos") or []):
            raise DicomError("o servidor não compartilha mais este nó")
        return True, "o servidor respondeu"

    def find_studies(self, t, cancel=None, **filtros) -> list[dict]:
        r = self._rpc("pacs_buscar", self._id(t), filtros) or {}
        return list(r.get("estudos") or [])

    def find_series(self, t, study_uid: str) -> list[dict]:
        r = self._rpc("pacs_series", self._id(t), study_uid) or {}
        return list(r.get("series") or [])

    def baixar(self, job, progress=None, intervalo: float = 1.0) -> str:
        """Pede o download ao servidor e acompanha até o fim. Cancelar aqui cancela lá."""
        r = self._rpc("pacs_baixar", self._id(job.node), job.study_uids[0], job.series_uids, job.label,
                      [job.dono_destino, job.visivel_destino]) or {}
        jid = (r.get("download") or {}).get("id")
        if not jid:
            raise DicomError("o servidor não aceitou o download")
        a: dict = {}
        while True:
            if job.cancel.is_set():
                self._rpc("pacs_cancelar", jid)
                return "Cancelado no servidor"
            a = self._rpc("pacs_andamento", jid) or {}
            if progress:
                progress(int(a.get("feitas") or 0), int(a.get("total") or 0),
                         "no servidor: " + str(a.get("mensagem") or ""))
            if a.get("estado") in FIM:
                break
            time.sleep(intervalo)
        if a.get("estado") == "error":
            raise DicomError(f"o servidor não conseguiu baixar: {a.get('mensagem') or ''}")
        if a.get("estado") == "cancelled":
            raise DicomError("o download foi cancelado no servidor")
        return f"{a.get('mensagem') or 'Concluído'} — no banco do servidor"
