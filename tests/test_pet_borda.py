"""0.100.8: contorno do PET pela borda (gradiente, como o PET Edge), com a correção do volume parcial — esferas
borradas pela resolução do aparelho (FWHM 7 mm), com ruído que cresce com o sinal, contra o limiar de 41%."""
import numpy as np
import pytest

from ipe.imaging import pet_borda as PB
from ipe.imaging.segment import _grow

VOX = (3.0, 2.0, 2.0)
N = (48, 80, 80)


def _borrar(a, fwhm=7.0):
    out = a.astype(np.float64)
    for ax, v in enumerate(VOX):
        s = fwhm / 2.3548 / v
        f = np.fft.fftfreq(out.shape[ax])
        h = np.exp(-2 * (np.pi * f * s) ** 2).reshape([-1 if i == ax else 1 for i in range(3)])
        out = np.real(np.fft.ifft(np.fft.fft(out, axis=ax) * h, axis=ax))
    return out


def _dist(c):
    kk, jj, ii = np.meshgrid(*[np.arange(x) for x in N], indexing="ij")
    return np.sqrt(((kk - c[0]) * VOX[0]) ** 2 + ((jj - c[1]) * VOX[1]) ** 2 + ((ii - c[2]) * VOX[2]) ** 2)


def _esfera(diam, razao=6.0, ruido=0.10, semente=0):
    c = tuple(x // 2 for x in N)
    a = np.where(_dist(c) <= diam / 2, razao, 1.0)
    img = _borrar(a)
    rng = np.random.default_rng(semente)
    img += rng.normal(0, ruido * razao, img.shape) * np.sqrt(np.clip(img / razao, 0.05, None))
    return img.astype(np.float32), c, 4 / 3 * np.pi * (diam / 2) ** 3 / 1000


def _volume(img, c, fwhm=7.0):
    b = PB.achar_borda(img, c, VOX, fwhm_mm=fwhm)
    m, _ = PB.mascara(img, b, VOX)
    return m.sum() * np.prod(VOX) / 1000, b


def test_perfil_da_esfera_e_correcao():
    """A queda mais íngreme de uma esfera borrada fica para dentro da borda; a tabela leva de volta."""
    s = 7 / 2.3548
    r = np.linspace(0, 40, 8001)
    for raio in (5.0, 8.0, 15.0):
        g = np.gradient(PB.perfil_esfera(r, raio, s), r)
        medido = r[np.argmin(g)]
        assert medido < raio
        assert PB.corrigir_raios(np.array([medido]), s)[0] == pytest.approx(raio, abs=0.15)
    assert PB.perfil_esfera(np.array([0.0]), 30.0, s)[0] == pytest.approx(1.0, abs=1e-3)


@pytest.mark.parametrize("diam", [13, 17, 22, 37])
def test_volume_certo_com_ruido(diam):
    erros = []
    for semente in range(2):
        img, c, real = _esfera(diam, semente=semente)
        v, _ = _volume(img, c)
        erros.append(v / real - 1)
    assert abs(np.mean(erros)) < 0.15, erros


def test_melhor_que_41_por_cento_nas_pequenas():
    """Com fundo 4:1, o 41% do máximo infla a lesão pequena (o máximo cai pelo volume parcial, o limiar desce até o
    fundo borrado); a borda pelo gradiente não depende do pico."""
    for diam in (13, 17):
        img, c, real = _esfera(diam, razao=4.0)
        v, b = _volume(img, c)
        v41 = _grow(img >= 0.41 * img[b.centro], b.centro).sum() * np.prod(VOX) / 1000
        assert abs(v / real - 1) < 0.5 * abs(v41 / real - 1), (diam, v / real, v41 / real)


def test_resolucao_medida_na_lesao_grande():
    img, c, real = _esfera(37, ruido=0.03)
    v, b = _volume(img, c, fwhm=4.0)          # ajuste errado: a lesão grande mostra a resolução de verdade
    assert b.fwhm_da_lesao and 5.5 < b.fwhm_mm < 9.0
    assert v / real == pytest.approx(1, abs=0.08)


def test_nao_invade_a_vizinha_mais_quente():
    c1, c2 = (24, 40, 30), (24, 40, 52)
    a = np.ones(N)
    a[_dist(c1) <= 10] = 6
    a[_dist(c2) <= 15] = 15                   # 15:1, a 12 mm de distância
    img = _borrar(a).astype(np.float32)
    b = PB.achar_borda(img, c1, VOX)
    m, off = PB.mascara(img, b, VOX)
    cheio = np.zeros(N, bool)
    cheio[off[0]:off[0] + m.shape[0], off[1]:off[1] + m.shape[1], off[2]:off[2] + m.shape[2]] = m
    assert not (cheio & (_dist(c2) <= 15)).any()
    assert cheio.sum() * np.prod(VOX) / 1000 == pytest.approx(4 / 3 * np.pi * 1.0, rel=0.2)


def test_pelo_segment_com_aviso_na_pequena():
    from ipe.imaging.segment import METHODS, segment
    from ipe.imaging.volume import Volume
    assert "pet_grad" in METHODS
    img, c, real = _esfera(22)
    vol = Volume(data=img, origin=np.zeros(3), row_dir=np.array([1.0, 0, 0]), col_dir=np.array([0, 1.0, 0]),
                 slice_vec=np.array([0, 0, VOX[0]]), dx=VOX[2], dy=VOX[1], window=None, source_path="")
    r = segment(vol, (c[0], c[1] + 2, c[2]), "pet_grad", suv=2.0, fwhm_mm=7.0)
    assert r.ml == pytest.approx(real, rel=0.15)
    assert r.suvmax == pytest.approx(img.max() * 2.0, rel=0.05)
    assert any("resolução do PET 7.0 mm" in n for n in r.notes) and 0 < r.lo < img.max()
    pequena, c2, _ = _esfera(8, razao=8.0)
    vol.data = pequena
    r2 = segment(vol, c2, "pet_grad", suv=1.0, fwhm_mm=7.0)
    assert any("limite da resolução" in n for n in r2.notes)


def test_na_janela_de_segmentacao(env, tmp_path):
    """O método aparece para o PET, mostra o campo da resolução (e só nele) e guarda a resolução ajustada."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from test_pedidos_29_10 import _sem_protocolos
    from test_pet_onco import _gravar_pet
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    from ipe.ui.viewer.onco import SegmentDialog
    paths, db, repo = env
    _gravar_pet(tmp_path / "pet")
    Importer(db, paths.storage).import_paths([tmp_path / "pet"])
    app = QApplication.instance() or QApplication([])
    st = _sem_protocolos(Settings(paths.settings_file))
    w = MainWindow(paths, st)
    w.show()
    try:
        w.handle_external({"accession": "PET001"})
        tab = w.tabs.currentWidget()
        tab.set_layout(1, 1)
        app.processEvents()
        vp = tab.viewports[0]
        vol = tab._volume_for(vp, tab._source_series(vp))
        dlg = SegmentDialog(tab, vp, vol, (12, 20, 30), (0, 0), vp.frame_key())
        assert dlg.method.findData("pet_grad") >= 0
        assert dlg.fwhm.isHidden() or not dlg.fwhm.isVisible()
        dlg.fwhm.setValue(6.5)
        dlg.method.setCurrentIndex(dlg.method.findData("pet_grad"))
        app.processEvents()
        assert not dlg.fwhm.isHidden()
        assert dlg.res is not None and dlg.res.method == "pet_grad" and dlg.res.voxels >= 1
        assert "resolução do PET" in dlg.result.text()
        dlg.save()
        assert float(st.get("segment.pet_fwhm")) == 6.5 and st.get("segment.pet_method") == "pet_grad"
        dlg.close()
    finally:
        w.close()
