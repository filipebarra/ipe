"""Lista de impressões: os filmes que chegaram das modalidades e os que você montou aqui.

Daqui você vê a folha, identifica o paciente quando der, e manda para onde quiser —
um a um ou vários de uma vez.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ipe.printing import dispatch as D
from ipe.printing import jobs as J
from ipe.ui.table_filter import FilterHeader, ValueFilterDialog, fold, match
from ipe.ui.tabelas import colunas_ajustaveis

log = logging.getLogger(__name__)

SITUACAO = {"new": "Na lista", "sent": "Enviado", "error": "Erro"}
#: dica na coluna Paciente: de onde veio o nome
ORIGEM_PACIENTE = {"ocr": "Paciente achado pelo OCR na chegada (cabeçalho da folha comparado com o banco).",
                   "manual": "Paciente confirmado à mão.",
                   "exame": "Paciente escolhido entre os exames do banco.",
                   "label": "Nome tirado do rótulo da sessão de impressão; ainda não confirmado."}


# ---------------------------------------------------------------------------
# destinos
# ---------------------------------------------------------------------------

class DestinationEditor(QDialog):
    """Cadastro de um destino: pasta com PDF, impressora do computador, impressora DICOM…"""

    def __init__(self, dest: D.Destination | None, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Destino da impressão")
        d = dest or D.Destination()
        self._base = d              # o que o editor não mostra (modelo de folha) passa adiante
        self.name = QLineEdit(d.name)
        self.kind = QComboBox()
        for k, texto in D.KINDS.items():
            self.kind.addItem(texto, k)
        self.kind.setCurrentIndex(max(0, self.kind.findData(d.kind)))
        self.kind.currentIndexChanged.connect(self._mostrar)
        self.folder = QLineEdit(d.folder)
        b_pasta = QPushButton("Escolher…")
        b_pasta.clicked.connect(self._escolher_pasta)
        linha = QHBoxLayout()
        linha.addWidget(self.folder, 1)
        linha.addWidget(b_pasta)
        self.printer = QComboBox()
        self.printer.addItem("Impressora padrão do computador", "")
        try:
            from PySide6.QtPrintSupport import QPrinterInfo
            for nome in QPrinterInfo.availablePrinterNames():
                self.printer.addItem(nome, nome)
        except Exception:  # noqa: BLE001
            log.debug("Sem impressoras do sistema")
        self.printer.setCurrentIndex(max(0, self.printer.findData(d.printer)))
        self.dicom = QComboBox()
        for p in (settings.get("printing.dicom_printers", []) or []):
            self.dicom.addItem(p.get("name", ""), p.get("name", ""))
        if d.dicom_printer:
            self.dicom.setCurrentIndex(max(0, self.dicom.findData(d.dicom_printer)))
        self.dpi = QSpinBox(minimum=72, maximum=600, singleStep=50, value=int(d.dpi or 150), suffix=" dpi")
        self.fmt = QComboBox()
        self.fmt.addItem("PNG", "png")
        self.fmt.addItem("JPEG", "jpg")
        self.fmt.setCurrentIndex(max(0, self.fmt.findData(d.fmt)))
        f = QFormLayout()
        f.addRow("Nome:", self.name)
        f.addRow("Tipo:", self.kind)
        self.l_folder = QLabel("Pasta:")
        self.l_printer = QLabel("Impressora:")
        self.l_dicom = QLabel("Impressora DICOM:")
        self.l_fmt = QLabel("Formato:")
        f.addRow(self.l_folder, self._wrap(linha))
        f.addRow(self.l_printer, self.printer)
        f.addRow(self.l_dicom, self.dicom)
        f.addRow(self.l_fmt, self.fmt)
        f.addRow("Resolução:", self.dpi)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(f)
        lay.addWidget(bb)
        self._mostrar()

    @staticmethod
    def _wrap(layout) -> QWidget:
        w = QWidget()
        w.setLayout(layout)
        return w

    def _escolher_pasta(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "Pasta de destino", self.folder.text() or str(Path.home()))
        if p:
            self.folder.setText(p)

    def _mostrar(self) -> None:
        k = self.kind.currentData()
        pasta, sistema, dicom = k in ("pdf", "images"), k == "system", k == "dicom"
        for widget, mostrar in ((self.l_folder, pasta), (self.l_printer, sistema),
                                (self.l_dicom, dicom), (self.l_fmt, k == "images")):
            widget.setVisible(mostrar)
        self.folder.parentWidget().setVisible(pasta)
        self.printer.setVisible(sistema)
        self.dicom.setVisible(dicom)
        self.fmt.setVisible(k == "images")

    def _ok(self) -> None:
        k = self.kind.currentData()
        if not self.name.text().strip():
            QMessageBox.warning(self, "Destino", "Dê um nome ao destino.")
            return
        if k in ("pdf", "images") and not self.folder.text().strip():
            QMessageBox.warning(self, "Destino", "Escolha a pasta onde os arquivos vão ficar.")
            return
        if k == "dicom" and not self.dicom.currentData():
            QMessageBox.warning(self, "Destino", "Cadastre a impressora DICOM em Filme → Impressoras.")
            return
        self.accept()

    def destination(self) -> D.Destination:
        import dataclasses
        return dataclasses.replace(self._base, name=self.name.text().strip(), kind=self.kind.currentData(),
                             folder=self.folder.text().strip(), printer=self.printer.currentData() or "",
                             dicom_printer=self.dicom.currentData() or "", dpi=self.dpi.value(),
                             fmt=self.fmt.currentData())


class SendDialog(QDialog):
    """Escolher para onde mandar (e cadastrar destinos novos)."""

    def __init__(self, settings, quantos: int, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Enviar impressão")
        self.resize(480, 320)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _i: self._ok())
        b_novo = QPushButton("Novo…")
        b_editar = QPushButton("Editar…")
        b_remover = QPushButton("Remover")
        b_novo.clicked.connect(self._novo)
        b_editar.clicked.connect(self._editar)
        b_remover.clicked.connect(self._remover)
        botoes = QHBoxLayout()
        for b in (b_novo, b_editar, b_remover):
            botoes.addWidget(b)
        botoes.addStretch(1)
        self.modelo = QComboBox()
        self.modelo.addItem("A folha como veio", "")
        from ipe.printing.layout import all_templates
        for m in all_templates(settings):
            self.modelo.addItem(m.name, m.name)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Enviar")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Enviar {quantos} trabalho(s) para:"))
        lay.addWidget(self.list, 1)
        lay.addLayout(botoes)
        linha_modelo = QHBoxLayout()
        linha_modelo.addWidget(QLabel("Modelo de folha:"))
        linha_modelo.addWidget(self.modelo, 1)
        lay.addLayout(linha_modelo)
        lay.addWidget(bb)
        self._encher()

    def _encher(self, escolher: str = "") -> None:
        self.dests = D.all_destinations(self.settings)
        self.list.clear()
        for d in self.dests:
            self.list.addItem(d.label())
        if self.dests:
            alvo = next((i for i, d in enumerate(self.dests) if d.name == escolher), 0)
            self.list.setCurrentRow(alvo)

    def _novo(self) -> None:
        dlg = DestinationEditor(None, self.settings, self)
        if dlg.exec() == QDialog.Accepted:
            d = dlg.destination()
            D.save_destinations(self.settings, self.dests + [d])
            self._encher(d.name)

    def _editar(self) -> None:
        i = self.list.currentRow()
        if not 0 <= i < len(self.dests):
            return
        dlg = DestinationEditor(self.dests[i], self.settings, self)
        if dlg.exec() == QDialog.Accepted:
            self.dests[i] = dlg.destination()
            D.save_destinations(self.settings, self.dests)
            self._encher(self.dests[i].name)

    def _remover(self) -> None:
        i = self.list.currentRow()
        if not 0 <= i < len(self.dests):
            return
        del self.dests[i]
        D.save_destinations(self.settings, self.dests)
        self._encher()

    def _ok(self) -> None:
        if self.chosen() is None:
            QMessageBox.information(self, "Enviar impressão", "Cadastre um destino primeiro (Novo…).")
            return
        self.accept()

    def chosen(self) -> D.Destination | None:
        i = self.list.currentRow()
        return self.dests[i] if 0 <= i < len(self.dests) else None

    def chosen_template(self) -> str:
        return self.modelo.currentData() or ""


class IdentifyDialog(QDialog):
    """De quem é este trabalho: escreva, escolha um exame do banco ou leia o cabeçalho (OCR).

    0.80: o OCR é embutido (RapidOCR) e o texto lido é comparado com os pacientes do banco; os que
    combinam entram no alto da lista, e o mais provável já vem escolhido quando a folga é clara.
    """

    def __init__(self, nome: str, ident: str, candidatos: list[dict] | None = None,
                 ler_ocr=None, parent=None, estudos_fn=None):
        super().__init__(parent)
        self.setWindowTitle("Identificar o paciente")
        self.resize(680, 500)
        self.candidatos = list(candidatos or [])
        self.escolhido = ""                 # study_uid do exame escolhido
        self.estudos_fn = estudos_fn
        self.origem_ocr = False
        self.nome = QLineEdit(nome)
        self.ident = QLineEdit(ident)
        f = QFormLayout()
        f.addRow("Nome:", self.nome)
        f.addRow("ID:", self.ident)
        self.l_lista = QLabel()
        self.lista = QListWidget()
        self.lista.itemSelectionChanged.connect(self._escolher)
        self.b_ocr = QPushButton("Ler o cabeçalho da folha (OCR)")
        self.b_ocr.clicked.connect(lambda: self._ocr(ler_ocr))
        from ipe.printing.ocr import available, motivo_indisponivel
        if ler_ocr is None:
            self.b_ocr.setEnabled(False)
            self.b_ocr.setToolTip("Este trabalho não tem folha para ler.")
        elif not available():
            self.b_ocr.setEnabled(False)
            self.b_ocr.setToolTip(motivo_indisponivel())
        else:
            self.b_ocr.setToolTip("Lê o texto gravado no alto da primeira folha e procura o paciente "
                                  "no banco. É sugestão: confira antes de confirmar.")
        self.lido = QPlainTextEdit()
        self.lido.setReadOnly(True)
        self.lido.setMaximumHeight(90)
        self.lido.setVisible(False)
        self.l_lido = QLabel("Texto lido no cabeçalho:")
        self.l_lido.setVisible(False)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        aviso = QLabel("A impressão DICOM não traz nome nem ID — o que aparece aqui veio do "
                       "rótulo da sessão, quando a modalidade escreve algo nele.")
        aviso.setWordWrap(True)
        lay.addWidget(aviso)
        lay.addLayout(f)
        lay.addWidget(self.l_lista)
        lay.addWidget(self.lista, 1)
        lay.addWidget(self.b_ocr)
        lay.addWidget(self.l_lido)
        lay.addWidget(self.lido)
        lay.addWidget(bb)
        self._preencher_lista()

    def _preencher_lista(self) -> None:
        from ipe.printing.matching import describe
        self.lista.blockSignals(True)
        self.lista.clear()
        for c in self.candidatos:
            texto = describe(c)
            if c.get("ocr"):
                texto = f"OCR {c['score'] * 100:.0f}% · {texto}"
            self.lista.addItem(texto)
        self.lista.blockSignals(False)
        tem = bool(self.candidatos)
        self.lista.setVisible(tem)
        self.l_lista.setVisible(tem)
        ocr = any(c.get("ocr") for c in self.candidatos)
        self.l_lista.setText("Pacientes do banco que combinam com o cabeçalho, e exames do mesmo aparelho "
                             "e horário (clique para usar):" if ocr else
                             "Exames do banco do mesmo aparelho e horário (clique para usar):")

    def _escolher(self) -> None:
        i = self.lista.currentRow()
        if not 0 <= i < len(self.candidatos):
            return
        c = self.candidatos[i]
        self.nome.setText(c.get("patient_name", ""))
        self.ident.setText(c.get("patient_id", ""))
        self.escolhido = c.get("study_uid", "")

    def _ocr(self, ler) -> None:
        if ler is None:
            return
        from PySide6.QtWidgets import QApplication
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            texto = ler()
        except Exception as e:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "OCR", f"Não deu para ler: {e}")
            return
        QApplication.restoreOverrideCursor()
        from ipe.printing.ocr import combinar, escolher, guess
        self.lido.setPlainText(texto.strip() or "(nada)")
        self.lido.setVisible(True)
        self.l_lido.setVisible(True)
        achados = []
        if texto.strip() and self.estudos_fn is not None:
            try:
                achados = combinar(texto, self.estudos_fn())
            except Exception:  # noqa: BLE001
                log.exception("comparar o OCR com o banco")
        nome, ident = guess(texto)
        if not achados and not nome and not ident:
            QMessageBox.information(self, "OCR", "Não consegui ler um nome nem um ID no cabeçalho da "
                                    "folha. O texto lido está na janela, para você conferir.")
            return
        self.origem_ocr = True
        if achados:
            ja = {a["study_uid"] for a in achados}
            self.candidatos = achados + [c for c in self.candidatos if c.get("study_uid") not in ja]
            self._preencher_lista()
            if escolher(achados) is not None:
                self.lista.setCurrentRow(0)          # o mais provável já escolhido; confira e OK
                return
        if nome:
            self.nome.setText(nome)
        if ident:
            self.ident.setText(ident)


# ---------------------------------------------------------------------------
# a lista
# ---------------------------------------------------------------------------

#: (chave, título, tipo) — o tipo diz como o filtro da coluna lê o valor (ver table_filter)
COLUNAS_DEF = [("origem", "Origem", "text"), ("paciente", "Paciente", "text"), ("id", "ID", "text"),
               ("modalidade", "Modalidade", "text"), ("de_onde", "De onde veio", "text"), ("chegada", "Chegada", "datetime"),
               ("folhas", "Folhas", "int"), ("imagens", "Imagens", "int"), ("filme", "Filme", "text"),
               ("situacao", "Situação", "text"), ("destino", "Último destino", "text")]
COLUNAS = [c[1] for c in COLUNAS_DEF]
CHAVES = [c[0] for c in COLUNAS_DEF]
KINDS = [c[2] for c in COLUNAS_DEF]
COL_PACIENTE = CHAVES.index("paciente")
LINHA = Qt.UserRole + 1          # no item da coluna 0: o índice da linha em self.rows


class _Item(QTableWidgetItem):
    """Célula que ordena pelo valor guardado (data, número) e, sem ele, pelo texto sem acento."""

    def __lt__(self, other) -> bool:
        a, b = self.data(Qt.UserRole), other.data(Qt.UserRole)
        if a is not None and b is not None:
            try:
                return a < b
            except TypeError:
                pass
        return fold(self.text()) < fold(other.text())


class PrintsTab(QWidget):
    open_study = Signal(str)             # abrir o exame criado com as folhas
    open_film = Signal(int)              # abrir um filme montado aqui, no compositor
    status_message = Signal(str)
    settings_requested = Signal()        # abrir as configurações de impressão
    release_requested = Signal(list)     # soltar os trabalhos parados, pelo caminho normal
    dashboard_requested = Signal()       # painel de filmes e impressões
    identified = Signal(object)          # paciente confirmado à mão: a janela segue a regra

    def __init__(self, repo, settings, net=None, parent=None):
        super().__init__(parent)
        self.repo, self.settings, self.net = repo, settings, net
        self.rows: list[dict] = []
        self._folha = 0
        self._held = None

        self.filtro = QLineEdit(placeholderText="Procurar (paciente, AE, rótulo)")
        self.filtro.textChanged.connect(self.refresh)
        self.tipo = QComboBox()
        for texto, dado in (("Tudo", ""), ("Recebidos das modalidades", "scp"),
                            ("Montados no programa", "film"),
                            ("Filme que veio no exame", "aw"),
                            ("Ainda não enviados", "new"), ("Já enviados", "sent"),
                            ("Parados, esperando liberação", "held")):
            self.tipo.addItem(texto, dado)
        self.tipo.currentIndexChanged.connect(self.refresh)
        b_atualizar = QPushButton("Atualizar")
        b_atualizar.clicked.connect(self.refresh)
        self.b_enviar = QPushButton("Enviar para…")
        self.b_enviar.clicked.connect(self.send_selected)
        self.b_abrir = QPushButton("Abrir")
        self.b_abrir.clicked.connect(self.open_selected)
        self.b_id = QPushButton("Identificar paciente…")
        self.b_id.clicked.connect(self.identify_selected)
        self.b_juntar = QPushButton("Juntar como páginas")
        self.b_juntar.setToolTip("As folhas escolhidas viram páginas de um trabalho só (o que chegou primeiro), "
                                 "na ordem de chegada")
        self.b_juntar.clicked.connect(self.juntar_selecionados)
        self.b_apagar = QPushButton("Apagar")
        self.b_apagar.clicked.connect(self.delete_selected)
        self.b_reimprimir = QPushButton("Reimprimir…")
        self.b_reimprimir.setToolTip("Manda de novo cada trabalho escolhido para o último destino dele "
                                     "(dá para escolher vários)")
        self.b_reimprimir.clicked.connect(self.reprint_selected)
        self.b_historico = QPushButton("Histórico…")
        self.b_historico.setToolTip("Todos os envios deste trabalho: quando, para onde e por quem")
        self.b_historico.clicked.connect(self.show_history)
        b_painel = QPushButton("Painel…")
        b_painel.setToolTip("Painel de filmes e impressões: % impressos, tempos, por modalidade e usuário")
        b_painel.clicked.connect(self.dashboard_requested.emit)
        b_config = QPushButton("Configurações…")
        b_config.setToolTip("Servidores de impressão, destinos, regras e modelos de folha")
        b_config.clicked.connect(self.settings_requested.emit)
        self.faixa_origens = QLabel()
        self.faixa_origens.setWordWrap(True)
        self.faixa_origens.setStyleSheet(
            "background:#4a3c14; color:#f0dca0; padding:6px; border-radius:4px;")
        self.faixa_origens.setVisible(False)
        self.b_origens = QPushButton("Cadastrar origens…")
        self.b_origens.clicked.connect(self.settings_requested.emit)
        self.b_origens.setVisible(False)
        self.b_parados = QPushButton("Parados…")
        self.b_parados.setToolTip("O que chegou e não foi encaminhado, por aparelho")
        self.b_parados.clicked.connect(self.open_held)
        aviso = QHBoxLayout()
        aviso.addWidget(self.faixa_origens, 1)
        aviso.addWidget(self.b_origens)

        # duas linhas: a busca em cima (com espaço para escrever), as ações sobre o trabalho embaixo
        topo = QHBoxLayout()
        topo.addWidget(self.filtro, 1)
        topo.addWidget(self.tipo)
        for b in (b_atualizar, b_painel, b_config):
            topo.addWidget(b)
        acoes = QHBoxLayout()
        for b in (self.b_abrir, self.b_enviar, self.b_reimprimir, self.b_historico, self.b_id,
                  self.b_juntar, self.b_parados, self.b_apagar):
            acoes.addWidget(b)
        acoes.addStretch(1)

        # filtros e ordem das colunas como no banco: caixa de filtro sob cada título, botão direito
        # no título para filtrar por valores e escolher colunas, arrastar o título muda a ordem
        self.table = QTableWidget(0, len(COLUNAS))
        self.cab = FilterHeader(self.table)
        self.table.setHorizontalHeader(self.cab)
        self.table.setHorizontalHeaderLabels(COLUNAS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._mostrar)
        self.table.doubleClicked.connect(self.open_selected)
        colunas_ajustaveis(self.table)
        self.filtros_texto: dict[int, str] = {}
        self.filtros_valor: dict[int, set[str]] = {}
        self._ordem: tuple[int, Qt.SortOrder] | None = None    # None = mais recentes primeiro
        self._aplicando = False
        self.cab.setSectionsMovable(True)
        self.cab.setSortIndicator(-1, Qt.DescendingOrder)
        self.cab.sectionClicked.connect(self._ordenar_por)
        self.cab.setContextMenuPolicy(Qt.CustomContextMenu)
        self.cab.customContextMenuRequested.connect(self._menu_cabecalho)
        self.cab.sectionMoved.connect(lambda *_: self._salvar_colunas())
        self._t_larguras = QTimer(self)
        self._t_larguras.setSingleShot(True)
        self._t_larguras.setInterval(600)
        self._t_larguras.timeout.connect(self._salvar_larguras)
        self.cab.sectionResized.connect(lambda *_: None if self._aplicando else self._t_larguras.start())
        self.cab.set_filter_boxes(len(COLUNAS))
        self.cab.filter_changed.connect(self._filtro_texto)
        self.contagem = QLabel("")
        self.b_limpar = QPushButton("Limpar filtros")
        self.b_limpar.clicked.connect(self.clear_filters)
        self.b_limpar.setEnabled(False)
        self._aplicar_colunas()

        self.preview = QLabel("Selecione um trabalho para ver a folha.")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumWidth(280)
        self.preview.setStyleSheet("background:#111; color:#aaa;")
        self.detalhes = QLabel("")
        self.detalhes.setWordWrap(True)
        self.detalhes.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.envios_label = QLabel("")          # histórico de envios do trabalho escolhido (0.84)
        self.envios_label.setWordWrap(True)
        self.envios_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.b_anterior = QPushButton("◀")
        self.b_proxima = QPushButton("▶")
        self.b_anterior.clicked.connect(lambda: self._virar(-1))
        self.b_proxima.clicked.connect(lambda: self._virar(1))
        self.folha_label = QLabel("")
        navegar = QHBoxLayout()
        navegar.addWidget(self.b_anterior)
        navegar.addWidget(self.folha_label, 1, Qt.AlignCenter)
        navegar.addWidget(self.b_proxima)
        direita = QWidget()
        dl = QVBoxLayout(direita)
        dl.setContentsMargins(6, 0, 0, 0)
        dl.addWidget(self.preview, 1)
        dl.addLayout(navegar)
        dl.addWidget(self.detalhes)
        dl.addWidget(self.envios_label)

        div = QSplitter(Qt.Horizontal)
        esquerda = QWidget()
        el = QVBoxLayout(esquerda)
        el.setContentsMargins(0, 0, 0, 0)
        el.addWidget(self.table)
        rodape = QHBoxLayout()
        rodape.addWidget(self.contagem, 1)
        rodape.addWidget(self.b_limpar)
        el.addLayout(rodape)
        div.addWidget(esquerda)
        div.addWidget(direita)
        div.setStretchFactor(0, 5)
        div.setStretchFactor(1, 3)
        lay = QVBoxLayout(self)
        lay.addLayout(aviso)
        lay.addLayout(topo)
        lay.addLayout(acoes)
        lay.addWidget(div, 1)
        self.refresh()

    # ------------------------------------------------------------ lista
    def refresh(self) -> None:
        texto = self.filtro.text().strip().lower()
        so = self.tipo.currentData()
        linhas: list[dict] = []
        problemas: list[str] = []

        def tenta(nome, fn):
            """Uma fonte que falha não pode derrubar a lista inteira — nem a aba."""
            try:
                return fn()
            except Exception as e:  # noqa: BLE001
                log.exception("lista de impressões: %s", nome)
                problemas.append(f"{nome}: {e}")
                return []
        for r in tenta("trabalhos recebidos", self.repo.print_jobs):
            linhas.append(dict(r, kind="scp"))
        from ipe.printing import aw_film as AW
        linhas.extend(tenta("filme que veio no exame", lambda: AW.studies(self.repo)))
        for f in tenta("filmes montados aqui", self.repo.films):
            linhas.append({"kind": "film", "id": f["id"], "source": "film", "uid": "",
                           "patient_name": f["patient_name"], "patient_id": "", "calling_ae": "",
                           "label": f["name"], "received_at": f["updated_at"], "sheets": f["sheets"],
                           "images": f["images"], "film_size": "", "status":
                           "sent" if f.get("printed_at") else "new", "destination": "", "folder": "",
                           "study_uid": (f["study_uids"] or [""])[0], "message": "",
                           "id_source": f.get("id_source", "") or "", "patient_id": f.get("patient_id", "") or ""})
        self._modalidade_dos_estudos(linhas)
        if so in ("scp", "film", "aw"):
            linhas = [r for r in linhas if r["kind"] == so]
        elif so in ("new", "sent"):
            linhas = [r for r in linhas if r["status"] == so]
        elif so == "held":
            from ipe.printing import held as H
            linhas = H.held(linhas)
        if texto:
            linhas = [r for r in linhas
                      if texto in " ".join(str(r.get(k, "")) for k in
                                           ("patient_name", "patient_id", "calling_ae", "label")).lower()]
        linhas.sort(key=lambda r: r.get("received_at") or datetime.min, reverse=True)
        self.rows = linhas          # ANTES da faixa: ela lê self.rows e leria a lista anterior
        self._atualiza_faixa_origens()
        if problemas:
            detalhe = " · ".join(problemas[:2])
            self.status_message.emit(f"Parte da lista de impressões não pôde ser lida: {detalhe}")
        self.table.setRowCount(0)
        self.table.setRowCount(len(linhas))
        for i, r in enumerate(linhas):
            quando = r.get("received_at")
            brutos = [None, None, None, None, None,
                      quando.strftime("%Y%m%d%H%M%S") if isinstance(quando, datetime) else "",
                      int(r.get("sheets") or 0), int(r.get("images") or 0), None, None, None]
            valores = [
                {"scp": "Recebido", "aw": "Veio no exame"}.get(r["kind"], "Montado aqui"),
                r.get("patient_name") or (r.get("label") or "(sem identificação)"),
                r.get("patient_id", ""),
                "/".join(m for m in str(r.get("modality") or "").split("\\") if m),
                self._de_onde(r),
                quando.strftime("%d/%m/%Y %H:%M") if isinstance(quando, datetime) else "",
                str(r.get("sheets", 0)), str(r.get("images", 0)), r.get("film_size", ""),
                self._situacao(r),
                r.get("destination", ""),
            ]
            for c, v in enumerate(valores):
                item = _Item(v)
                if brutos[c] is not None:
                    item.setData(Qt.UserRole, brutos[c])
                if c == 0:
                    item.setData(LINHA, i)
                if c == 1 and r["kind"] == "scp":
                    dica = ORIGEM_PACIENTE.get(r.get("id_source") or "", "")
                    if not r.get("patient_name"):
                        dica = "A impressão DICOM não manda nome nem ID; use “Identificar paciente”."
                    if dica:
                        item.setToolTip(dica)
                self.table.setItem(i, c, item)
        if self._ordem is not None:
            self.table.sortItems(*self._ordem)
        self._ajusta_colunas()
        self._aplicar_filtros()

    def _modalidade_dos_estudos(self, linhas: list[dict]) -> None:
        """Filme do compositor e filme do exame: a modalidade é a dos estudos dele."""
        faltam = {r.get("study_uid") for r in linhas
                  if r.get("kind") in ("film", "aw") and not r.get("modality") and r.get("study_uid")}
        if not faltam or not hasattr(self.repo, "study_modalities"):
            return
        try:
            mods = self.repo.study_modalities(list(faltam))
        except Exception:  # noqa: BLE001
            log.exception("modalidade dos filmes")
            return
        for r in linhas:
            if r.get("kind") in ("film", "aw") and not r.get("modality"):
                r["modality"] = mods.get(r.get("study_uid") or "", "")

    def _ajusta_colunas(self) -> None:
        """Larguras salvas por você; as que não foram mexidas vão pelo conteúdo."""
        salvas = self.settings.get("impressoes.larguras", {}) or {}
        self._aplicando = True
        try:
            for c, chave in enumerate(CHAVES):
                if chave in salvas:
                    self.table.setColumnWidth(c, max(28, int(salvas[chave])))
                    continue
                self.table.resizeColumnToContents(c)
                largura = min(220, max(60, self.table.columnWidth(c) + 14))
                if c == COL_PACIENTE:
                    largura = max(230, largura)
                self.table.setColumnWidth(c, largura)
        finally:
            self._aplicando = False
        self.cab.adjust_positions()

    # ------------------------------------------------------------ colunas e filtros (como no banco)
    def colunas_visiveis(self) -> list[str]:
        salvas = self.settings.get("impressoes.colunas") or CHAVES
        cols = [c for c in salvas if c in CHAVES]
        # coluna que nasceu depois de ele arrumar as colunas entra à vista, ao lado da vizinha
        # (esconder é escolha dele; coluna que ele nunca viu não foi escondida por ele)
        antes_da_084 = [k for k in CHAVES if k != "modalidade"]      # as colunas da 0.82/0.83
        vistas = set(self.settings.get("impressoes.colunas_vistas") or
                     (antes_da_084 if self.settings.get("impressoes.colunas") else CHAVES))
        for i, k in enumerate(CHAVES):
            if k not in vistas and k not in cols:
                antes = CHAVES[i - 1] if i else ""
                cols.insert(cols.index(antes) + 1 if antes in cols else len(cols), k)
        if "paciente" not in cols:
            cols.insert(0, "paciente")
        return cols

    def _aplicar_colunas(self) -> None:
        """Mostra as colunas escolhidas, na ordem salva."""
        vis = self.colunas_visiveis()
        self._aplicando = True
        try:
            for c, chave in enumerate(CHAVES):
                self.table.setColumnHidden(c, chave not in vis)
            for pos, chave in enumerate(vis):
                self.cab.moveSection(self.cab.visualIndex(CHAVES.index(chave)), pos)
        finally:
            self._aplicando = False
        self.cab.adjust_positions()

    def _salvar_colunas(self) -> None:
        if self._aplicando:
            return
        ordem = sorted((self.cab.visualIndex(c), k) for c, k in enumerate(CHAVES)
                       if not self.table.isColumnHidden(c))
        self.settings.set("impressoes.colunas", [k for _v, k in ordem])
        self.settings.set("impressoes.colunas_vistas", list(CHAVES))
        self.settings.save()

    def _salvar_larguras(self) -> None:
        larguras = dict(self.settings.get("impressoes.larguras", {}) or {})
        for c, k in enumerate(CHAVES):
            if not self.table.isColumnHidden(c):
                larguras[k] = self.table.columnWidth(c)
        self.settings.set("impressoes.larguras", larguras)
        self.settings.save()

    def set_coluna_visivel(self, chave: str, ligar: bool) -> None:
        if chave == "paciente":
            return                                  # o paciente sempre aparece
        c = CHAVES.index(chave)
        self.table.setColumnHidden(c, not ligar)
        if not ligar:                               # coluna escondida não pode ficar filtrando
            self._limpar_coluna(c)
        self._salvar_colunas()
        self.cab.adjust_positions()

    def _restaurar_colunas(self) -> None:
        self.settings.set("impressoes.colunas", list(CHAVES))
        self.settings.set("impressoes.colunas_vistas", list(CHAVES))
        self.settings.set("impressoes.larguras", {})
        self.settings.save()
        self._aplicar_colunas()
        self._ajusta_colunas()

    def _ordenar_por(self, col: int) -> None:
        """Clique no título: ordena; o segundo clique inverte; o terceiro volta à ordem de chegada."""
        if self._ordem is None or self._ordem[0] != col:
            self._ordem = (col, Qt.AscendingOrder)
        elif self._ordem[1] == Qt.AscendingOrder:
            self._ordem = (col, Qt.DescendingOrder)
        else:
            self._ordem = None
        if self._ordem is None:
            self.cab.setSortIndicator(-1, Qt.DescendingOrder)
            self.refresh()
            return
        self.cab.setSortIndicator(*self._ordem)
        self.table.sortItems(*self._ordem)

    def _filtro_texto(self, col: int, texto: str) -> None:
        if texto.strip():
            self.filtros_texto[col] = texto
        else:
            self.filtros_texto.pop(col, None)
        self._aplicar_filtros()

    def set_column_filter(self, chave: str, texto: str) -> None:
        """Escreve na caixa de filtro de uma coluna e aplica na hora."""
        col = CHAVES.index(chave)
        ed = self.cab.editor(col)
        ed.blockSignals(True)
        ed.setText(texto)
        ed.blockSignals(False)
        self._filtro_texto(col, texto)

    def valores_da_coluna(self, col: int) -> list[str]:
        vals = {self.table.item(i, col).text() for i in range(self.table.rowCount())
                if self.table.item(i, col) is not None}
        return sorted(vals, key=lambda v: (v == "", fold(v)))

    def filtrar_valores(self, col: int) -> None:
        dlg = ValueFilterDialog(COLUNAS[col], self.valores_da_coluna(col), self.filtros_valor.get(col), self)
        if dlg.exec():
            self.set_value_filter(col, dlg.chosen())

    def set_value_filter(self, col: int, valores: set[str] | None) -> None:
        if valores is None:
            self.filtros_valor.pop(col, None)
        else:
            self.filtros_valor[col] = set(valores)
        self._aplicar_filtros()

    def _limpar_coluna(self, col: int) -> None:
        ed = self.cab.editor(col)
        ed.blockSignals(True)
        ed.clear()
        ed.blockSignals(False)
        self.filtros_texto.pop(col, None)
        self.filtros_valor.pop(col, None)
        self._aplicar_filtros()

    def clear_filters(self) -> None:
        self.cab.clear_boxes()
        self.filtros_texto.clear()
        self.filtros_valor.clear()
        self._aplicar_filtros()

    @property
    def filtros_ativos(self) -> bool:
        return bool(self.filtros_texto or self.filtros_valor)

    def _passa(self, linha: int) -> bool:
        for col, vals in self.filtros_valor.items():
            it = self.table.item(linha, col)
            if (it.text() if it else "") not in vals:
                return False
        for col, texto in self.filtros_texto.items():
            it = self.table.item(linha, col)
            if it is None or not match(texto, KINDS[col], it.data(Qt.UserRole), it.text()):
                return False
        return True

    def _aplicar_filtros(self) -> None:
        mostradas = 0
        for i in range(self.table.rowCount()):
            ok = self._passa(i)
            self.table.setRowHidden(i, not ok)
            mostradas += ok
        total = self.table.rowCount()
        if self.filtros_ativos:
            self.contagem.setText(f"Mostrando {mostradas} de {total} trabalho(s) — filtros de coluna ativos")
        else:
            self.contagem.setText(f"Trabalhos na lista: {total}")
        self.b_limpar.setEnabled(self.filtros_ativos)
        self._mostrar()

    def _menu_cabecalho(self, pos) -> None:
        col = self.cab.logicalIndexAt(pos)
        menu = QMenu(self)
        if col >= 0:
            titulo = COLUNAS[col]
            a = QAction(f"Filtrar valores de \"{titulo}\"…", menu)
            a.triggered.connect(lambda: self.filtrar_valores(col))
            menu.addAction(a)
            if col in self.filtros_texto or col in self.filtros_valor:
                a = QAction(f"Remover filtro de \"{titulo}\"", menu)
                a.triggered.connect(lambda: self._limpar_coluna(col))
                menu.addAction(a)
        a = QAction("Limpar todos os filtros", menu)
        a.setEnabled(self.filtros_ativos)
        a.triggered.connect(self.clear_filters)
        menu.addAction(a)
        menu.addSeparator()
        sub = menu.addMenu("Colunas")
        for c, (chave, titulo, _k) in enumerate(COLUNAS_DEF):
            a = QAction(titulo, sub, checkable=True, checked=not self.table.isColumnHidden(c))
            a.setEnabled(chave != "paciente")
            a.toggled.connect(lambda on, k=chave: self.set_coluna_visivel(k, on))
            sub.addAction(a)
        sub.addSeparator()
        a = QAction("Restaurar colunas padrão", sub)
        a.triggered.connect(self._restaurar_colunas)
        sub.addAction(a)
        menu.exec(self.cab.mapToGlobal(pos))

    def _situacao(self, r: dict) -> str:
        """Na lista / Enviado / Erro — e "Esperando paciente" quando o OCR não identificou."""
        status = r.get("status", "new") or "new"
        if status == "new" and r.get("kind") == "film" and r.get("id_source") == "aguardando":
            return "Esperando paciente"           # 0.89: filme montado com imagens recebidas
        if status == "new" and r.get("kind", "scp") == "scp":
            # 0.86: o motivo de estar parado, e não só "Na lista" — o filme identificado pelo OCR
            # que esperava o cadastro do aparelho parecia OCR que não tinha funcionado
            from ipe.printing import held as H
            try:
                motivo = H.reason(self.settings, r)
            except Exception:  # noqa: BLE001
                motivo = ""
            return {H.SEM_PACIENTE: "Esperando paciente",
                    H.SEM_CADASTRO: "Parado: aparelho sem cadastro",
                    H.DESLIGADA: "Parado: origem desligada",
                    H.SEM_REGRA: "Na lista (nenhuma regra)"}.get(motivo, SITUACAO["new"])
        return SITUACAO.get(status, status)

    def _de_onde(self, r: dict) -> str:
        """Nome cadastrado da origem; sem cadastro, o AE com um aviso."""
        if r.get("kind") == "film":
            return "compositor"
        if r.get("kind") == "aw":
            return "veio no exame (estação AW)"
        from ipe.printing import origins as O
        o = O.job_origin(self.settings, r)
        if o is not None and o.registered:
            return o.name
        return f"{r.get('calling_ae') or '?'} (não cadastrada)"

    def _atualiza_faixa_origens(self) -> None:
        """Avisa quando há filme parado esperando — por falta de cadastro ou de liberação."""
        from ipe.printing import held as H
        from ipe.printing import origins as O
        grupos = H.groups(self.settings, self.rows)   # a faixa não abre arquivo: é só contagem
        pendentes = O.pending(self.settings)
        parados = sum(g.trabalhos for g in grupos)
        self.b_parados.setText(f"Parados ({parados})…" if parados else "Parados…")
        if not parados and not pendentes:
            self.faixa_origens.setVisible(False)
            self.b_origens.setVisible(False)
            return
        partes = []
        if pendentes:
            quem = ", ".join(f"{o.calling_ae or '?'} ({o.remote_host or '?'})" for o in pendentes[:4])
            if len(pendentes) > 4:
                quem = f"{quem}…"
            partes.append(f"{len(pendentes)} origem(ns) sem cadastro: {quem}.")
        if parados:
            partes.append(H.resumo(grupos))
        self.faixa_origens.setText(" ".join(partes))
        self.faixa_origens.setVisible(True)
        self.b_origens.setVisible(bool(pendentes))

    def _carrega_job(self, row: dict):
        """O trabalho no disco, quando existir — é dele que saem as regras de destino."""
        from ipe.printing import jobs as J
        pasta = (row or {}).get("folder", "")
        return J.load(pasta) if pasta else None

    def open_held(self) -> None:
        """A fila dos parados, agrupada por aparelho, com liberação em lote."""
        from ipe.ui.held_dialog import HeldDialog
        dlg = HeldDialog(self.settings, self.rows, self._carrega_job, self)
        dlg.registrar.connect(lambda _ident: self.settings_requested.emit())
        dlg.liberar.connect(self._liberar)
        self._held = dlg
        dlg.exec()
        self._held = None

    def _liberar(self, linhas: list) -> None:
        self.release_requested.emit(list(linhas))

    def held_done(self, enviados: int, falhas: int) -> None:
        """Chamado depois da liberação: atualiza a lista e conta o que saiu."""
        self.refresh()
        if self._held is not None:
            self._held.recarregar(self.rows)
        if falhas:
            self.status_message.emit(f"{enviados} trabalho(s) enviados, {falhas} com erro.")
        else:
            self.status_message.emit(f"{enviados} trabalho(s) enviados.")

    def selected(self) -> list[dict]:
        """As linhas escolhidas, na ordem da tela (que pode estar reordenada ou filtrada)."""
        saida = []
        for vis in sorted({i.row() for i in self.table.selectedIndexes()}):
            if self.table.isRowHidden(vis):
                continue
            it = self.table.item(vis, 0)
            i = it.data(LINHA) if it is not None else None
            if i is not None and 0 <= int(i) < len(self.rows):
                saida.append(self.rows[int(i)])
        return saida

    # ------------------------------------------------------------ pré-visualização
    def _job(self, row: dict) -> tuple[J.PrintJob | None, Path | None]:
        if row.get("kind") == "aw":
            return self._job_aw(row)
        if row.get("kind") != "scp" or not row.get("folder"):
            return None, None
        folder = Path(row["folder"])
        return J.load(folder), folder

    def _job_aw(self, row: dict) -> tuple[J.PrintJob | None, Path | None]:
        """Filme da estação AW: monta uma vez por exame e guarda em cache."""
        from ipe.printing import aw_film as AW
        uid = str(row.get("study_uid") or "")
        cache = self.__dict__.setdefault("_aw_cache", {})
        if uid not in cache:
            try:
                cache[uid] = AW.to_job(self.repo, uid, self._film_root())
            except Exception:  # noqa: BLE001
                log.exception("filme da AW de %s", uid)
                cache[uid] = (None, None)
        return cache[uid]

    def _mostrar(self) -> None:
        sel = self.selected()
        um = sel[0] if len(sel) == 1 else None
        self.b_enviar.setEnabled(bool(sel))
        self.b_reimprimir.setEnabled(bool(sel))
        self.b_historico.setEnabled(bool(um))
        self.b_apagar.setEnabled(bool(sel))
        self.b_juntar.setEnabled(sum(1 for r in sel if r.get("kind") == "scp") >= 2)
        self.b_id.setEnabled(bool(um and (um["kind"] == "scp" or (um["kind"] == "film"
                                                                   and um.get("id_source")))))
        self.b_abrir.setEnabled(bool(um))
        self._detalhes_envios(um)
        if um is None:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Selecione um trabalho para ver a folha.")
            self.detalhes.setText("")
            self.folha_label.setText("")
            return
        if um["kind"] == "film":
            self._mostrar_filme(um)
            return
        job, folder = self._job(um)
        if job is None:
            self.preview.setText("A pasta deste trabalho não está mais aqui.")
            self.detalhes.setText("")
            return
        job.patient_name = um.get("patient_name") or job.patient_name
        self._folha = max(0, min(self._folha, len(job.films) - 1))
        film = job.films[self._folha]
        img = D.sheet_qimage(folder, film, dpi=72)
        pm = QPixmap.fromImage(img).scaled(self.preview.width() or 280, self.preview.height() or 380,
                                           Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setPixmap(pm)
        self.folha_label.setText(f"Folha {self._folha + 1} de {len(job.films)}")
        self.b_anterior.setEnabled(len(job.films) > 1)
        self.b_proxima.setEnabled(len(job.films) > 1)
        mm_w, mm_h = J.sheet_mm(film)
        grade = film.display_format.replace(chr(92), " ")
        linhas = [f"<b>{job.title()}</b>",
                  f"Grade {grade}, filme {film.film_size or '?'} ({mm_w:.0f}×{mm_h:.0f} mm)",
                  f"{job.copies} cópia(s) em {job.medium or '?'}, saída {job.destination or '?'}",
                  f"Rótulo da sessão: {job.label or '(vazio)'}",
                  f"Chegou de {job.calling_ae or '?'} ({job.remote_host or '?'})"]
        if um.get("kind") == "aw":
            linhas = [f"<b>{um.get('patient_name') or ''}</b>",
                      f"Folha da estação AW, {mm_w:.0f}×{mm_h:.0f} mm",
                      f"{um.get('sheets', 0)} folha(s) e {um.get('images', 0)} imagem(ns) no exame",
                      "Veio dentro do exame, não pela impressora DICOM"]
        elif job.server:
            linhas.append(f"Recebido em: {job.server}")
        linhas += [f"Anotação: {a.get('text', '')}" for a in film.annotations[:4]]
        if um.get("message"):
            linhas.append(f"<i>{um['message']}</i>")
        self.detalhes.setText("<br>".join(linhas))

    # ------------------------------------------------------------ histórico de envios (0.84)
    @staticmethod
    def ref_de(r: dict) -> tuple[str, str]:
        """(lista, referência) de um trabalho no histórico de envios."""
        if r.get("kind") == "aw":
            return "aw", str(r.get("study_uid") or "")
        return r.get("kind", "scp"), str(r.get("id", ""))

    def envios(self, r: dict) -> list[dict]:
        if not hasattr(self.repo, "sends"):
            return []
        try:
            return self.repo.sends(*self.ref_de(r))
        except Exception:  # noqa: BLE001
            log.exception("histórico de envios")
            return []

    @staticmethod
    def como_foi(e: dict) -> str:
        from ipe.core.i18n import tr
        return tr({"regra": "pela regra", "reimpressão": "reimpressão", "compositor": "no compositor"}.get(
            e.get("how", ""), "à mão"))

    @classmethod
    def texto_envio(cls, e: dict) -> str:
        """Uma linha de dado (data · destino · quem): não passa pelo catálogo de tradução inteira."""
        from ipe.core.i18n import tr
        quando = e["at"].strftime("%d/%m/%Y %H:%M") if isinstance(e.get("at"), datetime) else ""
        falha = "" if e.get("ok", True) else " — " + tr("FALHOU")
        partes = [quando, e.get("destination") or "?", e.get("user") or "?"]
        return " · ".join(partes) + " (" + cls.como_foi(e) + ")" + falha

    def _detalhes_envios(self, r: dict | None) -> None:
        envios = self.envios(r) if r else []
        if not envios:
            self.envios_label.setText("")
            return
        mais = f"<br>Mais {len(envios) - 3} no Histórico…" if len(envios) > 3 else ""
        txt = "<br>".join(self.texto_envio(e) for e in envios[:3])
        self.envios_label.setText(f"<b>Envios ({len(envios)})</b><br>{txt}{mais}")

    def show_history(self) -> None:
        sel = self.selected()
        if len(sel) != 1:
            return
        r = sel[0]
        envios = self.envios(r)
        dlg = QDialog(self)
        dlg.setWindowTitle("Histórico de envios")
        dlg.resize(720, 360)
        t = QTableWidget(len(envios), 6)
        t.setHorizontalHeaderLabels(["Quando", "Destino", "Quem", "Como", "Modelo de folha", "Resultado"])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for i, e in enumerate(envios):
            quando = e["at"].strftime("%d/%m/%Y %H:%M:%S") if isinstance(e.get("at"), datetime) else ""
            como = self.como_foi(e)
            for j, v in enumerate([quando, e.get("destination", ""), e.get("user", ""), como,
                                   e.get("template") or "como veio",
                                   "ok" if e.get("ok", True) else f"falhou: {e.get('message', '')}"]):
                t.setItem(i, j, QTableWidgetItem(v))
        t.resizeColumnsToContents()
        colunas_ajustaveis(t)
        lay = QVBoxLayout(dlg)
        quem = r.get("patient_name") or r.get("label") or "(sem identificação)"
        lay.addWidget(QLabel(f"<b>{quem}</b> — {len(envios)} envio(s)" if envios else
                             f"<b>{quem}</b> — ainda não foi enviado (o histórico existe desde a 0.84)"))
        lay.addWidget(t, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.button(QDialogButtonBox.Close).setText("Fechar")
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        self._dlg_historico = dlg
        dlg.exec()

    # ------------------------------------------------------------ reimprimir em lote (0.84)
    def ultimo_destino(self, r: dict) -> tuple[D.Destination | None, str]:
        """(destino, modelo) do último envio que deu certo; (None, "") quando nunca saiu."""
        from ipe.printing.dispatch import find_destination
        ok = [e for e in self.envios(r) if e.get("ok", True)]
        candidatos = [(e.get("destination", ""), e.get("template", "")) for e in ok[:1]]
        if r.get("kind") == "scp" and r.get("destination"):
            candidatos.append((r["destination"], ""))
        for nome, modelo in candidatos:
            d = find_destination(self.settings, nome)
            if d is None:                 # o compositor grava o rótulo do destino, não o nome
                d = next((x for x in D.all_destinations(self.settings) if x.label() == nome), None)
            if d is not None:
                return d, modelo
        return None, ""

    def plano_reimpressao(self, linhas: list[dict]) -> tuple[dict, list[dict]]:
        """{(nome do destino, modelo): (destino, [linhas])}, e as que nunca saíram."""
        grupos: dict = {}
        sem: list[dict] = []
        for r in linhas:
            d, modelo = self.ultimo_destino(r)
            if d is None:
                sem.append(r)
                continue
            grupos.setdefault((d.name, modelo), (d, []))[1].append(r)
        return grupos, sem

    def reprint_selected(self, confirmar: bool = True) -> tuple[int, int]:
        from ipe.auth import session as S
        sel = self.selected()
        if not sel or not S.require("print", self):
            return 0, 0
        grupos, sem = self.plano_reimpressao(sel)
        if not grupos:
            QMessageBox.information(self, "Reimprimir", "Nenhum dos trabalhos escolhidos foi enviado "
                                    "antes, então não há destino para repetir. Use “Enviar para…”.")
            return 0, 0
        partes = [(f"para {d.name}, com o modelo {m}: {len(rs)}" if m else f"para {d.name}: {len(rs)}")
                  for (_n, m), (d, rs) in grupos.items()]
        n = sum(len(rs) for _d, rs in grupos.values())
        aviso = f"Reimprimir {n} trabalho(s) — " + "; ".join(partes) + "."
        if sem:
            aviso += f"\n\n{len(sem)} nunca foram enviados e ficam de fora."
        if confirmar and QMessageBox.question(self, "Reimprimir", aviso) != QMessageBox.Yes:
            return 0, 0
        ok = falhas = 0
        for (_n, modelo), (d, rs) in grupos.items():
            a, b = self.send_rows(rs, d, avisar=False, template=modelo, how="reimpressão")
            ok, falhas = ok + a, falhas + b
        if falhas:
            QMessageBox.warning(self, "Reimprimir", f"Reimpressos: {ok}; com erro: {falhas}. Veja o Histórico.")
        else:
            self.status_message.emit(f"Reimpressos: {ok} trabalho(s).")
        return ok, falhas

    def _mostrar_filme(self, um: dict) -> None:
        """Filme do compositor: só a folha desenhada, para olhar. O duplo clique abre o compositor."""
        folhas = self._folhas_do_filme(um)
        self.detalhes.setText("<br>".join([
            f"<b>{um.get('label', '')}</b>",
            f"{um.get('patient_name') or ''}",
            f"{um.get('sheets', 0)} folha(s), {um.get('images', 0)} imagem(ns)",
            "Montado no compositor — duplo clique abre para editar"]))
        if not folhas:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Não deu para desenhar este filme.")
            self.folha_label.setText("")
            self.b_anterior.setEnabled(False)
            self.b_proxima.setEnabled(False)
            return
        self._folha = max(0, min(self._folha, folhas - 1))
        img = self._folha_do_filme(um, self._folha)
        if img is None or img.isNull():
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Não deu para desenhar esta folha.")
        else:
            pm = QPixmap.fromImage(img).scaled(self.preview.width() or 280, self.preview.height() or 380,
                                               Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preview.setPixmap(pm)
        self.folha_label.setText(f"Folha {self._folha + 1} de {folhas}")
        self.b_anterior.setEnabled(folhas > 1)
        self.b_proxima.setEnabled(folhas > 1)

    def _filme(self, um: dict):
        """O filme salvo (guardado enquanto não mudar no banco)."""
        chave = (int(um["id"]), str(um.get("received_at") or ""))
        guardado = self.__dict__.get("_filme_atual")
        if guardado is not None and guardado[0] == chave:
            return guardado[1]
        filme = None
        try:
            from ipe.printing.film import Film
            dados = self.repo.film_data(int(um["id"]))
            filme = Film.from_dict(dados) if dados else None
        except Exception:  # noqa: BLE001
            log.exception("abrir o filme %s para a pré-visualização", um.get("id"))
        self._filme_atual = (chave, filme)
        self._folhas_desenhadas: dict[int, object] = {}
        return filme

    def _folhas_do_filme(self, um: dict) -> int:
        filme = self._filme(um)
        return len(filme.sheets) if filme is not None else 0

    def _folha_do_filme(self, um: dict, i: int):
        filme = self._filme(um)
        if filme is None:
            return None
        if i not in self._folhas_desenhadas:
            from ipe.imaging.series import FrameCache
            from ipe.ui.film.render import FrameSource, render_sheet_image
            if "_fonte_filme" not in self.__dict__:
                self._fonte_filme = FrameSource(self.repo)
                self._cache_filme = FrameCache(max_mb=128)
            try:
                self._folhas_desenhadas[i] = render_sheet_image(filme, i, self._fonte_filme, self._cache_filme,
                                                                self.settings, dpi=60)
            except Exception:  # noqa: BLE001
                log.exception("desenhar a folha %s do filme %s", i, um.get("id"))
                self._folhas_desenhadas[i] = None
        return self._folhas_desenhadas[i]

    def _virar(self, passo: int) -> None:
        self._folha = max(0, self._folha + passo)
        self._mostrar()

    # ------------------------------------------------------------ ações
    def open_selected(self) -> None:
        sel = self.selected()
        if not sel:
            return
        r = sel[0]
        if r["kind"] == "film":
            self.open_film.emit(int(r["id"]))
        elif r.get("study_uid"):
            self.open_study.emit(r["study_uid"])
        else:
            QMessageBox.information(self, "Impressões",
                                    "Este trabalho não foi guardado como exame no banco.")

    def identify_selected(self) -> None:
        sel = self.selected()
        if len(sel) == 1 and sel[0]["kind"] == "film" and sel[0].get("id_source"):
            self._identificar_filme_montado(sel[0])
            return
        if len(sel) != 1 or sel[0]["kind"] != "scp":
            return
        r = sel[0]
        job, folder = self._job(r)
        from ipe.printing.matching import candidates
        sugestoes = candidates(self.repo, job) if job is not None else []

        def ler_cabecalho() -> str:
            """O texto que veio pronto (anotação, rótulo), o alto e o rodapé da primeira folha."""
            from ipe.printing.arrival import texto_sem_ocr
            from ipe.printing.ocr import read_header
            if job is None:
                return ""
            partes = [texto_sem_ocr(job)]
            if job.films:
                folha = J.compose_sheet(folder, job.films[0], width=1600)
                partes += [read_header(folha, parte="cima"), read_header(folha, parte="baixo")]
            return "\n".join(p for p in partes if p and p.strip())

        dlg = IdentifyDialog(r.get("patient_name", ""), r.get("patient_id", ""), sugestoes,
                             ler_cabecalho, self, estudos_fn=self.repo.studies_for_ocr)
        if dlg.exec() != QDialog.Accepted:
            return
        nome, ident = dlg.nome.text().strip(), dlg.ident.text().strip()
        campos = {"patient_name": nome, "patient_id": ident, "id_source": "manual"}
        if dlg.escolhido:
            campos["id_source"] = "exame"
        # 0.84: com o paciente, a modalidade passa a ser a do exame dele (regra por modalidade)
        from ipe.printing.modalidade import descobrir
        campos["modality"] = descobrir(self.repo, self.settings, dict(r, patient_id=ident)) or r.get("modality", "")
        self.repo.update_print_job(r["id"], **campos)
        if job is not None and folder is not None:
            job.patient_name, job.patient_id = nome, ident
            job.id_source = campos["id_source"]
            job.modality = campos["modality"]
            J.save(job, folder.parent)
        self.refresh()
        atual = self.repo.print_job(r["id"]) if hasattr(self.repo, "print_job") else None
        self.identified.emit(atual or dict(r, **campos))

    def _identificar_filme_montado(self, r: dict) -> None:
        """O mesmo "Identificar paciente" do filme impresso, para o filme montado com as imagens que
        chegaram à porta da impressora (0.89). O OCR lê o texto gravado nas primeiras imagens."""
        from ipe.printing import arrival
        from ipe.printing.film import Film
        dados = self.repo.film_data(int(r["id"])) or {}
        filme = Film.from_dict(dados) if dados else None

        def ler() -> str:
            if filme is None:
                return ""
            textos = []
            for _onde, f in arrival.fontes_do_filme(self.repo, filme, quantas=1):
                if len(textos) == 2:                 # alto e rodapé; a imagem inteira fica de fora
                    break
                textos.append(f())
            return "\n".join(t for t in textos if t and t.strip())
        pac = (dados.get("paciente") or {}) if dados else {}
        nome = pac.get("patient_name", "") or (r.get("patient_name", "") if r.get("id_source") != "aguardando" else "")
        dlg = IdentifyDialog(nome, pac.get("patient_id", "") or r.get("patient_id", ""), [], ler, self,
                             estudos_fn=self.repo.studies_for_ocr)
        if dlg.exec() != QDialog.Accepted:
            return
        nome, ident = dlg.nome.text().strip(), dlg.ident.text().strip()
        origem = "exame" if dlg.escolhido else "manual"
        self.repo.set_film_patient(int(r["id"]), nome, ident, origem)
        self.refresh()
        if r.get("id_source") == "aguardando" and (r.get("status") or "new") == "new":
            self.identified.emit(dict(r, kind="film", patient_name=nome, patient_id=ident, id_source=origem))

    def delete_selected(self) -> None:
        sel = self.selected()
        if not sel:
            return
        recebidos = [r for r in sel if r["kind"] == "scp"]
        filmes = [r for r in sel if r["kind"] == "film"]
        do_exame = [r for r in sel if r["kind"] == "aw"]
        apagaveis = len(recebidos) + len(filmes)
        if not apagaveis:
            QMessageBox.information(self, "Apagar", "O filme que veio no exame não se apaga daqui: "
                                                    "ele é do exame. Apague o exame no banco.")
            return
        aviso = f"Apagar {apagaveis} trabalho(s) da lista?\nOs exames já guardados no banco não são apagados."
        if do_exame:
            resto = f"{len(do_exame)} filme(s) que vieram no exame ficam como estão."
            aviso = aviso + "\n\n" + resto
        if QMessageBox.question(self, "Apagar", aviso) != QMessageBox.Yes:
            return
        import shutil
        for r in recebidos + filmes:
            if hasattr(self.repo, "delete_sends"):
                self.repo.delete_sends(*self.ref_de(r))
        for r in recebidos:
            pasta = self.repo.delete_print_job(r["id"])
            if pasta:
                shutil.rmtree(pasta, ignore_errors=True)
        for r in filmes:
            self.repo.delete_film(r["id"])
        self.refresh()
        self.status_message.emit(f"{apagaveis} trabalho(s) apagado(s) da lista de impressões.")

    def juntar_selecionados(self, confirmar: bool = True) -> dict | None:
        """0.99.6: folhas recebidas separadas → páginas de um trabalho só (o que chegou primeiro)."""
        from ipe.printing import juntar as JUN
        sel = [r for r in self.selected() if r.get("kind") == "scp"]
        if len(sel) < 2:
            return None
        sel.sort(key=lambda r: JUN._quando(r.get("received_at")) or datetime.min)
        base, resto = sel[0], sel[1:]
        avisos = []
        if any(not JUN.mesma_origem(base, r) for r in resto):
            avisos.append("vieram de origens diferentes")
        if any(JUN.mesmo_paciente(base, r) is False for r in resto):
            avisos.append("o paciente identificado não é o mesmo em todas")
        if any(r.get("status") != "new" for r in sel):
            avisos.append("alguma já foi enviada (o histórico de envio das juntadas sai junto)")
        if confirmar:
            texto = (f"Juntar {len(sel)} trabalhos como páginas de “{base.get('patient_name') or base.get('label') or 'um trabalho'}”?"
                     + ("\n\nAtenção: " + "; ".join(avisos) + "." if avisos else ""))
            if QMessageBox.question(self, "Juntar como páginas", texto) != QMessageBox.Yes:
                return None
        sink = getattr(self.net, "sink", None)
        try:
            novo = JUN.juntar(self.repo, base, resto, sink, getattr(sink, "storage", None))
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Juntar como páginas", f"Não deu para juntar: {e}")
            return None
        self.refresh()
        self.status_message.emit(f"{len(sel)} trabalhos juntados: {novo.get('sheets', 0)} folha(s) em um só.")
        return novo

    def send_selected(self) -> None:
        from ipe.auth import session as S
        sel = self.selected()
        if not sel or not S.require("print", self):
            return
        dlg = SendDialog(self.settings, len(sel), self)
        if dlg.exec() != QDialog.Accepted:
            return
        dest = dlg.chosen()
        if dest is None:
            return
        self.send_rows(sel, dest, template=dlg.chosen_template())

    def send_rows(self, linhas: list[dict], dest: D.Destination, avisar: bool = True,
                  template: str = "", how: str = "manual") -> tuple[int, int]:
        """Manda cada trabalho e anota o resultado (e o histórico de envios). Devolve (enviados, falhas).

        `how`: manual, regra ou reimpressão — vai para o histórico, com quem estava no programa."""
        ok = falhas = 0
        from ipe.auth import session as S
        usuario = S.get().username or ""
        S.audit(self.repo, "imprimir", f"impressoes: {len(linhas)} para {dest.label()}")
        local_ae = getattr(self.net, "local_ae", "") if self.net is not None else ""
        for r in linhas:
            try:
                job, folder = self._preparar(r)
                if job is None:
                    raise D.PrintError("Não foi possível montar este trabalho.")
                msg = D.send(job, folder, dest, self.settings, local_ae, template)
                ok += 1
                if r["kind"] == "scp":
                    self.repo.update_print_job(r["id"], status="sent", destination=dest.name, message=msg)
                elif r["kind"] == "film":
                    self.repo.mark_film_printed(r["id"], S.get().username or "", dest.label())
                # "aw": o filme é do exame, não há linha nossa para marcar
                self._anota_envio(r, dest, usuario, how, True, msg, template)
                self.status_message.emit(msg)
            except Exception as e:  # noqa: BLE001
                falhas += 1
                log.exception("Falha ao enviar impressão")
                if r["kind"] == "scp":
                    self.repo.update_print_job(r["id"], status="error", destination=dest.name,
                                               message=str(e))
                self._anota_envio(r, dest, usuario, how, False, str(e), template)
                self.status_message.emit(f"Falha ao enviar: {e}")
        self.refresh()
        if falhas and avisar:
            QMessageBox.warning(self, "Enviar impressão",
                                f"{ok} enviado(s), {falhas} com erro. Veja a coluna Situação.")
        return ok, falhas

    def _anota_envio(self, r, dest, usuario, how, ok, msg, template) -> None:
        if not hasattr(self.repo, "add_send"):
            return
        try:
            self.repo.add_send(*self.ref_de(r), dest.name, usuario, how, ok, msg or "", template=template)
        except Exception:  # noqa: BLE001 - histórico não pode derrubar o envio
            log.exception("histórico de envios")

    def _preparar(self, r: dict) -> tuple[J.PrintJob | None, Path | None]:
        """O trabalho pronto para enviar: o recebido vem do disco; o montado aqui é desenhado agora."""
        if r["kind"] in ("scp", "aw"):
            return self._job(r)
        return film_to_job(self.repo, self.settings, int(r["id"]), self._film_root())

    def _film_root(self) -> Path:
        base = getattr(self.net, "print_root", None)
        return Path(base) / "filmes" if base else Path.home() / ".dicomviewer-filmes"

    # ------------------------------------------------------------ avisos
    def job_arrived(self, row: dict) -> None:
        self.refresh()


def film_to_job(repo, settings, film_id: int, root: Path) -> tuple[J.PrintJob | None, Path | None]:
    """Desenha um filme montado aqui e guarda como um trabalho de impressão (uma folha por página),
    para poder ir pelos mesmos caminhos do que chega das modalidades."""
    import numpy as np
    from pydicom.dataset import Dataset

    from ipe.imaging.series import FrameCache
    from ipe.printing.film import Film
    from ipe.ui.film.render import FrameSource, render_sheet_image

    dados = repo.film_data(film_id)
    if not dados:
        return None, None
    filme = Film.from_dict(dados)
    linha = next((f for f in repo.films() if f["id"] == film_id), {})
    job = J.PrintJob(uid=f"filme-{film_id}", received_at=datetime.now().isoformat(timespec="seconds"),
                     calling_ae="", label=linha.get("name", "Filme"),
                     patient_name=linha.get("patient_name", ""))
    folder = Path(root) / f"filme-{film_id}"
    import shutil
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    src = FrameSource(repo)
    cache = FrameCache(max_mb=256)
    for i, sheet in enumerate(filme.sheets):
        img = render_sheet_image(filme, i, src, cache, settings, dpi=150, grayscale=True)
        largura, altura = img.width(), img.height()
        buf = img.constBits()
        a = np.frombuffer(bytes(buf), dtype=np.uint8)[:altura * img.bytesPerLine()]
        a = a.reshape(altura, img.bytesPerLine())[:, :largura]
        item = Dataset()
        item.SamplesPerPixel = 1
        item.PhotometricInterpretation = "MONOCHROME2"
        item.Rows, item.Columns = int(altura), int(largura)
        item.BitsAllocated = item.BitsStored = 8
        item.HighBit, item.PixelRepresentation = 7, 0
        item.PixelData = np.ascontiguousarray(a).tobytes()
        box = J.write_box(folder, item, i + 1, job)
        box.position = 1
        tamanho = {"A4": "A4", "A3": "A3"}.get(sheet.paper, "")
        if not tamanho:
            from ipe.printing.film import PAPERS
            tamanho = PAPERS.get(sheet.paper, PAPERS["A4"])[2]
        job.films.append(J.FilmBox(display_format="STANDARD\\1,1", film_size=tamanho,
                                   orientation="LANDSCAPE" if sheet.landscape else "PORTRAIT",
                                   border="WHITE", empty="WHITE", boxes=[box]))
    src.clear()
    return job, folder
