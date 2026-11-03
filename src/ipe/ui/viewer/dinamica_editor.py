"""Preferências ▸ Dinâmica da mama (0.99.9): parâmetros pré-configurados e layouts da avaliação dinâmica.

Em cima, os parâmetros com que a janela da dinâmica abre. Embaixo, os layouts, no mesmo desenho
do editor de protocolos de exibição: a lista à esquerda, a grade à direita; clique num quadro e
escolha embaixo o que ele mostra (mapa, fase ou outra série do exame) e a cor.
"""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QPushButton, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from ipe.ui.viewer import dinamica_config as DC


class DinamicaMamaEditor(QWidget):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.lays = DC.layouts(settings)
        self._li = -1
        self._ci = 0
        self._enchendo = False
        self.botoes_quadro: list[QPushButton] = []

        # ------------------------------------------------ parâmetros
        p = dict(DC.PARAMETROS_FABRICA)
        gravado = settings.get("dyn.padrao", None)
        if isinstance(gravado, dict):
            p.update(gravado)
        elif isinstance(settings.get("dyn.ultimos", None), dict):
            p.update(settings.get("dyn.ultimos"))        # ponto de partida: o que ele já usava
        g_par = QGroupBox("Parâmetros pré-configurados (a janela da dinâmica abre com eles)")
        f = QFormLayout(g_par)
        self.c_origem = QComboBox()
        self.c_origem.addItem("Estes parâmetros", "padrao")
        self.c_origem.addItem("Os últimos usados no botão Dinâmica", "ultimos")
        origem = settings.get("dyn.origem_parametros", "") or "padrao"
        self.c_origem.setCurrentIndex(max(0, self.c_origem.findData(origem)))
        f.addRow("Ao abrir a dinâmica, começar com:", self.c_origem)
        self.s_thr = QDoubleSpinBox(minimum=0, maximum=500, decimals=0, singleStep=10, suffix=" %")
        self.s_thr.setValue(float(p["threshold_pct"]))
        self.s_thr.setToolTip("Realce inicial mínimo para calcular o SER (fora disso o mapa fica preto).")
        f.addRow("Limiar de realce inicial:", self.s_thr)
        self.c_thr_all = QCheckBox("Aplicar o limiar também em MSI, PEI, realce inicial e TTP")
        self.c_thr_all.setChecked(bool(p["threshold_all"]))
        f.addRow(self.c_thr_all)
        self.s_noise = QDoubleSpinBox(minimum=0, maximum=50, decimals=1, suffix=" % do máximo")
        self.s_noise.setValue(float(p["noise_pct"]))
        f.addRow("Ignorar sinal abaixo de:", self.s_noise)
        self.s_rapido = QDoubleSpinBox(minimum=50, maximum=1000, decimals=0, singleStep=10, suffix=" %")
        self.s_rapido.setValue(float(p["rapido_pct"]))
        f.addRow("Mapa cinético — realce rápido acima de:", self.s_rapido)
        self.s_tardio = QDoubleSpinBox(minimum=1, maximum=50, decimals=0, suffix=" %")
        self.s_tardio.setValue(float(p["tardio_pct"]))
        f.addRow("Mapa cinético — faixa do platô:", self.s_tardio)
        self.s_sinal = QDoubleSpinBox(minimum=0, maximum=60, decimals=0, suffix=" % da referência")
        self.s_sinal.setValue(float(p["sinal_min_pct"]))
        f.addRow("Mapa cinético — tecido com pré ≥:", self.s_sinal)
        self.c_units = QComboBox()
        self.c_units.addItem("Relativos ao pré-contraste (%)", True)
        self.c_units.addItem("Absolutos (sinal)", False)
        self.c_units.setCurrentIndex(0 if p["relative"] else 1)
        f.addRow("Mapas MSI/PEI:", self.c_units)
        self.c_motion = QCheckBox("Corrigir movimento entre as fases (translação 3D)")
        self.c_motion.setChecked(bool(p["motion"]))
        f.addRow(self.c_motion)
        self.c_rigido = QCheckBox("Incluir rotação (registro rígido, mais lento)")
        self.c_rigido.setChecked(bool(p.get("motion_rigido", False)))
        f.addRow(self.c_rigido)
        self.s_pre = QSpinBox(minimum=1, maximum=20)
        self.s_pre.setValue(int(p.get("pre", 0)) + 1)
        self.s_pre.setToolTip("Qual fase é a pré-contraste (quase sempre a 1ª). A inicial e a tardia "
                              "são escolhidas pela dinâmica de cada exame.")
        f.addRow("Fase pré-contraste:", self.s_pre)
        self.c_padrao = QComboBox()
        f.addRow("Layout que abre:", self.c_padrao)
        self.c_motion.toggled.connect(self._habilitar_parametros)
        self.c_origem.currentIndexChanged.connect(self._habilitar_parametros)

        # ------------------------------------------------ layouts
        self.l_lays = QListWidget()
        self.l_lays.currentRowChanged.connect(lambda _r: self._escolheu_layout())
        botoes = QGridLayout()
        for k, (texto, fn) in enumerate((("+ Novo", self.novo), ("Duplicar", self.duplicar),
                                         ("Remover", self.remover), ("▲", lambda: self.mover(-1)),
                                         ("▼", lambda: self.mover(1)), ("De fábrica", self.de_fabrica))):
            b = QPushButton(texto)
            b.clicked.connect(fn)
            if texto == "De fábrica":
                b.setToolTip("Acrescenta os layouts de fábrica que não estão na lista")
            botoes.addWidget(b, k // 3, k % 3)
        esq = QWidget()
        el = QVBoxLayout(esq)
        el.setContentsMargins(0, 0, 0, 0)
        el.addWidget(QLabel("<b>Layouts</b>"))
        el.addWidget(self.l_lays, 1)
        el.addLayout(botoes)

        self.e_nome = QLineEdit()
        self.e_nome.textEdited.connect(self._mudou_nome)
        self.e_rows = QSpinBox(minimum=1, maximum=4)
        self.e_cols = QSpinBox(minimum=1, maximum=4)
        for sp in (self.e_rows, self.e_cols):
            sp.valueChanged.connect(self._mudou_grade)
        topo = QHBoxLayout()
        topo.addWidget(QLabel("Nome:"))
        topo.addWidget(self.e_nome, 1)
        topo.addWidget(QLabel("Quadros:"))
        topo.addWidget(self.e_rows)
        topo.addWidget(QLabel("×"))
        topo.addWidget(self.e_cols)
        self.grade = QGridLayout()
        self.grade.setSpacing(4)
        grade_host = QWidget()
        grade_host.setLayout(self.grade)
        grade_host.setMinimumHeight(130)

        self.q_vista = QComboBox()
        for k, v in DC.VISTAS.items():
            self.q_vista.addItem(v, k)
        self.q_serie = QLineEdit(placeholderText="Ex.: T2|STIR  ou  DWI|DIFUS|ADC")
        self.q_serie.setToolTip("Palavras da descrição da série. Com |, as alternativas em ordem de "
                                "preferência: a primeira que existir no exame entra.")
        self.q_cor = QComboBox()
        self.q_cor.addItem("A do mapa (a última escolhida para ele)", DC.COR_PADRAO)
        self.q_cor.addItem("Cinza", DC.COR_CINZA)
        from ipe.imaging import colormaps as CM
        for k, v in CM.COLORMAPS.items():
            self.q_cor.addItem(v[0], k)
        self.q_vista.currentIndexChanged.connect(self._mudou_quadro)
        self.q_cor.currentIndexChanged.connect(self._mudou_quadro)
        self.q_serie.textEdited.connect(self._mudou_quadro)
        fq = QFormLayout()
        fq.addRow("Mostra:", self.q_vista)
        fq.addRow("Série:", self.q_serie)
        fq.addRow("Cor:", self.q_cor)
        self.l_quadro = QLabel("<b>Quadro</b>")
        self.painel_quadro = QWidget()
        self.painel_quadro.setLayout(fq)

        dir_ = QWidget()
        dl = QVBoxLayout(dir_)
        dl.setContentsMargins(6, 0, 0, 0)
        dl.addLayout(topo)
        dl.addWidget(grade_host, 1)
        dl.addWidget(self.l_quadro)
        dl.addWidget(self.painel_quadro)
        nota = QLabel("<small>O painel das curvas fica sempre ao lado dos quadros. Quadro de <b>série</b> abre "
                      "a série do exame no mesmo corte do mapa (a T2 ou a difusão junto da cinética, por "
                      "exemplo). Fase que o exame não tem (a 5ª pós numa dinâmica de 4) deixa o quadro vazio "
                      "com o aviso.</small>")
        nota.setWordWrap(True)
        nota.setStyleSheet("color:#9a9a9a")
        dl.addWidget(nota)
        self.painel_layout = dir_

        div = QSplitter(Qt.Horizontal)
        div.addWidget(esq)
        div.addWidget(dir_)
        div.setStretchFactor(0, 1)
        div.setStretchFactor(1, 3)
        esq.setMaximumWidth(320)
        g_lay = QGroupBox("Layouts da avaliação dinâmica")
        gl = QVBoxLayout(g_lay)
        gl.addWidget(div)

        lay = QVBoxLayout(self)
        lay.addWidget(g_par)
        lay.addWidget(g_lay, 1)
        self._encher_lista()
        self._encher_padrao(settings.get("dyn.layout_padrao", "") or (self.lays[0]["nome"] if self.lays else ""))
        if self.lays:
            self.l_lays.setCurrentRow(0)
        self._habilitar_parametros()

    # ------------------------------------------------------------ parâmetros
    def _habilitar_parametros(self, *_a) -> None:
        proprios = self.c_origem.currentData() == "padrao"
        for w in (self.s_thr, self.c_thr_all, self.s_noise, self.s_rapido, self.s_tardio, self.s_sinal,
                  self.c_units, self.c_motion, self.s_pre):
            w.setEnabled(proprios)
        self.c_rigido.setEnabled(proprios and self.c_motion.isChecked())

    def parametros(self) -> dict:
        return {"pre": self.s_pre.value() - 1, "threshold_pct": self.s_thr.value(),
                "threshold_all": self.c_thr_all.isChecked(), "noise_pct": self.s_noise.value(),
                "rapido_pct": self.s_rapido.value(), "tardio_pct": self.s_tardio.value(),
                "sinal_min_pct": self.s_sinal.value(), "relative": bool(self.c_units.currentData()),
                "motion": self.c_motion.isChecked(),
                "motion_rigido": self.c_motion.isChecked() and self.c_rigido.isChecked(),
                "layout_nome": self.c_padrao.currentText()}

    def _encher_padrao(self, escolhido: str) -> None:
        self.c_padrao.blockSignals(True)
        self.c_padrao.clear()
        for lay in self.lays:
            self.c_padrao.addItem(lay["nome"])
        i = self.c_padrao.findText(escolhido)
        self.c_padrao.setCurrentIndex(i if i >= 0 else 0)
        self.c_padrao.blockSignals(False)

    # ------------------------------------------------------------ lista
    def _encher_lista(self) -> None:
        atual = self.l_lays.currentRow()
        self.l_lays.blockSignals(True)
        self.l_lays.clear()
        for lay in self.lays:
            self.l_lays.addItem(f"{lay['nome']}  ({lay['rows']}×{lay['cols']})")
        self.l_lays.blockSignals(False)
        if 0 <= atual < len(self.lays):
            self.l_lays.setCurrentRow(atual)

    def _layout(self) -> dict | None:
        return self.lays[self._li] if 0 <= self._li < len(self.lays) else None

    def _escolheu_layout(self) -> None:
        r = self.l_lays.currentRow()
        self._li = r if 0 <= r < len(self.lays) else -1
        self._ci = 0
        lay = self._layout()
        self.painel_layout.setEnabled(lay is not None)
        self._enchendo = True
        try:
            self.e_nome.setText(lay["nome"] if lay else "")
            self.e_rows.setValue(lay["rows"] if lay else 1)
            self.e_cols.setValue(lay["cols"] if lay else 1)
        finally:
            self._enchendo = False
        self._desenhar_grade()

    def _nome_livre(self, base: str) -> str:
        nomes = {lay["nome"] for lay in self.lays}
        if base not in nomes:
            return base
        k = 2
        while f"{base} ({k})" in nomes:
            k += 1
        return f"{base} ({k})"

    def _depois_de_mudar_lista(self, escolher: int) -> None:
        padrao = self.c_padrao.currentText()
        self._encher_lista()
        self._encher_padrao(padrao)
        if self.lays:
            self.l_lays.setCurrentRow(max(0, min(escolher, len(self.lays) - 1)))
        self._escolheu_layout()

    def novo(self) -> None:
        self.lays.append(DC.normalizado({"nome": self._nome_livre("Novo layout"), "rows": 1, "cols": 2,
                                         "quadros": ["cin", "ph:early"]}))
        self._depois_de_mudar_lista(len(self.lays) - 1)

    def duplicar(self) -> None:
        lay = self._layout()
        if lay is None:
            return
        c = copy.deepcopy(lay)
        c["nome"] = self._nome_livre(f"{lay['nome']} (cópia)")
        self.lays.insert(self._li + 1, c)
        self._depois_de_mudar_lista(self._li + 1)

    def remover(self) -> None:
        if self._layout() is None or len(self.lays) <= 1:
            return                   # a dinâmica precisa de pelo menos um layout
        i = self._li
        del self.lays[i]
        self._depois_de_mudar_lista(max(0, i - 1))

    def mover(self, d: int) -> None:
        i, j = self._li, self._li + d
        if not (0 <= i < len(self.lays) and 0 <= j < len(self.lays)):
            return
        self.lays[i], self.lays[j] = self.lays[j], self.lays[i]
        self._depois_de_mudar_lista(j)

    def de_fabrica(self) -> None:
        nomes = {lay["nome"] for lay in self.lays}
        for lay in DC.FABRICA:
            if lay["nome"] not in nomes:
                self.lays.append(copy.deepcopy(lay))
        self._depois_de_mudar_lista(self._li)

    # ------------------------------------------------------------ layout escolhido
    def _mudou_nome(self, *_a) -> None:
        lay = self._layout()
        if lay is None or self._enchendo:
            return
        antigo = lay["nome"]
        novo = self.e_nome.text().strip() or "Layout"
        if any(x is not lay and x["nome"] == novo for x in self.lays):
            return                   # nome repetido não entra: o protocolo acha o layout pelo nome
        lay["nome"] = novo
        it = self.l_lays.item(self._li)
        if it is not None:
            it.setText(f"{lay['nome']}  ({lay['rows']}×{lay['cols']})")
        padrao = self.c_padrao.currentText()
        self._encher_padrao(novo if padrao == antigo else padrao)

    def _mudou_grade(self, *_a) -> None:
        lay = self._layout()
        if lay is None or self._enchendo:
            return
        lay["rows"], lay["cols"] = self.e_rows.value(), self.e_cols.value()
        n = lay["rows"] * lay["cols"]
        lay["quadros"] = (lay["quadros"] + [DC.quadro("") for _ in range(n)])[:n]
        it = self.l_lays.item(self._li)
        if it is not None:
            it.setText(f"{lay['nome']}  ({lay['rows']}×{lay['cols']})")
        self._desenhar_grade()

    def _desenhar_grade(self) -> None:
        for b in self.botoes_quadro:
            self.grade.removeWidget(b)
            b.hide()
            b.setParent(None)
            b.deleteLater()
        self.botoes_quadro = []
        lay = self._layout()
        if lay is None:
            self._mostrar_quadro()
            return
        for k, q in enumerate(lay["quadros"]):
            r, c = divmod(k, lay["cols"])
            b = QPushButton(self._texto(k, q))
            b.setCheckable(True)
            b.setMinimumHeight(44)
            b.setStyleSheet("QPushButton{text-align:left;padding:4px}"
                            "QPushButton:checked{background:#35506e;color:white}")
            b.clicked.connect(lambda _=False, i=k: self._escolheu_quadro(i))
            self.grade.addWidget(b, r, c)
            self.botoes_quadro.append(b)
        self._ci = min(self._ci, len(lay["quadros"]) - 1)
        self._escolheu_quadro(self._ci)

    @staticmethod
    def _texto(k: int, q: dict) -> str:
        return f"{k + 1}. " + DC.descrever(q).replace(" · ", "\n", 1)

    def _quadro(self) -> dict | None:
        lay = self._layout()
        if lay is None or not 0 <= self._ci < len(lay["quadros"]):
            return None
        return lay["quadros"][self._ci]

    def _escolheu_quadro(self, i: int) -> None:
        self._ci = i
        for k, b in enumerate(self.botoes_quadro):
            b.setChecked(k == i)
        self._mostrar_quadro()

    def _mostrar_quadro(self) -> None:
        q = self._quadro()
        self._enchendo = True
        try:
            self.l_quadro.setText(f"<b>Quadro {self._ci + 1}</b>" if q is not None else "<b>Quadro</b>")
            q = DC.quadro(q)
            self.q_vista.setCurrentIndex(max(0, self.q_vista.findData(q["vista"])))
            self.q_serie.setText(q["serie"])
            self.q_cor.setCurrentIndex(max(0, self.q_cor.findData(q["cor"])))
            self.q_serie.setEnabled(q["vista"] == "serie")
        finally:
            self._enchendo = False

    def _mudou_quadro(self, *_a) -> None:
        if self._enchendo:
            return
        q = self._quadro()
        if q is None:
            return
        q.update(DC.quadro({"vista": self.q_vista.currentData() or "", "serie": self.q_serie.text().strip(),
                            "cor": self.q_cor.currentData() or ""}))
        self.q_serie.setEnabled(q["vista"] == "serie")
        if 0 <= self._ci < len(self.botoes_quadro):
            self.botoes_quadro[self._ci].setText(self._texto(self._ci, q))

    # ------------------------------------------------------------ gravar
    def layouts(self) -> list[dict]:
        return [DC.normalizado(x) for x in self.lays]

    def save(self) -> None:
        s = self.settings
        s.set("dyn.layouts", self.layouts())
        s.set("dyn.layout_padrao", self.c_padrao.currentText())
        s.set("dyn.origem_parametros", self.c_origem.currentData() or "padrao")
        s.set("dyn.padrao", self.parametros())
