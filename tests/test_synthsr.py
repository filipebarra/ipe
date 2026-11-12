"""0.100.23: T1 sintético de 1 mm (SynthSR) — a série nova no lugar certo do paciente.

O exame de teste é como o do protocolo de Parkinson: um sagital 2D de 5 mm (22 cortes). Uma esfera clara
num ponto conhecido do paciente tem de cair no mesmo ponto na série de 1 mm. O trabalhador roda simulado
(sem PyTorch); a rede de verdade tem teste próprio, que só roda onde houver PyTorch e os pesos.
"""
import numpy as np
import pydicom
import pytest

from ipe.ai import synthsr as SR

ALVO = np.array([22.0, -30.0, 15.0])          # LPS, mm
XS = np.arange(-52.5, 55, 5.0)                 # 22 cortes sagitais de 5 mm (x cresce para a esquerda)
YS = np.arange(-100, 101, 1.0)                 # colunas: de anterior para posterior
ZS = np.arange(90, -91, -1.0)                  # linhas: de cima para baixo


def _volume():
    xx, zz, yy = np.meshgrid(XS, ZS, YS, indexing="ij")          # (corte, linha, coluna)
    cab = (xx / 70) ** 2 + (yy / 90) ** 2 + (zz / 80) ** 2 <= 1
    v = np.where(cab, 300, 0).astype(np.int16)
    v[(xx - ALVO[0]) ** 2 + (yy - ALVO[1]) ** 2 + (zz - ALVO[2]) ** 2 <= 8 ** 2] = 1200
    return v


