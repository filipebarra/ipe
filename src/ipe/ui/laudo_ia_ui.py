"""Telas da IA no texto do laudo (0.99.54, onda B5): botão "IA ▾" da janela do laudo, resultado para
aceitar ou não, conferência antes de assinar e a configuração do provedor."""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
                               QToolButton, QVBoxLayout)

from ipe.core import laudo_ia as LI

log = logging.getLogger(__name__)


class _Trabalho(QObject):
    pronto = Signal(str, str)          # (resposta, erro)

    def __init__(self, acao, texto, cfg, info):
        super().__init__()
        self.args = (acao, texto, cfg, info)

    def rodar(self):
        try:
            self.pronto.emit(LI.pedir(*self.args), "")
        except Exception as e:  # noqa: BLE001
            log.exception("IA do laudo")
            self.pronto.emit("", str(e))


class ResultadoDialog(QDialog):
    """A proposta da IA, editável; nada entra no laudo sem um dos botões."""

    def __init__(self, acao: str, proposta: str, parent=None):
        super().__init__(parent)
        self.acao = acao
        self.escolha = ""
        self.setWindowTitle(f"IA do laudo — {LI.ACOES.get(acao, acao)}")
        self.resize(760, 560)
        aviso = QLabel("Sugestão do modelo de linguagem: confira cada linha antes de usar. Nada muda no laudo sem "
                       "você clicar abaixo (e Ctrl+Z desfaz).")
        aviso.setWordWrap(True)
        self.texto = QPlainTextEdit(proposta)
        bb = QDialogButtonBox()
        if acao == "refinar":
            self.b_usar = bb.addButton("Trocar o texto do laudo por este", QDialogButtonBox.AcceptRole)
        elif acao == "impressao":
            self.b_usar = bb.addButton("Inserir no laudo (no cursor)", QDialogButtonBox.AcceptRole)
        else:
            self.b_usar = None
        bb.addButton("Fechar", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._usar)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(aviso)
        lay.addWidget(self.texto, 1)
        lay.addWidget(bb)

    def _usar(self):
        self.escolha = self.texto.toPlainText()
        self.accept()


class IALaudo(QObject):
    """O botão "IA ▾" da janela do laudo e o que ele faz."""

    def __init__(self, janela):
        super().__init__(janela)
        self.j = janela
        self._thread = None
        self.botao = QToolButton()
        self.botao.setText("IA ▾")
        self.botao.setToolTip("Conferir o laudo, refinar o texto, gerar a impressão, apontar erros")
        self.botao.setPopupMode(QToolButton.InstantPopup)
        m = QMenu(janela)
        m.addAction("Conferir o laudo (sem rede)", self.conferir)
        m.addSeparator()
        self.acoes = {}
        for k in ("refinar", "impressao", "erros"):
            self.acoes[k] = m.addAction(LI.ACOES[k] + " (IA)…", lambda k=k: self.pedir(k))
        m.addSeparator()
        m.addAction("Configurar a IA do laudo…", self.configurar)
        m.aboutToShow.connect(self._ajustar)
        self.botao.setMenu(m)

    def _cfg(self):
        return LI.config(self.j.settings)

    def _ajustar(self):
        ligada = bool(self._cfg()["provedor"])
        for a in self.acoes.values():
            a.setEnabled(ligada and not self.j.editor.isReadOnly() or (a is self.acoes["erros"] and ligada))

    # ------------------------------------------------------------------ conferência local
    def avisos(self) -> list[dict]:
        return LI.conferir(self.j.editor.toPlainText(), self.j._birads_values(), self.j.info)

    def conferir(self) -> list[dict]:
        av = self.avisos()
        if not av:
            QMessageBox.information(self.j, "Conferir o laudo", "Nada a apontar na conferência local.")
        else:
            QMessageBox.warning(self.j, "Conferir o laudo", LI.texto_dos_avisos(av))
        return av

    def pode_assinar(self) -> bool:
        """Antes de assinar: com avisos, pergunta. Sim = assinar mesmo assim."""
        if not self._cfg()["conferir_ao_assinar"]:
            return True
        av = self.avisos()
        if not av:
            return True
        return QMessageBox.question(
            self.j, "Conferir antes de assinar",
            "A conferência do laudo achou:\n\n" + LI.texto_dos_avisos(av) + "\n\nAssinar mesmo assim?") \
            == QMessageBox.Yes

    # ------------------------------------------------------------------ modelo de linguagem
    def pedir(self, acao: str, esperar: bool = False) -> None:
        cfg = self._cfg()
        if not cfg["provedor"]:
            QMessageBox.information(self.j, "IA do laudo", "Escolha o provedor em Configurar a IA do laudo….")
            return
        texto = self.j.editor.toPlainText().strip()
        if not texto:
            return
        st = self.j.settings
        if LI.remoto(cfg) and st is not None and not st.get("laudo_ia.remoto_aceito", False):
            if QMessageBox.question(self.j, "IA do laudo",
                                    f"O texto do laudo vai para {cfg['url']} — sem o nome, o ID, o accession e "
                                    "a data de nascimento do paciente. Continuar? (Não pergunta de novo.)") \
                    != QMessageBox.Yes:
                return
            st.set("laudo_ia.remoto_aceito", True)
            st.save()
        self.j.status.setText(f"IA do laudo: {LI.ACOES[acao].lower()}…")
        tr = _Trabalho(acao, texto, cfg, self.j.info)
        if esperar:                                   # testes: sem thread
            tr.pronto.connect(lambda r, e: self._chegou(acao, r, e))
            tr.rodar()
            return
        th = QThread(self)
        tr.moveToThread(th)
        th.started.connect(tr.rodar)
        tr.pronto.connect(lambda r, e: self._chegou(acao, r, e))
        tr.pronto.connect(th.quit)
        th.finished.connect(tr.deleteLater)
        self._thread, self._trabalho = th, tr
        th.start()

    def _chegou(self, acao: str, resposta: str, erro: str) -> None:
        self.j.status.setText("")
        if erro:
            QMessageBox.warning(self.j, "IA do laudo", f"Não deu certo: {erro}")
            return
        dlg = ResultadoDialog(acao, resposta, self.j)
        self.ultimo = dlg
        if dlg.exec() and dlg.escolha:
            self.aplicar(acao, dlg.escolha)

    def aplicar(self, acao: str, texto: str) -> None:
        cur = self.j.editor.textCursor()
        if acao == "refinar":
            cur.beginEditBlock()
            cur.select(cur.SelectionType.Document)
            cur.insertText(texto)
            cur.endEditBlock()
        elif acao == "impressao":
            cur.insertText(texto)

    def configurar(self) -> None:
        LaudoIAConfigDialog(self.j.settings, self.j).exec()


