"""0.100.55: escalas das calcificações arteriais da mama (Margolies, CSBI, Loberant, BAC-SS) estimadas pela máscara."""
import numpy as np
import pytest

cv2 = pytest.importorskip("cv2")

from ipe.ai import calc_vascular_escalas as E  # noqa: E402

P = 0.1


def _mama():
    img = np.zeros((1000, 800), np.uint8)
    img[:, :600] = 120  # 60 mm de profundidade
    return img


def _desenho():
    m = np.zeros((1000, 800), np.uint8)
    cv2.line(m, (50, 100), (300, 100), 1, 2)   # trilho: duas paredes a 1,5 mm, 25 mm
    cv2.line(m, (50, 115), (300, 115), 1, 2)
    cv2.line(m, (100, 500), (200, 520), 1, 14)  # sem luz: 1,4 mm de espessura
    cv2.line(m, (100, 800), (160, 860), 1, 2)   # linear fino
    for k in range(5):
        cv2.circle(m, (500, 200 + 60 * k), 3, 1, -1)  # puntiformes
    return m.astype(bool)


def test_caracteristicas():
    c = E.caracteristicas(_desenho(), _mama(), P)
    assert c["profundidade_mm"] == 60.0 and c["puntiformes"] == 5
    assert len(c["vasos"]) == 3
    trilho = [v for v in c["vasos"] if v["trilho"]]
    assert len(trilho) == 1 and 24 <= trilho[0]["comprimento_mm"] <= 27 and not trilho[0]["opaco"]
    assert sum(v["opaco"] for v in c["vasos"]) == 1


def test_escalas():
    c = E.caracteristicas(_desenho(), _mama(), P)
    vazio = E.caracteristicas(np.zeros((1000, 800), bool), _mama(), P)
    imgs = [{"chave": "R-MLO", "lado": "R", "incidencia": "MLO", "extra": False, "tracado": c},
            {"chave": "R-CC", "lado": "R", "incidencia": "CC", "extra": False, "tracado": vazio},
            {"chave": "L-MLO", "lado": "L", "incidencia": "MLO", "extra": False, "tracado": vazio},
            {"chave": "L-CC", "lado": "L", "incidencia": "CC", "extra": True, "tracado": c}]  # ampliação: fora
    e = E.calcular(imgs)
    d = e["margolies"]["por_mama"]["R"]
    assert (d["vasos"], d["extensao"], d["densidade"], d["total"]) == (3, 2, 3, 8)
    assert e["margolies"]["por_mama"]["L"]["total"] == 0
    assert e["margolies"]["total"] == 8 and e["margolies"]["categoria"] == "moderada_acentuada"
    assert e["csbi"]["grau"] == 3 and e["loberant"]["grau"] == 3
    b = e["bacss"]["por_mama"]["R"]
    assert (b["nv"], b["ov"], b["l"]) == (3, 1, 3) and e["bacss"]["maior"] == 7
    assert len(E.resumo(e)) == 4


def test_sem_nada_e_medida_antiga():
    vazio = E.caracteristicas(np.zeros((1000, 800), bool), _mama(), P)
    e = E.calcular([{"chave": "R-MLO", "lado": "R", "incidencia": "MLO", "extra": False, "tracado": vazio}])
    assert e["margolies"]["total"] == 0 and e["csbi"]["grau"] == 0 and e["loberant"]["grau"] == 0
    assert e["bacss"]["maior"] == 0 and e["margolies"]["categoria"] == "negativa"
    assert E.calcular([{"chave": "R-MLO", "lado": "R", "area_mm2": 3.0}]) is None  # antes da 0.100.55
    # só puntiformes: CSBI 1, Loberant 1
    m = np.zeros((1000, 800), np.uint8)
    for k in range(4):
        cv2.circle(m, (300, 200 + 80 * k), 3, 1, -1)
    e = E.calcular([{"chave": "R-MLO", "lado": "R", "incidencia": "MLO", "extra": False,
                         "tracado": E.caracteristicas(m.astype(bool), _mama(), P)}])
    assert e["csbi"]["grau"] == 1 and e["loberant"]["grau"] == 1 and e["margolies"]["total"] == 0
