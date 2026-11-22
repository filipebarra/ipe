"""Conferência de protocolo de RM (0.100.93) — como o dicompare, para todas as RM.

Pedido dele (21/11/2026): *"pode fazer a conferência. estenda para todas as RMs"* (item 2 da pesquisa Neurodesk,
08/11: "cada aquisição de RM contra um protocolo de referência por aparelho e exame — TR, TE, espessura, matriz,
séries que faltam — com aviso na lista").

Como funciona (só cabeçalho; nada de pixel):

* **Parâmetros de cada série** (`parametros_da_serie`): o que o aparelho grava no DICOM — TR, TE, TI, ângulo, ETL, NEX,
  espessura, espaço entre cortes, matriz de aquisição, FOV, tamanho do pixel, banda, campo, plano (pela orientação),
  2D/3D, a sequência (ScanningSequence + SequenceVariant), os valores de b da difusão e se é pós-contraste.
  Ficam de fora o localizador, a calibração e o que é DERIVED (mapa ADC, subtração, MIP, reformatação): são
  pós-processamento, não aquisição.
* **Protocolo de referência** (`Referencia`): por **exame** (a descrição do estudo, normalizada) e, se quiser, por
  **aparelho** (estação). Cada série esperada tem o nome (a descrição normalizada), os valores e se é obrigatória.
  Nasce de duas formas:
  - de um exame bom (`referencia_do_exame`): "use este como padrão";
  - **do acervo** (`referencia_pelo_acervo`): o protocolo dominante de N exames do mesmo tipo no mesmo aparelho — a
    série que aparece em ≥ 80% dos exames é obrigatória, em ≥ 50% é opcional; número = mediana; o resto = o mais
    comum. É o jeito de cadastrar as 8 RM de uma vez (`referencias_do_acervo`).
* **Conferência** (`conferir`): cada série esperada é procurada no exame pelo nome (e, se não achar, pelo plano +
  sequência); o que falta, o que sobra e cada parâmetro fora da tolerância. Tolerâncias de fábrica em `TOLERANCIAS`
  (relativas em %, absolutas, ou "igual"); cada referência pode ter as suas.
* **Gravidade**: "erro" — série obrigatória faltando, plano, 2D/3D, campo, sequência, valores de b, contraste; "aviso"
  — número fora da tolerância, série opcional faltando, série a mais. O exame fica *conforme*, *com avisos* ou
  *divergente*.

O resultado fica no exame (`revisao_ia`, módulo `MODULO`) e aparece na coluna "Protocolo (RM)" do banco.
Sem Qt.
"""
from __future__ import annotations

import json
import logging
import re
import statistics
import time
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass, field

log = logging.getLogger(__name__)

MODULO = "protocolo_rm"
CHAVE_REFERENCIAS = "rm.protocolos"            # Settings: a lista de referências (dicts)
CHAVE_LIGADO = "rm.conferir_protocolo"         # conferir sozinho na chegada (padrão: ligado)
VERSAO = 1

#: o que não é aquisição de diagnóstico (descrição ou ImageType)
IGNORAR = re.compile(r"\b(loc|localizer|localizador|scout|survey|calibra\w*|asset cal|cal scan|ref scan|"
                     r"pure cal|3[ -]?pl(ane)?|tri[ -]?pilot|aahead\w*|aascout\w*|smart ?exam ?loc)\b", re.I)

#: nome legível de cada parâmetro (em português: passa pelo tr na tela)
NOMES = {
    "tr": "TR (ms)", "te": "TE (ms)", "ti": "TI (ms)", "flip": "Ângulo (°)", "etl": "ETL", "nex": "NEX",
    "espessura": "Espessura (mm)", "espaco": "Espaço entre cortes (mm)", "matriz": "Matriz", "fov": "FOV (mm)",
    "pixel": "Pixel (mm)", "banda": "Banda (Hz/px)", "campo": "Campo (T)", "plano": "Plano", "tipo": "2D/3D",
    "sequencia": "Sequência", "b": "Valores de b", "contraste": "Contraste", "imagens": "Imagens",
}

