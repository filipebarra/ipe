"""PDF do laudo (Qt: QTextDocument + QPdfWriter): cabeçalho, dados do paciente, texto, imagens-chave
e assinatura. Rascunho sai marcado como RASCUNHO."""

from __future__ import annotations

import html
from datetime import datetime

from ipe.reporting.fill import age_text, fmt_date


def report_html(info: dict, report: dict, header: str = "", signature: str = "", n_images: int = 0,
                anonymize: bool = False) -> str:
    e = html.escape
    name = "" if anonymize else (info.get("patient_name") or "").replace("^", " ").strip()
    rows = [("Paciente", name), ("ID", "" if anonymize else info.get("patient_id", "")),
            ("Idade", age_text(info)), ("Sexo", {"M": "Masculino", "F": "Feminino"}.get(info.get("sex", ""), "")),
            ("Exame", info.get("description", "") or info.get("modalities", "")),
            ("Data do exame", fmt_date(info.get("study_date", ""))),
            ("Acesso", info.get("accession", "")),
            ("Solicitante", (info.get("referring") or "").replace("^", " ").strip())]
    cells = "".join(f"<tr><td style='color:#555;padding-right:10px'>{e(k)}:</td><td><b>{e(v)}</b></td></tr>"
                    for k, v in rows if v)
    head = "".join(f"<div>{e(x)}</div>" for x in (header or info.get("institution", "")).splitlines() if x.strip())
    body_lines = []
    for line in (report.get("text") or "").splitlines():
        t = line.strip()
        if t and t.upper() == t and any(c.isalpha() for c in t) and len(t) < 90:
            body_lines.append(f"<p style='margin:10px 0 2px 0'><b>{e(line)}</b></p>")
        elif not t:
            body_lines.append("<p style='margin:0'>&nbsp;</p>")
        else:
            body_lines.append(f"<p style='margin:0'>{e(line)}</p>")
    imgs = ""
    if n_images:
        cellsimg = "".join(f"<td style='padding:4px'><img src='key{i}.png' width='300'></td>"
                           + ("</tr><tr>" if i % 3 == 2 else "") for i in range(n_images))
        imgs = f"<p style='margin-top:12px'><b>Imagens-chave</b></p><table><tr>{cellsimg}</tr></table>"
    if report.get("status") in ("final", "amended"):
        when = report.get("signed_at") or datetime.now().strftime("%Y-%m-%d %H:%M")
        try:
            when = datetime.strptime(when, "%Y-%m-%d %H:%M").strftime("%d/%m/%Y %H:%M")
        except ValueError:
            pass
        sig = (f"<p style='margin-top:26px'>Assinado eletronicamente por <b>{e(report.get('signed_by') or '')}</b>"
               f" em {e(when)}.</p>")
        if report.get("status") == "amended":
            sig = "<p><b>LAUDO RETIFICADO</b> (substitui o anterior).</p>" + sig
    else:
        sig = "<p style='margin-top:26px;color:#b00'><b>RASCUNHO — laudo não assinado.</b></p>"
    if signature:
        sig += "".join(f"<div>{e(x)}</div>" for x in signature.splitlines())
    title = e(report.get("title") or "Laudo")
    return (f"<html><body style='font-family:Arial,Helvetica,sans-serif;font-size:10.5pt'>"
            f"<div style='font-size:12pt'>{head}</div><hr>"
            f"<table style='font-size:9.5pt'>{cells}</table><hr>"
            f"<h3 style='text-align:center'>{title}</h3>{''.join(body_lines)}{imgs}{sig}</body></html>")


def write_pdf(path_or_none, info: dict, report: dict, header: str = "", signature: str = "",
              images: list | None = None, anonymize: bool = False) -> bytes:
    """Gera o PDF (A4). Devolve os bytes; se `path_or_none` vier, grava também no arquivo."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QUrl
    from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument
    images = images or []
    doc = QTextDocument()
    for i, q in enumerate(images):
        doc.addResource(QTextDocument.ImageResource, QUrl(f"key{i}.png"), q)
    doc.setHtml(report_html(info, report, header, signature, len(images), anonymize))
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    w = QPdfWriter(buf)
    w.setResolution(150)
    w.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait, QMarginsF(18, 15, 18, 15),
                                QPageLayout.Millimeter))
    w.setTitle(report.get("title") or "Laudo")
    w.setCreator("Ipê")
    doc.print_(w)
    del w
    buf.close()
    data = bytes(ba.data())
    if path_or_none:
        with open(path_or_none, "wb") as f:
            f.write(data)
    return data
