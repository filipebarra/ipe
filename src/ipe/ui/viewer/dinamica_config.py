"""Configuração da avaliação dinâmica da mama (0.99.9): parâmetros pré-configurados e layouts.

Pedido dele: *"na parte dinâmica da mama, poder escolher o layout. Hoje eu tenho alguns modelos
pré-definidos. Crie uma parte no menu onde eu possa deixar pré-configurados os parâmetros da
dinâmica e também configurar os layouts, incluindo séries e cor. A configuração do layout pode ser
parecida com a que já temos em protocolos de exibição."*

Um layout é uma grade (linhas × colunas) e, por quadro, **o que entra** (um mapa, uma fase da
dinâmica ou outra série do exame, como a T2 ou a difusão) e **a cor**. Os cinco modelos que
existiam viraram os layouts de fábrica, com os mesmos nomes — protocolos de exibição antigos que
apontavam para eles pelo número continuam abrindo o mesmo arranjo.

Tudo mora em settings.json: `dyn.layouts` (a lista), `dyn.layout_padrao` (o nome do que abre
quando nada diz outra coisa), `dyn.padrao` (os parâmetros) e `dyn.origem_parametros` ("padrao" =
começar pelos parâmetros daqui; "ultimos" = pelos últimos usados no botão, como era até a 0.99.8).
"""
from __future__ import annotations

import copy

#: o que um quadro do layout pode mostrar
VISTAS: dict[str, str] = {
    "cin": "Mapa cinético (6 cores)",
    "msi": "MSI — inclinação máxima",
    "pei": "PEI — integral do realce",
    "ser": "SER",
    "ei": "Realce inicial",
    "sub": "Subtração (inicial − pré)",
    "ttp": "Tempo até o pico",
    "ph:pre": "Fase: pré-contraste",
    "ph:early": "Fase: inicial (a do SER)",
    "ph:late": "Fase: tardia (a do SER)",
    **{f"ph:pos{k}": f"Fase: {k}ª pós-contraste" for k in range(1, 7)},
    "ph:ult": "Fase: última",
    "serie": "Outra série do exame (T2, difusão…)",
    "": "Vazio",
}
MAPAS = ("cin", "msi", "pei", "ser", "ei", "sub", "ttp")

#: cor do quadro: "" = a do mapa (a última que ele escolheu para aquele mapa, ou a de fábrica)
COR_PADRAO = ""
COR_CINZA = "gray"


def quadro(q: dict | str | None = None) -> dict:
    """Quadro com todos os campos (aceita a forma curta: só a chave da vista)."""
    if isinstance(q, str):
        q = {"vista": q}
    q = dict(q or {})
    vista = str(q.get("vista", "") or "")
    return {"vista": vista if vista in VISTAS else "", "serie": str(q.get("serie", "") or ""),
            "cor": str(q.get("cor", "") or "")}


def _fab(nome: str, rows: int, cols: int, vistas: list[str]) -> dict:
    return {"nome": nome, "rows": rows, "cols": cols, "quadros": [quadro(v) for v in vistas]}


#: os cinco modelos de antes, na mesma ordem (o número antigo continua valendo)
FABRICA: list[dict] = [
    _fab("Mapa cinético + curva", 1, 1, ["cin"]),
    _fab("Mapa cinético, subtração e fase inicial + curva", 1, 3, ["cin", "sub", "ph:early"]),
    _fab("MSI + curva", 1, 1, ["msi"]),
    _fab("MSI, PEI e SER + curva", 1, 3, ["msi", "pei", "ser"]),
    _fab("MSI, SER, subtração e fase inicial + curva", 2, 2, ["msi", "ser", "sub", "ph:early"]),
]

#: os parâmetros de fábrica da janela da dinâmica (os mesmos valores de antes)
PARAMETROS_FABRICA: dict = {
    "pre": 0, "threshold_pct": 50.0, "threshold_all": False, "noise_pct": 5.0, "rapido_pct": 100.0,
    "tardio_pct": 10.0, "sinal_min_pct": 10.0, "relative": True, "motion": False,
}


