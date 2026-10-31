"""O que os índices do crânio deixam no exame (0.99.17): a SEG das estruturas (ventrículos,
hipocampos, amígdalas, tronco) e uma imagem de conferência — o axial dos cornos frontais com as
linhas do Evans e do 3º ventrículo, o coronal da comissura posterior com o ângulo calosal, e a lista
dos números. Os números e as linhas vão também num bloco privado da imagem, para reabrir sem refazer.
Séries só locais, como as outras do CAD/IA."""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from ipe.ai import neuro as N

log = logging.getLogger(__name__)

PASSO = 0.5


def corte(vol, centro, u, v, meia_u: float, meia_v: float, passo: float = PASSO) -> np.ndarray:
    """Imagem do plano por `centro` com eixos `u` (colunas) e `v` (linhas), vizinho mais próximo."""
    M = np.asarray(vol.matrix(), float)
    o = np.asarray(vol.origin, float)
    us = np.arange(-meia_u, meia_u + 1e-6, passo)
    vs = np.arange(-meia_v, meia_v + 1e-6, passo)
    V, U = np.meshgrid(vs, us, indexing="ij")
    P = np.asarray(centro, float) + U[..., None] * np.asarray(u, float) + V[..., None] * np.asarray(v, float)
    ijk = np.rint((P.reshape(-1, 3) - o) @ np.linalg.inv(M).T).astype(int)
    nk, nj, ni = vol.data.shape
    ok = (ijk[:, 0] >= 0) & (ijk[:, 0] < ni) & (ijk[:, 1] >= 0) & (ijk[:, 1] < nj) & (ijk[:, 2] >= 0) & \
         (ijk[:, 2] < nk)
    out = np.full(len(ijk), np.nan)
    q = ijk[ok]
    out[ok] = vol.data[q[:, 2], q[:, 1], q[:, 0]]
    return out.reshape(V.shape)


def _cinza(img: np.ndarray, ct: bool) -> np.ndarray:
    if ct:
        lo, hi = 0.0, 80.0                                    # janela de encéfalo
    else:
        val = img[np.isfinite(img)]
        lo, hi = (np.percentile(val, (1, 99.5)) if len(val) else (0.0, 1.0))
    g = np.clip((np.nan_to_num(img, nan=lo) - lo) / max(hi - lo, 1e-6), 0, 1)
    return (g * 255).astype(np.uint8)


def desenhar(vol, res, cab: dict, settings=None) -> np.ndarray:
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

    ct = (res.modalidade or "").upper() == "CT"
    m = res.medidas
    xm = res.x_meio or 0.0
    # centros dos dois cortes: o axial dos cornos e o coronal do ângulo calosal (ou o meio do volume)
    meio_vol = np.asarray(vol.voxel_to_patient(vol.shape[2] / 2, vol.shape[1] / 2, vol.shape[0] / 2), float)
    z_ax = float(m["cornos"].linhas[0][0][2]) if m["cornos"].linhas else float(meio_vol[2])
    y_co = float(m["calosal"].linhas[0][0][1]) if m["calosal"].linhas else float(meio_vol[1])
    c_ax = np.array([xm, meio_vol[1], z_ax])
    c_co = np.array([xm, y_co, meio_vol[2]])
    R = 90.0
    ax = corte(vol, c_ax, (1, 0, 0), (0, 1, 0), R, R)          # colunas +x (esquerda do paciente à direita)
    co = corte(vol, c_co, (1, 0, 0), (0, 0, -1), R, R)         # linhas para baixo
    imgs = [(_cinza(ax, ct), c_ax, (1, 0, 0), (0, 1, 0), "Axial dos cornos frontais"),
            (_cinza(co, ct), c_co, (1, 0, 0), (0, 0, -1), "Coronal da comissura posterior")]
    lado = 380
    LARG_TXT = 560
    W = 20 + 2 * (lado + 20) + LARG_TXT
    H = 40 + lado + 60
    qi = QImage(W, max(H, 520), QImage.Format_RGB888)
    H = qi.height()
    qi.fill(QColor(16, 16, 16))
    p = QPainter(qi)
    p.setRenderHint(QPainter.Antialiasing)

    def fonte(px, negrito=False):
        f = QFont("Arial")
        f.setPixelSize(px)
        f.setBold(negrito)
        return f
    for n, (g, centro, u, v, titulo) in enumerate(imgs):
        x0 = 20 + n * (lado + 20)
        h, w = g.shape
        q = QImage(np.ascontiguousarray(np.repeat(g[..., None], 3, axis=2)).data, w, h, 3 * w, QImage.Format_RGB888)
        p.drawImage(QRectF(x0, 40, lado, lado), q)
        esc = lado / w

        def tela(pt, centro=centro, u=u, v=v, x0=x0, esc=esc):
            d = np.asarray(pt, float) - centro
            return QPointF(x0 + (float(d @ np.asarray(u, float)) + R) / PASSO * esc,
                           40 + (float(d @ np.asarray(v, float)) + R) / PASSO * esc)
        normal = np.cross(np.asarray(u, float), np.asarray(v, float))
        for k, med in m.items():
            for a, b in med.linhas:
                if abs(float((np.asarray(a) - centro) @ normal)) > 1.5 or abs(float((np.asarray(b) - centro) @ normal)) > 1.5:
                    continue
                p.setPen(QPen(QColor(*N.CORES.get(k, (255, 255, 255))), 2))
                p.drawLine(tela(a), tela(b))
        p.setPen(QColor(220, 220, 220))
        p.setFont(fonte(13, True))
        p.drawText(QRectF(x0, 40 + lado + 4, lado, 18), Qt.AlignLeft, titulo)
        p.setFont(fonte(12))
        p.drawText(QRectF(x0, 40 + lado + 4, lado, 18), Qt.AlignRight, "D ←  → E")
    p.setPen(QColor(235, 235, 235))
    p.setFont(fonte(16, True))
    p.drawText(QRectF(20, 8, W - 40, 26), Qt.AlignLeft | Qt.AlignVCenter,
               f"Índices do crânio (automático — conferir) · {cab.get('paciente', '')} · {cab.get('data', '')}")
    x0 = 20 + 2 * (lado + 20)
    y = 44
    refs = N.referencias(settings)
    for k in N.ORDEM:
        med = m[k]
        p.setPen(QColor(*N.CORES.get(k, (200, 200, 200))))
        p.setFont(fonte(14, True))
        p.drawText(QRectF(x0, y, 24, 20), Qt.AlignLeft | Qt.AlignVCenter, N.NUMERO.get(k, ""))
        p.setPen(QColor(230, 230, 230))
        p.setFont(fonte(13))
        if med.valor is not None:
            val = med.texto_valor() + (f"   ({refs[k]})" if refs.get(k) else "")
        else:
            val = f"não medido: {med.motivo or 'sem dados'}"
        p.drawText(QRectF(x0 + 22, y, LARG_TXT - 30, 20), Qt.AlignLeft | Qt.AlignVCenter, f"{med.nome}: {val}")
        y += 22
    p.setPen(QColor(150, 150, 150))
    p.setFont(fonte(12))
    p.drawText(QRectF(20, H - 24, W - 40, 20), Qt.AlignLeft | Qt.AlignVCenter,
               f"Série: {cab.get('serie', '')} · SynthSeg (Billot et al.) pela DIPY · planos da aquisição · Ipê — não "
               "destinado a uso diagnóstico")
    p.end()
    buf = qi.constBits()
    arr = np.frombuffer(buf, np.uint8, count=qi.sizeInBytes()).reshape(H, qi.bytesPerLine())
    return arr[:, : W * 3].reshape(H, W, 3).copy()


