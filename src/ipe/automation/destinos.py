"""Mandar o resultado do CAD/IA para outros nós DICOM depois de feito (Preferências ▸ CAD/IA, 0.99).

As séries do CAD/IA (cópia sem implante, SEG e tabela de órgãos) ficam só neste computador por padrão:
o envio do exame inteiro as pula. Aqui é o contrário — o médico escolheu destinos, e só essas séries
vão, de propósito (envio por série, que não passa pelo filtro do exame inteiro).
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def nos_escolhidos(repo, ids) -> list[dict]:
    """Os nós ativos cujos ids estão em `ids` (os que sumiram ou foram desligados ficam de fora)."""
    alvo = {int(i) for i in (ids or []) if str(i).strip().lstrip("-").isdigit()}
    if not alvo:
        return []
    try:
        return [n for n in repo.nodes(only_active=True, todos=True) if n["id"] in alvo]
    except Exception:  # noqa: BLE001
        log.exception("nós de destino do CAD/IA")
        return []


def enviar(net, repo, study_uid: str, series_uids, ids, rotulo: str, ferramenta: str | None = None) -> int:
    """Põe na fila um envio por destino. Devolve quantos destinos receberam o pedido.

    0.100.124: vale também o que se escolheu em Configurações ▸ CAD/IA ▸ "O que as IAs gravam e enviam": os
    destinos de todas as IAs entram junto com os da ferramenta, só vão as séries das classes marcadas (SEG,
    tabelas, overlay colorido) e, com o overlay ligado, a série colorida é criada antes (em segundo plano).
    `ferramenta` ("abdome", "coluna", "figado"…): a escolha dela, em Configurações ▸ CAD/IA, vale por cima da global."""
    from ipe.ai import saidas_ia as SI
    series_uids = [u for u in (series_uids or []) if u]
    if net is None or not series_uids:
        return 0
    ctx = SI.contexto()
    settings = ctx.get("settings")
    nos = nos_escolhidos(repo, SI.ids_de_destino(settings, ids, ferramenta))

    def mandar(lista) -> None:
        lista = SI.filtrar(repo, settings, lista, ferramenta)
        if not lista:
            return
        for no in nos:
            try:
                net.send(no, None, [study_uid], f"{rotulo} → {no.get('name', '')}", series_uids=lista)
            except Exception:  # noqa: BLE001
                log.exception("enviar %s para %s", rotulo, no.get("name"))

    if settings is not None and SI.efetivo(settings, "overlay", ferramenta) and ctx.get("db") is not None:
        def trabalho():
            return SI.completar(repo, ctx["db"], ctx["storage"], settings, series_uids, ferramenta)

        def pronto(out, err) -> None:
            if err is not None:
                log.warning("overlay colorido de %s: %s", study_uid, err)
            mandar(out if err is None and out else series_uids)

        net.run_async(trabalho, pronto)
        return len(nos)
    mandar(series_uids)
    return len(nos)
