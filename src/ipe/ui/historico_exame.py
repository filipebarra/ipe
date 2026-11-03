"""Histórico do exame (0.99.31, onda A6 — ideia da Eden).

Botão direito no exame ▸ "Histórico do exame…": quem fez o quê **neste** exame — abriu, baixou,
exportou, enviou, imprimiu, mudou de banco, apagou imagem, assumiu o laudo — e quando os laudos foram
criados e assinados. O registro de acesso de todo o programa continua em Usuários (administrador);
aqui é o pedaço dele que é deste exame, para quem pode ver o exame.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

EXTRA = {"laudo_criado": "Laudo criado", "laudo_assinado": "Laudo assinado", "apagou_imagem": "Apagou imagem",
         "assumiu_laudo": "Assumiu o laudo", "apagar série": "Apagou série"}


def rotulo(acao: str) -> str:
    from ipe.ui.users_dialog import ACTIONS
    return EXTRA.get(acao) or ACTIONS.get(acao) or acao


class HistoricoDialog(QDialog):
    def __init__(self, repo, study_uid: str, titulo: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Histórico do exame" + (f" — {titulo}" if titulo else ""))
        self.resize(820, 460)
        lay = QVBoxLayout(self)
        try:
            self.linhas = repo.historico_do_exame(study_uid)
        except Exception as e:  # noqa: BLE001
            self.linhas = []
            lay.addWidget(QLabel(f"Não foi possível ler o histórico: {e}"))
        self.tabela = QTableWidget(len(self.linhas), 4)
        self.tabela.setHorizontalHeaderLabels(["Quando", "Quem", "O quê", "Detalhe"])
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.horizontalHeader().setStretchLastSection(True)
        for r, x in enumerate(self.linhas):
            quando = x["at"].strftime("%d/%m/%Y %H:%M") if isinstance(x.get("at"), datetime) else str(x.get("at", ""))[:16]
            for c, v in enumerate((quando, x.get("user", ""), rotulo(x.get("action", "")), x.get("detail", ""))):
                self.tabela.setItem(r, c, QTableWidgetItem(str(v or "")))
        from ipe.ui.tabelas import colunas_ajustaveis
        colunas_ajustaveis(self.tabela)
        self.tabela.resizeColumnsToContents()
        lay.addWidget(self.tabela, 1)
        if not self.linhas:
            lay.addWidget(QLabel("Nada registrado para este exame ainda."))
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
