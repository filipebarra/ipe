"""Revisão da densidade mamária (0.100.43): o programa sugere, o radiologista confirma ou corrige.

Pedido dele: *"queria atuar como revisor, confirmando a leitura automática"*. Para cada exame de mamografia da
fila, o Ipê calcula duas sugestões com o que é livre para estar no programa — a **rede da NYU** (categoria a–d,
licença BSD-2) e o **% de área densa** (limiar de Otsu, com a faixa de referência) — e o médico marca a categoria
dele. A revisão fica no banco, com as sugestões que ele viu, o aparelho e se o exame era de **controle** (sugestão
escondida até ele responder: quem revisa com a resposta à vista tende a concordar com ela).

A concordância sai daqui: kappa ponderado (quadrático) de cada método contra o revisor, acerto exato, acerto denso
(c/d) × não denso (a/b) e a matriz de confusão — no total, nos exames de controle à parte e por aparelho. É essa
tabela, nos exames dele, que diz se o método serve; e é com ela que, mais tarde, se calibra o % de área por aparelho.

Nada aqui depende de tela: a janela (`ui/densidade_revisao.py`) só chama estas funções.
"""
from __future__ import annotations

import hashlib
import logging
from collections import Counter

log = logging.getLogger(__name__)

CATEGORIAS = ("a", "b", "c", "d")
NAO_AVALIAVEL = "x"
NOMES = {"a": "A — quase toda gordurosa", "b": "B — áreas esparsas de tecido fibroglandular",
         "c": "C — heterogeneamente densa", "d": "D — extremamente densa", "x": "Não avaliável"}
METODOS = {"nyu": "Rede (NYU)", "area": "% de área"}
#: fração dos exames com a sugestão escondida até a resposta (o controle do viés de ancoragem)
CONTROLE_PADRAO = 0.10


# ------------------------------------------------------------------ quais imagens
def _lado(ds) -> str:
    v = str(getattr(ds, "ImageLaterality", "") or getattr(ds, "Laterality", "") or "").upper()[:1]
    return v if v in ("L", "R") else ""


def _incidencia(ds) -> str:
    v = str(getattr(ds, "ViewPosition", "") or "").upper()
    if not v:
        try:
            v = str(ds.ViewCodeSequence[0].CodeMeaning or "").upper()
        except Exception:  # noqa: BLE001
            v = ""
    if "MLO" in v or "MEDIO-LATERAL OBLIQUE" in v or "MEDIOLATERAL OBLIQUE" in v:
        return "MLO"
    if v.startswith("CC") or "CRANIO-CAUDAL" in v or "CRANIOCAUDAL" in v:
        return "CC"
    return ""


def cabecalho(caminho: str) -> dict | None:
    """O que a fila precisa de cada arquivo, sem ler os pixels. None: não é mamografia 2D que sirva."""
    import pydicom
    try:
        ds = pydicom.dcmread(str(caminho), stop_before_pixels=True, force=True)
    except Exception:  # noqa: BLE001
        log.debug("revisão de densidade: não li %s", caminho, exc_info=True)
        return None
    if str(getattr(ds, "Modality", "") or "").upper() != "MG":
        return None
    try:
        quadros = int(getattr(ds, "NumberOfFrames", 1) or 1)
    except (TypeError, ValueError):
        quadros = 1
    tipo = [str(x).upper() for x in (getattr(ds, "ImageType", None) or [])]
    return {
        "caminho": str(caminho), "lado": _lado(ds), "incidencia": _incidencia(ds),
        "fabricante": str(getattr(ds, "Manufacturer", "") or "").strip(),
        "modelo": str(getattr(ds, "ManufacturerModelName", "") or "").strip(),
        "processamento": str(getattr(ds, "PresentationIntentType", "") or "").upper() == "FOR PROCESSING",
        "tomo": quadros > 1 or any(t in ("TOMO", "TOMOSYNTHESIS", "VOLUME") for t in tipo),
        "implante": str(getattr(ds, "BreastImplantPresent", "") or "").upper() == "YES",
    }


