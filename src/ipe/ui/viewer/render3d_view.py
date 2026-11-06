"""3D dentro do layout: o quadro deixa de mostrar cortes e passa a mostrar o volume.

Não há janela separada. O 3D é um quadro como os outros — entra no 1×2 e no 2×2, vai
para o filme, vira imagem-chave e aceita o botão direito —, só que o desenho vem do
renderizador por raios em vez de um arquivo. Arrastar com o esquerdo gira; clicar leva
o cursor dos cortes até o ponto da superfície onde o raio bateu.
"""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainterPath, QPen
from PySide6.QtWidgets import QComboBox, QLabel, QMenu, QSlider, QToolBar, QWidget

from ipe.imaging import colormaps as CM
from ipe.imaging.render3d import VR_PRESETS, Renderer3D, rotation
from ipe.imaging.series import Frame, FrameImage

log = logging.getLogger(__name__)

MODES = [("vr", "Renderização de volume (VR)"), ("surf", "Superfície"), ("mip", "MIP"),
         ("minip", "MinIP"), ("avg", "Média (raio-X)")]
# cortes em caixa a partir do cursor: o que fica na tela
CUTS = [("posterior", "Só o que está atrás (posterior)"), ("anterior", "Só o que está à frente (anterior)"),
        ("right", "Só o lado direito do paciente"), ("left", "Só o lado esquerdo do paciente"),
        ("head", "Só da cabeça para cima"), ("feet", "Só dos pés para baixo")]
TETO_PX = 900          # nenhum quadro é renderizado maior que isto, mesmo em monitor grande


