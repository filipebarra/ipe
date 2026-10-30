"""Indicador de profundidade da tomossíntese: geometria, desenho e navegação."""
import numpy as np
import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.imaging import tomo_pos as TP
from ipe.importer.scanner import Importer

BTO = "1.2.840.10008.5.1.4.1.1.13.1.3"


def _tomo(folder, lado="R", vista="CC", angulo=0.0, n=10, espessura=55.0, forca=80.0):
    """Fantoma de mamografia: uma 2D e uma tomossíntese da mesma incidência.

    A 2D precisa existir porque o hanging da mama monta a célula com as duas juntas — é
    assim que o quadro ganha `tomo_range`, que é o que o indicador usa.
    """
    from pydicom.uid import generate_uid
    from ipe.core.sample_data import _base, _mono, _save, tomo_geometry
    pat = {"name": "TOMO^Fantoma", "id": "TOMO9", "birth": "19700101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20260915", "accession": "TOMOD01",
             "description": "MAMOGRAFIA", "for": generate_uid()}
    h, w = 256, 200
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx = w if lado == "R" else 0
    mama = ((xx - cx) / (w * 0.95)) ** 2 + ((yy - h / 2) / (h * 0.45)) ** 2 < 1

    s2d = {"uid": generate_uid(), "number": 1, "description": "MAMOGRAFIA 2D"}
    ds = _base("1.2.840.10008.5.1.4.1.1.1.2", pat, study, s2d, "MG")
    ds.InstanceNumber, ds.ImageLaterality, ds.ViewPosition = 1, lado, vista
    ds.AcquisitionTime = "100000"
    ds.ImagerPixelSpacing = [0.1, 0.1]
    _mono(ds, np.where(mama, 1500, 100), signed=False)
    _save(ds, folder / "mg2d")

    st = {"uid": generate_uid(), "number": 2, "description": f"TOMO {lado} {vista}"}
    ds = _base(BTO, pat, study, st, "MG")
    ds.InstanceNumber, ds.ImageLaterality, ds.ViewPosition = 1, lado, vista
    ds.PixelSpacing = [0.1, 0.1]
    vol = np.stack([np.where(mama, 1000 + 20 * z, 50) for z in range(n)]).astype(np.uint16)
    _mono(ds, vol[0], signed=False)
    ds.NumberOfFrames = n
    ds.PixelData = vol.tobytes()
    tomo_geometry(ds, n, thickness_mm=espessura, force_n=forca, angle_deg=angulo, side=lado)
    _save(ds, folder / "tomo")
    return study["uid"]


def _geo(tmp_path, **kw):
    import pydicom
    caminho = tmp_path / f"g{len(list(tmp_path.glob('**/*')))}"
    caminho.mkdir()
    _tomo(caminho, **kw)
    arq = next(p for p in caminho.rglob("*.dcm") if "tomo" in str(p))
    return TP.from_dataset(pydicom.dcmread(str(arq), stop_before_pixels=True, force=True))


# ------------------------------------------------------------------ motor
def test_profundidade_vem_da_posicao_de_cada_corte(tmp_path):
    g = _geo(tmp_path, n=10, espessura=55.0)
    assert g is not None and g.n == 10 and g.source == "arquivo"
    assert g.depths_mm[0] == pytest.approx(0)               # o primeiro corte é o do detector
    assert g.depths_mm[-1] == pytest.approx(45)             # 9 passos de 5 mm
    assert g.thickness_mm == pytest.approx(55) and g.force_n == pytest.approx(80)
    assert g.slab_mm == pytest.approx(10) and "Paddle" in g.paddle
    assert g.detector_known is True
    assert g.depth_text(4) == "20 mm" and "comprimida 55" in g.thickness_text()


def test_angulo_do_braco_sai_do_arquivo(tmp_path):
    assert _geo(tmp_path, vista="CC", angulo=0.0).angle_deg == pytest.approx(0)
    mlo = _geo(tmp_path, vista="MLO", angulo=45.0)
    assert mlo.angle_deg == pytest.approx(45)
    assert mlo.side == "R"
    assert _geo(tmp_path, lado="L", vista="MLO", angulo=45.0).side == "L"


def test_fracao_e_o_caminho_de_volta(tmp_path):
    g = _geo(tmp_path, n=10, espessura=55.0)
    # a faixa é a reconstrução inteira (45 mm), não a espessura comprimida
    assert g.scale_mm == pytest.approx(55)                  # espessura maior que o percurso
    assert g.fraction(0) == pytest.approx(0)
    assert g.index_at(g.fraction(6)) == 6                   # ida e volta fecham
    assert g.index_at(-5) == 0 and g.index_at(9) == g.n - 1  # fora da faixa não estoura


def test_pa_marcada_quando_a_reconstrucao_passa_da_mama(tmp_path):
    curta = _geo(tmp_path, n=10, espessura=30.0)            # 45 mm de cortes, 30 mm de mama
    assert curta.scale_mm == pytest.approx(45)
    assert curta.paddle_fraction() == pytest.approx(30 / 45, abs=0.01)
    larga = _geo(tmp_path, n=10, espessura=55.0)            # a mama cabe toda
    assert larga.paddle_fraction() == pytest.approx(1.0)


