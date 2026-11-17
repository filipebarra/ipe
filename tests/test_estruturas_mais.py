"""0.100.67: estruturas — tesoura, oco, suavização, Otsu, dividir ilhas, contorno por nível, crescer de sementes e a
segmentação pelo maior diâmetro."""
import numpy as np
import pytest

from ipe.imaging import estruturas as ES
from ipe.imaging import estruturas_mais as EM
from ipe.imaging.volume import Volume


def _vol(nz=20, n=64, dz=2.0, dxy=1.0, ruido=0.0, fundo=0.0, lesao=100.0, r=12.0, rz=5.0):
    z, y, x = np.mgrid[0:nz, 0:n, 0:n]
    d = np.full((nz, n, n), fundo, np.float32)
    d[((x - n / 2) / r) ** 2 + ((y - n / 2) / r) ** 2 + ((z - nz / 2) / rz) ** 2 < 1] = lesao
    if ruido:
        d += np.random.default_rng(3).normal(0, ruido, d.shape).astype(np.float32)
    return Volume(d, np.array([-10.0, -20.0, 5.0]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
                  np.array([0, 0, dz]), dxy, dxy, None, "")


def _bloco(g, k0, k1, j0, j1, i0, i1, nome="a"):
    e = ES.Estrutura(nome, (255, 0, 0))
    m = np.zeros(g.forma, bool)
    m[k0:k1, j0:j1, i0:i1] = True
    e.definir(m)
    return e


def _quadrado(g, k, j0, j1, i0, i1):
    return g.para_mm([[i0, j0, k], [i1, j0, k], [i1, j1, k], [i0, j1, k]])


# ---------------------------------------------------------------- tesoura
def test_tesoura_apaga_dentro_no_corte_e_no_volume():
    g = ES.Grade.do_volume(_vol())
    e = _bloco(g, 5, 15, 20, 40, 20, 40)
    antes = e.cheia(g)
    q = _quadrado(g, 10, 24.5, 30.5, 24.5, 30.5)                # pixels 25..30 (6 × 6)
    assert EM.tesoura(e, g, q, [0, 0, 1], "apagar_dentro", "corte") == -36
    c = e.cheia(g)
    assert not c[10, 25:31, 25:31].any() and c[10, 24, 24] and (c[9] == antes[9]).all() and (c[11] == antes[11]).all()
    assert EM.tesoura(e, g, q, [0, 0, 1], "apagar_dentro", "volume") == -36 * 9
    assert not e.cheia(g)[:, 25:31, 25:31].any()


def test_tesoura_apaga_fora_preenche_e_respeita_travada_e_limites():
    v = _vol()
    g = ES.Grade.do_volume(v)
    e = _bloco(g, 5, 15, 20, 40, 20, 40)
    q = _quadrado(g, 10, 24.5, 30.5, 24.5, 30.5)
    EM.tesoura(e, g, q, [0, 0, 1], "apagar_fora", "corte")
    c = e.cheia(g)
    assert c[10].sum() == 36 and c[9].sum() == 400              # só o corte mudou
    EM.tesoura(e, g, q, [0, 0, 1], "apagar_fora", "volume")
    assert e.voxels == 36 * 10
    n = ES.Estrutura("n", (0, 255, 0))
    assert EM.tesoura(n, g, q, [0, 0, 1], "preencher", "corte") == 36
    assert n.offset[0] == 10 and n.mascara.shape[0] == 1
    t = ES.Estrutura("t", (0, 255, 0))
    assert EM.tesoura(t, g, q, [0, 0, 1], "preencher", "volume") == 36 * 20
    f = ES.Estrutura("f", (0, 0, 255))                           # só na faixa: a "lesão" (raio 12, tudo dentro)
    lim = ES.Limites(faixa=(50, 150), dados=v.data)
    EM.tesoura(f, g, _quadrado(g, 10, 10.5, 50.5, 10.5, 50.5), [0, 0, 1], "preencher", "corte", limites=lim)
    assert f.voxels == int((v.data[10] == 100).sum())
    p = ES.Estrutura("p", (9, 9, 9))
    n.travada = True
    EM.tesoura(p, g, q, [0, 0, 1], "preencher", "corte", proibidas=[n])
    assert p.vazia()
    assert EM.tesoura(n, g, q, [0, 0, 1], "apagar_dentro", "volume") == 0     # travada não muda


def test_tesoura_em_plano_coronal_e_forma_livre():
    g = ES.Grade.do_volume(_vol())
    e = _bloco(g, 2, 18, 20, 40, 20, 40)
    # plano coronal (normal = y): um retângulo em x–z, na linha j = 30
    q = g.para_mm([[24.5, 30, 4.5], [30.5, 30, 4.5], [30.5, 30, 9.5], [24.5, 30, 9.5]])
    assert EM.tesoura(e, g, q, [0, 1, 0], "apagar_dentro", "corte") == -6 * 5
    assert not e.cheia(g)[5:10, 30, 25:31].any() and e.cheia(g)[5:10, 29, 25:31].all()
    # elipse pela forma pronta
    e1, e2, _n = EM._base_do_plano([0, 0, 1])
    el = EM.forma_da_tesoura("elipse", g.para_mm([20, 20, 10])[0], g.para_mm([40, 40, 10])[0], e1, e2)
    o = ES.Estrutura("o", (1, 2, 3))
    EM.tesoura(o, g, el, [0, 0, 1], "preencher", "corte")
    assert abs(o.voxels - np.pi * 100) < 25                      # círculo de raio 10 px
    assert EM.forma_da_tesoura("retangulo", [0, 0, 0], [3, 4, 0], e1, e2).shape == (4, 3)


def test_poligono_concavo():
    poli = np.array([[0, 0], [10, 0], [10, 10], [5, 3], [0, 10]], float)      # um "M"
    px, py = np.array([2.0, 5.0, 8.0, 5.0]), np.array([5.0, 6.0, 5.0, 1.0])
    assert EM.dentro_do_poligono(px, py, poli).tolist() == [True, False, True, True]


# ---------------------------------------------------------------- oco e suavização
def test_oco_dentro_fora_meio():
    g = ES.Grade.do_volume(_vol(dz=1.0))
    e = _bloco(g, 4, 16, 20, 40, 20, 40)
    antes = e.cheia(g)
    EM.oco(e, g, 2.0, "dentro")
    c = e.cheia(g)
    assert (c <= antes).all() and c[4, 30, 30] and c[10, 20, 30] and not c[10, 30, 30]
    assert not c[6:14, 22:38, 22:38].any() and c.sum() == antes.sum() - 8 * 16 * 16
    f = _bloco(g, 4, 16, 20, 40, 20, 40)
    EM.oco(f, g, 2.0, "fora")
    cf = f.cheia(g)
    assert not (cf & antes).any() and cf[10, 18, 30] and cf[2, 30, 30] and not cf[10, 17, 30]
    m = _bloco(g, 4, 16, 20, 40, 20, 40)
    EM.oco(m, g, 2.0, "meio")
    cm = m.cheia(g)
    assert cm[10, 19, 30] and cm[10, 20, 30] and not cm[10, 21, 30] and not cm[10, 18, 30]
    assert EM.oco(m, g, 0.2, "dentro") == 0                      # menor que um voxel: nada


def test_suavizar_mediana_abertura_fechamento():
    g = ES.Grade.do_volume(_vol(dz=1.0))
    base = np.zeros(g.forma, bool)
    base[5:15, 20:40, 20:40] = True
    ponta = base.copy()
    ponta[10, 30, 40:46] = True                                  # um fio de 1 voxel para fora
    furo = base.copy()
    furo[10, 30, 30] = False
    for metodo in ("mediana", "abertura"):
        e = ES.Estrutura("a", (1, 1, 1))
        e.definir(ponta)
        assert EM.suavizar(e, g, metodo, 1.5) > 0
        assert not e.cheia(g)[10, 30, 41:46].any() and e.cheia(g)[10, 30, 30], metodo
    for metodo in ("mediana", "fechamento"):
        e = ES.Estrutura("a", (1, 1, 1))
        e.definir(furo)
        EM.suavizar(e, g, metodo, 1.5)
        assert e.cheia(g)[10, 30, 30], metodo
    e = ES.Estrutura("a", (1, 1, 1))
    e.definir(furo)
    EM.suavizar(e, g, "fechamento", 1.5)
    assert (e.cheia(g) == base).all()                            # o fechamento só fecha o furo
    e.travada = True
    assert EM.suavizar(e, g, "mediana", 3) == 0


# ---------------------------------------------------------------- Otsu e ilhas
def test_otsu_e_preencher_pela_faixa():
    v = _vol(ruido=6.0)
    g = ES.Grade.do_volume(v)
    t = EM.otsu_da_regiao(v.data, passo=1)
    assert 30 < t < 70
    assert 30 < EM.limiar_otsu(np.r_[np.zeros(500), np.full(40, 100.0)]) < 70    # classes desiguais
    assert EM.limiar_otsu([5, 5, 5]) == 5 and EM.limiar_otsu([]) == 0
    e = ES.Estrutura("a", (1, 1, 1))
    EM.preencher_pela_faixa(e, g, v.data, t, 1e9)
    real = _vol().data == 100
    c = e.cheia(g)
    assert (c & real).sum() / (c | real).sum() > 0.98
    # só dentro de outra estrutura
    caixa = _bloco(g, 0, 20, 0, 32, 0, 64, "caixa")
    d = ES.Estrutura("d", (1, 1, 1))
    EM.preencher_pela_faixa(d, g, v.data, t, 1e9, limites=ES.Limites(area="dentro", alvo=caixa))
    assert d.voxels and d.cheia(g)[:, 32:, :].sum() == 0
    # Otsu só dentro de uma estrutura: metade lesão, metade fundo
    assert 30 < EM.otsu_da_regiao(v.data, dentro=_bloco(g, 8, 12, 20, 44, 10, 54)) < 70


def test_dividir_ilhas():
    g = ES.Grade.do_volume(_vol())
    m = np.zeros(g.forma, bool)
    m[5:15, 10:30, 10:30] = True       # 4000
    m[5:10, 40:50, 40:50] = True       # 500
    m[2:4, 2:6, 2:6] = True            # 32
    m[18, 60, 60] = True               # 1
    e = ES.Estrutura("Lesão", (255, 0, 0), tipo="lesão")
    e.definir(m)
    novas = EM.dividir_ilhas(e, g, min_ml=0.01)                  # 1 voxel = 0,002 mL: o voxel solto some
    assert [x.voxels for x in novas] == [500, 32] and e.voxels == 4000
    assert [x.nome for x in novas] == ["Lesão 2", "Lesão 3"] and novas[0].cor != novas[1].cor
    assert not (novas[0].cheia(g) & e.cheia(g)).any()
    assert EM.dividir_ilhas(e, g) == []                          # uma ilha só: nada a dividir
    x = ES.Estrutura("x", (1, 1, 1))
    x.definir(m)
    assert len(EM.dividir_ilhas(x, g, maximo=2)) == 1


# ---------------------------------------------------------------- contorno por nível
def test_contorno_por_nivel():
    n, nz = 64, 20
    z, y, x = np.mgrid[0:nz, 0:n, 0:n]
    r = np.sqrt((x - 32.0) ** 2 + (y - 32.0) ** 2)
    d = np.clip(200 - 10 * r, 0, None).astype(np.float32)        # um cone: 200 no centro, 0 a 20 px
    d[:, 32, 32] = 0                                             # um furo no meio
    v = Volume(d, np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 2.0]), 1, 1, None, "")
    g = ES.Grade.do_volume(v)
    m, caixa = EM.contorno_por_nivel(d, g, g.para_mm([40, 32, 7])[0], [0, 0, 1])    # r = 8 → nível 120
    assert caixa[:2] == (7, 8) and m.shape[0] == 1
    assert abs(m.sum() - np.pi * 64) < 20 and m[0, 32 - caixa[2], 32 - caixa[4]]     # o furo foi fechado
    e = ES.Estrutura("a", (1, 1, 1))
    assert EM.aplicar_mascara(e, g, m, caixa) == m.sum()
    m2, c2 = EM.contorno_por_nivel(d, g, g.para_mm([36, 32, 7])[0], [0, 0, 1])       # mais para dentro: menor
    assert m2.sum() < m.sum()
    assert EM.aplicar_mascara(e, g, m2, c2, apagar=True) == -m2.sum()
    assert EM.contorno_por_nivel(d, g, g.para_mm([2, 2, 7])[0], [0, 0, 1]) is None   # no fundo: o corte todo
    assert EM.contorno_por_nivel(d, g, g.para_mm([200, 2, 7])[0], [0, 0, 1]) is None
    m4, _c4 = EM.contorno_por_nivel(300 - d, g, g.para_mm([40, 32, 7])[0], [0, 0, 1])   # lesão escura: o mesmo
    assert abs(int(m4.sum()) - int(m.sum())) <= 2
    # num plano coronal: o cone vira uma faixa ao longo dos cortes
    m3, c3 = EM.contorno_por_nivel(d, g, g.para_mm([40, 33, 7])[0], [0, 1, 0])
    assert m3.shape[1] == 1 and c3[2:4] == (33, 34) and m3.shape[0] == nz


