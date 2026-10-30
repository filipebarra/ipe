"""Submenu “Enviar para”: nós de envio e, em cada um, as identidades (outra modalidade).

Usado pela lista do banco e pela busca no PACS, para os dois menus serem iguais.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu


def preencher_envio(menu: QMenu, repo, escolher: Callable[[int, int | None], None]) -> None:
    """Põe em `menu` um item por nó de envio; `escolher(node_id, identity_id)` ao clicar."""
    from ipe.network.nodes import send_nodes
    targets = send_nodes(repo)
    for n in targets:
        idents = [i for i in repo.identities()
                  if not i["allowed_nodes"] or str(n["id"]) in i["allowed_nodes"].split(",")]
        if idents:
            sub = menu.addMenu(n["name"])
            sub.addAction("como este programa", lambda nid=n["id"]: escolher(nid, None))
            for i in idents:
                sub.addAction(f"como {i['name']} ({i['ae_title']})",
                              lambda nid=n["id"], iid=i["id"]: escolher(nid, iid))
        else:
            menu.addAction(n["name"], lambda nid=n["id"]: escolher(nid, None))
    if menu.isEmpty():
        menu.addAction(QAction("(nenhum nó marcado para envio — Rede → Configurar nós)", menu,
                               enabled=False))
