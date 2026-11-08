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
from ipe.central.rpc import POR_EXAME, POR_LISTA, RPC_METHODS, SERVER_STORAGE_ARG

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
        from ipe.central.leituras import Leituras
        self.leituras = Leituras()       # 0.99.31: quem está laudando cada exame
        from ipe.central.atualizacoes import Atualizacoes
        self.atualizacoes = Atualizacoes(self.storage.parent / "Atualizacoes")   # 0.99.56 (onda B1)
        self.settings = None             # 0.99.91: o visualizador web lê idioma, janelas e protocolos daqui

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
        # 0.99.56 (ondas B1 e B2): perfil da estação e atualizações — quem e qual papel vêm da sessão
        if method == "perfil_da_estacao":
            comp = str(args[0] if args else kwargs.get("computador", "") or "")
            return self.repo.perfil_da_estacao(comp, s.username, s.role)
        if method in ("salvar_estado", "estado", "esquecer_estado", "estados_anteriores"):
            # cada um tem o seu: o usuário é sempre o da sessão, nunca o que o cliente mandou
            uid = str(args[0] if args else kwargs.get("study_uid", "") or "")
            if not s.can("view"):
                raise PermissionError("seu perfil não permite (view)")
            if uid and not self.pode_ver(s, uid):
                raise PermissionError("o exame está no banco pessoal de outro usuário")
            if method == "salvar_estado":
                dados = args[1] if len(args) > 1 else kwargs.get("dados", {})
                return self.repo.salvar_estado(uid, dados, s.username)
            return getattr(self.repo, method)(uid, s.username)
        if method == "atualizacoes_todas":
            return self.atualizacoes.todas()
        if method in ("atualizacao_promover", "atualizacao_retirar"):
            if not s.can("users"):
                raise PermissionError("só quem gerencia usuários publica atualizações")
            if method == "atualizacao_promover":
                d = self.atualizacoes.promover(s.full_name or s.username)
            else:
                canal = str(args[0] if args else kwargs.get("canal", ""))
                d = self.atualizacoes.retirar(canal)
            self.repo.audit("atualizacao", f"{method}: {d}", user=s.username, host=client_host)
            return d
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
        # 0.99.31 (onda A1): trava de leitura do laudo
        if method == "leitura_comecar":
            uid = args[0] if args else kwargs.get("study_uid", "")
            forcar = bool(args[1] if len(args) > 1 else kwargs.get("forcar", False))
            if not self.pode_ver(s, uid):
                raise PermissionError("o exame está no banco pessoal de outro usuário")
            r = self.leituras.comecar(uid, s.username, s.full_name, forcar)
            if r.get("assumiu_de"):
                self.repo.audit("assumiu_laudo", f"o laudo estava com {r['assumiu_de']}", user=s.username,
                                study_uid=uid, host=client_host)
            return r
        if method == "leitura_manter":
            return self.leituras.manter(args[0] if args else kwargs.get("study_uids", []), s.username)
        if method == "leitura_terminar":
            return self.leituras.terminar(args[0] if args else kwargs.get("study_uid", ""), s.username)
        if method == "leituras_ativas":
            return self.leituras.ativas()
        if method in ("save_report", "sign_report", "delete_report"):
            if method == "save_report":
                uid = str(((args[0] if args else kwargs.get("data")) or {}).get("study_uid", ""))
            else:
                rep = self.repo.report(args[0] if args else kwargs.get("report_id"))
                uid = (rep or {}).get("study_uid", "")
            motivo = self.leituras.bloqueia(uid, s.username) if uid else ""
            if motivo:
                raise PermissionError(motivo + " (para gravar, abra o laudo e escolha assumir)")
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
        # 0.99.28: o banco pessoal vale também no servidor — exame de outro banco não sai daqui
        alvo = ""
        if method in POR_EXAME:
            alvo = str(args[0] if args else kwargs.get("study_uid", "") or "")
        elif method == "save_report":
            alvo = str(((args[0] if args else kwargs.get("data")) or {}).get("study_uid", ""))
        elif method == "save_annotation":
            alvo = str(kwargs.get("study_uid", ""))
        elif method == "delete_instance" and args:
            alvo = self.repo.study_of_sop(str(args[0]))
        if alvo and not self.pode_ver(s, alvo):
            raise PermissionError("o exame está no banco pessoal de outro usuário")
        if method in POR_LISTA and (args or kwargs.get("list_id") is not None):
            lid = args[0] if args else kwargs.get("list_id")
            v = self._visao(s)
            info = self.repo.case_list_info(lid) if v is not None and not v.admin else None
            from ipe.auth import visibilidade as V
            if info is not None and not V.visivel(info, v):
                raise PermissionError("a lista é pessoal de outro usuário")
        if method == "set_study_scope":
            return self.mudar_banco(s, *args, **kwargs)
        if method == "search_studies":              # "todos" e o banco de outro: só o administrador
            v = self._visao(s)
            b = str(kwargs.get("banco", args[5] if len(args) > 5 else "visivel") or "visivel")
            if v is not None and not v.admin and (b == "todos" or b.startswith("usuario:")):
                args = list(args[:5])
                kwargs["banco"] = "visivel"
        if method == "retirar_do_servidor":
            return self.retirar(s, alvo)
        if method == "receber_dados_do_exame":     # o banco do exame não muda por aqui (só por set_study_scope)
            pac = args[0] if args else kwargs.get("pacote_", {})
            if pac.get("study_uid") and not self.pode_ver(s, pac["study_uid"]):
                raise PermissionError("o exame está no banco pessoal de outro usuário")
            return self.repo.receber_dados_do_exame(pac, escopo=False)
        if method in SERVER_STORAGE_ARG:
            args = [args[0], self.storage] if args else []
            kwargs.pop("storage_root", None)
        from ipe.auth.visibilidade import com_visao
        with com_visao(s):                    # 0.99.26: o cliente enxerga o que ele vê, não o que a tela do servidor vê
            return getattr(self.repo, method)(*args, **kwargs)

    # ------------------------------------------------------------------ banco pessoal (0.99.28)
    @staticmethod
    def _visao(s):
        from ipe.auth import visibilidade as V
        with V.com_visao(s):
            return V.visao_atual()

    def pode_ver(self, s: UserSession, study_uid: str) -> bool:
        """O dono, quem ele escolheu, o compartilhado — e o administrador (decisão dele)."""
        from ipe.auth import visibilidade as V
        v = self._visao(s)
        if v is None or v.admin:
            return True
        info = self.repo.study_info(study_uid)
        return info is None or V.visivel(info, v)

    def mudar_banco(self, s: UserSession, study_uids, dono: str = "", visivel_para: str = "") -> int:
        """As mesmas regras do botão direito ▸ Banco: o dono mexe no que é dele; tirar do compartilhado
        pede a permissão de configurar; passar para o banco de outro só o administrador."""
        v = self._visao(s)
        dono = (dono or "").strip()
        if v is not None and not v.admin and dono and dono.lower() != v.usuario.lower():
            raise PermissionError("só o administrador põe exame no banco de outro usuário")
        ok = []
        for uid in study_uids or []:
            info = self.repo.study_info(uid)
            if info is None:
                continue
            atual = (info.get("dono") or "").lower()
            if v is None or v.admin or atual == v.usuario.lower() or (not atual and (not dono or s.can("configure"))):
                ok.append(uid)
        n = self.repo.set_study_scope(ok, dono, visivel_para) if ok else 0
        if n:
            self.repo.audit("moveu_banco", f"{n} exame(s) para o " + (f"banco pessoal de {dono}" if dono
                            else "compartilhado") + " (pelo servidor)", user=s.username,
                            study_uid=ok[0] if len(ok) == 1 else "")
        return n

    def retirar(self, s: UserSession, study_uid: str) -> int:
        """Tira do servidor um exame pessoal que o dono levou para o computador dele."""
        v = self._visao(s)
        info = self.repo.study_info(study_uid)
        if info is None:
            return 0
        if v is not None and not v.admin and (info.get("dono") or "").lower() != v.usuario.lower():
            raise PermissionError("só o dono (ou o administrador) tira o exame pessoal do servidor")
        if v is not None and not v.admin and not info.get("dono"):
            raise PermissionError("exame do compartilhado: tirar do servidor pede a permissão de apagar")
        n = self.repo.delete_study(study_uid, self.storage)
        self.repo.audit("retirou_do_servidor", f"levado para o computador de {s.username}", user=s.username,
                        study_uid=study_uid)
        return n

    # ------------------------------------------------------------------ STOW
    def store(self, parts: list[bytes], s: UserSession, banco: str = "") -> dict:
        """STOW. `banco` = "meu": os exames **novos** já entram no banco pessoal de quem mandou (0.99.28)."""
        from ipe.importer.scanner import Importer
        from ipe.importer.thumbnails import generate_thumbnails
        tmp = Path(tempfile.mkdtemp(prefix="dv_stow_"))
        try:
            uids = set()
            for i, data in enumerate(parts):
                (tmp / f"{i:06d}.dcm").write_bytes(data)
                if banco == "meu":
                    uids.add(_study_uid_de(tmp / f"{i:06d}.dcm"))
            uids.discard("")
            ja = set(self.repo.study_uids_present(list(uids))) if uids else set()
            r = Importer(self.db, self.storage).import_paths([tmp])
            if banco == "meu" and s.username:
                novos = sorted(uids - ja)
                if novos:
                    self.repo.set_study_scope(novos, s.username, "")
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
        from ipe.central import web as WEB
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        cab = WEB.cabecalhos(bool(self.central.certfile), pagina=ctype.startswith("text/html"))
        cab.update(extra or {})
        for k, v in cab.items():
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
            if not self.headers.get("X-Ipe-Web"):        # 0.99.91: no site, sem a janela de senha do navegador
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
        if path == "/api/ac" and method == "GET":         # 0.99.74: a AC interna, para o cliente confiar (público)
            from ipe.core.certificados import ac_ao_lado
            pem = ac_ao_lado(c.certfile)
            if pem is None:
                return self._error(404, "este servidor não tem AC interna")
            return self._send(200, pem, "application/x-pem-file")
        if path == "/web" or path.startswith("/web/"):                   # 0.99.91: o visualizador web (público)
            from ipe.central import web as WEB
            bruto = unquote(parts.path)
            if bruto == "/web":
                return self._send(301, b"", "text/plain", {"Location": "/web/"})
            achado = WEB.arquivo_estatico(bruto[len("/web/"):])
            if achado is None:
                return self._error(404, "arquivo do site não encontrado" if WEB.site_instalado()
                                   else "o visualizador web não está instalado neste servidor")
            return self._send(200, achado[0], achado[1])
        if path == "" and method == "GET":
            return self._send(302, b"", "text/plain", {"Location": "/web/"})
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
        if path == "/api/web/config" and method == "GET":
            from ipe.central import web as WEB
            prefs = c.repo.user_prefs(s.user_id) if s.user_id else {}
            return self._json(200, WEB.configuracao(c.settings, prefs, {
                "username": s.username, "full_name": s.full_name, "role": s.role, "perms": sorted(s.perms)}), raw=True)
        if path == "/api/web/abriu" and method == "POST":
            data = json.loads(self._body() or b"{}")
            uid = str(data.get("study_uid", ""))
            if uid and c.pode_ver(s, uid):
                c.repo.audit("web_abriu", f"abriu no navegador: {uid}", user=s.username, host=self.client_address[0])
            return self._json(200, {"ok": True}, raw=True)
        if path.startswith("/api/atualizacao"):
            return self._atualizacao(method, path, parse_qs(parts.query), s)
        if path.startswith("/dicomweb"):
            return self._dicomweb(method, path[len("/dicomweb"):], parse_qs(parts.query), s)
        return self._error(404, "rota desconhecida")

    # ------------------------------------------------------------------ atualizações (0.99.56, onda B1)
    def _atualizacao(self, method: str, path: str, q: dict, s: UserSession) -> None:
        c = self.central
        first = lambda k: (q.get(k) or [""])[0]          # noqa: E731
        canal = first("canal") or "estavel"
        if canal not in ("estavel", "teste"):
            return self._error(400, "canal desconhecido")
        if method == "GET" and path == "/api/atualizacao":
            return self._json(200, c.atualizacoes.info(canal) or {}, raw=True)
        if method == "GET" and path == "/api/atualizacao/pacote":
            arq = c.atualizacoes.caminho(canal)
            if arq is None:
                return self._error(404, "nenhum pacote neste canal")
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(arq.stat().st_size))
            self.end_headers()
            with open(arq, "rb") as f:
                shutil.copyfileobj(f, self.wfile, 1 << 20)
            return None
        if method == "POST" and path == "/api/atualizacao":
            if not s.can("users"):
                return self._error(403, "só quem gerencia usuários publica atualizações")
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0:
                return self._error(400, "pacote vazio")
            tmp = Path(tempfile.mkdtemp(prefix="ipe_atualiza_"))
            try:
                arq = tmp / "pacote"
                with open(arq, "wb") as f:                   # em pedaços: o instalador tem centenas de MB
                    falta = n
                    while falta > 0:
                        bloco = self.rfile.read(min(falta, 1 << 20))
                        if not bloco:
                            break
                        f.write(bloco)
                        falta -= len(bloco)
                try:
                    d = c.atualizacoes.publicar(arq, first("nome") or "pacote", first("versao"), canal,
                                                first("notas"), s.full_name or s.username)
                except ValueError as e:
                    return self._error(400, str(e))
                c.repo.audit("atualizacao", f"publicou {d['versao']} no canal {canal}", user=s.username,
                             host=self.client_address[0])
                return self._json(200, d, raw=True)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
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
            banco = (self.headers.get("X-Ipe-Banco", "") or "").strip().lower()
            return self._json(200, c.store(parts, s, banco=banco), raw=True)
        if not s.can("view"):
            return self._error(403, "sem permissão")
        if len(seg) >= 2 and seg[0] == "studies" and not c.pode_ver(s, seg[1]):
            return self._error(404, "nada encontrado")        # 0.99.28: exame do banco pessoal de outro
        # QIDO-RS
        if seg == ["studies"]:
            first = lambda k: (q.get(k) or [""])[0]
            text = first("PatientName").replace("*", "") or first("PatientID") or first("AccessionNumber")
            date = first("StudyDate")
            d_from, _, d_to = date.partition("-")
            from ipe.auth.visibilidade import com_visao
            with com_visao(s):                # 0.99.28: a busca vê o que quem pede vê
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
        # 0.99.91: o que o visualizador web pede (metadados, quadros, miniatura)
        if len(seg) == 5 and seg[0] == "studies" and seg[2] == "series" and seg[4] == "metadata":
            from ipe.central import web as WEB
            meta = WEB.metadados_da_serie(c.repo, seg[1], seg[3], "/dicomweb")
            if not meta:
                return self._error(404, "nada encontrado")
            return self._send(200, json.dumps(meta).encode(), "application/dicom+json")
        if len(seg) == 5 and seg[0] == "studies" and seg[2] == "series" and seg[4] == "thumbnail":
            png = next((r.thumbnail for r in c.repo.series_for_study(seg[1]) if r.series_uid == seg[3]), None)
            if not png:                                       # ainda não feita: faz agora (a do Ipê)
                from ipe.importer.thumbnails import generate_thumbnails
                try:
                    generate_thumbnails(c.repo, [seg[3]])
                except Exception:  # noqa: BLE001
                    log.exception("miniatura (web)")
                png = next((r.thumbnail for r in c.repo.series_for_study(seg[1]) if r.series_uid == seg[3]), None)
            if not png:
                return self._error(404, "sem miniatura")
            return self._send(200, bytes(png), "image/png")
        if len(seg) == 8 and seg[0] == "studies" and seg[4] == "instances" and seg[6] == "frames":
            from ipe.central import web as WEB
            caminho = WEB.CAMINHOS.da_serie(c.repo, seg[3]).get(seg[5])
            if not caminho or not Path(caminho).exists():
                return self._error(404, "nada encontrado")
            try:
                numeros = [int(x) for x in seg[7].split(",") if x.strip()]
                partes = WEB.quadros(caminho, numeros)
            except (ValueError, IndexError) as e:
                return self._error(400, str(e))
            boundary = DW.new_boundary()
            corpo = WEB.multipart_quadros(partes, boundary)
            return self._send(200, corpo, f'multipart/related; type="application/octet-stream"; boundary={boundary}')
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


def _study_uid_de(path) -> str:
    try:
        import pydicom
        return str(pydicom.dcmread(str(path), stop_before_pixels=True, specific_tags=["StudyInstanceUID"],
                                   force=True).get("StudyInstanceUID", "") or "")
    except Exception:  # noqa: BLE001
        return ""


def _multipart_length(files, boundary: str) -> int:
    """Tamanho exato do corpo multipart (para Content-Length) sem ler os arquivos."""
    total = 0
    for p in files:
        size = Path(p).stat().st_size
        total += len((f"--{boundary}\r\nContent-Type: application/dicom\r\n"
                      f"Content-Length: {size}\r\n\r\n").encode("ascii")) + size + 2
    return total + len(f"--{boundary}--\r\n")
