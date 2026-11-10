"""Fim da leitura (0.100.7): ao assinar o laudo, o que o Ipê fez no exame vai sozinho para o PACS.

Pedido do backlog (AW Server, grupo 1): "ao concluir o laudo, enviar automaticamente SR, KOS, estado e mapas ao
PACS". Ao assinar (no Ipê ou no navegador), com a opção ligada em Configurações ▸ Laudos ▸ Fim da leitura:

1. as imagens-chave viram um **KO** e as medidas/anotações um **GSPS** no exame (`exporter/ko_gsps.py`, o mesmo do
   botão "Gravar imagens-chave e anotações");
2. vão ao nó escolhido: o **laudo** desta assinatura (PDF encapsulado e SR), o **KO** e o **GSPS** recém-gravados e,
   se marcado, as **séries do Ipê** do exame (SEG das análises, mapas salvos, capturas) — o que o Ipê gravou, pelo
   fabricante "Ipe" ou pela marca "(Ipe)" na descrição.

As cópias que ficam só neste computador (sem implante, tabelas da segmentação) nunca vão, como no envio à mão.
Laudo, KO e GSPS de assinaturas anteriores também não: cada assinatura manda os seus. Sem Qt.
"""
from __future__ import annotations

import logging

from ipe import FABRICANTES_NOSSOS, MARCAS_NOSSAS

log = logging.getLogger(__name__)

CHAVE = "fim_leitura"
PADRAO = {"ligado": False, "destino": None, "laudo": True, "ko": True, "gsps": True, "ipe": True}
#: as categorias, na ordem da tela
CATEGORIAS = (("laudo", "O laudo (PDF e SR desta assinatura)"),
              ("ko", "As imagens-chave (KO)"),
              ("gsps", "As medidas e anotações (GSPS)"),
              ("ipe", "As séries do Ipê no exame (SEG das análises, mapas, capturas)"))


def config(settings) -> dict:
    try:
        v = settings.get(CHAVE, {}) if settings is not None else {}
    except Exception:  # noqa: BLE001
        v = {}
    return {**PADRAO, **(v if isinstance(v, dict) else {})}


def guardar(settings, cfg: dict) -> None:
    settings.set(CHAVE, {k: cfg.get(k, PADRAO[k]) for k in PADRAO})


def destino(repo, cfg: dict) -> dict | None:
    """O nó de destino (ativo), ou None."""
    nid = cfg.get("destino")
    if nid in (None, ""):
        return None
    try:
        no = repo.node(int(nid))
    except Exception:  # noqa: BLE001
        return None
    if not no or not no.get("active", True):
        return None
    return no


def _do_ipe(desc: str, aparelho: str) -> bool:
    d, a = (desc or "").strip(), (aparelho or "").strip().lower()
    return any(a.startswith(f.lower()) for f in FABRICANTES_NOSSOS) or d.endswith(MARCAS_NOSSAS)


def _categoria(modalidade: str, desc: str) -> str:
    m = (modalidade or "").upper()
    if m == "KO":
        return "ko"
    if m == "PR":
        return "gsps"
    if m == "DOC" or (m == "SR" and (desc or "").startswith("Laudo")):
        return "laudo"
    return "ipe"


def series_do_exame(repo, study_uid: str) -> list[dict]:
    """As séries do exame com o que importa aqui (modalidade, descrição, aparelho, oculta)."""
    from sqlalchemy import select
    from ipe.db.models import Series, Study
    with repo.db.session() as s:
        q = (select(Series.series_uid, Series.modality, Series.description, Series.device, Series.hidden)
             .join(Study).where(Study.study_uid == study_uid))
        return [{"uid": u, "modalidade": m or "", "descricao": d or "", "aparelho": a or "", "oculta": bool(h)}
                for u, m, d, a, h in s.execute(q)]


def antes(repo, study_uid: str) -> set[str]:
    """As séries que o exame já tinha (chamar antes de gravar o laudo, o KO e o GSPS)."""
    return {x["uid"] for x in series_do_exame(repo, study_uid)}


def _locais(repo, study_uid: str) -> set[str]:
    out: set[str] = set()
    try:
        from ipe.ai.totalseg import series_locais as seg_locais
        out |= seg_locais(repo, study_uid)
    except Exception:  # noqa: BLE001
        pass
    try:
        from ipe.automation.implante import series_locais
        out |= series_locais(repo, study_uid)
    except Exception:  # noqa: BLE001
        pass
    return out


def gravar_ko_gsps(repo, storage, study_uid: str, cfg: dict) -> list[str]:
    """O KO e o GSPS do exame, gravados agora (se pedidos e se houver o que gravar). Devolve as frases."""
    if not (cfg.get("ko") or cfg.get("gsps")) or storage is None:
        return []
    from ipe.exporter import ko_gsps as KG
    ko = KG.build_ko(repo, study_uid) if cfg.get("ko") else None
    gsps, n = KG.build_gsps(repo, study_uid) if cfg.get("gsps") else (None, 0)
    if ko is None and gsps is None:
        return []
    KG.gravar_no_exame(repo, storage, ko, gsps)
    msgs = []
    if ko is not None:
        msgs.append(f"{len(ko.ContentSequence)} imagem(ns)-chave (KO)")
    if gsps is not None:
        msgs.append(f"{n} medida(s)/anotação(ões) (GSPS)")
    return msgs


def escolher(repo, study_uid: str, novas: set[str], cfg: dict) -> list[str]:
    """As séries que vão ao PACS: o laudo, o KO e o GSPS **desta** leitura (as novas) e, se marcado, as séries do
    Ipê do exame que não estão ocultas. As que ficam só neste computador nunca vão."""
    locais = _locais(repo, study_uid)
    out = []
    for x in series_do_exame(repo, study_uid):
        if x["uid"] in locais or not _do_ipe(x["descricao"], x["aparelho"]):
            continue
        cat = _categoria(x["modalidade"], x["descricao"])
        if not cfg.get(cat):
            continue
        if cat in ("laudo", "ko", "gsps"):
            if x["uid"] not in novas:
                continue
        elif x["oculta"]:
            continue
        out.append(x["uid"])
    return out


def resumo(repo, study_uid: str, series: list[str]) -> str:
    cats: dict[str, int] = {}
    por_uid = {x["uid"]: x for x in series_do_exame(repo, study_uid)}
    for u in series:
        x = por_uid.get(u)
        if x:
            c = _categoria(x["modalidade"], x["descricao"])
            cats[c] = cats.get(c, 0) + 1
    nomes = {"laudo": "laudo", "ko": "imagens-chave", "gsps": "anotações", "ipe": "séries do Ipê"}
    return ", ".join(f"{nomes[c]} ({n})" for c, n in cats.items())


def enviar_direto(repo, settings, node: dict, study_uid: str, series: list[str]) -> tuple[int, int]:
    """Envia sem a fila do Ipê (para o servidor do site, que não tem a janela da rede). Devolve (enviados, falhas)."""
    files = repo.files_for_study(study_uid, series) if series else []
    if not files:
        return 0, 0
    cfg = dict(settings.get("dicom", {}) or {}) if settings is not None else {}
    timeout = int(cfg.get("timeout", 30))
    if str(node.get("kind", "dimse")) == "dicomweb":
        from ipe.network.dicomweb_client import DicomWebClient, WebTarget
        cli, t = DicomWebClient(timeout), WebTarget.build(node, timeout)
    else:
        from ipe.network.client import DicomClient, Target
        cli, t = DicomClient(timeout=timeout), Target.build(node, cfg.get("ae_title", "DICOMVIEWER"), None)
    return cli.store(t, files)
