"""Folhas que chegam separadas viram páginas de um trabalho só (0.99.6).

Pedido dele (27/10): *"as impressões DICOM que chegam já montadas, hoje cada folha aparece como um
elemento separado em Impressões. é possível unir como páginas? as impressões que chegaram da mesma
fonte e no mesmo horário, fazendo OCR, e juntar como um paciente com várias folhas?"*

Muitas modalidades abrem uma sessão de impressão por folha. Aqui a folha que chega se junta ao trabalho
anterior quando:
- veio da **mesma origem** (AE, endereço e servidor de impressão);
- chegou **logo depois** da última folha dele (até `printing.juntar_segundos`, padrão 90 s);
- o trabalho anterior **ainda não saiu** (situação "new");
- o **paciente bate**: com os dois identificados (OCR, rótulo ou à mão), o ID tem de ser o mesmo (ou,
  sem ID, o nome); se só um foi identificado, junta e fica o paciente identificado; OCR que leu
  pacientes diferentes **nunca** junta.
O mesmo `juntar` serve ao botão "Juntar como páginas" da lista de impressões.
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from ipe.printing import jobs as J

log = logging.getLogger(__name__)

CHAVE = "printing.juntar_folhas"
CHAVE_SEGUNDOS = "printing.juntar_segundos"
PADRAO_SEGUNDOS = 90
PADRAO = True                    # os testes de encaminhamento desligam (conftest), como o OCR na chegada


def ligado(settings) -> bool:
    return bool(settings.get(CHAVE, PADRAO)) if settings is not None else False


def segundos(settings) -> int:
    try:
        return max(5, int(settings.get(CHAVE_SEGUNDOS, PADRAO_SEGUNDOS) or PADRAO_SEGUNDOS))
    except (TypeError, ValueError):
        return PADRAO_SEGUNDOS


def _quando(v) -> datetime | None:
    if isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v))
    except ValueError:
        return None


def mesma_origem(a: dict, b: dict) -> bool:
    return all((a.get(k) or "").strip().upper() == (b.get(k) or "").strip().upper()
               for k in ("calling_ae", "remote_host", "server"))


def _norm(t: str) -> str:
    return " ".join(str(t or "").replace("^", " ").upper().split())


def mesmo_paciente(a: dict, b: dict) -> bool | None:
    """True/False quando os dois foram identificados; None quando um (ou os dois) não foi."""
    ida, idb = (a.get("patient_id") or "").strip(), (b.get("patient_id") or "").strip()
    if ida and idb:
        return ida == idb
    na, nb = _norm(a.get("patient_name")), _norm(b.get("patient_name"))
    if (ida or na) and (idb or nb):
        return bool(na and nb and na == nb)
    return None


def _ultima(row: dict) -> datetime | None:
    """Hora da última folha do trabalho (a do json, se já juntou algo; senão a de chegada)."""
    job = J.load(row.get("folder", "")) if row.get("folder") else None
    t = _quando(job.ultima_folha_em) if job is not None and job.ultima_folha_em else None
    return t or _quando(row.get("received_at"))


def pode_juntar(base: dict, nova: dict, janela_s: int) -> bool:
    if base.get("id") == nova.get("id") or base.get("source", "scp") != "scp" or nova.get("source", "scp") != "scp":
        return False
    if base.get("status") != "new" or not mesma_origem(base, nova):
        return False
    t_base, t_nova = _ultima(base), _quando(nova.get("received_at"))
    if t_base is None or t_nova is None:
        return False
    dt = (t_nova - t_base).total_seconds()
    if dt < -5 or dt > janela_s:
        return False
    return mesmo_paciente(base, nova) is not False


def candidato(repo, nova: dict, settings) -> dict | None:
    """O trabalho a que a folha que acabou de chegar se junta (o mais recente que serve), ou None."""
    if not ligado(settings):
        return None
    janela = segundos(settings)
    for r in repo.print_jobs(60):
        if pode_juntar(r, nova, janela):
            return r
    return None


def juntar(repo, base: dict, outras: list[dict], sink=None, storage=None) -> dict:
    """Passa as folhas de `outras` (em ordem de chegada) para o fim de `base`. Os trabalhos de
    `outras` saem da lista; o exame das folhas montadas no banco é refeito com todas as páginas."""
    pasta = Path(base["folder"])
    jb = J.load(pasta)
    if jb is None:
        raise ValueError("trabalho base ilegível")
    if base.get("patient_id") or base.get("patient_name"):      # a lista é quem manda (OCR, à mão)
        jb.patient_name = base.get("patient_name") or jb.patient_name
        jb.patient_id = base.get("patient_id") or jb.patient_id
        jb.id_source = base.get("id_source") or jb.id_source
    outras = sorted([o for o in outras if o.get("id") != base.get("id")],
                    key=lambda r: _quando(r.get("received_at")) or datetime.min)
    ultima = _quando(jb.ultima_folha_em) or jb.when()
    estudos_velhos = [base.get("study_uid")] if base.get("study_uid") else []
    for k, o in enumerate(outras, start=len(jb.juntados) + 1):
        jo = J.load(o["folder"]) if o.get("folder") else None
        if jo is None:
            continue
        for film in jo.films:
            for box in film.boxes:
                if box.file:
                    novo = f"j{k:02d}_{box.file}"
                    origem = Path(o["folder"]) / box.file
                    if origem.exists():
                        shutil.copy2(origem, pasta / novo)
                    box.file = novo
            jb.films.append(film)
        pac = (o.get("patient_name") or jo.patient_name, o.get("patient_id") or jo.patient_id,
               o.get("id_source") or jo.id_source)
        if not jb.patient_id and pac[1]:
            jb.patient_name, jb.patient_id, jb.id_source = pac
        jb.juntados.append(jo.uid)
        t = jo.when()
        ultima = max(ultima, t)
        if o.get("study_uid"):
            estudos_velhos.append(o["study_uid"])
    jb.ultima_folha_em = ultima.isoformat(timespec="seconds")
    # o exame com as folhas montadas: um só, com todas as páginas
    if sink is not None and estudos_velhos:
        try:
            sink.flush(60)               # o exame da folha nova pode estar entrando agora
        except Exception:  # noqa: BLE001
            pass
        for uid in estudos_velhos:
            try:
                if storage is not None:
                    repo.delete_study(uid, Path(storage))
            except Exception:  # noqa: BLE001
                log.exception("apagar o exame da folha juntada %s", uid)
        from ipe.printing.receiver import to_database
        jb.study_uid = to_database(sink, jb, pasta)
    J.save(jb, pasta.parent)
    repo.update_print_job(base["id"], sheets=jb.sheets, images=jb.images, patient_name=jb.patient_name,
                          patient_id=jb.patient_id, id_source=jb.id_source, study_uid=jb.study_uid)
    for o in outras:
        try:
            if hasattr(repo, "delete_sends"):
                repo.delete_sends("scp", str(o["id"]))
        except Exception:  # noqa: BLE001
            pass
        velha = repo.delete_print_job(o["id"])
        if velha and Path(velha).resolve() != pasta.resolve():
            shutil.rmtree(velha, ignore_errors=True)
    out = repo.print_job(base["id"])
    if out is not None:
        out["juntadas"] = len(outras)
    return out