#: tolerâncias de fábrica: ("rel", %) relativa · ("abs", valor) absoluta · ("igual", None) · ("info", None) só mostra
TOLERANCIAS: dict[str, tuple[str, float | None]] = {
    "tr": ("rel", 10.0), "te": ("rel", 10.0), "ti": ("rel", 10.0), "flip": ("abs", 2.0), "etl": ("abs", 2.0),
    "nex": ("abs", 0.5), "espessura": ("abs", 0.3), "espaco": ("abs", 0.5), "matriz": ("igual", None),
    "fov": ("rel", 10.0), "pixel": ("rel", 10.0), "banda": ("rel", 15.0), "campo": ("igual", None),
    "plano": ("igual", None), "tipo": ("igual", None), "sequencia": ("igual", None), "b": ("igual", None),
    "contraste": ("igual", None), "imagens": ("info", None),
}
#: o que, fora do esperado, é erro (o resto é aviso)
GRAVES = {"campo", "plano", "tipo", "sequencia", "b", "contraste"}
#: ordem das colunas na tela
ORDEM = ["plano", "tipo", "sequencia", "tr", "te", "ti", "flip", "etl", "nex", "espessura", "espaco", "matriz",
         "fov", "pixel", "banda", "b", "contraste", "campo", "imagens"]


# ------------------------------------------------------------------ normalização
def normalizar(txt: str) -> str:
    """'Ax T2 FSE  FS' → 'ax t2 fse fs': minúsculas, sem acento, sem pontuação, espaços simples."""
    t = unicodedata.normalize("NFKD", str(txt or "")).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9+]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _num(v) -> float | None:
    try:
        if v is None or v == "":
            return None
        if isinstance(v, (list, tuple)) or hasattr(v, "__iter__") and not isinstance(v, (str, bytes)):
            v = list(v)[0]
        return float(v)
    except (TypeError, ValueError, IndexError):
        return None


def _r(v: float | None, casas: int = 2) -> float | None:
    return None if v is None else round(float(v), casas)


def plano(iop) -> str:
    """AX, COR, SAG ou OBL pela ImageOrientationPatient (o eixo normal ao corte)."""
    try:
        a = [float(x) for x in iop]
        if len(a) != 6:
            return ""
    except (TypeError, ValueError):
        return ""
    n = (a[1] * a[5] - a[2] * a[4], a[2] * a[3] - a[0] * a[5], a[0] * a[4] - a[1] * a[3])
    m = max(range(3), key=lambda i: abs(n[i]))
    if abs(n[m]) < 0.8:
        return "OBL"
    return ("SAG", "COR", "AX")[m]


def _texto(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)) or (hasattr(v, "__iter__") and not isinstance(v, (str, bytes))):
        return "\\".join(str(x) for x in v)
    return str(v)


def valor_b(ds) -> float | None:
    """O b da imagem: (0018,9087) ou o privado da GE (0043,1039), primeiro número, módulo 10⁹."""
    b = _num(ds.get((0x0018, 0x9087)).value if ds.get((0x0018, 0x9087)) is not None else None)
    if b is not None:
        return b
    el = ds.get((0x0043, 0x1039))
    if el is not None:
        try:
            v = el.value
            v = list(v)[0] if hasattr(v, "__iter__") and not isinstance(v, (str, bytes)) else v
            if isinstance(v, bytes):
                v = v.decode("latin-1").split("\\")[0]
            return float(v) % 1e9
        except (TypeError, ValueError, IndexError):
            return None
    return None


def eh_aquisicao(ds) -> bool:
    """Imagem ORIGINAL de RM que não é localizador nem calibração."""
    if str(getattr(ds, "Modality", "") or "").upper() != "MR":
        return False
    tipo = [str(x).upper() for x in (getattr(ds, "ImageType", None) or [])]
    if tipo and (tipo[0] != "ORIGINAL" or "LOCALIZER" in tipo):
        return False
    if IGNORAR.search(str(getattr(ds, "SeriesDescription", "") or "")):
        return False
    return True