class LaudoIAConfigDialog(QDialog):
    """Configurações ▸ Laudos ▸ IA no texto do laudo (por computador)."""

    def __init__(self, settings, parent=None, testar=None):
        super().__init__(parent)
        self.settings = settings
        self._testar = testar
        self.setWindowTitle("IA no texto do laudo")
        cfg = LI.config(settings)
        self.prov = QComboBox()
        for k, v in LI.PROVEDORES.items():
            self.prov.addItem(v, k)
        self.prov.setCurrentIndex(max(0, list(LI.PROVEDORES).index(cfg["provedor"])
                                      if cfg["provedor"] in LI.PROVEDORES else 0))
        self.url = QLineEdit(str(settings.get("laudo_ia.url", "") or ""))
        self.modelo = QLineEdit(str(settings.get("laudo_ia.modelo", "") or ""))
        self.chave = QLineEdit(cfg["chave"])
        self.chave.setEchoMode(QLineEdit.Password)
        self.tempo = QDoubleSpinBox()
        self.tempo.setRange(5, 600)
        self.tempo.setSuffix(" s")
        self.tempo.setValue(cfg["tempo"])
        self.conferir = QCheckBox("Conferir o laudo antes de assinar (sem rede; pergunta só quando acha algo)")
        self.conferir.setChecked(cfg["conferir_ao_assinar"])
        self.prov.currentIndexChanged.connect(self._dicas)
        form = QFormLayout()
        form.addRow("Provedor:", self.prov)
        form.addRow("Endereço:", self.url)
        form.addRow("Modelo:", self.modelo)
        form.addRow("Chave da API:", self.chave)
        form.addRow("Tempo máximo:", self.tempo)
        form.addRow(self.conferir)
        self.nota = QLabel()
        self.nota.setWordWrap(True)
        b_teste = QPushButton("Testar")
        b_teste.clicked.connect(self.testar)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._salvar)
        bb.rejected.connect(self.reject)
        h = QHBoxLayout()
        h.addWidget(b_teste)
        h.addStretch(1)
        h.addWidget(bb)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.nota)
        lay.addLayout(h)
        self._dicas()

    def _dicas(self, *_a):
        k = self.prov.currentData()
        self.url.setPlaceholderText(LI.URL_PADRAO.get(k, ""))
        self.modelo.setPlaceholderText(LI.MODELO_PADRAO.get(k, ""))
        self.chave.setEnabled(k in ("openai", "anthropic"))
        self.nota.setText({
            "": "Desligada: o botão IA ▾ do laudo só faz a conferência local.",
            "ollama": "Ollama roda o modelo neste computador (ou num da rede): o texto não sai do serviço.",
            "openai": "Qualquer servidor com a API do OpenAI (LM Studio, vLLM, llama.cpp). Se o endereço não for "
                      "deste computador, o texto sai dele — sem o nome, o ID e o nascimento do paciente.",
            "anthropic": "O texto vai para a API da Anthropic, sem o nome, o ID e o nascimento do paciente. Use "
                         "só se o serviço permitir enviar laudos para fora.",
        }.get(k, ""))

    def valor(self) -> dict:
        return {"provedor": self.prov.currentData(), "url": self.url.text().strip(),
                "modelo": self.modelo.text().strip(), "chave": self.chave.text().strip(),
                "tempo": self.tempo.value(), "conferir_ao_assinar": self.conferir.isChecked()}

    def _cfg_da_tela(self) -> dict:
        v = self.valor()
        return {**v, "url": v["url"] or LI.URL_PADRAO.get(v["provedor"], ""),
                "modelo": v["modelo"] or LI.MODELO_PADRAO.get(v["provedor"], "")}

    def testar(self) -> str:
        try:
            r = LI.conversar(self._cfg_da_tela(), "Responda só OK.", "Diga OK.", post=self._testar)
            QMessageBox.information(self, "IA do laudo", f"Respondeu: {r[:200]}")
            return r
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "IA do laudo", f"Não deu certo: {e}")
            return ""

    def _salvar(self) -> None:
        from ipe.core import segredos as SG
        v = self.valor()
        self.settings.set("laudo_ia.provedor", v["provedor"])
        self.settings.set("laudo_ia.url", v["url"])
        self.settings.set("laudo_ia.modelo", v["modelo"])
        self.settings.set("laudo_ia.tempo", v["tempo"])
        self.settings.set("laudo_ia.conferir_ao_assinar", v["conferir_ao_assinar"])
        self.settings.set("laudo_ia.chave", SG.guardar(v["chave"]))
        self.settings.save()
        self.accept()
