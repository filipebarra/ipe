"""Visualizador web do servidor central (0.99.91, fase W0 do `plano-visualizador-web`).

O site (TypeScript + Cornerstone3D, construído de `web/` para `ipe/web_dist`) é servido em `/web`. Aqui ficam as
peças do lado do servidor que o site precisa e o DICOMweb de antes não tinha:

- **arquivos estáticos** de `/web` (sem login: o site não tem dado de paciente; os dados pedem o token);
- **metadados** de uma série em DICOM JSON (WADO-RS `…/series/{uid}/metadata`), sem os pixels — o carregador do
  Cornerstone3D monta as imagens com eles;
- **quadros** (WADO-RS `…/instances/{uid}/frames/{n}`): o quadro como está no arquivo (JPEG-LS, J2K, JPEG…,
  decodificado no navegador pelos codecs em WebAssembly do Cornerstone3D) ou, nos poucos formatos que o
  navegador não lê (big endian, deflate), já descomprimido;
- **miniatura** da série (a mesma PNG da tira do Ipê);
- **configuração** do usuário: idioma, janelas prontas, protocolos (as preferências dele no servidor por cima
  das do servidor).

Os cabeçalhos de segurança valem para tudo: nada vai para o cache do navegador, o site só carrega o que vem do
próprio servidor.
"""
from __future__ import annotations

import json
import logging
import mimetypes
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

PASTA = Path(__file__).resolve().parent.parent / "web_dist"

#: sintaxes que o navegador decodifica (o carregador do Cornerstone3D): o quadro vai como está
NATIVAS = {"1.2.840.10008.1.2", "1.2.840.10008.1.2.1"}
COMPRIMIDAS = {
    "1.2.840.10008.1.2.4.50", "1.2.840.10008.1.2.4.51", "1.2.840.10008.1.2.4.57", "1.2.840.10008.1.2.4.70",
    "1.2.840.10008.1.2.4.80", "1.2.840.10008.1.2.4.81", "1.2.840.10008.1.2.4.90", "1.2.840.10008.1.2.4.91",
    "1.2.840.10008.1.2.4.201", "1.2.840.10008.1.2.4.202", "1.2.840.10008.1.2.4.203", "1.2.840.10008.1.2.5",
}
EXPLICITA = "1.2.840.10008.1.2.1"

#: chaves da configuração que o site lê (as de usuário vêm das preferências dele por cima)
CHAVES_CONFIG = ("viewer.wl_presets", "viewer.wl_presets_mod", "hanging_protocols", "mg_protocols")

CSP = ("default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; "
       "img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


def cabecalhos(https: bool, pagina: bool = False) -> dict:
    h = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
         "Cache-Control": "no-store", "X-Frame-Options": "DENY"}
    if pagina:
        h["Content-Security-Policy"] = CSP
        h["Cross-Origin-Opener-Policy"] = "same-origin"
    if https:
        h["Strict-Transport-Security"] = "max-age=31536000"
    return h


# ------------------------------------------------------------------ estáticos
def arquivo_estatico(caminho: str, pasta: Path | None = None) -> tuple[bytes, str] | None:
    """(conteúdo, tipo) do arquivo do site, ou None. `caminho` é o que vem depois de /web/. Sem nome de
    arquivo (ou rota do próprio site, sem extensão), devolve o index.html."""
    raiz = (pasta or PASTA).resolve()
    rel = caminho.strip("/")
    alvo = (raiz / rel).resolve() if rel else raiz / "index.html"
    if not str(alvo).startswith(str(raiz)):                 # nada fora da pasta do site
        return None
    if alvo.is_dir():
        alvo = alvo / "index.html"
    if not alvo.is_file():
        if "." in Path(rel).name:
            return None
        alvo = raiz / "index.html"                          # rota do site (/web/exame/…)
        if not alvo.is_file():
            return None
    tipo = mimetypes.guess_type(alvo.name)[0] or "application/octet-stream"
    if alvo.suffix == ".wasm":
        tipo = "application/wasm"
    elif alvo.suffix in (".js", ".mjs"):
        tipo = "text/javascript"
    if tipo.startswith("text/") or tipo in ("application/json", "text/javascript"):
        tipo += "; charset=utf-8"
    return alvo.read_bytes(), tipo


def site_instalado(pasta: Path | None = None) -> bool:
    return ((pasta or PASTA) / "index.html").is_file()


# ------------------------------------------------------------------ caminhos das instâncias (com cache curto)
class _Caminhos:
    """sop_uid -> caminho, por série, por alguns minutos (o site pede um quadro de cada vez)."""

    def __init__(self, ttl: float = 300.0):
        self.ttl = ttl
        self._d: dict[str, tuple[float, dict]] = {}
        self._lock = threading.Lock()

    def da_serie(self, repo, series_uid: str) -> dict:
        agora = time.time()
        with self._lock:
            it = self._d.get(series_uid)
            if it and agora - it[0] < self.ttl:
                return it[1]
        mapa = {i["sop_uid"]: i["path"] for i in repo.instances_for_series(series_uid) if i.get("path")}
        with self._lock:
            self._d[series_uid] = (agora, mapa)
            if len(self._d) > 200:
                for k in sorted(self._d, key=lambda k: self._d[k][0])[:50]:
                    self._d.pop(k, None)
        return mapa


