"""Painel "Locais" — o banco deste computador, os outros locais e os nós PACS.

Inspirado no painel Sources do OsiriX/Horos: um clique troca de local; a lista de exames passa a
ser a daquele local. Um local é uma pasta que carrega o banco inteiro (ver core/locations.py).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QHBoxLayout, QInputDialog, QMenu, QMessageBox,
    QPushButton, QStyle, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ipe.core import locations as L
from ipe.ui.tabelas import colunas_ajustaveis

# ícone de cada tipo de local (os do próprio sistema, para ficar igual ao Windows/Linux do usuário)
ICON = {"default": QStyle.SP_ComputerIcon, "external": QStyle.SP_DriveHDIcon,
        "network": QStyle.SP_DriveNetIcon, "folder": QStyle.SP_DirIcon, "central": QStyle.SP_DriveNetIcon}


class LocationsPanel(QWidget):
    """Lista os locais e os nós PACS. Emite o id do local ao trocar."""

    location_chosen = Signal(str)          # id do local
    move_default_requested = Signal()      # mudar a pasta do banco deste computador
    pacs_chosen = Signal(object)           # id do nó (ou None = abrir o PACS como está)
    add_requested = Signal()               # pediu para acrescentar um local
    rescan_requested = Signal(str)         # id do local: procurar exames novos na pasta
    banco_chosen = Signal(str)             # 0.99.27: visivel | meu | compartilhado | comigo | usuario:<nome>
    enviar_ao_servidor_requested = Signal(str)   # 0.99.28: id do local cujo banco vai para o servidor central

    def __init__(self, settings, paths, repo=None, parent=None):
        super().__init__(parent)
        self.settings, self.paths = settings, paths
        self.repo = repo
        self.banco = "visivel"

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(12)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.setMinimumHeight(110)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        colunas_ajustaveis(self.tree)

        b_add = QPushButton("+ Local…")
        b_add.setToolTip("Acrescentar uma pasta com exames: HD externo, pasta de rede ou outra pasta do PC")
        b_add.clicked.connect(self.add_requested.emit)
        btns = QHBoxLayout()
        btns.addWidget(b_add)
        self._botoes = QWidget()
        self._botoes.setLayout(btns)

        # Cabeçalho que recolhe: com muitos locais (ou nenhum) o painel só rouba altura da
        # coluna das listas de casos. O estado fica guardado.
        self.cabecalho = QToolButton()
        self.cabecalho.setAutoRaise(True)
        self.cabecalho.setStyleSheet("QToolButton { border: none; font-weight: bold; padding: 2px; }")
        self.cabecalho.clicked.connect(lambda: self.recolher(not self._recolhido))
        self._recolhido = False

        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(self.cabecalho)
        box.addWidget(self.tree, 1)
        box.addWidget(self._botoes)
        self.rebuild()
        self.recolher(bool(self.settings.get("browser.locais_recolhido", False))
                      if self.settings is not None else False)

    # ------------------------------------------------------------------ recolher
    def recolher(self, on: bool) -> None:
        self._recolhido = bool(on)
        self.tree.setVisible(not self._recolhido)
        self._botoes.setVisible(not self._recolhido)
        if self.settings is not None:
            self.settings.set("browser.locais_recolhido", self._recolhido)
        self._texto_do_cabecalho()

    def _texto_do_cabecalho(self) -> None:
        if self._recolhido:
            atual = ""
            try:
                loc = L.find(self.settings, self.paths, L.current_id(self.settings))
                atual = loc.name if loc is not None else ""
            except Exception:  # noqa: BLE001
                atual = ""
            self.cabecalho.setText("▸ Locais" + (f"  ({atual})" if atual else ""))
            self.cabecalho.setToolTip("Mostrar a lista de locais e de nós do PACS")
        else:
            self.cabecalho.setText("▾ Locais")
            self.cabecalho.setToolTip("Recolher o painel de locais")

    # ------------------------------------------------------------------ lista
    def rebuild(self) -> None:
        cur = L.current_id(self.settings)
        nodes = self._nodes()
        self.tree.clear()
        if nodes:                       # só vale a pena separar em grupos quando há nós de busca
            grupo = QTreeWidgetItem(self.tree, ["Exames guardados"])
            grupo.setFlags(Qt.ItemIsEnabled)
            grupo.setForeground(0, Qt.gray)
        escolhido = None
        for loc in L.all_locations(self.settings, self.paths):
            on = loc.online()
            it = QTreeWidgetItem(self.tree, [loc.name])
            it.setIcon(0, self.style().standardIcon(ICON.get(loc.kind, QStyle.SP_DirIcon)))
            it.setData(0, Qt.UserRole, ("loc", loc.id))
            it.setToolTip(0, f"{loc.kind_label()} — {loc.path}" if not loc.is_default
                          else f"{loc.kind_label()} — {loc.path}")
            if not on:
                it.setText(0, f"{loc.name}   (fora do ar)")
                it.setForeground(0, Qt.gray)
                it.setToolTip(0, f"{loc.path}\nA pasta não está acessível agora "
                                 "(disco desconectado ou rede fora do ar).")
            if loc.id == cur:
                f = it.font(0)
                f.setBold(True)
                it.setFont(0, f)
                escolhido = it
        self._bancos()
        if nodes:
            g2 = QTreeWidgetItem(self.tree, ["Buscar no PACS"])
            g2.setFlags(Qt.ItemIsEnabled)
            g2.setForeground(0, Qt.gray)
            for n in nodes:
                it = QTreeWidgetItem(self.tree, [n["name"]])
                it.setIcon(0, self.style().standardIcon(QStyle.SP_DriveNetIcon))
                it.setData(0, Qt.UserRole, ("pacs", n["id"]))
                it.setToolTip(0, f"{n['ae_title']}@{n['host']}:{n['port']}")
        if escolhido is not None:
            self.tree.setCurrentItem(escolhido)
        self._fit_height()
        if hasattr(self, "cabecalho"):
            self._texto_do_cabecalho()

    def _bancos(self) -> None:
        """0.99.27: com várias pessoas, o banco do computador se mostra por partes — o compartilhado,
        o meu, o compartilhado comigo e, para o administrador, o banco pessoal de cada um."""
        from ipe.auth import visibilidade as V
        from ipe.db import banco as B
        v = V.visao_atual()
        if v is None or self.repo is None:
            return
        g = QTreeWidgetItem(self.tree, ["Banco"])
        g.setFlags(Qt.ItemIsEnabled)
        g.setForeground(0, Qt.gray)
        itens = list(B.BANCOS.items())
        if v.admin:
            try:
                donos = self.repo.donos_de_exames()
            except Exception:  # noqa: BLE001
                donos = {}
            itens += [(f"usuario:{d}", f"Banco de {d} ({n})") for d, n in sorted(donos.items())
                      if d.lower() != v.usuario.lower()]
        for chave, nome in itens:
            it = QTreeWidgetItem(self.tree, [nome])
            it.setData(0, Qt.UserRole, ("banco", chave))
            it.setIcon(0, self.style().standardIcon(QStyle.SP_DirHomeIcon if chave == "meu" else QStyle.SP_DirIcon))
            it.setToolTip(0, B.AVISO_LOCAL if chave in ("meu", "comigo") else
                          ("Abrir exame daqui fica no registro de acesso." if chave.startswith("usuario:") else ""))
            if chave == self.banco:
                f = it.font(0)
                f.setItalic(True)
                it.setFont(0, f)

    def _fit_height(self) -> None:
        """O painel ocupa só o que precisa (o resto da coluna fica para as listas de casos)."""
        linhas = self.tree.topLevelItemCount()
        alt = self.tree.sizeHintForRow(0) if linhas else 18
        self.tree.setMaximumHeight(min(max(3, linhas) * max(16, alt) + 10, 260))

    def _nodes(self) -> list[dict]:
        try:
            return [n for n in (self.repo.nodes() if self.repo else []) if n.get("use_query")]
        except Exception:  # noqa: BLE001
            return []

    def set_repo(self, repo) -> None:
        self.repo = repo
        self.rebuild()

    # ------------------------------------------------------------------ ações
    def _selected(self) -> tuple[str, object] | None:
        it = self.tree.currentItem()
        return None if it is None else it.data(0, Qt.UserRole)

    def _clicked(self, item, _col) -> None:
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind, ident = data
        if kind == "pacs":
            self.pacs_chosen.emit(ident)
            return
        if kind == "banco":
            self.banco = str(ident)
            self.banco_chosen.emit(self.banco)
            self.rebuild()
            return
        loc = L.find(self.settings, self.paths, str(ident))
        if loc is None:
            return
        if not loc.online():
            QMessageBox.information(self, "Local fora do ar",
                                    f"A pasta não está acessível agora:\n{loc.path}\n\n"
                                    "Conecte o disco (ou a rede) e clique de novo.")
            self.rebuild()
            return
        if str(ident) != L.current_id(self.settings):
            self.location_chosen.emit(str(ident))

    def _menu(self, pos) -> None:
        it = self.tree.itemAt(pos)
        if it is None or not it.data(0, Qt.UserRole):
            m = QMenu(self)
            m.addAction("Acrescentar local…").triggered.connect(self.add_requested.emit)
            m.exec(self.tree.viewport().mapToGlobal(pos))
            return
        kind, ident = it.data(0, Qt.UserRole)
        if kind == "pacs":
            m = QMenu(self)
            m.addAction("Buscar neste nó").triggered.connect(lambda: self.pacs_chosen.emit(ident))
            m.exec(self.tree.viewport().mapToGlobal(pos))
            return
        if kind == "banco":
            m = self.menu_de_banco(str(ident))
            m.exec(self.tree.viewport().mapToGlobal(pos))
            return
        loc = L.find(self.settings, self.paths, str(ident))
        if loc is None:
            return
        m = QMenu(self)
        m.addAction("Usar este local").triggered.connect(lambda: self._clicked(it, 0))
        if loc.is_central:
            m.exec(self.tree.viewport().mapToGlobal(pos))
            return
        m.addAction("Abrir a pasta").triggered.connect(lambda: self._open_folder(loc))
        if self._cliente():
            a = m.addAction("Enviar este banco ao servidor central…")
            a.setToolTip("Leva os exames deste local (com laudos, medidas e anotações) para o servidor do grupo. "
                         "Nada é apagado daqui.")
            a.triggered.connect(lambda: self.enviar_ao_servidor_requested.emit(loc.id))
        m.addSeparator()
        if not loc.is_default:
            m.addAction("Renomear…").triggered.connect(lambda: self._rename(loc))
            m.addAction("Procurar exames novos nesta pasta…").triggered.connect(
                lambda: self.rescan_requested.emit(loc.id))
            m.addSeparator()
            m.addAction("Tirar da lista (não apaga nada)").triggered.connect(lambda: self._remove(loc))
        else:
            m.addAction("Mudar a pasta deste banco…").triggered.connect(
                self.move_default_requested.emit)
        m.exec(self.tree.viewport().mapToGlobal(pos))

    def menu_de_banco(self, chave: str) -> QMenu:
        """Botão direito num banco: para onde vão os exames que eu trago; e, para o administrador, passar o
        banco pessoal de alguém (que saiu do serviço) para outro usuário ou para o compartilhado."""
        from ipe.auth import visibilidade as V
        from ipe.db import banco as B
        m = QMenu(self)
        m.addAction("Mostrar este banco").triggered.connect(lambda: self.banco_chosen.emit(chave))
        novos = m.addMenu("Exames que eu importo ou baixo vão para")
        atual = str(self.settings.get(B.CHAVE_NOVOS, "compartilhado") or "compartilhado") if self.settings else ""
        opcoes = [("compartilhado", "o compartilhado"), ("meu", "o meu banco")]
        if self._cliente():                   # 0.99.28: o banco pessoal pode ficar no servidor ou aqui
            opcoes = [("compartilhado", "o compartilhado (no servidor)"), ("meu", "o meu banco no servidor"),
                      ("computador", "o meu banco neste computador")]
        elif atual == "computador":
            atual = "meu"
        for valor, nome in opcoes:
            a = novos.addAction(nome, lambda val=valor: self._novos(val))
            a.setCheckable(True)
            a.setChecked(atual == valor)
        v = V.visao_atual()
        if chave.startswith("usuario:") and v is not None and v.admin:
            de = chave.split(":", 1)[1]
            sub = m.addMenu(f"Passar o banco de {de} para")
            sub.addAction("o compartilhado", lambda: self.transferir(de, ""))
            for u in (self.repo.users() if self.repo else []):
                if u["active"] and u["username"].lower() != de.lower():
                    sub.addAction(u["username"], lambda n=u["username"]: self.transferir(de, n))
        return m

    def _cliente(self) -> bool:
        return self.settings is not None and str(self.settings.get("central.mode", "local") or "") == "client"

    def _novos(self, valor: str) -> None:
        from ipe.db import banco as B
        if self.settings is not None:
            self.settings.set(B.CHAVE_NOVOS, valor)
            self.settings.save()

    def transferir(self, de: str, para: str) -> int:
        from ipe.auth import session as S
        n = self.repo.transferir_banco(de, para)
        try:
            self.repo.audit("transferiu_banco", f"{n} exame(s) do banco de {de} para "
                            + (f"o banco de {para}" if para else "o compartilhado"), user=S.get().username)
        except Exception:  # noqa: BLE001
            pass
        self.banco = "visivel"
        self.banco_chosen.emit(self.banco)
        self.rebuild()
        return n

    def _open_folder(self, loc) -> None:
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(loc.path)))

    def _rename(self, loc) -> None:
        name, ok = QInputDialog.getText(self, "Renomear o local", "Nome:", text=loc.name)
        if ok and name.strip():
            L.rename(self.settings, loc.id, name.strip())
            self.rebuild()

    def _remove(self, loc) -> None:
        r = QMessageBox.question(
            self, "Tirar da lista",
            f"Tirar “{loc.name}” da lista de locais?\n\n"
            f"Os exames e o índice continuam na pasta:\n{loc.path}\n"
            "Nada é apagado; para usar de novo, basta acrescentar a pasta outra vez.")
        if r == QMessageBox.Yes:
            trocar = L.current_id(self.settings) == loc.id
            L.remove(self.settings, loc.id)
            self.rebuild()
            if trocar:
                self.location_chosen.emit(L.DEFAULT_ID)


def choose_folder(parent, settings, titulo: str = "") -> Path | None:
    """Pergunta a pasta do local novo (HD externo, pasta de rede, outra pasta do PC)."""
    start = settings.get("locations_last_dir", "") or str(Path.home())
    d = QFileDialog.getExistingDirectory(
        parent, titulo or "Escolha a pasta do local (HD externo, rede, pasta do PC)", start)
    if not d:
        return None
    settings.set("locations_last_dir", str(Path(d).parent))
    return Path(d)
