"""A janela que mostra a instalação das IAs acontecendo (0.100.27).

Pedido dele (12/11/2026): *"quando eu for instalar as IAs de segmentações, abra uma janela para eu acompanhar o
andamento e possíveis erros. hoje eu clico e não sei se deu certo nem acompanho."*

Antes o instalador abria num console à parte (que no Linux empacotado e no macOS nem sempre abria). Agora ele roda
como processo-filho do Ipê (QProcess) e a saída aparece aqui, linha a linha, com:

- o **passo atual** e o tempo decorrido no alto;
- no fim, um veredito claro — **instalado**, **terminou com erros** (com as linhas de erro destacadas) ou
  **interrompido** — conferido de verdade (o ambiente existe? os pesos estão lá?), não só pelo código de saída;
- Copiar tudo, Salvar…, Abrir a pasta do log; o texto inteiro também fica em `instalacao_ia.log`, na pasta dos logs.

A janela não trava o programa: dá para continuar usando o Ipê. Fechar a janela com a instalação rodando pergunta
se é para interromper ou só esconder (ela volta pelo mesmo menu).
"""
from __future__ import annotations

import logging
import os
import re
import sys
import time
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QVBoxLayout,
)

log = logging.getLogger(__name__)

#: linhas que contam como erro (o .bat escreve "[ERRO]"; o pip, "ERROR:"; o Python, "Traceback")
_ERRO = re.compile(r"\[ERRO\]|\[ERROR\]|^ERROR[: ]|^Traceback \(most recent call last\)|No matching distribution|"
                   r"os error \d+|Errno \d+|^\s*\w*Error: ", re.IGNORECASE)
_AVISO = re.compile(r"\[aviso\]|^WARNING[: ]|DEPRECATION", re.IGNORECASE)
#: linhas que dizem em que passo a instalação está
_PASSO = re.compile(r"^\s*(\[\d+/\d+\]|\[extra\]|\[[A-Za-zÀ-ÿ0-9 ]+\]|===|Collecting |Downloading |Installing collected|"
                    r"Successfully installed|baixando|extraindo|criando)", re.IGNORECASE)

#: as janelas abertas, por chave ("segmentacao", "extras"): uma só de cada
_ABERTAS: dict[str, "InstaladorJanela"] = {}


def pasta_do_log() -> Path:
    try:
        from ipe.core.config import get_paths
        return Path(get_paths().logs)
    except Exception:  # noqa: BLE001
        import tempfile
        return Path(tempfile.gettempdir())


