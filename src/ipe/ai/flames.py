"""Lesões de substância branca no FLAIR pela IA (FLAMeS) — 0.100.25.

O modelo é o **FLAMeS** (Dereskewicz, La Rosa et al., J Neuroimaging 2025; nnU-Net v2 `3d_fullres`, treinado em
668 exames de esclerose múltipla de 1,5 T e 3 T; pesos CC BY 4.0 no Zenodo, registro 17955359). Entra **só o
FLAIR**, sem o crânio; o Ipê tira o crânio com a máscara do SynthSeg (a mesma dos índices do crânio), na mesma
rodada, e usa as estruturas do SynthSeg para dizer **onde** está cada lesão:

- **infratentorial**: a maior parte da lesão no tronco ou no cerebelo;
- **periventricular**: encosta num ventrículo lateral (até 1,5 mm);
- **justacortical / cortical**: encosta no córtex;
- **profunda**: as demais.

Sai um achado revisável com o número de lesões, o volume total, a contagem por região, a maior lesão e a
comparação com o exame anterior do paciente que também tenha passado pela ferramenta (número e volume; não é
pareamento lesão a lesão). A SEG tem as lesões coloridas por região.

É um modelo de pesquisa, feito para esclerose múltipla e para FLAIR 3D: marca qualquer hipersinal em FLAIR da
substância branca (microangiopatia, gliose…), não distingue a causa, e perde sensibilidade em FLAIR 2D espesso.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from ipe.ai import achados as AC

log = logging.getLogger(__name__)

FERRAMENTA = "flames"
TITULO = "Lesões de substância branca no FLAIR (IA, FLAMeS)"
MARCA = "· FLAMeS"
DESC_SEG = f"Lesões no FLAIR {MARCA}"
SERIE_SEG = 988
MIN_CORTES = 16
MODALIDADES = ("MR",)
MOTIVO_MODALIDADE = "O FLAMeS roda no FLAIR da RM de crânio."
MODELO = "FLAMeS (nnU-Net 3d_fullres)"
MODELO_EXTRA = "flames"
CHAVE_SAIDA = "flames"
TIPO = "Lesões de substância branca (FLAIR)"
MIN_ML = 0.010                 # ilhas menores que ~10 mm³ (menos de 3 mm) ficam de fora
PERTO_MM = 1.5                 # "encosta" no ventrículo
ESPESSO_MM = 3.0

REGIOES = ("peri", "justa", "infra", "prof")
NOMES = {"peri": "Periventriculares", "justa": "Justacorticais / corticais", "infra": "Infratentoriais",
         "prof": "Profundas"}
CORES = {"peri": (255, 90, 60), "justa": (250, 210, 60), "infra": (90, 170, 255), "prof": (190, 120, 255)}
VENTRICULOS = (4, 43, 5, 44)
CORTEX = (3, 42)
INFRA = (16, 7, 8, 46, 47)

CHAVE_AUTO = "flames.auto"
CHAVE_EXAME_CONTEM = "flames.exame_contem"
CHAVE_MODALIDADES = "flames.modalidades"
CHAVE_PRIOR_CT = "flames.prioridade"
CHAVE_ESPESSURA = "flames.espessura_max"
CHAVE_MIN_CORTES = "flames.min_cortes"
CHAVE_DESTINOS = "flames.destinos"
PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "CRANIO|CRÂNIO|ENCEFALO|ENCÉFALO|BRAIN|HEAD|ESCLEROSE|DESMIELINIZANTE|NEURO",
    CHAVE_MODALIDADES: ["MR"],
    CHAVE_PRIOR_CT: "3D FLAIR|FLAIR 3D|CUBE|SPACE|VISTA|FLAIR",
    CHAVE_ESPESSURA: 6.0,
    CHAVE_MIN_CORTES: MIN_CORTES,
    CHAVE_DESTINOS: [],
}
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_CT, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES,
          "excluir": ("T1", "ADC", "DWI", "DIF", "SWI", "SWAN", "PERF", "DSC", "ASL", "TOF", "MIP", "SCOUT",
                      "LOCALIZER", "CALIBRA", "SYNTHSR")}
NOME_CADIA = "Lesões no FLAIR (FLAMeS)"
TITULO_CADIA = "Lesões de substância branca no FLAIR: número, volume e regiões (FLAMeS)"
EXPLICACAO_CADIA = ("Na RM de crânio com FLAIR (de preferência 3D): tira o crânio, marca as lesões hiperintensas da "
                    "substância branca e conta por região (periventricular, justacortical, infratentorial, profunda), "
                    "com o volume total e a comparação com o exame anterior. Precisa dos modelos extras instalados "
                    "(2,4 GB). O resultado aparece em Aplicações ▸ Achados de IA, para conferir.")


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


def e_flair(descricao: str) -> bool:
    """FLAIR em T2 (o "T1 FLAIR" da GE é um T1: não serve)."""
    from ipe.ai.totalseg import _sem_acento
    d = _sem_acento(descricao or "")
    if "FLAIR" not in d and "DARK FLUID" not in d and "TIRM" not in d:
        return False
    return not any(x in d for x in PERFIL["excluir"])


def escolher_serie(repo, study_uid: str, settings=None):
    """O FLAIR com mais cortes (o 3D, quando há)."""
    flairs = [s for s in repo.series_for_study(study_uid)
              if (s.modality or "").upper() == "MR" and e_flair(s.description or "")
              and (s.num_images or 0) >= MIN_CORTES and MARCA not in (s.description or "")]
    if not flairs:
        return None, "não achei um FLAIR (T2) neste exame"
    return max(flairs, key=lambda s: s.num_images or 0).series_uid, ""


def ja_feita(repo, study_uid: str) -> bool:
    return bool(repo.achados(study_uid, FERRAMENTA))


def tarefas(modalidade: str = "MR", settings=None) -> list[dict]:
    return [{"nome": "synthseg", "rotulo": "encéfalo (tirar o crânio e localizar)", "neuro": True},
            {"nome": "flames", "rotulo": "lesões no FLAIR (FLAMeS)"}]


# ------------------------------------------------------------------ a conta
@dataclass
class Lesao:
    n: int
    vol_ml: float
    regiao: str
    centro: list


@dataclass
class Resultado:
    lesoes: list = field(default_factory=list)
    total_ml: float = 0.0
    por_regiao: dict = field(default_factory=dict)       # região -> (número, mL)
    maior_mm: float | None = None
    rotulos: np.ndarray | None = None                    # recorte: 1 peri, 2 justa, 3 infra, 4 prof
    offset: tuple = (0, 0, 0)
    centro: list | None = None
    anterior: dict | None = None                         # {"data", "n", "ml"}
    avisos: list = field(default_factory=list)
    elegibilidade: str = ""
    versao: str = ""
    series_uid: str = ""
    calculado: bool = False


def _dilatar3(m: np.ndarray, passos: tuple) -> np.ndarray:
    """Dilatação por deslocamentos (6 vizinhos), `passos` voxels em cada eixo (k, j, i)."""
    out = m.copy()
    for eixo, n in enumerate(passos):
        for _ in range(int(n)):
            a = out.copy()
            sl_a, sl_b = [slice(None)] * 3, [slice(None)] * 3
            sl_a[eixo], sl_b[eixo] = slice(1, None), slice(None, -1)
            a[tuple(sl_a)] |= out[tuple(sl_b)]
            a[tuple(sl_b)] |= out[tuple(sl_a)]
            out = a
    return out


def classificar(lesoes: np.ndarray, synthseg: np.ndarray, espacamento: tuple) -> tuple:
    """(rótulos das ilhas, lista de (id, voxels, região)). `espacamento` = (dz, dy, dx) em mm."""
    from ipe.imaging.estruturas import rotular
    ilhas, n = rotular(lesoes)
    if n == 0:
        return ilhas, []
    tam = np.bincount(ilhas.ravel(), minlength=n + 1)
    infra = np.bincount(ilhas[np.isin(synthseg, INFRA)], minlength=n + 1)
    perto = tuple(max(1, int(np.ceil(PERTO_MM / max(float(e), 1e-3)))) if e <= PERTO_MM * 2 else 1
                  for e in espacamento)
    vent = _dilatar3(np.isin(synthseg, VENTRICULOS), perto)
    toca_vent = np.bincount(ilhas[vent], minlength=n + 1) > 0
    cortex = _dilatar3(np.isin(synthseg, CORTEX), (0, 1, 1))
    toca_cortex = np.bincount(ilhas[cortex], minlength=n + 1) > 0
    out = []
    for k in range(1, n + 1):
        if infra[k] >= 0.5 * tam[k]:
            reg = "infra"
        elif toca_vent[k]:
            reg = "peri"
        elif toca_cortex[k]:
            reg = "justa"
        else:
            reg = "prof"
        out.append((k, int(tam[k]), reg))
    return ilhas, out


def _anterior(t) -> dict | None:
    """O resultado desta ferramenta no exame anterior mais recente do mesmo paciente."""
    try:
        info = t.repo.study_info(t.study_uid) or {}
        pid, data = info.get("patient_id"), str(info.get("study_date") or "")
        if not pid or not data:
            return None
        antes = [s for s in t.repo.studies_of_patient(pid)
                 if s.study_uid != t.study_uid and str(s.study_date or "") and str(s.study_date) < data]
        for s in sorted(antes, key=lambda s: str(s.study_date), reverse=True):
            for a in t.repo.achados(s.study_uid, FERRAMENTA):
                if a.get("estado") == "descartado":
                    continue
                n = AC.numeros_validos(a)
                if (n.get("n") or {}).get("v") is not None:
                    return {"data": str(s.study_date), "n": int(float(n["n"]["v"])),
                            "ml": float((n.get("vol_ml") or {}).get("v") or 0.0)}
    except Exception:  # noqa: BLE001
        log.exception("procurar o FLAMeS do exame anterior")
    return None


def calcular(t, rotulos: dict, settings=None) -> Resultado:
    from ipe.ai.figado_lesoes import _maior_diametro_axial
    vol = t.vol
    res = Resultado(versao=getattr(t, "versao", ""), series_uid=t.series_uid, calculado=True)
    desc = t.descricao_serie or t.series_uid[-8:]
    dz = float(abs(vol.dz))
    res.elegibilidade = f"RM, FLAIR “{desc}”, {vol.data.shape[0]} cortes de {dz:.2f} mm".replace(".", ",")
    lab = rotulos.get("flames", (None, {}))[0]
    seg = rotulos.get("synthseg", (None, {}))[0]
    if lab is None or seg is None:
        res.avisos.append("o modelo não devolveu a máscara" if lab is None else "o SynthSeg não devolveu o encéfalo")
        res.calculado = lab is not None and seg is not None
        return res
    lab, seg = np.asarray(lab) > 0, np.asarray(seg)
    voxel_ml = float(vol.dx * vol.dy * dz) / 1000.0
    ilhas, lista = classificar(lab, seg, (dz, float(vol.dy), float(vol.dx)))
    codigo = {r: i + 1 for i, r in enumerate(REGIOES)}
    mapa = np.zeros(lab.shape, np.uint8)
    tabela = np.zeros(len(lista) + 1, np.uint8)
    validas = []
    for k, vox, reg in lista:
        if vox * voxel_ml < MIN_ML:
            continue
        tabela[k] = codigo[reg]
        validas.append((k, vox, reg))
    if validas:
        mapa = tabela[ilhas]
    res.por_regiao = {r: (0, 0.0) for r in REGIOES}
    if validas:
        kk, jj, ii = np.nonzero(ilhas)
        quem = ilhas[kk, jj, ii]
        cont = np.maximum(np.bincount(quem, minlength=len(lista) + 1), 1)
        ck, cj, ci = (np.bincount(quem, weights=x, minlength=len(lista) + 1) / cont for x in (kk, jj, ii))
    for n, (k, vox, reg) in enumerate(sorted(validas, key=lambda x: -x[1]), 1):
        centro = [float(x) for x in vol.voxel_to_patient(ci[k], cj[k], ck[k])]
        res.lesoes.append(Lesao(n, vox * voxel_ml, reg, centro))
        a, b = res.por_regiao[reg]
        res.por_regiao[reg] = (a + 1, b + vox * voxel_ml)
        if n == 1:
            mk, mj, mi = np.nonzero(ilhas == k)
            rec = (ilhas == k)[mk.min():mk.max() + 1, mj.min():mj.max() + 1, mi.min():mi.max() + 1]
            res.maior_mm = _maior_diametro_axial(rec, vol.dx, vol.dy)
            res.centro = centro
    res.total_ml = float(sum(x.vol_ml for x in res.lesoes))
    if (mapa > 0).any():
        kk, jj, ii = np.nonzero(mapa)
        a, b, c = kk.min(), jj.min(), ii.min()
        res.rotulos = mapa[a:kk.max() + 1, b:jj.max() + 1, c:ii.max() + 1].copy()
        res.offset = (int(a), int(b), int(c))
    res.anterior = _anterior(t)
    if dz > ESPESSO_MM:
        res.avisos.append(f"FLAIR 2D de {dz:.1f} mm: o modelo foi feito para FLAIR 3D e perde lesões pequenas"
                          .replace(".", ","))
    res.avisos.append("modelo de pesquisa feito para esclerose múltipla: marca qualquer hipersinal da substância "
                      "branca, sem distinguir a causa; confira as lesões na imagem")
    return res


def _n(v, u, n, casas=1):
    return AC.numero(None if v is None else round(float(v), casas), u, n)


def itens_para_o_banco(res: Resultado, t, versao: str) -> list[dict]:
    if not res.calculado:
        return []
    numeros = {"n": _n(len(res.lesoes), "", "Lesões", 0), "vol_ml": _n(res.total_ml, "mL", "Volume total", 2)}
    for r in REGIOES:
        numeros[f"n_{r}"] = _n(res.por_regiao.get(r, (0, 0))[0], "", NOMES[r], 0)
    numeros["maior_mm"] = _n(res.maior_mm, "mm", "Maior lesão (axial)", 0)
    if res.anterior:
        numeros["ant_data"] = _n(int(res.anterior["data"][:8] or 0), "", "Exame anterior (AAAAMMDD)", 0)
        numeros["ant_n"] = _n(res.anterior["n"], "", "Lesões no anterior", 0)
        numeros["ant_ml"] = _n(res.anterior["ml"], "mL", "Volume no anterior", 2)
    return [{"series_uid": t.series_uid, "modelo": MODELO, "versao": versao or res.versao, "rotulo": "SB", "tipo": TIPO,
             "local": "encéfalo", "posicao": res.centro, "numeros": numeros,
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
                log.exception("trocar a SEG do FLAMeS anterior")
    out = {"series": [], "ferramenta": FERRAMENTA}
    if res.rotulos is not None and (res.rotulos > 0).any():
        vol = t.vol
        segs = [(SimpleNamespace(mask=res.rotulos == i + 1, offset=res.offset), NOMES[r], CORES[r])
                for i, r in enumerate(REGIOES) if (res.rotulos == i + 1).any()]
        ds = build_seg(vol, segs, vol.source_path, frames=t.frames, series_number=SERIE_SEG, description=DESC_SEG,
                       algoritmo=("AUTOMATIC", f"FLAMeS {versao}".strip()))
        tmp = Path(tempfile.mkdtemp(prefix="ipe_flames_"))
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


def _data(d) -> str:
    d = str(int(float(d))) if d else ""
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 else ""


def resumo(res: Resultado) -> str:
    if not res.calculado:
        return res.avisos[0] if res.avisos else "sem resultado"
    if not res.lesoes:
        return "nenhuma lesão achada pela IA"
    partes = [f"{res.por_regiao[r][0]} {NOMES[r].lower()}" for r in REGIOES if res.por_regiao.get(r, (0,))[0]]
    return f"{len(res.lesoes)} lesão(ões), {_f(res.total_ml, 2)} mL ({', '.join(partes)})"


def n_itens(res: Resultado) -> int:
    return int(res.calculado)


def mensagem(res: Resultado, minutos: float) -> str:
    msg = (f"FLAMeS pronto em {minutos:.1f} min — {resumo(res)}. O achado está em Aplicações ▸ Achados de IA, para "
           f"conferir; as lesões, coloridas por região, estão na série “{DESC_SEG}”.")
    if res.anterior:
        msg += (f"\n\nExame anterior ({_data(res.anterior['data'])}): {res.anterior['n']} lesão(ões), "
                f"{_f(res.anterior['ml'], 2)} mL.")
    if res.avisos:
        msg += "\n\nConfira: " + "; ".join(res.avisos) + "."
    return msg


def frase(a: dict) -> str:
    n = AC.numeros_validos(a)

    def v(k):
        x = (n.get(k) or {}).get("v")
        return None if x is None else float(x)
    total = int(v("n") or 0)
    if not total:
        return "Sem lesões hiperintensas em FLAIR na substância branca pela segmentação automática (FLAMeS)."
    partes = []
    for r, nome in (("peri", "periventriculares"), ("justa", "justacorticais/corticais"),
                    ("infra", "infratentoriais"), ("prof", "na substância branca profunda")):
        q = int(v(f"n_{r}") or 0)
        if q:
            partes.append(f"{q} {nome}")
    txt = (f"Lesões hiperintensas em FLAIR na substância branca: {total}, com volume total de "
           f"{_f(v('vol_ml'), 2)} mL")
    if partes:
        txt += " (" + ", ".join(partes) + ")"
    if v("maior_mm"):
        txt += f"; a maior com {_f(v('maior_mm'), 0)} mm"
    txt += "."
    if v("ant_n") is not None and v("ant_data"):
        dn = total - int(v("ant_n"))
        dv = (v("vol_ml") or 0.0) - (v("ant_ml") or 0.0)
        sinal = "+" if dn > 0 else ""
        txt += (f" No exame de {_data(v('ant_data'))}: {int(v('ant_n'))} lesões e {_f(v('ant_ml'), 2)} mL "
                f"(diferença de {sinal}{dn} lesões e {'+' if dv > 0 else ''}{_f(dv, 2)} mL, pela mesma ferramenta).")
    return txt
