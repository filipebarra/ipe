"""Anonimizar: exportar **ou** criar uma cópia anonimizada no próprio banco, como outro exame.

O original nunca muda. A cópia no banco precisa de UIDs novos (senão cairia dentro do original)
e de um ID de paciente que não repita os que já estão no banco.
"""
from _menus import submenu, todas  # noqa: F401
import hashlib
from pathlib import Path

import pydicom
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.exporter.core import ExportItem
from ipe.importer.scanner import Importer


@pytest.fixture()
def janela(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    w.browser.refresh()
    yield app, w
    w.close()


def _dialogo(w, uid, **kw):
    from ipe.ui.export_dialog import ExportDialog
    return ExportDialog(w.repo, w.settings, [("1 exame", [ExportItem(uid)])], w, anonimizar=True,
                        storage_root=w.browser.storage_root, **kw)


def _esperar(cond, ms=20000):
    from PySide6.QtTest import QTest
    for _ in range(ms // 20):
        if cond():
            return
        QTest.qWait(20)
    raise AssertionError("não terminou")


def _arquivos(repo, study_uid):
    out = []
    for s in repo.series_for_study(study_uid):
        out += [i["path"] for i in repo.instances_for_series(s.series_uid)]
    return sorted(out)


def _hashes(paths):
    return {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}


def test_a_janela_deixa_escolher_exportar_ou_banco(janela):
    app, w = janela
    uid = w.repo.search_studies()[0].study_uid
    d = _dialogo(w, uid)
    assert not d.r_banco.isHidden()
    assert d.mode() == "dicom" and d.ok.text() == "Exportar"
    d.r_banco.setChecked(True)
    assert d.mode() == "banco"
    assert d.w_dest.isHidden(), "na cópia no banco não há pasta de destino"
    assert not d.banco_hint.isHidden()
    assert not d.g_anon.isHidden() and not d.g_anon.isCheckable(), "no banco anonimizar não é opcional"
    assert d.a_uids.isChecked() and not d.a_uids.isEnabled(), "UIDs novos são obrigatórios"
    assert d.ok.text() == "Criar cópia"
    d.r_dicom.setChecked(True)          # volta como estava
    assert d.g_anon.isCheckable() and d.g_anon.isChecked() and d.a_uids.isEnabled()
    assert not d.w_dest.isHidden() and d.ok.text() == "Exportar"
    d.close()


def test_sem_banco_local_a_opcao_nao_aparece(janela):
    app, w = janela
    from ipe.ui.export_dialog import ExportDialog
    uid = w.repo.search_studies()[0].study_uid
    d = ExportDialog(w.repo, w.settings, [("1 exame", [ExportItem(uid)])], w, anonimizar=True)
    assert d.r_banco.isHidden() and not d.pode_banco()
    d.close()


def test_a_copia_vira_outro_exame_e_o_original_nao_muda(janela):
    app, w = janela
    repo = w.repo
    original = repo.search_studies()[0]
    arquivos = _arquivos(repo, original.study_uid)
    antes = _hashes(arquivos)
    n_antes = len(repo.search_studies())
    d = _dialogo(w, original.study_uid)
    d.r_banco.setChecked(True)
    d.a_uids.setChecked(False)          # mesmo tentando, o banco força UIDs novos
    res = d.job()
    assert len(res.estudos) == 1 and res.imagens == original.num_images and not res.erros
    novo_uid = res.estudos[0]
    assert novo_uid != original.study_uid
    assert len(repo.search_studies()) == n_antes + 1
    novo = next(r for r in repo.search_studies() if r.study_uid == novo_uid)
    assert novo.patient_name.upper().startswith("ANONIMO")
    assert novo.patient_id == "ANON001"
    assert novo.origin == "anonymized"
    assert novo.num_images == original.num_images
    assert novo.num_series == original.num_series
    # o original: mesmos arquivos, mesmo conteúdo, mesmo nome
    assert _arquivos(repo, original.study_uid) == arquivos
    assert _hashes(arquivos) == antes
    assert next(r for r in repo.search_studies() if r.study_uid == original.study_uid).patient_name \
        == original.patient_name
    # a cópia tem arquivos próprios, anonimizados, e miniaturas
    copias = _arquivos(repo, novo_uid)
    assert copias and not set(copias) & set(arquivos)
    ds = pydicom.dcmread(copias[0], stop_before_pixels=True)
    assert str(ds.PatientName).upper().startswith("ANONIMO")
    assert ds.SOPInstanceUID not in {pydicom.dcmread(a, stop_before_pixels=True).SOPInstanceUID
                                     for a in arquivos}
    for s in repo.series_for_study(novo_uid):
        assert repo.has_thumbnail(s.series_uid)
    d.close()


def test_duas_copias_nao_viram_o_mesmo_paciente(janela):
    app, w = janela
    repo = w.repo
    uids = [r.study_uid for r in repo.search_studies()[:2]]
    ids = []
    for uid in uids:
        d = _dialogo(w, uid)
        d.r_banco.setChecked(True)
        ids += [next(r for r in repo.search_studies() if r.study_uid == u).patient_id
                for u in d.job().estudos]
        d.close()
    assert ids == ["ANON001", "ANON002"]


def test_pelo_menu_da_lista_criar_copia_atualiza_a_lista(janela, monkeypatch):
    """O caminho inteiro: botão direito → Anonimizar → banco → Criar cópia → aparece na lista."""
    app, w = janela
    from ipe.ui.export_dialog import ExportDialog
    b = w.browser
    n_antes = b.model.rowCount()
    b.table.selectRow(0)
    avisos = []
    monkeypatch.setattr(ExportDialog, "avisar", lambda self, msg: avisos.append(msg))
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: avisos.append(("W",) + a[1:]))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: avisos.append(("I",) + a[1:]))

    def exec_(self):
        self.r_banco.setChecked(True)
        self.ok.click()
        _esperar(lambda: self.result_obj is not None)
        return 1
    monkeypatch.setattr(ExportDialog, "exec", exec_)
    menu = b.menu_do_exame(b.selected_rows())
    next(a for a in todas(menu) if a.text().startswith("Anonimizar")).trigger()
    assert avisos and avisos[0].startswith("Cópia anonimizada criada: 1 exame(s)")
    assert b.model.rowCount() == n_antes + 1, "a lista mostra a cópia sem precisar atualizar à mão"


