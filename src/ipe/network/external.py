"""Chamada externa: link dicomviewer://, API HTTP local e registro do link no sistema.

As três portas de entrada (linha de comando, link e HTTP) geram o mesmo pedido
(dict) que a janela principal trata em handle_external(). Só abrir, buscar e
baixar são aceitos de fora; apagar e exportar nunca.

`janela=viewer` abre **só o visualizador** naquela chamada (sem o banco de dados,
sem busca no PACS, sem exportar); `janela=completo` abre o programa inteiro. Sem o
parâmetro vale a configuração de Rede.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QHostAddress, QTcpServer

log = logging.getLogger(__name__)

#: o link do programa. O antigo (dicomviewer://, de antes do nome Ipê) continua aceito e registrado:
#: botões do RIS e atalhos que já existem não quebram.
SCHEME = "ipe"
SCHEMES = ("ipe", "dicomviewer")
SAFE = re.compile(r"^[A-Za-z0-9.\-_^ ,*]{1,128}$")
PARAMS = {  # nome no link/HTTP -> chave interna
    "accession": "accession", "studyuid": "study_uid", "study_uid": "study_uid",
    "patientid": "patient_id", "patient_id": "patient_id", "node": "node", "layout": "layout",
    "janela": "janela", "window": "janela", "modo": "janela",
}
COMMANDS = {"open", "retrieve"}
# `janela=` decide, **nesta chamada**, se abre o programa inteiro ou só o visualizador. Sem o
# parâmetro vale a configuração de Rede. Assim a estação do médico segue abrindo o programa e a
# chamada do RIS para a sala de exame pede só o visualizador, sem trocar configuração nenhuma.
JANELAS = {"viewer": "viewer", "visualizador": "viewer", "so_viewer": "viewer",
           "completo": "completo", "full": "completo", "programa": "completo", "banco": "completo"}


class ExternalError(ValueError):
    pass


def payload_from_query(command: str, query: dict[str, list[str]]) -> dict:
    command = command.strip("/").lower() or "open"
    if command not in COMMANDS:
        raise ExternalError(f"comando não aceito: {command}")
    out: dict = {"command": command}
    for k, vals in query.items():
        key = PARAMS.get(k.lower())
        if key is None or not vals:
            continue
        v = unquote(vals[0]).strip()
        if not v:
            continue
        if not SAFE.match(v):
            raise ExternalError(f"valor inválido em {k}")
        if key == "janela":
            # Valor que eu não entendo não vira silêncio: quem chamou precisa saber que o pedido
            # dele não foi atendido, senão descobre pelo exame abrindo na janela errada.
            escolha = JANELAS.get(v.lower())
            if escolha is None:
                raise ExternalError(f"janela={v}: use viewer ou completo")
            v = escolha
        out[key] = v
    if not any(out.get(k) for k in ("accession", "study_uid", "patient_id")):
        raise ExternalError("informe accession, studyuid ou patientid")
    return out


def parse_url(url: str) -> dict:
    """ipe://open?accession=123&node=PACS (ou dicomviewer://…) -> pedido."""
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in SCHEMES:
        raise ExternalError("link não é ipe:// nem dicomviewer://")
    command = parts.netloc or parts.path.strip("/").split("/")[0]
    return payload_from_query(command, parse_qs(parts.query))


# ---------------------------------------------------------------------------
# API HTTP local (sem dependências: QTcpServer)
# ---------------------------------------------------------------------------

