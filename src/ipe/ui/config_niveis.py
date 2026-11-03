"""Configurações ▸ Usuários ▸ Pessoais e compartilhadas… (0.99.30).

Uma janela só para ver e mudar **quem vê** cada item das listas de configuração — protocolos de
exibição, protocolos de mamografia, layouts da dinâmica, modelos de folha, modelos de laudo — e das
listas de casos. As janelas de cada configuração continuam as mesmas; esta é a do "Visível para".

As regras são as de core/itens.py (e, no modo cliente, o servidor confere de novo). Atalhos, mouse,
presets de janela e o resto das preferências do visualizador são de cada usuário, com o padrão do
computador por baixo: a aba "Preferências" deixa voltar ao padrão ou (quem configura) tornar as suas o
padrão deste computador.
"""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ipe.auth import visibilidade as V
from ipe.core import itens as IT

#: preferências que são de cada usuário (core/config.USER_KEYS), com o nome da tela
PREFERENCIAS = [("shortcuts", "Atalhos de teclado"), ("viewer.mouse", "Mouse"),
                ("viewer.wl_presets", "Presets de janela"), ("viewer.wl_presets_mod", "Presets por modalidade"),
                ("browser.columns", "Colunas da lista de exames")]


def base_de(chave: str, settings):
    """A lista que vale enquanto ninguém gravou com usuários: a do computador ou a de fábrica."""
    from ipe.core.config import _get
    ok, v = _get(settings.data, chave) if settings is not None else (False, None)
    if ok and isinstance(v, list) and v:
        return copy.deepcopy(v)
    if chave == "hanging_protocols":
        from ipe.ui.viewer.hanging import DEFAULT_PROTOCOLS
        return [dict(x) for x in DEFAULT_PROTOCOLS]
    if chave == "mg_protocols":
        from ipe.imaging.mammo import DEFAULT_MG_PROTOCOLS
        return [dict(x) for x in DEFAULT_MG_PROTOCOLS]
    if chave == "dyn.layouts":
        from ipe.ui.viewer.dinamica_config import FABRICA
        return copy.deepcopy(FABRICA)
    if chave == "report_templates":
        from ipe.reporting.templates import default_templates
        return default_templates()
    return []


