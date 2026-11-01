"""Janela do roteiro de medida guiada (0.99.14) — o lado de tela de `imaging/roteiros.py`.

Fica por cima do visualizador sem travá-lo (como o painel de medidas). Mostra os passos, o que
falta e a instrução do passo atual; ao clicar em **Medir**, liga a ferramenta certa no botão
esquerdo e espera: a próxima medida desse tipo que ele fizer em qualquer quadro da aba vira o valor
do passo, e o roteiro anda sozinho. A medida continua sendo uma medida comum, visível no quadro e no
painel de medidas.

O plano e a espessura do corte são conferidos e viram **observação**, não recusa: o coronal
oblíquo, por exemplo, é o certo para o pedúnculo cerebelar superior.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QTextEdit,
    QVBoxLayout,
)

from ipe.imaging import measure as M
from ipe.imaging import roteiros as R


def valor_da_anotacao(vp, ann) -> float | None:
    """mm, mm² ou graus de uma medida, na escala que o quadro usa (calibração, US, arquivo)."""
    sp = vp.measure_spacing(ann)
    pts = list(ann.points or [])
    if ann.kind == "line" and len(pts) >= 2:
        return M.length_mm(pts[0], pts[1], sp)
    if ann.kind in ("polygon", "ellipse", "rect") and len(pts) >= 2:
        rs, cs = sp or (1.0, 1.0)
        return M.roi_area_px(ann.kind, pts) * rs * cs
    if ann.kind == "angle" and len(pts) >= 3:
        return M.angle_deg(pts[0], pts[1], pts[2], sp)
    return None


def espessura_do_quadro(vp) -> float | None:
    img = getattr(vp, "_img", None)
    hdr = getattr(img, "header", {}) or {}
    try:
        return float(hdr.get("SliceThickness")) if hdr.get("SliceThickness") else None
    except (TypeError, ValueError):
        return None


def distancia_entre_cortes(vp) -> float | None:
    """mm entre o corte atual e o vizinho (posições do arquivo ou da reconstrução), ou None."""
    import numpy as np
    fr = getattr(vp, "frames", None) or []
    i = getattr(vp, "index", 0)
    if len(fr) < 2 or fr[0].position is None or fr[0].normal is None:
        return None
    j = i + 1 if i + 1 < len(fr) else i - 1
    if fr[j].position is None or fr[i].position is None:
        return None
    d = abs(float((np.asarray(fr[j].position) - np.asarray(fr[i].position)) @ np.asarray(fr[0].normal)))
    return d if d > 0 else None


class RoteiroPainel(QDialog):
    def __init__(self, tab, roteiro_id: str = "mrpi", parent=None):
        super().__init__(parent or tab)
        self.tab = tab
        self.setWindowFlag(Qt.Window, True)
        self.setModal(False)
        self.resize(520, 600)
        self.esperando: R.Passo | None = None
        self._usadas: set[int] = set()               # id() das anotações já usadas

        self.c_roteiro = QComboBox()
        for rid, r in R.ROTEIROS.items():
            self.c_roteiro.addItem(r.nome, rid)
        self.c_roteiro.currentIndexChanged.connect(lambda _i: self.comecar(self.c_roteiro.currentData()))
        self.descricao = QLabel()
        self.descricao.setWordWrap(True)
        self.descricao.setStyleSheet("color:#9a9a9a")
        self.lista = QListWidget()
        self.lista.currentRowChanged.connect(self._escolheu_passo)
        self.instrucao = QLabel()
        self.instrucao.setWordWrap(True)
        self.instrucao.setStyleSheet("background:#26303a;color:#e8e8e8;padding:8px;border-radius:4px")
        self.b_medir = QPushButton("Medir este passo")
        self.b_medir.clicked.connect(self.medir_passo_atual)
        self.b_apagar = QPushButton("Refazer")
        self.b_apagar.setToolTip("Apaga o valor deste passo (a medida continua no quadro)")
        self.b_apagar.clicked.connect(self._refazer)
        self.b_pular = QPushButton("Próximo passo")
        self.b_pular.setToolTip("Passa ao próximo passo (ex.: medido só um lado do pedúnculo)")
        self.b_pular.clicked.connect(self._pular)
        botoes = QHBoxLayout()
        for b in (self.b_medir, self.b_apagar, self.b_pular):
            botoes.addWidget(b)
        botoes.addStretch(1)
        self.resultado = QTextEdit()
        self.resultado.setReadOnly(True)
        self.resultado.setMinimumHeight(150)
        self.b_copiar = QPushButton("Copiar o texto")
        self.b_copiar.clicked.connect(self._copiar)
        self.b_laudo = QPushButton("Mandar para o laudo")
        self.b_laudo.clicked.connect(self._mandar_ao_laudo)
        self.b_recomecar = QPushButton("Recomeçar")
        self.b_recomecar.clicked.connect(lambda: self.comecar(self.andamento.roteiro.id))
        rodape = QHBoxLayout()
        for b in (self.b_copiar, self.b_laudo, self.b_recomecar):
            rodape.addWidget(b)
        rodape.addStretch(1)

        lay = QVBoxLayout(self)
        lay.addWidget(self.c_roteiro)
        lay.addWidget(self.descricao)
        lay.addWidget(self.lista, 1)
        lay.addWidget(self.instrucao)
        lay.addLayout(botoes)
        lay.addWidget(QLabel("<b>Resultado</b>"))
        lay.addWidget(self.resultado)
        lay.addLayout(rodape)

        self._ligados = []
        self.ligar_quadros()
        self.comecar(roteiro_id)

    # ------------------------------------------------------------ roteiro
    def comecar(self, roteiro_id: str) -> None:
        r = R.ROTEIROS.get(roteiro_id) or R.MRPI
        self.andamento = R.Andamento(r)
        self._usadas = {id(a) for vp in self.tab.viewports for a in getattr(vp, "annotations", [])}
        i = self.c_roteiro.findData(r.id)
        if i != self.c_roteiro.currentIndex():
            self.c_roteiro.blockSignals(True)
            self.c_roteiro.setCurrentIndex(i)
            self.c_roteiro.blockSignals(False)
        self.setWindowTitle(f"Roteiro — {r.nome}")
        self.descricao.setText(r.descricao + (f"<br><small>Fonte: {r.fonte}</small>" if r.fonte else ""))
        self.esperando = None
        self._preencher_da_ia()
        self._encher()
        prox = self.andamento.proximo()
        if prox is not None:
            self.lista.setCurrentRow(list(r.passos).index(prox))

    def _preencher_da_ia(self) -> None:
        """0.99.17: com os índices do crânio (SynthSeg) já no exame, os passos que a IA mede (3º
        ventrículo, cornos frontais, diâmetro do crânio, ângulo calosal) vêm preenchidos, com a marca."""
        obter = getattr(self.tab, "neuro_do_exame", None)
        try:
            res = obter() if callable(obter) else None
        except Exception:  # noqa: BLE001
            res = None
        if res is None:
            return
        from ipe.ai import neuro as N
        valores = N.valores_para_roteiro(res)
        for p in self.andamento.roteiro.passos:
            for v in valores.get(p.id, []):
                self.andamento.registrar(p, v, ["medido automaticamente (SynthSeg)"])

    def _encher(self) -> None:
        a = self.andamento
        atual = self.lista.currentRow()
        self.lista.blockSignals(True)
        self.lista.clear()
        for p in a.roteiro.passos:
            feitas = a.feitas(p)
            vals = a.valores.get(p.id, [])
            unid = R.UNIDADE.get(p.ferramenta, "")
            if vals and p.acumula:
                txt = f"{R.soma(vals):.0f} mm³ ({len(vals)} {'corte' if len(vals) == 1 else 'cortes'})"
                marca = "✓"
            elif vals:
                m = R.media(vals)
                txt = f"{m:.1f}".replace(".", ",") + f" {unid}"
                if len(vals) > 1:
                    txt += f" (média de {len(vals)})"
                marca = "✓" if a.completo(p) else f"{feitas}/{p.vezes}"
            else:
                txt, marca = ("opcional" if p.opcional else "falta"), "○"
            aviso = " ⚠" if a.avisos.get(p.id) else ""
            it = QListWidgetItem(f"{marca}  {p.nome} — {txt}{aviso}")
            it.setData(Qt.UserRole, p.id)
            if a.avisos.get(p.id):
                it.setToolTip("\n".join(a.avisos[p.id]))
                it.setForeground(QBrush(QColor(240, 190, 90)))
            elif a.completo(p):
                it.setForeground(QBrush(QColor(120, 210, 130)))
            self.lista.addItem(it)
        self.lista.blockSignals(False)
        if 0 <= atual < self.lista.count():
            self.lista.setCurrentRow(atual)
        self._mostrar_resultado()

    def passo_atual(self) -> R.Passo | None:
        row = self.lista.currentRow()
        passos = self.andamento.roteiro.passos
        return passos[row] if 0 <= row < len(passos) else None

    def _escolheu_passo(self, _row: int) -> None:
        p = self.passo_atual()
        if p is None:
            self.instrucao.setText("")
            return
        ferramenta = R.NOME_DA_FERRAMENTA.get(p.ferramenta, p.ferramenta)
        plano = f" · plano <b>{p.plano.lower()}</b>" if p.plano else ""
        vezes = f" · {p.vezes} medidas (média)" if p.vezes > 1 else (
            f" · até {p.limite} medidas (média)" if p.limite > 1 else "")
        avisos = "".join(f"<br>⚠ {a}" for a in self.andamento.avisos.get(p.id, []))
        self.instrucao.setText(f"<b>{p.nome}</b> — {ferramenta}{plano}{vezes}<br>{p.instrucao}{avisos}")
        if self.esperando is not None and self.esperando is not p:
            self.medir_passo_atual()

    def medir_passo_atual(self) -> None:
        """Liga a ferramenta do passo e espera a próxima medida desse tipo."""
        p = self.passo_atual()
        if p is None:
            return
        self.esperando = p
        if hasattr(self.tab, "set_left_tool"):
            self.tab.set_left_tool(p.ferramenta)
        plano = f" no plano {p.plano.lower()}" if p.plano else ""
        self.tab.status_message.emit(f"Roteiro: faça a medida “{p.nome}”{plano}.")
        self.b_medir.setText("Esperando a medida…")

    def _refazer(self) -> None:
        p = self.passo_atual()
        if p is not None:
            self.andamento.apagar(p)
            self._encher()
            self.medir_passo_atual()

    def _pular(self) -> None:
        row = self.lista.currentRow()
        if row + 1 < self.lista.count():
            self.lista.setCurrentRow(row + 1)

    # ------------------------------------------------------------ captura das medidas
    def ligar_quadros(self) -> None:
        for vp in self.tab.viewports:
            if vp in self._ligados:
                continue
            vp.sig.annotations_changed.connect(self.medida_feita)
            self._ligados.append(vp)

    def medida_feita(self, vp) -> None:
        p = self.esperando
        if p is None or not self.isVisible():
            return
        tipos = R.FERRAMENTA_PARA_TIPO.get(p.ferramenta, ())
        novas = [a for a in getattr(vp, "annotations", []) if a.done and a.kind in tipos
                 and id(a) not in self._usadas]
        if not novas:
            return
        ann = novas[-1]
        self._usadas.add(id(ann))
        valor = valor_da_anotacao(vp, ann)
        if valor is None or valor <= 0:
            return
        extra, chave = [], None
        if p.acumula:                          # planimetria: área × distância entre os cortes (0.99.19)
            passo_mm = distancia_entre_cortes(vp)
            if passo_mm is None:
                passo_mm = espessura_do_quadro(vp) or 1.0
                extra.append("distância entre os cortes desconhecida: usada a espessura")
            elif passo_mm > 3.0:
                extra.append(f"cortes a cada {passo_mm:.1f} mm: volume pouco preciso para uma estrutura tão "
                             "pequena")
            valor = valor * passo_mm
            chave = (getattr(vp, "series_uid", ""), getattr(vp, "index", 0),
                     vp.plano_nome() if hasattr(vp, "plano_nome") else "")
        self.registrar(p, valor, vp.plano_nome() if hasattr(vp, "plano_nome") else "",
                       espessura_do_quadro(vp), sem_escala=vp.measure_spacing(ann) is None, extra=extra,
                       chave=chave)

    def registrar(self, p: R.Passo, valor: float, plano: str = "", espessura: float | None = None,
                  sem_escala: bool = False, extra: list | None = None, chave=None) -> None:
        avisos = R.avisos_da_medida(p, plano, espessura)
        if sem_escala:
            avisos.append("imagem sem escala: valor em pixels")
        avisos += list(extra or [])
        self.andamento.registrar(p, valor, avisos, chave=chave)
        if self.andamento.feitas(p) >= p.limite:
            prox = self.andamento.proximo()
            self.esperando = None
            self.b_medir.setText("Medir este passo")
            self._encher()
            if prox is not None:
                self.lista.setCurrentRow(list(self.andamento.roteiro.passos).index(prox))
                self.medir_passo_atual()
            else:
                self.tab.status_message.emit("Roteiro completo.")
        else:
            self._encher()                     # o mesmo passo pede outra medida (média)
            self._escolheu_passo(self.lista.currentRow())

    # ------------------------------------------------------------ resultado
    def _mostrar_resultado(self) -> None:
        a = self.andamento
        linhas = ["<table cellpadding='3'>"]
        for res in a.resultados():
            ref = f"<br><small style='color:#9a9a9a'>{res.referencia}</small>" if res.referencia else ""
            negrito = res.referencia != ""
            nome = f"<b>{res.nome}</b>" if negrito else res.nome
            valor = f"<b>{res.texto_valor()}</b>" if negrito else res.texto_valor()
            linhas.append(f"<tr><td>{nome}</td><td align='right'>{valor}</td><td>{ref}</td></tr>")
        linhas.append("</table>")
        if not a.pronto():
            faltam = [p.nome for p in a.roteiro.passos if not p.opcional and not a.completo(p)]
            linhas.append(f"<p style='color:#9a9a9a'>Faltam: {', '.join(faltam)}.</p>")
        self.resultado.setHtml("".join(linhas))

    def texto(self) -> str:
        return R.texto_do_laudo(self.andamento)

    def _copiar(self) -> None:
        QGuiApplication.clipboard().setText(self.texto())
        self.tab.status_message.emit("Texto do roteiro copiado.")

    def _mandar_ao_laudo(self) -> None:
        ok = hasattr(self.tab, "append_to_report") and self.tab.append_to_report(self.texto())
        if not ok:
            self._copiar()
            self.tab.status_message.emit("Sem laudo aberto para escrever: o texto foi copiado.")
