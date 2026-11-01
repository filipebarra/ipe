"""0.99.20: níveis linfonodais cervicais na TC — marcos do TotalSegmentator e as regras de imagem.

Fantoma em mm (LPS: +x esquerda, +y posterior, +z superior), 1 mm por voxel, com os marcos em
caixas de posição conhecida, espelhados nos dois lados: base do crânio em z = 200, borda de baixo do
hioide em 120, da cricoide em 80, topo do manúbrio em 30, clavículas em 37,5; carótida com a borda
medial a 25 mm (comum) e 27 mm (interna) do meio; jugular até y = 12; esternocleidomastóideo até y = 25;
submandibular até y = −10; barriga anterior do digástrico a 8 mm do meio.
"""
import numpy as np
import pytest

from ipe.ai import linfonodos as L
from ipe.imaging.volume import Volume

X = np.arange(-80, 81)
Y = np.arange(-60, 81)
Z = np.arange(220, -1, -1)

#: estrutura -> (código no fantoma, caixas [(x0, x1, y0, y1, z0, z1)] do lado esquerdo; o direito é o espelho)
CAIXAS = {
    # o "skull" do TotalSegmentator pode trazer a mandíbula (caso real): uma "mandíbula" logo acima do hioide
    "skull": (14, [(-80, 80, -60, 80, 200, 220), (-40, 40, -58, -45, 128, 140)], False),
    "hyoid": (1, [(-15, 15, -20, -12, 120, 124)], False),
    "thyroid_cartilage": (3, [(-15, 15, -25, -15, 95, 115)], False),
    "cricoid_cartilage": (2, [(-12, 12, -20, -5, 80, 86)], False),
    "sternum": (15, [(-20, 20, -30, -10, 0, 30)], False),
    "clavicula_left": (16, [(20, 80, -20, -10, 35, 40)], False),
    "clavicula_right": (17, [(-80, -20, -20, -10, 35, 40)], False),
    "submandibular_gland_left": (11, [(25, 40, -30, -10, 125, 145)], False),
    "submandibular_gland_right": (10, [(-40, -25, -30, -10, 125, 145)], False),
    "digastric_left": (13, [(8, 12, -50, -30, 125, 130), (30, 35, 0, 20, 130, 140)], False),
    "digastric_right": (12, [(-12, -8, -50, -30, 125, 130), (-35, -30, 0, 20, 130, 140)], False),
    "common_carotid_artery_left": (18, [(25, 31, 0, 6, 30, 110)], False),
    "common_carotid_artery_right": (19, [(-31, -25, 0, 6, 30, 110)], False),
    "internal_carotid_artery_left": (5, [(27, 33, 3, 9, 111, 195)], False),
    "internal_carotid_artery_right": (4, [(-33, -27, 3, 9, 111, 195)], False),
    "internal_jugular_vein_left": (7, [(35, 45, 2, 12, 30, 200)], False),
    "internal_jugular_vein_right": (6, [(-45, -35, 2, 12, 30, 200)], False),
    "sternocleidomastoid_left": (9, [(46, 60, -10, 25, 40, 190)], False),
    "sternocleidomastoid_right": (8, [(-60, -46, -10, 25, 40, 190)], False),
}


def fantoma():
    zz, yy, xx = np.meshgrid(Z, Y, X, indexing="ij")
    hu = np.full(xx.shape, 40, np.int16)
    for nome, (cod, caixas, _e) in CAIXAS.items():
        for x0, x1, y0, y1, z0, z1 in caixas:
            sel = (xx >= x0) & (xx <= x1) & (yy >= y0) & (yy <= y1) & (zz >= z0) & (zz <= z1)
            hu[sel] = 2000 + cod
    vol = Volume(hu, np.array([X[0], Y[0], Z[0]], float), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
                 np.array([0, 0, -1.0]), 1.0, 1.0, None, "")
    from ipe.ai import totalseg_worker as W
    rot = {}
    for tarefa, cods in W.LINFO_SIM.items():
        lab = np.zeros(hu.shape, np.uint8)
        for cid, (cod, _n) in cods.items():
            lab[hu == 2000 + cod] = cid
        rot[tarefa] = (lab, {cid: n for cid, (_c, n) in cods.items()})
    return vol, rot


