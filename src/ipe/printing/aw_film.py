"""Séries de filme da estação AW da GE: "AW electronic film" e "AW electronic pages".

Não são séries de exame — são impressão. O técnico monta o filme na AW e a estação manda
as duas coisas junto com o estudo:

- **AW electronic pages**: a folha já montada, do jeito que sairia na impressora (aqui,
  2560×1810 em RGB — proporção de A4 em pé);
- **AW electronic film**: as imagens soltas que entraram na folha (724×512 em cinza).

Nos dois casos é Secondary Capture com `ConversionType = WSD` e `ImageType = SCREEN SAVE`,
gravado pelo `FILMER` da estação. O reconhecimento aqui é **pelo nome da série** (escolha do
usuário): é o que aparece no exame e o que ele reconhece de olho.

O que o programa faz com elas: tira do visualizador e põe na aba Impressões, montando um
trabalho de impressão de verdade — uma folha por página — para poder pré-visualizar,
reimprimir e encaminhar pelos mesmos caminhos do que chega pela impressora DICOM.
"""

from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime
from pathlib import Path

from ipe.printing import jobs as J

log = logging.getLogger(__name__)

# nome da série -> papel dela no filme
NOMES = {"aw electronic pages": "pages", "aw electronic film": "film"}


def _norma(texto) -> str:
    return re.sub(r"\s+", " ", str(texto or "").strip()).lower()


def kind_of(description) -> str:
    """"pages" (folha montada), "film" (imagens da folha) ou "" (série normal)."""
    return NOMES.get(_norma(description), "")


def is_print_series(description) -> bool:
    """A série é material de impressão, e não do exame."""
    return bool(kind_of(description))


def split(rows: list) -> tuple[list, list]:
    """Separa uma lista de séries em (folhas montadas, imagens do filme)."""
    pages = [s for s in rows if kind_of(getattr(s, "description", "")) == "pages"]
    film = [s for s in rows if kind_of(getattr(s, "description", "")) == "film"]
    return pages, film


# ---------------------------------------------------------------- lista para a aba
def studies(repo, limit: int = 500) -> list[dict]:
    """Uma linha por exame que trouxe filme da AW, no formato da aba Impressões."""
    try:
        achados = repo.series_by_description(list(NOMES), limit)
    except Exception:  # noqa: BLE001 - a lista de impressões não pode cair por causa disto
        log.exception("séries de filme da AW")
        return []
    por_estudo: dict[str, dict] = {}
    for r in achados:
        papel = kind_of(r.get("description"))
        if not papel:
            continue
        chave = r.get("study_uid") or ""
        linha = por_estudo.setdefault(chave, {
            "kind": "aw", "id": chave, "source": "exame", "uid": "", "calling_ae": "",
            "patient_name": r.get("patient_name", ""), "patient_id": r.get("patient_id", ""),
            "label": "Filme da estação AW", "received_at": _quando(r),
            "sheets": 0, "images": 0, "film_size": "", "status": "new", "destination": "",
            "folder": "", "study_uid": chave, "message": "", "id_source": "exame",
            "pages": [], "film": [],
        })
        linha[papel].append(r.get("series_uid", ""))
        if papel == "pages":
            linha["sheets"] += int(r.get("num_images") or 0)
        else:
            linha["images"] += int(r.get("num_images") or 0)
    for linha in por_estudo.values():
        if not linha["sheets"]:          # veio só o filme solto, sem a folha montada
            linha["sheets"] = linha["images"]
            linha["message"] = "Sem a folha montada: as imagens soltas é que vão ser impressas."
    return sorted(por_estudo.values(),
                  key=lambda d: d.get("received_at") or datetime.min, reverse=True)


