"""Banco pessoal × compartilhado (0.99.27, etapa 3 do plano do modo de uso).

Pedido dele: *"banco de dados compartilhado e 'do meu usuário' [...] como se fosse listas. clicando
com o botão direito (mover para bd compartilhado, compartilhar com: selecionar usuários, mover para
bd pessoal)"*. Decisões: o administrador vê o banco dos outros (cada exame pessoal alheio que ele abre
fica no registro de acesso); laudos, medidas e anotações acompanham o exame.

O exame existe **uma vez só** no banco do computador; "pessoal" é uma marca (`Study.dono`). Mover de
um banco para outro não copia imagem. E, num mesmo computador, pessoal **esconde dentro do programa**,
mas não protege o arquivo: quem abrir a pasta do banco pelo sistema vê as imagens.

Para onde vai um exame novo:
- chegou pela rede no AE de uma **identidade pessoal** (o "AE do Dr. Fulano") → banco pessoal do dono;
- chegou no AE do serviço → compartilhado;
- importado ou baixado do PACS por alguém → a escolha dele em "Exames que eu trago vão para"
  (`browser.novos_no_banco`, por usuário; de fábrica, compartilhado).
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

AVISO_LOCAL = ("No mesmo computador, “pessoal” esconde o exame dentro do programa, mas os arquivos continuam "
               "na pasta do banco: quem abrir a pasta pelo sistema vê as imagens.")
CHAVE_NOVOS = "browser.novos_no_banco"          # "compartilhado" | "meu" | "computador" (cada usuário)
BANCOS = {"visivel": "Tudo o que vejo", "meu": "Meu banco", "compartilhado": "Compartilhado",
          "comigo": "Compartilhados comigo"}


def dono_da_chegada(repo, meu_ae: str) -> str:
    """Exame recebido pela rede: o dono da identidade (AE) que a modalidade chamou, se for pessoal."""
    ae = str(meu_ae or "").strip().upper()
    if not ae or repo is None:
        return ""
    try:
        for i in repo.identities(todos=True):
            if str(i.get("ae_title") or "").strip().upper() == ae:
                return str(i.get("dono") or "").strip()
    except Exception:  # noqa: BLE001
        log.exception("identidade da chegada")
    return ""


def dono_dos_novos(settings) -> str:
    """Exame que **eu** trago (importar, baixar do PACS): vai para o meu banco ou o compartilhado."""
    from ipe.auth import visibilidade as V
    v = V.visao_atual()
    if v is None or settings is None:
        return ""
    try:
        escolha = str(settings.get(CHAVE_NOVOS, "compartilhado") or "compartilhado")
    except Exception:  # noqa: BLE001
        escolha = "compartilhado"
    return v.usuario if escolha in ("meu", "computador") else ""


def fica_neste_computador(settings) -> bool:
    """0.99.28, modo cliente: o que eu importo vai para o meu banco **neste computador** (não sobe)."""
    try:
        return (str(settings.get("central.mode", "local") or "") == "client"
                and str(settings.get(CHAVE_NOVOS, "") or "") == "computador")
    except Exception:  # noqa: BLE001
        return False


def marcar_novos(repo, study_uids, dono: str) -> int:
    """Põe os exames **novos** no banco pessoal de `dono` (nada a fazer para o compartilhado)."""
    if not dono or not study_uids or repo is None:
        return 0
    try:
        n = repo.set_study_scope(list(study_uids), dono, "")
        log.info("%d exame(s) novo(s) no banco pessoal de %s", n, dono)
        return n
    except Exception:  # noqa: BLE001
        log.exception("marcar o banco dos exames novos")
        return 0


def precisa_registrar(info: dict | None) -> str:
    """Quem abre um exame pessoal de outro (o administrador): devolve o dono, para o registro de
    acesso; "" quando o exame é dele, compartilhado ou compartilhado com ele."""
    from ipe.auth import visibilidade as V
    v = V.visao_atual()
    if v is None or not info:
        return ""
    if V.visivel(info, v):
        return ""
    return str(info.get("dono") or "")


def rotulo_do_banco(row, visao=None) -> str:
    """Texto da coluna "Banco": Compartilhado / Meu / Meu + bia / de ana."""
    from ipe.auth import visibilidade as V
    v = visao if visao is not None else V.visao_atual()
    dono = str(getattr(row, "dono", "") or (row.get("dono", "") if isinstance(row, dict) else "") or "")
    outros = V.lista(getattr(row, "visivel_para", "") if not isinstance(row, dict) else row.get("visivel_para", ""))
    if not dono:
        return "Compartilhado"
    if v is not None and dono.lower() == v.usuario.lower():
        return "Meu" + (" + " + ", ".join(outros) if outros else "")
    return f"de {dono}" + (" + " + ", ".join(outros) if outros else "")