@pytest.fixture(scope="module")
def marcos():
    vol, rot = fantoma()
    return L.marcos(vol, rot)


def test_marcos(marcos):
    m = marcos
    assert m.xm == pytest.approx(0.0, abs=1.0)
    assert m.z_hioide == pytest.approx(120, abs=0.6) and m.z_cricoide == pytest.approx(80, abs=0.6)
    assert m.z_cranio == pytest.approx(200, abs=0.6) and m.z_manubrio == pytest.approx(30, abs=0.6)
    assert m.z_clav["E"] == pytest.approx(37.5, abs=1) and m.y_smg["D"] == pytest.approx(-10, abs=0.6)
    assert m.d_dig == pytest.approx(8, abs=0.6)
    z = np.array([60.0, 150.0])
    assert np.allclose(m._tab(m.car_med, "E", z, 0), [25, 27], atol=0.6)
    assert np.allclose(m._tab(m.scm_post, "D", z, 0), [25, 25], atol=0.6)
    assert not m.avisos


@pytest.mark.parametrize("ponto, esperado", [
    ((0, -40, 135), ("IA", "D")), ((20, -40, 135), ("IB", "E")), ((30, 10, 150), ("IIA", "E")),
    ((-30, 10, 150), ("IIA", "D")), ((40, 20, 150), ("IIB", "E")), ((35, 5, 100), ("III", "E")),
    ((-35, 5, 60), ("IV", "D")), ((40, 40, 100), ("VA", "E")), ((40, 40, 60), ("VB", "E")),
    ((5, -30, 100), ("VI", "E")), ((5, 10, 150), ("RF", "E")), ((5, -20, 20), ("VII", "E")),
    ((5, 0, 215), ("", "E")), ((40, -20, 25), ("", "E")),
])
def test_niveis(marcos, ponto, esperado):
    nv, ld, regra = L.classificar([ponto], marcos)[0]
    assert (nv, ld) == esperado, regra
    assert regra


def test_texto_e_json(marcos):
    curto, longo, regra = L.texto_da_lesao((30, 10, 150), marcos)
    assert curto == "IIA E" and longo == "nível IIA esquerdo" and "jugular" in regra
    assert L.texto_da_lesao((5, 10, 150), marcos)[1] == "retrofaríngeo esquerdo"
    m2 = L.de_json(L.para_json(marcos))
    assert L.classificar([(40, 40, 60)], m2)[0][0] == "VB"


