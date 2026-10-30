"""Onde o login é conferido: banco local ou servidor central (modo cliente)."""

from __future__ import annotations

from ipe.auth.permissions import permissions_for
from ipe.auth.session import UserSession


class AuthError(Exception):
    pass


class LocalAuth:
    """Usuários no banco deste computador (modo local e o próprio servidor central)."""

    remote = False

    def __init__(self, repo):
        self.repo = repo

    def needs_first_admin(self) -> bool:
        return self.repo.user_count() == 0

    def create_first_admin(self, username: str, full_name: str, password: str) -> None:
        if not self.needs_first_admin():
            raise AuthError("Já existem usuários cadastrados.")
        self.repo.save_user({"username": username, "full_name": full_name, "role": "admin",
                             "active": True, "password": password})

    def login(self, username: str, password: str) -> UserSession:
        u = self.repo.authenticate(username, password)
        if u is None:
            raise AuthError("Usuário ou senha incorretos (ou usuário desativado).")
        s = UserSession(username=u["username"], full_name=u["full_name"], role=u["role"], user_id=u["id"],
                        perms=permissions_for(u["role"], self.repo))
        s.must_change = u.get("must_change", False)
        return s

    def auto_session(self, username: str) -> UserSession | None:
        """Entrada automática configurada pelo administrador neste computador (modo local)."""
        u = self.repo.user_by_name(username)
        if u is None or not u["active"]:
            return None
        return UserSession(username=u["username"], full_name=u["full_name"], role=u["role"], user_id=u["id"],
                           perms=permissions_for(u["role"], self.repo))

    def user_by_name(self, username: str):
        return self.repo.user_by_name(username)

    def prefs(self, s: UserSession) -> dict:
        return self.repo.user_prefs(s.user_id) if s.user_id else {}

    def save_prefs(self, s: UserSession, prefs: dict) -> None:
        if s.user_id:
            self.repo.save_user_prefs(s.user_id, prefs)

    def change_password(self, s: UserSession, old: str, new: str) -> None:
        if self.repo.authenticate(s.username, old) is None:
            raise AuthError("A senha atual não confere.")
        self.repo.set_password(s.user_id, new)


class RemoteAuth:
    """Login conferido no servidor central (modo cliente)."""

    remote = True

    def __init__(self, client):
        self.client = client

    def needs_first_admin(self) -> bool:
        return False

    def login(self, username: str, password: str) -> UserSession:
        from ipe.central.remote import Unauthorized
        try:
            info = self.client.login(username, password)
        except Unauthorized as e:
            raise AuthError(str(e) or "Usuário ou senha incorretos.") from None
        s = UserSession(username=info["username"], full_name=info.get("full_name", ""), role=info["role"],
                        user_id=info.get("user_id"), perms=set(info.get("perms") or []), token=info["token"])
        s.must_change = bool(info.get("must_change"))
        return s

    def prefs(self, s: UserSession) -> dict:
        try:
            return self.client.rpc("my_prefs") or {}
        except Exception:  # noqa: BLE001
            return {}

    def save_prefs(self, s: UserSession, prefs: dict) -> None:
        self.client.rpc("save_my_prefs", prefs)

    def change_password(self, s: UserSession, old: str, new: str) -> None:
        from ipe.central.remote import RemoteError
        try:
            self.client.rpc("change_my_password", old, new)
        except RemoteError as e:
            raise AuthError(str(e)) from None
