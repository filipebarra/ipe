"""Assistente de primeiro uso e Configurações ▸ Usuários ▸ Modo de uso (0.99.25).

A mesma janela serve às duas portas: no primeiro uso ela pergunta como o programa vai ser usado e já
cria o administrador quando precisa; pelo menu, mostra o modo de agora e deixa trocar. As regras
(o que cada modo grava e quem entra sem senha) estão em `ipe.auth.modo`.
"""
from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QRadioButton, QSpinBox, QVBoxLayout, QWidget,
)

from ipe import APP_NAME
from ipe.auth import modo as MODO
from ipe.auth.passwords import password_problem

log = logging.getLogger(__name__)

EXPLICA = {
    "um": "Abre direto, sem pedir usuário e senha. É o caso do computador pessoal, de casa ou do "
          "consultório. Dá para pôr senha depois, em Configurações ▸ Usuários.",
    "varios": "Cada pessoa entra com o seu usuário. O administrador cadastra os outros (médicos, "
              "residentes, técnicos) e o que cada perfil pode fazer.",
    "servidor": "Este computador guarda os exames, os usuários e as configurações do grupo, e atende "
                "os outros computadores da rede, que entram como clientes.",
    "cliente": "Este computador usa o banco e os usuários de um servidor do grupo. Os exames abertos "
               "ficam num cache local.",
}


