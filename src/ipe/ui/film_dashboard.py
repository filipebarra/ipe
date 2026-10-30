"""Painel de filmes e impressões (0.77): quantos filmes, quantos impressos, por quem e em quanto tempo.

As contas estão em `core.film_stats`; aqui só a tela. Os gráficos são desenhados à mão (QPainter):
o programa não leva biblioteca de gráficos, e duas barras não justificam uma.
"""
from __future__ import annotations

import csv
from datetime import date, datetime

from PySide6.QtCore import QDate, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QSpinBox, QTableWidget,
    QTableWidgetItem, QToolTip, QVBoxLayout, QWidget,
)

from ipe.core import film_stats as F
from ipe.ui.tabelas import colunas_ajustaveis

# cores dos dados (paleta categórica validada, passos do modo escuro); texto nunca na cor da série
COR_IMPRESSO = QColor("#3987e5")
COR_NAO = QColor("#d95926")
TINTA = QColor("#dcdcdc")
TINTA_2 = QColor("#9a9a9a")
GRADE = QColor("#3a3c41")
FUNDO_CARTAO = "#2a2c31"

PERIODOS = [("Últimos 30 dias", "30d"), ("Últimos 7 dias", "7d"), ("Hoje", "hoje"),
            ("Últimos 90 dias", "90d"), ("Últimos 12 meses", "12m"), ("Este ano", "ano"),
            ("Tudo", "tudo"), ("Escolher datas…", "datas")]

COLUNAS = ["Criado em", "Origem", "Criado por", "Paciente", "Modalidade", "Exame (data/hora)", "Descrição do exame",
           "Folhas", "Imagens", "Impresso", "Impresso em", "Impresso por", "Destino", "Vezes",
           "Exame → filme", "Filme → impressão", "Exame → impressão"]
COLUNAS_GRUPO = ["Filmes", "Impressos", "% impressos", "Exame → filme", "Filme → impressão",
                 "Folhas impressas", "Reimpressos"]


def _item(texto, direita: bool = False, ordem=None) -> QTableWidgetItem:
    it = QTableWidgetItem(str(texto))
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    if direita:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if ordem is not None:
        it.setData(Qt.UserRole, ordem)
    return it


class _ItemOrdenavel(QTableWidgetItem):
    """Ordena pelo valor guardado (horas, datas), não pelo texto "3,1 d"."""

    def __lt__(self, other):  # noqa: D105
        a, b = self.data(Qt.UserRole), other.data(Qt.UserRole)
        if a is None or b is None:
            return (a is None) > (b is None)
        return a < b


def _ord(texto, valor, direita: bool = True) -> QTableWidgetItem:
    it = _ItemOrdenavel(str(texto))
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    it.setData(Qt.UserRole, valor)
    if direita:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return it


def _data(d: datetime | None) -> str:
    return d.strftime("%d/%m/%Y %H:%M") if d else ""


# --------------------------------------------------------------------------- cartões
class Cartao(QFrame):
    """Um número grande com o rótulo em cima e o detalhe embaixo."""

    def __init__(self, rotulo: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"Cartao{{background:{FUNDO_CARTAO}; border-radius:6px}}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        self.l_rotulo = QLabel(rotulo)
        self.l_rotulo.setStyleSheet("color:#9a9a9a; font-size:11px")
        self.l_valor = QLabel("—")
        f = QFont()
        f.setPointSizeF(f.pointSizeF() * 1.9)
        f.setBold(True)
        self.l_valor.setFont(f)
        self.l_detalhe = QLabel("")
        self.l_detalhe.setStyleSheet("color:#9a9a9a; font-size:11px")
        self.l_detalhe.setWordWrap(True)
        for w in (self.l_rotulo, self.l_valor, self.l_detalhe):
            lay.addWidget(w)

    def mostrar(self, valor: str, detalhe: str = "", dica: str = "") -> None:
        self.l_valor.setText(valor)
        self.l_detalhe.setText(detalhe)
        self.setToolTip(dica)


# --------------------------------------------------------------------------- gráficos
class _Grafico(QWidget):
    """Base: área de desenho com margens e dica ao passar o mouse por cima de uma barra."""

    def __init__(self, titulo: str, parent=None):
        super().__init__(parent)
        self.titulo = titulo
        self.setMouseTracking(True)
        self.setMinimumHeight(220)
        self._alvos: list[tuple[QRectF, str]] = []

    def mouseMoveEvent(self, e):  # noqa: N802
        for r, dica in self._alvos:
            if r.contains(e.position()):
                QToolTip.showText(e.globalPosition().toPoint(), dica, self)
                return
        QToolTip.hideText()

    def _titulo(self, p: QPainter) -> float:
        p.setPen(TINTA)
        f = p.font()
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(4, 2, self.width() - 8, 20), Qt.AlignLeft | Qt.AlignVCenter, self.titulo)
        f.setBold(False)
        p.setFont(f)
        return 26.0

    @staticmethod
    def _barra(p: QPainter, r: QRectF, cor: QColor, topo_redondo: bool) -> None:
        """Barra com a ponta de dados arredondada (4 px) e a base reta, presa no eixo."""
        if r.height() <= 0 or r.width() <= 0:
            return
        raio = min(4.0, r.width() / 2, r.height())
        path = QPainterPath()
        if topo_redondo and raio > 0:
            path.moveTo(r.left(), r.bottom())
            path.lineTo(r.left(), r.top() + raio)
            path.quadTo(r.left(), r.top(), r.left() + raio, r.top())
            path.lineTo(r.right() - raio, r.top())
            path.quadTo(r.right(), r.top(), r.right(), r.top() + raio)
            path.lineTo(r.right(), r.bottom())
            path.closeSubpath()
        else:
            path.addRect(r)
        p.fillPath(path, cor)


