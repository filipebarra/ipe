"""Rede ▸ Lote a partir de planilha… (0.100.97): a janela do `automation.lote`, em cinco passos.

1. Planilha — o arquivo, a aba e o tipo de cada coluna (adivinhado pelo título, com a prévia);
2. Achar o exame — tolerância de dias, modalidades, "descrição contém", vários exames, nascimento;
3. De onde — o banco do Ipê e os nós marcados, na ordem;
4. O que fazer — IAs, protocolo de RM, enviar, imprimir, exportar, apagar o que veio de fora;
5. Rodar — saída, anonimizar, janela de horário, simular, iniciar/parar, andamento e diário (sem nome de paciente).

No topo, os modelos (os prontos e os salvos). Roda numa linha de fundo; o que precisa da linha da tela (a fila de IA,
o desenho das folhas) passa pela ponte.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTime, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
    QProgressBar, QPushButton, QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem, QTimeEdit, QVBoxLayout,
    QWidget,
)

from ipe.automation import lote as L
from ipe.automation import lote_ias as LIA
from ipe.automation import planilha as P
from ipe.core.i18n import tr
from ipe.ui.tabelas import colunas_ajustaveis

log = logging.getLogger(__name__)

PREVIA = 8              # linhas na prévia da planilha


class _Sinais(QObject):
    linha = Signal(object, object, object)      # andamento, linha (ou None: esperando a janela), resultado
    fim = Signal(object, str)                   # andamento, erro
    aviso = Signal(str)                         # 0.100.111: uma linha no diário vinda de outra linha de execução


def duracao(s: float | None) -> str:
    if s is None:
        return ""
    s = int(s)
    if s < 90:
        return "%d s" % s
    if s < 5400:
        return "%d min" % (s // 60)
    return "%d h %02d min" % (s // 3600, s % 3600 // 60)


class LoteDialog(QDialog):
    PASSOS = ("1. Planilha", "2. Achar o exame", "3. De onde", "4. O que fazer", "5. Rodar")

    def __init__(self, repo, db, net, settings, storage_root, engine=None, parent=None):
        super().__init__(parent)
        from ipe.central.ponte import Ponte
        self.repo, self.db, self.net, self.settings = repo, db, net, settings
        self.storage_root, self.engine = storage_root, engine
        self.ponte = Ponte()                          # criada aqui, na linha da tela
        # 0.100.98: no Ipê cliente, o lote roda no servidor (os nós, as IAs e as impressoras são os dele)
        from ipe.automation import mama_auto as MA
        self.remoto = not MA.local(repo)
        self.opcoes_servidor: dict = {}
        self.remoto_id = ""
        self.remoto_desde = 0
        self.remoto_copiando: set[str] = set()
        self.remoto_falhas: dict[str, int] = {}
        self.remoto_ia_rodando: set[str] = set()
        if self.remoto:
            try:
                self.opcoes_servidor = repo.client.rpc("lote_opcoes") or {}
            except Exception as e:  # noqa: BLE001
                log.warning("opções do lote no servidor: %s", e)
                self.opcoes_servidor = {"erro": str(e)}
        self.setWindowTitle(tr("Lote a partir de planilha"))
        self.resize(980, 680)
        self.dados: list[list] = []
        self.lote: L.Lote | None = None
        self.parar = threading.Event()
        self.linha_de_fundo: threading.Thread | None = None
        self.sinais = _Sinais(self)
        self.sinais.linha.connect(self._andou)
        self.sinais.fim.connect(self._acabou)
        self.sinais.aviso.connect(self.diario_anotar)
        self._combos_coluna: list[QComboBox] = []

        lay = QVBoxLayout(self)
        topo = QHBoxLayout()
        topo.addWidget(QLabel(tr("Modelo:")))
        self.c_modelo = QComboBox()
        self.c_modelo.setMinimumWidth(280)
        topo.addWidget(self.c_modelo)
        b = QPushButton(tr("Usar"))
        b.clicked.connect(self.usar_modelo)
        topo.addWidget(b)
        b = QPushButton(tr("Salvar como modelo…"))
        b.clicked.connect(self.salvar_modelo)
        topo.addWidget(b)
        self.b_apagar_modelo = QPushButton(tr("Apagar modelo"))
        self.b_apagar_modelo.clicked.connect(self.apagar_modelo)
        topo.addWidget(self.b_apagar_modelo)
        topo.addStretch(1)
        lay.addLayout(topo)

        meio = QHBoxLayout()
        self.passos = QListWidget()
        self.passos.setFixedWidth(170)
        for p in self.PASSOS:
            self.passos.addItem(tr(p))
        meio.addWidget(self.passos)
        self.pilha = QStackedWidget()
        for fazer in (self._pagina_planilha, self._pagina_achar, self._pagina_onde, self._pagina_acoes,
                      self._pagina_rodar):
            self.pilha.addWidget(fazer())
        meio.addWidget(self.pilha, 1)
        lay.addLayout(meio, 1)
        self.passos.currentRowChanged.connect(self.pilha.setCurrentIndex)
        self.passos.setCurrentRow(0)

        base = QHBoxLayout()
        self.b_simular = QPushButton(tr("Simular"))
        self.b_simular.setToolTip(tr("Só procura os exames (no banco e nos nós) e conta — não baixa nem roda nada."))
        self.b_simular.clicked.connect(lambda: self.iniciar(simular=True))
        self.b_iniciar = QPushButton(tr("Iniciar"))
        self.b_iniciar.setDefault(True)
        self.b_iniciar.clicked.connect(lambda: self.iniciar(simular=False))
        self.b_parar = QPushButton(tr("Parar"))
        self.b_parar.setEnabled(False)
        self.b_parar.clicked.connect(self.pedir_parada)
        self.b_abrir = QPushButton(tr("Abrir a pasta da saída"))
        self.b_abrir.clicked.connect(self.abrir_pasta)
        b_fechar = QPushButton(tr("Fechar"))
        b_fechar.clicked.connect(self.close)
        for w in (self.b_simular, self.b_iniciar, self.b_parar):
            base.addWidget(w)
        base.addStretch(1)
        base.addWidget(self.b_abrir)
        base.addWidget(b_fechar)
        lay.addLayout(base)
        self._carregar_modelos()

    # ================================================================== páginas
    def _pagina_planilha(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        intro = QLabel(tr("Uma linha por exame (ou por paciente e data). Diga o que é cada coluna: o Ipê acha o "
                          "exame pela melhor chave da linha — Study UID, nº de acesso ou ID + data."))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        f = QFormLayout()
        self.e_arquivo = QLineEdit()
        self.e_arquivo.setReadOnly(True)
        b = QPushButton(tr("Escolher…"))
        b.clicked.connect(self.escolher_arquivo)
        h = QHBoxLayout()
        h.addWidget(self.e_arquivo, 1)
        h.addWidget(b)
        f.addRow(tr("Planilha (CSV, XLSX ou ODS):"), h)
        self.c_aba = QComboBox()
        self.c_aba.currentIndexChanged.connect(lambda _i: self.carregar_aba())
        f.addRow(tr("Aba:"), self.c_aba)
        lay.addLayout(f)
        self.t_previa = QTableWidget()
        self.t_previa.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(self.t_previa, 1)
        self.l_lista = QLabel()
        self.l_lista.setWordWrap(True)
        lay.addWidget(self.l_lista)
        return w

    def _pagina_achar(self) -> QWidget:
        w = QWidget()
        fora = QVBoxLayout(w)
        fora.addWidget(QLabel(tr("Buscar por (na ordem) — o Ipê tenta a primeira marcada; se não acha, a seguinte:")))
        f = QFormLayout()
        # 0.100.99: as tentativas de busca, marcadas e na ordem dele; para na primeira que acha
        h = QHBoxLayout()
        self.l_tentativas = QListWidget()
        self.l_tentativas.setDragDropMode(QAbstractItemView.InternalMove)
        self.l_tentativas.setMaximumHeight(150)
        self.l_tentativas.setToolTip(tr("Marque e ponha na ordem: o Ipê tenta a primeira; se não acha, a seguinte. "
                                        "A modalidade e a data vêm da planilha (ou dos campos abaixo)."))
        self._marcar_tentativas(list(L.TENTATIVAS_PADRAO))
        h.addWidget(self.l_tentativas, 1)
        v = QVBoxLayout()
        for txt, d in ((tr("Subir"), -1), (tr("Descer"), 1)):
            b = QPushButton(txt)
            b.clicked.connect(lambda _c=False, d=d: self._mover(self.l_tentativas, d))
            v.addWidget(b)
        v.addStretch(1)
        h.addLayout(v)
        fora.addLayout(h)
        fora.addLayout(f)
        fora.addStretch(1)
        self.l_tentativas.itemChanged.connect(lambda _i: self._conferir())
        self.l_tentativas.model().rowsMoved.connect(lambda *_a: self._conferir())
        self.s_tol = QSpinBox(minimum=0, maximum=365)
        self.s_tol.setSuffix(tr(" dia(s)"))
        self.s_tol.setToolTip(tr("0 = só no dia da planilha. Vale quando a linha tem ID e data."))
        f.addRow(tr("Tolerância da data (±):"), self.s_tol)
        self.e_mods = QLineEdit()
        self.e_mods.setPlaceholderText(tr("ex.: MG  ou  CT, MR  (vazio = qualquer)"))
        f.addRow(tr("Modalidade(s):"), self.e_mods)
        self.e_desc = QLineEdit()
        self.e_desc.setPlaceholderText(tr("ex.: abdome  (vazio = qualquer)"))
        f.addRow(tr("Descrição contém:"), self.e_desc)
        self.c_varios = QComboBox()
        for k, t in L.VARIOS.items():
            self.c_varios.addItem(tr(t), k)
        f.addRow(tr("Se achar mais de um exame:"), self.c_varios)
        self.k_nasc = QCheckBox(tr("Conferir a data de nascimento (se a planilha tiver)"))
        self.k_nasc.setChecked(True)
        self.k_nasc.setToolTip(tr("Nascimento diferente: o exame é de outra pessoa (mesmo ID) e não é usado."))
        f.addRow("", self.k_nasc)
        nota = QLabel(tr("Linha só com o ID, sem data, só é feita se \"Só ID\" ou \"ID + modalidade\" estiver "
                         "marcado (e então, com \"Se achar mais de um exame\", o Ipê escolhe entre os exames do "
                         "paciente)."))
        nota.setWordWrap(True)
        f.addRow("", nota)
        return w

    def _nos_dicom(self) -> list[dict]:
        if self.remoto:
            return [{"id": n["id"], "name": n["name"]} for n in self.opcoes_servidor.get("nos") or []]
        try:
            return [n for n in self.repo.nodes(only_active=True) if n.get("kind") in ("dimse", "dicomweb")]
        except Exception:  # noqa: BLE001
            return []

    def _pagina_onde(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel(tr("Primeiro o banco do Ipê; se o exame não está, os nós marcados, nesta ordem — baixa do "
                                "primeiro que tiver.")))
        h = QHBoxLayout()
        self.l_nos = QListWidget()
        self.l_nos.setDragDropMode(QAbstractItemView.InternalMove)
        for n in self._nos_dicom():
            extra = n.get("ae_title") or n.get("url") or ""
            it = QListWidgetItem(f"{n['name']} ({extra})" if extra else n["name"])
            it.setData(Qt.UserRole, str(n["id"]))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.l_nos.addItem(it)
        h.addWidget(self.l_nos, 1)
        v = QVBoxLayout()
        for txt, d in ((tr("Subir"), -1), (tr("Descer"), 1)):
            b = QPushButton(txt)
            b.clicked.connect(lambda _c=False, d=d: self._mover_no(d))
            v.addWidget(b)
        v.addStretch(1)
        h.addLayout(v)
        lay.addLayout(h, 1)
        f = QFormLayout()
        self.c_ident = QComboBox()
        self.c_ident.addItem(tr("Este programa ({})").format(getattr(self.net, "local_ae", "")), None)
        try:
            for i in self.repo.identities():
                self.c_ident.addItem(f"{i['name']} ({i['ae_title']})", i["id"])
        except Exception:  # noqa: BLE001
            pass
        f.addRow(tr("Falar como:"), self.c_ident)
        if self.remoto:                        # no cliente, quem fala com os nós é o servidor, com o AE dele
            self.c_ident.setEnabled(False)
        lay.addLayout(f)
        return w

    def _mover_no(self, d: int) -> None:
        self._mover(self.l_nos, d)

    @staticmethod
    def _mover(lista: QListWidget, d: int) -> None:
        r = lista.currentRow()
        if r < 0 or not 0 <= r + d < lista.count():
            return
        it = lista.takeItem(r)
        lista.insertItem(r + d, it)
        lista.setCurrentRow(r + d)

    def _marcar_tentativas(self, marcadas: list[str]) -> None:
        """A lista na ordem: as marcadas primeiro (na ordem dada), depois as outras na ordem de fábrica."""
        self.l_tentativas.blockSignals(True)
        self.l_tentativas.clear()
        nomes = dict(L.TENTATIVAS)
        ordem = [k for k in marcadas if k in nomes] + [k for k, _n in L.TENTATIVAS if k not in marcadas]
        for k in ordem:
            it = QListWidgetItem(tr(nomes[k]))
            it.setData(Qt.UserRole, k)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if k in marcadas else Qt.Unchecked)
            self.l_tentativas.addItem(it)
        self.l_tentativas.blockSignals(False)

    def _pagina_acoes(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGroupBox(tr("Rodar IAs (a que não serve para o exame pula, com o motivo)"))
        gl = QVBoxLayout(g)
        self.l_ias = QListWidget()
        cat = [tuple(x) for x in self.opcoes_servidor.get("ias") or []] if self.remoto else \
            LIA.catalogo(self.engine)
        for tipo, titulo in cat:
            it = QListWidgetItem(tr(titulo))
            it.setData(Qt.UserRole, tipo)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.l_ias.addItem(it)
        gl.addWidget(self.l_ias)
        self.k_refazer_ias = QCheckBox(tr("Rodar de novo a IA que o exame já tem"))
        gl.addWidget(self.k_refazer_ias)
        lay.addWidget(g, 1)
        self.k_protocolo = QCheckBox(tr("Conferir o protocolo de RM"))
        lay.addWidget(self.k_protocolo)
        g = QGroupBox(tr("Enviar"))
        gf = QFormLayout(g)
        self.l_enviar = QListWidget()
        self.l_enviar.setMaximumHeight(90)
        for n in self._nos_dicom():
            it = QListWidgetItem(n["name"])
            it.setData(Qt.UserRole, str(n["id"]))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.l_enviar.addItem(it)
        gf.addRow(tr("Para:"), self.l_enviar)
        self.c_enviar = QComboBox()
        for k, t in L.ENVIAR.items():
            self.c_enviar.addItem(tr(t), k)
        gf.addRow(tr("O quê:"), self.c_enviar)
        lay.addWidget(g)
        g = QGroupBox(tr("Imprimir e exportar as séries de conferência das IAs"))
        gf = QFormLayout(g)
        self.c_imprimir = QComboBox()
        self.c_imprimir.addItem(tr("Não imprimir"), "")
        if self.remoto:
            for x in self.opcoes_servidor.get("imprimir") or []:
                self.c_imprimir.addItem(tr(x["nome"]), x["id"])
        else:
            try:
                from ipe.printing import dispatch as D
                for d in D.all_destinations(self.settings):
                    self.c_imprimir.addItem(tr("Destino: {}").format(d.label()), f"dest:{d.name}")
            except Exception:  # noqa: BLE001
                pass
            for x in (self.settings.get("printing.dicom_printers", []) or []):
                self.c_imprimir.addItem(tr("Impressora DICOM: {}").format(x.get("name", "")),
                                        f"dicom:{x.get('name', '')}")
        gf.addRow(tr("Imprimir em:"), self.c_imprimir)
        self.e_exportar = QLineEdit()
        self.e_exportar.setPlaceholderText(tr("(não exportar arquivos)"))
        b = QPushButton(tr("Pasta…"))
        b.clicked.connect(self.escolher_pasta_exportar)
        h = QHBoxLayout()
        h.addWidget(self.e_exportar, 1)
        h.addWidget(b)
        gf.addRow(tr("Exportar para:"), h)
        self.c_formato = QComboBox()
        self.c_formato.addItem(tr("Imagens PNG"), "png")
        self.c_formato.addItem(tr("Um PDF por exame"), "pdf")
        self.c_formato.addItem(tr("Nenhuma imagem"), "")
        gf.addRow(tr("Formato:"), self.c_formato)
        self.k_dicom = QCheckBox(tr("Também os DICOM gerados pelas IAs"))
        gf.addRow("", self.k_dicom)
        lay.addWidget(g)
        self.k_apagar = QCheckBox(tr("Apagar do Ipê, no fim, os exames baixados só para o lote"))
        self.k_apagar.setChecked(True)
        self.k_apagar.setToolTip(tr("O que já estava no banco do Ipê nunca é apagado."))
        lay.addWidget(self.k_apagar)
        self.k_chegada = QCheckBox(tr("Exame que já está no Ipê: aplicar as regras da chegada (IA, envio, impressão), "
                                      "como num exame baixado"))
        self.k_chegada.setChecked(True)
        self.k_chegada.setToolTip(tr("As regras de Preferências ▸ CAD/IA e de Configurações ▸ Rede ▸ Automação que valem para o exame "
                                     "que chega. O exame baixado pelo lote já passa por elas ao terminar o download."))
        lay.addWidget(self.k_chegada)
        # 0.100.98: no cliente, o lote roda no servidor; o exame pode vir também para o banco deste computador
        self.k_trazer = QCheckBox(tr("Trazer os exames também para este computador (banco local)"))
        self.k_trazer.setToolTip(tr("O lote roda no servidor. Marcado, cada exame feito é copiado para este "
                                    "computador; se o lote apaga o que baixou, o servidor só apaga depois da cópia."))
        self.k_trazer.setVisible(self.remoto)
        lay.addWidget(self.k_trazer)
        if self.remoto:                       # 0.100.107: no cliente, o "apagar" diz de onde e quando
            self.k_trazer.toggled.connect(self._rotulo_apagar)
            self._rotulo_apagar(self.k_trazer.isChecked())
        return w

    def _rotulo_apagar(self, trazer: bool) -> None:
        """No Ipê cliente: com "trazer", o servidor só apaga depois que o exame chegou inteiro a este computador."""
        if trazer:
            self.k_apagar.setText(tr("Apagar do servidor os exames que o lote baixou do PACS, depois que chegarem "
                                     "inteiros a este computador"))
            self.k_apagar.setToolTip(tr("Ficam só no banco deste computador. O que já estava no servidor antes do "
                                        "lote nunca é apagado."))
        else:
            self.k_apagar.setText(tr("Apagar do servidor, no fim, os exames que o lote baixou do PACS"))
            self.k_apagar.setToolTip(tr("O que já estava no servidor antes do lote nunca é apagado."))

    def _pagina_rodar(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        f = QFormLayout()
        self.e_saida = QLineEdit()
        b = QPushButton(tr("Escolher…"))
        b.clicked.connect(self.escolher_saida)
        h = QHBoxLayout()
        h.addWidget(self.e_saida, 1)
        h.addWidget(b)
        f.addRow(tr("Planilha de saída (.xlsx):"), h)
        self.k_anon = QCheckBox(tr("Anonimizar a saída (Caso 0001…; a chave vai para um arquivo à parte)"))
        f.addRow("", self.k_anon)
        self.k_janela = QCheckBox(tr("Só rodar entre"))
        self.t_de, self.t_ate = QTimeEdit(QTime(20, 0)), QTimeEdit(QTime(6, 0))
        for t in (self.t_de, self.t_ate):
            t.setDisplayFormat("HH:mm")
        h = QHBoxLayout()
        h.addWidget(self.k_janela)
        h.addWidget(self.t_de)
        h.addWidget(QLabel(tr("e")))
        h.addWidget(self.t_ate)
        h.addStretch(1)
        f.addRow(tr("Horário:"), h)
        self.k_refazer = QCheckBox(tr("Ao continuar, tentar de novo os não encontrados e os com erro"))
        self.k_refazer.setChecked(True)
        f.addRow("", self.k_refazer)
        self.s_limite = QSpinBox(minimum=0, maximum=1_000_000, value=0)
        self.s_limite.setSpecialValueText(tr("todas"))
        self.s_limite.setToolTip(tr("Para testar: faz só as primeiras N linhas que faltam e para."))
        f.addRow(tr("Quantas linhas agora:"), self.s_limite)
        lay.addLayout(f)
        self.barra = QProgressBar()
        lay.addWidget(self.barra)
        self.l_estado = QLabel()
        self.l_estado.setWordWrap(True)
        lay.addWidget(self.l_estado)
        self.diario = QPlainTextEdit()
        self.diario.setReadOnly(True)
        self.diario.setMaximumBlockCount(1000)
        lay.addWidget(self.diario, 1)
        return w

    # ================================================================== planilha
    def escolher_arquivo(self) -> None:
        caminho, _f = QFileDialog.getOpenFileName(self, tr("Planilha"), "",
                                                  tr("Planilhas") + " (*.xlsx *.xlsm *.ods *.csv *.tsv *.txt)")
        if caminho:
            self.abrir_arquivo(caminho)

    def abrir_arquivo(self, caminho: str) -> bool:
        try:
            nomes = P.abas(caminho)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, self.windowTitle(), tr("Não deu para abrir a planilha:\n{}").format(e))
            return False
        self.e_arquivo.setText(caminho)
        self.c_aba.blockSignals(True)
        self.c_aba.clear()
        self.c_aba.addItems(nomes or [tr("(única)")])
        escolhida = 0
        for i, nome in enumerate(nomes):          # a primeira aba com cara de lista (uma coluna-chave reconhecida)
            try:
                cab = (P.ler_planilha(caminho, nome) or [[]])[0]
            except Exception:  # noqa: BLE001
                continue
            if {"id", "acesso", "uid"} & set(L.adivinhar_colunas(cab)):
                escolhida = i
                break
        self.c_aba.setCurrentIndex(escolhida)
        self.c_aba.blockSignals(False)
        if not self.e_saida.text():
            p = Path(caminho)
            self.e_saida.setText(str(p.with_name(p.stem + "-Ipe.xlsx")))
        return self.carregar_aba()

    def carregar_aba(self, tipos: list[str] | None = None) -> bool:
        caminho = self.e_arquivo.text()
        if not caminho:
            return False
        aba = self.c_aba.currentText() if P.abas(caminho) else None
        try:
            self.dados = P.ler_planilha(caminho, aba)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, self.windowTitle(), tr("Não deu para ler a aba:\n{}").format(e))
            self.dados = []
            return False
        cab = self.dados[0] if self.dados else []
        largura = max([len(cab)] + [len(x) for x in self.dados[1:PREVIA + 1]]) if self.dados else 0
        tipos = tipos or L.adivinhar_colunas(cab)
        self.t_previa.clear()
        self.t_previa.setColumnCount(largura)
        self.t_previa.setRowCount(1 + min(PREVIA, max(0, len(self.dados) - 1)))
        self.t_previa.setHorizontalHeaderLabels([str(c if c not in (None, "") else tr("coluna {}").format(i + 1))
                                                 for i, c in enumerate(list(cab) + [""] * (largura - len(cab)))])
        self.t_previa.setVerticalHeaderLabels([tr("tipo")] + [str(i + 2) for i in range(self.t_previa.rowCount() - 1)])
        self._combos_coluna = []
        for c in range(largura):
            combo = QComboBox()
            for k, t in L.TIPOS_COLUNA:
                combo.addItem(tr(t), k)
            combo.setCurrentIndex(max(0, combo.findData(tipos[c] if c < len(tipos) else "ignorar")))
            combo.currentIndexChanged.connect(lambda _i: self._conferir())
            self.t_previa.setCellWidget(0, c, combo)
            self._combos_coluna.append(combo)
        for r, linha in enumerate(self.dados[1:PREVIA + 1], start=1):
            for c, v in enumerate(linha):
                self.t_previa.setItem(r, c, QTableWidgetItem("" if v is None else str(v)))
        self.t_previa.resizeColumnsToContents()
        colunas_ajustaveis(self.t_previa, estica_ultima=False)
        self._conferir()
        return True

    def tipos(self) -> list[str]:
        return [c.currentData() for c in self._combos_coluna]

    def linhas(self) -> list[L.Linha]:
        return L.montar_linhas(self.dados[1:], self.tipos()) if len(self.dados) > 1 else []

    def _conferir(self) -> None:
        ls = self.linhas()
        if not ls:
            self.l_lista.setText("")
            return
        cfg = self.config()
        com_chave = sum(1 for l in ls if l.criterios(cfg))
        sem_data = sum(1 for l in ls if not l.criterios(cfg) and l.pid and not l.data)
        txt = tr("{} linhas; {} com chave para achar o exame").format(len(ls), com_chave)
        if sem_data:
            txt += tr("; {} só com o ID, sem data (não serão feitas)").format(sem_data)
        if not self._marcados(self.l_tentativas):
            txt += "\n" + tr("Nenhuma tentativa de busca marcada: vale a ordem de fábrica.")
        repetidos = [t for t in ("id", "acesso", "data", "uid", "nascimento", "nome") if self.tipos().count(t) > 1]
        if repetidos:
            txt += "\n" + tr("Atenção: mais de uma coluna marcada como {} — vale a primeira.").format(
                ", ".join(tr(dict(L.TIPOS_COLUNA)[t]) for t in repetidos))
        self.l_lista.setText(txt + ".")

    # ================================================================== configuração ↔ janela
    @staticmethod
    def _marcados(lista: QListWidget) -> list[str]:
        return [lista.item(i).data(Qt.UserRole) for i in range(lista.count())
                if lista.item(i).checkState() == Qt.Checked]

    @staticmethod
    def _marcar(lista: QListWidget, ids: list[str], ordenar: bool = False) -> None:
        ids = [str(x) for x in ids or []]
        if ordenar:                                 # os marcados sobem, na ordem do modelo
            itens = [lista.takeItem(0) for _ in range(lista.count())]
            itens.sort(key=lambda it: ids.index(it.data(Qt.UserRole)) if it.data(Qt.UserRole) in ids else 10 ** 6)
            for it in itens:
                lista.addItem(it)
        for i in range(lista.count()):
            it = lista.item(i)
            it.setCheckState(Qt.Checked if str(it.data(Qt.UserRole)) in ids else Qt.Unchecked)

    def config(self) -> L.Config:
        mods = [m.strip().upper() for m in self.e_mods.text().replace(";", ",").replace("/", ",").split(",")
                if m.strip()]
        return L.Config(
            aba=self.c_aba.currentText(), colunas=self.tipos(), tentativas=self._marcados(self.l_tentativas),
            tolerancia_dias=self.s_tol.value(),
            modalidades=mods, descricao_contem=self.e_desc.text().strip(), varios=self.c_varios.currentData(),
            conferir_nascimento=self.k_nasc.isChecked(), nos=self._marcados(self.l_nos),
            ias=self._marcados(self.l_ias), refazer_ias=self.k_refazer_ias.isChecked(),
            protocolo_rm=self.k_protocolo.isChecked(), enviar_nos=self._marcados(self.l_enviar),
            enviar_o_que=self.c_enviar.currentData(), imprimir=self.c_imprimir.currentData() or "",
            exportar_pasta=self.e_exportar.text().strip(), exportar_imagens=self.c_formato.currentData() or "",
            exportar_dicom=self.k_dicom.isChecked(), apagar_depois=self.k_apagar.isChecked(),
            regras_chegada=self.k_chegada.isChecked(),
            anonimizar=self.k_anon.isChecked(),
            janela_de=self.t_de.time().toString("HH:mm") if self.k_janela.isChecked() else "",
            janela_ate=self.t_ate.time().toString("HH:mm") if self.k_janela.isChecked() else "",
            refazer_erros=self.k_refazer.isChecked())

    def aplicar(self, cfg: L.Config) -> None:
        self._marcar_tentativas(cfg.tentativas_validas())
        self.s_tol.setValue(int(cfg.tolerancia_dias or 0))
        self.e_mods.setText(", ".join(cfg.modalidades or []))
        self.e_desc.setText(cfg.descricao_contem or "")
        self.c_varios.setCurrentIndex(max(0, self.c_varios.findData(cfg.varios)))
        self.k_nasc.setChecked(bool(cfg.conferir_nascimento))
        self._marcar(self.l_nos, cfg.nos, ordenar=True)
        self._marcar(self.l_ias, cfg.ias)
        self.k_refazer_ias.setChecked(bool(cfg.refazer_ias))
        self.k_protocolo.setChecked(bool(cfg.protocolo_rm))
        self._marcar(self.l_enviar, cfg.enviar_nos)
        self.c_enviar.setCurrentIndex(max(0, self.c_enviar.findData(cfg.enviar_o_que)))
        self.c_imprimir.setCurrentIndex(max(0, self.c_imprimir.findData(cfg.imprimir or "")))
        self.e_exportar.setText(cfg.exportar_pasta or "")
        self.c_formato.setCurrentIndex(max(0, self.c_formato.findData(cfg.exportar_imagens or "")))
        self.k_dicom.setChecked(bool(cfg.exportar_dicom))
        self.k_apagar.setChecked(bool(cfg.apagar_depois))
        self.k_chegada.setChecked(bool(cfg.regras_chegada))
        self.k_anon.setChecked(bool(cfg.anonimizar))
        self.k_janela.setChecked(bool(cfg.janela_de and cfg.janela_ate))
        if cfg.janela_de and cfg.janela_ate:
            self.t_de.setTime(QTime.fromString(cfg.janela_de, "HH:mm"))
            self.t_ate.setTime(QTime.fromString(cfg.janela_ate, "HH:mm"))
        self.k_refazer.setChecked(bool(cfg.refazer_erros))
        if cfg.colunas and self.dados:
            self.carregar_aba(cfg.colunas)
        self._conferir()

    # ================================================================== modelos
    def _carregar_modelos(self, escolher: str = "") -> None:
        self.c_modelo.clear()
        self.c_modelo.addItem(tr("(nenhum)"), "")
        for nome in L.modelos(self.settings):
            self.c_modelo.addItem(tr(nome), nome)
        if escolher:
            self.c_modelo.setCurrentIndex(max(0, self.c_modelo.findData(escolher)))

    def usar_modelo(self) -> None:
        nome = self.c_modelo.currentData()
        if nome:
            self.aplicar(L.modelos(self.settings)[nome])

    def salvar_modelo(self) -> None:
        nome, ok = QInputDialog.getText(self, tr("Salvar como modelo"), tr("Nome do modelo:"),
                                        text=self.c_modelo.currentData() or "")
        nome = (nome or "").strip()
        if not ok or not nome:
            return
        if nome in L.MODELOS_PRONTOS:
            QMessageBox.information(self, self.windowTitle(), tr("Esse nome é de um modelo pronto: escolha outro."))
            return
        L.salvar_modelo(self.settings, nome, self.config())
        self._carregar_modelos(nome)

    def apagar_modelo(self) -> None:
        nome = self.c_modelo.currentData()
        if not nome or nome in L.MODELOS_PRONTOS:
            return
        L.apagar_modelo(self.settings, nome)
        self._carregar_modelos()

    # ================================================================== pastas
    def escolher_saida(self) -> None:
        caminho, _f = QFileDialog.getSaveFileName(self, tr("Planilha de saída"), self.e_saida.text(), "Excel (*.xlsx)")
        if caminho:
            self.e_saida.setText(caminho if caminho.lower().endswith(".xlsx") else caminho + ".xlsx")

    def escolher_pasta_exportar(self) -> None:
        pasta = QFileDialog.getExistingDirectory(self, tr("Exportar para"), self.e_exportar.text())
        if pasta:
            self.e_exportar.setText(pasta)

    def abrir_pasta(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        if self.e_saida.text():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.e_saida.text()).parent)))

    # ================================================================== rodar
    def _servicos(self, ident):
        from ipe.automation import lote_ipe as LP
        return LP.servicos(self.repo, self.db, self.net, self.settings, self.storage_root, self.engine,
                           chamar=lambda fn: self.ponte.chamar(fn, espera=900), identidade=ident, parar=self.parar)

    def permissoes(self, cfg: L.Config) -> list[str]:
        out = []
        if cfg.nos:
            out += ["query", "retrieve"]
        if cfg.enviar_nos:
            out.append("send")
        if cfg.imprimir:
            out.append("print")
        if cfg.exportar_pasta:
            out.append("export")
            if not cfg.anonimizar:
                out.append("export_identified")
        return out

    def validar(self, simular: bool) -> L.Config | None:
        """As escolhas fazem sentido? (com o aviso, se não)"""
        from ipe.auth import session as S
        titulo = self.windowTitle()
        if self.remoto and self.opcoes_servidor.get("erro"):
            QMessageBox.warning(self, titulo, tr("O servidor não respondeu às opções do lote: {}").format(
                self.opcoes_servidor["erro"]))
            return None
        cfg = self.config()
        ls = self.linhas()
        if not [l for l in ls if l.criterios(cfg)]:
            self.passos.setCurrentRow(0)
            QMessageBox.information(self, titulo, tr("Escolha a planilha e marque as colunas: ID + data, nº de acesso "
                                                     "ou Study UID."))
            return None
        for p in self.permissoes(cfg) if not simular else (["query"] if cfg.nos else []):
            if not S.require(p, self):
                return None
        saida = self.e_saida.text().strip()
        if not saida:
            self.passos.setCurrentRow(4)
            QMessageBox.information(self, titulo, tr("Escolha onde gravar a planilha de saída."))
            return None
        if Path(saida).resolve() == Path(self.e_arquivo.text()).resolve():
            QMessageBox.warning(self, titulo, tr("A planilha de saída não pode ser a mesma da lista."))
            return None
        if cfg.exportar_pasta and not Path(cfg.exportar_pasta).is_dir():
            QMessageBox.warning(self, titulo, tr("A pasta de exportação não existe."))
            return None
        return cfg

    def montar(self, simular: bool) -> L.Lote | None:
        from ipe.automation import lote_ipe as LP
        ok, motivo = LP.pronto(self.repo)
        if not ok:
            QMessageBox.warning(self, self.windowTitle(), motivo)
            return None
        cfg = self.validar(simular)
        if cfg is None:
            return None
        ls = self.linhas()
        saida = self.e_saida.text().strip()
        ident = self.repo.identity(self.c_ident.currentData()) if self.c_ident.currentData() else None
        return L.Lote(self.dados[0], self.dados[1:], ls, cfg, self._servicos(ident), saida, simular=simular,
                      limite=self.s_limite.value())

    def iniciar(self, simular: bool = False) -> None:
        if self.linha_de_fundo is not None and self.linha_de_fundo.is_alive():
            return
        if self.remoto:
            self.iniciar_no_servidor(simular)
            return
        lote = self.montar(simular)
        if lote is None:
            return
        falta = len(lote.por_fazer(com_limite=False))
        total = len(lote.linhas)
        if not falta:
            lote.gravar_planilha()
            QMessageBox.information(self, self.windowTitle(), tr("Todas as linhas já têm resposta nessa planilha de "
                                                                 "saída. Ela foi gravada de novo."))
            return
        self.lote = lote
        self.parar.clear()
        self.passos.setCurrentRow(4)
        self.barra.setRange(0, total)
        self.barra.setValue(total - falta)
        self.diario.appendPlainText(("— " + tr("Simulação") + " —") if simular else
                                    ("— " + tr("O que fazer: {}").format(", ".join(lote.cfg.acoes())) + " —"))
        if total - falta and not simular:
            self.diario.appendPlainText(tr("Continuando: {} de {} já feitas.").format(total - falta, total))
        self._ocupado(True)
        try:
            self.repo.audit("lote", f"lote a partir de planilha: {falta} linha(s); {', '.join(lote.cfg.acoes())}"
                            + (" (simulação)" if simular else ""))
        except Exception:  # noqa: BLE001
            log.debug("registro do lote", exc_info=True)

        def rodar():
            erro = ""
            a = None
            try:
                a = lote.rodar(self.parar, lambda a, l, r: self.sinais.linha.emit(a, l, r))
            except Exception as e:  # noqa: BLE001
                log.exception("lote")
                erro = str(e)
            self.sinais.fim.emit(a, erro)
        self.linha_de_fundo = threading.Thread(target=rodar, name="lote", daemon=True)
        self.linha_de_fundo.start()

    # ================================================================== no servidor (Ipê cliente, 0.100.98)
    @staticmethod
    def _json(v):
        """A célula como vai ao servidor (data em texto)."""
        from datetime import date, datetime
        if isinstance(v, datetime):
            return v.strftime("%Y-%m-%d %H:%M:%S") if (v.hour, v.minute, v.second) != (0, 0, 0) \
                else v.strftime("%Y-%m-%d")
        if isinstance(v, date):
            return v.strftime("%Y-%m-%d")
        return v

    def iniciar_no_servidor(self, simular: bool) -> None:
        if self.remoto_id and self._timer_remoto.isActive():
            return
        cfg = self.validar(simular)
        if cfg is None:
            return
        exportar = bool(cfg.exportar_pasta)
        self.pasta_exportar_local = cfg.exportar_pasta
        cfg.exportar_pasta = ""                         # quem decide a pasta é o servidor
        corpo = {"nome": Path(self.e_saida.text().strip()).stem, "cabecalho": [self._json(v) for v in self.dados[0]],
                 "dados": [[self._json(v) for v in linha] for linha in self.dados[1:]], "config": cfg.to_dict(),
                 "simular": simular, "limite": self.s_limite.value(), "exportar": exportar,
                 "trazer": self.k_trazer.isChecked() and not simular}
        # 0.100.100: as IAs rodam neste computador (preferência + perfil + pacote instalado) e sobem ao servidor
        from ipe.ai import onde as OND
        onde, aviso = OND.decidir(self.repo, self.settings)
        corpo["ia_no_cliente"] = bool(cfg.ias) and not simular and onde == OND.LOCAL
        self.remoto_ia_rodando = set()
        try:
            r = self.repo.client.rpc("lote_iniciar", corpo)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, self.windowTitle(), tr("O servidor não começou o lote: {}").format(e))
            return
        self.remoto_id, self.remoto_desde, self.remoto_simular = r["id"], 0, simular
        self.remoto_copiando = set()
        self.remoto_falhas = {}
        self.passos.setCurrentRow(4)
        self.diario.appendPlainText(tr("O lote roda no servidor central; esta janela acompanha (pode fechar e "
                                       "abrir de novo: mande com o mesmo nome para continuar)."))
        if corpo.get("trazer"):
            self.diario.appendPlainText(tr("Cada exame vem para este computador assim que chega ao servidor: deixe esta "
                                           "janela aberta enquanto o lote roda."))
        if corpo["ia_no_cliente"]:
            self.diario.appendPlainText(tr("As IAs rodam neste computador e o resultado sobe ao servidor: deixe esta "
                                           "janela aberta enquanto o lote roda."))
        elif cfg.ias and aviso and not simular:
            self.diario.appendPlainText(tr("As IAs rodam no servidor: {}.").format(tr(aviso)))
        self._ocupado(True)
        self._timer_remoto.start()

    @property
    def _timer_remoto(self):
        from PySide6.QtCore import QTimer
        t = getattr(self, "_timer_r", None)
        if t is None:
            t = self._timer_r = QTimer(self)
            t.setInterval(1500)
            t.timeout.connect(self._acompanhar)
        return t

    def _acompanhar(self) -> None:
        try:
            e = self.repo.client.rpc("lote_estado", self.remoto_id, self.remoto_desde)
        except Exception as x:  # noqa: BLE001
            self.l_estado.setText(tr("Sem resposta do servidor: {}").format(x))
            return
        self.remoto_desde = e.get("n_diario", self.remoto_desde)
        for d in e.get("diario") or []:
            self.diario.appendPlainText(self._linha_do_servidor(d))
        self.barra.setRange(0, max(1, e.get("total") or 0))
        self.barra.setValue(e.get("feitos") or 0)
        falta = duracao(e.get("falta_s"))
        txt = tr("{} de {}").format(e.get("feitos") or 0, e.get("total") or 0)
        if e.get("esperando"):
            txt = tr("Esperando: {}").format(e["esperando"])
        elif falta:
            txt += " · " + tr("faltam cerca de {}").format(falta)
        self.l_estado.setText(txt + "\n" + self._contagem(e.get("contagem") or {}))
        for p in e.get("pedidos_ia") or []:
            if p["study_uid"] not in self.remoto_ia_rodando:
                self.remoto_ia_rodando.add(p["study_uid"])
                threading.Thread(target=self._rodar_ia_aqui, args=(p,), name="lote-ia-aqui", daemon=True).start()
        for uid in e.get("para_copiar") or []:
            if self.remoto_falhas.get(uid, 0) >= 2:      # 0.100.111: já tentou 2 rodadas; fica no servidor
                continue
            if uid not in self.remoto_copiando:
                self.remoto_copiando.add(uid)
                threading.Thread(target=self._copiar, args=(uid,), name="lote-copiar", daemon=True).start()
        if not e.get("rodando"):
            self._timer_remoto.stop()
            self._ocupado(False)
            if e.get("erro"):
                self.l_estado.setText(tr("O lote parou com erro: {}").format(e["erro"]))
            elif not self.remoto_simular:
                self._baixar_saidas(e)

    @staticmethod
    def _linha_do_servidor(d) -> str:
        """Uma linha do diário que veio do servidor, no idioma deste Ipê: {"linha", "partes", "faixa"}."""
        if isinstance(d, str):
            return tr(d)
        partes = []
        for p in d.get("partes") or []:
            partes.append(tr(p[0]).format(*p[1:]) if isinstance(p, list) else tr(str(p)))
        txt = " — ".join(x for x in partes if x)
        if d.get("faixa"):
            return f"— {txt} —"
        return (tr("Linha {}").format(d["linha"]) + ": " + txt) if d.get("linha") else txt

    def _rodar_ia_aqui(self, p: dict) -> None:
        """O servidor pediu as IAs deste exame a este computador (0.100.100): traz o exame, roda, sobe o resultado e
        avisa. O que não deu certo aqui o servidor faz ele mesmo ao recolher (a IA cai para o servidor)."""
        uid = p["study_uid"]
        msg = ""
        try:
            self.repo.download(uid)
            from ipe.automation import lote_ias as LIA
            ex = LIA.Executor(self.repo, self.db, self.storage_root, self.settings, self.engine,
                              chamar=lambda fn: self.ponte.chamar(fn, espera=900))
            res = ex.rodar(uid, list(p.get("tipos") or []), bool(p.get("refazer")), self.parar)
            falhas = [f"{x.get('titulo')}: {x.get('motivo')}" for x in res.values() if x.get("situacao") == LIA.ERRO]
            if falhas:
                msg = "; ".join(falhas)
                log.warning("lote: IAs neste computador com falha (o servidor tenta): %s", msg)
            self.repo.upload_study(uid, wait=True)
        except Exception as x:  # noqa: BLE001
            log.exception("lote: IAs neste computador")
            msg = str(x)
        try:
            self.repo.client.rpc("lote_ia_feita", self.remoto_id, uid, not self.parar.is_set(), msg)
        except Exception:  # noqa: BLE001
            log.exception("lote: avisar o servidor")

    def diario_anotar(self, texto: str) -> None:
        self.diario.appendPlainText(texto)

    def _avisar(self, texto: str) -> None:
        sinais = getattr(self, "sinais", None)
        if sinais is not None:
            sinais.aviso.emit(texto)

    def _copiar(self, uid: str) -> None:
        """Traz o exame do servidor para o banco deste computador e avisa o servidor — só quando chegou **inteiro**
        (0.100.107: o servidor pode apagar o dele em seguida). Tenta de novo o que faltou, até 3 vezes.
        0.100.111: começa assim que o exame chega ao servidor; no fim da linha o servidor pede de novo (só o que
        faltar, como as séries das IAs); o andamento aparece no diário."""
        ref = "…" + uid[-8:]
        try:
            for tentativa in range(3):
                if self.parar.is_set():
                    return
                try:
                    th, _primeiro, _parar = self.repo.baixar_em_segundo_plano(uid)
                    th.join()
                    faltam = self.repo.missing_series(uid) if hasattr(self.repo, "missing_series") else (
                        [] if self.repo.is_cached(uid) else ["?"])
                    if not faltam:
                        try:
                            n = int(self.repo.local.imagens_por_exame([uid]).get(uid, 0))
                        except Exception:  # noqa: BLE001
                            n = -1                         # não sei contar: o servidor confere pelas séries
                        self.repo.client.rpc("lote_copiado", self.remoto_id, uid, n)
                        self._avisar(tr("Exame {} neste computador.").format(ref))
                        return
                    log.warning("lote: %s chegou incompleto (%d série(s) faltando), tentativa %d", uid, len(faltam),
                                tentativa + 1)
                except Exception:  # noqa: BLE001
                    log.exception("lote: copiar %s para este computador", uid)
            log.error("lote: %s não chegou inteiro a este computador; o servidor não apaga o dele", uid)
            falhas = getattr(self, "remoto_falhas", None)
            if falhas is not None:
                falhas[uid] = falhas.get(uid, 0) + 1
            self._avisar(tr("Exame {}: não chegou inteiro a este computador; ficou no servidor.").format(ref))
        finally:
            copiando = getattr(self, "remoto_copiando", None)
            if copiando is not None:
                copiando.discard(uid)            # o servidor pode pedir de novo (fim da linha)

    def _baixar_saidas(self, e: dict) -> None:
        import base64
        import io
        import zipfile
        feitos = []
        saida = Path(self.e_saida.text().strip())
        try:
            if e.get("saida"):
                r = self.repo.client.rpc("lote_arquivo", self.remoto_id, "saida")
                saida.write_bytes(base64.b64decode(r["dados"]))
                feitos.append(str(saida))
            if e.get("chave"):
                r = self.repo.client.rpc("lote_arquivo", self.remoto_id, "chave")
                chave = saida.with_name(saida.stem + "-chave" + saida.suffix)
                chave.write_bytes(base64.b64decode(r["dados"]))
                feitos.append(str(chave))
            pasta = getattr(self, "pasta_exportar_local", "")
            if e.get("exportados") and pasta:
                r = self.repo.client.rpc("lote_arquivo", self.remoto_id, "exportados")
                with zipfile.ZipFile(io.BytesIO(base64.b64decode(r["dados"]))) as z:
                    z.extractall(pasta)
                feitos.append(pasta)
        except Exception as x:  # noqa: BLE001
            self.l_estado.setText(tr("Não deu para baixar a saída do servidor: {}").format(x))
            return
        self.l_estado.setText(tr("Terminado.") + " " + tr("Planilha gravada em {}").format(", ".join(feitos))
                              + "\n" + self._contagem(e.get("contagem") or {}))

    def pedir_parada(self) -> None:
        if self.remoto and self.remoto_id:
            try:
                self.repo.client.rpc("lote_parar", self.remoto_id)
            except Exception as x:  # noqa: BLE001
                log.warning("parar o lote no servidor: %s", x)
        self.parar.set()
        self.b_parar.setEnabled(False)
        self.l_estado.setText(tr("Parando no fim desta linha…"))

    def _ocupado(self, on: bool) -> None:
        self.b_iniciar.setEnabled(not on)
        self.b_simular.setEnabled(not on)
        self.b_parar.setEnabled(on)
        for i in range(4):
            self.pilha.widget(i).setEnabled(not on)
        for w in (self.e_saida, self.k_anon, self.k_janela, self.t_de, self.t_ate, self.k_refazer, self.s_limite,
                  self.c_modelo):
            w.setEnabled(not on)

    @staticmethod
    def _contagem(c: dict) -> str:
        return " · ".join(f"{tr(k)}: {v}" for k, v in sorted(c.items(), key=lambda kv: -kv[1]))

    def _andou(self, a, linha, r) -> None:
        self.barra.setValue(a.feitos)
        if linha is None:
            self.l_estado.setText(tr("Esperando: {}").format(a.esperando))
            return
        falta = duracao(a.falta_s())
        self.l_estado.setText(tr("{} de {}").format(a.feitos, a.total)
                              + (" · " + tr("faltam cerca de {}").format(falta) if falta else "")
                              + "\n" + self._contagem(a.contagem))
        partes = [tr(r.get("situacao", ""))]
        for e in r.get("exames") or []:
            ias = e.get("ias") or {}
            ok = sum(1 for x in ias.values() if x.get("situacao") in (LIA.FEITA, LIA.JA_FEITA))
            if ias:
                partes.append(tr("IAs: {} de {}").format(ok, len(ias)))
        if r.get("observacao"):
            partes.append(r["observacao"])
        for e in r.get("exames") or []:
            if e.get("observacao"):
                partes.append(e["observacao"])
        self.diario.appendPlainText(tr("Linha {}").format(linha.n + 2) + ": " + " — ".join(p for p in partes if p))

    def _acabou(self, a, erro: str) -> None:
        self._ocupado(False)
        self.linha_de_fundo = None
        if erro:
            self.l_estado.setText(tr("O lote parou com erro: {}").format(erro))
            return
        fim = tr("Parado.") if self.parar.is_set() else tr("Terminado.")
        if self.lote is not None and self.lote.simular:
            self.l_estado.setText(fim + " " + tr("Simulação") + "\n" + self._contagem(a.contagem if a else {}))
            return
        saida = self.lote.saida if self.lote else ""
        self.l_estado.setText(fim + " " + tr("Planilha gravada em {}").format(saida) + "\n"
                              + self._contagem(a.contagem if a else {}))

    def closeEvent(self, e) -> None:
        trazendo = getattr(self, "remoto_id", None) and self._timer_remoto.isActive() and self.k_trazer.isChecked()
        if trazendo:
            r = QMessageBox.question(self, self.windowTitle(), tr("O lote continua no servidor, mas os exames só vêm para "
                                                                  "este computador com esta janela aberta. Fechar?\n"
                                                                  "Ao abrir de novo com o mesmo nome, o que faltou vem."))
            if r != QMessageBox.Yes:
                e.ignore()
                return
        if self.linha_de_fundo is not None and self.linha_de_fundo.is_alive():
            r = QMessageBox.question(self, self.windowTitle(), tr("O lote está rodando. Parar e fechar?\nO que já foi "
                                                                  "feito fica gravado; dá para continuar depois."))
            if r != QMessageBox.Yes:
                e.ignore()
                return
            self.parar.set()
            self.linha_de_fundo.join(timeout=20)
        e.accept()
