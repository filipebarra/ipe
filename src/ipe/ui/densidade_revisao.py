"""Revisão da densidade mamária (0.100.43): uma fila de mamografias, a sugestão do programa e a categoria do médico.

Pedido dele: *"queria atuar como revisor, confirmando a leitura automática"*. A janela fica ao lado do visualizador:
abre cada exame da fila numa aba, mostra as duas sugestões (rede da NYU e % de área) e espera a categoria dele —
um clique ou uma tecla (A, B, C, D ou 1–4; N = não avaliável; → pula; ← volta). Ao responder, grava e passa ao
próximo. Em parte dos exames (10% de fábrica) a sugestão fica escondida até a resposta: é o **controle**, que mede
quanto a sugestão à vista puxa a resposta.

Embaixo, a concordância até agora (kappa ponderado, acerto exato, denso × não denso), no total e nos de controle, e
o CSV com tudo. As contas estão em `imaging/densidade_revisao.py`.
"""
from __future__ import annotations

import csv
import logging
import threading

from PySide6.QtCore import QDate, Qt, QThread, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QDateEdit, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ipe.core.i18n import tr
from ipe.imaging import densidade_revisao as R

log = logging.getLogger(__name__)

CHAVE_CONTROLE = "densidade.revisao.controle_pct"
CHAVE_FECHAR = "densidade.revisao.fechar_anterior"


class _Sugeridor(QThread):
    """Calcula a sugestão de um exame fora da tela (no cliente do servidor, baixa o exame antes)."""
    pronto = Signal(str, object)

    def __init__(self, repo, study_uid: str, dados=None, parent=None) -> None:
        super().__init__(parent)
        self.repo, self.uid, self.dados = repo, study_uid, dados
        self.stop = threading.Event()

    def run(self) -> None:  # noqa: D102
        try:
            s = R.guardada(self.repo, self.uid)               # 0.100.44: o que já foi medido não se mede de novo
            if s is None or s.get("versao", 1) < R.VERSAO:
                s = R.medir_exame(self.repo, self.uid, self.dados, self.stop)
                if not self.stop.is_set():
                    R.guardar_medida(self.repo, self.uid, s)
            self.pronto.emit(self.uid, s)
        except Exception as e:  # noqa: BLE001
            log.debug("revisão de densidade: sugestão", exc_info=True)
            self.pronto.emit(self.uid, {"nyu": None, "area": None, "area_pd": None, "nyu_probs": [],
                                        "aparelho": "", "nyu_aviso": "", "avisos": [f"Não calculei: {e}"]})


