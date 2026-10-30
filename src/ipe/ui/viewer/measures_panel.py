"""Painel de medidas: tudo o que foi medido no exame, numa lista só.

As medidas sempre ficaram salvas no banco — o que faltava era **vê-las juntas**. Espalhadas por
série e corte, achar de novo a régua do nódulo do ano passado era rolar a tira procurando o
distintivo verde. Aqui elas aparecem numa tabela: clicar leva até a imagem, com a medida já
selecionada para editar.

A tabela é montada a partir do **banco**, não dos quadros abertos: medida de série que não está em
nenhum quadro aparece do mesmo jeito. Por isso o valor é calculado com o espaçamento do arquivo
(régua, ângulo, área); o que depende dos pixels (média e máximo de ROI) fica para a imagem.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QDialog, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ipe.imaging import measure as M
from ipe.ui.tabelas import colunas_ajustaveis

log = logging.getLogger(__name__)

COLS = ["Série", "Im", "Tipo", "Medida", "Lesão", "Texto"]


class MeasuresPanel(QDialog):
    """Janela própria (não presa à direita): a tabela precisa de largura, e o quadro também."""

    def __init__(self, tab, parent=None):
        super().__init__(parent or tab)
        self.tab = tab
        self.linhas: list[dict] = []
        self.setWindowTitle("Medidas do exame")
        self.setWindowFlag(Qt.Window, True)          # fica por cima, mas não trava o visualizador
        self.setModal(False)
        self.resize(760, 420)
        self.setMinimumWidth(420)

        self.titulo = QLabel("<b>Medidas</b>")
        self.so_serie = QCheckBox("só a série do quadro ativo")
        self.so_serie.toggled.connect(lambda _on: self.refresh())
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._escolheu)
        self.table.itemDoubleClicked.connect(lambda _it: self._duplo_clique())
        colunas_ajustaveis(self.table)

        b_ir = QPushButton("Ir e editar")
        b_ir.setToolTip("Abre a imagem da medida, seleciona a medida e liga a ferramenta Selecionar")
        b_ir.clicked.connect(lambda: self.ir_para(editar=True))
        self.b_lesao = QPushButton("Editar lesão…")
        self.b_lesao.setToolTip("Reabre a segmentação: limiar, nome, distância ao mamilo e captura")
        self.b_lesao.clicked.connect(self.editar_lesao)
        self.b_lesao.setEnabled(False)
        b_txt = QPushButton("Texto / nota…")
        b_txt.clicked.connect(self._editar_texto)
        b_les = QPushButton("Ligar a lesão…")
        b_les.clicked.connect(self._ligar_lesao)
        b_del = QPushButton("Apagar")
        b_del.clicked.connect(self._apagar)
        b_exp = QPushButton("Exportar…")
        b_exp.setToolTip("Todas as medidas dos exames abertos numa planilha")
        b_exp.clicked.connect(self.tab.export_measures_table)
        botoes = QHBoxLayout()
        for b in (b_ir, self.b_lesao, b_txt, b_les, b_del, b_exp):
            botoes.addWidget(b)
        botoes.addStretch(1)

        cab = QHBoxLayout()
        cab.addWidget(self.titulo)
        cab.addStretch(1)
        cab.addWidget(self.so_serie)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        cab_w = QWidget()
        cab_w.setLayout(cab)
        lay.addWidget(cab_w)
        lay.addWidget(self.table, 1)
        bw = QWidget()
        bw.setLayout(botoes)
        lay.addWidget(bw)
        self.vazio = QLabel("Nenhuma medida guardada neste exame.\nMeça alguma coisa e ela aparece aqui.")
        self.vazio.setWordWrap(True)
        self.vazio.setStyleSheet("color:#9a9a9a")
        lay.addWidget(self.vazio)

    def closeEvent(self, e) -> None:  # noqa: N802
        acao = getattr(self.tab, "measures_action", None)
        if acao is not None and acao.isChecked():
            acao.setChecked(False)
        super().closeEvent(e)

    # ------------------------------------------------------------------ dados
    def _dados(self) -> list[dict]:
        from ipe.reporting.fill import _spacings
        tab = self.tab
        uids = list(tab.study_order)
        recs = tab.repo.annotations_for_studies(uids)
        if not recs:
            return []
        spac = _spacings(tab.repo, sorted({r["sop_uid"] for r in recs}))
        series = {}
        for u in uids:
            for s in tab.repo.series_for_study(u, ocultas=True):
                series[s.series_uid] = s
        ordem: dict[str, dict] = {}
        nomes = {}
        try:
            from ipe.ui.viewer.lesion_panel import patient_key
            pid = patient_key(tab.study_info)
            if pid:
                nomes = {x["id"]: x["name"] for x in tab.repo.lesions(pid)}
        except Exception:  # noqa: BLE001
            log.exception("nomes das lesões")
        out = []
        for r in recs:
            a = M.Annotation.from_record(r)
            s = series.get(a.series_uid)
            if a.series_uid not in ordem:
                ordem[a.series_uid] = {i["sop_uid"]: n for n, i in
                                       enumerate(tab.repo.instances_for_series(a.series_uid), 1)}
            try:
                labs = M.labels(a, None, spac.get(a.frame_key[0]), s.modality if s else "")
            except Exception:  # noqa: BLE001
                log.exception("rótulo da medida")
                labs = []
            lid = (a.meta or {}).get("lesion")
            out.append({
                "id": r["id"], "ann": a, "series_uid": a.series_uid,
                "serie": (f"Se {s.series_number} {s.description}".strip() if s else "(série fora do exame)"),
                "im": ordem[a.series_uid].get(a.frame_key[0], 0),
                "tipo": M.KINDS.get(a.kind, a.kind),
                "valor": "  ".join(x for x in labs[:3] if x),
                "lesao": nomes.get(lid, "") or (f"lesão {lid}" if lid else ""),
                "texto": a.text or "",
            })
        out.sort(key=lambda d: (d["serie"], d["im"]))
        return out

    def refresh(self) -> None:
        atual = self.selecionada_id()
        try:
            linhas = self._dados()
        except Exception:  # noqa: BLE001
            log.exception("painel de medidas")
            linhas = []
            self.vazio.setText("Não consegui ler as medidas do banco. O registro está no log.")
        if self.so_serie.isChecked():
            vp = self.tab.active
            uid = getattr(vp, "series_uid", "") if vp is not None else ""
            linhas = [d for d in linhas if d["series_uid"] == uid]
        self.linhas = linhas
        self.table.blockSignals(True)
        self.table.setRowCount(len(linhas))
        for r, d in enumerate(linhas):
            for c, chave in enumerate(("serie", "im", "tipo", "valor", "lesao", "texto")):
                v = d[chave]
                it = QTableWidgetItem(str(v) if v else "")
                if chave == "im":
                    it.setTextAlignment(Qt.AlignmentFlag(Qt.AlignRight | Qt.AlignVCenter))
                if chave == "valor" and not v:
                    it.setForeground(QColor(150, 150, 150))
                    it.setText("—")
                    it.setToolTip("Média e máximo de ROI dependem dos pixels: aparecem na imagem.")
                self.table.setItem(r, c, it)
        self.table.blockSignals(False)
        self.titulo.setText(f"<b>Medidas</b> — {len(linhas)}")
        self.vazio.setVisible(not linhas)
        self.table.setVisible(bool(linhas))
        if atual is not None:
            self.selecionar_id(atual)

    # ------------------------------------------------------------------ seleção
    def selecionada_id(self) -> int | None:
        r = self.table.currentRow()
        return self.linhas[r]["id"] if 0 <= r < len(self.linhas) else None

    def selecionar_id(self, db_id: int | None) -> None:
        """Deixa marcada na tabela a medida que está selecionada na imagem."""
        if db_id is None:
            self.table.clearSelection()
            return
        for r, d in enumerate(self.linhas):
            if d["id"] == db_id:
                self.table.blockSignals(True)
                self.table.selectRow(r)
                self.table.blockSignals(False)
                return

    def _escolheu(self) -> None:
        d = self._linha()
        self.b_lesao.setEnabled(d is not None and d["ann"].kind == "seg")
        self.ir_para(editar=False)

    def _duplo_clique(self) -> None:
        d = self._linha()
        if d is not None and d["ann"].kind == "seg":
            self.editar_lesao()
        else:
            self.ir_para(editar=True)

    def editar_lesao(self):
        """Lesão segmentada: abre a imagem dela e reabre a janela da segmentação."""
        d = self._linha()
        if d is None or d["ann"].kind != "seg":
            return None
        meta = d["ann"].meta or {}
        sessao = getattr(self.tab, "dyn", None)
        if meta.get("semente_mm") is not None and str(meta.get("method", "")).startswith("realce") \
                and sessao is not None and self.tab.active is not None:
            # Lesão da dinâmica com a semente guardada: não precisa abrir a imagem — e abrir
            # trocaria o mapa cinético do quadro pela série da fase, desmontando a tela dele.
            return self.tab.editar_segmentacao(self.tab.active, d["ann"])
        self.ir_para()
        vp = self.tab.active
        viva = next((x for x in getattr(vp, "annotations", []) if x.db_id == d["id"]), None)
        if viva is None:
            QMessageBox.information(self, "Medidas", "Abra a série desta lesão para editá-la.")
            return None
        return self.tab.editar_segmentacao(vp, viva)

    def _linha(self) -> dict | None:
        r = self.table.currentRow()
        return self.linhas[r] if 0 <= r < len(self.linhas) else None

    def ir_para(self, editar: bool = False) -> None:
        d = self._linha()
        if d is None:
            return
        tab = self.tab
        vp = tab.active or (tab.viewports[0] if tab.viewports else None)
        if vp is None:
            return
        if vp.series_uid != d["series_uid"]:
            try:
                tab.load_series_into(vp, d["series_uid"])
            except Exception:  # noqa: BLE001
                log.exception("abrir a série da medida")
                QMessageBox.information(self, "Medidas", "Não consegui abrir a série desta medida.")
                return
        alvo = d["ann"].frame_key
        idx = next((i for i, f in enumerate(vp.frames) if (f.sop_uid, f.frame_index) == alvo), None)
        if idx is None:
            QMessageBox.information(self, "Medidas", "A imagem desta medida não está nesta série "
                                    "(a série pode ter mudado).")
            return
        vp.go_to(idx)
        viva = next((x for x in vp.annotations if x.db_id == d["id"]), None)
        vp.selected = viva
        vp.update()
        if editar:
            tab.set_left_tool("pick")
            tab.status_message.emit("Medida selecionada: arraste as pontas para editar "
                                    "(ferramenta Selecionar).")

    # ------------------------------------------------------------------ ações
    def _editar_texto(self) -> None:
        d = self._linha()
        if d is None:
            return
        txt, ok = QInputDialog.getText(self, "Texto da medida", "Texto / nota:", text=d["texto"])
        if not ok:
            return
        self.ir_para()
        vp = self.tab.active
        viva = next((x for x in getattr(vp, "annotations", []) if x.db_id == d["id"]), None)
        if viva is None:
            QMessageBox.information(self, "Medidas", "Abra a série desta medida para editá-la.")
            return
        viva.text = txt.strip()
        vp._store("save", viva)
        vp.update()
        self.refresh()

    def _ligar_lesao(self) -> None:
        d = self._linha()
        if d is None:
            return
        self.ir_para()
        vp = self.tab.active
        viva = next((x for x in getattr(vp, "annotations", []) if x.db_id == d["id"]), None)
        if viva is None:
            QMessageBox.information(self, "Medidas", "Abra a série desta medida para ligá-la a uma lesão.")
            return
        self.tab.choose_lesion_for(vp, viva)

    def _apagar(self) -> None:
        d = self._linha()
        if d is None:
            return
        detalhe = d["tipo"] + "  " + (d["valor"] or "")
        if QMessageBox.question(self, "Apagar medida",
                                f"Apagar esta medida?\n\n{detalhe}") != QMessageBox.Yes:
            return
        vp = self.tab.active
        viva = next((x for x in getattr(vp, "annotations", []) if x.db_id == d["id"]), None)
        if viva is not None:
            vp.delete_annotation(viva)
        else:
            self.tab.repo.delete_annotation(d["id"])
        carregar = getattr(self.tab, "carregar_segmentacoes", None)
        if carregar is not None:
            carregar()                  # a máscara da lesão apagada sai da tela junto
        self.refresh()
