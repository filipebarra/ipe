"""Nódulo pulmonar completo (0.99.62, plano AW O10), sem Qt.

- **Segmentação por clique:** a partir do ponto clicado, os voxels conectados acima do limiar (−500 HU de
  fábrica, a parte sólida; −750 HU pega também o vidro fosco), numa caixa de 25 mm de raio. Os vasos e a pleura
  que encostam saem por uma **abertura** (erosão e dilatação de 1 voxel no plano e nos cortes de até 1,5 mm): a
  ponte fina entre o nódulo e o vaso some na erosão, e fica o pedaço que contém o clique. Se a região encosta na
  borda da caixa, avisa que vazou.
- **Os números** são os mesmos dos candidatos da IA (`ai/nodulos.numeros_do_nodulo`): diâmetro maior e médio,
  volume, HU médio, parte sólida, consistência pelo HU e os três eixos.
- **O mesmo nódulo no exame anterior:** os achados confirmados ou corrigidos dos outros exames do paciente,
  levados para este pelo registro (`imaging/seguimento.transformar`), até 10 mm. Sem registro entre os dois, vale o
  mesmo lobo e até 25 mm entre as posições — marcado como "provável, sem registro", para conferir.
- **Crescimento:** variação do diâmetro médio e do volume e o tempo de duplicação do volume,
  TD = Δt · ln 2 / ln(V2/V1) (sem crescimento, "não se aplica").
"""
from __future__ import annotations

import math

import numpy as np

LIMIAR_SOLIDO = -500.0
LIMIAR_VIDRO = -750.0
RAIO_MM = 25.0
ABRIR_ATE_MM = 1.5                  # a abertura usa 1 voxel nos eixos de espaçamento até isto
DIST_COM_REGISTRO = 10.0
DIST_SEM_REGISTRO = 25.0


def _erode(m: np.ndarray, eixos) -> np.ndarray:
    e = m.copy()
    for ax in eixos:
        a = np.swapaxes(e, 0, ax)
        b = a.copy()
        b[1:] &= a[:-1]
        b[:-1] &= a[1:]
        b[0] = False
        b[-1] = False
        e = np.swapaxes(b, 0, ax)
    return e


def _dilate(m: np.ndarray, eixos) -> np.ndarray:
    d = m.copy()
    for ax in eixos:
        a = np.swapaxes(d, 0, ax)
        b = a.copy()
        b[1:] |= a[:-1]
        b[:-1] |= a[1:]
        d = np.swapaxes(b, 0, ax)
    return d


def segmentar(vol, semente_kji, limiar: float = LIMIAR_SOLIDO, raio_mm: float = RAIO_MM,
              abrir: bool = True) -> tuple[np.ndarray | None, tuple[int, int, int], list[str]]:
    """(máscara recortada (k, j, i), deslocamento do recorte, avisos)."""
    from ipe.imaging.segment import _grow
    data = vol.data
    nz, ny, nx = data.shape
    k, j, i = (int(np.clip(v, 0, n - 1)) for v, n in zip(semente_kji, (nz, ny, nx)))
    dz, dy, dx = (max(float(v), 1e-6) for v in (vol.dz, vol.dy, vol.dx))
    rk, rj, ri = int(raio_mm / dz) + 1, int(raio_mm / dy) + 1, int(raio_mm / dx) + 1
    k0, k1, j0, j1, i0, i1 = max(0, k - rk), min(nz, k + rk + 1), max(0, j - rj), min(ny, j + rj + 1), \
        max(0, i - ri), min(nx, i + ri + 1)
    sub = np.asarray(data[k0:k1, j0:j1, i0:i1], np.float32)
    dentro = sub >= limiar
    s = (k - k0, j - j0, i - i0)
    avisos: list[str] = []
    if not dentro[s]:                           # o clique caiu na borda: o voxel acima do limiar mais perto (3 mm)
        kk, jj, ii = np.nonzero(dentro)
        if not len(kk):
            return None, (k0, j0, i0), ["nada acima do limiar perto do clique"]
        d = ((kk - s[0]) * dz) ** 2 + ((jj - s[1]) * dy) ** 2 + ((ii - s[2]) * dx) ** 2
        n = int(np.argmin(d))
        if d[n] > 9.0:
            return None, (k0, j0, i0), ["nada acima do limiar a até 3 mm do clique"]
        s = (int(kk[n]), int(jj[n]), int(ii[n]))
    reg = _grow(dentro, s)
    if abrir:
        eixos = [ax for ax, sp in enumerate((dz, dy, dx)) if sp <= ABRIR_ATE_MM]
        if eixos:
            nucleo = _erode(reg, eixos)
            if nucleo.any():
                if not nucleo[s]:
                    kk, jj, ii = np.nonzero(nucleo)
                    d = ((kk - s[0]) * dz) ** 2 + ((jj - s[1]) * dy) ** 2 + ((ii - s[2]) * dx) ** 2
                    n = int(np.argmin(d))
                    s2 = (int(kk[n]), int(jj[n]), int(ii[n]))
                else:
                    s2 = s
                nucleo = _grow(nucleo, s2)
                aberta = _dilate(nucleo, eixos) & reg
                if aberta.sum() >= 0.2 * reg.sum() or reg.sum() > 0.5 * reg.size:
                    reg = aberta
            else:
                avisos.append("nódulo muito pequeno para separar dos vasos: confira a máscara")
    if not reg.any():
        return None, (k0, j0, i0), ["nada acima do limiar perto do clique"]
    borda = reg[0].any() or reg[-1].any() or reg[:, 0].any() or reg[:, -1].any() or reg[:, :, 0].any() \
        or reg[:, :, -1].any()
    if borda:
        avisos.append(f"a região chegou à borda da caixa de {raio_mm:.0f} mm: deve ter vazado para um vaso ou para "
                      "a pleura — confira e, se precisar, corrija nas Estruturas")
    zs, ys, xs = np.nonzero(reg.any(axis=(1, 2)))[0], np.nonzero(reg.any(axis=(0, 2)))[0], \
        np.nonzero(reg.any(axis=(0, 1)))[0]
    m = reg[zs[0]:zs[-1] + 1, ys[0]:ys[-1] + 1, xs[0]:xs[-1] + 1]
    return m, (k0 + int(zs[0]), j0 + int(ys[0]), i0 + int(xs[0])), avisos


