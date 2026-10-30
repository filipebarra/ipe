"""Pré-cálculo da dinâmica na chegada: o exame abre pronto, sem gravar nem mandar nada.

O que o CADstream fazia era processar na chegada e devolver séries derivadas ao PACS. Aqui a
escolha foi outra, do usuário: **nada é gravado como série e nada sai**. O que o programa adianta
é o trabalho caro — descobrir quais séries formam a dinâmica e **decodificar os quadros delas** —
para que, quando ele abrir o exame, a dinâmica suba na hora em vez de ler o disco inteiro de novo.

Por que decodificar é o que vale: medindo no acervo, montar o volume de um mapa numa RM de mama
leva ~7 s em 100 cortes × 4 fases, e quase tudo é leitura e decodificação dos arquivos. Com os
quadros já no cache de imagens (o mesmo que o visualizador usa), a conta do mapa é aritmética de
array, e é rápida.

Limite de propósito: o cache de quadros tem tamanho máximo em MB, e aquecer um exame novo não
pode expulsar o exame que o médico está lendo. Por isso o pré-cálculo para quando passa do que
cabe, e diz quantos quadros conseguiu.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Fração do cache de quadros que um pré-cálculo pode ocupar.
FATIA_DO_CACHE = 0.4
# Motivos de parada (chave de programa, não texto de tela).
SEM_DINAMICA = "não achei dinâmica neste exame"
CANCELADO = "cancelado"
CACHE_CHEIO = "cache cheio"


def regra_serve(cfg: dict, info: dict) -> bool:
    """A regra vale para este exame? Modalidade e pedaço da descrição, como as outras regras."""
    mods = [m.strip().upper() for m in (cfg.get("modalities") or []) if m.strip()]
    if mods and not any(m in (info.get("modalities") or "").upper() for m in mods):
        return False
    trecho = (cfg.get("description_contains") or "").strip().lower()
    if trecho and trecho not in (info.get("description") or "").lower():
        return False
    return True


def series_da_dinamica(repo, study_uid: str) -> list[tuple[str, list]]:
    """As séries que formam a dinâmica deste exame: [(series_uid, quadros)], em ordem de fase."""
    from ipe.imaging import phases as P
    from ipe.imaging.series import build_frames
    candidatas = []
    for s in repo.series_for_study(study_uid):
        quadros = build_frames(repo.instances_for_series(s.series_uid), s.series_uid)
        if quadros:
            candidatas.append((s.series_uid, quadros, s.series_number or 0, s.modality or "",
                               s.description or ""))
    por = {c[0]: c for c in candidatas}
    grupos = P.detect(candidatas)
    if not grupos:
        return []
    maior = max(grupos, key=len)
    return [(u, por[u][1]) for u in maior] if len(maior) >= 3 else []


def aquecer(repo, cache, study_uid: str, parar=lambda: False) -> dict:
    """Decodifica os quadros da dinâmica para o cache. Devolve o que conseguiu fazer.

    Não grava arquivo, não cria série, não manda nada: só deixa os quadros prontos na memória.
    """
    fases = series_da_dinamica(repo, study_uid)
    out = {"fases": len(fases), "quadros": 0, "parou": "", "series": [u for u, _f in fases]}
    if not fases:
        out["parou"] = SEM_DINAMICA
        return out
    limite = int(getattr(cache, "max_bytes", 0) * FATIA_DO_CACHE)
    gasto = 0
    for _uid, quadros in fases:
        for q in quadros:
            if parar():
                out["parou"] = CANCELADO
                return out
            if cache.contains(q):
                continue
            try:
                img = cache.get(q)
            except Exception:  # noqa: BLE001 - um arquivo ruim não pode derrubar o pré-cálculo
                log.debug("quadro que não abriu no pré-cálculo", exc_info=True)
                continue
            out["quadros"] += 1
            gasto += int(getattr(img.pixels, "nbytes", 0))
            if limite and gasto >= limite:
                out["parou"] = CACHE_CHEIO
                return out
    return out


def resumo(out: dict) -> str:
    base = f"Dinâmica: {out['fases']} fases, {out['quadros']} quadros prontos"
    return f"{base} ({out['parou']})" if out.get("parou") else base