def escolher_vistas(cabecalhos: list[dict]) -> tuple[dict, str, list[str]]:
    """As quatro incidências do exame ({"R-CC": caminho, ...}), o aparelho e os avisos.

    Ficam de fora a tomossíntese (cortes), as imagens "para processamento" (brutas) e as sem lado ou incidência.
    Quando há mais de uma da mesma incidência (repetição), vale a última do exame."""
    avisos: list[str] = []
    vistas: dict[str, str] = {}
    aparelhos: Counter = Counter()
    implante = False
    for c in cabecalhos:
        if not c or c["tomo"] or c["processamento"] or not c["lado"] or not c["incidencia"]:
            continue
        vistas[f"{c['lado']}-{c['incidencia']}"] = c["caminho"]
        aparelhos[" ".join(x for x in (c["fabricante"], c["modelo"]) if x) or "?"] += 1
        implante = implante or c["implante"]
    faltam = [k for k in ("R-CC", "L-CC", "R-MLO", "L-MLO") if k not in vistas]
    if faltam:
        avisos.append("Faltam incidências: " + ", ".join(faltam) + " (a rede pede as quatro).")
    if implante:
        avisos.append("Exame com prótese (o arquivo declara).")
    aparelho = aparelhos.most_common(1)[0][0] if aparelhos else ""
    return vistas, aparelho, avisos


# ------------------------------------------------------------------ sugestão
def sugerir(vistas: dict, dados=None, stop=None) -> dict:
    """As sugestões dos dois métodos para o exame. Cada um falha sozinho, com o motivo, sem derrubar o outro."""
    from ipe.imaging import density as D
    out: dict = {"nyu": None, "nyu_probs": [], "nyu_aviso": "", "area_pd": None, "area": None,
                 "area_por_mama": {}, "avisos": []}
    caminhos = list(dict.fromkeys(vistas.values()))
    if caminhos:
        try:
            medidas = D.medir_imagens(caminhos, stop=stop, metodos=(D.LIMIAR,))
            boas = [m for m in medidas if m.mama_cm2 > 0]
            if boas:
                out["area_pd"] = round(D.do_exame(boas), 1)
                out["area"] = D.faixa_de(out["area_pd"])
                out["area_por_mama"] = {k: round(v, 1) for k, v in D.por_mama(boas).items()}
            for m in medidas:
                out["avisos"].extend(a for a in m.avisos if a not in out["avisos"])
        except Exception as e:  # noqa: BLE001
            log.debug("revisão de densidade: %% de área", exc_info=True)
            out["avisos"].append(f"O % de área falhou: {e}")
    if stop is not None and stop.is_set():
        return out
    if len(vistas) < 4:
        out["nyu_aviso"] = "A rede precisa das quatro incidências (CC e MLO dos dois lados)."
        return out
    from ipe.ai import densidade_nyu as N
    ok, motivo = N.disponivel(dados)
    if not ok:
        out["nyu_aviso"] = motivo
        return out
    try:
        prob, aviso = N.do_exame(vistas, dados)
        if prob is not None:
            out["nyu_probs"] = [round(float(p), 4) for p in prob]
            out["nyu"] = N.faixa_de(prob)
        out["nyu_aviso"] = aviso or ""
    except Exception as e:  # noqa: BLE001
        log.debug("revisão de densidade: rede", exc_info=True)
        out["nyu_aviso"] = f"A rede falhou: {e}"
    return out


def de_controle(study_uid: str, usuario: str, fracao: float) -> bool:
    """O exame é de controle (sugestão escondida até a resposta)? Sorteio fixo por exame e revisor: reabrir a fila
    não troca o exame de grupo."""
    if fracao <= 0:
        return False
    h = hashlib.sha256(f"{study_uid}|{usuario}|densidade".encode()).digest()
    return int.from_bytes(h[:4], "big") / 2 ** 32 < fracao


# ------------------------------------------------------------------ concordância
def kappa_ponderado(a: list[str], b: list[str], cats=CATEGORIAS) -> float | None:
    """Kappa de Cohen com peso quadrático (o usual para categorias ordenadas como a–d). None sem dados ou sem
    variação nenhuma (tudo numa categoria só, dos dois lados)."""
    pares = [(x, y) for x, y in zip(a, b) if x in cats and y in cats]
    n = len(pares)
    if n == 0:
        return None
    k = len(cats)
    idx = {c: i for i, c in enumerate(cats)}
    obs = [[0.0] * k for _ in range(k)]
    for x, y in pares:
        obs[idx[x]][idx[y]] += 1
    lin = [sum(obs[i]) for i in range(k)]
    col = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    w = [[((i - j) ** 2) / ((k - 1) ** 2) for j in range(k)] for i in range(k)]
    do = sum(w[i][j] * obs[i][j] for i in range(k) for j in range(k)) / n
    de = sum(w[i][j] * lin[i] * col[j] for i in range(k) for j in range(k)) / (n * n)
    if de == 0:
        return None
    return 1.0 - do / de


