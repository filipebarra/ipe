"""0.99.17: índices do crânio com o SynthSeg — Evans, 3º ventrículo, ângulo calosal e volumes.

Fantoma em mm (LPS: +x esquerda, +y posterior, +z superior), 1 mm por voxel, com os rótulos do
SynthSeg: crânio elipsoide, cornos frontais de 37 mm, 3º ventrículo de 7 mm, corpos dos ventrículos
com as paredes mediais a 80° uma da outra no coronal da comissura posterior, hipocampos e amígdalas.
"""
import numpy as np
import pytest

from ipe.ai import neuro as N
from ipe.imaging.volume import Volume

X = np.arange(-80, 81)
Y = np.arange(-100, 101)
Z = np.arange(80, -61, -1)
ANG = 80.0


def fantoma(intensidade: bool = False):
    zz, yy, xx = np.meshgrid(Z, Y, X, indexing="ij")
    xx, yy, zz = (a.astype(float) for a in (xx, yy, zz))
    lab = np.zeros(xx.shape, np.uint8)
    dentro = (xx / 65) ** 2 + (yy / 85) ** 2 + (zz / 60) ** 2 <= 1
    lab[dentro & (xx >= 0)] = 2
    lab[dentro & (xx < 0)] = 41
    casca = dentro & ~((xx / 62) ** 2 + (yy / 82) ** 2 + (zz / 57) ** 2 <= 1)
    lab[casca] = 24
    # cornos frontais (à frente do 3º ventrículo, que começa em y = −5)
    cornos = (yy >= -40) & (yy <= -5) & (zz >= 5) & (zz <= 20)
    lab[cornos & (xx >= 3) & (xx <= 18)] = 4
    lab[cornos & (xx <= -3) & (xx >= -18)] = 43
    # corpos: parede medial x = (30 − z)·tan(40°) + 1, faixa de 12 mm
    t = np.tan(np.radians(ANG / 2))
    corpo = (yy >= -3) & (yy <= 30) & (zz >= 0) & (zz <= 25)
    med = (30 - zz) * t + 1
    lab[corpo & (xx >= med) & (xx <= med + 12)] = 4
    lab[corpo & (-xx >= med) & (-xx <= med + 12)] = 43
    lab[(yy >= -5) & (yy <= 25) & (zz >= -5) & (zz <= 10) & (np.abs(xx) <= 3)] = 14
    lab[(yy >= 40) & (yy <= 46) & (zz >= -40) & (zz <= -34) & (np.abs(xx) <= 3)] = 15
    for sx, hip, amig in ((1, 17, 18), (-1, 53, 54)):
        lab[((xx - sx * 25) / 8) ** 2 + ((yy - 10) / 18) ** 2 + ((zz + 20) / 8) ** 2 <= 1] = hip
        lab[((xx - sx * 22) / 6) ** 2 + ((yy + 15) / 6) ** 2 + ((zz + 20) / 6) ** 2 <= 1] = amig
    vol = Volume(np.where(lab > 0, 300, 0).astype(np.int16), np.array([X[0], Y[0], Z[0]], float),
                 np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, -1.0]), 1.0, 1.0, None, "")
    return vol, {"synthseg": (lab, dict(N.NOMES_SYNTHSEG))}, lab


@pytest.fixture(scope="module")
def res():
    vol, rot, _lab = fantoma()
    return N.calcular(vol, rot)


def test_evans(res):
    vol, rot, lab = fantoma()
    assert res["cornos"].valor == pytest.approx(37.0, abs=1.0)
    z = res["cornos"].linhas[0][0][2]
    k = int(np.where(Z == round(z))[0][0])
    fatia = lab[k] > 0
    esperado = max((np.ptp(np.nonzero(r)[0]) + 1) for r in fatia if r.any())
    assert res["cranio"].valor == pytest.approx(esperado, abs=1.0)
    assert res["evans"].valor == pytest.approx(res["cornos"].valor / res["cranio"].valor)
    a, b = res["cornos"].linhas[0]
    assert a[2] == b[2] and a[1] == b[1] and a[1] <= -5                     # axial, à frente do 3º


