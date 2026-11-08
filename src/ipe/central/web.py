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


def tabelas_de_cores() -> dict:
    """As tabelas de cores do Ipê (imaging/colormaps.py) para o site, como pontos (0–1, r, g, b em 0–1)."""
    from ipe.imaging import colormaps as CM
    out = {}
    for chave, (nome, pontos) in CM.COLORMAPS.items():
        if chave.startswith("vr_"):
            continue
        out[chave] = {"nome": nome, "pontos": [[float(x), *(float(v) / 255 for v in rgb)] for x, rgb in pontos]}
    return out
