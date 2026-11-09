"""0.99.97: ajudantes dos testes do visualizador web para a interface nova (barra de ícones, menus, abas)."""
import time


def layout(pg, lxc: str) -> None:
    """Escolhe a grade (\"2x2\") pelo ícone de layout."""
    pg.click("nav.barra button[aria-label='Layout dos quadros']")
    pg.click(f".menu [data-layout='{lxc}']")


def ferramenta(pg, f: str, botao: str = "esq") -> None:
    """Dá a função f ao botão do mouse (esq, meio, dir) — o mesmo que clicar no ícone com aquele botão."""
    pg.evaluate(f"() => window.__ipeEscolher('{f}', '{botao}')")


def botoes(pg) -> dict:
    return pg.evaluate("() => window.__ipeBotoes()")


def icone(pg, rotulo: str) -> None:
    pg.click(f"nav.barra button[aria-label='{rotulo}']")


def menu(pg, texto: str) -> None:
    """Clica no item do menu aberto que tem o texto."""
    pg.locator(".menu .menu-item", has_text=texto).first.click()


def espessura(pg, mm: int | None = None, projecao: str | None = None) -> None:
    if mm is not None:
        icone(pg, "Espessura e projeção")
        menu(pg, f"{mm} mm" if mm else "Corte fino")
    if projecao is not None:
        icone(pg, "Espessura e projeção")
        menu(pg, {"mip": "MIP", "minip": "MinIP", "media": "Média"}[projecao])


def aba(pg, nome: str) -> None:
    pg.click(f".abas button[data-aba='{nome}']")
    time.sleep(0.05)


def quadros(pg) -> str:
    return pg.evaluate("() => `${window.__ipeGrade.linhas}x${window.__ipeGrade.colunas}`")
