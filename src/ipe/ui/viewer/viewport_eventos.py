"""Mouse e teclado no quadro (mixin do Viewport, separado do `viewport.py` na 0.100.42).

Aqui ficam: os botões do mouse e o arrasto, as teclas que emprestam o botão esquerdo, as pontas da barra de cores, a
roda, o teclado e as janelas prontas (presets e as do arquivo).

Os métodos continuam sendo do Viewport (mesmos nomes): o resto do programa e os testes não mudam.
"""

from __future__ import annotations

import logging
import math
import time

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QAction, QFont, QFontMetrics, QKeyEvent, QMouseEvent, QWheelEvent,
)
from PySide6.QtWidgets import QInputDialog, QMenu

from ipe.imaging.series import Frame, FrameCache, FrameImage  # noqa: F401

from ipe.ui.viewer.annotate import (
    ANNOT_TOOLS, CLICK_TOOLS,
)

TOMO_DIAL = "tomodial"          # área clicável do indicador de profundidade da tomossíntese
CBAR = {"cbar_hi": "topo", "cbar_lo": "base"}    # números clicáveis da barra de cores
# Áreas clicáveis que também respondem ao botão direito — nelas, o direito é o sentido
# contrário do esquerdo (a fase da dinâmica anda para a frente e para trás).
HOTSPOTS_DOS_DOIS_BOTOES = {"fase"}

log = logging.getLogger("ipe.ui.viewer.viewport")      # o mesmo registro de antes da separação


class VpEventosMixin:
    """VpEventosMixin: métodos do ViewerTab separados (mesmos nomes)."""

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
        if hot is None and tool in ("oblique", "caixa_ia") and self._img is not None:
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
        if not pr["hot"] and pr["tool"] in ("oblique", "caixa_ia"):
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
        if not pr["hot"] and pr["tool"] == "caixa_ia":             # 0.99.83: MedSAM2
            draft, self._obl_draft = self._obl_draft, None
            self.update()
            if draft is not None and pr["moved"]:
                a, b = draft[0], self.widget_to_image(pos)
                if abs(a.x() - b.x()) >= 3 and abs(a.y() - b.y()) >= 3:
                    self.sig.caixa_ia_requested.emit(self, min(a.x(), b.x()), min(a.y(), b.y()),
                                                      max(a.x(), b.x()), max(a.y(), b.y()))
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