CAMINHOS = _Caminhos()


# ------------------------------------------------------------------ metadados
def _bulk(raiz_url: str):
    def handler(elem):
        return raiz_url
    return handler


def metadados_da_serie(repo, study_uid: str, series_uid: str, base_url: str) -> list[dict]:
    """DICOM JSON de cada instância da série (PS3.18 F.2), com o PixelData como BulkDataURI. Inclui a
    sintaxe de transferência (0002,0010), que o site usa para saber como pedir o quadro."""
    import pydicom
    out = []
    for sop, caminho in CAMINHOS.da_serie(repo, series_uid).items():
        if not Path(caminho).exists():
            continue
        try:
            ds = pydicom.dcmread(caminho, stop_before_pixels=True, force=True)
        except Exception:  # noqa: BLE001
            log.exception("metadados: %s", caminho)
            continue
        url = f"{base_url}/studies/{study_uid}/series/{series_uid}/instances/{sop}"
        try:
            # tudo junto (sem BulkDataURI): as tabelas de VOI LUT da mamografia e as sobreposições vão no JSON —
            # os pixels já ficaram de fora (stop_before_pixels)
            d = ds.to_json_dict(bulk_data_threshold=1 << 30, bulk_data_element_handler=_bulk(url + "/bulk"))
        except Exception:  # noqa: BLE001
            log.exception("metadados (json): %s", caminho)
            continue
        ts = str(getattr(getattr(ds, "file_meta", None), "TransferSyntaxUID", "") or EXPLICITA)
        d["00020010"] = {"vr": "UI", "Value": [ts]}
        d["7FE00010"] = {"vr": "OW", "BulkDataURI": url + "/frames/1"}
        out.append(d)
    return out


# ------------------------------------------------------------------ quadros
def quadros(caminho: str, numeros: list[int]) -> list[tuple[bytes, str]]:
    """[(bytes do quadro, sintaxe de transferência)] dos quadros pedidos (1 = o primeiro)."""
    import pydicom
    ds = pydicom.dcmread(caminho, force=True)
    ts = str(getattr(getattr(ds, "file_meta", None), "TransferSyntaxUID", "") or EXPLICITA)
    n_quadros = int(getattr(ds, "NumberOfFrames", 1) or 1)
    for n in numeros:
        if n < 1 or n > n_quadros:
            raise IndexError(f"quadro {n} fora de 1..{n_quadros}")
    if ts in COMPRIMIDAS:
        from pydicom.encaps import generate_frames
        todos = list(generate_frames(ds.PixelData, number_of_frames=n_quadros))
        return [(bytes(todos[n - 1]), ts) for n in numeros]
    if ts in NATIVAS:
        bits = int(ds.BitsAllocated)
        tam = int(ds.Rows) * int(ds.Columns) * int(getattr(ds, "SamplesPerPixel", 1) or 1) * bits // 8
        px = ds.PixelData
        return [(bytes(px[(n - 1) * tam:n * tam]), EXPLICITA) for n in numeros]
    # big endian, deflate…: decodifica e manda nativo explícito (little endian)
    import numpy as np
    arr = ds.pixel_array
    if n_quadros == 1:
        arr = arr[None]
    return [(np.ascontiguousarray(arr[n - 1]).astype(arr.dtype.newbyteorder("<")).tobytes(), EXPLICITA)
            for n in numeros]


def multipart_quadros(partes: list[tuple[bytes, str]], boundary: str) -> bytes:
    out = bytearray()
    for dados, ts in partes:
        out += (f"--{boundary}\r\nContent-Type: application/octet-stream; transfer-syntax={ts}\r\n"
                f"Content-Length: {len(dados)}\r\n\r\n").encode("ascii")
        out += dados + b"\r\n"
    out += f"--{boundary}--\r\n".encode("ascii")
    return bytes(out)


# ------------------------------------------------------------------ configuração
def _get(d: dict, dotted: str):
    cur = d
    for p in dotted.split("."):
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def configuracao(settings, prefs: dict | None, usuario: dict) -> dict:
    """O que o site lê: idioma, janelas e protocolos — as preferências do usuário por cima das do servidor."""
    from ipe.core import i18n
    lang = ""
    if settings is not None:
        try:
            lang = settings.get("language", "") or ""
        except Exception:  # noqa: BLE001
            lang = ""
    lang = (lang or i18n.current() or "en").lower()
    out = {"usuario": usuario, "lang": "pt" if lang.startswith("pt") else "es" if lang.startswith("es") else "en"}
    for chave in CHAVES_CONFIG:
        v = _get(prefs or {}, chave)
        if v is None and settings is not None:
            try:
                v = settings.get(chave, None)
            except Exception:  # noqa: BLE001
                v = None
        out[chave] = v
    from ipe import __version__
    out["versao"] = __version__
    return json.loads(json.dumps(out, default=str))
