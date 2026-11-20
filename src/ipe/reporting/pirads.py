"""0.100.79: RM de próstata — o fluxo PI-RADS® v2.1 sem IA: volume da glândula e densidade do PSA, cada lesão com a
zona, os setores do mapa, o tamanho, as pontuações de T2, difusão e DCE, o ADC e a extensão extraprostática; a
categoria de cada lesão e a geral; o mapa de setores pintado (esquema), o texto do laudo e o SR.

Pedido dele (20/11/2026): *"Fluxo PI-RADS sem IA: volume e densidade do PSA, PI-RADS por lesão ligado aos setores,
ADC, curva DCE, laudo e SR"*, mais o volume automático (TotalSegmentator) e, à parte, as zonas e a detecção por
modelos de pesquisa (instalados à parte, com a licença aceita). Aqui não há Qt nem rede.

**Regras da categoria** (ACR PI-RADS® v2.1, 2019):

- zona periférica (PZ): manda a **difusão**; difusão 3 com **DCE positivo** vira 4;
- zona de transição (TZ): manda o **T2**; T2 2 com difusão ≥ 4 vira 3; T2 3 com difusão 5 vira 4;
- sem difusão adequada: na PZ vale o T2 (com a mesma regra do DCE); na TZ, o T2;
- biparamétrica (sem DCE): a PZ com difusão 3 fica 3;
- estroma fibromuscular anterior e zona central: o PI-RADS v2.1 não traz tabela própria — o Ipê usa a regra da TZ
  no estroma anterior e a da PZ na zona central, e o médico troca pela categoria manual quando discordar.

A pontuação 5 pede ≥ 15 mm ou extensão extraprostática, e a 4, menos de 15 mm: quando o tamanho e a pontuação não
combinam, sai um aviso (a categoria não muda sozinha).

**Formato** (guardado por exame em `revisao_ia`, módulo "pirads"):

    {"psa": 6.2, "psa_data": "2026-10-12", "diametros": [45, 50, 38], "volume_usar": "" | "auto" | "elipsoide",
     "volume_auto": {"ml": 41.8, "fonte": "TotalSegmentator", "pesquisa": false, "diametros": [..], "series_uid": ".."},
     "biparametrico": false, "qualidade": "", "hemorragia": false, "outros": "texto livre",
     "lesoes": [{"n": 1, "zona": "PZ", "setores": ["medio_PZpl_D"], "tamanho_mm": 12, "t2": 4, "dwi": 4, "dce": "+",
                 "adc": 750, "epe": "nao", "descricao": "", "categoria_manual": "", "imagem": {...},
                 "origem": "medico" | "picai", "pesquisa": false, "conferida": true, "probabilidade": null}]}
"""
from __future__ import annotations

import json
import logging
import math
import re
from functools import lru_cache

log = logging.getLogger(__name__)

MODULO = "pirads"
MODELO_ESQUEMA = "prostata"
ID_ESQUEMA = "0a1ad5000079"                 # o esquema do PI-RADS dentro da lista de esquemas do exame (um só)
MARCA_PESQUISA = "modelo de pesquisa — não usar para diagnóstico"
MAX_LESOES = 12

ZONAS = {"PZ": "zona periférica", "TZ": "zona de transição", "CZ": "zona central",
         "AS": "estroma fibromuscular anterior"}
#: qual sequência manda na zona (ver o texto do módulo)
DOMINANTE = {"PZ": "dwi", "CZ": "dwi", "TZ": "t2", "AS": "t2"}
CATEGORIAS = {
    "1": "probabilidade muito baixa — câncer clinicamente significativo altamente improvável",
    "2": "probabilidade baixa — câncer clinicamente significativo improvável",
    "3": "probabilidade intermediária — presença de câncer clinicamente significativo equívoca",
    "4": "probabilidade alta — câncer clinicamente significativo provável",
    "5": "probabilidade muito alta — câncer clinicamente significativo altamente provável",
}
CORES = {"1": "#78909c", "2": "#689f38", "3": "#f9a825", "4": "#ef6c00", "5": "#c62828"}
DCE = {"+": "positivo", "-": "negativo", "": "não avaliado"}
EPE = {"": "", "nao": "sem sinais de extensão extraprostática", "suspeita": "suspeita de extensão extraprostática",
       "sim": "com extensão extraprostática"}
