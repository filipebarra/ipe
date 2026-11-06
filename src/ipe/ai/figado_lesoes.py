"""Lesões hepáticas e carga tumoral por segmento de Couinaud, na TC e na RM (0.99.82).

Pedido dele (06/11/2026): "faça então as etapas 1 a 5" da lista do MedMLX; esta é a 3 ("nnU-Net fígado com
tumor → carga tumoral por Couinaud", item O12 do backlog). Em vez de baixar mais um modelo, usa duas tarefas
**abertas** do TotalSegmentator que já vêm no instalador da segmentação (2.18):

- `liver_segments` / `liver_segments_mr`: os oito segmentos de Couinaud (a união é o fígado);
- `liver_lesions` / `liver_lesions_mr`: as lesões focais do fígado (sem dizer o que são).

Sai, para o fígado inteiro e para cada segmento: volume, volume das lesões e a **carga** (% do volume ocupado
por lesão); e, para cada lesão (componente conexo, 6-vizinhos): volume, maior diâmetro axial, HU/sinal médio e
o segmento onde está a maior parte dela. Cada lesão vira um **achado** revisável (até 20, as maiores), mais um
achado de resumo com a carga por segmento; os que o médico confirmar vão ao laudo e podem ser ligados a uma
lesão do acompanhamento.

O modelo não classifica a lesão (cisto, hemangioma, metástase): é contagem e volume. A elegibilidade avisa
quando a série não tem contraste (as lesões pequenas e hipovasculares escapam mais) e quando o corte é grosso.

Saída: SEG "Lesões hepáticas · TotalSegmentator" (série 984), só na série calculada, com as lesões e os
segmentos de Couinaud (aparecem também no 3D, em Estruturas).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from ipe.ai import achados as AC

log = logging.getLogger(__name__)

FERRAMENTA = "figado_lesoes"
TITULO = "Lesões hepáticas e carga por segmento de Couinaud (IA)"
MARCA = "· TotalSegmentator"
DESC_SEG = f"Lesões hepáticas {MARCA}"
SERIE_SEG = 984
MIN_CORTES = 30
MODALIDADES = ("CT", "MR")
MOTIVO_MODALIDADE = "As lesões hepáticas são procuradas na TC ou na RM de abdome."
MODELO = "TotalSegmentator liver_lesions + liver_segments"
CHAVE_SAIDA = "figado_lesoes"
TIPO_RESUMO = "Lesões hepáticas (carga por segmento)"
TIPO_LESAO = "Lesão hepática"
MIN_ML = 0.05              # ilhas menores que isso (≈ 4 mm de diâmetro) ficam de fora: ruído do modelo
MAX_ACHADOS = 20
ESPESSURA_MAX = 3.0

SEGMENTOS = {f"liver_segment_{k}": k for k in range(1, 9)}
NOME_SEGMENTO = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII"}
COR_LESAO = (255, 80, 80)
CORES_SEG = {1: (230, 200, 90), 2: (120, 200, 120), 3: (90, 170, 230), 4: (200, 140, 230),
             5: (240, 160, 90), 6: (110, 210, 200), 7: (230, 120, 160), 8: (170, 170, 240)}
_CONTRASTE = ("C/C", "COM CONTRASTE", "CONTRASTE", "ARTERIAL", "PORTAL", "VENOSA", "TARDIA", "EQUILIBRIO",
              "HEPATOBILIAR", "CONTRAST", "C+", "POS", "POST", "GD", "GADO", "PRIMOVIST", "EOB")

# Configurações ▸ CAD/IA ▸ Lesões hepáticas
CHAVE_AUTO = "figado_lesoes.auto"
CHAVE_EXAME_CONTEM = "figado_lesoes.exame_contem"
CHAVE_MODALIDADES = "figado_lesoes.modalidades"
CHAVE_PRIOR_CT = "figado_lesoes.prioridade_ct"
CHAVE_PRIOR_MR = "figado_lesoes.prioridade_mr"
CHAVE_ESPESSURA = "figado_lesoes.espessura_max"
CHAVE_MIN_CORTES = "figado_lesoes.min_cortes"
CHAVE_DESTINOS = "figado_lesoes.destinos"
PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "ABD|ABDOME|ABDOMEN|ABDOMINAL|FIGADO|FÍGADO|HEPAT|LIVER|TORAX E ABDOME",
    CHAVE_MODALIDADES: ["CT", "MR"],
    CHAVE_PRIOR_CT: "PORTAL|VENOSA|VENOUS|C/C|CONTRASTE|ABDOME|STANDARD|PARTES MOLES",
    CHAVE_PRIOR_MR: "HEPATOBILIAR|HBP|PORTAL|VENOSA|POS|PÓS|GD|C+|VIBE|LAVA|THRIVE|T1",
    CHAVE_ESPESSURA: 5.0,
    CHAVE_MIN_CORTES: MIN_CORTES,
    CHAVE_DESTINOS: [],
}
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_MR, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES,
          "excluir": ("FATFRAC", "FAT FRAC", "R2*", "T2*", "ADC", "DWI", "DIFUS", "MIP", "SCOUT", "TOPO")}
NOME_CADIA = "Lesões hepáticas por segmento"
TITULO_CADIA = "Lesões hepáticas e carga tumoral por segmento de Couinaud (TotalSegmentator liver_lesions)"
EXPLICACAO_CADIA = ("Na TC ou na RM de abdome: acha o fígado, os oito segmentos de Couinaud e as lesões focais, e "
                    "mede o volume de cada lesão, o maior diâmetro axial e a carga (% do fígado e de cada segmento "
                    "ocupada por lesão). Não diz o que a lesão é. Os resultados aparecem em Aplicações ▸ Achados de "
                    "IA, um por lesão, para conferir antes do laudo.")
CHAVES_RESUMO = ("n_lesoes", "vol_lesoes", "carga_pct", "vol_figado", "maior_diam")
CHAVES_LESAO = ("vol_ml", "diam_mm", "media")
CHAVES = CHAVES_RESUMO + CHAVES_LESAO


def config(settings, chave):
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
    mr = (modalidade or "").upper() == "MR"
    suf = "_mr" if mr else ""
    return [{"nome": f"liver_segments{suf}", "rotulo": "segmentos do fígado (Couinaud)", "fig_lesoes": True},
            {"nome": f"liver_lesions{suf}", "rotulo": "lesões hepáticas", "fig_lesoes": True}]


# ------------------------------------------------------------------ a conta
@dataclass
class Lesao:
    n: int
    vol_ml: float
    diam_mm: float
    media: float
    segmento: int | None
    segmentos: dict                      # segmento -> fração da lesão nele
    centro: list
    caixa: tuple                         # k0, k1, j0, j1, i0, i1


@dataclass
class Resultado:
    vol_figado: float = 0.0
    vol_lesoes: float = 0.0
    segmentos: dict = field(default_factory=dict)      # k -> {"vol": mL, "lesao": mL, "carga": %}
    lesoes: list = field(default_factory=list)
    lesao_mask: np.ndarray | None = None               # recorte (bbox do fígado)
    seg_mask: np.ndarray | None = None                 # uint8 1..8 no mesmo recorte
    offset: tuple = (0, 0, 0)
    centro: list | None = None
    modalidade: str = "CT"
    avisos: list = field(default_factory=list)
    elegibilidade: str = ""
    versao: str = ""
    series_uid: str = ""

    @property
    def carga(self) -> float | None:
        return round(100.0 * self.vol_lesoes / self.vol_figado, 2) if self.vol_figado > 0 else None


def _maior_diametro_axial(m: np.ndarray, dx: float, dy: float) -> float:
    """Maior distância entre dois pontos da borda da lesão no mesmo corte axial (mm)."""
    melhor = 0.0
    for k in range(m.shape[0]):
        sl = m[k]
        if not sl.any():
            continue
        borda = sl & ~(np.roll(sl, 1, 0) & np.roll(sl, -1, 0) & np.roll(sl, 1, 1) & np.roll(sl, -1, 1))
        jj, ii = np.nonzero(borda if borda.any() else sl)
        pts = np.column_stack([ii * dx, jj * dy]).astype(np.float64)
        if len(pts) > 400:
            pts = pts[np.linspace(0, len(pts) - 1, 400).astype(int)]
        if len(pts) < 2:
            melhor = max(melhor, max(dx, dy))
            continue
        d2 = ((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1)
        melhor = max(melhor, float(np.sqrt(d2.max())) + (dx + dy) / 2)     # + 1 pixel: borda a borda
    return melhor


def _cabecalho(t) -> dict:
    try:
        import pydicom
        ds = pydicom.dcmread(t.frames[0].path, stop_before_pixels=True, force=True,
                             specific_tags=["SliceThickness", "ContrastBolusAgent", "SeriesDescription", "Modality"])
    except Exception:  # noqa: BLE001
        return {}
    return {"espessura": ds.get("SliceThickness"), "contraste": str(ds.get("ContrastBolusAgent", "") or "").strip(),
            "descricao": str(ds.get("SeriesDescription", "") or ""), "modalidade": str(ds.get("Modality", "") or "")}


def calcular(t, rotulos: dict, settings=None) -> Resultado:
    from ipe.ai import cefalometria as CF
    from ipe.ai.totalseg import _sem_acento
    from ipe.imaging.estruturas import rotular
    vol = t.vol
    cab = _cabecalho(t)
    mod = (getattr(t, "modalidade", "") or cab.get("modalidade") or "CT").upper()
    res = Resultado(versao=getattr(t, "versao", ""), series_uid=t.series_uid, modalidade=mod)
    ms = CF.Mascaras(vol, rotulos)
    dados = vol.data
    voxel_ml = float(vol.dx * vol.dy * abs(vol.dz)) / 1000.0
    esp = float(cab.get("espessura") or 0) or abs(float(vol.dz))
    desc = (t.descricao_serie or cab.get("descricao") or t.series_uid[-8:])
    res.elegibilidade = (f"{'RM' if mod == 'MR' else 'TC'}, série “{desc}”, {dados.shape[0]} cortes de {esp:.2f} mm, "
                         f"pixel {vol.dy:.2f} × {vol.dx:.2f} mm")
    seg = np.zeros(dados.shape, np.uint8)
    for classe, k in SEGMENTOS.items():
        m = ms.get(classe)
        if m is not None and m.any():
            seg[m & (seg == 0)] = k
    lesao = ms.get("liver_lesions")
    lesao = np.zeros(dados.shape, bool) if lesao is None else np.asarray(lesao, bool)
    figado = (seg > 0) | lesao
    if not (seg > 0).any():
        res.avisos.append("a IA não achou o fígado nesta série")
        return res
    faltam = [NOME_SEGMENTO[k] for k in range(1, 9) if not (seg == k).any()]
    if faltam:
        res.avisos.append("a IA não separou os segmentos " + ", ".join(faltam))
    # lesão que encosta no fígado conta inteira; o que está longe dele (outro órgão) sai
    if lesao.any():
        lab, n = rotular(lesao)
        perto = np.unique(lab[figado & (lab > 0) & (seg > 0)]) if n else []
        lesao = np.isin(lab, [x for x in perto if x > 0]) if n else lesao
    # o segmento de cada voxel de lesão: o do vizinho de fígado mais próximo (a lesão não é segmento)
    seg_les = seg.copy()
    if lesao.any():
        falta = lesao & (seg_les == 0)
        for _ in range(30):
            if not falta.any():
                break
            viz = np.zeros_like(seg_les)
            for ax in range(3):
                for sh in (1, -1):
                    r_ = np.roll(seg_les, sh, axis=ax)
                    viz = np.where((viz == 0) & (r_ > 0), r_, viz)
            seg_les = np.where(falta & (viz > 0), viz, seg_les)
            falta = lesao & (seg_les == 0)
    res.vol_figado = float(figado.sum() * voxel_ml)
    res.vol_lesoes = float(lesao.sum() * voxel_ml)
    for k in range(1, 9):
        mk = (seg_les == k) & figado
        if not mk.any():
            continue
        v = float(mk.sum() * voxel_ml)
        vl = float((mk & lesao).sum() * voxel_ml)
        res.segmentos[k] = {"vol": v, "lesao": vl, "carga": 100.0 * vl / v if v else 0.0}
    # as lesões, uma a uma
    if lesao.any():
        lab, n = rotular(lesao)
        cont = np.bincount(lab.ravel(), minlength=n + 1)
        ordem = [x for x in np.argsort(-cont[1:]) + 1 if cont[x] * voxel_ml >= MIN_ML]
        pequenas = int(sum(1 for x in range(1, n + 1) if 0 < cont[x] * voxel_ml < MIN_ML))
        for num, x in enumerate(ordem, start=1):
            idx = np.argwhere(lab == x)
            (k0, j0, i0), (k1, j1, i1) = idx.min(0), idx.max(0) + 1
            sub = lab[k0:k1, j0:j1, i0:i1] == x
            segs = seg_les[k0:k1, j0:j1, i0:i1][sub]
            fr = {int(s): float((segs == s).mean()) for s in np.unique(segs) if s > 0}
            principal = max(fr, key=fr.get) if fr else None
            kk, jj, ii = idx.mean(0)
            res.lesoes.append(Lesao(
                n=num, vol_ml=float(cont[x] * voxel_ml), diam_mm=_maior_diametro_axial(sub, vol.dx, vol.dy),
                media=float(np.asarray(dados[k0:k1, j0:j1, i0:i1][sub], np.float32).mean()), segmento=principal,
                segmentos=fr, centro=[float(c) for c in vol.voxel_to_patient(ii, jj, kk)],
                caixa=(int(k0), int(k1), int(j0), int(j1), int(i0), int(i1))))
        if pequenas:
            res.avisos.append(f"{pequenas} ilha(s) menor(es) que {MIN_ML:.2f} mL ficaram de fora (ruído do modelo)"
                              .replace(".", ","))
    # o recorte da caixa do fígado (para a SEG)
    ks, js, is_ = (np.nonzero(figado.any(axis=a))[0] for a in ((1, 2), (0, 2), (0, 1)))
    k0, k1, j0, j1, i0, i1 = ks[0], ks[-1] + 1, js[0], js[-1] + 1, is_[0], is_[-1] + 1
    res.offset = (int(k0), int(j0), int(i0))
    res.lesao_mask = lesao[k0:k1, j0:j1, i0:i1].copy()
    res.seg_mask = np.where(figado, seg_les, 0)[k0:k1, j0:j1, i0:i1].astype(np.uint8)
    kk, jj, ii = np.argwhere(figado).mean(axis=0)
    res.centro = [float(x) for x in vol.voxel_to_patient(ii, jj, kk)]
    # elegibilidade
    d = _sem_acento(((t.descricao_serie or "") + " " + cab.get("descricao", "")).upper())
    com_contraste = bool(cab.get("contraste")) or any(p in d for p in _CONTRASTE) and "SEM CONTRASTE" not in d
    if not com_contraste:
        res.avisos.append("série que parece sem contraste: o modelo acha melhor as lesões nas fases com contraste "
                          "(portal ou hepatobiliar); lesões pequenas ou isodensas podem ficar de fora")
    if esp > ESPESSURA_MAX:
        res.avisos.append(f"cortes de {esp:.1f} mm: lesões menores que o dobro do corte ficam subestimadas ou de fora"
                          .replace(".", ","))
    res.avisos.append("o modelo não classifica a lesão (cisto, hemangioma, nódulo, metástase): é contagem e volume "
                      "— conferir cada uma")
    return res


# ------------------------------------------------------------------ banco e laudo
def _n(v, u, n, casas=1):
    return AC.numero(None if v is None else round(float(v), casas), u, n)


def _seg_txt(k) -> str:
    return f"segmento {NOME_SEGMENTO[k]}" if k else "segmento indefinido"


def numeros_resumo(res: Resultado) -> dict:
    out = {"n_lesoes": _n(len(res.lesoes), "", "Lesões", 0),
           "vol_lesoes": _n(res.vol_lesoes, "mL", "Volume das lesões"),
           "carga_pct": _n(res.carga, "%", "Carga (% do fígado)", 2),
           "vol_figado": _n(res.vol_figado, "mL", "Volume do fígado", 0),
           "maior_diam": _n(max((x.diam_mm for x in res.lesoes), default=None), "mm", "Maior diâmetro", 0)}
    for k, s in sorted(res.segmentos.items()):
        out[f"seg{k}_carga"] = _n(s["carga"], "%", f"Carga do segmento {NOME_SEGMENTO[k]}", 1)
        out[f"seg{k}_vol"] = _n(s["vol"], "mL", f"Volume do segmento {NOME_SEGMENTO[k]}", 0)
    return out


def numeros_lesao(x: Lesao, mod: str) -> dict:
    return {"vol_ml": _n(x.vol_ml, "mL", "Volume", 2),
            "diam_mm": _n(x.diam_mm, "mm", "Maior diâmetro axial", 0),
            "media": _n(x.media, "HU" if mod == "CT" else "", "Atenuação média" if mod == "CT" else "Sinal médio", 0)}


def itens_para_o_banco(res: Resultado, t, versao: str) -> list[dict]:
    if not res.vol_figado:
        return []
    eleg = res.elegibilidade + (". Atenção: " + "; ".join(res.avisos) if res.avisos else "")
    base = {"series_uid": t.series_uid, "modelo": MODELO, "versao": versao or res.versao, "elegibilidade": eleg}
    itens = [{**base, "rotulo": "F", "tipo": TIPO_RESUMO, "local": "fígado", "posicao": res.centro,
              "numeros": numeros_resumo(res)}]
    for x in res.lesoes[:MAX_ACHADOS]:
        outros = [NOME_SEGMENTO[k] for k, f in sorted(x.segmentos.items()) if k != x.segmento and f >= 0.2]
        local = _seg_txt(x.segmento) + (f" (estende-se ao {', '.join(outros)})" if outros else "")
        itens.append({**base, "rotulo": f"L{x.n}", "tipo": TIPO_LESAO, "local": local, "posicao": x.centro,
                      "numeros": numeros_lesao(x, res.modalidade)})
    if len(res.lesoes) > MAX_ACHADOS:
        itens[0]["elegibilidade"] += (f"; {len(res.lesoes) - MAX_ACHADOS} lesões menores não viraram achado "
                                      f"(entram no volume total)")
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
                log.exception("trocar a SEG de lesões hepáticas anterior")
    out = {"series": [], "ferramenta": FERRAMENTA}
    if res.seg_mask is not None and res.seg_mask.any():
        vol = t.vol
        segs = []
        if res.lesao_mask is not None and res.lesao_mask.any():
            segs.append((SimpleNamespace(mask=res.lesao_mask, offset=res.offset), "Lesões hepáticas", COR_LESAO))
        for k in range(1, 9):
            m = (res.seg_mask == k) & ~(res.lesao_mask if res.lesao_mask is not None else False)
            if m.any():
                segs.append((SimpleNamespace(mask=m, offset=res.offset), f"Segmento {NOME_SEGMENTO[k]}",
                             CORES_SEG[k]))
        ds = build_seg(vol, segs, vol.source_path, frames=t.frames, series_number=SERIE_SEG, description=DESC_SEG,
                       algoritmo=("AUTOMATIC", f"TotalSegmentator {versao} liver_lesions".strip()), anatomia=True)
        tmp = Path(tempfile.mkdtemp(prefix="dv_figles_"))
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
    if not res.vol_figado:
        return res.avisos[0] if res.avisos else "nada medido"
    if not res.lesoes:
        return f"nenhuma lesão hepática achada (fígado {_f(res.vol_figado, 0)} mL)"
    return (f"{len(res.lesoes)} lesão(ões), {_f(res.vol_lesoes)} mL, carga de {_f(res.carga, 2)}% do fígado "
            f"({_f(res.vol_figado, 0)} mL)")


def n_itens(res: Resultado) -> int:
    return (1 + min(len(res.lesoes), MAX_ACHADOS)) if res.vol_figado else 0


def mensagem(res: Resultado, minutos: float) -> str:
    msg = (f"Lesões hepáticas prontas em {minutos:.1f} min — {resumo(res)}. Cada lesão está em Aplicações ▸ Achados "
           f"de IA, para conferir antes do laudo; as máscaras estão na série “{DESC_SEG}”.")
    avisos = [a for a in res.avisos if not a.startswith("o modelo não classifica")]
    if avisos:
        msg += "\n\nConfira: " + "; ".join(avisos) + "."
    return msg


def frase(a: dict) -> str:
    n = AC.numeros_validos(a)

    def v(k, casas=1):
        x = (n.get(k) or {}).get("v")
        return None if x is None else _f(x, casas)
    if a.get("tipo") == TIPO_LESAO:
        txt = f"Lesão hepática no {a.get('local', 'fígado')}"
        partes = []
        if v("diam_mm", 0):
            partes.append(f"maior diâmetro axial {v('diam_mm', 0)} mm")
        if v("vol_ml", 2):
            partes.append(f"volume {v('vol_ml', 2)} mL")
        if v("media", 0) is not None and (n.get("media") or {}).get("u") == "HU":
            partes.append(f"atenuação média {v('media', 0)} HU")
        return txt + (", " + ", ".join(partes) if partes else "") + "."
    nl = int(float((n.get("n_lesoes") or {}).get("v") or 0))
    if not nl:
        return f"Não foram identificadas lesões focais hepáticas pela segmentação automática (fígado {v('vol_figado', 0)} mL)."
    txt = (f"{nl} lesão(ões) focal(is) hepática(s), volume total de {v('vol_lesoes')} mL, correspondendo a "
           f"{v('carga_pct', 2)}% do volume hepático ({v('vol_figado', 0)} mL)")
    segs = [f"{NOME_SEGMENTO[k]} {v(f'seg{k}_carga')}%" for k in range(1, 9)
            if v(f"seg{k}_carga") is not None and float((n.get(f"seg{k}_carga") or {}).get("v") or 0) > 0]
    if segs:
        txt += ". Carga por segmento: " + ", ".join(segs)
    return txt + "."
