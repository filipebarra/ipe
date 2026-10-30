"""Modelos de folha: logo, nome da clínica, cabeçalho e rodapé nas folhas impressas.

Serve tanto para o que chega das modalidades quanto para o que sai daqui. Dois modos:
respeitar a folha como veio (só põe a moldura em volta) ou **remontar** com a nossa grade,
usando as imagens soltas de cada caixa.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ipe.printing import jobs as J

log = logging.getLogger(__name__)

NOT_FOR_DIAGNOSIS = "Não destinado a uso diagnóstico"


@dataclass
class SheetTemplate:
    """Como a folha é desenhada: cabeçalho com logo e nome, rodapé, margens e grade."""
    name: str = "Modelo"
    clinic: str = ""
    subtitle: str = ""                  # endereço, telefone, uma linha
    logo: str = ""                      # caminho de uma imagem (PNG/JPG)
    show_patient: bool = True
    show_date: bool = True
    show_source: bool = True            # de qual aparelho veio
    footer: str = ""
    dark: bool = True                   # fundo preto (filme) ou branco (papel)
    margin_mm: float = 6.0
    header_mm: float = 15.0
    footer_mm: float = 6.0
    remount: bool = False               # remontar com a nossa grade
    rows: int = 0                       # 0 = a grade que veio
    cols: int = 0
    gap_mm: float = 1.5

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in SheetTemplate.__dataclass_fields__}

    @staticmethod
    def from_dict(d: dict) -> "SheetTemplate":
        known = SheetTemplate.__dataclass_fields__
        return SheetTemplate(**{k: v for k, v in (d or {}).items() if k in known})

    def label(self) -> str:
        como = "remontando a grade" if self.remount else "como veio"
        return f"{self.name}: clínica {self.clinic or 'sem nome'}, {como}"


def all_templates(settings) -> list[SheetTemplate]:
    return [SheetTemplate.from_dict(d) for d in (settings.get("printing.templates", []) or [])]


def save_templates(settings, modelos: list[SheetTemplate]) -> None:
    settings.set("printing.templates", [m.to_dict() for m in modelos])
    settings.save()


def find_template(settings, nome: str) -> SheetTemplate | None:
    if not nome:
        return None
    for m in all_templates(settings):
        if m.name == nome:
            return m
    return None


# ---------------------------------------------------------------------------
# desenho
# ---------------------------------------------------------------------------

def _qimage(px) -> "object":
    from PySide6.QtGui import QImage
    if px.ndim == 3:
        h, w, _ = px.shape
        img = QImage(px.tobytes(), w, h, 3 * w, QImage.Format_RGB888)
    else:
        h, w = px.shape
        img = QImage(px.tobytes(), w, h, w, QImage.Format_Grayscale8)
    return img.copy()


def render(images: list, rects: list[tuple[float, float, float, float]], meta: dict,
           template: SheetTemplate, mm: tuple[float, float], sheet_no: int = 1, total: int = 1,
           dpi: int = 150):
    """Desenha uma folha: moldura do modelo + as imagens nos seus lugares (frações da área)."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter

    mm_w, mm_h = mm
    escala = max(50, int(dpi)) / 25.4
    w, h = max(200, int(mm_w * escala)), max(200, int(mm_h * escala))
    fundo = QColor(0, 0, 0) if template.dark else QColor(255, 255, 255)
    frente = QColor(240, 240, 240) if template.dark else QColor(20, 20, 20)
    fraco = QColor(160, 160, 160) if template.dark else QColor(110, 110, 110)
    folha = QImage(w, h, QImage.Format_RGB32)
    folha.fill(fundo)
    p = QPainter(folha)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    try:
        m = template.margin_mm * escala
        cab_h = template.header_mm * escala if _tem_cabecalho(template) else 0.0
        rod_h = template.footer_mm * escala if template.footer or total > 1 else 0.0
        _cabecalho(p, template, meta, QRectF(m, m, w - 2 * m, cab_h), frente, fraco, escala)
        area = QRectF(m, m + cab_h, w - 2 * m, h - 2 * m - cab_h - rod_h)
        vao = template.gap_mm * escala
        for img, (x0, y0, cw, ch) in zip(images, rects):
            if img is None:
                continue
            celula = QRectF(area.x() + x0 * area.width() + vao / 2, area.y() + y0 * area.height() + vao / 2,
                            cw * area.width() - vao, ch * area.height() - vao)
            k = min(celula.width() / img.width(), celula.height() / img.height())
            iw, ih = img.width() * k, img.height() * k
            p.drawImage(QRectF(celula.x() + (celula.width() - iw) / 2,
                               celula.y() + (celula.height() - ih) / 2, iw, ih), img)
        if rod_h:
            fonte = QFont()
            fonte.setPixelSize(max(8, int(3.0 * escala)))
            p.setFont(fonte)
            p.setPen(fraco)
            rod = QRectF(m, h - m - rod_h, w - 2 * m, rod_h)
            p.drawText(rod, Qt.AlignLeft | Qt.AlignVCenter, template.footer or NOT_FOR_DIAGNOSIS)
            if total > 1:
                p.drawText(rod, Qt.AlignRight | Qt.AlignVCenter, f"Folha {sheet_no} de {total}")
            _ = QFontMetrics(fonte)
    finally:
        p.end()
    folha.setDotsPerMeterX(round(dpi / 0.0254))
    folha.setDotsPerMeterY(round(dpi / 0.0254))
    return folha


