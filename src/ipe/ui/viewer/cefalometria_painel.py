"""Janela da cefalometria do cavum (0.99.15): a conferência do que a IA mediu, e o roteiro à mão.

Uma linha por medida, na ordem do laudo dele: o número, a referência e **de quem é** o número
(automático ou editado). Para trocar um valor: digitar na célula, ou **Medir à mão**, que liga a
ferramenta certa (régua; contorno para a área) e usa a próxima medida feita em qualquer quadro da
aba. Sem a IA (ou sem TC), a mesma janela começa vazia e serve de roteiro manual.

A imagem de conferência (sagital com as linhas) e as estruturas ficam no exame; esta janela é a
que monta o texto e manda para o laudo.
"""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
)

from ipe.ai import cefalometria as CF
from ipe.ui.tabelas import colunas_ajustaveis
from ipe.ui.viewer.roteiro_painel import valor_da_anotacao

#: ferramenta para medir à mão: a área é um contorno; o nível do hioide é texto (digitado)
FERRAMENTA = {k: "measure" for k in CF.ORDEM}
FERRAMENTA["area"] = "polygon"
FERRAMENTA.pop("hioide_nivel")
TIPOS = {"measure": ("line",), "polygon": ("polygon",)}
INSTRUCAO = {
    "area": "No plano perpendicular ao eixo da via aérea (MPR oblíquo), no ponto mais estreito, contorne a luz.",
    "palato_comprimento": "No sagital mediano, da espinha nasal posterior à ponta da úvula.",
    "palato_espessura": "No sagital mediano, a maior espessura do palato mole, perpendicular ao comprimento.",
    "pas_retropalatal": "No sagital mediano, a menor distância entre o palato mole e a parede posterior da faringe.",
    "pas_retrolingual": "No sagital mediano, a menor distância entre a base da língua e a parede posterior.",
    "hioide_mp": "No sagital, da linha gônio–mento (plano mandibular) à borda superior do hioide, perpendicular.",
    "lingua_transversal": "No axial ou coronal, a maior largura laterolateral da língua.",
    "lingua_ap": "No sagital mediano, da ponta à base da língua.",
    "hioide_nivel": "Linha horizontal pelo corpo do hioide: em que nível da coluna cai (ex.: platô inferior de C3).",
}


def vazio() -> CF.Cefalometria:
    res = CF.Cefalometria()
    for k in CF.ORDEM:
        res.medidas[k] = CF.Medida(k, CF.NOMES[k], unidade="mm²" if k == "area" else ("" if k == "hioide_nivel"
                                                                                     else "mm"),
                                   casas=0 if k == "area" else 1, origem="")
    return res


def _numero(txt: str) -> float | None:
    t = (txt or "").strip().replace(",", ".")
    for suf in ("mm²", "mm2", "mm"):
        if t.endswith(suf):
            t = t[: -len(suf)].strip()
    try:
        return float(t)
    except ValueError:
        return None


