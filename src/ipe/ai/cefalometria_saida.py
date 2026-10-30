"""O que a cefalometria deixa no exame (0.99.15): a SEG das estruturas usadas e uma imagem de
conferência — o sagital mediano com as linhas de cada medida, a lista dos números e o perfil da área
da via aérea ao longo do eixo. Séries só locais, como as outras do CAD/IA.

A imagem existe para o médico ver **de onde** cada número saiu: se a linha do plano mandibular caiu
fora do lugar, ele sabe que aquele número não vale e mede à mão.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from ipe.ai import cefalometria as CF

log = logging.getLogger(__name__)

PASSO = 0.5                  # mm por pixel do sagital
CORES = CF.CORES


def sagital_mediano(vol, x: float, meia: float = 1.0) -> tuple[np.ndarray, tuple]:
    """(imagem float H×W em HU, (y0, z_topo)): o plano x = `x` (mm), média de ±`meia` mm.
    Anterior à esquerda, cranial em cima."""
    M = np.asarray(vol.matrix(), float)
    o = np.asarray(vol.origin, float)
    nk, nj, ni = vol.data.shape
    cantos = np.array([[i, j, k] for i in (0, ni - 1) for j in (0, nj - 1) for k in (0, nk - 1)], float)
    P = (o[:, None] + M @ cantos.T).T
    y0, y1, z0, z1 = P[:, 1].min(), P[:, 1].max(), P[:, 2].min(), P[:, 2].max()
    ys = np.arange(y0, y1 + 1e-6, PASSO)
    zs = np.arange(z1, z0 - 1e-6, -PASSO)
    Z, Y = np.meshgrid(zs, ys, indexing="ij")
    Minv = np.linalg.inv(M)
    soma = np.zeros(Z.shape)
    n = np.zeros(Z.shape)
    for dx in np.arange(-meia, meia + 1e-6, max(float(vol.dx), 0.5)):
        Q = np.stack([np.full(Z.shape, x + dx), Y, Z], -1).reshape(-1, 3)
        ijk = np.rint((Q - o) @ Minv.T).astype(int)
        ok = (ijk[:, 0] >= 0) & (ijk[:, 0] < ni) & (ijk[:, 1] >= 0) & (ijk[:, 1] < nj) & \
             (ijk[:, 2] >= 0) & (ijk[:, 2] < nk)
        v = np.zeros(len(Q))
        q = ijk[ok]
        v[ok] = vol.data[q[:, 2], q[:, 1], q[:, 0]]
        soma += v.reshape(Z.shape)
        n += ok.reshape(Z.shape)
    img = np.where(n > 0, soma / np.maximum(n, 1), -1000.0)
    return img, (float(y0), float(z1))


def desenhar(vol, res: CF.Cefalometria, cab: dict, settings=None) -> np.ndarray:
    """RGB uint8: sagital com as linhas | lista das medidas e o perfil da área."""
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

    img, (y0, ztopo) = sagital_mediano(vol, res.x_meio or 0.0)
    lo, hi = -600.0, 1200.0                                   # ar, partes moles e osso juntos
    cinza = (np.clip((img - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)
    h_s, w_s = cinza.shape
    escala = max(1.0, 700.0 / h_s)
    H = max(760, int(h_s * escala) + 60)
    LARG_TXT = 620
    W = int(w_s * escala) + LARG_TXT + 40
    qi = QImage(W, H, QImage.Format_RGB888)
    qi.fill(QColor(16, 16, 16))
    p = QPainter(qi)
    p.setRenderHint(QPainter.Antialiasing)
    sag = QImage(np.ascontiguousarray(np.repeat(cinza[..., None], 3, axis=2)).data, w_s, h_s, 3 * w_s,
                 QImage.Format_RGB888)
    p.drawImage(QRectF(20, 40, w_s * escala, h_s * escala), sag)

    def tela(pt):
        return QPointF(20 + (pt[1] - y0) / PASSO * escala, 40 + (ztopo - pt[2]) / PASSO * escala)

    def fonte(px, negrito=False):
        f = QFont("Arial")
        f.setPixelSize(px)
        f.setBold(negrito)
        return f
    for k, m in res.medidas.items():
        if not m.linhas:
            continue
        cor = QColor(*CORES.get(k, (255, 255, 255)))
        p.setPen(QPen(cor, 2))
        for a, b in m.linhas:
            p.drawLine(tela(a), tela(b))
        a = m.linhas[-1][1]
        p.setFont(fonte(14, True))
        p.drawText(tela(a) + QPointF(4, -4), CF.NUMERO[k] or "A")
    p.setPen(QColor(235, 235, 235))
    p.setFont(fonte(16, True))
    p.drawText(QRectF(20, 8, W - 40, 26), Qt.AlignLeft | Qt.AlignVCenter,
               f"Cefalometria (automática — conferir) · {cab.get('paciente', '')} · {cab.get('data', '')}")
    x0 = 40 + w_s * escala
    y = 48
    refs = CF.referencias(settings)
    for k in CF.ORDEM:
        m = res.medidas[k]
        cor = QColor(*CORES.get(k, (255, 255, 255)))
        p.setPen(cor)
        p.setFont(fonte(15, True))
        p.drawText(QRectF(x0, y, 30, 22), Qt.AlignLeft | Qt.AlignVCenter, CF.NUMERO[k] or "A")
        p.setPen(QColor(230, 230, 230))
        p.drawText(QRectF(x0 + 28, y, LARG_TXT - 40, 22), Qt.AlignLeft | Qt.AlignVCenter, m.nome)
        y += 22
        if m.valor is not None or (m.texto and not m.motivo):
            v = m.texto_valor() + (f" — {m.texto}" if m.valor is not None and m.texto else "")
            if k == "area" and m.valor is not None:
                v += f" — {CF.classe_da_area(m.valor)}"
            ref = refs.get(k, "")
            p.setFont(fonte(14))
            p.drawText(QRectF(x0 + 28, y, LARG_TXT - 40, 20), Qt.AlignLeft | Qt.AlignVCenter,
                       v + (f"   ({ref})" if ref and k != "area" else ""))
        else:
            p.setPen(QColor(240, 170, 90))
            p.setFont(fonte(14))
            p.drawText(QRectF(x0 + 28, y, LARG_TXT - 40, 20), Qt.AlignLeft | Qt.AlignVCenter,
                       f"não medido: {m.motivo or 'sem dados'}")
        y += 28
    # perfil da área ao longo do eixo
    if res.perfil:
        caixa = QRectF(x0 + 28, y + 16, LARG_TXT - 60, max(160, H - y - 70))
        p.setPen(QColor(120, 120, 120))
        p.drawRect(caixa)
        zs = np.array([z for z, _a in res.perfil])
        ar = np.array([a for _z, a in res.perfil])
        amax = max(150.0, float(ar.max()) * 1.05)
        zmin, zmax = float(zs.min()), float(zs.max())

        def ponto(z, a):
            return QPointF(caixa.left() + a / amax * caixa.width(),
                           caixa.top() + (zmax - z) / max(zmax - zmin, 1e-6) * caixa.height())
        for lim in CF.FAIXAS_AREA:
            if lim < amax:
                p.setPen(QPen(QColor(110, 110, 110), 1, Qt.DashLine))
                p.drawLine(ponto(zmax, lim), ponto(zmin, lim))
        p.setPen(QPen(QColor(*CORES["area"]), 2))
        for (za, aa), (zb, ab) in zip(res.perfil, res.perfil[1:]):
            p.drawLine(ponto(za, aa), ponto(zb, ab))
        p.setPen(QColor(200, 200, 200))
        p.setFont(fonte(13))
        p.drawText(QRectF(caixa.left(), caixa.top() - 18, caixa.width(), 16), Qt.AlignLeft,
                   "Área perpendicular ao eixo (mm²), de cima para baixo · tracejado: 50 e 100 mm²")
    p.setPen(QColor(150, 150, 150))
    p.setFont(fonte(12))
    p.drawText(QRectF(20, H - 24, W - 40, 20), Qt.AlignLeft | Qt.AlignVCenter,
               f"Série: {cab.get('serie', '')} · TotalSegmentator (tarefas abertas) · Ipê — não destinado a uso "
               "diagnóstico")
    p.end()
    buf = qi.constBits()
    arr = np.frombuffer(buf, np.uint8, count=qi.sizeInBytes()).reshape(H, qi.bytesPerLine())
    return arr[:, : W * 3].reshape(H, W, 3).copy()


def gravar(trabalho, res: CF.Cefalometria, versao: str, db, storage_root, repo=None, settings=None) -> dict:
    """SEG das estruturas + imagem de conferência no exame; as anteriores da cefalometria saem."""
    from ipe.ai import totalseg as TS
    from ipe.ai.totalseg_saida import _caminho_do_sop, cabecalho
    from ipe.imaging.derived import save_secondary_capture
    from ipe.imaging.seg_writer import build_seg
    from ipe.importer.scanner import Importer
    if repo is not None:
        for se in repo.series_for_study(trabalho.study_uid):
            if (se.description or "") in (CF.DESC_SEG, CF.DESC_IMAGEM):
                try:
                    repo.delete_series(se.series_uid, Path(storage_root))
                except Exception:  # noqa: BLE001
                    log.exception("trocar a cefalometria anterior")
    vol = trabalho.vol
    segs = []
    for nome, (m, off) in res.estruturas.items():
        if nome.startswith("vertebrae_"):
            segs.append((SimpleNamespace(mask=m, offset=off), nome.split("_", 1)[1], (120, 200, 255)))
        elif nome in CF.ESTRUTURAS:
            _t, rotulo, cor = CF.ESTRUTURAS[nome]
            segs.append((SimpleNamespace(mask=m, offset=off), rotulo, cor))
    if not segs:
        raise TS.Falhou("O TotalSegmentator não achou as estruturas da cefalometria nesta série.")
    out = {"series": []}
    ds = build_seg(vol, segs, vol.source_path, frames=trabalho.frames, series_number=CF.SERIE_SEG,
                   description=CF.DESC_SEG, algoritmo=("AUTOMATIC", f"TotalSegmentator {versao}".strip()),
                   anatomia=True)
    tmp = Path(tempfile.mkdtemp(prefix="dv_cefalo_"))
    try:
        ds.save_as(tmp / "seg.dcm", enforce_file_format=True)
        r = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([tmp])
        out["series"] += sorted(getattr(r, "new_series", None) or [])
        out["seg_sop"] = str(ds.SOPInstanceUID)
        out["seg_path"] = _caminho_do_sop(db, trabalho.study_uid, out["seg_sop"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rgb = desenhar(vol, res, cabecalho(trabalho), settings)
    uid, _s = save_secondary_capture(rgb, vol.source_path, db, storage_root, description=CF.DESC_IMAGEM,
                                     series_number=CF.SERIE_IMAGEM,
                                     extra={"BurnedInAnnotation": "YES",
                                            "ImageComments": "Cefalometria automática — conferência"},
                                     privado={(CF.GRUPO_PRIVADO, CF.CRIADOR): {0x01: ("UT", CF.para_json(res))}})
    out["series"].append(uid)
    return out
