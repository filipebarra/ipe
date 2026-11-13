"""Cliente HTTP do servidor central (biblioteca padrão).

0.100.38: as conexões ficam **abertas** entre um pedido e outro (HTTP/1.1 keep-alive, `http.client`). Antes, cada
pedido abria uma conexão nova — e, em https, refazia o aperto de mãos do TLS: abrir um exame no modo cliente faz umas
vinte chamadas ao servidor, e cada uma pagava isso. Com um proxy configurado no sistema para o endereço do servidor,
continua pelo `urllib` (que sabe falar com o proxy), como antes.
"""

from __future__ import annotations

import http.client
import json
import logging
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ipe.central import codec, dicomweb as DW

log = logging.getLogger(__name__)


class RemoteError(Exception):
    pass


class Unauthorized(RemoteError):
    pass


class _Resposta:
    """A resposta de um pedido numa conexão que fica aberta: lida até o fim, a conexão volta para a reserva."""

    def __init__(self, cliente: "RemoteClient", conexao, resposta):
        self._cliente, self._conexao, self._r = cliente, conexao, resposta
        self.headers = resposta.headers
        self.status = resposta.status

    def read(self, n: int | None = None) -> bytes:
        return self._r.read() if n is None else self._r.read(n)

    def close(self) -> None:
        c, self._conexao = self._conexao, None
        if c is None:
            return
        if self._r.isclosed() and not self._r.will_close:
            self._cliente._devolver(c)              # lida inteira: a conexão serve para o próximo pedido
        else:
            try:
                c.close()
            except OSError:
                pass

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class RemoteClient:
    RESERVA = 6                 # conexões abertas guardadas para o próximo pedido
    PARADA_MAX = 90.0           # segundos: conexão parada há mais que isso não é reaproveitada

    def __init__(self, url: str, verify_tls: bool = True, timeout: float = 30.0, ca_pem: str = ""):
        self.url = url.rstrip("/")
        if "://" not in self.url:
            self.url = "http://" + self.url
        self.timeout = timeout
        self.token = ""
        self.username = ""
        self.on_unauthorized = None          # callback() -> bool (pede login de novo)
        self._ctx = None
        if self.url.startswith("https") and ca_pem:
            # 0.99.74: a AC interna do servidor (Confiar neste servidor): HTTPS conferido de verdade
            self._ctx = ssl.create_default_context(cadata=ca_pem)
        elif self.url.startswith("https") and not verify_tls:
            self._ctx = ssl.create_default_context()
            self._ctx.check_hostname = False
            self._ctx.verify_mode = ssl.CERT_NONE
        self._reserva: list[tuple] = []          # (conexão, quando ficou parada)
        self._trava = threading.Lock()
        self._por_proxy = self._tem_proxy()

    # ------------------------------------------------------------------ HTTP
    def _tem_proxy(self) -> bool:
        try:
            u = urllib.parse.urlsplit(self.url)
            return bool(urllib.request.getproxies().get(u.scheme)) and not urllib.request.proxy_bypass(u.hostname or "")
        except Exception:  # noqa: BLE001
            return False

    def _nova_conexao(self, timeout: float):
        u = urllib.parse.urlsplit(self.url)
        if u.scheme == "https":
            return http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=timeout,
                                               context=self._ctx or ssl.create_default_context())
        return http.client.HTTPConnection(u.hostname, u.port or 80, timeout=timeout)

    def _pegar(self, timeout: float):
        """(conexão, reaproveitada?)"""
        agora = time.monotonic()
        with self._trava:
            while self._reserva:
                c, quando = self._reserva.pop()
                if agora - quando <= self.PARADA_MAX and c.sock is not None:
                    try:
                        c.sock.settimeout(timeout)
                    except OSError:
                        continue
                    return c, True
                try:
                    c.close()
                except OSError:
                    pass
        return self._nova_conexao(timeout), False

    def _devolver(self, c) -> None:
        with self._trava:
            if len(self._reserva) < self.RESERVA:
                self._reserva.append((c, time.monotonic()))
                return
        try:
            c.close()
        except OSError:
            pass

    def fechar_conexoes(self) -> None:
        with self._trava:
            reserva, self._reserva = self._reserva, []
        for c, _q in reserva:
            try:
                c.close()
            except OSError:
                pass

    def _open(self, path: str, data=None, headers: dict | None = None,
              method: str | None = None, timeout: float | None = None):
        h = dict(headers or {})
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if self._por_proxy:
            return self._open_urllib(path, data, h, method, timeout)
        base = urllib.parse.urlsplit(self.url).path.rstrip("/")
        metodo = method or ("POST" if data is not None else "GET")
        corpo_relivel = data is None or isinstance(data, (bytes, bytearray))
        ultima = None
        for tentativa in (0, 1):
            c, reaproveitada = self._pegar(timeout or self.timeout)
            try:
                c.request(metodo, base + path, body=data, headers=h)
                r = c.getresponse()
            except (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError,
                    ConnectionAbortedError, http.client.CannotSendRequest, http.client.BadStatusLine) as e:
                # a conexão guardada foi fechada do outro lado (o servidor reiniciou): uma nova, uma vez
                try:
                    c.close()
                except OSError:
                    pass
                ultima = e
                if reaproveitada and tentativa == 0 and corpo_relivel:
                    continue
                raise RemoteError(f"Servidor central inacessível ({self.url}): {e}") from None
            except (OSError, http.client.HTTPException) as e:
                try:
                    c.close()
                except OSError:
                    pass
                raise RemoteError(f"Servidor central inacessível ({self.url}): {getattr(e, 'reason', e)}") from None
            if r.status >= 400:
                try:
                    bruto = r.read()
                except (OSError, http.client.HTTPException):
                    bruto = b""
                _Resposta(self, c, r).close()
                try:
                    msg = json.loads(bruto or b"{}").get("error", "")
                except (ValueError, AttributeError):
                    msg = ""
                if r.status == 401:
                    raise Unauthorized(msg or "login necessário")
                raise RemoteError(msg or f"HTTP {r.status}")
            return _Resposta(self, c, r)
        raise RemoteError(f"Servidor central inacessível ({self.url}): {ultima}")

    def _open_urllib(self, path: str, data, h: dict, method: str | None, timeout: float | None):
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

    @staticmethod
    def buscar_ac(url: str, timeout: float = 10.0) -> str:
        """A AC interna que o servidor publica em /api/ac (0.99.74). Baixada sem conferir: quem confere é a
        pessoa, pela impressão digital mostrada na tela."""
        url = url.rstrip("/")
        if "://" not in url:
            url = "https://" + url
        if not url.startswith("https://"):
            raise RemoteError("O servidor precisa estar em https:// para usar a AC interna.")
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            with urllib.request.urlopen(url + "/api/ac", timeout=timeout, context=ctx) as r:
                pem = r.read().decode("ascii", "replace")
        except urllib.error.HTTPError as e:
            raise RemoteError("O servidor não publica uma AC interna (gere o certificado nele)." if e.code == 404
                              else f"HTTP {e.code}") from None
        except (urllib.error.URLError, OSError) as e:
            raise RemoteError(f"Servidor central inacessível ({url}): {getattr(e, 'reason', e)}") from None
        if "BEGIN CERTIFICATE" not in pem:
            raise RemoteError("A resposta do servidor não é um certificado.")
        return pem

    # ------------------------------------------------------------------ sessão
    def ping(self) -> dict:
        with self._open("/api/ping", timeout=5) as r:
            return json.loads(r.read())

    def medir_rede(self, completo: bool = True) -> dict:
        """0.100.1: o teste de rede do cliente. {"ping_ms": mediana de 3 idas e voltas, "mbps": vazão baixando
        2 MB que não comprimem (só no teste completo; None se o servidor é antigo), "ok": bool}."""
        import time
        tempos = []
        try:
            for _ in range(3):
                t = time.perf_counter()
                with self._open("/api/ping", timeout=5) as r:
                    r.read()
                tempos.append((time.perf_counter() - t) * 1000)
        except Exception:  # noqa: BLE001
            return {"ok": False, "ping_ms": None, "mbps": None}
        out = {"ok": True, "ping_ms": sorted(tempos)[len(tempos) // 2], "mbps": None}
        if completo:
            try:
                t = time.perf_counter()
                n = 0
                with self._open("/api/velocidade?mb=2", timeout=20) as r:
                    primeiro = None
                    while True:
                        b = r.read(1 << 16)
                        if not b:
                            break
                        if primeiro is None:
                            primeiro = time.perf_counter()     # a conta começa no primeiro byte (sem a ida)
                        n += len(b)
                dt = time.perf_counter() - (primeiro or t)
                if n and dt > 0:
                    out["mbps"] = n * 8 / dt / 1e6
            except Exception:  # noqa: BLE001
                pass
        return out

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

    # ------------------------------------------------------------------ atualizações (0.99.56, onda B1)
    def info_atualizacao(self, canal: str = "estavel") -> dict:
        def call():
            with self._open(f"/api/atualizacao?canal={canal}", timeout=10) as r:
                return json.loads(r.read() or b"{}")
        return self._retry(call)

    def baixar_atualizacao(self, canal: str, dest: Path, progress=None) -> Path:
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)

        def call():
            with self._open(f"/api/atualizacao/pacote?canal={canal}", timeout=max(self.timeout, 300)) as r:
                total = int(r.headers.get("Content-Length") or 0)
                feito = 0
                with open(dest, "wb") as f:
                    while True:
                        bloco = r.read(1 << 20)
                        if not bloco:
                            break
                        f.write(bloco)
                        feito += len(bloco)
                        if progress:
                            progress(feito, total)
            return dest
        return self._retry(call)

    def publicar_atualizacao(self, arquivo: Path, versao: str = "", canal: str = "teste", notas: str = "") -> dict:
        from urllib.parse import urlencode
        arquivo = Path(arquivo)
        q = urlencode({"canal": canal, "nome": arquivo.name, "versao": versao, "notas": notas})

        def call():
            with open(arquivo, "rb") as f:
                h = {"Content-Type": "application/octet-stream", "Content-Length": str(arquivo.stat().st_size)}
                with self._open(f"/api/atualizacao?{q}", f, h, "POST", timeout=max(self.timeout, 900)) as r:
                    return json.loads(r.read())
        return self._retry(call)

    # ------------------------------------------------------------------ DICOMweb
    def qido(self, path: str) -> list[dict]:
        def call():
            with self._open("/dicomweb" + path, headers={"Accept": "application/dicom+json"}) as r:
                return json.loads(r.read() or b"[]")
        return self._retry(call)

    def retrieve(self, study_uid: str, dest: Path, series_uid: str | None = None, progress=None,
                 sop_uid: str | None = None, htj2k: bool = False, destino=None, metas: list | None = None,
                 amostras: list[str] | bool = False) -> list[Path]:
        """WADO-RS: baixa o estudo (ou uma série, ou uma imagem) para `dest`, arquivo por arquivo.
        `htj2k`: pede os pixels em HTJ2K sem perda (0.100.0); o servidor manda o original se não ganha nada.
        0.100.38: `destino(meta, n)` diz onde gravar cada imagem pelas colunas que o servidor manda junto (e
        `metas` recebe as de cada uma, na ordem dos arquivos devolvidos); `amostras` (True ou as séries) pede só
        a imagem do meio de cada série, num pedido só."""
        path = f"/dicomweb/studies/{study_uid}" + (f"/series/{series_uid}" if series_uid else "")
        if series_uid and sop_uid:
            path += f"/instances/{sop_uid}"
        if amostras:
            path = f"/dicomweb/studies/{study_uid}/amostras"
            if isinstance(amostras, (list, tuple)):
                path += "?series=" + ",".join(amostras)
        aceita = 'multipart/related; type="application/dicom"'
        if htj2k:
            aceita += "; transfer-syntax=1.2.840.10008.1.2.4.202"
        h = {"Accept": aceita}
        if destino is not None or metas is not None:
            h["X-Ipe-Cliente"] = "2"

        def call():
            r = self._open(path, headers=h, timeout=max(self.timeout, 120))
            try:
                boundary = DW.boundary_of(r.headers.get("Content-Type", ""))
                leitor = DW.MultipartReader(r, boundary, dest, progress, destino)
                try:
                    arquivos = leitor.run()
                    for _ in range(4):                  # o fim do corpo: lido, a conexão serve para o próximo pedido
                        if not r.read(65536):
                            break
                    return arquivos
                finally:
                    if metas is not None:
                        metas[:] = leitor.metas
            finally:
                r.close()
        return self._retry(call)

    def store(self, files: list[str | Path], progress=None, batch_mb: int = 64, banco: str = "") -> dict:
        """STOW-RS em lotes; devolve o total recebido e os estudos. `banco="meu"`: exame novo entra no
        banco pessoal de quem manda (0.99.28)."""
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
            h = {"Content-Type": ctype}
            if banco:
                h["X-Ipe-Banco"] = banco
            with self._open("/dicomweb/studies", body, h, "POST",
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
