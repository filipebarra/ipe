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


class ClientRepository:
    remote = True

    def __init__(self, local, client: RemoteClient, storage_root: Path, settings=None):
        self.local, self.client = local, client
        self.db = local.db
        self.storage = Path(storage_root)
        self.settings = settings
        self._upload_lock = threading.Lock()
        self.on_upload_done = None           # callback(texto)

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

    def download(self, study_uid: str, progress=None, cancel=None) -> int:
        """Baixa (WADO-RS) o que falta do estudo e importa no cache. Devolve arquivos baixados."""
        from ipe.importer.scanner import Importer
        from ipe.importer.thumbnails import generate_thumbnails
        missing = self.missing_series(study_uid)
        if not missing:
            self._touch(study_uid)
            return 0
        tmp = Path(tempfile.mkdtemp(prefix="dv_cache_"))
        count = 0
        try:
            whole = not self.is_cached(study_uid)
            targets = [None] if whole else missing
            for se in targets:
                if cancel and cancel():
                    break
                files = self.client.retrieve(study_uid, tmp / (se or "all"), se,
                                             progress=lambda n, base=count: progress and progress(base + n))
                count += len(files)
            r = Importer(self.local.db, self.storage).import_paths([tmp])
            try:
                generate_thumbnails(self.local, r.new_series)
            except Exception:  # noqa: BLE001
                log.exception("miniaturas do cache")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self._touch(study_uid)
        self.evict()
        return count

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
        if parent is None:
            self.download(study_uid)
            return self.is_cached(study_uid)
        from PySide6.QtCore import QObject, Qt, Signal
        from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

        class _B(QObject):
            prog = Signal(int)
            done = Signal(object)
        b = _B()
        dlg = QProgressDialog("Baixando do servidor central…", "Cancelar", 0, 0, parent)
        dlg.setWindowTitle("Servidor central")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(300)
        stop = threading.Event()
        dlg.canceled.connect(stop.set)
        b.prog.connect(lambda n: dlg.setLabelText(f"Baixando do servidor central… {n} imagem(ns)"))
        state: dict = {}
        b.done.connect(lambda res: state.update(res=res))

        def work():
            try:
                b.done.emit(self.download(study_uid, progress=b.prog.emit, cancel=stop.is_set))
            except Exception as e:  # noqa: BLE001
                b.done.emit(e)
        th = threading.Thread(target=work, daemon=True)
        th.start()
        while "res" not in state:
            QApplication.processEvents()
            th.join(0.03)
        QApplication.processEvents()
        dlg.close()
        if isinstance(state["res"], Exception):
            QMessageBox.warning(parent, "Servidor central", f"Não foi possível baixar o exame:\n{state['res']}")
            return self.is_cached(study_uid)
        return self.is_cached(study_uid)

    # ------------------------------------------------------------------ envio ao servidor
    def upload_study(self, study_uid: str, wait: bool = False) -> None:
        """Manda ao servidor (STOW-RS) as imagens do cache que ele ainda não tem."""
        def work():
            with self._upload_lock:
                try:
                    have = set(self.client.rpc("sop_uids_for_study", study_uid) or [])
                    files = self.local.files_with_sops(study_uid)
                    todo = [p for sop, p in files if sop not in have and Path(p).exists()]
                    if not todo:
                        return
                    res = self.client.store(todo)
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
