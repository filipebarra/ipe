"""Níveis linfonodais cervicais na TC (0.99.20, etapa da neuro / cabeça e pescoço).

O TotalSegmentator (tarefas abertas, só TC) acha os marcos; daqui sai um **mapa de níveis** (I a VII,
direita e esquerda) pelas regras de imagem da classificação usada no estadiamento (Som et al., 1999;
AJCC). O mapa aparece como rótulo ("IIA D") em qualquer plano, e a lesão segmentada com a ferramenta
Segmentar ganha o nível sozinha.

| marco | de onde | limite |
|---|---|---|
| base do crânio | `skull` (total) | alto do nível II/V |
| corpo do hioide (borda de baixo) | `hyoid` | II/III; I acima |
| cricoide (borda de baixo) | `cricoid_cartilage` | III/IV; VA/VB |
| clavícula | `clavicula_*` (total) | IV/VB embaixo |
| manúbrio (topo) | `sternum` (total) | VI/VII |
| borda posterior da submandibular | `submandibular_gland_*` | I/II |
| barriga anterior do digástrico | `digastric_*` (head_muscles) | IA/IB |
| borda medial da carótida | `common_carotid_*` (total), `internal_carotid_*` | VI e retrofaríngeo (medial) × II–IV |
| borda posterior do esternocleidomastóideo | `sternocleidomastoid_*` (headneck_muscles) | II–IV × V |
| borda posterior da jugular interna | `internal_jugular_vein_*` | IIA × IIB |

Coordenadas do paciente (mm, LPS: +x esquerda, +y posterior, +z superior). Os limites que mudam com
a altura (carótida, esternocleidomastóideo, jugular) são guardados a cada milímetro; onde o marco não
aparece, vale o mais próximo. Tudo é proposta: o nível sai com a regra que o decidiu.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

import numpy as np

from ipe.ai import cefalometria as CF

log = logging.getLogger(__name__)

MARCA = "· TotalSegmentator"
DESC_SEG = f"Níveis linfonodais {MARCA}"
SERIE_SEG = 980
MIN_CORTES = 40
FONTE_OVERLAY = "Níveis linfonodais"
GRUPO_PRIVADO, CRIADOR = 0x0071, "IPE LINFONODOS"
LADOS = ("D", "E")
NOME_LADO = {"D": "direito", "E": "esquerdo"}

#: estruturas usadas (tarefa, nome na tela, cor) — vão para a SEG de conferência
ESTRUTURAS = {
    "hyoid": ("headneck_bones_vessels", "Hioide", (255, 220, 80)),
    "cricoid_cartilage": ("headneck_bones_vessels", "Cricoide", (255, 180, 80)),
    "thyroid_cartilage": ("headneck_bones_vessels", "Cartilagem tireoide", (255, 200, 120)),
    "internal_carotid_artery_right": ("headneck_bones_vessels", "Carótida interna D", (230, 60, 60)),
    "internal_carotid_artery_left": ("headneck_bones_vessels", "Carótida interna E", (230, 60, 60)),
    "internal_jugular_vein_right": ("headneck_bones_vessels", "Jugular interna D", (80, 110, 230)),
    "internal_jugular_vein_left": ("headneck_bones_vessels", "Jugular interna E", (80, 110, 230)),
    "sternocleidomastoid_right": ("headneck_muscles", "Esternocleidomastóideo D", (200, 120, 110)),
    "sternocleidomastoid_left": ("headneck_muscles", "Esternocleidomastóideo E", (200, 120, 110)),
    "submandibular_gland_right": ("head_glands_cavities", "Submandibular D", (240, 170, 220)),
    "submandibular_gland_left": ("head_glands_cavities", "Submandibular E", (240, 170, 220)),
    "common_carotid_artery_right": ("total", "Carótida comum D", (230, 60, 60)),
    "common_carotid_artery_left": ("total", "Carótida comum E", (230, 60, 60)),
}
NIVEIS = ("IA", "IB", "IIA", "IIB", "III", "IV", "VA", "VB", "VI", "VII", "RF")
NOME_NIVEL = {"RF": "retrofaríngeo"}
CORES = {"IA": (255, 230, 120), "IB": (255, 200, 90), "IIA": (120, 220, 255), "IIB": (90, 170, 255),
         "III": (140, 255, 160), "IV": (90, 210, 120), "VA": (255, 150, 200), "VB": (230, 110, 170),
         "VI": (210, 170, 255), "VII": (170, 130, 240), "RF": (200, 200, 200)}

# Preferências ▸ CAD/IA ▸ Níveis linfonodais
CHAVE_AUTO = "linfonodos.auto"
CHAVE_EXAME_CONTEM = "linfonodos.exame_contem"
CHAVE_MODALIDADES = "linfonodos.modalidades"
CHAVE_PRIOR_CT = "linfonodos.prioridade_ct"
CHAVE_ESPESSURA = "linfonodos.espessura_max"
CHAVE_MIN_CORTES = "linfonodos.min_cortes"
CHAVE_DESTINOS = "linfonodos.destinos"
PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "PESCOCO|CERVICAL|NECK|LARING|FARING|TIREOIDE|TIROIDE|PAROTIDA|CAVIDADE ORAL|ORAL",
    CHAVE_MODALIDADES: ["CT"],
    CHAVE_PRIOR_CT: "PARTES MOLES|PARTES|SOFT|STD|STANDARD|VENOSA|AX|AXIAL",
    CHAVE_ESPESSURA: 3.0,
    CHAVE_MIN_CORTES: MIN_CORTES,
    CHAVE_DESTINOS: [],
}
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_CT, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES}


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
        {"nome": "headneck_bones_vessels", "rotulo": "hioide, cricoide, carótidas e jugulares", "linfo": True},
        {"nome": "headneck_muscles", "rotulo": "esternocleidomastóideos", "linfo": True},
        {"nome": "head_glands_cavities", "rotulo": "glândulas submandibulares", "linfo": True},
        {"nome": "head_muscles", "rotulo": "digástricos", "linfo": True},
        {"nome": "total", "roi": ["skull", "sternum", "clavicula_left", "clavicula_right",
                                  "common_carotid_artery_left", "common_carotid_artery_right"],
         "fast": True, "rotulo": "crânio, esterno, clavículas e carótidas comuns", "linfo": True},
    ]


# ------------------------------------------------------------------ os marcos
@dataclass
class Marcos:
    xm: float = 0.0
    z_cranio: float | None = None          # base do crânio (alto do II e do V)
    z_hioide: float | None = None          # borda de baixo do corpo do hioide
    z_cricoide: float | None = None        # borda de baixo da cricoide
    z_manubrio: float | None = None        # topo do manúbrio
    z_clav: dict = field(default_factory=dict)      # lado -> z da clavícula
    y_smg: dict = field(default_factory=dict)       # lado -> borda posterior da submandibular
    d_dig: float = 10.0                    # distância da borda medial do digástrico anterior ao meio
    z0: float = 0.0                        # alturas das tabelas: z0, z0 + 1, …
    car_med: dict = field(default_factory=dict)     # lado -> [distância da borda medial da carótida ao meio]
    scm_post: dict = field(default_factory=dict)    # lado -> [y da borda posterior do ECM]
    ijv_post: dict = field(default_factory=dict)    # lado -> [y da borda posterior da jugular]
    avisos: list = field(default_factory=list)

    # -------------------------------------------------------------- tabela por altura
    def _tab(self, tab: dict, lado: str, z: np.ndarray, padrao: float) -> np.ndarray:
        v = tab.get(lado)
        if not v:
            return np.full(np.shape(z), padrao, float)
        a = np.asarray(v, float)
        i = np.clip(np.round(np.asarray(z, float) - self.z0).astype(int), 0, len(a) - 1)
        return a[i]

    def para_dict(self) -> dict:
        d = self.__dict__.copy()
        return json.loads(json.dumps(d, default=float))

    @classmethod
    def de_dict(cls, d: dict) -> "Marcos":
        m = cls()
        for k, v in (d or {}).items():
            if hasattr(m, k):
                setattr(m, k, v)
        return m


def _preencher(valores: dict, z0: int, n: int) -> list | None:
    """{z inteiro: valor} -> lista de n alturas, cada buraco com o valor mais próximo."""
    if not valores:
        return None
    zs = np.array(sorted(valores), float)
    vs = np.array([valores[int(z)] for z in zs], float)
    alvo = np.arange(z0, z0 + n, dtype=float)
    idx = np.abs(alvo[:, None] - zs[None, :]).argmin(axis=1)
    return [round(float(x), 2) for x in vs[idx]]


def marcos(vol, rotulos: dict) -> Marcos:
    ms = CF.Mascaras(vol, rotulos)
    m = Marcos()
    P = {}
    for nome in ("hyoid", "cricoid_cartilage", "thyroid_cartilage", "skull", "sternum", "clavicula_left",
                 "clavicula_right", "submandibular_gland_left", "submandibular_gland_right", "digastric_left",
                 "digastric_right", "sternocleidomastoid_left", "sternocleidomastoid_right",
                 "internal_carotid_artery_left", "internal_carotid_artery_right", "common_carotid_artery_left",
                 "common_carotid_artery_right", "internal_jugular_vein_left", "internal_jugular_vein_right",
                 "trachea"):
        mk = ms.get(nome)
        if mk is not None:
            p = CF.pontos(vol, mk)
            if len(p) > 200_000:
                p = p[:: len(p) // 200_000 + 1]
            P[nome] = p
    meio = [P[n][:, 0] for n in ("hyoid", "cricoid_cartilage", "thyroid_cartilage", "trachea") if n in P]
    if meio:
        m.xm = float(np.median(np.concatenate(meio)))
    else:
        cc = [P[n][:, 0].mean() for n in ("sternocleidomastoid_left", "sternocleidomastoid_right") if n in P]
        m.xm = float(np.mean(cc)) if len(cc) == 2 else 0.0
        m.avisos.append("sem hioide nem cartilagens: o meio do pescoço foi estimado")
    xm = m.xm
    if "hyoid" in P:
        corpo = P["hyoid"][np.abs(P["hyoid"][:, 0] - xm) <= 10]
        m.z_hioide = float((corpo if len(corpo) else P["hyoid"])[:, 2].min())
    else:
        m.avisos.append("hioide não segmentado")
    if "cricoid_cartilage" in P:
        m.z_cricoide = float(P["cricoid_cartilage"][:, 2].min())
    else:
        m.avisos.append("cricoide não segmentada")
    # base do crânio (0.99.21): no primeiro caso real o "skull" do TotalSegmentator trouxe a mandíbula, e o
    # mínimo dele caiu 9 mm acima do hioide — o nível II quase sumiu. O topo das jugulares internas (forame
    # jugular) e das carótidas internas (canal carotídeo) é a base do crânio que interessa ao nível II.
    topos = [float(P[n][:, 2].max()) for n in ("internal_jugular_vein_left", "internal_jugular_vein_right")
             if n in P]
    if not topos:
        topos = [float(P[n][:, 2].max()) for n in ("internal_carotid_artery_left", "internal_carotid_artery_right")
                 if n in P]
    if topos:
        m.z_cranio = float(np.mean(topos))
    elif "skull" in P:
        sk = P["skull"]
        if "hyoid" in P:                                   # só a parte de trás (occipital, mastoide): sem a mandíbula
            sk = sk[sk[:, 1] > float(np.median(P["hyoid"][:, 1])) + 20]
        if len(sk):
            m.z_cranio = float(sk[:, 2].min())
            m.avisos.append("base do crânio estimada pelo crânio (sem as jugulares)")
    if "sternum" in P:
        m.z_manubrio = float(P["sternum"][:, 2].max())
    for lado, sufixo in (("D", "right"), ("E", "left")):
        if f"clavicula_{sufixo}" in P:
            m.z_clav[lado] = float(np.median(P[f"clavicula_{sufixo}"][:, 2]))
        if f"submandibular_gland_{sufixo}" in P:
            m.y_smg[lado] = float(P[f"submandibular_gland_{sufixo}"][:, 1].max())
    dig = []
    for sufixo in ("left", "right"):
        if f"digastric_{sufixo}" in P and m.z_hioide is not None:
            d = P[f"digastric_{sufixo}"]
            ant = d[d[:, 1] <= np.percentile(d[:, 1], 30)]          # a barriga anterior: a parte da frente
            if len(ant):
                dig.append(float(np.abs(ant[:, 0] - xm).min()))
    if dig:
        m.d_dig = float(np.mean(dig))
    # tabelas por altura (1 mm)
    todos = np.concatenate(list(P.values())) if P else np.zeros((0, 3))
    if not len(todos):
        m.avisos.append("nenhum marco do pescoço segmentado")
        return m
    z0 = int(np.floor(todos[:, 2].min()))
    n = int(np.ceil(todos[:, 2].max())) - z0 + 1
    m.z0 = float(z0)
    for lado, sufixo in (("D", "right"), ("E", "left")):
        car = {}
        for nome in (f"common_carotid_artery_{sufixo}", f"internal_carotid_artery_{sufixo}"):
            if nome in P:
                p = P[nome]
                for z in np.unique(np.round(p[:, 2]).astype(int)):
                    q = p[np.round(p[:, 2]).astype(int) == z]
                    d = float(np.abs(q[:, 0] - xm).min())
                    car[int(z)] = min(car.get(int(z), 1e9), d)
        scm, ijv = {}, {}
        if f"sternocleidomastoid_{sufixo}" in P:
            p = P[f"sternocleidomastoid_{sufixo}"]
            for z in np.unique(np.round(p[:, 2]).astype(int)):
                scm[int(z)] = float(p[np.round(p[:, 2]).astype(int) == z][:, 1].max())
        if f"internal_jugular_vein_{sufixo}" in P:
            p = P[f"internal_jugular_vein_{sufixo}"]
            for z in np.unique(np.round(p[:, 2]).astype(int)):
                ijv[int(z)] = float(p[np.round(p[:, 2]).astype(int) == z][:, 1].max())
        m.car_med[lado] = _preencher(car, z0, n)
        m.scm_post[lado] = _preencher(scm, z0, n)
        m.ijv_post[lado] = _preencher(ijv, z0, n)
        if not car:
            m.avisos.append(f"carótida do lado {NOME_LADO[lado]} não segmentada")
        if not scm:
            m.avisos.append(f"esternocleidomastóideo {NOME_LADO[lado]} não segmentado")
    return m


# ------------------------------------------------------------------ a regra
def classificar(pts, m: Marcos) -> list[tuple[str, str, str]]:
    """[(nível, lado, regra)] de cada ponto (mm). Nível "" = fora dos níveis cervicais. Vetorizado: o
    mapa do pescoço inteiro passa por aqui (centenas de milhares de pontos)."""
    p = np.atleast_2d(np.asarray(pts, float))
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    n = len(p)
    esq = x > m.xm
    lado = np.where(esq, "E", "D").astype(object)
    dx = np.abs(x - m.xm)

    def tab(t, padrao):
        return np.where(esq, m._tab(t, "E", z, padrao), m._tab(t, "D", z, padrao))
    car = tab(m.car_med, 15.0)
    scm = tab(m.scm_post, 1e9)
    ijv = tab(m.ijv_post, 1e9)              # sem a jugular: tudo IIA (há aviso)
    piso = m.z_manubrio if m.z_manubrio is not None else -1e9
    z_clav = np.where(esq, m.z_clav.get("E", piso), m.z_clav.get("D", piso))
    y_smg = np.where(esq, m.y_smg.get("E", -1e9), m.y_smg.get("D", -1e9))
    hi = m.z_hioide if m.z_hioide is not None else -1e9
    cr = m.z_cricoide if m.z_cricoide is not None else -1e9
    nivel = np.array([""] * n, dtype=object)
    regra = np.array([""] * n, dtype=object)
    livre = np.ones(n, bool)

    def marca(cond, nv, rg):
        sel = livre & cond
        nivel[sel], regra[sel] = nv, rg
        livre[sel] = False
    if m.z_cranio is not None:
        marca(z > m.z_cranio, "", "acima da base do crânio")
    if m.z_manubrio is not None:
        abaixo = z < m.z_manubrio
        marca(abaixo & (dx < car), "VII", "abaixo do topo do manúbrio, medial às carótidas")
        marca(abaixo, "", "abaixo do pescoço")
    post = (y > scm) & (z >= z_clav)
    marca(post & (z < cr), "VB", "posterior ao esternocleidomastóideo, abaixo da cricoide")
    marca(post, "VA", "posterior ao esternocleidomastóideo, acima da cricoide")
    acima = z >= hi
    frente_smg = acima & (y <= y_smg)
    marca(frente_smg & (dx < m.d_dig), "IA", "acima do hioide, entre as barrigas anteriores dos digástricos")
    marca(frente_smg, "IB", "acima do hioide, à frente da borda posterior da submandibular")
    medial = dx < car
    marca(medial & acima, "RF", "acima do hioide, medial à carótida")
    marca(medial, "VI", "entre as carótidas, do hioide ao manúbrio")
    marca(acima & (y <= ijv), "IIA", "do hioide à base do crânio, à frente da borda posterior da jugular")
    marca(acima, "IIB", "do hioide à base do crânio, atrás da jugular")
    marca(z >= cr, "III", "entre o hioide e a cricoide")
    marca(z >= z_clav, "IV", "entre a cricoide e a clavícula")
    marca(np.ones(n, bool), "", "abaixo da clavícula")
    return list(zip(nivel.tolist(), lado.tolist(), regra.tolist()))


def nome_do_nivel(nivel: str, lado: str) -> str:
    if not nivel:
        return "fora dos níveis cervicais"
    base = NOME_NIVEL.get(nivel, f"nível {nivel}")
    return f"{base} {NOME_LADO[lado]}"


def rotulo(nivel: str, lado: str) -> str:
    return f"{nivel} {lado}" if nivel else ""


# ------------------------------------------------------------------ o mapa (rótulos em qualquer plano)
def mapa(m: Marcos, vol=None, passo: float = 2.5) -> list:
    """MaskVolumes "só rótulo" de cada nível e lado, numa grade grossa em volta do pescoço. Com `vol`
    (a TC), a grade fica só dentro do corpo (o ar de fora não leva rótulo)."""
    from ipe.imaging import overlays as O
    zs = [v for v in (m.z_cranio, m.z_hioide, m.z_cricoide, m.z_manubrio, *m.z_clav.values()) if v is not None]
    if not zs or m.z_hioide is None:
        return []
    z_top = m.z_cranio if m.z_cranio is not None else m.z_hioide + 50
    z_bot = (m.z_manubrio - 30) if m.z_manubrio is not None else min(zs) - 10
    ys = [v for lst in (*m.scm_post.values(), *m.ijv_post.values()) if lst for v in lst] + list(m.y_smg.values())
    if not ys:
        return []
    y0, y1 = min(ys) - 60.0, max(ys) + 40.0
    gx = np.arange(m.xm - 90, m.xm + 90 + 1e-6, passo)
    gy = np.arange(y0, y1 + 1e-6, passo)
    gz = np.arange(z_bot, z_top + 1e-6, passo)
    Z, Y, X = np.meshgrid(gz, gy, gx, indexing="ij")
    P = np.stack([X, Y, Z], -1).reshape(-1, 3)
    dentro = np.ones(len(P), bool)
    if vol is not None:
        Mv = np.asarray(vol.matrix(), float)
        ijk = np.rint((P - np.asarray(vol.origin, float)) @ np.linalg.inv(Mv).T).astype(int)
        nk, nj, ni = vol.data.shape
        ok = (ijk[:, 0] >= 0) & (ijk[:, 0] < ni) & (ijk[:, 1] >= 0) & (ijk[:, 1] < nj) & (ijk[:, 2] >= 0) & \
             (ijk[:, 2] < nk)
        hu = np.full(len(P), -1000.0)
        q = ijk[ok]
        hu[ok] = vol.data[q[:, 2], q[:, 1], q[:, 0]]
        dentro = (hu > -250) & (hu < 250)                 # partes moles: nem ar, nem osso
    niveis = np.array([""] * len(P), dtype=object)
    lados = np.array([""] * len(P), dtype=object)
    idx = np.nonzero(dentro)[0]
    for i, (nv, ld, _r) in zip(idx, classificar(P[idx], m)):
        niveis[i], lados[i] = nv, ld
    forma = Z.shape
    origem = np.array([gx[0], gy[0], gz[0]])
    matriz = np.diag([passo, passo, passo])
    out = []
    for nv in NIVEIS:
        for ld in LADOS:
            sel = ((niveis == nv) & (lados == ld)).reshape(forma)
            if sel.sum() < 4:
                continue
            mv = O.MaskVolume(sel, origem, matriz, CORES.get(nv, (220, 220, 220)), rotulo(nv, ld))
            mv.so_rotulo = True
            out.append(mv)
    return out


def objeto(m: Marcos, study_uid: str = "", vol=None, volumes: list | None = None):
    from ipe.imaging import overlays as O
    obj = O.OverlayObject(f"linfonodos:{study_uid}", FONTE_OVERLAY, "mapa dos níveis", (140, 255, 160),
                          study_uid=study_uid)
    obj.volumes = volumes if volumes is not None else mapa(m, vol)
    obj.findings = [f"{a}" for a in m.avisos]
    obj.marcos = m
    return obj


# ------------------------------------------------------------------ guardar na SEG e ler de volta
def para_json(m: Marcos, volumes: list | None = None) -> str:
    """Os marcos e, se houver, o mapa já recortado no corpo (para reabrir sem a TC montada)."""
    mapa_ = [{"rotulo": mv.label, "cor": list(mv.color), "meta": mv.para_meta()} for mv in (volumes or [])]
    return json.dumps({"versao": 1, "marcos": m.para_dict(), "mapa": mapa_}, ensure_ascii=True)


def de_json(texto: str) -> Marcos:
    return Marcos.de_dict(json.loads(texto).get("marcos") or {})


def mapa_do_json(texto: str) -> list:
    from ipe.imaging import overlays as O
    out = []
    for d in json.loads(texto).get("mapa") or []:
        mv = O.MaskVolume.da_meta(d["meta"], tuple(d.get("cor") or (200, 200, 200)), d.get("rotulo", ""))
        mv.so_rotulo = True
        out.append(mv)
    return out


def ler_do_exame(repo, study_uid: str, com_mapa: bool = False):
    """Os marcos guardados na SEG do exame (com `com_mapa`: (marcos, volumes do mapa)), ou None."""
    import pydicom
    try:
        series = [s for s in repo.series_for_study(study_uid) if (s.description or "") == DESC_SEG]
    except Exception:  # noqa: BLE001
        return None
    for s in reversed(series):
        for inst in repo.instances_for_series(s.series_uid):
            try:
                ds = pydicom.dcmread(inst["path"], stop_before_pixels=True, force=True)
                texto = str(ds.private_block(GRUPO_PRIVADO, CRIADOR)[0x01].value)
                return (de_json(texto), mapa_do_json(texto)) if com_mapa else de_json(texto)
            except Exception:  # noqa: BLE001
                continue
    return None


def gravar(trabalho, m: Marcos, rotulos: dict, versao: str, db, storage_root, repo=None,
           volumes: list | None = None) -> dict:
    """SEG com as estruturas usadas e, num bloco privado, os marcos (o mapa se refaz a partir deles)."""
    import shutil
    import tempfile
    from pathlib import Path
    from types import SimpleNamespace

    from ipe.ai import totalseg as TS
    from ipe.ai.totalseg_saida import _caminho_do_sop
    from ipe.imaging.seg_writer import build_seg
    from ipe.importer.scanner import Importer
    if repo is not None:
        for se in repo.series_for_study(trabalho.study_uid):
            if (se.description or "") == DESC_SEG:
                try:
                    repo.delete_series(se.series_uid, Path(storage_root))
                except Exception:  # noqa: BLE001
                    log.exception("trocar o mapa linfonodal anterior")
    ms = CF.Mascaras(trabalho.vol, rotulos)
    segs = []
    for nome, (_t, rot, cor) in ESTRUTURAS.items():
        mk = ms.get(nome)
        if mk is not None:
            fat, off = CF._recorte(mk)
            segs.append((SimpleNamespace(mask=mk[fat], offset=off), rot, cor))
    if not segs:
        raise TS.Falhou("O TotalSegmentator não achou os marcos do pescoço nesta série.")
    vol = trabalho.vol
    ds = build_seg(vol, segs, vol.source_path, frames=trabalho.frames, series_number=SERIE_SEG,
                   description=DESC_SEG, algoritmo=("AUTOMATIC", f"TotalSegmentator {versao}".strip()),
                   anatomia=True)
    bloco = ds.private_block(GRUPO_PRIVADO, CRIADOR, create=True)
    bloco.add_new(0x01, "UT", para_json(m, volumes))
    tmp = Path(tempfile.mkdtemp(prefix="dv_linfo_"))
    out = {"series": []}
    try:
        ds.save_as(tmp / "seg.dcm", enforce_file_format=True)
        r = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([tmp])
        out["series"] += sorted(getattr(r, "new_series", None) or [])
        out["seg_sop"] = str(ds.SOPInstanceUID)
        out["seg_path"] = _caminho_do_sop(db, trabalho.study_uid, out["seg_sop"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def resumo(m: Marcos) -> str:
    feitos = [n for n, v in (("hioide", m.z_hioide), ("cricoide", m.z_cricoide), ("base do crânio", m.z_cranio),
                             ("manúbrio", m.z_manubrio)) if v is not None]
    txt = "marcos: " + (", ".join(feitos) if feitos else "nenhum")
    lados = [NOME_LADO[ld] for ld in LADOS if m.scm_post.get(ld) and m.car_med.get(ld)]
    if lados:
        txt += "; ECM e carótida: " + " e ".join(lados)
    return txt


def texto_da_lesao(centro, m: Marcos) -> tuple[str, str, str]:
    """(rótulo curto "IIA D", texto "nível IIA direito", regra) do centro de uma lesão (mm)."""
    nv, ld, regra = classificar([centro], m)[0]
    return rotulo(nv, ld), nome_do_nivel(nv, ld), regra
