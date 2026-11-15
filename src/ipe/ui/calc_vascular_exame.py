"""Calcificações vasculares da mama de um exame (0.100.51): medir, ver nas imagens, graduar e mandar ao laudo.

Pedido dele (15/11/2026): identificar as calcificações vasculares na mamografia, com o mesmo jeito da densidade — a
rede mede, ele revisa e confirma, tudo fica guardado para validar. Graus combinados: **ausente, leve, moderada,
acentuada** (a escala de pontos vem depois da validação).

A rede (SCU-Net, `ai/calc_vascular.py`) mede as quatro incidências 2D do exame; a janela mostra as quatro com o que
foi marcado em vermelho, a área por mama e a sugestão provisória de grau (pela área dos trechos alongados). O grau é
do médico: a sugestão vem marcada de saída, ele troca se discordar e confirma.
"""
from __future__ import annotations

import logging
import threading

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from ipe.ai import calc_vascular as C
from ipe.core.i18n import tr

log = logging.getLogger(__name__)

ROTULO_VISTA = {"R-CC": "CC direita", "L-CC": "CC esquerda", "R-MLO": "MLO direita", "L-MLO": "MLO esquerda"}
LADO = {"R": "direita", "L": "esquerda"}


class Medidor(QThread):
    pronto = Signal(str, object, str)            # study_uid, medida (ou None), erro

    def __init__(self, repo, study_uid: str, dados=None, parent=None) -> None:
        super().__init__(parent)
        self.repo, self.uid, self.dados = repo, study_uid, dados
        self.stop = threading.Event()

    def run(self) -> None:  # noqa: D102
        try:
            m = C.medir_exame(self.repo, self.uid, self.dados, self.stop.is_set)
            try:
                C.guardar_medida(self.repo, self.uid, m)
                m = C.guardada(self.repo, self.uid) or m
            except Exception as e:  # noqa: BLE001 - não guardar não pode esconder a medida
                log.info("calcificação vascular: não guardei a medida: %s", e)
                m.setdefault("avisos", []).append(
                    f"A medida não foi guardada no exame ({e}). Num servidor central, atualize o servidor para a "
                    "mesma versão deste computador.")
            self.pronto.emit(self.uid, m, "")
        except InterruptedError:
            self.pronto.emit(self.uid, None, "interrompida")
        except Exception as e:  # noqa: BLE001
            log.debug("calcificação vascular do exame", exc_info=True)
            self.pronto.emit(self.uid, None, str(e))


def resumo_curto(m: dict) -> str:
    if m.get("aviso"):
        return tr("a rede não rodou ({})").format(tr(m["aviso"]))
    g = m.get("grau") or m.get("sugestao")
    a = m.get("area_mm2")
    partes = [tr(C.NOMES[g]) if g else tr("sem sugestão")]
    if a is not None:
        partes.append(f"{a:.0f} mm²")
    return " · ".join(partes)


def _pixmap(rgb) -> QPixmap:
    h, w, _ = rgb.shape
    img = QImage(rgb.tobytes(), w, h, 3 * w, QImage.Format_RGB888)
    return QPixmap.fromImage(img.copy())


