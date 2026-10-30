"""Quem está usando o programa agora e o que pode fazer.

Sem login (testes, linha de comando) vale o usuário "sistema", com todas as permissões."""

from __future__ import annotations

from dataclasses import dataclass, field

from ipe.auth.permissions import PERMISSIONS, ROLES


@dataclass
class UserSession:
    username: str = "sistema"
    full_name: str = "Sistema"
    role: str = "admin"
    user_id: int | None = None
    perms: set[str] = field(default_factory=lambda: set(PERMISSIONS))
    token: str = ""                      # no modo cliente: token do servidor central

    def can(self, perm: str) -> bool:
        return perm in self.perms

    @property
    def role_name(self) -> str:
        return ROLES.get(self.role, self.role)

    @property
    def label(self) -> str:
        return f"{self.full_name or self.username} ({self.role_name})"


current = UserSession()


def set_current(s: UserSession) -> None:
    global current
    current = s


def get() -> UserSession:
    return current


def can(perm: str) -> bool:
    return current.can(perm)


def require(perm: str, parent=None, what: str = "") -> bool:
    """True se pode; senão avisa (se houver janela) e devolve False."""
    if current.can(perm):
        return True
    if parent is not None:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(parent, "Permissão", f"Seu perfil ({current.role_name}) não permite: "
                                f"{what or PERMISSIONS.get(perm, perm)}.")
    return False


def audit(repo, action: str, detail: str = "", study_uid: str = "") -> None:
    """Registro de acesso (quem, o quê, qual exame)."""
    if repo is None:
        return
    try:
        repo.audit(action, detail, user=current.username, study_uid=study_uid)
    except Exception:  # noqa: BLE001
        pass
