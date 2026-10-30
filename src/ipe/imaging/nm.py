"""Medicina nuclear: leitura do módulo NM Multi-frame (PS3.3 C.8.4.8).

Um arquivo de medicina nuclear guarda vários quadros num cubo só, e quem diz o que é
cada quadro são os *vetores* do grupo 0054. Cada vetor tem um valor (base 1) por quadro:

===================  ===========  ====================================================
Vetor                Tag          Separa
===================  ===========  ====================================================
Energy Window        (0054,0010)  janela de energia (duplo isótopo: paratireoide, leucócitos)
Detector             (0054,0020)  cabeça da gama-câmara (ANT × POST)
Phase                (0054,0030)  fase do dinâmico (fluxo × pool × tardia)
Rotation             (0054,0050)  rotação do SPECT
R-R Interval         (0054,0060)  intervalo R-R do gated
Time Slot            (0054,0070)  intervalo de tempo do gated (MUGA)
Slice                (0054,0080)  corte do SPECT reconstruído
Angular View         (0054,0090)  projeção do SPECT
Time Slice           (0054,0100)  quadro do dinâmico
===================  ===========  ====================================================

Sem desempacotar isso, um renograma ou um gated vira uma pilha de quadros sem sentido.

O mesmo exame pode vir de duas formas, e as duas aparecem aqui: um arquivo só com
todos os quadros, ou um arquivo por vista (comum em corpo inteiro ANT/POST). Por isso
o desmembramento trabalha sobre a lista de quadros da série, não sobre um arquivo.

Nada aqui depende de Qt. Só numpy e pydicom.
"""

from __future__ import annotations

import logging
import math
import re
from collections import OrderedDict
from dataclasses import dataclass, field

import numpy as np
import pydicom

log = logging.getLogger(__name__)

# chave interna -> (tag do vetor, tag da contagem, tag da sequência de informação, nome)
VECTORS: dict[str, tuple[tuple[int, int], tuple[int, int], tuple[int, int] | None, str]] = {
    "energy":     ((0x0054, 0x0010), (0x0054, 0x0011), (0x0054, 0x0012), "Janela de energia"),
    "detector":   ((0x0054, 0x0020), (0x0054, 0x0021), (0x0054, 0x0022), "Detector"),
    "phase":      ((0x0054, 0x0030), (0x0054, 0x0031), (0x0054, 0x0032), "Fase"),
    "rotation":   ((0x0054, 0x0050), (0x0054, 0x0051), (0x0054, 0x0052), "Rotação"),
    "rr":         ((0x0054, 0x0060), (0x0054, 0x0061), None, "Intervalo R-R"),
    "time_slot":  ((0x0054, 0x0070), (0x0054, 0x0071), (0x0054, 0x0072), "Intervalo de tempo"),
    "slice":      ((0x0054, 0x0080), (0x0054, 0x0081), None, "Corte"),
    "angular":    ((0x0054, 0x0090), None, None, "Projeção"),
    "time_slice": ((0x0054, 0x0100), (0x0054, 0x0101), None, "Quadro"),
}

# ordem em que os eixos são oferecidos ao usuário (o que separa vista vem antes)
AXIS_ORDER = ["detector", "energy", "phase", "rotation", "rr", "time_slot",
              "angular", "slice", "time_slice"]

# eixos que geram *vistas* separadas (imagens que devem aparecer lado a lado),
# em oposição aos que geram quadros de uma mesma vista (tempo, corte, projeção)
VIEW_AXES = ["detector", "energy", "phase", "rotation"]

# texto da ViewCodeSequence -> sigla usada na tela
VIEW_NAMES: list[tuple[tuple[str, ...], str]] = [
    (("right anterior oblique", "rao"), "OAD"),
    (("left anterior oblique", "lao"), "OAE"),
    (("right posterior oblique", "rpo"), "OPD"),
    (("left posterior oblique", "lpo"), "OPE"),
    (("right lateral",), "LAT D"),
    (("left lateral",), "LAT E"),
    (("anterior", "frontal"), "ANT"),
    (("posterior",), "POST"),
    (("lateral",), "LAT"),
    (("superior",), "SUP"),
    (("inferior",), "INF"),
]

