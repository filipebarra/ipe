"""MPR, sincronização, imagens-chave, preferências e multimonitor."""
import numpy as np
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.imaging.series import FrameCache, build_frames
from ipe.imaging.volume import MPRPlane, VolumeError, build_volume
from ipe.importer.scanner import Importer



def _sem_protocolos(s):
    """Estes testes conferem o layout e a sincronia **sem** protocolo de exibição. Desde a 0.88 a TC
    de tórax tem protocolo de fábrica (com coronal e grupos de sincronia próprios), então ele fica
    desligado aqui."""
    from ipe.ui.viewer import hanging as H
    s.set("hanging_protocols", [dict(p, enabled=False) for p in H.DEFAULT_PROTOCOLS])
    s.set("hanging_fabrica", H.FABRICA_VERSAO)
    return s

@pytest.fixture()
def loaded(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    return paths, db, repo


def _ct_frames(repo, acc="ACC1001"):
    uid = repo.find_study_uids(accession=acc)[0]
    s = repo.series_for_study(uid)[0]
    return build_frames(repo.instances_for_series(s.series_uid), s.series_uid)


def test_volume_geometry_and_planes(loaded):
    _, _, repo = loaded
    vol = build_volume(_ct_frames(repo), FrameCache(512))
    assert vol.shape == (60, 256, 256)
    assert vol.data.dtype == np.int16                     # HU inteiros -> metade da memória
    assert vol.dx == vol.dy == 1.5 and abs(vol.dz - 3.0) < 1e-6
    p = vol.voxel_to_patient(10, 20, 30)
    assert np.allclose(p, [-192 + 15, -192 + 30, -90 + 90])
    assert np.allclose(vol.patient_to_voxel(p), [10, 20, 30])
    ax, co, sa = (MPRPlane(vol, a) for a in (0, 1, 2))
    assert (ax.name, co.name, sa.name) == ("Axial", "Coronal", "Sagital")
    # coronal: superior em cima (linhas vão para inferior), direita do paciente à esquerda
    assert np.allclose(co.orientation, [1, 0, 0, 0, 0, -1])
    assert np.allclose(sa.orientation, [0, 1, 0, 0, 0, -1])
    img = co.image(128)
    assert img.pixels.shape == (60, 256)
    assert img.pixel_spacing == (3.0, 1.5)
    # ponto -> índice do plano e volta
    assert co.index_for_point(vol.voxel_to_patient(0, 77, 0)) == 77
    # o topo do coronal é o corte mais superior (k = 59)
    assert np.isclose(co.position(0)[2], -90 + 3 * 59)


def test_slab_modes(loaded):
    _, _, repo = loaded
    vol = build_volume(_ct_frames(repo), FrameCache(512))
    pl = MPRPlane(vol, 0)
    thin = pl.image(30).pixels
    pl.set_slab(20, "mip")
    mip = pl.image(30).pixels
    pl.set_slab(20, "minip")
    minip = pl.image(30).pixels
    assert (mip >= thin - 1e-3).all() and (minip <= thin + 1e-3).all()
    assert mip.mean() > minip.mean()


def test_volume_rejects_single_images(loaded):
    _, _, repo = loaded
    uid = repo.find_study_uids(accession="ACC3001")[0]
    s = repo.series_for_study(uid)[0]
    with pytest.raises(VolumeError):
        build_volume(build_frames(repo.instances_for_series(s.series_uid)), FrameCache(64))


def _window(loaded):
    paths, _, _ = loaded
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, _sem_protocolos(Settings(paths.settings_file)))
    w.resize(1400, 800)
    w.show()
    w.browser.refresh()
    return app, w


