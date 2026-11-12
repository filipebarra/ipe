"""0.100.25: lesões de substância branca no FLAIR (FLAMeS) — contagem, volume, regiões e comparação.

O fantoma é o do crânio dos índices (rótulos do SynthSeg, 1 mm), com quatro lesões de posição e tamanho
conhecidos: uma encostada no ventrículo lateral, uma encostada no córtex, uma no tronco e uma no meio da
substância branca. O trabalhador roda simulado (3000 + rótulo = lesão dentro daquela estrutura).
"""
import numpy as np
import pytest

from ipe.ai import flames as FL
from tests.test_neuro import X, Y, Z, fantoma

#: (centro x, y, z em mm, raio, região esperada)
LESOES = [((22.0, -20.0, 12.0), 3, "peri"),        # encosta no corno frontal esquerdo (x 3–18)
          ((58.0, 0.0, 0.0), 3, "justa"),          # encosta na casca (córtex) lateral
          ((0.0, 43.0, -37.0), 2, "prof"),         # ao lado do 4º ventrículo: nem ventrículo lateral nem córtex
          ((-40.0, -40.0, 20.0), 4, "prof")]


def _labels():
    _v, _r, lab = fantoma()
    lab = lab.copy()
    lab[lab == 24] = 3                                   # a casca do fantoma faz de córtex
    lab[(lab == 2) & (np.abs(Z)[:, None, None] > 200)] = 2
    return lab


def _com_lesoes(infra=False):
    lab = _labels()
    zz, yy, xx = np.meshgrid(Z, Y, X, indexing="ij")
    les = np.zeros(lab.shape, bool)
    lista = list(LESOES)
    if infra:
        tronco = (np.abs(xx) <= 8) & (np.abs(yy - 30) <= 8) & (zz <= -20) & (zz >= -45) & (lab > 0)
        lab[tronco & (lab != 15)] = 16
        lista.append(((0.0, 30.0, -30.0), 3, "infra"))
    for (cx, cy, cz), r, _reg in lista:
        les |= ((xx - cx) ** 2 + (yy - cy) ** 2 + (zz - cz) ** 2 <= r * r) & (lab > 0)
    return lab, les, lista


def test_e_flair_e_escolha():
    assert FL.e_flair("AX T2 FLAIR") and FL.e_flair("3D Sag T2 FLAIR Cube") and FL.e_flair("t2_tirm_tra_dark-fluid")
    assert not FL.e_flair("S T1 FLAIR") and not FL.e_flair("AX T2 FSE") and not FL.e_flair("FLAIR MIP")
    assert [t["nome"] for t in FL.tarefas()] == ["synthseg", "flames"]


def test_classificar_por_regiao():
    lab, les, lista = _com_lesoes(infra=True)
    ilhas, itens = FL.classificar(les, lab, (1.0, 1.0, 1.0))
    assert len(itens) == len(lista)
    zz, yy, xx = np.meshgrid(Z, Y, X, indexing="ij")
    for (cx, cy, cz), _r, esperado in lista:
        k = int(ilhas[int(np.argmin(np.abs(Z - cz))), int(np.argmin(np.abs(Y - cy))), int(np.argmin(np.abs(X - cx)))])
        assert k > 0
        assert next(reg for q, _v, reg in itens if q == k) == esperado, (cx, cy, cz)


