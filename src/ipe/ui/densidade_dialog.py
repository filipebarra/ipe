"""Densidade mamária das imagens que estão na tela, por mais de um método — e as máscaras.

**Quem escolhe as imagens é o médico, pondo-as no quadro.** Não há regra a configurar: a janela
mede o que estiver visível no layout, seja uma imagem ou oito.

**Por que mais de um método.** Um número sozinho não dá para reprovar. Dois métodos que medem a
mesma coisa por critérios diferentes (limiar de Otsu e agrupamento nebuloso) mostram *onde* a
imagem é difícil: quando concordam, o número é sólido; quando discordam, é ali que o olho precisa
ir. E a rede da NYU, quando instalada, é opinião de outra natureza — treinada para reproduzir a
**categoria que o radiologista escreve**, olhando as quatro incidências juntas.

A tela **não dá categoria**. Mostra os números, põe a faixa a/b/c/d ao lado como referência, e
deixa ligar a máscara por cima da imagem.
"""

from __future__ import annotations

import csv
import logging
import threading

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ipe.core.i18n import tr
from ipe.imaging import density as D
from ipe.ui.tabelas import colunas_ajustaveis

log = logging.getLogger(__name__)

#: cores da máscara: a mama em contorno frio, o tecido denso preenchido em quente
COR_MAMA = (80, 200, 255)
COR_DENSA = (255, 130, 60)
#: a partir de quantos pontos percentuais a discordância entre os métodos vira aviso
DISCORDA_PP = 5.0
#: os dois métodos de área, na ordem em que aparecem na tabela
AREA = (D.LIMIAR, D.FCM)


