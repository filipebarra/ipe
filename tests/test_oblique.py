"""MPR oblíquo no programa."""
import numpy as np
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.imaging.series import FrameCache, build_frames
from ipe.imaging.volume import MPRPlane, ObliquePlane, VolumeError, build_volume, sample_trilinear
from ipe.importer.scanner import Importer


def _vol(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    uid = repo.find_study_uids(accession="ACC1001")[0]
    s = repo.series_for_study(uid)[0]
    return build_volume(build_frames(repo.instances_for_series(s.series_uid), s.series_uid), FrameCache(512))


def test_trilinear_matches_voxels():
    d = np.arange(4 * 5 * 6, dtype=np.int16).reshape(4, 5, 6)
    pts = np.array([[1, 2, 3], [0.5, 2, 3], [9, 0, 0]], dtype=np.float32)
    out = sample_trilinear(d, pts)
    assert out[0] == d[3, 2, 1] and abs(out[1] - (d[3, 2, 0] + d[3, 2, 1]) / 2) < 1e-4
    assert np.isnan(out[2])


def test_oblique_plane_geometry(env, sample_dir):
    vol = _vol(env, sample_dir)
    ax = MPRPlane(vol, 0)
    k = 30
    z = ax.position(k)[2]
    # linha horizontal (esquerda-direita) num corte axial -> plano coronal
    p0, p1 = np.array([-100, 10, z]), np.array([100, 10, z])
    ob = ObliquePlane(vol, p0, p1, ax.normal)
    assert np.allclose(ob.orientation, [1, 0, 0, 0, 0, -1], atol=1e-6)
    assert ob.name == "Oblíquo" and ob.index_for_point(p0) == ob.idx0
    img = ob.image(ob.idx0).pixels
    co = MPRPlane(vol, 1)
    ref = co.image(co.index_for_point(p0)).pixels
    # mesmo ponto nos dois: centro do volume no plano
    c = vol.voxel_to_patient(vol.shape[2] / 2, 0, vol.shape[0] / 2)
    c[1] = 10
    def pix(pl, idx, p):
        d = p - pl.position(idx)
        return int(round(d @ pl.orientation[3:] / pl.row_spacing)), int(round(d @ pl.orientation[:3] / pl.col_spacing))
    r1, c1 = pix(ob, ob.idx0, c)
    r2, c2 = pix(co, co.index_for_point(p0), c)
    assert abs(float(img[r1, c1]) - float(ref[r2, c2])) < 60
    # linha a 45°: normal no plano axial, diagonal
    ob2 = ObliquePlane(vol, np.array([-50, -50, z]), np.array([50, 50, z]), ax.normal)
    assert abs(abs(ob2.normal[0]) - abs(ob2.normal[1])) < 1e-6 and abs(ob2.normal[2]) < 1e-6
    thin = ob2.image(ob2.idx0).pixels
    ob2.set_slab(10, "mip")
    thick = ob2.image(ob2.idx0).pixels
    assert (thick >= thin - 1e-3).all() and thick.max() >= thin.max()
    with pytest.raises(VolumeError):
        ObliquePlane(vol, p0, p0, ax.normal)


def test_oblique_in_viewer(env, sample_dir):
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    Importer(db, paths.storage).import_paths([sample_dir])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1200, 800)
    w.show()
    w.browser.refresh()
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 1)
    app.processEvents()
    a = tab.viewports[0]
    tab._activate(a)
    tab.set_left_tool("oblique")
    app.processEvents()
    c = a.rect().center()
    QTest.mousePress(a, Qt.LeftButton, Qt.NoModifier, c - QPoint(80, 40))
    QTest.mouseMove(a, c)
    QTest.mouseMove(a, c + QPoint(80, 40))
    QTest.mouseRelease(a, Qt.LeftButton, Qt.NoModifier, c + QPoint(80, 40))
    app.processEvents()
    assert tab._layout == (1, 2)
    b = tab.viewports[1]
    assert b.mpr_plane is not None and b.mpr_plane.name == "Oblíquo"
    assert a.oblique_targets == [b] and "Oblíquo" in b.series_label
    assert b._img is not None and b._img.pixels.size > 0
    # rolar o oblíquo e salvar como série
    b.step(3)
    res = tab.save_reconstruction(b)
    assert res is not None and len(res[1]) == b.mpr_plane.n
    # nova linha no mesmo quadro reaproveita o quadro do oblíquo
    old_axis = b.mpr_plane.axis
    assert tab.create_oblique(a, a.pixel_to_patient(10, 100), a.pixel_to_patient(200, 120))
    assert tab.viewports[1] is b and b.mpr_plane.axis != old_axis
    b.sig.reconstruction_save_requested.emit(b, True)
    assert any(len(v[1]) == 1 for k, v in tab._derived.items() if len(k) == 5)
    one = tab._film_item(b)
    assert one is not None and one["index"] == 0
    w.close()


