"""Escolher quais séries de um estudo abrir (com as dinâmicas agrupadas, se houver)."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
)

from ipe.ui.icons import with_badge


class SeriesChooserDialog(QDialog):
    def __init__(self, repo, study_uid: str, preselect: list[str] | None = None, parent=None):
        super().__init__(parent)
        info = repo.study_info(study_uid) or {}
        self.setWindowTitle("Abrir séries")
        self.resize(560, 620)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<b>{info.get('description', '')}</b> — marque as séries que quer abrir "
                             "(abrem nesta ordem, uma por quadro):"))
        self.list = QListWidget()
        self.list.setIconSize(QSize(64, 64))
        self.list.setDragDropMode(QListWidget.InternalMove)      # arrastar muda a ordem
        pre = set(preselect or [])
        series = repo.series_for_study(study_uid)
        by_uid = {s.series_uid: s for s in series}
        grouped = set()
        for g in repo.series_groups(study_uid):
            grouped |= set(g["series_uids"])
            first = by_uid.get(g["series_uids"][0]) if g["series_uids"] else None
            it = QListWidgetItem(f"▦ {g['name']} — {len(g['series_uids'])} fases")
            pm = QPixmap()
            if first is not None and first.thumbnail:
                pm.loadFromData(first.thumbnail, "PNG")
            it.setIcon(QIcon(with_badge(pm, "fases", QColor(255, 180, 0))))
            self._add(it, f"group:{g['id']}", pre)
        for s in series:
            if not s.num_images:
                continue
            extra = "  (fase de uma dinâmica)" if s.series_uid in grouped else ""
            it = QListWidgetItem(f"Se {s.series_number}  {s.modality}  {s.description}  "
                                 f"({s.num_images} im){extra}")
            if s.thumbnail:
                pm = QPixmap()
                pm.loadFromData(s.thumbnail, "PNG")
                it.setIcon(QIcon(pm))
            self._add(it, s.series_uid, pre)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        for text, state in (("Marcar todas", Qt.Checked), ("Desmarcar todas", Qt.Unchecked)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, st=state: self._set_all(st))
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Abrir")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _add(self, it: QListWidgetItem, uid: str, pre: set[str]) -> None:
        it.setData(Qt.UserRole, uid)
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
        it.setCheckState(Qt.Checked if uid in pre else Qt.Unchecked)
        self.list.addItem(it)

    def _set_all(self, state) -> None:
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(state)

    def chosen(self) -> list[str]:
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]