def test_sem_posicao_por_quadro_a_profundidade_e_estimada():
    from pydicom.dataset import Dataset
    ds = Dataset()
    ds.NumberOfFrames = 8
    ds.BodyPartThickness = "40"
    g = TP.from_dataset(ds, 8)
    assert g is not None and g.source == "estimado" and g.n == 8
    assert g.depths_mm[-1] == pytest.approx(40)
    assert "estimada" in g.tip_text(3)
    assert TP.from_dataset(Dataset(), 1) is None            # um corte só não é volume


def test_ordem_invertida_ainda_acha_o_detector():
    pos = [np.array([0.0, 0.0, 50.0]), np.array([0.0, 0.0, 45.0]), np.array([0.0, 0.0, 40.0])]
    d, certo = TP.depths_from_positions(pos, None)
    assert certo is True and d[0] == pytest.approx(10) and d[-1] == pytest.approx(0)
    # incidência lateral pura: sem componente vertical, a ordem do arquivo é mantida e avisada
    lat = [np.array([0.0, 0.0, 0.0]), np.array([5.0, 0.0, 0.0])]
    _d, certo = TP.depths_from_positions(lat, None)
    assert certo is False


# ------------------------------------------------------------------ desenho e navegação
def _aba(env, tmp_path, **kw):
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    pasta = tmp_path / "exame"
    pasta.mkdir()
    _tomo(pasta, **kw)
    Importer(db, paths.storage).import_paths([pasta])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1000, 800)
    w.show()
    w.browser.refresh()
    assert w.handle_external({"accession": "TOMOD01"}) == "aberto"
    tab = w.tabs.currentWidget()
    tab.set_layout(2, 2)          # o hanging da mama reserva as quatro incidências
    app.processEvents()
    vp = next((v for v in tab.viewports if v.frames), tab.viewports[0])
    tab._activate(vp)
    if vp.tomo_range is not None:
        vp.go_to(vp.tomo_range[0] + (vp.tomo_range[1] - vp.tomo_range[0]) // 2)
    app.processEvents()
    return w, tab, vp, app


def test_indicador_no_canto_externo(env, tmp_path):
    from ipe.ui.viewer import tomo_dial as TD
    w, tab, vp, app = _aba(env, tmp_path, lado="R", vista="MLO", angulo=45.0, n=10)
    assert vp.in_tomo() and vp.tomo_range == (1, 11)
    geo = TD.geometry(vp)
    assert geo is not None and geo.angle_deg == pytest.approx(45)
    # mama direita: parede torácica à direita da tela, indicador no canto de baixo à esquerda
    assert vp.chest_screen_side() == "right"
    caixa = TD.box(vp, 12.0, 2)
    assert caixa.x() < vp.width() / 2 and caixa.bottom() > vp.height() / 2
    vp.grab()
    assert TD.HOTSPOT in vp._hotspots
    w.close()


def test_indicador_troca_de_canto_na_outra_mama(env, tmp_path):
    from ipe.ui.viewer import tomo_dial as TD
    w, tab, vp, app = _aba(env, tmp_path, lado="L", vista="MLO", angulo=45.0, n=10)
    assert vp.chest_screen_side() == "left"
    assert TD.box(vp, 12.0, 2).x() > vp.width() / 2          # canto de baixo à direita
    w.close()


def test_arrastar_o_marcador_salta_o_corte(env, tmp_path):
    from ipe.ui.viewer import tomo_dial as TD
    w, tab, vp, app = _aba(env, tmp_path, lado="R", vista="CC", angulo=0.0, n=10)
    vp.grab()
    lh, linhas = vp._overlay_metrics()
    geo = TD.geometry(vp)
    c, r, (ax, ay), faixa = TD._band(vp, geo, TD.box(vp, lh, linhas), lh)
    # o topo da faixa é a pá; o fundo, o detector
    perto_do_detector = QPointF(c.x() + ax * (-faixa / 2), c.y() + ay * (-faixa / 2))
    perto_da_pa = QPointF(c.x() + ax * (faixa / 2), c.y() + ay * (faixa / 2))
    base, fim = vp.tomo_range
    vp._tomo_dial_jump(perto_do_detector)
    assert vp.index == base                                  # primeiro corte, colado no detector
    vp._tomo_dial_jump(perto_da_pa)
    assert vp.index == fim - 1
    vp._tomo_dial_jump(QPointF(c.x(), c.y()))
    assert base + 3 <= vp.index <= base + 6                  # o meio da faixa cai no meio da mama
    w.close()


def test_indicador_some_fora_da_tomo(env, tmp_path):
    from ipe.ui.viewer import tomo_dial as TD
    w, tab, vp, app = _aba(env, tmp_path, n=10)
    vp.tomo_range = (0, 0)
    assert TD.geometry(vp) is None                           # 2D não tem profundidade
    pix = QPixmap(vp.size())
    p = QPainter(pix)
    TD.draw(vp, p, vp.font(), 12.0, 2)                       # não desenha nem estoura
    p.end()
    vp.tomo_range = None
    vp.settings.set("viewer.tomo_dial", False)
    vp._hotspots = {}
    vp.grab()
    assert TD.HOTSPOT not in vp._hotspots                    # desligado nas preferências
    w.close()
