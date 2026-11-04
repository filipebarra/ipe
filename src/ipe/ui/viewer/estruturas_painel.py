"""Painel Estruturas (0.99.40, plano AW F2): editar, organizar e gravar máscaras.

Uma janela por aba, não modal. A **série de referência** é a do quadro ativo quando o painel abre: as
estruturas vivem na grade dela (`imaging.estruturas.Grade`), mas aparecem em qualquer série e plano do
mesmo exame (o desenho é em mm). O pincel pinta em qualquer quadro do exame, no plano que está na tela.

- Lista: visível, cor, nome, tipo, volume, travada, de onde veio.
- Nova / Importar do exame (lesões guardadas, SEG, RTSTRUCT, IA) / Duplicar / Apagar.
- Pincel e borracha (raio em mm; disco no plano ou esfera 3D; só na faixa de intensidade do clique).
- Crescer / encolher, só a maior ilha, tirar ilhas pequenas, preencher buracos, interpolar cortes,
  aparar pela faixa, unir / subtrair / cruzar. Desfazer e refazer (Ctrl+Z / Ctrl+Y).
- Gravar SEG, gravar RTSTRUCT, atualizar a lesão guardada, mandar os volumes ao laudo.
"""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QDoubleSpinBox, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QMenu, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from ipe.imaging import estruturas as ES
from ipe.imaging import overlays as O

log = logging.getLogger(__name__)
FONTE = "Estruturas"
COL_VIS, COL_NOME, COL_TIPO, COL_ML, COL_TRAVA, COL_FONTE = range(6)


