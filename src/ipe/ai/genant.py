"""Fratura vertebral pela classificação semiquantitativa de Genant (0.99.77).

Usa a medida da altura dos corpos vertebrais que já existe no módulo Coluna (`coluna.medir_vertebras`,
0.99.4–0.99.5), desligada desde a 0.99.7 na numeração da coluna (pedido dele: "apenas nomeie as vértebras").
Aqui ela volta como **ferramenta própria**, pedida à parte:

- as vértebras vêm do TotalSegmentator em resolução cheia (TC: tarefa `total` a 1,5 mm, não o modo rápido de
  3 mm da numeração; RM: `vertebrae_mr` + `total_mr`), nomeadas pela regra da Coluna (âncora em C2 ou na
  última costela);
- em cada corpo, as alturas anterior, média e posterior na faixa sagital central;
- a perda de altura é a maior entre **cunha** (1 − Ha/Hp), **bicôncava** (1 − Hm/Hp) e **esmagamento** (Hp
  contra a média das duas vizinhas);
- o grau (Genant et al., J Bone Miner Res 1993): 20–25% leve (1), 25–40% moderada (2), > 40% acentuada (3),
  só de T4 a L5 (onde a classificação foi validada).

Cada vértebra com grau 1 ou mais vira um **achado** (`ai/achados.py`) "Fratura vertebral (Genant)" para
revisar, e um achado de resumo diz quantas foram medidas. Deformidade não é sinônimo de fratura (variante,
Scheuermann, nódulo de Schmorl, degeneração): a tela pede para conferir na sagital.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from ipe.ai import achados as AC

log = logging.getLogger(__name__)

FERRAMENTA = "genant"
TITULO = "Fratura vertebral — Genant (IA)"
MARCA = "· TotalSegmentator"
DESC_SEG = f"Vértebras (Genant) {MARCA}"
MIN_CORTES = 30
MODALIDADES = ("CT", "MR")
MOTIVO_MODALIDADE = "A altura das vértebras é medida na TC ou na RM."
MODELO = "TotalSegmentator (vértebras 1,5 mm) + alturas do corpo (Coluna) + Genant"
CHAVE_SAIDA = "genant"
TIPO = "Fratura vertebral (Genant)"
TIPO_RESUMO = "Alturas vertebrais (Genant)"

# Configurações ▸ CAD/IA ▸ Fratura vertebral
CHAVE_AUTO = "genant.auto"
CHAVE_EXAME_CONTEM = "genant.exame_contem"
CHAVE_MODALIDADES = "genant.modalidades"
CHAVE_PRIOR_CT = "genant.prioridade_ct"
CHAVE_ESPESSURA = "genant.espessura_max"
CHAVE_MIN_CORTES = "genant.min_cortes"
CHAVE_DESTINOS = "genant.destinos"
PADROES = {
    CHAVE_AUTO: False,
    CHAVE_EXAME_CONTEM: "COLUNA|SPINE|LOMBAR|DORSAL|TORACICA|TORAX|TÓRAX|CHEST|ABDOME|ABD|CORPO INTEIRO",
    CHAVE_MODALIDADES: ["CT", "MR"],
    CHAVE_PRIOR_CT: "OSSO|BONE|SAG|SAGITAL|COLUNA|STD|STANDARD|PARTES MOLES|AX",
    CHAVE_ESPESSURA: 3.0,
    CHAVE_MIN_CORTES: MIN_CORTES,
    CHAVE_DESTINOS: [],
}
PERFIL = {"modalidades": CHAVE_MODALIDADES, "exame_contem": CHAVE_EXAME_CONTEM, "prior_ct": CHAVE_PRIOR_CT,
          "prior_mr": CHAVE_PRIOR_CT, "espessura": CHAVE_ESPESSURA, "min_cortes": CHAVE_MIN_CORTES}
NOME_CADIA = "Fratura vertebral (Genant)"
TITULO_CADIA = "Fratura vertebral pela classificação de Genant (TotalSegmentator + alturas do corpo vertebral)"
EXPLICACAO_CADIA = ("Na TC ou na RM com a coluna torácica ou lombar: nomeia as vértebras, mede a altura anterior, "
                    "média e posterior de cada corpo e calcula a perda de altura (cunha, bicôncava ou esmagamento). "
                    "De T4 a L5, perda de 20–25% é grau 1, 25–40% grau 2 e mais de 40% grau 3. Cada vértebra "
                    "alterada aparece em Aplicações ▸ Achados de IA, para conferir na sagital antes do laudo.")


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
    try:
        return bool(repo.achados(study_uid, FERRAMENTA))
    except Exception:  # noqa: BLE001
        return False


def tarefas(modalidade: str = "CT", settings=None) -> list[dict]:
    """As da Coluna, mas em resolução cheia: 3 mm (o modo rápido) é grosso demais para uma altura de 25 mm."""
    from ipe.ai import coluna as COL
    if (modalidade or "").upper() == "MR":
        return [{"nome": "vertebrae_mr", "rotulo": "vértebras"}, {"nome": "total_mr", "rotulo": "discos (1,5 mm)"}]
    vertebras = [f"vertebrae_{n}" for n in COL.ORDEM if n != "S2"] + ["sacrum"]
    vertebras += [f"rib_{lado}_{i}" for lado in ("left", "right") for i in range(1, 13)]
    return [{"nome": "total", "roi": vertebras, "rotulo": "vértebras (1,5 mm)"},
            {"nome": "vertebrae_body", "rotulo": "discos"}]


# ------------------------------------------------------------------ a conta
@dataclass
class Resultado:
    medidas: list = field(default_factory=list)       # coluna.MedidaVertebra
    numeracao: str = ""
    avisos: list = field(default_factory=list)
    elegibilidade: str = ""
    versao: str = ""
    series_uid: str = ""

    @property
    def alteradas(self) -> list:
        return [m for m in self.medidas if m.grau]

    @property
    def medidas_validas(self) -> list:
        return [m for m in self.medidas if m.perda is not None]


def avaliar(obj, res: Resultado | None = None) -> Resultado:
    """As alturas e o grau, a partir do objeto da coluna (volumes com o nome de cada vértebra)."""
    from ipe.ai import coluna as COL
    res = res or Resultado()
    res.medidas = COL.medir_vertebras(obj)
    aviso = COL.aviso_da_serie(obj)
    if aviso:
        res.avisos.append(aviso)
    duv = [m.nome for m in res.medidas if m.duvidosa]
    if duv:
        res.avisos.append("medida duvidosa (conferir): " + ", ".join(duv))
    notas = [f"{m.nome}: {m.nota}" for m in res.medidas if m.nota and m.perda is None]
    if notas:
        res.avisos.append("sem medida — " + "; ".join(notas))
    if not res.medidas_validas:
        res.avisos.append("nenhuma vértebra pôde ser medida nesta série")
    res.avisos.append("deformidade não é sinônimo de fratura (variante, Scheuermann, nódulo de Schmorl, degeneração): "
                      "confira cada uma na sagital; graus de Genant et al., J Bone Miner Res 1993")
    return res


def calcular(t, rotulos: dict, settings=None) -> Resultado:
    from ipe.ai import coluna as COL
    vol = t.vol
    res = Resultado(versao=getattr(t, "versao", ""), series_uid=t.series_uid)
    desc = t.descricao_serie or t.series_uid[-8:]
    n, dy, dx, dz = vol.data.shape[0], vol.dy, vol.dx, abs(float(vol.dz))
    res.elegibilidade = f"Série “{desc}”, {n} cortes, pixel {dy:.2f} × {dx:.2f} mm, intervalo {dz:.2f} mm"
    niveis = COL.nomear(vol, rotulos)
    if not niveis.itens:
        res.avisos.append("a IA não achou as vértebras nesta série")
        return res
    res.numeracao = COL.resumo(niveis)
    obj = COL.objeto(vol, niveis, t.study_uid, chave="genant")
    return avaliar(obj, res)


def _n(v, u, n, casas=1):
    return AC.numero(None if v is None else round(float(v), casas), u, n)


def itens_para_o_banco(res: Resultado, t, versao: str, revisados: set | None = None) -> list[dict]:
    from ipe.ai import coluna as COL
    base = {"series_uid": t.series_uid, "modelo": MODELO, "versao": versao or res.versao}
    eleg = res.elegibilidade + (". Atenção: " + "; ".join(res.avisos) if res.avisos else "")
    out = []
    for m in res.alteradas:
        if revisados and m.nome in revisados:
            continue                    # o médico já decidiu sobre esta vértebra: não volta como sugestão
        out.append({**base, "rotulo": m.nome, "tipo": TIPO, "local": f"corpo vertebral de {m.nome}",
                    "posicao": None if m.centro is None else [float(x) for x in m.centro],
                    "numeros": {"perda": _n(m.perda, "%", "Perda de altura", 0),
                                "grau": AC.numero(int(m.grau), "", "Grau de Genant"),
                                "forma": AC.numero(COL.FORMAS.get(m.forma, m.forma), "", "Forma"),
                                "anterior": _n(m.anterior, "mm", "Altura anterior"),
                                "media": _n(m.media, "mm", "Altura média"),
                                "posterior": _n(m.posterior, "mm", "Altura posterior")},
                    "elegibilidade": eleg})
    validas = res.medidas_validas
    if validas or res.medidas:
        maior = max(validas, key=lambda m: m.perda) if validas else None
        faixa = f"{validas[0].nome}–{validas[-1].nome}" if validas else ""
        out.append({**base, "rotulo": "Coluna", "tipo": TIPO_RESUMO, "local": faixa or "coluna",
                    "posicao": None if maior is None or maior.centro is None else [float(x) for x in maior.centro],
                    "numeros": {"medidas": AC.numero(len(validas), "", "Vértebras medidas"),
                                "alteradas": AC.numero(len(res.alteradas), "", "Com perda ≥ 20% (T4–L5)"),
                                "maior": _n(maior.perda if maior else None, "%", "Maior perda", 0),
                                "nivel": AC.numero(maior.nome if maior else "", "", "Onde")},
                    "elegibilidade": eleg})
    return out


def gravar(t, res: Resultado, versao: str, db, storage_root, repo=None, settings=None) -> dict:
    from ipe.db.repository import Repository
    repo = repo or Repository(db)
    try:
        revisados = {a.get("rotulo") for a in repo.achados(t.study_uid, FERRAMENTA)
                     if a.get("estado") != "sugerido" and a.get("tipo") == TIPO}
    except Exception:  # noqa: BLE001
        revisados = set()
    out = {"series": [], "ferramenta": FERRAMENTA}
    out["achados"] = repo.gravar_achados(t.study_uid, FERRAMENTA, itens_para_o_banco(res, t, versao, revisados))
    return out


def resumo(res: Resultado) -> str:
    if not res.medidas_validas:
        return res.avisos[0] if res.avisos else "nada medido"
    alt = res.alteradas
    txt = f"{len(res.medidas_validas)} vértebras medidas"
    if alt:
        from ipe.ai import coluna as COL
        txt += "; perda de altura ≥ 20% em " + ", ".join(
            m.nome + f" (perda de {m.perda:.0f}%, {COL.FORMAS.get(m.forma, m.forma)}, grau {m.grau})" for m in alt)
    else:
        txt += ", nenhuma com perda de altura de 20% ou mais"
    return txt


def n_itens(res: Resultado) -> int:
    return len(res.alteradas) + int(bool(res.medidas))


def mensagem(res: Resultado, minutos: float) -> str:
    msg = (f"Genant pronto em {minutos:.1f} min — {resumo(res)}. Cada vértebra alterada está em Aplicações ▸ "
           "Achados de IA, para conferir na sagital antes do laudo.")
    avisos = [a for a in res.avisos if not a.startswith("deformidade")]
    if avisos:
        msg += "\n\nConfira: " + "; ".join(avisos) + "."
    return msg


def frase(a: dict) -> str:
    n = AC.numeros_validos(a)

    def v(k):
        return (n.get(k) or {}).get("v")
    if a.get("tipo") == TIPO_RESUMO:
        medidas, alteradas = v("medidas") or 0, v("alteradas") or 0
        if not alteradas:
            return (f"Corpos vertebrais ({a.get('local', '')}) sem redução de altura de 20% ou mais "
                    f"(análise semiquantitativa de Genant, {medidas} vértebras).")
        return ""                       # as alteradas têm frase própria
    grau = {1: "leve (grau 1)", 2: "moderada (grau 2)", 3: "acentuada (grau 3)"}.get(int(v("grau") or 0), "")
    perda = v("perda")
    perda_txt = "" if perda is None else f"{float(perda):.0f}%"
    forma = v("forma") or ""
    return (f"Redução de altura do corpo vertebral de {a.get('rotulo', '')} de {perda_txt}"
            + (f", do tipo {forma}" if forma else "") + (f" — fratura/deformidade {grau} de Genant" if grau else "") + ".")
