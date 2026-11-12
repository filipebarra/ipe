"""Inicialização da interface e instância única.

Se o programa já estiver aberto, uma nova chamada (ex.: RIS chamando
`ipe open --accession 123`) é repassada à janela existente por um canal
local (named pipe no Windows, socket no Linux) e a janela vem para frente.
"""

from __future__ import annotations

import json
import os
import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from ipe import APP_NAME, DATA_NAME
from ipe.core.config import Settings, get_paths
from ipe.core.logging_setup import setup_logging

log = logging.getLogger(__name__)
# o mesmo canal de antes: uma chamada do programa velho acha a janela do novo
SERVER_NAME = f"{DATA_NAME}-instance"


def _arquivo_da_trava() -> str:
    """Trava de instância única, por usuário, na pasta temporária (0.99.79)."""
    import getpass
    import tempfile
    try:
        quem = getpass.getuser()
    except Exception:  # noqa: BLE001
        quem = "usuario"
    seguro = "".join(c if c.isalnum() else "_" for c in quem)
    return os.path.join(tempfile.gettempdir(), f"{DATA_NAME}-{seguro}.lock")


def pegar_a_vez():
    """0.99.79: só um Ipê aberto por usuário. Devolve a trava (guardar enquanto o programa roda)
    ou None se outro Ipê já está aberto. A trava some sozinha se o programa cair (o PID é conferido)."""
    from PySide6.QtCore import QLockFile
    trava = QLockFile(_arquivo_da_trava())
    trava.setStaleLockTime(0)          # só conta como velha se o processo dono não existe mais
    if trava.tryLock(200):
        return trava
    return None


def avisar_a_instancia_aberta(payload: dict, espera_s: float = 25.0) -> bool:
    """Manda o pedido ao Ipê já aberto. Se ele ainda está abrindo (login, banco), espera o canal subir."""
    import time
    fim = time.monotonic() + espera_s
    while True:
        if send_to_running_instance(payload):
            return True
        if time.monotonic() >= fim:
            return False
        time.sleep(0.3)


