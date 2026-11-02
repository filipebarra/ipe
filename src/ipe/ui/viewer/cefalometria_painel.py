"""Janela da cefalometria do cavum (0.99.15): a conferência do que a IA mediu, e o roteiro à mão.

Uma linha por medida, na ordem do laudo dele: o número, a referência e **de quem é** o número
(automático ou editado). Para trocar um valor: digitar na célula, ou **Medir à mão**, que liga a
ferramenta certa (régua; contorno para a área) e usa a próxima medida feita em qualquer quadro da
aba. Sem a IA (ou sem TC), a mesma janela começa vazia e serve de roteiro manual.

A imagem de conferência (sagital com as linhas) e as estruturas ficam no exame; esta janela é a
que monta o texto e manda para o laudo.
"""
from __future__ import annotations

import copy
import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
)

from dataclasses import dataclass, field
from typing import Callable

from ipe.ai import cefalometria as CF
from ipe.ui.tabelas import colunas_ajustaveis
from ipe.ui.viewer.roteiro_painel import valor_da_anotacao

log = logging.getLogger(__name__)

#: ferramenta para medir à mão: a área é um contorno; o nível do hioide é texto (digitado)
FERRAMENTA = {k: "measure" for k in CF.ORDEM}
FERRAMENTA["area"] = "polygon"
FERRAMENTA.pop("hioide_nivel")
TIPOS = {"measure": ("line",), "polygon": ("polygon",), "angle": ("angle",)}
INSTRUCAO = {
    "area": "No plano perpendicular ao eixo da via aérea (MPR oblíquo), no ponto mais estreito, contorne a luz.",
    "palato_comprimento": "No sagital mediano, da espinha nasal posterior à ponta da úvula.",
    "palato_espessura": "No sagital mediano, a maior espessura do palato mole, perpendicular ao comprimento.",
    "pas_retropalatal": "No sagital mediano, a menor distância entre o palato mole e a parede posterior da faringe.",
    "pas_retrolingual": "No sagital mediano, a menor distância entre a base da língua e a parede posterior.",
    "hioide_mp": "No sagital, da linha gônio–mento (plano mandibular) à borda superior do hioide, perpendicular.",
    "lingua_transversal": "No axial ou coronal, a maior largura laterolateral da língua.",
    "lingua_ap": "No sagital mediano, da ponta à base da língua.",
    "hioide_nivel": "Linha horizontal pelo corpo do hioide: em que nível da coluna cai (ex.: platô inferior de C3).",
}


def vazio() -> CF.Cefalometria:
    res = CF.Cefalometria()
    for k in CF.ORDEM:
        res.medidas[k] = CF.Medida(k, CF.NOMES[k], unidade="mm²" if k == "area" else ("" if k == "hioide_nivel"
                                                                                     else "mm"),
                                   casas=0 if k == "area" else 1, origem="")
    return res


def _numero(txt: str) -> float | None:
    t = (txt or "").strip().replace(",", ".")
    for suf in ("mm²", "mm2", "mm", "mL", "ml", "°", "%"):
        if t.endswith(suf):
            t = t[: -len(suf)].strip()
    try:
        return float(t)
    except ValueError:
        return None


@dataclass
class Definicao:
    """O que muda de uma IA de medidas para outra (cefalometria, índices do crânio…): a janela é a mesma."""
    modulo: object                       # o módulo das medidas (ORDEM, NOMES, NUMERO, REFERENCIAS…)
    titulo: str
    ferramenta: dict
    instrucao: dict
    vazio: Callable
    texto: Callable                      # (res, settings, automatica) -> str
    explicacao_auto: str
    textuais: set = field(default_factory=set)        # medidas que são texto, não número
    recalcular: Callable | None = None                # medidas que saem de outras (Evans = cornos ÷ crânio)
    dica: Callable | None = None                      # (medida) -> texto extra na dica da linha


DEF_CEFALOMETRIA = Definicao(
    CF, "Cefalometria", FERRAMENTA, INSTRUCAO, vazio,
    lambda res, s, auto: CF.texto_do_laudo(res, s, automatica=auto),
    "Medidas feitas pela IA (TotalSegmentator + geometria). <b>Confira cada uma</b> na imagem "
    "“Cefalometria: conferência” do exame; troque digitando ou com <i>Medir à mão</i>.",
    textuais={"hioide_nivel"},
    dica=lambda m: f"{m.texto} — {CF.classe_da_area(m.valor)}" if m.id == "area" and m.texto and m.valor is not None
    else "",
)


