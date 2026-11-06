"""Lesões hepáticas e carga por segmento de Couinaud (0.99.82; item 3 da lista do MedMLX)."""
import numpy as np
import pytest

from ipe.ai import achados as AC
from ipe.ai import figado_lesoes as FL
from ipe.imaging.volume import Volume

PX, N, NZ, DZ = 2.0, 90, 40, 2.5


def _hu(lesoes=((0.5, 0.5, 6), (0.8, 0.5, 4)), contraste=True):
    """Abdome: corpo 40 HU, fígado (620) numa elipse; lesões (630) esféricas: (fração de x, de y, raio em px)."""
    c = np.arange(N)
    yy, xx = np.meshgrid(c, c, indexing="ij")
    hu = np.full((NZ, N, N), -1000, np.int16)
    corpo = ((xx - N / 2) / 42) ** 2 + ((yy - N / 2) / 38) ** 2 <= 1
    fig = ((xx - N / 2) / 36) ** 2 + ((yy - N / 2) / 20) ** 2 <= 1
    for k in range(NZ):
        s = hu[k]
        s[corpo] = 40
        if 8 <= k < 32:
            s[fig] = 620
    kk = np.arange(NZ)[:, None, None]
    for fx, fy, r in lesoes:
        cx, cy = fx * N, fy * N
        esf = ((xx[None] - cx) ** 2 + (yy[None] - cy) ** 2 + ((kk - 20) * DZ / PX) ** 2) <= r * r
        hu[esf & (hu == 620)] = 630
    return hu


class _T:
    def __init__(self, hu, desc="ABDOME PORTAL"):
        self.vol = Volume(hu, np.array([0.0, 0.0, 0.0]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
                          np.array([0, 0, DZ]), PX, PX, None, "")
        self.frames = []
        self.series_uid = "1.2.3"
        self.study_uid = "1.2"
        self.descricao_serie = desc
        self.versao = "simulado"
        self.modalidade = "CT"


def _rotulos(hu, tarefas):
    from ipe.ai import totalseg_worker as W
    return W._simular(hu, tarefas)


def test_tarefas_ct_e_rm():
    assert [t["nome"] for t in FL.tarefas("CT")] == ["liver_segments", "liver_lesions"]
    assert [t["nome"] for t in FL.tarefas("MR")] == ["liver_segments_mr", "liver_lesions_mr"]
    assert not any(t.get("fast") for t in FL.tarefas("CT"))


def test_lesoes_volume_diametro_e_segmento():
    hu = _hu()
    t = _T(hu)
    res = FL.calcular(t, _rotulos(hu, FL.tarefas("CT")))
    assert len(res.lesoes) == 2
    a, b = res.lesoes                                   # a maior primeiro
    voxel_ml = PX * PX * DZ / 1000
    assert a.vol_ml == pytest.approx((hu == 630).sum() * voxel_ml * a.vol_ml / res.vol_lesoes, rel=1e-6)
    assert a.diam_mm == pytest.approx(2 * 6 * PX + PX, abs=2 * PX)          # raio 6 px
    assert b.diam_mm < a.diam_mm
    assert a.segmento == 4 and b.segmento == 2                            # terço do meio / terço de cima de x
    assert a.media == pytest.approx(630, abs=0.5)
    vf = ((hu == 620) | (hu == 630)).sum() * voxel_ml
    assert res.vol_figado == pytest.approx(vf, rel=1e-6)
    assert res.carga == pytest.approx(100 * (hu == 630).sum() / ((hu == 620) | (hu == 630)).sum(), abs=0.01)
    assert set(res.segmentos) == {2, 4, 7} and res.segmentos[7]["carga"] == 0
    assert res.segmentos[4]["carga"] > 0 and res.segmentos[2]["carga"] > 0
    assert not any("sem contraste" in x for x in res.avisos)
    assert res.seg_mask is not None and res.lesao_mask.sum() == (hu == 630).sum()


def test_achados_frase_e_laudo():
    hu = _hu()
    t = _T(hu)
    res = FL.calcular(t, _rotulos(hu, FL.tarefas("CT")))
    itens = FL.itens_para_o_banco(res, t, "x")
    assert [i["tipo"] for i in itens] == [FL.TIPO_RESUMO, FL.TIPO_LESAO, FL.TIPO_LESAO]
    assert [i["rotulo"] for i in itens] == ["F", "L1", "L2"]
    assert itens[1]["local"].startswith("segmento IV")
    resumo = {**itens[0], "estado": "confirmado", "corrigidos": {}}
    f = FL.frase(resumo)
    assert f.startswith("2 lesão(ões) focal(is) hepática(s)") and "Carga por segmento: II" in f and "VII" not in f
    l1 = {**itens[1], "estado": "confirmado", "corrigidos": {}}
    f1 = FL.frase(l1)
    assert f1.startswith("Lesão hepática no segmento IV") and "maior diâmetro axial" in f1 and "HU" in f1
    assert "2 lesão(ões)" in FL.resumo(res) and FL.n_itens(res) == 3
    # sem lesão
    hu0 = _hu(lesoes=())
    res0 = FL.calcular(_T(hu0), _rotulos(hu0, FL.tarefas("CT")))
    assert not res0.lesoes and res0.carga == 0
    it0 = FL.itens_para_o_banco(res0, _T(hu0), "x")
    assert len(it0) == 1 and FL.frase({**it0[0], "corrigidos": {}}).startswith("Não foram identificadas")


def test_avisos_sem_contraste_e_corte_grosso_e_ilhas():
    hu = _hu(lesoes=((0.35, 0.5, 6), (0.6, 0.45, 0.6)))         # a segunda é uma ilha de 1 voxel
    t = _T(hu, desc="ABDOME SEM CONTRASTE")
    t.vol = Volume(hu, np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 5.0]), PX, PX,
                   None, "")
    res = FL.calcular(t, _rotulos(hu, FL.tarefas("CT")))
    av = " ".join(res.avisos)
    assert "sem contraste" in av and "cortes de 5,0 mm" in av and "ilha" in av
    assert len(res.lesoes) == 1


