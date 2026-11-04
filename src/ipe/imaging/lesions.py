"""Acompanhamento de lesões ao longo dos exames (sem Qt).

Cada lesão tem nome, local, tipo (alvo, não alvo, nova) e se é linfonodo. As medidas desenhadas
no visualizador são ligadas a uma lesão (o id vai no JSON da anotação, em "meta") junto com o
valor já calculado (mm, SUV…). Aqui juntamos tudo numa tabela lesão × exame e calculamos a
resposta pelo critério escolhido:

- Livre: só a tabela e a variação percentual.
- RECIST 1.1: soma dos maiores diâmetros (menor eixo nos linfonodos); RP ≤ −30% da base;
  DP ≥ +20% do nadir e ≥ 5 mm, ou lesão nova, ou progressão inequívoca de não alvo.
- mRECIST (carcinoma hepatocelular): mesma conta, medindo só a parte viável (realce arterial).
- PERCIST 1.0 (PET): SUVpeak da lesão mais ávida; RMP ≤ −30% e ≥ 0,8; DMP ≥ +30% e ≥ 0,8
  ou lesão nova.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import numpy as np

CRITERIA = {
    "free": "Livre (só a tabela)",
    "recist": "RECIST 1.1",
    "mrecist": "mRECIST (fígado)",
    "percist": "PERCIST 1.0 (PET)",
}
KINDS = {"target": "Alvo", "nontarget": "Não alvo", "new": "Nova"}
STATUS = {"": "—", "present": "Presente", "absent": "Desapareceu", "progression": "Progressão inequívoca",
          "nm": "Não mensurável"}
RESPONSES = {
    "RC": "Resposta completa", "RP": "Resposta parcial", "DE": "Doença estável", "DP": "Doença progressiva",
    "NRC": "Não RC / não DP",
    "RMC": "Resposta metabólica completa", "RMP": "Resposta metabólica parcial",
    "DME": "Doença metabólica estável", "DMP": "Doença metabólica progressiva",
    "BASE": "Exame de base", "NA": "Não avaliável",
}
RESPONSE_COLORS = {"RC": "#3fb950", "RMC": "#3fb950", "RP": "#7ee787", "RMP": "#7ee787",
                   "DE": "#e3b341", "DME": "#e3b341", "NRC": "#e3b341",
                   "DP": "#f85149", "DMP": "#f85149", "BASE": "#8fb3ff", "NA": "#8b949e"}
MAX_TARGETS = 5
MAX_PER_ORGAN = 2


# ------------------------------------------------------------------ valores das medidas
def feret_mm(points: list, spacing) -> float:
    """Maior distância entre dois pontos do contorno (diâmetro máximo), em mm."""
    if len(points) < 2:
        return 0.0
    rs, cs = spacing or (1.0, 1.0)
    pts = np.array(points, dtype=float)
    if len(pts) > 200:
        pts = pts[:: int(math.ceil(len(pts) / 200))]
    xy = np.stack([pts[:, 0] * cs, pts[:, 1] * rs], axis=1)
    d = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(-1))
    return float(d.max())


def peak_mean(pixels: np.ndarray, center: tuple[int, int], radius_px: tuple[float, float]) -> float | None:
    """Média num círculo (raio em pixels, por linha/coluna) em volta do centro (linha, coluna)."""
    h, w = pixels.shape[:2]
    r, c = center
    ry, rx = max(radius_px[0], 0.5), max(radius_px[1], 0.5)
    y0, y1 = max(0, int(r - ry - 1)), min(h, int(r + ry + 2))
    x0, x1 = max(0, int(c - rx - 1)), min(w, int(c + rx + 2))
    yy, xx = np.mgrid[y0:y1, x0:x1]
    m = ((yy - r) / ry) ** 2 + ((xx - c) / rx) ** 2 <= 1.0
    vals = pixels[y0:y1, x0:x1][m]
    return float(vals.mean()) if vals.size else None


def measure_values(kind: str, points: list, pixels: np.ndarray | None, spacing,
                   suv: float | None = None) -> dict:
    """Valores guardados na medida ligada à lesão: mm (diâmetro), SUV (máx/pico/médio), média, área."""
    from ipe.imaging import measure as M
    out: dict = {}
    if kind in ("line",) and len(points) >= 2:
        out["mm"] = round(M.length_mm(points[0], points[1], spacing), 2)
    elif kind in ("ellipse", "rect", "tic") and len(points) >= 2:
        rs, cs = spacing or (1.0, 1.0)
        (x1, y1), (x2, y2) = points[:2]
        out["mm"] = round(max(abs(x2 - x1) * cs, abs(y2 - y1) * rs), 2)
    elif kind == "polygon" and len(points) >= 3:
        out["mm"] = round(feret_mm(points, spacing), 2)
    if kind in M.ROI_KINDS and pixels is not None and pixels.ndim == 2:
        st = M.roi_stats(pixels, kind, points, spacing)
        if st.mean is not None:
            out["mean"] = round(st.mean, 3)
            out["max"] = round(st.maximum, 3)
            if st.area_mm2 is not None:
                out["area_mm2"] = round(st.area_mm2, 2)
            if suv:
                out["suvmax"] = round(st.maximum * suv, 3)
                out["suvmean"] = round(st.mean * suv, 3)
                res = M.roi_mask(kind, points, pixels.shape)
                if res is not None:
                    from ipe.imaging.segment import box_mean_max
                    sl, mask = res
                    full = np.zeros(pixels.shape, bool)
                    full[sl] = mask
                    rs, cs = spacing or (1.0, 1.0)
                    pk = box_mean_max(pixels, full, (max(1, round(10 / rs)), max(1, round(10 / cs))))
                    if pk is not None:           # quadrado de 1 cm (aprox. 2D do SUVpeak)
                        out["suvpeak"] = round(pk * suv, 3)
    return out


# ------------------------------------------------------------------ tabela
@dataclass
class Cell:
    value: float | None = None       # valor usado pelo critério
    long_mm: float | None = None
    short_mm: float | None = None
    suvmax: float | None = None
    suvpeak: float | None = None
    ml: float | None = None
    status: str = ""                 # present, absent, progression, nm
    refs: list = field(default_factory=list)   # (series_uid, sop_uid, frame_index, annotation_id)

    def text(self, criterion: str) -> str:
        if self.status == "absent":
            return "0 (desapareceu)"
        if self.status == "progression":
            return "progressão"
        if self.status == "nm" and self.value is None:
            return "não mensurável"
        if self.value is None:
            return "presente" if self.status == "present" else ""
        if criterion == "percist":
            return f"SUVpk {self.value:.2f}"
        if criterion == "free" and self.long_mm is None and self.suvmax is not None:
            return f"SUVmáx {self.suvmax:.2f}"
        if criterion == "free" and self.long_mm is None and self.ml is not None:
            return f"{self.ml:.1f} mL"
        s = f"{self.value:.1f} mm"
        if self.long_mm is not None and self.short_mm is not None and self.short_mm != self.long_mm:
            s = f"{self.long_mm:.1f} × {self.short_mm:.1f} mm"
        return s


def collect_cells(lesions: list[dict], annotations: list[dict], criterion: str) -> dict:
    """(lesão, estudo) -> Cell, a partir das medidas ligadas e do estado marcado à mão."""
    by_id = {le["id"]: le for le in lesions}
    cells: dict[tuple[int, str], Cell] = {}
    for a in annotations:
        try:
            d = json.loads(a.get("data") or "{}")
        except ValueError:
            continue
        meta = d.get("meta") or {}
        lid = meta.get("lesion")
        if lid not in by_id:
            continue
        c = cells.setdefault((lid, a["study_uid"]), Cell())
        c.refs.append((a.get("series_uid", ""), a.get("sop_uid", ""), int(a.get("frame_index") or 0), a.get("id")))
        mm = meta.get("mm")
        if mm is not None:
            c.long_mm = mm if c.long_mm is None else max(c.long_mm, mm)
            c.short_mm = mm if c.short_mm is None else min(c.short_mm, mm)
        for k in ("suvmax", "suvpeak", "ml"):
            v = meta.get(k)
            if v is not None:
                cur = getattr(c, k)
                setattr(c, k, v if cur is None else max(cur, v))
    for le in lesions:
        for study, st in ((le.get("data") or {}).get("status") or {}).items():
            if st:
                cells.setdefault((le["id"], study), Cell()).status = st
    for (lid, _study), c in cells.items():
        le = by_id[lid]
        if c.status == "absent":
            c.value = 0.0
            continue
        if criterion == "percist":
            c.value = c.suvpeak if c.suvpeak is not None else c.suvmax
        elif c.long_mm is not None:
            nlines = len(c.refs)
            if le.get("nodal"):
                c.value = c.short_mm if nlines >= 2 else c.long_mm
            else:
                c.value = c.long_mm
        elif criterion == "free":
            c.value = c.suvmax if c.suvmax is not None else c.ml
        if c.status == "" and (c.value is not None or c.refs):
            c.status = "present"
    return cells


# ------------------------------------------------------------------ tempo de duplicação (0.99.45)
def _dias(a: str, b: str) -> int | None:
    from datetime import date
    try:
        da = date(int(a[:4]), int(a[4:6]), int(a[6:8]))
        db = date(int(b[:4]), int(b[4:6]), int(b[6:8]))
    except (TypeError, ValueError, IndexError):
        return None
    return (db - da).days


def tempo_de_duplicacao(v1: float, v2: float, dias: float, por_diametro: bool = False) -> float | None:
    """Dias para o volume dobrar, supondo crescimento exponencial: TD = t·ln2 / ln(V2/V1).

    Com diâmetros (`por_diametro`), supõe esfera (V ∝ d³): TD = t·ln2 / (3·ln(d2/d1)).
    Sem crescimento (V2 ≤ V1), sem intervalo ou valor ≤ 0 devolve None — "não se aplica", nunca
    um número enorme ou negativo (a AW usa N/A nos mesmos casos)."""
    if v1 is None or v2 is None or dias is None or dias <= 0 or v1 <= 0 or v2 <= v1:
        return None
    r = math.log(v2 / v1)
    if por_diametro:
        r *= 3.0
    return dias * math.log(2.0) / r if r > 0 else None


def duplicacoes(lesions: list[dict], studies: list[tuple[str, str]], cells: dict) -> dict:
    """(lesão, exame) -> (dias ou None, texto curto, explicação), contra o exame anterior com medida
    da mesma lesão. Usa o volume (mL) quando os dois exames têm; senão, o maior diâmetro."""
    out: dict = {}
    ordem = sorted(studies, key=lambda s: (s[1] or "", s[0]))
    for le in lesions:
        anterior = None
        for uid, data in ordem:
            c = cells.get((le["id"], uid))
            if c is None:
                continue
            if c.status == "absent":
                anterior = None                     # sumiu: o crescimento recomeça do zero
                continue
            if c.ml is None and c.long_mm is None:
                continue
            if anterior is not None:
                (u0, d0, c0) = anterior
                dias = _dias(d0, data)
                if c.ml is not None and c0.ml is not None:
                    td, base = tempo_de_duplicacao(c0.ml, c.ml, dias), "volume"
                    v0, v1 = f"{c0.ml:.2f} mL", f"{c.ml:.2f} mL"
                else:
                    a0 = c0.long_mm if c0.long_mm is not None else None
                    a1 = c.long_mm if c.long_mm is not None else None
                    td = tempo_de_duplicacao(a0, a1, dias, por_diametro=True) if a0 and a1 else None
                    base = "diâmetro (supondo esfera)"
                    v0 = f"{a0:.1f} mm" if a0 else "?"
                    v1 = f"{a1:.1f} mm" if a1 else "?"
                if dias is None or dias <= 0:
                    expl = "Tempo de duplicação: sem intervalo entre as datas."
                    curto = ""
                elif td is None:
                    curto = "TD não se aplica"
                    expl = (f"Tempo de duplicação não se aplica: não cresceu ({v0} → {v1} em {dias} dias, "
                            f"pelo {base}).")
                else:
                    curto = f"TD {td:.0f} d"
                    expl = (f"Tempo de duplicação {td:.0f} dias: {v0} → {v1} em {dias} dias, pelo {base}. "
                            "Supõe crescimento exponencial; medidas de diâmetro com 1 mm de erro mudam muito "
                            "o resultado em lesões pequenas.")
                out[(le["id"], uid)] = (td, curto, expl)
            anterior = (uid, data, c)
    return out


@dataclass
class StudyEval:
    study_uid: str
    date: str
    total: float | None = None           # soma (RECIST) ou pico (PERCIST)
    pct_base: float | None = None
    pct_nadir: float | None = None
    pct_prev: float | None = None
    response: str = ""                   # código (RC, RP…); vazio antes da base
    notes: list[str] = field(default_factory=list)

    @property
    def response_text(self) -> str:
        return RESPONSES.get(self.response, self.response)


def _pct(cur: float | None, ref: float | None) -> float | None:
    if cur is None or ref is None or ref == 0:
        return None
    return (cur - ref) / ref * 100.0


def evaluate(criterion: str, lesions: list[dict], studies: list[tuple[str, str]], cells: dict,
             baseline: str = "") -> list[StudyEval]:
    """Resposta por exame. `studies`: (study_uid, data AAAAMMDD), em qualquer ordem."""
    studies = sorted(studies, key=lambda s: (s[1] or "", s[0]))
    targets = [le for le in lesions if le.get("kind", "target") == "target"]
    nontargets = [le for le in lesions if le.get("kind") == "nontarget"]
    news = [le for le in lesions if le.get("kind") == "new"]
    measured = [s for s, _d in studies if any((le["id"], s) in cells for le in lesions)]
    if not baseline or baseline not in [s for s, _ in studies]:
        baseline = measured[0] if measured else (studies[0][0] if studies else "")
    out: list[StudyEval] = []
    started = False
    history: list[float] = []
    prev_total: float | None = None
    base_total: float | None = None
    for uid, date in studies:
        ev = StudyEval(uid, date)
        out.append(ev)
        if uid == baseline:
            started = True
        if not started:
            continue
        vals, missing = [], []
        for le in targets:
            c = cells.get((le["id"], uid))
            if c is None or c.value is None:
                missing.append(le.get("name") or f"#{le['id']}")
            else:
                vals.append((le, c.value))
        if criterion == "percist":
            ev.total = max((v for _le, v in vals), default=None)
        else:
            ev.total = sum(v for _le, v in vals) if vals else None
        if missing and uid != baseline:
            ev.notes.append("sem medida: " + ", ".join(missing))
        if missing and uid == baseline and targets:
            ev.notes.append("base incompleta: " + ", ".join(missing))
        new_here = [le for le in news
                    if (c := cells.get((le["id"], uid))) is not None and c.status in ("present", "nm", "progression")]
        prog_nt = [le for le in nontargets
                   if (c := cells.get((le["id"], uid))) is not None and c.status == "progression"]
        if uid == baseline:
            ev.response = "BASE"
            base_total = ev.total
            if ev.total is not None:
                history.append(ev.total)
            prev_total = ev.total
            if criterion == "recist" or criterion == "mrecist":
                n_by_org: dict[str, int] = {}
                for le in targets:
                    n_by_org[le.get("location", "")] = n_by_org.get(le.get("location", ""), 0) + 1
                if len(targets) > MAX_TARGETS:
                    ev.notes.append(f"mais de {MAX_TARGETS} lesões-alvo")
                if any(n > MAX_PER_ORGAN for org, n in n_by_org.items() if org):
                    ev.notes.append(f"mais de {MAX_PER_ORGAN} alvos no mesmo órgão")
            continue
        ev.pct_base = _pct(ev.total, base_total)
        nadir = min(history) if history else None
        ev.pct_nadir = _pct(ev.total, nadir)
        ev.pct_prev = _pct(ev.total, prev_total)
        if criterion == "free":
            ev.response = ""
        elif criterion == "percist":
            ev.response = _percist(ev, base_total, targets, cells, uid, bool(new_here))
        else:
            ev.response = _recist(ev, base_total, nadir, targets, nontargets, cells, uid,
                                  bool(new_here), bool(prog_nt), bool(missing))
        if new_here:
            ev.notes.append("lesão nova: " + ", ".join(le.get("name", "") for le in new_here))
        if prog_nt:
            ev.notes.append("progressão de não alvo: " + ", ".join(le.get("name", "") for le in prog_nt))
        if ev.total is not None:
            history.append(ev.total)
            prev_total = ev.total
    return out


def _recist(ev: StudyEval, base, nadir, targets, nontargets, cells, uid, new: bool, prog_nt: bool,
            missing: bool) -> str:
    if new or prog_nt:
        return "DP"
    if ev.total is None or base is None:
        return "NA"
    if nadir is not None and ev.total - nadir >= 5.0 and (ev.pct_nadir or 0) >= 20.0:
        return "DP"
    if missing:
        return "NA"
    cr_targets = all(
        (c := cells.get((le["id"], uid))) is not None and
        (c.status == "absent" or (le.get("nodal") and c.value is not None and c.value < 10.0))
        for le in targets) if targets else True
    if cr_targets:
        nt_gone = all((c := cells.get((le["id"], uid))) is not None and c.status == "absent" for le in nontargets)
        return "RC" if nt_gone else "RP" if targets else "NRC"
    if ev.pct_base is not None and ev.pct_base <= -30.0:
        return "RP"
    return "DE"


def _percist(ev: StudyEval, base, targets, cells, uid, new: bool) -> str:
    if new:
        return "DMP"
    if targets and all((c := cells.get((le["id"], uid))) is not None and c.status == "absent" for le in targets):
        return "RMC"
    if ev.total is None or base is None:
        return "NA"
    diff = ev.total - base
    if ev.pct_base is not None and ev.pct_base <= -30.0 and diff <= -0.8:
        return "RMP"
    if ev.pct_base is not None and ev.pct_base >= 30.0 and diff >= 0.8:
        return "DMP"
    return "DME"


def summary_text(criterion: str, lesions: list[dict], studies: list[tuple[str, str]], cells: dict,
                 evals: list[StudyEval], study_uid: str | None = None) -> str:
    """Texto para o laudo: tabela das lesões e a resposta do exame (o último, se não disser qual)."""
    if not lesions:
        return ""
    studies = sorted(studies, key=lambda s: (s[1] or "", s[0]))
    by_uid = {e.study_uid: e for e in evals}
    target_uid = study_uid or (studies[-1][0] if studies else "")
    ev = by_uid.get(target_uid)
    base = next((e for e in evals if e.response == "BASE"), None)
    lines = [f"Acompanhamento de lesões — critério {CRITERIA.get(criterion, criterion)}"]
    if base is not None:
        lines.append(f"Exame de base: {_fmt_date(base.date)}")
    for le in lesions:
        c = cells.get((le["id"], target_uid))
        cb = cells.get((le["id"], base.study_uid)) if base is not None else None
        parts = [f"- {le.get('name') or 'Lesão'}"]
        if le.get("location"):
            parts.append(f"({le['location']})")
        parts.append(f"[{KINDS.get(le.get('kind', 'target'), '')}{', linfonodo' if le.get('nodal') else ''}]")
        cur = c.text(criterion) if c else "sem medida"
        txt = " ".join(parts) + f": {cur}"
        if cb is not None and base is not None and base.study_uid != target_uid:
            txt += f" (base: {cb.text(criterion) or '—'})"
        lines.append(txt)
    if ev is not None and ev.total is not None and criterion != "free":
        lab = "SUVpeak máximo" if criterion == "percist" else "Soma dos diâmetros"
        unit = "" if criterion == "percist" else " mm"
        lines.append(f"{lab}: {ev.total:.1f}{unit}" + (f" ({ev.pct_base:+.0f}% da base)" if ev.pct_base is not None else "")
                     + (f", {ev.pct_nadir:+.0f}% do nadir" if ev.pct_nadir is not None and criterion != "percist" else ""))
    if ev is not None and ev.response and ev.response != "BASE":
        lines.append(f"Resposta ({CRITERIA.get(criterion, criterion)}): {ev.response_text}")
    if ev is not None and ev.notes:
        lines.append("Obs.: " + "; ".join(ev.notes))
    return "\n".join(lines)


def _fmt_date(d: str) -> str:
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if d and len(d) >= 8 else (d or "")
