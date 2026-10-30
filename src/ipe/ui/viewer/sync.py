"""Sincronização entre quadros, inclusive entre janelas de monitores diferentes.

Um único SyncHub (da janela principal) conhece todas as abas de estudo abertas.
Regras:
- mesmo referencial espacial (FrameOfReferenceUID) + sincronização automática:
  os quadros paralelos vão para a mesma posição no paciente (mm);
- grupos de sincronização (1 a 4, cada um com uma cor): os quadros do grupo andam
  juntos mantendo o deslocamento do momento em que entraram no grupo. Serve para
  comparar com exames anteriores ou de outra modalidade;
  - com geometria e planos paralelos, o deslocamento é em mm;
  - sem geometria (DBT, US, séries de planos diferentes), usa a posição relativa
    na pilha (fração do número de cortes);
- ajuste fino: rolar com Alt pressionado move só aquele quadro e redefine o deslocamento;
- o alinhamento entre dois estudos fica salvo no banco e é reaproveitado.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

log = logging.getLogger(__name__)

GROUP_COLORS = {1: QColor(80, 200, 255), 2: QColor(120, 230, 120), 3: QColor(255, 160, 60),
                4: QColor(255, 110, 200)}
GROUP_NAMES = {1: "azul", 2: "verde", 3: "laranja", 4: "rosa"}
REF_COLORS = [QColor(255, 200, 0), QColor(0, 200, 255), QColor(255, 80, 200), QColor(120, 255, 120),
              QColor(255, 140, 60), QColor(180, 140, 255), QColor(255, 255, 255), QColor(0, 255, 200),
              QColor(255, 100, 100)]
SYNC_MODES = {"off": "Sincronização desligada",
              "study": "Sincronização: só mesmo estudo",
              "all": "Sincronização: todos os quadros"}


@dataclass
class Member:
    group: int
    geo: np.ndarray | None     # deslocamento em mm (posição − posição canônica do grupo)
    rel: float                 # deslocamento relativo na pilha


def _pos(v) -> np.ndarray | None:
    pl = v.plane()
    return None if pl is None else np.asarray(pl[0], dtype=float)


def _rel(v) -> float:
    n = len(v.frames)
    return v.index / (n - 1) if n > 1 else 0.0


def _parallel(a, b) -> bool:
    if not a.frames or not b.frames:
        return False
    na, nb = a.frames[0].normal, b.frames[0].normal
    return na is not None and nb is not None and float(np.linalg.norm(np.cross(na, nb))) < 0.1


def alt_pressed() -> bool:
    return bool(QApplication.keyboardModifiers() & Qt.AltModifier)


#: modalidades em que a sincronização automática nasce desligada (0.99.9, pedido dele: "na RM pode
#: deixar desativada por padrão"). Na RM o exame tem várias sequências no mesmo plano — duas
#: sagitais, T1 e T2 — e rolar uma não é pedido para rolar a outra.
AUTO_DESLIGADA_DE_FABRICA = {"MR": False}

#: nome da modalidade nos menus e nas preferências
MODALIDADE_TXT = {"MR": "RM", "CT": "TC", "PT": "PET", "NM": "Medicina nuclear", "MG": "Mamografia",
                  "US": "Ultrassom", "CR": "Raios X (CR)", "DX": "Raios X (DX)", "XA": "Angiografia",
                  "RF": "Fluoroscopia", "OT": "Outros"}


def _modalidade_base(mod: str) -> str:
    """"MAP msi" (mapa da dinâmica) e "MR" contam como a mesma modalidade para a regra."""
    mod = (mod or "").strip().upper()
    return "MR" if mod.startswith("MAP") else mod


def _sempre_juntos(a, b) -> bool:
    """Quadros que só fazem sentido andando juntos, qualquer que seja a regra da modalidade:
    os mapas e as fases da avaliação dinâmica (são o mesmo corte visto de jeitos diferentes) e os
    planos de um mesmo MPR."""
    ua, ub = getattr(a, "series_uid", "") or "", getattr(b, "series_uid", "") or ""
    din = ("dyn:", "dynph:", "dynmpr:")
    if ua.startswith(din) and ub.startswith(din):
        return True
    if ua.startswith("mpr:") and ub.startswith("mpr:"):
        return ua.split(":")[1:2] == ub.split(":")[1:2]
    return False


class SyncHub(QObject):
    # o que o usuário liga e desliga fica guardado: ligar de novo a cada abertura é defeito.
    # A automática (sync_auto) não está aqui: desde a 0.99.9 ela é lembrada **por modalidade**
    # (viewer.sync_auto_mod) — sync_auto virou só o "desligado geral" do modo de sincronização.
    GUARDADOS = ("sync_wl", "sync_zoom", "show_refs")

    def __init__(self, repo=None, parent=None, settings=None):
        super().__init__(parent)
        self.repo = repo
        self.settings = settings
        self.tabs: list = []
        self.members: dict = {}           # Viewport -> Member
        self.sync_auto = True
        self.sync_wl = False
        self.sync_zoom = False
        self.show_refs = True
        self.mode = "study"
        for nome in self.GUARDADOS:
            if settings is not None:
                setattr(self, nome, bool(settings.get("viewer." + nome, getattr(self, nome))))
        # Antes da 0.99.9 a automática era uma chave só, para tudo. Quem a tinha desligado continua
        # com ela desligada em todas as modalidades que ainda não têm escolha própria.
        self.auto_padrao = True
        self.auto_mod: dict[str, bool] = dict(AUTO_DESLIGADA_DE_FABRICA)
        if settings is not None:
            self.auto_padrao = bool(settings.get("viewer.sync_auto", True))
            gravado = settings.get("viewer.sync_auto_mod", None)
            if isinstance(gravado, dict):
                self.auto_mod.update({str(k).upper(): bool(v) for k, v in gravado.items()})
        self._busy = False
        self._dirty_groups: set[int] = set()
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(700)
        self._save_timer.timeout.connect(self.flush_registrations)

    # ------------------------------------------------------------ abas
    def register(self, tab) -> None:
        if tab not in self.tabs:
            self.tabs.append(tab)

    def unregister(self, tab) -> None:
        if tab in self.tabs:
            self.tabs.remove(tab)
        for v in list(self.members):
            if v in tab.viewports:
                self.members.pop(v, None)
        self.refresh_icons()

    def viewports(self, extra=None) -> list:
        """Quadros visíveis em todas as janelas (mais os da aba `extra`)."""
        out = []
        for t in self.tabs:
            if t is extra or t.isVisible():
                out += [v for v in t._shown() if v not in out]
        return out

    # ------------------------------------------------------------ automática por modalidade
    def recarregar_regras(self) -> None:
        """Relê a regra por modalidade das preferências (depois da janela de Preferências)."""
        if self.settings is None:
            return
        self.auto_padrao = bool(self.settings.get("viewer.sync_auto", True))
        self.auto_mod = dict(AUTO_DESLIGADA_DE_FABRICA)
        gravado = self.settings.get("viewer.sync_auto_mod", None)
        if isinstance(gravado, dict):
            self.auto_mod.update({str(k).upper(): bool(v) for k, v in gravado.items()})

    def auto_da_modalidade(self, mod: str) -> bool:
        """A regra guardada para a modalidade (sem olhar o modo geral)."""
        return bool(self.auto_mod.get(_modalidade_base(mod), self.auto_padrao))

    def auto_entre(self, a, b) -> bool:
        """Os dois quadros andam juntos sozinhos (sem grupo)?"""
        if not self.sync_auto:                      # modo "desligado" vale para tudo
            return False
        if _sempre_juntos(a, b):
            return True
        return self.auto_da_modalidade(a.modality) and self.auto_da_modalidade(b.modality)

    def set_auto_modalidade(self, mod: str, on: bool) -> None:
        mod = _modalidade_base(mod)
        if not mod:
            self.auto_padrao = bool(on)
            if self.settings is not None:
                self.settings.set("viewer.sync_auto", bool(on))
        else:
            self.auto_mod[mod] = bool(on)
            if self.settings is not None:
                self.settings.set("viewer.sync_auto_mod", dict(self.auto_mod))
        if on and not self.sync_auto:               # ligar a automática tira do modo "desligado"
            self.sync_auto, self.mode = True, "study"
        for t in self.tabs:
            t.reflect_sync_flags()

    def set_flag(self, name: str, value: bool) -> None:
        setattr(self, name, value)
        if self.settings is not None and name in self.GUARDADOS:
            self.settings.set("viewer." + name, bool(value))
        for t in self.tabs:
            t.reflect_sync_flags()
        if name == "show_refs":
            self.update_reference_lines()

    # ------------------------------------------------------------ grupos
    def group_of(self, v) -> int | None:
        m = self.members.get(v)
        return m.group if m else None

    def _free_group(self) -> int:
        used = {m.group for m in self.members.values()}
        return next((g for g in GROUP_COLORS if g not in used), 1)

    def _canonical(self, group: int, exclude=None) -> tuple[np.ndarray | None, float | None]:
        """Posição canônica do grupo, a partir de um membro (preferindo quem tem geometria)."""
        geo, rel = None, None
        for v, m in self.members.items():
            if m.group != group or v is exclude or not v.frames:
                continue
            p = _pos(v)
            if geo is None and p is not None and m.geo is not None:
                geo = p - m.geo
            if rel is None:
                rel = _rel(v) - m.rel
        return geo, rel

    def join(self, v, group: int, geo_offset=None, rel_offset=None) -> None:
        """Põe o quadro no grupo mantendo o alinhamento atual (ou um deslocamento dado)."""
        self.members.pop(v, None)
        c_geo, c_rel = self._canonical(group)
        p = _pos(v)
        if geo_offset is not None:
            geo = np.asarray(geo_offset, dtype=float)
        elif p is None:
            geo = None
        else:
            geo = p - c_geo if c_geo is not None else np.zeros(3)
        if rel_offset is not None:
            rel = float(rel_offset)
        else:
            rel = _rel(v) - c_rel if c_rel is not None else 0.0
        self.members[v] = Member(group, geo, rel)
        self._mark_dirty(group)
        self.refresh_icons()

    def leave(self, v) -> None:
        if self.members.pop(v, None) is not None:
            self.refresh_icons()

    def cycle(self, v) -> int | None:
        """Clique no ícone de corrente: nenhum -> 1 -> 2 -> 3 -> 4 -> nenhum."""
        g = self.group_of(v)
        order = [None, *GROUP_COLORS]
        nxt = order[(order.index(g) + 1) % len(order)]
        if nxt is None:
            self.leave(v)
        else:
            self.join(v, nxt)
        return nxt

    def link_all(self, views: list, group: int | None = None) -> int | None:
        views = [v for v in views if v.frames]
        if len(views) < 2:
            return None
        g = group or self._free_group()
        for v in views:
            self.join(v, g)
        return g

    def unlink(self, views: list) -> None:
        for v in views:
            self.members.pop(v, None)
        self.refresh_icons()

    def unlink_all(self) -> None:
        self.members.clear()
        self.refresh_icons()

    def refresh_icons(self) -> None:
        for t in self.tabs:
            for v in t.viewports:
                g = self.group_of(v)
                v.sync_color = GROUP_COLORS.get(g) if g else None
                v.sync_label = str(g) if g else ""
                v.update()
            t.reflect_sync_flags()

    def set_mode(self, mode: str, extra=None) -> str:
        self.mode = mode
        if mode == "off":
            self.sync_auto = False
            self.unlink_all()
        elif mode == "study":
            self.sync_auto = True
            self.unlink_all()
        else:
            self.sync_auto = True
            self.unlink_all()
            self.link_all(self.viewports(extra), 1)
        for t in self.tabs:
            t.reflect_sync_flags()
        self.update_reference_lines(extra)
        return SYNC_MODES[mode]

    def cycle_mode(self, extra=None) -> str:
        order = list(SYNC_MODES)
        return self.set_mode(order[(order.index(self.mode) + 1) % len(order)], extra)

    # ------------------------------------------------------------ alinhamento salvo
    def _mark_dirty(self, group: int) -> None:
        if self.repo is not None:
            self._dirty_groups.add(group)
            self._save_timer.start()

    def flush_registrations(self) -> None:
        groups, self._dirty_groups = self._dirty_groups, set()
        if self.repo is None:
            return
        for g in groups:
            ms = [(v, m) for v, m in self.members.items() if m.group == g and v.frames
                  and not v.frames[0].is_virtual and not v.series_uid.startswith("key:")]
            for i, (a, ma) in enumerate(ms):
                for b, mb in ms[i + 1:]:
                    if not a.study_uid or not b.study_uid or a.study_uid == b.study_uid:
                        continue
                    geo = (mb.geo - ma.geo) if (ma.geo is not None and mb.geo is not None) else np.zeros(3)
                    try:
                        self.repo.save_registration(a.study_uid, b.study_uid, geo, mb.rel - ma.rel)
                    except Exception as e:  # noqa: BLE001
                        log.warning("Não foi possível salvar o alinhamento: %s", e)

    def apply_saved(self, a, b) -> bool:
        """Liga dois quadros de estudos diferentes usando o alinhamento salvo, se houver."""
        if self.repo is None or not a.frames or not b.frames or a.study_uid == b.study_uid:
            return False
        reg = self.repo.get_registration(a.study_uid, b.study_uid)
        if reg is None:
            return False
        geo, rel = reg
        g = self.group_of(a) or self._free_group()
        if self.group_of(a) is None:
            self.join(a, g)
        ma = self.members[a]
        geo_b = (ma.geo + np.asarray(geo)) if ma.geo is not None and _pos(b) is not None else None
        self.join(b, g, geo_offset=geo_b, rel_offset=ma.rel + rel)
        self._dirty_groups.discard(g)
        self._busy = True
        try:
            self._follow(a, b)
        finally:
            self._busy = False
        self.update_reference_lines()
        return True

    # ------------------------------------------------------------ eventos dos quadros
    def _linked(self, a, b) -> bool:
        ma, mb = self.members.get(a), self.members.get(b)
        return ma is not None and mb is not None and ma.group == mb.group

    @staticmethod
    def same_space(a, b) -> bool:
        return bool(a.for_uid) and a.for_uid == b.for_uid

    def _follow(self, src, dst) -> None:
        if self._linked(src, dst):
            ms, md = self.members[src], self.members[dst]
            ps = _pos(src)
            if ps is not None and ms.geo is not None and md.geo is not None and _parallel(src, dst):
                dst.go_to_point(ps - ms.geo + md.geo)
            else:
                n = len(dst.frames)
                r = _rel(src) - ms.rel + md.rel
                dst.set_index_silently(int(round(min(1.0, max(0.0, r)) * (n - 1))) if n > 1 else 0)
        elif self.auto_entre(src, dst) and self.same_space(src, dst) and _parallel(src, dst):
            ps = _pos(src)
            if ps is not None:
                dst.go_to_point(ps, tolerance_mm=15.0)

    def _rebase(self, v) -> None:
        """Ajuste fino: redefine o deslocamento de v em relação ao resto do grupo."""
        m = self.members[v]
        c_geo, c_rel = self._canonical(m.group, exclude=v)
        p = _pos(v)
        if c_geo is not None and p is not None:
            m.geo = p - c_geo
        if c_rel is not None:
            m.rel = _rel(v) - c_rel
        self._mark_dirty(m.group)

    def frame_changed(self, vp, extra=None) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            if vp in self.members and alt_pressed():
                self._rebase(vp)
            else:
                for w in self.viewports(extra):
                    if w is not vp and w.frames:
                        self._follow(vp, w)
        finally:
            self._busy = False
        self.update_reference_lines(extra)

    def cursor_moved(self, vp, point: np.ndarray, extra=None) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            for w in self.viewports(extra):
                if w is vp:
                    continue
                if self._linked(vp, w):
                    ms, md = self.members[vp], self.members[w]
                    p = point - ms.geo + md.geo if ms.geo is not None and md.geo is not None else point
                elif self.sync_auto and self.same_space(vp, w):
                    # O cursor 3D é pedido explícito ("vá para este ponto"): leva os quadros do mesmo
                    # espaço mesmo com a automática da modalidade desligada. Só o modo desligado o cala.
                    p = point
                else:
                    w.cursor_point = None
                    w.update()
                    continue
                w.cursor_point = p
                w.go_to_point(p)
        finally:
            self._busy = False
        self.update_reference_lines(extra)

    def view_changed(self, vp, kind: str, extra=None) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            for w in self.viewports(extra):
                if w is vp or not w.frames:
                    continue
                if kind == "window" and self.sync_wl and w.modality == vp.modality \
                        and w._img is not None and not w._img.is_color:
                    w.set_window(vp.state.width, vp.state.level, emit=False)
                elif kind == "cmap" and self.sync_wl and w.modality == vp.modality \
                        and w._img is not None and not w._img.is_color:
                    w.state.cmap = vp.state.cmap
                    w._qimage_key = None
                    w.update()
                elif kind in ("zoom", "pan") and self.sync_zoom:
                    if getattr(vp, "mg_cell", None) is not None and getattr(w, "mg_cell", None) is not None:
                        continue        # mamografia: a aba segue pelo lugar da mama (mg_sync_view)
                    w.set_zoom_pan(vp.state.zoom, vp.state.pan)
                elif kind == "invert" and self.sync_wl and w.modality == vp.modality \
                        and w._img is not None and not w._img.is_color:
                    if w.state.invert != vp.state.invert:
                        w.state.invert = vp.state.invert
                        w._qimage_key = None
                        w.update()
                elif kind == "filter" and self.sync_wl and w.modality == vp.modality:
                    w.state.filter = vp.state.filter       # o filtro acompanha a janela
                    w._qimage_key = None
                    w.update()
        finally:
            self._busy = False

    def update_reference_lines(self, extra=None) -> None:
        shown = self.viewports(extra)
        planes = {}
        for i, v in enumerate(shown):
            pl = v.plane()
            if pl is not None:
                planes[v] = (pl[0], pl[3], REF_COLORS[i % len(REF_COLORS)])
        for t in self.tabs:
            for v in t.viewports:
                v.ref_planes = []
                v._refs_on = self.show_refs
                if self.show_refs and v in planes:
                    for w, (p, n, color) in planes.items():
                        if w is not v and self.same_space(v, w):
                            v.ref_planes.append((p, n, color))
                v.update()
