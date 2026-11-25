"""0.100.117: conferir e reconstruir o banco (parcial e completa), sem perder o que só existe no Ipê."""
import shutil
import threading

import pydicom
import pytest
from pydicom.uid import generate_uid

from ipe.db import reconstruir as R


def _importar(env, sample_dir, copiar=True, pasta=None):
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    origem = sample_dir
    if pasta is not None:
        shutil.copytree(sample_dir, pasta)
        origem = pasta
    Importer(db, paths.storage, copy_to_storage=copiar).import_paths([origem])
    return repo.search_studies(limit=50, banco="todos")


def test_conferir_e_parcial(env, sample_dir, tmp_path):
    paths, db, repo = env
    estudos = _importar(env, sample_dir)
    assert estudos
    rel = R.conferir(db, paths.storage)
    assert rel.problemas == len(rel.sem_miniatura)                # banco recém-importado: nada errado
    # 1) uma imagem do Storage some; 2) um arquivo aparece no Storage sem estar no banco; 3) uma pasta vazia
    uid = estudos[0].study_uid
    from pathlib import Path
    arquivos = sorted(Path(f) for f in repo.files_for_study(uid) if f)
    some = arquivos[0]
    some.unlink()
    ds = pydicom.dcmread(arquivos[1])
    ds.SOPInstanceUID = generate_uid()
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    novo = paths.storage / "solto" / "x.dcm"
    novo.parent.mkdir(parents=True)
    ds.save_as(novo)
    (paths.storage / "vazia" / "funda").mkdir(parents=True)
    antes = repo.counts()
    rel = R.conferir(db, paths.storage)
    assert len(rel.faltando_storage) == 1 and not rel.faltando_ref
    assert [p for p in rel.arquivos_fora] == [str(novo)]
    assert any(p.endswith("funda") for p in rel.pastas_vazias)
    assert "Arquivos no Storage fora do banco:" in rel.texto()
    assert repo.counts() == antes                                  # conferir não muda nada
    feito = R.parcial(repo, db, paths.storage, rel)
    assert feito["indexadas"] == 1 and feito["removidas"] == 1
    assert repo.counts()["instances"] == antes["instances"]        # -1 que sumiu, +1 que estava solto
    assert not (paths.storage / "vazia").exists()
    rel = R.conferir(db, paths.storage)
    assert not rel.faltando_storage and not rel.arquivos_fora


def test_referenciado_que_sumiu_so_sai_se_pedir_e_os_dados_do_medico_ficam(env, sample_dir, tmp_path):
    paths, db, repo = env
    estudos = _importar(env, sample_dir, copiar=False, pasta=tmp_path / "disco_externo")
    uid = estudos[0].study_uid
    repo.add_comment("study", uid, "caso de ensino")
    shutil.move(str(tmp_path / "disco_externo"), str(tmp_path / "desligado"))      # o disco foi desligado
    rel = R.conferir(db, paths.storage)
    assert rel.faltando_ref and not rel.faltando_storage
    R.parcial(repo, db, paths.storage, rel)                                  # padrão: mantém
    assert repo.study_info(uid) is not None
    R.parcial(repo, db, paths.storage, rel, remover_referenciados=True)
    assert repo.study_info(uid) is None and repo.counts()["patients"] == 0
    assert [c.text for c in repo.comments(uid)] == ["caso de ensino"]        # o comentário fica (volta com o exame)


def test_completa_rele_os_arquivos_guarda_copia_e_retoma(env, sample_dir, tmp_path):
    from ipe.core.config import Settings
    from ipe.db.models import Patient, Series, Study
    paths, db, repo = env
    estudos = _importar(env, sample_dir)
    st_ = Settings(paths.settings_file)
    with db.session() as s:                                        # o índice estragado
        for st in s.query(Study):
            st.description = "ERRADO"
        for se in s.query(Series):
            se.description = "ERRADO"
        p = s.query(Patient).first()
        nome_certo = p.name
        p.name = "NOME^ERRADO"
    # para no meio e retoma
    parar = threading.Event()
    vistos = []

    def progresso(feito, total, msg):
        if msg.startswith("relendo"):
            vistos.append(feito)
            parar.set()
    with pytest.raises(R.Cancelado):
        R.completa(repo, db, paths.storage, tmp_path / "copias", progresso, parar, settings=st_)
    assert R.em_andamento(st_)
    copia = R.em_andamento(st_)["copia"]
    r = R.completa(repo, db, paths.storage, tmp_path / "copias", settings=st_)
    assert r["retomou"] and r["copia"] == copia and not R.em_andamento(st_)
    with db.session() as s:
        assert "ERRADO" not in {x.description for x in s.query(Study)}
        assert "ERRADO" not in {x.description for x in s.query(Series)}
        assert nome_certo in {x.name for x in s.query(Patient)}
        assert "NOME^ERRADO" not in {x.name for x in s.query(Patient)}
    # a cópia do índice volta o banco a como estava antes (com o "ERRADO")
    contagem = R.restaurar_indice(db, copia)
    assert contagem["study"] == len(estudos)
    with db.session() as s:
        assert {x.description for x in s.query(Study)} == {"ERRADO"}
    assert repo.counts()["instances"] > 0


def test_janela_confere_e_faz_a_parcial(env, sample_dir, monkeypatch):
    import time

    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.ui.reconstruir_dialogo import ReconstruirDialog
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    _importar(env, sample_dir)
    (paths.storage / "vazia").mkdir()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    d = ReconstruirDialog(repo, db, paths, Settings(paths.settings_file))
    from PySide6.QtCore import Qt
    assert d.windowType() == Qt.Window                                    # minimiza (Ubuntu)

    def esperar():
        fim = time.time() + 60
        while (d.ocupado() or d.linha is not None) and time.time() < fim:
            app.processEvents()
            time.sleep(0.02)
        app.processEvents()
    d.conferir()
    esperar()
    assert d.rel is not None and d.rel.pastas_vazias and d.b_parcial.isEnabled()
    assert d.tabela.rowCount() == len(d.rel.linhas())
    d.parcial()
    esperar()
    assert "Reconstrução parcial" in d.estado.text() and not (paths.storage / "vazia").exists()
    d.completa(False)
    esperar()
    assert "Reconstrução completa" in d.estado.text(), d.estado.text()
    assert list((paths.data / "Backups").glob("indice-*.json.gz"))


def test_linha_de_comando(env, sample_dir, tmp_path, capsys):
    import ipe.__main__ as M
    paths, db, repo = env
    _importar(env, sample_dir)
    (paths.storage / "vazia").mkdir()
    rel = tmp_path / "rel.txt"
    assert M.main(["banco", "conferir", "--relatorio", str(rel)]) == 0
    assert "Pastas vazias no Storage" in capsys.readouterr().out and rel.exists()
    assert M.main(["banco", "parcial"]) == 0
    assert not (paths.storage / "vazia").exists()
    assert M.main(["banco", "completa"]) == 0
    copia = sorted((paths.data / "Backups").glob("indice-*.json.gz"))[-1]
    assert M.main(["banco", "restaurar-indice", str(copia)]) == 0
    assert repo.counts()["studies"] > 0
