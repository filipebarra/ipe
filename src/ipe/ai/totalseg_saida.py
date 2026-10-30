"""O que a segmentação deixa no exame: a SEG com as máscaras e a tabela de volumes (OT).

A tabela segue o modelo que ele mostrou (cartões no alto, órgãos, segmentos de Couinaud), com o que
faltava para o número ser conferível: **de que série** saiu, o modelo e o modo, a soma dos segmentos
contra o fígado inteiro (são dois modelos diferentes — a soma não fecha) e o aviso de que não é para
diagnóstico. Na TC entra a densidade média (HU).

A imagem traz o nome do paciente escrito: vai com `BurnedInAnnotation = YES`, para a anonimização e o
modo reunião saberem que ela não serve sem tratamento.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from ipe.ai import totalseg as TS

log = logging.getLogger(__name__)

LARGURA = 1600
AZUL = (38, 54, 89)
FAIXA = (219, 225, 242)


def _fmt(v, casas=1) -> str:
    return "—" if v is None else f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def desenhar_tabela(res: "TS.Resultado", cab: dict) -> np.ndarray:
    """A tabela como imagem RGB (H×W×3). `cab`: paciente, id, aparelho, data, serie, cortes."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen

    ct = res.modalidade == "CT"
    linhas = []                                    # (tipo, textos…)
    orgaos, outras, segs = res.por_grupo("orgaos"), res.por_grupo("outras"), res.por_grupo("segmentos")
    if orgaos:
        linhas.append(("faixa", "ÓRGÃOS"))
        linhas += [("linha", e) for e in orgaos]
    if outras:
        linhas.append(("faixa", "OUTRAS ESTRUTURAS"))
        linhas += [("linha", e) for e in outras]
    if segs:
        linhas.append(("faixa", "FÍGADO — SEGMENTOS (Couinaud)"))
        linhas += [("linha", e) for e in segs]
        linhas.append(("soma", None))
    alt_linha, topo_tabela = 44, 330
    altura = topo_tabela + alt_linha * (len(linhas) + 1) + 170
    img = QImage(LARGURA, altura, QImage.Format_RGB888)
    img.fill(QColor(255, 255, 255))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)

    def fonte(pt, negrito=False):
        f = QFont("DejaVu Sans")
        f.setStyleHint(QFont.SansSerif)
        f.setPixelSize(pt)
        f.setBold(negrito)
        p.setFont(f)

    def texto(x, y, w, h, s, cor=(30, 30, 30), alin=Qt.AlignLeft | Qt.AlignVCenter):
        p.setPen(QColor(*cor))
        p.drawText(QRectF(x, y, w, h), int(alin), s)

    m = 30
    fonte(40, True)
    texto(m, 18, LARGURA, 56, f"Volumetria de órgãos abdominais — {'TC' if ct else 'RM'}")
    fonte(21)
    sub = "  |  ".join(x for x in (f"Paciente {cab.get('id', '')}".strip(), cab.get("paciente", ""),
                                   cab.get("aparelho", ""), f"Estudo {cab.get('data', '')}".strip()) if x.strip())
    texto(m, 76, LARGURA - 2 * m, 30, sub, (70, 70, 70))
    modo = "rápido (3 mm)" if any(t.get("fast") for t in cab.get("tarefas", [])) else "completo"
    texto(m, 106, LARGURA - 2 * m, 30,
          f"Série: {cab.get('serie', '')}  ·  {cab.get('cortes', '')} cortes  ·  TotalSegmentator "
          f"{res.versao or ''}  ·  modo {modo}", (70, 70, 70))

    # cartões
    rins = [res.ml("kidney_left"), res.ml("kidney_right")]
    cartoes = [(_fmt(res.figado) + " mL" if res.figado else "—", "fígado", (150, 90, 50)),
               (_fmt(res.ml("spleen")) + " mL" if res.ml("spleen") else "—", "baço", (140, 60, 80)),
               (_fmt(sum(r for r in rins if r)) + " mL" if any(rins) else "—", "rins (E+D)", (50, 100, 190)),
               (str(len(orgaos) + len(outras)), "estruturas medidas", AZUL),
               (f"{len(segs)}/8" if segs else "—", "segmentos do fígado", (60, 130, 90))]
    cw, ch, gap, y0 = (LARGURA - 2 * m - 4 * 16) / 5, 150, 16, 150
    for k, (valor, nome, cor) in enumerate(cartoes):
        x = m + k * (cw + gap)
        p.fillRect(QRectF(x, y0, cw, ch), QColor(243, 244, 248))
        p.fillRect(QRectF(x, y0, 8, ch), QColor(*cor))
        fonte(40, True)
        texto(x, y0 + 18, cw, 70, valor, (30, 30, 30), Qt.AlignHCenter | Qt.AlignVCenter)
        fonte(20)
        texto(x, y0 + 92, cw, 40, nome, (90, 90, 90), Qt.AlignHCenter | Qt.AlignVCenter)

    # tabela
    cols = [("Estrutura", 0.27), ("Volume (mL)", 0.14)]
    cols += [("HU médio", 0.17)] if ct else []
    cols += [("% da soma" if segs else "", 0.12), ("Observação", 0.0)]
    largura_util = LARGURA - 2 * m
    xs, x = [], m
    for _n, f in cols:
        xs.append(x)
        x += f * largura_util
    xs.append(LARGURA - m)
    y = topo_tabela
    p.fillRect(QRectF(m, y, largura_util, alt_linha), QColor(*AZUL))
    fonte(21, True)
    for k, (nome, _f) in enumerate(cols):
        texto(xs[k] + 14, y, xs[k + 1] - xs[k] - 20, alt_linha, nome, (255, 255, 255),
              (Qt.AlignLeft if k == 0 else Qt.AlignHCenter) | Qt.AlignVCenter)
    y += alt_linha
    par = False
    for tipo, e in linhas:
        if tipo == "faixa":
            p.fillRect(QRectF(m, y, largura_util, alt_linha), QColor(*FAIXA))
            fonte(20, True)
            texto(m + 14, y, largura_util, alt_linha, e)
            par = False
        else:
            p.fillRect(QRectF(m, y, largura_util, alt_linha), QColor(247, 247, 247) if par else QColor(255, 255, 255))
            par = not par
            if tipo == "soma":
                fonte(20, True)
                dif = (res.soma_segmentos - res.figado) if res.figado else None
                valores = ["Soma dos segmentos", _fmt(res.soma_segmentos)] + ([""] if ct else []) + \
                    ["100%" if res.soma_segmentos else "",
                     (f"{'+' if dif >= 0 else ''}{_fmt(dif)} mL ({_fmt(100 * dif / res.figado, 0)}%) em relação ao fígado"
                      if dif is not None else "")]
            else:
                fonte(20)
                valores = [e.rotulo, _fmt(e.ml)] + ([_fmt(e.hu, 0)] if ct else []) + \
                    [f"{_fmt(e.pct_figado)}%" if e.pct_figado is not None else "", e.nota]
                p.fillRect(QRectF(m + 14, y + alt_linha / 2 - 7, 14, 14), QColor(*e.cor))
            for k, v in enumerate(valores):
                dx = 38 if (k == 0 and tipo != "soma") else 14
                texto(xs[k] + dx, y, xs[k + 1] - xs[k] - dx - 6, alt_linha, v, (30, 30, 30),
                      (Qt.AlignLeft if k in (0, len(valores) - 1) else Qt.AlignHCenter) | Qt.AlignVCenter)
        p.setPen(QPen(QColor(215, 215, 215), 1))
        p.drawLine(m, int(y + alt_linha), LARGURA - m, int(y + alt_linha))
        y += alt_linha
    p.setPen(QPen(QColor(200, 200, 200), 1))
    p.drawRect(QRectF(m, topo_tabela, largura_util, y - topo_tabela))

    fonte(19)
    notas = ["Segmentação automática (TotalSegmentator, Wasserthal et al.). Confira as máscaras na série "
             "da segmentação antes de usar os números.",
             "Os segmentos de Couinaud vêm de outro modelo, menos robusto: a soma deles não precisa fechar "
             "com o volume do fígado inteiro." if segs else "",
             "Não destinado a uso diagnóstico."]
    yy = y + 22
    for n in notas:
        if n:
            texto(m, yy, largura_util, 34, n, (90, 90, 90))
            yy += 36
    p.end()
    buf = img.constBits()
    arr = np.frombuffer(buf, np.uint8, count=img.sizeInBytes()).reshape(altura, img.bytesPerLine())
    return arr[:, : LARGURA * 3].reshape(altura, LARGURA, 3).copy()


