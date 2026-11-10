"""0.100.4: o fim do laudo no navegador — o formulário BI-RADS com os textos do Ipê, o PDF, os objetos DICOM
(PDF encapsulado e SR) guardados no exame ao assinar e a busca ativa (BI-RADS 0, 3…).

Tudo aqui usa as mesmas funções da janela do laudo do Ipê (`reporting/birads.py`, `reporting/pdf.py`,
`reporting/dicom_out.py`, `reporting/busca_ativa.py`): o navegador só mostra o formulário e o texto. Assim o
texto do BI-RADS, o PDF e o SR saem iguais aos do consultório.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
import threading
from pathlib import Path

log = logging.getLogger(__name__)

#: o PDF usa o QTextDocument/QPdfWriter do Qt: um de cada vez (as threads do servidor são várias)
_PDF = threading.Lock()


def catalogo_birads() -> dict:
    """As listas do formulário (as do Ipê), para o navegador montar os campos."""
    from ipe.reporting import birads as B
    return {"tipos": B.KIND_NAMES, "categorias": B.CATEGORIES, "achados": B.FINDING_TYPES,
            "descritores": B.DESCRIPTORS, "lados": B.SIDES, "composicao": B.COMPOSITION, "bpe": B.BPE,
            "locais": B.LOCATIONS, "mudancas": B.CHANGES, "recomendacao": B.RECOMMENDATION}


def textos_birads(fields: dict) -> dict:
    """Os blocos do laudo que saem do formulário (os mesmos campos {composicao}, {achados_birads}, {birads},
    {conduta} e {bpe_texto} dos modelos), a categoria final e a frase de cada achado."""
    from ipe.reporting import birads as B
    f = fields if isinstance(fields, dict) else {}
    if not f.get("kind"):
        return {"blocos": {}, "final": "", "achados": []}
    return {"blocos": {"composicao": B.composition_text(f), "achados_birads": B.findings_text(f),
                       "birads": B.category_text(f), "conduta": B.recommendation(f), "bpe_texto": B.bpe_text(f)},
            "final": B.final_category(f),
            "achados": [B.finding_text(x) for x in f.get("findings") or []]}


def preferencias(settings, usuario: str, info: dict) -> dict:
    """O cabeçalho do PDF, a linha da assinatura e se guarda o PDF e o SR no exame — as mesmas chaves da janela
    do laudo do Ipê (a assinatura é de cada usuário)."""
    def get(k, d=None):
        try:
            return settings.get(k, d) if settings is not None else d
        except Exception:  # noqa: BLE001
            return d
    return {"cabecalho": str(get("report.header", "") or info.get("institution", "") or ""),
            "assinatura": str(get(f"report.signature.{usuario}", "") or ""),
            "pdf": bool(get("report.dicom_pdf", True)), "sr": bool(get("report.dicom_sr", True))}


def guardar_preferencias(settings, usuario: str, op: dict) -> None:
    if settings is None:
        return
    try:
        if "cabecalho" in op:
            settings.set("report.header", str(op.get("cabecalho") or "").strip())
        if "assinatura" in op:
            settings.set(f"report.signature.{usuario}", str(op.get("assinatura") or "").strip())
        if "pdf" in op:
            settings.set("report.dicom_pdf", bool(op.get("pdf")))
        if "sr" in op:
            settings.set("report.dicom_sr", bool(op.get("sr")))
    except Exception as e:  # noqa: BLE001
        log.warning("laudo web: não gravei as preferências: %s", e)


def pdf_do_laudo(info: dict, rep: dict, cabecalho: str, assinatura: str) -> bytes:
    """O PDF do laudo, igual ao do Ipê (rascunho sai marcado RASCUNHO). Precisa do Qt de interface: no
    servidor sem janela, o `ipe server` sobe o Qt sem tela (offscreen)."""
    from PySide6.QtGui import QGuiApplication
    from ipe.reporting.pdf import write_pdf
    if QGuiApplication.instance() is None:
        raise RuntimeError("o PDF precisa do Qt de interface (atualize o servidor)")
    with _PDF:
        return write_pdf(None, info, rep, cabecalho, assinatura, [], False)


def depois_de_assinar(repo, storage: Path, rep: dict, info: dict, op: dict) -> list[str]:
    """O que a janela do Ipê faz ao assinar (report_window.sign/store_dicom): o PDF encapsulado e o SR no
    exame (como séries novas) e a busca ativa. Devolve as frases para mostrar ao médico."""
    from ipe.reporting import birads as B
    from ipe.reporting import busca_ativa as BA
    from ipe.reporting import dicom_out as D
    msgs: list[str] = []
    files = repo.files_for_study(rep["study_uid"])
    if files and (op.get("pdf") or op.get("sr")):
        tmp = Path(tempfile.mkdtemp(prefix="ipe_laudo_web_"))
        try:
            n = 0
            if op.get("pdf"):
                pdf = pdf_do_laudo(info, rep, op.get("cabecalho", ""), op.get("assinatura", ""))
                D.encapsulated_pdf(pdf, files[0], rep.get("title") or "Laudo").save_as(
                    tmp / "laudo_pdf.dcm", enforce_file_format=True)
                n += 1
            if op.get("sr"):
                cat = B.final_category(rep.get("fields") or {})
                D.text_sr(rep.get("text", ""), files[0], rep.get("title") or "Laudo", rep.get("author", ""), True,
                          rep.get("signed_by", ""), cat).save_as(tmp / "laudo_sr.dcm", enforce_file_format=True)
                n += 1
            if n:
                from ipe.importer.scanner import Importer
                Importer(repo.db, storage).import_paths([tmp])
                msgs.append(f"{n} objeto(s) DICOM guardado(s) no exame")
        except Exception as e:  # noqa: BLE001
            log.exception("laudo web: DICOM no exame")
            msgs.append(f"não foi possível gravar no exame: {e}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    try:
        txt = BA.registrar_do_laudo(repo, rep, info)
        if txt:
            msgs.append(txt)
    except Exception:  # noqa: BLE001
        log.exception("laudo web: busca ativa")
    return msgs


def buscas_do_paciente(repo, info: dict) -> list[dict]:
    """Os pedidos de busca ativa abertos da paciente (de qualquer exame), para o médico ver no laudo."""
    from ipe.reporting import busca_ativa as BA
    pid = (info or {}).get("patient_id", "")
    if not pid:
        return []
    try:
        itens = repo.buscas_ativas(estados=BA.ABERTOS)
    except Exception:  # noqa: BLE001
        return []
    out = []
    for b in itens:
        if b.get("patient_id") != pid:
            continue
        sit, atrasado = BA.situacao(b)
        out.append({"id": b.get("id"), "study_uid": b.get("study_uid"), "categoria": b.get("categoria"),
                    "motivo": b.get("motivo"), "prazo": BA.fmt(b.get("prazo", "")),
                    "estado": BA.ESTADOS.get(b.get("estado", ""), b.get("estado", "")), "situacao": sit,
                    "atrasado": bool(atrasado)})
    return out
