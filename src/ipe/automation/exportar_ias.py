"""Exportar em lote os resultados das IAs para Excel (0.100.123).

Pega os exames escolhidos no banco e junta, num .xlsx, o que as IAs **já gravaram** neles (não roda nada): os achados
de IA de cada ferramenta (com os números corrigidos pelo médico por cima, o estado da revisão) e as medidas da
mamografia (densidade e calcificações vasculares). Abas: *Leia-me*, *Exames* (um por linha, com quais IAs têm
resultado) e uma aba por IA. Sem biblioteca de fora (`planilha.gravar_xlsx`). Opcionalmente anonimiza (Caso 001…).
"""
from __future__ import annotations

import logging
import time

from ipe.core.i18n import tr

log = logging.getLogger(__name__)

MAMA = {"densidade": "Densidade mamária", "calc_vascular": "Calcificações vasculares"}


def _mama(repo, uid: str, tipo: str) -> dict:
    from ipe.automation import lote_ias as LIA
    try:
        if tipo == "densidade":
            from ipe.imaging import densidade_revisao as R
            return LIA.campos_densidade(R.guardada(repo, uid))
        from ipe.ai import calc_vascular as C
        return LIA.campos_calc(C.guardada(repo, uid))
    except Exception:  # noqa: BLE001
        log.debug("mama %s", tipo, exc_info=True)
        return {}


def coletar(repo, study_uids: list[str], titulos: dict | None = None, anonimizar: bool = False) -> dict:
    """{'exames': [...], 'ias': {titulo: {'campos': [...], 'linhas': [(exame, campos)]}}}."""
    from ipe.automation import lote_ias as LIA
    titulos = titulos or {}
    exames: list[dict] = []
    ias: dict[str, dict] = {}

    def somar(titulo: str, ex: dict, campos: dict) -> None:
        d = ias.setdefault(titulo, {"campos": [], "linhas": []})
        for c in campos:
            if c not in d["campos"]:
                d["campos"].append(c)
        d["linhas"].append((ex, campos))

    for n, uid in enumerate(study_uids, start=1):
        info = repo.study_info(uid) or {}
        ex = {"n": n, "caso": f"Caso {n:03d}", "uid": uid, "info": info, "ias": []}
        for tipo, titulo in MAMA.items():
            campos = _mama(repo, uid, tipo)
            if campos:
                somar(titulo, ex, campos)
                ex["ias"].append(titulo)
        try:
            achados = repo.achados(uid)
        except Exception:  # noqa: BLE001
            achados = []
        por_ferr: dict[str, list[dict]] = {}
        for a in achados:
            por_ferr.setdefault(a.get("ferramenta") or "", []).append(a)
        for ferr, lista in por_ferr.items():
            titulo = titulos.get(ferr) or ferr or "IA"
            campos = LIA.campos_achados(lista)
            if campos:
                somar(titulo, ex, campos)
                ex["ias"].append(titulo)
        exames.append(ex)
    return {"exames": exames, "ias": ias, "anonimizar": anonimizar}


def _ident(ex: dict, anonimizar: bool) -> tuple[list[str], list]:
    i = ex["info"]
    if anonimizar:
        return [tr("Caso")], [ex["caso"]]
    return ([tr("Paciente"), tr("ID do paciente"), tr("Study UID")],
            [i.get("patient_name", ""), i.get("patient_id", ""), ex["uid"]])


def folhas(dados: dict) -> list[tuple[str, list[list]]]:
    anon = bool(dados.get("anonimizar"))
    exames, ias = dados["exames"], dados["ias"]
    out: list[tuple[str, list[list]]] = []
    out.append((tr("Leia-me"), [
        [tr("Resultados de IA exportados do Ipê (não destinado a uso diagnóstico).")],
        [""],
        [tr("São os resultados que as IAs já tinham gravado nos exames; nada foi rodado agora.")],
        [tr("Os valores são sugestões de IA, não confirmados, exceto onde a coluna Revisão diz o contrário; "
            "números corrigidos pelo médico aparecem no lugar dos da IA.")],
        [tr("Exames escolhidos"), len(exames)],
        [tr("Com algum resultado de IA"), sum(1 for e in exames if e["ias"])],
        [tr("Identificação"), tr("anonimizada (Caso 001…)") if anon else tr("com nome e ID")],
        [tr("Gravado em"), time.strftime("%d/%m/%Y %H:%M")],
    ]))
    cab_id, _ = _ident(exames[0], anon) if exames else ([tr("Caso")], [])
    nomes_ia = list(ias)
    linhas = [cab_id + ([] if anon else [tr("Accession")]) + [tr("Data do exame"), tr("Modalidades"), tr("Descrição")]
              + [tr(n) for n in nomes_ia]]
    for ex in exames:
        i = ex["info"]
        _, idv = _ident(ex, anon)
        linhas.append(idv + ([] if anon else [i.get("accession", "")])
                      + [i.get("study_date", ""), i.get("modalities", ""), "" if anon else i.get("description", "")]
                      + [tr("sim") if n in ex["ias"] else "" for n in nomes_ia])
    out.append((tr("Exames"), linhas))
    usados = {tr("Leia-me"), tr("Exames")}
    for titulo, d in ias.items():
        cab_id, _ = _ident(exames[0], anon)
        cab = cab_id + [tr("Data do exame")] + [tr(c) for c in d["campos"]]
        rows = [cab]
        for ex, campos in d["linhas"]:
            _, idv = _ident(ex, anon)
            rows.append(idv + [ex["info"].get("study_date", "")] + [campos.get(c) for c in d["campos"]])
        nome = f"IA · {tr(titulo)}"[:31]
        base, k = nome, 2
        while nome in usados:
            nome = f"{base[:28]}·{k}"
            k += 1
        usados.add(nome)
        out.append((nome, rows))
    return out


def exportar(repo, study_uids: list[str], caminho, titulos: dict | None = None, anonimizar: bool = False) -> dict:
    """Grava o .xlsx. Devolve {'exames', 'com_resultado', 'ias': [títulos]}."""
    from ipe.automation.planilha import gravar_xlsx
    dados = coletar(repo, study_uids, titulos, anonimizar)
    gravar_xlsx(caminho, folhas(dados))
    return {"exames": len(dados["exames"]), "com_resultado": sum(1 for e in dados["exames"] if e["ias"]),
            "ias": list(dados["ias"])}
