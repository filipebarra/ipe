"""Repositório do modo cliente: o que é de todos vai para o servidor central (exames, medidas,
imagens-chave, listas, filmes, usuários, registro de acesso); os arquivos ficam num cache local
(banco e pasta próprios) e as configurações da máquina (nós DICOM, automação) continuam locais."""

from __future__ import annotations

import logging
import shutil
import tempfile
import threading
from datetime import datetime
from pathlib import Path

from ipe.central.remote import RemoteClient, RemoteError
from ipe.central.rpc import RPC_METHODS

log = logging.getLogger(__name__)

# ficam no cache local (arquivos e dados da máquina)
LOCAL_ONLY = {"instances_for_series", "series_meta", "has_thumbnail", "files_for_study", "instance_counts",
              "series_missing_details"}
# lidos do cache se o estudo já estiver no computador; senão do servidor
LOCAL_FIRST = {"series_for_study", "study_info"}


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 1e9


class ClientRepository:
    remote = True

    def __init__(self, local, client: RemoteClient, storage_root: Path, settings=None):
        self.local, self.client = local, client
        self.db = local.db
        self.storage = Path(storage_root)
        self.settings = settings
        self._upload_lock = threading.Lock()
        self.on_upload_done = None           # callback(texto)
        self._banco_pendente: dict[str, tuple[str, str]] = {}   # 0.99.28: banco de exame que ainda vai subir
        self._baixando: dict = {}            # 0.99.85: study_uid -> (thread, primeiro_lote, parar)
        self._baixar_lock = threading.Lock()
        self._andamentos: dict[str, dict] = {}  # 0.100.0: study_uid -> andamento do download, série a série
        self.on_download_status = None       # callback(texto), andamento do download
        self.progressivo = True              # abre o exame antes de terminar de baixar

    # ------------------------------------------------------------------ roteamento
    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        if name in LOCAL_FIRST:
            return lambda *a, **k: self._local_first(name, *a, **k)
        if name in RPC_METHODS and name not in LOCAL_ONLY:
            return lambda *a, **k: self.client.rpc(name, *a, **k)
        return getattr(self.local, name)

    def _local_first(self, name: str, study_uid: str, *a, **k):
        if self.is_cached(study_uid):
            return getattr(self.local, name)(study_uid, *a, **k)
        return self.client.rpc(name, study_uid, *a, **k)

    def is_cached(self, study_uid: str) -> bool:
        return bool(self.local.study_uids_present([study_uid]))

    # ------------------------------------------------------------------ especiais
    def audit(self, action: str, detail: str, user: str = "", study_uid: str = "", host: str = "") -> None:
        try:
            self.client.rpc("audit", action, detail, study_uid=study_uid, host=host)
        except RemoteError as e:
            log.warning("auditoria no servidor falhou (%s); gravando no cache", e)
            self.local.audit(action, detail, user=user or self.client.username, study_uid=study_uid)

    def set_study_scope(self, study_uids, dono: str = "", visivel_para: str = "") -> int:
        """0.99.28: no servidor (que confere as regras). Exame que ainda não subiu guarda o banco para o envio."""
        uids = list(study_uids or [])
        for u in uids:
            self._banco_pendente[u] = (dono or "", visivel_para or "")
        n = self.client.rpc("set_study_scope", uids, dono, visivel_para)
        try:
            self.local.set_study_scope(uids, dono, visivel_para)        # o cache mostra igual
        except Exception:  # noqa: BLE001
            pass
        return n

    def key_images(self, study_uid: str) -> list[dict]:
        """Do servidor, com o caminho do arquivo no cache local."""
        rows = self.client.rpc("key_images", study_uid)
        paths = self.local.paths_for_sops([r["sop_uid"] for r in rows])
        return [{**r, "path": paths[r["sop_uid"]]} for r in rows if r["sop_uid"] in paths]

    def delete_study(self, study_uid: str, storage_root=None) -> int:
        """Apaga no servidor (precisa da permissão) e no cache."""
        n = self.client.rpc("delete_study", study_uid)
        self.remove_cached(study_uid)
        return n

    def delete_instance(self, sop_uid: str, storage_root=None) -> int:
        """0.99.31: apaga a imagem no servidor (precisa da permissão) e no cache."""
        n = self.client.rpc("delete_instance", sop_uid)
        try:
            self.local.delete_instance(sop_uid, self.storage)
        except Exception:  # noqa: BLE001
            pass
        return n

    def remove_cached(self, study_uid: str) -> None:
        if self.is_cached(study_uid):
            self.local.delete_study(study_uid, self.storage)

    # ------------------------------------------------------------------ cache
    def missing_series(self, study_uid: str) -> list[str]:
        """Séries do servidor que faltam (ou estão incompletas) no cache."""
        remote = {s.series_uid: s.num_images for s in self.client.rpc("series_for_study", study_uid)}
        local = {s.series_uid: s.num_images for s in self.local.series_for_study(study_uid)} \
            if self.is_cached(study_uid) else {}
        return [u for u, n in remote.items() if local.get(u, 0) < n]

    #: 0.99.85: de quantas em quantas imagens (ou segundos) o que chegou entra no cache, para o exame
    #: abrir com as primeiras e ir crescendo enquanto o resto baixa
    LOTE_IMAGENS = 24
    LOTE_SEGUNDOS = 1.5
    #: 0.100.0: quantas séries baixam ao mesmo tempo (cada uma numa conexão)
    CONEXOES = 2

    def rede_htj2k(self) -> bool:
        """0.100.0: pedir os pixels em HTJ2K sem perda (2 a 4× menos bytes na rede). O acervo do servidor não muda."""
        return bool(self.settings.get("central.rede_htj2k", True)) if self.settings is not None else True

    def andamento(self, study_uid: str) -> dict:
        """0.100.0: o download do exame, série a série: {"series": {uid: (já no computador, total)},
        "baixando": [uids chegando agora], "fila": [uids que faltam, na ordem]}. Vazio se não está baixando."""
        a = self._andamentos.get(study_uid)
        if not a:
            return {}
        with self._baixar_lock:
            return {"series": {u: tuple(v) for u, v in a["series"].items()}, "baixando": list(a["baixando"]),
                    "fila": [s.series_uid for s in a["fila"]]}

    def priorizar(self, study_uid: str, series_uid: str) -> bool:
        """0.100.0: a série que ele pôs no quadro passa para a frente da fila do download."""
        a = self._andamentos.get(study_uid)
        if not a:
            return False
        with self._baixar_lock:
            fila = a["fila"]
            i = next((k for k, s in enumerate(fila) if s.series_uid == series_uid), -1)
            if i <= 0:
                return i == 0
            fila.insert(0, fila.pop(i))
        log.info("servidor central: série %s passou para a frente", series_uid)
        return True

    def download(self, study_uid: str, progress=None, cancel=None, primeiro_lote=None) -> int:
        """Baixa (WADO-RS) o que falta do estudo e importa no cache. Devolve arquivos baixados.

        0.99.85: série por série (na ordem do número da série), e o que chega entra no cache em
        lotes pequenos, não só no fim. `primeiro_lote` (threading.Event) é sinalizado assim que há
        imagens do exame no cache — é o que deixa o exame abrir antes de o download terminar.

        0.100.0: duas séries de cada vez (`CONEXOES`), os pixels em HTJ2K sem perda (`rede_htj2k`), e a
        importação numa linha à parte (antes, a rede parava enquanto o lote entrava no banco). O andamento de
        cada série fica em `andamento`, e `priorizar` passa uma série para a frente."""
        import queue
        import time

        from ipe.importer.scanner import Importer
        from ipe.importer.thumbnails import generate_thumbnails
        remotas = list(self.client.rpc("series_for_study", study_uid) or [])
        local = {s.series_uid: s.num_images for s in self.local.series_for_study(study_uid)} \
            if self.is_cached(study_uid) else {}
        faltam = [s for s in remotas if local.get(s.series_uid, 0) < (s.num_images or 0)]
        faltam.sort(key=lambda s: (_num(getattr(s, "series_number", None)), s.series_uid))
        if not faltam:
            self._touch(study_uid)
            if primeiro_lote is not None:
                primeiro_lote.set()
            return 0
        total = sum(int(s.num_images or 0) for s in faltam)
        htj2k = self.rede_htj2k()
        log.info("servidor central: baixando %s — %d imagem(ns) em %d série(s)%s", study_uid, total, len(faltam),
                 " (HTJ2K na rede)" if htj2k else "")
        estado = {"series": {s.series_uid: [int(local.get(s.series_uid, 0)), int(s.num_images or 0)] for s in remotas},
                  "baixando": [], "fila": list(faltam)}
        self._andamentos[study_uid] = estado
        tmp = Path(tempfile.mkdtemp(prefix="dv_cache_"))
        recebidos = {"n": 0}
        trava = threading.Lock()
        fila_imp: queue.Queue = queue.Queue()
        erro_imp: list = []

        def importador():
            imp = Importer(self.local.db, self.storage)
            while True:
                arquivos = fila_imp.get()
                if arquivos is None:
                    return
                try:
                    r = imp.import_paths(arquivos)
                    if r.new_series:
                        try:
                            generate_thumbnails(self.local, r.new_series)
                        except Exception:  # noqa: BLE001
                            log.exception("miniaturas do cache")
                except Exception as e:  # noqa: BLE001
                    log.exception("importar no cache")
                    erro_imp.append(e)
                finally:
                    for f in arquivos:
                        try:
                            Path(f).unlink()
                        except OSError:
                            pass
                if primeiro_lote is not None and self.is_cached(study_uid):
                    primeiro_lote.set()

        th_imp = threading.Thread(target=importador, name="ipe-importar-cache", daemon=True)
        th_imp.start()

        def baixar_serie(se) -> int:
            pasta = tmp / se.series_uid
            ja = {"feitos": 0, "quando": time.monotonic()}
            base = int(local.get(se.series_uid, 0))

            def chegou(n):
                with trava:
                    recebidos["n"] += 1
                    feito = recebidos["n"]
                with self._baixar_lock:
                    c = estado["series"][se.series_uid]
                    c[0] = max(c[0], min(base + n, c[1]))
                if progress:
                    progress(feito, total)
                if n - ja["feitos"] >= self.LOTE_IMAGENS or time.monotonic() - ja["quando"] >= self.LOTE_SEGUNDOS:
                    lote = [pasta / f"{i:06d}.dcm" for i in range(ja["feitos"], n)]
                    ja["feitos"], ja["quando"] = n, time.monotonic()
                    fila_imp.put(lote)

            files = self.client.retrieve(study_uid, pasta, se.series_uid, progress=chegou, htj2k=htj2k)
            fila_imp.put([pasta / f"{i:06d}.dcm" for i in range(ja["feitos"], len(files))])
            return len(files)

        def trabalhador():
            n = 0
            while not (cancel and cancel()):
                with self._baixar_lock:
                    if not estado["fila"]:
                        return n
                    se = estado["fila"].pop(0)
                    estado["baixando"].append(se.series_uid)
                try:
                    n += baixar_serie(se)
                except Exception:  # noqa: BLE001
                    log.exception("servidor central: série %s", se.series_uid)
                finally:
                    with self._baixar_lock:
                        estado["baixando"].remove(se.series_uid)
            return n

        count = 0
        try:
            if primeiro_lote is not None:
                # 0.99.85: antes de tudo, uma imagem do meio de cada série que falta — o exame abre com
                # todas as séries na tira e o protocolo de exibição monta os quadros como sempre; o
                # resto de cada série vai chegando e a aba acrescenta
                amostras = []
                for se in faltam:
                    if cancel and cancel():
                        break
                    if local.get(se.series_uid, 0):
                        continue
                    try:
                        inst = self.client.rpc("instances_for_series", se.series_uid) or []
                        if not inst:
                            continue
                        meio = inst[len(inst) // 2]["sop_uid"]
                        amostras += self.client.retrieve(study_uid, tmp / "amostras" / se.series_uid,
                                                         se.series_uid, sop_uid=meio, htj2k=htj2k)
                        with self._baixar_lock:
                            c = estado["series"][se.series_uid]
                            c[0] = max(c[0], 1)
                    except Exception:  # noqa: BLE001
                        log.debug("amostra da série %s", se.series_uid, exc_info=True)
                if amostras:
                    fila_imp.put(amostras)
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=max(1, self.CONEXOES), thread_name_prefix="ipe-baixar-serie") as ex:
                for f in [ex.submit(trabalhador) for _ in range(max(1, self.CONEXOES))]:
                    count += f.result()
        finally:
            fila_imp.put(None)
            th_imp.join()
            shutil.rmtree(tmp, ignore_errors=True)
            self._andamentos.pop(study_uid, None)
            if primeiro_lote is not None:
                primeiro_lote.set()              # terminou (ou falhou): quem espera não fica preso
        self._touch(study_uid)
        self.evict(keep={study_uid})
        return count

    def baixando(self, study_uid: str) -> bool:
        """0.99.85: o exame ainda está chegando do servidor em segundo plano?"""
        b = self._baixando.get(study_uid)
        return b is not None and b[0].is_alive()

    def baixar_em_segundo_plano(self, study_uid: str):
        """Começa (ou reaproveita) o download do exame numa linha à parte; devolve (thread, primeiro_lote,
        parar). O andamento vai para `on_download_status(texto)`."""
        with self._baixar_lock:
            b = self._baixando.get(study_uid)
            if b is not None and b[0].is_alive():
                return b
            primeiro, parar = threading.Event(), threading.Event()
            avisar = self.on_download_status or (lambda m: None)
            ultimo = {"t": 0.0}

            def andamento(n, total):
                import time
                if time.monotonic() - ultimo["t"] >= 0.5 or n >= total:
                    ultimo["t"] = time.monotonic()
                    pct = int(100 * n / total) if total else 100
                    avisar(f"Baixando do servidor central: {n} de {total} imagem(ns) ({pct}%)…")

            def trabalho():
                try:
                    n = self.download(study_uid, progress=andamento, cancel=parar.is_set, primeiro_lote=primeiro)
                    avisar(f"Exame baixado do servidor central ({n} imagem(ns)).")
                except Exception as e:  # noqa: BLE001
                    log.exception("download do servidor central")
                    avisar(f"Falha ao baixar do servidor central: {e}")
                finally:
                    primeiro.set()

            th = threading.Thread(target=trabalho, name="ipe-baixar", daemon=True)
            self._baixando[study_uid] = (th, primeiro, parar)
            th.start()
            return self._baixando[study_uid]

    def _touch(self, study_uid: str) -> None:
        try:
            self.local.mark_opened(study_uid)
        except Exception:  # noqa: BLE001
            pass

    def cache_limit_gb(self) -> float:
        return float(self.settings.get("central.cache_gb", 20) if self.settings is not None else 20)

    def cache_usage(self) -> tuple[float, list]:
        rows = self.local.search_studies(limit=1_000_000)
        return sum(r.size_mb for r in rows) / 1024, rows

    def evict(self, keep: set[str] | None = None) -> list[str]:
        """Apaga do cache os estudos abertos há mais tempo até caber no limite."""
        limit = self.cache_limit_gb()
        used, rows = self.cache_usage()
        removed = []
        if used <= limit:
            return removed
        keep = keep or set()
        for r in sorted(rows, key=lambda r: r.last_accessed or r.date_added or ""):
            if used <= limit * 0.9:
                break
            if r.study_uid in keep:
                continue
            try:
                self.local.delete_study(r.study_uid, self.storage)
                used -= r.size_mb / 1024
                removed.append(r.study_uid)
            except Exception:  # noqa: BLE001
                log.exception("limpeza do cache")
        return removed

    def ensure_local(self, study_uid: str, parent=None) -> bool:
        """Garante o estudo no cache antes de abrir (com barra de progresso se houver janela)."""
        try:
            missing = self.missing_series(study_uid)
        except RemoteError as e:
            if self.is_cached(study_uid):
                log.warning("servidor inacessível; abrindo do cache: %s", e)
                return True
            if parent is not None:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(parent, "Servidor central", str(e))
            return False
        if not missing:
            self._touch(study_uid)
            return True
        if parent is None or not self.progressivo:
            # sem janela (linha de comando, testes): baixa tudo antes de voltar, como sempre
            self.download(study_uid)
            return self.is_cached(study_uid)
        # 0.99.85: abre com as primeiras imagens e o resto continua chegando em segundo plano
        # (a aba acrescenta o que chega pela vigia de séries da janela principal)
        th, primeiro, parar = self.baixar_em_segundo_plano(study_uid)
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog
        if not primeiro.is_set():
            dlg = QProgressDialog("Baixando as primeiras imagens do servidor central…", "Cancelar", 0, 0, parent)
            dlg.setWindowTitle("Servidor central")
            dlg.setWindowModality(Qt.WindowModal)
            dlg.setMinimumDuration(400)
            dlg.canceled.connect(parar.set)
            while not primeiro.is_set() and not parar.is_set():
                QApplication.processEvents()
                primeiro.wait(0.03)
            dlg.close()
            QApplication.processEvents()
        if not self.is_cached(study_uid) and not parar.is_set():
            QMessageBox.warning(parent, "Servidor central", "Não foi possível baixar o exame do servidor central.")
        return self.is_cached(study_uid)

    # ------------------------------------------------------------------ envio ao servidor
    def upload_study(self, study_uid: str, wait: bool = False) -> None:
        """Manda ao servidor (STOW-RS) as imagens do cache que ele ainda não tem."""
        def work():
            with self._upload_lock:
                try:
                    try:
                        have = set(self.client.rpc("sop_uids_for_study", study_uid) or [])
                    except RemoteError:
                        have = set()
                    files = self.local.files_with_sops(study_uid)
                    todo = [p for sop, p in files if sop not in have and Path(p).exists()]
                    pend = self._banco_pendente.pop(study_uid, None)
                    if not todo:
                        return
                    meu = bool(pend and pend[0] and pend[0].lower() == (self.client.username or "").lower())
                    res = self.client.store(todo, banco="meu" if meu else "")
                    if pend and (pend[1] or (pend[0] and not meu)):
                        self.client.rpc("set_study_scope", [study_uid], pend[0], pend[1])
                    msg = f"{res['sent']} imagem(ns) enviadas ao servidor central."
                except Exception as e:  # noqa: BLE001
                    log.exception("envio ao servidor central")
                    msg = f"Falha ao enviar ao servidor central: {e}"
                if self.on_upload_done:
                    self.on_upload_done(msg)
        if wait:
            work()
        else:
            threading.Thread(target=work, daemon=True).start()


def upload_if_client(repo, study_uid: str) -> None:
    """Chamado depois de gravar algo novo no banco local (importação, reconstrução, SR…)."""
    fn = getattr(repo, "upload_study", None)
    if fn is not None and study_uid:
        fn(study_uid)