def aparelho(ds) -> str:
    """A chave do aparelho: a estação; sem ela, modelo + número de série."""
    est = str(getattr(ds, "StationName", "") or "").strip()
    if est:
        return est
    return " ".join(x for x in (str(getattr(ds, "ManufacturerModelName", "") or "").strip(),
                                str(getattr(ds, "DeviceSerialNumber", "") or "").strip()) if x)


def parametros_da_serie(ds, n_imagens: int = 0, bs: list[float] | None = None) -> dict:
    """Os parâmetros de aquisição da série, pelo cabeçalho de uma imagem dela (e os b de todas, se for difusão)."""
    rows, cols = int(getattr(ds, "Rows", 0) or 0), int(getattr(ds, "Columns", 0) or 0)
    ps = getattr(ds, "PixelSpacing", None)
    try:
        psr, psc = float(ps[0]), float(ps[1])
    except (TypeError, ValueError, IndexError):
        psr = psc = None
    am = [int(x) for x in (getattr(ds, "AcquisitionMatrix", None) or []) if str(x).isdigit() and int(x) > 0]
    matriz = "×".join(str(x) for x in am[:2]) if len(am) >= 2 else (f"{cols}×{rows}" if rows and cols else "")
    esp = _num(getattr(ds, "SliceThickness", None))
    entre = _num(getattr(ds, "SpacingBetweenSlices", None))
    seq = " ".join(x for x in (_texto(getattr(ds, "ScanningSequence", "")),
                               _texto(getattr(ds, "SequenceVariant", ""))) if x)
    contraste = "pós" if str(getattr(ds, "ContrastBolusAgent", "") or "").strip() else "pré"
    p = {
        "tr": _r(_num(getattr(ds, "RepetitionTime", None)), 1),
        "te": _r(_num(getattr(ds, "EchoTime", None)), 2),
        "ti": _r(_num(getattr(ds, "InversionTime", None)), 1),
        "flip": _r(_num(getattr(ds, "FlipAngle", None)), 1),
        "etl": _r(_num(getattr(ds, "EchoTrainLength", None)), 0),
        "nex": _r(_num(getattr(ds, "NumberOfAverages", None)), 2),
        "espessura": _r(esp, 2),
        "espaco": _r(entre, 2),
        "matriz": matriz,
        "fov": _r(max(rows * psr, cols * psc), 1) if psr and psc and rows and cols else None,
        "pixel": _r(max(psr, psc), 3) if psr and psc else None,
        "banda": _r(_num(getattr(ds, "PixelBandwidth", None)), 1),
        "campo": _r(_num(getattr(ds, "MagneticFieldStrength", None)), 1),
        "plano": plano(getattr(ds, "ImageOrientationPatient", None)),
        "tipo": str(getattr(ds, "MRAcquisitionType", "") or "").upper(),
        "sequencia": seq,
        "b": ",".join(str(int(round(b))) for b in sorted(set(bs))) if bs and len(set(bs)) > 1 else "",
        "contraste": contraste,
        "imagens": int(n_imagens or 0),
    }
    if p["ti"] == 0:
        p["ti"] = None
    return p


