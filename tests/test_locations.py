"""Locais (bancos) — registro, troca de local ao vivo, indexar sem copiar e copiar entre locais."""
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from ipe.core import locations as L
from ipe.core.config import Settings
from ipe.db.repository import Repository
from ipe.db.session import Database
from ipe.importer.scanner import Importer


def test_registro_de_locais(tmp_path):
    st = Settings(tmp_path / "s.json")
    paths = type("P", (), {"data": tmp_path / "padrao"})()
    (tmp_path / "padrao").mkdir()
    # só o banco deste computador no começo
    todos = L.all_locations(st, paths)
    assert len(todos) == 1 and todos[0].is_default and todos[0].id == L.DEFAULT_ID
    assert L.current(st, paths).is_default

    hd = tmp_path / "HD externo"
    loc = L.add(st, hd, "Pesquisa 2026")
    assert loc.name == "Pesquisa 2026" and loc.path == hd.resolve()
    assert (hd / L.MARKER).exists() and (hd / L.STORAGE_NAME).is_dir()   # pasta preparada
    assert loc.database == hd.resolve() / L.DB_NAME
    assert L.looks_used(hd) and L.suggest_name(hd) == "Pesquisa 2026"

    # a lista fica nas configurações do usuário, não dentro do local
    assert [d["path"] for d in st.get("locations")] == [str(hd.resolve())]
    assert len(L.all_locations(st, paths)) == 2

    # acrescentar a mesma pasta de novo não duplica
    assert L.add(st, hd).id == loc.id
    assert len(L.all_locations(st, paths)) == 2

    # trocar o local ativo
    L.set_current(st, loc.id)
    assert L.current(st, paths).id == loc.id
    # renomear muda a lista e a marca da pasta
    L.rename(st, loc.id, "Mama")
    assert L.find(st, paths, loc.id).name == "Mama" and L.read_marker(hd)["name"] == "Mama"
    # tirar da lista não apaga nada e volta para o banco deste computador
    L.remove(st, loc.id)
    assert (hd / L.MARKER).exists() and len(L.all_locations(st, paths)) == 1
    assert L.current(st, paths).is_default


def test_local_fora_do_ar_volta_para_o_padrao(tmp_path):
    st = Settings(tmp_path / "s.json")
    paths = type("P", (), {"data": tmp_path / "padrao"})()
    (tmp_path / "padrao").mkdir()
    hd = tmp_path / "pendrive"
    loc = L.add(st, hd, "Pendrive")
    L.set_current(st, loc.id)
    assert L.current(st, paths).id == loc.id and loc.online() and loc.ready()
    # "desconecta" o disco
    import shutil
    shutil.rmtree(hd)
    assert not L.find(st, paths, loc.id).online()
    assert L.current(st, paths).is_default        # não trava: cai no banco deste computador
    assert len(L.all_locations(st, paths)) == 2   # mas continua na lista, para quando voltar


def test_tipo_do_local(tmp_path):
    assert L.guess_kind("//servidor/exames") == "network"
    assert L.guess_kind("\\\\servidor\\exames") == "network"
    assert L.guess_kind("/media/filipe/HD") == "external"
    assert L.guess_kind("/Volumes/Backup") == "external"
    assert L.guess_kind(str(tmp_path)) in ("folder", "external")
    assert L.default_location(type("P", (), {"data": tmp_path})()).kind_label() == "Este computador"


def test_banco_do_local_e_portatil(tmp_path, sample_dir):
    """O índice e as listas ficam dentro da pasta: leva o HD e abre com tudo."""
    st = Settings(tmp_path / "s.json")
    hd = tmp_path / "externo"
    loc = L.add(st, hd, "Externo")
    db = Database(loc.database)
    repo = Repository(db)
    # indexa sem copiar: os arquivos ficam onde estão
    res = Importer(db, loc.storage, copy_to_storage=False).import_paths([sample_dir])
    assert res.added > 0
    lid = repo.create_case_list("Casos do HD")
    db.close()
    assert loc.database.exists()
    assert not any(loc.storage.rglob("*.dcm"))          # nada foi copiado
    assert list(Path(sample_dir).rglob("*.dcm"))        # originais intactos

    # "outro computador": só a pasta, sem as configurações
    st2 = Settings(tmp_path / "outro.json")
    loc2 = L.add(st2, hd)
    assert loc2.name == "Externo"                        # o nome veio da marca na pasta
    repo2 = Repository(Database(loc2.database))
    assert repo2.search_studies("", "", "", "", limit=50)
    assert any(n["name"] == "Casos do HD" for n in repo2.case_list_tree())
    assert lid


