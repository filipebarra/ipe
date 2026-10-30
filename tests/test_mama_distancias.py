"""Distâncias da lesão à pele, ao mamilo e à parede torácica (RM de mama).

Pedido dele: "na segmentação de lesões das mamas, queria ter distância da lesão para a pele,
mamilo e peitoral". As três referências foram medidas nos três exames reais de RM de mama antes de
virar número na tela: nos 6 seios o mamilo automático caiu no ápice da cúpula da pele (a 30 mm de
distância a pele já está 8 a 25 mm atrás do ponto), a profundidade mamilo→parede deu 24 a 58 mm, e
sondas no meio do caminho deram 4 a 15 mm de pele e 12 a 29 mm de parede. Depois das referências
prontas, cada lesão sai em 0,04 s.

O fantoma aqui é geométrico de propósito: com a forma conhecida, dá para exigir o número exato.
"""
import numpy as np
import pytest

from ipe.imaging import mama_distancias as MD

# volume (nz, ny, nx) de 1 mm, axial: i -> x (direita-esquerda), j -> y (posterior), k -> z
AXIAL = [1.0, 0, 0, 0, 1.0, 0]
PASSO_Z = np.array([0.0, 0.0, 1.0])
AFIM = MD.afim_do_volume(np.zeros(3), AXIAL, 1.0, 1.0, PASSO_Z)


def _fantoma():
    """Tórax de brinquedo com a anatomia que importa, em 1 mm:

    - corpo (tecido) de y=20 a y=60: mama + parede;
    - **pulmão** (escuro) de y=60 a y=90: 30 mm, o trecho escuro longo que marca a parede;
    - costas (tecido) de y=90 a y=110, com a pele das costas, que **não** é pele da mama;
    - duas cúpulas anteriores (os mamilos) em y=14;
    - um buraco interno de gordura, que não é pele.
    """
    corpo = np.zeros((40, 130, 120), bool)
    corpo[:, 20:60, 10:110] = True             # mama + parede
    corpo[:, 90:110, 10:110] = True            # costas
    zz, yy, xx = np.mgrid[0:40, 0:130, 0:120]
    for cx in (40, 80):
        corpo |= ((xx - cx) ** 2 + ((yy - 26) * 1.0) ** 2 + ((zz - 20) * 1.0) ** 2) <= 12 ** 2
    corpo[:, 40:50, 40:50] = False             # buraco interno: não é pele
    return corpo


def _fantoma_reto():
    """O mesmo sem as cúpulas: pele exatamente em y=20, parede exatamente em y=59."""
    corpo = np.zeros((40, 130, 120), bool)
    corpo[:, 20:60, 10:110] = True
    corpo[:, 90:110, 10:110] = True
    return corpo


def test_eixo_anterior_posterior_do_volume():
    assert MD.eixo_ap_do_volume(AXIAL, PASSO_Z) == (1, 1)              # axial: anda nas linhas
    sagital = [0, 1.0, 0, 0, 0, -1.0]
    assert MD.eixo_ap_do_volume(sagital, np.array([-1.0, 0, 0])) == (2, 1)   # como no acervo dele
    coronal = [1.0, 0, 0, 0, 0, -1.0]
    assert MD.eixo_ap_do_volume(coronal, np.array([0.0, 1.0, 0])) == (0, 1)  # anda entre cortes
    assert MD.eixo_ap_do_volume(coronal, np.array([0.0, -1.0, 0])) == (0, -1)
    # oblíquo de verdade: nenhum eixo é A-P, e isso tem de ser dito
    obl = [0.72, 0.69, 0, 0, 0, -1.0]
    assert MD.eixo_ap_do_volume(obl, np.array([0.69, -0.72, 0.0])) == (-1, 0)
    # um sagital inclinado de verdade (uns 15°) continua tendo parede torácica
    inclinado = [0.0, 0.97, 0.26, 0, 0, -1.0]
    assert MD.eixo_ap_do_volume(inclinado, np.array([-1.0, 0, 0])) == (2, 1)
    assert MD.eixo_ap_do_volume([1, 0, 0], PASSO_Z) == (-1, 0)


def test_buraco_interno_nao_e_pele():
    """A máscara é por limiar e é cheia de buracos: borda de buraco não é pele."""
    corpo = _fantoma()
    p = MD.pele(corpo)
    assert p[20, 20, 60], "a superfície anterior tem de ser pele"
    assert not p[20, 41, 41], "a parede do buraco interno virou pele"
    assert not p[20, 40, 60], "voxel interno virou pele"
    fora = MD.ar_de_fora(corpo)
    assert fora[20, 0, 0] and not fora[20, 45, 45], "o buraco interno entrou no ar de fora"


