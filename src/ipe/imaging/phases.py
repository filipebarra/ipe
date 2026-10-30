"""Fases de uma série dinâmica guardadas em séries separadas (uma série por fase).

Duas séries são "fases compatíveis" quando têm o mesmo número de cortes, a mesma
orientação e os cortes nas mesmas posições. A ordem das fases segue o horário
de aquisição (AcquisitionTime) e, na falta dele, o número da série.
"""

from __future__ import annotations

import re

import numpy as np

from ipe.imaging.series import Frame

SKIP_WORDS = re.compile(r"\b(SUB|SUBTR|MIP|MPR|3D|RECON|DIFF|DWI|ADC|T2|STIR|LOC|SURVEY|SCOUT)\b", re.I)

# O nome da série não basta: a GE grava a subtração com o nome da conta que a produziu
# ("(43798/301/60)-(43798/300/60)"), e a estação AW devolve cópias alinhadas com nome qualquer.
# Quem diz o que a série é, é o arquivo — ImageType (0008,0008). Subtração e projeção entrando
# como fase envenenam tudo em silêncio: o pico passa a ser calculado sobre a subtração, e duas
# séries com o mesmo horário fazem o conjunto perder os horários e virar "1 min por fase".
FORA_POR_TIPO = (
    ("SECONDARY", "série derivada da estação"),
    ("SUBTRACT", "subtração"),
    ("MIP", "projeção (MIP)"),
    ("PJN", "projeção (MIP)"),
    ("ADC", "mapa de difusão"),
    ("TRACEW", "difusão"),
)
# Dixon (VIBRANT FLEX, IDEAL): água e gordura são dinâmicas **separadas**, apesar de terem a
# mesma geometria. Juntá-las dobrava as fases e misturava dois exames num só.
DIXON = ("WATER", "FAT", "IN_PHASE", "OPP_PHASE")


def image_type(caminho: str) -> list[str]:
    """ImageType do arquivo, em maiúsculas. Lista vazia quando não dá para ler."""
    try:
        import pydicom
        ds = pydicom.dcmread(caminho, stop_before_pixels=True, specific_tags=["ImageType"])
        return [str(x).upper().strip() for x in (getattr(ds, "ImageType", None) or [])]
    except Exception:  # noqa: BLE001 - arquivo ilegível não pode derrubar a detecção
        return []


def fora_das_fases(tipos: list[str]) -> str:
    """Por que esta série não serve de fase — "" quando serve."""
    marcas = set(tipos)
    for marca, motivo in FORA_POR_TIPO:
        if marca in marcas:
            return motivo
    return ""


def componente(tipos: list[str]) -> str:
    """Água, gordura, em fase… nas sequências Dixon; "" nas demais."""
    for x in tipos:
        if x in DIXON:
            return x
    return ""


def seconds(t: str) -> float | None:
    t = (t or "").replace(":", "").strip()
    if len(t) < 4:
        return None
    try:
        return int(t[0:2]) * 3600 + int(t[2:4]) * 60 + (float(t[4:]) if len(t) > 4 else 0.0)
    except ValueError:
        return None


def phase_time(frames: list[Frame]) -> float | None:
    ts = [s for s in (seconds(f.acquisition_time) for f in frames) if s is not None]
    return min(ts) if ts else None


def compatible(a: list[Frame], b: list[Frame], tol_mm: float = 1.0) -> tuple[bool, str]:
    if not a or not b:
        return False, "série vazia"
    if len(a) != len(b):
        return False, f"número de imagens diferente ({len(a)} × {len(b)})"
    fa, fb = a[0], b[0]
    if fa.orientation is None or fb.orientation is None:
        return False, "sem informação de orientação"
    if not np.allclose(fa.orientation, fb.orientation, atol=1e-2):
        return False, "orientação diferente"
    for x, y in zip(a, b):
        if x.position is None or y.position is None:
            return False, "sem posição dos cortes"
        if float(np.linalg.norm(np.asarray(x.position) - np.asarray(y.position))) > tol_mm:
            return False, "cortes em posições diferentes"
    return True, ""


def order(items: list[tuple[str, list[Frame], int]]) -> list[tuple[str, list[Frame], int]]:
    """Ordena (uid, quadros, número da série) pelo horário; sem horário, pelo número."""
    def key(it):
        t = phase_time(it[1])
        return (0 if t is not None else 1, t if t is not None else 0.0, it[2])
    return sorted(items, key=key)


def map_index(src: list[Frame], idx: int, dst: list[Frame]) -> int:
    """Índice em `dst` do corte mais próximo do corte `idx` de `src`."""
    if not dst:
        return 0
    if len(src) == len(dst) or src[idx].position is None:
        return min(idx, len(dst) - 1)
    p = np.asarray(src[idx].position)
    d = [float(np.linalg.norm(np.asarray(f.position) - p)) if f.position is not None else 1e9 for f in dst]
    return int(np.argmin(d))


def detect(candidates: list[tuple[str, list[Frame], int, str, str]]) -> list[list[str]]:
    """Grupos prováveis de fases: (uid, quadros, número, modalidade, descrição) -> [[uids em ordem]].

    Junta séries de RM compatíveis entre si (3 ou mais). Séries de subtração, MIP,
    difusão etc. ficam de fora pelo nome."""
    pool = []
    for c in candidates:
        if c[3] != "MR" or len(c[1]) < 2:
            continue
        tipos = image_type(c[1][0].path) if c[1][0].path else []
        if tipos:
            if fora_das_fases(tipos):
                continue
        elif SKIP_WORDS.search(c[4] or ""):   # sem ImageType legível, resta o nome
            continue
        pool.append((c, componente(tipos)))
    groups: list[list[tuple]] = []
    comps: list[str] = []
    for c, comp in pool:
        for g, gc in zip(groups, comps):
            if gc == comp and compatible(g[0][1], c[1])[0]:
                g.append(c)
                break
        else:
            groups.append([c])
            comps.append(comp)
    out = []
    for g in groups:
        if len(g) >= 3:
            out.append([uid for uid, _f, _n in order([(c[0], c[1], c[2]) for c in g])])
    return out
