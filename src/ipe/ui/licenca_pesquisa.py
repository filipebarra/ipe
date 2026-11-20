"""0.100.79: antes de baixar um modelo de PESQUISA (zonas da próstata, PI-CAI), a pessoa lê a licença e aceita
"uso em pesquisa e ensino, não clínico, não comercial". Sem o aceite, o instalador não baixa e a IA não roda.

Pedido dele (20/11/2026): *"Antes de baixar, o programa mostra a licença e a pessoa aceita: 'uso em pesquisa e
ensino, não clínico, não comercial'"*.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QLabel, QMessageBox, QTextBrowser, QVBoxLayout,
)

from ipe.ai import extras as EX


class LicencaDialog(QDialog):
    def __init__(self, modelo: str, parent=None):
        super().__init__(parent)
        lic = EX.LICENCAS[modelo]
        self.setWindowTitle("Modelo de pesquisa — licença")
        self.resize(640, 520)
        lay = QVBoxLayout(self)
        aviso = QLabel("MODELO DE PESQUISA — não usar para diagnóstico")
        aviso.setStyleSheet("background:#b71c1c;color:white;padding:8px;border-radius:4px;font-weight:bold")
        lay.addWidget(aviso)
        titulo = QLabel(lic["titulo"])
        titulo.setStyleSheet("font-size:15px;font-weight:bold")
        titulo.setWordWrap(True)
        lay.addWidget(titulo)
        t = QTextBrowser()
        t.setOpenExternalLinks(True)
        links = "".join(f'<li><a href="{u}">{u}</a></li>' for u in lic["links"])
        corpo = lic["texto"].replace("\n\n", "</p><p>")
        t.setHtml(f"<p>{corpo}</p><p><b>O que será baixado:</b> {lic['baixa']}.</p>"
                  f"<p><b>Crédito:</b> {EX.CREDITOS.get(modelo, '')}</p><ul>{links}</ul>")
        lay.addWidget(t, 1)
        self.aceito = QCheckBox(f"Li a licença e aceito: {EX.ACEITE}.")
        lay.addWidget(self.aceito)
        bb = QDialogButtonBox()
        self.b_ok = bb.addButton("Aceitar e instalar", QDialogButtonBox.AcceptRole)
        bb.addButton("Cancelar", QDialogButtonBox.RejectRole)
        self.b_ok.setEnabled(False)
        self.aceito.toggled.connect(self.b_ok.setEnabled)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


def pedir_aceite(janela, modelo: str, settings) -> bool:
    """Mostra a licença; True se a pessoa aceitou (o aceite fica gravado, com quem e quando)."""
    if EX.licenca_aceita(settings, modelo):
        return True
    dlg = LicencaDialog(modelo, janela)
    if dlg.exec() != QDialog.Accepted or not dlg.aceito.isChecked():
        return False
    from ipe.auth import session as auth
    quem = getattr(auth.get(), "username", "") or ""
    EX.aceitar_licenca(settings, modelo, quem)
    return True


def instalar_pesquisa(janela, modelo: str, settings) -> bool:
    """Aceite (se ainda não houve) e o instalador só deste modelo."""
    if not pedir_aceite(janela, modelo, settings):
        return False
    from ipe.ui.segmentacao import abrir_instalador_extras
    return abrir_instalador_extras(janela, (modelo,), settings, perguntar=False)


def escolher_e_instalar(janela, settings) -> bool:
    """Configurações ▸ CAD/IA ▸ Modelos de pesquisa: qual instalar (com o estado de cada um)."""
    from PySide6.QtWidgets import QInputDialog
    itens = []
    for m in EX.PESQUISA:
        pr = EX.prontidao(m, settings)
        itens.append(f"{EX.NOMES[m]} — " + ("pronto" if pr.pronto else pr.falta))
    escolha, ok = QInputDialog.getItem(janela, "Modelos de pesquisa (próstata)",
                                       "Modelos de PESQUISA e ensino (não clínico, não comercial), instalados à parte. "
                                       "Antes de baixar, você lê e aceita a licença.\n\nQual instalar?", itens, 0, False)
    if not ok:
        return False
    modelo = EX.PESQUISA[itens.index(escolha)]
    if EX.prontidao(modelo, settings).pronto:
        QMessageBox.information(janela, "Modelos de pesquisa", f"{EX.NOMES[modelo]} já está instalado.")
        return True
    return instalar_pesquisa(janela, modelo, settings)