# ------------------------------------------------------------------ o exame
def series_do_exame(repo, study_uid: str, ler=None) -> dict:
    """{"exame", "descricao", "aparelho", "data", "series": [{"uid", "numero", "descricao", "nome", "params"}]}.

    `ler(caminho)` → dataset sem pixels (para os testes). Lê o cabeçalho da primeira imagem de cada série e, na
    difusão, os de todas (os valores de b)."""
    import pydicom
    ler = ler or (lambda p: pydicom.dcmread(p, stop_before_pixels=True, force=True))
    if hasattr(repo, "is_cached") and not repo.is_cached(study_uid):
        repo.download(study_uid)
    info = repo.study_info(study_uid) or {}
    out = {"study_uid": study_uid, "descricao": info.get("description", "") or "",
           "exame": normalizar(info.get("description", "")), "aparelho": "", "data": info.get("study_date", "") or "",
           "series": []}
    estacoes = Counter()
    for se in repo.series_for_study(study_uid):
        if str(getattr(se, "modality", "") or "").upper() != "MR":
            continue
        inst = repo.instances_for_series(se.series_uid)
        caminhos = [i["path"] for i in inst if i.get("path")]
        if not caminhos:
            continue
        try:
            ds = ler(caminhos[0])
        except Exception:  # noqa: BLE001
            log.debug("protocolo: não li %s", caminhos[0], exc_info=True)
            continue
        if not eh_aquisicao(ds):
            continue
        estacoes[aparelho(ds)] += 1
        bs = None
        if valor_b(ds) is not None or re.search(r"dwi|diff|dti|difus", str(se.description or ""), re.I):
            bs = []
            for c in caminhos:
                try:
                    b = valor_b(ler(c))
                except Exception:  # noqa: BLE001
                    b = None
                if b is not None:
                    bs.append(b)
        n = sum(int(i.get("frames") or 1) for i in inst)
        out["series"].append({"uid": se.series_uid, "numero": int(getattr(se, "series_number", 0) or 0),
                              "descricao": se.description or "", "nome": normalizar(se.description),
                              "params": parametros_da_serie(ds, n, bs)})
    out["series"].sort(key=lambda s: s["numero"])
    out["aparelho"] = estacoes.most_common(1)[0][0] if estacoes else ""
    return out


# ------------------------------------------------------------------ referências
@dataclass
class Referencia:
    nome: str
    exame: str                                    # descrição do estudo normalizada ("" = qualquer)
    aparelho: str = ""                            # "" = qualquer aparelho
    series: list[dict] = field(default_factory=list)   # {"nome", "descricao", "obrigatoria", "params"}
    tolerancias: dict = field(default_factory=dict)    # parâmetro → [tipo, valor]; vazio = de fábrica
    origem: str = ""
    criado: str = ""
    id: str = ""

    def tolerancia(self, p: str) -> tuple[str, float | None]:
        t = self.tolerancias.get(p)
        if t:
            return (str(t[0]), None if t[1] is None else float(t[1]))
        return TOLERANCIAS.get(p, ("igual", None))

    def para_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def de_dict(cls, d: dict) -> Referencia:
        return cls(nome=str(d.get("nome", "") or ""), exame=str(d.get("exame", "") or ""),
                   aparelho=str(d.get("aparelho", "") or ""), series=list(d.get("series") or []),
                   tolerancias=dict(d.get("tolerancias") or {}), origem=str(d.get("origem", "") or ""),
                   criado=str(d.get("criado", "") or ""), id=str(d.get("id") or _novo_id()))


def _novo_id() -> str:
    import secrets
    return secrets.token_hex(6)


def referencias(settings) -> list[Referencia]:
    out = []
    for d in (settings.get(CHAVE_REFERENCIAS, []) if settings is not None else []) or []:
        try:
            out.append(Referencia.de_dict(d))
        except Exception:  # noqa: BLE001
            log.warning("protocolo: referência inválida %r", d)
    return out


def gravar_referencias(settings, refs: list[Referencia]) -> None:
    settings.set(CHAVE_REFERENCIAS, [r.para_dict() for r in refs])
    settings.save()


def referencia_do_exame(exame: dict, nome: str = "", por_aparelho: bool = True) -> Referencia:
    """O exame vira o padrão: todas as séries obrigatórias, com os valores dele."""
    series, vistos = [], set()
    for s in exame["series"]:
        if s["nome"] in vistos:            # série repetida: vale a última (a refeita)
            series = [x for x in series if x["nome"] != s["nome"]]
        vistos.add(s["nome"])
        series.append({"nome": s["nome"], "descricao": s["descricao"], "obrigatoria": True, "params": dict(s["params"])})
    return Referencia(nome=nome or exame.get("descricao") or exame["exame"], exame=exame["exame"],
                      aparelho=exame["aparelho"] if por_aparelho else "", series=series,
                      origem=f"exame de {exame.get('data', '')}".strip(), criado=time.strftime("%Y-%m-%d"),
                      id=_novo_id())