# ------------------------------------------------------------------ o mesmo nódulo em outro exame
def lobo_do_achado(a: dict) -> str:
    return (a.get("local") or "").strip().lower()


def _media(a: dict) -> float | None:
    from ipe.ai import achados as AC
    n = AC.numeros_validos(a)
    v = (n.get("medio_mm") or n.get("diametro_mm") or {}).get("v")
    return float(v) if v is not None else None


def _volume(a: dict) -> float | None:
    from ipe.ai import achados as AC
    v = (AC.numeros_validos(a).get("volume_mm3") or {}).get("v")
    return float(v) if v else None


def correspondente(repo, achado: dict, anteriores: list[dict], datas: dict[str, str]) -> dict | None:
    """O achado de outro exame (mais antigo) que é o mesmo nódulo. Devolve {achado, distancia, como} ou None.

    `anteriores`: achados de nódulo dos outros exames do paciente, já revisados (confirmados ou corrigidos)."""
    from ipe.imaging import seguimento as SG
    if not achado.get("posicao"):
        return None
    p = np.asarray(achado["posicao"], float)
    data_atual = datas.get(achado["study_uid"], "")
    melhor = None
    for b in anteriores:
        if b["study_uid"] == achado["study_uid"] or not b.get("posicao"):
            continue
        if (datas.get(b["study_uid"], "") or "") > (data_atual or "99999999"):
            continue
        q = SG.transformar(repo, b["posicao"], b["study_uid"], achado["study_uid"])
        if q is not None:
            d, como, lim = float(np.linalg.norm(np.asarray(q) - p)), "pelo registro", DIST_COM_REGISTRO
        else:
            if lobo_do_achado(b) and lobo_do_achado(b) != lobo_do_achado(achado):
                continue
            d = float(np.linalg.norm(np.asarray(b["posicao"], float) - p))
            como, lim = "provável, sem registro (confira)", DIST_SEM_REGISTRO
        if d > lim:
            continue
        chave = (0 if como == "pelo registro" else 1, -(int((datas.get(b["study_uid"], "") or "0")[:8] or 0)), d)
        if melhor is None or chave < melhor[0]:
            melhor = (chave, {"achado": b, "distancia": d, "como": como})
    return None if melhor is None else melhor[1]


def _dias(a: str, b: str) -> int | None:
    from datetime import date
    try:
        da = date(int(a[:4]), int(a[4:6]), int(a[6:8]))
        db = date(int(b[:4]), int(b[4:6]), int(b[6:8]))
    except (ValueError, TypeError, IndexError):
        return None
    return (db - da).days


def crescimento(antes: dict, agora: dict, data_antes: str, data_agora: str) -> dict:
    """{dias, medio_antes, medio_agora, d_medio_mm, vol_antes, vol_agora, pct_vol, td_dias, texto}."""
    out: dict = {"dias": _dias(data_antes, data_agora)}
    ma, mb = _media(antes), _media(agora)
    va, vb = _volume(antes), _volume(agora)
    out.update(medio_antes=ma, medio_agora=mb, vol_antes=va, vol_agora=vb)
    partes = []
    if ma is not None and mb is not None:
        out["d_medio_mm"] = mb - ma
        partes.append(f"diâmetro médio {ma:.1f} → {mb:.1f} mm ({mb - ma:+.1f} mm)")
    if va and vb:
        out["pct_vol"] = 100.0 * (vb - va) / va
        partes.append(f"volume {va:.0f} → {vb:.0f} mm³ ({out['pct_vol']:+.0f}%)")
        dias = out["dias"]
        if dias and dias > 0 and vb > va:
            td = dias * math.log(2) / math.log(vb / va)
            out["td_dias"] = td
            partes.append(f"tempo de duplicação {td:.0f} dias")
        elif dias and dias > 0:
            partes.append("tempo de duplicação não se aplica (não cresceu)")
    d = data_antes
    quando = f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d or "") >= 8 else "exame anterior"
    out["quando"] = quando
    out["lista"] = partes
    out["partes"] = "; ".join(partes) if partes else "sem números para comparar"
    out["texto"] = f"Em {quando}: " + out["partes"]
    return out