_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: setor do mapa -> zona (pela parte do meio do id: base_PZpl_D -> PZpl -> PZ)
_ZONA_DO_CURTO = {"PZa": "PZ", "PZpl": "PZ", "PZpm": "PZ", "TZa": "TZ", "TZp": "TZ", "CZ": "CZ", "AS": "AS"}


# ---------------------------------------------------------------------- os setores do mapa (o modelo "prostata")
@lru_cache(maxsize=1)
def _modelo() -> dict:
    from ipe.reporting import esquemas as E
    return next((m for m in E._de_fabrica() if m["id"] == MODELO_ESQUEMA), {})


def setores() -> list[dict]:
    """[{id, nome, zona, nivel, lado}] na ordem do mapa (sem vesículas e esfíncter, que não recebem lesão)."""
    out = []
    for s in _modelo().get("setores") or []:
        z = zona_do_setor(s["id"])
        if not z:
            continue
        nivel, _c, lado = s["id"].split("_")
        out.append({"id": s["id"], "nome": s["nome"], "zona": z, "nivel": nivel, "lado": lado})
    return out


def zona_do_setor(sid: str) -> str:
    partes = (sid or "").split("_")
    return _ZONA_DO_CURTO.get(partes[1], "") if len(partes) == 3 else ""


def nome_do_setor(sid: str) -> str:
    return next((s["nome"] for s in _modelo().get("setores") or [] if s["id"] == sid), sid)


def centro_do_setor(sid: str) -> tuple[float, float] | None:
    """O meio do setor no mapa, em fração da largura e da altura (onde vai o número da lesão)."""
    m = _modelo()
    s = next((x for x in m.get("setores") or [] if x["id"] == sid), None)
    if not s or not s.get("p"):
        return None
    xs, ys = zip(*s["p"])
    # centroide do polígono (fórmula do laço); se degenerado, a média dos vértices
    a = cx = cy = 0.0
    n = len(xs)
    for i in range(n):
        x0, y0, x1, y1 = xs[i], ys[i], xs[(i + 1) % n], ys[(i + 1) % n]
        c = x0 * y1 - x1 * y0
        a += c
        cx += (x0 + x1) * c
        cy += (y0 + y1) * c
    if abs(a) < 1e-6:
        cx, cy = sum(xs) / n, sum(ys) / n
    else:
        cx, cy = cx / (3 * a), cy / (3 * a)
    return cx / float(m.get("w") or 1000), cy / float(m.get("h") or 1000)


def setores_de(zona: str = "", nivel: str = "", lado: str = "") -> list[str]:
    return [s["id"] for s in setores() if (not zona or s["zona"] == zona) and (not nivel or s["nivel"] == nivel)
            and (not lado or s["lado"] == lado)]


# ---------------------------------------------------------------------- conferir o que chega das telas
def _num(v, lo: float, hi: float, casas: int = 2) -> float | None:
    try:
        x = float(str(v).replace(",", ".")) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None
    if x is None or x != x or math.isinf(x):
        return None
    return round(max(lo, min(hi, x)), casas)


def _pontos(v) -> int | None:
    try:
        x = int(v)
    except (TypeError, ValueError):
        return None
    return x if 1 <= x <= 5 else None


def _imagem(im) -> dict | None:
    if not isinstance(im, dict) or not im.get("sop_uid"):
        return None
    return {"series_uid": str(im.get("series_uid") or "")[:64], "sop_uid": str(im["sop_uid"])[:64],
            "frame": int(_num(im.get("frame", 0), 0, 100000, 0) or 0), "rotulo": str(im.get("rotulo") or "")[:80]}


def normalizar_lesao(l: dict, n: int) -> dict:
    ids = {s["id"] for s in setores()}
    zona = str(l.get("zona") or "").upper()
    sets = [s for s in dict.fromkeys(l.get("setores") or []) if isinstance(s, str) and s in ids][:12]
    if zona not in ZONAS and sets:                   # sem zona, vale a do primeiro setor
        zona = zona_do_setor(sets[0])
    origem = "picai" if l.get("origem") == "picai" else "medico"
    out = {"n": n, "zona": zona if zona in ZONAS else "", "setores": sets,
           "tamanho_mm": _num(l.get("tamanho_mm"), 0, 200, 1), "t2": _pontos(l.get("t2")), "dwi": _pontos(l.get("dwi")),
           "dce": l.get("dce") if l.get("dce") in DCE else "", "adc": _num(l.get("adc"), 0, 5000, 0),
           "epe": l.get("epe") if l.get("epe") in EPE else "", "descricao": str(l.get("descricao") or "").strip()[:300],
           "categoria_manual": str(l.get("categoria_manual") or "") if str(l.get("categoria_manual") or "")
           in CATEGORIAS else "", "origem": origem,
           "pesquisa": bool(l.get("pesquisa")) or origem == "picai",
           "conferida": bool(l.get("conferida", origem == "medico")),
           "probabilidade": _num(l.get("probabilidade"), 0, 1, 3)}
    im = _imagem(l.get("imagem"))
    if im:
        out["imagem"] = im
    return out


