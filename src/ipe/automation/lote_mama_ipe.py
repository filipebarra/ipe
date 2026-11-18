"""O lote da mama ligado no Ipê (0.100.69): quem busca no banco e no PACS, baixa, mede e apaga.

`servicos(...)` devolve o `lote_mama.Servicos` de verdade. Sem janelas; roda numa linha de fundo.
"""
from __future__ import annotations

import logging
import time

from ipe.automation import lote_mama as L

log = logging.getLogger(__name__)

ESPERA_DOWNLOAD_S = 30 * 60
ESPERA_FILA_S = 20 * 60


def pronto_para_medir(repo) -> tuple[bool, str]:
    """As duas redes estão instaladas e o banco é o deste computador?"""
    from ipe.ai import calc_vascular as C
    from ipe.ai import densidade_nyu as N
    from ipe.automation import mama_auto as MA
    if not MA.local(repo):
        return False, ("Este Ipê é cliente de um servidor: as imagens não ficam aqui. Rode o lote no Ipê do "
                       "servidor (ou num Ipê com banco próprio).")
    faltam = []
    for nome, mod in (("densidade (rede da NYU)", N), ("calcificações vasculares (SCU-Net)", C)):
        ok, motivo = mod.disponivel()
        if not ok:
            faltam.append(f"{nome}: {motivo}")
    if faltam:
        return False, "Falta instalar o modelo de " + "; ".join(faltam)
    return True, ""


def _so_mg(exames: list[dict], pid: str) -> list[dict]:
    """O PACS pode devolver mais do que foi pedido: fica o ID igual (sem contar zeros à esquerda) e o que tem MG."""
    def igual(a: str) -> bool:
        a, b = str(a or "").strip(), pid.strip()
        return a == b or (a.lstrip("0") == b.lstrip("0") and a.lstrip("0") != "")
    out = [e for e in exames if igual(e.get("patient_id", ""))]
    com_mg = [e for e in out if "MG" in str(e.get("modalities") or "").upper()]
    return com_mg or [e for e in out if not str(e.get("modalities") or "").strip()]


def servicos(repo, net, settings, node: dict, identity: dict | None, storage_root, fila=None) -> L.Servicos:
    from ipe.ai import calc_vascular as C
    from ipe.automation import mama_auto as MA
    from ipe.imaging import densidade_revisao as R

    def local(pid: str, data: str) -> list[dict]:
        linhas = repo.search_studies(text=pid, modality="MG", date_from=data, date_to=data, limit=200, banco="todos")
        return _so_mg([{"study_uid": r.study_uid, "patient_id": r.patient_id, "birth_date": r.birth_date,
                        "accession": r.accession, "study_date": r.study_date, "study_time": r.study_time,
                        "description": r.description, "modalities": r.modalities, "num_images": r.num_images}
                       for r in linhas if (r.study_date or "")[:8] == data], pid)

    def pacs(pid: str, data: str) -> list[dict]:
        cli, alvo = net.cliente(node), net.target(node, identity)
        achados = cli.find_studies(alvo, patient_id=pid, date_from=data, date_to=data, modality="MG", limit=50)
        out = _so_mg(achados, pid)
        if not out and pid.lstrip("0"):
            # o PACS pode guardar o ID com (ou sem) zeros à esquerda: busca pelo fim e fica só o que é o mesmo número
            out = _so_mg(cli.find_studies(alvo, patient_id="*" + pid.lstrip("0"), date_from=data, date_to=data,
                                          modality="MG", limit=50), pid)
        return out

    def baixar(exame: dict, parar=None) -> tuple[bool, str]:
        uid = exame["study_uid"]
        job = net.retrieve(node, identity, uid, f"Lote da mama: {exame.get('accession') or uid[-12:]}")
        fim = time.time() + ESPERA_DOWNLOAD_S
        while job.active:
            if parar is not None and parar.is_set():
                net.cancel(job)
                return False, "parado"
            if time.time() > fim:
                net.cancel(job)
                return False, "o download passou de 30 minutos"
            time.sleep(0.25)
        if job.status != "done":
            return False, job.message or job.status
        if not [f for f in repo.files_for_study(uid) if f]:
            return False, "o PACS não mandou nenhuma imagem"
        return True, job.message

    def medir(uid: str, parar=None):
        # com "medir sozinho na chegada" ligado, a fila do Ipê pode estar medindo este exame agora: espera
        if fila is not None:
            if MA.ligado(settings):
                time.sleep(1.5)                  # o aviso de chegada vem pela linha da tela, um instante depois
            fim = time.time() + ESPERA_FILA_S
            while uid in getattr(fila, "_na_fila", ()) and time.time() < fim:
                if parar is not None and parar.is_set():
                    return None, None
                time.sleep(0.5)
        falta = MA.falta(repo, uid)
        if falta:
            out = MA.medir(repo, uid, parar, o_que=falta)
            if out.get("erros"):
                log.warning("lote da mama %s: %s", uid, "; ".join(out["erros"]))
        return R.guardada(repo, uid), C.guardada(repo, uid)

    def apagar(uid: str) -> None:
        repo.delete_study(uid, storage_root)

    return L.Servicos(local=local, pacs=pacs, baixar=baixar, medir=medir, apagar=apagar)
