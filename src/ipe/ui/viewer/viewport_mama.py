"""Mamografia no quadro (mixin do Viewport, separado do `viewport.py` na 0.100.42).

Aqui ficam: o ponto anatômico (mamilo, parede), enquadrar a mama no quadro e o eixo de simetria à mão com a ROI
espelhada.

Os métodos continuam sendo do Viewport (mesmos nomes): o resto do programa e os testes não mudam.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QPointF

from ipe.core.i18n import tr
from ipe.imaging.series import Frame, FrameCache, FrameImage  # noqa: F401


log = logging.getLogger("ipe.ui.viewer.viewport")      # o mesmo registro de antes da separação


class VpMamaMixin:
    """VpMamaMixin: métodos do ViewerTab separados (mesmos nomes)."""

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
        alvo = QPointF(tx, self.height() / 2.0 + float(getattr(self, "mg_dy", 0.0) or 0.0))
        self.state.pan += self._delta_unrotated(alvo - agora)
        self.anat_lock = ("mama", float(self.state.zoom),
                          float(self.MARGEM_MAMA if margem is None else margem))
        self.update()
        return True

    def mamilo_imagem(self) -> tuple[float, float] | None:
        """O mamilo aproximado nesta imagem (pixels), guardado por imagem."""
        if self._img is None or self._img.is_color:
            return None
        hit = getattr(self, "_mamilo_cache", None)
        if hit is not None and hit[0] == id(self._img):
            return hit[1]
        from ipe.imaging.mammo import mamilo
        try:
            pt = mamilo(self._img.pixels, self._img.header.get("_monochrome1") == "1", self.chest_image_side())
        except Exception:  # noqa: BLE001
            pt = None
        self._mamilo_cache = (id(self._img), pt)
        return pt

    def mamilo_na_tela(self) -> float | None:
        """Altura (y da tela) do mamilo, ou None."""
        pt = self.mamilo_imagem()
        if pt is None:
            return None
        return float(self.image_to_widget(QPointF(pt[0], pt[1])).y())

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


    # -------------------------------------------- eixo de simetria à mão (0.99.61, rodada mama P2)
    CHAVE_EIXOS = "roi_espelhada.eixos"

    def _serie_do_eixo(self) -> str:
        f = self.current_frame()
        return (f.series_uid if f is not None and getattr(f, "series_uid", "") else "") or self.series_uid or ""

    def eixo_manual(self) -> float | None:
        """x (mm do paciente) do eixo marcado à mão nesta série, ou None."""
        if self.settings is None:
            return None
        v = (self.settings.get(self.CHAVE_EIXOS, {}) or {}).get(self._serie_do_eixo())
        return float(v) if v is not None else None

    def marcar_eixo(self, pos: QPointF) -> float | None:
        """O eixo passa pelo ponto clicado: o plano sagital (x constante) do paciente nesse ponto. Fica guardado
        para a série, neste computador."""
        if self._img is None or self.settings is None:
            return None
        ip = self.widget_to_image(pos)
        p = self.pixel_to_patient(ip.x(), ip.y())
        if p is None:
            self.sig.status_message.emit(tr("Sem geometria: não dá para marcar o eixo nesta imagem."))
            return None
        eixos = dict(self.settings.get(self.CHAVE_EIXOS, {}) or {})
        eixos[self._serie_do_eixo()] = round(float(p[0]), 2)
        if len(eixos) > 300:                               # não cresce para sempre
            eixos = dict(list(eixos.items())[-300:])
        self.settings.set(self.CHAVE_EIXOS, eixos)
        self.settings.save()
        self.sig.status_message.emit(tr(f"Eixo de simetria marcado em x = {float(p[0]):.1f} mm nesta série."))
        self.update()
        return float(p[0])

    def esquecer_eixo(self) -> None:
        if self.settings is None:
            return
        eixos = dict(self.settings.get(self.CHAVE_EIXOS, {}) or {})
        eixos.pop(self._serie_do_eixo(), None)
        self.settings.set(self.CHAVE_EIXOS, eixos)
        self.settings.save()
        self.sig.status_message.emit(tr("Eixo de simetria de volta ao automático."))
        self.update()

    def _linha_do_eixo(self):
        """(QPointF, QPointF) da linha do eixo à mão neste quadro (axial ou coronal), ou None."""
        xm = self.eixo_manual()
        if xm is None or self._img is None:
            return None
        h, w = self._img.pixels.shape[:2]
        p0, p1 = self.pixel_to_patient(0.0, h / 2), self.pixel_to_patient(1.0, h / 2)
        if p0 is None or p1 is None or abs(float(p1[0] - p0[0])) < 1e-6:
            return None                                    # sagital: o eixo é um corte, não uma linha
        u = (xm - float(p0[0])) / float(p1[0] - p0[0])
        if not (0 <= u <= w):
            return None
        return self.image_to_widget(QPointF(u, 0)), self.image_to_widget(QPointF(u, h))

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
