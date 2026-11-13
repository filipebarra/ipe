"""Configurações ▸ Banco de dados ▸ Servidor de banco de dados (PostgreSQL) — 0.100.34.

Escolhe onde fica o banco principal deste computador: o PostgreSQL que vem com o Ipê (o padrão e, desde a 0.100.36,
o único tipo de banco, sem instalar nada) ou um servidor PostgreSQL próprio. Testa a conexão e copia o banco em uso
para o outro. A troca vale ao abrir o Ipê de novo.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QProgressDialog, QPushButton, QRadioButton, QSpinBox,
                               QVBoxLayout)

from ipe.core import banco_config as BC


class BancoDialog(QDialog):
    def __init__(self, parent, paths, db=None):
        super().__init__(parent)
        self.paths, self.db = paths, db
        self.setWindowTitle("Servidor de banco de dados")
        self.resize(560, 0)
        cfg = BC.ler()
        lay = QVBoxLayout(self)
        agora = db.descricao() if db is not None else str(paths.database)
        topo = QLabel(f"Em uso agora: <b>{agora}</b>")
        topo.setWordWrap(True)
        lay.addWidget(topo)
        import os
        if os.environ.get("IPE_DATABASE_URL"):
            v = QLabel("A variável IPE_DATABASE_URL está definida neste computador e passa na frente do que for "
                       "escolhido aqui.")
            v.setWordWrap(True)
            v.setStyleSheet("color: #d9a400;")
            lay.addWidget(v)
        self.r_emb = QRadioButton("PostgreSQL que vem com o Ipê, neste computador — o padrão, sem instalar nada")
        self.r_pg = QRadioButton("Servidor PostgreSQL próprio (outro computador ou nuvem)")
        from ipe.core import pg_embutido as PE
        if not PE.disponivel():
            self.r_emb.setEnabled(False)
            self.r_emb.setToolTip("Este pacote do Ipê não traz o PostgreSQL embutido.")
        (self.r_pg if BC.proprio(cfg) else self.r_emb).setChecked(True)
        lay.addWidget(self.r_emb)
        lay.addWidget(self.r_pg)
        self.grupo = QGroupBox("PostgreSQL")
        f = QFormLayout(self.grupo)
        self.host = QLineEdit(cfg.get("host") or "localhost")
        self.porta = QSpinBox()
        self.porta.setRange(1, 65535)
        self.porta.setValue(int(cfg.get("porta") or 5432))
        self.banco = QLineEdit(cfg.get("banco") or "ipe")
        self.usuario = QLineEdit(cfg.get("usuario") or "ipe")
        self.senha = QLineEdit()
        self.senha.setEchoMode(QLineEdit.Password)
        self.senha.setPlaceholderText("(a gravada)" if cfg.get("senha") else "")
        self.ssl = QComboBox()
        for v, t in (("prefer", "Usar se o servidor oferecer"), ("require", "Exigir"),
                     ("verify-full", "Exigir e conferir o certificado"), ("disable", "Não usar")):
            self.ssl.addItem(t, v)
        i = self.ssl.findData(cfg.get("ssl") or "prefer")
        self.ssl.setCurrentIndex(max(0, i))
        f.addRow("Servidor:", self.host)
        f.addRow("Porta:", self.porta)
        f.addRow("Banco:", self.banco)
        f.addRow("Usuário:", self.usuario)
        f.addRow("Senha:", self.senha)
        f.addRow("Conexão cifrada (SSL):", self.ssl)
        lay.addWidget(self.grupo)
        linha = QHBoxLayout()
        self.b_testar = QPushButton("Testar a conexão")
        self.b_testar.clicked.connect(self.testar)
        self.b_copiar = QPushButton("Copiar o banco deste computador para lá…")
        self.b_copiar.clicked.connect(self.copiar)
        linha.addWidget(self.b_testar)
        linha.addWidget(self.b_copiar)
        linha.addStretch(1)
        lay.addLayout(linha)
        self.estado = QLabel("")
        self.estado.setWordWrap(True)
        lay.addWidget(self.estado)
        nota = QLabel("As imagens continuam na pasta de dados (Storage); só as informações do banco vão para o "
                      "PostgreSQL. A troca vale ao abrir o Ipê de novo. A senha fica cifrada neste computador.")
        nota.setWordWrap(True)
        nota.setStyleSheet("color: gray;")
        lay.addWidget(nota)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.aceitar)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        for r in (self.r_emb, self.r_pg):
            r.toggled.connect(self._ligar)
        self._ligar()
        self._cfg_gravada = cfg

    def _ligar(self) -> None:
        self.grupo.setEnabled(self.r_pg.isChecked())
        self.b_copiar.setText("Copiar o banco deste computador para o PostgreSQL do Ipê…" if self.r_emb.isChecked()
                              else "Copiar o banco deste computador para lá…")
        self.estado.setText("")

    def _mudou(self) -> bool:
        return self.r_pg.isChecked() != BC.proprio(self._cfg_gravada)

    def cfg(self) -> dict:
        if self.r_emb.isChecked():
            return {"tipo": "embutido"}
        return {"tipo": "postgresql", "host": self.host.text().strip(), "porta": self.porta.value(),
                "banco": self.banco.text().strip(), "usuario": self.usuario.text().strip(),
                "ssl": self.ssl.currentData()}

    def _senha(self) -> str:
        if self.senha.text():
            return self.senha.text()
        from ipe.core import segredos as SG
        return SG.abrir_ou_vazio(self._cfg_gravada.get("senha") or "")

    def url(self) -> str:
        if self.r_emb.isChecked():
            from PySide6.QtCore import Qt
            from PySide6.QtWidgets import QApplication
            QApplication.setOverrideCursor(Qt.WaitCursor)     # a primeira vez cria o banco (alguns segundos)
            try:
                return BC.url_embutido(self.paths.data / "postgres")
            finally:
                QApplication.restoreOverrideCursor()
        return BC.url(self.cfg(), self._senha())

    def testar(self) -> BC.Teste:
        try:
            endereco = self.url()
        except Exception as e:  # noqa: BLE001 - o embutido não ligou
            self.estado.setText(f"Não conectou: {e}")
            self.estado.setStyleSheet("color: #d04040;")
            return BC.Teste(False, erro=str(e))
        t = BC.testar(endereco)
        if t.ok:
            if t.vazio and not t.tabelas:
                self.estado.setText(f"Conectou: PostgreSQL {t.versao}. Banco vazio.")
            elif t.vazio:
                self.estado.setText(f"Conectou: PostgreSQL {t.versao}. Banco vazio (já com as tabelas do Ipê).")
            else:
                self.estado.setText(f"Conectou: PostgreSQL {t.versao}. O banco já tem exames.")
            self.estado.setStyleSheet("color: #3a9d3a;")
        else:
            self.estado.setText(f"Não conectou: {t.erro}")
            self.estado.setStyleSheet("color: #d04040;")
        return t

    def _origem(self):
        if self.db is not None and getattr(self.db, "url", ""):
            return self.db.url
        return BC.origem_atual(self.paths.database)

    def copiar(self) -> bool:
        t = self.testar()
        if not t.ok:
            return False
        origem = self._origem()
        url = self.url()
        if isinstance(origem, str) and BC.mesmo_banco(origem, url):
            QMessageBox.information(self, "Copiar o banco", "Este já é o banco em uso: não há o que copiar.")
            return False
        if not t.vazio:
            QMessageBox.warning(self, "Copiar o banco", "O banco de destino já tem exames. Use um banco vazio.")
            return False
        from ipe.db.session import mascarar
        de = mascarar(origem) if isinstance(origem, str) else str(origem)
        if QMessageBox.question(self, "Copiar o banco",
                                f"Copiar todas as informações de\n{de}\npara o banco escolhido?\n\n"
                                "Feche o Ipê nas outras estações antes: o que entrar durante a cópia não vai junto."
                                ) != QMessageBox.Yes:
            return False
        estado = {"tabela": "", "feitas": 0, "total": 0, "fim": False, "erro": "", "res": {}}

        def andou(tabela, feitas, total):
            estado.update(tabela=tabela, feitas=feitas, total=total)

        def rodar():
            try:
                estado["res"] = BC.copiar(origem, url, andou)
            except Exception as e:  # noqa: BLE001
                estado["erro"] = str(e)
            estado["fim"] = True

        prog = QProgressDialog("Copiando…", None, 0, 0, self)
        prog.setWindowTitle("Copiar o banco")
        prog.setMinimumDuration(0)
        threading.Thread(target=rodar, daemon=True).start()
        laco = QTimer(self)

        def olhar():
            prog.setLabelText(f"{estado['tabela']}: {estado['feitas']} de {estado['total']}")
            if estado["fim"]:
                laco.stop()
                prog.close()
                if estado["erro"]:
                    QMessageBox.warning(self, "Copiar o banco", f"A cópia não foi feita: {estado['erro']}")
                else:
                    n = sum(estado["res"].values())
                    QMessageBox.information(self, "Copiar o banco",
                                            f"Copiadas {n} linhas em {len(estado['res'])} tabelas, com a contagem "
                                            "conferida. Clique em OK nesta janela para passar a usar este banco.")
                self.testar()
        laco.timeout.connect(olhar)
        laco.start(200)
        self._laco = laco
        return True

    def aceitar(self) -> None:
        t = self.testar()
        if not t.ok:
            if QMessageBox.question(self, "Servidor de banco de dados",
                                    "Não conectou. Gravar assim mesmo? (O Ipê não abre o banco até o servidor "
                                    "responder.)") != QMessageBox.Yes:
                return
        elif t.vazio and self._mudou():
            if QMessageBox.question(self, "Servidor de banco de dados",
                                    "O banco escolhido está vazio: os exames deste computador não vão aparecer lá até "
                                    "serem copiados (botão Copiar). Gravar assim mesmo?") != QMessageBox.Yes:
                return
        BC.gravar(self.cfg() if self.r_emb.isChecked() else dict(self.cfg(), senha=self._senha()))
        QMessageBox.information(self, "Servidor de banco de dados",
                                "Gravado. Feche e abra o Ipê para passar a usar o banco escolhido.")
        self.accept()
