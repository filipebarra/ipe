"""Lesões no PET-FDG pela IA (autoPET): volume metabólico (MTV) e TLG automáticos (0.99.83; item 2 do MedMLX).

O modelo é o nnU-Net do **autoPET II** (DKFZ, Isensee et al. 2023, "Look Ma, no code"), que roda com o
nnU-Net comum (o mesmo que o TotalSegmentator usa), um fold só, em CPU. Entra o PET em **SUV** e a TC do
mesmo exame reamostrada na grade do PET (o mesmo Frame of Reference do PET/CT); sai a máscara das lesões
ávidas por FDG (o modelo aprendeu a deixar de fora o cérebro, o coração, a bexiga e os rins).

Sai, para o exame: número de lesões, **MTV** (volume metabólico total, mL), **TLG** (glicólise total: SUVmédio
× volume), SUVmáx; para cada lesão (até 20, as maiores pela TLG): volume, SUVmáx, SUVmédio, SUVpeak e TLG.
Cada lesão é um achado revisável (o captante fisiológico que escapar se descarta ali); o resumo vai ao laudo
e serve ao seguimento.

Precisa do PET com o fator de SUV (peso, dose, horários) e da TC do PET/CT. Pesos: instalar os modelos
extras (Configurações ▸ CAD/IA).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from ipe.ai import achados as AC

log = logging.getLogger(__name__)

FERRAMENTA = "autopet"
TITULO = "Lesões no PET-FDG: MTV e TLG (IA, autoPET)"
MARCA = "· autoPET"
DESC_SEG = f"Lesões FDG {MARCA}"
SERIE_SEG = 985
MIN_CORTES = 40
MODALIDADES = ("PT",)
MOTIVO_MODALIDADE = "O autoPET roda no PET (com a TC do PET/CT no mesmo exame)."
MODELO = "nnU-Net autoPET II (DKFZ)"
MODELO_EXTRA = "autopet"
CHAVE_SAIDA = "autopet"
TIPO_RESUMO = "Carga tumoral FDG (MTV/TLG)"
TIPO_LESAO = "Lesão FDG"
MIN_ML = 0.2               # ilhas menores que ~2 voxels do PET ficam de fora
MAX_ACHADOS = 20
_FORA_CT = ("TOPO", "SCOUT", "LOCALIZER", "MIP", "DOSE", "SURVIEW", "PATIENT PROTOCOL")

CHAVE_AUTO = "autopet.auto"
CHAVE_EXAME_CONTEM = "autopet.exame_contem"
CHAVE_MODALIDADES = "autopet.modalidades"
CHAVE_PRIOR_CT = "autopet.prioridade"
CHAVE_ESPESSURA = "autopet.espessura_max"
CHAVE_MIN_CORTES = "autopet.min_cortes"
CHAVE_DESTINOS = "autopet.destinos"
PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "PET|FDG|PET-CT|PET/CT|PETCT|ONCO|CORPO INTEIRO|WHOLE BODY",
    CHAVE_MODALIDADES: ["PT"],
    CHAVE_PRIOR_CT: "AC|CORRIGIDO|WB|WHOLE|CORPO|FDG|PET",
    CHAVE_ESPESSURA: 6.0,
    CHAVE_MIN_CORTES: MIN_CORTES,
    CHAVE_DESTINOS: [],
}
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_CT, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES,
          "excluir": ("NAC", "NOAC", "NON AC", "SEM CORRECAO", "MIP", "MAX", "3D")}
NOME_CADIA = "Lesões no PET-FDG (autoPET)"
TITULO_CADIA = "Lesões no PET-FDG: MTV, TLG e SUV de cada lesão (nnU-Net autoPET II)"
EXPLICACAO_CADIA = ("No PET/CT com FDG: a IA do desafio autoPET acha as lesões ávidas (deixa de fora a captação "
                    "fisiológica do cérebro, coração, rins e bexiga) e mede o volume metabólico total (MTV), a "
                    "glicólise total (TLG) e o SUV de cada lesão. Precisa dos modelos extras instalados. Os "
                    "resultados aparecem em Aplicações ▸ Achados de IA, um por lesão, para conferir.")
CHAVES_RESUMO = ("n_lesoes", "mtv", "tlg", "suvmax")
CHAVES_LESAO = ("vol_ml", "suvmax", "suvmean", "suvpeak", "tlg")
CHAVES = CHAVES_RESUMO + CHAVES_LESAO


def config(settings, chave):
    if chave == CHAVE_MODALIDADES:
        return ["PT"]
    if settings is None:
        return PADROES.get(chave)
    try:
        v = settings.get(chave, PADROES.get(chave))
    except Exception:  # noqa: BLE001
        v = PADROES.get(chave)
    return PADROES.get(chave) if v is None else v


def exame_serve(info: dict, settings=None) -> bool:
    if "PT" not in (info.get("modalities") or "").upper():
        return False
    from ipe.ai import totalseg as TS
    pads = TS._padroes(config(settings, CHAVE_EXAME_CONTEM))
    return not pads or any(p in TS._sem_acento(info.get("description", "")) for p in pads)


def escolher_serie(repo, study_uid: str, settings=None):
    """O PET corrigido por atenuação com mais cortes."""
    from ipe.ai import totalseg as TS
    pets = [s for s in repo.series_for_study(study_uid) if (s.modality or "").upper() == "PT"]
    excl = [TS._sem_acento(x) for x in PERFIL["excluir"]]
    bons = [s for s in pets if not any(e in TS._sem_acento(s.description or "") for e in excl)] or pets
    bons = [s for s in bons if (s.num_images or 0) >= MIN_CORTES]
    if not bons:
        return None, "não há PET com cortes suficientes neste exame"
    return max(bons, key=lambda s: s.num_images or 0).series_uid, ""


def ja_feita(repo, study_uid: str) -> bool:
    from ipe.ai import totalseg as TS
    return TS.ja_segmentado(repo, study_uid, DESC_SEG)


def tarefas(modalidade: str = "PT", settings=None) -> list[dict]:
    return [{"nome": "autopet", "rotulo": "lesões FDG (autoPET)"}]


def serie_ct(repo, study_uid: str):
    """A TC do PET/CT: a de mais cortes, sem topograma/MIP."""
    from ipe.ai import totalseg as TS
    cts = [s for s in repo.series_for_study(study_uid) if (s.modality or "").upper() == "CT"
           and not any(x in TS._sem_acento(s.description or "") for x in _FORA_CT)]
    return max(cts, key=lambda s: s.num_images or 0) if cts else None


def fator_suv(t) -> tuple[float | None, str]:
    from ipe.imaging.suv import suv_factor_for_file
    try:
        return suv_factor_for_file(t.frames[0].path)
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def canais_extras(t) -> dict:
    """A TC na grade do PET e o PET em SUV (o trabalhador usa os dois)."""
    from ipe.ai import extras as EX
    from ipe.ai.totalseg import Falhou
    from ipe.imaging.series import build_frames
    from ipe.imaging.volume import build_volume
    se = serie_ct(t.repo, t.study_uid)
    if se is None:
        raise Falhou("O autoPET precisa da TC do PET/CT, e não há TC neste exame.")
    fator, motivo = fator_suv(t)
    if not fator:
        raise Falhou(f"Sem o SUV deste PET ({motivo}): o autoPET trabalha em SUV.")
    vol_ct = build_volume(build_frames(t.repo.instances_for_series(se.series_uid), se.series_uid), t.cache)
    t.ct_series_uid = se.series_uid
    return {"ct": EX.na_grade(t.vol, vol_ct, fora=-1024.0), "suv": np.asarray(t.vol.data, np.float32) * fator}


# ------------------------------------------------------------------ a conta
@dataclass
class Lesao:
    n: int
    vol_ml: float
    suvmax: float
    suvmean: float
    suvpeak: float | None
    tlg: float
    centro: list


@dataclass
class Resultado:
    lesoes: list = field(default_factory=list)
    mtv: float = 0.0
    tlg: float = 0.0
    suvmax: float | None = None
    fator: float | None = None
    mascara: np.ndarray | None = None
    offset: tuple = (0, 0, 0)
    centro: list | None = None
    avisos: list = field(default_factory=list)
    elegibilidade: str = ""
    versao: str = ""
    series_uid: str = ""
    calculado: bool = False


def calcular(t, rotulos: dict, settings=None) -> Resultado:
    from ipe.imaging.estruturas import rotular
    from ipe.imaging.segment import suv_peak
    vol = t.vol
    res = Resultado(versao=getattr(t, "versao", ""), series_uid=t.series_uid, calculado=True)
    fator, motivo = fator_suv(t)
    res.fator = fator
    lab = rotulos.get("autopet", (None, {}))[0]
    desc = t.descricao_serie or t.series_uid[-8:]
    res.elegibilidade = (f"PET, série “{desc}”, {vol.data.shape[0]} cortes de {abs(vol.dz):.2f} mm, pixel "
                         f"{vol.dy:.2f} × {vol.dx:.2f} mm; TC do PET/CT reamostrada na grade do PET")
    if not fator:
        res.avisos.append(f"sem o fator de SUV ({motivo})")
        return res
    if lab is None:
        res.avisos.append("o modelo não devolveu a máscara")
        return res
    m = np.asarray(lab) > 0
    voxel_ml = float(vol.dx * vol.dy * abs(vol.dz)) / 1000.0
    suv = np.asarray(vol.data, np.float32) * fator
    if m.any():
        rot, n = rotular(m)
        cont = np.bincount(rot.ravel(), minlength=n + 1)
        manter = [x for x in range(1, n + 1) if cont[x] * voxel_ml >= MIN_ML]
        pequenas = n - len(manter)
        m = np.isin(rot, manter)
        les = []
        for x in manter:
            idx = np.argwhere(rot == x)
            (k0, j0, i0), (k1, j1, i1) = idx.min(0), idx.max(0) + 1
            sub = suv[k0:k1, j0:j1, i0:i1]
            mk = rot[k0:k1, j0:j1, i0:i1] == x
            v = sub[mk]
            vol_ml = float(mk.sum() * voxel_ml)
            kk, jj, ii = idx.mean(0)
            les.append(Lesao(0, vol_ml, float(v.max()), float(v.mean()), suv_peak(vol, sub / fator, mk, fator),
                             float(v.mean() * vol_ml), [float(c) for c in vol.voxel_to_patient(ii, jj, kk)]))
        les.sort(key=lambda x: -x.tlg)
        for i, x in enumerate(les, start=1):
            x.n = i
        res.lesoes = les
        if pequenas:
            res.avisos.append(f"{pequenas} ilha(s) menor(es) que {MIN_ML:.1f} mL ficaram de fora".replace(".", ","))
    if m.any():
        res.mtv = float(m.sum() * voxel_ml)
        res.tlg = float(suv[m].mean() * res.mtv)
        res.suvmax = float(suv[m].max())
        kk, jj, ii = np.nonzero(m)
        a, b, c = kk.min(), jj.min(), ii.min()
        res.mascara = m[a:kk.max() + 1, b:jj.max() + 1, c:ii.max() + 1].copy()
        res.offset = (int(a), int(b), int(c))
        res.centro = [float(x) for x in vol.voxel_to_patient(ii.mean(), jj.mean(), kk.mean())]
    res.avisos.append("modelo de pesquisa (desafio autoPET): conferir cada lesão — captação fisiológica (intestino, "
                      "músculo, gordura marrom, inflamação) pode entrar, e lesão pequena ou pouco ávida pode faltar")
    return res


# ------------------------------------------------------------------ banco e laudo
def _n(v, u, n, casas=1):
    return AC.numero(None if v is None else round(float(v), casas), u, n)


def itens_para_o_banco(res: Resultado, t, versao: str) -> list[dict]:
    if not res.calculado or not res.fator:
        return []
    eleg = res.elegibilidade + (". Atenção: " + "; ".join(res.avisos) if res.avisos else "")
    base = {"series_uid": t.series_uid, "modelo": MODELO, "versao": versao or res.versao, "elegibilidade": eleg}
    itens = [{**base, "rotulo": "T", "tipo": TIPO_RESUMO, "local": "corpo inteiro", "posicao": res.centro,
              "numeros": {"n_lesoes": _n(len(res.lesoes), "", "Lesões", 0), "mtv": _n(res.mtv, "mL", "MTV"),
                          "tlg": _n(res.tlg, "g", "TLG"), "suvmax": _n(res.suvmax, "", "SUVmáx", 1)}}]
    for x in res.lesoes[:MAX_ACHADOS]:
        itens.append({**base, "rotulo": f"P{x.n}", "tipo": TIPO_LESAO, "local": "", "posicao": x.centro,
                      "numeros": {"vol_ml": _n(x.vol_ml, "mL", "Volume", 2), "suvmax": _n(x.suvmax, "", "SUVmáx"),
                                  "suvmean": _n(x.suvmean, "", "SUVmédio"),
                                  "suvpeak": _n(x.suvpeak, "", "SUVpeak"), "tlg": _n(x.tlg, "g", "TLG")}})
    if len(res.lesoes) > MAX_ACHADOS:
        itens[0]["elegibilidade"] += f"; {len(res.lesoes) - MAX_ACHADOS} lesões menores não viraram achado"
    return itens


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
                log.exception("trocar a SEG do autoPET anterior")
    out = {"series": [], "ferramenta": FERRAMENTA}
    if res.mascara is not None and res.mascara.any():
        vol = t.vol
        ds = build_seg(vol, [(SimpleNamespace(mask=res.mascara, offset=res.offset), "Lesões FDG", (255, 90, 40))],
                       vol.source_path, frames=t.frames, series_number=SERIE_SEG, description=DESC_SEG,
                       algoritmo=("AUTOMATIC", f"nnU-Net autoPET II {versao}".strip()))
        tmp = Path(tempfile.mkdtemp(prefix="dv_autopet_"))
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


def _f(v, casas=1) -> str:
    return "—" if v is None else f"{float(v):.{casas}f}".replace(".", ",")


def resumo(res: Resultado) -> str:
    if not res.fator:
        return res.avisos[0] if res.avisos else "sem SUV"
    if not res.lesoes:
        return "nenhuma lesão ávida por FDG achada pela IA"
    return f"{len(res.lesoes)} lesão(ões), MTV {_f(res.mtv)} mL, TLG {_f(res.tlg)} g, SUVmáx {_f(res.suvmax)}"


def n_itens(res: Resultado) -> int:
    return (1 + min(len(res.lesoes), MAX_ACHADOS)) if res.fator else 0


def mensagem(res: Resultado, minutos: float) -> str:
    msg = (f"autoPET pronto em {minutos:.1f} min — {resumo(res)}. Cada lesão está em Aplicações ▸ Achados de IA, "
           f"para conferir (e descartar a captação fisiológica); a máscara está na série “{DESC_SEG}”.")
    avisos = [a for a in res.avisos if not a.startswith("modelo de pesquisa")]
    if avisos:
        msg += "\n\nConfira: " + "; ".join(avisos) + "."
    return msg


def frase(a: dict) -> str:
    n = AC.numeros_validos(a)

    def v(k, casas=1):
        x = (n.get(k) or {}).get("v")
        return None if x is None else _f(x, casas)
    if a.get("tipo") == TIPO_LESAO:
        txt = "Lesão hipermetabólica" + (f" ({a['local']})" if a.get("local") else "")
        partes = [f"SUVmáx {v('suvmax')}" if v("suvmax") else "", f"volume metabólico {v('vol_ml', 2)} mL"
                  if v("vol_ml", 2) else "", f"TLG {v('tlg')} g" if v("tlg") else ""]
        partes = [p for p in partes if p]
        return txt + (", " + ", ".join(partes) if partes else "") + "."
    nl = int(float((n.get("n_lesoes") or {}).get("v") or 0))
    if not nl:
        return "Sem lesões hipermetabólicas identificadas pela segmentação automática (autoPET)."
    return (f"Volume metabólico tumoral total (MTV) de {v('mtv')} mL e glicólise total das lesões (TLG) de {v('tlg')} g, "
            f"em {nl} lesão(ões) hipermetabólica(s), SUVmáx {v('suvmax')}.")
