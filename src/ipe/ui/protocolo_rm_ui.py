"""Telas da conferência de protocolo de RM (0.100.93): a do exame, a das referências e a dos exames conferidos.

O cálculo mora em `ipe.imaging.protocolo_rm` (sem Qt)."""
from __future__ import annotations

import logging

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QProgressDialog,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ipe.core.i18n import tr
from ipe.imaging import protocolo_rm as PR
from ipe.ui.tabelas import colunas_ajustaveis

log = logging.getLogger(__name__)

COR = {"ok": None, "aviso": QColor(214, 160, 40), "erro": QColor(220, 80, 70), "falta": QColor(220, 80, 70)}
SITUACAO = {"ok": "ok", "aviso": "fora da tolerância", "erro": "divergente", "falta": "falta"}
ESTADO = {"conforme": "conforme", "avisos": "com avisos", "divergente": "divergente",
          "sem_referencia": "sem referência", "sem_rm": "sem RM"}


def _item(txt, cor: QColor | None = None, dado=None) -> QTableWidgetItem:
    it = QTableWidgetItem("" if txt is None else str(txt))
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    if cor is not None:
        it.setForeground(QBrush(cor))
    if dado is not None:
        it.setData(Qt.UserRole, dado)
    return it


def _fmt(v) -> str:
    if v is None or v == "":
        return "—"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def _difs_texto(difs: list[dict]) -> str:
    partes = []
    for d in difs:
        tol = f" {d['tolerancia']}" if d.get("tolerancia") else ""
        partes.append(f"{tr(PR.NOMES.get(d['param'], d['param']))}: {_fmt(d['valor'])} "
                      f"({tr('esperado')} {_fmt(d['esperado'])}{tol})")
    return " · ".join(partes)