# siglas de vista escritas na descrição da série ("ANT POST PERF", "OAD OPE PERF", "LD LE PERF").
# Muitas câmaras não gravam a ViewCodeSequence, e aí a descrição é a única fonte da vista.
# "POS" NÃO entra: em português é "pós" (pós-micção), não posterior.
TEXT_VIEWS: dict[str, str] = {
    "ANT": "ANT", "ANTERIOR": "ANT", "AP": "ANT",
    "POST": "POST", "POSTERIOR": "POST", "PA": "POST",
    "OAD": "OAD", "OAE": "OAE", "OPD": "OPD", "OPE": "OPE",
    "RAO": "OAD", "LAO": "OAE", "RPO": "OPD", "LPO": "OPE",
    "LD": "LAT D", "LE": "LAT E", "LLAT": "LAT E", "RLAT": "LAT D",
}

# palavras que aparecem em SeriesType (0054,1000)
TYPE_NAMES = {
    "STATIC": "Estática", "DYNAMIC": "Dinâmica", "GATED": "Sincronizada",
    "WHOLE BODY": "Corpo inteiro", "TOMO": "SPECT", "GATED TOMO": "SPECT sincronizado",
    "RECON TOMO": "SPECT reconstruído", "RECON GATED TOMO": "SPECT sincronizado reconstruído",
}


# ------------------------------------------------------------------ utilidades
def _ints(v) -> list[int]:
    if v is None:
        return []
    if isinstance(v, (int, float)):
        return [int(v)]
    try:
        return [int(x) for x in v]
    except (TypeError, ValueError):
        return []


def _num(v, default: float = 0.0) -> float:
    try:
        if isinstance(v, (list, tuple, pydicom.multival.MultiValue)):
            v = v[0] if len(v) else None
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _code_meaning(item) -> str:
    """Texto da primeira ViewCodeSequence do item, em minúsculas."""
    try:
        return str(item[(0x0054, 0x0220)].value[0].CodeMeaning).strip().lower()
    except (KeyError, AttributeError, IndexError, TypeError):
        return ""


def views_in_text(text: str, n: int) -> list[str]:
    """Siglas de vista escritas na descrição, em ordem — ["ANT", "POST"] em "ANT POST PERF".

    Só vale quando o número de siglas bate com o número de detectores: se a descrição diz duas
    vistas e a câmara gravou dois detectores, a ordem da descrição é a ordem dos detectores.
    Qualquer outra combinação devolve [] — chutar de qual lado é cada imagem inverte direita e
    esquerda no laudo, então na dúvida não se rotula.
    """
    if n < 2:
        return []
    achadas = []
    for palavra in re.split(r"[^A-Za-z]+", (text or "").upper()):
        sigla = TEXT_VIEWS.get(palavra)
        if sigla and sigla not in achadas:
            achadas.append(sigla)
    return achadas if len(achadas) == n else []


def view_abbrev(text: str) -> str:
    """"anterior" -> "ANT". Texto desconhecido volta em maiúsculas, sem inventar sigla."""
    t = (text or "").strip().lower()
    if not t:
        return ""
    for words, abbrev in VIEW_NAMES:
        if any(w in t for w in words):
            return abbrev
    return t.upper()[:10]


# ------------------------------------------------------------------ eixos
@dataclass
class NMAxis:
    """Um vetor do grupo 0054 já desempacotado."""
    key: str
    name: str
    vector: list[int]          # valor (base 1) de cada quadro
    size: int
    labels: list[str] = field(default_factory=list)   # rótulo de cada valor (índice = valor - 1)

    def label(self, value: int) -> str:
        if 1 <= value <= len(self.labels) and self.labels[value - 1]:
            return self.labels[value - 1]
        return f"{self.name} {value}"

    def frames_of(self, value: int) -> list[int]:
        """Índices dos quadros com este valor."""
        return [i for i, v in enumerate(self.vector) if v == value]


