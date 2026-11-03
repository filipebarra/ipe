"""Painel da difusão (0.99.37): ADC, DWI sintética e a tabela por ROI, em qualquer RM.

Abre pelo botão **Difusão** da barra (RM com série de difusão) ou por Aplicações. Não é modal: dá para
desenhar a ROI no quadro e apertar "Medir a ROI selecionada" sem fechar.

O cálculo e as regras estão em `imaging/difusao.py`; a gravação, em `imaging/difusao_saida.py`.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QProgressDialog, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ipe.imaging import difusao as DF

log = logging.getLogger(__name__)

from ipe.imaging.measure import ROI_KINDS as ROIS       # elipse, polígono (mão livre), retângulo


def series_candidatas(series) -> list:
    """As séries de difusão do exame (pela descrição), primeiro; as outras RM depois (o aparelho que
    não escreve DWI na descrição não pode trancar a ferramenta)."""
    mr = [s for s in series if (s.modality or "").upper() == "MR"]
    sim = [s for s in mr if DF.parece_difusao(s.description or "")]
    return sim + [s for s in mr if s not in sim and not DF.e_mapa_adc(s.description or "")]


def adc_do_aparelho(repo, series, study_uid: str):
    """A série de ADC que o aparelho gravou no exame (não a nossa), se houver."""
    for s in series:
        d = s.description or ""
        if s.study_uid == study_uid and DF.e_mapa_adc(d) and "Ipê" not in d and "Ipe" not in d:
            return s.series_uid
    return None


class DifusaoPainel(QDialog):
    def __init__(self, tab, parent=None):
        super().__init__(parent or tab, Qt.Window)
        self.tab = tab
        self.repo = tab.repo
        self.serie: DF.SerieDifusao | None = None
        self.mapa: DF.Mapa | None = None
        self.setWindowTitle("Difusão (ADC)")
        self.resize(720, 640)
        lay = QVBoxLayout(self)
        topo = QFormLayout()
        self.c_serie = QComboBox()
        self.cands = series_candidatas(getattr(tab, "series", []) or [])
        for s in self.cands:
            self.c_serie.addItem(f"{s.series_number} · {s.description} ({s.num_images} im)", s.series_uid)
        self.c_serie.currentIndexChanged.connect(self.ler)
        topo.addRow("Série de difusão:", self.c_serie)
        self.w_bs = QWidget()
        self.l_bs = QHBoxLayout(self.w_bs)
        self.l_bs.setContentsMargins(0, 0, 0, 0)
        topo.addRow("Valores de b:", self.w_bs)
        self.e_bs = QLineEdit()
        self.e_bs.setPlaceholderText("ex.: 0, 1000 — na ordem em que se repetem em cada corte")
        self.e_bs.editingFinished.connect(self.ler)
        self.lab_bs = QLabel("Digitar os b:")
        topo.addRow(self.lab_bs, self.e_bs)
        self.s_limiar = QSpinBox(minimum=1, maximum=40, value=int(DF.LIMIAR_SINAL * 100), suffix=" %")
        self.s_limiar.setToolTip("Pixel com sinal do b0 abaixo desta fração do percentil 99 é ruído e fica 0")
        topo.addRow("Limiar de ruído:", self.s_limiar)
        self.s_r2 = QDoubleSpinBox(minimum=0, maximum=0.99, singleStep=0.05, value=DF.R2_MINIMO, decimals=2)
        self.s_r2.setToolTip("Com 3 b ou mais: pixel com ajuste pior que isto (R²) fica 0")
        topo.addRow("R² mínimo (3 b ou mais):", self.s_r2)
        lay.addLayout(topo)
        self.avisos = QLabel()
        self.avisos.setWordWrap(True)
        lay.addWidget(self.avisos)
        bot = QHBoxLayout()
        self.b_adc = QPushButton("Calcular e gravar o ADC")
        self.b_adc.clicked.connect(self.gravar_adc)
        bot.addWidget(self.b_adc)
        self.s_bsint = QSpinBox(minimum=50, maximum=5000, singleStep=100, value=1500)
        self.s_bsint.setPrefix("b = ")
        bot.addWidget(QLabel("DWI sintética:"))
        bot.addWidget(self.s_bsint)
        self.b_sint = QPushButton("Gravar")
        self.b_sint.setToolTip("S(b) = S0·e^(−ADC·b), marcada como sintética — não use para calcular ADC")
        self.b_sint.clicked.connect(self.gravar_sintetica)
        bot.addWidget(self.b_sint)
        bot.addStretch(1)
        lay.addLayout(bot)
        lay.addWidget(QLabel("<b>Medir numa ROI</b> — desenhe uma ROI (elipse, retângulo, mão livre) num quadro com a "
                             "difusão, o ADC daqui ou o do aparelho, e escolha-a."))
        mb = QHBoxLayout()
        self.b_medir = QPushButton("Medir a ROI selecionada")
        self.b_medir.clicked.connect(self.medir)
        self.b_laudo = QPushButton("Mandar ao laudo")
        self.b_laudo.clicked.connect(self.ao_laudo)
        mb.addWidget(self.b_medir)
        mb.addWidget(self.b_laudo)
        mb.addStretch(1)
        lay.addLayout(mb)
        self.tabela = QTableWidget(0, 7)
        self.tabela.setHorizontalHeaderLabels(["Mapa", "Média", "DP", "Mediana", "Mín", "Máx", "Obs."])
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.horizontalHeader().setStretchLastSection(True)
        from ipe.ui.tabelas import colunas_ajustaveis
        colunas_ajustaveis(self.tabela)
        lay.addWidget(self.tabela, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self._linhas: list[dict] = []
        self.ler()

    # ------------------------------------------------------------------ a série
    def serie_escolhida(self) -> str:
        return self.c_serie.currentData() or ""

    def _bs_digitados(self) -> list[float] | None:
        t = self.e_bs.text().replace(";", ",").strip()
        if not t:
            return None
        try:
            return [float(x) for x in t.split(",") if x.strip()]
        except ValueError:
            return None

    def ler(self) -> None:
        uid = self.serie_escolhida()
        self.mapa = None
        while self.l_bs.count():
            w = self.l_bs.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self.caixas: dict[float, QCheckBox] = {}
        if not uid:
            self.avisos.setText("Nenhuma série de RM neste exame.")
            self._botoes()
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.serie = DF.ler_serie(self.repo, uid, self._bs_digitados())
        except Exception as e:  # noqa: BLE001
            log.exception("ler a difusão")
            self.serie = None
            self.avisos.setText(f"Não deu para ler a série: {e}")
            self._botoes()
            return
        finally:
            QApplication.restoreOverrideCursor()
        for b in self.serie.bs:
            cb = QCheckBox(DF._b(b))
            cb.setChecked(True)
            cb.toggled.connect(self._botoes)
            self.caixas[b] = cb
            self.l_bs.addWidget(cb)
        self.l_bs.addStretch(1)
        self.e_bs.setVisible(self.serie.sem_b or bool(self.e_bs.text()))
        self.lab_bs.setVisible(self.e_bs.isVisible())
        self.s_r2.setEnabled(len(self.serie.bs) >= 3)
        txt = f"{self.serie.n} corte(s), b: {', '.join(DF._b(b) for b in self.serie.bs) or '—'}."
        if self.serie.avisos:
            txt += "<br>" + "<br>".join(f"⚠ {a}" for a in self.serie.avisos)
        self.avisos.setText(txt)
        self._botoes()

    def bs_escolhidos(self) -> list[float]:
        return [b for b, cb in getattr(self, "caixas", {}).items() if cb.isChecked()]

    def _botoes(self) -> None:
        ok = self.serie is not None and len(self.bs_escolhidos()) >= 2
        self.b_adc.setEnabled(ok)
        self.b_sint.setEnabled(ok)
        self.b_medir.setEnabled(ok)

    # ------------------------------------------------------------------ calcular
    def calcular(self) -> DF.Mapa | None:
        if self.mapa is not None and self.mapa.bs == sorted(self.bs_escolhidos()) \
                and abs(self.mapa_limiar - self.s_limiar.value()) < 1e-9:
            return self.mapa
        if self.serie is None:
            return None
        prog = QProgressDialog("Calculando o ADC…", "Parar", 0, max(1, self.serie.n), self)
        prog.setWindowTitle("Difusão")
        prog.setMinimumDuration(400)

        def andar(feitos, total):
            prog.setMaximum(max(1, total))
            prog.setValue(feitos)
            QApplication.processEvents()
            return not prog.wasCanceled()
        try:
            self.mapa = DF.calcular(self.serie, self.bs_escolhidos(), self.s_limiar.value() / 100.0,
                                    self.s_r2.value(), andar)
            self.mapa_limiar = self.s_limiar.value()
        except InterruptedError:
            self.status.setText("Cálculo interrompido.")
            return None
        except Exception as e:  # noqa: BLE001
            log.exception("calcular o ADC")
            QMessageBox.warning(self, "Difusão", f"Não deu para calcular o ADC: {e}")
            return None
        finally:
            prog.close()
        return self.mapa

    def _gravar(self, volume, descricao: str, tipo: str, b=None) -> str | None:
        from ipe.imaging import difusao_saida as SAIDA
        db = getattr(self.repo, "db", None)
        storage = getattr(self.tab, "storage_root", None)
        if db is None or storage is None:
            QMessageBox.information(self, "Difusão", "Este banco não aceita série nova daqui.")
            return None
        try:
            uid, _sops = SAIDA.gravar(db, storage, self.mapa, volume, descricao, tipo, b)
        except Exception as e:  # noqa: BLE001
            log.exception("gravar a difusão")
            QMessageBox.warning(self, "Difusão", f"Não deu para gravar: {e}")
            return None
        study = (self.repo.series_meta(self.serie_escolhida()) or {}).get("study_uid", "")
        try:
            self.tab.rescan(study)
            if self.tab.active is not None:
                self.tab.load_series_into(self.tab.active, uid, como_serie=True)
        except Exception:  # noqa: BLE001
            log.exception("abrir a série da difusão")
        try:
            from ipe.central.client_repo import upload_if_client
            upload_if_client(self.repo, study)
        except Exception:  # noqa: BLE001
            pass
        return uid

    def gravar_adc(self) -> str | None:
        m = self.calcular()
        if m is None:
            return None
        bs = "-".join(str(int(b)) for b in m.bs)
        uid = self._gravar(m.adc, f"ADC (Ipê) · b{bs} · 10^-6 mm²/s", "adc")
        if uid:
            self.status.setText(f"ADC gravado no exame ({m.adc.shape[0]} cortes, b {bs}), aberto no quadro ativo. "
                                "O valor do pixel é o ADC em ×10⁻⁶ mm²/s: as ROIs de sempre medem nele.")
        return uid

    def gravar_sintetica(self) -> str | None:
        m = self.calcular()
        if m is None:
            return None
        b = self.s_bsint.value()
        uid = self._gravar(DF.dwi_sintetica(m, b), f"DWI sintética b{b} (Ipê)", "sintetica", b)
        if uid:
            self.status.setText(f"DWI sintética b{b} gravada (a partir de b {', '.join(str(int(x)) for x in m.bs)}). "
                                "É uma imagem calculada: não serve para calcular ADC.")
        return uid

    # ------------------------------------------------------------------ medir
    def _roi_escolhida(self):
        vp = getattr(self.tab, "active", None)
        if vp is None:
            return None, None, None
        ann = getattr(vp, "selected", None)
        if ann is None or ann.kind not in ROIS:
            rois = [a for a in getattr(vp, "annotations", []) if a.kind in ROIS]
            f = vp.current_frame() if hasattr(vp, "current_frame") else None
            rois = [a for a in rois if f is not None and a.frame_key[0] == f.sop_uid] or rois
            ann = rois[-1] if rois else None
        f = vp.current_frame() if hasattr(vp, "current_frame") else None
        img = getattr(vp, "image", None)
        return vp, ann, (f, img)

    def medir(self) -> list[dict]:
        from ipe.imaging.measure import roi_mask
        vp, ann, (f, _img) = self._roi_escolhida()
        if ann is None or f is None or f.position is None:
            self.status.setText("Desenhe uma ROI (elipse, retângulo, mão livre) num quadro e selecione-a.")
            return []
        m = self.calcular()
        if m is None:
            return []
        k = m.em(f.position, tol=max(1.0, 0.5 * self._espessura()))
        if k is None:
            self.status.setText("A ROI está num corte que não existe na difusão (outra posição ou outro plano).")
            return []
        forma = m.adc[k].shape
        import numpy as np
        try:
            r = roi_mask(ann.kind, ann.points, forma)
        except Exception as e:  # noqa: BLE001
            self.status.setText(f"A ROI não serve aqui: {e}")
            return []
        mascara = None
        if r is not None:
            (fy, fx), local = r
            mascara = np.zeros(forma, dtype=bool)
            mascara[fy, fx] = local
        if mascara is None or not mascara.any():
            self.status.setText("A ROI não tem pixels nesta grade (desenhada noutra série com outra matriz?).")
            return []
        aparelho = self._adc_aparelho(m.cortes[k].posicao, forma)
        self._linhas = DF.tabela_da_roi(m, k, mascara, aparelho)
        self.tabela.setRowCount(len(self._linhas))
        for r, ln in enumerate(self._linhas):
            vals = [ln["mapa"]] + [f"{ln[c]:.0f}" if isinstance(ln.get(c), float) else "" for c in
                                   ("media", "dp", "mediana", "min", "max")] + [ln.get("obs", "")]
            for c, v in enumerate(vals):
                self.tabela.setItem(r, c, QTableWidgetItem(str(v)))
        self.status.setText(f"ROI no corte {k + 1} de {len(m.cortes)} ({int(mascara.sum())} pixels).")
        return self._linhas

    def _espessura(self) -> float:
        try:
            return float((self.repo.series_meta(self.serie_escolhida()) or {}).get("slice_thickness") or 4.0)
        except (TypeError, ValueError):
            return 4.0

    def _adc_aparelho(self, posicao, forma):
        study = (self.repo.series_meta(self.serie_escolhida()) or {}).get("study_uid", "")
        uid = adc_do_aparelho(self.repo, getattr(self.tab, "series", []) or [], study)
        if not uid:
            return None
        import numpy as np
        for it in self.repo.instances_for_series(uid):
            pos = it.get("position")
            if pos is None:
                continue
            try:
                p = [float(x) for x in (pos if isinstance(pos, (list, tuple)) else str(pos).split("\\"))]
            except ValueError:
                continue
            if np.linalg.norm(np.asarray(p) - np.asarray(posicao)) <= 1.0:
                px = DF._pixels(it["path"])
                return px if px.shape == forma else None
        return None

    def texto(self) -> str:
        if not self._linhas:
            return ""
        from ipe.core.i18n import tr          # a frase vai para o laudo, fora do Qt: traduz aqui
        partes = []
        for ln in self._linhas:
            if "ADC" in ln["mapa"] and isinstance(ln.get("media"), float):
                nome = tr(ln["mapa"].split(" ×")[0])
                partes.append(tr(f"{nome}: média {ln['media']:.0f} ± {ln['dp']:.0f}, "
                                 f"mínimo {ln['min']:.0f} ×10⁻⁶ mm²/s"))
        if not partes:
            return ""
        b = ", ".join(DF._b(x) for x in (self.mapa.bs if self.mapa else []))
        lista = "; ".join(partes)
        return tr(f"Difusão ({b}): {lista}.")

    def ao_laudo(self) -> None:
        t = self.texto()
        if not t:
            self.status.setText("Meça uma ROI primeiro.")
            return
        self.tab.mandar_texto_ao_laudo(t)


def abrir(tab) -> DifusaoPainel:
    d = getattr(tab, "_difusao", None)
    try:
        import shiboken6
        viva = d is not None and shiboken6.isValid(d)
    except Exception:  # noqa: BLE001
        viva = d is not None
    if not viva:
        d = DifusaoPainel(tab)
        tab._difusao = d
    d.show()
    d.raise_()
    return d
