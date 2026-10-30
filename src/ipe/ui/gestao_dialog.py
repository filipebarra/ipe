"""Gestão DICOM: os exames das modalidades estão no PACS? Inteiros? Se não, mandar.

Pedido dele: *"hoje eu confiro diariamente manualmente se os exames dessas modalidades estão no
meu PACS. verifico por exames e por número de sequências. uso o OsiriX para poder fazer o envio de
uma modalidade para o PACS (...) pode aplicar em um botão na tela do BD (gestão DICOM, ou algo
assim)"*.

A janela é a rotina dele em três passos: escolher as modalidades (cada uma com a identidade que
ela aceita) e o PACS; conferir o dia; mandar o que falta. A regra de rede mora em
`network/gestao.py` — aqui só há tela, linha de trabalho e o que se lembra de uma vez para outra.
"""

from __future__ import annotations

import csv
import logging
import threading
from datetime import date, datetime

from PySide6.QtCore import QByteArray, QDate, QObject, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QProgressBar, QPushButton, QSizePolicy, QSplitter,
    QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ipe.auth import session as S
from ipe.network import gestao as G
from ipe.network.client import DicomError
from ipe.ui.tabelas import colunas_ajustaveis

log = logging.getLogger(__name__)

CHAVE = "gestao"

COLUNAS_FILA = ["Situação", "Paciente", "Accession", "Destino", "Modo", "Hora", "Resultado"]
ESTADOS_FILA = {"fila": ("⏳", "Na fila"), "enviando": ("➜", "Enviando"), "ok": ("✔", "Enviado"),
                "nada": ("✔", "Nada a enviar"), "falhou": ("⚠", "Falhou"), "parado": ("■", "Não foi")}

PERIODOS = [("Hoje", "hoje"), ("Ontem", "ontem"), ("Ontem e hoje", "2dias"),
            ("Últimos 7 dias", "7dias"), ("Escolher as datas", "datas")]

SIMBOLO = {"erro": "⚠", "ausente": "✖", "outro_uid": "≠", "incompleto": "◐",
           "sem_contagem": "?", "completo": "✔"}
COR = {"erro": QColor(230, 90, 90), "ausente": QColor(230, 90, 90), "outro_uid": QColor(235, 160, 60),
       "incompleto": QColor(235, 160, 60), "sem_contagem": QColor(150, 150, 150),
       "completo": QColor(90, 190, 110)}
COR_SERIE = {"falta": COR["ausente"], "incompleta": COR["incompleto"], "sem_contagem": COR["sem_contagem"],
             "ok": COR["completo"], "ignorada": QColor(130, 130, 130), "so_no_pacs": QColor(130, 130, 130)}

RESUMO = {"completo": "completo(s)", "incompleto": "incompleto(s)", "ausente": "ausente(s) no PACS",
          "outro_uid": "com outro UID no PACS", "sem_contagem": "sem contagem", "erro": "com erro"}

COLUNAS = ["Situação", "Origem", "Data", "Paciente", "ID", "Accession", "Descrição",
           "Séries (origem / PACS)", "Imagens (origem / PACS)", "Detalhe", "Envio"]


class _Sinais(QObject):
    progresso = Signal(int, int, str)
    linha = Signal(object)                  # Conferencia nova (vai entrando enquanto confere)
    atualizada = Signal(object)             # Conferencia refeita depois de um envio
    fila = Signal(int, str, str, str)       # 0.99.6: lote, study_uid, estado, mensagem (fila de envio)


class _LinhaCurta(QLabel):
    """Etiqueta de uma linha que nunca pede a largura do texto.

    Defeito da 0.66.1, relatado por ele: a mensagem de erro (300 caracteres) ia inteira para a
    linha de estado; o QLabel pede como largura mínima o texto todo, o layout não cabia mais na
    janela e os botões iam para fora da tela, até ele restaurar e maximizar de novo. Aqui o texto
    é cortado com "…" na largura que houver, e o inteiro fica na dica (passar o mouse).
    """

    def __init__(self, texto: str = "", parent=None):
        super().__init__(parent)
        self._inteiro = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(40)
        self.setText(texto)

    def setText(self, texto: str) -> None:  # noqa: N802
        self._inteiro = str(texto or "")
        self.setToolTip(self._inteiro if len(self._inteiro) > 60 else "")
        self._cortar()

    def text(self) -> str:
        return self._inteiro

    def _cortar(self) -> None:
        linha = self._inteiro.replace("\n", " ")
        cortado = self.fontMetrics().elidedText(linha, Qt.ElideRight, max(40, self.width() - 4))
        QLabel.setText(self, cortado)

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._cortar()

    def minimumSizeHint(self):  # noqa: N802
        h = super().minimumSizeHint()
        h.setWidth(40)
        return h

    def sizeHint(self):  # noqa: N802
        h = super().sizeHint()
        h.setWidth(min(h.width(), 400))
        return h


class _Item(QTreeWidgetItem):
    """Ordena pelo valor guardado em UserRole quando há (situação pela gravidade, não pelo texto)."""

    def __lt__(self, other) -> bool:  # noqa: D401
        col = self.treeWidget().sortColumn() if self.treeWidget() else 0
        a, b = self.data(col, Qt.UserRole), other.data(col, Qt.UserRole)
        if a is not None and b is not None:
            return a < b
        return self.text(col).casefold() < other.text(col).casefold()


def _data(d: str, h: str = "") -> str:
    if len(d) == 8 and d.isdigit():
        s = f"{d[6:]}/{d[4:6]}/{d[:4]}"
        return f"{s} {h[:2]}:{h[2:4]}" if len(h) >= 4 else s
    return d


