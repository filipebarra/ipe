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
        return [n for n in repo.nodes(only_active=True) if n["id"] in alvo]
    except Exception:  # noqa: BLE001
        log.exception("nós de destino do CAD/IA")
        return []


def enviar(net, repo, study_uid: str, series_uids, ids, rotulo: str) -> int:
    """Põe na fila um envio por destino. Devolve quantos destinos receberam o pedido."""
    series_uids = [u for u in (series_uids or []) if u]
    if net is None or not series_uids:
        return 0
    n = 0
    for no in nos_escolhidos(repo, ids):
        try:
            net.send(no, None, [study_uid], f"{rotulo} → {no.get('name', '')}", series_uids=series_uids)
            n += 1
        except Exception:  # noqa: BLE001
            log.exception("enviar %s para %s", rotulo, no.get("name"))
    return n
