"""Reconstrução de série sagital: o axial e o coronal têm de sair em pé, não girados 90°.

O que ele viu na tela, numa RM de mama sagital: o mapa reconstruído em "Axial" com as marcas R em
cima, L embaixo, A à esquerda e P à direita — ou seja, deitado. A reconstrução escolhia linhas e
colunas pela ordem dos índices do volume, não pela convenção de leitura.
"""
import numpy as np
import pytest

from ipe.imaging.volume import MPRPlane, Volume, alvos_da_tela


def _volume(row_dir, col_dir, slice_vec, shape=(20, 24, 28)):
    return Volume(data=np.zeros(shape, np.float32), origin=np.zeros(3),
                  row_dir=np.asarray(row_dir, float), col_dir=np.asarray(col_dir, float),
                  slice_vec=np.asarray(slice_vec, float), dx=1.0, dy=1.0,
                  window=None, source_path="x")


SAGITAL = dict(row_dir=(0, 1, 0), col_dir=(0, 0, -1), slice_vec=(1, 0, 0))   # colunas A→P, cortes E→D
AXIAL = dict(row_dir=(1, 0, 0), col_dir=(0, 1, 0), slice_vec=(0, 0, -1))


def _direcoes(plano):
    """(para onde aponta a direita da tela, para onde aponta o baixo da tela)."""
    return plano.orientation[:3], plano.orientation[3:]


def test_alvos_da_tela():
    d, b = alvos_da_tela([0, 0, 1])          # axial
    assert list(d) == [1, 0, 0] and list(b) == [0, 1, 0]
    d, b = alvos_da_tela([0, -1, 0])         # coronal
    assert list(d) == [1, 0, 0] and list(b) == [0, 0, -1]
    d, b = alvos_da_tela([1, 0, 0])          # sagital
    assert list(d) == [0, 1, 0] and list(b) == [0, 0, -1]


@pytest.mark.parametrize("fonte", [SAGITAL, AXIAL], ids=["fonte sagital", "fonte axial"])
def test_cada_plano_sai_na_convencao(fonte):
    vol = _volume(**fonte)
    planos = {MPRPlane(vol, ax).name: MPRPlane(vol, ax) for ax in (0, 1, 2)}
    assert set(planos) == {"Axial", "Coronal", "Sagital"}
    for nome, p in planos.items():
        if p.axis == 0:
            continue                          # o plano original sai como o aparelho gravou
        direita, baixo = _direcoes(p)
        alvo_h, alvo_v = alvos_da_tela(p.normal)
        assert float(direita @ alvo_h) > 0.9, f"{nome}: a direita da tela aponta para o lado errado"
        assert float(baixo @ alvo_v) > 0.9, f"{nome}: o baixo da tela aponta para o lado errado"


def test_o_axial_de_uma_sagital_nao_sai_deitado():
    """Era o defeito: linhas no eixo dos cortes (direita-esquerda) e colunas em ântero-posterior."""
    vol = _volume(**SAGITAL)
    axial = next(MPRPlane(vol, ax) for ax in (1, 2) if MPRPlane(vol, ax).name == "Axial")
    assert axial.transposto, "sem transpor, o axial de uma sagital sai girado 90°"
    direita, baixo = _direcoes(axial)
    assert abs(direita[0]) > 0.9 and direita[0] > 0      # direita da tela = esquerda do paciente
    assert abs(baixo[1]) > 0.9 and baixo[1] > 0          # baixo da tela = posterior
    img = axial.image(axial.n // 2).pixels
    # linhas no eixo ântero-posterior (28 colunas do volume) e colunas no eixo dos cortes (20)
    assert img.shape == (28, 20)


def test_a_geometria_continua_batendo_depois_de_transpor():
    """Transpor não pode mentir sobre onde o pixel está: ida e volta no mesmo ponto."""
    vol = _volume(**SAGITAL)
    for ax in (1, 2):
        p = MPRPlane(vol, ax)
        idx = p.n // 3
        canto = p.position(idx)
        # o canto superior esquerdo tem de ser um voxel do volume, e o índice de volta tem de bater
        ijk = vol.patient_to_voxel(canto)
        assert np.allclose(np.rint(ijk), ijk, atol=1e-6), f"{p.name}: canto fora da grade"
        assert p.index_for_point(canto) == idx, f"{p.name}: o corte de volta não é o mesmo"
        # andar uma coluna na tela = andar col_spacing em mm na direção da coluna
        passo = p.orientation[:3] * p.col_spacing
        de_novo = vol.patient_to_voxel(canto + passo)
        assert np.allclose(np.rint(de_novo), de_novo, atol=1e-6)


def test_o_plano_original_nao_e_mexido():
    vol = _volume(**SAGITAL)
    p = MPRPlane(vol, 0)
    assert not p.transposto and not p.flip_v and not p.flip_h
    assert np.allclose(p.orientation[:3], SAGITAL["row_dir"])
    assert np.allclose(p.orientation[3:], SAGITAL["col_dir"])
