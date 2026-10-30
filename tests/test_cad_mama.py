"""Números do CAD de RM de mama para uma lesão segmentada (estilo CADstream)."""
import numpy as np
import pytest

from ipe.imaging import cad_mama as C
from ipe.imaging.segment import segment
from ipe.imaging.volume import Volume


def _vol(data: np.ndarray, dx=1.0, dy=1.0, dz=1.0) -> Volume:
    return Volume(data=data.astype(np.float32), origin=np.zeros(3), row_dir=np.array([1.0, 0, 0]),
                  col_dir=np.array([0.0, 1, 0]), slice_vec=np.array([0.0, 0, dz]), dx=dx, dy=dy,
                  window=None, source_path="")


def _lesao(realce=300.0, classe=6, lado=6, forma=(10, 40, 40)):
    """Um cubo que realça no meio de um volume frio."""
    r = np.zeros(forma, np.float32)
    c = np.zeros(forma, np.uint8)
    k, j, i = (s // 2 for s in forma)
    sl = (slice(k - lado // 2, k + lado // 2), slice(j - lado // 2, j + lado // 2),
          slice(i - lado // 2, i + lado // 2))
    r[sl] = realce
    c[sl] = classe
    return r, c, (k, j, i)


def test_volume_angiovolume_e_realce():
    r, c, semente = _lesao(lado=6)
    c[c > 0] = 6
    c[5, 20, 20] = 0                      # um voxel dentro da lesão que não realça (necrose)
    vol = _vol(r, 1.0, 1.0, 2.0)
    res = segment(vol, semente, "realce", 50.0)
    m = C.medir(vol, c, res)
    assert res.voxels == 6 * 6 * 6
    assert m.ml == pytest.approx(res.voxels * 1.0 * 1.0 * 2.0 / 1000.0)
    assert m.angio_ml < m.ml, "o voxel sem realce fica de fora do angiovolume"
    assert m.fracao_que_realca == pytest.approx((res.voxels - 1) / res.voxels * 100, abs=0.1)
    assert m.realce_pico == pytest.approx(300.0)
    assert m.percentuais["rápido/washout"] == pytest.approx(100.0)


def test_o_maior_diametro_nunca_fica_abaixo_de_um_lado():
    """Saiu "maior diâmetro 3D 26,4 mm" numa lesão de 30 mm de altura.

    O segmentador soma só o menor lado **no plano** ao maior eixo; com corte de 10 mm isso dá um
    número menor que o próprio diâmetro crânio-caudal — e o médico vê a contradição na hora.
    """
    r, c, semente = _lesao(lado=4, forma=(5, 30, 30))
    vol = _vol(r, 1.0, 1.0, 10.0)         # cortes grossos: é aí que o erro aparecia
    res = segment(vol, semente, "realce", 50.0)
    m = C.medir(vol, c, res)
    assert m.maior_3d_mm >= max(m.diametros_mm) - 1e-6, \
        f"maior 3D {m.maior_3d_mm:.1f} < lado {max(m.diametros_mm):.1f}"


def test_heterogeneidade_vai_de_zero_a_um():
    r, c, semente = _lesao(lado=6)
    vol = _vol(r)
    res = segment(vol, semente, "realce", 50.0)
    um_padrao = C.medir(vol, c, res)
    assert um_padrao.heterogeneidade == pytest.approx(0.0), "um padrão só: nada de heterogêneo"
    espalhado = c.copy()
    dentro = np.nonzero(espalhado)
    for n, (k, j, i) in enumerate(zip(*dentro)):
        espalhado[k, j, i] = 1 + n % 6             # os seis padrões em partes iguais
    m = C.medir(vol, espalhado, res)
    assert m.heterogeneidade > 0.98, "seis padrões iguais: heterogeneidade máxima"
    assert sum(m.percentuais.values()) == pytest.approx(100.0, abs=0.01)


def test_avisa_quando_a_regiao_tem_forma_de_vaso():
    """Numa RM de mama tudo o que realça está ligado pelos vasos.

    Medido no acervo real: semente num vaso deu 15 mL com 105 mm de maior diâmetro — a "lesão"
    era a árvore vascular. O programa não decide por ele, mas avisa.
    """
    r = np.zeros((10, 40, 40), np.float32)
    r[5, 20, 4:36] = 300.0                 # um tubo fino e comprido
    c = (r > 0).astype(np.uint8) * 6
    vol = _vol(r)
    res = segment(vol, (5, 20, 20), "realce", 50.0)
    m = C.medir(vol, c, res)
    assert m.alongamento > 3
    assert any("vaso" in a for a in m.avisos)
    # e uma massa compacta não dispara o aviso
    r2, c2, s2 = _lesao(lado=8)
    vol2 = _vol(r2)
    m2 = C.medir(vol2, c2, segment(vol2, s2, "realce", 50.0))
    assert m2.alongamento < 2 and not m2.avisos


def test_limiar_relativo_nao_vaza_onde_o_fixo_vaza():
    """O limiar fixo cresce pelo parênquima e pelos vasos; o relativo à lesão, não.

    No acervo, o fixo de 50% deu **996 mL e 120 mm** a partir de um vaso: isso é a mama, não a
    lesão.
    """
    r = np.full((10, 40, 40), 120.0, np.float32)   # parênquima realçando 120%
    r[4:7, 18:23, 18:23] = 900.0                   # a lesão
    c = np.where(r >= 100, 6, 0).astype(np.uint8)
    vol = _vol(r)
    fixo = segment(vol, (5, 20, 20), "realce", 50.0)
    relativo = segment(vol, (5, 20, 20), "realce_pct", None, None, None, 50.0)
    assert fixo.voxels > 10 * relativo.voxels, "o fixo tem que vazar para o teste provar algo"
    assert relativo.voxels == 3 * 5 * 5
    assert C.medir(vol, c, relativo).ml < C.medir(vol, c, fixo).ml


def test_nada_segmentado_nao_quebra_a_medida():
    r, c, semente = _lesao(realce=80.0)
    vol = _vol(r)
    res = segment(vol, semente, "realce", 500.0)   # limiar acima de tudo
    m = C.medir(vol, c, res)
    assert m.ml == 0 and m.percentuais == {} and m.avisos


# --------------------------------------------------------------------- exame inteiro

def test_numeros_do_exame_sem_o_coracao():
    """O realce de fundo tem que ser o da mama, não o do coração que estava na máscara antiga."""
    import numpy as np
    from ipe.imaging.cad_mama import medir_exame
    from ipe.imaging.mama_mascara import mascara_da_mama
    from tests.test_mama_mascara import SAGITAL, fantoma
    pre, p = fantoma()
    pico = pre.copy()
    pico[p["mama"]] *= 1.3              # mama realça 30%
    pico[p["coracao"]] *= 4.0           # coração realça 300%
    classes = np.zeros(pre.shape, np.uint8)
    classes[p["mama"]] = 2              # médio/platô
    classes[p["coracao"]] = 6
    m, det = mascara_da_mama(pre, 1000.0, SAGITAL, (1.0, 1.0))
    e = medir_exame(pre, pico, classes, m, voxel_ml=0.001, texto_mascara=det["texto"])
    # A mediana é o realce da mama; a média fica abaixo porque a máscara mantém o músculo da
    # parede, que não realça. É por isso que os dois números aparecem na tela.
    assert 29.0 < e.realce_mediana < 31.0, "o realce de fundo não é o da mama"
    assert e.realce_medio < e.realce_mediana
    assert e.angio_ml > 0 and e.percentuais["médio/platô"] == 100.0
    assert "médio/washout" in e.percentuais and e.percentuais["médio/washout"] == 0.0
    assert "Realce de fundo =" in e.formula and det["texto"] in e.mascara
    # sem máscara nenhuma, o coração domina — é a comparação que justifica a máscara
    corpo = pre >= 100.0
    sem = medir_exame(pre, pico, classes, corpo, voxel_ml=0.001)
    assert sem.realce_medio > e.realce_medio * 1.5


def test_exame_sem_mascara_avisa():
    import numpy as np
    from ipe.imaging.cad_mama import medir_exame
    e = medir_exame(np.ones((2, 4, 4), np.float32), np.ones((2, 4, 4), np.float32),
                    np.zeros((2, 4, 4), np.uint8), np.zeros((2, 4, 4), bool), 1.0)
    assert e.avisos and "vazia" in e.avisos[0] and e.mama_ml == 0
