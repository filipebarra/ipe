"""Viewport 2D: exibe uma série, com ferramentas de mouse, overlay clicável e medidas.

Desenho feito com QPainter (rápido e simples para 2D). MPR e 3D virão com VTK
em outra classe de viewport, reaproveitando a mesma lógica de mouse e overlay.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QRunnable, QThreadPool, Qt, QTimer, Signal, QObject
from PySide6.QtGui import QTransform
from PySide6.QtGui import (
    QAction, QColor, QFont, QFontMetrics, QImage, QPainter, QPen,
)
from PySide6.QtWidgets import QMenu, QWidget

from ipe.core.i18n import tr
from ipe.imaging.measure import Annotation
from ipe.imaging.series import Frame, FrameCache, FrameImage  # noqa: F401
from ipe.imaging import colormaps as CM
from ipe.imaging.windowing import auto_window

log = logging.getLogger(__name__)

from ipe.ui.viewer.annotate import (  # noqa: E402,F401
    ANNOT_TOOLS, CLICK_TOOLS, FERRAMENTAS_DE_DESENHO, MEASURE_COLOR, RASCUNHAVEIS, SELECTED_COLOR, TOOLS, AnnotationMixin,
)


# as áreas clicáveis moram com o mouse (0.100.42); outros módulos ainda as importam daqui
from ipe.ui.viewer.viewport_eventos import CBAR, HOTSPOTS_DOS_DOIS_BOTOES, TOMO_DIAL, VpEventosMixin  # noqa: E402,F401
from ipe.ui.viewer.viewport_desenho import VpDesenhoMixin  # noqa: E402
from ipe.ui.viewer.viewport_mama import VpMamaMixin  # noqa: E402
from ipe.ui.viewer.viewport_menus import VpMenusMixin  # noqa: E402


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
    medida_criada = Signal(object, object)
    nodulo_requested = Signal(object, float, float)      # 0.99.62: nódulo pulmonar por clique (u, v da imagem)
    fusion_requested = Signal(object, str)                # 0.99.64: série solta no canto de fundir      # 0.99.59: medida nova (régua/ROI) — o seguimento liga sozinho
    clone_roi_requested = Signal(object, object)  # viewport, anotação: clonar a ROI nos outros quadros
    histogram_requested = Signal(object)        # viewport: mostrar o histograma
    anotacoes_requested = Signal(str)           # nível de anotação escolhido no botão direito (0.99.9)
    copy_requested = Signal(object)             # "Copiar imagem" no botão direito (0.99.9)
    segment_requested = Signal(object, float, float)   # viewport, ponto clicado (px da imagem)
    caixa_ia_requested = Signal(object, float, float, float, float)   # 0.99.83: caixa do MedSAM2 (px da imagem)
    pincel = Signal(object, float, float, str)  # viewport, ponto (px da imagem), "ini" | "meio" | "fim" (0.99.40)
    annotation_picked = Signal(object, object)  # viewport, medida escolhida (ou None)
    reflines_toggled = Signal(bool)             # mostrar/ocultar as linhas de corte das outras séries
    phase_changed = Signal(object)              # o quadro trocou de fase da dinâmica
    status_message = Signal(str)                # recado curto para a barra de estado
    enquadre_pendente = Signal(object)          # o quadro mudou de tamanho e o enquadramento da mama
                                                # precisa ser refeito (o zoom depende do tamanho)


class Viewport(VpDesenhoMixin, VpEventosMixin, VpMenusMixin, VpMamaMixin, AnnotationMixin, QWidget):
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
        self.baixando_txt: str = ""        # 0.100.0: "⬇ 34/120" enquanto a série chega do servidor central
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
        self.inverter_mama = False             # 0.99.61 (PV 17): inverte só a mama; o fundo continua preto
        self.mg_dy = 0.0                       # 0.99.61 (PV 16): deslocamento vertical do alinhamento pelo mamilo
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
        self.inverter_mama = False
        self.mg_dy = 0.0
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
        self.sul_razao = None
        self.glic = None
        mod = (self._img.header.get("Modality", "") if self._img is not None else "") or self.modality
        if frames and mod == "PT":
            from ipe.imaging.pet_onco import fatores_do_arquivo
            fs = fatores_do_arquivo(frames[0].path)
            self.suv_factor, self.sul_razao = fs["suv"], fs["sul_razao"]
            self.atualizar_glicemia()
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

    #: as cores mais usadas de cada modalidade (0.99.78); as outras ficam em "Mais cores"
    CORES_PRINCIPAIS = {
        "CT": ("inverse", "bone", "rainbow", "jet", "spectrum"),
        "MR": ("inverse", "hot", "rainbow", "ser", "cinetico"),
        "PT": ("hot", "pet", "gold", "hotmetal", "inverse"),
        "NM": ("hot", "thallium", "puh_thalium", "gold", "inverse"),
        "MG": ("inverse", "hot", "rainbow"),
    }
    CORES_PADRAO = ("inverse", "hot", "rainbow", "jet", "spectrum")

    def cores_principais(self) -> tuple:
        mod = (self.modalidade_atual() or self.modality or "").upper()
        base = self.CORES_PRINCIPAIS.get(mod, self.CORES_PADRAO)
        if self.state.cmap and self.state.cmap not in base:
            base = (*base, self.state.cmap)
        return tuple(k for k in base if k in CM.COLORMAPS)

    def add_colormap_actions(self, menu: QMenu, apply_fn=None, lembrar: bool = False,
                             principais: bool = False) -> None:
        """Itens de cor num menu (marcado = a do quadro). `apply_fn(key)` substitui set_colormap.

        `principais`: só as mais usadas da modalidade; as outras num submenu "Mais cores" (0.99.78)."""
        fn = apply_fn or ((lambda k: self.set_colormap(k, lembrar=True)) if lembrar else self.set_colormap)
        todas = [(k, v[0]) for k, v in CM.COLORMAPS.items()]
        mais = []
        if principais:
            topo = self.cores_principais()
            mais = [(k, n) for k, n in todas if k not in topo]
            todas = [(k, CM.COLORMAPS[k][0]) for k in topo]

        def item(alvo, key, label):
            act = QAction(label, alvo, checkable=True, checked=(key == self.state.cmap))
            if key:
                act.setIcon(colormap_icon(key))
            act.triggered.connect(lambda _=False, k=key: fn(k))
            alvo.addAction(act)
        item(menu, "", "Cinza (normal)")
        menu.addSeparator()
        for key, label in todas:
            item(menu, key, label)
        if mais:
            sub = menu.addMenu("Mais cores")
            for key, label in mais:
                item(sub, key, label)
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

    # ------------------------------------------------------------ drag & drop
    def join_rect(self) -> QRectF:
        """Canto inferior direito: soltar uma série aqui junta como fase."""
        return QRectF(self.width() * 0.6, self.height() * 0.6, self.width() * 0.4 - 6, self.height() * 0.4 - 6)

    def fuse_rect(self) -> QRectF:
        """Canto inferior esquerdo (0.99.64): soltar uma série aqui funde por cima, em cores."""
        return QRectF(6, self.height() * 0.6, self.width() * 0.4 - 6, self.height() * 0.4 - 6)

    def _zone_for(self, pos) -> str:
        if self.frames and self.join_rect().contains(QPointF(pos)):
            return "join"
        if self.frames and self.fuse_rect().contains(QPointF(pos)):
            return "fuse"
        return "replace"

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
        elif zone == "fuse":
            self.sig.fusion_requested.emit(self, uid)
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
        fz = self.fuse_rect()                          # 0.99.64: fundir por cima
        on_fuse = self._drag_zone == "fuse"
        p.fillRect(fz, QColor(170, 60, 200, 170 if on_fuse else 70))
        pen2 = QPen(QColor(210, 140, 255))
        pen2.setWidth(2)
        pen2.setStyle(Qt.DashLine)
        p.setPen(pen2)
        p.drawRect(fz)
        p.setPen(QColor(0, 0, 0) if on_fuse else QColor(235, 210, 255))
        p.drawText(fz, Qt.AlignCenter, "Fundir por cima\n(cores e transparência)")

    def parent_viewer_load(self, uid: str) -> None:
        """Pede ao ViewerTab (pai) para carregar a série neste viewport."""
        w = self.parentWidget()
        while w is not None and not hasattr(w, "load_series_into"):
            w = w.parentWidget()
        if w is not None:
            w.load_series_into(self, uid)