class ConfigNiveisDialog(QDialog):
    def __init__(self, repo, settings, parent=None):
        super().__init__(parent)
        self.repo, self.settings = repo, settings
        self.visao = V.visao_atual()
        self.setWindowTitle("Configurações pessoais e compartilhadas")
        self.resize(820, 540)
        lay = QVBoxLayout(self)
        t = QLabel("Quem vê cada item: <b>Todos</b> (do serviço), <b>Só eu</b> ou <b>eu e usuários escolhidos</b>. "
                   "Um item pessoal com o nome de um do serviço toma o lugar dele só para o dono — é assim que "
                   "você ajusta um protocolo do serviço para você sem mexer no dos outros.")
        t.setWordWrap(True)
        lay.addWidget(t)
        self.abas = QTabWidget()
        lay.addWidget(self.abas, 1)
        self.tabelas: dict[str, QTableWidget] = {}
        for chave, (_campo, titulo) in IT.CHAVES.items():
            self.abas.addTab(self._aba(chave), titulo)
        self.abas.addTab(self._aba("listas"), "Listas de casos")
        self.abas.addTab(self._aba_preferencias(), "Preferências")
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        for chave in self.tabelas:
            self.recarregar(chave)

    # ------------------------------------------------------------------ montagem
    def _aba(self, chave: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        tab = QTableWidget(0, 3 if self._admin() else 2)
        tab.setHorizontalHeaderLabels(["Nome", "Visível para", "Dono"][: tab.columnCount()])
        tab.setSelectionBehavior(QAbstractItemView.SelectRows)
        tab.setSelectionMode(QAbstractItemView.SingleSelection)
        tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tab.horizontalHeader().setStretchLastSection(True)
        tab.verticalHeader().setVisible(False)
        from ipe.ui.tabelas import colunas_ajustaveis
        colunas_ajustaveis(tab)
        tab.setColumnWidth(0, 360)
        tab.setColumnWidth(1, 180)
        self.tabelas[chave] = tab
        lay.addWidget(tab, 1)
        bot = QHBoxLayout()
        for texto, fn in (("Todos (do serviço)", lambda: self.mudar(chave, "todos")),
                          ("Só eu", lambda: self.mudar(chave, "eu")),
                          ("Eu e usuários escolhidos…", lambda: self.mudar(chave, "escolher"))):
            b = QPushButton(texto)
            b.clicked.connect(fn)
            bot.addWidget(b)
        if chave != "listas":
            b = QPushButton("Copiar para mim")
            b.setToolTip("Cria uma cópia pessoal do item (do serviço ou compartilhado com você) para você ajustar")
            b.clicked.connect(lambda: self.copiar(chave))
            bot.addWidget(b)
        if self._admin():
            b = QPushButton("Passar para ▾")
            b.clicked.connect(lambda _=False, bb=b: self._menu_passar(chave, bb))
            bot.addWidget(b)
        bot.addStretch(1)
        lay.addLayout(bot)
        return w

    def _aba_preferencias(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        t = QLabel("Atalhos, mouse, presets de janela e colunas são de cada usuário. Quem nunca mexeu usa o "
                   "padrão deste computador.")
        t.setWordWrap(True)
        lay.addWidget(t)
        b1 = QPushButton("Voltar ao padrão deste computador (apaga as minhas)")
        b1.clicked.connect(self.voltar_ao_padrao)
        b2 = QPushButton("Tornar as minhas o padrão deste computador")
        b2.setToolTip("Quem nunca mexeu passa a usar as suas. Pede a permissão de configurar.")
        b2.setEnabled(V.pode("configure"))
        b2.clicked.connect(self.tornar_padrao)
        lay.addWidget(b1)
        lay.addWidget(b2)
        lay.addStretch(1)
        return w

    def _admin(self) -> bool:
        return self.visao is not None and self.visao.admin

    # ------------------------------------------------------------------ dados
    def itens(self, chave: str) -> list[dict]:
        if chave == "listas":
            return [d for d in self.repo.case_list_tree(gerenciar=True)]
        v = self.repo.itens_de_config(chave, gerenciar=True)
        if v is None:
            v = [{**x, "dono": "", "visivel_para": ""} for x in base_de(chave, self.settings)]
        return v

    def recarregar(self, chave: str) -> None:
        tab = self.tabelas[chave]
        lista = self.itens(chave)
        tab.setRowCount(0)
        for x in lista:
            r = tab.rowCount()
            tab.insertRow(r)
            nome = x.get("name") if chave == "listas" else IT.nome_de(chave, x)
            if chave == "listas" and x.get("kind") == "folder":
                nome = "📁 " + nome
            it = QTableWidgetItem(nome)
            it.setData(Qt.UserRole, x)
            tab.setItem(r, 0, it)
            tab.setItem(r, 1, QTableWidgetItem(V.rotulo(x, self.visao)))
            if tab.columnCount() > 2:
                tab.setItem(r, 2, QTableWidgetItem(x.get("dono") or "(serviço)"))

    def _escolhido(self, chave: str) -> dict | None:
        tab = self.tabelas[chave]
        r = tab.currentRow()
        if r < 0:
            QMessageBox.information(self, "Visível para", "Escolha um item na lista.")
            return None
        return tab.item(r, 0).data(Qt.UserRole)

    def _base(self, chave: str):
        return None if chave == "report_templates" else base_de(chave, self.settings)

    def _aplicar(self, chave: str, x: dict, dono: str, vp: str) -> bool:
        try:
            if chave == "listas":
                self.repo.escopo_da_lista(x["id"], dono, vp)
            else:
                self.repo.escopo_de_item_de_config(chave, IT.nome_de(chave, x), x.get("dono", ""), dono, vp,
                                                   base=self._base(chave))
        except Exception as e:  # noqa: BLE001
            QMessageBox.information(self, "Visível para", _msg(e))
            return False
        self._depois(chave)
        return True

    def _depois(self, chave: str) -> None:
        if chave != "listas" and getattr(self.settings, "itens", None) is not None:
            self.settings.itens.limpar()
        self.recarregar(chave)
        try:
            from ipe.auth import session as S
            self.repo.audit("escopo_de_config", f"{chave}", user=S.get().username)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ ações
    def mudar(self, chave: str, como: str) -> bool:
        x = self._escolhido(chave)
        if x is None or self.visao is None:
            return False
        dono = x.get("dono", "") or ""
        if como == "todos":
            return self._aplicar(chave, x, "", "")
        if como == "eu":
            novo = dono if dono and self._admin() else self.visao.usuario
            return self._aplicar(chave, x, novo, "")
        from ipe.ui.visivel_para import EscolherUsuarios
        dono = dono or self.visao.usuario
        try:
            nomes = list(self.repo.nomes_de_usuarios())
        except Exception:  # noqa: BLE001
            nomes = []
        d = EscolherUsuarios([n for n in nomes if n.lower() != dono.lower()], V.lista(x.get("visivel_para")), self)
        if not d.exec():
            return False
        return self._aplicar(chave, x, dono, ",".join(d.escolhidos()))

    def copiar(self, chave: str) -> bool:
        x = self._escolhido(chave)
        if x is None:
            return False
        try:
            self.repo.escopo_de_item_de_config(chave, IT.nome_de(chave, x), x.get("dono", ""), copiar=True,
                                               base=self._base(chave))
        except Exception as e:  # noqa: BLE001
            QMessageBox.information(self, "Copiar para mim", _msg(e))
            return False
        self._depois(chave)
        return True

    def _menu_passar(self, chave: str, botao) -> None:
        m = QMenu(self)
        try:
            nomes = list(self.repo.nomes_de_usuarios())
        except Exception:  # noqa: BLE001
            nomes = []
        for n in nomes:
            m.addAction(n, lambda n=n: self.passar(chave, n))
        m.exec(botao.mapToGlobal(botao.rect().bottomLeft()))

    def passar(self, chave: str, para: str) -> bool:
        x = self._escolhido(chave)
        return x is not None and self._aplicar(chave, x, para, "")

    # ------------------------------------------------------------------ preferências de cada um
    def voltar_ao_padrao(self) -> int:
        from ipe.core.config import _del
        u = getattr(self.settings, "user", None)
        if u is None:
            QMessageBox.information(self, "Preferências", "Sem usuário logado: já é o padrão deste computador.")
            return 0
        n = 0
        for chave, _t in PREFERENCIAS:
            from ipe.core.config import _get
            ok, _v = _get(u, chave)
            if ok:
                _del(u, chave)
                n += 1
        self.settings.save()
        QMessageBox.information(self, "Preferências", f"{n} preferência(s) suas voltaram ao padrão deste computador.")
        return n

    def tornar_padrao(self) -> int:
        from ipe.core.config import _get, _set
        if not V.pode("configure"):
            return 0
        u = getattr(self.settings, "user", None) or {}
        n = 0
        for chave, _t in PREFERENCIAS:
            ok, v = _get(u, chave)
            if ok:
                _set(self.settings.data, chave, copy.deepcopy(v))
                n += 1
        self.settings.save()
        QMessageBox.information(self, "Preferências", f"{n} preferência(s) suas viraram o padrão deste computador.")
        return n


def _msg(e: Exception) -> str:
    t = str(e)
    return t.split(": ", 1)[1] if t.startswith(("PermissionError", "Error")) else t
