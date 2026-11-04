"""Painel de produtividade (0.99.53, onda B6 do plano ViewerHub/Eden).

Conta os laudos **assinados** no período e agrupa por médico, modalidade, subespecialidade, prioridade ou
dia: quantos, quantas retificações, o tempo da chegada do exame à assinatura (mediana e p90, em horas) e
a parte entregue no prazo (as regras de prazo são as de Configurações ▸ Laudos ▸ Prioridade,
subespecialidade e prazos). Sem pesos por modalidade: um laudo é um laudo.
"""
from __future__ import annotations

from datetime import date, timedelta

AGRUPAR = {"medico": "Médico", "modalidade": "Modalidade", "subesp": "Subespecialidade",
           "prioridade": "Prioridade", "dia": "Dia"}
PERIODOS = {"hoje": "Hoje", "7d": "Últimos 7 dias", "30d": "Últimos 30 dias", "mes": "Este mês",
            "mes_passado": "Mês passado", "ano": "Este ano"}
COLS = ["Grupo", "Laudos", "Retificações", "Mediana (h)", "P90 (h)", "No prazo", "Fora do prazo"]


def periodo(chave: str, hoje: date | None = None) -> tuple[str, str]:
    h = hoje or date.today()
    if chave == "hoje":
        a = b = h
    elif chave == "7d":
        a, b = h - timedelta(days=6), h
    elif chave == "30d":
        a, b = h - timedelta(days=29), h
    elif chave == "mes":
        a, b = h.replace(day=1), h
    elif chave == "mes_passado":
        b = h.replace(day=1) - timedelta(days=1)
        a = b.replace(day=1)
    else:
        a, b = h.replace(month=1, day=1), h
    return a.isoformat(), b.isoformat()


def _quantil(v: list[float], q: float) -> float | None:
    if not v:
        return None
    v = sorted(v)
    pos = (len(v) - 1) * q
    i = int(pos)
    j = min(i + 1, len(v) - 1)
    return v[i] + (v[j] - v[i]) * (pos - i)


def agrupar(itens: list[dict], por: str = "medico") -> list[dict]:
    """Linhas do painel, da que tem mais laudos para a que tem menos (por dia: em ordem de data)."""
    grupos: dict[str, list[dict]] = {}
    for it in itens:
        grupos.setdefault(str(it.get(por) or "—"), []).append(it)
    out = []
    for nome, g in grupos.items():
        horas = [float(x["horas"]) for x in g if x.get("horas") is not None and x["horas"] >= 0]
        no = sum(1 for x in g if x.get("no_prazo"))
        out.append({"grupo": nome, "laudos": len(g), "retificacoes": sum(1 for x in g if x.get("retificacao")),
                    "mediana_h": _quantil(horas, 0.5), "p90_h": _quantil(horas, 0.9),
                    "no_prazo": no, "fora": len(g) - no, "pct_prazo": (100.0 * no / len(g)) if g else None})
    if por == "dia":
        return sorted(out, key=lambda r: r["grupo"])
    return sorted(out, key=lambda r: (-r["laudos"], r["grupo"]))


def total(itens: list[dict]) -> dict:
    t = agrupar(itens, "_todos_")
    return t[0] if t else {"grupo": "—", "laudos": 0, "retificacoes": 0, "mediana_h": None, "p90_h": None,
                           "no_prazo": 0, "fora": 0, "pct_prazo": None}


def _h(x) -> str:
    return "" if x is None else f"{x:.1f}".replace(".", ",")


def celulas(linha: dict) -> list[str]:
    pct = linha.get("pct_prazo")
    return [linha["grupo"], str(linha["laudos"]), str(linha["retificacoes"]), _h(linha["mediana_h"]),
            _h(linha["p90_h"]), (f"{linha['no_prazo']} ({pct:.0f}%)" if pct is not None else ""), str(linha["fora"])]


def csv(linhas: list[dict], titulo: str = "Grupo") -> str:
    out = [";".join([titulo] + COLS[1:])]
    for li in linhas:
        out.append(";".join(c.replace(";", ",") for c in celulas(li)))
    return "\n".join(out) + "\n"
