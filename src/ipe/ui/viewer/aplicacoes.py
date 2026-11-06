"""Aplicações do visualizador e quando cada uma aparece na barra (0.99.12).

Pedido dele: *"criar uma forma de gerenciar a barra de ferramentas, tanto de forma inteligente
quanto de forma manual: no exame de mama aparece o botão de dinâmico; numa angiotomografia do
pescoço aparece a opção de calcular a estenose; em um exame de pescoço, a possibilidade de calcular
os níveis de linfonodos, e daí em diante"*.

Cada aplicação tem uma **regra**: modalidades do exame e, opcionalmente, alternativas de
(regiões do corpo, tipos de série). A regra é avaliada pelo **exame inteiro** (escolha dele).

- **Região** sai do BodyPartExamined das séries e das descrições do exame e das séries, por um
  dicionário de termos que ele edita (Configurações ▸ Protocolos de exame ▸ Regiões do corpo).
  Termo de até 3 letras só vale como palavra inteira ("PE", "RIM", "ATM"); de 4 ou mais, vale como
  começo de palavra ("ABDOM" pega "ABDOMEN" e "ABDOMINAL"); com espaço, vale como trecho.
- **Tipo de série**: angio, T1 3D, T2 3D, dinâmica, volume — pelas descrições e pelo número de
  imagens.

Por cima da regra, a escolha dele por aplicação: **automático** (a regra), **sempre** ou
**nunca** — por usuário, com exceção opcional por região (`viewer.barra`).

Nada aqui esconde função: o que a regra tira da barra continua em "Todas as aplicações", com o
motivo, e roda mesmo assim. Descrição mal escrita no aparelho não pode trancar a ferramenta.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# ------------------------------------------------------------------ regiões do corpo
#: id -> (nome na tela, termos separados por "|")
REGIOES_FABRICA: dict[str, tuple[str, str]] = {
    "cranio": ("Crânio e encéfalo",
               "HEAD|BRAIN|CRANIO|CRANIUM|SKULL|ENCEFALO|CEREBR|SELA|HIPOFISE|PITUIT|ORBITA|ORBIT"),
    "pescoco": ("Pescoço",
                "NECK|PESCOCO|CAROTID|CAROTIDA|CAROTIDAS|TIREOIDE|THYROID|LARING|LARYNX|FARING|"
                "PHARYN|TSA|SUPRA AORT|SUPRAAORT|TRONCOS SUPRA|PAROTID|SUBMANDIB|CERVICAL"),
    "face": ("Face e seios da face",
             "FACE|FACIAL|SEIOS|SINUS|PARANASAL|MANDIB|MAXIL|ATM|TMJ|DENTAL|ODONTO|CBCT|"
             "MASTOID|OUVIDO|TEMPORAL BONE|ROCHED|CAVUM|RINOFARING|NASOFARING|ADENOIDE|APNEIA|CEFALOMETR"),
    "mama": ("Mama", "BREAST|MAMA|MAMAS|MAMARIA|MAMOGRAF|MAMMO"),
    "torax": ("Tórax", "CHEST|THORAX|TORAX|TORACIC|LUNG|PULMAO|PULMON"),
    "coracao": ("Coração", "HEART|CARDIAC|CARDIACA|CORONAR|CORACAO|CARDIO"),
    "abdome": ("Abdome", "ABD|ABDOM|LIVER|FIGADO|HEPAT|PANCREA|RENAL|RINS|RIM|KIDNEY|ENTERO|"
                         "COLANGIO|MRCP|ADRENAL|SUPRARREN"),
    "pelve": ("Pelve", "PELV|PELVE|PROSTAT|UTER|UTERO|OVARI|RETO|RECTUM|BEXIGA|BLADDER|ENDOMETR"),
    "coluna": ("Coluna", "SPINE|COLUNA|CSPINE|TSPINE|LSPINE|LOMBAR|LUMBAR|LOMBOSSACR|DORSAL|SACR|"
                         "VERTEB|CERVICAL"),
    "membros": ("Membros e articulações",
                "KNEE|JOELHO|SHOULDER|OMBRO|QUADRIL|ANKLE|TORNOZELO|WRIST|PUNHO|MAO|HAND|FOOT|PE|"
                "ELBOW|COTOVELO|EXTREMIT|MEMBRO|COXA|PERNA|BRACO|ANTEBRACO"),
}

#: tipos de série que as regras usam
TIPOS: dict[str, tuple[str, str]] = {
    "angio": ("Série angiográfica (angio-TC, angio-RM, TOF)",
              "ANGIO|ANGIOTC|ANGIORM|CTA|MRA|ATC|ARM|TOF|CEMRA|CE MRA|TRICKS|TWIST"),
    "t1_3d": ("T1 3D (MPRAGE, BRAVO, FSPGR…)",
              "MPRAGE|MP RAGE|BRAVO|FSPGR|SPGR|3D T1|T1 3D|T13D|3DT1|T1W 3D|3D T1W|CUBE T1|T1 CUBE|"
              "TFL3D|VISTA T1|T1 VISTA"),
    "t2_3d": ("T2 3D fino (CUBE, SPACE, VISTA, FIESTA, CISS)",
              "CUBE|SPACE|VISTA|FIESTA|CISS|DRIVE|3D T2|T2 3D|T23D|3DT2"),
    "dinamica": ("Série dinâmica (contraste em fases)",
                 "DYN|DYNAMIC|DINAM|DINAMICO|DINAMICA|DCE|VIBRANT|THRIVE|DISCO|PERFUS|PERFUSION"),
    "difusao": ("Difusão (DWI, ADC)", "DWI|DIFUS|DIFUSAO|DIFFUSION|DIFF|TRACE|TRACEW|ADC|EADC|DTI|EPI DIFF"),
    "volume": ("Volume (TC/RM/PET com muitos cortes)", ""),
}

VOLUME_MIN_IMAGENS = 30


def _sem_acento(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    return "".join(c for c in t if not unicodedata.combining(c)).upper()


def _palavras(texto: str) -> tuple[str, list[str]]:
    limpo = re.sub(r"[^A-Z0-9]+", " ", _sem_acento(texto)).strip()
    return f" {limpo} ", limpo.split()


def termos(texto_regra: str) -> list[str]:
    return [_sem_acento(t).strip() for t in (texto_regra or "").split("|") if t.strip()]


def casa(texto: str, lista_de_termos: list[str]) -> bool:
    """Algum termo aparece no texto? (regras do cabeçalho deste arquivo)"""
    cheio, palavras = _palavras(texto)
    for t in lista_de_termos:
        t = re.sub(r"[^A-Z0-9]+", " ", t).strip()
        if not t:
            continue
        if " " in t:
            if f" {t} " in cheio:
                return True
        elif len(t) <= 3:
            if t in palavras:
                return True
        elif any(p.startswith(t) for p in palavras):
            return True
    return False


def regioes(settings) -> dict[str, tuple[str, str]]:
    """As regiões de fábrica com o que ele mudou (`viewer.regioes`: id -> {nome, termos})."""
    out = dict(REGIOES_FABRICA)
    dele = settings.get("viewer.regioes", None) if settings is not None else None
    if isinstance(dele, dict):
        for rid, v in dele.items():
            if isinstance(v, dict):
                nome = str(v.get("nome") or out.get(rid, (rid, ""))[0])
                out[str(rid)] = (nome, str(v.get("termos", "")))
            elif v is None:
                out.pop(str(rid), None)          # região apagada por ele
    return out


def nome_da_regiao(settings, rid: str) -> str:
    return regioes(settings).get(rid, (rid, ""))[0]


# ------------------------------------------------------------------ o exame aberto
@dataclass
class Contexto:
    modalidades: set = field(default_factory=set)
    regioes: set = field(default_factory=set)
    tipos: set = field(default_factory=set)


def contexto(series, infos, settings, tipos_extra: set | None = None) -> Contexto:
    """Modalidades, regiões e tipos de série dos exames abertos numa aba."""
    series = list(series or [])
    mods = {(s.modality or "").upper() for s in series if getattr(s, "modality", "")}
    textos = [str((i or {}).get("description", "") or "") for i in (infos or [])]
    textos += [str(getattr(s, "description", "") or "") for s in series]
    textos += [str(getattr(s, "body_part", "") or "") for s in series]
    achadas = set()
    for rid, (_nome, regra) in regioes(settings).items():
        lista = termos(regra)
        if lista and any(casa(t, lista) for t in textos if t):
            achadas.add(rid)
    if "MG" in mods:
        achadas.add("mama")                      # mamografia é mama, diga a descrição o que disser
    tipos = set(tipos_extra or ())
    descricoes = [str(getattr(s, "description", "") or "") for s in series]
    for tid, (_nome, regra) in TIPOS.items():
        lista = termos(regra)
        if lista and any(casa(d, lista) for d in descricoes if d):
            tipos.add(tid)
    if any((s.modality or "").upper() in ("CT", "MR", "PT") and int(getattr(s, "num_images", 0) or 0)
           >= VOLUME_MIN_IMAGENS for s in series):
        tipos.add("volume")
    return Contexto(mods, achadas, tipos)


# ------------------------------------------------------------------ as aplicações
@dataclass(frozen=True)
class Aplicacao:
    id: str
    nome: str
    modalidades: frozenset = frozenset()          # vazio = qualquer
    #: alternativas (regiões, tipos): basta uma valer; dentro dela, vazio = qualquer
    quando: tuple = ()
    modulo: str = ""
    descricao: str = ""


APLICACOES: dict[str, Aplicacao] = {a.id: a for a in (
    Aplicacao("mpr", "MPR", frozenset({"CT", "MR", "PT", "NM"}),
              descricao="Reconstrução em outros planos"),
    Aplicacao("3d", "3D", frozenset({"CT", "MR", "PT", "NM"}), ((frozenset(), frozenset({"volume"})),),
              modulo="3d", descricao="Renderização de volume, MIP 3D, superfície"),
    Aplicacao("dinamica", "Dinâmica", frozenset({"MR"}),
              ((frozenset({"mama"}), frozenset()), (frozenset(), frozenset({"dinamica"}))),
              modulo="rm_tc", descricao="Avaliação dinâmica: MSI, PEI, SER e curvas"),
    Aplicacao("fusao", "Fusão", frozenset({"PT", "NM"}), modulo="mn",
              descricao="Sobrepor outra série ao quadro ativo (PET na TC)"),
    Aplicacao("mn", "MN", frozenset({"NM"}), modulo="mn", descricao="Medicina nuclear"),
    Aplicacao("indices", "Índices", frozenset({"MR", "CT"}), ((frozenset({"cranio"}), frozenset()),),
              descricao="Medidas guiadas: MRPI e MRPI 2.0, índice de Evans, ângulo calosal"),
    Aplicacao("linfonodos", "Linfonodos", frozenset({"CT"}), ((frozenset({"pescoco"}), frozenset()),),
              descricao="Mapa dos níveis linfonodais cervicais (I a VII) e o nível da lesão segmentada"),
    Aplicacao("nodulos", "Nódulos", frozenset({"CT"}), ((frozenset({"torax"}), frozenset()),),
              descricao="Nódulos pulmonares (IA): candidatos com volume, eixos e densidade, revisados um a um"),
    Aplicacao("composicao", "Composição", frozenset({"CT"}), ((frozenset({"abdome"}), frozenset()),),
              descricao="Composição corporal em L3 (músculo, gordura visceral e subcutânea) e atenuação hepática"),
    Aplicacao("figado_rm", "Fígado (RM)", frozenset({"MR"}), ((frozenset({"abdome"}), frozenset()),),
              descricao="Gordura (PDFF) e ferro (R2*) do fígado nos mapas do aparelho; dupla eco em fase / fora de fase"),
    Aplicacao("enfisema", "Enfisema", frozenset({"CT"}), ((frozenset({"torax"}), frozenset()),),
              descricao="Enfisema (IA): % abaixo de −950 HU e Perc15 por pulmão e por lobo, com a distribuição"),
    Aplicacao("genant", "Genant", frozenset({"CT", "MR"}),
              ((frozenset({"coluna"}), frozenset()), (frozenset({"torax"}), frozenset()),
               (frozenset({"abdome"}), frozenset())),
              descricao="Fratura vertebral (IA): altura dos corpos vertebrais e grau de Genant de T4 a L5"),
    Aplicacao("figado_lesoes", "Lesões hepáticas", frozenset({"CT", "MR"}), ((frozenset({"abdome"}), frozenset()),),
              descricao="Lesões hepáticas (IA): volume e diâmetro de cada uma e a carga por segmento de Couinaud"),
    Aplicacao("difusao", "Difusão", frozenset({"MR"}), ((frozenset(), frozenset({"difusao"})),),
              descricao="Mapa ADC dos valores de b, DWI sintética e ADC numa ROI (qualquer RM)"),
    Aplicacao("abdome", "Órgãos abdominais", frozenset({"CT", "MR"}),
              ((frozenset({"abdome", "pelve"}), frozenset()),),
              descricao="Segmentação dos órgãos abdominais (IA): máscaras e tabela de volumes no exame"),
    Aplicacao("cefalometria", "Cefalometria", frozenset({"CT"}),
              ((frozenset({"face", "pescoco"}), frozenset()),),
              descricao="Cefalometria do cavum: via aérea, palato mole, língua e hioide (automática ou à mão)"),
)}

MODOS = ("auto", "sempre", "nunca")
NOME_DO_MODO = {"auto": "Automático (pela regra)", "sempre": "Sempre", "nunca": "Nunca (só em Todas)"}


def avaliar(app: Aplicacao, ctx: Contexto, settings=None) -> tuple[bool, str]:
    """A regra vale para este exame? Devolve (vale, motivo quando não vale)."""
    if app.modalidades and not (set(app.modalidades) & ctx.modalidades):
        mods = "/".join(sorted(app.modalidades))
        return False, f"o exame não tem {mods}"
    if not app.quando:
        return True, ""
    faltas = []
    for regs, tipos in app.quando:
        ok_r = not regs or bool(set(regs) & ctx.regioes)
        ok_t = not tipos or bool(set(tipos) & ctx.tipos)
        if ok_r and ok_t:
            return True, ""
        if not ok_r:
            faltas.extend(nome_da_regiao(settings, r) for r in sorted(regs))
        if not ok_t:
            faltas.extend(TIPOS[t][0].split(" (")[0] for t in sorted(tipos))
    lista = ", ".join(dict.fromkeys(faltas))
    return False, f"não achei no exame: {lista}"


def _cfg(settings) -> dict:
    v = settings.get("viewer.barra", None) if settings is not None else None
    return dict(v) if isinstance(v, dict) else {}


def modo(settings, app_id: str, regs: set | None = None) -> tuple[str, str]:
    """(modo, de onde veio): a exceção da região manda sobre a escolha geral."""
    modos = (_cfg(settings).get("modos") or {}).get(app_id) or {}
    for r in sorted(regs or ()):
        m = modos.get(r)
        if m in MODOS:
            return m, r
    m = modos.get("*")
    return (m, "*") if m in MODOS else ("auto", "")


def definir_modo(settings, app_id: str, novo: str, regiao: str = "*") -> None:
    cfg = _cfg(settings)
    modos = dict(cfg.get("modos") or {})
    deste = dict(modos.get(app_id) or {})
    if novo == "auto" and regiao != "*":
        deste.pop(regiao, None)                  # tirar a exceção volta à escolha geral
    elif novo == "auto":
        deste.pop("*", None)
    else:
        deste[regiao or "*"] = novo
    if deste:
        modos[app_id] = deste
    else:
        modos.pop(app_id, None)
    cfg["modos"] = modos
    settings.set("viewer.barra", cfg)


def ordem(settings) -> list[str]:
    guardada = [a for a in (_cfg(settings).get("ordem") or []) if a in APLICACOES]
    return guardada + [a for a in APLICACOES if a not in guardada]


def definir_ordem(settings, lista: list[str]) -> None:
    cfg = _cfg(settings)
    cfg["ordem"] = [a for a in lista if a in APLICACOES]
    settings.set("viewer.barra", cfg)


def mostrar(settings, app_id: str, ctx: Contexto) -> tuple[bool, str]:
    """Aparece na barra? (aparece, explicação curta para a dica e para "Todas as aplicações")."""
    app = APLICACOES[app_id]
    m, origem = modo(settings, app_id, ctx.regioes)
    regiao = "" if origem in ("", "*") else nome_da_regiao(settings, origem).lower()
    if m == "sempre":
        return True, (f"você escolheu mostrar sempre em exames de {regiao}" if regiao
                      else "você escolheu mostrar sempre")
    if m == "nunca":
        return False, (f"você escolheu esconder em exames de {regiao}" if regiao
                       else "você escolheu esconder")
    return avaliar(app, ctx, settings)


def descrever_regra(app: Aplicacao, settings=None) -> str:
    partes = []
    if app.modalidades:
        partes.append("/".join(sorted(app.modalidades)))
    alts = []
    for regs, tipos in app.quando:
        p = []
        if regs:
            p.append(" ou ".join(nome_da_regiao(settings, r) for r in sorted(regs)))
        if tipos:
            p.append(" / ".join(TIPOS[t][0].split(" (")[0].lower() for t in sorted(tipos)))
        alts.append(" + ".join(p))
    if alts:
        partes.append("· " + " / ".join(alts))
    return " ".join(partes) or "qualquer exame"
