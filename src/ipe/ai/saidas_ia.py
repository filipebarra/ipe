"""O que as IAs gravam e mandam: SEG, tabelas e a série com overlay colorido (0.100.124).

Pedido dele (26/11/2026): *"o meu PACS não consegue ver essas imagens (SEG). Grave, para todas as IAs: séries SEG,
tabelas e série com overlay colorido. Coloque nas configurações das IAs: escolher salvar essas 3 séries e também
enviar para o destino."*

- **SEG** — as máscaras (o botão CAD/overlay do Ipê usa; muitos PACS não mostram);
- **Tabelas** — as imagens com números (volumes, medidas, conferência): o PACS vê como imagem comum;
- **Overlay colorido** — o mesmo exame com as máscaras pintadas por cima, uma imagem por corte, na mesma posição
  do corte original: qualquer PACS rola. É gerada a partir da SEG gravada (lê a SEG, não a ferramenta), por isso
  vale para todas as IAs que gravam SEG.

As caixas decidem **o que vai** aos destinos (e se a série colorida é criada); a SEG e as tabelas sempre ficam no
exame do Ipê, porque o CAD/overlay e as medidas dependem delas. Os destinos daqui valem para todas as IAs, além dos
que cada ferramenta já tem.
"""
from __future__ import annotations

import logging
import threading

import numpy as np

log = logging.getLogger(__name__)

CHAVE_SEG = "ia.saida.seg"
CHAVE_TABELAS = "ia.saida.tabelas"
CHAVE_OVERLAY = "ia.saida.overlay"
CHAVE_DESTINOS = "ia.saida.destinos"
PADROES = {CHAVE_SEG: True, CHAVE_TABELAS: True, CHAVE_OVERLAY: False, CHAVE_DESTINOS: []}

MARCA_OVERLAY = "overlay colorido"
SERIE_OVERLAY = 990
ALFA = 0.40
MAX_CORTES = 800                       # acima disso a série colorida não é feita (o exame é enorme)

_CTX: dict = {}
_TRAVA = threading.Lock()


def config(settings, chave):
    if settings is None:
        return PADROES[chave]
    try:
        v = settings.get(chave, PADROES[chave])
    except Exception:  # noqa: BLE001
        v = PADROES[chave]
    return PADROES[chave] if v is None else v


SIM, NAO, GLOBAL = "sim", "nao", "global"
SOMAR, SO_ESTA = "somar", "so_esta"
CAMPOS = {"seg": CHAVE_SEG, "tabelas": CHAVE_TABELAS, "overlay": CHAVE_OVERLAY}


def chave_ferramenta(ferramenta: str, campo: str) -> str:
    """`ia.saida.<ferramenta>.<campo>` — campo: seg, tabelas, overlay (global/sim/nao) ou destinos (somar/so_esta)."""
    return f"ia.saida.{ferramenta}.{campo}"


def escolha(settings, ferramenta, campo: str) -> str:
    """O que a ferramenta escolheu para o campo: "sim", "nao" ou "global" (sem escolha própria)."""
    if settings is None or not ferramenta:
        return GLOBAL
    try:
        v = str(settings.get(chave_ferramenta(ferramenta, campo), GLOBAL) or GLOBAL)
    except Exception:  # noqa: BLE001
        return GLOBAL
    return v if v in (SIM, NAO, SOMAR, SO_ESTA) else GLOBAL


def efetivo(settings, campo: str, ferramenta=None) -> bool:
    """A escolha da ferramenta vale por cima da global (0.100.124)."""
    e = escolha(settings, ferramenta, campo)
    if e == SIM:
        return True
    if e == NAO:
        return False
    return bool(config(settings, CAMPOS[campo]))


def registrar(settings, db, storage) -> None:
    """O motor de automação avisa onde está o banco e o armazenamento (para a série colorida ser gravada no lugar certo)."""
    with _TRAVA:
        _CTX.update(settings=settings, db=db, storage=storage)


def contexto() -> dict:
    with _TRAVA:
        return dict(_CTX)


def destinos(settings) -> list:
    v = config(settings, CHAVE_DESTINOS)
    return list(v) if isinstance(v, (list, tuple)) else []


# ------------------------------------------------------------------ classificar e filtrar
def classe(info: dict | None) -> str:
    """"seg", "overlay", "tabela" (imagens OT) ou "outra" (SR, séries de imagem das outras IAs…)."""
    if not info:
        return "outra"
    mod = (info.get("modality") or "").upper()
    desc = info.get("description") or ""
    if mod == "SEG":
        return "seg"
    if MARCA_OVERLAY in desc:
        return "overlay"
    if mod in ("OT", "SC"):
        return "tabela"
    return "outra"


