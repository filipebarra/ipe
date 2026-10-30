"""Janela de análise entre séries: DMSA, paratireoide, tireoide e trânsito colônico.

A diferença para a janela de curvas é a entrada: aqui não há uma série dinâmica, e sim **várias
imagens do mesmo exame** — ANT e POST, precoce e tardia, seringa cheia e vazia, 24/48/72 h.

Cada imagem é uma linha da lista, com um **papel** (qual é a anterior, qual é a precoce…) e o
horário lido do cabeçalho. As regiões são desenhadas **em cada imagem**, porque o rim não cai no
mesmo pixel na ANT e na POST; os botões de copiar poupam o retrabalho, inclusive espelhando.
"""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QPushButton, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ipe.imaging import nm_multi, nm_roi
from ipe.ui.viewer.nm_analysis import RoiCanvas
from ipe.ui.tabelas import colunas_ajustaveis

log = logging.getLogger(__name__)

IGNORAR = "—"


def _hhmm(t: float | None) -> str:
    if t is None:
        return "—"
    return f"{int(t) // 3600:02d}:{(int(t) % 3600) // 60:02d}"


class NMMultiDialog(QDialog):
    """Compara várias imagens de um exame de medicina nuclear."""

    def __init__(self, sources: list, cache, titulo: str, preset: str = "livre",
                 parent=None, tab=None):
        super().__init__(parent)
        self.setWindowTitle(f"Medicina nuclear — {titulo}")
        self.resize(1200, 740)
        self.sources: list[nm_multi.Source] = list(sources)
        for s in self.sources:
            s.fill_time()
        self.cache = cache
        self.tab = tab if tab is not None else parent
        self.preset = preset
        self.atual = 0
        self.resultado = None
        self.tabela_dados: nm_multi.Table | None = None
        self._imagens: dict[str, np.ndarray] = {}

        self.canvas = RoiCanvas()
        self.canvas.preset = "multi"
        self.lista = QTableWidget(len(self.sources), 3)
        self.lista.setHorizontalHeaderLabels(["Imagem", "Papel", "Hora"])
        self.lista.verticalHeader().setVisible(False)
        self.lista.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.lista.setSelectionBehavior(QTableWidget.SelectRows)
        self.lista.setMaximumHeight(160)
        colunas_ajustaveis(self.lista)
        self.tabela = QTableWidget(0, 1)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.horizontalHeader().setStretchLastSection(True)
        self.tabela.setMaximumHeight(190)
        colunas_ajustaveis(self.tabela)
        self.aviso = QLabel()
        self.aviso.setWordWrap(True)
        self.aviso.setStyleSheet("color:#e0c070;")
        self.referencia = QLabel()
        self.referencia.setWordWrap(True)
        self.referencia.setStyleSheet("color:#9fb8cc;")

        self._monta()
        self._enche_lista()
        self.canvas.rois_changed.connect(self.recalcular)
        self._exame_mudou()
        self._mostra(0)

    # ---------------------------------------------------------- layout
    def _monta(self) -> None:
        lay = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal)

        esq = QWidget()
        ve = QVBoxLayout(esq)
        ve.setContentsMargins(0, 0, 0, 0)
        ve.addWidget(self.lista)
        ve.addWidget(self.canvas, 1)
        barra = QHBoxLayout()
        self.forma = QComboBox()
        self.forma.addItem("Elipse", "ellipse")
        self.forma.addItem("Retângulo", "rect")
        self.forma.addItem("Mão livre", "freehand")
        self.forma.currentIndexChanged.connect(
            lambda: setattr(self.canvas, "kind", self.forma.currentData()))
        barra.addWidget(QLabel("Forma:"))
        barra.addWidget(self.forma)
        b = QPushButton("Contorno automático")
        b.clicked.connect(self._contorno)
        barra.addWidget(b)
        self.limiar = QSpinBox()
        self.limiar.setRange(5, 95)
        self.limiar.setValue(40)
        self.limiar.setSuffix("% do máximo")
        barra.addWidget(self.limiar)
        b = QPushButton("Apagar região")
        b.clicked.connect(self.canvas.remove_selected)
        barra.addWidget(b)
        barra.addStretch(1)
        ve.addLayout(barra)
        copiar = QHBoxLayout()
        copiar.addWidget(QLabel("Copiar regiões de:"))
        self.origem = QComboBox()
        copiar.addWidget(self.origem, 1)
        b = QPushButton("Copiar")
        b.setToolTip("Traz as regiões daquela imagem para esta, na mesma posição.")
        b.clicked.connect(lambda: self._copiar(False))
        copiar.addWidget(b)
        b = QPushButton("Copiar espelhado")
        b.setToolTip("Para ANT e POST: a mesma região, espelhada no eixo vertical — "
                     "é o que mantém as duas com a mesma área.")
        b.clicked.connect(lambda: self._copiar(True))
        copiar.addWidget(b)
        ve.addLayout(copiar)
        split.addWidget(esq)

        dir_ = QWidget()
        vd = QVBoxLayout(dir_)
        vd.setContentsMargins(0, 0, 0, 0)
        linha = QHBoxLayout()
        linha.addWidget(QLabel("Exame:"))
        self.exame = QComboBox()
        for chave in nm_multi.MULTI_ORDER:
            self.exame.addItem(nm_multi.MULTI_PROTOCOLS[chave].name, chave)
        i = self.exame.findData(self.preset)
        self.exame.setCurrentIndex(max(0, i))
        self.exame.currentIndexChanged.connect(self._exame_mudou)
        linha.addWidget(self.exame, 1)
        self.corrigir = QCheckBox("Corrigir decaimento entre as imagens")
        self.corrigir.setChecked(True)
        self.corrigir.setToolTip("Imagens de horários diferentes só se comparam depois disto.")
        self.corrigir.toggled.connect(self.recalcular)
        linha.addWidget(self.corrigir)
        vd.addLayout(linha)
        self.dica = QLabel()
        self.dica.setWordWrap(True)
        vd.addWidget(self.dica)
        vd.addWidget(self.tabela)
        vd.addWidget(self.aviso)
        vd.addWidget(self.referencia)
        vd.addStretch(1)
        split.addWidget(dir_)
        split.setSizes([620, 560])
        lay.addWidget(split, 1)

        bb = QDialogButtonBox()
        b = bb.addButton("Exportar CSV…", QDialogButtonBox.ActionRole)
        b.clicked.connect(self.exportar_csv)
        b = bb.addButton("Mandar para o laudo", QDialogButtonBox.ActionRole)
        b.clicked.connect(self.para_o_laudo)
        bb.addButton(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        nota = QLabel("As regiões são desenhadas em cada imagem: o alvo não cai no mesmo pixel em "
                      "vistas diferentes. Valores de referência são do serviço. Ferramenta de "
                      "pesquisa e ensino, não destinada a uso diagnóstico.")
        nota.setWordWrap(True)
        lay.addWidget(nota)

    # ---------------------------------------------------------- lista de imagens
    def _enche_lista(self) -> None:
        self.lista.setRowCount(len(self.sources))
        for i, s in enumerate(self.sources):
            it = QTableWidgetItem(s.label)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            self.lista.setItem(i, 0, it)
            combo = QComboBox()
            combo.currentIndexChanged.connect(self.recalcular)
            self.lista.setCellWidget(i, 1, combo)
            h = QTableWidgetItem(_hhmm(s.time_s))
            h.setFlags(h.flags() & ~Qt.ItemIsEditable)
            self.lista.setItem(i, 2, h)
        self.lista.currentCellChanged.connect(
            lambda linha, *_a: self._mostra(linha) if linha >= 0 else None)
        self.origem.clear()
        for s in self.sources:
            self.origem.addItem(s.label, s.key)

    def _enche_papeis(self) -> None:
        p = nm_multi.multi_protocol(self.preset)
        for i, _s in enumerate(self.sources):
            combo = self.lista.cellWidget(i, 1)
            if combo is None:
                continue
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(IGNORAR, "")
            for chave, rotulo in p.roles:
                combo.addItem(rotulo, chave)
            if p.roles and i < len(p.roles):
                combo.setCurrentIndex(i + 1)         # primeira imagem no primeiro papel
            combo.blockSignals(False)
            combo.setEnabled(bool(p.roles))

    def papeis(self) -> dict:
        out = {}
        for i, s in enumerate(self.sources):
            combo = self.lista.cellWidget(i, 1)
            chave = combo.currentData() if combo is not None else ""
            if chave:
                out[s.key] = chave
        return out

    def _mostra(self, linha: int) -> None:
        if not (0 <= linha < len(self.sources)):
            return
        self.atual = linha
        s = self.sources[linha]
        self.canvas.rois = s.rois
        self.canvas.selected = len(s.rois) - 1
        self.canvas.set_image(self._imagem(s))

    def _imagem(self, s: nm_multi.Source) -> np.ndarray:
        if s.key in self._imagens:
            return self._imagens[s.key]
        acc = None
        for f in s.frames:
            px = self.cache.get(f).pixels
            if px.ndim != 2:
                px = px.astype(np.float32).mean(axis=2)
            acc = px.astype(np.float32) if acc is None else acc + px.astype(np.float32)
        if acc is None:
            acc = np.zeros((1, 1), np.float32)
        self._imagens[s.key] = acc
        return acc

    # ---------------------------------------------------------- regiões
    def _contorno(self) -> None:
        erro = self.canvas.auto_contour(float(self.limiar.value()))
        if erro:
            QMessageBox.information(self, "Contorno automático", erro)

    def _copiar(self, espelhar: bool) -> None:
        origem = self.origem.currentData()
        destino = self.sources[self.atual]
        if not origem or origem == destino.key:
            QMessageBox.information(self, "Copiar regiões",
                                    "Escolha outra imagem como origem.")
            return
        fonte = next((s for s in self.sources if s.key == origem), None)
        if fonte is None or not fonte.rois:
            QMessageBox.information(self, "Copiar regiões", "Aquela imagem não tem regiões.")
            return
        largura = int(self._imagem(destino).shape[1])
        existentes = {r.name for r in destino.rois}
        novas = 0
        for r in fonte.rois:
            if r.name in existentes:
                continue
            destino.rois.append(r.mirrored(largura) if espelhar else _copia(r))
            novas += 1
        if not novas:
            QMessageBox.information(self, "Copiar regiões",
                                    "Esta imagem já tem regiões com esses nomes.")
            return
        self._mostra(self.atual)
        self.recalcular()

    # ---------------------------------------------------------- contas
    def _exame_mudou(self) -> None:
        self.preset = self.exame.currentData() or "livre"
        p = nm_multi.multi_protocol(self.preset)
        self.canvas.preset = self.preset
        self.canvas.preset_names = list(p.rois) if p.rois else None
        self._enche_papeis()
        if p.rois:
            self.dica.setText(f"Regiões deste exame: {', '.join(p.rois)}.")
        else:
            self.dica.setText("Desenhe as regiões que quiser; a tabela mostra a contagem de cada "
                              "uma em cada imagem.")
        self.recalcular()

    def recalcular(self) -> None:
        p = nm_multi.multi_protocol(self.preset)
        p.decay_default = self.corrigir.isChecked()
        self.tabela_dados = nm_multi.measure(self.sources, self.cache)
        if not self.corrigir.isChecked():
            self.tabela_dados.half_life_s = 0.0
        self.resultado = p.run(self.tabela_dados, self.papeis())
        self._preenche()

    def _preenche(self) -> None:
        res = self.resultado
        if res is None:
            self.tabela.setRowCount(0)
            return
        self.tabela.setColumnCount(max(1, len(res.headers)))
        self.tabela.setHorizontalHeaderLabels(res.headers or [""])
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabela.horizontalHeader().setStretchLastSection(True)
        self.tabela.setRowCount(len(res.rows))
        for i, linha in enumerate(res.rows):
            for j, v in enumerate(linha):
                self.tabela.setItem(i, j, QTableWidgetItem(v))
        self.aviso.setText(" ".join(a for a in res.notes if a))
        self.referencia.setText(res.reference)

    # ---------------------------------------------------------- saídas
    def report_text(self) -> str:
        return self.resultado.text if self.resultado else ""

    def csv_text(self) -> str:
        res = self.resultado
        if res is None or not res.rows:
            return ""
        linhas = [";".join(res.headers)]
        linhas += [";".join(l) for l in res.rows]
        return "\n".join(linhas)

    def exportar_csv(self) -> None:
        texto = self.csv_text()
        if not texto:
            QMessageBox.information(self, "Exportar", "Não há tabela para exportar.")
            return
        caminho, _f = QFileDialog.getSaveFileName(self, "Salvar tabela", "medidas.csv",
                                                  "Planilha (*.csv)")
        if not caminho:
            return
        with open(caminho, "w", encoding="utf-8-sig") as fh:
            fh.write(texto)

    def para_o_laudo(self) -> None:
        texto = self.report_text()
        if not texto:
            QMessageBox.information(self, "Laudo", "Não há números para mandar ao laudo.")
            return
        alvo = getattr(self.tab, "append_to_report", None)
        if callable(alvo) and alvo(texto):
            QMessageBox.information(self, "Laudo", "Os números foram para o laudo.")
            return
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(texto)
        QMessageBox.information(self, "Laudo", "O texto foi copiado; cole no laudo onde quiser.")


def _copia(r: nm_roi.Roi) -> nm_roi.Roi:
    novo = nm_roi.Roi(name=r.name, kind=r.kind, points=list(r.points), role=r.role,
                      background=r.background, background_roi=r.background_roi,
                      ring_px=r.ring_px, fraction=r.fraction, auto_pct=r.auto_pct)
    if r.auto_mask is not None:
        novo.auto_mask = r.auto_mask.copy()
        novo.auto_box = r.auto_box
    return novo
