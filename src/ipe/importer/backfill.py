"""Completa, em segundo plano, dados que versões antigas não guardavam (ex.: Operators' Name)."""

from __future__ import annotations

import logging

import pydicom

from ipe.importer.scanner import (
    AUTO_KEY_MODALITIES, SECONDARY_CAPTURE, is_workstation_capture, series_details)

log = logging.getLogger(__name__)


def backfill_series_details(repo, batch: int = 500) -> int:
    done = 0
    while True:
        todo = repo.series_missing_details(batch)
        if not todo:
            return done
        for uid, path in todo:
            ops = sta = dev = ""
            try:
                if path:
                    ds = pydicom.dcmread(path, stop_before_pixels=True, force=True)
                    ops, sta, dev = series_details(ds)
            except Exception as e:  # noqa: BLE001 - arquivo sumido ou ilegível: marca vazio
                log.debug("Detalhes da série %s: %s", uid, e)
            repo.set_series_details(uid, ops, sta, dev)
            done += 1


def backfill_nm_key_images(repo, batch: int = 500) -> int:
    """Marca como imagem-chave as folhas de laudo de MN/PET já importadas.

    A partir da 0.24 a importação faz isso sozinha; esta passagem cuida do que entrou antes.
    Confere o cabeçalho antes de marcar — a consulta no banco filtra por classe e modalidade,
    mas quem decide é `is_workstation_capture`.
    """
    achadas = repo.captures_missing_key(SECONDARY_CAPTURE, sorted(AUTO_KEY_MODALITIES), batch)
    if not achadas:
        return 0
    marcar = []
    for study_uid, series_uid, sop_uid, path in achadas:
        try:
            ds = pydicom.dcmread(path, stop_before_pixels=True, force=True)
        except Exception as e:  # noqa: BLE001 - arquivo sumido: deixa quieto
            log.debug("Captura %s: %s", sop_uid, e)
            continue
        if is_workstation_capture(ds, SECONDARY_CAPTURE):
            marcar.append((study_uid, series_uid, sop_uid))
    return repo.add_key_images(marcar) if marcar else 0
