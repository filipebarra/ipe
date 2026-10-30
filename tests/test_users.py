"""Fase 8 — usuários, senhas, perfis, preferências por usuário e registro de acesso."""
import pytest
from PySide6.QtWidgets import QApplication

from ipe.auth import session as S
from ipe.auth.backend import AuthError, LocalAuth
from ipe.auth.passwords import hash_password, verify_password
from ipe.auth.permissions import permissions_for, role_permissions
from ipe.core.config import Settings
from ipe.importer.scanner import Importer


def test_passwords():
    h = hash_password("segredo1", iterations=1000)
    assert verify_password("segredo1", h) and not verify_password("outra", h) and "segredo1" not in h
    assert not verify_password("x", "lixo")


def test_users_roles_and_login(env):
    paths, db, repo = env
    auth = LocalAuth(repo)
    assert auth.needs_first_admin()
    auth.create_first_admin("admin", "Administrador", "admin123")
    assert not auth.needs_first_admin()
    with pytest.raises(AuthError):
        auth.create_first_admin("x", "x", "123456")
    uid = repo.save_user({"username": "ana", "full_name": "Ana R.", "role": "residente", "password": "resid123"})
    with pytest.raises(ValueError):
        repo.save_user({"username": "ANA", "password": "123456"})
    with pytest.raises(AuthError):
        auth.login("ana", "errada")
    s = auth.login("Ana", "resid123")
    assert s.role == "residente" and s.can("view") and not s.can("delete") and not s.can("export_identified")
    assert repo.user_by_name("ana")["last_login"] is not None
    # desativado não entra
    repo.save_user({"id": uid, "username": "ana", "active": False})
    with pytest.raises(AuthError):
        auth.login("ana", "resid123")
    # tabela de perfis ajustável (admin sempre tudo)
    repo.set_app_setting("roles", {"residente": ["view", "delete"], "admin": []})
    t = role_permissions(repo)
    assert t["residente"] == {"view", "delete"} and "users" in t["admin"]
    assert permissions_for("tecnico", repo) == role_permissions(None)["tecnico"]
    # troca de senha
    a = auth.login("admin", "admin123")
    with pytest.raises(AuthError):
        auth.change_password(a, "errada", "novasenha")
    auth.change_password(a, "admin123", "novasenha")
    assert auth.login("admin", "novasenha").username == "admin"


def test_user_prefs_layer(env):
    paths, db, repo = env
    auth = LocalAuth(repo)
    auth.create_first_admin("admin", "Adm", "admin123")
    repo.save_user({"username": "bia", "role": "medico", "password": "medico123"})
    st = Settings(paths.settings_file)
    st.set("dicom.port", 11112)
    a = auth.login("admin", "admin123")
    st.attach_user(auth.prefs(a), lambda p: auth.save_prefs(a, p))
    st.set("viewer.mouse.right", "pan")          # do usuário
    st.set("dicom.port", 2222)                    # do computador
    st.set("viewer.close_to_tray", True)          # exceção: do computador
    st.save()
    assert repo.user_prefs(a.user_id)["viewer"]["mouse"]["right"] == "pan"
    assert "dicom" not in repo.user_prefs(a.user_id)
    assert st.get("viewer.mouse.left") == "wl"     # padrão continua valendo por baixo
    b = auth.login("bia", "medico123")
    st2 = Settings(paths.settings_file)
    assert st2.get("dicom.port") == 2222 and st2.get("viewer.close_to_tray") is True
    st2.attach_user(auth.prefs(b), lambda p: auth.save_prefs(b, p))
    assert st2.get("viewer.mouse.right") == "zoom"   # a Bia não herda o mouse do admin


def test_gui_permissions_and_audit(env, sample_dir, tmp_path):
    from ipe.ui.main_window import MainWindow
    from ipe.ui.users_dialog import UsersDialog
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    Importer(db, paths.storage).import_paths([sample_dir])
    auth = LocalAuth(repo)
    auth.create_first_admin("admin", "Adm", "admin123")
    repo.save_user({"username": "tec", "full_name": "Técnico", "role": "tecnico", "password": "tecnic123"})
    st = Settings(paths.settings_file)
    w = MainWindow(paths, st, auth=auth, repo=repo, db=db)
    w.start_session(auth.login("tec", "tecnic123"))
    w.show()
    app.processEvents()
    assert "Técnico" in w.user_label.text() and w.user_label.text().startswith("Usuário")
    assert w.browser.tree.isHidden()           # técnico não vê listas de casos
    w.browser.refresh()
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    log = repo.access_log(user="tec")
    assert {"login", "abrir"} <= {e["action"] for e in log}
    assert any(e["study_uid"] for e in log if e["action"] == "abrir")
    from PySide6.QtWidgets import QMessageBox
    shown = []
    orig = QMessageBox.information
    QMessageBox.information = staticmethod(lambda *a, **k: shown.append(a) or 0)
    try:
        w.open_users()                                   # sem permissão
        w.open_network_settings()
        w.browser._delete([])
    finally:
        QMessageBox.information = orig
    assert len(shown) == 3
    # export: técnico pode exportar identificado; residente não
    from ipe.ui.export_dialog import ExportDialog
    from ipe.exporter.core import ExportItem
    d = ExportDialog(repo, st, [("x", [ExportItem("1")])], w)
    assert d.c_anon_names.isEnabled()
    S.set_current(S.UserSession(username="r", role="residente", perms=permissions_for("residente")))
    d2 = ExportDialog(repo, st, [("x", [ExportItem("1")])], w)
    assert not d2.c_anon_names.isEnabled() and d2.g_anon.isChecked()
    # admin: diálogo de usuários
    w.start_session(auth.login("admin", "admin123"))
    assert not w.browser.tree.isHidden()
    dlg = UsersDialog(repo, st, w)
    assert dlg.t_users.rowCount() == 2
    t = dlg.roles_table()
    assert "delete" in t["medico"] and "delete" not in t["residente"]
    dlg.f_days.setValue(1)
    dlg.fill_log()
    assert dlg.t_log.rowCount() >= 3
    w.close()


def test_startup_auto_login(env):
    from ipe.app import open_main_window
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    LocalAuth(repo).create_first_admin("admin", "Adm", "admin123")
    st = Settings(paths.settings_file)
    st.set("auth.auto_login", "admin")
    w = open_main_window(paths, st)
    assert w is not None and S.get().username == "admin" and st.user is not None
    assert repo.access_log(action="login")[0]["user"] == "admin"
    w.close()