def _item(texto: str, direita: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem(texto)
    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
    if direita:
        it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
    return it


def imagens_na_tela(tab) -> list:
    """(número do quadro, Frame) de cada imagem visível, sem medir a mesma duas vezes.

    Quadro virtual (MPR, 3D) fica de fora: ali não há arquivo de imagem para medir. A mesma
    imagem em dois quadros é medida uma vez só — o número seria idêntico e a lista, confusa.
    """
    try:
        vistos = tab._shown()
    except Exception:  # noqa: BLE001 - aba sem layout ainda: vale o que houver
        vistos = list(getattr(tab, "viewports", []) or [])
    ja, saida = set(), []
    for k, vp in enumerate(vistos, start=1):
        try:
            f = vp.current_frame()
        except Exception:  # noqa: BLE001
            f = None
        if f is None or getattr(f, "is_virtual", False) or not getattr(f, "path", ""):
            continue
        chave = (f.path, getattr(f, "frame_index", 0))
        if chave in ja:
            continue
        ja.add(chave)
        saida.append((k, f))
    return saida


class _Medidor(QThread):
    """Mede fora da interface: a tela continua respondendo e dá para parar no meio."""
    andamento = Signal(int, int)
    pronto = Signal(object, object, str)

    def __init__(self, caminhos, dados=None, parent=None) -> None:
        super().__init__(parent)
        self.caminhos = list(caminhos)
        self.dados = dados
        self.stop = threading.Event()

    def run(self) -> None:  # noqa: D102
        try:
            medidas = D.medir_imagens(self.caminhos, stop=self.stop, mascaras=True, metodos=AREA,
                                      progresso=lambda i, n: self.andamento.emit(i, n))
        except Exception:  # noqa: BLE001
            log.debug("densidade: a medição falhou", exc_info=True)
            self.pronto.emit([], None, "")
            return
        prob, aviso = None, ""
        if not self.stop.is_set():
            prob, aviso = self._rede(medidas)
        self.pronto.emit(medidas, prob, aviso)

    def _rede(self, medidas):
        """A rede pede as quatro incidências; aqui se monta o conjunto a partir do que foi medido."""
        from ipe.ai import densidade_nyu as N
        vistas = {}
        for m in medidas:
            k = N.chave(m.lado, m.incidencia)
            if k and m.caminho:
                vistas.setdefault(k, m.caminho)
        try:
            return N.do_exame(vistas, self.dados)
        except Exception:  # noqa: BLE001
            log.debug("rede de densidade", exc_info=True)
            return None, "A rede falhou ao rodar; os outros métodos continuam valendo."


class DensidadeDialog(QDialog):
    COLUNAS = ("Quadro", "Mama", "Incidência", "Otsu (PD%)", "Nebuloso (PD%)", "Diferença",
               "Faixa", "Mama (cm²)", "Espessura", "Avisos")

    def __init__(self, tab, parent=None, dados=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Densidade mamária"))
        self.tab = tab
        self.dados = dados
        self.study_uid = str(getattr(tab, "study_uid", "") or "")
        self.medidas: list = []
        self.quadros: list = []                  # [(número do quadro, Frame)]
        self.rede = None                         # probabilidades a/b/c/d, quando a rede roda
        self.aviso_rede = ""
        self.medidor = None

        lay = QVBoxLayout(self)
        self.lb_tela = QLabel()
        self.lb_tela.setWordWrap(True)
        lay.addWidget(self.lb_tela)

        linha = QHBoxLayout()
        self.bt_medir = QPushButton(tr("Medir o que está na tela"))
        self.bt_medir.clicked.connect(self.medir)
        self.bt_parar = QPushButton(tr("Parar"))
        self.bt_parar.clicked.connect(self.parar)
        self.bt_parar.setEnabled(False)
        self.barra = QProgressBar()
        self.barra.setVisible(False)
        linha.addWidget(self.bt_medir)
        linha.addWidget(self.bt_parar)
        linha.addWidget(self.barra, 1)
        linha.addStretch(1)                       # barra escondida não faz botão inchar
        lay.addLayout(linha)

        self.tabela = QTableWidget(0, len(self.COLUNAS))
        self.tabela.setHorizontalHeaderLabels([tr(c) for c in self.COLUNAS])
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        cab = self.tabela.horizontalHeader()
        cab.setSectionResizeMode(QHeaderView.ResizeToContents)
        cab.setSectionResizeMode(len(self.COLUNAS) - 1, QHeaderView.Stretch)
        self.tabela.setWordWrap(False)
        self.tabela.doubleClicked.connect(self.ir_para_imagem)
        lay.addWidget(self.tabela)
        colunas_ajustaveis(self.tabela)

        self.lb_resumo = QLabel()
        self.lb_resumo.setWordWrap(True)
        lay.addWidget(self.lb_resumo)

        self.lb_discorda = QLabel()
        self.lb_discorda.setWordWrap(True)
        self.lb_discorda.setStyleSheet("color:#b8860b")     # âmbar: lê-se no claro e no escuro
        lay.addWidget(self.lb_discorda)

        # os avisos por extenso: na tabela eles cabem cortados, e aviso cortado não avisa
        self.lb_avisos = QLabel()
        self.lb_avisos.setWordWrap(True)
        lay.addWidget(self.lb_avisos)

        self.lb_nota = QLabel(tr(
            "As faixas a/b/c/d são referência ao lado do número: a categoria do BI-RADS leva em "
            "conta mascaramento e distribuição, não só fração de área, e é julgamento do "
            "radiologista."))
        self.lb_nota.setWordWrap(True)
        lay.addWidget(self.lb_nota)

        lay.addStretch(1)                         # a sobra fica no fim, nunca no meio

        baixo = QHBoxLayout()
        self.ck_mascara = QCheckBox(tr("Mostrar a máscara sobre a imagem"))
        self.ck_mascara.toggled.connect(self.aplicar_mascara)
        self.c_mascara = QComboBox()
        for nome in AREA:
            self.c_mascara.addItem(tr(D.METODOS[nome]), nome)
        self.c_mascara.currentIndexChanged.connect(
            lambda _i: self.aplicar_mascara(self.ck_mascara.isChecked()))
        self.bt_csv = QPushButton(tr("Exportar CSV…"))
        self.bt_csv.clicked.connect(self.exportar)
        self.bt_csv.setEnabled(False)
        fechar = QPushButton(tr("Fechar"))
        fechar.clicked.connect(self.accept)
        baixo.addWidget(self.ck_mascara)
        baixo.addWidget(self.c_mascara)
        baixo.addStretch(1)
        baixo.addWidget(self.bt_csv)
        baixo.addWidget(fechar)
        lay.addLayout(baixo)

        self.resize(1040, 460)
        self.ler_a_tela()

    # ------------------------------------------------------------- o que medir
    def ler_a_tela(self) -> None:
        """Relê o layout. Mudou o quadro, mudou a incidência: basta mandar medir de novo."""
        self.quadros = imagens_na_tela(self.tab)
        if self.quadros:
            self.lb_tela.setText(tr("Mede as {} imagem(ns) que estão na tela agora. Mude os "
                                    "quadros e mande medir de novo quando quiser.").format(
                len(self.quadros)))
        else:
            self.lb_tela.setText(tr("Não há imagem para medir: os quadros visíveis estão vazios "
                                    "ou são reconstruções (MPR, 3D), que não têm imagem de "
                                    "origem para medir."))
        self.bt_medir.setEnabled(bool(self.quadros))

    # ------------------------------------------------------------------ medir
    def medir(self) -> None:
        if self.medidor is not None:
            return
        self.ler_a_tela()                         # o layout pode ter mudado desde que abriu
        if not self.quadros:
            return
        self.barra.setVisible(True)
        self.barra.setRange(0, max(1, len(self.quadros)))
        self.bt_medir.setEnabled(False)
        self.bt_parar.setEnabled(True)
        self.medidor = _Medidor([f.path for _k, f in self.quadros], self.dados, self)
        self.medidor.andamento.connect(lambda i, n: self.barra.setValue(i))
        self.medidor.pronto.connect(self.medido)
        self.medidor.start()

    def parar(self) -> None:
        if self.medidor is not None:
            self.medidor.stop.set()
        self.bt_parar.setEnabled(False)

    def medido(self, medidas, rede=None, aviso_rede: str = "") -> None:
        self.medidas = list(medidas or [])
        self.rede, self.aviso_rede = rede, aviso_rede
        for i, m in enumerate(self.medidas):
            if i < len(self.quadros):
                k, f = self.quadros[i]
                m.quadro = k
                m.serie_uid = getattr(f, "series_uid", "") or ""
                m.sop_uid = m.sop_uid or getattr(f, "sop_uid", "") or ""
        self.medidor = None
        self.barra.setVisible(False)
        self.bt_medir.setEnabled(bool(self.quadros))
        self.bt_parar.setEnabled(False)
        self.bt_csv.setEnabled(bool(self.medidas))
        self.preencher()
        if self.ck_mascara.isChecked():
            self.aplicar_mascara(True)

    @staticmethod
    def _pd(m, metodo) -> float:
        med = m.medidas.get(metodo)
        return float(med.pd) if med is not None else 0.0

    def preencher(self) -> None:
        self.tabela.setRowCount(0)
        for m in self.medidas:
            i = self.tabela.rowCount()
            self.tabela.insertRow(i)
            vazio = m.mama_cm2 <= 0
            a, b = self._pd(m, D.LIMIAR), self._pd(m, D.FCM)
            valores = [
                str(getattr(m, "quadro", "") or i + 1),
                m.lado or tr("?"),
                m.incidencia or tr("?"),
                tr("não deu") if vazio else f"{a:.1f}",
                tr("—") if vazio or D.FCM not in m.medidas else f"{b:.1f}",
                tr("—") if vazio or D.FCM not in m.medidas else f"{b - a:+.1f}",
                tr("—") if vazio else m.faixa,
                tr("—") if vazio else f"{m.mama_cm2:.1f}",
                tr("—") if not m.espessura_mm else f"{m.espessura_mm:.0f}",
                " · ".join(tr(x) for x in m.avisos),
            ]
            for j, v in enumerate(valores):
                it = _item(v, direita=3 <= j <= 8)
                if j == len(valores) - 1 and v:
                    it.setToolTip(v)              # o aviso inteiro, mesmo com a coluna estreita
                self.tabela.setItem(i, j, it)
        self._altura_da_tabela()
        self.resumo()

    def _altura_da_tabela(self, maximo: int = 12) -> None:
        """Tabela do tamanho do que tem dentro: sem faixa vazia embaixo nem linha cortada."""
        t = self.tabela
        linhas = min(max(t.rowCount(), 1), maximo)
        altura = t.horizontalHeader().height() + 2 * t.frameWidth()
        for i in range(linhas):
            altura += t.rowHeight(i) if i < t.rowCount() else 24
        if t.rowCount() > maximo:
            altura += 12
        t.setFixedHeight(altura)

    # ----------------------------------------------------------------- resumo
    def resumo(self) -> None:
        validas = [m for m in self.medidas if m.mama_cm2 > 0]
        if not validas:
            self.lb_resumo.setText(tr(
                "Nenhuma das imagens na tela deu número: veja os avisos.") if self.medidas else "")
            self.lb_discorda.setText("")
            self.escrever_avisos()
            return
        linhas = []
        for metodo in AREA:
            vals = [type(m)(lado=m.lado, pd=self._pd(m, metodo), mama_cm2=m.mama_cm2)
                    for m in validas if metodo in m.medidas]
            if not vals:
                continue
            mamas = D.por_mama(vals)
            partes = []
            if "R" in mamas:
                partes.append(tr("direita {}% ({})").format(f"{mamas['R']:.1f}",
                                                            D.faixa_de(mamas["R"])))
            if "L" in mamas:
                partes.append(tr("esquerda {}% ({})").format(f"{mamas['L']:.1f}",
                                                             D.faixa_de(mamas["L"])))
            if not partes:
                partes.append(tr("{}% ({})").format(f"{max(v.pd for v in vals):.1f}",
                                                    D.faixa_de(max(v.pd for v in vals))))
            maior = D.do_exame(vals) or max(v.pd for v in vals)
            linhas.append(tr("Pelo {}: {} — maior das mamas {}% (faixa {})").format(
                tr(D.METODOS[metodo]), "   ".join(partes), f"{maior:.1f}", D.faixa_de(maior)))
        if self.rede is not None and getattr(self.rede, "size", 0) == 4:
            from ipe.ai import densidade_nyu as N
            i = int(max(range(4), key=lambda k: self.rede[k]))
            linhas.append(tr("Rede neural: faixa {} ({}), com {}% de certeza.").format(
                N.FAIXAS[i], tr(N.ROTULOS[i]), f"{100 * float(self.rede[i]):.0f}"))
        elif self.aviso_rede:
            linhas.append(tr("Rede neural: não rodou. {}").format(tr(self.aviso_rede)))
        if len(validas) < len(self.medidas):
            linhas.append(tr("{} imagem(ns) não deram número.").format(
                len(self.medidas) - len(validas)))
        self.lb_resumo.setText("\n".join(linhas))
        self.discordancia(validas)
        self.escrever_avisos()

    def discordancia(self, validas: list) -> None:
        """Onde os dois métodos de área não batem, o número não merece confiança."""
        longe = [m for m in validas if D.FCM in m.medidas
                 and abs(self._pd(m, D.FCM) - self._pd(m, D.LIMIAR)) >= DISCORDA_PP]
        if not longe:
            self.lb_discorda.setText("")
            return
        quem = ", ".join(dict.fromkeys(self._nome(m) for m in longe))
        self.lb_discorda.setText(tr(
            "Os dois métodos discordam em mais de {} pontos percentuais em: {}. Nessas imagens o "
            "número é frágil — vale olhar a máscara dos dois antes de usar.").format(
                f"{DISCORDA_PP:.0f}", quem))

    def escrever_avisos(self) -> None:
        """Cada aviso uma vez, com as imagens que ele atinge."""
        porta: dict = {}
        for m in self.medidas:
            for a in m.avisos:
                porta.setdefault(a, []).append(self._nome(m))
        if not porta:
            self.lb_avisos.setText("")
            return
        linhas = [tr("Nas imagens {}: {}").format(", ".join(dict.fromkeys(quem)), tr(a))
                  for a, quem in porta.items()]
        self.lb_avisos.setText(tr("Avisos:") + "\n" + "\n".join(linhas))

    @staticmethod
    def _nome(m) -> str:
        rot = m.rotulo()
        return rot if rot != "?" else tr("quadro {}").format(getattr(m, "quadro", "?"))

    # --------------------------------------------------------------- máscara
    def metodo_da_mascara(self) -> str:
        return self.c_mascara.currentData() or D.LIMIAR

    def aplicar_mascara(self, ligada: bool) -> None:
        """Põe (ou tira) a máscara da mama e do tecido denso no visualizador."""
        objs = getattr(self.tab, "overlay_objects", None)
        if objs is None:
            self.ck_mascara.setEnabled(False)
            return
        objs[:] = [o for o in objs if o.source != "Densidade"]
        if ligada:
            obj = self.objeto_de_mascara()
            if obj is None:
                QMessageBox.information(self, tr("Densidade mamária"), tr(
                    "Não há máscara para mostrar: meça as imagens primeiro."))
                self.ck_mascara.setChecked(False)
                return
            objs.append(obj)
        try:
            self.tab._apply_overlays()
        except Exception:  # noqa: BLE001 - desenhar a máscara é bônus, não pode derrubar a tela
            log.debug("densidade: não consegui aplicar a máscara", exc_info=True)

    def objeto_de_mascara(self):
        from ipe.imaging import overlays as O
        metodo = self.metodo_da_mascara()
        com_mascara = [m for m in self.medidas if m.mascara_mama is not None and m.sop_uid]
        if not com_mascara:
            return None
        obj = O.OverlayObject(key="densidade", source="Densidade",
                              label=tr("máscara da mama e do tecido denso"), color=COR_DENSA,
                              study_uid=self.study_uid)
        for m in com_mascara:
            alvo = tuple(m.forma) or None    # a máscara é menor que a imagem: diz sobre o quê
            obj.masks.append(O.MaskFrame(mask=D.contorno(m.mascara_mama, 2), color=COR_MAMA,
                                         label=tr("Contorno da mama"), ref=(m.sop_uid, -1),
                                         alvo=alvo))
            med = m.medidas.get(metodo)
            densa = med.mascara if med is not None and med.mascara is not None else m.mascara_densa
            if densa is not None:
                obj.masks.append(O.MaskFrame(mask=densa, color=COR_DENSA,
                                             label=tr("Tecido denso"), ref=(m.sop_uid, -1),
                                             alvo=alvo))
            obj.findings.append(tr("Densidade de {}: {}% em {} cm² de mama.").format(
                self._nome(m), f"{self._pd(m, metodo):.1f}", f"{m.mama_cm2:.1f}"))
        return obj

    def ir_para_imagem(self) -> None:
        i = self.tabela.currentRow()
        if not (0 <= i < len(self.medidas)):
            return
        m = self.medidas[i]
        if not (m.serie_uid and m.sop_uid):
            return
        try:
            self.tab.go_to_image(self.study_uid, m.serie_uid, m.sop_uid, 0)
        except Exception:  # noqa: BLE001
            log.debug("densidade: não consegui abrir a imagem", exc_info=True)

    # -------------------------------------------------------------- exportar
    def exportar(self) -> None:
        caminho, _ = QFileDialog.getSaveFileName(self, tr("Exportar CSV"), "densidade.csv",
                                                 tr("Planilha (*.csv)"))
        if not caminho:
            return
        try:
            with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow([tr(c) for c in self.COLUNAS])
                for m in self.medidas:
                    a, b = self._pd(m, D.LIMIAR), self._pd(m, D.FCM)
                    w.writerow([getattr(m, "quadro", ""), m.lado, m.incidencia, f"{a:.2f}",
                                f"{b:.2f}", f"{b - a:+.2f}", m.faixa, f"{m.mama_cm2:.2f}",
                                f"{m.espessura_mm:.0f}", " · ".join(m.avisos)])
        except OSError as e:
            QMessageBox.warning(self, tr("Densidade mamária"),
                                tr("Não consegui gravar o arquivo: {}").format(e))

    def closeEvent(self, event) -> None:  # noqa: D102, N802
        if self.medidor is not None:
            self.medidor.stop.set()
            self.medidor.wait(3000)
        super().closeEvent(event)
