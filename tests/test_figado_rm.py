"""0.99.49: gordura (PDFF) e ferro (R2*) do fígado na RM.

Fantoma com o arranjo da RM de abdome do acervo (GE, IDEAL IQ): uma série anatômica "WATER: 3D Ax LAVA S/C"
onde o simulador acha o fígado (600) e o baço (500); o mapa "FatFrac: IDEAL IQ (R2*)" (ImageType
…\\FAT_FRACTION, em %) e o "R2*: IDEAL IQ (R2*)" (…\\R2_STAR_MAP, s⁻¹), numa grade **mais grossa** (pixel
3 mm, cortes a cada 8 mm), a 1,5 T; e a dupla eco "3D Ax IN/OUT" com as duas ecos na mesma série.
"""
import time

import numpy as np
import pytest

from ipe.ai import achados as AC
from ipe.ai import figado_rm as F

# grade anatômica: 1,5 mm, 48 cortes de 2 mm (z de 0 a 94)
N, NZ, PX, DZ = 96, 48, 1.5, 2.0
O = -(N / 2) * PX
FIG = (-40, 40, -40, 20, 20, 75)       # caixa do fígado (x0, x1, y0, y1, z0, z1), mm
BACO = (48, 68, 0, 30, 30, 60)


def _dentro(x, y, z, cx):
    x0, x1, y0, y1, z0, z1 = cx
    return (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1) & (z >= z0) & (z <= z1)


def _grade(n, nz, px, dz, o, z0=0.0):
    c = o + np.arange(n) * px
    zz = z0 + np.arange(nz) * dz
    z, y, x = np.meshgrid(zz, c, c, indexing="ij")
    return x, y, z


def _serie(pasta, pat, study, desc, numero, vol, px, dz, o, z0=0.0, extra=None, te=None):
    from pydicom.uid import generate_uid

    from ipe.core.sample_data import _base, _mono, _save
    series = {"uid": generate_uid(), "number": numero, "description": desc}
    for k in range(vol.shape[0]):
        ds = _base("1.2.840.10008.5.1.4.1.1.4", pat, study, series, "MR")
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [o, o, z0 + dz * k]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [px, px]
        ds.SliceThickness = dz
        ds.MagneticFieldStrength = 1.5
        if te is not None:
            ds.EchoTime = te
        for kk, vv in (extra or {}).items():
            setattr(ds, kk, vv)
        _mono(ds, vol[k], signed=True)
        _save(ds, pasta / f"{numero}_{te or 0}")
    return series["uid"]


def _exame(env, tmp_path, com_mapas=True, com_dupla=True):
    from pydicom.uid import generate_uid

    from ipe.importer.scanner import Importer
    paths, db, repo = env
    pat = {"name": "FIGADO^Teste", "id": "FIG1", "birth": "19700101", "sex": "M"}
    study = {"uid": generate_uid(), "date": "20261104", "accession": "FIG01", "description": "RM ABDOME TOTAL",
             "for": generate_uid()}
    pasta = tmp_path / "fig"
    x, y, z = _grade(N, NZ, PX, DZ, O)
    anat = np.full(x.shape, 100, np.int16)
    anat[_dentro(x, y, z, FIG)] = 600
    anat[_dentro(x, y, z, BACO)] = 500
    uid_anat = _serie(pasta, pat, study, "WATER: 3D Ax LAVA S/C", 20, anat, PX, DZ, O)
    # uma série da pelve com mais cortes, que não pode ser a escolhida
    _serie(pasta, pat, study, "WATER: 3D Ax LAVA PRE PELVE", 11, np.full((60, 32, 32), 100, np.int16), 4.5, 2.0, O)
    if com_mapas:
        mx, my, mz = _grade(48, 12, 3.0, 8.0, O)
        ff = np.full(mx.shape, -50, np.int16)
        fig = _dentro(mx, my, mz, FIG)
        ff[fig & (mx < 0)] = 18                   # metade da direita do paciente (x < 0): 18%
        ff[fig & (mx >= 0)] = 6
        _serie(pasta, pat, study, "FatFrac: IDEAL IQ (R2*)", 19, ff, 3.0, 8.0, O,
               extra={"ImageType": ["DERIVED", "PRIMARY", "DIXON", "FAT_FRACTION"]})
        r2 = np.zeros(mx.shape, np.int16)
        r2[fig] = 80
        r2[_dentro(mx, my, mz, BACO)] = 40
        _serie(pasta, pat, study, "R2*: IDEAL IQ (R2*)", 1900, r2, 3.0, 8.0, O,
               extra={"ImageType": ["DERIVED", "PRIMARY", "DIXON", "R2_STAR_MAP"]})
    if com_dupla:
        op = np.full(x.shape, 100, np.int16)
        ip = np.full(x.shape, 120, np.int16)
        op[_dentro(x, y, z, FIG)] = 400
        ip[_dentro(x, y, z, FIG)] = 500
        from pydicom.uid import generate_uid as g
        uid = g()
        for te, v in ((2.084, op), (4.168, ip)):
            from ipe.core.sample_data import _base, _mono, _save
            series = {"uid": uid, "number": 18, "description": "3D Ax IN/OUT"}
            for k in range(v.shape[0]):
                ds = _base("1.2.840.10008.5.1.4.1.1.4", pat, study, series, "MR")
                ds.InstanceNumber = k + 1 + (0 if te < 3 else NZ)
                ds.ImagePositionPatient = [O, O, DZ * k]
                ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
                ds.PixelSpacing = [PX, PX]
                ds.SliceThickness = DZ
                ds.EchoTime = te
                ds.MagneticFieldStrength = 1.5
                _mono(ds, v[k], signed=True)
                _save(ds, pasta / f"io_{te}")
    Importer(db, paths.storage).import_paths([pasta])
    return study["uid"], uid_anat


