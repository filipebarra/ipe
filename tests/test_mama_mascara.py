"""A máscara da mama: mantém a mama, corta parede torácica, pulmão e coração.

Fantoma sagital, como os exames dele: colunas de anterior para posterior. Ar na frente, mama,
músculo peitoral, pulmão escuro e, atrás, o coração — que realça forte e não pode entrar em
nenhum número do exame inteiro.
"""
import numpy as np
import pytest

from ipe.imaging.mama_mascara import eixo_anterior_posterior, mascara_da_mama

SAGITAL = [0, 1, 0, 0, 0, -1]          # colunas A→P, linhas S→I
AXIAL = [1, 0, 0, 0, 1, 0]             # colunas E→D, linhas A→P
CORONAL = [1, 0, 0, 0, 0, -1]          # nenhum eixo da imagem é A-P


def fantoma(nz=6, ny=60, nx=80):
    """(volume pré-contraste, fatias de cada estrutura). Colunas: 0 = anterior.

    O pulmão tem de ficar **fechado pelo tórax** — é essa a diferença entre pulmão e ar do
    ambiente, e foi assim que o primeiro fantoma mentiu: o pulmão dele encostava no ar de fora
    por cima e por baixo, e o detector, com razão, não o viu como pulmão.
    """
    vol = np.zeros((nz, ny, nx), np.float32)
    mama = (slice(None), slice(12, 48), slice(10, 40))
    torax = (slice(None), slice(4, 56), slice(40, 78))
    pulmao = (slice(None), slice(8, 30), slice(48, 74))
    coracao = (slice(None), slice(32, 52), slice(48, 70))
    vol[mama] = 300.0            # gordura e glândula
    vol[torax] = 160.0           # parede, músculo, mediastino
    vol[pulmao] = 5.0            # pulmão: quase sem sinal, e cercado pelo tórax
    vol[coracao] = 400.0
    parede = (slice(None), slice(4, 56), slice(40, 48))      # o que fica na frente do pulmão
    return vol, {"mama": mama, "parede": parede, "pulmao": pulmao, "coracao": coracao}


def test_eixo_anterior_posterior():
    assert eixo_anterior_posterior(SAGITAL) == (1, 1)        # colunas, crescendo para posterior
    assert eixo_anterior_posterior([0, -1, 0, 0, 0, -1]) == (1, -1)
    assert eixo_anterior_posterior(AXIAL) == (0, 1)          # linhas
    assert eixo_anterior_posterior(CORONAL) == (-1, 0)
    assert eixo_anterior_posterior(None) == (-1, 0)
    assert eixo_anterior_posterior([1, 0, 0]) == (-1, 0)


def test_corta_tudo_que_esta_atras_da_parede():
    vol, p = fantoma()
    m, info = mascara_da_mama(vol, referencia=1000.0, orientation=SAGITAL, pixel_mm=(1.0, 1.0))
    assert info["modo"] == "corte na parede torácica"
    assert m[p["mama"]].mean() > 0.99, "a mama tem que ficar inteira"
    assert not m[p["coracao"]].any(), "o coração entrou na máscara"
    assert not m[p["pulmao"]].any()
    # A faixa na frente do pulmão (músculo peitoral) FICA: quem denuncia a parede é o pulmão, e
    # o músculo está na frente dele. Separar músculo de glândula por sinal não dá em T1 com
    # saturação de gordura, então em vez de chutar espessura em milímetros a máscara mantém o
    # músculo e **diz** que mantém.
    assert m[p["parede"]].mean() > 0.99
    assert "músculo peitoral" in info["texto"]


def test_a_conta_do_exame_muda_de_verdade():
    """Sem o corte, o coração domina: é esse número que a máscara existe para arrumar."""
    vol, p = fantoma()
    pos = vol.copy()
    pos[p["coracao"]] *= 3.0            # coração realça 200%
    pos[p["mama"]] *= 1.2               # mama realça 20%
    pos[p["parede"]] *= 1.2             # músculo realça pouco, como na vida
    realce = (pos - vol) / np.maximum(vol, 1e-6) * 100
    corpo = vol >= 100.0
    m, _i = mascara_da_mama(vol, referencia=1000.0, orientation=SAGITAL, pixel_mm=(1.0, 1.0))
    assert np.mean(realce[corpo] > 100) > 0.15          # sem a máscara, o coração aparece
    assert np.mean(realce[m] > 100) == 0.0              # com ela, só a mama entra na conta
    assert 19.0 < float(np.mean(realce[m])) < 21.0      # e o realce médio é o da mama


def test_plano_sem_eixo_ap_na_imagem_nao_corta_e_avisa():
    vol, _p = fantoma()
    m, info = mascara_da_mama(vol, referencia=1000.0, orientation=CORONAL)
    assert info["modo"] == "sem corte posterior"
    assert "sem eixo anterior-posterior" in info["texto"]
    assert m.sum() == (vol >= 100.0).sum()              # devolve o tecido, sem inventar corte


def test_axial_corta_nas_linhas():
    """No axial o anterior-posterior anda nas linhas: o mesmo fantoma, transposto."""
    vol, p = fantoma()
    vol_ax = np.swapaxes(vol, 1, 2)                     # linhas passam a ser o eixo A-P
    m, info = mascara_da_mama(vol_ax, referencia=1000.0, orientation=AXIAL, pixel_mm=(1.0, 1.0))
    assert info["eixo_ap"] == 0 and info["modo"] == "corte na parede torácica"
    alvo = np.zeros_like(vol, bool)
    alvo[p["coracao"]] = True
    coracao = np.swapaxes(alvo, 1, 2)
    assert not m[coracao].any()


def test_sentido_invertido_da_na_mesma():
    """Série gravada com as colunas de posterior para anterior: a mama continua sendo a mama."""
    vol, p = fantoma()
    virado = vol[:, :, ::-1].copy()
    m, _i = mascara_da_mama(virado, referencia=1000.0, orientation=[0, -1, 0, 0, 0, -1],
                            pixel_mm=(1.0, 1.0))
    alvo = np.zeros_like(vol, bool)
    alvo[p["coracao"]] = True
    assert not m[alvo[:, :, ::-1]].any()
    alvo_m = np.zeros_like(vol, bool)
    alvo_m[p["mama"]] = True
    assert m[alvo_m[:, :, ::-1]].mean() > 0.99


def test_corte_sem_pulmao_herda_a_parede_do_vizinho():
    """Corte medial: mediastino no lugar do pulmão, nenhuma interrupção. Não pode abrir a máscara."""
    vol, p = fantoma()
    vol[0, 8:30, 48:74] = 350.0               # o pulmão do primeiro corte virou mediastino
    m, _i = mascara_da_mama(vol, referencia=1000.0, orientation=SAGITAL, pixel_mm=(1.0, 1.0))
    assert not m[0, 32:52, 48:70].any(), "o corte sem pulmão deixou o coração entrar"
    assert m[0, 12:48, 10:40].mean() > 0.99


def test_volume_vazio_nao_quebra():
    m, info = mascara_da_mama(np.zeros((3, 10, 10), np.float32), 1000.0, SAGITAL)
    assert not m.any() and "modo" in info