def filtrar(repo, settings, series, ferramenta=None) -> list[str]:
    """As séries que vão aos destinos: tira as classes desmarcadas (as "outras" sempre vão).
    A escolha da ferramenta, se houver, vale por cima da global."""
    ligado = {"seg": efetivo(settings, "seg", ferramenta), "tabela": efetivo(settings, "tabelas", ferramenta),
              "overlay": efetivo(settings, "overlay", ferramenta), "outra": True}
    out = []
    for u in series or []:
        if not u:
            continue
        try:
            c = classe(repo.series_info(u))
        except Exception:  # noqa: BLE001
            c = "outra"
        if ligado.get(c, True):
            out.append(u)
    return out


def ids_de_destino(settings, ids, ferramenta=None) -> list:
    """Os destinos da ferramenta mais os de todas as IAs, sem repetir — ou só os da ferramenta, se ela assim escolheu."""
    so_esta = escolha(settings, ferramenta, "destinos") == SO_ESTA
    vistos, out = set(), []
    for i in list(ids or []) + ([] if so_esta else destinos(settings)):
        k = str(i)
        if k not in vistos:
            vistos.add(k)
            out.append(i)
    return out


# ------------------------------------------------------------------ série com overlay colorido
def _janela(ds) -> tuple[float, float] | None:
    try:
        c, w = ds.get("WindowCenter"), ds.get("WindowWidth")
        c = float(c[0] if hasattr(c, "__len__") and not isinstance(c, str) else c)
        w = float(w[0] if hasattr(w, "__len__") and not isinstance(w, str) else w)
        if w > 1:
            return c, w
    except Exception:  # noqa: BLE001
        pass
    return None


def _cinza(ds) -> np.ndarray:
    """Pixels da imagem → uint8 (janela do próprio arquivo; sem ela, percentis 1–99; CT sem janela: partes moles)."""
    arr = ds.pixel_array.astype(np.float32)
    if arr.ndim == 3 and arr.shape[-1] in (3, 4):                    # já é colorida
        return np.clip(arr[..., :3], 0, 255).astype(np.uint8)
    arr = arr * float(ds.get("RescaleSlope", 1) or 1) + float(ds.get("RescaleIntercept", 0) or 0)
    j = _janela(ds)
    if j is None and str(ds.get("Modality", "")).upper() == "CT":
        j = (40.0, 400.0)
    if j is None:
        lo, hi = np.percentile(arr, (1, 99))
        if hi <= lo:
            hi = lo + 1
    else:
        lo, hi = j[0] - j[1] / 2, j[0] + j[1] / 2
    g = np.clip((arr - lo) / max(hi - lo, 1e-6), 0, 1)
    if str(ds.get("PhotometricInterpretation", "")).upper() == "MONOCHROME1":
        g = 1 - g
    g = (g * 255).astype(np.uint8)
    return np.repeat(g[..., None], 3, axis=2)


def _borda(m: np.ndarray) -> np.ndarray:
    """Os pixels da máscara que encostam em fora dela (inclusive nas bordas do recorte)."""
    p = np.pad(m, 1)
    dentro = p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    return m & ~dentro


def _colar(rgb: np.ndarray, mask: np.ndarray, r0: int, c0: int, cor) -> None:
    """Pinta `mask` (recorte) na imagem a partir da linha r0/coluna c0: miolo translúcido e contorno cheio."""
    h, w = rgb.shape[:2]
    mh, mw = mask.shape
    ra, ca = max(r0, 0), max(c0, 0)
    rb, cb = min(r0 + mh, h), min(c0 + mw, w)
    if rb <= ra or cb <= ca:
        return
    m = mask[ra - r0:rb - r0, ca - c0:cb - c0]
    if not m.any():
        return
    alvo = rgb[ra:rb, ca:cb]
    cor = np.asarray(cor[:3], np.float32)
    miolo = m
    alvo[miolo] = (alvo[miolo].astype(np.float32) * (1 - ALFA) + cor * ALFA).astype(np.uint8)
    alvo[_borda(m)] = cor.astype(np.uint8)


def _posicao_no_corte(mf, ipp, ori, sp) -> tuple[int, int, float, float] | None:
    """Linha e coluna do canto da máscara na imagem de origem e razões de escala (spacing da máscara / da imagem)."""
    if mf.position is None or mf.orientation is None or mf.spacing is None:
        return None
    d = np.asarray(mf.position, float) - ipp
    u, v = np.asarray(ori[:3], float), np.asarray(ori[3:], float)
    c0 = float(np.dot(d, u)) / sp[1]
    r0 = float(np.dot(d, v)) / sp[0]
    return int(round(r0)), int(round(c0)), float(mf.spacing[0]) / sp[0], float(mf.spacing[1]) / sp[1]


def _reamostrar(m: np.ndarray, fr: float, fc: float) -> np.ndarray:
    if abs(fr - 1) < 0.02 and abs(fc - 1) < 0.02:
        return m
    nh, nw = max(int(round(m.shape[0] * fr)), 1), max(int(round(m.shape[1] * fc)), 1)
    ri = np.minimum((np.arange(nh) / fr).astype(int), m.shape[0] - 1)
    ci = np.minimum((np.arange(nw) / fc).astype(int), m.shape[1] - 1)
    return m[np.ix_(ri, ci)]


