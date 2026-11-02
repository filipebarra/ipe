"""Medidas e anotações no viewport: criar, editar, desenhar e navegar.

É um "mixin" do Viewport: as funções usam o estado do quadro (imagem, zoom,
série), mas ficam aqui para o viewport não virar um arquivo gigante.

Formas de desenhar (por ferramenta):
- dois pontos, arrastando: régua, seta, ROI elíptica/retangular, diferença de altura,
  calibração e curva tempo-intensidade;
- um clique: intensidade (valor do pixel) e texto;
- cliques sucessivos (fecha com duplo clique ou Enter): polilinha, ROI poligonal
  (também fecha clicando no 1º ponto; arrastando vira desenho livre) e rotular coluna;
- arrastar livre: lápis;
- ângulo: arraste o 1º braço e clique o 3º ponto (ou três cliques);
- duas retas (arraste uma, depois a outra): ângulo de Cobb e índice cardiotorácico.
"""

from __future__ import annotations

import logging
import math

import numpy as np

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QInputDialog, QMenu, QRadioButton, QVBoxLayout)

from ipe.imaging import measure as M
from ipe.imaging import us_regioes as US
from ipe.imaging.measure import Annotation

log = logging.getLogger(__name__)

TOOLS = {
    "wl": "Janela/nível",
    "zoom": "Zoom",
    "pan": "Pan",
    "scroll": "Rolar cortes",
    "measure": "Régua",
    "polyline": "Polilinha",
    "angle": "Ângulo",
    "cobb": "Ângulo de Cobb",
    "ellipse": "ROI elíptica",
    "rect": "ROI retangular",
    "polygon": "ROI poligonal / livre",
    "probe": "Intensidade (valor do pixel)",
    "ruler3d": "Régua 3D (um ponto em cada corte)",
    "height": "Diferença de altura",
    "ctr": "Índice cardiotorácico",
    "spine": "Rotular coluna",
    "tic": "Curva tempo-intensidade",
    "calibration": "Linha de calibração",
    "arrow": "Seta",
    "text": "Texto",
    "pencil": "Lápis",
    "cross": "Cursor 3D",
    "oblique": "MPR oblíquo (desenhe uma linha)",
    "curve": "MPR curvo (clique os pontos; duplo clique termina)",
    "rotplane": "Girar plano (oblíquo: arraste para inclinar)",
    "quadzoom": "Zoom por quadrante (cada clique: próximo quadrante)",
    "loupe": "Lupa (segure o botão; roda muda o aumento)",
    "grow": "Segmentar 3D (clique na lesão: volume, SUV, TLG)",
    "film": "Enviar ao filme (clique na imagem)",
    "pick": "Selecionar medida (clique para escolher; arraste as pontas para editar)",
}
# ferramentas de "clique" (não de arrastar): no botão direito/meio, o botão age como o esquerdo
CLICK_TOOLS = {"cross", "film", "oblique", "curve", "quadzoom", "loupe", "grow"}

# O menu do botão esquerdo tinha 31 itens numa lista só, e lista de 31 ninguém lê. Dividido em
# dois: o que move a imagem (Mouse) e o que mede (Medidas). A ferramenta escolhida é a mesma coisa
# nos dois casos — o que muda é onde ela está.
FERRAMENTAS_DE_MEDIDA = ("pick", "measure", "polyline", "angle", "cobb", "ellipse", "rect",
                         "polygon", "probe", "ruler3d", "height", "ctr", "spine", "tic", "calibration",
                         "grow", "arrow", "text", "pencil")


def ferramentas_divididas() -> tuple[dict, dict]:
    """(ferramentas do mouse, ferramentas de medida), na ordem em que aparecem no menu."""
    medidas = {k: TOOLS[k] for k in FERRAMENTAS_DE_MEDIDA if k in TOOLS}
    mouse = {k: v for k, v in TOOLS.items() if k not in medidas}
    return mouse, medidas
# ferramenta do botão esquerdo -> tipo de anotação
ANNOT_TOOLS = {"measure": "line", "polyline": "polyline", "angle": "angle", "cobb": "cobb",
               "ellipse": "ellipse", "rect": "rect", "polygon": "polygon", "probe": "probe", "ruler3d": "ponto3d",
               "height": "height", "ctr": "ctr", "spine": "spine", "tic": "tic",
               "calibration": "calibration", "arrow": "arrow", "text": "text", "pencil": "pencil",
               # "pick" passa pelo mesmo caminho das medidas, mas **não cria** nenhuma: só escolhe,
               # move e edita a que já está lá. Ferramenta que cria não serve para selecionar —
               # cada clique no vazio deixava uma medida nova para trás.
               "pick": "pick"}