class GraficoMeses(_Grafico):
    """Filmes por mês, empilhados: impressos embaixo, não impressos em cima."""

    def __init__(self, parent=None):
        super().__init__("Filmes por mês", parent)
        self.meses: list[tuple[str, int, int]] = []

    def definir(self, meses) -> None:
        self.meses = list(meses)[-12:]
        self.update()

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._alvos = []
        topo = self._titulo(p)
        # legenda (sempre: são duas séries), texto na tinta, a cor só no quadradinho
        x = 8.0
        y = topo
        for cor, nome in ((COR_IMPRESSO, "Impressos"), (COR_NAO, "Não impressos")):
            p.fillRect(QRectF(x, y + 4, 10, 10), cor)
            p.setPen(TINTA_2)
            p.drawText(QRectF(x + 14, y, 120, 18), Qt.AlignLeft | Qt.AlignVCenter, nome)
            x += 14 + p.fontMetrics().horizontalAdvance(nome) + 18
        topo += 24
        if not self.meses:
            p.setPen(TINTA_2)
            p.drawText(self.rect().adjusted(0, int(topo), 0, 0), Qt.AlignCenter, "Nenhum filme no período.")
            return
        base = self.height() - 22.0
        esq, dir_ = 34.0, self.width() - 8.0
        maximo = max(a + b for _m, a, b in self.meses) or 1
        alto = base - topo - 14
        # grade recessiva: três linhas
        p.setPen(QPen(GRADE, 1))
        for k in range(0, 4):
            v = maximo * k / 3
            yy = base - alto * k / 3
            p.drawLine(QPointF(esq, yy), QPointF(dir_, yy))
            p.setPen(TINTA_2)
            p.drawText(QRectF(0, yy - 8, esq - 4, 16), Qt.AlignRight | Qt.AlignVCenter, f"{v:.0f}")
            p.setPen(QPen(GRADE, 1))
        n = len(self.meses)
        passo = (dir_ - esq) / n
        larg = min(36.0, passo * 0.6)
        for i, (mes, imp, nao) in enumerate(self.meses):
            cx = esq + passo * (i + 0.5)
            h_imp = alto * imp / maximo
            h_nao = alto * nao / maximo
            r_imp = QRectF(cx - larg / 2, base - h_imp, larg, h_imp)
            gap = 2.0 if imp and nao else 0.0              # 2 px de fundo entre os segmentos
            r_nao = QRectF(cx - larg / 2, base - h_imp - gap - h_nao, larg, h_nao)
            self._barra(p, r_imp, COR_IMPRESSO, topo_redondo=not nao)
            self._barra(p, r_nao, COR_NAO, topo_redondo=True)
            total = imp + nao
            p.setPen(TINTA)
            p.drawText(QRectF(cx - 30, base - h_imp - gap - h_nao - 16, 60, 14), Qt.AlignCenter, str(total))
            p.setPen(TINTA_2)
            rot = f"{mes[5:]}/{mes[2:4]}"
            p.drawText(QRectF(cx - passo / 2, base + 2, passo, 18), Qt.AlignHCenter | Qt.AlignTop, rot)
            pct = 100 * imp / total if total else 0
            dica = f"{rot}: {total} filme(s) — {imp} impresso(s), {nao} não impresso(s) ({pct:.0f}% impressos)"
            self._alvos.append((QRectF(cx - passo / 2, topo, passo, base - topo + 18), dica))
        p.end()


