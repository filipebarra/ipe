"""Modo de acesso escolhido na instalação: um usuário só (sem login) ou vários (com login).

A decisão não é uma chave escondida: ela vale **enquanto não houver usuário cadastrado**.
No dia em que existir um, o login volta a ser pedido sozinho — e é assim que se sai do modo.
"""

import struct
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from ipe.auth.backend import LocalAuth
from ipe.core.config import Settings
from ipe.ui.login import do_login, single_user

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture()
def auth(env):
    _paths, _db, repo = env
    QApplication.instance() or QApplication([])
    return LocalAuth(repo)


@pytest.fixture()
def cfg(env):
    paths, _db, _repo = env
    return Settings(paths.settings_file)


# ------------------------------------------------------------------ a regra
def test_por_padrao_o_login_e_pedido(auth, cfg):
    assert str(cfg.get("auth.mode", "multi")) == "multi"
    assert not single_user(auth, cfg)


def test_um_usuario_so_abre_sem_pedir_nada(auth, cfg):
    cfg.set("auth.mode", "single")
    assert single_user(auth, cfg)
    s = do_login(auth, cfg)                     # sem diálogo nenhum: se abrisse um, travaria
    assert s is not None and s.username == "sistema"
    assert s.can("configure") and s.can("delete")


def test_so_eu_com_usuario_cadastrado_entra_como_ele(auth, cfg):
    """0.99.25: mudar de ideia agora é o Modo de uso (Configurações ▸ Usuários). Em "só eu", com um
    usuário cadastrado, o programa entra como ele — antes, cadastrar alguém fazia o login voltar."""
    cfg.set("auth.mode", "single")
    assert single_user(auth, cfg)
    auth.create_first_admin("filipe", "Filipe", "uma senha comprida")
    assert not single_user(auth, cfg)
    s = do_login(auth, cfg)
    assert s is not None and s.username == "filipe"


def test_modo_cliente_ignora_a_escolha(auth, cfg, monkeypatch):
    """No modo cliente quem manda é o servidor central."""
    cfg.set("auth.mode", "single")
    monkeypatch.setattr(auth, "remote", True, raising=False)
    assert not single_user(auth, cfg)


def test_sem_preferencias_nao_quebra(auth):
    assert not single_user(auth, None)
    assert not single_user(None, None)


# ------------------------------------------------------------------ linha de comando
def test_comando_set_mode_grava_a_escolha(env, monkeypatch):
    paths, _db, _repo = env
    from ipe.__main__ import main
    assert main(["set-mode", "single"]) == 0
    assert str(Settings(paths.settings_file).get("auth.mode", "")) == "single"
    assert main(["set-mode", "multi"]) == 0
    assert str(Settings(paths.settings_file).get("auth.mode", "")) == "multi"


def test_set_mode_so_aceita_os_dois_valores():
    from ipe.__main__ import _parser
    with pytest.raises(SystemExit):
        _parser().parse_args(["set-mode", "qualquer"])


# ------------------------------------------------------------------ instalador
def test_o_instalador_pergunta_e_manda_o_comando():
    iss = (RAIZ / "installer" / "ipe.iss").read_text(encoding="utf-8")
    assert "CreateInputOptionPage" in iss and "InitializeWizard" in iss
    assert 'Parameters: "set-mode single"' in iss and 'Parameters: "set-mode multi"' in iss
    assert "Check: EhUmUsuarioSo" in iss and "Check: NaoEhUmUsuarioSo" in iss
    assert "Usuários" in iss                     # a página diz onde mudar de ideia depois


def test_a_tela_de_usuarios_avisa_do_modo(env):
    from ipe.ui.users_dialog import UsersDialog
    paths, _db, repo = env
    QApplication.instance() or QApplication([])
    s = Settings(paths.settings_file)
    s.set("auth.mode", "single")
    dlg = UsersDialog(repo, s)
    assert dlg.faixa_modo.isVisibleTo(dlg) and "Só eu uso" in dlg.faixa_modo.text()
    assert "Modo de uso" in dlg.faixa_modo.text()     # diz onde mudar (0.99.25)
    from ipe.auth.backend import LocalAuth
    LocalAuth(repo).create_first_admin("filipe", "Filipe", "uma senha comprida")
    dlg.fill_users()
    assert dlg.faixa_modo.isVisibleTo(dlg)            # com gente cadastrada o modo continua valendo
    s.set("auth.mode", "multi")
    dlg.fill_users()
    assert not dlg.faixa_modo.isVisibleTo(dlg)
