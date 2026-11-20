"""0.100.79: lesões da próstata sugeridas por um **modelo de pesquisa** — o nnU-Net de base do desafio PI-CAI
(DIAGNijmegen, semi-supervisionado), instalado à parte e só depois de aceita a licença (pesos CC BY-NC-SA 4.0,
treinados nos dados do PI-CAI, CC BY-NC 4.0: pesquisa e ensino, não clínico, não comercial).

Pedido dele (20/11/2026): *"Zonas e detecção: só se você aceitar como modelo extra opcional de pesquisa, instalado
à parte, como o FLAMeS, com aviso na tela"* — e: *"Marca clara na tela e nas saídas (SEG, SR, laudo): 'modelo de
pesquisa — não usar para diagnóstico'"*.

Entra a RM biparamétrica: **T2 axial** (a série do trabalho), **mapa ADC** e **difusão de b alto** (a imagem de maior
b do exame), as duas reamostradas na grade do T2 pela posição do DICOM (o modelo supõe as sequências alinhadas).
Roda no ambiente próprio (`venv_picai`: nnU-Net 1.7, picai_prep), um fold, em CPU. Sai o mapa de detecção: cada
candidato com a probabilidade do modelo, o volume, o maior diâmetro axial e o lugar (lado e terço pela glândula do
TotalSegmentator; zona pelo modelo das zonas, se instalado). Os candidatos viram achados revisáveis e entram no
PI-RADS como lesões **a conferir**; a SEG leva "PESQUISA" na descrição.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import numpy as np

from ipe.ai import achados as AC

log = logging.getLogger(__name__)

FERRAMENTA = "picai"
TITULO = "Lesões da próstata — modelo de PESQUISA (PI-CAI), não usar para diagnóstico"
DESC_SEG = "PI-CAI candidatos (PESQUISA - não diagnóstico)"
SERIE_SEG = 985
MIN_CORTES = 12
MODALIDADES = ("MR",)
MOTIVO_MODALIDADE = "O modelo do PI-CAI roda na RM de próstata (T2 axial, ADC e difusão de b alto)."
MODELO = "PI-CAI baseline nnU-Net (semi-supervisionado), fold 0 — modelo de pesquisa"
MODELO_EXTRA = "picai"
CHAVE_SAIDA = "picai"
TIPO = "Próstata — candidato (pesquisa)"
LIMIAR_MIN = 0.10                                 # candidatos abaixo disto não viram achado

CHAVE_AUTO = "picai.auto"
CHAVE_EXAME_CONTEM = "picai.exame_contem"
CHAVE_MODALIDADES = "picai.modalidades"
CHAVE_PRIOR_CT = "picai.prioridade"
CHAVE_ESPESSURA = "picai.espessura_max"
CHAVE_MIN_CORTES = "picai.min_cortes"
CHAVE_DESTINOS = "picai.destinos"
PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "PROSTAT|PROSTATE|PI-RADS|PIRADS|MULTIPARAM",
    CHAVE_MODALIDADES: ["MR"],
    CHAVE_PRIOR_CT: "T2 TSE TRA|T2_TSE_TRA|T2 TRA|T2 AX|AX T2|T2",
    CHAVE_ESPESSURA: 5.0,
    CHAVE_MIN_CORTES: MIN_CORTES,
    CHAVE_DESTINOS: [],
}
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_CT, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES,
          "excluir": ("ADC", "DWI", "DIF", "TRACE", "DCE", "SAG", "COR", "SCOUT", "LOCALIZER")}
NOME_CADIA = "Próstata: lesões (PESQUISA)"
TITULO_CADIA = "Lesões da próstata — modelo de pesquisa do PI-CAI (não usar para diagnóstico)"
EXPLICACAO_CADIA = ("Modelo de PESQUISA e ensino (não clínico, não comercial), instalado à parte com a licença aceita: "
                    "na RM biparamétrica (T2 axial, ADC e difusão de b alto) sugere focos suspeitos, com a "
                    "probabilidade do modelo. Só roda à mão (nunca sozinho na chegada). As sugestões entram no "
                    "PI-RADS como lesões a conferir e todas as saídas saem marcadas 'não usar para diagnóstico'.")


def config(settings, chave):
    if chave == CHAVE_MODALIDADES:
        return ["MR"]
    if chave == CHAVE_AUTO:
        return False                              # modelo de pesquisa: nunca sozinho na chegada
    if settings is None:
        return PADROES.get(chave)
    try:
        v = settings.get(chave, PADROES.get(chave))
    except Exception:  # noqa: BLE001
        v = PADROES.get(chave)
    return PADROES.get(chave) if v is None else v


def exame_serve(info: dict, settings=None) -> bool:
    return False                                  # nunca automático


def escolher_serie(repo, study_uid: str, settings=None):
    from ipe.ai import prostata as PR
    return PR.escolher_serie(repo, study_uid, settings)


def ja_feita(repo, study_uid: str) -> bool:
    return bool(repo.achados(study_uid, FERRAMENTA))


def tarefas(modalidade: str = "MR", settings=None) -> list[dict]:
    from ipe.ai import prostata as PR
    out = [{"nome": "total_mr", "roi": ["prostate"], "rotulo": "próstata (TotalSegmentator, para localizar)",
            "prostata": True}]
    if PR.zonas_prontas(settings):
        out.append({"nome": "prostata_zonas", "rotulo": "zonas da próstata (modelo de pesquisa)"})
    out.append({"nome": "picai", "rotulo": "lesões (modelo de pesquisa do PI-CAI)"})
    return out


# ------------------------------------------------------------------ as séries que entram
_ADC = re.compile(r"(?<![A-Z])ADC|APPARENT")
_DWI = re.compile(r"DWI|DIFF|DIF|TRACE|EP2D|RESOLVE|ZOOMIT|B\s?\d{3,4}|CALC")


def series_de_difusao(repo, study_uid: str) -> tuple:
    """(série do ADC, série da difusão) — a de mais imagens de cada tipo; None quando falta."""
    from ipe.ai.totalseg import _sem_acento
    adc, dwi = [], []
    for s in repo.series_for_study(study_uid):
        if (s.modality or "").upper() != "MR":
            continue
        d = _sem_acento(s.description or "")
        if _ADC.search(d):
            adc.append(s)
        elif _DWI.search(d) and "SAG" not in d and "COR" not in d:
            dwi.append(s)
    def maior(xs):
        return max(xs, key=lambda s: s.num_images or 0) if xs else None
    return maior(adc), maior(dwi)


def _volume_de(t, series_uid: str, caminhos: set | None = None):
    from ipe.imaging.series import build_frames
    from ipe.imaging.volume import build_volume
    inst = t.repo.instances_for_series(series_uid)
    if caminhos is not None:
        inst = [i for i in inst if i["path"] in caminhos]
    return build_volume(build_frames(inst, series_uid), t.cache)


def canais_extras(t) -> dict:
    """ADC e a difusão de maior b na grade do T2 (pela posição do DICOM: mesmo exame, mesma referência)."""
    from ipe.ai import extras as EX
    from ipe.ai.totalseg import Falhou
    from ipe.imaging import difusao as DF
    s_adc, s_dwi = series_de_difusao(t.repo, t.study_uid)
    if s_adc is None or s_dwi is None:
        falta = [n for n, s in (("o mapa ADC", s_adc), ("a difusão", s_dwi)) if s is None]
        raise Falhou("O modelo do PI-CAI precisa do T2 axial, do ADC e da difusão; faltam neste exame: "
                     + " e ".join(falta) + ".")
    serie = DF.ler_serie(t.repo, s_dwi.series_uid)
    if not serie.bs:
        raise Falhou("A série de difusão não diz o valor de b: não dá para escolher a imagem de b alto.")
    b = max(serie.bs)
    caminhos = {c.imagens[b] for c in serie.cortes if b in c.imagens}
    v_adc = _volume_de(t, s_adc.series_uid)
    v_hbv = _volume_de(t, s_dwi.series_uid, caminhos)
    t.picai_info = {"adc": s_adc.description or "", "dwi": s_dwi.description or "", "b": float(b)}
    return {"adc": EX.na_grade(t.vol, v_adc, None, fora=0.0), "hbv": EX.na_grade(t.vol, v_hbv, None, fora=0.0)}


# ------------------------------------------------------------------ a conta
@dataclass
class Candidato:
    n: int
    probabilidade: float
    ml: float
    diametro_mm: float
    centro: list
    lado: str = ""
    nivel: str = ""
    zona: str = ""
    setores: list = field(default_factory=list)
    k: int = 0                                    # corte com mais voxels (para ligar a imagem)
    rotulo_id: int = 0                            # o valor do candidato no mapa de rótulos


@dataclass
class Resultado:
    candidatos: list = field(default_factory=list)
    rotulos: np.ndarray | None = None
    offset: tuple = (0, 0, 0)
    prob_caso: float | None = None
    avisos: list = field(default_factory=list)
    elegibilidade: str = ""
    versao: str = ""
    series_uid: str = ""
    calculado: bool = False


def _lugar(vol, m: np.ndarray, glandula: np.ndarray | None, zonas: np.ndarray | None) -> tuple:
    """(lado D/E, nível base/medio/apice, zona PZ/TZ/"", setores) do candidato, pela glândula e pelas zonas."""
    kk, jj, ii = np.nonzero(m)
    c = vol.voxel_to_patient(ii.mean(), jj.mean(), kk.mean())
    lado = nivel = zona = ""
    if glandula is not None and glandula.any():
        gk, gj, gi = np.nonzero(glandula)
        gc = vol.voxel_to_patient(gi.mean(), gj.mean(), gk.mean())
        lado = "E" if c[0] > gc[0] else "D"                   # LPS: x cresce para a esquerda do paciente
        zs = [vol.voxel_to_patient(gi.mean(), gj.mean(), float(k))[2] for k in (gk.min(), gk.max())]
        z0, z1 = min(zs), max(zs)
        f = (c[2] - z0) / (z1 - z0) if z1 > z0 else 0.5
        nivel = "base" if f > 2 / 3 else "medio" if f > 1 / 3 else "apice"
        if zonas is not None:
            v = zonas[m]
            v = v[v > 0]
            if v.size:
                zona = "TZ" if np.bincount(v).argmax() == 1 else "PZ"
        setores = []
        if zona:
            posterior = c[1] > gc[1]                          # LPS: y cresce para trás
            curto = ("PZpl" if posterior else "PZa") if zona == "PZ" else ("TZp" if posterior else "TZa")
            setores = [f"{nivel}_{curto}_{lado}"]
        return lado, nivel, zona, setores
    return lado, nivel, zona, []


def calcular(t, rotulos: dict, settings=None) -> Resultado:
    from ipe.ai.figado_lesoes import _maior_diametro_axial
    vol = t.vol
    info = getattr(t, "picai_info", {}) or {}
    res = Resultado(versao=getattr(t, "versao", ""), series_uid=t.series_uid, calculado=True)
    desc = t.descricao_serie or t.series_uid[-8:]
    res.elegibilidade = (f"RM biparamétrica: T2 “{desc}”, ADC “{info.get('adc', '?')}”, difusão “{info.get('dwi', '?')}” "
                         f"(b {info.get('b', 0):.0f}); {MODELO}")
    lab, classes = rotulos.get("picai", (None, {}))
    if lab is None:
        res.avisos.append("o modelo não devolveu o mapa de detecção")
        return res
    lab = np.asarray(lab)
    gl = None
    tl, tc = rotulos.get("total_mr", (None, {}))
    ids = [k for k, v in (tc or {}).items() if v == "prostate"]
    if tl is not None and ids:
        gl = np.isin(np.asarray(tl), ids)
    zonas = rotulos.get("prostata_zonas", (None, {}))[0]
    zonas = np.asarray(zonas) if zonas is not None else None
    voxel_ml = float(vol.dx * vol.dy * abs(vol.dz)) / 1000.0
    cands = []
    for cid, nome in sorted((classes or {}).items()):
        try:
            p = float(str(nome).rsplit("_", 1)[-1])
        except ValueError:
            continue
        m = lab == int(cid)
        if not m.any() or p < LIMIAR_MIN:
            continue
        kk, jj, ii = np.nonzero(m)
        sub = m[kk.min():kk.max() + 1, jj.min():jj.max() + 1, ii.min():ii.max() + 1]
        lado, nivel, zona, sets = _lugar(vol, m, gl, zonas)
        k_meio = int(np.bincount(kk).argmax())
        cands.append(Candidato(0, round(p, 3), round(float(m.sum()) * voxel_ml, 2),
                               round(_maior_diametro_axial(sub, vol.dx, vol.dy), 1),
                               [float(x) for x in vol.voxel_to_patient(ii.mean(), jj.mean(), kk.mean())],
                               lado, nivel, zona, sets, k_meio, int(cid)))
    cands.sort(key=lambda c: -c.probabilidade)
    for i, c in enumerate(cands, 1):
        c.n = i
    res.candidatos = cands
    res.prob_caso = max((c.probabilidade for c in cands), default=0.0)
    tudo = np.isin(lab, [int(k) for k in (classes or {})]) & (lab > 0)
    if tudo.any():
        kk, jj, ii = np.nonzero(tudo)
        a, b, c0 = kk.min(), jj.min(), ii.min()
        res.rotulos = lab[a:kk.max() + 1, b:jj.max() + 1, c0:ii.max() + 1].copy()
        res.offset = (int(a), int(b), int(c0))
    if not cands:
        res.avisos.append("o modelo não sugeriu nenhum foco")
    if info.get("b") and info["b"] < 1000:
        res.avisos.append(f"a difusão de maior b do exame é b {info['b']:.0f} (o modelo foi treinado com b alto, ≥ 1400)")
    from ipe.reporting.pirads import MARCA_PESQUISA
    res.avisos.append(MARCA_PESQUISA)
    return res


def _n(v, u, n, casas=1):
    return AC.numero(None if v is None else round(float(v), casas), u, n)


_NIVEL = {"base": "base", "medio": "terço médio", "apice": "ápice"}
_LADO = {"D": "à direita", "E": "à esquerda"}


def onde(c: Candidato) -> str:
    from ipe.reporting import pirads as P
    if c.setores:
        return P.nome_do_setor(c.setores[0])
    partes = [x for x in (_NIVEL.get(c.nivel, ""), _LADO.get(c.lado, "")) if x]
    return ", ".join(partes) or "próstata"


def itens_para_o_banco(res: Resultado, t, versao: str) -> list[dict]:
    from ipe.reporting.pirads import MARCA_PESQUISA
    out = []
    for c in res.candidatos:
        out.append({"series_uid": t.series_uid, "modelo": MODELO, "versao": versao or res.versao,
                    "rotulo": f"C{c.n}", "tipo": TIPO, "local": onde(c), "posicao": c.centro,
                    "numeros": {"prob": _n(c.probabilidade, "", "Probabilidade do modelo (pesquisa)", 3),
                                "ml": _n(c.ml, "mL", "Volume", 2), "diam": _n(c.diametro_mm, "mm", "Maior diâmetro axial")},
                    "segmento": c.n,
                    "elegibilidade": f"{MARCA_PESQUISA.upper()}. " + res.elegibilidade +
                                     (". Atenção: " + "; ".join(a for a in res.avisos if a != MARCA_PESQUISA)
                                      if len(res.avisos) > 1 else "")})
    return out


def para_o_pirads(res: Resultado, t) -> list[dict]:
    """Os candidatos no formato das lesões do PI-RADS (entram como a conferir)."""
    out = []
    for c in res.candidatos:
        im = None
        try:
            f = t.frames[c.k] if 0 <= c.k < len(t.frames) else None
            if f is not None and f.sop_uid:
                from ipe.reporting import esquemas as E
                im = {"series_uid": t.series_uid, "sop_uid": f.sop_uid, "frame": int(f.frame_index or 0),
                      "rotulo": E.rotulo_da_imagem(t.repo, t.study_uid, t.series_uid, f.sop_uid,
                                                   int(f.frame_index or 0)) or ""}
        except Exception:  # noqa: BLE001
            log.debug("picai: imagem do candidato", exc_info=True)
        out.append({"zona": c.zona, "setores": c.setores, "tamanho_mm": c.diametro_mm,
                    "probabilidade": c.probabilidade, "imagem": im,
                    "descricao": f"foco sugerido pelo modelo (probabilidade {c.probabilidade:.2f}"
                                 f"{', ' + onde(c) if not c.setores else ''})".replace(".", ",", 1)})
    return out


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
                log.exception("trocar a SEG do PI-CAI anterior")
    out = {"series": [], "ferramenta": FERRAMENTA}
    if res.rotulos is not None and res.candidatos:
        segs = [(SimpleNamespace(mask=res.rotulos == c.rotulo_id, offset=res.offset),
                 f"C{c.n} p={c.probabilidade:.2f} (PESQUISA)", (230, 60, 60))
                for c in res.candidatos if (res.rotulos == c.rotulo_id).any()]
        if segs:
            ds = build_seg(t.vol, segs, t.vol.source_path, frames=t.frames, series_number=SERIE_SEG,
                           description=DESC_SEG, algoritmo=("AUTOMATIC", f"PI-CAI baseline (PESQUISA) {versao}"[:64]))
            tmp = Path(tempfile.mkdtemp(prefix="dv_picai_"))
            try:
                ds.save_as(tmp / "seg.dcm", enforce_file_format=True)
                r = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([tmp])
                out["series"] += sorted(getattr(r, "new_series", None) or [])
                out["seg_sop"] = str(ds.SOPInstanceUID)
                out["seg_path"] = _caminho_do_sop(db, t.study_uid, out["seg_sop"], DESC_SEG)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
    out["achados"] = repo.gravar_achados(t.study_uid, FERRAMENTA, itens_para_o_banco(res, t, versao))
    try:
        from ipe.reporting import pirads as P
        P.aplicar_candidatos(repo, t.study_uid, para_o_pirads(res, t))
    except Exception:  # noqa: BLE001
        log.exception("picai: os candidatos no PI-RADS")
    return out


def resumo(res: Resultado) -> str:
    if not res.candidatos:
        return "nenhum foco sugerido"
    return f"{len(res.candidatos)} foco(s) sugerido(s), maior probabilidade {res.candidatos[0].probabilidade:.2f}"


def n_itens(res: Resultado) -> int:
    return len(res.candidatos)


def mensagem(res: Resultado, minutos: float) -> str:
    from ipe.reporting.pirads import MARCA_PESQUISA
    msg = (f"MODELO DE PESQUISA — não usar para diagnóstico.\n\nPI-CAI pronto em {minutos:.1f} min — {resumo(res)}. "
           f"As sugestões entraram no PI-RADS do exame como lesões a conferir; a SEG está na série “{DESC_SEG}”.")
    avisos = [a for a in res.avisos if a != MARCA_PESQUISA]
    if avisos:
        msg += "\n\nConfira: " + "; ".join(avisos) + "."
    return msg


def frase(a: dict) -> str:
    n = AC.numeros_validos(a)
    p = (n.get("prob") or {}).get("v")
    d = (n.get("diam") or {}).get("v")
    from ipe.reporting.pirads import MARCA_PESQUISA
    txt = f"Foco sugerido em {a.get('local') or 'próstata'}"
    if d:
        txt += f", com {str(round(float(d))).replace('.', ',')} mm"
    if p is not None:
        txt += f" (probabilidade do modelo {float(p):.2f})".replace(".", ",")
    return txt + f" — {MARCA_PESQUISA}."
