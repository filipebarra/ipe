import shutil
import zipfile

import numpy as np

from ipe.imaging.series import build_frames, read_frame
from ipe.imaging.windowing import apply_window, orientation_labels
from ipe.importer.scanner import Importer
from ipe.importer.thumbnails import generate_thumbnails


def test_import_dedupe_and_counts(env, sample_dir):
    paths, db, repo = env
    r = Importer(db, paths.storage).import_paths([sample_dir])
    assert r.added == 180 and r.errors == 0
    assert len(r.new_studies) == 8
    r2 = Importer(db, paths.storage).import_paths([sample_dir])
    assert r2.added == 0 and r2.duplicates == 180
    c = repo.counts()
    assert c == {"patients": 3, "studies": 8, "series": 16, "instances": 180}


def test_reference_mode_does_not_copy(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage, copy_to_storage=False).import_paths([sample_dir / "MG"])
    assert not any(paths.storage.rglob("*.dcm"))
    uid = repo.search_studies()[0].study_uid
    repo.delete_study(uid, paths.storage)
    assert any((sample_dir / "MG").glob("*.dcm")), "arquivo original nunca pode ser apagado"


def test_zip_import(env, sample_dir, tmp_path):
    paths, db, repo = env
    z = tmp_path / "exame.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in (sample_dir / "US").glob("*.dcm"):
            zf.write(f, f"pasta/{f.name}")
    r = Importer(db, paths.storage, copy_to_storage=False).import_paths([z])
    assert r.added == 1
    # ZIP é sempre copiado (a pasta temporária é apagada)
    assert any(paths.storage.rglob("*.dcm"))


def test_non_dicom_ignored(env, tmp_path):
    paths, db, _ = env
    junk = tmp_path / "junk"
    junk.mkdir()
    (junk / "lixo.bin").write_bytes(b"nao sou dicom" * 20)
    r = Importer(db, paths.storage).import_paths([junk])
    assert r.added == 0 and r.not_dicom == 1


def test_geometric_sort_ignores_instance_number(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    uid = repo.find_study_uids(accession="ACC1001")[0]
    series = repo.series_for_study(uid)[0]
    frames = build_frames(repo.instances_for_series(series.series_uid))
    z = [f.position[2] for f in frames]
    assert z == sorted(z) and len(z) == 60
    # InstanceNumber foi gravado invertido no fantoma
    assert frames[0].instance_number == 60


def test_pixels_rescaled_to_hu(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    uid = repo.find_study_uids(accession="ACC1001")[0]
    frames = build_frames(repo.instances_for_series(repo.series_for_study(uid)[0].series_uid))
    img = read_frame(frames[30])
    assert img.window == (1500.0, -600.0)
    assert img.pixel_spacing == (1.5, 1.5)
    assert img.pixels.min() < -900          # ar em HU
    assert 0 < float(np.median(img.pixels[100:156, 128])) < 100   # partes moles


def test_color_and_multiframe(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    uid = repo.find_study_uids(accession="ACC4001")[0]
    series = {s.description: s for s in repo.series_for_study(uid)}
    rgb = read_frame(build_frames(repo.instances_for_series(series["Doppler"].series_uid))[0])
    assert rgb.is_color and rgb.pixels.shape == (300, 400, 3)
    cine = build_frames(repo.instances_for_series(series["Cine multiframe"].series_uid))
    assert len(cine) == 10
    assert not np.array_equal(read_frame(cine[0]).pixels, read_frame(cine[5]).pixels)


def test_thumbnails(env, sample_dir):
    paths, db, repo = env
    r = Importer(db, paths.storage).import_paths([sample_dir])
    assert generate_thumbnails(repo, r.new_series) == 16
    assert all(s.thumbnail.startswith(b"\x89PNG") for s in repo.series_for_study(
        repo.find_study_uids(accession="ACC3001")[0]))


def test_window_and_orientation():
    px = np.array([[-1000, 40, 1000]], dtype=np.float32)
    out = apply_window(px, 400, 40)
    assert out.tolist() == [[0, 127, 255]]
    assert apply_window(px, 400, 40, invert=True).tolist() == [[255, 128, 0]]
    lab = orientation_labels(np.array([1, 0, 0, 0, 1, 0], dtype=float))
    assert lab == {"right": "L", "left": "R", "bottom": "P", "top": "A"}


def test_search_and_case_lists(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    assert len(repo.search_studies("FANTOMA")) == 1
    assert len(repo.search_studies("ACC1001|ACC3001")) == 2
    assert len(repo.search_studies(modality="CT")) == 2
    lid = repo.create_case_list("Reunião de mama", "meeting")
    uid = repo.find_study_uids(accession="ACC3001")[0]
    assert repo.add_to_case_list(lid, uid, "Caso 1 — calcificações")
    assert not repo.add_to_case_list(lid, uid)
    assert repo.study_uids_in_list(lid) == [uid]
    # estudo em lista fica protegido
    import pytest
    with pytest.raises(PermissionError):
        repo.delete_study(uid, paths.storage)
    repo.set_locked(uid, False)
    assert repo.delete_study(uid, paths.storage) == 4


def test_comments(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir / "US"])
    uid = repo.search_studies()[0].study_uid
    repo.add_comment("study", uid, "Caso bom para aula")
    assert repo.comments(uid)[0].text == "Caso bom para aula"
    assert repo.search_studies()[0].has_comment


def test_operators_column_and_backfill(env, sample_dir):
    """(0008,1070) Operators' Name, estação e aparelho: gravados na importação e completados
    em bancos antigos (colunas criadas sozinhas)."""
    from ipe.db.repository import Repository
    from ipe.db.session import Database
    from ipe.importer.backfill import backfill_series_details
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    rows = {r.accession: r for r in repo.search_studies()}
    assert rows["ACC2001"].operators == "Técnica, Maria; Técnico, João"
    assert rows["ACC1001"].operators == "Técnica, Maria" and rows["ACC1001"].station == "CT01"
    assert rows["ACC1001"].device == "Fantoma Modelo CT"
    # banco "antigo": sem as colunas novas (pela conexão do próprio banco: vale no SQLite e no PostgreSQL, 0.100.34)
    from sqlalchemy import text
    with db.engine.begin() as con:
        for col in ("operators", "station", "device"):
            con.execute(text(f"ALTER TABLE series DROP COLUMN {col}"))
    db.engine.dispose()
    db2 = Database(paths.database)               # recria as colunas (vazias)
    repo2 = Repository(db2)
    assert {r.accession: r for r in repo2.search_studies()}["ACC1001"].operators == ""
    assert backfill_series_details(repo2) == 16
    assert {r.accession: r for r in repo2.search_studies()}["ACC1001"].operators == "Técnica, Maria"
    assert backfill_series_details(repo2) == 0   # não relê