# ------------------------------------------- oblíquo a partir do plano que está na tela
def test_obliquo_do_plano_atual_nao_muda_a_imagem(env, sample_dir):
    """"Se estiver em axial, mude para oblíquo mantendo a mesma posição e imagem."

    O oblíquo que existia nascia de uma linha desenhada e saía **perpendicular** ao que estava na
    tela — o contrário do pedido.
    """
    vol = _vol(env, sample_dir)
    axial = MPRPlane(vol, 0)
    centro = axial.position(axial.n // 2)
    obl = ObliquePlane.do_plano(vol, axial.orientation[:3], axial.orientation[3:], centro)
    assert obl.name == "Oblíquo"
    assert np.allclose(np.abs(obl.normal), np.abs(axial.normal), atol=1e-6), "a normal tem que ser a mesma"
    a = axial.image(axial.n // 2).pixels
    b = obl.image(obl.index_for_point(centro)).pixels
    # mesma anatomia: a correlação entre as duas imagens, reamostradas no mesmo tamanho, é alta
    lado = min(a.shape[0], a.shape[1], b.shape[0], b.shape[1], 64)
    ra = a[:lado, :lado].ravel()
    rb = b[:lado, :lado].ravel()
    assert float(np.corrcoef(ra, rb)[0, 1]) > 0.5


def test_girar_o_plano_inclina_o_que_foi_pedido(env, sample_dir):
    vol = _vol(env, sample_dir)
    axial = MPRPlane(vol, 0)
    centro = axial.position(axial.n // 2)
    obl = ObliquePlane.do_plano(vol, axial.orientation[:3], axial.orientation[3:], centro)
    for graus in (5.0, 15.0, 30.0):
        novo = obl.girar(graus, 0.0, centro)
        ang = np.degrees(np.arccos(np.clip(abs(float(obl.normal @ novo.normal)), -1, 1)))
        assert abs(ang - graus) < 0.5, f"pedi {graus}° e girou {ang:.1f}°"
    # girar nos dois eixos e voltar devolve o plano de origem
    ida = obl.girar(12.0, -7.0, centro)
    volta = ida.girar(-12.0, 7.0, centro)
    assert np.degrees(np.arccos(np.clip(abs(float(obl.normal @ volta.normal)), -1, 1))) < 2.0


def test_o_canto_mostra_plano_fase_janela_e_fov(env, sample_dir):
    """As quatro linhas do canto inferior direito, nesta ordem."""
    from ipe.ui.main_window import MainWindow
    from ipe.importer.scanner import Importer as Imp
    paths, db, repo = env
    Imp(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1200, 800)
    w.show()
    w.browser.refresh()
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    vp = tab.active
    textos = [t for t, _h in vp._text_lines()["br"]]
    hots = [h for _t, h in vp._text_lines()["br"]]
    assert hots[0] == "plano" and textos[0].startswith(vp.plano_nome())
    assert "W " in textos[-2] and textos[-1].startswith("FOV")
    assert "fase" not in hots, "sem dinâmica, a linha da fase não aparece"
    # com dinâmica, a fase entra em segundo lugar
    vp.phases = [vp.frames, vp.frames]
    vp.phase_labels = ["a", "b"]
    linhas = vp._text_lines()["br"]
    assert [h for _t, h in linhas][:2] == ["plano", "fase"]
    assert linhas[1][0].startswith("Fase 1/2")
    w.close()


def test_a_fase_anda_nos_dois_sentidos_pelo_canto(env, sample_dir):
    """Esquerdo vai para a próxima, direito volta — foi o que ele pediu."""
    from ipe.ui.main_window import MainWindow
    from ipe.importer.scanner import Importer as Imp
    from ipe.ui.viewer.viewport import HOTSPOTS_DOS_DOIS_BOTOES
    paths, db, repo = env
    Imp(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    w.browser.refresh()
    w.handle_external({"accession": "ACC1001"})
    vp = w.tabs.currentWidget().active
    vp.phases = [vp.frames] * 4
    vp.phase_labels = ["a", "b", "c", "d"]
    vp.phase = 0
    assert "fase" in HOTSPOTS_DOS_DOIS_BOTOES
    vp._click_hotspot("fase", None, "left")
    assert vp.phase == 1
    vp._click_hotspot("fase", None, "right")
    assert vp.phase == 0
    vp._click_hotspot("fase", None, "right")
    assert vp.phase == 3, "antes da primeira, volta para a última"
    w.close()


def test_plano_muito_inclinado_se_chama_obliquo():
    """Chamar de "axial" um plano inclinado 30° é mentir no rótulo."""
    from ipe.imaging.series import Frame
    from ipe.ui.viewer.viewport import Viewport
    vp = Viewport.__new__(Viewport)
    vp.mpr_plane = None
    ang = np.radians(30.0)
    vp.frames = [Frame(path="/x", frame_index=0, sop_uid="s", instance_number=0,
                       position=np.zeros(3),
                       orientation=np.array([1., 0, 0, 0, np.cos(ang), np.sin(ang)]))]
    vp.index = 0
    assert vp.plano_nome() == "Oblíquo"
    vp.frames[0].orientation = np.array([1., 0, 0, 0, 1, 0])
    assert vp.plano_nome() == "Axial"


def test_a_linha_de_orientacao_nao_mostra_o_nome_do_mapa():
    """Mapa paramétrico e MPR curvo também moram em `mpr_plane`.

    O `name` deles é o nome do **conteúdo** ("Cinética", "MPR curvo"), não um plano — e a linha
    do canto é de orientação. Mostrava "Cinética  ▾" onde devia estar "Axial  ▾".
    """
    from types import SimpleNamespace
    from ipe.imaging.series import Frame
    from ipe.ui.viewer.viewport import Viewport
    vp = Viewport.__new__(Viewport)
    vp.frames = [Frame(path="/x", frame_index=0, sop_uid="s", instance_number=0,
                       position=np.zeros(3), orientation=np.array([1., 0, 0, 0, 1, 0]))]
    vp.index = 0
    vp.mpr_plane = SimpleNamespace(name="Cinética")      # não é um plano de reconstrução
    assert vp.plano_nome() == "Axial"
