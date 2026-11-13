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
#: 0.100.32: apelidos — outros nomes de link que abrem o Ipê (osirix://, horos://…), para o RIS que já tem o botão
#: de outro visualizador. Ficam em Rede ▸ Chamada externa ("dicom.link_apelidos").
APELIDO = re.compile(r"^[a-z][a-z0-9+.\-]{1,31}$")
#: nomes que são de outros programas do sistema: nunca viram apelido
RESERVADOS = {"http", "https", "file", "ftp", "mailto", "tel", "sms", "ssh", "data", "javascript", "about", "blob",
              "ws", "wss", "smb", "afp", "vnc", "x-apple", "facetime", "itms", "macappstore"}


def apelidos_validos(valor) -> list[str]:
    """A lista de apelidos como o usuário digitou (lista ou texto com vírgulas) -> só os que valem, sem repetir."""
    if isinstance(valor, str):
        valor = re.split(r"[,;\s]+", valor)
    out: list[str] = []
    for a in valor or ():
        a = str(a).strip().lower().rstrip(":/")
        if APELIDO.match(a) and a not in RESERVADOS and a not in SCHEMES and a not in out:
            out.append(a)
    return out


def esquemas(settings=None) -> tuple[str, ...]:
    """ipe, dicomviewer e os apelidos configurados."""
    if settings is None:
        try:
            from ipe.core.config import Settings, get_paths
            settings = Settings(get_paths().settings_file)
        except Exception:  # noqa: BLE001
            return SCHEMES
    try:
        extra = apelidos_validos((settings.get("dicom", {}) or {}).get("link_apelidos") or [])
    except Exception:  # noqa: BLE001
        extra = []
    return SCHEMES + tuple(extra)


def e_link(texto: str, settings=None) -> bool:
    """O argumento da linha de comando é um link nosso (ipe://, dicomviewer:// ou um apelido)?"""
    m = re.match(r"^([A-Za-z][A-Za-z0-9+.\-]*):", str(texto or ""))
    return bool(m) and m.group(1).lower() in esquemas(settings)


SAFE = re.compile(r"^[A-Za-z0-9.\-_^ ,*:+]{1,512}$")
PARAMS = {  # nome no link/HTTP -> chave interna
    "accession": "accession", "studyuid": "study_uid", "study_uid": "study_uid",
    "patientid": "patient_id", "patient_id": "patient_id", "node": "node", "layout": "layout",
    "janela": "janela", "window": "janela", "modo": "janela",
    # 0.99.31 (onda A2): os nomes do perfil IHE Invoke Image Display e os filtros do Weasis ViewerHub
    "accessionnumber": "accession", "requesttype": "tipo",
    "mostrecentresults": "recentes", "recentes": "recentes",
    "modalitiesinstudy": "modalidades", "modalidades": "modalidades",
    "lowerdatetime": "data_de", "data_de": "data_de", "upperdatetime": "data_ate", "data_ate": "data_ate",
    "containsindescription": "descricao", "descricao": "descricao",
    # 0.100.32: os nomes do link do OsiriX/Horos (osirix://?methodName=displayStudy&StudyInstanceUID=…)
    "studyinstanceuid": "study_uid",
}
#: parâmetros do IHE IID que o programa aceita e não usa (não viram erro)
IGNORADOS = {"viewertype", "diagnosticquality", "keyimagesonly", "methodname"}
#: 0.100.32: o que o methodName do link do OsiriX/Horos pede -> o nosso comando (baixar de URL não é aceito)
METODOS_OSIRIX = {"displaystudy": "open", "displaystudies": "open", "displayseries": "open", "openstudy": "open",
                  "retrieve": "retrieve", "retrievestudy": "retrieve"}
COMMANDS = {"open", "retrieve", "iheinvokeimagedisplay"}
# `janela=` decide, **nesta chamada**, se abre o programa inteiro ou só o visualizador. Sem o
# parâmetro vale a configuração de Rede. Assim a estação do médico segue abrindo o programa e a
# chamada do RIS para a sala de exame pede só o visualizador, sem trocar configuração nenhuma.
JANELAS = {"viewer": "viewer", "visualizador": "viewer", "so_viewer": "viewer",
           "completo": "completo", "full": "completo", "programa": "completo", "banco": "completo"}


class ExternalError(ValueError):
    pass


def _junta(vals: list[str]) -> str:
    """IHE IID: o parâmetro pode vir repetido ou com vírgulas (vários exames, vários IDs)."""
    return ",".join(x.strip() for v in vals for x in unquote(v).split(",") if x.strip())