def _dominante(valores: list):
    vs = [v for v in valores if v not in (None, "")]
    if not vs:
        return None
    if all(isinstance(v, (int, float)) for v in vs):
        return round(statistics.median(vs), 3)
    return Counter(vs).most_common(1)[0][0]


def referencia_pelo_acervo(exames: list[dict], nome: str = "", obrig: float = 0.8, opcional: float = 0.5,
                           por_aparelho: bool = True) -> Referencia | None:
    """O protocolo dominante de vários exames do mesmo tipo (e aparelho): série em ≥ 80% obrigatória, ≥ 50% opcional;
    cada parâmetro: a mediana (número) ou o mais comum (texto)."""
    exames = [e for e in exames if e.get("series")]
    if not exames:
        return None
    n = len(exames)
    conta: Counter = Counter()
    por_nome: dict[str, list[dict]] = {}
    descricao: dict[str, Counter] = {}
    ordem: dict[str, list[int]] = {}
    for e in exames:
        ultimos = {}
        for i, s in enumerate(e["series"]):
            ultimos[s["nome"]] = (i, s)             # repetida: a última
        for nm, (i, s) in ultimos.items():
            conta[nm] += 1
            por_nome.setdefault(nm, []).append(s["params"])
            descricao.setdefault(nm, Counter())[s["descricao"]] += 1
            ordem.setdefault(nm, []).append(i)
    series = []
    for nm, c in conta.items():
        if c / n < opcional:
            continue
        ps = por_nome[nm]
        params = {p: _dominante([x.get(p) for x in ps]) for p in ORDEM}
        if params.get("imagens") is not None:
            params["imagens"] = int(round(params["imagens"]))
        series.append({"nome": nm, "descricao": descricao[nm].most_common(1)[0][0], "obrigatoria": c / n >= obrig,
                       "params": params, "frequencia": round(c / n, 2),
                       "_ordem": statistics.median(ordem[nm])})
    series.sort(key=lambda s: s.pop("_ordem"))
    ex = Counter(e["exame"] for e in exames).most_common(1)[0][0]
    ap = Counter(e["aparelho"] for e in exames).most_common(1)[0][0] if por_aparelho else ""
    desc = Counter(e.get("descricao") or e["exame"] for e in exames).most_common(1)[0][0]
    return Referencia(nome=nome or (f"{desc} · {ap}" if ap else desc), exame=ex, aparelho=ap, series=series,
                      origem=f"acervo: {n} exame(s)", criado=time.strftime("%Y-%m-%d"), id=_novo_id())


def grupos_do_acervo(resumos: list[dict], minimo: int = 5) -> dict[tuple[str, str], list[str]]:
    """{(exame, aparelho): [study_uid…]} com pelo menos `minimo` exames. `resumos`: {"study_uid", "exame",
    "aparelho"} (de `series_do_exame` ou do banco)."""
    g: dict[tuple[str, str], list[str]] = {}
    for r in resumos:
        if r.get("exame"):
            g.setdefault((r["exame"], r.get("aparelho", "")), []).append(r["study_uid"])
    return {k: v for k, v in g.items() if len(v) >= minimo}


def escolher_referencia(exame: dict, refs: list[Referencia]) -> Referencia | None:
    """A do mesmo exame e aparelho; senão a do mesmo exame para qualquer aparelho; empate: a com mais séries em comum."""
    nomes = {s["nome"] for s in exame["series"]}

    def pontos(r: Referencia):
        comum = len(nomes & {s["nome"] for s in r.series})
        return (r.aparelho == exame["aparelho"], comum)
    cand = [r for r in refs if r.exame == exame["exame"] and r.aparelho in ("", exame["aparelho"])]
    if not cand:
        return None
    return max(cand, key=pontos)