def _axis_labels(ds, key: str, size: int) -> list[str]:
    """Rótulos de um eixo, lidos da sequência de informação correspondente."""
    _vec_tag, _n_tag, seq_tag, name = VECTORS[key]
    if seq_tag is None:
        return []
    try:
        seq = ds[seq_tag].value
    except (KeyError, TypeError):
        return []
    out: list[str] = []
    for i in range(size):
        item = seq[i] if i < len(seq) else None
        text = ""
        if item is not None:
            if key == "detector":
                text = view_abbrev(_code_meaning(item))
            elif key == "energy":
                text = str(item.get("EnergyWindowName", "") or "").strip()
            elif key == "phase":
                ms = _num(item.get("ActualFrameDuration"))
                n = int(_num(item.get("NumberOfFramesInPhase"), 0))
                if ms and n:
                    text = f"Fase {i + 1} · {n} × {_dur(ms)}"
                elif ms:
                    text = f"Fase {i + 1} · {_dur(ms)}"
        out.append(text or f"{name} {i + 1}")
    return out


def _dur(ms: float) -> str:
    """Duração de quadro legível: 2 s, 30 s, 5 min."""
    s = ms / 1000.0
    if s < 1:
        return f"{ms:.0f} ms"
    if s < 90:
        return f"{s:g} s"
    return f"{s / 60:g} min"


# ------------------------------------------------------------------ cabeçalho
@dataclass
class NMInfo:
    """Tudo que o cabeçalho NM diz sobre um arquivo."""
    path: str = ""
    modality: str = ""
    n_frames: int = 1
    series_type: list[str] = field(default_factory=list)
    axes: list[NMAxis] = field(default_factory=list)
    frame_duration_ms: float = 0.0            # ActualFrameDuration do arquivo (fallback)
    phase_duration_ms: list[float] = field(default_factory=list)   # duração por fase
    image_id: str = ""
    description: str = ""
    radiopharm: dict = field(default_factory=dict)

    @property
    def is_nm(self) -> bool:
        return self.modality == "NM"

    def axis(self, key: str) -> NMAxis | None:
        return next((a for a in self.axes if a.key == key), None)

    @property
    def kind(self) -> str:
        """Tipo da série em português, a partir de SeriesType (0054,1000)."""
        parts = [TYPE_NAMES.get(t.upper(), t.title()) for t in self.series_type
                 if t.upper() not in ("IMAGE", "")]
        return " · ".join(parts)

    @property
    def is_tomo(self) -> bool:
        """Reconstruído (eixo de corte) ou as projeções que vão gerar a reconstrução (eixo angular)."""
        return (any("TOMO" in t.upper() for t in self.series_type)
                or self.axis("slice") is not None or self.axis("angular") is not None)

    @property
    def is_dynamic(self) -> bool:
        return self.axis("time_slice") is not None or self.axis("phase") is not None

    @property
    def is_gated(self) -> bool:
        return self.axis("time_slot") is not None or self.axis("rr") is not None

    def durations_ms(self) -> list[float]:
        """Duração de cada quadro, em ms. Usa a duração por fase quando existe."""
        n = self.n_frames
        ph = self.axis("phase")
        seq = self.phase_duration_ms
        if ph is not None and seq:
            return [seq[v - 1] if 1 <= v <= len(seq) and seq[v - 1] else self.frame_duration_ms
                    for v in ph.vector[:n]]
        return [self.frame_duration_ms] * n

    def start_times_s(self, frames: list[int] | None = None) -> list[float]:
        """Início de cada quadro, em segundos desde o primeiro. Só faz sentido no dinâmico."""
        d = self.durations_ms()
        idx = list(range(self.n_frames)) if frames is None else frames
        t, out = 0.0, []
        for i in idx:
            out.append(t / 1000.0)
            t += d[i] if i < len(d) else self.frame_duration_ms
        return out

    def mid_times_s(self, frames: list[int] | None = None) -> list[float]:
        """Meio de cada quadro — é o tempo certo para plotar numa curva atividade-tempo."""
        d = self.durations_ms()
        idx = list(range(self.n_frames)) if frames is None else frames
        start = self.start_times_s(frames)
        return [s + (d[i] if i < len(d) else self.frame_duration_ms) / 2000.0
                for s, i in zip(start, idx)]


