"""Mamografia: identificação das incidências e protocolos de exibição por etapas.

Código de um quadro: incidência + lado (+ anterior), em português:
  CCD, CCE, MLOD, MLOE, MLD, MLE, LMD, LME, XCCLD, XCCLE, AT…; "ant" = exame anterior mais
  recente, "ant2" = o anterior a esse; "tomo" = tomossíntese (cortes) em vez da imagem 2D;
  "rec" = imagem recombinada da mamografia com contraste (CEM). Ex.: "CCD ant", "MLOE tomo", "CCD rec".
Uma etapa é escrita como colunas separadas por "x" e linhas (dentro da coluna) por vírgula:
  "CCD x CCE"                     → 1×2
  "CCD, MLOD x CCE, MLOE"         → 2×2 (direita à esquerda da tela, esquerda à direita)
  "CCD, CCD ant x CCE, CCE ant"   → 2×2 atual em cima, anterior embaixo
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import functools

import numpy as np

log = logging.getLogger(__name__)

VIEWS = ["CC", "MLO", "ML", "LM", "XCCL", "XCCM", "AT", "FB", "SIO", "SPOT", "MAG", "ANY"]
VIEW_NAMES = {"CC": "CC", "MLO": "MLO", "ML": "Perfil ML", "LM": "Perfil LM", "XCCL": "XCC lateral",
              "XCCM": "XCC medial", "AT": "Axilar", "FB": "Caudocranial", "SIO": "Oblíqua inversa",
              "SPOT": "Compressão localizada", "MAG": "Magnificação", "ANY": "Qualquer"}
SIDES = {"D": "R", "E": "L"}
SIDE_PT = {"R": "D", "L": "E"}

_CODE = re.compile(r"^\s*(CC|MLO|ML|LM|XCCL|XCCM|AT|FB|SIO|SPOT|MAG|ANY)?\s*([DE])\s*(ANT(?:ERIOR)?\s*(\d)?)?\s*$",
                   re.I)


@dataclass(frozen=True)
class Cell:
    view: str          # CC, MLO… (ANY = qualquer incidência)
    side: str          # R | L
    prior: int = 0     # 0 = atual; 1 = anterior; 2 = o anterior do anterior
    tomo: bool = False  # tomossíntese (cortes) em vez da imagem 2D
    rec: bool = False   # mamografia com contraste: imagem recombinada (em vez da de baixa energia)

    @property
    def code(self) -> str:
        v = "" if self.view == "ANY" else self.view
        return (f"{v}{SIDE_PT[self.side]}" + (" tomo" if self.tomo else "") + (" rec" if self.rec else "")
                + ("" if not self.prior else " ant" if self.prior == 1 else f" ant{self.prior}"))

    @property
    def label(self) -> str:
        side = "D" if self.side == "R" else "E"
        v = "" if self.view == "ANY" else f"{self.view} "
        return (f"{v}{side}" + (" tomo" if self.tomo else "") + (" recombinada" if self.rec else "")
                + ("" if not self.prior else " (anterior)" if self.prior == 1 else f" (anterior {self.prior})"))

    def with_tomo(self, on: bool) -> "Cell":
        return Cell(self.view, self.side, self.prior, on, self.rec)

    def with_rec(self, on: bool) -> "Cell":
        return Cell(self.view, self.side, self.prior, self.tomo, on)


_TOMO = re.compile(r"\s*\b(TOMO|DBT)\b\s*", re.I)
_REC = re.compile(r"\s*\b(REC|RECOMB|RECOMBINADA|SUB|CEM)\b\s*", re.I)


def parse_code(code: str) -> Cell | None:
    text = code or ""
    tomo = bool(_TOMO.search(text))
    text = _TOMO.sub(" ", text)
    rec = bool(_REC.search(text))
    text = _REC.sub(" ", text)
    m = _CODE.match(text)
    if not m:
        return None
    view = (m.group(1) or "ANY").upper()
    side = SIDES[m.group(2).upper()]
    prior = 0
    if m.group(3):
        prior = int(m.group(4) or 1)
    return Cell(view, side, prior, tomo, rec)


def parse_step(text: str) -> dict:
    """"CCD, MLOD x CCE, MLOE" → {"rows": 2, "cols": 2, "cells": ["CCD", "CCE", "MLOD", "MLOE"]} (linha a linha)."""
    t = (text or "").strip()
    m = re.match(r"^\s*(\d+)\s*[x×]\s*(\d+)\s*[:(]?\s*(.*?)\)?\s*$", t)
    if m and ("(" in t or ":" in t):             # "2x2 (CCD, MLOD x CCE, MLOE)"
        t = m.group(3)
    sep = r"\s+[x×]\s+|(?<=[DE0-9T,])\s*[x×]\s*(?=(?:CC|MLO|ML|LM|XCC|AT|FB|SIO|SPOT|MAG|[DE]\b))"
    cols = re.split(sep, t, flags=re.I)
    columns = [[x.strip() for x in c.split(",") if x.strip()] for c in cols]
    columns = [c for c in columns if c] or [[]]
    rows = max(1, max(len(c) for c in columns))
    cells = []
    for r in range(rows):
        for c in columns:
            cells.append(c[r] if r < len(c) else "")
    return {"rows": rows, "cols": len(columns), "cells": cells}


def step_text(step: dict) -> str:
    rows, cols, cells = int(step["rows"]), int(step["cols"]), list(step["cells"])
    columns = []
    for c in range(cols):
        columns.append(", ".join(cells[r * cols + c] for r in range(rows) if r * cols + c < len(cells)
                                 and cells[r * cols + c]))
    return " x ".join(columns)


def step_title(step: dict) -> str:
    return step.get("name") or f"{step['rows']}×{step['cols']}: {step_text(step)}"


def _passo(nome: str, rows: int, cols: int, cells: list[str]) -> dict:
    return {"name": nome, "rows": rows, "cols": cols, "cells": list(cells)}


# --------------------------------------------------------------- mamografia comum
QUATRO = _passo("4 incidências", 2, 2, ["CCD", "CCE", "MLOD", "MLOE"])
CC = _passo("CC", 1, 2, ["CCD", "CCE"])
MLO = _passo("MLO", 1, 2, ["MLOD", "MLOE"])
CC_ANT = _passo("CC atual × anterior", 2, 2, ["CCD", "CCE", "CCD ant", "CCE ant"])
MLO_ANT = _passo("MLO atual × anterior", 2, 2, ["MLOD", "MLOE", "MLOD ant", "MLOE ant"])
DIR_ANT = _passo("Direita atual × anterior", 2, 2, ["CCD", "CCD ant", "MLOD", "MLOD ant"])
ESQ_ANT = _passo("Esquerda atual × anterior", 2, 2, ["CCE", "CCE ant", "MLOE", "MLOE ant"])

# --------------------------------------------------------------- CEM
CEM_CC = _passo("CC: baixa energia × recombinada", 2, 2, ["CCD", "CCE", "CCD rec", "CCE rec"])
CEM_MLO = _passo("MLO: baixa energia × recombinada", 2, 2, ["MLOD", "MLOE", "MLOD rec", "MLOE rec"])
CEM_REC4 = _passo("Recombinadas (4 incidências)", 2, 2, ["CCD rec", "CCE rec", "MLOD rec", "MLOE rec"])
CEM_BAIXA4 = _passo("Baixa energia (4 incidências)", 2, 2, ["CCD", "CCE", "MLOD", "MLOE"])
CEM_REC_ANT = _passo("Recombinada atual × anterior", 2, 2,
                     ["CCD rec", "CCE rec", "CCD rec ant", "CCE rec ant"])

CEM_PROTOCOL = {
    "name": "Mamografia com contraste (CEM)", "enabled": True,
    "description": "CEM|CESM|CONTRAST|CONTRASTE|CONTRASTADA",
    "chest_to_center": True, "align_chest": True, "sync_zoom": True,
    "steps": [CEM_CC, CEM_MLO, CEM_REC4, CEM_BAIXA4, CEM_REC_ANT],
}

MG_PROTOCOL = {
    "name": "Mamografia (4 incidências, com anterior)", "enabled": True,
    "description": "",                # contém (vazio = qualquer MG)
    "chest_to_center": True,          # espelhar para a parede torácica ficar voltada ao centro
    "align_chest": True,              # encostar a imagem na borda do lado da parede torácica
    "sync_zoom": True,                # zoom por quadrante (Q) junto nos quadros; zoom/pan com o mouse
                                      # segue o botão de sincronia "Zoom e pan" (0.97.1)
    # **Uma** lista de etapas, não uma por monitor: a etapa é do conjunto. O que cada tela mostra
    # numa etapa sai de `telas` dentro da própria etapa (e, sem isso, da repartição automática
    # abaixo). Passar de etapa muda todos os monitores ao mesmo tempo.
    "steps": [QUATRO, CC, MLO, CC_ANT, MLO_ANT, DIR_ANT, ESQ_ANT],
}

DEFAULT_MG_PROTOCOLS = [CEM_PROTOCOL, MG_PROTOCOL]

TELAS_MAX = 4

# Escrito por extenso, e não com um {} na frente: "{} telas" seria um padrão genérico, e padrão
# que começa com o buraco sequestra qualquer outro texto na hora de traduzir.
TITULO_TELAS = {1: "1 tela", 2: "2 telas", 3: "3 telas", 4: "4 telas"}

# Como a etapa enquadra a imagem ao abrir. A chave fica em step["enquadre"]; sem a chave vale
# "mama", porque enquadrar pela imagem inteira é enquadrar o ar (metade do campo de uma
# mamografia não é mama).
ENQUADRES = {"mama": "Mama ao quadro (descarta o ar)",
             "imagem": "Imagem inteira no quadro",
             "pixel": "Resolução cheia (1 pixel da imagem = 1 do monitor)"}
ENQUADRE_PADRAO = "mama"


MARGEM_MAMA = 0.03          # folga de cada lado, para a pele não encostar na borda do quadro


def zoom_da_caixa(quadro, imagem, caixa, aspecto: float = 1.0,
                  margem: float = MARGEM_MAMA) -> float:
    """Zoom que faz `caixa` (a mama) ocupar `quadro`, partindo do ajuste da imagem inteira.

    `quadro` = (largura, altura) do quadro na tela — é daqui que vem a dependência do monitor;
    `imagem` = (largura, altura) em pixels; `caixa` = (x0, y0, x1, y1) em pixels da imagem;
    `aspecto` = espaçamento linha/coluna (pixel não quadrado).

    Nunca devolve menos de 1,0: o ajuste à janela já mostra tudo, e enquadrar a mama não pode
    deixá-la **menor** do que estava só para sobrar margem.
    """
    (qw, qh), (w, h) = quadro, imagem
    if qw <= 0 or qh <= 0 or w <= 0 or h <= 0:
        return 1.0
    bw, bh = max(1.0, caixa[2] - caixa[0]), max(1.0, caixa[3] - caixa[1])
    aspecto = aspecto if aspecto > 0 else 1.0
    ajuste = min(qw / w, qh / (h * aspecto))
    if ajuste <= 0:
        return 1.0
    folga = 1.0 + 2.0 * max(0.0, margem)
    por_largura = qw / (ajuste * bw * folga)
    por_altura = qh / (ajuste * aspecto * bh * folga)
    return float(max(1.0, min(8.0, min(por_largura, por_altura))))


def enquadre_da_etapa(step: dict | None) -> str:
    v = str((step or {}).get("enquadre") or ENQUADRE_PADRAO)
    return v if v in ENQUADRES else ENQUADRE_PADRAO


def passos_do_protocolo(proto: dict) -> list[dict]:
    """As etapas do protocolo — uma lista só, do conjunto de monitores.

    Lê também o formato intermediário que teve etapas por monitor: dali fica valendo a lista do
    arranjo de uma tela, que é a sequência que o médico via.
    """
    if not isinstance(proto, dict):
        return []
    passos = proto.get("steps")
    if not passos:
        telas = proto.get("telas")
        if isinstance(telas, dict):
            um = telas.get("1") or []
            passos = (um[0].get("steps") if um and isinstance(um[0], dict) else []) or []
    return [dict(p) for p in (passos or [])]


def _grade(n: int) -> tuple[int, int]:
    return {1: (1, 1), 2: (1, 2), 3: (1, 3), 4: (2, 2)}.get(n, (2, 3) if n <= 6 else (3, 3))


def repartir_etapa(step: dict, quantos: int) -> list[dict]:
    """A etapa repartida entre `quantos` monitores, quando ela não diz como.

    É a repartição que o radiologista faria à mão, e por isso é o padrão: numa etapa de duas
    linhas em duas telas, cada tela fica com uma linha — as CC numa, as MLO na outra. Quando as
    linhas não dividem, tenta pelas colunas; e só então reparte os quadros em ordem.
    """
    rows, cols = max(1, int(step.get("rows", 1))), max(1, int(step.get("cols", 1)))
    cells = list(step.get("cells") or [])
    cells += [""] * (rows * cols - len(cells))
    quantos = max(1, int(quantos or 1))
    if quantos == 1:
        return [{"rows": rows, "cols": cols, "cells": cells}]
    if rows % quantos == 0:
        f = rows // quantos
        return [{"rows": f, "cols": cols, "cells": cells[k * f * cols:(k + 1) * f * cols]}
                for k in range(quantos)]
    if cols % quantos == 0:
        f = cols // quantos
        saida = []
        for k in range(quantos):
            pedaco = [cells[r * cols + c] for r in range(rows) for c in range(k * f, (k + 1) * f)]
            saida.append({"rows": rows, "cols": f, "cells": pedaco})
        return saida
    cheias = [c for c in cells if c]
    if len(cheias) < quantos:
        # Menos imagens que telas: cada tela fica com uma, repetindo — monitor em branco parece
        # defeito, e nesta etapa não há mais o que mostrar.
        return [{"rows": 1, "cols": 1, "cells": [cheias[k % len(cheias)]]} if cheias
                else {"rows": 1, "cols": 1, "cells": [""]} for k in range(quantos)]
    tam, sobra = divmod(len(cheias), quantos)
    saida, i = [], 0
    for k in range(quantos):
        passo = tam + (1 if k < sobra else 0)
        parte = cheias[i:i + passo] or [""]
        i += passo
        l, c = _grade(len(parte))
        saida.append({"rows": l, "cols": c, "cells": parte})
    return saida


def quadro_da_etapa(step: dict, quantos: int, indice: int) -> dict:
    """O que o monitor `indice` mostra nesta etapa: {"rows", "cols", "cells"}.

    Primeiro o que a etapa disser (`telas`), que é o que o médico define na aba Mamografia;
    senão, a repartição automática.
    """
    quantos = max(1, int(quantos or 1))
    indice = max(0, int(indice or 0))
    if quantos == 1:
        return {"rows": max(1, int(step.get("rows", 1))), "cols": max(1, int(step.get("cols", 1))),
                "cells": list(step.get("cells") or [])}
    arranjo = (step.get("telas") or {}).get(str(quantos))
    if isinstance(arranjo, list) and len(arranjo) == quantos and indice < quantos:
        q = arranjo[indice] or {}
        if q.get("cells"):
            return {"rows": max(1, int(q.get("rows", 1))), "cols": max(1, int(q.get("cols", 1))),
                    "cells": list(q.get("cells") or [])}
    partes = repartir_etapa(step, quantos)
    return partes[indice] if indice < len(partes) else partes[-1]


def mg_protocols(settings) -> list[dict]:
    p = settings.get("mg_protocols") if settings is not None else None
    return [dict(x) for x in p] if isinstance(p, list) and p else [dict(x) for x in DEFAULT_MG_PROTOCOLS]


def find_mg_protocol(settings, description: str) -> dict | None:
    from ipe import modules as MOD
    if not MOD.ligado(settings, "mamografia"):        # módulo desligado: abre como imagem comum
        return None
    desc = (description or "").upper()
    for p in mg_protocols(settings):
        if not p.get("enabled", True):
            continue
        d = p.get("description", "")
        if d and not any(x.strip() and x.strip().upper() in desc for x in d.split("|")):
            continue
        return p
    return None


# ---------------------------------------------------------------------------- imagens do exame

@dataclass
class MgImage:
    study_uid: str
    series_uid: str
    sop_uid: str
    frame_index: int
    path: str
    side: str          # R | L | ""
    view: str          # CC, MLO… ou ""
    for_processing: bool = False
    number: int = 0
    time: str = ""
    frames: int = 1
    tomo: bool = False       # tomossíntese reconstruída (cortes)
    energy: str = ""         # CEM: "low" (baixa energia), "rec" (recombinada/subtraída), "high"; "" = comum
    # O rótulo da imagem é a incidência **em si** (RMLO), e não uma variante dela (RSMLO, a
    # complementar)? Os dois casos têm o mesmo ViewPosition e o mesmo código de incidência no
    # arquivo: o que distingue é o nome, e é por isso que ele entra na escolha.
    exata: bool = True
    serie: str = ""          # descrição da série, para o quadro poder dizer de onde veio
    rotulo: str = ""         # como o **aparelho** chama a incidência (GE 0045,101B): RMLO, RSMLO…
    sintetica: bool = False  # 2D sintetizada da tomossíntese (V-Preview/C-View), não 2D adquirida
    sem_implante: bool = False  # cópia com o implante corrigido, gravada na chegada (0.97)
    fonte: str = ""             # na cópia sem implante: o SOP Instance UID da imagem original


_VIEW_TEXT = [("XCCL", ("XCCL", "EXAGGERATED CRANIO-CAUDAL", "LATERALLY EXAGGERATED")),
              ("XCCM", ("XCCM", "MEDIALLY EXAGGERATED")),
              ("MLO", ("MLO", "MEDIO-LATERAL OBLIQUE", "MEDIOLATERAL OBLIQUE", "OBLIQ")),
              ("SIO", ("SIO", "SUPEROLATERAL")),
              ("FB", ("FB", "CAUDO-CRANIAL", "FROM BELOW")),
              ("CC", ("CC", "CRANIO-CAUDAL", "CRANIOCAUDAL", "CRANIO CAUDAL")),
              ("ML", ("ML", "MEDIO-LATERAL", "PERFIL")),
              ("LM", ("LM", "LATERO-MEDIAL")),
              ("AT", ("AT", "AXILLARY", "AXILAR"))]


def _view_of(texts: list[str]) -> str:
    for t in texts:
        up = f" {(t or '').upper()} "
        for code, keys in _VIEW_TEXT:
            for k in keys:
                if (len(k) <= 4 and re.search(rf"(?<![A-Z]){k}(?![A-Z])", up)) or (len(k) > 4 and k in up):
                    return code
    return ""


# GE Senographe: o nome da incidência como o próprio aparelho a chama, por imagem.
# Medido no acervo: 'RCC', 'LMLO', 'RSMLO', 'LSCC', 'RMSCC' — com lateralidade e com os
# modificadores do serviço. Está em 23 das 68 séries MG (falta nas V-Preview e ROUTINE3D_VOL),
# e por isso é referência quando existe, não condição.
TAG_INCIDENCIA_GE = (0x0045, 0x101B)


def rotulo_da_incidencia(ds) -> str:
    """O rótulo da incidência gravado pelo aparelho, só letras e maiúsculo. "" se não houver."""
    try:
        el = ds.get(TAG_INCIDENCIA_GE)
    except Exception:  # noqa: BLE001 - arquivo com tag privada estranha não derruba a leitura
        return ""
    valor = getattr(el, "value", el)
    if valor is None or isinstance(valor, bytes):
        return ""
    return re.sub(r"[^A-Z]", "", str(valor).upper())


def incidencia_exata(rotulo: str, nomes, view: str) -> bool:
    """Esta imagem é **a** incidência pedida, ou uma variante dela?

    Quando o aparelho gravou o rótulo (0045,101B), ele decide: `RMLO` é a MLO; `RSMLO`, `RSCC` e
    `RMSCC` são variantes (complementar, magnificada), e todas trazem o mesmo `ViewPosition` da
    incidência de origem. Sem o rótulo, sobra o nome da série.
    """
    if not view or view == "ANY":
        return True
    if rotulo:
        return bool(re.fullmatch(rf"[RLDE]?{re.escape(view)}", rotulo))
    return nomeia_a_incidencia(nomes, view)


def nomeia_a_incidencia(nomes, view: str) -> bool:
    """O **nome** da série diz esta incidência, ou diz uma variante dela?

    `CESM_PROC_RMLO` nomeia a MLO; `CESM_PROC_RSMLO` nomeia outra coisa — a complementar do
    serviço dele. As duas têm o mesmo `ViewPosition` ("MLO") e o mesmo código de incidência no
    arquivo: o `ViewPosition` não distingue, só o nome. Sem isto o programa escolhia a mais
    recente das duas, e a complementar aparecia no lugar da MLO que o protocolo pediu.

    Nome que não fala de incidência nenhuma (`2D_PROC`, `V-Preview`) não desempata nada: conta
    como exato, porque não há como afirmar o contrário.
    """
    if not view or view == "ANY":
        return True
    alvo = re.escape(view)
    for t in nomes:
        up = f" {(t or '').upper()} "
        if re.search(rf"(?<![A-Z])[RLDE]?{alvo}(?![A-Z])", up):
            return True                       # MLO, RMLO, LCC, DMLO…
    for t in nomes:
        if alvo and view in (t or "").upper():
            return False                      # SMLO, SCC: a sigla está lá, com letra sobrando
    return True


def _side_of(lat: str, texts: list[str]) -> str:
    lat = (lat or "").upper().strip()
    if lat in ("R", "L"):
        return lat
    for t in texts:
        up = f" {(t or '').upper()} "
        if re.search(r"(?<![A-Z])(R|D|RT|DIR|DIREITA|RIGHT)(?![A-Z])|^R(CC|MLO|ML)", up.strip()) or \
                re.search(r"(?<![A-Z])R(CC|MLO|ML|LM)", up):
            return "R"
        if re.search(r"(?<![A-Z])(L|E|LT|ESQ|ESQUERDA|LEFT)(?![A-Z])", up) or re.search(r"(?<![A-Z])L(CC|MLO|ML|LM)", up):
            return "L"
    return ""


def energy_of(ds, texts: list[str]) -> str:
    """Mamografia com contraste: baixa energia, alta energia ou recombinada (subtraída)."""
    it = " ".join(str(x) for x in (ds.get("ImageType") or [])).upper()
    allt = "_" + re.sub(r"[\s\-\\/]+", "_", (it + " " + " ".join(t or "" for t in texts)).upper()) + "_"
    if "EnergyWeightingFactor" in ds or any(k in allt for k in ("RECOMB", "SUBTRACT", "DUAL_ENERGY_SUB", "CESM_SUB",
                                                                "CEM_SUB", "_DES_", "RECOMBINADA")):
        return "rec"
    if "HIGH_ENERGY" in allt or "ALTA_ENERGIA" in allt:
        return "high"
    if "LOW_ENERGY" in allt or "BAIXA_ENERGIA" in allt:
        return "low"
    return ""


TOMO_CLASSES = {"1.2.840.10008.5.1.4.1.1.13.1.3"}                   # Breast Tomosynthesis Image
PROJECTION_CLASSES = {"1.2.840.10008.5.1.4.1.1.13.1.4", "1.2.840.10008.5.1.4.1.1.13.1.5"}   # projeções (não lidas)

# A 2D sintetizada da tomossíntese — "V-Preview" no aparelho dele, "C-View" em outros serviços —
# é gravada com a **classe SOP da tomossíntese**, mas é uma imagem só. O que a distingue do volume
# está medido no acervo: 22 imagens com um quadro e `GENERATED_2D` no ImageType, contra 22 volumes
# de 14 a 60 cortes que dizem `MAXIMUM` ou `VOLUME`. Enquanto a classe SOP decidia sozinha, a
# V-Preview contava como tomossíntese: a célula 2D do protocolo não a achava, e no exame que só tem
# V-Preview e volume o quadro da CC abria o volume em vez da incidência.
TIPO_2D_SINTETICA = "GENERATED_2D"


def dois_d_sintetica(ds, nframes: int) -> bool:
    """A imagem é a 2D sintetizada da tomossíntese (uma imagem) e não o volume (cortes)?"""
    if nframes > 1:
        return False
    return TIPO_2D_SINTETICA in {str(x).upper() for x in (ds.get("ImageType") or ())}


def _frame_laterality(ds) -> str:
    for seq in ("SharedFunctionalGroupsSequence", "PerFrameFunctionalGroupsSequence"):
        try:
            fa = getattr(ds, seq)[0].FrameAnatomySequence[0]
            v = str(fa.get("FrameLaterality", "") or "")
            if v:
                return v
        except (AttributeError, IndexError, KeyError):
            continue
    return ""


def read_images(repo, study_uid: str) -> list[MgImage]:
    """Todas as imagens de MG do estudo, com lado e incidência (lidos dos cabeçalhos)."""
    import pydicom
    out = []
    for s in repo.series_for_study(study_uid):
        if s.modality not in ("MG", "DX", "CR", "OT") and "MAM" not in (s.description or "").upper():
            continue
        for inst in repo.instances_for_series(s.series_uid):
            try:
                ds = pydicom.dcmread(inst["path"], stop_before_pixels=True, force=True)
                sop_class = str(ds.get("SOPClassUID", ""))
                if sop_class in PROJECTION_CLASSES:
                    continue
            except Exception as e:  # noqa: BLE001
                log.debug("MG: cabeçalho ilegível %s: %s", inst["path"], e)
                continue
            if str(ds.get("Modality", s.modality)) not in ("MG", "DX", "CR") and s.modality != "MG":
                continue
            codes = []
            for item in ds.get("ViewCodeSequence", []) or []:
                codes.append(str(item.get("CodeMeaning", "")))
            # `nomes`: só o que **nomeia** a imagem. O ViewPosition e os códigos de incidência
            # dizem "MLO" tanto na MLO como na complementar SMLO; quem distingue é o nome.
            nomes = [str(ds.get("SeriesDescription", "")), str(ds.get("ImageComments", "")),
                     str(ds.get("AcquisitionDeviceProcessingDescription", "")), s.description or ""]
            rotulo = rotulo_da_incidencia(ds)
            # O rótulo do aparelho entra **depois** do ViewPosition e dos códigos (que são padrão)
            # e antes dos nomes; ele também diz a lateralidade, e serve de reserva para o lado.
            texts = [str(ds.get("ViewPosition", "")), *codes, rotulo, *nomes]
            side = _side_of(str(ds.get("ImageLaterality", "") or ds.get("Laterality", "") or _frame_laterality(ds)
                                or ""), texts)
            view = _view_of(texts)
            spot = any(w in " ".join(texts).upper() for w in ("SPOT", "COMPRESS", "MAGNIF"))
            if spot and view in ("", "CC", "MLO", "ML"):
                view = "MAG" if "MAGNIF" in " ".join(texts).upper() else "SPOT"
            nframes = int(inst.get("frames") or ds.get("NumberOfFrames", 1) or 1)
            sintetica = dois_d_sintetica(ds, nframes)
            tomo = (sop_class in TOMO_CLASSES or nframes > 1) and not sintetica
            if tomo and view in ("SPOT", "MAG"):
                view = _view_of(texts[:2]) or view
            energy = energy_of(ds, texts)
            sem_implante = eh_sem_implante(ds)
            if energy == "high":
                continue                    # alta energia sozinha não é lida (só baixa energia e recombinada)
            out.append(MgImage(study_uid, s.series_uid, inst["sop_uid"], 0, inst["path"],
                               side, view, str(ds.get("PresentationIntentType", "")).upper() == "FOR PROCESSING",
                               int(inst.get("instance_number") or 0), str(ds.get("AcquisitionTime", "") or ""),
                               nframes, tomo, energy,
                               incidencia_exata(rotulo, nomes, view), s.description or "", rotulo,
                               sintetica, sem_implante, fonte_da_copia(ds) if sem_implante else ""))
    return out


def pick_image(images: list[MgImage], cell: Cell, used: set[str] | None = None) -> MgImage | None:
    """A imagem para o quadro: mesmo lado e incidência; "para apresentação" antes de "para processamento";
    a mais recente (última aquisição) se houver repetição."""
    used = used or set()
    cands = same_view(images, cell)
    cands = [im for im in cands if im.sop_uid not in used] or cands[:0]
    if not cands:
        return None
    return cands[-1]


def same_view(images: list[MgImage], cell: Cell) -> list[MgImage]:
    """Imagens do mesmo lado e incidência (2D ou tomossíntese, conforme a célula), na ordem de aquisição;
    "para processamento" só se não houver "para apresentação"."""
    rec = getattr(cell, "rec", False)
    images = [im for im in images if (im.energy == "rec") == rec]
    cands = [im for im in images if im.side == cell.side and (cell.view == "ANY" or im.view == cell.view)
             and im.tomo == cell.tomo]
    if not cands and not cell.tomo:        # sem 2D (só tomossíntese): usa a tomo
        cands = [im for im in images if im.side == cell.side and (cell.view == "ANY" or im.view == cell.view)]
    pres = [im for im in cands if not im.for_processing]
    cands = pres or cands
    # Quem escolhe pega o **último** da lista: a incidência que o protocolo pediu vai para o fim,
    # e as variantes (complementares com o mesmo ViewPosition) ficam atrás dela. Entre iguais,
    # vale a mais recente.
    # Entre a 2D adquirida e a 2D sintetizada da tomossíntese, a adquirida: ela é a imagem que o
    # serviço processou para leitura. A sintetizada fica atrás dela na mesma lista do quadro — e
    # vira a escolha quando o exame não tem a adquirida daquela incidência.
    # A cópia sem implante (0.97) leva a hora e o número da original: fica logo **depois** dela e
    # vira a escolha do quadro — a original continua na lista, um passo atrás.
    cands.sort(key=lambda im: (bool(getattr(im, "exata", True)), not getattr(im, "sintetica", False),
                               im.time, im.number, bool(getattr(im, "sem_implante", False))))
    return cands


def lados_das_celulas(codigos) -> set[str]:
    """Lados ("R"/"L") que aparecem nestes códigos de quadro (os vazios e inválidos não contam)."""
    out = set()
    for c in codigos or ():
        cell = parse_code(c) if c else None
        if cell is not None:
            out.add(cell.side)
    return out


def parede_desejada(lado: str, col: int, cols: int, lados_juntos: set[str]) -> str | None:
    """Lado da TELA ("left"/"right") para onde a parede torácica do quadro deve ficar, ou None.

    `lado` é a mama do quadro ("R"/"L"); `col`/`cols`, a coluna dele e quantas há; `lados_juntos`,
    os lados das mamas que dividem a tela com ele (a linha do quadro, ou a etapa quando o monitor
    tem uma coluna só).

    **Com as duas mamas juntas, quem manda é a mama, não a coluna**: direita com a parede à direita,
    esquerda com a parede à esquerda — o costas com costas de sempre. Até a 0.96.0 mandava a coluna
    (metade esquerda da tela × metade direita), o que só acerta com duas colunas: numa linha de
    quatro (CCD, CCE, MLOD, MLOE) a CCE e a MLOD saíam espelhadas.

    Com uma mama só (atual × anterior da mesma mama), a coluna continua mandando: o par fica costas
    com costas. Com quatro ou mais colunas (número par), os pares são as colunas vizinhas.
    """
    if {"R", "L"} <= set(lados_juntos or ()) and lado in ("R", "L"):
        return "right" if lado == "R" else "left"
    if cols < 2:
        return None
    if cols % 2 == 0 and cols >= 4:
        return "right" if col % 2 == 0 else "left"
    if cols % 2 and col == cols // 2:
        return None
    return "right" if col < cols / 2 else "left"


def chest_wall_side(pixels: np.ndarray) -> str:
    """Lado ("left"/"right") da parede torácica na imagem: a borda com mais tecido encostado."""
    if pixels.ndim != 2 or pixels.shape[1] < 10:
        return ""
    px = pixels[:: max(1, pixels.shape[0] // 256), :].astype(np.float32)
    lo, hi = np.percentile(px, 2), np.percentile(px, 98)
    if hi <= lo:
        return ""
    n = max(2, px.shape[1] // 25)
    left = float(np.mean(px[:, :n] > lo + 0.25 * (hi - lo)))
    right = float(np.mean(px[:, -n:] > lo + 0.25 * (hi - lo)))
    if abs(left - right) < 0.1:
        return ""
    return "left" if left > right else "right"


def display_values(pixels: np.ndarray, monochrome1: bool = False) -> np.ndarray:
    """Valores com o tecido "claro" (MONOCHROME1 é invertido)."""
    return -pixels if monochrome1 else pixels


def breast_bbox(pixels: np.ndarray, monochrome1: bool = False) -> tuple[int, int, int, int] | None:
    """Caixa da mama na imagem (x0, y0, x1, y1), ignorando o fundo e letreiros pequenos."""
    if pixels.ndim != 2 or min(pixels.shape) < 16:
        return None
    step = max(1, max(pixels.shape) // 512)
    px = display_values(pixels[::step, ::step].astype(np.float32), monochrome1)
    lo, hi = np.percentile(px, 1), np.percentile(px, 99.5)
    if hi <= lo:
        return None
    tissue = px > lo + 0.08 * (hi - lo)
    cols = tissue.mean(axis=0) > 0.05
    rows = tissue.mean(axis=1) > 0.03
    if not cols.any() or not rows.any():
        return None
    xs, ys = np.nonzero(cols)[0], np.nonzero(rows)[0]
    x0, x1 = int(xs[0]) * step, min(pixels.shape[1], (int(xs[-1]) + 1) * step)
    y0, y1 = int(ys[0]) * step, min(pixels.shape[0], (int(ys[-1]) + 1) * step)
    if (x1 - x0) < pixels.shape[1] * 0.1 or (y1 - y0) < pixels.shape[0] * 0.1:
        return None
    return x0, y0, x1, y1


def _box_stats(a: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """Média e desvio padrão numa janela (2k+1)², com somas acumuladas (sem scipy)."""
    def caixa(x):
        out = x.astype(np.float64)
        for eixo in (1, 0):
            n = out.shape[eixo]
            c = np.cumsum(out, axis=eixo)
            c = np.pad(c, ((0, 0), (1, 0)) if eixo == 1 else ((1, 0), (0, 0)))
            i0 = np.clip(np.arange(n) - k, 0, n)
            i1 = np.clip(np.arange(n) + k + 1, 0, n)
            out = (c[:, i1] - c[:, i0]) if eixo == 1 else (c[i1, :] - c[i0, :])
        return out

    uns = caixa(np.ones_like(a, dtype=np.float64))
    m = caixa(a) / uns
    v = np.maximum(caixa(np.asarray(a, np.float64) ** 2) / uns - m * m, 0.0)
    return m.astype(np.float32), np.sqrt(v).astype(np.float32)


def _maior_componente(mask: np.ndarray, seed=None, atalho=None) -> np.ndarray:
    """Maior região conectada de `mask` (ou a que contém a semente).

    `atalho`: um ponto provável (o pixel mais claro, por exemplo) — se a região dele já for grande,
    evita varrer as outras, que é a parte cara.
    """
    from ipe.imaging.segment import _grow
    if not mask.any():
        return mask
    if seed is not None:
        return _grow(mask[None], (0, int(seed[0]), int(seed[1])))[0]
    if atalho is not None and mask[atalho]:
        reg = _grow(mask[None], (0, int(atalho[0]), int(atalho[1])))[0]
        if reg.sum() > 0.5 * mask.sum():
            return reg
    resto, melhor = mask.copy(), np.zeros_like(mask)
    for _ in range(12):                      # as maiores primeiro; 12 tentativas bastam
        if not resto.any():
            break
        ys, xs = np.nonzero(resto)
        reg = _grow(resto[None], (0, int(ys[0]), int(xs[0])))[0]
        if reg.sum() > melhor.sum():
            melhor = reg
        resto &= ~reg
        if melhor.sum() > resto.sum():       # ninguém mais pode ser maior
            break
    return melhor


# ------------------------------------------------------------------ implante (0.95)
# Medido no acervo dele (28 imagens 2D, 5 exames, 2 com prótese): a busca por "região lisa e clara"
# achava a prótese em 2 de 3 imagens num exame, dava máscara serrilhada no outro e inventava prótese
# nas incidências com o implante deslocado (Eklund). A busca nova vem da patente US 8.160.346: a
# prótese é a região clara de **borda forte e forma convexa**; o limiar que dá a borda mais nítida
# ganha, e a área tem de ficar entre 5 e 85% da mama. Achou as 7 próteses visíveis, com contorno liso.
# O que sobrava de erro (incidência deslocada, compressão localizada, mama densa) sai com o que o
# próprio aparelho escreve: a tag BreastImplantPresent e o rótulo da incidência (0045,101B).

def _media_caixa(a: np.ndarray, k: int) -> np.ndarray:
    """Média numa janela (2k+1)², borda replicada (sem scipy)."""
    if k <= 0:
        return a.astype(np.float32)
    out = a.astype(np.float32)
    for eixo in (0, 1):
        larg = ((k + 1, k), (0, 0)) if eixo == 0 else ((0, 0), (k + 1, k))
        c = np.cumsum(np.pad(out, larg, mode="edge"), axis=eixo, dtype=np.float64)
        out = ((c[2 * k + 1:] - c[:-2 * k - 1]) if eixo == 0 else (c[:, 2 * k + 1:] - c[:, :-2 * k - 1]))
        out = (out / (2 * k + 1)).astype(np.float32)
    return out


def borrar(a: np.ndarray, sigma: float) -> np.ndarray:
    """Quase uma gaussiana: três médias em caixa seguidas (variância k(k+1) ≈ sigma²)."""
    k = max(0, int(round(sigma)))
    out = a
    for _ in range(3):
        out = _media_caixa(out, k)
    return out


def _sem_buracos(reg: np.ndarray) -> np.ndarray:
    return _fecha_buracos(reg) if reg.any() else reg


def _busca_pela_borda(px: np.ndarray, breast: np.ndarray, info: list | None = None) -> np.ndarray | None:
    """A prótese na imagem reduzida: para cada limiar, a maior região clara; fica a de borda mais
    nítida entre as convexas, com contraste e com área plausível."""
    lo, hi = float(np.percentile(px, 1)), float(np.percentile(px, 99.8))
    faixa = max(hi - lo, 1e-6)
    s = min(px.shape)
    sm = borrar(px, s / 150)
    gy, gx = np.gradient(sm)
    grad = np.hypot(gx, gy)
    vals = sm[breast]
    if vals.size < 400:
        return None
    interior = _erode(breast, 3)
    atalho = np.unravel_index(int(np.argmax(np.where(breast, sm, -np.inf))), sm.shape)
    melhor, nota_m = None, 0.0
    for q in range(95, 30, -2):
        t = float(np.percentile(vals, q))
        comp = _maior_componente(breast & (sm > t), atalho=atalho)
        if not comp.any():
            continue
        frac = comp.sum() / breast.sum()
        if not 0.05 <= frac <= 0.85:
            continue
        k = max(2, int(np.sqrt(comp.sum()) / 5))
        grande = np.pad(comp, k)
        fechado = _erode(_dilate(grande, k), k)[k:-k, k:-k] | comp
        solidez = comp.sum() / max(1, fechado.sum())
        borda = comp & ~_erode(comp, 1) & interior
        anel = _dilate(comp, max(3, s // 40)) & ~comp & breast
        dentro = _erode(comp, 3)
        if borda.sum() < 15 or anel.sum() < 20 or dentro.sum() < 20:
            continue
        nitidez = float(np.median(grad[borda])) / faixa * s / 20
        contraste = (float(np.median(sm[dentro])) - float(np.median(sm[anel]))) / faixa
        if info is not None:
            info.append({"q": q, "frac": frac, "solidez": solidez, "nitidez": nitidez, "contraste": contraste})
        if solidez < 0.95 or contraste < 0.10 or nitidez < 0.30:
            continue
        nota = nitidez * solidez * contraste
        if nota > nota_m:
            melhor, nota_m = comp, nota
    return _sem_buracos(melhor) if melhor is not None else None


#: Marca da cópia com o implante corrigido que o programa grava na chegada (0.97). Vai no
#: DerivationDescription (é por ela que se reconhece a cópia) e o sufixo, na descrição da série
#: (é por ele que o envio ao PACS a deixa de fora — ela é só deste computador).
# Não muda com o nome do programa (0.99.11): entra na geração dos UIDs da série corrigida e é
# como a série é reconhecida — trocar duplicaria séries já corrigidas.
MARCA_SEM_IMPLANTE = "DicomViewer: implante corrigido"
SUFIXO_SEM_IMPLANTE = " · sem implante"


def eh_sem_implante(ds) -> bool:
    return MARCA_SEM_IMPLANTE in str(ds.get("DerivationDescription", "") or "")


def serie_sem_implante(descricao: str) -> bool:
    return (descricao or "").endswith(SUFIXO_SEM_IMPLANTE)


def fonte_da_copia(ds) -> str:
    try:
        return str(ds.SourceImageSequence[0].ReferencedSOPInstanceUID)
    except (AttributeError, IndexError, KeyError):
        return ""


#: incidências-padrão (rótulo da GE sem o lado): fora disso é compressão localizada, magnificação…
_INCIDENCIAS_PADRAO = {"CC", "MLO", "ML", "LM", "LMO", "XCCL", "XCCM", "XCC", "FB", "SIO", "AT", "CV"}


def implante_esperado(tags: dict) -> str:
    """"" se vale procurar a prótese sozinho nesta imagem; senão, o motivo (para a barra de estado).

    `tags`: BreastImplantPresent, o rótulo da incidência do aparelho (0045,101B) e os significados do
    ViewModifierCodeSequence. Sem nenhuma dessas informações, procura (aparelho que não as escreve)."""
    presente = str(tags.get("BreastImplantPresent", "") or "").strip().upper()
    if presente == "NO":
        return "a imagem diz que não há implante (BreastImplantPresent = NO)"
    mods = " ".join(str(m).lower() for m in (tags.get("modificadores") or []))
    if "implant displaced" in mods or "implant-displaced" in mods:
        return "incidência com o implante deslocado"
    rot = str(tags.get("rotulo", "") or "").strip().upper()
    if rot:
        corpo = rot[1:] if rot[:1] in ("R", "L") else rot
        if corpo.endswith("ID"):
            return f"incidência com o implante deslocado ({rot})"
        if corpo and corpo not in _INCIDENCIAS_PADRAO:
            return f"compressão localizada ou magnificação ({rot})"
    if "spot" in mods or "magnif" in mods:
        return "compressão localizada ou magnificação"
    return ""


@functools.lru_cache(maxsize=256)
def tags_do_implante(path: str) -> dict:
    """Lê do arquivo só o que decide se vale procurar a prótese (sem os pixels)."""
    try:
        import pydicom
        ds = pydicom.dcmread(path, stop_before_pixels=True,
                             specific_tags=[(0x0028, 0x1300), (0x0054, 0x0222), (0x0045, 0x101B)])
    except Exception:  # noqa: BLE001
        return {}
    rot = ds.get((0x0045, 0x101B))
    rot = rot.value if rot is not None else ""
    if isinstance(rot, bytes):
        rot = rot.decode("latin-1", errors="ignore")
    mods = []
    for it in ds.get("ViewModifierCodeSequence", []) or []:
        mods.append(str(getattr(it, "CodeMeaning", "")))
    return {"BreastImplantPresent": str(ds.get("BreastImplantPresent", "") or ""),
            "rotulo": str(rot).strip("\x00 "), "modificadores": mods}


def corrige_implante(pixels: np.ndarray, mask: np.ndarray, monochrome1: bool = False,
                     ganho: float = 1.5) -> np.ndarray:
    """A prótese "corrigida" (patente US 8.160.346): só a parte de baixa frequência dela desce ao
    nível do tecido em volta; o detalhe fino fica (com ganho). O que está na frente ou atrás do
    silicone continua visível, e não há degrau na borda. Devolve uma cópia; o arquivo não muda."""
    if pixels.ndim != 2 or mask is None or mask.shape != pixels.shape or not mask.any():
        return pixels
    step = max(1, max(pixels.shape) // 1024)       # as contas de baixa frequência numa grade menor
    dv = display_values(pixels.astype(np.float32), monochrome1)
    m = mask.astype(np.float32)
    pq, mq = dv[::step, ::step], m[::step, ::step]
    s = min(pq.shape)
    sig = s / 40
    lp_in = borrar(pq * mq, sig) / np.maximum(borrar(mq, sig), 1e-3)     # baixa frequência só do implante
    anel = _dilate(mq > 0.5, max(3, s // 30)) & (mq < 0.5)
    tecido = anel & (pq > np.percentile(pq, 5))
    if tecido.sum() < 20:
        return pixels
    alvo = float(np.percentile(pq[tecido], 60))
    w = borrar(mq, max(1.0, s / 300))                 # passagem de 1–2 pixels na borda
    lp = borrar(pq, sig / 4)
    if step > 1:
        def cheio(a):
            return np.repeat(np.repeat(a, step, axis=0), step, axis=1)[: dv.shape[0], : dv.shape[1]]
        lp_in, w, lp = cheio(lp_in), cheio(w), cheio(lp)
    detalhe = dv - lp
    out = dv - w * (lp_in - alvo) + w * (ganho - 1.0) * detalhe
    return (-out if monochrome1 else out).astype(np.float32)


def implant_mask(pixels: np.ndarray, monochrome1: bool = False, seed=None) -> np.ndarray | None:
    """Prótese de silicone: região **grande, clara e lisa** (sem a textura do tecido fibroglandular).

    O que separa o implante do tecido não é só a densidade — mama densa também é clara — e sim a
    **ausência de textura**: o silicone é uma área homogênea. `seed` (linha, coluna na imagem) faz a
    busca a partir de um ponto escolhido pelo usuário, para quando a detecção automática não acerta.
    """
    if pixels.ndim != 2 or min(pixels.shape) < 32:
        return None
    step = max(1, max(pixels.shape) // 320)   # a prótese é grande: 320 px bastam e é bem mais rápido
    px = display_values(pixels[::step, ::step].astype(np.float32), monochrome1)
    lo, hi = np.percentile(px, 1), np.percentile(px, 99.8)
    if hi <= lo:
        return None
    breast = px > lo + 0.08 * (hi - lo)
    if breast.sum() < 400:
        return None
    k = max(2, min(px.shape) // 40)
    _m, textura = _box_stats(px, k)
    dentro = textura[breast]
    claro = px > np.percentile(px[breast], 45)
    if seed is not None:
        sy, sx = int(seed[0]) // step, int(seed[1]) // step
        sy, sx = int(np.clip(sy, 0, px.shape[0] - 1)), int(np.clip(sx, 0, px.shape[1] - 1))
        base = float(px[sy, sx])
        faixa = max(0.06 * (hi - lo), float(np.percentile(dentro, 60)) * 2.5)
        cand = breast & (np.abs(px - base) <= faixa)
        reg = _maior_componente(cand, (sy, sx))
        minimo = 0.01
    else:
        # 0.95: borda forte + forma convexa (ver _busca_pela_borda)
        reg = _busca_pela_borda(px, _sem_buracos(_maior_componente(breast)))
        if reg is None:
            return None
        minimo = 0.05
    if reg.sum() < minimo * breast.sum():
        return None
    if seed is not None:
        reg = _borda_do_implante(px, breast, reg, hi - lo)   # recupera a beirada perdida pela janela de textura
    reg = _fecha_buracos(reg)
    if step > 1:
        reg = np.repeat(np.repeat(reg, step, axis=0), step, axis=1)[: pixels.shape[0], : pixels.shape[1]]
        reg = refine_border(pixels, reg, step, monochrome1)
    return reg


def _borda_do_implante(px: np.ndarray, breast: np.ndarray, reg: np.ndarray, faixa: float) -> np.ndarray:
    """A janela usada para medir a textura corta a beirada do implante; esta etapa a traz de volta,
    aceitando os vizinhos com valor parecido com o do miolo."""
    vals = px[reg]
    if vals.size < 50:
        return reg
    centro = float(np.median(vals))
    tol = max(0.05 * faixa, 3.0 * float(np.std(vals)), float(np.percentile(vals, 98) - centro))
    cand = breast & (np.abs(px - centro) <= tol)
    ys, xs = np.nonzero(reg)
    maior = _maior_componente(cand | reg, seed=(int(np.median(ys)), int(np.median(xs))))
    return maior if maior.sum() >= reg.sum() else reg


def _fecha_buracos(reg: np.ndarray) -> np.ndarray:
    """Tapa os buracos da região (calcificações e dobras dentro do implante)."""
    fundo = ~reg
    borda = np.zeros_like(reg)
    borda[0, :] = borda[-1, :] = borda[:, 0] = borda[:, -1] = True
    sementes = np.nonzero(fundo & borda)
    if not len(sementes[0]):
        return reg
    from ipe.imaging.segment import _grow
    de_fora = np.zeros_like(reg)
    for y, x in zip(sementes[0][::37], sementes[1][::37]):     # algumas sementes bastam
        if de_fora[y, x]:
            continue
        de_fora |= _grow(fundo[None], (0, int(y), int(x)))[0]
    return reg | (fundo & ~de_fora)          # o que é fundo mas não se liga à borda é buraco


def _erode(mask: np.ndarray, k: int) -> np.ndarray:
    """Encolhe a máscara em k pixels (sem scipy): soma em caixa do complemento, em dois passos separados
    (linha e coluna), para não criar matrizes de índice do tamanho da imagem."""
    if k <= 0:
        return mask
    a = (~mask).astype(np.int32)
    for eixo in (1, 0):
        n = a.shape[eixo]
        c = np.cumsum(a, axis=eixo, dtype=np.int32)
        c = np.pad(c, ((0, 0), (1, 0)) if eixo == 1 else ((1, 0), (0, 0)))
        i0 = np.clip(np.arange(n) - k, 0, n)
        i1 = np.clip(np.arange(n) + k + 1, 0, n)
        a = (c[:, i1] - c[:, i0]) if eixo == 1 else (c[i1, :] - c[i0, :])
    return mask & (a == 0)


def _dilate(mask: np.ndarray, k: int) -> np.ndarray:
    return ~_erode(~mask, k)


def _suaviza(mask: np.ndarray, k: int) -> np.ndarray:
    """Maioria numa janela (2k+1)²: tira o serrilhado e os pontinhos soltos da borda."""
    if k <= 0:
        return mask
    a = mask.astype(np.float32)
    uns = np.ones_like(a)
    for eixo in (1, 0):
        n = a.shape[eixo]
        i0 = np.clip(np.arange(n) - k, 0, n)
        i1 = np.clip(np.arange(n) + k + 1, 0, n)
        for nome in ("a", "uns"):
            x = a if nome == "a" else uns
            c = np.cumsum(x, axis=eixo)
            c = np.pad(c, ((0, 0), (1, 0)) if eixo == 1 else ((1, 0), (0, 0)))
            y = (c[:, i1] - c[:, i0]) if eixo == 1 else (c[i1, :] - c[i0, :])
            if nome == "a":
                a = y
            else:
                uns = y
    return (a / np.maximum(uns, 1e-6)) > 0.5


def refine_border(pixels: np.ndarray, reg: np.ndarray, step: int, monochrome1: bool = False) -> np.ndarray:
    """Cola a borda da máscara no contorno real, na resolução cheia.

    A prótese é procurada numa imagem reduzida (rápido); ao voltar para o tamanho original a borda fica
    em degraus. Aqui, só na faixa em volta do contorno grosso, cada pixel é decidido pelo seu próprio
    valor — o limiar fica no meio do caminho entre o silicone e o tecido vizinho — e o resultado passa
    por um filtro de maioria. O contorno sai liso, com a precisão de 1 pixel.
    """
    if step <= 1 or not reg.any():
        return reg
    h, w = pixels.shape[:2]
    ys, xs = np.nonzero(reg)
    m = 2 * step
    y0, y1 = max(0, int(ys.min()) - m), min(h, int(ys.max()) + m + 1)
    x0, x1 = max(0, int(xs.min()) - m), min(w, int(xs.max()) + m + 1)
    corte = reg[y0:y1, x0:x1]
    dv = display_values(pixels[y0:y1, x0:x1].astype(np.float32), monochrome1)
    largo = _dilate(corte, step)
    anel = largo & ~_erode(corte, step)
    dentro, fora = dv[_erode(corte, step)], dv[anel & ~corte]
    if dentro.size < 50 or fora.size < 50:
        return reg
    limiar = 0.5 * (float(np.median(dentro)) + float(np.median(fora)))
    fino = largo & (dv >= limiar)
    fino = _suaviza(fino, max(1, step // 2))
    if fino.sum() < 0.6 * corte.sum() or fino.sum() > 1.8 * corte.sum():
        return reg                      # deu errado: fica com a máscara grossa
    out = np.zeros_like(reg)
    out[y0:y1, x0:x1] = fino
    return out


def implant_core(mask: np.ndarray, shape, rim: float = 0.0015) -> np.ndarray:
    """O miolo do implante: a máscara sem a faixa da cápsula (que continua com os valores originais)."""
    k = int(max(1, round(rim * max(shape))))
    miolo = _erode(mask, k)
    return miolo if miolo.any() else mask


def implant_window(pixels: np.ndarray, monochrome1: bool = False,
                   seed=None) -> tuple[tuple[float, float], np.ndarray] | None:
    """Janela calculada só no tecido mamário (sem o implante). Devolve ((largura, nível), máscara) ou None."""
    m = implant_mask(pixels, monochrome1, seed)
    if m is None:
        return None
    px = pixels.astype(np.float32)
    dv = display_values(px, monochrome1)
    lo_all, hi_all = np.percentile(dv, 1), np.percentile(dv, 99.8)
    tissue = (dv > lo_all + 0.08 * (hi_all - lo_all)) & ~m
    if tissue.sum() < 100:
        return None
    a, b = np.percentile(px[tissue], [2, 99.5])
    if b <= a:
        return None
    return (float(b - a), float((a + b) / 2)), m


# ------------------------------------------------------------------ rodada mama P2 (0.99.61)
def mascara_da_mama(pixels: np.ndarray, monochrome1: bool = False) -> np.ndarray | None:
    """Máscara da mama (tecido + pele) no tamanho da imagem: o maior pedaço acima do fundo, sem buracos.
    Serve para "inverter só a mama" (o fundo continua preto) e para achar o mamilo."""
    if pixels.ndim != 2 or min(pixels.shape) < 16:
        return None
    step = max(1, max(pixels.shape) // 512)
    px = display_values(pixels[::step, ::step].astype(np.float32), monochrome1)
    lo, hi = np.percentile(px, 1), np.percentile(px, 99.5)
    if hi <= lo:
        return None
    tecido = px > lo + 0.08 * (hi - lo)
    reg = _maior_componente(tecido)
    if reg.sum() < 0.02 * reg.size:
        return None
    reg = _sem_buracos(reg)
    cheia = np.repeat(np.repeat(reg, step, axis=0), step, axis=1)[: pixels.shape[0], : pixels.shape[1]]
    if cheia.shape != pixels.shape:                       # imagem não múltipla do passo
        out = np.zeros(pixels.shape, bool)
        out[: cheia.shape[0], : cheia.shape[1]] = cheia
        cheia = out
    return cheia


def mamilo(pixels: np.ndarray, monochrome1: bool = False, lado_parede: str = "") -> tuple[float, float] | None:
    """Ponto aproximado do mamilo (x, y em pixels): o ponto da pele mais longe da parede torácica — na CC e
    na MLO é ali que o mamilo fica. A altura é a média das linhas da mama na faixa mais distante (2% da
    profundidade), para um pelo ou um pixel solto não decidirem."""
    m = mascara_da_mama(pixels, monochrome1)
    if m is None:
        return None
    lado = lado_parede or chest_wall_side(pixels)
    if lado not in ("left", "right"):
        return None
    cols = np.nonzero(m.any(axis=0))[0]
    if not len(cols):
        return None
    prof = cols[-1] - cols[0] + 1
    faixa = max(2, int(0.02 * prof))
    if lado == "left":                                  # parede à esquerda: o mamilo é a coluna mais à direita
        x0, x1, xm = cols[-1] - faixa, cols[-1] + 1, float(cols[-1])
    else:
        x0, x1, xm = cols[0], cols[0] + faixa, float(cols[0])
    ys = np.nonzero(m[:, x0:x1].any(axis=1))[0]
    if not len(ys):
        return None
    return xm, float(ys.mean())


ALINHAMENTOS = {"mamilo": "Pelo mamilo (as duas mamas na mesma altura)",
                "meio": "Pelo meio da mama"}
ALINHAMENTO_PADRAO = "mamilo"


def alinhamento_do_protocolo(proto: dict | None) -> str:
    v = str((proto or {}).get("alinhar") or ALINHAMENTO_PADRAO)
    return v if v in ALINHAMENTOS else ALINHAMENTO_PADRAO

# Quadros de outro exame no protocolo da mamografia (PV 19): "US" e "RM", com filtro opcional da série
# depois de dois-pontos ("RM:SUB"). Pegam o exame mais recente do paciente com essa modalidade e da mama.
OUTROS = {"US": "US", "RM": "MR", "MR": "MR"}
_OUTRO = re.compile(r"^\s*(US|RM|MR)\s*(?::\s*(.*))?$", re.I)
_MAMA = re.compile(r"MAMA|MAMAR|MAMÁR|BREAST|MAMOGR|AXILA", re.I)
SERIE_RM_PREFERIDA = ["SUB", "SUBTR", "POS", "PÓS", "C\\+", "GD", "DYN", "DIN", "T1"]


def parse_outro(code: str) -> tuple[str, str] | None:
    """"US" → ("US", ""); "RM:SUB" → ("MR", "SUB"); o resto → None."""
    m = _OUTRO.match(code or "")
    if not m:
        return None
    return OUTROS[m.group(1).upper()], (m.group(2) or "").strip()


def rotulo_outro(mod: str) -> str:
    return "Última US" if mod == "US" else "Última RM"


def estudo_outro(rows, mod: str, data_limite: str, excluir: str = ""):
    """O exame mais recente (até `data_limite`, inclusive o mesmo dia) do paciente com a modalidade `mod`.
    Prefere os da mama (pela descrição); sem nenhum, aceita qualquer um dessa modalidade."""
    cands = [r for r in rows if r.study_uid != excluir and mod in (r.modalities or "").upper().replace("\\", " ").split()
             and (r.study_date or "") <= (data_limite or "99999999")]
    if not cands:
        cands = [r for r in rows if r.study_uid != excluir and mod in (r.modalities or "").upper()
                 and (r.study_date or "") <= (data_limite or "99999999")]
    da_mama = [r for r in cands if _MAMA.search(r.description or "")]
    pool = da_mama or cands
    if not pool:
        return None, False
    return max(pool, key=lambda r: (r.study_date or "", r.study_uid)), bool(da_mama)


def serie_outra(series, mod: str, filtro: str = ""):
    """A série do quadro: a que tem o filtro na descrição; sem filtro, na RM a primeira pela ordem de
    preferência (subtração, pós-contraste, dinâmica, T1); na US, a com mais imagens."""
    ss = [s for s in series if (s.num_images or 0) > 0 and (s.modality or "").upper() == mod]
    if not ss:
        ss = [s for s in series if (s.num_images or 0) > 0]
    if not ss:
        return None
    if filtro:
        try:
            pat = re.compile(filtro, re.I)
        except re.error:
            pat = re.compile(re.escape(filtro), re.I)
        achou = [s for s in ss if pat.search(s.description or "")]
        if achou:
            return achou[0]
    if mod == "MR":
        for p in SERIE_RM_PREFERIDA:
            pat = re.compile(rf"(?<![A-Z]){p}", re.I)
            achou = [s for s in ss if pat.search(s.description or "")]
            if achou:
                return max(achou, key=lambda s: s.num_images or 0)
    return max(ss, key=lambda s: s.num_images or 0)
