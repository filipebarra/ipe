"""Cliente HTTP do servidor central (biblioteca padrão: urllib)."""

from __future__ import annotations

import json
import logging
import ssl
import urllib.error
import urllib.request
from pathlib import Path

from ipe.central import codec, dicomweb as DW

log = logging.getLogger(__name__)


class RemoteError(Exception):
    pass


class Unauthorized(RemoteError):
    pass


class RemoteClient:
    def __init__(self, url: str, verify_tls: bool = True, timeout: float = 30.0):
        self.url = url.rstrip("/")
        if "://" not in self.url:
            self.url = "http://" + self.url
        self.timeout = timeout
        self.token = ""
        self.username = ""
        self.on_unauthorized = None          # callback() -> bool (pede login de novo)
        self._ctx = None
        if self.url.startswith("https") and not verify_tls:
            self._ctx = ssl.create_default_context()
            self._ctx.check_hostname = False
            self._ctx.verify_mode = ssl.CERT_NONE

    # ------------------------------------------------------------------ HTTP
    def _open(self, path: str, data: bytes | None = None, headers: dict | None = None,
              method: str | None = None, timeout: float | None = None):
        h = dict(headers or {})
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self.url + path, data=data, headers=h, method=method)
        try:
            return urllib.request.urlopen(req, timeout=timeout or self.timeout, context=self._ctx)
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read() or b"{}").get("error", "")
            except ValueError:
                msg = ""
            if e.code == 401:
                raise Unauthorized(msg or "login necessário") from None
            raise RemoteError(msg or f"HTTP {e.code}") from None
        except (urllib.error.URLError, OSError) as e:
            raise RemoteError(f"Servidor central inacessível ({self.url}): {getattr(e, 'reason', e)}") from None

    def _retry(self, fn):
        try:
            return fn()
        except Unauthorized:
            if self.on_unauthorized is not None and self.on_unauthorized():
                return fn()
            raise

    # ------------------------------------------------------------------ sessão
    def ping(self) -> dict:
        with self._open("/api/ping", timeout=5) as r:
            return json.loads(r.read())

    def login(self, username: str, password: str) -> dict:
        body = json.dumps({"username": username, "password": password}).encode("utf-8")
        self.token = ""
        try:
            with self._open("/api/login", body, {"Content-Type": "application/json"}) as r:
                info = json.loads(r.read())
        except Unauthorized as e:
            raise Unauthorized(str(e) or "Usuário ou senha incorretos.") from None
        self.token = info["token"]
        self.username = info["username"]
        return info

    def logout(self) -> None:
        if self.token:
            try:
                self._open("/api/logout", b"{}", {"Content-Type": "application/json"}).close()
            except RemoteError:
                pass
        self.token = ""

    # ------------------------------------------------------------------ RPC
    def rpc(self, method: str, *args, **kwargs):
        body = codec.dumps({"method": method, "args": list(args), "kwargs": kwargs})

        def call():
            with self._open("/api/rpc", body, {"Content-Type": "application/json"}) as r:
                return codec.loads(r.read())["result"]
        return self._retry(call)

    # ------------------------------------------------------------------ DICOMweb
    def qido(self, path: str) -> list[dict]:
        def call():
            with self._open("/dicomweb" + path, headers={"Accept": "application/dicom+json"}) as r:
                return json.loads(r.read() or b"[]")
        return self._retry(call)

    def retrieve(self, study_uid: str, dest: Path, series_uid: str | None = None, progress=None) -> list[Path]:
        """WADO-RS: baixa o estudo (ou uma série) para `dest`, arquivo por arquivo."""
        path = f"/dicomweb/studies/{study_uid}" + (f"/series/{series_uid}" if series_uid else "")

        def call():
            r = self._open(path, headers={"Accept": 'multipart/related; type="application/dicom"'},
                           timeout=max(self.timeout, 120))
            try:
                boundary = DW.boundary_of(r.headers.get("Content-Type", ""))
                return DW.MultipartReader(r, boundary, dest, progress).run()
            finally:
                r.close()
        return self._retry(call)

    def store(self, files: list[str | Path], progress=None, batch_mb: int = 64) -> dict:
        """STOW-RS em lotes; devolve o total recebido e os estudos."""
        done, studies, errors = 0, set(), 0
        batch: list[Path] = []
        size = 0

        def flush():
            nonlocal done, errors, batch, size
            if not batch:
                return
            boundary = DW.new_boundary()
            body = b"".join(DW.multipart_iter(batch, boundary))
            ctype = f'multipart/related; type="application/dicom"; boundary={boundary}'
            with self._open("/dicomweb/studies", body, {"Content-Type": ctype}, "POST",
                            timeout=max(self.timeout, 300)) as r:
                res = json.loads(r.read())
            done += len(batch)
            errors += int(res.get("errors") or 0)
            studies.update(res.get("studies") or [])
            batch, size = [], 0
            if progress:
                progress(done)
        for f in files:
            batch.append(Path(f))
            size += Path(f).stat().st_size
            if size >= batch_mb * 1024 * 1024 or len(batch) >= 200:
                self._retry(flush)
        self._retry(flush)
        return {"sent": done, "errors": errors, "studies": sorted(studies)}
