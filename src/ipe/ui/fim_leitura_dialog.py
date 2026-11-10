"""Configurações ▸ Laudos ▸ Fim da leitura (0.100.7): ao assinar o laudo, mandar ao PACS o que o Ipê fez no exame."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QMessageBox,
                               QVBoxLayout)

from ipe.exporter import fim_leitura as FL


class FimLeituraDialog(QDialog):
    def __init__(self, repo, settings, parent=None):
        super().__init__(parent)
        self.repo, self.settings = repo, settings
        self.setWindowTitle("Fim da leitura — enviar ao PACS")
        cfg = FL.config(settings)
        self.ligado = QCheckBox("Ao assinar o laudo, enviar ao PACS o que o Ipê fez no exame")
        self.ligado.setChecked(bool(cfg["ligado"]))
        self.destino = QComboBox()
        self.destino.addItem("(escolha o destino)", None)
        for n in repo.nodes(only_active=True):
            self.destino.addItem(f"{n['name']} ({n.get('ae_title', '')})", n["id"])
        i = self.destino.findData(cfg.get("destino"))
        self.destino.setCurrentIndex(max(0, i))
        form = QFormLayout()
        form.addRow(self.ligado)
        form.addRow("Destino", self.destino)
        self.itens = {}
        for chave, nome in FL.CATEGORIAS:
            c = QCheckBox(nome)
            c.setChecked(bool(cfg.get(chave, True)))
            form.addRow(c)
            self.itens[chave] = c
        nota = QLabel("Ao assinar, as imagens-chave viram um KO e as medidas um GSPS no exame, e tudo vai ao destino "
                      "pela fila de envios (a mesma do envio à mão). Vale também para o laudo assinado no navegador, "
                      "pelo servidor central. As cópias que ficam só neste computador (sem implante, tabelas da "
                      "segmentação) e as séries ocultas não vão.")
        nota.setWordWrap(True)
        form.addRow(nota)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._salvar)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(bb)
        self.resize(560, self.sizeHint().height())

    def valor(self) -> dict:
        return {"ligado": self.ligado.isChecked(), "destino": self.destino.currentData(),
                **{k: c.isChecked() for k, c in self.itens.items()}}

    def _salvar(self) -> None:
        v = self.valor()
        if v["ligado"] and v["destino"] is None:
            QMessageBox.warning(self, "Fim da leitura", "Escolha o destino (o PACS) para o envio.")
            return
        FL.guardar(self.settings, v)
        self.accept()
