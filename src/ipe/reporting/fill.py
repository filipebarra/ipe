"""Preenchimento automático dos campos do modelo de laudo a partir do banco (sem Qt)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime

from ipe.imaging import lesions as L
from ipe.imaging import measure as M
from ipe.reporting import birads as B

log = logging.getLogger(__name__)
_FIELD = re.compile(r"\{([a-z_]+)\}")
SKIP_KINDS = {"text", "arrow", "pencil", "calibration", "spine", "tic"}


def fmt_date(d: str) -> str:
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if d and len(d) >= 8 and d[:8].isdigit() else (d or "")


def age_text(info: dict) -> str:
    a = (info.get("patient_age") or "").strip()
    if a and a[:-1].isdigit():
        n, u = int(a[:-1]), a[-1].upper()
        return f"{n} " + {"Y": "anos", "M": "meses", "W": "semanas", "D": "dias"}.get(u, "")
    b, s = info.get("birth_date", ""), info.get("study_date", "")
    try:
        bd, sd = datetime.strptime(b[:8], "%Y%m%d"), datetime.strptime(s[:8], "%Y%m%d")
        years = sd.year - bd.year - ((sd.month, sd.day) < (bd.month, bd.day))
        return f"{years} anos"
    except ValueError:
        return ""


def fill(text: str, ctx: dict) -> str:
    """Troca {campo} pelo valor; campos vazios somem (com a linha, se ela ficar vazia)."""
    out_lines = []
    for line in (text or "").splitlines():
        had = bool(_FIELD.search(line))
        new = _FIELD.sub(lambda m: str(ctx[m.group(1)]) if m.group(1) in ctx else m.group(0), line)
        if had and not new.strip():
            continue
        out_lines.append(new)
    txt = "\n".join(out_lines)
    return re.sub(r"\n{3,}", "\n\n", txt).strip() + "\n"


def patient_key(info: dict) -> str:
    pid = (info or {}).get("patient_id", "")
    if pid:
        return pid
    name = (info or {}).get("patient_name", "")
    return f"nome:{name}|{(info or {}).get('birth_date', '')}" if name else ""


def comparison_text(repo, study_uid: str, info: dict) -> str:
    pid = info.get("patient_id", "")
    rows = [r for r in (repo.studies_of_patient(pid) if pid else []) if r.study_uid != study_uid
            and (r.study_date or "") <= (info.get("study_date") or "99999999")]
    if not rows:
        return "Não há exames anteriores disponíveis para comparação."
    rows.sort(key=lambda r: r.study_date or "", reverse=True)
    items = [f"{fmt_date(r.study_date)} ({r.modalities or '?'}{' — ' + r.description if r.description else ''})"
             for r in rows[:6]]
    return "Exames anteriores: " + "; ".join(items) + "."


def _spacings(repo, sops: list[str]) -> dict[str, tuple | None]:
    import pydicom
    from ipe.imaging.series import _spacing
    out: dict[str, tuple | None] = {}
    paths = repo.paths_for_sops(sops) if sops else {}
    for sop, path in paths.items():
        try:
            ds = pydicom.dcmread(path, stop_before_pixels=True, force=True)
            out[sop] = _spacing(ds)[0]
        except Exception:  # noqa: BLE001
            out[sop] = None
    return out


def measurements_text(repo, study_uid: str, limit: int = 60) -> str:
    rows = [r for r in repo.annotations_for_studies([study_uid])
            if r.get("kind") not in SKIP_KINDS and not M.e_rascunho(r)]
    if not rows:
        return ""
    anns = [M.Annotation.from_record(r) for r in rows[:limit]]
    spac = _spacings(repo, sorted({a.frame_key[0] for a in anns}))
    series = {s.series_uid: s for s in repo.series_for_study(study_uid)}
    paths = repo.paths_for_sops(sorted({a.frame_key[0] for a in anns if a.kind in M.ROI_KINDS}))
    lines = []
    for a in anns:
        sp = spac.get(a.frame_key[0])
        pix = None
        suv = None
        s = series.get(a.series_uid)
        mod = s.modality if s is not None else ""
        if a.kind in M.ROI_KINDS and a.frame_key[0] in paths:
            try:
                from ipe.imaging.series import Frame, read_frame
                img = read_frame(Frame(paths[a.frame_key[0]], a.frame_key[1], a.frame_key[0], 0))
                pix = None if img.is_color else img.pixels
                if mod == "PT":
                    from ipe.imaging.suv import suv_factor_for_file
                    suv = suv_factor_for_file(paths[a.frame_key[0]])[0]
            except Exception as e:  # noqa: BLE001
                log.debug("medida %s: %s", a.db_id, e)
        try:
            labs = M.labels(a, pix, sp, mod, suv)
        except Exception:  # noqa: BLE001
            labs = []
        if not labs:
            continue
        name = M.KINDS.get(a.kind, a.kind)
        lesion = (a.meta or {}).get("lesion_name")
        where = f" (série {s.series_number}{' — ' + s.description if s is not None and s.description else ''})" \
            if s is not None else ""
        lines.append(f"- {lesion + ': ' if lesion else ''}{name}: {'; '.join(labs[:3])}{where}")
    return ("Medidas:\n" + "\n".join(lines)) if lines else ""


def lesions_text(repo, study_uid: str, info: dict) -> str:
    pid = patient_key(info)
    if not pid:
        return ""
    lesions = repo.lesions(pid)
    if not lesions:
        return ""
    track = repo.lesion_track(pid)
    crit = track.get("criterion") or "recist"
    rows = repo.studies_of_patient(info.get("patient_id", "")) if info.get("patient_id") else []
    studies = {r.study_uid: r.study_date for r in rows}
    studies.setdefault(study_uid, info.get("study_date", ""))
    anns = [a for a in repo.annotations_for_studies(list(studies)) if not M.e_rascunho(a)]
    cells = L.collect_cells(lesions, anns, crit)
    used = {s for (_lid, s) in cells} | {study_uid}
    if track.get("baseline_study"):
        used.add(track["baseline_study"])
    st = [(u, d) for u, d in studies.items() if u in used and (d or "") <= (info.get("study_date") or "99999999")]
    evals = L.evaluate(crit, lesions, st, cells, track.get("baseline_study", ""))
    return L.summary_text(crit, lesions, st, cells, evals, study_uid)


def volumes_text(repo, study_uid: str) -> str:
    rows = [r for r in repo.annotations_for_studies([study_uid]) if r.get("kind") == "seg" and not M.e_rascunho(r)]
    if not rows:
        return ""
    metas = []
    lines = []
    for r in rows:
        try:
            d = json.loads(r.get("data") or "{}")
        except ValueError:
            continue
        m = d.get("meta") or {}
        metas.append(m)
        name = m.get("lesion_name") or d.get("text") or "Segmentação"
        s = f"- {name}: {float(m.get('ml') or 0):.2f} mL"
        if m.get("suvmax") is not None:
            s += (f", SUVmáx {m['suvmax']:.2f}, SUVmédio {float(m.get('suvmean') or 0):.2f}"
                  f", SUVpeak {float(m.get('suvpeak') or 0):.2f}, TLG {float(m.get('tlg') or 0):.1f}")
        elif m.get("mean") is not None:
            s += f", média {m['mean']:.1f}"
        if m.get("max_diam_mm"):
            s += f", maior eixo {m['max_diam_mm']:.1f} mm"
        lines.append(s)
    from ipe.imaging.segment import tmtv
    ml, tlg = tmtv(metas)
    out = "Segmentações volumétricas:\n" + "\n".join(lines)
    if ml:
        out += f"\nVolume tumoral metabólico total (TMTV): {ml:.1f} mL; glicólise total (TLG): {tlg:.1f}."
    return out


def curves_text(repo, study_uid: str) -> str:
    rows = [r for r in repo.annotations_for_studies([study_uid]) if r.get("kind") == "tic" and not M.e_rascunho(r)]
    out = []
    for r in rows:
        try:
            t = json.loads(r.get("data") or "{}").get("text", "")
        except ValueError:
            t = ""
        if t:
            out.append(f"- {t}")
    return ("Curvas tempo-intensidade:\n" + "\n".join(out)) if out else ""


def build_context(repo, study_uid: str, fields: dict | None = None, anonymize: bool = False) -> dict:
    info = repo.study_info(study_uid) or {}
    fields = fields or {}
    sex = {"M": "Masculino", "F": "Feminino", "O": "Outro"}.get((info.get("sex") or "").upper(), "")
    ctx = {
        "paciente": "" if anonymize else info.get("patient_name", "").replace("^", " ").strip(),
        "idade": age_text(info),
        "sexo": sex,
        "data_exame": fmt_date(info.get("study_date", "")),
        "exame": info.get("description", "") or info.get("modalities", ""),
        "solicitante": (info.get("referring") or "").replace("^", " ").strip(),
        "comparacao": comparison_text(repo, study_uid, info),
        "imagens_chave": str(len(repo.key_images(study_uid))),
    }
    for key, fn in (("medidas", lambda: measurements_text(repo, study_uid)),
                    ("lesoes", lambda: lesions_text(repo, study_uid, info)),
                    ("volumes", lambda: volumes_text(repo, study_uid)),
                    ("curva", lambda: curves_text(repo, study_uid))):
        try:
            ctx[key] = fn()
        except Exception as e:  # noqa: BLE001
            log.warning("campo %s: %s", key, e)
            ctx[key] = ""
    if fields.get("kind"):
        ctx["composicao"] = B.composition_text(fields)
        ctx["achados_birads"] = B.findings_text(fields)
        ctx["birads"] = B.category_text(fields)
        ctx["conduta"] = B.recommendation(fields)
        ctx["bpe_texto"] = B.bpe_text(fields)
    else:
        for k in ("composicao", "achados_birads", "birads", "conduta", "bpe_texto"):
            ctx[k] = ""
    return ctx
