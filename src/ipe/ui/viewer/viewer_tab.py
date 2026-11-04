"""Aba do viewer: tira de séries + grade de viewports + barra de ferramentas.

Aqui ficam também:
- a sincronização entre quadros (automática no mesmo referencial espacial e
  manual com deslocamento, para comparar com exames anteriores);
- as linhas de referência e o cursor 3D;
- o modo MPR (três planos ortogonais com slab);
- as imagens-chave.
"""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import QEvent, QMimeData, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QBrush, QColor, QDrag, QFont, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox,
    QApplication, QComboBox, QGridLayout, QSplitter, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMenu, QMessageBox, QProgressDialog, QTabWidget, QToolBar, QToolButton, QVBoxLayout, QWidget,
)

from ipe.core.sysinfo import auto_volume_mb
from ipe.db.repository import Repository, SeriesRow
from ipe.imaging.measure import Annotation
from ipe.imaging.series import Frame, FrameCache, _vec, build_frames
from ipe.imaging.curved import CurvedPlane
from ipe.imaging.volume import SLAB_MODES, MPRPlane, ObliquePlane, VolumeError, build_volume
from ipe.ui.viewer.actions import shortcut_for
from ipe.ui.icons import icon, with_badge
from ipe.ui.monitors import screen_with_role
from ipe.ui.viewer.sync import GROUP_NAMES, MODALIDADE_TXT, SyncHub
from ipe.ui.viewer.viewport import TOOLS, Viewport
from ipe.ui.viewer.dynamic import DynamicDialog, DynamicSession
from ipe.ui.viewer import nm_view as NMV
from ipe.ui.viewer.onco import OncoMixin

log = logging.getLogger(__name__)

SERIES_MIME = "application/x-dicomviewer-series"
LAYOUTS = [(1, 1), (1, 2), (2, 1), (2, 2), (1, 3), (2, 3), (3, 3), (1, 4), (2, 4), (3, 4), (4, 4)]
SLAB_CHOICES = [0, 2, 5, 10, 20, 40]


def fmt_date(d: str) -> str:
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 and d.isdigit() else d


