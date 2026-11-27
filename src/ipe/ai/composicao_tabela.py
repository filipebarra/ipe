"""Composição corporal e densidade óssea: medidas e confirmações (0.100.132) — a tabela, como a do fígado na RM.

Uma linha por exame com o resultado da IA de composição corporal (`composicao`): músculo, gorduras, fígado e baço e,
sobretudo, o **HU do osso trabecular de L1 e de L1–L4**, com a situação da revisão. Duas colunas são digitadas pelo
médico: a **DMO** (T-score) da **coluna** e do **fêmur**, para validar o osso da TC contra a densitometria e achar o
corte do próprio serviço (`analise_osso`: AUC e o melhor corte pela curva ROC, com sensibilidade e especificidade).
Sem Qt.
"""
from __future__ import annotations

from ipe.ai import achados as AC
from ipe.ai import composicao as C
from ipe.ai import densidade_osso as DO

LIMIAR_T = -2.5           # DMO: T-score ≤ −2,5 = osteoporose (OMS); abaixo de −1,0 e acima disso = osteopenia
SITUACOES = (("todas", "Todas"), ("revisadas", "Revisadas (confirmadas ou corrigidas)"),
             ("pendentes", "Não revisadas"), ("com_osso", "Com densidade óssea medida"),
             ("com_dmo", "Com DMO digitada"), ("sem_dmo", "Com osso e sem DMO"))


def _v(a: dict | None, k: str):
    if not a:
        return None
    v = (AC.numeros_validos(a).get(k) or {}).get("v")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _t(a: dict | None, k: str) -> str:
    if not a:
        return ""
    v = (AC.numeros_validos(a).get(k) or {}).get("v")
    return "" if v is None else str(v)


def _t_score(x):
    try:
        if x is None or str(x).strip() == "":
            return None
        return float(str(x).replace(",", "."))
    except ValueError:
        return None


def linha(base: dict, achados: list[dict], dmo: dict | None = None) -> dict:
    """Junta os achados de um exame (e a DMO digitada) numa linha: `base` traz o paciente e o exame."""
    por_tipo: dict[str, dict] = {}
    for a in achados:
        if a.get("estado") == "descartado" and a.get("tipo") in por_tipo:
            continue
        por_tipo[a.get("tipo", "")] = a
    l3, fig, osso = (por_tipo.get(t) for t in (C.TIPO_L3, C.TIPO_FIGADO, DO.TIPO_OSSO))
    est = {nome: (a.get("estado") or "sugerido") for nome, a in (("l3", l3), ("figado", fig), ("osso", osso)) if a}
    revisados = [a for a in (l3, fig, osso) if a and a.get("estado") in ("confirmado", "corrigido")]
    ultimo = max(revisados, key=lambda a: str(a.get("revisado_em") or ""), default=None)
    dmo = dmo or {}
    return {**base,
            "sma": _v(l3, "sma_cm2"), "smi": _v(l3, "smi"), "musculo_hu": _v(l3, "musculo_hu"),
            "vat": _v(l3, "vat_cm2"), "sat": _v(l3, "sat_cm2"), "imat": _v(l3, "imat_cm2"),
            "figado_hu": _v(fig, "figado_hu"), "baco_hu": _v(fig, "baco_hu"), "f_menos_b": _v(fig, "f_menos_b"),
            "l1": _v(osso, "l1_hu"), "l2": _v(osso, "l2_hu"), "l3_osso": _v(osso, "l3_hu"), "l4": _v(osso, "l4_hu"),
            "l1l4": _v(osso, "l1l4_hu"), "niveis": _v(osso, "niveis_n"),
            "osso": DO.resultado_do_achado(osso) if osso else "",
            "dmo_coluna": _t_score(dmo.get("coluna")), "dmo_femur": _t_score(dmo.get("femur")),
            "dmo_data": str(dmo.get("data") or ""),
            "estados": est, "revisor": (ultimo or {}).get("revisor", "") if ultimo else "",
            "revisado_em": str((ultimo or {}).get("revisado_em") or "")[:16] if ultimo else "",
            "medido_em": str(min((str(a.get("criado_em") or "") for a in achados), default=""))[:16]}


def dmo_minima(r: dict):
    """O pior T-score da DMO digitada (coluna ou fêmur), ou None."""
    ts = [t for t in (r.get("dmo_coluna"), r.get("dmo_femur")) if t is not None]
    return min(ts) if ts else None


def classe_dmo(t) -> str:
    if t is None:
        return ""
    return "osteoporose" if t <= LIMIAR_T else ("osteopenia" if t < -1.0 else "normal")


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
    if qual == "com_osso":
        return [r for r in linhas if r.get("l1") is not None or r.get("l1l4") is not None]
    if qual == "com_dmo":
        return [r for r in linhas if dmo_minima(r) is not None]
    if qual == "sem_dmo":
        return [r for r in linhas if (r.get("l1") is not None or r.get("l1l4") is not None) and dmo_minima(r) is None]
    return list(linhas)


def resumo(linhas: list[dict]) -> dict:
    return {"exames": len(linhas), "revisados": sum(1 for r in linhas if situacao(r) == "Revisada"),
            "osso": len(filtrar(linhas, "com_osso")), "com_dmo": len(filtrar(linhas, "com_dmo")),
            "validaveis": sum(1 for r in linhas if dmo_minima(r) is not None and r.get("l1l4") is not None)}


