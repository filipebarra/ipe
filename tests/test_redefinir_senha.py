"""0.100.113: "Esqueci o usuário ou a senha" — redefinir no Ipê de uso único; nos outros modos, o caminho certo."""
from types import SimpleNamespace

import pytest

from ipe.auth import redefinir as RD
from ipe.auth.backend import AuthError, LocalAuth
from ipe.core.config import Settings


def _settings(paths, modo):
    from ipe.auth import modo as MODO
    st = Settings(paths.settings_file)
    MODO.aplicar(st, modo)
    return st


def test_onde_redefinir(env):
    paths, db, repo = env
    auth = LocalAuth(repo)
    assert RD.onde_redefinir(auth, _settings(paths, "um")) == "aqui"
    assert RD.onde_redefinir(auth, _settings(paths, "varios")) == "admin"
    assert RD.onde_redefinir(auth, _settings(paths, "servidor")) == "admin"
    assert RD.onde_redefinir(SimpleNamespace(remote=True), _settings(paths, "um")) == "servidor"


def test_redefinir_troca_a_senha_reativa_e_audita(env):
    paths, db, repo = env
    auth = LocalAuth(repo)
    auth.create_first_admin("dra", "Dra. Teste", "esquecida1")
    u = repo.user_by_name("dra")
    repo.save_user({"id": u["id"], "username": "dra", "active": False})
    with pytest.raises(ValueError):
        RD.redefinir(repo, "dra", "123", "conta")                 # curta
    with pytest.raises(ValueError):
        RD.redefinir(repo, "ninguem", "novasenha1", "conta")
    r = RD.redefinir(repo, "DRA", "novasenha1", "conta-win")
    assert r == {"username": "dra", "reativado": True}
    assert auth.login("dra", "novasenha1").username == "dra"
    with pytest.raises(AuthError):
        auth.login("dra", "esquecida1")
    assert any(a["action"] == "senha_redefinida_neste_computador" for a in repo.access_log(limit=10))
    assert [x["username"] for x in RD.usuarios(repo)] == ["dra"]


def test_janela_de_login_redefine_no_uso_unico(env, monkeypatch):
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

    from ipe.ui import login as LG
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    auth = LocalAuth(repo)
    auth.create_first_admin("dra", "Dra. Teste", "esquecida1")
    st = _settings(paths, "um")
    dlg = LG.LoginDialog(auth, st)
    assert not dlg.b_esqueci.isHidden()

    def preencher(self):
        self.pw1.setText("novasenha1")
        self.pw2.setText("novasenha1")
        self._ok()
        return self.result()
    monkeypatch.setattr(LG.RedefinirSenhaDialog, "exec", preencher)
    dlg._esqueci()
    assert dlg.user.text() == "dra" and "redefinida" in dlg.msg.text()
    dlg.pw.setText("novasenha1")
    dlg._ok()
    assert dlg.result() == QDialog.Accepted and dlg.session.username == "dra"
    # senhas diferentes: não grava
    r = LG.RedefinirSenhaDialog(repo)
    r.pw1.setText("outrasenha1")
    r.pw2.setText("outrasenha2")
    r._ok()
    assert "iguais" in r.msg.text() and r.result() != QDialog.Accepted
    # várias pessoas: só explica (administrador ou ipe-cli)
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a: avisos.append(a[2]))
    LG.LoginDialog(auth, _settings(paths, "varios"))._esqueci()
    assert "ipe-cli redefinir-senha" in avisos[-1]


def test_linha_de_comando(env, monkeypatch, capsys):
    import ipe.__main__ as M
    paths, db, repo = env
    LocalAuth(repo).create_first_admin("dra", "Dra. Teste", "esquecida1")
    _settings(paths, "varios")
    assert M.main(["redefinir-senha"]) == 0
    assert "dra" in capsys.readouterr().out
    respostas = iter(["novasenha1", "novasenha1"])
    monkeypatch.setattr("getpass.getpass", lambda *a: next(respostas))
    assert M.main(["redefinir-senha", "dra"]) == 0
    assert LocalAuth(repo).login("dra", "novasenha1").username == "dra"
    _settings(paths, "cliente")
    assert M.main(["redefinir-senha", "dra"]) == 2
