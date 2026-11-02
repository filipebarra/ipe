"""Ajustar a numeração da coluna e a vértebra de transição (0.99.23).

Pedido dele: *"a maior mudança que quero é com relação às vértebras de transição. Como vamos lidar com
elas?"* — e as escolhas: nomes **lombarizada / sacralizada**, contagem **pela C2 e pela última
costela**, Castellvi como **sugestão** que ele confirma.

A janela abre com a vértebra que estava sob o botão direito. Três coisas se decidem aqui:

- **qual vértebra é qual** ("esta é a L5"): a contagem inteira anda junto;
- a **transição lombossacral**: nenhuma, L5 sacralizada (parcial), L5 sacralizada fundida ao sacro ou
  S1 lombarizada — renumera para ficar coerente (lombarizada põe a última livre como S1, e o sacro
  vira S2);
- o **Castellvi**, que vem com a sugestão da IA e o motivo.

"Aplicar" grava no SEG do exame e guarda a conferência (o próximo exame do paciente avisa se a
numeração sair diferente). A frase do laudo se refaz a cada mudança.
"""
from __future__ import annotations

import copy

from PySide6.QtCore import Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from ipe.ai import coluna as COL

OPCOES_LS = [
    (None, "Automático (pelos nomes)"),
    ("", "Nenhuma"),
    ("sacralizada", "L5 sacralizada (parcial)"),
    ("fundida", "L5 sacralizada, fundida ao sacro"),
    ("lombarizada", "S1 lombarizada"),
]
LADOS = ("à direita", "à esquerda")