def read_info(ds, path: str = "") -> NMInfo:
    """Lê os vetores NM de um dataset já aberto (sem pixels)."""
    n = int(_num(ds.get("NumberOfFrames"), 1)) or 1
    info = NMInfo(
        path=path,
        modality=str(ds.get("Modality", "") or "").upper(),
        n_frames=n,
        series_type=[str(x) for x in (ds.get((0x0054, 0x1000)).value
                                      if (0x0054, 0x1000) in ds else [])],
        frame_duration_ms=_num(ds.get("ActualFrameDuration"), 0.0),
        image_id=str(ds.get((0x0054, 0x0400)).value if (0x0054, 0x0400) in ds else "") or "",
        description=str(ds.get("SeriesDescription", "") or ""),
        radiopharm=read_radiopharm(ds),
    )
    phase_dur: list[float] = []
    if (0x0054, 0x0032) in ds:
        try:
            phase_dur = [_num(it.get("ActualFrameDuration"), 0.0) for it in ds[(0x0054, 0x0032)].value]
        except (TypeError, AttributeError):
            phase_dur = []
    for key in AXIS_ORDER:
        vec_tag, n_tag, _seq, name = VECTORS[key]
        if vec_tag not in ds:
            continue
        vector = _ints(ds[vec_tag].value)
        if not vector:
            continue
        if len(vector) < n:                 # cabeçalho curto: completa com o último valor
            vector = vector + [vector[-1]] * (n - len(vector))
        vector = vector[:n]
        size = int(_num(ds.get(n_tag), 0)) if n_tag else 0
        size = max(size, max(vector, default=1))
        info.axes.append(NMAxis(key, name, vector, size, _axis_labels(ds, key, size)))
    info.phase_duration_ms = phase_dur
    return info


def read_radiopharm(ds) -> dict:
    """Radiofármaco: nome, dose (Bq), meia-vida (s) e horário da injeção."""
    seq = ds.get((0x0054, 0x0016))
    seq = seq.value if seq is not None else None
    if not seq:
        return {}
    rp = seq[0]
    start = str(rp.get("RadiopharmaceuticalStartDateTime", "") or "")
    if not start:
        date = str(ds.get("SeriesDate", "") or ds.get("StudyDate", "") or "")
        start = date + str(rp.get("RadiopharmaceuticalStartTime", "") or "")
    return {
        "name": str(rp.get("Radiopharmaceutical", "") or "").strip(),
        "dose_bq": _num(rp.get("RadionuclideTotalDose"), 0.0),
        "half_life_s": _num(rp.get("RadionuclideHalfLife"), 0.0),
        "start": start,
    }


_CACHE: OrderedDict[str, NMInfo] = OrderedDict()


def info_for_file(path: str) -> NMInfo:
    """Cabeçalho NM de um arquivo, com cache (a tira de séries pergunta muitas vezes)."""
    hit = _CACHE.get(path)
    if hit is not None:
        _CACHE.move_to_end(path)
        return hit
    try:
        ds = pydicom.dcmread(path, stop_before_pixels=True, force=True)
        info = read_info(ds, path)
    except Exception as e:  # noqa: BLE001 - arquivo ilegível não pode derrubar a tira
        log.debug("NM: não leu o cabeçalho de %s: %s", path, e)
        info = NMInfo(path=path)
    if len(_CACHE) > 512:
        _CACHE.popitem(last=False)
    _CACHE[path] = info
    return info


def clear_cache() -> None:
    _CACHE.clear()