class View3D:
    """Estado do 3D de um quadro: volume, câmera, modo e cortes."""

    def __init__(self, tab, renderer: Renderer3D, title: str, modality: str, mode: str = "vr",
                 window: tuple[float, float] | None = None, src_uid: str = "",
                 study_uid: str = "", source_path: str = ""):
        self.tab, self.r, self.modality = tab, renderer, modality
        self.title, self.src_uid, self.study_uid, self.source_path = title, src_uid, study_uid, source_path
        self.mode, self.win = mode, window
        self.az = self.el = 0.0
        self.zoom = 1.0
        self.pan = (0.0, 0.0)
        self.opacity = 0.2
        self.cmap = ""
        self.lo, self.hi = 0.0, 1.0
        self.fast = False
        self.vp = None
        self.size = (512, 512)
        self.preset = "bone" if modality == "CT" else "auto"
        self.lasso: list | None = None      # laço da escultura em curso (pontos da imagem)
        self.sculpt_mode = ""               # "", "remove" ou "keep"
        self.plane_drag = False             # esquerdo arrasta o corte em vez de girar
        self.aviso = ""
        # 0.99.82: as estruturas segmentadas (TotalSegmentator, SEG, nódulos…) como superfícies coloridas
        self.estruturas = False
        self.estr_opacidade = 0.9
        self._estr_chave = None
        self._timer = QTimer(tab)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(lambda: self.refresh(fast=False))
        self._cine_timer = QTimer(tab)
        self._cine_timer.timeout.connect(self._cine_tick)
        self._init_ranges()

    # ------------------------------------------------------------------ faixas
    def _init_ranges(self) -> None:
        self.apply_preset(self.preset, render=False)
        if self.mode != "vr":
            self.cmap = ""
        if self.win and self.mode not in ("vr", "surf") and float(self.win[0] or 0) > 0:
            w, l = self.win
            self.lo, self.hi = l - w / 2, l + w / 2
        elif self.mode not in ("vr", "surf"):
            # sem janela que preste (largura zero): a faixa do próprio volume
            self.lo, self.hi = self.r.p[1], max(self.r.p[99.7], self.r.p[1] + 1e-3)

    def apply_preset(self, key: str, render: bool = True) -> None:
        _name, lo, hi, cmap, op = VR_PRESETS[key]
        if lo is None:
            lo, hi = self.r.auto_range()
        self.preset, self.lo, self.hi, self.opacity = key, lo, hi, op
        # a tabela de cores do preset é a função de transferência do VR; na superfície o
        # fundo tem que ficar preto, e lut[0] de uma tabela de VR não é preto
        self.cmap = cmap if self.mode == "vr" else ""
        if render:
            self.refresh(fast=False)

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        if mode in ("vr", "surf"):
            self.apply_preset(self.preset, render=False)
        elif self.win:
            w, l = self.win
            self.lo, self.hi = l - w / 2, l + w / 2
        else:
            self.lo, self.hi = self.r.p[1], self.r.p[99.7]
        if self.vp is not None:
            self.vp.state.window_set = False
        self.refresh(fast=False)

    # ------------------------------------------------------------------ quadro
    def attach(self, vp, study_info: dict, label: str = "") -> None:
        """Põe este 3D no quadro: uma série virtual de um quadro só."""
        self.vp = vp
        f = Frame(path=f"3d:{self.src_uid}", frame_index=0, sop_uid="", instance_number=1,
                  provider=lambda _i: self.image(), series_uid=f"3d:{self.src_uid}")
        vp.set_series(f"3d:{self.src_uid}", [f], label or f"3D — {self.title}", study_info, 0)
        vp.render3d = self
        vp.state.window_set = False
        vp.update()

    def header(self) -> dict:
        return {"Modality": self.modality, "SeriesDescription": f"3D {dict(MODES)[self.mode]}",
                "_render3d": "1"}

    def image(self) -> FrameImage:
        vp = self.vp
        w = max(64, vp.width() if vp is not None else 512)
        h = max(64, vp.height() if vp is not None else 512)
        esc = min(1.0, TETO_PX / max(w, h))
        w, h = max(int(w * esc), 64), max(int(h * esc), 64)
        self.size = (w, h)
        cmap = self.cmap if self.mode in ("vr", "surf") else ""
        px = self.r.render(self.mode, self.az, self.el, (w, h), self.lo, self.hi, cmap,
                           self.opacity, self.zoom, self.pan, fast=self.fast)
        ps = 2 * self.r.radius / (min(w, h) * self.zoom)
        if self.estruturas and getattr(self.r, "labels", None) is not None:
            from ipe.imaging.render3d import compor_estruturas
            prof_base = self.r.last_depth if self.mode in ("vr", "surf") else None
            passo = float((self.r._last or {}).get("st", self.r.step))
            estr = self.r.render_labels(self.az, self.el, (w, h), self.zoom, self.pan, fast=self.fast)
            lo, hi = self.lo, self.hi
            if px.ndim == 2 and self.vp is not None and self.vp.state.window_set:
                ww, wl = self.vp.state.width, self.vp.state.level
                lo, hi = wl - ww / 2, wl + ww / 2
            px = compor_estruturas(px, lo, hi, estr, prof_base, passo, self.estr_opacidade)
            return FrameImage(np.ascontiguousarray(px), True, None, (ps, ps), header=self.header())
        if px.ndim == 2:
            return FrameImage(px, False, (self.hi - self.lo, (self.hi + self.lo) / 2), (ps, ps),
                              header=self.header())
        return FrameImage(np.ascontiguousarray(px), True, None, (ps, ps), header=self.header())

    def refresh(self, fast: bool = False) -> None:
        vp = self.vp
        if vp is None:
            return
        self.fast = fast
        vp._qimage_key = None          # a imagem muda a cada giro: o cache por id não serve aqui
        vp._load_current()
        vp.update()
        if fast:
            self._timer.start(300)
        if self.tab is not None and getattr(self.tab, "render3d_bar", None) is not None:
            self.tab.update_render3d_bar()

    # ------------------------------------------------------------------ câmera
    def set_view(self, az: float, el: float) -> None:
        self.az, self.el = az, el
        self.refresh(fast=False)

    def rotate(self, dx: float, dy: float) -> None:
        self.az = (self.az - dx * 0.6) % 360
        self.el = float(np.clip(self.el + dy * 0.6, -89, 89))
        self.refresh(fast=True)

    def zoom_by(self, steps: float) -> None:
        self.zoom = float(np.clip(self.zoom * (1.1 ** steps), 0.3, 12))
        self.refresh(fast=True)

    def pan_by(self, dx: float, dy: float) -> None:
        w, h = self.size
        s = 2 * self.r.radius / (min(w, h) * self.zoom)
        self.pan = (self.pan[0] - dx * s, self.pan[1] - dy * s)
        self.refresh(fast=True)

    def window_by(self, dx: float, dy: float) -> None:
        span = max(self.hi - self.lo, 1e-3)
        k = span / 300
        self.lo += dy * k - dx * k
        self.hi += dy * k + dx * k
        if self.hi <= self.lo:
            self.hi = self.lo + 1e-3
        self.refresh(fast=True)

    # ------------------------------------------------------------------ cortes
    def cursor_mm(self):
        """Ponto do cursor 3D (a cruz dos quadros); sem cruz, o centro do volume."""
        for vp in getattr(self.tab, "viewports", []):
            p = getattr(vp, "cursor_point", None)
            if p is not None:
                return p
        return self.r.center

    def cut_box(self, side: str) -> None:
        self.r.cut_at(self.cursor_mm(), side)
        self.refresh(fast=False)

    def cut_view_plane(self) -> None:
        """Plano de corte paralelo à tela, passando pelo cursor: tira o que está na frente."""
        _u, _v, d = rotation(self.az, self.el)
        self.r.cut_plane(self.cursor_mm(), d, keep="front")
        self.plane_drag = True
        self.refresh(fast=False)

    def cut_reset(self) -> None:
        self.r.restore_all()
        self.plane_drag = False
        self.sculpt_mode = ""
        self.lasso = None
        self.aviso = ""
        self.refresh(fast=False)

    def remove_table(self) -> str:
        n = self.r.remove_table()
        if n:
            self.aviso = ""
            self.refresh(fast=False)
            return f"Maca removida: {n} voxels saíram do volume."
        self.aviso = "Não achei a maca"
        self.refresh(fast=False)
        return ("Não achei a maca neste volume (só funciona em TC com o paciente deitado de costas). "
                "Dá para apagá-la à mão com o laço da escultura.")

    # ------------------------------------------------------------------ escultura
    def sculpt_from(self, pontos: list) -> str:
        if len(pontos) < 3:
            return ""
        poly = [(p.x(), p.y()) for p in pontos]
        n = self.r.sculpt(poly, self.size, self.az, self.el, self.zoom, self.pan,
                          keep_inside=(self.sculpt_mode == "keep"))
        self.refresh(fast=False)
        if self.sculpt_mode == "keep":
            return f"Guardei só o que está dentro do laço: {n} voxels saíram."
        return f"Apaguei o que está dentro do laço: {n} voxels saíram."

    # ------------------------------------------------------------------ giro contínuo
    def cine(self, on: bool) -> None:
        if on:
            self._cine_timer.start(70)
        else:
            self._cine_timer.stop()
            self.refresh(fast=False)

    def cine_on(self) -> bool:
        return self._cine_timer.isActive()

    def _cine_tick(self) -> None:
        self.az = (self.az + 6) % 360
        self.fast = True
        vp = self.vp
        if vp is None:
            return
        vp._qimage_key = None
        vp._load_current()
        vp.update()

    # ------------------------------------------------------------------ clique
    def point_at(self, vp, pos: QPointF):
        ip = vp.widget_to_image(pos)
        return self.r.point_at(ip.x(), ip.y())

    # ------------------------------------------------------------------ mouse
    def press(self, vp, pos: QPointF, button: str) -> bool:
        if button == "left" and self.sculpt_mode:
            self.lasso = [vp.widget_to_image(pos)]
            return True
        return False

    def drag(self, vp, pos: QPointF, dx: float, dy: float, pr: dict) -> bool:
        button = pr.get("button")
        if button == "left" and self.sculpt_mode and self.lasso is not None:
            ip = vp.widget_to_image(pos)
            if not self.lasso or (ip - self.lasso[-1]).manhattanLength() >= 1:
                self.lasso.append(ip)
                vp.update()
            return True
        if button == "left" and self.plane_drag:
            passo = 2 * self.r.radius / max(min(self.size), 1)
            if self.r.nudge_plane(-dy * passo):
                self.refresh(fast=True)
            return True
        if button == "left":
            self.rotate(dx, dy)
            return True
        if button == "middle":
            self.pan_by(dx, dy)
            return True
        if button == "right" and self.mode in ("vr", "surf"):
            self.window_by(dx, dy)
            return True
        return False                       # MIP/MinIP/média: a janela é a do quadro, como sempre

    def release(self, vp, pos: QPointF, pr: dict, is_click: bool) -> bool:
        button = pr.get("button")
        if button == "left" and self.sculpt_mode and self.lasso is not None:
            pontos, self.lasso = self.lasso, None
            recado = self.sculpt_from(pontos)
            self.sculpt_mode = ""
            if recado and self.tab is not None:
                self.tab.status_message.emit(recado)
            return True
        if is_click and button == "left" and not pr.get("hot"):
            pt = self.point_at(vp, pos)
            if pt is not None:
                vp.cursor_point = np.asarray(pt, dtype=float)
                vp.update()
                if self.tab is not None:
                    self.tab.cursor_from_3d(vp, vp.cursor_point)
            return True
        if pr.get("moved") and button in ("left", "middle", "right"):
            self._timer.start(10)          # ao soltar, redesenha na resolução cheia
            return True
        return False

    def wheel(self, steps: float) -> None:
        self.zoom_by(steps)

    # ------------------------------------------------------------------ na tela
    def info_text(self) -> str:
        nome = dict(MODES)[self.mode]
        corte = "" if self.r.untouched() else " · cortado"
        if self.mode == "surf":
            return (f"{nome} · limiar {self.lo:.0f} · giro {self.az:.0f}° · "
                    f"elevação {self.el:.0f}°{corte}")
        return (f"{nome} · giro {self.az:.0f}° · elevação {self.el:.0f}° · "
                f"janela {self.lo:.0f} a {self.hi:.0f}{corte}")

    def state_text(self) -> str:
        """O que está ligado agora, para o usuário nunca ficar sem saber."""
        if self.sculpt_mode == "remove":
            return "Escultura: desenhe o laço em volta do que deve sumir"
        if self.sculpt_mode == "keep":
            return "Escultura: desenhe o laço em volta do que deve ficar"
        if self.plane_drag:
            return "Arrastando o corte: suba e desça com o esquerdo"
        if self.aviso:
            return self.aviso
        return ""

    def orientation_letters(self) -> list[tuple[str, str]]:
        from ipe.imaging.windowing import _axis_letter
        u, v, _d = rotation(self.az, self.el)
        return [(_axis_letter(-u)[:1], "left"), (_axis_letter(u)[:1], "right"),
                (_axis_letter(-v)[:1], "top"), (_axis_letter(v)[:1], "bottom")]

    def draw_extra(self, vp, p) -> None:
        f = QFont()
        f.setPointSizeF(9)
        p.setFont(f)
        # acima do bloco de texto do canto, para não escrever por cima dele
        p.setPen(QColor(230, 210, 80))
        p.drawText(QPointF(10, vp.height() - 58), self.info_text())
        estado = self.state_text()
        if estado:
            p.setPen(QColor(255, 176, 60))
            p.drawText(QPointF(10, vp.height() - 44), estado)
        w, h = vp.width(), vp.height()
        cantos = {"left": QPointF(8, h / 2), "right": QPointF(w - 20, h / 2),
                  "top": QPointF(w / 2 - 5, 32), "bottom": QPointF(w / 2 - 5, h - 40)}
        p.setPen(QColor(255, 210, 90))
        for letra, onde in self.orientation_letters():
            p.drawText(cantos[onde], letra)
        if self.lasso and len(self.lasso) > 1:
            caminho = QPainterPath()
            primeiro = vp.image_to_widget(self.lasso[0])
            caminho.moveTo(primeiro)
            for ip in self.lasso[1:]:
                caminho.lineTo(vp.image_to_widget(ip))
            caminho.closeSubpath()
            p.setPen(QPen(QColor(255, 120, 60), 2, Qt.DashLine))
            p.drawPath(caminho)
        if vp.cursor_point is not None:
            onde = self.r.screen_of(vp.cursor_point)
            if onde is not None:
                c = vp.image_to_widget(QPointF(onde[0], onde[1]))
                if vp.rect().contains(c.toPoint()):
                    p.setPen(QPen(QColor(120, 220, 255), 1))
                    p.drawLine(c + QPointF(-7, 0), c + QPointF(7, 0))
                    p.drawLine(c + QPointF(0, -7), c + QPointF(0, 7))

    # ------------------------------------------------------------------ saídas
    def save_image(self, vp) -> str:
        from PySide6.QtWidgets import QFileDialog
        q = vp._qimage_for_current()
        if q is None:
            return ""
        caminho, _f = QFileDialog.getSaveFileName(vp, "Salvar imagem 3D", "3d.png",
                                                  "PNG (*.png);;JPEG (*.jpg)")
        if caminho:
            q.save(caminho)
            return f"Imagem 3D salva em {caminho}."
        return ""

    def to_film(self, vp) -> str:
        from ipe.imaging.derived import qimage_to_rgb, save_secondary_capture
        q = vp._qimage_for_current()
        storage = getattr(self.tab, "storage_root", None)
        if q is None or storage is None:
            return ""
        uid, _s = save_secondary_capture(qimage_to_rgb(q), self.source_path, self.tab.repo.db, storage,
                                         f"3D {dict(MODES)[self.mode]}", series_number=960)
        from ipe.central.client_repo import upload_if_client
        upload_if_client(self.tab.repo, self.study_uid)
        self.tab.film_requested.emit({"kind": "images", "items": [
            {"study_uid": self.study_uid, "series_uid": uid, "index": 0,
             "label": f"3D {dict(MODES)[self.mode]}"}]})
        return "Imagem 3D enviada ao filme (e salva no exame)."

    def export_model(self, vp) -> str:
        """O que está na tela vira modelo 3D: com o corte, a maca tirada e a escultura."""
        from ipe.ui.surface_dialog import SurfaceDialog
        limiar = self.lo if self.mode in ("vr", "surf") else self.r.p[90]
        mask = self.r.solid_mask(limiar)
        if not mask.any():
            return "Não sobrou nada acima do limiar para virar modelo."
        origem = (float(self.r.lo[2]), float(self.r.lo[1]), float(self.r.lo[0]))
        passo = float(self.r.step)
        dlg = SurfaceDialog(None, None, (0, 0, 0), self.title or "Modelo 3D", vp,
                            grid=(mask, (passo, passo, passo), origem), tab=self.tab)
        dlg.calcular()
        dlg.exec()
        return ""

    # ------------------------------------------------------------------ estruturas (0.99.82)
    def volumes_do_exame(self) -> list:
        """As máscaras 3D ligadas no exame (segmentações, órgãos da IA, nódulos, níveis…) que valem para
        a série deste 3D."""
        from ipe.imaging import overlays as O
        out = []
        for o in getattr(self.tab, "overlay_objects", None) or []:
            if not getattr(o, "enabled", True):
                continue
            vols = list(getattr(o, "volumes", None) or [])
            if not vols and (getattr(o, "masks", None) or getattr(o, "planar", None)):
                try:
                    vols = O.volumes_derivados(o)          # SEG / RTSTRUCT: empilhadas por rótulo
                except Exception:  # noqa: BLE001
                    vols = []
            if not vols:
                continue
            if o.study_uid and self.study_uid and o.study_uid != self.study_uid:
                continue
            so = getattr(o, "so_series", "") or ""
            if so and self.src_uid and so != self.src_uid:
                continue
            out.extend(vols)
        return out

    def ha_estruturas(self) -> bool:
        return bool(self.volumes_do_exame())

    def mostrar_estruturas(self, ligado: bool) -> str:
        """Liga ou desliga as superfícies das estruturas. Devolve um recado (vazio = deu certo)."""
        if not ligado:
            self.estruturas = False
            self.refresh(fast=False)
            return ""
        vols = self.volumes_do_exame()
        if not vols:
            self.estruturas = False
            return "Não há estrutura segmentada neste exame (rode a IA ou segmente uma lesão antes)."
        chave = tuple(id(v) for v in vols)
        if chave != self._estr_chave:
            n = self.r.set_labels(vols)
            self._estr_chave = chave
            if not n:
                self.estruturas = False
                return "As estruturas segmentadas ficam fora deste volume."
        self.estruturas = True
        self.refresh(fast=False)
        return ""

    def add_menu_actions(self, vp, menu: QMenu) -> None:
        menu.addAction("Voltar à série de cortes", lambda: self.tab.close_3d(vp))
        a_est = menu.addAction("Estruturas segmentadas (superfícies coloridas)")
        a_est.setCheckable(True)
        a_est.setChecked(self.estruturas)
        a_est.setEnabled(self.estruturas or self.ha_estruturas())
        a_est.toggled.connect(lambda on: self._recado(self.mostrar_estruturas(on)))
        m = menu.addMenu("Vista")
        for texto, az, el in VISTAS:
            m.addAction(texto, lambda _c=False, a=az, e=el: self.set_view(a, e))
        menu.addAction("Cortar pelo plano do olhar", self.cut_view_plane)
        menu.addAction("Volume inteiro", self.cut_reset)
        menu.addAction("Exportar modelo 3D (STL, OBJ, GLB, 3MF)…",
                       lambda: self._recado(self.export_model(vp)))
        menu.addAction("Salvar a imagem 3D…", lambda: self._recado(self.save_image(vp)))
        menu.addAction("Enviar a imagem 3D ao filme", lambda: self._recado(self.to_film(vp)))
        menu.addSeparator()

    def _recado(self, texto: str) -> None:
        if texto and self.tab is not None:
            self.tab.status_message.emit(texto)