class GraficoModalidades(_Grafico):
    """% de filmes impressos por modalidade, em barras deitadas (uma série só: sem legenda)."""

    def __init__(self, parent=None):
        super().__init__("% de filmes impressos por modalidade", parent)
        self.grupos: list[F.Grupo] = []

    def definir(self, grupos) -> None:
        self.grupos = list(grupos)[:10]
        self.setMinimumHeight(max(220, 40 + 26 * len(self.grupos)))
        self.update()

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        self._alvos = []
        topo = self._titulo(p) + 6
        if not self.grupos:
            p.setPen(TINTA_2)
            p.drawText(self.rect().adjusted(0, int(topo), 0, 0), Qt.AlignCenter, "Nenhum filme no período.")
            return
        fm = p.fontMetrics()
        esq = 8 + max(fm.horizontalAdvance(g.nome) for g in self.grupos) + 10
        dir_ = self.width() - 90.0
        linha = min(26.0, (self.height() - topo - 8) / len(self.grupos))
        p.setPen(QPen(GRADE, 1))
        for k in (0, 50, 100):
            xx = esq + (dir_ - esq) * k / 100
            p.drawLine(QPointF(xx, topo - 2), QPointF(xx, topo + linha * len(self.grupos)))
        for i, g in enumerate(self.grupos):
            y = topo + i * linha
            p.setPen(TINTA)
            p.drawText(QRectF(4, y, esq - 12, linha), Qt.AlignRight | Qt.AlignVCenter, g.nome)
            pct = g.pct or 0.0
            w = (dir_ - esq) * pct / 100
            r = QRectF(esq, y + linha * 0.2, w, linha * 0.6)
            if w > 0:
                raio = min(4.0, r.height() / 2, w)
                path = QPainterPath()
                path.moveTo(r.left(), r.top())
                path.lineTo(r.right() - raio, r.top())
                path.quadTo(r.right(), r.top(), r.right(), r.top() + raio)
                path.lineTo(r.right(), r.bottom() - raio)
                path.quadTo(r.right(), r.bottom(), r.right() - raio, r.bottom())
                path.lineTo(r.left(), r.bottom())
                path.closeSubpath()
                p.fillPath(path, COR_IMPRESSO)
            p.setPen(TINTA_2)
            p.drawText(QRectF(esq + w + 6, y, 84, linha), Qt.AlignLeft | Qt.AlignVCenter,
                       f"{pct:.0f}%  ({g.impressos}/{g.filmes})")
            self._alvos.append((QRectF(0, y, self.width(), linha),
                                f"{g.nome}: {g.impressos} de {g.filmes} filme(s) impressos ({pct:.0f}%)"))
        p.end()


