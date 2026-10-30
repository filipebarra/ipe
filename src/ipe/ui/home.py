"""Tela inicial: barra de botões do banco de dados e janela flutuante do PACS."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QInputDialog, QMenu, QMessageBox, QToolBar, QToolButton, QVBoxLayout, QWidget,
)

from ipe.auth import session as S
from ipe.ui.icons import icon

HOME_STYLE = ("QToolBar{background:#2b2d31;border:none;border-bottom:1px solid #3c3f45;spacing:2px;padding:3px}"
              "QToolButton{color:#e6e6e6;padding:4px 8px;border-radius:4px;min-width:58px}"
              "QToolButton:hover{background:#3b4048}QToolButton:pressed{background:#35506e}"
              "QToolButton:checked{background:#35506e}QToolButton:disabled{color:#777}"
              "QToolButton::menu-indicator{subcontrol-position:bottom right;width:8px}")


class PacsWindow(QWidget):
    """Consulta ao PACS numa janela própria (fica por cima da principal, pode ir para outro monitor)."""

    def __init__(self, panel, settings, parent=None):
        super().__init__(parent, Qt.Window)
        self.panel, self.settings = panel, settings
        self.setWindowTitle("PACS — busca, download e fila de transferências")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(panel)
        self.resize(1150, 720)
        geo = settings.get("pacs.geometry", "") if settings is not None else ""
        if geo:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geo.encode("ascii")))
            except Exception:  # noqa: BLE001
                pass
        QShortcut(QKeySequence("Esc"), self, activated=self.close)

    def show_front(self) -> None:
        self.panel.refresh_nodes()
        self.show()
        if self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, e) -> None:  # noqa: N802
        if self.settings is not None:
            self.settings.set("pacs.geometry", bytes(self.saveGeometry().toBase64()).decode("ascii"))
            self.settings.save()
        super().closeEvent(e)


class HomeBar(QToolBar):
    """Botões grandes da tela inicial. Cada botão guarda a permissão que exige (apply_permissions)."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setStyleSheet(HOME_STYLE)
        self.setIconSize(QSize(30, 30))
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setMovable(False)
        self.perm: dict[str, str] = {}
        self.buttons: dict[str, QToolButton] = {}
        b = self.browser = win.browser

        self._add("import", "Importar", "import", self._import_default, "import",
                  "Importar pasta, arquivos, ZIP ou pacote de lista (também dá para arrastar para a janela)",
                  menu=self._import_menu)
        self._add("pacs", "PACS", "pacs", win.show_pacs, "query", "Buscar e baixar exames do PACS (Ctrl+Shift+F)")
        self._add("gestao", "Gestão", "gestao", win.show_gestao, "query",
                  "Gestão DICOM: conferir se os exames das modalidades estão no PACS (por exame, "
                  "série e imagem) e mandar o que falta")
        self.addSeparator()
        self._add("open", "Abrir", "open", self._open, "view", "Abrir o exame selecionado (duplo clique também)",
                  menu=self._open_menu)
        self._add("send", "Enviar", "send", self._send, "send", "Enviar os exames selecionados para um nó DICOM",
                  menu=self._send_menu, instant=True)
        self._add("export", "Exportar", "export", self._export, "export",
                  "Exportar: CD/pendrive com visualizador, pasta DICOM ou imagens JPG/PNG")
        self._add("print", "Imprimir", "print", win.show_film, "print",
                  "Filme e impressão (impressora comum, PDF, impressora DICOM)", menu=self._print_menu)
        self._add("prints", "Impressões", "prints", win.show_prints, "print",
                  "Lista de impressões: filmes recebidos das modalidades e montados aqui; "
                  "seta: configurações de impressão", menu=self._prints_menu)
        self._add("report", "Laudo", "report", self._report, "view",
                  "Laudo do exame selecionado: abre o rascunho ou o laudo assinado (ou começa um novo)")
        self.addSeparator()
        self._add("list", "Listas", "list", self._toggle_lists, "case_lists",
                  "Mostrar/esconder o painel de listas de casos; seta: adicionar à lista, nova lista…",
                  menu=self._list_menu, checkable=True)
        self._add("meeting", "Reunião", "meeting", self._meeting, "case_lists",
                  "Modo reunião: apresentar uma lista de casos com os dados do paciente ocultos")
        self._add("anon", "Ocultar", "anon", self._toggle_privacy, "view",
                  "Ocultar os dados do paciente em todo o programa (aula, tela compartilhada)", checkable=True)
        self._add("delete", "Apagar", "trash", self._delete, "delete", "Apagar os exames selecionados do banco")
        self.addSeparator()
        self._add("monitor", "Monitor", "monitor", self._monitor_default, "view",
                  "Configurar os monitores (papel e layout de cada um); seta: abrir o exame em outro "
                  "monitor, trazer de volta, calibração", menu=self._monitor_menu)
        self._add("refresh", "Atualizar", "refresh", lambda: (b.refresh_lists(), b.refresh()), "view",
                  "Recarregar a lista de exames (F5)")
        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy().Expanding,
                             spacer.sizePolicy().verticalPolicy().Preferred)
        self.addWidget(spacer)
        self._add("settings", "Configurações", "gear", win.open_preferences, "",
                  "Preferências, nós DICOM, automação, servidor central", menu=self._settings_menu)
        self._add("users", "Usuários", "users", lambda: win.open_users(), "users",
                  "Usuários, perfis e permissões, registro de acesso", menu=self._users_menu)
        self._add("help", "Ajuda", "help", win.show_help, "", "Guia do usuário em PDF (F1)")
        QShortcut(QKeySequence("F5"), b, activated=lambda: (b.refresh_lists(), b.refresh()))
        lists_visible = bool(win.settings.get("browser.show_lists", True))
        self.buttons["list"].setChecked(lists_visible)

    def _report(self) -> None:
        rows = self.browser.selected_rows()
        if len(rows) != 1:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Laudo", "Selecione um exame na lista.")
            return
        self.win.open_report(rows[0].study_uid)

    # ------------------------------------------------------------------ montagem
    def _add(self, key, text, icon_name, fn, perm, tip, menu=None, instant=False, checkable=False) -> QToolButton:
        a = QAction(icon(icon_name), text, self)
        a.setToolTip(tip)
        a.setCheckable(checkable)
        a.triggered.connect(lambda _=False: fn())
        btn = QToolButton()
        btn.setDefaultAction(a)
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setIconSize(QSize(30, 30))
        if menu is not None:
            m = QMenu(btn)
            m.aboutToShow.connect(lambda mm=m, f=menu: (mm.clear(), f(mm)))
            btn.setMenu(m)
            btn.setPopupMode(QToolButton.InstantPopup if instant else QToolButton.MenuButtonPopup)
        # quem manda na visibilidade de um widget na barra é a QAction que o addWidget devolve
        self.__dict__.setdefault("acoes", {})[key] = self.addWidget(btn)
        self.perm[key] = perm
        self.buttons[key] = btn
        return btn

    def set_visible(self, key: str, on: bool) -> None:
        acao = getattr(self, "acoes", {}).get(key)
        if acao is not None:
            acao.setVisible(bool(on))

    def apply_permissions(self) -> None:
        for key, perm in self.perm.items():
            self.buttons[key].setEnabled(not perm or S.can(perm))
        self.buttons["list"].setVisible(S.can("case_lists"))
        self.buttons["meeting"].setVisible(S.can("case_lists"))

    # ------------------------------------------------------------------ ações
    def _rows(self, what: str):
        rows = self.browser.selected_rows()
        if not rows:
            QMessageBox.information(self.win, what, "Selecione um ou mais exames na lista.")
        return rows

    def _import_default(self) -> None:
        self.win.import_folder()

    def _import_menu(self, m: QMenu) -> None:
        w = self.win
        for text, fn in (("Pasta…", w.import_folder), ("Arquivos…", w.import_files), ("ZIP…", w.import_zip),
                         (None, None), ("Pacote de lista de casos…", lambda: w.import_case_list(None)),
                         (None, None), ("Gerar exames de teste (fantomas)…", w.make_samples)):
            if text is None:
                m.addSeparator()
            else:
                m.addAction(text, fn)

    def _open(self) -> None:
        if self._rows("Abrir"):
            self.browser._open_selected()

    def _open_menu(self, m: QMenu) -> None:
        rows = self.browser.selected_rows()
        a = m.addAction("Abrir", self._open)
        a.setEnabled(bool(rows))
        a = m.addAction("Abrir escolhendo séries…", lambda: self.browser.choose_series.emit(rows[0].study_uid))
        a.setEnabled(len(rows) == 1)
        a = m.addAction("Abrir junto (comparar numa aba só)", self._open_together)
        a.setEnabled(len(rows) > 1)

    def _open_together(self) -> None:
        rows = self.browser.selected_rows()
        if not rows:
            return
        rows = sorted(rows, key=lambda r: r.study_date or "", reverse=True)
        self.win.open_study(rows[0].study_uid)
        tab = self.win.tabs.currentWidget()
        for r in rows[1:]:
            if hasattr(tab, "add_study"):
                tab.add_study(r.study_uid)

    def _send(self) -> None:
        pass                    # o botão abre o menu direto (InstantPopup)

    def _send_menu(self, m: QMenu) -> None:
        rows = self.browser.selected_rows()
        if not rows:
            a = m.addAction("(selecione um ou mais exames na lista)")
            a.setEnabled(False)
            return
        head = m.addAction(f"Enviar {len(rows)} exame(s) para:")
        head.setEnabled(False)
        m.addSeparator()
        self.browser.fill_send_menu(m, rows)

    def _export(self) -> None:
        if self._rows("Exportar"):
            self.browser.export_selected()

    def _prints_menu(self, m: QMenu) -> None:
        w = self.win
        m.addAction("Lista de impressões", w.show_prints)
        m.addAction("Configurações de impressão (servidores, destinos, regras, modelos)…",
                    w.open_print_settings)
        m.addSeparator()
        ligados = [s for s in w.net.print_servers if s.running]
        if ligados:
            for s in ligados:
                a = m.addAction(f"Recebendo: {s.status_text()}")
                a.setEnabled(False)
        else:
            a = m.addAction("Nenhum servidor de impressão ligado")
            a.setEnabled(False)

    def _print_menu(self, m: QMenu) -> None:
        w, rows = self.win, self.browser.selected_rows()
        m.addAction("Abrir o filme / compositor", w.show_film)
        m.addAction("Filmes salvos…", lambda: (w.dock_film(), w.film_composer().open_saved()))
        from ipe import modules as MOD
        if MOD.ligado(w.settings, "impressao"):
            m.addAction("Impressões (recebidas e montadas aqui)…", w.show_prints)
        a = m.addAction("Imagens-chave do exame selecionado no filme",
                        lambda: w.film_request({"kind": "keys", "study_uid": rows[0].study_uid}))
        a.setEnabled(len(rows) == 1 and bool(getattr(rows[0], "key_images", 0)))

    def _toggle_lists(self) -> None:
        on = self.buttons["list"].isChecked()
        self.browser.set_lists_visible(on)
        self.win.settings.set("browser.show_lists", on)
        self.win.settings.save()

    def _list_menu(self, m: QMenu) -> None:
        b, rows = self.browser, self.browser.selected_rows()
        sub = m.addMenu(f"Adicionar {len(rows)} exame(s) à lista" if rows else "Adicionar à lista")
        sub.setEnabled(bool(rows))
        if rows:
            sub.addAction("Nova lista…", lambda: b._add_to_new_list(rows))
            sub.addSeparator()
            for lid, name, kind, _n in self.win.repo.case_lists():
                sub.addAction(name, lambda l=lid, k=kind: b._add_to_list(l, k, rows))
        m.addSeparator()
        m.addAction("Nova lista…", lambda: (self._show_lists(), b._new_list()))
        m.addAction("Nova pasta…", lambda: (self._show_lists(), b._new_list(folder=True)))
        m.addAction("Importar pacote de lista…", lambda: self.win.import_case_list(None))
        lid = b.tree.current_id()
        node = b.tree.node(lid) if lid is not None else None
        a = m.addAction("Exportar a lista selecionada…", lambda: b._export(lid))
        a.setEnabled(node is not None and node["kind"] not in ("folder",))

    def _show_lists(self) -> None:
        if not self.buttons["list"].isChecked():
            self.buttons["list"].defaultAction().setChecked(True)
            self._toggle_lists()

    def _meeting(self) -> None:
        b = self.browser
        lid = b.tree.current_id()
        node = b.tree.node(lid) if lid is not None else None
        if node is not None and node["kind"] != "folder":
            b._start_meeting(lid)
            return
        lists = [(l_id, name) for l_id, name, kind, n in self.win.repo.case_lists() if n]
        if not lists:
            QMessageBox.information(self.win, "Reunião", "Crie uma lista de casos primeiro (botão Listas).")
            return
        meetings = [x for x in lists if any(l[0] == x[0] and l[2] == "meeting" for l in self.win.repo.case_lists())]
        names = [n for _i, n in (meetings or lists)]
        name, ok = QInputDialog.getItem(self.win, "Reunião", "Apresentar a lista:", names, 0, False)
        if ok:
            b._start_meeting(dict((n, i) for i, n in (meetings or lists))[name])

    def _toggle_privacy(self) -> None:
        on = self.buttons["anon"].isChecked()
        if self.win.meeting is not None:
            self.buttons["anon"].defaultAction().setChecked(True)
            return
        self.win.set_privacy(on)

    def _delete(self) -> None:
        rows = self._rows("Apagar")
        if rows:
            self.browser._delete(rows)

    def _monitor_default(self) -> None:
        """O botão abre as **configurações** de monitor; abrir o exame noutra tela está na seta.

        Abrir exame já tem botão (e duplo clique); configurar monitor não tinha nenhum — ficava
        escondido atrás da seta de um botão que fazia outra coisa.
        """
        if not S.can("configure"):
            # sem permissão para configurar, o botão volta a fazer o que fazia
            rows = self._rows("Monitor")
            if rows:
                self.win.open_on_monitor(rows[0].study_uid)
            return
        self.win.open_preferences("Monitores")

    def _monitor_menu(self, m: QMenu) -> None:
        from PySide6.QtGui import QGuiApplication
        from ipe.ui.monitors import monitor_config, ROLES
        w, rows = self.win, self.browser.selected_rows()
        for i, sc in enumerate(w.telas_na_ordem(), 1):
            g = sc.geometry()
            role = ROLES.get(monitor_config(w.settings, sc).get("role", ""), "")
            a = m.addAction(f"Abrir o exame selecionado no monitor {i} — {sc.name()} ({g.width()}×{g.height()})"
                            + (f" · {role}" if role and role != "Automático" else ""),
                            lambda s=sc: w.open_on_monitor(rows[0].study_uid, s))
            a.setEnabled(bool(rows))
        m.addSeparator()
        a = m.addAction(f"Trazer de volta os exames abertos em outros monitores ({len(w.detached)})", w.reattach_all)
        a.setEnabled(bool(w.detached))
        a = m.addAction("Configurar monitores (papel e layout de cada um)…", lambda: w.open_preferences("Monitores"))
        a.setEnabled(S.can("configure"))
        a = m.addAction("Calibração GSDF (escala de cinza do monitor)…", w.open_gsdf)
        a.setEnabled(S.can("configure"))

    def _settings_menu(self, m: QMenu) -> None:
        w = self.win
        can = S.can("configure")
        for text, fn, ok in (("Preferências…", w.open_preferences, True),
                             ("Protocolos de mamografia…", lambda: w.open_preferences("Mamografia"), True),
                             ("Nós DICOM (PACS, estações)…", w.open_network_settings, can),
                             ("Calibração GSDF do monitor…", w.open_gsdf, can),
                             ("Automação (buscas agendadas, anteriores, roteamento, limpeza)…", w.open_automation, can),
                             ("Servidor central (intranet)…", w.open_central_settings, can),
                             (None, None, True),
                             ("Registrar link ipe:// neste computador", w._register_url, can),
                             ("Abrir a pasta de dados", w._open_data_folder, True),
                             ("Mudar a pasta do banco deste computador…", w.move_default_database, can)):
            if text is None:
                m.addSeparator()
                continue
            a = m.addAction(text, fn)
            a.setEnabled(ok)

    def _users_menu(self, m: QMenu) -> None:
        w = self.win
        cur = S.get()
        a = m.addAction(cur.label)
        a.setEnabled(False)
        m.addSeparator()
        a = m.addAction("Alterar minha senha…", w.change_password)
        a.setEnabled(w.auth is not None and cur.user_id is not None)
        a = m.addAction("Trocar de usuário…", w.switch_user)
        a.setEnabled(w.auth is not None)
        m.addSeparator()
        for text, tab in (("Usuários e permissões…", 0), ("Registro de acesso…", 2)):
            a = m.addAction(text, lambda t=tab: w.open_users(tab=t))
            a.setEnabled(S.can("users"))
