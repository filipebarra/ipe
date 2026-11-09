"""0.100.0: no programa ligado ao servidor central, quanto de cada série já chegou.

A tira mostra "34/120 im" com uma barra embaixo da miniatura (e ⬇ na que está chegando agora); o quadro mostra
"⬇ 34/120" ao lado do número da imagem enquanto a série dele não termina. Pôr uma série num quadro passa ela
para a frente da fila do download (`ClientRepository.priorizar`)."""
from __future__ import annotations

import logging
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap

log = logging.getLogger(__name__)

VERDE = QColor(70, 190, 110)
AZUL = QColor(80, 160, 255)


def com_barra(pm: QPixmap, feitas: int, total: int, ativa: bool) -> QPixmap:
    """A miniatura com a barra de quanto já chegou embaixo."""
    out = QPixmap(pm)
    if out.isNull():
        out = QPixmap(80, 80)
        out.fill(QColor(30, 30, 30))
    p = QPainter(out)
    h = max(5, out.height() // 12)
    fundo = QRectF(0, out.height() - h, out.width(), h)
    p.fillRect(fundo, QColor(0, 0, 0, 170))
    frac = 0.0 if total <= 0 else max(0.0, min(1.0, feitas / total))
    p.fillRect(QRectF(0, out.height() - h, out.width() * frac, h), QBrush(AZUL if ativa else VERDE))
    p.end()
    return out


def texto_do_quadro(feitas: int, total: int) -> str:
    return f"⬇ {feitas}/{total}"


class VigiaDownload:
    """De 0,7 em 0,7 s, enquanto o exame da aba chega do servidor: atualiza a tira e os quadros."""

    INTERVALO_MS = 700
    RELER_S = 1.5

    def __init__(self, tab):
        self.tab = tab
        self._mini: dict[str, QPixmap] = {}
        self._antes: dict[str, tuple] = {}
        self._tinha = False
        self._releu = 0.0
        self.timer = QTimer(tab)
        self.timer.setInterval(self.INTERVALO_MS)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def estado(self) -> dict:
        f = getattr(self.tab.repo, "andamento", None)
        if f is None:
            return {}
        series, baixando, fila = {}, set(), []
        for uid in list(getattr(self.tab, "study_order", None) or [self.tab.study_uid]):
            try:
                a = f(uid) or {}
            except Exception:  # noqa: BLE001
                a = {}
            series.update(a.get("series", {}))
            baixando.update(a.get("baixando", []))
            fila += a.get("fila", [])
        return {"series": series, "baixando": baixando, "fila": fila} if series else {}

    def tick(self) -> None:
        try:
            e = self.estado()
            if not e:
                if self._tinha:
                    # terminou: a última leitura do banco e a tira sem as barras
                    self._tinha = False
                    self._antes = {}
                    for vp in self.tab.viewports:
                        vp.baixando_txt = ""
                        vp.update()
                    self.tab.rescan()
                    self.tab._fill_strip()
                return
            self._tinha = True
            mudou = {u: v for u, v in e["series"].items() if self._antes.get(u) != v}
            self._antes = dict(e["series"])
            self.aplicar(e)
            if mudou and time.monotonic() - self._releu >= self.RELER_S:
                self._releu = time.monotonic()
                self.tab.rescan()                        # as imagens novas entram nos quadros abertos
        except Exception:  # noqa: BLE001
            log.exception("andamento do download na aba")

    def aplicar(self, e: dict | None = None) -> None:
        """Põe o andamento na tira e nos quadros (também logo depois de a tira ser refeita)."""
        e = e if e is not None else self.estado()
        if not e:
            return
        rows = {s.series_uid: s for s in self.tab.series}
        strip = self.tab.strip
        for i in range(strip.count()):
            it = strip.item(i)
            uid = it.data(Qt.UserRole)
            if not isinstance(uid, str) or uid not in e["series"] or uid not in rows:
                continue
            feitas, total = e["series"][uid]
            s = rows[uid]
            ativa = uid in e["baixando"]
            fim = feitas >= total
            marca = "  ⬇" if ativa else ("" if fim else "  …")
            it.setText(f"{s.series_number} {s.modality}\n{s.description[:22]}\n{feitas}/{total} im{marca}")
            if fim:
                it.setToolTip("Série baixada do servidor central.")
            elif ativa:
                it.setToolTip(f"Baixando do servidor central: {feitas} de {total} imagens.")
            else:
                pos = e["fila"].index(uid) + 1 if uid in e["fila"] else 0
                it.setToolTip(f"Na fila para baixar ({pos}ª). Ponha num quadro para baixar primeiro."
                              if pos else f"{feitas} de {total} imagens no computador.")
            if uid not in self._mini:
                pm = QPixmap()
                if s.thumbnail:
                    pm.loadFromData(s.thumbnail, "PNG")
                self._mini[uid] = pm
            if not fim:
                it.setIcon(QIcon(com_barra(self._mini[uid], feitas, total, ativa)))
        for vp in self.tab.viewports:
            v = e["series"].get(getattr(vp, "series_uid", "") or "")
            txt = texto_do_quadro(*v) if v and v[0] < v[1] else ""
            if getattr(vp, "baixando_txt", "") != txt:
                vp.baixando_txt = txt
                vp.update()
