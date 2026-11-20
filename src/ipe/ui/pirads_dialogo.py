"""0.100.79: a janela PI-RADS do Ipê de mesa (botão **PI-RADS** do visualizador, na RM de próstata).

Volume (elipsoide pelos três diâmetros ou a segmentação automática) e densidade do PSA; as lesões, cada uma com a
zona, os setores (clique no mapa ou na lista), o tamanho, as pontuações, o DCE, o ADC (da ROI do quadro), a
extensão extraprostática e a imagem ligada; a categoria de cada uma e a geral, pelas regras de
`reporting/pirads.py`. Guarda sozinho; "Gravar no exame" grava o SR e o mapa; "Mandar ao laudo" põe o texto no laudo.

O que veio de um modelo de pesquisa (volume das zonas, lesões sugeridas) aparece com a faixa vermelha
"modelo de pesquisa — não usar para diagnóstico", e cada lesão sugerida fica "a conferir" até o médico marcar.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
    QRadioButton, QSizePolicy, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ipe.reporting import pirads as P

log = logging.getLogger(__name__)

PONTOS = [("—", None), ("1", 1), ("2", 2), ("3", 3), ("4", 4), ("5", 5)]
NIVEIS = {"base": "base", "medio": "terço médio", "apice": "ápice"}
_PESQUISA_CSS = "background:#b71c1c;color:white;padding:6px;border-radius:4px;font-weight:bold"


def _data_br(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if len(iso or "") == 10 else ""


def _data_iso(br: str) -> str:
    p = (br or "").strip().replace("-", "/").split("/")
    if len(p) == 3 and all(x.isdigit() for x in p) and len(p[2]) == 4:
        return f"{p[2]}-{int(p[1]):02d}-{int(p[0]):02d}"
    return ""


def adc_em_micro(v: float | None) -> float | None:
    """O ADC na unidade do PI-RADS (× 10⁻⁶ mm²/s): mapas em mm²/s (0,0008) ou em × 10⁻³ (0,8) são convertidos."""
    if v is None or v <= 0:
        return None
    if v < 0.01:
        return round(v * 1e6)
    if v < 10:
        return round(v * 1e3)
    return round(v)


class MapaSetores(QWidget):
    """O mapa de setores da próstata (o modelo do esquema): pinta as categorias, destaca os setores da lesão
    escolhida e o clique liga ou desliga um setor dela."""
    clicado = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        from ipe.reporting import esquemas as E
        self.mod = E.modelo(P.MODELO_ESQUEMA) or {}
        self.esquema: dict = {"marcas": [], "setores": {}}
        self.destaque: set[str] = set()
        self.setMinimumSize(220, 290)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Clique num setor para pôr ou tirar da lesão escolhida")

    def quadro(self) -> QRectF:
        if not self.mod:
            return QRectF()
        k = min(self.width() / self.mod["w"], self.height() / self.mod["h"])
        w, h = self.mod["w"] * k, self.mod["h"] * k
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def paintEvent(self, _e) -> None:  # noqa: N802
        if not self.mod:
            return
        from ipe.ui.esquema_dialogo import pintar
        p = QPainter(self)
        q = self.quadro()
        p.translate(q.topLeft())
        pintar(p, self.mod, self.esquema, q.width(), q.height())
        esc = q.width() / self.mod["w"]
        p.setPen(QPen(QColor("#1565c0"), 3))
        p.setBrush(Qt.NoBrush)
        from PySide6.QtGui import QPolygonF
        for s in self.mod.get("setores") or []:
            if s["id"] in self.destaque:
                p.drawPolygon(QPolygonF([QPointF(x * esc, y * esc) for x, y in s["p"]]))
        p.end()

    def mousePressEvent(self, ev) -> None:  # noqa: N802
        from ipe.ui.esquema_dialogo import _dentro
        q = self.quadro()
        if not q.contains(ev.position()):
            return
        esc = q.width() / self.mod["w"]
        x, y = (ev.position().x() - q.x()) / esc, (ev.position().y() - q.y()) / esc
        for s in self.mod.get("setores") or []:
            if P.zona_do_setor(s["id"]) and _dentro(s["p"], x, y):
                self.clicado.emit(s["id"])
                return


class PiradsDialog(QDialog):
    gravado = Signal(str)

    def __init__(self, repo, study_uid: str, usuario: str = "", pode: bool = True, tab=None, storage_root=None,
                 parent=None):
        super().__init__(parent)
        self.repo, self.study, self.usuario, self.pode, self.tab = repo, study_uid, usuario, pode, tab
        self.storage = storage_root
        self.setWindowTitle("PI-RADS — RM de próstata")
        self.resize(1180, 780)
        self.d = P.ler(repo, study_uid) or P.normalizar({})
        self.atual = 0 if self.d["lesoes"] else -1
        self._enchendo = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(700)
        self._timer.timeout.connect(self.salvar)
        self._montar()
        self._encher_tudo()

    # ------------------------------------------------------------------ montagem
    def _montar(self) -> None:
        lay = QVBoxLayout(self)
        self.faixa = QLabel(f"Atenção: há dados de um {P.MARCA_PESQUISA}.")
        self.faixa.setStyleSheet(_PESQUISA_CSS)
        self.faixa.setWordWrap(True)
        lay.addWidget(self.faixa)

        # ---- glândula e PSA
        g = QGroupBox("Glândula e PSA")
        gl = QGridLayout(g)
        self.psa = QDoubleSpinBox()
        self.psa.setRange(-0.01, 10000)
        self.psa.setDecimals(2)
        self.psa.setSpecialValueText("—")
        self.psa.setValue(-0.01)
        self.psa.setSuffix(" ng/mL")
        self.psa_data = QLineEdit()
        self.psa_data.setPlaceholderText("dd/mm/aaaa")
        self.psa_data.setMaximumWidth(110)
        gl.addWidget(QLabel("PSA:"), 0, 0)
        gl.addWidget(self.psa, 0, 1)
        gl.addWidget(QLabel("de"), 0, 2)
        gl.addWidget(self.psa_data, 0, 3)
        self.diam = []
        for i, nome in enumerate(("AP", "Transverso", "Craniocaudal")):
            s = QDoubleSpinBox()
            s.setRange(0, 200)
            s.setDecimals(1)
            s.setSpecialValueText("—")
            s.setSuffix(" mm")
            self.diam.append(s)
            gl.addWidget(QLabel(nome + ":"), 1, i * 2)
            gl.addWidget(s, 1, i * 2 + 1)
        b_med = QPushButton("Pegar das réguas")
        b_med.setToolTip("Usa as três últimas réguas desenhadas neste exame, na ordem: AP, transverso e craniocaudal")
        b_med.clicked.connect(self._das_reguas)
        gl.addWidget(b_med, 1, 6)
        self.r_elip = QRadioButton("Elipsoide (0,52 × AP × T × CC)")
        self.r_auto = QRadioButton("Segmentação automática")
        self.l_auto = QLabel()
        b_auto = QPushButton("Volume automático (IA)…")
        b_auto.setToolTip("Segmenta a próstata com o TotalSegmentator na série T2 axial e traz o volume para cá")
        b_auto.clicked.connect(self._volume_auto)
        gl.addWidget(QLabel("Volume:"), 2, 0)
        gl.addWidget(self.r_elip, 2, 1, 1, 2)
        gl.addWidget(self.r_auto, 2, 3, 1, 2)
        gl.addWidget(self.l_auto, 2, 5)
        gl.addWidget(b_auto, 2, 6)
        self.l_volume = QLabel()
        self.l_volume.setStyleSheet("font-weight:bold")
        self.l_volume.setToolTip("Densidade do PSA = PSA ÷ volume. Valores a partir de 0,15 ng/mL/cm³ costumam ser "
                                 "considerados elevados (confira a referência do seu serviço).")
        gl.addWidget(self.l_volume, 3, 0, 1, 7)
        self.biparam = QCheckBox("Biparamétrica (sem DCE)")
        self.hemorragia = QCheckBox("Hemorragia pós-biópsia")
        self.qualidade = QLineEdit()
        self.qualidade.setPlaceholderText("Qualidade (ex.: adequada; limitada por artefato de gás retal)")
        gl.addWidget(self.biparam, 4, 0, 1, 2)
        gl.addWidget(self.hemorragia, 4, 2, 1, 2)
        gl.addWidget(self.qualidade, 4, 4, 1, 3)
        lay.addWidget(g)

        # ---- lesões: tabela + editor + mapa
        corpo = QSplitter(Qt.Horizontal)
        esq = QWidget()
        el = QVBoxLayout(esq)
        el.setContentsMargins(0, 0, 0, 0)
        self.tabela = QTableWidget(0, 8)
        self.tabela.setHorizontalHeaderLabels(["Nº", "Localização", "mm", "T2", "DWI", "DCE", "ADC", "PI-RADS"])
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.horizontalHeader().setStretchLastSection(False)
        self.tabela.setColumnWidth(0, 34)
        self.tabela.setColumnWidth(1, 250)
        for c in range(2, 8):
            self.tabela.setColumnWidth(c, 52)
        from ipe.ui.tabelas import colunas_ajustaveis
        colunas_ajustaveis(self.tabela)
        self.tabela.itemSelectionChanged.connect(self._escolheu)
        el.addWidget(self.tabela, 1)
        bl = QHBoxLayout()
        self.b_nova = QPushButton("Nova lesão")
        self.b_nova.clicked.connect(self._nova)
        self.b_excluir = QPushButton("Excluir lesão")
        self.b_excluir.clicked.connect(self._excluir)
        self.b_ia = QPushButton("Sugestões do modelo de pesquisa…")
        self.b_ia.setToolTip("Detecção de lesões pelo modelo do PI-CAI (pesquisa e ensino, não clínico): instalado à "
                             "parte, com a licença aceita. As sugestões entram como lesões a conferir.")
        self.b_ia.clicked.connect(self._sugestoes)
        bl.addWidget(self.b_nova)
        bl.addWidget(self.b_excluir)
        bl.addStretch(1)
        bl.addWidget(self.b_ia)
        el.addLayout(bl)

        # editor da lesão
        self.editor = QGroupBox("Lesão")
        f = QFormLayout(self.editor)
        self.zona = QComboBox()
        self.zona.addItem("—", "")
        for k, v in P.ZONAS.items():
            self.zona.addItem(v, k)
        f.addRow("Zona:", self.zona)
        self.lista_setores = QListWidget()
        self.lista_setores.setMaximumHeight(120)
        f.addRow("Setores:", self.lista_setores)
        self.tam = QDoubleSpinBox()
        self.tam.setRange(0, 200)
        self.tam.setDecimals(1)
        self.tam.setSuffix(" mm")
        self.tam.setSpecialValueText("—")
        f.addRow("Maior diâmetro:", self.tam)
        linha = QHBoxLayout()
        self.t2, self.dwi = QComboBox(), QComboBox()
        for cb in (self.t2, self.dwi):
            for t, v in PONTOS:
                cb.addItem(t, v)
        self.dce = QComboBox()
        for k in ("", "-", "+"):
            self.dce.addItem(P.DCE[k], k)
        linha.addWidget(QLabel("T2"))
        linha.addWidget(self.t2)
        linha.addWidget(QLabel("Difusão"))
        linha.addWidget(self.dwi)
        linha.addWidget(QLabel("DCE"))
        linha.addWidget(self.dce)
        linha.addStretch(1)
        f.addRow("Pontuação:", linha)
        la = QHBoxLayout()
        self.adc = QDoubleSpinBox()
        self.adc.setRange(0, 5000)
        self.adc.setDecimals(0)
        self.adc.setSpecialValueText("—")
        self.adc.setSuffix(" × 10⁻⁶ mm²/s")
        b_adc = QPushButton("Da ROI do quadro")
        b_adc.setToolTip("A média da ROI escolhida (ou da última) na imagem do quadro ativo — de preferência no mapa "
                         "ADC")
        b_adc.clicked.connect(self._adc_da_roi)
        b_dce = QPushButton("Curva DCE…")
        b_dce.setToolTip("Abre a dinâmica (curva tempo-intensidade) no quadro ativo; as curvas medidas entram no "
                         "laudo pelo campo {curva}")
        b_dce.clicked.connect(self._curva_dce)
        la.addWidget(self.adc)
        la.addWidget(b_adc)
        la.addWidget(b_dce)
        f.addRow("ADC:", la)
        self.epe = QComboBox()
        self.epe.addItem("—", "")
        for k in ("nao", "suspeita", "sim"):
            self.epe.addItem(P.EPE[k], k)
        f.addRow("Extensão extraprostática:", self.epe)
        self.descricao = QLineEdit()
        self.descricao.setPlaceholderText("Descrição (ex.: área lenticular com hipossinal em T2)")
        f.addRow("Descrição:", self.descricao)
        lm = QHBoxLayout()
        self.manual = QComboBox()
        self.manual.addItem("pela regra", "")
        for k in P.CATEGORIAS:
            self.manual.addItem(f"PI-RADS {k}", k)
        self.l_cat = QLabel()
        self.l_cat.setStyleSheet("font-weight:bold")
        lm.addWidget(self.manual)
        lm.addWidget(self.l_cat, 1)
        f.addRow("Categoria:", lm)
        self.l_avisos = QLabel()
        self.l_avisos.setWordWrap(True)
        self.l_avisos.setStyleSheet("color:#b26a00")
        f.addRow("", self.l_avisos)
        li = QHBoxLayout()
        b_img = QPushButton("Ligar à imagem do quadro")
        b_img.clicked.connect(self._ligar_imagem)
        self.l_img = QLabel()
        li.addWidget(b_img)
        li.addWidget(self.l_img, 1)
        f.addRow("Imagem:", li)
        self.conferida = QCheckBox("Conferida pelo médico (sugestão do modelo de pesquisa)")
        f.addRow("", self.conferida)
        el.addWidget(self.editor)
        corpo.addWidget(esq)
        self.mapa = MapaSetores()
        self.mapa.clicado.connect(self._setor_clicado)
        corpo.addWidget(self.mapa)
        corpo.setStretchFactor(0, 3)
        corpo.setStretchFactor(1, 2)
        lay.addWidget(corpo, 1)

        # ---- geral e botões
        self.outros = QPlainTextEdit()
        self.outros.setPlaceholderText("Outros achados (vesículas seminais, feixes neurovasculares, linfonodos, ossos…)")
        self.outros.setMaximumHeight(60)
        lay.addWidget(self.outros)
        bx = QHBoxLayout()
        self.l_geral = QLabel()
        self.l_geral.setStyleSheet("font-size:15px;font-weight:bold")
        self.geral_manual = QComboBox()
        self.geral_manual.addItem("Geral pela maior categoria", "")
        for k in P.CATEGORIAS:
            self.geral_manual.addItem(f"Geral: PI-RADS {k}", k)
        self.l_status = QLabel()
        self.l_status.setStyleSheet("color:#777")
        b_exame = QPushButton("Gravar no exame (SR e mapa)")
        b_exame.setToolTip("Grava o SR do PI-RADS e a figura do mapa de setores no exame agora, sem precisar "
                           "assinar o laudo. Gravar de novo troca o que havia.")
        b_exame.clicked.connect(self._no_exame)
        b_laudo = QPushButton("Mandar ao laudo")
        b_laudo.clicked.connect(self._ao_laudo)
        b_fechar = QPushButton("Fechar")
        b_fechar.clicked.connect(self.close)
        bx.addWidget(self.l_geral)
        bx.addWidget(self.geral_manual)
        bx.addWidget(self.l_status, 1)
        bx.addWidget(b_exame)
        bx.addWidget(b_laudo)
        bx.addWidget(b_fechar)
        lay.addLayout(bx)
        self.b_exame, self.b_laudo = b_exame, b_laudo

        # mudanças
        for w in (self.psa, self.tam, self.adc, *self.diam):
            w.valueChanged.connect(self._mudou)
        for w in (self.psa_data, self.qualidade, self.descricao):
            w.textEdited.connect(self._mudou)
        for w in (self.zona, self.t2, self.dwi, self.dce, self.epe, self.manual, self.geral_manual):
            w.currentIndexChanged.connect(self._mudou)
        for w in (self.biparam, self.hemorragia, self.conferida, self.r_elip, self.r_auto):
            w.toggled.connect(self._mudou)
        self.outros.textChanged.connect(self._mudou)
        self.zona.currentIndexChanged.connect(self._encher_setores)
        self.lista_setores.itemChanged.connect(self._mudou)
        if not self.pode:
            for w in self.findChildren(QWidget):
                if isinstance(w, (QDoubleSpinBox, QLineEdit, QComboBox, QCheckBox, QRadioButton, QPlainTextEdit,
                                  QPushButton)) and w is not b_fechar:
                    w.setEnabled(False)

    # ------------------------------------------------------------------ tela ← estado
    def _encher_tudo(self) -> None:
        self._enchendo = True
        d = self.d
        self.psa.setValue(d["psa"] if d["psa"] is not None else -0.01)
        self.psa_data.setText(_data_br(d["psa_data"]))
        for s, v in zip(self.diam, d["diametros"] or [0, 0, 0]):
            s.setValue(v or 0)
        auto = d.get("volume_auto")
        self.r_auto.setEnabled(bool(auto))
        (self.r_auto if auto and d["volume_usar"] != "elipsoide" else self.r_elip).setChecked(True)
        self.biparam.setChecked(d["biparametrico"])
        self.hemorragia.setChecked(d["hemorragia"])
        self.qualidade.setText(d["qualidade"])
        self.outros.setPlainText(d["outros"])
        self.geral_manual.setCurrentIndex(max(0, self.geral_manual.findData(d.get("geral_manual") or "")))
        self._enchendo = False
        self._encher_lesao()
        self._recalcular()

    def _encher_setores(self) -> None:
        sel = set(self._lesao().get("setores") or []) if self._lesao() else set()
        zona = self.zona.currentData() or ""
        was = self._enchendo
        self._enchendo = True
        self.lista_setores.clear()
        for s in P.setores():
            if zona and s["zona"] != zona and s["id"] not in sel:
                continue
            it = QListWidgetItem(s["nome"])
            it.setData(Qt.UserRole, s["id"])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if s["id"] in sel else Qt.Unchecked)
            self.lista_setores.addItem(it)
        self._enchendo = was

    def _lesao(self) -> dict | None:
        return self.d["lesoes"][self.atual] if 0 <= self.atual < len(self.d["lesoes"]) else None

    def _encher_lesao(self) -> None:
        l = self._lesao()
        self.editor.setEnabled(l is not None and self.pode)
        self.b_excluir.setEnabled(l is not None and self.pode)
        self._enchendo = True
        l = l or {}
        self.editor.setTitle(f"Lesão {l.get('n', '')}" if l else "Lesão (escolha ou crie uma)")
        self.zona.setCurrentIndex(max(0, self.zona.findData(l.get("zona") or "")))
        self.tam.setValue(l.get("tamanho_mm") or 0)
        self.t2.setCurrentIndex(max(0, self.t2.findData(l.get("t2"))))
        self.dwi.setCurrentIndex(max(0, self.dwi.findData(l.get("dwi"))))
        self.dce.setCurrentIndex(max(0, self.dce.findData(l.get("dce") or "")))
        self.adc.setValue(l.get("adc") or 0)
        self.epe.setCurrentIndex(max(0, self.epe.findData(l.get("epe") or "")))
        self.descricao.setText(l.get("descricao") or "")
        self.manual.setCurrentIndex(max(0, self.manual.findData(l.get("categoria_manual") or "")))
        self.l_img.setText((l.get("imagem") or {}).get("rotulo") or "—")
        self.conferida.setVisible(bool(l.get("pesquisa")))
        self.conferida.setChecked(bool(l.get("conferida")))
        self._enchendo = False
        self._encher_setores()

    # ------------------------------------------------------------------ estado ← tela
    def _ler_tela(self) -> None:
        d = self.d
        d["psa"] = self.psa.value() if self.psa.value() >= 0 else None
        d["psa_data"] = _data_iso(self.psa_data.text())
        dd = [s.value() for s in self.diam]
        d["diametros"] = dd if any(dd) else []
        if self.r_auto.isEnabled():                      # sem segmentação, a escolha fica em aberto
            d["volume_usar"] = "auto" if self.r_auto.isChecked() else "elipsoide"
        d["biparametrico"] = self.biparam.isChecked()
        d["hemorragia"] = self.hemorragia.isChecked()
        d["qualidade"] = self.qualidade.text()
        d["outros"] = self.outros.toPlainText()
        d["geral_manual"] = self.geral_manual.currentData() or ""
        l = self._lesao()
        if l is not None:
            marcados = [self.lista_setores.item(i).data(Qt.UserRole) for i in range(self.lista_setores.count())
                        if self.lista_setores.item(i).checkState() == Qt.Checked]
            visiveis = {self.lista_setores.item(i).data(Qt.UserRole) for i in range(self.lista_setores.count())}
            antigos = list(l.get("setores") or [])
            l["setores"] = [s for s in antigos if s not in visiveis or s in marcados] + \
                [s for s in marcados if s not in antigos]
            l.update({"zona": self.zona.currentData() or "", "tamanho_mm": self.tam.value() or None,
                      "t2": self.t2.currentData(), "dwi": self.dwi.currentData(), "dce": self.dce.currentData() or "",
                      "adc": self.adc.value() or None, "epe": self.epe.currentData() or "",
                      "descricao": self.descricao.text(), "categoria_manual": self.manual.currentData() or ""})
            if l.get("pesquisa"):
                l["conferida"] = self.conferida.isChecked()
        self.d = P.normalizar(d)

    def _mudou(self, *_a) -> None:
        if self._enchendo:
            return
        self._ler_tela()
        self._recalcular()
        if self.pode:
            self.l_status.setText("…")
            self._timer.start()

    def _recalcular(self) -> None:
        c = P.calcular(self.d)
        self.c = c
        v = c["volume_ml"]
        txt = f"Volume: {P._f(v)} mL ({c['volume_fonte']})" if v else "Volume: —"
        txt += f"   ·   Densidade do PSA: {P._f(c['psad'], 2)} ng/mL/cm³" if c["psad"] is not None else ""
        self.l_volume.setText(txt)
        auto = c.get("volume_auto")
        self.l_auto.setText(f"{P._f(auto['ml'])} mL ({auto['fonte']})" if auto else "")
        self.faixa.setVisible(bool(c["pesquisa"]))
        if c["pesquisa"] and c["a_conferir"]:
            self.faixa.setText(f"Atenção: há dados de um {P.MARCA_PESQUISA}. {c['a_conferir']} lesão(ões) sugerida(s) "
                               "ainda a conferir.")
        elif c["pesquisa"]:
            self.faixa.setText(f"Atenção: há dados de um {P.MARCA_PESQUISA}.")
        self.tabela.blockSignals(True)
        self.tabela.setRowCount(len(c["lesoes"]))
        for i, l in enumerate(c["lesoes"]):
            vals = [str(l["n"]), P.onde(l), P._mm(l["tamanho_mm"]) if l["tamanho_mm"] else "—",
                    str(l["t2"] or "—"), str(l["dwi"] or "—"), {"+": "+", "-": "−", "": "—"}[l["dce"]],
                    P._f(l["adc"], 0) if l["adc"] else "—", l["categoria"] or "?"]
            for col, t in enumerate(vals):
                it = QTableWidgetItem(t)
                if col == 7 and l["categoria"]:
                    it.setBackground(QColor(P.CORES[l["categoria"]]))
                    it.setForeground(QColor("white"))
                if l["pesquisa"] and not l["conferida"]:
                    it.setToolTip(f"Sugerida por {P.MARCA_PESQUISA} — a conferir")
                    if col == 1:
                        it.setText("⚠ " + t)
                self.tabela.setItem(i, col, it)
        if 0 <= self.atual < len(c["lesoes"]):
            self.tabela.selectRow(self.atual)
        self.tabela.blockSignals(False)
        l = c["lesoes"][self.atual] if 0 <= self.atual < len(c["lesoes"]) else None
        self.l_cat.setText(f"PI-RADS {l['categoria']}" if l and l["categoria"] else "—")
        self.l_avisos.setText("; ".join(l["avisos"]) if l else "")
        self.l_geral.setText(f"PI-RADS geral: {c['geral']}" if c["geral"] else "PI-RADS geral: —")
        self.mapa.esquema = P.esquema(c)
        self.mapa.destaque = set(l["setores"]) if l else set()
        self.mapa.update()

    # ------------------------------------------------------------------ ações
    def salvar(self) -> bool:
        if not self.pode:
            return False
        try:
            P.gravar(self.repo, self.study, self.d, self.usuario)
            self.l_status.setText("Salvo.")
            self.gravado.emit(self.study)
            return True
        except Exception as e:  # noqa: BLE001
            log.exception("pirads: salvar")
            self.l_status.setText(f"Não salvou: {e}")
            return False

    def _escolheu(self) -> None:
        linhas = {i.row() for i in self.tabela.selectedIndexes()}
        if not linhas:
            return
        self.atual = min(linhas)
        self._encher_lesao()
        self._recalcular()

    def _nova(self) -> None:
        self._ler_tela()
        self.d["lesoes"].append({"zona": "", "setores": [], "origem": "medico", "conferida": True})
        self.d = P.normalizar(self.d)
        self.atual = len(self.d["lesoes"]) - 1
        self._encher_lesao()
        self._mudou()

    def _excluir(self) -> None:
        if self._lesao() is None:
            return
        del self.d["lesoes"][self.atual]
        self.d = P.normalizar(self.d)
        self.atual = min(self.atual, len(self.d["lesoes"]) - 1)
        self._encher_lesao()
        self._recalcular()
        if self.pode:
            self._timer.start()

    def _setor_clicado(self, sid: str) -> None:
        if not self.pode:
            return
        self._ler_tela()
        if self._lesao() is None:                            # sem lesão escolhida: o clique cria uma no setor
            self.d["lesoes"].append({"zona": "", "setores": [], "origem": "medico", "conferida": True})
            self.d = P.normalizar(self.d)
            self.atual = len(self.d["lesoes"]) - 1
        l = self._lesao()
        sets = list(l.get("setores") or [])
        if sid in sets:
            sets.remove(sid)
        else:
            sets.append(sid)
        l["setores"] = sets
        if not l.get("zona"):
            l["zona"] = P.zona_do_setor(sid)
        self.d = P.normalizar(self.d)
        self._encher_lesao()
        self._recalcular()
        if self.pode:
            self._timer.start()

    def _das_reguas(self) -> None:
        from ipe.imaging import measure as M
        try:
            rows = [r for r in self.repo.annotations_for_studies([self.study]) if r.get("kind") == "line"
                    and not M.e_rascunho(r)]
        except Exception:  # noqa: BLE001
            rows = []
        rows.sort(key=lambda r: r.get("id") or 0)
        mms = []
        for r in rows[-3:]:
            a = M.Annotation.from_record(r)
            mm = (a.meta or {}).get("mm")
            if mm is None and len(a.points) >= 2:
                from ipe.reporting.fill import _spacings
                sp = _spacings(self.repo, [a.frame_key[0]]).get(a.frame_key[0])
                mm = M.length_mm(a.points[0], a.points[1], sp)
            if mm:
                mms.append(float(mm))
        if len(mms) < 3:
            QMessageBox.information(self, "PI-RADS", "Desenhe as três réguas da próstata (AP e transverso no axial, "
                                                     "craniocaudal no sagital) e tente de novo.")
            return
        for s, v in zip(self.diam, mms):
            s.setValue(round(v, 1))
        self.r_elip.setChecked(True)

    def _volume_auto(self) -> None:
        if self.tab is None or not hasattr(self.tab, "ferramenta_ia"):
            QMessageBox.information(self, "PI-RADS", "Abra o exame no visualizador para rodar a segmentação.")
            return
        self.salvar()
        self.tab.ferramenta_ia("prostata", None)
        self.l_status.setText("Segmentando a próstata… o volume entra aqui quando terminar.")

    def _sugestoes(self) -> None:
        if self.tab is None or not hasattr(self.tab, "ferramenta_ia"):
            QMessageBox.information(self, "PI-RADS", "Abra o exame no visualizador para rodar o modelo.")
            return
        self.salvar()
        self.tab.ferramenta_ia("picai", None)
        self.l_status.setText("Rodando o modelo de pesquisa… as sugestões entram aqui quando terminar.")

    def recarregar(self) -> None:
        """A IA terminou (volume ou sugestões): lê de novo do banco, mantendo a lesão escolhida."""
        self.d = P.ler(self.repo, self.study) or self.d
        self.atual = min(max(self.atual, 0 if self.d["lesoes"] else -1), len(self.d["lesoes"]) - 1)
        self._encher_tudo()
        self.l_status.setText("Atualizado com o resultado da IA.")

    def _vp(self):
        t = self.tab
        return getattr(t, "active", None) or next(iter(getattr(t, "viewports", []) or []), None) if t else None

    def _adc_da_roi(self) -> None:
        from ipe.imaging import measure as M
        vp = self._vp()
        img = getattr(vp, "_img", None) if vp is not None else None
        if vp is None or img is None or getattr(img, "is_color", False):
            QMessageBox.information(self, "PI-RADS", "Abra o mapa ADC num quadro e desenhe uma ROI na lesão.")
            return
        roi = vp.selected if getattr(vp, "selected", None) is not None and vp.selected.kind in M.ROI_KINDS else None
        if roi is None:
            chave = vp.frame_key() if hasattr(vp, "frame_key") else None
            rois = [a for a in getattr(vp, "annotations", []) if a.kind in M.ROI_KINDS and a.frame_key == chave]
            roi = rois[-1] if rois else None
        if roi is None:
            QMessageBox.information(self, "PI-RADS", "Não há ROI nesta imagem: desenhe uma elipse na lesão, no mapa ADC.")
            return
        media = M.media_da_roi(roi, img.pixels, vp.measure_spacing(roi) if hasattr(vp, "measure_spacing") else None)
        v = adc_em_micro(media)
        if v is None:
            QMessageBox.information(self, "PI-RADS", "A ROI não tem valores para o ADC.")
            return
        self.adc.setValue(v)
        desc = ""
        try:
            linha = self.tab._series_row(vp.series_uid) if hasattr(self.tab, "_series_row") else None
            desc = (linha.description or "") if linha is not None else ""
        except Exception:  # noqa: BLE001
            pass
        if desc and "ADC" not in desc.upper():
            self.l_status.setText(f"Atenção: a série do quadro (“{desc}”) não parece ser um mapa ADC.")

    def _curva_dce(self) -> None:
        if self.tab is not None and hasattr(self.tab, "open_dynamic"):
            try:
                self.tab.open_dynamic()
                return
            except Exception:  # noqa: BLE001
                log.debug("pirads: dinâmica", exc_info=True)
        QMessageBox.information(self, "PI-RADS", "Use o botão Dinâmica do visualizador na série DCE e desenhe a ROI "
                                                 "na lesão; a curva entra no laudo pelo campo {curva}.")

    def _ligar_imagem(self) -> None:
        l = self._lesao()
        if l is None or self.tab is None:
            return
        from ipe.reporting import esquemas as E
        from ipe.ui.esquema_dialogo import imagem_do_quadro
        r = imagem_do_quadro(self.tab, self.study)
        im = E.ligar_imagem(self.repo, self.study, *r) if r else None
        if not im:
            QMessageBox.information(self, "PI-RADS", "A imagem do quadro ativo não é deste exame.")
            return
        self._ler_tela()
        self._lesao()["imagem"] = im
        self.d = P.normalizar(self.d)
        self._encher_lesao()
        self._mudou()

    def _no_exame(self) -> None:
        self._ler_tela()
        if not self.salvar():
            return
        if self.storage is None:
            QMessageBox.information(self, "PI-RADS", "Sem a pasta das imagens não dá para gravar no exame.")
            return
        from ipe.reporting import pirads_saida as PS
        try:
            r = PS.gravar_no_exame(self.repo, self.storage, self.study, self.usuario)
        except Exception as e:  # noqa: BLE001
            log.exception("pirads: gravar no exame")
            QMessageBox.warning(self, "PI-RADS", f"Não deu para gravar no exame: {e}")
            return
        self.l_status.setText("Gravado no exame: o SR do PI-RADS" + (" e o mapa de setores." if r["esquemas"] else "."))

    def _ao_laudo(self) -> None:
        self._ler_tela()
        self.salvar()
        texto = P.texto_laudo(self.d)
        par = self.tab
        if par is not None and hasattr(par, "append_to_report") and par.append_to_report(texto, self.study):
            self.l_status.setText("Texto do PI-RADS mandado ao laudo.")
            return
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(texto)
        self.l_status.setText("O laudo não abriu: o texto foi copiado (Ctrl+V).")

    def closeEvent(self, e) -> None:  # noqa: N802
        if self._timer.isActive():
            self._timer.stop()
            self.salvar()
        super().closeEvent(e)


def abrir(tab, study_uid: str, repo, usuario: str = "", pode: bool = True, storage_root=None) -> PiradsDialog:
    janelas = tab.__dict__.setdefault("_janelas_pirads", {})
    w = janelas.get(study_uid)
    if w is not None and w.isVisible():
        w.raise_()
        w.activateWindow()
        return w
    w = PiradsDialog(repo, study_uid, usuario, pode, tab, storage_root, tab)
    janelas[study_uid] = w
    w.show()
    return w


def recarregar_aberta(tab, study_uid: str) -> None:
    """A segmentação ou o modelo de pesquisa terminou: a janela aberta deste exame mostra o resultado."""
    w = (getattr(tab, "__dict__", {}).get("_janelas_pirads") or {}).get(study_uid)
    if w is not None:
        try:
            if w.isVisible():
                w.recarregar()
        except RuntimeError:
            pass
