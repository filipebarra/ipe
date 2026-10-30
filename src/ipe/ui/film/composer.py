"""Compositor de filmes: várias folhas, cada uma com grade, papel e orientação próprios;
edição por célula; saída para impressora, PDF, imagens e impressora DICOM; filmes salvos."""

from __future__ import annotations

import copy
import logging
import threading
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QPointF, QRectF, QSize, QSizeF, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem,
    QMenu, QMessageBox, QPushButton, QSizePolicy, QSplitter, QToolBar, QToolButton, QVBoxLayout, QWidget,
)

from ipe.ui.tabelas import esvaziar_lista
from ipe.printing.film import LAYOUTS, OVERLAYS, PAPERS, Cell, Film, Sheet, parse_layout
from ipe.ui.film.cell import FilmCell
from ipe.ui.film.render import (
    FrameSource, page_size_px, paint_page_decor, render_sheet_image, sheet_geometry,
)

log = logging.getLogger(__name__)
BAR_STYLE = "QToolBar{border:none;spacing:4px;padding:0}"


class SheetView(QWidget):
    """A folha atual na tela: página com cabeçalho e as células (widgets FilmCell)."""

    def __init__(self, composer: "FilmComposer"):
        super().__init__(composer)
        self.c = composer
        self.cells: list[FilmCell] = []
        self.setMinimumSize(300, 300)
        self._scale = 1.0
        self._page = QRectF()

    def page_rect(self) -> QRectF:
        sheet = self.c.sheet
        size = page_size_px(sheet)
        pad = 12
        k = min((self.width() - 2 * pad) / size.width(), (self.height() - 2 * pad) / size.height())
        k = max(k, 0.05)
        w, h = size.width() * k, size.height() * k
        self._scale = k
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def rebuild(self) -> None:
        """Cria/ajusta os widgets das células para a folha atual."""
        sheet = self.c.sheet
        while len(self.cells) < sheet.capacity:
            cw = FilmCell(self.c.cache, self.c.settings, self)
            cw.csig.clicked.connect(self.c.select_cell)
            cw.csig.changed.connect(self.c._cell_changed)
            cw.csig.menu_requested.connect(self.c.cell_menu)
            cw.csig.dropped.connect(self.c._dropped)
            cw.csig.delete_requested.connect(lambda _w: self.c.delete_selection())
            cw.csig.expand_requested.connect(self.c.expand_requested.emit)
            cw.csig.note_added.connect(self.c._note_added)
            self.cells.append(cw)
        while len(self.cells) > sheet.capacity:
            old = self.cells.pop()
            old.hide()                    # some na hora (deleteLater só roda no laço de eventos)
            old.setParent(None)
            old.deleteLater()
        film = self.c.film
        for i, (cw, cell) in enumerate(zip(self.cells, sheet.cells)):
            cw.slot = (self.c.current, i)
            cw.overlay, cw.ruler, cw.anonymize = film.overlay, film.ruler, film.anonymize
            cw.note_tool = self.c.note_tool
            cw.left_tool = self.c.left_tool
            cw.show_notes = film.notes_visible
            cw.setCursor(Qt.CrossCursor if self.c.note_tool else Qt.ArrowCursor)
            if cell is None:
                cw.load(None, None, None)
            else:
                src = self.c.src
                cw.load(cell, src.frames(cell.series_uid), src.study_info(cell.study_uid), src.store)
            cw.is_selected = (self.c.current, i) in self.c.selection
            cw.show()
        self.relayout()
        self.update()

    def relayout(self) -> None:
        page = self.page_rect()
        self._page = page
        _h, _f, rects = sheet_geometry(self.c.film, self.c.sheet, page_size_px(self.c.sheet))
        k = self._scale
        for cw, r in zip(self.cells, rects):
            cw.setGeometry(int(page.x() + r.x() * k), int(page.y() + r.y() * k),
                           max(10, int(r.width() * k)), max(10, int(r.height() * k)))

    def resizeEvent(self, _e) -> None:  # noqa: N802
        self.relayout()

    def mouseDoubleClickEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton:
            self.c.expand_requested.emit()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(45, 45, 48))
        page = self.page_rect()
        p.fillRect(page.translated(3, 3), QColor(20, 20, 20))
        p.save()
        p.translate(page.topLeft())
        p.scale(self._scale, self._scale)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        film = self.c.film
        paint_page_decor(p, film, self.c.sheet, self.c.current + 1, len(film.sheets), self.c.src,
                         page_size_px(self.c.sheet))
        p.restore()
        p.end()


LEFT_TOOLS = {"wl": "Janela", "pan": "Mover", "zoom": "Zoom"}   # botão esquerdo nas imagens do filme


class _Bridge(QObject):
    done = Signal(object, object)
    progress = Signal(int, int)


