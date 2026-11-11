"""0.100.14: quais séries do exame têm IA — para o selo "IA" nas miniaturas (Ipê e navegador).

Pedido dele (11/11/2026): *"nas miniaturas das séries (tanto no Ipê quanto no web), acrescente um ícone no canto
nas séries que têm IA"*. Duas situações levam o selo:

- **resultado de IA**: a série que uma IA gravou (SEG, tabelas, imagens de conferência) — as do Ipê terminam com a
  marca da ferramenta ("· TotalSegmentator", "· Ipê", "· BraTS"…); toda SEG também conta;
- **série analisada**: a série de onde saiu uma SEG (a ReferencedSeriesSequence da SEG) — é nela que a IA aparece.

A leitura da SEG é só do cabeçalho (sem os pixels) e fica guardada por arquivo e data.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

log = logging.getLogger(__name__)

#: o fim da descrição das séries que as IAs do Ipê gravam
MARCAS_IA = ("· TotalSegmentator", "· Ipê", "· Ipe", "· BraTS", "· autoPET", "· MedSAM2", "· SynthSeg")

_CACHE: dict[tuple, tuple[str, ...]] = {}
_TRAVA = threading.Lock()


def e_resultado(modalidade: str, descricao: str) -> bool:
    d = descricao or ""
    return (modalidade or "").upper() == "SEG" or any(m in d for m in MARCAS_IA)


def nome_da_ferramenta(descricao: str) -> str:
    d = descricao or ""
    for m in MARCAS_IA:
        d = d.replace(m, "")
    return d.strip(" ·-") or "IA"


def _referencias(caminho: str) -> tuple[str, ...]:
    """As séries de origem de uma SEG (só o cabeçalho)."""
    try:
        st = Path(caminho).stat()
    except OSError:
        return ()
    chave = (caminho, st.st_mtime_ns, st.st_size)
    with _TRAVA:
        if chave in _CACHE:
            return _CACHE[chave]
    out: list[str] = []
    try:
        import pydicom
        ds = pydicom.dcmread(caminho, stop_before_pixels=True, force=True)
        for r in ds.get("ReferencedSeriesSequence", []) or []:
            uid = str(r.get("SeriesInstanceUID", "") or "")
            if uid and uid not in out:
                out.append(uid)
        if not out:                                   # SEG sem a sequência: pelo quadro de origem
            for fg in (ds.get("SharedFunctionalGroupsSequence", []) or [])[:1]:
                for dv in fg.get("DerivationImageSequence", []) or []:
                    for src in dv.get("SourceImageSequence", []) or []:
                        uid = str(src.get("ReferencedSeriesInstanceUID", "") or "")
                        if uid and uid not in out:
                            out.append(uid)
    except Exception as e:  # noqa: BLE001
        log.debug("referências da SEG %s: %s", caminho, e)
    with _TRAVA:
        if len(_CACHE) > 4000:
            _CACHE.clear()
        _CACHE[chave] = tuple(out)
    return tuple(out)


def series_com_ia(repo, study_uid: str, series=None) -> dict[str, dict]:
    """{series_uid: {"resultado": bool, "ferramentas": [nomes]}} das séries do exame que têm IA.
    `series`: as linhas de `repo.series_for_study` já lidas (para não ler de novo)."""
    linhas = list(series) if series is not None else list(repo.series_for_study(study_uid, ocultas=True))
    uids = {r.series_uid for r in linhas}
    out: dict[str, dict] = {}
    for r in linhas:
        mod, desc = (r.modality or ""), (r.description or "")
        if not e_resultado(mod, desc):
            continue
        nome = nome_da_ferramenta(desc)
        out.setdefault(r.series_uid, {"resultado": True, "ferramentas": []})["resultado"] = True
        if nome not in out[r.series_uid]["ferramentas"]:
            out[r.series_uid]["ferramentas"].append(nome)
        if mod.upper() != "SEG":
            continue
        try:
            insts = repo.instances_for_series(r.series_uid)[:1]
        except Exception:  # noqa: BLE001
            insts = []
        for inst in insts:
            for ref in _referencias(str(inst.get("path") or "")):
                if ref in uids and ref != r.series_uid:
                    d = out.setdefault(ref, {"resultado": False, "ferramentas": []})
                    if nome not in d["ferramentas"]:
                        d["ferramentas"].append(nome)
    return out


def dica(info: dict) -> str:
    """O texto do selo (dica da miniatura)."""
    nomes = ", ".join(info.get("ferramentas") or []) or "IA"
    return f"Resultado de IA: {nomes}" if info.get("resultado") else f"IA nesta série: {nomes}"
