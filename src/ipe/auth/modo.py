"""Modo de uso do programa (0.99.25): só eu, várias pessoas neste computador, servidor ou cliente.

Pedido dele: *"sobre a instalação, queria facilitar. hoje sou obrigado a colocar nome, username e
senha. como vou distribuir, quero, na instalação ou primeiro uso, perguntar sobre o uso"* — e poder
trocar depois, no menu Usuários.

Por baixo, o modo junta duas chaves que já existiam:

| Modo | `central.mode` | `auth.mode` |
|---|---|---|
| Só eu (`um`) | local | single |
| Várias pessoas neste computador (`varios`) | local | multi |
| Este computador é o servidor (`servidor`) | server | multi |
| Conectar a um servidor (`cliente`) | client | — |

Até a 0.99.24 o modo "um usuário" só era escolhido pelo instalador do Windows; pelo `executar.bat`,
pelo portátil e no Linux o programa caía em "vários" e exigia criar o administrador.
"""
from __future__ import annotations

import getpass
import logging

log = logging.getLogger(__name__)

MODOS = {
    "um": "Só eu uso este computador",
    "varios": "Várias pessoas usam este computador",
    "servidor": "Este computador é o servidor do grupo",
    "cliente": "Conectar a um servidor do grupo",
}
CHAVE_CONFIRMADO = "auth.modo_confirmado"
CHAVE_PELO_SISTEMA = "auth.entrar_pelo_sistema"


def modo_atual(settings) -> str:
    central = str(settings.get("central.mode", "local") or "local")
    if central == "client":
        return "cliente"
    if central == "server":
        return "servidor"
    return "um" if str(settings.get("auth.mode", "multi")) == "single" else "varios"


def precisa_perguntar(settings, repo) -> bool:
    """Primeiro uso: ninguém escolheu o modo (nem o instalador) e não há usuário cadastrado. Quem já
    usa o programa com usuários não vê a pergunta: o modo dele é o que já está."""
    if bool(settings.get(CHAVE_CONFIRMADO, False)):
        return False
    if str(settings.get("central.mode", "local")) == "client":
        return False
    try:
        return repo.user_count() == 0
    except Exception:  # noqa: BLE001
        return False


def conta_do_sistema() -> str:
    """A conta do Windows/Linux de quem abriu o programa."""
    try:
        return getpass.getuser() or ""
    except Exception:  # noqa: BLE001
        return ""


def aplicar(settings, modo: str, *, auto_login: str | None = None, pelo_sistema: bool | None = None,
            porta: int | None = None, url: str | None = None, verificar_tls: bool | None = None) -> bool:
    """Grava o modo. Devolve True quando é preciso reabrir o programa (entrar ou sair do modo cliente:
    o banco que a janela usa muda)."""
    if modo not in MODOS:
        raise ValueError(f"modo desconhecido: {modo}")
    antes = modo_atual(settings)
    if modo == "cliente":
        settings.set("central.mode", "client")
        if url is not None:
            settings.set("central.url", url.strip())
        if verificar_tls is not None:
            settings.set("central.verify_tls", bool(verificar_tls))
    else:
        settings.set("central.mode", "server" if modo == "servidor" else "local")
        settings.set("auth.mode", "single" if modo == "um" else "multi")
        if modo == "servidor" and porta:
            settings.set("central.port", int(porta))
    if auto_login is not None:
        settings.set("auth.auto_login", auto_login)
    if pelo_sistema is not None:
        settings.set(CHAVE_PELO_SISTEMA, bool(pelo_sistema))
    settings.set(CHAVE_CONFIRMADO, True)
    settings.save()
    log.info("Modo de uso: %s → %s", antes, modo)
    return (antes == "cliente") != (modo == "cliente")


def sessao_sem_senha(auth, settings):
    """A sessão que entra sem a janela de login, ou None (pede usuário e senha).

    - **Só eu**: sem usuário cadastrado, entra com todas as permissões; com usuários, entra como o
      escolhido em "Entrar automaticamente como" ou, se houver um só ativo, como ele.
    - **Várias pessoas / servidor**: "entrar automaticamente como" (computador pessoal) e, com
      "entrar pela conta do sistema" ligado, o usuário ligado à conta do Windows/Linux de quem abriu.
    """
    from ipe.auth.session import UserSession
    if auth is None or getattr(auth, "remote", False) or settings is None:
        return None
    repo = getattr(auth, "repo", None)
    modo = modo_atual(settings)
    try:
        vazio = bool(auth.needs_first_admin())
    except Exception:  # noqa: BLE001
        vazio = False
    if modo == "um":
        if vazio:
            return UserSession()
        auto = str(settings.get("auth.auto_login", "") or "")
        if auto:
            s = auth.auto_session(auto)
            if s is not None:
                return s
        ativos = [u for u in (repo.users() if repo is not None else []) if u["active"]]
        if len(ativos) == 1:
            return auth.auto_session(ativos[0]["username"])
        return None
    if vazio:
        return None
    auto = str(settings.get("auth.auto_login", "") or "")
    if auto and hasattr(auth, "auto_session"):
        s = auth.auto_session(auto)
        if s is not None:
            return s
    if bool(settings.get(CHAVE_PELO_SISTEMA, False)) and repo is not None:
        u = repo.user_by_conta_sistema(conta_do_sistema())
        if u is not None:
            s = auth.auto_session(u["username"])
            if s is not None:
                log.info("Entrada pela conta do sistema: %s", u["username"])
                try:
                    repo.audit("login_pelo_sistema", conta_do_sistema(), user=u["username"])
                except Exception:  # noqa: BLE001
                    pass
                return s
    return None
