"""Editor dos protocolos de exibição com etapas (0.88) — Preferências ▸ Protocolos de exibição.

Em cima, os protocolos (uma linha cada: quando vale). Embaixo à esquerda, as etapas do protocolo
escolhido; à direita, o desenho da etapa: clique num quadro e edite embaixo a série, o plano, MIP,
a janela, a cor, a posição, a sincronia e o monitor.
"""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ipe.ui.tabelas import colunas_ajustaveis
from ipe.ui.viewer import hanging as H

COLUNAS = ["Ativo", "Nome", "Modalidade", "Descrição do exame contém", "Etapas",
           "Anterior no monitor de comparação"]
PLANO_TXT = {"": "Como foi adquirida", "Axial": "Axial", "Coronal": "Coronal", "Sagital": "Sagital"}
RECON_TXT = {"": "Nenhuma (como a série)", "mpr": "MPR (corte fino no plano escolhido)",
             "mip": "MIP (espessura)", "minip": "MinIP (espessura)", "avg": "Média (espessura)",
             "mip3d": "MIP 3D (como o botão 3D)", "vr": "VR — renderização de volume (como o botão 3D)"}
SEM_ESPESSURA = {"", "mpr", "mip3d", "vr"}
POS_TXT = {"auto": "Automática (mesmo lugar ao trocar de série)", "inicio": "Primeiro corte",
           "meio": "Meio da pilha", "ponto": "Mesmo ponto do quadro ativo da etapa anterior"}
FASE_TXT = {"": "Série inteira (não escolhe fase)", "pre": "Pré-contraste",
            **{str(k): f"Pós-contraste {k} ({k}ª fase depois da pré)" for k in range(1, 10)}, "ult": "Última fase"}
METADE_TXT = {"": "Paciente inteiro", "direita": "Só a metade direita (mama direita)",
              "esquerda": "Só a metade esquerda (mama esquerda)"}
VISTA_TXT = {"": "Como vier", "anterior": "Anterior", "posterior": "Posterior", "direita": "Direita",
             "esquerda": "Esquerda", "superior": "Superior", "inferior": "Inferior"}


