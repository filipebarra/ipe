"""Nó DICOM local (SCP): responde C-ECHO, recebe C-STORE e serve C-FIND, C-MOVE e C-GET
a partir do banco local. Roda em threads do pynetdicom, sem travar a interface."""

from __future__ import annotations

import logging
import time
from collections import defaultdict

import pydicom
from pynetdicom import AE, ALL_TRANSFER_SYNTAXES, StoragePresentationContexts, evt
from pynetdicom.sop_class import (
    PatientRootQueryRetrieveInformationModelFind, PatientRootQueryRetrieveInformationModelGet,
    PatientRootQueryRetrieveInformationModelMove, StudyRootQueryRetrieveInformationModelFind,
    StudyRootQueryRetrieveInformationModelGet, StudyRootQueryRetrieveInformationModelMove, Verification,
)

from ipe.network import local_query
from ipe.network.contexts import STORAGE_CLASSES, UNCOMPRESSED
from ipe.network.sink import IncomingSink

log = logging.getLogger(__name__)


class DicomServer:
    def __init__(self, repo, sink: IncomingSink, config: dict):
        self.repo, self.sink = repo, sink
        self.config = dict(config)
        self._server = None
        self.error = ""
        self.recusados: list = []          # (quando, AE, IP) das conexões recusadas pelo endereço

    @property
    def running(self) -> bool:
        return self._server is not None

    @property
    def ae_title(self) -> str:
        return self.config.get("ae_title", "DICOMVIEWER")

    @property
    def port(self) -> int:
        return int(self.config.get("port", 11112))

    def status_text(self) -> str:
        if self.running:
            return f"Nó DICOM: {self.ae_title} :{self.port}"
        return f"Nó DICOM desligado{(' — ' + self.error) if self.error else ''}"

    # ------------------------------------------------------------ ciclo de vida
    def start(self) -> bool:
        self.stop()
        ae = AE(ae_title=self.ae_title)
        ae.maximum_pdu_size = 0
        t = int(self.config.get("timeout", 30))
        ae.acse_timeout = ae.dimse_timeout = ae.network_timeout = t
        ae.maximum_associations = 20
        for cx in (Verification, PatientRootQueryRetrieveInformationModelFind,
                   StudyRootQueryRetrieveInformationModelFind, PatientRootQueryRetrieveInformationModelMove,
                   StudyRootQueryRetrieveInformationModelMove):
            ae.add_supported_context(cx)
        for cx in (PatientRootQueryRetrieveInformationModelGet, StudyRootQueryRetrieveInformationModelGet):
            ae.add_supported_context(cx)
        # armazenamento; no C-GET quem pede vira SCP de armazenamento na mesma associação
        for uid in {cx.abstract_syntax for cx in StoragePresentationContexts} | set(STORAGE_CLASSES):
            ae.add_supported_context(uid, ALL_TRANSFER_SYNTAXES, scu_role=True, scp_role=True)
        self._ae = ae
        self.refresh_acl()
        handlers = [(evt.EVT_ESTABLISHED, self._on_established),
                    (evt.EVT_C_ECHO, self._on_echo), (evt.EVT_C_STORE, self._on_store),
                    (evt.EVT_C_FIND, self._on_find), (evt.EVT_C_MOVE, self._on_move),
                    (evt.EVT_C_GET, self._on_get)]
        try:
            self._server = ae.start_server(("", self.port), block=False, evt_handlers=handlers)
            self.error = ""
            log.info("Nó DICOM ligado: %s na porta %d", self.ae_title, self.port)
            return True
        except OSError as e:
            self._server = None
            self.error = f"porta {self.port} ocupada ou bloqueada ({e.strerror or e})"
            log.error("Não foi possível ligar o nó DICOM: %s", e)
            return False

    def stop(self) -> None:
        if self._server is not None:
            try:
                self._server.shutdown()
            except Exception:  # noqa: BLE001
                pass
            self._server = None
            log.info("Nó DICOM desligado")

    def refresh_acl(self) -> None:
        """Só nós cadastrados podem se conectar (a menos que "aceitar qualquer AE")."""
        ae = getattr(self, "_ae", None)
        if ae is None:
            return
        if self.config.get("accept", "known") == "any":
            ae.require_calling_aet = []
        else:
            known = [n["ae_title"] for n in self.repo.nodes(only_active=True, todos=True) if n["ae_title"]]
            ae.require_calling_aet = known or ["-NENHUM-"]

    def aceita_endereco(self, ae_title: str, ip: str) -> bool:
        """Com "Só nós cadastrados, conferindo o IP" (0.99.24), o aparelho tem de estar no endereço
        do nó cadastrado com aquele AE: o AE Title sozinho qualquer um na rede imita."""
        if self.config.get("accept", "known") != "known_ip":
            return True
        from ipe.network.acesso import ip_do_no_confere
        try:
            nodes = self.repo.nodes(only_active=True, todos=True)
        except Exception:  # noqa: BLE001
            return False
        return ip_do_no_confere(nodes, ae_title, ip)

    def _on_established(self, event) -> None:
        a = event.assoc
        ae_title = str(a.requestor.ae_title or "").strip()
        ip = str(a.requestor.address or "")
        if not self.aceita_endereco(ae_title, ip):
            log.warning("Nó DICOM: recusado %s de %s — o endereço não é o do nó cadastrado", ae_title, ip)
            self.recusados.append((time.time(), ae_title, ip))
            del self.recusados[:-50]
            a.abort()

    # ------------------------------------------------------------ serviços
    def _on_echo(self, event) -> int:
        log.info("C-ECHO de %s", event.assoc.requestor.ae_title)
        return 0x0000

    @staticmethod
    def remetente(event) -> dict:
        """AE de quem mandou, endereço e o AE **nosso** que ele chamou (o nó aceita qualquer AE
        chamado: o AE principal, uma identidade ou outro nome configurado na modalidade)."""
        a = event.assoc
        chamado = ""
        try:
            chamado = str(a.requestor.primitive.called_ae_title or "")
        except Exception:  # noqa: BLE001
            pass
        return {"calling_ae": str(a.requestor.ae_title or "").strip(),
                "remote_host": str(a.requestor.address or ""),
                "my_ae": (chamado or str(a.acceptor.ae_title or "")).strip()}

    def _on_store(self, event) -> int:
        try:
            self.sink.store(event.dataset, event.file_meta, origin="received",
                            remetente=self.remetente(event))
            return 0x0000
        except Exception as e:  # noqa: BLE001
            log.error("Falha ao gravar imagem recebida: %s", e)
            return 0xA700

    def _on_find(self, event):
        ident = event.identifier
        log.info("C-FIND de %s (nível %s)", event.assoc.requestor.ae_title,
                 ident.get("QueryRetrieveLevel", ""))
        try:
            for ds in local_query.find(self.repo.db, ident):
                if event.is_cancelled:
                    yield 0xFE00, None
                    return
                yield 0xFF00, ds
        except Exception:  # noqa: BLE001
            log.exception("C-FIND falhou")
            yield 0xC000, None

    def _datasets(self, files):
        for path, _c, _t in files:
            try:
                yield pydicom.dcmread(path)
            except Exception as e:  # noqa: BLE001
                log.warning("Não foi possível ler %s: %s", path, e)
                yield None

    def _on_move(self, event):
        dest = self.repo.node_by_ae(event.move_destination.decode().strip()
                                    if isinstance(event.move_destination, bytes)
                                    else str(event.move_destination).strip())
        files = local_query.files_for(self.repo.db, event.identifier)
        log.info("C-MOVE de %s para %s: %d imagens", event.assoc.requestor.ae_title,
                 event.move_destination, len(files))
        if dest is None:
            yield None, None                     # destino desconhecido -> 0xA801
            return
        yield dest["host"], int(dest["port"]), {"contexts": _contexts_for(files)}
        yield len(files)
        for ds in self._datasets(files):
            if event.is_cancelled:
                yield 0xFE00, None
                return
            yield 0xFF00, ds

    def _on_get(self, event):
        files = local_query.files_for(self.repo.db, event.identifier)
        log.info("C-GET de %s: %d imagens", event.assoc.requestor.ae_title, len(files))
        yield len(files)
        for ds in self._datasets(files):
            if event.is_cancelled:
                yield 0xFE00, None
                return
            yield 0xFF00, ds


def _contexts_for(files) -> list:
    """Contextos de apresentação para mandar exatamente estes arquivos (máx. 128)."""
    from pynetdicom import build_context
    by_class: dict[str, set[str]] = defaultdict(set)
    for _p, cls, ts in files:
        if cls:
            by_class[cls].add(ts or UNCOMPRESSED[0])
    out = []
    for cls, tss in by_class.items():
        for ts in tss:
            out.append(build_context(cls, [ts]))
        out.append(build_context(cls, UNCOMPRESSED))
    return out[:128]