# ------------------------------------------------------------------ o exame
class ConferenciaDialog(QDialog):
    """A conferência de um exame: referência, cada série esperada (achada? parâmetros fora?) e as séries a mais."""

    def __init__(self, repo, settings, study_uid: str, parent=None):
        super().__init__(parent)
        self.repo, self.settings, self.study_uid = repo, settings, study_uid
        self.setWindowTitle(tr("Conferência do protocolo de RM"))
        self.resize(1100, 620)
        self.exame: dict | None = None
        self.resultado: dict | None = None
        lay = QVBoxLayout(self)
        self.l_exame = QLabel()
        self.l_exame.setWordWrap(True)
        lay.addWidget(self.l_exame)
        linha = QHBoxLayout()
        linha.addWidget(QLabel(tr("Referência:")))
        self.c_ref = QComboBox()
        self.c_ref.setMinimumWidth(360)
        self.c_ref.activated.connect(lambda _i: self.conferir(self.c_ref.currentData()))
        linha.addWidget(self.c_ref, 1)
        lay.addLayout(linha)
        self.l_estado = QLabel()
        lay.addWidget(self.l_estado)
        self.tabela = QTableWidget(0, 4)
        self.tabela.setHorizontalHeaderLabels([tr("Série esperada"), tr("Série do exame"), tr("Situação"),
                                               tr("O que mudou")])
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setWordWrap(True)
        colunas_ajustaveis(self.tabela)
        for i, w in enumerate((200, 200, 140)):
            self.tabela.setColumnWidth(i, w)
        lay.addWidget(self.tabela, 1)
        self.l_extras = QLabel()
        self.l_extras.setWordWrap(True)
        lay.addWidget(self.l_extras)
        bts = QHBoxLayout()
        for txt, fn in ((tr("Conferir de novo"), lambda: self.carregar(True)),
                        (tr("Usar este exame como referência…"), self.usar_como_referencia),
                        (tr("Protocolos de RM…"), self.abrir_protocolos),
                        (tr("Exportar CSV…"), self.exportar)):
            b = QPushButton(txt)
            b.clicked.connect(fn)
            bts.addWidget(b)
        bts.addStretch(1)
        fechar = QPushButton(tr("Fechar"))
        fechar.clicked.connect(self.accept)
        bts.addWidget(fechar)
        lay.addLayout(bts)
        self.carregar(False)

    # --------------------------------------------------------------
    def carregar(self, de_novo: bool) -> None:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.exame = PR.series_do_exame(self.repo, self.study_uid)
        finally:
            QApplication.restoreOverrideCursor()
        ex = self.exame
        self.l_exame.setText(f"<b>{ex['descricao'] or '—'}</b> · {tr('aparelho')}: {ex['aparelho'] or '—'} · "
                             + tr("{} série(s) de aquisição").format(len(ex["series"])))
        refs = [r for r in PR.referencias(self.settings) if r.exame == ex["exame"] or not r.exame]
        outras = [r for r in PR.referencias(self.settings) if r not in refs]
        escolhida = PR.escolher_referencia(ex, refs)
        self.c_ref.clear()
        self.c_ref.addItem(tr("(nenhuma)"), None)
        for r in refs + outras:
            rotulo = r.nome + (f" · {r.aparelho}" if r.aparelho and r.aparelho not in r.nome else "")
            self.c_ref.addItem(rotulo, r.id)
        if escolhida is not None:
            self.c_ref.setCurrentIndex(max(0, self.c_ref.findData(escolhida.id)))
        self.conferir(escolhida.id if escolhida else None)

    def _ref(self, rid):
        return next((r for r in PR.referencias(self.settings) if r.id == rid), None)

    def conferir(self, rid) -> None:
        if self.exame is None:
            return
        if not self.exame["series"]:
            self.l_estado.setText(tr("Este exame não tem séries de aquisição de RM."))
            self.tabela.setRowCount(0)
            return
        ref = self._ref(rid)
        r = PR.conferir(self.exame, ref)
        r["study_uid"] = self.study_uid
        self.resultado = r
        if ref is not None:
            PR.guardar(self.repo, self.study_uid, r)
        self.mostrar(r)

    def mostrar(self, r: dict) -> None:
        cor = {"conforme": "#3a9d5d", "avisos": "#d6a028", "divergente": "#dc5046"}.get(r["estado"], "#9a9a9a")
        txt = PR.MARCAS.get(r["estado"], "") + " " + tr(ESTADO.get(r["estado"], r["estado"]))
        if r["estado"] not in ("conforme", "sem_referencia"):
            txt += " — " + ", ".join(tr(p) for p in r.get("resumo", "").split(", "))
        if r["estado"] == "sem_referencia":
            txt += " — " + tr("escolha uma referência acima, ou use este exame como referência")
        self.l_estado.setText(f"<span style='color:{cor};font-size:15px'><b>{txt}</b></span>")
        linhas = r.get("series", [])
        self.tabela.setRowCount(len(linhas))
        for i, s in enumerate(linhas):
            c = COR.get(s["situacao"])
            if s["situacao"] == "falta" and not s.get("obrigatoria", True):
                c = COR["aviso"]                    # a opcional que falta é aviso, não divergência
            esp = s["descricao"] + ("" if s.get("obrigatoria", True) else " " + tr("(opcional)"))
            achada = s.get("achada") or "—"
            if s.get("nota"):
                achada += f" ({tr(s['nota']) if 'repetida' not in s['nota'] else tr('repetida {}×').format(s['repeticoes'])})"
            self.tabela.setItem(i, 0, _item(esp))
            self.tabela.setItem(i, 1, _item(achada, dado=s.get("uid")))
            self.tabela.setItem(i, 2, _item(tr(SITUACAO.get(s["situacao"], s["situacao"])), c))
            self.tabela.setItem(i, 3, _item(_difs_texto(s.get("difs", [])), c))
        self.tabela.resizeRowsToContents()
        ex = r.get("extras", [])
        self.l_extras.setText((tr("Séries a mais (não estão na referência):") + " " +
                               ", ".join(x["descricao"] for x in ex)) if ex else "")

    # --------------------------------------------------------------
    def usar_como_referencia(self) -> None:
        if not self.exame or not self.exame["series"]:
            return
        nome, ok = QInputDialog.getText(self, tr("Usar este exame como referência"), tr("Nome do protocolo:"),
                                        text=f"{self.exame['descricao']} · {self.exame['aparelho']}".strip(" ·"))
        if not ok or not nome.strip():
            return
        caixa = QMessageBox(self)
        caixa.setWindowTitle(tr("Usar este exame como referência"))
        caixa.setText(tr("Vale só para este aparelho ({}) ou para qualquer aparelho?").format(
            self.exame["aparelho"] or "?"))
        b_este = caixa.addButton(tr("Só este aparelho"), QMessageBox.AcceptRole)
        caixa.addButton(tr("Qualquer aparelho"), QMessageBox.ActionRole)
        caixa.addButton(tr("Cancelar"), QMessageBox.RejectRole)
        caixa.exec()
        if caixa.buttonRole(caixa.clickedButton()) == QMessageBox.RejectRole:
            return
        ref = PR.referencia_do_exame(self.exame, nome.strip(), por_aparelho=caixa.clickedButton() is b_este)
        refs = PR.referencias(self.settings) + [ref]
        PR.gravar_referencias(self.settings, refs)
        self.carregar(True)

    def abrir_protocolos(self) -> None:
        ProtocolosDialog(self.repo, self.settings, self).exec()
        self.carregar(True)

    def exportar(self) -> None:
        if not self.resultado:
            return
        caminho, _ = QFileDialog.getSaveFileName(self, tr("Exportar CSV…"), "protocolo_rm.csv", "CSV (*.csv)")
        if caminho:
            r = dict(self.resultado, data=(self.exame or {}).get("data", ""))
            with open(caminho, "w", encoding="utf-8-sig") as f:
                f.write(PR.para_csv([r]))