class ProtocolosEditor(QWidget):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.protos = [H.convertido(dict(p)) for p in H.protocols(settings)]
        self._pi = -1          # protocolo escolhido
        self._si = -1          # etapa escolhida
        self._ci = 0           # quadro escolhido
        self._enchendo = False

        dica = QLabel("Ao abrir um exame, o primeiro protocolo ativo que combinar (modalidade e descrição) "
                      "abre na etapa 1; <b>← →</b> passam de etapa, como na mamografia. Em cada etapa, cada "
                      "quadro diz a série (alternativas com <b>|</b>, em ordem de preferência), o plano, "
                      "MIP/MinIP/média, a janela e a cor. Mamografia não entra aqui: tem aba própria.")
        dica.setWordWrap(True)
        dica.setStyleSheet("color:#9a9a9a")

        # ---- protocolos: lista à esquerda, como na aba Mamografia (0.99.1)
        self.l_protos = QListWidget()
        self.l_protos.currentRowChanged.connect(lambda _r: self._escolheu_protocolo())
        botoes = QGridLayout()
        for k, (texto, fn) in enumerate((("+ Novo", self.novo_protocolo), ("Duplicar", self.duplicar_protocolo),
                                         ("Remover", self.remover_protocolo), ("▲", lambda: self.mover_protocolo(-1)),
                                         ("▼", lambda: self.mover_protocolo(1)),
                                         ("De fábrica", self.acrescentar_fabrica))):
            b = QPushButton(texto)
            b.clicked.connect(fn)
            if texto == "De fábrica":
                b.setToolTip("Acrescenta os protocolos de fábrica que não estão na lista")
            botoes.addWidget(b, k // 3, k % 3)
        coluna_esq = QWidget()
        ce = QVBoxLayout(coluna_esq)
        ce.setContentsMargins(0, 0, 0, 0)
        ce.addWidget(QLabel("<b>Protocolos</b> (o primeiro ativo que combina é usado)"))
        ce.addWidget(self.l_protos, 1)
        ce.addLayout(botoes)

        # ---- o protocolo escolhido, à direita
        self.e_p_nome = QLineEdit()
        self.e_p_mod = QLineEdit(placeholderText="CT, MR, PT…")
        self.e_p_desc = QLineEdit(placeholderText="vazio = qualquer exame da modalidade; ex.: ABDOME|PELVE")
        self.c_p_ativo = QCheckBox("Ativo")
        self.c_p_prior = QCheckBox("Anterior no monitor de comparação")
        for w in (self.e_p_nome, self.e_p_mod, self.e_p_desc):
            w.textEdited.connect(self._mudou_protocolo)
        for c in (self.c_p_ativo, self.c_p_prior):
            c.toggled.connect(self._mudou_protocolo)
        g_proto = QGroupBox("Protocolo")
        fp = QFormLayout(g_proto)
        fp.addRow("Nome:", self.e_p_nome)
        fp.addRow("Modalidade:", self.e_p_mod)
        fp.addRow("Descrição do exame contém:", self.e_p_desc)
        fp.addRow(self.c_p_ativo)
        fp.addRow(self.c_p_prior)
        self.g_proto = g_proto

        # ---- etapas
        self.l_etapas = QListWidget()
        self.l_etapas.currentRowChanged.connect(self._escolheu_etapa)
        be = QHBoxLayout()
        for texto, fn in (("+ Etapa", self.nova_etapa), ("Duplicar", self.duplicar_etapa),
                          ("Remover", self.remover_etapa), ("▲", lambda: self.mover_etapa(-1)),
                          ("▼", lambda: self.mover_etapa(1))):
            b = QPushButton(texto)
            b.clicked.connect(fn)
            be.addWidget(b)
        esq = QWidget()
        el = QVBoxLayout(esq)
        el.setContentsMargins(0, 0, 0, 0)
        self.l_titulo_etapas = QLabel("<b>Etapas</b>")
        el.addWidget(self.l_titulo_etapas)
        el.addWidget(self.l_etapas, 1)
        el.addLayout(be)
        gr = QLabel("Para montar uma etapa sem digitar: arrume o exame na tela e use <b>Gravar a tela como "
                    "etapa…</b> na barra do protocolo.")
        gr.setWordWrap(True)
        gr.setStyleSheet("color:#9a9a9a")
        el.addWidget(gr)

        # ---- desenho da etapa e o quadro
        self.e_nome = QLineEdit()
        self.e_nome.textEdited.connect(self._mudou_etapa)
        self.e_rows = QSpinBox(minimum=1, maximum=6)
        self.e_cols = QSpinBox(minimum=1, maximum=6)
        for sp in (self.e_rows, self.e_cols):
            sp.valueChanged.connect(self._mudou_grade)
        topo = QHBoxLayout()
        topo.addWidget(QLabel("Etapa:"))
        topo.addWidget(self.e_nome, 1)
        topo.addWidget(QLabel("Layout:"))
        topo.addWidget(self.e_rows)
        topo.addWidget(QLabel("×"))
        topo.addWidget(self.e_cols)
        # 0.94: a etapa pode abrir a avaliação dinâmica (como o botão Dinâmica)
        from ipe.ui.viewer import dinamica_config as DC
        self.e_din = QCheckBox("Abrir a avaliação dinâmica (mapas e curvas)")
        self.e_din.setToolTip("Como o botão Dinâmica: as fases vêm da dinâmica do exame e os parâmetros são os "
                              "últimos usados no botão. O layout desta etapa passa a ser o dos mapas.")
        self.e_din_layout = QComboBox()
        for rotulo in DC.nomes(settings):       # os layouts dele (Preferências ▸ Dinâmica da mama)
            self.e_din_layout.addItem(rotulo)
        self.e_din_layout.setToolTip("Os layouts da dinâmica se montam em Preferências ▸ Dinâmica da mama.")
        self.e_din_serie = QLineEdit(placeholderText=H.DINAMICA)
        self.e_din_serie.setToolTip("Série da dinâmica (palavras da descrição; | separa alternativas). "
                                    "Vazio = a dinâmica do exame, detectada sozinha.")
        self.e_din.toggled.connect(self._mudou_dinamica)
        self.e_din_layout.currentIndexChanged.connect(self._mudou_dinamica)
        self.e_din_serie.textEdited.connect(self._mudou_dinamica)
        self.e_din_serie.setMinimumWidth(150)
        linha_din = QHBoxLayout()
        linha_din.addWidget(self.e_din)
        linha_din.addWidget(QLabel("mapas:"))
        linha_din.addWidget(self.e_din_layout, 1)
        linha_din.addWidget(QLabel("série:"))
        linha_din.addWidget(self.e_din_serie, 1)
        self.grade = QGridLayout()
        self.grade.setSpacing(4)
        self.botoes_quadro: list[QPushButton] = []

        self.q_serie = QLineEdit(placeholderText="Ex.: T1 POS|T1 GD|T1  (vazio = quadro vazio)")
        self.q_serie.setToolTip("Palavras da descrição da série. Com |, as alternativas em ordem de "
                                "preferência: a primeira que existir no exame entra.")
        self.q_prior = QCheckBox("Do exame anterior (mesma modalidade)")
        self.q_fase = QComboBox()
        for k, v in FASE_TXT.items():
            self.q_fase.addItem(v, k)
        self.q_fase.setToolTip("Série dinâmica: qual fase entra no quadro. A série acima é procurada só entre as "
                               "que fazem parte de uma dinâmica (grupo ▦). A 1ª fase da dinâmica é a pré.")
        self.q_metade = QComboBox()
        for k, v in METADE_TXT.items():
            self.q_metade.addItem(v, k)
        self.q_metade.setToolTip("Meia mama: o volume é cortado no meio (centro do campo, direita-esquerda). Com "
                                 "MIP 3D ou VR, o 3D só daquela metade; com MIP/MinIP/média de espessura, o MIP "
                                 "sagital da metade inteira.")
        self.q_vista = QComboBox()
        for k, v in VISTA_TXT.items():
            self.q_vista.addItem(v, k)
        self.q_vista.setToolTip("De que lado se olha — as mesmas Vistas da barra do 3D. Mama direita com o "
                                "mamilo à esquerda: vista Esquerda; mama esquerda com o mamilo à direita: vista "
                                "Direita. Num corte, vale quando o corte é daquele plano.")
        self.q_plano = QComboBox()
        for k, v in PLANO_TXT.items():
            self.q_plano.addItem(v, k)
        self.q_recon = QComboBox()
        for k, v in RECON_TXT.items():
            self.q_recon.addItem(v, k)
        self.q_slab = QDoubleSpinBox(minimum=0, maximum=300, decimals=0, suffix=" mm")
        self.q_slab.setToolTip("Espessura do MIP/MinIP/média")
        self.q_janela = QComboBox()
        self.q_janela.setEditable(True)
        self.q_janela.setToolTip("Um preset (Preferências ▸ Presets de janela) ou largura/nível, ex.: 1500/-600")
        self.q_janela.addItem("Do arquivo", "")
        for k, (nome, w, lv) in sorted((settings.get("viewer.wl_presets", {}) or {}).items()):
            self.q_janela.addItem(f"{nome} (W {w} / L {lv})", str(k))
        self.q_cor = QComboBox()
        self.q_cor.addItem("Cinza", "")
        from ipe.imaging import colormaps as CM
        for k, v in CM.COLORMAPS.items():
            self.q_cor.addItem(v[0], k)
        self.q_pos = QComboBox()
        for k, v in POS_TXT.items():
            self.q_pos.addItem(v, k)
        self.q_sync = QSpinBox(minimum=0, maximum=9)
        self.q_sync.setSpecialValueText("Sozinho")
        self.q_sync.setToolTip("Quadros com o mesmo número rolam, ampliam e mudam de janela juntos")
        self.q_monitor = QComboBox()
        self.q_monitor.addItem("O programa reparte", 0)
        for k in (1, 2, 3, 4):
            self.q_monitor.addItem(f"Monitor {k}", k)
        self.q_monitor.setToolTip("Com o exame aberto em várias telas: em qual monitor este quadro fica")
        for w in (self.q_serie,):
            w.textEdited.connect(self._mudou_quadro)
        self.q_janela.lineEdit().textEdited.connect(self._mudou_quadro)
        for w in (self.q_plano, self.q_recon, self.q_janela, self.q_cor, self.q_pos, self.q_monitor,
                  self.q_fase, self.q_metade, self.q_vista):
            w.currentIndexChanged.connect(self._mudou_quadro)
        for w in (self.q_slab, self.q_sync):
            w.valueChanged.connect(self._mudou_quadro)
        self.q_prior.toggled.connect(self._mudou_quadro)
        form = QFormLayout()
        form.addRow("Série:", self.q_serie)
        form.addRow("", self.q_prior)
        form.addRow("Fase da dinâmica:", self.q_fase)
        form.addRow("Plano:", self.q_plano)
        linha = QHBoxLayout()
        linha.setContentsMargins(0, 0, 0, 0)          # sem a margem, a caixa não fica espremida
        linha.addWidget(self.q_recon, 1)
        linha.addWidget(QLabel("espessura"))
        linha.addWidget(self.q_slab)
        caixa = QWidget()
        caixa.setLayout(linha)
        form.addRow("Reconstrução:", caixa)
        form.addRow("Metade (meia mama):", self.q_metade)
        form.addRow("Vista:", self.q_vista)
        form.addRow("Janela:", self.q_janela)
        form.addRow("Cor:", self.q_cor)
        form.addRow("Posição:", self.q_pos)
        form.addRow("Sincronia (grupo):", self.q_sync)
        form.addRow("Com várias telas:", self.q_monitor)
        self.l_quadro = QLabel("<b>Quadro</b>")
        dir_ = QWidget()
        dl = QVBoxLayout(dir_)
        dl.setContentsMargins(6, 0, 0, 0)
        dl.addLayout(topo)
        dl.addLayout(linha_din)
        grade_host = QWidget()
        grade_host.setLayout(self.grade)
        grade_host.setMinimumHeight(140)
        self.grade_host = grade_host
        dl.addWidget(grade_host, 1)
        dl.addWidget(self.l_quadro)
        self.painel_quadro = QWidget()
        self.painel_quadro.setLayout(form)
        dl.addWidget(self.painel_quadro)
        self.painel_etapa = dir_

        div = QSplitter(Qt.Horizontal)
        div.addWidget(esq)
        div.addWidget(dir_)
        div.setStretchFactor(0, 1)
        div.setStretchFactor(1, 3)
        esq.setMaximumWidth(300)                  # a lista de etapas não precisa de meia tela
        g_etapas = QGroupBox("Etapas (← → no visualizador)")
        ge = QVBoxLayout(g_etapas)
        ge.addWidget(div)
        coluna_dir = QWidget()
        cd = QVBoxLayout(coluna_dir)
        cd.setContentsMargins(0, 0, 0, 0)
        cd.addWidget(g_proto)
        cd.addWidget(g_etapas, 1)
        corpo = QSplitter(Qt.Horizontal)
        corpo.addWidget(coluna_esq)
        corpo.addWidget(coluna_dir)
        corpo.setStretchFactor(0, 1)
        corpo.setStretchFactor(1, 4)
        corpo.setSizes([260, 900])
        lay = QVBoxLayout(self)
        lay.addWidget(dica)
        lay.addWidget(corpo, 1)
        self._encher_protocolos()
        if self.protos:
            self._selecionar(0)
        else:
            self._escolheu_protocolo()

    # ------------------------------------------------------------ protocolos
    def protocolos(self) -> list[dict]:
        return copy.deepcopy(self.protos)

    def _encher_protocolos(self) -> None:
        self._enchendo = True
        try:
            atual = self.l_protos.currentRow()
            self.l_protos.blockSignals(True)
            self.l_protos.clear()
            for p in self.protos:
                self.l_protos.addItem(self._rotulo(p))
            self.l_protos.blockSignals(False)
            if 0 <= atual < len(self.protos):
                self.l_protos.setCurrentRow(atual)
        finally:
            self._enchendo = False

    @staticmethod
    def _rotulo(p: dict) -> str:
        mod = (p.get("modality") or "").strip()
        texto = f"{p.get('name', '') or 'Protocolo'}" + (f"  ({mod})" if mod else "")
        return texto if p.get("enabled", True) else texto + " — desligado"

    def _selecionar(self, i: int) -> None:
        if 0 <= i < len(self.protos):
            self.l_protos.setCurrentRow(i)
            self._escolheu_protocolo()

    def _mostrar_protocolo(self) -> None:
        p = self.protos[self._pi] if 0 <= self._pi < len(self.protos) else None
        self._enchendo = True
        try:
            self.g_proto.setEnabled(p is not None)
            self.e_p_nome.setText(p.get("name", "") if p else "")
            self.e_p_mod.setText(p.get("modality", "") if p else "")
            self.e_p_desc.setText(p.get("description", "") if p else "")
            self.c_p_ativo.setChecked(bool(p.get("enabled", True)) if p else False)
            self.c_p_prior.setChecked(bool(p.get("prior", False)) if p else False)
        finally:
            self._enchendo = False

    def _mudou_protocolo(self, *_a) -> None:
        if self._enchendo or not 0 <= self._pi < len(self.protos):
            return
        p = self.protos[self._pi]
        p["name"] = self.e_p_nome.text().strip() or "Protocolo"
        p["modality"] = self.e_p_mod.text().strip().upper()
        p["description"] = self.e_p_desc.text().strip()
        p["enabled"] = self.c_p_ativo.isChecked()
        p["prior"] = self.c_p_prior.isChecked()
        it = self.l_protos.item(self._pi)
        if it is not None:
            it.setText(self._rotulo(p))
        self.l_titulo_etapas.setText(f"<b>Etapas de “{p['name']}”</b>")

    def _escolheu_protocolo(self) -> None:
        r = self.l_protos.currentRow()
        self._pi = r if 0 <= r < len(self.protos) else -1
        self._mostrar_protocolo()
        self._encher_etapas()

    def novo_protocolo(self) -> None:
        self.protos.append({"name": "Novo protocolo", "modality": "CT", "description": "", "enabled": True,
                            "prior": False, "steps": [H.etapa({"name": "Etapa 1", "rows": 1, "cols": 2})]})
        self._encher_protocolos()
        self._selecionar(len(self.protos) - 1)

    def duplicar_protocolo(self) -> None:
        if self._pi < 0:
            return
        c = copy.deepcopy(self.protos[self._pi])
        c["name"] = f"{c.get('name', '')} (cópia)"
        self.protos.insert(self._pi + 1, c)
        self._encher_protocolos()
        self._selecionar(self._pi + 1)

    def remover_protocolo(self) -> None:
        if self._pi < 0:
            return
        del self.protos[self._pi]
        self._encher_protocolos()
        if self.protos:
            self._selecionar(min(self._pi, len(self.protos) - 1))
        else:
            self._escolheu_protocolo()

    def mover_protocolo(self, d: int) -> None:
        i, j = self._pi, self._pi + d
        if not (0 <= i < len(self.protos) and 0 <= j < len(self.protos)):
            return
        self.protos[i], self.protos[j] = self.protos[j], self.protos[i]
        self._encher_protocolos()
        self._selecionar(j)

    def acrescentar_fabrica(self) -> None:
        nomes = {str(p.get("name", "")).lower() for p in self.protos}
        for p in H.DEFAULT_PROTOCOLS:
            if p["name"].lower() not in nomes:
                self.protos.append(H.convertido(copy.deepcopy(p)))
        self._encher_protocolos()

    # ------------------------------------------------------------ etapas
    def _passos(self) -> list:
        return self.protos[self._pi].setdefault("steps", []) if self._pi >= 0 else []

    def _encher_etapas(self, escolher: int = 0) -> None:
        self.l_etapas.blockSignals(True)
        self.l_etapas.clear()
        for k, st in enumerate(self._passos()):
            self.l_etapas.addItem(f"{k + 1}. {st.get('name', '')}")
        self.l_etapas.blockSignals(False)
        if self._pi >= 0:
            self.l_titulo_etapas.setText(f"<b>Etapas de “{self.protos[self._pi].get('name', '')}”</b>")
        passos = self._passos()
        if passos:
            self.l_etapas.setCurrentRow(max(0, min(escolher, len(passos) - 1)))
        else:
            self._escolheu_etapa(-1)

    def _escolheu_etapa(self, i: int) -> None:
        passos = self._passos()
        self._si = i if 0 <= i < len(passos) else -1
        self.painel_etapa.setEnabled(self._si >= 0)
        self._ci = 0
        self._mostrar_etapa()

    def _etapa(self) -> dict | None:
        passos = self._passos()
        return passos[self._si] if 0 <= self._si < len(passos) else None

    def _mostrar_etapa(self) -> None:
        st = self._etapa()
        self._enchendo = True
        try:
            if st is None:
                self.e_nome.setText("")
                self._desenhar_grade()
                return
            self.e_nome.setText(st.get("name", ""))
            self.e_rows.setValue(int(st.get("rows", 1)))
            self.e_cols.setValue(int(st.get("cols", 1)))
            din = st.get("dinamica") or {}
            self.e_din.setChecked(bool(din))
            if din:
                from ipe.ui.viewer import dinamica_config as DC
                lay = DC.escolher(self.settings, din.get("layout", 0), din.get("layout_nome", ""))
                self.e_din_layout.setCurrentIndex(max(0, self.e_din_layout.findText(lay["nome"])))
            else:
                self.e_din_layout.setCurrentIndex(0)
            serie = din.get("series", "") if din else ""
            self.e_din_serie.setText("" if serie == H.DINAMICA else serie)
        finally:
            self._enchendo = False
        self._desenhar_grade()
        self._habilitar_dinamica()

    def _desenhar_grade(self) -> None:
        for b in self.botoes_quadro:
            self.grade.removeWidget(b)
            b.hide()                      # deleteLater só apaga quando o laço de eventos voltar
            b.setParent(None)
            b.deleteLater()
        self.botoes_quadro = []
        st = self._etapa()
        if st is None:
            self._mostrar_quadro()
            return
        for k, q in enumerate(st["cells"]):
            r, c = divmod(k, int(st["cols"]))
            b = QPushButton(self._texto_quadro(k, q))
            b.setCheckable(True)
            b.setMinimumHeight(48)
            b.setStyleSheet("QPushButton{text-align:left;padding:4px}"
                            "QPushButton:checked{background:#35506e;color:white}")
            b.clicked.connect(lambda _=False, i=k: self._escolheu_quadro(i))
            self.grade.addWidget(b, r, c)
            self.botoes_quadro.append(b)
        self._ci = min(self._ci, len(st["cells"]) - 1)
        self._escolheu_quadro(self._ci)

    def _texto_quadro(self, k: int, q: dict) -> str:
        txt = H.descrever_quadro(q)
        jan = q.get("window", "")
        presets = self.settings.get("viewer.wl_presets", {}) or {}
        if jan and jan in presets:
            txt = txt.replace(f"janela {jan}", f"janela {presets[jan][0].lower()}")
        extra = []
        if q.get("sync"):
            extra.append(f"sinc. {q['sync']}")
        if q.get("monitor"):
            extra.append(f"monitor {q['monitor']}")
        return f"{k + 1}. " + txt.replace(" · ", "\n", 1) + (f"\n({', '.join(extra)})" if extra else "")

    def _mudou_etapa(self, *_a) -> None:
        st = self._etapa()
        if st is None or self._enchendo:
            return
        st["name"] = self.e_nome.text().strip() or "Etapa"
        it = self.l_etapas.item(self._si)
        if it is not None:
            it.setText(f"{self._si + 1}. {st['name']}")

    def _mudou_dinamica(self, *_a) -> None:
        st = self._etapa()
        if st is None or self._enchendo:
            return
        if self.e_din.isChecked():
            st["dinamica"] = {"layout": self.e_din_layout.currentIndex(),
                              "layout_nome": self.e_din_layout.currentText(),
                              "series": self.e_din_serie.text().strip() or H.DINAMICA}
        else:
            st.pop("dinamica", None)
        self._habilitar_dinamica()

    def _habilitar_dinamica(self) -> None:
        ligada = self.e_din.isChecked()
        for w in (self.e_din_layout, self.e_din_serie):
            w.setEnabled(ligada)
        # com a dinâmica, o layout e os quadros são os dos mapas: o desenho da etapa não vale
        for w in (self.e_rows, self.e_cols, self.grade_host, self.painel_quadro):
            w.setEnabled(not ligada)

    def _mudou_grade(self, *_a) -> None:
        st = self._etapa()
        if st is None or self._enchendo:
            return
        st["rows"], st["cols"] = self.e_rows.value(), self.e_cols.value()
        n = st["rows"] * st["cols"]
        st["cells"] = (st["cells"] + [H.quadro("") for _ in range(n)])[:n]
        self._desenhar_grade()

    def nova_etapa(self) -> None:
        if self._pi < 0:
            return
        passos = self._passos()
        passos.append(H.etapa({"name": f"Etapa {len(passos) + 1}", "rows": 1, "cols": 2}))
        self._encher_protocolos()
        self._selecionar(self._pi)
        self._encher_etapas(len(passos) - 1)

    def duplicar_etapa(self) -> None:
        st = self._etapa()
        if st is None:
            return
        c = copy.deepcopy(st)
        c["name"] = f"{c['name']} (cópia)"
        self._passos().insert(self._si + 1, c)
        self._encher_protocolos()
        self._selecionar(self._pi)
        self._encher_etapas(self._si + 1)

    def remover_etapa(self) -> None:
        if self._etapa() is None:
            return
        i = self._si
        del self._passos()[i]
        self._encher_protocolos()
        self._selecionar(self._pi)
        self._encher_etapas(max(0, i - 1))

    def mover_etapa(self, d: int) -> None:
        passos = self._passos()
        i, j = self._si, self._si + d
        if not (0 <= i < len(passos) and 0 <= j < len(passos)):
            return
        passos[i], passos[j] = passos[j], passos[i]
        self._encher_etapas(j)

    # ------------------------------------------------------------ quadro
    def _quadro(self) -> dict | None:
        st = self._etapa()
        if st is None or not 0 <= self._ci < len(st["cells"]):
            return None
        return st["cells"][self._ci]

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
            q = H.quadro(q or {})
            self.q_serie.setText(q["series"])
            self.q_prior.setChecked(q["prior"])
            self.q_plano.setCurrentIndex(max(0, self.q_plano.findData(q["plane"])))
            self.q_recon.setCurrentIndex(max(0, self.q_recon.findData(q["recon"])))
            self.q_slab.setValue(float(q["slab"] or 0))
            i = self.q_janela.findData(q["window"])
            if i >= 0:
                self.q_janela.setCurrentIndex(i)
            else:
                self.q_janela.setEditText(q["window"])
            self.q_cor.setCurrentIndex(max(0, self.q_cor.findData(q["cmap"])))
            self.q_pos.setCurrentIndex(max(0, self.q_pos.findData(q["pos"])))
            self.q_sync.setValue(int(q["sync"]))
            self.q_monitor.setCurrentIndex(max(0, self.q_monitor.findData(q["monitor"])))
            self.q_fase.setCurrentIndex(max(0, self.q_fase.findData(q["fase"])))
            self.q_metade.setCurrentIndex(max(0, self.q_metade.findData(q["metade"])))
            self.q_vista.setCurrentIndex(max(0, self.q_vista.findData(q["vista"])))
            self._habilitar(q)
        finally:
            self._enchendo = False

    def _janela_escolhida(self) -> str:
        texto = self.q_janela.currentText().strip()
        i = self.q_janela.findText(texto)
        if i >= 0:
            return str(self.q_janela.itemData(i) or "")
        return texto.replace(" ", "")

    def _mudou_quadro(self, *_a) -> None:
        if self._enchendo:
            return
        q = self._quadro()
        if q is None:
            return
        recon = self.q_recon.currentData() or ""
        metade = self.q_metade.currentData() or ""
        if metade and recon not in ("mip3d", "vr") and (self.q_plano.currentData() != "Sagital"
                                                        or recon not in ("mip", "minip", "avg")):
            self._enchendo = True                # meia mama: o 3D da metade, ou MIP sagital de espessura
            if recon not in ("mip", "minip", "avg"):
                self.q_recon.setCurrentIndex(self.q_recon.findData("mip3d"))
                recon = "mip3d"
            else:
                self.q_plano.setCurrentIndex(self.q_plano.findData("Sagital"))
            self._enchendo = False
        if recon not in SEM_ESPESSURA and not self.q_slab.value():
            self._enchendo = True
            self.q_slab.setValue(10)            # MIP sem espessura não é MIP
            self._enchendo = False
        q.update(H.quadro({"series": self.q_serie.text().strip(), "prior": self.q_prior.isChecked(),
                           "plane": self.q_plano.currentData() or "", "recon": recon,
                           "slab": self.q_slab.value() if recon not in SEM_ESPESSURA else 0,
                           "window": self._janela_escolhida(),
                           "cmap": self.q_cor.currentData() or "", "pos": self.q_pos.currentData() or "auto",
                           "sync": self.q_sync.value(), "monitor": self.q_monitor.currentData() or 0,
                           "fase": self.q_fase.currentData() or "", "metade": metade,
                           "vista": self.q_vista.currentData() or ""}))
        self._habilitar(q)
        if 0 <= self._ci < len(self.botoes_quadro):
            self.botoes_quadro[self._ci].setText(self._texto_quadro(self._ci, q))


    def _habilitar(self, q: dict) -> None:
        tres_d = q["recon"] in ("mip3d", "vr")
        self.q_slab.setEnabled(q["recon"] not in SEM_ESPESSURA and not q["metade"])
        self.q_slab.setToolTip("Com meia mama a espessura é a da metade inteira" if q["metade"]
                               else "Espessura do MIP/MinIP/média")
        self.q_plano.setEnabled(not q["metade"] and not tres_d)
        self.q_pos.setEnabled(not q["metade"] and not tres_d)


class ProtocolosDialog(QDialog):
    """O mesmo editor numa janela (aberto pela barra do protocolo no visualizador)."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Protocolos de exibição")
        self.resize(1000, 700)
        self.settings = settings
        self.editor = ProtocolosEditor(settings, self)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.editor, 1)
        lay.addWidget(bb)

    def _ok(self) -> None:
        self.settings.set("hanging_protocols", self.editor.protocolos())
        self.settings.save()
        self.accept()
