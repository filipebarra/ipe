"""Fígado na RM: medidas e confirmações (0.100.101) — a tabela, como a "Densidade mamária: medidas e confirmações".

Pedido dele (22/11/2026): *"crie uma tabela para os achados de esteatose, rigidez e ferro, como já temos para a
densidade mamária na mamografia"*. Uma linha por exame com o resultado da IA de fígado (`figado_rm`): PDFF e grau,
fração de sinal da dupla eco, R2* e ferro estimado (LIC), rigidez (kPa) e a faixa — com a situação de cada achado
(sugerido, confirmado, corrigido, descartado), quem revisou e quando. Os números são os que valem: os corrigidos pelo
médico por cima dos da IA. Sem Qt.
"""
from __future__ import annotations

from ipe.ai import achados as AC
from ipe.ai import figado_rm as F

ESTADOS = {"sugerido": "sugerido", "confirmado": "confirmado", "corrigido": "corrigido", "descartado": "descartado"}
SITUACOES = (("todas", "Todas"), ("revisadas", "Revisadas (confirmadas ou corrigidas)"),
             ("pendentes", "Não revisadas"), ("esteatose", "Com esteatose (PDFF ≥ 5%)"),
             ("ferro", "Com sobrecarga de ferro (LIC ≥ 3,2)"), ("rigidez", "Com rigidez acima do normal"))


def _v(a: dict | None, k: str):
    if not a:
        return None
    v = (AC.numeros_validos(a).get(k) or {}).get("v")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def linha(base: dict, achados: list[dict]) -> dict:
    """Junta os achados de um exame numa linha: `base` traz o paciente e o exame."""
    por_tipo: dict[str, dict] = {}
    for a in achados:
        if a.get("estado") == "descartado" and a.get("tipo") in por_tipo:
            continue
        por_tipo[a.get("tipo", "")] = a
    g, fe, dx, rg = (por_tipo.get(t) for t in (F.TIPO_GORDURA, F.TIPO_FERRO, F.TIPO_DIXON, F.TIPO_RIGIDEZ))
    pdff, lic, r2, r15 = _v(g, "pdff_mediana"), _v(fe, "lic"), _v(fe, "r2_mediana"), _v(fe, "r2_15")
    kpa = _v(rg, "kpa_media")
    est = {nome: (a.get("estado") or "sugerido") for nome, a in (("gordura", g), ("ferro", fe), ("rigidez", rg),
                                                                  ("dixon", dx)) if a}
    revisados = [a for a in (g, fe, rg, dx) if a and a.get("estado") in ("confirmado", "corrigido")]
    ultimo = max(revisados, key=lambda a: str(a.get("revisado_em") or ""), default=None)
    from ipe.ai import elastografia_rm as EL
    return {**base,
            "pdff": pdff, "grau": F.grau_da_gordura(pdff) if pdff is not None else None,
            "gordura": F.resultado_do_achado(g) if g else "", "ff_sinal": _v(dx, "ff_sinal"),
            "r2": r2, "r2_15": r15, "lic": lic, "ferro": F.resultado_do_achado(fe) if fe else "",
            "kpa": kpa, "faixa": EL.faixa(kpa) if kpa is not None else "",
            "rigidez": F.resultado_do_achado(rg) if rg else "",
            "estados": est, "revisor": (ultimo or {}).get("revisor", "") if ultimo else "",
            "revisado_em": str((ultimo or {}).get("revisado_em") or "")[:16] if ultimo else "",
            "medido_em": str(min((str(a.get("criado_em") or "") for a in achados), default=""))[:16]}


def situacao(r: dict) -> str:
    est = list((r.get("estados") or {}).values())
    if not est:
        return "Sem achado"
    if all(e in ("confirmado", "corrigido", "descartado") for e in est):
        return "Revisada"
    if any(e in ("confirmado", "corrigido") for e in est):
        return "Revisada em parte"
    return "Não revisada"


def filtrar(linhas: list[dict], qual: str) -> list[dict]:
    if qual == "revisadas":
        return [r for r in linhas if situacao(r) == "Revisada"]
    if qual == "pendentes":
        return [r for r in linhas if situacao(r) != "Revisada"]
    if qual == "esteatose":
        return [r for r in linhas if r.get("pdff") is not None and r["pdff"] >= F.PDFF_ESTEATOSE]
    if qual == "ferro":
        return [r for r in linhas if r.get("lic") is not None and r["lic"] >= 3.2]
    if qual == "rigidez":
        return [r for r in linhas if r.get("faixa") and r["faixa"] != "normal"]
    return list(linhas)


def resumo(linhas: list[dict]) -> dict:
    """Contagens para o topo da tela."""
    com = lambda k: [r for r in linhas if r.get(k) is not None]  # noqa: E731
    return {"exames": len(linhas), "revisados": sum(1 for r in linhas if situacao(r) == "Revisada"),
            "pdff": len(com("pdff")), "esteatose": len(filtrar(linhas, "esteatose")),
            "lic": len(com("lic")), "ferro": len(filtrar(linhas, "ferro")),
            "kpa": len(com("kpa")), "rigidez": len(filtrar(linhas, "rigidez"))}


CSV_CAB = ["study_uid", "data", "paciente", "id", "descricao", "aparelho", "pdff_pct", "grau_tang", "gordura",
           "ff_sinal_dupla_eco_pct", "r2_s-1", "r2_15T_s-1", "lic_mgFe_g", "ferro", "rigidez_kpa", "faixa",
           "rigidez", "estado_gordura", "estado_ferro", "estado_rigidez", "revisor", "revisado_em", "medido_em"]


def _n(v, casas=1) -> str:
    return "" if v is None else f"{v:.{casas}f}"


def linha_csv(r: dict) -> list:
    e = r.get("estados") or {}
    return [r.get("study_uid", ""), r.get("study_date", ""), r.get("patient_name", ""), r.get("patient_id", ""),
            r.get("description", ""), r.get("aparelho", ""), _n(r.get("pdff")),
            "" if r.get("grau") is None else r["grau"], r.get("gordura", ""), _n(r.get("ff_sinal")),
            _n(r.get("r2"), 0), _n(r.get("r2_15"), 0), _n(r.get("lic"), 2), r.get("ferro", ""), _n(r.get("kpa"), 2),
            r.get("faixa", ""), r.get("rigidez", ""), e.get("gordura", ""), e.get("ferro", ""), e.get("rigidez", ""),
            r.get("revisor", ""), r.get("revisado_em", ""), r.get("medido_em", "")]
