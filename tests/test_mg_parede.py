"""Lado da parede torácica por quadro do protocolo de mamografia (0.96.1).

O defeito: numa etapa 1×4 com CCD, CCE, MLOD, MLOE, a CCE e a MLOD saíam espelhadas — o lado da
parede vinha da metade da tela, não da mama. Com as duas mamas juntas, decide a mama.
"""
from ipe.imaging.mammo import lados_das_celulas, parede_desejada


def _linha(cells):
    lados = lados_das_celulas(cells)
    from ipe.imaging.mammo import parse_code
    return [parede_desejada(parse_code(c).side, i, len(cells), lados) for i, c in enumerate(cells)]


def test_1x4_alternando_os_lados():
    # o caso relatado: as duas direitas com a parede à direita, as duas esquerdas à esquerda
    assert _linha(["CCD", "CCE", "MLOD", "MLOE"]) == ["right", "left", "right", "left"]


def test_1x4_direitas_e_depois_esquerdas():
    assert _linha(["CCD", "MLOD", "CCE", "MLOE"]) == ["right", "right", "left", "left"]


def test_1x4_esquerda_primeiro_segue_a_mama():
    assert _linha(["CCE", "CCD", "MLOE", "MLOD"]) == ["left", "right", "left", "right"]


def test_par_de_sempre_nao_muda():
    assert _linha(["CCD", "CCE"]) == ["right", "left"]
    assert _linha(["MLOD rec", "MLOE rec"]) == ["right", "left"]


def test_mesma_mama_atual_x_anterior_fica_costas_com_costas():
    assert _linha(["CCD", "CCD ant"]) == ["right", "left"]
    assert _linha(["CCE", "CCE ant"]) == ["right", "left"]
    assert _linha(["CCD", "CCD ant", "MLOD", "MLOD ant"]) == ["right", "left", "right", "left"]


def test_coluna_unica_sem_as_duas_mamas_nao_espelha():
    assert parede_desejada("R", 0, 1, {"R"}) is None


def test_monitor_de_uma_coluna_com_a_etapa_inteira():
    # 4 monitores de uma coluna, etapa CCD, CCE, MLOD, MLOE: cada tela segue a mama
    lados = lados_das_celulas(["CCD", "CCE", "MLOD", "MLOE"])
    assert [parede_desejada(s, d % 2, 2, lados) for d, s in enumerate("RLRL")] == \
        ["right", "left", "right", "left"]


def test_codigos_vazios_ou_invalidos_nao_contam():
    assert lados_das_celulas(["CCD", "", "xyz"]) == {"R"}