def test_terceiro_ventriculo(res):
    assert res["v3"].valor == pytest.approx(7.0, abs=0.6)
    assert len(res["v3"].linhas) == 3 and res["v3"].texto.count("/") == 2


def test_angulo_calosal(res):
    assert res["calosal"].valor == pytest.approx(ANG, abs=4.0)
    (a0, a1), (b0, b1) = res["calosal"].linhas
    assert a0[1] == a1[1] == b0[1] == pytest.approx(25.0)                    # coronal da comissura posterior
    assert N.plano_da_medida(res["calosal"])[0] == "Coronal"


def test_volumes_e_assimetria(res):
    vol, rot, lab = fantoma()
    assert res["hipo_e"].valor == pytest.approx((lab == 17).sum() / 1000.0)
    assert res["hipo_d"].valor == pytest.approx((lab == 53).sum() / 1000.0)
    assert res["hipo_assim"].valor == pytest.approx(0.0, abs=1.0)
    assert res["vic"].valor == pytest.approx((lab > 0).sum() / 1000.0)
    assert res["vent_lat"].valor == pytest.approx(((lab == 4) | (lab == 43)).sum() / 1000.0)


def test_texto_recalculo_e_roteiro(res):
    import copy
    t = N.texto_do_laudo(res, modalidade="MR")
    assert t.startswith("Índices do crânio por RM (segmentação automática SynthSeg):")
    assert "- Índice de Evans: 0," in t and "(referência: acima de 0,30" in t
    assert f"- Ângulo calosal: {round(res['calosal'].valor)}° (referência: abaixo de 90°" in t
    assert "- Volume dos hipocampos: direito " in t
    r = copy.deepcopy(res)
    r["cornos"].valor, r["cornos"].origem = 45.0, "editado"
    N.recalcular(r)
    assert r["evans"].valor == pytest.approx(45.0 / r["cranio"].valor) and r["evans"].origem == "calculado"
    v = N.valores_para_roteiro(res)
    assert len(v["v3"]) == 3 and v["cornos"] == [res["cornos"].valor] and v["angulo"] == [res["calosal"].valor]
    # json de ida e volta
    lido = N.de_json(N.para_json(res))
    assert lido["calosal"].valor == pytest.approx(res["calosal"].valor) and len(lido["v3"].linhas) == 3


def test_sem_segmentacao():
    vol, rot, lab = fantoma()
    r = N.calcular(vol, {})
    assert r["evans"].valor is None and r.avisos
    lab2 = lab.copy()
    lab2[lab2 == 14] = 2
    r = N.calcular(vol, {"synthseg": (lab2, dict(N.NOMES_SYNTHSEG))})
    assert r["v3"].valor is None and "3º ventrículo" in r["v3"].motivo
    assert r["hipo_d"].valor is not None                                     # o resto continua


