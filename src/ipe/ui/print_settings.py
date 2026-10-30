"""Configurações de impressão, numa janela só: servidores, destinos, regras, modelos e automático.

Separada das configurações de rede de propósito — impressão tem vida própria: mais de uma
"impressora" na rede, para onde cada coisa vai, como a folha é desenhada.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton,
    QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ipe.printing import auto_film as AF
from ipe.printing import config as C
from ipe.printing import dispatch as D
from ipe.printing import layout as L
from ipe.printing import origins as O
from ipe.printing import rules as R
from ipe.ui.tabelas import colunas_ajustaveis

log = logging.getLogger(__name__)

COLUNAS_SERVIDOR = ["Ligado", "Nome", "AE Title", "Porta", "Aceita", "Ao receber", "Modelo de folha",
                    "No banco", "Situação"]


def _quando(iso: str) -> str:
    """ISO -> 22/09/2026 14:05. Vazio vira travessão."""
    t = (iso or "").strip()
    if len(t) < 10:
        return "—"
    dia = f"{t[8:10]}/{t[5:7]}/{t[0:4]}"
    return f"{dia} {t[11:16]}" if len(t) >= 16 else dia


def _ips() -> str:
    from ipe.ui.network_dialog import local_ips
    return ", ".join(local_ips()) or "?"


def nome_de_copia(nome: str, existentes) -> str:
    """"Mamografia" -> "Mamografia (cópia)"; se já existe, "(cópia 2)", "(cópia 3)"…"""
    import re
    base = re.sub(r"\s*\(cópia(?: \d+)?\)$", "", (nome or "").strip()) or "Sem nome"
    usados = set(existentes)
    n = 1
    while True:
        novo = f"{base} (cópia)" if n == 1 else f"{base} (cópia {n})"
        if novo not in usados:
            return novo
        n += 1


class _TabelaLista(QTableWidget):
    """Tabela que responde como lista (currentRow / setCurrentRow), linha inteira selecionada."""

    def __init__(self, colunas: list[str], parent=None):
        super().__init__(0, len(colunas), parent)
        self.setHorizontalHeaderLabels(colunas)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.setWordWrap(False)

    def setCurrentRow(self, i: int) -> None:  # noqa: N802
        if 0 <= i < self.rowCount():
            self.selectRow(i)
            self.setCurrentCell(i, 1 if self.columnCount() > 1 else 0)


class _ListaCadastro(QWidget):
    """Lista com Novo / Editar / Duplicar / Remover (e subir/descer quando a ordem importa).

    Com `colunas`, a lista é uma tabela (cadastro com mais de dois campos vira tabela)."""

    def __init__(self, titulo: str, com_ordem: bool = False, parent=None, colunas: list[str] | None = None):
        super().__init__(parent)
        self.list = _TabelaLista(colunas) if colunas else QListWidget()
        if colunas:
            self.list.cellDoubleClicked.connect(lambda *_: self.b_editar.click())
        else:
            self.list.itemDoubleClicked.connect(lambda _i: self.b_editar.click())
        self.b_novo = QPushButton("Novo…")
        self.b_editar = QPushButton("Editar…")
        self.b_duplicar = QPushButton("Duplicar…")
        self.b_duplicar.setToolTip("Abre uma cópia do item escolhido para você mudar só o que for diferente")
        self.b_remover = QPushButton("Remover")
        botoes = QHBoxLayout()
        for b in (self.b_novo, self.b_editar, self.b_duplicar, self.b_remover):
            botoes.addWidget(b)
        if com_ordem:
            self.b_sobe = QPushButton("▲")
            self.b_desce = QPushButton("▼")
            botoes.addWidget(self.b_sobe)
            botoes.addWidget(self.b_desce)
        botoes.addStretch(1)
        lay = QVBoxLayout(self)
        if titulo:
            rotulo = QLabel(titulo)
            rotulo.setWordWrap(True)
            lay.addWidget(rotulo)
        lay.addWidget(self.list, 1)
        lay.addLayout(botoes)



# ---------------------------------------------------------------------------
# servidores
# ---------------------------------------------------------------------------

class ServerEditor(QDialog):
    def __init__(self, srv: C.ServerConfig | None, settings, outros: list[C.ServerConfig], parent=None):
        super().__init__(parent)
        self.outros = outros
        self.setWindowTitle("Servidor de impressão")
        s = srv or C.ServerConfig(port=C.next_free_port(outros))
        self._base = s              # o que o editor não mostra (dias de guarda) passa adiante
        self.name = QLineEdit(s.name)
        self.enabled = QCheckBox("Ligado (recebe filmes das modalidades)")
        self.enabled.setChecked(s.enabled)
        self.ae = QLineEdit(s.ae_title)
        self.port = QSpinBox(minimum=1, maximum=65535, value=int(s.port))
        # não pode se chamar `self.accept`: apagaria o QDialog.accept e o OK nunca fecharia (0.81)
        self.aceitar_de = QComboBox()
        self.aceitar_de.addItem("Qualquer AE", "any")
        self.aceitar_de.addItem("Só nós cadastrados", "known")
        self.aceitar_de.setCurrentIndex(max(0, self.aceitar_de.findData(s.accept)))
        self.timeout = QSpinBox(minimum=10, maximum=600, suffix=" s", value=int(s.timeout))
        self.to_db = QCheckBox("Guardar cada folha recebida como exame no banco")
        self.to_db.setChecked(s.to_database)
        self.auto = QComboBox()
        self.auto.addItem("Segurar na lista (ou o que as regras mandarem)", "")
        for d in D.all_destinations(settings):
            self.auto.addItem(f"Encaminhar para {d.name}", d.name)
        self.auto.setCurrentIndex(max(0, self.auto.findData(s.auto_destination)))
        self.modelo = QComboBox()
        self.modelo.addItem("A folha como veio", "")
        for m in L.all_templates(settings):
            self.modelo.addItem(m.name, m.name)
        self.modelo.setCurrentIndex(max(0, self.modelo.findData(s.template)))
        f = QFormLayout()
        f.addRow("Nome:", self.name)
        f.addRow(self.enabled)
        f.addRow("AE Title:", self.ae)
        f.addRow("Porta:", self.port)
        f.addRow("Aceitar conexões de:", self.aceitar_de)
        f.addRow("Tempo limite:", self.timeout)
        f.addRow("Ao receber:", self.auto)
        f.addRow("Modelo de folha:", self.modelo)
        f.addRow(self.to_db)
        info = QLabel(f"Na modalidade, cadastre uma impressora DICOM com este AE, o IP <b>{_ips()}</b> "
                      f"e esta porta.")
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        nota = QLabel("<i>Impressora de filme costuma usar a porta 104. Este programa não roda como "
                      "administrador, e no Linux portas abaixo de 1024 exigem isso — por isso o padrão "
                      "é 11113. Quase toda modalidade aceita porta diferente.</i>")
        nota.setWordWrap(True)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(f)
        lay.addWidget(info)
        lay.addWidget(nota)
        lay.addWidget(bb)

    def _ok(self) -> None:
        nome, ae = self.name.text().strip(), self.ae.text().strip()
        if not nome or not ae:
            QMessageBox.warning(self, "Servidor", "Preencha o nome e o AE Title.")
            return
        if len(ae) > 16 or any(ord(c) > 126 for c in ae):
            QMessageBox.warning(self, "Servidor", "O AE Title tem no máximo 16 caracteres, sem acento.")
            return
        for o in self.outros:
            if o.port == self.port.value():
                QMessageBox.warning(self, "Servidor",
                                    f"A porta {o.port} já é do servidor “{o.name}”.")
                return
            if o.name == nome:
                QMessageBox.warning(self, "Servidor", "Já existe um servidor com esse nome.")
                return
        self.accept()

    def server(self) -> C.ServerConfig:
        import dataclasses
        return dataclasses.replace(self._base, name=self.name.text().strip(), enabled=self.enabled.isChecked(),
                              ae_title=self.ae.text().strip(), port=self.port.value(),
                              accept=self.aceitar_de.currentData(), timeout=self.timeout.value(),
                              to_database=self.to_db.isChecked(),
                              auto_destination=self.auto.currentData() or "",
                              template=self.modelo.currentData() or "")


# ---------------------------------------------------------------------------
# regras
# ---------------------------------------------------------------------------

COLUNAS_AUTO = ["Ligada", "Nome", "Origem (AE)", "Recebido por", "Modalidade", "Outras condições",
                "Grade", "Imagens", "Depois", "Modelo"]
COLUNAS_REGRA = ["Ligada", "Nome", "Origem (AE)", "Recebido por", "Modalidade", "Outras condições",
                 "Destino", "Modelo", "Parar aqui"]
COLUNAS_ORIGEM = ["Nome", "AE", "Modalidade", "Endereço", "Servidor", "Trabalhos", "Visto pela última vez"]


class OriginEditor(QDialog):
    """Dá nome a um aparelho que mandou trabalhos de impressão."""

    def __init__(self, origem: O.Origin, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Origem de impressão")
        self.orig = origem
        self.name = QLineEdit(origem.name or O.suggest_name(origem.calling_ae))
        self.name.setPlaceholderText("Ex.: TC Sala 2")
        self.enabled = QCheckBox("Aceitar trabalhos desta origem")
        self.enabled.setChecked(origem.enabled)
        self.note = QLineEdit(origem.note, placeholderText="Observação (opcional)")
        self.modalidade = QLineEdit(origem.modality, placeholderText="Ex.: MG (opcional)")
        self.modalidade.setToolTip("A modalidade deste aparelho. Vale para as regras por modalidade "
                                   "quando o paciente do filme não foi identificado (com o paciente "
                                   "identificado, vale a modalidade do exame dele).")
        f = QFormLayout()
        f.addRow("Nome amigável:", self.name)
        f.addRow(self.enabled)
        f.addRow("Modalidade:", self.modalidade)
        f.addRow("Observação:", self.note)
        f.addRow(QLabel("<b>Como o aparelho se identifica</b>"))
        f.addRow("AE title:", QLabel(origem.calling_ae or "—"))
        f.addRow("Endereço:", QLabel(", ".join(origem.hosts()) or "—"))
        f.addRow("Recebido em:", QLabel(origem.server or "—"))
        f.addRow("Trabalhos:", QLabel(str(origem.jobs or 0)))
        lay = QVBoxLayout(self)
        lay.addLayout(f)
        parecidas = O.same_ae_elsewhere(settings, origem.calling_ae, origem.remote_host,
                                        origem.server)
        self.mesma = None
        if parecidas and not origem.registered:
            aviso = QLabel("Já existe origem cadastrada com este mesmo AE, em outro endereço. "
                           "Se for o mesmo aparelho que mudou de IP, junte os dois em vez de "
                           "cadastrar de novo — as regras continuam valendo.")
            aviso.setWordWrap(True)
            aviso.setStyleSheet("color:#e0c070;")
            lay.addWidget(aviso)
            linha = QHBoxLayout()
            self.mesma = QComboBox()
            for o in parecidas:
                self.mesma.addItem(o.label(), o.id)
            linha.addWidget(self.mesma, 1)
            b = QPushButton("É o mesmo aparelho")
            b.clicked.connect(self._juntar)
            linha.addWidget(b)
            lay.addLayout(linha)
        self.juntar_em = ""
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _juntar(self) -> None:
        if self.mesma is not None:
            self.juntar_em = self.mesma.currentData() or ""
            self.accept()

    def _ok(self) -> None:
        if not self.name.text().strip():
            QMessageBox.warning(self, "Origem", "Dê um nome à origem para poder usá-la em regras.")
            return
        self.accept()

    def origin(self) -> O.Origin:
        o = self.orig
        o.name = self.name.text().strip()
        o.enabled = self.enabled.isChecked()
        o.note = self.note.text().strip()
        o.modality = self.modalidade.text().strip().upper()
        return o


#: modalidades que aparecem sempre na lista da regra (as das origens e das regras entram junto)
MODALIDADES_COMUNS = ["MG", "CT", "MR", "US", "CR", "DX", "NM", "PT", "XA", "RF", "OT"]


class _Marcas(QListWidget):
    """Lista de marcar: nenhum marcado = qualquer."""

    def __init__(self, itens: list[tuple[str, str]], marcados, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        marcados = {str(m).upper() for m in (marcados or [])}
        for texto, dado in itens:
            self.acrescentar(texto, dado, str(dado).upper() in marcados)

    def acrescentar(self, texto: str, dado: str, marcado: bool = True) -> None:
        from PySide6.QtWidgets import QListWidgetItem
        for i in range(self.count()):
            if str(self.item(i).data(Qt.UserRole)).upper() == str(dado).upper():
                self.item(i).setCheckState(Qt.Checked if marcado else self.item(i).checkState())
                return
        it = QListWidgetItem(texto)
        it.setData(Qt.UserRole, dado)
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
        it.setCheckState(Qt.Checked if marcado else Qt.Unchecked)
        self.addItem(it)

    def marcados(self) -> list[str]:
        return [self.item(i).data(Qt.UserRole) for i in range(self.count())
                if self.item(i).checkState() == Qt.Checked]

    def marcar(self, dados) -> None:
        alvo = {str(d).upper() for d in dados}
        for i in range(self.count()):
            it = self.item(i)
            it.setCheckState(Qt.Checked if str(it.data(Qt.UserRole)).upper() in alvo else Qt.Unchecked)


class RuleEditor(QDialog):
    """Regra de encaminhamento (0.85): quem mandou, qual AE meu recebeu e a modalidade, por listas.

    Pedido dele: *"quero criar regras podendo selecionar origem (aetitle), qual ae meu recebeu,
    modalidade e daí criar regras diferentes"*. Em cada lista dá para marcar vários; nenhum marcado
    é "qualquer". O resto (rótulo, filme, folhas, horário, origem por endereço) fica em "Outras
    condições", que abre sozinho quando a regra já usa alguma delas.
    """

    def __init__(self, rule: R.Rule | None, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Regra de encaminhamento")
        self.resize(820, 640)
        r = rule or R.Rule()
        self._base = r
        self.name = QLineEdit(r.name)
        self.enabled = QCheckBox("Ligada")
        self.enabled.setChecked(r.enabled)

        # ---- quem mandou: os AE titles já vistos (com o nome dado em Origens)
        origens = O.all_origins(settings)
        nomes: dict[str, list[str]] = {}
        for o in origens:
            if o.calling_ae:
                nomes.setdefault(o.calling_ae.upper(), [])
                if o.name and o.name not in nomes[o.calling_ae.upper()]:
                    nomes[o.calling_ae.upper()].append(o.name)
        itens_ae = [(f"{ae} — {', '.join(n)}" if n else f"{ae} (sem nome)", ae) for ae, n in sorted(nomes.items())]
        self.l_aes = _Marcas(itens_ae, r.aes())
        for ae in r.aes():                       # AE de regra antiga que não aparece mais
            self.l_aes.acrescentar(f"{ae} (não visto)", ae, True)
        self.novo_ae = QLineEdit(placeholderText="Outro AE title…")
        self.novo_ae.setToolTip("AE de um aparelho que ainda não mandou nada")
        b_ae = QPushButton("+")
        b_ae.setFixedWidth(28)
        b_ae.clicked.connect(self._mais_ae)
        self.novo_ae.returnPressed.connect(self._mais_ae)

        # ---- meu AE que recebeu: os servidores de impressão
        itens_srv = [(f"{s.ae_title} (porta {s.port}) — {s.name}", s.name) for s in C.all_servers(settings)]
        self.l_servers = _Marcas(itens_srv, r.servidores())
        for nome in r.servidores():
            self.l_servers.acrescentar(f"{nome} (servidor apagado)", nome, True)

        # ---- modalidade
        mods = list(MODALIDADES_COMUNS)
        for m in [o.modality for o in origens] + [m for x in R.all_rules(settings) for m in x.modalidades()] \
                + r.modalidades():
            for parte in str(m or "").replace("\\", "|").split("|"):
                if parte.strip() and parte.strip().upper() not in mods:
                    mods.append(parte.strip().upper())
        self.l_mods = _Marcas([(m, m) for m in mods], r.modalidades())
        self.l_mods.setToolTip("Modalidade do exame do paciente (achado pelo OCR ou confirmado à mão) "
                               "ou, sem paciente, a da origem cadastrada. Trabalho de modalidade "
                               "desconhecida não combina com regra que exige modalidade.")
        self.nova_mod = QLineEdit(placeholderText="Outra…")
        b_mod = QPushButton("+")
        b_mod.setFixedWidth(28)
        b_mod.clicked.connect(self._mais_mod)
        self.nova_mod.returnPressed.connect(self._mais_mod)

        colunas = QHBoxLayout()
        for titulo, lista, extra in (("Origem (AE title de quem mandou)", self.l_aes, (self.novo_ae, b_ae)),
                                     ("Recebido por (meu AE)", self.l_servers, None),
                                     ("Modalidade", self.l_mods, (self.nova_mod, b_mod))):
            caixa = QVBoxLayout()
            caixa.addWidget(QLabel(f"<b>{titulo}</b>"))
            caixa.addWidget(lista, 1)
            if extra:
                linha = QHBoxLayout()
                linha.addWidget(extra[0], 1)
                linha.addWidget(extra[1])
                caixa.addLayout(linha)
            colunas.addLayout(caixa, 1)
        dica = QLabel("<i>Marque um ou vários em cada lista. Lista sem nada marcado = qualquer. "
                      "O trabalho precisa combinar com as três.</i>")
        dica.setWordWrap(True)

        # ---- outras condições
        self.origem = QComboBox()
        self.origem.addItem("Qualquer origem", "")
        for o in origens:
            if o.registered:
                self.origem.addItem(o.label(), o.id)
        if r.origin and self.origem.findData(r.origin) < 0:
            self.origem.addItem(f"(origem apagada) {r.origin}", r.origin)
        self.origem.setCurrentIndex(max(0, self.origem.findData(r.origin)))
        self.origem.setToolTip("O aparelho exato (AE + endereço + servidor), como está em Origens")
        self.ae = QLineEdit(r.calling_ae, placeholderText="Ex.: MG*  (vazio = qualquer)")
        self.label = QLineEdit(r.label, placeholderText="Texto no rótulo da sessão (aceita *)")
        self.film = QLineEdit(r.film_size, placeholderText="Ex.: 14INX17IN")
        self.min_sheets = QSpinBox(minimum=0, maximum=99, value=int(r.min_sheets))
        self.max_sheets = QSpinBox(minimum=0, maximum=99, value=int(r.max_sheets))
        self.h_de = QSpinBox(minimum=0, maximum=23, value=int(r.hour_from), suffix=" h")
        self.h_ate = QSpinBox(minimum=0, maximum=23, value=int(r.hour_to), suffix=" h")
        outras = QFormLayout()
        outras.addRow("Aparelho cadastrado:", self.origem)
        outras.addRow("AE com curinga:", self.ae)
        outras.addRow("Rótulo contém:", self.label)
        outras.addRow("Tamanho do filme:", self.film)
        outras.addRow("A partir de (folhas):", self.min_sheets)
        outras.addRow("Até (folhas, 0 = sem limite):", self.max_sheets)
        horas = QHBoxLayout()
        horas.addWidget(self.h_de)
        horas.addWidget(QLabel("até"))
        horas.addWidget(self.h_ate)
        horas.addWidget(QLabel("(iguais = o dia todo)"))
        outras.addRow("Horário:", self._wrap(horas))
        self.caixa_outras = self._wrap(outras)
        self.b_outras = QPushButton("Outras condições ▸")
        self.b_outras.setCheckable(True)
        self.b_outras.setFlat(True)
        self.b_outras.setStyleSheet("text-align:left")
        self.b_outras.toggled.connect(self._mostrar_outras)
        usa = bool(r.origin or r.calling_ae or r.label or r.film_size or r.min_sheets or r.max_sheets
                   or r.hour_from != r.hour_to)
        self.b_outras.setChecked(usa)
        self._mostrar_outras(usa)

        # ---- então
        self.dest = QComboBox()
        for d in D.all_destinations(settings):
            self.dest.addItem(d.label(), d.name)
        self.dest.setCurrentIndex(max(0, self.dest.findData(r.destination)))
        self.modelo = QComboBox()
        self.modelo.addItem("O modelo do servidor (ou como veio)", "")
        for m in L.all_templates(settings):
            self.modelo.addItem(m.name, m.name)
        self.modelo.setCurrentIndex(max(0, self.modelo.findData(r.template)))
        self.stop = QCheckBox("Parar aqui (não olhar as regras seguintes)")
        self.stop.setChecked(r.stop)
        entao = QFormLayout()
        entao.addRow("Mandar para:", self.dest)
        entao.addRow("Modelo de folha:", self.modelo)
        entao.addRow(self.stop)

        topo = QFormLayout()
        topo.addRow("Nome:", self.name)
        topo.addRow(self.enabled)
        self.resumo = QLabel("")
        self.resumo.setWordWrap(True)
        self.resumo.setStyleSheet("color:#9a9a9a")
        for lista in (self.l_aes, self.l_servers, self.l_mods):
            lista.itemChanged.connect(self._atualizar_resumo)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(topo)
        lay.addWidget(QLabel("<b>Quando</b>"))
        lay.addLayout(colunas, 1)
        lay.addWidget(dica)
        lay.addWidget(self.b_outras)
        lay.addWidget(self.caixa_outras)
        lay.addWidget(QLabel("<b>Então</b>"))
        lay.addLayout(entao)
        lay.addWidget(self.resumo)
        lay.addWidget(bb)
        self._atualizar_resumo()

    def _mostrar_outras(self, on: bool) -> None:
        self.caixa_outras.setVisible(bool(on))
        self.b_outras.setText("Outras condições ▾" if on else "Outras condições ▸")

    def _mais_ae(self) -> None:
        ae = self.novo_ae.text().strip().upper()
        if ae:
            self.l_aes.acrescentar(f"{ae} (não visto)", ae, True)
            self.novo_ae.clear()

    def _mais_mod(self) -> None:
        m = self.nova_mod.text().strip().upper()
        if m:
            self.l_mods.acrescentar(m, m, True)
            self.nova_mod.clear()

    def _atualizar_resumo(self, *_a) -> None:
        self.resumo.setText("Resumo: " + self.rule().label_text())

    @staticmethod
    def _wrap(layout) -> QWidget:
        w = QWidget()
        w.setLayout(layout)
        return w

    def _ok(self) -> None:
        if not self.dest.count():
            QMessageBox.warning(self, "Regra", "Cadastre um destino primeiro (aba Destinos).")
            return
        self.accept()

    def rule(self) -> R.Rule:
        import dataclasses
        # os campos de um valor só (servidor, modalidade) das regras antigas viram as listas
        return dataclasses.replace(
            self._base, name=self.name.text().strip() or "Regra", enabled=self.enabled.isChecked(),
            calling_aes=self.l_aes.marcados(), servers=self.l_servers.marcados(),
            modalities=self.l_mods.marcados(), server="", modality="",
            origin=self.origem.currentData() or "", calling_ae=self.ae.text().strip(),
            label=self.label.text().strip(), film_size=self.film.text().strip(),
            min_sheets=self.min_sheets.value(), max_sheets=self.max_sheets.value(),
            hour_from=self.h_de.value(), hour_to=self.h_ate.value(),
            destination=self.dest.currentData() or "",
            template=self.modelo.currentData() or "", stop=self.stop.isChecked())


# ---------------------------------------------------------------------------
# modelos de folha
# ---------------------------------------------------------------------------

def aes_vistos(settings, repo=None, net=None) -> dict[str, str]:
    """AE title -> nome, de quem já mandou alguma coisa: nós DICOM, origens de impressão e o que
    chegou nesta sessão."""
    out: dict[str, str] = {}
    for o in O.all_origins(settings):
        if o.calling_ae:
            out.setdefault(o.calling_ae.upper(), o.name or "")
    if repo is not None:
        try:
            for n in repo.nodes():
                if n.get("ae_title"):
                    ae = str(n["ae_title"]).upper()
                    if not out.get(ae):
                        out[ae] = n.get("name", "") or ""
        except Exception:  # noqa: BLE001
            log.exception("nós DICOM para a regra")
    for rem in (getattr(getattr(net, "sink", None), "remetentes", {}) or {}).values():
        if rem.get("calling_ae"):
            out.setdefault(str(rem["calling_ae"]).upper(), "")
    return out


def meus_aes(settings, repo=None) -> list[tuple[str, str]]:
    """(AE title, de onde ele é): o AE do nó, as identidades e cada servidor de impressão."""
    out: list[tuple[str, str]] = []
    vistos = set()

    def poe(ae, onde):
        ae = (ae or "").strip().upper()
        if ae and ae not in vistos:
            vistos.add(ae)
            out.append((ae, onde))
    dicom = settings.get("dicom", {}) or {}
    poe(dicom.get("ae_title", "DICOMVIEWER") or "DICOMVIEWER", "nó DICOM")
    if repo is not None:
        try:
            for ident in repo.identities():
                poe(ident.get("ae_title", ""), "identidade")
        except Exception:  # noqa: BLE001
            log.exception("identidades para a regra")
    for srv in C.all_servers(settings):
        poe(srv.ae_title, f"impressora {srv.name}")
    return out


class AutoRuleEditor(QDialog):
    """Regra do filme automático (0.86): as mesmas três listas da regra de impressão — origem (AE de
    quem mandou), meu AE que foi chamado e modalidade — e, embaixo, como montar o filme."""

    def __init__(self, regra, settings, parent=None, repo=None, net=None):
        super().__init__(parent)
        self.setWindowTitle("Regra do filme automático")
        self.resize(820, 660)
        r = regra or AF.AutoRule()
        self._base = r
        self.name = QLineEdit(r.name)
        self.enabled = QCheckBox("Ligada")
        self.enabled.setChecked(r.enabled)

        vistos = aes_vistos(settings, repo, net)
        self.l_aes = _Marcas([(f"{ae} — {nome}" if nome else f"{ae} (sem nome)", ae)
                              for ae, nome in sorted(vistos.items())], r.calling_aes)
        for ae in r.calling_aes:
            self.l_aes.acrescentar(f"{ae} (não visto)", ae, True)
        self.novo_ae = QLineEdit(placeholderText="Outro AE title…")
        b_ae = QPushButton("+")
        b_ae.setFixedWidth(28)
        b_ae.clicked.connect(lambda: self._mais(self.novo_ae, self.l_aes, "(não visto)"))
        self.novo_ae.returnPressed.connect(lambda: self._mais(self.novo_ae, self.l_aes, "(não visto)"))

        self.l_meus = _Marcas([(f"{ae} ({onde})", ae) for ae, onde in meus_aes(settings, repo)], r.my_aes)
        for ae in r.my_aes:
            self.l_meus.acrescentar(f"{ae} (outro nome)", ae, True)
        self.l_meus.setToolTip("O AE title que a modalidade chamou. O nó aceita qualquer AE chamado na "
                               "mesma porta: dá para configurar no aparelho um AE diferente para cada "
                               "jeito de montar o filme.")
        self.novo_meu = QLineEdit(placeholderText="Outro AE meu…")
        b_meu = QPushButton("+")
        b_meu.setFixedWidth(28)
        b_meu.clicked.connect(lambda: self._mais(self.novo_meu, self.l_meus, "(outro nome)"))
        self.novo_meu.returnPressed.connect(lambda: self._mais(self.novo_meu, self.l_meus, "(outro nome)"))

        mods = list(MODALIDADES_COMUNS)
        for m in list(r.modalities) + [m for x in AF.all_rules(settings) for m in x.modalities]:
            if m and m.upper() not in mods:
                mods.append(m.upper())
        self.l_mods = _Marcas([(m, m) for m in mods], r.modalities)
        self.nova_mod = QLineEdit(placeholderText="Outra…")
        b_mod = QPushButton("+")
        b_mod.setFixedWidth(28)
        b_mod.clicked.connect(lambda: self._mais(self.nova_mod, self.l_mods, ""))
        self.nova_mod.returnPressed.connect(lambda: self._mais(self.nova_mod, self.l_mods, ""))

        colunas = QHBoxLayout()
        for titulo, lista, extra in (("Origem (AE title de quem mandou)", self.l_aes, (self.novo_ae, b_ae)),
                                     ("Recebido por (meu AE chamado)", self.l_meus, (self.novo_meu, b_meu)),
                                     ("Modalidade", self.l_mods, (self.nova_mod, b_mod))):
            caixa = QVBoxLayout()
            caixa.addWidget(QLabel(f"<b>{titulo}</b>"))
            caixa.addWidget(lista, 1)
            linha = QHBoxLayout()
            linha.addWidget(extra[0], 1)
            linha.addWidget(extra[1])
            caixa.addLayout(linha)
            colunas.addLayout(caixa, 1)
        dica = QLabel("<i>Marque um ou vários em cada lista. Lista sem nada marcado = qualquer. O exame "
                      "precisa combinar com as três. A primeira regra ligada que combinar monta o filme.</i>")
        dica.setWordWrap(True)

        self.descricao = QLineEdit(r.description, placeholderText="Ex.: MAMA|AXILA  (vazio = qualquer)")
        outras = QFormLayout()
        outras.addRow("Descrição do exame contém:", self.descricao)
        self.caixa_outras = RuleEditor._wrap(outras)
        self.b_outras = QPushButton("Outras condições ▸")
        self.b_outras.setCheckable(True)
        self.b_outras.setFlat(True)
        self.b_outras.setStyleSheet("text-align:left")
        self.b_outras.toggled.connect(self._mostrar_outras)
        self.b_outras.setChecked(bool(r.description))
        self._mostrar_outras(bool(r.description))

        self.rows = QSpinBox(minimum=1, maximum=8, value=int(r.rows))
        self.cols = QSpinBox(minimum=1, maximum=8, value=int(r.cols))
        grade = QHBoxLayout()
        grade.addWidget(self.rows)
        grade.addWidget(QLabel("×"))
        grade.addWidget(self.cols)
        grade.addStretch(1)
        self.paper = QComboBox()
        from ipe.printing.film import PAPERS
        for nome in PAPERS:
            self.paper.addItem(nome, nome)
        self.paper.setCurrentIndex(max(0, self.paper.findData(r.paper)))
        self.max_images = QSpinBox(minimum=0, maximum=60, value=int(r.max_images))
        self.max_images.setToolTip("0 = todas. Vale para o exame que chega pelo nó; as imagens mandadas "
                                   "à porta da impressora entram todas.")
        self.dest = QComboBox()
        self.dest.addItem("Só deixar pronto na lista de impressões", "")
        for d in D.all_destinations(settings):
            self.dest.addItem(f"Mandar para {d.name}", d.name)
        self.dest.setCurrentIndex(max(0, self.dest.findData(r.destination)))
        self.modelo = QComboBox()
        self.modelo.addItem("Sem modelo", "")
        for m in L.all_templates(settings):
            self.modelo.addItem(m.name, m.name)
        self.modelo.setCurrentIndex(max(0, self.modelo.findData(r.template)))
        entao = QFormLayout()
        entao.addRow("Grade:", RuleEditor._wrap(grade))
        entao.addRow("Papel:", self.paper)
        entao.addRow("Quantas imagens (0 = todas):", self.max_images)
        entao.addRow("Depois de montar:", self.dest)
        entao.addRow("Modelo de folha:", self.modelo)

        topo = QFormLayout()
        topo.addRow("Nome:", self.name)
        topo.addRow(self.enabled)
        self.resumo = QLabel("")
        self.resumo.setWordWrap(True)
        self.resumo.setStyleSheet("color:#9a9a9a")
        for lista in (self.l_aes, self.l_meus, self.l_mods):
            lista.itemChanged.connect(self._atualizar_resumo)
        for w in (self.rows, self.cols, self.max_images):
            w.valueChanged.connect(self._atualizar_resumo)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(topo)
        lay.addWidget(QLabel("<b>Quando chegar um exame</b>"))
        lay.addLayout(colunas, 1)
        lay.addWidget(dica)
        lay.addWidget(self.b_outras)
        lay.addWidget(self.caixa_outras)
        lay.addWidget(QLabel("<b>Montar o filme assim</b>"))
        lay.addLayout(entao)
        lay.addWidget(self.resumo)
        lay.addWidget(bb)
        self._atualizar_resumo()

    def _mostrar_outras(self, on: bool) -> None:
        self.caixa_outras.setVisible(bool(on))
        self.b_outras.setText("Outras condições ▾" if on else "Outras condições ▸")

    @staticmethod
    def _mais(campo: QLineEdit, lista: _Marcas, nota: str) -> None:
        v = campo.text().strip().upper()
        if v:
            lista.acrescentar(f"{v} {nota}".strip(), v, True)
            campo.clear()

    def _atualizar_resumo(self, *_a) -> None:
        self.resumo.setText("Resumo: " + self.regra().label_text())

    def regra(self):
        import dataclasses
        return dataclasses.replace(
            self._base, name=self.name.text().strip() or "Regra", enabled=self.enabled.isChecked(),
            calling_aes=self.l_aes.marcados(), my_aes=self.l_meus.marcados(), modalities=self.l_mods.marcados(),
            description=self.descricao.text().strip(), rows=self.rows.value(), cols=self.cols.value(),
            paper=self.paper.currentData() or "A4", max_images=self.max_images.value(),
            destination=self.dest.currentData() or "", template=self.modelo.currentData() or "")


class TemplateEditor(QDialog):
    def __init__(self, modelo: L.SheetTemplate | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Modelo de folha")
        self.resize(900, 620)
        t = modelo or L.SheetTemplate()
        self.name = QLineEdit(t.name)
        self.clinic = QLineEdit(t.clinic, placeholderText="Nome da clínica ou do serviço")
        self.subtitle = QLineEdit(t.subtitle, placeholderText="Endereço, telefone (uma linha)")
        self.logo = QLineEdit(t.logo)
        b_logo = QPushButton("Escolher…")
        b_logo.clicked.connect(self._escolher_logo)
        b_sem = QPushButton("Tirar")
        b_sem.clicked.connect(lambda: self.logo.setText(""))
        linha_logo = QHBoxLayout()
        linha_logo.addWidget(self.logo, 1)
        linha_logo.addWidget(b_logo)
        linha_logo.addWidget(b_sem)
        self.show_patient = QCheckBox("Paciente")
        self.show_patient.setChecked(t.show_patient)
        self.show_date = QCheckBox("Data")
        self.show_date.setChecked(t.show_date)
        self.show_source = QCheckBox("Aparelho de origem")
        self.show_source.setChecked(t.show_source)
        mostrar = QHBoxLayout()
        for c in (self.show_patient, self.show_date, self.show_source):
            mostrar.addWidget(c)
        mostrar.addStretch(1)
        self.footer = QLineEdit(t.footer, placeholderText="Frase do rodapé")
        self.dark = QCheckBox("Fundo preto (filme); desmarcado = papel branco")
        self.dark.setChecked(t.dark)
        self.remount = QCheckBox("Remontar a folha com a nossa grade (em vez de usar a folha como veio)")
        self.remount.setChecked(t.remount)
        self.remount.toggled.connect(self._preview)
        self.rows = QSpinBox(minimum=0, maximum=8, value=int(t.rows))
        self.cols = QSpinBox(minimum=0, maximum=8, value=int(t.cols))
        grade = QHBoxLayout()
        grade.addWidget(self.rows)
        grade.addWidget(QLabel("×"))
        grade.addWidget(self.cols)
        grade.addWidget(QLabel("(0 × 0 = a grade que veio)"))
        self.margin = QDoubleSpinBox(minimum=0, maximum=30, value=float(t.margin_mm), suffix=" mm")
        self.header = QDoubleSpinBox(minimum=0, maximum=60, value=float(t.header_mm), suffix=" mm")
        self.foot = QDoubleSpinBox(minimum=0, maximum=30, value=float(t.footer_mm), suffix=" mm")
        self.gap = QDoubleSpinBox(minimum=0, maximum=20, value=float(t.gap_mm), suffix=" mm")
        for w in (self.clinic, self.subtitle, self.logo, self.footer):
            w.textChanged.connect(self._preview)
        for w in (self.show_patient, self.show_date, self.show_source, self.dark):
            w.toggled.connect(self._preview)
        for w in (self.rows, self.cols):
            w.valueChanged.connect(self._preview)
        for w in (self.margin, self.header, self.foot, self.gap):
            w.valueChanged.connect(self._preview)
        f = QFormLayout()
        f.addRow("Nome do modelo:", self.name)
        f.addRow("Clínica:", self.clinic)
        f.addRow("Segunda linha:", self.subtitle)
        f.addRow("Logo:", RuleEditor._wrap(linha_logo))
        f.addRow("Mostrar:", RuleEditor._wrap(mostrar))
        f.addRow("Rodapé:", self.footer)
        f.addRow(self.dark)
        f.addRow(self.remount)
        f.addRow("Grade:", RuleEditor._wrap(grade))
        f.addRow("Margem:", self.margin)
        f.addRow("Altura do cabeçalho:", self.header)
        f.addRow("Altura do rodapé:", self.foot)
        f.addRow("Espaço entre imagens:", self.gap)
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumWidth(300)
        self.preview_label.setStyleSheet("background:#222;")
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        esquerda = QWidget()
        el = QVBoxLayout(esquerda)
        el.addLayout(f)
        el.addStretch(1)
        el.addWidget(bb)
        tudo = QHBoxLayout(self)
        tudo.addWidget(esquerda, 3)
        tudo.addWidget(self.preview_label, 2)
        self._preview()

    def _escolher_logo(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, "Logo", self.logo.text() or str(Path.home()),
                                           "Imagens (*.png *.jpg *.jpeg *.bmp)")
        if p:
            self.logo.setText(p)

    def _preview(self) -> None:
        try:
            img = L.preview(self.template(), dpi=70)
        except Exception:  # noqa: BLE001
            log.exception("prévia do modelo")
            return
        self.preview_label.setPixmap(QPixmap.fromImage(img).scaled(
            max(120, self.preview_label.width()), max(160, self.preview_label.height()),
            Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _ok(self) -> None:
        if not self.name.text().strip():
            QMessageBox.warning(self, "Modelo", "Dê um nome ao modelo.")
            return
        self.accept()

    def template(self) -> L.SheetTemplate:
        return L.SheetTemplate(
            name=self.name.text().strip() or "Modelo", clinic=self.clinic.text().strip(),
            subtitle=self.subtitle.text().strip(), logo=self.logo.text().strip(),
            show_patient=self.show_patient.isChecked(), show_date=self.show_date.isChecked(),
            show_source=self.show_source.isChecked(), footer=self.footer.text().strip(),
            dark=self.dark.isChecked(), margin_mm=self.margin.value(), header_mm=self.header.value(),
            footer_mm=self.foot.value(), remount=self.remount.isChecked(), rows=self.rows.value(),
            cols=self.cols.value(), gap_mm=self.gap.value())


# ---------------------------------------------------------------------------
# a janela
# ---------------------------------------------------------------------------

class PrintSettingsDialog(QDialog):
    """Tudo o que é de impressão num lugar só."""

    def __init__(self, settings, net=None, parent=None, repo=None):
        super().__init__(parent)
        self.settings, self.net = settings, net
        self.repo = repo if repo is not None else getattr(net, "repo", None)
        self.setWindowTitle("Configurações de impressão")
        self.resize(880, 600)
        self.servers = C.all_servers(settings)
        self.dests = D.all_destinations(settings)
        self.rules = R.all_rules(settings)
        self.origens = O.all_origins(settings)
        self.templates = L.all_templates(settings)
        tabs = QTabWidget()
        tabs.addTab(self._aba_servidores(), "Servidores")
        tabs.addTab(self._aba_destinos(), "Destinos")
        tabs.addTab(self._aba_origens(), "Origens")
        tabs.addTab(self._aba_regras(), "Regras")
        tabs.addTab(self._aba_modelos(), "Modelos de folha")
        tabs.addTab(self._aba_automatico(), "Automático")
        tabs.addTab(self._aba_limpeza(), "Limpeza")
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self._salvar)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(bb)

    # -------------------------------------------------------------- servidores
    def _aba_servidores(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Cada servidor é uma impressora que as modalidades enxergam na rede. "
                             "Dá para ter um por aparelho ou por setor — marque a caixa para ligar "
                             "ou desligar."))
        self._enchendo = False
        self.t_serv = QTableWidget(0, len(COLUNAS_SERVIDOR))
        self.t_serv.setHorizontalHeaderLabels(COLUNAS_SERVIDOR)
        self.t_serv.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.t_serv.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.t_serv.verticalHeader().setVisible(False)
        self.t_serv.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.t_serv.doubleClicked.connect(lambda _i: self._editar_servidor())
        self.t_serv.itemChanged.connect(self._marcou_servidor)
        colunas_ajustaveis(self.t_serv)
        botoes = QHBoxLayout()
        for texto, fn in (("Adicionar…", self._novo_servidor), ("Editar…", self._editar_servidor),
                          ("Duplicar…", self._duplicar_servidor),
                          ("Excluir", self._excluir_servidor), ("Testar (C-ECHO)", self._testar_servidor)):
            b = QPushButton(texto)
            b.clicked.connect(fn)
            botoes.addWidget(b)
        botoes.addStretch(1)
        self.serv_status = QLabel("")
        lay.addWidget(self.t_serv, 1)
        lay.addLayout(botoes)
        lay.addWidget(self.serv_status)
        # 0.99.6: folhas que chegam em sessões separadas viram páginas de um trabalho
        from ipe.printing import juntar as JUN
        hj = QHBoxLayout()
        self.k_juntar = QCheckBox("Juntar como páginas as folhas da mesma origem que chegam em até")
        self.k_juntar.setChecked(JUN.ligado(self.settings))
        self.k_juntar.setToolTip("Muitas modalidades mandam uma folha por vez. Com isto, a folha que chega logo "
                                 "depois de outra, da mesma origem e do mesmo paciente (OCR), vira a página "
                                 "seguinte do mesmo trabalho. Pacientes diferentes nunca se juntam. O "
                                 "encaminhamento automático espera esse tempo sem folha nova antes de mandar.")
        self.s_juntar = QSpinBox(minimum=5, maximum=900, value=JUN.segundos(self.settings))
        self.s_juntar.setSuffix(" s uma da outra")
        hj.addWidget(self.k_juntar)
        hj.addWidget(self.s_juntar)
        hj.addStretch(1)
        lay.addLayout(hj)
        self._encher_servidores()
        return w

    def _situacao(self, srv: C.ServerConfig) -> str:
        """O que está acontecendo com este servidor agora (precisa do serviço de rede)."""
        if self.net is None:
            return "Ligado" if srv.enabled else "Desligado"
        vivo = next((s for s in self.net.print_servers if s.port == srv.port), None)
        if vivo is None:
            return "Desligado"
        if vivo.running:
            return "Recebendo"
        return vivo.error or "Desligado"

    def _encher_servidores(self) -> None:
        self._enchendo = True
        try:
            self.t_serv.setRowCount(len(self.servers))
            for r, s in enumerate(self.servers):
                marca = QTableWidgetItem()
                marca.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                marca.setCheckState(Qt.Checked if s.enabled else Qt.Unchecked)
                marca.setToolTip("Ligar ou desligar este servidor")
                self.t_serv.setItem(r, 0, marca)
                valores = [s.name, s.ae_title, str(s.port),
                           "qualquer AE" if s.accept == "any" else "só cadastrados",
                           s.auto_destination or "segurar na lista",
                           s.template or "como veio",
                           "sim" if s.to_database else "não",
                           self._situacao(s)]
                for c, v in enumerate(valores, start=1):
                    self.t_serv.setItem(r, c, QTableWidgetItem(v))
            self.t_serv.resizeColumnsToContents()
            self.t_serv.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        finally:
            self._enchendo = False

    def _marcou_servidor(self, item) -> None:
        """Clicou na caixa de ligar/desligar."""
        if self._enchendo or item.column() != 0:
            return
        i = item.row()
        if not 0 <= i < len(self.servers):
            return
        self.servers[i].enabled = item.checkState() == Qt.Checked
        self._encher_servidores()
        nome = self.servers[i].name
        self.serv_status.setText(f"“{nome}” ligado — vale quando você clicar em OK."
                                 if self.servers[i].enabled else
                                 f"“{nome}” desligado — vale quando você clicar em OK.")

    def _servidor_atual(self) -> int:
        i = self.t_serv.currentRow()
        return i if 0 <= i < len(self.servers) else -1

    def _novo_servidor(self) -> None:
        dlg = ServerEditor(None, self.settings, self.servers, self)
        if dlg.exec() == QDialog.Accepted:
            self.servers.append(dlg.server())
            self._encher_servidores()

    def _editar_servidor(self) -> None:
        i = self._servidor_atual()
        if i < 0:
            return
        outros = [s for k, s in enumerate(self.servers) if k != i]
        dlg = ServerEditor(self.servers[i], self.settings, outros, self)
        if dlg.exec() == QDialog.Accepted:
            self.servers[i] = dlg.server()
            self._encher_servidores()

    def _duplicar_servidor(self) -> None:
        """Cópia com nome e porta novos (dois servidores não dividem a porta); o resto igual."""
        i = self._servidor_atual()
        if i < 0:
            return
        import dataclasses
        copia = dataclasses.replace(self.servers[i],
                                    name=nome_de_copia(self.servers[i].name, [s.name for s in self.servers]),
                                    port=C.next_free_port(self.servers))
        dlg = ServerEditor(copia, self.settings, self.servers, self)
        dlg.setWindowTitle("Servidor de impressão (cópia)")
        if dlg.exec() == QDialog.Accepted:
            self.servers.insert(i + 1, dlg.server())
            self._encher_servidores()
            self.t_serv.selectRow(i + 1)

    def _excluir_servidor(self) -> None:
        i = self._servidor_atual()
        if i < 0:
            return
        if QMessageBox.question(self, "Servidores",
                                f"Excluir o servidor “{self.servers[i].name}”?") != QMessageBox.Yes:
            return
        del self.servers[i]
        self._encher_servidores()

    def _testar_servidor(self) -> None:
        """C-ECHO em si mesmo: confere se a porta está aberta e respondendo."""
        i = self._servidor_atual()
        if i < 0:
            return
        s = self.servers[i]
        aplicou = self._aplicar_servidores()
        self.serv_status.setText(f"Testando {s.ae_title} na porta {s.port}…")
        QApplication.processEvents()
        from pynetdicom import AE
        from pynetdicom.sop_class import Verification
        ae = AE(ae_title="TESTE")
        ae.acse_timeout = ae.dimse_timeout = ae.network_timeout = 5
        ae.add_requested_context(Verification)
        assoc = None
        try:
            assoc = ae.associate("127.0.0.1", int(s.port), ae_title=s.ae_title)
            if not assoc.is_established:
                raise OSError("sem resposta")
            resposta = assoc.send_c_echo()
            ok = resposta is not None and int(resposta.get("Status", 0xFFFF)) == 0
            self.serv_status.setText(f"“{s.name}” respondeu na porta {s.port}."
                                     + (" (servidores aplicados para o teste)" if aplicou else "") if ok else
                                     f"“{s.name}” conectou, mas não respondeu ao C-ECHO.")
        except Exception as e:  # noqa: BLE001
            situacao = self._situacao(s)
            extra = "" if s.enabled else " (o servidor está desligado: marque a caixa e teste de novo)"
            if s.enabled and situacao not in ("Recebendo", "Ligado"):
                extra = f" ({situacao})"
            self.serv_status.setText(f"Não respondeu na porta {s.port}: {e}{extra}")
        finally:
            if assoc is not None and assoc.is_established:
                assoc.release()

    def _aplicar_servidores(self) -> bool:
        """Bug relatado (27/10): servidor novo só respondia ao teste depois de salvar, fechar e abrir a
        janela — os servidores só ligavam no OK. Testar agora aplica a lista de servidores antes (grava
        só os servidores e religa as portas). Devolve True se precisou religar."""
        if self.net is None:
            return False
        vivos = {(getattr(v, "port", None), bool(getattr(v, "running", False))) for v in self.net.print_servers}
        querem = [x for x in self.servers if x.enabled]
        if C.all_servers(self.settings) == self.servers and all((x.port, True) in vivos for x in querem):
            return False
        C.save_servers(self.settings, self.servers)
        self.settings.save()
        self.net.start_print_servers()
        self._encher_servidores()
        return True

    # -------------------------------------------------------------- origens
    def _aba_origens(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel(
            "Cada aparelho que manda impressão aparece aqui sozinho, pelo AE, endereço e servidor "
            "que recebeu. Dê um nome e as regras podem apontar para ele. "
            "Enquanto uma origem não tiver nome, os trabalhos dela ficam esperando na lista."))
        self.t_orig = QTableWidget(0, len(COLUNAS_ORIGEM))
        self.t_orig.setHorizontalHeaderLabels(COLUNAS_ORIGEM)
        self.t_orig.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.t_orig.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.t_orig.verticalHeader().setVisible(False)
        self.t_orig.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.t_orig.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.t_orig.doubleClicked.connect(lambda _i: self._editar_origem())
        colunas_ajustaveis(self.t_orig)
        botoes = QHBoxLayout()
        for texto, fn in (("Cadastrar…", self._editar_origem),
                          ("Desligar/ligar", self._alternar_origem),
                          ("Esquecer", self._esquecer_origem)):
            b = QPushButton(texto)
            b.clicked.connect(fn)
            botoes.addWidget(b)
        botoes.addStretch(1)
        self.orig_status = QLabel("")
        self.orig_status.setWordWrap(True)
        lay.addWidget(self.t_orig, 1)
        lay.addLayout(botoes)
        lay.addWidget(self.orig_status)
        self._encher_origens()
        return w

    def _encher_origens(self) -> None:
        self.t_orig.setRowCount(len(self.origens))
        for i, o in enumerate(self.origens):
            valores = [o.name or "(sem nome — trabalhos parados)", o.calling_ae, o.modality or "",
                       ", ".join(o.hosts()), o.server or "—", str(o.jobs or 0),
                       _quando(o.last_seen)]
            for j, v in enumerate(valores):
                it = QTableWidgetItem(v)
                if not o.registered:
                    it.setForeground(QBrush(QColor(224, 192, 112)))
                elif not o.enabled:
                    it.setForeground(QBrush(QColor(150, 150, 150)))
                self.t_orig.setItem(i, j, it)
        pendentes = [o for o in self.origens if not o.registered]
        if pendentes:
            self.orig_status.setText(f"{len(pendentes)} origem(ns) sem cadastro: "
                                     "os trabalhos delas ficam esperando na lista de impressões.")
        else:
            self.orig_status.setText("Todas as origens vistas até agora estão cadastradas.")

    def _origem_atual(self) -> int:
        linha = self.t_orig.currentRow()
        return linha if 0 <= linha < len(self.origens) else -1

    def _editar_origem(self) -> None:
        i = self._origem_atual()
        if i < 0:
            QMessageBox.information(self, "Origem", "Escolha uma origem da lista.")
            return
        dlg = OriginEditor(self.origens[i], self.settings, self)
        if not dlg.exec():
            return
        if dlg.juntar_em:
            alvo = next((o for o in self.origens if o.id == dlg.juntar_em), None)
            if alvo is not None:
                for h in self.origens[i].hosts():
                    if h not in alvo.hosts():
                        alvo.also_hosts.append(h)
                alvo.jobs = int(alvo.jobs or 0) + int(self.origens[i].jobs or 0)
                del self.origens[i]
        else:
            self.origens[i] = dlg.origin()
        self._encher_origens()

    def _alternar_origem(self) -> None:
        i = self._origem_atual()
        if i < 0:
            return
        if not self.origens[i].registered:
            QMessageBox.information(self, "Origem", "Cadastre um nome antes de ligar a origem.")
            return
        self.origens[i].enabled = not self.origens[i].enabled
        self._encher_origens()

    def _esquecer_origem(self) -> None:
        i = self._origem_atual()
        if i < 0:
            return
        o = self.origens[i]
        usada = [r for r in self.rules
                 if r.origin == o.id or ((o.calling_ae or "").upper() in r.aes()
                                         and not [x for x in self.origens if x is not o
                                                  and (x.calling_ae or "").upper() == (o.calling_ae or "").upper()])]
        quem = o.name or o.calling_ae
        if usada:
            pergunta = (f"Tirar {quem} da lista? {len(usada)} regra(s) apontam para esta origem "
                        f"e vão parar de combinar. Se o aparelho mandar de novo, ela volta a "
                        f"aparecer sem nome.")
        else:
            pergunta = (f"Tirar {quem} da lista? Se o aparelho mandar de novo, ela volta a "
                        f"aparecer sem nome.")
        if QMessageBox.question(self, "Esquecer origem", pergunta) != QMessageBox.Yes:
            return
        del self.origens[i]
        self._encher_origens()

    # -------------------------------------------------------------- destinos
    def _aba_destinos(self) -> QWidget:
        w = _ListaCadastro("Para onde os trabalhos podem ir: PDF, impressora do computador, "
                           "impressora DICOM ou imagens numa pasta.")
        self.w_dest = w
        w.b_novo.clicked.connect(self._novo_destino)
        w.b_editar.clicked.connect(self._editar_destino)
        w.b_duplicar.clicked.connect(self._duplicar_destino)
        w.b_remover.clicked.connect(lambda: self._remover(self.dests, w, self._encher_destinos))
        self._encher_destinos()
        return w

    def _encher_destinos(self) -> None:
        self.w_dest.list.clear()
        for d in self.dests:
            self.w_dest.list.addItem(d.label())

    def _novo_destino(self) -> None:
        from ipe.ui.prints_tab import DestinationEditor
        dlg = DestinationEditor(None, self.settings, self)
        if dlg.exec() == QDialog.Accepted:
            self.dests.append(dlg.destination())
            self._encher_destinos()

    def _editar_destino(self) -> None:
        from ipe.ui.prints_tab import DestinationEditor
        i = self.w_dest.list.currentRow()
        if not 0 <= i < len(self.dests):
            return
        dlg = DestinationEditor(self.dests[i], self.settings, self)
        if dlg.exec() == QDialog.Accepted:
            self.dests[i] = dlg.destination()
            self._encher_destinos()

    def _duplicar_destino(self) -> None:
        from ipe.ui.prints_tab import DestinationEditor
        i = self.w_dest.list.currentRow()
        if not 0 <= i < len(self.dests):
            return
        import dataclasses
        copia = dataclasses.replace(self.dests[i], name=nome_de_copia(self.dests[i].name,
                                                                      [d.name for d in self.dests]))
        dlg = DestinationEditor(copia, self.settings, self)
        dlg.setWindowTitle("Destino da impressão (cópia)")
        if dlg.exec() == QDialog.Accepted:
            self.dests.insert(i + 1, dlg.destination())
            self._encher_destinos()
            self.w_dest.list.setCurrentRow(i + 1)

    # -------------------------------------------------------------- regras
    def _aba_regras(self) -> QWidget:
        w = _ListaCadastro("As regras são olhadas nesta ordem quando um trabalho chega (▲ ▼ mudam a "
                           "ordem). Cada regra escolhe a origem, o meu AE que recebeu e a modalidade. "
                           "Sem regra nenhuma, o trabalho fica esperando você na lista de impressões.", True,
                           colunas=COLUNAS_REGRA)
        self.w_regra = w
        w.b_novo.clicked.connect(self._nova_regra)
        w.b_editar.clicked.connect(self._editar_regra)
        w.b_duplicar.clicked.connect(self._duplicar_regra)
        w.b_remover.clicked.connect(lambda: self._remover(self.rules, w, self._encher_regras))
        w.b_sobe.clicked.connect(lambda: self._mover(-1))
        w.b_desce.clicked.connect(lambda: self._mover(1))
        w.list.itemChanged.connect(self._marcou_regra)
        from ipe.printing import arrival
        self.ocr_chegada = QCheckBox("Identificar o paciente pelo OCR quando o filme chegar "
                                     "(sem identificar, o filme espera você confirmar)")
        self.ocr_chegada.setChecked(arrival.ligado(self.settings))
        self.ocr_chegada.setToolTip("O cabeçalho da folha é lido e comparado com os pacientes do "
                                    "banco. Achando o paciente, o filme segue pela regra; senão, "
                                    "fica parado até você usar Identificar paciente.")
        w.layout().insertWidget(1, self.ocr_chegada)
        self._encher_regras()
        return w

    def _encher_regras(self) -> None:
        t = self.w_regra.list
        self._enchendo_regras = True
        try:
            t.setRowCount(len(self.rules))
            for i, r in enumerate(self.rules):
                marca = QTableWidgetItem()
                marca.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                marca.setCheckState(Qt.Checked if r.enabled else Qt.Unchecked)
                marca.setToolTip("Ligar ou desligar esta regra")
                t.setItem(i, 0, marca)
                outras = R.Rule(name="", origin=r.origin, calling_ae=r.calling_ae, label=r.label,
                                film_size=r.film_size, min_sheets=r.min_sheets, max_sheets=r.max_sheets,
                                hour_from=r.hour_from, hour_to=r.hour_to).label_text()
                outras = outras.split(": ", 1)[1].rsplit(" → ", 1)[0]
                aes_meus = {x.name: x.ae_title for x in self.servers}
                recebido = ", ".join(f"{aes_meus[n]} ({n})" if n in aes_meus else n for n in r.servidores())
                valores = [r.name, ", ".join(r.aes()) or "qualquer", recebido or "qualquer",
                           ", ".join(r.modalidades()) or "qualquer",
                           "" if outras == "qualquer trabalho" else outras,
                           r.destination or "(sem destino)", r.template or "", "sim" if r.stop else "não"]
                for j, v in enumerate(valores, start=1):
                    it = QTableWidgetItem(v)
                    if not r.enabled:
                        it.setForeground(QBrush(QColor(150, 150, 150)))
                    t.setItem(i, j, it)
            t.resizeColumnsToContents()
            colunas_ajustaveis(t, estica_ultima=False)
            t.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)   # outras condições
        finally:
            self._enchendo_regras = False

    def _marcou_regra(self, item) -> None:
        if getattr(self, "_enchendo_regras", False) or item.column() != 0:
            return
        i = item.row()
        if 0 <= i < len(self.rules):
            self.rules[i].enabled = item.checkState() == Qt.Checked
            self._encher_regras()
            self.w_regra.list.setCurrentRow(i)

    def _nova_regra(self) -> None:
        dlg = RuleEditor(None, self.settings, self)
        if dlg.exec() == QDialog.Accepted:
            self.rules.append(dlg.rule())
            self._encher_regras()

    def _editar_regra(self) -> None:
        i = self.w_regra.list.currentRow()
        if not 0 <= i < len(self.rules):
            return
        dlg = RuleEditor(self.rules[i], self.settings, self)
        if dlg.exec() == QDialog.Accepted:
            self.rules[i] = dlg.rule()
            self._encher_regras()

    def _duplicar_regra(self) -> None:
        """A cópia entra logo abaixo da original: a ordem das regras importa."""
        i = self.w_regra.list.currentRow()
        if not 0 <= i < len(self.rules):
            return
        import dataclasses
        copia = dataclasses.replace(self.rules[i], name=nome_de_copia(self.rules[i].name,
                                                                      [r.name for r in self.rules]))
        dlg = RuleEditor(copia, self.settings, self)
        dlg.setWindowTitle("Regra (cópia)")
        if dlg.exec() == QDialog.Accepted:
            self.rules.insert(i + 1, dlg.rule())
            self._encher_regras()
            self.w_regra.list.setCurrentRow(i + 1)

    def _mover(self, passo: int) -> None:
        i = self.w_regra.list.currentRow()
        j = i + passo
        if not (0 <= i < len(self.rules) and 0 <= j < len(self.rules)):
            return
        self.rules[i], self.rules[j] = self.rules[j], self.rules[i]
        self._encher_regras()
        self.w_regra.list.setCurrentRow(j)

    # -------------------------------------------------------------- modelos
    def _aba_modelos(self) -> QWidget:
        w = _ListaCadastro("O desenho da folha: logo, nome da clínica, cabeçalho e rodapé. "
                           "Vale para o que chega das modalidades e para os filmes montados aqui.")
        self.w_modelo = w
        w.b_novo.clicked.connect(self._novo_modelo)
        w.b_editar.clicked.connect(self._editar_modelo)
        w.b_duplicar.clicked.connect(self._duplicar_modelo)
        w.b_remover.clicked.connect(lambda: self._remover(self.templates, w, self._encher_modelos))
        self._encher_modelos()
        return w

    def _encher_modelos(self) -> None:
        self.w_modelo.list.clear()
        for m in self.templates:
            self.w_modelo.list.addItem(m.label())

    def _novo_modelo(self) -> None:
        dlg = TemplateEditor(None, self)
        if dlg.exec() == QDialog.Accepted:
            self.templates.append(dlg.template())
            self._encher_modelos()

    def _editar_modelo(self) -> None:
        i = self.w_modelo.list.currentRow()
        if not 0 <= i < len(self.templates):
            return
        dlg = TemplateEditor(self.templates[i], self)
        if dlg.exec() == QDialog.Accepted:
            self.templates[i] = dlg.template()
            self._encher_modelos()

    def _duplicar_modelo(self) -> None:
        i = self.w_modelo.list.currentRow()
        if not 0 <= i < len(self.templates):
            return
        import dataclasses
        copia = dataclasses.replace(self.templates[i], name=nome_de_copia(self.templates[i].name,
                                                                          [m.name for m in self.templates]))
        dlg = TemplateEditor(copia, self)
        dlg.setWindowTitle(f"{dlg.windowTitle()} (cópia)")
        if dlg.exec() == QDialog.Accepted:
            self.templates.insert(i + 1, dlg.template())
            self._encher_modelos()
            self.w_modelo.list.setCurrentRow(i + 1)

    # -------------------------------------------------------------- automático
    def _aba_automatico(self) -> QWidget:
        """Filme automático por regras (0.86): exame que chega pela rede (o ultrassom manda as imagens,
        não o filme pronto) e imagens comuns mandadas à porta de uma impressora."""
        self.auto_rules = AF.all_rules(self.settings)
        w = _ListaCadastro("Quando uma modalidade manda <b>as imagens</b> (e não o filme pronto), o programa "
                           "monta o filme sozinho alguns segundos depois de o exame parar de chegar. Cada "
                           "regra escolhe a origem, o meu AE que foi chamado e a modalidade, e diz como "
                           "montar. A primeira regra ligada que combinar vale (▲ ▼ mudam a ordem); sem "
                           "nenhuma, nada é montado.", True, colunas=COLUNAS_AUTO)
        self.w_auto = w
        w.b_novo.clicked.connect(self._nova_auto)
        w.b_editar.clicked.connect(self._editar_auto)
        w.b_duplicar.clicked.connect(self._duplicar_auto)
        w.b_remover.clicked.connect(lambda: self._remover(self.auto_rules, w, self._encher_auto))
        w.b_sobe.clicked.connect(lambda: self._mover_auto(-1))
        w.b_desce.clicked.connect(lambda: self._mover_auto(1))
        w.list.itemChanged.connect(self._marcou_auto)
        # grade padrão das imagens à porta da impressora que não caem em regra nenhuma
        padrao = AF.config(self.settings)
        self.af_rows = QSpinBox(minimum=1, maximum=8, value=int(padrao.rows))
        self.af_cols = QSpinBox(minimum=1, maximum=8, value=int(padrao.cols))
        self.af_paper = QComboBox()
        from ipe.printing.film import PAPERS
        for nome in PAPERS:
            self.af_paper.addItem(nome, nome)
        self.af_paper.setCurrentIndex(max(0, self.af_paper.findData(padrao.paper)))
        linha = QHBoxLayout()
        linha.addWidget(QLabel("Imagens mandadas à porta de uma impressora, sem regra que combine: grade"))
        linha.addWidget(self.af_rows)
        linha.addWidget(QLabel("×"))
        linha.addWidget(self.af_cols)
        linha.addWidget(QLabel("papel"))
        linha.addWidget(self.af_paper)
        linha.addWidget(QLabel("(e seguem as regras de impressão daquele servidor)"))
        linha.addStretch(1)
        w.layout().addLayout(linha)
        self._encher_auto()
        return w

    def _encher_auto(self) -> None:
        t = self.w_auto.list
        self._enchendo_auto = True
        try:
            t.setRowCount(len(self.auto_rules))
            for i, r in enumerate(self.auto_rules):
                marca = QTableWidgetItem()
                marca.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                marca.setCheckState(Qt.Checked if r.enabled else Qt.Unchecked)
                marca.setToolTip("Ligar ou desligar esta regra")
                t.setItem(i, 0, marca)
                valores = [r.name, ", ".join(r.calling_aes) or "qualquer", ", ".join(r.my_aes) or "qualquer",
                           ", ".join(r.modalities) or "qualquer",
                           f"descrição com {r.description}" if r.description else "",
                           f"{r.rows}×{r.cols} {r.paper}", str(r.max_images) if r.max_images else "todas",
                           r.destination or "fica na lista", r.template or ""]
                for j, v in enumerate(valores, start=1):
                    it = QTableWidgetItem(v)
                    if not r.enabled:
                        it.setForeground(QBrush(QColor(150, 150, 150)))
                    t.setItem(i, j, it)
            t.resizeColumnsToContents()
            colunas_ajustaveis(t, estica_ultima=False)
            t.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        finally:
            self._enchendo_auto = False

    def _marcou_auto(self, item) -> None:
        if getattr(self, "_enchendo_auto", False) or item.column() != 0:
            return
        i = item.row()
        if 0 <= i < len(self.auto_rules):
            self.auto_rules[i].enabled = item.checkState() == Qt.Checked
            self._encher_auto()
            self.w_auto.list.setCurrentRow(i)

    def _editor_auto(self, regra):
        return AutoRuleEditor(regra, self.settings, self, repo=self.repo, net=self.net)

    def _nova_auto(self) -> None:
        dlg = self._editor_auto(None)
        if dlg.exec() == QDialog.Accepted:
            self.auto_rules.append(dlg.regra())
            self._encher_auto()
            self.w_auto.list.setCurrentRow(len(self.auto_rules) - 1)

    def _editar_auto(self) -> None:
        i = self.w_auto.list.currentRow()
        if not 0 <= i < len(self.auto_rules):
            return
        dlg = self._editor_auto(self.auto_rules[i])
        if dlg.exec() == QDialog.Accepted:
            self.auto_rules[i] = dlg.regra()
            self._encher_auto()
            self.w_auto.list.setCurrentRow(i)

    def _duplicar_auto(self) -> None:
        i = self.w_auto.list.currentRow()
        if not 0 <= i < len(self.auto_rules):
            return
        import dataclasses
        copia = dataclasses.replace(self.auto_rules[i], name=nome_de_copia(
            self.auto_rules[i].name, [r.name for r in self.auto_rules]))
        dlg = self._editor_auto(copia)
        dlg.setWindowTitle("Regra do filme automático (cópia)")
        if dlg.exec() == QDialog.Accepted:
            self.auto_rules.insert(i + 1, dlg.regra())
            self._encher_auto()
            self.w_auto.list.setCurrentRow(i + 1)

    def _mover_auto(self, passo: int) -> None:
        i = self.w_auto.list.currentRow()
        j = i + passo
        if not (0 <= i < len(self.auto_rules) and 0 <= j < len(self.auto_rules)):
            return
        self.auto_rules[i], self.auto_rules[j] = self.auto_rules[j], self.auto_rules[i]
        self._encher_auto()
        self.w_auto.list.setCurrentRow(j)

    # -------------------------------------------------------------- limpeza (0.84)
    def _aba_limpeza(self) -> QWidget:
        from ipe.printing import limpeza as LZ
        cfg = LZ.config(self.settings)
        w = QWidget()
        lay = QVBoxLayout(w)
        expl = QLabel("Apaga sozinho os <b>trabalhos recebidos</b> das modalidades (a pasta com as folhas "
                      "e a linha da lista) que atendem a <b>todos</b> os critérios marcados. Roda ao abrir "
                      "o programa e de hora em hora. Não apaga filme montado no compositor, filme que veio "
                      "no exame nem o exame criado no banco com as folhas.")
        expl.setWordWrap(True)
        lay.addWidget(expl)
        f = QFormLayout()
        self.lz_on = QCheckBox("Limpar automaticamente")
        self.lz_on.setChecked(cfg.ligada)
        self.lz_dias = QSpinBox(minimum=0, maximum=3650, value=int(cfg.dias), suffix=" dia(s)")
        self.lz_dias.setToolTip("Conta a partir da chegada. 0 = qualquer idade.")
        self.lz_imp = QCheckBox("Só os que já foram impressos (enviados)")
        self.lz_imp.setChecked(cfg.so_impressos)
        self.lz_mod = QLineEdit(cfg.modalidades, placeholderText="Ex.: MG ou MG|US (vazio = qualquer)")
        self.lz_mod.setToolTip("Modalidade do trabalho (do exame do paciente ou da origem cadastrada). "
                               "Com modalidade preenchida, trabalho de modalidade desconhecida não é apagado.")
        self.lz_orig = QListWidget()
        self.lz_orig.setMaximumHeight(130)
        for o in self.origens:
            from PySide6.QtWidgets import QListWidgetItem
            it = QListWidgetItem(o.label())
            it.setData(Qt.UserRole, o.id)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if o.id in cfg.origens else Qt.Unchecked)
            self.lz_orig.addItem(it)
        f.addRow(self.lz_on)
        f.addRow("Mais velhos que:", self.lz_dias)
        f.addRow(self.lz_imp)
        f.addRow("Modalidade:", self.lz_mod)
        f.addRow("Só destas origens\n(nenhuma marcada = todas):", self.lz_orig)
        lay.addLayout(f)
        self.lz_aviso = QLabel("")
        self.lz_aviso.setWordWrap(True)
        self.lz_aviso.setStyleSheet("color:#e0c070;")
        lay.addWidget(self.lz_aviso)
        linha = QHBoxLayout()
        self.lz_conta = QLabel("")
        b_ver = QPushButton("Quantos sairiam?")
        b_ver.clicked.connect(self._lz_contar)
        b_agora = QPushButton("Limpar agora…")
        b_agora.clicked.connect(self._lz_limpar_agora)
        for b in (b_ver, b_agora):
            b.setEnabled(self.repo is not None)
        linha.addWidget(b_ver)
        linha.addWidget(b_agora)
        linha.addWidget(self.lz_conta, 1)
        lay.addLayout(linha)
        lay.addStretch(1)
        self.lz_imp.toggled.connect(self._lz_avisar)
        self._lz_avisar()
        return w

    def _lz_avisar(self, *_a) -> None:
        self.lz_aviso.setText("" if self.lz_imp.isChecked() else
                              "Atenção: sem “só os impressos”, filme que nunca saiu também é apagado "
                              "quando passar da idade.")

    def lz_config(self):
        from ipe.printing import limpeza as LZ
        origens = [self.lz_orig.item(i).data(Qt.UserRole) for i in range(self.lz_orig.count())
                   if self.lz_orig.item(i).checkState() == Qt.Checked]
        return LZ.Config(ligada=self.lz_on.isChecked(), dias=self.lz_dias.value(),
                         so_impressos=self.lz_imp.isChecked(),
                         modalidades=self.lz_mod.text().strip().upper(), origens=origens)

    def _lz_contar(self) -> int:
        from ipe.printing import limpeza as LZ
        if self.repo is None:
            return 0
        n = len(LZ.candidatos(self.repo, self.settings, self.lz_config()))
        self.lz_conta.setText(f"Com estes critérios, {n} trabalho(s) seriam apagados agora.")
        return n

    def _lz_limpar_agora(self, confirmar: bool = True) -> int:
        from ipe.printing import limpeza as LZ
        if self.repo is None:
            return 0
        n = len(LZ.candidatos(self.repo, self.settings, self.lz_config()))
        if not n:
            self.lz_conta.setText("Nada a apagar com estes critérios.")
            return 0
        if confirmar and QMessageBox.question(
                self, "Limpeza", f"Apagar agora {n} trabalho(s) recebido(s) da lista de impressões?\n"
                                 "As pastas com as folhas são apagadas; os exames no banco ficam.") != QMessageBox.Yes:
            return 0
        feitos = LZ.limpar(self.repo, self.settings, self.lz_config())
        self.lz_conta.setText(f"Apagados: {feitos} trabalho(s).")
        return feitos

    # -------------------------------------------------------------- comum
    @staticmethod
    def _remover(lista: list, w: _ListaCadastro, encher) -> None:
        i = w.list.currentRow()
        if 0 <= i < len(lista):
            del lista[i]
            encher()

    def _salvar(self) -> None:
        C.save_servers(self.settings, self.servers)
        from ipe.printing import juntar as JUN
        self.settings.set(JUN.CHAVE, self.k_juntar.isChecked())
        self.settings.set(JUN.CHAVE_SEGUNDOS, self.s_juntar.value())
        D.save_destinations(self.settings, self.dests)
        R.save_rules(self.settings, self.rules)
        O.save_origins(self.settings, self.origens)
        L.save_templates(self.settings, self.templates)
        from ipe.printing import arrival
        from ipe.printing import limpeza as LZ
        self.settings.set(arrival.CHAVE, self.ocr_chegada.isChecked())
        self.settings.set(LZ.CHAVE, self.lz_config().to_dict())
        AF.save_rules(self.settings, self.auto_rules)
        antiga = AF.config(self.settings)           # a grade padrão continua morando na chave antiga
        antiga.enabled = False                      # quem monta agora são as regras
        antiga.rows, antiga.cols = self.af_rows.value(), self.af_cols.value()
        antiga.paper = self.af_paper.currentData() or "A4"
        AF.save(self.settings, antiga)
        self.settings.save()
        if self.net is not None:
            self.net.start_print_servers()
        self.accept()
