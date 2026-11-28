"""0.100.117: Configurações ▸ Banco de dados ▸ Conferir e reconstruir o banco… (o *Rebuild Database* do OsiriX).

Conferir (só relatório) → reconstrução parcial (a partir do relatório) ou completa (relê todos os arquivos, com cópia
do índice antes; retoma). A lógica está em `ipe.db.reconstruir`.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QProgressBar,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ipe.core.i18n import tr
from ipe.db import reconstruir as R


class _Sinais(QObject):
    andamento = Signal(int, int, str)
    fim = Signal(str, object, str)          # etapa, resultado, erro


class ReconstruirDialog(QDialog):
    def __init__(self, repo, db, paths, settings, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
                            | Qt.WindowCloseButtonHint)
        self.setWindowTitle(tr("Conferir e reconstruir o banco"))
        self.repo, self.db, self.paths, self.settings = repo, db, paths, settings
        self.rel: R.Relatorio | None = None
        self.parar = threading.Event()
        self.linha: threading.Thread | None = None
        self.sinais = _Sinais()
        self.sinais.andamento.connect(self._andamento)
        self.sinais.fim.connect(self._fim)
        lay = QVBoxLayout(self)
        topo = QLabel(tr(
            "Confere o índice do banco contra os arquivos e conserta o que estiver errado. Comentários, listas, "
            "medidas, imagens-chave, laudos e resultados de IA nunca são apagados: eles se ligam ao exame pelo UID "
            "e voltam com ele. Comece por <b>Conferir</b> — não muda nada."))
        topo.setWordWrap(True)
        lay.addWidget(topo)
        h = QHBoxLayout()
        self.b_conferir = QPushButton(tr("Conferir"))
        self.b_conferir.clicked.connect(self.conferir)
        self.b_salvar = QPushButton(tr("Salvar o relatório…"))
        self.b_salvar.clicked.connect(self.salvar)
        self.b_salvar.setEnabled(False)
        h.addWidget(self.b_conferir)
        h.addWidget(self.b_salvar)
        h.addStretch(1)
        lay.addLayout(h)
        self.tabela = QTableWidget(0, 2)
        self.tabela.setHorizontalHeaderLabels([tr("O que"), tr("Quantos")])
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        from ipe.ui.tabelas import colunas_ajustaveis
        colunas_ajustaveis(self.tabela)
        self.tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        lay.addWidget(self.tabela, 1)
        g = QGroupBox(tr("Reconstrução parcial (rápida)"))
        gl = QVBoxLayout(g)
        info = QLabel(tr("Indexa os arquivos do Storage que estão fora do banco, tira do banco as imagens do Storage "
                         "cujo arquivo sumiu, tira os exames e séries que ficaram vazios e os pacientes sem exame, "
                         "refaz as miniaturas e apaga as pastas vazias."))
        info.setWordWrap(True)
        gl.addWidget(info)
        self.k_ref = QCheckBox(tr("Também tirar as imagens referenciadas (fora do Storage) que não estão no lugar"))
        self.k_ref.setToolTip(tr("Desmarcado (o padrão), ficam: um disco externo ou pendrive desligado volta a "
                                 "funcionar quando for ligado de novo."))
        gl.addWidget(self.k_ref)
        self.b_parcial = QPushButton(tr("Fazer a reconstrução parcial"))
        self.b_parcial.clicked.connect(self.parcial)
        self.b_parcial.setEnabled(False)
        gl.addWidget(self.b_parcial, 0, Qt.AlignLeft)
        lay.addWidget(g)
        g2 = QGroupBox(tr("Reconstrução completa (demorada)"))
        gl2 = QVBoxLayout(g2)
        info2 = QLabel(tr("Relê o cabeçalho de todos os arquivos e atualiza o índice (paciente, exame, séries, "
                          "imagens). Antes, grava uma cópia do índice em {}. Pode parar e continuar depois.")
                       .format(str(self.pasta_copias())))
        info2.setWordWrap(True)
        gl2.addWidget(info2)
        h2 = QHBoxLayout()
        self.b_completa = QPushButton(tr("Fazer a reconstrução completa…"))
        self.b_completa.clicked.connect(lambda: self.completa(False))
        self.b_continuar = QPushButton(tr("Continuar de onde parou"))
        self.b_continuar.clicked.connect(lambda: self.completa(True))
        h2.addWidget(self.b_completa)
        h2.addWidget(self.b_continuar)
        h2.addStretch(1)
        gl2.addLayout(h2)
        lay.addWidget(g2)
        self.barra = QProgressBar()
        self.barra.setVisible(False)
        self.estado = QLabel("")
        self.estado.setWordWrap(True)
        h3 = QHBoxLayout()
        h3.addWidget(self.barra, 1)
        self.b_parar = QPushButton(tr("Parar"))
        self.b_parar.clicked.connect(self.parar.set)
        self.b_parar.setEnabled(False)
        h3.addWidget(self.b_parar)
        lay.addLayout(h3)
        lay.addWidget(self.estado)
        self.resize(720, 640)
        self._botoes()

    # ------------------------------------------------------------------ apoio
    def _atuais(self):
        """(repo, banco, pasta de arquivos) do local em uso agora (0.100.122: com o HD externo, não os do computador)."""
        j = self.parent()
        return (getattr(j, "repo", self.repo), getattr(j, "db", self.db),
                getattr(j, "storage", None) or self.paths.storage)

    def pasta_copias(self):
        return self.paths.data / "Backups"

    def ocupado(self) -> bool:
        return self.linha is not None and self.linha.is_alive()

    def _botoes(self) -> None:
        livre = not self.ocupado()
        self.b_conferir.setEnabled(livre)
        self.b_parcial.setEnabled(livre and self.rel is not None and self.rel.problemas > 0)
        self.b_completa.setEnabled(livre)
        self.b_continuar.setVisible(bool(R.em_andamento(self.settings)))
        self.b_continuar.setEnabled(livre)
        self.b_parar.setEnabled(not livre)
        self.b_salvar.setEnabled(self.rel is not None)

    def _rodar(self, etapa: str, fn) -> None:
        self.parar.clear()

        def trabalho():
            try:
                res = fn(lambda a, b, m: self.sinais.andamento.emit(int(a), int(b), m))
                self.sinais.fim.emit(etapa, res, "")
            except R.Cancelado:
                self.sinais.fim.emit(etapa, None, tr("parado"))
            except Exception as e:  # noqa: BLE001
                import logging
                logging.getLogger(__name__).exception("reconstrução do banco: %s", etapa)
                self.sinais.fim.emit(etapa, None, str(e))
        self.barra.setVisible(True)
        self.barra.setRange(0, 0)
        self.linha = threading.Thread(target=trabalho, name=f"banco-{etapa}", daemon=True)
        self.linha.start()
        self._botoes()

    def _andamento(self, feito: int, total: int, msg: str) -> None:
        if total > 0:
            self.barra.setRange(0, total)
            self.barra.setValue(min(feito, total))
            self.estado.setText(tr(msg) + " %d/%d" % (feito, total))
        else:
            self.barra.setRange(0, 0)
            self.estado.setText(tr(msg))

    def _mostrar(self, rel: R.Relatorio) -> None:
        linhas = rel.linhas()
        self.tabela.setRowCount(len(linhas))
        for i, (t, n) in enumerate(linhas):
            self.tabela.setItem(i, 0, QTableWidgetItem(tr(t)))
            it = QTableWidgetItem(str(n))
            it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.tabela.setItem(i, 1, it)

    def _fim(self, etapa: str, res, erro: str) -> None:
        self.linha = None
        self.barra.setVisible(False)
        if erro:
            self.estado.setText(tr("Não terminou ({}): {}").format(tr(etapa), erro))
        elif etapa == "conferir":
            self.rel = res
            self._mostrar(res)
            self.estado.setText(tr("Conferido em {:.0f} s: {} item(ns) para consertar.").format(
                res.segundos, res.problemas) if res.problemas else tr("Conferido: o banco está em ordem."))
        elif etapa == "parcial":
            self.estado.setText(tr("Reconstrução parcial: {indexadas} imagem(ns) indexada(s), {removidas} tirada(s) "
                                   "do banco, {series} série(s) e {exames} exame(s) vazios, {pacientes} paciente(s) "
                                   "sem exame, {miniaturas} miniatura(s), {pastas} pasta(s) vazia(s).").format(**res))
            self.rel = None
            self.tabela.setRowCount(0)
        elif etapa == "completa":
            self.estado.setText(tr("Reconstrução completa: {exames} exame(s), {series} série(s), {imagens} imagem(ns) "
                                   "relidas; {ilegiveis} sem arquivo ou ilegível(is) (a conferência cuida); "
                                   "{pacientes_trocados} exame(s) com o paciente corrigido. Cópia do índice: {copia}")
                                .format(**res))
        self._botoes()
        try:
            self.parent().browser.refresh()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ ações
    def conferir(self) -> None:
        self._rodar("conferir", lambda p: R.conferir(self._atuais()[1], self._atuais()[2], p, self.parar))

    def parcial(self) -> None:
        rel = self.rel
        if rel is None:
            return
        if QMessageBox.question(self, self.windowTitle(), tr(
                "Fazer a reconstrução parcial agora? O que for tirado do banco é só o índice: os arquivos que "
                "existem não são apagados.")) != QMessageBox.Yes:
            return
        ref = self.k_ref.isChecked()
        self._rodar("parcial", lambda p: R.parcial(*self._atuais(), rel, ref, p, self.parar))

    def completa(self, continuar: bool) -> None:
        if not continuar and QMessageBox.question(self, self.windowTitle(), tr(
                "A reconstrução completa relê todos os arquivos e pode levar muito tempo num banco grande. Antes, "
                "grava uma cópia do índice. Começar?")) != QMessageBox.Yes:
            return
        self._rodar("completa", lambda p: R.completa(*self._atuais(), self.pasta_copias(), p,
                                                      self.parar, settings=self.settings, recomecar=not continuar))

    def salvar(self) -> None:
        if self.rel is None:
            return
        caminho, _f = QFileDialog.getSaveFileName(self, tr("Salvar o relatório"), "conferencia-do-banco.txt",
                                                  "Texto (*.txt)")
        if caminho:
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(self.rel.texto())

    def closeEvent(self, e) -> None:
        if self.ocupado():
            if QMessageBox.question(self, self.windowTitle(), tr("A tarefa ainda está rodando. Parar e fechar? A "
                                                                 "reconstrução completa continua depois de onde "
                                                                 "parou.")) != QMessageBox.Yes:
                e.ignore()
                return
            self.parar.set()
        super().closeEvent(e)
