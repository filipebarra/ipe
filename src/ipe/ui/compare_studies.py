"""Abrir mais de um exame na mesma aba para comparar.

O programa trata os exames escolhidos como se fossem do mesmo paciente — o mais
recente vira o atual e os outros entram como anteriores. Como isso é exatamente o
tipo de coisa que dá errado em silêncio, antes de abrir ele confere nome, ID,
nascimento e sexo e, havendo diferença, **mostra o que difere e pergunta**.
"""

from __future__ import annotations

import re

CAMPOS = (("patient_name", "Nome"), ("patient_id", "ID do paciente"),
          ("birth_date", "Data de nascimento"), ("sex", "Sexo"))


def _norma(campo: str, valor) -> str:
    """Forma comparável: maiúsculas, sem o ^ do DICOM e sem espaço sobrando."""
    txt = str(valor or "").strip()
    if campo == "patient_name":
        txt = txt.replace("^", " ")
    return re.sub(r"\s+", " ", txt).upper()


def _mostra(campo: str, valor) -> str:
    txt = str(valor or "").strip()
    if not txt:
        return "(em branco)"
    if campo == "birth_date" and len(txt) == 8 and txt.isdigit():
        return f"{txt[6:8]}/{txt[4:6]}/{txt[:4]}"
    return txt.replace("^", " ")


def differences(infos: list) -> list:
    """Campos de identidade em que os exames não batem: [(rótulo, [valores])]."""
    saida = []
    for campo, rotulo in CAMPOS:
        vistos, mostrados = [], []
        for info in infos:
            n = _norma(campo, (info or {}).get(campo))
            if n not in vistos:
                vistos.append(n)
                mostrados.append(_mostra(campo, (info or {}).get(campo)))
        if len(vistos) > 1:
            saida.append((rotulo, mostrados))
    return saida


def summary(infos: list) -> str:
    """Texto do aviso quando os exames não são do mesmo paciente."""
    linhas = []
    for rotulo, valores in differences(infos):
        juntos = " ≠ ".join(valores)
        linhas.append(f"• Diferença em {rotulo}: {juntos}")
    return "\n".join(linhas)


def order(infos: list) -> list:
    """Exames do mais recente para o mais antigo: o primeiro é o atual, o resto é anterior."""
    def chave(info):
        return (str((info or {}).get("study_date") or ""), str((info or {}).get("study_time") or ""))
    return sorted(infos, key=chave, reverse=True)


def confirm(parent, infos: list) -> bool:
    """Pergunta antes de juntar exames de identidades diferentes. Sem diferença, não pergunta."""
    texto = summary(infos)
    if not texto:
        return True
    from PySide6.QtWidgets import QMessageBox
    caixa = QMessageBox(parent)
    caixa.setIcon(QMessageBox.Warning)
    caixa.setWindowTitle("Exames de pacientes diferentes")
    caixa.setText("Os exames escolhidos não têm a mesma identidade:")
    caixa.setInformativeText(texto + "\n\nAbrir mesmo assim, lado a lado, como se fossem "
                                     "do mesmo paciente?")
    caixa.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
    caixa.setDefaultButton(QMessageBox.Cancel)
    caixa.button(QMessageBox.Yes).setText("Abrir assim mesmo")
    caixa.button(QMessageBox.Cancel).setText("Cancelar")
    return caixa.exec() == QMessageBox.Yes
