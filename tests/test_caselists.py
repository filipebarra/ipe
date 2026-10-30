"""Fase 6: listas de casos (pastas, dados do caso, ordem), pacotes e modo reunião."""
import zipfile
from pathlib import Path

import pydicom
import pytest

from ipe.caselists.package import (
    PackageError, export_case_list, import_case_list, read_manifest,
)
from ipe.importer.scanner import Importer


def _studies(repo):
    rows = repo.search_studies()
    return {r.accession: r.study_uid for r in rows}


def test_list_management(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    st = _studies(repo)
    folder = repo.create_case_list("Mama", "folder")
    sub = repo.create_case_list("Reunião março", "meeting", parent=folder)
    for acc in ("ACC3001", "ACC2001", "ACC1001"):
        assert repo.add_to_case_list(sub, st[acc], f"Caso {acc}")
    assert not repo.add_to_case_list(sub, st["ACC1001"])          # sem repetir
    repo.update_list_item(sub, st["ACC2001"], hidden_diagnosis="CDI", tags=["mama", "RM"],
                          clinical_summary="nódulo palpável", show_series=["x", "y"])
    items = repo.list_items(sub)
    assert [i["study_uid"] for i in items] == [st["ACC3001"], st["ACC2001"], st["ACC1001"]]
    assert items[1]["tags"] == ["mama", "RM"] and items[1]["show_series"] == ["x", "y"]
    repo.reorder_case_list(sub, [st["ACC1001"], st["ACC3001"]])
    assert [i["study_uid"] for i in repo.list_items(sub)] == [st["ACC1001"], st["ACC3001"], st["ACC2001"]]
    dup = repo.duplicate_case_list(sub)
    assert len(repo.list_items(dup)) == 3 and repo.list_items(dup)[2]["hidden_diagnosis"] == "CDI"
    repo.remove_from_case_list(dup, [st["ACC1001"]])
    assert len(repo.list_items(dup)) == 2 and len(repo.list_items(sub)) == 3
    repo.update_case_list(sub, name="Reunião abril")
    tree = {d["id"]: d for d in repo.case_list_tree()}
    assert tree[sub]["name"] == "Reunião abril" and tree[sub]["parent"] == folder and tree[folder]["kind"] == "folder"
    with pytest.raises(ValueError):
        repo.update_case_list(folder, parent_fk=folder)
    # apagar a pasta: as listas sobem um nível, os exames continuam
    repo.delete_case_list(folder)
    tree = {d["id"]: d for d in repo.case_list_tree()}
    assert folder not in tree and tree[sub]["parent"] is None
    assert len(repo.search_studies()) >= 4
    assert (sub, "Reunião abril") in repo.lists_of_study(st["ACC1001"])


def test_export_import_package(env, sample_dir, tmp_path):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    st = _studies(repo)
    lid = repo.create_case_list("Ensino", "meeting")
    repo.add_to_case_list(lid, st["ACC2001"], "Caso 1 — realce", hidden_diagnosis="Fibroadenoma",
                          tags=["mama"])
    se = repo.series_for_study(st["ACC2001"])[0]
    inst = repo.instances_for_series(se.series_uid)[0]
    repo.toggle_key_image(st["ACC2001"], se.series_uid, inst["sop_uid"], 0)
    repo.save_annotation(db_id=None, study_uid=st["ACC2001"], series_uid=se.series_uid, sop_uid=inst["sop_uid"],
                         frame_index=0, kind="line", data='{"points": [[1, 2], [3, 4]]}')
    repo.update_list_item(lid, st["ACC2001"], show_series=[se.series_uid])
    # pacote anonimizado
    out = tmp_path / "ensino.zip"
    r = export_case_list(repo, lid, out, with_images=True)
    assert r.cases == 1 and r.files == len(repo.files_for_study(st["ACC2001"]))
    man = read_manifest(out)
    case = man["cases"][0]
    assert case["hidden_diagnosis"] == "Fibroadenoma" and case["study_uid"] != st["ACC2001"]
    assert case["show_series"][0] != se.series_uid and len(case["key_images"]) == 1
    with zipfile.ZipFile(out) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".dcm"))
        zf.extract(name, tmp_path)
    ds = pydicom.dcmread(tmp_path / name)
    assert str(ds.PatientName) == "CASO^001" and ds.PatientID == "CASO001"
    assert "PatientBirthDate" not in ds and "InstitutionName" not in ds and ds.AccessionNumber == ""
    assert ds.StudyInstanceUID == case["study_uid"] and ds.PatientIdentityRemoved == "YES"
    orig = pydicom.dcmread(repo.files_for_study(st["ACC2001"])[0])
    assert str(orig.PatientName) != "CASO^001"               # o original não muda
    # importar no mesmo banco: vira um exame novo, anônimo, com chave e medida
    n_before = len(repo.search_studies())
    ir = import_case_list(repo, db, paths.storage, out)
    assert ir.cases == 1 and not ir.missing and len(repo.search_studies()) == n_before + 1
    it = repo.list_items(ir.list_id)[0]
    assert it["friendly_name"] == "Caso 1 — realce" and it["patient_name"].startswith("CASO")
    assert it["show_series"] == case["show_series"]
    assert len(repo.key_images(it["study_uid"])) == 1
    assert repo.count_annotations(it["study_uid"]) == 1
    # só a lista: referencia os exames originais
    out2 = tmp_path / "so_lista.zip"
    r2 = export_case_list(repo, lid, out2, with_images=False)
    assert r2.files == 0 and read_manifest(out2)["cases"][0]["study_uid"] == st["ACC2001"]
    ir2 = import_case_list(repo, db, paths.storage, out2, name="Cópia")
    assert repo.list_items(ir2.list_id)[0]["study_uid"] == st["ACC2001"]
    bad = tmp_path / "x.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("a.txt", "x")
    with pytest.raises(PackageError):
        read_manifest(bad)


