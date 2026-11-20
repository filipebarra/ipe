"""0.100.79: volume da próstata pela IA (TotalSegmentator, `total_mr`, classe `prostate`) na RM — e, à parte, as zonas
(zona de transição / glândula central e zona periférica) por um **modelo de pesquisa** (MONAI `prostate_mri_anatomy`,
treinado no Prostate158), só quando ele foi instalado com a licença aceita e a opção está ligada.

Pedido dele (20/11/2026): *"Volume automático da glândula pelo TotalSegmentator, já com a densidade do PSA"* e
*"Zonas e detecção: só como modelo extra opcional de pesquisa, instalado à parte, com aviso na tela"*.

Roda no **T2 axial** do exame (escolhido pela descrição). Sai o volume (mL), as maiores extensões nos três eixos do
paciente (AP, transverso, craniocaudal), a SEG e um achado revisável; o volume entra no formulário PI-RADS do
exame (`reporting/pirads.py`), onde vale no lugar do elipsoide, se o médico não escolheu o elipsoide. As zonas saem
numa SEG à parte, marcada "PESQUISA — não usar para diagnóstico", com os volumes no achado.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import numpy as np

from ipe.ai import achados as AC

log = logging.getLogger(__name__)

FERRAMENTA = "prostata"
TITULO = "Volume da próstata (IA, TotalSegmentator)"
MARCA = "· TotalSegmentator"
DESC_SEG = f"Próstata {MARCA}"
DESC_ZONAS = "Zonas da próstata (PESQUISA - não diagnóstico)"
SERIE_SEG, SERIE_ZONAS = 983, 984
MIN_CORTES = 12
MODALIDADES = ("MR",)
MOTIVO_MODALIDADE = "O volume automático da próstata é feito na RM (T2 axial)."
MODELO = "TotalSegmentator total_mr (prostate)"
CHAVE_SAIDA = "prostata"
TIPO = "Próstata (volume)"

CHAVE_AUTO = "prostata.auto"
CHAVE_EXAME_CONTEM = "prostata.exame_contem"
CHAVE_MODALIDADES = "prostata.modalidades"
CHAVE_PRIOR_CT = "prostata.prioridade"
CHAVE_ESPESSURA = "prostata.espessura_max"
CHAVE_MIN_CORTES = "prostata.min_cortes"
CHAVE_DESTINOS = "prostata.destinos"
CHAVE_ZONAS = "prostata.zonas_pesquisa"          # rodar também o modelo de pesquisa das zonas (se instalado)
PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "PROSTAT|PROSTATE|PI-RADS|PIRADS|MULTIPARAM",
    CHAVE_MODALIDADES: ["MR"],
    CHAVE_PRIOR_CT: "T2 TSE TRA|T2_TSE_TRA|T2 TRA|TRA T2|T2 AX|AX T2|T2W TRA|T2 AXIAL|AXIAL T2|T2 FSE AX|T2",
    CHAVE_ESPESSURA: 5.0,
    CHAVE_MIN_CORTES: MIN_CORTES,
    CHAVE_DESTINOS: [],
    CHAVE_ZONAS: False,
}
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_CT, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES,
          "excluir": ("ADC", "DWI", "DIF", "TRACE", "PERF", "DCE", "DYN", "VIBE", "TWIST", "T1", "SAG", "COR",
                      "SCOUT", "LOCALIZER", "CALIBRA", "MIP", "SUB")}
CAIXAS = ((CHAVE_ZONAS, "Também separar as zonas (modelo de PESQUISA: MONAI/Prostate158, instalado à parte)",
           "Zona de transição e zona periférica pelo modelo MONAI prostate_mri_anatomy, treinado no Prostate158. "
           "É um modelo de pesquisa e ensino (não clínico, não comercial): só roda depois de instalado com a licença "
           "aceita, e as saídas saem marcadas 'não usar para diagnóstico'."),)
NOME_CADIA = "Próstata: volume (IA)"
TITULO_CADIA = "Volume da próstata na RM (TotalSegmentator), com a densidade do PSA no PI-RADS"
EXPLICACAO_CADIA = ("Na RM de próstata: segmenta a glândula no T2 axial e mede o volume e as extensões nos três eixos. "
                    "O volume vai para o formulário PI-RADS do exame (botão PI-RADS), onde dá a densidade do PSA. "
                    "Opcional: as zonas por um modelo de pesquisa instalado à parte.")
CHAVES = ("ml", "ap", "t", "cc", "tz_ml", "pz_ml")
COR, CORES_ZONAS = (120, 200, 200), {1: (240, 200, 80), 2: (90, 160, 240)}
NOMES_ZONAS = {1: "Zona de transição / glândula central (pesquisa)", 2: "Zona periférica (pesquisa)"}

_T2 = re.compile(r"(?<![A-Z0-9])T2")
_AX = re.compile(r"TRA|AX|AXIAL|TRANSV")
_FORA = ("ADC", "DWI", "DIF", "TRACE", "PERF", "DCE", "DYN", "SAG", "COR", "SCOUT", "LOCALIZER", "CALIBRA", "MIP",
         "STAR", "SUB", "T2*", "FLAIR")


def config(settings, chave):
    if chave == CHAVE_MODALIDADES:
        return ["MR"]
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


def e_t2_axial(descricao: str) -> bool:
    from ipe.ai.totalseg import _sem_acento
    d = _sem_acento(descricao or "")
    return bool(_T2.search(d)) and bool(_AX.search(d)) and not any(x in d for x in _FORA)


def escolher_serie(repo, study_uid: str, settings=None):
    """O T2 axial (o de mais cortes); sem a palavra "axial", o T2 que não é sagital nem coronal."""
    from ipe.ai.totalseg import _sem_acento
    mr = [s for s in repo.series_for_study(study_uid) if (s.modality or "").upper() == "MR"
          and (s.num_images or 0) >= MIN_CORTES and MARCA not in (s.description or "")]
    ax = [s for s in mr if e_t2_axial(s.description or "")]
    if not ax:
        ax = [s for s in mr if _T2.search(_sem_acento(s.description or "")) and
              not any(x in _sem_acento(s.description or "") for x in _FORA)]
    if not ax:
        return None, "não achei o T2 axial neste exame"
    return max(ax, key=lambda s: s.num_images or 0).series_uid, ""


def ja_feita(repo, study_uid: str) -> bool:
    return bool(repo.achados(study_uid, FERRAMENTA))


def zonas_prontas(settings=None) -> bool:
    from ipe.ai import extras as EX
    return EX.prontidao("prostata_zonas", settings).pronto and EX.licenca_aceita(settings, "prostata_zonas")


def tarefas(modalidade: str = "MR", settings=None) -> list[dict]:
    out = [{"nome": "total_mr", "roi": ["prostate"], "rotulo": "próstata (TotalSegmentator)", "prostata": True}]
    if bool(config(settings, CHAVE_ZONAS)) and zonas_prontas(settings):
        out.append({"nome": "prostata_zonas", "rotulo": "zonas da próstata (modelo de pesquisa)"})
    return out


# ------------------------------------------------------------------ a conta
@dataclass
class Resultado:
    ml: float | None = None
    extensoes: list = field(default_factory=list)      # [AP, transverso, craniocaudal] (mm)
    mascara: np.ndarray | None = None
    offset: tuple = (0, 0, 0)
    centro: list | None = None
    zonas: np.ndarray | None = None                    # recorte do mesmo tamanho: 1 TZ/CG, 2 PZ
    zonas_ml: dict = field(default_factory=dict)
    avisos: list = field(default_factory=list)
    elegibilidade: str = ""
    versao: str = ""
    series_uid: str = ""
    calculado: bool = False


def extensoes_mm(vol, mascara: np.ndarray, offset=(0, 0, 0)) -> list[float]:
    """As maiores extensões da máscara nos eixos do paciente: AP (y), transverso (x) e craniocaudal (z), em mm."""
    kk, jj, ii = np.nonzero(mascara)
    if not kk.size:
        return []
    idx = np.stack([ii + offset[2], jj + offset[1], kk + offset[0]], 1).astype(np.float64)
    pts = idx @ vol.matrix().T + vol.origin
    ext = pts.max(0) - pts.min(0)
    passo = np.abs(vol.matrix()).max(1)                   # meio voxel de cada lado
    x, y, z = (float(ext[i] + passo[i]) for i in range(3))
    return [round(y, 1), round(x, 1), round(z, 1)]


def calcular(t, rotulos: dict, settings=None) -> Resultado:
    vol = t.vol
    res = Resultado(versao=getattr(t, "versao", ""), series_uid=t.series_uid, calculado=True)
    desc = t.descricao_serie or t.series_uid[-8:]
    res.elegibilidade = f"RM, “{desc}”, {vol.data.shape[0]} cortes de {abs(vol.dz):.2f} mm"
    lab, classes = rotulos.get("total_mr", (None, {}))
    ids = [k for k, v in (classes or {}).items() if v == "prostate"]
    if lab is None or not ids:
        res.avisos.append("o TotalSegmentator não devolveu a próstata")
        return res
    m = np.isin(np.asarray(lab), ids)
    if not m.any():
        res.avisos.append("a próstata não foi achada nesta série")
        return res
    voxel_ml = float(vol.dx * vol.dy * abs(vol.dz)) / 1000.0
    res.ml = round(float(m.sum()) * voxel_ml, 1)
    kk, jj, ii = np.nonzero(m)
    a, b, c = int(kk.min()), int(jj.min()), int(ii.min())
    res.mascara = m[a:kk.max() + 1, b:jj.max() + 1, c:ii.max() + 1].copy()
    res.offset = (a, b, c)
    res.extensoes = extensoes_mm(vol, res.mascara, res.offset)
    res.centro = [float(x) for x in vol.voxel_to_patient(ii.mean(), jj.mean(), kk.mean())]
    if abs(vol.dz) > 4.5:
        res.avisos.append(f"cortes de {abs(vol.dz):.1f} mm: o volume fica menos preciso")
    if res.ml < 10 or res.ml > 300:
        res.avisos.append(f"volume fora do comum ({res.ml:.0f} mL): confira a segmentação")
    zl = rotulos.get("prostata_zonas", (None, {}))[0]
    if zl is not None:
        z = np.asarray(zl)[a:kk.max() + 1, b:jj.max() + 1, c:ii.max() + 1]
        if (z > 0).any():
            res.zonas = np.where(z > 0, z, 0).astype(np.uint8)
            res.zonas_ml = {"tz": round(float((z == 1).sum()) * voxel_ml, 1),
                            "pz": round(float((z == 2).sum()) * voxel_ml, 1)}
            res.avisos.append("zonas por " + _marca_pesquisa())
    return res


def _marca_pesquisa() -> str:
    from ipe.reporting.pirads import MARCA_PESQUISA
    return MARCA_PESQUISA


def _n(v, u, n, casas=1):
    return AC.numero(None if v is None else round(float(v), casas), u, n)


def itens_para_o_banco(res: Resultado, t, versao: str) -> list[dict]:
    if not res.calculado or not res.ml:
        return []
    e = res.extensoes or [None, None, None]
    nums = {"ml": _n(res.ml, "mL", "Volume da próstata"), "ap": _n(e[0], "mm", "Extensão AP"),
            "t": _n(e[1], "mm", "Extensão transversa"), "cc": _n(e[2], "mm", "Extensão craniocaudal")}
    if res.zonas_ml:
        nums["tz_ml"] = _n(res.zonas_ml.get("tz"), "mL", "Zona de transição (pesquisa)")
        nums["pz_ml"] = _n(res.zonas_ml.get("pz"), "mL", "Zona periférica (pesquisa)")
    return [{"series_uid": t.series_uid, "modelo": MODELO + (" + MONAI prostate_mri_anatomy (pesquisa)"
                                                             if res.zonas_ml else ""),
             "versao": versao or res.versao, "rotulo": "P", "tipo": TIPO, "local": "próstata",
             "posicao": res.centro, "numeros": nums,
             "elegibilidade": res.elegibilidade + (". Atenção: " + "; ".join(res.avisos) if res.avisos else "")}]


def _seg(t, segs, descricao, numero, algoritmo, db, storage_root) -> dict:
    import shutil
    import tempfile
    from pathlib import Path

    from ipe.ai.totalseg_saida import _caminho_do_sop
    from ipe.imaging.seg_writer import build_seg
    from ipe.importer.scanner import Importer
    vol = t.vol
    ds = build_seg(vol, segs, vol.source_path, frames=t.frames, series_number=numero, description=descricao,
                   algoritmo=("AUTOMATIC", algoritmo))
    tmp = Path(tempfile.mkdtemp(prefix="dv_prostata_"))
    try:
        ds.save_as(tmp / "seg.dcm", enforce_file_format=True)
        r = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([tmp])
        sop = str(ds.SOPInstanceUID)
        return {"series": sorted(getattr(r, "new_series", None) or []), "sop": sop,
                "path": _caminho_do_sop(db, t.study_uid, sop, descricao)}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def gravar(t, res: Resultado, versao: str, db, storage_root, repo=None, settings=None) -> dict:
    from pathlib import Path
    from types import SimpleNamespace

    from ipe.db.repository import Repository
    repo = repo or Repository(db)
    for se in repo.series_for_study(t.study_uid):
        if (se.description or "") in (DESC_SEG, DESC_ZONAS):
            try:
                repo.delete_series(se.series_uid, Path(storage_root))
            except Exception:  # noqa: BLE001
                log.exception("trocar a SEG da próstata anterior")
    out = {"series": [], "ferramenta": FERRAMENTA}
    if res.mascara is not None and res.mascara.any():
        s = _seg(t, [(SimpleNamespace(mask=res.mascara, offset=res.offset), "Próstata", COR)], DESC_SEG, SERIE_SEG,
                 f"TotalSegmentator {versao}".strip(), db, storage_root)
        out["series"] += s["series"]
        out["seg_sop"], out["seg_path"] = s["sop"], s["path"]
    if res.zonas is not None:
        segs = [(SimpleNamespace(mask=res.zonas == k, offset=res.offset), NOMES_ZONAS[k], CORES_ZONAS[k])
                for k in (1, 2) if (res.zonas == k).any()]
        if segs:
            s = _seg(t, segs, DESC_ZONAS, SERIE_ZONAS, "MONAI prostate_mri_anatomy (PESQUISA - nao usar para "
                                                         "diagnostico)", db, storage_root)
            out["series"] += s["series"]
    out["achados"] = repo.gravar_achados(t.study_uid, FERRAMENTA, itens_para_o_banco(res, t, versao))
    if res.ml:
        try:
            from ipe.reporting import pirads as P
            P.aplicar_volume_auto(repo, t.study_uid, res.ml, res.extensoes, "TotalSegmentator",
                                  series_uid=t.series_uid)
        except Exception:  # noqa: BLE001
            log.exception("próstata: o volume no PI-RADS")
    return out


def _f(v, casas=1) -> str:
    return "—" if v is None else f"{float(v):.{casas}f}".replace(".", ",")


def resumo(res: Resultado) -> str:
    if not res.ml:
        return res.avisos[0] if res.avisos else "próstata não achada"
    txt = f"próstata {_f(res.ml)} mL"
    if res.extensoes:
        txt += f" ({_f(res.extensoes[0], 0)} × {_f(res.extensoes[1], 0)} × {_f(res.extensoes[2], 0)} mm)"
    if res.zonas_ml:
        txt += f"; zonas (pesquisa): transição {_f(res.zonas_ml.get('tz'))} mL, periférica {_f(res.zonas_ml.get('pz'))} mL"
    return txt


def n_itens(res: Resultado) -> int:
    return int(bool(res.ml))


def mensagem(res: Resultado, minutos: float) -> str:
    msg = (f"Próstata pronta em {minutos:.1f} min — {resumo(res)}. O volume entrou no formulário PI-RADS do exame "
           f"(com a densidade do PSA, se o PSA estiver preenchido); a máscara está na série “{DESC_SEG}”.")
    avisos = [a for a in res.avisos if not a.startswith("zonas por")]
    if res.zonas_ml:
        msg += f"\n\nAs zonas vieram de um {_marca_pesquisa()} (série “{DESC_ZONAS}”)."
    if avisos:
        msg += "\n\nConfira: " + "; ".join(avisos) + "."
    return msg


def frase(a: dict) -> str:
    n = AC.numeros_validos(a)

    def v(k, casas=1):
        x = (n.get(k) or {}).get("v")
        return None if x is None else _f(x, casas)
    if not v("ml"):
        return ""
    txt = f"Próstata com volume de {v('ml')} mL pela segmentação automática"
    if v("ap", 0):
        txt += f" (extensões {v('ap', 0)} × {v('t', 0)} × {v('cc', 0)} mm)"
    return txt + "."
