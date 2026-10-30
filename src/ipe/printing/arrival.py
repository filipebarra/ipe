"""Quem é o paciente do filme que acabou de chegar — lido pelo OCR, antes de qualquer regra.

A impressão DICOM não manda nome nem ID. Com o OCR na chegada ligado (o padrão desde a 0.81):

- o cabeçalho da primeira folha é lido e comparado com os pacientes do banco;
- se um paciente bate com folga clara (`ocr.escolher`, a mesma régua da janela "Identificar
  paciente"), nome e ID entram no trabalho, a origem fica "ocr" e o filme **segue pela regra**;
- se não bate, o trabalho fica **parado** esperando você confirmar o paciente à mão. Depois da
  confirmação ele segue pela regra, pelo mesmo caminho do encaminhamento automático.

Corre na thread da impressora (≈2 s por trabalho), nunca na tela.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ipe.printing import jobs as J

log = logging.getLogger(__name__)

CHAVE = "printing.ocr_on_arrival"
PADRAO = True            # ligado de fábrica: foi o pedido do serviço (0.81)

#: de onde pode vir um paciente que libera o filme para as regras
CONFIRMADO = {"ocr", "manual", "exame"}


def ligado(settings) -> bool:
    if settings is None:
        return False
    try:
        return bool(settings.get(CHAVE, PADRAO))
    except Exception:  # noqa: BLE001
        return False


def falta_paciente(settings, row: dict) -> bool:
    """Este trabalho recebido ainda espera alguém dizer de quem é?"""
    row = row or {}
    if not ligado(settings) or (row.get("source") or "scp") != "scp":
        return False
    return (row.get("id_source") or "") not in CONFIRMADO


def _ler(job: J.PrintJob, folder) -> str:
    """Só a faixa de cima (é o que a janela "Identificar paciente" lê). A chegada usa `_fontes`."""
    from ipe.printing.ocr import read_header
    if not job.films:
        return ""
    return read_header(J.compose_sheet(folder, job.films[0], width=1600))


def texto_sem_ocr(job: J.PrintJob) -> str:
    """O que a modalidade mandou **em texto**: caixas de anotação de todas as folhas e o rótulo da
    sessão. Há aparelho que não grava o nome na imagem e manda só aqui (0.86: antes isto não era lido)."""
    partes = [str(a.get("text", "")) for f in job.films for a in (f.annotations or []) if a.get("text")]
    if job.label:
        partes.append(job.label)
    return "\n".join(p for p in partes if p.strip())


def _fontes(job: J.PrintJob, folder):
    """Onde procurar o paciente, do mais barato ao mais caro (0.86): texto que veio pronto, faixa de
    cima, faixa de baixo e, por último, a folha inteira. Quem chama para no primeiro que identificar."""
    from ipe.printing import ocr
    yield "texto", lambda: texto_sem_ocr(job)
    if not job.films:
        return
    yield "cima", lambda: _ler(job, folder)           # a mesma leitura da janela "Identificar paciente"
    if not ocr.available():
        return
    folha = {}

    def px():
        if "px" not in folha:
            folha["px"] = J.compose_sheet(folder, job.films[0], width=1600)
        return folha["px"]
    yield "baixo", lambda: ocr.read_header(px(), parte="baixo")
    yield "tudo", lambda: ocr.read_header(px(), parte="tudo")


def procurar(fontes, repo) -> tuple[dict | None, str]:
    """Lê cada fonte (nome, função que devolve texto) até uma identificar o paciente com folga."""
    from ipe.printing import ocr
    estudos = None
    for onde, fonte in fontes:
        texto = fonte() or ""
        if not texto.strip():
            continue
        if estudos is None:
            estudos = repo.studies_for_ocr()
        achado = ocr.escolher(ocr.combinar(texto, estudos))
        if achado is not None:
            return achado, onde
    return None, ""


# ------------------------------------------------------------------ filme montado das imagens (0.89)
def _pixels_da_celula(repo, cell):
    """Os pixels da imagem de uma célula do filme (o quadro certo, em multiframe)."""
    import pydicom
    inst = next((i for i in repo.instances_for_series(cell.series_uid) if i.get("sop_uid") == cell.sop_uid), None)
    if inst is None:
        return None
    ds = pydicom.dcmread(inst["path"], force=True)
    px = ds.pixel_array
    n = int(str(ds.get("NumberOfFrames", 1) or 1) or 1)
    if n > 1 and px.ndim >= 3 and px.shape[0] == n:
        px = px[max(0, min(n - 1, int(cell.frame or 0)))]
    return px


def fontes_do_filme(repo, filme, quantas: int = 2):
    """Onde procurar o paciente num filme montado com imagens recebidas: o texto que a modalidade
    gravou na imagem (alto, rodapé, imagem inteira), nas primeiras imagens do filme.

    O nome do cabeçalho DICOM das imagens **não** entra: é dele que se desconfia (aparelho que manda
    nome genérico também tem esse nome no banco, e ele "combinaria" consigo mesmo)."""
    from ipe.printing import ocr
    if not ocr.available():
        return
    celulas = [c for sh in filme.sheets for c in sh.cells if c is not None][:quantas]
    for k, cell in enumerate(celulas):
        guardado = {}

        def px(c=cell, g=guardado):
            if "px" not in g:
                g["px"] = _pixels_da_celula(repo, c)
            return g["px"]
        for parte in ("cima", "baixo", "tudo"):
            yield f"imagem {k + 1} ({parte})", (lambda p=parte, f=px: ocr.read_header(f(), parte=p)
                                               if f() is not None else "")


def identificar_filme(repo, filme) -> dict | None:
    """O paciente de um filme montado com as imagens que chegaram à porta da impressora, pelo OCR."""
    try:
        achado, onde = procurar(fontes_do_filme(repo, filme), repo)
    except Exception:  # noqa: BLE001
        log.exception("OCR do filme montado %r", getattr(filme, "name", ""))
        return None
    if achado is None:
        log.info("OCR na chegada: paciente do filme montado %r não identificado", getattr(filme, "name", ""))
        return None
    log.info("OCR na chegada: filme montado %r é de %s (%.2f, lido em: %s)", getattr(filme, "name", ""),
             achado.get("patient_name", ""), achado.get("score", 0.0), onde)
    return achado


def identify(job: J.PrintJob, folder, repo, ler=None) -> dict | None:
    """Tenta identificar `job` pelo OCR. Devolve o paciente aceito (e preenche o trabalho) ou None.

    `ler(job, folder)` devolve o texto do cabeçalho; os testes trocam pelo texto pronto.
    """
    from ipe.printing import ocr
    if ler is not None:
        fontes = [("teste", lambda: ler(job, folder))]
    else:
        if not ocr.available():
            log.warning("OCR na chegada: leitor não instalado; só o texto que veio pronto é lido "
                        "(trabalho %s)", job.uid)
        fontes = _fontes(job, folder)
    try:
        achado, onde = procurar(fontes, repo)
    except Exception:  # noqa: BLE001 - OCR que falha só deixa o trabalho esperando
        log.exception("OCR na chegada do trabalho %s", job.uid)
        return None
    if achado is None:
        log.info("OCR na chegada: paciente do trabalho %s não identificado", job.uid)
        return None
    job.patient_name = achado.get("patient_name", "") or ""
    job.patient_id = achado.get("patient_id", "") or ""
    job.id_source = "ocr"
    try:
        J.save(job, Path(folder).parent)
    except Exception:  # noqa: BLE001
        log.exception("Gravando o paciente lido no trabalho %s", job.uid)
    log.info("OCR na chegada: trabalho %s é de %s (%.2f, lido em: %s)", job.uid, job.patient_name,
             achado.get("score", 0.0), onde)
    return achado
