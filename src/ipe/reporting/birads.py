"""Formulário BI-RADS® (ACR, 5ª edição) para mamografia, ultrassonografia e RM, e o texto do laudo."""

from __future__ import annotations

CATEGORIES = {
    "0": "Incompleto — necessita avaliação adicional",
    "1": "Negativo",
    "2": "Achado(s) benigno(s)",
    "3": "Achado provavelmente benigno",
    "4A": "Baixa suspeita de malignidade",
    "4B": "Moderada suspeita de malignidade",
    "4C": "Alta suspeita de malignidade",
    "5": "Altamente sugestivo de malignidade",
    "6": "Malignidade comprovada por biópsia",
}
# hierarquia para a categoria final (do menos para o mais preocupante)
ORDER = ["1", "2", "3", "6", "0", "4A", "4B", "4C", "5"]

RECOMMENDATION = {
    "0": "Recomenda-se avaliação adicional por imagem e/ou comparação com exames anteriores.",
    "1": "Recomenda-se rastreamento de rotina.",
    "2": "Recomenda-se rastreamento de rotina.",
    "3": "Recomenda-se controle em curto intervalo (6 meses).",
    "4A": "Recomenda-se diagnóstico histopatológico.",
    "4B": "Recomenda-se diagnóstico histopatológico.",
    "4C": "Recomenda-se diagnóstico histopatológico.",
    "5": "Recomenda-se diagnóstico histopatológico.",
    "6": "Recomenda-se excisão cirúrgica quando clinicamente apropriada.",
}

COMPOSITION = {
    "mg": {"a": "As mamas são quase inteiramente adiposas (ACR a).",
           "b": "Há áreas esparsas de densidade fibroglandular (ACR b).",
           "c": "As mamas são heterogeneamente densas, o que pode ocultar pequenos nódulos (ACR c).",
           "d": "As mamas são extremamente densas, o que diminui a sensibilidade da mamografia (ACR d)."},
    "us": {"a": "Ecotextura de fundo homogênea — adiposa.",
           "b": "Ecotextura de fundo homogênea — fibroglandular.",
           "c": "Ecotextura de fundo heterogênea."},
    "mri": {"a": "Tecido fibroglandular: quase inteiramente adiposo (a).",
            "b": "Tecido fibroglandular: áreas esparsas (b).",
            "c": "Tecido fibroglandular: heterogêneo (c).",
            "d": "Tecido fibroglandular: extremo (d)."},
}
BPE = {"minimo": "mínimo", "discreto": "discreto", "moderado": "moderado", "acentuado": "acentuado"}

FINDING_TYPES = {
    "mg": ["Nódulo", "Calcificações", "Assimetria", "Assimetria focal", "Assimetria global",
           "Assimetria em desenvolvimento", "Distorção arquitetural", "Linfonodo intramamário",
           "Lesão de pele", "Ducto dilatado solitário", "Achado associado"],
    "us": ["Nódulo", "Cisto simples", "Cisto complicado", "Cisto complexo (sólido-cístico)", "Calcificações",
           "Distorção arquitetural", "Linfonodo intramamário", "Ectasia ductal", "Coleção"],
    "mri": ["Foco", "Nódulo", "Realce não nodular", "Linfonodo intramamário", "Cisto", "Lesão de pele"],
}
DESCRIPTORS = {
    "Nódulo": ["forma oval", "forma redonda", "forma irregular", "margem circunscrita", "margem obscurecida",
               "margem microlobulada", "margem indistinta", "margem espiculada", "alta densidade",
               "isodenso", "paralelo à pele", "não paralelo", "hipoecoico", "sombra acústica posterior",
               "realce homogêneo", "realce heterogêneo", "realce anelar", "septações internas escuras"],
    "Calcificações": ["tipicamente benignas", "amorfas", "grosseiras heterogêneas", "finas pleomórficas",
                      "finas lineares ou lineares ramificadas", "difusas", "regionais", "agrupadas",
                      "lineares", "segmentares"],
    "Realce não nodular": ["focal", "linear", "segmentar", "regional", "múltiplas regiões", "difuso",
                           "homogêneo", "heterogêneo", "agrupado (clumped)", "anelar agrupado (clustered ring)"],
}
SIDES = {"D": "Mama direita", "E": "Mama esquerda", "B": "Ambas as mamas"}


