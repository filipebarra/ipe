"""0.99.25: modo de uso — assistente de primeiro uso, troca pelo menu e entrada pela conta do sistema.

Pedido dele: *"hoje sou obrigado a colocar nome, username e senha. como vou distribuir, quero, na
instalação ou primeiro uso, perguntar sobre o uso"*: só eu, várias pessoas, servidor — e poder trocar
depois no menu Usuários.
"""
import pytest
from PySide6.QtWidgets import QApplication

from ipe.auth import modo as MODO
from ipe.auth.backend import LocalAuth
from ipe.core.config import Settings
from ipe.ui.login import do_login


@pytest.fixture()
def base(env):
    paths, db, repo = env
    QApplication.instance() or QApplication([])
    return paths, repo, LocalAuth(repo), Settings(paths.settings_file)


def _dlg(repo, auth, cfg, primeiro=True):
    from ipe.ui.modo_de_uso import ModoDeUsoDialog
    return ModoDeUsoDialog(cfg, repo, auth, primeiro_uso=primeiro)


# ------------------------------------------------------------------ quando perguntar
def test_pergunta_so_no_primeiro_uso(base):
    _p, repo, auth, cfg = base
    assert MODO.precisa_perguntar(cfg, repo)
    MODO.aplicar(cfg, "um")
    assert not MODO.precisa_perguntar(cfg, repo)


def test_quem_ja_tem_usuarios_nao_ve_a_pergunta(base):
    _p, repo, auth, cfg = base
    auth.create_first_admin("filipe", "Filipe", "uma senha comprida")
    assert not MODO.precisa_perguntar(cfg, repo)


def test_o_instalador_ja_perguntou(base):
    paths, repo, _auth, _cfg = base
    from ipe.__main__ import main
    assert main(["set-mode", "single"]) == 0
    assert not MODO.precisa_perguntar(Settings(paths.settings_file), repo)


# ------------------------------------------------------------------ assistente
def test_so_eu_abre_sem_criar_ninguem(base):
    _p, repo, auth, cfg = base
    d = _dlg(repo, auth, cfg)
    assert d.radios["um"].isChecked()                         # a escolha que já vem marcada
    assert not d.g_admin.isVisibleTo(d)
    assert d.aplicar()
    assert MODO.modo_atual(cfg) == "um" and repo.user_count() == 0
    s = do_login(auth, cfg)                                   # nada de janela de login
    assert s is not None and s.can("configure")


def test_varias_pessoas_cria_o_administrador_e_liga_a_conta(base, monkeypatch):
    _p, repo, auth, cfg = base
    monkeypatch.setattr(MODO, "conta_do_sistema", lambda: "filipe.barra")
    d = _dlg(repo, auth, cfg)
    d.radios["varios"].setChecked(True)
    assert d.g_admin.isVisibleTo(d) and d.cb_sistema.isVisibleTo(d)
    d.e_nome.setText("Filipe")
    d.e_user.setText("filipe")
    d.e_pw1.setText("uma senha comprida")
    d.e_pw2.setText("outra")
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.warning", lambda *a, **k: None)
    assert not d.aplicar()                                    # senhas diferentes
    d.e_pw2.setText("uma senha comprida")
    d.cb_sistema.setChecked(True)
    assert d.aplicar()
    u = repo.user_by_name("filipe")
    assert u["role"] == "admin" and u["conta_sistema"] == "filipe.barra"
    assert MODO.modo_atual(cfg) == "varios" and cfg.get(MODO.CHAVE_PELO_SISTEMA)
    # quem abriu com a conta do Windows dele entra direto
    s = do_login(auth, cfg)
    assert s is not None and s.username == "filipe"


def test_conta_de_outro_ou_desligada_pede_a_senha(base, monkeypatch):
    _p, repo, auth, cfg = base
    repo.save_user({"username": "ana", "full_name": "Ana", "role": "medico", "active": True,
                    "password": "uma senha comprida", "conta_sistema": "ana"})
    MODO.aplicar(cfg, "varios", pelo_sistema=True)
    monkeypatch.setattr(MODO, "conta_do_sistema", lambda: "outro")
    assert MODO.sessao_sem_senha(auth, cfg) is None
    monkeypatch.setattr(MODO, "conta_do_sistema", lambda: "ANA")          # sem diferença de maiúsculas
    assert MODO.sessao_sem_senha(auth, cfg).username == "ana"
    MODO.aplicar(cfg, "varios", pelo_sistema=False)
    assert MODO.sessao_sem_senha(auth, cfg) is None
    repo.save_user({"id": repo.user_by_name("ana")["id"], "username": "ana", "active": False})
    MODO.aplicar(cfg, "varios", pelo_sistema=True)
    assert MODO.sessao_sem_senha(auth, cfg) is None                         # desativada não entra


