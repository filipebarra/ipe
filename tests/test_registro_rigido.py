"""0.99.38: registro rígido (rotação + translação) entre exames, a matriz guardada, a validação por pares
de pontos e o exame gravado no plano do outro."""
import numpy as np
import pydicom
import pytest
from pydicom.dataset import FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from ipe.imaging import registro_rigido as RR
from ipe.imaging.volume import Volume


def _cabeca(n=64, sp=3.0, valor_borda=150.0):
    z, y, x = np.mgrid[0:n, 0:n, 0:n].astype(float)
    c = n / 2
    r = ((x - c) / 25) ** 2 + ((y - c) / 29) ** 2 + ((z - c) / 22) ** 2
    v = np.zeros((n, n, n), np.float32)
    v[r < 1] = 100
    v[((x - c + 8) / 5) ** 2 + ((y - c - 4) / 9) ** 2 + ((z - c) / 7) ** 2 < 1] = 300
    v[((x - c - 12) / 4) ** 2 + ((y - c + 13) / 4) ** 2 + ((z - c + 6) / 4) ** 2 < 1] = 500
    v[(r > 0.85) & (r < 1)] += valor_borda
    return Volume(v, np.array([-n * sp / 2] * 3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
                  np.array([0, 0, sp]), sp, sp, None, "")


def _movido(A, M, transformar=None):
    nz, ny, nx = A.shape
    K, J, I = np.mgrid[0:nz, 0:ny, 0:nx]
    pts = A.origin + np.stack([I.ravel(), J.ravel(), K.ravel()], 1) @ A.matrix().T
    d = np.nan_to_num(RR.amostrar(A, RR.aplicar(np.linalg.inv(M), pts), fora=0)).reshape(A.shape)
    if transformar is not None:
        d = transformar(d)
    return Volume(d.astype(np.float32), A.origin.copy(), A.row_dir, A.col_dir, A.slice_vec, A.dx, A.dy, None, "")


def test_geometria_ida_e_volta():
    M = RR.matriz((10, -5, 20, 3, 4, 5), (1, 2, 3))
    assert np.allclose(RR.angulos(M), (10, -5, 20))
    p = np.array([[10.0, -20.0, 30.0]])
    assert np.allclose(RR.aplicar(np.linalg.inv(M), RR.aplicar(M, p)), p)
    assert np.allclose(RR.aplicar(M, [[1, 2, 3]])[0], [4, 6, 8])          # o centro só translada


def test_recupera_rotacao_e_translacao_conhecidas():
    A = _cabeca()
    verdade = (6.0, -4.0, 8.0, 5.0, -7.0, 3.0)
    M = RR.matriz(verdade, RR._cantos(A).mean(0))
    r = RR.registrar(A, _movido(A, M), "ncc", tempo_max=60)
    assert np.allclose(r.params[:3], verdade[:3], atol=0.6)
    assert np.allclose(r.params[3:], verdade[3:], atol=1.5)
    assert r.valor > r.valor_inicial and r.qualidade() in ("boa", "razoável")
    pts = [(10, 20, 5), (-30, 10, 0), (0, -40, 15)]
    e = RR.erro_dos_pontos(r.M, [(p, RR.aplicar(M, p)[0]) for p in pts])
    assert e["n"] == 3 and e["maximo"] < 2.0
    assert 8 < r.rotacao_total < 13          # 6°, −4° e 8° juntos dão ≈ 10,8°


def test_informacao_mutua_com_contraste_invertido():
    """Outra "sequência": as intensidades trocam de ordem (líquido escuro vira claro) — a correlação
    falha, a informação mútua acerta."""
    A = _cabeca()
    verdade = (0.0, 0.0, 7.0, 4.0, 0.0, -3.0)
    M = RR.matriz(verdade, RR._cantos(A).mean(0))
    trocar = {0: 0, 100: 400, 250: 100, 300: 50, 500: 200}

    def t2(d):
        out = np.zeros_like(d)
        for de, para in trocar.items():
            out[np.abs(d - de) < 25] = para
        return out
    B = _movido(A, M, t2)
    r = RR.registrar(A, B, "mi", tempo_max=60)
    assert abs(r.params[2] - 7.0) < 1.0 and abs(r.params[3] - 4.0) < 2.0
    assert RR.metrica_para("MR", "MR", "Ax T1", "Ax T2 FSE") == "mi"
    assert RR.metrica_para("MR", "MR", "A 3D FSPGR", "A 3D FSPGR POS") == "ncc"
    assert RR.metrica_para("CT", "MR") == "mi"


def test_reformatar_poe_b_na_grade_de_a():
    A = _cabeca()
    M = RR.matriz((0, 0, 10, 6, 0, 0), RR._cantos(A).mean(0))
    B = _movido(A, M)
    volta = RR.reformatar(B, A, M)
    dentro = A.data > 0
    assert np.corrcoef(volta[dentro], A.data[dentro])[0, 1] > 0.95


def test_matriz_guardada_nos_dois_sentidos(env):
    _paths, _db, repo = env
    M = RR.matriz((3, 0, 5, 1, 2, 3), (0, 0, 0))
    repo.save_registration("2.2", "1.1", [1, 2, 3], 0.0, method="rigido", matriz=M)   # guardado invertido
    assert np.allclose(repo.get_registration_matriz("2.2", "1.1"), M)
    assert np.allclose(repo.get_registration_matriz("1.1", "2.2"), np.linalg.inv(M))
    # ajuste à mão (Alt+rodinha) grava sem matriz: vale o último
    repo.save_registration("2.2", "1.1", [1, 2, 4], 0.0)
    assert repo.get_registration_matriz("2.2", "1.1") is None
    assert repo.get_registration("2.2", "1.1")[0] == [1, 2, 4]


def _serie(pasta, vol, estudo, frame_ref, desc, data="20260101"):
    pasta.mkdir(parents=True, exist_ok=True)
    serie = generate_uid()
    for k in range(vol.shape[0]):
        ds = pydicom.Dataset()
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.4"
        meta.MediaStorageSOPInstanceUID = generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.file_meta = meta
        ds.SOPClassUID, ds.SOPInstanceUID = meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID
        ds.PatientName, ds.PatientID = "REGISTRO^Teste", "REG1"
        ds.StudyInstanceUID, ds.SeriesInstanceUID, ds.FrameOfReferenceUID = estudo, serie, frame_ref
        ds.StudyDate, ds.Modality, ds.SeriesDescription, ds.SeriesNumber = data, "MR", desc, 3
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = list(vol.voxel_to_patient(0, 0, k))
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing, ds.SliceThickness = [vol.dy, vol.dx], vol.dz
        px = np.clip(np.round(vol.data[k]), 0, 32767).astype(np.uint16)
        ds.Rows, ds.Columns = px.shape
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 0
        ds.PixelData = px.tobytes()
        ds.save_as(pasta / f"{k:03d}.dcm", enforce_file_format=True)
    return serie


def test_grava_o_registrado_com_a_geometria_do_outro(env, tmp_path):
    from ipe.imaging import registro_saida as SAIDA
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    A = _cabeca(48, 4.0)
    M = RR.matriz((0, 0, 8, 5, 0, 0), RR._cantos(A).mean(0))
    B = _movido(A, M)
    ea, eb, fa, fb = generate_uid(), generate_uid(), generate_uid(), generate_uid()
    sa = _serie(tmp_path / "a", A, ea, fa, "A T1", "20260731")
    sb = _serie(tmp_path / "b", B, eb, fb, "A T1", "20220124")
    Importer(db, paths.storage).import_paths([tmp_path / "a", tmp_path / "b"])
    ia = repo.instances_for_series(sa)[0]["path"]
    ib = repo.instances_for_series(sb)[0]["path"]
    r = RR.registrar(A, B, "ncc", tempo_max=60)
    dados = RR.reformatar(B, A, r.M)
    uid, sops = SAIDA.gravar(db, paths.storage, A, dados, ib, ia, "A T1 · registrada em 31/07/2026", r.M)
    assert len(sops) == A.shape[0]
    meta = repo.series_meta(uid)
    assert meta["study_uid"] == eb                                   # fica no exame de B
    ds = pydicom.dcmread(sorted(repo.instances_for_series(uid), key=lambda i: i["instance_number"])[5]["path"])
    assert ds.FrameOfReferenceUID == fa and "REGISTERED" in ds.ImageType      # com a geometria de A
    assert np.allclose([float(x) for x in ds.ImagePositionPatient], A.voxel_to_patient(0, 0, 5), atol=1e-3)
    dentro = A.data[5] > 0
    assert np.corrcoef(ds.pixel_array[dentro].astype(float), A.data[5][dentro])[0, 1] > 0.9


def test_botao_alinhar_grava_e_abre_o_registrado(env, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    A = _cabeca(48, 4.0)
    M = RR.matriz((0, 0, 8, 5, 0, 0), RR._cantos(A).mean(0))
    ea, eb, fa = generate_uid(), generate_uid(), generate_uid()
    _serie(tmp_path / "a", A, ea, fa, "A T1", "20260731")
    _serie(tmp_path / "b", _movido(A, M), eb, generate_uid(), "A T1", "20220124")
    Importer(db, paths.storage).import_paths([tmp_path / "a", tmp_path / "b"])
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        w.open_study(ea)
        QApplication.processEvents()
        tab = next(iter(w.all_viewer_tabs()))
        tab.add_study(eb)
        QApplication.processEvents()
        va = next(v for v in tab.viewports if v.study_uid == ea)
        vb = next(v for v in tab.viewports if v.study_uid == eb)
        tab._activate(va)
        perguntas = []
        monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: (perguntas.append(a[2]),
                                                                                  QMessageBox.Yes)[1]))
        assert tab.auto_register()
        assert perguntas and "girado" in perguntas[0]                     # 8°: oferece gravar no plano
        Mg = repo.get_registration_matriz(ea, eb)
        assert Mg is not None and abs(RR.angulos(np.asarray(Mg))[2] - 8) < 1.0
        reg = next(s for s in repo.series_for_study(eb) if "registrada" in (s.description or ""))
        assert vb.series_uid == reg.series_uid                            # aberta no quadro do outro exame
        ds = pydicom.dcmread(repo.instances_for_series(reg.series_uid)[0]["path"], stop_before_pixels=True)
        assert ds.FrameOfReferenceUID == fa
        assert tab.hub.group_of(va) is not None and tab.hub.group_of(va) == tab.hub.group_of(vb)
    finally:
        w._really_quit = True
        w.settings.set("ui.confirmar_sair", False)
        w.close()
