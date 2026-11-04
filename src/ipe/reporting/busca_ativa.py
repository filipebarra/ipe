"""Busca ativa (0.99.51, onda B8 do plano ViewerHub/Eden): o laudo BI-RADS 0 ou 3 gera o pedido de chamar
a paciente de volta.

Pedido dele (04/11/2026): *"faça toda a onda B"* — B8 é "BI-RADS que gera a busca ativa (BI-RADS 3 e 0)".

Regras:
- ao **assinar** um laudo com formulário BI-RADS, a categoria final (`birads.final_category`) decide: as
  categorias da configuração (de fábrica 0 → 30 dias e 3 → 180 dias) geram um pedido com prazo = data da
  assinatura + dias;
- a **retificação** substitui o pedido aberto do mesmo exame; se a categoria nova não pede busca, o pedido
  aberto é encerrado com o motivo;
- **retornou** sozinho: quando chega ao banco um exame de mama do mesmo paciente (MG; US ou RM com "mama"
  ou "breast" na descrição) com data igual ou posterior e adicionado depois do pedido;
- estados: pendente → contatado / agendado → retornou ou encerrado; cada passo vai ao histórico.

A configuração mora nas configurações centrais (`AppSetting`, chave `busca_ativa`): no servidor central vale
para todas as estações.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from ipe.reporting import birads as BR

CHAVE = "busca_ativa"
PADRAO = {"ligada": True, "dias": {"0": 30, "3": 180}}
ESTADOS = {"pendente": "Pendente", "contatado": "Contatada", "agendado": "Agendada", "retornou": "Retornou",
           "encerrado": "Encerrada"}
ABERTOS = ("pendente", "contatado", "agendado")
MOTIVOS = {"0": "BI-RADS 0 — avaliação adicional", "3": "BI-RADS 3 — controle em curto intervalo",
           "4A": "BI-RADS 4A — aguardando o histopatológico", "4B": "BI-RADS 4B — aguardando o histopatológico",
           "4C": "BI-RADS 4C — aguardando o histopatológico", "5": "BI-RADS 5 — aguardando o histopatológico"}
#: categorias que a configuração oferece, com os dias sugeridos quando ligadas
OPCOES = (("0", 30), ("3", 180), ("4A", 30), ("4B", 30), ("4C", 30), ("5", 30))
MODALIDADE_DO_TIPO = {"mg": "MG", "us": "US", "mri": "MR"}
_MAMA = re.compile(r"MAMA|MAMAS|BREAST|MAMOGR|MAMMO", re.I)


def config(repo) -> dict:
    cfg = {}
    try:
        cfg = repo.get_app_setting(CHAVE, None) or {}
    except Exception:  # noqa: BLE001
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    dias = {str(k): int(v) for k, v in (cfg.get("dias") or PADRAO["dias"]).items() if str(v).strip()}
    return {"ligada": bool(cfg.get("ligada", PADRAO["ligada"])), "dias": dias}


def _data(s: str) -> date | None:
    try:
        return datetime.strptime(str(s or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        try:
            return datetime.strptime(str(s or "")[:8], "%Y%m%d").date()
        except ValueError:
            return None


def categoria_do_laudo(rep: dict) -> tuple[str, str]:
    """(categoria final, tipo mg/us/mri) — ("", "") quando o laudo não tem formulário BI-RADS."""
    f = (rep or {}).get("fields") or {}
    if not isinstance(f, dict) or not (f.get("kind") or f.get("findings") or f.get("cat_right")
                                       or f.get("cat_left") or f.get("category")):
        return "", ""
    return BR.final_category(f), str(f.get("kind") or "mg")


def pedido_do_laudo(rep: dict, info: dict | None, cfg: dict, hoje: date | None = None) -> dict | None:
    """O pedido de busca ativa que este laudo assinado gera, ou None."""
    if not cfg.get("ligada", True):
        return None
    cat, tipo = categoria_do_laudo(rep)
    if cat not in cfg.get("dias", {}):
        return None
    base = _data(rep.get("signed_at") or "") or hoje or date.today()
    prazo = base + timedelta(days=int(cfg["dias"][cat]))
    info = info or {}
    return {"study_uid": rep.get("study_uid") or info.get("study_uid", ""), "report_id": rep.get("id"),
            "patient_id": info.get("patient_id", ""), "patient_name": info.get("patient_name", ""),
            "study_date": info.get("study_date", ""), "modalidade": MODALIDADE_DO_TIPO.get(tipo, "MG"),
            "categoria": cat, "motivo": MOTIVOS.get(cat, f"BI-RADS {cat}"), "prazo": prazo.strftime("%Y%m%d"),
            "criado_por": rep.get("signed_by", "")}


def registrar_do_laudo(repo, rep: dict, info: dict | None = None) -> str:
    """Depois de assinar: cria ou troca o pedido do exame. Devolve a frase para a barra de status ("" = nada)."""
    if not rep:
        return ""
    cat, _tipo = categoria_do_laudo(rep)
    if not cat:
        return ""
    if info is None:
        try:
            info = repo.study_info(rep.get("study_uid", "")) or {}
        except Exception:  # noqa: BLE001
            info = {}
    ped = pedido_do_laudo(rep, info, config(repo))
    if ped is None:
        n = repo.encerrar_buscas_do_exame(rep.get("study_uid", ""), f"retificação: BI-RADS {cat}",
                                          rep.get("signed_by", ""))
        return f"busca ativa encerrada ({n})" if n else ""
    repo.criar_busca_ativa(ped)
    return f"busca ativa: {ped['motivo']}, até {fmt(ped['prazo'])}"


def fmt(d: str) -> str:
    d = str(d or "")
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 and d.isdigit() else d


def situacao(item: dict, hoje: date | None = None) -> tuple[str, bool]:
    """(texto do prazo, atrasado?) — "faltam 12 dias", "vence hoje", "atrasada 3 dias"."""
    if item.get("estado") not in ABERTOS:
        return ESTADOS.get(item.get("estado", ""), item.get("estado", "")), False
    p = _data(item.get("prazo", ""))
    if p is None:
        return "", False
    dd = (p - (hoje or date.today())).days
    if dd > 1:
        return f"faltam {dd} dias", False
    if dd == 1:
        return "vence amanhã", False
    if dd == 0:
        return "vence hoje", False
    return ("atrasada 1 dia" if dd == -1 else f"atrasada {-dd} dias"), True


def exame_de_retorno(st: dict) -> bool:
    """Exame que conta como retorno da busca: mamografia, ou US/RM de mama."""
    mods = str(st.get("modalities") or "").upper()
    if "MG" in mods.split("\\") or mods == "MG":
        return True
    if any(m in mods for m in ("US", "MR")):
        return bool(_MAMA.search(str(st.get("description") or "")))
    return False


def linha(acao: str, usuario: str = "", quando: datetime | None = None) -> str:
    q = (quando or datetime.now()).strftime("%d/%m/%Y %H:%M")
    return f"{q} {usuario or '—'}: {acao}"


def csv_das_buscas(itens: list[dict], hoje: date | None = None) -> str:
    cab = ["Paciente", "ID", "Data do exame", "Modalidade", "BI-RADS", "Motivo", "Prazo", "Situação", "Estado"]
    out = [";".join(cab)]
    for it in itens:
        sit, _a = situacao(it, hoje)
        out.append(";".join(str(x).replace(";", ",") for x in (
            it.get("patient_name", ""), it.get("patient_id", ""), fmt(it.get("study_date", "")),
            it.get("modalidade", ""), it.get("categoria", ""), it.get("motivo", ""), fmt(it.get("prazo", "")),
            sit, ESTADOS.get(it.get("estado", ""), it.get("estado", "")))))
    return "\n".join(out) + "\n"
