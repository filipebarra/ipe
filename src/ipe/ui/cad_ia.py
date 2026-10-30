"""Preferências ▸ CAD/IA (0.99): cada ferramenta de CAD/IA com as suas configurações —
se roda sozinha na chegada, como roda, e para onde vai o resultado depois de feito.

Hoje: **Segmentação abdominal**, **Níveis da coluna** e **Cefalometria do cavum** (TotalSegmentator) e
**Implante de silicone** (mamografia).
O que roda sozinho fica registrado em Tarefas automáticas, como o resto da automação.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QRadioButton, QSpinBox, QSplitter, QStackedWidget,
    QVBoxLayout, QWidget,
)

from ipe.ai import cefalometria as CF
from ipe.ai import coluna as COL
from ipe.ai import totalseg as TS
from ipe.automation import implante as IMP


def _lista_de_nos(repo, marcados) -> QListWidget:
    """Nós DICOM ativos, com caixa de marcar — os mesmos do menu Enviar para."""
    lw = QListWidget()
    lw.setMaximumHeight(110)
    alvo = {int(i) for i in (marcados or []) if str(i).lstrip("-").isdigit()}
    nos = []
    try:
        nos = repo.nodes(only_active=True) if repo is not None else []
    except Exception:  # noqa: BLE001
        nos = []
    for n in nos:
        it = QListWidgetItem(f"{n.get('name', '')}  ({n.get('ae_title', '')})")
        it.setData(Qt.UserRole, n["id"])
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
        it.setCheckState(Qt.Checked if n["id"] in alvo else Qt.Unchecked)
        lw.addItem(it)
    if not nos:
        it = QListWidgetItem("(nenhum nó DICOM cadastrado — Rede ▸ Nós DICOM)")
        it.setFlags(Qt.NoItemFlags)
        lw.addItem(it)
    return lw


def _marcados(lw: QListWidget) -> list[int]:
    out = []
    for k in range(lw.count()):
        it = lw.item(k)
        if it.data(Qt.UserRole) is not None and it.checkState() == Qt.Checked:
            out.append(int(it.data(Qt.UserRole)))
    return out


class CadIaTab(QWidget):
    #: (nome na lista, construtor do painel, chave do "automático")
    FERRAMENTAS = (("Segmentação abdominal", "_grupo_segmentacao", TS.CHAVE_AUTO),
                   ("Níveis da coluna", "_grupo_coluna", COL.CHAVE_AUTO),
                   ("Implante de silicone", "_grupo_implante", IMP.CHAVE),
                   ("Cefalometria do cavum", "_grupo_cefalometria", CF.CHAVE_AUTO))

    def __init__(self, settings, repo=None, parent=None):
        """Como a aba Mamografia (0.99.1): as ferramentas à esquerda, as configurações à direita."""
        super().__init__(parent)
        self.settings, self.repo = settings, repo
        lay = QVBoxLayout(self)
        nota = QLabel("Cada ferramenta de CAD/IA com as suas configurações: se roda sozinha quando o exame "
                      "chega (pela rede ou importado), como roda e para onde vai o resultado. O resultado fica "
                      "no próprio exame, só neste computador — a não ser que você escolha destinos. Não "
                      "destinado a uso diagnóstico.")
        nota.setWordWrap(True)
        nota.setStyleSheet("color:#9a9a9a")
        lay.addWidget(nota)

        esq = QWidget()
        el = QVBoxLayout(esq)
        el.setContentsMargins(0, 0, 0, 0)
        el.addWidget(QLabel("<b>Ferramentas</b>"))
        self.l_ferramentas = QListWidget()
        el.addWidget(self.l_ferramentas, 1)
        self.painel = QStackedWidget()
        for nome, construtor, _chave in self.FERRAMENTAS:
            grupo = getattr(self, construtor)()
            caixa = QWidget()
            cl = QVBoxLayout(caixa)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.addWidget(grupo)
            cl.addStretch(1)
            self.painel.addWidget(caixa)
            self.l_ferramentas.addItem(nome)
        self.l_ferramentas.currentRowChanged.connect(self.painel.setCurrentIndex)
        for c in self._caixas_auto():
            c.toggled.connect(lambda _on: self._rotulos())
        self._rotulos()
        corpo = QSplitter(Qt.Horizontal)
        corpo.addWidget(esq)
        corpo.addWidget(self.painel)
        corpo.setStretchFactor(0, 1)
        corpo.setStretchFactor(1, 4)
        corpo.setSizes([230, 900])
        lay.addWidget(corpo, 1)
        self.l_ferramentas.setCurrentRow(0)

    def _rotulos(self) -> None:
        """Na lista, cada ferramenta diz se está no automático."""
        for k, ((nome, _c, _ch), caixa) in enumerate(zip(self.FERRAMENTAS, self._caixas_auto())):
            auto = caixa.isChecked()
            self.l_ferramentas.item(k).setText(f"{nome}\n   {'automático na chegada' if auto else 'só à mão'}")

    def _caixas_auto(self) -> list:
        return [self.c_seg_auto, self.c_col_auto, self.c_imp_auto, self.c_cef_auto]

    def mostrar(self, nome: str) -> None:
        for k, (n, _c, _ch) in enumerate(self.FERRAMENTAS):
            if n == nome:
                self.l_ferramentas.setCurrentRow(k)

    # ------------------------------------------------------------ segmentação abdominal
    def _grupo_segmentacao(self) -> QGroupBox:
        g = QGroupBox("Segmentação abdominal (TotalSegmentator)")
        f = QFormLayout(g)
        cfg = lambda k: TS.config(self.settings, k)       # noqa: E731
        linha = QHBoxLayout()
        self.l_seg_estado = QLabel()
        b = QPushButton("Instalar / atualizar…")
        b.clicked.connect(self._instalar)
        linha.addWidget(self.l_seg_estado, 1)
        linha.addWidget(b)
        f.addRow("Situação:", linha)
        self._estado_seg()

        self.c_seg_auto = QCheckBox("Segmentar automaticamente quando o exame chegar")
        self.c_seg_auto.setChecked(bool(cfg(TS.CHAVE_AUTO)))
        f.addRow(self.c_seg_auto)
        self.e_seg_exame = QLineEdit(str(cfg(TS.CHAVE_EXAME_CONTEM) or ""))
        self.e_seg_exame.setPlaceholderText("vazio = qualquer TC/RM; ex.: ABDOME|FIGADO|RENAL")
        self.e_seg_exame.setToolTip("Pedaços da descrição do exame, separados por |, sem diferença de acento "
                                    "ou maiúscula. Vale para o automático.")
        f.addRow("Descrição do exame contém:", self.e_seg_exame)
        mods = {m.upper() for m in (cfg(TS.CHAVE_MODALIDADES) or [])}
        lm = QHBoxLayout()
        self.c_seg_ct, self.c_seg_mr = QCheckBox("TC"), QCheckBox("RM")
        self.c_seg_ct.setChecked("CT" in mods)
        self.c_seg_mr.setChecked("MR" in mods)
        lm.addWidget(self.c_seg_ct)
        lm.addWidget(self.c_seg_mr)
        lm.addStretch(1)
        f.addRow("Modalidades:", lm)
        self.e_seg_ct = QLineEdit(str(cfg(TS.CHAVE_PRIOR_CT) or ""))
        self.e_seg_mr = QLineEdit(str(cfg(TS.CHAVE_PRIOR_MR) or ""))
        dica = ("Séries em ordem de preferência, separadas por |: vale a primeira que aparecer na descrição da "
                "série; entre iguais, a de mais cortes. Localizador, MIP, difusão e mapas nunca são usados.")
        self.e_seg_ct.setToolTip(dica)
        self.e_seg_mr.setToolTip(dica)
        f.addRow("Série preferida na TC:", self.e_seg_ct)
        f.addRow("Série preferida na RM:", self.e_seg_mr)
        lf = QHBoxLayout()
        self.s_seg_esp = QDoubleSpinBox()
        self.s_seg_esp.setRange(0, 20)
        self.s_seg_esp.setDecimals(2)
        self.s_seg_esp.setSuffix(" mm")
        self.s_seg_esp.setSpecialValueText("sem limite")
        self.s_seg_esp.setValue(float(cfg(TS.CHAVE_ESPESSURA) or 0))
        self.s_seg_min = QSpinBox()
        self.s_seg_min.setRange(20, 2000)
        self.s_seg_min.setValue(int(cfg(TS.CHAVE_MIN_CORTES) or 40))
        lf.addWidget(QLabel("espessura até"))
        lf.addWidget(self.s_seg_esp)
        lf.addWidget(QLabel("  mínimo de"))
        lf.addWidget(self.s_seg_min)
        lf.addWidget(QLabel("cortes"))
        lf.addStretch(1)
        f.addRow("Filtros da série:", lf)

        self.l_seg_estr = QListWidget()
        self.l_seg_estr.setMaximumHeight(150)
        escolhidas = set(TS.estruturas(self.settings))
        for nome, pt, grupo, _p, _c in TS.ESTRUTURAS:
            it = QListWidgetItem(pt + ("" if grupo == "orgaos" else "  (outras estruturas)"))
            it.setData(Qt.UserRole, nome)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if nome in escolhidas else Qt.Unchecked)
            self.l_seg_estr.addItem(it)
        f.addRow("Estruturas:", self.l_seg_estr)
        self.c_seg_rapido = QCheckBox("Modo rápido na TC (3 mm; bem mais rápido em CPU)")
        self.c_seg_rapido.setChecked(bool(TS.config(self.settings, TS.CHAVE_RAPIDO)))
        self.c_seg_couinaud = QCheckBox("Segmentos do fígado (Couinaud) — outro modelo, menos robusto")
        self.c_seg_couinaud.setChecked(bool(TS.config(self.settings, TS.CHAVE_COUINAUD)))
        f.addRow(self.c_seg_rapido)
        f.addRow(self.c_seg_couinaud)
        self.l_seg_dest = _lista_de_nos(self.repo, cfg(TS.CHAVE_DESTINOS))
        self.l_seg_dest.setToolTip("A SEG e a tabela de volumes vão para os nós marcados depois de feitas — "
                                   "no automático e quando você pede pelo botão direito.")
        f.addRow("Depois de fazer, enviar para:", self.l_seg_dest)
        return g

    def _estado_seg(self) -> None:
        if TS.instalado(self.settings):
            self.l_seg_estado.setText(f"instalada ({TS.python_do_ambiente(self.settings).parent.parent})")
        else:
            self.l_seg_estado.setText("não instalada — baixe uma vez (uns 5 GB)")

    def _instalar(self) -> None:
        from ipe.ui.segmentacao import abrir_instalador
        abrir_instalador(self)

    # ------------------------------------------------------------ níveis da coluna (0.99.2)
    def _grupo_coluna(self) -> QGroupBox:
        g = QGroupBox("Níveis da coluna — vértebras e discos (TotalSegmentator)")
        f = QFormLayout(g)
        cfg = lambda k: COL.config(self.settings, k)      # noqa: E731
        expl = QLabel("Dá nome a cada vértebra e disco (C2-C3 … L5-S1). Os nomes aparecem em qualquer série e "
                      "plano do exame — num axial, o nível daquele corte. Usa a mesma instalação da "
                      "segmentação abdominal. Contagem que pede conferência (vértebra de transição, série só "
                      "torácica) gera aviso; botão direito ▸ Renumerar os níveis corrige com um clique.")
        expl.setWordWrap(True)
        expl.setStyleSheet("color: gray")
        f.addRow(expl)
        self.c_col_auto = QCheckBox("Identificar automaticamente quando o exame chegar")
        self.c_col_auto.setChecked(bool(cfg(COL.CHAVE_AUTO)))
        f.addRow(self.c_col_auto)
        self.e_col_exame = QLineEdit(str(cfg(COL.CHAVE_EXAME_CONTEM) or ""))
        self.e_col_exame.setPlaceholderText("vazio = qualquer TC/RM; ex.: COLUNA|LOMBAR|CERVICAL")
        f.addRow("Descrição do exame contém:", self.e_col_exame)
        mods = {m.upper() for m in (cfg(COL.CHAVE_MODALIDADES) or [])}
        lm = QHBoxLayout()
        self.c_col_ct, self.c_col_mr = QCheckBox("TC"), QCheckBox("RM")
        self.c_col_ct.setChecked("CT" in mods)
        self.c_col_mr.setChecked("MR" in mods)
        lm.addWidget(self.c_col_ct)
        lm.addWidget(self.c_col_mr)
        lm.addStretch(1)
        f.addRow("Modalidades:", lm)
        self.e_col_ct = QLineEdit(str(cfg(COL.CHAVE_PRIOR_CT) or ""))
        self.e_col_mr = QLineEdit(str(cfg(COL.CHAVE_PRIOR_MR) or ""))
        dica = ("Séries em ordem de preferência, separadas por |: vale a primeira que aparecer na descrição da "
                "série; entre iguais, a de mais cortes. Na RM, o sagital T2 costuma ser o melhor.")
        self.e_col_ct.setToolTip(dica)
        self.e_col_mr.setToolTip(dica)
        f.addRow("Série preferida na TC:", self.e_col_ct)
        f.addRow("Série preferida na RM:", self.e_col_mr)
        lf = QHBoxLayout()
        self.s_col_esp = QDoubleSpinBox()
        self.s_col_esp.setRange(0, 20)
        self.s_col_esp.setDecimals(2)
        self.s_col_esp.setSuffix(" mm")
        self.s_col_esp.setSpecialValueText("sem limite")
        self.s_col_esp.setValue(float(cfg(COL.CHAVE_ESPESSURA) or 0))
        self.s_col_min = QSpinBox()
        self.s_col_min.setRange(COL.MIN_CORTES, 2000)
        self.s_col_min.setValue(int(cfg(COL.CHAVE_MIN_CORTES) or COL.MIN_CORTES))
        lf.addWidget(QLabel("espessura até"))
        lf.addWidget(self.s_col_esp)
        lf.addWidget(QLabel("  mínimo de"))
        lf.addWidget(self.s_col_min)
        lf.addWidget(QLabel("cortes"))
        lf.addStretch(1)
        f.addRow("Filtros da série:", lf)
        self.c_col_medir = QCheckBox("Medir os discos (altura e volume) e os corpos vertebrais (altura e perda de altura) — tabelas no exame")
        self.c_col_medir.setToolTip("Na RM usa o modelo de discos de 1,5 mm (mais lento; o de 3 mm é grosso demais "
                                    "para uma altura de ~10 mm). A tabela é refeita quando você renumera.")
        self.c_col_medir.setChecked(bool(cfg(COL.CHAVE_MEDIR)))
        if COL.MEDIR_DISPONIVEL:                         # 0.99.7: só nomeia (medidas desligadas)
            f.addRow(self.c_col_medir)
        self.cb_col_seq = QComboBox()
        self.cb_col_seq.addItem("Uma sagital (mais rápido)", 1)
        self.cb_col_seq.addItem("Duas sagitais, conferindo uma com a outra", 2)
        self.cb_col_seq.setCurrentIndex(1 if int(cfg(COL.CHAVE_SEQUENCIAS) or 1) >= 2 else 0)
        self.cb_col_seq.setToolTip("Na RM, mede também numa segunda sagital do exame (T1, STIR…) e só gradua a "
                                   "perda de altura onde as duas concordam. Leva o dobro do tempo.")
        if COL.MEDIR_DISPONIVEL:
            f.addRow("Medir na RM em:", self.cb_col_seq)
        self.l_col_dest = _lista_de_nos(self.repo, cfg(COL.CHAVE_DESTINOS))
        self.l_col_dest.setToolTip("As séries “Níveis da coluna” e a tabela dos discos vão para os nós marcados "
                                   "depois de feitas.")
        f.addRow("Depois de fazer, enviar para:", self.l_col_dest)
        return g

    # ------------------------------------------------------------ cefalometria do cavum (0.99.16)
    def _grupo_cefalometria(self) -> QGroupBox:
        g = QGroupBox("Cefalometria do cavum — via aérea, palato, língua e hioide (TotalSegmentator)")
        f = QFormLayout(g)
        cfg = lambda k: CF.config(self.settings, k)      # noqa: E731
        expl = QLabel("Na TC: área de secção transversal mínima perpendicular ao eixo da via aérea, palato mole, "
                      "espaço aéreo posterior, hioide ao plano mandibular, língua e nível do hioide. No exame "
                      "ficam as estruturas e uma imagem de conferência com as linhas; o botão Cefalometria abre "
                      "os números para conferir e mandar para o laudo. Usa a mesma instalação da segmentação "
                      "abdominal; leva alguns minutos em CPU.")
        expl.setWordWrap(True)
        expl.setStyleSheet("color: gray")
        f.addRow(expl)
        self.c_cef_auto = QCheckBox("Fazer automaticamente quando o exame chegar (só TC)")
        self.c_cef_auto.setChecked(bool(cfg(CF.CHAVE_AUTO)))
        f.addRow(self.c_cef_auto)
        self.e_cef_exame = QLineEdit(str(cfg(CF.CHAVE_EXAME_CONTEM) or ""))
        self.e_cef_exame.setPlaceholderText("vazio = qualquer TC; ex.: CAVUM|RINOFARINGE|APNEIA")
        self.e_cef_exame.setToolTip("Pedaços da descrição do exame, separados por |, sem diferença de acento ou "
                                    "maiúscula. Vale para o automático.")
        f.addRow("Descrição do exame contém:", self.e_cef_exame)
        self.e_cef_ct = QLineEdit(str(cfg(CF.CHAVE_PRIOR_CT) or ""))
        self.e_cef_ct.setToolTip("Séries em ordem de preferência, separadas por |: vale a primeira que aparecer na "
                                 "descrição da série; entre iguais, a de mais cortes. A axial fina de partes moles "
                                 "costuma ser a melhor.")
        f.addRow("Série preferida na TC:", self.e_cef_ct)
        lf = QHBoxLayout()
        self.s_cef_esp = QDoubleSpinBox()
        self.s_cef_esp.setRange(0, 20)
        self.s_cef_esp.setDecimals(2)
        self.s_cef_esp.setSuffix(" mm")
        self.s_cef_esp.setSpecialValueText("sem limite")
        self.s_cef_esp.setValue(float(cfg(CF.CHAVE_ESPESSURA) or 0))
        self.s_cef_min = QSpinBox()
        self.s_cef_min.setRange(CF.MIN_CORTES, 2000)
        self.s_cef_min.setValue(int(cfg(CF.CHAVE_MIN_CORTES) or CF.MIN_CORTES))
        lf.addWidget(QLabel("espessura até"))
        lf.addWidget(self.s_cef_esp)
        lf.addWidget(QLabel("  mínimo de"))
        lf.addWidget(self.s_cef_min)
        lf.addWidget(QLabel("cortes"))
        lf.addStretch(1)
        f.addRow("Filtros da série:", lf)
        self.l_cef_dest = _lista_de_nos(self.repo, cfg(CF.CHAVE_DESTINOS))
        self.l_cef_dest.setToolTip("As séries “Cefalometria” (estruturas e imagem de conferência) vão para os nós "
                                   "marcados depois de feitas.")
        f.addRow("Depois de fazer, enviar para:", self.l_cef_dest)
        return g

    # ------------------------------------------------------------ implante
    def _grupo_implante(self) -> QGroupBox:
        g = QGroupBox("Implante de silicone (mamografia)")
        f = QFormLayout(g)
        cfg = lambda k: IMP.config(self.settings, k)      # noqa: E731
        self.c_imp_auto = QCheckBox("Corrigir automaticamente quando a mamografia chegar")
        self.c_imp_auto.setChecked(bool(cfg(IMP.CHAVE)))
        self.c_imp_ant = QCheckBox("Também nos exames anteriores baixados para comparação")
        self.c_imp_ant.setChecked(bool(cfg(IMP.CHAVE_ANTERIORES)))
        f.addRow(self.c_imp_auto)
        f.addRow(self.c_imp_ant)
        self.r_imp_qualquer = QRadioButton("quando o aparelho marca implante ou não diz nada (procura pela imagem)")
        self.r_imp_marca = QRadioButton("só quando o aparelho marca implante (BreastImplantPresent = YES)")
        self.r_imp_marca.setToolTip("Mais seguro com aparelhos que não gravam a marcação: sem ela, a busca só "
                                    "pela imagem pode confundir a pá da compressão localizada.")
        bg = QButtonGroup(g)
        bg.addButton(self.r_imp_qualquer)
        bg.addButton(self.r_imp_marca)
        (self.r_imp_marca if cfg(IMP.CHAVE_SO_COM_MARCA) else self.r_imp_qualquer).setChecked(True)
        caixa = QVBoxLayout()
        caixa.addWidget(self.r_imp_qualquer)
        caixa.addWidget(self.r_imp_marca)
        f.addRow("Procurar o implante:", caixa)
        nunca = QLabel("Nunca procura quando o aparelho diz que não há implante, nem na incidência com o "
                       "implante deslocado (Eklund), compressão localizada ou magnificação.")
        nunca.setWordWrap(True)
        nunca.setStyleSheet("color: gray")
        f.addRow(nunca)
        self.c_imp_botao = QCheckBox("Ao usar o botão Implante no visualizador, salvar a imagem sem o silicone "
                                     "no banco (se ainda não houver)")
        self.c_imp_botao.setChecked(bool(cfg(IMP.CHAVE_SALVAR_BOTAO)))
        f.addRow(self.c_imp_botao)
        self.l_imp_dest = _lista_de_nos(self.repo, cfg(IMP.CHAVE_DESTINOS))
        self.l_imp_dest.setToolTip("A série “· sem implante” vai para os nós marcados depois de gravada — na "
                                   "chegada, pelo banco (Apagar implante) e pelo botão Implante.")
        f.addRow("Depois de fazer, enviar para:", self.l_imp_dest)
        return g

    # ------------------------------------------------------------ gravar
    def save(self) -> None:
        s = self.settings
        s.set(TS.CHAVE_AUTO, self.c_seg_auto.isChecked())
        s.set(TS.CHAVE_EXAME_CONTEM, self.e_seg_exame.text().strip())
        s.set(TS.CHAVE_MODALIDADES, [m for m, c in (("CT", self.c_seg_ct), ("MR", self.c_seg_mr)) if c.isChecked()])
        s.set(TS.CHAVE_PRIOR_CT, self.e_seg_ct.text().strip())
        s.set(TS.CHAVE_PRIOR_MR, self.e_seg_mr.text().strip())
        s.set(TS.CHAVE_ESPESSURA, round(self.s_seg_esp.value(), 2))
        s.set(TS.CHAVE_MIN_CORTES, self.s_seg_min.value())
        s.set(TS.CHAVE_ESTRUTURAS, [self.l_seg_estr.item(k).data(Qt.UserRole) for k in range(self.l_seg_estr.count())
                                    if self.l_seg_estr.item(k).checkState() == Qt.Checked] or list(TS.PADRAO))
        s.set(TS.CHAVE_RAPIDO, self.c_seg_rapido.isChecked())
        s.set(TS.CHAVE_COUINAUD, self.c_seg_couinaud.isChecked())
        s.set(TS.CHAVE_DESTINOS, _marcados(self.l_seg_dest))
        s.set(COL.CHAVE_AUTO, self.c_col_auto.isChecked())
        s.set(COL.CHAVE_EXAME_CONTEM, self.e_col_exame.text().strip())
        s.set(COL.CHAVE_MODALIDADES, [m for m, c in (("CT", self.c_col_ct), ("MR", self.c_col_mr)) if c.isChecked()])
        s.set(COL.CHAVE_PRIOR_CT, self.e_col_ct.text().strip())
        s.set(COL.CHAVE_PRIOR_MR, self.e_col_mr.text().strip())
        s.set(COL.CHAVE_ESPESSURA, round(self.s_col_esp.value(), 2))
        s.set(COL.CHAVE_MIN_CORTES, self.s_col_min.value())
        s.set(COL.CHAVE_DESTINOS, _marcados(self.l_col_dest))
        if COL.MEDIR_DISPONIVEL:
            s.set(COL.CHAVE_MEDIR, self.c_col_medir.isChecked())
            s.set(COL.CHAVE_SEQUENCIAS, int(self.cb_col_seq.currentData() or 1))
        s.set(CF.CHAVE_AUTO, self.c_cef_auto.isChecked())
        s.set(CF.CHAVE_EXAME_CONTEM, self.e_cef_exame.text().strip())
        s.set(CF.CHAVE_PRIOR_CT, self.e_cef_ct.text().strip())
        s.set(CF.CHAVE_ESPESSURA, round(self.s_cef_esp.value(), 2))
        s.set(CF.CHAVE_MIN_CORTES, self.s_cef_min.value())
        s.set(CF.CHAVE_DESTINOS, _marcados(self.l_cef_dest))
        s.set(IMP.CHAVE, self.c_imp_auto.isChecked())
        s.set(IMP.CHAVE_ANTERIORES, self.c_imp_ant.isChecked())
        s.set(IMP.CHAVE_SO_COM_MARCA, self.r_imp_marca.isChecked())
        s.set(IMP.CHAVE_SALVAR_BOTAO, self.c_imp_botao.isChecked())
        s.set(IMP.CHAVE_DESTINOS, _marcados(self.l_imp_dest))