# --------------------------------------------------------------------------- janela
class FilmDashboard(QDialog):
    """Janela do painel. Não modal: dá para deixá-la aberta e voltar ao trabalho."""

    abrir_filme = Signal(int)
    abrir_exame = Signal(str)            # impressão DICOM: o exame criado com as folhas

    def __init__(self, repo, settings=None, parent=None):
        super().__init__(parent)
        self.repo, self.settings = repo, settings
        self.setWindowTitle("Painel de filmes e impressões")
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.resize(1250, 860)
        self.todas: list[F.Linha] = []
        self.visiveis: list[F.Linha] = []

        # ---- filtros, numa linha só, em cima de tudo
        self.c_periodo = QComboBox()
        for texto, chave in PERIODOS:
            self.c_periodo.addItem(texto, chave)
        self.d_de = QDateEdit(calendarPopup=True)
        self.d_ate = QDateEdit(calendarPopup=True)
        hoje = QDate.currentDate()
        self.d_de.setDate(hoje.addDays(-29))
        self.d_ate.setDate(hoje)
        for d in (self.d_de, self.d_ate):
            d.setDisplayFormat("dd/MM/yyyy")
            d.dateChanged.connect(self.atualizar_tela)
        self.c_mod = QComboBox()
        self.c_user = QComboBox()
        self.c_tipo = QComboBox()
        self.c_tipo.addItem("Todas", "")
        for chave, texto in F.TIPOS.items():
            self.c_tipo.addItem(texto, chave)
        self.c_tipo.setToolTip("Compositor: filmes montados aqui. Impressão DICOM: os que chegaram "
                               "prontos das modalidades pela impressora do programa.")
        self.s_parado = QSpinBox()
        self.s_parado.setRange(0, 60)
        self.s_parado.setValue(int(self._pref("dias_parado", 2)))
        self.s_parado.setSuffix(" dia(s)")
        self.s_parado.setToolTip("Filme salvo e não impresso há mais que isto entra em \"Parados\"")
        self.k_so_nao = QCheckBox("Só os não impressos")
        b_atualizar = QPushButton("Atualizar")
        b_atualizar.clicked.connect(self.carregar)
        self.b_csv = QPushButton("Exportar CSV…")
        self.b_csv.clicked.connect(self.exportar_csv)
        topo = QHBoxLayout()
        for rot, w in (("Período:", self.c_periodo), ("de", self.d_de), ("até", self.d_ate),
                       ("Origem:", self.c_tipo), ("Modalidade:", self.c_mod), ("Usuário:", self.c_user),
                       ("Parado há mais de", self.s_parado)):
            topo.addWidget(QLabel(rot))
            topo.addWidget(w)
        topo.addWidget(self.k_so_nao)
        topo.addStretch(1)
        topo.addWidget(b_atualizar)
        topo.addWidget(self.b_csv)
        self.c_periodo.currentIndexChanged.connect(self._periodo_mudou)
        for c in (self.c_mod, self.c_user, self.c_tipo):
            c.currentIndexChanged.connect(self.atualizar_tela)
        self.s_parado.valueChanged.connect(self.atualizar_tela)
        self.k_so_nao.toggled.connect(self.atualizar_tela)

        # ---- cartões
        self.k_filmes = Cartao("Filmes")
        self.k_impressos = Cartao("Impressos")
        self.k_parados = Cartao("Parados (não impressos)")
        self.k_ex_filme = Cartao("Exame → filme")
        self.k_filme_imp = Cartao("Filme → impressão")
        self.k_ex_imp = Cartao("Exame → impressão")
        self.k_folhas = Cartao("Folhas impressas")
        cartoes = QGridLayout()
        for i, k in enumerate((self.k_filmes, self.k_impressos, self.k_parados, self.k_ex_filme,
                               self.k_filme_imp, self.k_ex_imp, self.k_folhas)):
            cartoes.addWidget(k, 0, i)

        # ---- gráficos
        self.g_meses = GraficoMeses()
        self.g_mod = GraficoModalidades()
        graficos = QHBoxLayout()
        graficos.addWidget(self.g_meses, 3)
        graficos.addWidget(self.g_mod, 2)

        # ---- tabelas por modalidade e por usuário
        self.t_mod = self._tabela_grupo("Modalidade")
        self.t_user = self._tabela_grupo("Usuário")
        grupos = QHBoxLayout()
        for titulo, t in (("Por modalidade", self.t_mod),
                          ("Por usuário ou aparelho (quem fez o filme)", self.t_user)):
            caixa = QVBoxLayout()
            l = QLabel(f"<b>{titulo}</b>")
            caixa.addWidget(l)
            caixa.addWidget(t)
            grupos.addLayout(caixa, 1)

        # ---- lista de filmes
        self.t_filmes = QTableWidget(0, len(COLUNAS))
        self.t_filmes.setHorizontalHeaderLabels(COLUNAS)
        self.t_filmes.verticalHeader().setVisible(False)
        self.t_filmes.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.t_filmes.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.t_filmes.setSortingEnabled(True)
        self.t_filmes.setMinimumHeight(260)
        self.t_filmes.doubleClicked.connect(self._abrir_linha)
        self.t_filmes.setToolTip("Duplo clique abre o filme no compositor (na impressão DICOM, o exame "
                                 "com as folhas)")
        self.t_filmes.horizontalHeaderItem(2).setToolTip(
            "Quem montou o filme no compositor; na impressão DICOM, o aparelho que mandou")
        colunas_ajustaveis(self.t_filmes)
        self.l_lista = QLabel()

        self.l_notas = QLabel(
            "<span style='color:#9a9a9a'>Tempos em mediana (e percentil 90 na dica do cartão). "
            "<b>Exame → filme</b>: da data/hora do estudo até o filme ser salvo. <b>Filme → impressão</b>: "
            "do filme salvo até a última impressão. Tempo negativo (hora do aparelho errada) não entra na "
            "conta. Um filme com duas modalidades conta nas duas, na tabela e no gráfico por modalidade. "
            "Filmes salvos antes da versão 0.77 aparecem como <i>(não registrado)</i> em usuário e destino: "
            "o programa ainda não gravava isso. Exportar para PDF ou imagem não conta como impressão; "
            "impressora do Windows, impressora DICOM e envio pela aba Impressões contam. "
            "<b>Impressão DICOM</b>: o filme que chegou pronto da modalidade conta a partir da chegada; "
            "fica como impresso quando é encaminhado (pela regra ou à mão). O exame dele é o do paciente "
            "identificado, feito até a hora da chegada; sem paciente identificado, os tempos ficam em "
            "branco.</span>")
        self.l_notas.setWordWrap(True)

        corpo = QWidget()
        lay = QVBoxLayout(corpo)
        lay.addLayout(cartoes)
        lay.addLayout(graficos)
        lay.addLayout(grupos)
        cab = QHBoxLayout()
        cab.addWidget(QLabel("<b>Filmes</b>"))
        cab.addWidget(self.l_lista, 1)
        lay.addLayout(cab)
        lay.addWidget(self.t_filmes, 1)
        lay.addWidget(self.l_notas)
        rolar = QScrollArea()
        rolar.setWidgetResizable(True)
        rolar.setFrameShape(QFrame.NoFrame)
        rolar.setWidget(corpo)
        raiz = QVBoxLayout(self)
        raiz.addLayout(topo)
        raiz.addWidget(rolar, 1)

        self._periodo_mudou()
        self.carregar()

    # ------------------------------------------------------------------ preferências
    def _pref(self, chave: str, padrao):
        if self.settings is None:
            return padrao
        return (self.settings.get("painel_filmes", {}) or {}).get(chave, padrao)

    def _guardar_pref(self, chave: str, valor) -> None:
        if self.settings is None:
            return
        d = dict(self.settings.get("painel_filmes", {}) or {})
        if d.get(chave) == valor:
            return
        d[chave] = valor
        self.settings.set("painel_filmes", d)
        try:
            self.settings.save()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------ dados
    def carregar(self) -> None:
        """Lê o banco de novo (o filme impresso agora entra sem fechar a janela)."""
        self.todas = F.linhas(self.repo.film_stats_rows() + self._impressoes_dicom())
        for combo, valores, todos in (
                (self.c_mod, sorted({m for l in self.todas for m in (l.modalidades or [F.SEM_MODALIDADE])}),
                 "Todas"),
                (self.c_user, sorted({l.criado_por for l in self.todas}), "Todos")):
            atual = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(todos, "")
            for v in valores:
                combo.addItem(v, v)
            i = combo.findData(atual)
            combo.setCurrentIndex(i if i >= 0 else 0)
            combo.blockSignals(False)
        self.atualizar_tela()

    def _impressoes_dicom(self) -> list[dict]:
        """As que chegaram prontas: "criado por" é o aparelho (nome cadastrado, ou o AE)."""
        try:
            rows = self.repo.print_job_stats_rows()
        except Exception:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).exception("painel: impressões recebidas")
            return []
        from ipe.printing import origins as O
        for r in rows:
            o = O.job_origin(self.settings, r) if self.settings is not None else None
            r["created_by"] = (o.name if o is not None and o.registered else "") or r.get("calling_ae") \
                or "(aparelho desconhecido)"
        return rows

    def _periodo_mudou(self) -> None:
        chave = self.c_periodo.currentData()
        escolher = chave == "datas"
        self.d_de.setEnabled(escolher)
        self.d_ate.setEnabled(escolher)
        if not escolher:
            de, ate = F.periodo(chave)
            for w, d in ((self.d_de, de), (self.d_ate, ate)):
                w.blockSignals(True)
                if d is not None:
                    w.setDate(QDate(d.year, d.month, d.day))
                w.blockSignals(False)
        self.atualizar_tela()

    def filtro(self) -> F.Filtro:
        chave = self.c_periodo.currentData()
        if chave == "datas":
            de, ate = self.d_de.date().toPython(), self.d_ate.date().toPython()
        else:
            de, ate = F.periodo(chave)
        return F.Filtro(de, ate, self.c_mod.currentData() or "", self.c_user.currentData() or "",
                        self.c_tipo.currentData() or "")

    def atualizar_tela(self, *_a) -> None:
        if not hasattr(self, "t_filmes"):
            return
        self._guardar_pref("dias_parado", self.s_parado.value())
        flt = self.filtro()
        ls = [l for l in self.todas if flt.aceita(l)]
        self._no_periodo = ls
        r = F.resumo(ls, dias_parado=self.s_parado.value())
        self._cartoes(r)
        self.g_meses.definir(r.por_mes)
        self.g_mod.definir(r.por_modalidade)
        self._preencher_grupo(self.t_mod, r.por_modalidade)
        self._preencher_grupo(self.t_user, r.por_usuario)
        self.visiveis = [l for l in ls if not l.impresso] if self.k_so_nao.isChecked() else ls
        self._preencher_filmes(self.visiveis)
        self.l_lista.setText(f"<span style='color:#9a9a9a'>{len(self.visiveis)} de {len(ls)} no período"
                             " · clique no cabeçalho para ordenar · duplo clique abre</span>")
        self.b_csv.setEnabled(bool(self.visiveis))

    def _cartoes(self, r: F.Resumo) -> None:
        def tempo(t: F.Tempo) -> tuple[str, str, str]:
            det = f"p90 {F.duracao(t.p90)} · {t.n} filme(s)" if t.n else "sem dado"
            if t.negativos:
                det += f" · {t.negativos} com hora errada, fora da conta"
            return F.duracao(t.mediana), det, "Mediana; o percentil 90 diz quanto demoram os 10% mais lentos."

        n_dicom = sum(1 for l in self._no_periodo if l.tipo == "dicom")
        if n_dicom:
            self.k_filmes.mostrar(str(r.filmes), f"Compositor: {r.filmes - n_dicom} · impressão DICOM: "
                                                 f"{n_dicom} · {r.folhas} folha(s), {r.imagens} imagem(ns)")
        else:
            self.k_filmes.mostrar(str(r.filmes), f"{r.folhas} folha(s), {r.imagens} imagem(ns)")
        self.k_impressos.mostrar(F.porcentagem(r.pct), f"{r.impressos} de {r.filmes} filme(s)"
                                 + (f" · {r.reimpressos} reimpresso(s)" if r.reimpressos else ""))
        dias = self.s_parado.value()
        self.k_parados.mostrar(str(len(r.parados)), f"há mais de {dias} dia(s) · {r.nao_impressos} não "
                               "impresso(s) no total",
                               "\n".join(f"{_data(l.criado)} — {l.paciente} ({l.modalidade})"
                                         for l in r.parados[:15]))
        self.k_parados.l_valor.setStyleSheet("color:#e0a040" if r.parados else "")
        self.k_ex_filme.mostrar(*tempo(r.exame_filme))
        self.k_filme_imp.mostrar(*tempo(r.filme_impressao))
        v, det, dica = tempo(r.exame_impressao)
        if r.impressos:
            det += f" · {100 * r.impressos_24h / r.impressos:.0f}% em até 24 h"
        self.k_ex_imp.mostrar(v, det, dica)
        destinos = "; ".join(f"{d}: {n}" for d, n in r.por_destino[:5])
        self.k_folhas.mostrar(str(r.folhas_impressas), f"{r.impressoes} impressão(ões)",
                              f"Destinos: {destinos}" if destinos else "")

    def _tabela_grupo(self, primeira: str) -> QTableWidget:
        t = QTableWidget(0, 1 + len(COLUNAS_GRUPO))
        t.setHorizontalHeaderLabels([primeira] + COLUNAS_GRUPO)
        for j, dica in ((4, "Mediana, da hora do exame até o filme salvo"),
                        (5, "Mediana, do filme salvo até a última impressão")):
            t.horizontalHeaderItem(j).setToolTip(dica)
        t.verticalHeader().setVisible(False)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setMinimumHeight(150)
        t.setMaximumHeight(240)
        colunas_ajustaveis(t)
        return t

    def _preencher_grupo(self, t: QTableWidget, grupos: list[F.Grupo]) -> None:
        t.setSortingEnabled(False)
        t.setRowCount(len(grupos))
        for i, g in enumerate(grupos):
            valores = [
                _item(g.nome),
                _ord(g.filmes, g.filmes), _ord(g.impressos, g.impressos),
                _ord(F.porcentagem(g.pct), g.pct),
                _ord(F.duracao(g.exame_filme.mediana), g.exame_filme.mediana),
                _ord(F.duracao(g.filme_impressao.mediana), g.filme_impressao.mediana),
                _ord(g.folhas_impressas, g.folhas_impressas), _ord(g.reimpressoes, g.reimpressoes)]
            for j, it in enumerate(valores):
                t.setItem(i, j, it)
        t.setSortingEnabled(True)
        t.resizeColumnsToContents()

    def _preencher_filmes(self, ls: list[F.Linha]) -> None:
        t = self.t_filmes
        t.setSortingEnabled(False)
        t.setRowCount(len(ls))
        for i, l in enumerate(ls):
            primeira = _ord(_data(l.criado), l.criado.timestamp(), direita=False)
            primeira.setData(Qt.UserRole + 1, l.id)
            primeira.setData(Qt.UserRole + 2, l.tipo)
            primeira.setData(Qt.UserRole + 3, l.study_uid)
            imp = _item("Sim" if l.impresso else "Não")
            imp.setForeground(TINTA if l.impresso else QColor("#e0a040"))
            valores = [
                primeira, _item(l.origem), _item(l.criado_por), _item(l.paciente), _item(l.modalidade),
                _ord(_data(l.exame), l.exame.timestamp() if l.exame else None, direita=False),
                _item(l.exame_descricao), _ord(l.folhas, l.folhas), _ord(l.imagens, l.imagens), imp,
                _ord(_data(l.impresso_em), l.impresso_em.timestamp() if l.impresso_em else None, direita=False),
                _item(l.impresso_por), _item(l.destino if l.impresso else ""),
                _ord(l.impressoes or "", l.impressoes),
                _ord(F.duracao(l.h_exame_filme), l.h_exame_filme),
                _ord(F.duracao(l.h_filme_impressao), l.h_filme_impressao),
                _ord(F.duracao(l.h_exame_impressao), l.h_exame_impressao)]
            for j, it in enumerate(valores):
                t.setItem(i, j, it)
        t.setSortingEnabled(True)
        t.sortItems(0, Qt.DescendingOrder)
        t.resizeColumnsToContents()          # datas e nomes inteiros; a divisa continua arrastável

    def _abrir_linha(self, idx) -> None:
        it = self.t_filmes.item(idx.row(), 0)
        if it is None:
            return
        if it.data(Qt.UserRole + 2) == "dicom":
            uid = it.data(Qt.UserRole + 3) or ""
            if uid:
                self.abrir_exame.emit(str(uid))
            else:
                QMessageBox.information(self, "Painel de filmes", "Esta impressão não foi guardada "
                                        "como exame no banco.")
            return
        fid = it.data(Qt.UserRole + 1)
        if fid:
            self.abrir_filme.emit(int(fid))

    # ------------------------------------------------------------------ CSV
    def exportar_csv(self, caminho: str | None = None) -> str | None:
        if not caminho:
            caminho, _f = QFileDialog.getSaveFileName(
                self, "Exportar CSV", f"filmes_{date.today():%Y%m%d}.csv", "CSV (*.csv)")
        if not caminho:
            return None
        try:
            # ; e UTF-8 com BOM, quebra de linha do Windows: abre direto no Excel em português
            with open(caminho, "w", encoding="utf-8-sig", newline="") as fh:
                w = csv.writer(fh, delimiter=";", lineterminator="\r\n")
                w.writerow(COLUNAS + ["Horas exame → filme", "Horas filme → impressão",
                                      "Horas exame → impressão"])
                for l in self.visiveis:
                    h = [("" if v is None else f"{v:.2f}".replace(".", ","))
                         for v in (l.h_exame_filme, l.h_filme_impressao, l.h_exame_impressao)]
                    w.writerow([_data(l.criado), l.origem, l.criado_por, l.paciente, l.modalidade, _data(l.exame),
                                l.exame_descricao, l.folhas, l.imagens, "Sim" if l.impresso else "Não",
                                _data(l.impresso_em), l.impresso_por, l.destino, l.impressoes,
                                F.duracao(l.h_exame_filme), F.duracao(l.h_filme_impressao),
                                F.duracao(l.h_exame_impressao)] + h)
        except OSError as e:
            QMessageBox.warning(self, "Exportar CSV", f"Não foi possível gravar o arquivo:\n{e}")
            return None
        return caminho