# ------------------------------------------------------------------ vistas
@dataclass
class NMView:
    """Um pedaço da série que deve ser mostrado como uma imagem (ou um cine) só."""
    key: str                       # identificador estável, entra no uid do quadro
    label: str                     # o que aparece na tela ("ANT", "POST", "ANT · Tc-99m")
    frames: list = field(default_factory=list)          # list[Frame]
    axis_values: dict = field(default_factory=dict)     # {"detector": 1, ...}
    info: NMInfo | None = None
    inferred: bool = False         # a vista veio da descrição, não da ViewCodeSequence

    @property
    def n(self) -> int:
        return len(self.frames)

    @property
    def display(self) -> str:
        """Rótulo para a tela: vista deduzida da descrição vem marcada como tal."""
        return f"{self.label} (da descrição)" if self.inferred else self.label

    @property
    def is_anterior(self) -> bool:
        return "ANT" in self.label.upper().split()

    @property
    def is_posterior(self) -> bool:
        return "POST" in self.label.upper().split()


def series_view_axes(frames: list) -> dict[str, int]:
    """Tamanho de cada eixo de vista **na série inteira**, não em cada arquivo.

    Existe porque a mesma série pode misturar arquivos de dois detectores com arquivos de um só
    (aquisição repetida, por exemplo). Decidindo o eixo por arquivo, cada um criava as próprias
    vistas e a série aparecia partida em pedaços que não combinam.
    """
    tamanhos: dict[str, int] = {}
    for path in dict.fromkeys(f.path for f in frames):
        info = info_for_file(path)
        if not info.is_nm:
            return {}
        for key in VIEW_AXES:
            ax = info.axis(key)
            if ax is not None:
                tamanhos[key] = max(tamanhos.get(key, 0), ax.size)
    return {k: v for k, v in tamanhos.items() if v > 1}


def _axis_names(frames: list, key: str, size: int) -> tuple[list[str], bool]:
    """(rótulos de cada valor do eixo, se vieram deduzidos da descrição).

    Para o detector, a ViewCodeSequence é a fonte boa. Faltando ela — que é o caso comum —
    tenta-se a descrição da série ("ANT POST PERF"), e o resultado fica marcado como deduzido.
    """
    nomes = [""] * size
    for path in dict.fromkeys(f.path for f in frames):
        ax = info_for_file(path).axis(key)
        if ax is None:
            continue
        for i, texto in enumerate(ax.labels[:size]):
            padrao = f"{ax.name} {i + 1}"
            if i < size and not nomes[i] and texto and texto != padrao:
                nomes[i] = texto
    if all(nomes) or key != "detector":
        return nomes, False
    for path in dict.fromkeys(f.path for f in frames):
        info = info_for_file(path)
        siglas = views_in_text(info.description or info.image_id, size)
        if siglas:
            return siglas, True
    return nomes, False


def split_views(frames: list, max_views: int = 32) -> list[NMView]:
    """Separa os quadros de uma série NM nas vistas que devem aparecer lado a lado.

    Quebra pelos eixos de *vista* (detector, janela de energia, fase, rotação); os eixos de
    tempo, corte e projeção ficam como quadros dentro de cada vista. Os eixos são decididos
    para a série inteira, então arquivos diferentes caem nas mesmas vistas.

    Devolve [] quando não há o que separar — a série é mostrada do jeito normal.
    """
    if not frames:
        return []
    eixos = series_view_axes(frames)
    rotulos: dict[str, tuple[list[str], bool]] = {
        k: _axis_names(frames, k, v) for k, v in eixos.items()}
    ordem = [k for k in VIEW_AXES if k in eixos]
    buckets: OrderedDict[tuple, NMView] = OrderedDict()

    for f in frames:
        info = info_for_file(f.path)
        values: dict[str, int] = {}
        parts: list[str] = []
        deduzido = False
        for key in ordem:
            ax = info.axis(key)
            if ax is not None and ax.vector:
                i = min(f.frame_index, len(ax.vector) - 1)
                v = ax.vector[i]
            else:
                v = 1                      # arquivo que não declara o eixo: primeiro valor
            values[key] = v
            nomes, marcado = rotulos[key]
            nome = nomes[v - 1] if 1 <= v <= len(nomes) and nomes[v - 1] else ""
            parts.append(nome or f"{VECTORS[key][3]} {v}")
            deduzido = deduzido or (marcado and bool(nome))
        if not values:
            # arquivo por vista: o próprio ImageID ("ANT"/"POST") é o que separa
            tag = view_abbrev(info.image_id) if info.image_id else ""
            if not tag:
                return []
            values, parts = {"image_id": tag}, [tag]
        ident = tuple(sorted(values.items()))
        view = buckets.get(ident)
        if view is None:
            if len(buckets) >= max_views:
                return []
            key = "-".join(f"{k}{v}" for k, v in sorted(values.items()))
            buckets[ident] = view = NMView(key, " · ".join(parts), [], dict(values), info, deduzido)
        view.frames.append(f)

    views = list(buckets.values())
    if len(views) < 2:
        return []
    return sorted(views, key=_view_order)