def normalizar(d: dict | None) -> dict:
    d = d if isinstance(d, dict) else {}
    diam = [_num(x, 0, 200, 1) or 0.0 for x in (d.get("diametros") or [])[:3]]
    diam = diam if len(diam) == 3 and any(diam) else []          # parcial fica (o elipsoide pede os três)
    va = d.get("volume_auto")
    auto = None
    if isinstance(va, dict) and _num(va.get("ml"), 0.1, 2000, 1):
        da = [_num(x, 0, 300, 1) for x in (va.get("diametros") or [])[:3]]
        auto = {"ml": _num(va.get("ml"), 0.1, 2000, 1), "fonte": str(va.get("fonte") or "segmentação")[:60],
                "pesquisa": bool(va.get("pesquisa")), "diametros": [x for x in da if x] if all(da) and len(da) == 3
                else [], "series_uid": str(va.get("series_uid") or "")[:64], "quando": str(va.get("quando") or "")[:32]}
    data = str(d.get("psa_data") or "")
    lesoes = [normalizar_lesao(l, i + 1) for i, l in enumerate([x for x in (d.get("lesoes") or [])
                                                                 if isinstance(x, dict)][:MAX_LESOES])]
    return {"psa": _num(d.get("psa"), 0, 10000, 2), "psa_data": data if _DATA.match(data) else "",
            "diametros": diam, "volume_auto": auto,
            # "" = ninguém escolheu: vale a segmentação quando houver, senão o elipsoide
            "volume_usar": d.get("volume_usar") if d.get("volume_usar") in ("elipsoide", "auto") else "",
            "biparametrico": bool(d.get("biparametrico")), "qualidade": str(d.get("qualidade") or "").strip()[:200],
            "hemorragia": bool(d.get("hemorragia")), "outros": str(d.get("outros") or "").strip()[:2000],
            "geral_manual": str(d.get("geral_manual") or "") if str(d.get("geral_manual") or "") in CATEGORIAS else "",
            "lesoes": lesoes}


# ---------------------------------------------------------------------- as contas
def volume_elipsoide(diametros) -> float | None:
    """0,52 × AP × transverso × craniocaudal (mm → mL)."""
    if not diametros or len(diametros) != 3 or not all(diametros):
        return None
    a, b, c = (float(x) for x in diametros)
    return round(0.52 * a * b * c / 1000.0, 1)


def volume(d: dict) -> tuple[float | None, str, bool]:
    """(mL, de onde veio, se veio de um modelo de pesquisa)."""
    auto = d.get("volume_auto")
    elip = volume_elipsoide(d.get("diametros"))
    if auto and (d.get("volume_usar") != "elipsoide" or elip is None):
        return float(auto["ml"]), auto.get("fonte") or "segmentação", bool(auto.get("pesquisa"))
    return elip, ("elipsoide" if elip is not None else ""), False


def psad(d: dict) -> float | None:
    v, _f, _p = volume(d)
    if not v or d.get("psa") is None:
        return None
    return round(float(d["psa"]) / v, 2)


