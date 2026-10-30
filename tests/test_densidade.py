"""Densidade mamária: a medida, e o que ela recusa a fazer.

O valor sai de limiar dentro da mama; os testes usam fantoma com fração densa **conhecida**,
porque sem valor verdadeiro não dá para dizer se a conta está certa.
"""

import numpy as np
import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from ipe.imaging import density as D


def _mamo(lado="R", incidencia="CC", fracao=0.30, implante="NO", peitoral=False,
          monochrome1=False, linhas=600, colunas=480, espaco=0.2, denso=2600.0):
    """Fantoma: meia elipse de mama (fundo escuro), com `fracao` da área em tecido denso."""
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.1.2"
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.SOPClassUID = ds.file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
    ds.Modality, ds.ImageLaterality, ds.ViewPosition = "MG", lado, incidencia
    ds.BreastImplantPresent = implante
    ds.ImagerPixelSpacing = [espaco, espaco]
    ds.BodyPartThickness = 50
    ds.Rows, ds.Columns = linhas, colunas
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit, ds.PixelRepresentation, ds.SamplesPerPixel = 15, 0, 1
    ds.PhotometricInterpretation = "MONOCHROME1" if monochrome1 else "MONOCHROME2"

    y, x = np.mgrid[0:linhas, 0:colunas]
    cy, cx = linhas / 2.0, 0.0 if lado == "R" else colunas - 1.0     # parede torácica de um lado
    rr = ((y - cy) / (linhas * 0.42)) ** 2 + ((x - cx) / (colunas * 0.85)) ** 2
    mama = rr < 1.0
    img = np.full((linhas, colunas), 300.0)                           # fundo
    img[mama] = 1200.0                                                # gordura
    dentro = np.nonzero(mama)
    ordem = np.argsort(rr[dentro])                                    # mais denso no meio
    n = int(round(fracao * len(ordem)))
    img[dentro[0][ordem[:n]], dentro[1][ordem[:n]]] = 2600.0          # fibroglandular
    if peitoral:
        tri = (x < colunas * 0.22 - 0.25 * y) if lado == "R" else (x > colunas * 0.78 + 0.25 * y)
        img[tri & mama] = 2900.0
    if monochrome1:
        img = 4095.0 - img
    ds.PixelData = img.astype(np.uint16).tobytes()
    return ds, mama


# ------------------------------------------------------------------ a conta
def test_mede_a_fracao_densa_do_fantoma():
    ds, _ = _mamo(fracao=0.30)
    r = D.medir(ds)
    assert r.pd == pytest.approx(30, abs=6)          # o fantoma foi desenhado com 30%
    assert r.lado == "R" and r.incidencia == "CC"
    assert r.metodo == D.LIMIAR and not r.avisos


def test_mama_mais_densa_da_valor_maior():
    pouca = D.medir(_mamo(fracao=0.15)[0]).pd
    muita = D.medir(_mamo(fracao=0.60)[0]).pd
    assert muita > pouca + 25


def test_areas_saem_em_cm2_com_o_pixel_do_arquivo():
    ds, mama = _mamo(fracao=0.30, espaco=0.2)
    r = D.medir(ds)
    esperado = mama.sum() * (0.02 ** 2)             # cm² da máscara desenhada
    assert r.mama_cm2 == pytest.approx(esperado, rel=0.25)
    assert r.densa_cm2 < r.mama_cm2
    assert r.espessura_mm == 50


def test_monochrome1_nao_inverte_o_resultado():
    a = D.medir(_mamo(fracao=0.35)[0]).pd
    b = D.medir(_mamo(fracao=0.35, monochrome1=True)[0]).pd
    assert abs(a - b) < 8


def test_sem_tamanho_de_pixel_avisa_mas_mede():
    ds, _ = _mamo()
    del ds.ImagerPixelSpacing
    r = D.medir(ds)
    assert r.pd > 0 and r.mama_cm2 == 0
    assert any("tamanho de pixel" in a for a in r.avisos)


def test_tomossintese_nao_entra_nesta_conta():
    ds, _ = _mamo()
    ds.NumberOfFrames = 4
    ds.PixelData = ds.PixelData * 4
    r = D.medir(ds)
    assert r.pd == 0 and any("2D" in a for a in r.avisos)


# ------------------------------------------------------------------ peitoral
def test_peitoral_sai_da_conta_quando_da_para_separar():
    """O método só separa o peitoral quando ele é a coisa mais clara ligada à parede torácica."""
    com = D.medir(_mamo(incidencia="MLO", fracao=0.20, peitoral=True, denso=1700.0)[0])
    sem = D.medir(_mamo(incidencia="CC", fracao=0.20, peitoral=False, denso=1700.0)[0])
    assert not any("peitoral" in a for a in com.avisos)   # reconheceu
    assert abs(com.pd - sem.pd) < 12                      # e não inflou o valor


