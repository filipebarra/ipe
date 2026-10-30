"""Relatório do acervo: o que está guardado, em que formato, e quanto a compressão renderia.

A tela não decide nada. Mostra o que existe, mede numa amostra do **seu** acervo e escreve ao
lado o que a medida significa — inclusive o que o programa ainda não consegue gravar.
"""

from __future__ import annotations

import csv
import threading

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QMessageBox, QProgressBar, QPushButton, QSizePolicy, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from ipe.core import acervo as A
from ipe.core import compress as K
from ipe.core.i18n import tr
from ipe.ui.tabelas import colunas_ajustaveis


def _item(texto: str, alinhar_direita: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem(texto)
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    if alinhar_direita:
        it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
    return it


def _ajusta_altura(t: QTableWidget, maximo: int = 9) -> None:
    """Tabela do tamanho do que tem dentro: sem faixa vazia embaixo nem linha cortada."""
    linhas = min(max(t.rowCount(), 1), maximo)
    altura = t.horizontalHeader().height() + 2 * t.frameWidth()
    for i in range(linhas):
        altura += t.rowHeight(i) if i < t.rowCount() else 24
    if t.rowCount() > maximo:
        altura += 12
    t.setFixedHeight(altura)


def _tabela(colunas: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(colunas))
    t.setHorizontalHeaderLabels(colunas)
    t.verticalHeader().setVisible(False)
    t.setSelectionBehavior(QTableWidget.SelectRows)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    cab = t.horizontalHeader()
    cab.setSectionResizeMode(QHeaderView.ResizeToContents)
    cab.setSectionResizeMode(0, QHeaderView.Stretch)
    return t
    colunas_ajustaveis(t)


class _Medidor(QThread):
    """Mede em segundo plano: a tela continua respondendo e dá para parar no meio."""
    andamento = Signal(int, int)
    pronto = Signal(object)

    def __init__(self, caminhos, parent=None) -> None:
        super().__init__(parent)
        self.caminhos = list(caminhos)
        self.stop = threading.Event()

    def run(self) -> None:  # noqa: D102
        try:
            medidas = A.medir(self.caminhos, stop=self.stop,
                              progresso=lambda i, n: self.andamento.emit(i, n))
        except Exception:  # noqa: BLE001
            medidas = []
        self.pronto.emit(medidas)


class _Comprimidor(QThread):
    """O lote roda fora da interface: dá para acompanhar e parar no meio."""
    andamento = Signal(int, int)
    pronto = Signal(object)

    def __init__(self, repo, politica, pular, parent=None) -> None:
        super().__init__(parent)
        self.repo, self.politica, self.pular = repo, politica, list(pular or [])
        self.stop = threading.Event()

    def run(self) -> None:  # noqa: D102
        try:
            b = K.run(self.repo, self.politica, limite=100000, stop=self.stop,
                      progresso=lambda i, n: self.andamento.emit(i, n),
                      pular_exames=self.pular)
        except Exception:  # noqa: BLE001
            b = K.Balanco()
        self.pronto.emit(b)


class AcervoDialog(QDialog):
    def __init__(self, repo, settings=None, em_uso=(), parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Relatório do acervo"))
        self.repo, self.settings = repo, settings
        self.em_uso = list(em_uso or [])      # exames abertos agora: não se mexe neles
        self.acervo = A.levantar(repo)
        self.medidas: list = []
        self._medidor: _Medidor | None = None
        self._comprimidor: _Comprimidor | None = None
        self.resize(940, 760)

        v = QVBoxLayout(self)
        self.resumo = QLabel()
        self.resumo.setWordWrap(True)
        v.addWidget(self.resumo)

        self.t_sintaxe = _tabela([tr("Formato guardado"), tr("Tipo"), tr("Arquivos"),
                                  tr("Tamanho"), tr("% do acervo"), tr("Bytes por pixel")])
        v.addWidget(self._caixa(tr("Por formato de gravação"), self.t_sintaxe))

        self.t_modalidade = _tabela([tr("Modalidade"), tr("Arquivos"), tr("Tamanho"),
                                     tr("% do acervo"), tr("Bytes por pixel")])
        v.addWidget(self._caixa(tr("Por modalidade"), self.t_modalidade))

        self.t_ganho = _tabela([tr("Compressão sem perda"), tr("Medido em"), tr("Taxa"),
                                tr("O acervo sem compressão passaria a"), tr("Economia")])
        caixa = self._caixa(tr("Quanto renderia, medido no seu acervo"), self.t_ganho)
        linha = QHBoxLayout()
        self.b_medir = QPushButton(tr("Medir numa amostra"))
        self.b_medir.clicked.connect(self.medir)
        self.barra = QProgressBar()
        self.barra.setVisible(False)
        linha.addWidget(self.b_medir)
        linha.addWidget(self.barra, 1)
        caixa.layout().addLayout(linha)
        self.nota = QLabel()
        self.nota.setWordWrap(True)
        caixa.layout().addWidget(self.nota)
        v.addWidget(caixa)

        if settings is not None:
            v.addWidget(self._caixa_compressao())
        v.addStretch(1)
        rodape = QHBoxLayout()
        b_csv = QPushButton(tr("Exportar CSV…"))
        b_csv.clicked.connect(self.exportar)
        b_fechar = QPushButton(tr("Fechar"))
        b_fechar.clicked.connect(self.reject)
        rodape.addWidget(b_csv)
        rodape.addStretch(1)
        rodape.addWidget(b_fechar)
        v.addLayout(rodape)

        self.preencher()

    # ------------------------------------------------------------------ compressão
    def _caixa_compressao(self) -> QGroupBox:
        pol = K.Politica.from_settings(self.settings)
        g = QGroupBox(tr("Compressão automática (sem perda)"))
        g.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        lay = QVBoxLayout(g)

        linha = QHBoxLayout()
        self.c_ligada = QCheckBox(tr("Comprimir sozinho os exames guardados há mais de"))
        self.c_ligada.setChecked(pol.ligada)
        self.s_dias = QSpinBox()
        self.s_dias.setRange(0, 3650)
        self.s_dias.setValue(pol.dias)
        self.cb_formato = QComboBox()
        for uid in K.SINTAXES:
            self.cb_formato.addItem(A.sintaxe(uid).nome, uid)
        self.cb_formato.setCurrentIndex(max(0, list(K.SINTAXES).index(pol.sintaxe)))
        self.c_protegidos = QCheckBox(tr("Não mexer em exame protegido"))
        self.c_protegidos.setChecked(pol.pular_protegidos)
        linha.addWidget(self.c_ligada)
        linha.addWidget(self.s_dias)
        linha.addWidget(QLabel(tr("dias, em")))
        linha.addWidget(self.cb_formato)
        linha.addWidget(self.c_protegidos)
        linha.addStretch(1)
        lay.addLayout(linha)
        for w, sinal in ((self.c_ligada, "toggled"), (self.s_dias, "valueChanged"),
                         (self.cb_formato, "currentIndexChanged"),
                         (self.c_protegidos, "toggled")):
            getattr(w, sinal).connect(self.salvar_politica)

        self.l_fila = QLabel()
        self.l_fila.setWordWrap(True)
        lay.addWidget(self.l_fila)

        acao = QHBoxLayout()
        self.b_comprimir = QPushButton(tr("Comprimir agora o que já passou do prazo"))
        self.b_comprimir.clicked.connect(self.comprimir)
        self.barra_c = QProgressBar()
        self.barra_c.setVisible(False)
        acao.addWidget(self.b_comprimir)
        acao.addWidget(self.barra_c, 1)
        lay.addLayout(acao)

        aviso = QLabel(tr("Sem perda: os pixels voltam idênticos. Antes de trocar, o programa lê de volta o arquivo novo e compara pixel a pixel com o original — se não bater, não troca nada. Exame aberto agora fica de fora."))
        aviso.setWordWrap(True)
        lay.addWidget(aviso)
        self.atualiza_fila()
        return g

    def politica(self) -> K.Politica:
        pol = K.Politica.from_settings(self.settings)
        pol.ligada = self.c_ligada.isChecked()
        pol.dias = int(self.s_dias.value())
        pol.sintaxe = self.cb_formato.currentData()
        pol.pular_protegidos = self.c_protegidos.isChecked()
        return pol

    def salvar_politica(self) -> None:
        self.politica().save(self.settings)
        self.atualiza_fila()

    def atualiza_fila(self) -> None:
        pol = self.politica()
        try:
            fila = K.elegiveis(self.repo, pol, limite=100000)
        except Exception:  # noqa: BLE001
            fila = []
        bytes_ = sum(int(a.get("bytes") or 0) for a in fila)
        self.b_comprimir.setEnabled(bool(fila) and self._comprimidor is None)
        if fila:
            self.l_fila.setText(tr("{} arquivo(s) já passaram do prazo, somando {}.").format(
                len(fila), A.tamanho(bytes_)))
        else:
            self.l_fila.setText(tr("Nenhum arquivo passou do prazo ainda."))

    def comprimir(self) -> None:
        if self._comprimidor is not None:
            self._comprimidor.stop.set()
            return
        pol = self.politica()
        fila = K.elegiveis(self.repo, pol, limite=100000)
        if not fila:
            return
        resp = QMessageBox.question(
            self, tr("Compressão automática (sem perda)"),
            tr("Comprimir {} arquivo(s) agora? Cada um é conferido pixel a pixel antes de substituir o original.").format(len(fila)),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if resp != QMessageBox.Yes:
            return
        self.barra_c.setVisible(True)
        self.barra_c.setRange(0, len(fila))
        self.b_comprimir.setText(tr("Parar"))
        self._comprimidor = _Comprimidor(self.repo, pol, self.em_uso, self)
        self._comprimidor.andamento.connect(lambda i, n: self.barra_c.setValue(i))
        self._comprimidor.pronto.connect(self.comprimido)
        self._comprimidor.start()

    def comprimido(self, balanco) -> None:
        self._comprimidor = None
        self.barra_c.setVisible(False)
        self.b_comprimir.setText(tr("Comprimir agora o que já passou do prazo"))
        self.acervo = A.levantar(self.repo)
        self.preencher()
        self.atualiza_fila()
        texto = K.resumo(balanco)
        if balanco.falhas:
            texto = tr("{} {} arquivo(s) não deram e continuam como estavam.").format(
                texto, len(balanco.falhas))
        QMessageBox.information(self, tr("Compressão automática (sem perda)"), texto)

    def _caixa(self, titulo: str, tabela: QTableWidget) -> QGroupBox:
        """A caixa acompanha a tabela: sobra vira espaço no fim da janela, não buraco no meio."""
        g = QGroupBox(titulo)
        g.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        lay = QVBoxLayout(g)
        lay.addWidget(tabela)
        return g

    # ------------------------------------------------------------------ conteúdo
    def preencher(self) -> None:
        acv = self.acervo
        total = acv.bytes or 1
        sem = acv.bytes_do_tipo(A.SEM)
        perda = acv.bytes_do_tipo(A.LOSSY)
        semperda = acv.bytes_do_tipo(A.LOSSLESS)
        self.resumo.setText(tr("{} arquivos, {} no total. Sem compressão: {} ({}%). Comprimidos sem perda: {} ({}%). Com perda: {} ({}%).").format(
            f"{acv.arquivos:,}".replace(",", "."), A.tamanho(acv.bytes),
            A.tamanho(sem), round(100 * sem / total),
            A.tamanho(semperda), round(100 * semperda / total),
            A.tamanho(perda), round(100 * perda / total)))

        self.t_sintaxe.setRowCount(0)
        for uid, arquivos, bytes_, pixels in acv.por_sintaxe():
            s = A.sintaxe(uid)
            i = self.t_sintaxe.rowCount()
            self.t_sintaxe.insertRow(i)
            for col, txt, dir_ in ((0, s.nome, False), (1, self._tipo(s.tipo), False),
                                   (2, f"{arquivos}", True), (3, A.tamanho(bytes_), True),
                                   (4, f"{round(100 * bytes_ / total)}%", True),
                                   (5, f"{(bytes_ / pixels):.2f}" if pixels else "—", True)):
                self.t_sintaxe.setItem(i, col, _item(txt, dir_))

        self.t_modalidade.setRowCount(0)
        for mod, arquivos, bytes_, pixels in acv.por_modalidade():
            i = self.t_modalidade.rowCount()
            self.t_modalidade.insertRow(i)
            for col, txt, dir_ in ((0, mod, False), (1, f"{arquivos}", True),
                                   (2, A.tamanho(bytes_), True),
                                   (3, f"{round(100 * bytes_ / total)}%", True),
                                   (4, f"{(bytes_ / pixels):.2f}" if pixels else "—", True)):
                self.t_modalidade.setItem(i, col, _item(txt, dir_))
        _ajusta_altura(self.t_sintaxe)
        _ajusta_altura(self.t_modalidade)
        _ajusta_altura(self.t_ganho, 4)
        self.escrever_nota()

    def _tipo(self, tipo: str) -> str:
        return {A.SEM: tr("sem compressão"), A.LOSSLESS: tr("sem perda"),
                A.LOSSY: tr("com perda")}.get(tipo, tr("não reconhecido"))

    def escrever_nota(self) -> None:
        faltando = [f"{A.sintaxe(u).nome} (pip install {falta})"
                    for u, (ok, falta) in A.codificadores().items() if not ok and falta]
        partes = [tr("A medição comprime uma amostra em memória e descarta: nenhum arquivo do acervo é alterado.")]
        if faltando:
            partes.append(tr("Este computador ainda não grava: {}.").format("; ".join(faltando)))
        partes.append(tr("Compressão com perda cria um objeto novo (SOP Instance UID novo, ImageType DERIVED) e nunca substitui o original; no Brasil a taxa aceitável é avaliação do radiologista (CFM 2.107/2014)."))
        self.nota.setText(" ".join(partes))

    # ------------------------------------------------------------------ medição
    def medir(self) -> None:
        if self._medidor is not None:
            self._medidor.stop.set()
            return
        caminhos = A.amostra(self.repo)
        if not caminhos:
            QMessageBox.information(self, tr("Relatório do acervo"),
                                    tr("Não há arquivo sem compressão no acervo para medir."))
            return
        self.barra.setVisible(True)
        self.barra.setRange(0, len(caminhos))
        self.b_medir.setText(tr("Parar a medição"))
        self._medidor = _Medidor(caminhos, self)
        self._medidor.andamento.connect(lambda i, n: self.barra.setValue(i))
        self._medidor.pronto.connect(self.medido)
        self._medidor.start()

    def medido(self, medidas) -> None:
        self._medidor = None
        self.medidas = list(medidas or [])
        self.barra.setVisible(False)
        self.b_medir.setText(tr("Medir de novo"))
        self.t_ganho.setRowCount(0)
        for m, hoje, depois in A.projetar(self.acervo, self.medidas):
            i = self.t_ganho.rowCount()
            self.t_ganho.insertRow(i)
            if not m.disponivel:
                valores = [m.nome, tr("não instalado"), "—", "—", "—"]
            elif m.arquivos == 0:
                valores = [m.nome, tr("nenhum arquivo"), "—", "—", "—"]
            else:
                valores = [m.nome, tr("{} arquivos").format(m.arquivos), f"{m.razao:.2f}:1",
                           A.tamanho(depois), A.tamanho(hoje - depois)]
            for col, txt in enumerate(valores):
                self.t_ganho.setItem(i, col, _item(txt, col > 1))
        _ajusta_altura(self.t_ganho, 4)
        self.escrever_nota()

    # ------------------------------------------------------------------ saída
    def exportar(self) -> None:
        caminho, _ = QFileDialog.getSaveFileName(self, tr("Exportar CSV…"), "acervo.csv",
                                                 tr("Planilha (*.csv)"))
        if not caminho:
            return
        try:
            with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow([tr("Modalidade"), tr("Formato guardado"), tr("Tipo"),
                            tr("Arquivos"), tr("Bytes"), tr("Pixels")])
                for l in self.acervo.linhas:
                    w.writerow([l.modalidade, l.nome, self._tipo(l.tipo), l.arquivos,
                                l.bytes, l.pixels])
                if self.medidas:
                    w.writerow([])
                    w.writerow([tr("Compressão sem perda"), tr("Arquivos medidos"),
                                tr("Bytes de origem"), tr("Bytes de saída"), tr("Taxa")])
                    for m in self.medidas:
                        w.writerow([m.nome, m.arquivos, m.bytes_origem, m.bytes_saida,
                                    f"{m.razao:.3f}"])
        except OSError as e:
            QMessageBox.warning(self, tr("Exportar CSV…"),
                                tr("Não consegui gravar a planilha: {}").format(e))
            return
        QMessageBox.information(self, tr("Exportar CSV…"),
                                tr("Planilha gravada em {}").format(caminho))

    def closeEvent(self, event) -> None:  # noqa: D102, N802
        for w in (self._medidor, self._comprimidor):
            if w is not None:
                w.stop.set()
                w.wait(5000)
        super().closeEvent(event)