class FilmComposer(QWidget):
    status_message = Signal(str)
    expand_requested = Signal()                        # duplo clique: expandir/restaurar o painel
    close_requested = Signal()
    open_study_requested = Signal(str, list)          # estudo, séries
    saved_to_study = Signal(str)                      # filme gravado dentro deste exame

    def __init__(self, repo, cache, settings, parent=None, local_ae_fn=None):
        super().__init__(parent)
        self.repo, self.cache, self.settings = repo, cache, settings
        self.local_ae_fn = local_ae_fn or (lambda: "DICOMVIEWER")
        self.src = FrameSource(repo)
        self.film = self._new_film()
        self.film_id: int | None = None
        self.dirty = False
        self.current = 0
        self.selected: tuple[int, int] | None = None      # âncora da seleção
        self.selection: list[tuple[int, int]] = []        # células selecionadas (folha atual)
        self.clipboard: list[Cell] = []                   # copiar/recortar/colar (vale entre filmes)
        self._loading = False
        self._bridge = _Bridge()
        self._bridge.done.connect(self._dicom_done)

        # --- barra do filme
        self.name_label = QLabel()
        from ipe.ui.fluxo import BarraQuebra
        tb1 = BarraQuebra()          # 0.99.6: painel estreito quebra a linha (antes ia tudo para um »)
        # "Salvar" leva junto a caixa "também no exame" (0.78: o botão "No exame" saiu)
        self.chk_no_exame = QCheckBox("também no exame", self)   # 0.99.6: a escolha mora na janela Salvar
        self.chk_no_exame.setVisible(False)
        self.chk_no_exame.setToolTip(
            "Ao salvar, grava também o filme dentro do exame, como a estação AW da GE: um SR com a "
            "montagem, as folhas prontas e as imagens soltas. Se o filme não mudou desde a última "
            "gravação, não grava de novo; se mudou, pergunta se substitui a anterior.")
        self.chk_no_exame.setChecked(bool(settings.get("printing.salvar_no_exame", False)))
        self.chk_no_exame.toggled.connect(lambda on: self._remember("salvar_no_exame", on))
        # 0.99.6: "Salvar…" abre a janela com nome, salvar/salvar como novo e também no exame;
        # "Imprimir…" abre a janela com impressora do computador, PDF, JPG/PNG, DICOM e as folhas
        for text, fn, tip in (
                ("Novo", self.new_film, "Começar um filme vazio"),
                ("Abrir…", self.open_saved, "Filmes salvos"),
                ("Salvar…", self.save_dialog, "Nome, salvar, salvar como novo e também no exame"),
                ("Imprimir…", self.imprimir, "Impressora do computador, PDF, JPG/PNG ou impressora DICOM, "
                                             "com a escolha das folhas"),
        ):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(fn)
            tb1.addWidget(b)
        tb1.addSeparator()
        tb1.addWidget(self.name_label)
        bar1 = QHBoxLayout()
        bar1.addWidget(tb1, 1)
        self.btn_expand = QToolButton()
        self.btn_expand.setText("⤢")
        self.btn_expand.setToolTip("Expandir o filme / voltar aos quadros (ou duplo clique no filme)")
        self.btn_expand.clicked.connect(self.expand_requested.emit)
        self.btn_close = QToolButton()
        self.btn_close.setText("✕")
        self.btn_close.setToolTip("Fechar o painel do filme (o filme continua guardado; Ctrl+P reabre)")
        self.btn_close.clicked.connect(self.close_requested.emit)
        bar1.addWidget(self.btn_expand, 0, Qt.AlignTop)
        bar1.addWidget(self.btn_close, 0, Qt.AlignTop)

        # --- barra da folha
        self.layout_box = QComboBox()
        self.layout_box.addItems(LAYOUTS + ["Outro…"])
        self.layout_box.setToolTip("Grade da folha (linhas × colunas)")
        self.layout_box.activated.connect(self._layout_chosen)
        self.paper_box = QComboBox()
        self.paper_box.addItems(list(PAPERS))
        self.paper_box.activated.connect(self._paper_chosen)
        self.orient_box = QComboBox()
        self.orient_box.addItems(["Retrato", "Paisagem"])
        self.orient_box.activated.connect(self._orient_chosen)
        self.all_sheets = QCheckBox("em todas as folhas")
        self.all_sheets.setToolTip("Layout, papel e orientação valem para todas as folhas")
        self.overlay_box = QComboBox()
        for k, v in OVERLAYS.items():
            self.overlay_box.addItem(v, k)
        self.overlay_box.activated.connect(lambda _i: self._set_opt("overlay", self.overlay_box.currentData()))
        self.chk_header = QCheckBox("Cabeçalho")
        self.chk_anon = QCheckBox("Anonimizar")
        self.chk_ruler = QCheckBox("Régua")
        self.chk_black = QCheckBox("Fundo preto")
        for chk, key in ((self.chk_header, "header"), (self.chk_anon, "anonymize"), (self.chk_ruler, "ruler"),
                         (self.chk_black, "black_page")):
            chk.toggled.connect(lambda on, k=key: self._set_opt(k, on))
        self.chk_black.setToolTip("Folha preta como filme de raio-X (bom para impressora DICOM)")
        tb2 = BarraQuebra()   # o que não couber desce para a linha de baixo (antes: botão » escondido)
        # botão esquerdo: a função do mouse (janela, mover, zoom) ou uma anotação do filme
        self.note_tool = ""
        lt = str(settings.get("printing.left_tool", "wl") or "wl")
        self.left_tool = lt if lt in LEFT_TOOLS else "wl"
        self.note_buttons: dict[str, QToolButton] = {}
        self.btn_mouse = QToolButton()
        self.btn_mouse.setCheckable(True)
        self.btn_mouse.setChecked(True)
        self.btn_mouse.setPopupMode(QToolButton.MenuButtonPopup)
        self.btn_mouse.setToolTip("Função do botão esquerdo nas imagens do filme (a seta escolhe). "
                                  "Arrastar pela alça ⠿ troca a imagem de lugar, seja qual for a função.")
        self.btn_mouse.clicked.connect(lambda: self.set_note_tool(""))
        self.mouse_menu = QMenu(self)
        self.mouse_menu.aboutToShow.connect(lambda: self.fill_mouse_menu(self.mouse_menu))
        self.btn_mouse.setMenu(self.mouse_menu)
        self.note_buttons[""] = self.btn_mouse
        tb2.addWidget(self.btn_mouse)
        tb2.addWidget(QLabel(" Anotar: "))
        for key, text, tip in (("arrow", "➚ Seta", "Arraste da ponta da seta para trás"),
                               ("text", "T Texto", "Clique onde o texto começa"),
                               ("pencil", "✎ Lápis", "Desenho livre")):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip + " — anotações ficam só no filme; depois de uma, o mouse volta à função dele")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, k=key: self.set_note_tool(k))
            self.note_buttons[key] = b
            tb2.addWidget(b)
        self.btn_notes = QToolButton()
        self.btn_notes.setText("Anotações")
        self.btn_notes.setCheckable(True)
        self.btn_notes.setChecked(True)
        self.btn_notes.setToolTip("Mostrar ou esconder as anotações do filme (seta, texto, lápis) — "
                                  "vale também para a impressão, o PDF e as imagens")
        self.btn_notes.toggled.connect(self.set_notes_visible)
        tb2.addWidget(self.btn_notes)
        self._update_mouse_button()
        tb2.addSeparator()
        tb2.addWidget(QLabel("Folha: "))
        for w in (self.layout_box, self.paper_box, self.orient_box, self.all_sheets):
            tb2.addWidget(w)
        tb2.addSeparator()
        tb2.addWidget(QLabel("Textos: "))
        tb2.addWidget(self.overlay_box)
        for w in (self.chk_header, self.chk_anon, self.chk_ruler, self.chk_black):
            tb2.addWidget(w)
        bar2 = QHBoxLayout()
        bar2.addWidget(tb2, 1)

        # --- folhas (esquerda)
        self.sheet_list = QListWidget()
        self.sheet_list.setViewMode(QListWidget.IconMode)
        self.sheet_list.setIconSize(QSize(90, 115))
        self.sheet_list.setMovement(QListWidget.Static)
        self.sheet_list.setFlow(QListWidget.TopToBottom)
        self.sheet_list.setWrapping(False)
        self.sheet_list.setSpacing(4)
        self.sheet_list.setMaximumWidth(170)
        self.sheet_list.currentRowChanged.connect(self._sheet_clicked)
        self.sheet_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.sheet_list.customContextMenuRequested.connect(self._sheet_menu)
        self.sheet_btns = QGridLayout()
        self._sheet_buttons: list[QToolButton] = []
        for k, (text, fn, tip) in enumerate((
                ("+ Nova", self.add_sheet, "Nova folha depois desta"), ("Duplicar", self.duplicate_sheet, "Duplicar folha"),
                ("↑ Subir", lambda: self.move_sheet(-1), "Mover a folha para cima"),
                ("↓ Descer", lambda: self.move_sheet(1), "Mover a folha para baixo"),
                ("Excluir", self.delete_sheet, "Excluir a folha"),
                ("Compactar", self.compact, "Tirar as vagas vazias de todas as folhas"))):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setToolButtonStyle(Qt.ToolButtonTextOnly)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(fn)
            self._sheet_buttons.append(b)
        self._arrange_sheet_buttons(2)
        left = QVBoxLayout()
        left.addWidget(QLabel("<b>Folhas</b>"))
        left.addWidget(self.sheet_list, 1)
        left.addLayout(self.sheet_btns)
        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setMaximumWidth(170)
        self.left_w = left_w

        self.view = SheetView(self)
        self.help = QLabel(
            "Visualizador: <b>F1</b> (ou botão <b>Filme</b>) envia a imagem do quadro, <b>F2</b> a série do "
            "quadro (inteira/intervalo) · botão direito na tira de séries: imagens-chave · arraste miniaturas "
            "para uma célula.  Na célula: esquerdo = a função escolhida (janela, mover ou zoom; botão "
            "direito ▸ Mouse), <b>alça ⠿ arrastada = trocar a imagem de lugar</b>, anotação: arrastar move, "
            "a ponta da seta estica, duplo clique no texto edita · direito arrastado = zoom, meio = mover, "
            "rodinha = corte, botão direito = girar/espelhar/copiar/colar/remover. "
            "Ctrl/Shift+clique seleciona várias · Ctrl+C / Ctrl+X / Ctrl+V · Del · duplo clique = expandir.")
        self.help.setWordWrap(True)
        self.help.setStyleSheet("color:#9a9a9a")

        split = QSplitter()
        split.addWidget(left_w)
        split.addWidget(self.view)
        split.setStretchFactor(1, 1)
        self.split = split
        root = QVBoxLayout(self)
        root.addLayout(bar1)
        root.addLayout(bar2)
        root.addWidget(split, 1)
        root.addWidget(self.help)

        self._thumb_timer = QTimer(self)
        self._thumb_timer.setSingleShot(True)
        self._thumb_timer.setInterval(400)
        self._thumb_timer.timeout.connect(self.refresh_thumbs)
        for seq, fn in ((QKeySequence.Copy, self.copy_selection), (QKeySequence.Cut, self.cut_selection),
                        (QKeySequence.Paste, lambda: self.paste()), (QKeySequence.SelectAll, self.select_all),
                        (QKeySequence.Undo, self.undo_note)):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(fn)
        self.refresh_all()

    def set_note_tool(self, key: str) -> None:
        """"" volta à função do mouse; "arrow" | "text" | "pencil" anota (uma anotação por vez)."""
        self.note_tool = key
        if key and not self.film.notes_visible:
            self.btn_notes.setChecked(True)          # anotar escondido seria desenhar no escuro
        for k, b in self.note_buttons.items():
            b.setChecked(k == key)
        for cw in self.view.cells:
            cw.note_tool = key
            cw.setCursor(Qt.CrossCursor if key else Qt.ArrowCursor)

    def _note_added(self, _cw=None) -> None:
        """Anotação pronta: o mouse volta à função que estava (janela, mover, zoom)."""
        self.set_note_tool("")

    def set_left_tool(self, key: str) -> None:
        if key not in LEFT_TOOLS:
            return
        self.left_tool = key
        self._remember("left_tool", key)
        for cw in self.view.cells:
            cw.left_tool = key
        self._update_mouse_button()
        self.set_note_tool("")

    def _update_mouse_button(self) -> None:
        self.btn_mouse.setText(f"Mouse: {LEFT_TOOLS[self.left_tool]}")

    def fill_mouse_menu(self, menu: QMenu) -> None:
        menu.clear()
        for key, nome in LEFT_TOOLS.items():
            a = QAction(nome, menu, checkable=True, checked=(key == self.left_tool and not self.note_tool))
            a.triggered.connect(lambda _c=False, k=key: self.set_left_tool(k))
            menu.addAction(a)

    def set_notes_visible(self, on: bool) -> None:
        if self._loading or self.film.notes_visible == bool(on):
            return
        self.film.notes_visible = bool(on)
        self._mark_dirty()
        self.view.rebuild()

    def _arrange_sheet_buttons(self, cols: int) -> None:
        for b in self._sheet_buttons:
            self.sheet_btns.removeWidget(b)
        for k, b in enumerate(self._sheet_buttons):
            self.sheet_btns.addWidget(b, k // cols, k % cols)

    def set_docked(self, docked: bool, expanded: bool = False) -> None:
        """No painel do visualizador: mostra ⤢/✕, coluna de folhas estreita e sem a ajuda longa."""
        self.btn_expand.setVisible(docked)
        self.btn_close.setVisible(docked)
        self.btn_expand.setText("⤡" if expanded else "⤢")
        self.help.setVisible(not docked or expanded)
        narrow = docked and not expanded
        self.left_w.setMaximumWidth(96 if narrow else 170)
        self.sheet_list.setIconSize(QSize(64, 82) if narrow else QSize(90, 115))
        self._arrange_sheet_buttons(1 if narrow else 2)
        w = self.left_w.maximumWidth()
        self.split.setSizes([w, max(300, self.split.width() - w)])

    # ------------------------------------------------------------ estado
    def _new_film(self) -> Film:
        s = self.settings
        rows, cols = parse_layout(s.get("printing.default_layout", "3×4") or "3×4")
        sheet = Sheet(rows, cols, s.get("printing.default_paper", "A4") or "A4",
                      bool(s.get("printing.default_landscape", False)))
        return Film(sheets=[sheet], overlay=s.get("printing.overlay", "min") or "min",
                    header=bool(s.get("printing.header", True)), ruler=bool(s.get("printing.ruler", True)),
                    black_page=bool(s.get("printing.black_page", False)))

    @property
    def sheet(self) -> Sheet:
        self.current = max(0, min(self.current, len(self.film.sheets) - 1))
        return self.film.sheets[self.current]

    def _mark_dirty(self) -> None:
        self.dirty = True
        self._update_name()
        self._thumb_timer.start()

    def _update_name(self) -> None:
        n = self.film.image_count()
        saved = "" if self.film_id is None else "  (salvo)" if not self.dirty else "  (alterado)"
        self.name_label.setText(f"<b>{self.film.name}</b> — {len(self.film.sheets)} folha(s), {n} imagem(ns){saved}")

    def refresh_all(self) -> None:
        self._loading = True
        sh = self.sheet
        txt = f"{sh.rows}×{sh.cols}"
        if self.layout_box.findText(txt) < 0:
            self.layout_box.insertItem(self.layout_box.count() - 1, txt)
        self.layout_box.setCurrentText(txt)
        self.paper_box.setCurrentText(sh.paper)
        self.orient_box.setCurrentIndex(1 if sh.landscape else 0)
        self.overlay_box.setCurrentIndex(max(0, self.overlay_box.findData(self.film.overlay)))
        self.chk_header.setChecked(self.film.header)
        self.chk_anon.setChecked(self.film.anonymize)
        self.chk_ruler.setChecked(self.film.ruler)
        self.chk_black.setChecked(self.film.black_page)
        self.btn_notes.setChecked(self.film.notes_visible)
        self._loading = False
        self.view.rebuild()
        self.refresh_thumbs()
        self._update_name()

    def refresh_thumbs(self) -> None:
        self.sheet_list.blockSignals(True)
        esvaziar_lista(self.sheet_list)
        for i in range(len(self.film.sheets)):
            try:
                img = render_sheet_image(self.film, i, self.src, self.cache, self.settings, dpi=14)
                pm = QPixmap.fromImage(img)
            except Exception as e:  # noqa: BLE001
                log.debug("miniatura da folha falhou: %s", e)
                pm = QPixmap(80, 110)
                pm.fill(QColor(90, 90, 90))
            sh = self.film.sheets[i]
            it = QListWidgetItem(QIcon(pm), f"{i + 1}  ({sh.rows}×{sh.cols})")
            self.sheet_list.addItem(it)
        self.sheet_list.setCurrentRow(self.current)
        self.sheet_list.blockSignals(False)

    def go_to_sheet(self, i: int) -> None:
        self.current = max(0, min(i, len(self.film.sheets) - 1))
        self.refresh_all()

    def _sheet_clicked(self, row: int) -> None:
        if row >= 0 and row != self.current:
            self.current = row
            self.selected = None
            self.selection = []
            self.refresh_all()

    # ------------------------------------------------------------ opções da folha / filme
    def _targets(self) -> list[Sheet]:
        return list(self.film.sheets) if self.all_sheets.isChecked() else [self.sheet]

    def _layout_chosen(self, _i: int) -> None:
        if self._loading:
            return
        txt = self.layout_box.currentText()
        if txt == "Outro…":
            sh = self.sheet
            txt, ok = QInputDialog.getText(self, "Layout", "Linhas × colunas (ex.: 3x5):", text=f"{sh.rows}x{sh.cols}")
            if not ok:
                self.refresh_all()
                return
        try:
            rows, cols = parse_layout(txt)
        except ValueError:
            self.refresh_all()
            return
        self.set_layout(rows, cols)

    def set_layout(self, rows: int, cols: int) -> None:
        idxs = range(len(self.film.sheets)) if self.all_sheets.isChecked() else [self.current]
        # de trás para frente: folhas novas criadas pela sobra não mudam os índices anteriores
        for i in sorted(idxs, reverse=True):
            self.film.set_layout(i, rows, cols)
        self._remember("default_layout", f"{rows}×{cols}")
        self._mark_dirty()
        self.refresh_all()

    def _paper_chosen(self, _i: int) -> None:
        if self._loading:
            return
        for sh in self._targets():
            sh.paper = self.paper_box.currentText()
        self._remember("default_paper", self.paper_box.currentText())
        self._mark_dirty()
        self.refresh_all()

    def _orient_chosen(self, i: int) -> None:
        if self._loading:
            return
        for sh in self._targets():
            sh.landscape = i == 1
        self._remember("default_landscape", i == 1)
        self._mark_dirty()
        self.refresh_all()

    def _set_opt(self, key: str, value) -> None:
        if self._loading:
            return
        setattr(self.film, key, value)
        if key in ("overlay", "header", "ruler", "black_page"):
            self._remember(key, value)
        self._mark_dirty()
        self.view.rebuild()

    def _remember(self, key: str, value) -> None:
        """A última escolha vira o padrão dos próximos filmes."""
        try:
            self.settings.set(f"printing.{key}", value)
            self.settings.save()
        except Exception as e:  # noqa: BLE001
            log.debug("não salvou preferência de filme: %s", e)

    # ------------------------------------------------------------ folhas
    def add_sheet(self) -> None:
        ref = self.sheet
        self.film.sheets.insert(self.current + 1, Sheet(ref.rows, ref.cols, ref.paper, ref.landscape))
        self.current += 1
        self._mark_dirty()
        self.refresh_all()

    def duplicate_sheet(self) -> None:
        self.film.sheets.insert(self.current + 1, copy.deepcopy(self.sheet))
        self.current += 1
        self._mark_dirty()
        self.refresh_all()

    def delete_sheet(self) -> None:
        if len(self.film.sheets) == 1:
            self.film.sheets[0].cells = [None] * self.film.sheets[0].capacity
        else:
            n = sum(1 for c in self.sheet.cells if c)
            if n and QMessageBox.question(self, "Excluir folha", f"Excluir a folha {self.current + 1} "
                                          f"({n} imagem(ns))?") != QMessageBox.Yes:
                return
            self.film.sheets.pop(self.current)
        self.selected = None
        self._mark_dirty()
        self.go_to_sheet(self.current)

    def move_sheet(self, delta: int) -> None:
        j = self.current + delta
        if 0 <= j < len(self.film.sheets):
            s = self.film.sheets
            s[self.current], s[j] = s[j], s[self.current]
            self.current = j
            self._mark_dirty()
            self.refresh_all()

    def _sheet_menu(self, pos) -> None:
        m = QMenu(self)
        for text, fn in (("Nova folha depois desta", self.add_sheet), ("Duplicar", self.duplicate_sheet),
                         ("Subir", lambda: self.move_sheet(-1)), ("Descer", lambda: self.move_sheet(1)),
                         ("Compactar (tirar vagas vazias de todas as folhas)", self.compact),
                         ("Excluir folha", self.delete_sheet)):
            m.addAction(text, fn)
        m.exec(self.sheet_list.mapToGlobal(pos))

    def compact(self) -> None:
        cells = [c for sh in self.film.sheets for c in sh.cells if c is not None]
        first = self.film.sheets[0]
        for sh in self.film.sheets:
            sh.cells = [None] * sh.capacity
        self.film.sheets = [first]
        self.film.add_cells(cells)
        self.current = 0
        self._mark_dirty()
        self.refresh_all()

    # ------------------------------------------------------------ células
    def cell_widget(self, slot: tuple[int, int]) -> FilmCell | None:
        if slot[0] != self.current or not 0 <= slot[1] < len(self.view.cells):
            return None
        return self.view.cells[slot[1]]

    def select_cell(self, cw: FilmCell, mods=None, button=None) -> None:
        """Clique: seleciona; Ctrl+clique: soma/tira; Shift+clique: intervalo. Botão direito numa
        célula já selecionada mantém a seleção (para copiar/recortar várias)."""
        slot = cw.slot
        mods = mods if mods is not None else Qt.NoModifier
        if button == Qt.RightButton and slot in self.selection:
            pass
        elif mods & Qt.ControlModifier:
            if slot in self.selection:
                self.selection.remove(slot)
            else:
                self.selection.append(slot)
            self.selected = slot
        elif mods & Qt.ShiftModifier and self.selected is not None and self.selected[0] == slot[0]:
            a, b = sorted((self.selected[1], slot[1]))
            self.selection = [(slot[0], i) for i in range(a, b + 1)]
        else:
            self.selection = [slot]
            self.selected = slot
        self._paint_selection()

    def _paint_selection(self) -> None:
        self.selection = [s for s in self.selection if s[0] == self.current]
        for w in self.view.cells:
            w.is_selected = w.slot in self.selection
            w.update()

    def select_all(self) -> None:
        self.selection = [(self.current, i) for i in range(self.sheet.capacity)]
        self.selected = self.selection[0] if self.selection else None
        self._paint_selection()

    def undo_note(self) -> None:
        """Ctrl+Z: desfaz a última anotação da célula selecionada."""
        if self.selected is not None:
            cw = self.cell_widget(self.selected)
            if cw is not None:
                cw.undo_note()

    # ------------------------------------------------------------ copiar / recortar / colar
    def _selected_cells(self) -> list[tuple[tuple[int, int], Cell]]:
        out = []
        for s, i in sorted(self.selection):
            if 0 <= s < len(self.film.sheets) and 0 <= i < self.film.sheets[s].capacity:
                c = self.film.sheets[s].cells[i]
                if c is not None:
                    out.append(((s, i), c))
        return out

    def copy_selection(self) -> int:
        cells = self._selected_cells()
        if cells:
            self.clipboard = [copy.deepcopy(c) for _slot, c in cells]
            self.status_message.emit(f"{len(cells)} imagem(ns) copiada(s). Ctrl+V cola na célula selecionada.")
        return len(cells)

    def cut_selection(self) -> int:
        cells = self._selected_cells()
        if not cells:
            return 0
        self.clipboard = [copy.deepcopy(c) for _slot, c in cells]
        for (s, i), _c in cells:
            self.film.sheets[s].cells[i] = None
        self._mark_dirty()
        self.view.rebuild()
        self.status_message.emit(f"{len(cells)} imagem(ns) recortada(s). Ctrl+V cola na célula selecionada.")
        return len(cells)

    def delete_selection(self) -> None:
        for (s, i), _c in self._selected_cells():
            self.film.sheets[s].cells[i] = None
        self._mark_dirty()
        self.view.rebuild()

    def _slot_of(self, flat: int) -> tuple[int, int]:
        for s, sh in enumerate(self.film.sheets):
            if flat < sh.capacity:
                return (s, flat)
            flat -= sh.capacity
        return (len(self.film.sheets) - 1, self.film.sheets[-1].capacity - 1)

    def paste(self, at: tuple[int, int] | None = None) -> int:
        """Cola na célula indicada (ou na selecionada). A imagem que estava ali e as seguintes andam
        para a frente até a próxima vaga vazia — nada é apagado; se faltar lugar, cria folha."""
        if not self.clipboard:
            return 0
        if at is None:
            at = min(self.selection) if self.selection else self.selected
        if at is None:
            free = self.sheet.free_slots()
            at = (self.current, free[0]) if free else (self.current, self.sheet.capacity - 1)
        cells = [copy.deepcopy(c) for c in self.clipboard]
        k = len(cells)
        flat = self._flat()
        p = self._flat_index(at)
        flat[p:p] = cells
        removed, j = 0, p + k
        while removed < k and j < len(flat):
            if flat[j] is None:
                flat.pop(j)
                removed += 1
            else:
                j += 1
        self._unflat(flat)
        slots = [self._slot_of(p + n) for n in range(k)]
        self.current = slots[0][0]
        self.selection = [sl for sl in slots if sl[0] == self.current]
        self.selected = slots[0]
        self._mark_dirty()
        self.refresh_all()
        self.status_message.emit(f"{k} imagem(ns) colada(s).")
        return k

    def _cell_changed(self, _cw: FilmCell) -> None:
        self._mark_dirty()

    def remove_cell(self, slot: tuple[int, int]) -> None:
        s, i = slot
        if 0 <= s < len(self.film.sheets) and 0 <= i < self.film.sheets[s].capacity:
            self.film.sheets[s].cells[i] = None
            self._mark_dirty()
            self.view.rebuild()

    def cell_menu(self, cw: FilmCell, global_pos) -> None:
        self.build_cell_menu(cw).exec(global_pos)

    def build_cell_menu(self, cw: FilmCell) -> QMenu:
        """Monta o menu da célula (sem exibir: assim dá para testar)."""
        self.select_cell(cw, Qt.NoModifier, Qt.RightButton)
        m = QMenu(self)
        self.fill_mouse_menu(m.addMenu("Mouse (botão esquerdo)"))
        m.addSeparator()
        n_sel = len(self._selected_cells())
        a = m.addAction(f"Copiar ({n_sel})\tCtrl+C", self.copy_selection)
        a.setEnabled(bool(n_sel))
        a = m.addAction(f"Recortar ({n_sel})\tCtrl+X", self.cut_selection)
        a.setEnabled(bool(n_sel))
        a = m.addAction(f"Colar aqui ({len(self.clipboard)})\tCtrl+V", lambda: self.paste(cw.slot))
        a.setEnabled(bool(self.clipboard))
        m.addAction("Selecionar todas desta folha\tCtrl+A", self.select_all)
        m.addSeparator()
        if cw.cell is not None:
            m.addAction("Girar 90° ↻", lambda: cw.rotate(90))
            m.addAction("Girar 90° ↺", lambda: cw.rotate(-90))
            m.addAction("Espelhar (esquerda ↔ direita)", cw.toggle_flip)
            m.addAction("Inverter cinza", cw.toggle_invert)
            wl = m.addMenu("Janela")
            cw._add_preset_actions(wl)
            if cw._img is None or not cw._img.is_color:
                cmm = m.addMenu("Cor (tabela de cores)")
                cw.add_colormap_actions(cmm, lambda k, c=cw: (c.set_colormap(k), c._changed()))
            from ipe.imaging import filters as _filters
            fm = m.addMenu("Filtro da imagem")
            for nome in _filters.ORDER:
                af = QAction(_filters.label(nome), fm, checkable=True,
                             checked=cw.state.filter == nome)
                af.triggered.connect(lambda _c=False, n=nome, c=cw: (c.set_filter(n), c._changed()))
                fm.addAction(af)
            a = QAction("Mostrar medidas e anotações", m, checkable=True, checked=cw.show_measures)
            a.toggled.connect(lambda on: (setattr(cw, "show_measures", on), cw._changed()))
            m.addAction(a)
            m.addAction("Restaurar (janela, zoom, giro)", cw.reset_cell)
            if cw.cell.notes:
                m.addAction(f"Desfazer a última anotação ({len(cw.cell.notes)})\tCtrl+Z", cw.undo_note)
                m.addAction("Apagar as anotações desta imagem", cw.clear_notes)
            m.addSeparator()
            m.addAction("Copiar janela para todas desta folha", lambda: self.copy_to_sheet(cw, window=True))
            m.addAction("Copiar janela e zoom para todas desta folha",
                        lambda: self.copy_to_sheet(cw, window=True, zoom=True))
            m.addSeparator()
            m.addAction("Abrir no visualizador", lambda: self.open_study_requested.emit(
                cw.cell.study_uid, [cw.cell.series_uid]))
            m.addAction("Remover imagem (Del)", lambda: self.remove_cell(cw.slot))
        m.addAction("Inserir vaga aqui (empurra as seguintes)", lambda: self.insert_gap(cw.slot))
        m.addAction("Remover vaga (puxa as seguintes)", lambda: self.remove_gap(cw.slot))
        return m

    def copy_to_sheet(self, cw: FilmCell, window: bool = False, zoom: bool = False) -> None:
        src = cw.cell
        if src is None:
            return
        for c in self.sheet.cells:
            if c is None or c is src:
                continue
            if window:
                c.width, c.level, c.invert, c.cmap = src.width, src.level, src.invert, src.cmap
            if zoom:
                c.zoom, c.pan_x, c.pan_y = src.zoom, src.pan_x, src.pan_y
        self._mark_dirty()
        self.view.rebuild()

    def _flat(self) -> list[Cell | None]:
        return [c for sh in self.film.sheets for c in sh.cells]

    def _unflat(self, cells: list[Cell | None]) -> None:
        k = 0
        for sh in self.film.sheets:
            sh.cells = cells[k:k + sh.capacity]
            k += sh.capacity
            sh.fit_cells()
        rest = [c for c in cells[k:] if c is not None]
        if rest:
            self.film.add_cells(rest, len(self.film.sheets) - 1)

    def _flat_index(self, slot: tuple[int, int]) -> int:
        return sum(sh.capacity for sh in self.film.sheets[:slot[0]]) + slot[1]

    def insert_gap(self, slot: tuple[int, int]) -> None:
        cells = self._flat()
        cells.insert(self._flat_index(slot), None)
        # tira a última vaga vazia (se houver) para não criar folha à toa
        for j in range(len(cells) - 1, -1, -1):
            if cells[j] is None and j != self._flat_index(slot):
                cells.pop(j)
                break
        self._unflat(cells)
        self._mark_dirty()
        self.refresh_all()

    def remove_gap(self, slot: tuple[int, int]) -> None:
        cells = self._flat()
        cells.pop(self._flat_index(slot))
        cells.append(None)
        self._unflat(cells)
        self._mark_dirty()
        self.refresh_all()

    def swap_cells(self, origem: tuple[int, int], destino: tuple[int, int]) -> bool:
        """Troca duas imagens de lugar (vale entre folhas); as outras não se mexem.

        0.76 fazia "inserir e empurrar"; a pedido dele (19/10/2026) voltou a ser troca, e o arraste
        passou a ser só pela alça ⠿, para o botão esquerdo ficar com a função do mouse."""
        if origem == destino:
            return False
        try:
            a = self.film.sheets[origem[0]].cells
            b = self.film.sheets[destino[0]].cells
            if a[origem[1]] is None:
                return False
            a[origem[1]], b[destino[1]] = b[destino[1]], a[origem[1]]
        except IndexError:
            return False
        self.selected = destino
        self.selection = [destino]
        self._mark_dirty()
        self.refresh_all()
        return True

    def _dropped(self, cw: FilmCell, kind: str, payload: str) -> None:
        target = cw.slot
        if kind == "cell":
            try:
                s, i = (int(x) for x in payload.split(","))
            except ValueError:
                return
            self.swap_cells((s, i), target)
            return
        # série (ou imagens-chave / dinâmica) vinda da tira do visualizador
        if payload.startswith("key:"):
            self.add_key_images(payload[4:], at=target)
            return
        if payload.startswith("action:"):
            return
        if payload.startswith("group:"):
            g = self.repo.series_group(int(payload[6:])) if payload[6:].isdigit() else None
            if not g or not g["series_uids"]:
                return
            payload = g["series_uids"][0]
        frames = self.src.frames(payload)
        if not frames:
            return
        m = QMenu(self)
        a_mid = m.addAction("Imagem do meio da série")
        a_rng = m.addAction("Série inteira / intervalo… (a partir desta vaga)")
        chosen = m.exec(cw.mapToGlobal(cw.rect().center()))
        if chosen is a_mid:
            self.place_cells([self._cell_for(payload, len(frames) // 2)], at=target, replace=True)
        elif chosen is a_rng:
            self.add_series_range(payload, at=target)

    # ------------------------------------------------------------ adicionar imagens (API do visualizador)
    def _cell_for(self, series_uid: str, index: int, study_uid: str = "", label: str = "", **view) -> Cell:
        frames = self.src.frames(series_uid)
        f = frames[max(0, min(index, len(frames) - 1))]
        if not study_uid or not label:
            info = self.repo.series_info(series_uid) or {}
            study_uid = study_uid or info.get("study_uid", "")
            label = label or info.get("description", "")
        return Cell(study_uid, series_uid, f.sop_uid, f.frame_index, label=label, **view)

    def place_cells(self, cells: list[Cell], at: tuple[int, int] | None = None, replace: bool = False,
                    layout: str | None = None) -> int:
        """Põe as células no filme. `at`: a partir desta vaga (a primeira substitui se `replace`);
        sem `at`: nas vagas livres a partir da folha atual. Devolve quantas entraram."""
        if not cells:
            return 0
        if self.film.image_count() == 0 and self.film.name == Film().name:
            info = self.src.study_info(cells[0].study_uid)
            self.film.name = " — ".join(x for x in (info.get("patient_name", ""), info.get("description", "")) if x) \
                or Film().name
        if layout:
            rows, cols = parse_layout(layout)
            if self.film.image_count() == 0:
                for i in range(len(self.film.sheets)):
                    self.film.set_layout(i, rows, cols)
        if at is not None:
            s, i = at
            pending = list(cells)
            if replace and pending:
                self.film.sheets[s].cells[i] = pending.pop(0)
                i += 1
            # continua pelas vagas livres a partir da posição
            sh = self.film.sheets[s]
            while pending and i < sh.capacity:
                if sh.cells[i] is None:
                    sh.cells[i] = pending.pop(0)
                i += 1
            last = self.film.add_cells(pending, s + 1) if pending else s
        else:
            if layout and self.film.image_count() > 0:
                # folhas novas com o layout pedido, depois das existentes
                rows, cols = parse_layout(layout)
                ref = self.film.sheets[-1]
                if any(ref.cells):
                    self.film.sheets.append(Sheet(rows, cols, ref.paper, ref.landscape))
                else:
                    self.film.set_layout(len(self.film.sheets) - 1, rows, cols)
                last = self.film.add_cells(cells, len(self.film.sheets) - 1)
            else:
                last = self.film.add_cells(cells, self.current)
        self.current = last
        self._mark_dirty()
        self.refresh_all()
        self.status_message.emit(f"{len(cells)} imagem(ns) no filme “{self.film.name}” "
                                 f"(folha {last + 1}/{len(self.film.sheets)})")
        return len(cells)

    def add_images(self, items: list[dict]) -> int:
        """Itens vindos do visualizador: study_uid, series_uid, index, e opcionalmente width, level,
        zoom, pan_x, pan_y, invert, label."""
        cells = []
        for it in items:
            view = {k: it[k] for k in ("width", "level", "zoom", "pan_x", "pan_y", "invert", "cmap",
                                       "rotation", "flip_h", "filter")
                    if k in it}
            cells.append(self._cell_for(it["series_uid"], int(it.get("index", 0)), it.get("study_uid", ""),
                                        it.get("label", ""), **view))
        return self.place_cells(cells)

    def add_series_range(self, series_uid: str, at: tuple[int, int] | None = None, current_index: int = 0,
                         view: dict | None = None, parent=None) -> int:
        from ipe.ui.film.dialogs import SeriesRangeDialog
        frames = self.src.frames(series_uid)
        if not frames:
            return 0
        info = self.repo.series_info(series_uid) or {}
        dlg = SeriesRangeDialog(info.get("description", "") or "Série", len(frames), current_index, parent or self)
        dlg.keep_window.setVisible(bool(view))
        if not dlg.exec():
            return 0
        v = dict(view or {}) if dlg.keep_window.isChecked() else {}
        cells = [self._cell_for(series_uid, i, info.get("study_uid", ""), info.get("description", ""), **v)
                 for i in dlg.indices()]
        return self.place_cells(cells, at=at, layout=dlg.chosen_layout())

    def add_key_images(self, study_uid: str, at: tuple[int, int] | None = None) -> int:
        keys = self.repo.key_images(study_uid)
        if not keys:
            QMessageBox.information(self, "Filme", "Este exame não tem imagens-chave.")
            return 0
        cells = []
        for k in keys:
            frames = self.src.frames(k["series_uid"])
            idx = next((i for i, f in enumerate(frames)
                        if f.sop_uid == k["sop_uid"] and f.frame_index == k["frame_index"]), None)
            if idx is not None:
                cells.append(self._cell_for(k["series_uid"], idx, study_uid))
        return self.place_cells(cells, at=at)

    # ------------------------------------------------------------ salvar / abrir
    def _patient_name(self) -> str:
        uids = self.film.study_uids()
        return self.src.study_info(uids[0]).get("patient_name", "") if uids else ""

    def save(self) -> bool:
        if self.film_id is None:
            return self.save_as()
        no_exame = self._no_exame_ao_salvar()
        self.film_id = self.repo.save_film(self.film.name, self.film.to_dict(), self.film.study_uids(),
                                           self._patient_name(), self.film_id, user=self._usuario())
        self.dirty = False
        self._update_name()
        self.status_message.emit(self._msg_salvo(no_exame))
        return True

    def _msg_salvo(self, no_exame: str) -> str:
        n = self.film.name
        if no_exame == "igual":
            return f"Filme “{n}” salvo (no exame já estava igual)."
        if no_exame == "substituiu":
            return f"Filme “{n}” salvo e gravado no exame (substituiu a cópia anterior)."
        if no_exame == "gravado":
            return f"Filme “{n}” salvo e gravado no exame."
        return f"Filme “{n}” salvo."

    def save_as(self, name: str | None = None) -> bool:
        if name is None:
            name, ok = QInputDialog.getText(self, "Salvar filme", "Nome do filme:", text=self.film.name)
            if not ok or not name.strip():
                return False
        self.film.name = name.strip()
        self.film_id = None
        no_exame = self._no_exame_ao_salvar(nome_novo=True)
        if no_exame:
            self.status_message.emit(self._msg_salvo(no_exame))
        self.film_id = self.repo.save_film(self.film.name, self.film.to_dict(), self.film.study_uids(),
                                           self._patient_name(), user=self._usuario())
        from ipe.auth import session as S
        S.audit(self.repo, "salvar filme", self.film.name or "",
                study_uid=(self.film.study_uids() or [""])[0])
        self.dirty = False
        self.refresh_all()
        self.status_message.emit(f"Filme “{self.film.name}” salvo.")
        return True

    def _confirm_discard(self) -> bool:
        if not self.dirty or self.film.image_count() == 0:
            return True
        r = QMessageBox.question(self, "Filme", f"Salvar as alterações em “{self.film.name}”?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def new_film(self) -> None:
        if not self._confirm_discard():
            return
        self.film, self.film_id, self.dirty, self.current, self.selected = self._new_film(), None, False, 0, None
        self.selection = []
        self.src.clear()
        self.refresh_all()

    def open_saved(self, study_uid: str | None = None) -> None:
        from ipe.ui.film.dialogs import FilmsDialog
        dlg = FilmsDialog(self.repo, study_uid if isinstance(study_uid, str) else None, self)
        if dlg.exec() and dlg.chosen is not None:
            self.load_film(dlg.chosen)

    def load_film(self, film_id: int) -> bool:
        if not self._confirm_discard():
            return False
        data = self.repo.film_data(film_id)
        if data is None:
            return False
        self.film = Film.from_dict(data)
        self.film_id, self.dirty, self.current, self.selected = film_id, False, 0, None
        self.selection = []
        self.src.clear()
        self.refresh_all()
        return True

    # ------------------------------------------------------------ saídas
    def _check_not_empty(self) -> bool:
        if self.film.image_count() == 0:
            QMessageBox.information(self, "Filme", "O filme está vazio. Envie imagens do visualizador primeiro.")
            return False
        return True

    @staticmethod
    def _usuario() -> str:
        from ipe.auth import session as S
        return S.get().username or ""

    def _after_print(self, destino: str = "") -> None:
        """Conta a impressão no filme (painel de filmes, 0.77): quem, quando e para onde.

        Filme impresso sem ter sido salvo é salvo agora, com o nome que tem: senão a impressão
        não existiria para o painel, e a % de filmes impressos sairia menor do que é."""
        if self.film_id is None and self.film.image_count():
            self.film_id = self.repo.save_film(self.film.name, self.film.to_dict(),
                                               self.film.study_uids(), self._patient_name(),
                                               user=self._usuario())
            self.dirty = False
            self._update_name()
        if self.film_id is not None:
            self.repo.mark_film_printed(self.film_id, self._usuario(), destino)
            try:                         # 0.84: histórico de envios
                self.repo.add_send("film", self.film_id, destino, self._usuario(), "compositor")
            except Exception:  # noqa: BLE001
                pass

    def sheet_images(self, dpi: float, indices: list[int] | None = None, grayscale: bool = False):
        for i in (indices if indices is not None else range(len(self.film.sheets))):
            yield i, render_sheet_image(self.film, i, self.src, self.cache, self.settings, dpi, grayscale)

    @staticmethod
    def _page_layout(sheet: Sheet):
        from PySide6.QtCore import QMarginsF
        from PySide6.QtGui import QPageLayout, QPageSize
        w, h, _id = PAPERS.get(sheet.paper, PAPERS["A4"])
        size = QPageSize(QSizeF(w, h), QPageSize.Millimeter, sheet.paper, QPageSize.ExactMatch)
        return QPageLayout(size, QPageLayout.Landscape if sheet.landscape else QPageLayout.Portrait,
                           QMarginsF(0, 0, 0, 0))

    def _paint_pages(self, device, dpi: float, indices: list[int] | None = None) -> None:
        """Desenha as folhas (todas, ou as de `indices`) num QPrinter/QPdfWriter (uma página por folha)."""
        painter = None
        try:
            for i in (indices if indices is not None else range(len(self.film.sheets))):
                sheet = self.film.sheets[i]
                device.setPageLayout(self._page_layout(sheet))
                if painter is None:
                    painter = QPainter(device)
                    if not painter.isActive():
                        raise RuntimeError("Não foi possível iniciar a impressão.")
                else:
                    device.newPage()
                img = render_sheet_image(self.film, i, self.src, self.cache, self.settings, dpi)
                target = QRectF(painter.viewport())
                # mantém a proporção da folha dentro da área imprimível
                k = min(target.width() / img.width(), target.height() / img.height())
                w, h = img.width() * k, img.height() * k
                painter.drawImage(QRectF(target.x() + (target.width() - w) / 2,
                                         target.y() + (target.height() - h) / 2, w, h), img)
        finally:
            if painter is not None:
                painter.end()

    # ------------------------------------------------------------ 0.99.6: as janelas Salvar e Imprimir
    def save_dialog(self) -> bool:
        from ipe.ui.film.dialogs import SalvarFilmeDialog
        dlg = SalvarFilmeDialog(self.film.name, self.film_id is not None, self.chk_no_exame.isChecked(), self)
        if not dlg.exec():
            return False
        self.chk_no_exame.setChecked(dlg.no_exame())
        if dlg.acao == "novo" or self.film_id is None:
            return self.save_as(dlg.nome())
        if dlg.nome() != self.film.name:
            self.film.name = dlg.nome()
        return self.save()

    def imprimir(self) -> None:
        from ipe.auth import session as S
        if not S.require("print", self) or not self._check_not_empty():
            return
        from ipe.ui.film.dialogs import ImprimirFilmeDialog
        dlg = ImprimirFilmeDialog(self.settings, self.local_ae_fn(), len(self.film.sheets), self.current, self)
        if not dlg.exec():
            return
        folhas, d = dlg.folhas(), dlg.destino()
        if d == "local":
            self.print_dialog(folhas)
        elif d == "pdf":
            self.export_pdf(indices=folhas)
        elif d == "imagem":
            self.export_images(dpi=int(self.settings.get("printing.image_dpi", 150) or 150), indices=folhas,
                               fmt=str(self.settings.get("printing.image_fmt", "PNG") or "PNG"))
        else:
            self.enviar_dicom(dlg.impressora_dicom(), folhas)

    def print_dialog(self, indices: list[int] | None = None) -> None:
        from ipe.auth import session as S
        if not S.require("print", self):
            return None
        S.audit(self.repo, "imprimir", "print_dialog: " + (self.film.name or ""))
        if not self._check_not_empty():
            return
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageLayout(self._page_layout(self.film.sheets[(indices or [0])[0]]))
        printer.setDocName(self.film.name)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QPrintDialog.Accepted:
            return
        dpi = min(300, max(150, printer.resolution()))
        try:
            self._paint_pages(printer, dpi, indices)
        except Exception as e:  # noqa: BLE001
            log.exception("impressão")
            QMessageBox.critical(self, "Imprimir", f"Falha ao imprimir:\n{e}")
            return
        self._after_print(f"Impressora do Windows: {printer.printerName()}" if printer.printerName()
                          else "Impressora do Windows")
        self.status_message.emit(f"Filme enviado para {printer.printerName() or 'a impressora'}.")

    def _default_dir(self) -> str:
        return self.settings.get("printing.last_dir", "") or str(Path.home())

    def _safe_name(self) -> str:
        return "".join(ch if ch.isalnum() or ch in " -_" else "_" for ch in self.film.name).strip() or "filme"

    def export_pdf(self, path: str | None = None, indices: list[int] | None = None) -> str | None:
        from ipe.auth import session as S
        if not S.require("print", self):
            return None
        S.audit(self.repo, "imprimir", "export_pdf: " + (self.film.name or ""))
        if not self._check_not_empty():
            return None
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "Salvar PDF",
                                                  str(Path(self._default_dir()) / f"{self._safe_name()}.pdf"),
                                                  "PDF (*.pdf)")
            if not path:
                return None
        from PySide6.QtGui import QPdfWriter
        dpi = int(self.settings.get("printing.pdf_dpi", 200) or 200)
        writer = QPdfWriter(path)
        writer.setResolution(dpi)
        writer.setTitle(self.film.name)
        writer.setCreator("Ipê")
        self._paint_pages(writer, dpi, indices)
        self.settings.set("printing.last_dir", str(Path(path).parent))
        self.status_message.emit(f"PDF salvo: {path}")
        return path

    def export_images(self, path: str | None = None, dpi: int | None = None, indices: list[int] | None = None,
                      fmt: str = "") -> list[str]:
        from ipe.auth import session as S
        if not S.require("print", self):
            return None
        S.audit(self.repo, "imprimir", "export_images: " + (self.film.name or ""))
        if not self._check_not_empty():
            return []
        if not path:
            ext = ".jpg" if fmt.upper() in ("JPG", "JPEG") else ".png"
            filtros = "JPEG (*.jpg);;PNG (*.png)" if ext == ".jpg" else "PNG (*.png);;JPEG (*.jpg)"
            path, flt = QFileDialog.getSaveFileName(
                self, "Salvar folhas como imagem", str(Path(self._default_dir()) / f"{self._safe_name()}{ext}"),
                filtros)
            if not path:
                return []
            if Path(path).suffix.lower() not in (".png", ".jpg", ".jpeg"):
                path += ".jpg" if "JPEG" in flt else ".png"
        if dpi is None:
            opts = ["150", "200", "300", "96"]
            last = str(self.settings.get("printing.image_dpi", 150))
            txt, ok = QInputDialog.getItem(self, "Resolução", "Pontos por polegada (dpi):", opts,
                                           opts.index(last) if last in opts else 0, True)
            if not ok:
                return []
            dpi = max(50, min(600, int(txt)))
            self.settings.set("printing.image_dpi", dpi)
        p = Path(path)
        out = []
        quais = indices if indices is not None else list(range(len(self.film.sheets)))
        for i, img in self.sheet_images(dpi, quais):
            target = p if len(quais) == 1 else p.with_name(f"{p.stem}_{i + 1:02d}{p.suffix}")
            img.save(str(target), quality=92)
            out.append(str(target))
        self.settings.set("printing.last_dir", str(p.parent))
        self.status_message.emit(f"{len(out)} imagem(ns) salva(s) em {p.parent}")
        return out

    def dicom_print(self) -> None:
        from ipe.auth import session as S
        if not S.require("print", self):
            return None
        if not self._check_not_empty():
            return
        from ipe.ui.film.dialogs import DicomPrintDialog
        dlg = DicomPrintDialog(self.settings, self.local_ae_fn(), len(self.film.sheets), self.current, self)
        if not dlg.exec():
            return
        idx = [self.current] if dlg.only_current() else list(range(len(self.film.sheets)))
        self.enviar_dicom(dlg.config(), idx)

    def enviar_dicom(self, cfg, idx: list[int]) -> None:
        """Manda as folhas `idx` para a impressora DICOM `cfg` em segundo plano."""
        if cfg is None:
            return
        from ipe.auth import session as S
        S.audit(self.repo, "imprimir", "dicom_print: " + (self.film.name or ""))
        self._destino_dicom = f"Impressora DICOM: {cfg.name}"
        pages = self.dicom_pages(cfg, idx)
        self.status_message.emit(f"Enviando {len(pages)} folha(s) para {cfg.name}…")
        local = self.local_ae_fn()

        def run():
            from ipe.printing.dicom_print import dicom_print
            try:
                self._bridge.done.emit(dicom_print(cfg, pages, local), None)
            except Exception as e:  # noqa: BLE001
                self._bridge.done.emit(None, e)
        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------------ também no exame (caixa do Salvar)
    def _assinatura(self) -> str:
        """Impressão digital do conteúdo do filme (sem o registro da cópia no exame)."""
        import hashlib
        import json
        d = self.film.to_dict()
        d.pop("no_exame", None)
        return hashlib.sha1(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()

    def perguntar_substituir_no_exame(self) -> str | None:
        """"substituir", "nova" ou None (não gravar no exame agora). Separado para testar."""
        caixa = QMessageBox(self)
        caixa.setWindowTitle("Filme no exame")
        caixa.setText("Este filme já foi gravado no exame, e mudou desde então.\n\n"
                      "Substituir a cópia anterior no exame, ou guardar as duas?")
        b_sub = caixa.addButton("Substituir a anterior", QMessageBox.AcceptRole)
        b_nova = caixa.addButton("Guardar as duas", QMessageBox.ActionRole)
        caixa.addButton("Agora não", QMessageBox.RejectRole)
        caixa.exec()
        if caixa.clickedButton() is b_sub:
            return "substituir"
        if caixa.clickedButton() is b_nova:
            return "nova"
        return None

    def _no_exame_ao_salvar(self, nome_novo: bool = False) -> str:
        """Com a caixa "também no exame" marcada, grava a cópia no exame. Devolve o que houve:
        "gravado", "substituiu", "igual" (não mudou, não gravou de novo) ou "" (não gravou)."""
        if not self.chk_no_exame.isChecked() or self.film.image_count() == 0:
            return ""
        ant = self.film.no_exame or {}
        anteriores = [u for u in ant.get("series", []) if u and self.repo.instances_for_series(u)]
        assinatura = self._assinatura()
        if anteriores and ant.get("assinatura") == assinatura and not nome_novo:
            return "igual"
        escolha = "nova"
        if anteriores and not nome_novo:
            escolha = self.perguntar_substituir_no_exame()
            if escolha is None:
                return ""
        res = self.salvar_no_exame(avisar_fim=False)
        if res is None:
            return ""
        if escolha == "substituir":
            storage = getattr(self, "storage_root", None)
            for u in anteriores:
                try:
                    self.repo.delete_series(u, storage)
                except Exception as e:  # noqa: BLE001
                    log.exception("delete previous film copy in study")
                    self.avisar(f"O filme novo foi gravado no exame, mas a cópia anterior não pôde "
                                f"ser apagada:\n{e}")
                    break
        from datetime import datetime as _dt
        self.film.no_exame = {"series": [u for u in (res.serie_filme, res.serie_sr, res.serie_folhas) if u],
                              "study_uid": res.study_uid, "assinatura": assinatura,
                              "em": _dt.now().isoformat(timespec="seconds")}
        return "substituiu" if escolha == "substituir" else "gravado"

    def salvar_no_exame(self, avisar_fim: bool = True):
        """O filme vira três séries do exame da primeira imagem (formato da AW). Devolve o resultado."""
        from ipe.auth import session as S
        if not self._check_not_empty():
            return None
        storage = getattr(self, "storage_root", None)
        db = getattr(self.repo, "db", None)
        if storage is None or db is None:
            self.avisar("Este banco não aceita gravar séries novas daqui.")
            return None
        from PySide6.QtWidgets import QApplication
        from ipe.ui.film.salvar_dicom import salvar_no_exame
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            res = salvar_no_exame(self.film, self.src, self.cache, self.settings, db, storage, self.repo)
        except Exception as e:  # noqa: BLE001
            log.exception("salvar o filme no exame")
            QApplication.restoreOverrideCursor()
            self.avisar(f"Não consegui gravar o filme no exame:\n{e}")
            return None
        QApplication.restoreOverrideCursor()
        S.audit(self.repo, "filme no exame", self.film.name or "", study_uid=res.study_uid)
        self.ultimo_no_exame = res
        self.saved_to_study.emit(res.study_uid)
        msg = (f"Filme gravado no exame: {res.folhas} folha(s) e {res.imagens} imagem(ns).\n"
               f"Séries {res.numero} (SR e imagens) e {res.numero + 1} (folhas prontas).")
        self.status_message.emit(msg.replace("\n", " "))
        if avisar_fim:
            self.avisar(msg)
        return res

    def avisar(self, msg: str) -> None:
        QMessageBox.information(self, "Filme no exame", msg)

    def dicom_pages(self, cfg, indices: list[int]):
        from ipe.printing.dicom_print import PageImage
        pages = []
        for i, img in self.sheet_images(cfg.dpi, indices, grayscale=not cfg.color):
            sheet = self.film.sheets[i]
            if cfg.color:
                img = img.convertToFormat(img.Format.Format_RGB888)
                arr = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())
                arr = arr[:, :img.width() * 3].reshape(img.height(), img.width(), 3).copy()
            else:
                arr = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.bytesPerLine())
                arr = arr[:, :img.width()].copy()
            pages.append(PageImage(arr, PAPERS.get(sheet.paper, PAPERS["A4"])[2], sheet.landscape))
        return pages

    def _dicom_done(self, res, err) -> None:
        if err is not None:
            QMessageBox.critical(self, "Impressora DICOM", str(err))
            return
        self._after_print(getattr(self, "_destino_dicom", "Impressora DICOM"))
        extra = f" (avisos: {'; '.join(res.warnings)})" if res.warnings else ""
        self.status_message.emit(f"{res.pages} folha(s) impressa(s){extra}.")
        QMessageBox.information(self, "Impressora DICOM", f"{res.pages} folha(s) enviada(s) para impressão.{extra}")