def test_troca_de_local_na_janela(env, sample_dir, tmp_path):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    QApplication.instance() or QApplication([])
    st = Settings(paths.settings_file)
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, st)
    try:
        assert w.location.is_default
        n_padrao = len(w.repo.search_studies("", "", "", "", limit=50))
        assert n_padrao > 0
        # local novo, vazio
        loc = L.add(st, tmp_path / "hd", "HD externo")
        assert w.switch_location(loc.id)
        assert w.location.id == loc.id and w.storage == loc.storage
        assert w.db is not db and w.repo is not repo
        assert w.net.repo is w.repo and w.pacs.repo is w.repo    # rede e PACS acompanham
        assert w.auto.repo is w.repo
        assert w.browser.repo is w.repo
        assert loc.name in w.windowTitle()
        assert w.repo.search_studies("", "", "", "", limit=50) == []   # banco novo, vazio
        # copiar um exame para o local
        uids = [r.study_uid for r in repo.search_studies("", "", "", "", limit=50)][:1]
        w.switch_location(L.DEFAULT_ID)
        assert w.location.is_default
        assert len(w.repo.search_studies("", "", "", "", limit=50)) == n_padrao
        assert [i for i, _n in w.browser.other_locations] == [loc.id]
        assert uids
    finally:
        w.close()


def test_copiar_exames_para_outro_local(env, sample_dir, tmp_path, monkeypatch):
    """Copiar para o local leva as imagens para dentro da pasta, sem tocar nos originais."""
    from PySide6.QtWidgets import QMessageBox
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    QApplication.instance() or QApplication([])
    st = Settings(paths.settings_file)
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, st)
    try:
        loc = L.add(st, tmp_path / "hd2", "HD 2")
        w._refresh_other_locations()
        assert (loc.id, "HD 2") in w.browser.other_locations
        uid = repo.search_studies("", "", "", "", limit=50)[0].study_uid
        originais = sorted(Path(f) for f in w.repo.files_for_study(uid))
        antes = [(f, f.stat().st_mtime_ns) for f in originais]
        monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
        w.copy_studies_to_location([uid], loc.id)
        # chegou no destino
        destino = Repository(Database(loc.database))
        achados = destino.search_studies("", "", "", "", limit=50)
        assert [r.study_uid for r in achados] == [uid]
        assert len(list(loc.storage.rglob("*.dcm"))) == len(originais)
        # os originais não foram tocados
        assert [(f, f.stat().st_mtime_ns) for f in originais] == antes
        # o local ativo não mudou
        assert w.location.is_default
    finally:
        w.close()


def test_mudar_a_pasta_do_banco_padrao(env, sample_dir, tmp_path, monkeypatch):
    """A pasta do banco deste computador pode ser trocada, levando os arquivos junto."""
    from PySide6.QtWidgets import QMessageBox
    from ipe.core import config as C
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    QApplication.instance() or QApplication([])
    st = Settings(paths.settings_file)
    from ipe.ui.main_window import MainWindow
    from ipe.ui import locations_panel as LP
    w = MainWindow(paths, st)
    try:
        antes = len(w.repo.search_studies("", "", "", "", limit=50))
        antiga = Path(paths.data)
        nova = tmp_path / "banco novo"
        monkeypatch.setattr(LP, "choose_folder", lambda *a, **k: nova)
        # escolhe "Mover os arquivos" (o primeiro botão de aceitar)
        monkeypatch.setattr(QMessageBox, "exec", lambda self: self.setProperty("_x", 1))
        monkeypatch.setattr(QMessageBox, "clickedButton",
                            lambda self: (self.buttons() or [None])[0])
        monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: None))
        w.move_default_database()
        # o banco e os arquivos foram para a pasta nova
        assert Path(w.paths.data) == nova and (nova / "dicomviewer.sqlite").exists()
        assert (nova / "Storage").is_dir() and not (antiga / "dicomviewer.sqlite").exists()
        assert w.storage == nova / "Storage" and w.location.path == nova
        assert len(w.repo.search_studies("", "", "", "", limit=50)) == antes   # os exames vieram junto
        assert w.net.repo is w.repo and w.browser.repo is w.repo
        # a escolha fica gravada e o programa a encontra ao abrir de novo
        assert st.get("data_dir") == str(nova)
        assert C.chosen_data_dir(paths.config) == nova
    finally:
        w.close()