def _view_order(v: NMView) -> tuple:
    """ANT antes de POST; no resto, a ordem dos valores dos eixos."""
    pref = 0 if v.is_anterior else (1 if v.is_posterior else 2)
    return (pref, tuple(v.axis_values.get(k, 0) for k in VIEW_AXES))


def pair_ant_post(views: list[NMView]) -> tuple[NMView, NMView] | None:
    """A dupla ANT/POST, se existir — é o que o layout de corpo inteiro precisa."""
    ant = next((v for v in views if v.is_anterior), None)
    post = next((v for v in views if v.is_posterior), None)
    return (ant, post) if ant is not None and post is not None else None


# ------------------------------------------------------------------ contas
def geometric_mean(ant: np.ndarray, post: np.ndarray, flip_post: bool = True) -> np.ndarray:
    """√(ANT × POST), a combinação que compensa a profundidade da fonte.

    A vista posterior é a imagem espelhada da anterior: sem inverter uma das duas, a média
    soma o fígado com o baço. `flip_post=False` só para câmara que já grava espelhado.
    """
    a = np.asarray(ant, dtype=np.float64)
    p = np.asarray(post, dtype=np.float64)
    if flip_post:
        p = p[:, ::-1]
    if a.shape != p.shape:
        raise ValueError("ANT e POST têm tamanhos diferentes; não dá para combinar.")
    return np.sqrt(np.clip(a, 0, None) * np.clip(p, 0, None)).astype(np.float32)


def decay_factor(half_life_s: float, seconds: float) -> float:
    """Fator que desfaz o decaimento: contagens × fator = contagens no instante zero."""
    if half_life_s <= 0:
        return 1.0
    return float(math.exp(math.log(2) * seconds / half_life_s))


def decay_correct(counts, times_s, half_life_s: float):
    """Corrige uma série de contagens pelo decaimento físico do radionuclídeo."""
    c = np.asarray(counts, dtype=np.float64)
    t = np.asarray(times_s, dtype=np.float64)
    if half_life_s <= 0:
        return c.astype(np.float32)
    return (c * np.exp(math.log(2) * t / half_life_s)).astype(np.float32)


def counts_per_second(counts, durations_ms):
    """Contagens por segundo — o que permite comparar quadros de duração diferente."""
    c = np.asarray(counts, dtype=np.float64)
    d = np.asarray(durations_ms, dtype=np.float64) / 1000.0
    return np.divide(c, d, out=np.zeros_like(c), where=d > 0).astype(np.float32)


HALF_LIVES_S = {           # meia-vida dos radionuclídeos que aparecem aqui, em segundos
    "TC99M": 6.0058 * 3600,
    "I123": 13.2234 * 3600,
    "I131": 8.0252 * 24 * 3600,
    "GA67": 3.2617 * 24 * 3600,
    "IN111": 2.8047 * 24 * 3600,
    "TL201": 3.0456 * 24 * 3600,
    "LU177": 6.647 * 24 * 3600,
}


def half_life_for(info: NMInfo) -> float:
    """Meia-vida em segundos: a do cabeçalho; se faltar, a tabela pelo nome do radiofármaco."""
    hl = float(info.radiopharm.get("half_life_s") or 0.0)
    if hl > 0:
        return hl
    name = str(info.radiopharm.get("name") or "").upper().replace("-", "").replace(" ", "")
    for key, value in HALF_LIVES_S.items():
        if key in name:
            return value
    return 0.0
