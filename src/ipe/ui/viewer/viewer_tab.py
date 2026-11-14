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
from PySide6.QtCore import QMimeData, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QBrush, QColor, QDrag, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox,
    QApplication, QComboBox, QGridLayout, QSplitter, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMenu, QMessageBox, QProgressDialog, QVBoxLayout, QWidget,
)

from ipe.db.repository import Repository, SeriesRow
from ipe.imaging.measure import Annotation
from ipe.core import cronometro as CR
from ipe.imaging.series import Frame, FrameCache, _vec, build_frames
from ipe.imaging.volume import ObliquePlane, VolumeError, build_volume
from ipe.ui.icons import with_badge
from ipe.ui.monitors import screen_with_role
from ipe.ui.viewer.sync import GROUP_NAMES, MODALIDADE_TXT, SyncHub
from ipe.ui.viewer.viewport import TOOLS, Viewport
from ipe.ui.viewer.dynamic import DynamicDialog, DynamicSession
from ipe.ui.viewer import nm_view as NMV
from ipe.ui.viewer.onco import OncoMixin
# LAYOUTS e as tabelas de ferramentas moram na barra (0.100.39); outros módulos ainda os importam daqui
from ipe.ui.viewer.barra import BarraMixin, LAYOUTS, MEASURE_TOOLS, SLAB_CHOICES, TOOL_ICONS, TOOL_SHORT  # noqa: F401
from ipe.ui.viewer.fusao_aba import FusaoMixin
from ipe.ui.viewer.ia_aba import IAMixin
from ipe.ui.viewer.mamografia_aba import MamografiaMixin
from ipe.ui.viewer.mpr_aba import MPRMixin

log = logging.getLogger(__name__)

SERIES_MIME = "application/x-dicomviewer-series"


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


VOLUME = {"CT", "MR", "PT", "NM"}     # modalidades que empilham cortes: 3D, MPR e fusão


NON_IMAGE = {"SR", "KO", "PR", "REG", "SEG", "RTSTRUCT", "RTPLAN", "DOC"}


def _image_series(rows: list) -> list:
    """Séries que o visualizador mostra.

    Fora: relatórios estruturados, estados de apresentação e o **filme da estação AW**
    ("AW electronic film" e "AW electronic pages"), que é impressão e vive na aba Impressões.
    """
    from ipe.printing.aw_film import is_print_series
    return [s for s in rows if (s.modality or "").upper() not in NON_IMAGE
            and not is_print_series(getattr(s, "description", ""))]


