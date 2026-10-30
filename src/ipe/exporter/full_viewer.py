"""Visualizador completo que vai junto com a exportação: valores originais dos pixels (HU etc.),
medidas em mm, ROIs com média/DP, janelas reais e MPR ortogonal.

Os pixels vão em arquivos .js (o navegador carrega <script> mesmo abrindo do disco, sem servidor):
cada arquivo chama DV.chunk(id, n, "<base64>") com os quadros em int16, bytes separados
(altos/baixos, comprimem melhor) e compactados com zlib — o navegador descompacta com
DecompressionStream("deflate").
"""

from __future__ import annotations

import base64
import json
import logging
import zlib
from pathlib import Path

import numpy as np

from ipe.imaging.series import read_frame
from ipe.imaging.windowing import auto_window

log = logging.getLogger(__name__)

CHUNK_BYTES = 6 * 1024 * 1024       # ~6 MB de pixels por arquivo .js
MAX_DIM = 2048                      # imagens maiores (mamografia) são reduzidas para caber
MPR_MIN_SLICES = 8


def _vec(v):
    return None if v is None else [float(x) for x in v]


def _encode_int16(arr: np.ndarray, scale: float, offset: float) -> bytes:
    raw = np.clip(np.round((arr - offset) / scale), -32768, 32767).astype("<i2")
    b = raw.view(np.uint8).reshape(-1, 2)
    return b[:, 1].tobytes() + b[:, 0].tobytes()     # altos, depois baixos


def _mpr_geometry(frames, shape) -> dict | None:
    """Série serve para MPR? Mesma orientação, posições alinhadas e espaçamento regular."""
    if len(frames) < MPR_MIN_SLICES:
        return None
    ori = frames[0].orientation
    if ori is None or any(f.orientation is None or f.position is None for f in frames):
        return None
    ori = np.asarray(ori, float)
    if any(np.abs(np.asarray(f.orientation, float) - ori).max() > 1e-3 for f in frames):
        return None
    n = np.cross(ori[:3], ori[3:])
    pos = np.array([np.asarray(f.position, float) for f in frames])
    d = pos @ n
    steps = np.diff(d)
    if len(steps) == 0 or np.any(np.abs(steps) < 1e-4):
        return None
    mean = float(np.mean(steps))
    if np.max(np.abs(steps - mean)) > max(0.05 * abs(mean), 0.05):
        return None                                         # espaçamento irregular
    kvec = (pos[-1] - pos[0])
    kvec = kvec / (np.linalg.norm(kvec) or 1.0)
    return {"slice": abs(mean), "k": [float(x) for x in kvec]}