def test_mpr_cursor_moves_other_planes(loaded):
    app, w = _window(loaded)
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    tab.mpr_action.setChecked(True)
    app.processEvents()
    assert tab.mpr_active
    ax, co, sa = tab.viewports[:3]
    assert [len(v.ref_planes) for v in (ax, co, sa)] == [2, 2, 2]
    pt = ax.image_to_widget(QPointF(179, 115)).toPoint()
    QTest.mouseClick(ax, Qt.LeftButton, Qt.NoModifier, pt)
    assert abs(co.index - 115) <= 1 and abs(sa.index - 179) <= 1
    tab.slab_combo.setCurrentIndex(3)          # 10 mm
    assert co.mpr_plane.slab_mm == 10
    tab.mpr_action.setChecked(False)
    assert not tab.mpr_active and tab._layout == (1, 1)
    w.close()


def test_link_with_prior_keeps_offset(loaded):
    app, w = _window(loaded)
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    prior = w.repo.find_study_uids(accession="ACC0901")[0]
    tab.add_study(prior)
    a, b = tab._shown()[:2]
    assert b.study_uid == prior and a.for_uid != b.for_uid
    a.go_to(20)
    b.go_to(24)
    # sem ligar: exames diferentes não andam juntos
    a.step(2)
    assert b.index == 24
    tab.escolher_modo_sync("manual")
    a.step(5)
    assert (a.index, b.index) == (27, 29)       # mantém a diferença do momento da ligação (2)
    tab.link_action.setChecked(False)
    a.step(1)
    assert b.index == 29
    w.close()


def test_key_images(loaded):
    app, w = _window(loaded)
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    vp = tab.active
    vp.go_to(10)
    tab.toggle_key_image()
    vp.go_to(40)
    tab.toggle_key_image()
    study = tab.study_uid
    assert len(w.repo.key_images(study)) == 2
    tab.show_key_images()
    assert vp.series_uid == f"key:{study}" and len(vp.frames) == 2
    # estudo com imagem-chave fica protegido
    with pytest.raises(PermissionError):
        w.repo.delete_study(study, w.paths.storage)
    vp.go_to(0)
    tab.toggle_key_image()                      # desmarca
    assert len(w.repo.key_images(study)) == 1
    w.close()


def test_preferences_shortcut_applied(loaded):
    app, w = _window(loaded)
    w.settings.set("shortcuts", {"key.toggle": "J"})
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    assert tab.actions_by_id["key.toggle"].shortcut().toString() == "J"
    # Ação que ele não configurou fica **sem** tecla desde a 0.65 (a lista de fábrica foi zerada);
    # as três que sobraram continuam valendo.
    assert tab.actions_by_id["view.invert"].shortcut().toString() == ""
    assert tab.actions_by_id["mg.next"].shortcut().toString() == "Right"
    assert tab.actions_by_id["mg.prev"].shortcut().toString() == "Left"
    assert tab.actions_by_id["mg.quad_next"].shortcut().toString() == "Q"
    w.close()


def test_detach_and_reattach(loaded):
    app, w = _window(loaded)
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    n = w.tabs.count()
    w.detach_tab(tab)
    assert w.tabs.count() == n - 1 and len(w.detached) == 1
    w.detached[0].devolver_estudos()         # pelo menu: devolve as abas
    assert w.tabs.count() == n and not w.detached
    # já o X fecha o exame: é gesto diferente, e deliberadamente
    w.detach_tab(w.tabs.currentWidget())
    w.detached[0].close()
    app.processEvents()
    assert not w.detached and not w.all_viewer_tabs()
    w.close()


