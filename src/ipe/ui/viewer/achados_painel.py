"""Achados de IA (0.99.46): a lista revisável do que as IAs apontaram no exame.

Uma linha por achado: rótulo, tipo, local, números, estado e quem revisou. Clicar leva o quadro ativo
(ou o que mostra a série usada pela IA) até o achado, com o cursor 3D em cima. Botões:

- **Confirmar**, **Descartar**, **Voltar a sugerido**;
- **Corrigir…**: o médico troca os números (diâmetro, volume, consistência…); fica "corrigido" e
  o laudo leva os números dele;
- **Acompanhar como lesão**: o achado confirmado vira uma lesão do acompanhamento, com uma medida
  (círculo do diâmetro, e o volume) no corte do achado — e daí entra no seguimento e no tempo de
  duplicação;
- **Mandar ao laudo**: só os confirmados e corrigidos.

Não é modal. Uma por aba.
"""
from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from ipe.ai import achados as AC
from ipe.ai import ferramentas as FE
from ipe.core.i18n import tr

log = logging.getLogger(__name__)

COLUNAS = ["Achado", "Local", "Medidas", "Estado", "Revisão"]


def _usuario() -> str:
    from ipe.auth import session as S
    try:
        s = S.get()
        return s.full_name or s.username
    except Exception:  # noqa: BLE001
        return ""


def _modulo(ferramenta: str):
    try:
        return FE.modulo(ferramenta)
    except Exception:  # noqa: BLE001
        return None


