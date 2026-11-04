"""Diálogo de exportação: DICOM (pasta/CD/pendrive/ZIP, com DICOMDIR e visualizador) ou imagens."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QProgressDialog, QPushButton, QRadioButton, QSpinBox, QVBoxLayout, QWidget,
)

from ipe.exporter.anonymize import AnonOptions
from ipe.exporter.core import Cancelled, ExportItem, export_dicom, export_images


def first_name(pn: str) -> str:
    """Primeiro nome do paciente: "SILVA^JOAO CARLOS" / "SILVA, João" -> João; "JOAO DA SILVA" -> Joao."""
    pn = (pn or "").strip()
    for sep in ("^", ","):
        if sep in pn:
            fam, _, giv = pn.partition(sep)
            pn = giv.strip() or fam
            break
    words = [w for w in pn.replace("^", " ").split() if w]
    return words[0].capitalize() if words else ""


def safe_folder(name: str) -> str:
    out = "".join(ch if ch.isalnum() or ch in " -_." else "_" for ch in name).strip(" .")
    return out[:60] or "Exames"


def unique_path(p: Path) -> Path:
    """p, ou p_2, p_3… se já existir e não estiver vazio (arquivos: se já existir)."""
    def busy(x: Path) -> bool:
        return x.exists() and (x.is_file() or any(x.iterdir()))
    if not busy(p):
        return p
    n = 2
    while True:
        q = p.with_name(f"{p.stem}_{n}{p.suffix}")
        if not busy(q):
            return q
        n += 1


class _Bridge(QObject):
    progress = Signal(int, int, str)
    done = Signal(object, object)


class ExportDialog(QDialog):
    """`scopes`: [(rótulo, [ExportItem])]; o primeiro é o padrão. `window`: (W, L) do quadro atual."""

    def __init__(self, repo, settings, scopes: list[tuple[str, list[ExportItem]]], parent=None,
                 window: tuple[float, float] | None = None, force_anonymize: bool = False,
                 cmap: str = "", anonimizar: bool = False, storage_root=None):
        super().__init__(parent)
        from ipe.auth import session as S
        if not S.can("export_identified"):
            force_anonymize = True          # o perfil só exporta anonimizado
        self.repo, self.settings, self.scopes, self.window = repo, settings, scopes, window
        # `anonimizar`: veio do "Anonimizar…" da lista — já vem marcado, mas o médico ainda
        # escolhe o que manter. `force_anonymize` é diferente: o perfil não deixa desmarcar.
        self.anonimizar_pedido = bool(anonimizar) or bool(force_anonymize)
        self.setWindowTitle("Anonimizar cópias" if anonimizar and not force_anonymize else "Exportar")
        self.resize(640, 640)
        cfg = settings.get("export", {}) or {}

        self.scope = QComboBox()
        for label, _items in scopes:
            self.scope.addItem(label)

        self.r_dicom = QRadioButton("DICOM — pasta, CD ou pendrive (abre em outros visualizadores)")
        self.r_img = QRadioButton("Imagens — JPG ou PNG (para aulas, apresentações, artigos)")
        # cópia anonimizada que fica no banco, como outro exame — nada sai da máquina
        self.storage_root = storage_root
        self.r_banco = QRadioButton("Cópia anonimizada no meu banco — vira outro exame na lista (nada sai da máquina)")
        self.r_banco.setToolTip("Os arquivos originais não mudam. A cópia ganha UIDs novos e um ID de "
                                "paciente que não repete os que já estão no banco.")
        self.r_banco.setVisible(self.pode_banco())
        if self.anonimizar_pedido and cfg.get("anon_destino") == "banco" and self.pode_banco():
            self.r_banco.setChecked(True)
        # anonimizar é sobre o arquivo DICOM: JPG/PNG não guardam tag nenhuma para tirar
        (self.r_img if cfg.get("mode") == "images" and not self.anonimizar_pedido
         else self.r_dicom).setChecked(True)

        # --- DICOM
        self.c_dicomdir = QCheckBox("Criar DICOMDIR (padrão de CD/pendrive)")
        self.c_dicomdir.setChecked(cfg.get("dicomdir", True))
        self.c_viewer = QComboBox()
        self.c_viewer.addItem("Completo: medidas em mm, HU/valores, ROIs, janelas, MPR", "full")
        self.c_viewer.addItem("Leve: só as imagens (menor)", "light")
        self.c_viewer.addItem("Sem visualizador", "")
        v = cfg.get("viewer", "full")
        v = "full" if v is True else ("" if v is False else v)
        self.c_viewer.setCurrentIndex(max(0, self.c_viewer.findData(v)))
        self.c_viewer.setToolTip("O visualizador abre no navegador (Chrome, Edge, Firefox, Safari), sem instalar nada.\n"
                                 "Completo: leva os valores originais dos pixels (tamanho parecido com o dos DICOM).")
        self.c_zip = QCheckBox("Compactar num arquivo .zip")
        self.c_zip.setChecked(cfg.get("zip", False))
        dg = QGroupBox("Opções DICOM")
        dl = QVBoxLayout(dg)
        dl.addWidget(self.c_dicomdir)
        vrow = QHBoxLayout()
        vrow.addWidget(QLabel("Visualizador no navegador:"))
        vrow.addWidget(self.c_viewer, 1)
        dl.addLayout(vrow)
        dl.addWidget(self.c_zip)
        self.g_dicom = dg

        # --- imagens
        self.fmt = QComboBox()
        self.fmt.addItems(["JPG", "PNG"])
        self.fmt.setCurrentText(cfg.get("format", "JPG"))
        self.quality = QSpinBox(minimum=50, maximum=100, value=int(cfg.get("quality", 92)), suffix=" %")
        self.win = QComboBox()
        self.win.addItem("Janela do arquivo", None)
        if window is not None:
            self.win.addItem(f"Janela do quadro atual (W {window[0]:.0f} / L {window[1]:.0f})", "current")
            self.win.setCurrentIndex(1)
        self.every = QSpinBox(minimum=1, maximum=100, value=1, prefix="a cada ", suffix=" imagem(ns)")
        self.maxsize = QComboBox()
        for label, v in (("Tamanho original", 0), ("Máx. 1024 px", 1024), ("Máx. 2048 px", 2048), ("Máx. 512 px", 512)):
            self.maxsize.addItem(label, v)
        ig = QGroupBox("Opções de imagem")
        il = QFormLayout(ig)
        il.addRow("Formato:", self.fmt)
        il.addRow("Qualidade (JPG):", self.quality)
        il.addRow("Janela:", self.win)
        self.c_cmap = QCheckBox()
        self.cmap = cmap
        if cmap:
            from ipe.imaging.colormaps import name as cmap_name
            self.c_cmap.setText(f"Usar a cor do quadro ({cmap_name(cmap)})")
            self.c_cmap.setChecked(True)
            il.addRow("Cor:", self.c_cmap)
        self.c_filter = QComboBox()
        from ipe.imaging import filters as _filters
        for nome in _filters.ORDER:
            self.c_filter.addItem(_filters.label(nome), nome)
        il.addRow("Filtro:", self.c_filter)
        il.addRow("Quais:", self.every)
        il.addRow("Tamanho:", self.maxsize)
        self.c_anon_names = QCheckBox("Sem dados do paciente nos nomes das pastas/arquivos")
        self.c_anon_names.setChecked(bool(cfg.get("anon_names", True)) or self.anonimizar_pedido)
        self.c_anon_names.setEnabled(not force_anonymize)
        il.addRow(self.c_anon_names)
        self.g_img = ig

        # --- anonimização
        a = AnonOptions.from_dict(cfg.get("anon"))
        self.g_anon = QGroupBox("Anonimizar (as cópias; o banco não muda)")
        self.g_anon.setCheckable(True)
        self.g_anon.setChecked(bool(a.enabled) or self.anonimizar_pedido)
        if force_anonymize:
            self.g_anon.setEnabled(False)
        self.a_name = QLineEdit(a.name)
        self.a_name.setToolTip("{n} = número do exame nesta exportação (1, 2, …)")
        self.a_id = QLineEdit(a.patient_id)
        self.a_sex = QCheckBox("Manter sexo")
        self.a_sex.setChecked(a.keep_sex)
        self.a_age = QCheckBox("Manter idade")
        self.a_age.setChecked(a.keep_age)
        self.a_dates = QCheckBox("Manter datas do exame")
        self.a_dates.setChecked(a.keep_dates)
        self.a_shift = QCheckBox("Deslocar as datas (mesmo intervalo entre os exames)")
        self.a_shift.setToolTip("Todas as datas do mesmo paciente andam para trás o mesmo número de dias (30 a "
                                "329, sorteado por paciente): a data real some, o intervalo entre o atual e o "
                                "anterior fica. É o perfil Ensino da tela.")
        from ipe.core import mascara as MK
        self.a_shift.setChecked(bool(a.shift_dates) or (force_anonymize and MK.perfil_de(settings) == "ensino"))
        self.a_dates.toggled.connect(self.a_shift.setDisabled)
        self.a_shift.setEnabled(not self.a_dates.isChecked())
        self.a_desc = QCheckBox("Manter descrições (exame/série)")
        self.a_desc.setChecked(a.keep_descriptions)
        self.a_inst = QCheckBox("Manter instituição")
        self.a_inst.setChecked(a.keep_institution)
        self.a_priv = QCheckBox("Remover tags privadas")
        self.a_priv.setChecked(a.remove_private)
        self.a_uids = QCheckBox("Gerar UIDs novos")
        self.a_uids.setChecked(a.new_uids)
        self.a_burn = QComboBox()
        self.a_burn.addItem("Automático: US (fora das regiões de imagem) e imagens marcadas com texto", "auto")
        self.a_burn.addItem(f"Tarjar a faixa superior de todas as imagens ({a.top_pct:g}%)", "top")
        self.a_burn.addItem("Não mexer nos pixels", "none")
        self.a_burn.setCurrentIndex(max(0, self.a_burn.findData(a.burned)))
        self._top_pct = a.top_pct
        al = QFormLayout(self.g_anon)
        al.addRow("Nome do paciente:", self.a_name)
        al.addRow("ID do paciente:", self.a_id)
        grid = QHBoxLayout()
        col1, col2 = QVBoxLayout(), QVBoxLayout()
        for w in (self.a_sex, self.a_age, self.a_dates, self.a_shift, self.a_desc):
            col1.addWidget(w)
        for w in (self.a_inst, self.a_priv, self.a_uids):
            col2.addWidget(w)
        grid.addLayout(col1)
        grid.addLayout(col2)
        al.addRow(grid)
        al.addRow("Texto gravado na imagem:", self.a_burn)
        note = QLabel("Sempre saem: nascimento, accession, endereço/telefone, médicos, operador, estação e outros "
                      "identificadores. O texto gravado nos pixels é tarjado de preto pelo critério acima — "
                      "confira as imagens (em US o nome às vezes fica dentro da área da imagem).")
        note.setWordWrap(True)
        note.setStyleSheet("color:#9a9a9a")
        al.addRow(note)

        # --- destino
        self.dest = QLineEdit(cfg.get("last_dir", "") or str(Path.home()))
        self.c_newdir = QCheckBox("Criar uma pasta nova dentro do destino, chamada:")
        self.c_newdir.setChecked(bool(cfg.get("new_folder", True)))
        self.newdir = QLineEdit(self._default_folder_name(self.anonimizar_pedido))
        self.newdir.setToolTip("Por padrão, o primeiro nome do paciente (ou ANONIMO, se anonimizar). "
                               "Se já existir, vira _2, _3…")
        b = QPushButton("Escolher…")
        b.clicked.connect(self._choose)
        drow = QHBoxLayout()
        drow.addWidget(self.dest, 1)
        drow.addWidget(b)
        self.dest_hint = QLabel()
        self.dest_hint.setStyleSheet("color:#9a9a9a")

        lay = QVBoxLayout(self)
        f = QFormLayout()
        f.addRow("O que exportar:", self.scope)
        lay.addLayout(f)
        lay.addWidget(self.r_dicom)
        lay.addWidget(self.r_img)
        lay.addWidget(self.r_banco)
        lay.addWidget(self.g_dicom)
        lay.addWidget(self.g_img)
        lay.addWidget(self.g_anon)
        self.w_dest = QWidget()
        wl = QVBoxLayout(self.w_dest)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(QLabel("<b>Destino</b>"))
        wl.addLayout(drow)
        nrow = QHBoxLayout()
        nrow.addWidget(self.c_newdir)
        nrow.addWidget(self.newdir, 1)
        wl.addLayout(nrow)
        wl.addWidget(self.dest_hint)
        lay.addWidget(self.w_dest)
        self.banco_hint = QLabel("A cópia aparece na lista de exames com o nome escolhido acima, "
                                 "marcada como origem “anonimizado”. O exame original continua igual.")
        self.banco_hint.setWordWrap(True)
        self.banco_hint.setStyleSheet("color:#9a9a9a")
        lay.addWidget(self.banco_hint)
        bb = QDialogButtonBox()
        self.ok = bb.addButton("Exportar", QDialogButtonBox.AcceptRole)
        bb.addButton("Cancelar", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self._run)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        for w in (self.r_dicom, self.r_img, self.r_banco, self.c_zip, self.c_newdir):
            w.toggled.connect(self._update)
        self.g_anon.toggled.connect(self._anon_toggled)
        self._update()
        self._auto_name = self.newdir.text()
        self.result_obj = None

    # ---------------------------------------------------------- estado
    def _default_folder_name(self, anon: bool = False) -> str:
        if anon or self.g_anon.isChecked() and self.mode() == "dicom":
            return safe_folder(self.a_name.text().split("{")[0].strip("^ _") or "ANONIMO")
        for _label, items in self.scopes:
            for it in items:
                info = self.repo.study_info(it.study_uid) or {}
                name = first_name(info.get("patient_name", ""))
                if name:
                    return safe_folder(name)
        return "Exames"

    def _anon_toggled(self, _on: bool) -> None:
        # só troca o nome se o usuário não tiver digitado outro
        if self.newdir.text() in (getattr(self, "_auto_name", ""), "", "ANONIMO"):
            self._auto_name = self._default_folder_name()
            self.newdir.setText(self._auto_name)

    def mode(self) -> str:
        if self.r_banco.isChecked():
            return "banco"
        return "images" if self.r_img.isChecked() else "dicom"

    def pode_banco(self) -> bool:
        """Só com banco local (o cliente da central não grava arquivos aqui)."""
        return self.storage_root is not None and getattr(self.repo, "db", None) is not None

    def anon_options(self) -> AnonOptions:
        return AnonOptions(enabled=self.g_anon.isChecked(), name=self.a_name.text().strip() or "ANONIMO",
                           patient_id=self.a_id.text().strip() or "ANON{n:03d}", keep_sex=self.a_sex.isChecked(),
                           keep_age=self.a_age.isChecked(), keep_dates=self.a_dates.isChecked(),
                           shift_dates=self.a_shift.isChecked() and not self.a_dates.isChecked(),
                           keep_descriptions=self.a_desc.isChecked(), keep_institution=self.a_inst.isChecked(),
                           remove_private=self.a_priv.isChecked(), new_uids=self.a_uids.isChecked(),
                           burned=self.a_burn.currentData(), top_pct=self._top_pct)

    def _update(self) -> None:
        banco = self.mode() == "banco"
        dicom = self.mode() == "dicom"
        self.newdir.setEnabled(self.c_newdir.isChecked())
        self.g_dicom.setVisible(dicom)
        self.g_img.setVisible(self.mode() == "images")
        self.g_anon.setVisible(dicom or banco)
        self.w_dest.setVisible(not banco)
        self.banco_hint.setVisible(banco)
        # no banco a anonimização não é opcional, e os UIDs novos também não: com os mesmos
        # UIDs a cópia cairia dentro do exame original
        if banco:
            if self.g_anon.isCheckable():
                self._anon_antes = (self.g_anon.isChecked(), self.a_uids.isChecked())
            self.g_anon.setCheckable(False)
            self.a_uids.setChecked(True)
            self.a_uids.setEnabled(False)
            self.a_uids.setToolTip("Obrigatório na cópia dentro do banco: com os mesmos UIDs, as imagens "
                                   "cairiam no exame original.")
            self.ok.setText("Criar cópia")
        elif not self.g_anon.isCheckable():
            antes = getattr(self, "_anon_antes", (True, True))
            self.g_anon.setCheckable(True)
            self.g_anon.setChecked(antes[0])
            self.a_uids.setChecked(antes[1])
            self.a_uids.setEnabled(True)
            self.a_uids.setToolTip("")
        if not banco and hasattr(self, "ok"):
            self.ok.setText("Exportar")
        self.adjustSize()
        if self.c_newdir.isChecked():
            what = "o arquivo .zip" if dicom and self.c_zip.isChecked() else "a pasta nova"
            self.dest_hint.setText(f"Escolha onde criar {what} (ex.: a raiz do pendrive ou Documentos).")
        elif dicom and self.c_zip.isChecked():
            self.dest_hint.setText("Arquivo .zip de destino.")
        elif dicom:
            self.dest_hint.setText("Pasta vazia (ex.: a raiz do pendrive, ou uma pasta nova para gravar no CD).")
        else:
            self.dest_hint.setText("Pasta onde as imagens serão salvas (uma subpasta por exame/série).")

    def _choose(self) -> None:
        if self.mode() == "dicom" and self.c_zip.isChecked() and not self.c_newdir.isChecked():
            path, _ = QFileDialog.getSaveFileName(self, "Arquivo ZIP", str(Path(self.dest.text()) / "exames.zip"),
                                                  "ZIP (*.zip)")
        else:
            path = QFileDialog.getExistingDirectory(self, "Pasta de destino", self.dest.text())
        if path:
            self.dest.setText(path)

    def _save_prefs(self) -> None:
        dest = Path(self.dest.text())
        antigo = self.settings.get("export", {}) or {}
        modo = antigo.get("mode", "dicom") if self.mode() == "banco" else self.mode()
        destino = ("banco" if self.mode() == "banco" else "exportar") if self.anonimizar_pedido \
            else antigo.get("anon_destino", "exportar")
        self.settings.set("export", {
            "mode": modo, "anon_destino": destino, "dicomdir": self.c_dicomdir.isChecked(), "viewer": self.c_viewer.currentData(),
            "zip": self.c_zip.isChecked(), "format": self.fmt.currentText(), "quality": self.quality.value(),
            "anon_names": self.c_anon_names.isChecked(), "new_folder": self.c_newdir.isChecked(),
            "anon": (self.anon_options() if self.mode() != "banco" else self._anon_para_lembrar()).to_dict(),
            "last_dir": self.dest.text().strip() if self.c_newdir.isChecked()
            else str(dest.parent if dest.suffix.lower() == ".zip" else dest)})
        try:
            self.settings.save()
        except Exception:  # noqa: BLE001
            pass

    def _anon_para_lembrar(self) -> AnonOptions:
        """No banco os UIDs são forçados; o que fica lembrado é a escolha de antes."""
        o = self.anon_options()
        antes = getattr(self, "_anon_antes", None)
        if antes is not None:
            o.enabled, o.new_uids = antes
        return o

    # ---------------------------------------------------------- executar
    def target(self) -> Path:
        dest = Path(self.dest.text().strip() or ".")
        if self.c_newdir.isChecked():
            name = safe_folder(self.newdir.text().strip() or self._default_folder_name())
            if self.mode() == "dicom" and self.c_zip.isChecked():
                return unique_path(dest / f"{name}.zip")
            return unique_path(dest / name)
        if self.mode() == "dicom" and self.c_zip.isChecked() and dest.suffix.lower() != ".zip":
            dest = dest / "exames.zip"
        return dest

    def job(self, progress=None, cancel=None):
        items = self.scopes[self.scope.currentIndex()][1]
        if self.mode() == "banco":
            from ipe.exporter.copia import copiar_anonimizado
            return copiar_anonimizado(self.repo, self.repo.db, self.storage_root, items, self.anon_options(),
                                      progress, cancel)
        dest = getattr(self, "_fixed_target", None) or self.target()
        if self.mode() == "dicom":
            return export_dicom(self.repo, items, dest, self.anon_options(), self.c_dicomdir.isChecked(),
                                self.c_viewer.currentData() or False, self.c_zip.isChecked(), progress, cancel)
        window = self.window if self.win.currentData() == "current" else None
        return export_images(self.repo, items, dest, self.fmt.currentText().lower(), self.quality.value(), window,
                             False, self.maxsize.currentData() or None, self.every.value(),
                             self.c_anon_names.isChecked(), progress, cancel,
                             self.cmap if self.cmap and self.c_cmap.isChecked() else None,
                             self.c_filter.currentData() or "")

    def _run(self) -> None:
        if self.mode() == "banco":
            self._save_prefs()
            self._rodar("Criando a cópia anonimizada")
            return
        if not self.dest.text().strip():
            QMessageBox.warning(self, "Exportar", "Escolha o destino.")
            return
        self._fixed_target = None
        dest = self.target()
        if self.c_newdir.isChecked():
            self._fixed_target = dest
        elif self.mode() == "dicom" and not self.c_zip.isChecked() and dest.exists() and any(dest.iterdir()):
            sub = dest / "EXAMES"
            n = 2
            while sub.exists() and any(sub.iterdir()):
                sub = dest / f"EXAMES_{n}"
                n += 1
            if QMessageBox.question(self, "Exportar", f"A pasta não está vazia. Gravar em\n{sub}?") != QMessageBox.Yes:
                return
            self.dest.setText(str(sub))
        self._save_prefs()
        self._rodar("Exportando")

    def _rodar(self, titulo: str) -> None:
        dlg = QProgressDialog("Preparando…", "Cancelar", 0, 100, self)
        dlg.setWindowTitle(titulo)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        # a barra chega ao fim de uma etapa antes do trabalho acabar (a cópia no banco tem duas:
        # anonimizar e guardar); quem fecha a janela é o fim do trabalho, não a barra cheia
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        stop = threading.Event()
        dlg.canceled.connect(stop.set)
        bridge = _Bridge()

        def on_progress(d, t, text):
            dlg.setMaximum(max(1, t))
            dlg.setValue(min(d, max(1, t)))
            dlg.setLabelText(text)
        bridge.progress.connect(on_progress)
        state = {}

        def finished(res, err):
            state["done"] = True
            dlg.reset()
            dlg.close()
            self._finished(res, err)
        bridge.done.connect(finished)

        def work():
            try:
                res = self.job(lambda d, t, x: bridge.progress.emit(d, t, x), stop.is_set)
                bridge.done.emit(res, None)
            except Exception as e:  # noqa: BLE001
                bridge.done.emit(None, e)
        self._bridge = bridge
        threading.Thread(target=work, daemon=True).start()
        dlg.exec()

    def exec(self) -> int:  # noqa: A003
        from ipe.auth import session as S
        if not S.require("export", self.parent()):
            return 0
        return super().exec()

    def _finished(self, res, err) -> None:
        if isinstance(err, Cancelled):
            QMessageBox.information(self, "Exportar", "Exportação cancelada.")
            return
        if err is not None:
            QMessageBox.warning(self, "Exportar", f"Falha na exportação:\n{err}")
            return
        self.result_obj = res
        from ipe.auth import session as S
        items = self.scopes[self.scope.currentIndex()][1]
        if self.mode() == "banco":
            self._terminou_banco(res, items)
            return
        anon = self.mode() == "dicom" and self.g_anon.isChecked()
        for it in items:
            S.audit(self.repo, "anonimizar" if anon else "exportar",
                    f"{self.mode()} → {getattr(self, '_fixed_target', None) or self.target()}",
                    study_uid=getattr(it, "study_uid", "") or "")
        if self.mode() == "dicom":
            what = f"{res.files} arquivo(s) DICOM de {res.studies} exame(s)"
            extra = [("DICOMDIR criado" if res.dicomdir else "sem DICOMDIR")]
            if res.viewer is not None or (res.zip_path and self.c_viewer.currentData()):
                extra.append("visualizador: ABRIR_VISUALIZADOR.html")
        else:
            what = f"{res.images} imagem(ns)"
            extra = []
        msg = f"{what} exportado(s).\n{res.dest}"
        if extra:
            msg += "\n" + " · ".join(extra)
        if res.warnings:
            msg += "\n\nAvisos:\n" + "\n".join(res.warnings[:5])
        if res.errors:
            msg += f"\n\n{len(res.errors)} arquivo(s) com erro:\n" + "\n".join(res.errors[:5])
        box = QMessageBox(QMessageBox.Information, "Exportar", msg, parent=self)
        open_btn = box.addButton("Abrir pasta", QMessageBox.ActionRole)
        box.addButton("OK", QMessageBox.AcceptRole)
        box.exec()
        if box.clickedButton() is open_btn:
            folder = res.dest.parent if res.dest.suffix.lower() == ".zip" else res.dest
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        self.accept()



    # ---------------------------------------------------------- cópia no banco
    def mensagem_banco(self, res) -> str:
        if not res.estudos:
            msg = "Nenhuma imagem foi copiada para o banco."
        else:
            msg = (f"Cópia anonimizada criada: {len(res.estudos)} exame(s), {res.imagens} imagem(ns).\n"
                   f"Aparece na lista de exames como {self.a_name.text().strip() or 'ANONIMO'}. "
                   "O exame original não mudou.")
        if res.avisos:
            msg += "\n\nAvisos:\n" + "\n".join(res.avisos[:5])
        if res.erros:
            msg += f"\n\n{len(res.erros)} arquivo(s) com erro:\n" + "\n".join(res.erros[:5])
        return msg

    def _terminou_banco(self, res, items) -> None:
        from ipe.auth import session as S
        for it in items:
            S.audit(self.repo, "anonimizar cópia no banco",
                    "novo exame: " + (", ".join(res.estudos) or "nenhum"),
                    study_uid=getattr(it, "study_uid", "") or "")
        self.avisar(self.mensagem_banco(res))
        self.accept()

    def avisar(self, msg: str) -> None:
        QMessageBox.information(self, "Cópia anonimizada", msg)