def _exame(env, tmp_path, descricao_serie="S T1 FLAIR", fino=False):
    from pydicom.uid import generate_uid

    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    v = _volume()
    pat = {"name": "EXEMPLO^Sintetico", "id": "SR1", "birth": "19500101", "sex": "M"}
    study = {"uid": generate_uid(), "date": "20261112", "accession": "SR01", "description": "RM CRANIO",
             "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 4, "description": descricao_serie}
    pasta = tmp_path / "sr"
    for k in range(v.shape[0]):
        ds = _base("1.2.840.10008.5.1.4.1.1.4", pat, study, series, "MR")
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [float(XS[k]), float(YS[0]), float(ZS[0])]
        ds.ImageOrientationPatient = [0, 1, 0, 0, 0, -1]
        ds.PixelSpacing = [1.0, 1.0]
        ds.SliceThickness = 1.0 if fino else 5.0
        _mono(ds, v[k], signed=True)
        _save(ds, pasta)
    Importer(db, paths.storage).import_paths([pasta])
    return study["uid"], series["uid"], study["for"]


def _centro_claro(repo, serie_uid):
    """Centro (LPS) dos pixels mais claros da série, pelos cabeçalhos DICOM."""
    pts = []
    for inst in repo.instances_for_series(serie_uid):
        ds = pydicom.dcmread(inst["path"])
        img = ds.pixel_array.astype(float)
        rr, cc = np.nonzero(img > 0.8 * 128 * SR.ESCALA)
        if not rr.size:
            continue
        ipp = np.array(ds.ImagePositionPatient, float)
        iop = np.array(ds.ImageOrientationPatient, float)
        dr, dc = (float(x) for x in ds.PixelSpacing)
        pts.append(ipp[None] + cc[:, None] * dc * iop[None, :3] + rr[:, None] * dr * iop[None, 3:])
    return np.concatenate(pts).mean(0)


def test_geometria_axial_de_um_volume_ras():
    afim = np.array([[1.0, 0, 0, -50], [0, 1.0, 0, -60], [0, 0, 1.0, -40], [0, 0, 0, 1]])
    g = SR.geometria(afim, (100, 120, 80))
    assert g["linha"] == pytest.approx([1, 0, 0]) and g["coluna"] == pytest.approx([0, 1, 0])   # LPS: esq., post.
    assert g["passo"] == pytest.approx([0, 0, 1])
    # o canto do pixel (0, 0) é o voxel mais à direita e mais anterior: RAS (+49, +59) = LPS (−49, −59)
    assert g["canto"] == pytest.approx([-49, -59, -40])
    assert np.cross(g["linha"], g["coluna"]) == pytest.approx(g["passo"])


def test_do_sagital_de_5_mm_a_serie_de_1_mm(env, tmp_path):
    from PySide6.QtWidgets import QApplication

    from ipe.ai import ferramentas as FE
    from ipe.ai import totalseg as TS
    from ipe.imaging.series import FrameCache
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie, frame = _exame(env, tmp_path)
    assert FE.modulo("synthsr") is SR
    assert SR.escolher_serie(repo, uid)[0] == serie and not SR.tem_serie_fina(repo, uid)
    t = TS.Trabalho(repo, FrameCache(256), None, uid, serie, simular=True)
    FE.preparar_trabalho(t, SR)
    t.preparar()
    try:
        t.rodar_aqui()
        res, versao = FE.rodar_conta(t, SR, None)
        assert res.imagem is not None and res.n_origem == 22 and res.espessura == pytest.approx(5.0)
        assert SR.AVISO in res.avisos
        saida = FE.gravar(t, SR, res, versao, db, paths.storage, repo, None)
        saida = FE.gravar(t, SR, res, versao, db, paths.storage, repo, None)      # refazer troca, não duplica
    finally:
        t.limpar()
    novas = [s for s in repo.series_for_study(uid) if s.description == SR.DESC_SERIE]
    assert len(novas) == 1 and novas[0].series_uid == saida["nova_serie"] and novas[0].modality == "MR"
    inst = repo.instances_for_series(novas[0].series_uid)
    assert len(inst) >= 150                                                  # ~180 mm de cabeça em cortes de 1 mm
    ds = pydicom.dcmread(inst[0]["path"])
    assert [float(x) for x in ds.PixelSpacing] == pytest.approx([1.0, 1.0]) and float(ds.SliceThickness) == 1.0
    assert ds.FrameOfReferenceUID == frame                                   # sincroniza com a original
    assert "SINTETICA" in ds.DerivationDescription and "SYNTHETIC" in list(ds.ImageType)
    assert abs(np.array(ds.ImageOrientationPatient, float)[:3] @ [1, 0, 0]) > 0.99      # axial
    assert _centro_claro(repo, novas[0].series_uid) == pytest.approx(ALVO, abs=3.0)
    # fica só neste computador, tem o selo de IA e não é escolhida por nenhuma ferramenta
    assert novas[0].series_uid in TS.series_locais(repo, uid)
    from ipe.ai import neuro as N
    from ipe.ai import series_ia as SI
    assert SI.e_resultado("MR", SR.DESC_SERIE)
    assert N.escolher_serie(repo, uid)[0] == serie and SR.escolher_serie(repo, uid)[0] == serie
    assert SR.ja_feita(repo, uid)
    assert "série" in SR.mensagem(res, 1.0) and "lesão" in SR.mensagem(res, 1.0)


def test_exame_com_serie_fina_nao_roda_sozinho(env, tmp_path):
    paths, db, repo = env
    xs = np.arange(-80, 80, 1.0)
    from pydicom.uid import generate_uid

    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    pat = {"name": "EXEMPLO^Fino", "id": "SR2", "birth": "19500101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20261112", "accession": "SR02", "description": "RM CRANIO",
             "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 5, "description": "SAG 3D T1"}
    pasta = tmp_path / "fino"
    for k, x in enumerate(xs):
        ds = _base("1.2.840.10008.5.1.4.1.1.4", pat, study, series, "MR")
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [float(x), -20.0, 20.0]
        ds.ImageOrientationPatient = [0, 1, 0, 0, 0, -1]
        ds.PixelSpacing = [1.0, 1.0]
        ds.SliceThickness = 1.0
        _mono(ds, np.full((40, 40), 100, np.int16), signed=True)
        _save(ds, pasta)
    Importer(db, paths.storage).import_paths([pasta])
    assert SR.tem_serie_fina(repo, study["uid"])
    uid, motivo = SR.escolher_serie(repo, study["uid"])
    assert uid is None and "fina" in motivo


def test_reamostrar_a_1_mm_como_o_original():
    pytest.importorskip("scipy")
    from ipe.ai import totalseg_worker as W
    dados = np.zeros((10, 40, 30), np.float32)                 # eixo 0 de 5 mm
    dados[4:6, 10:30, 8:22] = 100
    afim = np.diag([5.0, 1.0, 1.0, 1.0])
    afim[:3, 3] = [-25, -20, -15]
    v, a = W._a_1mm_ras(dados, afim)
    assert v.shape == (50, 40, 30) and np.sqrt((a[:3, :3] ** 2).sum(0)) == pytest.approx([1, 1, 1])
    # o centro do bloco fica no mesmo ponto do mundo
    ii, jj, kk = np.nonzero(v > 50)
    centro = a[:3, :3] @ [ii.mean(), jj.mean(), kk.mean()] + a[:3, 3]
    ii, jj, kk = np.nonzero(dados > 50)
    esperado = afim[:3, :3] @ [ii.mean(), jj.mean(), kk.mean()] + afim[:3, 3]
    assert centro == pytest.approx(esperado, abs=0.6)
    # eixos trocados e invertidos voltam para perto de RAS
    afim2 = np.array([[0, 0, -1.0, 10], [-5.0, 0, 0, 20], [0, 1.0, 0, -5], [0, 0, 0, 1]])
    v2, a2 = W._a_1mm_ras(dados, afim2)
    assert np.argmax(np.abs(a2[:3, :3]), axis=0).tolist() == [0, 1, 2] and (np.diag(a2[:3, :3]) > 0).all()


def test_rede_em_pytorch_com_os_pesos_originais():
    """Só onde houver PyTorch e o .h5 (IPE_SYNTHSR_H5): a rede carrega todos os pesos e devolve a forma certa."""
    import os
    torch = pytest.importorskip("torch")
    pytest.importorskip("h5py")
    h5 = os.environ.get("IPE_SYNTHSR_H5", "")
    if not os.path.isfile(h5):
        pytest.skip("sem os pesos do SynthSR")
    from ipe.ai import totalseg_worker as W
    rede = W._rede_synthsr(h5)
    n = sum(p.numel() for p in rede.parameters())
    assert 13_000_000 < n < 13_600_000
    with torch.no_grad():
        y = rede(torch.zeros(1, 1, 32, 32, 32))
    assert tuple(y.shape) == (1, 1, 32, 32, 32)


def test_tela_cria_e_mostra_a_serie(env, tmp_path, monkeypatch):
    import time

    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie, _f = _exame(env, tmp_path)
    perguntas, avisos = [], []
    monkeypatch.setattr(QMessageBox, "question", lambda _p, _t, msg, *a, **k: perguntas.append(msg) or QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(msg))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, msg, *a, **k: avisos.append("ERRO " + msg))
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1300, 800)
    w.show()
    try:
        assert w.handle_external({"accession": "SR01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        vp = next(v for v in tab.viewports if v.frames)
        tab.set_active(vp) if hasattr(tab, "set_active") else None
        tab.t1_sintetico(vp, simular=True)
        fim = time.time() + 120
        while not perguntas and not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert perguntas and perguntas[-1].startswith("T1 sintético pronto"), (perguntas, avisos)
        assert "Mostrar a série nova" in perguntas[-1]
        app.processEvents()
        nova = next(s for s in repo.series_for_study(uid) if s.description == SR.DESC_SERIE)
        assert any(s.series_uid == nova.series_uid for s in tab.series)                 # entrou na tira
        assert any(getattr(v, "series_uid", "") == nova.series_uid for v in tab.viewports)   # e no quadro
        # sobre a própria série sintética, o programa pede a original
        alvo = next(v for v in tab.viewports if getattr(v, "series_uid", "") == nova.series_uid)
        tab.t1_sintetico(alvo, simular=True)
        assert avisos and "já é um T1 sintético" in avisos[-1]
    finally:
        w.close()
        app.processEvents()


def test_so_para_o_cranio(env, tmp_path):
    paths, db, repo = env
    uid, serie, _f = _exame(env, tmp_path)
    assert SR.escolher_serie(repo, uid)[0] == serie
    assert SR.exame_serve({"modalities": "MR", "description": "RM CRANIO"})
    assert not SR.exame_serve({"modalities": "MR", "description": "RM JOELHO D"})
    assert not SR.exame_serve({"modalities": "CT", "description": "TC CRANIO"})       # TC: só à mão