def _tem_cabecalho(t: SheetTemplate) -> bool:
    return bool(t.clinic or t.logo or t.subtitle or t.show_patient or t.show_date or t.show_source)


def _cabecalho(p, t: SheetTemplate, meta: dict, rect, frente, fraco, escala) -> None:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QFont, QFontMetrics, QImage

    if rect.height() <= 1:
        return
    x = rect.x()
    if t.logo and Path(t.logo).exists():
        logo = QImage(t.logo)
        if not logo.isNull():
            alt = rect.height() * 0.9
            larg = alt * logo.width() / max(1, logo.height())
            larg = min(larg, rect.width() * 0.3)
            p.drawImage(QRectF(x, rect.y() + (rect.height() - alt) / 2, larg, alt), logo)
            x += larg + 3 * escala
    nome = QFont()
    nome.setPixelSize(max(10, int(4.2 * escala)))
    nome.setBold(True)
    pequena = QFont()
    pequena.setPixelSize(max(8, int(3.0 * escala)))
    y = rect.y()
    if t.clinic:
        p.setFont(nome)
        p.setPen(frente)
        fm = QFontMetrics(nome)
        p.drawText(QRectF(x, y, rect.width() * 0.55, fm.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(t.clinic, Qt.ElideRight, int(rect.width() * 0.55)))
        y += fm.height()
    if t.subtitle:
        p.setFont(pequena)
        p.setPen(fraco)
        fm = QFontMetrics(pequena)
        p.drawText(QRectF(x, y, rect.width() * 0.55, fm.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(t.subtitle, Qt.ElideRight, int(rect.width() * 0.55)))
    direita = []
    if t.show_patient:
        quem = meta.get("patient") or "(sem identificação)"
        ident = meta.get("id") or ""
        direita.append(f"{quem}   ID {ident}" if ident else quem)
    if t.show_date:
        quando = meta.get("when") or datetime.now()
        direita.append(quando.strftime("%d/%m/%Y %H:%M"))
    if t.show_source and meta.get("source"):
        direita.append(str(meta["source"]))
    p.setFont(pequena)
    fm = QFontMetrics(pequena)
    for i, texto in enumerate(direita[:3]):
        p.setPen(frente if i == 0 else fraco)
        p.drawText(QRectF(rect.x() + rect.width() * 0.45, rect.y() + i * fm.height(),
                          rect.width() * 0.55, fm.height()), Qt.AlignRight | Qt.AlignVCenter,
                   fm.elidedText(texto, Qt.ElideLeft, int(rect.width() * 0.55)))


def render_job_sheet(job, folder, index: int, template: SheetTemplate, dpi: int = 150):
    """Uma folha do trabalho, com o modelo aplicado."""
    film = job.films[index]
    meta = {"patient": job.patient_name, "id": job.patient_id, "when": job.when(),
            "source": job.calling_ae, "film": film.film_size}
    mm = J.sheet_mm(film)
    if template.remount:
        caixas = film.filled()
        linhas, colunas = (template.rows, template.cols) if template.rows and template.cols else (0, 0)
        if linhas and colunas:
            fmt = f"STANDARD\\{colunas},{linhas}"
        else:
            fmt = film.display_format
        rects = J.cell_rects(fmt, len(caixas))
        imagens, lugares = [], []
        for i, box in enumerate(caixas):
            px = J.box_pixels(folder, box)
            if px is None:
                continue
            pos = int(box.position or (i + 1)) - 1
            if not 0 <= pos < len(rects):
                pos = min(i, len(rects) - 1)
            imagens.append(_qimage(px))
            lugares.append(rects[pos])
        return render(imagens, lugares, meta, template, mm, index + 1, len(job.films), dpi)
    pronta = _qimage(J.compose_sheet(folder, film, width=max(400, int(mm[0] / 25.4 * dpi))))
    return render([pronta], [(0.0, 0.0, 1.0, 1.0)], meta, template, mm, index + 1, len(job.films), dpi)


def preview(template: SheetTemplate, dpi: int = 60):
    """Prévia do modelo com quadrados cinza no lugar das imagens (para o editor)."""
    import numpy as np

    linhas = template.rows or 2
    colunas = template.cols or 2
    if not template.remount:
        linhas = colunas = 1
    imagens, rects = [], J.cell_rects(f"STANDARD\\{colunas},{linhas}", linhas * colunas)
    for i in range(linhas * colunas):
        tom = 60 + (i * 40) % 160
        a = np.full((120, 100), tom, dtype=np.uint8)
        a[10:30, 10:70] = 235
        imagens.append(_qimage(a))
    meta = {"patient": "MARIA SOUZA", "id": "44821", "when": datetime.now(), "source": "MG_SALA1"}
    return render(imagens, rects, meta, template, (210.0, 297.0), 1, 2, dpi)