def categoria(l: dict, biparametrico: bool = False) -> tuple[str, list[str]]:
    """(categoria "1"–"5" ou "" se faltam dados, avisos) de uma lesão, pela regra do PI-RADS v2.1."""
    avisos = []
    if l.get("categoria_manual"):
        return l["categoria_manual"], avisos
    zona, t2, dwi = l.get("zona") or "", l.get("t2"), l.get("dwi")
    if zona not in ZONAS:
        return "", ["falta a zona"]
    dce = "" if biparametrico else (l.get("dce") or "")
    if DOMINANTE[zona] == "dwi":
        base = dwi if dwi else t2
        if base is None:
            return "", ["falta a pontuação da difusão"]
        if not dwi:
            avisos.append("sem difusão: categoria pelo T2")
        cat = 4 if base == 3 and dce == "+" else base
        dom = base
    else:
        if t2 is None:
            return "", ["falta a pontuação de T2"]
        cat = t2
        if t2 == 2 and dwi and dwi >= 4:
            cat = 3
        elif t2 == 3 and dwi == 5:
            cat = 4
        dom = t2
    tam, epe = l.get("tamanho_mm"), l.get("epe")
    if dom == 4 and ((tam and tam >= 15) or epe == "sim"):
        avisos.append("≥ 15 mm ou extensão extraprostática: pela definição, a pontuação dominante seria 5")
    if dom == 5 and tam and tam < 15 and epe != "sim":
        avisos.append("pontuação 5 pede ≥ 15 mm ou extensão extraprostática")
    if zona in ("AS", "CZ"):
        avisos.append(f"{ZONAS[zona]}: sem tabela própria no PI-RADS v2.1 — confira a categoria")
    return str(cat), avisos


def calcular(d: dict) -> dict:
    """O estado com as contas: volume, densidade do PSA, a categoria de cada lesão e a geral."""
    d = normalizar(d)
    v, fonte, pesq_v = volume(d)
    lesoes = []
    for l in d["lesoes"]:
        c, av = categoria(l, d["biparametrico"])
        lesoes.append({**l, "categoria": c, "avisos": av})
    cats = [l["categoria"] for l in lesoes if l["categoria"]]
    geral = d["geral_manual"] or (max(cats, key=int) if cats else "")
    return {**d, "lesoes": lesoes, "volume_ml": v, "volume_fonte": fonte, "psad": psad(d), "geral": geral,
            "pesquisa": pesq_v or any(l["pesquisa"] for l in lesoes),
            "a_conferir": sum(1 for l in lesoes if l["pesquisa"] and not l["conferida"])}


# ---------------------------------------------------------------------- texto do laudo
def _f(v, casas: int = 1) -> str:
    if v is None:
        return "—"
    s = f"{float(v):.{casas}f}"
    return s.replace(".", ",")


def _mm(v) -> str:
    """Medida em mm sem o ",0" quando é inteira (12 mm; 12,5 mm)."""
    if v is None:
        return "—"
    return str(int(round(float(v)))) if abs(float(v) - round(float(v))) < 0.05 else _f(v)


