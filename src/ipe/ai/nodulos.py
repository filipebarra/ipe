"""Nódulos pulmonares na TC (0.99.46) — a primeira IA de achados revisáveis.

Modelo: a tarefa **`lung_nodules`** do TotalSegmentator (≥ 2.10; pesos abertos, sem licença paga),
treinada pela BLUEMIND AI em 1353 TCs, parte do LIDC-IDRI. Ela devolve **máscaras** (o pulmão e os
nódulos), não caixas: dá para medir volume, eixos e densidade de cada candidato. Os lobos saem da
tarefa `total` no modo rápido (`lung_*_lobe_*`).

Cada componente conexo da máscara de nódulos vira um **achado sugerido** (`ai/achados.py`):

| número | conta |
|---|---|
| volume | voxels × volume do voxel (mm³) |
| diâmetro maior e eixos | os três eixos perpendiculares (`segment.tres_eixos`) |
| diâmetro médio | média dos dois maiores eixos — o "average diameter" do Fleischner (2017) e do Lung-RADS |
| diâmetro equivalente | da esfera de mesmo volume, (6V/π)^⅓ |
| HU médio e parte sólida | média do HU; voxels ≥ −300 HU como "parte sólida" |
| consistência | proposta pela fração sólida: ≥ 80% sólido, ≤ 20% vidro fosco, no meio parcialmente sólido |
| lobo | o lobo do centro (ou o mais perto, até 10 mm) |

A consistência pelo HU é **proposta**: em nódulo de poucos milímetros o volume parcial baixa o HU e
um nódulo sólido pode parecer vidro fosco. Por isso fica marcada como "pelo HU".

Filtros: diâmetro equivalente ≥ `nodulos.diametro_min` (3 mm de fábrica); no máximo 30 candidatos
(os maiores). Elegibilidade: TC, e o aviso quando o corte passa de 2,5 mm (o Fleischner pede cortes
finos, ≤ 1,5 mm, para nódulos pequenos).

Saída: SEG "Nódulos pulmonares · TotalSegmentator" (série 981), um segmento por candidato, e os
achados no banco. Nada vai ao laudo sem revisão.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field

import numpy as np

from ipe.ai import achados as AC

log = logging.getLogger(__name__)

FERRAMENTA = "nodulos"
TITULO = "Nódulos pulmonares (IA)"
MARCA = "· TotalSegmentator"
DESC_SEG = f"Nódulos pulmonares {MARCA}"
SERIE_SEG = 981
MIN_CORTES = 40
MODALIDADES = ("CT",)
MOTIVO_MODALIDADE = "A detecção de nódulos pulmonares é feita na TC."
MODELO = "TotalSegmentator lung_nodules"
CHAVE_SAIDA = "nodulos"
TIPO = "Nódulo pulmonar"
MAX_CANDIDATOS = 30
LIMIAR_SOLIDO = -300.0             # HU: daqui para cima é parte sólida
COR = (255, 210, 60)

LOBOS = {"lung_upper_lobe_right": "lobo superior direito", "lung_middle_lobe_right": "lobo médio",
         "lung_lower_lobe_right": "lobo inferior direito", "lung_upper_lobe_left": "lobo superior esquerdo",
         "lung_lower_lobe_left": "lobo inferior esquerdo"}
SIGLA = {"lung_upper_lobe_right": "LSD", "lung_middle_lobe_right": "LM", "lung_lower_lobe_right": "LID",
         "lung_upper_lobe_left": "LSE", "lung_lower_lobe_left": "LIE"}

# Configurações ▸ CAD/IA ▸ Nódulos pulmonares
CHAVE_AUTO = "nodulos.auto"
CHAVE_EXAME_CONTEM = "nodulos.exame_contem"
CHAVE_MODALIDADES = "nodulos.modalidades"
CHAVE_PRIOR_CT = "nodulos.prioridade_ct"
CHAVE_ESPESSURA = "nodulos.espessura_max"
CHAVE_MIN_CORTES = "nodulos.min_cortes"
CHAVE_DESTINOS = "nodulos.destinos"
CHAVE_DIAMETRO_MIN = "nodulos.diametro_min"
PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "TORAX|TORACICA|CHEST|PULMAO|PULMONAR|LUNG|TCAR|ALTA RESOLUCAO|NODULO|RASTREAMENTO",
    CHAVE_MODALIDADES: ["CT"],
    CHAVE_PRIOR_CT: "PULMAO|PULMONAR|LUNG|PARENQUIMA|ALTA RESOLUCAO|HR|THIN|FINO|1MM|1.25|0.625|AX|AXIAL",
    CHAVE_ESPESSURA: 3.0,
    CHAVE_MIN_CORTES: MIN_CORTES,
    CHAVE_DESTINOS: [],
    CHAVE_DIAMETRO_MIN: 3.0,
}
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_CT, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES}

# Configurações ▸ CAD/IA
NOME_CADIA = "Nódulos pulmonares"
TITULO_CADIA = "Nódulos pulmonares na TC — candidatos revisáveis (TotalSegmentator lung_nodules)"
EXPLICACAO_CADIA = ("Na TC de tórax: cada candidato a nódulo vira um achado sugerido, com lobo, diâmetro maior e "
                    "médio, volume, HU médio e parte sólida. Revise em Aplicações ▸ Achados de IA: confirme, "
                    "corrija ou descarte; só o confirmado vai ao laudo. Usa a mesma instalação da segmentação.")
OPCOES = ((CHAVE_DIAMETRO_MIN, "Diâmetro mínimo do candidato:", 0.0, 30.0, " mm",
           "Candidatos menores que isto (diâmetro da esfera de mesmo volume) não entram na lista."),)

#: a ordem dos números na tabela e no laudo
CHAVES = ("diametro_mm", "medio_mm", "volume_mm3", "consistencia", "hu_medio", "solido_mm3", "eixos_mm",
          "equivalente_mm")


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
    return [
        {"nome": "lung_nodules", "rotulo": "nódulos pulmonares", "nodulos": True},
        {"nome": "total", "roi": list(LOBOS), "fast": True, "rotulo": "lobos pulmonares", "nodulos": True},
    ]


# ------------------------------------------------------------------ a conta
@dataclass(eq=False)
class Candidato:
    rotulo: str
    centro: list                    # mm, paciente
    voxels: int
    numeros: dict
    lobo: str = ""
    mascara: np.ndarray | None = field(default=None, repr=False)     # recorte bool (k, j, i)
    offset: tuple = (0, 0, 0)


@dataclass
class Resultado:
    candidatos: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    elegibilidade: str = ""
    versao: str = ""
    series_uid: str = ""
    descartados_pequenos: int = 0


def _espessura(t) -> float | None:
    try:
        import pydicom
        ds = pydicom.dcmread(t.frames[0].path, stop_before_pixels=True, force=True,
                             specific_tags=["SliceThickness"])
        v = ds.get("SliceThickness")
        return float(v) if v not in (None, "") else None
    except Exception:  # noqa: BLE001
        return None


def elegibilidade(t) -> tuple[str, list[str]]:
    """(por que a série serviu, avisos)."""
    vol = t.vol
    esp = _espessura(t)
    passo = float(vol.dz)
    txt = (f"TC, série “{t.descricao_serie or t.series_uid[-8:]}”, {vol.data.shape[0]} cortes, "
           f"pixel {vol.dy:.2f} × {vol.dx:.2f} mm, intervalo {passo:.2f} mm"
           + (f", espessura {esp:.2f} mm" if esp else ""))
    avisos = []
    grosso = max(esp or 0.0, passo)
    if grosso > 2.5:
        avisos.append(f"cortes de {grosso:.1f} mm: nódulos pequenos podem não aparecer e o volume sai menos "
                      "preciso (o Fleischner pede cortes de até 1,5 mm)")
    return txt, avisos


def _consistencia(frac_solida: float) -> str:
    if frac_solida >= 0.8:
        return "sólido"
    if frac_solida <= 0.2:
        return "vidro fosco"
    return "parcialmente sólido"


def calcular(t, rotulos: dict, settings=None) -> Resultado:
    from ipe.ai import cefalometria as CF
    from ipe.imaging import estruturas as E
    from ipe.imaging.segment import tres_eixos
    vol = t.vol
    ms = CF.Mascaras(vol, rotulos)
    res = Resultado(versao=getattr(t, "versao", ""), series_uid=t.series_uid)
    res.elegibilidade, res.avisos = elegibilidade(t)
    nod = ms.get("lung_nodules")
    if nod is None:
        return res
    vox = float(vol.dx * vol.dy * vol.dz)
    voxel_mm = (vol.dx, vol.dy, vol.dz)
    lobos = {nome: ms.get(nome) for nome in LOBOS}
    lobos = {k: v for k, v in lobos.items() if v is not None}
    dmin = float(config(settings, CHAVE_DIAMETRO_MIN) or 0)
    fat, off = CF._recorte(nod, 1)
    rot, n = E.rotular(nod[fat])
    cands = []
    for c in range(1, n + 1):
        m = rot == c
        nv = int(m.sum())
        vol_mm3 = nv * vox
        eq = (6 * vol_mm3 / math.pi) ** (1 / 3)
        if eq < dmin:
            res.descartados_pequenos += 1
            continue
        pts = CF.pontos(vol, m, off)
        eixos = tres_eixos(pts, voxel_mm) if len(pts) > 1 else (eq, eq, eq)
        hu = np.asarray(vol.data[fat][m], float)
        solido = float((hu >= LIMIAR_SOLIDO).mean()) if len(hu) else 0.0
        centro = pts.mean(axis=0)
        k, j, i = (np.argwhere(m).mean(axis=0) + np.asarray(off)).round().astype(int)
        lobo = ""
        for nome, mk in lobos.items():
            if 0 <= k < mk.shape[0] and 0 <= j < mk.shape[1] and 0 <= i < mk.shape[2] and mk[k, j, i]:
                lobo = nome
                break
        if not lobo and lobos:                       # na borda (justapleural): o lobo mais perto, até 10 mm
            melhor = (1e9, "")
            for nome, mk in lobos.items():
                r = max(1, int(round(10 / max(vol.dx, 1e-3))))
                rz = max(1, int(round(10 / max(vol.dz, 1e-3))))
                sub = mk[max(0, k - rz):k + rz + 1, max(0, j - r):j + r + 1, max(0, i - r):i + r + 1]
                if sub.any():
                    q = CF.pontos(vol, sub, (max(0, k - rz), max(0, j - r), max(0, i - r)))
                    d = float(np.min(np.linalg.norm(q - centro, axis=1)))
                    if d < melhor[0]:
                        melhor = (d, nome)
            if melhor[0] <= 10.0:
                lobo = melhor[1]
        nums = {
            "diametro_mm": AC.numero(round(float(eixos[0]), 1), "mm", "Diâmetro maior"),
            "medio_mm": AC.numero(round(float((eixos[0] + eixos[1]) / 2), 1), "mm", "Diâmetro médio"),
            "volume_mm3": AC.numero(round(vol_mm3, 0), "mm³", "Volume"),
            "consistencia": AC.numero(_consistencia(solido), "", "Consistência (pelo HU)"),
            "hu_medio": AC.numero(round(float(hu.mean()), 0) if len(hu) else None, "HU", "HU médio"),
            "solido_mm3": AC.numero(round(solido * vol_mm3, 0), "mm³", "Parte sólida"),
            "eixos_mm": AC.numero([round(float(x), 1) for x in eixos], "mm", "Eixos"),
            "equivalente_mm": AC.numero(round(eq, 1), "mm", "Diâmetro equivalente"),
        }
        cands.append(Candidato("", [float(x) for x in centro], nv, nums, lobo, m, off))
    cands.sort(key=lambda c: -c.voxels)
    if len(cands) > MAX_CANDIDATOS:
        res.avisos.append(f"{len(cands)} candidatos: ficaram os {MAX_CANDIDATOS} maiores")
        cands = cands[:MAX_CANDIDATOS]
    for n_, c in enumerate(cands, 1):
        c.rotulo = f"N{n_}"
    res.candidatos = cands
    return res


def itens_para_o_banco(res: Resultado, t, versao: str) -> list[dict]:
    texto = res.elegibilidade + (". Atenção: " + "; ".join(res.avisos) if res.avisos else "")
    return [{"series_uid": t.series_uid, "rotulo": c.rotulo, "tipo": TIPO, "local": LOBOS.get(c.lobo, ""),
             "posicao": c.centro, "numeros": c.numeros, "modelo": MODELO, "versao": versao or res.versao,
             "elegibilidade": texto, "segmento": k}
            for k, c in enumerate(res.candidatos, 1)]


def gravar(t, res: Resultado, versao: str, db, storage_root, repo=None, settings=None) -> dict:
    """SEG com um segmento por candidato (série 981) e os achados sugeridos no banco."""
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
                log.exception("trocar a SEG de nódulos anterior")
    out = {"series": [], "ferramenta": FERRAMENTA}
    # 0.99.46: o que o médico já revisou não volta como sugestão (nem com outro rótulo)
    revisados = [a for a in repo.achados(t.study_uid, FERRAMENTA) if a["estado"] != "sugerido"]
    novos, res.candidatos = AC.conciliar(res.candidatos, revisados)
    if res.candidatos:
        segs = [(SimpleNamespace(mask=c.mascara, offset=c.offset),
                 f"{c.rotulo} {SIGLA.get(c.lobo, '')} {c.numeros['diametro_mm']['v']:.0f} mm".replace("  ", " "), COR)
                for c in res.candidatos]
        vol = t.vol
        ds = build_seg(vol, segs, vol.source_path, frames=t.frames, series_number=SERIE_SEG, description=DESC_SEG,
                       algoritmo=("AUTOMATIC", f"TotalSegmentator {versao} lung_nodules".strip()))
        tmp = Path(tempfile.mkdtemp(prefix="dv_nod_"))
        try:
            ds.save_as(tmp / "seg.dcm", enforce_file_format=True)
            r = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([tmp])
            out["series"] += sorted(getattr(r, "new_series", None) or [])
            out["seg_sop"] = str(ds.SOPInstanceUID)
            out["seg_path"] = _caminho_do_sop(db, t.study_uid, out["seg_sop"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    sao_novos = {id(c) for c in novos}
    itens = [it for it, c in zip(itens_para_o_banco(res, t, versao), res.candidatos) if id(c) in sao_novos]
    out["achados"] = repo.gravar_achados(t.study_uid, FERRAMENTA, itens)
    out["ja_revisados"] = len(res.candidatos) - len(novos)
    return out


def resumo(res: Resultado) -> str:
    n = len(res.candidatos)
    txt = "nenhum candidato a nódulo" if not n else f"{n} candidato(s) a nódulo"
    if res.descartados_pequenos:
        txt += f" (mais {res.descartados_pequenos} abaixo do diâmetro mínimo)"
    return txt


def n_itens(res: Resultado) -> int:
    return len(res.candidatos)


def mensagem(res: Resultado, minutos: float) -> str:
    msg = (f"Nódulos pulmonares prontos em {minutos:.1f} min: {resumo(res)}. Cada candidato está em "
           "Aplicações ▸ Achados de IA, como sugestão: confirme, corrija ou descarte um a um — só o que for "
           "confirmado vai ao laudo.")
    if res.avisos:
        msg += "\n\nConfira: " + "; ".join(res.avisos) + "."
    return msg


def frase(a: dict) -> str:
    """Uma linha do laudo para um achado confirmado ou corrigido."""
    nums = AC.numeros_validos(a)
    medio = nums.get("medio_mm", {}).get("v")
    vol = nums.get("volume_mm3", {}).get("v")
    cons = nums.get("consistencia", {}).get("v") or ""
    partes = [f"Nódulo {cons}".strip()]
    if a.get("local"):
        partes.append(f"no {a['local']}")
    medidas = []
    if medio is not None:
        medidas.append(f"diâmetro médio de {float(medio):.1f} mm".replace(".", ","))
    if vol is not None:
        medidas.append(f"volume de {float(vol):.0f} mm³")
    txt = " ".join(partes) + (", " + " e ".join(medidas) if medidas else "")
    return txt + f" ({a.get('rotulo', '')})."


def json_do_resultado(res: Resultado) -> str:
    return json.dumps({"n": len(res.candidatos), "avisos": res.avisos}, ensure_ascii=False)
