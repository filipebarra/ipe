"""Receitas por exame: esvaziamento gástrico, vesícula, salivares e razão lesão/lado normal."""

import numpy as np
import pytest

from ipe.imaging import nm_exams, nm_roi


def curva(tempos, valores, nome="A", pixels=100):
    t = np.asarray(tempos, float)
    v = np.asarray(valores, float)
    return nm_roi.Curve(nome, t, v, v, np.zeros(t.size), np.ones(t.size), pixels, "roi")


def _esvazia(meia_vida_min=60.0, dur_h=4.0, nome="Estômago"):
    """Curva de esvaziamento exponencial com T½ conhecido."""
    t = np.arange(0, dur_h * 3600 + 1, 300.0)
    v = 1000.0 * np.exp(-np.log(2) * t / (meia_vida_min * 60.0))
    return curva(t, v, nome)


# ------------------------------------------------------------------ registro
def test_todos_os_protocolos_tem_nome_e_regioes():
    for chave in nm_exams.ORDER:
        p = nm_exams.PROTOCOLS[chave]
        assert p.name and p.rois
        assert p.key == chave
    assert nm_exams.protocol("inexistente").key == "livre"


def test_protocolo_livre_da_os_numeros_gerais():
    c = curva([0, 60, 120, 180, 240], [0, 50, 100, 75, 50], "Região")
    res = nm_exams.run("livre", [c])
    assert res.headers[0] == "Região"
    assert res.rows[0][1] == "2.0 min"                  # pico aos 120 s
    assert "pico aos 2.0 min" in res.text
    assert res.reference == ""


# ------------------------------------------------------------------ gástrico
def test_esvaziamento_mede_a_retencao_nos_tempos_do_guia():
    res = nm_exams.run("gastrico", [_esvazia(meia_vida_min=60.0)])
    linha = res.rows[0]
    assert linha[0] == "Estômago"
    assert linha[2] == "50%"                            # 1 h com T½ de 60 min
    assert linha[3] == "25%"                            # 2 h
    assert linha[4] == "6%"                             # 4 h
    assert "60 min" in linha[5]                         # T½ medido bate com o simulado
    assert "retenção" in res.text
    assert "SNMMI" in res.reference


def test_esvaziamento_rapido_e_lento_se_distinguem():
    rapido = nm_exams.run("gastrico", [_esvazia(30.0)]).rows[0]
    lento = nm_exams.run("gastrico", [_esvazia(180.0)]).rows[0]
    assert int(rapido[3].rstrip("%")) < int(lento[3].rstrip("%"))


def test_estudo_curto_avisa_e_nao_inventa_o_ponto_de_4h():
    res = nm_exams.run("gastrico", [_esvazia(dur_h=2.0)])
    assert res.rows[0][4] == "—"                        # 4 h não existe na curva
    assert any("mais curto" in n for n in res.notes)


# ------------------------------------------------------------------ vesícula
def test_fracao_de_ejecao_vesicular():
    t = np.arange(0, 3601.0, 60.0)          # inclui o instante final: a queda completa
    v = np.where(t <= 1800, 1000.0, 1000.0 - 600.0 * (t - 1800) / 1800.0)
    res = nm_exams.run("vesicula", [curva(t, v, "Vesícula")], stimulus_s=1800.0)
    assert res.rows[0][3] == "60%"                      # cai de 1000 para 400
    assert "fração de ejeção de 60%" in res.text
    assert "38%" in res.reference                       # o corte do guia aparece, sem julgar


def test_vesicula_sem_estimulo_avisa_que_usou_o_pico_da_curva():
    t = np.arange(0, 3600.0, 60.0)
    v = 1000.0 - 500.0 * t / 3600.0
    res = nm_exams.run("vesicula", [curva(t, v, "Vesícula")])
    assert any("sem o instante do estímulo" in n.lower() for n in res.notes)


def test_vesicula_sem_contagem_nao_calcula():
    t = np.arange(0, 600.0, 60.0)
    res = nm_exams.run("vesicula", [curva(t, np.zeros(t.size), "Vesícula")], stimulus_s=300.0)
    assert res.rows[0][3] == "—"
    assert any("não dá para calcular" in n for n in res.notes)


# ------------------------------------------------------------------ salivares
def test_salivar_reparte_a_captacao_entre_as_glandulas():
    t = np.arange(0, 1800.0, 60.0)
    forte = curva(t, np.minimum(t / 600.0, 1.0) * 300.0, "Parótida direita")
    fraca = curva(t, np.minimum(t / 600.0, 1.0) * 100.0, "Parótida esquerda")
    res = nm_exams.run("salivar", [forte, fraca], stimulus_s=1200.0)
    assert res.rows[0][1] == "75%" and res.rows[1][1] == "25%"
    assert sum(int(r[1].rstrip("%")) for r in res.rows) == 100


def test_salivar_mede_a_excrecao_depois_do_estimulo():
    t = np.arange(0, 1801.0, 60.0)
    v = np.where(t <= 1200, 400.0, 400.0 - 300.0 * (t - 1200) / 600.0)
    res = nm_exams.run("salivar", [curva(t, v, "Parótida direita")], stimulus_s=1200.0)
    assert res.rows[0][2] == "75%"
    assert "excreção de 75%" in res.text


def test_salivar_sem_estimulo_nao_inventa_excrecao():
    t = np.arange(0, 1800.0, 60.0)
    res = nm_exams.run("salivar", [curva(t, t * 0 + 100.0, "Parótida direita")])
    assert res.rows[0][2] == "—"
    assert any("estímulo" in n for n in res.notes)


# ------------------------------------------------------------------ razão
def test_razao_lesao_lado_normal():
    t = np.arange(0, 600.0, 60.0)
    lesao = curva(t, np.full(t.size, 300.0), "Lesão", pixels=100)
    normal = curva(t, np.full(t.size, 100.0), "Lado normal", pixels=100)
    res = nm_exams.run("razao", [lesao, normal])
    assert res.rows[0][2] == "3.00"
    assert "razão de 3.00" in res.text


def test_razao_com_areas_diferentes_avisa():
    t = np.arange(0, 600.0, 60.0)
    a = curva(t, np.full(t.size, 300.0), "Lesão", pixels=100)
    b = curva(t, np.full(t.size, 200.0), "Lado normal", pixels=50)
    res = nm_exams.run("razao", [a, b])
    assert any("áreas diferentes" in n for n in res.notes)


def test_razao_com_uma_regiao_so_avisa():
    t = np.arange(0, 600.0, 60.0)
    res = nm_exams.run("razao", [curva(t, np.full(t.size, 300.0), "Lesão")])
    assert res.rows == []
    assert any("duas regiões" in n for n in res.notes)


# ------------------------------------------------------------------ renograma pela receita
def test_renograma_pela_receita_bate_com_o_modulo():
    from ipe.imaging import renogram
    t = np.arange(0, 1200.0, 15.0)
    d = curva(t, 100 * (1 - np.exp(-t / 90)) * np.exp(-np.clip(t - 180, 0, None) / 200), "Rim direito")
    e = curva(t, 100 * (1 - np.exp(-t / 90)) * np.exp(-np.clip(t - 180, 0, None) / 200), "Rim esquerdo")
    res = nm_exams.run("renograma", [d, e])
    assert res.headers == renogram.SUMMARY_HEADERS
    assert len(res.rows) == 2
    assert "função relativa" in res.text
