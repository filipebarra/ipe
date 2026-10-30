"""Arrastar arquivos, pastas ou ZIPs do Explorer/gerenciador de arquivos para o programa.

Um filtro de eventos na aplicação intercepta o arrasto de arquivos em qualquer
ponto das janelas do programa (banco de dados, viewer, janelas de outros
monitores), mostra o aviso "Solte para importar" e manda os caminhos para a
janela principal importar. Arrastos internos (miniatura de série para um
quadro) não têm arquivos e seguem o caminho normal.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QLabel, QWidget


log = logging.getLogger(__name__)


def local_paths(mime) -> list[Path]:
    """Caminhos locais do arrasto (URLs file://; no Windows também o formato FileNameW)."""
    if mime is None:
        return []
    out: list[Path] = []
    if mime.hasUrls():
        for u in mime.urls():
            f = u.toLocalFile()
            if f:
                out.append(Path(f))
    if not out:
        for fmt in mime.formats():
            if "FileNameW" in fmt or fmt == "text/uri-list":
                raw = bytes(mime.data(fmt))
                try:
                    text = raw.decode("utf-16-le" if "FileNameW" in fmt else "utf-8")
                except UnicodeDecodeError:
                    continue
                for line in text.replace("\x00", "\n").splitlines():
                    line = line.strip()
                    if line.startswith("file:"):
                        from PySide6.QtCore import QUrl
                        line = QUrl(line).toLocalFile()
                    if line and Path(line).exists():
                        out.append(Path(line))
    return out


def describe(paths: list[Path]) -> str:
    n_dirs = sum(1 for p in paths if p.is_dir())
    n_zip = sum(1 for p in paths if p.is_file() and p.suffix.lower() == ".zip")
    n_files = len(paths) - n_dirs - n_zip
    parts = []
    if n_dirs:
        parts.append(f"{n_dirs} pasta" + ("s" if n_dirs > 1 else ""))
    if n_zip:
        parts.append(f"{n_zip} ZIP")
    if n_files:
        parts.append(f"{n_files} arquivo" + ("s" if n_files > 1 else ""))
    return ", ".join(parts)


class DropOverlay(QLabel):
    """Aviso semitransparente sobre a janela enquanto os arquivos são arrastados."""

    def __init__(self, window: QWidget):
        super().__init__(window)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet("QLabel{background:rgba(20,40,70,190);color:white;font-size:22px;"
                           "border:3px dashed rgb(255,200,0);border-radius:18px}")
        self.hide()

    def show_for(self, paths: list[Path]) -> None:
        win = self.parentWidget()
        self.setGeometry(win.rect().adjusted(24, 24, -24, -24))
        self.setText(f"Solte para importar\n{describe(paths)}\n\n"
                     "(os exames abrem quando terminar)")
        self.raise_()
        self.show()


class FileDropFilter(QObject):
    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self._overlays: dict[QWidget, DropOverlay] = {}
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(120)       # evita piscar ao passar de um widget para outro
        self._hide_timer.timeout.connect(self.hide_all)

    def _window_of(self, obj) -> QWidget | None:
        if not isinstance(obj, QWidget):
            return None
        win = obj.window()
        return win if win in self.main.drop_windows() else None

    def _overlay(self, win: QWidget) -> DropOverlay:
        ov = self._overlays.get(win)
        if ov is None:
            ov = self._overlays[win] = DropOverlay(win)
        return ov

    def hide_all(self) -> None:
        for ov in self._overlays.values():
            ov.hide()

    def eventFilter(self, obj, e) -> bool:  # noqa: N802
        try:
            return self._filter(obj, e)
        except Exception:  # noqa: BLE001
            log.exception("Erro ao tratar arrasto de arquivos")
            return False

    def _filter(self, obj, e) -> bool:
        t = e.type()
        if t not in (QEvent.DragEnter, QEvent.DragMove, QEvent.DragLeave, QEvent.Drop):
            return False
        win = self._window_of(obj)
        if win is None:
            return False
        if t == QEvent.DragLeave:
            self._hide_timer.start()
            return False
        paths = local_paths(e.mimeData())
        if t == QEvent.DragEnter:
            log.info("Arrasto sobre %s: formatos=%s, caminhos=%s", type(obj).__name__,
                     list(e.mimeData().formats())[:8], [str(p) for p in paths][:5])
        if not paths:
            return False                      # arrasto interno (série -> quadro)
        if t in (QEvent.DragEnter, QEvent.DragMove):
            self._hide_timer.stop()
            e.setDropAction(Qt.CopyAction)
            e.accept()
            if t == QEvent.DragEnter:
                self._overlay(win).show_for(paths)
            return True
        # Drop
        log.info("Arquivos soltos: %s", [str(p) for p in paths][:10])
        self.hide_all()
        e.setDropAction(Qt.CopyAction)
        e.accept()
        QTimer.singleShot(0, lambda p=paths: self.main.import_dropped(p))
        return True