def _quando(r: dict):
    """Data/hora do exame como datetime — é o que a lista de impressões mostra na coluna."""
    data = str(r.get("study_date") or "")
    hora = str(r.get("study_time") or "")[:6]
    if len(data) == 8:
        try:
            return datetime.strptime(data + hora.ljust(6, "0"), "%Y%m%d%H%M%S")
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------- virar trabalho
def _oito_bits(ds):
    """A caixa do filme é desenhada em 8 bits.

    A folha montada da AW já vem em RGB de 8 bits e passa como está — pixels como vieram.
    As imagens soltas às vezes vêm em cinza de 16 bits; aí é preciso aplicar a janela do
    próprio arquivo (ou os percentis) antes, senão a folha sai quase preta, porque o valor
    máximo usado é uma fração do que 16 bits comportam.
    """
    import numpy as np
    from pydicom.dataset import Dataset

    bits = int(getattr(ds, "BitsStored", 8) or 8)
    amostras = int(getattr(ds, "SamplesPerPixel", 1) or 1)
    if bits <= 8 or amostras != 1:
        _ = ds.PixelData
        return ds
    a = ds.pixel_array.astype(np.float32)
    centro, largura = getattr(ds, "WindowCenter", None), getattr(ds, "WindowWidth", None)
    try:
        c = float(centro[0] if isinstance(centro, (list, tuple)) or hasattr(centro, "__len__")
                  else centro)
        w = float(largura[0] if isinstance(largura, (list, tuple)) or hasattr(largura, "__len__")
                  else largura)
    except (TypeError, ValueError):
        c = w = 0.0
    if w <= 1:
        lo, hi = (float(np.percentile(a, 1)), float(np.percentile(a, 99)))
    else:
        lo, hi = c - w / 2, c + w / 2
    g = np.clip((a - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    if str(getattr(ds, "PhotometricInterpretation", "")).upper() == "MONOCHROME1":
        g = 1.0 - g
    item = Dataset()
    item.SamplesPerPixel = 1
    item.PhotometricInterpretation = "MONOCHROME2"
    item.Rows, item.Columns = int(a.shape[0]), int(a.shape[1])
    item.BitsAllocated = item.BitsStored = 8
    item.HighBit, item.PixelRepresentation = 7, 0
    item.PixelData = np.ascontiguousarray((g * 255 + 0.5).astype(np.uint8)).tobytes()
    return item


def to_job(repo, study_uid: str, root: Path | str) -> tuple[J.PrintJob | None, Path | None]:
    """Monta o trabalho de impressão do filme da AW deste exame (uma folha por página).

    A folha da AW já vem montada, então cada página vira uma folha de uma caixa só —
    nada é redesenhado, os pixels vão como vieram.
    """
    import pydicom

    rows = repo.series_for_study(study_uid)
    pages, film = split(rows)
    usar = pages or film
    if not usar:
        return None, None
    info = repo.study_info(study_uid) or {}
    quando = _quando(info)
    job = J.PrintJob(uid=f"aw-{study_uid[-16:]}",
                     received_at=quando.isoformat(timespec="seconds") if quando else "",
                     calling_ae="", label="Filme da estação AW", id_source="exame",
                     patient_name=info.get("patient_name", ""),
                     patient_id=info.get("patient_id", ""), study_uid=study_uid)
    folder = Path(root) / f"aw-{study_uid[-16:]}"
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)
    n = 0
    for se in usar:
        for inst in repo.instances_for_series(se.series_uid):
            caminho = inst.get("path") if isinstance(inst, dict) else None
            if not caminho:
                continue
            try:
                ds = pydicom.dcmread(caminho, force=True)
                item = _oito_bits(ds)
            except Exception:  # noqa: BLE001
                log.exception("lendo a folha %s", caminho)
                continue
            n += 1
            box = J.write_box(folder, item, n, job)
            box.position = 1
            linhas, colunas = int(getattr(ds, "Rows", 0)), int(getattr(ds, "Columns", 0))
            job.films.append(J.FilmBox(display_format="STANDARD\\1,1", film_size="A4",
                                       orientation="PORTRAIT" if linhas >= colunas else "LANDSCAPE",
                                       border="WHITE", empty="WHITE", boxes=[box]))
    if not job.films:
        return None, None
    return job, folder