class ModoDeUsoDialog(QDialog):
    def __init__(self, settings, repo, auth=None, parent=None, primeiro_uso: bool = False):
        super().__init__(parent)
        self.settings, self.repo, self.auth = settings, repo, auth
        self.primeiro_uso = primeiro_uso
        self.reabrir = False
        self.admin_criado = ""              # quem acabou de ser criado entra sem digitar a senha de novo
        self.setWindowTitle(f"{APP_NAME} — como o programa vai ser usado" if primeiro_uso else "Modo de uso")
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        topo = ("<b>Bem-vindo ao Ipê.</b> Como este computador vai usar o programa? Dá para trocar depois, "
                "em Configurações ▸ Usuários ▸ Modo de uso." if primeiro_uso else
                f"<b>Agora:</b> {MODO.MODOS[MODO.modo_atual(settings)]}.")
        t = QLabel(topo)
        t.setWordWrap(True)
        lay.addWidget(t)
        self.grupo = QButtonGroup(self)
        self.radios: dict[str, QRadioButton] = {}
        for chave, nome in MODO.MODOS.items():
            r = QRadioButton(nome)
            self.radios[chave] = r
            self.grupo.addButton(r)
            lay.addWidget(r)
        self.l_explica = QLabel()
        self.l_explica.setWordWrap(True)
        self.l_explica.setStyleSheet("color: gray")
        lay.addWidget(self.l_explica)

        self.usuarios = [u for u in (repo.users() if repo is not None else []) if u["active"]]
        self.tem_usuarios = bool(repo.user_count()) if repo is not None else False
        conta = MODO.conta_do_sistema()

        # só eu, com usuários já cadastrados: quem entra
        self.g_um = QGroupBox("Entrar como")
        fu = QFormLayout(self.g_um)
        self.c_auto = QComboBox()
        for u in self.usuarios:
            self.c_auto.addItem(f"{u['full_name'] or u['username']} ({u['username']})", u["username"])
        i = self.c_auto.findData(settings.get("auth.auto_login", "") or "")
        self.c_auto.setCurrentIndex(max(0, i))
        fu.addRow("Usuário:", self.c_auto)
        lay.addWidget(self.g_um)

        # administrador (vários / servidor, quando ainda não há ninguém)
        self.g_admin = QGroupBox("Administrador do programa")
        fa = QFormLayout(self.g_admin)
        self.e_nome = QLineEdit(placeholderText="Nome completo")
        self.e_user = QLineEdit("admin")
        self.e_pw1 = QLineEdit(echoMode=QLineEdit.Password)
        self.e_pw2 = QLineEdit(echoMode=QLineEdit.Password)
        fa.addRow("Nome:", self.e_nome)
        fa.addRow("Usuário:", self.e_user)
        fa.addRow("Senha:", self.e_pw1)
        fa.addRow("Repita a senha:", self.e_pw2)
        lay.addWidget(self.g_admin)
        self.cb_sistema = QCheckBox(f"Entrar com a conta do sistema ({conta or '?'}) sem digitar senha")
        self.cb_sistema.setToolTip("Quem abrir o programa com a conta do Windows/Linux ligada a um usuário entra "
                                   "direto como ele. A conta de cada usuário fica em Usuários e permissões.")
        self.cb_sistema.setChecked(bool(settings.get(MODO.CHAVE_PELO_SISTEMA, False)))
        lay.addWidget(self.cb_sistema)

        # servidor
        self.g_srv = QGroupBox("Servidor")
        fs = QFormLayout(self.g_srv)
        self.s_porta = QSpinBox(minimum=1, maximum=65535, value=int(settings.get("central.port", 8043) or 8043))
        fs.addRow("Porta:", self.s_porta)
        fs.addRow(QLabel("<small>Os clientes conectam em http://<b>IP deste computador</b>:porta. Certificado "
                         "HTTPS e o resto ficam em Configurações ▸ Rede ▸ Servidor central.</small>"))
        lay.addWidget(self.g_srv)

        # cliente
        self.g_cli = QGroupBox("Servidor do grupo")
        fc = QFormLayout(self.g_cli)
        self.e_url = QLineEdit(settings.get("central.url", "") or "", placeholderText="Ex.: http://10.0.0.5:8043")
        self.cb_tls = QCheckBox("Conferir o certificado HTTPS")
        self.cb_tls.setChecked(bool(settings.get("central.verify_tls", False)))
        linha = QHBoxLayout()
        b_testar = QPushButton("Testar")
        b_testar.clicked.connect(self.testar)
        self.l_teste = QLabel("")
        linha.addWidget(b_testar)
        linha.addWidget(self.l_teste, 1)
        fc.addRow("Endereço:", self.e_url)
        fc.addRow(self.cb_tls)
        fc.addRow(linha)
        lay.addWidget(self.g_cli)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Começar" if primeiro_uso else "Aplicar")
        if primeiro_uso:
            bb.button(QDialogButtonBox.Cancel).setText("Sair")
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        for r in self.radios.values():
            r.toggled.connect(self._mostrar)
        self.radios["um" if primeiro_uso and str(settings.get("auth.mode", "")) != "multi"
                    else MODO.modo_atual(settings)].setChecked(True)
        self._mostrar()

    # ------------------------------------------------------------ estado
    def escolhido(self) -> str:
        return next((k for k, r in self.radios.items() if r.isChecked()), "um")

    def _mostrar(self, *_a) -> None:
        m = self.escolhido()
        self.l_explica.setText(EXPLICA[m])
        self.g_um.setVisible(m == "um" and len(self.usuarios) > 1)
        self.g_admin.setVisible(m in ("varios", "servidor") and not self.tem_usuarios)
        self.cb_sistema.setVisible(m in ("varios", "servidor"))
        self.g_srv.setVisible(m == "servidor")
        self.g_cli.setVisible(m == "cliente")
        self.adjustSize()

    def testar(self) -> bool:
        from ipe.central.remote import RemoteClient, RemoteError
        try:
            info = RemoteClient(self.e_url.text().strip(), verify_tls=self.cb_tls.isChecked()).ping()
        except (RemoteError, ValueError, OSError) as e:
            self.l_teste.setText(f"<span style='color:#f88'>{e}</span>")
            return False
        self.l_teste.setText(f"<span style='color:#8f8'>OK: {info.get('app')} {info.get('version')} "
                             f"em {info.get('name')}</span>")
        return True

    # ------------------------------------------------------------ aplicar
    def _criar_admin(self) -> bool:
        u, p = self.e_user.text().strip(), self.e_pw1.text()
        if not u:
            QMessageBox.warning(self, "Usuário", "Informe o nome de usuário do administrador.")
            return False
        why = password_problem(p)
        if why or p != self.e_pw2.text():
            QMessageBox.warning(self, "Senha", why or "As senhas não conferem.")
            return False
        try:
            self.repo.save_user({"username": u, "full_name": self.e_nome.text().strip() or u, "role": "admin",
                                 "active": True, "password": p,
                                 "conta_sistema": MODO.conta_do_sistema() if self.cb_sistema.isChecked() else ""})
        except ValueError as e:
            QMessageBox.warning(self, "Usuário", str(e))
            return False
        self.admin_criado = u
        return True

    def aplicar(self) -> bool:
        m = self.escolhido()
        if m == "cliente" and not self.e_url.text().strip():
            QMessageBox.warning(self, "Servidor", "Informe o endereço do servidor do grupo.")
            return False
        if m in ("varios", "servidor") and not self.tem_usuarios:
            if not self._criar_admin():
                return False
            self.tem_usuarios = True
        auto = None
        if m == "um":
            auto = self.c_auto.currentData() if len(self.usuarios) > 1 else ""
        self.reabrir = MODO.aplicar(
            self.settings, m, auto_login=auto,
            pelo_sistema=self.cb_sistema.isChecked() if m in ("varios", "servidor") else None,
            porta=self.s_porta.value() if m == "servidor" else None,
            url=self.e_url.text() if m == "cliente" else None,
            verificar_tls=self.cb_tls.isChecked() if m == "cliente" else None)
        return True

    def aviso(self) -> str:
        """0.99.28: o que acontece com os exames nesta troca de modo."""
        donos = {}
        try:
            donos = self.repo.donos_de_exames() if self.repo is not None else {}
        except Exception:  # noqa: BLE001
            donos = {}
        return MODO.aviso_da_troca(MODO.modo_atual(self.settings), self.escolhido(), donos)

    def _ok(self) -> None:
        aviso = "" if self.primeiro_uso else self.aviso()
        if aviso and QMessageBox.question(self, "Modo de uso", aviso + "\n\nTrocar o modo?",
                                          QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        if not self.aplicar():
            return
        if self.reabrir and not self.primeiro_uso:
            QMessageBox.information(self, "Modo de uso", "Feche e abra o programa de novo para "
                                    + ("entrar como cliente do servidor do grupo." if self.escolhido() == "cliente"
                                       else "voltar a usar o banco deste computador."))
        self.accept()