class ViewerTab(BarraMixin, MPRMixin, FusaoMixin, MamografiaMixin, IAMixin, OncoMixin, QWidget):
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
        CR.marca("barra")
        # as regras de dinâmico valem **antes** de montar a tira: o que foi juntado ou separado
        # já aparece pronto, e o médico vê o que aconteceu na barra de estado
        try:
            self._regras_feitas = self.aplicar_regras_dinamicas()
        except Exception:  # noqa: BLE001
            log.exception("regras de dinâmico")
            self._regras_feitas = []
        self.strip = SeriesStrip()
        CR.marca("regras")
        self._fill_strip()
        CR.marca("tira")
        # 0.100.0: no programa ligado ao servidor central, quanto de cada série já chegou (tira e quadros)
        self._vigia_download = None
        if getattr(repo, "andamento", None) is not None:
            from ipe.ui.viewer.baixando import VigiaDownload
            self._vigia_download = VigiaDownload(self)
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
        CR.marca("protocolo")
        if self._regras_feitas:
            feito = "; ".join(self._regras_feitas)
            QTimer.singleShot(0, lambda: self.status_message.emit(
                f"Regras de dinâmico (Preferências ▸ Dinâmicos): {feito}"))
        repo.mark_opened(study_uid)
        QTimer.singleShot(0, self.carregar_overlays)

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
            # 0.100.14: o selo "IA" nas séries com resultado de IA ou analisadas por uma
            try:
                from ipe.ai import series_ia as SIA
                com_ia = SIA.series_com_ia(self.repo, st_uid)     # todas (a tira não tem as SEG)
            except Exception:  # noqa: BLE001
                log.exception("séries com IA")
                com_ia = {}
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
                dicas = []
                if n_ann:
                    pm = with_badge(pm, f"✎ {n_ann}")
                    dicas.append(f"{n_ann} imagem(ns) com medida ou anotação — botão direito para ir direto a elas")
                ia = com_ia.get(s.series_uid)
                if ia:
                    pm = with_badge(pm, "IA", QColor(186, 140, 255), topo=True)
                    dicas.append(SIA.dica(ia))
                if dicas:
                    item.setToolTip("\n".join(dicas))
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
        vigia = getattr(self, "_vigia_download", None)
        if vigia is not None:
            vigia.aplicar()

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
        priorizar = getattr(self.repo, "priorizar", None)
        if priorizar is not None and series_uid and ":" not in series_uid:
            # 0.100.0: a série posta no quadro passa para a frente do download do servidor central
            st = next((s.study_uid for s in self.series if s.series_uid == series_uid), self.study_uid)
            try:
                priorizar(st, series_uid)
            except Exception:  # noqa: BLE001
                log.debug("priorizar a série", exc_info=True)
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
        QTimer.singleShot(0, self.carregar_overlays)
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

    def t1_sintetico(self, vp=None, simular: bool = False):
        """0.100.23: T1 de 1 mm pelo SynthSR a partir da série do quadro — para o MPR dos exames só com 2D."""
        from ipe.ai import synthsr as SR
        vp = vp or self.active
        f = vp.current_frame() if vp is not None else None
        if f is None:
            return None
        linha = self._series_row(f.series_uid)
        if linha is not None and SR.MARCA in (linha.description or ""):
            QMessageBox.information(self, SR.TITULO, "Esta série já é um T1 sintético. Escolha a série original.")
            return None
        if not simular and QMessageBox.question(
                self, SR.TITULO,
                "Cria no exame uma série T1 de 1 mm a partir da série deste quadro, para abrir no MPR e medir "
                "quando o exame não tem T1 3D. Leva alguns minutos.\n\n"
                "É imagem sintética: serve para medir a anatomia. Lesões podem não aparecer ou mudar de aspecto — "
                "não use para procurar nem caracterizar lesão.\n\nCriar agora?") != QMessageBox.Yes:
            return None
        return self.segmentar_orgaos(vp, simular=simular, tipo="synthsr")

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
        vp.sig.medida_criada.connect(self.ligar_pela_posicao)
        vp.sig.nodulo_requested.connect(self.nodulo_no_clique)
        vp.sig.fusion_requested.connect(self.fundir_por_arrastar)            # 0.99.59
        vp.sig.clone_roi_requested.connect(self.clonar_roi)
        vp.referencial_da_sincronia = self.outros_referenciais_ligados
        vp.sig.segment_requested.connect(self.segment_at)
        vp.sig.caixa_ia_requested.connect(self.caixa_ia)
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

    def marcar_revisado(self, study_uid: str | None = None) -> str:
        """0.99.63: o exame do quadro ativo passa a "Revisado" à mão; de novo, volta ao automático."""
        vp = self.active
        uid = study_uid or ((vp.study_uid if vp is not None and vp.study_uid else None) or self.study_uid)
        try:
            atual = self.repo.estado_do_exame(uid)
            novo = "" if atual.get("manual") == "revisado" else "revisado"
            self.repo.set_estado_leitura([uid], novo)
            depois = self.repo.estado_do_exame(uid)
        except Exception as e:  # noqa: BLE001
            log.exception("estado do exame")
            self.status_message.emit(f"Não deu para trocar o estado do exame: {e}")
            return ""
        from ipe.core import estado_exame as EST
        self.status_message.emit("Exame marcado como revisado." if novo else
                                 f"Estado do exame de volta ao automático: {EST.rotulo(depois.get('estado', ''))}.")
        return depois.get("estado", "")

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
        QTimer.singleShot(0, self.carregar_overlays)

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
