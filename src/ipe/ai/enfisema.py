"""Enfisema na TC: % de baixa atenuação (< −950 HU) por pulmão e por lobo (0.99.77).

Os lobos vêm do TotalSegmentator (tarefa `total`, `lung_*_lobe_*`) e a conta é feita nos HU da série
original. Para cada lobo, cada pulmão e o total:

- **%LAA−950**: fração do volume com HU abaixo de −950 (o limiar validado contra a anatomia patológica por
  Gevenois et al., Am J Respir Crit Care Med 1996);
- **Perc15**: o HU do percentil 15 (quanto mais baixo, mais enfisema; usado no seguimento);
- volume (mL) e HU médio;
- a distribuição: lobos superiores contra inferiores (predomínio superior, inferior ou homogêneo).

Cada lobo é erodido 1 voxel (a borda com a parede e o mediastino tem volume parcial). As vias aéreas dentro do
lobo (brônquios lobares e segmentares) entram na conta: somam pouco, mas somam, e a tela diz.

O número depende de como a TC foi feita, e a elegibilidade avisa: corte fino (≤ 1,5 mm), filtro suave
(ex.: B30, STANDARD; filtro de pulmão/osso aumenta o ruído e a %LAA), sem contraste, inspiração plena. A
traqueia serve de conferência da calibração do ar (perto de −1000 HU).

A referência vai como **texto ao lado**, nunca como veredito: na literatura, %LAA−950 acima de ~5–6% costuma
ser tratado como enfisema relevante (ex.: COPDGene usa 5%).

Saída: SEG "Enfisema (< -950 HU) · TotalSegmentator" (série 983), só na série calculada, e um **achado**
(`ai/achados.py`) "Enfisema (%LAA−950)", que se revisa e vai ao laudo como os outros.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from ipe.ai import achados as AC

log = logging.getLogger(__name__)

FERRAMENTA = "enfisema"
TITULO = "Enfisema: % abaixo de −950 HU por pulmão e lobo (IA)"
MARCA = "· TotalSegmentator"
DESC_SEG = f"Enfisema (< -950 HU) {MARCA}"          # hífen comum: o DICOM (Latin-1) não tem o "−"
SERIE_SEG = 983
MIN_CORTES = 40
MODALIDADES = ("CT",)
MOTIVO_MODALIDADE = "O enfisema é medido na TC."
MODELO = "TotalSegmentator total (lobos pulmonares) + limiar de −950 HU"
CHAVE_SAIDA = "enfisema"
TIPO = "Enfisema (%LAA−950)"
LIMIAR = -950.0
PERCENTIL = 15
EROSAO = 1
ESPESSURA_MAX = 1.5

LOBOS = {"lung_upper_lobe_right": "LSD", "lung_middle_lobe_right": "LM", "lung_lower_lobe_right": "LID",
         "lung_upper_lobe_left": "LSE", "lung_lower_lobe_left": "LIE"}
NOME_LOBO = {"LSD": "lobo superior direito", "LM": "lobo médio", "LID": "lobo inferior direito",
             "LSE": "lobo superior esquerdo", "LIE": "lobo inferior esquerdo"}
DIREITO, ESQUERDO = ("LSD", "LM", "LID"), ("LSE", "LIE")
SUPERIORES, INFERIORES = ("LSD", "LSE"), ("LID", "LIE")
_DUROS = ("LUNG", "BONE", "SHARP", "EDGE", "DETAIL", "B60", "B70", "B80", "BR6", "BR7", "BL5", "BL6", "BL7",
          "BI6", "BI7", "FC5", "FC8", "YA", "YB", "YC")
_CONTRASTE = ("C/C", "COM CONTRASTE", "CONTRASTE", "ARTERIAL", "PORTAL", "VENOSA", "ANGIO", "CONTRAST", "C+")

# Configurações ▸ CAD/IA ▸ Enfisema
CHAVE_AUTO = "enfisema.auto"
CHAVE_EXAME_CONTEM = "enfisema.exame_contem"
CHAVE_MODALIDADES = "enfisema.modalidades"
CHAVE_PRIOR_CT = "enfisema.prioridade_ct"
CHAVE_ESPESSURA = "enfisema.espessura_max"
CHAVE_MIN_CORTES = "enfisema.min_cortes"
CHAVE_DESTINOS = "enfisema.destinos"
PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "TORAX|TÓRAX|CHEST|THORAX|PULMAO|PULMÃO|LUNG|TCAR|HRCT|ALTA RESOLUCAO|TORAX E ABDOME",
    CHAVE_MODALIDADES: ["CT"],
    CHAVE_PRIOR_CT: "PARTES MOLES|MEDIASTINO|STANDARD|STD|SOFT|B30|B31|BR40|SEM CONTRASTE|PULMAO|LUNG",
    CHAVE_ESPESSURA: 2.0,
    CHAVE_MIN_CORTES: MIN_CORTES,
    CHAVE_DESTINOS: [],
}
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_CT, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES}
NOME_CADIA = "Enfisema (%LAA−950)"
TITULO_CADIA = "Enfisema na TC de tórax: % abaixo de −950 HU por pulmão e por lobo (TotalSegmentator + limiar)"
EXPLICACAO_CADIA = ("Na TC de tórax: separa os cinco lobos e mede, em cada lobo, em cada pulmão e no total, a "
                    "fração do volume abaixo de −950 HU (%LAA−950), o percentil 15 do HU (Perc15) e o volume, com a "
                    "distribuição entre lobos superiores e inferiores. Avisa quando a série não serve bem (corte "
                    "grosso, filtro duro, contraste). Os resultados aparecem em Aplicações ▸ Achados de IA, para "
                    "conferir antes do laudo.")


def config(settings, chave):
    if chave == CHAVE_MODALIDADES:
        return ["CT"]
    if settings is None:
        return PADROES.get(chave)
    try:
        v = settings.get(chave, PADROES.get(chave))
    except Exception:  # noqa: BLE001
        v = PADROES.get(chave)
    return PADROES.get(chave) if v is None else v


def exame_serve(info: dict, settings=None) -> bool:
    from ipe.ai import totalseg as TS
    return TS.exame_serve(info, settings, PERFIL, config)


def escolher_serie(repo, study_uid: str, settings=None):
    from ipe.ai import totalseg as TS
    return TS.escolher_serie(repo, study_uid, settings, PERFIL, config, min_absoluto=MIN_CORTES)


def ja_feita(repo, study_uid: str) -> bool:
    from ipe.ai import totalseg as TS
    return TS.ja_segmentado(repo, study_uid, DESC_SEG)


def tarefas(modalidade: str = "CT", settings=None) -> list[dict]:
    return [{"nome": "total", "roi": list(LOBOS) + ["trachea"], "fast": True, "rotulo": "lobos pulmonares",
             "enfisema": True}]


# ------------------------------------------------------------------ a conta
@dataclass
class Resultado:
    regioes: dict = field(default_factory=dict)       # sigla/"D"/"E"/"total" -> {laa, perc15, vol_ml, media}
    razao_sup_inf: float | None = None
    distribuicao: str = ""
    traqueia_hu: float | None = None
    laa: np.ndarray | None = None                     # máscara (bbox) das voxels < −950 nos pulmões
    laa_offset: tuple = (0, 0, 0)
    centro: list | None = None
    avisos: list = field(default_factory=list)
    elegibilidade: str = ""
    versao: str = ""
    series_uid: str = ""


def _cabecalho(t) -> dict:
    try:
        import pydicom
        ds = pydicom.dcmread(t.frames[0].path, stop_before_pixels=True, force=True,
                             specific_tags=["ConvolutionKernel", "SliceThickness", "ContrastBolusAgent",
                                            "SeriesDescription"])
    except Exception:  # noqa: BLE001
        return {}
    from pydicom.multival import MultiValue
    k = ds.get("ConvolutionKernel", "")
    k = " ".join(str(x) for x in k) if isinstance(k, (list, tuple, MultiValue)) else str(k or "")
    return {"kernel": k.strip(), "espessura": ds.get("SliceThickness"),
            "contraste": str(ds.get("ContrastBolusAgent", "") or "").strip(),
            "descricao": str(ds.get("SeriesDescription", "") or "")}


def filtro_duro(kernel: str) -> bool:
    k = (kernel or "").upper().replace(" ", "")
    return any(p.replace(" ", "") in k for p in _DUROS)


def _medidas(hu: np.ndarray, voxel_ml: float) -> dict:
    if hu.size == 0:
        return {}
    return {"laa": float((hu < LIMIAR).mean() * 100.0), "perc15": float(np.percentile(hu, PERCENTIL)),
            "vol_ml": float(hu.size * voxel_ml), "media": float(hu.mean())}


def calcular(t, rotulos: dict, settings=None) -> Resultado:
    from ipe.ai import cefalometria as CF
    from ipe.ai.composicao import _ero3
    vol = t.vol
    res = Resultado(versao=getattr(t, "versao", ""), series_uid=t.series_uid)
    ms = CF.Mascaras(vol, rotulos)
    dados = vol.data
    voxel_ml = float(vol.dx * vol.dy * abs(vol.dz)) / 1000.0
    cab = _cabecalho(t)
    esp = float(cab.get("espessura") or 0) or abs(float(vol.dz))
    desc = (t.descricao_serie or cab.get("descricao") or t.series_uid[-8:])
    res.elegibilidade = (f"TC, série “{desc}”, {dados.shape[0]} cortes de {esp:.2f} mm, pixel {vol.dy:.2f} × "
                         f"{vol.dx:.2f} mm" + (f", filtro {cab['kernel']}" if cab.get("kernel") else ""))
    hus: dict[str, np.ndarray] = {}
    uniao = np.zeros(dados.shape, bool)
    for classe, sigla in LOBOS.items():
        m = ms.get(classe)
        if m is None or not m.any():
            continue
        me = _ero3(m, EROSAO)
        me = me if me.sum() > 200 else m
        uniao |= me
        hus[sigla] = np.asarray(dados[me], np.float32)
    if not hus:
        res.avisos.append("a IA não achou os pulmões nesta série")
        return res
    faltam = [NOME_LOBO[s] for s in LOBOS.values() if s not in hus]
    if faltam:
        res.avisos.append("a IA não separou: " + ", ".join(faltam) + " (o pulmão daquele lado fica sem esse lobo)")
    for sigla, h in hus.items():
        res.regioes[sigla] = _medidas(h, voxel_ml)
    for chave, grupo in (("D", DIREITO), ("E", ESQUERDO), ("total", tuple(LOBOS.values()))):
        h = [hus[s] for s in grupo if s in hus]
        if h:
            res.regioes[chave] = _medidas(np.concatenate(h), voxel_ml)
    sup = [hus[s] for s in SUPERIORES if s in hus]
    inf = [hus[s] for s in INFERIORES if s in hus]
    if sup and inf:
        ls = float((np.concatenate(sup) < LIMIAR).mean() * 100)
        li = float((np.concatenate(inf) < LIMIAR).mean() * 100)
        res.razao_sup_inf = round(ls / li, 2) if li > 0.05 else None
        if max(ls, li) >= 1.0:
            if li <= 0.05 or ls / max(li, 1e-9) >= 1.5:
                res.distribuicao = "predomínio nos lobos superiores"
            elif ls / max(li, 1e-9) <= 1 / 1.5:
                res.distribuicao = "predomínio nos lobos inferiores"
            else:
                res.distribuicao = "distribuição homogênea entre lobos superiores e inferiores"
    # a máscara das áreas de baixa atenuação, recortada na caixa dos pulmões
    laa = uniao & (dados < LIMIAR)
    if laa.any():
        ks, js, is_ = (np.nonzero(laa.any(axis=a)) for a in ((1, 2), (0, 2), (0, 1)))
        k0, k1, j0, j1, i0, i1 = ks[0][0], ks[0][-1] + 1, js[0][0], js[0][-1] + 1, is_[0][0], is_[0][-1] + 1
        res.laa = laa[k0:k1, j0:j1, i0:i1]
        res.laa_offset = (int(k0), int(j0), int(i0))
    kk, jj, ii = np.argwhere(uniao).mean(axis=0)
    res.centro = [float(x) for x in vol.voxel_to_patient(ii, jj, kk)]
    # a conferência da calibração e da técnica
    tr = ms.get("trachea")
    if tr is not None and tr.sum() > 50:
        tre = _ero3(tr, 1)
        tre = tre if tre.sum() > 20 else tr
        res.traqueia_hu = float(np.median(dados[tre]))
        if abs(res.traqueia_hu + 1000) > 30:
            res.avisos.append(f"ar da traqueia em {res.traqueia_hu:.0f} HU (o esperado é perto de −1000): a "
                              f"calibração mexe na %LAA")
    if esp > ESPESSURA_MAX:
        res.avisos.append(f"cortes de {esp:.1f} mm: a %LAA−950 é validada em cortes finos (≤ 1,5 mm); corte grosso "
                          f"a subestima")
    if cab.get("kernel") and filtro_duro(cab["kernel"]):
        res.avisos.append(f"filtro {cab['kernel']} (duro): o ruído aumenta a %LAA; o padrão é filtro suave "
                          f"(ex.: B30, STANDARD)")
    from ipe.ai.totalseg import _sem_acento
    d = _sem_acento(((t.descricao_serie or "") + " " + cab.get("descricao", "")).upper())
    if cab.get("contraste") or (any(p in d for p in _CONTRASTE) and "SEM CONTRASTE" not in d):
        res.avisos.append("série com contraste: a densidade do parênquima sobe um pouco e a %LAA cai")
    res.avisos.append("o padrão é TC em inspiração plena (esta série não diz se foi); as vias aéreas dentro dos "
                      "lobos entram na conta")
    res.avisos.append("referência: limiar de −950 HU validado contra a anatomia patológica (Gevenois et al., Am J "
                      "Respir Crit Care Med 1996); %LAA−950 acima de ~5–6% costuma ser tratado como enfisema "
                      "relevante — texto de referência, não diagnóstico")
    return res


def _n(v, u, n, casas=1):
    return AC.numero(None if v is None else round(float(v), casas), u, n)


def numeros(res: Resultado) -> dict:
    out = {}
    tot = res.regioes.get("total")
    if tot:
        out["laa_total"] = _n(tot["laa"], "%", "%LAA−950 total")
        out["perc15_total"] = _n(tot["perc15"], "HU", "Perc15 total", 0)
        out["vol_total"] = _n(tot["vol_ml"], "mL", "Volume pulmonar", 0)
    for chave, nome in (("D", "pulmão direito"), ("E", "pulmão esquerdo")):
        if chave in res.regioes:
            out[f"laa_{chave}"] = _n(res.regioes[chave]["laa"], "%", f"%LAA−950 {nome}")
    for sigla in LOBOS.values():
        if sigla in res.regioes:
            out[f"laa_{sigla}"] = _n(res.regioes[sigla]["laa"], "%", f"%LAA−950 {sigla}")
    if res.razao_sup_inf is not None:
        out["sup_inf"] = _n(res.razao_sup_inf, "", "Superiores / inferiores", 2)
    return out


def itens_para_o_banco(res: Resultado, t, versao: str) -> list[dict]:
    if not res.regioes:
        return []
    return [{"series_uid": t.series_uid, "modelo": MODELO, "versao": versao or res.versao, "rotulo": "E",
             "tipo": TIPO, "local": "pulmões" + (f" ({res.distribuicao})" if res.distribuicao else ""),
             "posicao": res.centro, "numeros": numeros(res),
             "elegibilidade": res.elegibilidade + (". Atenção: " + "; ".join(res.avisos) if res.avisos else "")}]


def gravar(t, res: Resultado, versao: str, db, storage_root, repo=None, settings=None) -> dict:
    import shutil
    import tempfile
    from pathlib import Path
    from types import SimpleNamespace

    from ipe.ai.totalseg_saida import _caminho_do_sop
    from ipe.db.repository import Repository
    from ipe.imaging.seg_writer import build_seg
    from ipe.importer.scanner import Importer
    repo = repo or Repository(db)
    for se in repo.series_for_study(t.study_uid):
        if (se.description or "") == DESC_SEG:
            try:
                repo.delete_series(se.series_uid, Path(storage_root))
            except Exception:  # noqa: BLE001
                log.exception("trocar a SEG de enfisema anterior")
    out = {"series": [], "ferramenta": FERRAMENTA}
    if res.laa is not None and res.laa.any():
        vol = t.vol
        segs = [(SimpleNamespace(mask=res.laa, offset=res.laa_offset), "Baixa atenuação (< -950 HU)",
                 (250, 120, 40))]
        ds = build_seg(vol, segs, vol.source_path, frames=t.frames, series_number=SERIE_SEG, description=DESC_SEG,
                       algoritmo=("AUTOMATIC", f"TotalSegmentator {versao} + limiar −950 HU".strip()),
                       anatomia=True)
        tmp = Path(tempfile.mkdtemp(prefix="dv_enf_"))
        try:
            ds.save_as(tmp / "seg.dcm", enforce_file_format=True)
            r = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([tmp])
            out["series"] += sorted(getattr(r, "new_series", None) or [])
            out["seg_sop"] = str(ds.SOPInstanceUID)
            out["seg_path"] = _caminho_do_sop(db, t.study_uid, out["seg_sop"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    out["achados"] = repo.gravar_achados(t.study_uid, FERRAMENTA, itens_para_o_banco(res, t, versao))
    return out


def _pct(v) -> str:
    return "—" if v is None else f"{float(v):.1f}".replace(".", ",") + "%"


def resumo(res: Resultado) -> str:
    tot = res.regioes.get("total")
    if not tot:
        return res.avisos[0] if res.avisos else "nada medido"
    txt = f"%LAA−950 {_pct(tot['laa'])} (D {_pct(res.regioes.get('D', {}).get('laa'))}, " \
          f"E {_pct(res.regioes.get('E', {}).get('laa'))})"
    return txt + (f", {res.distribuicao}" if res.distribuicao else "")


def n_itens(res: Resultado) -> int:
    return int(bool(res.regioes))


def mensagem(res: Resultado, minutos: float) -> str:
    msg = (f"Enfisema pronto em {minutos:.1f} min — {resumo(res)}. Os números por lobo estão em Aplicações ▸ "
           f"Achados de IA, para conferir antes do laudo; as áreas abaixo de −950 HU estão na série “{DESC_SEG}”.")
    avisos = [a for a in res.avisos if not a.startswith(("referência", "o padrão é TC"))]
    if avisos:
        msg += "\n\nConfira: " + "; ".join(avisos) + "."
    return msg


def frase(a: dict) -> str:
    n = AC.numeros_validos(a)

    def v(k, casas=1):
        x = (n.get(k) or {}).get("v")
        return None if x is None else f"{float(x):.{casas}f}".replace(".", ",")
    txt = f"Áreas de baixa atenuação pulmonar (< −950 HU) em {v('laa_total')}% do volume pulmonar"
    lados = [f"{nome} {v(k)}%" for k, nome in (("laa_D", "direito"), ("laa_E", "esquerdo")) if v(k) is not None]
    if lados:
        txt += " (" + ", ".join(lados) + ")"
    local = a.get("local", "")
    if "(" in local:
        txt += ", com " + local[local.index("(") + 1:].rstrip(")")
    lobos = [f"{s} {v('laa_' + s)}%" for s in LOBOS.values() if v("laa_" + s) is not None]
    if lobos:
        txt += ". Por lobo: " + ", ".join(lobos)
    if v("perc15_total", 0):
        txt += f". Perc15: {v('perc15_total', 0)} HU"
    return txt + "."