def _window(env, sample_dir):
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    Importer(db, paths.storage).import_paths([sample_dir])
    s = Settings(paths.settings_file)
    s.set("meeting.fullscreen", False)
    w = MainWindow(paths, s)
    w.resize(1300, 850)
    w.show()
    w.browser.refresh()
    return app, w, repo


def test_browser_lists_ui(env, sample_dir):
    from ipe.ui.browser import KEY_INDEX
    app, w, repo = _window(env, sample_dir)
    b = w.browser
    st = _studies(repo)
    folder = repo.create_case_list("Ensino", "folder")
    lid = repo.create_case_list("Mama", "meeting", parent=folder)
    rows = [r for r in b.model.rows if r.accession in ("ACC3001", "ACC2001")]
    b._add_to_list(lid, "normal", rows)                      # como soltar exames arrastados na lista
    b.tree.rebuild(select=lid)
    b._list_selected(lid)
    assert b.model.rowCount() == 2 and not b.table.isColumnHidden(KEY_INDEX["case_name"])
    assert {r.case_n for r in b.model.rows} == {1, 2}
    # pasta mostra os casos de todas as listas dentro dela
    b._list_selected(folder)
    assert b.model.rowCount() == 2
    # "Todos": as colunas da lista somem e não são salvas
    b._list_selected(None)
    assert b.table.isColumnHidden(KEY_INDEX["case_name"]) and b.model.rowCount() >= 4
    assert "case_name" not in (w.settings.get("browser.columns") or [])
    # mover a lista para a raiz arrastando na árvore
    b.tree.move_node(lid, None)
    assert repo.case_list_info(lid)["parent"] is None
    # arrastar exames: a tabela gera o mime com os UIDs
    from ipe.ui.caselists import STUDIES_MIME
    md = b.model.mimeData([b.model.index(0, 0)])
    assert bytes(md.data(STUDIES_MIME)).decode() == b.model.rows[0].study_uid
    # editor da lista: ordem e campos do caso
    from ipe.ui.caselists import ListEditorDialog
    dlg = ListEditorDialog(repo, lid, b)
    assert dlg.cases.count() == 2
    dlg.f_name.setText("Caso A")
    dlg.f_dx.setPlainText("Carcinoma")
    dlg.f_series.item(0).setCheckState(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.Checked)
    first = dlg._cur
    dlg._move(1)                                  # desce o primeiro caso
    items = repo.list_items(lid)
    assert items[1]["study_uid"] == first and items[1]["friendly_name"] == "Caso A"
    assert items[1]["hidden_diagnosis"] == "Carcinoma" and len(items[1]["show_series"]) == 1
    dlg.name.setText("Mama — abril")
    dlg.accept()
    assert repo.case_list_info(lid)["name"] == "Mama — abril"
    w.close()
    _ = st