def normalizado(lay: dict) -> dict:
    rows = max(1, min(4, int(lay.get("rows", 1) or 1)))
    cols = max(1, min(4, int(lay.get("cols", 1) or 1)))
    qs = [quadro(q) for q in (lay.get("quadros") or [])]
    qs = (qs + [quadro("") for _ in range(rows * cols)])[: rows * cols]
    return {"nome": str(lay.get("nome", "") or "Layout").strip() or "Layout", "rows": rows, "cols": cols,
            "quadros": qs}


def layouts(settings) -> list[dict]:
    gravado = settings.get("dyn.layouts", None) if settings is not None else None
    if isinstance(gravado, list) and gravado:
        return [normalizado(x) for x in gravado if isinstance(x, dict)]
    return copy.deepcopy(FABRICA)


def nomes(settings) -> list[str]:
    return [lay["nome"] for lay in layouts(settings)]


def indice_padrao(settings) -> int:
    nome = settings.get("dyn.layout_padrao", "") if settings is not None else ""
    lista = nomes(settings)
    return lista.index(nome) if nome in lista else 0


def escolher(settings, indice=None, nome: str = "") -> dict:
    """O layout pelo nome (se existir) ou pelo número; sem nada, o padrão."""
    lista = layouts(settings)
    if nome:
        for lay in lista:
            if lay["nome"] == nome:
                return lay
    if indice is not None:
        try:
            i = int(indice)
        except (TypeError, ValueError):
            i = -1
        if 0 <= i < len(lista):
            return lista[i]
    return lista[indice_padrao(settings)]


def parametros_iniciais(settings) -> dict:
    """Com o que a janela da dinâmica abre.

    Até a 0.99.8 era sempre "os últimos usados". Agora, se ele deixou parâmetros pré-configurados
    (Preferências ▸ Dinâmica da mama), começa por eles — a não ser que ele tenha escolhido lá
    continuar com os últimos usados. Sem pré-configuração nenhuma, nada muda: os últimos usados."""
    base = dict(PARAMETROS_FABRICA)
    padrao = settings.get("dyn.padrao", None) if settings is not None else None
    ultimos = settings.get("dyn.ultimos", None) if settings is not None else None
    origem = settings.get("dyn.origem_parametros", "") if settings is not None else ""
    if not origem:
        origem = "padrao" if isinstance(padrao, dict) and padrao else "ultimos"
    if origem == "padrao" and isinstance(padrao, dict):
        base.update(padrao)
    elif isinstance(ultimos, dict):
        base.update(ultimos)
    base.pop("uids", None)
    lista = nomes(settings)
    # "Layout que abre" (Preferências ▸ Dinâmica da mama) vale nos dois modos, quando escolhido
    escolhido = settings.get("dyn.layout_padrao", "") if settings is not None else ""
    if escolhido in lista:
        base["layout_nome"] = escolhido
    if base.get("layout_nome") in lista:
        base["layout"] = lista.index(base["layout_nome"])
    else:
        base.pop("layout_nome", None)
        try:
            i = int(base.get("layout", indice_padrao(settings)))
        except (TypeError, ValueError):
            i = 0
        base["layout"] = i if 0 <= i < len(lista) else 0
    return base


def descrever(q: dict) -> str:
    q = quadro(q)
    if not q["vista"]:
        return "vazio"
    txt = VISTAS[q["vista"]]
    if q["vista"] == "serie":
        txt = f"série {q['serie'].replace('|', ' ou ')}" if q["serie"] else "série (não escolhida)"
    if q["cor"]:
        from ipe.imaging import colormaps as CM
        nome = "cinza" if q["cor"] == COR_CINZA else CM.COLORMAPS.get(q["cor"], (q["cor"],))[0]
        txt += f" · cor {nome}"
    return txt
