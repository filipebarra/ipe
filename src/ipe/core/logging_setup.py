"""Log em arquivo rotativo + console."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: Path, level: int = logging.INFO) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = logging.getLogger()
    if root.handlers:  # já configurado (ex.: testes)
        return
    root.setLevel(level)
    fh = RotatingFileHandler(log_dir / "dicomviewer.log", maxBytes=5_000_000,
                             backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)
    # pydicom é verboso com avisos de arquivos fora do padrão
    logging.getLogger("pydicom").setLevel(logging.ERROR)