def write_series(series: dict, sid: str, vdir: Path, annotations: list[dict], keys: set[tuple[str, int]],
                 progress=None, cancel=None) -> dict:
    """Grava os dados da série e devolve o descritor para a página."""
    frames = series["frames"]
    ddir = vdir / "dados"
    ddir.mkdir(parents=True, exist_ok=True)
    first = read_frame(frames[0])
    meta = {"id": sid, "label": f"{series['number']} {series['modality']} {series['description']}".strip(),
            "modality": series["modality"], "n": len(frames), "chunks": [], "annotations": [], "keys": []}
    if first.is_color:
        # cor (US, fotos): JPG por quadro; mede distâncias, sem valores
        from ipe.exporter.core import render_frame, save_image
        meta["color"] = True
        meta["files"] = []
        h, w = first.pixels.shape[:2]
        k = max(1.0, max(h, w) / MAX_DIM)
        for i, f in enumerate(frames):
            if cancel is not None and cancel():
                from ipe.exporter.core import Cancelled
                raise Cancelled("Exportação cancelada.")
            fn = f"{sid}_{i:04d}.jpg"
            save_image(render_frame(f, max_size=MAX_DIM if k > 1 else None), ddir / fn, 90)
            meta["files"].append(f"VISUALIZADOR/dados/{fn}")
            if progress:
                progress()
        rs, cs = first.pixel_spacing or (0, 0)
        meta.update(rows=int(h / k), cols=int(w / k), spacing=[rs * k, cs * k] if rs else None)
        return meta

    rows, cols = first.pixels.shape[:2]
    step = int(np.ceil(max(rows, cols) / MAX_DIM))
    out_r, out_c = (rows + step - 1) // step, (cols + step - 1) // step
    # varre a série: faixa de valores e se são inteiros (para escolher escala/offset do int16)
    imgs = []
    vmin, vmax, integral = np.inf, -np.inf, True
    same_shape = True
    for f in frames:
        img = first if f is frames[0] else read_frame(f)
        px = img.pixels
        if px.shape != (rows, cols):
            same_shape = False
            px = np.resize(px, (rows, cols))
        if step > 1:
            px = px[::step, ::step]
        imgs.append((px, img))
        vmin, vmax = min(vmin, float(px.min())), max(vmax, float(px.max()))
        if integral and not np.allclose(px[:: max(1, px.shape[0] // 64), :: max(1, px.shape[1] // 64)],
                                        np.round(px[:: max(1, px.shape[0] // 64), :: max(1, px.shape[1] // 64)])):
            integral = False
        if cancel is not None and cancel():
            from ipe.exporter.core import Cancelled
            raise Cancelled("Exportação cancelada.")
    if integral and vmax - vmin <= 65535:
        scale = 1.0
        offset = 0.0 if (vmin >= -32768 and vmax <= 32767) else float(np.floor(vmin) + 32768)
    else:
        scale = max((vmax - vmin) / 65000.0, 1e-9)
        offset = vmin + 32768 * scale
    w, l = first.window or auto_window(first.pixels)
    rs, cs = first.pixel_spacing or (0.0, 0.0)
    meta.update(rows=int(out_r), cols=int(out_c), scale=scale, offset=offset, window=[float(w), float(l)],
                invert=first.header.get("_monochrome1") == "1", step=step,
                spacing=[rs * step, cs * step] if rs and cs else None,
                orientation=_vec(frames[0].orientation), thickness=first.header.get("SliceThickness", ""))
    geo = _mpr_geometry(frames, (rows, cols)) if same_shape else None
    if geo is not None and meta["spacing"]:
        meta["mpr"] = geo
    meta["pos"] = [_vec(f.position) for f in frames]
    if (series["modality"] or "").upper() == "MG":
        mg = _mg_meta(frames, imgs, meta["invert"])
        if mg:
            meta["mg"] = mg
    try:
        import pydicom
        po = pydicom.dcmread(frames[0].path, stop_before_pixels=True, force=True).get("PatientOrientation")
        if po is not None and len(po) == 2:
            meta["porient"] = [str(po[0]), str(po[1])]
    except Exception:  # noqa: BLE001
        pass
    # blocos
    per = max(1, CHUNK_BYTES // (out_r * out_c * 2))
    for ci, k0 in enumerate(range(0, len(imgs), per)):
        parts = []
        for px, _img in imgs[k0:k0 + per]:
            parts.append(_encode_int16(px.astype(np.float64), scale, offset))
            if progress:
                progress()
        comp = zlib.compress(b"".join(parts), 4)
        fn = f"{sid}_{ci:03d}.js"
        (ddir / fn).write_text(f'DV.chunk("{sid}",{ci},"{base64.b64encode(comp).decode()}");', encoding="ascii")
        meta["chunks"].append({"file": f"VISUALIZADOR/dados/{fn}", "k0": k0, "n": len(imgs[k0:k0 + per])})
    # medidas do programa e imagens-chave (em pixels desta exportação)
    index = {(f.sop_uid, f.frame_index): i for i, f in enumerate(frames)}
    for a in annotations:
        i = index.get((a["sop_uid"], int(a["frame_index"])))
        if i is None:
            continue
        try:
            d = json.loads(a.get("data") or "{}")
        except ValueError:
            continue
        pts = [[float(p[0]) / step, float(p[1]) / step] for p in d.get("points", [])]
        meta["annotations"].append({"k": i, "kind": a["kind"], "pts": pts, "text": d.get("text", "")})
    meta["keys"] = sorted(index[k] for k in keys if k in index)
    return meta


def _mg_meta(frames, imgs, invert: bool) -> list[dict]:
    """Mamografia: lado, incidência, caixa da mama, lado da parede torácica e janela do tecido —
    tudo em pixels DESTA exportação, para o visualizador do navegador montar o protocolo, a janela
    e o zoom por quadrante sem precisar analisar a imagem."""
    from ipe.imaging.mammo import breast_bbox, chest_wall_side
    from ipe.imaging.windowing import tissue_window
    import pydicom
    out: list[dict] = []
    lados: dict[str, tuple[str, str]] = {}
    for i, (px, _img) in enumerate(imgs):
        f = frames[i]
        if f.path not in lados:
            try:
                ds = pydicom.dcmread(f.path, stop_before_pixels=True, force=True)
                lado = str(ds.get("ImageLaterality", "") or ds.get("Laterality", "") or "").upper()[:1]
                vista = str(ds.get("ViewPosition", "") or "").upper()
            except Exception:  # noqa: BLE001
                lado, vista = "", ""
            lados[f.path] = (lado, vista)
        lado, vista = lados[f.path]
        item: dict = {"side": lado, "view": vista}
        try:
            pequena = px[:: max(1, px.shape[0] // 400), :: max(1, px.shape[1] // 400)]
            box = breast_bbox(px, invert)
            if box:
                item["bbox"] = [int(v) for v in box]
            lado_tela = chest_wall_side(-px if invert else px)
            if lado_tela:
                item["chest"] = lado_tela
            w, l = tissue_window(pequena, invert)
            item["tissue"] = [float(w), float(l)]
        except Exception as e:  # noqa: BLE001
            log.debug("mamografia (exportação): %s", e)
        out.append(item)
    return out if any(x.get("bbox") for x in out) else []


def write_thumb(series: dict, path: Path) -> None:
    from ipe.exporter.core import render_frame, save_image
    f = series["frames"][len(series["frames"]) // 2]
    save_image(render_frame(f, max_size=128), path, 85)