def _exame(env, tmp_path, les=True, data="20261112", acesso="FL01", pasta="fl"):
    from pydicom.uid import generate_uid

    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    lab, mask, lista = _com_lesoes(infra=True)
    if not les:
        mask[:] = False
    elif les == "menos":
        zz, yy, xx = np.meshgrid(Z, Y, X, indexing="ij")
        mask &= ~((xx + 40) ** 2 + (yy + 40) ** 2 + (zz - 20) ** 2 <= 30)      # sem a lesão profunda maior
    hu = np.where(lab > 0, 1000 + lab.astype(np.int16), 0).astype(np.int16)
    hu[mask] += 2000
    pat = {"name": "EXEMPLO^Flair", "id": "FL1", "birth": "19800101", "sex": "F"}
    study = {"uid": generate_uid(), "date": data, "accession": acesso, "description": "RM CRANIO",
             "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 6, "description": "AX 3D T2 FLAIR"}
    d = tmp_path / pasta
    for k in range(hu.shape[0]):
        ds = _base("1.2.840.10008.5.1.4.1.1.4", pat, study, series, "MR")
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [float(X[0]), float(Y[0]), float(Z[k])]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [1.0, 1.0]
        ds.SliceThickness = 1.0
        _mono(ds, hu[k], signed=True)
        _save(ds, d)
    Importer(db, paths.storage).import_paths([d])
    return study["uid"], series["uid"], mask, lista


def _rodar(env, uid, serie):
    from ipe.ai import ferramentas as FE
    from ipe.ai import totalseg as TS
    from ipe.imaging.series import FrameCache
    paths, db, repo = env
    t = TS.Trabalho(repo, FrameCache(256), None, uid, serie, simular=True)
    FE.preparar_trabalho(t, FL)
    t.preparar()
    try:
        t.rodar_aqui()
        res, versao = FE.rodar_conta(t, FL, None)
        saida = FE.gravar(t, FL, res, versao, db, paths.storage, repo, None)
    finally:
        t.limpar()
    return res, saida


def test_do_exame_ao_achado_e_comparacao(env, tmp_path):
    from PySide6.QtWidgets import QApplication

    from ipe.ai import ferramentas as FE
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    assert FE.modulo("flames") is FL
    ant, serie_a, _m, _l = _exame(env, tmp_path, les="menos", data="20260301", acesso="FL00", pasta="a")
    uid, serie, mask, lista = _exame(env, tmp_path)
    assert FL.escolher_serie(repo, uid) == (serie, "")
    res_a, _s = _rodar(env, ant, serie_a)
    assert len(res_a.lesoes) == len(lista) - 1 and res_a.anterior is None
    res, saida = _rodar(env, uid, serie)
    assert len(res.lesoes) == len(lista)
    assert res.total_ml == pytest.approx(mask.sum() / 1000.0, rel=0.01)
    assert {r: res.por_regiao[r][0] for r in FL.REGIOES} == {"peri": 1, "justa": 1, "infra": 1, "prof": 2}
    assert res.maior_mm == pytest.approx(9.0, abs=1.5)                       # a esfera de raio 4
    assert res.anterior == {"data": "20260301", "n": len(lista) - 1, "ml": pytest.approx(res_a.total_ml, abs=0.006)}
    ach = repo.achados(uid, "flames")
    assert len(ach) == 1 and ach[0]["estado"] == "sugerido" and FL.ja_feita(repo, uid)
    txt = FL.frase(ach[0])
    assert "5, com volume total" in txt and "1 periventriculares" in txt and "1 infratentoriais" in txt
    assert "No exame de 01/03/2026: 4 lesões" in txt and "+1 lesões" in txt
    descs = [s.description for s in repo.series_for_study(uid)]
    assert descs.count(FL.DESC_SEG) == 1 and saida["seg_path"]
    assert "Exame anterior (01/03/2026)" in FL.mensagem(res, 2.0) and "pesquisa" in FL.mensagem(res, 2.0)
    # sem lesão: achado com zero e frase negativa
    vazio, serie_v, _m, _l = _exame(env, tmp_path, les=False, data="20250101", acesso="FL99", pasta="v")
    res_v, _s = _rodar(env, vazio, serie_v)
    assert res_v.lesoes == [] and "Sem lesões" in FL.frase(repo.achados(vazio, "flames")[0])


def test_modelo_extra_instalador_e_creditos(tmp_path, monkeypatch):
    from ipe import creditos
    from ipe.ai import extras as EX
    from ipe.ai import instalar_modelos_extras as IM
    from ipe.ai import totalseg as TS
    assert "flames" in EX.MODELOS and "flames" in IM.PASSOS and "17955359" in IM.ZENODO_FLAMES
    assert any(c.nome == "FLAMeS" and "CC BY 4.0" in c.licenca for c in creditos.CREDITOS)
    monkeypatch.setattr(TS, "instalado", lambda _s=None: True)
    monkeypatch.setattr(TS, "pasta_base", lambda: tmp_path / "seg")
    sp = tmp_path / "seg" / "venv" / "lib" / "python3.12" / "site-packages"
    (sp / "nnunetv2").mkdir(parents=True)
    (sp / "dipy").mkdir()
    assert "FLAMeS" in EX.prontidao("flames").falta
    alvo = tmp_path / "seg" / "pesos" / "flames" / "Dataset004_WML" / "nnUNetTrainer_8000epochs__nnUNetPlans__3d_fullres"
    (alvo / "fold_0").mkdir(parents=True)
    (alvo / "fold_0" / "checkpoint_final.pth").write_bytes(b"x")
    assert EX.prontidao("flames").pronto
    # o trabalhador acha a pasta do modelo
    from ipe.ai import totalseg_worker as W
    monkeypatch.setenv("IPE_PESOS", str(tmp_path / "seg" / "pesos"))
    assert W._flames_pasta() == alvo


def test_botao_roda_no_flair_e_abre_os_achados(env, tmp_path, monkeypatch):
    import time

    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie, _m, lista = _exame(env, tmp_path)
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(msg))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, msg, *a, **k: avisos.append("ERRO " + msg))
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1300, 800)
    w.show()
    try:
        assert w.handle_external({"accession": "FL01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        assert tab.app_na_barra("flames")
        vp = next(v for v in tab.viewports if v.frames)
        tab.ferramenta_ia("flames", vp, simular=True)
        fim = time.time() + 180
        while not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert avisos and avisos[-1].startswith("FLAMeS pronto"), avisos
        assert f"{len(lista)} lesão(ões)" in avisos[-1]
        assert repo.achados(uid, "flames")
    finally:
        w.close()
        app.processEvents()
