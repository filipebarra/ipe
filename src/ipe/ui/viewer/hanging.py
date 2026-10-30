"""Protocolos de exibição (hanging protocols): layout e posição de cada série ao abrir o exame,
com o exame anterior ao lado ou no monitor de comparação.

Um protocolo (em settings "hanging_protocols"):
  {"name", "modality", "description" (contém; vazio = qualquer), "layout": [linhas, colunas],
   "cells": ["R CC", "L CC", ...]  (padrão de cada quadro; "|" separa alternativas),
   "prior": bool (trazer o anterior da mesma modalidade), "enabled": bool}
O padrão é comparado com a descrição da série + lateralidade + incidência (ViewPosition).
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

#: Como o exame se distribui quando há mais de um monitor "viewer". A chave é o **número de
#: monitores**; o valor, um plano por monitor (layout + padrão de cada quadro). Com 1 monitor vale
#: o `layout`/`cells` de sempre. Mamografia é o caso que pede isso: duas telas de diagnóstico lado
#: a lado é o arranjo clássico, com as CC numa e as MLO na outra, R à esquerda e L à direita.
# A mamografia (e a tomossíntese, que é MG) **não** usa o protocolo de exibição: ela tem aba
# própria, com arranjo por número de telas e etapas por monitor. Dois lugares decidindo o mesmo
# arranjo foi o que fez a mamografia abrir "certa" e sem o modo mamografia.
SEM_PROTOCOLO_GENERICO = {"MG"}

# ------------------------------------------------------------------ etapas (0.88)
# Protocolo com etapas, como o da mamografia, para os outros exames. Pedido dele: "criar protocolos
# de visualização para outros exames (TC, RM…), assim como o da mamografia. Steps mudando layout,
# cor, séries preferenciais, planos, podendo ter MIP, MPR."
#
#   protocolo: {"name", "modality", "description", "enabled", "prior", "steps": [etapa, …]}
#   etapa:     {"name", "rows", "cols", "cells": [quadro, …]}       (quadros linha a linha)
#   quadro:    {"series": "T1 POS|T1 GD|T1"  (alternativas em ordem de preferência; vazio = nada),
#               "prior": bool                 (a série vem do exame anterior),
#               "plane": "" | "Axial" | "Coronal" | "Sagital"   ("" = como foi adquirida),
#               "recon": "" | "mip" | "minip" | "avg",  "slab": mm,
#               "window": "" | chave do preset ("1") | "1500/-600",
#               "cmap": "" | tabela de cores,
#               "pos": "auto" | "inicio" | "meio" | "ponto",
#               "sync": 0 | n  (quadros com o mesmo n andam juntos),
#               "monitor": 0 | k  (com várias telas: 0 = o programa reparte),
#               "fase": "" | "pre" | "1".."9" | "ult"   (0.90: a fase da dinâmica — "1" = 1ª pós),
#               "metade": "" | "direita" | "esquerda"  (0.90: MIP sagital só daquela metade do
#                         paciente — a "meia mama"; a espessura é a da metade),
#               "vista": "" | "anterior" | "posterior" | "direita" | "esquerda" | "superior" |
#                         "inferior"  (0.91: de que lado se olha — as Vistas da barra do 3D. No 3D é a
#                         câmera; num corte daquele plano, o espelho que dá a mesma imagem. A 0.90
#                         tinha "anterior": "esquerda"/"direita", lido como vista esquerda/direita)}
#
# Protocolo sem "steps" (os de antes da 0.88) continua sendo aplicado pelo caminho antigo, que sabe
# pôr o anterior à direita e repartir por monitor; o editor novo converte ao salvar (`etapas`).

PLANOS = ("", "Axial", "Coronal", "Sagital")
RECONS = ("", "mip", "minip", "avg", "mpr", "mip3d", "vr")
#: reconstruções que põem o 3D no quadro — o mesmo do botão 3D, com a barra inteira (0.91)
RECONS_3D = {"mip3d": "mip", "vr": "vr"}
RECON_CURTO = {"": "", "mip": "MIP", "minip": "MinIP", "avg": "média", "mpr": "MPR", "mip3d": "MIP 3D",
               "vr": "VR"}
POSICOES = ("auto", "inicio", "meio", "ponto")
FASES = ("", "pre", "1", "2", "3", "4", "5", "6", "7", "8", "9", "ult")
METADES = ("", "direita", "esquerda")
VISTAS = ("", "anterior", "posterior", "direita", "esquerda", "superior", "inferior")


def fase_indice(fase: str, quantas: int) -> int | None:
    """Índice da fase no grupo dinâmico (0 = pré-contraste), ou None se não houver tantas fases.
    "1" é a 1ª pós-contraste, que é o índice 1."""
    if not fase or quantas <= 0:
        return None
    if fase == "pre":
        return 0
    if fase == "ult":
        return quantas - 1
    k = int(fase)
    return k if k < quantas else None


def fase_texto(fase: str) -> str:
    return {"": "", "pre": "pré-contraste", "ult": "última fase"}.get(fase, f"pós-contraste {fase}")

QUADRO_PADRAO = {"series": "", "prior": False, "plane": "", "recon": "", "slab": 0.0, "window": "",
                 "cmap": "", "pos": "auto", "sync": 0, "monitor": 0, "fase": "", "metade": "",
                 "vista": ""}


def quadro(d) -> dict:
    """Um quadro completo (aceita o texto solto dos protocolos antigos: "T2|STIR")."""
    if isinstance(d, str):
        d = {"series": d}
    q = dict(QUADRO_PADRAO)
    q.update({k: v for k, v in (d or {}).items() if k in QUADRO_PADRAO})
    antigo = d.get("anterior") if isinstance(d, dict) else None
    if antigo in ("esquerda", "direita") and not q["vista"]:
        # 0.90 → 0.91: no sagital, olhar da esquerda põe a frente à esquerda da tela
        q["vista"] = antigo
    q["plane"] = q["plane"] if q["plane"] in PLANOS else ""
    q["recon"] = q["recon"] if q["recon"] in RECONS else ""
    q["pos"] = q["pos"] if q["pos"] in POSICOES else "auto"
    try:
        q["slab"] = max(0.0, float(q["slab"] or 0))
        q["sync"] = max(0, int(q["sync"] or 0))
        q["monitor"] = max(0, int(q["monitor"] or 0))
    except (TypeError, ValueError):
        q["slab"], q["sync"], q["monitor"] = 0.0, 0, 0
    q["prior"] = bool(q["prior"])
    q["fase"] = str(q["fase"] or "")
    q["fase"] = q["fase"] if q["fase"] in FASES else ""
    q["metade"] = q["metade"] if q["metade"] in METADES else ""
    q["vista"] = q["vista"] if q["vista"] in VISTAS else ""
    if q["metade"]:                       # meia mama: MIP sagital de espessura, ou o 3D da metade
        q["recon"] = q["recon"] if q["recon"] in ("mip", "minip", "avg", "mip3d", "vr") else "mip"
        if q["recon"] not in RECONS_3D:
            q["plane"] = "Sagital"
    return q


def etapa(d) -> dict:
    rows = max(1, min(6, int((d or {}).get("rows", 1) or 1)))
    cols = max(1, min(6, int((d or {}).get("cols", 1) or 1)))
    cells = [quadro(c) for c in ((d or {}).get("cells") or [])][: rows * cols]
    cells += [quadro("") for _ in range(rows * cols - len(cells))]
    st = {"name": str((d or {}).get("name", "") or "Etapa"), "rows": rows, "cols": cols, "cells": cells}
    din = (d or {}).get("dinamica") if isinstance(d, dict) else None
    if isinstance(din, dict) and din:
        # 0.94: a etapa abre a avaliação dinâmica (mapas e curvas), como o botão Dinâmica
        try:
            lay = max(0, int(din.get("layout", 0) or 0))
        except (TypeError, ValueError):
            lay = 0
        st["dinamica"] = {"layout": lay, "series": str(din.get("series", "") or DINAMICA)}
    return st


def tem_etapas(proto: dict | None) -> bool:
    return bool(proto) and isinstance(proto.get("steps"), list) and bool(proto.get("steps"))


def etapas(proto: dict) -> list[dict]:
    """As etapas do protocolo. Protocolo antigo vira uma etapa só — com o anterior ao lado, como
    ele fazia, quando estava marcado (sem monitor de comparação)."""
    if tem_etapas(proto):
        return [etapa(e) for e in proto["steps"]]
    rows, cols = (int(x) for x in (proto.get("layout") or [1, 1])[:2])
    cells = [quadro(c) for c in (proto.get("cells") or [])]
    cells += [quadro("") for _ in range(rows * cols - len(cells))]
    if proto.get("prior"):
        lados = []
        for r in range(rows):
            linha = cells[r * cols:(r + 1) * cols]
            lados += linha + [dict(c, prior=True) if c.get("series") else c for c in linha]
        cells, cols = lados, cols * 2
    return [etapa({"name": proto.get("name", "") or "Etapa 1", "rows": rows, "cols": cols, "cells": cells})]


def convertido(proto: dict) -> dict:
    """O protocolo no formato com etapas (o editor grava assim). Guarda o que não conhece."""
    novo = {k: v for k, v in proto.items() if k not in ("layout", "cells")}
    novo["steps"] = etapas(proto)
    if not tem_etapas(proto) and proto.get("prior"):
        novo["prior"] = False                  # o anterior agora está nos quadros da etapa
    return novo


def descrever_quadro(q: dict) -> str:
    """Duas ou três palavras para o desenho da etapa: "PULMAO · Coronal MIP 10 mm · pulmão"."""
    q = quadro(q)
    partes = [q["series"].split("|")[0] or "(vazio)"]
    if q["prior"]:
        partes[0] += " (anterior)"
    if q["fase"]:
        partes.append(fase_texto(q["fase"]))
    plano = q["plane"] or ""
    if q["metade"]:
        plano = f"mama {q['metade']}, {RECON_CURTO[q['recon']]}"
    elif q["recon"] in RECONS_3D or q["recon"] == "mpr":
        plano = f"{plano} {RECON_CURTO[q['recon']]}".strip()
    elif q["recon"]:
        plano = f"{plano} {q['recon'].upper().replace('AVG', 'média')} {q['slab']:g} mm".strip()
    if plano:
        partes.append(plano)
    if q["vista"]:
        partes.append(f"vista {q['vista']}")
    if q["window"]:
        partes.append(f"janela {q['window']}")
    if q["cmap"]:
        partes.append(q["cmap"])
    return " · ".join(partes)


def _grade(n: int) -> tuple[int, int]:
    return {1: (1, 1), 2: (1, 2), 3: (1, 3), 4: (2, 2)}.get(n, (2, 3) if n <= 6 else (3, 3) if n <= 9 else (3, 4))


def parte_da_tela(step: dict, quantos: int, indice: int) -> dict:
    """O pedaço da etapa que cabe ao monitor `indice` de `quantos`: {"rows","cols","cells"}.

    Quadro com "monitor" escolhido vai para aquela tela; sem escolha em nenhum, a etapa se reparte
    como na mamografia (pelas linhas, senão pelas colunas, senão em ordem)."""
    st = etapa(step)
    if quantos <= 1:
        return st
    escolhidos = [q for q in st["cells"] if q["monitor"]]
    if escolhidos:
        meus = [q for q in st["cells"] if (q["monitor"] or 1) == indice + 1 and q["series"]]
        if not meus:
            meus = [quadro("")]
        r, c = _grade(len(meus))
        return {"name": st["name"], "rows": r, "cols": c, "cells": meus + [quadro("")] * (r * c - len(meus))}
    from ipe.imaging.mammo import repartir_etapa
    ids = [str(i) if q["series"] else "" for i, q in enumerate(st["cells"])]
    pedaco = repartir_etapa({"rows": st["rows"], "cols": st["cols"], "cells": ids}, quantos)[indice]
    cells = [st["cells"][int(i)] if i else quadro("") for i in pedaco["cells"]]
    return {"name": st["name"], "rows": pedaco["rows"], "cols": pedaco["cols"], "cells": cells}


def escolher_serie(padrao: str, candidatos: list[tuple[str, set[str], str]], evitar: set[str] = frozenset()):
    """A série do quadro: as alternativas valem **em ordem de preferência** ("T1 POS|T1 GD|T1" quer
    a pós antes da simples). Dentro de cada alternativa, prefere uma série ainda não usada."""
    for alt in [a for a in (padrao or "").split("|") if a.strip()]:
        achadas = [uid for uid, words, text in candidatos if pattern_match(alt, words, text)]
        if achadas:
            livres = [u for u in achadas if u not in evitar]
            return (livres or achadas)[0]
    return None


DINAMICA = "DIN|DYN|VIBRANT|THRIVE|TWIST|▦"
# 0.90 — pedido dele: "uma etapa com layout 2×2 com 4 MIPs: dois da 1ª fase pós-contraste e dois da
# 3ª. Os MIPs só de meia mama, direita com o mamilo virado para a esquerda e esquerda virado para a
# direita." Em cima a 1ª pós, embaixo a 3ª; à esquerda a mama direita, à direita a esquerda.
#: etapa de fábrica (0.94): a avaliação dinâmica — mapa cinético e curva, com os parâmetros que ele
#: usou por último no botão Dinâmica
ETAPA_DINAMICA = {"name": "Avaliação dinâmica", "rows": 1, "cols": 1, "cells": [""],
                  "dinamica": {"layout": 0, "series": DINAMICA}}

ETAPA_MIP_MEIA_MAMA = {"name": "MIP das fases (meia mama)", "rows": 2, "cols": 2, "cells": [
    {"series": DINAMICA, "fase": "1", "metade": "direita", "recon": "mip3d", "vista": "esquerda", "sync": 0},
    {"series": DINAMICA, "fase": "1", "metade": "esquerda", "recon": "mip3d", "vista": "direita"},
    {"series": DINAMICA, "fase": "3", "metade": "direita", "recon": "mip3d", "vista": "esquerda"},
    {"series": DINAMICA, "fase": "3", "metade": "esquerda", "recon": "mip3d", "vista": "direita"}]}

DEFAULT_PROTOCOLS = [
    {"name": "RM de mama", "modality": "MR", "description": "MAMA|BREAST", "enabled": True, "prior": False,
     "steps": [
         {"name": "Sem contraste", "rows": 2, "cols": 2, "cells": [
             {"series": "T2|STIR", "sync": 1}, {"series": "T1", "sync": 1},
             {"series": "DWI|DIFUS", "sync": 1}, {"series": "ADC", "sync": 1}]},
         {"name": "Dinâmica", "rows": 1, "cols": 2, "cells": [
             {"series": "DIN|DYN|VIBRANT|THRIVE|▦", "sync": 1}, {"series": "SUB|SUBTR", "sync": 1}]},
         {"name": "MIP da subtração", "rows": 1, "cols": 2, "cells": [
             {"series": "SUB|SUBTR|DIN|DYN|VIBRANT", "plane": "Axial", "recon": "mip", "slab": 40},
             {"series": "SUB|SUBTR|DIN|DYN|VIBRANT", "plane": "Sagital", "recon": "mip", "slab": 40}]},
         ETAPA_MIP_MEIA_MAMA,
         ETAPA_DINAMICA,
     ]},
    {"name": "TC de tórax", "modality": "CT", "description": "TORAX|TÓRAX|CHEST|THORAX", "enabled": True,
     "prior": False,
     "steps": [
         {"name": "Mediastino", "rows": 1, "cols": 2, "cells": [
             {"series": "MEDIAST|PARTES MOLES|SOFT|STANDARD|PADRAO|AXIAL", "window": "2", "sync": 1},
             {"series": "MEDIAST|PARTES MOLES|SOFT|STANDARD|PADRAO|AXIAL", "plane": "Coronal",
              "window": "2", "sync": 1}]},
         {"name": "Pulmão", "rows": 1, "cols": 2, "cells": [
             {"series": "PULM|LUNG|PARENQ|ALTA RES|HR|AXIAL", "window": "1", "sync": 1},
             {"series": "PULM|LUNG|PARENQ|ALTA RES|HR|AXIAL", "plane": "Coronal", "window": "1", "sync": 1}]},
         {"name": "Pulmão MIP", "rows": 1, "cols": 2, "cells": [
             {"series": "PULM|LUNG|PARENQ|ALTA RES|HR|AXIAL", "recon": "mip", "plane": "Axial", "slab": 10,
              "window": "1"},
             {"series": "PULM|LUNG|PARENQ|ALTA RES|HR|AXIAL", "plane": "Coronal", "recon": "mip", "slab": 10,
              "window": "1"}]},
     ]},
    {"name": "RM de crânio", "modality": "MR", "description": "CRANIO|CRÂNIO|ENCEFALO|ENCÉFALO|BRAIN|HEAD",
     "enabled": True, "prior": False,
     "steps": [
         {"name": "T2, FLAIR e difusão", "rows": 1, "cols": 3, "cells": [
             {"series": "T2", "sync": 1}, {"series": "FLAIR", "sync": 1}, {"series": "DWI|DIFUS|ADC", "sync": 1}]},
         {"name": "Pós-contraste", "rows": 1, "cols": 3, "cells": [
             {"series": "T1 SE|T1 FSE|T1", "sync": 1},
             {"series": "T1 POS|T1 GD|T1+C|POS|GD|MPRAGE|BRAVO|3D T1", "sync": 1},
             {"series": "MPRAGE|BRAVO|3D T1|T1 3D|T1 POS|GD", "plane": "Coronal"}]},
     ]},
]
FABRICA_VERSAO = "0.94"
#: Etapas de fábrica que chegaram depois do protocolo: entram uma vez no protocolo dele de mesmo nome
#: (se ele não tiver uma etapa com esse nome). As outras etapas dele ficam como estão.
ETAPAS_NOVAS = {"0.90": {"RM de mama": [ETAPA_MIP_MEIA_MAMA]}, "0.94": {"RM de mama": [ETAPA_DINAMICA]}}


def acrescentar_os_de_fabrica(settings) -> list[str]:
    """Uma vez (marca de versão): quem já tem protocolos gravados ganha os de fábrica que faltam, pelo
    nome. Os dele não são tocados. Devolve os nomes acrescentados."""
    if settings is None or settings.get("hanging_fabrica", "") == FABRICA_VERSAO:
        return []
    gravados = settings.get("hanging_protocols")
    novos: list[str] = []
    if isinstance(gravados, list) and gravados:
        nomes = {str(p.get("name", "")).strip().lower() for p in gravados}
        faltam = [dict(p) for p in DEFAULT_PROTOCOLS if p["name"].lower() not in nomes]
        gravados = list(gravados)
        feita = str(settings.get("hanging_fabrica", "") or "0")
        for versao, por_nome in ETAPAS_NOVAS.items():
            if _versao(feita) >= _versao(versao):
                continue
            for i, p in enumerate(gravados):
                extras = por_nome.get(str(p.get("name", "")).strip())
                if not extras or not isinstance(p, dict):
                    continue
                proto = convertido(p)
                ja = {str(st.get("name", "")).strip().lower() for st in proto.get("steps", [])}
                mais = [dict(st) for st in extras if st["name"].lower() not in ja]
                if mais:
                    proto["steps"] = list(proto.get("steps", [])) + mais
                    gravados[i] = proto
                    novos += [f"{p['name']} ▸ {st['name']}" for st in mais]
        if faltam:
            novos += [p["name"] for p in faltam]
        settings.set("hanging_protocols", gravados + faltam)
    settings.set("hanging_fabrica", FABRICA_VERSAO)
    try:
        settings.save()
    except Exception:  # noqa: BLE001
        pass
    return novos


def _versao(v: str) -> tuple:
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return (0,)


def protocols(settings) -> list[dict]:
    p = settings.get("hanging_protocols") if settings is not None else None
    return list(p) if isinstance(p, list) and p else [dict(x) for x in DEFAULT_PROTOCOLS]


def _words(text: str) -> set[str]:
    return {w for w in re.split(r"[^A-Z0-9▦]+", (text or "").upper()) if w}


def pattern_match(pattern: str, words: set[str], text: str) -> bool:
    """Todas as palavras de uma das alternativas precisam aparecer (palavra inteira ou prefixo ≥3)."""
    for alt in (pattern or "").upper().split("|"):
        need = [w for w in re.split(r"[^A-Z0-9▦]+", alt) if w]
        if need and all(w in words or (len(w) >= 3 and w in text) for w in need):
            return True
    return False


def find_protocol(settings, modalities: set[str], description: str) -> dict | None:
    """O protocolo de exibição do exame — para tudo menos mamografia.

    Mamografia fica de fora aqui, e não só nos padrões de fábrica: protocolo MG gravado por quem
    usava a versão antiga também é ignorado, senão ele voltaria a disputar com a aba Mamografia.
    """
    desc = (description or "").upper()
    for p in protocols(settings):
        if not p.get("enabled", True) or p.get("modality", "").upper() not in modalities:
            continue
        if p.get("modality", "").upper() in SEM_PROTOCOLO_GENERICO:
            continue
        d = p.get("description", "")
        if d and not any(x.strip() and x.strip().upper() in desc for x in d.split("|")):
            continue
        return p
    return None


def plano_de_monitores(settings, modalities: set, description: str, quantos: int) -> list | None:
    """O plano de cada monitor, quando o protocolo tiver um para essa quantidade de telas.

    Devolve uma lista com `quantos` itens, cada um `{"layout": [l, c], "cells": [...]}`, ou None —
    e aí quem chama divide as séries na ordem, como antes.
    """
    if quantos < 2 or (modalities & SEM_PROTOCOLO_GENERICO):
        return None
    proto = find_protocol(settings, modalities, description)
    if proto is None:
        return None
    planos = (proto.get("monitores") or {}).get(str(quantos))
    if not planos or len(planos) != quantos:
        return None
    return [dict(x) for x in planos]


def series_words(repo, series) -> tuple[set[str], str]:
    """Palavras que descrevem a série: descrição, lateralidade e incidência (lidas do 1º arquivo)."""
    text = f"{series.description or ''}"
    try:
        inst = repo.instances_for_series(series.series_uid)
        if inst:
            import pydicom
            ds = pydicom.dcmread(inst[0]["path"], stop_before_pixels=True, force=True)
            lat = str(ds.get("ImageLaterality", "") or ds.get("Laterality", "") or "")
            view = str(ds.get("ViewPosition", "") or "")
            text += f" {lat} {view}"
    except Exception as e:  # noqa: BLE001
        log.debug("hanging: não leu cabeçalho: %s", e)
    return _words(text), text.upper()


def assign(cells: list[str], candidates: list[tuple[str, set[str], str]]) -> list[str | None]:
    """Para cada célula, a primeira série livre que combina com o padrão."""
    used: set[str] = set()
    out: list[str | None] = []
    for pat in cells:
        pick = next((uid for uid, words, text in candidates if uid not in used and pattern_match(pat, words, text)),
                    None)
        if pick:
            used.add(pick)
        out.append(pick)
    return out
