"""Janela de altura, peso e sexo antes da composição corporal e em Achados de IA (0.99.80)."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QVBoxLayout,
)

from ipe.ai import biometria as B


class BiometriaDialog(QDialog):
    """Mostra o que veio do arquivo (ou o já digitado neste exame) e deixa trocar. 0 = não informado."""

    def __init__(self, valores: dict, parent=None, perguntar: bool | None = None,
                 titulo: str = "Altura e peso do paciente"):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        lay = QVBoxLayout(self)
        txt = QLabel("O índice muscular usa a altura; o IMC e as referências de Martin (2013) usam também o peso. "
                     "Os valores vêm do arquivo DICOM quando ele traz; o que você digitar vale para este exame "
                     "(o arquivo não muda). Deixe 0 se não souber.")
        txt.setWordWrap(True)
        lay.addWidget(txt)
        fonte = valores.get("fonte") or {}
        form = QFormLayout()
        self.altura = QDoubleSpinBox()
        self.altura.setRange(0, 230)
        self.altura.setDecimals(0)
        self.altura.setSuffix(" cm")
        self.altura.setSpecialValueText("não informada")
        self.altura.setValue(round(float(valores.get("altura_m") or 0) * 100))
        form.addRow(self._rotulo("Altura:", fonte.get("altura_m")), self.altura)
        self.peso = QDoubleSpinBox()
        self.peso.setRange(0, 350)
        self.peso.setDecimals(1)
        self.peso.setSuffix(" kg")
        self.peso.setSpecialValueText("não informado")
        self.peso.setValue(float(valores.get("peso_kg") or 0))
        form.addRow(self._rotulo("Peso:", fonte.get("peso_kg")), self.peso)
        self.sexo = QComboBox()
        for cod, nome in (("", "não informado"), ("F", "Feminino"), ("M", "Masculino")):
            self.sexo.addItem(nome, cod)
        i = self.sexo.findData(valores.get("sexo") or "")
        self.sexo.setCurrentIndex(max(0, i))
        form.addRow(self._rotulo("Sexo:", fonte.get("sexo")), self.sexo)
        self.l_imc = QLabel("")
        form.addRow("IMC:", self.l_imc)
        lay.addLayout(form)
        self.c_perguntar = None
        if perguntar is not None:
            self.c_perguntar = QCheckBox("Perguntar sempre antes de calcular a composição corporal")
            self.c_perguntar.setChecked(bool(perguntar))
            lay.addWidget(self.c_perguntar)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Calcular" if perguntar is not None else "Salvar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.altura.valueChanged.connect(self._imc)
        self.peso.valueChanged.connect(self._imc)
        self._imc()

    @staticmethod
    def _rotulo(txt: str, fonte: str | None) -> str:
        rotulos = {
            ("Altura:", "arquivo"): "Altura (do arquivo):", ("Altura:", "digitado"): "Altura (digitada):",
            ("Peso:", "arquivo"): "Peso (do arquivo):", ("Peso:", "digitado"): "Peso (digitado):",
            ("Sexo:", "arquivo"): "Sexo (do arquivo):", ("Sexo:", "digitado"): "Sexo (digitado):",
        }
        return rotulos.get((txt, fonte or ""), txt)

    def _imc(self) -> None:
        v = B.imc(self.altura.value() / 100.0, self.peso.value())
        self.l_imc.setText("—" if v is None else f"{v:.1f} kg/m²".replace(".", ","))

    def valores(self) -> dict:
        return {"altura_m": (self.altura.value() / 100.0) or None, "peso_kg": self.peso.value() or None,
                "sexo": self.sexo.currentData() or ""}

    def perguntar(self) -> bool:
        return self.c_perguntar is None or self.c_perguntar.isChecked()