VISTAS = [("Anterior", 0, 0), ("Posterior", 180, 0), ("Direita", 270, 0), ("Esquerda", 90, 0),
          ("Superior", 0, -89), ("Inferior", 0, 89)]


class Render3DBar(QToolBar):
    """Barra do 3D, no mesmo lugar e no mesmo estilo da barra do MPR."""

    def __init__(self, tab):
        super().__init__(tab)
        self.tab = tab
        self.setStyleSheet("QToolBar{background:#1b2a1f;color:#ddd;spacing:6px}"
                           "QLabel{color:#ddd}QToolButton{color:#e8e8e8}QComboBox{color:#111}")
        self._mudo = False
        self.addWidget(QLabel("  3D — modo:"))
        self.c_mode = QComboBox()
        for k, nome in MODES:
            self.c_mode.addItem(nome, k)
        self.c_mode.setFixedWidth(150)
        self.c_mode.activated.connect(self._modo)
        self.addWidget(self.c_mode)
        self.addWidget(QLabel(" preset:"))
        self.c_preset = QComboBox()
        for k, (nome, *_r) in VR_PRESETS.items():
            self.c_preset.addItem(nome, k)
        self.c_preset.setFixedWidth(120)
        self.c_preset.activated.connect(self._preset)
        self.addWidget(self.c_preset)
        self.addWidget(QLabel(" opacidade:"))
        self.s_op = QSlider(Qt.Horizontal)
        self.s_op.setRange(1, 100)
        self.s_op.setFixedWidth(90)
        self.s_op.valueChanged.connect(self._opacidade)
        self.addWidget(self.s_op)
        self.addWidget(QLabel(" cor:"))
        self.c_cmap = QComboBox()
        self.c_cmap.addItem("Cinza", "")
        for k in CM.COLORMAPS:
            self.c_cmap.addItem(CM.name(k), k)
        self.c_cmap.setFixedWidth(120)
        self.c_cmap.activated.connect(self._cor)
        self.addWidget(self.c_cmap)
        self.a_vista = self.addAction("Vistas…", self._menu_vistas)
        self.a_corte = self.addAction("Cortar…", self._menu_cortes)
        self.a_escultura = self.addAction("Esculpir…", self._menu_escultura)
        self.a_estr = self.addAction("Estruturas", self._estruturas)
        self.a_estr.setToolTip("Mostra as estruturas segmentadas (órgãos da IA, lesões, nódulos) como superfícies "
                               "coloridas sobre o 3D")
        self.a_estr.setCheckable(True)
        self.a_girar = self.addAction("Girar", self._girar)
        self.a_girar.setToolTip("Gira o volume sem parar, 360°")
        self.a_girar.setCheckable(True)
        self.a_inteiro = self.addAction("Volume inteiro", self._inteiro)
        self.a_inteiro.setToolTip("Desfaz cortes, plano e escultura")
        self.a_modelo = self.addAction("Modelo 3D…", self._modelo)
        self.a_modelo.setToolTip("Exporta o que está na tela como STL, OBJ, PLY, GLB ou 3MF")
        self.a_voltar = self.addAction("Voltar à série", self._voltar)
        self.a_voltar.setToolTip("Este quadro volta a mostrar os cortes da série")
        self.info = QLabel("")
        self.addWidget(self.info)
        self.setVisible(False)

    # ------------------------------------------------------------------
    def _quadro_3d(self) -> View3D | None:
        vp = getattr(self.tab, "active", None)
        return getattr(vp, "render3d", None) if vp is not None else None

    def _recon(self):
        """O quadro ativo é uma reconstrução da etapa do protocolo (0.93)? Então a barra do 3D
        vale para ele também: a reconstrução é tratada como um volume 3D."""
        vp = getattr(self.tab, "active", None)
        f = getattr(self.tab, "recon_da_etapa", None)
        return f(vp) if vp is not None and f is not None and getattr(vp, "render3d", None) is None else None

    def view(self) -> View3D | None:
        """O 3D do quadro ativo. Reconstrução da etapa vira 3D aqui, no primeiro uso da barra — com
        a mesma espessura (a caixa do corte), o mesmo modo e olhando do mesmo lado."""
        v = self._quadro_3d()
        if v is None and self._recon() is not None:
            v = self.tab.recon_para_3d(self.tab.active)
        return v

    def _modo(self, *_a) -> None:
        modo = self.c_mode.currentData()       # lido antes: virar 3D ressincroniza a barra
        v = self.view()
        if v is not None:
            v.set_mode(modo)

    def _preset(self, *_a) -> None:
        preset = self.c_preset.currentData()
        v = self.view()
        if v is not None:
            v.apply_preset(preset)

    def _opacidade(self, valor: int) -> None:
        if self._mudo:
            return
        v = self.view()
        if v is not None:
            v.opacity = valor / 200.0
            v.refresh(fast=False)

    def _cor(self, *_a) -> None:
        cor = self.c_cmap.currentData() or ""
        v = self.view()
        if v is None:
            return
        if v.mode in ("vr", "surf"):
            v.cmap = cor
            v.refresh(fast=False)
        elif v.vp is not None:
            v.vp.set_colormap(cor)

    def _menu_vistas(self) -> None:
        v = self.view()
        if v is None:
            return
        m = QMenu(self)
        for texto, az, el in VISTAS:
            m.addAction(texto, lambda _c=False, a=az, e=el: v.set_view(a, e))
        m.exec(self._onde(self.a_vista))

    def _menu_cortes(self) -> None:
        v = self.view()
        if v is None:
            return
        tem_cruz = any(getattr(w, "cursor_point", None) is not None
                       for w in getattr(self.tab, "viewports", []))
        m = QMenu(self)
        m.addAction("Cortar a partir do cursor 3D:" if tem_cruz
                    else "Cortar a partir do meio do volume:").setEnabled(False)
        for chave, rotulo in CUTS:
            m.addAction(rotulo, lambda _c=False, k=chave: v.cut_box(k))
        m.addSeparator()
        m.addAction("Plano do olhar (arrastar com o esquerdo)", v.cut_view_plane)
        if v.plane_drag:
            m.addAction("Parar de arrastar o corte", lambda: self._parar_arrasto(v))
        m.addSeparator()
        m.addAction("Volume inteiro", v.cut_reset)
        m.exec(self._onde(self.a_corte))

    def _parar_arrasto(self, v: View3D) -> None:
        v.plane_drag = False
        v.refresh(fast=False)

    def _menu_escultura(self) -> None:
        v = self.view()
        if v is None:
            return
        m = QMenu(self)
        m.addAction("Apagar o que estiver dentro do laço", lambda: self._escultura(v, "remove"))
        m.addAction("Guardar só o que estiver dentro do laço", lambda: self._escultura(v, "keep"))
        m.addSeparator()
        m.addAction("Tirar a maca da TC", lambda: self.tab.status_message.emit(v.remove_table()))
        m.addSeparator()
        m.addAction("Volume inteiro (desfaz tudo)", v.cut_reset)
        m.exec(self._onde(self.a_escultura))

    def _escultura(self, v: View3D, modo: str) -> None:
        v.sculpt_mode = modo
        v.lasso = None
        v.refresh(fast=False)
        self.tab.status_message.emit("Desenhe o laço com o botão esquerdo, em volta da região.")

    def _estruturas(self, ligado=None) -> None:
        v = self.view()
        if v is None:
            return
        recado = v.mostrar_estruturas(self.a_estr.isChecked() if ligado is None else bool(ligado))
        if recado:
            self.tab.status_message.emit(recado)
        self.sync()

    def _girar(self, ligado: bool) -> None:
        v = self.view()
        if v is not None:
            v.cine(ligado)

    def _inteiro(self) -> None:
        v = self.view()
        if v is not None:
            v.cut_reset()

    def _modelo(self) -> None:
        v = self.view()
        vp = getattr(self.tab, "active", None)
        if v is not None and vp is not None:
            recado = v.export_model(vp)
            if recado:
                self.tab.status_message.emit(recado)

    def _voltar(self) -> None:
        vp = getattr(self.tab, "active", None)
        if vp is not None and getattr(vp, "render3d", None) is not None:
            self.tab.close_3d(vp)

    def _onde(self, acao):
        w = self.widgetForAction(acao)
        return w.mapToGlobal(w.rect().bottomLeft()) if isinstance(w, QWidget) else self.mapToGlobal(
            self.rect().bottomLeft())

    # ------------------------------------------------------------------
    def sync(self) -> None:
        """Deixa a barra igual ao 3D do quadro ativo."""
        v = self._quadro_3d()
        if v is None:
            rec = self._recon()
            if rec is None:
                self.setVisible(False)
                return
            self._mostrar_recon(rec)
            return
        self._mudo = True
        try:
            self.c_mode.setCurrentIndex(max(self.c_mode.findData(v.mode), 0))
            self.c_preset.setCurrentIndex(max(self.c_preset.findData(v.preset), 0))
            self.c_preset.setEnabled(v.mode in ("vr", "surf"))
            self.s_op.setEnabled(v.mode == "vr")
            self.s_op.setValue(int(np.clip(v.opacity * 200, 1, 100)))
            atual = v.cmap if v.mode in ("vr", "surf") else (v.vp.state.cmap if v.vp else "")
            self.c_cmap.setCurrentIndex(max(self.c_cmap.findData(atual or ""), 0))
            self.a_girar.setChecked(v.cine_on())
            self.a_estr.setChecked(v.estruturas)
            self.a_estr.setEnabled(v.estruturas or v.ha_estruturas())
            self.a_inteiro.setEnabled(not v.r.untouched())
            self.info.setText("   " + v.info_text())
        finally:
            self._mudo = False
        self.setVisible(True)

    def _mostrar_recon(self, rec: dict) -> None:
        """A barra para uma reconstrução que ainda é corte: o modo dela, e o resto pronto para usar
        — qualquer ação transforma o quadro num 3D."""
        self._mudo = True
        try:
            self.c_mode.setCurrentIndex(max(self.c_mode.findData(rec["modo"]), 0))
            self.c_preset.setEnabled(False)
            self.s_op.setEnabled(False)
            self.c_cmap.setCurrentIndex(max(self.c_cmap.findData(rec["cmap"] or ""), 0))
            self.a_girar.setChecked(False)
            self.a_estr.setChecked(False)
            self.a_estr.setEnabled(False)
            self.a_inteiro.setEnabled(False)
            self.info.setText("   " + rec["texto"])
        finally:
            self._mudo = False
        self.setVisible(True)

