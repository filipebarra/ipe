"""Servidor central da intranet: login, RPC do banco (medidas, listas, filmes, usuários…) e
DICOMweb (QIDO-RS, WADO-RS e STOW-RS) sobre HTTP. Roda dentro do programa (Rede → Servidor
central) ou sem janela: `ipe server`.

Autenticação: POST /api/login devolve um token (Authorization: Bearer <token>). Os endpoints
DICOMweb também aceitam Basic (usuário e senha do programa), para outros visualizadores.
"""

from __future__ import annotations

import base64
import json
import logging
import secrets
import shutil
import socket
import ssl
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from ipe import APP_ASCII, APP_NAME, __version__
from ipe.auth.backend import AuthError, LocalAuth
from ipe.auth.permissions import permissions_for
from ipe.auth.session import UserSession
from ipe.central import codec, dicomweb as DW
from ipe.central.rpc import RPC_METHODS, SERVER_STORAGE_ARG

log = logging.getLogger(__name__)
TOKEN_IDLE_S = 12 * 3600


class Bloqueado(AuthError):
    """Endereço bloqueado por senhas erradas demais (0.99.24)."""


class CentralServer:
    def __init__(self, db, repo, storage_root: Path, port: int = 8043, host: str = "0.0.0.0",
                 certfile: str = "", keyfile: str = "", name: str = ""):
        self.db, self.repo, self.storage = db, repo, Path(storage_root)
        self.auth = LocalAuth(repo)
        self.port, self.host = port, host
        self.certfile, self.keyfile = certfile, keyfile
        self.name = name or socket.gethostname()
        self.tokens: dict[str, tuple[UserSession, float]] = {}
        from ipe.network.acesso import Tentativas
        self.tentativas = Tentativas()      # 0.99.24: 5 senhas erradas em 10 min bloqueiam o endereço
        self._lock = threading.Lock()
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.on_import = None            # chamado com a lista de estudos recebidos por STOW

    # ------------------------------------------------------------------ ciclo de vida
    @property
    def running(self) -> bool:
        return self._httpd is not None

    @property
    def scheme(self) -> str:
        return "https" if self.certfile else "http"

    def start(self) -> None:
        if self._httpd is not None:
            return
        server = self

        class Handler(_Handler):
            central = server
        httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        httpd.daemon_threads = True
        if self.certfile:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(self.certfile, self.keyfile or None)
            httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        self.port = httpd.server_address[1]
        self._httpd = httpd
        self._thread = threading.Thread(target=httpd.serve_forever, name="central-http", daemon=True)
        self._thread.start()
        log.info("Servidor central em %s://%s:%d", self.scheme, self.host, self.port)

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    def serve_forever(self) -> None:
        self.start()
        try:
            while self._thread is not None and self._thread.is_alive():
                self._thread.join(1.0)
        except KeyboardInterrupt:
            self.stop()

    # ------------------------------------------------------------------ sessões
    def login(self, username: str, password: str, ip: str = "") -> tuple[str, UserSession]:
        s = self._login(username, password, ip)
        tok = secrets.token_urlsafe(32)
        with self._lock:
            self.tokens[tok] = (s, time.time())
        return tok, s

    def _login(self, username: str, password: str, ip: str = "") -> UserSession:
        """Login com limite de tentativas por endereço."""
        falta = self.tentativas.bloqueado(ip)
        if falta:
            raise Bloqueado(f"muitas senhas erradas deste computador: tente de novo em {int(falta // 60) + 1} min")
        try:
            s = self.auth.login(username, password)
        except AuthError:
            self.tentativas.errou(ip)
            raise
        self.tentativas.acertou(ip)
        return s

    def session_for(self, headers, ip: str = "") -> UserSession | None:
        h = headers.get("Authorization", "") or ""
        if h.startswith("Bearer "):
            tok = h[7:].strip()
            with self._lock:
                item = self.tokens.get(tok)
                if item is None or time.time() - item[1] > TOKEN_IDLE_S:
                    self.tokens.pop(tok, None)
                    return None
                self.tokens[tok] = (item[0], time.time())
                s = item[0]
            # permissões atualizadas (o admin pode ter mudado o perfil)
            s.perms = permissions_for(s.role, self.repo)
            return s
        if h.startswith("Basic "):
            try:
                user, _, pw = base64.b64decode(h[6:]).decode("utf-8").partition(":")
                return self._login(user, pw, ip)
            except (AuthError, ValueError):
                return None
        return None

    def logout(self, headers) -> None:
        h = headers.get("Authorization", "") or ""
        with self._lock:
            self.tokens.pop(h[7:].strip(), None)

    # ------------------------------------------------------------------ RPC
    def rpc(self, s: UserSession, method: str, args: list, kwargs: dict, client_host: str):
        if method == "whoami":
            return {"username": s.username, "full_name": s.full_name, "role": s.role, "user_id": s.user_id,
                    "perms": sorted(s.perms)}
        if method == "my_prefs":
            return self.repo.user_prefs(s.user_id) if s.user_id else {}
        if method == "save_my_prefs":
            if s.user_id:
                self.repo.save_user_prefs(s.user_id, args[0] if args else kwargs.get("prefs", {}))
            return None
        if method == "change_my_password":
            old, new = args[0], args[1]
            if self.repo.authenticate(s.username, old) is None:
                raise PermissionError("A senha atual não confere.")
            self.repo.set_password(s.user_id, new)
            return None
        need = RPC_METHODS.get(method)
        if need is None:
            raise PermissionError(f"método não permitido: {method}")
        if need and not s.can(need):
            raise PermissionError(f"seu perfil não permite ({need})")
        if method == "audit":
            action = args[0] if args else kwargs.get("action", "")
            detail = args[1] if len(args) > 1 else kwargs.get("detail", "")
            study_uid = kwargs.get("study_uid", "")
            host = kwargs.get("host", "") or client_host
            return self.repo.audit(action, detail, user=s.username, study_uid=study_uid, host=host)
        if method == "sign_report":           # quem assina é quem está logado no servidor
            rid = args[0] if args else kwargs.get("report_id")
            status = (args[2] if len(args) > 2 else kwargs.get("status", "final"))
            return self.repo.sign_report(rid, s.full_name or s.username, status)
        if method in SERVER_STORAGE_ARG:
            args = [args[0], self.storage] if args else []
            kwargs.pop("storage_root", None)
        return getattr(self.repo, method)(*args, **kwargs)

    # ------------------------------------------------------------------ STOW
    def store(self, parts: list[bytes], s: UserSession) -> dict:
        from ipe.importer.scanner import Importer
        from ipe.importer.thumbnails import generate_thumbnails
        tmp = Path(tempfile.mkdtemp(prefix="dv_stow_"))
        try:
            for i, data in enumerate(parts):
                (tmp / f"{i:06d}.dcm").write_bytes(data)
            r = Importer(self.db, self.storage).import_paths([tmp])
            try:
                generate_thumbnails(self.repo, r.new_series)
            except Exception:  # noqa: BLE001
                log.exception("miniaturas (STOW)")
            studies = sorted(r.studies)
            self.repo.audit("upload", f"{len(parts)} arquivo(s) recebidos por STOW", user=s.username)
            if self.on_import:
                try:
                    self.on_import(studies)
                except Exception:  # noqa: BLE001
                    pass
            return {"received": len(parts), "summary": r.summary(), "errors": r.errors, "studies": studies}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class _Handler(BaseHTTPRequestHandler):
    central: CentralServer = None          # definido na subclasse
    protocol_version = "HTTP/1.1"
    server_version = f"{APP_ASCII}/{__version__}"

    def log_message(self, fmt, *args) -> None:  # noqa: D401
        log.debug("HTTP %s " + fmt, self.client_address[0], *args)

    # ------------------------------------------------------------------ respostas
    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8",
              extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, obj, raw: bool = False) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8") if raw else codec.dumps(obj)
        self._send(code, body)

    def _error(self, code: int, msg: str) -> None:
        self._json(code, {"error": msg}, raw=True)

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _auth(self) -> UserSession | None:
        try:
            s = self.central.session_for(self.headers, self.client_address[0])
        except Bloqueado as e:
            self._error(429, str(e))
            return None
        if s is None:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Ipe"')
            self.send_header("Content-Type", "application/json")
            body = b'{"error": "login necessario"}'
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        return s

    # ------------------------------------------------------------------ rotas
    def do_GET(self) -> None:  # noqa: N802
        try:
            self._route("GET")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa: BLE001
            log.exception("HTTP GET")
            self._error(500, str(e))

    def do_POST(self) -> None:  # noqa: N802
        try:
            self._route("POST")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa: BLE001
            log.exception("HTTP POST")
            self._error(500, str(e))

    def _route(self, method: str) -> None:
        parts = urlsplit(self.path)
        path = unquote(parts.path).rstrip("/")
        c = self.central
        if path == "/api/ping":
            return self._json(200, {"ok": True, "app": APP_NAME, "version": __version__, "name": c.name}, raw=True)
        if path == "/api/login" and method == "POST":
            try:
                data = json.loads(self._body() or b"{}")
                tok, s = c.login(data.get("username", ""), data.get("password", ""), self.client_address[0])
            except Bloqueado as e:
                return self._error(429, str(e))
            except AuthError as e:
                c.repo.audit("login_falhou", f"{data.get('username', '')}", user=data.get("username", "?"),
                             host=self.client_address[0])
                return self._error(401, str(e))
            return self._json(200, {"token": tok, "username": s.username, "full_name": s.full_name,
                                    "role": s.role, "user_id": s.user_id, "perms": sorted(s.perms),
                                    "must_change": bool(getattr(s, "must_change", False))}, raw=True)
        s = self._auth()
        if s is None:
            return None
        if path == "/api/logout":
            c.logout(self.headers)
            return self._json(200, {"ok": True}, raw=True)
        if path == "/api/rpc" and method == "POST":
            try:
                req = codec.loads(self._body())
                res = c.rpc(s, req["method"], list(req.get("args") or []), dict(req.get("kwargs") or {}),
                            self.client_address[0])
            except PermissionError as e:
                return self._error(403, str(e))
            except (KeyError, TypeError, ValueError) as e:
                return self._error(400, f"{type(e).__name__}: {e}")
            return self._json(200, {"result": res})
        if path.startswith("/dicomweb"):
            return self._dicomweb(method, path[len("/dicomweb"):], parse_qs(parts.query), s)
        return self._error(404, "rota desconhecida")

    # ------------------------------------------------------------------ DICOMweb
    def _dicomweb(self, method: str, path: str, q: dict, s: UserSession) -> None:
        c = self.central
        seg = [p for p in path.split("/") if p]
        if method == "POST" and seg == ["studies"]:
            if not s.can("import"):
                return self._error(403, "seu perfil não permite importar")
            boundary = DW.boundary_of(self.headers.get("Content-Type", ""))
            parts = DW.split_multipart(self._body(), boundary)
            return self._json(200, c.store(parts, s), raw=True)
        if not s.can("view"):
            return self._error(403, "sem permissão")
        # QIDO-RS
        if seg == ["studies"]:
            first = lambda k: (q.get(k) or [""])[0]
            text = first("PatientName").replace("*", "") or first("PatientID") or first("AccessionNumber")
            date = first("StudyDate")
            d_from, _, d_to = date.partition("-")
            rows = c.repo.search_studies(text=text, modality=first("ModalitiesInStudy"),
                                         date_from=d_from, date_to=d_to or d_from if date else "",
                                         limit=int(first("limit") or 500))
            if first("StudyInstanceUID"):
                rows = [r for r in rows if r.study_uid == first("StudyInstanceUID")]
            return self._send(200, json.dumps([DW.study_json(r) for r in rows]).encode(), "application/dicom+json")
        if len(seg) == 3 and seg[0] == "studies" and seg[2] == "series":
            rows = c.repo.series_for_study(seg[1])
            return self._send(200, json.dumps([DW.series_json(r) for r in rows]).encode(), "application/dicom+json")
        if len(seg) == 5 and seg[0] == "studies" and seg[2] == "series" and seg[4] == "instances":
            rows = c.repo.instances_for_series(seg[3])
            return self._send(200, json.dumps([DW.instance_json(seg[1], seg[3], i) for i in rows]).encode(),
                              "application/dicom+json")
        # WADO-RS
        files: list[str] = []
        if len(seg) == 2 and seg[0] == "studies":
            files = c.repo.files_for_study(seg[1])
        elif len(seg) == 4 and seg[0] == "studies" and seg[2] == "series":
            files = c.repo.files_for_study(seg[1], [seg[3]])
        elif len(seg) == 6 and seg[4] == "instances":
            files = [i["path"] for i in c.repo.instances_for_series(seg[3]) if i["sop_uid"] == seg[5]]
        else:
            return self._error(404, "rota DICOMweb desconhecida")
        files = [f for f in files if f and Path(f).exists()]
        if not files:
            return self._error(404, "nada encontrado")
        boundary = DW.new_boundary()
        total = _multipart_length(files, boundary)
        self.send_response(200)
        self.send_header("Content-Type", f'multipart/related; type="application/dicom"; boundary={boundary}')
        self.send_header("Content-Length", str(total))
        self.end_headers()
        for chunk in DW.multipart_iter(files, boundary):
            self.wfile.write(chunk)


def _multipart_length(files, boundary: str) -> int:
    """Tamanho exato do corpo multipart (para Content-Length) sem ler os arquivos."""
    total = 0
    for p in files:
        size = Path(p).stat().st_size
        total += len((f"--{boundary}\r\nContent-Type: application/dicom\r\n"
                      f"Content-Length: {size}\r\n\r\n").encode("ascii")) + size + 2
    return total + len(f"--{boundary}--\r\n")
