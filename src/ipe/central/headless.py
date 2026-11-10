"""`ipe server`: servidor central sem janela (para um computador dedicado)."""

from __future__ import annotations

import getpass
import logging
import signal
import sys

log = logging.getLogger(__name__)


def run_server(args) -> int:
    from PySide6.QtCore import QCoreApplication, QTimer
    from ipe.auth.backend import LocalAuth
    from ipe.auth.passwords import password_problem
    from ipe.central.server import CentralServer
    from ipe.core.config import Settings, get_paths
    from ipe.core.logging_setup import setup_logging
    from ipe.db.repository import Repository
    from ipe.db.session import Database
    paths = get_paths()
    setup_logging(paths.logs)
    settings = Settings(paths.settings_file)
    db = Database(paths.database)
    repo = Repository(db)
    auth = LocalAuth(repo)
    if args.create_admin:
        if not auth.needs_first_admin():
            print("Já existem usuários; crie os outros pela janela (Usuário → Usuários e permissões).")
        else:
            pw = getpass.getpass(f"Senha para {args.create_admin}: ")
            why = password_problem(pw)
            if why or pw != getpass.getpass("Repita: "):
                print(why or "As senhas não conferem.", file=sys.stderr)
                return 2
            auth.create_first_admin(args.create_admin, args.create_admin, pw)
            print(f"Administrador {args.create_admin} criado.")
    if auth.needs_first_admin():
        print("Nenhum usuário cadastrado: rode `ipe server --create-admin admin` primeiro.",
              file=sys.stderr)
        return 2
    # 0.100.4: o Qt de interface sem tela (offscreen): o PDF do laudo do navegador usa o QTextDocument/QPdfWriter
    import os
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY") and sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtGui import QGuiApplication
        app = QCoreApplication.instance() or QGuiApplication(sys.argv)
    except Exception:  # noqa: BLE001
        app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    port = args.port or int(settings.get("central.port", 8043))
    srv = CentralServer(db, repo, paths.storage, port=port, certfile=settings.get("central.certfile", "") or "",
                        keyfile=settings.get("central.keyfile", "") or "")
    srv.settings = settings
    srv.start()
    net = None
    if not args.no_dicom:
        from ipe.network.service import NetworkService
        from ipe.automation.engine import AutomationEngine
        net = NetworkService(db, repo, paths.storage, settings)
        net.start_server()
        auto = AutomationEngine(repo, db, net, settings, paths)
        auto.start()
        print(net.server.status_text())
        # impressora DICOM (Print SCP): só liga se estiver ativada nas configurações
        if net.start_print_servers():
            print("Impressora DICOM: ligada")
    print(f"Servidor central em {srv.scheme}://0.0.0.0:{srv.port}  (Ctrl+C para parar)")
    if srv.scheme == "http":
        print("ATENÇÃO: sem certificado (central.certfile), o servidor usa HTTP e as senhas passam pela "
              "rede sem criptografia. Use só em rede interna confiável.")
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())   # systemctl stop / reboot: fecha limpo
    t = QTimer()
    t.start(500)                 # deixa o Python tratar o Ctrl+C
    t.timeout.connect(lambda: None)
    code = app.exec()
    srv.stop()
    if net is not None:
        net.shutdown()
    return code