def pedir_calibracao(parent, so_imagem: bool, mm: float = 10.0) -> tuple[float, str] | None:
    """Pergunta o comprimento real do segmento e até onde a calibração vale.

    Devolve (mm, "imagem"|"serie") ou None se o médico desistiu. Separar os dois escopos é o
    que permite calibrar ultrassom: lá cada imagem tem a sua escala, e uma calibração que
    vazasse para a série toda daria medida errada nas outras imagens, sem avisar.
    """
    d = QDialog(parent)
    d.setWindowTitle("Calibração")
    lay = QVBoxLayout(d)
    form = QFormLayout()
    campo = QDoubleSpinBox(d)
    campo.setRange(0.01, 100000.0)
    campo.setDecimals(2)
    campo.setSuffix(" mm")
    campo.setValue(mm)
    form.addRow("Comprimento real deste segmento:", campo)
    lay.addLayout(form)
    r_img = QRadioButton("Vale só para esta imagem", d)
    r_ser = QRadioButton("Vale para toda a série", d)
    (r_img if so_imagem else r_ser).setChecked(True)
    lay.addWidget(r_img)
    lay.addWidget(r_ser)
    botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=d)
    botoes.accepted.connect(d.accept)
    botoes.rejected.connect(d.reject)
    lay.addWidget(botoes)
    campo.setFocus()
    campo.selectAll()
    if d.exec() != QDialog.Accepted:
        return None
    return float(campo.value()), ("imagem" if r_img.isChecked() else "serie")

TWO_POINT = {"line", "arrow", "ellipse", "rect", "height", "calibration", "tic"}
TWO_LINE = {"cobb", "ctr"}
RUBBER = {"angle", "polygon", "polyline"}          # último ponto segue o mouse enquanto desenha
MEASURE_COLOR = QColor(80, 255, 120)
SELECTED_COLOR = QColor(255, 230, 80)
ANNOT_COLORS = {"arrow": QColor(255, 220, 80), "text": QColor(255, 220, 80), "pencil": QColor(255, 150, 60),
                "spine": QColor(120, 200, 255), "calibration": QColor(255, 120, 255),
                "tic": QColor(255, 120, 120), "seg": QColor(90, 220, 255)}
#: o que marca a ROI de referência (0.99.22); sobrevive a ligar/desligar lesão
REF_CHAVES = ("referencia", "ref_media")
ROI_LABEL_LEFT = ("ellipse", "polygon", "rect", "tic", "line", "arrow", "polyline", "height")