def worst(categories: list[str]) -> str:
    cats = [c for c in categories if c in ORDER]
    return max(cats, key=ORDER.index) if cats else ""


def final_category(fields: dict) -> str:
    cats = [fields.get("cat_right", ""), fields.get("cat_left", "")]
    cats += [f.get("category", "") for f in fields.get("findings", []) or []]
    return worst(cats) or fields.get("category", "")


def composition_text(fields: dict) -> str:
    kind = fields.get("kind", "mg")
    out = []
    comp = COMPOSITION.get(kind, {}).get(fields.get("composition" if kind != "mri" else "fgt", ""), "")
    if comp:
        out.append(comp)
    elif kind in COMPOSITION:            # ainda não escolhida: deixa o lugar marcado no texto
        out.append({"mg": "Composição mamária: ___", "us": "Ecotextura de fundo: ___",
                    "mri": "Tecido fibroglandular: ___"}[kind])
    if kind == "mri" and fields.get("bpe"):
        sym = {"simetrico": "simétrico", "assimetrico": "assimétrico"}.get(fields.get("bpe_sym", ""), "")
        out.append(f"Realce de fundo do parênquima: {BPE.get(fields['bpe'], fields['bpe'])}"
                   + (f", {sym}" if sym else "") + ".")
    return "\n".join(out)


def bpe_text(fields: dict) -> str:
    b = BPE.get(fields.get("bpe", ""), "")
    sym = {"simetrico": "simétrico", "assimetrico": "assimétrico"}.get(fields.get("bpe_sym", ""), "")
    return (b + (f", {sym}" if sym else "")) or "___"


def finding_text(f: dict) -> str:
    side = SIDES.get(f.get("side", ""), "")
    parts = [f.get("type", "Achado")]
    if f.get("desc"):
        parts.append(f["desc"])
    txt = ", ".join(p for p in parts if p)
    if f.get("size"):
        size = str(f["size"]).strip()
        txt += f", medindo {size}" + ("" if any(u in size for u in ("mm", "cm")) else " mm")
    if f.get("location"):
        txt += f", localizado(a) {f['location']}"
    if f.get("distance"):
        txt += f", a {f['distance']} do mamilo"
    if f.get("change"):
        txt += f" ({f['change']})"
    txt = (f"{side}: " if side else "") + txt[0].lower() + txt[1:] if side and txt else txt
    if f.get("category"):
        txt += f" — BI-RADS® {f['category']}"
    return txt.rstrip(".") + "."


def findings_text(fields: dict) -> str:
    fs = fields.get("findings", []) or []
    if not fs:
        return fields.get("no_findings_text") or "Não há nódulos, calcificações suspeitas ou distorções arquiteturais."
    return "\n".join(finding_text(f) for f in fs)


def category_text(fields: dict) -> str:
    cat = final_category(fields)
    if not cat:
        return "BI-RADS®: ___"
    lines = []
    r, l = fields.get("cat_right", ""), fields.get("cat_left", "")
    if r and l and r != l:
        lines.append(f"Mama direita: BI-RADS® {r} — {CATEGORIES.get(r, '')}.")
        lines.append(f"Mama esquerda: BI-RADS® {l} — {CATEGORIES.get(l, '')}.")
        lines.append(f"Categoria final: BI-RADS® {cat}.")
    else:
        lines.append(f"BI-RADS® {cat}: {CATEGORIES.get(cat, '')}.")
    lines.append(recommendation(fields))
    return "\n".join(x for x in lines if x)


def recommendation(fields: dict) -> str:
    if fields.get("recommendation"):
        return fields["recommendation"]
    cat = final_category(fields)
    rec = RECOMMENDATION.get(cat, "")
    if cat == "0" and fields.get("kind") == "mri":
        rec = "Recomenda-se avaliação adicional por imagem."
    if cat == "4A" and fields.get("kind") == "mri":
        rec = "Recomenda-se diagnóstico histopatológico."
    return rec
