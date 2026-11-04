"""Browser do banco local: listas de casos, busca, estudos, séries e comentários."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton, QSplitter, QTableView,
    QTextBrowser, QToolButton, QVBoxLayout, QWidget,
)

from ipe.db.repository import Repository, StudyRow
from ipe.ui.dialogs import TextInputDialog
from ipe.ui.table_filter import FilterHeader, FilterProxy, ValueFilterDialog
from ipe.ui.tabelas import esvaziar_lista, colunas_ajustaveis

# todas as colunas possíveis: (chave, título, tipo). O usuário escolhe quais aparecem e a ordem.
COLUMNS = [
    ("patient_name", "Paciente", "text"), ("patient_id", "ID", "text"), ("birth_date", "Nascimento", "date"),
    ("sex", "Sexo", "text"), ("patient_age", "Idade", "text"),
    ("study_date", "Data", "date"), ("study_time", "Hora", "time"), ("modalities", "Mod.", "text"),
    ("description", "Descrição", "text"), ("body_part", "Região", "text"), ("accession", "Accession", "text"),
    ("num_series", "Séries", "int"), ("num_images", "Imagens", "int"), ("size_mb", "Tamanho (MB)", "float"),
    ("institution", "Instituição", "text"), ("referring", "Solicitante", "text"),
    ("operators", "Operador (técnico)", "text"), ("station", "Estação", "text"), ("device", "Aparelho", "text"),
    ("origin", "Origem", "origin"), ("date_added", "Adicionado em", "datetime"),
    ("last_accessed", "Último acesso", "datetime"), ("locked", "Protegido", "bool"),
    ("key_images", "Imagens-chave", "int"), ("measured", "Imagens c/ medida", "int"),
    ("num_groups", "Dinâmicas", "int"), ("lists", "Listas", "text"), ("comment", "Comentário", "text"),
    ("report", "Laudo", "text"), ("banco", "Banco", "banco"), ("ia", "IA", "ia"),
    ("case_n", "Nº", "int"), ("case_name", "Caso (lista)", "text"),
]
LIST_ONLY = ["case_n", "case_name"]          # aparecem sozinhas quando uma lista está aberta
DEFAULT_COLUMNS = ["patient_name", "patient_id", "birth_date", "study_date", "modalities", "description",
                   "accession", "num_series", "num_images", "report", "ia"]
SENSITIVE = {"patient_name", "patient_id", "birth_date", "accession", "institution", "referring", "operators"}
ORIGINS = {"import": "importado", "received": "recebido", "retrieved": "baixado", "prefetch": "pré-busca",
           "anonymized": "anonimizado"}
KEY_INDEX = {c[0]: i for i, c in enumerate(COLUMNS)}


def fmt_date(d: str) -> str:
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 and d.isdigit() else d


# marcas ao lado do nome do paciente (mesma ideia do ✎ do comentário)
MARK_COMMENT = "✎"
MARK_DRAFT = "⌛"
MARK_SIGNED = "✔"
MARK_AMENDED = "✔↻"
MARK_FILM = "▦"
MARK_IA = "✦"            # 0.99.32: o exame tem resultado de IA (segmentação, coluna, implante…)
MARK_IA_RODANDO = "⚙"    # uma IA está na fila ou rodando neste exame agora
MARK_TIPS = {MARK_COMMENT: "tem comentário", MARK_DRAFT: "laudo em rascunho",
             MARK_SIGNED: "laudo assinado", MARK_AMENDED: "laudo retificado",
             MARK_FILM: "tem filme salvo", MARK_IA: "tem aplicação de IA", MARK_IA_RODANDO: "IA rodando ou na fila"}
REPORT_MARKS = {"rascunho": MARK_DRAFT, "assinado": MARK_SIGNED, "retificado": MARK_AMENDED}


def _mark_list(r) -> list[str]:
    marcas = []
    if getattr(r, "has_comment", False):
        marcas.append(MARK_COMMENT)
    marca = REPORT_MARKS.get(getattr(r, "report", "") or "")
    if marca:
        marcas.append(marca)
    if getattr(r, "has_film", False):
        marcas.append(MARK_FILM)
    if getattr(r, "ia", ""):
        marcas.append(MARK_IA)
    if _ia_rodando(r.study_uid if hasattr(r, "study_uid") else ""):
        marcas.append(MARK_IA_RODANDO)
    return marcas


def _ia_rodando(study_uid: str) -> list:
    try:
        from ipe.ai import tarefas as TA
        return TA.REGISTRO.ativas(study_uid) if study_uid else []
    except Exception:  # noqa: BLE001
        return []


def _texto_ia(r) -> str:
    """Coluna IA: o que já foi feito e o que está rodando."""
    feitas = getattr(r, "ia", "") or ""
    rod = _ia_rodando(getattr(r, "study_uid", ""))
    partes = ([f"{MARK_IA} {feitas}"] if feitas else []) + \
        [f"{MARK_IA_RODANDO} {t.ferramenta.lower()} ({'na fila' if t.estado == 'fila' else 'rodando'})" for t in rod]
    return "  ".join(partes)


def _marks(r) -> str:
    return " ".join(_mark_list(r))


def _marks_tip(r) -> str:
    partes = []
    for m in _mark_list(r):
        if m == MARK_IA:
            partes.append(f"{m} IA: {getattr(r, 'ia', '')}")
        elif m == MARK_IA_RODANDO:
            partes.append(f"{m} IA: " + ", ".join(f"{t.ferramenta.lower()} ({'na fila' if t.estado == 'fila' else 'rodando'})"
                                                     for t in _ia_rodando(r.study_uid)))
        else:
            partes.append(f"{m} {MARK_TIPS.get(m, '')}".strip())
    return " · ".join(partes)


class StudyTableModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self.rows: list[StudyRow] = []
        self.anonymize = False
        self.case_names: dict[str, str] = {}      # modo reunião: nome amigável no lugar do paciente
        self.settings = None                      # para o perfil de ocultação (0.99.42)

    def set_rows(self, rows: list[StudyRow]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section][1]
        return None

    def perfil(self) -> str:
        from ipe.core import mascara as MK
        return MK.perfil_de(self.settings) if not self.case_names else "oculto"

    def data(self, index, role=Qt.DisplayRole):
        r = self.rows[index.row()]
        key, _label, kind = COLUMNS[index.column()]
        if role in (Qt.DisplayRole, Qt.UserRole):
            v = getattr(r, key, "")
            perfil = self.perfil() if self.anonymize and not self.case_names.get(r.study_uid) else "oculto"
            if self.anonymize and perfil != "oculto" and key in SENSITIVE | {"study_date"}:
                # 0.99.42: perfil de ocultação — pseudônimo, datas deslocadas ou sem datas
                from ipe.core import mascara as MK
                info = {"patient_name": r.patient_name, "patient_id": getattr(r, "patient_id", ""),
                        "study_date": getattr(r, "study_date", "")}
                if key in ("patient_name", "patient_id", "study_date"):
                    mv = MK.mascarar_info(info, perfil).get(key, "")
                    if role == Qt.UserRole or not mv:
                        return mv or ("•••" if key != "study_date" else "")
                    return fmt_date(mv) if key == "study_date" else mv
                return "•••"
            if self.anonymize and key == "patient_name":
                return self.case_names.get(r.study_uid) or "Paciente oculto"
            if self.anonymize and key in SENSITIVE:
                return "•••"
            if role == Qt.UserRole:
                return v                                  # ordenação pelo valor bruto
            if kind == "date":
                return fmt_date(v)
            if kind == "time":
                return f"{v[0:2]}:{v[2:4]}" if len(v) >= 4 and v[:4].isdigit() else v
            if kind == "datetime":
                return f"{v[6:8]}/{v[4:6]}/{v[:4]} {v[8:10]}:{v[10:12]}" if len(v) >= 12 else ""
            if kind == "bool":
                return "🔒" if v else ""
            if kind == "origin":
                return ORIGINS.get(v, v)
            if kind == "banco":
                from ipe.db import banco as B
                return B.rotulo_do_banco(r)
            if kind == "ia":
                return _texto_ia(r)
            if kind in ("int", "float") and not v:
                return ""
            if key == "patient_name":
                marcas = _marks(r)
                return f"{v}  {marcas}" if marcas else v
            return v
        if role == Qt.TextAlignmentRole and kind in ("int", "float"):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.FontRole and r.unread:
            f = QFont()
            f.setBold(True)
            return f
        if role == Qt.ToolTipRole and key == "patient_name":
            dica = _marks_tip(r)
            if dica:
                return dica
        return None

    def row(self, i: int) -> StudyRow:
        return self.rows[i]

    # arrastar exames da tabela para uma lista (árvore à esquerda)
    def flags(self, index):
        f = super().flags(index)
        return f | Qt.ItemIsDragEnabled if index.isValid() else f

    def mimeTypes(self):  # noqa: N802
        from ipe.ui.caselists import STUDIES_MIME
        return [STUDIES_MIME]

    def mimeData(self, indexes):  # noqa: N802
        from PySide6.QtCore import QMimeData
        from ipe.ui.caselists import STUDIES_MIME
        uids = []
        for i in indexes:
            u = self.rows[i.row()].study_uid
            if u not in uids:
                uids.append(u)
        md = QMimeData()
        md.setData(STUDIES_MIME, ",".join(uids).encode())
        return md


class Browser(QWidget):
    open_study = Signal(str)
    compare_studies = Signal(list)                 # abrir vários juntos, para comparar
    import_requested = Signal()
    send_requested = Signal(list, int, object)     # estudos, nó, identidade (ou None)
    send_series_requested = Signal(str, list, int, object)   # estudo, séries, nó, identidade
    copy_to_location = Signal(list, str)          # estudos, id do local de destino
    open_series = Signal(str, list)                # estudo, séries escolhidas
    choose_series = Signal(str)                    # abrir o diálogo de escolha de séries
    fix_tags_requested = Signal(str)               # corrigir as tags de um exame
    film_requested = Signal(dict)                  # filme: imagens-chave, filmes salvos
    meeting_requested = Signal(int, int)           # lista, caso inicial
    open_case = Signal(str, list)                  # abrir exame (séries escolhidas)
    import_list_requested = Signal(object)         # pasta de destino (ou None)
    report_requested = Signal(str)                 # abrir o laudo do estudo
    series_changed = Signal()                      # série oculta ou apagada: quem mostra séries recarrega
    segmentacao_pronta = Signal(str, object)       # estudo, saída da segmentação de órgãos (0.98)
    status_message = Signal(str)                   # 0.99.27: recado para a barra de estado

    def __init__(self, repo: Repository, storage_root, parent=None, settings=None):
        super().__init__(parent)
        self.repo = repo
        self.settings = settings
        self.storage_root = storage_root
        self.current_list: int | None = None
        self.other_locations: list[tuple[str, str]] = []   # (id, nome) dos outros locais, para copiar

        # --- barra de busca
        self.search = QLineEdit(placeholderText="Buscar nome, ID, accession, descrição (use | para vários)")
        self.search.returnPressed.connect(self.refresh)
        self.modality = QComboBox()
        self.modality.addItems(["Todas", "CT", "MR", "MG", "US", "CR", "DX", "PT", "NM", "XA", "OT"])
        self.period = QComboBox()
        self.period.addItems(["Qualquer data", "Hoje", "Últimos 7 dias", "Últimos 30 dias",
                              "Último ano"])
        for w in (self.modality, self.period):
            w.currentIndexChanged.connect(self.refresh)
        btn_search = QPushButton("Buscar")
        btn_search.clicked.connect(self.refresh)
        btn_import = QPushButton("Importar…")
        btn_import.clicked.connect(self.import_requested.emit)
        btn_cols = QPushButton("Colunas ▾")
        btn_cols.setToolTip("Escolher as colunas da lista (também pelo botão direito no cabeçalho)")
        btn_cols.clicked.connect(lambda: self.columns_menu().exec(btn_cols.mapToGlobal(btn_cols.rect().bottomLeft())))
        self.btn_clear_filters = QPushButton("Limpar filtros")
        self.btn_clear_filters.setToolTip("Remove os filtros das colunas")
        self.btn_clear_filters.clicked.connect(self.clear_filters)
        self.btn_clear_filters.setEnabled(False)
        top = QHBoxLayout()
        top.addWidget(self.search, 1)
        top.addWidget(self.modality)
        top.addWidget(self.period)
        top.addWidget(btn_search)
        top.addWidget(btn_cols)
        top.addWidget(self.btn_clear_filters)

        # --- listas de casos (esquerda)
        from ipe.ui.caselists import ListTree
        self.tree = ListTree(repo)
        self.tree.setMinimumWidth(170)
        self.tree.list_selected.connect(self._list_selected)
        self.tree.studies_dropped.connect(self._studies_dropped)
        self.tree.changed.connect(self.refresh)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.tree.itemDoubleClicked.connect(lambda it, _c: self.edit_list(it.data(0, Qt.UserRole)))
        btn_new_list = QPushButton("+ Lista")
        btn_new_list.setToolTip("Nova lista de casos (dentro da pasta selecionada)")
        btn_new_list.clicked.connect(lambda: self._new_list())
        btn_new_folder = QPushButton("+ Pasta")
        btn_new_folder.clicked.connect(lambda: self._new_list(folder=True))
        self.btn_meeting = QPushButton("▶ Modo reunião")
        self.btn_meeting.setToolTip("Apresentar a lista selecionada: casos um a um, dados do paciente ocultos")
        self.btn_meeting.clicked.connect(lambda: self._start_meeting(self.tree.current_id()))
        self.btn_meeting.setEnabled(False)
        lbtns = QHBoxLayout()
        lbtns.addWidget(btn_new_list)
        lbtns.addWidget(btn_new_folder)
        left = QVBoxLayout()
        self._left_layout = left                     # o painel "Locais" entra acima (add_side_panel)
        left.addWidget(QLabel("<b>Banco de casos</b>"))
        left.addWidget(self.tree, 1)
        left.addLayout(lbtns)
        left.addWidget(self.btn_meeting)
        left_w = QWidget()
        left_w.setLayout(left)
        # 0.99.29: os painéis dos lados recolhem para uma tira na borda, como no Weasis
        from ipe.ui.painel_recolhivel import PainelRecolhivel
        self.painel_esq = PainelRecolhivel("Locais e listas", left_w, "esq")
        self.painel_esq.set_max_aberto(280)
        self.painel_esq.recolher(not bool(self._settings_get("browser.show_lists", True)), salvar=False)
        self.painel_esq.mudou.connect(self._painel_esq_mudou)
        self.lists_panel = self.painel_esq

        # --- tabela de estudos
        self.model = StudyTableModel()
        self.model.settings = self.settings
        self.proxy = FilterProxy([c[2] for c in COLUMNS])
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(Qt.UserRole)
        self.table = QTableView()
        self.filter_header = FilterHeader(self.table)
        self.table.setHorizontalHeader(self.filter_header)
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setDragEnabled(True)                  # arrastar exames para uma lista
        self.table.setDragDropMode(QAbstractItemView.DragOnly)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._open_selected)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._study_menu)
        hh = self.table.horizontalHeader()
        colunas_ajustaveis(self.table)
        hh.setSectionsMovable(True)                   # arrastar o título muda a ordem
        hh.setContextMenuPolicy(Qt.CustomContextMenu)
        hh.customContextMenuRequested.connect(self._header_menu)
        hh.sectionMoved.connect(lambda *_: self._save_columns())
        hh.sectionResized.connect(lambda *_: self._save_widths_later())
        self._widths_timer = None
        self._applying_columns = False
        self.filter_header.set_filter_boxes(len(COLUMNS))
        self.filter_header.filter_changed.connect(self._text_filter_changed)
        self.apply_columns()

        # --- séries e comentários (direita)
        self.series_list = QListWidget()
        self.series_list.setResizeMode(QListWidget.Adjust)
        self.series_list.setMovement(QListWidget.Static)
        self.series_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.series_list.itemDoubleClicked.connect(self._open_series_item)
        self.series_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.series_list.customContextMenuRequested.connect(self._series_menu)
        QShortcut(QKeySequence(Qt.Key_Delete), self.series_list,
                  activated=self._delete_series, context=Qt.WidgetShortcut)
        self.series_view = str(self._settings_get("browser.series_view", "icone") or "icone")
        self.mostrar_ocultas = False
        self.btn_series_view = QToolButton()
        self.btn_series_view.setAutoRaise(True)
        self.btn_series_view.clicked.connect(
            lambda: self.set_series_view("lista" if self.series_view == "icone" else "icone"))
        self.btn_ocultas = QToolButton()
        self.btn_ocultas.setAutoRaise(True)
        self.btn_ocultas.setCheckable(True)
        self.btn_ocultas.setText("Ocultas")
        self.btn_ocultas.setToolTip("Mostrar também as séries que você ocultou")
        self.btn_ocultas.toggled.connect(self._ocultas_toggled)
        self.btn_ocultas.setVisible(False)
        cab = QHBoxLayout()
        cab.addWidget(QLabel("<b>Séries</b>"))
        cab.addStretch(1)
        cab.addWidget(self.btn_ocultas)
        cab.addWidget(self.btn_series_view)
        self.comments = QTextBrowser()
        btn_comment = QPushButton("Adicionar comentário")
        btn_comment.clicked.connect(self._add_comment)
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.addLayout(cab)
        right.addWidget(self.series_list, 3)
        right.addWidget(QLabel("<b>Comentários</b>"))
        right.addWidget(self.comments, 2)
        right.addWidget(btn_comment)
        right_w = QWidget()
        right_w.setLayout(right)
        self.painel_dir = PainelRecolhivel("Séries e comentários", right_w, "dir", self.settings,
                                           "browser.painel_dir_recolhido")
        self.painel_dir.mudou.connect(lambda on: self._painel_mudou(2, on))

        split = QSplitter()
        split.setChildrenCollapsible(False)
        split.addWidget(self.painel_esq)
        split.addWidget(self.table)
        split.addWidget(self.painel_dir)
        split.setStretchFactor(1, 3)
        split.setStretchFactor(2, 1)
        split.setSizes([250, 850, 340])
        self.split = split
        self._larguras = {0: 250, 2: 340}         # para voltar ao tamanho de antes ao abrir
        for i, painel in ((0, self.painel_esq), (2, self.painel_dir)):
            if painel.recolhido:                  # já abre recolhido (como ficou da última vez)
                self._painel_mudou(i, True)

        self.count_label = QLabel()
        root = QVBoxLayout(self)
        root.addLayout(top)
        root.addWidget(split, 1)
        root.addWidget(self.count_label)
        self._aplicar_series_view()
        self.refresh_lists()
        self.refresh()

    # ------------------------------------------------------------ dados
    def _period_range(self) -> tuple[str, str]:
        today = date.today()
        days = {1: 0, 2: 7, 3: 30, 4: 365}.get(self.period.currentIndex())
        if days is None:
            return "", ""
        return (today - timedelta(days=days)).strftime("%Y%m%d"), today.strftime("%Y%m%d")

    def refresh(self) -> None:
        """Relê a lista **sem tirar você do exame escolhido** (0.99.7).

        Pedido dele: *"quando estou na tela de banco de dados e novos exames estão sendo baixados, ele
        fica piscando, atualizando e isso me tira do exame que estou selecionado"*. A lista é refeita a
        cada exame que chega; agora a seleção, o exame atual e a posição da rolagem voltam ao que eram,
        a tela não é redesenhada no meio, e as séries do exame escolhido só são refeitas se mudaram."""
        antes = {r.study_uid: (r.num_series, r.num_images) for r in self.selected_rows()}
        cur = self.table.currentIndex()
        atual_uid = self.model.row(self.proxy.mapToSource(cur).row()).study_uid \
            if cur.isValid() and 0 <= self.proxy.mapToSource(cur).row() < self.model.rowCount() else None
        rolagem = (self.table.verticalScrollBar().value(), self.table.horizontalScrollBar().value())
        self.table.setUpdatesEnabled(False)
        try:
            self._refresh_rows()
            depois = self._restaurar_selecao(list(antes), atual_uid, rolagem)
        finally:
            self.table.setUpdatesEnabled(True)
        if not depois:
            esvaziar_lista(self.series_list)
            self.btn_ocultas.setVisible(False)
            self.comments.clear()
            if antes:
                self._selection_changed()
            return
        if len(depois) == 1:
            uid = depois[0].study_uid
            if antes.get(uid) != (depois[0].num_series, depois[0].num_images) or len(antes) != 1:
                self._fill_series(uid)              # chegaram séries/imagens deste exame: refaz só elas

    def _restaurar_selecao(self, uids: list, atual_uid, rolagem) -> list:
        """Marca de novo os exames que estavam escolhidos (os que ainda estão na lista)."""
        from PySide6.QtCore import QItemSelection, QItemSelectionModel
        if not uids:
            return []
        linha_de = {r.study_uid: i for i, r in enumerate(self.model.rows)}
        sm = self.table.selectionModel()
        sel = QItemSelection()
        achou = []
        for u in uids:
            i = linha_de.get(u)
            if i is None:
                continue
            pi = self.proxy.mapFromSource(self.model.index(i, 0))
            if not pi.isValid():
                continue
            sel.select(pi, pi)
            achou.append(self.model.rows[i])
        sm.blockSignals(True)
        try:
            sm.select(sel, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
            if atual_uid in linha_de:
                pi = self.proxy.mapFromSource(self.model.index(linha_de[atual_uid], 0))
                if pi.isValid():
                    sm.setCurrentIndex(pi, QItemSelectionModel.NoUpdate)
        finally:
            sm.blockSignals(False)
        self.table.verticalScrollBar().setValue(rolagem[0])
        self.table.horizontalScrollBar().setValue(rolagem[1])
        return achou

    def _refresh_rows(self) -> None:
        mod = self.modality.currentText()
        d_from, d_to = self._period_range()
        try:
            rows = self.repo.search_studies(self.search.text().strip(),
                                            "" if mod == "Todas" else mod, d_from, d_to, limit=20000,
                                            banco=getattr(self, "banco", "visivel"))
        except TypeError:                       # repositório do modo cliente (servidor antigo)
            rows = self.repo.search_studies(self.search.text().strip(),
                                            "" if mod == "Todas" else mod, d_from, d_to, limit=20000)
        names: dict[str, str] = {}
        order: dict[str, int] = {}
        if self.current_list is not None:
            for lid in self._lists_under(self.current_list):
                for it in self.repo.list_items(lid):
                    if it["study_uid"] not in order:
                        order[it["study_uid"]] = len(order) + 1
                        names[it["study_uid"]] = it["friendly_name"]
            rows = sorted([r for r in rows if r.study_uid in order], key=lambda r: order[r.study_uid])
        for r in rows:
            r.case_n = order.get(r.study_uid, 0)
            r.case_name = names.get(r.study_uid, "")
        self.model.set_rows(rows)
        widths = self._settings_get("browser.column_widths", {}) or {}
        self._applying_columns = True
        for col, (key, _l, _k) in enumerate(COLUMNS):
            if self.table.isColumnHidden(col):
                continue
            if key in widths:
                self.table.setColumnWidth(col, int(widths[key]))
            elif not getattr(self, "_colunas_ajustadas", False) or not self.model.rows:
                self.table.resizeColumnToContents(col)
                self.table.setColumnWidth(col, min(self.table.columnWidth(col), 320))
        # a largura pelo conteúdo só na primeira vez: refazer a cada exame que chega fazia as
        # colunas pularem (0.99.7)
        self._colunas_ajustadas = bool(self.model.rows)
        self._applying_columns = False
        self._update_count()

    def _update_count(self) -> None:
        c = self.repo.counts()
        total = self.model.rowCount()
        shown = self.proxy.rowCount()
        node = self.tree.node(self.current_list)
        where = "" if node is None else f" em “{node['name']}”"
        if self.proxy.active:
            what = f"{shown} de {total} estudo(s) exibido(s){where} — filtros de coluna ativos"
        else:
            what = f"{total} estudo(s) exibido(s){where}"
        self.count_label.setText(
            f"{what}  ·  banco: {c['patients']} pacientes, "
            f"{c['studies']} estudos, {c['series']} séries, {c['instances']} imagens")
        self.btn_clear_filters.setEnabled(self.proxy.active)

    # ------------------------------------------------------------ filtros
    def _text_filter_changed(self, col: int, text: str) -> None:
        self.proxy.set_text_filter(col, text)
        self._update_count()

    def set_column_filter(self, key: str, text: str) -> None:
        """Preenche a caixa de filtro de uma coluna (e aplica na hora)."""
        col = KEY_INDEX[key]
        ed = self.filter_header.editor(col)
        ed.blockSignals(True)
        ed.setText(text)
        ed.blockSignals(False)
        self._text_filter_changed(col, text)

    def column_values(self, col: int) -> list[str]:
        vals = {str(self.model.data(self.model.index(r, col), Qt.DisplayRole) or "")
                for r in range(self.model.rowCount())}
        return sorted(vals, key=lambda v: (v == "", v.lower()))

    def filter_values_dialog(self, col: int) -> None:
        dlg = ValueFilterDialog(COLUMNS[col][1], self.column_values(col),
                                self.proxy.value_filters.get(col), self)
        if dlg.exec():
            self.proxy.set_value_filter(col, dlg.chosen())
            self._update_count()

    def clear_filters(self) -> None:
        self.filter_header.clear_boxes()
        self.proxy.clear_filters()
        self._update_count()

    def _header_menu(self, pos) -> None:
        hh = self.table.horizontalHeader()
        col = hh.logicalIndexAt(pos)
        menu = QMenu(self)
        if col >= 0:
            label = COLUMNS[col][1]
            a = QAction(f"Filtrar valores de \"{label}\"…", menu)
            a.triggered.connect(lambda: self.filter_values_dialog(col))
            menu.addAction(a)
            if col in self.proxy.value_filters or col in self.proxy.text_filters:
                a = QAction(f"Remover filtro de \"{label}\"", menu)
                a.triggered.connect(lambda: self._clear_column_filter(col))
                menu.addAction(a)
        a = QAction("Limpar todos os filtros", menu)
        a.setEnabled(self.proxy.active)
        a.triggered.connect(self.clear_filters)
        menu.addAction(a)
        menu.addSeparator()
        self.columns_menu(menu.addMenu("Colunas"))
        menu.exec(hh.mapToGlobal(pos))

    def _clear_column_filter(self, col: int) -> None:
        ed = self.filter_header.editor(col)
        ed.blockSignals(True)
        ed.clear()
        ed.blockSignals(False)
        self.proxy.set_text_filter(col, "")
        self.proxy.set_value_filter(col, None)
        self._update_count()

    # ------------------------------------------------------------ colunas
    def _settings_get(self, key, default=None):
        return self.settings.get(key, default) if self.settings is not None else default

    def visible_columns(self) -> list[str]:
        cols = self._settings_get("browser.columns") or DEFAULT_COLUMNS
        cols = [c for c in cols if c in KEY_INDEX and c not in LIST_ONLY] or list(DEFAULT_COLUMNS)
        if self.current_list is not None:
            cols = LIST_ONLY + cols
        return cols

    def apply_columns(self) -> None:
        """Mostra as colunas escolhidas, na ordem salva."""
        hh = self.table.horizontalHeader()
        self._applying_columns = True
        visible = self.visible_columns()
        for key, idx in KEY_INDEX.items():
            self.table.setColumnHidden(idx, key not in visible)
        for pos, key in enumerate(visible):
            hh.moveSection(hh.visualIndex(KEY_INDEX[key]), pos)
        self._applying_columns = False
        self.filter_header.adjust_positions()

    def set_columns(self, keys: list[str]) -> None:
        if self.settings is None:
            return
        self.settings.set("browser.columns", [k for k in keys if k in KEY_INDEX and k not in LIST_ONLY])
        self.settings.save()
        self.apply_columns()
        self.refresh()

    def _save_columns(self) -> None:
        if self._applying_columns or self.settings is None:
            return
        hh = self.table.horizontalHeader()
        order = sorted((hh.visualIndex(i), key) for key, i in KEY_INDEX.items()
                       if not self.table.isColumnHidden(i) and key not in LIST_ONLY)
        self.settings.set("browser.columns", [k for _v, k in order])
        self.settings.save()

    def _save_widths_later(self) -> None:
        if self._applying_columns or self.settings is None:
            return
        from PySide6.QtCore import QTimer
        if self._widths_timer is None:
            self._widths_timer = QTimer(self)
            self._widths_timer.setSingleShot(True)
            self._widths_timer.setInterval(600)
            self._widths_timer.timeout.connect(self._save_widths)
        self._widths_timer.start()

    def _save_widths(self) -> None:
        widths = {key: self.table.columnWidth(i) for key, i in KEY_INDEX.items()
                  if not self.table.isColumnHidden(i) and key not in LIST_ONLY}
        self.settings.set("browser.column_widths", {**(self._settings_get("browser.column_widths", {}) or {}),
                                                    **widths})
        self.settings.save()

    def columns_menu(self, menu: QMenu | None = None) -> QMenu:
        menu = menu if menu is not None else QMenu(self)
        visible = self.visible_columns()
        for key, label, _k in COLUMNS:
            if key in LIST_ONLY:
                continue
            a = QAction(label, menu, checkable=True, checked=key in visible)
            a.setEnabled(key != "patient_name")          # o nome do paciente sempre aparece
            a.toggled.connect(lambda on, k=key: self._toggle_column(k, on))
            menu.addAction(a)
        menu.addSeparator()
        a = QAction("Restaurar colunas padrão", menu)
        a.triggered.connect(self._reset_columns)
        menu.addAction(a)
        a = QAction("Ajustar larguras ao conteúdo", menu)
        a.triggered.connect(self._fit_widths)
        menu.addAction(a)
        return menu

    def _toggle_column(self, key: str, on: bool) -> None:
        cols = self.visible_columns()
        if on and key not in cols:
            cols.append(key)
        elif not on and key in cols:
            cols.remove(key)
            self._clear_column_filter(KEY_INDEX[key])     # filtro de coluna oculta não fica escondido
        self.set_columns(cols)

    def _reset_columns(self) -> None:
        if self.settings is not None:
            self.settings.set("browser.column_widths", {})
        self.set_columns(list(DEFAULT_COLUMNS))

    def _fit_widths(self) -> None:
        if self.settings is not None:
            self.settings.set("browser.column_widths", {})
            self.settings.save()
        self.refresh()

    def add_side_panel(self, widget) -> None:
        """Coloca um painel no alto da coluna da esquerda (usado pelo painel "Locais")."""
        self._left_layout.insertWidget(0, widget)
        self.painel_esq.set_max_aberto(320)

    # ------------------------------------------------------------------ painéis recolhíveis (0.99.29)
    listas_mudou = Signal(bool)              # True = painel da esquerda aberto (o botão Listas acompanha)

    def _painel_mudou(self, indice: int, recolhido: bool) -> None:
        split = getattr(self, "split", None)
        if split is None:
            return
        tam = split.sizes()
        if recolhido:
            if tam[indice] > 60:
                self._larguras[indice] = tam[indice]
            from ipe.ui.painel_recolhivel import LARGURA_TIRA
            sobra = tam[indice] - (LARGURA_TIRA + 4)
            if sobra > 0:
                tam[indice] -= sobra
                tam[1] += sobra
                split.setSizes(tam)
            return
        alvo = max(180, self._larguras.get(indice, 280))
        tira = tam[indice]
        tam[indice] = alvo
        tam[1] = max(200, tam[1] - (alvo - tira))
        split.setSizes(tam)

    def _painel_esq_mudou(self, recolhido: bool) -> None:
        self._painel_mudou(0, recolhido)
        if self.settings is not None:
            self.settings.set("browser.show_lists", not recolhido)
            try:
                self.settings.save()
            except Exception:  # noqa: BLE001
                pass
        if recolhido and self.current_list is not None:
            self.tree.select_id(None)
            self._list_selected(None)
        self.listas_mudou.emit(not recolhido)

    def set_banco(self, banco: str) -> None:
        """0.99.27: que banco a lista mostra — tudo o que vejo, o meu, o compartilhado, os
        compartilhados comigo, ou (administrador) o banco pessoal de alguém ("usuario:<nome>")."""
        self.banco = banco or "visivel"
        self.refresh()

    # ------------------------------------------------------------------ banco pessoal × compartilhado
    def acoes_de_banco(self, menu, rows) -> None:
        """Botão direito ▸ Banco: mover para o meu banco, para o compartilhado, compartilhar com…"""
        from ipe.auth import session as S
        from ipe.auth import visibilidade as V
        from ipe.db import banco as B
        v = V.visao_atual()
        if v is None or not rows:
            return
        sub = menu.addMenu("Banco")
        sub.setToolTip(B.AVISO_LOCAL)
        eu = v.usuario.lower()
        meus = all((r.dono or "").lower() == eu for r in rows)
        do_servico = any(not r.dono for r in rows)
        pode_servico = S.can("configure")
        pode = all((r.dono or "").lower() == eu or v.admin or (not r.dono and pode_servico) for r in rows)
        uids = [r.study_uid for r in rows]
        a = sub.addAction("Mover para o meu banco (pessoal)", lambda: self.mover_banco(uids, v.usuario, ""))
        a.setEnabled(pode and not meus and (not do_servico or pode_servico))
        if do_servico and not pode_servico:
            a.setToolTip("Tirar um exame do compartilhado esconde dos outros: só quem configura o computador "
                         "faz isso. Para juntar casos, use as listas.")
        a = sub.addAction("Mover para o compartilhado", lambda: self.mover_banco(uids, "", ""))
        a.setEnabled(pode and not all(not r.dono for r in rows))
        a = sub.addAction("Compartilhar com…", lambda: self._compartilhar_com(rows))
        a.setEnabled(pode and (meus or v.admin))
        if v.admin:
            outros = sub.addMenu("Passar para o banco de")
            for n in self._nomes_de_usuarios():
                if n.lower() != eu:
                    outros.addAction(n, lambda n=n: self.mover_banco(uids, n, ""))
        extra = getattr(self, "acoes_extras_banco", None)       # 0.99.28: servidor ⇄ este computador
        if extra is not None:
            extra(sub, rows)

    def _nomes_de_usuarios(self) -> list[str]:
        """Os usuários ativos (no modo cliente vem do servidor, sem pedir a permissão de usuários)."""
        try:
            return list(self.repo.nomes_de_usuarios())
        except Exception:  # noqa: BLE001
            try:
                return [u["username"] for u in self.repo.users() if u["active"]]
            except Exception:  # noqa: BLE001
                return []

    def mover_banco(self, uids, dono: str, visivel_para: str = "") -> int:
        from ipe.auth import session as S
        from ipe.db import banco as B
        n = self.repo.set_study_scope(uids, dono, visivel_para)
        destino = "compartilhado" if not dono else f"banco pessoal de {dono}"
        try:
            self.repo.audit("moveu_banco", f"{n} exame(s) para o {destino}", user=S.get().username,
                            study_uid=uids[0] if len(uids) == 1 else "")
        except Exception:  # noqa: BLE001
            pass
        self.refresh()
        self.status_message.emit(f"{n} exame(s) no {destino}." + (" " + B.AVISO_LOCAL if dono else ""))
        return n

    def _compartilhar_com(self, rows) -> None:
        from ipe.auth import visibilidade as V
        from ipe.ui.visivel_para import EscolherUsuarios
        v = V.visao_atual()
        dono = rows[0].dono or (v.usuario if v else "")
        nomes = [n for n in self._nomes_de_usuarios() if n.lower() != dono.lower()]
        d = EscolherUsuarios(nomes, V.lista(rows[0].visivel_para), self)
        if d.exec():
            self.mover_banco([r.study_uid for r in rows], dono, ",".join(d.escolhidos()))

    def set_source(self, repo, storage_root) -> None:
        """Troca o banco que a lista mostra (troca de local)."""
        self.repo = repo
        self.storage_root = storage_root
        self.current_list = None
        self.tree.repo = repo
        self.refresh_lists()
        self.refresh()

    def refresh_lists(self) -> None:
        self.tree.rebuild()

    def _lists_under(self, node_id: int | None) -> list[int]:
        """A lista, ou todas as listas dentro da pasta (em qualquer nível)."""
        tree = self.repo.case_list_tree()
        byid = {d["id"]: d for d in tree}
        if node_id not in byid:
            return []
        if byid[node_id]["kind"] != "folder":
            return [node_id]
        out, stack = [], [node_id]
        while stack:
            p = stack.pop()
            for d in tree:
                if d["parent"] == p:
                    (stack.append(d["id"]) if d["kind"] == "folder" else out.append(d["id"]))
        return out

    def _list_selected(self, lid) -> None:
        if lid == self.current_list:
            return
        self.current_list = lid
        node = self.tree.node(lid)
        self.btn_meeting.setEnabled(node is not None and node["kind"] != "folder")
        self.apply_columns()
        self.refresh()
        if lid is not None:
            self.table.sortByColumn(KEY_INDEX["case_n"], Qt.AscendingOrder)

    def _new_list(self, folder: bool = False, parent: int | None = -1) -> int | None:
        if parent == -1:
            node = self.tree.node(self.tree.current_id())
            parent = None if node is None else (node["id"] if node["kind"] == "folder" else node["parent"])
        what = "pasta" if folder else "lista de casos"
        name, ok = QInputDialog.getText(self, f"Nova {what}", "Nome:")
        if not ok or not name.strip():
            return None
        kind = "folder"
        if not folder:
            kind_label, ok2 = QInputDialog.getItem(
                self, "Tipo de lista", "Tipo (Reunião pede um nome amigável para cada caso; Inteligente "
                "se preenche sozinha por um filtro):", ["Normal", "Reunião", "Inteligente (filtro)"], 0, False)
            if not ok2:
                return None
            if kind_label.startswith("Inteligente"):
                return self._new_smart(name.strip(), parent)
            kind = "meeting" if kind_label == "Reunião" else "normal"
        lid = self.repo.create_case_list(name.strip(), kind, parent)
        self.tree.rebuild(select=lid)
        self._list_selected(lid)
        return lid

    def _new_smart(self, name: str = "", parent: int | None = None, lid: int | None = None) -> int | None:
        import json
        from ipe.ui.caselists import SmartListDialog
        q = {}
        if lid is not None:
            info = self.repo.case_list_info(lid) or {}
            name = info.get("name", name)
            try:
                q = json.loads(info.get("smart_query") or "{}")
            except ValueError:
                q = {}
        dlg = SmartListDialog(name, q, self)
        if not dlg.exec():
            return None
        query = json.dumps(dlg.query(), ensure_ascii=False)
        if lid is None:
            lid = self.repo.create_case_list(dlg.name.text().strip(), "smart", parent, smart_query=query)
        else:
            self.repo.update_case_list(lid, name=dlg.name.text().strip(), smart_query=query)
        self.tree.rebuild(select=lid)
        self.current_list = None
        self._list_selected(lid)
        return lid

    def _tree_menu(self, pos) -> None:
        it = self.tree.itemAt(pos)
        lid = it.data(0, Qt.UserRole) if it is not None else None
        node = self.tree.node(lid)
        m = QMenu(self)
        m.addAction("Nova lista…", lambda: self._new_list())
        m.addAction("Nova pasta…", lambda: self._new_list(folder=True))
        if node is not None:
            m.addSeparator()
            if node["kind"] == "smart":
                m.addAction("▶ Iniciar reunião (modo apresentação)", lambda: self._start_meeting(lid))
                m.addAction("Editar filtro…", lambda: self._new_smart(lid=lid))
            elif node["kind"] != "folder":
                m.addAction("▶ Iniciar reunião (modo apresentação)", lambda: self._start_meeting(lid))
                m.addAction("Organizar lista (ordem, nomes, respostas)…", lambda: self.edit_list(lid))
                m.addAction("Duplicar", lambda: self._duplicate(lid))
            if node["kind"] in ("normal", "meeting"):
                conv = "Tornar lista normal" if node["kind"] == "meeting" else "Tornar lista de reunião"
                m.addAction(conv, lambda: (self.repo.update_case_list(
                    lid, kind="normal" if node["kind"] == "meeting" else "meeting"), self.tree.rebuild()))
            m.addAction("Renomear…", lambda: self._rename(lid))
            m.addAction("Descrição…", lambda: self._describe(lid))
            self._menu_visivel_da_lista(m, lid, node)
            move = m.addMenu("Mover para")
            move.addAction("(raiz)", lambda: self._move_to(lid, None))
            for d in self.repo.case_list_tree():
                if d["kind"] == "folder" and d["id"] != lid:
                    move.addAction(f"📁 {d['name']}", lambda _=False, t=d["id"]: self._move_to(lid, t))
            m.addSeparator()
            if node["kind"] not in ("folder",):
                m.addAction("Exportar lista…", lambda: self._export(lid))
            m.addAction("Excluir…", lambda: self._delete_list(lid))
        m.addSeparator()
        dest = lid if node is not None and node["kind"] == "folder" else None
        m.addAction("Importar lista (pacote .zip)…", lambda: self.import_list_requested.emit(dest))
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def _menu_visivel_da_lista(self, m, lid, node) -> None:
        """0.99.30: Visível para — todos (do serviço), só eu, eu e escolhidos; o administrador passa para outro."""
        from ipe.auth import session as S
        from ipe.auth import visibilidade as V
        v = V.visao_atual()
        if v is None or not V.modo_com_usuarios(self.settings):
            return
        sub = m.addMenu(f"Visível para ({V.rotulo(node)})")
        dono = (node.get("dono") or "").lower()
        meu = dono == v.usuario.lower()
        pode = v.admin or meu or (not dono)
        a = sub.addAction("Todos (do serviço)", lambda: self._escopo_lista(lid, "", ""))
        a.setEnabled(pode and bool(dono))
        a = sub.addAction("Só eu", lambda: self._escopo_lista(lid, v.usuario, ""))
        a.setEnabled(pode and not (meu and not node.get("visivel_para")) and (bool(dono) or S.can("configure") or v.admin))
        if not dono and not (S.can("configure") or v.admin):
            a.setToolTip("Tirar uma lista de todos esconde dos outros: só quem configura o computador faz isso. "
                         "Para ter a sua, use Duplicar.")
        a = sub.addAction("Eu e usuários escolhidos…", lambda: self._compartilhar_lista(lid, node))
        a.setEnabled(pode and (meu or v.admin or S.can("configure")))
        if v.admin:
            outros = sub.addMenu("Passar para")
            for n in self._nomes_de_usuarios():
                if n.lower() != dono:
                    outros.addAction(n, lambda n=n: self._escopo_lista(lid, n, ""))

    def _escopo_lista(self, lid, dono: str, visivel_para: str) -> None:
        from ipe.auth import session as S
        try:
            n = self.repo.escopo_da_lista(lid, dono, visivel_para)
        except Exception as e:  # noqa: BLE001
            QMessageBox.information(self, "Visível para", str(e).split(": ", 1)[-1] if "Error" in str(e) else str(e))
            return
        try:
            self.repo.audit("escopo_da_lista", f"lista {lid}: " + (f"de {dono}" if dono else "de todos")
                            + (f" + {visivel_para}" if visivel_para else "") + f" ({n} item(ns))",
                            user=S.get().username)
        except Exception:  # noqa: BLE001
            pass
        self.tree.rebuild()
        self.status_message.emit("Lista " + ("de todos (do serviço)." if not dono else f"pessoal de {dono}."
                                             + (f" Também para {visivel_para}." if visivel_para else "")))

    def _compartilhar_lista(self, lid, node) -> None:
        from ipe.auth import visibilidade as V
        from ipe.ui.visivel_para import EscolherUsuarios
        v = V.visao_atual()
        dono = node.get("dono") or (v.usuario if v else "")
        nomes = [n for n in self._nomes_de_usuarios() if n.lower() != dono.lower()]
        d = EscolherUsuarios(nomes, V.lista(node.get("visivel_para", "")), self)
        if d.exec():
            self._escopo_lista(lid, dono, ",".join(d.escolhidos()))

    def _start_meeting(self, lid, start: int = 0) -> None:
        node = self.tree.node(lid)
        if node is None or node["kind"] == "folder":
            QMessageBox.information(self, "Modo reunião", "Selecione uma lista de casos à esquerda.")
            return
        self.meeting_requested.emit(lid, start)

    def edit_list(self, lid) -> None:
        node = self.tree.node(lid)
        if node is None or node["kind"] == "folder":
            return
        if node["kind"] == "smart":
            self._new_smart(lid=lid)
            return
        from ipe.ui.caselists import ListEditorDialog
        rows = self.selected_rows()
        dlg = ListEditorDialog(self.repo, lid, self, rows[0].study_uid if len(rows) == 1 else None)
        dlg.open_case.connect(self.open_case.emit)
        dlg.exec()
        self.tree.rebuild()
        self.refresh()

    def _duplicate(self, lid) -> None:
        new = self.repo.duplicate_case_list(lid)
        self.tree.rebuild(select=new)

    def _rename(self, lid) -> None:
        node = self.tree.node(lid)
        name, ok = QInputDialog.getText(self, "Renomear", "Nome:", text=node["name"])
        if ok and name.strip():
            self.repo.update_case_list(lid, name=name.strip())
            self.tree.rebuild()

    def _describe(self, lid) -> None:
        node = self.tree.node(lid)
        text, ok = QInputDialog.getMultiLineText(self, "Descrição", "Descrição:", node["description"])
        if ok:
            self.repo.update_case_list(lid, description=text.strip())
            self.tree.rebuild()

    def _move_to(self, lid, target) -> None:
        self.tree.move_node(lid, target)
        self.tree.rebuild(select=lid)

    def _delete_list(self, lid) -> None:
        node = self.tree.node(lid)
        what = (f"a pasta “{node['name']}”? As listas de dentro sobem um nível." if node["kind"] == "folder"
                else f"a lista “{node['name']}” ({node['count']} caso(s))? Os exames continuam no banco.")
        if QMessageBox.question(self, "Excluir", f"Excluir {what}") != QMessageBox.Yes:
            return
        self.repo.delete_case_list(lid)
        if self.current_list == lid:
            self.current_list = None
            self.apply_columns()
        self.tree.rebuild(select=None if self.current_list == lid else -1)
        self.refresh()

    def _export(self, lid) -> None:
        from ipe.ui.caselists import export_dialog
        export_dialog(self, self.repo, lid)

    def _studies_dropped(self, lid: int, uids: list[str]) -> None:
        if (self.tree.node(lid) or {}).get("kind") == "smart":
            return
        node = self.tree.node(lid)
        rows = [r for r in self.model.rows if r.study_uid in uids]
        self._add_to_list(lid, node["kind"] if node else "normal", rows)

    def _remove_from_current(self, rows: list[StudyRow]) -> None:
        node = self.tree.node(self.current_list)
        if node is None or node["kind"] == "folder":
            return
        self.repo.remove_from_case_list(self.current_list, [r.study_uid for r in rows])
        self.tree.rebuild()
        self.refresh()

    def set_privacy(self, on: bool, case_names: dict[str, str] | None = None) -> None:
        """Modo reunião: nenhum dado do paciente na lista (nome amigável no lugar do nome)."""
        self.model.beginResetModel()
        self.model.anonymize = on
        self.model.case_names = dict(case_names or {}) if on else {}
        self.model.endResetModel()
        self.comments.clear()

    def selected_rows(self) -> list[StudyRow]:
        idxs = self.table.selectionModel().selectedRows()
        return [self.model.row(self.proxy.mapToSource(i).row()) for i in idxs]

    def _selection_changed(self, *_):
        rows = self.selected_rows()
        esvaziar_lista(self.series_list)
        self.comments.clear()
        if len(rows) != 1:
            return
        r = rows[0]
        self._fill_series(r.study_uid)
        html = []
        if self.model.anonymize:
            self.comments.setHtml("<i>Modo reunião: dados ocultos</i>")
            return
        node = self.tree.node(self.current_list)
        if node is not None and node["kind"] != "folder":
            it = next((x for x in self.repo.list_items(self.current_list) if x["study_uid"] == r.study_uid), None)
            if it is not None:
                html.append(f"<p><b>Caso {it['n']}: {_esc(it['friendly_name'] or '(sem nome)')}</b>"
                            + (f"<br><i>{_esc(', '.join(it['tags']))}</i>" if it["tags"] else "")
                            + (f"<br><b>História:</b> {_esc(it['clinical_summary'])}" if it["clinical_summary"] else "")
                            + (f"<br><b>Resposta:</b> {_esc(it['hidden_diagnosis'])}" if it["hidden_diagnosis"] else "")
                            + (f"<br><b>Notas:</b> {_esc(it['note'])}" if it["note"] else "")
                            + "<br><span style='color:gray'>Botão direito → Editar caso</span></p><hr>")
        for c in self.repo.comments(r.study_uid):
            html.append(f"<p><span style='color:gray'>{c.created_at:%d/%m/%Y %H:%M}</span><br>"
                        f"{_esc(c.text)}</p>")
        self.comments.setHtml("".join(html) or "<i>Sem comentários</i>")

    # ------------------------------------------------------------ séries
    def _fill_series(self, study_uid: str) -> None:
        """Preenche a lista de séries do exame, na vista escolhida (ícone ou lista)."""
        esvaziar_lista(self.series_list)
        escondidas = self.repo.count_hidden_series(study_uid)
        self.btn_ocultas.setVisible(bool(escondidas))
        self.btn_ocultas.setToolTip(f"Mostrar também as {escondidas} série(s) que você ocultou"
                                    if escondidas else "Mostrar também as séries que você ocultou")
        if not escondidas and self.btn_ocultas.isChecked():
            self.btn_ocultas.setChecked(False)
        icone = self.series_view == "icone"
        grupo_de = {u: g["name"] for g in self.repo.series_groups(study_uid) for u in g["series_uids"]}
        from ipe.importer.thumbnails import miniaturas_que_faltam
        miniaturas_que_faltam(self.repo, study_uid)
        for se in self.repo.series_for_study(study_uid, ocultas=self.mostrar_ocultas):
            desc = se.description[:24] if icone else se.description
            entre = "\n" if icone else "  ·  "
            # montado por pedaços de propósito: padrão de tradução que começa com {} sequestra
            # outros textos, e "{} im" seria o mais genérico de todos
            texto = entre.join([str(se.series_number) + " " + se.modality, desc,
                                str(se.num_images) + " im"])
            if se.hidden:
                texto = "Oculta" + entre + texto
            if se.series_uid in grupo_de:
                texto += entre + "◆ " + grupo_de[se.series_uid]
            it = QListWidgetItem(texto)
            if se.thumbnail:
                pm = QPixmap()
                pm.loadFromData(se.thumbnail, "PNG")
                it.setIcon(QIcon(pm))
            it.setSizeHint(QSize(120, 150) if icone else QSize(10, 26))
            it.setData(Qt.UserRole, se.series_uid)
            if se.hidden:
                it.setForeground(QColor(140, 140, 140))
            it.setToolTip("Duplo clique: abrir só esta série. Botão direito: ocultar ou apagar. "
                          "Ctrl+clique escolhe várias; a tecla Delete apaga as escolhidas.")
            self.series_list.addItem(it)

    def set_series_view(self, modo: str) -> None:
        self.series_view = "lista" if modo == "lista" else "icone"
        if self.settings is not None:
            self.settings.set("browser.series_view", self.series_view)
        self._aplicar_series_view()
        self._recarregar_series()

    def _aplicar_series_view(self) -> None:
        icone = self.series_view == "icone"
        self.series_list.setViewMode(QListWidget.IconMode if icone else QListWidget.ListMode)
        self.series_list.setIconSize(QSize(96, 96) if icone else QSize(28, 28))
        self.series_list.setWordWrap(icone)
        self.series_list.setSpacing(0)
        self.btn_series_view.setText("Em lista" if icone else "Em ícones")
        self.btn_series_view.setToolTip("Mostrar as séries em lista (uma por linha)" if icone
                                        else "Mostrar as séries em ícones com miniatura")

    def _ocultas_toggled(self, on: bool) -> None:
        self.mostrar_ocultas = bool(on)
        self._recarregar_series()

    def _recarregar_series(self) -> None:
        rows = self.selected_rows()
        if len(rows) == 1:
            self._fill_series(rows[0].study_uid)
        else:
            esvaziar_lista(self.series_list)

    def _hide_series(self, uids: list[str], hidden: bool) -> None:
        if not uids:
            return
        self.repo.set_series_hidden(uids, hidden)
        if hidden:
            self.series_changed.emit()
        self._recarregar_series()

    def _delete_series(self, uids: list[str] | None = None) -> None:
        """Apaga séries do banco e os arquivos delas que estão no Storage."""
        from ipe.auth import session as S
        rows = self.selected_rows()
        uids = uids if uids is not None else self.selected_series()
        if len(rows) != 1 or not uids:
            return
        if not S.require("delete", self):
            return
        nomes = [it.text().replace("\n", " ") for it in self.series_list.selectedItems()
                 if it.data(Qt.UserRole) in uids]
        aviso = ("Os arquivos copiados para o armazenamento são removidos; arquivos apenas "
                 "referenciados continuam no lugar original. Para só tirar da lista, use Ocultar.")
        if QMessageBox.question(self, "Apagar série",
                                f"Apagar {len(uids)} série(s) do exame?"
                                + "\n\n" + "\n".join(nomes[:8]) + "\n\n" + aviso) != QMessageBox.Yes:
            return
        erros = []
        for u in uids:
            try:
                self.repo.delete_series(u, self.storage_root)
                S.audit(self.repo, "apagar série", f"{rows[0].patient_name} — {u}",
                        study_uid=rows[0].study_uid)
            except PermissionError as e:
                erros.append(str(e))
            except Exception as e:  # noqa: BLE001
                erros.append(str(e))
        if erros:
            QMessageBox.warning(self, "Nem tudo foi apagado", "\n".join(dict.fromkeys(erros)))
        uid = rows[0].study_uid
        self.series_changed.emit()
        self.refresh()
        self.select_study(uid)

    def historico(self, row):
        from ipe.ui.historico_exame import HistoricoDialog
        nome = "" if getattr(self.model, "anonymize", False) else (row.patient_name or "")
        d = HistoricoDialog(self.repo, row.study_uid, f"{nome} {row.description or ''}".strip(), self)
        d.show()
        self._historicos = [d]
        return d

    def select_study(self, study_uid: str) -> None:
        """Volta a selecionar um exame na tabela (depois de um refresh)."""
        for r in range(self.proxy.rowCount()):
            idx = self.proxy.index(r, 0)
            if self.model.row(self.proxy.mapToSource(idx).row()).study_uid == study_uid:
                self.table.selectRow(r)
                return

    def _open_series_item(self, item) -> None:
        rows = self.selected_rows()
        if len(rows) == 1 and item.data(Qt.UserRole):
            self.open_series.emit(rows[0].study_uid, [item.data(Qt.UserRole)])

    def selected_series(self) -> list[str]:
        return [it.data(Qt.UserRole) for it in self.series_list.selectedItems() if it.data(Qt.UserRole)]

    def _series_menu(self, pos) -> None:
        rows = self.selected_rows()
        if len(rows) != 1:
            return
        it = self.series_list.itemAt(pos)
        if it is not None and it.data(Qt.UserRole) not in self.selected_series():
            # botão direito numa série fora da seleção age sobre ela, não sobre a seleção antiga
            self.series_list.setCurrentItem(it)
        menu = self.series_menu(rows[0].study_uid, self.selected_series())
        menu.exec(self.series_list.viewport().mapToGlobal(pos))

    def series_menu(self, study_uid: str, uids: list[str]) -> QMenu:
        menu = QMenu(self)
        a = menu.addAction(f"Abrir as {len(uids)} séries selecionadas" if len(uids) > 1 else "Abrir esta série",
                           lambda: self.open_series.emit(study_uid, uids))
        a.setEnabled(bool(uids))
        menu.addAction("Abrir escolhendo séries…", lambda: self.choose_series.emit(study_uid))
        menu.addSeparator()
        ocultas = [u for u in uids if u in self._uids_ocultos(study_uid)]
        a = menu.addAction(f"Ocultar {len(uids)} série(s)" if len(uids) > 1 else "Ocultar esta série",
                           lambda: self._hide_series([u for u in uids if u not in ocultas], True))
        a.setEnabled(bool(uids) and len(ocultas) < len(uids))
        a.setToolTip("A série some das listas e do visualizador. Nada é apagado.")
        if ocultas:
            menu.addAction(f"Mostrar de novo {len(ocultas)} série(s) oculta(s)",
                           lambda: self._hide_series(ocultas, False))
        a = menu.addAction(f"Apagar {len(uids)} série(s)…" if len(uids) > 1 else "Apagar esta série…",
                           lambda: self._delete_series(uids))
        a.setEnabled(bool(uids))
        menu.addSeparator()
        mods = {(se.modality or "").upper() for se in self.repo.series_for_study(study_uid, ocultas=True)
                if se.series_uid in set(uids)}
        a = menu.addAction("Segmentar órgãos abdominais (TotalSegmentator)…",
                           lambda: self.segmentar_orgaos(study_uid, uids[0]))
        a.setEnabled(len(uids) == 1 and bool(mods & {"CT", "MR"}))
        a.setToolTip("Fígado, baço, rins, pâncreas… numa série de TC ou RM do abdome. Grava as máscaras "
                     "(SEG) e a tabela de volumes (OT) no exame, só neste computador.")
        a = menu.addAction("Identificar vértebras e discos (TotalSegmentator)…",
                           lambda: self.segmentar_orgaos(study_uid, uids[0], tipo="coluna"))
        a.setEnabled(len(uids) == 1 and bool(mods & {"CT", "MR"}))
        a.setToolTip("Dá nome a cada vértebra e disco (C2-C3 … L5-S1) numa série de TC ou RM da coluna. Os "
                     "nomes aparecem em qualquer série e plano do exame.")
        menu.addSeparator()
        a = menu.addAction(f"Marcar as {len(uids)} séries como dinâmica…",
                           lambda: self._marcar_dinamica(study_uid, uids))
        a.setEnabled(len(uids) >= 2)
        a.setToolTip("Uma fase por série: o visualizador passa a abrir estas séries juntas, "
                     "com os mapas e as curvas da avaliação dinâmica.")
        for g in self._grupos_de(study_uid, uids):
            menu.addAction(f"Desfazer a dinâmica {g['name']}",
                           lambda gid=g["id"]: self._desfazer_dinamica(study_uid, gid))
        menu.addSeparator()
        from ipe.auth import session as S
        from ipe.ui.send_menu import preencher_envio
        send_menu = menu.addMenu(f"Enviar {len(uids)} série(s) para" if len(uids) > 1
                                 else "Enviar esta série para")
        preencher_envio(send_menu, self.repo,
                        lambda nid, iid, su=list(uids): self.send_series_requested.emit(study_uid, su, nid, iid))
        send_menu.setEnabled(bool(uids) and S.can("send"))
        return menu

    def _mandar_aos_destinos(self, study_uid: str, series: list, ids) -> int:
        """Preferências ▸ CAD/IA ▸ "depois de fazer, enviar para": o pedido vai pela janela principal,
        como o envio de série pelo menu (o banco não tem a rede)."""
        from ipe.automation import destinos as DEST
        nos = DEST.nos_escolhidos(self.repo, ids)
        for no in nos:
            self.send_series_requested.emit(study_uid, list(series), no["id"], None)
        return len(nos)

    def segmentar_orgaos(self, study_uid: str, series_uid: str, simular: bool = False, tipo: str = "abdome"):
        """Banco ▸ botão direito na série ▸ Segmentar órgãos abdominais (0.98) ou Identificar vértebras e
        discos (tipo="coluna", 0.99.2)."""
        from ipe.ui.segmentacao import Segmentacao
        seg = Segmentacao(self, self.repo, self.settings, self.storage_root, study_uid, series_uid,
                          simular=simular, tipo=tipo)

        def pronto(saida, msg):
            if saida is not None:
                self.refresh()
                self.series_changed.emit()
                self.segmentacao_pronta.emit(study_uid, saida)
                from ipe.ai import coluna as COL
                from ipe.ai import totalseg as TS
                destinos = (COL.config(self.settings, COL.CHAVE_DESTINOS) if tipo == "coluna"
                            else TS.config(self.settings, TS.CHAVE_DESTINOS))
                if self._mandar_aos_destinos(study_uid, saida.get("series") or [], destinos):
                    msg += " Enviada também aos destinos escolhidos em Preferências ▸ CAD/IA."
                QMessageBox.information(self, seg.titulo, msg)
            elif msg != "Segmentação cancelada.":
                QMessageBox.warning(self, seg.titulo, msg)
        seg.terminou.connect(pronto)
        seg.iniciar()
        return seg

    def _grupos_de(self, study_uid: str, uids: list[str]) -> list[dict]:
        alvo = set(uids)
        return [g for g in self.repo.series_groups(study_uid) if alvo & set(g["series_uids"])]

    def _marcar_dinamica(self, study_uid: str, uids: list[str]) -> None:
        """Classifica as séries escolhidas como uma dinâmica (uma fase por série)."""
        if len(uids) < 2:
            QMessageBox.information(self, "Dinâmica", "Escolha pelo menos duas séries: "
                                    "uma dinâmica é uma fase por série.")
            return
        ja = self._grupos_de(study_uid, uids)
        if ja:
            nomes = ", ".join(g["name"] for g in ja)
            if QMessageBox.question(self, "Dinâmica",
                                    f"Alguma destas séries já está na dinâmica {nomes}. "
                                    "Criar outra assim mesmo?") != QMessageBox.Yes:
                return
        nome, ok = QInputDialog.getText(self, "Classificar como dinâmica",
                                        "Nome da dinâmica (aparece no visualizador):", text="Dinâmica")
        if not ok or not nome.strip():
            return
        # a ordem das fases é a ordem das séries no exame, não a ordem em que ele clicou
        ordem = [se.series_uid for se in self.repo.series_for_study(study_uid, ocultas=True)
                 if se.series_uid in set(uids)]
        self.repo.save_series_group(study_uid, ordem, nome.strip())
        self._anotar_regra(study_uid, ordem, nome.strip())
        self.series_changed.emit()
        self._recarregar_series()
        QMessageBox.information(self, "Dinâmica", f"{len(ordem)} séries marcadas como “{nome.strip()}”. "
                                "No visualizador elas abrem juntas, com as fases na ordem das séries.")

    def _anotar_regra(self, study_uid: str, uids: list[str], nome: str) -> None:
        """Marcou na mão: vira regra **pendente** nas Preferências, para ele confirmar."""
        from ipe.imaging import dinamicas as D
        linhas = {s.series_uid: s for s in self.repo.series_for_study(study_uid, ocultas=True)}
        rows = [linhas[u] for u in uids if u in linhas]
        if not rows or self.settings is None:
            return
        linha = next((r for r in self.model.rows if r.study_uid == study_uid), None)
        exame = " ".join(x for x in ((linha.accession if linha else ""), fmt_date(
            linha.study_date if linha else ""), (linha.description if linha else "")[:24]) if x)
        regra = D.acrescentar_pendente(
            self.settings, D.sugerir(rows[0].modality, [r.description for r in rows], "juntar", nome,
                                     study_uid, exame or study_uid[-8:]))
        if regra:
            QMessageBox.information(
                self, "Dinâmica",
                f"Anotei uma regra pendente: juntar séries de {regra['modalidade']} com "
                f"“{regra['contem']}” na descrição.\n\nEla só passa a valer depois que você "
                "confirmar em Preferências ▸ Dinâmicos.")

    def _desfazer_dinamica(self, study_uid: str, group_id: int) -> None:
        self.repo.delete_series_group(group_id)
        self.series_changed.emit()
        self._recarregar_series()

    def _uids_ocultos(self, study_uid: str) -> set[str]:
        return {se.series_uid for se in self.repo.series_for_study(study_uid, ocultas=True) if se.hidden}

    def _open_selected(self, *_):
        """Um exame abre normal; mais de um abre junto, para comparar."""
        rows = self.selected_rows()
        if len(rows) > 1:
            self.compare_studies.emit([r.study_uid for r in rows[:6]])
            return
        for r in rows[:4]:
            self.open_study.emit(r.study_uid)

    def _open_each(self) -> None:
        for r in self.selected_rows()[:4]:
            self.open_study.emit(r.study_uid)

    # ------------------------------------------------------------ ações
    def _add_comment(self) -> None:
        rows = self.selected_rows()
        if len(rows) != 1:
            QMessageBox.information(self, "Comentário", "Selecione um estudo.")
            return
        dlg = TextInputDialog("Comentário", f"Comentário para: {rows[0].description}", parent=self)
        if dlg.exec() and dlg.value():
            self.repo.add_comment("study", rows[0].study_uid, dlg.value())
            r = rows[0]
            r.has_comment = True
            from ipe.db.repository import comment_summary
            r.comment = comment_summary([getattr(c, "text", None) or (c.get("text", "") if isinstance(c, dict) else "")
                                         for c in self.repo.comments(r.study_uid)])
            mdl = self.model
            mdl.dataChanged.emit(mdl.index(0, 0), mdl.index(mdl.rowCount() - 1, mdl.columnCount() - 1))
            self._selection_changed()

    def _study_menu(self, pos) -> None:
        rows = self.selected_rows()
        if not rows:
            return
        menu = self.menu_do_exame(rows)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def menu_do_exame(self, rows: list[StudyRow]) -> QMenu:
        """Monta o menu do botão direito da lista (montar e abrir são passos separados:
        assim o menu pode ser conferido sem precisar abrir uma janela modal)."""
        menu = QMenu(self)
        a_open = QAction("Abrir juntos, para comparar" if len(rows) > 1 else "Abrir", menu)
        a_open.triggered.connect(self._open_selected)
        menu.addAction(a_open)
        if len(rows) > 1:
            a_cada = QAction("Abrir cada um em sua aba", menu)
            a_cada.triggered.connect(self._open_each)
            menu.addAction(a_cada)
        a_choose = QAction("Abrir escolhendo séries…", menu)
        a_choose.triggered.connect(lambda: self.choose_series.emit(rows[0].study_uid))
        a_choose.setEnabled(len(rows) == 1)
        menu.addAction(a_choose)
        rep = getattr(rows[0], "report", "")
        a_rep = QAction(f"Laudo ({rep})…" if rep else "Laudo…", menu)
        a_rep.triggered.connect(lambda: self.report_requested.emit(rows[0].study_uid))
        a_rep.setEnabled(len(rows) == 1)
        menu.addAction(a_rep)
        a_com = QAction("Adicionar comentário…", menu)
        a_com.triggered.connect(self._add_comment)
        a_com.setEnabled(len(rows) == 1)
        menu.addAction(a_com)
        a_hist = QAction("Histórico do exame…", menu)          # 0.99.31 (onda A6)
        a_hist.triggered.connect(lambda: self.historico(rows[0]))
        a_hist.setEnabled(len(rows) == 1)
        menu.addAction(a_hist)
        node = self.tree.node(self.current_list)
        if node is not None and node["kind"] != "folder":
            a = QAction("Editar caso (nome, história, resposta)…" if node["kind"] != "smart"
                        else "Editar filtro da lista…", menu)
            a.triggered.connect(lambda: self.edit_list(self.current_list))
            a.setEnabled(len(rows) == 1 or node["kind"] == "smart")
            menu.addAction(a)
            a = QAction("▶ Reunião a partir deste caso", menu)
            a.triggered.connect(lambda: self._start_meeting(
                self.current_list, max(0, int(getattr(rows[0], "case_n", 1) or 1) - 1)))
            a.setEnabled(len(rows) == 1)
            menu.addAction(a)
            if node["kind"] != "smart":
                a = QAction(f"Tirar da lista “{node['name']}”", menu)
                a.triggered.connect(lambda: self._remove_from_current(rows))
                menu.addAction(a)
            menu.addSeparator()
        if self.other_locations:
            loc_menu = menu.addMenu("Copiar para o local")
            for lid, lname in self.other_locations:
                loc_menu.addAction(lname, lambda u=[r.study_uid for r in rows], i=lid:
                                   self.copy_to_location.emit(u, i))
        lists_menu = menu.addMenu("Adicionar à lista")
        a_new = QAction("Nova lista…", lists_menu)
        a_new.triggered.connect(lambda: self._add_to_new_list(rows))
        lists_menu.addAction(a_new)
        lists_menu.addSeparator()
        for lid, name, kind, _n in self.repo.case_lists():
            a = QAction(name, lists_menu)
            a.triggered.connect(lambda _=False, l=lid, k=kind: self._add_to_list(l, k, rows))
            lists_menu.addAction(a)

        self.acoes_de_banco(menu, rows)
        send_menu = menu.addMenu("Enviar para")
        self.fill_send_menu(send_menu, rows)
        from ipe.auth import session as S
        send_menu.setEnabled(S.can("send"))
        lists_menu.setEnabled(S.can("case_lists"))
        a_exp = QAction("Exportar (DICOM, CD/pendrive, imagens)…", menu)
        a_exp.setEnabled(S.can("export"))
        a_exp.triggered.connect(lambda: self.export_rows(rows))
        menu.addAction(a_exp)
        a_anon = QAction("Anonimizar cópias destes {} exames…".format(len(rows)) if len(rows) > 1
                         else "Anonimizar uma cópia deste exame…", menu)
        a_anon.setEnabled(S.can("export"))
        a_anon.triggered.connect(lambda: self.export_rows(rows, anonimizar=True))
        menu.addAction(a_anon)
        film_menu = menu.addMenu("Filme")
        film_menu.setEnabled(len(rows) == 1)
        if len(rows) == 1:
            st = rows[0].study_uid
            a = film_menu.addAction("Imagens-chave no filme",
                                    lambda: self.film_requested.emit({"kind": "keys", "study_uid": st}))
            a.setEnabled(bool(rows[0].key_images))
            n = len(self.repo.films(st))
            a = film_menu.addAction(f"Filmes salvos deste exame ({n})…",
                                    lambda: self.film_requested.emit({"kind": "saved", "study_uid": st}))
            a.setEnabled(bool(n))
        mgs = [r for r in rows if "MG" in (r.modalities or "").upper()]
        a_imp = QAction("Apagar implante (salvar a mamografia sem o silicone)" if len(mgs) <= 1
                        else f"Apagar implante ({len(mgs)} mamografias; salvar sem o silicone)", menu)
        a_imp.setToolTip("Grava, no mesmo exame, uma cópia de cada imagem com prótese com o silicone "
                         "corrigido. A original não muda e a cópia não vai ao PACS.")
        a_imp.setEnabled(bool(mgs))
        a_imp.triggered.connect(lambda: self.apagar_implante(mgs))
        menu.addAction(a_imp)
        a_tags = QAction("Corrigir tags (nome, lado, data)…", menu)
        a_tags.setEnabled(len(rows) == 1)
        a_tags.triggered.connect(lambda: self.fix_tags_requested.emit(rows[0].study_uid))
        menu.addAction(a_tags)
        menu.addSeparator()
        a_lock = QAction("Proteger (não apagar)", menu)
        a_lock.triggered.connect(lambda: [self.repo.set_locked(r.study_uid, True) for r in rows])
        menu.addAction(a_lock)
        a_unlock = QAction("Remover proteção", menu)
        a_unlock.triggered.connect(lambda: [self.repo.set_locked(r.study_uid, False) for r in rows])
        menu.addAction(a_unlock)
        a_lock.setEnabled(S.can("delete"))
        a_unlock.setEnabled(S.can("delete"))
        a_del = QAction("Apagar do banco…", menu)
        a_del.setEnabled(S.can("delete"))
        a_del.triggered.connect(lambda: self._delete(rows))
        menu.addAction(a_del)
        return menu

    def apagar_implante(self, rows: list[StudyRow]) -> dict:
        """Botão direito ▸ Apagar implante: grava as cópias sem silicone das mamografias escolhidas
        (as que já têm cópia são puladas). Devolve o total, para a tela e para os testes."""
        from PySide6.QtWidgets import QApplication, QProgressDialog

        from ipe.automation import implante as IMP
        total = {"exames": 0, "corrigidas": 0, "ja": 0, "vistas": 0}
        if not rows or self.storage_root is None:
            return total
        dlg = QProgressDialog("Procurando o implante…", "Parar", 0, 100, self)
        dlg.setWindowTitle("Apagar implante")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(300)
        try:
            for k, r in enumerate(rows):
                if dlg.wasCanceled():
                    break
                nome = (r.patient_name or "").replace("^", " ").strip()
                antes = len(IMP.ja_salvas(self.repo, r.study_uid))

                def prog(feitas, n, k=k, nome=nome):
                    dlg.setLabelText(f"{nome} — exame {k + 1} de {len(rows)}: imagem {min(feitas + 1, n)} de {n}")
                    dlg.setValue(int(100 * (k + (feitas / n if n else 1)) / len(rows)))
                    QApplication.processEvents()

                out = IMP.processar(self.repo, self.repo.db, self.storage_root, r.study_uid,
                                    parar=dlg.wasCanceled, progresso=prog,
                                    so_com_marca=bool(IMP.config(self.settings, IMP.CHAVE_SO_COM_MARCA)))
                if out.get("series"):
                    self._mandar_aos_destinos(r.study_uid, out["series"],
                                              IMP.config(self.settings, IMP.CHAVE_DESTINOS))
                total["exames"] += 1
                total["corrigidas"] += out["corrigidas"]
                total["vistas"] += out["vistas"]
                total["ja"] += antes
        finally:
            dlg.close()
        if total["corrigidas"]:
            msg = f"{total['corrigidas']} imagem(ns) salva(s) sem o silicone, no próprio exame (série “· sem implante”)."
        elif total["ja"]:
            msg = "Estas mamografias já tinham as imagens sem o silicone salvas."
        else:
            msg = ("Não achei implante nestas mamografias (ou o aparelho diz que não há, ou são incidências com "
                   "o implante deslocado). Se houver prótese, abra o exame e use o botão Implante ou o botão "
                   "direito dentro do silicone.")
        if total["ja"] and total["corrigidas"]:
            msg += f" {total['ja']} já estavam salvas antes."
        QMessageBox.information(self, "Apagar implante", msg)
        self.refresh()
        return total

    def _add_to_list(self, list_id: int, kind: str, rows: list[StudyRow]) -> None:
        n = len(self.repo.list_items(list_id))
        for r in rows:
            friendly = ""
            if kind == "meeting":
                friendly, ok = QInputDialog.getText(
                    self, "Nome amigável", f"Nome do caso na reunião ({r.modalities} {r.description}) — "
                    "sem dados do paciente:", text=f"Caso {n + 1}")
                if not ok:
                    continue
            if self.repo.add_to_case_list(list_id, r.study_uid, friendly):
                n += 1
        self.tree.rebuild()
        if self.current_list is not None:
            self.refresh()

    def export_selected(self) -> None:
        rows = self.selected_rows()
        if not rows:
            QMessageBox.information(self, "Exportar", "Selecione um ou mais exames na lista.")
            return
        self.export_rows(rows)

    def export_rows(self, rows: list[StudyRow], anonimizar: bool = False) -> None:
        """`anonimizar`: abre a janela já marcada para anonimizar, perguntando o que manter.

        Anonimizar é sempre **cópia**: os arquivos do banco não são tocados, e o nome do
        paciente continua igual na lista — o que sai da máquina é que está sem identificação.
        """
        from ipe.exporter.core import ExportItem
        from ipe.ui.export_dialog import ExportDialog
        scopes = [(f"{len(rows)} exame(s) selecionado(s)", [ExportItem(r.study_uid) for r in rows])]
        series = self.selected_series() if len(rows) == 1 else []
        if series:
            scopes.insert(0, (f"{len(series)} série(s) selecionada(s) no painel", [ExportItem(rows[0].study_uid, series)]))
        keyed = [r for r in rows if getattr(r, "key_images", 0)]
        if keyed:
            items = [ExportItem(r.study_uid, None, [(k["sop_uid"], k["frame_index"])
                                                    for k in self.repo.key_images(r.study_uid)]) for r in keyed]
            scopes.append((f"Imagens-chave ({sum(r.key_images for r in keyed)})", items))
        dlg = ExportDialog(self.repo, self.settings, scopes, self, force_anonymize=self.model.anonymize,
                           anonimizar=anonimizar, storage_root=self.storage_root)
        dlg.exec()
        if getattr(dlg.result_obj, "estudos", None):
            self.refresh()          # a cópia anonimizada é um exame novo na lista

    def fill_send_menu(self, send_menu: QMenu, rows: list[StudyRow]) -> None:
        """Nós de envio (e identidades) para os estudos `rows`."""
        from ipe.ui.send_menu import preencher_envio
        uids = [r.study_uid for r in rows]
        preencher_envio(send_menu, self.repo,
                        lambda nid, iid, u=uids: self.send_requested.emit(u, nid, iid))

    def set_lists_visible(self, on: bool) -> None:
        """O botão Listas: abre ou recolhe o painel da esquerda (0.99.29: recolhe para a borda)."""
        if self.painel_esq.recolhido == (not on):
            return
        self.painel_esq.recolher(not on)

    def set_home_bar(self, bar: QWidget) -> None:
        """Barra de botões da tela inicial (montada pela janela principal)."""
        self.layout().insertWidget(0, bar)

    def apply_permissions(self) -> None:
        """Mostra/esconde o que depende do perfil do usuário."""
        from ipe.auth import session as S
        ok = S.can("case_lists")
        for w in (self.tree, self.btn_meeting):
            w.setVisible(ok)
        if not ok and self.current_list is not None:
            self.tree.select_id(None)
            self._list_selected(None)

    def _add_to_new_list(self, rows: list[StudyRow]) -> None:
        cur = self.current_list
        lid = self._new_list()
        if lid is not None:
            node = self.tree.node(lid)
            self._add_to_list(lid, node["kind"], rows)
            self.tree.select_id(cur)
            self._list_selected(cur)

    def _delete(self, rows: list[StudyRow]) -> None:
        from ipe.auth import session as S
        if not S.require("delete", self):
            return
        ans = QMessageBox.question(
            self, "Apagar", f"Apagar {len(rows)} estudo(s) do banco?\n"
            "Arquivos copiados para o armazenamento serão removidos; "
            "arquivos apenas referenciados continuam no lugar original.")
        if ans != QMessageBox.Yes:
            return
        errors = []
        for r in rows:
            try:
                self.repo.delete_study(r.study_uid, self.storage_root)
                S.audit(self.repo, "apagar", f"{r.patient_name} — {r.study_date} {r.modalities} {r.description}",
                        study_uid=r.study_uid)
            except PermissionError as e:
                errors.append(f"{r.patient_name} — {e}")
        if errors:
            QMessageBox.warning(self, "Alguns estudos não foram apagados", "\n".join(errors))
        self.refresh_lists()
        self.refresh()


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