class AnnotationMixin:
    # ------------------------------------------------------------ estado
    @property
    def left_tool(self) -> str:
        return self._left_tool

    @left_tool.setter
    def left_tool(self, tool: str) -> None:
        if tool != self._left_tool:
            if self._draft is not None and self._draft.kind == "spine":
                self.finish_draft()
            self.cancel_draft()
        self._left_tool = tool

    def frame_key(self) -> tuple[str, int] | None:
        f = self.current_frame()
        if f is None:
            return None
        if f.is_virtual:     # reconstruções: medidas só nesta sessão
            return ("", f.frame_index)
        return (f.sop_uid, f.frame_index)

    def frame_annotations(self) -> list[Annotation]:
        key = self.frame_key()
        return [a for a in self.annotations if a.frame_key == key]

    def _load_annotations(self) -> list[Annotation]:
        frames = [f for ph in self.phases for f in ph] if getattr(self, "phases", None) else self.frames
        if self.annotation_store is None or not frames or frames[0].is_virtual:
            return []
        try:
            return self.annotation_store.load(frames)
        except Exception as e:  # noqa: BLE001
            log.warning("Não foi possível carregar as medidas: %s", e)
            return []

    def _store(self, op: str, ann: Annotation) -> None:
        if self.annotation_store is not None and ann.frame_key[0]:
            try:
                getattr(self.annotation_store, op)(ann)
            except Exception as e:  # noqa: BLE001
                log.warning("Falha ao gravar medida (%s): %s", op, e)
        self.sig.annotations_changed.emit(self)

    def _calibracoes(self) -> list[Annotation]:
        return [a for a in reversed(self.annotations)
                if a.kind == "calibration" and a.done and M.calibration_spacing(a)]

    def calibracao_da_imagem(self) -> tuple[float, float] | None:
        """Calibração feita à mão **nesta imagem** (a mais recente vence)."""
        chave = self.frame_key()
        if chave is None:
            return None
        for a in self._calibracoes():
            if a.frame_key == chave:
                return M.calibration_spacing(a)
        return None

    def calibracao_da_serie(self) -> tuple[float, float] | None:
        """Calibração feita à mão em outra imagem e marcada como válida para a série toda."""
        f = self.current_frame()
        series = f.series_uid if f is not None and f.series_uid else self.series_uid
        for a in self._calibracoes():
            if (a.meta or {}).get("escopo") == "imagem":
                continue
            if a.series_uid == series or not a.frame_key[0]:
                return M.calibration_spacing(a)
        return None

    def measure_spacing(self, ann: Annotation | None = None) -> tuple[float, float] | None:
        """Escala das medidas, nesta ordem: calibração desta imagem, calibração da série,
        região calibrada do ultrassom onde a medida está, espaçamento do arquivo.

        A ordem é a da confiança: o que o médico mediu nesta imagem vale mais do que o que
        ele mediu em outra, e os dois valem mais do que a tag — porque quem calibra à mão já
        viu que a tag não servia. Sem nada disso a medida sai em pixels, dizendo que é pixel.
        """
        sp = self.calibracao_da_imagem() or self.calibracao_da_serie()
        if sp:
            return sp
        img = self._img
        if img is None:
            return None
        if getattr(img, "us_regioes", ()):  # ultrassom: a régua é por região, dentro da região
            if ann is not None and ann.points:
                return US.espacamento_dos_pontos(img.us_regioes, ann.points)
            return US.espacamento(img.us_regioes)
        return img.pixel_spacing

    def escala_texto(self) -> str:
        """De onde veio a escala desta imagem — a tela não pode deixar dúvida sobre isso."""
        if self.calibracao_da_imagem():
            return "Escala: calibrada nesta imagem"
        if self.calibracao_da_serie():
            return "Escala: calibrada na série"
        img = self._img
        if img is None:
            return ""
        if getattr(img, "us_regioes", ()):
            return "Escala: região do ultrassom"
        if img.pixel_spacing:
            return ""
        return "Sem escala — medidas em pixels"

    def is_calibrated(self) -> bool:
        return bool(self.calibracao_da_imagem() or self.calibracao_da_serie())

    # ------------------------------------------------------------ ciclo de vida da medida
    def _finish(self, ann: Annotation, created: bool = True) -> None:
        ann.done = True
        ann.cache.clear()
        if self._draft is ann:
            self._draft = None
        if ann.kind == "calibration" and not ann.text:
            # No ultrassom a escala muda a cada imagem (profundidade, zoom): o padrão é valer
            # só aqui. Nas outras modalidades uma calibração serve para a série toda.
            so_imagem = bool(getattr(self._img, "us_regioes", ()) or (self.modality or "").upper() == "US")
            resp = pedir_calibracao(self, so_imagem)
            if resp is None:
                self.annotations.remove(ann)
                self.update()
                return
            mm, escopo = resp
            ann.text = f"{mm:g}"
            ann.meta = dict(ann.meta or {})
            ann.meta["escopo"] = escopo
            for a in self.annotations:
                a.cache.clear()
        if ann.meta.get("lesion") is not None:
            self.update_lesion_values(ann)
        if ann.kind == "ponto3d" and created:
            self._ponto_da_regua3d(ann)
        self._store("save", ann)
        if ann.kind == "tic":
            self.sig.tic_requested.emit(self, ann)
        if created and not self.settings.get("viewer.measure_continuous", True):
            self.sig.tool_requested.emit("wl")
        self.update()

    def update_lesion_values(self, ann: Annotation) -> None:
        """Recalcula os valores (mm, SUV…) guardados na medida ligada a uma lesão."""
        from ipe.imaging.lesions import measure_values
        img = self._img
        pix = img.pixels if img is not None and not img.is_color else None
        if ann.kind == "seg":           # os valores vêm da segmentação 3D, não do desenho
            return
        keep = {k: v for k, v in ann.meta.items() if k in ("lesion", "lesion_name", "role") + REF_CHAVES}
        try:
            vals = measure_values(ann.kind, ann.points, pix, self.measure_spacing(ann), getattr(self, "suv_factor", None))
        except Exception as e:  # noqa: BLE001
            log.warning("valores da lesão: %s", e)
            vals = {}
        ann.meta = {**keep, **vals}

    def link_lesion(self, ann: Annotation, lesion_id: int | None, name: str = "") -> None:
        """Liga (ou desliga, com None) a medida a uma lesão do acompanhamento."""
        if lesion_id is None:
            ann.meta = {k: v for k, v in ann.meta.items() if k not in ("lesion", "lesion_name")} \
                if ann.kind == "seg" else {k: v for k, v in ann.meta.items() if k in REF_CHAVES}
        else:
            base = dict(ann.meta) if ann.kind == "seg" else {k: v for k, v in ann.meta.items() if k in REF_CHAVES}
            ann.meta = {**base, "lesion": lesion_id, "lesion_name": name}
            self.update_lesion_values(ann)
        ann.cache.clear()
        self._store("save", ann)
        self.update()

    # ---- régua 3D (0.99.22, plano AW 8): A num corte, B em outro (ou em outro quadro)
    def _ponto_da_regua3d(self, ann: Annotation) -> None:
        """Primeiro clique: ponto A. Segundo (em qualquer corte ou quadro da aba): ponto B, e a
        distância em 3D com dx/dy/dz vai para os dois."""
        import uuid
        pt = ann.points[0]
        xyz = self.pixel_to_patient(pt[0], pt[1])
        if xyz is None:
            ann.meta = {"papel": "A", "erro": "imagem sem posição no paciente"}
            return
        estado = getattr(self, "regua3d_estado", None)
        if estado is None:
            estado = self.regua3d_estado = {}
        pend = estado.get("A")
        dono = estado.get("dono_A")
        if pend is not None and dono is not None and pend not in getattr(dono, "annotations", []):
            pend = None                          # o ponto A foi apagado: este vira o novo A
        xyz = [float(v) for v in xyz]
        if pend is None or pend is ann:
            ann.meta = {"papel": "A", "xyz": xyz, "par": uuid.uuid4().hex[:12]}
            estado["A"] = ann
            estado["dono_A"] = self
            return
        a_xyz = np.asarray(pend.meta["xyz"], float)
        d = np.asarray(xyz) - a_xyz
        dist = float(np.linalg.norm(d))
        mesmo_plano = pend.frame_key == ann.frame_key and bool(ann.frame_key[0])
        dados = {"dist": dist, "d": [float(x) for x in d], "plano": "2D" if mesmo_plano else "3D"}
        ann.meta = {"papel": "B", "xyz": xyz, "par": pend.meta.get("par"), **dados}
        pend.meta.update(dados)
        pend.cache.clear()
        estado["A"] = None
        if dono is not None and dono is not self:
            dono._store("save", pend)
            dono.update()
        elif pend in self.annotations:
            self._store("save", pend)

    # ---- ROI de referência (0.99.22, plano AW): as outras ROIs mostram a média em % dela
    def roi_de_referencia(self) -> Annotation | None:
        return next((a for a in self.annotations if (a.meta or {}).get("referencia")), None)

    def marcar_referencia(self, ann: Annotation | None) -> None:
        """Faz de `ann` a ROI de referência da série (None desliga). Só uma por série."""
        for a in self.annotations:
            if (a.meta or {}).get("referencia") and a is not ann:
                a.meta = {k: v for k, v in a.meta.items() if k not in REF_CHAVES}
                self._store("save", a)
        if ann is not None:
            img = self._img
            pix = img.pixels if img is not None and not img.is_color else None
            media = M.media_da_roi(ann, pix, self.measure_spacing(ann)) if ann.frame_key == self.frame_key() else None
            ann.meta = {**(ann.meta or {}), "referencia": True}
            if media is not None:
                ann.meta["ref_media"] = media
            self._store("save", ann)
        self.update()

    def media_de_referencia(self) -> float | None:
        ref = self.roi_de_referencia()
        if ref is None:
            return None
        if ref.frame_key == self.frame_key() and self._img is not None and not self._img.is_color:
            m = M.media_da_roi(ref, self._img.pixels, self.measure_spacing(ref))
            if m is not None:
                if abs(m - float(ref.meta.get("ref_media") or 0)) > 1e-9:
                    ref.meta["ref_media"] = m          # a ROI foi mexida: o número acompanha
                return m
        v = ref.meta.get("ref_media")
        return float(v) if v is not None else None

    def delete_annotation(self, ann: Annotation) -> None:
        if ann in self.annotations:
            self.annotations.remove(ann)
        if self.selected is ann:
            self.selected = None
        if self._draft is ann:
            self._draft = None
        if ann.db_id is not None:
            self._store("delete", ann)
        else:
            self.sig.annotations_changed.emit(self)
        self.update()

    def delete_frame_annotations(self) -> None:
        for a in self.frame_annotations():
            self.delete_annotation(a)

    def delete_series_annotations(self) -> None:
        for a in list(self.annotations):
            self.delete_annotation(a)

    def cancel_draft(self) -> None:
        d = self._draft
        if d is not None:
            self._draft = None
            if d in self.annotations:
                self.annotations.remove(d)
            self.update()

    def escape(self) -> None:
        if self._draft is not None and self._draft.kind == "spine":
            self.finish_draft()
        else:
            self.cancel_draft()
        self.selected = None
        self.update()

    def finish_draft(self) -> bool:
        """Termina polilinha, polígono ou rotulagem da coluna (duplo clique / Enter)."""
        d = self._draft
        if d is None or d.kind not in ("polygon", "polyline", "spine"):
            return False
        pts = d.points if d.kind == "spine" else d.points[:-1]
        clean = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
        need = {"polygon": 3, "polyline": 2, "spine": 1}[d.kind]
        if len(clean) >= need:
            d.points = clean
            self._finish(d)
        else:
            self.cancel_draft()
        return True

    finish_polygon = finish_draft

    def edit_text(self, ann: Annotation) -> None:
        text, ok = QInputDialog.getText(self, "Texto", "Texto da anotação:", text=ann.text)
        if ok:
            ann.text = text.strip()
            if ann.kind == "text" and not ann.text:
                self.delete_annotation(ann)
                return
            self._store("save", ann)
            self.update()

    # ------------------------------------------------------------ navegação pelas medidas
    def annotated_indices(self) -> list[int]:
        keys = {a.frame_key for a in self.annotations if a.done}
        if not keys:
            return []
        out = []
        for i, f in enumerate(self.frames):
            k = ("", f.frame_index) if f.is_virtual else (f.sop_uid, f.frame_index)
            if k in keys:
                out.append(i)
        return out

    def go_to_annotation(self, direction: int) -> bool:
        idx = self.annotated_indices()
        if not idx:
            return False
        if direction > 0:
            nxt = next((i for i in idx if i > self.index), idx[0])
        else:
            nxt = next((i for i in reversed(idx) if i < self.index), idx[-1])
        self.go_to(nxt)
        return True

    def annotation_summary(self) -> list[tuple[int, str]]:
        """(índice da imagem, descrição) de cada medida da série, na ordem das imagens."""
        pos = {}
        for i, f in enumerate(self.frames):
            pos[("", f.frame_index) if f.is_virtual else (f.sop_uid, f.frame_index)] = i
        out = []
        for a in self.annotations:
            if not a.done or a.frame_key not in pos:
                continue
            i = pos[a.frame_key]
            lab = ""
            if a.kind not in M.ROI_KINDS and a.kind != "probe":
                try:
                    lab = " ".join(M.labels(a, None, self.measure_spacing(a), self.modality, getattr(self, "suv_factor", None))[:2])
                except Exception:  # noqa: BLE001
                    lab = ""
            if a.kind in ("text", "arrow") and a.text:
                lab = f"“{a.text}”"
            out.append((i, f"Im {i + 1}: {M.KINDS.get(a.kind, a.kind)}" + (f" — {lab}" if lab else "")))
        return sorted(out)

    def menu_da_escala(self, global_pos) -> None:
        """Clique na linha da escala: dizer de onde ela vem e deixar trocar na hora."""
        menu = QMenu(self)
        img = self._img
        regs = getattr(img, "us_regioes", ()) if img is not None else ()
        if regs:
            menu.addAction(f"Ultrassom: {US.texto(regs)}").setEnabled(False)
        elif img is not None and not img.pixel_spacing:
            menu.addAction("O arquivo não traz o tamanho do pixel").setEnabled(False)
        if img is not None and img.pixel_spacing and not regs:
            rs, cs = img.pixel_spacing
            menu.addAction(f"Arquivo: {cs:.3f} × {rs:.3f} mm/pixel").setEnabled(False)
        menu.addSeparator()
        a = menu.addAction("Calibrar esta imagem…")
        a.triggered.connect(lambda: self.sig.tool_requested.emit("calibration"))
        chave = self.frame_key()
        minha = next((x for x in self._calibracoes() if x.frame_key == chave), None) if chave else None
        da_serie = next((x for x in self._calibracoes()
                         if (x.meta or {}).get("escopo") != "imagem" and x is not minha), None)
        if minha is not None:
            b = menu.addAction("Vale para toda a série"
                               if (minha.meta or {}).get("escopo") == "imagem" else "Vale só para esta imagem")
            b.triggered.connect(lambda: self.trocar_escopo_da_calibracao(minha))
            c = menu.addAction("Apagar a calibração desta imagem")
            c.triggered.connect(lambda: self.delete_annotation(minha))
        if da_serie is not None:
            d = menu.addAction("Apagar a calibração da série")
            d.triggered.connect(lambda: self.delete_annotation(da_serie))
        menu.exec(global_pos)

    def trocar_escopo_da_calibracao(self, ann: Annotation) -> None:
        ann.meta = dict(ann.meta or {})
        ann.meta["escopo"] = "serie" if ann.meta.get("escopo") == "imagem" else "imagem"
        for a in self.annotations:
            a.cache.clear()
        self._store("save", ann)
        self.update()

    def show_annotation_menu(self, global_pos) -> None:
        menu = QMenu(self)
        items = self.annotation_summary()
        if not items:
            menu.addAction("Nenhuma medida nesta série").setEnabled(False)
        for i, text in items[:60]:
            a = menu.addAction(text)
            a.triggered.connect(lambda _=False, k=i: self.go_to(k))
            if i == self.index:
                f = a.font()
                f.setBold(True)
                a.setFont(f)
        menu.exec(global_pos)

    # ------------------------------------------------------------ utilidades
    def _img_pt(self, pos: QPointF) -> tuple[float, float]:
        ip = self.widget_to_image(pos)
        return (ip.x(), ip.y())

    def _img_tol(self, px: float = 6.0) -> float:
        r = self._image_rect()
        w = self._img.pixels.shape[1] if self._img is not None else 1
        scale = r.width() / w if w and r.width() else 1.0
        return px / scale

    def _annotation_at(self, ip: tuple[float, float], tol: float) -> Annotation | None:
        for a in reversed(self.frame_annotations()):
            if a.done and M.hit(a, ip, tol):
                return a
        return None

    def _new_annotation(self, kind: str, pts: list) -> Annotation:
        f = self.current_frame()
        a = Annotation(kind, self.frame_key(), pts, study_uid=self.study_uid,
                       series_uid=(f.series_uid if f is not None and f.series_uid else self.series_uid),
                       done=False)
        self.annotations.append(a)
        return a

    # ------------------------------------------------------------ mouse
    def _draft_click(self, ip: tuple[float, float], tol: float) -> None:
        d = self._draft
        if d.kind == "angle":
            d.points[-1] = ip
            if len(d.points) >= 3:
                self._finish(d)
            else:
                d.points.append(ip)
        elif d.kind in ("polygon", "polyline"):
            fixed = d.points[:-1]
            if d.kind == "polygon" and len(fixed) >= 3 \
                    and math.hypot(ip[0] - fixed[0][0], ip[1] - fixed[0][1]) <= tol * 1.5:
                d.points = fixed
                self._finish(d)
            else:
                d.points[-1] = ip
                d.points.append(ip)
        elif d.kind == "spine":
            d.points.append(ip)
        self.update()

    def _annot_press(self, pos: QPointF) -> None:
        pr = self._press
        ip = self._img_pt(pos)
        tol = self._img_tol()
        d = self._draft
        if d is not None:
            if d.frame_key != self.frame_key():
                self.cancel_draft()
            elif d.kind in TWO_LINE and len(d.points) == 2:
                d.points += [ip, ip]              # começa a segunda reta
                pr["line2"] = d
                return
            elif d.kind in TWO_LINE:
                return
            else:
                self._draft_click(ip, tol)
                pr["draft_click"] = True
                return
        for a in reversed(self.frame_annotations()):   # alça: arrastar edita
            h = M.nearest_handle(a, ip, tol)
            if a.done and h is not None:
                pr["edit"] = (a, h)
                self.selected = a
                self.update()
                return
        hit = self._annotation_at(ip, tol)
        pr["candidate"] = hit
        if hit is not None and hit is self.selected:
            pr["move"], pr["move_last"] = hit, ip      # arrastar a selecionada move-a inteira
            return
        kind = ANNOT_TOOLS[pr.get("tool") or self.left_tool]
        if kind == "pick":
            if hit is not None:
                self.selected = hit
                pr["move"], pr["move_last"] = hit, ip   # já sai arrastando a que acabou de escolher
            else:
                self.selected = None
            self.sig.annotation_picked.emit(self, self.selected)
            self.update()
            return
        if kind == "text":
            pr["text_at"] = ip
            return
        if kind == "spine":
            if hit is not None:
                return
            start, ok = QInputDialog.getItem(self, "Rotular coluna", "Primeira vértebra marcada:",
                                             M.SPINE_LABELS, M.SPINE_LABELS.index(self._spine_start)
                                             if self._spine_start in M.SPINE_LABELS else 19, False)
            self._press = None
            if not ok:
                return
            self._spine_start = start
            a = self._new_annotation("spine", [ip])
            a.text = start
            self._draft = a
            self.update()
            return
        pts = [ip] if kind in ("polygon", "polyline", "pencil", "probe", "ponto3d") else [ip, ip]
        a = self._new_annotation(kind, pts)
        pr["new"] = a
        if kind == "angle" or kind in TWO_LINE:
            self._draft = a

    def _annot_move(self, pos: QPointF) -> bool:
        pr = self._press
        ip = self._img_pt(pos)
        if "edit" in pr:
            a, h = pr["edit"]
            a.points[h] = ip
            a.cache.clear()
        elif "move" in pr:
            last = pr["move_last"]
            M.translate(pr["move"], ip[0] - last[0], ip[1] - last[1])
            pr["move"].cache.clear()
            pr["move_last"] = ip
        elif "line2" in pr:
            pr["line2"].points[-1] = ip
        elif "new" in pr:
            a = pr["new"]
            if a.kind in ("polygon", "polyline", "pencil"):       # desenho livre
                last = a.points[-1]
                if math.hypot(ip[0] - last[0], ip[1] - last[1]) >= self._img_tol(3):
                    a.points.append(ip)
            elif a.kind in ("probe", "ponto3d"):
                a.points[0] = ip
            else:
                a.points[-1] = ip
        elif pr.get("draft_click") and self._draft is not None and self._draft.kind == "angle":
            self._draft.points[-1] = ip
        else:
            return False
        self.update()
        return True

    def _annot_hover(self, pos: QPointF) -> None:
        d = self._draft
        if d is not None and d.kind in RUBBER and d.frame_key == self.frame_key() and self._img is not None:
            d.points[-1] = self._img_pt(pos)
            self.update()

    def _annot_release(self, pos: QPointF, moved: bool) -> None:
        pr = self._press_done
        ip = self._img_pt(pos)
        cand = pr.get("candidate")
        if "edit" in pr or "move" in pr:
            a = pr["edit"][0] if "edit" in pr else pr["move"]
            if moved:
                a.cache.clear()
                self._store("save", a)
        elif "line2" in pr:
            d = pr["line2"]
            if moved:
                self._finish(d)
            else:
                del d.points[2:]                     # clique solto: espera a segunda reta de novo
        elif "text_at" in pr:
            if cand is not None:
                self.selected = cand
            elif not moved:
                text, ok = QInputDialog.getText(self, "Texto", "Texto da anotação:")
                if ok and text.strip():
                    a = self._new_annotation("text", [pr["text_at"]])
                    a.text = text.strip()
                    self._finish(a)
        elif "new" in pr:
            a = pr["new"]
            if not moved:
                if cand is not None:                 # clique sobre uma medida: seleciona
                    self.selected = cand
                    if self._draft is a:
                        self._draft = None
                    self.annotations.remove(a)
                elif a.kind in ("polygon", "polyline"):   # por cliques
                    a.points = [ip, ip]
                    self._draft = a
                elif a.kind in ("probe", "ponto3d"):
                    self._finish(a)
                elif a.kind == "angle":
                    pass                             # continua por cliques
                else:
                    if self._draft is a:
                        self._draft = None
                    self.annotations.remove(a)
            else:
                if a.kind == "angle":
                    a.points.append(ip)              # braço feito; falta o terceiro ponto
                elif a.kind in TWO_LINE:
                    pass                             # 1ª reta feita; falta a segunda
                elif a.kind in ("polygon", "polyline", "pencil"):
                    if len(a.points) >= (3 if a.kind == "polygon" else 2):
                        self._finish(a)
                    else:
                        self.annotations.remove(a)
                else:
                    self._finish(a)
                    self.selected = None
        self.update()

    # ------------------------------------------------------------ desenho
    def _draw_measurements(self, p: QPainter) -> None:
        anns = self.frame_annotations()
        if not self._mostra("medidas"):
            # nível de anotação sem medidas: só a que está selecionada (a que ele está mexendo)
            # aparece, para a ferramenta não ficar desenhando no escuro; a cópia sai limpa
            anns = [] if self._capturando else [a for a in anns if a is self.selected]
        if not anns or self._img is None:
            return
        img = self._img
        pix = None if img.is_color else img.pixels
        spacing_base = self.measure_spacing()
        usa_regiao = bool(getattr(self._img, "us_regioes", ())) and not (
            self.calibracao_da_imagem() or self.calibracao_da_serie())
        font = QFont()
        font.setPointSizeF(max(8.0, min(11.5, self.width() / 50))
                           * self.escala_da_letra("viewer.measure_font_scale"))
        fm = QFontMetrics(font)
        p.setFont(font)
        incerteza = bool(self.settings.get("viewer.incerteza_medidas", False)) if self.settings is not None else False
        try:
            espessura = float((img.header or {}).get("SliceThickness") or 0) or None
        except (TypeError, ValueError):
            espessura = None
        if getattr(self, "mpr_plane", None) is not None:
            espessura = None            # reconstrução: o aviso que vale é o do pixel na direção
        ref_media = self.media_de_referencia()
        for a in anns:
            base = getattr(self, "ann_colors", {}).get(id(a)) or ANNOT_COLORS.get(a.kind, MEASURE_COLOR)
            color = SELECTED_COLOR if a is self.selected else base
            pen = QPen(color)
            pen.setWidth(2)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            pts = [self.image_to_widget(QPointF(*q)) for q in a.points]
            k = a.kind
            anchor = pts[-1] if pts else QPointF()
            if k in ("line", "arrow", "calibration") and len(pts) >= 2:
                p.drawLine(pts[0], pts[1])
                if k == "arrow":
                    self._draw_arrow_head(p, pts[1], pts[0])
                else:
                    for pt in pts[:2]:
                        p.drawEllipse(pt, 3, 3)
                    if k == "calibration":
                        for pt in pts[:2]:          # traços perpendiculares nas pontas
                            d = pts[1] - pts[0]
                            n = math.hypot(d.x(), d.y()) or 1
                            perp = QPointF(-d.y() / n * 7, d.x() / n * 7)
                            p.drawLine(pt - perp, pt + perp)
                anchor = pts[1]
            elif k in ("angle", "polyline", "pencil"):
                if len(pts) >= 2:
                    p.drawPolyline(QPolygonF(pts))
                if k != "pencil":
                    for pt in pts:
                        p.drawEllipse(pt, 3, 3)
                anchor = pts[1] if k == "angle" and len(pts) >= 2 else anchor
            elif k in TWO_LINE:
                for i in range(0, len(pts) - 1, 2):
                    p.drawLine(pts[i], pts[i + 1])
                    for pt in pts[i:i + 2]:
                        p.drawEllipse(pt, 3, 3)
                if k == "cobb" and len(pts) >= 4:
                    self._draw_cobb_perpendiculars(p, pts, color)
                anchor = pts[-1]
            elif k in ("ellipse", "tic") and len(pts) >= 2:
                rect = QRectF(pts[0], pts[1]).normalized()
                p.drawEllipse(rect)
                anchor = rect.topRight()
            elif k == "rect" and len(pts) >= 2:
                rect = QRectF(pts[0], pts[1]).normalized()
                p.drawRect(rect)
                anchor = rect.topRight()
            elif k == "polygon" and pts:
                p.drawPolygon(QPolygonF(pts)) if a.done else p.drawPolyline(QPolygonF(pts))
                anchor = max(pts, key=lambda q: q.x())
            elif k == "height" and len(pts) >= 2:
                a0, a1 = pts[0], pts[1]
                for pt in (a0, a1):
                    p.drawLine(pt - QPointF(14, 0), pt + QPointF(14, 0))
                dash = QPen(color)
                dash.setStyle(Qt.DashLine)
                p.setPen(dash)
                p.drawLine(QPointF(a1.x(), a0.y()), a1)
                p.drawLine(a0, QPointF(a1.x(), a0.y()))
                p.setPen(pen)
                anchor = QPointF(a1.x(), (a0.y() + a1.y()) / 2)
            elif k == "seg" and pts:
                c = pts[0]
                # Com a máscara guardada (0.68) a lesão aparece como foi segmentada; o círculo
                # no ponto do clique ficava no lugar dela ("um círculo pequeno fica no lugar").
                if not (a.meta or {}).get("mascara3d"):
                    p.setBrush(QColor(color.red(), color.green(), color.blue(), 90))
                    p.drawEllipse(c, 6, 6)
                    p.setBrush(Qt.NoBrush)
                anchor = c + QPointF(6, 0)
            elif k in ("probe", "ponto3d") and pts:
                c = pts[0]
                p.drawLine(c - QPointF(8, 0), c - QPointF(2, 0))
                p.drawLine(c + QPointF(2, 0), c + QPointF(8, 0))
                p.drawLine(c - QPointF(0, 8), c - QPointF(0, 2))
                p.drawLine(c + QPointF(0, 2), c + QPointF(0, 8))
                anchor = c + QPointF(4, 0)
            elif k == "spine" and pts:
                for i, pt in enumerate(pts):
                    p.setBrush(color)
                    p.drawEllipse(pt, 4, 4)
                    p.setBrush(Qt.NoBrush)
                    lab = M.spine_label(a.text, i)
                    self._shadow_text(p, pt + QPointF(9, fm.ascent() / 2 - 1), lab, color)
            elif k == "text" and pts:
                anchor = pts[0]
            if a is self.selected and k not in ("polygon", "pencil"):
                p.setPen(QPen(color))
                for pt in pts:
                    p.drawRect(QRectF(pt.x() - 3, pt.y() - 3, 6, 6))
            show = a.done or k in ("seg", "line", "ellipse", "rect", "angle", "cobb", "ctr", "height",
                                   "probe", "polyline", "calibration")
            spacing = self.measure_spacing(a) if usa_regiao else spacing_base
            texts = M.labels(a, pix, spacing, self.modality, getattr(self, "suv_factor", None)) if show and k != "spine" else []
            if texts and a.done:
                texts += M.linhas_extras(a, pix, spacing, incerteza=incerteza, espessura=espessura,
                                         ref_media=ref_media)
            lid = a.meta.get("lesion") if a.meta else None
            if lid is not None and show:
                lname = getattr(self, "lesion_names", {}).get(lid) or a.meta.get("lesion_name") or f"Lesão {lid}"
                texts = [f"◆ {lname}"] + texts
            if not texts:
                continue
            lh = fm.height()
            wmax = max(fm.horizontalAdvance(t) for t in texts)
            x = anchor.x() + 8
            y = anchor.y() - 6 if k != "text" else anchor.y() + fm.ascent() / 2
            if k in ROI_LABEL_LEFT and pts and x + wmax > self.width() - 4:
                x = min(q.x() for q in pts)
                y = max(q.y() for q in pts) + fm.ascent() + 6
                if y + lh * (len(texts) - 1) > self.height() - 4:
                    y = min(q.y() for q in pts) - 6 - lh * (len(texts) - 1)
            x = max(4.0, min(x, self.width() - 4 - wmax))
            y = max(fm.ascent() + 2.0, min(y, self.height() - 4 - lh * (len(texts) - 1)))
            for i, t in enumerate(texts):
                self._shadow_text(p, QPointF(x, y + i * lh), t, color)

    @staticmethod
    def _shadow_text(p: QPainter, org: QPointF, text: str, color: QColor) -> None:
        p.setPen(QColor(0, 0, 0))
        p.drawText(org + QPointF(1, 1), text)
        p.setPen(color)
        p.drawText(org, text)

    @staticmethod
    def _draw_cobb_perpendiculars(p: QPainter, pts: list[QPointF], color: QColor) -> None:
        pen = QPen(color)
        pen.setStyle(Qt.DotLine)
        p.setPen(pen)
        for i in (0, 2):
            a, b = pts[i], pts[i + 1]
            mid = (a + b) / 2
            d = b - a
            n = math.hypot(d.x(), d.y()) or 1
            perp = QPointF(-d.y() / n, d.x() / n) * 60
            p.drawLine(mid - perp, mid + perp)
        p.setPen(QPen(color, 2))

    @staticmethod
    def _draw_arrow_head(p: QPainter, tail: QPointF, tip: QPointF) -> None:
        dx, dy = tip.x() - tail.x(), tip.y() - tail.y()
        n = math.hypot(dx, dy)
        if n < 1:
            return
        ux, uy = dx / n, dy / n
        size = 14.0
        for ang in (0.45, -0.45):
            c, s_ = math.cos(ang), math.sin(ang)
            bx, by = ux * c - uy * s_, ux * s_ + uy * c
            p.drawLine(tip, QPointF(tip.x() - bx * size, tip.y() - by * size))

    # ------------------------------------------------------------ barra de posição
    POSBAR_W = 9

    def posbar_rect(self) -> QRectF:
        top, bottom = 70.0, max(80.0, self.height() - 70.0)
        return QRectF(self.width() - self.POSBAR_W - 3, top, self.POSBAR_W, bottom - top)

    def _draw_posbar(self, p: QPainter) -> None:
        """Barra fina à direita: posição na série, medidas (verde) e imagens-chave (dourado)."""
        n = len(self.frames)
        if n < 2:
            return
        r = self.posbar_rect()
        p.fillRect(r, QColor(255, 255, 255, 45 if self._hover != "posbar" else 80))

        def y_of(i: int) -> float:
            return r.top() + (i + 0.5) / n * r.height()
        keys = self.key_frames
        for i, f in enumerate(self.frames):
            if not f.is_virtual and (f.sop_uid, f.frame_index) in keys:
                p.fillRect(QRectF(r.left(), y_of(i) - 1.5, r.width(), 3), QColor(255, 200, 0))
        for i in self.annotated_indices():
            p.fillRect(QRectF(r.left() + 2, y_of(i) - 1.5, r.width() - 4, 3), QColor(80, 255, 120))
        y = y_of(self.index)
        p.fillRect(QRectF(r.left() - 3, y - 1, r.width() + 6, 2), QColor(255, 255, 255))

    def _posbar_index(self, y: float) -> int:
        r = self.posbar_rect()
        n = len(self.frames)
        return int(min(n - 1, max(0, (y - r.top()) / r.height() * n)))
