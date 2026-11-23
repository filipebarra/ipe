"""0.100.103: abrir um exame no Ipê Web por chamada externa — pelo número de acesso ou pelo ID (com data e modalidade).

Pedido dele (23/11/2026): *"crie as opções de chamada externa (…/web/#/abrir?acesso=12345 e
…/web/#/abrir?id=98765&data=20261123&mod=MR) e também a opção de baixar do PACS se não estiver no Ipê. Por hora pode
deixar o login obrigatório; não precisa de link assinado"*.

`POST /api/web/abrir` com {acesso, id, data, mod, uid}: procura primeiro no servidor (só o que a pessoa enxerga);
se não achar, nos nós do PACS que o servidor compartilha e que servem para busca (permissão de busca). Quem baixa é a
página, pelo `/api/web/pacs/baixar` de sempre (permissão de download). Sem Qt.
"""
from __future__ import annotations

import re

CHAVES = ("acesso", "id", "data", "mod", "uid")


def criterios(corpo: dict) -> dict:
    """Os critérios limpos: data em AAAAMMDD (aceita AAAA-MM-DD e DD/MM/AAAA), modalidade em maiúsculas."""
    k = {c: str((corpo or {}).get(c) or "").strip()[:128] for c in CHAVES}
    for alias, c in (("accession", "acesso"), ("patient_id", "id"), ("paciente", "id"), ("modalidade", "mod"),
                     ("study", "uid"), ("StudyInstanceUID", "uid"), ("AccessionNumber", "acesso"),
                     ("PatientID", "id"), ("StudyDate", "data")):
        if not k[c] and (corpo or {}).get(alias):
            k[c] = str(corpo[alias]).strip()[:128]
    d = k["data"]
    if d:
        m = re.fullmatch(r"(\d{4})-?(\d{2})-?(\d{2})", d) or None
        if m:
            k["data"] = "".join(m.groups())
        else:
            m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", d)
            if not m:
                raise ValueError(f"data inválida: {d} (use AAAAMMDD)")
            k["data"] = m.group(3) + m.group(2) + m.group(1)
    k["mod"] = k["mod"].upper()
    if not (k["acesso"] or k["id"] or k["uid"]):
        raise ValueError("diga o número de acesso (acesso=), o ID do paciente (id=) ou o Study Instance UID (uid=)")
    return k


def _linha(r) -> dict:
    return {"study_uid": r.study_uid, "patient_name": r.patient_name or "", "patient_id": r.patient_id or "",
            "study_date": r.study_date or "", "description": r.description or "",
            "modalities": r.modalities or "", "accession": r.accession or "",
            "num_images": int(getattr(r, "num_images", 0) or 0)}


def _modalidade_bate(mods: str, mod: str) -> bool:
    if not mod:
        return True
    return mod in {m.strip().upper() for m in re.split(r"[\\/,; ]+", mods or "") if m.strip()}


def no_servidor(c, s, k: dict) -> list[dict]:
    """Os exames do servidor que batem (só os que a pessoa enxerga)."""
    from ipe.auth.visibilidade import com_visao
    with com_visao(s):
        if k["uid"]:
            rows = [r for r in c.repo.search_studies(text=k["uid"], limit=50) if r.study_uid == k["uid"]]
            if not rows and c.repo.study_info(k["uid"]) is not None and c.pode_ver(s, k["uid"]):
                return [{"study_uid": k["uid"], "patient_name": "", "patient_id": "", "study_date": "",
                         "description": "", "modalities": "", "accession": "", "num_images": 0}]
        elif k["acesso"]:
            rows = [r for r in c.repo.search_studies(text=k["acesso"], limit=200)
                    if (r.accession or "").strip() == k["acesso"]]
        else:
            rows = [r for r in c.repo.search_studies(text=k["id"], date_from=k["data"], date_to=k["data"],
                                                     limit=300)
                    if (r.patient_id or "").strip() == k["id"]]
    rows = [r for r in rows if _modalidade_bate(r.modalities or "", k["mod"]) and c.pode_ver(s, r.study_uid)]
    if k["data"]:
        rows = [r for r in rows if (r.study_date or "") == k["data"]]
    return [_linha(r) for r in rows]


def _filtros(k: dict, com_mod: bool = True) -> dict:
    f = {"accession": k["acesso"]} if k["acesso"] else {"patient_id": k["id"]}
    if k["data"]:
        f["date_from"] = f["date_to"] = k["data"]
    if k["mod"] and com_mod:
        f["modality"] = k["mod"]
    return f


def no_pacs(c, s, k: dict) -> tuple[list[dict], list[str]]:
    """Os exames dos nós de busca que batem: ([{…, no, no_nome}], [erros])."""
    from ipe.central import pacs_servidor as PS
    if "query" not in (getattr(s, "perms", None) or set()):
        return [], ["seu perfil não permite buscar no PACS"]
    if k["uid"] and not (k["acesso"] or k["id"]):
        return [], ["pelo Study Instance UID só dá para abrir o que já está no servidor"]
    out, erros, vistos = [], [], set()
    for no in [n for n in PS.compartilhados(c, s) if n.get("use_in_search", True)]:
        try:
            achados = PS.buscar(c, s, no["id"], _filtros(k), "web")["estudos"]
            if not achados and k["mod"]:             # PACS que não filtram pela modalidade: busca sem ela e filtra aqui
                achados = [e for e in PS.buscar(c, s, no["id"], _filtros(k, False), "web")["estudos"]
                           if _modalidade_bate(str(e.get("modalities") or ""), k["mod"])]
        except Exception as e:  # noqa: BLE001
            erros.append(f"{no.get('name', '')}: {e}")
            continue
        for e in achados:
            mods = str(e.get("modalities") or "")
            if mods and not _modalidade_bate(mods, k["mod"]):     # PACS que ignora o filtro de modalidade
                continue
            if k["acesso"] and str(e.get("accession") or "").strip() not in ("", k["acesso"]):
                continue
            if k["id"] and not k["acesso"] and str(e.get("patient_id") or "").strip() not in ("", k["id"]):
                continue
            if e.get("study_uid") in vistos:
                continue
            vistos.add(e.get("study_uid"))
            out.append({**e, "no": no["id"], "no_nome": no.get("name", "")})
    return out, erros


def buscar(c, s, corpo: dict) -> dict:
    """{criterios, servidor: [...], pacs: [...], erros: [...], baixar: pode baixar?}. O PACS só é consultado quando o
    exame não está no servidor."""
    k = criterios(corpo)
    aqui = no_servidor(c, s, k)
    pacs, erros = ([], []) if aqui else no_pacs(c, s, k)
    try:
        c.repo.audit("abrir_externo", ", ".join(f"{a}={v}" for a, v in k.items() if v)
                     + f" — {len(aqui)} no servidor, {len(pacs)} no PACS", user=s.username)
    except Exception:  # noqa: BLE001
        pass
    return {"criterios": k, "servidor": aqui, "pacs": pacs, "erros": erros,
            "baixar": "retrieve" in (getattr(s, "perms", None) or set())}
