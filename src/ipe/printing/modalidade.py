"""De que modalidade é um trabalho de impressão (0.84).

A impressão DICOM não diz a modalidade: a folha é só imagem. Duas fontes, nesta ordem:

1. **o exame do paciente**: com o paciente identificado (OCR na chegada, ou à mão), o exame dele
   mais recente feito até a hora da chegada (no mesmo dia ou no anterior) — é a modalidade "de
   verdade", a do exame que gerou o filme;
2. **a origem cadastrada**: quando o cadastro do aparelho diz a modalidade (Configurações de
   impressão ▸ Origens), vale para todo trabalho dele — inclusive antes de identificar o paciente.

Sem nenhuma das duas, a modalidade fica vazia, e regra que exige modalidade não combina.
"""
from __future__ import annotations

from datetime import datetime


def _quando(valor) -> datetime | None:
    if isinstance(valor, datetime):
        return valor
    try:
        return datetime.fromisoformat(str(valor)[:19])
    except ValueError:
        return None


def do_exame(repo, patient_id: str, chegada, excluir_uid: str = "") -> dict | None:
    """O exame do paciente que mais provavelmente gerou o filme (ou None)."""
    quando = _quando(chegada)
    if not patient_id or quando is None or not hasattr(repo, "exame_do_paciente"):
        return None
    try:
        return repo.exame_do_paciente(patient_id, quando, excluir_uid)
    except Exception:  # noqa: BLE001 - modalidade é ajuda, não pode derrubar o recebimento
        return None


def da_origem(settings, row: dict) -> str:
    if settings is None:
        return ""
    from ipe.printing import origins as O
    o = O.job_origin(settings, row)
    return (getattr(o, "modality", "") or "").strip().upper() if o is not None else ""


def descobrir(repo, settings, row: dict) -> str:
    """'MG', 'CT\\\\PT'… ou '' — ver o alto do arquivo."""
    row = row or {}
    exame = do_exame(repo, row.get("patient_id", ""), row.get("received_at"), row.get("study_uid", ""))
    if exame and exame.get("modalities"):
        return exame["modalities"]
    return da_origem(settings, row)


def lista(mod: str) -> list[str]:
    """'CT\\\\PT' -> ['CT', 'PT']."""
    return [m.strip().upper() for m in str(mod or "").replace("/", "\\").split("\\") if m.strip()]


def combina(padrao: str, mod: str) -> bool:
    """Padrão da regra: 'MG', 'MG|US', 'C*'. Vazio = qualquer. Trabalho sem modalidade não combina."""
    import fnmatch
    termos = [t.strip().upper() for t in str(padrao or "").replace(",", "|").split("|") if t.strip()]
    if not termos:
        return True
    mods = lista(mod)
    return any(fnmatch.fnmatch(m, t) for m in mods for t in termos)
