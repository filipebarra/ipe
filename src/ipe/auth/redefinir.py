"""0.100.113: "Esqueci o usuário ou a senha" — redefinir a senha no Ipê de uso único deste computador.

Pedido dele (24/11/2026): *"um usuário instalou e esqueceu os dados de acesso. como resolver? (…) crie uma solução
para redefinir quando for o Ipê de uso único no PC"*.

- **Só eu uso este computador** (`modo um`): a janela de login mostra "Esqueci o usuário ou a senha…" — escolhe o
  usuário na lista e grava uma senha nova. Quem abriu o Ipê já está dentro da conta do Windows dona da pasta do banco
  (e poderia apagá-la): a senha aqui não protege nada além disso. Fica na auditoria, com a conta do sistema.
- **Várias pessoas, servidor**: a senha separa pessoas — a janela não redefine; quem resolve é um administrador
  (Usuários) ou, se ninguém lembra, `ipe-cli redefinir-senha` rodado neste computador (quem roda o comando tem acesso
  à pasta do banco).
- **Cliente**: a senha é do servidor central — fala com o administrador dele.

Sem Qt.
"""
from __future__ import annotations

from ipe.auth import modo as MODO
from ipe.auth.passwords import password_problem


def onde_redefinir(auth, settings) -> str:
    """"aqui" (a janela de login redefine), "admin" (local com várias pessoas ou servidor) ou "servidor" (cliente)."""
    if auth is None or getattr(auth, "remote", False):
        return "servidor"
    if settings is not None and MODO.modo_atual(settings) == "um":
        return "aqui"
    return "admin"


def usuarios(repo) -> list[dict]:
    """Os usuários para escolher (sem senha, claro): username, nome, perfil, ativo."""
    return [{"username": u["username"], "full_name": u.get("full_name") or "", "role": u.get("role") or "",
             "active": bool(u.get("active"))} for u in repo.users()]


def redefinir(repo, username: str, nova: str, quem: str = "", origem: str = "janela") -> dict:
    """Grava a senha nova (e reativa o usuário, se estava desativado). ValueError se não serve."""
    problema = password_problem(nova or "")
    if problema:
        raise ValueError(problema)
    u = repo.user_by_name(username or "")
    if u is None:
        raise ValueError("Usuário não encontrado.")
    repo.set_password(u["id"], nova, must_change=False)
    if not u.get("active"):
        repo.save_user({"id": u["id"], "username": u["username"], "active": True})
    try:
        repo.audit("senha_redefinida_neste_computador", f"pela {origem}; conta do sistema: {quem or '?'}",
                   user=u["username"])
    except Exception:  # noqa: BLE001
        pass
    return {"username": u["username"], "reativado": not u.get("active")}
