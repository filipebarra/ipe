"""Onde rodar as IAs no Ipê cliente (0.100.100): no servidor central (padrão) ou neste computador.

Pedido dele (22/11/2026): *"como padrão deixar as IAs rodando no servidor, mas se o cliente quiser, marca que as IAs
rodem no cliente e depois vá para o servidor (automaticamente)"*. Decisões: o administrador trava pelo perfil (a
permissão `ia_local`); sem o pacote de IA neste computador, cai para o servidor.

- **Servidor** (padrão): a IA pedida no visualizador vai para a fila de IA do servidor (a mesma do Ipê Web); o
  resultado aparece no exame quando fica pronto.
- **Este computador**: roda aqui, com o pacote de IA daqui, e as séries geradas e os achados sobem sozinhos ao
  servidor.

Fora do modo cliente (banco próprio, servidor), a IA roda sempre aqui. Sem Qt.
"""
from __future__ import annotations

CHAVE = "ia.onde_cliente"            # "servidor" | "local"
SERVIDOR, LOCAL = "servidor", "local"


def cliente(repo) -> bool:
    """O Ipê é cliente de um servidor central (as imagens são do servidor)?"""
    return hasattr(repo, "client") and hasattr(repo, "upload_study")


def escolha(settings) -> str:
    try:
        v = str(settings.get(CHAVE, SERVIDOR) or SERVIDOR) if settings is not None else SERVIDOR
    except Exception:  # noqa: BLE001
        v = SERVIDOR
    return LOCAL if v == LOCAL else SERVIDOR


def pode_local(perms=None) -> bool:
    if perms is None:
        from ipe.auth import session as S
        return S.can("ia_local")
    return "ia_local" in set(perms)


def decidir(repo, settings, perms=None, instalado=None) -> tuple[str, str]:
    """(onde, aviso). `aviso` explica quando a escolha "este computador" não pôde valer."""
    if not cliente(repo):
        return LOCAL, ""
    if escolha(settings) != LOCAL:
        return SERVIDOR, ""
    if not pode_local(perms):
        return SERVIDOR, "o seu perfil não permite rodar as IAs neste computador — vai para o servidor"
    if instalado is None:
        from ipe.ai import totalseg as TS
        instalado = TS.instalado(settings)
    if not instalado:
        return SERVIDOR, "o pacote de IA não está instalado neste computador — vai para o servidor"
    return LOCAL, ""
