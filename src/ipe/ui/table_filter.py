"""Filtros por coluna numa tabela (linha de filtros sob o cabeçalho + filtro por valores).

Sintaxe do filtro de texto (vale para todas as colunas):
- texto: contém, sem diferenciar maiúsculas nem acentos; * e ? funcionam como curinga;
  "=texto" exige igual;
- vários termos com | (qualquer um serve): "MG|US";
- ! nega: "!CT" (tudo menos CT);
- números: >10  >=10  <5  10..20  =3;
- datas: 2025  03/2025  15/03/2025  >=01/2025  01/01/2025..30/06/2025; também "hoje",
  "7d" (últimos 7 dias), "12m" (últimos 12 meses);
- sim / não nas colunas de marcar (ex.: Protegido).
"""

from __future__ import annotations

import fnmatch
import re
import unicodedata
from datetime import date, timedelta

from PySide6.QtCore import QSortFilterProxyModel, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHeaderView, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout,
)


def fold(s: str) -> str:
    """Minúsculas e sem acentos (para comparar)."""
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _num(s: str) -> float | None:
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def _date_bounds(s: str, today: date) -> tuple[str, str] | None:
    """Texto de data -> (início, fim) em AAAAMMDD (inclusivo)."""
    s = s.strip().lower()
    if s == "hoje":
        d = today.strftime("%Y%m%d")
        return d, d
    m = re.fullmatch(r"(\d+)\s*([dm])", s)
    if m:
        n = int(m.group(1))
        start = today - (timedelta(days=n) if m.group(2) == "d" else timedelta(days=round(n * 30.44)))
        return start.strftime("%Y%m%d"), today.strftime("%Y%m%d")
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        d = f"{m.group(3)}{int(m.group(2)):02d}{int(m.group(1)):02d}"
        return d, d
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", s)
    if m:
        return f"{m.group(2)}{int(m.group(1)):02d}01", f"{m.group(2)}{int(m.group(1)):02d}31"
    m = re.fullmatch(r"(\d{4})", s)
    if m:
        return f"{s}0101", f"{s}1231"
    m = re.fullmatch(r"(\d{8})", s)
    if m:
        return s, s
    return None


def match_term(term: str, kind: str, raw, shown: str, today: date) -> bool:
    t = term.strip()
    if not t:
        return True
    if kind in ("int", "float"):
        v = float(raw or 0)
        m = re.fullmatch(r"(>=|<=|>|<|=)?\s*(\d+(?:[.,]\d+)?)(?:\s*\.\.\s*(\d+(?:[.,]\d+)?))?", t)
        if m:
            op, a, b = m.group(1), _num(m.group(2)), _num(m.group(3) or "")
            if a is not None and b is not None:
                return a <= v <= b
            if a is not None:
                return {">": v > a, ">=": v >= a, "<": v < a, "<=": v <= a}.get(op, v == a)
    if kind in ("date", "datetime"):
        v = str(raw or "")[:8]
        m = re.fullmatch(r"(>=|<=|>|<)?\s*(.+?)(?:\s*\.\.\s*(.+))?", t)
        if m and v:
            op, a, b = m.group(1), _date_bounds(m.group(2), today), _date_bounds(m.group(3) or "", today)
            if a and b:
                return a[0] <= v <= b[1]
            if a:
                return {">": v > a[1], ">=": v >= a[0], "<": v < a[0], "<=": v <= a[1]}.get(op, a[0] <= v <= a[1])
    if kind == "bool":
        yes = fold(t) in ("sim", "s", "1", "true", "x")
        no = fold(t) in ("nao", "n", "0", "false")
        if yes or no:
            return bool(raw) == yes
    text = fold(shown)
    if t.startswith("="):
        return text == fold(t[1:])
    ft = fold(t)
    if "*" in ft or "?" in ft:
        return fnmatch.fnmatch(text, ft if ft.startswith("*") or ft.endswith("*") else f"*{ft}*")
    return ft in text


def match(filter_text: str, kind: str, raw, shown: str, today: date | None = None) -> bool:
    """Filtro de uma coluna: termos com | (ou); ! nega o termo."""
    today = today or date.today()
    terms = [x for x in filter_text.split("|") if x.strip()]
    if not terms:
        return True
    pos = [x for x in terms if not x.strip().startswith("!")]
    neg = [x.strip()[1:] for x in terms if x.strip().startswith("!")]
    if any(match_term(n, kind, raw, shown, today) for n in neg):
        return False
    return not pos or any(match_term(p, kind, raw, shown, today) for p in pos)


