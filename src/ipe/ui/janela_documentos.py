"""Documentos anexados aos exames (mixin da MainWindow, separado do `main_window.py` na 0.100.42).

Aqui ficam: anexar arquivos (PDF, imagens) ao exame, o roteamento dos anexos soltos e abrir os documentos.

Os métodos continuam sendo da MainWindow (mesmos nomes): o resto do programa e os testes não mudam.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QMessageBox,
)

from ipe.importer.scanner import Importer
from ipe.ui.browser import fmt_date
from ipe.ui.viewer.viewer_tab import ViewerTab

log = logging.getLogger("ipe.ui.main_window")      # o mesmo registro de antes da separação


class DocumentosMixin:
    """DocumentosMixin: métodos do ViewerTab separados (mesmos nomes)."""

    # ------------------------------------------------------------------ documentos anexados (0.99.57)
    def _fonte_do_exame(self, study_uid: str):
        """Um arquivo do exame (para copiar paciente e exame) ou, sem arquivo aqui, os dados do banco."""
        from pydicom.dataset import Dataset
        try:
            for f in self.repo.files_for_study(study_uid):
                if f and Path(f).exists():
                    return str(f)
        except Exception:  # noqa: BLE001
            log.exception("arquivo do exame para o anexo")
        info = self.repo.study_info(study_uid) or {}
        ds = Dataset()
        for kw, k in (("PatientName", "patient_name"), ("PatientID", "patient_id"), ("PatientBirthDate", "birth_date"),
                      ("PatientSex", "sex"), ("PatientAge", "patient_age"), ("StudyDate", "study_date"),
                      ("StudyTime", "study_time"), ("AccessionNumber", "accession"),
                      ("StudyDescription", "description"), ("ReferringPhysicianName", "referring"),
                      ("InstitutionName", "institution")):
            if info.get(k):
                setattr(ds, kw, info[k])
        ds.StudyInstanceUID = study_uid
        return ds

    def anexar_ao_exame(self, study_uid: str, arquivos, confirmar: bool = False) -> dict:
        """PDF e imagens viram DICOM dentro do exame (importer/anexos.py). Devolve {"series", "n", "avisos",
        "enviados"}."""
        import shutil
        import tempfile
        from ipe.auth import session as S
        from ipe.importer import anexos as AX
        out = {"series": [], "n": 0, "avisos": [], "enviados": 0}
        arquivos = [Path(a) for a in arquivos if Path(a).exists()]
        if not arquivos or not study_uid:
            return out
        if not S.require("import", self, "anexar documentos ao exame"):
            return out
        info = self.repo.study_info(study_uid) or {}
        if confirmar:
            quem = (info.get("patient_name") or "").replace("^", " ")
            if QMessageBox.question(self, "Anexar ao exame",
                                    f"Anexar {len(arquivos)} arquivo(s) ao exame de {quem} — "
                                    f"{info.get('description', '')} ({fmt_date(info.get('study_date', ''))})?") \
                    != QMessageBox.Yes:
                return out
        u = S.get()
        fonte = self._fonte_do_exame(study_uid)
        try:
            dss, avisos = AX.criar(arquivos, fonte, (u.full_name or u.username) if u else "")
        except Exception as e:  # noqa: BLE001
            log.exception("anexar")
            QMessageBox.warning(self, "Anexar ao exame", f"Não deu para converter: {e}")
            return out
        out["avisos"] = avisos
        if dss:
            tmp = Path(tempfile.mkdtemp(prefix="ipe_anexos_"))
            try:
                AX.gravar(dss, tmp)
                r = Importer(self.db, self.storage, copy_to_storage=True).import_paths([tmp])
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            out["series"] = sorted({str(d.SeriesInstanceUID) for d in dss})
            out["n"] = len(dss)
            from ipe.central.client_repo import upload_if_client
            upload_if_client(self.repo, study_uid)
            S.audit(self.repo, "anexou_documento", ", ".join(a.name for a in arquivos)[:400], study_uid)
            out["enviados"] = self._rotear_anexos(study_uid, info, out["series"])
            self.browser.refresh()
            for tab in self.all_viewer_tabs():
                if study_uid in (getattr(tab, "study_order", None) or [tab.study_uid]):
                    try:
                        tab.recarregar_series()
                    except Exception:  # noqa: BLE001
                        log.exception("recarregar as séries depois do anexo")
            msg = f"{len(dss)} anexo(s) gravado(s) no exame" + (f"; enviado(s) a {out['enviados']} destino(s)"
                                                                  if out["enviados"] else "") + "."
            self.statusBar().showMessage(msg, 12000)
            del r
        if avisos:
            QMessageBox.warning(self, "Anexar ao exame", "Alguns arquivos não entraram:\n\n" + "\n".join(avisos))
        return out

    def _rotear_anexos(self, study_uid: str, info: dict, series_uids: list[str]) -> int:
        """O anexo segue as regras de roteamento que valem para o exame (a origem do exame não conta aqui)."""
        from ipe.automation.rules import route_matches
        n = 0
        try:
            regras = self.repo.rules("route")
        except Exception:  # noqa: BLE001
            return 0
        for r in regras:
            cfg = dict(r.get("config") or {})
            cfg.pop("origins", None)
            if not r.get("active") or not cfg.get("node_id") or not route_matches(cfg, info, ""):
                continue
            node = self.repo.node(cfg["node_id"])
            if node is None:
                continue
            try:
                self.net.send(node, self.repo.identity(cfg.get("identity_id")), [study_uid],
                              f"Anexo → {node['name']}", series_uids=series_uids)
                n += 1
            except Exception:  # noqa: BLE001
                log.exception("enviar o anexo")
        return n

    def alvo_dos_anexos(self, obj=None) -> tuple[str, bool]:
        """(exame, precisa confirmar) para arquivos soltos: o exame do visualizador sob o mouse, ou o exame
        selecionado no banco de dados (com confirmação)."""
        w = obj
        while w is not None:
            if isinstance(w, ViewerTab):
                vp = getattr(w, "active", None)
                uid = (vp.study_uid if vp is not None and getattr(vp, "study_uid", "") else "") or w.study_uid
                return uid, False
            w = w.parentWidget() if hasattr(w, "parentWidget") else None
        if self.tabs.currentWidget() is self.browser or obj is None or self.browser.isAncestorOf(obj):
            rows = self.browser.selected_rows()
            if len(rows) == 1:
                return rows[0].study_uid, True
        return "", False

    def anexar_soltos(self, docs, recusados, obj=None) -> dict | None:
        """Arquivos PDF/imagem soltos numa janela do programa."""
        if recusados:
            QMessageBox.information(self, "Anexar ao exame", "Estes arquivos não são PDF nem imagem e ficaram de "
                                    "fora (salve como PDF e arraste de novo):\n\n" +
                                    "\n".join(Path(p).name for p in recusados))
        if not docs:
            return None
        uid, confirmar = self.alvo_dos_anexos(obj)
        if not uid:
            QMessageBox.information(self, "Anexar ao exame", "Para anexar um PDF ou imagem, solte o arquivo sobre o "
                                    "exame aberto no visualizador, ou selecione um exame (um só) no banco de dados e "
                                    "solte de novo.")
            return None
        return self.anexar_ao_exame(uid, docs, confirmar=confirmar)

    def escolher_anexos(self, study_uid: str) -> dict | None:
        """Botão direito no exame ▸ Anexar documento (PDF ou imagem)…"""
        from PySide6.QtWidgets import QFileDialog
        from ipe.importer import anexos as AX
        filtro = "PDF e imagens (" + " ".join(f"*{e}" for e in sorted(AX.PDF | AX.IMAGENS)) + ")"
        nomes, _f = QFileDialog.getOpenFileNames(self, "Anexar ao exame", "", filtro)
        if not nomes:
            return None
        return self.anexar_ao_exame(study_uid, nomes)

    def abrir_documentos(self, study_uid: str):
        from ipe.ui.documentos_dialog import DocumentosDialog
        d = DocumentosDialog(self.repo, study_uid, self, anexar=lambda: self.escolher_anexos(study_uid))
        self._documentos_dlg = d
        d.show()
        return d
