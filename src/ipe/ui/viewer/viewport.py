"""Viewport 2D: exibe uma série, com ferramentas de mouse, overlay clicável e medidas.

Desenho feito com QPainter (rápido e simples para 2D). MPR e 3D virão com VTK
em outra classe de viewport, reaproveitando a mesma lógica de mouse e overlay.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QRunnable, QThreadPool, Qt, QTimer, Signal, QObject
from PySide6.QtGui import QTransform
from PySide6.QtGui import (
    QAction, QColor, QFont, QFontMetrics, QImage, QKeyEvent, QMouseEvent, QPainter, QPen,
    QPolygonF, QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QInputDialog, QMenu, QMessageBox, QWidget

from ipe.core.i18n import tr
from ipe.imaging import measure as M
from ipe.imaging.measure import Annotation
from ipe.imaging.series import Frame, FrameCache, FrameImage  # noqa: F401
from ipe.imaging import colormaps as CM
from ipe.imaging.windowing import auto_window, orientation_labels, to_display

log = logging.getLogger(__name__)

from ipe.ui.viewer.annotate import (  # noqa: E402,F401
    ANNOT_TOOLS, CLICK_TOOLS, MEASURE_COLOR, RASCUNHAVEIS, SELECTED_COLOR, TOOLS, AnnotationMixin,
)


TOMO_DIAL = "tomodial"          # área clicável do indicador de profundidade da tomossíntese
CBAR = {"cbar_hi": "topo", "cbar_lo": "base"}    # números clicáveis da barra de cores
# Áreas clicáveis que também respondem ao botão direito — nelas, o direito é o sentido
# contrário do esquerdo (a fase da dinâmica anda para a frente e para trás).
HOTSPOTS_DOS_DOIS_BOTOES = {"fase"}


def _source_uid(uid: str) -> str:
    """Série de origem (reconstruções "mpr:<uid>:<eixo>" contam como a própria série)."""
    return uid.split(":")[1] if uid.startswith("mpr:") and uid.count(":") >= 2 else uid


def colormap_icon(key: str):
    from PySide6.QtGui import QIcon, QPixmap
    g = np.tile(np.linspace(0, 255, 48).astype(np.uint8), (14, 1))
    rgb = np.ascontiguousarray(CM.apply(g, key))
    q = QImage(rgb.data, 48, 14, rgb.strides[0], QImage.Format_RGB888).copy()
    return QIcon(QPixmap.fromImage(q))


@dataclass
class ViewState:
    width: float = 400.0
    level: float = 40.0
    zoom: float = 1.0           # multiplicador sobre "ajustar à janela"
    pan: QPointF = field(default_factory=lambda: QPointF(0, 0))
    invert: bool = False
    cmap: str = ""              # tabela de cores ("" = cinza)
    rot: int = 0                # giro da exibição: 0, 90, 180, 270 (horário)
    flip_h: bool = False        # espelho esquerda ↔ direita (aplicado antes do giro)
    flip_v: bool = False        # espelho cima ↕ baixo
    window_set: bool = False    # o usuário já mexeu na janela?
    filter: str = ""            # filtro de imagem (imaging.filters): nitidez ou suavização


class _Prefetch(QRunnable):
    def __init__(self, cache: FrameCache, frames: list[Frame], order: list[int],
                 token: list[bool]):
        super().__init__()
        self.cache, self.frames, self.order, self.token = cache, frames, order, token

    def run(self) -> None:
        for i in self.order:
            if not self.token[0]:
                return
            f = self.frames[i]
            if not self.cache.contains(f):
                try:
                    self.cache.get(f)
                except Exception as e:  # noqa: BLE001
                    log.debug("prefetch falhou %s: %s", f.path, e)


class ViewportSignals(QObject):
    activated = Signal(object)            # viewport clicado
    tool_requested = Signal(str)          # hotspot pediu troca de ferramenta
    plane_menu_requested = Signal(object, object)   # viewport, posição global: menu de plano
    plane_rotate_requested = Signal(object, float, float)   # viewport, graus horizontal, vertical
    series_menu_requested = Signal(object, object)   # viewport, posição global
    empty_clicked = Signal(object, object)           # quadro vazio clicado: escolher a série (0.99.11)
    maximize_requested = Signal(object)
    frame_changed = Signal(object)
    view_changed = Signal(object, str)          # viewport, "window" | "zoom" | "pan"
    cursor_moved = Signal(object, object)       # viewport, ponto 3D (mm)
    key_toggle_requested = Signal(object)
    sync_group_requested = Signal(object)       # clique no ícone de corrente
    button_action = Signal(object, str)         # botões laterais do mouse -> ação
    annotations_changed = Signal(object)        # medida criada, editada ou apagada
    tic_requested = Signal(object, object)      # viewport, anotação de curva tempo-intensidade
    join_requested = Signal(object, str)        # série solta no canto "+ fase"
    oblique_requested = Signal(object, object, object)   # viewport, p0, p1 (mm)
    reconstruction_save_requested = Signal(object, bool)   # viewport, só a imagem atual
    hover_moved = Signal(object, float, float)   # viewport, posição na imagem (px) sem botão
    curved_requested = Signal(object, object)   # viewport, pontos 3D (mm) do caminho
    quadrant_cycle = Signal(object, int)            # viewport, +1 próximo quadrante / -1 anterior
    quadrant_requested = Signal(object, int)        # viewport, quadrante 0..3 (-1 = imagem inteira)
    implant_changed = Signal(object)                # o implante apagado mudou neste quadro
    orgaos_requested = Signal(object)               # segmentar órgãos abdominais desta série (0.98)
    coluna_requested = Signal(object)               # identificar vértebras e discos desta série (0.99.2)
    renumerar_requested = Signal(object, int)       # níveis da coluna: todos andam ±1 (0.99.2)
    numeracao_requested = Signal(object, object)    # coluna: Ajustar a numeração (vp, ponto mm ou None; 0.99.23)
    film_requested = Signal(object)             # ferramenta "enviar ao filme": clique na imagem
    group_action = Signal(object, str)          # "remove_phase" | "ungroup"
    lesion_requested = Signal(object, object)   # viewport, anotação: ligar a uma lesão
    clone_roi_requested = Signal(object, object)  # viewport, anotação: clonar a ROI nos outros quadros
    histogram_requested = Signal(object)        # viewport: mostrar o histograma
    anotacoes_requested = Signal(str)           # nível de anotação escolhido no botão direito (0.99.9)
    copy_requested = Signal(object)             # "Copiar imagem" no botão direito (0.99.9)
    segment_requested = Signal(object, float, float)   # viewport, ponto clicado (px da imagem)
    pincel = Signal(object, float, float, str)  # viewport, ponto (px da imagem), "ini" | "meio" | "fim" (0.99.40)
    annotation_picked = Signal(object, object)  # viewport, medida escolhida (ou None)
    reflines_toggled = Signal(bool)             # mostrar/ocultar as linhas de corte das outras séries
    phase_changed = Signal(object)              # o quadro trocou de fase da dinâmica
    status_message = Signal(str)                # recado curto para a barra de estado
    enquadre_pendente = Signal(object)          # o quadro mudou de tamanho e o enquadramento da mama
                                                # precisa ser refeito (o zoom depende do tamanho)


class Viewport(AnnotationMixin, QWidget):
    def __init__(self, cache: FrameCache, settings, parent: QWidget | None = None):
        super().__init__(parent)
        self.cache = cache
        self.settings = settings
        self.sig = ViewportSignals()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(120, 120)
        self.setAcceptDrops(True)

        self.frames: list[Frame] = []
        self.series_uid: str = ""
        self._filter_key = None
        self._filter_img = None
        # subtração digital (DSA): ligada, qual quadro é a máscara, modo e deslocamento
        self.dsa = {"on": False, "mask": 0, "avg": 1, "mode": "log", "dy": 0, "dx": 0, "invert": False}
        self.cardiac = None            # série 4D (cortes × fases), quando detectada
        self._dsa_mask = None
        self._gsdf_key = None
        self._gsdf_lut = None
        self.series_label: str = ""
        self.study_info: dict = {}
        self.index = 0
        self.state = ViewState()
        self._left_tool = "wl"
        self.active = False
        self.anonymize = False
        self._capturando = False          # pintando a cópia do Ctrl+C (sem moldura, ícones nem realce)
        self._anot_vis = None
        self.case_label = ""                 # nome amigável do caso (modo reunião)
        self.suv_factor: float | None = None  # PET: Bq/ml × fator = SUVbw
        self.annotations: list[Annotation] = []
        self.annotation_store = None         # objeto com load/save/delete (banco); None = só na sessão
        self.selected: Annotation | None = None
        self._draft: Annotation | None = None   # medida sendo desenhada por cliques
        self._spine_start = "L1"
        self.for_uid = ""                    # FrameOfReferenceUID (sincronização)
        self.study_uid = ""
        self.modality = ""
        self.ref_planes: list[tuple[np.ndarray, np.ndarray, QColor]] = []   # linhas de referência
        self.cursor_point: np.ndarray | None = None
        self.key_frames: set[tuple[str, int]] = set()
        self.sync_color: QColor | None = None
        self.sync_label: str = ""
        self.fusion = None                     # imaging.fusion.Fusion sobreposta (ex.: PET na TC)
        self._fusion_cache: tuple | None = None
        self.fusion_value: float | None = None
        self._curve_pts: list = []             # pontos do MPR curvo sendo marcados (mm)
        self.curve_paths: list = []            # caminhos já usados, para mostrar
        self.align_edge: str | None = None       # "left"/"right": encosta a imagem nessa borda da tela
        self.mg_cell = None                      # quadro de um protocolo de mamografia (coluna, colunas)
        self._loupe: QPointF | None = None
        self.loupe_zoom = float(self.settings.get("viewer.loupe_zoom", 3.0) or 3.0)
        self.quad_idx = -1
        self.anat_lock: tuple | None = None    # (fx, fy, zoom): enquadramento refeito ao trocar de imagem
        self._anat_box_norm = None             # caixa da mama em proporção, para a tomo cair no mesmo lugar
        self.mg_spec = None
        self.mg_tomo = False
        self.cine_bounce = False
        self.empty_note = ""
        self.lesion_names: dict = {}           # id da lesão -> nome (acompanhamento de lesões)
        self.implant_mask = False              # mamografia: implante "apagado" (prótese lisa)
        self.implant_found: bool | None = None
        self.implant_seed = None               # ponto (linha, coluna) escolhido à mão dentro da prótese
        self.implant_motivo = ""               # por que não procurou sozinho (tag do aparelho, 0.95)
        self._implant_cache = None
        self.tomo_slab = 1                     # tomossíntese: espessura em cortes (1 = fino)
        self.tomo_range: tuple[int, int] | None = None   # mamografia: índices [início, fim) dos cortes da tomo
        self.tomo_slab_mode = "mip"            # "mip" | "avg"
        self.overlays: list = []               # objetos de CAD/IA/anotações (SR, SEG, RTSTRUCT, GSPS)
        self.ghosts: list = []                 # (tipo, pontos, cor): contornos de outros quadros
        self.ann_colors: dict = {}             # id(anotação) -> cor (curvas da dinâmica)
        self.dyn_key: str | None = None        # mapa/fase mostrado na avaliação dinâmica
        self.oblique_targets: list = []       # quadros com um oblíquo desenhado a partir deste
        self._obl_draft: list | None = None
        self.mpr_plane = None                # MPRPlane quando o quadro mostra uma reconstrução
        self.render3d = None                 # View3D quando o quadro mostra o volume em 3D
        # fases (série dinâmica montada a partir de várias séries)
        self.phases: list[list[Frame]] | None = None
        self.phase_labels: list[str] = []
        self.phase = 0
        self.subtract = False
        self._cine_phases = False
        self._drag_zone: str | None = None

        self._img: FrameImage | None = None
        self._qimage: QImage | None = None
        self._qimage_key: tuple | None = None
        self._hotspots: dict[str, QRectF] = {}
        self._hover: str | None = None
        self._cursor_por_tecla = False      # o ponteiro mudou por causa de uma tecla segurada
        self._ultimo_hover = None
        self._acc_tecla = 0.0
        self._press: dict | None = None
        self._press_done: dict = {}
        self._prefetch_token = [False]
        self._cine = QTimer(self)
        self._cine.timeout.connect(self._cine_tick)

    # ------------------------------------------------------------ dados
    def set_series(self, series_uid: str, frames: list[Frame], label: str, study_info: dict,
                   start_index: int | None = None) -> None:
        self._prefetch_token[0] = False
        self.render3d = None
        keep = self.state.cmap if _source_uid(series_uid) == _source_uid(self.series_uid or "") else ""
        self.align_edge = None
        self.empty_note = ""
        self.quad_idx = -1
        self.anat_lock = self._anat_box_norm = None
        self.mg_spec = None
        self.mg_tomo = False
        self.cine_bounce = False
        self.tomo_slab = 1
        self.tomo_range = None
        self._win_seg = None
        self._seg_windows = {}
        self.implant_found = None
        self.implant_mask = False
        self.implant_seed = None
        self._implant_cache = None
        self.series_uid, self.frames, self.series_label = series_uid, frames, label
        try:
            from ipe.imaging.cardiac import detect as _detect_4d
            self.cardiac = _detect_4d(frames)
        except Exception:  # noqa: BLE001
            log.exception("detecção 4D")
            self.cardiac = None
        self.study_info = study_info
        self.phases, self.phase_labels, self.phase, self.subtract = None, [], 0, False
        self.index = len(frames) // 2 if start_index is None else start_index
        self.state = ViewState(cmap=keep)
        self._draft = None
        self.selected = None
        self.annotations = self._load_annotations()
        self._img = None
        self._qimage_key = None
        self._load_current()
        self.suv_factor = None
        mod = (self._img.header.get("Modality", "") if self._img is not None else "") or self.modality
        if frames and mod == "PT":
            from ipe.imaging.suv import suv_factor_for_file
            self.suv_factor = suv_factor_for_file(frames[0].path)[0]
        if frames and mod == "NM" and self.settings is not None \
                and self.settings.get("nm.invert", True):
            # medicina nuclear se lê com a captação escura; é a convenção da área
            self.state.invert = True
        if not self.state.cmap:
            self.state.cmap = self.cor_padrao()
        self._start_prefetch()
        self.update()

    # ------------------------------------------------------------ fases
    def set_phases(self, group_uid: str, phases: list[list[Frame]], labels: list[str], label: str,
                   study_info: dict, phase: int = 0, start_index: int | None = None) -> None:
        phase = max(0, min(phase, len(phases) - 1))
        self.set_series(group_uid, phases[phase], label, study_info, start_index)
        self.phases, self.phase_labels, self.phase = phases, labels, phase
        self.annotations = self._load_annotations()
        self._qimage_key = None
        self._load_current()
        self.update()

    def set_phase(self, p: int, wrap: bool = False) -> None:
        if not self.phases:
            return
        n = len(self.phases)
        p = p % n if wrap else max(0, min(n - 1, p))
        if p == self.phase:
            return
        from ipe.imaging.phases import map_index
        idx = map_index(self.phases[self.phase], self.index, self.phases[p])
        self.cancel_draft()
        self.phase, self.frames, self.index = p, self.phases[p], idx
        self._qimage_key = None
        self._load_current()
        self.update()
        self.sig.phase_changed.emit(self)

    def set_subtract(self, on: bool) -> None:
        self.subtract = on and bool(self.phases)
        self.state.window_set = False
        self._qimage_key = None
        self._load_current()
        self.update()

    def phase_text(self) -> str:
        if not self.phases:
            return ""
        sub = "  subtração" if self.subtract and self.phase > 0 else ""
        pais = float(getattr(self, "paisagem", 0.0) or 0.0)
        if sub and pais > 0:
            sub += f" + {pais * 100:.0f}% anatomia"
        return f"Fase {self.phase + 1}/{len(self.phases)}{sub}  ◂▸"

    #: frações da anatomia que a paisagem devolve à subtração
    PAISAGENS = (0.0, 0.1, 0.2, 0.3, 0.5)

    def set_paisagem(self, fracao: float) -> None:
        """Mistura a anatomia de volta na subtração para localizar o realce (mamilo, clipe, pele)
        sem trocar de série. 0 = subtração pura."""
        self.paisagem = max(0.0, min(1.0, float(fracao)))
        if self.subtract:
            self.state.window_set = False
            self._qimage_key = None
            self._load_current()
            self.update()

    def show_phase_menu(self, global_pos) -> None:
        if not self.phases:
            return
        menu = QMenu(self)
        for i, lab in enumerate(self.phase_labels):
            a = QAction(f"Fase {i + 1}: {lab}", menu, checkable=True, checked=(i == self.phase))
            a.triggered.connect(lambda _=False, k=i: self.set_phase(k))
            menu.addAction(a)
        menu.addSeparator()
        sub = QAction("Subtração (fase − pré-contraste)", menu, checkable=True, checked=self.subtract)
        sub.triggered.connect(self.set_subtract)
        menu.addAction(sub)
        pm = menu.addMenu("Paisagem (anatomia na subtração)")
        pm.setEnabled(self.subtract)
        atual = float(getattr(self, "paisagem", 0.0) or 0.0)
        for f in self.PAISAGENS:
            a = QAction("Sem anatomia (subtração pura)" if f == 0 else f"{f * 100:.0f}% da anatomia", pm,
                        checkable=True, checked=abs(f - atual) < 1e-6)
            a.triggered.connect(lambda _=False, ff=f: self.set_paisagem(ff))
            pm.addAction(a)
        cine = QAction("Cine das fases", menu)
        cine.triggered.connect(lambda: self.toggle_cine(phases=True))
        menu.addAction(cine)
        menu.addSeparator()
        rm = QAction("Tirar esta fase do grupo", menu)
        rm.triggered.connect(lambda: self.sig.group_action.emit(self, "remove_phase"))
        menu.addAction(rm)
        ung = QAction("Desfazer o grupo", menu)
        ung.triggered.connect(lambda: self.sig.group_action.emit(self, "ungroup"))
        menu.addAction(ung)
        menu.exec(global_pos)

    def clear(self) -> None:
        self._prefetch_token[0] = False
        self.frames, self.series_uid, self._img = [], "", None
        self.update()

    def _start_prefetch(self) -> None:
        if len(self.frames) < 2 or self.frames[0].is_virtual:
            return
        token = [True]
        self._prefetch_token = token
        # a partir do corte atual, alternando para cima e para baixo
        order, n = [], len(self.frames)
        for d in range(1, n):
            for j in (self.index + d, self.index - d):
                if 0 <= j < n:
                    order.append(j)
        QThreadPool.globalInstance().start(_Prefetch(self.cache, self.frames, order, token))

    def _load_current(self) -> None:
        if not self.frames:
            return
        try:
            self._img = self.cache.get(self.frames[self.index])
            if self.subtract and self.phases and self.phase > 0 and not self._img.is_color:
                from ipe.imaging.phases import map_index
                pre_f = self.phases[0][map_index(self.frames, self.index, self.phases[0])]
                pre = self.cache.get(pre_f)
                if pre.pixels.shape == self._img.pixels.shape:
                    from dataclasses import replace
                    # paisagem (0.99.22, plano AW M11): devolve uma fração da anatomia à subtração
                    k = 1.0 - float(getattr(self, "paisagem", 0.0) or 0.0)
                    self._img = replace(self._img, pixels=self._img.pixels - k * pre.pixels, window=None)
            if self.dsa.get("on") and len(self.frames) > 1 and not self._img.is_color:
                self._img = self._dsa_image(self._img)
            if self.tomo_slab > 1 and self.in_tomo() and not self._img.is_color and len(self.frames) > 1:
                self._img = self._slab_image()
        except Exception as e:  # noqa: BLE001
            log.error("Erro lendo %s: %s", self.frames[self.index].path, e)
            self._img = None
            return
        if getattr(self, "anat_lock", None) is not None:
            self.reapply_anat()                 # mesmo lugar da mama na imagem nova (tomo, recombinada…)
        implante = self._implant_info()
        self._switch_window_segment()
        if not self.state.window_set and not self._img.is_color:
            # 0.96: a janela é a de antes de tirar o silicone (pedido dele) — não a do tecido
            w, l = self._img.window or self._auto_window()
            self.state.width, self.state.level = w, l
        if implante is not None:
            self._corrige_implante_now(implante[2])

    # ------------------------------------------------------------ subtração digital (DSA)
    def _dsa_mask_pixels(self) -> np.ndarray | None:
        """Pixels da máscara (um quadro ou a média dos primeiros), guardados entre os quadros."""
        from ipe.imaging import dsa as D
        base = int(self.dsa.get("mask", 0))
        media = max(1, int(self.dsa.get("avg", 1)))
        chave = (self.series_uid, base, media, len(self.frames))
        if getattr(self, "_dsa_key", None) == chave and self._dsa_mask is not None:
            return self._dsa_mask
        try:
            pedaco = self.frames[base:base + media] or self.frames[:1]
            pixels = [self.cache.get(f).pixels for f in pedaco]
            self._dsa_mask = D.mask_pixels(pixels, len(pixels))
        except Exception:  # noqa: BLE001
            log.exception("máscara da DSA")
            self._dsa_mask = None
        self._dsa_key = chave
        return self._dsa_mask

    def _dsa_image(self, img):
        """A imagem já subtraída da máscara."""
        from dataclasses import replace

        from ipe.imaging import dsa as D
        mask = self._dsa_mask_pixels()
        if mask is None or mask.shape != img.pixels.shape:
            return img
        try:
            sub = D.subtract(img.pixels, mask, self.dsa.get("mode", "log"),
                             int(self.dsa.get("dy", 0)), int(self.dsa.get("dx", 0)),
                             invert=bool(self.dsa.get("invert", False)))
            sub = D.paisagem(sub, img.pixels, float(self.dsa.get("paisagem", 0.0) or 0.0),
                             bool(self.dsa.get("invert", False)))
        except Exception:  # noqa: BLE001
            log.exception("subtração DSA")
            return img
        cabecalho = dict(img.header)
        cabecalho["_monochrome1"] = "0"                 # a subtraída é sempre "quanto maior, mais claro"
        return replace(img, pixels=sub, window=D.auto_window(sub), header=cabecalho)

    def set_dsa(self, **mudancas) -> None:
        """Liga/desliga ou ajusta a subtração; a janela é recalculada porque os valores mudam."""
        antes = dict(self.dsa)
        self.dsa.update(mudancas)
        if any(self.dsa.get(k) != antes.get(k) for k in ("on", "mode", "paisagem")):
            self.state.window_set = False
        self._dsa_key = None
        self._qimage_key = None
        self._load_current()
        self.update()
        self.sig.view_changed.emit(self, "dsa")

    def dsa_status(self) -> str:
        if not self.dsa.get("on"):
            return ""
        d = self.dsa
        desloc = f", deslocada {d['dy']:+d}/{d['dx']:+d} px" if (d.get("dy") or d.get("dx")) else ""
        pais = float(d.get("paisagem", 0.0) or 0.0)
        pais_txt = f", paisagem {pais * 100:.0f}%" if pais > 0 else ""
        return f"DSA: máscara no quadro {int(d.get('mask', 0)) + 1}{desloc}{pais_txt}"

    def _corrige_implante_now(self, mascara) -> None:
        from dataclasses import replace
        from ipe.imaging.mammo import corrige_implante
        mono1 = self._img.header.get("_monochrome1") == "1"
        self._img = replace(self._img, pixels=corrige_implante(self._img.pixels, mascara, mono1), window=None)

    def _implant_info(self, so_cache: bool = False) -> tuple[tuple[float, float], np.ndarray, np.ndarray] | None:
        """Acha a prótese e devolve ((largura, nível) do tecido, miolo a apagar, máscara inteira).
        Guardado por imagem. Sem ponto clicado, só procura quando o arquivo não diz que não há prótese
        nem que a incidência é deslocada/localizada (0.95) — o motivo fica em `implant_motivo`."""
        if not self.implant_mask or self._img is None or self._img.is_color:
            return None
        f = self.frames[self.index] if self.frames else None
        chave = (getattr(f, "path", ""), getattr(f, "frame_index", 0), self._img.pixels.shape,
                 self.implant_seed, self.tomo_slab)     # pelo QUADRO: não muda ao trocar _img pela cópia
        guardado = getattr(self, "_implant_cache", None)
        if guardado is not None and guardado[0] == chave:
            self.implant_found = guardado[1] is not None
            return guardado[1]
        if so_cache:
            return None
        from ipe.imaging.mammo import implant_core, implant_window, implante_esperado, tags_do_implante
        self.implant_motivo = ""
        if self.implant_seed is None and f is not None and getattr(f, "path", ""):
            self.implant_motivo = implante_esperado(tags_do_implante(f.path))
        if self.implant_motivo:
            res = None
        else:
            mono1 = self._img.header.get("_monochrome1") == "1"
            try:
                res = implant_window(self._img.pixels, mono1, self.implant_seed)
            except Exception as e:  # noqa: BLE001
                log.warning("implante: %s", e)
                res = None
        self.implant_found = res is not None
        info = None if res is None else (res[0], implant_core(res[1], self._img.pixels.shape), res[1])
        self._implant_cache = (chave, info)
        return info

    def _auto_window(self) -> tuple[float, float]:
        """Janela quando o arquivo não traz uma. Mamografia/tomossíntese: só no tecido; na tomo, a mesma janela
        para todos os cortes (calculada no corte do meio), para não piscar ao rolar."""
        from ipe.imaging.windowing import tissue_window
        img = self._img
        mono1 = img.header.get("_monochrome1") == "1"
        is_mg = self.mg_spec is not None or (self.modality or "").upper() == "MG" or self.tomo_range is not None
        if not is_mg:
            return auto_window(img.pixels)
        if self.in_tomo() and self.tomo_range is not None:
            key = (self.series_uid, self.tomo_range)
            hit = getattr(self, "_tomo_auto", None)
            if hit is not None and hit[0] == key:
                return hit[1]
            a, b = self.tomo_range
            mid = self.frames[a + (b - a) // 2]
            try:
                px = img.pixels if mid is self.frames[self.index] else self.cache.get(mid).pixels
            except Exception:  # noqa: BLE001
                px = img.pixels
            win = tissue_window(px, mono1)
            self._tomo_auto = (key, win)
            return win
        return tissue_window(img.pixels, mono1)

    def _switch_window_segment(self) -> None:
        """Mamografia com 2D e tomo na mesma lista: cada parte guarda a sua janela (a da 2D não serve na tomo)."""
        if self.tomo_range is None:
            self._win_seg = None
            return
        seg = "tomo" if self.in_tomo() else "2d"
        cur = getattr(self, "_win_seg", None)
        if cur == seg:
            return
        saved = getattr(self, "_seg_windows", {})
        if cur is not None:
            saved[cur] = (self.state.width, self.state.level, self.state.window_set)
        self._seg_windows = saved
        self._win_seg = seg
        if seg in saved:
            self.state.width, self.state.level, self.state.window_set = saved[seg]
        else:
            self.state.window_set = False

    def _slab_image(self):
        """Tomossíntese com espessura: MIP (ou média) dos cortes em volta do atual."""
        from dataclasses import replace
        half = self.tomo_slab // 2
        a, b = self.tomo_range or (0, len(self.frames))
        lo, hi = max(a, self.index - half), min(b, self.index + half + 1)
        stack = []
        for i in range(lo, hi):
            px = self._img.pixels if i == self.index else self.cache.get(self.frames[i]).pixels
            if px.shape == self._img.pixels.shape:
                stack.append(px)
        if len(stack) < 2:
            return self._img
        arr = np.stack(stack)
        mono1 = self._img.header.get("_monochrome1") == "1"
        if self.tomo_slab_mode == "avg":
            out = arr.mean(axis=0)
        else:
            out = arr.min(axis=0) if mono1 else arr.max(axis=0)
        return replace(self._img, pixels=out.astype(np.float32))

    def in_tomo(self, index: int | None = None) -> bool:
        """O quadro mostra um corte de tomossíntese? (na mamografia, 2D e tomo ficam na mesma lista)"""
        i = self.index if index is None else index
        if self.tomo_range is not None:
            return self.tomo_range[0] <= i < self.tomo_range[1]
        return bool(self.mg_tomo)

    def set_tomo_slab(self, n: int, mode: str | None = None) -> None:
        self.tomo_slab = max(1, int(n))
        if mode:
            self.tomo_slab_mode = mode
        self._qimage_key = None
        self._load_current()
        self.update()

    def set_implant_mask(self, on: bool, seed=None) -> None:
        """Liga/desliga o implante corrigido (o silicone desce ao nível do tecido; o detalhe fica).
        A janela continua a que estava (0.96).

        `seed` = ponto (linha, coluna) dentro da prótese, para quando o programa não a acha sozinho."""
        self.implant_mask = on
        self.implant_seed = seed if on else None
        self._implant_cache = None
        self._qimage_key = None
        self._load_current()
        self.update()

    def blank_implant_at(self, pos: QPointF) -> None:
        """Apaga o implante a partir do ponto clicado (quando a busca automática não acerta)."""
        if self._img is None:
            return
        ip = self.widget_to_image(pos)
        h, w = self._img.pixels.shape[:2]
        y, x = int(np.clip(ip.y(), 0, h - 1)), int(np.clip(ip.x(), 0, w - 1))
        self.set_implant_mask(True, seed=(y, x))
        self.sig.implant_changed.emit(self)

    # ------------------------------------------------------------ ferramenta / anotações
    # ------------------------------------------------------------ navegação
    def step(self, delta: int, wrap: bool = False) -> None:
        if not self.frames:
            return
        if self.is_4d() and not getattr(self, "_cine_phases", False):
            self.step_cardiac_slice(delta)      # em 4D a rolagem anda nos cortes, sem trocar de fase
            return
        n = len(self.frames)
        new = (self.index + delta) % n if wrap else max(0, min(n - 1, self.index + delta))
        if new != self.index:
            if not wrap and not getattr(self, "_indo_direto", False):
                self._rolagem = True                # para o aviso de cortes pulados (0.99.45)
            self.cancel_draft()
            self.index = new
            self._load_current()
            self.update()
            self.sig.frame_changed.emit(self)

    def set_index_silently(self, index: int) -> None:
        index = max(0, min(len(self.frames) - 1, index))
        if index != self.index:
            self.cancel_draft()
            self.index = index
            self._load_current()
            self.update()

    def go_to(self, index: int) -> None:
        self._indo_direto = True                    # ir a um corte não é rolar: nada a avisar
        try:
            self.step(index - self.index)
        finally:
            self._indo_direto = False

    # ---- cortes pulados na rolagem rápida (0.99.45, plano AW item 14)
    #: por quanto tempo o aviso fica na tela, em segundos
    PULADOS_SEG = 1.5

    def _contar_pulados(self) -> None:
        """Chamado a cada pintura. Rolando depressa, a roda (ou o arrasto) anda vários cortes entre
        duas pinturas: os do meio nunca chegaram à tela. Quem lê precisa saber que pulou."""
        ultimo = getattr(self, "_ultimo_pintado", None)
        if getattr(self, "_rolagem", False) and ultimo is not None and not self.em_mosaico():
            d = abs(self.index - ultimo) - 1
            if d > 0:
                self._pulados = (d, time.monotonic())
                QTimer.singleShot(int(self.PULADOS_SEG * 1000) + 50, self.update)
        self._rolagem = False
        self._ultimo_pintado = self.index

    def cortes_pulados(self) -> int:
        """Quantos cortes a última rolagem pulou, enquanto o aviso está valendo (0 = nenhum)."""
        d, t = getattr(self, "_pulados", (0, 0.0))
        return d if d and time.monotonic() - t <= self.PULADOS_SEG else 0

    def _draw_pulados(self, p: QPainter) -> None:
        d = self.cortes_pulados()
        if not d:
            return
        txt = tr(f"{d} corte(s) não mostrado(s)")
        f = QFont()
        f.setPixelSize(max(10, int(self.height() / 45)))
        p.setFont(f)
        fm = QFontMetrics(f)
        r = self.posbar_rect()
        n = max(1, len(self.frames))
        y = r.top() + (self.index + 0.5) / n * r.height()
        w = fm.horizontalAdvance(txt) + 10
        caixa = QRectF(r.left() - w - 6, y - fm.height() / 2 - 2, w, fm.height() + 4)
        p.fillRect(caixa, QColor(0, 0, 0, 170))
        p.setPen(QColor(255, 190, 60))
        p.drawText(caixa, Qt.AlignCenter, txt)

    # ------------------------------------------------------------ cardíaco 4D
    def is_4d(self) -> bool:
        return self.cardiac is not None and self.cardiac.is_4d

    def cardiac_where(self) -> tuple[int, int]:
        """(corte, fase) do quadro atual."""
        return self.cardiac.where(self.index) if self.is_4d() else (self.index, 0)

    def set_cardiac_phase(self, phase: int, wrap: bool = True) -> None:
        """Mesma posição, outro instante do ciclo."""
        if not self.is_4d():
            return
        corte, _atual = self.cardiac_where()
        n = self.cardiac.n_phases
        p = (int(phase) % n) if wrap else max(0, min(int(phase), n - 1))
        novo = self.cardiac.frame_index(corte, p)
        if novo != self.index:
            self.index = novo
            self._load_current()
            self.update()
            self.sig.frame_changed.emit(self)

    def step_cardiac_slice(self, delta: int) -> None:
        """Rola os cortes sem sair da fase (o normal em exame 4D)."""
        if not self.is_4d():
            self.step(delta)
            return
        corte, fase = self.cardiac_where()
        corte = max(0, min(self.cardiac.n_slices - 1, corte + int(delta)))
        novo = self.cardiac.frame_index(corte, fase)
        if novo != self.index:
            self.index = novo
            self._load_current()
            self.update()
            self.sig.frame_changed.emit(self)

    def cardiac_text(self) -> str:
        if not self.is_4d():
            return ""
        corte, fase = self.cardiac_where()
        return f"Corte {corte + 1}/{self.cardiac.n_slices} · Fase {fase + 1}/{self.cardiac.n_phases}"

    def toggle_cine(self, fps: int = 15, phases: bool = False) -> None:
        if self._cine.isActive():
            self._cine.stop()
            return
        self._cine_phases = phases and (bool(self.phases) or self.is_4d())
        if self._cine_phases:
            self._cine.start(500)
        elif len(self.frames) > 1:
            self._cine.start(int(1000 / fps))

    def _cine_tick(self) -> None:
        if self._cine_phases and self.is_4d() and not self.phases:
            _corte, fase = self.cardiac_where()
            self.set_cardiac_phase(fase + 1)
        elif self._cine_phases:
            self.set_phase(self.phase + 1, wrap=True)
        elif getattr(self, "cine_bounce", False) and len(self.frames) > 1:   # tomossíntese: vai e volta
            d = getattr(self, "_cine_dir", 1)
            a, b = (0, len(self.frames))
            if self.tomo_range is not None and self.in_tomo():
                a, b = self.tomo_range                 # cine só nos cortes da tomo
            if not a <= self.index + d < b:
                d = -d
            self._cine_dir = d
            self.step(d)
        else:
            self.step(1, wrap=True)

    def reset_view(self) -> None:
        self.state = ViewState(cmap=self.state.cmap)        # a tabela de cores continua
        self._load_current()
        self.update()

    def fit(self) -> None:
        self.quad_idx = -1
        self.anat_lock = self._anat_box_norm = None
        self.state.zoom = 1.0
        self.state.pan = QPointF(0, 0)
        self.update()

    def set_window(self, width: float, level: float, emit: bool = True) -> None:
        self.state.width, self.state.level = max(1.0, width), level
        self.state.window_set = True
        self.update()
        if emit:
            self.sig.view_changed.emit(self, "window")

    def set_zoom_pan(self, zoom: float, pan: QPointF) -> None:
        self.state.zoom, self.state.pan = zoom, QPointF(pan)
        self.update()

    # ------------------------------------------------------------ geometria 3D
    def current_frame(self) -> Frame | None:
        return self.frames[self.index] if self.frames else None

    def plane(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
        """(posição do pixel 0,0; direção das colunas; direção das linhas; normal)."""
        f = self.current_frame()
        if f is None or f.position is None or f.orientation is None:
            return None
        row, col = np.asarray(f.orientation[:3]), np.asarray(f.orientation[3:])
        return np.asarray(f.position), row, col, np.cross(row, col)

    def pixel_to_patient(self, u: float, v: float) -> np.ndarray | None:
        pl = self.plane()
        if pl is None:
            return None
        pos, row, col, _n = pl
        rs, cs = self._spacing()
        return pos + u * cs * row + v * rs * col

    def ponto_central(self):
        """O ponto do paciente no meio do que está à vista — ou None sem geometria."""
        if self._img is None:
            return None
        h, w = self._img.pixels.shape[:2]
        return self.pixel_to_patient(w / 2, h / 2)

    def fracao_atual(self) -> float:
        n = len(self.frames)
        return self.index / (n - 1) if n > 1 else 0.5

    def patient_to_pixel(self, p: np.ndarray) -> tuple[float, float, float] | None:
        """(u, v, distância ao plano em mm)."""
        pl = self.plane()
        if pl is None:
            return None
        pos, row, col, n = pl
        rs, cs = self._spacing()
        d = np.asarray(p) - pos
        return float(d @ row / cs), float(d @ col / rs), float(d @ n)

    def go_to_point(self, p: np.ndarray, tolerance_mm: float | None = None) -> bool:
        """Vai para o corte mais próximo do ponto (em mm). Só para cortes paralelos."""
        if not self.frames or self.frames[0].normal is None:
            return False
        n = self.frames[0].normal
        dists = [abs(float((np.asarray(f.position) - p) @ n)) if f.position is not None else 1e9
                 for f in self.frames]
        best = int(np.argmin(dists))
        if tolerance_mm is not None and dists[best] > tolerance_mm:
            return False
        if best != self.index:
            self.cancel_draft()
            self.index = best
            self._load_current()
        self.update()
        return True

    def set_invert(self, on: bool | None = None) -> None:
        self.state.invert = (not self.state.invert) if on is None else on
        self.update()
        self.sig.view_changed.emit(self, "invert")

    def set_colormap(self, key: str | None, lembrar: bool = False) -> None:
        """Tabela de cores (pseudocor) do quadro; "" ou None = cinza.

        `lembrar` grava a escolha como padrão da modalidade: é o que o menu usa, para que a
        próxima série da mesma modalidade já abra na cor que você usou por último. As chamadas
        de dentro do programa (mapas da dinâmica, fusão) não gravam nada.
        """
        self.state.cmap = key if key in CM.COLORMAPS else ""
        if lembrar:
            self.guardar_cor_padrao()
        self._qimage_key = None
        self.update()
        self.sig.view_changed.emit(self, "cmap")

    def modalidade_atual(self) -> str:
        if self.modality and self.modality.startswith("MAP"):
            return self.modality
        return (self._img.header.get("Modality", "") if self._img is not None else "") or self.modality or ""

    def cor_padrao(self) -> str:
        """Cor guardada para a modalidade do quadro ("" = cinza)."""
        if self.settings is None:
            return ""
        cor = (self.settings.get("viewer.cmap_padrao", {}) or {}).get(self.modalidade_atual(), "")
        return cor if cor in CM.COLORMAPS else ""

    def guarda_a_cor(self) -> bool:
        """Guarda a cor escolhida como padrão — inclusive nos mapas da dinâmica.

        Até a 0.55 o mapa era exceção, com o argumento de que a tabela dele é a legenda. O
        argumento não para em pé: a barra de cores desenhada ao lado **é** a tabela em uso, então
        ela acompanha a escolha e não mente. E a conta prática é outra: ele trocava a cor do mapa
        em todo exame. A chave é por mapa (`MAP msi`, `MAP ser`…), não por modalidade, então
        mudar a cor do MSI não mexe no SER.
        """
        return self.settings is not None

    def guardar_cor_padrao(self) -> None:
        if not self.guarda_a_cor():
            return
        guardadas = dict(self.settings.get("viewer.cmap_padrao", {}) or {})
        guardadas[self.modalidade_atual()] = self.state.cmap
        self.settings.set("viewer.cmap_padrao", guardadas)

    def add_colormap_actions(self, menu: QMenu, apply_fn=None, lembrar: bool = False) -> None:
        """Itens de cor num menu (marcado = a do quadro). `apply_fn(key)` substitui set_colormap."""
        fn = apply_fn or ((lambda k: self.set_colormap(k, lembrar=True)) if lembrar else self.set_colormap)
        items = [("", "Cinza (normal)")] + [(k, v[0]) for k, v in CM.COLORMAPS.items()]
        for key, label in items:
            act = QAction(label, menu, checkable=True, checked=(key == self.state.cmap))
            if key:
                act.setIcon(colormap_icon(key))
            act.triggered.connect(lambda _=False, k=key: fn(k))
            menu.addAction(act)
            if not key:
                menu.addSeparator()
        if lembrar and apply_fn is None and self.guarda_a_cor():
            menu.addSeparator()
            mod = self.modalidade_atual() or "esta modalidade"
            nota = QAction("A cor escolhida aqui fica como padrão de " + mod, menu)
            nota.setEnabled(False)
            menu.addAction(nota)

    # ------------------------------------------------------------ geometria
    def _spacing(self) -> tuple[float, float]:
        if self._img is not None and self._img.pixel_spacing:
            return self._img.pixel_spacing
        return (1.0, 1.0)

    def _image_rect(self) -> QRectF:
        """Retângulo (em coordenadas do widget) onde a imagem é desenhada."""
        if self._img is None:
            return QRectF()
        h, w = self._img.pixels.shape[:2]
        rs, cs = self._spacing()
        aspect = rs / cs if cs else 1.0            # pixels não quadrados
        disp_w, disp_h = w, h * aspect
        bw, bh = (self.height(), self.width()) if self.state.rot in (90, 270) else (self.width(), self.height())
        fit = min(bw / disp_w, bh / disp_h) if disp_w and disp_h else 1
        s = fit * self.state.zoom
        rw, rh = disp_w * s, disp_h * s
        cx = self.width() / 2 + self.state.pan.x()
        cy = self.height() / 2 + self.state.pan.y()
        edge = self._unrotated_align()
        if edge and rw < bw:
            cx += (bw - rw) / 2 * (1 if edge == "right" else -1)
        return QRectF(cx - rw / 2, cy - rh / 2, rw, rh)

    def _unrotated_align(self) -> str | None:
        """Borda (antes do giro/espelho) em que a imagem encosta para ficar em `align_edge` na tela."""
        e = self.align_edge
        if not e or self.state.rot in (90, 270):
            return None
        flip = self.state.flip_h != (self.state.rot == 180)
        if flip:
            e = "left" if e == "right" else "right"
        return e

    def fit_scale(self) -> float:
        """Fator de "ajustar à janela" (tela px por pixel da imagem, na horizontal)."""
        if self._img is None:
            return 1.0
        h, w = self._img.pixels.shape[:2]
        rs, cs = self._spacing()
        aspect = rs / cs if cs else 1.0
        bw, bh = (self.height(), self.width()) if self.state.rot in (90, 270) else (self.width(), self.height())
        return min(bw / w, bh / (h * aspect)) if w and h else 1.0

    # ------------------------------------------------- ponto anatômico (mamografia)
    def chest_image_side(self) -> str:
        """Lado da IMAGEM onde está a parede torácica ("left"/"right"); "" quando não dá para saber."""
        if self._img is None or self._img.is_color:
            return ""
        key = id(self._img)
        hit = getattr(self, "_chest_cache", None)
        if hit is not None and hit[0] == key:
            return hit[1]
        from ipe.imaging.mammo import chest_wall_side
        try:
            side = chest_wall_side(self._img.pixels)
        except Exception:  # noqa: BLE001
            side = ""
        self._chest_cache = (key, side)
        return side

    def chest_screen_side(self) -> str:
        """Lado da TELA onde aparece a parede torácica ("left"/"right"), já contando o espelho da exibição."""
        side = self.chest_image_side()
        if not side or self._img is None:
            return ""
        w = self._img.pixels.shape[1]
        if self.image_to_widget(QPointF(w, 0)).x() < self.image_to_widget(QPointF(0, 0)).x():
            side = "left" if side == "right" else "right"      # imagem espelhada na tela
        return side

    def anat_point(self, pos: QPointF) -> tuple[float, float] | None:
        """Ponto da tela -> lugar dentro da mama: (fração a partir da parede torácica, fração de cima para
        baixo). É o que permite mostrar o mesmo lugar em outro quadro (outra mama, 2D, tomo ou recombinada)."""
        if self._img is None:
            return None
        bx0, by0, bx1, by1 = self.anat_box()
        if bx1 <= bx0 or by1 <= by0:
            return None
        ip = self.widget_to_image(pos)
        fx = (ip.x() - bx0) / (bx1 - bx0)
        if self.chest_image_side() == "right":
            fx = 1.0 - fx
        return float(fx), float((ip.y() - by0) / (by1 - by0))

    def anat_center(self) -> tuple[float, float] | None:
        return self.anat_point(QPointF(self.width() / 2, self.height() / 2))

    def anat_box(self) -> tuple[float, float, float, float]:
        """A caixa da mama usada no enquadramento. Com o zoom por quadrante ligado, é a mesma caixa (em
        proporção) para todos os cortes: a tomo cai exatamente onde estava a 2D."""
        h, w = self._img.pixels.shape[:2]
        norm = getattr(self, "_anat_box_norm", None)
        if norm is not None:
            return norm[0] * w, norm[1] * h, norm[2] * w, norm[3] * h
        return self.quadrant_box()

    def show_anat(self, fx: float, fy: float, zoom: float, lock: bool = False) -> None:
        """Põe aquele lugar da mama no meio do quadro, com esse zoom. `lock`: refaz sozinho quando a imagem
        troca (rolar do 2D para a tomo, alternar baixa energia/recombinada)."""
        if self._img is None:
            return
        self.state.zoom = max(0.05, float(zoom))
        self.state.pan = QPointF(0, 0)
        h, w = self._img.pixels.shape[:2]
        if lock and getattr(self, "_anat_box_norm", None) is None:
            b = self.quadrant_box()
            self._anat_box_norm = (b[0] / w, b[1] / h, b[2] / w, b[3] / h)
        bx0, by0, bx1, by1 = self.anat_box() if lock else self.quadrant_box()
        gx = 1.0 - fx if self.chest_image_side() == "right" else fx
        ip = QPointF(bx0 + gx * (bx1 - bx0), by0 + fy * (by1 - by0))
        now = self.image_to_widget(ip)
        c = QPointF(self.width() / 2, self.height() / 2)
        self.state.pan += self._delta_unrotated(c - now)
        if lock:
            self.anat_lock = ("pt", float(fx), float(fy), float(self.state.zoom))
        else:
            self.anat_lock, self._anat_box_norm = None, None
        self.update()

    def reapply_anat(self) -> None:
        """Refaz o enquadramento guardado (imagem nova: outro corte, outro tamanho ou recombinada)."""
        lock = getattr(self, "anat_lock", None)
        if lock is None or self._img is None:
            return
        if lock[0] == "quad":
            self._anchor_quadrant(int(lock[1]), lock[2])
            self.update()
        elif lock[0] == "mama":
            # a tomo e a recombinada têm a sua própria caixa: refaz a conta, não repete o zoom
            self._anat_box_norm = None
            self.enquadrar_na_mama(None, lock[2])
        else:
            self.show_anat(lock[1], lock[2], lock[3], lock=True)

    def relock_free(self) -> None:
        """Depois de um zoom/pan à mão: guarda o ponto atual, para a tomo e a recombinada continuarem
        caindo no mesmo lugar da mama."""
        if self._img is None or (self.mg_spec is None and self.tomo_range is None):
            return
        pt = self.anat_center()
        if pt is not None:
            self.anat_lock = ("pt", pt[0], pt[1], float(self.state.zoom))

    def anat_state(self) -> tuple | None:
        """Guarda o enquadramento (para atravessar uma troca de imagem feita de fora)."""
        if getattr(self, "anat_lock", None) is None:
            return None
        return (self.anat_lock, getattr(self, "_anat_box_norm", None), self.quad_idx)

    def restore_anat(self, saved) -> None:
        if not saved:
            return
        self.anat_lock, self._anat_box_norm, self.quad_idx = saved
        self.reapply_anat()

    def zoom_to_anat_quadrant(self, idx: int, factor: float = 2.0) -> None:
        """Quadrante da mama: 0 posterior+superior, 1 posterior+inferior, 2 anterior+superior,
        3 anterior+inferior. idx < 0 volta à imagem inteira.

        O quadrante fica **encostado no canto**: a parede torácica continua no mesmo lado da tela em que
        estava (o alinhamento da mamografia não se perde) e as duas mamas ficam espelhadas."""
        self.quad_idx = idx
        self._anat_box_norm = None              # a caixa da mama é recalculada a cada quadrante novo
        if idx < 0 or self._img is None:
            self.anat_lock = None
            self.state.zoom, self.state.pan = 1.0, QPointF(0, 0)
            self.update()
            return
        h, w = self._img.pixels.shape[:2]
        b = self.quadrant_box()
        self._anat_box_norm = (b[0] / w, b[1] / h, b[2] / w, b[3] / h)
        self._anchor_quadrant(idx, self.quadrant_zoom(b, factor))
        self.anat_lock = ("quad", idx, float(self.state.zoom))
        self.update()

    def quadrant_zoom(self, box, minimo: float = 2.0) -> float:
        """Zoom que faz o quadrante (um quarto da caixa da mama) caber no quadro, o maior possível."""
        fit = self.fit_scale()
        rs, cs = self._spacing()
        aspect = rs / cs if cs else 1.0
        bw, bh = max(1.0, box[2] - box[0]), max(1.0, box[3] - box[1])
        if fit <= 0:
            return minimo
        precisa_x = 2.0 * self.width() / (fit * bw)              # mostrar só metade da caixa na horizontal
        precisa_y = 2.0 * self.height() / (fit * aspect * bh)    # …e metade na vertical
        return float(min(8.0, max(minimo, min(precisa_x, precisa_y))))

    def _anchor_quadrant(self, idx: int, zoom: float) -> None:
        """Encosta o canto do quadrante no canto correspondente da tela."""
        self.state.zoom = max(0.05, float(zoom))
        self.state.pan = QPointF(0, 0)
        bx0, by0, bx1, by1 = self.anat_box()
        posterior, superior = idx < 2, idx % 2 == 0
        lado_img = self.chest_image_side()
        ix = (bx1 if lado_img == "right" else bx0) if posterior else (bx0 if lado_img == "right" else bx1)
        iy = by0 if superior else by1
        lado_tela = self.chest_screen_side() or self.align_edge or "left"
        tx = (self.width() if lado_tela == "right" else 0.0) if posterior else \
             (0.0 if lado_tela == "right" else self.width())
        ty = 0.0 if superior else float(self.height())
        now = self.image_to_widget(QPointF(ix, iy))
        self.state.pan += self._delta_unrotated(QPointF(tx, ty) - now)

    def zoom_to_quadrant(self, col: int, row: int, factor: float = 2.0) -> None:
        """Amplia o quadrante (coluna/linha 0 ou 1, na tela) da imagem; col < 0 volta ao inteiro."""
        if self._img is None:
            return
        self.state.pan = QPointF(0, 0)
        if col < 0:
            self.state.zoom = 1.0
            self.update()
            return
        h, w = self._img.pixels.shape[:2]
        self.state.zoom = 1.0
        bx0, by0, bx1, by1 = self.quadrant_box()
        # quadrante na tela -> ponto da imagem (vale com giro/espelho)
        tl, br = self.image_to_widget(QPointF(bx0, by0)), self.image_to_widget(QPointF(bx1, by1))
        x0, x1 = sorted((tl.x(), br.x()))
        y0, y1 = sorted((tl.y(), br.y()))
        target = QPointF(x0 + (x1 - x0) * (0.25 + 0.5 * col), y0 + (y1 - y0) * (0.25 + 0.5 * row))
        ip = self.widget_to_image(target)
        if (bx1 - bx0) < w or (by1 - by0) < h:      # mama menor que a imagem: amplia o quadrante da mama
            factor = max(factor, min(8.0, factor * min(w / max(1, bx1 - bx0), h / max(1, by1 - by0))))
        self.state.zoom = factor
        now = self.image_to_widget(ip)
        c = QPointF(self.width() / 2, self.height() / 2)
        self.state.pan += self._delta_unrotated(c - now)
        self.update()

    def quadrant_box(self) -> tuple[float, float, float, float]:
        """Área dividida em quadrantes: na mamografia, a caixa da mama (acompanha a parede torácica);
        nos outros exames, a imagem inteira."""
        h, w = self._img.pixels.shape[:2]
        if (self.mg_cell is not None or (self.modality or "").upper() == "MG") and not self._img.is_color:
            key = (id(self._img),)
            hit = getattr(self, "_bbox_cache", None)
            if hit is not None and hit[0] == key:
                box = hit[1]
            else:
                from ipe.imaging.mammo import breast_bbox
                try:
                    box = breast_bbox(self._img.pixels, self._img.header.get("_monochrome1") == "1")
                except Exception:  # noqa: BLE001
                    box = None
                self._bbox_cache = (key, box)
            if box is not None:
                return tuple(float(v) for v in box)
        return 0.0, 0.0, float(w), float(h)

    # ---------------------------------------------- enquadrar a mama no quadro (mamografia)
    MARGEM_MAMA = 0.03          # folga de cada lado, para a pele não encostar na borda

    def zoom_da_mama(self, margem: float | None = None) -> float | None:
        """Zoom que faz **a mama** (não o detector) caber no quadro. `None` se não achou mama.

        Metade do campo de uma mamografia é ar: no acervo real a mama ocupa 33 a 55% da largura
        das imagens CESM. Enquadrar pela imagem inteira é enquadrar o ar. Nunca devolve menos de
        1,0 — o ajuste de hoje já mostra tudo, e ninguém quer a mama menor do que estava.
        """
        if self._img is None or self._img.is_color:
            return None
        fit = self.fit_scale()
        if fit <= 0 or not self.width() or not self.height():
            return None
        h, w = self._img.pixels.shape[:2]
        caixa = self.quadrant_box()
        bw, bh = caixa[2] - caixa[0], caixa[3] - caixa[1]
        if bw < 0.08 * w or bh < 0.08 * h:
            return None                      # caixa pequena demais para ser mama: não confio nela
        from ipe.imaging import mammo as MG
        rs, cs = self._spacing()
        return MG.zoom_da_caixa((self.width(), self.height()), (w, h), caixa,
                                rs / cs if cs else 1.0,
                                self.MARGEM_MAMA if margem is None else margem)

    def enquadrar_na_mama(self, zoom: float | None = None, margem: float | None = None) -> bool:
        """Põe a mama ocupando o quadro, com a parede torácica encostada no lado dela.

        `zoom` dado de fora é o zoom **comum** do conjunto: duas mamas de tamanhos diferentes na
        mesma etapa precisam da mesma escala, senão a comparação lado a lado compara escalas.
        """
        if self._img is None:
            return False
        z = self.zoom_da_mama(margem) if zoom is None else float(zoom)
        if not z:
            return False
        self.quad_idx = -1
        self.state.zoom = max(0.05, min(8.0, z))
        self.state.pan = QPointF(0, 0)
        h, w = self._img.pixels.shape[:2]
        caixa = self.quadrant_box()
        self._anat_box_norm = (caixa[0] / w, caixa[1] / h, caixa[2] / w, caixa[3] / h)
        bx0, by0, bx1, by1 = caixa
        lado_img = self.chest_image_side()
        ix = bx1 if lado_img == "right" else bx0
        iy = (by0 + by1) / 2.0
        lado_tela = self.chest_screen_side() or self.align_edge or "left"
        # Encostado na borda, **sem folga**, do lado da parede torácica: é ali que o alinhamento
        # da mamografia mora (as duas mamas espelhadas na mesma linha). A folga do zoom serve
        # para o outro lado, o da pele.
        tx = float(self.width()) if lado_tela == "right" else 0.0
        agora = self.image_to_widget(QPointF(ix, iy))
        alvo = QPointF(tx, self.height() / 2.0)
        self.state.pan += self._delta_unrotated(alvo - agora)
        self.anat_lock = ("mama", float(self.state.zoom),
                          float(self.MARGEM_MAMA if margem is None else margem))
        self.update()
        return True

    def zoom_actual_pixels(self) -> None:
        """1 pixel da imagem = 1 pixel da tela (mamografia: ver microcalcificações)."""
        f = self.fit_scale()
        if f > 0:
            self.state.zoom = 1.0 / f
            self.update()
            self.sig.view_changed.emit(self, "zoom")

    def quadrant_at(self, pos: QPointF) -> tuple[int, int] | None:
        if self._img is None:
            return None
        h, w = self._img.pixels.shape[:2]
        tl, br = self.image_to_widget(QPointF(0, 0)), self.image_to_widget(QPointF(w, h))
        x0, x1 = sorted((tl.x(), br.x()))
        y0, y1 = sorted((tl.y(), br.y()))
        if not (x0 <= pos.x() <= x1 and y0 <= pos.y() <= y1):
            return None
        return int(pos.x() > (x0 + x1) / 2), int(pos.y() > (y0 + y1) / 2)

    # ------------------------------------------------------------ giro e espelho da exibição
    def is_transformed(self) -> bool:
        st = self.state
        return bool(st.rot or st.flip_h or st.flip_v)

    def _linear_t(self) -> QTransform:
        t = QTransform()
        t.rotate(self.state.rot)
        t.scale(-1 if self.state.flip_h else 1, -1 if self.state.flip_v else 1)
        return t

    def display_transform(self) -> QTransform:
        """Da imagem "sem giro" (coordenadas do quadro) para a tela: gira/espelha em volta do centro."""
        if not self.is_transformed():
            return QTransform()
        c = QPointF(self.width() / 2, self.height() / 2)
        return QTransform.fromTranslate(-c.x(), -c.y()) * self._linear_t() * QTransform.fromTranslate(c.x(), c.y())

    def _to_unrotated(self, p: QPointF) -> QPointF:
        if not self.is_transformed():
            return p
        inv, _ok = self.display_transform().inverted()
        return inv.map(p)

    def _delta_unrotated(self, d: QPointF) -> QPointF:
        if not self.is_transformed():
            return d
        inv, _ok = self._linear_t().inverted()
        return inv.map(d)

    def rotate_view(self, degrees: int, emit: bool = True) -> None:
        self.state.rot = (self.state.rot + degrees) % 360
        self.state.pan = self._rot_pan(self.state.pan, degrees)
        self.update()
        if emit:
            self.sig.view_changed.emit(self, "orient")

    @staticmethod
    def _rot_pan(pan: QPointF, degrees: int) -> QPointF:
        return pan          # o pan fica no espaço da imagem: gira junto

    def flip_view(self, horizontal: bool = True, emit: bool = True) -> None:
        """Espelha como aparece na tela (esquerda ↔ direita ou cima ↕ baixo)."""
        screen_h = horizontal != (self.state.rot in (90, 270))
        if screen_h:
            self.state.flip_h = not self.state.flip_h
        else:
            self.state.flip_v = not self.state.flip_v
        if self.state.flip_h and self.state.flip_v:       # os dois espelhos = giro de 180°
            self.state.flip_h = self.state.flip_v = False
            self.state.rot = (self.state.rot + 180) % 360
        self.update()
        if emit:
            self.sig.view_changed.emit(self, "orient")

    def set_orientation(self, rot: int, flip_h: bool, flip_v: bool = False) -> None:
        self.state.rot, self.state.flip_h, self.state.flip_v = rot % 360, flip_h, flip_v
        self.update()

    def reset_orientation(self, emit: bool = True) -> None:
        self.set_orientation(0, False, False)
        if emit:
            self.sig.view_changed.emit(self, "orient")

    def film_orientation(self) -> tuple[int, bool]:
        """(giro, espelho horizontal) equivalente, para o filme (que não tem espelho vertical)."""
        rot, fh = self.state.rot, self.state.flip_h
        if self.state.flip_v:
            rot, fh = (rot + 180) % 360, not fh
        return rot, fh

    def orientation_text(self) -> str:
        parts = []
        if self.state.flip_h:
            parts.append("⇋")
        if self.state.flip_v:
            parts.append("⇵")
        if self.state.rot:
            parts.append(f"↻{self.state.rot}°")
        return " ".join(parts)

    def add_orientation_actions(self, menu: QMenu) -> None:
        for text, fn in (("Girar 90° à direita ↻", lambda: self.rotate_view(90)),
                         ("Girar 90° à esquerda ↺", lambda: self.rotate_view(-90)),
                         ("Girar 180°", lambda: self.rotate_view(180)),
                         (None, None),
                         ("Espelhar esquerda ↔ direita", lambda: self.flip_view(True)),
                         ("Espelhar cima ↕ baixo", lambda: self.flip_view(False)),
                         (None, None),
                         ("Voltar à orientação original", lambda: self.reset_orientation())):
            if text is None:
                menu.addSeparator()
                continue
            a = QAction(text, menu)
            a.triggered.connect(fn)
            if text.startswith("Voltar"):
                a.setEnabled(self.is_transformed())
            menu.addAction(a)

    def display_orientation(self):
        """Vetores de orientação como a imagem aparece na tela (depois do giro/espelho)."""
        f = self.current_frame()
        if f is None or f.orientation is None:
            return None
        if not self.is_transformed():
            return f.orientation
        r, c = np.asarray(f.orientation[:3], float), np.asarray(f.orientation[3:], float)
        inv, _ok = self._linear_t().inverted()
        a, b = inv.map(QPointF(1, 0)), inv.map(QPointF(0, 1))
        return np.concatenate([r * a.x() + c * a.y(), r * b.x() + c * b.y()])

    def widget_to_image(self, p: QPointF) -> QPointF:
        p = self._to_unrotated(p)
        r = self._image_rect()
        h, w = self._img.pixels.shape[:2]
        return QPointF((p.x() - r.x()) / r.width() * w, (p.y() - r.y()) / r.height() * h)

    def image_to_widget(self, p: QPointF) -> QPointF:
        r = self._image_rect()
        h, w = self._img.pixels.shape[:2]
        q = QPointF(r.x() + p.x() / w * r.width(), r.y() + p.y() / h * r.height())
        return self.display_transform().map(q) if self.is_transformed() else q

    # ------------------------------------------------------------ desenho
    # ------------------------------------------------------------ mosaico (0.99.43, Weasis "tiled")
    mosaico: tuple | None = None
    MOSAICOS = ((2, 2), (3, 3), (4, 4))

    def em_mosaico(self) -> bool:
        return bool(self.mosaico) and len(self.frames) > 1 and self.render3d is None

    def set_mosaico(self, rc) -> None:
        """Mosaico de cortes seguidos da mesma série dentro deste quadro: (linhas, colunas) ou None.
        A imagem de cima à esquerda é a atual; a roda vira a página; duplo clique volta ao normal ali."""
        self.mosaico = tuple(rc) if rc else None
        self._mosaico_cache = {}
        self.update()

    def proximo_mosaico(self) -> None:
        ordem = [None, *self.MOSAICOS]
        i = ordem.index(self.mosaico) if self.mosaico in ordem else 0
        self.set_mosaico(ordem[(i + 1) % len(ordem)])
        r = self.mosaico
        self.sig.status_message.emit(f"Mosaico {r[0]}×{r[1]}: a roda vira a página; duplo clique abre a imagem."
                                     if r else "Mosaico desligado.")

    def _celulas_mosaico(self):
        r, c = self.mosaico
        w, h = self.width() / c, self.height() / r
        return [(i, QRectF(col * w, lin * h, w, h)) for i, (lin, col) in
                enumerate((a, b) for a in range(r) for b in range(c))]

    def mosaico_indice_em(self, pos) -> int | None:
        if not self.em_mosaico():
            return None
        for t, cel in self._celulas_mosaico():
            if cel.contains(pos):
                i = self.index + t
                return i if i < len(self.frames) else None
        return None

    def _qimage_do_corte(self, i: int) -> QImage | None:
        fr = self.frames[i]
        chave = (fr.sop_uid, fr.frame_index, getattr(fr, "path", ""), round(self.state.width, 3),
                 round(self.state.level, 3), self.state.invert, self.state.cmap)
        cache = getattr(self, "_mosaico_cache", None)
        if cache is None:
            cache = self._mosaico_cache = {}
        if chave in cache:
            return cache[chave]
        try:
            img = self.cache.get(self.frames[i])
        except Exception:  # noqa: BLE001
            return None
        if img is None or img.pixels is None:
            return None
        disp = np.ascontiguousarray(to_display(img, self.state.width, self.state.level, self.state.invert,
                                               self.state.cmap))
        hh, ww = disp.shape[:2]
        fmt = QImage.Format_Grayscale8 if disp.ndim == 2 else QImage.Format_RGB888
        q = QImage(disp.data, ww, hh, disp.strides[0], fmt).copy()
        if len(cache) > 64:
            cache.clear()
        cache[chave] = q
        return q

    def _pintar_mosaico(self, p: QPainter) -> None:
        p.save()
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        n = len(self.frames)
        rs, cs = self._spacing()
        aspect = rs / cs if cs else 1.0
        font = p.font()
        font.setPointSizeF(max(7.5, min(10.0, self.width() / (self.mosaico[1] * 18))))
        p.setFont(font)
        chaves = getattr(self, "key_frames", set()) or set()
        for t, cel in self._celulas_mosaico():
            i = self.index + t
            if i >= n:
                break
            q = self._qimage_do_corte(i)
            if q is not None:
                iw, ih = q.width(), q.height() * aspect
                s = min(cel.width() / iw, cel.height() / ih) if iw and ih else 1.0
                alvo = QRectF(cel.center().x() - iw * s / 2, cel.center().y() - ih * s / 2, iw * s, ih * s)
                p.drawImage(alvo, q)
            p.setPen(QColor(70, 70, 70))
            p.drawRect(cel.adjusted(0, 0, -1, -1))
            f = self.frames[i]
            marca = " ★" if (f.sop_uid, f.frame_index) in chaves else ""
            p.setPen(QColor(255, 210, 60) if t == 0 else QColor(230, 230, 230))
            p.drawText(cel.adjusted(4, 2, -4, -2), int(Qt.AlignLeft | Qt.AlignTop), f"{i + 1}{marca}")
        p.setPen(QColor(200, 200, 200))
        r, c = self.mosaico
        p.drawText(QRectF(4, self.height() - 18, self.width() - 8, 16), int(Qt.AlignRight | Qt.AlignBottom),
                   f"Mosaico {r}×{c} · {self.index + 1}–{min(n, self.index + r * c)} de {n}")
        p.restore()

    def _qimage_for_current(self) -> QImage | None:
        img = self._img
        if img is None:
            return None
        key = (id(img), round(self.state.width, 3), round(self.state.level, 3), self.state.invert,
               self.state.cmap, self.state.filter, self.settings.get("monitors.gsdf_stamp", 0))
        if key == self._qimage_key and self._qimage is not None:
            return self._qimage
        img = self._filtered(img)
        disp = to_display(img, self.state.width, self.state.level, self.state.invert, self.state.cmap)
        tabela = self._gsdf_table()
        if tabela is not None:
            disp = tabela[disp]                # calibração GSDF deste monitor
        disp = np.ascontiguousarray(disp)
        h, w = disp.shape[:2]
        if disp.ndim == 2:
            q = QImage(disp.data, w, h, disp.strides[0], QImage.Format_Grayscale8)
        else:
            q = QImage(disp.data, w, h, disp.strides[0], QImage.Format_RGB888)
        self._qimage = q.copy()           # copia: o buffer numpy pode ser liberado
        self._qimage_key = key
        return self._qimage

    def _gsdf_table(self):
        """Tabela de calibração GSDF do monitor em que este quadro está (None = desligada)."""
        from ipe.imaging import gsdf
        tela = self.screen()
        if tela is None:
            return None
        from ipe.ui.monitors import screen_key
        chave = screen_key(tela)
        marca = (chave, id(self.settings), self.settings.get("monitors.gsdf_stamp", 0))
        if getattr(self, "_gsdf_key", None) != marca:
            try:
                self._gsdf_lut = gsdf.table_for(self.settings, chave)
            except Exception:  # noqa: BLE001
                log.exception("calibração GSDF")
                self._gsdf_lut = None
            self._gsdf_key = marca
        return self._gsdf_lut

    def _filtered(self, img):
        """A imagem com o filtro escolhido (nitidez/suavização), guardada para não refazer."""
        if not self.state.filter:
            return img
        chave = (id(img), self.state.filter)
        if getattr(self, "_filter_key", None) == chave and self._filter_img is not None:
            return self._filter_img
        from dataclasses import replace
        from ipe.imaging import filters
        try:
            saida = replace(img, pixels=filters.apply(img.pixels, self.state.filter))
        except Exception:  # noqa: BLE001
            log.exception("filtro de imagem")
            return img
        self._filter_key, self._filter_img = chave, saida
        return saida

    def set_filter(self, name: str) -> None:
        """Escolhe o filtro (nitidez/suavização) desta imagem."""
        from ipe.imaging.filters import FILTERS
        self.state.filter = name if name in FILTERS else ""
        self._qimage_key = None
        self.update()
        self.sig.view_changed.emit(self, "filter")

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0))
        self._hotspots = {}
        self._anot_vis = self.anotacoes_visiveis()     # uma consulta às preferências por pintura
        q = self._qimage_for_current()
        if q is not None and self.em_mosaico():
            self._pintar_mosaico(p)
        elif q is not None:
            p.setRenderHint(QPainter.SmoothPixmapTransform, self.state.zoom < 3)
            p.save()
            if self.is_transformed():
                p.setTransform(self.display_transform(), True)
            p.drawImage(self._image_rect(), q)
            if self.fusion is not None:
                self._draw_fusion(p)
            if self.overlays:
                from ipe.ui.viewer.overlay_draw import draw_masks
                draw_masks(self, p)
            p.restore()
            if self.overlays:
                from ipe.ui.viewer.overlay_draw import draw_graphics
                draw_graphics(self, p)
            self._draw_reference_lines(p)
            self._draw_measurements(p)
            if self.ghosts and self._mostra("medidas"):
                self._draw_ghosts(p)
            self._draw_overlay(p)
            if self.render3d is not None:
                self.render3d.draw_extra(self, p)
            if self._mostra("barra_posicao") and not self._capturando:
                self._draw_posbar(p)
            if not self._capturando:
                self._contar_pulados()
                self._draw_pulados(p)
            if self._loupe is not None:
                self._draw_loupe(p, q)
            self._desenhar_pincel(p)
        elif self.frames:
            p.setPen(QColor(220, 80, 80))
            p.drawText(self.rect(), Qt.AlignCenter, "Não foi possível ler esta imagem")
        else:
            p.setPen(QColor(110, 110, 110))
            nota = getattr(self, "empty_note", "") or ""
            p.drawText(self.rect(), Qt.AlignCenter,
                       (nota + "\n\n" if nota else "") + "Clique aqui para escolher a série\nou arraste uma da tira")
        if not self._capturando:               # a cópia (Ctrl+C) sai sem a moldura nem as zonas de soltar
            self._draw_drop_zones(p)
            pen = QPen(QColor(255, 200, 0) if self.active else QColor(60, 60, 60))
            pen.setWidth(2 if self.active else 1)
            p.setPen(pen)
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.end()
        self._anot_vis = None

    # ------------------------------------------------------------ cópia (Ctrl+C)
    COPIA_LADO_MIN = 1600      # px: a cópia nunca sai menor que isto no lado maior
    COPIA_LADO_MAX = 6000      # px: nem maior que isto (área de transferência e memória)

    def escala_da_copia(self) -> float:
        """Quantas vezes a cópia é maior que o quadro na tela.

        "Em boa resolução": a imagem não pode sair com menos pixels do que tem no arquivo (uma
        mamografia de 3000 px vista num quadro de 700 sairia borrada) nem pequena demais para colar
        num documento. Texto e medidas são redesenhados na escala nova, então saem nítidos."""
        w, h = max(1, self.width()), max(1, self.height())
        k = self.COPIA_LADO_MIN / max(w, h)
        if self._img is not None:
            r = self._image_rect()
            if r.width() > 0 and r.height() > 0:
                ih, iw = self._img.pixels.shape[:2]
                lado_tela = r.height() if self.state.rot in (90, 270) else r.width()
                k = max(k, iw / lado_tela)
        k = max(1.0, k)
        return min(k, self.COPIA_LADO_MAX / max(w, h))

    def imagem_da_tela(self, escala: float | None = None) -> QImage:
        """O quadro como está na tela — imagem, medidas e as anotações do nível em uso — numa
        resolução maior. Sem a moldura amarela, o ícone do mouse, a barra de posição e o realce do
        mouse por cima: isso é da tela, não da imagem."""
        k = self.escala_da_copia() if escala is None else float(escala)
        w, h = max(1, self.width()), max(1, self.height())
        out = QImage(int(round(w * k)), int(round(h * k)), QImage.Format_RGB32)
        out.setDevicePixelRatio(k)
        out.fill(QColor(0, 0, 0))
        hover, self._hover = self._hover, None
        hotspots = dict(self._hotspots)
        self._capturando = True
        self._nivel_forcado = self.nivel_de_saida()
        try:
            self.render(out)
            if self.settings is None or self.settings.get("viewer.carimbo_saida", True):
                p = QPainter(out)
                try:
                    self._draw_carimbo(p)
                finally:
                    p.end()
        finally:
            self._capturando = False
            self._nivel_forcado = None
            self._hover = hover
            self._hotspots = hotspots
        out.setDevicePixelRatio(1.0)
        return out

    # ---- perfil de anotação da saída e carimbo mínimo (0.99.22, plano AW 12)
    def nivel_de_saida(self) -> str | None:
        """Nível de anotação da cópia/exportação; None = o mesmo da tela."""
        from ipe.ui.viewer import anotacoes as AN
        if self.settings is None:
            return None
        n = str(self.settings.get("viewer.anotacoes_saida", "") or "")
        return n if n in AN.NOME_DO_NIVEL else None

    def processamento_aplicado(self) -> list[str]:
        """O que foi feito na imagem além de mostrá-la: entra sempre no carimbo da saída."""
        out = []
        if self.dsa.get("on"):
            out.append(self.dsa_status())
        if self.subtract and self.phases and self.phase > 0:
            pais = float(getattr(self, "paisagem", 0.0) or 0.0)
            out.append(f"Subtração fase {self.phase + 1} − pré" + (f" + {pais * 100:.0f}% anatomia" if pais else ""))
        if self.state.filter:
            from ipe.imaging.filters import label as _flabel
            out.append(_flabel(self.state.filter))
        plano = getattr(self, "mpr_plane", None)
        if plano is not None:
            slab = float(getattr(plano, "slab_mm", 0) or 0)
            modo = {"mip": "MIP", "minip": "MinIP", "avg": "média"}.get(str(getattr(plano, "mode", "")), "")
            nome = getattr(plano, "name", "") or "Reconstrução"
            out.append(f"{nome} {modo} {slab:.0f} mm".replace("  ", " ") if slab > 0 and modo else str(nome))
        if self.tomo_slab > 1 and self.in_tomo():
            out.append(f"Tomo: {self.tomo_slab} cortes ({'MIP' if self.tomo_slab_mode == 'mip' else 'média'})")
        if self.fusion is not None:
            out.append(f"Fusão: {self.fusion.label} {self.fusion.alpha * 100:.0f}%")
        return out

    def carimbo_texto(self) -> str:
        """A linha mínima que toda imagem que sai do programa leva: série, janela, escala e
        processamento (rastreabilidade: quem vê a cópia sabe o que foi feito nela)."""
        partes = []
        if self.series_label:
            partes.append(self.series_label)
        if self._img is not None and not self._img.is_color:
            partes.append(f"W {self.state.width:.0f} L {self.state.level:.0f}")
        if self._img is not None and self._img.pixel_spacing:
            rs, cs = self._img.pixel_spacing
            partes.append(f"pixel {cs:.2f} mm" if abs(rs - cs) < 1e-6 else f"pixel {rs:.2f}×{cs:.2f} mm")
        else:
            partes.append("sem escala")
        partes += self.processamento_aplicado()
        partes += [s.texto for s in self.selos() if s.grave]
        return " · ".join(partes)

    def _draw_carimbo(self, p: QPainter) -> None:
        txt = tr(self.carimbo_texto())
        if not txt:
            return
        f = QFont()
        f.setPixelSize(max(11, int(p.device().height() / 70)))
        p.setFont(f)
        fm = QFontMetrics(f)
        W, H = p.device().width(), p.device().height()
        txt = fm.elidedText(txt, Qt.ElideRight, W - 12)
        r = QRectF(0, H - fm.height() - 6, W, fm.height() + 6)
        p.fillRect(r, QColor(0, 0, 0, 170))
        p.setPen(QColor(235, 235, 235))
        p.drawText(r.adjusted(6, 0, -6, 0), Qt.AlignLeft | Qt.AlignVCenter, txt)

    def copiar_para_area_de_transferencia(self) -> tuple[int, int] | None:
        """Ctrl+C: o quadro vai para a área de transferência. Devolve o tamanho copiado."""
        if not self.frames or self._img is None:
            return None
        img = self.imagem_da_tela()
        QApplication.clipboard().setImage(img)
        return img.width(), img.height()

    def anotacoes_visiveis(self) -> set[str]:
        """Itens do overlay que o nível de anotação em uso mostra (Preferências ▸ Anotações)."""
        from ipe.ui.viewer import anotacoes as AN
        if self.settings is None:
            return set(AN.CHAVES)
        return AN.itens_do_nivel(self.settings, getattr(self, "_nivel_forcado", None))

    def _mostra(self, item: str) -> bool:
        vis = getattr(self, "_anot_vis", None)
        if vis is None:
            vis = self.anotacoes_visiveis()
        return item in vis

    def perfil_de_ocultacao(self) -> str:
        """O perfil de ocultação em uso (0.99.42). Na reunião é sempre "ocultar tudo" (o nome do caso)."""
        if not self.anonymize or self.case_label:
            return "oculto"
        from ipe.core import mascara as MK
        return MK.perfil_de(self.settings)

    def _text_lines(self) -> dict[str, list[tuple[str, str | None]]]:
        """Linhas do overlay por canto. Cada linha: (texto, hotspot ou None).

        Cada linha tem um item do catálogo de anotações (anotacoes.ITENS); só entram as do nível
        em uso. O canto que fica vazio fica vazio de verdade (o indicador da tomo desce junto)."""
        si = self.study_info or {}
        img = self._img
        hdr = img.header if img else {}
        n = len(self.frames)
        perfil = self.perfil_de_ocultacao()
        if self.anonymize and perfil != "oculto":
            # 0.99.42: perfis de ocultação — pseudônimo, sexo/idade, datas deslocadas ou sem datas
            from ipe.core import mascara as MK
            si = MK.mascarar_info(si, perfil, self.case_label)
            tl = [(si.get("patient_name", ""), None, "nome"),
                  *([(f"ID {si['patient_id']}", None, "id")] if si.get("patient_id") else []),
                  (" ".join(x for x in (si.get("sex", ""), si.get("patient_age", "")) if x), None, "sexo_idade"),
                  (MK.selo(perfil), None, "nome")]
        elif self.anonymize:
            # "Ocultar dados do paciente" continua valendo por cima do nível: só o rótulo do caso
            tl = [(self.case_label or "Paciente oculto", None, "nome")]
        else:
            birth = si.get("birth_date", "")
            birth_fmt = f"{birth[6:8]}/{birth[4:6]}/{birth[:4]}" if len(birth) == 8 else ""
            tl = [(si.get("patient_name", ""), None, "nome"),
                  (f"ID {si.get('patient_id', '')}", None, "id"),
                  (" ".join(x for x in (si.get("sex", ""), si.get("patient_age", ""), birth_fmt) if x), None,
                   "sexo_idade"),
                  (si.get("institution", ""), None, "instituicao")]
        date = si.get("study_date", "")
        date_fmt = f"{date[6:8]}/{date[4:6]}/{date[:4]}" if len(date) == 8 else date
        tr = [(si.get("description", ""), None, "exame"),
              (f"{self.series_label}  ▾", "series", "serie"),
              # o nome da fase só entra se o rótulo da série já não o disser (na dinâmica diz)
              *([(f"Fase {self.phase + 1}: {self.phase_labels[self.phase]}", "phase", "fase_nome")]
                if self.phases and self.phase < len(self.phase_labels)
                and self.phase_labels[self.phase] not in (self.series_label or "") else []),
              (date_fmt if not self.anonymize or perfil in ("tela", "ensino") else "", None, "data")]
        bl = [(f"Im {self.index + 1}/{n}", "scroll", "imagem")]
        trng = getattr(self, "tomo_range", None)
        if trng is not None:
            if trng[0] <= self.index < trng[1]:
                bl = [(f"Tomo corte {self.index - trng[0] + 1}/{trng[1] - trng[0]}  (Im {self.index + 1}/{n})",
                       "scroll", "imagem")]
            else:
                bl = [(f"2D  (Im {self.index + 1}/{n})", "scroll", "imagem")]
        if self.is_transformed():
            bl.append((self.orientation_text(), "orient", "orientacao"))
        pos_txt = self._position_text()
        if pos_txt:
            bl.append((pos_txt, "scroll", "posicao"))
        if hdr.get("SliceThickness"):
            bl.append((f"Esp {float(hdr['SliceThickness']):.1f} mm", None, "espessura"))
        esc = self.escala_texto() if hasattr(self, "escala_texto") else ""
        if esc:
            bl.append((esc, "escala", "escala"))
        # Canto inferior direito, de cima para baixo: plano, fase da dinâmica, janela, FOV.
        br = [(self.plano_texto(), "plano", "plano")]
        if self.phases:
            br.append((self.fase_texto(), "fase", "fase"))
        if img is not None and not img.is_color:
            if self.suv_factor:
                f = self.suv_factor
                br.append((f"SUV  W {self.state.width * f:.1f}  L {self.state.level * f:.1f}", "wl", "janela"))
            else:
                nome_j = self.nome_da_janela()
                br.append((f"W {self.state.width:.0f}  L {self.state.level:.0f}" + (f"  {nome_j}" if nome_j else ""),
                           "wl", "janela"))
        br.append((self._fov_text(), "zoom", "fov"))
        if self.is_4d():
            bl.insert(0, (self.cardiac_text(), "phase", "fase_cardiaca"))
        if self.dsa.get("on"):
            bl.append((self.dsa_status(), None, "processamento"))
        if self.state.filter:
            from ipe.imaging.filters import label as _flabel
            bl.append((_flabel(self.state.filter), None, "processamento"))
        if self.fusion is not None and self.plane() is not None:
            fu = self.fusion
            val = "" if self.fusion_value is None else f"  {self.fusion_value:.2f} {fu.unit}".rstrip()
            bl.append((f"Fusão: {fu.label} {fu.alpha * 100:.0f}%{val}", None, "processamento"))

        def filtra(linhas, vazio_sai: bool = True):
            return [(t, h) for t, h, k in linhas if self._mostra(k) and (t or not vazio_sai)]

        return {"tl": filtra(tl), "tr": filtra(tr), "bl": filtra(bl), "br": filtra(br)}

    def plano_texto(self) -> str:
        """O plano em que o quadro está: axial, coronal, sagital ou oblíquo."""
        nome = self.plano_nome()
        # Concatenação, não f-string: "{}  ▾" seria um padrão que começa com o buraco e
        # sequestraria qualquer outro texto na tradução.
        return (nome + "  ▾") if nome else ""

    def plano_nome(self) -> str:
        # Só a reconstrução sabe o nome do plano. Mapa paramétrico da dinâmica e MPR curvo também
        # moram em `mpr_plane`, mas o `name` deles é o nome do mapa ("Cinética"), não um plano —
        # e essa linha é de orientação, não de conteúdo.
        from ipe.imaging.volume import MPRPlane
        plano = getattr(self, "mpr_plane", None)
        if isinstance(plano, MPRPlane) and getattr(plano, "name", ""):
            return plano.name
        f = self.current_frame()
        if f is None or f.orientation is None:
            return ""
        from ipe.imaging.volume import plane_name
        n = np.cross(f.orientation[:3], f.orientation[3:])
        # Chamar de "axial" um plano inclinado 30° é mentir no rótulo: acima de ~18° fora do
        # eixo, o nome honesto é oblíquo.
        if float(np.max(np.abs(n))) < 0.95 * float(np.linalg.norm(n) or 1.0):
            return "Oblíquo"
        return plane_name(n)

    def fase_texto(self) -> str:
        """Fase da dinâmica: esquerdo avança, direito volta."""
        return self.phase_text()

    def _position_text(self) -> str:
        f = self.frames[self.index] if self.frames else None
        if f is None or f.position is None or f.orientation is None:
            return ""
        normal = np.cross(f.orientation[:3], f.orientation[3:])
        axis = int(np.argmax(np.abs(normal)))
        val = float(f.position[axis])
        pos_letter, neg_letter = ("L", "R") if axis == 0 else ("P", "A") if axis == 1 else ("S", "I")
        letter = pos_letter if val >= 0 else neg_letter
        return f"{letter}{abs(val):.1f}"

    def _fov_text(self) -> str:
        if self._img is None:
            return ""
        h, w = self._img.pixels.shape[:2]
        rs, cs = self._spacing()
        zoom_txt = f"Zoom {self.state.zoom * 100:.0f}%"
        regs = getattr(self._img, "us_regioes", ())
        if regs:
            # no ultrassom o arquivo é a tela do aparelho; o campo de visão é o da região varrida
            from ipe.imaging import us_regioes as US
            r = US.maior(regs)
            return (f"FOV {(r.x1 - r.x0) * r.mm_coluna / 10:.1f}×"
                    f"{(r.y1 - r.y0) * r.mm_linha / 10:.1f} cm  {zoom_txt}")
        if self._img.pixel_spacing:
            return f"FOV {w * cs / 10:.1f}×{h * rs / 10:.1f} cm  {zoom_txt}"
        return zoom_txt

    def escala_da_letra(self, chave: str) -> float:
        """Quanto o usuário aumentou (ou diminuiu) a letra, de 0,6 a 2,5."""
        if self.settings is None:
            return 1.0
        try:
            return max(0.6, min(2.5, float(self.settings.get(chave, 1.0))))
        except (TypeError, ValueError):
            return 1.0

    def _draw_overlay(self, p: QPainter) -> None:
        font = QFont()
        font.setPointSizeF(max(7.0, min(10.0, self.width() / 60))
                           * self.escala_da_letra("viewer.overlay_font_scale"))
        p.setFont(font)
        fm = QFontMetrics(font)
        lh = fm.height()
        margin = 6
        hot_enabled = bool(self.settings.get("viewer.overlay_hotspots", True)) and not self._capturando
        lines = self._text_lines()

        def draw_block(key: str, items, align_right: bool, from_bottom: bool) -> None:
            for i, (text, hot) in enumerate(items):
                tw = fm.horizontalAdvance(text)
                x = self.width() - margin - tw if align_right else margin
                y = (self.height() - margin - (len(items) - i) * lh) if from_bottom else margin + i * lh
                rect = QRectF(x - 3, y, tw + 6, lh)
                if hot and hot_enabled:
                    self._hotspots.setdefault(hot, rect)
                    if self._hover == hot:
                        p.fillRect(rect, QColor(255, 200, 0, 60))
                p.setPen(QColor(0, 0, 0))
                p.drawText(QPointF(x + 1, y + fm.ascent() + 1), text)   # sombra
                p.setPen(QColor(255, 220, 120) if (hot and self._hover == hot) else QColor(230, 230, 230))
                p.drawText(QPointF(x, y + fm.ascent()), text)

        draw_block("tl", lines["tl"], False, False)
        draw_block("tr", lines["tr"], True, False)
        draw_block("bl", lines["bl"], False, True)
        draw_block("br", lines["br"], True, True)
        self._draw_selos(p, font, margin, lh, hot_enabled)
        if self.settings.get("viewer.tomo_dial", True) and self._mostra("tomo"):
            from ipe.ui.viewer import tomo_dial as TD
            canto = "br" if self.chest_screen_side() == "left" else "bl"
            TD.draw(self, p, font, lh, len(lines[canto]))

        # letras de orientação no meio das bordas (clicáveis -> pan)
        f = self.frames[self.index] if self.frames else None
        labels = orientation_labels(self.display_orientation() if f else None) if self._mostra("letras") else {}
        big = QFont(font)
        big.setBold(True)
        big.setPointSizeF(font.pointSizeF() + 2)
        p.setFont(big)
        bfm = QFontMetrics(big)
        pos = {
            "left": (margin, self.height() / 2),
            "right": (self.width() - margin - (self.POSBAR_W + 6 if len(self.frames) > 1 else 0),
                      self.height() / 2),
            "top": (self.width() / 2, margin + bfm.height()),
            "bottom": (self.width() / 2, self.height() - margin - bfm.height() * 1.2),
        }
        for side, txt in labels.items():
            tw = bfm.horizontalAdvance(txt)
            x, y = pos[side]
            if side == "right":
                x -= tw
            elif side in ("top", "bottom"):
                x -= tw / 2
            rect = QRectF(x - 4, y - bfm.ascent(), tw + 8, bfm.height())
            if hot_enabled:
                self._hotspots.setdefault(f"pan_{side}", rect)
                if self._hover == f"pan_{side}":
                    p.fillRect(rect, QColor(255, 200, 0, 60))
            p.setPen(QColor(255, 220, 120))
            p.drawText(QPointF(x, y), txt)

        f_cur = self.current_frame()
        if f_cur is not None and (f_cur.sop_uid, f_cur.frame_index) in self.key_frames and self._mostra("chave"):
            star = QFont(font)
            star.setPointSizeF(font.pointSizeF() + 6)
            p.setFont(star)
            p.setPen(QColor(255, 210, 0))
            p.drawText(QPointF(self.width() / 2 + 30, margin + QFontMetrics(star).ascent()), "★")
        if self.frames and self._mostra("sincronia") and not self._capturando:
            self._draw_sync_icon(p, font, margin, lh, hot_enabled)
        n_ann = len(self.annotated_indices()) if self.annotations and self._mostra("medidas_aviso") else 0
        if n_ann:
            txt = f"✎ {n_ann} imagem(ns) com medida  ▾"
            tw = QFontMetrics(font).horizontalAdvance(txt)
            rect = QRectF(self.width() / 2 + 30, self.height() - margin - lh - 2, tw + 8, lh + 4)
            if hot_enabled:
                self._hotspots.setdefault("annots", rect)
                if self._hover == "annots":
                    p.fillRect(rect, QColor(255, 200, 0, 60))
            p.setFont(font)
            p.setPen(QColor(0, 0, 0))
            p.drawText(QPointF(rect.x() + 5, rect.y() + 2 + QFontMetrics(font).ascent() + 1), txt)
            p.setPen(QColor(80, 255, 120))
            p.drawText(QPointF(rect.x() + 4, rect.y() + 2 + QFontMetrics(font).ascent()), txt)
        if self.state.cmap and self._img is not None and not self._img.is_color and self._mostra("barra_cores"):
            self._draw_colorbar(p, font)
        if self.is_calibrated() and self._mostra("calibrada"):
            p.setFont(font)
            p.setPen(QColor(255, 120, 255))
            p.drawText(QPointF(margin, self.height() / 2 + lh * 3), "Medidas calibradas")
        if self._mostra("mouse") and not self._capturando:
            self._draw_mouse_icon(p, font, margin, lh, hot_enabled)

    # --------------------------------------------------- selos de integridade (0.99.22)
    def selos(self) -> list:
        """Os selos da imagem à vista (compressão com perdas, Modality LUT, pixel não quadrado…)."""
        if self._img is None:
            return []
        from ipe.imaging import selos as SL
        out = SL.selos(self._img.header, self._img.pixel_spacing)
        layout = getattr(self, "pacientes_do_layout", None)
        if callable(layout) and self.study_info:
            from ipe.ui import compare_studies as CS
            if CS.pacientes_diferentes([self.study_info, *layout()]):
                if self.anonymize and self.perfil_de_ocultacao() != "oculto":
                    from ipe.core import mascara as MK
                    nome = MK.mascarar_info(self.study_info, self.perfil_de_ocultacao())["patient_name"]
                else:
                    nome = (self.case_label or "Paciente oculto") if self.anonymize else CS.nome_curto(self.study_info)
                out.insert(0, SL.selo_de_mistura(nome))
        outros = getattr(self, "referencial_da_sincronia", None)
        if callable(outros):
            n = outros(self)
            if n:
                out.append(SL.selo_de_referencial(n))
        return out

    def _selos_visiveis(self) -> list:
        from ipe.ui.viewer import anotacoes as AN
        nivel = getattr(self, "_nivel_forcado", None) or (AN.nivel_atual(self.settings) if self.settings else "")
        if nivel == "ausente":
            return []
        todos = self.selos()
        return todos if self._mostra("selos") else [s for s in todos if s.grave]

    def _draw_selos(self, p: QPainter, font: QFont, margin: int, lh: float, hot_enabled: bool) -> None:
        sel = self._selos_visiveis()
        if not sel:
            return
        txt = "  ·  ".join(tr(s.texto) for s in sel)
        f = QFont(font)
        f.setBold(any(s.grave for s in sel))
        fm = QFontMetrics(f)
        tw = fm.horizontalAdvance(txt)
        largura = self.width() - 2 * margin
        if tw > largura:                       # quadro estreito: só o primeiro (o mais grave)
            txt = tr(sel[0].texto) + ("  …" if len(sel) > 1 else "")
            tw = fm.horizontalAdvance(txt)
        rect = QRectF((self.width() - tw) / 2 - 6, margin + lh * 1.3, tw + 12, fm.height() + 4)
        grave = sel[0].grave
        p.save()
        p.setFont(f)
        p.fillRect(rect, QColor(170, 0, 0, 200) if grave else QColor(0, 0, 0, 150))
        if hot_enabled:
            self._hotspots.setdefault("selos", rect)
            if self._hover == "selos":
                p.fillRect(rect, QColor(255, 200, 0, 60))
        p.setPen(QColor(255, 255, 255) if grave else QColor(255, 190, 70))
        p.drawText(QPointF(rect.x() + 6, rect.y() + 2 + fm.ascent()), txt)
        p.restore()

    def explicar_selos(self) -> None:
        sel = self.selos()
        if not sel:
            return
        texto = "\n\n".join(f"• {tr(s.texto)}\n{tr(s.explicacao)}" for s in sel)
        QMessageBox.information(self, tr("Selos de integridade"), texto)

    # --------------------------------------------------- ícone do mouse (o que cada botão faz)
    def mouse_actions(self) -> list[tuple[str, str]]:
        """(botão, o que ele faz agora) — para o balão do ícone do mouse."""
        mouse = self.settings.get("viewer.mouse", {})
        wheel = {"scroll": "Rolar cortes", "scroll5": "Rolar 5 cortes", "zoom": "Zoom",
                 "pan": "Pan", "wl": "Janela/nível"}

        def name(key, default):
            v = mouse.get(key, default)
            return tr(TOOLS.get(v, wheel.get(v, v)))

        out = [("Esquerdo", tr(TOOLS.get(self.left_tool, self.left_tool))),
               ("Direito", name("right", "zoom")),
               ("Meio", name("middle", "pan")),
               ("Roda", name("wheel", "scroll")),
               ("Ctrl+roda", name("ctrl_wheel", "zoom")),
               ("Shift+roda", name("shift_wheel", "scroll5"))]
        if mouse.get("right_click", "menu") == "menu":
            out[1] = ("Direito", out[1][1] + tr(" (clique: menu)"))
        if mouse.get("middle_click", "fit") == "fit":
            out[2] = ("Meio", out[2][1] + tr(" (clique: ajustar à janela)"))
        # entram no fim: as linhas acima mexem em out[1] e out[2] pela posição
        nomes = {"shift": "Shift", "ctrl": "Ctrl", "alt": "Alt"}
        for ferramenta, tecla in self.teclas_emprestadas().items():
            if tecla in nomes and ferramenta in TOOLS:
                out.append((nomes[tecla] + tr(" (segurar)"), tr(TOOLS[ferramenta])))
        return [(tr(b), t) for b, t in out]

    def _draw_mouse_icon(self, p: QPainter, font: QFont, margin: int, lh: float,
                         hot_enabled: bool) -> None:
        """Ícone pequeno do mouse; o balão com os botões aparece ao passar o mouse por cima."""
        w, h = 13.0, 19.0
        y = self.height() / 2 + lh * 2 - h
        rect = QRectF(margin, y, w, h)
        if hot_enabled:
            self._hotspots.setdefault("mouse", rect.adjusted(-3, -3, 3, 3))
        on = self._hover == "mouse"
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(QColor(0, 0, 0, 120))
        p.setPen(QPen(QColor(255, 220, 120) if on else QColor(150, 200, 255), 1.4))
        p.drawRoundedRect(rect, w / 2, w / 2)
        if self.left_tool != "wl":       # alguma ferramenta ligada: botão esquerdo aceso
            p.save()
            p.setClipRect(QRectF(rect.left(), rect.top(), w / 2, h * 0.4))
            p.setBrush(QColor(255, 200, 0, 190))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(rect, w / 2, w / 2)
            p.restore()
            p.setPen(QPen(QColor(255, 220, 120) if on else QColor(150, 200, 255), 1.4))
        p.drawLine(QPointF(rect.center().x(), rect.top() + 1.5),
                   QPointF(rect.center().x(), rect.top() + h * 0.38))
        p.setBrush(QColor(255, 220, 120) if on else QColor(150, 200, 255))
        p.drawEllipse(QPointF(rect.center().x(), rect.top() + h * 0.52), 1.4, 1.4)
        p.restore()
        if on:
            self._draw_mouse_balloon(p, font, rect)

    def _draw_mouse_balloon(self, p: QPainter, font: QFont, icon: QRectF) -> None:
        fm = QFontMetrics(font)
        lh = fm.height() + 2
        items = self.mouse_actions()
        title = "Botões do mouse"
        rows = [f"{b}:  {t}" for b, t in items]
        tw = max([fm.horizontalAdvance(title)] + [fm.horizontalAdvance(r) for r in rows]) + 16
        th = lh * (len(rows) + 1) + 12
        x = min(icon.right() + 8, max(0.0, self.width() - tw - 4))
        y = min(max(4.0, icon.center().y() - th / 2), max(4.0, self.height() - th - 4))
        box = QRectF(x, y, tw, th)
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(QColor(0, 0, 0, 205))
        p.setPen(QPen(QColor(150, 200, 255), 1))
        p.drawRoundedRect(box, 5, 5)
        p.setFont(font)
        yy = box.top() + 6 + fm.ascent()
        p.setPen(QColor(255, 220, 120))
        p.drawText(QPointF(box.left() + 8, yy), title)
        p.setPen(QColor(225, 235, 245))
        for r in rows:
            yy += lh
            p.drawText(QPointF(box.left() + 8, yy), r)
        p.restore()

    def _fusion_image(self) -> tuple[QImage, int] | None:
        fu, pl = self.fusion, self.plane()
        if fu is None or pl is None or self._img is None:
            return None
        pos, row, col, _n = pl
        h, w = self._img.pixels.shape[:2]
        rs, cs = self._spacing()
        key = (id(fu), fu.version, self.index, id(self._img), tuple(np.round(pos, 3)), h, w,
               fu.modo, round(fu.cortina, 3), round(self.state.width, 2), round(self.state.level, 2))
        if self._fusion_cache is not None and self._fusion_cache[0] == key:
            return self._fusion_cache[1], self._fusion_cache[2]
        vals, stride = fu.values(pos, row, col, rs, cs, h, w)
        if fu.modo in fu.MODOS_DE_CONFERIR:
            a8 = None
            if fu.modo == "diferenca" and not self._img.is_color:
                disp = to_display(self._img, self.state.width, self.state.level, self.state.invert, None)
                a8 = disp[(stride - 1) // 2::stride, (stride - 1) // 2::stride][:vals.shape[0], :vals.shape[1]]
                if a8.ndim != 2:
                    a8 = None
            rgba = np.ascontiguousarray(fu.conferir(vals, a8))
        else:
            rgba = np.ascontiguousarray(fu.rgba(vals))
        q = QImage(rgba.data, rgba.shape[1], rgba.shape[0], rgba.strides[0], QImage.Format_RGBA8888).copy()
        self._fusion_cache = (key, q, stride)
        return q, stride

    def _draw_fusion(self, p: QPainter) -> None:
        try:
            res = self._fusion_image()
        except Exception as e:  # noqa: BLE001
            log.warning("fusão: %s", e)
            return
        if res is None:
            return
        q, stride = res
        r = self._image_rect()                  # o pintor já está com o giro/espelho
        h, w = self._img.pixels.shape[:2]
        tl = QPointF(r.x(), r.y())
        br = QPointF(r.x() + q.width() * stride / w * r.width(), r.y() + q.height() * stride / h * r.height())
        p.save()
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.drawImage(QRectF(tl, br), q)
        p.restore()

    #: raio do pincel de estruturas (mm), posto pelo painel Estruturas (0.99.40); 0 = sem círculo
    pincel_raio_mm: float = 0.0
    _pincel_pos = None

    def _desenhar_pincel(self, p: QPainter) -> None:
        """O círculo do pincel de estruturas em volta do mouse, do tamanho que ele pinta."""
        if self.left_tool != "pincel" or not self.pincel_raio_mm or self._pincel_pos is None \
                or self._capturando or not self.underMouse():
            return
        sp = self._spacing()
        if not sp:
            return
        ip = self.widget_to_image(self._pincel_pos)
        borda = self.image_to_widget(QPointF(ip.x() + self.pincel_raio_mm / float(sp[1]), ip.y()))
        r = math.hypot(borda.x() - self._pincel_pos.x(), borda.y() - self._pincel_pos.y())
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 180), 3))
        p.drawEllipse(self._pincel_pos, r, r)
        p.setPen(QPen(QColor(255, 120, 120) if getattr(self, "pincel_apaga", False) else QColor(255, 255, 255), 1.5))
        p.drawEllipse(self._pincel_pos, r, r)
        p.restore()

    def _draw_loupe(self, p: QPainter, q: QImage) -> None:
        """Lupa circular: a imagem em resolução original, aumentada em volta do cursor."""
        from PySide6.QtGui import QPainterPath
        c = self._loupe
        r = float(self.settings.get("viewer.loupe_size", 240) or 240) / 2
        f = self.loupe_zoom
        p.save()
        path = QPainterPath()
        path.addEllipse(c, r, r)
        p.setClipPath(path)
        p.fillRect(QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r), QColor(0, 0, 0))
        p.translate(c)
        p.scale(f, f)
        p.translate(-c)
        if self.is_transformed():
            p.setTransform(self.display_transform(), True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        p.drawImage(self._image_rect(), q)
        p.restore()
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor(255, 210, 60), 2))
        p.drawEllipse(c, r, r)
        p.setPen(QColor(255, 210, 60))
        p.drawText(QPointF(c.x() + r * 0.62, c.y() + r * 0.9), f"{f:g}×")
        p.restore()

    def _draw_ghosts(self, p: QPainter) -> None:
        """Pontos/ROIs desenhados em outro quadro (mesma grade), tracejados; "star" = pior pixel."""
        from PySide6.QtGui import QPolygonF
        for kind, pts, color in self.ghosts:
            q = [self.image_to_widget(QPointF(*pt)) for pt in pts]
            pen = QPen(color, 1.6)
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            if kind == "probe" and q:
                p.drawEllipse(q[0], 5, 5)
            elif kind == "star" and q:
                pen.setStyle(Qt.SolidLine)
                p.setPen(pen)
                c = q[0]
                for dx, dy in ((1, 0), (0, 1), (0.7, 0.7), (0.7, -0.7)):
                    p.drawLine(c + QPointF(-7 * dx, -7 * dy), c + QPointF(7 * dx, 7 * dy))
            elif kind in ("ellipse", "tic") and len(q) >= 2:
                p.drawEllipse(QRectF(q[0], q[1]).normalized())
            elif kind == "rect" and len(q) >= 2:
                p.drawRect(QRectF(q[0], q[1]).normalized())
            elif kind == "polygon" and len(q) >= 3:
                p.drawPolygon(QPolygonF(q))

    def _draw_colorbar(self, p: QPainter, font: QFont) -> None:
        """Barra da tabela de cores com os valores das pontas da janela."""
        h = min(140.0, self.height() * 0.25)
        x = self.width() - self.POSBAR_W - 22
        y = self.height() * 0.58
        lut = CM.lut(self.state.cmap)
        if self.state.invert != (self._img.header.get("_monochrome1") == "1"):
            lut = lut[::-1]
        col = np.ascontiguousarray(np.repeat(lut[::-1][:, None, :], 8, axis=1))
        q = QImage(col.data, 8, 256, col.strides[0], QImage.Format_RGB888).copy()
        rect = QRectF(x, y, 8, h)
        p.drawImage(rect, q)
        p.setPen(QColor(160, 160, 160))
        p.drawRect(rect)
        f = QFont(font)
        f.setPointSizeF(max(6.5, font.pointSizeF() - 1.5))
        p.setFont(f)
        fm = QFontMetrics(f)
        lo = self.state.level - self.state.width / 2
        hi = self.state.level + self.state.width / 2
        scale = self.suv_factor if getattr(self, "suv_factor", None) else None
        for chave, val, yy in (("cbar_hi", hi, y - 3), ("cbar_lo", lo, y + h + fm.ascent() + 2)):
            v = val * scale if scale else val
            t = f"{v:.1f}" if abs(v) < 100 else f"{v:.0f}"
            tw = fm.horizontalAdvance(t)
            tx = x + 4 - tw / 2
            # cada ponta é clicável: clique digita o valor, arrastar ajusta só aquela ponta
            rect = QRectF(tx - 5, yy - fm.ascent() - 3, max(tw, 18) + 10, fm.height() + 6)
            self._hotspots.setdefault(chave, rect)
            if self._hover == chave:
                p.fillRect(rect, QColor(255, 200, 0, 60))
            p.setPen(QColor(0, 0, 0))
            p.drawText(QPointF(tx + 1, yy + 1), t)
            p.setPen(QColor(255, 220, 120) if self._hover == chave else QColor(220, 220, 220))
            p.drawText(QPointF(tx, yy), t)

    def _draw_sync_icon(self, p: QPainter, font: QFont, margin: float, lh: float,
                        hot_enabled: bool) -> None:
        """Ícone de corrente (grupo de sincronização). Clicável: troca o grupo do quadro."""
        color = self.sync_color or QColor(110, 110, 110)
        x = self.width() / 2 - 40
        y = self.height() - margin - lh
        rect = QRectF(x - 4, y - 2, 64, lh + 4)
        if hot_enabled:
            self._hotspots.setdefault("sync", rect)
            if self._hover == "sync":
                p.fillRect(rect, QColor(255, 200, 0, 60))
        pen = QPen(color)
        pen.setWidth(2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        cy = y + lh / 2
        p.drawRoundedRect(QRectF(x, cy - 4, 13, 8), 4, 4)
        p.drawRoundedRect(QRectF(x + 8, cy - 4, 13, 8), 4, 4)
        p.setFont(font)
        p.drawText(QPointF(x + 26, y + QFontMetrics(font).ascent()), self.sync_label or "")

    def _draw_reference_lines(self, p: QPainter) -> None:
        """Linhas onde os planos dos outros quadros cortam este plano + cursor 3D."""
        pl = self.plane()
        if pl is None or self._img is None:
            return
        pos, row, col, n = pl
        rs, cs = self._spacing()
        h, w = self._img.pixels.shape[:2]
        lines = [(po, no, color, 1) for po, no, color in self.ref_planes]
        for t in self.oblique_targets:
            tp = t.plane() if t.isVisible() and t.mpr_plane is not None and t.mpr_plane.name == "Oblíquo" else None
            if tp is not None:
                lines.append((tp[0], tp[3], QColor(255, 60, 255), 2))
        for p_other, n_other, color, width in lines:
            # n_o·(pos + u·cs·row + v·rs·col − p_o) = 0  ->  a·u + b·v + c = 0
            a = cs * float(n_other @ row)
            b = rs * float(n_other @ col)
            c = float(n_other @ (pos - p_other))
            if abs(a) < 1e-6 and abs(b) < 1e-6:
                continue          # planos paralelos
            pts = []
            for u in (0.0, float(w)):
                if abs(b) > 1e-9:
                    v = -(a * u + c) / b
                    if 0 <= v <= h:
                        pts.append((u, v))
            for v in (0.0, float(h)):
                if abs(a) > 1e-9:
                    u = -(b * v + c) / a
                    if 0 <= u <= w:
                        pts.append((u, v))
            if len(pts) >= 2:
                pen = QPen(color)
                pen.setWidth(width)
                pen.setStyle(Qt.DashLine)
                p.setPen(pen)
                p.drawLine(self.image_to_widget(QPointF(*pts[0])), self.image_to_widget(QPointF(*pts[-1])))
        for path, live in [(np.array(self._curve_pts), True)] * bool(self._curve_pts) + \
                [(pp, False) for pp in self.curve_paths]:
            uvd = [self.patient_to_pixel(q) for q in path]
            if any(x is None for x in uvd):
                continue
            wp = [self.image_to_widget(QPointF(u, v)) for u, v, _d in uvd]
            pen = QPen(QColor(0, 230, 255), 2)
            if not live:
                pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            for a, b in zip(wp, wp[1:]):
                p.drawLine(a, b)
            tol = max(rs, cs, 1.0) * 1.5
            for q, (_u, _v, dd) in zip(wp, uvd):
                p.setBrush(QColor(0, 230, 255) if abs(dd) <= tol else Qt.NoBrush)
                p.drawEllipse(q, 3.5, 3.5)
            p.setBrush(Qt.NoBrush)
        if self._obl_draft is not None:
            pen = QPen(QColor(255, 60, 255))
            pen.setWidth(2)
            p.setPen(pen)
            p.drawLine(self.image_to_widget(self._obl_draft[0]), self.image_to_widget(self._obl_draft[1]))
        if self.cursor_point is not None:
            uvd = self.patient_to_pixel(self.cursor_point)
            if uvd is not None and abs(uvd[2]) <= max(rs, cs, 1.0) * 2:
                c = self.image_to_widget(QPointF(uvd[0], uvd[1]))
                pen = QPen(QColor(255, 80, 80))
                pen.setWidth(2)
                p.setPen(pen)
                for dx, dy in ((1, 0), (0, 1)):
                    p.drawLine(c + QPointF(-12 * dx, -12 * dy), c + QPointF(-4 * dx, -4 * dy))
                    p.drawLine(c + QPointF(4 * dx, 4 * dy), c + QPointF(12 * dx, 12 * dy))

    def resizeEvent(self, e) -> None:  # noqa: N802
        """O enquadramento da mama vem do tamanho do quadro: se o quadro muda, ele tem de ser
        refeito. É isto que fazia o exame abrir sem o zoom — ao montar a etapa o quadro ainda não
        tinha o tamanho final, e só na segunda etapa a conta encontrava a tela de verdade."""
        super().resizeEvent(e)
        lock = getattr(self, "anat_lock", None)
        if lock and lock[0] == "mama":
            self.sig.enquadre_pendente.emit(self)

    # ------------------------------------------------------------ mouse
    def _hotspot_at(self, pos: QPointF) -> str | None:
        for name, rect in self._hotspots.items():
            if rect.contains(pos):
                return name
        return None

    def _button_name(self, b: Qt.MouseButton) -> str:
        return {Qt.LeftButton: "left", Qt.RightButton: "right",
                Qt.MiddleButton: "middle", Qt.BackButton: "back",
                Qt.ForwardButton: "forward"}.get(b, "")

    def vazio(self) -> bool:
        """Quadro sem nada para mostrar (nem imagem, nem volume 3D, nem imagem com defeito)."""
        return not self.frames and self._img is None and self.render3d is None

    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        self.sig.activated.emit(self)
        self.setFocus()
        pos = e.position()
        button = self._button_name(e.button())
        if button == "left" and self.vazio():
            # quadro vazio (o protocolo não achou a série, ou nada foi posto aqui): o clique abre a
            # lista de séries do exame e a escolhida entra **só neste quadro** — o protocolo não muda
            self.sig.empty_clicked.emit(self, self.mapToGlobal(pos.toPoint()))
            return
        if button in ("back", "forward"):
            mouse = self.settings.get("viewer.mouse", {})
            default = "series_prev" if button == "back" else "series_next"
            self.sig.button_action.emit(self, mouse.get(button, default))
            return
        # com a tecla que empresta uma ferramenta (Ctrl = rolar), o clique não pega a barra de posição
        # nem os cantos: senão clicar com Ctrl em cima deles pulava para outro corte
        com_tecla = button == "left" and bool(self.tecla_de_atalho(e.modifiers()))
        hot = self._hotspot_at(pos) if button == "left" and not com_tecla else None
        if hot is None and button == "right":
            direito = self._hotspot_at(pos)
            if direito in HOTSPOTS_DOS_DOIS_BOTOES:     # o canto da fase anda nos dois sentidos
                hot = direito
        if button == "left" and not com_tecla and hot is None and len(self.frames) > 1 \
                and self.posbar_rect().contains(pos):
            hot = "posbar"
            self.go_to(self._posbar_index(pos.y()))
        tool = self.button_tool(button)
        # Shift + direito/meio: volta ao comportamento padrão (menu / ajustar) mesmo com ferramenta de clique
        if button in ("right", "middle") and e.modifiers() & Qt.ShiftModifier and self.is_click_tool(tool):
            tool = "none"
        atalho = self.tecla_de_atalho(e.modifiers()) if button == "left" else ""
        if atalho:
            # Enquanto a tecla está apertada o botão esquerdo faz outra coisa; a ferramenta
            # escolhida na barra **não muda**, e ao soltar tudo volta ao que era.
            tool = atalho
        self._press = {"button": button, "pos": pos, "last": pos, "t": time.monotonic(),
                       "moved": False, "hot": hot, "tool": tool}
        if self.render3d is not None and hot is None and self.render3d.press(self, pos, button):
            return
        if self.em_mosaico() and hot is None and (tool in ANNOT_TOOLS or tool in CLICK_TOOLS or tool == "pincel"):
            self.sig.status_message.emit("Mosaico: só para ver. Duplo clique numa imagem volta ao quadro "
                                         "normal nela, para medir.")
            self._press = None
            return
        if hot is None and tool in ANNOT_TOOLS and self._img is not None:
            self._annot_press(pos)
        if hot == TOMO_DIAL:
            self._tomo_dial_jump(pos)
        if hot is None and tool == "cross":
            self._set_cursor_at(pos)
        if hot is None and tool == "loupe" and self._img is not None:
            self._loupe = pos
            self.setCursor(Qt.BlankCursor)
            self.update()
        if hot is None and tool == "oblique" and self._img is not None:
            ip = self.widget_to_image(pos)
            self._obl_draft = [ip, ip]
        if hot is None and tool == "pincel" and self._img is not None:
            ip = self.widget_to_image(pos)
            self.sig.pincel.emit(self, ip.x(), ip.y(), "ini")

    # ---------------------------------------------- teclas que emprestam o botão esquerdo
    # A ferramenta é emprestada **enquanto a tecla está apertada**; a da barra não muda. Qual
    # tecla empresta qual ferramenta se escolhe em Preferências ▸ Atalhos de teclado.
    TECLAS = {"shift": Qt.ShiftModifier, "ctrl": Qt.ControlModifier, "alt": Qt.AltModifier}
    PADRAO_TECLAS = {"cross": "shift", "scroll": "ctrl"}
    ORDEM_TECLAS = ("scroll", "cross")        # quem ganha quando duas teclas estão apertadas

    def teclas_emprestadas(self) -> dict[str, str]:
        """{ferramenta: tecla}. Vazio = ninguém empresta nada."""
        if self.settings is None:
            return dict(self.PADRAO_TECLAS)
        guardado = self.settings.get("viewer.teclas_emprestadas", None)
        if guardado is None:          # versões anteriores tinham só uma caixa de liga/desliga
            return dict(self.PADRAO_TECLAS) if self.settings.get("viewer.teclas_do_mouse", True) else {}
        return {f: k for f, k in (guardado or {}).items() if k in self.TECLAS}

    PONTEIRO_DA_TECLA = {"cross": Qt.CrossCursor, "scroll": Qt.SizeVerCursor}

    def _tecla_sem_clique(self, pos, mods) -> bool:
        """Tecla segurada **sem clicar**: a ferramenta emprestada já age enquanto o mouse passa.

        Vale para o cursor 3D (o ponto segue o mouse) e para rolar (sobe e desce troca o corte).
        Se a tecla já diz o que fazer, o clique sobra.
        """
        ferramenta = self.tecla_de_atalho(mods)
        if ferramenta not in self.PONTEIRO_DA_TECLA or self._img is None \
                or self._draft is not None or self.render3d is not None:
            return False
        if ferramenta == "cross":
            self._set_cursor_at(pos)
        else:                                     # rolar: acumula o movimento vertical
            # 0.99.7: *"quando eu seguro o Ctrl para rolar, muitas vezes o viewer muda a imagem onde
            # estou"*. A referência do movimento ficava da última vez que a tecla foi usada (ou de outro
            # quadro): o primeiro movimento pulava muitos cortes de uma vez. Agora a referência é onde
            # o mouse está quando a tecla desce, some ao sair do quadro, e um salto grande não conta.
            salto = self._ultimo_hover is not None and abs(pos.y() - self._ultimo_hover.y()) > 60
            if self._cursor_por_tecla and self._ultimo_hover is not None and not salto:
                acc = self._acc_tecla + (pos.y() - self._ultimo_hover.y())
                passos = int(acc / 4)
                self._acc_tecla = acc - passos * 4
                if passos:
                    self.step(passos)
            else:
                self._acc_tecla = 0.0
        self._ultimo_hover = pos
        self.setCursor(self.PONTEIRO_DA_TECLA[ferramenta])
        self._cursor_por_tecla = True
        return True

    def tecla_de_atalho(self, mods) -> str:
        """Ferramenta emprestada agora pela tecla apertada; vazio quando nenhuma está."""
        teclas = self.teclas_emprestadas()
        for ferramenta in self.ORDEM_TECLAS:
            tecla = teclas.get(ferramenta, "")
            if tecla and mods & self.TECLAS[tecla]:
                return ferramenta
        return ""

    def button_tool(self, button: str) -> str:
        """Ferramenta de cada botão: esquerdo = a escolhida na barra; direito/meio = Preferências
        (ou clique com esse botão num ícone da barra)."""
        if button == "left":
            return self.left_tool
        mouse = self.settings.get("viewer.mouse", {})
        if button == "right":
            return mouse.get("right", "zoom")
        if button == "middle":
            return mouse.get("middle", "pan")
        return "none"

    @staticmethod
    def is_click_tool(tool: str) -> bool:
        return tool in ANNOT_TOOLS or tool in CLICK_TOOLS

    # ------------------------------------------------------------ desenho de medidas
    def _set_cursor_at(self, pos: QPointF) -> None:
        if self._img is None:
            return
        ip = self.widget_to_image(pos)
        pt = self.pixel_to_patient(ip.x(), ip.y())
        if pt is not None:
            self.cursor_point = pt
            self.update()
            self.sig.cursor_moved.emit(self, pt)

    # ------------------------------------------------- pontas da barra de cores
    def colorbar_ends(self) -> tuple[float, float]:
        """Valores de baixo e de cima da escala, nas unidades que aparecem na tela."""
        escala = self.suv_factor if getattr(self, "suv_factor", None) else 1.0
        lo = (self.state.level - self.state.width / 2) * escala
        hi = (self.state.level + self.state.width / 2) * escala
        return lo, hi

    def set_colorbar_end(self, qual: str, valor: float) -> bool:
        """Muda uma ponta da escala sem mexer na outra. `qual`: "cbar_hi" ou "cbar_lo"."""
        if self._img is None or qual not in CBAR:
            return False
        escala = self.suv_factor if getattr(self, "suv_factor", None) else 1.0
        lo, hi = self.colorbar_ends()
        if qual == "cbar_hi":
            hi = max(float(valor), lo + 1e-6 * max(abs(lo), 1.0))
        else:
            lo = min(float(valor), hi - 1e-6 * max(abs(hi), 1.0))
        lo, hi = lo / escala, hi / escala
        self.state.width = max(hi - lo, 1e-6)
        self.state.level = (hi + lo) / 2
        self.state.window_set = True
        self._qimage_key = None
        self.sig.view_changed.emit(self, "window")
        self.update()
        return True

    def _colorbar_drag(self, qual: str, dy: float) -> None:
        lo, hi = self.colorbar_ends()
        k = max(abs(hi - lo), 1.0) / 250.0
        self.set_colorbar_end(qual, (hi if qual == "cbar_hi" else lo) - dy * k)

    def _colorbar_ask(self, qual: str) -> None:
        from PySide6.QtWidgets import QInputDialog
        lo, hi = self.colorbar_ends()
        atual = hi if qual == "cbar_hi" else lo
        titulo = "Topo da escala de cores" if qual == "cbar_hi" else "Base da escala de cores"
        rotulo = "Valor (SUV):" if getattr(self, "suv_factor", None) else "Valor:"
        valor, ok = QInputDialog.getDouble(self, titulo, rotulo, float(atual), -1e9, 1e9, 2)
        if ok:
            self.set_colorbar_end(qual, valor)

    def _tomo_dial_jump(self, pos: QPointF) -> None:
        """Clique ou arrasto no indicador de profundidade: vai para aquele corte."""
        from ipe.ui.viewer import tomo_dial as TD
        lh, linhas = self._overlay_metrics()
        alvo = TD.index_at(self, pos, lh, linhas)
        if alvo is not None and alvo != self.index:
            self.go_to(alvo)
        recado = TD.tip(self)
        if recado:
            self.sig.status_message.emit(recado)

    def _overlay_metrics(self) -> tuple[float, int]:
        """Altura da linha e quantas linhas tem o canto de baixo onde o indicador fica."""
        font = QFont()
        font.setPointSizeF(max(7.0, min(10.0, self.width() / 60)))
        lh = QFontMetrics(font).height()
        canto = "br" if self.chest_screen_side() == "left" else "bl"
        try:
            return lh, len(self._text_lines()[canto])
        except Exception:  # noqa: BLE001
            return lh, 0

    def _tool_for_drag(self) -> str:
        pr = self._press
        if pr["button"] == "left" and pr["hot"]:
            return self._hot_to_tool(pr["hot"])
        return pr.get("tool") or "none"

    @staticmethod
    def _hot_to_tool(hot: str) -> str:
        if hot == "scroll":
            return "scroll"
        if hot == "zoom":
            return "zoom"
        if hot == "wl":
            return "wl"
        if hot.startswith("pan_"):
            return "pan"
        return "none"

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        pos = e.position()
        pr = self._press
        if pr is None and self._tecla_sem_clique(pos, e.modifiers()):
            return
        if self._cursor_por_tecla and pr is None:
            self._cursor_por_tecla = False
            self._acc_tecla = 0.0
            self.setCursor(Qt.ArrowCursor)
        if pr is None and self.fusion is not None and getattr(self.fusion, "modo", "") == "cortina" \
                and self._img is not None:
            ip = self.widget_to_image(pos)                 # a cortina segue o mouse (0.99.44)
            w = self._img.pixels.shape[1]
            self.fusion.cortina = float(np.clip(ip.x() / max(w, 1), 0, 1))
            self.update()
        if pr is None:
            if self.left_tool == "pincel":
                self._pincel_pos = pos
                self.update()
            self._annot_hover(pos)
            if self.fusion is not None and self._img is not None:
                ip = self.widget_to_image(pos)
                pt = self.pixel_to_patient(ip.x(), ip.y())
                self.fusion_value = self.fusion.value_at(pt) if pt is not None else None
                self.update()
            if self._img is not None and self.dyn_key is not None:
                ip = self.widget_to_image(pos)
                self.sig.hover_moved.emit(self, ip.x(), ip.y())
            hot = self._hotspot_at(pos)
            if hot is None and len(self.frames) > 1 and self.posbar_rect().contains(pos):
                hot = "posbar"
            if hot != self._hover:
                self._hover = hot
                self.setCursor(Qt.PointingHandCursor if hot else Qt.ArrowCursor)
                self.update()
            return
        if not pr["hot"] and pr["tool"] == "pincel":
            pr["moved"] = True
            self._pincel_pos = pos
            if self._img is not None:
                ip = self.widget_to_image(pos)
                self.sig.pincel.emit(self, ip.x(), ip.y(), "meio")
            return
        max_px = self.settings.get("viewer.click_max_px", 4)
        if not pr["moved"] and (pos - pr["pos"]).manhattanLength() <= max_px:
            return
        pr["moved"] = True
        dx, dy = pos.x() - pr["last"].x(), pos.y() - pr["last"].y()
        pr["last"] = pos
        if pr["hot"] == "posbar":
            self.go_to(self._posbar_index(pos.y()))
            return
        if pr["hot"] == TOMO_DIAL:
            self._tomo_dial_jump(pos)
            return
        if pr["hot"] in CBAR:
            self._colorbar_drag(pr["hot"], dy)
            return
        if self.render3d is not None and not pr["hot"] \
                and self.render3d.drag(self, pos, dx, dy, pr):
            return
        if not pr["hot"] and pr["tool"] in ANNOT_TOOLS and self._img is not None:
            self._annot_move(pos)
            return
        if not pr["hot"] and pr["tool"] == "cross":
            self._set_cursor_at(pos)
            return
        if not pr["hot"] and pr["tool"] == "loupe":
            self._loupe = pos
            self.update()
            return
        if not pr["hot"] and pr["tool"] == "grow":
            return                      # crescer região é clique; arrastar com ela não faz nada
        if not pr["hot"] and pr["tool"] == "quadzoom":
            return
        if not pr["hot"] and pr["tool"] == "oblique":
            if self._obl_draft is not None:
                self._obl_draft[1] = self.widget_to_image(pos)
                self.update()
            return
        if not pr["hot"] and pr["tool"] == "film":
            return
        self._apply_drag(self._tool_for_drag(), dx, dy, pr)

    def _apply_drag(self, tool: str, dx: float, dy: float, pr: dict) -> None:
        if self._img is None:
            return
        if tool == "wl" and not self._img.is_color:
            k = max(self.state.width, 1.0) / 300.0
            self.state.width = max(1.0, self.state.width + dx * k)
            self.state.level = self.state.level + dy * k
            self.state.window_set = True
            self.sig.view_changed.emit(self, "window")
        elif tool == "zoom":
            old = self.state.zoom
            self.state.zoom = float(np.clip(old * math.exp(-dy * 0.01), 0.05, 40))
            # zoom em torno do ponto clicado
            c = QPointF(self.width() / 2, self.height() / 2) + self.state.pan
            anchor = self._to_unrotated(pr["pos"])
            f = self.state.zoom / old
            self.state.pan += (anchor - c) * (1 - f)
            self.sig.view_changed.emit(self, "zoom")
        elif tool == "pan":
            self.state.pan += self._delta_unrotated(QPointF(dx, dy))
            self.sig.view_changed.emit(self, "pan")
        elif tool == "rotplane":
            # Acumula e só pede a reconstrução a cada 2°: refazer o plano a cada pixel de arrasto
            # é trabalho jogado fora, e a imagem não acompanharia mesmo.
            gh = pr.get("acc_h", 0.0) + dx * 0.4
            gv = pr.get("acc_v", 0.0) + dy * 0.4
            if abs(gh) >= 2.0 or abs(gv) >= 2.0:
                self.sig.plane_rotate_requested.emit(self, gh, gv)
                gh = gv = 0.0
            pr["acc_h"], pr["acc_v"] = gh, gv
        elif tool == "scroll":
            acc = pr.get("acc", 0.0) + dy
            steps = int(acc / 4)
            pr["acc"] = acc - steps * 4
            if steps:
                self.step(steps)
        self.update()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        pr = self._press
        self._press = None
        if pr is None:
            return
        elapsed_ms = (time.monotonic() - pr["t"]) * 1000
        is_click = not pr["moved"] and elapsed_ms <= self.settings.get("viewer.click_max_ms", 220)
        pos = e.position()
        if self.render3d is not None and not pr["hot"] \
                and self.render3d.release(self, pos, pr, is_click):
            return
        if not pr["hot"] and pr["tool"] in ANNOT_TOOLS and self._img is not None:
            self._press_done = pr
            self._annot_release(pos, pr["moved"])
            return
        if not pr["hot"] and pr["tool"] == "film":
            if not pr["moved"] and self.frames:
                self.sig.film_requested.emit(self)
            return
        if not pr["hot"] and pr["tool"] == "cross":
            return
        if not pr["hot"] and pr["tool"] == "pincel":
            if self._img is not None:
                ip = self.widget_to_image(pos)
                self.sig.pincel.emit(self, ip.x(), ip.y(), "fim")
            return
        if not pr["hot"] and pr["tool"] == "grow":
            # Clique de segmentar: sai no soltar. Sem limite de tempo de propósito — mirar numa
            # lesão demora mais que um clique rápido, e o clique lento sumia sem dizer nada.
            if not pr["moved"] and self._img is not None:
                ip = self.widget_to_image(pos)
                self.sig.segment_requested.emit(self, ip.x(), ip.y())
            return
        if not pr["hot"] and pr["tool"] == "loupe":
            self._loupe = None
            self.setCursor(Qt.ArrowCursor)
            self.update()
            return
        if not pr["hot"] and pr["tool"] == "quadzoom":
            if not pr["moved"] and self._img is not None:
                self.sig.quadrant_cycle.emit(self, -1 if e.modifiers() & Qt.ShiftModifier else 1)
            return
        if not pr["hot"] and pr["tool"] == "curve":
            if not pr["moved"] and self._img is not None:
                ip = self.widget_to_image(pos)
                pt = self.pixel_to_patient(ip.x(), ip.y())
                if pt is not None and not (self._curve_pts and np.linalg.norm(pt - self._curve_pts[-1]) < 0.5):
                    self._curve_pts.append(pt)
                    self.update()
            return
        if not pr["hot"] and pr["tool"] == "oblique":
            draft, self._obl_draft = self._obl_draft, None
            self.update()
            if draft is not None and pr["moved"]:
                a, b = draft[0], self.widget_to_image(pos)
                p0, p1 = self.pixel_to_patient(a.x(), a.y()), self.pixel_to_patient(b.x(), b.y())
                if p0 is not None and p1 is not None:
                    self.sig.oblique_requested.emit(self, p0, p1)
            return
        if not is_click:
            return
        mouse = self.settings.get("viewer.mouse", {})
        if pr["hot"] and (pr["button"] == "left" or pr["hot"] in HOTSPOTS_DOS_DOIS_BOTOES):
            self._click_hotspot(pr["hot"], e.globalPosition().toPoint(), pr["button"])
        elif pr["button"] == "right" and mouse.get("right_click", "menu") == "menu":
            self.show_context_menu(e.globalPosition().toPoint(), pos)
        elif pr["button"] == "middle" and mouse.get("middle_click", "fit") == "fit":
            self.fit()

    def _click_hotspot(self, hot: str, global_pos, button: str = "left") -> None:
        if hot == "fase":
            self.set_phase((self.phase + (1 if button == "left" else -1)) % max(len(self.phases or [1]), 1))
            return
        if hot == "plano":
            self.sig.plane_menu_requested.emit(self, global_pos)
            return
        if hot in CBAR:
            self._colorbar_ask(hot)
            return
        if hot == "escala":
            self.menu_da_escala(global_pos)
            return
        if hot == "selos":
            self.explicar_selos()
            return
        if hot == "orient":
            m = QMenu(self)
            self.add_orientation_actions(m)
            m.exec(global_pos)
            return
        if hot == "series":
            self.sig.series_menu_requested.emit(self, global_pos)
        elif hot == "annots":
            self.show_annotation_menu(global_pos)
        elif hot == "phase":
            self.show_phase_menu(global_pos)
        elif hot == "posbar":
            pass
        elif hot == "sync":
            self.sig.sync_group_requested.emit(self)
        elif hot == "mouse":
            m = QMenu(self)
            m.addAction(QAction("Mouse (botão esquerdo)", m)).setEnabled(False)
            self.acoes_de_ferramenta(m, medidas_em_submenu=True)
            m.exec(global_pos)
        else:
            self.sig.tool_requested.emit(self._hot_to_tool(hot))

    def acoes_de_ferramenta(self, menu, medidas_em_submenu: bool = True,
                            so_medidas: bool = False) -> None:
        """Põe no menu as ferramentas do botão esquerdo, separadas em mouse e medidas."""
        from ipe.ui.viewer.annotate import ferramentas_divididas
        mouse, medidas = ferramentas_divididas()

        def preencher(alvo, itens):
            for key, name in itens.items():
                act = QAction(name, alvo, checkable=True, checked=(key == self.left_tool))
                act.triggered.connect(lambda _=False, kk=key: self.sig.tool_requested.emit(kk))
                alvo.addAction(act)
        if so_medidas:
            preencher(menu, medidas)
            return
        preencher(menu, mouse)
        if medidas_em_submenu:
            menu.addSeparator()
            preencher(menu.addMenu("Medidas"), medidas)

    def finish_curve(self) -> bool:
        pts, self._curve_pts = self._curve_pts, []
        self.update()
        if len(pts) >= 2:
            self.curve_paths = [np.array(pts)]
            self.sig.curved_requested.emit(self, np.array(pts))
            return True
        return False

    def mouseDoubleClickEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if self.em_mosaico() and e.button() == Qt.LeftButton:
            i = self.mosaico_indice_em(e.position())
            self.set_mosaico(None)
            if i is not None:
                self.go_to(i)
            return
        hot = self._hotspot_at(e.position())
        btool = self.button_tool(self._button_name(e.button()))
        if hot is None and btool == "curve":
            self.finish_curve()
            return
        if hot is None and btool in ANNOT_TOOLS and self._img is not None \
                and (e.button() == Qt.LeftButton or not e.modifiers() & Qt.ShiftModifier):
            if self.finish_draft():
                return
            a = self._annotation_at(self._img_pt(e.position()), self._img_tol())
            if a is not None and a.kind in ("text", "arrow"):
                self.edit_text(a)
                return
            if a is not None and a.kind == "tic":
                self.sig.tic_requested.emit(self, a)
                return
            if self._draft is not None:
                return
        if hot in ("sync", "annots", "posbar", "phase"):
            return
        if hot == "scroll" and self.frames:
            n, ok = QInputDialog.getInt(self, "Ir para imagem", f"Imagem (1–{len(self.frames)}):",
                                        self.index + 1, 1, len(self.frames))
            if ok:
                self.go_to(n - 1)
        elif hot == "zoom":
            self.menu_do_zoom().exec(e.globalPosition().toPoint())
        elif hot and hot.startswith("pan_"):
            self.state.pan = QPointF(0, 0)
            self.update()
        elif hot == "wl":
            self.show_preset_menu(e.globalPosition().toPoint())
        elif hot is None and e.button() == Qt.LeftButton:
            self.sig.maximize_requested.emit(self)

    def leaveEvent(self, _e) -> None:  # noqa: N802
        self._ultimo_hover = None                 # ao voltar (ou em outro quadro) começa do zero
        self._acc_tecla = 0.0
        if self._hover:
            self._hover = None
            self.update()

    def wheelEvent(self, e: QWheelEvent) -> None:  # noqa: N802
        d = e.angleDelta()
        steps = (d.y() or d.x()) / 120       # com Alt, alguns sistemas mandam a rodinha como horizontal
        if steps == 0:
            return
        if self._loupe is not None:          # lupa aberta: a roda muda o aumento
            self.loupe_zoom = float(np.clip(self.loupe_zoom + (0.5 if steps > 0 else -0.5), 1.5, 8.0))
            self.settings.set("viewer.loupe_zoom", self.loupe_zoom)
            self.update()
            return
        if self.render3d is not None:        # no 3D a roda aproxima a câmera
            self.render3d.wheel(-steps if self.settings.get("viewer.invert_wheel", False) else steps)
            return
        if self.settings.get("viewer.invert_wheel", False):
            steps = -steps
        mods = e.modifiers()
        mouse = self.settings.get("viewer.mouse", {})
        hot = self._hotspot_at(e.position())
        if mods & Qt.ControlModifier:
            action = mouse.get("ctrl_wheel", "zoom")
        elif mods & Qt.ShiftModifier:
            action = mouse.get("shift_wheel", "scroll5")
        elif hot == "zoom":
            action = "zoom"
        else:
            action = mouse.get("wheel", "scroll")
        if action == "zoom":
            self.state.zoom = float(np.clip(self.state.zoom * (1.1 ** steps), 0.05, 40))
            self.update()
            self.sig.view_changed.emit(self, "zoom")
        elif action == "scroll5":
            self.step(int(-steps * 5))
        elif self.em_mosaico():               # mosaico: a roda vira a página (o conjunto anda junto)
            r, c = self.mosaico
            self.step((-1 if steps > 0 else 1) * r * c)
        else:
            self.step(int(-steps) if abs(steps) >= 1 else (-1 if steps > 0 else 1))

    # ------------------------------------------------------------ teclado
    TECLAS_QT = {"shift": Qt.Key_Shift, "ctrl": Qt.Key_Control, "alt": Qt.Key_Alt}

    def keyReleaseEvent(self, e: QKeyEvent) -> None:  # noqa: N802
        if e.key() in self.TECLAS_QT.values() and self._cursor_por_tecla:
            self._cursor_por_tecla = False
            self._acc_tecla = 0.0
            self._ultimo_hover = None
            self.setCursor(Qt.ArrowCursor)     # soltou a tecla: o ponteiro volta ao que era
        super().keyReleaseEvent(e)

    def keyPressEvent(self, e: QKeyEvent) -> None:  # noqa: N802
        k = e.key()
        for ferramenta, tecla in self.teclas_emprestadas().items():
            if k == self.TECLAS_QT.get(tecla) and ferramenta in self.PONTEIRO_DA_TECLA \
                    and self._img is not None and self._draft is None and self.render3d is None:
                # o ponteiro muda na hora em que a tecla desce, antes de mexer o mouse
                self.setCursor(self.PONTEIRO_DA_TECLA[ferramenta])
                if not self._cursor_por_tecla:     # a tecla acabou de descer: rola a partir daqui
                    from PySide6.QtGui import QCursor
                    self._ultimo_hover = QPointF(self.mapFromGlobal(QCursor.pos()))
                self._cursor_por_tecla = True
                self._acc_tecla = 0.0
                return
        if self._curve_pts and k in (Qt.Key_Return, Qt.Key_Enter):
            self.finish_curve()
            return
        if self._curve_pts and k == Qt.Key_Escape:
            self._curve_pts = []
            self.update()
            return
        if self._curve_pts and k == Qt.Key_Backspace:
            self._curve_pts.pop()
            self.update()
            return
        # ← → saíram da navegação na 0.65: são o atalho das etapas do protocolo de mamografia,
        # e atalho de ação é consumido antes do evento de tecla do quadro — deixá-las aqui seria
        # função que não acontece. Quem rola cortes é ↑↓ (e PgUp/PgDn); a fase da dinâmica anda
        # pelo canto clicável "Fase" e pelas ações "Dinâmica: próxima/anterior fase", que nascem
        # sem tecla, para ele escolher.
        if k == Qt.Key_Up:
            self.step(-1)
        elif k == Qt.Key_Down:
            self.step(1)
        elif k == Qt.Key_PageUp:
            self.step(-10)
        elif k == Qt.Key_PageDown:
            self.step(10)
        elif k == Qt.Key_Home:
            self.go_to(0)
        elif k == Qt.Key_End:
            self.go_to(len(self.frames) - 1)
        elif k in (Qt.Key_Delete, Qt.Key_Backspace):
            if self.selected is not None:
                self.delete_annotation(self.selected)
            else:
                self.delete_frame_annotations()
        elif k == Qt.Key_Escape and (self._draft is not None or self.selected is not None):
            self.escape()
        elif k in (Qt.Key_Return, Qt.Key_Enter) and self._draft is not None:
            self.finish_draft()
        elif Qt.Key_1 <= k <= Qt.Key_9 and not e.modifiers():
            self.apply_preset(chr(k))
        elif k == Qt.Key_0 and not e.modifiers():
            self.state.window_set = False
            self._load_current()
            self.update()
        else:
            super().keyPressEvent(e)

    # ------------------------------------------------------------ menus
    def presets_da_janela(self) -> dict:
        """Presets da modalidade deste quadro (0.99.22); sem lista própria, os gerais."""
        from ipe.imaging import presets_janela as PJ
        return PJ.presets(self.settings, self.modalidade_atual())

    def apply_preset(self, key: str, geral: bool = False) -> None:
        """Tecla 1–9. `geral`: a lista geral (os protocolos de exibição gravam a tecla dela)."""
        presets = (self.settings.get("viewer.wl_presets", {}) or {}) if geral else self.presets_da_janela()
        if key in presets:
            _name, w, l = presets[key]
            self.set_window(float(w), float(l))

    # ---- Switch WL (0.99.22): as janelas gravadas no arquivo, uma a uma
    def janelas_do_arquivo(self) -> tuple:
        return tuple(getattr(self._img, "janelas", ()) or ()) if self._img is not None else ()

    def usar_janela_do_arquivo(self, i: int) -> None:
        js = self.janelas_do_arquivo()
        if not js:
            return
        i %= len(js)
        nome, w, l = js[i]
        self.set_window(float(w), float(l))
        self._janela_arquivo = (i, nome, float(w), float(l))

    def switch_wl(self) -> str:
        """Próxima janela do arquivo, em ciclo. Devolve o que mostrou (para a barra de status)."""
        js = self.janelas_do_arquivo()
        if not js:
            return ""
        atual = getattr(self, "_janela_arquivo", None)
        i = 0
        if atual is not None and self._na_janela_do_arquivo():
            i = atual[0] + 1
        elif len(js) > 1 and abs(self.state.width - js[0][1]) < 1e-3 and abs(self.state.level - js[0][2]) < 1e-3:
            i = 1                          # já está na primeira (a que abre): a tecla vai para a segunda
        self.usar_janela_do_arquivo(i)
        i, nome, _w, _l = self._janela_arquivo
        return f"Janela do arquivo {i + 1}/{len(js)}: {nome}"

    def _na_janela_do_arquivo(self) -> bool:
        a = getattr(self, "_janela_arquivo", None)
        return a is not None and abs(self.state.width - a[2]) < 1e-3 and abs(self.state.level - a[3]) < 1e-3

    def nome_da_janela(self) -> str:
        """Nome da janela do arquivo em uso (some quando ele arrasta a janela)."""
        return self._janela_arquivo[1] if self._na_janela_do_arquivo() else ""

    def espelhar_roi(self, ann):
        """ROI do outro lado, no espelho do plano sagital mediano (0.99.48, plano AW M14). A original
        passa a mostrar a razão lesão / contralateral; a barra de status diz onde ficou o eixo."""
        from ipe.imaging import clonar_roi as CR
        xm, como = CR.eixo_de_simetria(self)
        if xm is None:
            self.sig.status_message.emit(tr(f"Não espelhei: {tr(como)}."))
            return None
        cp, razao = CR.espelhar(self, ann, xm)
        if cp is None:
            self.sig.status_message.emit(tr(f"Não espelhei: {tr(razao)}."))
            return None
        if razao is not None:
            txt = f"ROI espelhada (eixo em x = {xm:.1f} mm, {tr(como)}): lesão / contralateral = {razao:.2f}."
        else:
            txt = f"ROI espelhada (eixo em x = {xm:.1f} mm, {tr(como)})."
        self.sig.status_message.emit(tr(txt))
        self.sig.frame_changed.emit(self)
        return cp

    def menu_do_zoom(self) -> QMenu:
        """Duplo clique no "Zoom N%" do canto (0.99.45): ajustar, 1:1, valores prontos ou digitar."""
        menu = QMenu(self)
        menu.addAction("Ajustar à janela").triggered.connect(self.fit)
        menu.addAction("1 pixel da imagem = 1 pixel da tela (1:1)").triggered.connect(self.zoom_actual_pixels)
        menu.addSeparator()
        for pct in (50, 150, 200, 300, 400):
            menu.addAction(f"{pct}%").triggered.connect(lambda _=False, f=pct / 100: self.aplicar_zoom("ajuste", f))
        menu.addSeparator()
        menu.addAction("Digitar o zoom…").triggered.connect(self.digitar_zoom)
        return menu

    def aplicar_zoom(self, modo: str, fator: float) -> None:
        """`modo` "ajuste": em relação a ajustar à janela (o número do canto); "pixel": pixels da
        imagem por pixel da tela. A imagem continua centrada onde estava."""
        if modo == "pixel":
            f = self.fit_scale()
            if f <= 0:
                return
            fator = fator / f
        self.quad_idx = -1
        self.anat_lock = self._anat_box_norm = None
        self.state.zoom = float(np.clip(fator, 0.05, 40))
        self.update()
        self.sig.view_changed.emit(self, "zoom")

    def digitar_zoom(self) -> None:
        from ipe.imaging import presets_janela as PJ
        txt, ok = QInputDialog.getText(self, "Zoom", "Zoom (ex.: 150, 150%, 2x, 1:1):",
                                       text=f"{self.state.zoom * 100:.0f}%")
        if not ok:
            return
        z = PJ.ler_zoom(txt)
        if z is None:
            QMessageBox.warning(self, "Zoom", "Digite uma porcentagem (5 a 4000), um fator (2x) ou 1:1.")
            return
        self.aplicar_zoom(*z)

    def digitar_janela(self) -> None:
        """Clicar no "W 400 L 40" e digitar (0.99.22, plano AW item 9)."""
        from ipe.imaging import presets_janela as PJ
        txt, ok = QInputDialog.getText(self, "Janela", "Largura e nível (ex.: 400 40):",
                                       text=f"{self.state.width:.0f} {self.state.level:.0f}")
        if not ok:
            return
        wl = PJ.ler_wl(txt)
        if wl is None:
            QMessageBox.warning(self, "Janela", "Digite dois números: a largura (maior que zero) e o nível.")
            return
        self.set_window(*wl)

    def guardar_janela_atual(self) -> bool:
        """Guarda a janela à vista como preset da modalidade do quadro (0.99.22, item 10)."""
        from ipe.imaging import presets_janela as PJ
        mod = self.modalidade_atual() or ""
        nome, ok = QInputDialog.getText(self, "Guardar a janela atual",
                                        f"Nome do preset ({mod or 'geral'}, W {self.state.width:.0f} "
                                        f"L {self.state.level:.0f}):", text=self.nome_da_janela())
        if not ok or not nome.strip():
            return False
        tecla = PJ.tecla_livre(self.settings, mod) if PJ.tem_lista_propria(self.settings, mod) or \
            (mod and mod != "CT") else None
        teclas = [str(k) for k in range(1, 10)]
        if tecla is None:
            atuais = self.presets_da_janela()
            itens = [f"{k}  {atuais[k][0]}" if k in atuais else f"{k}  (livre)" for k in teclas]
            esc, ok = QInputDialog.getItem(self, "Guardar a janela atual", "Em que tecla?", itens, 0, False)
            if not ok:
                return False
            tecla = esc.split()[0]
        PJ.guardar(self.settings, mod, tecla, nome.strip(), self.state.width, self.state.level)
        return True

    def show_preset_menu(self, global_pos) -> None:
        menu = QMenu(self)
        self._add_preset_actions(menu)
        menu.exec(global_pos)

    def _add_preset_actions(self, menu: QMenu) -> None:
        js = self.janelas_do_arquivo()
        if js:
            tit = QAction("Do arquivo (Switch WL)", menu)
            tit.setEnabled(False)
            menu.addAction(tit)
            for i, (nome, w, l) in enumerate(js):
                act = QAction(f"   {nome}  (W {w:g} / L {l:g})", menu)
                act.triggered.connect(lambda _=False, k=i: self.usar_janela_do_arquivo(k))
                menu.addAction(act)
            menu.addSeparator()
        for key, (name, w, l) in sorted(self.presets_da_janela().items()):
            if not name:
                continue
            act = QAction(f"{key}  {name}  (W {w} / L {l})", menu)
            act.triggered.connect(lambda _=False, kk=key: self.apply_preset(kk))
            menu.addAction(act)
        auto = QAction("0  Automático / do arquivo", menu)
        auto.triggered.connect(lambda: (setattr(self.state, "window_set", False),
                                        self._load_current(), self.update()))
        menu.addAction(auto)
        menu.addSeparator()
        dig = QAction("Digitar a janela…", menu)
        dig.triggered.connect(self.digitar_janela)
        menu.addAction(dig)
        cap = QAction("Guardar a janela atual como preset…", menu)
        cap.setToolTip("Vale para a modalidade deste quadro: RM, mamografia e PET podem ter presets próprios.")
        cap.triggered.connect(self.guardar_janela_atual)
        menu.addAction(cap)

    def abrir_perfil(self, ann):
        """Gráfico do valor ao longo da régua/polilinha (0.99.31)."""
        from ipe.ui.viewer.perfil import PerfilDialog
        d = PerfilDialog(self, ann, self.window())
        self._perfis = [x for x in getattr(self, "_perfis", []) if x is not None] + [d]
        d.show()
        return d

    def show_context_menu(self, global_pos, local_pos: QPointF | None = None) -> None:
        self.build_context_menu(local_pos).exec(global_pos)

    def build_context_menu(self, local_pos: QPointF | None = None) -> QMenu:
        menu = QMenu(self)
        if self.render3d is not None:
            self.render3d.add_menu_actions(self, menu)
        target = None
        if local_pos is not None and self._img is not None:
            target = self._annotation_at(self._img_pt(local_pos), self._img_tol())
        if target is not None:
            name = M.KINDS.get(target.kind, "medida")
            a_del = QAction(f"Apagar esta medida ({name})", menu)
            a_del.triggered.connect(lambda: self.delete_annotation(target))
            menu.addAction(a_del)
            if target.kind in ("text", "arrow"):
                a_txt = QAction("Editar texto…", menu)
                a_txt.triggered.connect(lambda: self.edit_text(target))
                menu.addAction(a_txt)
            if target.kind in RASCUNHAVEIS and target.frame_key[0] and not (target.meta or {}).get("lesion"):
                a_ras = QAction("Rascunho (não vai ao SR, ao laudo, à planilha nem ao PACS)", menu)
                a_ras.setCheckable(True)
                a_ras.setChecked(M.e_rascunho(target))
                a_ras.toggled.connect(lambda on: self.marcar_rascunho(target, on))
                menu.addAction(a_ras)
            if target.kind in ("line", "ellipse", "rect", "polygon", "tic", "seg") and target.frame_key[0] \
                    and not M.e_rascunho(target):
                lid = target.meta.get("lesion") if target.meta else None
                a_les = QAction("Ligar a uma lesão (acompanhamento)…" if lid is None
                                else "Trocar / desligar a lesão…", menu)
                a_les.triggered.connect(lambda: self.sig.lesion_requested.emit(self, target))
                menu.addAction(a_les)
            if target.kind in M.ROI_KINDS and target.frame_key[0]:
                if (target.meta or {}).get("referencia"):
                    a_ref = QAction("Deixar de ser a ROI de referência", menu)
                    a_ref.triggered.connect(lambda: self.marcar_referencia(None))
                else:
                    a_ref = QAction("Usar como ROI de referência (as outras mostram % dela)", menu)
                    a_ref.triggered.connect(lambda: self.marcar_referencia(target))
                menu.addAction(a_ref)
            if target.kind in M.ROI_KINDS and self.plane() is not None and target.frame_key == self.frame_key() \
                    and not (target.meta or {}).get("contralateral_de"):
                a_esp = QAction("Espelhar no outro lado (razão lesão / contralateral)", menu)
                a_esp.triggered.connect(lambda: self.espelhar_roi(target))
                menu.addAction(a_esp)
            if target.kind in M.ROI_KINDS and self.plane() is not None:
                a_cl = QAction("Clonar esta ROI nos outros quadros (mesma posição no paciente)", menu)
                a_cl.triggered.connect(lambda: self.sig.clone_roi_requested.emit(self, target))
                menu.addAction(a_cl)
            if target.kind in ("line", "polyline") and self._img is not None and not self._img.is_color:
                a_perf = QAction("Perfil de intensidade…", menu)          # 0.99.31 (onda A4)
                a_perf.triggered.connect(lambda: self.abrir_perfil(target))
                menu.addAction(a_perf)
            if target.kind == "tic":
                a_tic = QAction("Mostrar curva tempo-intensidade…", menu)
                a_tic.triggered.connect(lambda: self.sig.tic_requested.emit(self, target))
                menu.addAction(a_tic)
            menu.addSeparator()
        if self.annotations:
            nav = menu.addMenu("Medidas desta série")
            for i, text in self.annotation_summary()[:40]:
                act = nav.addAction(text)
                act.triggered.connect(lambda _=False, k=i: self.go_to(k))
        if self.frames and not self.frames[0].is_virtual and self.mpr_plane is None and self.render3d is None:
            tab = self.parentWidget()
            while tab is not None and not hasattr(tab, "apagar_imagem"):
                tab = tab.parentWidget()
            if tab is not None and len(self.frames) > 1:       # 0.99.31 (onda A7)
                a_apagar = QAction("Apagar esta imagem…", menu)
                a_apagar.triggered.connect(lambda: tab.apagar_imagem(self))
                from ipe.auth import session as _S
                a_apagar.setEnabled(_S.can("delete"))
                menu.addAction(a_apagar)
        if (self.mpr_plane is not None or self.render3d is not None) and (self.modality or "").upper() == "CT":
            tab = self.parentWidget()
            while tab is not None and not hasattr(tab, "alternar_mesa"):
                tab = tab.parentWidget()
            if tab is not None:                               # 0.99.31 (onda A5)
                a_mesa = QAction("Tirar a mesa da TC (MPR e 3D)", menu, checkable=True,
                                 checked=bool(self.settings.get("viewer.tirar_mesa", False))
                                 if self.settings is not None else False)
                a_mesa.toggled.connect(tab.alternar_mesa)
                menu.addAction(a_mesa)
        if self.mpr_plane is not None:
            n = len(self.frames)
            a_all = QAction(f"Salvar a reconstrução como série nova ({self.mpr_plane.name}, {n} imagens)", menu)
            a_all.triggered.connect(lambda: self.sig.reconstruction_save_requested.emit(self, False))
            menu.addAction(a_all)
            a_one = QAction("Salvar só esta imagem reconstruída como série nova", menu)
            a_one.triggered.connect(lambda: self.sig.reconstruction_save_requested.emit(self, True))
            menu.addAction(a_one)
            menu.addSeparator()
        if self.frames and self._img is not None:
            cp = QAction("Copiar a imagem (área de transferência)", menu)
            cp.setToolTip("Como está na tela, com as anotações do nível em uso, em boa resolução")
            cp.triggered.connect(lambda: self.sig.copy_requested.emit(self))
            menu.addAction(cp)
        from ipe.ui.viewer import anotacoes as AN
        am = menu.addMenu("Anotações")
        atual = AN.nivel_atual(self.settings) if self.settings is not None else "completa"
        for chave, nome in AN.NIVEIS:
            a = QAction(nome, am, checkable=True, checked=chave == atual)
            a.triggered.connect(lambda _c=False, k=chave: self.sig.anotacoes_requested.emit(k))
            am.addAction(a)
        if len(self.frames) > 1 and self.render3d is None:
            mm = menu.addMenu("Mosaico de cortes")
            for rc in (None, *self.MOSAICOS):
                a = QAction("Desligado" if rc is None else f"{rc[0]} × {rc[1]}", mm, checkable=True,
                            checked=self.mosaico == rc)
                a.triggered.connect(lambda _c=False, x=rc: self.set_mosaico(x))
                mm.addAction(a)
        wl = menu.addMenu("Janela (presets)")
        self._add_preset_actions(wl)
        if self._img is None or not self._img.is_color:
            cm = menu.addMenu("Cor (tabela de cores)")
            self.add_colormap_actions(cm, lembrar=True)
        self.add_orientation_actions(menu.addMenu("Girar / espelhar"))
        refs = QAction("Linhas de corte das outras séries", menu, checkable=True,
                       checked=bool(getattr(self, "_refs_on", True)))
        refs.setToolTip("As linhas coloridas que mostram onde passam os cortes dos outros quadros")
        refs.toggled.connect(self.sig.reflines_toggled.emit)
        menu.addAction(refs)
        menu.addSeparator()
        hist = QAction("Histograma da imagem (ou da ROI)…", menu)
        hist.triggered.connect(lambda: self.sig.histogram_requested.emit(self))
        hist.setEnabled(self._img is not None and not self._img.is_color)
        menu.addAction(hist)
        for label, fn in (("Inverter", lambda: self.set_invert()),
                          ("Ajustar à janela", self.fit),
                          ("Restaurar visualização", self.reset_view),
                          ("Cine liga/desliga", self.toggle_cine),
                          ("Apagar medidas deste corte", self.delete_frame_annotations)):
            act = QAction(label, menu)
            act.triggered.connect(fn)
            menu.addAction(act)
        if (self.mg_spec is not None or (self.modality or "").upper() == "MG") and self._img is not None \
                and not self._img.is_color and local_pos is not None:
            pt = QPointF(local_pos)
            a_imp = QAction("Achar o implante a partir daqui", menu)
            a_imp.setToolTip("Use quando o programa não achar a prótese sozinho: clique dentro do silicone.")
            a_imp.triggered.connect(lambda: self.blank_implant_at(pt))
            menu.addAction(a_imp)
            if self.implant_mask:
                a_off = QAction("Mostrar o implante como veio do aparelho", menu)
                a_off.triggered.connect(lambda: (self.set_implant_mask(False),
                                                 self.sig.implant_changed.emit(self)))
                menu.addAction(a_off)
        f_seg = self.current_frame()
        if (self.modality or "").upper() in ("CT", "MR") and f_seg is not None and not f_seg.is_virtual \
                and f_seg.series_uid and len(self.frames) >= 20:
            a_org = QAction("Segmentar órgãos abdominais desta série (TotalSegmentator)…", menu)
            a_org.setToolTip("Grava as máscaras (SEG) e a tabela de volumes (OT) no exame, só neste computador.")
            a_org.triggered.connect(lambda: self.sig.orgaos_requested.emit(self))
            menu.addAction(a_org)
        if (self.modality or "").upper() in ("CT", "MR") and f_seg is not None and not f_seg.is_virtual \
                and f_seg.series_uid and len(self.frames) >= 8:
            a_col = QAction("Identificar vértebras e discos desta série (TotalSegmentator)…", menu)
            a_col.setToolTip("Dá nome a cada vértebra e disco (C2-C3 … L5-S1); os nomes aparecem em qualquer "
                             "série e plano do exame.")
            a_col.triggered.connect(lambda: self.sig.coluna_requested.emit(self))
            menu.addAction(a_col)
        if any(getattr(o, "source", "") == "Coluna" and o.study_uid in ("", self.study_uid)
               for o in (getattr(self, "overlays", None) or [])):
            ponto = None
            if local_pos is not None and self._img is not None:
                try:
                    u, v = self._img_pt(local_pos)
                    ponto = self.pixel_to_patient(u, v)
                except Exception:  # noqa: BLE001
                    ponto = None
            rm = menu.addMenu("Numeração da coluna")
            rm.setToolTip("Vértebra de transição, contagem deslocada: renumerar ou dizer qual vértebra é qual.")
            a_aj = QAction("Ajustar a numeração e a vértebra de transição…", rm)
            a_aj.triggered.connect(lambda _=False, p=ponto: self.sig.numeracao_requested.emit(self, p))
            rm.addAction(a_aj)
            rm.addSeparator()
            rm.addAction("Um nível para baixo (L4 vira L5)", lambda: self.sig.renumerar_requested.emit(self, 1))
            rm.addAction("Um nível para cima (L5 vira L4)", lambda: self.sig.renumerar_requested.emit(self, -1))
        menu.addSeparator()
        self.acoes_de_ferramenta(menu.addMenu("Mouse (botão esquerdo)"), medidas_em_submenu=False)
        self.acoes_de_ferramenta(menu.addMenu("Medidas"), so_medidas=True)
        f_cur = self.current_frame()
        if f_cur is not None and not f_cur.is_virtual:
            is_key = (f_cur.sop_uid, f_cur.frame_index) in self.key_frames
            k_act = QAction("Desmarcar imagem-chave" if is_key else "Marcar imagem-chave ★", menu)
            k_act.triggered.connect(lambda: self.sig.key_toggle_requested.emit(self))
            menu.addAction(k_act)
        menu.addSeparator()
        grp = QAction("Grupo de sincronização (trocar)", menu)
        grp.triggered.connect(lambda: self.sig.sync_group_requested.emit(self))
        menu.addAction(grp)
        if self.is_4d():
            cm = menu.addMenu(f"Cardíaco 4D ({self.cardiac.summary()})")
            cm.addAction("Cine das fases (ciclo parado neste corte)",
                         lambda: self.toggle_cine(phases=True))
            cm.addAction("Fase seguinte", lambda: self.set_cardiac_phase(self.cardiac_where()[1] + 1))
            cm.addAction("Fase anterior", lambda: self.set_cardiac_phase(self.cardiac_where()[1] - 1))
            cm.addSeparator()
            for p in range(self.cardiac.n_phases):
                a = QAction(f"Fase {p + 1}", cm, checkable=True, checked=self.cardiac_where()[1] == p)
                a.triggered.connect(lambda _c=False, q=p: self.set_cardiac_phase(q))
                cm.addAction(a)
        if len(self.frames) > 1:
            dm = menu.addMenu("Subtração digital (DSA)")
            a = QAction("Ligada", dm, checkable=True, checked=bool(self.dsa.get("on")))
            a.triggered.connect(lambda on: self.set_dsa(on=on))
            dm.addAction(a)
            dm.addAction("Usar este quadro como máscara",
                         lambda: self.set_dsa(on=True, mask=self.index, avg=1))
            dm.addAction("Máscara = média dos 3 primeiros quadros",
                         lambda: self.set_dsa(on=True, mask=0, avg=3))
            dm.addSeparator()
            from ipe.imaging.dsa import MODES as _DSA_MODES
            for chave, rotulo in _DSA_MODES.items():
                a = QAction(rotulo, dm, checkable=True, checked=self.dsa.get("mode") == chave)
                a.triggered.connect(lambda _c=False, k=chave: self.set_dsa(mode=k))
                dm.addAction(a)
            a = QAction("Inverter (vasos escuros)", dm, checkable=True,
                        checked=bool(self.dsa.get("invert")))
            a.triggered.connect(lambda on: self.set_dsa(invert=on))
            dm.addAction(a)
            pm = dm.addMenu("Paisagem (anatomia na subtração)")
            atual = float(self.dsa.get("paisagem", 0.0) or 0.0)
            for f in self.PAISAGENS:
                a = QAction("Sem anatomia (subtração pura)" if f == 0 else f"{f * 100:.0f}% da anatomia", pm,
                            checkable=True, checked=abs(f - atual) < 1e-6)
                a.triggered.connect(lambda _c=False, ff=f: self.set_dsa(on=True, paisagem=ff))
                pm.addAction(a)
            dm.addSeparator()
            dm.addAction("Ajustar o deslocamento da máscara…", self.open_dsa_shift)
        from ipe.imaging import filters as _filters
        fmenu = menu.addMenu("Filtro da imagem")
        for nome in _filters.ORDER:
            a = QAction(_filters.label(nome), fmenu)
            a.setCheckable(True)
            a.setChecked(self.state.filter == nome)
            a.triggered.connect(lambda _c=False, n=nome: self.set_filter(n))
            fmenu.addAction(a)
        tags = QAction("Informações DICOM (tags)…", menu)
        tags.triggered.connect(self.show_tags)
        tags.setEnabled(bool(self.frames) and not self.anonymize)
        menu.addAction(tags)
        return menu

    def open_dsa_shift(self) -> None:
        """Janelinha com as setas para empurrar a máscara e tirar o fantasma do movimento."""
        from ipe.ui.viewer.dsa_shift import DsaShiftDialog
        DsaShiftDialog(self, self).show()

    def show_tags(self) -> None:
        if not self.frames:
            return
        from ipe.ui.dialogs import TagDialog
        TagDialog(self.frames[self.index].path, self, files_for=self._files_for_scope,
                  on_fixed=self._tags_fixed).exec()

    def _files_for_scope(self, escopo: str) -> list:
        """Arquivos que a correção de tags vai copiar: esta imagem, a série ou o exame inteiro."""
        from pathlib import Path as _Path
        if escopo == "image" or not self.series_uid:
            return [_Path(self.frames[self.index].path)]
        repo = getattr(self.window(), "repo", None)
        if repo is None:
            return [_Path(f.path) for f in self.frames]
        if escopo == "series":
            return [_Path(i["path"]) for i in repo.instances_for_series(self.series_uid)]
        arquivos = []
        for se in repo.series_for_study(self.study_uid or ""):
            arquivos += [_Path(i["path"]) for i in repo.instances_for_series(se.series_uid)]
        return arquivos or [_Path(f.path) for f in self.frames]

    def _tags_fixed(self, arquivos) -> None:
        janela = self.window()
        importar = getattr(janela, "import_fixed_tags", None)
        if importar is not None:
            importar(arquivos)

    # ------------------------------------------------------------ drag & drop
    def join_rect(self) -> QRectF:
        """Canto inferior direito: soltar uma série aqui junta como fase."""
        return QRectF(self.width() * 0.6, self.height() * 0.6, self.width() * 0.4 - 6, self.height() * 0.4 - 6)

    def _zone_for(self, pos) -> str:
        return "join" if self.frames and self.join_rect().contains(QPointF(pos)) else "replace"

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasFormat("application/x-dicomviewer-series"):
            self._drag_zone = self._zone_for(e.position())
            e.acceptProposedAction()
            self.update()

    def dragMoveEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasFormat("application/x-dicomviewer-series"):
            z = self._zone_for(e.position())
            if z != self._drag_zone:
                self._drag_zone = z
                self.update()
            e.acceptProposedAction()

    def dragLeaveEvent(self, _e) -> None:  # noqa: N802
        self._drag_zone = None
        self.update()

    def dropEvent(self, e) -> None:  # noqa: N802
        uid = bytes(e.mimeData().data("application/x-dicomviewer-series")).decode()
        zone = self._zone_for(e.position())
        self._drag_zone = None
        self.sig.activated.emit(self)
        e.acceptProposedAction()
        if zone == "join" and not uid.startswith(("key:", "group:")):
            self.sig.join_requested.emit(self, uid)
        else:
            self.parent_viewer_load(uid)
        self.update()

    def _draw_drop_zones(self, p: QPainter) -> None:
        if self._drag_zone is None or not self.frames:
            return
        j = self.join_rect()
        full = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        f = QFont()
        f.setPointSize(12)
        f.setBold(True)
        p.setFont(f)
        on_join = self._drag_zone == "join"
        p.fillRect(full, QColor(40, 90, 150, 40 if on_join else 90))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(full.x(), full.y(), full.width(), full.height() * 0.6), Qt.AlignCenter,
                   "Soltar aqui: trocar a série")
        p.fillRect(j, QColor(255, 180, 0, 170 if on_join else 70))
        pen = QPen(QColor(255, 200, 0))
        pen.setWidth(2)
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.drawRect(j)
        p.setPen(QColor(0, 0, 0) if on_join else QColor(255, 230, 150))
        p.drawText(j, Qt.AlignCenter, "+ Juntar como fase\n(série dinâmica)")

    def parent_viewer_load(self, uid: str) -> None:
        """Pede ao ViewerTab (pai) para carregar a série neste viewport."""
        w = self.parentWidget()
        while w is not None and not hasattr(w, "load_series_into"):
            w = w.parentWidget()
        if w is not None:
            w.load_series_into(self, uid)
