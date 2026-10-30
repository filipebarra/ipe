"""Queda intermitente ao refazer a tira de séries (0.79).

`QListWidget.clear()` às vezes derrubava o programa (falha de segmentação no Shiboken,
`unregisterWrapper`) quando a tira era refeita logo depois de abrir a janela da curva
tempo-intensidade — no PySide 6.11.2 (o do computador dele) em ~60% dos processos, no 6.12 em
~12%. Com os itens saindo um a um por `takeItem` (`tabelas.esvaziar_lista`) não caiu em 70
processos.

Quem detecta o defeito é `test_measure_tools.py::test_time_intensity_curve` (as duas variações no
mesmo processo): sem a correção ele derrubava o pytest em ~60% das rodadas no PySide 6.11.2. Uma
cópia mais curta da sequência não reproduziu a queda, e teste que não reproduz não guarda nada —
aqui fica só o contrato do `esvaziar_lista`.
"""
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from ipe.ui.tabelas import esvaziar_lista


def test_esvaziar_lista_tira_tudo_sem_sinal():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    lst = QListWidget()
    for i in range(5):
        lst.addItem(QListWidgetItem(str(i)))
    lst.setCurrentRow(2)
    sinais = []
    lst.currentRowChanged.connect(sinais.append)
    esvaziar_lista(lst)
    assert lst.count() == 0 and not sinais


def test_esvaziar_lista_devolve_o_bloqueio_como_estava():
    """Quem chama pode ter bloqueado os sinais para repovoar a lista (as folhas do filme fazem
    isso): esvaziar não pode desbloquear no meio."""
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    lst = QListWidget()
    lst.addItem(QListWidgetItem("a"))
    lst.blockSignals(True)
    esvaziar_lista(lst)
    assert lst.signalsBlocked()
    lst.blockSignals(False)
    esvaziar_lista(lst)
    assert not lst.signalsBlocked()