def test_servidor_grava_a_porta_e_cliente_pede_o_endereco(base, monkeypatch):
    _p, repo, auth, cfg = base
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.warning", lambda *a, **k: None)
    d = _dlg(repo, auth, cfg)
    d.radios["cliente"].setChecked(True)
    assert d.g_cli.isVisibleTo(d) and not d.aplicar()                      # sem endereço
    d.e_url.setText("http://10.0.0.5:8043")
    assert d.aplicar() and d.reabrir and cfg.get("central.mode") == "client"
    assert cfg.get("central.url") == "http://10.0.0.5:8043"
    d2 = _dlg(repo, auth, cfg, primeiro=False)
    d2.radios["servidor"].setChecked(True)
    d2.s_porta.setValue(9043)
    d2.e_user.setText("admin")
    d2.e_pw1.setText("uma senha comprida")
    d2.e_pw2.setText("uma senha comprida")
    assert d2.aplicar() and d2.reabrir                                      # saiu do modo cliente
    assert cfg.get("central.mode") == "server" and int(cfg.get("central.port")) == 9043
    assert repo.user_by_name("admin")["role"] == "admin"


# ------------------------------------------------------------------ trocar depois
def test_so_eu_com_varios_usuarios_entra_como_o_escolhido(base):
    _p, repo, auth, cfg = base
    for n in ("ana", "bia"):
        repo.save_user({"username": n, "full_name": n.title(), "role": "medico", "active": True,
                        "password": "uma senha comprida"})
    d = _dlg(repo, auth, cfg, primeiro=False)
    d.radios["um"].setChecked(True)
    assert d.g_um.isVisibleTo(d)
    d.c_auto.setCurrentIndex(d.c_auto.findData("bia"))
    assert d.aplicar()
    assert do_login(auth, cfg).username == "bia"


def test_o_menu_configuracoes_tem_o_modo_de_uso(env):
    from ipe.ui import configuracoes as C
    assert any(alvo == "f:abrir_modo_de_uso" for _s, _t, alvo in C.itens())
    from ipe.ui.main_window import MainWindow
    assert hasattr(MainWindow, "abrir_modo_de_uso")


def test_editar_usuario_guarda_a_conta_do_sistema(base, monkeypatch):
    _p, repo, auth, cfg = base
    from ipe.ui.users_dialog import UserEditDialog
    monkeypatch.setattr(MODO, "conta_do_sistema", lambda: "joao")
    d = UserEditDialog(None)
    d.username.setText("joao")
    d.pw.setText("uma senha comprida")
    next(b for b in d.findChildren(__import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton)
         if "deste computador" in b.text()).click()
    d._ok()
    assert d.data["conta_sistema"] == "joao"
    repo.save_user(d.data)
    assert repo.user_by_conta_sistema("joao")["username"] == "joao"


def test_primeira_abertura_pergunta_e_entra_sem_pedir_a_senha_de_novo(env, monkeypatch):
    """open_main_window de verdade: o assistente aparece, cria o administrador e a janela abre logada."""
    paths, _db, _repo = env
    QApplication.instance() or QApplication([])
    from ipe import app as APP
    from ipe.ui import modo_de_uso as MU

    vistos = []

    def exec_(self):
        vistos.append(1)
        self.radios["varios"].setChecked(True)
        self.e_user.setText("filipe")
        self.e_pw1.setText("uma senha comprida")
        self.e_pw2.setText("uma senha comprida")
        assert self.aplicar()
        return 1
    monkeypatch.setattr(MU.ModoDeUsoDialog, "exec", exec_)
    monkeypatch.setattr("ipe.ui.login.LoginDialog.exec", lambda self: pytest.fail("pediu a senha de novo"))
    cfg = Settings(paths.settings_file)
    win = APP.open_main_window(paths, cfg)
    try:
        assert vistos and win is not None
        from ipe.auth import session as S
        assert S.get().username == "filipe"
        # na segunda abertura não pergunta mais
        assert not MODO.precisa_perguntar(cfg, win.repo)
    finally:
        win.close()