class EstruturasPainel(QDialog):
    def __init__(self, tab, vp=None):
        super().__init__(tab, Qt.Window)
        self.tab = tab
        self.setWindowTitle("Estruturas")
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.estruturas: list[ES.Estrutura] = []
        self.vol = self.grade = None
        self.study_uid = self.serie_uid = ""
        self.frames = None
        self._faixa_ref = (0.0, 1.0)
        self._enchendo = False
        self._traco = None                  # (estrutura, último ponto mm, faixa) do traço em curso
        self._ocultados: list = []          # objetos do exame escondidos enquanto editados aqui
        self._ferramenta_antes = None
        self._gravado = True
        self.obj = O.OverlayObject(f"estruturas:{id(self)}", FONTE, "Estruturas em edição", (255, 255, 255))
        self._montar()
        self.usar_quadro(vp)

    # ================================================================ interface
    def _montar(self) -> None:
        lay = QVBoxLayout(self)
        self.l_ref = QLabel()
        self.l_ref.setWordWrap(True)
        lay.addWidget(self.l_ref)

        self.tabela = QTableWidget(0, 6)
        self.tabela.setHorizontalHeaderLabels(["Ver", "Nome", "Tipo", "mL", "Travada", "Origem"])
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabela.verticalHeader().setVisible(False)
        hh = self.tabela.horizontalHeader()
        hh.setSectionResizeMode(COL_NOME, QHeaderView.Stretch)
        for c in (COL_VIS, COL_TIPO, COL_ML, COL_TRAVA, COL_FONTE):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        from ipe.ui.tabelas import colunas_ajustaveis
        colunas_ajustaveis(self.tabela, estica_ultima=False)
        self.tabela.itemChanged.connect(self._item_mudou)
        self.tabela.cellDoubleClicked.connect(self._duplo_clique)
        self.tabela.currentCellChanged.connect(lambda *_a: self._selecionou())
        self.tabela.setMinimumHeight(170)
        lay.addWidget(self.tabela)

        bar = QHBoxLayout()
        self.b_nova = QPushButton("Nova")
        self.b_nova.clicked.connect(lambda: self.nova())
        self.b_importar = QPushButton("Importar do exame ▾")
        self.b_importar.clicked.connect(self._menu_importar)
        self.b_dup = QPushButton("Duplicar")
        self.b_dup.clicked.connect(self.duplicar)
        self.b_apagar = QPushButton("Apagar")
        self.b_apagar.clicked.connect(self.apagar)
        for b in (self.b_nova, self.b_importar, self.b_dup, self.b_apagar):
            bar.addWidget(b)
        lay.addLayout(bar)

        # ---------------- pincel
        gp = QGroupBox("Pincel")
        g = QGridLayout(gp)
        self.b_pincel = QPushButton("Pincel")
        self.b_borracha = QPushButton("Borracha")
        for b in (self.b_pincel, self.b_borracha):
            b.setCheckable(True)
        self.b_pincel.toggled.connect(lambda on: self._ferramenta(on, apagar=False))
        self.b_borracha.toggled.connect(lambda on: self._ferramenta(on, apagar=True))
        self.s_raio = QDoubleSpinBox(minimum=0.5, maximum=60.0, value=5.0, singleStep=0.5, suffix=" mm")
        self.s_raio.valueChanged.connect(lambda _v: self._raio_nos_quadros())
        self.c_esfera = QCheckBox("Esfera 3D")
        self.c_esfera.setToolTip("Desligado: um disco no plano da tela (só o corte que se vê). "
                                 "Ligado: uma esfera, que pinta também os cortes vizinhos.")
        self.c_faixa = QCheckBox("Só na faixa do clique ±")
        self.c_faixa.setToolTip("O pincel só pinta voxels de intensidade parecida com a do ponto onde o "
                                "traço começa — não sai da lesão para a gordura ou o ar.")
        self.s_tol = QDoubleSpinBox(minimum=1, maximum=100, value=15, suffix=" %", decimals=0)
        self.s_tol.setToolTip("Meia largura da faixa, em porcentagem da faixa de intensidades da série.")
        g.addWidget(self.b_pincel, 0, 0)
        g.addWidget(self.b_borracha, 0, 1)
        g.addWidget(QLabel("Raio:"), 0, 2)
        g.addWidget(self.s_raio, 0, 3)
        g.addWidget(self.c_esfera, 1, 0, 1, 2)
        g.addWidget(self.c_faixa, 1, 2)
        g.addWidget(self.s_tol, 1, 3)
        lay.addWidget(gp)

        # ---------------- limites da edição (0.99.44, como as opções de máscara do 3D Slicer)
        gl = QGroupBox("Limites da edição (pincel, crescer, buracos, interpolar)")
        lg = QGridLayout(gl)
        self.c_area = QComboBox()
        for txt, k in (("Em toda parte", "tudo"), ("Só dentro de", "dentro"), ("Só fora das outras (visíveis)", "fora")):
            self.c_area.addItem(txt, k)
        self.c_area_alvo = QComboBox()
        self.c_area.currentIndexChanged.connect(self._area_mudou)
        self.c_area_alvo.setEnabled(False)
        self.c_lim_faixa = QCheckBox("Só intensidades entre")
        self.c_lim_faixa.setToolTip("Nada entra fora desta faixa — vale para todas as ferramentas, não só para o pincel.")
        self.s_lim_lo = QDoubleSpinBox(minimum=-1e6, maximum=1e6, decimals=1)
        self.s_lim_hi = QDoubleSpinBox(minimum=-1e6, maximum=1e6, decimals=1)
        self.c_sobre = QCheckBox("Sobrescrever as outras (o que esta ganha sai delas)")
        self.c_sobre.setToolTip("Desligado: as estruturas podem se sobrepor. Ligado: pintar a lesão tira esses "
                                "voxels do órgão (as travadas nunca mudam).")
        lg.addWidget(QLabel("Área:"), 0, 0)
        lg.addWidget(self.c_area, 0, 1)
        lg.addWidget(self.c_area_alvo, 0, 2, 1, 2)
        lg.addWidget(self.c_lim_faixa, 1, 0, 1, 2)
        lg.addWidget(self.s_lim_lo, 1, 2)
        lg.addWidget(self.s_lim_hi, 1, 3)
        lg.addWidget(self.c_sobre, 2, 0, 1, 4)
        lay.addWidget(gl)

        # ---------------- operações
        go = QGroupBox("Corrigir a estrutura escolhida")
        o = QGridLayout(go)
        self.s_mm = QDoubleSpinBox(minimum=0.5, maximum=50, value=2.0, singleStep=0.5, suffix=" mm")
        self.c_plano = QCheckBox("só nos cortes")
        self.c_plano.setToolTip("Cresce e encolhe só dentro de cada corte (não passa para o corte de cima e de baixo).")
        b_cresce = QPushButton("Crescer")
        b_cresce.clicked.connect(lambda: self._crescer(+1))
        b_encolhe = QPushButton("Encolher")
        b_encolhe.clicked.connect(lambda: self._crescer(-1))
        o.addWidget(self.s_mm, 0, 0)
        o.addWidget(self.c_plano, 0, 1)
        o.addWidget(b_cresce, 0, 2)
        o.addWidget(b_encolhe, 0, 3)
        b_maior = QPushButton("Só a maior ilha")
        b_maior.clicked.connect(lambda: self._operar("ilhas", lambda e: ES.limpar_ilhas(e, self.grade, True)))
        self.s_ilha = QDoubleSpinBox(minimum=0.001, maximum=1000, value=0.1, decimals=3, suffix=" mL")
        b_peq = QPushButton("Tirar ilhas menores que")
        b_peq.clicked.connect(lambda: self._operar("ilhas", lambda e: ES.limpar_ilhas(
            e, self.grade, False, self.s_ilha.value())))
        o.addWidget(b_maior, 1, 0)
        o.addWidget(b_peq, 1, 1, 1, 2)
        o.addWidget(self.s_ilha, 1, 3)
        b_bur = QPushButton("Preencher buracos")
        b_bur.clicked.connect(lambda: self._operar("buracos", ES.preencher_buracos))
        b_int = QPushButton("Interpolar cortes")
        b_int.setToolTip("Desenhe a cada 3 ou 4 cortes; os cortes vazios entre dois desenhados são preenchidos "
                         "pela forma intermediária.")
        b_int.clicked.connect(lambda: self._operar("interpolar", lambda e: ES.interpolar(e, self.grade)))
        o.addWidget(b_bur, 2, 0, 1, 2)
        o.addWidget(b_int, 2, 2, 1, 2)
        self.s_lo = QDoubleSpinBox(minimum=-1e6, maximum=1e6, decimals=1)
        self.s_hi = QDoubleSpinBox(minimum=-1e6, maximum=1e6, decimals=1)
        b_apara = QPushButton("Aparar fora de")
        b_apara.setToolTip("Tira da estrutura os voxels com intensidade fora da faixa (gordura, ar, osso).")
        b_apara.clicked.connect(lambda: self._operar("faixa", lambda e: ES.aplicar_faixa(
            e, self.vol.data, self.s_lo.value(), self.s_hi.value())))
        o.addWidget(b_apara, 3, 0)
        o.addWidget(self.s_lo, 3, 1)
        o.addWidget(QLabel("a"), 3, 2, alignment=Qt.AlignCenter)
        o.addWidget(self.s_hi, 3, 3)
        self.c_op = QComboBox()
        for txt, op in (("Unir com", "uniao"), ("Subtrair", "subtracao"), ("Cruzar com", "intersecao")):
            self.c_op.addItem(txt, op)
        self.c_outra = QComboBox()
        b_comb = QPushButton("Criar nova")
        b_comb.clicked.connect(self._combinar)
        o.addWidget(self.c_op, 4, 0)
        o.addWidget(self.c_outra, 4, 1, 1, 2)
        o.addWidget(b_comb, 4, 3)
        self.b_desfazer = QPushButton("Desfazer")
        self.b_desfazer.clicked.connect(self.desfazer)
        self.b_refazer = QPushButton("Refazer")
        self.b_refazer.clicked.connect(self.refazer)
        o.addWidget(self.b_desfazer, 5, 0, 1, 2)
        o.addWidget(self.b_refazer, 5, 2, 1, 2)
        lay.addWidget(go)
        QShortcut(QKeySequence.Undo, self, activated=self.desfazer)
        QShortcut(QKeySequence.Redo, self, activated=self.refazer)

        self.l_num = QLabel()
        self.l_num.setWordWrap(True)
        self.l_num.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.l_num)

        # ---------------- saída
        sai = QHBoxLayout()
        self.b_seg = QPushButton("Gravar SEG")
        self.b_seg.setToolTip("Grava todas as estruturas no exame como DICOM SEG (máscara voxel a voxel): "
                              "vai ao PACS e abre no 3D Slicer e em outros visualizadores.")
        self.b_seg.clicked.connect(lambda: self.gravar("SEG"))
        self.b_rt = QPushButton("Gravar RTSTRUCT")
        self.b_rt.setToolTip("Grava as estruturas como contornos de radioterapia (RTSTRUCT), que o sistema "
                             "de planejamento lê direto.")
        self.b_rt.clicked.connect(lambda: self.gravar("RTSTRUCT"))
        self.b_lesao = QPushButton("Atualizar a lesão guardada")
        self.b_lesao.setToolTip("A estrutura veio de uma lesão segmentada e guardada: a medida passa a ter a "
                                "máscara e o volume corrigidos (vale para o acompanhamento de lesões).")
        self.b_lesao.clicked.connect(self.atualizar_lesao)
        self.b_laudo = QPushButton("Mandar ao laudo")
        self.b_laudo.clicked.connect(self.mandar_ao_laudo)
        self.b_copiar = QPushButton("Copiar os números")
        self.b_copiar.setToolTip("Uma linha por estrutura (volume, intensidade, forma), separada por tabulação — "
                                 "cola direto na planilha.")
        self.b_copiar.clicked.connect(self.copiar_numeros)
        for b in (self.b_seg, self.b_rt, self.b_lesao, self.b_laudo, self.b_copiar):
            sai.addWidget(b)
        lay.addLayout(sai)
        self.resize(560, 720)

    # ================================================================ referência
    def usar_quadro(self, vp) -> bool:
        """A série do quadro vira a grade de referência (só com a lista vazia)."""
        if self.estruturas:
            return False
        tab = self.tab
        uid = tab._source_series(vp) if vp is not None else None
        vol = None
        if uid:
            try:
                vol = tab._volume_for(vp, uid)
            except Exception:  # noqa: BLE001
                log.exception("volume da referência")
        if vol is None:
            self.vol = self.grade = None
            self.l_ref.setText("Escolha um quadro com uma série de cortes (TC, RM, PET) e abra o painel de "
                               "novo: as estruturas são desenhadas na grade dessa série.")
            self._habilitar()
            return False
        self.vol, self.grade = vol, ES.Grade.do_volume(vol)
        self.study_uid, self.serie_uid = vp.study_uid, uid
        try:
            from ipe.imaging.series import build_frames
            self.frames = build_frames(tab.repo.instances_for_series(uid), uid)
        except Exception:  # noqa: BLE001
            self.frames = list(vp.frames) if vp.mpr_plane is None else None
        amostra = np.asarray(vol.data[:: max(1, vol.data.shape[0] // 24), ::4, ::4], np.float64)
        lo, hi = (float(x) for x in np.percentile(amostra, [1, 99]))
        self._faixa_ref = (lo, hi if hi > lo else lo + 1.0)
        self.s_lo.setValue(lo)
        self.s_hi.setValue(hi)
        self.s_lim_lo.setValue(lo)
        self.s_lim_hi.setValue(hi)
        nz, ny, nx = self.grade.forma
        dx, dy, dz = self.grade.espacamento
        desc = ""
        try:
            desc = tab.repo.series_meta(uid).get("description") or ""
        except Exception:  # noqa: BLE001
            pass
        grade_txt = f"{nx} × {ny} × {nz}"
        voxel_txt = f"{dx:.2f} × {dy:.2f} × {dz:.2f}"
        self.l_ref.setText(f"Série de referência: <b>{desc or uid[-12:]}</b> — {grade_txt} ({voxel_txt} mm). "
                           "As estruturas aparecem em todas as séries e planos deste exame.")
        self.obj.study_uid = self.study_uid
        if self.obj not in tab.overlay_objects:
            tab.overlay_objects.append(self.obj)
            tab._apply_overlays()
        self._habilitar()
        return True

    def _habilitar(self) -> None:
        ok = self.grade is not None
        for tipo in (QPushButton, QDoubleSpinBox, QCheckBox, QComboBox):
            for w in self.findChildren(tipo):
                w.setEnabled(ok)
        if ok:
            self._atualizar_botoes()

    # ================================================================ lista
    def atual(self) -> ES.Estrutura | None:
        r = self.tabela.currentRow()
        return self.estruturas[r] if 0 <= r < len(self.estruturas) else None

    def _encher(self, escolher: ES.Estrutura | None = None) -> None:
        self._enchendo = True
        try:
            atual = escolher or self.atual()
            self.tabela.setRowCount(len(self.estruturas))
            for r, e in enumerate(self.estruturas):
                vis = QTableWidgetItem()
                vis.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                vis.setCheckState(Qt.Checked if e.visivel else Qt.Unchecked)
                vis.setBackground(QColor(*e.cor))
                vis.setToolTip("Mostrar / ocultar. Duplo clique: mudar a cor.")
                self.tabela.setItem(r, COL_VIS, vis)
                nome = QTableWidgetItem(e.nome)
                nome.setFlags(Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.tabela.setItem(r, COL_NOME, nome)
                tipo = QComboBox()
                for t in ES.TIPOS:
                    tipo.addItem(t, t)
                tipo.setCurrentIndex(max(0, tipo.findData(e.tipo)))
                tipo.currentIndexChanged.connect(lambda _i, ee=e, cb=tipo: setattr(ee, "tipo", cb.currentData()))
                self.tabela.setCellWidget(r, COL_TIPO, tipo)
                ml = QTableWidgetItem(f"{e.ml(self.grade):.2f}" if self.grade else "")
                ml.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                ml.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tabela.setItem(r, COL_ML, ml)
                tr = QTableWidgetItem()
                tr.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                tr.setCheckState(Qt.Checked if e.travada else Qt.Unchecked)
                tr.setToolTip("Travada: não muda, e o pincel das outras não pinta por cima dela.")
                self.tabela.setItem(r, COL_TRAVA, tr)
                fo = QTableWidgetItem(e.fonte)
                fo.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.tabela.setItem(r, COL_FONTE, fo)
            if atual in self.estruturas:
                self.tabela.setCurrentCell(self.estruturas.index(atual), COL_NOME)
            elif self.estruturas:
                self.tabela.setCurrentCell(0, COL_NOME)
        finally:
            self._enchendo = False
        self._encher_outras()
        self._selecionou()

    def _encher_outras(self) -> None:
        self.c_outra.clear()
        alvo = self.c_area_alvo.currentData()
        self.c_area_alvo.clear()
        for e in self.estruturas:
            self.c_outra.addItem(e.nome, e.id)
            self.c_area_alvo.addItem(e.nome, e.id)
        if alvo is not None:
            self.c_area_alvo.setCurrentIndex(max(0, self.c_area_alvo.findData(alvo)))

    def _area_mudou(self, _i=0) -> None:
        self.c_area_alvo.setEnabled(self.c_area.currentData() == "dentro")

    def limites(self) -> ES.Limites:
        """Os limites da edição escolhidos na janela."""
        alvo_id = self.c_area_alvo.currentData()
        return ES.Limites(area=self.c_area.currentData() or "tudo",
                          alvo=next((x for x in self.estruturas if x.id == alvo_id), None),
                          outras=list(self.estruturas),
                          faixa=(self.s_lim_lo.value(), self.s_lim_hi.value()) if self.c_lim_faixa.isChecked() else None,
                          dados=self.vol.data if self.vol is not None else None,
                          sobrescrever=self.c_sobre.isChecked())

    def _depois_de_somar(self, e: ES.Estrutura, lim: ES.Limites) -> list:
        """Depois de uma operação que soma voxels: tira o que entrou fora dos limites e, com sobrescrever,
        tira das outras o que esta ganhou. Devolve as outras que mudaram."""
        if not e._desfazer:
            return []
        foto = e._desfazer[-1]
        ES.restringir(e, foto, lim)
        if not lim.sobrescrever:
            return []
        mudaram = ES.sobrescrever(e, foto, self.estruturas)
        for o in mudaram:
            self._linha(o)
        return mudaram

    def _item_mudou(self, item: QTableWidgetItem) -> None:
        if self._enchendo:
            return
        r = item.row()
        if not 0 <= r < len(self.estruturas):
            return
        e = self.estruturas[r]
        if item.column() == COL_VIS:
            e.visivel = item.checkState() == Qt.Checked
            self._redesenhar()
        elif item.column() == COL_TRAVA:
            e.travada = item.checkState() == Qt.Checked
        elif item.column() == COL_NOME:
            novo = item.text().strip()
            if novo and novo != e.nome:
                e.nome = novo
                e.alterada = True
                self._gravado = False
                self._encher_outras()
                self._redesenhar()

    def _duplo_clique(self, r: int, c: int) -> None:
        if c != COL_VIS or not 0 <= r < len(self.estruturas):
            return
        e = self.estruturas[r]
        cor = QColorDialog.getColor(QColor(*e.cor), self, "Cor da estrutura")
        if cor.isValid():
            e.cor = (cor.red(), cor.green(), cor.blue())
            e.alterada = True
            self._gravado = False
            self._encher(e)
            self._redesenhar()

    def _linha(self, e: ES.Estrutura) -> None:
        """Atualiza só o volume da linha (barato, durante o pincel)."""
        if e in self.estruturas and self.grade is not None:
            it = self.tabela.item(self.estruturas.index(e), COL_ML)
            if it is not None:
                self._enchendo = True
                it.setText(f"{e.ml(self.grade):.2f}")
                self._enchendo = False

    def _selecionou(self) -> None:
        self._atualizar_botoes()
        self._numeros()

    def _atualizar_botoes(self) -> None:
        e = self.atual()
        ok = self.grade is not None
        self.b_desfazer.setEnabled(ok and e is not None and e.pode_desfazer())
        self.b_refazer.setEnabled(ok and e is not None and e.pode_refazer())
        self.b_lesao.setEnabled(ok and e is not None and e.chave_origem.startswith("segann:"))
        tem = ok and any(not x.vazia() for x in self.estruturas)
        for b in (self.b_seg, self.b_rt, self.b_laudo, self.b_copiar):
            b.setEnabled(tem)

    def _numeros(self) -> None:
        e = self.atual()
        if e is None or self.grade is None:
            self.l_num.setText("Nenhuma estrutura. <b>Nova</b> e pinte com o pincel, ou <b>Importar do exame</b>."
                               if self.grade is not None else "")
            return
        if e.vazia():
            self.l_num.setText(f"<b>{e.nome}</b>: vazia — pinte com o pincel.")
            return
        s = ES.estatisticas(e, self.grade, self.vol.data)
        t = f"<b>{e.nome}</b>: {s['ml']:.2f} mL · {s['voxels']} voxels · {s.get('cortes', 0)} cortes"
        if s.get("eixos_mm"):
            a, b, c = s["eixos_mm"]
            t += f"<br>eixos {a:.1f} × {b:.1f} × {c:.1f} mm"
        if "media" in s:
            t += f"<br>média {s['media']:.1f} ± {s['dp']:.1f} · mín {s['minimo']:.1f} · máx {s['maximo']:.1f}"
            t += (f"<br>mediana {s['mediana']:.1f} · p10–p90 {s['p10']:.1f}–{s['p90']:.1f} · "
                  f"assimetria {s['assimetria']:.2f} · curtose {s['curtose']:.2f}")
            t += f"<br>entropia {s['entropia']:.2f} bits · uniformidade {s['uniformidade']:.3f}"
        if s.get("feret_mm"):
            t += f"<br>maior diâmetro (Feret) {s['feret_mm']:.1f} mm"
            if "esfericidade" in s:
                t += f" · esfericidade {s['esfericidade']:.2f}"
            if "alongamento" in s:
                t += f" · alongamento {s['alongamento']:.2f} · achatamento {s['achatamento']:.2f}"
        n_ilhas = len(ES.ilhas(e, self.grade)) if e.voxels < 4_000_000 else 0
        if n_ilhas > 1:
            t += f"<br>{n_ilhas} ilhas separadas"
        self.l_num.setText(t)

    # ================================================================ desenho
    def _redesenhar(self) -> None:
        if self.grade is None:
            return
        self.obj.volumes = [e.mask_volume(self.grade) for e in self.estruturas if e.visivel and not e.vazia()]
        self.obj.version += 1
        for vp in self.tab.viewports:
            vp.update()

    # ================================================================ lista: criar, importar, apagar
    def nova(self, nome: str = "") -> ES.Estrutura | None:
        if self.grade is None:
            return None
        e = ES.nova(self.estruturas, nome)
        self.estruturas.append(e)
        self._encher(e)
        return e

    def duplicar(self) -> None:
        e = self.atual()
        if e is None:
            return
        c = ES.Estrutura(f"{e.nome} (cópia)", e.cor, e.mascara.copy(), e.offset, tipo=e.tipo, fonte="cópia")
        c.alterada = True
        self.estruturas.append(c)
        self._gravado = False
        self._encher(c)
        self._redesenhar()

    def apagar(self) -> None:
        e = self.atual()
        if e is None:
            return
        if not e.vazia() and QMessageBox.question(
                self, "Estruturas", f"Apagar “{e.nome}” desta sessão de edição?\n\nO que já foi gravado no "
                "exame não muda.") != QMessageBox.Yes:
            return
        self.estruturas.remove(e)
        self._encher()
        self._redesenhar()

    def candidatos(self) -> list[tuple]:
        """(objeto, MaskVolume, rótulo) que podem ser importados: tudo o que o exame mostra com volume."""
        out = []
        for o in self.tab.overlay_objects:
            if o is self.obj or (o.study_uid and o.study_uid != self.study_uid):
                continue
            vols = [mv for mv in (o.volumes or []) if not getattr(mv, "so_rotulo", False)]
            if not vols and (o.masks or o.planar):
                vols = O.volumes_derivados(o)
            for mv in vols:
                rot = mv.label or o.label
                out.append((o, mv, f"{rot} ({O.TIPOS.get(o.source, o.source)})"))
        return out

    def _menu_importar(self) -> None:
        cands = self.candidatos()
        m = QMenu(self)
        if not cands:
            a = m.addAction("Nada para importar: o exame não tem segmentação, SEG nem RTSTRUCT aberto.")
            a.setEnabled(False)
        for o, mv, rot in cands:
            a = m.addAction(rot)
            a.triggered.connect(lambda _=False, oo=o, mm=mv: self.importar(oo, mm))
        if len(cands) > 1:
            m.addSeparator()
            todos = m.addAction(f"Todos ({len(cands)})")
            todos.triggered.connect(lambda: self.importar_todos(cands))
        m.exec(self.b_importar.mapToGlobal(self.b_importar.rect().bottomLeft()))

    def importar_todos(self, cands=None) -> int:
        n = 0
        for o, mv, _r in (cands if cands is not None else self.candidatos()):
            n += self.importar(o, mv, encher=False) is not None
        self._encher()
        return n

    def importar(self, o, mv, encher: bool = True) -> ES.Estrutura | None:
        if self.grade is None:
            return None
        if o.source == "Segmentação":
            tipo = "lesão"
        elif o.source in ("SEG", "Coluna") or "TotalSegmentator" in (o.label or "") or "SynthSeg" in (o.label or ""):
            tipo = "órgão"
        else:
            tipo = "outro" if o.source == "RTSTRUCT" else "lesão"
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            e = ES.de_mask_volume(mv, self.grade, mv.label or o.label, mv.color, tipo=tipo,
                                  fonte=O.TIPOS.get(o.source, o.source), chave=o.key)
        finally:
            QApplication.restoreOverrideCursor()
        if e.vazia():
            self.tab.status_message.emit(f"“{mv.label or o.label}” não cai na série de referência.")
            return None
        self.estruturas.append(e)
        if o.enabled:
            o.enabled = False                 # o original sai da tela enquanto a cópia é editada aqui
            self._ocultados.append(o)
            self.tab._apply_overlays()
        if encher:
            self._encher(e)
        self._redesenhar()
        return e

    # ================================================================ pincel
    def _ferramenta(self, on: bool, apagar: bool) -> None:
        outro = self.b_borracha if not apagar else self.b_pincel
        if on:
            outro.blockSignals(True)
            outro.setChecked(False)
            outro.blockSignals(False)
            if self.tab.left_tool != "pincel":
                self._ferramenta_antes = self.tab.left_tool
                self.tab.set_left_tool("pincel")
            for vp in self.tab.viewports:
                vp.pincel_apaga = apagar
            self._raio_nos_quadros()
            if self.atual() is None and not apagar:
                self.nova()
        elif not self.b_pincel.isChecked() and not self.b_borracha.isChecked():
            self._soltar_ferramenta()

    def _soltar_ferramenta(self) -> None:
        if self.tab.left_tool == "pincel":
            self.tab.set_left_tool(self._ferramenta_antes or "wl")
        self._ferramenta_antes = None
        for vp in self.tab.viewports:
            vp.pincel_raio_mm = 0.0
            vp.update()

    def _raio_nos_quadros(self) -> None:
        for vp in self.tab.viewports:
            vp.pincel_raio_mm = float(self.s_raio.value())

    def pincel(self, vp, u: float, v: float, etapa: str) -> None:
        """Chamado pelo quadro (ferramenta "pincel"): começo, meio e fim de um traço."""
        if self.grade is None:
            return
        if vp.study_uid != self.study_uid:
            if etapa == "ini":
                self.tab.status_message.emit("O pincel pinta só no exame da série de referência.")
            return
        apagar = self.b_borracha.isChecked()
        if not self.b_pincel.isChecked() and not apagar:
            self.b_pincel.setChecked(True)
        p = vp.pixel_to_patient(u - 0.5, v - 0.5)
        if etapa == "ini":
            e = self.atual() or self.nova()
            if e is None:
                return
            if e.travada:
                self.tab.status_message.emit(f"“{e.nome}” está travada: destrave para editar.")
                self._traco = None
                return
            if p is None:
                return
            e.guardar_para_desfazer()
            faixa = None
            if self.c_faixa.isChecked() and not apagar:
                ijk = np.rint(self.grade.para_ijk(p)[0]).astype(int)
                nz, ny, nx = self.grade.forma
                i, j, k = int(np.clip(ijk[0], 0, nx - 1)), int(np.clip(ijk[1], 0, ny - 1)), int(np.clip(ijk[2], 0, nz - 1))
                v0 = float(np.mean(self.vol.data[k, max(0, j - 1):j + 2, max(0, i - 1):i + 2]))
                meia = (self._faixa_ref[1] - self._faixa_ref[0]) * self.s_tol.value() / 100.0
                faixa = (v0 - meia, v0 + meia)
            self._traco = (e, None, faixa, 0)
        if self._traco is None:
            return
        e, ultimo, faixa, total = self._traco
        if p is not None:
            pl = vp.plane()
            normal = None if self.c_esfera.isChecked() or pl is None else pl[3]
            r = float(self.s_raio.value())
            proib = [x for x in self.estruturas if x.travada and x is not e]
            pontos = [np.asarray(p, float)]
            if ultimo is not None:
                dist = float(np.linalg.norm(pontos[0] - ultimo))
                n = int(dist / max(r * 0.5, 0.3))
                pontos = [ultimo + (pontos[0] - ultimo) * (t / (n + 1)) for t in range(1, n + 1)] + pontos
            mudou = 0
            lim = self.limites()
            for q in pontos:
                mudou += ES.pintar(e, self.grade, q, r, normal=normal, apagar=apagar, dados=self.vol.data,
                                   faixa=faixa, proibidas=proib, limites=lim)
            total += mudou
            self._traco = (e, np.asarray(p, float), faixa, total)
            if mudou:
                self._gravado = False
                self._redesenhar()
                self._linha(e)
        if etapa == "fim":
            e.aparar()
            if not total and e._desfazer:
                e._desfazer.pop()             # traço que não mudou nada não ocupa o desfazer
            elif total and not apagar and self.c_sobre.isChecked():
                if self._depois_de_somar(e, self.limites()):
                    self._redesenhar()
            self._traco = None
            self._selecionou()

    # ================================================================ operações
    def _operar(self, nome: str, fn) -> int:
        e = self.atual()
        if e is None or self.grade is None:
            return 0
        if e.travada:
            QMessageBox.information(self, "Estruturas", f"“{e.nome}” está travada.")
            return 0
        e.guardar_para_desfazer()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            r = fn(e)
        except Exception as ex:  # noqa: BLE001
            log.exception("estrutura: %s", nome)
            e.desfazer()
            e._refazer.clear()
            QMessageBox.warning(self, "Estruturas", f"Não deu certo:\n{ex}")
            return 0
        finally:
            QApplication.restoreOverrideCursor()
        if r and nome in ("crescer", "buracos", "interpolar"):
            self._depois_de_somar(e, self.limites())
        if not r:
            e._desfazer.pop()                 # nada mudou: não ocupa o desfazer
            self.tab.status_message.emit("Nada mudou.")
        else:
            self._gravado = False
            self._redesenhar()
            self._linha(e)
        self._selecionou()
        return r

    def _crescer(self, sinal: int) -> None:
        proib = [x for x in self.estruturas if x.travada]
        self._operar("crescer", lambda e: ES.crescer(e, self.grade, sinal * self.s_mm.value(),
                                                     so_no_plano=self.c_plano.isChecked(), proibidas=proib))

    def _combinar(self) -> None:
        a = self.atual()
        bid = self.c_outra.currentData()
        b = next((x for x in self.estruturas if x.id == bid), None)
        if a is None or b is None:
            return
        if a is b:
            QMessageBox.information(self, "Estruturas", "Escolha outra estrutura para combinar.")
            return
        c = ES.combinar(a, b, self.grade, self.c_op.currentData())
        c.cor = ES.nova(self.estruturas).cor
        c.alterada = True
        self.estruturas.append(c)
        self._gravado = False
        self._encher(c)
        self._redesenhar()

    def desfazer(self) -> None:
        e = self.atual()
        if e is not None and e.desfazer():
            self._gravado = False
            self._redesenhar()
            self._linha(e)
            self._selecionou()

    def refazer(self) -> None:
        e = self.atual()
        if e is not None and e.refazer():
            self._gravado = False
            self._redesenhar()
            self._linha(e)
            self._selecionou()

    # ================================================================ saída
    def _validas(self) -> list[ES.Estrutura]:
        return [e for e in self.estruturas if not e.vazia()]

    def gravar(self, formato: str, perguntar: bool = True) -> str | None:
        """Grava todas as estruturas no exame (SEG ou RTSTRUCT). Devolve o SeriesInstanceUID."""
        from ipe.importer.scanner import Importer
        validas = self._validas()
        storage = getattr(self.tab, "storage_root", None)
        if not validas or self.vol is None:
            return None
        if storage is None:
            QMessageBox.information(self, "Estruturas", "Banco de dados indisponível.")
            return None
        try:
            if formato == "SEG":
                from ipe.imaging.seg_writer import build_seg
                segs = [(SimpleNamespace(mask=e.mascara, offset=e.offset), e.nome, e.cor, e.tipo) for e in validas]
                ds = build_seg(self.vol, segs, self.vol.source_path, self.frames, series_number=982,
                               description="Estruturas (Ipe)",
                               algoritmo=("SEMIAUTOMATIC", "Ipe estruturas (revisado)"))
            else:
                from ipe.imaging.rtstruct_writer import build_rtstruct
                ds = build_rtstruct(self.vol, validas, self.vol.source_path, self.frames)
            tmp = Path(tempfile.mkdtemp(prefix="ipe_estr_"))
            try:
                ds.save_as(tmp / "estruturas.dcm", enforce_file_format=True)
                Importer(self.tab.repo.db, storage).import_paths([tmp])
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            try:
                from ipe.central.client_repo import upload_if_client
                upload_if_client(self.tab.repo, self.study_uid)
            except Exception:  # noqa: BLE001
                log.exception("estruturas: enviar ao servidor")
        except Exception as ex:  # noqa: BLE001
            log.exception("gravar %s", formato)
            if perguntar:
                QMessageBox.warning(self, "Estruturas", f"Não foi possível gravar:\n{ex}")
            return None
        for e in validas:
            e.alterada = False
        self._gravado = True
        nomes = ", ".join(e.nome for e in validas)
        self.tab.status_message.emit(f"{len(validas)} estrutura(s) gravada(s) no exame como {formato}: {nomes}.")
        return str(ds.SeriesInstanceUID)

    def atualizar_lesao(self) -> bool:
        """A lesão guardada (medida "seg") de onde a estrutura veio passa a ter a máscara e os números novos."""
        e = self.atual()
        if e is None or not e.chave_origem.startswith("segann:") or e.vazia():
            return False
        db_id = int(e.chave_origem.split(":", 1)[1])
        repo = self.tab.repo
        rec = next((r for r in repo.annotations_for_studies([self.study_uid]) if r["id"] == db_id), None)
        if rec is None:
            QMessageBox.information(self, "Estruturas", "A lesão guardada não existe mais.")
            return False
        try:
            d = json.loads(rec.get("data") or "{}")
        except ValueError:
            d = {}
        meta = dict(d.get("meta") or {})
        s = ES.estatisticas(e, self.grade, self.vol.data)
        e.aparar()
        meta["mascara3d"] = e.mask_volume(self.grade).para_meta()
        meta["ml"] = round(s["ml"], 3)
        meta["cor"] = [int(c) for c in e.cor]
        if s.get("eixos_mm"):
            meta["eixos_mm"] = [round(float(x), 1) for x in s["eixos_mm"]]
            meta["max_diam_mm"] = meta["mm"] = round(float(s["eixos_mm"][0]), 2)
        if "media" in s and not str(meta.get("method", "")).startswith("realce"):
            meta["mean"], meta["maximum"] = round(s["media"], 3), round(s["maximo"], 3)
        meta["editada_em_estruturas"] = True
        d["meta"] = meta
        d["text"] = e.nome
        repo.save_annotation(db_id=db_id, study_uid=rec["study_uid"], series_uid=rec["series_uid"],
                             sop_uid=rec["sop_uid"], frame_index=rec["frame_index"], kind=rec["kind"],
                             data=json.dumps(d))
        for vp in self.tab.viewports:
            for a in getattr(vp, "annotations", []) or []:
                if getattr(a, "db_id", None) == db_id:
                    a.meta = meta
                    a.text = e.nome
        # o objeto antigo sai; o novo (com a máscara nova) entra oculto enquanto o painel está aberto
        chave = e.chave_origem
        self.tab.overlay_objects[:] = [o for o in self.tab.overlay_objects if o.key != chave]
        self._ocultados = [o for o in self._ocultados if o.key != chave]
        try:
            self.tab.carregar_segmentacoes()
        except Exception:  # noqa: BLE001
            log.exception("recarregar as lesões")
        for o in self.tab.overlay_objects:
            if o.key == chave and o.enabled:
                o.enabled = False
                self._ocultados.append(o)
        e.alterada = False
        self._gravado = all(not x.alterada for x in self.estruturas)
        self.tab._apply_overlays()
        try:
            self.tab.refresh_lesions()
        except Exception:  # noqa: BLE001
            pass
        self.tab.status_message.emit(f"Lesão “{e.nome}” atualizada: {s['ml']:.2f} mL.")
        return True

    COLUNAS = ("ml", "voxels", "cortes", "media", "dp", "minimo", "maximo", "mediana", "p10", "p90", "assimetria",
               "curtose", "entropia", "uniformidade", "feret_mm", "superficie_mm2", "esfericidade", "alongamento",
               "achatamento")

    def tabela_de_numeros(self) -> str:
        """TSV com os números de todas as estruturas (para a planilha, a pesquisa)."""
        linhas = ["\t".join(("estrutura", "tipo", *self.COLUNAS, "eixo1_mm", "eixo2_mm", "eixo3_mm"))]
        for e in self._validas():
            s = ES.estatisticas(e, self.grade, self.vol.data if self.vol is not None else None)
            eixos = s.get("eixos_mm") or ("", "", "")
            vals = [s.get(k, "") for k in self.COLUNAS] + list(eixos)
            linhas.append("\t".join([e.nome, e.tipo] + [f"{v:.4g}" if isinstance(v, float) else str(v) for v in vals]))
        return "\n".join(linhas)

    def copiar_numeros(self) -> None:
        QApplication.clipboard().setText(self.tabela_de_numeros())
        self.tab.status_message.emit("Números das estruturas copiados (cole na planilha).")

    def mandar_ao_laudo(self) -> None:
        from ipe.core.i18n import tr
        texto = ES.texto_do_laudo(self._validas(), self.grade, self.vol.data if self.vol is not None else None)
        if texto:
            self.tab.mandar_texto_ao_laudo(tr(texto))

    # ================================================================ fechar
    def pendente(self) -> bool:
        return not self._gravado and any(e.alterada and not e.vazia() for e in self.estruturas)

    def closeEvent(self, ev) -> None:  # noqa: N802
        if self.pendente():
            r = QMessageBox.question(
                self, "Estruturas", "Há estruturas alteradas que não foram gravadas no exame.\n\n"
                "Gravar como SEG antes de fechar?", QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if r == QMessageBox.Cancel:
                ev.ignore()
                return
            if r == QMessageBox.Save and self.gravar("SEG") is None:
                ev.ignore()
                return
        self.encerrar()
        super().closeEvent(ev)

    def encerrar(self) -> None:
        """Tira o desenho, devolve à tela o que estava oculto e solta o pincel."""
        self._soltar_ferramenta()
        for b in (self.b_pincel, self.b_borracha):
            b.blockSignals(True)
            b.setChecked(False)
            b.blockSignals(False)
        tab = self.tab
        tab.overlay_objects[:] = [o for o in tab.overlay_objects if o is not self.obj]
        for o in self._ocultados:
            o.enabled = True
        self._ocultados = []
        tab._apply_overlays()


def abrir(tab, vp=None) -> EstruturasPainel:
    d = getattr(tab, "_estruturas", None)
    try:
        import shiboken6
        viva = d is not None and shiboken6.isValid(d)
    except Exception:  # noqa: BLE001
        viva = d is not None
    if viva and d.isVisible():
        d.raise_()
        d.activateWindow()
        return d
    if viva:
        d.deleteLater()
    d = EstruturasPainel(tab, vp)
    tab._estruturas = d
    d.show()
    d.raise_()
    return d
