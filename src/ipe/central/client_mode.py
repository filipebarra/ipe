"""Abertura do programa no modo cliente: login no servidor central e cache local."""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QDialog, QMessageBox

from ipe.auth.backend import RemoteAuth
from ipe.central.client_repo import ClientRepository
from ipe.central.remote import RemoteClient

log = logging.getLogger(__name__)


def cache_paths(paths):
    base = paths.data / "CacheCentral"
    (base / "Storage").mkdir(parents=True, exist_ok=True)
    return base / "cache.sqlite", base / "Storage"


def open_client_window(paths, settings, login=True):
    from ipe.db.repository import Repository
    from ipe.db.session import Database
    from ipe.ui.login import LoginDialog
    from ipe.ui.main_window import MainWindow
    url = settings.get("central.url", "")
    client = RemoteClient(url, verify_tls=bool(settings.get("central.verify_tls", False)))
    auth = RemoteAuth(client)
    dlg = LoginDialog(auth, settings, where=f"Servidor central: {client.url}")
    if dlg.exec() != QDialog.Accepted or dlg.session is None:
        if getattr(dlg, "go_local", False):
            settings.set("central.mode", "local")
            settings.save()
            from ipe.app import open_main_window
            return open_main_window(paths, settings)
        return None
    s = dlg.session
    db_path, storage = cache_paths(paths)
    db = Database(db_path)
    repo = ClientRepository(Repository(db), client, storage, settings)
    win = MainWindow(paths, settings, auth=auth, repo=repo, db=db, storage=storage)

    def relogin() -> bool:
        QMessageBox.information(win, "Servidor central", "A sessão no servidor expirou. Entre de novo.")
        d = LoginDialog(auth, settings, win, where=f"Servidor central: {client.url}")
        return d.exec() == QDialog.Accepted
    client.on_unauthorized = relogin
    repo.on_upload_done = lambda msg: win.upload_message.emit(msg)
    win.start_session(s)
    return win
