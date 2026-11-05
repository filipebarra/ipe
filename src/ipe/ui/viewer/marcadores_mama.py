"""Achados BI-RADS por marcadores na mamografia (0.99.64, PV 20): marcar na CC e na MLO, ver a tabela com a
distância ao mamilo e a localização, e mandar ao laudo BI-RADS."""
from __future__ import annotations

import json
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from ipe.reporting import marcadores_mama as MM

log = logging.getLogger(__name__)

CHAVE = "mama_marca"
TIPOS = ["Nódulo", "Calcificações", "Assimetria", "Assimetria focal", "Distorção arquitetural",
         "Linfonodo intramamário", "Achado associado"]


def _lado_vista(vp) -> tuple[str, str, list]:
    """(lado R/L, vista, PatientOrientation) do quadro de mamografia."""
    lado = vista = ""
    cell = getattr(vp, "mg_spec", None)
    if cell is not None:
        lado, vista = cell.side, ("" if cell.view == "ANY" else cell.view)
    orient = []
    f = vp.current_frame()
    if f is not None and getattr(f, "path", ""):
        try:
            import pydicom
            ds = pydicom.dcmread(f.path, stop_before_pixels=True, force=True,
                                 specific_tags=["ImageLaterality", "Laterality", "ViewPosition", "PatientOrientation"])
            lado = lado or {"R": "R", "L": "L"}.get(str(ds.get("ImageLaterality", "") or ds.get("Laterality", "")
                                                        or "").upper()[:1], "")
            vista = vista or str(ds.get("ViewPosition", "") or "").upper()
            po = ds.get("PatientOrientation")
            orient = [str(x) for x in po] if po else []
        except Exception:  # noqa: BLE001
            log.debug("cabeçalho da mamografia", exc_info=True)
    return lado, vista, orient


def marcas_do_exame(repo, study_uid: str) -> dict[int, list[dict]]:
    """{número do achado: [marca (meta da anotação) por vista]}."""
    out: dict[int, list[dict]] = {}
    for a in repo.annotations_for_studies([study_uid]):
        try:
            d = json.loads(a.get("data") or "{}")
        except ValueError:
            continue
        meta = d.get("meta") or {}
        n = meta.get(CHAVE)
        if n is None:
            continue
        out.setdefault(int(n), []).append({**meta, "id": a.get("id"), "sop_uid": a.get("sop_uid", "")})
    return out


def marcar(tab, vp, ip, numero: int | None = None):
    """Põe a marca "A{n}" no ponto `ip` (pixels da imagem) do quadro e guarda a posição em relação ao mamilo.
    Devolve a anotação, ou None (e diz por quê na barra)."""
    from ipe.imaging import measure as M
    lado, vista, orient = _lado_vista(vp)
    if lado not in ("R", "L") or not vista:
        tab.status_message.emit("Não sei a mama ou a incidência deste quadro: abra pelo protocolo da mamografia.")
        return None
    mam = vp.mamilo_imagem()
    if mam is None:
        tab.status_message.emit("Não achei o mamilo nesta imagem: a marca precisa dele para medir a distância.")
        return None
    h, w = vp._img.pixels.shape[:2]
    pos = MM.posicao(vista, lado, (ip[0], ip[1]), mam, vp._spacing(), vp.chest_image_side(), w, orient)
    existentes = marcas_do_exame(tab.repo, vp.study_uid or tab.study_uid)
    if numero is None:
        numero = max(existentes, default=0) + 1
    else:                                          # a mesma vista do mesmo achado: troca a marca
        for m in existentes.get(numero, []):
            if m.get("plano") == pos["plano"] and m.get("id"):
                for v in tab.viewports:
                    for ann in list(v.annotations):
                        if ann.db_id == m["id"]:
                            v.delete_annotation(ann)
    f = vp.current_frame()
    ann = M.Annotation("text", vp.frame_key(), [(float(ip[0]), float(ip[1]))], text=f"A{numero}",
                       study_uid=vp.study_uid,
                       series_uid=(f.series_uid if f is not None and getattr(f, "series_uid", "") else vp.series_uid),
                       meta={CHAVE: int(numero), **pos})
    vp.annotations.append(ann)
    vp._store("save", ann)
    vp.update()
    lado_pt = "direita" if lado == "R" else "esquerda"
    tab.status_message.emit(f"A{numero} ({pos['vista']}, mama {lado_pt}): {pos['dist_mm']:.0f} mm do mamilo.")
    return ann


