"""Janela principal: aba do banco de dados + uma aba por estudo aberto."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QInputDialog, QTabBar, QLabel, QMainWindow, QMenu, QMessageBox,
    QProgressDialog, QTabWidget,
)

from ipe.network import nodes as NODES
from ipe import APP_NAME, NOT_FOR_DIAGNOSIS, __version__
from ipe.core.config import AppPaths, Settings
from ipe.core.sysinfo import auto_cache_mb, is_elevated, process_ram_mb
from ipe.db.repository import Repository
from ipe.db.session import Database
from ipe.imaging.series import FrameCache
from ipe.importer.scanner import Importer
from ipe.ui.browser import Browser
from ipe.network.external import HttpApi
from ipe.network.service import NetworkService
from ipe.ui.file_drop import FileDropFilter, local_paths
from ipe.ui.pacs_panel import PacsPanel
from ipe.ui.import_worker import ImportThread
from ipe.ui.monitors import (
    ScreenWindow, layout_for_screen, screen_key, screen_with_role, screens_with_role,
    tela_da_janela_principal)
from ipe.ui.viewer.sync import SyncHub
from ipe.ui.viewer.viewer_tab import LAYOUTS, ViewerTab

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    upload_message = Signal(str)            # modo cliente: envio ao servidor central terminou

    def __init__(self, paths: AppPaths, settings: Settings, session=None, auth=None, repo=None, db=None,
                 storage=None):
        super().__init__()
        from ipe.auth import session as S
        self.paths, self.settings = paths, settings
        from ipe.core import locations as LOC
        # local ativo: o banco deste computador ou a pasta escolhida (HD externo, rede…)
        self.location = LOC.current(settings, paths)
        self.db = db or Database(paths.database if self.location.is_default else self.location.database)
        self.repo = repo or Repository(self.db)
        self.auth = auth
        self.storage = Path(storage) if storage is not None else (
            paths.storage if self.location.is_default else self.location.storage)
        self.central = None                  # servidor central (quando este computador é o servidor)
        if session is not None:
            S.set_current(session)
        # cache de imagens: automático (1/4 da RAM) ou o teto definido em Preferências → Desempenho
        self.cache = FrameCache(max_mb=self.cache_limit_mb())
        self._import_thread = None
        self._import_dialog = None
        self._open_after_import = False
        self._pending_imports: list[Path] = []
        self.detached: list[ScreenWindow] = []
        self.sync_hub = SyncHub(self.repo, self, settings)

        self.setWindowTitle(f"{APP_NAME} {__version__} — {NOT_FOR_DIAGNOSIS}")
        self.resize(1400, 860)
        self.setAcceptDrops(True)
        # arrastar arquivos/pastas/ZIP para qualquer janela do programa importa
        self._drop_filter = FileDropFilter(self)
        QApplication.instance().installEventFilter(self._drop_filter)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        self.browser = Browser(self.repo, self.storage, settings=settings)
        self.browser.open_study.connect(self.open_from_browser)
        self.browser.compare_studies.connect(self.open_comparison)
        self.browser.open_series.connect(self.open_study)
        self.browser.choose_series.connect(self.choose_series)
        self.browser.fix_tags_requested.connect(self.fix_study_tags)
        self.browser.film_requested.connect(self.film_request)
        self.browser.meeting_requested.connect(self.start_meeting)
        self.browser.open_case.connect(lambda st, series: self.open_study(st, series or None))
        self.browser.import_list_requested.connect(self.import_case_list)
        self.browser.import_requested.connect(self.import_dialog)
        self.browser.report_requested.connect(self.open_report)
        # rede DICOM: nó local, consultas e transferências (o nó liga em start_services)
        self.net = NetworkService(self.db, self.repo, self.storage, settings, self)
        self.net.received.connect(self._on_received)
        self.net.job_finished.connect(self._on_job_finished)
        self.net.job_changed.connect(self._on_job_changed)
        self.net.server_status.connect(lambda _t: self._update_net_label())
        self.net.print_status.connect(lambda _t: self._update_net_label())
        self.net.print_received.connect(self._on_print_received)
        self.net.print_images.connect(self._on_print_images)
        self.pacs = PacsPanel(self.net, self.repo)
        self.pacs.open_study.connect(self.open_study)
        self.pacs.configure_requested.connect(self.open_network_settings)
        from ipe.ui.home import PacsWindow
        self.pacs_window = PacsWindow(self.pacs, settings, self)      # janela flutuante (botão PACS)
        self.tabs.addTab(self.browser, "Banco de dados")
        bar = self.tabs.tabBar()
        bar.setTabButton(0, QTabBar.ButtonPosition.RightSide, None)
        # a barra de abas não fica com o foco: com ele, ← → trocavam de exame em vez de etapa
        # da mamografia (o atalho do visualizador só vale com o foco dentro do visualizador)
        bar.setFocusPolicy(Qt.NoFocus)
        self.tabs.setFocusPolicy(Qt.NoFocus)
        self.tabs.currentChanged.connect(self._focar_aba)
        self.tabs.setCurrentWidget(self.browser)
        self.browser.send_requested.connect(self.send_studies)
        self.browser.send_series_requested.connect(
            lambda uid, series, nid, iid: self.send_studies([uid], nid, iid, series))
        self.browser.copy_to_location.connect(self.copy_studies_to_location)
        self.http = HttpApi(self.handle_external, self)
        from ipe.automation.engine import AutomationEngine
        self.auto = AutomationEngine(self.repo, self.db, self.net, settings, paths,
                                     open_uids=lambda: {u for t in self.all_viewer_tabs() for u in t.study_order},
                                     parent=self, cache=self.cache)
        self.auto.notify.connect(self.show_notification)
        self.auto.implante_corrigido.connect(self._implante_pronto)
        self.auto.segmentacao_pronta.connect(self._segmentacao_pronta)
        self._really_quit = False
        self._fechando_exames = False
        self._prints = None               # aba de impressões (criada quando usada)
        self._auto_film_wait: dict[str, float] = {}   # exames chegando (filme automático do US)
        self._film = None                 # compositor de filmes (criado quando usado)
        self._film_host = None            # estudo (ViewerTab) ou janela onde o filme está
        self.meeting = None               # MeetingController quando o modo reunião está ativo
        self._privacy_restore: list = []
        self._film_window = None
        self._setup_tray()
        # 0.84: limpeza automática da lista de impressões (só age se ligada em Configurações)
        self._limpeza_timer = QTimer(self)
        self._limpeza_timer.setInterval(3600 * 1000)
        self._limpeza_timer.timeout.connect(self.run_print_cleanup)
        self._limpeza_timer.start()
        QTimer.singleShot(20000, self.run_print_cleanup)
        self._auto_film_timer = QTimer(self)
        self._auto_film_timer.setInterval(5000)
        self._auto_film_timer.timeout.connect(self._run_auto_film)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(1200)
        self._refresh_timer.timeout.connect(self.browser.refresh)
        # 0.99.4: a tira de séries do exame aberto se atualiza sozinha quando chega série nova
        # (tabela dos discos, SEG, captura, cópia sem implante, imagens da rede).
        self._assin_exames: dict[str, tuple[int, int]] = {}
        self._vigia_timer = QTimer(self)
        self._vigia_timer.setInterval(3000)
        self._vigia_timer.timeout.connect(self._vigiar_series)
        self._vigia_timer.start()
        self.setCentralWidget(self.tabs)

        self._build_menus()
        from ipe.ui.home import HomeBar
        self.home_bar = HomeBar(self)
        self.browser.set_home_bar(self.home_bar)
        from ipe import modules as _MOD
        self.home_bar.set_visible("prints", _MOD.ligado(settings, "impressao"))
        try:                    # 0.88: os protocolos com etapas de fábrica, uma vez, para quem já tinha os seus
            from ipe.ui.viewer.hanging import acrescentar_os_de_fabrica
            acrescentar_os_de_fabrica(settings)
        except Exception:  # noqa: BLE001
            log.exception("protocolos de exibição de fábrica")
        from ipe.ui.locations_panel import LocationsPanel
        self.locations = LocationsPanel(settings, paths, self.repo, self)
        self.locations.location_chosen.connect(self.switch_location)
        self.locations.add_requested.connect(self.add_location)
        self.locations.rescan_requested.connect(self.rescan_location)
        self.locations.pacs_chosen.connect(self.open_pacs_node)
        self.locations.move_default_requested.connect(self.move_default_database)
        self.browser.series_changed.connect(self._series_changed)
        self.browser.segmentacao_pronta.connect(self._segmentacao_pronta)
        self.browser.add_side_panel(self.locations)
        self._refresh_other_locations()
        self._update_title()
        self.user_label = QLabel()
        self.statusBar().addPermanentWidget(self.user_label)
        self.net_label = QLabel()
        self.statusBar().addPermanentWidget(self.net_label)
        self.cache_label = QLabel()
        self.statusBar().addPermanentWidget(self.cache_label)
        self.statusBar().addPermanentWidget(QLabel(f"<i>{NOT_FOR_DIAGNOSIS}</i>"))
        if is_elevated():
            warn = QLabel("<b style='color:#ffb040'>⚠ Aberto como administrador — arrastar do Explorer "
                          "não funciona</b>")
            warn.setToolTip("O Windows bloqueia arrastar arquivos do Explorer para programas abertos "
                            "como administrador. Abra o executar.bat normalmente (sem “Executar como "
                            "administrador”).")
            self.statusBar().addPermanentWidget(warn)
        timer = QTimer(self)
        timer.timeout.connect(self._update_status)
        timer.start(2000)
        self._update_status()
        self.apply_permissions()
        self.upload_message.connect(lambda m: (self.statusBar().showMessage(m, 10000), self.browser.refresh()))

    # ------------------------------------------------------------ menus
    def _build_menus(self, janela=None, restrito: bool = False) -> None:
        """Monta a barra de menu. `janela` permite montar a mesma barra nos monitores viewer.

        O menu é o mesmo, mas as ações olham para a **janela ativa** (ver `aba_atual`): clicar em
        "Layout 2 × 2" no monitor da direita mexe no exame daquele monitor, não no da esquerda.
        """
        j = janela or self
        if restrito:
            self._menus_restritos(j)
            return
        m = j.menuBar().addMenu("&Arquivo")
        for text, fn, sc in (
            ("Importar pasta…", self.import_folder, "Ctrl+I"),
            ("Importar arquivos…", self.import_files, None),
            ("Importar ZIP…", self.import_zip, None),
            (None, None, None),
            ("Importar lista de casos (pacote)…", lambda: self.import_case_list(None), None),
            ("Exportar (DICOM, CD/pendrive, imagens)…", self.export_current, None),
            (None, None, None),
            ("Relatório do acervo (formato e compressão)…", self.open_acervo_report, None),
            ("Densidade mamária das imagens na tela…", self.open_densidade, None),
            ("Instalar a segmentação de órgãos (TotalSegmentator)…", self.instalar_segmentacao, None),
            (None, None, None),
            ("Sair", self.quit_app, "Ctrl+Q"),
        ):
            if text is None:
                m.addSeparator()
                continue
            a = QAction(text, j)
            if sc:
                a.setShortcut(QKeySequence(sc))
            a.triggered.connect(fn)
            m.addAction(a)
            if text.startswith("Densidade"):
                m._densidade = a                      # só com exame aberto: mede o que está na tela
            if text.startswith(("Impressões (recebidas", "Configurações de impressão")):
                m.__dict__.setdefault("_impressao", []).append(a)   # somem com o módulo desligado
        m.aboutToShow.connect(lambda menu=m: self.ajustar_menu_arquivo(menu))

        # 0.99.6: "crie um menu Impressão onde agrupa tudo que está no menu Arquivo sobre impressão e
        # acrescente a opção de acrescentar impressora DICOM"
        mi = j.menuBar().addMenu("I&mpressão")
        for text, fn, sc in (
            ("Filme / impressão (mostrar/esconder)", self.show_film, "Ctrl+P"),
            ("Filmes salvos…", lambda: (self.dock_film(), self.film_composer().open_saved()), None),
            (None, None, None),
            ("Impressões (recebidas e montadas aqui)…", self.show_prints, "Ctrl+Shift+P"),
            ("Painel de filmes e impressões…", self.show_film_dashboard, None),
            (None, None, None),
            ("Acrescentar impressora DICOM…", self.acrescentar_impressora_dicom, None),
            ("Impressoras DICOM…", lambda: self.acrescentar_impressora_dicom(nova=False), None),
            ("Configurações de impressão…", self.open_print_settings, None),
        ):
            if text is None:
                mi.addSeparator()
                continue
            a = QAction(text, j)
            if sc:
                a.setShortcut(QKeySequence(sc))
            a.triggered.connect(fn)
            mi.addAction(a)
            if text.startswith(("Impressões (recebidas", "Configurações de impressão")):
                mi.__dict__.setdefault("_impressao", []).append(a)   # somem com o módulo desligado
        mi.aboutToShow.connect(lambda menu=mi: self.ajustar_menu_arquivo(menu))

        v = j.menuBar().addMenu("&Exibir")
        # Os onze layouts viravam onze linhas no menu, e no banco de dados nenhuma delas fazia
        # nada: o clique sumia num `return` calado. Agora são um submenu só, e tudo o que depende
        # de um exame aberto **não aparece** quando não há exame.
        lay = QMenu("Layout dos quadros", j)
        for rows, cols in LAYOUTS:
            a = QAction(f"{rows} × {cols}", j)
            a.triggered.connect(lambda _=False, r=rows, c=cols: self._current_viewer_call(
                lambda t: t.set_layout(r, c)))
            lay.addAction(a)
        v.addMenu(lay)
        mon = QMenu("Mover estudo atual para o monitor", j)
        mon.aboutToShow.connect(lambda m=mon: self._fill_monitor_menu(m))
        v.addMenu(mon)
        if janela is None:
            self.monitor_menu = mon
        voltar_todos = QAction("Trazer todos os estudos de volta", j)
        voltar_todos.triggered.connect(self.reattach_all)
        v.addAction(voltar_todos)
        sep_exame = v.addSeparator()
        a = QAction("Calibração GSDF do monitor…", j)
        a.triggered.connect(self.open_gsdf)
        v.addAction(a)
        a = QAction("Preferências…", j)
        a.setShortcut(QKeySequence("Ctrl+,"))
        a.triggered.connect(self.open_preferences)
        v.addAction(a)
        sep_banco = v.addSeparator()
        banco = QAction("Voltar ao banco de dados", j)
        banco.setShortcut(QKeySequence("Ctrl+B"))
        banco.triggered.connect(self.ir_para_o_banco)
        v.addAction(banco)
        v._com_exame = [lay.menuAction(), mon.menuAction()]
        v._com_monitor = [voltar_todos]
        v._sep_exame, v._sep_banco, v._banco = sep_exame, sep_banco, banco
        v._janela = janela
        v.aboutToShow.connect(lambda m=v: self.ajustar_menu_exibir(m))
        self.ajustar_menu_exibir(v)

        r = j.menuBar().addMenu("&Rede")
        a = QAction("Consulta PACS (janela)", j)
        a.setShortcut(QKeySequence("Ctrl+Shift+F"))
        a.triggered.connect(self.show_pacs)
        r.addAction(a)
        # 0.99.6: a Gestão DICOM também no menu (antes só pelo botão do banco)
        a = QAction("Gestão DICOM (exames das modalidades no PACS)…", j)
        a.triggered.connect(self.show_gestao)
        r.addAction(a)
        a = QAction("Gestão automática (regras com horário)…", j)
        a.triggered.connect(self.show_gestao_automatica)
        r.addAction(a)
        r.addSeparator()
        a = QAction("Configurar nós DICOM…", j)
        a.triggered.connect(self.open_network_settings)
        r.addAction(a)
        a = QAction("Automação (buscas agendadas, anteriores, roteamento, limpeza)…", j)
        a.triggered.connect(self.open_automation)
        r.addAction(a)
        a = QAction("Configurar servidor central (intranet)…", j)
        a.triggered.connect(self.open_central_settings)
        r.addAction(a)
        r.addSeparator()
        a = QAction("Registrar link ipe:// neste computador", j)
        a.triggered.connect(self._register_url)
        r.addAction(a)

        u = j.menuBar().addMenu("&Usuário")
        u.aboutToShow.connect(lambda m=u: self._fill_user_menu(m))
        if janela is None:
            self.user_menu = u

        h = j.menuBar().addMenu("A&juda")
        a = QAction("Guia do usuário (PDF)", j)
        a.setShortcut(QKeySequence("F1"))
        a.triggered.connect(self.show_help)
        h.addAction(a)
        self._registrar_f1_da_ajuda(a)
        a = QAction("Sobre o Ipê…", j)
        a.triggered.connect(self.show_about)
        h.addAction(a)
        a = QAction("Abrir pasta de dados", j)
        a.triggered.connect(self._open_data_folder)
        h.addAction(a)
        # Ferramenta de teste: estava entre as ações clínicas do menu Arquivo.
        a = QAction("Gerar exames de teste (fantomas)…", j)
        a.triggered.connect(self.make_samples)
        h.addAction(a)

    def _menus_restritos(self, j) -> None:
        """Barra de menu da janela aberta por chamada externa no modo "só visualizador".

        Não é um menu com itens apagados: os caminhos para o banco de dados, para o PACS e para a
        exportação **não existem** nesta janela. A regra que o usuário escolheu é essa — quem
        recebe a chamada vê o exame que o RIS pediu.
        """
        v = j.menuBar().addMenu("&Exibir")
        lay = QMenu("Layout dos quadros", j)
        for rows, cols in LAYOUTS:
            a = QAction(f"{rows} × {cols}", j)
            a.triggered.connect(lambda _=False, r=rows, c=cols: self._current_viewer_call(
                lambda t: t.set_layout(r, c)))
            lay.addAction(a)
        v.addMenu(lay)
        mon = QMenu("Mover estudo atual para o monitor", j)
        mon.aboutToShow.connect(lambda m=mon: self._fill_monitor_menu(m))
        v.addMenu(mon)
        v.addSeparator()
        a = QAction("Calibração GSDF do monitor…", j)
        a.triggered.connect(self.open_gsdf)
        v.addAction(a)
        u = j.menuBar().addMenu("&Usuário")
        u.aboutToShow.connect(lambda m=u: self._fill_user_menu(m))
        h = j.menuBar().addMenu("A&juda")
        a = QAction("Guia do usuário (PDF)", j)
        a.setShortcut(QKeySequence("F1"))
        a.triggered.connect(self.show_help)
        h.addAction(a)
        self._registrar_f1_da_ajuda(a)
        a = QAction("Sobre o Ipê…", j)
        a.triggered.connect(self.show_about)
        h.addAction(a)

    # ------------------------------------------------- chamada externa só com o visualizador
    def so_viewer_externo(self) -> bool:
        c = self.settings.get("dicom", {}) or {}
        return bool(c.get("external_viewer_only", False))

    def so_viewer_do_pedido(self, args: dict) -> bool:
        """Esta chamada abre só o visualizador?

        O parâmetro da chamada manda; sem ele, vale a configuração. É o que deixa a estação dele
        abrindo o programa inteiro e a chamada do RIS para a sala pedir só o visualizador, sem
        ninguém trocar configuração entre uma coisa e outra.
        """
        pedido = str(args.get("janela", "") or "")
        if pedido:
            return pedido == "viewer"
        return self.so_viewer_externo()

    def janela_so_viewer(self, tela=None):
        """A janela de visualização da chamada externa, naquele monitor (cria se precisar)."""
        telas = self.telas_de_visualizacao()
        return self.window_for_screen(tela or (telas[0] if telas else self.screen()), restrito=True)

    def janelas_so_viewer(self) -> list:
        """As janelas restritas abertas agora (para mostrar e fechar o conjunto todo)."""
        return [d for d in self.detached if getattr(d, "restrito", False)]

    def abrir_so_viewer(self, study_uid: str) -> bool:
        """Abre o exame sem mostrar o banco de dados — **em todos os monitores viewer**.

        A repartição é a mesma do caminho normal (`abrir_dividido`): mamografia por etapa, plano
        por monitor, ou as séries na ordem. Antes a chamada externa abria só em `telas[0]`, e com
        dois monitores o segundo ficava vazio — o modo só-visualizador não é motivo para usar
        menos tela.
        """
        telas = self.telas_de_visualizacao()
        aberta = self._focus_open_study(study_uid)
        if aberta is None:
            dividiu = len(telas) > 1 and self.abrir_dividido(study_uid, telas, restrito=True)
            if not dividiu:
                janela = self.janela_so_viewer(telas[0] if telas else None)
                layout = layout_for_screen(self.settings, janela.screen() or self.screen())
                tab = self._make_tab(study_uid, layout)
                if tab is None:
                    return False
                janela.add_tab(tab)
        janelas = self.janelas_so_viewer() or [self.janela_so_viewer()]
        for j in janelas:
            j.showMaximized()
            j.raise_()
        janelas[0].activateWindow()
        self.browser.refresh()
        self.auto.on_study_opened(study_uid)
        return True

    def abrir_exame_do_pedido(self, study_uid: str, so_viewer: bool | None = None) -> None:
        """Abre o exame respeitando o modo da chamada **que o pediu**.

        Quando o exame veio do PACS, quem abre é o fim do download, longe do pedido: por isso a
        escolha fica guardada por exame. Sem isso, um pedido com `janela=viewer` abriria o
        programa inteiro só porque o exame demorou a chegar.
        """
        if so_viewer is None:
            so_viewer = self.__dict__.setdefault("_janela_do_pedido", {}).pop(
                study_uid, self.so_viewer_externo())
        if so_viewer:
            self.abrir_so_viewer(study_uid)
        else:
            self.open_study(study_uid)

    def avisar_bandeja_so_viewer(self) -> None:
        """Fechou a janela da chamada externa: fecha as dos outros monitores e diz que o programa
        continua recebendo. Exame aberto em metade das telas é pior do que exame fechado."""
        self._janela_externa = None
        if getattr(self, "_fechando_externas", False):
            return                           # já estou fechando o conjunto: não repito o aviso
        self._fechando_externas = True
        try:
            for j in self.janelas_so_viewer():
                if j.isVisible():
                    j.close()
        finally:
            self._fechando_externas = False
        if self.tray is not None and self.tray.isVisible():
            self.tray.showMessage(APP_NAME, "O exame foi fechado. O programa continua na bandeja: "
                                  "a próxima chamada do RIS abre na hora.")

    def ajustar_menu_exibir(self, menu) -> None:
        """Esconde o que não serve na tela em que ele está.

        Escolha dele: item que não serve **some**, em vez de ficar apagado. O que sobra é o que
        funciona ali — e o menu nunca engole um clique em silêncio.
        """
        tem_exame = isinstance(self.aba_atual(), ViewerTab)
        for a in getattr(menu, "_com_exame", []):
            a.setVisible(tem_exame)
        for a in getattr(menu, "_com_monitor", []):
            a.setVisible(bool(self.detached))
        sep = getattr(menu, "_sep_exame", None)
        if sep is not None:
            sep.setVisible(tem_exame or bool(self.detached))
        banco = getattr(menu, "_banco", None)
        if banco is not None:
            # na janela de um monitor sempre vale; na principal, só quando ele não está no banco
            no_banco = getattr(menu, "_janela", None) is None and self.tabs.currentWidget() is self.browser
            banco.setVisible(not no_banco)
            if getattr(menu, "_sep_banco", None) is not None:
                menu._sep_banco.setVisible(not no_banco)

    def acrescentar_impressora_dicom(self, nova: bool = True):
        """Menu Impressão ▸ Acrescentar impressora DICOM… (0.99.6): o cadastro das impressoras do filme,
        já com uma impressora nova na lista para preencher (nome, AE, IP, porta, AE de origem…).
        "Impressoras DICOM…" abre o mesmo cadastro sem acrescentar."""
        from ipe.auth import session as S
        if not S.require("configure", self, "cadastrar impressoras"):
            return None
        from ipe.ui.film.dialogs import DicomPrintDialog
        dlg = DicomPrintDialog(self.settings, self.net.local_ae, 0, 0, self, so_configurar=True)
        if nova and (self.settings.get("printing.dicom_printers", []) or []):
            dlg._add()                 # sem nenhuma, o próprio cadastro já abre com uma nova
        dlg.f_name.setFocus()
        dlg.f_name.selectAll()
        dlg.exec()
        return dlg

    def ajustar_menu_arquivo(self, menu) -> None:
        from ipe import modules as MOD
        a = getattr(menu, "_densidade", None)
        if a is not None:
            a.setVisible(isinstance(self.aba_atual(), ViewerTab) and MOD.ligado(self.settings, "mamografia"))
        for a in getattr(menu, "_impressao", []):
            a.setVisible(MOD.ligado(self.settings, "impressao"))

    @staticmethod
    def _can(perm: str) -> bool:
        from ipe.auth import session as S
        return S.can(perm)

    # ------------------------------------------------- F1: guia fora do visualizador, filme dentro
    def _registrar_f1_da_ajuda(self, acao: QAction) -> None:
        """No visualizador o F1 é do filme (pedido dele, 0.76); no resto, do guia do usuário.

        Duas ações com a mesma tecla valendo ao mesmo tempo é ambiguidade, e o Qt não dispara
        nenhuma das duas. Então a ajuda solta o F1 enquanto o foco está num visualizador que usa
        essa tecla, e o pega de volta quando o foco sai.
        """
        if not hasattr(self, "_acoes_f1"):
            self._acoes_f1 = []
            QApplication.instance().focusChanged.connect(self._f1_conforme_foco)
        self._acoes_f1.append(acao)

    def _f1_conforme_foco(self, _antes=None, depois=None) -> None:
        f1 = QKeySequence("F1")
        w, aba = depois, None
        while w is not None:
            if isinstance(w, ViewerTab):
                aba = w
                break
            w = w.parentWidget()
        do_filme = aba is not None and any(a.shortcut() == f1 for a in aba.actions_by_id.values())
        for a in list(getattr(self, "_acoes_f1", [])):
            try:
                a.setShortcut(QKeySequence() if do_filme else f1)
            except RuntimeError:                 # janela de monitor que já fechou
                self._acoes_f1.remove(a)

    def show_help(self) -> None:
        """F1: o guia do usuário em PDF, no leitor do sistema."""
        from ipe.ui.ajuda import abrir_guia
        abrir_guia(self)

    def show_about(self) -> None:
        from ipe.ui.ajuda import mostrar_sobre
        mostrar_sobre(self)

    def show_gestao(self) -> None:
        """Abre (ou traz para frente) a janela de gestão: modalidades × PACS."""
        from ipe.auth import session as S
        if self.meeting is not None or getattr(self, "_privacy_on", False):
            QMessageBox.information(self, "Gestão DICOM", "A gestão de exames fica indisponível "
                                    "enquanto os dados do paciente estão ocultos (reunião / Ocultar).")
            return
        if not S.require("query", self):
            return
        if getattr(self, "gestao_window", None) is None:
            from ipe.ui.gestao_dialog import GestaoWindow
            self.gestao_window = GestaoWindow(self.net, self.settings, self, auto=self.auto)
        self.gestao_window.show_front()

    def show_gestao_automatica(self) -> None:
        """Rede ▸ Gestão automática: a janela de Gestão já na aba "Automático"."""
        self.show_gestao()
        g = getattr(self, "gestao_window", None)
        if g is not None and g.isVisible():
            g.abas.setCurrentWidget(g.painel_auto)

    def show_pacs(self) -> None:
        """Abre (ou traz para frente) a janela flutuante do PACS."""
        from ipe.auth import session as S
        if self.meeting is not None or getattr(self, "_privacy_on", False):
            QMessageBox.information(self, "PACS", "O PACS fica indisponível enquanto os dados do paciente "
                                    "estão ocultos (reunião / Ocultar).")
            return
        if not S.require("query", self):
            return
        self.pacs_window.show_front()

    # ------------------------------------------------------------ usuário e permissões
    def _fill_user_menu(self, menu=None) -> None:
        from ipe.auth import session as S
        m = menu or self.user_menu
        m.clear()
        cur = S.get()
        a = QAction(cur.label, m)
        a.setEnabled(False)
        m.addAction(a)
        m.addSeparator()
        a = QAction("Alterar minha senha…", m)
        a.setEnabled(self.auth is not None and cur.user_id is not None)
        a.triggered.connect(self.change_password)
        m.addAction(a)
        a = QAction("Trocar de usuário…", m)
        a.setEnabled(self.auth is not None)
        a.triggered.connect(self.switch_user)
        m.addAction(a)
        m.addSeparator()
        a = QAction("Usuários e permissões…", m)
        a.setEnabled(S.can("users"))
        a.triggered.connect(lambda: self.open_users())
        m.addAction(a)
        a = QAction("Registro de acesso…", m)
        a.setEnabled(S.can("users"))
        a.triggered.connect(lambda: self.open_users(tab=2))
        m.addAction(a)

    def open_users(self, tab: int = 0) -> None:
        from ipe.auth import session as S
        from ipe.ui.users_dialog import UsersDialog
        if not S.require("users", self):
            return
        dlg = UsersDialog(self.repo, self.settings, self, local_mode=not getattr(self.repo, "remote", False))
        dlg.tabs.setCurrentIndex(tab)
        dlg.exec()

    def change_password(self) -> None:
        from ipe.auth import session as S
        from ipe.ui.login import ChangePasswordDialog
        if self.auth is not None:
            ChangePasswordDialog(self.auth, S.get(), self).exec()

    def switch_user(self) -> bool:
        """Fecha os exames abertos, sai e pede outro login."""
        from ipe.auth import session as S
        from ipe.ui.login import LoginDialog
        if self.auth is None:
            return False
        dlg = LoginDialog(self.auth, self.settings, self)
        if dlg.exec() != LoginDialog.Accepted or dlg.session is None:
            return False
        for i in reversed(range(self.tabs.count())):
            if isinstance(self.tabs.widget(i), ViewerTab):
                self._close_tab(i)
        S.audit(self.repo, "logout", "")
        self.settings.save()
        self.start_session(dlg.session)
        return True

    def start_session(self, s) -> None:
        from ipe.auth import session as S
        S.set_current(s)
        if self.auth is not None:
            self.settings.attach_user(self.auth.prefs(s), lambda p, ss=s: self.auth.save_prefs(ss, p))
        S.audit(self.repo, "login", "")
        self.apply_permissions()

    def apply_permissions(self) -> None:
        from ipe.auth import session as S
        cur = S.get()
        self.user_label.setText(f"Usuário: {cur.full_name or cur.username} · {cur.role_name}")
        self.browser.apply_permissions()
        for a in [x for w in [self, *self.detached] for x in w.menuBar().actions()]:
            menu = a.menu()
            if menu is None:
                continue
            for act in menu.actions():
                t = act.text()
                if t.startswith("Importar") and "lista" not in t:
                    act.setEnabled(cur.can("import"))
                elif t.startswith(("Configurar nós", "Automação", "Configurar servidor central")):
                    act.setEnabled(cur.can("configure"))
                elif t.startswith("Exportar"):
                    act.setEnabled(cur.can("export"))
        self.home_bar.apply_permissions()
        if not cur.can("query"):
            self.pacs_window.hide()

    # ------------------------------------------------------------ preferências
    def _vigiar_series(self) -> None:
        """De 3 em 3 s: algum exame aberto ganhou (ou perdeu) série ou imagem no banco? Refaz a tira
        daquela aba. Uma consulta só, e só com exame aberto."""
        tabs = self.all_viewer_tabs()
        if not tabs:
            self._assin_exames = {}
            return
        uids = sorted({u for t in tabs for u in (getattr(t, "study_order", None) or [t.study_uid])})
        try:
            atual = self.repo.assinatura_dos_exames(uids)
        except Exception as e:  # noqa: BLE001
            log.debug("vigiar séries: %s", e)
            return
        antes, self._assin_exames = self._assin_exames, atual
        for uid, sig in atual.items():
            if uid not in antes or antes[uid] == sig:
                continue
            for t in tabs:
                if uid in (getattr(t, "study_order", None) or [t.study_uid]):
                    try:
                        t.rescan(uid)
                    except Exception:  # noqa: BLE001
                        log.exception("atualizar a tira de séries")

    def _series_changed(self) -> None:
        """Série oculta ou apagada no banco: as abas abertas refazem a tira de séries."""
        for t in self.all_viewer_tabs():
            try:
                t.recarregar_series()
            except Exception:  # noqa: BLE001
                log.exception("recarregar séries da aba")

    def open_preferences(self, tab: str = "") -> None:
        from ipe.ui.preferences import PreferencesDialog
        dlg = PreferencesDialog(self.settings, self)
        if tab:
            for i in range(dlg.tabs.count()):
                if dlg.tabs.tabText(i) == tab:
                    dlg.tabs.setCurrentIndex(i)
        if dlg.exec():
            self.cache.set_limit(self.cache_limit_mb())
            self._update_status()
            # Mudou o papel dos monitores? A janela principal tem que sair de cima de um viewer
            # agora, e não só na próxima vez que o programa abrir.
            self.recolocar_janela_principal()
            self.sync_hub.recarregar_regras()          # sincronização automática por modalidade (0.99.9)
            for tab in self.all_viewer_tabs():
                tab.apply_shortcuts()
                tab.update_modality_buttons()          # módulos ligados/desligados (0.84)
                tab.reflect_anotacoes()                # o nível e os itens de anotação (0.99.9)
                tab.reflect_sync_flags()
                for vp in tab.viewports:
                    vp.update()
            self.aplicar_modulos()
            self.statusBar().showMessage("Preferências salvas.", 5000)

    def open_report(self, study_uid: str) -> None:
        """Laudo do exame: pela aba aberta, se houver; senão numa janela própria."""
        for t in self.all_viewer_tabs():
            if study_uid in t.study_order:
                t.open_report(study_uid)
                return
        wins = self.__dict__.setdefault("_report_windows", {})
        w = wins.get(study_uid)
        if w is not None and w.isVisible():
            w.raise_()
            w.activateWindow()
            return
        from types import SimpleNamespace
        from ipe.ui.report_window import ReportWindow
        shim = SimpleNamespace(cache=self.cache, storage_root=self.storage, overlay_objects=[],
                               anonymize=bool(getattr(self, "_privacy_on", False)))
        w = ReportWindow(self.repo, study_uid, self.settings, shim, self)
        w.saved.connect(lambda _u: self.browser.refresh())
        wins[study_uid] = w
        w.show()

    def _focar_aba(self, _i: int = -1) -> None:
        """Ao trocar de aba, o teclado vai para o exame: ← → andam nas etapas, não nas abas."""
        def focar():
            tab = self.tabs.currentWidget()
            if not isinstance(tab, ViewerTab):
                return
            vp = getattr(tab, "active", None)
            alvo = vp if vp is not None and vp.isVisible() else tab
            alvo.setFocus(Qt.OtherFocusReason)
        QTimer.singleShot(0, focar)

    def all_viewer_tabs(self) -> list[ViewerTab]:
        tabs = [self.tabs.widget(i) for i in range(1, self.tabs.count())]
        for d in self.detached:
            tabs += d.viewer_tabs()
        return [t for t in tabs if isinstance(t, ViewerTab)]

    # ------------------------------------------------------------ multimonitor
    def telas_na_ordem(self) -> list:
        from ipe.ui.monitors import telas_ordenadas
        return telas_ordenadas(self.settings)

    def _fill_monitor_menu(self, menu=None) -> None:
        menu = menu or self.monitor_menu
        menu.clear()
        for i, screen in enumerate(self.telas_na_ordem(), 1):
            g = screen.geometry()
            a = QAction(f"Monitor {i}: {screen.name()}  ({g.width()}×{g.height()})", menu)
            a.triggered.connect(lambda _=False, s=screen: self._detach_current(s))
            menu.addAction(a)

    def open_on_monitor(self, study_uid: str, screen=None) -> bool:
        """Abre o exame e leva a aba para o monitor (o do papel "Viewer" se não disser qual)."""
        self.open_study(study_uid)
        w = self.tabs.currentWidget()
        if isinstance(w, ViewerTab) and getattr(w, "study_uid", None) == study_uid:
            self.detach_tab(w, screen)
            return True
        return False

    def _detach_current(self, screen=None) -> None:
        w = self.aba_atual()
        if isinstance(w, ViewerTab):
            self.detach_tab(w, screen)
        else:
            self.statusBar().showMessage("Abra um estudo primeiro.", 5000)

    def window_for_screen(self, screen, restrito: bool = False) -> ScreenWindow:
        """A janela daquele monitor. `restrito`: a janela sem banco de dados da chamada externa —
        uma coisa diferente da janela normal do mesmo monitor, e não pode ser confundida com ela."""
        key = screen_key(screen)
        for d in self.detached:
            if d.screen_key == key and bool(getattr(d, "restrito", False)) == bool(restrito):
                return d
        win = ScreenWindow(self, screen, restrito=restrito)
        self.detached.append(win)
        if restrito:
            self._janela_externa = win
        self.apply_permissions()             # a barra de menu nova obedece às mesmas permissões
        return win

    def telas_de_visualizacao(self) -> list:
        """Os monitores em que um exame deve aparecer, na ordem do usuário."""
        from ipe.ui.monitors import telas_ordenadas
        return screens_with_role(self.settings, "viewer") or telas_ordenadas(self.settings)

    def detach_tab(self, tab: ViewerTab, screen=None) -> None:
        """Move o estudo para a janela do monitor escolhido (maximizada)."""
        idx = self.tabs.indexOf(tab)
        if idx < 0:
            return
        if screen is None:
            mine = self.screen()
            screen = screen_with_role(self.settings, "viewer", exclude=mine)
            if screen is None:
                others = [s for s in QGuiApplication.screens() if s is not mine]
                screen = others[0] if others else mine
        self.tabs.removeTab(idx)
        self.window_for_screen(screen).add_tab(tab)

    def reattach(self, win: ScreenWindow) -> None:
        """Devolve à janela principal os estudos de uma janela de monitor."""
        if win in self.detached:
            self.detached.remove(win)
        for tab in win.viewer_tabs():
            win.take_tab(tab)
            idx = self.tabs.addTab(tab, tab.title()[:40])
            self.tabs.setTabToolTip(idx, tab.title())
            self.tabs.setCurrentIndex(idx)

    def fechar_exames_e_voltar_ao_banco(self) -> bool:
        """Fecha o que estiver aberto em todas as telas e devolve a janela do banco de dados.

        É o que o X faz enquanto houver exame aberto. Antes ele fechava **só aquela janela** e
        deixava as outras de pé: o médico clicava no X achando que tinha fechado o programa e
        ficava com meia estação aberta num monitor que ele não estava olhando.
        """
        if self._fechando_exames:
            return False
        abertos = self.all_viewer_tabs()
        if not abertos:
            return False
        self._fechando_exames = True
        try:
            for t in abertos:
                t.monitor_group = []          # já estamos fechando todas: nada de arrastar de volta
            for t in abertos:
                self.fechar_aba(t)
            for win in list(self.detached):
                if win in self.detached:
                    self.detached.remove(win)
                win.close()
        finally:
            self._fechando_exames = False
        self.show_on_configured_screen()
        self.showNormal() if self.isMinimized() else None
        self.raise_()
        self.activateWindow()
        self.statusBar().showMessage("Exame fechado em todos os monitores.", 6000)
        return True

    def reattach_all(self) -> None:
        for win in list(self.detached):
            self.reattach(win)
            win.close()

    def discard_tab(self, tab) -> None:
        if isinstance(tab, ViewerTab):
            try:
                tab.guardar_layout()
            except Exception:  # noqa: BLE001 - lembrar o layout não pode impedir fechar o exame
                log.debug("não consegui guardar o layout deste exame", exc_info=True)
        # exame repartido entre monitores: as abas vão juntas. Zerar o grupo antes de fechar os
        # irmãos é o que impede a volta infinita.
        grupo = [t for t in (getattr(tab, "monitor_group", None) or []) if t is not tab]
        if grupo:
            tab.monitor_group = []
            for outro in grupo:
                outro.monitor_group = []
            for outro in grupo:
                self.fechar_aba(outro)
        if tab is self._film_host:
            self._release_film()          # o filme não fecha junto com o estudo
        if isinstance(tab, ViewerTab):
            self.sync_hub.unregister(tab)
            strip = getattr(tab, "strip", None)
            if strip is not None:
                # os itens saem pelo Python, não pelo destrutor do Qt (queda do Shiboken, 0.79)
                from ipe.ui.tabelas import esvaziar_lista
                esvaziar_lista(strip)
        tab.deleteLater()

    def recolocar_janela_principal(self) -> None:
        """Leva a janela do banco para a tela que o papel dos monitores indica, se não estiver lá."""
        alvo = tela_da_janela_principal(self.settings)
        if alvo is None or alvo is self.screen():
            return
        if self.windowHandle() is not None:
            self.windowHandle().setScreen(alvo)
        self.setGeometry(alvo.availableGeometry())
        self.showMaximized()

    def show_on_configured_screen(self) -> None:
        """Mostra a janela principal no monitor com o papel "banco de dados", se houver.

        Abre **maximizada** por padrão: numa estação de laudo a janela do banco ocupa a tela
        inteira, e abrir num retângulo no meio do monitor é trabalho repetido todo dia. Quem
        preferir o contrário desliga em Preferências ▸ Geral.
        """
        screen = tela_da_janela_principal(self.settings)
        self.show()
        if screen is not None and screen is not self.screen():
            if self.windowHandle() is not None:
                self.windowHandle().setScreen(screen)
            self.setGeometry(screen.availableGeometry())
        if self.abre_maximizada():
            self.showMaximized()

    def abre_maximizada(self) -> bool:
        return bool(self.settings.get("ui.start_maximized", True))

    def trazer_para_a_frente(self) -> None:
        """Põe a janela principal na frente sem desfazer o que o usuário arrumou.

        `showNormal()` **desmaximiza**: a janela saía do monitor do banco de dados e voltava para
        a geometria de antes, na tela primária. Quem chama de fora quer a janela à vista, não a
        janela remanejada. Então só tiramos o "minimizada" e mantemos o resto do estado; se ela
        estava escondida (bandeja), aí sim reabre, e no monitor configurado.
        """
        escondida = not self.isVisible()
        if self.isMinimized():
            self.setWindowState((self.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        if escondida:
            self.show_on_configured_screen()
        self.raise_()
        self.activateWindow()

    def ir_para_o_banco(self) -> None:
        """No monitor viewer não há lista de exames: traz a janela principal para a frente."""
        self.tabs.setCurrentWidget(self.browser)
        self.raise_()
        self.activateWindow()

    def janela_ativa(self):
        """A janela em que o usuário está. O menu é o mesmo nos monitores; o alvo, não.

        Sem isto, clicar em "Layout 2 × 2" no monitor da direita mexeria no exame da esquerda —
        que é o tipo de coisa que faz o médico desistir do segundo monitor.
        """
        from PySide6.QtWidgets import QApplication
        w = QApplication.activeWindow()
        return w if w in self.detached else self

    def aba_atual(self):
        return self.janela_ativa().tabs.currentWidget()

    def janela_da_aba(self, tab):
        for w in [self, *self.detached]:
            if w.tabs.indexOf(tab) >= 0:
                return w
        return self

    def mostrar_status(self, msg: str, tab=None, ms: int = 8000) -> None:
        """A mensagem aparece no monitor em que a coisa aconteceu."""
        self.janela_da_aba(tab).statusBar().showMessage(msg, ms)

    def abas_do_conjunto(self, tab) -> list:
        """A aba e as irmãs dela nos outros monitores.

        Os monitores viewer são **uma estação**, não várias: o que o menu manda vale para o
        conjunto. Fora de um exame repartido, o conjunto é a própria aba.
        """
        grupo = [t for t in (getattr(tab, "monitor_group", None) or []) if t is not None]
        return grupo if tab in grupo else [tab]

    def _current_viewer_call(self, fn) -> None:
        w = self.aba_atual()
        if not isinstance(w, ViewerTab):
            return
        conjunto = self.abas_do_conjunto(w)
        for t in conjunto:
            try:
                fn(t)
            except Exception:  # noqa: BLE001 - um monitor que recusa não pode travar os outros
                log.debug("ação do menu falhou num dos monitores", exc_info=True)
        if len(conjunto) > 1:
            self.ligar_conjunto(conjunto)      # mudou o layout: os quadros novos entram na ligação

    def _open_data_folder(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.data)))

    def cache_limit_mb(self) -> int:
        return int(self.settings.get("performance.cache_mb", 0) or auto_cache_mb())

    def _update_status(self) -> None:
        vol_mb = sum(v.nbytes_mb for t in self.all_viewer_tabs() for v in t._volumes.values())
        ram = process_ram_mb()
        parts = []
        if ram is not None:
            parts.append(f"RAM do programa: {ram:,.0f} MB".replace(",", "."))
        parts.append(f"Cache de imagens: {self.cache.used_mb:.0f} / {self.cache.max_bytes / 1024 / 1024:.0f} MB")
        if vol_mb:
            parts.append(f"Volumes MPR: {vol_mb:.0f} MB")
        self.cache_label.setText("   ·   ".join(parts))

    # ------------------------------------------------------------ estudos
    def open_study(self, study_uid: str, series_uids: list[str] | None = None) -> None:
        """Abre o estudo (ou traz a aba para a frente). `series_uids`: só estas séries nos quadros
        (aceita "group:<id>" para uma dinâmica agrupada)."""
        tab = self._focus_open_study(study_uid)
        if tab is not None:
            if series_uids:
                tab.show_series(series_uids)
            return
        # monitores com papel "viewer" (fora o da janela principal)
        # Monitor marcado como viewer é viewer. A única exceção é o computador de uma tela só,
        # em que o único viewer é a tela da janela principal: ali o exame vira aba, como sempre
        # foi — abrir uma janela por cima do banco de dados não ajudaria ninguém. Com dois ou
        # mais, usam-se todos, inclusive o que estiver debaixo da janela principal: era isso que
        # fazia o segundo monitor ficar vazio.
        telas = screens_with_role(self.settings, "viewer")
        if len(telas) == 1 and telas[0] is self.screen():
            telas = []
        if len(telas) > 1 and self.abrir_dividido(study_uid, telas, series_uids):
            self.browser.refresh()
            self.auto.on_study_opened(study_uid)
            return
        target = telas[0] if telas else None
        layout = layout_for_screen(self.settings, target or self.screen())
        tab = self._make_tab(study_uid, layout, series_uids)
        if tab is None:
            return
        if target is not None:
            self.window_for_screen(target).add_tab(tab)
        else:
            title = tab.title()
            idx = self.tabs.addTab(tab, title[:40])
            self.tabs.setTabToolTip(idx, title)
            self.tabs.setCurrentIndex(idx)
        self.browser.refresh()
        self.auto.on_study_opened(study_uid)

    @staticmethod
    def repartir(itens: list, n: int) -> list:
        """Divide uma lista em `n` partes, na ordem, o mais iguais possível.

        Em ordem, e não intercalado, porque a ordem das séries já é a do protocolo: numa
        mamografia de quatro incidências isso põe as duas CC num monitor e as duas MLO no outro.
        """
        if n <= 0:
            return []
        tam, sobra = divmod(len(itens), n)
        partes, i = [], 0
        for k in range(n):
            passo = tam + (1 if k < sobra else 0)
            partes.append(itens[i:i + passo])
            i += passo
        return partes

    def abrir_dividido(self, study_uid: str, telas: list, series_uids=None,
                       restrito: bool = False) -> bool:
        """Abre o mesmo exame repartido entre os monitores viewer, uma aba em cada.

        As abas ficam amarradas: fechar uma fecha as outras, porque meio exame aberto em um
        monitor e nada no outro é pior do que não ter aberto.

        Tudo o que decide o arranjo é registrado no log e dito na barra de estado. Sem isso, um
        arranjo que não sobe é indistinguível de um arranjo que não existe — foi o que fez a
        mamografia parecer quebrada três vezes seguidas.
        """
        from ipe.ui.viewer.hanging import plano_de_monitores
        from ipe.ui.viewer.viewer_tab import _image_series
        try:
            linhas = _image_series(self.repo.series_for_study(study_uid))
        except Exception:  # noqa: BLE001
            log.debug("não consegui listar as séries para dividir", exc_info=True)
            return False
        todas = [s.series_uid for s in linhas]
        if series_uids:
            escolhidas = [u for u in todas if u in series_uids]
            todas = escolhidas or todas

        # Quem reparte é o protocolo, nesta ordem:
        # 1. mamografia: **uma** etapa para o conjunto, e cada tela mostra o pedaço dela que lhe
        #    cabe — com o modo mamografia inteiro em todas (barra, espelhamento, zoom por
        #    quadrante). Passar de etapa num monitor passa em todos.
        # 2. protocolo de exibição com plano por monitor (tudo menos mamografia);
        # 3. nada disso: as séries repartidas na ordem.
        info = self.repo.study_info(study_uid) or {}
        descricao = info.get("description", "")
        mods = {s.modality for s in linhas if s.modality}
        quantos = len(telas)
        mamografia = False
        etapas_repartidas = False
        planos = None
        if not series_uids:
            if "MG" in mods:
                from ipe.imaging.mammo import find_mg_protocol, passos_do_protocolo
                mg = find_mg_protocol(self.settings, descricao)
                if mg is None:
                    log.info("monitores: %r é MG mas nenhum protocolo de mamografia combina",
                             descricao)
                elif not passos_do_protocolo(mg):
                    log.info("monitores: o protocolo de mamografia %r não tem etapa nenhuma",
                             mg.get("name"))
                else:
                    mamografia = True
                    log.info("monitores: mamografia %r em %d telas, etapas: %s",
                             mg.get("name"), quantos,
                             [x.get("name") for x in passos_do_protocolo(mg)])
            else:
                from ipe.ui.viewer.etapas import achar
                com_etapas = achar(self.settings, mods, descricao)
                if com_etapas is not None:
                    # 0.88: protocolo com etapas — cada tela monta o pedaço dela de cada etapa
                    etapas_repartidas = True
                    log.info("monitores: protocolo com etapas %r em %d telas", com_etapas.get("name"),
                             quantos)
                else:
                    planos = plano_de_monitores(self.settings, mods, descricao, quantos)
                log.info("monitores: plano de exibição para %d telas: %s", quantos,
                         [p.get("nome") or p.get("layout") for p in planos] if planos else None)

        repartido = not mamografia and planos is None and not etapas_repartidas
        if repartido and len(todas) < 2:     # uma série só não se divide; com arranjo, nem precisa
            log.info("monitores: sem arranjo e com %d série(s) — o exame abre numa tela só",
                     len(todas))
            return False
        partes = [p for p in self.repartir(todas, quantos) if p] if repartido \
            else [None] * quantos
        if repartido and len(partes) < 2:
            return False
        abas = []
        for i, (tela, parte) in enumerate(zip(telas, partes)):
            plano = planos[i] if planos else None
            alvo = tuple(plano["layout"]) if plano else layout_for_screen(self.settings, tela)
            tab = self._make_tab(study_uid, alvo, parte, plano=plano,
                                 mg_monitor=i if mamografia else None, mg_telas=quantos,
                                 monitor_idx=i)
            if tab is None:
                break
            self.window_for_screen(tela, restrito=restrito).add_tab(tab)
            abas.append(tab)
        if len(abas) < 2:                        # não deu para abrir nos dois: desfaz e segue o caminho normal
            for t in abas:
                self.fechar_aba(t)
            return False
        for t in abas:
            t.monitor_group = abas
        self.ligar_conjunto(abas)
        resumo = self.resumo_do_arranjo(abas)
        for t in abas:                       # o estado aparece em **todas** as telas do conjunto
            self.mostrar_status(resumo, t)
        log.info("monitores: %s", resumo)
        return True

    @staticmethod
    def resumo_do_arranjo(abas: list) -> str:
        """O que está em cada monitor, em uma linha. É o estado na tela, não só no log."""
        partes = []
        etapa = ""
        for i, t in enumerate(abas, 1):
            s = getattr(t, "mg_session", None)
            if s is not None and s.steps:
                etapa = s.steps[s.step].get("name") or ""
                from ipe.imaging.mammo import quadro_da_etapa
                q = quadro_da_etapa(s.steps[s.step], getattr(t, "mg_telas", 1) or 1,
                                    getattr(t, "mg_monitor", 0) or 0)
                celulas = [c for c in (q.get("cells") or []) if c]
                partes.append(f"Monitor {i}: {', '.join(celulas) if celulas else 'mamografia'}")
            elif getattr(t, "hanging_name", ""):
                partes.append(f"Monitor {i}: {t.hanging_name}")
            else:
                partes.append(f"Monitor {i}: séries do exame")
        detalhe = " · ".join(partes)
        if etapa:
            return f"Exame em {len(abas)} monitores, ligados entre si — etapa “{etapa}” — {detalhe}"
        return f"Exame em {len(abas)} monitores, ligados entre si — {detalhe}"

    def ligar_conjunto(self, abas=None) -> None:
        """Liga os quadros dos monitores do conjunto: rolagem, janela e zoom andam juntos.

        É o que o usuário quer dizer com "os monitores agem como se fossem um": clicar num ponto
        numa tela leva as outras ao mesmo lugar. Pode ser desligado em Preferências ▸ Monitores,
        para quem prefere cada tela por conta própria.
        """
        if not self.settings.get("monitors.sync_group", True):
            return
        abas = [t for t in (abas or []) if t is not None]
        if len(abas) < 2:
            return
        for t in abas:
            self.sync_hub.register(t)
        quadros = [v for t in abas for v in t._shown() if getattr(v, "frames", None)]
        if len(quadros) < 2:
            return
        self.sync_hub.link_all(quadros, 1)
        self.sync_hub.set_flag("sync_wl", True)
        self.sync_hub.set_flag("sync_zoom", True)

    def fechar_aba(self, tab) -> None:
        """Tira a aba da janela que a contém e a descarta — venha ela de onde vier."""
        for win in [self, *self.detached]:
            idx = win.tabs.indexOf(tab)
            if idx >= 0:
                win.tabs.removeTab(idx)
                self.discard_tab(tab)
                if win is not self and win.tabs.count() == 0:
                    win.close()
                return

    def open_from_browser(self, study_uid: str) -> None:
        """Duplo clique no banco: pergunta as séries se o estudo tiver muitas (Preferências)."""
        limit = int(self.settings.get("viewer.ask_series_above", 0) or 0)
        if limit and self._focus_open_study(study_uid) is None \
                and len(self.repo.series_for_study(study_uid)) > limit:
            self.choose_series(study_uid)
        else:
            self.open_study(study_uid)

    def open_comparison(self, study_uids: list) -> bool:
        """Abre vários exames na mesma aba, o mais recente como atual e os outros como anteriores.

        Antes de juntar, confere a identidade: se nome, ID, nascimento ou sexo não batem,
        mostra o que difere e pergunta. Juntar exames de pacientes diferentes sem avisar é
        como um laudo sai trocado.
        """
        from ipe.ui import compare_studies as CS
        uids = [u for u in dict.fromkeys(study_uids) if u]
        if not uids:
            return False
        if len(uids) == 1:
            self.open_from_browser(uids[0])
            return True
        infos = [self.repo.study_info(u) or {"study_uid": u} for u in uids]
        if not CS.confirm(self, infos):
            self.statusBar().showMessage("Comparação cancelada: os exames não são do mesmo paciente.",
                                        6000)
            return False
        ordem = [str(i.get("study_uid") or "") for i in CS.order(infos)]
        self.open_study(ordem[0])
        aba = self.tabs.currentWidget()
        if not hasattr(aba, "add_study"):
            return False
        for u in ordem[1:]:
            aba.add_study(u)
        n = len(ordem)
        if CS.differences(infos):
            recado = f"{n} exames abertos juntos para comparação — atenção, as identidades diferem."
        else:
            recado = f"{n} exames abertos juntos para comparação."
        self.statusBar().showMessage(recado, 8000)
        return True

    def choose_series(self, study_uid: str) -> None:
        from ipe.ui.series_chooser import SeriesChooserDialog
        dlg = SeriesChooserDialog(self.repo, study_uid, parent=self)
        if dlg.exec() and dlg.chosen():
            self.open_study(study_uid, dlg.chosen())

    def instalar_segmentacao(self) -> None:
        """Arquivo ▸ Instalar a segmentação: o TotalSegmentator é baixado uma vez, à parte (0.98)."""
        from ipe.ui.segmentacao import abrir_instalador
        abrir_instalador(self)

    def _segmentacao_pronta(self, study_uid: str, saida) -> None:
        """Órgãos segmentados pelo banco: o exame aberto ganha as máscaras sem precisar reabrir."""
        from ipe.ui.segmentacao import carregar_na_aba
        for t in self.all_viewer_tabs():
            if study_uid in (getattr(t, "study_order", None) or [t.study_uid]):
                carregar_na_aba(t, saida)

    def _implante_pronto(self, study_uid: str) -> None:
        """As cópias sem implante de um exame ficaram prontas (0.97). Se ele já está aberto no
        protocolo de mamografia, a etapa é refeita para os quadros pegarem as cópias."""
        for t in self.all_viewer_tabs():
            s = getattr(t, "mg_session", None)
            if s is None or study_uid not in (getattr(t, "study_order", None) or [t.study_uid]):
                continue
            try:
                s._images.clear()
                s.apply_step(s.step)
                t.status_message.emit("Implante corrigido: os quadros mostram as imagens sem o silicone "
                                      "(a original continua um passo atrás na lista do quadro).")
            except Exception:  # noqa: BLE001
                log.exception("refazer a etapa depois do implante corrigido")

    def _focus_open_study(self, study_uid: str) -> ViewerTab | None:
        for i in range(1, self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, ViewerTab) and w.study_uid == study_uid:
                self.tabs.setCurrentIndex(i)
                return w
        achada = None
        for d in self.detached:
            for t in d.viewer_tabs():
                if t.study_uid == study_uid:
                    d.tabs.setCurrentWidget(t)
                    d.raise_()
                    if achada is None:           # a primeira fica com o foco; as outras só aparecem
                        d.activateWindow()
                        achada = t
        return achada

    def _make_tab(self, study_uid: str, layout=None, series_uids=None,
                  plano=None, mg_monitor=None, mg_telas=1, monitor_idx=0) -> ViewerTab | None:
        from ipe.auth import session as S
        if not S.require("view", self):
            return None
        ensure = getattr(self.repo, "ensure_local", None)
        if ensure is not None and not ensure(study_uid, self):
            return None
        info = self.repo.study_info(study_uid) or {}
        S.audit(self.repo, "abrir", f"{info.get('patient_name', '')} — {info.get('study_date', '')} "
                f"{info.get('modalities', '')} {info.get('description', '')}", study_uid=study_uid)
        try:
            tab = ViewerTab(self.repo, self.cache, self.settings, study_uid, hub=self.sync_hub,
                            layout=layout, series_filter=series_uids, plano=plano,
                            mg_monitor=mg_monitor, mg_telas=mg_telas, monitor_idx=monitor_idx)
        except Exception as e:  # noqa: BLE001
            log.exception("Falha ao abrir estudo")
            QMessageBox.critical(self, "Erro", f"Não foi possível abrir o estudo:\n{e}")
            return None
        tab.detach_requested.connect(lambda t: self.detach_tab(t))
        tab.status_message.connect(lambda msg, t=tab: self.mostrar_status(msg, t))
        tab.open_prior_requested.connect(self.open_prior_on_compare)
        tab.film_requested.connect(lambda req, t=tab: self.film_request(req, t))
        tab.preferences_requested.connect(self.open_preferences)
        tab.anotacoes_mudaram.connect(lambda _n: [t.reflect_anotacoes() for t in self.all_viewer_tabs()])
        tab.compare_handler_connected = True
        tab.net = self.net
        tab.storage_root = self.storage
        if self.meeting is not None:           # modo reunião: tudo o que abrir já vem sem dados do paciente
            tab.set_anonymize(True)
            tab.anon_action.setChecked(True)
            tab.anon_action.setEnabled(False)
            self._privacy_restore.append(tab)   # volta a mostrar quando a reunião acabar
        return tab

    def export_current(self) -> None:
        """Exporta o que está na frente: o exame da aba atual ou os selecionados no banco."""
        w = self.aba_atual()
        if isinstance(w, ViewerTab):
            w.export_dialog()
        else:
            self.tabs.setCurrentWidget(self.browser)
            self.browser.export_selected()

    # ------------------------------------------------------------ listas e modo reunião
    def start_meeting(self, list_id: int, start: int = 0) -> None:
        from ipe.ui.caselists import MeetingController
        if self.meeting is not None:
            self.meeting.end()
        mc = MeetingController(self, list_id)
        mc.finished.connect(lambda: setattr(self, "meeting", None))
        self.meeting = mc
        if not mc.start(start):
            self.meeting = None

    def set_privacy(self, on: bool, case_names: dict[str, str] | None = None) -> None:
        """Esconde os dados do paciente em todo o programa (banco, abas, quadros, filme, PACS)."""
        self.browser.set_privacy(on, case_names)
        self._privacy_on = on
        if on:
            self.pacs_window.hide()
            if getattr(self, "gestao_window", None) is not None:
                self.gestao_window.hide()
            if getattr(self, "_film_dashboard", None) is not None:
                self._film_dashboard.hide()          # tem nome de paciente na lista
        self.home_bar.buttons["pacs"].setEnabled(not on and self._can("query"))
        self.home_bar.buttons["gestao"].setEnabled(not on and self._can("query"))
        anon = self.home_bar.buttons["anon"].defaultAction()
        anon.blockSignals(True)
        anon.setChecked(on)
        anon.blockSignals(False)
        if on:
            self._privacy_restore = []
            for t in self.all_viewer_tabs():
                if not t.anonymize:
                    self._privacy_restore.append(t)
                    t.set_anonymize(True)
                t.anon_action.setEnabled(False)
            if self._film is not None:
                self._privacy_restore.append(("film", self._film.film.anonymize))
                self._film.chk_anon.setChecked(True)
                self._film.chk_anon.setEnabled(False)
        else:
            for t in self._privacy_restore:
                if isinstance(t, tuple):
                    if self._film is not None:
                        self._film.chk_anon.setEnabled(True)
                        self._film.chk_anon.setChecked(bool(t[1]))
                    continue
                try:
                    t.set_anonymize(False)
                    t.anon_action.setChecked(False)
                except RuntimeError:
                    pass                  # aba já fechada
            for t in self.all_viewer_tabs():
                if not t.case_label:
                    t.anon_action.setEnabled(True)
            if self._film is not None:
                self._film.chk_anon.setEnabled(True)
            self._privacy_restore = []

    def import_case_list(self, parent_folder=None) -> None:
        from ipe.ui.caselists import import_dialog
        lid = import_dialog(self, self.repo, self.db, self.storage, parent_folder)
        if lid is not None:
            self.browser.tree.rebuild(select=lid)
            self.browser._list_selected(lid)
            self.browser.refresh()

    # ------------------------------------------------------------ filme
    def film_composer(self):
        if self._film is None:
            from ipe.ui.film.composer import FilmComposer
            self._film = FilmComposer(self.repo, self.cache, self.settings, None,
                                      local_ae_fn=lambda: self.net.local_ae)
            self._film.status_message.connect(lambda msg: self.statusBar().showMessage(msg, 8000))
            self._film.open_study_requested.connect(lambda st, series: self.open_study(st, series))
            self._film.storage_root = self.storage
            self._film.saved_to_study.connect(lambda _st: (self.browser.refresh(), self._series_changed()))
            self._film.expand_requested.connect(self._film_expand)
            self._film.close_requested.connect(self._film_close)
        return self._film

    def _film_expand(self) -> None:
        host = self._film_host
        if isinstance(host, ViewerTab):
            host.toggle_film_expanded()
        elif host is not None:
            host.setWindowState(host.windowState() ^ Qt.WindowMaximized)

    def _film_close(self) -> None:
        host = self._film_host
        if isinstance(host, ViewerTab):
            host.hide_film_panel()
        elif host is not None:
            host.hide()

    def _release_film(self) -> None:
        comp, host = self._film, self._film_host
        if comp is None or host is None:
            return
        if isinstance(host, ViewerTab):
            host.release_film(comp)
        else:
            host.layout().removeWidget(comp)
            comp.setParent(None)
            host.hide()
        self._film_host = None

    def dock_film(self, tab=None) -> None:
        """Mostra o filme como painel do estudo (ao lado dos quadros). Sem estudo aberto, numa janela."""
        comp = self.film_composer()
        if tab is None:
            w = self.aba_atual()
            tab = w if isinstance(w, ViewerTab) else None
        if tab is not None:
            if self._film_host is not tab:
                self._release_film()
                self._film_host = tab
            tab.show_film_panel(comp)
            return
        if self._film_window is None:
            from PySide6.QtWidgets import QVBoxLayout, QWidget
            win = QWidget(self, Qt.Window)
            win.setWindowTitle(f"Filme — {APP_NAME}")
            win.resize(1200, 850)
            QVBoxLayout(win).setContentsMargins(4, 4, 4, 4)
            self._film_window = win
        win = self._film_window
        if self._film_host is not win:
            self._release_film()
            win.layout().addWidget(comp)
            comp.show()
            self._film_host = win
        comp.set_docked(False)
        win.show()
        win.raise_()

    def show_film(self) -> None:
        """Ctrl+P: abre/fecha o painel do filme no estudo atual (ou a janela do filme)."""
        w = self.aba_atual()
        if isinstance(w, ViewerTab) and self._film_host is w and w.film_panel_visible():
            w.hide_film_panel()
            return
        self.dock_film(w if isinstance(w, ViewerTab) else None)

    def film_request(self, req: dict, tab=None) -> None:
        """Pedidos do visualizador/banco: imagens, série/intervalo, imagens-chave, filmes salvos ou
        abrir/fechar o painel."""
        comp = self.film_composer()
        kind = req.get("kind")
        if kind == "show":
            if tab is not None and self._film_host is tab and tab.film_panel_visible():
                tab.hide_film_panel()
            else:
                self.dock_film(tab)
            return
        if kind == "saved":
            self.dock_film(tab)
            comp.open_saved(req.get("study_uid"))
            return
        if tab is not None and not (self._film_host is tab and tab.film_panel_visible()):
            self.dock_film(tab)
        if kind == "images":
            n = comp.add_images(req.get("items", []))
        elif kind == "series":
            n = comp.add_series_range(req["series_uid"], current_index=int(req.get("index", 0)),
                                      view=req.get("view") or {}, parent=tab or self)
        elif kind == "keys":
            n = comp.add_key_images(req["study_uid"])
            if n and tab is None:
                self.dock_film(None)
        else:
            return
        if n:
            self.statusBar().showMessage(
                f"{n} imagem(ns) no filme “{comp.film.name}” — {comp.film.image_count()} no total, "
                f"{len(comp.film.sheets)} folha(s). Ctrl+P mostra/esconde o filme.", 8000)

    def open_prior_on_compare(self, tab: ViewerTab, prior_uid: str) -> None:
        """Abre o exame anterior no monitor de comparação, ligado ao quadro ativo."""
        from ipe.ui.viewer.viewer_tab import match_series
        screen = screen_with_role(self.settings, "compare")
        if screen is None:
            tab.add_study(prior_uid)
            return
        ptab = self._focus_open_study(prior_uid)
        if ptab is None:
            ptab = self._make_tab(prior_uid, layout_for_screen(self.settings, screen))
            if ptab is None:
                return
            self.window_for_screen(screen).add_tab(ptab)
        src = tab.active
        ref = tab._series_row(src.series_uid) if src is not None else None
        m = match_series(ref, ptab.series)
        dst = ptab.viewports[0]
        if m is not None:
            ptab.load_series_into(dst, m.series_uid)
        if src is not None and src.frames and dst.frames and self.sync_hub.apply_saved(src, dst):
            msg = "Anterior aberto no monitor de comparação, alinhado como da última vez."
        else:
            msg = ("Anterior aberto no monitor de comparação. Alinhe os quadros e clique no ícone "
                   "de corrente dos dois (ou Ctrl+L) para rolarem juntos.")
        self.statusBar().showMessage(msg, 10000)

    def _close_tab(self, index: int) -> None:
        """Fecha qualquer aba que tenha o X — se o X existe, ele precisa funcionar.

        Só o Banco de dados não fecha, e por isso ele nem tem o botão. A aba de Impressões é
        guardada em `self._prints` e volta inteira quando for aberta de novo; a de exame é
        descartada de verdade, porque carrega imagem.
        """
        w = self.tabs.widget(index)
        if w is None or w is self.browser:
            return
        if self.meeting is not None and w is self.meeting.tab:
            self.meeting.end()                    # fechar a aba do caso encerra a reunião
            return
        self.tabs.removeTab(index)
        if isinstance(w, ViewerTab):
            self.discard_tab(w)
        else:
            w.setParent(self)                     # fica viva e escondida, para reabrir depois
            w.hide()
        self.tabs.setCurrentWidget(self.browser)      # ao fechar uma aba, volta ao banco de dados

    def handle_external(self, args: dict) -> str:
        """Chamada externa (linha de comando ou outra instância). Devolve mensagem."""
        if not self.so_viewer_do_pedido(args):
            self.trazer_para_a_frente()
        command = args.get("command", "open")
        so_viewer = self.so_viewer_do_pedido(args)
        if command == "status":
            active = len(self.net.active_jobs())
            return f"{self.net.server.status_text()}; {active} transferência(s) ativa(s)"
        if args.get("source", "").startswith(("http", "link")):
            log.info("Chamada externa (%s): %s", args.get("source"),
                     {k: v for k, v in args.items() if k != "source"})
        if args.get("paths"):
            self.import_dropped([Path(p) for p in args["paths"]])
            return "importando"
        uids = self.repo.find_study_uids(accession=args.get("accession", ""),
                                         study_uid=args.get("study_uid", ""),
                                         patient_id=args.get("patient_id", ""))
        if uids:
            if command == "retrieve":
                return "ja_no_banco"
            for uid in uids[: 1 if args.get("patient_id") else 4]:
                self.abrir_exame_do_pedido(uid, so_viewer)
            return "aberto"
        what = args.get("accession") or args.get("study_uid") or args.get("patient_id")
        nodes = self._search_nodes(args.get("node", ""))
        if not what or not nodes:
            self.statusBar().showMessage(f"Estudo não encontrado no banco local: {what}", 8000)
            return "nao_encontrado"
        self.statusBar().showMessage(f"Buscando {what} em {', '.join(n['name'] for n in nodes)}…", 8000)
        filters = {"accession": args.get("accession", ""), "study_uid": args.get("study_uid", ""),
                   "patient_id": args.get("patient_id", "")}
        open_after = command == "open"

        def found(res, err) -> None:
            from ipe.network import probe
            rows = (res or ([], []))[0] if err is None else []
            if not rows:
                errs = "; ".join((res or ([], []))[1]) if err is None else str(err)
                self.statusBar().showMessage(f"Estudo {what} não encontrado nos nós. {errs}", 12000)
                return
            rows.sort(key=lambda r: (r["study_date"], r["study_time"]), reverse=True)
            for r in rows[: 1 if args.get("patient_id") else 4]:
                node = self.repo.node(r["node_id"])
                label = f"{r['patient_name']} — {r['study_date']} {r['modalities']} {r['description']}"
                self.__dict__.setdefault("_janela_do_pedido", {})[r["study_uid"]] = so_viewer
                stream = open_after and probe.stream_externo(node, self.settings)
                self.net.retrieve(node, None, r["study_uid"], label,
                                  open_after=open_after, stream=stream)
            self.statusBar().showMessage(f"Baixando {what} de {rows[0]['node_name']}…", 8000)
        self.net.search(nodes, None, filters, found)
        return "buscando"

    def _search_nodes(self, name: str) -> list[dict]:
        nodes = [n for n in self.repo.nodes(only_active=True) if n["kind"] in NODES.CONSULTA]
        if name:
            return [n for n in nodes if name.lower() in (n["name"].lower(), n["ae_title"].lower())]
        return [n for n in nodes if n["use_in_search"]]

    # ------------------------------------------------------------ rede
    def start_services(self) -> None:
        """Liga o nó DICOM, a impressora DICOM e a API HTTP (chamado ao abrir o programa)."""
        self.net.start_server()
        self.net.start_print_servers()
        c = self.settings.get("dicom", {}) or {}
        if not c.get("http_token"):
            import secrets
            c["http_token"] = secrets.token_urlsafe(18)
            self.settings.set("dicom", c)
            self.settings.save()
        if c.get("http_enabled", True):
            self.http.start(int(c.get("http_port", 8042)), c["http_token"],
                            bool(c.get("http_allow_remote", False)), c.get("http_allowed_ips", []))
        else:
            self.http.stop()
        self._update_net_label()
        if not getattr(self.repo, "remote", False):     # no modo cliente a automação roda no servidor
            self.auto.start()
        self.start_central_server()
        # bancos de versões antigas: lê operador/estação/aparelho das séries em segundo plano
        from ipe.importer.backfill import backfill_nm_key_images, backfill_series_details
        self.net.run_async(lambda: backfill_series_details(self.repo),
                           lambda n, err: self.browser.refresh() if n else None)
        # exames de MN importados antes da 0.24: marca a folha de laudo como imagem-chave
        self.net.run_async(lambda: backfill_nm_key_images(self.repo),
                           lambda n, err: self.browser.refresh() if n else None)
        # impressões recebidas antes do cadastro de origens: monta a lista do que já chegou
        from ipe.printing import origins as O
        self.net.run_async(lambda: O.backfill(self.settings, self.repo.print_jobs(5000)),
                           lambda _n, _e: None)
        # compressão do que já passou do prazo: uma passagem agora e outra a cada 6 horas
        self._comprimindo = False
        self._compress_timer = QTimer(self)
        self._compress_timer.timeout.connect(self.compress_pass)
        self._compress_timer.start(6 * 60 * 60 * 1000)
        QTimer.singleShot(90_000, self.compress_pass)   # depois que a abertura acalmar

    # ------------------------------------------------------------ impressões
    def show_prints(self):
        """Abre (ou traz para a frente) a lista de impressões."""
        try:
            return self._show_prints()
        except Exception as e:  # noqa: BLE001
            log.exception("abrindo a lista de impressões")
            QMessageBox.critical(self, "Impressões",
                                 f"Não consegui abrir a lista de impressões:\n{e}\n\n"
                                 "O erro completo está no arquivo de registro (Ajuda ▸ Registro).")
            return None

    def _show_prints(self):
        from ipe.ui.prints_tab import PrintsTab
        if self._prints is None:
            self._prints = PrintsTab(self.repo, self.settings, self.net, self)
            self._prints.open_study.connect(self.open_study)
            self._prints.open_film.connect(self._open_saved_film)
            self._prints.status_message.connect(lambda t: self.statusBar().showMessage(t, 8000))
            self._prints.settings_requested.connect(self.open_print_settings)
            self._prints.release_requested.connect(self.release_held_rows)
            self._prints.identified.connect(self._on_print_identified)
            self._prints.dashboard_requested.connect(self.show_film_dashboard)
        if self.tabs.indexOf(self._prints) < 0:
            self.tabs.addTab(self._prints, "Impressões")
        self._prints.refresh()
        self.tabs.setCurrentWidget(self._prints)
        return self._prints

    def show_film_dashboard(self):
        """Painel de filmes e impressões (0.77): % impressos, tempos, por modalidade e usuário."""
        from ipe.auth import session as S
        if self.meeting is not None or getattr(self, "_privacy_on", False):
            QMessageBox.information(self, "Painel de filmes", "O painel de filmes fica indisponível "
                                    "enquanto os dados do paciente estão ocultos (reunião / Ocultar).")
            return None
        if not S.require("print", self):
            return None
        from ipe.ui.film_dashboard import FilmDashboard
        d = getattr(self, "_film_dashboard", None)
        if d is None:
            d = self._film_dashboard = FilmDashboard(self.repo, self.settings, self)
            d.abrir_filme.connect(self._open_saved_film)
            d.abrir_exame.connect(self.open_study)
        else:
            d.carregar()
        d.show()
        d.raise_()
        d.activateWindow()
        return d

    def open_gsdf(self) -> None:
        """Calibração GSDF: a escala de cinza deste monitor, com os padrões para conferir."""
        from ipe.auth import session as S
        if not S.require("configure", self):
            return
        from ipe.ui.gsdf_dialog import GsdfDialog
        if GsdfDialog(self.settings, self).exec():
            for t in self.all_viewer_tabs():
                for v in t.viewports:
                    v._qimage_key = None
                    v.update()
            self.statusBar().showMessage("Calibração do monitor atualizada.", 6000)

    def open_print_settings(self) -> None:
        """Servidores de impressão, destinos, regras, modelos de folha e montagem automática."""
        from ipe.auth import session as S
        if not S.require("configure", self):
            return
        from ipe.ui.print_settings import PrintSettingsDialog
        PrintSettingsDialog(self.settings, self.net, self, repo=self.repo).exec()
        self._update_net_label()

    def _open_saved_film(self, film_id: int) -> None:
        self.dock_film()
        self.film_composer().load_film(int(film_id))

    def _on_print_received(self, row) -> None:
        """Chegou um filme de alguma modalidade."""
        from ipe.printing import origins as O
        origem = O.job_origin(self.settings, row)
        quem = (origem.name if origem and origem.registered else "") \
            or (row or {}).get("calling_ae") or "uma modalidade"
        folhas = (row or {}).get("sheets", 0)
        if (row or {}).get("juntadas"):
            quem_pac = (row or {}).get("patient_name") or "o mesmo trabalho"
            self.show_notification("Impressão recebida", f"mais uma folha de {quem} juntada a {quem_pac} "
                                                         f"({folhas} folha(s))")
        else:
            self.show_notification("Impressão recebida", f"{folhas} folha(s) de {quem}")
        if origem is not None and not origem.registered:
            self.show_notification("Origem de impressão nova",
                                   f"{origem.calling_ae or '?'} em {origem.remote_host or '?'} "
                                   "ainda não está cadastrada; o trabalho ficou esperando.")
        if self._prints is not None:
            self._prints.refresh()
        self.browser.refresh()
        self._encaminhar_quando_parar(row)

    def _encaminhar_quando_parar(self, row) -> None:
        """0.99.6: com "juntar folhas" ligado, o trabalho espera a janela (padrão 90 s) sem folha nova
        antes de seguir a regra — senão a primeira folha sairia sozinha e as outras viriam depois.
        Cada folha que se junta recomeça a contagem."""
        from ipe.printing import juntar as JUN
        if not row or not JUN.ligado(self.settings) or row.get("source", "scp") != "scp":
            self._auto_forward(row)
            return
        timers = self.__dict__.setdefault("_esperando_juntar", {})
        rid = row.get("id")
        t = timers.get(rid)
        if t is None:
            t = QTimer(self)
            t.setSingleShot(True)

            def soltar(rid=rid) -> None:
                timers.pop(rid, None)
                atual = self.repo.print_job(rid)
                if atual is not None and atual.get("status") == "new":
                    self._auto_forward(atual)
            t.timeout.connect(soltar)
            timers[rid] = t
        t.start(JUN.segundos(self.settings) * 1000)

    def aplicar_modulos(self) -> None:
        """Módulos mudaram: a barra do banco, as portas de impressão e a aba de impressões."""
        from ipe import modules as MOD
        imp = MOD.ligado(self.settings, "impressao")
        hb = getattr(self, "home_bar", None)
        if hb is not None and "prints" in getattr(hb, "buttons", {}):
            hb.set_visible("prints", imp)
        try:
            if getattr(self.net, "print_servers", None) is not None:
                ligado_agora = any(s.running for s in self.net.print_servers)
                if imp or ligado_agora:
                    self.net.start_print_servers()
        except Exception:  # noqa: BLE001
            log.exception("servidores de impressão ao mudar os módulos")
        if not imp and self._prints is not None:
            i = self.tabs.indexOf(self._prints)
            if i >= 0:
                self.tabs.removeTab(i)

    def run_print_cleanup(self) -> int:
        """Limpeza da lista de impressões, pelos critérios de Configurações de impressão ▸ Limpeza."""
        from ipe import modules as M
        if not M.ligado(self.settings, "impressao"):
            return 0
        try:
            from ipe.printing import limpeza as LZ
            n = LZ.automatica(self.repo, self.settings)
        except Exception:  # noqa: BLE001
            log.exception("Limpeza automática das impressões")
            return 0
        if n:
            self.statusBar().showMessage(f"Limpeza automática: {n} trabalho(s) de impressão apagado(s).", 10000)
            if self._prints is not None:
                self._prints.refresh()
        return n

    def _auto_forward(self, row) -> None:
        """Encaminha sozinho quando uma regra manda (ou quando o servidor tem destino fixo).

        Trabalho de origem ainda não cadastrada fica parado na lista, de propósito: o destino
        depende de saber que aparelho mandou.
        """
        ok, motivo = self.forward_row(row)
        if not ok and motivo:
            self.statusBar().showMessage(motivo, 10000)

    def forward_row(self, row, avisar: bool = False) -> tuple[bool, str]:
        """Manda **um** trabalho pelo caminho das regras. Devolve (saiu, motivo de não ter saído).

        É o único caminho de saída: tanto o encaminhamento automático de quem acabou de chegar
        quanto a liberação em lote dos parados passam por aqui, senão existiriam dois jeitos
        diferentes de mandar o mesmo filme.
        """
        if not row:
            return False, ""
        from ipe.printing import held as HELD
        from ipe.printing import jobs as J
        from ipe.printing import origins as O
        from ipe.printing.dispatch import find_destination
        job = J.load(row.get("folder", "")) if row.get("folder") else None
        if job is None:
            return False, ""
        pode, motivo = O.may_forward(self.settings, row)
        if not pode:
            if self._prints is not None:
                self._prints.refresh()
            return False, motivo
        from ipe.printing import arrival
        if arrival.falta_paciente(self.settings, row):
            if self._prints is not None:
                self._prints.refresh()
            return False, ("O OCR não identificou o paciente do filme: ele ficou esperando você "
                           "confirmar em Impressões › Identificar paciente.")
        alvos = HELD.alvos(self.settings, row, job)
        if not alvos:
            return False, ""                        # sem regra: fica esperando você na lista
        aba = self.show_prints()
        saiu = False
        for nome, modelo in alvos:
            dest = find_destination(self.settings, nome)
            if dest is None:
                return False, f"Destino “{nome}” não existe mais; o trabalho ficou na lista."
            enviados, _falhas = aba.send_rows([dict(row, kind="scp")], dest, avisar=avisar,
                                              template=modelo, how="regra")
            saiu = saiu or bool(enviados)
        return saiu, ""

    def _on_print_images(self, info) -> None:
        """A modalidade mandou imagens comuns (não impressão) à porta da impressora: monta o filme
        com todas elas e segue a regra daquele servidor, como um filme impresso.

        O paciente vem nas próprias imagens, então não passa pelo OCR.
        """
        from datetime import datetime

        from ipe.printing import auto_film as AF
        from ipe.printing import held as HELD
        from ipe.printing import origins as O
        info = info or {}
        padrao = AF.config(self.settings)            # grade padrão, sem regra que combine
        try:
            estudos = {e for e, *_ in info.get("images", []) if e}
            filmes = []
            for estudo in estudos:                   # 0.86: cada exame pode cair numa regra diferente
                dados = self.repo.study_info(estudo) or {}
                regra = AF.escolher(self.settings, info.get("calling_ae", ""), info.get("my_ae", ""),
                                    dados.get("modalities", ""), dados.get("description", ""))
                cfg = regra.as_film_cfg() if regra is not None else padrao
                imgs = [x for x in info.get("images", []) if x[0] == estudo]
                filmes += [(e, f, regra, cfg) for e, f in AF.films_from_images(self.repo, imgs, cfg)]
        except Exception:  # noqa: BLE001
            log.exception("Montando o filme das imagens mandadas à impressora")
            return
        from ipe.printing import arrival
        for estudo, filme, regra, cfg in filmes:
            dados = self.repo.study_info(estudo) or {}
            linha = {"calling_ae": info.get("calling_ae", ""), "remote_host": info.get("remote_host", ""),
                     "server": info.get("server", ""), "label": filme.name, "film_size": cfg.paper,
                     "sheets": len(filme.sheets), "received_at": datetime.now(), "source": "scp",
                     "id_source": "exame", "modality": dados.get("modalities", "") or ""}
            # 0.89: OCR na chegada também para o filme montado com as imagens — o nome gravado na
            # imagem é procurado no banco; sem achar, o filme espera você confirmar o paciente
            encaminhar = {"linha": dict(linha, received_at=linha["received_at"].isoformat()),
                          "destino": regra.destination if regra is not None else "",
                          "modelo": regra.template if regra is not None else ""}
            achado, esperar = None, False
            if arrival.ligado(self.settings):
                achado = arrival.identificar_filme(self.repo, filme)
                esperar = achado is None
            if achado is not None:
                filme.paciente = {"patient_name": achado.get("patient_name", ""),
                                  "patient_id": achado.get("patient_id", ""), "id_source": "ocr"}
            elif esperar:
                filme.paciente = {"id_source": "aguardando", "encaminhar": encaminhar}
            nome = (achado or {}).get("patient_name") or dados.get("patient_name", "")
            film_id = self.repo.save_film(filme.name, filme.to_dict(), [estudo], nome)
            if achado is not None or esperar:
                self.repo.set_film_patient(film_id, nome, (achado or {}).get("patient_id", ""),
                                           "ocr" if achado is not None else "aguardando",
                                           {"encaminhar": encaminhar})
            self.show_notification("Imagens recebidas na impressora",
                                   f"Filme montado: {filme.name} ({filme.image_count()} imagem(ns))"
                                   + (" — esperando você confirmar o paciente" if esperar else ""))
            if self._prints is not None:
                self._prints.refresh()
            if esperar:
                self.statusBar().showMessage(
                    "O OCR não identificou o paciente do filme montado com as imagens recebidas: ele "
                    "ficou esperando você confirmar em Impressões › Identificar paciente.", 12000)
                continue
            pode, motivo = O.may_forward(self.settings, linha)
            if not pode:
                self.statusBar().showMessage(motivo, 10000)
                continue
            if regra is not None and regra.destination:      # a regra do Automático já diz para onde
                self._send_film(film_id, regra.destination, regra.template)
                continue
            for destino, modelo in HELD.alvos(self.settings, linha):
                self._send_film(film_id, destino, modelo)

    def _on_print_identified(self, row) -> None:
        """Você confirmou o paciente de um filme recebido: agora ele segue pela regra."""
        row = row or {}
        if row.get("kind") == "film":
            self._liberar_filme_montado(int(row.get("id", 0) or 0))
            return
        if (row.get("status") or "new") != "new" or (row.get("source") or "scp") != "scp":
            return                                  # já saiu (ou não veio da impressora)
        ok, motivo = self.forward_row(row)
        if ok:
            self.statusBar().showMessage("Paciente confirmado; o filme seguiu pela regra.", 8000)
        elif motivo:
            self.statusBar().showMessage(motivo, 10000)
        if self._prints is not None:
            self._prints.refresh()

    def _liberar_filme_montado(self, film_id: int) -> None:
        """Filme montado com imagens recebidas, que esperava o paciente: segue pela regra que valia
        quando chegou (a do Automático, se tinha destino; senão as regras daquele servidor)."""
        from ipe.printing import held as HELD
        from ipe.printing import origins as O
        dados = self.repo.film_data(film_id) or {}
        enc = (dados.get("paciente") or {}).get("encaminhar") or {}
        linha = dict(enc.get("linha") or {})
        if not linha:
            return
        pode, motivo = O.may_forward(self.settings, linha)
        if not pode:
            self.statusBar().showMessage(motivo, 10000)
            return
        alvos = [(enc["destino"], enc.get("modelo", ""))] if enc.get("destino") else HELD.alvos(self.settings, linha)
        for destino, modelo in alvos:
            self._send_film(film_id, destino, modelo)
        self.statusBar().showMessage("Paciente confirmado; o filme seguiu pela regra." if alvos else
                                     "Paciente confirmado. Nenhuma regra manda este filme para lugar "
                                     "nenhum: ele ficou na lista.", 8000)
        if self._prints is not None:
            self._prints.refresh()

    def release_held_rows(self, linhas: list) -> None:
        """Solta em lote os filmes que estavam parados. Um por um, pelo mesmo caminho."""
        enviados = falhas = 0
        for row in linhas or []:
            atual = self.repo.print_job_by_uid(row.get("uid", "")) or row
            try:
                ok, _motivo = self.forward_row(atual)
            except Exception:  # noqa: BLE001 - um filme ruim não pode parar a fila
                log.exception("Liberando o trabalho %s", row.get("uid", ""))
                ok = False
            enviados += 1 if ok else 0
            falhas += 0 if ok else 1
        if self._prints is not None:
            self._prints.held_done(enviados, falhas)

    def open_acervo_report(self) -> None:
        """Relatório do acervo: o que está guardado, em que formato, e o que a compressão renderia."""
        from ipe.ui.acervo_dialog import AcervoDialog
        AcervoDialog(self.repo, self.settings, self.studies_in_use(), self).exec()
        self.browser.refresh()

    def open_densidade(self, tab=None) -> None:
        """Densidade mamária do exame que está na tela. Sem exame aberto, diz isso e não abre nada."""
        aba = tab if isinstance(tab, ViewerTab) else self.aba_atual()
        if not isinstance(aba, ViewerTab):
            QMessageBox.information(self, "Densidade mamária",
                                    "Abra primeiro as imagens: a densidade é medida no que está "
                                    "nos quadros da tela.")
            return
        from ipe.ui.densidade_dialog import DensidadeDialog
        DensidadeDialog(aba, self).exec()

    def studies_in_use(self) -> list:
        """Exames que não podem ser reescritos agora: abertos numa aba ou ainda baixando."""
        uids = set()
        for aba in self.all_viewer_tabs():
            uids.update(getattr(aba, "study_order", None) or [getattr(aba, "study_uid", "")])
        try:
            for j in self.net.active_jobs():
                uids.update(getattr(j, "study_uids", None) or [])
        except Exception:  # noqa: BLE001 - saber o que está baixando é bônus, não pode derrubar
            log.debug("transferências ativas", exc_info=True)
        return sorted(u for u in uids if u)

    def compress_pass(self) -> None:
        """Passagem automática da compressão, em segundo plano. Só roda se estiver ligada."""
        from ipe.core import compress as K
        pol = K.Politica.from_settings(self.settings)
        if not pol.ligada or getattr(self.repo, "remote", False):
            return
        if self._comprimindo:
            return
        self._comprimindo = True
        em_uso = self.studies_in_use()

        def terminou(balanco, err) -> None:
            self._comprimindo = False
            if err is not None:
                log.exception("passagem da compressão", exc_info=err)
                return
            if balanco is not None and balanco.feitos:
                self.statusBar().showMessage(K.resumo(balanco), 10000)
                self.browser.refresh()
        self.net.run_async(lambda: K.run(self.repo, pol, pular_exames=em_uso), terminou)

    def start_central_server(self) -> None:
        """Liga (ou desliga) o servidor central se este computador for o servidor do grupo."""
        from ipe.central.server import CentralServer
        want = self.settings.get("central.mode", "local") == "server"
        if self.central is not None and (not want or self.central.port != int(self.settings.get("central.port", 8043))):
            self.central.stop()
            self.central = None
        if want and self.central is None:
            try:
                srv = CentralServer(self.db, self.repo, self.storage, port=int(self.settings.get("central.port", 8043)),
                                    certfile=self.settings.get("central.certfile", "") or "",
                                    keyfile=self.settings.get("central.keyfile", "") or "")
                srv.on_import = lambda _s: self._refresh_timer.start()
                srv.start()
                self.central = srv
            except OSError as e:
                QMessageBox.warning(self, "Servidor central", f"Não foi possível ligar o servidor central:\n{e}")
        self._update_net_label()

    def open_central_settings(self) -> None:
        from ipe.auth import session as S
        if not S.require("configure", self):
            return
        from ipe.ui.central_dialog import CentralDialog
        if CentralDialog(self.settings, self).exec():
            self.start_central_server()

    def open_automation(self) -> None:
        from ipe.auth import session as S
        if not S.require("configure", self):
            return
        from ipe.ui.automation_dialog import AutomationDialog
        AutomationDialog(self, self).exec()
        self.browser.refresh()

    def show_notification(self, title: str, text: str) -> None:
        self.statusBar().showMessage(f"{title}: {text}", 12000)
        tray = getattr(self, "tray", None)
        if tray is not None and tray.isVisible():
            tray.showMessage(title, text)

    # ------------------------------------------------------------ locais (bancos)
    def _update_title(self) -> None:
        loc = getattr(self, "location", None)
        extra = "" if loc is None or loc.is_default else f" — {loc.name}"
        self.setWindowTitle(f"{APP_NAME} {__version__}{extra} — {NOT_FOR_DIAGNOSIS}")

    def switch_location(self, loc_id: str) -> bool:
        """Troca o local ativo: a lista passa a ser a daquela pasta (banco, listas, laudos e medidas)."""
        from ipe.core import locations as LOC
        loc = LOC.find(self.settings, self.paths, str(loc_id))
        if loc is None or loc.id == self.location.id:
            return False
        if not loc.online():
            QMessageBox.information(self, "Local fora do ar",
                                    f"A pasta não está acessível agora:\n{loc.path}")
            self.locations.rebuild()
            return False
        abertos = self.all_viewer_tabs()
        if abertos:
            r = QMessageBox.question(
                self, "Trocar de local",
                f"Usar “{loc.name}”?\n\nOs {len(abertos)} exame(s) abertos serão fechados "
                "(os exames continuam guardados no local de origem).")
            if r != QMessageBox.Yes:
                self.locations.rebuild()
                return False
        for w in list(self.detached):
            w.close()
        for i in range(self.tabs.count() - 1, 0, -1):
            self.tabs.removeTab(i)
        self.cache.clear()
        antigo = self.db
        try:
            db = Database(self.paths.database if loc.is_default else loc.database)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Local", f"Não foi possível abrir o banco do local:\n{e}")
            return False
        self.location = loc
        LOC.set_current(self.settings, loc.id)
        self.settings.save()
        self._use_database(db, self.paths.storage if loc.is_default else loc.storage,
                           (self.paths.data if loc.is_default else loc.path) / "Lixeira")
        self.statusBar().showMessage(f"Local: {loc.name}", 6000)
        if antigo is not None and antigo is not db:
            antigo.close()
        return True

    def _use_database(self, db, storage, trash_root) -> None:
        """Passa a usar este banco: religa a lista, a rede, o PACS, a automação e a sincronização."""
        self.db = db
        self.repo = Repository(db)
        self.storage = Path(storage)
        self.storage.mkdir(parents=True, exist_ok=True)
        self.browser.set_source(self.repo, self.storage)
        self.net.set_source(self.db, self.repo, self.storage)
        self.pacs.repo = self.repo
        self.pacs.refresh_nodes()
        self.auto.set_source(self.repo, self.db, Path(trash_root))
        self.sync_hub.repo = self.repo
        self.locations.set_repo(self.repo)
        self._refresh_other_locations()
        self._update_title()
        self._update_status()

    def move_default_database(self) -> None:
        """Muda a pasta do banco deste computador (com a opção de levar os arquivos junto)."""
        from ipe.core import locations as LOC
        from ipe.core.config import AppPaths, default_data_dir
        from ipe.ui.locations_panel import choose_folder
        atual = Path(self.paths.data)
        nova = choose_folder(self, self.settings, "Pasta do banco deste computador")
        if nova is None or nova.resolve() == atual.resolve():
            return
        if atual.resolve() in nova.resolve().parents:
            QMessageBox.warning(self, "Pasta do banco",
                                "Escolha uma pasta fora da pasta atual do banco.")
            return
        for outra in LOC.all_locations(self.settings, self.paths):
            if not outra.is_default and outra.online() and outra.path.resolve() == nova.resolve():
                QMessageBox.warning(self, "Pasta do banco",
                                    f"Essa pasta já é o local “{outra.name}”.")
                return
        itens = [d for d in ("dicomviewer.sqlite", "Storage", "Lixeira") if (atual / d).exists()]
        mb = sum(f.stat().st_size for d in itens for f in [atual / d] + list((atual / d).rglob("*"))
                 if f.is_file()) / 1024 / 1024
        caixa = QMessageBox(self)
        caixa.setWindowTitle("Pasta do banco")
        caixa.setText(f"Usar esta pasta para o banco deste computador?\n\n{nova}")
        caixa.setInformativeText(
            f"Pasta de agora: {atual}\nBanco e arquivos: {mb:.0f} MB.\n\n"
            "“Mover” leva o banco e os arquivos para a pasta nova. "
            "“Só apontar” deixa tudo onde está e começa do que houver na pasta nova.")
        b_mover = caixa.addButton("Mover os arquivos", QMessageBox.AcceptRole)
        caixa.addButton("Só apontar", QMessageBox.AcceptRole)
        b_cancel = caixa.addButton("Cancelar", QMessageBox.RejectRole)
        caixa.exec()
        if caixa.clickedButton() is b_cancel:
            return
        mover = caixa.clickedButton() is b_mover
        if self.all_viewer_tabs():
            for i in range(self.tabs.count() - 1, 0, -1):
                self.tabs.removeTab(i)
        self.cache.clear()
        antigo = self.db
        antigo.close()
        nova.mkdir(parents=True, exist_ok=True)
        if mover:
            dlg = QProgressDialog("Movendo o banco…", "", 0, len(itens), self)
            dlg.setCancelButton(None)
            dlg.setWindowModality(Qt.WindowModal)
            try:
                import shutil
                for i, d in enumerate(itens):
                    dlg.setValue(i)
                    QApplication.processEvents()
                    destino = nova / d
                    if destino.exists():
                        QMessageBox.warning(self, "Pasta do banco",
                                            f"Já existe “{d}” na pasta nova; nada foi movido.")
                        self._use_database(Database(self.paths.database), self.paths.storage,
                                           self.paths.data / "Lixeira")
                        return
                    shutil.move(str(atual / d), str(destino))
                for extra in atual.glob("dicomviewer.sqlite-*"):     # WAL e índice do SQLite
                    shutil.move(str(extra), str(nova / extra.name))
            except Exception as e:  # noqa: BLE001
                log.exception("mover o banco")
                QMessageBox.warning(self, "Pasta do banco",
                                    f"Não foi possível mover tudo:\n{e}\n\n"
                                    "O programa vai usar a pasta nova com o que já foi para lá.")
            finally:
                dlg.close()
        self.settings.set("data_dir", "" if nova.resolve() == Path(default_data_dir()).resolve()
                          else str(nova))
        self.settings.save()
        self.paths = AppPaths(nova, self.paths.config, self.paths.logs).ensure()
        self.location = LOC.default_location(self.paths)
        self.locations.paths = self.paths
        self._use_database(Database(self.paths.database), self.paths.storage,
                           self.paths.data / "Lixeira")
        self.locations.rebuild()
        self.statusBar().showMessage(f"Banco deste computador: {nova}", 12000)
        QMessageBox.information(
            self, "Pasta do banco",
            f"O banco deste computador passou a ser:\n{nova}\n\n"
            + ("Os arquivos foram movidos." if mover else
               "Os arquivos antigos continuam em:\n" + str(atual)))

    def _refresh_other_locations(self) -> None:
        """Os outros locais que aparecem no menu "Copiar para o local"."""
        from ipe.core import locations as LOC
        self.browser.other_locations = [
            (loc.id, loc.name) for loc in LOC.all_locations(self.settings, self.paths)
            if loc.id != self.location.id and loc.online()]

    def copy_studies_to_location(self, study_uids: list[str], loc_id: str) -> None:
        """Copia exames para outro local. Os arquivos de origem não são tocados."""
        from ipe.core import locations as LOC
        loc = LOC.find(self.settings, self.paths, str(loc_id))
        if loc is None or not loc.online():
            QMessageBox.information(self, "Local", "O local de destino não está acessível agora.")
            return
        arquivos: list[Path] = []
        for uid in study_uids:
            arquivos += [Path(f) for f in self.repo.files_for_study(uid)]
        arquivos = [f for f in arquivos if f.exists()]
        if not arquivos:
            QMessageBox.information(self, "Copiar para o local", "Nenhum arquivo encontrado.")
            return
        mb = sum(f.stat().st_size for f in arquivos) / 1024 / 1024
        r = QMessageBox.question(
            self, "Copiar para o local",
            f"Copiar {len(study_uids)} exame(s) — {len(arquivos)} imagem(ns), {mb:.0f} MB — "
            f"para “{loc.name}”?\n\nOs arquivos de origem não são alterados.")
        if r != QMessageBox.Yes:
            return
        dlg = QProgressDialog(f"Copiando para {loc.name}…", "Cancelar", 0, len(arquivos), self)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(400)
        alvo = None
        try:
            LOC.prepare(loc.path, loc.name)
            alvo = Database(loc.database)
            imp = Importer(alvo, loc.storage, copy_to_storage=True)
            res = imp.import_paths(arquivos, progress=lambda i, n, _t: (dlg.setValue(i),
                                                                       QApplication.processEvents()))
        except Exception as e:  # noqa: BLE001
            log.exception("copiar para o local")
            QMessageBox.warning(self, "Copiar para o local", f"Não foi possível copiar:\n{e}")
            return
        finally:
            dlg.close()
            if alvo is not None:
                alvo.close()
        self.statusBar().showMessage(
            f"{res.added} imagem(ns) copiada(s) para “{loc.name}”; {res.duplicates} já existiam.", 10000)

    def add_location(self) -> None:
        """Acrescenta uma pasta como local: HD externo, pasta de rede ou outra pasta do PC."""
        from ipe.core import locations as LOC
        from ipe.ui.locations_panel import choose_folder
        pasta = choose_folder(self, self.settings)
        if pasta is None:
            return
        if pasta.resolve() == Path(self.paths.data).resolve():
            QMessageBox.information(self, "Local", "Essa já é a pasta do banco deste computador.")
            return
        usada = LOC.looks_used(pasta)
        nome = LOC.suggest_name(pasta)
        nome, ok = QInputDialog.getText(
            self, "Abrir local" if usada else "Local novo",
            ("A pasta já tem um local montado; ele será aberto como está.\n\nNome:" if usada else
             "A pasta será usada como local. Os arquivos que já estiverem lá são apenas indexados — "
             "nada é copiado, movido ou alterado.\n\nNome:"), text=nome)
        if not ok or not nome.strip():
            return
        loc = LOC.add(self.settings, pasta, nome.strip())
        self.settings.save()
        self.locations.rebuild()
        self._refresh_other_locations()
        if not self.switch_location(loc.id):
            return
        if not usada:
            self.rescan_location(loc.id, primeira=True)

    def rescan_location(self, loc_id: str, primeira: bool = False) -> None:
        """Procura exames novos na pasta do local e indexa sem copiar (os originais ficam onde estão)."""
        from ipe.core import locations as LOC
        loc = LOC.find(self.settings, self.paths, str(loc_id))
        if loc is None or not loc.online():
            return
        if not primeira:
            r = QMessageBox.question(
                self, "Procurar exames",
                f"Procurar exames novos em:\n{loc.path}\n\n"
                "Os arquivos continuam onde estão — o programa só acrescenta ao índice.")
            if r != QMessageBox.Yes:
                return
        if loc.id != self.location.id and not self.switch_location(loc.id):
            return
        self.start_import([loc.path], reference=True)

    def open_pacs_node(self, node_id) -> None:
        """Abre a janela do PACS já com aquele nó escolhido."""
        self.show_pacs()
        if node_id is not None:
            i = self.pacs.node.findData(node_id)
            if i >= 0:
                self.pacs.node.setCurrentIndex(i)

    def open_network_settings(self) -> None:
        from ipe.auth import session as S
        if not S.require("configure", self):
            return
        from ipe.ui.network_dialog import NetworkDialog
        before = (dict(self.settings.get("dicom", {}) or {}),
                  dict(self.settings.get("print_scp", {}) or {}))
        dlg = NetworkDialog(self.settings, self.repo, self.net, self, ao_mudar=self._nos_mudaram)
        dlg.exec()
        # nós e identidades são gravados na hora; configurações locais só com OK
        if (dict(self.settings.get("dicom", {}) or {}),
                dict(self.settings.get("print_scp", {}) or {})) != before:
            self.start_services()
        else:
            self.net.refresh_acl()
        self.pacs.refresh_nodes()

    def _nos_mudaram(self) -> None:
        """Um nó foi salvo ou excluído (na hora, sem esperar fechar a janela da rede)."""
        self.pacs.refresh_nodes()
        g = getattr(self, "gestao_window", None)
        if g is not None:
            g.recarregar_nos()

    def _register_url(self) -> None:
        from ipe.network.external import register_url_scheme
        try:
            QMessageBox.information(self, "Link ipe://", register_url_scheme())
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Link ipe://", f"Não foi possível registrar: {e}")

    def send_studies(self, study_uids: list, node_id: int, identity_id,
                     series_uids: list | None = None) -> None:
        """Põe os estudos na fila de envio; `series_uids`: só estas séries (um estudo só)."""
        from ipe.auth import session as S
        if not S.require("send", self):
            return
        node = self.repo.node(node_id)
        if node is None:
            return
        ident = self.repo.identity(identity_id)
        for uid in study_uids:
            info = self.repo.study_info(uid) or {}
            label = f"{info.get('patient_name', '')} — {info.get('description', '')}"
            if series_uids:
                label += f" ({len(series_uids)} série(s))"
            S.audit(self.repo, "enviar", f"{node['name']}: {label}", study_uid=uid)
            try:
                self.net.send(node, ident, [uid], label, series_uids or None)
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "Enviar", str(e))
                return
        if series_uids:
            msg = f"{len(series_uids)} série(s) na fila de envio para {node['name']}. Acompanhe na aba PACS."
        else:
            msg = f"{len(study_uids)} estudo(s) na fila de envio para {node['name']}. Acompanhe na aba PACS."
        self.statusBar().showMessage(msg, 8000)

    def _on_received(self, result, origin: str) -> None:
        self._refresh_timer.start()
        self._note_auto_film(getattr(result, "studies", set()) or set())
        from ipe.central.client_repo import upload_if_client
        studies = set(getattr(result, "studies", set()) or set())
        for uid in studies:
            upload_if_client(self.repo, uid)
        if origin == "received" and result.added:
            self.statusBar().showMessage(f"Recebidas {result.added} imagem(ns) pela rede.", 8000)
        if result.added:
            self._stream_progress(studies)

    def _on_job_changed(self, job) -> None:
        """Mudou alguma coisa no download: barra de estado e a tira das séries que faltam."""
        self._update_net_label()
        if getattr(job, "kind", "") != "retrieve":
            return
        abertos = set(getattr(job, "study_uids", []) or [])
        for tab in self.all_viewer_tabs():
            if abertos & set(tab.study_order):
                tab._fill_strip()

    # ------------------------------------------------------------ filme automático (US)
    def _note_auto_film(self, studies) -> None:
        """Marca os exames que acabaram de receber imagens; o filme é montado quando pararem de chegar."""
        from ipe.printing.auto_film import alguma_ligada
        if not studies or not alguma_ligada(self.settings):
            return
        # o que chegou pela porta da impressão já vira filme lá (_on_print_images)
        studies = set(studies) - set(getattr(self.net, "print_port_studies", set()) or set())
        import time
        for uid in studies:
            self._auto_film_wait[uid] = time.monotonic()
        if not self._auto_film_timer.isActive():
            self._auto_film_timer.start()

    def _run_auto_film(self) -> None:
        """Monta o filme dos exames que estão quietos há alguns segundos (terminaram de chegar)."""
        import time
        from ipe.printing.auto_film import montar_para_estudo
        agora = time.monotonic()
        from ipe import modules as MOD
        if not MOD.ligado(self.settings, "impressao"):
            self._auto_film_wait.clear()
            self._auto_film_timer.stop()
            return
        prontos = [uid for uid, quando in self._auto_film_wait.items() if agora - quando >= 15]
        for uid in prontos:
            self._auto_film_wait.pop(uid, None)
            remetente = (getattr(getattr(self.net, "sink", None), "remetentes", {}) or {}).get(uid)
            try:
                film_id, cfg = montar_para_estudo(self.repo, self.settings, uid, remetente)
            except Exception:  # noqa: BLE001
                log.exception("Falha ao montar o filme automático")
                continue
            if film_id is None:
                continue
            info = self.repo.study_info(uid) or {}
            self.show_notification("Filme montado sozinho",
                                   f"{info.get('patient_name', '')} — {info.get('description', '')}".strip(" —"))
            if self._prints is not None:
                self._prints.refresh()
            if cfg.destination:
                self._send_film(film_id, cfg.destination, cfg.template)
        if not self._auto_film_wait:
            self._auto_film_timer.stop()

    def _send_film(self, film_id: int, destino: str, modelo: str = "") -> None:
        from ipe.printing.dispatch import find_destination
        dest = find_destination(self.settings, destino)
        if dest is None:
            self.statusBar().showMessage(f"Destino “{destino}” não existe mais; o filme ficou na lista.",
                                         8000)
            return
        aba = self.show_prints()
        linha = next((r for r in aba.rows if r["kind"] == "film" and r["id"] == film_id), None)
        if linha is not None:
            aba.send_rows([linha], dest, avisar=False, template=modelo, how="regra")

    def _stream_progress(self, studies: set) -> None:
        """Exame baixando com “abrir enquanto baixa”: abre no primeiro lote e vai acrescentando o resto."""
        for job in self.net.active_jobs():
            if job.kind != "retrieve" or not job.stream:
                continue
            uid = job.study_uids[0] if job.study_uids else ""
            if uid not in studies:
                continue
            if not job.opened and self.repo.study_info(uid):
                job.opened = True
                self.statusBar().showMessage(f"Abrindo enquanto baixa: {job.label}", 8000)
                self.open_study(uid)
        for uid in studies:
            for tab in self.all_viewer_tabs():
                if uid in tab.study_order:
                    tab.rescan(uid)

    def _on_job_finished(self, job) -> None:
        self.browser.refresh()
        if job.status == "error":
            self.statusBar().showMessage(f"Falha em “{job.label}”: {job.message}", 15000)
        elif job.status == "done":
            self.statusBar().showMessage(f"Concluído: {job.label} — {job.message}", 8000)
            if job.kind == "retrieve":
                from ipe.central.client_repo import upload_if_client
                for uid in job.study_uids:
                    upload_if_client(self.repo, uid)
            if job.kind == "retrieve":
                self._learn_network(job)
                for uid in job.study_uids:
                    for tab in self.all_viewer_tabs():
                        if uid in tab.study_order:
                            tab.rescan(uid)
            if job.kind == "retrieve" and job.open_after and not job.opened \
                    and self.repo.study_info(job.study_uids[0]):
                # O exame que o RIS mandou baixar abre do mesmo jeito que o que já estava no
                # banco: no modo "só visualizador", sem passar pelo banco de dados.
                self.abrir_exame_do_pedido(job.study_uids[0])
        self._update_net_label()

    def _learn_network(self, job) -> None:
        """Aprende a velocidade do nó com o download que acabou (MB/s e MB por imagem)."""
        try:
            from ipe.network.probe import learn
            secs = max(0.5, (job.finished or time.time()) - (job.started or 0))
            rows = [r for r in self.repo.search_studies(limit=5000) if r.study_uid in set(job.study_uids)]
            mb = sum(r.size_mb for r in rows)
            imgs = sum(r.num_images for r in rows)
            if mb > 0 and imgs:
                learn(self.settings, job.node.get("id"), mb, secs, imgs)
        except Exception as e:  # noqa: BLE001
            log.debug("medida de rede: %s", e)

    def _update_net_label(self) -> None:
        active = len(self.net.active_jobs())
        text = self.net.server.status_text()
        if self.central is not None:
            text += f"  ·  servidor central :{self.central.port}"
        if getattr(self.repo, "remote", False):
            text += f"  ·  cliente de {self.repo.client.url}"
        if self.net.print_servers:
            text += "  ·  " + self.net.print_status_text()
        if self.http.server.isListening():
            text += f"  ·  API :{self.http.port}"
        if active:
            text += f"  ·  {active} transferência(s)"
        self.net_label.setText(text)
        hb = getattr(self, "home_bar", None)
        if hb is not None:
            hb.buttons["pacs"].defaultAction().setText(f"PACS ({active})" if active else "PACS")

    def _setup_tray(self) -> None:
        from PySide6.QtWidgets import QSystemTrayIcon
        from ipe.ui.icons import icon
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(icon("mpr"), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu(self)
        menu.addAction("Abrir", self.restore_from_tray)
        menu.addAction("Automação…", self.open_automation)
        menu.addSeparator()
        menu.addAction("Sair", self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.restore_from_tray()
                                    if reason == QSystemTrayIcon.Trigger else None)
        self.tray.show()

    def restore_from_tray(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_app(self) -> None:
        from ipe.auth import session as S
        S.audit(self.repo, "logout", "")
        self._really_quit = True
        self.close()

    def _confirmar_saida(self) -> bool:
        """0.99.6: *"Ative uma mensagem para confirmar se eu quero mesmo fechar o programa. Às vezes
        estou fechando por engano."* Preferências ▸ Geral ▸ "Perguntar antes de fechar o programa"."""
        if not self.settings.get("ui.confirmar_sair", True):
            return True
        caixa = QMessageBox(QMessageBox.Question, APP_NAME, "Fechar o Ipê?", parent=self)
        servicos = []
        if any(getattr(s, "running", False) for s in getattr(self.net, "print_servers", []) or []):
            servicos.append("o servidor de impressão")
        if getattr(self.net, "active_jobs", None) and self.net.active_jobs():
            servicos.append("os downloads/envios em andamento")
        caixa.setInformativeText("Enquanto o programa estiver fechado, o nó DICOM não recebe exames"
                                 + (" e param " + " e ".join(servicos) if servicos else "") + ".")
        sim = caixa.addButton("Fechar", QMessageBox.AcceptRole)
        nao = caixa.addButton("Cancelar", QMessageBox.RejectRole)
        caixa.setDefaultButton(nao)                    # Enter por engano não fecha
        caixa.setEscapeButton(nao)
        caixa.exec()
        return caixa.clickedButton() is sim

    def closeEvent(self, e) -> None:  # noqa: N802
        # Com exame aberto, o X fecha o exame — em **todas** as telas — e devolve o banco de
        # dados. Só com tudo fechado é que ele encerra o programa.
        if not self._really_quit and self.fechar_exames_e_voltar_ao_banco():
            e.ignore()
            return
        if (not self._really_quit and self.settings.get("viewer.close_to_tray", False)
                and self.tray is not None and self.tray.isVisible()):
            self.hide()
            e.ignore()
            self.tray.showMessage(APP_NAME, "O programa continua na bandeja (nó DICOM e buscas "
                                  "agendadas ativos). Botão direito no ícone → Sair para fechar.")
            return
        if not self._confirmar_saida():
            e.ignore()
            self._really_quit = False
            return
        if self._film is not None and not self._film._confirm_discard():
            e.ignore()
            self._really_quit = False
            return
        # Sair com exame aberto também guarda o layout: o X do programa é tão "fechar o exame"
        # quanto o X da aba, e perder o arranjo por causa de qual botão ele apertou seria arbitrário.
        for t in self.all_viewer_tabs():
            try:
                t.guardar_layout()
            except Exception:  # noqa: BLE001
                log.debug("não consegui guardar o layout ao sair", exc_info=True)
        if self.tray is not None:
            self.tray.hide()
        self.pacs_window.close()
        self.auto.stop()
        self.http.stop()
        if self.central is not None:
            self.central.stop()
            self.central = None
        client = getattr(self.repo, "client", None)
        if client is not None:
            client.logout()
        self.net.shutdown()
        super().closeEvent(e)

    # ------------------------------------------------------------ importação
    def import_dialog(self) -> None:
        self.import_folder()

    def import_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Importar pasta (inclui subpastas, CD/DVD)")
        if d:
            self.start_import([Path(d)])

    def import_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Importar arquivos DICOM")
        if files:
            self.start_import([Path(f) for f in files])

    def import_zip(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Importar ZIP", filter="ZIP (*.zip)")
        if files:
            self.start_import([Path(f) for f in files])

    def make_samples(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Pasta onde gerar os exames de teste")
        if not d:
            return
        from ipe.core.sample_data import make_sample_data
        out = Path(d) / "Ipe_fantomas"
        make_sample_data(out)
        self.start_import([out])

    def drop_windows(self) -> list:
        return [self, *self.detached]

    def import_dropped(self, paths: list[Path]) -> None:
        """Arquivos soltos na janela (ou `ipe open <pasta>`): importa e abre os exames."""
        paths = [p for p in paths if p.exists()]
        if not paths:
            return
        if self._import_thread is not None:
            self._pending_imports.extend(paths)
            self.statusBar().showMessage(
                f"Importação em andamento; mais {len(paths)} item(ns) na fila.", 8000)
            return
        self.start_import(paths, open_after=True)

    def fix_study_tags(self, study_uid: str) -> None:
        """Corrigir as tags de um exame direto da lista (grava uma cópia corrigida)."""
        from pathlib import Path as _Path
        from ipe.auth import session as S
        if not S.require("import", self):
            return
        series = self.repo.series_for_study(study_uid)
        arquivos = [_Path(i["path"]) for se in series for i in self.repo.instances_for_series(se.series_uid)]
        if not arquivos:
            QMessageBox.information(self, "Corrigir tags", "Não encontrei os arquivos deste exame.")
            return

        def escopo(qual: str) -> list:
            if qual == "image":
                return arquivos[:1]
            if qual == "series" and series:
                return [_Path(i["path"]) for i in self.repo.instances_for_series(series[0].series_uid)]
            return arquivos

        from ipe.ui.dialogs import TagDialog
        dlg = TagDialog(str(arquivos[0]), self, files_for=escopo, on_fixed=self.import_fixed_tags)
        dlg.escopo.setCurrentIndex(2)          # da lista, o normal é corrigir o exame inteiro
        dlg.tabs.setCurrentIndex(1)
        dlg.exec()

    def import_fixed_tags(self, paths) -> None:
        """As cópias com as tags corrigidas entram no banco (o original continua onde estava)."""
        from ipe.auth import session as S
        S.audit(self.repo, "importar", f"tags corrigidas: {len(paths)} imagem(ns)")
        self.statusBar().showMessage(f"Gravando {len(paths)} imagem(ns) corrigida(s)…", 8000)
        self.start_import([Path(p) for p in paths], open_after=False)

    def start_import(self, paths: list[Path], open_after: bool = False,
                     reference: bool = False) -> None:
        from ipe.auth import session as S
        if not S.require("import", self):
            return
        S.audit(self.repo, "importar", ", ".join(str(p) for p in paths)[:500])
        if self._import_thread is not None:
            QMessageBox.information(self, "Importação", "Já há uma importação em andamento.")
            return
        self._open_after_import = open_after
        copiar = False if reference else bool(self.settings.get("import.copy_to_storage", True))
        importer = Importer(self.db, self.storage, copy_to_storage=copiar)
        dlg = QProgressDialog("Procurando arquivos…", "Cancelar", 0, 0, self)
        dlg.setWindowTitle("Importando")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        self._import_dialog = dlg
        th = ImportThread(importer, self.repo, paths, self)
        th.progress.connect(self._on_import_progress)
        th.status.connect(dlg.setLabelText)
        th.done.connect(self._on_import_done)
        dlg.canceled.connect(th.cancel)
        self._import_thread = th        # guarda a referência até terminar
        log.info("Importando: %s", ", ".join(str(p) for p in paths))
        th.start()
        dlg.show()

    def _on_import_progress(self, done: int, total: int, current: str) -> None:
        dlg = self._import_dialog
        if dlg is None:
            return
        dlg.setMaximum(max(total, 1))
        dlg.setValue(done)
        dlg.setLabelText(f"Importando {done} de {total} arquivos\n{Path(current).name}")

    def _on_import_done(self, result) -> None:
        th = self._import_thread
        if th is not None:
            th.wait(2000)
            th.deleteLater()
        self._import_thread = None
        if self._import_dialog is not None:
            self._import_dialog.close()
            self._import_dialog = None
        self.browser.refresh()
        self.statusBar().showMessage(result.summary(), 15000)
        from ipe.central.client_repo import upload_if_client
        for uid in getattr(result, "studies", set()) or set():
            upload_if_client(self.repo, uid)
        try:                       # 0.99.1: implante e segmentação automáticos também na importação
            self.auto.cad_ia_importados(result)
        except Exception:  # noqa: BLE001
            log.exception("CAD/IA nos exames importados")
        open_after, self._open_after_import = self._open_after_import, False
        opened = self._open_imported(result) if open_after else False
        if result.errors:
            QMessageBox.warning(self, "Importação concluída com erros",
                                result.summary() + "\n\n" + "\n".join(result.error_files[:15]))
        elif result.added == 0 and not opened:
            QMessageBox.information(
                self, "Importação",
                result.summary() + "\n\nNenhuma imagem nova. Se a pasta tem exames, confira se "
                "são arquivos DICOM (não JPG/PDF) ou se já estavam no banco.")
        if self._pending_imports:
            pending, self._pending_imports = self._pending_imports, []
            self.import_dropped(pending)

    MAX_OPEN_AFTER_IMPORT = 4

    # reserva: se o filtro da aplicação não pegar o arrasto, a própria janela trata
    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if local_paths(e.mimeData()):
            e.setDropAction(Qt.CopyAction)
            e.accept()

    def dragMoveEvent(self, e) -> None:  # noqa: N802
        if local_paths(e.mimeData()):
            e.setDropAction(Qt.CopyAction)
            e.accept()

    def dropEvent(self, e) -> None:  # noqa: N802
        paths = local_paths(e.mimeData())
        if paths:
            log.info("Arquivos soltos na janela: %s", [str(p) for p in paths][:10])
            e.setDropAction(Qt.CopyAction)
            e.accept()
            self.import_dropped(paths)

    def _open_imported(self, result) -> bool:
        """Abre os exames que vieram no arrasto (novos ou que já estavam no banco)."""
        uids = [u for u in result.studies if self.repo.study_info(u)]
        if not uids:
            return False
        if len(uids) > self.MAX_OPEN_AFTER_IMPORT:
            self.tabs.setCurrentWidget(self.browser)
            self.statusBar().showMessage(
                f"{len(uids)} exames importados; estão no banco de dados. " + result.summary(), 15000)
            return True
        infos = sorted(uids, key=lambda u: self.repo.study_info(u).get("study_date", ""))
        for uid in infos:                      # o mais recente fica em primeiro plano
            self.open_study(uid)
        return True
