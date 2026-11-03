"""0.99.40 (plano AW F2): estruturas editáveis — pincel, morfologia, ilhas, interpolação, SEG e RTSTRUCT."""
import json

import numpy as np
import pydicom
import pytest
from pydicom.uid import generate_uid

from ipe.imaging import estruturas as ES
from ipe.imaging import overlays as O
from ipe.imaging.volume import Volume


def _vol(nz=20, n=64, dz=2.0, dxy=1.0):
    z, y, x = np.mgrid[0:nz, 0:n, 0:n]
    d = np.zeros((nz, n, n), np.float32)
    d[((x - n / 2) / 12) ** 2 + ((y - n / 2) / 12) ** 2 + ((z - nz / 2) / 5) ** 2 < 1] = 100
    return Volume(d, np.array([-10.0, -20.0, 5.0]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
                  np.array([0, 0, dz]), dxy, dxy, None, "")


def test_pincel_disco_esfera_faixa_e_travada():
    v = _vol()
    g = ES.Grade.do_volume(v)
    c = g.para_mm([32, 32, 10])[0]
    e = ES.Estrutura("a", (255, 0, 0))
    n = ES.pintar(e, g, c, 5.0, normal=[0, 0, 1])
    assert n == e.voxels and 70 < n < 90                             # disco de 5 mm: π·25 ≈ 78 pixels
    assert len(np.flatnonzero(e.mascara.any(axis=(1, 2)))) == 1      # um corte só
    b = ES.Estrutura("b", (0, 255, 0))
    ES.pintar(b, g, c, 5.0)                                          # esfera: 5 cortes (dz 2 mm)
    assert len(np.flatnonzero(b.mascara.any(axis=(1, 2)))) == 5
    f = ES.Estrutura("f", (0, 0, 255))
    ES.pintar(f, g, c, 20.0, normal=[0, 0, 1], dados=v.data, faixa=(50, 150))
    assert f.voxels and v.data[f.caixa()][f.mascara].min() == 100    # não saiu da "lesão"
    a2 = ES.Estrutura("a2", (1, 1, 1))
    e.travada = True
    ES.pintar(a2, g, c, 8.0, normal=[0, 0, 1], proibidas=[e])
    assert not (a2.cheia(g) & e.cheia(g)).any()                      # não pinta por cima da travada
    assert ES.pintar(e, g, c, 8.0, normal=[0, 0, 1]) == 0            # a travada não muda
    e.travada = False
    assert ES.pintar(e, g, c, 3.0, normal=[0, 0, 1], apagar=True) > 0


def test_crescer_encolher_ilhas_buracos_interpolar_e_desfazer():
    v = _vol()
    g = ES.Grade.do_volume(v)
    e = ES.Estrutura("a", (255, 0, 0))
    ES.pintar(e, g, g.para_mm([32, 32, 10])[0], 6.0)
    base = e.cheia(g)
    e.guardar_para_desfazer()
    assert ES.crescer(e, g, 3.0) > 0
    ES.crescer(e, g, -3.0)
    assert np.array_equal(e.cheia(g) & base, base)                   # fechar não perde nada
    assert e.desfazer() and not e.desfazer() and np.array_equal(e.cheia(g), base)
    # ilhas
    ES.pintar(e, g, g.para_mm([5, 5, 2])[0], 2.0)
    assert len(ES.ilhas(e, g)) == 2
    assert ES.limpar_ilhas(e, g, so_a_maior=True) == 1 and len(ES.ilhas(e, g)) == 1
    # buracos
    anel = np.zeros((1, 20, 20), bool)
    anel[0, 3:17, 3:17] = True
    anel[0, 7:13, 7:13] = False
    r = ES.Estrutura("r", (1, 1, 1))
    r.definir(anel, (3, 10, 10))
    assert ES.preencher_buracos(r) == 36
    # interpolação entre os cortes 2 e 10
    t = ES.Estrutura("t", (1, 1, 1))
    ES.pintar(t, g, g.para_mm([32, 32, 2])[0], 4.0, normal=[0, 0, 1])
    ES.pintar(t, g, g.para_mm([32, 32, 10])[0], 8.0, normal=[0, 0, 1])
    assert ES.interpolar(t, g) == 7
    areas = [int(t.cheia(g)[k].sum()) for k in range(2, 11)]
    assert all(a <= b for a, b in zip(areas, areas[1:])) and areas[0] < areas[4] < areas[-1]   # de um disco ao outro
    # desfazer / refazer
    t.guardar_para_desfazer()
    antes = t.voxels
    ES.crescer(t, g, 2.0)
    assert t.voxels > antes and t.desfazer() and t.voxels == antes and t.refazer() and t.voxels > antes


def test_combinar_e_importar_de_outra_grade():
    v = _vol()
    g = ES.Grade.do_volume(v)
    a, b = ES.Estrutura("a", (1, 1, 1)), ES.Estrutura("b", (2, 2, 2))
    ES.pintar(a, g, g.para_mm([28, 32, 10])[0], 6.0)
    ES.pintar(b, g, g.para_mm([36, 32, 10])[0], 6.0)
    u = ES.combinar(a, b, g, "uniao")
    s = ES.combinar(a, b, g, "subtracao")
    i = ES.combinar(a, b, g, "intersecao")
    assert u.voxels == s.voxels + b.voxels and i.voxels == a.voxels - s.voxels and i.voxels > 0
    # a máscara de uma lesão guardada (em mm) volta exatamente na mesma grade
    mv = a.mask_volume(g)
    volta = ES.de_mask_volume(mv, g, "volta")
    assert np.array_equal(volta.cheia(g), a.cheia(g))
    # numa grade mais fina (metade do passo no plano) o volume em mL se mantém
    fina = ES.Grade(g.forma[:1] + (128, 128), g.origem, np.diag([0.5, 0.5, 2.0]))
    f = ES.de_mask_volume(mv, fina, "fina")
    assert abs(f.ml(fina) - a.ml(g)) / a.ml(g) < 0.12


def test_contornos_reproduzem_a_mascara():
    from ipe.imaging.rtstruct_writer import contornos_do_corte
    rng = np.random.default_rng(1)
    m = np.zeros((30, 30), bool)
    m[5:25, 5:25] = True
    m[10:15, 10:15] = False                         # buraco
    m[27, 27] = True                                # ilha de um pixel
    m[3, 3] = m[4, 4] = True                        # dois pixels que se tocam só no canto
    m |= rng.random((30, 30)) > 0.97
    polis = contornos_do_corte(m)
    ys, xs = np.mgrid[0:30, 0:30] + 0.5             # centros dos pixels nas coordenadas dos cantos
    cheio = np.zeros_like(m)
    for p in polis:
        cheio ^= O._dentro_do_poligono(xs, ys, p)
    assert np.array_equal(cheio, m)


@pytest.fixture
def exame(env, tmp_path):
    """Uma série de RM de 20 cortes no banco; devolve (paths, db, repo, study, série, volume)."""
    from ipe.importer.scanner import Importer
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from test_registro_rigido import _serie
    paths, db, repo = env
    v = _vol()
    estudo = generate_uid()
    serie = _serie(tmp_path / "a", v, estudo, generate_uid(), "Ax T1 POS", "20261101")
    Importer(db, paths.storage).import_paths([tmp_path / "a"])
    return paths, db, repo, estudo, serie, v


def _volume_do_banco(repo, serie):
    from ipe.imaging.series import FrameCache, build_frames
    from ipe.imaging.volume import build_volume
    frames = build_frames(repo.instances_for_series(serie), serie)
    return build_volume(frames, FrameCache(64)), frames


def test_seg_e_rtstruct_ida_e_volta(exame, tmp_path):
    from types import SimpleNamespace
    from ipe.imaging.rtstruct_writer import build_rtstruct
    from ipe.imaging.seg_writer import build_seg
    _paths, _db, repo, _estudo, serie, _v = exame
    vol, frames = _volume_do_banco(repo, serie)
    g = ES.Grade.do_volume(vol)
    les = ES.Estrutura("Tumor", (255, 80, 80), tipo="lesão")
    ES.pintar(les, g, g.para_mm([32, 32, 10])[0], 7.0)
    org = ES.Estrutura("Fígado", (80, 200, 80), tipo="órgão")
    ES.pintar(org, g, g.para_mm([20, 20, 6])[0], 5.0)
    ES.pintar(les, g, g.para_mm([32, 32, 10])[0], 3.0, normal=[0, 0, 1], apagar=True)   # necrose central
    # SEG
    segs = [(SimpleNamespace(mask=e.mascara, offset=e.offset), e.nome, e.cor, e.tipo) for e in (les, org)]
    ds = build_seg(vol, segs, vol.source_path, frames)
    ds.save_as(tmp_path / "s.dcm", enforce_file_format=True)
    lido = O.parse_seg(pydicom.dcmread(tmp_path / "s.dcm"))
    tipos = [str(s.SegmentedPropertyTypeCodeSequence[0].CodeMeaning) for s in ds.SegmentSequence]
    assert tipos == ["Mass", "Organ"]
    vols = {mv.label: mv for mv in O.volumes_das_mascaras(lido.masks)}
    for e in (les, org):
        assert np.array_equal(ES.de_mask_volume(vols[e.nome], g).cheia(g), e.cheia(g))
    # RTSTRUCT
    rt = build_rtstruct(vol, [les, org], vol.source_path, frames)
    rt.save_as(tmp_path / "r.dcm", enforce_file_format=True)
    rd = pydicom.dcmread(tmp_path / "r.dcm")
    assert rd.Modality == "RTSTRUCT" and [r.ROIName for r in rd.StructureSetROISequence] == ["Tumor", "Fígado"]
    assert [o.RTROIInterpretedType for o in rd.RTROIObservationsSequence] == ["GTV", "ORGAN"]
    c0 = rd.ROIContourSequence[0].ContourSequence[0]
    assert c0.ContourImageSequence[0].ReferencedSOPInstanceUID in {f.sop_uid for f in frames}
    obj = O.parse_rtstruct(rd)
    for mv in O.volumes_dos_contornos(obj.planar, passo=0.5):
        e = les if mv.label == "Tumor" else org
        volta = ES.de_mask_volume(mv, g)
        inter = (volta.cheia(g) & e.cheia(g)).sum()
        assert inter / (volta.cheia(g) | e.cheia(g)).sum() > 0.9     # o buraco também volta (par-ímpar)


def test_painel_pinta_corrige_grava_e_atualiza_a_lesao(exame, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    paths, db, repo, estudo, serie, v = exame
    # uma lesão guardada (como a ferramenta Segmentar grava), para editar aqui
    vol, frames = _volume_do_banco(repo, serie)
    g = ES.Grade.do_volume(vol)
    les = ES.Estrutura("Nódulo", (255, 120, 90))
    ES.pintar(les, g, g.para_mm([32, 32, 10])[0], 4.0)
    meta = {"ml": round(les.ml(g), 3), "mascara3d": les.mask_volume(g).para_meta(), "cor": [255, 120, 90],
            "method": "range"}
    f = frames[10]
    db_id = repo.save_annotation(db_id=None, study_uid=estudo, series_uid=serie, sop_uid=f.sop_uid,
                                 frame_index=0, kind="seg",
                                 data=json.dumps({"text": "Nódulo", "points": [[32, 32]], "meta": meta}))
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        w.open_study(estudo)
        QApplication.processEvents()
        tab = next(iter(w.all_viewer_tabs()))
        vp = next(x for x in tab.viewports if x.study_uid == estudo)
        tab._activate(vp)
        tab.load_overlay_objects()
        assert any(o.key == f"segann:{db_id}" for o in tab.overlay_objects)
        painel = tab.abrir_estruturas(vp)
        assert painel.grade is not None and painel.obj in tab.overlay_objects
        # importar a lesão guardada: o original sai da tela enquanto é editado
        cand = [c for c in painel.candidatos() if c[0].key == f"segann:{db_id}"]
        assert cand
        e = painel.importar(cand[0][0], cand[0][1])
        assert e.tipo == "lesão" and abs(e.ml(painel.grade) - les.ml(g)) < 1e-6
        assert not cand[0][0].enabled
        # pincel pelo quadro (o sinal do quadro passa pela aba)
        vp.go_to(10)
        painel.b_pincel.setChecked(True)
        assert tab.left_tool == "pincel" and vp.pincel_raio_mm == 5.0
        antes = e.voxels
        vp.sig.pincel.emit(vp, 32.5, 22.5, "ini")
        vp.sig.pincel.emit(vp, 32.5, 18.5, "meio")
        vp.sig.pincel.emit(vp, 32.5, 18.5, "fim")
        assert e.voxels > antes and e.pode_desfazer()
        painel.desfazer()
        assert e.voxels == antes
        painel.refazer()
        # o mesmo traço com o mouse de verdade no quadro
        from PySide6.QtCore import QPoint, QPointF
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt as _Qt
        vp.resize(400, 400)
        a_ = vp.image_to_widget(QPointF(44.5, 44.5)).toPoint()
        b_ = vp.image_to_widget(QPointF(48.5, 44.5)).toPoint()
        n0 = e.voxels
        QTest.mousePress(vp, _Qt.LeftButton, _Qt.NoModifier, a_)
        QTest.mouseMove(vp, b_)
        QTest.mouseRelease(vp, _Qt.LeftButton, _Qt.NoModifier, b_)
        assert e.voxels > n0
        painel.desfazer()
        assert e.voxels == n0
        # crescer pelo botão (operação com desfazer)
        painel.s_mm.setValue(1.0)
        painel._crescer(+1)
        maior = e.voxels
        assert maior > antes
        # gravar SEG e RTSTRUCT no exame
        uid_seg = painel.gravar("SEG")
        uid_rt = painel.gravar("RTSTRUCT")
        mods = {s.series_uid: s.modality for s in repo.series_for_study(estudo)}
        assert mods.get(uid_seg) == "SEG" and mods.get(uid_rt) == "RTSTRUCT"
        # atualizar a lesão guardada: a medida passa a ter o volume novo
        assert painel.atualizar_lesao()
        rec = next(r for r in repo.annotations_for_studies([estudo]) if r["id"] == db_id)
        m2 = json.loads(rec["data"])["meta"]
        assert abs(m2["ml"] - maior * painel.grade.ml_por_voxel) < 1e-3 and m2["editada_em_estruturas"]
        assert ES.de_mask_volume(O.MaskVolume.da_meta(m2["mascara3d"], (1, 1, 1)), painel.grade).voxels == maior
        # fechar: nada pendente; o desenho sai e a lesão volta à tela
        painel.pincel(vp, 40.5, 40.5, "ini")
        painel.pincel(vp, 40.5, 40.5, "fim")
        assert painel.pendente()
        monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Discard))
        painel.close()
        assert painel.obj not in tab.overlay_objects and tab.left_tool != "pincel"
        assert next(o for o in tab.overlay_objects if o.key == f"segann:{db_id}").enabled
    finally:
        w._really_quit = True
        w.settings.set("ui.confirmar_sair", False)
        w.close()
