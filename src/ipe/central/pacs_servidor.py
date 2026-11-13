"""0.100.37: buscar e baixar exames do PACS **pelo servidor central** — para o Ipê cliente e para o Ipê Web.

No servidor, cada nó DICOM de busca (DIMSE ou DICOMweb) pode ser marcado *Compartilhar com os clientes*. O cliente
(ou o navegador) vê esses nós, pede a busca e o download; quem fala com o PACS é o servidor, com o AE title e as
credenciais dele, e o exame baixado entra **no banco do servidor** (no banco de quem pediu, como num download feito
na tela do servidor). O cliente nunca recebe o endereço, o AE title nem a senha do nó.

Permissões: buscar pede `query`; baixar pede `retrieve`. Tudo vai para o registro de acesso do servidor.
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

CONSULTA = ("dimse", "dicomweb")
FILTROS = ("name", "patient_id", "accession", "description", "modality", "date_from", "date_to")
_ULTIMOS = 30


def _exigir(s, perm: str) -> None:
    if perm not in (getattr(s, "perms", None) or set()):
        nomes = {"query": "buscar no PACS (query)", "retrieve": "baixar do PACS (retrieve)"}
        raise PermissionError(f"seu perfil não permite {nomes.get(perm, perm)}")


def _net(c):
    net = getattr(c, "net", None)
    if net is None:
        raise RuntimeError("este servidor não tem a fila de rede ligada")
    return net


def compartilhados(c, s) -> list[dict]:
    """Os nós de busca ativos que o servidor compartilha (e que esta pessoa enxerga), com tudo o que é dele."""
    from ipe.auth import visibilidade as V
    with V.com_visao(s):
        nos = c.repo.nodes(only_active=True)
    return [n for n in nos if n.get("kind") in CONSULTA and n.get("compartilhar_clientes")]


def _no(c, s, node_id) -> dict:
    nid = abs(int(node_id or 0))
    no = next((n for n in compartilhados(c, s) if n["id"] == nid), None)
    if no is None:
        raise KeyError("nó não compartilhado pelo servidor (ou desligado)")
    return no


def nos(c, s) -> dict:
    """Só o que o cliente precisa mostrar: id, nome e para que serve. Nada de endereço, AE ou senha."""
    _exigir(s, "query")
    return {"nos": [{"id": n["id"], "nome": n["name"], "busca": bool(n.get("use_in_search")),
                     "anteriores": bool(n.get("use_in_priors")), "dicomweb": n.get("kind") == "dicomweb"}
                    for n in compartilhados(c, s)],
            "baixar": "retrieve" in (getattr(s, "perms", None) or set())}


def _filtros(f: dict) -> dict:
    out = {}
    for k in FILTROS:
        v = str((f or {}).get(k) or "").strip()
        if k in ("date_from", "date_to") and v and not re.fullmatch(r"\d{8}", v):
            raise ValueError(f"data inválida: {v} (AAAAMMDD)")
        out[k] = v[:128]
    return out


def buscar(c, s, node_id, filtros: dict, host: str = "") -> dict:
    _exigir(s, "query")
    no = _no(c, s, node_id)
    net = _net(c)
    f = _filtros(filtros)
    if not any(f[k] for k in ("name", "patient_id", "accession", "description")) and not f["date_from"]:
        raise ValueError("diga um nome, ID, acesso, descrição ou um período (busca sem filtro pesa no PACS)")
    linhas = net.cliente(no).find_studies(net.target(no, None), **f)
    c.repo.audit("busca", f"{no['name']} (pelo servidor): " + ", ".join(f"{k}={v}" for k, v in f.items() if v),
                 user=s.username, host=host)
    aqui = set(c.repo.study_uids_present([r["study_uid"] for r in linhas])) if linhas else set()
    out = []
    for r in linhas:
        d = {k: v for k, v in r.items() if isinstance(v, (str, int, float, bool)) or v is None}
        d["no_servidor"] = r["study_uid"] in aqui
        out.append(d)
    return {"estudos": out, "no": no["name"]}


def series(c, s, node_id, study_uid: str) -> dict:
    _exigir(s, "query")
    no = _no(c, s, node_id)
    net = _net(c)
    linhas = net.cliente(no).find_series(net.target(no, None), str(study_uid))
    return {"series": [{k: v for k, v in r.items() if isinstance(v, (str, int, float, bool)) or v is None}
                       for r in linhas]}


def _job(j) -> dict:
    return {"id": j.id, "rotulo": j.label, "no": (j.node or {}).get("name", ""), "estado": j.status,
            "feitas": j.done, "total": j.total, "mensagem": j.message, "inicio": j.started, "fim": j.finished,
            "study_uid": (j.study_uids or [""])[0]}


def baixar(c, s, node_id, study_uid: str, series_uids=None, rotulo: str = "", banco=None,
           host: str = "") -> dict:
    """Põe o download na fila do servidor. `banco`: (dono, visível para) do exame novo — só o próprio banco de quem
    pede (ou "" = compartilhado); o administrador escolhe qualquer um."""
    _exigir(s, "retrieve")
    no = _no(c, s, node_id)
    net = _net(c)
    uid = str(study_uid or "").strip()
    if not uid:
        raise ValueError("diga o exame (study_uid)")
    dono, visivel = "", ""
    if banco:
        dono = str((banco[0] if len(banco) > 0 else "") or "").strip()
        visivel = str((banco[1] if len(banco) > 1 else "") or "").strip()
    v = c._visao(s)
    admin = v is None or getattr(v, "admin", False)
    if dono and dono != s.username and not admin:
        raise PermissionError("o exame baixado só pode ir para o seu banco ou para o compartilhado")
    if not dono:
        visivel = ""
    if c.repo.study_info(uid) is not None and not c.pode_ver(s, uid):
        raise PermissionError("o exame já está no servidor, no banco pessoal de outro usuário")
    lista = [str(x) for x in (series_uids or []) if x] or None
    rot = (rotulo or uid)[:200] + " — pelo " + ("navegador" if host == "web" else "cliente")
    job = net.retrieve(no, None, uid, rot, lista, banco=(dono, visivel))
    job.dono = s.username
    c.repo.audit("baixar", f"{no['name']} (pelo servidor, para {s.username}): {rotulo or uid}",
                 user=s.username, study_uid=uid, host="" if host == "web" else host)
    return {"ok": True, "download": _job(job)}


def downloads(c, s) -> dict:
    net = getattr(c, "net", None)
    if net is None:
        return {"downloads": []}
    meus = [j for j in net.jobs if j.kind == "retrieve" and j.dono == s.username]
    return {"downloads": [_job(j) for j in meus[-_ULTIMOS:]][::-1]}


def andamento(c, s, job_id) -> dict:
    net = _net(c)
    jid = int(job_id or 0)
    for j in net.jobs:
        if j.id == jid and j.kind == "retrieve" and j.dono == s.username:
            return _job(j)
    raise KeyError("download não encontrado")


def cancelar(c, s, job_id) -> dict:
    net = _net(c)
    jid = int(job_id or 0)
    for j in net.jobs:
        if j.id == jid and j.kind == "retrieve" and j.dono == s.username:
            net.cancel(j)
            return {"ok": True}
    raise KeyError("download não encontrado")


# o que o Ipê cliente chama pelo RPC (o servidor trata, com a sessão de quem pede)
RPC = ("pacs_nos", "pacs_buscar", "pacs_series", "pacs_baixar", "pacs_andamento", "pacs_cancelar",
       "pacs_downloads")


def rpc(c, s, method: str, args: list, kwargs: dict, host: str = ""):
    a = list(args or [])

    def arg(i, nome, padrao=None):
        return a[i] if len(a) > i else kwargs.get(nome, padrao)
    if method == "pacs_nos":
        return nos(c, s)
    if method == "pacs_buscar":
        return buscar(c, s, arg(0, "node_id"), arg(1, "filtros", {}) or {}, host)
    if method == "pacs_series":
        return series(c, s, arg(0, "node_id"), arg(1, "study_uid", ""))
    if method == "pacs_baixar":
        return baixar(c, s, arg(0, "node_id"), arg(1, "study_uid", ""), arg(2, "series_uids"),
                      arg(3, "rotulo", ""), arg(4, "banco"), host)
    if method == "pacs_andamento":
        return andamento(c, s, arg(0, "job_id"))
    if method == "pacs_cancelar":
        return cancelar(c, s, arg(0, "job_id"))
    if method == "pacs_downloads":
        return downloads(c, s)
    raise PermissionError(f"método não permitido: {method}")
