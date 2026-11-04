"""Clonar uma ROI para outro quadro pela posição no paciente (0.99.45, plano AW item 15).

A AW leva a ROI de uma série para outra (T2 → ADC, pré → pós, exame atual → anterior) e recalcula a
estatística na imagem de destino. Aqui é o mesmo, com três regras:

- **mesmo lugar no paciente**, não o mesmo pixel: cada ponto vai para coordenadas do paciente (mm) e
  volta em pixels do quadro de destino — séries com matriz, FOV ou espaçamento diferentes recebem a
  ROI no tamanho certo;
- **referencial**: mesmo Frame of Reference vale direto; quadros ligados num grupo de sincronia
  usam o deslocamento do grupo (o mesmo que faz os cortes andarem juntos); sem nenhum dos dois, a
  cópia é recusada com o motivo — não há como saber onde o ponto está no outro exame;
- **plano paralelo e corte dentro da cobertura**: o destino vai ao corte mais perto do centro da
  ROI; se não houver corte a menos de meio intervalo + 2 mm, não copia.

A cópia é uma ROI comum do destino (meta `clonada_de`), gravada no banco como as outras.

Sem Qt: recebe os quadros por "duck typing" (plane, pixel_to_patient, patient_to_pixel,
go_to_point, frame_key…).
"""
from __future__ import annotations

import numpy as np

from ipe.imaging import measure as M


def _normal(v):
    pl = v.plane()
    return None if pl is None else np.asarray(pl[3], float)


def _intervalo(v) -> float:
    fr = v.frames
    if len(fr) > 1 and fr[0].position is not None and fr[1].position is not None and fr[0].normal is not None:
        return abs(float((np.asarray(fr[1].position) - np.asarray(fr[0].position)) @ np.asarray(fr[0].normal)))
    return 0.0


def deslocamento(src, dst, hub=None):
    """Vetor (mm) a somar ao ponto de `src` para cair em `dst`, ou None quando não há referencial comum."""
    if hub is not None and hub.group_of(src) is not None and hub.group_of(src) == hub.group_of(dst):
        ms, md = hub.members.get(src), hub.members.get(dst)
        if ms is not None and md is not None and ms.geo is not None and md.geo is not None:
            return np.asarray(md.geo, float) - np.asarray(ms.geo, float)
    if src.for_uid and src.for_uid == dst.for_uid:
        return np.zeros(3)
    return None


def clonar(src, ann, dst, hub=None) -> str:
    """Cria a cópia em `dst`. Devolve "" quando deu, ou o motivo de não ter dado."""
    if ann.kind not in M.ROI_KINDS:
        return "só ROIs (elipse, retângulo, polígono, curva) se clonam"
    if ann.frame_key != src.frame_key():
        return "a ROI não está no corte à vista"
    if dst.plane() is None or src.plane() is None:
        return "sem geometria (posição do corte) no arquivo"
    na, nb = _normal(src), _normal(dst)
    if float(np.linalg.norm(np.cross(na, nb))) > 0.1:
        return "plano diferente (só entre cortes paralelos)"
    off = deslocamento(src, dst, hub)
    if off is None:
        return "outro referencial: ligue os quadros (Sincronizar) ou registre os exames"
    pts = [src.pixel_to_patient(float(x), float(y)) for x, y in ann.points]
    if any(p is None for p in pts):
        return "sem geometria no quadro de origem"
    pts = [np.asarray(p, float) + off for p in pts]
    centro = np.mean(pts, axis=0)
    tol = _intervalo(dst) / 2 + 2.0
    if not dst.go_to_point(centro, tolerance_mm=tol):
        return "fora dos cortes desta série"
    novo = []
    for p in pts:
        uvd = dst.patient_to_pixel(p)
        if uvd is None:
            return "sem geometria no quadro de destino"
        novo.append((uvd[0], uvd[1]))
    img = getattr(dst, "_img", None)
    if img is not None:
        h, w = img.pixels.shape[:2]
        cx, cy = np.mean([q[0] for q in novo]), np.mean([q[1] for q in novo])
        if not (0 <= cx < w and 0 <= cy < h):
            return "a posição cai fora da imagem"
    f = dst.current_frame()
    cp = M.Annotation(ann.kind, dst.frame_key(), novo, text=ann.text, study_uid=dst.study_uid,
                      series_uid=(f.series_uid if f is not None and getattr(f, "series_uid", "") else dst.series_uid),
                      meta={"clonada_de": src.series_label or ""})
    dst.annotations.append(cp)
    dst._store("save", cp)
    dst.update()
    return ""
