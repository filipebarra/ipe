"""Serviço de rede da interface: nó local, buscas e fila de transferências.

Tudo o que usa a rede roda fora da thread da interface (QThreadPool); os
resultados voltam por sinais Qt, que chegam na thread principal.
"""

from __future__ import annotations

import itertools
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from ipe.network.client import DicomClient, DicomError, Target
from ipe.network.print_scp import PrintScpServer
from ipe.network.server import DicomServer
from ipe.network.sink import IncomingSink

log = logging.getLogger(__name__)

STATUS_TEXT = {"waiting": "Na fila", "running": "Em andamento", "done": "Concluído",
               "error": "Erro", "cancelled": "Cancelado"}
_ids = itertools.count(1)


@dataclass
class Job:
    kind: str                       # retrieve | send | moveto (do nó direto para outro destino)
    label: str
    node: dict
    identity: dict | None = None
    study_uids: list[str] = field(default_factory=list)
    series_uids: list[str] | None = None
    open_after: bool = False
    stream: bool = False            # abrir o exame enquanto as imagens chegam
    series_plan: list = field(default_factory=list)   # séries do exame no PACS (para baixar uma a uma)
    skip: set = field(default_factory=set)            # séries que o usuário mandou não baixar
    done_series: set = field(default_factory=set)     # séries já baixadas neste trabalho
    current_series: str = ""                          # série que está vindo agora
    opened: bool = False            # já foi aberto (streaming)
    destino: str = ""               # moveto: AE para onde o nó manda
    dono_destino: str = ""          # 0.99.27: exame novo baixado vai para o banco pessoal de quem pediu
    visivel_destino: str = ""       # 0.99.36: e com quem ele é compartilhado (anterior herda do exame atual)
    novo: bool = False              # 0.99.36: o exame não estava no banco quando o download começou
    id: int = field(default_factory=lambda: next(_ids))
    status: str = "waiting"
    done: int = 0
    total: int = 0
    message: str = ""
    cancel: threading.Event = field(default_factory=threading.Event)
    started: float = 0.0
    finished: float = 0.0

    @property
    def active(self) -> bool:
        return self.status in ("waiting", "running")


class _Relay(QObject):
    done = Signal(object, object)       # resultado, erro


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], Any], relay: _Relay):
        super().__init__()
        self.fn, self.relay = fn, relay

    def run(self) -> None:
        try:
            res, err = self.fn(), None
        except Exception as e:  # noqa: BLE001
            res, err = None, e
            if not isinstance(e, DicomError):
                log.exception("Falha na operação de rede")
        try:
            self.relay.done.emit(res, err)
        except RuntimeError:            # quem pediu já fechou (janela ou teste encerrado)
            log.debug("resposta de rede descartada: destino fechado")


