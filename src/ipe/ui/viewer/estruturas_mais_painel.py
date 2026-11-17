"""A aba "Mais ferramentas" do painel Estruturas (0.100.67): tesoura, contorno por nível, segmentação pelo maior
diâmetro, oco, suavização, limiar automático (Otsu), dividir ilhas em estruturas e crescer das sementes.

É um complemento (mixin) de `EstruturasPainel`: usa a lista, a grade, os limites e o desfazer de lá; as ferramentas de
mouse entram pelo mesmo canal do pincel (a ferramenta "pincel" do quadro), conforme o modo ligado aqui.
"""
from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout, QGroupBox, QLabel, QMessageBox, QPushButton,
    QSpinBox, QVBoxLayout, QWidget,
)

from ipe.core.i18n import tr
from ipe.imaging import estruturas as ES
from ipe.imaging import estruturas_mais as EM

log = logging.getLogger(__name__)


class MaisFerramentas:
    # ================================================================ interface
    def _iniciar_mais(self) -> None:
        self._acao = None                   # o gesto em curso (tesoura, nível, diâmetro)
        self._diam = None                   # a última segmentação pelo diâmetro (para o "Ajuste" recalcular)

    def _montar_mais(self) -> QWidget:
        pag = QWidget()
        lay = QVBoxLayout(pag)

        # ---------------- tesoura
        gt = QGroupBox("Tesoura")
        g = QGridLayout(gt)
        self.b_tesoura = QPushButton("Tesoura")
        self.b_tesoura.setCheckable(True)
        self.b_tesoura.setToolTip("Desenhe uma forma sobre a imagem: a estrutura escolhida é cortada (ou preenchida) "
                                  "por ela, só neste corte ou atravessando todos os cortes.")
        self.b_tesoura.toggled.connect(lambda on: self._modo_mudou(self.b_tesoura, on))
        self.c_tes_acao = QComboBox()
        for k, txt in EM.ACOES_TESOURA.items():
            self.c_tes_acao.addItem(txt, k)
        self.c_tes_forma = QComboBox()
        for txt, k in (("Forma livre", "livre"), ("Retângulo", "retangulo"), ("Elipse", "elipse")):
            self.c_tes_forma.addItem(txt, k)
        self.c_tes_alcance = QComboBox()
        for k, txt in EM.ALCANCES.items():
            self.c_tes_alcance.addItem(txt, k)
        g.addWidget(self.b_tesoura, 0, 0)
        g.addWidget(self.c_tes_acao, 0, 1)
        g.addWidget(self.c_tes_forma, 0, 2)
        g.addWidget(self.c_tes_alcance, 0, 3)
        lay.addWidget(gt)

        # ---------------- contorno por nível e diâmetro
        gn = QGroupBox("Contornar com um clique")
        n = QGridLayout(gn)
        self.b_nivel = QPushButton("Contorno por nível")
        self.b_nivel.setCheckable(True)
        self.b_nivel.setToolTip("Clique e arraste sobre a lesão: entra a região do corte, ligada ao ponto, limitada "
                                "pela linha de mesma intensidade que passa por ele. Perto da borda pega a lesão toda; "
                                "mais para dentro, só o miolo. Solte quando o contorno estiver bom.")
        self.b_nivel.toggled.connect(lambda on: self._modo_mudou(self.b_nivel, on))
        self.c_nivel_apaga = QCheckBox("apagar em vez de somar")
        n.addWidget(self.b_nivel, 0, 0, 1, 2)
        n.addWidget(self.c_nivel_apaga, 0, 2, 1, 2)
        self.b_diam = QPushButton("Pelo maior diâmetro")
        self.b_diam.setCheckable(True)
        self.b_diam.setToolTip("Trace o maior diâmetro da lesão (de borda a borda): o Ipê devolve o contorno em 3D, "
                               "numa estrutura nova, com o maior diâmetro, o eixo curto e o volume. Se ficou pequeno "
                               "ou grande, mude o Ajuste — o contorno é refeito na hora.")
        self.b_diam.toggled.connect(lambda on: self._modo_mudou(self.b_diam, on))
        self.s_ajuste = QSpinBox(minimum=-100, maximum=100, value=0, singleStep=10, suffix=" %")
        self.s_ajuste.setToolTip("Negativo: contorno mais justo (menor). Positivo: mais solto (maior).")
        self.s_ajuste.valueChanged.connect(lambda _v: self._recalcular_diametro())
        n.addWidget(self.b_diam, 1, 0, 1, 2)
        n.addWidget(QLabel("Ajuste:"), 1, 2, alignment=Qt.AlignRight | Qt.AlignVCenter)
        n.addWidget(self.s_ajuste, 1, 3)
        self.l_diam = QLabel()
        self.l_diam.setWordWrap(True)
        self.l_diam.setTextInteractionFlags(Qt.TextSelectableByMouse)
        n.addWidget(self.l_diam, 2, 0, 1, 4)
        lay.addWidget(gn)

        # ---------------- oco e suavização
        gs = QGroupBox("Oco e suavização (na estrutura escolhida)")
        s = QGridLayout(gs)
        b_oco = QPushButton("Oco (casca)")
        b_oco.setToolTip("Troca a estrutura pela casca dela, com a espessura ao lado (a parede de um órgão, a borda "
                         "de uma lesão, o anel em volta dela).")
        b_oco.clicked.connect(self._oco)
        self.s_oco = QDoubleSpinBox(minimum=0.5, maximum=50, value=3.0, singleStep=0.5, suffix=" mm")
        self.c_oco_onde = QComboBox()
        for k, txt in EM.ONDE_OCO.items():
            self.c_oco_onde.addItem(txt, k)
        s.addWidget(b_oco, 0, 0)
        s.addWidget(self.s_oco, 0, 1)
        s.addWidget(self.c_oco_onde, 0, 2, 1, 2)
        b_suav = QPushButton("Suavizar")
        b_suav.clicked.connect(self._suavizar)
        self.s_suav = QDoubleSpinBox(minimum=0.5, maximum=20, value=2.0, singleStep=0.5, suffix=" mm")
        self.c_suav = QComboBox()
        for k, txt in EM.SUAVIZACOES.items():
            self.c_suav.addItem(txt, k)
        s.addWidget(b_suav, 1, 0)
        s.addWidget(self.s_suav, 1, 1)
        s.addWidget(self.c_suav, 1, 2, 1, 2)
        lay.addWidget(gs)

        # ---------------- limiar e ilhas
        gl = QGroupBox("Limiar e ilhas")
        ll = QGridLayout(gl)
        b_otsu = QPushButton("Limiar automático (Otsu)")
        b_otsu.setToolTip("Acha sozinho o corte que melhor separa o claro do escuro (na série; com o limite "
                          "“Só dentro de”, só dentro dessa estrutura) e põe na faixa ao lado.")
        b_otsu.clicked.connect(self._otsu)
        self.c_otsu_lado = QComboBox()
        for txt, k in (("acima do limiar", "acima"), ("abaixo do limiar", "abaixo")):
            self.c_otsu_lado.addItem(txt, k)
        ll.addWidget(b_otsu, 0, 0, 1, 2)
        ll.addWidget(self.c_otsu_lado, 0, 2, 1, 2)
        b_faixa = QPushButton("Preencher pela faixa")
        b_faixa.setToolTip("A estrutura escolhida passa a ser tudo o que tem intensidade na faixa (respeita a Área "
                           "dos limites da edição: use “Só dentro de” para não pegar o exame inteiro).")
        b_faixa.clicked.connect(self._preencher_faixa)
        self.s_f_lo = QDoubleSpinBox(minimum=-1e6, maximum=1e6, decimals=1)
        self.s_f_hi = QDoubleSpinBox(minimum=-1e6, maximum=1e6, decimals=1)
        ll.addWidget(b_faixa, 1, 0)
        ll.addWidget(self.s_f_lo, 1, 1)
        ll.addWidget(QLabel("a"), 1, 2, alignment=Qt.AlignCenter)
        ll.addWidget(self.s_f_hi, 1, 3)
        b_div = QPushButton("Dividir ilhas em estruturas")
        b_div.setToolTip("Cada pedaço solto vira uma estrutura (a escolhida fica com o maior): uma lesão por linha, "
                         "cada uma com o seu volume. Os pedaços menores que o valor ao lado são apagados.")
        b_div.clicked.connect(self._dividir)
        self.s_div = QDoubleSpinBox(minimum=0.0, maximum=1000, value=0.05, decimals=3, suffix=" mL")
        ll.addWidget(b_div, 2, 0, 1, 3)
        ll.addWidget(self.s_div, 2, 3)
        lay.addWidget(gl)

        # ---------------- sementes
        gg = QGroupBox("Crescer das sementes")
        gl2 = QGridLayout(gg)
        dica = QLabel("Traços dentro da lesão numa estrutura; em outra (“Fundo”), traços no que está em volta. "
                      "O espaço é repartido entre elas pela intensidade.")
        dica.setWordWrap(True)
        gl2.addWidget(dica, 0, 0, 1, 4)
        b_sem = QPushButton("Crescer das sementes")
        b_sem.setToolTip("Usa todas as estruturas visíveis como sementes (as travadas servem de semente e não "
                         "mudam). Desfazer: em cada estrutura.")
        b_sem.clicked.connect(self.crescer_sementes)
        self.s_margem = QDoubleSpinBox(minimum=2, maximum=100, value=15, singleStep=5, suffix=" mm", decimals=0)
        self.s_margem.setToolTip("Até onde, além das sementes, o crescimento pode ir.")
        gl2.addWidget(b_sem, 1, 0, 1, 2)
        gl2.addWidget(QLabel("Margem:"), 1, 2, alignment=Qt.AlignRight | Qt.AlignVCenter)
        gl2.addWidget(self.s_margem, 1, 3)
        lay.addWidget(gg)
        lay.addStretch(1)
        return pag

    # ================================================================ modos de mouse
    def _botoes_de_modo(self) -> dict:
        return {"tesoura": self.b_tesoura, "nivel": self.b_nivel, "diametro": self.b_diam}

    def modo(self) -> str:
        """A ferramenta de mouse desta aba que está ligada ("" = nenhuma: vale o pincel)."""
        for nome, b in self._botoes_de_modo().items():
            if b.isChecked():
                return nome
        return ""

    def _soltar_modos(self) -> None:
        for b in self._botoes_de_modo().values():
            b.blockSignals(True)
            b.setChecked(False)
            b.blockSignals(False)
        self._acao = None

    def _modo_mudou(self, botao, on: bool) -> None:
        if on:
            for b in (*self._botoes_de_modo().values(), self.b_pincel, self.b_borracha):
                if b is not botao:
                    b.blockSignals(True)
                    b.setChecked(False)
                    b.blockSignals(False)
            if self.tab.left_tool != "pincel":
                self._ferramenta_antes = self.tab.left_tool
                self.tab.set_left_tool("pincel")
            for vp in self.tab.viewports:
                vp.pincel_raio_mm = 0.0            # sem o círculo do pincel
                vp.traco_temp = None
                vp.update()
        elif not self.modo():
            self._acao = None
            self._soltar_ferramenta()

    def _pincel_mais(self, vp, u: float, v: float, etapa: str) -> None:
        if self.grade is None:
            return
        if vp.study_uid != self.study_uid:
            if etapa == "ini":
                self.tab.status_message.emit("As ferramentas de estruturas funcionam só no exame da série de referência.")
            return
        pl = vp.plane()
        if pl is None:
            if etapa == "ini":
                self.tab.status_message.emit("Este quadro não tem posição no espaço (sem plano): use um quadro de cortes.")
            return
        {"tesoura": self._gesto_tesoura, "nivel": self._gesto_nivel, "diametro": self._gesto_diametro}[self.modo()](
            vp, u, v, etapa, np.asarray(pl[3], float))

    @staticmethod
    def _mm(vp, u: float, v: float):
        return vp.pixel_to_patient(u - 0.5, v - 0.5)

    def _proibidas(self, e) -> list:
        return [x for x in self.estruturas if x.travada and x is not e]

    # ---------------------------------------------------------------- tesoura
    def _forma_uv(self, pts: list) -> list:
        forma = self.c_tes_forma.currentData()
        if forma == "livre" or len(pts) < 2:
            return pts
        (u0, v0), (u1, v1) = pts[0], pts[-1]
        if forma == "retangulo":
            return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        t = np.linspace(0, 2 * np.pi, 72, endpoint=False)
        cu, cv, ru, rv = (u0 + u1) / 2, (v0 + v1) / 2, abs(u1 - u0) / 2, abs(v1 - v0) / 2
        return [(cu + ru * np.cos(a), cv + rv * np.sin(a)) for a in t]

    def _gesto_tesoura(self, vp, u, v, etapa, normal) -> None:
        if etapa == "ini":
            self._acao = {"vp": vp, "pts": [(u, v)]}
            return
        a = self._acao
        if not a or a.get("vp") is not vp or "pts" not in a:
            return
        if self.c_tes_forma.currentData() == "livre":
            if (u, v) != a["pts"][-1]:
                a["pts"].append((u, v))
        else:
            a["pts"] = [a["pts"][0], (u, v)]
        uv = self._forma_uv(a["pts"])
        vp.traco_temp = (uv, True)
        vp.update()
        if etapa != "fim":
            return
        self._acao = None
        vp.traco_temp = None
        vp.update()
        mm = [self._mm(vp, x, y) for x, y in uv]
        if len(mm) < 3 or any(p is None for p in mm):
            return
        self.cortar_com_tesoura(np.asarray(mm, float), normal)

    def cortar_com_tesoura(self, poligono_mm, normal, acao: str | None = None, alcance: str | None = None) -> int:
        acao = acao or self.c_tes_acao.currentData()
        alcance = alcance or self.c_tes_alcance.currentData()
        if self.atual() is None:
            if acao != "preencher":
                self.tab.status_message.emit("Tesoura: escolha a estrutura a cortar.")
                return 0
            self.nova()
        lim = self.limites()
        r = self._operar("tesoura", lambda e: EM.tesoura(e, self.grade, poligono_mm, normal, acao, alcance,
                                                         limites=lim, proibidas=self._proibidas(e)))
        if r and acao == "preencher" and lim.sobrescrever and self._depois_de_somar(self.atual(), lim):
            self._redesenhar()
        return r

    # ---------------------------------------------------------------- contorno por nível
    def _gesto_nivel(self, vp, u, v, etapa, normal) -> None:
        if etapa == "ini":
            e = self.atual() or self.nova()
            if e is None:
                return
            if e.travada:
                self.tab.status_message.emit(f"“{e.nome}” está travada: destrave para editar.")
                self._acao = None
                return
            e.guardar_para_desfazer()
            self._acao = {"e": e, "foto": e._desfazer[-1], "mudou": 0, "achou": False}
        a = self._acao
        if not a or "foto" not in a:
            return
        e = a["e"]
        p = self._mm(vp, u, v)
        if p is not None:
            e.mascara, e.offset = ES.Estrutura._de_foto(a["foto"])
            res = EM.contorno_por_nivel(self.vol.data, self.grade, p, normal)
            a["achou"] = res is not None
            a["mudou"] = 0
            if res is not None:
                a["mudou"] = EM.aplicar_mascara(e, self.grade, res[0], res[1], apagar=self.c_nivel_apaga.isChecked(),
                                                limites=self.limites(), proibidas=self._proibidas(e))
            self._redesenhar()
            self._linha(e)
        if etapa != "fim":
            return
        self._acao = None
        if not a["mudou"]:
            if e._desfazer:
                e._desfazer.pop()
            self.tab.status_message.emit(
                "Contorno por nível: nada mudou." if a["achou"] else
                "Contorno por nível: a região tomaria mais da metade do corte — clique dentro da lesão, perto da borda.")
        else:
            self._gravado = False
            lim = self.limites()
            if not self.c_nivel_apaga.isChecked() and lim.sobrescrever and self._depois_de_somar(e, lim):
                self._redesenhar()
        self._selecionou()

    # ---------------------------------------------------------------- pelo maior diâmetro
    def _gesto_diametro(self, vp, u, v, etapa, normal) -> None:
        if etapa == "ini":
            self._acao = {"vp": vp, "uv": (u, v), "a": self._mm(vp, u, v)}
            return
        a = self._acao
        if not a or a.get("vp") is not vp or "uv" not in a:
            return
        vp.traco_temp = ([a["uv"], (u, v)], False)
        vp.update()
        if etapa != "fim":
            return
        self._acao = None
        vp.traco_temp = None
        vp.update()
        b = self._mm(vp, u, v)
        if a["a"] is None or b is None:
            return
        self.segmentar_pelo_diametro(a["a"], b, normal)

    def segmentar_pelo_diametro(self, a_mm, b_mm, normal=None) -> ES.Estrutura | None:
        """O contorno 3D da lesão a partir do maior diâmetro traçado: numa estrutura nova (ou na escolhida, se
        estiver vazia). Devolve a estrutura, ou None se não deu."""
        if self.grade is None:
            return None
        e = self.atual()
        if e is None or e.travada or not e.vazia():
            e = self.nova()
        e.guardar_para_desfazer()
        self._diam = {"e": e, "a": np.asarray(a_mm, float), "b": np.asarray(b_mm, float), "normal": normal,
                      "foto": e._desfazer[-1]}
        if not self._calcular_diametro():
            e._desfazer.pop()
            self._diam = None
            return None
        return e

    def _recalcular_diametro(self) -> None:
        d = self._diam
        if d and d["e"] in self.estruturas and not d["e"].travada:
            self._calcular_diametro()

    def _calcular_diametro(self) -> bool:
        d = self._diam
        e = d["e"]
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            r = EM.por_diametro(self.vol.data, self.grade, d["a"], d["b"], ajuste=self.s_ajuste.value() / 100.0,
                                normal=d["normal"])
        except Exception:  # noqa: BLE001
            log.exception("segmentação pelo diâmetro")
            r = None
        finally:
            QApplication.restoreOverrideCursor()
        if r is None or r.get("mascara") is None:
            motivo = tr((r or {}).get("aviso") or "a linha é curta demais ou está fora da série")
            self.l_diam.setText(f"Pelo maior diâmetro: não deu — {motivo}.")
            self.tab.status_message.emit(f"Pelo maior diâmetro: não deu — {motivo}.")
            return False
        e.mascara, e.offset = ES.Estrutura._de_foto(d["foto"])
        EM.aplicar_mascara(e, self.grade, r["mascara"], r["caixa"], limites=self.limites(),
                           proibidas=self._proibidas(e))
        e.alterada = True
        self._gravado = False
        m = EM.diametros_axiais(e, self.grade)
        tracado = float(np.linalg.norm(d["b"] - d["a"]))
        partes = [tr(f"<b>{e.nome}</b>: traçado {tracado:.1f} mm")]
        if m:
            partes.append(tr(f"maior diâmetro {m['maior_mm']:.1f} mm · eixo curto {m['curto_mm']:.1f} mm"))
        partes.append(tr(f"volume {e.ml(self.grade):.2f} mL"))
        txt = " · ".join(partes)
        if r.get("aviso"):
            atencao = tr(f"Atenção: {tr(r['aviso'])}.")
            txt += f"<br><span style='color:#e0a030'>{atencao}</span>"
        self.l_diam.setText(txt)
        self._redesenhar()
        self._linha(e)
        self._selecionou()
        return True

    # ================================================================ botões
    def _operar_somando(self, nome: str, fn) -> int:
        """Como `_operar`, para o que pode pôr voxel novo: depois respeita os limites e o sobrescrever."""
        r = self._operar(nome, fn)
        e = self.atual()
        if r and e is not None and e._desfazer:
            self._depois_de_somar(e, self.limites())
            self._redesenhar()
            self._linha(e)
            self._selecionou()
        return r

    def _oco(self) -> None:
        onde = self.c_oco_onde.currentData()
        fn = lambda e: EM.oco(e, self.grade, self.s_oco.value(), onde)   # noqa: E731
        r = self._operar("oco", fn) if onde == "dentro" else self._operar_somando("oco", fn)
        if not r:
            self.tab.status_message.emit("Oco: nada mudou (a espessura é menor que um voxel, ou a estrutura está vazia).")

    def _suavizar(self) -> None:
        self._operar_somando("suavizar", lambda e: EM.suavizar(e, self.grade, self.c_suav.currentData(),
                                                               self.s_suav.value()))

    def _otsu(self) -> float | None:
        if self.vol is None:
            return None
        lim = self.limites()
        dentro = lim.alvo if lim.area == "dentro" else None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            t = EM.otsu_da_regiao(self.vol.data, dentro)
            amostra = self.vol.data[dentro.caixa()][dentro.mascara] if dentro is not None and not dentro.vazia() \
                else self.vol.data[::2, ::4, ::4]
            lo, hi = float(np.min(amostra)), float(np.max(amostra))
        finally:
            QApplication.restoreOverrideCursor()
        if self.c_otsu_lado.currentData() == "acima":
            self.s_f_lo.setValue(t)
            self.s_f_hi.setValue(max(hi, t))
        else:
            self.s_f_lo.setValue(min(lo, t))
            self.s_f_hi.setValue(t)
        if dentro is not None and not dentro.vazia():
            self.tab.status_message.emit(f"Limiar de Otsu dentro de “{dentro.nome}”: {t:.1f}. Agora “Preencher pela faixa”.")
        else:
            self.tab.status_message.emit(f"Limiar de Otsu na série: {t:.1f}. Agora “Preencher pela faixa”.")
        return t

    def _preencher_faixa(self) -> None:
        if self.atual() is None:
            self.nova()
        lim = self.limites()
        lo, hi = sorted((self.s_f_lo.value(), self.s_f_hi.value()))
        r = self._operar("faixa", lambda e: EM.preencher_pela_faixa(e, self.grade, self.vol.data, lo, hi, lim,
                                                                    self._proibidas(e)))
        if r and lim.sobrescrever and self._depois_de_somar(self.atual(), lim):
            self._redesenhar()

    def _dividir(self) -> int:
        e = self.atual()
        if e is None or self.grade is None:
            return 0
        if e.travada:
            QMessageBox.information(self, "Estruturas", f"“{e.nome}” está travada.")
            return 0
        e.guardar_para_desfazer()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            novas = EM.dividir_ilhas(e, self.grade, self.s_div.value())
        finally:
            QApplication.restoreOverrideCursor()
        if not novas:
            e._desfazer.pop()
            self.tab.status_message.emit("Dividir ilhas: a estrutura tem um pedaço só.")
            return 0
        for x in novas:
            x.cor = ES.nova(self.estruturas).cor
            self.estruturas.append(x)
        self._gravado = False
        self._encher(e)
        self._redesenhar()
        self.tab.status_message.emit(f"Dividir ilhas: {len(novas) + 1} estruturas.")
        return len(novas)

    def crescer_sementes(self) -> dict:
        if self.grade is None:
            return {}
        sem = [e for e in self.estruturas if e.visivel and not e.vazia()]
        if len(sem) < 2:
            QMessageBox.information(
                self, "Estruturas", "Crescer das sementes precisa de duas estruturas ou mais com traços: por exemplo, "
                "uma com uns traços dentro da lesão e outra (“Fundo”) com uns traços no que está em volta.")
            return {}
        mexe = [e for e in sem if not e.travada]
        for e in mexe:
            e.guardar_para_desfazer()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            out = EM.crescer_de_sementes(self.estruturas, self.grade, self.vol.data, self.s_margem.value())
        except Exception as ex:  # noqa: BLE001
            log.exception("crescer das sementes")
            for e in mexe:
                e.desfazer()
                e._refazer.clear()
            QMessageBox.warning(self, "Estruturas", f"Não deu certo:\n{ex}")
            return {}
        finally:
            QApplication.restoreOverrideCursor()
        self._gravado = False
        self._encher(self.atual())
        self._redesenhar()
        return out