class HttpApi(QObject):
    """GET /api/status · GET /api/open?accession=… · GET /api/retrieve?… (token obrigatório)."""
    request = Signal(dict)          # pedido válido -> janela principal

    def __init__(self, handler, parent=None):
        super().__init__(parent)
        self.handler = handler          # callable(payload) -> str
        self.server = QTcpServer(self)
        self.server.newConnection.connect(self._accept)
        self.token = ""
        self.allow_remote = False
        self.allowed_ips: set[str] = set()
        self.error = ""

    def start(self, port: int, token: str, allow_remote: bool = False, allowed_ips=()) -> bool:
        self.stop()
        self.token, self.allow_remote = token, allow_remote
        self.allowed_ips = {ip.strip() for ip in allowed_ips if ip.strip()}
        addr = QHostAddress(QHostAddress.AnyIPv4 if allow_remote else QHostAddress.LocalHost)
        if not self.server.listen(addr, port):
            self.error = self.server.errorString()
            log.error("API HTTP não iniciou na porta %d: %s", port, self.error)
            return False
        self.error = ""
        log.info("API HTTP em %s:%d", "0.0.0.0" if allow_remote else "127.0.0.1", port)
        return True

    def stop(self) -> None:
        if self.server.isListening():
            self.server.close()

    @property
    def port(self) -> int:
        return self.server.serverPort()

    def _accept(self) -> None:
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            sock.setProperty("buf", b"")
            sock.readyRead.connect(lambda s=sock: self._read(s))
            sock.disconnected.connect(sock.deleteLater)

    def _read(self, sock) -> None:
        buf = (sock.property("buf") or b"") + bytes(sock.readAll())
        sock.setProperty("buf", buf)
        if b"\r\n\r\n" not in buf and len(buf) < 8192:
            return
        status, body = self._handle(buf, sock.peerAddress())
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        head = (f"HTTP/1.1 {status}\r\nContent-Type: application/json; charset=utf-8\r\n"
                f"Content-Length: {len(data)}\r\nConnection: close\r\n\r\n").encode("ascii")
        sock.write(head + data)
        sock.flush()
        sock.disconnectFromHost()

    def _handle(self, raw: bytes, peer: QHostAddress) -> tuple[str, dict]:
        ip = peer.toString().replace("::ffff:", "")
        if not peer.isLoopback() and ip not in self.allowed_ips:
            log.warning("API HTTP: chamada recusada de %s", ip)
            return "403 Forbidden", {"ok": False, "erro": "IP não autorizado"}
        try:
            text = raw.split(b"\r\n\r\n", 1)[0].decode("latin-1")
            first, *headers = text.split("\r\n")
            method, target, _ = first.split(" ", 2)
        except ValueError:
            return "400 Bad Request", {"ok": False, "erro": "pedido inválido"}
        if method != "GET":
            return "405 Method Not Allowed", {"ok": False, "erro": "use GET"}
        parts = urlsplit(target)
        query = parse_qs(parts.query)
        token = (query.pop("token", [""])[0]
                 or next((h.split(":", 1)[1].strip().removeprefix("Bearer ").strip()
                          for h in headers if h.lower().startswith(("authorization:", "x-token:"))), ""))
        if not self.token or token != self.token:
            log.warning("API HTTP: token inválido de %s", ip)
            return "401 Unauthorized", {"ok": False, "erro": "token inválido"}
        path = parts.path.rstrip("/")
        if path == "/api/status":
            return "200 OK", {"ok": True, "status": self.handler({"command": "status"})}
        if path.startswith("/api/"):
            try:
                payload = payload_from_query(path[len("/api/"):], query)
            except ExternalError as e:
                return "400 Bad Request", {"ok": False, "erro": str(e)}
            payload["source"] = f"http:{ip}"
            result = self.handler(payload)
            return "200 OK", {"ok": result not in ("nao_encontrado", "erro"), "resultado": result}
        return "404 Not Found", {"ok": False, "erro": "use /api/open, /api/retrieve ou /api/status"}


# ---------------------------------------------------------------------------
# Registro dos links ipe:// e dicomviewer:// no sistema
# ---------------------------------------------------------------------------

def _gui_python() -> str:
    from ipe.core.runtime import app_exe
    return str(app_exe())


def unregister_url_scheme() -> str:
    """Tira o registro dos links ipe:// e dicomviewer:// deste usuário (usado ao desinstalar)."""
    if sys.platform == "win32":
        import winreg
        for esquema in SCHEMES:
            for chave in (rf"Software\Classes\{esquema}\shell\open\command",
                          rf"Software\Classes\{esquema}\shell\open",
                          rf"Software\Classes\{esquema}\shell",
                          rf"Software\Classes\{esquema}"):
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, chave)
                except OSError:
                    pass
        return "Links ipe:// e dicomviewer:// desregistrados."
    if sys.platform.startswith("linux"):
        for nome in ("ipe-url.desktop", "dicomviewer-url.desktop"):
            desk = Path.home() / ".local/share/applications" / nome
            if desk.exists():
                desk.unlink()
        return "Links ipe:// e dicomviewer:// desregistrados."
    return "Sem registro de link neste sistema."


def register_url_scheme() -> str:
    """Faz o sistema abrir links ipe:// (e os antigos dicomviewer://) com este programa."""
    if sys.platform == "win32":
        import winreg
        from ipe.core.runtime import app_command
        cmd = app_command('"%1"')
        for esquema in SCHEMES:
            base = rf"Software\Classes\{esquema}"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:Ipê")
                winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\shell\open\command") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
        return "Links ipe:// e dicomviewer:// registrados para este usuário do Windows."
    if sys.platform.startswith("linux"):
        import subprocess
        apps = Path.home() / ".local/share/applications"
        apps.mkdir(parents=True, exist_ok=True)
        from ipe.core.runtime import app_command
        # um arquivo só, com os dois esquemas; o antigo dicomviewer-url.desktop sai
        velho = apps / "dicomviewer-url.desktop"
        if velho.exists():
            velho.unlink()
        desk = apps / "ipe-url.desktop"
        mimes = "".join(f"x-scheme-handler/{e};" for e in SCHEMES)
        desk.write_text(
            "[Desktop Entry]\nType=Application\nName=Ipê\nNoDisplay=true\n"
            f"Exec={app_command('%u')}\nMimeType={mimes}\n",
            encoding="utf-8")
        try:
            for e in SCHEMES:
                subprocess.run(["xdg-mime", "default", desk.name, f"x-scheme-handler/{e}"],
                               check=False, timeout=10)
            subprocess.run(["update-desktop-database", str(apps)], check=False, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return f"Arquivo {desk} criado; rode: xdg-mime default {desk.name} x-scheme-handler/{SCHEME}"
        return "Links ipe:// e dicomviewer:// registrados (xdg-mime)."
    return "Registro automático do link só no Windows e no Linux."
