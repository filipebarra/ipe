"""A barra de ferramentas do visualizador (mixin do ViewerTab, separado do `viewer_tab.py` na 0.100.39).

Aqui ficam:
- a montagem da barra (`_build_toolbar`), os botões, os menus e os atalhos de teclado;
- os botões por modalidade e os opcionais que a pessoa tira da barra;
- as aplicações do exame e o botão "IA" (a lista agrupada das ferramentas de IA);
- os botões do mouse (ferramenta de cada botão e os selos nos ícones);
- o nível de anotação, a cópia do quadro e os perfis de ocultação.

Os métodos continuam sendo do ViewerTab (mesmos nomes): o resto do programa e os testes não mudam.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QComboBox, QLabel, QMenu, QMessageBox, QTabWidget, QToolBar, QToolButton, QWidget,
)

from ipe.imaging.volume import SLAB_MODES
from ipe.ui.viewer.actions import shortcut_for
from ipe.ui.icons import icon
from ipe.ui.viewer.viewport import TOOLS, Viewport
from ipe.ui.viewer import nm_view as NMV

log = logging.getLogger("ipe.ui.viewer.viewer_tab")      # o mesmo registro de antes da separação


LAYOUTS = [(1, 1), (1, 2), (2, 1), (2, 2), (1, 3), (2, 3), (3, 3), (1, 4), (2, 4), (3, 4), (4, 4)]
SLAB_CHOICES = [0, 2, 5, 10, 20, 40]
MEASURE_TOOLS = ("pick", "measure", "polyline", "angle", "cobb", "height", "ellipse", "rect", "polygon",
                 "probe", "ruler3d", "tic", "grow", "caixa_ia", "pincel", "ctr", "spine", "calibration", "text", "arrow",
                 "pencil")
TOOL_ICONS = {"measure": "measure", "ruler3d": "measure", "oblique": "mpr", "curve": "mpr", "rotplane": "mpr",
              "quadzoom": "quad", "loupe": "loupe",
              "grow": "segment", "caixa_ia": "segment", "pick": "pick", "pincel": "pencil"}
TOOL_SHORT = {"film": "Filme", "wl": "Janela", "zoom": "Zoom", "pan": "Pan", "scroll": "Rolar", "measure": "Régua",
              "polyline": "Polilinha", "angle": "Ângulo", "cobb": "Cobb", "ellipse": "Elipse",
              "rect": "Retângulo", "polygon": "Polígono", "probe": "Intensidade", "ruler3d": "Régua 3D", "height": "Altura",
              "ctr": "ICT", "spine": "Coluna", "tic": "Curva", "calibration": "Calibrar",
              "arrow": "Seta", "text": "Texto", "pencil": "Lápis", "cross": "Cursor 3D",
              "oblique": "Oblíquo", "curve": "Curvo", "quadzoom": "Quadrante", "loupe": "Lupa",
              "grow": "Segmentar", "caixa_ia": "Caixa IA", "pick": "Selecionar", "pincel": "Pincel"}


class BarraMixin:
    """Barra de ferramentas, botões e menus do ViewerTab."""

    # ================================================================ toolbar
    def _act(self, action_id: str, text: str, slot, checkable: bool = False,
             checked: bool = False) -> QAction:
        a = QAction(text, self, checkable=checkable)
        if checkable:
            a.setChecked(checked)
        a.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        a.setData(action_id)
        if checkable:
            a.toggled.connect(slot)
        else:
            a.triggered.connect(slot)
        self.addAction(a)
        self.actions_by_id[action_id] = a
        return a

    def apply_shortcuts(self) -> None:
        """(Re)aplica os atalhos a partir das preferências."""
        for aid, a in self.actions_by_id.items():
            key = shortcut_for(self.settings, aid)
            a.setShortcut(QKeySequence(key) if key else QKeySequence())
            base = a.text().split("  (")[0]
            tip = f"{base}  ({key})" if key else base
            if aid.startswith("tool.") or aid == "film.add":
                tip += "\nClique direito / do meio no ícone: usar no botão direito / do meio do mouse"
            a.setToolTip(tip)

    TOOLBAR_STYLE = (
        "QToolBar{background:#26272b;border:none;spacing:1px;padding:2px}"
        "QToolButton{color:#e0e0e0;background:transparent;border:none;border-radius:4px;"
        "padding:3px 5px;min-width:46px;font-size:11px}"
        "QToolButton:hover{background:#3a3d44}"
        "QToolButton:checked{background:#35506e}"
        "QToolButton[popupMode=\"1\"]{padding-right:14px}"
        "QToolButton::menu-button{border:none;width:12px}"
        "QToolButton::menu-arrow{width:8px;height:8px}"
        "QToolBar::separator{background:#44474e;width:1px;margin:6px 3px}")
    MENU_STYLE = ("QMenu{background:#2d2f34;color:#e0e0e0;border:1px solid #44474e}"
                  "QMenu::item{padding:5px 28px 5px 8px}"
                  "QMenu::item:selected{background:#35506e}"
                  "QMenu::separator{height:1px;background:#44474e;margin:4px 8px}")

    def _menu(self) -> QMenu:
        m = QMenu(self)
        m.setStyleSheet(self.MENU_STYLE)
        return m

    # Botões que saem da barra por padrão e moram no menu "Mais": são os que ele usa de vez em
    # quando, e a barra tinha 31 itens numa linha só. Quem quiser de volta marca em
    # Preferências ▸ Geral — a lista de fora fica em `viewer.botoes_fora`.
    FORA_POR_PADRAO = ("view.invert", "view.rotate_cw", "view.cine", "view.anonymize")
    NOME_DOS_OPCIONAIS = {"view.invert": "Inverter", "view.rotate_cw": "Girar e espelhar",
                          "view.cine": "Cine", "view.anonymize": "Ocultar dados do paciente"}

    def botoes_fora(self) -> set:
        guardado = self.settings.get("viewer.botoes_fora", None)
        if guardado is None:
            return set(self.FORA_POR_PADRAO)
        return {b for b in guardado if b in self.NOME_DOS_OPCIONAIS}

    def _button(self, tb: QToolBar, action: QAction, menu: QMenu | None = None,
                instant: bool = False, mods: set | None = None,
                opcional: str = "", modulo: str = "", app: str = "") -> QToolButton:
        """`mods`: modalidades em que o botão faz sentido (None = sempre).

        `opcional`: id do botão que o usuário pode tirar da barra (ele continua no menu "Mais").

        `app` (0.99.12): o botão é uma **aplicação** (`aplicacoes.APLICACOES`): não entra aqui, entra
        no bloco "do exame", no fim da barra, e aparece pela regra e pela escolha dele.
        """
        btn = QToolButton()
        btn.setDefaultAction(action)
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setIconSize(QSize(26, 26))
        if menu is not None:
            btn.setMenu(menu)
            btn.setPopupMode(QToolButton.InstantPopup if instant else QToolButton.MenuButtonPopup)
            menu.installEventFilter(self)
        btn.installEventFilter(self)
        if app:
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, a=app, b=btn: self._menu_da_aplicacao(a, b, pos))
            self.__dict__.setdefault("_apps_pendentes", []).append((app, btn))
            return btn
        # o QToolBar embrulha o widget numa QAction; quem manda na visibilidade é ela,
        # não o botão — esconder o widget direto é desfeito no próximo layout da barra
        acao = tb.addWidget(btn)
        if opcional:
            acao.setVisible(opcional not in self.botoes_fora())
            self.__dict__.setdefault("_opcionais", {})[opcional] = acao
        if mods or modulo:
            self.__dict__.setdefault("_mod_buttons", []).append((btn, acao, set(mods or ()), modulo))
            self.update_modality_buttons()
        return btn

    # ------------------------------------------------- botões por modalidade
    def study_modalities(self) -> set:
        """Modalidades que existem nos exames abertos nesta aba."""
        return {(s.modality or "").upper() for s in getattr(self, "series", [])
                if getattr(s, "modality", "")}

    def update_modality_buttons(self) -> None:
        """Esconde o que não serve ao exame aberto (MN fora de MN, 3D fora de volume…) e o que é de
        módulo desligado (Preferências ▸ Módulos) — este, nem com "todos os botões" ligado."""
        from ipe import modules as MOD
        tudo = bool(self.settings.get("viewer.all_buttons", False))
        presentes = self.study_modalities()
        fora = MOD.desligados(self.settings)
        for btn, acao, mods, modulo in getattr(self, "_mod_buttons", []):
            mostra = tudo or not mods or not presentes or bool(mods & presentes)
            mostra = mostra and modulo not in fora
            acao.setVisible(mostra)
            btn.setVisible(mostra)
        self._atualizar_aplicacoes()

    def switch_wl(self) -> None:
        """Próxima janela gravada no arquivo (0.99.22, plano AW M15). Na mamografia vale para os
        quadros à vista: a AW troca a janela das quatro incidências juntas."""
        vp = self.active
        if vp is None:
            return
        msg = vp.switch_wl()
        if not msg:
            self.status_message.emit("Esta imagem não traz janelas gravadas no arquivo.")
            return
        if (vp.modalidade_atual() or "").upper() == "MG":
            i = vp._janela_arquivo[0]
            for v in self._shown():
                if v is not vp and (v.modalidade_atual() or "").upper() == "MG" and v.janelas_do_arquivo():
                    v.usar_janela_do_arquivo(min(i, len(v.janelas_do_arquivo()) - 1))
        self.status_message.emit(msg)

    def outros_referenciais_ligados(self, vp) -> int:
        """Quantos quadros à vista estão no mesmo grupo de sincronia de `vp` com outro Frame of
        Reference (0.99.45). A sincronia automática só junta o mesmo referencial; o grupo junta
        qualquer coisa, pelo deslocamento — e é isso que o selo avisa."""
        hub = getattr(self, "hub", None)
        if hub is None or not vp.frames or not vp.for_uid:
            return 0
        g = hub.group_of(vp)
        if g is None:
            return 0
        n = 0
        for w in hub.viewports(self):
            if w is vp or not w.frames or hub.group_of(w) != g or not w.for_uid:
                continue
            if w.for_uid != vp.for_uid and w.plane() is not None and vp.plane() is not None:
                n += 1
        return n

    def clonar_roi(self, src, ann) -> list[tuple]:
        """Leva a ROI para os outros quadros à vista, na mesma posição no paciente (0.99.45, plano AW
        item 15). Cada cópia é uma ROI nova do quadro de destino: a média, o desvio e a área são os
        da imagem de lá. Devolve [(quadro, motivo ou "")]."""
        from ipe.imaging import clonar_roi as CR
        out = []
        alvos = [w for w in self._shown() if w is not src and w.frames]
        if not alvos:
            self.status_message.emit("Não há outro quadro com imagem para receber a ROI.")
            return out
        feitos = 0
        for w in alvos:
            motivo = CR.clonar(src, ann, w, self.hub)
            out.append((w, motivo))
            if not motivo:
                feitos += 1
        faltas = [f"{w.series_label or 'quadro'}: {m}" for w, m in out if m]
        msg = f"ROI clonada em {feitos} quadro(s)."
        if faltas:
            msg += " Sem cópia — " + "; ".join(faltas[:3])
        self.status_message.emit(msg)
        return out

    def pacientes_no_layout(self) -> list[dict]:
        """A identidade de cada quadro com imagem (para o selo de mistura de pacientes, 0.99.22)."""
        return [vp.study_info for vp in getattr(self, "viewports", []) if vp.frames and vp.study_info]

    # ------------------------------------------------- aplicações do exame (0.99.12)
    def contexto_do_exame(self):
        from ipe.ui.viewer import aplicacoes as AP
        infos = list(getattr(self, "study_infos", {}).values()) or [getattr(self, "study_info", {})]
        extra = {"dinamica"} if getattr(self, "groups", None) else set()
        return AP.contexto(getattr(self, "series", []), infos, self.settings, extra)

    def _montar_bloco_de_aplicacoes(self, tb: QToolBar) -> None:
        """O bloco "do exame": as aplicações na ordem dele, depois de um separador, e o botão
        "Todas as aplicações", que lista todas — inclusive as que a regra tirou, com o motivo."""
        from ipe.ui.viewer import aplicacoes as AP
        pendentes = dict(getattr(self, "_apps_pendentes", []))
        self._sep_apps = tb.addSeparator()
        self._apps: dict[str, tuple] = {}
        # 0.100.37: as IAs num botão só — uma lista, como a das medidas, com as que valem para este exame
        self.ia_menu = self._menu()
        self.ia_menu.setToolTipsVisible(True)
        self.ia_menu.aboutToShow.connect(self._encher_menu_ia)
        ia = self._plain("IA", "ia", "Inteligência artificial: as ferramentas que valem para este exame, os achados "
                                     "para revisar e as tarefas em andamento")
        self.ia_button = self._button(tb, ia, self.ia_menu, instant=True)
        self._acao_ia = tb.actions()[-1]
        for aid in AP.ordem(self.settings):
            btn = pendentes.get(aid)
            if btn is not None:
                self._apps[aid] = (btn, tb.addWidget(btn))
        self.todas_menu = self._menu()
        self.todas_menu.aboutToShow.connect(self._encher_todas_as_aplicacoes)
        todas = self._plain("Aplicações", "apps", "Todas as aplicações: as deste exame e as outras, "
                                                  "com o motivo de não estarem na barra")
        self.todas_button = self._button(tb, todas, self.todas_menu, instant=True)
        self.update_modality_buttons()

    def estado_das_aplicacoes(self) -> dict[str, tuple[bool, str]]:
        """id -> (na barra, motivo). Módulo desligado tira de tudo, até de "Todas"."""
        from ipe import modules as MOD
        from ipe.ui.viewer import aplicacoes as AP
        ctx = self.contexto_do_exame()
        fora = MOD.desligados(self.settings)
        tudo = bool(self.settings.get("viewer.all_buttons", False))
        out = {}
        for aid in getattr(self, "_apps", {}):
            app = AP.APLICACOES[aid]
            if app.modulo and app.modulo in fora:
                out[aid] = (False, "módulo desligado")
                continue
            vis, motivo = AP.mostrar(self.settings, aid, ctx)
            m, _o = AP.modo(self.settings, aid, ctx.regioes)
            if tudo and m != "nunca":
                vis = True
            out[aid] = (vis, motivo)
        return out

    def app_na_barra(self, aid: str) -> bool:
        """A aplicação está à mão na barra — com o seu botão ou, se é uma IA, na lista do botão IA (0.100.37)."""
        from ipe.ui.viewer import aplicacoes as AP
        par = getattr(self, "_apps", {}).get(aid)
        if par and aid in AP.IA and AP.ia_agrupada(self.settings):
            acao_ia = getattr(self, "_acao_ia", None)
            return bool(acao_ia is not None and acao_ia.isVisible() and aid in self.ias_do_exame()[0])
        return bool(par and par[1].isVisible())

    def _atualizar_aplicacoes(self) -> None:
        apps = getattr(self, "_apps", None)
        if not apps:
            return
        from ipe.ui.viewer import aplicacoes as AP
        estado = self.estado_das_aplicacoes()
        agrupar = AP.ia_agrupada(self.settings)
        algum = ia_vale = False
        for aid, (btn, acao) in apps.items():
            vis, motivo = estado.get(aid, (False, ""))
            if agrupar and aid in AP.IA:
                ia_vale = ia_vale or vis
                vis = False                       # entra na lista do botão IA
            acao.setVisible(vis)
            algum = algum or vis
        acao_ia = getattr(self, "_acao_ia", None)
        if acao_ia is not None:
            acao_ia.setVisible(agrupar and ia_vale)
            algum = algum or (agrupar and ia_vale)
        sep = getattr(self, "_sep_apps", None)
        if sep is not None:
            sep.setVisible(algum)

    def ias_do_exame(self) -> tuple[list[str], list[tuple[str, str]]]:
        """As IAs que valem para este exame (na ordem da barra) e as outras, com o motivo."""
        from ipe import modules as MOD
        from ipe.ui.viewer import aplicacoes as AP
        estado = self.estado_das_aplicacoes()
        fora = MOD.desligados(self.settings)
        ids = [a for a in AP.ordem(self.settings) if a in AP.IA and a in getattr(self, "_apps", {})]
        valem = [a for a in ids if estado.get(a, (False, ""))[0]]
        outras = [(a, estado.get(a, (False, ""))[1]) for a in ids if a not in valem
                  and AP.APLICACOES[a].modulo not in fora]
        return valem, outras

    def _encher_menu_ia(self) -> None:
        """A lista do botão IA (0.100.37): cada IA que vale para o exame, com as opções dela; os achados para
        revisar e as tarefas; e, num submenu, as que a regra deixou de fora (rodam mesmo assim)."""
        m = self.ia_menu
        m.clear()
        for velho in self.__dict__.pop("_submenus_de_todas", []):
            velho.deleteLater()
        valem, outras = self.ias_do_exame()
        if hasattr(m, "addSection"):
            m.addSection("Para este exame (na série do quadro ativo)")
        for aid in valem:
            self._item_ia(m, aid, "")
        if not valem:
            a = QAction("Nenhuma IA para este exame pela regra", m)
            a.setEnabled(False)
            m.addAction(a)
        m.addSeparator()
        a = QAction("Achados de IA (revisar, confirmar, descartar)…", m)
        a.triggered.connect(self.abrir_achados)
        m.addAction(a)
        a = QAction("Tarefas de IA (andamento e cancelar)…", m)
        a.triggered.connect(self.abrir_tarefas_ia)
        m.addAction(a)
        if outras:
            sub = QMenu("Outras IAs (não são deste exame; rodam mesmo assim)", m)
            sub.setStyleSheet(self.MENU_STYLE)
            for aid, motivo in outras:
                self._item_ia(sub, aid, motivo)
            m.addMenu(sub)
            self.__dict__.setdefault("_submenus_de_todas", []).append(sub)
        m.addSeparator()
        a = QAction("Mostrar cada IA com o seu botão na barra", m, checkable=True)
        from ipe.ui.viewer import aplicacoes as AP
        a.setChecked(not AP.ia_agrupada(self.settings))
        a.triggered.connect(lambda v: self.agrupar_ia(not v))
        m.addAction(a)

    def _item_ia(self, menu: QMenu, aid: str, motivo: str) -> None:
        """Uma IA na lista: o nome e, ao passar, o que ela faz nesta série (as opções do botão dela); os achados
        ficam uma vez só, no fim da lista."""
        from ipe.ui.viewer import aplicacoes as AP
        btn, _acao = self._apps[aid]
        acao = btn.defaultAction()
        nome = acao.iconText() or acao.text()
        texto = f"{nome} — {motivo}" if motivo else nome
        opcoes = [x for x in (btn.menu().actions() if btn.menu() is not None else [])
                  if not x.isSeparator() and not x.text().startswith("Achados de IA")]
        if not opcoes:
            a = QAction(acao.icon(), texto, menu)
            a.setToolTip(AP.APLICACOES[aid].descricao)
            a.triggered.connect(acao.trigger)
            menu.addAction(a)
            return
        sub = QMenu(texto, menu)
        sub.setIcon(acao.icon())
        sub.setStyleSheet(self.MENU_STYLE)
        sub.setToolTipsVisible(True)
        for x in opcoes:
            sub.addAction(x)
        sub.menuAction().setToolTip(AP.APLICACOES[aid].descricao)
        menu.addMenu(sub)
        self.__dict__.setdefault("_submenus_de_todas", []).append(sub)

    def agrupar_ia(self, sim: bool) -> None:
        from ipe.ui.viewer import aplicacoes as AP
        self.settings.set(AP.CHAVE_IA_AGRUPADA, bool(sim))
        try:
            self.settings.save()
        except Exception:  # noqa: BLE001
            log.debug("salvar a escolha da barra de IA", exc_info=True)
        self._atualizar_aplicacoes()

    def _encher_todas_as_aplicacoes(self) -> None:
        from ipe import modules as MOD
        from ipe.ui.viewer import aplicacoes as AP
        m = self.todas_menu
        m.clear()
        for velho in self.__dict__.pop("_submenus_de_todas", []):
            velho.deleteLater()
        estado = self.estado_das_aplicacoes()
        fora = MOD.desligados(self.settings)
        sec_barra = [a for a in AP.ordem(self.settings) if a in self._apps and estado[a][0]]
        sec_outras = [a for a in AP.ordem(self.settings) if a in self._apps and not estado[a][0]
                      and AP.APLICACOES[a].modulo not in fora]
        if hasattr(m, "addSection"):
            m.addSection("Na barra, para este exame")
        for aid in sec_barra:
            self._item_da_aplicacao(m, aid, "")
        if sec_outras:
            if hasattr(m, "addSection"):
                m.addSection("Fora da barra (rodam mesmo assim)")
            for aid in sec_outras:
                self._item_da_aplicacao(m, aid, estado[aid][1])
        m.addSeparator()
        a = QAction("Tarefas de IA (andamento e cancelar)…", m)          # 0.99.32
        a.triggered.connect(self.abrir_tarefas_ia)
        m.addAction(a)
        a = QAction("Achados de IA (revisar, confirmar, descartar)…", m)  # 0.99.46
        a.triggered.connect(self.abrir_achados)
        m.addAction(a)
        a = QAction("Configurar a barra e as aplicações…", m)
        a.triggered.connect(self._configurar_barra)
        m.addAction(a)

    def _item_da_aplicacao(self, menu: QMenu, aid: str, motivo: str) -> None:
        btn, _acao = self._apps[aid]
        acao = btn.defaultAction()
        nome = acao.iconText() or acao.text()
        texto = f"{nome} — {motivo}" if motivo else nome
        opcoes = btn.menu()
        if opcoes is None:
            a = QAction(acao.icon(), texto, menu)
            a.triggered.connect(acao.trigger)
            menu.addAction(a)
            return
        if btn.popupMode() == QToolButton.InstantPopup:
            # o próprio menu do botão vira o submenu (ele se enche sozinho ao abrir)
            opcoes.setTitle(texto)
            opcoes.setIcon(acao.icon())
            menu.addMenu(opcoes)
            return
        sub = QMenu(texto, menu)
        sub.setIcon(acao.icon())
        sub.setStyleSheet(self.MENU_STYLE)
        principal = QAction(acao.text(), sub)
        principal.triggered.connect(acao.trigger)
        sub.addAction(principal)
        opcoes.setTitle("Opções")
        sub.addMenu(opcoes)
        menu.addMenu(sub)
        self.__dict__.setdefault("_submenus_de_todas", []).append(sub)

    def _menu_da_aplicacao(self, aid: str, btn, pos) -> None:
        self.menu_da_aplicacao(aid).exec(btn.mapToGlobal(pos))

    def menu_da_aplicacao(self, aid: str) -> QMenu:
        """Botão direito numa aplicação da barra: sempre, automático ou nunca — em todo exame ou
        só nesta região (separado de quem exibe, para testar)."""
        from ipe.ui.viewer import aplicacoes as AP
        m = self._menu()
        ctx = self.contexto_do_exame()
        atual, origem = AP.modo(self.settings, aid, ctx.regioes)
        nome = AP.APLICACOES[aid].nome
        if hasattr(m, "addSection"):
            m.addSection(f"Em todos os exames ({nome})")
        for modo in AP.MODOS:
            a = QAction(AP.NOME_DO_MODO[modo], m, checkable=True)
            a.setChecked(origem in ("", "*") and modo == atual)
            a.triggered.connect(lambda _=False, md=modo: self._definir_modo_da_aplicacao(aid, md, "*"))
            m.addAction(a)
        for r in sorted(ctx.regioes):
            nr = AP.nome_da_regiao(self.settings, r)
            if hasattr(m, "addSection"):
                m.addSection(f"Só em exames de {nr.lower()}")
            for modo, rotulo in (("sempre", f"Sempre em exames de {nr.lower()}"),
                                 ("nunca", f"Nunca em exames de {nr.lower()}")):
                a = QAction(rotulo, m, checkable=True)
                a.setChecked(origem == r and atual == modo)
                a.triggered.connect(lambda _=False, md=modo, rr=r: self._definir_modo_da_aplicacao(aid, md, rr))
                m.addAction(a)
            if origem == r:
                a = QAction(f"Tirar a exceção de {nr.lower()}", m)
                a.triggered.connect(lambda _=False, rr=r: self._definir_modo_da_aplicacao(aid, "auto", rr))
                m.addAction(a)
        m.addSeparator()
        regra = QAction(f"Regra: {AP.descrever_regra(AP.APLICACOES[aid], self.settings)}", m)
        regra.setEnabled(False)
        m.addAction(regra)
        a = QAction("Configurar a barra e as aplicações…", m)
        a.triggered.connect(self._configurar_barra)
        m.addAction(a)
        return m

    def _definir_modo_da_aplicacao(self, aid: str, modo: str, regiao: str) -> None:
        from ipe.ui.viewer import aplicacoes as AP
        AP.definir_modo(self.settings, aid, modo, regiao)
        self.settings.save()
        self._atualizar_todas_as_abas()
        vis = self.estado_das_aplicacoes().get(aid, (False, ""))[0]
        nome = AP.APLICACOES[aid].nome
        self.status_message.emit(f"Aplicação {nome}: na barra." if vis else
                                 f"Aplicação {nome}: fora da barra — continua no botão Aplicações.")

    def _atualizar_todas_as_abas(self) -> None:
        win = self.window()
        abas = list(win.all_viewer_tabs()) if hasattr(win, "all_viewer_tabs") else []
        for t in abas or [self]:
            t.update_modality_buttons()
        if self not in abas:
            self.update_modality_buttons()

    def _configurar_barra(self) -> None:
        win = self.window()
        if hasattr(win, "abrir_config_barra"):
            win.abrir_config_barra()
        else:
            from ipe.ui.viewer.barra_config import BarraDialog
            if BarraDialog(self.settings, self).exec():
                self.update_modality_buttons()

    # ------------------------------------------------------------ botões do mouse
    @staticmethod
    def _tool_of_action(a: QAction | None) -> str | None:
        if a is None:
            return None
        data = str(a.data() or "")
        if data.startswith("tool.") and data[5:] in TOOLS:
            return data[5:]
        if data == "film.add":
            return "film"
        return None

    def eventFilter(self, obj, ev) -> bool:  # noqa: N802
        """Clique com o botão direito ou do meio num ícone de ferramenta: atribui a ferramenta a
        esse botão do mouse (o esquerdo continua sendo o clique normal)."""
        t = ev.type()
        if t in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, QEvent.MouseButtonDblClick) \
                and ev.button() in (Qt.RightButton, Qt.MiddleButton):
            if isinstance(obj, QToolButton):
                tool = self._tool_of_action(obj.defaultAction())
            elif isinstance(obj, QMenu):
                tool = self._tool_of_action(obj.actionAt(ev.position().toPoint()))
            else:
                tool = None
            if tool is not None:
                if t == QEvent.MouseButtonRelease:
                    self.set_button_tool("right" if ev.button() == Qt.RightButton else "middle", tool)
                    if isinstance(obj, QMenu):
                        obj.close()
                return True
        return super().eventFilter(obj, ev)

    def irmaos(self) -> list:
        """As abas dos **outros** monitores do mesmo exame.

        Os monitores são uma estação só: o que se escolhe num vale nos outros. Quem muda alguma
        coisa chama isto e repassa — sem repassar de volta, senão os dois ficam se avisando.
        """
        return [t for t in (self.monitor_group or []) if t is not self]

    def mouse_mudou(self) -> None:
        """O mouse mudou em outro lugar: só redesenhar o que mostra o estado."""
        self.refresh_tool_badges()
        for v in self.viewports:
            v.update()

    def set_button_tool(self, button: str, tool: str, propagar: bool = True) -> None:
        mouse = dict(self.settings.get("viewer.mouse", {}) or {})
        mouse[button] = tool
        self.settings.set("viewer.mouse", mouse)
        try:
            self.settings.save()
        except Exception as e:  # noqa: BLE001
            log.warning("não salvou o mouse: %s", e)
        self.mouse_mudou()
        if propagar:
            for t in self.irmaos():
                t.mouse_mudou()
        name = {"right": "Botão direito", "middle": "Botão do meio"}[button]
        extra = ""
        if Viewport.is_click_tool(tool):
            extra = (" — Shift + clique direito abre o menu" if button == "right"
                     else " — Shift + clique do meio ajusta a imagem")
        self.status_message.emit(f"{name}: {TOOLS.get(tool, tool)}{extra}")

    def refresh_tool_badges(self) -> None:
        """Selo D (direito) / M (meio) nos ícones das ferramentas atribuídas a esses botões."""
        if not hasattr(self, "tool_actions"):
            return
        mouse = self.settings.get("viewer.mouse", {}) or {}
        right, middle = mouse.get("right", "zoom"), mouse.get("middle", "pan")
        targets = dict(self.tool_actions)
        if hasattr(self, "film_action"):
            targets["film.add"] = self.film_action
        for key, a in targets.items():
            tool = "film" if key == "film.add" else key
            base = icon(TOOL_ICONS.get(tool, tool))
            letters = "".join(x for x, t in (("D", right), ("M", middle)) if t == tool)
            if letters:
                from ipe.ui.icons import with_corner_letter
                pm = with_corner_letter(base.pixmap(64, 64), letters)
                a.setIcon(QIcon(pm))
            else:
                a.setIcon(base)

    def showEvent(self, e) -> None:  # noqa: N802
        self.refresh_tool_badges()
        super().showEvent(e)

    def _plain(self, text: str, icon_name: str, tip: str = "") -> QAction:
        a = QAction(icon(icon_name), text, self)
        a.setToolTip(tip or text)
        return a

    def _build_toolbar(self) -> QToolBar:
        self.actions_by_id: dict[str, QAction] = {}
        tb = QToolBar()
        tb.setStyleSheet(self.TOOLBAR_STYLE)
        tb.setIconSize(QSize(26, 26))
        tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        group = QActionGroup(self)
        self.tool_actions: dict[str, QAction] = {}
        for key, name in TOOLS.items():
            a = self._act(f"tool.{key}", name, lambda _=False, kk=key: self.set_left_tool(kk))
            a.setCheckable(True)
            a.setIcon(icon(TOOL_ICONS.get(key, key)))
            a.setIconText(TOOL_SHORT.get(key, name))
            group.addAction(a)
            self.tool_actions[key] = a
        self.tool_actions.get(self.left_tool, self.tool_actions["wl"]).setChecked(True)

        # --- janela/nível (clique: ferramenta; seta: presets)
        wl_menu = self._menu()
        wl_menu.aboutToShow.connect(lambda: self._fill_preset_menu(wl_menu))
        self._button(tb, self.tool_actions["wl"], wl_menu)
        self._button(tb, self.tool_actions["pan"])
        zoom_menu = self._menu()
        self._button(tb, self.tool_actions["zoom"], zoom_menu)
        scroll_menu = self._menu()
        self._button(tb, self.tool_actions["scroll"], scroll_menu)

        # --- medidas: o botão mostra a última ferramenta escolhida
        self.measure_menu = self._menu()
        for key in MEASURE_TOOLS:
            if key in ("measure", "text"):
                self.measure_menu.addSeparator()
            self.measure_menu.addAction(self.tool_actions[key])
        self.measure_menu.addSeparator()
        self.continuous_action = self._act(
            "annot.continuous", "Medição contínua (a ferramenta continua ativa)",
            lambda on: self.settings.set("viewer.measure_continuous", on), checkable=True,
            checked=bool(self.settings.get("viewer.measure_continuous", True)))
        self.measure_menu.addAction(self.continuous_action)
        self.measure_menu.addSeparator()
        nxt = self._act("annot.next", "Próxima imagem com medida",
                        lambda: self._on_active(lambda v: v.go_to_annotation(1)))
        nxt.setIcon(icon("next"))
        prv = self._act("annot.prev", "Imagem anterior com medida",
                        lambda: self._on_active(lambda v: v.go_to_annotation(-1)))
        prv.setIcon(icon("prev"))
        self.measure_menu.addAction(nxt)
        self.measure_menu.addAction(prv)
        self.annot_list_menu = self.measure_menu.addMenu("Ir para a medida…")
        self.annot_list_menu.setStyleSheet(self.MENU_STYLE)
        self.annot_list_menu.aboutToShow.connect(self._fill_annotation_list)
        self.measure_menu.addSeparator()
        for text, fn in (("Apagar a medida selecionada (Del)",
                          lambda v: v.delete_annotation(v.selected) if v.selected else None),
                         ("Apagar as medidas desta imagem", lambda v: v.delete_frame_annotations()),
                         ("Apagar todas as medidas da série…", self._delete_series_annotations)):
            a = QAction(icon("trash"), text, self)
            a.triggered.connect(lambda _=False, f=fn: self._on_active(f))
            self.measure_menu.addAction(a)
        self.measure_menu.addSeparator()
        self.measure_menu.addAction(self._act("annot.export", "Exportar medidas para planilha (CSV/Excel)…",
                                              self.export_measures_table))
        hint = QAction("Editar: clique na medida e arraste as pontas; botão direito sobre ela = opções", self)
        hint.setEnabled(False)
        self.measure_menu.addAction(hint)
        first = self.left_tool if self.left_tool in MEASURE_TOOLS else "measure"
        self.measure_button = self._button(tb, self.tool_actions[first], self.measure_menu)
        self._button(tb, self.tool_actions["cross"])
        tb.addSeparator()

        # --- layout e imagem
        layout_menu = self._menu()
        for rows, cols in LAYOUTS:
            a = QAction(f"{rows} × {cols}", self)
            a.triggered.connect(lambda _=False, r=rows, c=cols: self.set_layout(r, c))
            layout_menu.addAction(a)
        self._button(tb, self._plain("Layout", "layout", "Layout dos quadros"), layout_menu, instant=True)
        inv = self._act("view.invert", "Inverter", lambda: self._on_active(lambda v: v.set_invert()))
        inv.setIcon(icon("invert"))
        self._button(tb, inv, opcional="view.invert")
        rot_menu = self._menu()
        rcw = self._act("view.rotate_cw", "Girar 90° à direita", lambda: self._on_active(lambda v: v.rotate_view(90)))
        rcw.setIcon(icon("rotate"))
        rcw.setIconText("Girar")
        rot_menu.addAction(rcw)
        rot_menu.addAction(self._act("view.rotate_ccw", "Girar 90° à esquerda",
                                     lambda: self._on_active(lambda v: v.rotate_view(-90))))
        rot_menu.addAction(self._act("view.rotate_180", "Girar 180°",
                                     lambda: self._on_active(lambda v: v.rotate_view(180))))
        rot_menu.addSeparator()
        rot_menu.addAction(self._act("view.flip_h", "Espelhar esquerda ↔ direita",
                                     lambda: self._on_active(lambda v: v.flip_view(True))))
        rot_menu.addAction(self._act("view.flip_v", "Espelhar cima ↕ baixo",
                                     lambda: self._on_active(lambda v: v.flip_view(False))))
        rot_menu.addSeparator()
        rot_menu.addAction(self._act("view.orient_reset", "Voltar à orientação original",
                                     lambda: self._on_active(lambda v: v.reset_orientation())))
        a_all = QAction("Aplicar o giro/espelho do quadro ativo a todos os quadros", self)
        a_all.triggered.connect(self.orientation_to_all)
        rot_menu.addAction(a_all)
        self._button(tb, rcw, rot_menu, opcional="view.rotate_cw")
        self.cmap_menu = self._menu()
        self.cmap_menu.aboutToShow.connect(self._fill_cmap_menu)
        cm = self._plain("Cor", "palette", "Tabela de cores (pseudocor) do quadro ativo")
        self._button(tb, cm, self.cmap_menu, instant=True)
        self.fusion_menu = self._menu()
        self.fusion_menu.aboutToShow.connect(self._fill_fusion_menu)
        fu = self._plain("Fusão", "fusion", "Fusão: sobrepor outra série ao quadro ativo (ex.: PET na TC)")
        self._button(tb, fu, self.fusion_menu, instant=True, app="fusao")
        self._act("wl.switch", "Switch WL", self.switch_wl)
        fit = self._act("view.fit", "Ajustar à janela", lambda: self._on_active(lambda v: v.fit()))
        fit.setIcon(icon("fit"))
        reset = self._act("view.reset", "Restaurar", lambda: self._on_active(lambda v: v.reset_view()))
        reset.setIcon(icon("reset"))
        reset_menu = self._menu()
        reset_menu.addAction(fit)
        reset_menu.addAction(reset)
        self._button(tb, reset, reset_menu)
        cine = self._act("view.cine", "Cine", lambda: self._on_active(lambda v: v.toggle_cine()))
        cine.setIcon(icon("cine"))
        self._button(tb, cine, opcional="view.cine")
        zoom_menu.addAction(fit)
        zoom_menu.addSeparator()
        zoom_menu.addAction(self.tool_actions["loupe"])
        zoom_menu.addAction(self.tool_actions["quadzoom"])
        one = QAction("Tamanho real (1 pixel da imagem = 1 da tela)", self)
        one.triggered.connect(lambda: self._on_active(lambda v: v.zoom_actual_pixels()))
        zoom_menu.addAction(one)
        zoom_menu.addSeparator()
        zoom_menu.addAction(reset)
        wl_menu.addSeparator()
        wl_menu.addAction(self._act("view.histogram", "Histograma da imagem (ou da ROI)…",
                                    lambda: self._on_active(self.show_histogram)))
        scroll_menu.addAction(cine)
        goto = QAction("Ir para a imagem…", self)
        goto.triggered.connect(lambda: self._on_active(self._ask_image))
        scroll_menu.addAction(goto)
        sp = self._act("series.prev", "Série anterior", lambda: self._cycle_series(-1))
        sn = self._act("series.next", "Próxima série", lambda: self._cycle_series(1))
        sp.setIcon(icon("prev"))
        sn.setIcon(icon("next"))
        tb.addSeparator()

        # --- MPR
        self.mpr_action = self._act("mpr.toggle", "MPR 3 planos (axial, coronal, sagital)", self.toggle_mpr,
                                    checkable=True)
        self.mpr_action.setIcon(icon("mpr"))
        self.mpr_action.setIconText("MPR")
        mpr_menu = self._menu()
        mpr_menu.addAction(self.mpr_action)
        mpr_menu.addSeparator()
        for name, key in (("Axial", "A"), ("Coronal", "C"), ("Sagital", "S")):
            mpr_menu.addAction(self._act(f"mpr.{name.lower()}", f"Reconstruir no quadro ativo: {name}",
                                         lambda _=False, n=name: self.reconstruct_plane(n)))
        mpr_menu.addAction(self._act("mpr.obliquo_daqui", "Oblíquo a partir do plano atual (sem mudar a imagem)",
                                     lambda: self.reformatar(self.active, "Oblíquo")))
        mpr_menu.addAction(self.tool_actions["oblique"])
        mpr_menu.addAction(self.tool_actions["rotplane"])
        mpr_menu.addSeparator()
        save = QAction("Salvar a reconstrução do quadro ativo como série nova", self)
        save.triggered.connect(lambda: self.save_reconstruction(self.active, notify=True))
        mpr_menu.addAction(save)
        back = QAction("Voltar o quadro ativo à série original", self)
        back.triggered.connect(self._plane_back)
        mpr_menu.addAction(back)
        self._button(tb, self.mpr_action, mpr_menu, app="mpr")
        menu3d = self._menu()
        for text, fn in (("Renderização de volume (VR)…", lambda: self.open_3d("vr")),
                         ("MIP 3D girável…", lambda: self.open_3d("mip")),
                         ("MinIP 3D (vias aéreas)…", lambda: self.open_3d("minip"))):
            a = QAction(text, self)
            a.triggered.connect(fn)
            menu3d.addAction(a)
        a = QAction("Comparar duas fases lado a lado (4D)…", self)
        a.triggered.connect(lambda: self.compare_phases())
        menu3d.addAction(a)
        a = QAction("Superfície 3D por limiar (STL)…", self)
        a.triggered.connect(self.open_surface)
        menu3d.addAction(a)
        menu3d.addSeparator()
        menu3d.addAction(self.tool_actions["curve"])
        menu3d.addAction(self.tool_actions["grow"])
        est = self._act("estruturas.abrir", "Estruturas: editar máscaras (SEG / RTSTRUCT)",
                        lambda: self.abrir_estruturas())
        menu3d.addAction(est)
        tm = QAction("Resumo das segmentações (TMTV / TLG)…", self)
        tm.triggered.connect(self.show_tmtv)
        menu3d.addAction(tm)
        b3d = self._act("view.3d", "3D: renderização de volume", lambda: self.open_3d("vr"))
        b3d.setIcon(icon("cube"))
        b3d.setIconText("3D")
        self._button(tb, b3d, menu3d, app="3d")
        dyn = self._act("dyn.open", "Avaliação dinâmica (MSI, PEI, SER e curvas)", lambda: self.open_dynamic())
        dyn.setIcon(icon("tic"))
        dyn.setIconText("Dinâmica")
        self._button(tb, dyn, app="dinamica")
        menu_nm = self._menu()
        a = QAction("Curvas atividade-tempo por região…", self)
        a.triggered.connect(lambda: NMV.open_analysis(self))
        menu_nm.addAction(a)
        a = QAction("Comparar imagens do exame (DMSA, paratireoide, tireoide, trânsito)…", self)
        a.triggered.connect(lambda: NMV.open_multi(self))
        menu_nm.addAction(a)
        menu_nm.addSeparator()
        a = QAction("Anterior e posterior lado a lado", self)
        a.triggered.connect(lambda: NMV.open_ant_post(self))
        menu_nm.addAction(a)
        a = QAction("Anterior, posterior e média geométrica", self)
        a.triggered.connect(lambda: NMV.open_ant_post(self, with_gm=True))
        menu_nm.addAction(a)
        menu_nm.addSeparator()
        a = QAction("Espelhar a vista posterior na média geométrica", self)
        a.setCheckable(True)
        a.setChecked(bool(self.settings.get("nm.flip_post", True)))
        a.toggled.connect(self._nm_set_flip)
        menu_nm.addAction(a)
        a = QAction("Escala de cinza invertida nas imagens de medicina nuclear", self)
        a.setCheckable(True)
        a.setChecked(bool(self.settings.get("nm.invert", True)))
        a.toggled.connect(self._nm_set_invert)
        menu_nm.addAction(a)
        self.nm_action = self._act("nm.ant_post", "Medicina nuclear: anterior e posterior lado a lado",
                                   lambda: NMV.open_ant_post(self))
        self.nm_action.setIcon(icon("tic"))
        self.nm_action.setIconText("MN")
        self._button(tb, self.nm_action, menu_nm, app="mn")

        # --- sincronização (clique: ligar quadros; seta: opções)
        sync_menu = self._menu()
        # 0.99.10: as duas primeiras linhas escolhem COMO o botão Sincronizar sincroniza.
        # Automática: os quadros do mesmo exame vão para o mesmo ponto do paciente (alinhados pelo
        # quadro ativo ao ligar). Manual: ficam ligados mantendo a diferença de cortes do momento.
        # A automática continua lembrada por modalidade (na RM nasce desligada, 0.99.9).
        self.sync_auto_action = self._act("sync.auto", "Automática (mesmo ponto do paciente)",
                                          lambda *_a: self.escolher_modo_sync("auto"))
        self.sync_manual_action = self._act("sync.manual", "Manual (mantém a diferença entre os quadros)",
                                            lambda *_a: self.escolher_modo_sync("manual"))
        self.sync_modo_group = QActionGroup(self)
        for a in (self.sync_auto_action, self.sync_manual_action):
            a.setCheckable(True)
            self.sync_modo_group.addAction(a)
        self.sync_auto_action.setToolTip("Ao ligar, os outros quadros do mesmo exame vão para o ponto do "
                                         "quadro ativo e passam a andar com ele")
        self.sync_manual_action.setToolTip("Ao ligar, os quadros andam juntos mantendo a diferença de cortes "
                                           "que tinham na hora (serve para comparar com outro exame)")
        self.sync_wl_action = self._act("sync.window", "Janela/nível",
                                        lambda on: self.hub.set_flag("sync_wl", on),
                                        checkable=True, checked=self.hub.sync_wl)
        self.sync_zoom_action = self._act("sync.zoom", "Zoom e pan",
                                          lambda on: self.hub.set_flag("sync_zoom", on),
                                          checkable=True, checked=self.hub.sync_zoom)
        self.strip_action = self._act("view.strip", "Tira de séries (miniaturas)",
                                      lambda on: self.strip_col.setVisible(on),
                                      checkable=True, checked=True)
        self.strip_action.setToolTip("Mostrar ou esconder a coluna de miniaturas desta tela. Com o "
                                     "exame repartido entre monitores ela vem escondida nas telas "
                                     "de dentro (Preferências ▸ Monitores).")
        self.refs_action = self._act("view.reflines", "Linhas de referência",
                                     lambda on: self.hub.set_flag("show_refs", on),
                                     checkable=True, checked=self.hub.show_refs)
        for a in (self.sync_auto_action, self.sync_manual_action):
            sync_menu.addAction(a)
        sync_menu.addSeparator()
        for a in (self.sync_wl_action, self.sync_zoom_action, self.refs_action, self.strip_action):
            sync_menu.addAction(a)
        sync_menu.addSeparator()
        self.sync_mode_action = self._act(
            "sync.mode", "Alternar modo: desligado / mesmo estudo / todos",
            lambda: self.status_message.emit(self.hub.cycle_mode(self)))
        sync_menu.addAction(self.sync_mode_action)
        grp = self._act("sync.group", "Trocar grupo do quadro ativo (corrente)",
                        lambda: self._on_active(self._cycle_group))
        sync_menu.addAction(grp)
        a = QAction("Desligar todos os grupos", self)
        a.triggered.connect(lambda: (self.hub.unlink_all(), self.update_reference_lines()))
        sync_menu.addAction(a)
        sync_menu.addSeparator()
        conf = sync_menu.addMenu("Conferir o registro com o outro exame")
        for modo, nome in (("xadrez", "Xadrez"), ("cortina", "Cortina (segue o mouse)"), ("diferenca", "Diferença"),
                           ("mistura", "Mistura 50%")):
            conf.addAction(self._act(f"registro.conferir.{modo}", f"Conferir o registro: {nome}",
                                     lambda _=False, m=modo: self.conferir_registro(m)))
        conf.addSeparator()
        conf.addAction(self._act("registro.conferir.off", "Conferir o registro: desligar",
                                 lambda: self.conferir_registro(None)))
        sync_menu.addAction(self._act("sync.register", "Alinhar automaticamente com o outro exame (registro)",
                                      self.auto_register))
        self.link_action = self._act("sync.link", "Ligar quadros", self.toggle_link, checkable=True)
        self.link_action.setIcon(icon("sync"))
        self.link_action.setIconText("Sincronizar")
        self.link_action.setToolTip("Liga ou desliga a sincronização, automática ou manual "
                                    "(seta: escolher e outras opções)")
        self._button(tb, self.link_action, sync_menu)
        tb.addSeparator()

        # --- imagens-chave, anteriores, monitor, ocultar
        key = self._act("key.toggle", "Marcar/desmarcar imagem-chave", self.toggle_key_image)
        key.setIcon(icon("key"))
        key.setIconText("Chave")
        show_keys = self._act("key.show", "Mostrar imagens-chave", self.show_key_images)
        key_menu = self._menu()
        key_menu.addAction(key)
        key_menu.addAction(show_keys)
        key_menu.addSeparator()
        grava_ko = self._act("key.gravar", "Gravar imagens-chave e anotações no exame (KO + GSPS)",
                             lambda: self.gravar_ko_gsps())
        key_menu.addAction(grava_ko)
        self._button(tb, key, key_menu)
        self.priors_menu = self._menu()
        self.priors_menu.aboutToShow.connect(self._fill_priors_menu)
        self.priors_action = QAction(icon("priors"), "Anteriores", self, checkable=True)
        self.priors_action.setToolTip("Linha do tempo do paciente (banco e PACS); seta: menu rápido")
        self.priors_action.toggled.connect(self.toggle_priors_panel)
        self._button(tb, self.priors_action, self.priors_menu)
        self._act("study.revisado", "Exame: marcar como revisado (ou voltar ao automático)",
                  lambda: self.marcar_revisado())
        self._act("study.priors", "Adicionar exame anterior",
                  lambda: self.priors_menu.exec(self.mapToGlobal(self.rect().center())))
        self.measures_action = self._act("measures.panel", "Medidas", self.toggle_measures_panel,
                                         checkable=True)
        self.measures_action.setIcon(icon("measure"))
        self.measures_action.setIconText("Medidas")
        self.measures_action.setToolTip("Todas as medidas e ROIs do exame numa lista: clicar leva até a "
                                        "imagem com a medida já selecionada")
        self._button(tb, self.measures_action)
        # --- oncologia / IA / laudo
        self.lesions_action = self._act("lesion.panel", "Lesões", self.toggle_lesion_panel, checkable=True)
        self.lesions_action.setIcon(icon("lesion"))
        self.lesions_action.setIconText("Lesões")
        les_menu = self._menu()
        les_menu.addAction(self.lesions_action)
        la = QAction("Layout das lesões (um quadro por lesão)", self)
        la.triggered.connect(lambda: self.lesion_layout())
        les_menu.addAction(la)
        lk = QAction("Ligar a medida selecionada a uma lesão…", self)
        lk.triggered.connect(lambda: self._on_active(lambda v: self.choose_lesion_for(v, v.selected)
                                                     if v.selected is not None else None))
        les_menu.addAction(lk)
        self._button(tb, self.lesions_action, les_menu)
        self.overlay_menu = self._menu()
        self.overlay_menu.aboutToShow.connect(lambda: self._fill_overlay_menu(self.overlay_menu))
        self.overlay_action = self._act("overlay.toggle", "CAD/IA", self.toggle_overlays)
        self.overlay_action.setIcon(icon("ai"))
        self.overlay_action.setIconText("CAD/IA")
        self.overlay_action.setToolTip("Resultados de CAD/IA, segmentações (SEG/RTSTRUCT) e anotações de outros "
                                       "sistemas (GSPS). Clique: mostrar/ocultar; seta: lista")
        self._button(tb, self.overlay_action, self.overlay_menu)
        rep = self._act("report.open", "Laudo", self.open_report)
        rep.setIcon(icon("report"))
        rep.setIconText("Laudo")
        self._button(tb, rep)
        film = self._act("film.add", "Enviar ao filme", self.film_add_current)
        film.setIcon(icon("film"))
        film.setIconText("Filme")
        self.film_action = film
        film_menu = self._menu()
        film_menu.addAction(film)
        film_menu.addAction(self.tool_actions["film"])
        film_menu.addAction(self._act("film.add_all", "Enviar todos os quadros", self.film_add_all))
        film_menu.addAction(self._act("film.series", "Série do quadro (inteira / intervalo)…", self.film_add_series))
        film_menu.addAction(self._act("film.keys", "Imagens-chave do exame", self.film_add_keys))
        film_menu.addSeparator()
        film_menu.addAction(self._act("film.show", "Abrir o compositor de filmes",
                                      lambda: self.film_requested.emit({"kind": "show"})))
        self._button(tb, film, film_menu)
        mon = self._plain("Monitor", "monitor", "Mover este estudo para uma janela em outro monitor")
        mon.triggered.connect(lambda: self.detach_requested.emit(self))
        self._button(tb, mon)
        self._act("cad.revelar", "Revelar o CAD (ler antes, ver depois)", lambda: self.revelar_cad())
        self._act("view.mosaico", "Mosaico de cortes no quadro (2×2 → 3×3 → 4×4 → desligado)",
                  lambda: self._on_active(lambda v: v.proximo_mosaico()))
        self.anon_action = self._act("view.anonymize", "Ocultar dados do paciente",
                                     self.set_anonymize, checkable=True)
        self.anon_action.setIcon(icon("anon"))
        self.anon_action.setIconText("Ocultar")
        # 0.99.42: perfis de ocultação (Ocultar tudo / Tela / Ensino / Publicação), na seta do botão
        self.perfil_menu = self._menu()
        self.perfil_menu.aboutToShow.connect(self._encher_menu_de_perfis)
        self._button(tb, self.anon_action, self.perfil_menu, opcional="view.anonymize")

        # --- anotações da tela (0.99.9): completa / parcial 1 / parcial 2 / ausente
        from ipe.ui.viewer import anotacoes as AN
        self.anot_menu = self._menu()
        self.anot_group = QActionGroup(self)
        self.anot_actions: dict[str, QAction] = {}
        for chave, nome in AN.NIVEIS:
            a = QAction(nome, self, checkable=True)
            a.triggered.connect(lambda _=False, c=chave: self.set_anotacoes(c))
            self.anot_group.addAction(a)
            self.anot_menu.addAction(a)
            self.anot_actions[chave] = a
        self.anot_menu.addSeparator()
        self.anot_menu.addAction(self._act("view.annot_next", "Anotações: próximo nível",
                                           self.proximo_nivel_de_anotacao))
        # 0.100.40: a letra das anotações (os dados dos cantos) maior ou menor, sem ir às Preferências
        self.anot_menu.addSeparator()
        self.letra_info = QAction("", self)
        self.letra_info.setEnabled(False)
        self.anot_menu.addAction(self.letra_info)
        self.anot_menu.addAction(self._act("view.letra_maior", "Letra maior", lambda: self.mudar_letra(+1)))
        self.anot_menu.addAction(self._act("view.letra_menor", "Letra menor", lambda: self.mudar_letra(-1)))
        self.anot_menu.addAction(self._act("view.letra_normal", "Letra no tamanho normal", lambda: self.mudar_letra(0)))
        self.anot_menu.addSeparator()
        cfg = QAction("Escolher o que cada nível mostra…", self)
        cfg.triggered.connect(lambda: self.preferences_requested.emit("Anotações"))
        self.anot_menu.addAction(cfg)
        self.anot_button_action = self._plain("Anotações", "text",
                                              "Anotações da tela: completa, parcial 1, parcial 2 ou ausente")
        self.anot_button_action.triggered.connect(self.proximo_nivel_de_anotacao)
        self._button(tb, self.anot_button_action, self.anot_menu)
        self.copy_action = self._act("view.copy", "Copiar a imagem do quadro (área de transferência)",
                                     self.copiar_quadro)
        self.reflect_anotacoes()

        # --- mais
        more = self._menu()
        # O que saiu da barra entra aqui: botão escondido não pode virar função perdida.
        self._mais_opcionais = more.addSection("Da barra de ferramentas") if hasattr(more, "addSection") else None
        for aid in self.FORA_POR_PADRAO:
            acao = self.actions_by_id.get(aid)
            if acao is not None:
                more.addAction(acao)
        more.addSeparator()
        more.addAction(sp)
        more.addAction(sn)
        more.addSeparator()
        exportar = self._act("study.export", "Exportar (DICOM, CD/pendrive, imagens)…", self.export_dialog)
        more.addAction(exportar)
        sr = QAction("Salvar medidas como DICOM SR…", self)
        sr.triggered.connect(self.save_measurements_sr)
        more.addAction(sr)
        # Tudo o que tira dado do programa; a janela da chamada externa "só visualizador" esconde.
        self.acoes_de_saida = [exportar, sr, self.film_action]
        more.addSeparator()
        tags = QAction("Informações DICOM (tags)…", self)
        tags.triggered.connect(lambda: self._on_active(lambda v: v.show_tags()))
        more.addAction(tags)
        # medidas guiadas (0.99.14): MRPI, Evans, ângulo calosal — aparece em RM/TC de crânio
        menu_idx = self._menu()
        a_nres = QAction("Resultado dos índices automáticos deste exame…", self)
        a_nres.triggered.connect(lambda: self.abrir_neuro(do_exame=True))
        menu_idx.addAction(a_nres)
        a_nauto = QAction("Índices automáticos (IA, SynthSeg) desta série…", self)
        a_nauto.triggered.connect(lambda: self.neuro_automatica(self.active))
        menu_idx.addAction(a_nauto)
        menu_idx.aboutToShow.connect(lambda: a_nres.setEnabled(self.neuro_do_exame() is not None))
        a_sr = QAction("Criar T1 sintético de 1 mm desta série (IA, SynthSR)…", self)   # 0.100.23
        a_sr.triggered.connect(lambda: self.t1_sintetico(self.active))
        menu_idx.addAction(a_sr)
        menu_idx.addSeparator()
        from ipe.imaging import roteiros as RT
        for rid, rot in RT.ROTEIROS.items():
            a = QAction(rot.nome + "…", self)
            a.triggered.connect(lambda _=False, r=rid: self.abrir_roteiro(r))
            menu_idx.addAction(a)
        idx = self._act("roteiro.mrpi", "Medidas guiadas: MRPI e MRPI 2.0",
                        lambda: self.abrir_roteiro("mrpi"))
        idx.setIcon(icon("app_indices"))
        idx.setIconText("Índices")
        self._button(tb, idx, menu_idx, app="indices")
        # cefalometria do cavum (0.99.15): automática (TotalSegmentator) ou à mão — TC de face/pescoço
        menu_cef = self._menu()
        a_res = QAction("Resultado da cefalometria automática deste exame…", self)
        a_res.triggered.connect(lambda: self.abrir_cefalometria(do_exame=True))
        menu_cef.addAction(a_res)
        a_auto = QAction("Cefalometria automática (IA) desta série…", self)
        a_auto.triggered.connect(lambda: self.cefalometria_automatica(self.active))
        menu_cef.addAction(a_auto)
        a_mao = QAction("Cefalometria à mão (roteiro)…", self)
        a_mao.triggered.connect(lambda: self.abrir_cefalometria(do_exame=False))
        menu_cef.addAction(a_mao)
        menu_cef.aboutToShow.connect(lambda: a_res.setEnabled(self.cefalometria_do_exame() is not None))
        cef = self._act("cefalometria.auto", "Cefalometria do cavum (automática)", self.cefalometria_botao)
        cef.setIcon(icon("app_cefalometria"))
        cef.setIconText("Cefalometria")
        self._button(tb, cef, menu_cef, app="cefalometria")
        # níveis linfonodais (0.99.20): mapa na TC de pescoço; a lesão segmentada ganha o nível
        lin = self._act("linfonodos.auto", "Mapa dos níveis linfonodais (IA)",
                        lambda: self.linfonodos_automatico(self.active))
        lin.setIcon(icon("app_linfonodos"))
        lin.setIconText("Linfonodos")
        self._button(tb, lin, None, app="linfonodos")
        # nódulos pulmonares (0.99.46): achados revisáveis
        menu_nod = self._menu()
        a_nod = QAction("Procurar nódulos pulmonares nesta série (IA)…", self)
        a_nod.triggered.connect(self._nodulos_do_ativo)
        menu_nod.addAction(a_nod)
        a_ach = QAction("Achados de IA (revisar, confirmar, descartar)…", self)
        a_ach.triggered.connect(self.abrir_achados)
        menu_nod.addAction(a_ach)
        nod = self._act("nodulos.auto", "Nódulos pulmonares (IA)", self.nodulos_botao)
        nod.setIcon(icon("app_nodulos"))
        nod.setIconText("Nódulos")
        self._button(tb, nod, menu_nod, app="nodulos")
        self._act("achados.abrir", "Achados de IA: revisar, confirmar, descartar", self.abrir_achados)
        # composição corporal em L3 e esteatose (0.99.47)
        menu_comp = self._menu()
        a_comp = QAction("Medir a composição corporal em L3 e o fígado nesta série (IA)…", self)
        a_comp.triggered.connect(self._composicao_do_ativo)
        menu_comp.addAction(a_comp)
        a_ach2 = QAction("Achados de IA (revisar, confirmar, descartar)…", self)
        a_ach2.triggered.connect(self.abrir_achados)
        menu_comp.addAction(a_ach2)
        comp = self._act("composicao.auto", "Composição corporal em L3 e esteatose (IA)", self.composicao_botao)
        comp.setIcon(icon("app_composicao"))
        comp.setIconText("Composição")
        self._button(tb, comp, menu_comp, app="composicao")
        # gordura e ferro hepáticos na RM (0.99.49)
        menu_fig = self._menu()
        a_fig = QAction("Medir a gordura (PDFF) e o ferro (R2*) do fígado nesta RM (IA)…", self)
        a_fig.triggered.connect(self._figado_rm_do_ativo)
        menu_fig.addAction(a_fig)
        a_ach3 = QAction("Achados de IA (revisar, confirmar, descartar)…", self)
        a_ach3.triggered.connect(self.abrir_achados)
        menu_fig.addAction(a_ach3)
        fig = self._act("figado_rm.auto", "Gordura e ferro hepáticos na RM (IA)", self.figado_rm_botao)
        fig.setIcon(icon("app_figado"))
        fig.setIconText("Fígado")
        self._button(tb, fig, menu_fig, app="figado_rm")
        # enfisema e Genant (0.99.77): o mesmo molde da composição
        for tipo, rotulo_menu, nome_acao, texto_icone in (
                ("enfisema", "Medir o enfisema (% abaixo de −950 HU por lobo) nesta série (IA)…",
                 "Enfisema: % abaixo de −950 HU por pulmão e lobo (IA)", "Enfisema"),
                ("genant", "Medir as alturas vertebrais (Genant) nesta série (IA)…",
                 "Fratura vertebral — Genant (IA)", "Genant"),
                ("figado_lesoes", "Achar as lesões hepáticas e a carga por segmento nesta série (IA)…",
                 "Lesões hepáticas e carga por segmento (IA)", "Lesões"),
                ("autopet", "Achar as lesões no PET-FDG (MTV e TLG) nesta série (IA)…",
                 "Lesões no PET-FDG: MTV e TLG (IA)", "autoPET"),
                ("brats", "Segmentar o glioma (captante, necrose, edema) nesta RM (IA)…",
                 "Glioma na RM — BraTS (IA)", "BraTS"),
                ("flames", "Achar as lesões de substância branca no FLAIR deste exame (IA)…",
                 "Lesões de substância branca no FLAIR — FLAMeS (IA)", "Lesões SB"),
                ("medula", "Medir a medula e o canal por nível (área, AP, MSCC) nesta série (IA)…",
                 "Medula e canal: área e compressão por nível (IA)", "Medula"),
                ("aorta", "Medir o diâmetro da aorta por segmento (perpendicular ao eixo) nesta TC…",
                 "Aorta: diâmetro por segmento (IA)", "Aorta"),
                ("calcio", "Medir o escore de cálcio coronariano (Agatston) nesta TC sem contraste…",
                 "Cálcio coronariano — Agatston (IA)", "Cálcio"),
                ("carga_pet", "Medir a carga tumoral deste PET (FDG, PSMA ou DOTA)…",
                 "Carga tumoral no PET (FDG/PSMA/DOTA)", "Carga")):
            menu_x = self._menu()
            a_x = QAction(rotulo_menu, self)
            a_x.triggered.connect(lambda _=False, tp=tipo: self.ferramenta_ia(tp, self.active))
            menu_x.addAction(a_x)
            a_r = QAction("Achados de IA (revisar, confirmar, descartar)…", self)
            a_r.triggered.connect(self.abrir_achados)
            menu_x.addAction(a_r)
            if tipo == "genant":            # 0.99.78: saiu do botão direito do quadro, fica aqui
                a_col = QAction("Identificar vértebras e discos desta série (IA)…", self)
                a_col.triggered.connect(lambda: self.active is not None
                                        and self.segmentar_orgaos(self.active, tipo="coluna"))
                menu_x.addAction(a_col)
            bx = self._act(f"{tipo}.auto", nome_acao, lambda _=False, tp=tipo: self.ferramenta_ia_botao(tp))
            bx.setIcon(icon(f"app_{tipo}"))
            bx.setIconText(texto_icone)
            self._button(tb, bx, menu_x, app=tipo)
        # órgãos abdominais (0.99.32, pedido dele: também no botão Aplicações)
        menu_abd = self._menu()
        a_abd = QAction("Segmentar órgãos abdominais desta série (IA)…", self)
        a_abd.triggered.connect(lambda: self.segmentar_orgaos(self.active))
        menu_abd.addAction(a_abd)
        a_tar = QAction("Tarefas de IA (andamento e cancelar)…", self)
        a_tar.triggered.connect(self.abrir_tarefas_ia)
        menu_abd.addAction(a_tar)
        abd = self._act("abdome.auto", "Segmentar órgãos abdominais (IA)",
                        lambda: self.segmentar_orgaos(self.active))
        abd.setIcon(icon("app_orgaos"))
        abd.setIconText("Órgãos")
        self._button(tb, abd, menu_abd, app="abdome")
        # difusão (0.99.37, pedido dele: em todas as RM, não só na mama)
        dwi = self._act("difusao.abrir", "Difusão: ADC, DWI sintética e ADC na ROI", self.abrir_difusao)
        dwi.setIcon(icon("app_difusao"))
        dwi.setIconText("Difusão")
        self._button(tb, dwi, None, app="difusao")
        self._montar_bloco_de_aplicacoes(tb)
        self._button(tb, self._plain("Mais", "more", "Mais opções"), more, instant=True)

        # barra do MPR (slab)
        self.mpr_bar = QToolBar()
        self.mpr_bar.setStyleSheet("QToolBar{background:#1a2530;color:#ddd;spacing:6px}"
                                   "QLabel{color:#ddd}")
        self.mpr_bar.addWidget(QLabel("  MPR — espessura (slab):"))
        self.slab_combo = QComboBox()
        for mm in SLAB_CHOICES:
            self.slab_combo.addItem("fino" if mm == 0 else f"{mm} mm", mm)
        self.mode_combo = QComboBox()
        for k, name in SLAB_MODES.items():
            self.mode_combo.addItem(name, k)
        self.slab_all = QAction("Aplicar aos 3 planos", self, checkable=True, checked=True)
        self.slab_combo.currentIndexChanged.connect(self._apply_slab)
        self.mode_combo.currentIndexChanged.connect(self._apply_slab)
        self.mpr_bar.addWidget(self.slab_combo)
        self.mpr_bar.addWidget(QLabel(" modo:"))
        self.mpr_bar.addWidget(self.mode_combo)
        self.mpr_bar.addAction(self.slab_all)
        self.mpr_info = QLabel("")
        self.mpr_bar.addWidget(self.mpr_info)
        self.mpr_bar.setVisible(False)
        from ipe.ui.viewer.render3d_view import Render3DBar
        self.render3d_bar = Render3DBar(self)

        # barra da fusão
        from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QSlider
        self.fusion_bar = QToolBar()
        self.fusion_bar.setStyleSheet("QToolBar{background:#2a2018;color:#ddd;spacing:6px}QLabel{color:#ddd}"
                                      "QCheckBox{color:#ddd}")
        self.fusion_label = QLabel("  Fusão")
        self.fusion_bar.addWidget(self.fusion_label)
        self.fusion_bar.addWidget(QLabel("  opacidade:"))
        self.fusion_alpha = QSlider(Qt.Horizontal)
        self.fusion_alpha.setRange(0, 100)
        self.fusion_alpha.setFixedWidth(140)
        self.fusion_alpha.valueChanged.connect(lambda v: self._fusion_set(alpha=v / 100))
        self.fusion_bar.addWidget(self.fusion_alpha)
        self.fusion_bar.addWidget(QLabel(" cor:"))
        self.fusion_cmap = QComboBox()
        from ipe.imaging import colormaps as CM
        for k in ("hot", "pet", "rainbow", "gold", "hotmetal", "jet", "thallium", "spectrum"):
            self.fusion_cmap.addItem(CM.name(k), k)
        self.fusion_cmap.activated.connect(lambda _i: self._fusion_set(cmap=self.fusion_cmap.currentData()))
        self.fusion_bar.addWidget(self.fusion_cmap)
        self.fusion_bar.addWidget(QLabel(" mín:"))
        self.fusion_lo = QDoubleSpinBox(decimals=2, minimum=-1e6, maximum=1e7)
        self.fusion_lo.editingFinished.connect(lambda: self._fusion_set(lo=self.fusion_lo.value()))
        self.fusion_bar.addWidget(self.fusion_lo)
        self.fusion_bar.addWidget(QLabel(" máx:"))
        self.fusion_hi = QDoubleSpinBox(decimals=2, minimum=-1e6, maximum=1e7)
        self.fusion_hi.editingFinished.connect(lambda: self._fusion_set(hi=self.fusion_hi.value()))
        self.fusion_bar.addWidget(self.fusion_hi)
        self.fusion_hide = QCheckBox("ocultar abaixo do mínimo")
        self.fusion_hide.toggled.connect(lambda on: self._fusion_set(hide_below=on))
        self.fusion_bar.addWidget(self.fusion_hide)
        a_all = QAction("Todos os quadros", self)
        a_all.triggered.connect(self.fusion_to_all)
        self.fusion_bar.addAction(a_all)
        a_rm = QAction("Remover", self)
        a_rm.triggered.connect(lambda: self.remove_fusion(self.active))
        self.fusion_bar.addAction(a_rm)
        self.fusion_bar.setVisible(False)

        # barra da mamografia (protocolo por etapas, quadrantes, lupa)
        from ipe.ui.viewer.mammo_view import MgBar
        self._act("mg.next", "Mamografia: próxima etapa do protocolo", lambda: self.mg_next(1))
        self._act("mg.prev", "Mamografia: etapa anterior do protocolo", lambda: self.mg_next(-1))
        self._act("phase.next", "Dinâmica: próxima fase", lambda: self.fase_passo(1))
        self._act("phase.prev", "Dinâmica: fase anterior", lambda: self.fase_passo(-1))
        self._act("mg.quad_next", "Zoom por quadrante: próximo quadrante", lambda: self.mg_quadrant_cycle(self.active, 1))
        self._act("mg.quad_prev", "Zoom por quadrante: quadrante anterior", lambda: self.mg_quadrant_cycle(self.active, -1))
        self._act("mg.tomo", "Mamografia: pular entre 2D e tomossíntese", lambda: self.mg_toggle_tomo())
        self._act("mg.cem", "Mamografia contrastada: baixa energia / recombinada", lambda: self.mg_toggle_cem())
        self._act("mg.implant", "Mamografia: corrigir o implante",
                  lambda: self.mg_set_implant(not getattr(self, "mg_implant", False)))
        self._act("mg.slab", "Tomossíntese: próxima espessura", lambda: self.mg_set_slab(-1))
        self._act("mg.enquadrar", "Mamografia: enquadrar a mama no quadro", lambda: self.mg_enquadrar())
        self._act("mg.inverter_mama", "Mamografia: inverter só a mama",
                  lambda: self.mg_set_inverter_mama(not getattr(self, "mg_inverter_mama", False)))
        self._act("mg.corte_chave", "Mamografia: corte da tomo como imagem-chave", lambda: self.mg_corte_chave())
        self._act("mg.chave_proxima", "Imagens-chave: próximo corte marcado", lambda: self.mg_proximo_chave(1))
        self._act("mg.chave_anterior", "Imagens-chave: corte marcado anterior", lambda: self.mg_proximo_chave(-1))
        # Os atalhos se aplicam **depois** da última ação criada. Até a 0.65 esta chamada ficava
        # no meio da montagem da barra, antes do bloco da mamografia: as teclas de mamografia
        # nasciam mortas e só passavam a funcionar depois que ele abrisse Preferências e
        # salvasse (é dali que vem a única outra chamada de `apply_shortcuts`). Com a lista de
        # atalhos zerada, as três teclas que sobraram são justamente deste bloco.
        self.apply_shortcuts()
        self.refresh_tool_badges()
        self.mg_bar = MgBar(self)
        from ipe.ui.viewer.etapas import EtapasBar
        self.etapas_bar = EtapasBar(self)
        return tb

    def _fill_cmap_menu(self) -> None:
        m = self.cmap_menu
        m.clear()
        vp = self.active
        if vp is None:
            return
        vp.add_colormap_actions(m, lembrar=True)
        m.addSeparator()
        a = QAction("Aplicar a cor do quadro ativo a todos os quadros", m)
        a.triggered.connect(self.colormap_to_all)
        m.addAction(a)

    def orientation_to_all(self) -> None:
        vp = self.active
        if vp is None:
            return
        st = vp.state
        for v in self._shown():
            if v is not vp:
                v.set_orientation(st.rot, st.flip_h, st.flip_v)

    def colormap_to_all(self) -> None:
        vp = self.active
        if vp is None:
            return
        for v in self._shown():
            if v is not vp and v._img is not None and not v._img.is_color:
                v.state.cmap = vp.state.cmap
                v._qimage_key = None
                v.update()

    def _fill_preset_menu(self, menu: QMenu) -> None:
        menu.clear()
        vp = self.active
        js = vp.janelas_do_arquivo() if vp is not None else ()
        if js:
            menu.addAction("Do arquivo (Switch WL)").setEnabled(False)
            for i, (nome, w, l) in enumerate(js):
                a = menu.addAction(f"   {nome}  (W {w:g} / L {l:g})")
                a.triggered.connect(lambda _=False, k=i: self._on_active(lambda v: v.usar_janela_do_arquivo(k)))
            menu.addSeparator()
        presets = vp.presets_da_janela() if vp is not None else self.settings.get("viewer.wl_presets", {})
        for key, (name, w, l) in sorted(presets.items()):
            if not name:
                continue
            a = menu.addAction(f"{name}   (W {w:g} / L {l:g})")
            a.setShortcut(QKeySequence(key))
            a.triggered.connect(lambda _=False, kk=key: self._on_active(lambda v: v.apply_preset(kk)))
        menu.addSeparator()
        a = menu.addAction("Automático / do arquivo")
        a.setShortcut(QKeySequence("0"))
        a.triggered.connect(lambda: self._on_active(
            lambda v: (setattr(v.state, "window_set", False), v._load_current(), v.update())))
        menu.addSeparator()
        menu.addAction("Digitar a janela…").triggered.connect(lambda: self._on_active(lambda v: v.digitar_janela()))
        menu.addAction("Guardar a janela atual como preset…").triggered.connect(
            lambda: self._on_active(lambda v: v.guardar_janela_atual()))

    def _fill_annotation_list(self) -> None:
        m = self.annot_list_menu
        m.clear()
        v = self.active
        items = v.annotation_summary() if v is not None else []
        if not items:
            m.addAction("Nenhuma medida nesta série").setEnabled(False)
        for i, text in items[:60]:
            a = m.addAction(text)
            a.triggered.connect(lambda _=False, k=i, vv=v: vv.go_to(k))

    def _delete_series_annotations(self, vp: Viewport) -> None:
        n = len([a for a in vp.annotations if a.done])
        if n and QMessageBox.question(self, "Apagar medidas",
                                      f"Apagar as {n} medidas desta série?") == QMessageBox.Yes:
            vp.delete_series_annotations()

    def _ask_image(self, vp: Viewport) -> None:
        if not vp.frames:
            return
        from PySide6.QtWidgets import QInputDialog
        n, ok = QInputDialog.getInt(self, "Ir para imagem", f"Imagem (1–{len(vp.frames)}):",
                                    vp.index + 1, 1, len(vp.frames))
        if ok:
            vp.go_to(n - 1)

    def _on_active(self, fn) -> None:
        if self.active is not None:
            fn(self.active)

    def set_left_tool(self, tool: str, propagar: bool = True) -> None:
        self.left_tool = tool
        if tool in self.tool_actions:
            self.tool_actions[tool].setChecked(True)
        if tool in MEASURE_TOOLS and hasattr(self, "measure_button"):
            self.measure_button.setDefaultAction(self.tool_actions[tool])
            self.measure_button.setMenu(self.measure_menu)
        for v in self.viewports:
            v.left_tool = tool
            v.update()
        if propagar:
            for t in self.irmaos():
                t.set_left_tool(tool, propagar=False)

    def set_meeting(self, label: str, bar: QWidget | None = None) -> None:
        """Modo reunião: dados do paciente ocultos e travados; o nome amigável aparece no lugar."""
        self.case_label = label
        self.anon_action.setChecked(True)
        self.anon_action.setEnabled(False)
        self.set_anonymize(True)
        if bar is not None:
            self._root_layout.insertWidget(0, bar)
            bar.show()

    # ------------------------------------------------------------ anotações e cópia (0.99.9)
    def set_anotacoes(self, nivel: str) -> None:
        """Troca o nível de anotação de **todos** os quadros e guarda a escolha."""
        from ipe.ui.viewer import anotacoes as AN
        if nivel not in AN.NOME_DO_NIVEL:
            return
        self.settings.set("viewer.anotacoes_nivel", nivel)
        try:
            self.settings.save()
        except Exception:  # noqa: BLE001 - não gravar não pode impedir de trocar na tela
            log.debug("não gravei o nível de anotação", exc_info=True)
        self.anotacoes_mudaram.emit(nivel)
        self.reflect_anotacoes()
        for v in self.viewports:
            v.update()
        self.status_message.emit(f"Anotações: {AN.NOME_DO_NIVEL[nivel]}")

    LETRA_PASSO, LETRA_MIN, LETRA_MAX = 0.1, 0.6, 2.5

    def mudar_letra(self, sentido: int) -> float:
        """Letra das anotações (os dados dos cantos: paciente, série, janela, FOV) maior (+1), menor (−1) ou no
        tamanho normal (0). É a mesma escolha de Preferências ▸ Geral ▸ "Letra das informações nos cantos", e vale
        para todas as janelas. Devolve a escala nova."""
        chave = "viewer.overlay_font_scale"
        try:
            atual = float(self.settings.get(chave, 1.0) or 1.0)
        except (TypeError, ValueError):
            atual = 1.0
        nova = 1.0 if sentido == 0 else atual + sentido * self.LETRA_PASSO
        nova = round(max(self.LETRA_MIN, min(self.LETRA_MAX, nova)), 2)
        self.settings.set(chave, nova)
        try:
            self.settings.save()
        except Exception:  # noqa: BLE001 - não gravar não pode impedir de trocar na tela
            log.debug("não gravei a letra das anotações", exc_info=True)
        from ipe.ui.viewer import anotacoes as AN
        self.anotacoes_mudaram.emit(AN.nivel_atual(self.settings))      # as outras janelas redesenham
        self.reflect_anotacoes()
        pct = round(nova * 100)
        if sentido and nova in (self.LETRA_MIN, self.LETRA_MAX):
            self.status_message.emit(f"Letra das anotações: {pct}% (limite)")
        else:
            self.status_message.emit(f"Letra das anotações: {pct}%")
        return nova

    def proximo_nivel_de_anotacao(self) -> None:
        from ipe.ui.viewer import anotacoes as AN
        self.set_anotacoes(AN.proximo(AN.nivel_atual(self.settings)))

    def reflect_anotacoes(self) -> None:
        """Botão e menu dizem o nível em uso (também quando outra janela o trocou)."""
        from ipe.ui.viewer import anotacoes as AN
        if not hasattr(self, "anot_actions"):
            return
        nivel = AN.nivel_atual(self.settings)
        for chave, a in self.anot_actions.items():
            a.setChecked(chave == nivel)
        self.anot_button_action.setText(f"Anot.: {AN.NOME_DO_NIVEL[nivel]}")
        info = getattr(self, "letra_info", None)
        if info is not None:
            try:
                escala = float(self.settings.get("viewer.overlay_font_scale", 1.0) or 1.0)
            except (TypeError, ValueError):
                escala = 1.0
            info.setText(f"Letra das anotações: {round(escala * 100)}%")
        for v in self.viewports:
            v.update()

    def copiar_quadro(self) -> bool:
        """Ctrl+C: o quadro ativo vai para a área de transferência como está na tela."""
        vp = self.active
        if vp is None or not vp.frames:
            self.status_message.emit("Nada para copiar: clique num quadro com imagem.")
            return False
        try:
            tam = vp.copiar_para_area_de_transferencia()
        except Exception:  # noqa: BLE001
            log.exception("copiar o quadro")
            self.status_message.emit("Não consegui copiar a imagem do quadro.")
            return False
        if tam is None:
            self.status_message.emit("Nada para copiar: o quadro ainda não tem imagem.")
            return False
        self.status_message.emit(f"Imagem copiada ({tam[0]} × {tam[1]} px) — cole com Ctrl+V.")
        return True

    def _encher_menu_de_perfis(self) -> None:
        from PySide6.QtGui import QActionGroup
        from ipe.core import mascara as MK
        m = self.perfil_menu
        m.clear()
        cab = m.addAction("Ao ocultar, mostrar:")
        cab.setEnabled(False)
        g = QActionGroup(m)
        atual = MK.perfil_de(self.settings)
        for chave, nome in MK.PERFIS.items():
            a = m.addAction(nome)
            a.setCheckable(True)
            a.setChecked(chave == atual)
            a.setEnabled(not self.case_label)
            g.addAction(a)
            a.triggered.connect(lambda _=False, k=chave: self.set_perfil_de_ocultacao(k))
        m.addSeparator()
        nota = m.addAction("Ocultar na tela não muda os arquivos: o que sai passa pela anonimização.")
        nota.setEnabled(False)

    def set_perfil_de_ocultacao(self, perfil: str, ligar: bool = True) -> None:
        """Escolhe o perfil (vale para todas as abas e para a lista do banco) e liga o Ocultar."""
        from ipe.core import mascara as MK
        self.settings.set(MK.CHAVE, MK.normalizar(perfil))
        if ligar and not self.anonymize:
            self.anon_action.setChecked(True)
        self.set_anonymize(self.anonymize)
        self.perfil_mudou.emit(MK.normalizar(perfil))

    def set_anonymize(self, on: bool) -> None:
        if self.case_label and not on:
            return                      # reunião: não dá para mostrar os dados
        self.anonymize = on
        for v in self.viewports:
            v.anonymize = on
            v.case_label = self.case_label
            v.update()
        self._fill_strip()
        w = self.parentWidget()
        while w is not None and not isinstance(w, QTabWidget):
            w = w.parentWidget()
        if w is not None and w.indexOf(self) >= 0:
            w.setTabText(w.indexOf(self), self.title()[:40])
            w.setTabToolTip(w.indexOf(self), self.title())
        elif self.window() is not None and self.window() is not self:
            self.window().setWindowTitle(self.title())