# ------------------------------------------------------------------ editar uma referência
class EditarReferenciaDialog(QDialog):
    """Nome, exame, aparelho, as séries (obrigatória, valores) e as tolerâncias desta referência."""

    def __init__(self, ref: PR.Referencia, parent=None):
        super().__init__(parent)
        self.ref = ref
        self.setWindowTitle(tr("Protocolo de RM: {}").format(ref.nome))
        self.resize(1250, 640)
        lay = QVBoxLayout(self)
        f = QFormLayout()
        self.e_nome = QLineEdit(ref.nome)
        self.e_exame = QLineEdit(ref.exame)
        self.e_exame.setToolTip(tr("A descrição do estudo, como o Ipê a compara (minúsculas, sem acento). Vazio = "
                                   "qualquer exame."))
        self.e_aparelho = QLineEdit(ref.aparelho)
        self.e_aparelho.setPlaceholderText(tr("qualquer aparelho"))
        f.addRow(tr("Nome:"), self.e_nome)
        f.addRow(tr("Exame (descrição do estudo):"), self.e_exame)
        f.addRow(tr("Aparelho (estação):"), self.e_aparelho)
        lay.addLayout(f)
        abas = QTabWidget()
        lay.addWidget(abas, 1)
        # séries
        w = QWidget()
        wl = QVBoxLayout(w)
        self.t_series = QTableWidget(len(ref.series), 2 + len(PR.ORDEM))
        self.t_series.setHorizontalHeaderLabels([tr("Obrigatória"), tr("Série")] +
                                                [tr(PR.NOMES[p]) for p in PR.ORDEM])
        self.t_series.verticalHeader().setVisible(False)
        for i, s in enumerate(ref.series):
            ck = QTableWidgetItem()
            ck.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            ck.setCheckState(Qt.Checked if s.get("obrigatoria", True) else Qt.Unchecked)
            self.t_series.setItem(i, 0, ck)
            self.t_series.setItem(i, 1, QTableWidgetItem(s.get("descricao", "")))
            for j, p in enumerate(PR.ORDEM):
                v = s.get("params", {}).get(p)
                self.t_series.setItem(i, 2 + j, QTableWidgetItem("" if v is None else _fmt(v)))
        colunas_ajustaveis(self.t_series, estica_ultima=False)
        wl.addWidget(self.t_series, 1)
        b_tira = QPushButton(tr("Tirar a série selecionada"))
        b_tira.clicked.connect(lambda: [self.t_series.removeRow(r) for r in
                                        sorted({i.row() for i in self.t_series.selectedIndexes()}, reverse=True)])
        wl.addWidget(b_tira, 0, Qt.AlignLeft)
        wl.addWidget(QLabel(tr("Valor vazio = não confere esse parâmetro nesta série.")))
        abas.addTab(w, tr("Séries esperadas"))
        # tolerâncias
        w2 = QWidget()
        wl2 = QVBoxLayout(w2)
        self.t_tol = QTableWidget(len(PR.ORDEM), 3)
        self.t_tol.setHorizontalHeaderLabels([tr("Parâmetro"), tr("Como compara"), tr("Tolerância")])
        self.t_tol.verticalHeader().setVisible(False)
        self._tipos = []
        for i, p in enumerate(PR.ORDEM):
            tipo, lim = ref.tolerancia(p)
            self.t_tol.setItem(i, 0, _item(tr(PR.NOMES[p])))
            c = QComboBox()
            for k, nome in (("rel", "relativa (%)"), ("abs", "absoluta"), ("igual", "igual"),
                            ("info", "só mostrar")):
                c.addItem(tr(nome), k)
            c.setCurrentIndex(max(0, c.findData(tipo)))
            self.t_tol.setCellWidget(i, 1, c)
            self._tipos.append(c)
            self.t_tol.setItem(i, 2, QTableWidgetItem("" if lim is None else f"{lim:g}"))
        colunas_ajustaveis(self.t_tol)
        wl2.addWidget(self.t_tol, 1)
        wl2.addWidget(QLabel(tr("Plano, 2D/3D, campo, sequência, valores de b e contraste fora do esperado contam como "
                                "divergência; o resto, como aviso.")))
        abas.addTab(w2, tr("Tolerâncias"))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    @staticmethod
    def _valor(txt: str):
        t = (txt or "").strip()
        if not t or t == "—":
            return None
        try:
            return float(t)
        except ValueError:
            return t

    def resultado(self) -> PR.Referencia:
        series = []
        for i in range(self.t_series.rowCount()):
            desc = self.t_series.item(i, 1).text() if self.t_series.item(i, 1) else ""
            params = {}
            for j, p in enumerate(PR.ORDEM):
                it = self.t_series.item(i, 2 + j)
                params[p] = self._valor(it.text() if it else "")
            antigo = next((s for s in self.ref.series if s.get("descricao") == desc), {})
            series.append({"nome": antigo.get("nome") or PR.normalizar(desc), "descricao": desc,
                           "obrigatoria": self.t_series.item(i, 0).checkState() == Qt.Checked, "params": params})
        tol = {}
        for i, p in enumerate(PR.ORDEM):
            tipo = self._tipos[i].currentData()
            v = self._valor(self.t_tol.item(i, 2).text() if self.t_tol.item(i, 2) else "")
            par = [tipo, v if isinstance(v, float) else None]
            if tuple(par) != PR.TOLERANCIAS.get(p):
                tol[p] = par
        return PR.Referencia(nome=self.e_nome.text().strip() or self.ref.nome,
                             exame=PR.normalizar(self.e_exame.text()), aparelho=self.e_aparelho.text().strip(),
                             series=series, tolerancias=tol, origem=self.ref.origem, criado=self.ref.criado,
                             id=self.ref.id)


