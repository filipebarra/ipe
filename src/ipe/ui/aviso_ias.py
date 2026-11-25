"""0.100.121: o aviso "faltam IAs neste computador", com "Não me notificar mais"."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QMessageBox

from ipe.ai import aviso_instalacao as AV
from ipe.core.i18n import tr


def avisar(win, f: dict | None = None) -> str:
    """Devolve "" (nada a avisar), "depois", "instalar" ou "nunca"."""
    s = win.settings
    if f is None:
        if not AV.ligado(s):
            return ""
        f = AV.faltando(s)
    if not AV.tem_o_que_avisar(f):
        return ""
    caixa = QMessageBox(win)
    caixa.setIcon(QMessageBox.Information)
    caixa.setWindowTitle(tr("IAs não instaladas"))
    if f["segmentacao"]:
        caixa.setText(tr("Este computador ainda não tem as IAs instaladas."))
        caixa.setInformativeText(tr(
            "Falta a segmentação de órgãos (TotalSegmentator), a base da maioria das IAs do Ipê. A instalação é feita "
            "uma vez, com internet, e leva alguns minutos. Sem ela, só as IAs que não dependem dela funcionam."))
        rotulo = tr("Instalar a segmentação")
    else:
        caixa.setText(tr("Faltam modelos de IA neste computador."))
        caixa.setInformativeText(tr("Ainda não estão instalados:") + "\n• " + "\n• ".join(f["extras"]))
        rotulo = tr("Instalar os modelos extras")
    b_inst = caixa.addButton(rotulo, QMessageBox.AcceptRole)
    caixa.addButton(tr("Depois"), QMessageBox.RejectRole)
    nunca = QCheckBox(tr("Não me notificar mais"))
    caixa.setCheckBox(nunca)
    caixa.exec()
    res = "depois"
    if caixa.clickedButton() is b_inst:
        res = "instalar"
    if nunca.isChecked():
        s.set(AV.CHAVE_AVISAR, False)
        s.save()
        res = "nunca" if res != "instalar" else res
    if res == "instalar":
        from ipe.ui import segmentacao as SG
        if f["segmentacao"]:
            SG.abrir_instalador(win, perguntar=False)
        else:
            SG.abrir_instalador_extras(win, settings=s, perguntar=False)
    return res