class CalcVascularJanela(QDialog):
    def __init__(self, tab, parent=None, dados=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Calcificações vasculares da mama"))
        self.tab, self.dados = tab, dados
        self.repo = tab.repo
        vp = getattr(tab, "active", None)
        self.uid = (vp.study_uid if vp is not None and getattr(vp, "study_uid", "") else "") or tab.study_uid
        from ipe.ui.viewer.estado_analise import usuario_atual
        self.usuario = usuario_atual()
        self.medida: dict | None = None
        self.medidor: Medidor | None = None

        lay = QVBoxLayout(self)
        self.lb_estado = QLabel("")
        self.lb_estado.setWordWrap(True)
        lay.addWidget(self.lb_estado)
        self.barra = QProgressBar()
        self.barra.setRange(0, 0)
        self.barra.setVisible(False)
        lay.addWidget(self.barra)

        grade = QGridLayout()
        self.quadros: dict[str, QLabel] = {}
        self.legendas: dict[str, QLabel] = {}
        for i, k in enumerate(("R-CC", "L-CC", "R-MLO", "L-MLO")):
            q = QLabel()
            q.setAlignment(Qt.AlignCenter)
            q.setMinimumSize(200, 240)
            q.setStyleSheet("background:black")
            leg = QLabel(tr(ROTULO_VISTA[k]))
            leg.setAlignment(Qt.AlignCenter)
            grade.addWidget(q, (i // 2) * 2, i % 2)
            grade.addWidget(leg, (i // 2) * 2 + 1, i % 2)
            self.quadros[k], self.legendas[k] = q, leg
        lay.addLayout(grade, 1)

        self.lb_rede = QLabel("")
        self.lb_rede.setTextFormat(Qt.RichText)
        self.lb_rede.setWordWrap(True)
        lay.addWidget(self.lb_rede)
        self.lb_avisos = QLabel("")
        self.lb_avisos.setWordWrap(True)
        self.lb_avisos.setStyleSheet("color:#b8860b")
        lay.addWidget(self.lb_avisos)

        lay.addWidget(QLabel("<b>" + tr("Seu grau") + "</b>"))
        self.grupo = QButtonGroup(self)
        linha = QHBoxLayout()
        self.radios: dict[str, QRadioButton] = {}
        for g in C.GRAUS:
            rb = QRadioButton(tr(C.NOMES[g]))
            self.grupo.addButton(rb)
            linha.addWidget(rb)
            self.radios[g] = rb
        linha.addStretch(1)
        lay.addLayout(linha)
        self.lb_confirmado = QLabel("")
        self.lb_confirmado.setStyleSheet("color:gray")
        lay.addWidget(self.lb_confirmado)

        botoes = QHBoxLayout()
        self.bt_medir = QPushButton(tr("Medir de novo"))
        self.bt_medir.clicked.connect(self.medir)
        self.bt_ok = QPushButton(tr("Confirmar"))
        self.bt_ok.clicked.connect(lambda: self.confirmar(False))
        self.bt_laudo = QPushButton(tr("Confirmar e mandar ao laudo"))
        self.bt_laudo.clicked.connect(lambda: self.confirmar(True))
        fechar = QPushButton(tr("Fechar"))
        fechar.clicked.connect(self.close)
        botoes.addWidget(self.bt_medir)
        botoes.addStretch(1)
        botoes.addWidget(self.bt_ok)
        botoes.addWidget(self.bt_laudo)
        botoes.addWidget(fechar)
        lay.addLayout(botoes)
        self.resize(760, 900)

        self.medida = C.guardada(self.repo, self.uid)
        if self.medida is None:
            self.medir()
        else:
            self.mostrar()

    def medir(self) -> None:
        if self.medidor is not None and self.medidor.isRunning():
            return
        self.lb_estado.setText(tr("Procurando calcificações vasculares nas quatro incidências…"))
        self.barra.setVisible(True)
        self._habilitar(False)
        self.medidor = Medidor(self.repo, self.uid, self.dados, self)
        self.medidor.pronto.connect(self._medido)
        self.medidor.start()

    def _medido(self, uid: str, m, erro: str) -> None:
        self.barra.setVisible(False)
        self._habilitar(True)
        if m is None:
            self.lb_estado.setText(tr("Não consegui medir: {}").format(erro))
            return
        self.medida = m
        self.mostrar()

    def _habilitar(self, sim: bool) -> None:
        for b in (self.bt_medir, self.bt_ok, self.bt_laudo):
            b.setEnabled(sim)

    def mostrar(self) -> None:
        m = self.medida or {}
        apar = m.get("aparelho", "")
        self.lb_estado.setText(tr("Medido em {}").format(m.get("quando", "")) + (f" — {apar}" if apar else ""))
        self._previas(m)
        if m.get("aviso"):
            self.lb_rede.setText(f"<b>{tr('Rede (SCU-Net)')}:</b> — {tr(m['aviso'])}")
        else:
            lados = " · ".join(f"{tr('mama')} {tr(LADO[k])} {v:.0f} mm²" for k, v in (m.get("por_mama") or {}).items())
            sug = m.get("sugestao")
            self.lb_rede.setText(
                f"<b>{tr('Rede (SCU-Net)')}:</b> " + (lados or "—")
                + f"<br><b>{tr('Sugestão')}:</b> " + (tr(C.NOMES[sug]) if sug else tr("nenhuma"))
                + " <span style='color:gray'>(" + tr("provisória, pela área dos trechos alongados") + ")</span>")
        self.lb_avisos.setText("\n".join(tr(a) for a in (m.get("avisos") or [])))
        marcado = m.get("grau") or m.get("sugestao") or ""
        self.grupo.setExclusive(False)
        for g, rb in self.radios.items():
            rb.setChecked(g == marcado)
        self.grupo.setExclusive(True)
        if m.get("grau"):
            self.lb_confirmado.setText(tr("Confirmado: {} — {} {}").format(
                tr(C.NOMES[m["grau"]]), m.get("revisor", ""), m.get("confirmado_em", "")).strip())
        else:
            self.lb_confirmado.setText(tr("Ainda não confirmado."))

    def _previas(self, m: dict) -> None:
        try:
            import pydicom
            arquivos = C.arquivos_das_vistas(self.repo, self.uid)
        except Exception:  # noqa: BLE001
            arquivos = {}
        for k, q in self.quadros.items():
            v = (m.get("vistas") or {}).get(k)
            cam = arquivos.get(k)
            if not v or not cam:
                q.setPixmap(QPixmap())
                q.setText(tr("sem esta incidência"))
                self.legendas[k].setText(tr(ROTULO_VISTA[k]))
                continue
            try:
                rgb = C.previa(pydicom.dcmread(cam, force=True), v, 420)
                q.setPixmap(_pixmap(rgb).scaled(q.width(), q.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            except Exception as e:  # noqa: BLE001
                log.debug("prévia da calcificação vascular", exc_info=True)
                q.setText(str(e))
            self.legendas[k].setText(f"{tr(ROTULO_VISTA[k])} — {v.get('area_mm2', 0):.0f} mm²")

    def grau(self) -> str:
        return next((g for g, rb in self.radios.items() if rb.isChecked()), "")

    def confirmar(self, laudo: bool) -> bool:
        g = self.grau()
        if not g or self.medida is None:
            self.lb_confirmado.setText(tr("Marque um grau."))
            return False
        try:
            C.confirmar(self.repo, self.uid, self.medida, g, self.usuario)
        except Exception as e:  # noqa: BLE001
            log.debug("confirmar calcificação vascular", exc_info=True)
            self.lb_confirmado.setText(tr("Não gravei: {}").format(e))
            return False
        self.medida = C.guardada(self.repo, self.uid) or dict(self.medida, grau=g)
        self.mostrar()
        if laudo:
            self.tab.mandar_texto_ao_laudo(C.frase_do_laudo(g))
        return True

    def closeEvent(self, event) -> None:  # noqa: D102, N802
        if self.medidor is not None and self.medidor.isRunning():
            self.medidor.stop.set()
            self.medidor.wait(5000)
        super().closeEvent(event)


def abrir(tab, parent=None):
    d = CalcVascularJanela(tab, parent or tab)
    tab._calc_vascular = d
    d.show()
    return d
