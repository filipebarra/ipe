"""O desenho do quadro (mixin do Viewport, separado do `viewport.py` na 0.100.42).

Aqui ficam: o mosaico de cortes, a pintura da imagem e do que vai por cima (texto dos cantos, réguas, linhas de
referência, barra de cores), a cópia do quadro (Ctrl+C), os selos de integridade e o ícone do mouse.

Os métodos continuam sendo do Viewport (mesmos nomes): o resto do programa e os testes não mudam.
"""

from __future__ import annotations

import logging
import math

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QImage, QPainter, QPen,
)
from PySide6.QtWidgets import QApplication, QMessageBox

from ipe.core.i18n import tr
from ipe.core import cronometro as _CR
from ipe.imaging.series import Frame, FrameCache, FrameImage  # noqa: F401
from ipe.imaging import colormaps as CM
from ipe.imaging.windowing import orientation_labels, to_display

from ipe.ui.viewer.annotate import (
    TOOLS,
)

log = logging.getLogger("ipe.ui.viewer.viewport")      # o mesmo registro de antes da separação


class VpDesenhoMixin:
    """VpDesenhoMixin: métodos do ViewerTab separados (mesmos nomes)."""

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
               self.state.cmap, self.state.filter, self.settings.get("monitors.gsdf_stamp", 0),
               bool(getattr(self, "inverter_mama", False)))
        if key == self._qimage_key and self._qimage is not None:
            return self._qimage
        bruta = img
        img = self._filtered(img)
        so_mama = self._mascara_para_inverter(bruta)
        disp = to_display(img, self.state.width, self.state.level,
                          self.state.invert if so_mama is None else False, self.state.cmap)
        if so_mama is not None and disp.ndim == 2 and disp.shape == so_mama.shape:
            disp = np.where(so_mama, 255 - disp, 0).astype(np.uint8)
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

    def _mascara_para_inverter(self, img):
        """Máscara da mama quando "inverter só a mama" está ligado (só imagem cinza); senão None."""
        if not getattr(self, "inverter_mama", False) or img is None or img.is_color or img.pixels.ndim != 2:
            return None
        hit = getattr(self, "_mascara_mama_cache", None)
        if hit is not None and hit[0] == id(img):
            return hit[1]
        from ipe.imaging.mammo import mascara_da_mama
        try:
            m = mascara_da_mama(img.pixels, img.header.get("_monochrome1") == "1")
        except Exception:  # noqa: BLE001
            log.debug("máscara da mama", exc_info=True)
            m = None
        self._mascara_mama_cache = (id(img), m)
        return m

    def set_inverter_mama(self, on: bool) -> bool:
        """Inverte só a mama (PV 17): tecido invertido, fundo preto. Devolve se achou a mama."""
        self.inverter_mama = bool(on)
        self._qimage_key = None
        self.update()
        return not on or self._mascara_para_inverter(self._img) is not None

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

    def atualizar_glicemia(self) -> None:
        """0.99.88: o fator da glicemia digitada para o exame (SUVglic = SUV × glicemia ÷ 100)."""
        self.glic = None
        if not self.suv_factor:
            return
        repo = getattr(self.window(), "repo", None)
        if repo is None or not self.study_uid:
            return
        try:
            from ipe.ai import biometria as B
            self.glic = B.fator_glicemia(B.glicemia(repo, self.study_uid))
        except Exception:  # noqa: BLE001
            log.debug("glicemia do exame", exc_info=True)

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
            if _CR._atual is not None and not _CR._atual.fechado:
                _CR.primeira_imagem()
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
        if self.baixando_txt:
            bl.append((self.baixando_txt, None, "imagem"))
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
        linha_eixo = self._linha_do_eixo() if not self._capturando and self.settings is not None else None
        if linha_eixo is not None:                         # 0.99.61: eixo de simetria marcado à mão
            caneta = QPen(QColor(0, 220, 255, 170), 1, Qt.DashLine)
            p.setPen(caneta)
            p.drawLine(linha_eixo[0], linha_eixo[1])
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
            if self.left_tool == "caixa_ia":                  # 0.99.83: a caixa do MedSAM2, tracejada
                pen.setColor(QColor(255, 200, 40))
                pen.setStyle(Qt.DashLine)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawRect(QRectF(self.image_to_widget(self._obl_draft[0]),
                                  self.image_to_widget(self._obl_draft[1])).normalized())
            else:
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