def _denso(c: str) -> bool:
    return c in ("c", "d")


def _resumo(pares: list[tuple[str, str]]) -> dict:
    validos = [(r, s) for r, s in pares if r in CATEGORIAS and s in CATEGORIAS]
    n = len(validos)
    if not n:
        return {"n": 0, "kappa": None, "exato": None, "denso": None, "matriz": {}}
    matriz: dict = {}
    for r, s in validos:
        matriz.setdefault(r, Counter())[s] += 1
    return {
        "n": n,
        "kappa": kappa_ponderado([r for r, _ in validos], [s for _, s in validos]),
        "exato": sum(r == s for r, s in validos) / n,
        "denso": sum(_denso(r) == _denso(s) for r, s in validos) / n,
        "matriz": {r: dict(c) for r, c in matriz.items()},
    }


def concordancia(revisoes: list[dict]) -> dict:
    """A tabela da revisão. `revisoes`: dicts com "categoria" (a revisão), "nyu", "area", "controle" e "aparelho".

    Para cada método: o total, só os exames de controle (sugestão escondida) e por aparelho. "Não avaliável" e
    os exames sem a sugestão daquele método ficam fora da conta daquele método."""
    feitas = [r for r in revisoes if r.get("categoria") in CATEGORIAS]
    saida: dict = {"revisados": len(revisoes), "avaliaveis": len(feitas),
                   "nao_avaliaveis": sum(1 for r in revisoes if r.get("categoria") == NAO_AVALIAVEL),
                   "distribuicao": dict(Counter(r["categoria"] for r in feitas)), "metodos": {}}
    aparelhos = sorted({r.get("aparelho") or "?" for r in feitas})
    for m in METODOS:
        pares = [(r["categoria"], r.get(m) or "") for r in feitas]
        saida["metodos"][m] = {
            "total": _resumo(pares),
            "controle": _resumo([(r["categoria"], r.get(m) or "") for r in feitas if r.get("controle")]),
            "vista": _resumo([(r["categoria"], r.get(m) or "") for r in feitas if not r.get("controle")]),
            "aparelhos": {a: _resumo([(r["categoria"], r.get(m) or "") for r in feitas
                                      if (r.get("aparelho") or "?") == a]) for a in aparelhos},
        }
    return saida


def _pct(v) -> str:
    return "—" if v is None else f"{100 * v:.0f}%"


def _k(v) -> str:
    return "—" if v is None else f"{v:.2f}".replace(".", ",")


def texto_da_concordancia(c: dict) -> str:
    """O resumo em texto, para a janela e para o CSV."""
    linhas = [f"Revisados: {c['revisados']} (avaliáveis {c['avaliaveis']}, não avaliáveis {c['nao_avaliaveis']})."]
    if c["distribuicao"]:
        linhas.append("Suas categorias: " + " · ".join(f"{k.upper()} {c['distribuicao'].get(k, 0)}"
                                                      for k in CATEGORIAS) + ".")
    for m, nome in METODOS.items():
        t = c["metodos"][m]["total"]
        if not t["n"]:
            linhas.append(f"{nome}: sem exames com sugestão ainda.")
            continue
        ctl = c["metodos"][m]["controle"]
        extra = (f"; nos de controle (sugestão escondida, n = {ctl['n']}): kappa {_k(ctl['kappa'])}, "
                 f"exato {_pct(ctl['exato'])}") if ctl["n"] else ""
        linhas.append(f"{nome} (n = {t['n']}): kappa ponderado {_k(t['kappa'])}, exato {_pct(t['exato'])}, "
                      f"denso × não denso {_pct(t['denso'])}{extra}.")
    return "\n".join(linhas)


def linhas_csv(revisoes: list[dict]) -> list[list[str]]:
    cab = ["study_uid", "data_do_exame", "aparelho", "revisor", "categoria", "controle", "nyu", "nyu_a", "nyu_b",
           "nyu_c", "nyu_d", "area_pd", "area", "quando"]
    out = [cab]
    for r in revisoes:
        p = list(r.get("nyu_probs") or []) + [""] * 4
        out.append([r.get("study_uid", ""), r.get("study_date", ""), r.get("aparelho", ""), r.get("usuario", ""),
                    r.get("categoria", ""), "1" if r.get("controle") else "0", r.get("nyu") or "",
                    *[str(x) for x in p[:4]], "" if r.get("area_pd") is None else str(r["area_pd"]),
                    r.get("area") or "", r.get("quando", "")])
    return out