def test_tipo_do_mapa():
    assert F.tipo_do_mapa("qualquer", ["DERIVED", "PRIMARY", "DIXON", "FAT_FRACTION"]) == "ff"
    assert F.tipo_do_mapa("qualquer", ["DERIVED", "PRIMARY", "DIXON", "R2_STAR_MAP"]) == "r2"
    assert F.tipo_do_mapa("FatFrac: IDEAL IQ (R2*)", None) == "ff"
    assert F.tipo_do_mapa("R2*: IDEAL IQ (R2*)", None) == "r2"
    assert F.tipo_do_mapa("T2* map", None) == "t2"
    assert F.tipo_do_mapa("Ax T2 SSFSE", None) == ""


def test_amostrar_entre_grades():
    from ipe.imaging.volume import Volume
    a = Volume(np.zeros((10, 20, 20)), np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
               np.array([0, 0, 1.0]), 1.0, 1.0, None, "")
    m = np.zeros((10, 20, 20), bool)
    m[2:8, 4:12, 6:14] = True
    b = Volume(np.zeros((5, 10, 10)), np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
               np.array([0, 0, 2.0]), 2.0, 2.0, None, "")
    out = F._amostrar(a, m, b)
    assert out[1:4, 2:6, 3:7].all() and out.sum() == 3 * 4 * 4


def test_escolhe_a_serie_do_abdome_nao_a_da_pelve(env, tmp_path):
    paths, db, repo = env
    uid, uid_anat = _exame(env, tmp_path)
    assert F.escolher_serie(repo, uid)[0] == uid_anat
    m = F.mapas_do_exame(repo, uid)
    assert set(m) == {"ff", "r2"}
    ff, ef, desc = F.dupla_eco(repo, uid)
    assert len(ff) == len(ef) == NZ and "TE 2.08" in desc


def _rodar(env, tmp_path, **kw):
    from ipe.ai import ferramentas as FE
    from ipe.ai import totalseg as TS
    from ipe.imaging.series import FrameCache
    paths, db, repo = env
    uid, uid_anat = _exame(env, tmp_path, **kw)
    t = TS.Trabalho(repo, FrameCache(256), None, uid, uid_anat, simular=True)
    FE.preparar_trabalho(t, F)
    t.preparar()
    t.rodar_aqui()
    res, versao = FE.rodar_conta(t, F, None)
    return t, res, versao, repo, paths, db