def def_neuro() -> Definicao:
    from ipe.ai import neuro as N
    return Definicao(
        N, N.TITULO, N.FERRAMENTA, N.INSTRUCAO, N.vazio,
        lambda res, s, auto: N.texto_do_laudo(res, s, automatica=auto),
        "Medidas feitas pela IA (SynthSeg + geometria), nos planos da aquisição. <b>Confira cada uma</b> na "
        "imagem “Índices do crânio: conferência” do exame ou com <i>Ver no quadro</i>; troque digitando ou "
        "com <i>Medir à mão</i>.",
        recalcular=N.recalcular,
        dica=lambda m: m.texto if m.id == "v3" and m.texto else "",
    )


class CefalometriaPainel(QDialog):
    """A janela de conferência das medidas de uma IA (a cefalometria foi a primeira; `D` diz qual)."""

    def __init__(self, tab, res: CF.Cefalometria | None = None, parent=None, automatica: bool = False,
                 D: Definicao | None = None):
        super().__init__(parent or tab)
        self.D = D or DEF_CEFALOMETRIA
        self.tab = tab
        self.settings = getattr(tab, "settings", None)
        self.setWindowFlag(Qt.Window, True)
        self.setModal(False)
        self.resize(760, 640)
        self.esperando: str | None = None
        self._usadas: set[int] = set()
        self._ligados: list = []

        self.titulo = QLabel()
        self.titulo.setWordWrap(True)
        self.tabela = QTableWidget(0, 5)
        self.tabela.setHorizontalHeaderLabels(["Nº", "Medida", "Valor", "Referência", "De quem"])
        for c, larg in enumerate((36, 300, 110, 200, 100)):
            self.tabela.setColumnWidth(c, larg)
        colunas_ajustaveis(self.tabela)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.itemChanged.connect(self._editou)
        self.tabela.currentCellChanged.connect(lambda *_a: self._mostrar_instrucao())
        self.instrucao = QLabel()
        self.instrucao.setWordWrap(True)
        self.instrucao.setStyleSheet("background:#26303a;color:#e8e8e8;padding:8px;border-radius:4px")
        self.b_medir = QPushButton("Medir à mão")
        self.b_medir.setToolTip("Liga a ferramenta: a próxima medida feita num quadro substitui este valor")
        self.b_medir.clicked.connect(self.medir_linha_atual)
        self.b_auto = QPushButton("Voltar ao automático")
        self.b_auto.clicked.connect(self._voltar_ao_automatico)
        self.b_refs = QPushButton("Referências…")
        self.b_refs.clicked.connect(self.editar_referencias)
        linha = QHBoxLayout()
        self.b_ver = QPushButton("Ver no quadro")
        self.b_ver.setToolTip("Leva o quadro ativo ao plano da medida (reformata no sagital, axial ou coronal) e ao "
                              "corte onde a linha está. As linhas aparecem em qualquer plano que as contenha.")
        self.b_ver.clicked.connect(self.ver_no_quadro)
        self.tabela.cellDoubleClicked.connect(lambda r, c: self.ver_no_quadro() if c != 2 else None)
        for b in (self.b_ver, self.b_medir, self.b_auto, self.b_refs):
            linha.addWidget(b)
        linha.addStretch(1)
        # estado do resultado (0.99.22, plano AW): automático, editado*, aceito por quem e quando
        self.l_estado = QLabel()
        self.l_estado.setWordWrap(True)
        self.b_aceitar = QPushButton("Aceitar o resultado")
        self.b_aceitar.setToolTip("Registra que você conferiu: quem e quando ficam guardados com o exame, "
                                  "neste computador, junto com o que foi editado.")
        self.b_aceitar.clicked.connect(self.aceitar)
        linha_estado = QHBoxLayout()
        linha_estado.addWidget(self.l_estado, 1)
        linha_estado.addWidget(self.b_aceitar)
        self.texto_laudo = QTextEdit()
        self.texto_laudo.setReadOnly(True)
        self.texto_laudo.setMinimumHeight(170)
        self.b_copiar = QPushButton("Copiar o texto")
        self.b_copiar.clicked.connect(self._copiar)
        self.b_laudo = QPushButton("Mandar para o laudo")
        self.b_laudo.clicked.connect(self._mandar_ao_laudo)
        rodape = QHBoxLayout()
        rodape.addWidget(self.b_copiar)
        rodape.addWidget(self.b_laudo)
        rodape.addStretch(1)
        lay = QVBoxLayout(self)
        lay.addWidget(self.titulo)
        lay.addWidget(self.tabela, 1)
        lay.addWidget(self.instrucao)
        lay.addLayout(linha)
        lay.addLayout(linha_estado)
        lay.addWidget(QLabel("<b>Texto para o laudo</b>"))
        lay.addWidget(self.texto_laudo)
        lay.addLayout(rodape)
        self.ligar_quadros()
        self.carregar(res, automatica)

    # ------------------------------------------------------------ dados
    def carregar(self, res: CF.Cefalometria | None, automatica: bool = False) -> None:
        self.res = res if res is not None else self.D.vazio()
        self.original = copy.deepcopy(self.res)
        self.automatica = automatica and res is not None
        self.revisao = None
        if self.automatica:
            self.revisao = self._ler_revisao()
            dados = (self.revisao or {}).get("dados") or ""
            if dados:
                try:
                    self.res = self.D.modulo.de_json(dados)      # o que ficou da conferência anterior
                except Exception:  # noqa: BLE001
                    log.exception("revisão da IA ilegível")
        self.setWindowTitle(f"{self.D.titulo} — conferência da automática" if self.automatica
                            else f"{self.D.titulo} — à mão")
        if self.automatica:
            self.titulo.setText(self.D.explicacao_auto)
        else:
            self.titulo.setText("Faça as medidas na ordem: escolha a linha e clique em <i>Medir à mão</i>, ou digite "
                                "o valor.")
        self._usadas = {id(a) for vp in self.tab.viewports for a in getattr(vp, "annotations", [])}
        self._encher()
        self.tabela.setCurrentCell(0, 2)

    def _encher(self) -> None:
        M = self.D.modulo
        refs = M.referencias(self.settings)
        self.tabela.blockSignals(True)
        self.tabela.setRowCount(len(M.ORDEM))
        for r, k in enumerate(M.ORDEM):
            m = self.res.medidas[k]
            if m.valor is not None:
                v = m.texto_valor()
            else:
                v = m.texto if m.texto and not m.motivo else ""
            itens = [QTableWidgetItem(M.NUMERO[k]), QTableWidgetItem(m.nome), QTableWidgetItem(v),
                     QTableWidgetItem(refs.get(k, "")), QTableWidgetItem(m.origem or "falta")]
            for c, it in enumerate(itens):
                if c != 2:
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                it.setData(Qt.UserRole, k)
                self.tabela.setItem(r, c, it)
            dica = []
            extra = self.D.dica(m) if self.D.dica else ""
            if extra:
                dica.append(extra)
            if m.motivo and m.valor is None:
                dica.append(f"não medido: {m.motivo}")
                itens[4].setText("não medido")
                itens[4].setForeground(QBrush(QColor(240, 170, 90)))
            elif m.origem == "editado":
                itens[4].setText("editado *")
                itens[4].setForeground(QBrush(QColor(120, 190, 255)))
            for it in itens:
                it.setToolTip("\n".join(dica))
        self.tabela.blockSignals(False)
        self._atualizar_texto()
        self._mostrar_estado()
        if hasattr(self.tab, "mostrar_linhas_da_ia"):
            self.tab.mostrar_linhas_da_ia(self.res, self.D.modulo)

    def chave_atual(self) -> str | None:
        r = self.tabela.currentRow()
        ordem = self.D.modulo.ORDEM
        return ordem[r] if 0 <= r < len(ordem) else None

    def _mostrar_instrucao(self) -> None:
        k = self.chave_atual()
        if k is None:
            return
        m = self.res.medidas[k]
        extra = f"<br>⚠ não medido pela IA: {m.motivo}" if m.motivo and m.valor is None else ""
        self.instrucao.setText(f"<b>{m.nome}</b><br>{self.D.instrucao.get(k, '')}{extra}")
        self.b_medir.setEnabled(k in self.D.ferramenta)
        self.b_ver.setEnabled(bool(m.linhas))
        o = self.original.medidas[k]
        self.b_auto.setEnabled(self.automatica and m.origem == "editado" and (o.valor is not None or bool(o.texto)))

    def definir(self, k: str, valor: float | None = None, texto: str | None = None) -> None:
        m = self.res.medidas[k]
        if texto is not None:
            m.texto = texto
        if valor is not None:
            m.valor = valor
            if k not in self.D.textuais:
                m.texto = ""                        # o local (área), as três larguras (3º ventrículo)…
        m.motivo = ""
        m.origem = "editado"
        m.linhas = []
        if self.D.recalcular is not None:
            self.D.recalcular(self.res)
        self._gravar_revisao("editado")
        self._encher()

    def _editou(self, it: QTableWidgetItem) -> None:
        if it.column() != 2:
            return
        k = it.data(Qt.UserRole)
        txt = it.text().strip()
        if k in self.D.textuais:
            self.definir(k, texto=txt)
            return
        v = _numero(txt)
        if v is None and txt:
            self._encher()                          # não é número: volta o que estava
            return
        if v is None:
            m = self.res.medidas[k]
            m.valor, m.origem = None, "editado"
            if self.D.recalcular is not None:
                self.D.recalcular(self.res)
            self._gravar_revisao("editado")
            self._encher()
            return
        self.definir(k, valor=v)

    # ------------------------------------------------------------ estado (0.99.22)
    def _chave_modulo(self) -> str:
        return getattr(self.D.modulo, "__name__", "ia").rsplit(".", 1)[-1]

    def _repo(self):
        return getattr(self.tab, "repo", None)

    def _ler_revisao(self) -> dict | None:
        repo, uid = self._repo(), getattr(self.tab, "study_uid", "")
        if repo is None or not uid or not hasattr(repo, "revisao_ia"):
            return None
        try:
            return repo.revisao_ia(uid, self._chave_modulo())
        except Exception:  # noqa: BLE001
            log.exception("ler a revisão da IA")
            return None

    def editado(self) -> bool:
        return any(m.origem == "editado" for m in self.res.medidas.values())

    def _gravar_revisao(self, estado: str, usuario: str = "") -> None:
        if not self.automatica:
            return
        repo, uid = self._repo(), getattr(self.tab, "study_uid", "")
        if repo is None or not uid or not hasattr(repo, "salvar_revisao_ia"):
            return
        try:
            repo.salvar_revisao_ia(uid, self._chave_modulo(), estado, self.editado(), usuario,
                                   self.D.modulo.para_json(self.res))
            self.revisao = repo.revisao_ia(uid, self._chave_modulo())
        except Exception:  # noqa: BLE001
            log.exception("gravar a revisão da IA")

    @staticmethod
    def _usuario() -> str:
        try:
            from ipe.auth import session as S
            return S.get().username or ""
        except Exception:  # noqa: BLE001
            return ""

    def aceitar(self) -> None:
        self._gravar_revisao("aceito", self._usuario() or "usuário do computador")
        self._mostrar_estado()

    def estado_texto(self) -> str:
        if not self.automatica:
            return "Medidas à mão."
        r = self.revisao or {}
        ed = self.editado()
        if r.get("estado") == "aceito":
            q = r.get("quando")
            quando = q.strftime("%d/%m/%Y %H:%M") if hasattr(q, "strftime") else str(q or "")
            return (f"Aceito por {r.get('usuario') or '?'} em {quando}" +
                    (" — com valores editados (*)" if ed else " — sem edição"))
        if ed:
            return "Editado (*) — ainda não aceito"
        return "Automático — ainda não conferido"

    def _mostrar_estado(self) -> None:
        if not hasattr(self, "l_estado"):
            return
        self.l_estado.setText(f"<b>Estado:</b> {self.estado_texto()}")
        self.b_aceitar.setVisible(self.automatica)

    def ver_no_quadro(self) -> bool:
        k = self.chave_atual()
        if k is None or not self.res.medidas[k].linhas or not hasattr(self.tab, "ver_medida_da_cefalometria"):
            self.tab.status_message.emit("Esta medida não tem linha para mostrar (medida à mão ou não medida).")
            return False
        return self.tab.ver_medida_da_cefalometria(self.res.medidas[k])

    def _voltar_ao_automatico(self) -> None:
        k = self.chave_atual()
        if k is not None:
            self.res.medidas[k] = copy.deepcopy(self.original.medidas[k])
            if self.D.recalcular is not None:
                self.D.recalcular(self.res)
            self._gravar_revisao("editado" if self.editado() else "auto")
            self._encher()
            self._mostrar_instrucao()

    # ------------------------------------------------------------ medir à mão
    def ligar_quadros(self) -> None:
        for vp in self.tab.viewports:
            if vp in self._ligados:
                continue
            vp.sig.annotations_changed.connect(self.medida_feita)
            self._ligados.append(vp)

    def medir_linha_atual(self) -> None:
        k = self.chave_atual()
        if k is None or k not in self.D.ferramenta:
            return
        self.esperando = k
        if hasattr(self.tab, "set_left_tool"):
            self.tab.set_left_tool(self.D.ferramenta[k])
        self.tab.status_message.emit(f"{self.D.titulo}: faça a medida “{self.D.modulo.NOMES[k]}”.")
        self.b_medir.setText("Esperando a medida…")

    def medida_feita(self, vp) -> None:
        k = self.esperando
        if k is None or not self.isVisible():
            return
        tipos = TIPOS.get(self.D.ferramenta.get(k, ""), ())
        novas = [a for a in getattr(vp, "annotations", []) if a.done and a.kind in tipos and id(a) not in self._usadas]
        if not novas:
            return
        ann = novas[-1]
        self._usadas.add(id(ann))
        v = valor_da_anotacao(vp, ann)
        if v is None or v <= 0:
            return
        self.esperando = None
        self.b_medir.setText("Medir à mão")
        self.definir(k, valor=v)
        ordem = self.D.modulo.ORDEM
        r = ordem.index(k)
        if not self.automatica and r + 1 < len(ordem):            # à mão: vai para a próxima
            self.tabela.setCurrentCell(r + 1, 2)
            if ordem[r + 1] in self.D.ferramenta:
                self.medir_linha_atual()

    # ------------------------------------------------------------ referências e texto
    def editar_referencias(self) -> bool:
        M = self.D.modulo
        refs = M.referencias(self.settings)
        dlg = QDialog(self)
        dlg.setWindowTitle("Referências da cefalometria" if M is CF else "Referências dos índices do crânio")
        form = QFormLayout(dlg)
        campos = {}
        for k in M.ORDEM:
            campos[k] = QLineEdit(refs.get(k, ""))
            form.addRow(M.NOMES[k], campos[k])
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        bb.button(QDialogButtonBox.RestoreDefaults).clicked.connect(
            lambda: [campos[k].setText(M.REFERENCIAS[k]) for k in M.ORDEM])
        form.addRow(bb)
        if dlg.exec() != QDialog.Accepted:
            return False
        self.salvar_referencias({k: c.text().strip() for k, c in campos.items()})
        return True

    def salvar_referencias(self, novas: dict) -> None:
        if self.settings is not None:
            M = self.D.modulo
            diferentes = {k: v for k, v in novas.items() if v != M.REFERENCIAS.get(k)}
            self.settings.set(M.CHAVE_REFERENCIAS, diferentes)
        self._encher()

    def texto(self) -> str:
        return self.D.texto(self.res, self.settings, self.automatica)

    def _atualizar_texto(self) -> None:
        self.texto_laudo.setPlainText(self.texto())

    def _copiar(self) -> None:
        QGuiApplication.clipboard().setText(self.texto())
        self.tab.status_message.emit("Texto copiado.")

    def _mandar_ao_laudo(self) -> None:
        ok = hasattr(self.tab, "append_to_report") and self.tab.append_to_report(self.texto())
        if not ok:
            self._copiar()
            self.tab.status_message.emit("Sem laudo aberto para escrever: o texto foi copiado.")