def test_a_parede_e_o_tecido_que_encosta_no_pulmao():
    """A parede sai do perfil da linha: o último tecido antes do trecho escuro longo."""
    corpo = _fantoma_reto()
    pele_mask = MD.pele(corpo)
    parede, pele_mama = MD.parede_e_pele(corpo, pele_mask, 1, 1, 1.0)
    assert parede[20, 59, 60] and not parede[20, 58, 60], "a parede não caiu em y=59"
    assert not parede[20, 109, 60], "a pele das costas virou parede"
    assert pele_mama[20, 20, 60], "a pele da mama saiu da nuvem"
    assert not pele_mama[20, 109, 60], "a pele das costas ficou na nuvem da pele da mama"
    assert not pele_mama[20, 90, 60], "a pele interna das costas ficou na nuvem"
    vazia, toda = MD.parede_e_pele(corpo, pele_mask, -1, 0, 1.0)
    assert vazia.sum() == 0 and toda is pele_mask, "plano oblíquo não inventa parede"


def test_bolsa_de_ar_curta_nao_e_pulmao():
    """O defeito medido: bolsa de ar de poucos milímetros fazia a parede saltar 49 mm."""
    corpo = _fantoma_reto()
    corpo[:, 30:36, 55:65] = False          # 6 mm de escuro dentro da mama
    parede, _pele = MD.parede_e_pele(corpo, MD.pele(corpo), 1, 1, 1.0)
    assert parede[20, 59, 60], "a parede foi para a bolsa de ar"
    assert not parede[20, 29, 60]
    # trecho escuro de 25 mm já conta como pulmão
    ini = MD._primeiro_escuro_longo(corpo, 1, 1, 1.0, 20.0)
    assert int(ini[20, 60]) == 60, int(ini[20, 60])
    assert int(MD._primeiro_escuro_longo(corpo, 1, 1, 1.0, 5.0)[20, 60]) == 30, "5 mm pega a bolsa"


def test_mamilo_e_o_apice_de_cada_lado():
    corpo = _fantoma()
    pele_mm = MD.para_mm(np.stack(np.nonzero(MD.pele(corpo)), 1), AFIM)
    mamilos = MD.mamilos_automaticos(pele_mm)
    assert len(mamilos) == 2
    xs = sorted(float(m[0]) for m in mamilos)
    assert xs == pytest.approx([40, 80], abs=2), "os ápices não caíram nos dois seios"
    for m in mamilos:
        assert float(m[1]) == pytest.approx(14, abs=1.5), "o mamilo não é o ponto mais anterior"


def test_as_duas_passadas_dao_o_mesmo_que_a_forca_bruta():
    rng = np.random.default_rng(7)
    nuvem = rng.normal(0, 30, (4000, 3))
    pontos = rng.normal(50, 2, (40, 3))
    bruta = min(float(np.linalg.norm(p - q)) for p in pontos for q in nuvem)
    assert MD.menor_distancia(pontos, nuvem[::7], nuvem) == pytest.approx(bruta, abs=1e-6)
    assert np.isnan(MD.menor_distancia(pontos, np.zeros((0, 3))))


def test_os_tres_numeros_na_geometria_conhecida():
    """Laje: pele em y=20, parede em y=59, lesão de raio 4 centrada em y=40 -> 16 e 15 mm."""
    corpo = _fantoma_reto()
    refs = MD.construir(corpo, AFIM, AXIAL, PASSO_Z)
    assert not refs.avisos
    zz, yy, xx = np.mgrid[0:40, 0:130, 0:120]
    lesao = ((xx - 40) ** 2 + (yy - 40) ** 2 + (zz - 20) ** 2) <= 16
    pontos = MD.para_mm(np.stack(np.nonzero(lesao), 1), AFIM)
    d = MD.distancias(refs, pontos)
    assert d["pele"] == pytest.approx(16, abs=1), "distância à pele fora do esperado"
    assert d["posterior"] == pytest.approx(15, abs=1), "distância à parede fora do esperado"
    assert d["mamilo_centro"] > d["mamilo"], "o centro não pode estar mais perto que a borda"
    assert not d["mamilo_manual"]
    rotulos = dict(MD.linhas(d))
    assert "Distância à pele" in rotulos and "automático" in rotulos["Distância ao mamilo"]
    assert "Distância ao peitoral (parede torácica)" in rotulos


def test_o_mamilo_marcado_manda_e_a_tela_diz():
    corpo = _fantoma()
    refs = MD.construir(corpo, AFIM, AXIAL, PASSO_Z)
    ponto = np.array([[45.0, 40.0, 20.0]])
    antes = MD.distancias(refs, ponto)
    refs.manual = np.array([45.0, 10.0, 20.0])          # mamilo apontado pelo médico
    depois = MD.distancias(refs, ponto)
    assert depois["mamilo"] == pytest.approx(30, abs=1)
    assert depois["mamilo"] != pytest.approx(antes["mamilo"], abs=1)
    assert depois["mamilo_manual"] and "marcado" in dict(MD.linhas(depois))["Distância ao mamilo"]


def test_plano_obliquo_nao_da_numero_de_peitoral():
    corpo = _fantoma()
    obl = [0.72, 0.69, 0, 0, 0, -1.0]
    refs = MD.construir(corpo, AFIM, obl, np.array([0.69, -0.72, 0.0]))
    assert len(refs.posterior) == 0
    assert refs.avisos and "oblíquo" in refs.avisos[0]
    d = MD.distancias(refs, np.array([[45.0, 40.0, 20.0]]))
    assert np.isnan(d["posterior"])
    assert not any(r[0].startswith("Distância ao peitoral") for r in MD.linhas(d))