def test_mapa_rotulos_em_qualquer_plano(marcos):
    vol, _r = fantoma()
    vols = L.mapa(marcos, vol)
    rotulos = {mv.label for mv in vols}
    assert {"IIA E", "IIA D", "III E", "IV D", "VA E", "VI E", "IA D"} <= rotulos
    assert all(getattr(mv, "so_rotulo", False) for mv in vols)
    # um axial em z = 100 corta o nível III, não o II
    iii = next(mv for mv in vols if mv.label == "III E")
    pos, row, col, n = (np.array([-80.0, -60.0, 100.0]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
                        np.array([0, 0, 1.0]))
    assert iii.fatia(pos, row, col, n, (1.0, 1.0), (141, 161)) is not None
    ii = next(mv for mv in vols if mv.label == "IIA E")
    assert ii.fatia(pos, row, col, n, (1.0, 1.0), (141, 161)) is None


def test_sem_marcos_avisa():
    vol, rot = fantoma()
    lab, cl = rot["headneck_muscles"]
    rot["headneck_muscles"] = (np.zeros_like(lab), cl)
    m = L.marcos(vol, rot)
    assert any("esternocleidomastóideo" in a for a in m.avisos)
    # sem o ECM, nada vira V
    assert L.classificar([(40, 40, 100)], m)[0][0] != "VA"


# ------------------------------------------------------------------ do exame à tela
def _exame(env, tmp_path):
    from pydicom.uid import generate_uid

    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    vol, _r = fantoma()
    hu = vol.data.copy()
    hu[hu == 40] = -100                                     # gordura
    zz, yy, xx = np.meshgrid(Z, Y, X, indexing="ij")
    hu[((xx - 30) ** 2 + (yy - 10) ** 2 + (zz - 150) ** 2) <= 36] = 60      # linfonodo de 12 mm no IIA E
    pat = {"name": "PESCOCO^Teste", "id": "LIN1", "birth": "19600101", "sex": "M"}
    study = {"uid": generate_uid(), "date": "20261101", "accession": "LIN01", "description": "TC PESCOCO",
             "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 3, "description": "AX PARTES MOLES"}
    pasta = tmp_path / "linfo"
    for k in range(hu.shape[0]):
        ds = _base("1.2.840.10008.5.1.4.1.1.2", pat, study, series, "CT")
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [float(X[0]), float(Y[0]), float(Z[k])]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [1.0, 1.0]
        ds.SliceThickness = 1.0
        ds.RescaleSlope, ds.RescaleIntercept = 1, 0
        _mono(ds, hu[k], signed=True)
        _save(ds, pasta)
    Importer(db, paths.storage).import_paths([pasta])
    return study["uid"], series["uid"]


def test_tela_mapa_e_lesao_com_nivel(env, tmp_path, monkeypatch):
    import time

    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, _s = _exame(env, tmp_path)
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(msg))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, msg, *a, **k: avisos.append("ERRO " + msg))
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1300, 800)
    w.show()
    try:
        assert w.handle_external({"accession": "LIN01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        assert tab.app_na_barra("linfonodos")
        vp = next(v for v in tab.viewports if v.frames)
        tab.linfonodos_automatico(vp, simular=True)
        fim = time.time() + 120
        while not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert avisos and avisos[-1].startswith("Mapa dos níveis linfonodais pronto"), avisos
        mapa = [o for o in tab.overlay_objects if o.source == L.FONTE_OVERLAY]
        assert len(mapa) == 1 and {"IIA E", "III D"} <= {mv.label for mv in mapa[0].volumes}
        assert tab.nivel_linfonodal_do_ponto((30, 10, 150))[0] == "IIA E"
        assert L.ja_feita(repo, uid)
        # a lesão segmentada ganha o nível e o nome
        from ipe.ui.viewer.onco import SegmentDialog
        vol = tab._volume_for(vp, tab._source_series(vp))
        ijk = np.rint(vol.patient_to_voxel(np.array([30.0, 10.0, 150.0]))).astype(int)
        dlg = SegmentDialog(tab, vp, vol, (ijk[2], ijk[1], ijk[0]), (0, 0), vp.frame_key())
        assert dlg.res is not None and dlg.res.voxels > 100
        assert dlg.name.text() == "Linfonodo IIA E"
        assert "nível IIA esquerdo" in dlg.result.text()
        assert dlg.obj.stats.get("nivel_linfonodal") == "nível IIA esquerdo"
        dlg.close()
        # reabrindo o exame, o mapa volta da SEG
        w.tabs.removeTab(w.tabs.indexOf(tab))
        assert w.handle_external({"accession": "LIN01"}) == "aberto"
        tab2 = w.tabs.currentWidget()
        for _ in range(30):
            app.processEvents()
        assert getattr(tab2, "marcos_linfonodais", None) is not None
        assert any(o.source == L.FONTE_OVERLAY for o in tab2.overlay_objects)
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
    assert not eng.niveis_linfonodais(uid)
    st.set(L.CHAVE_AUTO, True)
    eng.study_arrived(uid, "received")
    assert L.ja_feita(repo, uid)
    m, vols = L.ler_do_exame(repo, uid, com_mapa=True)
    assert m.z_hioide == pytest.approx(120, abs=0.6) and vols
    assert any(r["name"] == "Níveis linfonodais" and r["status"] == "ok" for r in repo.job_runs())


def test_instalador_baixa_os_musculos_do_pescoco():
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    for arq in ("instalar_segmentacao.bat", "instalar_segmentacao.sh"):
        assert "headneck_muscles" in (raiz / arq).read_text(encoding="utf-8"), arq


def test_base_do_cranio_sem_jugulares_ignora_a_mandibula():
    vol, rot = fantoma()
    lab, cl = rot["headneck_bones_vessels"]
    lab = lab.copy()
    for cid in (9, 10, 11, 12):                  # sem carótidas internas nem jugulares
        lab[lab == cid] = 0
    rot["headneck_bones_vessels"] = (lab, cl)
    m = L.marcos(vol, rot)
    assert m.z_cranio == pytest.approx(200, abs=0.6) and any("base do crânio" in a for a in m.avisos)
