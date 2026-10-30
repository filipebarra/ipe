"""Colunas que o usuário pode arrastar, em toda tabela do programa.

Pedido dele: *"um ajuste em tudo que tem tabela no programa: dimensões ajustáveis das colunas (sei
que em configurações de nós dicom hoje não tem como ajustar)"*.

O Qt só deixa arrastar a divisa quando o modo da coluna é `Interactive`. Onde o código pedia
`Stretch` ou `ResizeToContents` — que é a maioria, porque dá uma largura boa de saída — a divisa
fica travada: a largura é boa até o dia em que não é, e aí não há o que fazer. Aqui a largura de
saída continua a mesma (quem a calculou continua calculando), e o que muda é que ela deixa de ser
definitiva.

A última coluna continua esticando para ocupar a sobra, senão a tabela fica com um vazio à direita.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHeaderView

MINIMO = 28          # px: coluna menor que isto some e o usuário não a acha de volta


def colunas_ajustaveis(tabela, estica_ultima: bool = True, minimo: int = MINIMO):
    """Deixa as colunas de `tabela` (QTableWidget/QTableView/QTreeWidget) arrastáveis.

    Chame **depois** de configurar as larguras: o modo da coluna é o que o Qt consulta na hora de
    arrastar, e quem escreve por último manda. Devolve a própria tabela, para encadear.
    """
    cab = None
    for nome in ("horizontalHeader", "header"):
        obtem = getattr(tabela, nome, None)
        if callable(obtem):
            cab = obtem()
            break
    if cab is None:
        return tabela
    larguras = [cab.sectionSize(i) for i in range(cab.count())]
    cab.setSectionResizeMode(QHeaderView.Interactive)
    cab.setStretchLastSection(bool(estica_ultima))
    cab.setMinimumSectionSize(int(minimo))
    cab.setCascadingSectionResizes(False)
    # `setSectionResizeMode` zera a largura calculada em algumas versões: devolve o que estava
    for i, w in enumerate(larguras):
        if w > 0 and cab.sectionSize(i) != w:
            cab.resizeSection(i, w)
    return tabela


def esvaziar_lista(lista) -> None:
    """Tira todos os itens de um QListWidget, um a um, em vez de `clear()`.

    Defeito achado na 0.79: o `clear()` da tira de séries derrubava o programa às vezes (1 em 7 a
    1 em 8 rodadas), com falha de segmentação dentro do Shiboken (`unregisterWrapper`). O
    `clear()` apaga os itens pelo lado do C++, e o PySide tenta soltar o espelho Python de cada
    um; se o coletor de lixo do Python já mexeu nesse espelho, o ponteiro está velho. Com
    `takeItem` o item volta a ser do Python, e quem o apaga é só o Python.
    """
    antes = lista.blockSignals(True)
    try:
        while lista.count():
            it = lista.takeItem(lista.count() - 1)
            del it
    finally:
        # devolve como estava: quem chama pode ter bloqueado os sinais para repovoar a lista em
        # silêncio, e desbloquear aqui faria cada item novo disparar "mudou a linha atual"
        lista.blockSignals(antes)