class GestaoWindow(QWidget):
    """Janela própria (fica por cima do banco e pode ir para outro monitor), como a do PACS."""

    def __init__(self, net, settings, parent=None, auto=None):
        super().__init__(parent, Qt.Window)
        self.net, self.settings = net, settings
        self.auto = auto if auto is not None else getattr(parent, "auto", None)   # gestão automática (0.99.6)
        self.setWindowTitle("Gestão DICOM — exames das modalidades no PACS")
        self.sinais = _Sinais(self)
        self.sinais.progresso.connect(self._progresso)
        self.sinais.linha.connect(self._nova_linha)
        self.sinais.atualizada.connect(self._linha_refeita)
        self.sinais.fila.connect(self._fila_estado)
        self._lote = 0
        self._fila_itens: dict[tuple[int, str], QTreeWidgetItem] = {}
        self.cancel: threading.Event | None = None
        self.ocupado = False
        self.resultados: list[G.Conferencia] = []
        self.itens: dict[tuple, _Item] = {}
        self._fontes_usadas: dict[int, G.Fonte] = {}
        self._pacs_usado: G.Fonte | None = None
        self._cfg_usada: dict = {}
        self._montar()
        self.recarregar_nos()
        self._restaurar()
        QShortcut(QKeySequence("Esc"), self, activated=self.close)

    # ------------------------------------------------------------------ montagem
    def _montar(self) -> None:
        # --- origem
        self.t_fontes = QTableWidget(0, 4)
        self.t_fontes.setHorizontalHeaderLabels(["Conferir", "Modalidade (nó)", "AE", "Como (identidade)"])
        self.t_fontes.verticalHeader().hide()
        self.t_fontes.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.t_fontes.setSelectionMode(QAbstractItemView.SingleSelection)
        self.t_fontes.setColumnWidth(0, 64)
        self.t_fontes.setColumnWidth(1, 170)
        self.t_fontes.setColumnWidth(2, 100)
        colunas_ajustaveis(self.t_fontes)
        self.l_web = QLabel("")
        self.l_web.setWordWrap(True)
        self.l_web.setStyleSheet("color:#999")
        b_todas = QPushButton("Marcar todas")
        b_todas.clicked.connect(lambda: self._marcar_todas(True))
        b_nenhuma = QPushButton("Desmarcar")
        b_nenhuma.clicked.connect(lambda: self._marcar_todas(False))
        self.b_testar = QPushButton("Testar o nó selecionado")
        self.b_testar.setToolTip("C-ECHO, busca por data, séries, nível imagem e se a modalidade "
                                 "conhece o PACS como destino do C-MOVE (nada é enviado)")
        self.b_testar.clicked.connect(self.testar_no)
        fb = QHBoxLayout()
        for b in (b_todas, b_nenhuma, self.b_testar):
            fb.addWidget(b)
        fb.addStretch(1)
        g1 = QGroupBox("Modalidades (onde os exames foram feitos)")
        l1 = QVBoxLayout(g1)
        l1.addWidget(self.t_fontes, 1)
        l1.addWidget(self.l_web)
        l1.addLayout(fb)

        # --- PACS
        self.c_pacs = QComboBox()
        self.c_pacs.currentIndexChanged.connect(lambda _i: self._pacs_mudou())
        self.c_pacs_ident = QComboBox()
        self.c_pacs_ident.setToolTip("AE com que este programa pergunta ao PACS e, no envio pelo "
                                     "computador, com que entrega as imagens")
        self.e_destino = QLineEdit()
        self.e_destino.setToolTip(
            "AE que a modalidade usa para mandar ao PACS no envio direto. Normalmente é o AE do "
            "próprio PACS; alguns PACS recebem num AE diferente do que responde às buscas. "
            "A modalidade precisa ter esse destino cadastrado (AE, IP e porta).")
        self.c_modo = QComboBox()
        for k, txt in G.MODOS_ENVIO.items():
            self.c_modo.addItem(txt, k)
        g2 = QGroupBox("PACS (onde os exames têm de estar)")
        f2 = QFormLayout(g2)
        f2.addRow("PACS:", self.c_pacs)
        f2.addRow("Como:", self.c_pacs_ident)
        f2.addRow("Destino do C-MOVE:", self.e_destino)
        f2.addRow("Como enviar:", self.c_modo)

        # --- o que conferir
        self.c_periodo = QComboBox()
        for txt, k in PERIODOS:
            self.c_periodo.addItem(txt, k)
        self.c_periodo.currentIndexChanged.connect(self._periodo_mudou)
        hoje = QDate.currentDate()
        self.d_de = QDateEdit(hoje)
        self.d_ate = QDateEdit(hoje)
        for d in (self.d_de, self.d_ate):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd/MM/yyyy")
        hd = QHBoxLayout()
        hd.addWidget(self.c_periodo)
        hd.addWidget(self.d_de)
        hd.addWidget(QLabel("até"))
        hd.addWidget(self.d_ate)
        hd.addStretch(1)
        self.e_ignorar = QLineEdit()
        self.e_ignorar.setPlaceholderText("ex.: Patient Protocol; ScreenCap")
        self.e_ignorar.setToolTip("Séries que a modalidade guarda e não manda ao PACS de propósito. "
                                  "Separe por ponto e vírgula; vale trecho da descrição, sem "
                                  "diferenciar maiúsculas.")
        self.k_exato = QCheckBox("Conferir imagem por imagem (mais lento; diz quais imagens faltam)")
        g3 = QGroupBox("O que conferir")
        f3 = QFormLayout(g3)
        f3.addRow("Período:", hd)
        f3.addRow("Ignorar séries:", self.e_ignorar)
        f3.addRow("", self.k_exato)

        self.b_conferir = QPushButton("Conferir")
        self.b_conferir.setDefault(True)
        self.b_conferir.setStyleSheet("font-weight:bold;padding:6px 18px")
        self.b_conferir.clicked.connect(self.conferir)
        self.b_parar = QPushButton("Parar")
        self.b_parar.setEnabled(False)
        self.b_parar.clicked.connect(self.parar)
        direita = QVBoxLayout()
        direita.addWidget(g2)
        direita.addWidget(g3)
        hb = QHBoxLayout()
        hb.addStretch(1)
        hb.addWidget(self.b_parar)
        hb.addWidget(self.b_conferir)
        direita.addLayout(hb)
        direita.addStretch(1)
        topo = QWidget()
        ht = QHBoxLayout(topo)
        ht.setContentsMargins(0, 0, 0, 0)
        ht.addWidget(g1, 1)
        dw = QWidget()
        dw.setLayout(direita)
        ht.addWidget(dw, 1)

        # --- resultado
        self.l_resumo = _LinhaCurta("Escolha as modalidades e o PACS e clique em Conferir.")
        self.c_mostrar = QComboBox()
        self.c_mostrar.addItems(["Todos os exames", "Só os com problema"])
        self.c_mostrar.currentIndexChanged.connect(self._filtrar)
        hr = QHBoxLayout()
        hr.addWidget(self.l_resumo, 1)
        hr.addWidget(QLabel("Mostrar:"))
        hr.addWidget(self.c_mostrar)
        self.arvore = QTreeWidget()
        self.arvore.setColumnCount(len(COLUNAS))
        self.arvore.setHeaderLabels(COLUNAS)
        self.arvore.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.arvore.setSortingEnabled(True)
        self.arvore.sortByColumn(0, Qt.AscendingOrder)
        self.arvore.setContextMenuPolicy(Qt.CustomContextMenu)
        self.arvore.customContextMenuRequested.connect(self._menu)
        self.arvore.itemSelectionChanged.connect(self._botoes)
        for i, w in enumerate((150, 90, 120, 220, 90, 90, 150, 140, 150, 260)):
            self.arvore.setColumnWidth(i, w)
        colunas_ajustaveis(self.arvore)

        self.b_falta = QPushButton("Enviar o que falta ao PACS")
        self.b_falta.setToolTip("Manda só as séries que faltam e, nas incompletas, só as imagens que faltam")
        self.b_falta.clicked.connect(lambda: self.enviar(inteiro=False))
        self.b_inteiro = QPushButton("Enviar o exame inteiro")
        self.b_inteiro.clicked.connect(lambda: self.enviar(inteiro=True))
        # 0.99.6: os mesmos dois envios para outro destino, como o "Enviar para" do banco
        self.b_falta_para = QPushButton("Enviar o que falta para ▾")
        self.b_falta_para.setToolTip("Confere o exame no destino escolhido e manda só o que falta lá")
        self.m_falta_para = QMenu(self.b_falta_para)
        self.m_falta_para.aboutToShow.connect(lambda: self._encher_destinos(self.m_falta_para, False))
        self.b_falta_para.setMenu(self.m_falta_para)
        self.b_inteiro_para = QPushButton("Enviar o exame inteiro para ▾")
        self.m_inteiro_para = QMenu(self.b_inteiro_para)
        self.m_inteiro_para.aboutToShow.connect(lambda: self._encher_destinos(self.m_inteiro_para, True))
        self.b_inteiro_para.setMenu(self.m_inteiro_para)
        self.b_reconferir = QPushButton("Conferir de novo")
        self.b_reconferir.clicked.connect(self.reconferir_selecionados)
        self.b_csv = QPushButton("Exportar CSV…")
        self.b_csv.clicked.connect(self.exportar_csv)
        self.barra = QProgressBar()
        self.barra.setMaximumWidth(260)
        self.barra.hide()
        self.l_estado = _LinhaCurta("")
        hb2 = QHBoxLayout()
        for b in (self.b_falta, self.b_inteiro, self.b_falta_para, self.b_inteiro_para, self.b_reconferir,
                  self.b_csv):
            hb2.addWidget(b)
        hb2.addWidget(self.barra)
        hb2.addWidget(self.l_estado, 1)
        # 0.99.6: a fila de envio — *"hoje eu seleciono para enviar e na barra inferior somente o
        # exame atual é mostrado"*. Cada exame mandado entra aqui com o destino e o andamento, e fica
        # até ele limpar (dá para ver o que foi, o que falhou e o que ainda espera).
        self.g_fila = QGroupBox("Fila de envio")
        vf = QVBoxLayout(self.g_fila)
        vf.setContentsMargins(6, 4, 6, 4)
        self.t_fila = QTreeWidget()
        self.t_fila.setColumnCount(len(COLUNAS_FILA))
        self.t_fila.setHeaderLabels(COLUNAS_FILA)
        self.t_fila.setRootIsDecorated(False)
        self.t_fila.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for i, larg in enumerate((70, 220, 110, 160, 110, 120)):
            self.t_fila.setColumnWidth(i, larg)
        colunas_ajustaveis(self.t_fila)
        vf.addWidget(self.t_fila, 1)
        hf = QHBoxLayout()
        self.l_fila = QLabel("Nada na fila.")
        self.b_fila_parar = QPushButton("Parar o envio")
        self.b_fila_parar.setToolTip("O exame que está indo termina; os que esperam não vão")
        self.b_fila_parar.clicked.connect(self.parar)
        self.b_fila_limpar = QPushButton("Limpar os concluídos")
        self.b_fila_limpar.clicked.connect(self.limpar_fila)
        hf.addWidget(self.l_fila, 1)
        hf.addWidget(self.b_fila_parar)
        hf.addWidget(self.b_fila_limpar)
        vf.addLayout(hf)
        self.g_fila.hide()                       # aparece no primeiro envio
        lista = QWidget()
        vl = QVBoxLayout(lista)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.addWidget(self.arvore, 1)
        self.split_fila = QSplitter(Qt.Vertical)
        self.split_fila.addWidget(lista)
        self.split_fila.addWidget(self.g_fila)
        self.split_fila.setStretchFactor(0, 3)
        self.split_fila.setStretchFactor(1, 1)
        baixo = QWidget()
        vb = QVBoxLayout(baixo)
        vb.setContentsMargins(0, 0, 0, 0)
        vb.addLayout(hr)
        vb.addWidget(self.split_fila, 1)
        vb.addLayout(hb2)

        self.split = QSplitter(Qt.Vertical)
        self.split.addWidget(topo)
        self.split.addWidget(baixo)
        self.split.setStretchFactor(1, 1)
        # 0.99.6: a aba "Automático" — regras com horário, o que completou, erros e nós fora do ar
        from PySide6.QtWidgets import QTabWidget
        from ipe.ui.gestao_auto_ui import PainelAutomatico
        self.abas = QTabWidget()
        self.abas.addTab(self.split, "Conferir agora")
        self.painel_auto = PainelAutomatico(self.net, self.auto, self)
        self.abas.addTab(self.painel_auto, "Automático")
        lay = QVBoxLayout(self)
        lay.addWidget(self.abas)
        self.resize(1250, 800)
        self._periodo_mudou()
        self._botoes()

    # ------------------------------------------------------------------ nós
    @property
    def repo(self):
        return self.net.repo

    def _nos_dimse(self) -> list[dict]:
        return [n for n in self.repo.nodes(only_active=True) if n["kind"] == "dimse"]

    def _encher_identidades(self, combo: QComboBox, no: dict | None, atual=None) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(f"Este programa ({self.net.local_ae})", None)
        for i in (self.net.identities_for(no) if no else self.repo.identities()):
            combo.addItem(f"{i['name']} ({i['ae_title']})", i["id"])
        combo.setCurrentIndex(max(0, combo.findData(atual)))
        combo.blockSignals(False)

    def recarregar_nos(self) -> None:
        cfg = self._cfg()
        nos = self._nos_dimse()
        fontes = cfg.get("fontes", {})
        self.t_fontes.setRowCount(0)
        for n in nos:
            r = self.t_fontes.rowCount()
            self.t_fontes.insertRow(r)
            mem = fontes.get(str(n["id"]), {})
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            chk.setCheckState(Qt.Checked if mem.get("on") else Qt.Unchecked)
            chk.setData(Qt.UserRole, n["id"])
            self.t_fontes.setItem(r, 0, chk)
            self.t_fontes.setItem(r, 1, QTableWidgetItem(n["name"]))
            self.t_fontes.setItem(r, 2, QTableWidgetItem(n["ae_title"]))
            for c in (1, 2):
                self.t_fontes.item(r, c).setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            cb = QComboBox()
            self._encher_identidades(cb, n, mem.get("ident"))
            self.t_fontes.setCellWidget(r, 3, cb)
        web = [n["name"] for n in self.repo.nodes(only_active=True) if n["kind"] == "dicomweb"]
        self.l_web.setText(
            "Nenhum nó cadastrado. Cadastre as modalidades e o PACS em Configurações ▸ Nós DICOM."
            if not nos else
            f"Nós DICOMweb não entram aqui ({', '.join(web)}): a conferência e o envio direto usam "
            f"C-FIND e C-MOVE, que são DIMSE." if web else "")
        self.l_web.setVisible(bool(self.l_web.text()))
        self.c_pacs.blockSignals(True)
        self.c_pacs.clear()
        for n in nos:
            self.c_pacs.addItem(f"{n['name']}  ({n['ae_title']}@{n['host']})", n["id"])
        alvo = cfg.get("pacs")
        if alvo is None:
            alvo = next((n["id"] for n in nos if "PACS" in n["name"].upper()
                         or "PACS" in n["ae_title"].upper()), nos[0]["id"] if nos else None)
        self.c_pacs.setCurrentIndex(max(0, self.c_pacs.findData(alvo)))
        self.c_pacs.blockSignals(False)
        self._pacs_mudou(cfg.get("pacs_ident"))

    def _pacs_mudou(self, ident="atual") -> None:
        no = self.repo.node(self.c_pacs.currentData()) if self.c_pacs.currentData() else None
        atual = self.c_pacs_ident.currentData() if ident == "atual" else ident
        self._encher_identidades(self.c_pacs_ident, no, atual)
        self.e_destino.setPlaceholderText(no["ae_title"] if no else "")

    def _marcar_todas(self, on: bool) -> None:
        for r in range(self.t_fontes.rowCount()):
            self.t_fontes.item(r, 0).setCheckState(Qt.Checked if on else Qt.Unchecked)

    def fontes(self, so_marcadas: bool = True) -> list[G.Fonte]:
        out = []
        for r in range(self.t_fontes.rowCount()):
            it = self.t_fontes.item(r, 0)
            if so_marcadas and it.checkState() != Qt.Checked:
                continue
            no = self.repo.node(it.data(Qt.UserRole))
            if no is None:
                continue
            ident = self.repo.identity(self.t_fontes.cellWidget(r, 3).currentData())
            out.append(G.Fonte(no, ident))
        return out

    def pacs(self) -> G.Fonte | None:
        no = self.repo.node(self.c_pacs.currentData()) if self.c_pacs.currentData() else None
        return G.Fonte(no, self.repo.identity(self.c_pacs_ident.currentData())) if no else None

    def destino(self) -> str:
        p = self.pacs()
        return self.e_destino.text().strip() or (p.no["ae_title"] if p else "")

    def ignorar(self) -> list[str]:
        return [x.strip() for x in self.e_ignorar.text().split(";") if x.strip()]

    # ------------------------------------------------------------------ período
    def _periodo_mudou(self) -> None:
        livre = self.c_periodo.currentData() == "datas"
        for w in (self.d_de, self.d_ate):
            w.setVisible(livre)

    def datas(self) -> tuple[str, str]:
        k = self.c_periodo.currentData()
        if k == "datas":
            de, ate = self.d_de.date().toPython(), self.d_ate.date().toPython()
            if de > ate:
                de, ate = ate, de
            return de.strftime("%Y%m%d"), ate.strftime("%Y%m%d")
        return G.periodo(k, date.today())

    # ------------------------------------------------------------------ memória
    def _cfg(self) -> dict:
        cfg = self.settings.get("gestao", {}) if self.settings is not None else {}
        return dict(cfg) if isinstance(cfg, dict) else {}

    def _restaurar(self) -> None:
        cfg = self._cfg()
        self.e_destino.setText(cfg.get("destino", ""))
        self.c_modo.setCurrentIndex(max(0, self.c_modo.findData(cfg.get("modo", "auto"))))
        self.c_periodo.setCurrentIndex(max(0, self.c_periodo.findData(cfg.get("periodo", "hoje"))))
        self.e_ignorar.setText(cfg.get("ignorar", ""))
        self.k_exato.setChecked(bool(cfg.get("exato", False)))
        self.c_mostrar.setCurrentIndex(1 if cfg.get("so_problemas") else 0)
        geo = cfg.get("geometria", "")
        if geo:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geo.encode("ascii")))
            except Exception:  # noqa: BLE001
                pass

    def guardar(self) -> None:
        """O padrão é o último que ele usou: a rotina do dia seguinte é um clique."""
        if self.settings is None:
            return
        cfg = self._cfg()
        fontes = {}
        for r in range(self.t_fontes.rowCount()):
            it = self.t_fontes.item(r, 0)
            fontes[str(it.data(Qt.UserRole))] = {
                "on": it.checkState() == Qt.Checked,
                "ident": self.t_fontes.cellWidget(r, 3).currentData()}
        cfg.update({"fontes": fontes, "pacs": self.c_pacs.currentData(),
                    "pacs_ident": self.c_pacs_ident.currentData(),
                    "destino": self.e_destino.text().strip(), "modo": self.c_modo.currentData(),
                    "periodo": self.c_periodo.currentData(), "ignorar": self.e_ignorar.text().strip(),
                    "exato": self.k_exato.isChecked(), "so_problemas": self.c_mostrar.currentIndex() == 1,
                    "geometria": bytes(self.saveGeometry().toBase64()).decode("ascii")})
        self.settings.set("gestao", cfg)
        self.settings.save()

    # ------------------------------------------------------------------ conferir
    def _ocupar(self, on: bool, texto: str = "") -> None:
        self.ocupado = on
        self.b_conferir.setEnabled(not on)
        self.b_testar.setEnabled(not on)
        self.b_parar.setEnabled(on)
        self.barra.setVisible(on)
        if on:
            self.barra.setRange(0, 0)
        self.l_estado.setText(texto)
        self._botoes()

    def conferir(self) -> None:
        if self.ocupado or not S.require("query", self, "conferir exames nos nós DICOM"):
            return
        fontes, pacs = self.fontes(), self.pacs()
        if pacs is None:
            QMessageBox.information(self, "Gestão DICOM", "Escolha o PACS.")
            return
        fontes = [f for f in fontes if f.no["id"] != pacs.no["id"]]
        if not fontes:
            QMessageBox.information(self, "Gestão DICOM", "Marque pelo menos uma modalidade "
                                    "(que não seja o próprio PACS).")
            return
        self.guardar()
        de, ate = self.datas()
        ignorar, exato = self.ignorar(), self.k_exato.isChecked()
        self.arvore.clear()
        self.itens.clear()
        self.resultados = []
        self._fontes_usadas = {f.no["id"]: f for f in fontes}
        self._pacs_usado = pacs
        self._cfg_usada = {"ignorar": ignorar, "exato": exato, "de": de, "ate": ate,
                           "destino": self.destino(), "modo": self.c_modo.currentData()}
        self._erros: list[str] = []
        self.cancel = threading.Event()
        self._ocupar(True, "Conferindo…")
        self.arvore.setSortingEnabled(False)
        conferidor = G.Conferidor(self.net.client, self.net.target)
        cancel = self.cancel

        def trabalho():
            return conferidor.conferir(fontes, pacs, de, ate, ignorar=ignorar, exato=exato,
                                       cancel=cancel, progresso=self.sinais.progresso.emit,
                                       ao_conferir=self.sinais.linha.emit)

        def pronto(res, err) -> None:
            self.arvore.setSortingEnabled(True)
            self._ocupar(False)
            if err is not None:
                self.l_estado.setText(f"Conferência parou: {err}")
                QMessageBox.warning(self, "Gestão DICOM", f"A conferência parou: {err}")
                return
            _res, erros = res
            self._erros = erros
            self._resumo()
            quem = ", ".join(f.nome for f in fontes)
            self.repo.audit("gestão", f"conferência {_data(de)}–{_data(ate)}: {quem} × "
                                      f"{pacs.nome} — {self.l_resumo.text()}")
            texto = self.texto_dos_erros(erros)
            if texto:
                self.l_estado.setText(texto.splitlines()[0])
                QMessageBox.warning(self, "Gestão DICOM", texto)
        self.net.run_async(trabalho, pronto)

    def texto_dos_erros(self, erros: list[str]) -> str:
        """Erros de nó e erros por exame num texto só, cada motivo uma vez, com quantos exames.

        Exame com erro não pode ficar só na coluna Detalhe — ela fica fora da tela."""
        partes = []
        if erros:
            partes.append("Alguns nós não puderam ser conferidos:\n" + "\n".join(f"• {e}" for e in erros))
        por_motivo: dict[str, int] = {}
        for c in self.resultados:
            if c.situacao == "erro":
                por_motivo[c.detalhe] = por_motivo.get(c.detalhe, 0) + 1
        if por_motivo:
            linhas = [f"• {n} exame(s): {m}" for m, n in sorted(por_motivo.items(), key=lambda x: -x[1])]
            partes.append("Exames com erro:\n" + "\n".join(linhas))
        return "\n\n".join(partes)

    def parar(self) -> None:
        if self.cancel is not None:
            self.cancel.set()
            self.l_estado.setText("Parando…")

    def _progresso(self, feitos: int, total: int, msg: str) -> None:
        if total:
            self.barra.setRange(0, total)
            self.barra.setValue(feitos)
        else:
            self.barra.setRange(0, 0)
        self.l_estado.setText(msg)

    # ------------------------------------------------------------------ tabela
    def _chave(self, c: G.Conferencia) -> tuple:
        return (c.fonte_id, c.study_uid)

    def _nova_linha(self, c: G.Conferencia) -> None:
        self.resultados.append(c)
        it = _Item()
        self.arvore.addTopLevelItem(it)
        self.itens[self._chave(c)] = it
        self._pintar(it, c)
        self._resumo()

    def _linha_refeita(self, c: G.Conferencia) -> None:
        k = self._chave(c)
        it = self.itens.get(k)
        self.resultados = [c if self._chave(r) == k else r for r in self.resultados]
        if it is not None:
            self._pintar(it, c)
        self._resumo()
        self._botoes()

    def _pintar(self, it: _Item, c: G.Conferencia) -> None:
        e = c.estudo
        ser, img = c.contagem()
        textos = [f"{SIMBOLO.get(c.situacao, '')} {c.texto()}", c.fonte,
                  _data(e.get("study_date", ""), e.get("study_time", "")),
                  e.get("patient_name", ""), e.get("patient_id", ""), e.get("accession", ""),
                  e.get("description", ""), ser, img, c.detalhe, c.envio]
        for i, t in enumerate(textos):
            it.setText(i, t)
        it.setData(0, Qt.UserRole, G.ORDEM.get(c.situacao, 99))
        it.setData(2, Qt.UserRole, f"{e.get('study_date', '')}{e.get('study_time', '')}")
        it.setForeground(0, QBrush(COR.get(c.situacao, QColor(200, 200, 200))))
        it.setToolTip(9, c.detalhe)
        it.setToolTip(10, c.envio)
        it.setData(1, Qt.UserRole + 1, self._chave(c))
        it.takeChildren()
        for s in sorted(c.series, key=lambda s: (s.situacao == "so_no_pacs", s.numero)):
            f = _Item()
            no = "—" if s.imagens_origem is None else str(s.imagens_origem)
            np_ = "—" if s.imagens_pacs is None else str(s.imagens_pacs)
            if s.situacao == "falta":
                np_ = "0"
            nome = f"Série {s.numero} · {s.descricao}" if s.descricao else f"Série {s.numero}"
            vals = [G.SITUACOES_SERIE.get(s.situacao, s.situacao), "", "", nome, "", "",
                    s.modalidade, "", f"{no} / {np_}",
                    f"faltam {s.faltam}" if s.situacao in G.A_ENVIAR and s.faltam else "", ""]
            for i, t in enumerate(vals):
                f.setText(i, t)
            f.setData(0, Qt.UserRole, list(G.SITUACOES_SERIE).index(s.situacao)
                      if s.situacao in G.SITUACOES_SERIE else 99)
            f.setData(3, Qt.UserRole, s.numero)
            f.setForeground(0, QBrush(COR_SERIE.get(s.situacao, QColor(200, 200, 200))))
            it.addChild(f)
        self._filtrar_item(it, c)

    def _filtrar_item(self, it, c) -> None:
        it.setHidden(self.c_mostrar.currentIndex() == 1 and not c.problema)

    def _filtrar(self) -> None:
        for c in self.resultados:
            it = self.itens.get(self._chave(c))
            if it is not None:
                self._filtrar_item(it, c)

    def _resumo(self) -> None:
        n = len(self.resultados)
        if not n:
            erros = getattr(self, "_erros", [])
            self.l_resumo.setText("Nenhum exame encontrado nas modalidades no período."
                                  if not self.ocupado and not erros else
                                  "Nenhum exame conferido." if erros else "Conferindo…")
            return
        cont = {k: 0 for k in G.SITUACOES}
        for c in self.resultados:
            cont[c.situacao] = cont.get(c.situacao, 0) + 1
        partes = [f"{n} exame(s)"]
        for k, nome in RESUMO.items():
            if cont.get(k):
                partes.append(f"{SIMBOLO[k]} {cont[k]} {nome}")
        self.l_resumo.setText(" · ".join(partes))

    # ------------------------------------------------------------------ seleção
    def selecionadas(self) -> list[G.Conferencia]:
        chaves = []
        for it in self.arvore.selectedItems():
            top = it if it.parent() is None else it.parent()
            k = top.data(1, Qt.UserRole + 1)
            if k is not None and k not in chaves:
                chaves.append(tuple(k))
        por = {self._chave(c): c for c in self.resultados}
        return [por[k] for k in chaves if k in por]

    def _botoes(self) -> None:
        sel = self.selecionadas() if hasattr(self, "arvore") else []
        livre = not self.ocupado
        self.b_falta.setEnabled(livre and any(c.situacao in ("incompleto", "ausente") for c in sel))
        self.b_inteiro.setEnabled(livre and any(c.situacao != "erro" for c in sel))
        self.b_reconferir.setEnabled(livre and bool(sel) and self._pacs_usado is not None)
        para = livre and any(c.situacao != "erro" for c in sel) and S.can("send")
        self.b_falta_para.setEnabled(para)
        self.b_inteiro_para.setEnabled(para)
        self.b_csv.setEnabled(bool(self.resultados))

    def _menu(self, pos) -> None:
        m = self.menu_da_arvore()
        if not m.isEmpty():
            m.exec(self.arvore.viewport().mapToGlobal(pos))

    def menu_da_arvore(self) -> QMenu:
        """Monta o menu do botão direito (separado de quem exibe, para poder testar)."""
        m = QMenu(self)
        sel = self.selecionadas()
        if not sel:
            return m
        for b in (self.b_falta, self.b_inteiro):
            a = m.addAction(b.text(), b.click)
            a.setEnabled(b.isEnabled())
        for texto, inteiro, botao in (("Enviar o que falta para", False, self.b_falta_para),
                                      ("Enviar o exame inteiro para", True, self.b_inteiro_para)):
            sub = m.addMenu(texto)
            self._encher_destinos(sub, inteiro)
            sub.setEnabled(botao.isEnabled())
        a = m.addAction(self.b_reconferir.text(), self.b_reconferir.click)
        a.setEnabled(self.b_reconferir.isEnabled())
        m.addSeparator()
        accs = [c.estudo.get("accession", "") for c in sel if c.estudo.get("accession")]
        a = m.addAction("Copiar accession", lambda: _copiar("\n".join(accs)))
        a.setEnabled(bool(accs))
        return m

    # ------------------------------------------------------------------ enviar
    def enviar(self, inteiro: bool = False, confirmar: bool = True) -> None:
        if self.ocupado or not S.require("send", self, "enviar exames ao PACS"):
            return
        sel = [c for c in self.selecionadas()
               if c.situacao != "erro" and (inteiro or c.situacao in ("incompleto", "ausente"))]
        if not sel or self._pacs_usado is None:
            return
        pacs = self._pacs_usado
        modo, destino = self.c_modo.currentData(), self.destino()
        if confirmar:
            outro = [c for c in sel if c.situacao == "outro_uid"]
            texto = (f"Enviar {len(sel)} exame(s) para {pacs.nome}?\n\n"
                     f"{'Exame inteiro' if inteiro else 'Só o que falta'} · {G.MODOS_ENVIO[modo]}\n"
                     f"Destino do C-MOVE: {destino}")
            if outro:
                texto = (f"{texto}\n\nAtenção: {len(outro)} exame(s) já estão no PACS com outro "
                         f"Study UID. Mandar cria um segundo exame do mesmo paciente no PACS.")
            if QMessageBox.question(self, "Gestão DICOM", texto) != QMessageBox.Yes:
                return
        rem = G.Remetente(self.net.client, self.net.target, sink=self.net.sink, repo=self.repo)
        conferidor = G.Conferidor(self.net.client, self.net.target)
        fontes = dict(self._fontes_usadas)
        cfg = dict(self._cfg_usada)
        self.cancel = threading.Event()
        cancel = self.cancel
        for c in sel:
            c.envio = "Na fila…"
            self._linha_refeita(c)
        lote = self._fila_entrar(sel, pacs.nome, f"{'inteiro' if inteiro else 'o que falta'} · "
                                                 f"{G.MODOS_ENVIO[modo]}")
        self._ocupar(True, f"Enviando {len(sel)} exame(s)…")

        def trabalho():
            feitos = 0
            for i, c in enumerate(sel, 1):
                if cancel.is_set():
                    break
                f = fontes.get(c.fonte_id)
                if f is None:
                    self.sinais.fila.emit(lote, c.study_uid, "falhou", "o nó de origem saiu da lista")
                    continue
                self.sinais.fila.emit(lote, c.study_uid, "enviando", "")
                self.sinais.progresso.emit(i - 1, len(sel), f"{c.estudo.get('patient_name', '')}: "
                                                            f"enviando ({i} de {len(sel)})…")
                try:
                    r = rem.enviar(modo, f, pacs, c, destino, inteiro=inteiro, cancel=cancel)
                    msg = r["mensagem"]
                    self.repo.audit("gestão", f"envio ao {pacs.nome}: {c.estudo.get('accession', '')} "
                                              f"{c.estudo.get('patient_name', '')} — {msg}",
                                    study_uid=c.study_uid)
                    feitos += 1
                    self.sinais.fila.emit(lote, c.study_uid, "nada" if msg.startswith("Nada a enviar") else "ok",
                                          msg)
                except Exception as e:  # noqa: BLE001
                    msg = f"Falhou: {e}"
                    log.warning("Envio da gestão falhou (%s): %s", c.study_uid, e)
                    c.envio = msg
                    self.sinais.fila.emit(lote, c.study_uid, "falhou", str(e))
                    self.sinais.atualizada.emit(c)
                    continue
                novo = self._reconferir_um(conferidor, f, pacs, c, cfg, msg)
                self.sinais.atualizada.emit(novo)
            return feitos

        def pronto(res, err) -> None:
            self._ocupar(False)
            self._fila_fechar(lote)
            self.l_estado.setText(f"Envio parou: {err}" if err is not None else
                                  f"{res} exame(s) enviado(s) e conferido(s) de novo.")
        self.net.run_async(trabalho, pronto, self.net.transfer_pool)

    # ------------------------------------------------------------------ fila de envio (0.99.6)
    def _fila_entrar(self, sel: list, destino: str, modo_txt: str) -> int:
        """Põe os exames do lote na fila (estado "Na fila") e devolve o número do lote."""
        self._lote += 1
        hora = datetime.now().strftime("%H:%M")
        for c in sel:
            it = QTreeWidgetItem(["", c.estudo.get("patient_name", "") or "", c.estudo.get("accession", "") or "",
                                  destino, modo_txt, hora, ""])
            it.setData(0, Qt.UserRole, c.study_uid)
            self.t_fila.addTopLevelItem(it)
            self._fila_itens[(self._lote, c.study_uid)] = it
            self._fila_pintar(it, "fila", "")
        self.g_fila.show()
        self._fila_resumo()
        return self._lote

    def _fila_pintar(self, it: QTreeWidgetItem, estado: str, msg: str) -> None:
        simb, txt = ESTADOS_FILA.get(estado, ("", estado))
        it.setText(0, f"{simb} {txt}")
        it.setData(0, Qt.UserRole + 1, estado)
        if msg:
            it.setText(6, msg)
            it.setToolTip(6, msg)
        cor = {"ok": "#7fd07f", "nada": "#7fd07f", "falhou": "#ff8a80", "enviando": "#ffd166",
               "parado": "#9a9a9a"}.get(estado)
        for col in range(len(COLUNAS_FILA)):
            it.setForeground(col, QBrush(QColor(cor)) if cor else QBrush())
        if estado == "enviando":
            self.t_fila.scrollToItem(it)

    def _fila_estado(self, lote: int, study_uid: str, estado: str, msg: str) -> None:
        it = self._fila_itens.get((lote, study_uid))
        if it is not None:
            self._fila_pintar(it, estado, msg)
        self._fila_resumo()

    def _fila_fechar(self, lote: int) -> None:
        """Fim do lote (ou parou): quem ainda estava na fila não foi."""
        for (lt, _u), it in self._fila_itens.items():
            if lt == lote and it.data(0, Qt.UserRole + 1) in ("fila", "enviando"):
                self._fila_pintar(it, "parado", "o envio foi parado antes deste exame")
        self._fila_resumo()

    def estados_da_fila(self) -> list[str]:
        return [self.t_fila.topLevelItem(i).data(0, Qt.UserRole + 1) for i in range(self.t_fila.topLevelItemCount())]

    def _fila_resumo(self) -> None:
        est = self.estados_da_fila()
        if not est:
            self.l_fila.setText("Nada na fila.")
        else:
            n = {k: est.count(k) for k in ESTADOS_FILA}
            partes = [f"{n['ok'] + n['nada']} enviado(s)", f"{n['fila']} esperando"]
            if n["enviando"]:
                partes.insert(0, "1 indo agora")
            if n["falhou"]:
                partes.append(f"{n['falhou']} com falha")
            if n["parado"]:
                partes.append(f"{n['parado']} não foi(ram)")
            self.l_fila.setText(f"{len(est)} exame(s) na fila: " + ", ".join(partes) + ".")
            self.g_fila.setTitle(f"Fila de envio ({len(est)})")
        self.b_fila_parar.setEnabled(any(e in ("fila", "enviando") for e in est))
        self.b_fila_limpar.setEnabled(any(e in ("ok", "nada", "falhou", "parado") for e in est))

    def limpar_fila(self) -> None:
        for k, it in list(self._fila_itens.items()):
            if it.data(0, Qt.UserRole + 1) in ("ok", "nada", "falhou", "parado"):
                self.t_fila.takeTopLevelItem(self.t_fila.indexOfTopLevelItem(it))
                del self._fila_itens[k]
        if not self._fila_itens:
            self.g_fila.setTitle("Fila de envio")
        self._fila_resumo()

    # ------------------------------------------------------------------ enviar para (0.99.6)
    def _encher_destinos(self, menu: QMenu, inteiro: bool) -> None:
        """Os destinos do "Enviar para" do banco (nós de envio e, em cada um, as identidades)."""
        from ipe.ui.send_menu import preencher_envio
        menu.clear()
        preencher_envio(menu, self.repo, lambda nid, iid, i=inteiro: self.enviar_para(nid, iid, inteiro=i))

    def enviar_para(self, node_id: int, ident_id: int | None = None, inteiro: bool = False,
                    confirmar: bool = True) -> None:
        """Pedido dele (27/10): *"enviar o que falta para" e "enviar o exame inteiro para", abrindo os
        destinos*. O que falta é contado **no destino escolhido**: antes de mandar, confere o exame
        lá; se o destino não responde à busca, vai o exame inteiro (e a linha diz). A situação da
        linha continua sendo a do PACS da conferência; o envio aparece na coluna do envio."""
        if self.ocupado or not S.require("send", self, "enviar exames"):
            return
        no = self.repo.node(node_id)
        if no is None:
            return
        destino = G.Fonte(no, self.repo.identity(ident_id) if ident_id else None)
        sel = [c for c in self.selecionadas() if c.situacao != "erro"]
        if not sel:
            return
        modo = self.c_modo.currentData()
        if confirmar:
            texto = (f"Enviar {len(sel)} exame(s) para {destino.nome}?\n\n"
                     f"{'Exame inteiro' if inteiro else 'Só o que falta em ' + destino.nome} · "
                     f"{G.MODOS_ENVIO[modo]}")
            if QMessageBox.question(self, "Gestão DICOM", texto) != QMessageBox.Yes:
                return
        rem = G.Remetente(self.net.client, self.net.target, sink=self.net.sink, repo=self.repo)
        conferidor = G.Conferidor(self.net.client, self.net.target)
        fontes = dict(self._fontes_usadas)
        cfg = dict(self._cfg_usada)
        self.cancel = threading.Event()
        cancel = self.cancel
        for c in sel:
            c.envio = f"Na fila para {destino.nome}…"
            self._linha_refeita(c)
        lote = self._fila_entrar(sel, destino.nome, f"{'inteiro' if inteiro else 'o que falta'} · "
                                                    f"{G.MODOS_ENVIO[modo]}")
        self._ocupar(True, f"Enviando {len(sel)} exame(s) para {destino.nome}…")

        def trabalho():
            feitos = 0
            for i, c in enumerate(sel, 1):
                if cancel.is_set():
                    break
                f = fontes.get(c.fonte_id)
                if f is None:
                    self.sinais.fila.emit(lote, c.study_uid, "falhou", "o nó de origem saiu da lista")
                    continue
                self.sinais.fila.emit(lote, c.study_uid, "enviando", "")
                self.sinais.progresso.emit(i - 1, len(sel), f"{c.estudo.get('patient_name', '')}: "
                                                            f"enviando para {destino.nome} ({i} de {len(sel)})…")
                nota = ""
                try:
                    alvo, tudo = c, inteiro
                    if not inteiro:
                        try:
                            alvo = conferidor.reconferir(f, destino, c.study_uid, ignorar=cfg.get("ignorar", ()),
                                                         exato=cfg.get("exato", False))
                        except DicomError as e:
                            alvo, tudo = c, True
                            nota = f" (não deu para conferir em {destino.nome}: foi o exame inteiro — {e})"
                    estado = "ok"
                    if not tudo and alvo.situacao == "completo":
                        msg, estado = f"já estava completo em {destino.nome}", "nada"
                    elif not tudo and alvo.situacao == "erro":
                        raise RuntimeError(alvo.detalhe or "não deu para conferir")
                    else:
                        r = rem.enviar(modo, f, destino, alvo, destino.no.get("ae_title", ""),
                                       inteiro=tudo, cancel=cancel)
                        msg = r["mensagem"] + nota
                        feitos += 1
                    self.repo.audit("gestão", f"envio a {destino.nome}: {c.estudo.get('accession', '')} "
                                              f"{c.estudo.get('patient_name', '')} — {msg}", study_uid=c.study_uid)
                    c.envio = f"→ {destino.nome}: {msg}"
                    self.sinais.fila.emit(lote, c.study_uid, estado, msg)
                except Exception as e:  # noqa: BLE001
                    log.warning("Envio da gestão para %s falhou (%s): %s", destino.nome, c.study_uid, e)
                    c.envio = f"→ {destino.nome}: falhou: {e}"
                    self.sinais.fila.emit(lote, c.study_uid, "falhou", str(e))
                self.sinais.atualizada.emit(c)
            return feitos

        def pronto(res, err) -> None:
            self._ocupar(False)
            self._fila_fechar(lote)
            self.l_estado.setText(f"Envio parou: {err}" if err is not None else
                                  f"{res} exame(s) enviado(s) para {destino.nome}.")
        self.net.run_async(trabalho, pronto, self.net.transfer_pool)

    @staticmethod
    def _reconferir_um(conferidor, f, pacs, c, cfg, envio: str = "", espera: float = 2.0):
        """Depois do envio, perguntar de novo: 'enviado' não é 'está no PACS'.

        O PACS indexa depois de receber; espera um pouco e, se ainda não fechou, tenta mais
        uma vez antes de dizer que não fechou."""
        import time
        novo = c
        for tentativa in range(3):
            time.sleep(espera if tentativa else min(espera, 1.0))
            try:
                novo = conferidor.reconferir(f, pacs, c.study_uid, ignorar=cfg.get("ignorar", ()),
                                             exato=cfg.get("exato", False))
            except DicomError as e:
                novo = c
                envio = f"{envio} — não deu para conferir de novo: {e}"
                break
            if novo.situacao == "completo":
                break
        novo.fonte_id = c.fonte_id
        novo.envio = envio if novo.situacao == "completo" else \
            f"{envio} — conferido de novo: {novo.texto().lower()}"
        return novo

    def reconferir_selecionados(self) -> None:
        sel = self.selecionadas()
        if self.ocupado or not sel or self._pacs_usado is None:
            return
        conferidor = G.Conferidor(self.net.client, self.net.target)
        fontes, pacs, cfg = dict(self._fontes_usadas), self._pacs_usado, dict(self._cfg_usada)
        self._ocupar(True, f"Conferindo {len(sel)} exame(s) de novo…")

        def trabalho():
            for c in sel:
                f = fontes.get(c.fonte_id)
                if f is None:
                    continue
                try:
                    novo = conferidor.reconferir(f, pacs, c.study_uid, ignorar=cfg.get("ignorar", ()),
                                                 exato=cfg.get("exato", False))
                except DicomError as e:
                    novo = c
                    novo.detalhe = f"não deu para conferir de novo: {e}"
                novo.fonte_id, novo.envio = c.fonte_id, c.envio
                self.sinais.atualizada.emit(novo)
            return len(sel)

        def pronto(res, err) -> None:
            self._ocupar(False, f"Erro: {err}" if err is not None else f"{res} exame(s) conferido(s) de novo.")
        self.net.run_async(trabalho, pronto)

    # ------------------------------------------------------------------ teste do nó
    def testar_no(self) -> None:
        if self.ocupado:
            return
        r = self.t_fontes.currentRow()
        todas = self.fontes(so_marcadas=False)
        if r < 0 or r >= len(todas):
            QMessageBox.information(self, "Gestão DICOM", "Selecione uma modalidade na lista.")
            return
        f = todas[r]
        destino = self.destino()
        conferidor = G.Conferidor(self.net.client, self.net.target)
        self._ocupar(True, f"Testando {f.nome}…")

        def pronto(res, err) -> None:
            self._ocupar(False)
            if err is not None:
                QMessageBox.warning(self, "Gestão DICOM", f"{f.nome}: {err}")
                return
            linhas = [f"{'✔' if ok else '✖' if ok is False else '?'}  {t}" for ok, t in res]
            QMessageBox.information(self, f"Teste de {f.nome}", "\n".join(linhas))
        self.net.run_async(lambda: conferidor.diagnosticar(f, destino, date.today().strftime("%Y%m%d")),
                           pronto)

    # ------------------------------------------------------------------ CSV
    def exportar_csv(self, caminho: str = "") -> str:
        if not self.resultados:
            return ""
        if not caminho:
            nome = f"conferencia-{datetime.now():%Y%m%d-%H%M}.csv"
            caminho, _ = QFileDialog.getSaveFileName(self, "Exportar conferência", nome, "CSV (*.csv)")
            if not caminho:
                return ""
        with open(caminho, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=";", lineterminator="\r\n")
            w.writerow(["Situação", "Origem", "Data", "Paciente", "ID", "Accession", "Descrição",
                        "Séries origem/PACS", "Imagens origem/PACS", "Detalhe", "Envio",
                        "Série", "Descrição da série", "Situação da série", "Imagens da série",
                        "Study UID"])
            for c in sorted(self.resultados, key=lambda c: (G.ORDEM.get(c.situacao, 99), c.fonte)):
                e = c.estudo
                ser, img = c.contagem()
                base = [c.texto(), c.fonte, _data(e.get("study_date", ""), e.get("study_time", "")),
                        e.get("patient_name", ""), e.get("patient_id", ""), e.get("accession", ""),
                        e.get("description", ""), ser, img, c.detalhe, c.envio]
                ruins = [s for s in c.series if s.situacao in ("falta", "incompleta", "sem_contagem")]
                if not ruins:
                    w.writerow(base + ["", "", "", "", c.study_uid])
                for s in ruins:
                    w.writerow(base + [s.numero, s.descricao, G.SITUACOES_SERIE[s.situacao],
                                       f"{s.imagens_origem if s.imagens_origem is not None else '?'} / "
                                       f"{s.imagens_pacs if s.imagens_pacs is not None else '?'}",
                                       c.study_uid])
        self.l_estado.setText(f"Conferência exportada para {caminho}")
        return caminho

    # ------------------------------------------------------------------ janela
    def show_front(self) -> None:
        if not self.ocupado:
            self.recarregar_nos()
        self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e) -> None:  # noqa: N802
        self.guardar()
        super().closeEvent(e)


def _copiar(texto: str) -> None:
    from PySide6.QtWidgets import QApplication
    QApplication.clipboard().setText(texto)