# ---------------------------------------------------------------- validação contra a DMO
def auc(positivos: list[float], negativos: list[float]) -> float | None:
    """AUC (Mann-Whitney) de um HU **menor = mais doente**: P(HU do doente < HU do sem doença); empate vale 1/2."""
    if not positivos or not negativos:
        return None
    ganho = 0.0
    for p in positivos:
        for n in negativos:
            ganho += 1.0 if p < n else (0.5 if p == n else 0.0)
    return ganho / (len(positivos) * len(negativos))


def _sens_esp(positivos, negativos, corte):
    """Doente = HU ≤ corte."""
    vp = sum(1 for x in positivos if x <= corte)
    vn = sum(1 for x in negativos if x > corte)
    return (vp / len(positivos) if positivos else None), (vn / len(negativos) if negativos else None)


def analise_osso(linhas: list[dict], campo: str = "l1l4", alvo: str = "osteoporose", limites: dict | None = None) -> dict:
    """Compara o HU (`campo`: "l1" ou "l1l4") com a DMO digitada (a pior das duas).

    `alvo`: "osteoporose" (T ≤ −2,5) ou "baixa" (T < −1,0, osteopenia ou pior). Devolve n, positivos, AUC, o melhor
    corte (Youden: sensibilidade + especificidade − 1; doente = HU ≤ corte) e a sensibilidade/especificidade nos
    cortes que o serviço usa hoje (`limites`: osteo, baixa, normal).
    """
    pos, neg = [], []
    for r in linhas:
        t, hu = dmo_minima(r), r.get(campo)
        if t is None or hu is None:
            continue
        doente = t <= LIMIAR_T if alvo == "osteoporose" else t < -1.0
        (pos if doente else neg).append(float(hu))
    out = {"campo": campo, "alvo": alvo, "n": len(pos) + len(neg), "positivos": len(pos), "negativos": len(neg),
           "auc": auc(pos, neg), "corte": None, "sens": None, "esp": None, "nos_cortes": {}}
    if not pos or not neg:
        return out
    melhor = None
    for corte in sorted(set(pos + neg)):
        s, e = _sens_esp(pos, neg, corte)
        j = s + e - 1.0
        if melhor is None or j > melhor[0] + 1e-12:
            melhor = (j, corte, s, e)
    out["corte"], out["sens"], out["esp"] = melhor[1], melhor[2], melhor[3]
    for nome, corte in (limites or {}).items():
        if corte:
            s, e = _sens_esp(pos, neg, float(corte))
            out["nos_cortes"][nome] = {"corte": float(corte), "sens": s, "esp": e}
    return out


def texto_da_analise(a: dict) -> str:
    nome = "L1" if a["campo"] == "l1" else "L1–L4"
    alvo = "osteoporose (T ≤ −2,5)" if a["alvo"] == "osteoporose" else "baixa densidade (T < −1,0)"
    if a["n"] == 0:
        return f"{nome}: sem exames com HU e DMO ao mesmo tempo."
    if a["auc"] is None:
        return (f"{nome} × {alvo}: {a['n']} exame(s), {a['positivos']} com a doença e {a['negativos']} sem — precisa "
                "de pelo menos um de cada.")
    txt = (f"{nome} × {alvo}: {a['n']} exame(s) ({a['positivos']} com, {a['negativos']} sem); AUC {a['auc']:.2f}; "
           f"melhor corte ≤ {a['corte']:.0f} HU (sensibilidade {100 * a['sens']:.0f}%, especificidade "
           f"{100 * a['esp']:.0f}%).")
    for nome_c, d in a["nos_cortes"].items():
        txt += f" Em {d['corte']:.0f} HU: {100 * d['sens']:.0f}% / {100 * d['esp']:.0f}%."
    return txt


CSV_CAB = ["study_uid", "data", "paciente", "id", "descricao", "aparelho", "sma_cm2", "smi_cm2_m2", "musculo_hu",
           "vat_cm2", "sat_cm2", "imat_cm2", "figado_hu", "baco_hu", "figado_menos_baco", "l1_hu", "l2_hu", "l3_hu",
           "l4_hu", "l1_l4_hu", "niveis", "resultado_osso", "dmo_coluna_t", "dmo_femur_t", "dmo_classe", "dmo_data",
           "estado_l3", "estado_figado", "estado_osso", "revisor", "revisado_em", "medido_em"]


def _n(v, casas=1) -> str:
    return "" if v is None else f"{v:.{casas}f}"


def linha_csv(r: dict) -> list:
    e = r.get("estados") or {}
    return [r.get("study_uid", ""), r.get("study_date", ""), r.get("patient_name", ""), r.get("patient_id", ""),
            r.get("description", ""), r.get("aparelho", ""), _n(r.get("sma")), _n(r.get("smi")),
            _n(r.get("musculo_hu")), _n(r.get("vat")), _n(r.get("sat")), _n(r.get("imat")), _n(r.get("figado_hu")),
            _n(r.get("baco_hu")), _n(r.get("f_menos_b")), _n(r.get("l1")), _n(r.get("l2")), _n(r.get("l3_osso")),
            _n(r.get("l4")), _n(r.get("l1l4")), _n(r.get("niveis"), 0), r.get("osso", ""), _n(r.get("dmo_coluna")),
            _n(r.get("dmo_femur")), classe_dmo(dmo_minima(r)), r.get("dmo_data", ""), e.get("l3", ""),
            e.get("figado", ""), e.get("osso", ""), r.get("revisor", ""), r.get("revisado_em", ""),
            r.get("medido_em", "")]