def _data(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if _DATA.match(iso or "") else ""


_NIVEIS = ("base", "terço médio", "ápice")


def onde(l: dict) -> str:
    """Os setores da lesão por extenso, juntando os níveis da mesma área ("zona periférica posterolateral direita,
    base e terço médio"); sem setor, a zona."""
    if not l.get("setores"):
        return ZONAS.get(l.get("zona") or "", "localização não informada")
    grupos: dict[str, list[str]] = {}
    for s in l["setores"]:
        area, _v, nivel = nome_do_setor(s).rpartition(", ")
        grupos.setdefault(area or nivel, [])
        if area and nivel not in grupos[area]:
            grupos[area].append(nivel)
    partes = []
    for area, niveis in grupos.items():
        niveis = sorted(niveis, key=lambda n: _NIVEIS.index(n) if n in _NIVEIS else 9)
        if len(niveis) == 3:
            partes.append(f"{area}, da base ao ápice")
        elif niveis:
            partes.append(f"{area}, " + " e ".join(niveis))
        else:
            partes.append(area)
    return "; ".join(partes)


def texto_volume(d: dict) -> str:
    c = d if "volume_ml" in d else calcular(d)
    partes = []
    v = c["volume_ml"]
    if v:
        if c["volume_fonte"] == "elipsoide":
            a, b, cc = c["diametros"]
            partes.append(f"Próstata com volume estimado de {_f(v)} mL (diâmetros anteroposterior {_mm(a)}, transverso "
                          f"{_mm(b)} e craniocaudal {_mm(cc)} mm; fórmula do elipsoide).")
        else:
            txt = f"Próstata com volume de {_f(v)} mL pela segmentação automática ({c['volume_fonte']})"
            dd = (c.get("volume_auto") or {}).get("diametros") or []
            if dd:
                txt += f"; diâmetros {_mm(dd[0])} × {_mm(dd[1])} × {_mm(dd[2])} mm (AP × transverso × craniocaudal)"
            partes.append(txt + (f" — {MARCA_PESQUISA}" if (c.get("volume_auto") or {}).get("pesquisa") else "") + ".")
    if c.get("psa") is not None:
        txt = f"PSA de {_f(c['psa'], 2)} ng/mL" + (f" ({_data(c['psa_data'])})" if c.get("psa_data") else "")
        if c.get("psad") is not None:
            txt += f"; densidade do PSA de {_f(c['psad'], 2)} ng/mL/cm³"
        partes.append(txt + ".")
    return " ".join(partes)


def texto_lesao(l: dict, biparametrico: bool = False) -> str:
    seq = []
    if l.get("t2"):
        seq.append(f"T2 {l['t2']}")
    if l.get("dwi"):
        seq.append(f"difusão {l['dwi']}")
    if not biparametrico and l.get("dce"):
        seq.append(f"DCE {DCE[l['dce']]}")
    txt = f"Lesão {l['n']} — {onde(l)}"
    det = []
    if l.get("tamanho_mm"):
        det.append(f"{_mm(l['tamanho_mm'])} mm")
    if l.get("descricao"):
        det.append(l["descricao"].rstrip("."))
    if seq:
        det.append(", ".join(seq))
    if l.get("adc"):
        det.append(f"ADC médio de {_f(l['adc'], 0)} × 10⁻⁶ mm²/s")
    if l.get("epe"):
        det.append(EPE[l["epe"]])
    if det:
        txt += ": " + "; ".join(det)
    if l.get("categoria"):
        txt += f". PI-RADS {l['categoria']}"
    if l.get("pesquisa"):
        txt += (" (sugerida por " + MARCA_PESQUISA + (", conferida pelo médico" if l.get("conferida") else
                                                      ", ainda não conferida") + ")")
    return txt + "."


def texto_achados(d: dict) -> str:
    c = d if "volume_ml" in d else calcular(d)
    linhas = []
    tv = texto_volume(c)
    if tv:
        linhas.append(tv)
    if c.get("qualidade"):
        linhas.append(f"Qualidade do exame: {c['qualidade'].rstrip('.')}.")
    if c.get("hemorragia"):
        linhas.append("Há sinais de hemorragia pós-biópsia, que pode limitar a avaliação.")
    if c["biparametrico"]:
        linhas.append("Exame biparamétrico (sem estudo dinâmico com contraste).")
    if c["lesoes"]:
        linhas += [texto_lesao(l, c["biparametrico"]) for l in c["lesoes"]]
    else:
        linhas.append("Não há lesão focal com categoria PI-RADS 3 ou maior.")
    if c.get("outros"):
        linhas.append(c["outros"])
    if c.get("pesquisa"):
        linhas.append(f"Atenção: parte destes dados veio de um {MARCA_PESQUISA}.")
    return "\n".join(linhas)


def texto_impressao(d: dict) -> str:
    c = d if "volume_ml" in d else calcular(d)
    if not c["geral"]:
        return "Sem lesão focal com categoria PI-RADS 3 ou maior." if not c["lesoes"] else "PI-RADS: ___"
    quais = [l for l in c["lesoes"] if l.get("categoria") == c["geral"]]
    txt = f"PI-RADS {c['geral']}: {CATEGORIAS[c['geral']]}"
    if quais:
        txt += " (" + "; ".join(f"lesão {l['n']}, {onde(l)}" for l in quais) + ")"
    linhas = [txt + "."]
    if c.get("psad") is not None:
        linhas.append(f"Densidade do PSA: {_f(c['psad'], 2)} ng/mL/cm³.")
    return "\n".join(linhas)


def texto_laudo(d: dict) -> str:
    c = calcular(d)
    return texto_achados(c) + "\n\nIMPRESSÃO:\n" + texto_impressao(c)


# ---------------------------------------------------------------------- guardar
def ler(repo, study_uid: str) -> dict | None:
    try:
        r = repo.revisao_ia(study_uid, MODULO)
        return normalizar(json.loads(r["dados"])) if r and r.get("dados") else None
    except Exception:  # noqa: BLE001
        log.debug("pirads: ler", exc_info=True)
        return None


def vazio(d: dict | None) -> bool:
    if not d:
        return True
    return not (d.get("lesoes") or d.get("psa") is not None or d.get("diametros") or d.get("volume_auto")
                or d.get("outros"))


def gravar(repo, study_uid: str, d: dict, usuario: str = "", com_esquema: bool = True) -> dict:
    """Guarda o formulário (conferido) e, com `com_esquema`, pinta o mapa de setores na lista de esquemas do exame.
    Devolve o estado com as contas."""
    limpo = normalizar(d)
    repo.salvar_revisao_ia(study_uid, MODULO, "editado", True, usuario or "", json.dumps(limpo, ensure_ascii=False))
    if com_esquema:
        try:
            gravar_esquema(repo, study_uid, limpo, usuario)
        except Exception:  # noqa: BLE001
            log.exception("pirads: o mapa de setores")
    return calcular(limpo)


def esquema(d: dict) -> dict:
    """O mapa de setores da próstata do PI-RADS: os setores de cada lesão pintados com a categoria dela (a maior,
    quando duas lesões dividem um setor) e o número da lesão no meio do primeiro setor."""
    c = d if "volume_ml" in d else calcular(d)
    pint: dict[str, str] = {}
    marcas = []
    for l in c["lesoes"]:
        cat = l.get("categoria") or ""
        for s in l.get("setores") or []:
            if cat and int(cat) >= int(pint.get(s, "0")):
                pint[s] = cat
        centro = centro_do_setor(l["setores"][0]) if l.get("setores") else None
        if centro is None:
            continue
        texto = f"PI-RADS {cat}" if cat else "PI-RADS ?"
        if l.get("tamanho_mm"):
            texto += f" — {_mm(l['tamanho_mm'])} mm"
        if l.get("pesquisa") and not l.get("conferida"):
            texto += " (modelo de pesquisa, a conferir)"
        m = {"tipo": "ponto", "n": l["n"], "p": [list(centro)], "cor": "#111111", "l": 3, "texto": texto}
        if l.get("imagem"):
            m["imagem"] = l["imagem"]
        marcas.append(m)
    return {"id": ID_ESQUEMA, "modelo": MODELO_ESQUEMA, "titulo": "PI-RADS — mapa de setores", "marcas": marcas,
            "setores": pint}


def gravar_esquema(repo, study_uid: str, d: dict, usuario: str = "") -> list[dict]:
    """Troca (ou acrescenta) o esquema do PI-RADS na lista de esquemas do exame; os outros ficam como estavam."""
    from ipe.reporting import esquemas as E
    lista = [e for e in E.ler(repo, study_uid) if e.get("id") != ID_ESQUEMA]
    e = esquema(d)
    if e["marcas"] or e["setores"]:
        lista.append(e)
    return E.gravar(repo, study_uid, lista, usuario)


def aplicar_volume_auto(repo, study_uid: str, ml: float, diametros=None, fonte: str = "TotalSegmentator",
                        pesquisa: bool = False, series_uid: str = "", usuario: str = "") -> dict:
    """A segmentação da glândula terminou: o volume entra no formulário (e passa a valer, se o médico não escolheu o
    elipsoide)."""
    from datetime import datetime
    d = ler(repo, study_uid) or normalizar({})
    d["volume_auto"] = {"ml": round(float(ml), 1), "fonte": fonte, "pesquisa": bool(pesquisa),
                        "diametros": [round(float(x), 1) for x in (diametros or [])][:3], "series_uid": series_uid,
                        "quando": datetime.now().isoformat(timespec="minutes")}
    return gravar(repo, study_uid, d, usuario)


def aplicar_candidatos(repo, study_uid: str, candidatos: list[dict], usuario: str = "") -> dict:
    """As lesões sugeridas pelo modelo de pesquisa (PI-CAI) entram como lesões **a conferir**, marcadas como de
    pesquisa. As sugestões anteriores que o médico ainda não conferiu saem; as conferidas ficam."""
    d = ler(repo, study_uid) or normalizar({})
    ficam = [l for l in d["lesoes"] if not (l.get("origem") == "picai" and not l.get("conferida"))]
    novas = []
    for c in candidatos[:max(0, MAX_LESOES - len(ficam))]:
        novas.append({"zona": c.get("zona") or "", "setores": c.get("setores") or [],
                      "tamanho_mm": c.get("tamanho_mm"), "origem": "picai", "pesquisa": True, "conferida": False,
                      "probabilidade": c.get("probabilidade"), "imagem": c.get("imagem"),
                      "descricao": c.get("descricao") or ""})
    d["lesoes"] = ficam + novas
    return gravar(repo, study_uid, d, usuario)