def test_meeting_mode(env, sample_dir):
    app, w, repo = _window(env, sample_dir)
    st = _studies(repo)
    lid = repo.create_case_list("Reunião", "meeting")
    repo.add_to_case_list(lid, st["ACC1001"], "Nódulo pulmonar", clinical_summary="Tosse", hidden_diagnosis="Adenocarcinoma")
    repo.add_to_case_list(lid, st["ACC2001"], "Realce na mama")
    # um exame já aberto antes da reunião também fica oculto
    assert w.handle_external({"accession": "ACC4001"}) == "aberto"
    other = w.tabs.currentWidget()
    assert "FANTOMA" in w.tabs.tabText(w.tabs.indexOf(other)).upper() or other.title()
    w.start_meeting(lid)
    mc = w.meeting
    tab = mc.tab
    app.processEvents()
    assert tab.case_label == "Nódulo pulmonar" and tab.anonymize and not tab.anon_action.isEnabled()
    assert all(v.case_label == "Nódulo pulmonar" for v in tab.viewports)
    lines = tab.viewports[0]._text_lines()
    flat = " ".join(t for side in lines.values() for t, _h in side)
    assert "Nódulo pulmonar" in flat and "TESTE" not in flat.upper() and "FANTOMA" not in flat.upper()
    assert other.anonymize and "FANTOMA" not in other.title().upper()
    assert not w.home_bar.buttons["pacs"].isEnabled() and w.home_bar.buttons["anon"].isChecked()
    # banco: nome amigável no lugar do paciente, sem ID
    b = w.browser
    from ipe.ui.browser import KEY_INDEX
    names = {b.model.data(b.model.index(i, KEY_INDEX["patient_name"])) for i in range(b.model.rowCount())}
    assert "Nódulo pulmonar" in names and not any("TESTE" in n.upper() for n in names)
    assert {b.model.data(b.model.index(i, KEY_INDEX["patient_id"])) for i in range(b.model.rowCount())} == {"•••"}
    # história visível, resposta só ao revelar
    bar = mc.bar
    assert "Tosse" in bar.info.text() and "Adenocarcinoma" not in bar.info.text()
    bar.btn_answer.setChecked(True)
    assert "Adenocarcinoma" in bar.info.text()
    # próximo caso: a aba anterior fecha, a resposta volta a ficar oculta
    mc.next()
    assert mc.index == 1 and mc.tab is not tab and w.tabs.indexOf(tab) < 0
    assert mc.tab.case_label == "Realce na mama" and not mc.bar.btn_answer.isChecked()
    mc.go(0)
    assert mc.tab.case_label == "Nódulo pulmonar"
    # abrir outro exame durante a reunião: já vem oculto
    assert w.handle_external({"accession": "ACC3001"}) == "aberto"
    during = w.tabs.currentWidget()
    assert during.anonymize
    mc.end()
    assert not during.anonymize
    app.processEvents()
    assert w.meeting is None and not b.model.anonymize and not other.anonymize
    assert w.home_bar.buttons["pacs"].isEnabled() and not w.home_bar.buttons["anon"].isChecked()
    assert w.tabs.currentWidget() is b
    w.close()


def test_lista_inteligente_filtra_por_instituicao(env, sample_dir):
    """O caso dele: “MG unidade Crispim”. Faltava o critério de unidade."""
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    linhas = repo.search_studies(limit=100)
    assert linhas
    inst = next((r.institution for r in linhas if r.institution), "")
    assert inst, "o fantoma precisa de instituição para este teste valer"
    todos = repo.smart_study_uids({})
    so_essa = repo.smart_study_uids({"institution": inst[:4].lower()})
    assert so_essa and set(so_essa) <= set(todos)
    assert repo.smart_study_uids({"institution": "unidade que não existe"}) == []