def cabecalho(trabalho: "TS.Trabalho") -> dict:
    import pydicom
    ds = pydicom.dcmread(trabalho.vol.source_path, stop_before_pixels=True, force=True)
    nome = str(ds.get("PatientName", "") or "").replace("^", " ").strip()
    data = str(ds.get("StudyDate", "") or "")
    if len(data) == 8:
        data = f"{data[6:]}/{data[4:6]}/{data[:4]}"
    esp = ds.get("SliceThickness")
    serie = trabalho.descricao_serie or str(ds.get("SeriesDescription", "") or "")
    if esp:
        serie += f" ({float(esp):g} mm)".replace(".", ",")
    return {"paciente": nome, "id": str(ds.get("PatientID", "") or ""),
            "aparelho": f"{ds.get('Manufacturer', '') or ''} {ds.get('ManufacturerModelName', '') or ''}".strip(),
            "data": data, "serie": serie, "cortes": trabalho.vol.data.shape[0],
            "tarefas": trabalho.lista_tarefas}


def gravar(trabalho: "TS.Trabalho", res: "TS.Resultado", db, storage_root) -> dict:
    """Grava a SEG e a tabela no exame. Devolve {"seg": caminho, "series": [...]}."""
    from ipe.imaging.derived import save_secondary_capture
    from ipe.imaging.seg_writer import build_seg
    from ipe.importer.scanner import Importer
    vol = trabalho.vol
    segmentos = [(SimpleNamespace(mask=e.mascara, offset=e.offset), e.rotulo, e.cor) for e in res.estruturas]
    if not segmentos:
        raise TS.Falhou("O TotalSegmentator não achou nenhum dos órgãos pedidos nesta série.")
    ds = build_seg(vol, segmentos, vol.source_path, frames=trabalho.frames, series_number=TS.SERIE_SEG,
                   description=TS.DESC_SEG,
                   algoritmo=("AUTOMATIC", f"TotalSegmentator {res.versao}".strip()), anatomia=True)
    tmp = Path(tempfile.mkdtemp(prefix="dv_totalseg_seg_"))
    out = {"series": []}
    try:
        caminho = tmp / "seg.dcm"
        ds.save_as(caminho, enforce_file_format=True)
        r = Importer(db, Path(storage_root), copy_to_storage=True, origin="import").import_paths([tmp])
        out["series"] += sorted(getattr(r, "new_series", None) or [])
        out["seg_sop"] = str(ds.SOPInstanceUID)
        out["seg_path"] = _caminho_do_sop(db, trabalho.study_uid, out["seg_sop"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    rgb = desenhar_tabela(res, cabecalho(trabalho))
    uid, _sops = save_secondary_capture(rgb, vol.source_path, db, storage_root, description=TS.DESC_TABELA,
                                        series_number=TS.SERIE_TABELA,
                                        extra={"BurnedInAnnotation": "YES",
                                               "ImageComments": "Tabela de volumes — TotalSegmentator"})
    out["series"].append(uid)
    return out


def _caminho_do_sop(db, study_uid: str, sop: str) -> str:
    from ipe.db.repository import Repository
    repo = Repository(db)
    for se in repo.series_for_study(study_uid):
        if TS.MARCA not in (se.description or ""):
            continue
        for inst in repo.instances_for_series(se.series_uid):
            if inst.get("sop_uid") == sop:
                return inst["path"]
    return ""


def resumo(res: "TS.Resultado") -> str:
    partes = [f"{e.rotulo} {_fmt(e.ml)} mL" for e in res.estruturas if e.grupo != "segmentos"][:6]
    txt = "; ".join(partes)
    if res.por_grupo("segmentos"):
        txt += f"; {len(res.por_grupo('segmentos'))} segmentos do fígado"
    return txt