def send_to_running_instance(payload: dict, timeout_ms: int = 800) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(timeout_ms):
        return False
    sock.write(json.dumps(payload).encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(timeout_ms)
    sock.disconnectFromServer()
    return True


DARK_STYLESHEET = """
QMenuBar { background:#252526; color:#dcdcdc; }
QMenuBar::item:selected { background:#35506e; }
QMenu { background:#2d2f34; color:#e0e0e0; border:1px solid #44474e; }
QMenu::item:selected { background:#35506e; }
QMenu::item:disabled { color:#808080; }
QTabBar::tab { background:#2d2d30; color:#cfcfcf; padding:5px 12px; border:1px solid #3c3c40;
               border-bottom:none; margin-right:1px; }
QTabBar::tab:selected { background:#3a3d44; color:#ffffff; }
QTabBar::tab:hover { background:#34373d; }
QHeaderView::section { background:#2d2d30; color:#dcdcdc; border:none; border-right:1px solid #3c3c40;
                       border-bottom:1px solid #3c3c40; padding:3px 6px; }
QTableCornerButton::section { background:#2d2d30; border:none; }
QLineEdit, QTextEdit, QPlainTextEdit {
    background:#1c1c1e; color:#e6e6e6; border:1px solid #4a4d55; border-radius:3px; padding:3px 5px;
    selection-background-color:#35506e; }
QLineEdit:focus { border:1px solid #4fb3ff; }
QComboBox QAbstractItemView { background:#2d2f34; color:#e6e6e6; selection-background-color:#35506e; }
QPushButton { background:#3a3d44; color:#e6e6e6; border:1px solid #50535b; border-radius:3px; padding:4px 12px; }
QPushButton:hover { background:#454952; }
QPushButton:pressed { background:#35506e; }
QPushButton:disabled { color:#808080; }
QToolTip { background:#2d2f34; color:#e6e6e6; border:1px solid #50535b; }
QStatusBar { background:#252526; color:#cfcfcf; }
QCheckBox, QRadioButton, QLabel, QGroupBox { color:#dcdcdc; }
"""


def _dark_palette(app: QApplication) -> None:
    """Tema escuro completo, independente do tema do Windows (claro ou escuro)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPalette
    hints = app.styleHints()
    if hasattr(hints, "setColorScheme"):          # Qt 6.8+: barra de título escura também
        try:
            hints.setColorScheme(Qt.ColorScheme.Dark)
        except Exception:  # noqa: BLE001
            pass
    app.setStyle("Fusion")
    pal = QPalette()
    text = QColor(220, 220, 220)
    colors = {
        QPalette.Window: QColor(37, 37, 38), QPalette.WindowText: text,
        QPalette.Base: QColor(28, 28, 30), QPalette.AlternateBase: QColor(45, 45, 48),
        QPalette.Text: text, QPalette.Button: QColor(45, 45, 48), QPalette.ButtonText: text,
        QPalette.BrightText: QColor(255, 120, 120), QPalette.Highlight: QColor(53, 80, 110),
        QPalette.HighlightedText: QColor(255, 255, 255), QPalette.ToolTipBase: QColor(45, 47, 52),
        QPalette.ToolTipText: text, QPalette.PlaceholderText: QColor(140, 140, 145),
        QPalette.Link: QColor(79, 179, 255), QPalette.LinkVisited: QColor(160, 140, 255),
        QPalette.Light: QColor(70, 70, 75), QPalette.Midlight: QColor(58, 58, 62),
        QPalette.Mid: QColor(45, 45, 48), QPalette.Dark: QColor(25, 25, 27), QPalette.Shadow: QColor(0, 0, 0),
    }
    for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
        for role, color in colors.items():
            pal.setColor(group, role, color)
    for role in (QPalette.Text, QPalette.ButtonText, QPalette.WindowText, QPalette.PlaceholderText):
        pal.setColor(QPalette.Disabled, role, QColor(115, 115, 120))
    app.setPalette(pal)
    app.setStyleSheet(DARK_STYLESHEET + _indicator_css())


def _indicator_css() -> str:
    """Caixas de marcar visíveis no tema escuro (em listas, tabelas e QCheckBox)."""
    import tempfile
    from pathlib import Path
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
    try:
        path = Path(tempfile.gettempdir()) / "dicomviewer_check.png"
        if not path.exists():
            pm = QPixmap(32, 32)
            pm.fill(Qt.transparent)
            pen = QPen(QColor(255, 255, 255), 5)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p = QPainter(pm)
            try:
                p.setRenderHint(QPainter.Antialiasing)
                p.setPen(pen)
                p.drawLine(QPointF(7, 17), QPointF(13, 23))
                p.drawLine(QPointF(13, 23), QPointF(25, 9))
            finally:
                p.end()
            pm.save(str(path))
        img = path.as_posix()
    except Exception:  # noqa: BLE001
        return ""
    box = ("width:11px; height:11px; border:1px solid #9aa0aa; border-radius:2px; background:#1c1c1e;")
    return f"""
QCheckBox::indicator, QAbstractItemView::indicator, QGroupBox::indicator {{ {box} }}
QCheckBox::indicator:hover, QAbstractItemView::indicator:hover {{ border:1px solid #4fb3ff; }}
QCheckBox::indicator:checked, QAbstractItemView::indicator:checked, QGroupBox::indicator:checked {{
    background:#2f7fd0; border:1px solid #4fb3ff; image:url({img}); }}
QCheckBox::indicator:disabled, QAbstractItemView::indicator:disabled {{ border:1px solid #55585f; background:#26272b; }}
QCheckBox::indicator:checked:disabled {{ background:#3a4a5c; }}
QRadioButton::indicator {{ width:11px; height:11px; border:1px solid #9aa0aa; border-radius:6px; background:#1c1c1e; }}
QRadioButton::indicator:hover {{ border:1px solid #4fb3ff; }}
QRadioButton::indicator:checked {{ border:1px solid #4fb3ff; background:qradialgradient(cx:0.5, cy:0.5, radius:0.5,
    fx:0.5, fy:0.5, stop:0 #ffffff, stop:0.38 #ffffff, stop:0.48 #2f7fd0, stop:1 #2f7fd0); }}
"""


QT_LOCALE = {"pt-BR": "pt_BR", "en": "en", "es": "es", "fr": "fr", "de": "de", "it": "it"}


def _install_translator(app: QApplication, lang: str = "pt-BR") -> None:
    """Botões padrão do Qt (OK, Cancelar, Sim, Não…) no idioma escolhido."""
    from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    tr = QTranslator(app)
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if tr.load(QLocale(QT_LOCALE.get(lang, lang)), "qtbase", "_", path):
        app.installTranslator(tr)
        app._qt_translator = tr   # mantém referência


def _choose_language(settings) -> str:
    """Idioma do programa. Na primeira vez, pergunta, com o inglês já escolhido (0.99.33; antes era o
    idioma do sistema). O instalador do Windows e os scripts instalar.* já perguntam e gravam; esta
    pergunta fica para quem abre o pacote portátil."""
    from ipe.core import i18n
    lang = settings.get("language", "")
    if lang:
        return lang
    from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout
    options = i18n.available()
    guess = i18n.DEFAULT_LANG
    dlg = QDialog()
    dlg.setWindowTitle("Language / Idioma")
    combo = QComboBox()
    for code, name in options:
        combo.addItem(name, code)
    combo.setCurrentIndex(max(0, combo.findData(guess)))
    lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel("Choose the program language.\nEscolha o idioma.  ·  Elija el idioma.\n"
                         "(You can change it later in Settings ▸ System ▸ Language.)"))
    lay.addWidget(combo)
    bb = QDialogButtonBox(QDialogButtonBox.Ok)
    bb.accepted.connect(dlg.accept)
    lay.addWidget(bb)
    dlg.exec()
    lang = combo.currentData() or i18n.DEFAULT_LANG
    settings.set("language", lang)
    settings.save()
    return lang


def _install_excepthook() -> None:
    """Erros não tratados vão para o log (com pythonw não há console para vê-los)."""
    def hook(exc_type, exc, tb) -> None:
        log.error("Erro não tratado", exc_info=(exc_type, exc, tb))
    sys.excepthook = hook


def _warn_if_admin() -> None:
    """No Windows, um programa aberto como administrador não recebe arrastos do Explorer."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            log.warning("Programa rodando como administrador: o Windows bloqueia arrastar "
                        "arquivos do Explorer para ele.")
    except Exception:  # noqa: BLE001
        pass


def _vigiar_quedas(pasta) -> None:
    """0.100.27: quando o programa cai por erro de uma biblioteca nativa (o "fechou sozinho"), o Python não chega a
    registrar nada. O faulthandler escreve onde cada linha de execução estava, em `queda.log`, na pasta dos logs."""
    try:
        import faulthandler
        arq = open(pasta / "queda.log", "a", encoding="utf-8")       # noqa: SIM115 - fica aberto até o fim
        arq.write(f"\n=== {APP_NAME} iniciado em {__import__('datetime').datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
        arq.flush()
        faulthandler.enable(file=arq, all_threads=True)
        _vigiar_quedas.arquivo = arq
    except Exception:  # noqa: BLE001
        log.debug("faulthandler", exc_info=True)


def open_main_window(paths, settings):
    """Login (banco local ou servidor central) e janela principal. None = cancelado."""
    from ipe.auth.backend import LocalAuth
    from ipe.db.repository import Repository
    from ipe.db.session import Database
    from ipe.ui.login import do_login
    from ipe.ui.main_window import MainWindow
    mode = settings.get("central.mode", "local")
    if mode == "client":
        from ipe.central.client_mode import open_client_window
        return open_client_window(paths, settings)
    db = Database(paths.database)
    repo = Repository(db)
    auth = LocalAuth(repo)
    # 0.99.25: primeiro uso — perguntar como o programa vai ser usado (e criar o administrador, se for o caso)
    from ipe.auth import modo as MODO
    criado = ""
    if MODO.precisa_perguntar(settings, repo):
        from PySide6.QtWidgets import QDialog

        from ipe.ui.modo_de_uso import ModoDeUsoDialog
        dlg = ModoDeUsoDialog(settings, repo, auth, primeiro_uso=True)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        criado = dlg.admin_criado
        mode = settings.get("central.mode", "local")
        if mode == "client":
            from ipe.central.client_mode import open_client_window
            return open_client_window(paths, settings)
    where = "Servidor central deste grupo" if mode == "server" else ""
    s = auth.auto_session(criado) if criado else None    # acabou de digitar a senha: não pede de novo
    if s is None:
        s = do_login(auth, settings, where=where)
    if s is None:
        return None
    win = MainWindow(paths, settings, auth=auth, repo=repo, db=db)
    win.start_session(s)
    return win


def run_gui(external: dict | None = None, minimized: bool = False) -> int:
    if os.environ.get("IPE_DIAG"):                   # 0.100.27: diagnóstico automático (workflow do macOS)
        from ipe import diag
        return diag.rodar(os.environ["IPE_DIAG"])
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    try:
        from ipe.ui.icons import icon
        app.setWindowIcon(icon("app"))
    except Exception:  # noqa: BLE001 - ícone não pode impedir o programa de abrir
        pass

    if external and send_to_running_instance(external):
        return 0     # a janela já aberta cuidou do pedido
    # 0.99.79: *"vários programas são abertos se eu clicar mais de uma vez no atalho… também quando
    # escolho minimizar ao fechar e deixar no tray"*. Um Ipê só por usuário: o segundo clique traz o
    # primeiro para a frente (inclusive da bandeja) e sai.
    trava = None
    if not os.environ.get("IPE_VARIAS_INSTANCIAS"):
        trava = pegar_a_vez()
        if trava is None:
            pedido = dict(external) if external else {"command": "mostrar", "minimizado": bool(minimized)}
            if avisar_a_instancia_aberta(pedido):
                return 0
            log.warning("Outro Ipê parece aberto, mas não respondeu; abrindo assim mesmo.")
    app._ipe_trava = trava
    pendentes: list[dict] = []
    janela: dict = {}

    def entregar(payload: dict) -> None:
        win_ = janela.get("win")
        if win_ is None:                       # ainda no login: guarda e põe o login na frente
            pendentes.append(payload)
            for w in QApplication.topLevelWidgets():
                if w.isVisible():
                    w.raise_()
                    w.activateWindow()
            return
        if payload.get("command") == "mostrar":
            if not payload.get("minimizado"):
                trazer = getattr(win_, "trazer_para_a_frente", None)
                if trazer is not None:
                    trazer()
                else:
                    win_.showNormal()
                    win_.raise_()
                    win_.activateWindow()
            return
        win_.handle_external(payload)

    server = QLocalServer()
    QLocalServer.removeServer(SERVER_NAME)   # temos a trava: um servidor com esse nome é órfão de uma queda
    if server.listen(SERVER_NAME):
        def on_connection() -> None:
            conn = server.nextPendingConnection()

            def read() -> None:
                try:
                    payload = json.loads(bytes(conn.readAll()).decode("utf-8"))
                    log.info("Chamada externa: %s", payload)
                    entregar(payload)
                except (ValueError, UnicodeDecodeError) as e:
                    log.warning("Chamada externa inválida: %s", e)
            conn.readyRead.connect(read)
        server.newConnection.connect(on_connection)
    else:
        log.warning("Não foi possível abrir o canal de instância única: %s", server.errorString())
    app._ipc_server = server

    paths = get_paths()
    setup_logging(paths.logs)
    _vigiar_quedas(paths.logs)
    _install_excepthook()
    _warn_if_admin()
    settings = Settings(paths.settings_file)
    if not paths.settings_file.exists():
        settings.save()          # cria o arquivo para o usuário poder editar
    # 0.99.75: a mudança da pasta do banco marcada com o programa aberto é feita agora, antes de abrir o banco
    from ipe.core import mover_banco as MB
    if MB.pendente(settings) is not None:
        from PySide6.QtWidgets import QMessageBox, QProgressDialog
        prog = QProgressDialog("Movendo o banco para a pasta nova…", "", 0, 0)
        prog.setCancelButton(None)
        prog.setMinimumDuration(0)
        prog.show()
        app.processEvents()
        feito = MB.executar_pendente(settings, paths, lambda _n: app.processEvents())
        prog.close()
        if feito is not None:
            ok, msg = feito
            (QMessageBox.information if ok else QMessageBox.warning)(None, "Pasta do banco", msg)
            paths = get_paths()
            settings = Settings(paths.settings_file)
    from ipe.core.config import publicar_pasta_do_banco
    publicar_pasta_do_banco(paths)           # 0.99.67: o instalador mostra esta pasta numa atualização
    _dark_palette(app)

    # idioma: traduções do usuário, escolha (pergunta na primeira vez) e tradução automática das telas
    from ipe.core import i18n
    i18n.set_user_dir(paths.config / "locale")
    lang = _choose_language(settings)
    i18n.load(lang)
    _install_translator(app, lang)
    if lang != i18n.BASE_LANG:
        from ipe.ui.qt_i18n import install as install_i18n
        install_i18n()

    from ipe.ui import janelas
    app._dv_janelas = janelas.instalar(app, settings)      # 0.99.6: toda janela abre maximizada
    from ipe.ui.main_window import MainWindow
    win = open_main_window(paths, settings)
    if win is None:
        return 0

    janela["win"] = win
    win._ipc_server = server   # mantém referência

    if minimized and win.tray is not None:
        pass                      # começa escondido na bandeja
    elif minimized:
        win.showMinimized()
    else:
        win.show_on_configured_screen()
    win.start_services()
    if external:
        win.handle_external(external)
    for pedido in pendentes:                 # cliques no atalho durante o login
        entregar(pedido)
    pendentes.clear()
    # A versão no log é o que permite saber **qual** programa produziu aquele registro: o
    # instalado, o portátil ou o código vivo. Sem ela, um relato de defeito não diz de
    # que versão está falando.
    from ipe import __version__
    from ipe.core import runtime as _R
    log.info("Ipê %s (%s) — dados em %s", __version__,
             "empacotado" if _R.frozen() else "código", paths.data)
    return app.exec()