def test_contrato_e_gravar(env, monkeypatch):
    from ipe.ai import ferramentas as FE
    assert FE.modulo("figado_lesoes") is FL
    for nome in ("FERRAMENTA", "TITULO", "MIN_CORTES", "MODALIDADES", "CHAVE_SAIDA", "CHAVE_AUTO",
                 "CHAVE_DESTINOS", "NOME_CADIA", "TITULO_CADIA", "EXPLICACAO_CADIA", "config", "exame_serve",
                 "escolher_serie", "ja_feita", "tarefas", "calcular", "gravar", "resumo", "n_itens",
                 "mensagem", "frase"):
        assert hasattr(FL, nome), nome
    paths, db, repo = env
    hu = _hu()
    t = _T(hu)
    res = FL.calcular(t, _rotulos(hu, FL.tarefas("CT")))
    t.study_uid = "9.9"
    res.seg_mask = None
    out = FL.gravar(t, res, "v", db, paths.storage, repo=repo)
    a = repo.achados("9.9", "figado_lesoes")
    assert len(out["achados"]) == 3 and all(x["estado"] == "sugerido" for x in a)
    assert AC.texto_do_laudo(a, FL.frase) == ""
    assert FL.exame_serve({"modalities": "CT", "description": "TC ABDOME TOTAL"})
    assert FL.exame_serve({"modalities": "MR", "description": "RM FIGADO"})
    assert not FL.exame_serve({"modalities": "CT", "description": "TC CRANIO"})


def test_tela(env, tmp_path, monkeypatch):
    import time

    from pydicom.uid import generate_uid
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    hu = _hu()
    pat = {"name": "ABDOME^Figado", "id": "FIG1", "birth": "19500101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20261106", "accession": "FIG01", "description": "TC ABDOME",
             "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 3, "description": "AX PORTAL"}
    pasta = tmp_path / "fig"
    for k in range(NZ):
        ds = _base("1.2.840.10008.5.1.4.1.1.2", pat, study, series, "CT")
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [0, 0, DZ * k]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [PX, PX]
        ds.SliceThickness = DZ
        ds.RescaleSlope, ds.RescaleIntercept = 1, 0
        _mono(ds, hu[k], signed=True)
        _save(ds, pasta)
    Importer(db, paths.storage).import_paths([pasta])
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
        assert "figado_lesoes.auto" in tab.actions_by_id
        vp = next(v for v in tab.viewports if v.frames)
        tab.ferramenta_ia("figado_lesoes", vp, simular=True)
        fim = time.time() + 120
        while not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert avisos and avisos[-1].startswith("Lesões hepáticas prontas"), avisos
        assert FL.ja_feita(repo, study["uid"])
        ach = repo.achados(study["uid"], "figado_lesoes")
        assert len(ach) == 3
        seg = [o for o in tab.overlay_objects if o.source == "SEG" and "Lesões hepáticas" in (o.label or "")]
        assert seg and all(o.so_series == series["uid"] for o in seg)
        from ipe.imaging import overlays as O
        assert any(O.volumes_derivados(o) for o in seg)         # vai ao 3D (Estruturas)
        tab._activate(vp)
        v3 = tab.open_3d("vr")
        assert v3 is not None and v3.ha_estruturas()
        assert v3.mostrar_estruturas(True) == "" and v3.estruturas
        assert v3.image().is_color
    finally:
        w.close()