def test_peitoral_grudado_no_tecido_denso_vira_aviso():
    """Quando o músculo e o tecido denso são igualmente claros **e contíguos**, o crescimento
    engole os dois. Aí o programa recusa o corte: cortar de mais some com mama de verdade.
    Nos exames reais isso acontece em cerca de metade das MLO."""
    arr = np.full((400, 300), 1000.0)
    mama = np.zeros((400, 300), bool)
    mama[50:380, 10:290] = True
    arr[mama] = 2000.0                                   # mama inteira clara: nada a separar
    tri, aviso = D.peitoral(arr, mama, "left")
    assert not tri.any() and "peitoral" in aviso


def test_mlo_sem_peitoral_nenhum_tambem_avisa():
    r = D.medir(_mamo(incidencia="MLO", fracao=0.20, peitoral=False)[0])
    assert any("peitoral" in a for a in r.avisos)         # não achou: avisa, não chuta


# ------------------------------------------------------------------ prótese
def test_protese_e_o_que_o_arquivo_diz():
    """71 exames reais do IMEB tinham a tag preenchida; o detector por textura errava para mais."""
    ds, _ = _mamo(implante="NO")
    assert not any("rótese" in a for a in D.medir(ds).avisos)
    ds2, _ = _mamo(implante="YES")
    assert any("rótese" in a for a in D.medir(ds2).avisos)


# ------------------------------------------------------------------ faixas e resumo
def test_faixas_sao_referencia_nao_veredito():
    assert D.faixa_de(10) == "a" and D.faixa_de(30) == "b"
    assert D.faixa_de(60) == "c" and D.faixa_de(90) == "d"


def test_valor_do_exame_e_a_mama_mais_densa():
    m = [D.Densidade(lado="R", pd=20, mama_cm2=100), D.Densidade(lado="L", pd=55, mama_cm2=100)]
    assert D.por_mama(m) == {"R": 20.0, "L": 55.0}
    assert D.do_exame(m) == 55.0
    assert D.do_exame([]) == 0.0


def test_modelo_que_falha_cai_no_limiar_e_avisa():
    def quebrado(_arr, _reg):
        raise RuntimeError("modelo ruim")
    r = D.medir(_mamo(fracao=0.30)[0], modelo=quebrado)
    assert r.metodo == D.LIMIAR and r.pd > 0
    assert any("modelo falhou" in a for a in r.avisos)


def test_modelo_bom_substitui_so_a_segmentacao():
    def tudo(_arr, reg):
        return reg
    r = D.medir(_mamo(fracao=0.30)[0], modelo=tudo)
    assert r.metodo == D.MODELO and r.pd == pytest.approx(100, abs=1)


# ------------------------------------------------------- máscara esburacada
def _meia_elipse(linhas=600, colunas=480):
    y, x = np.mgrid[0:linhas, 0:colunas]
    rr = ((y - linhas / 2.0) / (linhas * 0.42)) ** 2 + (x / (colunas * 0.85)) ** 2
    return rr < 1.0


def test_tapa_furos_enche_a_linha_entre_as_pontas():
    m = np.zeros((5, 9), bool)
    m[2, 1] = m[2, 7] = True                         # só as pontas
    assert D._tapa_furos(m)[2, 2:7].all()
    assert not D._tapa_furos(m)[2, 0] and not D._tapa_furos(m)[2, 8]


def test_mama_esburacada_sai_inteira():
    """Na 2D processada a gordura chega perto do fundo e o limiar recorta a mama em pedaços.

    Sem tapar os furos a área despencava: a mesma mama do acervo dava 108,8 cm² na 2D sintética
    e 38,4 cm² na processada.
    """
    forma = _meia_elipse()
    arr = np.full(forma.shape, 300.0)
    arr[forma] = 350.0                               # gordura quase no fundo
    ruido = (np.mgrid[0:600, 0:480][0] * 7 + np.mgrid[0:600, 0:480][1] * 13) % 5 == 0
    arr[forma & ruido] = 2600.0                      # só o tecido denso passa do limiar
    achada = D.mama(arr, 0.2)
    assert achada.sum() > 0.80 * forma.sum()
    assert achada.sum() <= forma.sum()


def test_mama_clara_e_inteira_nao_muda():
    """A 2D sintética já saía inteira: o conserto não pode mexer nela."""
    forma = _meia_elipse()
    arr = np.full(forma.shape, 300.0)
    arr[forma] = 2600.0
    achada = D.mama(arr, 0.2)
    assert 0.80 * forma.sum() < achada.sum() <= forma.sum()


def test_letreiro_solto_fica_de_fora():
    forma = _meia_elipse()
    arr = np.full(forma.shape, 300.0)
    arr[forma] = 2600.0
    arr[10:40, 430:470] = 4095.0                     # marcador claro longe da mama
    achada = D.mama(arr, 0.2)
    assert not achada[10:40, 430:470].any()
