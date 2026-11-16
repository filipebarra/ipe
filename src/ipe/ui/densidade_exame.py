"""Densidade mamária de um exame (0.100.44): medir, ver, confirmar e mandar ao laudo.

Pedido dele, depois de revisar os primeiros casos (concordou com a rede da NYU em todos e com o % de área em
dois): *"crie um botão para densidade mamária: medir em segundo plano, deixando salvo; medir e revisar, abrindo uma
janela com o que já foi medido, onde confirmo, salvo e posso enviar para o relatório. Use primariamente o NYU, mas
mostre por enquanto Otsu e fuzzy. Deixe tudo salvo para decidirmos depois."*

A medida é do **exame inteiro** (as quatro incidências 2D), não só do que está na tela, e fica guardada no exame
(`imaging/densidade_revisao.py`). A janela mostra a rede — a categoria e a probabilidade de cada uma (0.100.48: só
ela; o Otsu e o fuzzy saíram). A categoria marcada de saída é a da rede (ou a que já foi confirmada); o médico troca
se discordar e confirma. "Confirmar e mandar ao laudo" põe a composição no laudo BI-RADS do exame.
"""
from __future__ import annotations

import logging
import threading

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QRadioButton, QVBoxLayout,
)

from ipe.core.i18n import tr
from ipe.imaging import densidade_revisao as R

log = logging.getLogger(__name__)


class Medidor(QThread):
    """Mede o exame fora da tela e guarda o resultado no exame."""
    pronto = Signal(str, object, str)            # study_uid, medida (ou None), erro

    def __init__(self, repo, study_uid: str, dados=None, parent=None) -> None:
        super().__init__(parent)
        self.repo, self.uid, self.dados = repo, study_uid, dados
        self.stop = threading.Event()

    def run(self) -> None:  # noqa: D102
        try:
            m = R.medir_exame(self.repo, self.uid, self.dados, self.stop)
            if self.stop.is_set():
                self.pronto.emit(self.uid, None, "interrompida")
                return
            try:
                R.guardar_medida(self.repo, self.uid, m)
                m = R.guardada(self.repo, self.uid) or m
            except Exception as e:  # noqa: BLE001 - 0.100.45: não guardar não pode esconder a medida
                log.info("densidade: não guardei a medida: %s", e)
                m.setdefault("avisos", []).append(
                    f"A medida não foi guardada no exame ({e}). Num servidor central, atualize o servidor para a "
                    "mesma versão deste computador.")
            self.pronto.emit(self.uid, m, "")
        except Exception as e:  # noqa: BLE001
            log.debug("densidade do exame", exc_info=True)
            self.pronto.emit(self.uid, None, str(e))


def resumo_curto(m: dict) -> str:
    """Uma linha para a barra de estado: a rede primeiro."""
    partes = []
    if m.get("nyu"):
        p = max(m.get("nyu_probs") or [0])
        partes.append(f"NYU {m['nyu'].upper()} ({100 * p:.0f}%)")
    else:
        partes.append("NYU —")
    return " · ".join(partes)