def test_a_escolha_fica_lembrada_so_para_anonimizar(janela, monkeypatch):
    app, w = janela
    from ipe.ui.export_dialog import ExportDialog
    uid = w.repo.search_studies()[0].study_uid
    monkeypatch.setattr(ExportDialog, "avisar", lambda self, msg: None)
    d = _dialogo(w, uid)
    d.r_banco.setChecked(True)
    d.ok.click()
    _esperar(lambda: d.result_obj is not None)
    assert w.settings.get("export")["anon_destino"] == "banco"
    assert w.settings.get("export")["mode"] == "dicom"
    d2 = _dialogo(w, uid)
    assert d2.mode() == "banco", "quem anonimizou no banco da última vez volta no banco"
    d3 = ExportDialog(w.repo, w.settings, [("1 exame", [ExportItem(uid)])], w,
                      storage_root=w.browser.storage_root)
    assert d3.mode() == "dicom", "o Exportar comum não abre na cópia no banco"
    for x in (d, d2, d3):
        x.close()


def test_a_limpeza_automatica_nao_apaga_a_copia():
    """A cópia anonimizada só existe aqui (não está no PACS): conta como importada."""
    from datetime import datetime, timedelta
    from ipe.automation.rules import StudyStat, select_for_deletion
    import dataclasses
    campos = {f.name for f in dataclasses.fields(StudyStat)}
    velho = datetime(2020, 1, 1)
    base = dict(study_uid="1", origin="anonymized", date_added=velho, modalities="MR", size_bytes=1)
    st = StudyStat(**{k: v for k, v in base.items() if k in campos},
                   **{k: None for k in campos - set(base) - {"protected"}})
    escolhidos = select_for_deletion([st], {"only_network": True, "max_age_days": 30},
                                     velho + timedelta(days=400))
    assert escolhidos == []
    st2 = dataclasses.replace(st, origin="retrieved")
    assert select_for_deletion([st2], {"only_network": True, "max_age_days": 30},
                               velho + timedelta(days=400)), "o controle: baixado é apagado"
