"""Limpeza (autodelete) com lixeira.

Os estudos escolhidos pela política vão para a lixeira (pasta Lixeira/<data>/<estudo>),
saem do banco e ficam lá por alguns dias, podendo ser restaurados. Depois disso a
pasta é apagada de vez. Tudo fica no registro de exclusões.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from ipe.automation.rules import StudyStat, select_for_deletion
from ipe.importer.scanner import safe_name

log = logging.getLogger(__name__)


def disk_usage(path: Path) -> tuple[float, int]:
    """(% usado, bytes totais) do disco onde fica o armazenamento."""
    u = shutil.disk_usage(path)
    return (u.used / u.total * 100.0 if u.total else 0.0), u.total


def plan(repo, storage: Path, policy: dict, open_uids: set[str] = frozenset(),
         now: datetime | None = None) -> list[tuple[StudyStat, str]]:
    stats = repo.retention_stats()
    pct, total = disk_usage(storage)
    return select_for_deletion(stats, policy, now or datetime.now(), pct, total,
                               sum(s.size_bytes for s in stats), open_uids)


def trash_study(repo, stat: StudyStat, storage: Path, trash_root: Path, reason: str) -> int:
    """Move os arquivos do estudo para a lixeira e tira do banco. Devolve o nº de arquivos."""
    dest = trash_root / datetime.now().strftime("%Y%m%d") / safe_name(stat.study_uid)
    dest.mkdir(parents=True, exist_ok=True)
    moved = 0
    root = storage.resolve()
    for f in repo.files_for_study(stat.study_uid):
        p = Path(f)
        try:
            if p.exists() and root in p.resolve().parents:
                target = dest / p.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(p), str(target))
                moved += 1
        except OSError as e:
            log.warning("Não foi possível mover %s para a lixeira: %s", p, e)
    (dest / "manifest.json").write_text(json.dumps({
        "study_uid": stat.study_uid, "patient": stat.patient, "description": stat.description,
        "modalities": stat.modalities, "reason": reason, "at": datetime.now().isoformat(timespec="seconds"),
        "files": moved}, ensure_ascii=False, indent=1), encoding="utf-8")
    repo.delete_study(stat.study_uid, storage)
    repo.log_deletion(stat.study_uid, stat.patient, stat.description, reason, "trash")
    return moved


def trash_entries(trash_root: Path) -> list[dict]:
    out = []
    if not trash_root.exists():
        return out
    for m in sorted(trash_root.glob("*/*/manifest.json"), reverse=True):
        try:
            d = json.loads(m.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        d["folder"] = str(m.parent)
        out.append(d)
    return out


def restore(repo, db, storage: Path, entry: dict) -> int:
    from ipe.importer.scanner import Importer
    folder = Path(entry["folder"])
    r = Importer(db, storage, copy_to_storage=True, origin="import").import_paths([folder])
    from ipe.importer.thumbnails import generate_thumbnails
    generate_thumbnails(repo, r.new_series)
    shutil.rmtree(folder, ignore_errors=True)
    repo.log_deletion(entry["study_uid"], entry.get("patient", ""), entry.get("description", ""),
                      "restaurado da lixeira", "restore")
    return r.added


def purge(repo, trash_root: Path, days: int, now: datetime | None = None) -> int:
    """Apaga de vez o que está na lixeira há mais de `days` dias."""
    now = now or datetime.now()
    n = 0
    if not trash_root.exists():
        return 0
    for day_dir in trash_root.iterdir():
        try:
            day = datetime.strptime(day_dir.name, "%Y%m%d")
        except ValueError:
            continue
        if day < now - timedelta(days=days):
            for e in trash_entries(trash_root):
                if Path(e["folder"]).parent == day_dir:
                    repo.log_deletion(e["study_uid"], e.get("patient", ""), e.get("description", ""),
                                      "lixeira esvaziada", "purge")
                    n += 1
            shutil.rmtree(day_dir, ignore_errors=True)
    return n