class MarcadoresDialog(QDialog):
    COLS = ["Achado", "Mama", "Tipo", "Vistas", "Distância do mamilo", "Localização"]

    def __init__(self, tab, study_uid: str | None = None):
        super().__init__(tab, Qt.Tool)
        self.tab = tab
        self.study_uid = study_uid or tab.study_uid
        self.setWindowTitle("Achados marcados (BI-RADS)")
        self.resize(760, 320)
        self.t = QTableWidget(0, len(self.COLS))
        self.t.setHorizontalHeaderLabels(self.COLS)
        self.t.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        from ipe.ui.tabelas import colunas_ajustaveis
        colunas_ajustaveis(self.t)
        self.nota = QLabel("Botão direito na imagem ▸ Achado BI-RADS aqui: marque o mesmo achado na CC e na MLO. "
                           "Com as duas vistas sai o quadrante e a hora do relógio.")
        self.nota.setWordWrap(True)
        b_laudo = QPushButton("Mandar ao laudo BI-RADS")
        b_laudo.clicked.connect(self.mandar_ao_laudo)
        b_apagar = QPushButton("Apagar as marcas do achado")
        b_apagar.clicked.connect(self.apagar)
        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.close)
        h = QHBoxLayout()
        h.addWidget(b_laudo)
        h.addWidget(b_apagar)
        h.addStretch(1)
        h.addWidget(fechar)
        lay = QVBoxLayout(self)
        lay.addWidget(self.t, 1)
        lay.addWidget(self.nota)
        lay.addLayout(h)
        self.tipos: dict[int, QComboBox] = {}
        self.recarregar()

    def recarregar(self) -> None:
        self.marcas = marcas_do_exame(self.tab.repo, self.study_uid)
        self.locs = {n: MM.localizar(ms) for n, ms in sorted(self.marcas.items())}
        self.t.setRowCount(len(self.locs))
        self.tipos = {}
        for r, (n, loc) in enumerate(self.locs.items()):
            lado = {"R": "Direita", "L": "Esquerda"}.get(loc["lado"], "")
            dist = "" if loc["dist_mm"] is None else f"{loc['dist_mm']:.0f} mm"
            local = loc["local"] + (" (falta a outra vista)" if loc["so_uma_vista"] else "")
            for c, txt in enumerate([f"A{n}", lado, "", loc["vistas"], dist, local]):
                self.t.setItem(r, c, QTableWidgetItem(txt))
            cb = QComboBox()
            cb.addItems(TIPOS)
            self.t.setCellWidget(r, 2, cb)
            self.tipos[n] = cb
        self.t.resizeColumnsToContents()

    def achados(self) -> list[dict]:
        return [MM.achado_birads(n, loc, self.tipos[n].currentText() if n in self.tipos else "Nódulo")
                for n, loc in self.locs.items()]

    def mandar_ao_laudo(self) -> int:
        """Põe os achados no painel BI-RADS do laudo do exame (troca os que vieram das mesmas marcas)."""
        fs = self.achados()
        if not fs:
            return 0
        self.tab.open_report(self.study_uid)
        w = getattr(self.tab, "_report_windows", {}).get(self.study_uid)
        if w is None or not hasattr(w, "birads"):
            return 0
        p = w.birads
        if not (p.kind.currentData() or ""):
            p.kind.setCurrentIndex(max(0, p.kind.findData("mg")))
        novos = {f["marcador"] for f in fs}
        p.findings = [f for f in p.findings if f.get("marcador") not in novos] + fs
        p._render_list()
        p._emit()
        self.tab.status_message.emit(f"Achados no laudo BI-RADS: {len(fs)}. Complete descrição, tamanho e "
                                     "categoria de cada um.")
        return len(fs)

    def apagar(self) -> None:
        r = self.t.currentRow()
        if not (0 <= r < len(self.locs)):
            return
        n = list(self.locs)[r]
        ids = {m.get("id") for m in self.marcas.get(n, [])}
        for v in self.tab.viewports:
            for ann in list(v.annotations):
                if ann.db_id in ids:
                    v.delete_annotation(ann)
        for i in ids:
            try:
                self.tab.repo.delete_annotation(i)
            except Exception:  # noqa: BLE001
                pass
        self.recarregar()