# ------------------------------------------------------------------ a conferência
def _fora(p: str, v, ref, tol: tuple[str, float | None]) -> bool:
    tipo, lim = tol
    if tipo == "info" or ref in (None, ""):
        return False
    if v in (None, ""):
        return p in GRAVES or tipo == "igual"
    if tipo == "igual":
        if isinstance(ref, (int, float)) and isinstance(v, (int, float)):
            return abs(float(v) - float(ref)) > 1e-6
        return normalizar(str(v)) != normalizar(str(ref))
    try:
        v, ref = float(v), float(ref)
    except (TypeError, ValueError):
        return str(v) != str(ref)
    if tipo == "rel":
        return abs(v - ref) > abs(ref) * (lim or 0) / 100.0 + 1e-9
    return abs(v - ref) > (lim or 0) + 1e-9


def _txt_tol(tol: tuple[str, float | None]) -> str:
    tipo, lim = tol
    if tipo == "rel":
        return f"±{lim:g}%"
    if tipo == "abs":
        return f"±{lim:g}"
    return ""


def _parecida(s: dict, esperada: dict) -> bool:
    a, b = s["params"], esperada["params"]
    return a.get("plano") == b.get("plano") and a.get("sequencia") == b.get("sequencia") and \
        a.get("tipo") == b.get("tipo") and (a.get("contraste") == b.get("contraste"))


def conferir(exame: dict, ref: Referencia | None) -> dict:
    """{"estado": conforme | avisos | divergente | sem_referencia, "referencia", "series": [...], "extras": [...],
    "n_erros", "n_avisos", "resumo"}. Cada linha de `series`: a esperada, a achada (ou nada) e as diferenças
    [{"param", "valor", "esperado", "tolerancia", "grave"}]."""
    out = {"versao": VERSAO, "quando": time.strftime("%Y-%m-%d %H:%M"), "exame": exame.get("descricao", ""),
           "aparelho": exame.get("aparelho", ""), "referencia": ref.nome if ref else "",
           "referencia_id": ref.id if ref else "", "series": [], "extras": [], "n_erros": 0, "n_avisos": 0}
    if ref is None:
        out.update(estado="sem_referencia", resumo="sem referência")
        return out
    disponiveis = list(exame["series"])
    usados: set[str] = set()
    for esp in ref.series:
        achadas = [s for s in disponiveis if s["nome"] == esp["nome"] and s["uid"] not in usados]
        if not achadas:
            achadas = [s for s in disponiveis if s["uid"] not in usados and _parecida(s, esp)
                       and not any(e["nome"] == s["nome"] for e in ref.series)]
        linha = {"nome": esp["nome"], "descricao": esp["descricao"], "obrigatoria": esp.get("obrigatoria", True),
                 "achada": "", "uid": "", "repeticoes": 0, "difs": [], "situacao": "ok"}
        if not achadas:
            linha["situacao"] = "falta"
            if linha["obrigatoria"]:
                out["n_erros"] += 1
            else:
                out["n_avisos"] += 1
            out["series"].append(linha)
            continue
        s = achadas[-1]                         # repetida: a última (a refeita)
        for x in achadas:
            usados.add(x["uid"])
        linha.update(achada=s["descricao"], uid=s["uid"], repeticoes=len(achadas) - 1)
        for p in ORDEM:
            tol = ref.tolerancia(p)
            v, r = s["params"].get(p), esp["params"].get(p)
            if _fora(p, v, r, tol):
                grave = p in GRAVES
                linha["difs"].append({"param": p, "valor": v, "esperado": r, "tolerancia": _txt_tol(tol),
                                      "grave": grave})
                if grave:
                    out["n_erros"] += 1
                else:
                    out["n_avisos"] += 1
        if any(d["grave"] for d in linha["difs"]):
            linha["situacao"] = "erro"
        elif linha["difs"]:
            linha["situacao"] = "aviso"
        if linha["repeticoes"]:
            linha["nota"] = f"repetida {linha['repeticoes']}×"
        out["series"].append(linha)
    for s in disponiveis:
        if s["uid"] not in usados:
            out["extras"].append({"descricao": s["descricao"], "uid": s["uid"], "params": s["params"]})
    out["n_avisos"] += len(out["extras"])
    if out["n_erros"]:
        out["estado"] = "divergente"
    elif out["n_avisos"]:
        out["estado"] = "avisos"
    else:
        out["estado"] = "conforme"
    out["resumo"] = resumo(out)
    return out


