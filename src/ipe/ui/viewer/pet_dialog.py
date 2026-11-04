"""PET no acompanhamento de lesões (0.99.60, item 7, parte 2): SUL, referências do fígado e do mediastino,
limiar do PERCIST, Deauville e o Q.Check do cabeçalho (no exame e contra o de base)."""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
                               QPlainTextEdit, QPushButton, QVBoxLayout)

from ipe.imaging import pet_onco as PO

log = logging.getLogger(__name__)


def series_pet(tab, study_uid: str):
    return [s for s in tab.series if s.study_uid == study_uid and (s.modality or "").upper() == "PT"]


def cabecalho_do_exame(repo, tab, study_uid: str) -> dict | None:
    """O cabeçalho do PET do exame (a primeira série PT com Bq/ml ou SUV)."""
    import pydicom
    try:
        series = [s for s in repo.series_for_study(study_uid) if (s.modality or "").upper() == "PT"]
    except Exception:  # noqa: BLE001
        series = series_pet(tab, study_uid)
    for s in series:
        inst = repo.instances_for_series(s.series_uid)
        if not inst:
            continue
        try:
            ds = pydicom.dcmread(inst[0]["path"], stop_before_pixels=True, force=True)
        except Exception:  # noqa: BLE001
            continue
        h = PO.cabecalho(ds)
        h["serie"] = s.description or ""
        return h
    return None