class RevisaoDensidadeJanela(QDialog):
    """A janela da revisão. `main`: a janela principal (abre e fecha as abas dos exames)."""

    def __init__(self, main, repo, settings, dados=None, parent=None) -> None:
        super().__init__(parent or (main if isinstance(main, QWidget) else None))
        self.setWindowTitle(tr("Revisão da densidade mamária"))
        self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
        self.main, self.repo, self.settings, self.dados = main, repo, settings, dados
        from ipe.ui.viewer.estado_analise import usuario_atual
        self.usuario = usuario_atual()
        self.fila: list = []                     # StudyRow
        self.i = -1
        self.sugestoes: dict[str, dict] = {}
        self.respostas: dict[str, str] = {}      # o que foi respondido nesta sessão da janela
        self._sem_sugestao: set[str] = set()     # respondidos antes de a sugestão chegar (completa-se depois)
        self._threads: dict[str, _Sugeridor] = {}
        self._abertas: set[str] = set()          # abas que esta janela abriu (só essas ela fecha)

        lay = QVBoxLayout(self)
        # --- a fila
        filtro = QHBoxLayout()
        filtro.addWidget(QLabel(tr("Mamografias de")))
        self.de = QDateEdit(QDate.currentDate().addMonths(-3))
        self.de.setCalendarPopup(True)
        self.ate = QDateEdit(QDate.currentDate())
        self.ate.setCalendarPopup(True)
        filtro.addWidget(self.de)
        filtro.addWidget(QLabel(tr("até")))
        filtro.addWidget(self.ate)
        self.ck_novos = QCheckBox(tr("Só os que eu ainda não revisei"))
        self.ck_novos.setChecked(True)
        filtro.addWidget(self.ck_novos)
        self.bt_fila = QPushButton(tr("Montar a fila"))
        self.bt_fila.clicked.connect(self.montar_fila)
        filtro.addWidget(self.bt_fila)
        filtro.addStretch(1)
        lay.addLayout(filtro)

        opc = QHBoxLayout()
        opc.addWidget(QLabel(tr("Esconder a sugestão (controle) em")))
        self.sp_controle = QSpinBox()
        self.sp_controle.setRange(0, 100)
        self.sp_controle.setSuffix("%")
        self.sp_controle.setValue(int(self._pref(CHAVE_CONTROLE, round(100 * R.CONTROLE_PADRAO))))
        self.sp_controle.valueChanged.connect(lambda v: self._gravar_pref(CHAVE_CONTROLE, int(v)))
        opc.addWidget(self.sp_controle)
        opc.addWidget(QLabel(tr("dos exames")))
        self.ck_fechar = QCheckBox(tr("Fechar o exame anterior ao passar"))
        self.ck_fechar.setChecked(bool(self._pref(CHAVE_FECHAR, True)))
        self.ck_fechar.toggled.connect(lambda v: self._gravar_pref(CHAVE_FECHAR, bool(v)))
        opc.addWidget(self.ck_fechar)
        opc.addStretch(1)
        lay.addLayout(opc)

        self.lb_fila = QLabel(tr("Escolha o período e monte a fila."))
        lay.addWidget(self.lb_fila)

        # --- o exame da vez
        caixa = QFrame()
        caixa.setFrameShape(QFrame.StyledPanel)
        cl = QVBoxLayout(caixa)
        self.lb_exame = QLabel("")
        self.lb_exame.setStyleSheet("font-weight:bold")
        self.lb_exame.setWordWrap(True)
        cl.addWidget(self.lb_exame)
        self.lb_sugestao = QLabel("")
        self.lb_sugestao.setWordWrap(True)
        self.lb_sugestao.setTextFormat(Qt.RichText)
        cl.addWidget(self.lb_sugestao)
        self.lb_avisos = QLabel("")
        self.lb_avisos.setWordWrap(True)
        self.lb_avisos.setStyleSheet("color:#b8860b")
        cl.addWidget(self.lb_avisos)
        grade = QGridLayout()
        self.botoes: dict[str, QPushButton] = {}
        for k, c in enumerate(R.CATEGORIAS):
            b = QPushButton(tr(R.NOMES[c]))
            b.setMinimumHeight(34)
            b.clicked.connect(lambda _=False, cat=c: self.responder(cat))
            grade.addWidget(b, k // 2, k % 2)
            self.botoes[c] = b
        cl.addLayout(grade)
        nav = QHBoxLayout()
        self.bt_ant = QPushButton("← " + tr("Anterior"))
        self.bt_ant.clicked.connect(lambda: self.ir(self.i - 1))
        self.bt_na = QPushButton(tr("Não avaliável") + " (N)")
        self.bt_na.clicked.connect(lambda: self.responder(R.NAO_AVALIAVEL))
        self.bt_pular = QPushButton(tr("Pular") + " →")
        self.bt_pular.clicked.connect(lambda: self.ir(self.i + 1))
        for b in (self.bt_ant, self.bt_na, self.bt_pular):
            nav.addWidget(b)
        nav.addStretch(1)
        cl.addLayout(nav)
        lay.addWidget(caixa)

        # --- a concordância
        self.lb_conc = QLabel("")
        self.lb_conc.setWordWrap(True)
        lay.addWidget(self.lb_conc)
        nota = QLabel(tr("A sugestão é do programa; a categoria é sua. Os números de concordância são dos exames que "
                         "você revisou, neste serviço e nestes aparelhos."))
        nota.setWordWrap(True)
        nota.setStyleSheet("color:gray")
        lay.addWidget(nota)
        baixo = QHBoxLayout()
        self.bt_csv = QPushButton(tr("Exportar CSV…"))
        self.bt_csv.clicked.connect(self.exportar)
        fechar = QPushButton(tr("Fechar"))
        fechar.clicked.connect(self.close)
        baixo.addStretch(1)
        baixo.addWidget(self.bt_csv)
        baixo.addWidget(fechar)
        lay.addLayout(baixo)

        for tecla, cat in (("A", "a"), ("1", "a"), ("B", "b"), ("2", "b"), ("C", "c"), ("3", "c"),
                           ("D", "d"), ("4", "d"), ("N", R.NAO_AVALIAVEL)):
            QShortcut(QKeySequence(tecla), self, activated=lambda c=cat: self.responder(c))
        QShortcut(QKeySequence(Qt.Key_Right), self, activated=lambda: self.ir(self.i + 1))
        QShortcut(QKeySequence(Qt.Key_Left), self, activated=lambda: self.ir(self.i - 1))

        self._habilitar(False)
        self.atualizar_concordancia()
        self.resize(720, 520)

    # ------------------------------------------------------------- preferências
    def _pref(self, chave, padrao):
        try:
            v = self.settings.get(chave, padrao)
        except Exception:  # noqa: BLE001
            return padrao
        return padrao if v is None else v

    def _gravar_pref(self, chave, valor) -> None:
        try:
            self.settings.set(chave, valor)
            self.settings.save()
        except Exception:  # noqa: BLE001
            log.debug("revisão de densidade: preferência", exc_info=True)

    # ------------------------------------------------------------- a fila
    def _revisados(self) -> dict[str, dict]:
        try:
            return {r["study_uid"]: r for r in self.repo.revisoes_densidade(self.usuario)}
        except Exception:  # noqa: BLE001
            log.debug("revisão de densidade: lista", exc_info=True)
            return {}

    def montar_fila(self) -> list:
        de = self.de.date().toString("yyyyMMdd")
        ate = self.ate.date().toString("yyyyMMdd")
        try:
            linhas = self.repo.search_studies(modality="MG", date_from=de, date_to=ate, limit=5000)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, tr("Revisão da densidade mamária"), tr("Não consegui buscar os exames: {}")
                                .format(e))
            return []
        mg = [r for r in linhas if "MG" in (r.modalities or "").upper().replace("\\", "/").split("/")]
        feitos = self._revisados() if self.ck_novos.isChecked() else {}
        self.fila = [r for r in mg if r.study_uid not in feitos]
        self.fila.sort(key=lambda r: (r.study_date or "", r.study_uid), reverse=True)
        self.i = -1
        if not self.fila:
            self.lb_fila.setText(tr("Nenhuma mamografia {} neste período.").format(
                tr("por revisar") if self.ck_novos.isChecked() else tr("no banco")))
            self._habilitar(False)
            self.lb_exame.setText("")
            self.lb_sugestao.setText("")
            self.lb_avisos.setText("")
            return self.fila
        self.ir(0)
        return self.fila

    def _habilitar(self, sim: bool) -> None:
        for b in (*self.botoes.values(), self.bt_na, self.bt_pular, self.bt_ant):
            b.setEnabled(sim)

    def _aba(self, uid: str):
        try:
            return next((t for t in self.main.all_viewer_tabs() if getattr(t, "study_uid", "") == uid), None)
        except Exception:  # noqa: BLE001
            return None

    def ir(self, i: int) -> None:
        if not self.fila:
            return
        i = max(0, min(i, len(self.fila) - 1))
        anterior = self.fila[self.i].study_uid if 0 <= self.i < len(self.fila) else ""
        self.i = i
        uid = self.fila[i].study_uid
        if anterior and anterior != uid and self.ck_fechar.isChecked() and anterior in self._abertas:
            tab = self._aba(anterior)
            if tab is not None:
                try:
                    self.main.fechar_aba(tab)
                except Exception:  # noqa: BLE001
                    log.debug("revisão de densidade: fechar aba", exc_info=True)
            self._abertas.discard(anterior)
        if self.main is not None and self._aba(uid) is None:
            try:
                self.main.open_study(uid)
                self._abertas.add(uid)
            except Exception:  # noqa: BLE001
                log.debug("revisão de densidade: abrir exame", exc_info=True)
        self._habilitar(True)
        self.bt_ant.setEnabled(i > 0)
        self.bt_pular.setEnabled(i < len(self.fila) - 1)
        r = self.fila[i]
        data = r.study_date or ""
        data = f"{data[6:8]}/{data[4:6]}/{data[:4]}" if len(data) == 8 else data
        self.lb_exame.setText(f"{r.patient_name} — {data} — {r.description or ''}".strip(" —"))
        self.lb_fila.setText(tr("Exame {} de {} na fila").format(i + 1, len(self.fila)))
        self._marcar_resposta(self.respostas.get(uid, ""))
        self.mostrar_sugestao()
        self._calcular(uid)
        if i + 1 < len(self.fila):                # adianta o próximo, para não esperar
            self._calcular(self.fila[i + 1].study_uid)
        self.raise_()
        self.activateWindow()

    def _marcar_resposta(self, cat: str) -> None:
        for c, b in self.botoes.items():
            b.setStyleSheet("font-weight:bold;border:2px solid #2e86de" if c == cat else "")
        self.bt_na.setStyleSheet("font-weight:bold;border:2px solid #2e86de" if cat == R.NAO_AVALIAVEL else "")

    # ------------------------------------------------------------- a sugestão
    def controle(self, uid: str) -> bool:
        return R.de_controle(uid, self.usuario, self.sp_controle.value() / 100.0)

    def _calcular(self, uid: str) -> None:
        if uid in self.sugestoes or uid in self._threads:
            return
        t = _Sugeridor(self.repo, uid, self.dados, self)
        t.pronto.connect(self._chegou)
        t.finished.connect(lambda u=uid: self._threads.pop(u, None))
        self._threads[uid] = t
        t.start()

    def _chegou(self, uid: str, s: dict) -> None:
        self.sugestoes[uid] = s
        if uid in self._sem_sugestao and uid in self.respostas:
            self._sem_sugestao.discard(uid)
            self._gravar(uid, self.respostas[uid], controle=True)
        if 0 <= self.i < len(self.fila) and self.fila[self.i].study_uid == uid:
            self.mostrar_sugestao()

    def texto_da_sugestao(self, s: dict) -> str:
        partes = []
        if s.get("nyu"):
            probs = s.get("nyu_probs") or []
            p = max(probs) if probs else None
            conf = f" ({100 * p:.0f}%)" if p is not None else ""
            partes.append(f"<b>{tr('Rede (NYU)')}:</b> {s['nyu'].upper()}{conf}")
        else:
            partes.append(f"<b>{tr('Rede (NYU)')}:</b> — {s.get('nyu_aviso') or ''}")
        if s.get("aparelho"):
            partes.append(f"<span style='color:gray'>{tr('Aparelho')}: {s['aparelho']}</span>")
        return "<br>".join(partes)

    def mostrar_sugestao(self) -> None:
        if not (0 <= self.i < len(self.fila)):
            return
        uid = self.fila[self.i].study_uid
        s = self.sugestoes.get(uid)
        respondido = uid in self.respostas
        if self.controle(uid) and not respondido:
            self.lb_sugestao.setText(tr("<i>Exame de controle: a sugestão aparece depois da sua resposta.</i>"))
            self.lb_avisos.setText("")
            return
        if s is None:
            self.lb_sugestao.setText(tr("<i>Calculando a sugestão…</i>"))
            self.lb_avisos.setText("")
            return
        self.lb_sugestao.setText(self.texto_da_sugestao(s))
        self.lb_avisos.setText("\n".join(s.get("avisos") or []))

    # ------------------------------------------------------------- a resposta
    def _gravar(self, uid: str, cat: str, controle: bool) -> None:
        s = self.sugestoes.get(uid) or {}
        try:
            R.confirmar(self.repo, uid, s, cat, self.usuario, controle=controle)   # no exame e na revisão
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, tr("Revisão da densidade mamária"), tr("Não gravei a revisão: {}").format(e))
            return

    def responder(self, cat: str) -> None:
        if not (0 <= self.i < len(self.fila)):
            return
        uid = self.fila[self.i].study_uid
        mostrada = (not self.controle(uid)) and uid in self.sugestoes
        controle = not mostrada                  # sem a sugestão à vista, a resposta é "cega"
        if uid not in self.sugestoes:
            self._sem_sugestao.add(uid)
        self.respostas[uid] = cat
        self._gravar(uid, cat, controle)
        self._marcar_resposta(cat)
        self.atualizar_concordancia()
        if self.i < len(self.fila) - 1:
            self.ir(self.i + 1)
        else:
            self.mostrar_sugestao()
            self.lb_fila.setText(tr("Fim da fila: {} exame(s) revisado(s) nesta sessão.").format(len(self.respostas)))

    # ------------------------------------------------------------- concordância e saída
    def atualizar_concordancia(self) -> None:
        try:
            revs = self.repo.revisoes_densidade(self.usuario)
        except Exception:  # noqa: BLE001
            revs = []
        self.lb_conc.setText(R.texto_da_concordancia(R.concordancia(revs)) if revs
                             else tr("Nenhuma revisão ainda."))

    def exportar(self) -> None:
        try:
            revs = self.repo.revisoes_densidade(self.usuario)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, tr("Revisão da densidade mamária"), str(e))
            return
        if not revs:
            QMessageBox.information(self, tr("Revisão da densidade mamária"), tr("Nenhuma revisão para exportar."))
            return
        destino, _ = QFileDialog.getSaveFileName(self, tr("Exportar CSV…"), "revisao_densidade.csv", "CSV (*.csv)")
        if not destino:
            return
        with open(destino, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerows(R.linhas_csv(revs))

    def closeEvent(self, event) -> None:  # noqa: D102, N802
        for t in list(self._threads.values()):
            t.stop.set()
            t.wait(3000)
        super().closeEvent(event)


def abrir(main, repo=None, settings=None):
    """Abre (ou traz para a frente) a janela da revisão. Uma por janela principal."""
    j = getattr(main, "_revisao_densidade", None)
    if j is not None and j.isVisible():
        j.raise_()
        j.activateWindow()
        return j
    j = RevisaoDensidadeJanela(main, repo or main.repo, settings or main.settings)
    main._revisao_densidade = j
    j.setAttribute(Qt.WA_DeleteOnClose, False)
    j.show()
    return j