def payload_from_query(command: str, query: dict[str, list[str]]) -> dict:
    command = command.strip("/").lower()
    if not command:
        metodo = next((unquote(v[0]).strip() for k, v in query.items() if k.lower() == "methodname" and v), "")
        if metodo:                                   # link no formato do OsiriX/Horos
            command = METODOS_OSIRIX.get(metodo.lower(), "")
            if not command:
                raise ExternalError(f"methodName não aceito: {metodo}")
    command = command or "open"
    if command not in COMMANDS:
        raise ExternalError(f"comando não aceito: {command}")
    if command == "iheinvokeimagedisplay":          # IHE IID: abre (requestType diz paciente ou exame)
        command = "open"
    out: dict = {"command": command}
    cifrado = (query.get("c") or [""])[0]
    if cifrado:                                      # 0.99.31: link cifrado — a janela abre com o token
        out["cifrado"] = unquote(cifrado).strip()
        return out
    for k, vals in query.items():
        key = PARAMS.get(k.lower())
        if key is None or not vals:
            if k.lower() not in IGNORADOS and k.lower() not in ("token", "c"):
                log.debug("parâmetro ignorado na chamada externa: %s", k)
            continue
        v = _junta(vals) if key in ("study_uid", "patient_id", "accession", "modalidades") else unquote(vals[0]).strip()
        if not v:
            continue
        if not SAFE.match(v):
            raise ExternalError(f"valor inválido em {k}")
        if key == "patient_id":                      # IHE: 123^^^EMISSOR — o emissor não é usado
            v = ",".join(x.split("^^^")[0].strip() for x in v.split(",") if x.split("^^^")[0].strip())
        if key == "recentes":
            if not v.isdigit():
                raise ExternalError(f"{k}={v}: use um número")
        if key in ("data_de", "data_ate"):
            v = re.sub(r"[^0-9]", "", v)[:8]
            if len(v) != 8:
                raise ExternalError(f"{k}: use AAAAMMDD ou AAAA-MM-DD")
        if key == "tipo":
            v = v.upper()
            if v not in ("PATIENT", "STUDY"):
                raise ExternalError("requestType: use PATIENT ou STUDY")
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


def tem_filtro(pedido: dict) -> bool:
    return any(pedido.get(k) for k in ("recentes", "modalidades", "data_de", "data_ate", "descricao"))


def _sem_acento(t: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()


def filtrar_estudos(estudos: list[dict], pedido: dict) -> list[dict]:
    """Os filtros do pedido (IHE IID / ViewerHub) sobre exames {study_date, modalities, description},
    do mais recente para o mais antigo. Sem `recentes`, vêm todos os que passam."""
    mods = {m.strip().upper() for m in str(pedido.get("modalidades", "") or "").split(",") if m.strip()}
    de, ate = str(pedido.get("data_de", "") or ""), str(pedido.get("data_ate", "") or "")
    desc = _sem_acento(str(pedido.get("descricao", "") or ""))
    out = []
    for e in estudos:
        data = str(e.get("study_date", "") or "")
        if de and (not data or data < de):
            continue
        if ate and (not data or data > ate):
            continue
        if mods:
            tem = {m.strip().upper() for m in re.split(r"[\\/,]", str(e.get("modalities", "") or "")) if m.strip()}
            if not (tem & mods):
                continue
        if desc and desc not in _sem_acento(str(e.get("description", "") or "")):
            continue
        out.append(e)
    out.sort(key=lambda e: (str(e.get("study_date", "") or ""), str(e.get("study_time", "") or "")), reverse=True)
    n = int(pedido.get("recentes") or 0)
    return out[:n] if n > 0 else out


def parse_url(url: str, aceitos: tuple[str, ...] | None = None) -> dict:
    """ipe://open?accession=123&node=PACS (ou dicomviewer://…, ou um apelido configurado) -> pedido."""
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in (aceitos if aceitos is not None else esquemas()):
        raise ExternalError("link não é ipe:// nem dicomviewer:// (nem um apelido configurado)")
    command = parts.netloc or parts.path.strip("/").split("/")[0]
    query = parse_qs(parts.query)
    token = (query.pop("token", [""]) or [""])[0]
    payload = payload_from_query(command, query)
    if token:
        payload["link_token"] = unquote(token).strip()     # 0.99.24: link com token abre sem perguntar
    return payload


def token_confere(dado: str, esperado: str) -> bool:
    """Comparação em tempo constante (não deixa adivinhar o token pelo tempo de resposta)."""
    import hmac
    return bool(esperado) and hmac.compare_digest(str(dado or "").encode(), str(esperado).encode())


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
        if not token_confere(token, self.token):
            log.warning("API HTTP: token inválido de %s", ip)
            return "401 Unauthorized", {"ok": False, "erro": "token inválido"}
        path = parts.path.rstrip("/")
        if path.lower() in ("/iheinvokeimagedisplay", "/display"):     # 0.99.31: IHE IID e o /display do ViewerHub
            path = "/api/iheinvokeimagedisplay"
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


def unregister_url_scheme(settings=None) -> str:
    """Tira o registro dos links (ipe://, dicomviewer:// e apelidos) deste usuário (usado ao desinstalar)."""
    todos = esquemas(settings)
    if sys.platform == "win32":
        import winreg
        for esquema in todos:
            _tirar_do_registro(winreg, esquema)
        return "Links ipe:// e dicomviewer:// desregistrados."
    if sys.platform.startswith("linux"):
        for nome in ("ipe-url.desktop", "dicomviewer-url.desktop"):
            desk = Path.home() / ".local/share/applications" / nome
            if desk.exists():
                desk.unlink()
        return "Links ipe:// e dicomviewer:// desregistrados."
    if sys.platform == "darwin":
        _mac_apelidos([])
        return "Apelidos de link desregistrados (ipe:// e dicomviewer:// são do próprio aplicativo)."
    return "Sem registro de link neste sistema."


def _tirar_do_registro(winreg, esquema: str) -> None:
    for chave in (rf"Software\Classes\{esquema}\shell\open\command",
                  rf"Software\Classes\{esquema}\shell\open",
                  rf"Software\Classes\{esquema}\shell",
                  rf"Software\Classes\{esquema}"):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, chave)
        except OSError:
            pass


