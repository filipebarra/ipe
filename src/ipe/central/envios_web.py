"""0.100.9: enviar do visualizador web para um destino DICOM (PACS) — o exame, séries ou uma imagem.

O navegador só pede: o envio entra na **fila de envios do servidor** (`NetworkService`, a mesma do Ipê), com os nós
de rede cadastrados nele. Pode ir junto o que se fez no navegador: as medidas viram um GSPS e as imagens-chave um KO
no exame, e vão no mesmo envio. Só para quem tem a permissão de enviar; tudo fica no registro de acesso.

O andamento: `GET /api/web/envios` lista os envios pedidos por esta pessoa (os últimos 20), com feitas/total e a
mensagem do serviço; `POST /api/web/envios/cancelar` para um.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

PERMISSAO = "send"
_ULTIMOS = 20


def _exigir(s) -> None:
    if PERMISSAO not in (getattr(s, "perms", None) or set()):
        raise PermissionError("seu perfil não permite enviar para nós DICOM (send)")


def destinos(c, s) -> dict:
    """Os nós ativos do servidor (e as identidades que podem falar com cada um)."""
    _exigir(s)
    net = getattr(c, "net", None)
    from ipe.auth import visibilidade as V
    out = []
    with V.com_visao(s):                      # os nós do serviço, os desta pessoa e os compartilhados com ela
        nos = c.repo.nodes(only_active=True)
    for n in nos:
        ids = net.identities_for(n) if net is not None else []
        out.append({"id": n["id"], "nome": n["name"], "ae": n.get("ae_title", ""), "host": n.get("host", ""),
                    "porta": n.get("port", 0), "dicomweb": bool(n.get("dicomweb_url") or n.get("kind") == "dicomweb"),
                    "identidades": [{"id": i["id"], "nome": i.get("name", ""), "ae": i.get("ae_title", "")}
                                    for i in ids]})
    return {"destinos": out, "fila": net is not None}


def _job(j) -> dict:
    return {"id": j.id, "rotulo": j.label, "destino": (j.node or {}).get("name", ""), "estado": j.status,
            "feitas": j.done, "total": j.total, "mensagem": j.message, "inicio": j.started, "fim": j.finished}


def envios(c, s) -> dict:
    net = getattr(c, "net", None)
    if net is None:
        return {"envios": []}
    meus = [j for j in net.jobs if j.kind == "send" and j.dono == s.username]
    return {"envios": [_job(j) for j in meus[-_ULTIMOS:]][::-1]}


def cancelar(c, s, corpo: dict) -> dict:
    _exigir(s)
    net = getattr(c, "net", None)
    jid = int(corpo.get("id") or 0)
    for j in (net.jobs if net is not None else []):
        if j.id == jid and j.kind == "send" and j.dono == s.username:
            net.cancel(j)
            return {"ok": True}
    raise KeyError("envio não encontrado")


def enviar(c, s, corpo: dict) -> dict:
    """{study, destino, identidade?, series?: [...], sops?: [...] (com uma série), objetos?: bool}."""
    _exigir(s)
    net = getattr(c, "net", None)
    if net is None:
        raise RuntimeError("este servidor não tem a fila de rede ligada")
    study = str(corpo.get("study") or "")
    if not study or not c.pode_ver(s, study):
        raise PermissionError("exame fora do seu acesso")
    from ipe.auth import visibilidade as V
    nid = int(corpo.get("destino") or 0)
    with V.com_visao(s):
        no = next((n for n in c.repo.nodes(only_active=True) if n["id"] == nid), None)
    if no is None:
        raise KeyError("destino não encontrado ou desligado")
    ident = None
    if corpo.get("identidade"):
        ident = c.repo.identity(int(corpo["identidade"]))
        if ident is not None and ident["id"] not in {i["id"] for i in net.identities_for(no)}:
            raise PermissionError("esta identidade não fala com este destino")
    series = [str(x) for x in (corpo.get("series") or []) if x]
    sops = [str(x) for x in (corpo.get("sops") or []) if x]
    if sops and len(series) != 1:
        raise ValueError("imagens: diga de qual série (uma)")
    do_exame = {x.series_uid for x in c.repo.series_for_study(study)}
    if any(x not in do_exame for x in series):
        raise ValueError("série de outro exame")
    extras = []
    if corpo.get("objetos"):
        # as medidas e as imagens-chave feitas até agora viram GSPS e KO no exame e vão juntas
        from ipe.exporter import fim_leitura as FL
        antes = FL.antes(c.repo, study)
        try:
            FL.gravar_ko_gsps(c.repo, c.storage, study, {"ko": True, "gsps": True})
        except Exception:  # noqa: BLE001
            log.exception("KO/GSPS do envio pelo navegador")
        extras = sorted(FL.antes(c.repo, study) - antes)
    info = c.repo.study_info(study) or {}
    rotulo = f"{info.get('patient_name', '')} — {info.get('description', '')}".strip(" —")
    jobs = []
    if sops:
        n = len(sops)
        jobs.append(net.send(no, ident, [study], f"{rotulo} ({n} imagem(ns))", series, sops,
                             dono=s.username))
        if extras:
            jobs.append(net.send(no, ident, [study], f"{rotulo} (medidas e imagens-chave)", extras, dono=s.username))
    else:
        todas = (series + [x for x in extras if x not in series]) if series else None
        quantas = f" ({len(series)} série(s))" if series else ""
        jobs.append(net.send(no, ident, [study], f"{rotulo}{quantas}", todas, dono=s.username))
    c.repo.audit("enviar", f"{no['name']}: {rotulo} — pelo navegador", user=s.username, study_uid=study)
    return {"ok": True, "envios": [_job(j) for j in jobs], "objetos": len(extras)}
