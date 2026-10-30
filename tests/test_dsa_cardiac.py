"""Subtração digital (DSA) e séries 4D (cardíaco, cine)."""
from dataclasses import dataclass

import numpy as np

from ipe.imaging import cardiac as C
from ipe.imaging import dsa as D


# ---------------------------------------------------------------- DSA
def _angio(n=8):
    """Fundo com "osso" fixo e um vaso que enche a partir do 3º quadro."""
    rng = np.random.default_rng(7)
    osso = np.zeros((64, 64), np.float32)
    osso[20:24, :] = 900.0
    quadros = []
    for k in range(n):
        f = 3000.0 - osso + rng.normal(0, 2, osso.shape).astype(np.float32)
        if k >= 3:
            f[10:12, 10:10 + 6 * (k - 2)] -= 600.0        # contraste no vaso
        quadros.append(f)
    return quadros


def test_subtracao_tira_o_osso_e_deixa_o_vaso():
    quadros = _angio()
    mask = D.mask_pixels(quadros, 3)
    sub = D.subtract(quadros[7], mask, "log")
    # o osso sumiu: na faixa do osso a subtraída fica perto de zero
    assert abs(float(sub[20:24, 40:60].mean())) < 0.02
    # o vaso aparece bem acima do fundo
    vaso = float(sub[10:12, 12:30].mean())
    fundo = float(np.abs(sub[40:60, 40:60]).mean())
    assert vaso > 0.05 and vaso > 10 * fundo
    # linear também funciona (mesmo sinal), e inverter troca o sinal
    lin = D.subtract(quadros[7], mask, "lin")
    assert float(lin[10:12, 12:30].mean()) > 0
    inv = D.subtract(quadros[7], mask, "log", invert=True)
    assert float(inv[10:12, 12:30].mean()) < 0
    w, l = D.auto_window(sub)
    assert w > 0 and l == 0.0


def test_deslocamento_da_mascara():
    a = np.zeros((10, 10), np.float32)
    a[5, 5] = 1.0
    assert D.shift(a, 1, 0)[6, 5] == 1.0
    assert D.shift(a, 0, -2)[5, 3] == 1.0
    assert D.shift(a, 0, 0) is a
    # mover a máscara de volta apaga o fantasma do movimento
    osso = np.zeros((32, 32), np.float32)
    osso[10:14, :] = 500.0
    mexido = D.shift(osso, 2, 0)
    ruim = D.subtract(3000 - mexido, 3000 - osso, "lin")
    bom = D.subtract(3000 - mexido, 3000 - osso, "lin", dy=2)
    assert np.abs(bom).max() < np.abs(ruim).max() / 10


# ---------------------------------------------------------------- 4D
@dataclass
class F:
    position: tuple
    instance_number: int = 0
    slice_location: float = 0.0


def _serie_4d(n_slices=5, n_phases=4, juntas=True):
    quadros = []
    if juntas:                              # fases juntas: corte 1 fases 1..4, corte 2 fases 1..4…
        for s in range(n_slices):
            for p in range(n_phases):
                quadros.append(F((0.0, 0.0, s * 2.0), s * n_phases + p))
    else:                                   # volume inteiro por fase
        for p in range(n_phases):
            for s in range(n_slices):
                quadros.append(F((0.0, 0.0, s * 2.0), p * n_slices + s))
    return quadros


def test_detecta_cortes_e_fases():
    info = C.detect(_serie_4d(5, 4, juntas=True))
    assert info is not None and info.is_4d
    assert (info.n_slices, info.n_phases, info.order) == (5, 4, "phase_major")
    assert info.summary() == "5 corte(s) × 4 fases"
    # o quadro do corte 3, fase 2
    k = info.frame_index(2, 1)
    assert info.where(k) == (2, 1)
    # os quadros de uma fase são um volume inteiro, um por posição
    fase = info.phase_frames(_serie_4d(5, 4), 2)
    assert len(fase) == 5 and [f.position[2] for f in fase] == [0.0, 2.0, 4.0, 6.0, 8.0]

    outra = C.detect(_serie_4d(6, 3, juntas=False))
    assert outra is not None and (outra.n_slices, outra.n_phases) == (6, 3)
    assert outra.order == "slice_major"


def test_serie_comum_nao_vira_4d():
    normal = [F((0.0, 0.0, s * 1.5), s) for s in range(20)]
    assert C.detect(normal) is None
    # contagens diferentes por posição também não são 4D
    torto = normal + [F((0.0, 0.0, 0.0), 99)]
    assert C.detect(torto) is None
    assert C.volume_frames(normal) == normal          # série comum: volume com tudo


def test_volume_de_uma_fase(monkeypatch):
    quadros = _serie_4d(4, 3)
    fase1 = C.volume_frames(quadros, 1)
    assert len(fase1) == 4
    assert [q.instance_number for q in fase1] == [1, 4, 7, 10]
    assert C.phase_label(C.detect(quadros), 2) == "Fase 3/3"


def test_viewport_4d_rola_cortes_e_toca_fases(env, sample_dir):
    """No quadro: a rolagem anda nos cortes da fase; o cine das fases fica parado no corte."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    from ipe.core.config import Settings
    from ipe.imaging.series import FrameCache
    from ipe.ui.viewer.viewport import Viewport

    vp = Viewport(FrameCache(), Settings(paths.settings_file))
    vp.frames = _serie_4d(5, 4)
    from ipe.imaging.cardiac import detect
    vp.cardiac = detect(vp.frames)
    vp.index = 0
    assert vp.is_4d() and vp.cardiac_where() == (0, 0)
    vp._load_current = lambda: None                 # sem pixels de verdade neste teste
    vp.step(1)
    assert vp.cardiac_where() == (1, 0)             # andou um corte, mesma fase
    vp.set_cardiac_phase(2)
    assert vp.cardiac_where() == (1, 2)             # mesma posição, outra fase
    vp.step(-1)
    assert vp.cardiac_where() == (0, 2)
    vp.set_cardiac_phase(4)                          # dá a volta no ciclo
    assert vp.cardiac_where() == (0, 0)
    assert "Corte 1/5" in vp.cardiac_text() and "Fase 1/4" in vp.cardiac_text()
    _ = app
