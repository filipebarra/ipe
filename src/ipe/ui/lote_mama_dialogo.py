"""Pesquisa ▸ Densidade e calcificações em lote (0.100.69): a janela do `automation.lote_mama`.

Escolhe a planilha (ID e data da mamografia), o PACS e a saída; roda numa linha de fundo, uma mamografia por vez;
pode parar e continuar. Não mostra nome de paciente: só o número da linha, a situação e as contagens.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QVBoxLayout,
)

from ipe.automation import lote_mama as L
from ipe.automation import lote_mama_ipe as LI
from ipe.core.i18n import tr

log = logging.getLogger(__name__)


class _Sinais(QObject):
    linha = Signal(object, object, object)      # andamento, linha, resultado
    fim = Signal(object, str)                   # andamento, erro


def duracao(s: float | None) -> str:
    if s is None:
        return ""
    s = int(s)
    if s < 90:
        return "%d s" % s
    if s < 5400:
        return "%d min" % (s // 60)
    return "%d h %02d min" % (s // 3600, s % 3600 // 60)


class LoteMamaDialog(QDialog):
    def __init__(self, repo, net, settings, storage_root, fila=None, parent=None):
        super().__init__(parent)
        self.repo, self.net, self.settings, self.storage_root, self.fila = repo, net, settings, storage_root, fila
        self.setWindowTitle("Densidade e calcificações vasculares em lote")
        self.setMinimumWidth(680)
        self.dados: list[list] = []
        self.lote: L.Lote | None = None
        self.parar = threading.Event()
        self.linha_de_fundo: threading.Thread | None = None
        self.sinais = _Sinais(self)
        self.sinais.linha.connect(self._andou)
        self.sinais.fim.connect(self._acabou)
        lay = QVBoxLayout(self)
        intro = QLabel("Para cada linha de uma planilha (ID do paciente e data da mamografia), o Ipê acha o exame — "
                       "no banco dele ou no PACS —, baixa, mede a densidade e as calcificações vasculares e grava "
                       "uma planilha com os resultados ao lado das colunas originais. São as medidas automáticas, "
                       "sem confirmação de um médico.")
        intro.setWordWrap(True)
        lay.addWidget(intro)
        f = QFormLayout()
        self.e_arquivo = QLineEdit()
        self.e_arquivo.setReadOnly(True)
        b = QPushButton("Escolher…")
        b.clicked.connect(self.escolher_arquivo)
        h = QHBoxLayout()
        h.addWidget(self.e_arquivo, 1)
        h.addWidget(b)
        f.addRow("Planilha (.xlsx ou .csv):", h)
        self.c_aba = QComboBox()
        self.c_aba.currentIndexChanged.connect(lambda _i: self.carregar_aba())
        f.addRow("Aba:", self.c_aba)
        self.c_id, self.c_data, self.c_nasc = QComboBox(), QComboBox(), QComboBox()
        self.c_nasc.setToolTip("Opcional. Com ela, o exame achado só é medido se a data de nascimento for a mesma "
                               "(protege contra dois pacientes com o mesmo ID).")
        f.addRow("Coluna do ID do paciente:", self.c_id)
        f.addRow("Coluna da data da mamografia:", self.c_data)
        f.addRow("Coluna do nascimento (conferência):", self.c_nasc)
        self.c_no = QComboBox()
        for n in [n for n in repo.nodes(only_active=True) if n["kind"] == "dimse"]:
            self.c_no.addItem(f"{n['name']} ({n['ae_title']})", n["id"])
        self.c_no.currentIndexChanged.connect(lambda _i: self._identidades())
        f.addRow("PACS:", self.c_no)
        self.c_ident = QComboBox()
        f.addRow("Falar como:", self.c_ident)
        self.e_saida = QLineEdit()
        b2 = QPushButton("Escolher…")
        b2.clicked.connect(self.escolher_saida)
        h2 = QHBoxLayout()
        h2.addWidget(self.e_saida, 1)
        h2.addWidget(b2)
        f.addRow("Planilha de saída:", h2)
        self.k_apagar = QCheckBox("Apagar do Ipê, depois de medir, os exames baixados só para o lote")
        self.k_apagar.setChecked(True)
        self.k_apagar.setToolTip("Os exames que já estavam no Ipê nunca são apagados. Desmarque para ficar com as "
                                 "imagens (confira o espaço em disco: são dezenas de megabytes por mamografia).")
        f.addRow("", self.k_apagar)
        self.k_refazer = QCheckBox("Ao continuar, tentar de novo os não encontrados e os com erro")
        self.k_refazer.setChecked(True)
        f.addRow("", self.k_refazer)
        self.s_limite = QSpinBox(minimum=0, maximum=1_000_000, value=0)
        self.s_limite.setSpecialValueText("todas")
        self.s_limite.setToolTip("Para testar: faz só as primeiras N linhas que faltam e para.")
        f.addRow("Quantas linhas agora:", self.s_limite)
        lay.addLayout(f)
        self.l_lista = QLabel()
        self.l_lista.setWordWrap(True)
        lay.addWidget(self.l_lista)
        self.barra = QProgressBar()
        lay.addWidget(self.barra)
        self.l_estado = QLabel()
        self.l_estado.setWordWrap(True)
        lay.addWidget(self.l_estado)
        self.diario = QPlainTextEdit()
        self.diario.setReadOnly(True)
        self.diario.setMaximumBlockCount(400)
        self.diario.setMinimumHeight(130)
        lay.addWidget(self.diario)
        hb = QHBoxLayout()
        self.b_iniciar = QPushButton("Iniciar")
        self.b_iniciar.setDefault(True)
        self.b_iniciar.clicked.connect(self.iniciar)
        self.b_parar = QPushButton("Parar")
        self.b_parar.setEnabled(False)
        self.b_parar.clicked.connect(self.pedir_parada)
        self.b_abrir = QPushButton("Abrir a pasta da saída")
        self.b_abrir.clicked.connect(self.abrir_pasta)
        b_fechar = QPushButton("Fechar")
        b_fechar.clicked.connect(self.close)
        hb.addWidget(self.b_iniciar)
        hb.addWidget(self.b_parar)
        hb.addStretch(1)
        hb.addWidget(self.b_abrir)
        hb.addWidget(b_fechar)
        lay.addLayout(hb)
        self._identidades()
        self._conferir()

    # ------------------------------------------------------------------ escolhas
    def _identidades(self) -> None:
        self.c_ident.clear()
        self.c_ident.addItem(f"Este programa ({self.net.local_ae})", None)
        no = self.no()
        for i in (self.net.identities_for(no) if no else []):
            self.c_ident.addItem(f"{i['name']} ({i['ae_title']})", i["id"])

    def no(self) -> dict | None:
        nid = self.c_no.currentData()
        return next((n for n in self.repo.nodes(only_active=True) if n["id"] == nid), None)

    def escolher_arquivo(self) -> None:
        caminho, _f = QFileDialog.getOpenFileName(self, "Planilha com a lista", "", "Planilhas (*.xlsx *.csv)")
        if caminho:
            self.abrir_arquivo(caminho)

    def abrir_arquivo(self, caminho: str) -> bool:
        try:
            nomes = L.abas(caminho)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, self.windowTitle(), f"Não deu para abrir a planilha:\n{e}")
            return False
        self.e_arquivo.setText(caminho)
        self.c_aba.blockSignals(True)
        self.c_aba.clear()
        self.c_aba.addItems(nomes or ["(única)"])
        # a aba com cara de lista: a primeira que tem uma coluna de ID e uma de data
        escolhida = 0
        for i, nome in enumerate(nomes):
            try:
                cab = (L.ler_planilha(caminho, nome) or [[]])[0]
            except Exception:  # noqa: BLE001
                continue
            c = L.achar_colunas(cab)
            if c["id"] >= 0 and c["data"] >= 0:
                escolhida = i
                break
        self.c_aba.setCurrentIndex(escolhida)
        self.c_aba.blockSignals(False)
        if not self.e_saida.text():
            p = Path(caminho)
            self.e_saida.setText(str(p.with_name(p.stem + "-Ipe.xlsx")))
        return self.carregar_aba()

    def carregar_aba(self) -> bool:
        caminho = self.e_arquivo.text()
        if not caminho:
            return False
        aba = self.c_aba.currentText() if L.abas(caminho) else None
        try:
            self.dados = L.ler_planilha(caminho, aba)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, self.windowTitle(), f"Não deu para ler a aba:\n{e}")
            self.dados = []
            return False
        cab = self.dados[0] if self.dados else []
        achadas = L.achar_colunas(cab)
        for combo, chave, opcional in ((self.c_id, "id", False), (self.c_data, "data", False),
                                       (self.c_nasc, "nascimento", True)):
            combo.clear()
            if opcional:
                combo.addItem("(não conferir)", -1)
            for i, t in enumerate(cab):
                combo.addItem(str(t if t not in (None, "") else f"coluna {i + 1}"), i)
            combo.setCurrentIndex(max(0, combo.findData(achadas[chave])))
        self._conferir()
        return True

    def colunas(self) -> dict:
        return {"id": self.c_id.currentData() if self.c_id.count() else -1,
                "data": self.c_data.currentData() if self.c_data.count() else -1,
                "nascimento": self.c_nasc.currentData() if self.c_nasc.count() else -1, "nome": -1}

    def linhas(self) -> list[L.Linha]:
        return L.montar_linhas(self.dados[1:], self.colunas()) if len(self.dados) > 1 else []

    def _conferir(self) -> None:
        ls = self.linhas()
        if not ls:
            self.l_lista.setText("")
            return
        validas = [l for l in ls if l.pid and l.data]
        self.l_lista.setText(tr(f"Na aba: {len(ls)} linhas; {len(validas)} com ID e data.") + " " + tr(
            "Cada mamografia leva de meio minuto a alguns minutos (download e as duas redes): uma lista grande "
            "roda por horas ou dias. Pode parar e continuar depois, com a mesma planilha de saída."))

    def escolher_saida(self) -> None:
        caminho, _f = QFileDialog.getSaveFileName(self, "Planilha de saída", self.e_saida.text(), "Excel (*.xlsx)")
        if caminho:
            self.e_saida.setText(caminho if caminho.lower().endswith(".xlsx") else caminho + ".xlsx")

    def abrir_pasta(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        if self.e_saida.text():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.e_saida.text()).parent)))

    # ------------------------------------------------------------------ rodar
    def montar(self) -> L.Lote | None:
        """Confere as escolhas e devolve o lote pronto (None, com o aviso, se falta algo)."""
        titulo = self.windowTitle()
        ok, motivo = LI.pronto_para_medir(self.repo)
        if not ok:
            QMessageBox.warning(self, titulo, motivo)
            return None
        ls = self.linhas()
        if not [l for l in ls if l.pid and l.data]:
            QMessageBox.information(self, titulo, "Escolha a planilha e as colunas do ID e da data da mamografia.")
            return None
        no = self.no()
        if no is None:
            QMessageBox.information(self, titulo, "Escolha o PACS (um nó DICOM ativo, em Configurações ▸ Rede).")
            return None
        saida = self.e_saida.text().strip()
        if not saida:
            QMessageBox.information(self, titulo, "Escolha onde gravar a planilha de saída.")
            return None
        if Path(saida).resolve() == Path(self.e_arquivo.text()).resolve():
            QMessageBox.warning(self, titulo, "A planilha de saída não pode ser a mesma da lista.")
            return None
        ident = self.repo.identity(self.c_ident.currentData()) if self.c_ident.currentData() else None
        serv = LI.servicos(self.repo, self.net, self.settings, no, ident, self.storage_root, self.fila)
        op = L.Opcoes(apagar_depois=self.k_apagar.isChecked(), refazer_erros=self.k_refazer.isChecked(),
                      limite=self.s_limite.value())
        return L.Lote(self.dados[0], self.dados[1:], ls, serv, saida, op)

    def iniciar(self) -> None:
        if self.linha_de_fundo is not None and self.linha_de_fundo.is_alive():
            return
        lote = self.montar()
        if lote is None:
            return
        falta = len(lote.por_fazer_sem_limite())
        total = len({l.chave for l in lote.linhas})
        if not falta:
            lote.gravar_planilha()
            QMessageBox.information(self, self.windowTitle(), "Todas as linhas desta lista já têm resposta nessa "
                                    "planilha de saída. Ela foi gravada de novo.")
            return
        self.lote = lote
        self.parar.clear()
        self.barra.setRange(0, total)
        self.barra.setValue(total - falta)
        if total - falta:
            self.diario.appendPlainText(tr(f"Continuando: {total - falta} de {total} já feitas."))
        self._ocupado(True)
        try:
            self.repo.audit("pesquisa", f"lote da mama: {falta} linhas, {self.c_no.currentText()}")
        except Exception:  # noqa: BLE001
            log.debug("registro do lote", exc_info=True)

        def rodar():
            erro = ""
            a = None
            try:
                a = lote.rodar(self.parar, lambda a, l, r: self.sinais.linha.emit(a, l, r))
            except Exception as e:  # noqa: BLE001
                log.exception("lote da mama")
                erro = str(e)
            self.sinais.fim.emit(a, erro)
        self.linha_de_fundo = threading.Thread(target=rodar, name="lote-mama", daemon=True)
        self.linha_de_fundo.start()

    def pedir_parada(self) -> None:
        self.parar.set()
        self.b_parar.setEnabled(False)
        self.l_estado.setText("Parando no fim desta mamografia…")

    def _ocupado(self, on: bool) -> None:
        self.b_iniciar.setEnabled(not on)
        self.b_parar.setEnabled(on)
        for w in (self.c_aba, self.c_id, self.c_data, self.c_nasc, self.c_no, self.c_ident, self.e_saida,
                  self.k_apagar, self.k_refazer, self.s_limite):
            w.setEnabled(not on)

    @staticmethod
    def _contagem(c: dict) -> str:
        return " · ".join(f"{tr(k)}: {v}" for k, v in sorted(c.items(), key=lambda kv: -kv[1]))

    def _andou(self, a, linha, r) -> None:
        self.barra.setValue(a.feitos)
        falta = duracao(a.falta_s())
        self.l_estado.setText(tr(f"{a.feitos} de {a.total}") + (" · " + tr(f"faltam cerca de {falta}") if falta else "")
                              + "\n" + self._contagem(a.contagem))
        resumo = tr(r.get("situacao", ""))
        if r.get("situacao") == L.MEDIDO:
            resumo += " — " + tr("densidade") + " " + (r.get("densidade") or "?") + ", BAC " + tr(r.get("bac_grau") or "?")
            if r.get("bac_area") is not None:
                resumo += " (" + str(r["bac_area"]) + " mm²)"
        elif r.get("observacao") and r.get("situacao") not in (L.NAO_ACHADO,):
            resumo += f" — {r['observacao']}"
        self.diario.appendPlainText(tr(f"Linha {linha.n + 2}") + f": {resumo}")

    def _acabou(self, a, erro: str) -> None:
        self._ocupado(False)
        self.linha_de_fundo = None
        if erro:
            self.l_estado.setText(tr(f"O lote parou com erro: {erro}"))
            return
        fim = "Parado." if self.parar.is_set() else "Terminado."
        saida = self.lote.saida if self.lote else ""
        self.l_estado.setText(tr(fim) + " " + tr(f"Planilha gravada em {saida}") + "\n" + self._contagem(a.contagem if a else {}))

    def closeEvent(self, e) -> None:
        if self.linha_de_fundo is not None and self.linha_de_fundo.is_alive():
            r = QMessageBox.question(self, self.windowTitle(), "O lote está rodando. Parar e fechar?\n"
                                     "O que já foi feito fica gravado; dá para continuar depois.")
            if r != QMessageBox.Yes:
                e.ignore()
                return
            self.parar.set()
            self.linha_de_fundo.join(timeout=20)
        e.accept()