class CefalometriaPainel(QDialog):
    def __init__(self, tab, res: CF.Cefalometria | None = None, parent=None, automatica: bool = False):
        super().__init__(parent or tab)
        self.tab = tab
        self.settings = getattr(tab, "settings", None)
        self.setWindowFlag(Qt.Window, True)
        self.setModal(False)
        self.resize(760, 640)
        self.esperando: str | None = None
        self._usadas: set[int] = set()
        self._ligados: list = []

        self.titulo = QLabel()
        self.titulo.setWordWrap(True)
        self.tabela = QTableWidget(0, 5)
        self.tabela.setHorizontalHeaderLabels(["Nº", "Medida", "Valor", "Referência", "De quem"])
        for c, larg in enumerate((36, 300, 110, 200, 100)):
            self.tabela.setColumnWidth(c, larg)
        colunas_ajustaveis(self.tabela)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.itemChanged.connect(self._editou)
        self.tabela.currentCellChanged.connect(lambda *_a: self._mostrar_instrucao())
        self.instrucao = QLabel()
        self.instrucao.setWordWrap(True)
        self.instrucao.setStyleSheet("background:#26303a;color:#e8e8e8;padding:8px;border-radius:4px")
        self.b_medir = QPushButton("Medir à mão")
        self.b_medir.setToolTip("Liga a ferramenta: a próxima medida feita num quadro substitui este valor")
        self.b_medir.clicked.connect(self.medir_linha_atual)
        self.b_auto = QPushButton("Voltar ao automático")
        self.b_auto.clicked.connect(self._voltar_ao_automatico)
        self.b_refs = QPushButton("Referências…")
        self.b_refs.clicked.connect(self.editar_referencias)
        linha = QHBoxLayout()
        for b in (self.b_medir, self.b_auto, self.b_refs):
            linha.addWidget(b)
        linha.addStretch(1)
        self.texto_laudo = QTextEdit()
        self.texto_laudo.setReadOnly(True)
        self.texto_laudo.setMinimumHeight(170)
        self.b_copiar = QPushButton("Copiar o texto")
        self.b_copiar.clicked.connect(self._copiar)
        self.b_laudo = QPushButton("Mandar para o laudo")
        self.b_laudo.clicked.connect(self._mandar_ao_laudo)
        rodape = QHBoxLayout()
        rodape.addWidget(self.b_copiar)
        rodape.addWidget(self.b_laudo)
        rodape.addStretch(1)
        lay = QVBoxLayout(self)
        lay.addWidget(self.titulo)
        lay.addWidget(self.tabela, 1)
        lay.addWidget(self.instrucao)
        lay.addLayout(linha)
        lay.addWidget(QLabel("<b>Texto para o laudo</b>"))
        lay.addWidget(self.texto_laudo)
        lay.addLayout(rodape)
        self.ligar_quadros()
        self.carregar(res, automatica)

    # ------------------------------------------------------------ dados
    def carregar(self, res: CF.Cefalometria | None, automatica: bool = False) -> None:
        self.res = res if res is not None else vazio()
        self.original = copy.deepcopy(self.res)
        self.automatica = automatica and res is not None
        self.setWindowTitle("Cefalometria — conferência da automática" if self.automatica else "Cefalometria — à mão")
        if self.automatica:
            self.titulo.setText("Medidas feitas pela IA (TotalSegmentator + geometria). <b>Confira cada uma</b> na "
                                "imagem “Cefalometria: conferência” do exame; troque digitando ou com "
                                "<i>Medir à mão</i>.")
        else:
            self.titulo.setText("Faça as medidas na ordem: escolha a linha e clique em <i>Medir à mão</i>, ou digite "
                                "o valor.")
        self._usadas = {id(a) for vp in self.tab.viewports for a in getattr(vp, "annotations", [])}
        self._encher()
        self.tabela.setCurrentCell(0, 2)

    def _encher(self) -> None:
        refs = CF.referencias(self.settings)
        self.tabela.blockSignals(True)
        self.tabela.setRowCount(len(CF.ORDEM))
        for r, k in enumerate(CF.ORDEM):
            m = self.res.medidas[k]
            if m.valor is not None:
                v = m.texto_valor()
            else:
                v = m.texto if m.texto and not m.motivo else ""
            itens = [QTableWidgetItem(CF.NUMERO[k]), QTableWidgetItem(m.nome), QTableWidgetItem(v),
                     QTableWidgetItem(refs.get(k, "")), QTableWidgetItem(m.origem or "falta")]
            for c, it in enumerate(itens):
                if c != 2:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                it.setData(Qt.UserRole, k)
                self.tabela.setItem(r, c, it)
            dica = []
            if k == "area" and m.texto and m.valor is not None:
                dica.append(f"{m.texto} — {CF.classe_da_area(m.valor)}")
            if m.motivo and m.valor is None:
                dica.append(f"não medido: {m.motivo}")
                itens[4].setText("não medido")
                itens[4].setForeground(QBrush(QColor(240, 170, 90)))
            elif m.origem == "editado":
                itens[4].setForeground(QBrush(QColor(120, 190, 255)))
            for it in itens:
                it.setToolTip("\n".join(dica))
        self.tabela.blockSignals(False)
        self._atualizar_texto()

    def chave_atual(self) -> str | None:
        r = self.tabela.currentRow()
        return CF.ORDEM[r] if 0 <= r < len(CF.ORDEM) else None

    def _mostrar_instrucao(self) -> None:
        k = self.chave_atual()
        if k is None:
            return
        m = self.res.medidas[k]
        extra = f"<br>⚠ não medido pela IA: {m.motivo}" if m.motivo and m.valor is None else ""
        self.instrucao.setText(f"<b>{m.nome}</b><br>{INSTRUCAO.get(k, '')}{extra}")
        self.b_medir.setEnabled(k in FERRAMENTA)
        o = self.original.medidas[k]
        self.b_auto.setEnabled(self.automatica and m.origem == "editado" and (o.valor is not None or bool(o.texto)))

    def definir(self, k: str, valor: float | None = None, texto: str | None = None) -> None:
        m = self.res.medidas[k]
        if texto is not None:
            m.texto = texto
        if valor is not None:
            m.valor = valor
            if k == "area":
                m.texto = ""                        # o local era o do automático
        m.motivo = ""
        m.origem = "editado"
        m.linhas = []
        self._encher()

    def _editou(self, it: QTableWidgetItem) -> None:
        if it.column() != 2:
            return
        k = it.data(Qt.UserRole)
        txt = it.text().strip()
        if k == "hioide_nivel":
            self.definir(k, texto=txt)
            return
        v = _numero(txt)
        if v is None and txt:
            self._encher()                          # não é número: volta o que estava
            return
        if v is None:
            m = self.res.medidas[k]
            m.valor, m.origem = None, "editado"
            self._encher()
            return
        self.definir(k, valor=v)

    def _voltar_ao_automatico(self) -> None:
        k = self.chave_atual()
        if k is not None:
            self.res.medidas[k] = copy.deepcopy(self.original.medidas[k])
            self._encher()
            self._mostrar_instrucao()

    # ------------------------------------------------------------ medir à mão
    def ligar_quadros(self) -> None:
        for vp in self.tab.viewports:
            if vp in self._ligados:
                continue
            vp.sig.annotations_changed.connect(self.medida_feita)
            self._ligados.append(vp)

    def medir_linha_atual(self) -> None:
        k = self.chave_atual()
        if k is None or k not in FERRAMENTA:
            return
        self.esperando = k
        if hasattr(self.tab, "set_left_tool"):
            self.tab.set_left_tool(FERRAMENTA[k])
        self.tab.status_message.emit(f"Cefalometria: faça a medida “{CF.NOMES[k]}”.")
        self.b_medir.setText("Esperando a medida…")

    def medida_feita(self, vp) -> None:
        k = self.esperando
        if k is None or not self.isVisible():
            return
        tipos = TIPOS.get(FERRAMENTA.get(k, ""), ())
        novas = [a for a in getattr(vp, "annotations", []) if a.done and a.kind in tipos and id(a) not in self._usadas]
        if not novas:
            return
        ann = novas[-1]
        self._usadas.add(id(ann))
        v = valor_da_anotacao(vp, ann)
        if v is None or v <= 0:
            return
        self.esperando = None
        self.b_medir.setText("Medir à mão")
        self.definir(k, valor=v)
        r = CF.ORDEM.index(k)
        if not self.automatica and r + 1 < len(CF.ORDEM):         # à mão: vai para a próxima
            self.tabela.setCurrentCell(r + 1, 2)
            if CF.ORDEM[r + 1] in FERRAMENTA:
                self.medir_linha_atual()

    # ------------------------------------------------------------ referências e texto
    def editar_referencias(self) -> bool:
        refs = CF.referencias(self.settings)
        dlg = QDialog(self)
        dlg.setWindowTitle("Referências da cefalometria")
        form = QFormLayout(dlg)
        campos = {}
        for k in CF.ORDEM:
            campos[k] = QLineEdit(refs.get(k, ""))
            form.addRow(CF.NOMES[k], campos[k])
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        bb.button(QDialogButtonBox.RestoreDefaults).clicked.connect(
            lambda: [campos[k].setText(CF.REFERENCIAS[k]) for k in CF.ORDEM])
        form.addRow(bb)
        if dlg.exec() != QDialog.Accepted:
            return False
        self.salvar_referencias({k: c.text().strip() for k, c in campos.items()})
        return True

    def salvar_referencias(self, novas: dict) -> None:
        if self.settings is not None:
            diferentes = {k: v for k, v in novas.items() if v != CF.REFERENCIAS.get(k)}
            self.settings.set(CF.CHAVE_REFERENCIAS, diferentes)
        self._encher()

    def texto(self) -> str:
        return CF.texto_do_laudo(self.res, self.settings, automatica=self.automatica)

    def _atualizar_texto(self) -> None:
        self.texto_laudo.setPlainText(self.texto())

    def _copiar(self) -> None:
        QGuiApplication.clipboard().setText(self.texto())
        self.tab.status_message.emit("Texto da cefalometria copiado.")

    def _mandar_ao_laudo(self) -> None:
        ok = hasattr(self.tab, "append_to_report") and self.tab.append_to_report(self.texto())
        if not ok:
            self._copiar()
            self.tab.status_message.emit("Sem laudo aberto para escrever: o texto foi copiado.")