class SeriesStrip(QListWidget):
    """Miniaturas das séries; clique carrega no viewport ativo, arrastar leva a outro."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setFlow(QListWidget.TopToBottom)
        self.setWrapping(False)
        self.setIconSize(QSize(80, 80))
        self.setFixedWidth(122)
        self.setSpacing(3)
        self.setMovement(QListWidget.Static)
        self.setDragEnabled(True)
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.setWordWrap(True)
        self.setStyleSheet("QListWidget{background:#151515;color:#ddd;border:none}"
                           "QListWidget::item:selected{background:#35506e}")

    def startDrag(self, _actions) -> None:  # noqa: N802
        item = self.currentItem()
        if item is None or not item.data(Qt.UserRole):
            return
        mime = QMimeData()
        mime.setData(SERIES_MIME, item.data(Qt.UserRole).encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        if not item.icon().isNull():
            drag.setPixmap(item.icon().pixmap(64, 64))
        drag.exec(Qt.CopyAction)


def match_series(ref: SeriesRow | None, candidates: list[SeriesRow]) -> SeriesRow | None:
    """Série equivalente em outro estudo: mesma modalidade e descrição; senão mesma modalidade."""
    match = None
    for s in candidates:
        if not s.num_images:
            continue
        if ref and s.modality == ref.modality and s.description.lower() == ref.description.lower():
            return s
        if match is None and (ref is None or s.modality == ref.modality):
            match = s
    return match


class RepoAnnotationStore:
    """Liga as medidas dos viewports ao banco (tabela annotation)."""

    def __init__(self, repo: Repository):
        self.repo = repo

    def load(self, frames: list[Frame]) -> list[Annotation]:
        keys = {(f.sop_uid, f.frame_index) for f in frames}
        series = sorted({f.series_uid for f in frames if f.series_uid})
        return [a for a in (Annotation.from_record(r) for r in self.repo.annotations_for_series(series))
                if a.frame_key in keys]

    def save(self, ann: Annotation) -> None:
        ann.db_id = self.repo.save_annotation(
            db_id=ann.db_id, study_uid=ann.study_uid, series_uid=ann.series_uid,
            sop_uid=ann.frame_key[0], frame_index=ann.frame_key[1], kind=ann.kind,
            data=ann.data_json())

    def delete(self, ann: Annotation) -> None:
        if ann.db_id is not None:
            self.repo.delete_annotation(ann.db_id)
            ann.db_id = None


MEASURE_TOOLS = ("pick", "measure", "polyline", "angle", "cobb", "height", "ellipse", "rect", "polygon",
                 "probe", "ruler3d", "tic", "grow", "pincel", "ctr", "spine", "calibration", "text", "arrow", "pencil")
VOLUME = {"CT", "MR", "PT", "NM"}     # modalidades que empilham cortes: 3D, MPR e fusão
TOOL_ICONS = {"measure": "measure", "ruler3d": "measure", "oblique": "mpr", "curve": "mpr", "rotplane": "mpr",
              "quadzoom": "quad", "loupe": "loupe",
              "grow": "segment", "pick": "pick", "pincel": "pencil"}
TOOL_SHORT = {"film": "Filme", "wl": "Janela", "zoom": "Zoom", "pan": "Pan", "scroll": "Rolar", "measure": "Régua",
              "polyline": "Polilinha", "angle": "Ângulo", "cobb": "Cobb", "ellipse": "Elipse",
              "rect": "Retângulo", "polygon": "Polígono", "probe": "Intensidade", "ruler3d": "Régua 3D", "height": "Altura",
              "ctr": "ICT", "spine": "Coluna", "tic": "Curva", "calibration": "Calibrar",
              "arrow": "Seta", "text": "Texto", "pencil": "Lápis", "cross": "Cursor 3D",
              "oblique": "Oblíquo", "curve": "Curvo", "quadzoom": "Quadrante", "loupe": "Lupa",
              "grow": "Segmentar", "pick": "Selecionar", "pincel": "Pincel"}


NON_IMAGE = {"SR", "KO", "PR", "REG", "SEG", "RTSTRUCT", "RTPLAN", "DOC"}


def _image_series(rows: list) -> list:
    """Séries que o visualizador mostra.

    Fora: relatórios estruturados, estados de apresentação e o **filme da estação AW**
    ("AW electronic film" e "AW electronic pages"), que é impressão e vive na aba Impressões.
    """
    from ipe.printing.aw_film import is_print_series
    return [s for s in rows if (s.modality or "").upper() not in NON_IMAGE
            and not is_print_series(getattr(s, "description", ""))]


class ViewerTab(OncoMixin, QWidget):
    detach_requested = Signal(object)      # pede à janela principal para mover a aba de monitor
    status_message = Signal(str)
    perfil_mudou = Signal(str)            # perfil de ocultação escolhido (0.99.42): as outras abas e o banco
    implante_salvo = Signal(int)          # cópias sem silicone gravadas pelo botão Implante (0.97.1)
    open_prior_requested = Signal(object, str)   # abrir anterior no monitor de comparação
    film_requested = Signal(dict)                # pedido ao compositor de filmes (a janela principal liga)
    preferences_requested = Signal(str)          # abrir as preferências nesta aba (0.99.9)
    anotacoes_mudaram = Signal(str)              # o nível de anotação mudou: as outras janelas acompanham

    def __init__(self, repo: Repository, cache: FrameCache, settings, study_uid: str,
                 parent=None, hub: SyncHub | None = None, layout: tuple[int, int] | None = None,
                 series_filter: list[str] | None = None, plano: dict | None = None,
                 mg_monitor: int | None = None, mg_telas: int = 1, monitor_idx: int = 0):
        super().__init__(parent)
        self.repo, self.cache, self.settings = repo, cache, settings
        self.study_uid = study_uid
        self.study_info = repo.study_info(study_uid) or {}
        self.study_infos: dict[str, dict] = {study_uid: self.study_info}
        from ipe.importer.thumbnails import miniaturas_que_faltam
        miniaturas_que_faltam(repo, study_uid)
        self.study_order: list[str] = [study_uid]
        self.series: list[SeriesRow] = _image_series(repo.series_for_study(study_uid))
        # séries escolhidas ao abrir (None = todas); a tira pode mostrar só elas
        self.series_filter: list[str] | None = list(series_filter) if series_filter else None
        self.show_all_series = self.series_filter is None
        # plano deste monitor, quando o exame foi repartido entre telas: {"layout", "cells"}.
        # A tira continua com o exame inteiro — restringir seria tirar do médico a chance de
        # trocar o que está num quadro.
        self.plano_do_monitor: dict | None = dict(plano) if plano else None
        self.exib = None                  # protocolo de exibição com etapas em uso (ui.viewer.etapas)
        # Qual monitor do conjunto esta aba é, e quantas telas o conjunto tem. A etapa de
        # mamografia é **a mesma** em todas; o que muda é o pedaço dela que cabe a cada tela, e
        # passar de etapa num monitor passa em todos.
        self.mg_monitor: int | None = mg_monitor
        # qual tela do conjunto esta aba é (0 = a primeira), mesmo fora da mamografia
        self.monitor_idx: int = int(monitor_idx or 0)
        self.mg_telas: int = max(1, int(mg_telas or 1))
        self.monitor_group: list = []
        self.groups: dict[int, dict] = {g["id"]: g for g in repo.series_groups(study_uid)}
        self._nao_separar: set[str] = set()      # séries que ele mandou juntar de volta nesta sessão
        self.key_set: set[tuple[str, int]] = repo.key_image_set(study_uid)
        self.ann_store = RepoAnnotationStore(repo)
        self.viewports: list[Viewport] = []
        self.active: Viewport | None = None
        self.left_tool = settings.get("viewer.mouse.left", "wl")
        if self.left_tool not in TOOLS:
            self.left_tool = "wl"
        self.anonymize = False
        import time as _t
        self._aberta_em = _t.monotonic()        # para o "CAD revelado depois de N min" (0.99.43)
        self.case_label = ""            # modo reunião
        self._maximized: Viewport | None = None
        self._layout = tuple(layout or settings.get("viewer.default_layout", [1, 1]))

        # sincronização (compartilhada entre todas as janelas)
        self.hub = hub if hub is not None else SyncHub(repo)
        self.compare_handler_connected = False   # a janela principal liga open_prior_requested
        self.net = None                          # NetworkService (a janela principal preenche)
        self.hub.register(self)

        # MPR
        self.mpr_active = False
        self.dyn: DynamicSession | None = None
        self.mg_session = None
        self._dyn_saved: tuple | None = None
        self._mpr_saved: tuple | None = None
        self._volumes: dict[str, object] = {}
        self.overlay_objects: list = []          # CAD/IA, SEG, RTSTRUCT, GSPS e segmentações (imaging.overlays)
        self.lesion_panel = None
        self.measures_panel = None

        self.toolbar = self._build_toolbar()
        # as regras de dinâmico valem **antes** de montar a tira: o que foi juntado ou separado
        # já aparece pronto, e o médico vê o que aconteceu na barra de estado
        try:
            self._regras_feitas = self.aplicar_regras_dinamicas()
        except Exception:  # noqa: BLE001
            log.exception("regras de dinâmico")
            self._regras_feitas = []
        self.strip = SeriesStrip()
        self._fill_strip()
        self.strip.itemClicked.connect(self._strip_clicked)
        self.strip.itemDoubleClicked.connect(self._strip_double_clicked)
        self.strip.setContextMenuPolicy(Qt.CustomContextMenu)
        self.strip.customContextMenuRequested.connect(self._strip_menu)

        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(2)
        self.grid_host.setStyleSheet("background:#333")
        # Ctrl+C mora nos quadros (e na tira), não na aba inteira: o compositor de filmes, que pode
        # abrir ao lado dentro desta aba, tem o seu próprio Ctrl+C — duas teclas iguais valendo no
        # mesmo lugar fazem o Qt não disparar nenhuma das duas.
        self.removeAction(self.copy_action)
        self.copy_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        self.grid_host.addAction(self.copy_action)
        self.strip.addAction(self.copy_action)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        # coluna da tira: em cima, a escolha dos exames do paciente (este, um anterior ou todos),
        # como o "All Studies" do Weasis; só aparece quando o paciente tem outro exame no banco
        self.estudos_na_tira: set[str] | None = None     # None = todos os que estão na aba
        self._outros_exames: list = []
        self.filtro_exames = QComboBox()
        self.filtro_exames.setFixedWidth(122)
        self.filtro_exames.setToolTip("Exames do paciente na tira: este, um anterior ou todos")
        self.filtro_exames.setStyleSheet("QComboBox{background:#26272b;color:#ddd;border:none;padding:3px}")
        self.filtro_exames.activated.connect(self._filtro_de_exames_escolhido)
        self.filtro_exames.hide()
        self.strip_col = QWidget()
        col = QVBoxLayout(self.strip_col)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self.filtro_exames)
        col.addWidget(self.strip, 1)
        body.addWidget(self.strip_col)
        self._ajustar_tira()
        QTimer.singleShot(0, self._encher_filtro_de_exames)
        # quadros e, ao lado, o painel do filme (divisor ajustável; duplo clique no filme expande)
        self.view_split = QSplitter(Qt.Horizontal)
        self.view_split.setChildrenCollapsible(False)
        self.view_split.addWidget(self.grid_host)
        self.film_holder = QWidget()
        fl = QVBoxLayout(self.film_holder)
        fl.setContentsMargins(2, 0, 0, 0)
        self.film_holder.hide()
        self.view_split.addWidget(self.film_holder)
        self.view_split.setStretchFactor(0, 3)
        self.view_split.setStretchFactor(1, 2)
        self.film_expanded = False
        body.addWidget(self.view_split, 1)
        self.priors_panel = None
        self._body = body
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.toolbar)
        root.addWidget(self.mpr_bar)
        root.addWidget(self.render3d_bar)
        root.addWidget(self.fusion_bar)
        root.addWidget(self.mg_bar)
        root.addWidget(self.etapas_bar)
        root.addLayout(body, 1)
        self._root_layout = root

        self._initial_hanging()
        if self._regras_feitas:
            feito = "; ".join(self._regras_feitas)
            QTimer.singleShot(0, lambda: self.status_message.emit(
                f"Regras de dinâmico (Preferências ▸ Dinâmicos): {feito}"))
        repo.mark_opened(study_uid)
        QTimer.singleShot(0, self.load_overlay_objects)

    # ================================================================ toolbar
    def _act(self, action_id: str, text: str, slot, checkable: bool = False,
             checked: bool = False) -> QAction:
        a = QAction(text, self, checkable=checkable)
        if checkable:
            a.setChecked(checked)
        a.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        a.setData(action_id)
        if checkable:
            a.toggled.connect(slot)
        else:
            a.triggered.connect(slot)
        self.addAction(a)
        self.actions_by_id[action_id] = a
        return a

    def apply_shortcuts(self) -> None:
        """(Re)aplica os atalhos a partir das preferências."""
        for aid, a in self.actions_by_id.items():
            key = shortcut_for(self.settings, aid)
            a.setShortcut(QKeySequence(key) if key else QKeySequence())
            base = a.text().split("  (")[0]
            tip = f"{base}  ({key})" if key else base
            if aid.startswith("tool.") or aid == "film.add":
                tip += "\nClique direito / do meio no ícone: usar no botão direito / do meio do mouse"
            a.setToolTip(tip)

    TOOLBAR_STYLE = (
        "QToolBar{background:#26272b;border:none;spacing:1px;padding:2px}"
        "QToolButton{color:#e0e0e0;background:transparent;border:none;border-radius:4px;"
        "padding:3px 5px;min-width:46px;font-size:11px}"
        "QToolButton:hover{background:#3a3d44}"
        "QToolButton:checked{background:#35506e}"
        "QToolButton[popupMode=\"1\"]{padding-right:14px}"
        "QToolButton::menu-button{border:none;width:12px}"
        "QToolButton::menu-arrow{width:8px;height:8px}"
        "QToolBar::separator{background:#44474e;width:1px;margin:6px 3px}")
    MENU_STYLE = ("QMenu{background:#2d2f34;color:#e0e0e0;border:1px solid #44474e}"
                  "QMenu::item{padding:5px 28px 5px 8px}"
                  "QMenu::item:selected{background:#35506e}"
                  "QMenu::separator{height:1px;background:#44474e;margin:4px 8px}")

    def _menu(self) -> QMenu:
        m = QMenu(self)
        m.setStyleSheet(self.MENU_STYLE)
        return m

    # Botões que saem da barra por padrão e moram no menu "Mais": são os que ele usa de vez em
    # quando, e a barra tinha 31 itens numa linha só. Quem quiser de volta marca em
    # Preferências ▸ Geral — a lista de fora fica em `viewer.botoes_fora`.
    FORA_POR_PADRAO = ("view.invert", "view.rotate_cw", "view.cine", "view.anonymize")
    NOME_DOS_OPCIONAIS = {"view.invert": "Inverter", "view.rotate_cw": "Girar e espelhar",
                          "view.cine": "Cine", "view.anonymize": "Ocultar dados do paciente"}

    def botoes_fora(self) -> set:
        guardado = self.settings.get("viewer.botoes_fora", None)
        if guardado is None:
            return set(self.FORA_POR_PADRAO)
        return {b for b in guardado if b in self.NOME_DOS_OPCIONAIS}

    def _button(self, tb: QToolBar, action: QAction, menu: QMenu | None = None,
                instant: bool = False, mods: set | None = None,
                opcional: str = "", modulo: str = "", app: str = "") -> QToolButton:
        """`mods`: modalidades em que o botão faz sentido (None = sempre).

        `opcional`: id do botão que o usuário pode tirar da barra (ele continua no menu "Mais").

        `app` (0.99.12): o botão é uma **aplicação** (`aplicacoes.APLICACOES`): não entra aqui, entra
        no bloco "do exame", no fim da barra, e aparece pela regra e pela escolha dele.
        """
        btn = QToolButton()
        btn.setDefaultAction(action)
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setIconSize(QSize(26, 26))
        if menu is not None:
            btn.setMenu(menu)
            btn.setPopupMode(QToolButton.InstantPopup if instant else QToolButton.MenuButtonPopup)
            menu.installEventFilter(self)
        btn.installEventFilter(self)
        if app:
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, a=app, b=btn: self._menu_da_aplicacao(a, b, pos))
            self.__dict__.setdefault("_apps_pendentes", []).append((app, btn))
            return btn
        # o QToolBar embrulha o widget numa QAction; quem manda na visibilidade é ela,
        # não o botão — esconder o widget direto é desfeito no próximo layout da barra
        acao = tb.addWidget(btn)
        if opcional:
            acao.setVisible(opcional not in self.botoes_fora())
            self.__dict__.setdefault("_opcionais", {})[opcional] = acao
        if mods or modulo:
            self.__dict__.setdefault("_mod_buttons", []).append((btn, acao, set(mods or ()), modulo))
            self.update_modality_buttons()
        return btn

    # ------------------------------------------------- botões por modalidade
    def study_modalities(self) -> set:
        """Modalidades que existem nos exames abertos nesta aba."""
        return {(s.modality or "").upper() for s in getattr(self, "series", [])
                if getattr(s, "modality", "")}

    def update_modality_buttons(self) -> None:
        """Esconde o que não serve ao exame aberto (MN fora de MN, 3D fora de volume…) e o que é de
        módulo desligado (Preferências ▸ Módulos) — este, nem com "todos os botões" ligado."""
        from ipe import modules as MOD
        tudo = bool(self.settings.get("viewer.all_buttons", False))
        presentes = self.study_modalities()
        fora = MOD.desligados(self.settings)
        for btn, acao, mods, modulo in getattr(self, "_mod_buttons", []):
            mostra = tudo or not mods or not presentes or bool(mods & presentes)
            mostra = mostra and modulo not in fora
            acao.setVisible(mostra)
            btn.setVisible(mostra)
        self._atualizar_aplicacoes()

    def switch_wl(self) -> None:
        """Próxima janela gravada no arquivo (0.99.22, plano AW M15). Na mamografia vale para os
        quadros à vista: a AW troca a janela das quatro incidências juntas."""
        vp = self.active
        if vp is None:
            return
        msg = vp.switch_wl()
        if not msg:
            self.status_message.emit("Esta imagem não traz janelas gravadas no arquivo.")
            return
        if (vp.modalidade_atual() or "").upper() == "MG":
            i = vp._janela_arquivo[0]
            for v in self._shown():
                if v is not vp and (v.modalidade_atual() or "").upper() == "MG" and v.janelas_do_arquivo():
                    v.usar_janela_do_arquivo(min(i, len(v.janelas_do_arquivo()) - 1))
        self.status_message.emit(msg)

    def outros_referenciais_ligados(self, vp) -> int:
        """Quantos quadros à vista estão no mesmo grupo de sincronia de `vp` com outro Frame of
        Reference (0.99.45). A sincronia automática só junta o mesmo referencial; o grupo junta
        qualquer coisa, pelo deslocamento — e é isso que o selo avisa."""
        hub = getattr(self, "hub", None)
        if hub is None or not vp.frames or not vp.for_uid:
            return 0
        g = hub.group_of(vp)
        if g is None:
            return 0
        n = 0
        for w in hub.viewports(self):
            if w is vp or not w.frames or hub.group_of(w) != g or not w.for_uid:
                continue
            if w.for_uid != vp.for_uid and w.plane() is not None and vp.plane() is not None:
                n += 1
        return n

    def clonar_roi(self, src, ann) -> list[tuple]:
        """Leva a ROI para os outros quadros à vista, na mesma posição no paciente (0.99.45, plano AW
        item 15). Cada cópia é uma ROI nova do quadro de destino: a média, o desvio e a área são os
        da imagem de lá. Devolve [(quadro, motivo ou "")]."""
        from ipe.imaging import clonar_roi as CR
        out = []
        alvos = [w for w in self._shown() if w is not src and w.frames]
        if not alvos:
            self.status_message.emit("Não há outro quadro com imagem para receber a ROI.")
            return out
        feitos = 0
        for w in alvos:
            motivo = CR.clonar(src, ann, w, self.hub)
            out.append((w, motivo))
            if not motivo:
                feitos += 1
        faltas = [f"{w.series_label or 'quadro'}: {m}" for w, m in out if m]
        msg = f"ROI clonada em {feitos} quadro(s)."
        if faltas:
            msg += " Sem cópia — " + "; ".join(faltas[:3])
        self.status_message.emit(msg)
        return out

    def pacientes_no_layout(self) -> list[dict]:
        """A identidade de cada quadro com imagem (para o selo de mistura de pacientes, 0.99.22)."""
        return [vp.study_info for vp in getattr(self, "viewports", []) if vp.frames and vp.study_info]

    # ------------------------------------------------- aplicações do exame (0.99.12)
    def contexto_do_exame(self):
        from ipe.ui.viewer import aplicacoes as AP
        infos = list(getattr(self, "study_infos", {}).values()) or [getattr(self, "study_info", {})]
        extra = {"dinamica"} if getattr(self, "groups", None) else set()
        return AP.contexto(getattr(self, "series", []), infos, self.settings, extra)

    def _montar_bloco_de_aplicacoes(self, tb: QToolBar) -> None:
        """O bloco "do exame": as aplicações na ordem dele, depois de um separador, e o botão
        "Todas as aplicações", que lista todas — inclusive as que a regra tirou, com o motivo."""
        from ipe.ui.viewer import aplicacoes as AP
        pendentes = dict(getattr(self, "_apps_pendentes", []))
        self._sep_apps = tb.addSeparator()
        self._apps: dict[str, tuple] = {}
        for aid in AP.ordem(self.settings):
            btn = pendentes.get(aid)
            if btn is not None:
                self._apps[aid] = (btn, tb.addWidget(btn))
        self.todas_menu = self._menu()
        self.todas_menu.aboutToShow.connect(self._encher_todas_as_aplicacoes)
        todas = self._plain("Aplicações", "apps", "Todas as aplicações: as deste exame e as outras, "
                                                  "com o motivo de não estarem na barra")
        self.todas_button = self._button(tb, todas, self.todas_menu, instant=True)
        self.update_modality_buttons()

    def estado_das_aplicacoes(self) -> dict[str, tuple[bool, str]]:
        """id -> (na barra, motivo). Módulo desligado tira de tudo, até de "Todas"."""
        from ipe import modules as MOD
        from ipe.ui.viewer import aplicacoes as AP
        ctx = self.contexto_do_exame()
        fora = MOD.desligados(self.settings)
        tudo = bool(self.settings.get("viewer.all_buttons", False))
        out = {}
        for aid in getattr(self, "_apps", {}):
            app = AP.APLICACOES[aid]
            if app.modulo and app.modulo in fora:
                out[aid] = (False, "módulo desligado")
                continue
            vis, motivo = AP.mostrar(self.settings, aid, ctx)
            m, _o = AP.modo(self.settings, aid, ctx.regioes)
            if tudo and m != "nunca":
                vis = True
            out[aid] = (vis, motivo)
        return out

    def app_na_barra(self, aid: str) -> bool:
        par = getattr(self, "_apps", {}).get(aid)
        return bool(par and par[1].isVisible())

    def _atualizar_aplicacoes(self) -> None:
        apps = getattr(self, "_apps", None)
        if not apps:
            return
        estado = self.estado_das_aplicacoes()
        algum = False
        for aid, (btn, acao) in apps.items():
            vis, motivo = estado.get(aid, (False, ""))
            acao.setVisible(vis)
            algum = algum or vis
        sep = getattr(self, "_sep_apps", None)
        if sep is not None:
            sep.setVisible(algum)

    def _encher_todas_as_aplicacoes(self) -> None:
        from ipe import modules as MOD
        from ipe.ui.viewer import aplicacoes as AP
        m = self.todas_menu
        m.clear()
        for velho in self.__dict__.pop("_submenus_de_todas", []):
            velho.deleteLater()
        estado = self.estado_das_aplicacoes()
        fora = MOD.desligados(self.settings)
        sec_barra = [a for a in AP.ordem(self.settings) if a in self._apps and estado[a][0]]
        sec_outras = [a for a in AP.ordem(self.settings) if a in self._apps and not estado[a][0]
                      and AP.APLICACOES[a].modulo not in fora]
        if hasattr(m, "addSection"):
            m.addSection("Na barra, para este exame")
        for aid in sec_barra:
            self._item_da_aplicacao(m, aid, "")
        if sec_outras:
            if hasattr(m, "addSection"):
                m.addSection("Fora da barra (rodam mesmo assim)")
            for aid in sec_outras:
                self._item_da_aplicacao(m, aid, estado[aid][1])
        m.addSeparator()
        a = QAction("Tarefas de IA (andamento e cancelar)…", m)          # 0.99.32
        a.triggered.connect(self.abrir_tarefas_ia)
        m.addAction(a)
        a = QAction("Achados de IA (revisar, confirmar, descartar)…", m)  # 0.99.46
        a.triggered.connect(self.abrir_achados)
        m.addAction(a)
        a = QAction("Configurar a barra e as aplicações…", m)
        a.triggered.connect(self._configurar_barra)
        m.addAction(a)

    def _item_da_aplicacao(self, menu: QMenu, aid: str, motivo: str) -> None:
        btn, _acao = self._apps[aid]
        acao = btn.defaultAction()
        nome = acao.iconText() or acao.text()
        texto = f"{nome} — {motivo}" if motivo else nome
        opcoes = btn.menu()
        if opcoes is None:
            a = QAction(acao.icon(), texto, menu)
            a.triggered.connect(acao.trigger)
            menu.addAction(a)
            return
        if btn.popupMode() == QToolButton.InstantPopup:
            # o próprio menu do botão vira o submenu (ele se enche sozinho ao abrir)
            opcoes.setTitle(texto)
            opcoes.setIcon(acao.icon())
            menu.addMenu(opcoes)
            return
        sub = QMenu(texto, menu)
        sub.setIcon(acao.icon())
        sub.setStyleSheet(self.MENU_STYLE)
        principal = QAction(acao.text(), sub)
        principal.triggered.connect(acao.trigger)
        sub.addAction(principal)
        opcoes.setTitle("Opções")
        sub.addMenu(opcoes)
        menu.addMenu(sub)
        self.__dict__.setdefault("_submenus_de_todas", []).append(sub)

    def _menu_da_aplicacao(self, aid: str, btn, pos) -> None:
        self.menu_da_aplicacao(aid).exec(btn.mapToGlobal(pos))

    def menu_da_aplicacao(self, aid: str) -> QMenu:
        """Botão direito numa aplicação da barra: sempre, automático ou nunca — em todo exame ou
        só nesta região (separado de quem exibe, para testar)."""
        from ipe.ui.viewer import aplicacoes as AP
        m = self._menu()
        ctx = self.contexto_do_exame()
        atual, origem = AP.modo(self.settings, aid, ctx.regioes)
        nome = AP.APLICACOES[aid].nome
        if hasattr(m, "addSection"):
            m.addSection(f"Em todos os exames ({nome})")
        for modo in AP.MODOS:
            a = QAction(AP.NOME_DO_MODO[modo], m, checkable=True)
            a.setChecked(origem in ("", "*") and modo == atual)
            a.triggered.connect(lambda _=False, md=modo: self._definir_modo_da_aplicacao(aid, md, "*"))
            m.addAction(a)
        for r in sorted(ctx.regioes):
            nr = AP.nome_da_regiao(self.settings, r)
            if hasattr(m, "addSection"):
                m.addSection(f"Só em exames de {nr.lower()}")
            for modo, rotulo in (("sempre", f"Sempre em exames de {nr.lower()}"),
                                 ("nunca", f"Nunca em exames de {nr.lower()}")):
                a = QAction(rotulo, m, checkable=True)
                a.setChecked(origem == r and atual == modo)
                a.triggered.connect(lambda _=False, md=modo, rr=r: self._definir_modo_da_aplicacao(aid, md, rr))
                m.addAction(a)
            if origem == r:
                a = QAction(f"Tirar a exceção de {nr.lower()}", m)
                a.triggered.connect(lambda _=False, rr=r: self._definir_modo_da_aplicacao(aid, "auto", rr))
                m.addAction(a)
        m.addSeparator()
        regra = QAction(f"Regra: {AP.descrever_regra(AP.APLICACOES[aid], self.settings)}", m)
        regra.setEnabled(False)
        m.addAction(regra)
        a = QAction("Configurar a barra e as aplicações…", m)
        a.triggered.connect(self._configurar_barra)
        m.addAction(a)
        return m

    def _definir_modo_da_aplicacao(self, aid: str, modo: str, regiao: str) -> None:
        from ipe.ui.viewer import aplicacoes as AP
        AP.definir_modo(self.settings, aid, modo, regiao)
        self.settings.save()
        self._atualizar_todas_as_abas()
        vis = self.estado_das_aplicacoes().get(aid, (False, ""))[0]
        nome = AP.APLICACOES[aid].nome
        self.status_message.emit(f"Aplicação {nome}: na barra." if vis else
                                 f"Aplicação {nome}: fora da barra — continua no botão Aplicações.")

    def _atualizar_todas_as_abas(self) -> None:
        win = self.window()
        abas = list(win.all_viewer_tabs()) if hasattr(win, "all_viewer_tabs") else []
        for t in abas or [self]:
            t.update_modality_buttons()
        if self not in abas:
            self.update_modality_buttons()

    def _configurar_barra(self) -> None:
        win = self.window()
        if hasattr(win, "abrir_config_barra"):
            win.abrir_config_barra()
        else:
            from ipe.ui.viewer.barra_config import BarraDialog
            if BarraDialog(self.settings, self).exec():
                self.update_modality_buttons()

    # ------------------------------------------------------------ botões do mouse
    @staticmethod
    def _tool_of_action(a: QAction | None) -> str | None:
        if a is None:
            return None
        data = str(a.data() or "")
        if data.startswith("tool.") and data[5:] in TOOLS:
            return data[5:]
        if data == "film.add":
            return "film"
        return None

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802
        """Clique com o botão direito ou do meio num ícone de ferramenta: atribui a ferramenta a
        esse botão do mouse (o esquerdo continua sendo o clique normal)."""
        t = ev.type()
        if t in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick) \
                and ev.button() in (Qt.RightButton, Qt.MiddleButton):
            if isinstance(obj, QToolButton):
                tool = self._tool_of_action(obj.defaultAction())
            elif isinstance(obj, QMenu):
                tool = self._tool_of_action(obj.actionAt(ev.position().toPoint()))
            else:
                tool = None
            if tool is not None:
                if t == QEvent.MouseButtonRelease:
                    self.set_button_tool("right" if ev.button() == Qt.RightButton else "middle", tool)
                    if isinstance(obj, QMenu):
                        obj.close()
                return True
        return super().eventFilter(obj, ev)

    def irmaos(self) -> list:
        """As abas dos **outros** monitores do mesmo exame.

        Os monitores são uma estação só: o que se escolhe num vale nos outros. Quem muda alguma
        coisa chama isto e repassa — sem repassar de volta, senão os dois ficam se avisando.
        """
        return [t for t in (self.monitor_group or []) if t is not self]

    def mouse_mudou(self) -> None:
        """O mouse mudou em outro lugar: só redesenhar o que mostra o estado."""
        self.refresh_tool_badges()
        for v in self.viewports:
            v.update()

    def set_button_tool(self, button: str, tool: str, propagar: bool = True) -> None:
        mouse = dict(self.settings.get("viewer.mouse", {}) or {})
        mouse[button] = tool
        self.settings.set("viewer.mouse", mouse)
        try:
            self.settings.save()
        except Exception as e:  # noqa: BLE001
            log.warning("não salvou o mouse: %s", e)
        self.mouse_mudou()
        if propagar:
            for t in self.irmaos():
                t.mouse_mudou()
        name = {"right": "Botão direito", "middle": "Botão do meio"}[button]
        extra = ""
        if Viewport.is_click_tool(tool):
            extra = (" — Shift + clique direito abre o menu" if button == "right"
                     else " — Shift + clique do meio ajusta a imagem")
        self.status_message.emit(f"{name}: {TOOLS.get(tool, tool)}{extra}")

    def refresh_tool_badges(self) -> None:
        """Selo D (direito) / M (meio) nos ícones das ferramentas atribuídas a esses botões."""
        if not hasattr(self, "tool_actions"):
            return
        mouse = self.settings.get("viewer.mouse", {}) or {}
        right, middle = mouse.get("right", "zoom"), mouse.get("middle", "pan")
        targets = dict(self.tool_actions)
        if hasattr(self, "film_action"):
            targets["film.add"] = self.film_action
        for key, a in targets.items():
            tool = "film" if key == "film.add" else key
            base = icon(TOOL_ICONS.get(tool, tool))
            letters = "".join(x for x, t in (("D", right), ("M", middle)) if t == tool)
            if letters:
                from ipe.ui.icons import with_corner_letter
                pm = with_corner_letter(base.pixmap(64, 64), letters)
                a.setIcon(QIcon(pm))
            else:
                a.setIcon(base)

    def showEvent(self, e) -> None:  # noqa: N802
        self.refresh_tool_badges()
        super().showEvent(e)

    def _plain(self, text: str, icon_name: str, tip: str = "") -> QAction:
        a = QAction(icon(icon_name), text, self)
        a.setToolTip(tip or text)
        return a

    def _build_toolbar(self) -> QToolBar:
        self.actions_by_id: dict[str, QAction] = {}
        tb = QToolBar()
        tb.setStyleSheet(self.TOOLBAR_STYLE)
        tb.setIconSize(QSize(26, 26))
        tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        group = QActionGroup(self)
        self.tool_actions: dict[str, QAction] = {}
        for key, name in TOOLS.items():
            a = self._act(f"tool.{key}", name, lambda _=False, kk=key: self.set_left_tool(kk))
            a.setCheckable(True)
            a.setIcon(icon(TOOL_ICONS.get(key, key)))
            a.setIconText(TOOL_SHORT.get(key, name))
            group.addAction(a)
            self.tool_actions[key] = a
        self.tool_actions.get(self.left_tool, self.tool_actions["wl"]).setChecked(True)

        # --- janela/nível (clique: ferramenta; seta: presets)
        wl_menu = self._menu()
        wl_menu.aboutToShow.connect(lambda: self._fill_preset_menu(wl_menu))
        self._button(tb, self.tool_actions["wl"], wl_menu)
        self._button(tb, self.tool_actions["pan"])
        zoom_menu = self._menu()
        self._button(tb, self.tool_actions["zoom"], zoom_menu)
        scroll_menu = self._menu()
        self._button(tb, self.tool_actions["scroll"], scroll_menu)

        # --- medidas: o botão mostra a última ferramenta escolhida
        self.measure_menu = self._menu()
        for key in MEASURE_TOOLS:
            if key in ("measure", "text"):
                self.measure_menu.addSeparator()
            self.measure_menu.addAction(self.tool_actions[key])
        self.measure_menu.addSeparator()
        self.continuous_action = self._act(
            "annot.continuous", "Medição contínua (a ferramenta continua ativa)",
            lambda on: self.settings.set("viewer.measure_continuous", on), checkable=True,
            checked=bool(self.settings.get("viewer.measure_continuous", True)))
        self.measure_menu.addAction(self.continuous_action)
        self.measure_menu.addSeparator()
        nxt = self._act("annot.next", "Próxima imagem com medida",
                        lambda: self._on_active(lambda v: v.go_to_annotation(1)))
        nxt.setIcon(icon("next"))
        prv = self._act("annot.prev", "Imagem anterior com medida",
                        lambda: self._on_active(lambda v: v.go_to_annotation(-1)))
        prv.setIcon(icon("prev"))
        self.measure_menu.addAction(nxt)
        self.measure_menu.addAction(prv)
        self.annot_list_menu = self.measure_menu.addMenu("Ir para a medida…")
        self.annot_list_menu.setStyleSheet(self.MENU_STYLE)
        self.annot_list_menu.aboutToShow.connect(self._fill_annotation_list)
        self.measure_menu.addSeparator()
        for text, fn in (("Apagar a medida selecionada (Del)",
                          lambda v: v.delete_annotation(v.selected) if v.selected else None),
                         ("Apagar as medidas desta imagem", lambda v: v.delete_frame_annotations()),
                         ("Apagar todas as medidas da série…", self._delete_series_annotations)):
            a = QAction(icon("trash"), text, self)
            a.triggered.connect(lambda _=False, f=fn: self._on_active(f))
            self.measure_menu.addAction(a)
        self.measure_menu.addSeparator()
        self.measure_menu.addAction(self._act("annot.export", "Exportar medidas para planilha (CSV/Excel)…",
                                              self.export_measures_table))
        hint = QAction("Editar: clique na medida e arraste as pontas; botão direito sobre ela = opções", self)
        hint.setEnabled(False)
        self.measure_menu.addAction(hint)
        first = self.left_tool if self.left_tool in MEASURE_TOOLS else "measure"
        self.measure_button = self._button(tb, self.tool_actions[first], self.measure_menu)
        self._button(tb, self.tool_actions["cross"])
        tb.addSeparator()

        # --- layout e imagem
        layout_menu = self._menu()
        for rows, cols in LAYOUTS:
            a = QAction(f"{rows} × {cols}", self)
            a.triggered.connect(lambda _=False, r=rows, c=cols: self.set_layout(r, c))
            layout_menu.addAction(a)
        self._button(tb, self._plain("Layout", "layout", "Layout dos quadros"), layout_menu, instant=True)
        inv = self._act("view.invert", "Inverter", lambda: self._on_active(lambda v: v.set_invert()))
        inv.setIcon(icon("invert"))
        self._button(tb, inv, opcional="view.invert")
        rot_menu = self._menu()
        rcw = self._act("view.rotate_cw", "Girar 90° à direita", lambda: self._on_active(lambda v: v.rotate_view(90)))
        rcw.setIcon(icon("rotate"))
        rcw.setIconText("Girar")
        rot_menu.addAction(rcw)
        rot_menu.addAction(self._act("view.rotate_ccw", "Girar 90° à esquerda",
                                     lambda: self._on_active(lambda v: v.rotate_view(-90))))
        rot_menu.addAction(self._act("view.rotate_180", "Girar 180°",
                                     lambda: self._on_active(lambda v: v.rotate_view(180))))
        rot_menu.addSeparator()
        rot_menu.addAction(self._act("view.flip_h", "Espelhar esquerda ↔ direita",
                                     lambda: self._on_active(lambda v: v.flip_view(True))))
        rot_menu.addAction(self._act("view.flip_v", "Espelhar cima ↕ baixo",
                                     lambda: self._on_active(lambda v: v.flip_view(False))))
        rot_menu.addSeparator()
        rot_menu.addAction(self._act("view.orient_reset", "Voltar à orientação original",
                                     lambda: self._on_active(lambda v: v.reset_orientation())))
        a_all = QAction("Aplicar o giro/espelho do quadro ativo a todos os quadros", self)
        a_all.triggered.connect(self.orientation_to_all)
        rot_menu.addAction(a_all)
        self._button(tb, rcw, rot_menu, opcional="view.rotate_cw")
        self.cmap_menu = self._menu()
        self.cmap_menu.aboutToShow.connect(self._fill_cmap_menu)
        cm = self._plain("Cor", "palette", "Tabela de cores (pseudocor) do quadro ativo")
        self._button(tb, cm, self.cmap_menu, instant=True)
        self.fusion_menu = self._menu()
        self.fusion_menu.aboutToShow.connect(self._fill_fusion_menu)
        fu = self._plain("Fusão", "fusion", "Fusão: sobrepor outra série ao quadro ativo (ex.: PET na TC)")
        self._button(tb, fu, self.fusion_menu, instant=True, app="fusao")
        self._act("wl.switch", "Switch WL", self.switch_wl)
        fit = self._act("view.fit", "Ajustar à janela", lambda: self._on_active(lambda v: v.fit()))
        fit.setIcon(icon("fit"))
        reset = self._act("view.reset", "Restaurar", lambda: self._on_active(lambda v: v.reset_view()))
        reset.setIcon(icon("reset"))
        reset_menu = self._menu()
        reset_menu.addAction(fit)
        reset_menu.addAction(reset)
        self._button(tb, reset, reset_menu)
        cine = self._act("view.cine", "Cine", lambda: self._on_active(lambda v: v.toggle_cine()))
        cine.setIcon(icon("cine"))
        self._button(tb, cine, opcional="view.cine")
        zoom_menu.addAction(fit)
        zoom_menu.addSeparator()
        zoom_menu.addAction(self.tool_actions["loupe"])
        zoom_menu.addAction(self.tool_actions["quadzoom"])
        one = QAction("Tamanho real (1 pixel da imagem = 1 da tela)", self)
        one.triggered.connect(lambda: self._on_active(lambda v: v.zoom_actual_pixels()))
        zoom_menu.addAction(one)
        zoom_menu.addSeparator()
        zoom_menu.addAction(reset)
        wl_menu.addSeparator()
        wl_menu.addAction(self._act("view.histogram", "Histograma da imagem (ou da ROI)…",
                                    lambda: self._on_active(self.show_histogram)))
        scroll_menu.addAction(cine)
        goto = QAction("Ir para a imagem…", self)
        goto.triggered.connect(lambda: self._on_active(self._ask_image))
        scroll_menu.addAction(goto)
        sp = self._act("series.prev", "Série anterior", lambda: self._cycle_series(-1))
        sn = self._act("series.next", "Próxima série", lambda: self._cycle_series(1))
        sp.setIcon(icon("prev"))
        sn.setIcon(icon("next"))
        tb.addSeparator()

        # --- MPR
        self.mpr_action = self._act("mpr.toggle", "MPR 3 planos (axial, coronal, sagital)", self.toggle_mpr,
                                    checkable=True)
        self.mpr_action.setIcon(icon("mpr"))
        self.mpr_action.setIconText("MPR")
        mpr_menu = self._menu()
        mpr_menu.addAction(self.mpr_action)
        mpr_menu.addSeparator()
        for name, key in (("Axial", "A"), ("Coronal", "C"), ("Sagital", "S")):
            mpr_menu.addAction(self._act(f"mpr.{name.lower()}", f"Reconstruir no quadro ativo: {name}",
                                         lambda _=False, n=name: self.reconstruct_plane(n)))
        mpr_menu.addAction(self._act("mpr.obliquo_daqui", "Oblíquo a partir do plano atual (sem mudar a imagem)",
                                     lambda: self.reformatar(self.active, "Oblíquo")))
        mpr_menu.addAction(self.tool_actions["oblique"])
        mpr_menu.addAction(self.tool_actions["rotplane"])
        mpr_menu.addSeparator()
        save = QAction("Salvar a reconstrução do quadro ativo como série nova", self)
        save.triggered.connect(lambda: self.save_reconstruction(self.active, notify=True))
        mpr_menu.addAction(save)
        back = QAction("Voltar o quadro ativo à série original", self)
        back.triggered.connect(self._plane_back)
        mpr_menu.addAction(back)
        self._button(tb, self.mpr_action, mpr_menu, app="mpr")
        menu3d = self._menu()
        for text, fn in (("Renderização de volume (VR)…", lambda: self.open_3d("vr")),
                         ("MIP 3D girável…", lambda: self.open_3d("mip")),
                         ("MinIP 3D (vias aéreas)…", lambda: self.open_3d("minip"))):
            a = QAction(text, self)
            a.triggered.connect(fn)
            menu3d.addAction(a)
        a = QAction("Comparar duas fases lado a lado (4D)…", self)
        a.triggered.connect(lambda: self.compare_phases())
        menu3d.addAction(a)
        a = QAction("Superfície 3D por limiar (STL)…", self)
        a.triggered.connect(self.open_surface)
        menu3d.addAction(a)
        menu3d.addSeparator()
        menu3d.addAction(self.tool_actions["curve"])
        menu3d.addAction(self.tool_actions["grow"])
        est = self._act("estruturas.abrir", "Estruturas: editar máscaras (SEG / RTSTRUCT)",
                        lambda: self.abrir_estruturas())
        menu3d.addAction(est)
        tm = QAction("Resumo das segmentações (TMTV / TLG)…", self)
        tm.triggered.connect(self.show_tmtv)
        menu3d.addAction(tm)
        b3d = self._act("view.3d", "3D: renderização de volume", lambda: self.open_3d("vr"))
        b3d.setIcon(icon("cube"))
        b3d.setIconText("3D")
        self._button(tb, b3d, menu3d, app="3d")
        dyn = self._act("dyn.open", "Avaliação dinâmica (MSI, PEI, SER e curvas)", lambda: self.open_dynamic())
        dyn.setIcon(icon("tic"))
        dyn.setIconText("Dinâmica")
        self._button(tb, dyn, app="dinamica")
        menu_nm = self._menu()
        a = QAction("Curvas atividade-tempo por região…", self)
        a.triggered.connect(lambda: NMV.open_analysis(self))
        menu_nm.addAction(a)
        a = QAction("Comparar imagens do exame (DMSA, paratireoide, tireoide, trânsito)…", self)
        a.triggered.connect(lambda: NMV.open_multi(self))
        menu_nm.addAction(a)
        menu_nm.addSeparator()
        a = QAction("Anterior e posterior lado a lado", self)
        a.triggered.connect(lambda: NMV.open_ant_post(self))
        menu_nm.addAction(a)
        a = QAction("Anterior, posterior e média geométrica", self)
        a.triggered.connect(lambda: NMV.open_ant_post(self, with_gm=True))
        menu_nm.addAction(a)
        menu_nm.addSeparator()
        a = QAction("Espelhar a vista posterior na média geométrica", self)
        a.setCheckable(True)
        a.setChecked(bool(self.settings.get("nm.flip_post", True)))
        a.toggled.connect(self._nm_set_flip)
        menu_nm.addAction(a)
        a = QAction("Escala de cinza invertida nas imagens de medicina nuclear", self)
        a.setCheckable(True)
        a.setChecked(bool(self.settings.get("nm.invert", True)))
        a.toggled.connect(self._nm_set_invert)
        menu_nm.addAction(a)
        self.nm_action = self._act("nm.ant_post", "Medicina nuclear: anterior e posterior lado a lado",
                                   lambda: NMV.open_ant_post(self))
        self.nm_action.setIcon(icon("tic"))
        self.nm_action.setIconText("MN")
        self._button(tb, self.nm_action, menu_nm, app="mn")

        # --- sincronização (clique: ligar quadros; seta: opções)
        sync_menu = self._menu()
        # 0.99.10: as duas primeiras linhas escolhem COMO o botão Sincronizar sincroniza.
        # Automática: os quadros do mesmo exame vão para o mesmo ponto do paciente (alinhados pelo
        # quadro ativo ao ligar). Manual: ficam ligados mantendo a diferença de cortes do momento.
        # A automática continua lembrada por modalidade (na RM nasce desligada, 0.99.9).
        self.sync_auto_action = self._act("sync.auto", "Automática (mesmo ponto do paciente)",
                                          lambda *_a: self.escolher_modo_sync("auto"))
        self.sync_manual_action = self._act("sync.manual", "Manual (mantém a diferença entre os quadros)",
                                            lambda *_a: self.escolher_modo_sync("manual"))
        self.sync_modo_group = QActionGroup(self)
        for a in (self.sync_auto_action, self.sync_manual_action):
            a.setCheckable(True)
            self.sync_modo_group.addAction(a)
        self.sync_auto_action.setToolTip("Ao ligar, os outros quadros do mesmo exame vão para o ponto do "
                                         "quadro ativo e passam a andar com ele")
        self.sync_manual_action.setToolTip("Ao ligar, os quadros andam juntos mantendo a diferença de cortes "
                                           "que tinham na hora (serve para comparar com outro exame)")
        self.sync_wl_action = self._act("sync.window", "Janela/nível",
                                        lambda on: self.hub.set_flag("sync_wl", on),
                                        checkable=True, checked=self.hub.sync_wl)
        self.sync_zoom_action = self._act("sync.zoom", "Zoom e pan",
                                          lambda on: self.hub.set_flag("sync_zoom", on),
                                          checkable=True, checked=self.hub.sync_zoom)
        self.strip_action = self._act("view.strip", "Tira de séries (miniaturas)",
                                      lambda on: self.strip_col.setVisible(on),
                                      checkable=True, checked=True)
        self.strip_action.setToolTip("Mostrar ou esconder a coluna de miniaturas desta tela. Com o "
                                     "exame repartido entre monitores ela vem escondida nas telas "
                                     "de dentro (Preferências ▸ Monitores).")
        self.refs_action = self._act("view.reflines", "Linhas de referência",
                                     lambda on: self.hub.set_flag("show_refs", on),
                                     checkable=True, checked=self.hub.show_refs)
        for a in (self.sync_auto_action, self.sync_manual_action):
            sync_menu.addAction(a)
        sync_menu.addSeparator()
        for a in (self.sync_wl_action, self.sync_zoom_action, self.refs_action, self.strip_action):
            sync_menu.addAction(a)
        sync_menu.addSeparator()
        self.sync_mode_action = self._act(
            "sync.mode", "Alternar modo: desligado / mesmo estudo / todos",
            lambda: self.status_message.emit(self.hub.cycle_mode(self)))
        sync_menu.addAction(self.sync_mode_action)
        grp = self._act("sync.group", "Trocar grupo do quadro ativo (corrente)",
                        lambda: self._on_active(self._cycle_group))
        sync_menu.addAction(grp)
        a = QAction("Desligar todos os grupos", self)
        a.triggered.connect(lambda: (self.hub.unlink_all(), self.update_reference_lines()))
        sync_menu.addAction(a)
        sync_menu.addSeparator()
        conf = sync_menu.addMenu("Conferir o registro com o outro exame")
        for modo, nome in (("xadrez", "Xadrez"), ("cortina", "Cortina (segue o mouse)"), ("diferenca", "Diferença"),
                           ("mistura", "Mistura 50%")):
            conf.addAction(self._act(f"registro.conferir.{modo}", f"Conferir o registro: {nome}",
                                     lambda _=False, m=modo: self.conferir_registro(m)))
        conf.addSeparator()
        conf.addAction(self._act("registro.conferir.off", "Conferir o registro: desligar",
                                 lambda: self.conferir_registro(None)))
        sync_menu.addAction(self._act("sync.register", "Alinhar automaticamente com o outro exame (registro)",
                                      self.auto_register))
        self.link_action = self._act("sync.link", "Ligar quadros", self.toggle_link, checkable=True)
        self.link_action.setIcon(icon("sync"))
        self.link_action.setIconText("Sincronizar")
        self.link_action.setToolTip("Liga ou desliga a sincronização, automática ou manual "
                                    "(seta: escolher e outras opções)")
        self._button(tb, self.link_action, sync_menu)
        tb.addSeparator()

        # --- imagens-chave, anteriores, monitor, ocultar
        key = self._act("key.toggle", "Marcar/desmarcar imagem-chave", self.toggle_key_image)
        key.setIcon(icon("key"))
        key.setIconText("Chave")
        show_keys = self._act("key.show", "Mostrar imagens-chave", self.show_key_images)
        key_menu = self._menu()
        key_menu.addAction(key)
        key_menu.addAction(show_keys)
        key_menu.addSeparator()
        grava_ko = self._act("key.gravar", "Gravar imagens-chave e anotações no exame (KO + GSPS)",
                             lambda: self.gravar_ko_gsps())
        key_menu.addAction(grava_ko)
        self._button(tb, key, key_menu)
        self.priors_menu = self._menu()
        self.priors_menu.aboutToShow.connect(self._fill_priors_menu)
        self.priors_action = QAction(icon("priors"), "Anteriores", self, checkable=True)
        self.priors_action.setToolTip("Linha do tempo do paciente (banco e PACS); seta: menu rápido")
        self.priors_action.toggled.connect(self.toggle_priors_panel)
        self._button(tb, self.priors_action, self.priors_menu)
        self._act("study.priors", "Adicionar exame anterior",
                  lambda: self.priors_menu.exec(self.mapToGlobal(self.rect().center())))
        self.measures_action = self._act("measures.panel", "Medidas", self.toggle_measures_panel,
                                         checkable=True)
        self.measures_action.setIcon(icon("measure"))
        self.measures_action.setIconText("Medidas")
        self.measures_action.setToolTip("Todas as medidas e ROIs do exame numa lista: clicar leva até a "
                                        "imagem com a medida já selecionada")
        self._button(tb, self.measures_action)
        # --- oncologia / IA / laudo
        self.lesions_action = self._act("lesion.panel", "Lesões", self.toggle_lesion_panel, checkable=True)
        self.lesions_action.setIcon(icon("lesion"))
        self.lesions_action.setIconText("Lesões")
        les_menu = self._menu()
        les_menu.addAction(self.lesions_action)
        la = QAction("Layout das lesões (um quadro por lesão)", self)
        la.triggered.connect(lambda: self.lesion_layout())
        les_menu.addAction(la)
        lk = QAction("Ligar a medida selecionada a uma lesão…", self)
        lk.triggered.connect(lambda: self._on_active(lambda v: self.choose_lesion_for(v, v.selected)
                                                     if v.selected is not None else None))
        les_menu.addAction(lk)
        self._button(tb, self.lesions_action, les_menu)
        self.overlay_menu = self._menu()
        self.overlay_menu.aboutToShow.connect(lambda: self._fill_overlay_menu(self.overlay_menu))
        self.overlay_action = self._act("overlay.toggle", "CAD/IA", self.toggle_overlays)
        self.overlay_action.setIcon(icon("ai"))
        self.overlay_action.setIconText("CAD/IA")
        self.overlay_action.setToolTip("Resultados de CAD/IA, segmentações (SEG/RTSTRUCT) e anotações de outros "
                                       "sistemas (GSPS). Clique: mostrar/ocultar; seta: lista")
        self._button(tb, self.overlay_action, self.overlay_menu)
        rep = self._act("report.open", "Laudo", self.open_report)
        rep.setIcon(icon("report"))
        rep.setIconText("Laudo")
        self._button(tb, rep)
        film = self._act("film.add", "Enviar ao filme", self.film_add_current)
        film.setIcon(icon("film"))
        film.setIconText("Filme")
        self.film_action = film
        film_menu = self._menu()
        film_menu.addAction(film)
        film_menu.addAction(self.tool_actions["film"])
        film_menu.addAction(self._act("film.add_all", "Enviar todos os quadros", self.film_add_all))
        film_menu.addAction(self._act("film.series", "Série do quadro (inteira / intervalo)…", self.film_add_series))
        film_menu.addAction(self._act("film.keys", "Imagens-chave do exame", self.film_add_keys))
        film_menu.addSeparator()
        film_menu.addAction(self._act("film.show", "Abrir o compositor de filmes",
                                      lambda: self.film_requested.emit({"kind": "show"})))
        self._button(tb, film, film_menu)
        mon = self._plain("Monitor", "monitor", "Mover este estudo para uma janela em outro monitor")
        mon.triggered.connect(lambda: self.detach_requested.emit(self))
        self._button(tb, mon)
        self._act("cad.revelar", "Revelar o CAD (ler antes, ver depois)", lambda: self.revelar_cad())
        self._act("view.mosaico", "Mosaico de cortes no quadro (2×2 → 3×3 → 4×4 → desligado)",
                  lambda: self._on_active(lambda v: v.proximo_mosaico()))
        self.anon_action = self._act("view.anonymize", "Ocultar dados do paciente",
                                     self.set_anonymize, checkable=True)
        self.anon_action.setIcon(icon("anon"))
        self.anon_action.setIconText("Ocultar")
        # 0.99.42: perfis de ocultação (Ocultar tudo / Tela / Ensino / Publicação), na seta do botão
        self.perfil_menu = self._menu()
        self.perfil_menu.aboutToShow.connect(self._encher_menu_de_perfis)
        self._button(tb, self.anon_action, self.perfil_menu, opcional="view.anonymize")

        # --- anotações da tela (0.99.9): completa / parcial 1 / parcial 2 / ausente
        from ipe.ui.viewer import anotacoes as AN
        self.anot_menu = self._menu()
        self.anot_group = QActionGroup(self)
        self.anot_actions: dict[str, QAction] = {}
        for chave, nome in AN.NIVEIS:
            a = QAction(nome, self, checkable=True)
            a.triggered.connect(lambda _=False, c=chave: self.set_anotacoes(c))
            self.anot_group.addAction(a)
            self.anot_menu.addAction(a)
            self.anot_actions[chave] = a
        self.anot_menu.addSeparator()
        self.anot_menu.addAction(self._act("view.annot_next", "Anotações: próximo nível",
                                           self.proximo_nivel_de_anotacao))
        cfg = QAction("Escolher o que cada nível mostra…", self)
        cfg.triggered.connect(lambda: self.preferences_requested.emit("Anotações"))
        self.anot_menu.addAction(cfg)
        self.anot_button_action = self._plain("Anotações", "text",
                                              "Anotações da tela: completa, parcial 1, parcial 2 ou ausente")
        self.anot_button_action.triggered.connect(self.proximo_nivel_de_anotacao)
        self._button(tb, self.anot_button_action, self.anot_menu)
        self.copy_action = self._act("view.copy", "Copiar a imagem do quadro (área de transferência)",
                                     self.copiar_quadro)
        self.reflect_anotacoes()

        # --- mais
        more = self._menu()
        # O que saiu da barra entra aqui: botão escondido não pode virar função perdida.
        self._mais_opcionais = more.addSection("Da barra de ferramentas") if hasattr(more, "addSection") else None
        for aid in self.FORA_POR_PADRAO:
            acao = self.actions_by_id.get(aid)
            if acao is not None:
                more.addAction(acao)
        more.addSeparator()
        more.addAction(sp)
        more.addAction(sn)
        more.addSeparator()
        exportar = self._act("study.export", "Exportar (DICOM, CD/pendrive, imagens)…", self.export_dialog)
        more.addAction(exportar)
        sr = QAction("Salvar medidas como DICOM SR…", self)
        sr.triggered.connect(self.save_measurements_sr)
        more.addAction(sr)
        # Tudo o que tira dado do programa; a janela da chamada externa "só visualizador" esconde.
        self.acoes_de_saida = [exportar, sr, self.film_action]
        more.addSeparator()
        tags = QAction("Informações DICOM (tags)…", self)
        tags.triggered.connect(lambda: self._on_active(lambda v: v.show_tags()))
        more.addAction(tags)
        # medidas guiadas (0.99.14): MRPI, Evans, ângulo calosal — aparece em RM/TC de crânio
        menu_idx = self._menu()
        a_nres = QAction("Resultado dos índices automáticos deste exame…", self)
        a_nres.triggered.connect(lambda: self.abrir_neuro(do_exame=True))
        menu_idx.addAction(a_nres)
        a_nauto = QAction("Índices automáticos (IA, SynthSeg) desta série…", self)
        a_nauto.triggered.connect(lambda: self.neuro_automatica(self.active))
        menu_idx.addAction(a_nauto)
        menu_idx.aboutToShow.connect(lambda: a_nres.setEnabled(self.neuro_do_exame() is not None))
        menu_idx.addSeparator()
        from ipe.imaging import roteiros as RT
        for rid, rot in RT.ROTEIROS.items():
            a = QAction(rot.nome + "…", self)
            a.triggered.connect(lambda _=False, r=rid: self.abrir_roteiro(r))
            menu_idx.addAction(a)
        idx = self._act("roteiro.mrpi", "Medidas guiadas: MRPI e MRPI 2.0",
                        lambda: self.abrir_roteiro("mrpi"))
        idx.setIcon(icon("measure"))
        idx.setIconText("Índices")
        self._button(tb, idx, menu_idx, app="indices")
        # cefalometria do cavum (0.99.15): automática (TotalSegmentator) ou à mão — TC de face/pescoço
        menu_cef = self._menu()
        a_res = QAction("Resultado da cefalometria automática deste exame…", self)
        a_res.triggered.connect(lambda: self.abrir_cefalometria(do_exame=True))
        menu_cef.addAction(a_res)
        a_auto = QAction("Cefalometria automática (IA) desta série…", self)
        a_auto.triggered.connect(lambda: self.cefalometria_automatica(self.active))
        menu_cef.addAction(a_auto)
        a_mao = QAction("Cefalometria à mão (roteiro)…", self)
        a_mao.triggered.connect(lambda: self.abrir_cefalometria(do_exame=False))
        menu_cef.addAction(a_mao)
        menu_cef.aboutToShow.connect(lambda: a_res.setEnabled(self.cefalometria_do_exame() is not None))
        cef = self._act("cefalometria.auto", "Cefalometria do cavum (automática)", self.cefalometria_botao)
        cef.setIcon(icon("measure"))
        cef.setIconText("Cefalometria")
        self._button(tb, cef, menu_cef, app="cefalometria")
        # níveis linfonodais (0.99.20): mapa na TC de pescoço; a lesão segmentada ganha o nível
        lin = self._act("linfonodos.auto", "Mapa dos níveis linfonodais (IA)",
                        lambda: self.linfonodos_automatico(self.active))
        lin.setIcon(icon("measure"))
        lin.setIconText("Linfonodos")
        self._button(tb, lin, None, app="linfonodos")
        # nódulos pulmonares (0.99.46): achados revisáveis
        menu_nod = self._menu()
        a_nod = QAction("Procurar nódulos pulmonares nesta série (IA)…", self)
        a_nod.triggered.connect(self._nodulos_do_ativo)
        menu_nod.addAction(a_nod)
        a_ach = QAction("Achados de IA (revisar, confirmar, descartar)…", self)
        a_ach.triggered.connect(self.abrir_achados)
        menu_nod.addAction(a_ach)
        nod = self._act("nodulos.auto", "Nódulos pulmonares (IA)", self.nodulos_botao)
        nod.setIcon(icon("measure"))
        nod.setIconText("Nódulos")
        self._button(tb, nod, menu_nod, app="nodulos")
        self._act("achados.abrir", "Achados de IA: revisar, confirmar, descartar", self.abrir_achados)
        # composição corporal em L3 e esteatose (0.99.47)
        menu_comp = self._menu()
        a_comp = QAction("Medir a composição corporal em L3 e o fígado nesta série (IA)…", self)
        a_comp.triggered.connect(self._composicao_do_ativo)
        menu_comp.addAction(a_comp)
        a_ach2 = QAction("Achados de IA (revisar, confirmar, descartar)…", self)
        a_ach2.triggered.connect(self.abrir_achados)
        menu_comp.addAction(a_ach2)
        comp = self._act("composicao.auto", "Composição corporal em L3 e esteatose (IA)", self.composicao_botao)
        comp.setIcon(icon("measure"))
        comp.setIconText("Composição")
        self._button(tb, comp, menu_comp, app="composicao")
        # gordura e ferro hepáticos na RM (0.99.49)
        menu_fig = self._menu()
        a_fig = QAction("Medir a gordura (PDFF) e o ferro (R2*) do fígado nesta RM (IA)…", self)
        a_fig.triggered.connect(self._figado_rm_do_ativo)
        menu_fig.addAction(a_fig)
        a_ach3 = QAction("Achados de IA (revisar, confirmar, descartar)…", self)
        a_ach3.triggered.connect(self.abrir_achados)
        menu_fig.addAction(a_ach3)
        fig = self._act("figado_rm.auto", "Gordura e ferro hepáticos na RM (IA)", self.figado_rm_botao)
        fig.setIcon(icon("measure"))
        fig.setIconText("Fígado")
        self._button(tb, fig, menu_fig, app="figado_rm")
        # órgãos abdominais (0.99.32, pedido dele: também no botão Aplicações)
        menu_abd = self._menu()
        a_abd = QAction("Segmentar órgãos abdominais desta série (IA)…", self)
        a_abd.triggered.connect(lambda: self.segmentar_orgaos(self.active))
        menu_abd.addAction(a_abd)
        a_tar = QAction("Tarefas de IA (andamento e cancelar)…", self)
        a_tar.triggered.connect(self.abrir_tarefas_ia)
        menu_abd.addAction(a_tar)
        abd = self._act("abdome.auto", "Segmentar órgãos abdominais (IA)",
                        lambda: self.segmentar_orgaos(self.active))
        abd.setIcon(icon("measure"))
        abd.setIconText("Órgãos")
        self._button(tb, abd, menu_abd, app="abdome")
        # difusão (0.99.37, pedido dele: em todas as RM, não só na mama)
        dwi = self._act("difusao.abrir", "Difusão: ADC, DWI sintética e ADC na ROI", self.abrir_difusao)
        dwi.setIcon(icon("measure"))
        dwi.setIconText("Difusão")
        self._button(tb, dwi, None, app="difusao")
        self._montar_bloco_de_aplicacoes(tb)
        self._button(tb, self._plain("Mais", "more", "Mais opções"), more, instant=True)

        # barra do MPR (slab)
        self.mpr_bar = QToolBar()
        self.mpr_bar.setStyleSheet("QToolBar{background:#1a2530;color:#ddd;spacing:6px}"
                                   "QLabel{color:#ddd}")
        self.mpr_bar.addWidget(QLabel("  MPR — espessura (slab):"))
        self.slab_combo = QComboBox()
        for mm in SLAB_CHOICES:
            self.slab_combo.addItem("fino" if mm == 0 else f"{mm} mm", mm)
        self.mode_combo = QComboBox()
        for k, name in SLAB_MODES.items():
            self.mode_combo.addItem(name, k)
        self.slab_all = QAction("Aplicar aos 3 planos", self, checkable=True, checked=True)
        self.slab_combo.currentIndexChanged.connect(self._apply_slab)
        self.mode_combo.currentIndexChanged.connect(self._apply_slab)
        self.mpr_bar.addWidget(self.slab_combo)
        self.mpr_bar.addWidget(QLabel(" modo:"))
        self.mpr_bar.addWidget(self.mode_combo)
        self.mpr_bar.addAction(self.slab_all)
        self.mpr_info = QLabel("")
        self.mpr_bar.addWidget(self.mpr_info)
        self.mpr_bar.setVisible(False)
        from ipe.ui.viewer.render3d_view import Render3DBar
        self.render3d_bar = Render3DBar(self)

        # barra da fusão
        from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QSlider
        self.fusion_bar = QToolBar()
        self.fusion_bar.setStyleSheet("QToolBar{background:#2a2018;color:#ddd;spacing:6px}QLabel{color:#ddd}"
                                      "QCheckBox{color:#ddd}")
        self.fusion_label = QLabel("  Fusão")
        self.fusion_bar.addWidget(self.fusion_label)
        self.fusion_bar.addWidget(QLabel("  opacidade:"))
        self.fusion_alpha = QSlider(Qt.Horizontal)
        self.fusion_alpha.setRange(0, 100)
        self.fusion_alpha.setFixedWidth(140)
        self.fusion_alpha.valueChanged.connect(lambda v: self._fusion_set(alpha=v / 100))
        self.fusion_bar.addWidget(self.fusion_alpha)
        self.fusion_bar.addWidget(QLabel(" cor:"))
        self.fusion_cmap = QComboBox()
        from ipe.imaging import colormaps as CM
        for k in ("hot", "pet", "rainbow", "gold", "hotmetal", "jet", "thallium", "spectrum"):
            self.fusion_cmap.addItem(CM.name(k), k)
        self.fusion_cmap.activated.connect(lambda _i: self._fusion_set(cmap=self.fusion_cmap.currentData()))
        self.fusion_bar.addWidget(self.fusion_cmap)
        self.fusion_bar.addWidget(QLabel(" mín:"))
        self.fusion_lo = QDoubleSpinBox(decimals=2, minimum=-1e6, maximum=1e7)
        self.fusion_lo.editingFinished.connect(lambda: self._fusion_set(lo=self.fusion_lo.value()))
        self.fusion_bar.addWidget(self.fusion_lo)
        self.fusion_bar.addWidget(QLabel(" máx:"))
        self.fusion_hi = QDoubleSpinBox(decimals=2, minimum=-1e6, maximum=1e7)
        self.fusion_hi.editingFinished.connect(lambda: self._fusion_set(hi=self.fusion_hi.value()))
        self.fusion_bar.addWidget(self.fusion_hi)
        self.fusion_hide = QCheckBox("ocultar abaixo do mínimo")
        self.fusion_hide.toggled.connect(lambda on: self._fusion_set(hide_below=on))
        self.fusion_bar.addWidget(self.fusion_hide)
        a_all = QAction("Todos os quadros", self)
        a_all.triggered.connect(self.fusion_to_all)
        self.fusion_bar.addAction(a_all)
        a_rm = QAction("Remover", self)
        a_rm.triggered.connect(lambda: self.remove_fusion(self.active))
        self.fusion_bar.addAction(a_rm)
        self.fusion_bar.setVisible(False)

        # barra da mamografia (protocolo por etapas, quadrantes, lupa)
        from ipe.ui.viewer.mammo_view import MgBar
        self._act("mg.next", "Mamografia: próxima etapa do protocolo", lambda: self.mg_next(1))
        self._act("mg.prev", "Mamografia: etapa anterior do protocolo", lambda: self.mg_next(-1))
        self._act("phase.next", "Dinâmica: próxima fase", lambda: self.fase_passo(1))
        self._act("phase.prev", "Dinâmica: fase anterior", lambda: self.fase_passo(-1))
        self._act("mg.quad_next", "Zoom por quadrante: próximo quadrante", lambda: self.mg_quadrant_cycle(self.active, 1))
        self._act("mg.quad_prev", "Zoom por quadrante: quadrante anterior", lambda: self.mg_quadrant_cycle(self.active, -1))
        self._act("mg.tomo", "Mamografia: pular entre 2D e tomossíntese", lambda: self.mg_toggle_tomo())
        self._act("mg.cem", "Mamografia contrastada: baixa energia / recombinada", lambda: self.mg_toggle_cem())
        self._act("mg.implant", "Mamografia: corrigir o implante",
                  lambda: self.mg_set_implant(not getattr(self, "mg_implant", False)))
        self._act("mg.slab", "Tomossíntese: próxima espessura", lambda: self.mg_set_slab(-1))
        self._act("mg.enquadrar", "Mamografia: enquadrar a mama no quadro", lambda: self.mg_enquadrar())
        # Os atalhos se aplicam **depois** da última ação criada. Até a 0.65 esta chamada ficava
        # no meio da montagem da barra, antes do bloco da mamografia: as teclas de mamografia
        # nasciam mortas e só passavam a funcionar depois que ele abrisse Preferências e
        # salvasse (é dali que vem a única outra chamada de `apply_shortcuts`). Com a lista de
        # atalhos zerada, as três teclas que sobraram são justamente deste bloco.
        self.apply_shortcuts()
        self.refresh_tool_badges()
        self.mg_bar = MgBar(self)
        from ipe.ui.viewer.etapas import EtapasBar
        self.etapas_bar = EtapasBar(self)
        return tb

    def _fill_cmap_menu(self) -> None:
        m = self.cmap_menu
        m.clear()
        vp = self.active
        if vp is None:
            return
        vp.add_colormap_actions(m, lembrar=True)
        m.addSeparator()
        a = QAction("Aplicar a cor do quadro ativo a todos os quadros", m)
        a.triggered.connect(self.colormap_to_all)
        m.addAction(a)

    def orientation_to_all(self) -> None:
        vp = self.active
        if vp is None:
            return
        st = vp.state
        for v in self._shown():
            if v is not vp:
                v.set_orientation(st.rot, st.flip_h, st.flip_v)

    def colormap_to_all(self) -> None:
        vp = self.active
        if vp is None:
            return
        for v in self._shown():
            if v is not vp and v._img is not None and not v._img.is_color:
                v.state.cmap = vp.state.cmap
                v._qimage_key = None
                v.update()

    def _fill_preset_menu(self, menu: QMenu) -> None:
        menu.clear()
        vp = self.active
        js = vp.janelas_do_arquivo() if vp is not None else ()
        if js:
            menu.addAction("Do arquivo (Switch WL)").setEnabled(False)
            for i, (nome, w, l) in enumerate(js):
                a = menu.addAction(f"   {nome}  (W {w:g} / L {l:g})")
                a.triggered.connect(lambda _=False, k=i: self._on_active(lambda v: v.usar_janela_do_arquivo(k)))
            menu.addSeparator()
        presets = vp.presets_da_janela() if vp is not None else self.settings.get("viewer.wl_presets", {})
        for key, (name, w, l) in sorted(presets.items()):
            if not name:
                continue
            a = menu.addAction(f"{name}   (W {w:g} / L {l:g})")
            a.setShortcut(QKeySequence(key))
            a.triggered.connect(lambda _=False, kk=key: self._on_active(lambda v: v.apply_preset(kk)))
        menu.addSeparator()
        a = menu.addAction("Automático / do arquivo")
        a.setShortcut(QKeySequence("0"))
        a.triggered.connect(lambda: self._on_active(
            lambda v: (setattr(v.state, "window_set", False), v._load_current(), v.update())))
        menu.addSeparator()
        menu.addAction("Digitar a janela…").triggered.connect(lambda: self._on_active(lambda v: v.digitar_janela()))
        menu.addAction("Guardar a janela atual como preset…").triggered.connect(
            lambda: self._on_active(lambda v: v.guardar_janela_atual()))

    def _fill_annotation_list(self) -> None:
        m = self.annot_list_menu
        m.clear()
        v = self.active
        items = v.annotation_summary() if v is not None else []
        if not items:
            m.addAction("Nenhuma medida nesta série").setEnabled(False)
        for i, text in items[:60]:
            a = m.addAction(text)
            a.triggered.connect(lambda _=False, k=i, vv=v: vv.go_to(k))

    def _delete_series_annotations(self, vp: Viewport) -> None:
        n = len([a for a in vp.annotations if a.done])
        if n and QMessageBox.question(self, "Apagar medidas",
                                      f"Apagar as {n} medidas desta série?") == QMessageBox.Yes:
            vp.delete_series_annotations()

    def _ask_image(self, vp: Viewport) -> None:
        if not vp.frames:
            return
        from PySide6.QtWidgets import QInputDialog
        n, ok = QInputDialog.getInt(self, "Ir para imagem", f"Imagem (1–{len(vp.frames)}):",
                                    vp.index + 1, 1, len(vp.frames))
        if ok:
            vp.go_to(n - 1)

    def _on_active(self, fn) -> None:
        if self.active is not None:
            fn(self.active)

    def set_left_tool(self, tool: str, propagar: bool = True) -> None:
        self.left_tool = tool
        if tool in self.tool_actions:
            self.tool_actions[tool].setChecked(True)
        if tool in MEASURE_TOOLS and hasattr(self, "measure_button"):
            self.measure_button.setDefaultAction(self.tool_actions[tool])
            self.measure_button.setMenu(self.measure_menu)
        for v in self.viewports:
            v.left_tool = tool
            v.update()
        if propagar:
            for t in self.irmaos():
                t.set_left_tool(tool, propagar=False)

    def set_meeting(self, label: str, bar: QWidget | None = None) -> None:
        """Modo reunião: dados do paciente ocultos e travados; o nome amigável aparece no lugar."""
        self.case_label = label
        self.anon_action.setChecked(True)
        self.anon_action.setEnabled(False)
        self.set_anonymize(True)
        if bar is not None:
            self._root_layout.insertWidget(0, bar)
            bar.show()

    # ------------------------------------------------------------ anotações e cópia (0.99.9)
    def set_anotacoes(self, nivel: str) -> None:
        """Troca o nível de anotação de **todos** os quadros e guarda a escolha."""
        from ipe.ui.viewer import anotacoes as AN
        if nivel not in AN.NOME_DO_NIVEL:
            return
        self.settings.set("viewer.anotacoes_nivel", nivel)
        try:
            self.settings.save()
        except Exception:  # noqa: BLE001 - não gravar não pode impedir de trocar na tela
            log.debug("não gravei o nível de anotação", exc_info=True)
        self.anotacoes_mudaram.emit(nivel)
        self.reflect_anotacoes()
        for v in self.viewports:
            v.update()
        self.status_message.emit(f"Anotações: {AN.NOME_DO_NIVEL[nivel]}")

    def proximo_nivel_de_anotacao(self) -> None:
        from ipe.ui.viewer import anotacoes as AN
        self.set_anotacoes(AN.proximo(AN.nivel_atual(self.settings)))

    def reflect_anotacoes(self) -> None:
        """Botão e menu dizem o nível em uso (também quando outra janela o trocou)."""
        from ipe.ui.viewer import anotacoes as AN
        if not hasattr(self, "anot_actions"):
            return
        nivel = AN.nivel_atual(self.settings)
        for chave, a in self.anot_actions.items():
            a.setChecked(chave == nivel)
        self.anot_button_action.setText(f"Anot.: {AN.NOME_DO_NIVEL[nivel]}")
        for v in self.viewports:
            v.update()

    def copiar_quadro(self) -> bool:
        """Ctrl+C: o quadro ativo vai para a área de transferência como está na tela."""
        vp = self.active
        if vp is None or not vp.frames:
            self.status_message.emit("Nada para copiar: clique num quadro com imagem.")
            return False
        try:
            tam = vp.copiar_para_area_de_transferencia()
        except Exception:  # noqa: BLE001
            log.exception("copiar o quadro")
            self.status_message.emit("Não consegui copiar a imagem do quadro.")
            return False
        if tam is None:
            self.status_message.emit("Nada para copiar: o quadro ainda não tem imagem.")
            return False
        self.status_message.emit(f"Imagem copiada ({tam[0]} × {tam[1]} px) — cole com Ctrl+V.")
        return True

    def _encher_menu_de_perfis(self) -> None:
        from PySide6.QtGui import QActionGroup
        from ipe.core import mascara as MK
        m = self.perfil_menu
        m.clear()
        cab = m.addAction("Ao ocultar, mostrar:")
        cab.setEnabled(False)
        g = QActionGroup(m)
        atual = MK.perfil_de(self.settings)
        for chave, nome in MK.PERFIS.items():
            a = m.addAction(nome)
            a.setCheckable(True)
            a.setChecked(chave == atual)
            a.setEnabled(not self.case_label)
            g.addAction(a)
            a.triggered.connect(lambda _=False, k=chave: self.set_perfil_de_ocultacao(k))
        m.addSeparator()
        nota = m.addAction("Ocultar na tela não muda os arquivos: o que sai passa pela anonimização.")
        nota.setEnabled(False)

    def set_perfil_de_ocultacao(self, perfil: str, ligar: bool = True) -> None:
        """Escolhe o perfil (vale para todas as abas e para a lista do banco) e liga o Ocultar."""
        from ipe.core import mascara as MK
        self.settings.set(MK.CHAVE, MK.normalizar(perfil))
        if ligar and not self.anonymize:
            self.anon_action.setChecked(True)
        self.set_anonymize(self.anonymize)
        self.perfil_mudou.emit(MK.normalizar(perfil))

    def set_anonymize(self, on: bool) -> None:
        if self.case_label and not on:
            return                      # reunião: não dá para mostrar os dados
        self.anonymize = on
        for v in self.viewports:
            v.anonymize = on
            v.case_label = self.case_label
            v.update()
        self._fill_strip()
        w = self.parentWidget()
        while w is not None and not isinstance(w, QTabWidget):
            w = w.parentWidget()
        if w is not None and w.indexOf(self) >= 0:
            w.setTabText(w.indexOf(self), self.title()[:40])
            w.setTabToolTip(w.indexOf(self), self.title())
        elif self.window() is not None and self.window() is not self:
            self.window().setWindowTitle(self.title())

    # ================================================================ séries
    # ------------------------------------------------------------ regras de dinâmico
    def aplicar_regras_dinamicas(self) -> list[str]:
        """Junta e separa séries segundo as regras confirmadas nas Preferências.

        **Juntar** grava o grupo no banco (é o mesmo grupo que ele faria na mão). **Separar** é
        só na tela: um grupo virtual, de id negativo, com as fases montadas na hora — nada muda
        no banco nem nos arquivos, e “Desfazer” devolve a série inteira.
        """
        from ipe.imaging import dinamicas as D
        from ipe.imaging.dynamic import separar_fases
        regras = D.carregar(self.settings)
        if not regras:
            return []
        feitos: list[str] = []
        minhas = [s for s in self.series if s.study_uid == self.study_uid]
        agrupadas = {u for g in self.groups.values() for u in g["series_uids"]}
        for nome, uids in D.para_juntar(regras, minhas, self.study_uid):
            if any(u in agrupadas for u in uids):
                continue
            ordenadas = [s.series_uid for s in minhas if s.series_uid in set(uids)]
            gid = self.repo.save_series_group(self.study_uid, ordenadas, nome)
            self.groups[gid] = {"id": gid, "study_uid": self.study_uid, "name": nome,
                                "kind": "dynamic", "series_uids": ordenadas}
            agrupadas |= set(ordenadas)
            feitos.append(f"juntei {len(ordenadas)} séries em {nome}")
        for uid in D.para_separar(regras, minhas, self.study_uid):
            if uid in agrupadas or uid in self._nao_separar:
                continue
            s = self._series_row(uid)
            frames = build_frames(self.repo.instances_for_series(uid), uid)
            fases = separar_fases(frames) if frames else None
            if not fases or len(fases) < 2:
                continue
            gid = min([0] + [k for k in self.groups if k < 0]) - 1   # ids negativos = virtuais
            nome = f"Fases de {s.description[:22]} ({len(fases)})" if s else f"Fases ({len(fases)})"
            self.groups[gid] = {"id": gid, "study_uid": self.study_uid, "name": nome,
                                "kind": "dynamic", "series_uids": [uid], "split": True,
                                "fases": fases,
                                "rotulos": [f"Fase {i + 1}" for i in range(len(fases))]}
            agrupadas.add(uid)
            feitos.append(f"separei {nome}, só na tela")
        return feitos

    def _series_row(self, uid: str) -> SeriesRow | None:
        return next((s for s in self.series if s.series_uid == uid), None)

    def recarregar_series(self) -> None:
        """A lista de séries do banco mudou (oculta, apagada ou dinâmica nova): refazer a tira."""
        from ipe.importer.thumbnails import miniaturas_que_faltam
        for u in self.study_order:
            miniaturas_que_faltam(self.repo, u)
        self.groups = {g["id"]: g for u in self.study_order for g in self.repo.series_groups(u)}
        self.series = _image_series(self.repo.series_for_study(self.study_uid) + [
            s for u in self.study_order[1:] for s in self.repo.series_for_study(u)])
        vivas = {s.series_uid for s in self.series}
        for vp in self.viewports:
            uid = getattr(vp, "series_uid", "")
            if uid and ":" not in uid and uid not in vivas:
                vp.empty_note = "Esta série não está mais no exame\n(foi ocultada ou apagada)"
                vp.set_series("", [], "", vp.study_info or {})
        self._fill_strip()

    TIRA_MODOS = {"mamografia": "Só na mamografia", "sempre": "Sempre que o exame abre repartido",
                  "nunca": "Nunca (a tira aparece em todas as telas)"}

    def _ajustar_tira(self) -> None:
        """Com o exame repartido, a tira fica **só na primeira tela**.

        Com dois monitores a tira ficava na borda de dentro do segundo: bem no meio das duas mamas,
        cortando a imagem justamente onde o médico compara uma com a outra. Com 3 ou 4 telas é a
        mesma coisa, multiplicada. O protocolo é quem escolhe as séries nessas telas, então a tira
        ali não serve para nada — e atrapalha.
        """
        if self.monitor_idx <= 0:
            return
        modo = str(self.settings.get("viewer.tira_repartida", "mamografia") or "mamografia")
        if modo == "nunca":
            return
        if modo == "mamografia" and self.mg_monitor is None:
            return
        self.strip_col.hide()
        acao = getattr(self, "strip_action", None)
        if acao is not None:
            acao.setChecked(False)          # o botão do menu mostra o estado e desfaz

    def _fill_strip(self) -> None:
        self.update_modality_buttons()
        current = self.strip.currentItem().data(Qt.UserRole) if self.strip.currentItem() else None
        counts = self.repo.annotation_counts([s.series_uid for s in self.series])
        from ipe.ui.tabelas import esvaziar_lista
        esvaziar_lista(self.strip)              # clear() derrubava o programa às vezes (0.79)
        hidden = 0
        na_tira = [u for u in self.study_order
                   if getattr(self, "estudos_na_tira", None) is None or u in self.estudos_na_tira]
        multi = len(na_tira) > 1 or na_tira != [self.study_uid]
        for st_uid in na_tira:
            info = self.study_infos.get(st_uid, {})
            if multi:
                head = QListWidgetItem(("Atual" if st_uid == self.study_uid else "Anterior")
                                       + f"\n{fmt_date(info.get('study_date', ''))}")
                head.setFlags(Qt.NoItemFlags)
                f = QFont()
                f.setBold(True)
                head.setFont(f)
                head.setForeground(QBrush(QColor(255, 210, 120)))
                head.setSizeHint(QSize(112, 34))
                self.strip.addItem(head)
            for g in self.groups.values():
                if g["study_uid"] != st_uid:
                    continue
                self.strip.addItem(self._group_item(g))
                for sub in self._itens_das_fases(g):
                    self.strip.addItem(sub)
            n_keys = sum(1 for k in self._study_keys(st_uid))
            if n_keys:
                it = QListWidgetItem(f"★ Chave ({n_keys})")
                it.setToolTip("Imagens-chave deste estudo")
                it.setData(Qt.UserRole, f"key:{st_uid}")
                it.setForeground(QBrush(QColor(255, 210, 0)))
                it.setSizeHint(QSize(112, 30))
                self.strip.addItem(it)
            for s in self.series:
                if s.study_uid != st_uid:
                    continue
                if not self._series_visible(s):
                    hidden += 1
                    continue
                n_ann = counts.get(s.series_uid, 0)
                label = f"{s.series_number} {s.modality}\n{s.description[:22]}\n{s.num_images} im"
                item = QListWidgetItem(label)
                pm = QPixmap()
                if s.thumbnail:
                    pm.loadFromData(s.thumbnail, "PNG")
                if n_ann:
                    pm = with_badge(pm, f"✎ {n_ann}")
                    item.setToolTip(f"{n_ann} imagem(ns) com medida ou anotação — "
                                    "botão direito para ir direto a elas")
                if not pm.isNull():
                    item.setIcon(QIcon(pm))
                item.setData(Qt.UserRole, s.series_uid)
                item.setSizeHint(QSize(112, 128))
                self.strip.addItem(item)
                if (s.modality or "").upper() == "NM":
                    for sub in NMV.strip_items(self, s.series_uid):
                        self.strip.addItem(sub)
        self._add_pending_series()
        if hidden or (self.series_filter and self.show_all_series):
            it = QListWidgetItem(f"Mostrar todas as séries\n({hidden} ocultas)" if hidden
                                 else "Mostrar só as séries escolhidas")
            it.setData(Qt.UserRole, "action:toggle_all")
            it.setForeground(QBrush(QColor(120, 190, 255)))
            it.setSizeHint(QSize(112, 40))
            self.strip.addItem(it)
        if current:
            for i in range(self.strip.count()):
                if self.strip.item(i).data(Qt.UserRole) == current:
                    self.strip.setCurrentRow(i)
                    break

    # ------------------------------------------------------------ exames do paciente na tira
    def _encher_filtro_de_exames(self) -> None:
        """Monta a escolha de exames em cima da tira (0.99.11). Some quando não há anteriores."""
        try:
            outros = self.repo.other_studies_same_patient(self.study_uid)
        except Exception:  # noqa: BLE001 — repositório remoto fora do ar: a tira segue sem a escolha
            log.debug("anteriores para a tira", exc_info=True)
            outros = []
        outros = sorted(outros, key=lambda r: r.study_date or "", reverse=True)
        self._outros_exames = outros
        c = self.filtro_exames
        c.blockSignals(True)
        c.clear()
        if outros:
            info = self.study_infos.get(self.study_uid, {}) or self.study_info
            c.addItem(f"Este exame  {fmt_date(info.get('study_date', ''))}", "atual")
            for r in outros:
                marca = "✓ " if r.study_uid in self.study_order else ""
                c.addItem(f"{marca}{fmt_date(r.study_date)}  {r.modalities}", r.study_uid)
                c.setItemData(c.count() - 1, f"{fmt_date(r.study_date)}  {r.modalities}  {r.description}",
                              Qt.ToolTipRole)
            c.addItem(f"Todos os exames ({len(outros) + 1})", "todos")
            alvo = self.estudos_na_tira
            if alvo is None:
                chave = "todos" if len(self.study_order) > 1 else "atual"
            elif alvo == {self.study_uid}:
                chave = "atual"
            else:
                chave = next(iter(alvo - {self.study_uid}), "atual")
            c.setCurrentIndex(max(0, c.findData(chave)))
        c.blockSignals(False)
        c.setVisible(bool(outros))

    def _filtro_de_exames_escolhido(self, _indice: int = 0) -> None:
        self.mostrar_exames_na_tira(self.filtro_exames.currentData())

    def mostrar_exames_na_tira(self, escolha: str) -> None:
        """"atual", "todos" ou o StudyInstanceUID de um anterior.

        O anterior escolhido vem para a aba (como no botão Anteriores) e a tira passa a mostrar as
        séries dele; os quadros não mudam — a série vai para o quadro pelo clique ou arrastando."""
        if escolha == "atual":
            self.estudos_na_tira = {self.study_uid}
        elif escolha == "todos":
            for r in self._outros_exames:
                if r.study_uid not in self.study_order:
                    self.add_study(r.study_uid, colocar=False)
            self.estudos_na_tira = None
        elif escolha:
            if escolha not in self.study_order:
                self.add_study(escolha, colocar=False)
            if escolha not in self.study_order:          # não deu para trazer (download recusado)
                self._encher_filtro_de_exames()
                return
            self.estudos_na_tira = {escolha}
        self._fill_strip()
        self._encher_filtro_de_exames()

    def _pending_job(self):
        """Download em andamento de algum estudo aberto aqui."""
        net = getattr(self.window(), "net", None)
        if net is None or not hasattr(net, "job_for_study"):
            return None
        for uid in self.study_order:
            job = net.job_for_study(uid)
            if job is not None:
                return job
        return None

    def _add_pending_series(self) -> None:
        """Séries que ainda estão vindo aparecem na tira, mais claras, como no Weasis."""
        job = self._pending_job()
        if job is None or not job.series_plan:
            return
        ja_tem = {s.series_uid for s in self.series}
        for s in job.series_plan:
            uid = s.get("series_uid", "")
            if not uid or uid in ja_tem:
                continue
            pulada = uid in job.skip
            baixando = uid == job.current_series
            estado = "não vai baixar" if pulada else ("baixando agora" if baixando else "na fila")
            item = QListWidgetItem(f"{s.get('series_number', '')} {s.get('modality', '')}\n"
                                   f"{(s.get('description') or '')[:22]}\n"
                                   f"{s.get('num_images') or '?'} im · {estado}")
            item.setData(Qt.UserRole, f"pending:{uid}")
            item.setForeground(QBrush(QColor(110, 110, 110) if pulada else QColor(150, 175, 205)))
            item.setToolTip("Esta série ainda não chegou" if not pulada else
                            "Você mandou não baixar esta série")
            item.setSizeHint(QSize(112, 128))
            self.strip.addItem(item)

    def cancel_download(self) -> None:
        """Para o download deste exame; o que já chegou fica."""
        net = getattr(self.window(), "net", None)
        job = self._pending_job()
        if net is not None and job is not None:
            net.cancel(job)
            self.status_message.emit("Download cancelado; o que já chegou continua aqui.")
            self._fill_strip()

    def skip_pending_series(self, series_uid: str) -> None:
        """Não baixar uma série que ainda está na fila."""
        net = getattr(self.window(), "net", None)
        job = self._pending_job()
        if net is None or job is None:
            return
        if net.skip_series(job, series_uid):
            self.status_message.emit("Esta série não vai ser baixada.")
        else:
            self.status_message.emit("Essa série já chegou ou está chegando agora.")
        self._fill_strip()

    def show_series(self, uids: list[str]) -> None:
        """Estudo já aberto: põe estas séries nos quadros (e restringe a tira a elas)."""
        self.series_filter = list(uids)
        self.show_all_series = False
        self._fill_strip()
        self.set_layout(*self._layout_for(len(uids)))
        for vp, uid in zip(self.viewports, uids):
            self.load_series_into(vp, uid)
        if self.viewports:
            self._activate(self.viewports[0])

    def _series_visible(self, s: SeriesRow) -> bool:
        if self.show_all_series or not self.series_filter or s.study_uid != self.study_uid:
            return True
        grouped = {u for g in self.groups.values() for u in g["series_uids"]}
        return s.series_uid in self.series_filter or (s.series_uid in grouped and any(
            f"group:{gid}" in self.series_filter for gid in self.groups))

    def _itens_das_fases(self, g: dict) -> list[QListWidgetItem]:
        """Série separada em fases: cada fase vira uma miniatura própria na tira."""
        if not g.get("fases"):
            return []
        first = self._series_row(g["series_uids"][0])
        pm = QPixmap()
        if first is not None and first.thumbnail:
            pm.loadFromData(first.thumbnail, "PNG")
        out = []
        for i, fs in enumerate(g["fases"]):
            it = QListWidgetItem(f"Fase {i + 1}/{len(g['fases'])}\n{len(fs)} im")
            if not pm.isNull():
                it.setIcon(QIcon(pm))
            it.setData(Qt.UserRole, f"fase:{g['id']}:{i}")
            desc = first.description if first else ""
            it.setToolTip(f"Fase separada da série {desc} — só na tela; "
                          "a série no banco continua inteira.")
            it.setSizeHint(QSize(112, 112))
            out.append(it)
        return out

    def _group_item(self, g: dict) -> QListWidgetItem:
        n = len(g["series_uids"])
        first = self._series_row(g["series_uids"][0]) if g["series_uids"] else None
        imgs = first.num_images if first else 0
        it = QListWidgetItem(f"▦ {g['name']}\n{n} fases × {imgs} im")
        pm = QPixmap()
        if first is not None and first.thumbnail:
            pm.loadFromData(first.thumbnail, "PNG")
        pm = with_badge(pm, f"{n} fases", QColor(255, 180, 0))
        it.setIcon(QIcon(pm))
        it.setData(Qt.UserRole, f"group:{g['id']}")
        it.setToolTip("Série dinâmica montada a partir de várias séries. No quadro: ← → trocam a fase; "
                      "clique em “Fase x/y” para subtração e cine das fases.")
        it.setSizeHint(QSize(112, 128))
        return it

    def _refresh_annotation_marks(self) -> None:
        self._fill_strip()

    # ================================================================ exportar
    def export_dialog(self) -> None:
        from ipe.exporter.core import ExportItem
        from ipe.ui.export_dialog import ExportDialog
        vp = self.active or (self.viewports[0] if self.viewports else None)
        scopes = []
        window = None

        if vp is not None and isinstance(vp.mpr_plane, ObliquePlane):
            pl = vp.mpr_plane
            cur = self.save_reconstruction(vp, current_only=True)
            if cur is not None:
                scopes.append(("Imagem reconstruída do quadro ativo (oblíquo)",
                               [ExportItem(vp.study_uid, [cur[0]], [(cur[1][0], 0)])]))
                if pl.n * pl._w * pl._hgt <= 40e6:
                    whole = self.save_reconstruction(vp)
                    if whole is not None:
                        scopes.append((f"Reconstrução inteira (oblíquo, {len(whole[1])} imagens)",
                                       [ExportItem(vp.study_uid, [whole[0]])]))
                window = (vp.state.width, vp.state.level)
        elif vp is not None and vp.mpr_plane is not None:
            saved = self.save_reconstruction(vp)
            if saved is not None:
                series_uid, sops = saved
                su = vp.study_uid
                scopes.append(("Imagem reconstruída do quadro ativo", [ExportItem(su, [series_uid], [(sops[vp.index], 0)])]))
                scopes.append((f"Reconstrução inteira ({vp.mpr_plane.name}, {len(sops)} imagens)",
                               [ExportItem(su, [series_uid])]))
                if vp._img is not None:
                    window = (vp.state.width, vp.state.level)
        f = vp.current_frame() if vp is not None else None
        if f is not None and not f.is_virtual and f.series_uid:
            su = (self.repo.series_info(f.series_uid) or {}).get("study_uid", self.study_uid)
            scopes.append(("Imagem do quadro ativo", [ExportItem(su, [f.series_uid], [(f.sop_uid, f.frame_index)])]))
            if vp.phases:
                uids = [ph[0].series_uid for ph in vp.phases if ph and ph[0].series_uid]
                scopes.append((f"Série do quadro ativo (todas as {len(uids)} fases)", [ExportItem(su, uids)]))
            else:
                scopes.append(("Série do quadro ativo", [ExportItem(su, [f.series_uid])]))
            if vp._img is not None and not vp._img.is_color:
                window = (vp.state.width, vp.state.level)
        keys = self.repo.key_images(self.study_uid)
        if keys:
            scopes.append((f"Imagens-chave do exame ({len(keys)})",
                           [ExportItem(self.study_uid, None, [(k["sop_uid"], k["frame_index"]) for k in keys])]))
        scopes.append(("Exame inteiro", [ExportItem(self.study_uid)]))
        if len(self.study_order) > 1:
            scopes.append((f"Todos os exames desta aba ({len(self.study_order)})",
                           [ExportItem(u) for u in self.study_order]))
        cmap = vp.state.cmap if vp is not None and vp._img is not None and not vp._img.is_color else ""
        ExportDialog(self.repo, self.settings, scopes, self, window=window, force_anonymize=self.anonymize,
                     cmap=cmap).exec()

    # ================================================================ filme
    # ================================================================ registro automático
    def _volume_of(self, vp: Viewport, title: str):
        uid = self._source_series(vp)
        if uid is None:
            return None
        frames = build_frames(self.repo.instances_for_series(uid), uid)
        dlg = QProgressDialog(f"Montando volume ({title})…", "Cancelar", 0, len(frames), self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(300)

        def progress(done: int, total: int) -> bool:
            if done % 8 == 0 or done == total:
                dlg.setValue(done)
                QApplication.processEvents()
            return not dlg.wasCanceled()
        try:
            return build_volume(frames, self.cache, progress)
        except VolumeError as e:
            QMessageBox.information(self, "Registro", f"{title}: {e}")
            return None
        finally:
            dlg.close()

    def conferir_registro(self, modo: str | None):
        """Põe o outro exame sobre o quadro ativo para conferir o registro (0.99.44, como o MITK): xadrez,
        cortina que segue o mouse, diferença ou mistura — em cinza, cada um com a sua janela. Usa a matriz do
        registro rígido guardado; a série já gravada no plano deste (mesmo Frame of Reference) entra sem ela."""
        import numpy as np
        a = self.active
        if a is None:
            return None
        if modo is None:
            if a.fusion is not None and getattr(a.fusion, "modo", "cor") != "cor":
                self.remove_fusion(a)
            return None
        if a.fusion is not None and getattr(a.fusion, "matriz_de", None) is not None:
            a.fusion.modo = modo                 # já está conferindo: só troca o modo
            a.fusion.changed()
            a._fusion_cache = None
            a.update()
            return a.fusion
        others = [v for v in self.hub.viewports(self) if v is not a and v.study_uid and v.study_uid != a.study_uid
                  and self._source_series(v) is not None]
        if not others:
            QMessageBox.information(self, "Conferir o registro", "Abra o outro exame num quadro ao lado (botão "
                                    "Anteriores) e deixe ativo o quadro do exame atual.")
            return None
        b = others[0]
        uid_b = self._source_series(b)
        meta_b = self.repo.series_meta(uid_b) or {}
        mesma_ref = bool(a.for_uid) and meta_b.get("frame_of_reference") == a.for_uid
        M = None if mesma_ref else self.repo.get_registration_matriz(a.study_uid, b.study_uid)
        fu = self.set_fusion(a, uid_b)
        if fu is None:
            return None
        fu.matriz = None if M is None else np.asarray(M, float)
        fu.matriz_de = (a.study_uid, b.study_uid)
        fu.modo = modo
        fu.changed()
        a._fusion_cache = None
        a.update()
        if M is None and not mesma_ref:
            self.status_message.emit("Sem registro rígido guardado entre os dois exames: a conferência usa as "
                                     "coordenadas do paciente (rode o Alinhar automaticamente antes).")
        else:
            self.status_message.emit("Conferindo o registro: as bordas devem continuar sem degrau no xadrez e na "
                                     "cortina; na diferença, o que sobra claro é o que não alinhou.")
        return fu

    def auto_register(self) -> bool:
        """Alinha o quadro ativo com um quadro de outro exame (ex.: anterior) e liga os dois.

        0.99.38: registro **rígido** (rotação + translação, `imaging/registro_rigido.py`) no lugar da só
        translação. A sincronização continua pela translação do centro; quando o outro exame está girado
        (≥ 1°), o programa oferece gravá-lo **no plano deste** (série nova, mesma geometria e Frame of
        Reference), que então anda junto corte a corte."""
        a = self.active
        if a is None:
            return False
        others = [v for v in self.hub.viewports(self) if v is not a and v.study_uid and v.study_uid != a.study_uid
                  and self._source_series(v) is not None]
        if not others:
            QMessageBox.information(self, "Registro", "Abra o outro exame (ex.: o anterior) num quadro ao lado "
                                    "— botão Anteriores — e deixe ativo o quadro do exame atual.")
            return False
        b = others[0]
        va = self._volume_of(a, "exame ativo")
        vb = self._volume_of(b, "outro exame") if va is not None else None
        if va is None or vb is None:
            return False
        from ipe.imaging import registro_rigido as RR
        sa = self.repo.series_meta(self._source_series(a)) or {}
        sb = self.repo.series_meta(self._source_series(b)) or {}
        metrica = RR.metrica_para(sa.get("modality", ""), sb.get("modality", ""),
                                  sa.get("description", ""), sb.get("description", ""))
        prog = QProgressDialog("Registrando (rotação e translação)…", "Parar", 0, len(RR.NIVEIS), self)
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(300)

        def andar(feito, total, texto):
            prog.setLabelText(f"Registrando: {texto}…")
            prog.setValue(feito)
            QApplication.processEvents()
            return not prog.wasCanceled()
        try:
            r = RR.registrar(va, vb, metrica, progresso=andar, tempo_max=90.0)   # o botão Cancelar para antes
        except InterruptedError:
            self.status_message.emit("Registro interrompido.")
            return False
        finally:
            prog.close()
        t = r.translacao
        self.repo.save_registration(a.study_uid, b.study_uid, t, 0.0, method="rigido", matriz=r.M)
        self.ultimo_registro = (a.study_uid, b.study_uid, r)
        self.hub.unlink([a, b])
        self.hub.apply_saved(a, b)
        self.update_reference_lines()
        from ipe.core.i18n import tr
        rx, ry, rz = r.params[:3]
        rot = f"{rx:.1f}°, {ry:.1f}°, {rz:.1f}°"
        desl = f"{t[0]:.1f}, {t[1]:.1f}, {t[2]:.1f} mm"
        nome_m = tr("correlação") if r.metrica == "ncc" else tr("informação mútua")
        q = tr(r.qualidade())
        self.status_message.emit(f"Exames alinhados: rotação {rot}, deslocamento {desl} ({nome_m} "
                                 f"{r.valor_inicial:.2f} → {r.valor:.2f}, qualidade {q}). Os quadros agora rolam juntos.")
        if r.rotacao_total >= 1.0 and QMessageBox.question(
                self, "Registro",
                f"O outro exame está girado {r.rotacao_total:.1f}° em relação a este. Rolando juntos, os cortes "
                "não coincidem por inteiro.\n\nGravar o outro exame no plano deste (série nova no outro exame, "
                "com a geometria deste)? Aí os dois andam juntos corte a corte.") == QMessageBox.Yes:
            self.gravar_registrado(a, b, va, vb, r)
        return True

    def gravar_registrado(self, a, b, va, vb, r) -> str | None:
        """O exame do quadro `b` reamostrado na grade do quadro `a` (registro `r`), gravado e aberto em `b`."""
        from ipe.imaging import registro_rigido as RR
        from ipe.imaging import registro_saida as SAIDA
        db = getattr(self.repo, "db", None)
        storage = getattr(self, "storage_root", None)
        if db is None or storage is None:
            QMessageBox.information(self, "Registro", "Este banco não aceita série nova daqui.")
            return None
        prog = QProgressDialog("Reformatando no plano deste exame…", "Parar", 0, va.shape[0], self)
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(300)

        def andar(feito, total):
            prog.setMaximum(total)
            prog.setValue(feito)
            QApplication.processEvents()
            return not prog.wasCanceled()
        try:
            dados = RR.reformatar(vb, va, r.M, andar)
            ia = self.repo.instances_for_series(self._source_series(a))[0]["path"]
            ib = self.repo.instances_for_series(self._source_series(b))[0]["path"]
            info_a = self.repo.study_info(a.study_uid) or {}
            desc_b = (self.repo.series_meta(self._source_series(b)) or {}).get("description", "") or "série"
            data_a = str(info_a.get("study_date", "") or "")
            quando = f"{data_a[6:8]}/{data_a[4:6]}/{data_a[:4]}" if len(data_a) == 8 else data_a
            uid, _sops = SAIDA.gravar(db, storage, va, dados, ib, ia, f"{desc_b} · registrada em {quando}",
                                      r.M, andar)
        except InterruptedError:
            self.status_message.emit("Reformatação interrompida.")
            return None
        except Exception as e:  # noqa: BLE001
            log.exception("gravar o exame registrado")
            QMessageBox.warning(self, "Registro", f"Não deu para gravar: {e}")
            return None
        finally:
            prog.close()
        try:
            self.rescan(b.study_uid)
            self.load_series_into(b, uid, como_serie=True)
            # mesmo espaço agora: liga sem deslocamento (não "mantendo o desalinho de agora")
            self.hub.unlink([a, b])
            g = self.hub._free_group()
            self.hub.join(a, g)
            ma = self.hub.members[a]
            self.hub.join(b, g, geo_offset=ma.geo, rel_offset=ma.rel)
            try:
                self.hub._follow(a, b)
            except Exception:  # noqa: BLE001
                log.debug("seguir o quadro registrado", exc_info=True)
            self.update_reference_lines()
        except Exception:  # noqa: BLE001
            log.exception("abrir a série registrada")
        try:
            from ipe.central.client_repo import upload_if_client
            upload_if_client(self.repo, b.study_uid)
        except Exception:  # noqa: BLE001
            pass
        self.status_message.emit("O outro exame foi gravado no plano deste (série nova) e os dois andam juntos "
                                 "corte a corte.")
        return uid

    # ================================================================ medidas como SR
    def show_histogram(self, vp: Viewport | None = None) -> None:
        from ipe.ui.viewer.histogram import HistogramDialog
        vp = vp or self.active
        if vp is None or vp._img is None:
            return
        dlg = HistogramDialog(vp, self)
        self._histograms = [d for d in getattr(self, "_histograms", []) if d.isVisible()] + [dlg]
        dlg.show()

    def export_measures_table(self) -> None:
        """Todas as medidas dos exames abertos numa planilha (CSV que o Excel abre direto)."""
        from PySide6.QtWidgets import QFileDialog
        from ipe.exporter.measures_table import export_measures, rows_for_studies
        uids = list(self.study_order)
        rows = rows_for_studies(self.repo, uids, self.anonymize)
        if not rows:
            QMessageBox.information(self, "Medidas", "Não há medidas salvas neste exame.")
            return
        name = f"medidas_{(self.study_info.get('accession') or self.study_info.get('study_date') or 'exame')}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Exportar medidas", name, "Planilha CSV (*.csv)")
        if not path:
            return
        n = export_measures(self.repo, uids, path, self.anonymize)
        self.status_message.emit(f"{n} medida(s) exportadas para {path}")

    def save_measurements_sr(self) -> None:
        from ipe.exporter.sr import build_sr
        study = self.study_uid
        vp = self.active
        if vp is not None and vp.study_uid:
            study = vp.study_uid
        factors = {}
        for v in self.viewports:
            if v.suv_factor and v.series_uid and not v.series_uid.startswith(("mpr:", "key:", "group:")):
                factors[v.series_uid] = v.suv_factor
        try:
            ds, n = build_sr(self.repo, study, suv_factors=factors)
        except Exception as e:  # noqa: BLE001
            log.exception("SR")
            QMessageBox.warning(self, "DICOM SR", f"Não foi possível montar o SR:\n{e}")
            return
        if ds is None:
            QMessageBox.information(self, "DICOM SR", "Este exame não tem medidas salvas.")
            return
        box = QMessageBox(QMessageBox.Question, "DICOM SR",
                          f"{n} item(ns) de medida. O SR (relatório estruturado) abre em outros sistemas e "
                          "acompanha o exame ao enviar ao PACS ou exportar.", parent=self)
        b_db = box.addButton("Guardar no exame", QMessageBox.AcceptRole)
        b_file = box.addButton("Salvar arquivo…", QMessageBox.ActionRole)
        box.addButton("Cancelar", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is b_file:
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getSaveFileName(self, "Salvar SR", "medidas_sr.dcm", "DICOM (*.dcm)")
            if path:
                ds.save_as(path, enforce_file_format=True)
                self.status_message.emit(f"SR salvo em {path}")
        elif box.clickedButton() is b_db:
            import tempfile
            from pathlib import Path
            from ipe.importer.scanner import Importer
            storage = getattr(self, "storage_root", None)
            if storage is None:
                return
            tmp = Path(tempfile.mkdtemp(prefix="dv_sr_"))
            ds.save_as(tmp / "sr.dcm", enforce_file_format=True)
            Importer(self.repo.db, storage).import_paths([tmp])
            from ipe.central.client_repo import upload_if_client
            upload_if_client(self.repo, self.study_uid)
            self.status_message.emit("Medidas guardadas no exame como DICOM SR (série “Medidas (Ipe)”).")

    # ================================================================ reconstrução como série
    def save_reconstruction(self, vp: Viewport | None, notify: bool = False,
                            current_only: bool = False) -> tuple[str, list[str]] | None:
        """Grava a reconstrução do quadro (plano, slab e modo atuais) como série DICOM nova no banco.
        Reaproveita se a mesma reconstrução já foi salva nesta sessão."""
        if vp is None or vp.mpr_plane is None:
            if notify:
                QMessageBox.information(self, "Reconstrução", "O quadro ativo não mostra uma reconstrução (MPR).")
            return None
        pl = vp.mpr_plane
        key = (id(pl.vol), pl.axis, pl.slab_mm, pl.mode) + ((vp.index,) if current_only else ())
        cache = self.__dict__.setdefault("_derived", {})
        if key in cache:
            return cache[key]
        from ipe.imaging.derived import save_plane_series
        storage = getattr(self, "storage_root", None)
        if storage is None:
            return None
        from ipe.imaging.derived import Cancelado
        quantos = 1 if current_only else pl.n
        dlg = QProgressDialog(f"Salvando {getattr(pl, 'name', '')} como série…", "Cancelar",
                              0, max(quantos, 1), self)
        dlg.setWindowTitle("Salvar reconstrução")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(200)
        QApplication.processEvents()

        def progresso(feitos: int, total: int, etapa: str) -> bool:
            if etapa == "importando":
                dlg.setLabelText("Importando a série nova no banco…")
                dlg.setMaximum(0)          # o importador não sabe dizer quanto falta
            elif feitos % 4 == 0 or feitos == total:
                dlg.setLabelText(f"Salvando {getattr(pl, 'name', '')} como série… "
                                 f"{feitos} de {total} cortes")
                dlg.setValue(feitos)
            QApplication.processEvents()
            return not dlg.wasCanceled()

        try:
            res = save_plane_series(pl, self.repo.db, storage,
                                    indices=[vp.index] if current_only else None,
                                    progresso=progresso)
        except Cancelado:
            dlg.close()
            self.status_message.emit("Gravação cancelada: nada foi salvo.")
            return None
        except Exception as e:  # noqa: BLE001
            dlg.close()
            log.exception("salvar reconstrução")
            QMessageBox.warning(self, "Reconstrução", f"Não foi possível salvar:\n{e}")
            return None
        dlg.close()
        cache[key] = res
        from ipe.central.client_repo import upload_if_client
        upload_if_client(self.repo, vp.study_uid)
        self.series = _image_series(self.repo.series_for_study(self.study_uid) + [
            s for u in self.study_order[1:] for s in self.repo.series_for_study(u)])
        self._fill_strip()
        if notify:
            n = len(res[1])
            self.status_message.emit(f"Reconstrução salva como série nova ({n} imagem{'ns' if n > 1 else ''}) — "
                                     "já aparece na tira e no banco.")
        return res

    def _film_item(self, vp: Viewport) -> dict | None:
        """A imagem do quadro, com a janela/zoom/pan atuais, para o compositor."""
        f = vp.current_frame()
        if f is not None and f.is_virtual and vp.mpr_plane is not None:
            # reconstrução: vira série e segue normal (oblíquo: só a imagem atual, o volume pode ser grande)
            only = isinstance(vp.mpr_plane, ObliquePlane)
            saved = self.save_reconstruction(vp, current_only=only)
            if saved is None:
                return None
            series_uid, sops = saved
            w, h = max(vp.width(), 1), max(vp.height(), 1)
            item = {"study_uid": vp.study_uid, "series_uid": series_uid, "index": 0 if only else vp.index,
                    "label": getattr(vp.mpr_plane, "label", f"{vp.mpr_plane.name} (MPR)"), "zoom": vp.state.zoom,
                    "pan_x": vp.state.pan.x() / w, "pan_y": vp.state.pan.y() / h, "invert": vp.state.invert,
                    "cmap": vp.state.cmap, "rotation": vp.film_orientation()[0],
                    "flip_h": vp.film_orientation()[1], "filter": vp.state.filter}
            if vp.state.window_set:
                item["width"], item["level"] = vp.state.width, vp.state.level
            return item
        if f is None or f.is_virtual or not f.series_uid:
            return None
        study = self.repo.series_info(f.series_uid) or {}
        w, h = max(vp.width(), 1), max(vp.height(), 1)
        item = {"study_uid": study.get("study_uid", vp.study_uid), "series_uid": f.series_uid,
                "label": study.get("description", ""), "zoom": vp.state.zoom,
                "pan_x": vp.state.pan.x() / w, "pan_y": vp.state.pan.y() / h, "invert": vp.state.invert,
                "cmap": vp.state.cmap if vp._img is not None and not vp._img.is_color else "",
                "rotation": vp.film_orientation()[0], "flip_h": vp.film_orientation()[1],
                "filter": vp.state.filter}
        # índice dentro da série original (o quadro pode estar mostrando imagens-chave/fases)
        frames = build_frames(self.repo.instances_for_series(f.series_uid), f.series_uid)
        item["index"] = next((i for i, g in enumerate(frames)
                              if g.sop_uid == f.sop_uid and g.frame_index == f.frame_index), 0)
        if vp.state.window_set and vp._img is not None and not vp._img.is_color:
            item["width"], item["level"] = vp.state.width, vp.state.level
        return item

    def _film_from_viewport(self, vp: Viewport) -> None:
        item = self._film_item(vp)
        if item is not None:
            self.film_requested.emit({"kind": "images", "items": [item]})

    def film_add_current(self) -> None:
        vp = self.active or (self.viewports[0] if self.viewports else None)
        item = self._film_item(vp) if vp is not None else None
        if item is None:
            self.status_message.emit("Este quadro não tem uma imagem que possa ir para o filme (MPR ainda não).")
            return
        self.film_requested.emit({"kind": "images", "items": [item]})

    def film_add_all(self) -> None:
        items = [it for it in (self._film_item(v) for v in self.viewports) if it]
        if items:
            self.film_requested.emit({"kind": "images", "items": items})

    def film_add_series(self, uid: str | None = None) -> None:
        vp = self.active or (self.viewports[0] if self.viewports else None)
        item = self._film_item(vp) if vp is not None else None
        if uid and (item is None or item["series_uid"] != uid):
            self.film_requested.emit({"kind": "series", "series_uid": uid, "index": 0, "view": {}})
            return
        if item is None:
            return
        view = {k: item[k] for k in ("width", "level", "zoom", "pan_x", "pan_y", "invert", "filter")
                if k in item}
        self.film_requested.emit({"kind": "series", "series_uid": item["series_uid"], "index": item["index"],
                                  "view": view})

    def film_add_keys(self, study_uid: str | None = None) -> None:
        self.film_requested.emit({"kind": "keys", "study_uid": study_uid or self.study_uid})

    def _strip_menu(self, pos) -> None:
        item = self.strip.itemAt(pos)
        uid = item.data(Qt.UserRole) if item is not None else None
        selected = [it.data(Qt.UserRole) for it in self.strip.selectedItems()
                    if it.data(Qt.UserRole) and not str(it.data(Qt.UserRole)).startswith(
                        ("key:", "group:", "action:"))]
        m = self._menu()
        if len(selected) >= 2:
            m.addAction(f"Agrupar as {len(selected)} séries selecionadas como fases (dinâmica)",
                        lambda: self.group_series(selected))
        m.addAction("Detectar fases dinâmicas neste estudo…", self.detect_groups)
        if uid and uid.startswith("group:"):
            gid = int(uid[6:])
            m.addSeparator()
            m.addAction("Abrir no quadro ativo", lambda: self.load_series_into(self.active or self.viewports[0], uid))
            m.addAction("Renomear grupo…", lambda: self.rename_group(gid))
            m.addAction("Desfazer o grupo", lambda: self.ungroup(gid))
        if uid and uid.startswith("key:"):
            m.addSeparator()
            m.addAction("Imagens-chave no filme", lambda: self.film_add_keys(uid[4:]))
        if uid and uid.startswith("pending:"):
            serie = uid[8:]
            m.addSeparator()
            m.addAction("Não baixar esta série", lambda: self.skip_pending_series(serie))
            m.addAction("Cancelar o download deste exame", self.cancel_download)
            m.exec(self.strip.viewport().mapToGlobal(pos))
            return
        if not uid or uid.startswith(("key:", "group:", "action:")):
            m.exec(self.strip.viewport().mapToGlobal(pos))
            return
        m.addSeparator()
        m.addAction("Abrir no quadro ativo", lambda: self.load_series_into(self.active or self.viewports[0], uid))
        m.addAction("Série no filme (inteira / intervalo)…", lambda: self.film_add_series(uid))
        m.addAction("Separar esta série em fases (só na tela)…", lambda: self.separar_serie(uid))
        n = self.repo.annotation_counts([uid]).get(uid, 0)
        a = m.addAction(f"Abrir na primeira imagem com medida ({n})",
                        lambda: self.open_series_at_annotation(uid))
        a.setEnabled(bool(n))
        if n:
            sub = m.addMenu("Abrir na medida…")
            sub.setStyleSheet(self.MENU_STYLE)
            sub.aboutToShow.connect(lambda: self._fill_series_annotation_menu(sub, uid))
        m.exec(self.strip.viewport().mapToGlobal(pos))

    def open_series_at_annotation(self, uid: str, index: int | None = None) -> None:
        vp = self.active or self.viewports[0]
        if vp.series_uid != uid:
            self.load_series_into(vp, uid)
        idx = vp.annotated_indices()
        if idx:
            vp.go_to(idx[0] if index is None else index)

    def _fill_series_annotation_menu(self, menu: QMenu, uid: str) -> None:
        menu.clear()
        frames = build_frames(self.repo.instances_for_series(uid), uid)
        tmp = Viewport(self.cache, self.settings)
        tmp.frames, tmp.series_uid, tmp.annotation_store = frames, uid, self.ann_store
        tmp.annotations = tmp._load_annotations()
        for i, text in tmp.annotation_summary()[:60]:
            menu.addAction(text, lambda k=i: self.open_series_at_annotation(uid, k))
        tmp.deleteLater()

    def _show_tic(self, vp: Viewport, ann) -> None:
        from ipe.ui.viewer.tic import TicDialog, collect
        rows = collect(self, vp, ann)
        if len(rows) < 2:
            QMessageBox.information(
                self, "Curva tempo-intensidade",
                "Não achei outras fases nesta posição. A curva precisa de uma RM dinâmica: fases na "
                "mesma série (mesma posição) ou uma série por fase, com a mesma orientação e o mesmo "
                "tamanho de imagem.")
            return
        dlg = TicDialog(rows, self)
        summary = dlg.result.get("summary", "")
        if summary and ann.text != summary:
            ann.text = summary
            vp._store("save", ann)
            vp.update()
        dlg.exec()

    def _study_keys(self, study_uid: str) -> list:
        return self.repo.key_images(study_uid)

    def _strip_clicked(self, item: QListWidgetItem) -> None:
        uid = item.data(Qt.UserRole)
        if not uid:
            return
        if uid == "action:toggle_all":
            self.show_all_series = not self.show_all_series
            self._fill_strip()
            return
        if str(uid).startswith("pending:"):
            self.status_message.emit("Esta série ainda está vindo — botão direito para não baixá-la.")
            return
        if QApplication.keyboardModifiers() & (Qt.ControlModifier | Qt.ShiftModifier):
            return                                # só seleção (para agrupar)
        if self.active is None and self.viewports:
            self._activate(self.viewports[0])
        if self.active is not None:
            self.load_series_into(self.active, uid)

    def _strip_double_clicked(self, item: QListWidgetItem) -> None:
        """Duplo clique numa série de medicina nuclear com mais de uma incidência: abre lado a lado."""
        uid = item.data(Qt.UserRole)
        if not uid or not isinstance(uid, str) or ":" in uid:
            return
        s = self._series_row(uid)
        if s is None or (s.modality or "").upper() != "NM":
            return
        NMV.open_series_views(self, uid)

    # ------------------------------------------------------------ painel de medidas
    def _measures_panel(self, create: bool = True):
        if getattr(self, "measures_panel", None) is None and create:
            from ipe.ui.viewer.measures_panel import MeasuresPanel
            # janela própria, não um painel preso à direita: a tabela tem seis colunas
            self.measures_panel = MeasuresPanel(self, self.window())
            self.measures_panel.hide()
        return getattr(self, "measures_panel", None)

    def toggle_measures_panel(self, on: bool) -> None:
        panel = self._measures_panel(create=on)
        if panel is None:
            return
        if on:
            panel.refresh()
            panel.show()
            panel.raise_()
            panel.activateWindow()
        else:
            panel.hide()

    def refresh_measures(self) -> None:
        panel = self._measures_panel(create=False)
        if panel is not None and panel.isVisible():
            QTimer.singleShot(0, panel.refresh)

    def medida_escolhida(self, _vp, ann) -> None:
        panel = self._measures_panel(create=False)
        if panel is not None and panel.isVisible():
            panel.selecionar_id(getattr(ann, "db_id", None))

    def _series_label(self, uid: str) -> str:
        s = self._series_row(uid)
        if s is None:
            return ""
        label = f"Se {s.series_number} {s.description}".strip()
        if s.study_uid != self.study_uid:
            label += f" ({fmt_date(self.study_infos.get(s.study_uid, {}).get('study_date', ''))})"
        return label

    def grupo_dinamico_de(self, series_uid: str) -> tuple[int, int] | None:
        """(grupo, fase) se a série faz parte de uma série dinâmica do exame; senão None.

        Pedido dele (10/10/2026): *"uma vez que a série faça parte de um grupo dinâmico, trate-a
        sempre como dinâmica"*. Grupo montado à mão, grupo da regra de "juntar" e série separada
        em fases contam igual. O grupo do banco ganha do grupo só da tela."""
        achados = []
        for gid, g in self.groups.items():
            if g.get("kind", "dynamic") != "dynamic":
                continue
            uids = g.get("series_uids") or []
            if series_uid in uids:
                achados.append((gid, 0 if g.get("fases") else uids.index(series_uid)))
        if not achados:
            return None
        achados.sort(key=lambda a: (a[0] < 0, a[0]))
        return achados[0]

    def load_series_into(self, vp: Viewport, series_uid: str, phase: int = 0,
                         start_index: int | None = None, como_serie: bool = False) -> None:
        """Põe a série no quadro. Série que é fase de uma dinâmica abre **como a dinâmica**, já
        na fase dela (`como_serie=True` força a série sozinha)."""
        if not como_serie and series_uid and ":" not in series_uid:
            grupo = self.grupo_dinamico_de(series_uid)
            if grupo is not None:
                self._load_group(vp, grupo[0], grupo[1], start_index)
                return
        if series_uid.startswith("key:"):
            self._load_key_series(vp, series_uid[4:])
            return
        if series_uid.startswith("group:"):
            self._load_group(vp, int(series_uid[6:]), phase, start_index)
            return
        if series_uid.startswith("fase:"):
            _, gid, i = series_uid.split(":")
            if not como_serie and int(gid) in self.groups:
                # a fase de uma série separada também abre como a dinâmica, já naquela fase
                self._load_group(vp, int(gid), int(i), start_index)
            else:
                self._load_fase(vp, int(gid), int(i), start_index)
            return
        if series_uid.startswith("action:"):
            return
        if series_uid.startswith(NMV.PREFIX) and NMV.load_into(self, vp, series_uid):
            self.update_reference_lines()
            return
        s = self._series_row(series_uid)
        if s is None:
            return
        frames = build_frames(self.repo.instances_for_series(series_uid), series_uid)
        if not frames:
            return
        meta = self.repo.series_meta(series_uid) or {}
        novo_for = meta.get("frame_of_reference", "") or f"study:{s.study_uid}"
        if start_index is None:
            start_index = self._onde_entrar(vp, frames, novo_for, s.study_uid)
        vp.mpr_plane = None
        QTimer.singleShot(0, self._update_mpr_bar)
        vp.for_uid = novo_for
        vp.study_uid = s.study_uid
        vp.modality = s.modality
        vp.key_frames = self.key_set
        vp.set_series(series_uid, frames, self._series_label(series_uid),
                      self.study_infos.get(s.study_uid, self.study_info), start_index)
        vp.left_tool = self.left_tool
        vp.pacientes_do_layout = self.pacientes_no_layout
        vp.regua3d_estado = self.__dict__.setdefault("_regua3d", {})
        vp.anonymize = self.anonymize
        self.hub.leave(vp)
        self._activate(vp)
        self.enquadrar_imagem_solta(vp)
        self.update_reference_lines()

    def enquadrar_imagem_solta(self, vp: Viewport) -> None:
        """Mamografia arrastada para um quadro à mão: entra enquadrada na mama, como a do protocolo.

        Arrastar uma incidência para o quadro é pedir para olhar aquela mama, não o ar em volta.
        Até a 0.63 a imagem solta abria com a imagem inteira e o zoom tinha de ser dado na mão,
        quadro por quadro. Num quadro do protocolo, reenquadra o **conjunto**: as duas mamas têm
        de continuar na mesma escala, senão a comparação lado a lado não é comparação.
        """
        if vp is None or vp._img is None or (vp.modality or "").upper() != "MG":
            return
        s = self.mg_session
        if s is not None and vp.mg_cell is not None:
            s.enquadrar(so_pendentes=True)
            return
        if not vp.enquadrar_na_mama():
            self.status_message.emit("Não achei a mama nesta imagem: o quadro abriu inteiro.")

    def _onde_entrar(self, vp: Viewport, frames: list, novo_for: str, novo_estudo: str = "") -> int | None:
        """Em que corte a série nova entra no quadro: o mais perto de onde ele já estava.

        Só vale comparar milímetros quando as coordenadas são do mesmo espaço: mesmo frame of
        reference, ou pelo menos o mesmo exame (mesa e sessão iguais). Entre exames diferentes
        sem referência comum, a posição proporcional é o mais honesto que dá.
        """
        from ipe.imaging.series import quadro_na_posicao
        if not vp.frames:
            return None                       # quadro vazio: o meio da série, como sempre
        mesma_ref = (bool(vp.for_uid) and vp.for_uid == novo_for) or \
            (bool(vp.study_uid) and vp.study_uid == novo_estudo)
        ponto = vp.ponto_central() if mesma_ref else None
        return quadro_na_posicao(frames, ponto, vp.fracao_atual())

    def _load_key_series(self, vp: Viewport, study_uid: str) -> None:
        frames = []
        for k in self.repo.key_images(study_uid):
            frames.append(Frame(k["path"], k["frame_index"], k["sop_uid"], k["instance_number"],
                                _vec(k["position"], 3), _vec(k["orientation"], 6),
                                series_uid=k["series_uid"]))
        if not frames:
            self.status_message.emit("Este estudo não tem imagens-chave.")
            return
        vp.mpr_plane = None
        QTimer.singleShot(0, self._update_mpr_bar)
        vp.for_uid = ""            # quadros de séries diferentes: sem sincronização automática
        vp.study_uid = study_uid
        vp.key_frames = self.key_set
        vp.set_series(f"key:{study_uid}", frames, "★ Imagens-chave",
                      self.study_infos.get(study_uid, self.study_info), start_index=0)
        vp.left_tool = self.left_tool
        vp.anonymize = self.anonymize
        self._activate(vp)
        self.update_reference_lines()

    # ================================================================ fases (grupos)
    def _group_phases(self, g: dict) -> tuple[list[list[Frame]], list[str]]:
        if g.get("fases"):                    # grupo virtual: as fases já estão montadas
            return list(g["fases"]), list(g.get("rotulos") or
                                          [f"Fase {i + 1}" for i in range(len(g["fases"]))])
        phases, labels = [], []
        for uid in g["series_uids"]:
            frames = build_frames(self.repo.instances_for_series(uid), uid)
            if frames:
                phases.append(frames)
                s = self._series_row(uid)
                labels.append(f"Se {s.series_number} {s.description}".strip() if s else uid[-8:])
        return phases, labels

    def _load_fase(self, vp: Viewport, gid: int, i: int, start_index: int | None = None) -> None:
        """Uma fase de série separada, como se fosse uma série sozinha."""
        g = self.groups.get(gid)
        if g is None or not g.get("fases") or not 0 <= i < len(g["fases"]):
            return
        frames = g["fases"][i]
        uid = g["series_uids"][0]
        s = self._series_row(uid)
        meta = self.repo.series_meta(uid) or {}
        novo_for = meta.get("frame_of_reference", "") or f"study:{g['study_uid']}"
        if start_index is None:
            start_index = self._onde_entrar(vp, frames, novo_for, g["study_uid"])
        vp.mpr_plane = None
        QTimer.singleShot(0, self._update_mpr_bar)
        vp.for_uid = novo_for
        vp.study_uid = g["study_uid"]
        vp.modality = s.modality if s else ""
        vp.key_frames = self.key_set
        rotulo = (g.get("rotulos") or [])[i] if i < len(g.get("rotulos") or []) else f"Fase {i + 1}"
        vp.set_series(f"fase:{gid}:{i}", frames,
                      f"{self._series_label(uid)} — {rotulo}",
                      self.study_infos.get(g["study_uid"], self.study_info), start_index)
        vp.left_tool = self.left_tool
        vp.anonymize = self.anonymize
        self.hub.leave(vp)
        self._activate(vp)
        self.update_reference_lines()

    def _load_group(self, vp: Viewport, gid: int, phase: int = 0, start_index: int | None = None) -> None:
        g = self.groups.get(gid)
        if g is None:
            return
        phases, labels = self._group_phases(g)
        if not phases:
            return
        first = self._series_row(g["series_uids"][0])
        meta = self.repo.series_meta(g["series_uids"][0]) or {}
        vp.mpr_plane = None
        QTimer.singleShot(0, self._update_mpr_bar)
        novo_for = meta.get("frame_of_reference", "") or f"study:{g['study_uid']}"
        if start_index is None and phases[0]:
            start_index = self._onde_entrar(vp, phases[0], novo_for, g["study_uid"])
        vp.for_uid = novo_for
        vp.study_uid = g["study_uid"]
        vp.modality = first.modality if first else ""
        vp.key_frames = self.key_set
        vp.set_phases(f"group:{gid}", phases, labels, f"▦ {g['name']}",
                      self.study_infos.get(g["study_uid"], self.study_info), phase, start_index)
        vp.left_tool = self.left_tool
        vp.anonymize = self.anonymize
        self.hub.leave(vp)
        self._activate(vp)
        self.update_reference_lines()

    def _ordered_compatible(self, uids: list[str]) -> tuple[list[str], str]:
        """Ordena por horário e confere se as séries podem ser fases umas das outras."""
        from ipe.imaging import phases as PH
        items = []
        for uid in dict.fromkeys(uids):
            s = self._series_row(uid)
            frames = build_frames(self.repo.instances_for_series(uid), uid)
            items.append((uid, frames, s.series_number if s else 0))
        ref = items[0][1]
        for uid, frames, _n in items[1:]:
            ok, why = PH.compatible(ref, frames)
            if not ok:
                s = self._series_row(uid)
                return [], f"A série {s.series_number if s else ''} {s.description if s else ''} não combina: {why}."
        return [u for u, _f, _n in PH.order(items)], ""

    def group_series(self, uids: list[str], name: str = "Dinâmica", load_into: Viewport | None = None,
                     group_id: int | None = None, phase_uid: str | None = None) -> int | None:
        rows = [self._series_row(u) for u in uids]
        study = next((r.study_uid for r in rows if r), self.study_uid)
        if len({r.study_uid for r in rows if r}) > 1:
            QMessageBox.information(self, "Agrupar", "Só dá para agrupar séries do mesmo estudo.")
            return None
        ordered, err = self._ordered_compatible(uids)
        if err:
            QMessageBox.information(self, "Agrupar fases", err)
            return None
        gid = self.repo.save_series_group(study, ordered, name, group_id)
        self.groups[gid] = {"id": gid, "study_uid": study, "name": name, "kind": "dynamic",
                            "series_uids": ordered}
        if self.series_filter is not None:
            self.series_filter.append(f"group:{gid}")
        self._fill_strip()
        vp = load_into or self.active or self.viewports[0]
        phase = ordered.index(phase_uid) if phase_uid in ordered else 0
        idx = vp.index if vp.frames else None
        self.load_series_into(vp, f"group:{gid}", phase, idx)
        self.status_message.emit(f"{len(ordered)} fases agrupadas em “{name}”. No quadro, ← → trocam a fase.")
        self.anotar_regra(ordered, "juntar", name)
        return gid

    def anotar_regra(self, uids: list[str], acao: str, nome: str) -> None:
        """Ele fez na mão: o programa anota a regra como **pendente**, e não age até confirmar."""
        from ipe.imaging import dinamicas as D
        rows = [self._series_row(u) for u in uids]
        rows = [r for r in rows if r is not None]
        if not rows:
            return
        regra = D.acrescentar_pendente(
            self.settings, D.sugerir(rows[0].modality, [r.description for r in rows], acao, nome,
                                     self.study_uid, self.rotulo_do_exame()))
        if regra:
            self.status_message.emit(
                f"Anotei uma regra pendente: {acao} séries de {regra['modalidade']} com "
                f"“{regra['contem']}” na descrição. Confirme em Preferências ▸ Dinâmicos.")

    def rotulo_do_exame(self) -> str:
        """Como o exame aparece na tabela de regras (para a situação “só neste exame”)."""
        i = self.study_info or {}
        data = fmt_date(i.get("study_date", ""))
        return " ".join(x for x in (i.get("accession", ""), data,
                                    (i.get("description", "") or "")[:24]) if x) or self.study_uid[-8:]

    def separar_serie(self, uid: str) -> None:
        """Separa na tela uma série que traz todas as fases juntas (TC multifásica, por exemplo)."""
        from ipe.imaging.dynamic import separar_fases
        frames = build_frames(self.repo.instances_for_series(uid), uid)
        fases = separar_fases(frames) if frames else None
        if not fases or len(fases) < 2:
            QMessageBox.information(self, "Separar série", "Esta série não tem as fases juntas: "
                                    "não achei nem posições repetidas nem mais de um horário de "
                                    "aquisição.")
            return
        s = self._series_row(uid)
        gid = min([0] + [k for k in self.groups if k < 0]) - 1
        nome = f"Fases de {s.description[:22]} ({len(fases)})" if s else f"Fases ({len(fases)})"
        self.groups[gid] = {"id": gid, "study_uid": self.study_uid, "name": nome, "kind": "dynamic",
                            "series_uids": [uid], "split": True, "fases": fases,
                            "rotulos": [f"Fase {i + 1}" for i in range(len(fases))]}
        self._nao_separar.discard(uid)
        self._fill_strip()
        self.load_series_into(self.active or self.viewports[0], f"group:{gid}")
        self.status_message.emit(f"Série separada em {len(fases)} fases — só na tela; "
                                 "no banco ela continua inteira.")
        self.anotar_regra([uid], "separar", nome)

    def join_phase(self, vp: Viewport, uid: str) -> None:
        """Série solta no canto "+ fase" de um quadro."""
        if vp.series_uid.startswith("group:"):
            gid = int(vp.series_uid[6:])
            g = self.groups.get(gid)
            if g is None or uid in g["series_uids"]:
                return
            self.group_series(g["series_uids"] + [uid], g["name"], vp, gid, phase_uid=uid)
        elif vp.series_uid and not vp.series_uid.startswith(("key:", "mpr:", "mg:")):
            if uid == vp.series_uid:
                return
            self.group_series([vp.series_uid, uid], "Dinâmica", vp, phase_uid=uid)

    def ungroup(self, gid: int) -> None:
        if gid < 0:                            # grupo virtual (separação): só desfaz na tela
            g = self.groups.pop(gid, None)
            if g:
                self._nao_separar.add(g["series_uids"][0])
                for vp in self.viewports:
                    if vp.series_uid.startswith((f"group:{gid}", f"fase:{gid}:")):
                        self.load_series_into(vp, g["series_uids"][0])
            self._fill_strip()
            self.status_message.emit("Série inteira de volta. Para não separar nunca mais, "
                                     "tire a regra em Preferências ▸ Dinâmicos.")
            return
        self.repo.delete_series_group(gid)
        g = self.groups.pop(gid, None)
        for vp in self.viewports:
            if vp.series_uid == f"group:{gid}" and g:
                self.load_series_into(vp, g["series_uids"][min(vp.phase, len(g["series_uids"]) - 1)])
        self._fill_strip()

    def rename_group(self, gid: int) -> None:
        from PySide6.QtWidgets import QInputDialog
        g = self.groups.get(gid)
        if g is None:
            return
        name, ok = QInputDialog.getText(self, "Renomear grupo", "Nome:", text=g["name"])
        if ok and name.strip():
            g["name"] = name.strip()
            self.repo.save_series_group(g["study_uid"], g["series_uids"], g["name"], gid)
            self._fill_strip()

    def _group_action(self, vp: Viewport, action: str) -> None:
        if not vp.series_uid.startswith("group:"):
            return
        gid = int(vp.series_uid[6:])
        g = self.groups.get(gid)
        if g is None:
            return
        if action == "ungroup":
            self.ungroup(gid)
        elif action == "remove_phase":
            rest = [u for i, u in enumerate(g["series_uids"]) if i != vp.phase]
            if len(rest) < 2:
                self.ungroup(gid)
                return
            g["series_uids"] = rest
            self.repo.save_series_group(g["study_uid"], rest, g["name"], gid)
            self._fill_strip()
            self.load_series_into(vp, f"group:{gid}", min(vp.phase, len(rest) - 1), vp.index)

    def detect_groups(self) -> None:
        from ipe.imaging import phases as PH
        cands = []
        grouped = {u for g in self.groups.values() for u in g["series_uids"]}
        for s in self.series:
            if s.study_uid != self.study_uid or s.series_uid in grouped or not s.num_images:
                continue
            frames = build_frames(self.repo.instances_for_series(s.series_uid), s.series_uid)
            cands.append((s.series_uid, frames, s.series_number, s.modality, s.description))
        found = PH.detect(cands)
        if not found:
            QMessageBox.information(self, "Fases dinâmicas",
                                    "Não achei séries de RM com a mesma geometria (3 ou mais). "
                                    "Selecione as fases na tira (Ctrl+clique) e use “Agrupar”, ou arraste "
                                    "uma série para o canto inferior direito de um quadro.")
            return
        for uids in found:
            dlg = PhaseGroupDialog(self, uids)
            if dlg.exec():
                chosen = dlg.chosen()
                if len(chosen) >= 2:
                    self.group_series(chosen, dlg.name())

    def _cycle_series(self, delta: int) -> None:
        vp = self.active
        if vp is None:
            return
        uids = [s.series_uid for s in self.series if s.num_images]
        if not uids:
            return
        i = uids.index(vp.series_uid) if vp.series_uid in uids else -1
        self.load_series_into(vp, uids[(i + delta) % len(uids)])

    def show_series_menu(self, vp: Viewport, global_pos) -> None:
        self.menu_de_series(vp).exec(global_pos)

    def escolher_serie_no_vazio(self, vp: Viewport, global_pos) -> None:
        """Clique num quadro vazio (0.99.11): a lista de séries do exame, para pôr ali.

        Pedido dele: *"quando um protocolo de exibição for aberto e não houver sequência em
        determinada janela, ao clicar, mostre a lista de séries para eu poder colocar no local
        (somente nesse exame, não vai atualizar o protocolo)"*. É o mesmo menu do canto da série;
        carregar a série no quadro não grava nada no protocolo."""
        menu = self.menu_de_series(vp)
        if not menu.actions():
            self.status_message.emit("Este exame não tem séries para pôr neste quadro.")
            return
        self._menu_do_vazio = menu            # popup não bloqueia; a referência mantém o menu vivo
        menu.popup(global_pos)

    def _janela_principal(self):
        from PySide6.QtWidgets import QApplication
        return next((w for w in QApplication.topLevelWidgets() if hasattr(w, "anexar_ao_exame")), None)

    def acoes_de_documentos(self, menu: QMenu, study_uid: str) -> None:
        """0.99.57: anexar PDF/imagem ao exame e ver os documentos (PDF) dele."""
        main = self._janela_principal()
        n = 0
        try:
            n = sum(1 for se in self.repo.series_for_study(study_uid, ocultas=True)
                    if (se.modality or "").upper() == "DOC")
        except Exception:  # noqa: BLE001
            pass
        a = menu.addAction(f"📄 Documentos do exame ({n} série(s))…" if n else "📄 Documentos do exame…",
                           lambda: main.abrir_documentos(study_uid) if main else None)
        a.setEnabled(main is not None)
        a = menu.addAction("📎 Anexar documento (PDF ou imagem)…",
                           lambda: main.escolher_anexos(study_uid) if main else None)
        a.setEnabled(main is not None)

    def menu_de_series(self, vp: Viewport) -> QMenu:
        """Monta o menu de séries do canto do quadro (separado de quem exibe, para testar)."""
        menu = QMenu(self)
        for st_uid in self.study_order:
            if len(self.study_order) > 1:
                info = self.study_infos.get(st_uid, {})
                menu.addSection(("Atual " if st_uid == self.study_uid else "Anterior ")
                                + fmt_date(info.get("study_date", "")))
            if self._study_keys(st_uid):
                a = QAction("★ Imagens-chave", menu)
                a.triggered.connect(lambda _=False, u=st_uid: self.load_series_into(vp, f"key:{u}"))
                menu.addAction(a)
            for g in self.groups.values():
                if g["study_uid"] == st_uid:
                    a = QAction(f"▦ {g['name']} ({len(g['series_uids'])} fases)", menu, checkable=True,
                                checked=(vp.series_uid == f"group:{g['id']}"))
                    a.triggered.connect(lambda _=False, u=f"group:{g['id']}": self.load_series_into(vp, u))
                    menu.addAction(a)
            for s in self.series:
                if s.study_uid != st_uid:
                    continue
                text = f"{s.series_number:>3}  {s.modality}  {s.description}  ({s.num_images} im)"
                grupo = self.grupo_dinamico_de(s.series_uid)
                if grupo is not None:
                    g = self.groups[grupo[0]]
                    # diz que vai abrir como dinâmica, e em qual fase
                    # concatenado: um padrão que começa com {} sequestraria outros textos
                    text = text + "  ▦ " + f"fase {grupo[1] + 1} de {g['name']}"
                    marcada = vp.series_uid == f"group:{grupo[0]}" and int(vp.phase or 0) == grupo[1]
                else:
                    marcada = s.series_uid == vp.series_uid
                a = QAction(text, menu, checkable=True, checked=marcada)
                if s.thumbnail:
                    pm = QPixmap()
                    pm.loadFromData(s.thumbnail, "PNG")
                    a.setIcon(QIcon(pm))
                a.triggered.connect(lambda _=False, uid=s.series_uid: self.load_series_into(vp, uid))
                menu.addAction(a)
        menu.addSeparator()
        self.acoes_de_documentos(menu, vp.study_uid or self.study_uid)
        return menu

    # ================================================================ anteriores
    def _fill_priors_menu(self) -> None:
        self.priors_menu.clear()
        others = self.repo.other_studies_same_patient(self.study_uid)
        if not others:
            a = QAction("Nenhum outro exame deste paciente no banco", self.priors_menu)
            a.setEnabled(False)
            self.priors_menu.addAction(a)
            return
        if screen_with_role(self.settings, "compare") is not None:
            opt = QAction("Abrir no monitor de comparação", self.priors_menu, checkable=True,
                          checked=bool(self.settings.get("viewer.priors_on_compare", True)))
            opt.toggled.connect(lambda on: self.settings.set("viewer.priors_on_compare", on))
            self.priors_menu.addAction(opt)
            self.priors_menu.addSeparator()
        for r in others:
            text = f"{fmt_date(r.study_date)}  {r.modalities}  {r.description}"
            a = QAction(text, self.priors_menu, checkable=True,
                        checked=r.study_uid in self.study_order)
            a.setEnabled(r.study_uid not in self.study_order)
            a.triggered.connect(lambda _=False, u=r.study_uid: self.open_prior(u))
            self.priors_menu.addAction(a)

    def toggle_priors_panel(self, on: bool) -> None:
        if on and self.priors_panel is None:
            from ipe.ui.viewer.priors_panel import PriorsPanel
            self.priors_panel = PriorsPanel(self)
            self._body.addWidget(self.priors_panel)
        if self.priors_panel is not None:
            self.priors_panel.setVisible(on)
            if on:
                self.priors_panel.refresh()

    def open_prior(self, study_uid: str) -> None:
        if screen_with_role(self.settings, "compare") is not None \
                and self.settings.get("viewer.priors_on_compare", True) \
                and self.compare_handler_connected:
            self.open_prior_requested.emit(self, study_uid)
        else:
            self.add_study(study_uid)

    def add_study(self, study_uid: str, colocar: bool = True) -> None:
        """Traz outro estudo do mesmo paciente para esta aba (comparação).

        `colocar=False` (escolha na tira de miniaturas, 0.99.11): só traz as séries para a tira, sem
        mexer nos quadros."""
        ensure = getattr(self.repo, "ensure_local", None)
        if ensure is not None and not ensure(study_uid, self):
            return
        if study_uid in self.study_order:
            return
        info = self.repo.study_info(study_uid) or {}
        self.study_infos[study_uid] = info
        self.study_order.append(study_uid)
        new_series = _image_series(self.repo.series_for_study(study_uid))
        self.series.extend(new_series)
        self.groups.update({g["id"]: g for g in self.repo.series_groups(study_uid)})
        self.key_set |= self.repo.key_image_set(study_uid)
        if colocar:
            self.estudos_na_tira = None        # veio pelo botão Anteriores: aparece na tira
        self._fill_strip()
        QTimer.singleShot(0, self.load_overlay_objects)
        self._encher_filtro_de_exames()
        if not colocar:
            return
        # coloca a série equivalente ao lado do quadro ativo
        ref = self._series_row(self.active.series_uid) if self.active else None
        match = match_series(ref, new_series)
        if match is None:
            return
        rows, cols = self._layout
        if rows * cols == 1:
            self.set_layout(1, 2)
        src = self.active if self.active is not None else self.viewports[0]
        target = self.viewports[1] if src is self.viewports[0] else self.viewports[0]
        self.load_series_into(target, match.series_uid)
        if self.hub.apply_saved(src, target):
            self.status_message.emit("Exame anterior adicionado e alinhado como da última vez "
                                     "(Alt + rodinha ajusta um quadro sem mover o outro).")
        else:
            self.status_message.emit("Exame anterior adicionado. Alinhe os dois quadros no mesmo "
                                     "nível e clique em “Ligar quadros” (L) para rolarem juntos.")

    # ================================================================ layout
    def cefalometria_do_exame(self):
        """A cefalometria automática já gravada num exame desta aba (a da chegada, 0.99.16), ou None."""
        from ipe.ai import cefalometria as CF
        if self.repo is None:
            return None
        for uid in (getattr(self, "study_order", None) or [self.study_uid]):
            res = CF.ler_do_exame(self.repo, uid)
            if res is not None:
                return res
        return None

    def mostrar_linhas_da_ia(self, res, modulo=None, study_uid: str = "") -> None:
        """As linhas das medidas de uma IA (cefalometria, índices do crânio) como sobreposição 3D
        (0.99.16): aparecem em qualquer quadro cujo plano contenha a linha."""
        from ipe.ai import cefalometria as CF
        M = modulo or CF
        objs = getattr(self, "overlay_objects", None)
        if objs is None:
            return
        objs[:] = [o for o in objs if o.source != M.FONTE_OVERLAY]
        if res is not None and any(m.linhas for m in res.medidas.values()):
            objs.append(M.objeto_de_linhas(res, study_uid or self.study_uid))
        if hasattr(self, "_apply_overlays"):
            self._apply_overlays()

    def mostrar_cefalometria_na_tela(self, res, study_uid: str = "") -> None:
        self.mostrar_linhas_da_ia(res, None, study_uid)

    # ------------------------------------------------------------ índices do crânio (0.99.17, SynthSeg)
    def neuro_do_exame(self):
        from ipe.ai import neuro as N
        if self.repo is None:
            return None
        for uid in (getattr(self, "study_order", None) or [self.study_uid]):
            res = N.ler_do_exame(self.repo, uid)
            if res is not None:
                return res
        return None

    def abrir_neuro(self, res=None, automatica: bool = False, do_exame: bool = False):
        """Janela de conferência dos índices do crânio, uma por aba."""
        from ipe.ui.viewer.cefalometria_painel import CefalometriaPainel, def_neuro
        if res is None and do_exame:
            res = self.neuro_do_exame()
            automatica = res is not None
        p = getattr(self, "neuro_painel", None)
        if p is None:
            p = CefalometriaPainel(self, res, self.window(), automatica=automatica, D=def_neuro())
            self.neuro_painel = p
        else:
            p.carregar(res, automatica)
        p.ligar_quadros()
        p.show()
        p.raise_()
        return p

    def neuro_automatica(self, vp=None, simular: bool = False):
        """A série do quadro vai para o SynthSeg; no fim abre a conferência dos índices."""
        vp = vp or self.active
        if vp is None or (vp.modality or "").upper() not in ("MR", "CT"):
            QMessageBox.information(self, "Índices do crânio (IA)",
                                    "Os índices automáticos são feitos na RM ou na TC de crânio: abra a série "
                                    "(de preferência a 3D T1) num quadro.")
            return None
        return self.segmentar_orgaos(vp, simular=simular, tipo="neuro")

    # ------------------------------------------------------------ níveis linfonodais (0.99.20)
    def linfonodos_automatico(self, vp=None, simular: bool = False):
        vp = vp or self.active
        if vp is None or (vp.modality or "").upper() != "CT":
            QMessageBox.information(self, "Níveis linfonodais (IA)",
                                    "O mapa dos níveis linfonodais é feito na TC do pescoço: abra a série "
                                    "(axial de partes moles) num quadro.")
            return None
        return self.segmentar_orgaos(vp, simular=simular, tipo="linfonodos")

    def nivel_linfonodal_do_ponto(self, p):
        """(rótulo, texto, regra) do ponto (mm) pelo mapa do exame, ou None sem mapa."""
        m = getattr(self, "marcos_linfonodais", None)
        if m is None:
            return None
        from ipe.ai import linfonodos as LN
        return LN.texto_da_lesao(np.asarray(p, float), m)

    def neuro_botao(self):
        if self.neuro_do_exame() is not None:
            return self.abrir_neuro(do_exame=True)
        return self.neuro_automatica(self.active)

    def ver_medida_da_cefalometria(self, m, vp=None) -> bool:
        """Leva o quadro ao plano e ao corte onde a linha da medida está inteira (reformata se precisar)."""
        from ipe.ai import cefalometria as CF
        alvo = CF.plano_da_medida(m)
        vp = vp or self.active or next((v for v in self.viewports if v.frames), None)
        if alvo is None or vp is None:
            return False
        plano, ponto = alvo
        atual = vp.plano_nome() if hasattr(vp, "plano_nome") else ""
        if atual != plano and not self.reformatar(vp, plano):
            return False
        ok = vp.go_to_point(np.asarray(ponto, float))
        self.active = vp
        vp.update()
        return ok

    def cefalometria_botao(self):
        """O clique no botão: com o resultado já no exame (automático na chegada), abre a conferência;
        sem ele, roda a automática na série do quadro."""
        if self.cefalometria_do_exame() is not None:
            return self.abrir_cefalometria(do_exame=True)
        return self.cefalometria_automatica(self.active)

    def abrir_cefalometria(self, res=None, automatica: bool = False, do_exame: bool = False):
        """Janela da cefalometria (0.99.15), uma por aba: conferência da automática ou roteiro à mão.
        `do_exame`: sem `res`, usa a cefalometria automática gravada no exame (0.99.16)."""
        from ipe.ui.viewer.cefalometria_painel import CefalometriaPainel
        if res is None and do_exame:
            res = self.cefalometria_do_exame()
            automatica = res is not None
        p = getattr(self, "cefalometria_painel", None)
        if p is None:
            p = CefalometriaPainel(self, res, self.window(), automatica=automatica)
            self.cefalometria_painel = p
        else:
            p.carregar(res, automatica)
        p.ligar_quadros()
        p.show()
        p.raise_()
        return p

    def cefalometria_automatica(self, vp=None, simular: bool = False):
        """A série do quadro vai para o TotalSegmentator (palato, faringe, hioide, mandíbula, língua,
        vértebras); no fim abre a janela de conferência com os números."""
        vp = vp or self.active
        if vp is None or (vp.modality or "").upper() != "CT":
            QMessageBox.information(self, "Cefalometria automática",
                                    "A cefalometria automática é feita na TC: abra a série de TC (axial fina) "
                                    "num quadro. Para medir à mão, use Cefalometria ▸ à mão.")
            return None
        return self.segmentar_orgaos(vp, simular=simular, tipo="cefalometria")

    def abrir_roteiro(self, roteiro_id: str = "mrpi"):
        """Janela do roteiro de medida guiada (0.99.14), uma por aba."""
        from ipe.ui.viewer.roteiro_painel import RoteiroPainel
        p = getattr(self, "roteiro_painel", None)
        if p is None:
            p = RoteiroPainel(self, roteiro_id, self.window())
            self.roteiro_painel = p
        elif p.andamento.roteiro.id != roteiro_id:
            p.comecar(roteiro_id)
        p.ligar_quadros()
        p.show()
        p.raise_()
        p.medir_passo_atual()
        return p

    def _new_viewport(self) -> Viewport:
        vp = Viewport(self.cache, self.settings)
        painel = getattr(self, "roteiro_painel", None)
        if painel is not None:
            painel._ligados.append(vp)
            vp.sig.annotations_changed.connect(painel.medida_feita)
        for nome in ("cefalometria_painel", "neuro_painel"):
            cef = getattr(self, nome, None)
            if cef is not None:
                vp.sig.annotations_changed.connect(cef.medida_feita)
                cef._ligados.append(vp)
        vp.left_tool = self.left_tool
        vp.anonymize = self.anonymize
        vp.case_label = self.case_label
        vp.key_frames = self.key_set
        vp.annotation_store = self.ann_store
        vp.sig.activated.connect(self._activate)
        vp.sig.tool_requested.connect(self.set_left_tool)
        vp.sig.series_menu_requested.connect(self.show_series_menu)
        vp.sig.empty_clicked.connect(self.escolher_serie_no_vazio)
        vp.sig.maximize_requested.connect(self.toggle_maximize)
        vp.sig.frame_changed.connect(self._on_frame_changed)
        vp.sig.view_changed.connect(self._on_view_changed)
        vp.sig.view_changed.connect(self.mg_sync_view)
        vp.sig.cursor_moved.connect(self._on_cursor_moved)
        vp.sig.key_toggle_requested.connect(lambda v: (self._activate(v), self.toggle_key_image()))
        vp.sig.sync_group_requested.connect(self._cycle_group)
        vp.sig.button_action.connect(self._button_action)
        vp.sig.annotations_changed.connect(lambda _v: self._refresh_annotation_marks())
        vp.sig.tic_requested.connect(self._show_tic)
        vp.sig.join_requested.connect(self.join_phase)
        vp.sig.group_action.connect(self._group_action)
        vp.sig.film_requested.connect(self._film_from_viewport)
        vp.sig.oblique_requested.connect(self.create_oblique)
        vp.sig.plane_menu_requested.connect(self.menu_de_plano)
        vp.sig.plane_rotate_requested.connect(self.girar_plano)
        vp.sig.curved_requested.connect(self.create_curved)
        vp.sig.quadrant_requested.connect(self.mg_quadrant)
        vp.sig.quadrant_cycle.connect(self.mg_quadrant_cycle)
        vp.sig.implant_changed.connect(self._implant_changed)
        vp.sig.orgaos_requested.connect(self.segmentar_orgaos)
        vp.sig.coluna_requested.connect(lambda v: self.segmentar_orgaos(v, tipo="coluna"))
        vp.sig.renumerar_requested.connect(self.renumerar_coluna)
        vp.sig.numeracao_requested.connect(self.abrir_numeracao_coluna)
        vp.sig.lesion_requested.connect(self.choose_lesion_for)
        vp.sig.medida_criada.connect(self.ligar_pela_posicao)            # 0.99.59
        vp.sig.clone_roi_requested.connect(self.clonar_roi)
        vp.referencial_da_sincronia = self.outros_referenciais_ligados
        vp.sig.segment_requested.connect(self.segment_at)
        vp.sig.pincel.connect(self.pincel_estruturas)
        vp.sig.status_message.connect(self.status_message)
        vp.sig.enquadre_pendente.connect(self._enquadre_pendente)
        vp.sig.histogram_requested.connect(self.show_histogram)
        vp.sig.anotacoes_requested.connect(self.set_anotacoes)
        vp.sig.copy_requested.connect(lambda v: (self._activate(v), self.copiar_quadro()))
        vp.sig.annotations_changed.connect(lambda _v: self.refresh_lesions())
        vp.sig.annotations_changed.connect(lambda _v: self.refresh_measures())
        vp.sig.annotations_changed.connect(lambda _v: self.carregar_segmentacoes())
        vp.sig.annotation_picked.connect(self.medida_escolhida)
        vp.sig.reflines_toggled.connect(lambda on: self.refs_action.setChecked(on))
        vp.overlays = self.overlay_objects
        if self.lesion_panel is not None:
            vp.lesion_names = {x["id"]: x["name"] for x in self.lesion_panel.lesions}
        vp.sig.hover_moved.connect(lambda v, u, w: self.dyn.on_hover(v, u, w) if self.dyn else None)
        vp.sig.phase_changed.connect(lambda v: self.dyn.fase_mudou(v) if self.dyn else None)
        vp.sig.annotations_changed.connect(lambda _v: self.dyn.refresh() if self.dyn else None)
        vp.sig.reconstruction_save_requested.connect(
            lambda v, one: (self._activate(v), self.save_reconstruction(v, notify=True, current_only=one)))
        return vp

    def restringir_saidas(self) -> None:
        """Esconde o que tira dado do programa (exportar, SR, filme).

        Vale para a janela aberta por chamada externa no modo "só visualizador": quem recebe a
        chamada vê o exame, não leva o exame embora.
        """
        for a in getattr(self, "acoes_de_saida", []):
            if a is not None:
                a.setVisible(False)
                a.setEnabled(False)

    def set_layout(self, rows: int, cols: int) -> None:
        self._maximized = None
        needed = rows * cols
        while len(self.viewports) < needed:
            vp = self._new_viewport()
            self.viewports.append(vp)
            shown = {v.series_uid for v in self.viewports}
            for uid in self._auto_items():
                if uid not in shown:
                    self.load_series_into(vp, uid)
                    break
        for i in reversed(range(self.grid.count())):
            self.grid.itemAt(i).widget().setParent(None)
        for i, vp in enumerate(self.viewports):
            if i < needed:
                self.grid.addWidget(vp, i // cols, i % cols)
                vp.show()
            else:
                vp.hide()
                vp.setParent(None)
        self._layout = (rows, cols)
        if self.active is None or self.viewports.index(self.active) >= needed:
            self._activate(self.viewports[0])
        self.religar_monitores()
        self.update_reference_lines()

    def religar_monitores(self) -> None:
        """Quadro novo numa tela do conjunto entra na ligação com as outras.

        Sem isto, trocar o layout (ou de passo do protocolo) desfazia a sincronia entre os
        monitores sem avisar ninguém — e a tela voltava a andar sozinha.
        """
        grupo = [t for t in (getattr(self, "monitor_group", None) or []) if t is not None]
        if len(grupo) < 2 or not self.settings.get("monitors.sync_group", True):
            return
        try:
            quadros = [v for t in grupo for v in t._shown() if getattr(v, "frames", None)]
            if len(quadros) > 1:
                self.hub.link_all(quadros, 1)
        except Exception:  # noqa: BLE001 - sincronia é conveniência, não pode derrubar o layout
            log.debug("não consegui religar os monitores", exc_info=True)

    # ------------------------------------------------------------ painel do filme
    def film_panel_visible(self) -> bool:
        return self.film_holder.isVisibleTo(self) and self.film_holder.layout().count() > 0

    def show_film_panel(self, comp) -> None:
        lay = self.film_holder.layout()
        if comp.parentWidget() is not self.film_holder:
            lay.addWidget(comp)
        comp.show()
        was_hidden = self.film_holder.isHidden()
        self.film_holder.show()
        if was_hidden:
            total = max(self.view_split.width(), 600)
            self.view_split.setSizes([int(total * 0.55), int(total * 0.45)])
        self.film_expanded = False
        self.grid_host.show()
        comp.set_docked(True, False)

    def hide_film_panel(self) -> None:
        self.film_holder.hide()
        self.film_expanded = False
        self.grid_host.show()

    def toggle_film_expanded(self) -> None:
        """Filme ocupando todo o espaço dos quadros (como o 1×1 do layout) ou lado a lado."""
        if not self.film_panel_visible():
            return
        self.film_expanded = not self.film_expanded
        self.grid_host.setVisible(not self.film_expanded)
        comp = self.film_holder.layout().itemAt(0).widget()
        if comp is not None:
            comp.set_docked(True, self.film_expanded)

    def release_film(self, comp) -> None:
        """Tira o compositor deste estudo (antes de fechar a aba ou de levá-lo para outra)."""
        if comp.parentWidget() is self.film_holder:
            self.film_holder.layout().removeWidget(comp)
            comp.setParent(None)
        self.hide_film_panel()

    def toggle_maximize(self, vp: Viewport) -> None:
        rows, cols = self._layout
        if rows * cols == 1:
            return
        if self._maximized is vp:
            self.set_layout(rows, cols)
            return
        for v in self.viewports:
            v.setVisible(v is vp)
        self.grid.addWidget(vp, 0, 0, rows, cols)
        self._maximized = vp
        self.update_reference_lines()

    def _activate(self, vp: Viewport) -> None:
        if self.active is vp:
            return
        if self.active is not None:
            self.active.active = False
            self.active.update()
        self.active = vp
        vp.active = True
        vp.update()
        if vp.mpr_plane is not None and hasattr(self, "slab_combo"):
            self._sync_slab_controls(vp)
        uid = vp.frames[vp.index].series_uid if vp.series_uid.startswith("mg:") and vp.frames else vp.series_uid
        for i in range(self.strip.count()):
            it = self.strip.item(i)
            if it.data(Qt.UserRole) == uid:
                self.strip.setCurrentItem(it)
                break
        if vp.mpr_plane is not None:
            self._sync_slab_controls(vp)
        if self.dyn is not None:
            self.dyn.activated(vp)
        self.reflect_sync_flags()            # a automática mostrada é a da modalidade deste quadro
        self._sync_fusion_bar()
        self.update_render3d_bar()

    def _shown(self) -> list[Viewport]:
        if self._maximized is not None:
            return [self._maximized]
        return self.viewports[: self._layout[0] * self._layout[1]]

    # ================================================================ sincronização
    def reflect_sync_flags(self) -> None:
        """Deixa os botões desta aba iguais ao estado do SyncHub."""
        if not hasattr(self, "link_action"):
            return
        linked = any(v in self.hub.members for v in self.viewports)
        mod = self._modalidade_ativa()
        auto = self.hub.sync_auto and self.hub.auto_da_modalidade(mod)
        modo = self.modo_sync()
        for a, on in ((self.sync_auto_action, modo == "auto"), (self.sync_manual_action, modo == "manual"),
                      (self.sync_wl_action, self.hub.sync_wl),
                      (self.sync_zoom_action, self.hub.sync_zoom), (self.refs_action, self.hub.show_refs),
                      (self.link_action, linked or auto)):
            if a.isChecked() != on:
                a.blockSignals(True)
                a.setChecked(on)
                a.blockSignals(False)

    @property
    def sync_auto(self) -> bool:
        return self.hub.sync_auto

    def _modalidade_ativa(self) -> str:
        """A modalidade do quadro ativo — a regra da automática é desta modalidade."""
        from ipe.ui.viewer.sync import _modalidade_base
        vp = self.active
        mod = getattr(vp, "modality", "") if vp is not None and getattr(vp, "frames", None) else ""
        if not mod:
            mods = {s.modality for s in self.series if s.study_uid == self.study_uid and s.modality}
            mod = next(iter(mods)) if len(mods) == 1 else ""
        return _modalidade_base(mod)

    def modo_sync(self) -> str:
        """Como o botão Sincronizar sincroniza: "auto" (padrão) ou "manual"."""
        modo = self.settings.get("viewer.sync_modo", "auto")
        return modo if modo in ("auto", "manual") else "auto"

    def escolher_modo_sync(self, modo: str) -> None:
        """Escolher a linha no menu do botão já sincroniza daquele jeito."""
        self.settings.set("viewer.sync_modo", modo)
        self.sincronizar(True)

    def sincronizar(self, on: bool) -> None:
        """Liga ou desliga, do jeito escolhido no menu do botão."""
        vistos = self._shown()
        mod = self._modalidade_ativa()
        nome = MODALIDADE_TXT.get(mod, mod) or "todas as modalidades"
        if not on:
            self.hub.unlink(self.viewports)
            # Desligar é pedido para nada andar junto: desfaz os grupos e desliga a automática da
            # modalidade — antes a automática seguia valendo (0.99.9).
            if self.hub.sync_auto and self.hub.auto_da_modalidade(mod):
                self.hub.set_auto_modalidade(mod, False)
            self.status_message.emit(f"Sincronização desligada — {nome} (fica guardado).")
        elif self.modo_sync() == "manual":
            self.hub.unlink(vistos)
            if self.hub.auto_da_modalidade(mod):
                self.hub.set_auto_modalidade(mod, False)
            g = self.hub.link_all(vistos)
            if g is None:
                self.status_message.emit("Sincronizar precisa de pelo menos dois quadros com imagens.")
            else:
                self.status_message.emit(f"Sincronização manual (grupo {GROUP_NAMES[g]}): os quadros mantêm a "
                                         "diferença de cortes de agora. Alt + rodinha ou Alt + setas ajustam "
                                         "um quadro sem mover os outros.")
        else:
            self._ligar_automatica(vistos, mod, nome)
        self.reflect_sync_flags()
        self.update_reference_lines()

    def _ligar_automatica(self, vistos, mod: str, nome: str) -> None:
        """Automática: o quadro ativo (o que ele estava mexendo) manda; os outros do mesmo exame vão
        para o mesmo ponto do paciente agora, e não só na próxima rolagem (pedido de 29/10: "ao
        habilitar após desabilitar, sincronize automaticamente, ajustando pela janela ativa")."""
        ativo = self.active if self.active is not None and self.active.frames else \
            next((v for v in vistos if v.frames), None)
        self.hub.unlink(vistos)
        self.hub.set_auto_modalidade(mod, True)
        if ativo is None:
            return
        # quadros de outro exame (outro referencial) não têm "mesmo ponto": entram ligados mantendo a
        # diferença de agora, como no manual — senão comparar com o anterior pararia de andar junto
        outros = [v for v in vistos if v is not ativo and v.frames and not self.hub.same_space(ativo, v)]
        if outros:
            self.hub.link_all([ativo, *outros])
        self.hub.frame_changed(ativo, self)
        extra = f" Os quadros de outro exame ficam ligados mantendo a diferença de agora." if outros else ""
        self.status_message.emit(f"Sincronização automática — {nome}: os quadros foram para o ponto do quadro "
                                 f"ativo.{extra}")

    def toggle_link(self, on: bool) -> None:
        """O botão Sincronizar."""
        self.sincronizar(on)

    def _cycle_group(self, vp: Viewport) -> None:
        if not vp.frames:
            return
        g = self.hub.cycle(vp)
        self.status_message.emit(f"Quadro no grupo de sincronização {GROUP_NAMES[g]} ({g})" if g
                                 else "Quadro fora dos grupos de sincronização")
        self.update_reference_lines()

    def _button_action(self, vp: Viewport, action: str) -> None:
        self._activate(vp)
        if action == "series_prev":
            self._cycle_series(-1)
        elif action == "series_next":
            self._cycle_series(1)
        elif action == "frame_prev":
            vp.step(-1)
        elif action == "frame_next":
            vp.step(1)
        elif action == "key":
            self.toggle_key_image()

    def _on_frame_changed(self, vp: Viewport) -> None:
        self.hub.frame_changed(vp, self)
        if self.dyn is not None:
            self.dyn.hover = None
            self.dyn.refresh()
        for v in self._shown():
            if vp in v.oblique_targets:
                v.update()

    def _on_cursor_moved(self, vp: Viewport, point: np.ndarray) -> None:
        self.hub.cursor_moved(vp, point, self)
        for w in self._shown():             # o 3D não entra no hub, mas mostra a cruz
            if w is not vp and getattr(w, "render3d", None) is not None:
                w.cursor_point = point
                w.update()

    def _on_view_changed(self, vp: Viewport, kind: str) -> None:
        if kind in ("zoom", "pan") and getattr(vp, "mg_spec", None) is not None \
                and not getattr(self, "_mg_syncing", False):
            vp.relock_free()          # zoom/pan à mão: a tomo e a recombinada seguem este ponto
        self.hub.view_changed(vp, kind, self)

    def update_reference_lines(self) -> None:
        self.hub.update_reference_lines(self)

    # ================================================================ MPR
    def toggle_mpr(self, on: bool) -> None:
        if on:
            ok = self._enter_mpr()
            if not ok:
                self.mpr_action.blockSignals(True)
                self.mpr_action.setChecked(False)
                self.mpr_action.blockSignals(False)
        else:
            self._exit_mpr()

    def _source_series(self, vp: Viewport | None) -> str | None:
        """Série original do quadro (também quando ele já mostra uma reconstrução)."""
        if vp is None:
            return None
        if vp.mpr_plane is not None and vp.series_uid.startswith("mpr:"):
            return vp.series_uid.split(":")[1]
        if getattr(vp, "render3d", None) is not None:
            return vp.render3d.src_uid or None
        if vp.series_uid.startswith("group:"):
            # Dinâmica: a série da fase que está na tela. Sem isso, abrir sempre como dinâmica
            # (0.69) tiraria o MPR, o oblíquo e a segmentação de toda série que é fase.
            try:
                g = self.groups.get(int(vp.series_uid.split(":")[1]))
            except ValueError:
                g = None
            if g is None or g.get("fases") or not g.get("series_uids"):
                return None
            return g["series_uids"][min(max(int(vp.phase or 0), 0), len(g["series_uids"]) - 1)]
        if not vp.frames or vp.frames[0].is_virtual or vp.series_uid.startswith(("key:", "mg:")):
            return None
        return vp.series_uid

    def _volume_for(self, src: Viewport, uid: str, perguntar: bool = True,
                    frames: list | None = None, chave: str | None = None):
        """Volume da série `uid` (do cache, se já montado). `frames`/`chave`: monta destes quadros
        — a fase de uma dinâmica que o protocolo pede (0.90)."""
        # em série 4D cada fase tem o seu volume: a chave do cache leva a fase junto
        fase4d = src.cardiac_where()[1] if getattr(src, "is_4d", None) and src.is_4d() else 0
        if chave is None:
            chave = uid if not fase4d else f"{uid}#fase{fase4d}"
        vol = self._volumes.get(chave)
        if vol is not None:
            return vol
        if frames is None:
            frames = src.frames
            if src.mpr_plane is not None or src.series_uid != uid:
                frames = build_frames(self.repo.instances_for_series(uid), uid)
        else:
            fase4d = 0
        limit = int(self.settings.get("performance.max_volume_mb", 0) or auto_volume_mb())
        h, w = src._img.pixels.shape[:2] if src._img is not None and src.mpr_plane is None else (512, 512)
        est = len(frames) * h * w * 2 / 1024 / 1024
        if est > limit and not perguntar:
            return None
        if est > limit and QMessageBox.question(
                self, "MPR", f"O volume vai ocupar cerca de {est:,.0f} MB de memória, acima do "
                f"limite de {limit:,.0f} MB (Preferências → Desempenho).\n\nMontar mesmo assim?"
                .replace(",", ".")) != QMessageBox.Yes:
            return None
        if not perguntar:
            # pedido do protocolo ao abrir o exame: sem janela de progresso — ela aparecia e
            # fechava e levava o foco do teclado junto (as setas das etapas paravam de responder)
            class _SemJanela:
                def close(self):
                    pass
            dlg = _SemJanela()

            def progress(done: int, total: int) -> bool:
                return True
        else:
            dlg = QProgressDialog("Montando volume…", "Cancelar", 0, len(frames), self)
            dlg.setWindowTitle("MPR")
            dlg.setWindowModality(Qt.WindowModal)
            dlg.setMinimumDuration(300)

            def progress(done: int, total: int) -> bool:
                if done % 8 == 0 or done == total:
                    dlg.setValue(done)
                    QApplication.processEvents()
                return not dlg.wasCanceled()
        fase = fase4d
        try:
            vol = build_volume(frames, self.cache, progress, phase=fase)
        except VolumeError as e:
            dlg.close()
            if perguntar:
                QMessageBox.information(self, "MPR", str(e))
            return None
        dlg.close()
        if bool(self.settings.get("viewer.tirar_mesa", False)) and (src.modality or "").upper() == "CT":
            vol = self.tirar_a_mesa(vol)                    # 0.99.31 (onda A5)
        # mantém só o volume atual na memória — o protocolo que pede duas fases guarda as duas,
        # para a etapa de 4 MIPs (2 fases × 2 metades) não montar cada fase duas vezes
        manter = {k: v for k, v in self._volumes.items() if k.startswith("etapa:")} if chave.startswith("etapa:") else {}
        self._volumes = dict(list(manter.items())[-1:]) | {chave: vol}
        return vol

    def tirar_a_mesa(self, vol):
        """O volume do MPR/3D sem a mesa da TC (imaging/mesa.py). A série original não muda."""
        from ipe.imaging import mesa
        try:
            dados, mexeu = mesa.tirar_a_mesa(vol.data, vol.dx, vol.dy, vol.dz)
        except Exception:  # noqa: BLE001
            log.exception("tirar a mesa")
            return vol
        if mexeu:
            vol.data = dados
            vol.warnings.append("mesa da TC retirada (só no MPR e no 3D)")
        return vol

    def apagar_imagem(self, vp) -> bool:
        """0.99.31 (onda A7): apaga só a imagem do quadro (botão direito ▸ Apagar esta imagem…)."""
        from ipe.auth import session as S
        if vp is None or not vp.frames or vp.frames[0].is_virtual:
            return False
        if not S.require("delete", self, "apagar imagens"):
            return False
        f = vp.frames[vp.index]
        n_mesmo = sum(1 for x in vp.frames if x.sop_uid == f.sop_uid)
        extra = f" (o arquivo tem {n_mesmo} quadros; todos saem)" if n_mesmo > 1 else ""
        if self.perguntar_apagar_imagem(f"Apagar esta imagem (nº {f.instance_number}){extra}?\n\n"
                                        "Medidas e imagem-chave dela saem junto. O arquivo só é apagado se "
                                        "estiver no armazenamento do programa; fica no registro de acesso.") is False:
            return False
        try:
            self.repo.delete_instance(f.sop_uid, getattr(self, "storage_root", None))
        except Exception as e:  # noqa: BLE001
            QMessageBox.information(self, "Apagar imagem", str(e).split(": ", 1)[-1] if "Error:" in str(e) else str(e))
            return False
        S.audit(self.repo, "apagou_imagem", f"imagem nº {f.instance_number} — {f.sop_uid}", study_uid=vp.study_uid)
        i = vp.index
        restantes = [x for x in vp.frames if x.sop_uid != f.sop_uid]
        vp.frames[:] = restantes
        vp.index = min(i, len(restantes) - 1)
        vp.go_to(vp.index)
        self.status_message.emit(f"Imagem nº {f.instance_number} apagada.")
        return True

    def perguntar_apagar_imagem(self, texto: str) -> bool:
        return QMessageBox.question(self, "Apagar imagem", texto) == QMessageBox.Yes

    def alternar_mesa(self, on: bool) -> None:
        """Liga/desliga "Tirar a mesa da TC" e remonta os volumes na próxima vez."""
        self.settings.set("viewer.tirar_mesa", bool(on))
        self.settings.save()
        self._volumes = {}
        self.status_message.emit(("Mesa da TC: retirada" if on else "Mesa da TC: mostrada")
                                 + " nos próximos volumes montados — feche e abra o MPR/3D para valer agora.")

    # ------------------------------------------------------------ mapas da dinâmica
    def _mapa_do_quadro(self, vp) -> tuple | None:
        """(sessão, chave do mapa) se o quadro mostra um mapa paramétrico da dinâmica."""
        sess = getattr(self, "dyn", None)
        if sess is None or vp is None:
            return None
        from ipe.imaging.dynamic import MAPS
        chave = getattr(vp, "dyn_key", None)
        if chave not in MAPS:
            return None
        pref = (f"dyn:{id(sess.maps)}:", f"dynmpr:{id(sess.maps)}:")
        return (sess, chave) if vp.series_uid.startswith(pref) else None

    def _volume_do_mapa(self, sess, kind: str):
        """Volume 3D do mapa, para reconstruir em outro plano. Monta uma vez por mapa.

        O mapa é calculado corte a corte, sob demanda. Virar axial/coronal/sagital obriga a
        calcular **todos** os cortes: é demorado, então tem barra e botão de parar.
        """
        cache = getattr(self, "_vol_mapas", None)
        if cache is None:
            cache = self._vol_mapas = {}
        chave = f"{id(sess.maps)}:{kind}"
        if chave in cache:
            return cache[chave]
        from ipe.imaging.dynamic import MAPS
        from ipe.imaging.volume import VolumeError
        # Um mapa de RM de mama do acervo dele dá ~105 MB (100 cortes de 512²) e leva uns 7 s.
        # Com quatro mapas reorientados isso passa de 400 MB, então o cache guarda só os dois
        # últimos e o limite de memória do MPR também vale aqui.
        est = sess.maps.n * sess.maps.shape[0] * sess.maps.shape[1] * 4 / 1024 / 1024
        limite = int(self.settings.get("performance.max_volume_mb", 0) or auto_volume_mb())
        if est > limite and QMessageBox.question(
                self, "Reconstrução do mapa",
                f"O volume do mapa vai ocupar cerca de {est:,.0f} MB, acima do limite de "
                f"{limite:,.0f} MB (Preferências → Desempenho).\n\nMontar mesmo assim?"
                .replace(",", ".")) != QMessageBox.Yes:
            return None
        dlg = QProgressDialog(f"Montando o volume do mapa {MAPS[kind][0]}…", "Cancelar",
                              0, sess.maps.n, self)
        dlg.setWindowTitle("Reconstrução do mapa")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(300)

        def progresso(feitos: int, total: int) -> bool:
            if feitos % 4 == 0 or feitos == total:
                dlg.setValue(feitos)
                QApplication.processEvents()
            return not dlg.wasCanceled()

        try:
            vol = sess.maps.volume_do_mapa(kind, progresso)
        except VolumeError as e:
            dlg.close()
            QMessageBox.information(self, "Reconstrução do mapa", str(e))
            return None
        finally:
            dlg.close()
        cache[chave] = vol
        while len(cache) > 2:                   # guarda só os dois mapas mais recentes
            cache.pop(next(iter(cache)))
        return vol

    def _dyn_do_quadro(self, vp) -> tuple | None:
        """(sessão, chave) se o quadro é da dinâmica: mapa, subtração ou fase — no plano da
        aquisição ou já reconstruído."""
        sess = getattr(self, "dyn", None)
        if sess is None or vp is None:
            return None
        chave = str(getattr(vp, "dyn_key", "") or "")
        if not chave:
            return None
        mid = id(sess.maps)
        pref = (f"dyn:{mid}:", f"dynph:{mid}:", f"dynmpr:{mid}:")
        return (sess, chave) if vp.series_uid.startswith(pref) else None

    def _volume_da_fase_dyn(self, sess, i: int):
        """Volume de uma fase da dinâmica, para reconstruir o quadro de fase em outro plano."""
        cache = getattr(self, "_vol_mapas", None)
        if cache is None:
            cache = self._vol_mapas = {}
        chave = f"{id(sess.maps)}:ph{i}"
        if chave in cache:
            return cache[chave]
        from ipe.imaging.volume import VolumeError
        dlg = QProgressDialog(f"Montando a fase {i + 1} em 3D…", "Cancelar", 0, sess.maps.n, self)
        dlg.setWindowTitle("Reconstrução da fase")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(300)

        def progresso(feito, total):
            if feito % 8 == 0 or feito == total:
                dlg.setValue(feito)
                QApplication.processEvents()
            return not dlg.wasCanceled()
        try:
            vol = sess.maps.volume_da_fase(i, progresso)
        except VolumeError as e:
            QMessageBox.information(self, "Reconstrução da fase", str(e))
            return None
        finally:
            dlg.close()
        cache[chave] = vol
        while len(cache) > 2:
            cache.pop(next(iter(cache)))
        return vol

    def reformatar_mapa(self, vp, sess, kind: str, nome: str) -> bool:
        """Põe um quadro da dinâmica em axial, coronal, sagital ou oblíquo — ou de volta ao plano
        gravado. Vale para mapa, subtração **e fase** (0.68: pedido dele, *"no dinâmico, permita
        que eu possa mudar o eixo (sagital, axial, coronal e oblíquo)"* — antes só o mapa virava,
        e nunca em oblíquo).

        O quadro reorientado **não entra nas curvas**: ROI e ponto são medidos na grade em que a
        dinâmica foi adquirida, e uma ROI desenhada num corte reconstruído atravessaria vários
        cortes originais. Em vez de devolver número errado, o quadro sai da conta e diz por quê.
        A segmentação da lesão, ao contrário, funciona em qualquer plano: a semente é um ponto do
        paciente.
        """
        from ipe.imaging.dynamic import MAPS
        e_fase = kind.startswith("ph:")
        if nome == "Original":
            # Volta no corte que ele está olhando, não no que o índice do plano novo calhar de ser:
            # o índice de um sagital não quer dizer nada no plano da aquisição.
            idx = None
            centro = vp.ponto_central()
            if centro is not None:
                try:
                    idx = sess.maps.plane("ei" if e_fase else kind).index_for_point(np.asarray(centro, float))
                except Exception:  # noqa: BLE001
                    idx = None
            sess.show_view(vp, kind, index=idx)
            self._update_mpr_bar()
            self.update_reference_lines()
            sess.refresh()
            alvo = f"fase {int(kind[3:]) + 1}" if e_fase else MAPS[kind][0]
            self.status_message.emit(f"De volta ao plano da aquisição: {alvo}.")
            return True
        vol = self._volume_da_fase_dyn(sess, int(kind[3:])) if e_fase else self._volume_do_mapa(sess, kind)
        if vol is None:
            return False
        centro = vp.ponto_central()
        if centro is None:
            centro = vol.voxel_to_patient(vol.shape[2] / 2, vol.shape[1] / 2, vol.shape[0] / 2)
        if nome == "Oblíquo":
            pl = vp.plane()
            if pl is None:
                QMessageBox.information(self, "Oblíquo", "Este quadro não tem geometria para virar oblíquo.")
                return False
            try:
                plano = ObliquePlane.do_plano(vol, pl[1], pl[2], centro)
            except VolumeError as e:
                QMessageBox.information(self, "Oblíquo", str(e))
                return False
        else:
            plano = next((MPRPlane(vol, ax) for ax in (0, 1, 2) if MPRPlane(vol, ax).name == nome), None)
        if plano is None:
            QMessageBox.information(self, "Reconstrução da dinâmica",
                                    f"Não dá para montar o plano {nome} com a geometria desta dinâmica.")
            return False
        self._mostrar_plano_dyn(vp, sess, kind, plano, centro)
        return True

    def _mostrar_plano_dyn(self, vp, sess, kind: str, plano, centro) -> None:
        """Põe no quadro um plano reconstruído da dinâmica (mapa, subtração ou fase)."""
        from ipe.imaging.dynamic import MAPS
        info = self.study_infos.get(getattr(sess, "study_uid", self.study_uid), self.study_info)
        largura, nivel, janela_ok = vp.state.width, vp.state.level, vp.state.window_set
        vp.mpr_plane = plano
        vp.key_frames = self.key_set
        if kind.startswith("ph:"):
            i = int(kind[3:])
            vp.modality = "MR"
            rotulo = f"Fase {i + 1} — {sess.maps.dset.labels[i]} — {plano.name}"
        else:
            nome_mapa, _desc, u_rel, u_abs, _cmap = MAPS[kind]
            unidade = u_rel if sess.maps.relative else u_abs
            vp.modality = f"MAP {kind}"
            rotulo = (f"Mapa {nome_mapa} ({unidade}) — {plano.name}" if unidade
                      else f"Mapa {nome_mapa} — {plano.name}")
        vp.set_series(f"dynmpr:{id(sess.maps)}:{kind}:{plano.axis}", plano.frames(), rotulo, info,
                      start_index=plano.index_for_point(centro))
        vp.dyn_key = kind
        if kind.startswith("ph:"):
            if janela_ok:
                vp.set_window(largura, nivel, emit=False)
            vp.set_colormap("")
        else:
            w, l = sess.maps.window(kind)
            vp.set_window(w, l, emit=False)
            vp.set_colormap(vp.cor_padrao() or MAPS[kind][4])
        vp.ghosts = []
        vp.anonymize = self.anonymize
        self._update_mpr_bar()
        self._sync_slab_controls(vp)
        self.update_reference_lines()
        sess.refresh()
        self.status_message.emit(f"Reconstrução da dinâmica em {plano.name} ({plano.n} cortes). "
                                 "As curvas saem do plano da aquisição: volte ao original para "
                                 "medir ROI.")

    def reconstruct_plane(self, name: str) -> bool:
        """Reconstrução num único plano (axial, coronal ou sagital) no quadro ativo; os outros
        quadros continuam como estão (dá para comparar com a série original ao lado)."""
        src = self.active
        mapa = self._mapa_do_quadro(src)
        if mapa is not None:
            return self.reformatar_mapa(src, mapa[0], mapa[1], name)
        uid = self._source_series(src)
        if uid is None:
            QMessageBox.information(self, "Reconstrução", "Selecione um quadro com uma série (TC, RM, PET…).")
            return False
        vol = self._volume_for(src, uid)
        if vol is None:
            return False
        plane = next((MPRPlane(vol, ax) for ax in (0, 1, 2) if MPRPlane(vol, ax).name == name), None)
        if plane is None:
            QMessageBox.information(self, "Reconstrução", f"Não foi possível montar o plano {name} desta série.")
            return False
        width, level, win_set = src.state.width, src.state.level, src.state.window_set
        center = None
        if src._img is not None:
            h, w = src._img.pixels.shape[:2]
            center = src.pixel_to_patient(w / 2, h / 2)
        if center is None:
            center = vol.voxel_to_patient(vol.shape[2] / 2, vol.shape[1] / 2, vol.shape[0] / 2)
        s = self._series_row(uid)
        study_uid = s.study_uid if s else self.study_uid
        for_uid = src.for_uid
        vp = src
        vp.mpr_plane = plane
        vp.for_uid = for_uid
        vp.study_uid = study_uid
        vp.modality = s.modality if s else ""
        vp.key_frames = self.key_set
        vp.set_series(f"mpr:{uid}:{plane.axis}", plane.frames(), f"{plane.name} (reconstrução)",
                      self.study_infos.get(study_uid, self.study_info), start_index=plane.index_for_point(center))
        if win_set:
            vp.set_window(width, level, emit=False)
        vp.anonymize = self.anonymize
        self._update_mpr_bar()
        self._sync_slab_controls(vp)
        self.update_reference_lines()
        self.status_message.emit(f"{plane.name} reconstruído no quadro ativo ({plane.n} cortes). "
                                 "Espessura (slab) na barra MPR.")
        return True

    # --------------------------------------------------------------- plano do quadro
    PLANOS = ("Axial", "Coronal", "Sagital", "Oblíquo")

    def menu_de_plano(self, vp: Viewport, global_pos) -> None:
        """Menu da linha de orientação, no canto do quadro."""
        atual = vp.plano_nome()
        m = QMenu(self)
        cab = QAction("Plano do quadro", m)
        cab.setEnabled(False)
        m.addAction(cab)
        for nome in self.PLANOS:
            a = QAction(nome, m, checkable=True, checked=(nome == atual))
            a.triggered.connect(lambda _=False, n=nome, q=vp: self.reformatar(q, n))
            m.addAction(a)
        if isinstance(getattr(vp, "mpr_plane", None), ObliquePlane):
            m.addSeparator()
            g = QAction("Girar plano (arrastar)", m, checkable=True,
                        checked=(self.left_tool == "rotplane"))
            g.triggered.connect(lambda: self.set_left_tool("rotplane"))
            m.addAction(g)
        ehmapa = self._dyn_do_quadro(vp) is not None
        if getattr(vp, "mpr_plane", None) is not None:
            m.addSeparator()
            back = QAction("Voltar ao plano da aquisição" if ehmapa else "Voltar à série original", m)
            back.triggered.connect(lambda _=False, q=vp: self.reformatar(q, "Original"))
            m.addAction(back)
        m.exec(global_pos)

    def reformatar(self, vp: Viewport, nome: str) -> bool:
        """Troca o plano do quadro: axial, coronal, sagital, oblíquo — ou volta à série original."""
        anterior, self.active = self.active, vp
        try:
            dyn = self._dyn_do_quadro(vp)
            if dyn is not None:
                return self.reformatar_mapa(vp, dyn[0], dyn[1], nome)
            if nome == "Original":
                self._plane_back()
                return True
            if nome == "Oblíquo":
                return self.obliquo_do_plano_atual(vp)
            return self.reconstruct_plane(nome)
        finally:
            if anterior is not None and anterior is not vp:
                self.active = anterior

    def obliquo_do_plano_atual(self, vp: Viewport) -> bool:
        """Vira o quadro para oblíquo **sem mudar a imagem**: mesmo plano, agora girável.

        Era o pedido: "se estiver em axial, mude para oblíquo mantendo a mesma posição e imagem,
        e agora permita que eu possa girar". O oblíquo que já existia nascia de uma linha
        desenhada, e por isso saía sempre perpendicular ao que estava na tela.
        """
        uid = self._source_series(vp)
        pl = vp.plane()
        if uid is None or pl is None:
            QMessageBox.information(self, "Oblíquo", "Escolha um quadro com uma série de cortes "
                                    "(TC, RM, PET…).")
            return False
        vol = self._volume_for(vp, uid)
        if vol is None:
            return False
        _pos, row, col, _n = pl
        centro = vp.ponto_central()
        if centro is None:
            centro = vol.voxel_to_patient(vol.shape[2] / 2, vol.shape[1] / 2, vol.shape[0] / 2)
        try:
            plano = ObliquePlane.do_plano(vol, row, col, centro)
        except VolumeError as e:
            QMessageBox.information(self, "Oblíquo", str(e))
            return False
        antigo = vp.mpr_plane
        if antigo is not None:
            plano.set_slab(antigo.slab_mm, antigo.mode)
        self._mostrar_plano(vp, uid, plano, centro)
        self.status_message.emit("Oblíquo a partir do plano atual: a imagem é a mesma. Use "
                                 "“Girar plano” na barra de MPR para inclinar.")
        return True

    def girar_plano(self, vp: Viewport, graus_h: float, graus_v: float) -> bool:
        """Gira o plano oblíquo do quadro em torno dos eixos da tela."""
        plano = getattr(vp, "mpr_plane", None)
        if not isinstance(plano, ObliquePlane):
            return False
        dyn = self._dyn_do_quadro(vp)
        if dyn is not None:
            try:
                novo = plano.girar(graus_h, graus_v, vp.ponto_central())
            except VolumeError:
                return False
            self._mostrar_plano_dyn(vp, dyn[0], dyn[1], novo, vp.ponto_central())
            return True
        uid = self._source_series(vp)
        if uid is None:
            return False
        centro = vp.ponto_central()
        try:
            novo = plano.girar(graus_h, graus_v, centro)
        except VolumeError:
            return False
        novo.set_slab(plano.slab_mm, plano.mode)
        self._mostrar_plano(vp, uid, novo, centro)
        return True

    def _mostrar_plano(self, vp: Viewport, uid: str, plano, centro) -> None:
        """Põe o plano reconstruído no quadro, mantendo janela, cor e o ponto que estava à vista."""
        width, level, win_set = vp.state.width, vp.state.level, vp.state.window_set
        zoom, pan, cmap = vp.state.zoom, vp.state.pan, vp.state.cmap
        s = self._series_row(uid)
        study_uid = s.study_uid if s else self.study_uid
        vp.mpr_plane = plano
        vp.study_uid = study_uid
        vp.modality = s.modality if s else ""
        vp.key_frames = self.key_set
        idx = plano.index_for_point(centro) if centro is not None else plano.idx0
        sufixo = f"  {SLAB_MODES[plano.mode]} {plano.slab_mm:.0f} mm" if plano.slab_mm else ""
        rotulo = f"{plano.name} (reconstrução)" + sufixo
        vp.set_series(f"mpr:{uid}:{plano.axis}", plano.frames(), rotulo,
                      self.study_infos.get(study_uid, self.study_info), start_index=idx)
        if win_set:
            vp.set_window(width, level, emit=False)
        vp.state.zoom, vp.state.pan, vp.state.cmap = zoom, pan, cmap
        vp.anonymize = self.anonymize
        self._update_mpr_bar()
        self._sync_slab_controls(vp)
        self.update_reference_lines()

    def _oblique_target(self, src: Viewport) -> Viewport:
        """Quadro que vai mostrar o oblíquo: o mesmo de antes; senão, no layout 1×1 abre 1×2;
        senão o quadro seguinte ao de origem."""
        if self._maximized is not None:
            self.toggle_maximize(self._maximized)
        shown = self._shown()
        for t in src.oblique_targets:
            if t in shown and t is not src:
                return t
        if len(shown) == 1:
            self.set_layout(1, 2)
            shown = self._shown()
        i = shown.index(src) if src in shown else 0
        return shown[(i + 1) % len(shown)]

    def create_oblique(self, src: Viewport, p0, p1) -> bool:
        """MPR oblíquo: plano que contém a linha desenhada em `src` e a normal de `src`."""
        uid = self._source_series(src)
        pl = src.plane()
        if uid is None or pl is None:
            QMessageBox.information(self, "MPR oblíquo",
                                    "Desenhe a linha num quadro com uma série de cortes (TC, RM, PET…).")
            return False
        vol = self._volume_for(src, uid)
        if vol is None:
            return False
        try:
            plane = ObliquePlane(vol, p0, p1, pl[3])
        except VolumeError as e:
            QMessageBox.information(self, "MPR oblíquo", str(e))
            return False
        target = self._oblique_target(src)
        if target is src:
            QMessageBox.information(self, "MPR oblíquo", "Não há outro quadro para mostrar o oblíquo.")
            return False
        old = target.mpr_plane
        if old is not None:
            plane.set_slab(old.slab_mm, old.mode)
        width, level, win_set = src.state.width, src.state.level, src.state.window_set
        s = self._series_row(uid)
        study_uid = s.study_uid if s else self.study_uid
        target.mpr_plane = plane
        target.for_uid = src.for_uid
        target.study_uid = study_uid
        target.modality = s.modality if s else ""
        target.key_frames = self.key_set
        suffix = f"  {SLAB_MODES[plane.mode]} {plane.slab_mm:.0f} mm" if plane.slab_mm else ""
        target.set_series(f"mpr:{uid}:{plane.axis}", plane.frames(), f"MPR Oblíquo{suffix}",
                          self.study_infos.get(study_uid, self.study_info), start_index=plane.idx0)
        if win_set:
            target.set_window(width, level, emit=False)
        target.anonymize = self.anonymize
        target.state.cmap = src.state.cmap
        for v in self.viewports:
            if target in v.oblique_targets and v is not src:
                v.oblique_targets.remove(target)
        src.oblique_targets = [target]
        self._update_mpr_bar()
        self._sync_slab_controls(target)
        self.update_reference_lines()
        src.update()
        self.status_message.emit("Oblíquo criado: role no quadro para mover o plano; desenhe outra linha "
                                 "para mudar o ângulo. Espessura (MIP) na barra MPR.")
        return True

    def create_curved(self, src: Viewport, pts) -> bool:
        """MPR curvo pelo caminho marcado em `src` (pontos 3D); gira com a rolagem."""
        uid = self._source_series(src)
        pl = src.plane()
        if uid is None or pl is None:
            QMessageBox.information(self, "MPR curvo", "Marque os pontos num quadro com uma série de cortes.")
            return False
        vol = self._volume_for(src, uid)
        if vol is None:
            return False
        try:
            plane = CurvedPlane(vol, pts, pl[3])
        except VolumeError as e:
            QMessageBox.information(self, "MPR curvo", str(e))
            return False
        target = self._oblique_target(src)
        if target is src:
            QMessageBox.information(self, "MPR curvo", "Não há outro quadro para mostrar o MPR curvo.")
            return False
        s = self._series_row(uid)
        study_uid = s.study_uid if s else self.study_uid
        target.mpr_plane = plane
        target.for_uid = ""
        target.study_uid = study_uid
        target.modality = s.modality if s else ""
        target.key_frames = self.key_set
        target.set_series(f"mpr:{uid}:{plane.axis}", plane.frames(), f"MPR curvo ({plane.length_mm:.0f} mm)",
                          self.study_infos.get(study_uid, self.study_info), start_index=0)
        if src.state.window_set:
            target.set_window(src.state.width, src.state.level, emit=False)
        target.state.cmap = src.state.cmap
        target.anonymize = self.anonymize
        src.oblique_targets = [target]
        self._update_mpr_bar()
        self.update_reference_lines()
        self.status_message.emit(f"MPR curvo: {plane.length_mm:.0f} mm de caminho; role no quadro para girar "
                                 "o corte em volta do caminho (0–180°).")
        return True

    def compare_phases(self, fase_a: int = 0, fase_b: int | None = None) -> bool:
        """Mesma série em dois quadros, em duas fases do ciclo, rolando os cortes juntos."""
        vp = self.active or (self.viewports[0] if self.viewports else None)
        if vp is None or not vp.is_4d():
            QMessageBox.information(self, "Cardíaco 4D",
                                    "Abra uma série com fases (cine, cardíaca 4D) antes.")
            return False
        uid, info = vp.series_uid, vp.cardiac
        fase_b = info.n_phases // 2 if fase_b is None else fase_b
        self.set_layout(1, 2)
        for alvo, fase in zip(self.viewports[:2], (fase_a, fase_b)):
            self.load_series_into(alvo, uid)
            alvo.set_cardiac_phase(fase, wrap=False)
        self.hub.sync_scroll = True
        self.status_message.emit(
            f"Comparando a fase {fase_a + 1} com a fase {fase_b + 1} — a rolagem anda nos dois.")
        if self.viewports:
            self._activate(self.viewports[0])
        return True

    def open_surface(self):
        """Superfície por faixa de densidade (osso, pele, metal) e arquivo STL."""
        src = self.active
        uid = self._source_series(src)
        if uid is None:
            QMessageBox.information(self, "Superfície",
                                    "Selecione um quadro com uma série de cortes (TC, RM…).")
            return None
        vol = self._volume_for(src, uid)
        if vol is None:
            return None
        s = self._series_row(uid)
        from ipe.ui.surface_dialog import SurfaceDialog
        dlg = SurfaceDialog(vol, None, (0, 0, 0),
                            f"Se {s.series_number} {s.description}" if s else "Superfície", self)
        dlg.exec()
        return dlg

    def open_3d(self, mode: str = "vr"):
        """Põe o volume da série do quadro ativo em 3D, no próprio quadro."""
        src = self.active
        uid = self._source_series(src)
        if uid is None:
            QMessageBox.information(self, "3D", "Selecione um quadro com uma série de cortes (TC, RM, PET…).")
            return None
        return self.abrir_3d_no_quadro(src, uid, mode, perguntar=True)

    def abrir_3d_no_quadro(self, src: Viewport, uid: str, mode: str = "vr", perguntar: bool = False,
                           frames: list | None = None, chave: str | None = None):
        """3D da série `uid` no quadro `src` — o mesmo do botão 3D, com todas as ferramentas da barra.
        Sem `perguntar` (o protocolo de exibição, 0.91) não abre janela nenhuma; `frames`/`chave`:
        de uma fase da dinâmica."""
        from ipe.imaging.render3d import Renderer3D
        from ipe.ui.viewer.render3d_view import View3D
        vol = self._volume_for(src, uid, perguntar=perguntar, frames=frames, chave=chave)
        if vol is None:
            return None
        if perguntar:
            dlg = QProgressDialog("Preparando o volume 3D…", "Cancelar", 0, 100, self)
            dlg.setWindowTitle("3D")
            dlg.setWindowModality(Qt.WindowModal)
            dlg.setMinimumDuration(300)

            def progress(done: int, total: int) -> bool:
                dlg.setValue(int(done * 100 / max(total, 1)))
                QApplication.processEvents()
                return not dlg.wasCanceled()
        else:
            dlg = None

            def progress(done: int, total: int) -> bool:
                return True
        try:
            r = Renderer3D(vol, max_dim=int(self.settings.get("viewer.render3d_size", 256)), progress=progress)
        except InterruptedError:
            if dlg is not None:
                dlg.close()
            return None
        if dlg is not None:
            dlg.close()
        s = self._series_row(uid)
        window = (src.state.width, src.state.level) if src.state.window_set else vol.window
        title = f"Se {s.series_number} {s.description}" if s else ""
        v = View3D(self, r, title, s.modality if s else "", mode, window, src_uid=uid,
                   study_uid=s.study_uid if s else self.study_uid, source_path=vol.source_path)
        src.mpr_plane = None
        v.attach(src, self.study_infos.get(s.study_uid, self.study_info) if s else self.study_info)
        self._activate(src)
        self.update_render3d_bar()
        self._update_mpr_bar()
        self.status_message.emit(
            "3D no quadro: esquerdo gira, roda aproxima, clique leva os cortes ao ponto.")
        return v

    # ------------------------------------------------------------ reconstrução da etapa como 3D (0.93)
    def registrar_recon(self, vp: Viewport, uid: str, frames: list | None, chave: str | None) -> None:
        """O protocolo montou uma reconstrução neste quadro: guarda de onde ela veio, para a barra do
        3D poder transformá-la num volume 3D."""
        if not hasattr(self, "_recon_etapa"):
            self._recon_etapa = {}
        self._recon_etapa[id(vp)] = {"series_uid": vp.series_uid, "uid": uid, "frames": frames, "chave": chave}

    def recon_da_etapa(self, vp: Viewport | None) -> dict | None:
        """{modo, cmap, texto, …} se o quadro mostra uma reconstrução que o protocolo montou."""
        reg = getattr(self, "_recon_etapa", {}).get(id(vp)) if vp is not None else None
        pl = getattr(vp, "mpr_plane", None)
        if reg is None or pl is None or not isinstance(pl, MPRPlane) or reg["series_uid"] != vp.series_uid:
            return None
        mm = float(pl.slab_mm or 0)
        modo = pl.mode if mm > 0 else "mip"
        texto = (f"Corte {pl.name}, {SLAB_MODES[pl.mode]} {mm:.0f} mm — mexa na barra e o quadro vira 3D"
                 if mm > 0 else f"Corte {pl.name} — mexa na barra e o quadro vira 3D")
        return dict(reg, modo=modo, cmap=vp.state.cmap, texto=texto)

    def recon_para_3d(self, vp: Viewport):
        """Transforma a reconstrução da etapa num 3D, como o botão 3D: mesmo volume (a fase da
        dinâmica, se for o caso), a espessura vira a caixa do corte e a câmera olha do mesmo lado
        de onde o corte era visto."""
        from ipe.ui.viewer.render3d_view import VISTAS
        rec = self.recon_da_etapa(vp)
        if rec is None:
            return None
        pl = vp.mpr_plane
        mm = float(pl.slab_mm or 0)
        centro = np.asarray(pl.position(vp.index), float)
        tela = vp.display_orientation()
        cmap, rotulo, janela_feita = vp.state.cmap, vp.series_label, vp.state.window_set
        v = self.abrir_3d_no_quadro(vp, rec["uid"], rec["modo"], frames=rec["frames"], chave=rec["chave"])
        if v is None:
            self.status_message.emit("Não deu para montar o 3D desta reconstrução: memória ou volume.")
            return None
        n = np.asarray(pl.normal, float)
        eixo = int(np.argmax(np.abs(n)))
        if mm > 0:
            # a caixa do corte no eixo da espessura: do começo ao fim da fatia
            un = np.zeros(3)
            un[eixo] = 1.0
            menor, maior = centro - un * mm / 2, centro + un * mm / 2
            lado_min, lado_max = {0: ("left", "right"), 1: ("posterior", "anterior"), 2: ("head", "feet")}[eixo]
            v.r.cut_at(menor, lado_min)
            v.r.cut_at(maior, lado_max)
        if tela is not None:
            from ipe.imaging.render3d import rotation
            t = np.asarray(tela, float)

            def nota(az, el):
                u, w, _d = rotation(az, el)
                return float(np.dot(u, t[:3]) + np.dot(w, t[3:]))
            _n, az, el = max(VISTAS, key=lambda x: nota(x[1], x[2]))
            v.az, v.el = az, el
        if cmap and v.mode not in ("vr", "surf"):
            vp.set_colormap(cmap)
        if v.mode == "mip" and not janela_feita:
            from ipe.ui.viewer.etapas import _janela_do_mip
            _janela_do_mip(v)
        v.title = rotulo
        vp.series_label = rotulo.replace("MPR ", "3D ")
        v.refresh(fast=False)
        return v

    def close_3d(self, vp: Viewport | None = None) -> None:
        """Desfaz o 3D do quadro e volta a mostrar a série de cortes."""
        vp = vp or self.active
        v = getattr(vp, "render3d", None)
        if vp is None or v is None:
            return
        uid = v.src_uid
        v.cine(False)
        vp.render3d = None
        if uid:
            self.load_series_into(vp, uid)
        else:
            vp.clear()
        self.update_render3d_bar()

    def update_render3d_bar(self) -> None:
        if getattr(self, "render3d_bar", None) is not None:
            self.render3d_bar.sync()

    def cursor_from_3d(self, origem: Viewport, ponto: np.ndarray) -> None:
        """Clique no 3D: leva o cursor e os cortes dos outros quadros até o ponto."""
        for w in self._shown():
            if w is origem or not w.frames:
                continue
            if getattr(w, "render3d", None) is not None:
                w.cursor_point = ponto
                w.update()
                continue
            w.cursor_point = ponto
            w.go_to_point(ponto)
            w.update()
        self.update_reference_lines()

    def _plane_back(self) -> None:
        vp = self.active
        uid = self._source_series(vp)
        if vp is None or vp.mpr_plane is None or uid is None:
            return
        self.load_series_into(vp, uid)
        self._update_mpr_bar()

    def _update_mpr_bar(self) -> None:
        if not hasattr(self, "mpr_bar"):
            return
        self.mpr_bar.setVisible(self.mpr_active or any(
            v.mpr_plane is not None and getattr(v.mpr_plane, "supports_slab", True) for v in self._shown()))

    def _enter_mpr(self) -> bool:
        src = self.active
        uid = self._source_series(src)
        if uid is None:
            QMessageBox.information(self, "MPR", "Selecione um quadro com uma série (TC, RM, PET…).")
            return False
        vol = self._volume_for(src, uid)
        if vol is None:
            return False
        planes = [MPRPlane(vol, ax) for ax in (0, 1, 2)]
        order = {"Axial": 0, "Coronal": 1, "Sagital": 2}
        if len({p.name for p in planes}) == 3:
            planes.sort(key=lambda p: order[p.name])
        # guarda o estado para voltar
        self._mpr_saved = (self._layout, [(v.series_uid, v.index) for v in self.viewports])
        width, level, cmap = src.state.width, src.state.level, src.state.cmap
        s = self._series_row(uid)
        study_uid = s.study_uid if s else self.study_uid
        for_uid = src.for_uid
        center = vol.voxel_to_patient(vol.shape[2] / 2, vol.shape[1] / 2, vol.shape[0] / 2)
        center = src.pixel_to_patient(*[x / 2 for x in src._img.pixels.shape[:2][::-1]]) \
            if src._img is not None else center
        # só desfaz os grupos: desligar a sincronização aqui gravaria a automática da modalidade desligada
        self.hub.unlink(self.viewports)
        self.set_layout(1, 3)
        for vp, plane in zip(self.viewports[:3], planes):
            vp.mpr_plane = plane
            vp.for_uid = for_uid
            vp.study_uid = study_uid
            vp.modality = s.modality if s else ""
            vp.key_frames = self.key_set
            vp.set_series(f"mpr:{uid}:{plane.axis}", plane.frames(), f"MPR {plane.name}",
                          self.study_infos.get(study_uid, self.study_info),
                          start_index=plane.index_for_point(center))
            vp.set_window(width, level, emit=False)
            vp.state.cmap = cmap
            vp.cursor_point = center
            vp.anonymize = self.anonymize
        self.mpr_active = True
        # Os três planos do MPR andam juntos sozinhos (sync._sempre_juntos): ligar aqui a automática
        # gravava a escolha para a modalidade inteira — abrir um MPR religava a RM toda (0.99.9).
        self.refs_action.setChecked(True)
        self.set_left_tool("cross")
        self.mpr_bar.setVisible(True)
        self._activate(self.viewports[0])
        self._sync_slab_controls(self.viewports[0])
        self.mpr_info.setText(f"   volume {vol.shape[2]}×{vol.shape[1]}×{vol.shape[0]}, "
                              f"{vol.nbytes_mb:.0f} MB" + ("   ⚠ " + " ".join(vol.warnings) if vol.warnings else ""))
        self.update_reference_lines()
        return True

    def _exit_mpr(self) -> None:
        self.mpr_active = False
        saved = self._mpr_saved
        self._mpr_saved = None
        for v in self.viewports:
            v.mpr_plane = None
            v.cursor_point = None
        if saved:
            layout, contents = saved
            for vp, (uid, idx) in zip(self.viewports, contents):
                if uid and not uid.startswith("mpr:"):
                    self.load_series_into(vp, uid)
                    vp.set_index_silently(idx)
                else:
                    vp.clear()
            self.set_layout(*layout)
        self.set_left_tool("wl")
        self._update_mpr_bar()
        self.update_reference_lines()

    def _sync_slab_controls(self, vp: Viewport) -> None:
        pl = vp.mpr_plane
        if pl is None:
            return
        for combo, value in ((self.slab_combo, pl.slab_mm), (self.mode_combo, pl.mode)):
            combo.blockSignals(True)
            i = combo.findData(value)
            if i < 0 and combo is self.slab_combo and value:
                # espessura fora da lista (a da etapa: 62 mm, 165 mm): entra na lista, para a barra
                # dizer o que está na tela em vez de "fino"
                combo.addItem(f"{float(value):.0f} mm", value)
                i = combo.count() - 1
            if i >= 0:
                combo.setCurrentIndex(i)
            combo.blockSignals(False)

    def _apply_slab(self) -> None:
        mm = float(self.slab_combo.currentData())
        mode = self.mode_combo.currentData()
        targets = [v for v in self._shown() if v.mpr_plane is not None] if self.slab_all.isChecked() \
            else [self.active] if self.active is not None and self.active.mpr_plane is not None else []
        targets = [v for v in targets if getattr(v.mpr_plane, "supports_slab", True)]
        for v in targets:
            v.mpr_plane.set_slab(mm, mode)
            suffix = f"  {SLAB_MODES[mode]} {mm:.0f} mm" if mm else ""
            v.series_label = f"MPR {v.mpr_plane.name}{suffix}"
            v._qimage_key = None
            v._load_current()
            v.update()

    # ================================================================ fusão
    def _fill_fusion_menu(self) -> None:
        m = self.fusion_menu
        m.clear()
        vp = self.active
        src = self._source_series(vp) if vp is not None else None
        head = QAction("Sobrepor ao quadro ativo:", m)
        head.setEnabled(False)
        m.addAction(head)
        rows = [s for s in self.series if s.series_uid != src and s.num_images >= 3]
        rows.sort(key=lambda s: (s.modality not in ("PT", "NM"), s.study_uid != self.study_uid, s.series_number))
        for s in rows:
            a = QAction(f"{s.modality}  Se {s.series_number}  {s.description}  ({s.num_images} im)", m)
            a.triggered.connect(lambda _=False, u=s.series_uid: self.set_fusion(self.active, u))
            m.addAction(a)
        m.addSeparator()
        for text, fn, ok in (("Aplicar a fusão do quadro ativo a todos os quadros", self.fusion_to_all,
                              vp is not None and vp.fusion is not None),
                             ("Remover a fusão do quadro ativo", lambda: self.remove_fusion(self.active),
                              vp is not None and vp.fusion is not None)):
            a = QAction(text, m)
            a.setEnabled(ok)
            a.triggered.connect(fn)
            m.addAction(a)

    def _fusion_volume(self, uid: str):
        cache = self.__dict__.setdefault("_fusion_vols", {})
        if uid in cache:
            return cache[uid]
        frames = build_frames(self.repo.instances_for_series(uid), uid)
        dlg = QProgressDialog("Montando o volume da fusão…", "Cancelar", 0, len(frames), self)
        dlg.setWindowTitle("Fusão")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(300)

        def progress(done: int, total: int) -> bool:
            if done % 8 == 0 or done == total:
                dlg.setValue(done)
                QApplication.processEvents()
            return not dlg.wasCanceled()
        try:
            vol = build_volume(frames, self.cache, progress)
        except VolumeError as e:
            dlg.close()
            QMessageBox.information(self, "Fusão", str(e))
            return None
        dlg.close()
        while len(cache) >= 2:
            cache.pop(next(iter(cache)))
        cache[uid] = vol
        return vol

    def set_fusion(self, vp: Viewport | None, uid: str):
        """Sobrepõe a série `uid` (ex.: PET) ao quadro, colorida e com transparência."""
        from ipe.imaging.fusion import Fusion
        if vp is None or not vp.frames:
            return None
        vol = self._fusion_volume(uid)
        if vol is None:
            return None
        s = self._series_row(uid)
        suv = None
        if s is not None and s.modality == "PT":
            from ipe.imaging.suv import suv_factor_for_file
            suv = suv_factor_for_file(vol.source_path)[0]
        label = f"{s.modality} Se {s.series_number}" if s else "fusão"
        fu = Fusion(vol, label, suv, cmap="hot" if (s and s.modality in ("PT", "NM")) else "rainbow",
                    series_uid=uid)
        vp.fusion = fu
        vp._fusion_cache = None
        vp.update()
        meta = self.repo.series_meta(uid) or {}
        if vp.for_uid and meta.get("frame_of_reference") and meta["frame_of_reference"] != vp.for_uid:
            self.status_message.emit("Atenção: as séries têm referenciais espaciais diferentes — a fusão usa "
                                     "as coordenadas do paciente; confira o alinhamento.")
        else:
            self.status_message.emit(f"Fusão: {label} sobre o quadro. Ajuste opacidade, cor e janela na barra.")
        self._sync_fusion_bar()
        return fu

    def remove_fusion(self, vp: Viewport | None) -> None:
        if vp is None:
            return
        vp.fusion = None
        vp._fusion_cache = None
        vp.fusion_value = None
        vp.update()
        self._sync_fusion_bar()

    def fusion_to_all(self) -> None:
        vp = self.active
        if vp is None or vp.fusion is None:
            return
        for v in self._shown():
            if v is not vp and v.frames:
                v.fusion = vp.fusion
                v._fusion_cache = None
                v.update()

    def _sync_fusion_bar(self) -> None:
        if not hasattr(self, "fusion_bar"):
            return
        vp = self.active
        fu = vp.fusion if vp is not None else None
        self.fusion_bar.setVisible(fu is not None or any(v.fusion is not None for v in self._shown()))
        if fu is None:
            self.fusion_label.setText("  Fusão (quadro ativo sem fusão)")
            return
        widgets = (self.fusion_alpha, self.fusion_cmap, self.fusion_lo, self.fusion_hi, self.fusion_hide)
        for wdg in widgets:
            wdg.blockSignals(True)
        self.fusion_label.setText(f"  Fusão: {fu.label}" + (f" ({fu.unit})" if fu.unit else ""))
        self.fusion_alpha.setValue(int(round(fu.alpha * 100)))
        i = self.fusion_cmap.findData(fu.cmap)
        if i >= 0:
            self.fusion_cmap.setCurrentIndex(i)
        self.fusion_lo.setValue(fu.lo)
        self.fusion_hi.setValue(fu.hi)
        self.fusion_hide.setChecked(fu.hide_below)
        for wdg in widgets:
            wdg.blockSignals(False)

    def _fusion_set(self, **kw) -> None:
        vp = self.active
        fu = vp.fusion if vp is not None else None
        if fu is None:
            return
        for k, v in kw.items():
            setattr(fu, k, v)
        if fu.hi <= fu.lo:
            fu.hi = fu.lo + 1e-3
        fu.changed()
        for v in self.viewports:
            if v.fusion is fu:
                v.update()

    # ================================================================ avaliação dinâmica
    def open_dynamic(self, previous: dict | None = None) -> bool:
        """Escolhe as fases e gera MSI/PEI/SER com o painel de curvas."""
        pre = None
        if previous:
            pre = previous.get("uids")
        else:
            # sem "anterior" nesta sessão, o diálogo abre com os parâmetros pré-configurados
            # (Preferências ▸ Dinâmica da mama) ou com os últimos usados — a escolha é dele (0.99.9)
            from ipe.ui.viewer import dinamica_config as DC
            previous = DC.parametros_iniciais(self.settings)
            vp = self.active
            if vp is not None and vp.series_uid.startswith("group:"):
                g = self.groups.get(int(vp.series_uid.split(":")[1]))
                pre = g["series_uids"] if g else None
        dlg = DynamicDialog(self, pre, previous)
        if dlg.exec() != QDialog.Accepted or dlg.dset is None:
            return False
        p = dlg.params()
        self.settings.set("dyn.ultimos", {k: v for k, v in p.items() if k != "uids"})
        return self.start_dynamic(dlg.dset, p)

    def start_dynamic(self, dset, params: dict) -> bool:
        from ipe.imaging.dynamic import DynamicMaps
        dlg = None
        progress = None
        if params.get("motion"):
            n_passos = len(dset.phases) * (2 if params.get("motion_rigido") else 1)
            dlg = QProgressDialog("Corrigindo movimento entre as fases…", "Cancelar", 0, n_passos, self)
            dlg.setWindowTitle("Dinâmica")
            dlg.setWindowModality(Qt.WindowModal)
            dlg.setMinimumDuration(0)

            def progress(done: int, total: int) -> bool:
                dlg.setValue(done)
                QApplication.processEvents()
                return not dlg.wasCanceled()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            maps = DynamicMaps(dset, self.cache, pre=params["pre"], early=params["early"], late=params["late"],
                               threshold_pct=params["threshold_pct"], noise_pct=params["noise_pct"],
                               relative=params["relative"], threshold_all=params["threshold_all"],
                               motion=("rigido" if params.get("motion_rigido") else bool(params.get("motion"))),
                               progress=progress,
                               rapido_pct=params.get("rapido_pct", 100.0),
                               tardio_pct=params.get("tardio_pct", 10.0),
                               sinal_min_pct=params.get("sinal_min_pct", 10.0),
                               fases_pre=params.get("fases_pre"), excluidas=params.get("excluidas"))
            maps.compute(maps.n // 2)
            if dlg is not None:
                dlg.close()
        except Exception as e:  # noqa: BLE001
            if dlg is not None:
                dlg.close()
            QApplication.restoreOverrideCursor()
            log.exception("dinâmica")
            QMessageBox.warning(self, "Dinâmica", f"Não foi possível calcular os mapas:\n{e}")
            return False
        if self.mpr_active:
            self.mpr_action.setChecked(False)
        if self.dyn is not None:
            self.close_dynamic(restore=False)
        if self._dyn_saved is None:
            self._dyn_saved = (self._layout, [(v.series_uid, v.index) for v in self.viewports])
        self.dyn = DynamicSession(self, maps, params)
        self.view_split.insertWidget(1, self.dyn.panel)
        total = max(self.view_split.width(), 900)
        sizes = [int(total * 0.6), int(total * 0.4)] + ([int(total * 0.3)] if self.film_panel_visible() else [])
        self.dyn.start()
        self.view_split.setSizes(sizes)
        self._update_mpr_bar()
        QApplication.restoreOverrideCursor()
        self.status_message.emit("Dinâmica: clique com a ferramenta Intensidade (V) ou desenhe ROIs para ver as "
                                 "curvas; o painel troca o mapa do quadro ativo.")
        return True

    def close_dynamic(self, restore: bool = True) -> None:
        dyn, self.dyn = self.dyn, None
        if dyn is None:
            return
        dyn.panel.hide()
        dyn.panel.setParent(None)
        dyn.panel.deleteLater()
        for v in self.viewports:
            if v.dyn_key is not None:
                v.dyn_key = None
                v.ann_colors = {}
                v.ghosts = []
                v.mpr_plane = None
                v.set_colormap("")
        if restore and self._dyn_saved:
            layout, contents = self._dyn_saved
            self._dyn_saved = None
            for vp, (uid, idx) in zip(self.viewports, contents):
                try:
                    if uid.startswith("group:"):
                        self._load_group(vp, int(uid.split(":")[1]), start_index=idx)
                    elif uid.startswith("key:"):
                        self._load_key_series(vp, uid[4:])
                    elif uid and not uid.startswith(("mpr:", "dyn:", "dynph:")):
                        self.load_series_into(vp, uid)
                        vp.set_index_silently(idx)
                    else:
                        vp.clear()
                except Exception:  # noqa: BLE001
                    vp.clear()
            self.set_layout(*layout)
            self.set_left_tool("wl")
        self._update_mpr_bar()
        self.update_reference_lines()

    # ================================================================ imagens-chave
    def toggle_key_image(self) -> None:
        vp = self.active
        f = vp.current_frame() if vp else None
        if f is None:
            return
        if f.is_virtual:
            self.status_message.emit("Imagem-chave de reconstrução (MPR) virá com a exportação de "
                                     "capturas; marque a imagem original.")
            return
        s = self._series_row(f.series_uid) if f.series_uid else None
        study_uid = s.study_uid if s else vp.study_uid or self.study_uid
        on = self.repo.toggle_key_image(study_uid, f.series_uid or vp.series_uid, f.sop_uid, f.frame_index)
        key = (f.sop_uid, f.frame_index)
        if on:
            self.key_set.add(key)
        else:
            self.key_set.discard(key)
        for v in self.viewports:
            v.key_frames = self.key_set
            v.update()
        self._fill_strip()
        self.status_message.emit("Imagem-chave marcada ★" if on else "Imagem-chave desmarcada")

    def gravar_ko_gsps(self, perguntar: bool = True) -> list[str]:
        """Imagens-chave (KO) e medidas/anotações (GSPS) do exame do quadro ativo, gravadas no exame como
        DICOM: vão ao PACS com ele e abrem em outros visualizadores (0.99.41). Rascunho fica de fora."""
        from ipe.exporter import ko_gsps as KG
        vp = self.active
        study = (vp.study_uid if vp is not None and vp.study_uid else None) or self.study_uid
        storage = getattr(self, "storage_root", None)
        if storage is None:
            return []
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            ko = KG.build_ko(self.repo, study)
            gsps, n = KG.build_gsps(self.repo, study)
            if ko is None and gsps is None:
                QApplication.restoreOverrideCursor()
                if perguntar:
                    QMessageBox.information(self, "Imagens-chave e anotações",
                                            "Este exame não tem imagens-chave nem medidas para gravar "
                                            "(medida rascunho não conta).")
                return []
            uids = KG.gravar_no_exame(self.repo, storage, ko, gsps)
        except Exception as e:  # noqa: BLE001
            QApplication.restoreOverrideCursor()
            log.exception("KO/GSPS")
            if perguntar:
                QMessageBox.warning(self, "Imagens-chave e anotações", f"Não foi possível gravar:\n{e}")
            return []
        QApplication.restoreOverrideCursor()
        if ko is not None:
            try:                               # o nosso KO não volta a ser "lido" como de outro sistema
                lidos = set(self.settings.get(KG.CHAVE_LIDOS, []) or [])
                self.settings.set(KG.CHAVE_LIDOS, sorted(lidos | {str(ko.SOPInstanceUID)})[-5000:])
            except Exception:  # noqa: BLE001
                pass
        n_ko = len(ko.ContentSequence) if ko is not None else 0
        if ko is not None and gsps is not None:
            msg = (f"Gravado no exame: {n_ko} imagem(ns)-chave (KO) e {n} medida(s)/anotação(ões) (GSPS). "
                   "Vai ao PACS junto com o exame.")
        elif ko is not None:
            msg = f"Gravado no exame: {n_ko} imagem(ns)-chave (KO). Vai ao PACS junto com o exame."
        else:
            msg = f"Gravado no exame: {n} medida(s)/anotação(ões) (GSPS). Vai ao PACS junto com o exame."
        self.status_message.emit(msg)
        return uids

    def show_key_images(self) -> None:
        if self.active is not None:
            self.load_series_into(self.active, f"key:{self.active.study_uid or self.study_uid}")

    # ================================================================ hanging simples
    def _auto_items(self) -> list[str]:
        """O que vai para os quadros automaticamente: as séries escolhidas ao abrir ou, sem
        escolha, os grupos de fases e as séries que não estão em grupo."""
        if self.series_filter:
            return list(self.series_filter)
        grouped = {u for g in self.groups.values() for u in g["series_uids"]}
        out = [f"group:{g['id']}" for g in self.groups.values() if g["study_uid"] == self.study_uid]
        out += [s.series_uid for s in self.series
                if s.num_images and s.study_uid == self.study_uid and s.series_uid not in grouped]
        return out

    def _nm_set_flip(self, on: bool) -> None:
        """Espelhar ou não a vista posterior ao combinar com a anterior."""
        self.settings.set("nm.flip_post", bool(on))
        NMV.clear_cache(self)
        for vp in self.viewports:
            if vp.series_uid.startswith(NMV.PREFIX):
                self.load_series_into(vp, vp.series_uid)

    def _nm_set_invert(self, on: bool) -> None:
        """Escala invertida (captação escura) como padrão em medicina nuclear."""
        self.settings.set("nm.invert", bool(on))
        for vp in self.viewports:
            if (vp.modality or "").upper() == "NM":
                vp.set_invert(bool(on))

    @staticmethod
    def _layout_for(n: int) -> tuple[int, int]:
        return {1: (1, 1), 2: (1, 2), 3: (1, 3), 4: (2, 2)}.get(n, (2, 3) if n <= 6 else (3, 3) if n <= 9
                                                                 else (3, 4) if n <= 12 else (4, 4))

    def _initial_hanging(self) -> None:
        usable = [s for s in self.series if s.num_images]
        mods = {s.modality for s in usable}
        # Mamografia com vários monitores: o modo mamografia sobe inteiro em cada tela, com as
        # etapas daquele monitor. Tem que vir antes do plano genérico, senão o modo não sobe —
        # foi o que matou o arranjo duas vezes.
        if self.mg_monitor is not None and "MG" in mods and self._apply_mg_protocol():
            return
        if not self.series_filter and not self.plano_do_monitor and "MG" not in mods and \
                self._apply_protocolo_etapas(mods):
            self._arranjo_de_protocolo = True
            return
        if self.plano_do_monitor and self._aplicar_plano(usable):
            return
        if self.series_filter:
            items = self._auto_items()
            self.set_layout(*self._layout_for(len(items)))
            for vp, uid in zip(self.viewports, items):
                if vp.series_uid != uid:
                    self.load_series_into(vp, uid)
            if self.viewports:
                self._activate(self.viewports[0])
            self.update_reference_lines()
            return
        if "MG" in mods and self._apply_mg_protocol():
            return
        if self._apply_hanging_protocol(usable, mods):
            # Protocolo escrito manda. Então a memória também não **grava** este exame: guardar
            # uma grade que nunca vai ser aplicada é juntar lixo que parece configuração.
            self._arranjo_de_protocolo = True
            return
        if mods == {"MG"} and len(usable) >= 2:
            def key(s: SeriesRow) -> tuple:
                d = s.description.upper()
                view = 0 if "CC" in d else 1
                lat = 0 if d.startswith("R") or " R " in f" {d} " else 1
                return (view, lat, s.series_number)
            self.series.sort(key=key)
            self._fill_strip()
            self.set_layout(2, 2) if len(usable) >= 3 else self.set_layout(1, 2)
        elif self.layout_lembrado() is not None:
            self.set_layout(*self.layout_lembrado())
        elif len(usable) >= 2 and self._layout == (1, 1):
            self.set_layout(1, 2)
        else:
            self.set_layout(*self._layout)
        for vp in self.viewports[: self._layout[0] * self._layout[1]]:
            if not vp.series_uid:
                for uid in self._auto_items():
                    if uid not in {v.series_uid for v in self.viewports}:
                        self.load_series_into(vp, uid)
                        break
        if self.viewports:
            self._activate(self.viewports[0])
        self.update_reference_lines()

    # ------------------------------------------------- estado salvo da análise (0.99.58)
    def estado_pode(self) -> bool:
        """Reabrir e guardar o estado só quando quem montou o exame foi ele — não um protocolo, uma escolha de
        séries, a divisão entre monitores ou a mamografia."""
        return not (self.series_filter or self.plano_do_monitor or self.mg_monitor is not None
                    or self.mg_session is not None or self.exib is not None or self.case_label
                    or getattr(self, "_nao_guardar_estado", False))

    def guardar_estado(self) -> bool:
        from ipe.ui.viewer import estado_analise as EA
        if not self.estado_pode():
            return False
        try:
            dados = EA.capturar(self)
            if not EA.vale_a_pena(dados):
                return False
            self.repo.salvar_estado(self.study_uid, dados, EA.usuario_atual())
            return True
        except Exception:  # noqa: BLE001
            log.exception("guardar o estado da análise")
            return False

    def estado_salvo(self) -> dict | None:
        from ipe.ui.viewer import estado_analise as EA
        try:
            return self.repo.estado(self.study_uid, EA.usuario_atual())
        except Exception:  # noqa: BLE001
            log.exception("ler o estado da análise")
            return None

    def restaurar_estado_ao_abrir(self, forcar: bool = False) -> bool:
        """Ao abrir: reabre como ele deixou (Configurações ▸ Visualizador ▸ Estado da análise)."""
        from ipe.ui.viewer import estado_analise as EA
        modo = str(self.settings.get(EA.CHAVE_AO_ABRIR, "sempre") or "sempre")
        if not forcar and (modo == "nunca" or not self.estado_pode()):
            return False
        e = self.estado_salvo()
        if not e or not EA.vale_a_pena(e.get("dados") or {}):
            return False
        quando = e.get("atualizado_em", "")
        quando_txt = f"{quando[8:10]}/{quando[5:7]} {quando[11:16]}" if len(quando) >= 16 else quando
        if not forcar and modo == "perguntar" and QMessageBox.question(
                self, "Estado da análise", f"Reabrir este exame como você deixou ({quando_txt})?") != QMessageBox.Yes:
            return False
        avisos = EA.restaurar(self, e["dados"])
        self._estado_restaurado = e
        dica = []
        if (e["dados"].get("dinamica") or None):
            dica.append("a dinâmica religa em Exibir ▸ Estado da análise")
        if (e["dados"].get("mpr") or None):
            dica.append("o MPR estava ligado (botão MPR)")
        self.status_message.emit(f"Reaberto como você deixou em {quando_txt}"
                                 + ("; " + "; ".join(dica + avisos) if dica or avisos else "") + ".")
        return True

    def esquecer_estado(self) -> None:
        """Volta ao arranjo de fábrica e não guarda o estado desta vez."""
        from ipe.ui.viewer import estado_analise as EA
        try:
            self.repo.esquecer_estado(self.study_uid, EA.usuario_atual())
        except Exception:  # noqa: BLE001
            log.exception("esquecer o estado")
        self._nao_guardar_estado = True
        self._estado_restaurado = None
        self._initial_hanging()
        self.status_message.emit("Arranjo de fábrica; o estado deste exame foi esquecido.")

    def religar_dinamica_salva(self) -> bool:
        e = getattr(self, "_estado_restaurado", None) or self.estado_salvo() or {}
        params = (e.get("dados") or {}).get("dinamica")
        if not params:
            return False
        return self.open_dynamic(previous=params)

    # ------------------------------------------------- memória do layout (sem configurar nada)
    def etiqueta_do_layout(self) -> str:
        """Que “tipo de exame” é este, para a memória do layout. Vazio = não lembrar."""
        from ipe.ui.viewer import memoria_layout as ML
        # Protocolo de exibição e modo mamografia têm arranjo **declarado**, que manda: a memória
        # não entra nem para ler nem para gravar, senão as duas coisas brigam.
        if self.plano_do_monitor or self.mg_monitor is not None or self.series_filter:
            return ""
        if getattr(self, "_arranjo_de_protocolo", False):
            return ""
        info = self.study_infos.get(self.study_uid, self.study_info) or {}
        mods = {s.modality for s in self.series if s.num_images and s.modality}
        if "MG" in mods:
            return ""                      # mamografia é das etapas, não da memória
        # Exame repartido entre monitores: cada tela tem a sua memória, e a quantidade de telas
        # entra na etiqueta — a grade que serve numa tela só não é a que serve em duas.
        return ML.chave(mods, info.get("description", "")) + ML.sufixo_das_telas(
            self.mg_telas, self.monitor_idx)

    def layout_lembrado(self):
        from ipe.ui.viewer import memoria_layout as ML
        return ML.lembrado(self.settings, self.etiqueta_do_layout())

    def guardar_layout(self) -> None:
        """Chamado quando a aba fecha: a grade com que ele terminou vira o padrão do tipo.

        Guardar no fim, e não a cada mudança, é de propósito: o que interessa é o arranjo em que
        ele ficou, não o 1×1 de dois segundos que ele usou para olhar um detalhe.
        """
        from ipe.ui.viewer import memoria_layout as ML
        etiqueta = self.etiqueta_do_layout()
        if not etiqueta:
            return
        if ML.lembrar(self.settings, etiqueta, self._layout):
            log.info("layout lembrado para %s: %s", etiqueta, self._layout)

    # ================================================================ mamografia
    def _apply_protocolo_etapas(self, mods: set) -> bool:
        """Protocolo de exibição com etapas (0.88): abre na etapa 1 — nesta tela, ou no pedaço dela
        que cabe a este monitor quando o exame foi repartido."""
        from ipe.ui.viewer import etapas as E
        proto = E.achar(self.settings, mods, self.study_info.get("description", ""))
        if proto is None:
            return False
        try:
            return E.iniciar(self, proto, self.monitor_idx, self.mg_telas)
        except Exception:  # noqa: BLE001
            log.exception("protocolo com etapas %r", proto.get("name"))
            self.exib = None
            return False

    def etapa_passo(self, d: int = 1) -> None:
        from ipe.ui.viewer import etapas as E
        E.passo(self, d)

    def gravar_tela_como_etapa(self) -> None:
        """Pergunta em que protocolo e com que nome, e grava a tela como etapa."""
        from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
                                       QRadioButton)

        from ipe.ui.viewer import etapas as E
        from ipe.ui.viewer import hanging as H
        etapa = E.gravar_tela(self)
        mods = sorted({s.modality for s in self.series if s.study_uid == self.study_uid and s.modality})
        mod = next((m for m in mods if m not in ("SR", "PR", "KO", "SEG")), mods[0] if mods else "")
        desc = self.study_info.get("description", "") or ""
        dlg = QDialog(self)
        dlg.setWindowTitle("Gravar a tela como etapa")
        proto = QComboBox()
        novo = f"{mod} — {desc}".strip(" —") or "Novo protocolo"
        atual = self.exib.nome if self.exib is not None else ""
        for p in H.protocols(self.settings):
            if p.get("modality", "").upper() == mod.upper():
                proto.addItem(p.get("name", ""), p.get("name", ""))
        proto.addItem(f"Novo protocolo: {novo}", "__novo__")
        proto.setCurrentIndex(max(0, proto.findData(atual)))
        nome = QLineEdit(f"Etapa {len(self.exib.steps) + 1}" if self.exib is not None else "Etapa 1")
        acrescentar = QRadioButton("Acrescentar como etapa nova")
        acrescentar.setChecked(True)
        substituir = QRadioButton("Substituir a etapa que está na tela")
        substituir.setEnabled(self.exib is not None)
        f = QFormLayout(dlg)
        f.addRow("Protocolo:", proto)
        f.addRow("Nome da etapa:", nome)
        f.addRow(acrescentar)
        f.addRow(substituir)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        f.addRow(bb)
        self._dlg_gravar = dlg
        if not dlg.exec():
            return
        etapa["name"] = nome.text().strip() or "Etapa"
        alvo = proto.currentData()
        nome_proto = novo if alvo == "__novo__" else alvo
        trocar = self.exib.indice if (substituir.isChecked() and self.exib is not None
                                      and self.exib.nome == nome_proto) else None
        gravado = E.salvar_etapa(self.settings, etapa, nome_proto, mod, desc if alvo == "__novo__" else "",
                                 trocar)
        indice = trocar if trocar is not None else len(gravado["steps"]) - 1
        self.exib = E.Sessao(gravado, self.monitor_idx, self.mg_telas)
        self.exib.indice = indice
        E.sincronizar_barra(self)
        self.status_message.emit(f"Etapa “{etapa['name']}” gravada em “{nome_proto}” "
                                 f"({len(gravado['steps'])} etapa(s)).")

    def editar_protocolos(self) -> None:
        from ipe.ui.viewer import etapas as E
        from ipe.ui.viewer import hanging as H
        from ipe.ui.viewer.protocolos_editor import ProtocolosDialog
        if not ProtocolosDialog(self.settings, self).exec() or self.exib is None:
            return
        p = next((x for x in H.protocols(self.settings) if x.get("name") == self.exib.nome), None)
        if p is None or not H.tem_etapas(p):
            E.encerrar(self)
            return
        i = self.exib.indice
        self.exib = E.Sessao(p, self.monitor_idx, self.mg_telas)
        E.aplicar_etapa(self, min(i, len(self.exib.steps) - 1), propagar=False)

    def plano_no_quadro(self, vp: Viewport, uid: str, nome: str, frames: list | None = None,
                        chave: str | None = None, rotulo: str = "") -> bool:
        """Reconstrói o plano `nome` da série no quadro, **sem perguntar nada** (é o protocolo que
        pede, ao abrir o exame). Volume acima do limite de memória fica de fora, com aviso.
        `frames`/`chave`: de uma fase da dinâmica (0.90)."""
        vol = self._volume_for(vp, uid, perguntar=False, frames=frames, chave=chave)
        if vol is None:
            self.status_message.emit(f"Reconstrução {nome}: o volume desta série não coube no limite de "
                                     "memória (Preferências ▸ Desempenho) ou não forma volume.")
            return False
        plane = next((MPRPlane(vol, ax) for ax in (0, 1, 2) if MPRPlane(vol, ax).name == nome), None)
        if plane is None:
            return False
        center = None
        if vp._img is not None:
            h, w = vp._img.pixels.shape[:2]
            center = vp.pixel_to_patient(w / 2, h / 2)
        if center is None:
            center = vol.voxel_to_patient(vol.shape[2] / 2, vol.shape[1] / 2, vol.shape[0] / 2)
        s = self._series_row(uid)
        study_uid = s.study_uid if s else self.study_uid
        width, level, win_set = vp.state.width, vp.state.level, vp.state.window_set
        vp.mpr_plane = plane
        vp.study_uid = study_uid
        vp.modality = s.modality if s else ""
        vp.key_frames = self.key_set
        vp.set_series(f"mpr:{uid}:{plane.axis}", plane.frames(), rotulo or f"{plane.name} (reconstrução)",
                      self.study_infos.get(study_uid, self.study_info), start_index=plane.index_for_point(center))
        if win_set:
            vp.set_window(width, level, emit=False)
        vp.anonymize = self.anonymize
        self._update_mpr_bar()
        return True

    def _apply_mg_protocol(self) -> bool:
        from ipe.imaging.mammo import find_mg_protocol
        proto = find_mg_protocol(self.settings, self.study_info.get("description", ""))
        if proto is None:
            log.info("mamografia: nenhum protocolo combina com %r",
                     self.study_info.get("description", ""))
            return False
        try:
            if self.start_mg(proto):
                return True
            log.info("mamografia: protocolo %r não subiu (sem imagens com lado reconhecido)",
                     proto.get("name"))
            return False
        except Exception as e:  # noqa: BLE001
            log.warning("protocolo de mamografia falhou: %s", e)
            self.mg_session = None
            return False

    def start_mg(self, proto: dict, propagar: bool = True) -> bool:
        """Levanta o modo mamografia com este protocolo — e nos outros monitores do conjunto.

        Os monitores são uma estação só: trocar de protocolo numa tela troca em todas, senão o
        arranjo deixa de ser um arranjo.
        """
        from ipe.ui.viewer.mammo_view import MgSession
        s = MgSession(self, proto)
        if not s.has_images():
            return False
        self.mg_session = s
        self.hanging_name = proto.get("name", "")
        s.apply_step(0)
        if propagar:
            for t in self.irmaos():
                t.start_mg(proto, propagar=False)
        return True

    def mg_step(self, i: int, propagar: bool = True) -> None:
        """Vai para a etapa `i` — **em todos os monitores do conjunto**, ao mesmo tempo."""
        if self.mg_session is None:
            return
        self.mg_session.apply_step(i)
        self._sync_mg_bar()
        if propagar:
            for t in self.irmaos():
                if t.mg_session is not None:
                    t.mg_step(i, propagar=False)

    def mg_next(self, d: int = 1) -> None:
        if self.mg_session is None and getattr(self, "exib", None) is not None:
            self.etapa_passo(d)                       # 0.88: protocolo com etapas de TC, RM…
            return
        if self.mg_session is None:
            from ipe.imaging.mammo import find_mg_protocol
            p = find_mg_protocol(self.settings, self.study_info.get("description", ""))
            if p is not None and self.start_mg(p):
                return
            # Desde a 0.65 quem chama isto são as setas ← →. Num exame que não é mamografia a
            # seta não tem o que fazer, e avisar a cada toque seria ruído: o aviso fica para
            # quando o exame **é** MG e o que falta é o protocolo.
            if "MG" in (self.study_info.get("modalities") or ""):
                self.status_message.emit("Sem protocolo de mamografia para este exame.")
            return
        self.mg_step(self.mg_session.step + d)

    def fase_passo(self, d: int = 1) -> None:
        """Próxima/anterior fase da dinâmica no quadro ativo (as setas deixaram de fazer isso)."""
        vp = self.active
        if vp is None or not getattr(vp, "phases", None):
            self.status_message.emit("Este quadro não tem fases: não é uma dinâmica.")
            return
        vp.set_phase(vp.phase + d, wrap=True)

    def close_mg(self) -> None:
        self.mg_session = None
        for v in self.viewports:
            v.mg_cell = None
            v.align_edge = None
            v.update()
        self._sync_mg_bar()

    def _sync_mg_bar(self) -> None:
        if hasattr(self, "mg_bar"):
            self.mg_bar.sync()

    def mg_cells(self, vp):
        """O quadro e, no protocolo de mamografia com zoom junto, os outros quadros de mamografia."""
        if vp is None:
            return []
        out = [vp]
        s = self.mg_session
        if s is not None and s.proto.get("sync_zoom", True) and vp.mg_cell is not None:
            out += [v for v in self._shown() if v is not vp and v.mg_cell is not None and v.frames]
        return out

    def mg_quadrant(self, vp, idx: int) -> None:
        """Zoom no quadrante da mama (posterior/anterior × superior/inferior) e, no protocolo, nos outros
        quadros — cada um no seu próprio quadrante, já que a parede torácica troca de lado."""
        for t in self.mg_cells(vp):
            t.zoom_to_anat_quadrant(idx)
            t.quad_idx = idx

    def _enquadre_pendente(self, _vp=None) -> None:
        """Um quadro mudou de tamanho: refaz o enquadramento da mamografia, **do conjunto**.

        Junta os pedidos num disparo só (a montagem do layout redimensiona todos os quadros, um
        atrás do outro) e refaz o grupo inteiro, para as duas mamas continuarem na mesma escala.
        """
        t = getattr(self, "_timer_enquadre", None)
        if t is None:
            t = self._timer_enquadre = QTimer(self)
            t.setSingleShot(True)
            t.setInterval(50)
            t.timeout.connect(self._refazer_enquadre)
        t.start()

    def _refazer_enquadre(self) -> None:
        s = self.mg_session
        if s is None:
            for vp in self.viewports:
                lock = getattr(vp, "anat_lock", None)
                if lock and lock[0] == "mama":
                    vp.enquadrar_na_mama(None, lock[2])
            return
        s.enquadrar(so_pendentes=True)

    def mg_enquadrar(self) -> None:
        """Reenquadra a mamografia da tela (Alt+Q / botão "Mama no quadro").

        O protocolo já enquadra ao abrir cada etapa; isto é o modo manual de reserva, para depois
        de mexer no zoom à mão — e funciona também sem protocolo, quadro por quadro.
        """
        s = self.mg_session
        if s is not None:
            modo = s.enquadrar()
            from ipe.imaging import mammo as M
            self.status_message.emit(f"Enquadrado: {M.ENQUADRES.get(modo, modo)}")
            return
        feitos = 0
        for vp in self.viewports:
            if vp._img is not None and (vp.modality or "").upper() == "MG" and vp.enquadrar_na_mama():
                feitos += 1
        if feitos:
            self.status_message.emit(f"Mama enquadrada em {feitos} quadro(s).")
        else:
            self.status_message.emit("Não achei a mama nos quadros desta tela.")

    def mg_quadrant_cycle(self, vp, d: int = 1) -> None:
        """Cada clique vai para o próximo: posterior+superior → posterior+inferior → imagem inteira."""
        from ipe.ui.viewer.mammo_view import QUAD_NAMES
        if vp is None or vp._img is None:
            return
        n = len(QUAD_NAMES)
        cur = vp.quad_idx if vp.state.zoom > 1.05 else -1
        new = (cur + 1 + d) % (n + 1) - 1
        self.mg_quadrant(vp, new)
        self.status_message.emit("Zoom: imagem inteira" if new < 0
                                 else f"Zoom: quadrante {QUAD_NAMES[new]}")

    def mg_sync_view(self, vp, kind: str) -> None:
        """Zoom/pan num quadro de mamografia: com o botão de sincronia **Zoom e pan** ligado, os outros
        mostram o mesmo lugar da mama (espelhado na outra mama, e valendo para 2D, tomossíntese e
        recombinada). Desligado, cada quadro anda sozinho — como nos outros exames (0.97.1). A opção
        do protocolo ("Zoom por quadrante em todos os quadros juntos") vale só para o zoom por
        quadrante (Q)."""
        if kind not in ("zoom", "pan") or vp is None or vp.mg_cell is None:
            return
        if self.mg_session is None or not self.hub.sync_zoom or getattr(self, "_mg_syncing", False):
            return
        ponto = vp.anat_center()
        if ponto is None:
            return
        self._mg_syncing = True
        try:
            outros = [t for t in self.hub.viewports(self) if t is not vp and t.mg_cell is not None and t.frames]
            for t in outros:
                if t._img is None:
                    continue
                t.show_anat(ponto[0], ponto[1], vp.state.zoom,
                            lock=getattr(vp, "anat_lock", None) is not None)
                t.quad_idx = vp.quad_idx
        finally:
            self._mg_syncing = False

    def mg_toggle_tomo(self) -> None:
        vp = self.active
        if self.mg_session is None or vp is None or getattr(vp, "mg_spec", None) is None:
            self.status_message.emit("2D / tomo: só nos quadros do protocolo de mamografia.")
            return
        self.mg_session.toggle_tomo(vp)

    def mg_toggle_cem(self) -> None:
        vp = self.active
        if self.mg_session is None or vp is None or getattr(vp, "mg_spec", None) is None:
            self.status_message.emit("Baixa energia ⇄ recombinada: só nos quadros do protocolo de mamografia.")
            return
        self.mg_session.toggle_rec(vp)

    def mg_densidade(self) -> None:
        """Densidade das imagens que estão na tela. A janela lê os quadros visíveis desta aba."""
        from ipe.ui.densidade_dialog import DensidadeDialog
        DensidadeDialog(self, self).exec()

    def mg_set_implant(self, on: bool) -> None:
        """Implante "apagado" em todos os quadros de mamografia (ou no ativo, fora do protocolo)."""
        self.mg_implant = on
        a = getattr(self.mg_bar, "a_implant", None)
        if a is not None and a.isChecked() != on:
            a.blockSignals(True)
            a.setChecked(on)
            a.blockSignals(False)
        targets = [v for v in self._shown() if v.frames and (v.mg_cell is not None or (v.modality or "") == "MG")]
        if not targets and self.active is not None:
            targets = [self.active]
        for v in targets:
            v.set_implant_mask(on)
        if on:
            self.salvar_implante([v for v in targets if v.implant_found])
            found = sum(1 for v in targets if v.implant_found)
            motivos = [v.implant_motivo for v in targets if not v.implant_found and getattr(v, "implant_motivo", "")]
            if found and motivos and found + len(motivos) == len(targets):
                self.status_message.emit(f"Implante corrigido em {found} quadro(s); nos outros {len(motivos)} não "
                                         f"procurei: {motivos[0]}.")
            elif not found and motivos and len(motivos) == len(targets):
                self.status_message.emit(f"Não procurei o implante: {motivos[0]}. Se houver prótese, clique com "
                                         "o botão direito dentro do silicone → “Achar o implante a partir daqui”.")
            elif found == len(targets):
                self.status_message.emit(f"Implante corrigido em {found} quadro(s).")
            elif found:
                self.status_message.emit(
                    f"Implante corrigido em {found} de {len(targets)} quadro(s). Nos outros, clique com o "
                    "botão direito dentro do silicone → “Achar o implante a partir daqui”.")
            else:
                self.status_message.emit(
                    "Não achei a prótese sozinho. Clique com o botão direito dentro do silicone → "
                    "“Achar o implante a partir daqui”.")
        else:
            self.status_message.emit("Implante mostrado como veio do aparelho.")

    def _implant_changed(self, vp) -> None:
        """Alguém apagou (ou mostrou) o implante num quadro pelo botão direito."""
        self.mg_implant = bool(vp.implant_mask)
        a = getattr(self.mg_bar, "a_implant", None)
        if a is not None and a.isChecked() != self.mg_implant:
            a.blockSignals(True)
            a.setChecked(self.mg_implant)
            a.blockSignals(False)
        if vp.implant_mask:
            self.status_message.emit("Implante corrigido neste quadro." if vp.implant_found
                                     else "Não consegui separar a prótese a partir desse ponto — "
                                          "tente um ponto mais no meio do silicone.")
            if vp.implant_found:
                self.salvar_implante([vp])

    def objetos_da_coluna(self, vp=None) -> list:
        estudo = getattr(vp, "study_uid", "") or self.study_uid
        return [o for o in self.overlay_objects
                if getattr(o, "source", "") == "Coluna" and o.study_uid in ("", estudo)]

    def guardar_coluna(self, o, estudo: str = "", conferido: bool = False) -> None:
        """Depois de renumerar ou ajustar: o SEG guardado (reabrir vem certo), a tabela das medidas e,
        se ele conferiu, a numeração do exame (aviso no próximo exame do paciente)."""
        from ipe.ai import coluna as COL
        caminho = getattr(o, "caminho", "")
        estudo = estudo or o.study_uid or self.study_uid
        if caminho:
            try:
                COL.salvar_no_seg(caminho, o)
                storage = getattr(self, "storage_root", None)
                if storage is not None and COL.config(self.settings, COL.CHAVE_MEDIR) and \
                        COL.tem_tabela(self.repo, estudo):
                    COL.gravar_tabela(self.repo, self.repo.db, storage, estudo, caminho, obj=o)
            except Exception:  # noqa: BLE001
                log.exception("guardar a numeração da coluna")
        if conferido:
            from ipe.auth import session as S
            try:
                quem = S.get().username or ""
            except Exception:  # noqa: BLE001
                quem = ""
            COL.guardar_conferencia(self.repo, estudo, o.numeracao, quem)

    def _coluna_mudou(self, o=None) -> None:
        """Refaz a tela depois de renumerar/ajustar — **em todas as abas e janelas** com este exame.

        0.99.23.1, relato dele: *"mudei a nomenclatura (L5 sacralizada) mas não mudou nada no viewer"*.
        Cada monitor tem a sua aba, com os seus objetos lidos do SEG; mudar o objeto da aba em que ele
        clicou deixava as outras telas com o nome antigo. E um objeto repetido na mesma aba (o mesmo SEG
        lido duas vezes) desenhava o rótulo velho por cima, porque o primeiro rótulo do lugar ganha."""
        from ipe.ai import coluna as COL
        caminho = getattr(o, "caminho", "") if o is not None else ""
        abas = [self]
        from PySide6.QtWidgets import QApplication
        # a janela principal **desta** aba (com várias janelas vivas — testes, outra sessão —, a primeira
        # da lista podia ser outra)
        for w in [self.window(), *QApplication.topLevelWidgets()]:
            f = getattr(w, "all_viewer_tabs", None)
            if not callable(f):
                continue
            try:
                todas = list(f())
            except Exception:  # noqa: BLE001
                log.exception("abas abertas")
                continue
            if self in todas or w is self.window():
                abas += [t for t in todas if t is not self]
                break
        for t in abas:
            objs = getattr(t, "overlay_objects", None)
            if objs is None:
                continue
            if caminho:
                novo = []
                for x in objs:
                    if getattr(x, "source", "") == "Coluna" and getattr(x, "caminho", "") == caminho:
                        if t is self:
                            if x is o:
                                novo.append(x)
                            continue                 # repetido nesta aba: sai, fica o que mudou
                        try:
                            x = COL.objeto_do_seg(caminho, x.study_uid)
                            x.enabled = True
                        except Exception:  # noqa: BLE001
                            log.exception("reler a coluna em outra aba")
                    novo.append(x)
                if t is self and o not in novo:
                    novo.append(o)
                objs[:] = novo
            if hasattr(t, "_apply_overlays"):
                t._apply_overlays()
            for v in getattr(t, "viewports", []):
                v.update()

    def renumerar_coluna(self, vp, passo: int) -> int:
        """Níveis da coluna ±1 (0.99.2): todos os nomes andam um nível, na tela e no SEG guardado — ao
        reabrir o exame já vem certo. Devolve quantos objetos mudaram. 0.99.23: recusa, dizendo, quando
        um nível sairia da coluna (antes parava em S1 e dava duas S1)."""
        from ipe.ai import coluna as COL
        n = 0
        vistos, mudados = set(), []
        for o in self.objetos_da_coluna(vp):
            chave = getattr(o, "caminho", "") or id(o)
            if chave in vistos:
                continue                              # o mesmo SEG lido duas vezes: renumera um só
            vistos.add(chave)
            try:
                COL.renumerar(o, passo)
            except COL.ForaDaColuna as e:
                self.status_message.emit(f"Não renumerei: {e}.")
                return 0
            self.guardar_coluna(o, getattr(vp, "study_uid", ""))
            mudados.append(o)
            n += 1
        for o in mudados:
            self._coluna_mudou(o)
        if n:
            self.status_message.emit("Níveis da coluna renumerados: " + ("um nível para baixo." if passo > 0
                                                                         else "um nível para cima."))
        return n

    def abrir_numeracao_coluna(self, vp, ponto=None):
        """Botão direito ▸ Numeração da coluna ▸ Ajustar… (0.99.23): a janela abre com a vértebra que
        estava sob o clique."""
        from ipe.ui.viewer.coluna_numeracao import NumeracaoDialog
        objs = self.objetos_da_coluna(vp)
        if not objs:
            self.status_message.emit("Esta aba não tem os níveis da coluna identificados.")
            return None
        o = objs[-1]
        clicada = None
        if ponto is not None:
            for mv in o.volumes:
                if "-" not in str(getattr(mv, "nivel", mv.label)) and mv.contem(ponto, folga=1):
                    clicada = getattr(mv, "nivel", None)
                    break
        dlg = NumeracaoDialog(self, o, clicada=clicada, repo=self.repo, study_uid=o.study_uid or self.study_uid)

        def aplicado():
            self.guardar_coluna(o, o.study_uid or self.study_uid, conferido=True)
            self._coluna_mudou(o)
            self.status_message.emit("Numeração da coluna conferida: " + __import__(
                "ipe.ai.coluna", fromlist=["descrever"]).descrever(o.numeracao) + ".")
        dlg.aplicado.connect(aplicado)
        dlg.laudo.connect(lambda txt: self.mandar_texto_ao_laudo(txt))
        dlg.show()
        self._numeracao_dlg = dlg
        return dlg

    def mandar_texto_ao_laudo(self, texto: str) -> None:
        ok = False
        try:
            ok = bool(hasattr(self, "append_to_report") and self.append_to_report(texto))
        except Exception:  # noqa: BLE001
            log.exception("mandar ao laudo")
        if not ok:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(texto)
            self.status_message.emit("Sem laudo aberto: a frase foi copiada.")

    def abrir_estruturas(self, vp=None):
        """O painel Estruturas (0.99.40): editar, organizar e gravar máscaras (SEG / RTSTRUCT)."""
        from ipe.ui.viewer.estruturas_painel import abrir
        return abrir(self, vp or self.active)

    def pincel_estruturas(self, vp, u: float, v: float, etapa: str) -> None:
        painel = getattr(self, "_estruturas", None)
        try:
            import shiboken6
            vivo = painel is not None and shiboken6.isValid(painel) and painel.isVisible()
        except Exception:  # noqa: BLE001
            vivo = painel is not None
        if not vivo:
            if etapa == "ini":
                self.status_message.emit("Pincel: abra o painel Estruturas (3D ▸ Estruturas) para escolher o que pintar.")
            return
        painel.pincel(vp, u, v, etapa)

    def abrir_difusao(self):
        """O painel da difusão (0.99.37): ADC, DWI sintética e a tabela por ROI."""
        from ipe.ui.viewer.difusao_painel import abrir
        return abrir(self)

    def abrir_achados(self, achado_id: int | None = None):
        """Achados de IA (0.99.46): a lista revisável do exame."""
        from ipe.ui.viewer.achados_painel import abrir
        return abrir(self, achado_id if isinstance(achado_id, int) and not isinstance(achado_id, bool) else None)

    def _nodulos_do_ativo(self):
        return self.nodulos_automatico(self.active)

    def nodulos_automatico(self, vp=None, simular: bool = False):
        """Procura nódulos pulmonares na série do quadro (TotalSegmentator lung_nodules)."""
        vp = vp or self.active or next((v for v in self.viewports if v.frames), None)
        if vp is None:
            return None
        return self.segmentar_orgaos(vp, simular=simular, tipo="nodulos")

    def _composicao_do_ativo(self):
        return self.composicao_automatica(self.active)

    def composicao_automatica(self, vp=None, simular: bool = False):
        vp = vp or self.active or next((v for v in self.viewports if v.frames), None)
        if vp is None:
            return None
        return self.segmentar_orgaos(vp, simular=simular, tipo="composicao")

    def composicao_botao(self):
        try:
            tem = any(self.repo.achados(u, "composicao") for u in (getattr(self, "study_order", None) or [self.study_uid]))
        except Exception:  # noqa: BLE001
            tem = False
        if tem:
            return self.abrir_achados()
        return self.composicao_automatica(self.active)

    def _figado_rm_do_ativo(self):
        return self.figado_rm_automatico(self.active)

    def figado_rm_automatico(self, vp=None, simular: bool = False):
        """Fígado na RM (0.99.49): a IA roda na série anatômica escolhida pela regra (o fígado vem dela) e
        mede nos mapas do aparelho. O quadro ativo só decide o exame."""
        from ipe.ai import figado_rm as FR
        from ipe.core.i18n import tr
        vp = vp or self.active or next((v for v in self.viewports if v.frames), None)
        if vp is None:
            return None
        uid = vp.study_uid or self.study_uid
        serie, motivo = FR.escolher_serie(self.repo, uid, self.settings)
        alvo = vp
        if serie and serie != vp.series_uid:
            alvo = next((v for v in self.viewports if v.series_uid == serie), None)
            if alvo is None:
                alvo = vp
                self.load_series_into(vp, serie)
        elif not serie:
            self.status_message.emit(tr(f"Fígado na RM: {motivo} — uso a série do quadro ativo."))
        return self.segmentar_orgaos(alvo, simular=simular, tipo="figado_rm")

    def figado_rm_botao(self):
        try:
            tem = any(self.repo.achados(u, "figado_rm") for u in (getattr(self, "study_order", None) or [self.study_uid]))
        except Exception:  # noqa: BLE001
            tem = False
        if tem:
            return self.abrir_achados()
        return self.figado_rm_automatico(self.active)

    def nodulos_botao(self):
        """O botão: com achados no exame, abre a lista; sem, procura na série do quadro ativo."""
        try:
            tem = any(self.repo.achados(u, "nodulos") for u in (getattr(self, "study_order", None) or [self.study_uid]))
        except Exception:  # noqa: BLE001
            tem = False
        if tem:
            return self.abrir_achados()
        return self.nodulos_automatico(self.active)

    def achados_mudaram(self) -> None:
        p = getattr(self, "achados_painel", None)
        if p is not None:
            try:
                p.recarregar()
            except RuntimeError:
                self.achados_painel = None

    def abrir_tarefas_ia(self):
        """A janela "Tarefas de IA" (0.99.32): uma só para o programa todo."""
        from ipe.ui.tarefas_ia import abrir
        return abrir(self.window())

    def segmentar_orgaos(self, vp, simular: bool = False, tipo: str = "abdome"):
        """Quadro ▸ botão direito ▸ Segmentar órgãos abdominais (0.98) ou Identificar vértebras e discos
        (tipo="coluna", 0.99.2): a série do quadro vai para o TotalSegmentator; ao terminar, o resultado
        entra nas sobreposições desta aba."""
        from ipe.ui.segmentacao import Segmentacao, carregar_na_aba
        f = vp.current_frame() if vp is not None else None
        storage = getattr(self, "storage_root", None)
        if f is None or not f.series_uid or storage is None:
            return None
        seg = Segmentacao(self, self.repo, self.settings, storage, vp.study_uid or self.study_uid,
                          f.series_uid, cache=self.cache, simular=simular, tipo=tipo)
        net, repo, settings = getattr(self, "net", None), self.repo, self.settings

        def pronto(saida, msg):
            if not seg.janela_viva():
                # 0.99.34: o exame foi fechado enquanto rodava. O resultado já está gravado no exame
                # (aparece ao abrir de novo); só falta mandar aos destinos de CAD/IA.
                if saida is not None and saida.get("ferramenta") and net is not None:
                    try:
                        from ipe.ai import ferramentas as FE
                        from ipe.automation import destinos as DEST
                        mod = FE.modulo(saida["ferramenta"])
                        DEST.enviar(net, repo, seg.trabalho.study_uid, saida.get("series"),
                                    mod.config(settings, mod.CHAVE_DESTINOS), mod.TITULO)
                    except Exception:  # noqa: BLE001
                        log.exception("enviar os achados aos destinos (exame fechado)")
                    return
                if saida is not None and tipo in ("abdome", "coluna") and net is not None:
                    try:
                        from ipe.ai import coluna as COL
                        from ipe.ai import totalseg as TS
                        from ipe.automation import destinos as DEST
                        destinos = (COL.config(settings, COL.CHAVE_DESTINOS) if tipo == "coluna"
                                    else TS.config(settings, TS.CHAVE_DESTINOS))
                        DEST.enviar(net, repo, seg.trabalho.study_uid, saida.get("series"), destinos,
                                    "Níveis da coluna" if tipo == "coluna" else "Órgãos abdominais")
                    except Exception:  # noqa: BLE001
                        log.exception("enviar a segmentação aos destinos (exame fechado)")
                return
            if saida is not None and tipo == "cefalometria":
                carregar_na_aba(self, saida)
                self.status_message.emit(msg)
                self.abrir_cefalometria(saida.get("cefalometria"), automatica=True)
                QMessageBox.information(self, seg.titulo, msg)
                return
            if saida is not None and tipo == "linfonodos":
                carregar_na_aba(self, saida)
                from ipe.ai import linfonodos as LN
                self.overlay_objects[:] = [o for o in self.overlay_objects if o.source != LN.FONTE_OVERLAY]
                self.overlay_objects.append(saida["mapa"])
                self.marcos_linfonodais = saida["linfonodos"]
                if hasattr(self, "_apply_overlays"):
                    self._apply_overlays()
                self.status_message.emit(msg)
                QMessageBox.information(self, seg.titulo, msg)
                return
            if saida is not None and saida.get("ferramenta"):          # 0.99.46: IAs do contrato comum
                carregar_na_aba(self, saida)
                from ipe.ai import ferramentas as FE
                from ipe.automation import destinos as DEST
                mod = FE.modulo(saida["ferramenta"])
                if mod is not None and DEST.enviar(self.net, self.repo, seg.trabalho.study_uid, saida.get("series"),
                                                   mod.config(self.settings, mod.CHAVE_DESTINOS), mod.TITULO):
                    msg += " Enviado também aos destinos escolhidos em Configurações ▸ CAD/IA."
                self.status_message.emit(msg)
                self.abrir_achados()
                QMessageBox.information(self, seg.titulo, msg)
                return
            if saida is not None and tipo == "neuro":
                carregar_na_aba(self, saida)
                self.status_message.emit(msg)
                self.abrir_neuro(saida.get("neuro"), automatica=True)
                QMessageBox.information(self, seg.titulo, msg)
                return
            if saida is not None:
                carregar_na_aba(self, saida)
                from ipe.ai import coluna as COL
                from ipe.ai import totalseg as TS
                from ipe.automation import destinos as DEST
                destinos = (COL.config(self.settings, COL.CHAVE_DESTINOS) if tipo == "coluna"
                            else TS.config(self.settings, TS.CHAVE_DESTINOS))
                if DEST.enviar(self.net, self.repo, seg.trabalho.study_uid, saida.get("series"), destinos,
                               "Níveis da coluna" if tipo == "coluna" else "Órgãos abdominais"):
                    msg += " Enviada também aos destinos escolhidos em Preferências ▸ CAD/IA."
                self.status_message.emit(msg)
                QMessageBox.information(self, seg.titulo, msg)
            elif msg != "Segmentação cancelada.":
                QMessageBox.warning(self, seg.titulo, msg)
            else:
                self.status_message.emit(msg)
        seg.terminou.connect(pronto)
        seg.iniciar()
        return seg

    def salvar_implante(self, vps: list) -> None:
        """Implante apagado na tela: confere se a imagem sem silicone já está no banco e, se não
        estiver, grava (0.97.1). Grava o que está na tela — com a prótese achada aqui, inclusive
        a do clique "a partir daqui". Em segundo plano; a tela não espera."""
        from ipe.automation import implante as IMP
        storage = getattr(self, "storage_root", None)
        if storage is None or self.repo is None or not IMP.config(self.settings, IMP.CHAVE_SALVAR_BOTAO):
            return
        pedidos = []
        for v in vps:
            f = v.current_frame()
            if f is None or f.is_virtual or not f.path or v.in_tomo() or not v.study_uid:
                continue
            info = v._implant_info(so_cache=True)
            if info is None:
                continue
            pedidos.append((v.study_uid, f.path, f.sop_uid, info[2].copy(), f.series_uid))
        if not pedidos:
            return
        repo, db = self.repo, self.repo.db

        def trabalho():
            return [IMP.salvar_uma(repo, db, storage, *p[:4]) for p in pedidos]

        def pronto(res, err) -> None:
            if err is not None:
                log.warning("salvar a imagem sem implante: %s", err)
                self.status_message.emit(f"Não consegui salvar a imagem sem o silicone: {err}")
                return
            novas = sum(1 for r in res if r == "salva")
            ja = sum(1 for r in res if r == "já estava salva")
            if novas:
                from ipe.automation import destinos as DEST
                por_estudo: dict = {}
                for p, r in zip(pedidos, res):
                    if r == "salva":
                        por_estudo.setdefault(p[0], set()).add(IMP.serie_da_copia(p[4]))
                for est, series in por_estudo.items():
                    DEST.enviar(self.net, self.repo, est, sorted(series),
                                IMP.config(self.settings, IMP.CHAVE_DESTINOS), "Sem implante")
            if novas:
                self.status_message.emit(f"Imagem sem o silicone salva no banco ({novas}"
                                         + (f"; {ja} já estava(m) salva(s)" if ja else "") + ").")
            elif ja:
                self.status_message.emit("A imagem sem o silicone já estava salva no banco.")
            self.implante_salvo.emit(novas)

        if self.net is not None:
            self.net.run_async(trabalho, pronto)
        else:
            try:
                pronto(trabalho(), None)
            except Exception as e:  # noqa: BLE001
                pronto(None, e)

    def mg_set_slab(self, n: int | None = None, mode: str | None = None) -> None:
        """Espessura da tomossíntese (em cortes). n = -1: próxima da lista; None: mantém (troca só o modo)."""
        from ipe.ui.viewer.mammo_view import SLAB_STEPS
        cur = getattr(self, "mg_slab", 1)
        if n == -1:
            n = SLAB_STEPS[(SLAB_STEPS.index(cur) + 1) % len(SLAB_STEPS)] if cur in SLAB_STEPS else SLAB_STEPS[0]
        elif n is None:
            n = cur
        self.mg_slab = n
        if mode:
            self.mg_slab_mode = mode
        mode = getattr(self, "mg_slab_mode", "mip")
        tomo = [v for v in self._shown() if getattr(v, "mg_tomo", False)]
        if not tomo:
            self.status_message.emit("Espessura: só nos quadros com tomossíntese (role até os cortes da tomo).")
        for v in tomo:
            v.set_tomo_slab(n, mode)
        btn = getattr(self.mg_bar, "slab_btn", None)
        if btn is not None:
            btn.setText("Espessura: fina ▾" if n == 1 else f"Espessura: {n} cortes {'MIP' if mode == 'mip' else 'média'} ▾")
        if tomo:
            self.status_message.emit("Tomossíntese: corte fino." if n == 1 else
                                     f"Tomossíntese: espessura de {n} cortes ({'MIP' if mode == 'mip' else 'média'}).")

    def load_frames_into(self, vp: Viewport, uid: str, frames: list, label: str, study_uid: str,
                         series_uid: str = "", start_index: int = 0) -> None:
        """Carrega uma lista de quadros escolhida (ex.: só as imagens de uma incidência da mamografia)."""
        meta = self.repo.series_meta(series_uid) if series_uid else None
        s = self._series_row(series_uid) if series_uid else None
        vp.mpr_plane = None
        QTimer.singleShot(0, self._update_mpr_bar)
        vp.for_uid = (meta or {}).get("frame_of_reference", "") or f"study:{study_uid}"
        vp.study_uid = study_uid
        vp.modality = s.modality if s else "MG"
        vp.key_frames = self.key_set
        vp.set_series(uid, frames, label, self.study_infos.get(study_uid, self.study_info), start_index=start_index)
        vp.left_tool = self.left_tool
        vp.anonymize = self.anonymize
        self.hub.leave(vp)
        self._activate(vp)

    def edit_mg_protocols(self) -> None:
        from ipe.ui.viewer.mammo_view import MgProtocolsDialog
        if MgProtocolsDialog(self.settings, self).exec() and self.mg_session is not None:
            from ipe.imaging.mammo import mg_protocols
            name = self.mg_session.proto.get("name")
            p = next((x for x in mg_protocols(self.settings) if x.get("name") == name), None)
            if p is not None:
                step = self.mg_session.step
                self.mg_session.proto = p
                self.mg_session.apply_step(min(step, max(0, len(self.mg_session.steps) - 1)))
            else:
                self._sync_mg_bar()

    def _aplicar_plano(self, usable: list) -> bool:
        """Monta esta tela segundo o plano que o monitor recebeu (layout + padrão de cada quadro).

        É o mesmo mecanismo do protocolo de exibição, só que a lista de quadros veio de fora —
        de `hanging.plano_de_monitores`, que sabe repartir as incidências entre as telas.
        """
        from ipe.ui.viewer.hanging import assign, series_words
        try:
            rows, cols = (int(x) for x in self.plano_do_monitor.get("layout", [1, 1]))
            cells = list(self.plano_do_monitor.get("cells", []))
            if not cells:
                return False
            cand = [(s.series_uid, *series_words(self.repo, s)) for s in usable]
            picks = assign(cells, cand)
            if not any(picks):
                return False
            self.set_layout(rows, cols)
            for i, uid in enumerate(picks[: rows * cols]):
                if uid:
                    self.load_series_into(self.viewports[i], uid)
            if self.viewports:
                self._activate(self.viewports[0])
            self.hanging_name = self.plano_do_monitor.get("nome", "")
            self.update_reference_lines()
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("plano do monitor falhou: %s", e)
            return False

    def _apply_hanging_protocol(self, usable: list, mods: set) -> bool:
        """Protocolo de exibição (Preferências → Protocolos): layout, séries em cada quadro e anterior."""
        from ipe.ui.viewer.hanging import assign, find_protocol, series_words
        proto = find_protocol(self.settings, mods, self.study_info.get("description", ""))
        if proto is None:
            return False
        try:
            rows, cols = (int(x) for x in proto.get("layout", [2, 2]))
            cells = list(proto.get("cells", []))
            cand = [(s.series_uid, *series_words(self.repo, s)) for s in usable]
            picks = assign(cells, cand)
            if not any(picks):
                return False
            prior = self._hanging_prior(proto) if proto.get("prior") else None
            use_compare = prior is not None and screen_with_role(self.settings, "compare") is not None \
                and self.settings.get("viewer.priors_on_compare", True)
            prior_picks: list = []
            if prior is not None and not use_compare:
                self.add_study_silent(prior)
                pser = [s for s in self.series if s.study_uid == prior and s.num_images]
                prior_picks = assign(cells, [(s.series_uid, *series_words(self.repo, s)) for s in pser])
                if any(prior_picks):
                    cols *= 2           # atual à esquerda, anterior à direita
            self.set_layout(rows, cols)
            half = cols // 2 if prior_picks and any(prior_picks) else cols
            for i, uid in enumerate(picks):
                r, c = divmod(i, half)
                if uid and r < rows:
                    self.load_series_into(self.viewports[r * cols + c], uid)
            if prior_picks and any(prior_picks):
                for i, uid in enumerate(prior_picks):
                    r, c = divmod(i, half)
                    if uid and r < rows:
                        self.load_series_into(self.viewports[r * cols + half + c], uid)
                for i in range(len(picks)):
                    r, c = divmod(i, half)
                    a, b = self.viewports[r * cols + c], self.viewports[r * cols + half + c]
                    if a.series_uid and b.series_uid:
                        self.hub.apply_saved(a, b)
            # quadros que sobraram: outras séries do exame
            free = [u for u in self._auto_items() if u not in {v.series_uid for v in self.viewports}]
            for vp in self.viewports[: rows * cols]:
                if not vp.series_uid and free:
                    self.load_series_into(vp, free.pop(0))
            if self.viewports:
                self._activate(self.viewports[0])
            self.hanging_name = proto.get("name", "")
            if use_compare:
                from PySide6.QtCore import QTimer as _T
                _T.singleShot(0, lambda: self.open_prior(prior))
            self.update_reference_lines()
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("protocolo de exibição falhou: %s", e)
            return False

    def _hanging_prior(self, proto: dict) -> str | None:
        """Anterior mais recente da mesma modalidade (só se este exame for o mais recente)."""
        mod = proto.get("modality", "").upper()
        date = self.study_info.get("study_date", "")
        others = [r for r in self.repo.other_studies_same_patient(self.study_uid)
                  if mod in (r.modalities or "").upper()]
        if any(r.study_date > date for r in others):
            return None                   # este já é um anterior: não encadeia
        older = sorted([r for r in others if r.study_date and r.study_date <= date], key=lambda r: r.study_date)
        return older[-1].study_uid if older else None

    def rescan(self, study_uid: str = "") -> bool:
        """Relê as séries do estudo (usado quando o exame está sendo baixado e continua chegando):
        atualiza a tira e acrescenta as imagens novas aos quadros já abertos, sem mexer na janela."""
        uids = [study_uid] if study_uid else list(self.study_order)
        changed = False
        for uid in uids:
            if uid not in self.study_order:
                continue
            rows = _image_series(self.repo.series_for_study(uid))
            by_uid = {s.series_uid: s for s in rows}
            old_rows = {s.series_uid: s for s in self.series if s.study_uid == uid}
            if {u: r.num_images for u, r in by_uid.items()} == {u: r.num_images for u, r in old_rows.items()}:
                continue
            changed = True
            if set(by_uid) - set(old_rows):
                # série nova (tabela, captura, cópia gravada pelo programa): miniatura e grupos (0.99.4)
                try:
                    from ipe.importer.thumbnails import miniaturas_que_faltam
                    if miniaturas_que_faltam(self.repo, uid):
                        rows = _image_series(self.repo.series_for_study(uid))
                        by_uid = {s.series_uid: s for s in rows}
                    self.groups.update({g["id"]: g for g in self.repo.series_groups(uid)})
                except Exception as e:  # noqa: BLE001
                    log.debug("miniatura da série nova: %s", e)
            self.series = [s for s in self.series if s.study_uid != uid] + rows
            for vp in self.viewports:
                uid_vp = vp.series_uid
                if not uid_vp or vp.mpr_plane is not None or uid_vp.startswith(("mpr:", "key:", "group:", "dyn")):
                    continue
                if uid_vp.startswith("mg:"):
                    continue
                row = by_uid.get(uid_vp)
                if row is None or row.num_images <= len(vp.frames):
                    continue
                frames = build_frames(self.repo.instances_for_series(uid_vp), uid_vp)
                if len(frames) <= len(vp.frames):
                    continue
                cur = vp.frames[vp.index] if vp.frames else None
                vp.frames = frames
                if cur is not None:
                    vp.index = next((i for i, f in enumerate(frames)
                                     if f.sop_uid == cur.sop_uid and f.frame_index == cur.frame_index), vp.index)
                vp.index = max(0, min(vp.index, len(frames) - 1))
                vp.series_label = self._series_label(uid_vp)
                vp._qimage_key = None
                vp._load_current()
                vp._start_prefetch()
                vp.update()
        if changed:
            self._fill_strip()
        return changed

    def add_study_silent(self, study_uid: str) -> None:
        """Traz o estudo para a aba (séries na tira) sem mexer nos quadros."""
        ensure = getattr(self.repo, "ensure_local", None)
        if ensure is not None and not ensure(study_uid, self):
            return
        if study_uid in self.study_order:
            return
        self.study_infos[study_uid] = self.repo.study_info(study_uid) or {}
        self.study_order.append(study_uid)
        self.series.extend(_image_series(self.repo.series_for_study(study_uid)))
        self.groups.update({g["id"]: g for g in self.repo.series_groups(study_uid)})
        self.key_set |= self.repo.key_image_set(study_uid)
        self.estudos_na_tira = None            # o exame que chegou aparece na tira
        self._fill_strip()
        self._encher_filtro_de_exames()
        QTimer.singleShot(0, self.load_overlay_objects)

    def title(self) -> str:
        if self.case_label:
            return self.case_label
        if self.anonymize:
            from ipe.core import mascara as MK
            perfil = MK.perfil_de(self.settings)
            if perfil != "oculto":
                nome = MK.mascarar_info(self.study_info, perfil)["patient_name"]
                desc = self.study_info.get("description", "")
                return f"{nome} — {desc} [{MK.PERFIS[perfil].split(' (')[0]}]" if desc else \
                    f"{nome} [{MK.PERFIS[perfil].split(' (')[0]}]"
            return f"Estudo — {self.study_info.get('description', '')}".strip(" —")
        name = self.study_info.get("patient_name", "")
        desc = self.study_info.get("description", "")
        return f"{name} — {desc}" if desc else name


class PhaseGroupDialog(QDialog):
    """Confirma as séries detectadas como fases de uma dinâmica (dá para desmarcar)."""

    def __init__(self, tab: ViewerTab, uids: list[str]):
        super().__init__(tab)
        self.setWindowTitle("Agrupar fases dinâmicas")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Estas séries têm a mesma geometria e parecem fases de uma sequência "
                             "dinâmica (em ordem de aquisição). Desmarque o que não for fase:"))
        self.list = QListWidget()
        for uid in uids:
            s = tab._series_row(uid)
            it = QListWidgetItem(f"Se {s.series_number}  {s.description}  ({s.num_images} im)" if s else uid)
            it.setData(Qt.UserRole, uid)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            self.list.addItem(it)
        lay.addWidget(self.list)
        from PySide6.QtWidgets import QLineEdit
        self.name_edit = QLineEdit("Dinâmica")
        lay.addWidget(QLabel("Nome do grupo:"))
        lay.addWidget(self.name_edit)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Agrupar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def chosen(self) -> list[str]:
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]

    def name(self) -> str:
        return self.name_edit.text().strip() or "Dinâmica"
