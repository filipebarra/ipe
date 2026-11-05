"""Ajuda dos testes de menu: os menus do botão direito têm submenus desde a 0.99.78."""


def todas(menu):
    """Todas as ações do menu, descendo nos submenus (o próprio item do submenu também vem)."""
    out = []
    for a in menu.actions():
        out.append(a)
        if a.menu() is not None:
            out.extend(todas(a.menu()))
    return out


def submenu(menu, caminho: str):
    """O submenu por caminho: "Imagem/Cor (tabela de cores)"."""
    m = menu
    for parte in caminho.split("/"):
        m = next(a.menu() for a in m.actions() if a.menu() is not None and a.text() == parte)
    return m
