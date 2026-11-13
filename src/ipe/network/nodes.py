"""Quais nós remotos servem para cada função: busca, busca de anteriores e envio."""

from __future__ import annotations

PRIORS_SETTING = "priors.nodes"          # "all" ou lista de ids de nós


# Nó de consulta é o que sabe buscar e baixar: DIMSE (C-FIND/C-GET) ou DICOMweb (QIDO/WADO).
# O resto do programa não precisa saber qual é — os dois clientes devolvem o mesmo dicionário.
# 0.100.37: "servidor" = nó que o servidor central compartilha (no modo cliente; busca e baixa pelo servidor)
CONSULTA = ("dimse", "dicomweb", "servidor")


def _dimse(repo) -> list[dict]:
    return [n for n in repo.nodes(only_active=True) if n["kind"] in CONSULTA]


def search_nodes(repo) -> list[dict]:
    """Nós marcados para a busca ("Todos os nós de busca", chamada externa, buscas agendadas)."""
    return [n for n in _dimse(repo) if n["use_in_search"]]


def prior_candidates(repo) -> list[dict]:
    """Nós marcados, no cadastro, para a busca de anteriores."""
    return [n for n in _dimse(repo) if n["use_in_priors"]]


def prior_selection(settings) -> list[int] | None:
    """None = todos os nós de anteriores; senão, só os ids escolhidos."""
    sel = settings.get(PRIORS_SETTING, "all") if settings is not None else "all"
    if sel == "all" or not isinstance(sel, list):
        return None
    return [int(x) for x in sel]


def prior_nodes(repo, settings) -> list[dict]:
    """Nós usados na busca por anteriores (painel e pré-busca automática)."""
    nodes = prior_candidates(repo)
    sel = prior_selection(settings)
    if sel is None:
        return nodes
    chosen = [n for n in nodes if n["id"] in sel]
    return chosen


def set_prior_selection(settings, ids: list[int] | None) -> None:
    settings.set(PRIORS_SETTING, "all" if ids is None else [int(i) for i in ids])
    settings.save()


def send_nodes(repo) -> list[dict]:
    """Nós que aparecem em "Enviar para"."""
    return [n for n in _dimse(repo) if n["use_in_send"]]
