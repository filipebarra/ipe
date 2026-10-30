"""O menu de "onde esta análise roda".

A lista de valores de cada campo vem do **acervo do usuário**, não de uma lista que eu inventei:
descrição de série, aparelho e parte do corpo mudam de serviço para serviço, e é isso que torna a
regra utilizável em vez de teórica.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ipe.core import selecao as S
from ipe.core.i18n import tr
from ipe.ui.tabelas import colunas_ajustaveis

#: nome bonito de cada análise
ANALISES = {"densidade": "Densidade mamária"}


class EditorSelecao(QDialog):
    """Uma regra: nome + critérios ligados por E, com prévia no acervo."""

    def __init__(self, regra: S.Selecao, repo=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Regra de seleção"))
        self.regra = S.Selecao.from_dict(regra.to_dict())     # cópia: cancelar não estraga nada
        self.repo = repo
        self._valores: dict[str, list] = {}
        self.resize(760, 460)

        v = QVBoxLayout(self)
        linha = QHBoxLayout()
        linha.addWidget(QLabel(tr("Nome")))
        self.nome = QLineEdit(self.regra.nome)
        linha.addWidget(self.nome, 1)
        v.addLayout(linha)

        self.tabela = QTableWidget(0, 4)
        self.tabela.setHorizontalHeaderLabels([tr("E / OU"), tr("Campo"), tr("Comparação"),
                                               tr("Valor")])
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        cab = self.tabela.horizontalHeader()
        for c in (0, 1, 2):
            cab.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        cab.setSectionResizeMode(3, QHeaderView.Stretch)
        v.addWidget(self.tabela, 1)
        colunas_ajustaveis(self.tabela)

        botoes = QHBoxLayout()
        for texto, fn in ((tr("Acrescentar critério"), self.acrescentar),
                          (tr("Remover critério"), self.remover)):
            b = QPushButton(texto)
            b.clicked.connect(fn)
            botoes.addWidget(b)
        botoes.addStretch(1)
        v.addLayout(botoes)

        self.previa = QLabel()
        self.previa.setWordWrap(True)
        v.addWidget(self.previa)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.aceitar)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

        for c in self.regra.criterios:
            self._linha(c)
        if not self.regra.criterios:
            self.acrescentar()
        self.atualiza_previa()

    # ------------------------------------------------------------------ linhas
    def valores(self, campo: str) -> list:
        """O que existe no acervo para este campo (com a contagem), em cache."""
        if campo not in self._valores:
            try:
                self._valores[campo] = self.repo.valores_do_acervo(campo) if self.repo else []
            except Exception:  # noqa: BLE001 - sem acervo a regra ainda se escreve à mão
                self._valores[campo] = []
        return self._valores[campo]

    def _linha(self, criterio: S.Criterio) -> None:
        i = self.tabela.rowCount()
        self.tabela.insertRow(i)

        ligacao = QComboBox()
        for chave, rotulo in S.LIGACOES.items():
            ligacao.addItem(tr(rotulo), chave)
        ligacao.setCurrentIndex(1 if criterio.ligacao == "ou" else 0)
        ligacao.setEnabled(i > 0)            # a primeira linha não se liga a nada
        ligacao.setToolTip(tr("O E amarra mais forte que o OU: “A e B ou C” é “(A e B) ou C”."))

        campo = QComboBox()
        for chave, rotulo in S.CAMPOS.items():
            campo.addItem(tr(rotulo), chave)
        campo.setCurrentIndex(max(0, list(S.CAMPOS).index(criterio.campo)
                                  if criterio.campo in S.CAMPOS else 0))

        operador = QComboBox()
        for chave, rotulo in S.OPERADORES.items():
            operador.addItem(tr(rotulo), chave)
        operador.setCurrentIndex(max(0, list(S.OPERADORES).index(criterio.operador)
                                     if criterio.operador in S.OPERADORES else 0))

        valor = QComboBox()
        valor.setEditable(True)
        valor.setCurrentText(criterio.valor)

        self.tabela.setCellWidget(i, 0, ligacao)
        self.tabela.setCellWidget(i, 1, campo)
        self.tabela.setCellWidget(i, 2, operador)
        self.tabela.setCellWidget(i, 3, valor)
        ligacao.currentIndexChanged.connect(self.atualiza_previa)
        campo.currentIndexChanged.connect(lambda _x, r=i: self.sugerir(r))
        for w, sinal in ((campo, "currentIndexChanged"), (operador, "currentIndexChanged")):
            getattr(w, sinal).connect(self.atualiza_previa)
        valor.editTextChanged.connect(self.atualiza_previa)
        self.sugerir(i)

    def sugerir(self, linha: int) -> None:
        """Preenche o combo de valor com o que o acervo tem para o campo escolhido."""
        campo = self.tabela.cellWidget(linha, 1)
        valor = self.tabela.cellWidget(linha, 3)
        if campo is None or valor is None:
            return
        atual = valor.currentText()
        valor.blockSignals(True)
        valor.clear()
        for v, n in self.valores(campo.currentData())[:200]:
            valor.addItem(f"{v}", v)
            valor.setItemData(valor.count() - 1, tr("{} série(s) no acervo").format(n),
                              Qt.ToolTipRole)
        valor.setCurrentText(atual)
        valor.blockSignals(False)

    def acrescentar(self) -> None:
        self._linha(S.Criterio())
        self.atualiza_previa()

    def remover(self) -> None:
        i = self.tabela.currentRow()
        if i >= 0:
            self.tabela.removeRow(i)
            primeira = self.tabela.cellWidget(0, 0)
            if primeira is not None:         # quem virou primeira não se liga a nada
                primeira.setEnabled(False)
            self.atualiza_previa()

    # ------------------------------------------------------------------ prévia
    def atual(self) -> S.Selecao:
        criterios = []
        for i in range(self.tabela.rowCount()):
            ligacao = self.tabela.cellWidget(i, 0)
            campo = self.tabela.cellWidget(i, 1)
            operador = self.tabela.cellWidget(i, 2)
            valor = self.tabela.cellWidget(i, 3)
            if campo is None or operador is None or valor is None:
                continue
            criterios.append(S.Criterio(campo.currentData(), operador.currentData(),
                                        valor.currentText().strip(),
                                        "e" if i == 0 or ligacao is None else ligacao.currentData()))
        return S.Selecao(nome=self.nome.text().strip() or tr("Sem nome"),
                         ativa=self.regra.ativa, criterios=criterios)

    def atualiza_previa(self) -> None:
        """Conta no acervo **por grupo de E**, e diz que modalidades cada grupo pega.

        Um número só esconde o problema clássico: o `OU` começa um grupo novo, e grupo que não
        limita modalidade pega o acervo inteiro. Aconteceu de verdade — "descrição contém PROC"
        pegava `Processed Images` de TC e de RM. Quebrado por grupo, isso salta aos olhos.
        """
        regra = self.atual()
        if not regra.criterios:
            self.previa.setText(tr("Sem critério nenhum a regra não pega imagem alguma."))
            self.previa.setStyleSheet("")
            return
        if self.repo is None:
            self.previa.setText(regra.texto(tr))
            return
        try:
            series = self.repo.series_para_analise()
        except Exception:  # noqa: BLE001
            series = []
        grupos = S.grupos(regra.criterios)
        linhas, alerta = [], False
        for n, grupo in enumerate(grupos, 1):
            g = S.Selecao(criterios=list(grupo))
            pegas = [s for s in series if g.parcial(s)]
            mods = sorted({s["modalidade"] for s in pegas if s["modalidade"]})
            rotulo = tr("Grupo {}").format(n) if len(grupos) > 1 else tr("A regra")
            linhas.append(tr("{}: {} série(s) de {} exame(s) — {}").format(
                rotulo, len(pegas), len({s["study_uid"] for s in pegas}),
                ", ".join(mods) or tr("nenhuma")))
            if len(mods) > 1 and not any(c.campo in ("modalidade", "classe") for c in grupo):
                alerta = True
        if len(grupos) > 1:
            linhas.insert(0, tr("São {} grupos ligados por OU: basta um deles pegar.").format(
                len(grupos)))
        falta = regra.faltando(series[0]) if series else regra.faltando({})
        if falta:
            linhas.append(tr("Falta conferir {} — isso só dá para saber abrindo cada imagem, então os números são o limite de cima.").format(
                ", ".join(S.CAMPOS.get(c, c) for c in falta)))
        if alerta:
            linhas.append(tr("Atenção: há grupo que não limita modalidade nem tipo de imagem, e por isso alcança outras modalidades."))
        self.previa.setText(" ".join(linhas))
        self.previa.setStyleSheet("color:#c98b12;" if alerta else "")

    def aceitar(self) -> None:
        regra = self.atual()
        if not regra.criterios:
            QMessageBox.warning(self, tr("Regra de seleção"),
                                tr("Acrescente pelo menos um critério: regra vazia não pega nada."))
            return
        self.regra = regra
        self.accept()


class SelecaoDialog(QDialog):
    """A lista de regras de uma análise."""

    def __init__(self, settings, analise: str = "densidade", repo=None, parent=None) -> None:
        super().__init__(parent)
        self.settings, self.analise, self.repo = settings, analise, repo
        self.setWindowTitle(tr("Onde a análise roda"))
        self.resize(820, 520)
        self.regras = S.carregar(settings, analise)

        v = QVBoxLayout(self)
        self.escolha = QComboBox()
        for chave, rotulo in ANALISES.items():
            self.escolha.addItem(tr(rotulo), chave)
        self.escolha.setCurrentIndex(max(0, list(ANALISES).index(analise)
                                         if analise in ANALISES else 0))
        self.escolha.currentIndexChanged.connect(self.trocar_analise)
        topo = QHBoxLayout()
        topo.addWidget(QLabel(tr("Análise")))
        topo.addWidget(self.escolha, 1)
        v.addLayout(topo)

        explica = QLabel(tr("Cada serviço tem aparelho e protocolo diferentes. Marque aqui em que imagens esta análise deve rodar; as regras são lidas de cima para baixo e basta uma delas pegar. Os valores oferecidos saem do seu próprio acervo."))
        explica.setWordWrap(True)
        v.addWidget(explica)

        self.lista = QListWidget()
        self.lista.itemChanged.connect(self.marcou)
        self.lista.itemDoubleClicked.connect(lambda _i: self.editar())
        v.addWidget(self.lista, 1)

        botoes = QHBoxLayout()
        for texto, fn in ((tr("Nova…"), self.nova), (tr("Editar…"), self.editar),
                          (tr("Duplicar"), self.duplicar), (tr("Remover"), self.remover),
                          (tr("Restaurar o padrão"), self.restaurar)):
            b = QPushButton(texto)
            b.clicked.connect(fn)
            botoes.addWidget(b)
        botoes.addStretch(1)
        v.addLayout(botoes)

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.reject)
        v.addWidget(bb)
        self.preencher()

    # ------------------------------------------------------------------ lista
    def preencher(self) -> None:
        self.lista.blockSignals(True)
        self.lista.clear()
        for r in self.regras:
            it = QListWidgetItem(f"{r.nome} — {r.texto(tr)}")
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if r.ativa else Qt.Unchecked)
            self.lista.addItem(it)
        self.lista.blockSignals(False)

    def guardar(self) -> None:
        S.salvar(self.settings, self.analise, self.regras)
        self.preencher()

    def marcou(self, item: QListWidgetItem) -> None:
        i = self.lista.row(item)
        if 0 <= i < len(self.regras):
            self.regras[i].ativa = item.checkState() == Qt.Checked
            self.guardar()

    def atual(self) -> int:
        return self.lista.currentRow()

    # ------------------------------------------------------------------ ações
    def trocar_analise(self) -> None:
        self.analise = self.escolha.currentData()
        self.regras = S.carregar(self.settings, self.analise)
        self.preencher()

    def nova(self) -> None:
        dlg = EditorSelecao(S.Selecao(), self.repo, self)
        if dlg.exec() == QDialog.Accepted:
            self.regras.append(dlg.regra)
            self.guardar()

    def editar(self) -> None:
        i = self.atual()
        if i < 0:
            return
        dlg = EditorSelecao(self.regras[i], self.repo, self)
        if dlg.exec() == QDialog.Accepted:
            dlg.regra.ativa = self.regras[i].ativa
            self.regras[i] = dlg.regra
            self.guardar()

    def duplicar(self) -> None:
        i = self.atual()
        if i < 0:
            return
        copia = S.Selecao.from_dict(self.regras[i].to_dict())
        copia.nome = tr("{} (cópia)").format(copia.nome)
        self.regras.insert(i + 1, copia)
        self.guardar()

    def remover(self) -> None:
        i = self.atual()
        if i < 0:
            return
        if QMessageBox.question(self, tr("Onde a análise roda"),
                                tr("Remover a regra “{}”?").format(self.regras[i].nome)) \
                == QMessageBox.Yes:
            del self.regras[i]
            self.guardar()

    def restaurar(self) -> None:
        if QMessageBox.question(self, tr("Onde a análise roda"),
                                tr("Voltar às regras que vêm de fábrica? As suas serão perdidas.")) \
                == QMessageBox.Yes:
            self.regras = S.restaurar_padrao(self.settings, self.analise)
            self.preencher()
