"""Glioma na RM: parte captante, necrose e edema pela IA (BraTS) (0.99.83; item 4 da lista do MedMLX).

O modelo é o SegResNet do MONAI (model zoo `brats_mri_segmentation`, treinado no BraTS 2018; Myronenko
2018), em CPU. Entram as quatro sequências do protocolo de glioma, **alinhadas e sem o crânio**, como no
treino:

- a **T1 pós-contraste** é a referência (a série do quadro); a T1 sem contraste, a T2 e a FLAIR do mesmo exame
  são achadas pela descrição e **registradas** nela (registro rígido do Ipê, informação mútua);
- o crânio sai com a máscara do encéfalo do TotalSegmentator (`total_mr`, classe `brain`), na mesma rodada.

Sai a parte **captante** (ET), a **necrose** / parte não captante (NCR) e o **edema** / hipersinal em FLAIR (ED),
com os volumes de cada uma, do núcleo tumoral (TC = ET + NCR) e do total (WT), e o maior diâmetro axial da
parte captante. Um achado revisável; a SEG tem as três partes.

Modelo de exemplo do MONAI ("not to be used for diagnostic purposes"): conferir, e lembrar que o registro
entre as sequências precisa estar bom — a revisão avisa quando a semelhança ficou baixa.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import numpy as np

from ipe.ai import achados as AC

log = logging.getLogger(__name__)

FERRAMENTA = "brats"
TITULO = "Glioma na RM: captante, necrose e edema (IA, BraTS)"
MARCA = "· BraTS"
DESC_SEG = f"Glioma (BraTS) {MARCA}"
SERIE_SEG = 986
MIN_CORTES = 20
MODALIDADES = ("MR",)
MOTIVO_MODALIDADE = "O BraTS roda na RM de crânio (T1 pós, T1, T2 e FLAIR)."
MODELO = "MONAI brats_mri_segmentation (SegResNet)"
MODELO_EXTRA = "brats"
CHAVE_SAIDA = "brats"
TIPO = "Glioma (BraTS)"
CORES = {3: (255, 70, 70), 1: (250, 220, 60), 2: (80, 200, 120)}
NOMES = {3: "Captante (ET)", 1: "Necrose / não captante (NCR)", 2: "Edema (ED)"}

CHAVE_AUTO = "brats.auto"
CHAVE_EXAME_CONTEM = "brats.exame_contem"
CHAVE_MODALIDADES = "brats.modalidades"
CHAVE_PRIOR_CT = "brats.prioridade"
CHAVE_ESPESSURA = "brats.espessura_max"
CHAVE_MIN_CORTES = "brats.min_cortes"
CHAVE_DESTINOS = "brats.destinos"
PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "CRANIO|CRÂNIO|ENCEFALO|ENCÉFALO|BRAIN|HEAD|GLIOMA|TUMOR|NEURO",
    CHAVE_MODALIDADES: ["MR"],
    CHAVE_PRIOR_CT: "T1 POS|T1 PÓS|T1 GD|T1+C|T1 C+|MPRAGE|3D T1|T1 3D|POS|PÓS|GD|POST",
    CHAVE_ESPESSURA: 6.0,
    CHAVE_MIN_CORTES: MIN_CORTES,
    CHAVE_DESTINOS: [],
}
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_CT, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES,
          "excluir": ("ADC", "DWI", "DIF", "SWI", "PERF", "DSC", "ASL", "TOF", "MIP", "SCOUT", "LOCALIZER")}
NOME_CADIA = "Glioma (BraTS)"
TITULO_CADIA = "Glioma na RM: volumes da parte captante, necrose e edema (MONAI BraTS SegResNet)"
EXPLICACAO_CADIA = ("Na RM de crânio com T1 pós-contraste, T1, T2 e FLAIR: alinha as quatro sequências, tira o "
                    "crânio e separa a parte captante, a necrose e o edema do tumor, com os volumes e o maior diâmetro "
                    "da parte captante. Precisa dos modelos extras instalados. O resultado aparece em Aplicações ▸ "
                    "Achados de IA, para conferir.")
CHAVES = ("et_ml", "tc_ml", "wt_ml", "ncr_ml", "ed_ml", "diam_et")

_POS = re.compile(r"(POS|PÓS|POST|GD|GADO|C\+|\+C|CONTRAST|CE\b|MPRAGE.*(GD|POS))")
_T1 = re.compile(r"(?<![A-Z])T1|MPRAGE|SPGR|BRAVO|VIBE|FSPGR|TFE")
_T2 = re.compile(r"(?<![A-Z])T2")
_FLAIR = re.compile(r"FLAIR|TIRM|DARK.?FLUID")
_FORA = ("T2*", "T2 *", "STAR", "GRE", "SWI", "SWAN", "ADC", "DWI", "DIF", "PERF", "DSC", "ASL", "TOF", "MIP",
         "SCOUT", "LOCALIZER", "CALIBRA")


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


def tipo_da_serie(desc: str) -> str:
    """'t1c', 't1', 't2', 'flair' ou '' pela descrição."""
    from ipe.ai.totalseg import _sem_acento
    d = _sem_acento(desc or "")
    if any(x in d for x in _FORA):
        return ""
    if _FLAIR.search(d):
        return "flair"
    if _T1.search(d):
        return "t1c" if _POS.search(d) else "t1"
    if _T2.search(d):
        return "t2"
    return ""


def series_do_exame(repo, study_uid: str) -> dict:
    """{tipo: SeriesRow} — de cada tipo, a de mais imagens."""
    out = {}
    for s in repo.series_for_study(study_uid):
        if (s.modality or "").upper() != "MR" or (s.num_images or 0) < MIN_CORTES:
            continue
        tp = tipo_da_serie(s.description or "")
        if tp and (tp not in out or (s.num_images or 0) > (out[tp].num_images or 0)):
            out[tp] = s
    return out


def escolher_serie(repo, study_uid: str, settings=None):
    s = series_do_exame(repo, study_uid)
    if "t1c" not in s:
        return None, "não achei a T1 pós-contraste neste exame"
    falta = [n for n in ("t1", "t2", "flair") if n not in s]
    if falta:
        return None, "faltam as sequências: " + ", ".join(x.upper() for x in falta)
    return s["t1c"].series_uid, ""


def ja_feita(repo, study_uid: str) -> bool:
    from ipe.ai import totalseg as TS
    return TS.ja_segmentado(repo, study_uid, DESC_SEG)


def tarefas(modalidade: str = "MR", settings=None) -> list[dict]:
    return [{"nome": "total_mr", "roi": ["brain"], "rotulo": "encéfalo (tirar o crânio)"},
            {"nome": "brats", "rotulo": "glioma (BraTS)"}]


def canais_extras(t) -> dict:
    """T1, T2 e FLAIR registradas na T1 pós (a série do trabalho)."""
    from ipe.ai import extras as EX
    from ipe.ai.totalseg import Falhou
    from ipe.imaging import registro_rigido as RR
    from ipe.imaging.series import build_frames
    from ipe.imaging.volume import build_volume
    series = series_do_exame(t.repo, t.study_uid)
    falta = [n.upper() for n in ("t1", "t2", "flair") if n not in series]
    if falta:
        raise Falhou("O BraTS precisa da T1 pós, T1, T2 e FLAIR; faltam neste exame: " + ", ".join(falta) + ".")
    out, qualidade = {}, {}
    for nome in ("t1", "t2", "flair"):
        se = series[nome]
        v = build_volume(build_frames(t.repo.instances_for_series(se.series_uid), se.series_uid), t.cache)
        r = RR.registrar(t.vol, v, metrica="mi", tempo_max=90.0)
        qualidade[nome] = float(r.valor)
        out[nome] = EX.na_grade(t.vol, v, r.M, fora=0.0)
    t.brats_registro = qualidade
    return out


# ------------------------------------------------------------------ a conta
@dataclass
class Resultado:
    vols: dict = field(default_factory=dict)         # et, ncr, ed, tc, wt (mL)
    diam_et: float | None = None
    rotulos: np.ndarray | None = None                # recorte 1 = NCR, 2 = ED, 3 = ET
    offset: tuple = (0, 0, 0)
    centro: list | None = None
    registro: dict = field(default_factory=dict)
    avisos: list = field(default_factory=list)
    elegibilidade: str = ""
    versao: str = ""
    series_uid: str = ""
    calculado: bool = False


def calcular(t, rotulos: dict, settings=None) -> Resultado:
    from ipe.ai.figado_lesoes import _maior_diametro_axial
    vol = t.vol
    res = Resultado(versao=getattr(t, "versao", ""), series_uid=t.series_uid, calculado=True,
                    registro=dict(getattr(t, "brats_registro", {}) or {}))
    lab = rotulos.get("brats", (None, {}))[0]
    desc = t.descricao_serie or t.series_uid[-8:]
    res.elegibilidade = (f"RM, T1 pós “{desc}”, {vol.data.shape[0]} cortes de {abs(vol.dz):.2f} mm; T1, T2 e FLAIR "
                         f"registradas nela")
    if lab is None:
        res.avisos.append("o modelo não devolveu a máscara")
        return res
    lab = np.asarray(lab)
    voxel_ml = float(vol.dx * vol.dy * abs(vol.dz)) / 1000.0
    et, ncr, ed = lab == 3, lab == 1, lab == 2
    res.vols = {"et": float(et.sum() * voxel_ml), "ncr": float(ncr.sum() * voxel_ml), "ed": float(ed.sum() * voxel_ml)}
    res.vols["tc"] = res.vols["et"] + res.vols["ncr"]
    res.vols["wt"] = res.vols["tc"] + res.vols["ed"]
    if et.any():
        kk, jj, ii = np.nonzero(et)
        res.diam_et = _maior_diametro_axial(et[kk.min():kk.max() + 1, jj.min():jj.max() + 1, ii.min():ii.max() + 1],
                                            vol.dx, vol.dy)
    tudo = lab > 0
    if tudo.any():
        kk, jj, ii = np.nonzero(tudo)
        a, b, c = kk.min(), jj.min(), ii.min()
        res.rotulos = lab[a:kk.max() + 1, b:jj.max() + 1, c:ii.max() + 1].copy()
        res.offset = (int(a), int(b), int(c))
        res.centro = [float(x) for x in vol.voxel_to_patient(ii.mean(), jj.mean(), kk.mean())]
    else:
        res.avisos.append("o modelo não achou tumor")
    baixos = [n.upper() for n, q in res.registro.items() if q < 1.1]
    if baixos:
        res.avisos.append("registro com semelhança baixa em " + ", ".join(baixos) + ": confira o alinhamento")
    res.avisos.append("modelo de exemplo do MONAI (BraTS 2018), não validado para diagnóstico: conferir cada parte")
    return res


def _n(v, u, n, casas=1):
    return AC.numero(None if v is None else round(float(v), casas), u, n)


def itens_para_o_banco(res: Resultado, t, versao: str) -> list[dict]:
    if not res.calculado or not res.vols:
        return []
    v = res.vols
    return [{"series_uid": t.series_uid, "modelo": MODELO, "versao": versao or res.versao, "rotulo": "G", "tipo": TIPO,
             "local": "encéfalo", "posicao": res.centro,
             "numeros": {"et_ml": _n(v["et"], "mL", "Captante (ET)", 2), "tc_ml": _n(v["tc"], "mL", "Núcleo (TC)", 2),
                         "wt_ml": _n(v["wt"], "mL", "Total (WT)", 2), "ncr_ml": _n(v["ncr"], "mL", "Necrose (NCR)", 2),
                         "ed_ml": _n(v["ed"], "mL", "Edema (ED)", 2),
                         "diam_et": _n(res.diam_et, "mm", "Maior diâmetro da parte captante", 0)},
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
                log.exception("trocar a SEG do BraTS anterior")
    out = {"series": [], "ferramenta": FERRAMENTA}
    if res.rotulos is not None and (res.rotulos > 0).any():
        vol = t.vol
        segs = [(SimpleNamespace(mask=res.rotulos == k, offset=res.offset), NOMES[k], CORES[k])
                for k in (3, 1, 2) if (res.rotulos == k).any()]
        ds = build_seg(vol, segs, vol.source_path, frames=t.frames, series_number=SERIE_SEG, description=DESC_SEG,
                       algoritmo=("AUTOMATIC", f"MONAI BraTS SegResNet {versao}".strip()))
        tmp = Path(tempfile.mkdtemp(prefix="dv_brats_"))
        try:
            ds.save_as(tmp / "seg.dcm", enforce_file_format=True)
            r = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([tmp])
            out["series"] += sorted(getattr(r, "new_series", None) or [])
            out["seg_sop"] = str(ds.SOPInstanceUID)
            out["seg_path"] = _caminho_do_sop(db, t.study_uid, out["seg_sop"], DESC_SEG)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    out["achados"] = repo.gravar_achados(t.study_uid, FERRAMENTA, itens_para_o_banco(res, t, versao))
    return out


def _f(v, casas=1) -> str:
    return "—" if v is None else f"{float(v):.{casas}f}".replace(".", ",")


def resumo(res: Resultado) -> str:
    if not res.vols or not res.vols.get("wt"):
        return res.avisos[0] if res.avisos else "nada achado"
    v = res.vols
    return f"captante {_f(v['et'])} mL, necrose {_f(v['ncr'])} mL, edema {_f(v['ed'])} mL (total {_f(v['wt'])} mL)"


def n_itens(res: Resultado) -> int:
    return int(bool(res.vols))


def mensagem(res: Resultado, minutos: float) -> str:
    msg = (f"BraTS pronto em {minutos:.1f} min — {resumo(res)}. O achado está em Aplicações ▸ Achados de IA, para "
           f"conferir; as partes do tumor estão na série “{DESC_SEG}”.")
    avisos = [a for a in res.avisos if not a.startswith("modelo de exemplo")]
    if avisos:
        msg += "\n\nConfira: " + "; ".join(avisos) + "."
    return msg


def frase(a: dict) -> str:
    n = AC.numeros_validos(a)

    def v(k, casas=1):
        x = (n.get(k) or {}).get("v")
        return None if x is None else _f(x, casas)
    if not v("wt_ml"):
        return "Sem lesão tumoral identificada pela segmentação automática (BraTS)."
    txt = (f"Lesão expansiva com componente captante de {v('et_ml')} mL, componente necrótico / não captante de "
           f"{v('ncr_ml')} mL e hipersinal em FLAIR perilesional de {v('ed_ml')} mL (volume total {v('wt_ml')} mL)")
    if v("diam_et", 0):
        txt += f"; maior diâmetro axial da parte captante de {v('diam_et', 0)} mm"
    return txt + "."
