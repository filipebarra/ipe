"""Exportar exames/séries/imagens.

- DICOM: cópias (opcionalmente anonimizadas) numa pasta, com DICOMDIR (padrão de CD/pendrive) e um
  visualizador HTML simples que abre em qualquer navegador; opcionalmente compactado em ZIP.
- Imagens: JPG ou PNG, com a janela do arquivo ou a janela escolhida.
Tudo roda sem interface (dá para chamar numa thread); `progress(feito, total, texto)` e `cancel()`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pydicom

from ipe.exporter.anonymize import AnonOptions, anonymize
from ipe.imaging.series import build_frames, read_frame
from ipe.imaging.windowing import auto_window, to_display

log = logging.getLogger(__name__)


class ExportError(Exception):
    pass


class Cancelled(ExportError):
    pass


@dataclass
class ExportItem:
    """O que exportar: o exame inteiro, só algumas séries, ou quadros escolhidos
    (`frames` = [(sop_uid, frame_index)], ex.: imagens-chave ou a imagem atual)."""
    study_uid: str
    series_uids: list[str] | None = None
    frames: list[tuple[str, int]] | None = None


@dataclass
class ExportResult:
    dest: Path
    files: int = 0
    images: int = 0
    studies: int = 0
    dicomdir: bool = False
    viewer: Path | None = None
    zip_path: Path | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Entry:
    n: int                 # número do exame na exportação (1, 2, …)
    study_uid: str
    info: dict
    series: list[dict]     # {series_uid, number, modality, description, frames: [Frame]}


def _safe(text: str, limit: int = 40) -> str:
    out = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in (text or "")).strip()
    return (out or "x")[:limit].strip()


def _collect(repo, items: list[ExportItem]) -> list[_Entry]:
    entries: list[_Entry] = []
    by_study: dict[str, _Entry] = {}
    for it in items:
        info = repo.study_info(it.study_uid)
        if info is None:
            continue
        e = by_study.get(it.study_uid)
        if e is None:
            e = _Entry(len(entries) + 1, it.study_uid, info, [])
            by_study[it.study_uid] = e
            entries.append(e)
        wanted = set(it.series_uids or [])
        keys = set(tuple(k) for k in (it.frames or []))
        for sr in repo.series_for_study(it.study_uid):
            if wanted and sr.series_uid not in wanted:
                continue
            frames = build_frames(repo.instances_for_series(sr.series_uid), sr.series_uid)
            if keys:
                frames = [f for f in frames if (f.sop_uid, f.frame_index) in keys]
            if not frames:
                continue
            existing = next((s for s in e.series if s["series_uid"] == sr.series_uid), None)
            if existing is not None:
                have = {(f.sop_uid, f.frame_index) for f in existing["frames"]}
                existing["frames"] += [f for f in frames if (f.sop_uid, f.frame_index) not in have]
                continue
            e.series.append({"series_uid": sr.series_uid, "number": sr.series_number, "modality": sr.modality,
                             "description": sr.description, "frames": frames})
    return [e for e in entries if e.series]


def _progress(progress, done, total, text=""):
    if progress is not None:
        progress(done, total, text)


def _check(cancel):
    if cancel is not None and cancel():
        raise Cancelled("Exportação cancelada.")


# ------------------------------------------------------------------ imagens
def render_frame(frame, window: tuple[float, float] | None = None, invert: bool = False,
                 max_size: int | None = None, cmap: str | None = None,
                 image_filter: str = "") -> np.ndarray:
    """Pixels 8 bits prontos para gravar (cinza HxW ou RGB HxWx3)."""
    img = read_frame(frame)
    if image_filter:
        from dataclasses import replace
        from ipe.imaging import filters
        img = replace(img, pixels=filters.apply(img.pixels, image_filter))
    if img.is_color:
        disp = to_display(img, 0, 0, invert)
    else:
        w, l = window or img.window or auto_window(img.pixels)
        disp = to_display(img, w, l, invert, cmap)
    disp = np.ascontiguousarray(disp)
    # pixels não quadrados: corrige a proporção
    if img.pixel_spacing:
        rs, cs = img.pixel_spacing
        if rs and cs and abs(rs / cs - 1) > 0.01:
            h, w_ = disp.shape[:2]
            new_h = max(1, int(round(h * rs / cs)))
            idx = np.clip((np.arange(new_h) * h / new_h).astype(int), 0, h - 1)
            disp = np.ascontiguousarray(disp[idx])
    if max_size:
        h, w_ = disp.shape[:2]
        k = max(h, w_) / max_size
        if k > 1:
            ys = np.clip((np.arange(int(h / k)) * k).astype(int), 0, h - 1)
            xs = np.clip((np.arange(int(w_ / k)) * k).astype(int), 0, w_ - 1)
            disp = np.ascontiguousarray(disp[ys][:, xs])
    return disp


def save_image(arr: np.ndarray, path: Path, quality: int = 92) -> None:
    from PySide6.QtGui import QImage
    arr = np.ascontiguousarray(arr)
    h, w = arr.shape[:2]
    if arr.ndim == 2:
        q = QImage(arr.data, w, h, arr.strides[0], QImage.Format_Grayscale8)
    else:
        q = QImage(arr.data, w, h, arr.strides[0], QImage.Format_RGB888)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not q.save(str(path), None, quality):
        raise ExportError(f"Não foi possível gravar {path.name}")


def _study_folder(e: _Entry, anon: bool) -> str:
    info = e.info
    if anon:
        return f"exame{e.n:02d}_{_safe(info.get('modalities', ''), 12)}"
    d = info.get("study_date", "")
    return _safe(f"{info.get('patient_name', '')}_{d}_{info.get('modalities', '')}", 60)


def export_images(repo, items: list[ExportItem], dest: Path, fmt: str = "jpg", quality: int = 92,
                  window: tuple[float, float] | None = None, invert: bool = False, max_size: int | None = None,
                  every: int = 1, anonymous_names: bool = False, progress=None, cancel=None,
                  cmap: str | None = None, image_filter: str = "") -> ExportResult:
    """Uma imagem por quadro, em pastas exame/série. `window` None = janela do arquivo."""
    dest = Path(dest)
    res = ExportResult(dest)
    entries = _collect(repo, items)
    if not entries:
        raise ExportError("Nada para exportar.")
    ext = "png" if fmt.lower() == "png" else "jpg"
    total = sum(len(s["frames"][::max(1, every)]) for e in entries for s in e.series)
    done = 0
    single = total == 1
    for e in entries:
        sdir = dest if single else dest / _study_folder(e, anonymous_names)
        for s in e.series:
            sub = sdir if single else sdir / _safe(f"SE{s['number']:03d}_{s['modality']}_{s['description']}", 50)
            for k, f in enumerate(s["frames"][::max(1, every)], 1):
                _check(cancel)
                name = (f"{_safe(s['description'] or 'imagem', 30)}_{f.instance_number or k:04d}" if single
                        else f"IM{k:04d}")
                try:
                    save_image(render_frame(f, window, invert, max_size, cmap, image_filter),
                               sub / f"{name}.{ext}", quality)
                    res.images += 1
                except Exception as err:  # noqa: BLE001
                    res.errors.append(f"{Path(f.path).name}: {err}")
                done += 1
                _progress(progress, done, total, f"Imagens: {done}/{total}")
        res.studies += 1
    return res


# ------------------------------------------------------------------ DICOM
def _write_full_viewer(repo, entries: list[_Entry], dest: Path, anon: bool, progress, cancel, done: int,
                       total: int) -> Path:
    """Visualizador completo: pixels originais (medidas em mm, HU, ROIs, MPR)."""
    from ipe.exporter.full_viewer import write_series, write_thumb
    vdir = dest / "VISUALIZADOR"
    data = {"title": "Exames", "full": True, "studies": []}
    counter = [done]

    def tick():
        counter[0] += 1
        _progress(progress, counter[0], total, f"Visualizador: {counter[0]}/{total}")
    for e in entries:
        info = e.info
        d = info.get("study_date", "")
        st = {"label": (f"Exame {e.n}" if anon else info.get("patient_name", "")),
              "sub": " · ".join(x for x in (info.get("modalities", ""), info.get("description", ""),
                                              "" if anon else (f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 else d))
                                if x),
              "series": []}
        keys = {(k["sop_uid"], k["frame_index"]) for k in repo.key_images(e.study_uid)}
        for si, s in enumerate(e.series):
            _check(cancel)
            sid = f"e{e.n:02d}s{si + 1:03d}"
            anns = repo.annotations_for_series([s["series_uid"]])
            try:
                meta = write_series(s, sid, vdir, anns, keys, tick, cancel)
                write_thumb(s, vdir / "dados" / f"{sid}_thumb.jpg")
                meta["thumb"] = f"VISUALIZADOR/dados/{sid}_thumb.jpg"
                st["series"].append(meta)
            except Cancelled:
                raise
            except Exception as err:  # noqa: BLE001
                log.warning("visualizador: série %s falhou: %s", s["series_uid"], err)
        data["studies"].append(st)
    from ipe.exporter.full_viewer_page import page as full_page
    html = dest / "ABRIR_VISUALIZADOR.html"
    html.write_text(full_page(data), encoding="utf-8")
    return html


def _write_viewer(entries: list[_Entry], dest: Path, anon: bool, progress, cancel, done: int, total: int) -> Path:
    """Visualizador HTML: prévias JPG + uma página que funciona offline em qualquer navegador."""
    vdir = dest / "VISUALIZADOR"
    data = {"title": "Exames", "studies": []}
    for e in entries:
        info = e.info
        d = info.get("study_date", "")
        st = {"label": (f"Exame {e.n}" if anon else info.get("patient_name", "")),
              "sub": " · ".join(x for x in (info.get("modalities", ""), info.get("description", ""),
                                              "" if anon else (f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 else d))
                                if x),
              "series": []}
        for si, s in enumerate(e.series):
            rel = f"img/e{e.n:02d}s{si + 1:03d}"
            names = []
            for k, f in enumerate(s["frames"], 1):
                _check(cancel)
                fn = f"{k:04d}.jpg"
                try:
                    save_image(render_frame(f, max_size=1024), vdir / rel / fn, 88)
                    names.append(fn)
                except Exception as err:  # noqa: BLE001
                    log.debug("prévia falhou %s: %s", f.path, err)
                done += 1
                _progress(progress, done, total, f"Visualizador: {done}/{total}")
            if names:
                st["series"].append({"dir": f"VISUALIZADOR/{rel}", "files": names,
                                     "label": f"{s['number']} {s['modality']} {s['description']}".strip()})
        data["studies"].append(st)
    from ipe.exporter.html_viewer import page
    html = dest / "ABRIR_VISUALIZADOR.html"
    html.write_text(page(data), encoding="utf-8")
    return html


def _fill_for_dicomdir(ds, n: int) -> None:
    """O DICOMDIR exige alguns campos preenchidos (PS3.3 F.5). Só completa o que estiver vazio."""
    defaults = {"StudyDate": "19000101", "StudyTime": "000000", "StudyID": str(n), "PatientID": f"P{n:03d}",
                "Modality": "OT", "SeriesNumber": 1, "InstanceNumber": 1}
    for kw, val in defaults.items():
        if kw not in ds or ds.data_element(kw).value in (None, ""):
            setattr(ds, kw, val)
    if "PatientName" not in ds:
        ds.PatientName = ""


def export_dicom(repo, items: list[ExportItem], dest: Path, opts: AnonOptions | None = None,
                 dicomdir: bool = True, viewer: bool | str = True, zip_output: bool = False, progress=None,
                 cancel=None, primeiro: int = 1) -> ExportResult:
    """`viewer`: False, "light" (só prévias JPG) ou True/"full" (medidas, HU, MPR)."""
    """Copia os arquivos DICOM (anonimizados se pedido) para `dest` (pasta nova ou vazia)."""
    opts = opts or AnonOptions()
    dest = Path(dest)
    entries = _collect(repo, items)
    if not entries:
        raise ExportError("Nada para exportar.")
    for e in entries:           # `primeiro`: de onde conta o {n} (a cópia no banco não repete ANON001)
        e.n += max(1, int(primeiro)) - 1
    if dest.exists() and any(dest.iterdir()) and not zip_output:
        raise ExportError("A pasta de destino não está vazia. Escolha uma pasta vazia (ou nova).")
    salt = hashlib.sha256(datetime.now().isoformat().encode()).hexdigest()[:16]
    work = Path(tempfile.mkdtemp(prefix="dv_export_")) if zip_output else dest
    work.mkdir(parents=True, exist_ok=True)
    res = ExportResult(dest)
    stage = Path(tempfile.mkdtemp(prefix="dv_stage_"))
    try:
        # arquivos distintos (um multiquadro aparece uma vez só)
        plan: list[tuple[_Entry, str]] = []
        for e in entries:
            seen = set()
            for s in e.series:
                for f in s["frames"]:
                    if f.path not in seen:
                        seen.add(f.path)
                        plan.append((e, f.path))
        n_prev = sum(len(s["frames"]) for e in entries for s in e.series) if viewer else 0
        total = len(plan) + n_prev
        done = 0
        staged: list[Path] = []
        path_map: dict[str, str] = {}
        for k, (e, path) in enumerate(plan, 1):
            _check(cancel)
            try:
                ds = pydicom.dcmread(path)
                anonymize(ds, opts, e.n, salt)
                if dicomdir:
                    _fill_for_dicomdir(ds, e.n)
                out = stage / f"{k:06d}.dcm"
                ds.save_as(out, enforce_file_format=True)
                staged.append(out)
                path_map[path] = str(out)
            except Exception as err:  # noqa: BLE001
                res.errors.append(f"{Path(path).name}: {err}")
            done += 1
            _progress(progress, done, total, f"DICOM: {done}/{len(plan)}")
        wrote = False
        if dicomdir and staged:
            try:
                from pydicom.fileset import FileSet
                fs = FileSet()
                fs.ID = "DICOMVIEWER"
                for p in staged:
                    fs.add(str(p))
                fs.write(str(work))
                wrote = True
                res.dicomdir = True
            except Exception as err:  # noqa: BLE001
                log.warning("DICOMDIR falhou: %s", err)
                res.warnings.append(f"DICOMDIR não foi criado ({err}); os arquivos foram copiados mesmo assim.")
        if not wrote:
            ddir = work / "DICOM"
            ddir.mkdir(parents=True, exist_ok=True)
            for p in staged:
                shutil.copy2(p, ddir / f"IM{p.stem}")
        res.files = len(staged)
        if opts.enabled:
            # o visualizador usa as cópias anonimizadas (inclusive sem o texto gravado nos pixels)
            from dataclasses import replace
            for e in entries:
                for s in e.series:
                    s["frames"] = [replace(f, path=path_map.get(f.path, f.path)) for f in s["frames"]]
        if viewer == "light":
            res.viewer = _write_viewer(entries, work, opts.enabled, progress, cancel, done, total)
        elif viewer:
            res.viewer = _write_full_viewer(repo, entries, work, opts.enabled, progress, cancel, done, total)
        (work / "LEIA-ME.txt").write_text(
            "Exportado pelo Ipê (não destinado a uso diagnóstico).\n"
            + ("Arquivos DICOM com DICOMDIR (abrem em visualizadores DICOM: pasta raiz ou DICOMDIR).\n"
               if res.dicomdir else "Arquivos DICOM na pasta DICOM.\n")
            + ("Visualizador simples: abra ABRIR_VISUALIZADOR.html no navegador.\n" if viewer else "")
            + ("Dados do paciente removidos (anonimizado).\n" if opts.enabled else ""),
            encoding="utf-8")
        res.studies = len(entries)
        if zip_output:
            zpath = dest if dest.suffix.lower() == ".zip" else dest.with_suffix(".zip")
            zpath.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in sorted(work.rglob("*")):
                    if p.is_file():
                        zf.write(p, p.relative_to(work).as_posix())
            res.zip_path = zpath
            res.dest = zpath
    except Cancelled:
        if not zip_output:
            res.warnings.append("Cancelado: a pasta ficou incompleta.")
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        if zip_output:
            shutil.rmtree(work, ignore_errors=True)
    return res


def manifest(res: ExportResult) -> str:
    return json.dumps({"files": res.files, "images": res.images, "studies": res.studies}, ensure_ascii=False)
