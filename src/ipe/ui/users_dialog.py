"""Usuários e permissões (administrador): cadastro, perfis e registro de acesso."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QTabWidget, QVBoxLayout, QWidget,
)

from ipe.auth import session as S
from ipe.auth.passwords import password_problem
from ipe.auth.permissions import PERMISSIONS, ROLES, role_permissions
from ipe.ui.tabelas import colunas_ajustaveis

ACTIONS = {"login": "Entrou", "logout": "Saiu", "abrir": "Abriu exame", "exportar": "Exportou",
           "anonimizar": "Exportou anonimizado", "enviar": "Enviou", "apagar": "Apagou", "imprimir": "Imprimiu",
           "baixar": "Baixou do PACS", "busca": "Buscou no PACS", "usuarios": "Alterou usuários",
           "importar": "Importou", "upload": "Enviou ao servidor",
           "abriu_exame_pessoal": "Abriu exame pessoal de outro", "viu_banco_de": "Abriu o banco pessoal de",
           "moveu_banco": "Mudou o banco do exame", "transferiu_banco": "Passou um banco pessoal",
           "login_pelo_sistema": "Entrou pela conta do sistema"}


def _fmt(dt) -> str:
    return dt.strftime("%d/%m/%Y %H:%M") if isinstance(dt, datetime) else (str(dt or "")[:16])


class UserEditDialog(QDialog):
    def __init__(self, user: dict | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Usuário")
        u = user or {"role": "medico", "active": True}
        self.data = dict(u)
        f = QFormLayout(self)
        self.username = QLineEdit(u.get("username", ""))
        self.username.setEnabled(user is None)
        self.full_name = QLineEdit(u.get("full_name", ""))
        self.role = QComboBox()
        for k, name in ROLES.items():
            self.role.addItem(name, k)
        self.role.setCurrentIndex(max(0, self.role.findData(u.get("role", "medico"))))
        self.active = QCheckBox("Ativo (pode entrar)")
        self.active.setChecked(bool(u.get("active", True)))
        self.pw = QLineEdit(echoMode=QLineEdit.Password)
        self.pw.setPlaceholderText("obrigatória" if user is None else "deixe vazio para manter")
        self.must = QCheckBox("Pedir para trocar a senha no próximo acesso")
        self.must.setChecked(user is None or bool(u.get("must_change")))
        # 0.99.25: a conta do Windows/Linux que entra como este usuário sem digitar senha
        from ipe.auth import modo as MODO
        self.conta = QLineEdit(u.get("conta_sistema", "") or "", placeholderText="vazio = sempre pede a senha")
        self.conta.setToolTip("Com \u201centrar com a conta do sistema\u201d ligado (Modo de uso), quem abrir o "
                              "programa com esta conta do Windows/Linux entra direto como este usuário.")
        b_conta = QPushButton(f"Usar a deste computador ({MODO.conta_do_sistema() or '?'})")
        b_conta.clicked.connect(lambda: self.conta.setText(MODO.conta_do_sistema()))
        linha_conta = QHBoxLayout()
        linha_conta.addWidget(self.conta, 1)
        linha_conta.addWidget(b_conta)
        for lab, w in (("Usuário:", self.username), ("Nome:", self.full_name), ("Perfil:", self.role),
                       ("", self.active), ("Senha:", self.pw), ("", self.must)):
            f.addRow(lab, w)
        f.addRow("Conta do sistema:", linha_conta)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        f.addRow(bb)
        self._new = user is None

    def _ok(self) -> None:
        if not self.username.text().strip():
            QMessageBox.warning(self, "Usuário", "Informe o nome de usuário.")
            return
        pw = self.pw.text()
        if self._new or pw:
            why = password_problem(pw)
            if why:
                QMessageBox.warning(self, "Senha", why)
                return
        self.data.update({"username": self.username.text().strip(), "full_name": self.full_name.text().strip(),
                          "role": self.role.currentData(), "active": self.active.isChecked(),
                          "must_change": self.must.isChecked(), "conta_sistema": self.conta.text().strip()})
        if pw:
            self.data["password"] = pw
        else:
            self.data.pop("password", None)
        self.accept()


class UsersDialog(QDialog):
    def __init__(self, repo, settings=None, parent=None, local_mode: bool = True):
        super().__init__(parent)
        self.repo, self.settings = repo, settings
        self.setWindowTitle("Usuários e permissões")
        self.resize(900, 600)
        tabs = QTabWidget()
        tabs.addTab(self._users_tab(), "Usuários")
        tabs.addTab(self._roles_tab(), "Perfis e permissões")
        tabs.addTab(self._log_tab(), "Registro de acesso")
        if local_mode and settings is not None:
            tabs.addTab(self._machine_tab(), "Este computador")
        self.tabs = tabs
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    # ------------------------------------------------------------ usuários
    def _users_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.t_users = QTableWidget(0, 5)
        self.t_users.setHorizontalHeaderLabels(["Usuário", "Nome", "Perfil", "Situação", "Último acesso"])
        self.t_users.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.t_users.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.t_users.verticalHeader().setVisible(False)
        self.t_users.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.t_users.doubleClicked.connect(lambda _i: self.edit_user())
        self.faixa_modo = QLabel()
        self.faixa_modo.setWordWrap(True)
        self.faixa_modo.setStyleSheet(
            "background:#4a3c14; color:#f0dca0; padding:6px; border-radius:4px;")
        self.faixa_modo.setVisible(False)
        lay.addWidget(self.faixa_modo)
        lay.addWidget(self.t_users, 1)
        colunas_ajustaveis(self.t_users)
        row = QHBoxLayout()
        for text, fn in (("Novo…", lambda: self.edit_user(new=True)), ("Editar…", self.edit_user),
                         ("Redefinir senha…", self.reset_password), ("Ativar / desativar", self.toggle_active),
                         ("Excluir", self.delete_user)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.fill_users()
        return w

    def fill_users(self) -> None:
        users = self.repo.users()
        self.t_users.setRowCount(len(users))
        self._atualiza_faixa_modo()
        for r, u in enumerate(users):
            vals = [u["username"], u["full_name"], ROLES.get(u["role"], u["role"]),
                    "ativo" if u["active"] else "desativado", _fmt(u["last_login"])]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setData(Qt.UserRole, u["id"])
                self.t_users.setItem(r, c, it)

    def _selected(self) -> dict | None:
        r = self.t_users.currentRow()
        if r < 0 or self.t_users.item(r, 0) is None:
            return None
        uid = self.t_users.item(r, 0).data(Qt.UserRole)
        return next((u for u in self.repo.users() if u["id"] == uid), None)

    def _admins_left(self, without_id: int) -> int:
        return len([u for u in self.repo.users() if u["role"] == "admin" and u["active"] and u["id"] != without_id])

    def edit_user(self, new: bool = False) -> None:
        u = None if new else self._selected()
        if not new and u is None:
            return
        dlg = UserEditDialog(u, self)
        if dlg.exec() != QDialog.Accepted:
            return
        d = dlg.data
        if u is not None and u["role"] == "admin" and (d["role"] != "admin" or not d["active"]) \
                and self._admins_left(u["id"]) == 0:
            QMessageBox.warning(self, "Usuários", "Precisa sobrar pelo menos um administrador ativo.")
            return
        try:
            self.repo.save_user({k: v for k, v in d.items() if k not in ("created", "last_login")})
        except ValueError as e:
            QMessageBox.warning(self, "Usuários", str(e))
            return
        S.audit(self.repo, "usuarios", f"{'criou' if new else 'editou'} {d['username']} ({d['role']})")
        self.fill_users()

    def reset_password(self) -> None:
        u = self._selected()
        if u is None:
            return
        from PySide6.QtWidgets import QInputDialog
        pw, ok = QInputDialog.getText(self, "Redefinir senha", f"Nova senha de {u['username']}:",
                                      QLineEdit.Password)
        if not ok:
            return
        why = password_problem(pw)
        if why:
            QMessageBox.warning(self, "Senha", why)
            return
        self.repo.set_password(u["id"], pw, True)
        S.audit(self.repo, "usuarios", f"redefiniu a senha de {u['username']}")
        QMessageBox.information(self, "Senha", "Senha redefinida; o usuário vai trocá-la no próximo acesso.")

    def toggle_active(self) -> None:
        u = self._selected()
        if u is None:
            return
        if u["active"] and u["role"] == "admin" and self._admins_left(u["id"]) == 0:
            QMessageBox.warning(self, "Usuários", "Precisa sobrar pelo menos um administrador ativo.")
            return
        self.repo.save_user({"id": u["id"], "username": u["username"], "active": not u["active"]})
        S.audit(self.repo, "usuarios", f"{'desativou' if u['active'] else 'ativou'} {u['username']}")
        self.fill_users()

    def delete_user(self) -> None:
        u = self._selected()
        if u is None:
            return
        if u["username"] == S.get().username:
            QMessageBox.warning(self, "Usuários", "Você não pode excluir o próprio usuário.")
            return
        if u["role"] == "admin" and self._admins_left(u["id"]) == 0:
            QMessageBox.warning(self, "Usuários", "Precisa sobrar pelo menos um administrador ativo.")
            return
        if QMessageBox.question(self, "Excluir", f"Excluir o usuário {u['username']}? (o registro de acesso "
                                "continua; para só bloquear, use Ativar/desativar)") != QMessageBox.Yes:
            return
        self.repo.delete_user(u["id"])
        S.audit(self.repo, "usuarios", f"excluiu {u['username']}")
        self.fill_users()

    def _atualiza_faixa_modo(self) -> None:
        """Explica o modo de um usuário só — e como sair dele, que é cadastrar alguém."""
        if self.settings is None or not hasattr(self, "faixa_modo"):
            return
        um_so = str(self.settings.get("auth.mode", "multi")) == "single" and \
            str(self.settings.get("central.mode", "local")) == "local"
        self.faixa_modo.setVisible(um_so)
        if um_so:
            self.faixa_modo.setText(
                "Modo de uso: \u201cSó eu uso este computador\u201d — o programa abre sem pedir login. Para que "
                "cada pessoa entre com o seu usuário e senha, troque para \u201cVárias pessoas\u201d em "
                "Configurações ▸ Usuários ▸ Modo de uso.")

    # ------------------------------------------------------------ perfis
    def _roles_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Marque o que cada perfil pode fazer. O administrador sempre pode tudo."))
        roles = list(ROLES)
        self.t_roles = QTableWidget(len(PERMISSIONS), len(roles))
        self.t_roles.setHorizontalHeaderLabels([ROLES[r] for r in roles])
        self.t_roles.setVerticalHeaderLabels(list(PERMISSIONS.values()))
        self.t_roles.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        colunas_ajustaveis(self.t_roles)
        table = role_permissions(self.repo)
        for r, perm in enumerate(PERMISSIONS):
            for c, role in enumerate(roles):
                it = QTableWidgetItem()
                flags = Qt.ItemIsUserCheckable | Qt.ItemIsEnabled
                if role == "admin":
                    flags = Qt.ItemIsUserCheckable
                it.setFlags(flags)
                it.setCheckState(Qt.Checked if perm in table[role] else Qt.Unchecked)
                self.t_roles.setItem(r, c, it)
        lay.addWidget(self.t_roles, 1)
        row = QHBoxLayout()
        b = QPushButton("Salvar permissões")
        b.clicked.connect(self.save_roles)
        row.addWidget(b)
        b2 = QPushButton("Restaurar o padrão")
        b2.clicked.connect(self.reset_roles)
        row.addWidget(b2)
        row.addStretch(1)
        lay.addLayout(row)
        return w

    def roles_table(self) -> dict[str, list[str]]:
        out = {}
        for c, role in enumerate(ROLES):
            if role == "admin":
                continue
            out[role] = [perm for r, perm in enumerate(PERMISSIONS)
                         if self.t_roles.item(r, c).checkState() == Qt.Checked]
        return out

    def save_roles(self) -> None:
        self.repo.set_app_setting("roles", self.roles_table())
        S.audit(self.repo, "usuarios", "alterou as permissões dos perfis")
        QMessageBox.information(self, "Permissões", "Permissões salvas (valem no próximo login de cada usuário).")

    def reset_roles(self) -> None:
        self.repo.set_app_setting("roles", None)
        table = role_permissions(None)
        for r, perm in enumerate(PERMISSIONS):
            for c, role in enumerate(ROLES):
                self.t_roles.item(r, c).setCheckState(Qt.Checked if perm in table[role] else Qt.Unchecked)

    # ------------------------------------------------------------ registro
    def _log_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        self.f_user = QComboBox()
        self.f_user.addItem("Todos os usuários", "")
        for u in self.repo.users():
            self.f_user.addItem(u["username"], u["username"])
        self.f_action = QComboBox()
        self.f_action.addItem("Todas as ações", "")
        for k, v in ACTIONS.items():
            self.f_action.addItem(v, k)
        self.f_text = QLineEdit(placeholderText="texto (paciente, nó, arquivo…)")
        self.f_days = QSpinBox(minimum=1, maximum=3650, value=30, suffix=" dias")
        for wdg in (self.f_user, self.f_action, self.f_text, QLabel("últimos"), self.f_days):
            row.addWidget(wdg)
        b = QPushButton("Filtrar")
        b.clicked.connect(self.fill_log)
        row.addWidget(b)
        b2 = QPushButton("Exportar CSV…")
        b2.clicked.connect(self.export_log)
        row.addWidget(b2)
        lay.addLayout(row)
        self.t_log = QTableWidget(0, 6)
        self.t_log.setHorizontalHeaderLabels(["Data/hora", "Usuário", "Ação", "Detalhe", "Exame", "Computador"])
        self.t_log.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.t_log.verticalHeader().setVisible(False)
        self.t_log.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        lay.addWidget(self.t_log, 1)
        colunas_ajustaveis(self.t_log)
        self.fill_log()
        return w

    def log_rows(self) -> list[dict]:
        return self.repo.access_log(limit=2000, user=self.f_user.currentData(), action=self.f_action.currentData(),
                                    text=self.f_text.text().strip(),
                                    since=datetime.now() - timedelta(days=self.f_days.value()))

    def fill_log(self) -> None:
        rows = self.log_rows()
        self.t_log.setRowCount(len(rows))
        for r, e in enumerate(rows):
            for c, v in enumerate((_fmt(e["at"]), e["user"], ACTIONS.get(e["action"], e["action"]), e["detail"],
                                   e["study_uid"], e["host"])):
                self.t_log.setItem(r, c, QTableWidgetItem(str(v)))

    def export_log(self) -> None:
        path, _f = QFileDialog.getSaveFileName(self, "Exportar registro", "registro_de_acesso.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["data_hora", "usuario", "acao", "detalhe", "exame", "computador"])
            for e in self.log_rows():
                w.writerow([_fmt(e["at"]), e["user"], e["action"], e["detail"], e["study_uid"], e["host"]])

    # ------------------------------------------------------------ este computador
    def _machine_tab(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.auto = QComboBox()
        self.auto.addItem("Não (sempre pedir usuário e senha)", "")
        for u in self.repo.users():
            if u["active"]:
                self.auto.addItem(u["username"], u["username"])
        self.auto.setCurrentIndex(max(0, self.auto.findData(self.settings.get("auth.auto_login", ""))))
        self.auto.currentIndexChanged.connect(self._save_auto)
        f.addRow("Entrar automaticamente como:", self.auto)
        f.addRow(QLabel("<small>Só para computador pessoal: quem abrir o programa entra sem senha "
                        "com esse usuário.</small>"))
        return w

    def _save_auto(self) -> None:
        self.settings.set("auth.auto_login", self.auto.currentData())
        self.settings.save()