class NumeracaoDialog(QDialog):
    aplicado = Signal()
    laudo = Signal(str)

    def __init__(self, parent, obj, clicada: str | None = None, repo=None, study_uid: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Numeração da coluna")
        self.setMinimumWidth(520)
        self.obj, self.repo, self.study_uid = obj, repo, study_uid
        lay = QVBoxLayout(self)
        self.l_estado = QLabel()
        self.l_estado.setWordWrap(True)
        lay.addWidget(self.l_estado)
        form = QFormLayout()
        linha = QHBoxLayout()
        self.c_vert = QComboBox()
        self.c_alvo = QComboBox()
        self.c_alvo.addItems(COL.ORDEM)
        linha.addWidget(self.c_vert, 1)
        linha.addWidget(QLabel("é a"))
        linha.addWidget(self.c_alvo, 1)
        form.addRow("Esta vértebra", linha)
        self.c_ls = QComboBox()
        for _v, t in OPCOES_LS:
            self.c_ls.addItem(t)
        form.addRow("Transição lombossacral", self.c_ls)
        linha2 = QHBoxLayout()
        self.c_cast = QComboBox()
        self.c_cast.addItems(["—"] + list(COL.CASTELLVI[1:]))
        self.c_lado = QComboBox()
        self.c_lado.addItems(LADOS)
        linha2.addWidget(self.c_cast, 1)
        linha2.addWidget(self.c_lado, 1)
        form.addRow("Castellvi", linha2)
        self.l_sugestao = QLabel()
        self.l_sugestao.setWordWrap(True)
        form.addRow("", self.l_sugestao)
        lay.addLayout(form)
        lay.addWidget(QLabel("Frase para o laudo:"))
        self.t_frase = QPlainTextEdit()
        self.t_frase.setReadOnly(True)
        self.t_frase.setMaximumHeight(90)
        lay.addWidget(self.t_frase)
        bot = QHBoxLayout()
        self.b_aplicar = QPushButton("Aplicar")
        self.b_copiar = QPushButton("Copiar a frase")
        self.b_laudo = QPushButton("Mandar para o laudo")
        self.b_fechar = QPushButton("Fechar")
        for b in (self.b_aplicar, self.b_copiar, self.b_laudo):
            bot.addWidget(b)
        bot.addStretch(1)
        bot.addWidget(self.b_fechar)
        lay.addLayout(bot)
        self.b_aplicar.clicked.connect(self.aplicar)
        self.b_copiar.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.frase()))
        self.b_laudo.clicked.connect(lambda: self.laudo.emit(self.frase()))
        self.b_fechar.clicked.connect(self.close)
        for c in (self.c_vert, self.c_alvo, self.c_ls, self.c_cast, self.c_lado):
            c.currentIndexChanged.connect(self._previa)
        self.c_vert.currentIndexChanged.connect(self._alvo_igual)
        self._carregar(clicada)

    # ------------------------------------------------------------ estado
    def _vertebras(self) -> list[str]:
        return [COL.nivel_de(v) for v in COL._vertebras(self.obj.volumes) if not getattr(v, "sacro", False)]

    def _carregar(self, clicada: str | None = None) -> None:
        num = self.obj.numeracao
        for c in (self.c_vert, self.c_alvo, self.c_ls, self.c_cast, self.c_lado):
            c.blockSignals(True)
        self.c_vert.clear()
        vs = self._vertebras()
        self.c_vert.addItems(vs)
        alvo = clicada if clicada in vs else (vs[-1] if vs else "")
        if alvo:
            self.c_vert.setCurrentText(alvo)
            self.c_alvo.setCurrentText(alvo)
        tem_sacro = COL.tem_sacro(self.obj)
        self.c_ls.setEnabled(tem_sacro)
        self.c_ls.setToolTip("" if tem_sacro else "A série não pega o sacro.")
        med = num.lombossacral_medico
        i = next((k for k, (v, _t) in enumerate(OPCOES_LS)
                  if (v == (med if med != "nenhuma" else "") and med)), 0)
        self.c_ls.setCurrentIndex(i)
        self.c_cast.setCurrentText(num.castellvi or "—")
        if num.castellvi_lado in LADOS:
            self.c_lado.setCurrentText(num.castellvi_lado)
        for c in (self.c_vert, self.c_alvo, self.c_ls, self.c_cast, self.c_lado):
            c.blockSignals(False)
        self._mostrar_estado()
        self._previa()

    def _mostrar_estado(self) -> None:
        num = self.obj.numeracao
        linhas = [f"<b>Numeração:</b> {COL.ANCORAS.get(num.ancora) or 'de um SEG antigo (sem registro da âncora)'}."]
        linhas.append(f"<b>Agora:</b> {COL.descrever(num)}.")
        for e in num.evidencias:
            linhas.append(f"• {e}")
        if num.aviso_anterior:
            linhas.append(f"<span style='color:#c03030'>⚠ {num.aviso_anterior}</span>")
        else:
            ant = COL.anterior_confirmada(self.repo, self.study_uid)
            if ant is not None:
                linhas.append(f"Exame anterior ({COL._data_br(ant['data'])}): {COL.descrever(ant['numeracao'])}.")
        if num.confirmado_por or num.confirmado_em:
            linhas.append(f"Conferida por {num.confirmado_por or '—'} em {num.confirmado_em or '—'}.")
        self.l_estado.setText("<br>".join(linhas))
        if num.castellvi_fonte == "sugestão" and num.castellvi:
            self.l_sugestao.setText(f"Sugestão da IA: {num.castellvi} {num.castellvi_lado} — {num.castellvi_motivo}.")
        else:
            self.l_sugestao.setText(num.castellvi_motivo or "")

    def _alvo_igual(self) -> None:
        self.c_alvo.blockSignals(True)
        self.c_alvo.setCurrentText(self.c_vert.currentText())
        self.c_alvo.blockSignals(False)
        self._previa()

    def escolhas(self) -> dict:
        de, para = self.c_vert.currentText(), self.c_alvo.currentText()
        passo = COL.POS[para] - COL.POS[de] if de in COL.POS and para in COL.POS else 0
        ls = OPCOES_LS[self.c_ls.currentIndex()][0] if self.c_ls.isEnabled() else None
        cast = self.c_cast.currentText()
        cast = "" if cast == "—" else cast
        return {"passo": passo, "lombossacral": ls, "castellvi": cast,
                "castellvi_lado": self.c_lado.currentText() if cast.endswith("a") else ""}

    def _simular(self):
        o = copy.copy(self.obj)
        o.volumes = [copy.copy(mv) for mv in self.obj.volumes]
        for mv in o.volumes:
            mv._cache = {}
        o.numeracao = copy.deepcopy(self.obj.numeracao)
        o.findings = list(self.obj.findings or [])
        e = self.escolhas()
        COL.ajustar(o, passo=e["passo"], lombossacral=e["lombossacral"], castellvi=e["castellvi"],
                    castellvi_lado=e["castellvi_lado"])
        return o

    def frase(self) -> str:
        try:
            return COL.frase_do_laudo(self._simular().numeracao)
        except COL.ForaDaColuna as e:
            return f"(não dá: {e})"

    def _previa(self, *_a) -> None:
        self.c_lado.setEnabled(self.c_cast.currentText().endswith("a"))
        self.t_frase.setPlainText(self.frase())

    # ------------------------------------------------------------ aplicar
    def aplicar(self) -> bool:
        e = self.escolhas()
        from ipe.auth import session as S
        try:
            quem = S.get().username or ""
        except Exception:  # noqa: BLE001
            quem = ""
        try:
            COL.ajustar(self.obj, passo=e["passo"], lombossacral=e["lombossacral"], castellvi=e["castellvi"],
                        castellvi_lado=e["castellvi_lado"], quem=quem)
        except COL.ForaDaColuna as err:
            self.l_sugestao.setText(f"Não deu: {err}.")
            return False
        self._carregar(self.c_alvo.currentText())
        self.aplicado.emit()
        return True
