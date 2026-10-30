"""Regras de dinâmico: quais séries o programa junta sozinho e quais ele separa sozinho.

Duas coisas opostas, do mesmo assunto, e por isso no mesmo lugar:

* **Juntar** — o aparelho grava **uma série por fase** (a RM de mama é assim). As séries que
  combinam com a regra viram uma dinâmica, com as fases na ordem das séries.
* **Separar** — o aparelho grava **todas as fases na mesma série** (acontece muito na TC). A série
  que combina com a regra é repartida em fases, **só na tela**: nada muda no banco nem nos
  arquivos, e dá para desfazer.

Uma regra é `{modalidade, contem, acao, nome, status}`. `contem` é um pedaço da descrição da série
(sem caixa, sem acento); modalidade vazia vale para todas. Regra **pendente** é a que o programa
anotou sozinho, quando o médico marcou uma dinâmica na mão: ela não age até ele confirmar — o
programa não decide por ele, só sugere o que viu.
"""

from __future__ import annotations

import unicodedata
from datetime import date

CHAVE = "dyn.regras"
ACOES = {"juntar": "Juntar (uma série por fase)", "separar": "Separar (as fases na mesma série)"}
# Três situações, e a do meio é a que ele pediu: **ignorar** mantém o que ele fez no exame onde
# fez — ao reabrir aquele exame o arranjo volta —, e não encosta em nenhum outro.
STATUS = {"confirmada": "Confirmada (vale em todo exame)",
          "ignorada": "Ignorar (só no exame onde foi criada)",
          "pendente": "Pendente de confirmar"}


def normal(t: str) -> str:
    """Sem acento, sem caixa, sem espaço sobrando — para comparar descrição de série."""
    t = unicodedata.normalize("NFKD", str(t or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).lower().strip()


def carregar(settings) -> list[dict]:
    if settings is None:
        return []
    regras = settings.get(CHAVE, []) or []
    return [r for r in regras if isinstance(r, dict) and r.get("contem")]


def salvar(settings, regras: list[dict]) -> None:
    if settings is not None:
        settings.set(CHAVE, list(regras))


def casa(regra: dict, modalidade: str, descricao: str) -> bool:
    mod = normal(regra.get("modalidade", ""))
    if mod and mod != normal(modalidade):
        return False
    return normal(regra.get("contem", "")) in normal(descricao)


def valem(regras: list[dict], acao: str, study_uid: str = "") -> list[dict]:
    """As regras que agem neste exame: as confirmadas, mais as ignoradas **deste** exame.

    Pendente nunca age. Ignorada age só no exame em que nasceu — é o jeito de guardar o arranjo
    que ele fez na mão sem que ele volte a acontecer em exame nenhum.
    """
    out = []
    for r in regras:
        if r.get("acao") != acao:
            continue
        st = r.get("status", "confirmada")
        if st == "confirmada" or (st == "ignorada" and study_uid and r.get("estudo") == study_uid):
            out.append(r)
    return out


def trecho_comum(textos: list[str]) -> str:
    """Maior pedaço de texto que aparece em todas as descrições (é o que vira a regra).

    Duas fases de uma dinâmica quase sempre se chamam quase igual ("…Ph1", "…Ph2"): o pedaço
    comum é o nome da sequência, que é justamente o que identifica a dinâmica.
    """
    textos = [normal(t) for t in textos if normal(t)]
    if not textos:
        return ""
    base = min(textos, key=len)
    melhor = ""
    for i in range(len(base)):
        for j in range(len(base), i + len(melhor), -1):
            pedaco = base[i:j]
            if all(pedaco in t for t in textos):
                melhor = pedaco
                break
    return melhor.strip(" -_,.;/()")


def sugerir(modalidade: str, descricoes: list[str], acao: str, nome: str = "",
            estudo: str = "", exame: str = "") -> dict | None:
    """A regra que o programa anota quando o médico faz a coisa na mão.

    `estudo` e `exame` guardam **onde** ela nasceu: é o que permite a situação "ignorar", em que
    a regra vale só ali.
    """
    contem = trecho_comum(descricoes)
    if len(contem) < 3:
        return None
    return {"modalidade": (modalidade or "").upper(), "contem": contem, "acao": acao,
            "nome": nome or "Dinâmica", "status": "pendente", "criada": date.today().isoformat(),
            "estudo": estudo, "exame": exame}


def acrescentar_pendente(settings, regra: dict | None) -> dict | None:
    """Guarda a regra sugerida, se ainda não houver uma igual (confirmada ou pendente)."""
    if not regra:
        return None
    regras = carregar(settings)
    for r in regras:
        if (normal(r.get("contem")) == normal(regra["contem"])
                and normal(r.get("modalidade")) == normal(regra["modalidade"])
                and r.get("acao") == regra["acao"]):
            return None
    regras.append(regra)
    salvar(settings, regras)
    return regra


def para_juntar(regras: list[dict], series: list, study_uid: str = "") -> list[tuple[str, list[str]]]:
    """(nome, uids) de cada conjunto que as regras de **juntar** formam nas séries dadas."""
    out = []
    for r in valem(regras, "juntar", study_uid):
        uids = [s.series_uid for s in series if casa(r, s.modality, s.description)]
        if len(uids) >= 2:
            out.append((r.get("nome") or "Dinâmica", uids))
    return out


def para_separar(regras: list[dict], series: list, study_uid: str = "") -> list[str]:
    """uids das séries que as regras de **separar** mandam repartir em fases."""
    out = []
    for r in valem(regras, "separar", study_uid):
        for s in series:
            if casa(r, s.modality, s.description) and s.series_uid not in out:
                out.append(s.series_uid)
    return out
