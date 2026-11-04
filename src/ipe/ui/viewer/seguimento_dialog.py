"""Assistente do seguimento (0.99.59, item 7 — AW O3): as lesões medidas antes e ainda sem medida neste exame,
uma a uma — repetir a medida no lugar estimado, pequena demais (5 mm), ausente (0), estável ou progressão."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout)

from ipe.imaging import seguimento as SG


def _data(d: str) -> str:
    return f"{d[6:8]}/{d[4:6]}/{d[:4]}" if d and len(d) == 8 else (d or "")


class SeguimentoDialog(QDialog):
    def __init__(self, tab, study_uid: str):
        super().__init__(tab)
        self.tab, self.study_uid = tab, study_uid
        self.setWindowTitle("Seguimento — lesões sem medida neste exame")
        self.setWindowFlag(Qt.Tool, True)
        self.resize(520, 420)
        self.itens: list[dict] = []
        self.datas: dict[str, str] = {}
        self.lista = QListWidget()
        self.lista.currentRowChanged.connect(self._mostrar)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.botoes: dict[str, QPushButton] = {}
        h1, h2 = QHBoxLayout(), QHBoxLayout()
        for chave, rot, dica, linha in (
                ("repetir", "Repetir a medida", "Vai ao lugar estimado, com o contorno anterior em sombra e a mesma "
                                                "ferramenta; a próxima medida liga à lesão", h1),
                ("pequena", "Pequena demais (5 mm)", "RECIST 1.1: entra na soma com 5 mm", h1),
                ("absent", "Ausente (0)", "A lesão desapareceu", h1),
                ("present", "Presente / estável", "Não alvo: presente, sem progressão", h2),
                ("progression", "Progressão inequívoca", "Não alvo: progressão inequívoca", h2),
                ("pular", "Pular", "Deixa para depois", h2)):
            b = QPushButton(rot)
            b.setToolTip(dica)
            b.clicked.connect(lambda _=False, k=chave: self.acao(k))
            linha.addWidget(b)
            self.botoes[chave] = b
        self.vazio = QLabel()
        self.vazio.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addWidget(self.lista, 1)
        lay.addWidget(self.info)
        lay.addLayout(h1)
        lay.addLayout(h2)
        lay.addWidget(self.vazio)
        self.recarregar()

    def recarregar(self) -> None:
        _pid, lesoes, anns, datas = self.tab._dados_do_seguimento(self.study_uid)
        self.datas = datas
        self.itens = SG.pendentes(lesoes, anns, datas, self.study_uid)
        self.lista.clear()
        for it in self.itens:
            le, m = it["lesao"], it["medida"]
            kind = {"target": "alvo", "nontarget": "não alvo", "new": "nova"}.get(le.get("kind", "target"), "")
            valor = f", {m['mm']:.1f} mm" if m.get("mm") else ""
            self.lista.addItem(QListWidgetItem(f"{le['name']} ({kind}) — medida em {_data(datas.get(m['study_uid'], ''))}"
                                               f"{valor}"))
        self.vazio.setText("" if self.itens else "Todas as lesões já têm medida ou estado neste exame.")
        for b in self.botoes.values():
            b.setEnabled(bool(self.itens))
        if self.itens:
            self.lista.setCurrentRow(0)

    def atual(self) -> dict | None:
        r = self.lista.currentRow()
        return self.itens[r] if 0 <= r < len(self.itens) else None

    def _mostrar(self, _r: int) -> None:
        it = self.atual()
        if it is None:
            self.info.setText("")
            return
        le = it["lesao"]
        alvo = le.get("kind", "target") == "target"
        self.botoes["pequena"].setEnabled(alvo)
        self.botoes["present"].setEnabled(not alvo)
        self.botoes["progression"].setEnabled(not alvo)
        tem_pos = bool(it["medida"].get("centro"))
        self.info.setText(f"<b>{le['name']}</b> — {le.get('location', '')}"
                          + ("" if tem_pos else "<br><small>A medida anterior não tem posição guardada (feita antes da "
                                                "0.99.59): o Repetir abre a série equivalente, sem o lugar.</small>"))

    def acao(self, chave: str) -> None:
        it = self.atual()
        if it is None:
            return
        le = it["lesao"]
        if chave == "repetir":
            self.tab.repetir_medida(le, it["medida"], self.study_uid)
            return
        if chave == "pular":
            r = self.lista.currentRow()
            self.lista.setCurrentRow(min(r + 1, self.lista.count() - 1))
            return
        data = dict(le.get("data") or {})
        st = dict(data.get("status") or {})
        st[self.study_uid] = chave
        data["status"] = st
        self.tab.repo.save_lesion({"id": le["id"], "data": data})
        self.tab.refresh_lesions()
        r = self.lista.currentRow()
        self.recarregar()
        if self.itens:
            self.lista.setCurrentRow(min(r, len(self.itens) - 1))