# ---------------------------------------------------------------- crescer de sementes
def test_crescer_de_sementes_separa_lesao_do_fundo():
    v = _vol(ruido=4.0, fundo=20.0)
    g = ES.Grade.do_volume(v)
    real = _vol().data == 100
    lesao, fundo = ES.Estrutura("Lesão", (255, 0, 0)), ES.Estrutura("Fundo", (0, 0, 255))
    ES.pintar(lesao, g, g.para_mm([32, 32, 10])[0], 3.0, normal=[0, 0, 1])
    for p in ([10, 32, 10], [54, 32, 10], [32, 10, 10], [32, 54, 10], [32, 32, 1], [32, 32, 18]):
        ES.pintar(fundo, g, g.para_mm(p)[0], 2.5, normal=[0, 0, 1])
    out = EM.crescer_de_sementes([lesao, fundo], g, v.data, margem_mm=6)
    assert out[lesao.id] > 1000
    c = lesao.cheia(g)
    assert (c & real).sum() / (c | real).sum() > 0.93
    assert not (c & fundo.cheia(g)).any()
    with pytest.raises(ValueError):
        EM.crescer_de_sementes([lesao], g, v.data)


def test_crescer_de_sementes_travada_nao_muda_e_amostrado(monkeypatch):
    v = _vol(ruido=4.0, fundo=20.0)
    g = ES.Grade.do_volume(v)
    real = _vol().data == 100
    lesao, fundo = ES.Estrutura("Lesão", (255, 0, 0)), ES.Estrutura("Fundo", (0, 0, 255))
    ES.pintar(lesao, g, g.para_mm([32, 32, 10])[0], 3.0)
    for p in ([8, 32, 10], [56, 32, 10], [32, 8, 10], [32, 56, 10], [32, 32, 1], [32, 32, 18]):
        ES.pintar(fundo, g, g.para_mm(p)[0], 3.0)
    fundo.travada = True
    antes = fundo.voxels
    monkeypatch.setattr(EM, "MAX_VOXELS_SEMENTES", 20_000)        # força a amostragem (fator 2)
    out = EM.crescer_de_sementes([lesao, fundo], g, v.data, margem_mm=4)
    assert fundo.id not in out and fundo.voxels == antes
    c = lesao.cheia(g)
    assert (c & real).sum() / (c | real).sum() > 0.8
    with pytest.raises(InterruptedError):
        EM.crescer_de_sementes([lesao, fundo], g, v.data, cancelar=lambda: True)


