"""Desenho das folhas do filme: o mesmo código serve para a tela, a impressora, o PDF,
as imagens e a impressora DICOM (a folha vira uma imagem na resolução pedida)."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter

from ipe.imaging.series import build_frames
from ipe.printing.film import Film, Sheet

PX_PER_MM = 96 / 25.4           # unidade "lógica" das folhas (igual à tela em 96 dpi)
FOOTER_NOTE = "Ipê — não destinado a uso diagnóstico"


class FrameSource:
    """Busca (e guarda) os quadros das séries e os dados dos estudos usados no filme."""

    def __init__(self, repo):
        from ipe.ui.viewer.viewer_tab import RepoAnnotationStore
        self.repo = repo
        self.store = RepoAnnotationStore(repo)
        self._frames: dict[str, list] = {}
        self._info: dict[str, dict] = {}

    def frames(self, series_uid: str) -> list:
        if series_uid not in self._frames:
            try:
                self._frames[series_uid] = build_frames(self.repo.instances_for_series(series_uid), series_uid)
            except Exception:  # noqa: BLE001
                self._frames[series_uid] = []
        return self._frames[series_uid]

    def study_info(self, study_uid: str) -> dict:
        if study_uid not in self._info:
            self._info[study_uid] = self.repo.study_info(study_uid) or {}
        return self._info[study_uid]

    def clear(self) -> None:
        self._frames.clear()
        self._info.clear()


def page_size_px(sheet: Sheet) -> QSizeF:
    w, h = sheet.page_mm()
    return QSizeF(w * PX_PER_MM, h * PX_PER_MM)


def sheet_geometry(film: Film, sheet: Sheet, size: QSizeF) -> tuple[QRectF, QRectF, list[QRectF]]:
    """(cabeçalho, rodapé, retângulos das células) em unidades lógicas da folha."""
    m = film.margin_mm * PX_PER_MM
    gap = film.gap_mm * PX_PER_MM
    head_h = 11 * PX_PER_MM if film.header else 0
    foot_h = 5 * PX_PER_MM if film.header else 0
    header = QRectF(m, m, size.width() - 2 * m, head_h)
    footer = QRectF(m, size.height() - m - foot_h, size.width() - 2 * m, foot_h)
    area = QRectF(m, m + head_h, size.width() - 2 * m, size.height() - 2 * m - head_h - foot_h)
    cw = (area.width() - gap * (sheet.cols - 1)) / sheet.cols
    ch = (area.height() - gap * (sheet.rows - 1)) / sheet.rows
    rects = [QRectF(area.x() + c * (cw + gap), area.y() + r * (ch + gap), cw, ch)
             for r in range(sheet.rows) for c in range(sheet.cols)]
    return header, footer, rects


def header_lines(film: Film, sheet: Sheet, src: FrameSource) -> tuple[list[str], list[str]]:
    uids: list[str] = []
    for c in sheet.cells:
        if c is not None and c.study_uid not in uids:
            uids.append(c.study_uid)
    if not uids:
        return [film.name], []
    infos = [src.study_info(u) for u in uids]
    si = infos[0]
    if film.anonymize:
        left = ["Paciente oculto", film.name]
    else:
        b = si.get("birth_date", "")
        birth = f"nasc. {b[6:8]}/{b[4:6]}/{b[:4]}" if len(b) == 8 else ""
        pac = getattr(film, "paciente", None) or {}
        if pac.get("patient_name") and pac.get("id_source") != "aguardando":
            # paciente confirmado (OCR ou à mão) manda sobre o nome que veio nas imagens
            left = [pac["patient_name"].replace("^", " "),
                    f"ID {pac.get('patient_id', '')}" if pac.get("patient_id") else ""]
        else:
            left = [si.get("patient_name", "") or "(sem nome)",
                    "  ·  ".join(x for x in (f"ID {si.get('patient_id', '')}", si.get("sex", ""),
                                             si.get("patient_age", ""), birth) if x.strip())]
    right = []
    for info in infos[:2]:
        d = info.get("study_date", "")
        dt = f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 else d
        right.append("  ·  ".join(x for x in (info.get("description", ""), "" if film.anonymize else dt,
                                              info.get("accession", "") and not film.anonymize
                                              and f"Acc {info.get('accession')}" or "") if x))
    if len(infos) > 2:
        right.append(f"+ {len(infos) - 2} exame(s)")
    if not film.anonymize and si.get("institution"):
        right.append(si["institution"])
    return left, right


def paint_page_decor(p: QPainter, film: Film, sheet: Sheet, sheet_no: int, total: int, src: FrameSource,
                     size: QSizeF, printed: datetime | None = None) -> None:
    """Fundo, cabeçalho e rodapé (em unidades lógicas)."""
    bg = QColor(0, 0, 0) if film.black_page else QColor(255, 255, 255)
    fg = QColor(235, 235, 235) if film.black_page else QColor(20, 20, 20)
    dim = QColor(150, 150, 150) if film.black_page else QColor(100, 100, 100)
    p.fillRect(QRectF(0, 0, size.width(), size.height()), bg)
    if not film.header:
        return
    header, footer, _r = sheet_geometry(film, sheet, size)
    left, right = header_lines(film, sheet, src)
    big = QFont()
    big.setPixelSize(int(4.2 * PX_PER_MM))
    big.setBold(True)
    small = QFont()
    small.setPixelSize(int(3.0 * PX_PER_MM))
    y = header.y()
    for i, t in enumerate(left[:2]):
        f = big if i == 0 else small
        p.setFont(f)
        p.setPen(fg if i == 0 else dim)
        fm = QFontMetrics(f)
        p.drawText(QRectF(header.x(), y, header.width() * 0.55, fm.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(t, Qt.ElideRight, int(header.width() * 0.55)))
        y += fm.height()
    p.setFont(small)
    fm = QFontMetrics(small)
    for i, t in enumerate(right[:3]):
        p.setPen(fg if i == 0 else dim)
        p.drawText(QRectF(header.x() + header.width() * 0.4, header.y() + i * fm.height(),
                          header.width() * 0.6, fm.height()), Qt.AlignRight | Qt.AlignVCenter,
                   fm.elidedText(t, Qt.ElideLeft, int(header.width() * 0.6)))
    tiny = QFont()
    tiny.setPixelSize(int(2.5 * PX_PER_MM))
    p.setFont(tiny)
    p.setPen(dim)
    when = (printed or datetime.now()).strftime("%d/%m/%Y %H:%M")
    p.drawText(footer, Qt.AlignLeft | Qt.AlignVCenter, FOOTER_NOTE)
    p.drawText(footer, Qt.AlignHCenter | Qt.AlignVCenter, film.name)
    p.drawText(footer, Qt.AlignRight | Qt.AlignVCenter, f"Folha {sheet_no}/{total}  ·  {when}")


def paint_sheet(p: QPainter, film: Film, sheet_index: int, src: FrameSource, cache, settings) -> None:
    """Desenha a folha inteira em unidades lógicas (o chamador escala o pintor)."""
    from ipe.ui.film.cell import FilmCell
    sheet = film.sheets[sheet_index]
    size = page_size_px(sheet)
    paint_page_decor(p, film, sheet, sheet_index + 1, len(film.sheets), src, size)
    _h, _f, rects = sheet_geometry(film, sheet, size)
    cellw = FilmCell(cache, settings)
    cellw.interactive = False
    cellw.overlay, cellw.ruler, cellw.anonymize = film.overlay, film.ruler, film.anonymize
    cellw.show_notes = film.notes_visible
    try:
        for cell, rect in zip(sheet.cells, rects):
            if cell is None:
                if not film.black_page:
                    p.fillRect(rect, QColor(0, 0, 0))
                continue
            cellw.resize(max(1, int(rect.width())), max(1, int(rect.height())))
            cellw.load(cell, src.frames(cell.series_uid), src.study_info(cell.study_uid), src.store)
            cellw.paint_to(p, rect)
    finally:
        cellw.deleteLater()


def render_sheet_image(film: Film, sheet_index: int, src: FrameSource, cache, settings, dpi: float = 150,
                       grayscale: bool = False) -> QImage:
    """A folha como imagem na resolução pedida (pontos por polegada)."""
    sheet = film.sheets[sheet_index]
    size = page_size_px(sheet)
    k = dpi / 96.0
    img = QImage(max(1, round(size.width() * k)), max(1, round(size.height() * k)), QImage.Format_RGB32)
    img.setDotsPerMeterX(round(96 / 0.0254))       # fontes em pontos resolvidas como na tela
    img.setDotsPerMeterY(round(96 / 0.0254))
    img.fill(QColor(255, 255, 255))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    p.scale(k, k)
    paint_sheet(p, film, sheet_index, src, cache, settings)
    p.end()
    img.setDotsPerMeterX(round(dpi / 0.0254))
    img.setDotsPerMeterY(round(dpi / 0.0254))
    if grayscale:
        img = img.convertToFormat(QImage.Format_Grayscale8)
    return img