class PetDialog(QDialog):
    def __init__(self, tab, painel=None):
        super().__init__(tab)
        self.tab, self.painel = tab, painel
        self.study_uid = tab.study_uid
        self.pid = painel.pid if painel is not None else ""
        self.setWindowTitle("PET — referências, Deauville e Q.Check")
        self.setWindowFlag(Qt.Tool, True)
        self.resize(640, 620)
        self.fatores = QLabel()
        self.fatores.setWordWrap(True)
        self.l_figado, self.l_medi, self.l_limiar = QLabel(), QLabel(), QLabel()
        for lab in (self.l_figado, self.l_medi, self.l_limiar):
            lab.setWordWrap(True)
        b_auto = QPushButton("Fígado: automático")
        b_auto.setToolTip("Esfera de 3 cm no lobo direito, dentro da segmentação do fígado do exame "
                          "(Órgãos/TotalSegmentator na TC do PET/CT)")
        b_auto.clicked.connect(self.figado_automatico)
        b_fig = QPushButton("Fígado: clicar")
        b_fig.setToolTip("Clique no lobo direito do fígado no PET: a esfera de 3 cm procura, até 2 cm do clique, "
                         "o lugar mais homogêneo")
        b_fig.clicked.connect(lambda: self.pedir_clique("figado"))
        b_med = QPushButton("Mediastino: clicar")
        b_med.setToolTip("Clique na aorta descendente no PET: esfera de 1 cm (pool sanguíneo)")
        b_med.clicked.connect(lambda: self.pedir_clique("mediastino"))
        b_apagar = QPushButton("Apagar as referências deste exame")
        b_apagar.clicked.connect(self.apagar)
        self.fator5 = QDoubleSpinBox()
        self.fator5.setRange(1.2, 5.0)
        self.fator5.setSingleStep(0.1)
        self.fator5.setSuffix(" × o SUVmáx do fígado")
        self.fator5.setValue(float(self._dados().get("fator5") or PO.FATOR_DEAUVILLE_5))
        self.fator5.valueChanged.connect(self._fator5)
        self.qc = QPlainTextEdit()
        self.qc.setReadOnly(True)
        b_copiar = QPushButton("Copiar o Q.Check")
        b_copiar.clicked.connect(lambda: QApplication.clipboard().setText(self.qc.toPlainText()))
        fechar = QPushButton("Fechar")
        fechar.clicked.connect(self.close)
        form = QFormLayout()
        form.addRow("Fígado:", self.l_figado)
        form.addRow("Mediastino:", self.l_medi)
        form.addRow("PERCIST:", self.l_limiar)
        form.addRow("Deauville 5 acima de:", self.fator5)
        h1 = QHBoxLayout()
        for b in (b_auto, b_fig, b_med):
            h1.addWidget(b)
        h2 = QHBoxLayout()
        h2.addWidget(b_apagar)
        h2.addStretch(1)
        h2.addWidget(b_copiar)
        h2.addWidget(fechar)
        lay = QVBoxLayout(self)
        lay.addWidget(self.fatores)
        lay.addLayout(form)
        lay.addLayout(h1)
        lay.addWidget(QLabel("<b>Q.Check do cabeçalho</b>"))
        lay.addWidget(self.qc, 1)
        lay.addLayout(h2)
        self.recarregar()

    # ------------------------------------------------------------ dados
    def _track(self) -> dict:
        return self.tab.repo.lesion_track(self.pid) if self.pid else {}

    def _dados(self) -> dict:
        return dict(self._track().get("data") or {})

    def _gravar(self, dados: dict) -> None:
        if self.pid:
            self.tab.repo.save_lesion_track(self.pid, data=dados)
        if self.painel is not None:
            self.painel.refresh()

    def refs(self, study_uid: str | None = None) -> dict:
        return dict((self._dados().get("refs") or {}).get(study_uid or self.study_uid) or {})

    def guardar_ref(self, tipo: str, ref: dict, study_uid: str | None = None) -> None:
        dados = self._dados()
        refs = dict(dados.get("refs") or {})
        r = dict(refs.get(study_uid or self.study_uid) or {})
        r[tipo] = ref
        refs[study_uid or self.study_uid] = r
        dados["refs"] = refs
        self._gravar(dados)
        self.recarregar()

    def apagar(self) -> None:
        dados = self._dados()
        refs = dict(dados.get("refs") or {})
        refs.pop(self.study_uid, None)
        dados["refs"] = refs
        self._gravar(dados)
        self.recarregar()

    def _fator5(self, v: float) -> None:
        dados = self._dados()
        dados["fator5"] = float(v)
        self._gravar(dados)

    # ------------------------------------------------------------ tela
    def _texto_ref(self, r: dict | None) -> str:
        if not r:
            return "—"
        s = f"SUV {r['media']:.2f} ± {r['dp']:.2f} (máx. {r['max']:.2f}), esfera de {r['diam_mm']:.0f} mm"
        rs = PO.em_sul(r)
        if rs is not r:
            s += f" · SUL {rs['media']:.2f} ± {rs['dp']:.2f}"
        return s + (" · automático" if r.get("como") == "auto" else "")

    def recarregar(self) -> None:
        vp = self._quadro_pet()
        if vp is not None:
            fs = PO.fatores_do_arquivo(vp.frames[0].path) if vp.frames else {}
            self.fatores.setText(
                f"PET: {self._rotulo(vp)} — SUV: {fs.get('motivo_suv') or '—'}; "
                + (f"SUL = SUV × {fs['sul_razao']:.3f} (massa magra de Janmahasatian)" if fs.get("sul_razao")
                   else f"sem SUL: {fs.get('motivo_sul') or '—'}"))
        else:
            self.fatores.setText("Nenhum PET deste exame num quadro: abra a série PET para medir as referências.")
        r = self.refs()
        self.l_figado.setText(self._texto_ref(r.get("figado")))
        self.l_medi.setText(self._texto_ref(r.get("mediastino")))
        lim, como = PO.limiar_percist(PO.em_sul(r.get("figado")), PO.em_sul(r.get("mediastino")))
        self.l_limiar.setText(f"lesão mensurável a partir de {lim:.2f} ({como})" if lim is not None
                              else "meça a referência do fígado para o limiar")
        self.qc.setPlainText(self.texto_qc())

    def _rotulo(self, vp) -> str:
        row = self.tab._series_row(vp.series_uid) if vp.series_uid and ":" not in vp.series_uid else None
        return (row.description if row is not None else "") or vp.series_uid or ""

    def texto_qc(self) -> str:
        repo = self.tab.repo
        h = cabecalho_do_exame(repo, self.tab, self.study_uid)
        if h is None:
            return "Este exame não tem PET."
        linhas = [f"Este exame ({h.get('serie') or 'PET'}):", PO.texto(PO.conferir(h))]
        base = self._exame_de_comparacao()
        if base:
            hb = cabecalho_do_exame(repo, self.tab, base)
            if hb is not None:
                d = hb.get("data") or ""
                linhas += ["", f"Contra o exame de {d[6:8]}/{d[4:6]}/{d[:4]}:", PO.texto(PO.comparar(hb, h))]
                cf = PO.comparar_figado(PO.em_sul(self.refs(base).get("figado")), PO.em_sul(self.refs().get("figado")))
                if cf is not None:
                    linhas.append(PO.texto([(cf[0], "Fígado (PERCIST)", cf[1])]))
        linhas += ["", "A glicemia não vem no DICOM: confira na ficha (o PERCIST pede menos de 200 mg/dL)."]
        return "\n".join(linhas)

    def _exame_de_comparacao(self) -> str:
        """O exame de base do acompanhamento; sem ele, o PET anterior mais recente do paciente."""
        tr = self._track()
        base = tr.get("baseline_study") or ""
        if base and base != self.study_uid:
            return base
        if self.painel is not None:
            ev = [e for e in self.painel.evals if e.response == "BASE"]
            if ev and ev[0].study_uid != self.study_uid:
                return ev[0].study_uid
        info = self.tab.study_info or {}
        try:
            rows = self.tab.repo.studies_of_patient(info.get("patient_id", "")) if info.get("patient_id") else []
        except Exception:  # noqa: BLE001
            rows = []
        data = info.get("study_date", "") or ""
        antes = sorted((r for r in rows if r.study_uid != self.study_uid and (r.study_date or "") <= data
                        and "PT" in (r.modalities or "")), key=lambda r: r.study_date or "")
        return antes[-1].study_uid if antes else ""

    # ------------------------------------------------------------ medir
    def _quadro_pet(self):
        vps = [self.tab.active] + list(self.tab.viewports)
        for vp in vps:
            if vp is not None and vp.frames and (vp.modality or "").upper() == "PT" \
                    and vp.study_uid == self.study_uid and vp.mpr_plane is None:
                return vp
        return None

    def _volume(self, vp):
        uid = self.tab._source_series(vp)
        if uid is None:
            return None
        return self.tab._volume_for(vp, uid)

    def medir(self, vp, tipo: str, centro_kji, mascara=None, como: str = "clique") -> dict | None:
        vol = self._volume(vp)
        if vol is None:
            return None
        fs = PO.fatores_do_arquivo(vp.frames[0].path)
        if not fs.get("suv"):
            self.tab.status_message.emit(f"PET sem SUV: {fs.get('motivo_suv')}")
            return None
        diam = PO.DIAM_FIGADO_MM if tipo == "figado" else PO.DIAM_MEDIASTINO_MM
        busca = (40.0 if como == "auto" else PO.BUSCA_MM) if tipo == "figado" else 5.0
        r = PO.referencia(vol.data, (vol.dz, vol.dy, vol.dx), centro_kji, diam, mascara, busca, fs["suv"])
        if r is None:
            self.tab.status_message.emit("A esfera de referência não coube ali: clique mais para dentro do órgão.")
            return None
        k, j, i = r["centro"]
        r["centro_mm"] = [round(float(x), 1) for x in vol.voxel_to_patient(i, j, k)]
        r["sul_razao"] = fs.get("sul_razao")
        r["como"] = como
        self.guardar_ref(tipo, r)
        return r

    def pedir_clique(self, tipo: str) -> None:
        if self._quadro_pet() is None:
            self.tab.status_message.emit("Abra a série PET deste exame num quadro.")
            return
        self.tab._ref_pet_pendente = (self, tipo)
        self.tab.set_left_tool("grow")
        nome = "no lobo direito do fígado" if tipo == "figado" else "na aorta descendente"
        self.tab.status_message.emit(f"Clique {nome}, no PET.")

    def clicado(self, vp, u: float, v: float, tipo: str) -> dict | None:
        if (vp.modality or "").upper() != "PT":
            self.tab.status_message.emit("Clique no PET (não na TC).")
            return None
        vol = self._volume(vp)
        if vol is None:
            return None
        p = vp.pixel_to_patient(u - 0.5, v - 0.5)
        if p is None:
            return None
        i, j, k = (int(round(x)) for x in vol.patient_to_voxel(p))
        return self.medir(vp, tipo, (k, j, i))

    def mascara_do_figado(self, vol):
        for o in self.tab.overlay_objects:
            if o.study_uid and o.study_uid != self.study_uid:
                continue
            for mv in (o.volumes or []):
                if PO.e_figado(mv.label or "") or (not mv.label and PO.e_figado(o.label or "")):
                    m = PO.mascara_na_grade(mv, vol)
                    if m.any():
                        return m
        return None

    def figado_automatico(self) -> dict | None:
        vp = self._quadro_pet()
        if vp is None:
            self.tab.status_message.emit("Abra a série PET deste exame num quadro.")
            return None
        vol = self._volume(vp)
        if vol is None:
            return None
        m = self.mascara_do_figado(vol)
        if m is None:
            self.tab.status_message.emit("Sem a segmentação do fígado neste exame: rode Órgãos na TC do PET/CT, "
                                         "ou use Fígado: clicar.")
            return None
        c = PO.centro_da_mascara(m)
        return self.medir(vp, "figado", c, mascara=m, como="auto")