# ---------------------------------------------------------------- pelo maior diâmetro
@pytest.mark.parametrize("fundo,lesao", [(20.0, 100.0), (100.0, 20.0)])
def test_por_diametro_lesao_clara_e_escura(fundo, lesao):
    v = _vol(nz=30, n=96, ruido=4.0, fundo=fundo, lesao=lesao, r=12.0, rz=5.0)
    g = ES.Grade.do_volume(v)
    real = _vol(nz=30, n=96, fundo=fundo, lesao=lesao).data == lesao
    a, b = g.para_mm([36.5, 48, 15])[0], g.para_mm([59.5, 48, 15])[0]
    r = EM.por_diametro(v.data, g, a, b, normal=[0, 0, 1])
    assert r["clara"] == (lesao > fundo) and r["contraste"] > 5 and not r["aviso"]
    e = ES.Estrutura("a", (1, 1, 1))
    EM.aplicar_mascara(e, g, r["mascara"], r["caixa"])
    c = e.cheia(g)
    assert (c & real).sum() / (c | real).sum() > 0.9
    d = EM.diametros_axiais(e, g)
    assert abs(d["maior_mm"] - 24) < 2.5 and abs(d["curto_mm"] - 24) < 3.5 and abs(d["corte"] - 15) <= 3


def test_por_diametro_ajuste_vizinho_e_casos_ruins():
    n, nz = 96, 24
    z, y, x = np.mgrid[0:nz, 0:n, 0:n]
    rr = np.sqrt((x - 40.0) ** 2 + (y - 48.0) ** 2 + ((z - 12.0) * 2) ** 2)
    d = np.clip(140 - 6 * rr, 20, 100).astype(np.float32)        # borda em rampa: 100 até r 6,7; 20 de r 20 em diante
    d[(x - 70.0) ** 2 + (y - 48.0) ** 2 + ((z - 12.0) * 2) ** 2 < 36] = 100       # um vizinho claro, solto
    v = Volume(d, np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 2.0]), 1, 1, None, "")
    g = ES.Grade.do_volume(v)
    a, b = g.para_mm([27, 48, 12])[0], g.para_mm([53, 48, 12])[0]
    vox = {}
    for aj in (-0.8, 0.0, 0.8):
        r = EM.por_diametro(d, g, a, b, ajuste=aj, normal=[0, 0, 1])
        vox[aj] = int(r["mascara"].sum())
        k0, _k1, j0, _j1, i0, _i1 = r["caixa"]
        cheia = np.zeros(g.forma, bool)
        cheia[k0:k0 + r["mascara"].shape[0], j0:j0 + r["mascara"].shape[1], i0:i0 + r["mascara"].shape[2]] = r["mascara"]
        assert not cheia[:, :, 64:].any()                        # o vizinho não entra
    assert vox[-0.8] < vox[0.0] < vox[0.8]
    assert EM.por_diametro(d, g, a, a + 0.5) is None             # linha curta demais
    assert EM.por_diametro(d, g, a + 5000, b + 5000) is None     # fora da série
    plano = np.full(g.forma, 50, np.float32) + np.random.default_rng(1).normal(0, 5, g.forma).astype(np.float32)
    r = EM.por_diametro(plano, g, a, b, normal=[0, 0, 1])
    assert r is None or r["aviso"]                               # sem lesão: avisa
    assert EM.diametros_axiais(ES.Estrutura("v", (1, 1, 1)), g) == {}