def test_gordura_ferro_e_dupla_eco(env, tmp_path):
    t, res, versao, repo, paths, db = _rodar(env, tmp_path)
    try:
        g = res.gordura
        assert g["pdff_p25"]["v"] == pytest.approx(6, abs=0.5) and g["pdff_p75"]["v"] == pytest.approx(18, abs=0.5)
        assert 6 <= g["pdff_mediana"]["v"] <= 18
        assert "S7 18,0" in g["pdff_segmentos"]["v"] and "S2 6,0" in g["pdff_segmentos"]["v"]
        f = res.ferro
        assert f["r2_mediana"]["v"] == 80 and f["t2_ms"]["v"] == 12.5 and f["baco_r2"]["v"] == 40
        assert f["lic"]["v"] == pytest.approx(0.0254 * 80 + 0.202, abs=0.01)
        assert any("Wood" in a for a in res.avisos_ferro) and any("Tang" in a for a in res.avisos_gordura)
        d = res.dixon
        assert d["ff_sinal"]["v"] == pytest.approx(10.0) and d["razao_ef_ff"]["v"] == 1.25
        saida = F.gravar(t, res, versao, db, paths.storage, repo=repo)
        ach = repo.achados(t.study_uid, F.FERRAMENTA)
        assert [a["tipo"] for a in ach] == [F.TIPO_GORDURA, F.TIPO_FERRO, F.TIPO_DIXON]
        assert saida["seg_path"] and F.ja_feita(repo, t.study_uid)
        txt = F.frase({**ach[1], "estado": "confirmado"})
        assert txt.startswith("R2* hepático mediano de 80 s⁻¹ (T2* 12,5 ms)") and "mg Fe/g" in txt
        assert AC.texto_do_laudo(ach, F.frase) == ""          # tudo sugerido: nada vai ao laudo
    finally:
        t.limpar()


def test_sem_mapas_so_dupla_eco_e_ferro_aparece(env, tmp_path):
    t, res, _v, *_r = _rodar(env, tmp_path, com_mapas=False)
    try:
        assert not res.gordura and not res.ferro and res.dixon
    finally:
        t.limpar()


def test_sem_nada_avisa(env, tmp_path):
    t, res, _v, *_r = _rodar(env, tmp_path, com_mapas=False, com_dupla=False)
    try:
        assert not (res.gordura or res.ferro or res.dixon)
        assert any("não tem mapa" in a for a in res.avisos_gordura)
    finally:
        t.limpar()


def test_3t_nao_estima_o_ferro(env, tmp_path, monkeypatch):
    real = F._cabecalho

    def tres_tesla(repo, uid):
        ds = real(repo, uid)
        if ds is not None:
            ds.MagneticFieldStrength = 3.0
        return ds
    monkeypatch.setattr(F, "_cabecalho", tres_tesla)
    t, res, _v, *_r = _rodar(env, tmp_path)
    try:
        assert "lic" not in res.ferro and any("1,5 T" in a for a in res.avisos_ferro)
    finally:
        t.limpar()


def test_na_tela(env, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, uid_anat = _exame(env, tmp_path)
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(msg))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, msg, *a, **k: avisos.append("ERRO " + msg))
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1300, 800)
    w.show()
    try:
        assert w.handle_external({"accession": "FIG01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        assert tab.app_na_barra("figado_rm")
        tab.figado_rm_automatico(tab.active or tab.viewports[0], simular=True)
        fim = time.time() + 120
        while not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert avisos and avisos[-1].startswith("Fígado na RM pronto"), avisos
        p = tab.achados_painel
        assert p.t.rowCount() == 3 and "%" in p.t.item(0, 2).text()
        tab.figado_rm_botao()
        assert tab.achados_painel.isVisible()
    finally:
        w.close()


def test_contrato_e_aba(env):
    from PySide6.QtWidgets import QApplication

    from ipe.ai import ferramentas as FE
    from ipe.core.config import Settings
    from ipe.ui.cad_ia import CadIaTab
    QApplication.instance() or QApplication([])
    assert FE.modulo("figado_rm") is F
    paths, db, repo = env
    t = CadIaTab(Settings(paths.settings_file), repo)
    nomes = [t.l_ferramentas.item(k).text().split("\n")[0] for k in range(t.l_ferramentas.count())]
    assert F.NOME_CADIA in nomes
    assert [x["nome"] for x in F.tarefas()] == ["total_mr", "liver_segments_mr"]
