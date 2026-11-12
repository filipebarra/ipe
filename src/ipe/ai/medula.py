"""Medula e canal vertebral na RM: área e índices de compressão por nível — 0.100.26.

A segmentação é do **TotalSpineSeg** (NeuroPoly, Polytechnique Montréal; LGPL-3.0; nnU-Net em dois passos), que
devolve a medula, o canal, os discos e as vértebras já com o nome de cada nível, em qualquer contraste e
orientação. É um modelo extra, instalado uma vez no ambiente da segmentação.

As contas são do Ipê. A linha central da medula é o centro da máscara a cada 2 mm no eixo crânio-caudal,
suavizada; em cada nível o corte é **perpendicular à linha central**:

- **área** da medula (mm²), diâmetro **anteroposterior** (AP) e **transverso**, e a **razão de compressão**
  (AP ÷ transverso);
- diâmetro AP e área do **canal**, e a **ocupação** (área da medula ÷ área do canal);
- em cada disco, o **MSCC** (maximum spinal cord compression) e o **MCC** (maximum canal compromise) de
  Fehlings et al. (Spine 1999): 1 − d ÷ média(d acima, d abaixo), com d o diâmetro AP (da medula ou do canal) no
  disco e nos meios dos corpos vertebrais de cima e de baixo.

Os diâmetros e as áreas são a média de ±2 mm ao longo da medula. No disco vale o ponto de menor AP a até 3 mm
do centro do disco, quando ele é pelo menos 0,5 mm mais estreito que no centro. Cada disco vira um achado
revisável; nada é classificado: o número vai ao laudo só depois de conferido.

Em série sagital 2D (cortes de 3–4 mm), o diâmetro transverso e a área saem de poucos cortes: o programa avisa
que são aproximados; o AP, o MSCC e o MCC (definidos no plano sagital) continuam valendo.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from ipe.ai import achados as AC

log = logging.getLogger(__name__)

FERRAMENTA = "medula"
TITULO = "Medula e canal: área e compressão por nível (IA, TotalSpineSeg)"
MARCA = "· TotalSpineSeg"
DESC_SEG = f"Medula e canal {MARCA}"
SERIE_SEG = 989
MIN_CORTES = 8
MODALIDADES = ("MR",)
MOTIVO_MODALIDADE = "A medula é medida na RM da coluna."
MODELO = "TotalSpineSeg + cortes perpendiculares à medula"
MODELO_EXTRA = "medula"
CHAVE_SAIDA = "medula"
TIPO_RESUMO = "Medula: compressão por nível"
TIPO_NIVEL = "Medula: nível"

MEDULA, CANAL = 1, 2
DISCOS = {63: "C2-C3", 64: "C3-C4", 65: "C4-C5", 66: "C5-C6", 67: "C6-C7", 71: "C7-T1",
          **{72 + i: f"T{i + 1}-T{i + 2}" for i in range(11)},
          91: "T12-L1", 92: "L1-L2", 93: "L2-L3", 94: "L3-L4", 95: "L4-L5", 100: "L5-S1"}
VERTEBRAS = {**{11 + i: f"C{i + 1}" for i in range(7)}, **{21 + i: f"T{i + 1}" for i in range(12)},
             **{41 + i: f"L{i + 1}" for i in range(5)}, 50: "sacro"}
CORES = {MEDULA: (250, 210, 60), CANAL: (80, 170, 255)}
PASSO_MM = 1.0
BLOCO_MM = 2.0
PIXEL = 0.25
RAIO_MM = 22.0
PERTO_DISCO_MM = 3.0
LIMIAR_APERTO_MM = 0.5         # o corte vizinho só vale no lugar do do disco se for este tanto mais estreito
GROSSO_MM = 1.6               # acima disto no eixo direita-esquerda, área e transverso são aproximados
MIN_VOXELS = 30

CHAVE_AUTO = "medula.auto"
CHAVE_EXAME_CONTEM = "medula.exame_contem"
CHAVE_MODALIDADES = "medula.modalidades"
CHAVE_PRIOR_CT = "medula.prioridade"
CHAVE_ESPESSURA = "medula.espessura_max"
CHAVE_MIN_CORTES = "medula.min_cortes"
CHAVE_DESTINOS = "medula.destinos"
PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "COLUNA CERVICAL|CERVICAL|COLUNA|SPINE|MEDULA",
    CHAVE_MODALIDADES: ["MR"],
    CHAVE_PRIOR_CT: "3D T2|T2 3D|SPACE|CUBE|SAG T2|T2 SAG|S T2|T2|STIR|T1",
    CHAVE_ESPESSURA: 5.0,
    CHAVE_MIN_CORTES: MIN_CORTES,
    CHAVE_DESTINOS: [],
}
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_CT, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES,
          "excluir": ("ADC", "DWI", "DIF", "SCOUT", "LOCALIZER", "LOC", "MIP", "MIELO", "MYELO", "CALIBRA")}
NOME_CADIA = "Medula e canal (TotalSpineSeg)"
TITULO_CADIA = "Medula e canal: área, diâmetros e índices de compressão por nível (TotalSpineSeg)"
EXPLICACAO_CADIA = ("Na RM da coluna (de preferência o sagital T2): segmenta a medula, o canal, os discos e as "
                    "vértebras, e mede em cada disco, no plano perpendicular à medula, a área, os diâmetros AP e "
                    "transverso, a razão de compressão, o canal e os índices MSCC e MCC. Precisa do modelo extra "
                    "instalado. O resultado aparece em Aplicações ▸ Achados de IA, para conferir.")


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


def escolher_serie(repo, study_uid: str, settings=None):
    from ipe.ai import totalseg as TS
    return TS.escolher_serie(repo, study_uid, settings, PERFIL, config, min_absoluto=MIN_CORTES)


def ja_feita(repo, study_uid: str) -> bool:
    return bool(repo.achados(study_uid, FERRAMENTA))


def tarefas(modalidade: str = "MR", settings=None) -> list[dict]:
    return [{"nome": "totalspineseg", "rotulo": "medula, canal, discos e vértebras (TotalSpineSeg)"}]


# ------------------------------------------------------------------ geometria
def _pontos_mm(mascara: np.ndarray, vol) -> np.ndarray:
    idx = np.argwhere(mascara)                               # (k, j, i)
    return vol.origin + idx[:, ::-1].astype(float) @ np.asarray(vol.matrix(), float).T


def linha_central(medula: np.ndarray, vol) -> np.ndarray:
    """Pontos (mm do paciente, de cima para baixo) a cada PASSO_MM pelo centro da medula."""
    from ipe.ai.aorta import _reamostrar, _suavizar
    pts = _pontos_mm(medula, vol)
    if len(pts) < MIN_VOXELS:
        return np.zeros((0, 3))
    z = pts[:, 2]
    bloco = np.floor((z.max() - z) / BLOCO_MM).astype(int)   # 0 = o mais alto
    n = int(bloco.max()) + 1
    cont = np.bincount(bloco, minlength=n).astype(float)
    centros = np.column_stack([np.bincount(bloco, weights=pts[:, d], minlength=n) for d in range(3)])
    ok = cont >= max(3.0, 0.2 * np.median(cont[cont > 0]))
    if ok.sum() < 5:
        return np.zeros((0, 3))
    centros = centros[ok] / cont[ok, None]
    linha, _s = _reamostrar(_suavizar(centros, 5), PASSO_MM)
    return linha


def _base(tangente: np.ndarray):
    """(direita-esquerda, anteroposterior) no plano perpendicular à tangente, em LPS: +x esquerda, +y posterior."""
    t = np.asarray(tangente, float)
    t = t / max(np.linalg.norm(t), 1e-9)
    x = np.array([1.0, 0.0, 0.0])
    rl = x - (x @ t) * t
    rl /= max(np.linalg.norm(rl), 1e-9)
    ap = np.cross(t, rl)
    if ap[1] < 0:
        ap = -ap
    return rl, ap


def secao(mascara_f: np.ndarray, vol, centro, tangente) -> dict | None:
    """Área e diâmetros AP / transverso (pelo meio) do pedaço da máscara que contém o centro, no plano
    perpendicular."""
    from ipe.imaging.estruturas import rotular
    from ipe.imaging.volume import sample_trilinear
    rl, ap = _base(tangente)
    n = int(RAIO_MM / PIXEL)
    a = np.arange(-n, n + 1) * PIXEL
    A, B = np.meshgrid(a, a, indexing="ij")                  # A ao longo de RL, B ao longo de AP
    P = np.asarray(centro, float)[None, None] + A[..., None] * rl + B[..., None] * ap
    ijk = (P - vol.origin) @ np.linalg.inv(np.asarray(vol.matrix(), float)).T
    m = np.nan_to_num(sample_trilinear(mascara_f, ijk)) >= 0.5
    if not m.any():
        return None
    r, _q = rotular(m)
    c = r[n, n]
    if c == 0:
        idx = np.argwhere(r > 0)
        c = r[tuple(idx[np.argmin(((idx - n) ** 2).sum(axis=1))])]
    pe = r == c
    xa, xb = A[pe], B[pe]
    c_rl, c_ap = float(xa.mean()), float(xb.mean())
    # diâmetros pelo meio (faixa de ±1 mm): a média da largura na faixa não pula de pixel em pixel como a extensão
    faixa_ap = pe & (np.abs(A - c_rl) <= 1.0)
    faixa_rl = pe & (np.abs(B - c_ap) <= 1.0)
    col = faixa_ap.sum(axis=1)                               # pixels ao longo de AP, por coluna RL
    lin = faixa_rl.sum(axis=0)
    ap_mm = float(col[col > 0].mean() * PIXEL) if (col > 0).any() else float(xb.max() - xb.min() + PIXEL)
    rl_mm = float(lin[lin > 0].mean() * PIXEL) if (lin > 0).any() else float(xa.max() - xa.min() + PIXEL)
    bm = B[faixa_ap] if faixa_ap.any() else xb
    return {"area": float(pe.sum() * PIXEL ** 2), "rl": rl_mm, "ap": ap_mm,
            "p_ant": (np.asarray(centro, float) + c_rl * rl + float(bm.min()) * ap).tolist(),
            "p_post": (np.asarray(centro, float) + c_rl * rl + float(bm.max()) * ap).tolist(),
            "centro": (np.asarray(centro, float) + c_rl * rl + c_ap * ap).tolist()}


@dataclass
class Nivel:
    nome: str                       # "C5-C6" (disco) ou "C5" (meio do corpo)
    disco: bool
    s: float                        # mm ao longo da linha, a partir do alto
    centro: list
    area: float | None = None
    ap: float | None = None
    rl: float | None = None
    canal_ap: float | None = None
    canal_area: float | None = None
    mscc: float | None = None
    mcc: float | None = None
    linha_ap: tuple | None = None   # (ponto anterior, ponto posterior) da medula, mm

    @property
    def razao(self) -> float | None:
        return None if not self.ap or not self.rl else self.ap / self.rl

    @property
    def ocupacao(self) -> float | None:
        return None if not self.area or not self.canal_area else 100.0 * self.area / self.canal_area


@dataclass
class Resultado:
    niveis: list = field(default_factory=list)            # discos e meios de corpo, de cima para baixo
    comprimento: float = 0.0
    aproximado: bool = False                               # área e transverso de poucos cortes
    rotulos: np.ndarray | None = None                      # recorte: 1 medula, 2 canal (sem a medula)
    offset: tuple = (0, 0, 0)
    avisos: list = field(default_factory=list)
    elegibilidade: str = ""
    versao: str = ""
    series_uid: str = ""
    calculado: bool = False

    def discos(self) -> list:
        return [n for n in self.niveis if n.disco and n.ap]

    def pior(self):
        d = [n for n in self.discos() if n.mscc is not None]
        return max(d, key=lambda n: n.mscc) if d else None


def _medir_em(linha, tg, k, medula_f, canal_f, vol) -> dict | None:
    sm = secao(medula_f, vol, linha[k], tg[k])
    if sm is None:
        return None
    sc = secao(canal_f, vol, linha[k], tg[k])
    return {"k": k, "m": sm, "c": sc}


def calcular(t, rotulos: dict, settings=None) -> Resultado:
    from ipe.ai.aorta import _tangentes
    vol = t.vol
    res = Resultado(versao=getattr(t, "versao", ""), series_uid=t.series_uid)
    desc = t.descricao_serie or t.series_uid[-8:]
    lab = rotulos.get("totalspineseg", (None, {}))[0]
    if lab is None:
        res.avisos.append("o TotalSpineSeg não devolveu a segmentação")
        return res
    lab = np.asarray(lab)
    medula = lab == MEDULA
    canal = medula | (lab == CANAL)
    M = np.asarray(vol.matrix(), float)
    passo_rl = float(np.linalg.norm(M[:, int(np.argmax(np.abs(M[0])))]))     # mm por voxel no eixo direita-esquerda
    res.aproximado = passo_rl > GROSSO_MM
    res.elegibilidade = (f"RM, série “{desc}”, {vol.data.shape[0]} cortes de {abs(vol.dz):.1f} mm"
                         .replace(".", ","))
    linha = linha_central(medula, vol)
    if len(linha) < 10:
        res.avisos.append("a medula não foi achada nesta série")
        return res
    res.calculado = True
    res.comprimento = float(len(linha) - 1) * PASSO_MM
    tg = _tangentes(linha, 4)
    medula_f, canal_f = medula.astype(np.float32), canal.astype(np.float32)

    def indice(centro) -> tuple[int, float]:
        d = np.linalg.norm(linha - np.asarray(centro, float)[None], axis=1)
        k = int(np.argmin(d))
        return k, float(d[k])

    cache: dict[int, dict | None] = {}

    def medir(k: int):
        if k not in cache:
            cache[k] = _medir_em(linha, tg, k, medula_f, canal_f, vol)
        return cache[k]

    janela = int(round(PERTO_DISCO_MM / PASSO_MM))
    marcos = []
    for cod, nome in list(DISCOS.items()) + list(VERTEBRAS.items()):
        m = lab == cod
        if int(m.sum()) < MIN_VOXELS or nome == "sacro":
            continue
        centro = _pontos_mm(m, vol).mean(axis=0)
        k, dist = indice(centro)
        if dist > 60.0 or k <= 1 or k >= len(linha) - 2:        # nível fora do trecho de medula da série
            continue
        marcos.append((k, cod in DISCOS, nome))
    def suave(k: int) -> dict | None:
        """A medida em k com os diâmetros e as áreas na média de ±2 mm (tira o degrau dos voxels)."""
        viz = [medir(q) for q in range(max(0, k - 2), min(len(linha), k + 3))]
        viz = [v for v in viz if v is not None]
        centro = medir(k)
        if centro is None or len(viz) < 3:
            return None
        out = {"k": k, "m": dict(centro["m"]), "c": dict(centro["c"]) if centro["c"] else None}
        for chave in ("ap", "rl", "area"):
            out["m"][chave] = float(np.mean([v["m"][chave] for v in viz]))
            com_canal = [v["c"][chave] for v in viz if v["c"]]
            if out["c"] is not None and com_canal:
                out["c"][chave] = float(np.mean(com_canal))
        return out

    for k, e_disco, nome in sorted(marcos):
        esc = suave(k)
        if e_disco and esc is not None:
            # o ponto de maior aperto pode estar a alguns mm do centro do disco: vale se for de fato mais estreito
            cand = [suave(q) for q in range(max(0, k - janela), min(len(linha), k + janela + 1))]
            cand = [c for c in cand if c is not None]
            if cand:
                menor = min(cand, key=lambda c: c["m"]["ap"])
                if menor["m"]["ap"] < esc["m"]["ap"] - LIMIAR_APERTO_MM:
                    esc = menor
        if esc is None:
            continue
        sm, sc = esc["m"], esc["c"]
        res.niveis.append(Nivel(nome, e_disco, float(esc["k"]) * PASSO_MM, sm["centro"], sm["area"], sm["ap"],
                                sm["rl"], sc["ap"] if sc else None, sc["area"] if sc else None,
                                linha_ap=(sm["p_ant"], sm["p_post"])))
    corpos = {n.nome: n for n in res.niveis if not n.disco}
    for n in res.niveis:
        if not n.disco:
            continue
        cima, baixo = (n.nome.split("-") + [""])[:2]
        a, b = corpos.get(cima), corpos.get(baixo if baixo != "S1" else "sacro")
        if a and b and a.ap and b.ap and n.ap:
            n.mscc = 100.0 * (1.0 - n.ap / ((a.ap + b.ap) / 2.0))
            if a.canal_ap and b.canal_ap and n.canal_ap:
                n.mcc = 100.0 * (1.0 - n.canal_ap / ((a.canal_ap + b.canal_ap) / 2.0))
    if not res.discos():
        res.avisos.append("nenhum disco com a medula ao lado foi identificado nesta série")
    if res.aproximado:
        res.avisos.append(f"cortes de {passo_rl:.1f} mm no eixo direita-esquerda: a área, o diâmetro transverso e a "
                          f"razão de compressão são aproximados (o AP, o MSCC e o MCC valem)".replace(".", ",", 1))
    res.avisos.append("confira o nome dos níveis e o contorno da medula na imagem antes de usar os números")
    seg = np.zeros(lab.shape, np.uint8)
    seg[canal] = 2
    seg[medula] = 1
    kk, jj, ii = np.nonzero(seg)
    if kk.size:
        a, b, c = kk.min(), jj.min(), ii.min()
        res.rotulos = seg[a:kk.max() + 1, b:jj.max() + 1, c:ii.max() + 1].copy()
        res.offset = (int(a), int(b), int(c))
    return res


# ------------------------------------------------------------------ banco, SEG e texto
def _n(v, u, n, casas=1):
    return AC.numero(None if v is None else round(float(v), casas), u, n)


def itens_para_o_banco(res: Resultado, t, versao: str) -> list[dict]:
    if not res.calculado:
        return []
    eleg = res.elegibilidade + (". Atenção: " + "; ".join(res.avisos) if res.avisos else "")
    base = {"series_uid": t.series_uid, "modelo": MODELO, "versao": versao or res.versao, "elegibilidade": eleg}
    discos = res.discos()
    pior = res.pior()
    menor = min(discos, key=lambda n: n.ap) if discos else None
    itens = [{**base, "rotulo": "M", "tipo": TIPO_RESUMO, "local": "medula",
              "posicao": (pior or menor).centro if (pior or menor) else None,
              "numeros": {"n_niveis": _n(len(discos), "", "Discos medidos", 0),
                          "mscc_max": _n(pior.mscc if pior else None, "%", "Maior MSCC"),
                          "ap_min": _n(menor.ap if menor else None, "mm", "Menor AP da medula"),
                          "comprimento": _n(res.comprimento, "mm", "Medula na série", 0)},
              "elegibilidade": eleg + (f". Maior MSCC em {pior.nome}" if pior else "")
              + (f"; menor AP em {menor.nome}" if menor else "")}]
    for n in discos:
        itens.append({**base, "rotulo": n.nome, "tipo": TIPO_NIVEL, "local": n.nome, "posicao": n.centro,
                      "numeros": {"area": _n(n.area, "mm²", "Área da medula"), "ap": _n(n.ap, "mm", "AP da medula"),
                                  "rl": _n(n.rl, "mm", "Transverso da medula"),
                                  "razao": _n(n.razao, "", "Razão de compressão (AP/transverso)", 2),
                                  "canal_ap": _n(n.canal_ap, "mm", "AP do canal"),
                                  "ocupacao": _n(n.ocupacao, "%", "Ocupação do canal pela medula", 0),
                                  "mscc": _n(n.mscc, "%", "MSCC", 0), "mcc": _n(n.mcc, "%", "MCC", 0)}})
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
                log.exception("trocar a SEG da medula anterior")
    out = {"series": [], "ferramenta": FERRAMENTA}
    if res.rotulos is not None and (res.rotulos > 0).any():
        vol = t.vol
        segs = [(SimpleNamespace(mask=res.rotulos == cod, offset=res.offset), nome, CORES[cod])
                for cod, nome in ((MEDULA, "Medula"), (CANAL, "Canal (líquor)")) if (res.rotulos == cod).any()]
        ds = build_seg(vol, segs, vol.source_path, frames=t.frames, series_number=SERIE_SEG, description=DESC_SEG,
                       algoritmo=("AUTOMATIC", f"TotalSpineSeg {versao}".strip()))
        tmp = Path(tempfile.mkdtemp(prefix="ipe_medula_"))
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
    discos = res.discos()
    if not discos:
        return res.avisos[0] if res.avisos else "sem medidas"
    txt = f"{len(discos)} discos medidos ({discos[0].nome} a {discos[-1].nome})"
    pior = res.pior()
    if pior is not None:
        txt += f"; maior MSCC {_f(pior.mscc, 0)}% em {pior.nome} (AP da medula {_f(pior.ap)} mm)"
    return txt


def n_itens(res: Resultado) -> int:
    return (1 + len(res.discos())) if res.calculado else 0


def mensagem(res: Resultado, minutos: float) -> str:
    msg = (f"Medula pronta em {minutos:.1f} min — {resumo(res)}. Cada nível está em Aplicações ▸ Achados de IA, para "
           f"conferir; a medula e o canal estão na série “{DESC_SEG}”.")
    if res.avisos:
        msg += "\n\nConfira: " + "; ".join(res.avisos) + "."
    return msg


def frase(a: dict) -> str:
    n = AC.numeros_validos(a)

    def v(k, casas=1):
        x = (n.get(k) or {}).get("v")
        return None if x is None else _f(x, casas)
    if a.get("tipo") == TIPO_NIVEL:
        partes = []
        if v("ap"):
            partes.append(f"medula com {v('ap')} mm no anteroposterior")
        if v("area"):
            partes.append(f"área de {v('area', 0)} mm²")
        if v("razao", 2):
            partes.append(f"razão de compressão {v('razao', 2)}")
        if v("canal_ap"):
            partes.append(f"canal com {v('canal_ap')} mm")
        if v("mscc", 0):
            partes.append(f"MSCC {v('mscc', 0)}%")
        if v("mcc", 0):
            partes.append(f"MCC {v('mcc', 0)}%")
        return f"{a.get('local') or a.get('rotulo')}: " + ", ".join(partes) + "."
    if not v("n_niveis", 0) or v("n_niveis", 0) == "0":
        return "Medula não medida pela segmentação automática."
    txt = f"Medula e canal medidos em {v('n_niveis', 0)} níveis, no plano perpendicular ao eixo da medula"
    if v("mscc_max", 0):
        txt += f"; maior compressão medular (MSCC) de {v('mscc_max', 0)}%"
    if v("ap_min"):
        txt += f"; menor diâmetro anteroposterior da medula de {v('ap_min')} mm"
    return txt + "."


def laudo(achados: list[dict]) -> str:
    """O resumo e depois os níveis, de cima para baixo."""
    valem = [a for a in achados if a.get("estado") in AC.VALEM]
    if not valem:
        return ""
    ordem = {nome: i for i, nome in enumerate(DISCOS.values())}
    valem.sort(key=lambda a: (-1 if a.get("tipo") == TIPO_RESUMO else ordem.get(a.get("local") or "", 999)))
    return "\n".join(f"- {frase(a)}" for a in valem)