def _nosso_no_registro(winreg, esquema: str) -> bool:
    """O esquema está registrado para o Ipê (a marca "URL:Ipê")? Só esses são apagados quando o apelido sai."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{esquema}") as k:
            return str(winreg.QueryValueEx(k, "")[0]) == "URL:Ipê"
    except OSError:
        return False


def register_url_scheme(settings=None, antes: tuple[str, ...] | list[str] = ()) -> str:
    """Faz o sistema abrir links ipe:// (os antigos dicomviewer:// e os apelidos) com este programa.
    `antes`: os apelidos que valiam até agora — os que saíram da lista deixam de apontar para o Ipê."""
    todos = esquemas(settings)
    nomes = ", ".join(f"{e}://" for e in todos)
    sairam = [a for a in apelidos_validos(list(antes)) if a not in todos]
    if sys.platform == "win32":
        import winreg
        from ipe.core.runtime import app_command
        cmd = app_command('"%1"')
        for esquema in sairam:
            if _nosso_no_registro(winreg, esquema):
                _tirar_do_registro(winreg, esquema)
        for esquema in todos:
            base = rf"Software\Classes\{esquema}"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:Ipê")
                winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\shell\open\command") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
        return f"Links registrados para este usuário do Windows: {nomes}"
    if sys.platform.startswith("linux"):
        import subprocess
        apps = Path.home() / ".local/share/applications"
        apps.mkdir(parents=True, exist_ok=True)
        from ipe.core.runtime import app_command
        # um arquivo só, com todos os esquemas; o antigo dicomviewer-url.desktop sai
        velho = apps / "dicomviewer-url.desktop"
        if velho.exists():
            velho.unlink()
        desk = apps / "ipe-url.desktop"
        mimes = "".join(f"x-scheme-handler/{e};" for e in todos)
        desk.write_text(
            "[Desktop Entry]\nType=Application\nName=Ipê\nNoDisplay=true\n"
            f"Exec={app_command('%u')}\nMimeType={mimes}\n",
            encoding="utf-8")
        try:
            for e in todos:
                subprocess.run(["xdg-mime", "default", desk.name, f"x-scheme-handler/{e}"],
                               check=False, timeout=10)
            subprocess.run(["update-desktop-database", str(apps)], check=False, timeout=10)
        except (OSError, subprocess.SubprocessError):
            return f"Arquivo {desk} criado; rode: xdg-mime default {desk.name} x-scheme-handler/{SCHEME}"
        return f"Links registrados (xdg-mime): {nomes}"
    if sys.platform == "darwin":
        extra = [e for e in todos if e not in SCHEMES]
        feitos, falhas = _mac_apelidos(extra)
        txt = "No macOS, ipe:// e dicomviewer:// já são do aplicativo (abra o Ipê uma vez pela pasta Aplicativos)."
        if feitos:
            txt += "\nApelidos registrados: " + ", ".join(f"{e}://" for e in feitos)
        if falhas:
            txt += "\nNão deu para registrar: " + "; ".join(falhas)
        return txt
    return "Registro automático do link só no Windows, no Linux e no macOS."


# ---------------------------------------------------------------------------
# macOS: apelidos de link (0.100.32)
# ---------------------------------------------------------------------------
# ipe:// e dicomviewer:// estão no Info.plist do aplicativo. Um apelido escolhido pelo usuário não pode entrar lá
# (mexer no pacote estraga a assinatura), então cada apelido vira um aplicativo mínimo em
# ~/Applications/Ipe links/Ipe-<apelido>.app, feito com o `osacompile` do próprio macOS: ele recebe o link e o
# repassa como ipe://, que o sistema entrega ao Ipê (aberto ou não).

ROTEIRO_MAC = """on open location u
\ttry
\t\tset p to offset of ":" in u
\t\tset resto to text (p + 1) thru -1 of u
\t\tdo shell script "/usr/bin/open " & quoted form of ("ipe:" & resto)
\tend try
end open location
"""
LSREGISTER = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/"
              "lsregister")


def pasta_dos_apelidos_mac() -> Path:
    return Path.home() / "Applications" / "Ipe links"


def _mac_apelidos(apelidos: list[str], pasta: Path | None = None, rodar=None) -> tuple[list[str], list[str]]:
    """Cria um aplicativo-ponte por apelido e apaga os que saíram da lista. Devolve (feitos, falhas)."""
    import plistlib
    import shutil
    import subprocess
    pasta = pasta or pasta_dos_apelidos_mac()
    rodar = rodar or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=60))
    feitos: list[str] = []
    falhas: list[str] = []
    if pasta.is_dir():
        for velho in pasta.glob("Ipe-*.app"):
            if velho.name[4:-4] not in apelidos:
                try:
                    rodar([LSREGISTER, "-u", str(velho)])
                except Exception:  # noqa: BLE001
                    pass
                shutil.rmtree(velho, ignore_errors=True)
    for a in apelidos:
        app = pasta / f"Ipe-{a}.app"
        try:
            pasta.mkdir(parents=True, exist_ok=True)
            shutil.rmtree(app, ignore_errors=True)
            fonte = pasta / f".{a}.applescript"
            fonte.write_text(ROTEIRO_MAC, encoding="utf-8")
            r = rodar(["/usr/bin/osacompile", "-o", str(app), str(fonte)])
            fonte.unlink(missing_ok=True)
            if getattr(r, "returncode", 0) != 0 or not (app / "Contents" / "Info.plist").exists():
                raise OSError((getattr(r, "stderr", "") or "osacompile falhou").strip()[:200])
            info = app / "Contents" / "Info.plist"
            d = plistlib.loads(info.read_bytes())
            d["CFBundleIdentifier"] = f"br.ipe.link.{a}"
            d["CFBundleName"] = f"Ipe-{a}"
            d["LSUIElement"] = True                      # sem ícone no Dock
            d["CFBundleURLTypes"] = [{"CFBundleURLName": f"Ipe {a}", "CFBundleURLSchemes": [a]}]
            info.write_bytes(plistlib.dumps(d))
            rodar(["/usr/bin/codesign", "--force", "--deep", "-s", "-", str(app)])     # o plist mudou
            rodar([LSREGISTER, "-f", str(app)])
            _mac_padrao(a, d["CFBundleIdentifier"])
            feitos.append(a)
        except Exception as e:  # noqa: BLE001
            falhas.append(f"{a}:// ({e})")
    return feitos, falhas


def _mac_padrao(esquema: str, bundle_id: str) -> None:
    """Se outro programa (o OsiriX de verdade) também atende o link, o Ipê passa a ser o padrão."""
    try:
        import ctypes
        import ctypes.util
        cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
        cs = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreServices"))
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        cs.LSSetDefaultHandlerForURLScheme.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        cs.LSSetDefaultHandlerForURLScheme.restype = ctypes.c_int32
        utf8 = 0x08000100
        e = cf.CFStringCreateWithCString(None, esquema.encode(), utf8)
        b = cf.CFStringCreateWithCString(None, bundle_id.encode(), utf8)
        rc = cs.LSSetDefaultHandlerForURLScheme(e, b)
        if rc:
            log.info("LSSetDefaultHandlerForURLScheme(%s) = %s", esquema, rc)
    except Exception as e:  # noqa: BLE001
        log.info("Não deu para tornar o Ipê o padrão de %s://: %s", esquema, e)