class DensidadeExameJanela(QDialog):
    """A densidade do exame: o que foi medido (ou mede agora), a categoria do médico, o laudo."""

    def __init__(self, tab, parent=None, dados=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("Densidade mamária do exame"))
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

        # a rede, primeiro e maior
        caixa = QFrame()
        caixa.setFrameShape(QFrame.StyledPanel)
        cl = QVBoxLayout(caixa)
        self.lb_rede = QLabel("")
        self.lb_rede.setTextFormat(Qt.RichText)
        self.lb_rede.setWordWrap(True)
        self.lb_rede.setStyleSheet("font-size:15px")
        cl.addWidget(self.lb_rede)
        self.lb_probs = QLabel("")
        self.lb_probs.setTextFormat(Qt.RichText)
        cl.addWidget(self.lb_probs)
        lay.addWidget(caixa)
        self.lb_avisos = QLabel("")
        self.lb_avisos.setWordWrap(True)
        self.lb_avisos.setStyleSheet("color:#b8860b")
        lay.addWidget(self.lb_avisos)

        # a categoria do médico
        lay.addWidget(QLabel("<b>" + tr("Sua categoria") + "</b>"))
        self.grupo = QButtonGroup(self)
        cats = QVBoxLayout()
        self.radios: dict[str, QRadioButton] = {}
        for c in R.CATEGORIAS:
            rb = QRadioButton(tr(R.NOMES[c]))
            self.grupo.addButton(rb)
            cats.addWidget(rb)
            self.radios[c] = rb
        lay.addLayout(cats)
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
        self.resize(620, 470)

        self.medida = R.guardada(self.repo, self.uid)
        if self.medida is None:
            self.medir()
        else:
            self.mostrar()

    # ------------------------------------------------------------- medir
    def medir(self) -> None:
        if self.medidor is not None and self.medidor.isRunning():
            return
        self.lb_estado.setText(tr("Medindo as quatro incidências do exame…"))
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

    # ------------------------------------------------------------- mostrar
    def mostrar(self) -> None:
        m = self.medida or {}
        quando = m.get("quando", "")
        apar = m.get("aparelho", "")
        self.lb_estado.setText(tr("Medido em {}").format(quando) + (f" — {apar}" if apar else ""))
        if m.get("nyu"):
            self.lb_rede.setText(f"<b>{tr('Rede (NYU)')}:</b> <span style='font-size:20px'>"
                                 f"{tr(R.NOMES[m['nyu']])}</span>")
            probs = list(m.get("nyu_probs") or [])
            self.lb_probs.setText(" &nbsp; ".join(
                f"{c.upper()} <b>{100 * p:.0f}%</b>" if c == m["nyu"] else f"{c.upper()} {100 * p:.0f}%"
                for c, p in zip(R.CATEGORIAS, probs)))
        else:
            self.lb_rede.setText(f"<b>{tr('Rede (NYU)')}:</b> — {m.get('nyu_aviso') or ''}")
            self.lb_probs.setText("")
        self.lb_avisos.setText("\n".join(m.get("avisos") or []))
        marcada = m.get("categoria") or m.get("nyu") or ""
        for c, rb in self.radios.items():
            rb.setChecked(c == marcada)
        if m.get("categoria"):
            self.lb_confirmado.setText(tr("Confirmado: {} — {} {}").format(
                m["categoria"].upper(), m.get("revisor", ""), m.get("confirmado_em", "")).strip())
        else:
            self.lb_confirmado.setText(tr("Ainda não confirmado (marcada de saída: a categoria da rede)."))

    def categoria(self) -> str:
        return next((c for c, rb in self.radios.items() if rb.isChecked()), "")

    # ------------------------------------------------------------- confirmar
    def confirmar(self, laudo: bool) -> bool:
        cat = self.categoria()
        if not cat or self.medida is None:
            self.lb_confirmado.setText(tr("Marque uma categoria."))
            return False
        try:
            R.confirmar(self.repo, self.uid, self.medida, cat, self.usuario)
        except Exception as e:  # noqa: BLE001
            log.debug("confirmar densidade", exc_info=True)
            self.lb_confirmado.setText(tr("Não gravei: {}").format(e))
            return False
        self.medida = R.guardada(self.repo, self.uid) or dict(self.medida, categoria=cat)
        self.mostrar()
        try:                     # 0.100.57: tudo confirmado → o SR e as imagens marcadas no exame
            self.tab.mama_confirmada(self.uid)
        except Exception:  # noqa: BLE001
            log.debug("SR da mamografia", exc_info=True)
        if laudo:
            mandar_ao_laudo(self.tab, self.uid, cat)
        return True

    def closeEvent(self, event) -> None:  # noqa: D102, N802
        if self.medidor is not None and self.medidor.isRunning():
            self.medidor.stop.set()
            self.medidor.wait(3000)
        super().closeEvent(event)


def mandar_ao_laudo(tab, study_uid: str, categoria: str) -> bool:
    """Põe a composição no laudo BI-RADS do exame (abre o laudo se preciso). Laudo assinado ou sem a parte BI-RADS:
    a frase vai como texto (ou para a área de transferência)."""
    try:
        tab.open_report(study_uid)
        w = getattr(tab, "_report_windows", {}).get(study_uid)
        painel = getattr(w, "birads", None)
        editor = getattr(w, "editor", None)
        if painel is not None and editor is not None and not editor.isReadOnly():
            f = dict(painel.fields() or {})
            if f.get("kind") in ("", None, "mg") or not f:
                f["kind"] = "mg"
                f["composition"] = categoria
                painel.set_fields(f)
                w.raise_()
                tab.status_message.emit(tr("Densidade {} posta no laudo BI-RADS.").format(categoria.upper()))
                return True
    except Exception:  # noqa: BLE001
        log.debug("densidade no laudo BI-RADS", exc_info=True)
    tab.mandar_texto_ao_laudo(R.frase_do_laudo(categoria))
    return False


def abrir(tab, parent=None):
    d = DensidadeExameJanela(tab, parent or tab)
    tab._densidade_exame = d
    d.show()
    return d