def overlay_de_seg(repo, db, storage, seg_series_uid: str) -> str | None:
    """Lê a SEG gravada, pinta as máscaras nos cortes da série de origem e grava a série colorida.
    Devolve o UID da série nova (ou None: SEG sem origem achável, origem multiquadro, ou nada para pintar)."""
    import pydicom

    from ipe.imaging import overlays as OV
    from ipe.imaging.derived import save_secondary_capture_stack
    seg_insts = repo.instances_for_series(seg_series_uid)
    info = repo.series_info(seg_series_uid) or {}
    if not seg_insts:
        return None
    objs = []
    for si in seg_insts:
        try:
            ds = pydicom.dcmread(si["path"], force=True)
            objs.append(OV.parse_seg(ds, si["path"]))
        except Exception:  # noqa: BLE001
            log.warning("overlay colorido: não li a SEG %s", si.get("path"), exc_info=True)
    masks = [m for o in objs for m in o.masks]
    origem = next((o.series_ref for o in objs if o.series_ref), "")
    if not masks or not origem:
        return None
    fonte = repo.instances_for_series(origem)
    if not fonte or len(fonte) > MAX_CORTES or any((f.get("frames") or 1) > 1 for f in fonte):
        return None
    cab = {}
    for f in fonte:
        try:
            h = pydicom.dcmread(f["path"], stop_before_pixels=True, force=True)
            cab[f["sop_uid"]] = (np.array([float(x) for x in h.ImagePositionPatient]),
                                 [float(x) for x in h.ImageOrientationPatient],
                                 [float(x) for x in h.PixelSpacing])
        except Exception:  # noqa: BLE001
            continue
    if not cab:
        return None
    # de cada máscara → o corte (pelo SOP referenciado; sem ele, pelo plano mais próximo)
    sops = list(cab)
    normal = None
    por_corte: dict[str, list] = {}
    for mf in masks:
        alvo = mf.ref[0] if mf.ref and mf.ref[0] in cab else None
        if alvo is None and mf.position is not None:
            if normal is None:
                o = cab[sops[0]][1]
                normal = np.cross(o[:3], o[3:])
            dist = [abs(float(np.dot(np.asarray(mf.position, float) - cab[s][0], normal))) for s in sops]
            k = int(np.argmin(dist))
            if dist[k] < 2.0:
                alvo = sops[k]
        if alvo is not None:
            por_corte.setdefault(alvo, []).append(mf)
    if not por_corte:
        return None
    ordem = sorted(fonte, key=lambda f: (f.get("instance_number") or 0))
    idx = [k for k, f in enumerate(ordem) if f["sop_uid"] in por_corte]
    if not idx:
        return None
    itens = []
    for f in ordem[min(idx):max(idx) + 1]:
        try:
            ds = pydicom.dcmread(f["path"], force=True)
            rgb = _cinza(ds)
        except Exception:  # noqa: BLE001
            log.warning("overlay colorido: não li %s", f.get("path"), exc_info=True)
            continue
        ipp, ori, sp = cab.get(f["sop_uid"], (None, None, None))
        for mf in por_corte.get(f["sop_uid"], []):
            pos = _posicao_no_corte(mf, ipp, ori, sp) if ipp is not None else None
            if pos is None:
                continue
            r0, c0, fr, fc = pos
            _colar(rgb, _reamostrar(np.asarray(mf.mask, bool), fr, fc), r0, c0, mf.color)
        itens.append((rgb, f["path"]))
    if not itens:
        return None
    base = (info.get("description") or "IA")
    for m in ("· TotalSegmentator", "· Ipê", "· Ipe", "· BraTS", "· autoPET", "· MedSAM2", "· FLAMeS", "· TotalSpineSeg"):
        base = base.replace(m, "")
    base = base.strip(" ·-") or "IA"
    desc = f"{base[:30]} · {MARCA_OVERLAY} · Ipê"
    uid, _ = save_secondary_capture_stack(itens, db, storage, desc, series_number=SERIE_OVERLAY,
                                          parametros=f"overlay das máscaras da SEG {seg_series_uid}")
    return uid


def completar(repo, db, storage, settings, series, ferramenta=None) -> list[str]:
    """Com a opção ligada, cria a série colorida de cada SEG da lista (e já existente não é refeita).
    Devolve a lista com as séries novas no fim. Roda em segundo plano."""
    series = [u for u in (series or []) if u]
    if not efetivo(settings, "overlay", ferramenta) or db is None or storage is None:
        return series
    novas = []
    for u in series:
        try:
            if classe(repo.series_info(u)) != "seg":
                continue
            nova = overlay_de_seg(repo, db, storage, u)
            if nova:
                novas.append(nova)
        except Exception:  # noqa: BLE001
            log.warning("overlay colorido da série %s", u, exc_info=True)
    return series + novas
