"""Campo "Visível para" dos editores de configuração (0.99.26): Todos / Só eu / Escolher usuários…

Some sozinho no modo "só eu" (não há com quem compartilhar). Quem não tem a permissão de configurar
não pode criar item "de todos": o combo começa em "Só eu" e a opção "Todos" fica desligada.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QWidget,
)

from ipe.auth import visibilidade as V


class EscolherUsuarios(QDialog):
    def __init__(self, nomes: list[str], marcados: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compartilhar com")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Quem também vê este item:"))
        self.lista = QListWidget()
        low = {m.lower() for m in marcados}
        for n in nomes:
            it = QListWidgetItem(n)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if n.lower() in low else Qt.Unchecked)
            self.lista.addItem(it)
        lay.addWidget(self.lista)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def escolhidos(self) -> list[str]:
        return [self.lista.item(i).text() for i in range(self.lista.count())
                if self.lista.item(i).checkState() == Qt.Checked]


class VisivelPara(QWidget):
    """`item` é o dicionário (ou objeto) com `dono` e `visivel_para`; vazio = item novo."""

    def __init__(self, item=None, repo=None, settings=None, parent=None):
        super().__init__(parent)
        self.repo = repo
        self.visao = V.visao_atual()
        novo = not item or (not V._get(item, "dono") and not V._get(item, "id") and not V._get(item, "name"))
        base = V.padrao_novo(self.visao) if novo else {"dono": V._get(item, "dono") or "",
                                                       "visivel_para": V._get(item, "visivel_para") or ""}
        self.dono = str(base["dono"] or "")
        self.outros = V.lista(base["visivel_para"])
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.combo = QComboBox()
        self.combo.addItem("Todos (do serviço)", "todos")
        self.combo.addItem("Só eu", "eu")
        self.combo.addItem("Eu e usuários escolhidos…", "escolher")
        self.b = QPushButton("Escolher…")
        self.b.clicked.connect(self._escolher)
        self.l = QLabel()
        lay.addWidget(self.combo, 1)
        lay.addWidget(self.b)
        lay.addWidget(self.l, 1)
        from ipe.auth import session as S
        try:
            pode_todos = bool(S.get().can("configure"))
        except Exception:  # noqa: BLE001
            pode_todos = True
        self.combo.model().item(0).setEnabled(pode_todos or not self.dono)
        if not self.dono:
            self.combo.setCurrentIndex(0)
        else:
            self.combo.setCurrentIndex(2 if self.outros else 1)
        self.combo.currentIndexChanged.connect(self._mudou)
        self._mostrar()
        self.setVisible(V.modo_com_usuarios(settings) if settings is not None else True)

    def _nomes(self) -> list[str]:
        if self.repo is None:
            return []
        try:
            eu = (self.dono or (self.visao.usuario if self.visao else "")).lower()
            try:
                nomes = list(self.repo.nomes_de_usuarios())
            except Exception:  # noqa: BLE001
                nomes = [u["username"] for u in self.repo.users() if u["active"]]
            return [n for n in nomes if n.lower() != eu]
        except Exception:  # noqa: BLE001
            return []

    def _mudou(self) -> None:
        v = self.combo.currentData()
        if v == "todos":
            self.outros = []
        elif not self.dono:
            self.dono = self.visao.usuario if self.visao else ""
        if v == "eu":
            self.outros = []
        if v == "escolher" and not self.outros:
            self._escolher()
        self._mostrar()

    def _escolher(self) -> None:
        d = EscolherUsuarios(self._nomes(), self.outros, self)
        if d.exec():
            self.outros = d.escolhidos()
            if not self.dono:
                self.dono = self.visao.usuario if self.visao else ""
            self.combo.blockSignals(True)
            self.combo.setCurrentIndex(2 if self.outros else 1)
            self.combo.blockSignals(False)
        self._mostrar()

    def _mostrar(self) -> None:
        v = self.combo.currentData()
        self.b.setVisible(v == "escolher")
        alheio = self.dono and self.visao is not None and self.dono.lower() != self.visao.usuario.lower()
        txt = ", ".join(self.outros) if v == "escolher" else ""
        if alheio and v != "todos":
            txt = f"de {self.dono}" + (f"; também: {txt}" if txt else "")
        self.l.setText(txt)

    def valor(self) -> dict:
        """{'dono', 'visivel_para'} para gravar no item."""
        if self.combo.currentData() == "todos":
            return {"dono": "", "visivel_para": ""}
        dono = self.dono or (self.visao.usuario if self.visao else "")
        outros = self.outros if self.combo.currentData() == "escolher" else []
        return {"dono": dono, "visivel_para": ",".join(outros)}