class InstaladorJanela(QDialog):
    """Roda `comando` (lista) e mostra a saída. `conferir()` -> (bool, texto) diz, no fim, se ficou instalado."""
    terminou = Signal(bool)

    def __init__(self, titulo: str, comando: list[str], ambiente: dict | None = None, conferir=None, parent=None,
                 chave: str = ""):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.resize(860, 560)
        self.setModal(False)
        self.comando, self.conferir, self.chave = [str(c) for c in comando], conferir, chave
        self.erros: list[str] = []
        self.linhas = 0
        self.inicio = 0.0
        self.resultado: bool | None = None
        self.interrompido = False
        self._resto = ""
        self._ultima_cr = False
        self._arq = None

        lay = QVBoxLayout(self)
        self.l_estado = QLabel("Preparando…")
        f = self.l_estado.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() + 1)
        self.l_estado.setFont(f)
        self.l_estado.setWordWrap(True)
        lay.addWidget(self.l_estado)
        self.l_passo = QLabel("")
        self.l_passo.setWordWrap(True)
        lay.addWidget(self.l_passo)
        self.barra = QProgressBar()
        self.barra.setRange(0, 0)                               # "ocupado": não dá para saber o total
        self.barra.setTextVisible(False)
        self.barra.setFixedHeight(8)
        lay.addWidget(self.barra)
        self.texto = QPlainTextEdit(readOnly=True)
        self.texto.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.texto.setMaximumBlockCount(20000)
        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        mono.setStyleHint(QFont.Monospace)
        self.texto.setFont(mono)
        lay.addWidget(self.texto, 1)
        self.l_erros = QLabel("")
        self.l_erros.setWordWrap(True)
        self.l_erros.setVisible(False)
        self.l_erros.setStyleSheet("color: #ff7b72;")
        lay.addWidget(self.l_erros)
        bot = QHBoxLayout()
        self.b_parar = QPushButton("Interromper")
        self.b_parar.clicked.connect(self.interromper)
        self.b_copiar = QPushButton("Copiar tudo")
        self.b_copiar.clicked.connect(lambda: QApplication.clipboard().setText(self.texto.toPlainText()))
        self.b_salvar = QPushButton("Salvar…")
        self.b_salvar.clicked.connect(self.salvar)
        self.b_pasta = QPushButton("Abrir a pasta do log")
        self.b_pasta.clicked.connect(self.abrir_pasta)
        self.b_fechar = QPushButton("Esconder")
        self.b_fechar.clicked.connect(self.close)
        for b in (self.b_parar, self.b_copiar, self.b_salvar, self.b_pasta):
            bot.addWidget(b)
        bot.addStretch(1)
        bot.addWidget(self.b_fechar)
        lay.addLayout(bot)

        self.fmt_erro = QTextCharFormat()
        self.fmt_erro.setForeground(QColor("#ff7b72"))
        self.fmt_aviso = QTextCharFormat()
        self.fmt_aviso.setForeground(QColor("#e3b341"))
        self.fmt_ok = QTextCharFormat()
        self.fmt_ok.setForeground(QColor("#56d364"))
        self.fmt_normal = QTextCharFormat()

        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        env = QProcessEnvironment()
        amb = dict(os.environ if ambiente is None else ambiente)
        amb.setdefault("PYTHONUNBUFFERED", "1")                  # a saída do Python chega na hora, não no fim
        amb.setdefault("PYTHONIOENCODING", "utf-8")
        amb.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
        amb.setdefault("PIP_PROGRESS_BAR", "off")                # a barra do pip, sem terminal, vira lixo
        for k, v in amb.items():
            env.insert(str(k), str(v))
        self.proc.setProcessEnvironment(env)
        self.proc.readyReadStandardOutput.connect(self._ler)
        self.proc.finished.connect(self._fim)
        self.proc.errorOccurred.connect(self._erro_do_processo)
        self.relogio = QTimer(self)
        self.relogio.setInterval(1000)
        self.relogio.timeout.connect(self._tique)

    # ------------------------------------------------------------ rodar
    def iniciar(self) -> None:
        self.inicio = time.monotonic()
        try:
            pasta = pasta_do_log()
            pasta.mkdir(parents=True, exist_ok=True)
            self._arq = open(pasta / "instalacao_ia.log", "a", encoding="utf-8")       # noqa: SIM115
            self._arq.write(f"\n=== {self.windowTitle()} — {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
                            f"$ {' '.join(self.comando)}\n")
        except OSError:
            self._arq = None
        self._linha("$ " + " ".join(self.comando), self.fmt_aviso)
        self.l_estado.setText("Instalando… (pode continuar usando o programa)")
        self.proc.start(self.comando[0], self.comando[1:])
        self.proc.closeWriteChannel()                            # o "pause" / "Enter para fechar" do fim não espera
        self.relogio.start()

    def rodando(self) -> bool:
        return self.proc.state() != QProcess.NotRunning

    def _tique(self) -> None:
        s = int(time.monotonic() - self.inicio)
        self.l_estado.setText(f"Instalando… {s // 60}:{s % 60:02d} (pode continuar usando o programa)")

    # ------------------------------------------------------------ saída
    def _ler(self) -> None:
        dados = bytes(self.proc.readAllStandardOutput())
        try:
            txt = dados.decode("utf-8")
        except UnicodeDecodeError:
            txt = dados.decode("mbcs" if sys.platform == "win32" else "latin-1", errors="replace")
        self.alimentar(txt)

    def alimentar(self, txt: str) -> None:
        """Recebe um pedaço da saída. '\\r' sozinho (barra de progresso) reescreve a última linha."""
        txt = self._resto + txt.replace("\r\n", "\n")
        partes = re.split(r"(\n|\r)", txt)
        self._resto = partes.pop() if partes else ""
        for i in range(0, len(partes) - 1, 2):
            linha, sep = partes[i], partes[i + 1]
            self._linha(linha, None, substituir=self._ultima_cr)
            self._ultima_cr = sep == "\r"

    def _linha(self, linha: str, fmt=None, substituir: bool = False) -> None:
        linha = linha.rstrip()
        da_saida = fmt is None                                  # as linhas que a própria janela escreve não contam
        e_erro = da_saida and bool(_ERRO.search(linha))
        if fmt is None:
            fmt = self.fmt_erro if e_erro else self.fmt_aviso if _AVISO.search(linha) else self.fmt_normal
        if e_erro and linha not in self.erros:
            self.erros.append(linha.strip()[:300])
            self.l_erros.setText(f"{len(self.erros)} linha(s) de erro até agora. A última: {self.erros[-1]}")
            self.l_erros.setVisible(True)
        if da_saida and _PASSO.search(linha) and linha.strip():
            self.l_passo.setText(linha.strip()[:160])
        barra = self.texto.verticalScrollBar()
        no_fim = barra.value() >= barra.maximum() - 4
        cur = QTextCursor(self.texto.document())
        cur.movePosition(QTextCursor.End)
        if substituir and self.linhas:                          # barra de progresso: reescreve a última linha
            cur.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
            cur.removeSelectedText()
        elif self.linhas:
            cur.insertBlock()
        cur.insertText(linha, fmt)
        self.linhas += 1
        if no_fim:
            barra.setValue(barra.maximum())
        if self._arq is not None and not substituir:
            try:
                self._arq.write(linha + "\n")
                self._arq.flush()
            except OSError:
                pass

    # ------------------------------------------------------------ fim
    def _erro_do_processo(self, _e) -> None:
        if self.proc.state() == QProcess.NotRunning and self.resultado is None and not self.interrompido:
            msg = f"[ERRO] Não consegui rodar o instalador: {self.proc.errorString()}"
            self.erros.append(msg)
            self._linha(msg, self.fmt_erro)
            self._fim(-1, QProcess.CrashExit)

    def _fim(self, codigo: int = 0, _estado=None) -> None:
        if self.resultado is not None:
            return
        if self._resto:
            self._linha(self._resto)
            self._resto = ""
        self.relogio.stop()
        self.barra.setRange(0, 1)
        self.barra.setValue(1)
        s = int(time.monotonic() - self.inicio)
        tempo = f"{s // 60} min {s % 60:02d} s"
        instalado, detalhe = True, ""
        if self.conferir is not None:
            try:
                instalado, detalhe = self.conferir()
            except Exception as e:  # noqa: BLE001
                instalado, detalhe = False, f"não consegui conferir: {e}"
        ok = bool(instalado) and not self.interrompido and codigo == 0 and not self.erros
        if self.interrompido:
            titulo, fmt = f"Interrompido depois de {tempo}. Nada garante que ficou instalado.", self.fmt_aviso
            ok = False
        elif ok:
            titulo, fmt = f"Instalado sem erros em {tempo}.", self.fmt_ok
        elif instalado and (self.erros or codigo != 0):
            titulo = (f"Terminou em {tempo}, e o que foi conferido está instalado, mas houve {len(self.erros)} "
                      f"linha(s) de erro: leia abaixo.")
            fmt = self.fmt_aviso
        else:
            titulo = (f"NÃO ficou instalado ({tempo}): {detalhe}. Veja os erros abaixo." if detalhe
                      else f"NÃO ficou instalado ({tempo}). Veja os erros abaixo.")
            fmt = self.fmt_erro
        if detalhe and (ok or instalado):
            titulo += " " + detalhe
        self.resultado = ok
        self.l_estado.setText(titulo)
        self.l_estado.setStyleSheet(f"color: {fmt.foreground().color().name()};" if fmt is not self.fmt_normal else "")
        self._linha("")
        self._linha("=== " + titulo, fmt)
        if self.erros:
            self._linha("Linhas de erro:", self.fmt_erro)
            for e in self.erros[:30]:
                self._linha("  " + e, self.fmt_erro)
            self.l_erros.setText(f"{len(self.erros)} linha(s) de erro (em vermelho no texto). "
                                 "Use Copiar tudo para mandar a saída inteira.")
        self.b_parar.setEnabled(False)
        self.b_fechar.setText("Fechar")
        if self._arq is not None:
            try:
                self._arq.close()
            except OSError:
                pass
            self._arq = None
        self.show()
        self.raise_()                                            # terminou: volta para a frente
        self.terminou.emit(ok)

    def interromper(self) -> None:
        if not self.rodando():
            return
        if QMessageBox.question(self, self.windowTitle(),
                                "Interromper a instalação? O que já foi baixado fica; rodar de novo continua de "
                                "onde parou na maior parte dos passos.") != QMessageBox.Yes:
            return
        self.interrompido = True
        self._matar()

    def _matar(self) -> None:
        pid = int(self.proc.processId() or 0)
        if sys.platform == "win32" and pid:                      # o .bat tem filhos (python, pip): a árvore inteira
            import subprocess
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=15,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except Exception:  # noqa: BLE001
                log.debug("taskkill", exc_info=True)
        self.proc.kill()

    # ------------------------------------------------------------ utilidades
    def salvar(self) -> None:
        nome, _f = QFileDialog.getSaveFileName(self, "Salvar a saída da instalação",
                                               str(Path.home() / "instalacao_ia.txt"), "Texto (*.txt)")
        if nome:
            try:
                Path(nome).write_text(self.texto.toPlainText(), encoding="utf-8")
            except OSError as e:
                QMessageBox.warning(self, self.windowTitle(), f"Não consegui salvar: {e}")

    def abrir_pasta(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(pasta_do_log())))

    def closeEvent(self, e) -> None:  # noqa: N802
        if self.rodando():
            cx = QMessageBox(QMessageBox.Question, self.windowTitle(),
                             "A instalação ainda está rodando.", parent=self)
            b_esc = cx.addButton("Esconder (continua instalando)", QMessageBox.AcceptRole)
            b_int = cx.addButton("Interromper", QMessageBox.DestructiveRole)
            cx.addButton("Voltar", QMessageBox.RejectRole)
            cx.exec()
            if cx.clickedButton() is b_int:
                self.interrompido = True
                self._matar()
                e.accept()
            elif cx.clickedButton() is b_esc:
                e.ignore()
                self.hide()
            else:
                e.ignore()
            return
        _ABERTAS.pop(self.chave, None)
        e.accept()


def abrir(chave: str, titulo: str, comando: list[str], ambiente: dict | None = None, conferir=None, parent=None,
          ao_terminar=None) -> InstaladorJanela:
    """Abre (ou traz para a frente, se já estiver rodando) a janela da instalação `chave`."""
    velha = _ABERTAS.get(chave)
    if velha is not None:
        try:
            if velha.rodando():
                velha.show()
                velha.raise_()
                velha.activateWindow()
                return velha
            velha.close()
        except RuntimeError:                                     # a janela já foi destruída pelo Qt
            pass
    j = InstaladorJanela(titulo, comando, ambiente, conferir, parent, chave)
    _ABERTAS[chave] = j
    if ao_terminar is not None:
        j.terminou.connect(ao_terminar)
    j.show()
    j.iniciar()
    return j