class CorrigirDialog(QDialog):
    """Os números do achado, editáveis. Volta {chave: valor} só do que mudou."""

    def __init__(self, achado: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Corrigir {achado.get('rotulo', '')}")
        self.achado = achado
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.campos = {}
        nums = AC.numeros_validos(achado)
        for k, d in (achado.get("numeros") or {}).items():
            if isinstance(d.get("v"), (list, tuple)):
                continue
            e = QLineEdit("" if nums[k].get("v") is None else str(nums[k]["v"]).replace(".", ","))
            form.addRow(f"{tr(d.get('n', k))} ({d.get('u', '')}):" if d.get("u") else f"{tr(d.get('n', k))}:", e)
            self.campos[k] = e
        self.nota = QLineEdit(achado.get("nota", ""))
        form.addRow("Observação:", self.nota)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def valores(self) -> dict:
        out = dict(self.achado.get("corrigidos") or {})
        for k, e in self.campos.items():
            orig = (self.achado.get("numeros") or {}).get(k, {}).get("v")
            txt = e.text().strip()
            if isinstance(orig, (int, float)) and not isinstance(orig, bool):
                try:
                    v = float(txt.replace(",", "."))
                except ValueError:
                    continue
                if orig is None or abs(v - float(orig)) > 1e-9:
                    out[k] = v
                else:
                    out.pop(k, None)
            elif txt != (orig or ""):
                out[k] = txt
            else:
                out.pop(k, None)
        return out


class AchadosPainel(QDialog):
    def __init__(self, tab, parent=None):
        super().__init__(parent or tab, Qt.Window)
        self.tab = tab
        self.repo = tab.repo
        self.setWindowTitle("Achados de IA")
        self.resize(820, 460)
        self.achados: list[dict] = []
        lay = QVBoxLayout(self)
        topo = QHBoxLayout()
        topo.addWidget(QLabel("Mostrar:"))
        self.c_filtro = QComboBox()
        self.c_filtro.addItem("Todos", "")
        for e, nome in AC.ESTADOS.items():
            self.c_filtro.addItem(nome, e)
        self.c_filtro.currentIndexChanged.connect(self.recarregar)
        topo.addWidget(self.c_filtro)
        topo.addStretch(1)
        self.l_conta = QLabel("")
        topo.addWidget(self.l_conta)
        lay.addLayout(topo)
        self.t = QTableWidget(0, len(COLUNAS))
        self.t.setHorizontalHeaderLabels(COLUNAS)
        self.t.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.t.setSelectionMode(QAbstractItemView.SingleSelection)
        self.t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.t.itemSelectionChanged.connect(self._escolheu)
        self.t.cellDoubleClicked.connect(self._duplo_clique)
        from ipe.ui.tabelas import colunas_ajustaveis
        colunas_ajustaveis(self.t)
        lay.addWidget(self.t, 1)
        self.l_origem = QLabel("")
        self.l_origem.setWordWrap(True)
        self.l_origem.setStyleSheet("color:#8b949e")
        lay.addWidget(self.l_origem)
        bt = QHBoxLayout()
        self.b_ir = QPushButton("Ir até")
        self.b_ir.clicked.connect(self.ir_ate)
        self.b_conf = QPushButton("Confirmar")
        self.b_conf.clicked.connect(self.confirmar)
        self.b_corr = QPushButton("Corrigir…")
        self.b_corr.clicked.connect(self.corrigir)
        self.b_desc = QPushButton("Descartar")
        self.b_desc.clicked.connect(self.descartar)
        self.b_volta = QPushButton("Voltar a sugerido")
        self.b_volta.clicked.connect(self.voltar_a_sugerido)
        self.b_les = QPushButton("Acompanhar como lesão")
        self.b_les.setToolTip("O achado confirmado vira uma lesão do acompanhamento, com a medida no corte dele")
        self.b_les.clicked.connect(self.acompanhar)
        self.b_laudo = QPushButton("Mandar ao laudo")
        self.b_laudo.setToolTip("Só os confirmados e os corrigidos: nada vai sozinho ao laudo")
        self.b_laudo.clicked.connect(self.mandar_ao_laudo)
        for b in (self.b_ir, self.b_conf, self.b_corr, self.b_desc, self.b_volta, self.b_les):
            bt.addWidget(b)
        bt.addStretch(1)
        bt.addWidget(self.b_laudo)
        lay.addLayout(bt)
        self.recarregar()

    # ------------------------------------------------------------ dados
    def exames(self) -> list[str]:
        return list(getattr(self.tab, "study_order", None) or [self.tab.study_uid])

    def recarregar(self) -> None:
        todos = []
        for uid in self.exames():
            try:
                todos += self.repo.achados(uid)
            except Exception:  # noqa: BLE001
                log.exception("ler os achados de IA")
        self.todos = todos
        filtro = self.c_filtro.currentData()
        self.achados = [a for a in todos if not filtro or a["estado"] == filtro]
        sel = self.atual()
        self.t.setRowCount(len(self.achados))
        for r, a in enumerate(self.achados):
            mod = _modulo(a["ferramenta"])
            chaves = getattr(mod, "CHAVES", None)
            nums = AC.numeros_validos(a)
            medidas = " · ".join(AC._fmt(nums[k]) for k in [k for k in (chaves or list(nums)) if k in nums][:3])
            cels = [f"{a['rotulo']} {tr(a['tipo'])}".strip(), tr(a.get("local", "")), medidas,
                    tr(AC.ESTADOS.get(a["estado"], a["estado"])), tr(AC.quem_e_quando(a))]
            for c, txt in enumerate(cels):
                it = QTableWidgetItem(txt)
                if c == 3:
                    it.setForeground(QBrush(QColor(AC.CORES.get(a["estado"], "#ccc"))))
                if c == 2:
                    it.setToolTip(tr(AC.texto_dos_numeros(a)))
                self.t.setItem(r, c, it)
        self.t.resizeColumnsToContents()
        n = AC.contagem(todos)
        self.l_conta.setText(tr(f"{len(todos)} achado(s): {n['sugerido']} sugerido(s), {n['confirmado']} "
                                f"confirmado(s), {n['corrigido']} corrigido(s), {n['descartado']} descartado(s)"))
        if sel is not None:
            for r, a in enumerate(self.achados):
                if a["id"] == sel["id"]:
                    self.t.selectRow(r)
        self._escolheu()

    def atual(self) -> dict | None:
        r = self.t.currentRow() if hasattr(self, "t") else -1
        return self.achados[r] if 0 <= r < len(getattr(self, "achados", [])) else None

    def escolher(self, achado_id: int) -> bool:
        for r, a in enumerate(self.achados):
            if a["id"] == achado_id:
                self.t.selectRow(r)
                return True
        return False

    def _escolheu(self) -> None:
        a = self.atual()
        tem = a is not None
        for b in (self.b_ir, self.b_conf, self.b_corr, self.b_desc, self.b_volta):
            b.setEnabled(tem)
        self.b_les.setEnabled(tem and a["estado"] in AC.VALEM and not a.get("lesao_id"))
        self.b_laudo.setEnabled(any(x["estado"] in AC.VALEM for x in getattr(self, "todos", [])))
        if a is None:
            self.l_origem.setText("")
            return
        txt = f"{a.get('modelo', '')} {a.get('versao', '')}".strip()
        self.l_origem.setText(tr(f"{txt} — {a.get('elegibilidade', '')}" if txt else a.get("elegibilidade", "")))

    # ------------------------------------------------------------ ações
    def _quadro(self, a: dict):
        vps = [v for v in self.tab._shown() if v.frames]
        da_serie = [v for v in vps if v.series_uid == a.get("series_uid")]
        if da_serie:
            return da_serie[0]
        ativo = getattr(self.tab, "active", None)
        if ativo is not None and ativo.frames:
            return ativo
        return vps[0] if vps else None

    def ir_ate(self) -> bool:
        a = self.atual()
        if a is None or not a.get("posicao"):
            return False
        p = np.asarray(a["posicao"], float)
        vp = self._quadro(a)
        if vp is None:
            return False
        ok = vp.go_to_point(p)
        vp.cursor_point = p
        vp.update()
        try:
            self.tab._on_cursor_moved(vp, p)
        except Exception:  # noqa: BLE001
            pass
        if not ok:
            self.tab.status_message.emit(tr("O quadro ativo não passa por este achado: abra a série que a IA usou."))
        return ok

    def _duplo_clique(self, *_a) -> None:
        self.ir_ate()

    def confirmar(self) -> dict | None:
        return self.marcar("confirmado")

    def descartar(self) -> dict | None:
        return self.marcar("descartado")

    def voltar_a_sugerido(self) -> dict | None:
        return self.marcar("sugerido")

    def marcar(self, estado: str) -> dict | None:
        a = self.atual()
        if a is None:
            return None
        novo = self.repo.revisar_achado(a["id"], estado, _usuario())
        self.recarregar()
        return novo

    def corrigir(self) -> dict | None:
        a = self.atual()
        if a is None:
            return None
        d = CorrigirDialog(a, self)
        if d.exec() != QDialog.Accepted:
            return None
        return self.aplicar_correcao(a, d.valores(), d.nota.text())

    def aplicar_correcao(self, a: dict, valores: dict, nota: str = "") -> dict | None:
        novo = self.repo.revisar_achado(a["id"], "corrigido" if valores else "confirmado", _usuario(),
                                        corrigidos=valores, nota=nota)
        self.recarregar()
        return novo

    def acompanhar(self) -> int | None:
        """O achado confirmado vira lesão do acompanhamento, com um círculo do diâmetro no corte dele."""
        a = self.atual()
        if a is None or a["estado"] not in AC.VALEM:
            return None
        from ipe.imaging import measure as M
        from ipe.ui.viewer.lesion_panel import patient_key
        vp = self._quadro(a)
        pid = patient_key(self.tab.study_infos.get(a["study_uid"]) or self.tab.study_info)
        if vp is None or not pid or not a.get("posicao"):
            QMessageBox.information(self, "Achados de IA", "Sem quadro com a série do achado ou sem identificação "
                                                           "do paciente.")
            return None
        p = np.asarray(a["posicao"], float)
        if not vp.go_to_point(p, tolerance_mm=5.0):
            QMessageBox.information(self, "Achados de IA", "O quadro não passa por este achado: abra a série que "
                                                           "a IA usou e tente de novo.")
            return None
        uvd = vp.patient_to_pixel(p)
        nums = AC.numeros_validos(a)
        diam = nums.get("diametro_mm", {}).get("v") or nums.get("medio_mm", {}).get("v") or 5.0
        rs, cs = vp._spacing()
        rx, ry = float(diam) / 2 / cs, float(diam) / 2 / rs
        u, v = uvd[0], uvd[1]
        nome = f"{a.get('rotulo', '')} (IA)".strip()
        lid = self.repo.save_lesion({"patient_id": pid, "name": nome, "location": a.get("local", ""),
                                     "kind": "target", "data": {"achado_ia": a["id"]}})
        f = vp.current_frame()
        ann = M.Annotation("ellipse", vp.frame_key(), [(u - rx, v - ry), (u + rx, v + ry)],
                           study_uid=vp.study_uid, series_uid=(f.series_uid if f is not None else vp.series_uid),
                           meta={"achado_ia": a["id"]})
        vp.annotations.append(ann)
        vp.link_lesion(ann, lid, nome)
        vol = nums.get("volume_mm3", {}).get("v")
        if vol is not None:
            ann.meta["ml"] = round(float(vol) / 1000.0, 4)
            vp._store("save", ann)
        self.repo.revisar_achado(a["id"], a["estado"], a.get("revisor") or _usuario(), lesao_id=lid)
        try:
            self.tab.refresh_lesions()
        except Exception:  # noqa: BLE001
            pass
        self.recarregar()
        self.tab.status_message.emit(tr(f"{nome} entrou no acompanhamento de lesões."))
        return lid

    def texto_do_laudo(self) -> str:
        partes = []
        por_ferramenta: dict[str, list] = {}
        for a in self.todos:
            por_ferramenta.setdefault(a["ferramenta"], []).append(a)
        for ferr, lista in por_ferramenta.items():
            mod = _modulo(ferr)
            txt = AC.texto_do_laudo(lista, getattr(mod, "frase", None))
            if txt:
                partes.append(txt)
        return "\n".join(partes)

    def mandar_ao_laudo(self) -> bool:
        txt = self.texto_do_laudo()
        if not txt:
            QMessageBox.information(self, "Achados de IA", "Nenhum achado confirmado ou corrigido: nada vai ao "
                                                           "laudo sem revisão.")
            return False
        ok = False
        try:
            ok = bool(self.tab.append_to_report(txt))
        except Exception:  # noqa: BLE001
            log.exception("mandar os achados ao laudo")
        if not ok:
            from PySide6.QtWidgets import QApplication
            QApplication.clipboard().setText(txt)
            self.tab.status_message.emit(tr("Sem laudo aberto: o texto foi copiado."))
        return ok


def abrir(tab, achado_id: int | None = None) -> AchadosPainel:
    p = getattr(tab, "achados_painel", None)
    try:
        vivo = p is not None and p.isVisible() is not None
    except RuntimeError:
        vivo = False
    if not vivo:
        p = AchadosPainel(tab)
        tab.achados_painel = p
    else:
        p.recarregar()
    p.show()
    p.raise_()
    if achado_id is not None:
        p.escolher(achado_id)
    return p