def resumo(r: dict) -> str:
    """Texto curto para a lista: "conforme", "2 divergência(s), 1 aviso(s)"…"""
    e = r.get("estado")
    if e == "sem_referencia":
        return "sem referência"
    if e == "conforme":
        return "conforme"
    partes = []
    faltam = sum(1 for s in r.get("series", []) if s["situacao"] == "falta" and s.get("obrigatoria", True))
    if faltam:
        partes.append(f"falta(m) {faltam} série(s)")
    difs = r.get("n_erros", 0) - faltam
    if difs > 0:
        partes.append(f"{difs} divergência(s)")
    if r.get("n_avisos"):
        partes.append(f"{r['n_avisos']} aviso(s)")
    return ", ".join(partes)


#: marcas da coluna do banco
MARCAS = {"conforme": "✓", "avisos": "△", "divergente": "⚠", "sem_referencia": "·"}


def texto_da_coluna(dados_json: str) -> str:
    try:
        d = json.loads(dados_json or "{}")
    except ValueError:
        return ""
    if not d.get("estado"):
        return ""
    return f"{MARCAS.get(d['estado'], '')} {d.get('resumo', '')}".strip()


# ------------------------------------------------------------------ no exame
def guardar(repo, study_uid: str, resultado: dict) -> None:
    repo.salvar_revisao_ia(study_uid, MODULO, "auto", False, "", json.dumps(resultado, ensure_ascii=False))


def guardado(repo, study_uid: str) -> dict | None:
    try:
        r = repo.revisao_ia(study_uid, MODULO)
    except Exception:  # noqa: BLE001
        return None
    if not r or not r.get("dados"):
        return None
    try:
        return json.loads(r["dados"])
    except ValueError:
        return None


def conferir_exame(repo, settings, study_uid: str, ref: Referencia | None = None, gravar: bool = True,
                   ler=None) -> dict:
    """Lê o exame, escolhe a referência (ou usa a dada), confere e guarda. Exame sem RM: {"estado": "sem_rm"}."""
    ex = series_do_exame(repo, study_uid, ler)
    if not ex["series"]:
        return {"estado": "sem_rm", "resumo": "sem RM", "series": [], "extras": []}
    ref = ref or escolher_referencia(ex, referencias(settings))
    r = conferir(ex, ref)
    r["study_uid"] = study_uid
    if gravar and r["estado"] != "sem_referencia":
        guardar(repo, study_uid, r)
    return r


def ligado(settings) -> bool:
    try:
        return bool(settings.get(CHAVE_LIGADO, True))
    except Exception:  # noqa: BLE001
        return True


def para_csv(linhas: list[dict]) -> str:
    """Relatório: uma linha por diferença (ou por exame conforme)."""
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["data", "exame", "aparelho", "referencia", "estado", "serie", "situacao", "parametro", "valor",
                "esperado", "tolerancia"])
    for r in linhas:
        base = [r.get("data", ""), r.get("exame", ""), r.get("aparelho", ""), r.get("referencia", ""),
                r.get("estado", "")]
        escritas = 0
        for s in r.get("series", []):
            if s["situacao"] == "falta":
                w.writerow(base + [s["descricao"], "falta", "", "", "", ""])
                escritas += 1
            for d in s.get("difs", []):
                w.writerow(base + [s["descricao"], s["situacao"], d["param"], d["valor"], d["esperado"],
                                   d["tolerancia"]])
                escritas += 1
        for x in r.get("extras", []):
            w.writerow(base + [x["descricao"], "a mais", "", "", "", ""])
            escritas += 1
        if not escritas:
            w.writerow(base + ["", "", "", "", "", ""])
    return buf.getvalue()