def _caminho(db, study_uid: str, sop: str) -> str:
    from ipe.db.repository import Repository
    repo = Repository(db)
    for se in repo.series_for_study(study_uid):
        if N.MARCA not in (se.description or ""):
            continue
        for inst in repo.instances_for_series(se.series_uid):
            if inst.get("sop_uid") == sop:
                return inst["path"]
    return ""


def gravar(trabalho, res, versao: str, db, storage_root, repo=None, settings=None) -> dict:
    from ipe.ai import totalseg as TS
    from ipe.ai.totalseg_saida import cabecalho
    from ipe.imaging.derived import save_secondary_capture
    from ipe.imaging.seg_writer import build_seg
    from ipe.importer.scanner import Importer
    if repo is not None:
        for se in repo.series_for_study(trabalho.study_uid):
            if (se.description or "") in (N.DESC_SEG, N.DESC_IMAGEM):
                try:
                    repo.delete_series(se.series_uid, Path(storage_root))
                except Exception:  # noqa: BLE001
                    log.exception("trocar os índices do crânio anteriores")
    vol = trabalho.vol
    segs = [(SimpleNamespace(mask=mm, offset=off), N.ESTRUTURAS[cid][0], N.ESTRUTURAS[cid][1])
            for cid, (mm, off) in res.estruturas.items() if cid in N.ESTRUTURAS]
    if not segs:
        raise TS.Falhou("O SynthSeg não achou ventrículos nem hipocampos nesta série.")
    out = {"series": []}
    ds = build_seg(vol, segs, vol.source_path, frames=trabalho.frames, series_number=N.SERIE_SEG,
                   description=N.DESC_SEG, algoritmo=("AUTOMATIC", versao or "SynthSeg"), anatomia=True)
    tmp = Path(tempfile.mkdtemp(prefix="dv_neuro_"))
    try:
        ds.save_as(tmp / "seg.dcm", enforce_file_format=True)
        r = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([tmp])
        out["series"] += sorted(getattr(r, "new_series", None) or [])
        out["seg_sop"] = str(ds.SOPInstanceUID)
        out["seg_path"] = _caminho(db, trabalho.study_uid, out["seg_sop"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rgb = desenhar(vol, res, cabecalho(trabalho), settings)
    uid, _s = save_secondary_capture(rgb, vol.source_path, db, storage_root, description=N.DESC_IMAGEM,
                                     series_number=N.SERIE_IMAGEM,
                                     extra={"BurnedInAnnotation": "YES",
                                            "ImageComments": "Índices do crânio automáticos — conferência"},
                                     privado={(N.GRUPO_PRIVADO, N.CRIADOR): {0x01: ("UT", N.para_json(res))}})
    out["series"].append(uid)
    return out