def test_superficie_da_lesao_e_a_borda_em_mm():
    mask = np.zeros((5, 5, 5), bool)
    mask[1:4, 1:4, 1:4] = True
    pontos = MD.superficie_da_lesao(mask, (10, 20, 30), AFIM)
    assert len(pontos) == 26, "o miolo do cubo entrou na superfície"
    assert pontos[:, 0].min() == 31 and pontos[:, 1].min() == 21 and pontos[:, 2].min() == 11
    assert len(MD.superficie_da_lesao(np.zeros((3, 3, 3), bool), (0, 0, 0), AFIM)) == 0


def test_afim_do_objeto_nao_troca_linha_com_coluna():
    """`Volume.row_dir` é a direção de **i**: trocar põe a lesão no lugar errado do paciente."""
    class _Vol:
        origin = np.array([5.0, 6.0, 7.0])
        row_dir = np.array([1.0, 0, 0])
        col_dir = np.array([0, 1.0, 0])
        slice_vec = np.array([0, 0, 2.0])
        dx, dy = 0.5, 0.25
    afim = MD.afim_do_objeto(_Vol())
    p = MD.para_mm(np.array([[3, 2, 4]]), afim)[0]        # (k=3, j=2, i=4)
    assert p == pytest.approx([5 + 4 * 0.5, 6 + 2 * 0.25, 7 + 3 * 2.0])


# ------------------------------------------------------------------ ligação com a janela
def test_o_clique_do_mamilo_passa_na_frente_do_clique_de_segmentar():
    """Marcar o mamilo é um clique com a mesma ferramenta: não pode virar lesão nova."""
    from ipe.ui.viewer.onco import OncoMixin

    class _Janela:
        def __init__(self):
            self.visivel = True
            self.clicado = None

        def isVisible(self):
            return self.visivel

        def mamilo_clicado(self, vp, u, v):
            self.clicado = (u, v)

    class _Aba:
        segment_at = OncoMixin.segment_at
        dyn = None
        seguiu = False

        def _seg_sem_resultado(self, _motivo):
            self.seguiu = True        # só chega aqui se o clique não foi consumido

        def _source_series(self, _vp):
            return None

    aba = _Aba()
    janela = _Janela()
    aba._mamilo_pendente = janela
    aba.segment_at(object(), 10.0, 20.0)
    assert janela.clicado == (10.0, 20.0) and not aba.seguiu
    assert aba._mamilo_pendente is None, "o pedido tem de valer por um clique só"
    # janela fechada: o clique volta a ser de segmentação (e cai no caminho normal)
    class _VpVazio:
        mpr_plane = None
        frames = []
    aba._mamilo_pendente = _Janela()
    aba._mamilo_pendente.visivel = False
    try:
        aba.segment_at(_VpVazio(), 1.0, 2.0)
    except (AttributeError, TypeError):
        pass            # seguiu para o caminho normal e lá faltou o resto da aba de mentira
    assert aba._mamilo_pendente is None


def test_o_mamilo_clicado_vira_o_ponto_que_vale():
    from ipe.ui.viewer.onco import SegmentDialog

    class _Vp:
        @staticmethod
        def pixel_to_patient(_u, _v):
            return np.array([45.0, 10.0, 20.0])

    class _Aba:
        class _Sinal:
            @staticmethod
            def emit(_t):
                pass
        status_message = _Sinal()

    corpo = _fantoma_reto()
    dlg = SegmentDialog.__new__(SegmentDialog)
    dlg.tab = _Aba()
    dlg.refs = MD.construir(corpo, AFIM, AXIAL, PASSO_Z)
    dlg.res = None
    dlg.dist = {}
    dlg.atualizar_distancias = lambda: None
    dlg.mamilo_clicado(_Vp(), 1.0, 2.0)
    assert dlg.refs.manual is not None
    d = MD.distancias(dlg.refs, np.array([[45.0, 40.0, 20.0]]))
    assert d["mamilo_manual"] and d["mamilo"] == pytest.approx(30, abs=1)


def test_as_distancias_entram_na_medida_guardada():
    """Desde a 0.67 só o mamilo vai para a medida (pedido dele: tirar pele e peitoral)."""
    from ipe.ui.viewer.onco import SegmentDialog
    dlg = SegmentDialog.__new__(SegmentDialog)
    dlg.dist = {"pele": 8.44, "mamilo": 42.2, "mamilo_centro": 50.1, "posterior": 15.0,
                "mamilo_manual": True, "centro_mm": np.zeros(3)}
    meta = dlg.distancias_meta()
    assert meta == {"dist_mamilo_mm": 42.2, "dist_mamilo_centro_mm": 50.1, "mamilo_marcado": True}
    dlg.dist = {"pele": float("nan"), "posterior": 3.0}
    assert dlg.distancias_meta() == {}, "pele e peitoral não vão mais ao laudo"
    dlg.dist = {}
    assert dlg.distancias_meta() == {}
