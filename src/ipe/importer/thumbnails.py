"""Gera miniaturas das séries novas (imagem do meio da série)."""

from __future__ import annotations

import logging
from typing import Iterable

from ipe.db.repository import Repository
from ipe.imaging.series import build_frames, read_frame
from ipe.imaging.windowing import make_thumbnail

log = logging.getLogger(__name__)


def generate_thumbnails(repo: Repository, series_uids: Iterable[str], force: bool = False) -> int:
    done = 0
    for uid in series_uids:
        try:
            if not force and repo.has_thumbnail(uid):
                continue
            frames = build_frames(repo.instances_for_series(uid))
            if not frames:
                continue
            img = read_frame(frames[len(frames) // 2])
            repo.set_thumbnail(uid, make_thumbnail(img))
            done += 1
        except Exception as e:  # noqa: BLE001 - miniatura nunca pode travar importação
            log.warning("Miniatura falhou para %s: %s", uid, e)
    return done


_FALHARAM: set[str] = set()      # série que não deu miniatura: não tenta de novo nesta sessão


def miniaturas_que_faltam(repo: Repository, study_uid: str) -> int:
    """Gera a miniatura das séries do exame que não têm (0.69.1).

    Pedido dele: *"é possível mostrar a miniatura do SC no banco de dados e na lista de séries
    no viewer?"*. A captura da lesão, o gráfico da dinâmica, os mapas salvos e o DICOM SEG eram
    gravados pelo importador direto, sem passar pela miniatura (que só a importação de pasta e a
    rede faziam). Isto conserta as que já estão no banco, na hora em que o exame aparece.
    """
    try:
        faltam = [s.series_uid for s in repo.series_for_study(study_uid, ocultas=True)
                  if not s.thumbnail and s.num_images and s.series_uid not in _FALHARAM]
    except Exception as e:  # noqa: BLE001
        log.warning("Miniaturas do exame %s: %s", study_uid, e)
        return 0
    if not faltam:
        return 0
    feitas = generate_thumbnails(repo, faltam)
    for uid in faltam:
        if not repo.has_thumbnail(uid):
            _FALHARAM.add(uid)
    return feitas
