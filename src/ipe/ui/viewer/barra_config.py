"""Configurações ▸ Visualizador ▸ Barra de ferramentas e aplicações (0.99.12).

Duas abas:
- **Aplicações**: a ordem do bloco "do exame", e para cada uma Automático / Sempre / Nunca, com as
  exceções por região que ele criou pelo botão direito na barra (aqui se vê e se tira).
- **Regiões do corpo**: o dicionário de termos que diz de que região é o exame. Tem uma caixa de
  teste: escreve-se uma descrição e a tela diz em que regiões ela cai.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ipe.ui.tabelas import colunas_ajustaveis
from ipe.ui.viewer import aplicacoes as AP


class BarraDialog(QDialog):
    def __init__(self, settings, parent=None, aba: str = "aplicacoes"):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Configurações — Barra de ferramentas e aplicações")
        self.resize(820, 520)
        cfg = settings.get("viewer.barra", None)
        self._modos = dict((cfg or {}).get("modos") or {}) if isinstance(cfg, dict) else {}
        self.tabs = QTabWidget()
        self.tabs.addTab(self._aba_aplicacoes(), "Aplicações")
        self.tabs.addTab(self._aba_regioes(), "Regiões do corpo")
        if aba == "regioes":
            self.tabs.setCurrentIndex(1)
            self.setWindowTitle("Configurações — Regiões do corpo")
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText("Salvar")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self.save)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs)
        lay.addWidget(bb)

    # ------------------------------------------------------------ aplicações
    def _aba_aplicacoes(self) -> QWidget:
        w = QWidget()
        dica = QLabel("As aplicações aparecem num bloco próprio no fim da barra do visualizador, só quando "
                      "servem ao exame aberto (<b>Automático</b>). <b>Sempre</b> e <b>Nunca</b> passam por "
                      "cima da regra. O que fica fora da barra continua no botão <b>Aplicações</b> e roda "
                      "mesmo assim. Exceção por região se cria pelo botão direito na própria barra.")
        dica.setWordWrap(True)
        dica.setStyleSheet("color:#9a9a9a")
        self.t_apps = QTableWidget(0, 4)
        self.t_apps.setHorizontalHeaderLabels(["Aplicação", "Aparece automaticamente em", "Mostrar",
                                               "Exceções por região"])
        self.t_apps.verticalHeader().setVisible(False)
        self.t_apps.setSelectionBehavior(QTableWidget.SelectRows)
        self.t_apps.setSelectionMode(QTableWidget.SingleSelection)
        self.t_apps.setEditTriggers(QTableWidget.NoEditTriggers)
        for aid in AP.ordem(self.settings):
            self._linha_app(aid)
        self.t_apps.resizeColumnsToContents()
        colunas_ajustaveis(self.t_apps)
        botoes = QHBoxLayout()
        for texto, fn in (("▲ Subir", lambda: self._mover(-1)), ("▼ Descer", lambda: self._mover(1)),
                          ("Tirar as exceções da selecionada", self._tirar_excecoes),
                          ("Tudo automático", self._tudo_automatico)):
            b = QPushButton(texto)
            b.clicked.connect(fn)
            botoes.addWidget(b)
        botoes.addStretch(1)
        lay = QVBoxLayout(w)
        lay.addWidget(dica)
        lay.addWidget(self.t_apps, 1)
        lay.addLayout(botoes)
        return w

    def _texto_excecoes(self, aid: str) -> str:
        modos = self._modos.get(aid) or {}
        partes = [f"{AP.nome_da_regiao(self.settings, r)}: {AP.NOME_DO_MODO[m].split(' (')[0].lower()}"
                  for r, m in sorted(modos.items()) if r != "*" and m in AP.MODOS]
        return "; ".join(partes) or "—"

    def _linha_app(self, aid: str, linha: int | None = None) -> None:
        app = AP.APLICACOES[aid]
        if linha is None:
            linha = self.t_apps.rowCount()
            self.t_apps.insertRow(linha)
        it = QTableWidgetItem(app.nome)
        it.setData(Qt.UserRole, aid)
        it.setToolTip(app.descricao)
        self.t_apps.setItem(linha, 0, it)
        self.t_apps.setItem(linha, 1, QTableWidgetItem(AP.descrever_regra(app, self.settings)))
        c = QComboBox()
        for m in AP.MODOS:
            c.addItem(AP.NOME_DO_MODO[m], m)
        c.setCurrentIndex(max(0, c.findData((self._modos.get(aid) or {}).get("*", "auto"))))
        self.t_apps.setCellWidget(linha, 2, c)
        self.t_apps.setItem(linha, 3, QTableWidgetItem(self._texto_excecoes(aid)))

    def ordem_na_tela(self) -> list[str]:
        return [self.t_apps.item(r, 0).data(Qt.UserRole) for r in range(self.t_apps.rowCount())]

    def modo_na_tela(self, aid: str) -> str:
        for r in range(self.t_apps.rowCount()):
            if self.t_apps.item(r, 0).data(Qt.UserRole) == aid:
                return self.t_apps.cellWidget(r, 2).currentData()
        return "auto"

    def _recolher_modos(self) -> None:
        for aid in self.ordem_na_tela():
            deste = dict(self._modos.get(aid) or {})
            m = self.modo_na_tela(aid)
            if m == "auto":
                deste.pop("*", None)
            else:
                deste["*"] = m
            if deste:
                self._modos[aid] = deste
            else:
                self._modos.pop(aid, None)

    def _mover(self, passo: int) -> None:
        r = self.t_apps.currentRow()
        alvo = r + passo
        if r < 0 or not 0 <= alvo < self.t_apps.rowCount():
            return
        self._recolher_modos()
        ordem = self.ordem_na_tela()
        ordem[r], ordem[alvo] = ordem[alvo], ordem[r]
        self.t_apps.setRowCount(0)
        for aid in ordem:
            self._linha_app(aid)
        self.t_apps.selectRow(alvo)

    def _tirar_excecoes(self) -> None:
        r = self.t_apps.currentRow()
        if r < 0:
            return
        aid = self.t_apps.item(r, 0).data(Qt.UserRole)
        deste = {k: v for k, v in (self._modos.get(aid) or {}).items() if k == "*"}
        if deste:
            self._modos[aid] = deste
        else:
            self._modos.pop(aid, None)
        self.t_apps.setItem(r, 3, QTableWidgetItem("—"))

    def _tudo_automatico(self) -> None:
        self._modos = {}
        for r in range(self.t_apps.rowCount()):
            self.t_apps.cellWidget(r, 2).setCurrentIndex(0)
            self.t_apps.setItem(r, 3, QTableWidgetItem("—"))

    # ------------------------------------------------------------ regiões
    def _aba_regioes(self) -> QWidget:
        w = QWidget()
        dica = QLabel("A região do exame sai do <i>BodyPartExamined</i> das séries e das descrições do exame "
                      "e das séries. Termos separados por <b>|</b>, sem diferença de acento nem maiúscula. "
                      "Termo de até 3 letras vale como palavra inteira (PE, RIM, ATM); com 4 ou mais, como "
                      "começo de palavra (ABDOM pega ABDOMEN e ABDOMINAL); com espaço, como trecho "
                      "(TEMPORAL BONE).")
        dica.setWordWrap(True)
        dica.setStyleSheet("color:#9a9a9a")
        self.t_reg = QTableWidget(0, 2)
        self.t_reg.setHorizontalHeaderLabels(["Região", "Termos"])
        self.t_reg.verticalHeader().setVisible(False)
        self._encher_regioes(AP.regioes(self.settings))
        self.t_reg.resizeColumnsToContents()
        colunas_ajustaveis(self.t_reg)
        botoes = QHBoxLayout()
        for texto, fn in (("Nova região", self._nova_regiao), ("Remover", self._remover_regiao),
                          ("Voltar ao de fábrica", lambda: self._encher_regioes(dict(AP.REGIOES_FABRICA)))):
            b = QPushButton(texto)
            b.clicked.connect(fn)
            botoes.addWidget(b)
        botoes.addStretch(1)
        teste = QHBoxLayout()
        self.e_teste = QLineEdit(placeholderText="Teste: escreva uma descrição de exame ou série "
                                                 "(ex.: ANGIO TC TRONCOS SUPRA-AORTICOS)")
        self.l_teste = QLabel("")
        self.e_teste.textChanged.connect(self._testar)
        teste.addWidget(self.e_teste, 1)
        teste.addWidget(self.l_teste)
        lay = QVBoxLayout(w)
        lay.addWidget(dica)
        lay.addWidget(self.t_reg, 1)
        lay.addLayout(botoes)
        lay.addLayout(teste)
        return w

    def _encher_regioes(self, regs: dict) -> None:
        self.t_reg.setRowCount(0)
        for rid, (nome, termos) in regs.items():
            r = self.t_reg.rowCount()
            self.t_reg.insertRow(r)
            it = QTableWidgetItem(nome)
            it.setData(Qt.UserRole, rid)
            self.t_reg.setItem(r, 0, it)
            self.t_reg.setItem(r, 1, QTableWidgetItem(termos))

    def regioes_na_tela(self) -> dict[str, tuple[str, str]]:
        out = {}
        for r in range(self.t_reg.rowCount()):
            it = self.t_reg.item(r, 0)
            nome = (it.text() if it else "").strip()
            termos = (self.t_reg.item(r, 1).text() if self.t_reg.item(r, 1) else "").strip()
            if not nome:
                continue
            rid = it.data(Qt.UserRole) or AP._sem_acento(nome).lower().replace(" ", "_")
            out[str(rid)] = (nome, termos)
        return out

    def _nova_regiao(self) -> None:
        r = self.t_reg.rowCount()
        self.t_reg.insertRow(r)
        self.t_reg.setItem(r, 0, QTableWidgetItem("Nova região"))
        self.t_reg.setItem(r, 1, QTableWidgetItem(""))
        self.t_reg.editItem(self.t_reg.item(r, 0))

    def _remover_regiao(self) -> None:
        r = self.t_reg.currentRow()
        if r >= 0:
            self.t_reg.removeRow(r)

    def _testar(self, texto: str) -> None:
        achadas = [nome for _rid, (nome, termos) in self.regioes_na_tela().items()
                   if termos and AP.casa(texto, AP.termos(termos))]
        self.l_teste.setText("→ " + (", ".join(achadas) if achadas else "nenhuma região") if texto else "")

    # ------------------------------------------------------------ gravar
    def save(self) -> None:
        regs = self.regioes_na_tela()
        if not regs:
            QMessageBox.warning(self, "Regiões", "Deixe pelo menos uma região.")
            return
        self._recolher_modos()
        cfg = dict(self.settings.get("viewer.barra", None) or {})
        cfg["modos"] = self._modos
        cfg["ordem"] = self.ordem_na_tela()
        self.settings.set("viewer.barra", cfg)
        # só o que difere da fábrica é gravado; região de fábrica removida vira None
        dele = {}
        for rid, (nome, termos) in regs.items():
            if AP.REGIOES_FABRICA.get(rid) != (nome, termos):
                dele[rid] = {"nome": nome, "termos": termos}
        for rid in AP.REGIOES_FABRICA:
            if rid not in regs:
                dele[rid] = None
        self.settings.set("viewer.regioes", dele)
        self.settings.save()
        self.accept()
