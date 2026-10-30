"""Tela de login, criação do primeiro administrador e troca de senha."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QMessageBox, QVBoxLayout,
)

from ipe import APP_NAME, NOT_FOR_DIAGNOSIS, __version__
from ipe.auth.backend import AuthError
from ipe.auth.passwords import password_problem


class FirstAdminDialog(QDialog):
    """Primeira execução com usuários: cria o administrador."""

    def __init__(self, auth, parent=None):
        super().__init__(parent)
        self.auth = auth
        self.setWindowTitle(f"{APP_NAME} — primeiro acesso")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("<b>Crie o administrador do programa.</b><br>Ele cadastra os outros usuários "
                             "(médicos, residentes, técnicos) em Usuário → Usuários e permissões."))
        f = QFormLayout()
        self.user = QLineEdit("admin")
        self.name = QLineEdit(placeholderText="Nome completo")
        self.pw1 = QLineEdit(echoMode=QLineEdit.Password)
        self.pw2 = QLineEdit(echoMode=QLineEdit.Password)
        f.addRow("Usuário:", self.user)
        f.addRow("Nome:", self.name)
        f.addRow("Senha:", self.pw1)
        f.addRow("Repita a senha:", self.pw2)
        lay.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _ok(self) -> None:
        u, p = self.user.text().strip(), self.pw1.text()
        if not u:
            QMessageBox.warning(self, "Usuário", "Informe o nome de usuário.")
            return
        why = password_problem(p)
        if why or p != self.pw2.text():
            QMessageBox.warning(self, "Senha", why or "As senhas não conferem.")
            return
        try:
            self.auth.create_first_admin(u, self.name.text().strip() or u, p)
        except AuthError as e:
            QMessageBox.warning(self, "Usuário", str(e))
            return
        self.accept()


class LoginDialog(QDialog):
    def __init__(self, auth, settings=None, parent=None, where: str = ""):
        super().__init__(parent)
        self.auth, self.settings = auth, settings
        self.session = None
        self.setWindowTitle(f"{APP_NAME} {__version__} — entrar")
        lay = QVBoxLayout(self)
        head = QLabel(f"<h3>{APP_NAME}</h3><i>{NOT_FOR_DIAGNOSIS}</i>" + (f"<br>{where}" if where else ""))
        head.setTextFormat(Qt.RichText)
        lay.addWidget(head)
        f = QFormLayout()
        last = settings.get("auth.last_user", "") if settings is not None else ""
        self.user = QLineEdit(last)
        self.pw = QLineEdit(echoMode=QLineEdit.Password)
        f.addRow("Usuário:", self.user)
        f.addRow("Senha:", self.pw)
        lay.addLayout(f)
        self.msg = QLabel("")
        self.msg.setStyleSheet("color:#ff8080")
        lay.addWidget(self.msg)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Entrar")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        self.go_local = False
        if getattr(auth, "remote", False) and parent is None:
            b = bb.addButton("Usar sem o servidor (modo local)", QDialogButtonBox.ResetRole)
            b.clicked.connect(self._local)
        lay.addWidget(bb)
        (self.pw if last else self.user).setFocus()

    def _local(self) -> None:
        if QMessageBox.question(self, "Modo local", "Trabalhar só com o banco deste computador (sem o servidor "
                                "central)? Dá para voltar em Rede → Servidor central.") == QMessageBox.Yes:
            self.go_local = True
            self.reject()

    def _ok(self) -> None:
        try:
            s = self.auth.login(self.user.text().strip(), self.pw.text())
        except AuthError as e:
            self.msg.setText(str(e))
            self.pw.selectAll()
            self.pw.setFocus()
            return
        except Exception as e:  # noqa: BLE001 - rede, servidor fora do ar…
            self.msg.setText(f"Não foi possível entrar: {e}")
            return
        if getattr(s, "must_change", False):
            dlg = ChangePasswordDialog(self.auth, s, self, forced=True, old=self.pw.text())
            if dlg.exec() != QDialog.Accepted:
                return
        self.session = s
        if self.settings is not None:
            self.settings.set("auth.last_user", s.username)
            self.settings.save()
        self.accept()


class ChangePasswordDialog(QDialog):
    def __init__(self, auth, session, parent=None, forced: bool = False, old: str = ""):
        super().__init__(parent)
        self.auth, self.s = auth, session
        self.setWindowTitle("Alterar senha")
        lay = QVBoxLayout(self)
        if forced:
            lay.addWidget(QLabel("O administrador pediu que você troque a senha no primeiro acesso."))
        f = QFormLayout()
        self.old = QLineEdit(old, echoMode=QLineEdit.Password)
        self.pw1 = QLineEdit(echoMode=QLineEdit.Password)
        self.pw2 = QLineEdit(echoMode=QLineEdit.Password)
        if not forced:
            f.addRow("Senha atual:", self.old)
        f.addRow("Nova senha:", self.pw1)
        f.addRow("Repita:", self.pw2)
        lay.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _ok(self) -> None:
        why = password_problem(self.pw1.text())
        if why or self.pw1.text() != self.pw2.text():
            QMessageBox.warning(self, "Senha", why or "As senhas não conferem.")
            return
        try:
            self.auth.change_password(self.s, self.old.text(), self.pw1.text())
        except AuthError as e:
            QMessageBox.warning(self, "Senha", str(e))
            return
        QMessageBox.information(self, "Senha", "Senha alterada.")
        self.accept()


def single_user(auth, settings) -> bool:
    """Este computador está em modo de um usuário só e ainda não tem ninguém cadastrado?

    O modo é escolhido na instalação. Ele **não desliga** o sistema de usuários: no dia em que
    existir um usuário cadastrado, o login volta a ser pedido — o que faz a decisão ser
    reversível sem nenhuma outra chave escondida.
    """
    if auth is None or getattr(auth, "remote", False) or settings is None:
        return False
    if str(settings.get("auth.mode", "multi")) != "single":
        return False
    try:
        return bool(auth.needs_first_admin())
    except Exception:  # noqa: BLE001
        return False


def do_login(auth, settings, where: str = ""):
    """Primeiro acesso (cria o admin) e login. Devolve a sessão ou None (cancelado)."""
    if single_user(auth, settings):
        from ipe.auth.session import UserSession
        return UserSession()              # abre direto, com todas as permissões
    if not auth.remote and auth.needs_first_admin():
        if FirstAdminDialog(auth).exec() != QDialog.Accepted:
            return None
    auto = settings.get("auth.auto_login", "") if settings is not None else ""
    if auto and not auth.remote and hasattr(auth, "auto_session"):
        s = auth.auto_session(auto)
        if s is not None:
            return s
    dlg = LoginDialog(auth, settings, where=where)
    if dlg.exec() != QDialog.Accepted:
        return None
    return dlg.session
