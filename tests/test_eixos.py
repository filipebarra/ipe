"""Os três eixos perpendiculares da lesão.

O contrato: o eixo não é a caixa nos eixos da série. Lesão oblíqua tem caixa grande e eixo
pequeno — e é o eixo que vai para o laudo.
"""
import numpy as np
import pytest

from ipe.imaging.segment import tres_eixos


def _elipsoide(a, b, c, passo=1.0, giro=0.0):
    """Pontos (mm) de um elipsoide de semieixos a, b, c, girado `giro` graus no plano x-y."""
    g = np.arange(-max(a, b, c) - 1, max(a, b, c) + 1 + 1e-9, passo)
    x, y, z = np.meshgrid(g, g, g, indexing="ij")
    dentro = (x / a) ** 2 + (y / b) ** 2 + (z / c) ** 2 <= 1.0
    pts = np.stack([x[dentro], y[dentro], z[dentro]], axis=1)
    t = np.radians(giro)
    r = np.array([[np.cos(t), -np.sin(t), 0], [np.sin(t), np.cos(t), 0], [0, 0, 1.0]])
    return pts @ r.T


def test_os_eixos_sao_os_do_elipsoide():
    pts = _elipsoide(20, 10, 5)
    e = tres_eixos(pts, (1.0, 1.0, 1.0))
    assert e[0] == pytest.approx(41.0, abs=2.0)
    assert e[1] == pytest.approx(21.0, abs=2.0)
    assert e[2] == pytest.approx(11.0, abs=2.0)
    assert e[0] >= e[1] >= e[2]


def test_girar_a_lesao_nao_muda_os_eixos():
    """A caixa nos eixos da série cresce com o giro; o eixo de verdade, não."""
    reto = tres_eixos(_elipsoide(20, 8, 5), (1.0, 1.0, 1.0))
    obl = tres_eixos(_elipsoide(20, 8, 5, giro=35.0), (1.0, 1.0, 1.0))
    for a, b in zip(reto, obl):
        assert a == pytest.approx(b, abs=2.0)
    # a caixa, essa muda muito
    p = _elipsoide(20, 8, 5, giro=35.0)
    caixa = np.ptp(p, axis=0)
    assert caixa[0] > 1.15 * reto[0] * 0.8 or caixa[1] > 2 * 8


def test_lesao_de_um_corte_so_mede_a_espessura_do_corte():
    """Sem o voxel nas pontas, uma lesão de um corte mediria zero na direção do corte."""
    g = np.arange(-5, 5.001, 1.0)
    x, y = np.meshgrid(g, g, indexing="ij")
    dentro = x ** 2 + y ** 2 <= 25
    pts = np.stack([x[dentro], y[dentro], np.zeros(dentro.sum())], axis=1)
    e = tres_eixos(pts, (1.0, 1.0, 5.0))
    assert e[2] == pytest.approx(5.0, abs=0.01)


def test_os_eixos_sao_perpendiculares_de_verdade():
    """Uma panqueca inclinada: os dois maiores eixos ficam no plano dela, o menor é a espessura."""
    rng = np.random.default_rng(0)
    g = np.arange(-15, 15.001, 1.0)
    x, y, z = np.meshgrid(g, g, np.arange(-2, 2.001, 1.0), indexing="ij")
    dentro = (x / 15.0) ** 2 + (y / 10.0) ** 2 + (z / 2.0) ** 2 <= 1
    pts = np.stack([x[dentro], y[dentro], z[dentro]], axis=1)
    t = np.radians(40.0)
    r = np.array([[1, 0, 0], [0, np.cos(t), -np.sin(t)], [0, np.sin(t), np.cos(t)]])
    e = tres_eixos(pts @ r.T, (1.0, 1.0, 1.0))
    assert e[0] == pytest.approx(31.0, abs=2.5)
    assert e[1] == pytest.approx(21.0, abs=2.5)
    assert e[2] == pytest.approx(5.0, abs=2.0)
    del rng


def test_poucos_pontos_nao_quebram():
    assert tres_eixos(np.zeros((0, 3)), (1.0, 2.0, 3.0)) == (1.0, 1.0, 1.0)
    e = tres_eixos(np.array([[0.0, 0, 0], [10.0, 0, 0]]), (1.0, 1.0, 1.0))
    assert e[0] == pytest.approx(11.0, abs=0.01)