class NetworkService(QObject):
    received = Signal(object, str)          # ImportResult, origem (imagens que chegaram)
    job_changed = Signal(object)
    job_finished = Signal(object)
    server_status = Signal(str)
    print_received = Signal(object)     # trabalho de impressão novo (linha da lista)
    print_images = Signal(object)       # imagens comuns que chegaram na porta da impressão (0.81)
    print_status = Signal(str)

    def __init__(self, db, repo, storage, settings, parent=None):
        super().__init__(parent)
        self.db, self.repo, self.settings = db, repo, settings
        self.sink = IncomingSink(db, repo, storage, on_indexed=lambda r, o: self.received.emit(r, o))
        self.server = DicomServer(repo, self.sink, self.config)
        from ipe.printing.jobs import FOLDER as PRINT_FOLDER
        from pathlib import Path as _Path
        self.print_root = _Path(storage).parent / PRINT_FOLDER
        self.print_servers: list[PrintScpServer] = []
        self.print_port_studies: set[str] = set()
        self.client = DicomClient(timeout=int(self.config.get("timeout", 30)))
        self.jobs: list[Job] = []
        self.transfer_pool = QThreadPool(self)
        self.transfer_pool.setMaxThreadCount(max(1, int(self.config.get("max_parallel", 2))))
        self.query_pool = QThreadPool(self)
        self.query_pool.setMaxThreadCount(4)
        self._relays: set[_Relay] = set()

    def set_source(self, db, repo, storage) -> None:
        """Troca o banco de destino (troca de local): o que chegar pela rede entra no local ativo."""
        self.db, self.repo = db, repo
        self.sink = IncomingSink(db, repo, storage, on_indexed=lambda r, o: self.received.emit(r, o))
        self.server.repo = repo
        self.server.sink = self.sink
        from pathlib import Path as _Path
        from ipe.printing.jobs import FOLDER as PRINT_FOLDER
        self.print_root = _Path(storage).parent / PRINT_FOLDER
        for srv in self.print_servers:
            srv.root = self.print_root

    # ------------------------------------------------------------ configuração
    @property
    def config(self) -> dict:
        return dict(self.settings.get("dicom", {}) or {})

    @property
    def local_ae(self) -> str:
        return self.config.get("ae_title", "DICOMVIEWER")

    def start_server(self) -> bool:
        cfg = self.config
        self.server.config = cfg
        self.client.timeout = int(cfg.get("timeout", 30))
        self.transfer_pool.setMaxThreadCount(max(1, int(cfg.get("max_parallel", 2))))
        if not cfg.get("enabled", True):
            self.server.stop()
            self.server.error = ""
            self.server_status.emit(self.server.status_text())
            return False
        ok = self.server.start()
        self.server_status.emit(self.server.status_text())
        return ok

    # ------------------------------------------------------------ impressoras DICOM
    def _known_ae(self) -> list[str]:
        return [n["ae_title"] for n in self.repo.nodes(only_active=True, todos=True) if n["ae_title"]]

    def print_configs(self) -> list:
        from ipe.printing.config import all_servers
        return all_servers(self.settings)

    def start_print_servers(self) -> int:
        """Liga (ou desliga) cada servidor de impressão conforme as configurações."""
        for srv in self.print_servers:
            srv.stop()
        self.print_servers = []
        ligados = 0
        from ipe import modules as MOD
        if not MOD.ligado(getattr(self, "settings", None), "impressao"):
            return 0                       # módulo de impressão desligado: nenhuma porta recebe
        for cfg in self.print_configs():
            if not cfg.enabled:
                continue
            srv = PrintScpServer(cfg.to_dict(), self.print_root,
                                 lambda job, folder, c=cfg: self._on_print_job(job, folder, c),
                                 allowed=self._known_ae, on_store=self._on_print_store,
                                 on_images=lambda imgs, ae, host, c=cfg:
                                     self._on_print_images(imgs, ae, host, c))
            self.print_servers.append(srv)
            if srv.start():
                ligados += 1
        self.print_status.emit(self.print_status_text())
        return ligados

    # compatibilidade com o código que esperava um servidor só
    start_print_server = start_print_servers

    @property
    def print_server(self):
        return self.print_servers[0] if self.print_servers else None

    def print_status_text(self) -> str:
        ligados = [s for s in self.print_servers if s.running]
        if not self.print_servers:
            return "Impressora DICOM desligada"
        if not ligados:
            erro = next((s.error for s in self.print_servers if s.error), "")
            return f"Impressora DICOM desligada{(' — ' + erro) if erro else ''}"
        if len(ligados) == 1:
            return ligados[0].status_text()
        return f"{len(ligados)} impressoras DICOM ligadas"

    def _on_print_job(self, job, folder, cfg) -> None:
        """Chamado pela thread da impressora quando a modalidade termina de mandar o filme."""
        from ipe.printing import arrival
        from ipe.printing.receiver import store_job
        settings = getattr(self, "settings", None)
        if arrival.ligado(settings) and job.id_source not in arrival.CONFIRMADO:
            arrival.identify(job, folder, self.repo)     # antes de guardar: o exame já sai com o nome
        try:
            row = store_job(self.repo, self.sink, job, folder, self.print_root,
                            to_db=bool(getattr(cfg, "to_database", True)),
                            settings=getattr(self, "settings", None))
        except Exception:  # noqa: BLE001
            log.exception("Falha ao registrar o trabalho de impressão")
            return
        if row is not None:
            # 0.99.6: folha da mesma origem logo depois de outra (e do mesmo paciente) vira página dela
            try:
                from ipe.printing import juntar as JUN
                base = JUN.candidato(self.repo, row, settings)
                if base is not None:
                    row = JUN.juntar(self.repo, base, [row], self.sink if getattr(cfg, "to_database", True)
                                     else None, self.sink.storage) or row
            except Exception:  # noqa: BLE001 - juntar é conforto: a folha continua na lista sozinha
                log.exception("Juntar a folha ao trabalho anterior")
            self.print_received.emit(row)

    def _on_print_store(self, ds, file_meta) -> None:
        """Imagem comum mandada à porta da impressão: vai para o banco como qualquer recebida."""
        uid = str(ds.get("StudyInstanceUID", ""))
        if uid:
            self.print_port_studies.add(uid)      # o filme automático do US não repete este
        self.sink.store(ds, file_meta, origin="received")

    def _on_print_images(self, imagens, calling_ae, host, cfg) -> None:
        """Fim da conexão que mandou imagens à impressora: espera indexar e pede o filme."""
        self.sink.flush(120)
        try:
            from ipe.printing import origins as O
            O.see(self.settings, calling_ae, host, cfg.name)
        except Exception:  # noqa: BLE001
            log.exception("Origem das imagens recebidas na impressora")
        self.print_images.emit({"images": list(imagens), "calling_ae": calling_ae,
                                "remote_host": host, "server": cfg.name,
                                "my_ae": getattr(cfg, "ae_title", "") or ""})

    def refresh_acl(self) -> None:
        self.server.refresh_acl()
        for srv in self.print_servers:
            srv.refresh_acl()

    def shutdown(self) -> None:
        for j in self.jobs:
            j.cancel.set()
        self.server.stop()
        for srv in self.print_servers:
            srv.stop()
        self.transfer_pool.waitForDone(3000)
        self.query_pool.waitForDone(3000)
        self.sink.stop()

    # ------------------------------------------------------------ alvos
    @staticmethod
    def eh_web(node: dict) -> bool:
        return str(node.get("kind", "dimse")) == "dicomweb"

    def cliente(self, node: dict):
        """O cliente que fala com este nó: DIMSE ou DICOMweb.

        Os dois têm os mesmos métodos (`echo`, `find_studies`, `find_series`, `get`, `store`) e
        devolvem os mesmos dicionários, então tudo acima daqui — busca, fila de download,
        pré-busca de anteriores, chamada externa — funciona sem saber qual protocolo está embaixo.
        """
        if not self.eh_web(node):
            return self.client
        web = self.__dict__.get("_web_client")
        if web is None:
            from ipe.network.dicomweb_client import DicomWebClient
            web = self._web_client = DicomWebClient(self.client.timeout)
        web.timeout = self.client.timeout
        return web

    def target(self, node: dict, identity: dict | None = None):
        if identity:
            allowed = [x for x in str(identity.get("allowed_nodes", "")).split(",") if x.strip()]
            if allowed and str(node.get("id")) not in allowed:
                raise DicomError(f"A identidade {identity['name']} não está liberada para {node['name']}.")
        if self.eh_web(node):
            from ipe.network.dicomweb_client import WebTarget
            if identity:
                # Identidade é AE title: no DICOMweb quem identifica é usuário e senha do nó.
                raise DicomError("Identidade de AE não vale para um nó DICOMweb: "
                                 "a identificação ali é o usuário e a senha do próprio nó.")
            return WebTarget.build(node, self.client.timeout)
        return Target.build(node, self.local_ae, identity)

    def _audit_identity(self, action: str, node: dict, identity: dict | None, detail: str) -> None:
        who = f" como {identity['ae_title']} ({identity['name']})" if identity else ""
        self.repo.audit(action, f"{node['name']}{who}: {detail}")

    def identities_for(self, node: dict) -> list[dict]:
        out = []
        for i in self.repo.identities():
            allowed = [x for x in str(i.get("allowed_nodes", "")).split(",") if x.strip()]
            if not allowed or str(node.get("id")) in allowed:
                out.append(i)
        return out

    # ------------------------------------------------------------ assíncrono
    def run_async(self, fn: Callable[[], Any], on_done: Callable[[Any, Exception | None], None],
                  pool: QThreadPool | None = None) -> None:
        relay = _Relay()
        self._relays.add(relay)

        def finish(res, err) -> None:
            self._relays.discard(relay)
            try:
                on_done(res, err)
            except RuntimeError as e:
                # a janela/aba que pediu fechou antes da resposta: o widget já não existe
                if "deleted" not in str(e):
                    raise
                log.debug("resposta assíncrona descartada (quem pediu já fechou): %s", e)
        relay.done.connect(finish)
        (pool or self.query_pool).start(_Task(fn, relay))

    def echo(self, node: dict, identity: dict | None, on_done) -> None:
        def work():
            return self.cliente(node).echo(self.target(node, identity))
        self.run_async(work, on_done)

    def test_network(self, node: dict, identity: dict | None, on_done, tries: int = 3) -> None:
        """Teste rápido: responde? quanto demora? (C-ECHO). Guarda a latência no histórico do nó."""
        from ipe.network.probe import learn_latency

        def work():
            t = self.target(node, identity)
            times = []
            for _ in range(max(1, tries)):
                t0 = time.time()
                self.cliente(node).echo(t)
                times.append((time.time() - t0) * 1000)
            ms = sum(times) / len(times)
            return {"ok": True, "ms": ms, "stats": learn_latency(self.settings, node.get("id"), ms)}
        self.run_async(work, on_done)

    def search(self, nodes: list[dict], identity: dict | None, filters: dict, on_done,
               cancel: threading.Event | None = None) -> None:
        """Busca em um ou vários nós. on_done((resultados, erros), exceção).

        `cancel` para a busca no meio: o C-FIND é abortado e volta o que já tinha chegado."""
        def work():
            results, errors, seen = [], [], set()
            for node in nodes:
                if cancel is not None and cancel.is_set():
                    errors.append("Busca interrompida.")
                    break
                try:
                    t = self.target(node, identity)
                    rows = self.cliente(node).find_studies(t, cancel=cancel, **filters)
                    if identity:
                        self._audit_identity("busca", node, identity, str(filters))
                except DicomError as e:
                    errors.append(f"{node['name']}: {e}")
                    continue
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{node['name']}: {e}")
                    continue
                for r in rows:
                    if r["study_uid"] in seen:
                        continue
                    seen.add(r["study_uid"])
                    r["node_id"], r["node_name"] = node["id"], node["name"]
                    results.append(r)
            return results, errors
        self.run_async(work, on_done)

    def series(self, node: dict, identity: dict | None, study_uid: str, on_done) -> None:
        self.run_async(lambda: self.cliente(node).find_series(self.target(node, identity),
                                                              study_uid), on_done)

    # ------------------------------------------------------------ transferências
    def retrieve(self, node: dict, identity: dict | None, study_uid: str, label: str,
                 series_uids: list[str] | None = None, open_after: bool = False,
                 stream: bool = False, banco: tuple[str, str] | None = None) -> Job:
        """`banco`: (dono, visível para) do exame novo. None = a escolha de quem está logado ("Exames
        que eu importo ou baixo vão para"); a automação passa o banco da regra ou o do exame de origem
        (0.99.36)."""
        for j in self.jobs:          # não repete um download que já está na fila
            if j.active and j.kind == "retrieve" and j.study_uids == [study_uid] \
                    and j.series_uids == series_uids:
                j.open_after = j.open_after or open_after
                j.stream = j.stream or stream
                return j
        job = Job("retrieve", label, node, identity, [study_uid], series_uids, open_after, stream)
        try:
            from ipe.db import banco as B
            if self.repo.study_info(study_uid) is None:
                job.novo = True
                if banco is None:
                    job.dono_destino = B.dono_dos_novos(self.settings)
                else:
                    job.dono_destino = (banco[0] or "").strip()
                    job.visivel_destino = (banco[1] or "").strip() if job.dono_destino else ""
        except Exception:  # noqa: BLE001
            log.exception("banco do exame baixado")
        self._submit(job)
        return job

    def move_to(self, node: dict, identity: dict | None, study_uid: str, label: str, destino: str,
                series_uids: list[str] | None = None) -> Job:
        """O nó manda o exame direto para `destino` (C-MOVE); nada entra neste programa."""
        job = Job("moveto", label, node, identity, [study_uid], series_uids)
        job.destino = destino
        self._submit(job)
        return job

    def _arquivos_para_enviar(self, study_uid: str, series_uids: list[str] | None) -> list[str]:
        """Os arquivos do exame que saem para o nó. A cópia sem implante (0.97) e a segmentação de
        órgãos com a tabela (0.98) ficam só neste computador: no envio do exame inteiro elas não
        vão; só vão se a série for escolhida."""
        if series_uids:
            return self.repo.files_for_study(study_uid, series_uids)
        from ipe.ai.totalseg import series_locais as locais_seg
        from ipe.automation.implante import series_locais
        locais = series_locais(self.repo, study_uid) | locais_seg(self.repo, study_uid)
        if not locais:
            return self.repo.files_for_study(study_uid)
        resto = [s.series_uid for s in self.repo.series_for_study(study_uid) if s.series_uid not in locais]
        return self.repo.files_for_study(study_uid, resto) if resto else []

    def send(self, node: dict, identity: dict | None, study_uids: list[str], label: str,
             series_uids: list[str] | None = None) -> Job:
        job = Job("send", label, node, identity, list(study_uids), series_uids)
        self._submit(job)
        return job

    # ------------------------------------------------------------ download série a série
    def _series_plan(self, job: Job, t) -> list[dict]:
        """Lista das séries do exame no PACS — é o que permite baixar uma a uma e pular alguma.

        Sem essa lista (PACS que não responde no nível série), o download continua sendo do exame
        inteiro, e aí não dá para pular nada.
        """
        if job.series_plan:
            return job.series_plan
        try:
            series = self.cliente(job.node).find_series(t, job.study_uids[0])
        except Exception as e:  # noqa: BLE001
            log.info("Sem lista de séries para %s (%s); baixando o exame inteiro", job.label, e)
            return []
        if job.series_uids:                       # o usuário escolheu algumas séries na busca
            escolhidas = set(job.series_uids)
            series = [s for s in series if s["series_uid"] in escolhidas]
        job.series_plan = series
        self.job_changed.emit(job)
        return series

    def _retrieve_by_series(self, job: Job, plano: list[dict], baixar, progress) -> int:
        """Baixa série por série, respeitando as que o usuário mandou pular no meio do caminho."""
        total = sum(int(s.get("num_images") or 0) for s in plano) or len(plano)
        feitos = 0
        n = 0
        for s in plano:
            if job.cancel.is_set():
                break
            uid_s = s["series_uid"]
            if uid_s in job.skip:
                job.done_series.add(uid_s)
                continue
            job.current_series = uid_s
            self.job_changed.emit(job)
            base = feitos

            def prog(done: int, _total: int, msg: str, base=base) -> None:
                progress(base + done, total, msg)
            try:
                n += baixar([uid_s], prog)
            except DicomError as e:
                if job.cancel.is_set():
                    raise
                log.warning("Série %s falhou (%s); segue para a próxima", uid_s, e)
                job.message = f"Série {s.get('series_number', '')} falhou: {e}"
            feitos += int(s.get("num_images") or 0) or 1
            job.done_series.add(uid_s)
            job.current_series = ""
            self.job_changed.emit(job)
        return n

    def skip_series(self, job: Job, series_uid: str) -> bool:
        """Não baixar esta série. Só vale para as que ainda não vieram."""
        if series_uid in job.done_series or series_uid == job.current_series:
            return False
        job.skip.add(series_uid)
        self.job_changed.emit(job)
        return True

    def job_for_study(self, study_uid: str) -> Job | None:
        """Download em andamento deste exame (o viewer usa para mostrar o que falta)."""
        for j in self.jobs:
            if j.kind == "retrieve" and j.active and study_uid in j.study_uids:
                return j
        return None

    def cancel(self, job: Job) -> None:
        if job.active:
            job.cancel.set()
            job.message = "Cancelando…"
            self.job_changed.emit(job)

    def clear_finished(self) -> None:
        self.jobs = [j for j in self.jobs if j.active]

    def active_jobs(self) -> list[Job]:
        return [j for j in self.jobs if j.active]

    def _submit(self, job: Job) -> None:
        self.jobs.append(job)
        self.job_changed.emit(job)

        def progress(done: int, total: int, msg: str) -> None:
            job.done, job.total, job.message = done, total, msg
            self.job_changed.emit(job)

        def work():
            if job.cancel.is_set():
                return None
            job.status, job.started = "running", time.time()
            self.job_changed.emit(job)
            t = self.target(job.node, job.identity)
            if job.kind == "moveto":
                if self.eh_web(job.node):
                    raise DicomError("Nó DICOMweb não faz C-MOVE: não dá para mandar dele para outro destino.")
                from ipe.network.gestao import Fonte, Remetente
                r = Remetente(self.client, self.target).mover(
                    Fonte(job.node, job.identity), job.destino, job.study_uids[0], job.series_uids,
                    progress, job.cancel)
                self._audit_identity("baixar para", job.node, job.identity,
                                     f"para {job.destino}, {r['imagens']} imagens: {job.label}")
                return r["mensagem"]
            cli = self.cliente(job.node)
            # No DICOMweb não existe C-MOVE: o download é sempre o WADO-RS, que volta pela
            # mesma conexão — é o equivalente do C-GET.
            por_move = getattr(t, "retrieve", "get") == "move" and not self.eh_web(job.node)
            if job.kind == "retrieve":
                uid = job.study_uids[0]
                if por_move:
                    self.sink.expected_studies.add(uid)

                def baixar(series, prog):
                    if por_move:
                        return cli.move(t, uid, series, prog, job.cancel)
                    return cli.get(t, uid, series, self.sink, prog, job.cancel)

                plano = self._series_plan(job, t)
                if plano:
                    n = self._retrieve_by_series(job, plano, baixar, progress)
                else:
                    n = baixar(job.series_uids, progress)
                self.sink.flush(120)
                self._audit_identity("download", job.node, job.identity, f"{job.label} ({n} imagens)")
                return f"{n} imagens baixadas"
            files = [f for uid in job.study_uids for f in self._arquivos_para_enviar(uid, job.series_uids)]
            sent, failed = cli.store(t, files, progress, job.cancel)
            self._audit_identity("envio", job.node, job.identity, f"{job.label} ({sent} imagens)")
            if failed:
                raise DicomError(f"{sent} enviadas, {failed} com falha")
            return f"{sent} imagens enviadas"

        def done(res, err) -> None:
            job.finished = time.time()
            if job.cancel.is_set() and job.status != "done":
                job.status, job.message = "cancelled", "Cancelado"
            elif err is not None:
                job.status, job.message = "error", str(err)
            else:
                job.status, job.message = "done", res or "Concluído"
                if job.kind == "retrieve" and job.dono_destino:
                    from ipe.db import banco as B
                    B.marcar_novos(self.repo, job.study_uids, job.dono_destino, job.visivel_destino)
            self.job_changed.emit(job)
            self.job_finished.emit(job)
        self.run_async(work, done, self.transfer_pool)
