"""Seguimento oncológico entre datas (0.99.59, item 7 do backlog — AW O1 e O3), sem Qt.

- **Ligação pela posição (O1):** cada medida ligada a uma lesão guarda o centro e os pontos em mm (coordenadas
  do paciente). Uma medida nova num exame de seguimento é levada para o espaço dos exames anteriores pelo
  registro (a matriz do registro rígido ou o deslocamento salvo ao ligar os quadros); se cair a até 10 mm de
  onde uma lesão estava no exame anterior mais recente, liga sozinha a essa lesão. Sem registro entre os dois
  exames, não liga — não há como saber onde o ponto está no outro exame.
- **Assistente (O3):** as lesões medidas antes e ainda sem medida neste exame, com a posição estimada aqui
  (pelo mesmo registro) para "repetir" a medida, ou marcar "pequena demais" (5 mm, RECIST 1.1) ou "ausente" (0).
"""
from __future__ import annotations

import json

import numpy as np

RAIO_PADRAO_MM = 10.0
TIPOS_DE_MEDIDA = ("line", "ellipse", "rect", "polygon")
FERRAMENTA_DO_TIPO = {"line": "measure", "ellipse": "ellipse", "rect": "rect", "polygon": "polygon"}


def centro(pontos_mm) -> list[float] | None:
    pts = [p for p in (pontos_mm or []) if p is not None]
    if not pts:
        return None
    return [float(v) for v in np.mean(np.asarray(pts, float), axis=0)]


def transformar(repo, p, de: str, para: str):
    """O ponto `p` (mm) do exame `de` no espaço do exame `para`, ou None sem registro entre os dois."""
    if p is None:
        return None
    if de == para:
        return np.asarray(p, float)
    try:
        M = repo.get_registration_matriz(de, para)
    except Exception:  # noqa: BLE001
        M = None
    if M is not None:
        M = np.asarray(M, float)
        return (M @ np.append(np.asarray(p, float), 1.0))[:3]
    try:
        reg = repo.get_registration(de, para)
    except Exception:  # noqa: BLE001
        reg = None
    if reg is None:
        return None
    return np.asarray(p, float) + np.asarray(reg[0], float)


def medidas_das_lesoes(anotacoes: list[dict]) -> dict[int, list[dict]]:
    """{id da lesão: [{study_uid, series_uid, sop_uid, frame_index, kind, centro, pontos_mm, id}]}."""
    out: dict[int, list[dict]] = {}
    for a in anotacoes:
        try:
            d = json.loads(a.get("data") or "{}")
        except ValueError:
            continue
        meta = d.get("meta") or {}
        lid = meta.get("lesion")
        if lid is None:
            continue
        out.setdefault(lid, []).append({"study_uid": a["study_uid"], "series_uid": a.get("series_uid", ""),
                                        "sop_uid": a.get("sop_uid", ""), "frame_index": int(a.get("frame_index") or 0),
                                        "kind": d.get("kind") or a.get("kind", ""), "centro": meta.get("centro"),
                                        "pontos_mm": meta.get("pontos_mm"), "id": a.get("id"), "mm": meta.get("mm")})
    return out


def ultima_medida(medidas: list[dict], datas: dict[str, str], antes_de: str, data_limite: str) -> dict | None:
    """A medida de outro exame (data ≤ a do atual) mais recente que tem posição."""
    cands = [m for m in medidas if m["study_uid"] != antes_de and m.get("centro")
             and (datas.get(m["study_uid"], "") or "") <= (data_limite or "99999999")]
    if not cands:
        return None
    return max(cands, key=lambda m: (datas.get(m["study_uid"], "") or "", m.get("id") or 0))


def candidatos(repo, lesoes: list[dict], anotacoes: list[dict], datas: dict[str, str], study_uid: str,
               centro_aqui, raio_mm: float = RAIO_PADRAO_MM) -> list[tuple[float, dict, dict]]:
    """[(distância mm, lesão, medida anterior)] das lesões cuja posição anterior, levada a este exame, fica a até
    `raio_mm` do centro da medida nova — da mais perto para a mais longe."""
    if centro_aqui is None:
        return []
    meds = medidas_das_lesoes(anotacoes)
    out = []
    for le in lesoes:
        m = ultima_medida(meds.get(le["id"], []), datas, study_uid, datas.get(study_uid, ""))
        if m is None:
            continue
        p = transformar(repo, m["centro"], m["study_uid"], study_uid)
        if p is None:
            continue
        d = float(np.linalg.norm(np.asarray(p) - np.asarray(centro_aqui, float)))
        if d <= raio_mm:
            out.append((d, le, m))
    return sorted(out, key=lambda x: x[0])


def escolher(cands: list[tuple[float, dict, dict]]) -> tuple[float, dict, dict] | None:
    """A ligação só é automática quando não há dúvida: um candidato, ou o mais perto bem mais perto (metade
    da distância do segundo)."""
    if not cands:
        return None
    if len(cands) == 1 or cands[0][0] <= 0.5 * cands[1][0]:
        return cands[0]
    return None


def pendentes(lesoes: list[dict], anotacoes: list[dict], datas: dict[str, str], study_uid: str) -> list[dict]:
    """Lesões medidas em exame anterior e ainda sem medida nem estado neste: o que o assistente percorre.
    Cada item: {lesao, medida (a anterior mais recente, com ou sem posição)}."""
    meds = medidas_das_lesoes(anotacoes)
    out = []
    for le in lesoes:
        ms = meds.get(le["id"], [])
        if any(m["study_uid"] == study_uid for m in ms):
            continue
        if ((le.get("data") or {}).get("status") or {}).get(study_uid):
            continue
        antes = [m for m in ms if (datas.get(m["study_uid"], "") or "") <= (datas.get(study_uid, "") or "99999999")]
        if not antes:
            continue
        ult = max(antes, key=lambda m: (datas.get(m["study_uid"], "") or "", m.get("id") or 0))
        out.append({"lesao": le, "medida": ult})
    return out