def test_single_plane_reconstruction(env, sample_dir):
    """Reconstrução num plano só, no quadro ativo; o outro quadro continua com a série original."""
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    Importer(db, paths.storage).import_paths([sample_dir])
    w = MainWindow(paths, _sem_protocolos(Settings(paths.settings_file)))
    w.show()
    w.browser.refresh()
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 2)
    app.processEvents()
    a, b = tab.viewports[0], tab.viewports[1]
    tab.load_series_into(b, a.series_uid)
    orig = a.series_uid
    tab._activate(a)
    assert tab.reconstruct_plane("Coronal")
    assert a.mpr_plane is not None and a.mpr_plane.name == "Coronal" and a.series_uid.startswith("mpr:")
    assert b.series_uid == orig and b.mpr_plane is None
    assert tab.mpr_bar.isVisibleTo(tab) and not tab.mpr_active
    assert len(a.frames) == a.mpr_plane.n and "Coronal" in a.series_label
    # trocar de plano no mesmo quadro reaproveita o volume
    assert tab.reconstruct_plane("Sagital") and a.mpr_plane.name == "Sagital"
    tab._plane_back()
    app.processEvents()
    assert a.series_uid == orig and a.mpr_plane is None and not tab.mpr_bar.isVisibleTo(tab)
    w.close()


def test_trocar_de_serie_mantem_a_posicao(loaded):
    """"Quando eu mudo de sequência, quero que mantenha a posição."

    Antes ia para o meio da série nova. O contrato é o corte da série nova **passar pelo ponto**
    que estava à vista — inclusive quando a série nova é de outro plano, e aí o ponto não fica no
    meio da imagem, mas está dentro dela.
    """
    app, w = _window(loaded)
    w.handle_external({"accession": "ACC2001"})            # RM com várias séries
    tab = w.tabs.currentWidget()
    vp = tab.active
    uids = [s.series_uid for s in tab.series if s.study_uid == tab.study_uid and s.num_images >= 3]
    assert len(uids) >= 2, "o fantoma precisa de duas séries com 3+ cortes"
    tab.load_series_into(vp, uids[0])
    vp.go_to(2)
    antes = vp.ponto_central()
    assert antes is not None
    tab.load_series_into(vp, uids[1])
    assert vp.index != len(vp.frames) // 2, "não pode cair no meio da série nova"
    _u, _v, dist = vp.patient_to_pixel(antes)
    assert abs(dist) <= 3.0, f"o corte escolhido está a {dist:.1f} mm do ponto que estava à vista"


def test_sem_geometria_comparavel_entra_pela_fracao():
    """Séries de exames diferentes não têm milímetros comparáveis: resta a posição proporcional."""
    import numpy as np
    from ipe.imaging.series import Frame, quadro_na_posicao
    frames = [Frame(path=f"/x/{i}", frame_index=0, sop_uid=str(i), instance_number=i,
                    position=np.array([0.0, 0.0, i * 2.0]),
                    orientation=np.array([1., 0, 0, 0, 1, 0])) for i in range(101)]
    assert quadro_na_posicao(frames, None, 0.25) == 25
    assert quadro_na_posicao(frames, None, 0.0) == 0
    assert quadro_na_posicao(frames, None, 1.0) == 100
    assert quadro_na_posicao([], None, 0.5) == 0


def test_a_posicao_manda_sobre_a_fracao():
    """Com milímetros na mão, a fração não decide nada — é esse o ponto do pedido."""
    import numpy as np
    from ipe.imaging.series import Frame, quadro_na_posicao
    nova = [Frame(path=f"/y/{i}", frame_index=0, sop_uid=str(i), instance_number=i,
                  position=np.array([0.0, 0.0, 100.0 + i * 1.0]),
                  orientation=np.array([1., 0, 0, 0, 1, 0])) for i in range(201)]
    # estava em z = 150 mm, numa série que ia de 0 a 200: fração 0,75
    assert quadro_na_posicao(nova, np.array([0.0, 0.0, 150.0]), 0.75) == 50
    # e a fração sozinha levaria ao corte 150 — 100 mm fora do lugar
    assert quadro_na_posicao(nova, None, 0.75) == 150


def test_quadro_sem_posicao_na_serie_nova_cai_na_fracao():
    import numpy as np
    from ipe.imaging.series import Frame, quadro_na_posicao
    nova = [Frame(path=f"/z/{i}", frame_index=0, sop_uid=str(i), instance_number=i)
            for i in range(11)]
    assert quadro_na_posicao(nova, np.array([0.0, 0.0, 10.0]), 0.2) == 2
