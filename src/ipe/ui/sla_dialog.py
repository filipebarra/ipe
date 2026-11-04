"""Configurações ▸ Laudos ▸ Prioridade, subespecialidade e prazos (0.99.52, onda B4)."""
from __future__ import annotations

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from ipe.core import sla as SLA
from ipe.ui.tabelas import colunas_ajustaveis


class SlaConfigDialog(QDialog):
    def __init__(self, repo, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("Prioridade, subespecialidade e prazos do laudo")
        self.resize(760, 640)
        cfg = SLA.config(repo)
        g1 = QGroupBox("Prazo do laudo, em horas desde a chegada ao banco")
        f1 = QFormLayout(g1)
        self.horas = {}
        for k, rot in SLA.PRIORIDADES.items():
            sp = QDoubleSpinBox()
            sp.setRange(0.25, 24 * 60)
            sp.setDecimals(2)
            sp.setSuffix(" h")
            sp.setValue(float(cfg["horas"][k]))
            f1.addRow(rot + ":", sp)
            self.horas[k] = sp
        self.por_subesp = QLineEdit("; ".join(f"{k}={v:g}" for k, v in cfg["por_subesp"].items()))
        self.por_subesp.setPlaceholderText("Mama=72; Medicina nuclear=24")
        f1.addRow("Rotina por subespecialidade:", self.por_subesp)
        g2 = QGroupBox("Prioridade automática pelas palavras da descrição do exame (separe por |)")
        f2 = QFormLayout(g2)
        self.palavras = {}
        for k in ("urgente", "emergencia"):
            e = QLineEdit(cfg["palavras"].get(k, ""))
            f2.addRow(SLA.PRIORIDADES[k] + ":", e)
            self.palavras[k] = e
        g3 = QGroupBox("Subespecialidade: vale a primeira regra que casar (modalidades e palavras da descrição)")
        v3 = QVBoxLayout(g3)
        self.regras = QTableWidget(0, 3)
        self.regras.setHorizontalHeaderLabels(["Subespecialidade", "Modalidades (MG|US)", "Palavras (vazio = todas)"])
        for r in cfg["subesp"]:
            self._linha(r)
        colunas_ajustaveis(self.regras)
        h = QHBoxLayout()
        for texto, fn in (("+ Regra", lambda: self._linha({})), ("Tirar a regra", self._tirar),
                          ("↑", lambda: self._mover(-1)), ("↓", lambda: self._mover(1)),
                          ("Restaurar as de fábrica", self._fabrica)):
            b = QPushButton(texto)
            b.clicked.connect(fn)
            h.addWidget(b)
        h.addStretch(1)
        v3.addWidget(self.regras, 1)
        v3.addLayout(h)
        nota = QLabel("O que não casa com nenhuma regra fica em “Geral”. A prioridade e a subespecialidade de "
                      "cada exame também se trocam à mão: botão direito no exame ▸ Prioridade / Subespecialidade.")
        nota.setWordWrap(True)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._salvar)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(g1)
        lay.addWidget(g2)
        lay.addWidget(g3, 1)
        lay.addWidget(nota)
        lay.addWidget(bb)

    def _linha(self, r: dict) -> None:
        i = self.regras.rowCount()
        self.regras.insertRow(i)
        for c, k in enumerate(("nome", "mod", "desc")):
            self.regras.setItem(i, c, QTableWidgetItem(str(r.get(k, "") or "")))

    def _tirar(self) -> None:
        r = self.regras.currentRow()
        if r >= 0:
            self.regras.removeRow(r)

    def _mover(self, d: int) -> None:
        r = self.regras.currentRow()
        alvo = r + d
        if r < 0 or not (0 <= alvo < self.regras.rowCount()):
            return
        a, b = self._ler_linha(r), self._ler_linha(alvo)
        for c, k in enumerate(("nome", "mod", "desc")):
            self.regras.item(r, c).setText(b[k])
            self.regras.item(alvo, c).setText(a[k])
        self.regras.setCurrentCell(alvo, 0)

    def _ler_linha(self, i: int) -> dict:
        return {k: (self.regras.item(i, c).text().strip() if self.regras.item(i, c) else "")
                for c, k in enumerate(("nome", "mod", "desc"))}

    def _fabrica(self) -> None:
        self.regras.setRowCount(0)
        for r in SLA.PADRAO["subesp"]:
            self._linha(r)

    def valor(self) -> dict:
        por = {}
        for parte in self.por_subesp.text().split(";"):
            if "=" in parte:
                k, v = parte.split("=", 1)
                try:
                    por[k.strip()] = float(v.strip().replace(",", "."))
                except ValueError:
                    raise ValueError(f"horas inválidas em “{parte.strip()}”") from None
        regras = [r for r in (self._ler_linha(i) for i in range(self.regras.rowCount())) if r["nome"]]
        return {"horas": {k: sp.value() for k, sp in self.horas.items()}, "por_subesp": por,
                "palavras": {k: e.text().strip() for k, e in self.palavras.items()}, "subesp": regras}

    def _salvar(self) -> None:
        try:
            self.repo.set_app_setting(SLA.CHAVE, self.valor())
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Prazos", f"Não deu para gravar: {e}")
            return
        self.accept()