# ------------------------------------------------------------------ as referências e os exames conferidos
def _exames_rm(repo, de: str, ate: str, limite: int = 5000) -> list:
    return [r for r in repo.search_studies(date_from=de, date_to=ate, limit=limite)
            if "MR" in str(r.modalities or "").upper()]


def _estacao(row) -> str:
    return (str(getattr(row, "station", "") or "").split("; ")[0]
            or str(getattr(row, "device", "") or "").split("; ")[0])


class ProtocolosDialog(QDialog):
    """Rede ▸ Conferência de protocolos de RM: as referências (criar pelo acervo, editar) e os exames conferidos."""

    def __init__(self, repo, settings, parent=None):
        super().__init__(parent)
        self.repo, self.settings = repo, settings
        self.setWindowTitle(tr("Conferência de protocolos de RM"))
        self.resize(1150, 640)
        lay = QVBoxLayout(self)
        self.abas = QTabWidget()
        lay.addWidget(self.abas, 1)
        # --- referências
        w = QWidget()
        wl = QVBoxLayout(w)
        expl = QLabel(tr("Cada RM que chega é conferida contra o protocolo de referência do mesmo exame (e do mesmo "
                         "aparelho, quando houver): séries que faltam, plano, sequência, TR, TE, espessura, matriz, "
                         "FOV, valores de b… O resultado aparece na coluna “Protocolo (RM)” do banco."))
        expl.setWordWrap(True)
        wl.addWidget(expl)
        self.k_ligado = QCheckBox(tr("Conferir sozinho as RM que chegam (recebidas, baixadas e importadas)"))
        self.k_ligado.setChecked(PR.ligado(settings))
        self.k_ligado.toggled.connect(self._ligar)
        wl.addWidget(self.k_ligado)
        self.t_refs = QTableWidget(0, 6)
        self.t_refs.setHorizontalHeaderLabels([tr("Nome"), tr("Exame"), tr("Aparelho"), tr("Séries"), tr("Origem"),
                                               tr("Criado")])
        self.t_refs.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.t_refs.verticalHeader().setVisible(False)
        self.t_refs.doubleClicked.connect(lambda *_: self.editar())
        colunas_ajustaveis(self.t_refs)
        wl.addWidget(self.t_refs, 1)
        bts = QHBoxLayout()
        for txt, fn, tip in (
                (tr("Criar pelo acervo…"), self.criar_pelo_acervo,
                 tr("O protocolo dominante dos exames do mesmo tipo e aparelho já guardados no banco")),
                (tr("Criar todas pelo acervo"), self.criar_todas,
                 tr("Um protocolo para cada exame de RM × aparelho com exames suficientes no banco")),
                (tr("Editar…"), self.editar, ""), (tr("Duplicar"), self.duplicar, ""),
                (tr("Excluir"), self.excluir, "")):
            b = QPushButton(txt)
            if tip:
                b.setToolTip(tip)
            b.clicked.connect(fn)
            bts.addWidget(b)
        bts.addStretch(1)
        wl.addLayout(bts)
        self.abas.addTab(w, tr("Protocolos de referência"))
        # --- exames conferidos
        w2 = QWidget()
        wl2 = QVBoxLayout(w2)
        filtro = QHBoxLayout()
        self.d_de = QDateEdit(QDate.currentDate().addDays(-7))
        self.d_ate = QDateEdit(QDate.currentDate())
        for d in (self.d_de, self.d_ate):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd/MM/yyyy")
        filtro.addWidget(QLabel(tr("De")))
        filtro.addWidget(self.d_de)
        filtro.addWidget(QLabel(tr("até")))
        filtro.addWidget(self.d_ate)
        self.k_so_fora = QCheckBox(tr("Só os fora do padrão"))
        self.k_so_fora.toggled.connect(self.listar)
        filtro.addWidget(self.k_so_fora)
        b_listar = QPushButton(tr("Atualizar"))
        b_listar.clicked.connect(self.listar)
        filtro.addWidget(b_listar)
        b_conf = QPushButton(tr("Conferir o período"))
        b_conf.setToolTip(tr("Confere de novo todas as RM do período (só lê os cabeçalhos)"))
        b_conf.clicked.connect(self.conferir_periodo)
        filtro.addWidget(b_conf)
        b_csv = QPushButton(tr("Exportar CSV…"))
        b_csv.clicked.connect(self.exportar)
        filtro.addWidget(b_csv)
        filtro.addStretch(1)
        wl2.addLayout(filtro)
        self.l_soma = QLabel()
        wl2.addWidget(self.l_soma)
        self.t_ex = QTableWidget(0, 6)
        self.t_ex.setHorizontalHeaderLabels([tr("Data"), tr("Paciente"), tr("Exame"), tr("Aparelho"),
                                             tr("Referência"), tr("Resultado")])
        self.t_ex.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.t_ex.verticalHeader().setVisible(False)
        self.t_ex.setSortingEnabled(True)
        self.t_ex.doubleClicked.connect(self._abrir_conferencia)
        colunas_ajustaveis(self.t_ex)
        wl2.addWidget(self.t_ex, 1)
        self.abas.addTab(w2, tr("Exames conferidos"))
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Close).clicked.connect(self.accept)
        lay.addWidget(bb)
        self.linhas: list[dict] = []
        self.mostrar_refs()

    # ---------------------------------------------------------- referências
    def _ligar(self, on: bool) -> None:
        self.settings.set(PR.CHAVE_LIGADO, bool(on))
        self.settings.save()

    def mostrar_refs(self) -> None:
        refs = PR.referencias(self.settings)
        self.t_refs.setRowCount(len(refs))
        for i, r in enumerate(refs):
            self.t_refs.setItem(i, 0, _item(r.nome, dado=r.id))
            self.t_refs.setItem(i, 1, _item(r.exame or tr("qualquer")))
            self.t_refs.setItem(i, 2, _item(r.aparelho or tr("qualquer")))
            obr = sum(1 for s in r.series if s.get("obrigatoria", True))
            self.t_refs.setItem(i, 3, _item(tr("{} ({} obrigatória(s))").format(len(r.series), obr)))
            self.t_refs.setItem(i, 4, _item(r.origem))
            self.t_refs.setItem(i, 5, _item(r.criado))

    def _selecionada(self) -> PR.Referencia | None:
        linhas = sorted({i.row() for i in self.t_refs.selectedIndexes()})
        if not linhas:
            return None
        rid = self.t_refs.item(linhas[0], 0).data(Qt.UserRole)
        return next((r for r in PR.referencias(self.settings) if r.id == rid), None)

    def editar(self) -> None:
        ref = self._selecionada()
        if ref is None:
            return
        d = EditarReferenciaDialog(ref, self)
        if d.exec():
            nova = d.resultado()
            PR.gravar_referencias(self.settings, [nova if r.id == ref.id else r for r in PR.referencias(self.settings)])
            self.mostrar_refs()

    def duplicar(self) -> None:
        ref = self._selecionada()
        if ref is None:
            return
        import copy
        nova = copy.deepcopy(ref)
        nova.id = PR._novo_id()
        nova.nome = ref.nome + " " + tr("(cópia)")
        PR.gravar_referencias(self.settings, PR.referencias(self.settings) + [nova])
        self.mostrar_refs()

    def excluir(self) -> None:
        ref = self._selecionada()
        if ref is None:
            return
        if QMessageBox.question(self, tr("Excluir"), tr("Excluir o protocolo “{}”?").format(ref.nome)) \
                != QMessageBox.Yes:
            return
        PR.gravar_referencias(self.settings, [r for r in PR.referencias(self.settings) if r.id != ref.id])
        self.mostrar_refs()

    def _grupos(self, meses: int, minimo: int) -> dict:
        de = QDate.currentDate().addMonths(-meses).toString("yyyyMMdd")
        g: dict[tuple[str, str], list] = {}
        for r in _exames_rm(self.repo, de, ""):
            ex = PR.normalizar(r.description)
            if ex:
                g.setdefault((ex, _estacao(r)), []).append(r)
        return {k: v for k, v in g.items() if len(v) >= minimo}

    def _ler_exames(self, rows: list, titulo: str) -> list[dict] | None:
        prog = QProgressDialog(titulo, tr("Cancelar"), 0, len(rows), self)
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(300)
        exames = []
        for i, r in enumerate(rows):
            prog.setValue(i)
            QApplication.processEvents()
            if prog.wasCanceled():
                return None
            try:
                exames.append(PR.series_do_exame(self.repo, r.study_uid))
            except Exception:  # noqa: BLE001
                log.warning("protocolo: não li %s", r.study_uid, exc_info=True)
        prog.setValue(len(rows))
        return exames

    def _parametros_do_acervo(self) -> tuple[int, int, int] | None:
        d = QDialog(self)
        d.setWindowTitle(tr("Criar pelo acervo"))
        f = QFormLayout(d)
        s_meses = QSpinBox(minimum=1, maximum=60, value=6, suffix=" " + tr("mês(es)"))
        s_min = QSpinBox(minimum=2, maximum=200, value=5)
        s_max = QSpinBox(minimum=3, maximum=500, value=20)
        f.addRow(tr("Exames dos últimos:"), s_meses)
        f.addRow(tr("Mínimo de exames por protocolo:"), s_min)
        f.addRow(tr("Exames lidos por protocolo (os mais recentes):"), s_max)
        f.addRow(QLabel(tr("Série em ≥ 80% dos exames: obrigatória; em ≥ 50%: opcional. Números: a mediana; o "
                           "resto: o valor mais comum.")))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        f.addRow(bb)
        if not d.exec():
            return None
        return s_meses.value(), s_min.value(), s_max.value()

    def criar_pelo_acervo(self) -> None:
        par = self._parametros_do_acervo()
        if par is None:
            return
        meses, minimo, maximo = par
        grupos = self._grupos(meses, minimo)
        if not grupos:
            QMessageBox.information(self, tr("Criar pelo acervo"),
                                    tr("Nenhum exame de RM com pelo menos {} exames no período.").format(minimo))
            return
        chaves = sorted(grupos, key=lambda k: -len(grupos[k]))
        rotulos = [f"{grupos[k][0].description} · {k[1] or '?'} ({len(grupos[k])})" for k in chaves]
        esc, ok = QInputDialog.getItem(self, tr("Criar pelo acervo"), tr("Exame e aparelho:"), rotulos, 0, False)
        if not ok:
            return
        k = chaves[rotulos.index(esc)]
        self._criar([k], grupos, maximo)

    def criar_todas(self) -> None:
        par = self._parametros_do_acervo()
        if par is None:
            return
        meses, minimo, maximo = par
        grupos = self._grupos(meses, minimo)
        existentes = {(r.exame, r.aparelho) for r in PR.referencias(self.settings)}
        novos = [k for k in grupos if k not in existentes]
        if not novos:
            QMessageBox.information(self, tr("Criar todas pelo acervo"),
                                    tr("Nada novo: os exames com pelo menos {} exames já têm protocolo.").format(minimo))
            return
        self._criar(sorted(novos, key=lambda k: -len(grupos[k])), grupos, maximo)

    def _criar(self, chaves: list, grupos: dict, maximo: int) -> None:
        refs = PR.referencias(self.settings)
        feitas = 0
        for n, k in enumerate(chaves):
            rows = sorted(grupos[k], key=lambda r: (r.study_date or "", r.study_time or ""), reverse=True)[:maximo]
            exames = self._ler_exames(rows, tr("Lendo os exames ({} de {})…").format(n + 1, len(chaves)))
            if exames is None:
                break
            # o aparelho do cabeçalho manda; exames de outro aparelho no mesmo grupo (estação vazia) ficam de fora
            ap = max(set(e["aparelho"] for e in exames), key=[e["aparelho"] for e in exames].count) if exames else ""
            ref = PR.referencia_pelo_acervo([e for e in exames if e["aparelho"] == ap])
            if ref is not None and ref.series:
                refs = [r for r in refs if (r.exame, r.aparelho) != (ref.exame, ref.aparelho)] + [ref]
                feitas += 1
        PR.gravar_referencias(self.settings, refs)
        self.mostrar_refs()
        QMessageBox.information(self, tr("Criar pelo acervo"), tr("{} protocolo(s) criado(s).").format(feitas))

    # ---------------------------------------------------------- exames conferidos
    def _periodo(self) -> tuple[str, str]:
        return self.d_de.date().toString("yyyyMMdd"), self.d_ate.date().toString("yyyyMMdd")

    def listar(self) -> None:
        de, ate = self._periodo()
        self.linhas = []
        for r in _exames_rm(self.repo, de, ate):
            g = PR.guardado(self.repo, r.study_uid)
            if g is None:
                continue
            self.linhas.append(dict(g, data=r.study_date, paciente=r.patient_name, study_uid=r.study_uid,
                                    descricao_estudo=r.description))
        self._mostrar_linhas()

    def _mostrar_linhas(self) -> None:
        so_fora = self.k_so_fora.isChecked()
        linhas = [x for x in self.linhas if not so_fora or x.get("estado") in ("divergente", "avisos")]
        self.t_ex.setSortingEnabled(False)
        self.t_ex.setRowCount(len(linhas))
        for i, x in enumerate(linhas):
            d = x.get("data", "") or ""
            cor = COR.get({"divergente": "erro", "avisos": "aviso"}.get(x.get("estado"), "ok"))
            self.t_ex.setItem(i, 0, _item(f"{d[6:8]}/{d[4:6]}/{d[:4]}" if len(d) == 8 else d, dado=x["study_uid"]))
            self.t_ex.setItem(i, 1, _item(x.get("paciente", "")))
            self.t_ex.setItem(i, 2, _item(x.get("descricao_estudo") or x.get("exame", "")))
            self.t_ex.setItem(i, 3, _item(x.get("aparelho", "")))
            self.t_ex.setItem(i, 4, _item(x.get("referencia", "")))
            res = PR.MARCAS.get(x.get("estado"), "") + " " + ", ".join(tr(p) for p in
                                                                       (x.get("resumo") or "").split(", "))
            self.t_ex.setItem(i, 5, _item(res.strip(), cor))
        self.t_ex.setSortingEnabled(True)
        n = len(self.linhas)
        fora = sum(1 for x in self.linhas if x.get("estado") == "divergente")
        av = sum(1 for x in self.linhas if x.get("estado") == "avisos")
        self.l_soma.setText(tr("{} exame(s) conferido(s) no período: {} conforme(s), {} com avisos, {} "
                               "divergente(s).").format(n, n - fora - av, av, fora))

    def conferir_periodo(self) -> None:
        if not PR.referencias(self.settings):
            QMessageBox.information(self, tr("Conferir o período"),
                                    tr("Cadastre os protocolos de referência primeiro (aba Protocolos de referência)."))
            return
        de, ate = self._periodo()
        rows = _exames_rm(self.repo, de, ate)
        prog = QProgressDialog(tr("Conferindo as RM do período…"), tr("Cancelar"), 0, len(rows), self)
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(300)
        for i, r in enumerate(rows):
            prog.setValue(i)
            QApplication.processEvents()
            if prog.wasCanceled():
                break
            try:
                PR.conferir_exame(self.repo, self.settings, r.study_uid)
            except Exception:  # noqa: BLE001
                log.warning("protocolo: %s", r.study_uid, exc_info=True)
        prog.setValue(len(rows))
        self.listar()

    def _abrir_conferencia(self, idx) -> None:
        uid = self.t_ex.item(idx.row(), 0).data(Qt.UserRole)
        if uid:
            ConferenciaDialog(self.repo, self.settings, uid, self).exec()
            self.listar()

    def exportar(self) -> None:
        if not self.linhas:
            self.listar()
        caminho, _ = QFileDialog.getSaveFileName(self, tr("Exportar CSV…"), "protocolos_rm.csv", "CSV (*.csv)")
        if caminho:
            with open(caminho, "w", encoding="utf-8-sig") as f:
                f.write(PR.para_csv(self.linhas))


def abrir_do_exame(repo, settings, study_uid: str, parent=None) -> ConferenciaDialog:
    d = ConferenciaDialog(repo, settings, study_uid, parent)
    d.show()
    return d
