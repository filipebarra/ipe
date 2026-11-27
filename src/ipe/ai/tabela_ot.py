"""0.100.133: uma tabela OT (Secondary Capture) para TODAS as IAs, para o PACS ver os números como imagem comum.

Pedido dele (27/11/2026): *"quero OT de todas as IAs geradas, para poder enviar para o PACS"*. A opção "Tabelas" de
`saidas_ia` (global, com escolha por IA por cima) decide se a tabela é gravada e enviada. Quem já grava a sua
tabela própria (volumes do TotalSegmentator, fígado, coluna, neuro, cefalometria) não ganha uma segunda: só as
IAs sem tabela ganham esta, feita dos achados que ela guardou no exame (rótulo, local e números).
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

SERIE_TABELA = 987
MARCA = "tabela · Ipê"
MAX_LINHAS = 60


def descricao(titulo: str) -> str:
    base = (titulo or "IA").split(":")[0].split("(")[0].strip(" ·-") or "IA"
    return f"{base[:34]} · {MARCA}"


def _valor(d: dict) -> str:
    from ipe.ai import achados as AC
    return AC._fmt(d)


def linhas(achados: list[dict]) -> list[tuple[str, str, str]]:
    """[(tipo, texto da esquerda, texto da direita)] — tipo: "faixa" (cabeçalho do achado) ou "num"."""
    from ipe.ai import achados as AC
    out = []
    for a in achados[:MAX_LINHAS]:
        nome = " · ".join(x for x in (a.get("rotulo"), a.get("tipo"), a.get("local")) if x)
        est = a.get("estado") or "sugerido"
        out.append(("faixa", nome or "Achado", "" if est == "sugerido" else est))
        for k, d in AC.numeros_validos(a).items():
            if not isinstance(d, dict):
                continue
            out.append(("num", d.get("n") or k, _valor(d)))
        if a.get("elegibilidade"):
            out.append(("nota", str(a["elegibilidade"])[:150], ""))
    return out


def situacao(achados: list[dict]) -> str:
    est = [a.get("estado") or "sugerido" for a in achados]
    if est and all(e in ("confirmado", "corrigido", "descartado") for e in est):
        return "conferido pelo médico"
    if any(e in ("confirmado", "corrigido") for e in est):
        return "conferido em parte pelo médico"
    return "medida automática, sem conferência do médico"


def desenhar(titulo: str, achados: list[dict], cab: dict) -> np.ndarray:
    from PIL import Image, ImageDraw

    from ipe.ai.mama_sr import _fonte
    lin = linhas(achados)
    larg, alt_l, topo = 1400, 40, 190
    alt = topo + alt_l * max(len(lin), 1) + 110
    im = Image.new("RGB", (larg, alt), (255, 255, 255))
    g = ImageDraw.Draw(im)
    g.rectangle([0, 0, larg, 120], fill=(38, 54, 89))
    g.text((40, 22), (titulo or "IA")[:70], font=_fonte(34), fill=(255, 255, 255))
    g.text((40, 78), f"{cab.get('paciente', '')}  ·  {cab.get('id', '')}  ·  {cab.get('data', '')}",
           font=_fonte(22), fill=(219, 225, 242))
    g.text((40, 140), f"Ipê · {situacao(achados)} · {datetime.now().strftime('%d/%m/%Y %H:%M')}",
           font=_fonte(20), fill=(90, 90, 90))
    y = topo
    for tipo, a, b in lin:
        if tipo == "faixa":
            g.rectangle([30, y + 4, larg - 30, y + alt_l - 2], fill=(219, 225, 242))
            g.text((44, y + 10), a[:80], font=_fonte(22), fill=(38, 54, 89))
            g.text((larg - 44, y + 10), b, font=_fonte(20), fill=(38, 54, 89), anchor="ra")
        elif tipo == "nota":
            g.text((60, y + 11), a, font=_fonte(18), fill=(110, 110, 110))
        else:
            g.text((60, y + 9), a[:70], font=_fonte(22), fill=(30, 30, 30))
            g.text((larg - 60, y + 9), b, font=_fonte(22), fill=(30, 30, 30), anchor="ra")
            g.line([60, y + alt_l - 1, larg - 60, y + alt_l - 1], fill=(230, 230, 230))
        y += alt_l
    g.text((40, alt - 70), "Apoio à leitura — a decisão é do médico.", font=_fonte(18), fill=(110, 110, 110))
    return np.asarray(im)


def _apagar(repo, study_uid: str, desc: str, storage_root) -> None:
    for se in repo.series_for_study(study_uid):
        if (se.description or "") == desc:
            try:
                repo.delete_series(se.series_uid, Path(storage_root))
            except Exception:  # noqa: BLE001
                log.warning("não apaguei a tabela anterior %s", se.series_uid, exc_info=True)


def gravar(repo, db, storage_root, study_uid: str, ferramenta: str, titulo: str, origem: str | None = None):
    """Grava (ou refaz) a tabela da ferramenta no exame. Devolve o SeriesInstanceUID, ou None sem achados."""
    import pydicom

    from ipe.imaging.derived import save_secondary_capture
    achados = [a for a in repo.achados(study_uid, ferramenta) if (a.get("estado") or "") != "descartado"]
    desc = descricao(titulo)
    if not achados:
        _apagar(repo, study_uid, desc, storage_root)
        return None
    if not origem:
        arqs = [f for f in repo.files_for_study(study_uid) if f]
        if not arqs:
            return None
        origem = arqs[0]
    src = pydicom.dcmread(origem, stop_before_pixels=True, force=True)
    d = str(src.get("StudyDate", "") or "")
    cab = {"paciente": str(src.get("PatientName", "") or "").replace("^", " ").strip(),
           "id": str(src.get("PatientID", "") or ""),
           "data": f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 else d}
    rgb = desenhar(titulo, achados, cab)
    _apagar(repo, study_uid, desc, storage_root)
    uid, _s = save_secondary_capture(rgb, origem, db, Path(storage_root), description=desc,
                                     series_number=SERIE_TABELA, extra={"BurnedInAnnotation": "YES"},
                                     parametros=f"Tabela da IA {ferramenta} ({situacao(achados)})")
    return uid


def completar(repo, db, storage_root, settings, study_uid: str, ferramenta: str, titulo: str, saida: dict) -> dict:
    """Depois de a IA gravar: se a opção "Tabelas" vale para ela e ela não gravou tabela própria, grava esta e a
    põe em `saida["series"]`. Nunca levanta."""
    try:
        from ipe.ai import saidas_ia as SI
        if db is None or storage_root is None or not SI.efetivo(settings, "tabelas", ferramenta):
            return saida
        if repo is None:
            from ipe.db.repository import Repository
            repo = Repository(db)
        series = list(saida.get("series") or [])
        for u in series:
            try:
                if SI.classe(repo.series_info(u)) == "tabela":
                    return saida                      # a ferramenta já tem a sua
            except Exception:  # noqa: BLE001
                continue
        uid = gravar(repo, db, storage_root, study_uid, ferramenta, titulo)
        if uid:
            saida["series"] = series + [uid]
            saida["tabela_ot"] = uid
    except Exception:  # noqa: BLE001
        log.warning("tabela OT da IA %s", ferramenta, exc_info=True)
    return saida