class FilterProxy(QSortFilterProxyModel):
    """Ordena e filtra por coluna. `kinds[col]` diz como interpretar a coluna."""

    def __init__(self, kinds: list[str], parent=None):
        super().__init__(parent)
        self.kinds = kinds
        self.text_filters: dict[int, str] = {}
        self.value_filters: dict[int, set[str]] = {}

    def set_text_filter(self, col: int, text: str) -> None:
        if text.strip():
            self.text_filters[col] = text
        else:
            self.text_filters.pop(col, None)
        self._refilter()

    def set_value_filter(self, col: int, values: set[str] | None) -> None:
        if values is None:
            self.value_filters.pop(col, None)
        else:
            self.value_filters[col] = set(values)
        self._refilter()

    def clear_filters(self) -> None:
        self.text_filters.clear()
        self.value_filters.clear()
        self._refilter()

    def _refilter(self) -> None:
        # Qt 6.10+: beginFilterChange/endFilterChange; versões anteriores: invalidateFilter
        if hasattr(self, "beginFilterChange"):
            self.beginFilterChange()
            self.endFilterChange()
        else:
            self.invalidateFilter()

    @property
    def active(self) -> bool:
        return bool(self.text_filters or self.value_filters)

    def filterAcceptsRow(self, row, parent) -> bool:  # noqa: N802
        m = self.sourceModel()
        today = date.today()
        for col, vals in self.value_filters.items():
            if str(m.data(m.index(row, col, parent), Qt.DisplayRole) or "") not in vals:
                return False
        for col, text in self.text_filters.items():
            idx = m.index(row, col, parent)
            if not match(text, self.kinds[col], m.data(idx, Qt.UserRole),
                         str(m.data(idx, Qt.DisplayRole) or ""), today):
                return False
        return True


class FilterHeader(QHeaderView):
    """Cabeçalho com uma caixa de filtro embaixo de cada coluna."""
    filter_changed = Signal(int, str)

    def __init__(self, parent_table):
        super().__init__(Qt.Horizontal, parent_table)
        self._editors: list[QLineEdit] = []
        self._pad = 4
        self._timers: dict[int, QTimer] = {}
        self.setSectionsClickable(True)
        self.setSortIndicatorShown(True)
        self.setHighlightSections(False)
        self.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.sectionResized.connect(self.adjust_positions)
        self.sectionMoved.connect(self.adjust_positions)
        parent_table.horizontalScrollBar().valueChanged.connect(self.adjust_positions)

    def set_filter_boxes(self, count: int, placeholder: str = "filtrar") -> None:
        for e in self._editors:
            e.deleteLater()
        self._editors = []
        for col in range(count):
            e = QLineEdit(self)
            e.setPlaceholderText(placeholder)
            e.setClearButtonEnabled(True)
            e.setToolTip("Filtro desta coluna. Ex.: SILVA · MG|US · !CT · >10 · 2025 · 03/2025 · "
                         "01/01/2025..30/06/2025 · 30d · sim/não")
            e.setStyleSheet("QLineEdit{padding:1px 3px;font-size:11px}")
            t = QTimer(self)
            t.setSingleShot(True)
            t.setInterval(250)
            t.timeout.connect(lambda c=col, ed=e: self.filter_changed.emit(c, ed.text()))
            e.textChanged.connect(lambda _txt, tm=t: tm.start())
            self._timers[col] = t
            self._editors.append(e)
        self.updateGeometries()

    def editor(self, col: int) -> QLineEdit:
        return self._editors[col]

    def clear_boxes(self) -> None:
        for e in self._editors:
            e.blockSignals(True)
            e.clear()
            e.blockSignals(False)

    def sizeHint(self):  # noqa: N802
        size = super().sizeHint()
        if self._editors:
            size.setHeight(size.height() + self._editors[0].sizeHint().height() + self._pad)
        return size

    def updateGeometries(self) -> None:  # noqa: N802
        if self._editors:
            self.setViewportMargins(0, 0, 0, self._editors[0].sizeHint().height() + self._pad)
        else:
            self.setViewportMargins(0, 0, 0, 0)
        super().updateGeometries()
        self.adjust_positions()

    def adjust_positions(self, *_a) -> None:
        if not self._editors:
            return
        h = self._editors[0].sizeHint().height()
        top = super().sizeHint().height() + self._pad // 2
        for col, e in enumerate(self._editors):
            if self.isSectionHidden(col):
                e.hide()
                continue
            e.setGeometry(self.sectionViewportPosition(col) + 1, top, self.sectionSize(col) - 2, h)
            e.show()


class ValueFilterDialog(QDialog):
    """Filtrar por valores (como no Excel): marque os valores que devem aparecer."""

    def __init__(self, title: str, values: list[str], checked: set[str] | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Filtrar: {title}")
        self.resize(360, 460)
        lay = QVBoxLayout(self)
        self.search = QLineEdit(placeholderText="Procurar valor…")
        self.search.textChanged.connect(self._search)
        lay.addWidget(self.search)
        self.list = QListWidget()
        for v in values:
            it = QListWidgetItem(v if v else "(vazio)")
            it.setData(Qt.UserRole, v)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if checked is None or v in checked else Qt.Unchecked)
            self.list.addItem(it)
        lay.addWidget(self.list, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        b_all = bb.addButton("Todos", QDialogButtonBox.ResetRole)
        b_none = bb.addButton("Nenhum", QDialogButtonBox.ResetRole)
        b_all.clicked.connect(lambda: self._set(Qt.Checked))
        b_none.clicked.connect(lambda: self._set(Qt.Unchecked))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _search(self, text: str) -> None:
        f = fold(text)
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(bool(f) and f not in fold(it.text()))

    def _set(self, state) -> None:
        for i in range(self.list.count()):
            if not self.list.item(i).isHidden():
                self.list.item(i).setCheckState(state)

    def chosen(self) -> set[str] | None:
        """None = todos marcados (sem filtro)."""
        vals = {self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked}
        return None if len(vals) == self.list.count() else vals
