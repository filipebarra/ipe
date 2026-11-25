"""0.100.121: ao abrir, avisa se este computador não tem as IAs instaladas (a parte sem tela)."""
from __future__ import annotations

import os

CHAVE_AVISAR = "ia.avisar_nao_instaladas"


def ligado(settings) -> bool:
    if os.environ.get("IPE_SEM_GITHUB"):          # testes e quem não quer nada ao abrir
        return False
    return bool(settings.get(CHAVE_AVISAR, True))


def faltando(settings) -> dict:
    """{"segmentacao": bool, "extras": [nomes dos modelos extras que não estão prontos]}.
    Sem a segmentação, os extras nem são listados (dependem dela): o aviso pede a segmentação primeiro."""
    from ipe.ai import extras as EX
    from ipe.ai import totalseg as TS
    if not TS.instalado(settings):
        return {"segmentacao": True, "extras": []}
    sem = [EX.NOMES[m] for m in EX.MODELOS if not EX.prontidao(m, settings).pronto]
    return {"segmentacao": False, "extras": sem}


def tem_o_que_avisar(f: dict) -> bool:
    return bool(f["segmentacao"] or f["extras"])
