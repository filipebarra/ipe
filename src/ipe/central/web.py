"""Visualizador web do servidor central (0.99.91, fase W0 do `docs/projeto/plano-visualizador-web.md`).

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
import os
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


def _meta_da_instancia(sop: str, caminho: str, url_serie: str) -> dict | None:
    import pydicom
    try:
        ds = pydicom.dcmread(caminho, stop_before_pixels=True, force=True)
    except Exception:  # noqa: BLE001
        log.exception("metadados: %s", caminho)
        return None
    url = f"{url_serie}/instances/{sop}"
    try:
        # tudo junto (sem BulkDataURI): as tabelas de VOI LUT da mamografia e as sobreposições vão no JSON —
        # os pixels já ficaram de fora (stop_before_pixels)
        d = ds.to_json_dict(bulk_data_threshold=1 << 30, bulk_data_element_handler=_bulk(url + "/bulk"))
    except Exception:  # noqa: BLE001
        log.exception("metadados (json): %s", caminho)
        return None
    ts = str(getattr(getattr(ds, "file_meta", None), "TransferSyntaxUID", "") or EXPLICITA)
    d["00020010"] = {"vr": "UI", "Value": [ts]}
    d["7FE00010"] = {"vr": "OW", "BulkDataURI": url + "/frames/1"}
    return d


#: 0.99.99: os cabeçalhos são lidos em paralelo (no Windows, abrir arquivo é o que mais demora) e a resposta
#: pronta fica guardada — a série já lida sai na hora, e o exame inteiro é lido assim que abre
_LEITORES = 8
_META: dict[tuple, tuple[str, bytes, bytes]] = {}
_META_TRAVA = threading.Lock()
_META_FAZENDO: dict[tuple, threading.Event] = {}


def _assinatura(caminhos: dict) -> str:
    import hashlib
    h = hashlib.sha1()
    for sop, c in sorted(caminhos.items()):
        try:
            st = os.stat(c)
            h.update(f"{sop}|{c}|{st.st_mtime_ns}|{st.st_size}\n".encode())
        except OSError:
            h.update(f"{sop}|{c}|-\n".encode())
    return h.hexdigest()


def metadados_da_serie(repo, study_uid: str, series_uid: str, base_url: str) -> list[dict]:
    """DICOM JSON de cada instância da série (PS3.18 F.2), com o PixelData como BulkDataURI. Inclui a
    sintaxe de transferência (0002,0010), que o site usa para saber como pedir o quadro."""
    from concurrent.futures import ThreadPoolExecutor
    caminhos = {s: c for s, c in CAMINHOS.da_serie(repo, series_uid).items() if Path(c).exists()}
    url_serie = f"{base_url}/studies/{study_uid}/series/{series_uid}"
    itens = list(caminhos.items())
    if len(itens) <= 2:
        res = [_meta_da_instancia(s, c, url_serie) for s, c in itens]
    else:
        with ThreadPoolExecutor(max_workers=min(_LEITORES, len(itens)), thread_name_prefix="ipe-meta") as ex:
            res = list(ex.map(lambda sc: _meta_da_instancia(sc[0], sc[1], url_serie), itens))
    return [d for d in res if d is not None]


VERSAO_META = 1          # muda quando o JSON dos metadados muda de formato: o guardado em disco deixa de valer


def _meta_em_disco(chave: tuple, assin: str) -> Path | None:
    """Onde fica guardado o JSON (gzip) dos metadados desta série, com estes arquivos. None sem a pasta do cache."""
    import hashlib

    from ipe.central import envio
    pasta = envio.pasta()
    if pasta is None:
        return None
    h = hashlib.sha1(f"{VERSAO_META}|{'|'.join(chave)}|{assin}".encode()).hexdigest()
    return pasta / "meta" / h[:2] / f"{h}.json.gz"


def metadados_prontos(repo, study_uid: str, series_uid: str, base_url: str,
                      guardar: bool = True) -> tuple[bytes, bytes] | None:
    """(json, json em gzip) da série — do guardado quando os arquivos não mudaram. None se não há nada.
    Dois pedidos da mesma série ao mesmo tempo leem uma vez só. `guardar=False`: só deixa pronto em disco (a
    preparação dos exames recentes), sem ocupar a memória."""
    import gzip
    chave = (study_uid, series_uid, base_url)
    while True:
        assin = _assinatura({s: c for s, c in CAMINHOS.da_serie(repo, series_uid).items()})
        with _META_TRAVA:
            it = _META.get(chave)
            if it and it[0] == assin:
                return it[1], it[2]
            ev = _META_FAZENDO.get(chave)
            if ev is None:
                ev = _META_FAZENDO[chave] = threading.Event()
                minha = True
            else:
                minha = False
        if not minha:
            ev.wait(120)
            continue
        try:
            # 0.100.38: o que já foi montado uma vez fica também em disco (CacheWeb/meta): depois de o servidor
            # reiniciar, ou para um exame que saiu da memória, a série sai sem reler os cabeçalhos — e os exames
            # recentes ficam prontos em segundo plano (envio.varrer_recentes)
            disco = _meta_em_disco(chave, assin)
            gz = None
            if not guardar and disco is not None and disco.exists():
                return b"", b""                      # já está pronto em disco: nada a fazer
            if disco is not None:
                try:
                    gz = disco.read_bytes()
                    corpo = gzip.decompress(gz)
                except (OSError, EOFError, gzip.BadGzipFile):
                    gz = None
            if gz is None:
                meta = metadados_da_serie(repo, study_uid, series_uid, base_url)
                if not meta:
                    return None
                corpo = json.dumps(meta).encode()
                gz = gzip.compress(corpo, 5)
                if disco is not None:
                    try:
                        disco.parent.mkdir(parents=True, exist_ok=True)
                        tmp = disco.with_suffix(f".{threading.get_ident()}.tmp")
                        tmp.write_bytes(gz)
                        os.replace(tmp, disco)
                    except OSError:
                        log.debug("metadados em disco", exc_info=True)
            if not guardar:
                return corpo, gz
            with _META_TRAVA:
                _META[chave] = (assin, corpo, gz)
                if len(_META) > 300:
                    for k in list(_META)[:100]:
                        _META.pop(k, None)
            return corpo, gz
        finally:
            with _META_TRAVA:
                _META_FAZENDO.pop(chave, None)
            ev.set()


_AQUECENDO: set[str] = set()


def aquecer_exame(repo, study_uid: str, base_url: str, primeiro: str = "") -> None:
    """Em segundo plano: lê os metadados de todas as séries do exame (a que foi pedida primeiro já está sendo
    lida). Quando o navegador pedir a próxima série, ela sai na hora."""
    with _META_TRAVA:
        if study_uid in _AQUECENDO:
            return
        _AQUECENDO.add(study_uid)

    def trabalho():
        try:
            for r in repo.series_for_study(study_uid):
                if r.series_uid != primeiro:
                    try:
                        metadados_prontos(repo, study_uid, r.series_uid, base_url)
                    except Exception:  # noqa: BLE001
                        log.exception("metadados (json): %s", r.series_uid)
        finally:
            with _META_TRAVA:
                _AQUECENDO.discard(study_uid)
    threading.Thread(target=trabalho, name="ipe-meta-exame", daemon=True).start()


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


def quadros_para_web(caminho: str, numeros: list[int] | None) -> list[tuple[bytes, str]]:
    """Como `quadros`, mas cada quadro passa pela cópia de envio (HTJ2K/JPEG-LS sem perda, conferida, em cache).
    `numeros` None = todos (para preparar a série em segundo plano)."""
    import pydicom

    from ipe.central import envio
    ds = pydicom.dcmread(caminho, stop_before_pixels=True, force=True)
    n_quadros = int(getattr(ds, "NumberOfFrames", 1) or 1)
    if numeros is None:
        numeros = list(range(1, n_quadros + 1))
    originais = quadros(caminho, numeros)
    return [envio.quadro(ds, caminho, n, dados, ts) for n, (dados, ts) in zip(numeros, originais)]


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
    out["tabelas_cores"] = tabelas_de_cores()                 # 0.99.94 (W3): as cores da fusão são as do Ipê
    return json.loads(json.dumps(out, default=str))


# ------------------------------------------------------------------ medidas (0.99.93, W2)
#: os tipos que o site desenha e grava (os outros do Ipê ficam no banco, intocados)
TIPOS_MEDIDA = ("line", "angle", "cobb", "ellipse", "rect", "polygon", "probe", "arrow", "calibration")


def medidas(repo, s, method: str, path: str, q: dict, corpo: dict, pode_ver) -> object:
    """GET ?series=…&study=… lista; POST grava (devolve o número); POST …/apagar apaga. Quem fez vai em
    `owner` e em meta.autor (do login, não do que o navegador manda); só mexe em medida de exame visível."""
    if not s.can("view"):
        raise PermissionError("sem permissão")
    if method == "GET":
        study = (q.get("study") or [""])[0]
        series = (q.get("series") or [""])[0]
        if not study or not series or not pode_ver(s, study):
            raise PermissionError("exame não visível")
        return [r for r in repo.annotations_for_series([series]) if r["study_uid"] == study]
    if method != "POST":
        raise ValueError("método")
    if path.endswith("/apagar"):
        reg = repo.annotation_by_id(int(corpo["db_id"]))
        if reg is None:
            return {"ok": True}
        if not pode_ver(s, reg["study_uid"]):
            raise PermissionError("exame não visível")
        repo.delete_annotation(int(corpo["db_id"]))
        return {"ok": True}
    study = str(corpo["study_uid"])
    if not pode_ver(s, study):
        raise PermissionError("exame não visível")
    kind = str(corpo["kind"])
    if kind not in TIPOS_MEDIDA:
        raise ValueError(f"tipo de medida desconhecido: {kind}")
    dados = corpo.get("data") or {}
    if isinstance(dados, str):
        dados = json.loads(dados or "{}")
    pontos = [[float(x), float(y)] for x, y in dados.get("points", [])]
    meta = dict(dados.get("meta") or {})
    db_id = corpo.get("db_id")
    antigo = repo.annotation_by_id(int(db_id)) if db_id else None
    if antigo is not None:
        if antigo["study_uid"] != study:
            raise PermissionError("a medida é de outro exame")
        meta["autor"] = (json.loads(antigo["data"] or "{}").get("meta") or {}).get("autor") or antigo.get("owner") or ""
    else:
        db_id = None
        meta["autor"] = s.username
    d = {"points": pontos, "text": str(dados.get("text", ""))}
    if meta:
        d["meta"] = meta
    novo = repo.save_annotation(db_id=db_id, study_uid=study, series_uid=str(corpo["series_uid"]),
                                sop_uid=str(corpo["sop_uid"]), frame_index=int(corpo.get("frame_index", 0)),
                                kind=kind, data=json.dumps(d), owner=s.username)
    return {"id": novo}


# ------------------------------------------------------------------ PET/CT (0.99.94, W3)
def _serie_do_exame(repo, s, q: dict, pode_ver) -> tuple[str, str]:
    """(exame, série) do pedido, conferindo que o usuário vê o exame e que a série é dele."""
    if not s.can("view"):
        raise PermissionError("sem permissão")
    study = (q.get("study") or [""])[0]
    series = (q.get("series") or [""])[0]
    if not study or not series or not pode_ver(s, study):
        raise PermissionError("exame não visível")
    if series not in {r.series_uid for r in repo.series_for_study(study, ocultas=True)}:
        raise PermissionError("a série não é deste exame")
    return study, series


def suv_da_serie(repo, s, q: dict, pode_ver) -> dict:
    """O fator de SUV (pelo peso) da série de PET, com a mesma conta do Ipê (imaging/suv.py)."""
    from ipe.imaging.suv import suv_factor_for_file
    _study, series = _serie_do_exame(repo, s, q, pode_ver)
    for caminho in CAMINHOS.da_serie(repo, series).values():
        if Path(caminho).exists():
            fator, motivo = suv_factor_for_file(caminho)
            return {"fator": fator, "motivo": motivo}
    return {"fator": None, "motivo": "série sem arquivos"}


def _geometria(caminho: str):
    import numpy as np
    import pydicom
    ds = pydicom.dcmread(caminho, stop_before_pixels=True, force=True)
    try:
        ipp = np.array([float(v) for v in ds.ImagePositionPatient])
        iop = np.array([float(v) for v in ds.ImageOrientationPatient])
        sp = tuple(float(v) for v in ds.PixelSpacing)
        return ipp, iop, sp, int(ds.Rows), int(ds.Columns)
    except Exception:  # noqa: BLE001
        return None


def seg_mapa(repo, s, q: dict, pode_ver) -> dict:
    """A SEG do exame como mapa de rótulos sobre a série de origem: por corte dela (SOP), o recorte com algo
    (zlib + base64), o número do segmento em cada pixel. O nome e a cor de cada segmento vão à parte.
    Só os quadros na mesma orientação e espaçamento da série de origem (as SEG do Ipê e da IA são assim)."""
    import base64
    import zlib

    import numpy as np
    import pydicom

    from ipe.imaging import overlays as O
    study, series = _serie_do_exame(repo, s, q, pode_ver)
    caminhos = [c for c in CAMINHOS.da_serie(repo, series).values() if Path(c).exists()]
    if not caminhos:
        raise ValueError("SEG sem arquivo")
    ds = pydicom.dcmread(caminhos[0], force=True)
    if str(ds.get("Modality", "")).upper() != "SEG":
        raise ValueError("a série não é uma SEG")
    obj = O.parse_seg(ds, caminhos[0])
    ref = obj.series_ref
    if not ref or ref not in {r.series_uid for r in repo.series_for_study(study, ocultas=True)}:
        raise ValueError("a SEG não aponta para uma série deste exame")
    nomes = list(dict.fromkeys(m.label for m in obj.masks))
    cores = {m.label: m.color for m in obj.masks}
    num = {n: i + 1 for i, n in enumerate(nomes)}
    cortes = []
    for sop, cam in CAMINHOS.da_serie(repo, ref).items():
        g = _geometria(cam) if Path(cam).exists() else None
        if g is not None:
            cortes.append((sop, *g))
    if not cortes:
        raise ValueError("a série de origem não tem a posição dos cortes")
    normal = np.cross(cortes[0][2][:3], cortes[0][2][3:])
    d_ref = np.array([float(np.dot(c[1], normal)) for c in cortes])
    passo = float(np.median(np.diff(np.sort(d_ref)))) if len(d_ref) > 1 else 1.0
    tol = max(abs(passo) / 2, 0.01)
    mapas: dict[str, np.ndarray] = {}
    for m in obj.masks:
        if m.position is None or m.orientation is None or m.spacing is None:
            continue
        k = int(np.argmin(np.abs(d_ref - float(np.dot(m.position, normal)))))
        sop, ipp, iop, sp, linhas, colunas = cortes[k]
        if abs(d_ref[k] - float(np.dot(m.position, normal))) > tol or not np.allclose(m.orientation, iop, atol=1e-3) \
                or not np.allclose(m.spacing, sp, rtol=0.01):
            continue
        dv = m.position - ipp
        c0 = int(round(float(np.dot(dv, iop[:3])) / sp[1]))
        r0 = int(round(float(np.dot(dv, iop[3:])) / sp[0]))
        alvo = mapas.setdefault(sop, np.zeros((linhas, colunas), np.uint8))
        h, w = m.mask.shape
        rr0, cc0 = max(r0, 0), max(c0, 0)
        rr1, cc1 = min(r0 + h, linhas), min(c0 + w, colunas)
        if rr1 <= rr0 or cc1 <= cc0:
            continue
        sub = m.mask[rr0 - r0:rr1 - r0, cc0 - c0:cc1 - c0]
        alvo[rr0:rr1, cc0:cc1][sub] = num[m.label]
    fatias = []
    for sop, a in mapas.items():
        rs, cs = np.flatnonzero(a.any(axis=1)), np.flatnonzero(a.any(axis=0))
        if not len(rs):
            continue
        r0, r1, c0, c1 = int(rs[0]), int(rs[-1]) + 1, int(cs[0]), int(cs[-1]) + 1
        rec = np.ascontiguousarray(a[r0:r1, c0:c1])
        fatias.append({"sop": sop, "r0": r0, "c0": c0, "h": r1 - r0, "w": c1 - c0,
                       "dados": base64.b64encode(zlib.compress(rec.tobytes(), 6)).decode()})
    return {"ref_series": ref, "descricao": str(ds.get("SeriesDescription", "") or obj.label),
            "segmentos": [{"n": num[n], "nome": n, "cor": list(cores[n])} for n in nomes], "fatias": fatias}


# ------------------------------------------------------------------ overlays / CAD (0.100.2)
_OVERLAYS: dict = {}


def _graficos(gs) -> list:
    out = []
    for g in gs or []:
        d = {"tipo": g.kind, "pontos": [[round(float(x), 3), round(float(y), 3)] for x, y in (g.points or [])]}
        if g.text:
            d["texto"] = str(g.text)
        if g.color:
            d["cor"] = [int(c) for c in g.color[:3]]
        out.append(d)
    return out


def _objeto_web(obj) -> dict:
    import base64

    import numpy as np
    por_sop: dict[str, list] = {}
    for (sop, quadro), gs in (obj.by_frame or {}).items():
        for g in _graficos(gs):
            g["quadro"] = int(quadro)                       # 0 = o primeiro; -1 = todos
            por_sop.setdefault(str(sop), []).append(g)
    planos = []
    for g in obj.planar or []:
        if g.points3d is None:
            continue
        d = {"tipo": g.kind, "pontos3d": np.round(np.asarray(g.points3d, float), 2).tolist()}
        if g.text:
            d["texto"] = str(g.text)
        if g.color:
            d["cor"] = [int(c) for c in g.color[:3]]
        planos.append(d)
    mascaras = []
    for m in obj.masks or []:
        if m.ref is None or m.mask is None or not m.mask.any():
            continue
        a = np.asarray(m.mask, bool)
        rs, cs = np.flatnonzero(a.any(axis=1)), np.flatnonzero(a.any(axis=0))
        r0, r1, c0, c1 = int(rs[0]), int(rs[-1]) + 1, int(cs[0]), int(cs[-1]) + 1
        rec = np.ascontiguousarray(a[r0:r1, c0:c1])
        d = {"sop": str(m.ref[0]), "quadro": int(m.ref[1]), "r0": r0, "c0": c0, "h": r1 - r0, "w": c1 - c0,
             "bits": base64.b64encode(np.packbits(rec, axis=None).tobytes()).decode(),
             "cor": [int(c) for c in (m.color or obj.color)[:3]], "rotulo": m.label or ""}
        if m.alvo:
            d["escala"] = [float(m.alvo[0]) / a.shape[0], float(m.alvo[1]) / a.shape[1]]
        mascaras.append(d)
    return {"chave": obj.key, "fonte": obj.source, "rotulo": obj.label, "cor": [int(c) for c in obj.color[:3]],
            "achados": [str(f) for f in (obj.findings or [])][:50], "por_sop": por_sop,
            "todos": _graficos(obj.all_frames), "planos": planos, "mascaras": mascaras,
            "so_serie": obj.so_series or "", "serie_ref": obj.series_ref or ""}


def series_ia(repo, s, q: dict, pode_ver) -> dict:
    """0.100.14: as séries do exame com IA (resultado de IA ou analisadas por uma), para o selo nas miniaturas."""
    from ipe.ai import series_ia as SIA
    if not s.can("view"):
        raise PermissionError("sem permissão")
    study = (q.get("study") or [""])[0]
    if not study or not pode_ver(s, study):
        raise PermissionError("exame não visível")
    return {"series": {uid: {**d, "dica": SIA.dica(d)} for uid, d in SIA.series_com_ia(repo, study).items()}}


def _rotulos3d(volumes, alvo: int = 700) -> list:
    """0.100.14: os volumes "só rótulo" (níveis da coluna, níveis linfonodais) para o navegador: uma nuvem de pontos
    em mm (paciente) por nível, ralea até ~`alvo` pontos, e a tolerância (meio passo da nuvem). O navegador põe o
    nome no centro dos pontos que o plano do quadro corta — como o Ipê faz com a máscara —, em qualquer série e
    plano do exame."""
    import numpy as np
    out = []
    for mv in volumes or []:
        if not getattr(mv, "so_rotulo", False) or not mv.label:
            continue
        m = np.asarray(mv.mascara, bool)
        n = int(m.sum())
        if n < 4:
            continue
        passo = max(1, int(round((n / alvo) ** (1 / 3))))
        sub = m[::passo, ::passo, ::passo]
        k, j, i = np.nonzero(sub)
        if len(k) < 2:
            k, j, i = np.nonzero(m)
            passo = 1
        ijk = np.stack([i * passo, j * passo, k * passo]).astype(float)
        pts = (np.asarray(mv.origem, float)[:, None] + np.asarray(mv.matriz, float) @ ijk).T
        tol = 0.5 * passo * float(max(np.linalg.norm(np.asarray(mv.matriz, float), axis=0)))
        out.append({"texto": str(mv.label), "cor": [int(c) for c in (mv.color or (230, 230, 230))[:3]],
                    "tol": round(max(tol, 0.75), 2), "pontos": np.round(pts, 1).tolist()})
    return out


def _niveis_web(repo, study: str, assinatura: list) -> list:
    """Os objetos de rótulos da IA do Ipê: níveis da coluna (a SEG) e níveis linfonodais (o mapa guardado na SEG)."""
    from ipe.ai import coluna as COL
    from ipe.ai import linfonodos as LN
    objs = []
    for r in repo.series_for_study(study, ocultas=True):
        desc = r.description or ""
        if desc not in (COL.MARCA, LN.DESC_SEG):
            continue
        for inst in repo.instances_for_series(r.series_uid)[-1:]:
            cam = str(inst.get("path") or "")
            try:
                st = Path(cam).stat()
            except OSError:
                continue
            assinatura.append((cam, st.st_mtime_ns, st.st_size))
            objs.append((r, cam, desc == COL.MARCA))
    return objs


def _objeto_niveis(r, cam: str, coluna: bool, study: str) -> dict | None:
    from ipe.ai import coluna as COL
    from ipe.ai import linfonodos as LN
    try:
        if coluna:
            obj = COL.objeto_do_seg(cam, study)
            vols, fonte, rotulo = obj.volumes, obj.source, obj.label
            achados = [str(f) for f in (obj.findings or [])]
        else:
            import pydicom
            ds = pydicom.dcmread(cam, stop_before_pixels=True, force=True)
            texto = str(ds.private_block(LN.GRUPO_PRIVADO, LN.CRIADOR)[0x01].value)
            vols, fonte, rotulo = LN.mapa_do_json(texto), LN.FONTE_OVERLAY, "mapa dos níveis"
            achados = [mv.label for mv in vols]
    except Exception:  # noqa: BLE001
        log.exception("níveis da IA para o navegador: %s", cam)
        return None
    rot = _rotulos3d(vols)
    if not rot:
        return None
    return {"chave": f"{'coluna' if coluna else 'linfonodos'}:{r.series_uid}", "fonte": fonte, "rotulo": rotulo,
            "cor": [230, 230, 230], "achados": achados[:50], "por_sop": {}, "todos": [], "planos": [],
            "mascaras": [], "so_serie": "", "serie_ref": "", "rotulos3d": rot, "ia": True,
            "serie": r.series_uid, "descricao": r.description or ""}


def overlays(repo, s, q: dict, pode_ver, settings) -> dict:
    """Os objetos de overlay do exame (CAD/IA em SR, anotações GSPS de outro sistema, contornos RTSTRUCT),
    lidos com o mesmo leitor do Ipê (imaging/overlays.py), em coordenadas de pixel
    da imagem (o canto do pixel 0,0 em 0,0) — o navegador só desenha. As medidas que o Ipê guarda como SR/GSPS
    nossos ficam de fora: elas já vêm do banco. Também o que o médico deixou oculto no Ipê."""
    from ipe import MARCAS_NOSSAS
    from ipe.imaging import overlays as O
    if not s.can("view"):
        raise PermissionError("sem permissão")
    study = (q.get("study") or [""])[0]
    if not study or not pode_ver(s, study):
        raise PermissionError("exame não visível")
    objetos, assinatura = [], []
    pulos = ("Níveis da coluna (conferência) · TotalSegmentator", "Níveis da coluna · TotalSegmentator")
    escolhidos = []
    for r in repo.series_for_study(study, ocultas=True):
        # as SEG vão pelo menu de segmentação (seg_mapa: um mapa de rótulos compacto, também nas pilhas)
        if (r.modality or "").upper() not in O.OVERLAY_MODALITIES - {"SEG"} or (r.description or "") in pulos:
            continue
        if (r.modality or "").upper() in ("SR", "PR") and any(m in (r.description or "") for m in MARCAS_NOSSAS):
            continue
        for sop, cam in list(CAMINHOS.da_serie(repo, r.series_uid).items())[:50]:
            try:
                st = Path(cam).stat()
            except OSError:
                continue
            escolhidos.append((r, sop, cam))
            assinatura.append((cam, st.st_mtime_ns, st.st_size))
    niveis = _niveis_web(repo, study, assinatura)                   # 0.100.14: coluna e linfonodos
    chave = (study, tuple(assinatura))
    hit = _OVERLAYS.get(study)
    if hit is not None and hit[0] == chave:
        objetos = hit[1]
    else:
        for r, _sop, cam in escolhidos:
            obj = O.load_object(cam)
            if obj is None:
                continue
            obj.study_uid = obj.study_uid or study
            d = _objeto_web(obj)
            if d["por_sop"] or d["todos"] or d["planos"] or d["mascaras"]:
                d["serie"] = r.series_uid
                d["descricao"] = r.description or ""
                objetos.append(d)
        for r, cam, coluna in niveis:
            d = _objeto_niveis(r, cam, coluna, study)
            if d is not None:
                objetos.append(d)
        _OVERLAYS[study] = (chave, objetos)
        while len(_OVERLAYS) > 8:
            _OVERLAYS.pop(next(iter(_OVERLAYS)))
    return {"tipos": O.TIPOS, "ocultos": sorted(O.tipos_ocultos(settings)), "objetos": objetos}


def tabelas_de_cores() -> dict:
    """As tabelas de cores do Ipê (imaging/colormaps.py) para o site, como pontos (0–1, r, g, b em 0–1)."""
    from ipe.imaging import colormaps as CM
    out = {}
    for chave, (nome, pontos) in CM.COLORMAPS.items():
        if chave.startswith("vr_"):
            continue
        out[chave] = {"nome": nome, "pontos": [[float(x), *(float(v) / 255 for v in rgb)] for x, rgb in pontos]}
    return out


# ------------------------------------------------------------------ mamografia (0.99.98, W4)
class _Preferencias:
    """As configurações do servidor com as preferências do usuário por cima (o protocolo dele vale)."""

    def __init__(self, settings, prefs: dict | None):
        self.settings, self.prefs = settings, prefs or {}

    def get(self, chave, padrao=None):
        if chave in self.prefs and self.prefs[chave] not in (None, "", []):
            return self.prefs[chave]
        return self.settings.get(chave, padrao) if self.settings is not None else padrao


_ANALISE: dict[tuple, dict] = {}
_ANALISE_TRAVA = threading.Lock()


def mm_do_pixel_mg(ds) -> float | None:
    """0.100.17: o tamanho do pixel **no plano da mama** (mm), para o navegador manter a mesma escala ao rolar da 2D
    para a tomo. Na mamografia 2D ele costuma vir só em ImagerPixelSpacing (no detector: dividido pelo fator de
    ampliação estimado, quando o aparelho informa, dá o plano da mama — IHE Mammo); na tomossíntese, nos grupos
    funcionais. O carregador do navegador não lê nenhum dos dois: sem isto, a escala ia pela altura da caixa da
    mama, que muda de imagem para imagem — o zoom não acompanhava e não voltava."""
    def primeiro(v):
        try:
            x = float(v[0])
            return x if x > 0 else None
        except Exception:  # noqa: BLE001
            return None
    v = primeiro(ds.get("PixelSpacing")) if ds.get("PixelSpacing") is not None else None
    if v:
        return v
    try:
        pm = ds.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0]
        v = primeiro(pm.get("PixelSpacing")) if pm.get("PixelSpacing") is not None else None
        if v:
            return v
    except Exception:  # noqa: BLE001
        pass
    v = primeiro(ds.get("ImagerPixelSpacing")) if ds.get("ImagerPixelSpacing") is not None else None
    if not v:
        return None
    try:
        f = float(ds.get("EstimatedRadiographicMagnificationFactor") or 0)
    except (TypeError, ValueError):
        f = 0.0
    return v / f if 0.5 < f < 3 else v


def analise_da_mama(caminho: str, quadro: int = 0) -> dict:
    """Largura, altura, caixa da mama, lado da parede torácica e mamilo da imagem (as contas do Ipê em
    imaging/mammo.py). Guardado por arquivo e data: a mesma imagem não é lida duas vezes."""
    import numpy as np
    import pydicom

    from ipe.imaging import mammo as M
    try:
        chave = (caminho, Path(caminho).stat().st_mtime, quadro)
    except OSError:
        return {}
    with _ANALISE_TRAVA:
        if chave in _ANALISE:
            return _ANALISE[chave]
    out: dict = {}
    try:
        ds = pydicom.dcmread(caminho, force=True)
        mono1 = str(ds.get("PhotometricInterpretation", "")).upper() == "MONOCHROME1"
        n = int(ds.get("NumberOfFrames", 1) or 1)
        if n > 1:
            from pydicom.pixels import pixel_array
            px = pixel_array(ds, index=min(max(0, quadro), n - 1))
        else:
            px = ds.pixel_array
        px = np.asarray(px)
        if px.ndim == 2:
            h, w = px.shape
            caixa = M.breast_bbox(px, mono1)
            lado = M.chest_wall_side(-px if mono1 else px)
            mam = M.mamilo(px, mono1, lado) if lado else None
            out = {"largura": int(w), "altura": int(h), "caixa": list(caixa) if caixa else None,
                   "parede": lado, "mamilo": [float(mam[0]), float(mam[1])] if mam else None}
            mm = mm_do_pixel_mg(ds)
            if mm:
                out["mm"] = round(float(mm), 6)
    except Exception as e:  # noqa: BLE001
        log.debug("mamografia web: não li %s: %s", caminho, e)
    with _ANALISE_TRAVA:
        if len(_ANALISE) > 2000:
            _ANALISE.clear()
        _ANALISE[chave] = out
    return out


def _imagem_mg(im, analisar: bool = True) -> dict:
    meio = im.frames // 2 if im.tomo else 0
    d = {"study": im.study_uid, "series": im.series_uid, "sop": im.sop_uid, "quadros": int(im.frames or 1),
         "tomo": bool(im.tomo), "inicio": meio, "serie": im.serie, "rotulo": im.rotulo}
    if analisar:
        d.update(analise_da_mama(im.path, meio))
    return d


def mamografia(repo, s, q: dict, pode_ver, settings, prefs: dict | None = None) -> dict:
    """O protocolo de mamografia do exame resolvido para o navegador, com as mesmas regras do Ipê
    (imaging/mammo.py): por etapa e por número de telas (1 e 2), o que cada tela mostra — a imagem de cada
    quadro (do exame ou do anterior), para que lado vai a parede torácica, se espelha, a caixa da mama para o
    enquadramento e o mamilo para o alinhamento. As contas de imagem ficam no servidor; o navegador só põe a
    câmera."""
    from ipe.imaging import mammo as M
    if not s.can("view"):
        raise PermissionError("sem permissão")
    study = (q.get("study") or [""])[0]
    if not study or not pode_ver(s, study):
        raise PermissionError("exame não visível")
    info = repo.study_info(study) or {}
    cfg = _Preferencias(settings, prefs)
    from ipe import modules as MOD
    if not MOD.ligado(cfg, "mamografia"):
        return {"protocolo": None, "motivo": "o módulo de mamografia está desligado"}
    protos = [p for p in M.mg_protocols(cfg) if p.get("enabled", True)]
    if "MG" not in (info.get("modalities") or "").upper():
        return {"protocolo": None, "motivo": "o exame não é de mamografia"}
    escolhido = (q.get("protocolo") or [""])[0]
    proto = None
    if escolhido.isdigit() and int(escolhido) < len(protos):
        proto = protos[int(escolhido)]
    if proto is None:
        proto = M.find_mg_protocol(cfg, info.get("description", ""))
    if proto is None:
        return {"protocolo": None, "motivo": "nenhum protocolo de mamografia combina com o exame"}
    imagens = {0: M.read_images(repo, study)}
    if not any(im.side for im in imagens[0]):
        return {"protocolo": None, "motivo": "sem imagens com o lado reconhecido"}
    data = info.get("study_date", "") or ""
    outros = [r for r in repo.other_studies_same_patient(study)
              if "MG" in (r.modalities or "").upper() and r.study_date and r.study_date < data
              and pode_ver(s, r.study_uid)]
    outros.sort(key=lambda r: r.study_date, reverse=True)
    anteriores = {n + 1: r for n, r in enumerate(outros[:3])}

    def imgs(n: int):
        if n not in imagens:
            r = anteriores.get(n)
            imagens[n] = M.read_images(repo, r.study_uid) if r else []
        return imagens[n]

    catalogo: dict[str, dict] = {}

    def registrar(im) -> str:
        if im.sop_uid not in catalogo:
            catalogo[im.sop_uid] = _imagem_mg(im)
        return im.sop_uid

    passos = []
    for st in M.passos_do_protocolo(proto):
        por_telas = {}
        for quantos in (1, 2):
            quadros = [M.quadro_da_etapa(st, quantos, j) for j in range(quantos)]
            telas = []
            for indice, meu in enumerate(quadros):
                deslocamento = sum(x["cols"] for x in quadros[:indice])
                rows, cols = max(1, int(meu["rows"])), max(1, int(meu["cols"]))
                celulas = list(meu["cells"])
                usados: dict[int, set] = {}
                saida = []
                for k in range(rows * cols):
                    code = celulas[k] if k < len(celulas) else ""
                    cell = M.parse_code(code) if code else None
                    if cell is None:
                        saida.append({"codigo": code, "nota": "(quadro vazio no protocolo)" if not code
                                      else f"{code}: código inválido"})
                        continue
                    lista = imgs(cell.prior)
                    im = M.pick_image(lista, cell, usados.setdefault(cell.prior, set()))
                    c: dict = {"codigo": cell.code, "rotulo": cell.label, "anterior": cell.prior}
                    if cell.prior and cell.prior in anteriores:
                        c["data"] = anteriores[cell.prior].study_date
                    if im is None:
                        c["nota"] = f"{cell.label}\nnão encontrada" + (
                            "" if not cell.prior or cell.prior in anteriores else " (sem exame anterior)")
                        saida.append(c)
                        continue
                    usados[cell.prior].add(im.sop_uid)
                    c["sop"] = registrar(im)
                    # a outra forma da mesma incidência: a tomossíntese de uma 2D, ou a 2D de uma tomo
                    alt = M.pick_image(lista, cell.with_tomo(not cell.tomo))
                    if alt is not None and alt.tomo != im.tomo:
                        c["alt"] = registrar(alt)
                    # 0.100.2: a pilha do quadro, como no Ipê (mammo_view.cell_frames): as 2D da mesma mama e
                    # incidência e, em seguida, os cortes da tomossíntese — a roda passa por todas
                    base = cell.with_tomo(False)
                    membros = [x for x in M.same_view(lista, base) if not x.tomo] + \
                        [x for x in M.same_view(lista, base.with_tomo(True)) if x.tomo]
                    if len(membros) > 1 and any(x.sop_uid == im.sop_uid for x in membros):
                        # 0.100.4: cada imagem da pilha com a sua análise (caixa da mama, parede, mamilo) — ao
                        # rolar da 2D para a tomo o navegador refaz o enquadramento na imagem nova, na mesma
                        # escala e com a parede no mesmo lugar
                        for x in membros:
                            registrar(x)
                        c["pilha"] = [{"study": x.study_uid, "series": x.series_uid, "sop": x.sop_uid,
                                       "tomo": bool(x.tomo), "quadros": int(x.frames or 1)} for x in membros]
                        if c.get("alt") is None:
                            alt2 = next((x for x in membros if x.tomo != im.tomo), None)
                            if alt2 is not None:
                                c["alt"] = registrar(alt2)
                    if cols >= 2:
                        col, quantas = k % cols, cols
                        linha = celulas[(k // cols) * cols:(k // cols + 1) * cols]
                    else:
                        col, quantas = deslocamento % 2, 2
                        linha = list(st.get("cells") or [])
                    c["quer"] = M.parede_desejada(cell.side, col, quantas, M.lados_das_celulas(linha))
                    saida.append(c)
                telas.append({"rows": rows, "cols": cols, "celulas": saida})
            por_telas[str(quantos)] = telas
        passos.append({"nome": M.step_title(st), "enquadre": M.enquadre_da_etapa(st), "telas": por_telas})
    return {
        "protocolo": proto.get("name", ""), "protocolos": [p.get("name", "") for p in protos],
        "indice": protos.index(proto) if proto in protos else 0,
        "espelhar": bool(proto.get("chest_to_center", True)), "encostar": bool(proto.get("align_chest", True)),
        "zoom_junto": bool(proto.get("sync_zoom", True)), "alinhar": M.alinhamento_do_protocolo(proto),
        "margem": M.MARGEM_MAMA, "passos": passos, "imagens": catalogo,
        "anteriores": [{"n": n, "study": r.study_uid, "data": r.study_date} for n, r in anteriores.items()],
    }


# ------------------------------------------------------------------ dinâmica da mama (0.99.98, W5)
def dinamica(repo, s, q: dict, pode_ver, settings, prefs: dict | None = None) -> dict:
    """As fases da dinâmica do exame (a mesma detecção da janela do Ipê), com os tempos, as fases pré/inicial/
    tardia de fábrica e os parâmetros dele; e os mapas que o Ipê já gravou como séries ("SER (dinâmica)"…).
    Os mapas e as curvas são calculados no navegador, com as fórmulas de imaging/dynamic.py."""
    from ipe.imaging import phases as PH
    from ipe.imaging.dynamic import CLASSES, MAPS, DynamicSet, split_single_series
    from ipe.imaging.series import build_frames
    from ipe.ui.viewer import dinamica_config as DC
    if not s.can("view"):
        raise PermissionError("sem permissão")
    study = (q.get("study") or [""])[0]
    if not study or not pode_ver(s, study):
        raise PermissionError("exame não visível")
    from ipe import modules as MOD
    if not MOD.ligado(_Preferencias(settings, prefs), "rm_tc"):
        return {"fases": [], "mapas_salvos": [], "classes": CLASSES, "mapas": {},
                "motivo": "o módulo RM/TC avançado está desligado"}
    series = repo.series_for_study(study)
    nomes = {v[0]: k for k, v in MAPS.items()}
    salvos = []
    for r in series:
        d = (r.description or "").strip()
        if d.endswith(" (dinâmica)") and d[: -len(" (dinâmica)")] in nomes:
            chave = nomes[d[: -len(" (dinâmica)")]]
            salvos.append({"series": r.series_uid, "descricao": d, "chave": chave, "cores": MAPS[chave][4]})
    quadros = {}
    cands = []
    for r in series:
        if r.modality != "MR" or (r.description or "").strip().endswith(" (dinâmica)"):
            continue
        fr = build_frames(repo.instances_for_series(r.series_uid), r.series_uid)
        quadros[r.series_uid] = fr
        cands.append((r.series_uid, fr, r.series_number or 0, r.modality, r.description or ""))
    grupos = PH.detect(cands)
    escolha = max(grupos, key=len) if grupos else []
    fases, rotulos = [], []
    numero = {r.series_uid: r.series_number for r in series}
    if len(escolha) >= 2:
        for uid in escolha:
            fases.append(quadros[uid])
            rotulos.append(f"Se {numero.get(uid, '')}")
    else:
        for uid, fr, *_ in cands:
            ph = split_single_series(fr)
            if ph and len(ph) > len(fases):
                fases = ph
                rotulos = [f"Fase {i + 1} (Se {numero.get(uid, '')})" for i in range(len(ph))]
    base = {"fases": [], "mapas_salvos": salvos, "classes": CLASSES,
            "mapas": {k: {"nome": v[0], "descricao": v[1], "unidade": v[2], "cores": v[4]} for k, v in MAPS.items()}}
    if len(fases) < 3:
        return {**base, "motivo": "não achei as fases da dinâmica (são precisas a pré e duas pós-contraste)"}
    dset = DynamicSet(fases, rotulos)
    motivo = dset.check()
    if motivo:
        return {**base, "motivo": motivo}
    if q.get("_dset"):                         # para a correção de movimento (o mesmo conjunto de fases)
        return {"dset": dset}
    par = DC.parametros_iniciais(_Preferencias(settings, prefs))
    pre = int(par.get("pre", 0) or 0)
    pre = pre if 0 <= pre < len(dset.phases) - 2 else 0
    return {**base, "motivo": "",
            "fases": [{"rotulo": lab, "tempo": float(t),
                       "quadros": [{"series": f.series_uid, "sop": f.sop_uid, "quadro": f.frame_index + 1} for f in ph]}
                      for ph, lab, t in zip(dset.phases, dset.labels, dset.times)],
            "com_horario": bool(dset.timed), "pre": pre, "inicial": dset.default_early(pre),
            "tardia": len(dset.phases) - 1,
            "parametros": {k: par.get(k) for k in ("threshold_pct", "threshold_all", "noise_pct", "rapido_pct",
                                                  "tardio_pct", "sinal_min_pct", "relative")},
            # 0.100.8: a correção de movimento, como a deixou no Ipê
            "movimento": "rigido" if par.get("motion_rigido") else ("translacao" if par.get("motion") else "")}


_MOVIMENTO: dict = {}                          # (exame, pré, modo, fases) → resposta (a conta leva segundos)
_MOVIMENTO_TRAVA = __import__("threading").Lock()


def dinamica_movimento(repo, s, q: dict, pode_ver, settings, prefs: dict | None = None) -> dict:
    """0.100.8: a correção de movimento da dinâmica, com a mesma conta do Ipê (`DynamicMaps.estimate_motion`):
    translação 3D de cada fase sobre a pré (correlação de fase) e, no modo rígido, rotação + translação para a fase
    que girou. Devolve, por fase, o deslocamento (corte, linha, coluna, em voxels) e, para as que giraram, a matriz
    4×4 (índice da pré → índice da fase). O navegador aplica ao montar a pilha de cada corte."""
    import numpy as np

    from ipe.imaging.dynamic import DynamicMaps
    from ipe.imaging.series import FrameCache
    modo = (q.get("modo") or ["translacao"])[0]
    if modo not in ("translacao", "rigido"):
        raise ValueError("modo: translacao ou rigido")
    r = dinamica(repo, s, {**q, "_dset": ["1"]}, pode_ver, settings, prefs)
    dset = r.get("dset")
    if dset is None:
        return {"modo": "", "motivo": r.get("motivo") or "sem dinâmica", "shifts": [], "matrizes": {}, "rotacoes": []}
    pre = int((q.get("pre") or ["0"])[0] or 0)
    pre = pre if 0 <= pre < len(dset.phases) else 0
    study = (q.get("study") or [""])[0]
    chave = (study, pre, modo, tuple(f[0].series_uid + f[0].sop_uid for f in dset.phases))
    with _MOVIMENTO_TRAVA:
        if chave in _MOVIMENTO:
            return _MOVIMENTO[chave]
    maps = DynamicMaps(dset, FrameCache(max_mb=512), pre=pre, motion="rigido" if modo == "rigido" else True)
    mm = maps._espacamento()
    desl = [float(np.hypot(np.hypot(sz * mm[2], sy * mm[1]), sx * mm[0])) for sz, sy, sx in maps.shifts]
    partes = []
    if any(v > 0 for v in desl):
        i = int(np.argmax(desl))
        partes.append(f"maior deslocamento {desl[i]:.1f} mm (fase {i + 1})")
    if maps.matrizes:
        partes.append(f"rotação até {maps.rotacao_maxima:.1f}° (fase {', '.join(str(i + 1) for i in sorted(maps.matrizes))})")
    out = {"modo": modo, "motivo": "", "pre": pre,
           "shifts": [[float(v) for v in t] for t in maps.shifts],
           "matrizes": {str(i): np.asarray(M, float).tolist() for i, M in maps.matrizes.items()},
           "rotacoes": [float(v) for v in maps.rotacoes],
           "resumo": "; ".join(partes) or "sem movimento a corrigir",
           "maior_mm": float(max(desl, default=0.0)), "fase_maior": int(np.argmax(desl)) + 1 if desl else 0,
           "rotacao_max": float(maps.rotacao_maxima), "fases_giradas": [i + 1 for i in sorted(maps.matrizes)]}
    with _MOVIMENTO_TRAVA:
        _MOVIMENTO[chave] = out
        while len(_MOVIMENTO) > 32:
            _MOVIMENTO.pop(next(iter(_MOVIMENTO)))
    return out


# ------------------------------------------------------------------ laudo no navegador (0.99.98, W6)
def texto_dos_achados(repo, study: str) -> str:
    """Os achados de IA **revisados** (confirmados ou corrigidos) do exame, com a frase de cada ferramenta — o
    mesmo texto do botão "Mandar ao laudo" do painel de achados do Ipê. O sugerido não vai."""
    from ipe.ai import achados as AC
    from ipe.ai import ferramentas as FE
    por: dict[str, list] = {}
    for a in repo.achados(study):
        por.setdefault(a.get("ferramenta", ""), []).append(a)
    partes = []
    for ferr, lista in por.items():
        try:
            mod = FE.modulo(ferr)
        except Exception:  # noqa: BLE001
            mod = None
        fr = getattr(mod, "frase", None)
        proprio = getattr(mod, "laudo", None)
        try:
            txt = proprio(lista) if callable(proprio) else AC.texto_do_laudo(lista, fr)
        except Exception:  # noqa: BLE001
            txt = AC.texto_do_laudo(lista)
        if txt:
            partes.append(txt)
    return "\n".join(partes)


def laudo(repo, s, q: dict, pode_ver, leituras, settings=None) -> dict:
    """O que a janela do laudo do navegador precisa: os laudos do exame (versões), os modelos que ele vê, o
    sugerido para o exame, os campos automáticos ({paciente}, {comparacao}, {medidas}…), o texto dos achados de
    IA revisados e quem está laudando. Gravar, assinar e a trava vão pelo /api/rpc, com as regras de sempre."""
    from ipe.auth.visibilidade import com_visao
    from ipe.central import laudo_web as LW
    from ipe.reporting import fill as F
    from ipe.reporting.templates import PLACEHOLDERS, best_template
    if not s.can("view"):
        raise PermissionError("sem permissão")
    study = (q.get("study") or [""])[0]
    if not study or not pode_ver(s, study):
        raise PermissionError("exame não visível")
    info = repo.study_info(study) or {}
    with com_visao(s):
        modelos = repo.report_templates()
    sug = best_template(modelos, info.get("modalities", ""), info.get("description", ""))
    try:
        ctx = F.build_context(repo, study)
    except Exception as e:  # noqa: BLE001
        log.warning("laudo web: campos automáticos: %s", e)
        ctx = {}
    try:
        ia = texto_dos_achados(repo, study)
    except Exception as e:  # noqa: BLE001
        log.warning("laudo web: achados: %s", e)
        ia = ""
    trava = leituras.quem(study) if leituras is not None else None
    return {
        "laudos": repo.reports(study),
        "modelos": [{k: m.get(k) for k in ("id", "name", "modalities", "keywords", "text", "birads")} for m in modelos],
        # 0.100.4: o formulário BI-RADS, o PDF e o SR no exame, e a busca ativa da paciente
        "birads": LW.catalogo_birads(),
        "opcoes": LW.preferencias(settings, s.username, info),
        "buscas": LW.buscas_do_paciente(repo, info),
        "sugerido": sug.get("id") if sug else "",
        "contexto": {k: str(v) for k, v in ctx.items()},
        "campos": PLACEHOLDERS,
        "ia": ia,
        "trava": None if not trava else {"usuario": trava["usuario"], "nome": trava["nome"],
                                         "desde": time.strftime("%H:%M", time.localtime(trava["desde"]))},
        "pode": {"escrever": s.can("report"), "assinar": s.can("sign_report")},
        "eu": {"usuario": s.username, "nome": s.full_name or s.username},
    }