# ------------------------------------------------------------------ do exame à janela (trabalhador simulado)
def _exame(env, tmp_path, descricao="RM CRANIO"):
    from pydicom.uid import generate_uid

    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    _v, _r, lab = fantoma()
    hu = np.where(lab > 0, 1000 + lab.astype(np.int16), 0).astype(np.int16)
    pat = {"name": "CRANIO^Teste", "id": "NEU1", "birth": "19500101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20261030", "accession": "NEU01", "description": descricao,
             "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 5, "description": "AX 3D T1"}
    pasta = tmp_path / "neuro"
    for k in range(hu.shape[0]):
        ds = _base("1.2.840.10008.5.1.4.1.1.4", pat, study, series, "MR")
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [float(X[0]), float(Y[0]), float(Z[k])]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [1.0, 1.0]
        ds.SliceThickness = 1.0
        _mono(ds, hu[k], signed=True)
        _save(ds, pasta)
    Importer(db, paths.storage).import_paths([pasta])
    return study["uid"], series["uid"]


def test_trabalhador_simulado_grava_e_relê(env, tmp_path):
    from PySide6.QtWidgets import QApplication

    from ipe.ai import neuro_saida as NS
    from ipe.ai import totalseg as TS
    from ipe.imaging.series import FrameCache
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie = _exame(env, tmp_path)
    t = TS.Trabalho(repo, FrameCache(256), None, uid, serie, simular=True)
    t.tarefas_proprias, t.min_cortes, t.modalidades = N.tarefas, N.MIN_CORTES, ("MR", "CT")
    t.preparar()
    try:
        t.rodar_aqui()
        rot, versao, _s = t.ler_rotulos()
        r = N.calcular(t.vol, rot)
        r.modalidade = t.modalidade
        assert r["cornos"].valor == pytest.approx(37.0, abs=1.0)
        NS.gravar(t, r, versao, db, paths.storage, repo=repo)
        NS.gravar(t, r, versao, db, paths.storage, repo=repo)                 # refazer troca, não duplica
        descs = [s.description for s in repo.series_for_study(uid)]
        assert descs.count(N.DESC_SEG) == 1 and descs.count(N.DESC_IMAGEM) == 1
        lido = N.ler_do_exame(repo, uid)
        assert lido.modalidade == "MR" and lido["calosal"].valor == pytest.approx(r["calosal"].valor)
        assert N.ja_feita(repo, uid)
        assert N.DESC_SEG in [s.description for s in repo.series_for_study(uid)
                              if s.series_uid in TS.series_locais(repo, uid)]        # só neste computador
    finally:
        t.limpar()


def test_recorte_da_cabeca_do_trabalhador():
    from ipe.ai import totalseg_worker as W
    dados = np.zeros((40, 40, 300), np.float32)                     # (i, j, k), k crescente = para cima
    dados[5:35, 5:35, 10:290] = 100
    afim = np.diag([1.0, 1.0, 1.0, 1.0])
    fat, novo = W._recorte_da_cabeca(dados, afim)
    assert fat[2].stop - fat[2].start == 200 and fat[2].stop >= 290      # os 200 mm de cima
    assert novo[2, 3] == pytest.approx(fat[2].start)
    assert fat[0].start == 1 and fat[0].stop == 39


def test_tela_automatica_janela_e_mrpi_preenchido(env, tmp_path, monkeypatch):
    import time

    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.imaging import roteiros as RT
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    _exame(env, tmp_path)
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(msg))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, msg, *a, **k: avisos.append("ERRO " + msg))
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1300, 800)
    w.show()
    try:
        assert w.handle_external({"accession": "NEU01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        assert tab.app_na_barra("indices")
        vp = next(v for v in tab.viewports if v.frames)
        tab.neuro_automatica(vp, simular=True)
        fim = time.time() + 120
        while not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert avisos and avisos[-1].startswith("Índices do crânio prontos"), avisos
        p = tab.neuro_painel
        assert p.automatica and "Índice de Evans: 0," in p.texto()
        linhas = [o for o in tab.overlay_objects if o.source == N.FONTE_OVERLAY]
        assert len(linhas) == 1 and len(linhas[0].planar) >= 6
        # trocar os cornos recalcula o Evans
        r_cornos = N.ORDEM.index("cornos")
        p.tabela.item(r_cornos, 2).setText("50")
        ev = p.res["evans"]
        assert ev.valor == pytest.approx(50 / p.res["cranio"].valor) and ev.origem == "calculado"
        # ver o ângulo calosal: reformata em coronal
        p.tabela.setCurrentCell(N.ORDEM.index("calosal"), 2)
        assert p.ver_no_quadro() and tab.active.plano_nome() == "Coronal"
        # o roteiro do MRPI já vem com o 3º ventrículo e os cornos
        rot = tab.abrir_roteiro("mrpi")
        v3 = next(x for x in RT.MRPI.passos if x.id == "v3")
        assert rot.andamento.feitas(v3) == 3 and rot.andamento.avisos.get("v3")
        assert rot.andamento.proximo().id == "ponte"
        ev_rot = tab.abrir_roteiro("evans")
        assert ev_rot.andamento.pronto()
    finally:
        w.close()


def test_automatico_na_chegada(env, tmp_path):
    from PySide6.QtWidgets import QApplication

    from ipe.automation.engine import AutomationEngine
    from ipe.core.config import Settings
    from test_cefalometria import _Rede
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, _s = _exame(env, tmp_path)
    st = Settings(paths.settings_file)
    eng = AutomationEngine(repo, db, _Rede(), st, paths)
    eng._seg_simular = True
    assert not eng.indices_cranio(uid)                                      # desligado de fábrica
    st.set(N.CHAVE_AUTO, True)
    prontos = []
    eng.segmentacao_pronta.connect(lambda u, s: prontos.append(s))
    eng.study_arrived(uid, "received")
    assert N.ja_feita(repo, uid) and prontos and prontos[0]["neuro"]["evans"].valor is not None
    assert any(r["name"] == "Índices do crânio" and r["status"] == "ok" for r in repo.job_runs())
    assert not eng.indices_cranio(uid)


def test_cad_ia_e_creditos(env):
    from PySide6.QtWidgets import QApplication, QWidget

    from ipe import creditos
    from ipe.core.config import Settings
    from ipe.ui.preferences import PreferencesDialog
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    pai = QWidget()
    pai.repo = repo
    st = Settings(paths.settings_file)
    c = PreferencesDialog(st, pai).cad_ia
    nomes = [c.l_ferramentas.item(k).text().split("\n")[0] for k in range(c.l_ferramentas.count())]
    assert "Índices do crânio" in nomes
    c.c_neu_auto.setChecked(True)
    c.c_neu_ct.setChecked(False)
    c.save()
    assert st.get(N.CHAVE_AUTO) is True and st.get(N.CHAVE_MODALIDADES) == ["MR"]
    texto = creditos.markdown()
    assert "SynthSeg" in texto and "DIPY" in texto and "Billot" in texto


def test_instalador_acrescenta_a_dipy():
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    for arq in ("instalar_segmentacao.bat", "instalar_segmentacao.sh"):
        texto = (raiz / arq).read_text(encoding="utf-8")
        assert "dipy>=1.12" in texto and "synthseg_torch_weights" in texto and "DIPY_HOME" in texto, arq


# ------------------------------------------------------------------ 0.99.18: medir na grade de 1 mm do SynthSeg
def test_grade_de_1mm_vira_volume_em_lps():
    lab = np.zeros((10, 12, 14), np.uint8)              # (i, j, k) em RAS
    lab[2, 3, 4] = 14
    afim = np.eye(4)
    afim[:3, 3] = [-50.0, -60.0, -70.0]
    vol, lab_kji = N.volume_da_grade(lab, afim)
    p = N.pontos(vol, lab_kji == 14)
    # RAS (−48, −57, −66) → LPS (48, 57, −66)
    assert p.shape == (1, 3) and np.allclose(p[0], [48.0, 57.0, -66.0])


def test_serie_sagital_grossa_mede_na_grade_fina(env, tmp_path):
    """O primeiro caso real: série sagital de 5 mm — a largura do 3º ventrículo saiu do tamanho de um
    pixel. Medindo na grade do SynthSeg (aqui simulada pela própria série de 1 mm), sai a de verdade,
    e a SEG continua na grade da série."""
    from ipe.ai import totalseg as TS
    from ipe.imaging.series import FrameCache
    paths, db, repo = env
    uid, serie = _exame(env, tmp_path)
    t = TS.Trabalho(repo, FrameCache(256), None, uid, serie, simular=True)
    t.tarefas_proprias, t.min_cortes, t.modalidades = N.tarefas, N.MIN_CORTES, ("MR", "CT")
    t.preparar()
    try:
        t.rodar_aqui()
        r = N.calcular_do_trabalho(t)
        assert "synthseg" in t.extras and t.versao == "simulado"
        assert r["v3"].valor == pytest.approx(7.0, abs=0.6) and r["cranio"].valor is not None
        assert r.modalidade == "MR" and r.estruturas
        m, off = r.estruturas[N.V3]
        assert m.ndim == 3 and (np.asarray(off) >= 0).all()
    finally:
        t.limpar()


def test_serie_preferida_nao_pega_swan():
    from types import SimpleNamespace

    from ipe.ai import totalseg as TS

    class Repo:
        def series_for_study(self, _u):
            return [SimpleNamespace(series_uid="swan", modality="MR", description="3D Ax SWAN"),
                    SimpleNamespace(series_uid="t1", modality="MR", description="S T1 FLAIR")]

        def instances_for_series(self, uid):
            return [{"path": ""}] * (74 if uid == "swan" else 25)
    orig = TS._espessura
    TS._espessura = lambda *_a: None
    try:
        uid, _m = N.escolher_serie(Repo(), "x")
    finally:
        TS._espessura = orig
    assert uid == "t1"


def test_geometria_do_synthseg_de_verdade_com_modelo_falso(monkeypatch):
    """O caminho do trabalhador com a DIPY de verdade (transform_img, inv_pad_crop, recover_img) e um
    modelo falso que "acerta tudo": a grade de 1 mm e a da série têm de cair no mesmo lugar do paciente.
    É onde um eixo trocado ou um sinal de RAS/LPS errado passaria despercebido."""
    dipy_utils = pytest.importorskip("dipy.nn.utils")
    import sys
    import types

    from ipe.ai import totalseg as TS
    from ipe.ai import totalseg_worker as W
    vol, _r, lab = fantoma()
    rotulos_ss = np.array(sorted({0, *N.NOMES_SYNTHSEG}))

    class Falso:
        labels_segmentation = rotulos_ss
        label_dict = {0: "background", **N.NOMES_SYNTHSEG}

        def predict(self, img, afim, return_prob=False):
            t, _p = dipy_utils.transform_img(img, afim, target_voxsize=(1.0, 1.0, 1.0),
                                             final_size=(192, 192, 192), order=0)
            idx = np.searchsorted(rotulos_ss, np.round(t).astype(int))
            prob = np.zeros(t.shape + (len(rotulos_ss),), bool)
            np.put_along_axis(prob, idx[..., None], True, axis=-1)
            return prob

    mod = types.ModuleType("dipy.nn.torch.synthseg")
    mod.SynthSeg = Falso
    monkeypatch.setitem(sys.modules, "dipy.nn.torch.synthseg", mod)
    afim = TS.afim_ras(vol)
    serie, classes, lab_1mm, afim_1mm = W._synthseg(lab.astype(np.float32), afim)
    assert serie.shape == lab.shape and classes[14] == "3rd ventricle"
    # a da série volta igual (fora o que o cubo de 192 mm cortou)
    dentro = serie > 0
    assert (serie[dentro] == lab[dentro]).mean() > 0.99
    # a de 1 mm, no mesmo lugar do paciente
    vol1, lab1 = N.volume_da_grade(lab_1mm, afim_1mm)
    c0 = N.pontos(vol, lab == N.V3).mean(axis=0)
    c1 = N.pontos(vol1, lab1 == N.V3).mean(axis=0)
    assert np.allclose(c0, c1, atol=0.6)
    r = N.calcular(vol1, {"synthseg": (lab1, dict(N.NOMES_SYNTHSEG))})
    assert r["v3"].valor == pytest.approx(7.0, abs=0.6) and r["cornos"].valor == pytest.approx(37.0, abs=1.0)
