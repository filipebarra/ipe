"""Editor de traduções: o usuário traduz o programa para qualquer idioma, sem mexer no código.

Mostra os textos em português de um lado e a tradução do outro. O que é salvo vai para
<configurações>/locale/<código>.json e vale mais que o arquivo que vem com o programa.
"""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from ipe.core import i18n
from ipe.ui.tabelas import colunas_ajustaveis


class TranslateDialog(QDialog):
    def __init__(self, lang: str = "en", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Traduções")
        self.resize(1000, 640)
        self.lang = lang if lang != i18n.BASE_LANG else "en"
        self.map: dict[str, str] = {}
        self.lang_box = QComboBox()
        self._fill_languages()
        self.lang_box.activated.connect(lambda _i: self.set_lang(self.lang_box.currentData()))
        b_new = QPushButton("Novo idioma…")
        b_new.clicked.connect(self.new_language)
        self.search = QLineEdit(placeholderText="procurar…")
        self.search.textChanged.connect(lambda _t: self.render())
        self.only_missing = QCheckBox("Só o que falta")
        self.only_missing.toggled.connect(lambda _on: self.render())
        self.only_seen = QCheckBox("Só o que apareceu na tela")
        self.only_seen.setToolTip("Textos que o programa mostrou nesta sessão e ainda não têm tradução")
        self.only_seen.toggled.connect(lambda _on: self.render())
        top = QHBoxLayout()
        top.addWidget(QLabel("Idioma:"))
        top.addWidget(self.lang_box)
        top.addWidget(b_new)
        top.addWidget(self.search, 1)
        top.addWidget(self.only_missing)
        top.addWidget(self.only_seen)
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Português (original)", "Tradução"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self.table.itemChanged.connect(self._edited)
        colunas_ajustaveis(self.table)
        self.status = QLabel()
        b_imp = QPushButton("Importar arquivo…")
        b_imp.clicked.connect(self.import_file)
        b_exp = QPushButton("Exportar arquivo…")
        b_exp.clicked.connect(self.export_file)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Save).setText("Salvar")
        bb.button(QDialogButtonBox.Close).setText("Fechar")
        bb.accepted.connect(self.save)
        bb.rejected.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(self.status, 1)
        row.addWidget(b_imp)
        row.addWidget(b_exp)
        row.addWidget(bb)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(QLabel("Dica: {} marca a parte que muda na frase (número, nome do arquivo…); "
                             "mantenha os {} na tradução, na mesma ordem."))
        lay.addWidget(self.table, 1)
        lay.addLayout(row)
        self.set_lang(self.lang)

    # ------------------------------------------------------------ idiomas
    def _fill_languages(self) -> None:
        self.lang_box.blockSignals(True)
        self.lang_box.clear()
        for code, name in i18n.available():
            if code != i18n.BASE_LANG:
                self.lang_box.addItem(f"{name} ({code})", code)
        if self.lang_box.findData(self.lang) < 0:
            self.lang_box.addItem(f"{i18n.language_name(self.lang)} ({self.lang})", self.lang)
        self.lang_box.setCurrentIndex(max(0, self.lang_box.findData(self.lang)))
        self.lang_box.blockSignals(False)

    def set_lang(self, code: str) -> None:
        self.lang = code or "en"
        self.map = dict(i18n.translations_for(self.lang))
        self._fill_languages()
        self.render()

    def new_language(self) -> None:
        code, ok = QInputDialog.getText(self, "Novo idioma",
                                        "Código do idioma (ex.: fr, de, it, en-GB):")
        code = (code or "").strip()
        if not ok or not code:
            return
        name, ok = QInputDialog.getText(self, "Novo idioma", "Nome do idioma (ex.: Français):")
        if ok and name.strip():
            i18n.LANGUAGE_NAMES.setdefault(code, name.strip())
        path = i18n.user_file(code)
        if path is not None and not path.exists():
            i18n.save_user(code, {})
        self.set_lang(code)

    # ------------------------------------------------------------ tabela
    def rows(self) -> list[str]:
        srcs = i18n.all_sources()
        text = self.search.text().strip().lower()
        if self.only_seen.isChecked():
            seen = set(i18n.missing())
            srcs = [s for s in srcs if s in seen] or sorted(seen)
        if self.only_missing.isChecked():
            srcs = [s for s in srcs if not self.map.get(s)]
        if text:
            srcs = [s for s in srcs if text in s.lower() or text in (self.map.get(s, "").lower())]
        return srcs

    def render(self) -> None:
        srcs = self.rows()
        self.table.blockSignals(True)
        self.table.setRowCount(len(srcs))
        for r, src in enumerate(srcs):
            a = QTableWidgetItem(src)
            a.setFlags(a.flags() & ~Qt.ItemIsEditable)
            a.setData(Qt.UserRole, src)
            self.table.setItem(r, 0, a)
            self.table.setItem(r, 1, QTableWidgetItem(self.map.get(src, "")))
        self.table.blockSignals(False)
        total = len(i18n.all_sources())
        done = sum(1 for s in i18n.all_sources() if self.map.get(s))
        self.status.setText(f"{done} de {total} traduzidos ({done * 100 // max(1, total)}%) · "
                            f"mostrando {len(srcs)}")

    def _edited(self, item: QTableWidgetItem) -> None:
        if item.column() != 1:
            return
        src = self.table.item(item.row(), 0).data(Qt.UserRole)
        value = item.text().strip()
        if value:
            if src.count("{}") != value.count("{}"):
                self.status.setText("Atenção: a tradução deve ter os mesmos {} do original.")
            self.map[src] = value
        else:
            self.map.pop(src, None)

    # ------------------------------------------------------------ arquivos
    def save(self) -> None:
        path = i18n.save_user(self.lang, self.map)
        if path is None:
            QMessageBox.warning(self, "Traduções", "Não foi possível salvar (pasta de configurações).")
            return
        self.status.setText(f"Salvo em {path}. A troca aparece ao reabrir o programa.")

    def import_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Importar tradução", "", "JSON (*.json)")
        if not path:
            return
        try:
            data = json.loads(open(path, encoding="utf-8").read())
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Traduções", f"Arquivo inválido:\n{e}")
            return
        if isinstance(data, dict):
            self.map.update({k: v for k, v in data.items() if isinstance(v, str)})
            self.render()

    def export_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Exportar tradução", f"{self.lang}.json",
                                              "JSON (*.json)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.map, f, ensure_ascii=False, indent=1, sort_keys=True)
        self.status.setText(f"Exportado para {path}")