# ---------------------------------------------------------------- o painel (aba "Mais ferramentas")
@pytest.fixture
def exame(env, tmp_path):
    import sys
    from pathlib import Path

    from pydicom.uid import generate_uid

    from ipe.importer.scanner import Importer
    sys.path.insert(0, str(Path(__file__).parent))
    from test_registro_rigido import _serie
    paths, db, repo = env
    v = _vol(ruido=3.0, fundo=20.0)
    estudo = generate_uid()
    serie = _serie(tmp_path / "a", v, estudo, generate_uid(), "Ax T1 POS", "20261101")
    Importer(db, paths.storage).import_paths([tmp_path / "a"])
    return paths, db, repo, estudo, serie, v


def test_painel_mais_ferramentas(exame, monkeypatch):
    from PySide6.QtCore import QPointF
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    paths, db, repo, estudo, serie, v = exame
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        w.open_study(estudo)
        QApplication.processEvents()
        tab = next(iter(w.all_viewer_tabs()))
        vp = next(x for x in tab.viewports if x.study_uid == estudo)
        tab._activate(vp)
        painel = tab.abrir_estruturas(vp)
        g = painel.grade
        real = (np.asarray(painel.vol.data) > 60)
        assert painel.abas.count() == 2
        vp.go_to(10)
        vp.resize(400, 400)

        # --- pelo maior diâmetro, com o mouse: estrutura nova, números e o Ajuste refazendo o contorno
        painel.b_diam.setChecked(True)
        assert tab.left_tool == "pincel" and vp.pincel_raio_mm == 0 and painel.modo() == "diametro"
        a_ = vp.image_to_widget(QPointF(20.5, 32.5)).toPoint()
        b_ = vp.image_to_widget(QPointF(44.5, 32.5)).toPoint()
        QTest.mousePress(vp, _Qt.LeftButton, _Qt.NoModifier, a_)
        QTest.mouseMove(vp, b_)
        assert vp.traco_temp and len(vp.traco_temp[0]) == 2 and not vp.traco_temp[1]
        vp.repaint()                                             # o traço provisório desenha sem erro
        QTest.mouseRelease(vp, _Qt.LeftButton, _Qt.NoModifier, b_)
        assert vp.traco_temp is None and len(painel.estruturas) == 1
        les = painel.estruturas[0]
        c = les.cheia(g)
        assert (c & real).sum() / (c | real).sum() > 0.85
        assert "maior diâmetro" in painel.l_diam.text() and "mL" in painel.l_diam.text()
        n0 = les.voxels
        painel.s_ajuste.setValue(-60)
        assert les.voxels <= n0 and len(les._desfazer) == 1      # recalcular não empilha desfazer
        painel.s_ajuste.setValue(0)
        assert les.voxels == n0
        painel.desfazer()
        assert les.vazia()
        painel.refazer()
        # um segundo traço não mexe na primeira: cria outra
        painel.segmentar_pelo_diametro(g.para_mm([20, 32, 10])[0], g.para_mm([44, 32, 10])[0], [0, 0, 1])
        assert len(painel.estruturas) == 2 and painel.estruturas[0].voxels == n0

        # --- tesoura com o mouse: retângulo, apagar dentro, todos os cortes
        monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
        while len(painel.estruturas) > 1:
            painel.tabela.setCurrentCell(len(painel.estruturas) - 1, 1)
            painel.apagar()
        painel.tabela.setCurrentCell(0, 1)
        les = painel.atual()
        painel.b_tesoura.setChecked(True)
        assert painel.modo() == "tesoura" and not painel.b_diam.isChecked()
        painel.c_tes_forma.setCurrentIndex(painel.c_tes_forma.findData("retangulo"))
        painel.c_tes_alcance.setCurrentIndex(painel.c_tes_alcance.findData("volume"))
        a_ = vp.image_to_widget(QPointF(28.0, 28.0)).toPoint()
        b_ = vp.image_to_widget(QPointF(36.0, 36.0)).toPoint()
        QTest.mousePress(vp, _Qt.LeftButton, _Qt.NoModifier, a_)
        QTest.mouseMove(vp, b_)
        assert vp.traco_temp and len(vp.traco_temp[0]) == 4 and vp.traco_temp[1]
        QTest.mouseRelease(vp, _Qt.LeftButton, _Qt.NoModifier, b_)
        c = les.cheia(g)
        assert not c[:, 29:35, 29:35].any() and c[10, 26, 26] and les.voxels < n0
        painel.desfazer()
        assert les.voxels == n0
        # forma livre, só no corte, preencher (um triângulo), pelo canal do quadro
        painel.c_tes_forma.setCurrentIndex(painel.c_tes_forma.findData("livre"))
        painel.c_tes_alcance.setCurrentIndex(painel.c_tes_alcance.findData("corte"))
        painel.c_tes_acao.setCurrentIndex(painel.c_tes_acao.findData("preencher"))
        for (u, vv), et in (((2.5, 2.5), "ini"), ((10.5, 2.5), "meio"), ((2.5, 10.5), "meio"), ((2.5, 10.5), "fim")):
            vp.sig.pincel.emit(vp, u, vv, et)
        assert les.cheia(g)[10, 4, 4] and not les.cheia(g)[9, 4, 4] and not les.cheia(g)[10, 9, 9]
        painel.desfazer()

        # --- oco, suavizar
        painel.s_oco.setValue(2.0)
        painel._oco()
        assert 0 < les.voxels < n0 and not les.cheia(g)[10, 32, 32]
        painel.desfazer()
        painel.c_suav.setCurrentIndex(painel.c_suav.findData("fechamento"))
        painel._suavizar()
        painel.b_tesoura.setChecked(False)
        assert tab.left_tool != "pincel"

        # --- Otsu + preencher pela faixa numa estrutura nova; dividir ilhas
        nova = painel.nova("Otsu")
        t = painel._otsu()
        assert 40 < t < 80 and abs(painel.s_f_lo.value() - t) < 0.06
        painel._preencher_faixa()
        c = nova.cheia(g)
        assert (c & real).sum() / (c | real).sum() > 0.97
        ES.pintar(nova, g, g.para_mm([5, 5, 2])[0], 3.0)         # uma ilha solta
        painel.s_div.setValue(0.0)
        antes = len(painel.estruturas)
        assert painel._dividir() == 1 and len(painel.estruturas) == antes + 1
        assert painel.estruturas[-1].nome == "Otsu 2" and painel.estruturas[-1].cor != nova.cor
        assert painel._dividir() == 0

        import os
        if os.environ.get("IPE_ESTR_FOTO"):                      # para olhar a aba nova
            painel.abas.setCurrentIndex(1)
            painel.show()
            QApplication.processEvents()
            painel.grab().save(os.environ["IPE_ESTR_FOTO"])
        # --- contorno por nível com o mouse
        niv = painel.nova("Nível")
        painel.b_nivel.setChecked(True)
        a_ = vp.image_to_widget(QPointF(21.5, 32.5)).toPoint()
        QTest.mousePress(vp, _Qt.LeftButton, _Qt.NoModifier, a_)
        QTest.mouseRelease(vp, _Qt.LeftButton, _Qt.NoModifier, a_)
        assert niv.voxels > 200 and niv.mascara.shape[0] == 1 and niv.offset[0] == 10 and len(niv._desfazer) == 1
        painel.desfazer()
        assert niv.vazia()
        painel.b_nivel.setChecked(False)

        # --- crescer das sementes: a lesão e o fundo
        for e in painel.estruturas:
            e.visivel = False
        sl, sf = painel.nova("Semente"), painel.nova("Fundo")
        ES.pintar(sl, g, g.para_mm([32, 32, 10])[0], 3.0)
        for p in ([8, 32, 10], [56, 32, 10], [32, 8, 10], [32, 56, 10], [32, 32, 1], [32, 32, 18]):
            ES.pintar(sf, g, g.para_mm(p)[0], 3.0)
        painel.s_margem.setValue(6)
        out = painel.crescer_sementes()
        assert out[sl.id] > 500
        c = sl.cheia(g)
        assert (c & real).sum() / (c | real).sum() > 0.9
        sl.desfazer()
        assert sl.voxels < 400
        sf.visivel = False
        avisos = []
        monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: avisos.append(a[2])))
        assert painel.crescer_sementes() == {} and "duas estruturas" in avisos[0]
        monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Discard))
        painel.close()
        assert tab.left_tool != "pincel"
    finally:
        w.close()
