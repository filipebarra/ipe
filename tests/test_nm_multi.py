"""Análise entre séries: DMSA, paratireoide dupla fase, captação de tireoide e trânsito colônico."""

import math

import numpy as np
import pytest

from ipe.imaging import nm_multi
from ipe.imaging.nm_roi import Roi
from ipe.imaging.series import Frame, FrameImage

MEIA_TC = 6.0058 * 3600


class FakeCache:
    """Cada caminho é uma imagem pronta."""

    def __init__(self, imagens: dict):
        self.imagens = {k: np.asarray(v, np.float32) for k, v in imagens.items()}

    def get(self, frame):
        return FrameImage(self.imagens[frame.path], False, None, (1.0, 1.0), "PixelSpacing",
                          "MONOCHROME2", {})


def fonte(chave, rotulo, caminho, hora="100000", rois=None, papel="imagem"):
    f = Frame(path=caminho, frame_index=0, sop_uid="", instance_number=1, acquisition_time=hora)
    return nm_multi.Source(chave, rotulo, [f], papel, rois=list(rois or []))


def quadrado(nome, x0, y0, lado, **kw):
    return Roi(name=nome, kind="rect", points=[(x0, y0), (x0 + lado, y0 + lado)], **kw)


def imagem(blocos, tamanho=64, fundo=0.0):
    """blocos: {(x0, y0, lado): valor por pixel}."""
    img = np.full((tamanho, tamanho), fundo, np.float32)
    for (x0, y0, lado), v in blocos.items():
        img[y0:y0 + lado, x0:x0 + lado] = v
    return img


def medir(fontes, cache, meia=MEIA_TC):
    t = nm_multi.measure(fontes, cache)
    t.half_life_s = meia
    return t


# ------------------------------------------------------------------ horário
def test_le_o_horario_do_quadro():
    assert nm_multi.seconds_of_day("103015") == 10 * 3600 + 30 * 60 + 15
    assert nm_multi.seconds_of_day("10:30:15") == 10 * 3600 + 30 * 60 + 15
    assert nm_multi.seconds_of_day("") is None
    assert nm_multi.seconds_of_day("abc") is None
    s = fonte("a", "A", "x", hora="090500")
    s.fill_time()
    assert s.time_s == 9 * 3600 + 5 * 60


# ------------------------------------------------------------------ medir
def test_mede_cada_regiao_em_cada_fonte():
    cache = FakeCache({"ant": imagem({(10, 10, 4): 5.0, (40, 10, 4): 3.0}),
                       "post": imagem({(10, 10, 4): 7.0, (40, 10, 4): 2.0})})
    rois = [quadrado("Rim direito", 10, 10, 4), quadrado("Rim esquerdo", 40, 10, 4)]
    t = medir([fonte("ant", "ANT", "ant", rois=rois), fonte("post", "POST", "post", rois=rois)],
              cache)
    assert t.get("ant", "Rim direito").net == pytest.approx(5.0 * 16)
    assert t.get("post", "Rim direito").net == pytest.approx(7.0 * 16)
    assert t.get("ant", "Rim direito").pixels == 16


def test_fundo_por_anel_desconta_na_medida():
    cache = FakeCache({"ant": imagem({(20, 20, 4): 10.0}, fundo=2.0)})
    r = quadrado("Alvo", 20, 20, 4, background="ring", ring_px=3)
    t = medir([fonte("ant", "ANT", "ant", rois=[r])], cache)
    c = t.get("ant", "Alvo")
    assert c.raw == pytest.approx(10.0 * 16)
    assert c.background == pytest.approx(2.0 * 16, rel=0.02)
    assert c.net == pytest.approx(8.0 * 16, rel=0.02)


def test_correcao_de_decaimento_entre_horarios():
    cache = FakeCache({"a": imagem({(10, 10, 4): 100.0}), "b": imagem({(10, 10, 4): 50.0})})
    r = [quadrado("Alvo", 10, 10, 4)]
    a = fonte("a", "Precoce", "a", hora="100000", rois=r)
    b = fonte("b", "Tardia", "b", hora="160004", rois=r)     # ~1 meia-vida depois
    t = medir([a, b], cache)
    ref = t.common_time()
    assert t.net("a", "Alvo", ref) == pytest.approx(100.0 * 16)
    # a tardia, corrigida para a hora da precoce, vale o dobro do que foi contado
    assert t.net("b", "Alvo", ref) == pytest.approx(50.0 * 16 * 2, rel=0.01)
    assert t.net("b", "Alvo") == pytest.approx(50.0 * 16)     # sem corrigir, o que foi contado


def test_sem_meia_vida_nao_corrige():
    cache = FakeCache({"a": imagem({(10, 10, 4): 100.0})})
    t = medir([fonte("a", "A", "a", rois=[quadrado("Alvo", 10, 10, 4)])], cache, meia=0.0)
    assert t.net("a", "Alvo", 0.0) == pytest.approx(100.0 * 16)


# ------------------------------------------------------------------ DMSA
def test_dmsa_media_geometrica_e_funcao_relativa():
    # rim direito: ANT 4, POST 9 -> GM 6 ; rim esquerdo: ANT 1, POST 4 -> GM 2
    cache = FakeCache({"ant": imagem({(10, 10, 4): 4.0, (40, 10, 4): 1.0}),
                       "post": imagem({(10, 10, 4): 9.0, (40, 10, 4): 4.0})})
    rois = [quadrado("Rim direito", 10, 10, 4), quadrado("Rim esquerdo", 40, 10, 4)]
    t = medir([fonte("ant", "ANT", "ant", rois=rois), fonte("post", "POST", "post", rois=rois)],
              cache)
    res = nm_multi.geometric_mean_function(t, "ant", "post", "Rim esquerdo", "Rim direito")
    assert [l[0] for l in res.rows] == ["Rim direito", "Rim esquerdo"]
    assert res.rows[0][4] == "75.0%"                  # 6 / (6 + 2)
    assert res.rows[1][4] == "25.0%"
    assert "75.0%" in res.text and "25.0%" in res.text


def test_dmsa_avisa_quando_uma_vista_nao_tem_contagem():
    cache = FakeCache({"ant": imagem({(10, 10, 4): 4.0, (40, 10, 4): 1.0}),
                       "post": imagem({(10, 10, 4): 9.0})})
    rois = [quadrado("Rim direito", 10, 10, 4), quadrado("Rim esquerdo", 40, 10, 4)]
    t = medir([fonte("ant", "ANT", "ant", rois=rois), fonte("post", "POST", "post", rois=rois)],
              cache)
    res = nm_multi.geometric_mean_function(t, "ant", "post", "Rim esquerdo", "Rim direito")
    assert any("só uma das vistas" in n for n in res.notes)


def test_dmsa_avisa_areas_diferentes_entre_as_vistas():
    cache = FakeCache({"ant": imagem({(10, 10, 6): 4.0}), "post": imagem({(10, 10, 4): 9.0})})
    ant = fonte("ant", "ANT", "ant", rois=[quadrado("Rim direito", 10, 10, 6),
                                           quadrado("Rim esquerdo", 40, 10, 6)])
    post = fonte("post", "POST", "post", rois=[quadrado("Rim direito", 10, 10, 4),
                                               quadrado("Rim esquerdo", 40, 10, 4)])
    t = medir([ant, post], cache)
    res = nm_multi.geometric_mean_function(t, "ant", "post", "Rim esquerdo", "Rim direito")
    assert any("áreas bem diferentes" in n for n in res.notes)


# ------------------------------------------------------------------ paratireoide
def test_dupla_fase_mede_a_retencao_corrigida():
    """Atividade fisicamente igual nas duas fases: a retenção tem que dar 100%, não 50%."""
    cache = FakeCache({"cedo": imagem({(10, 10, 4): 100.0}),
                       "tarde": imagem({(10, 10, 4): 50.0})})
    r = [quadrado("Nódulo", 10, 10, 4)]
    t = medir([fonte("cedo", "10 min", "cedo", hora="100000", rois=r),
               fonte("tarde", "2 h", "tarde", hora="160004", rois=r)], cache)
    res = nm_multi.dual_phase(t, "cedo", "tarde", ["Nódulo"])
    assert res.rows[0][3] == "100%"
    assert "retenção de 100%" in res.text


def test_dupla_fase_sem_corrigir_mostra_a_queda_do_decaimento():
    cache = FakeCache({"cedo": imagem({(10, 10, 4): 100.0}),
                       "tarde": imagem({(10, 10, 4): 50.0})})
    r = [quadrado("Nódulo", 10, 10, 4)]
    t = medir([fonte("cedo", "10 min", "cedo", hora="100000", rois=r),
               fonte("tarde", "2 h", "tarde", hora="160004", rois=r)], cache)
    res = nm_multi.dual_phase(t, "cedo", "tarde", ["Nódulo"], decay=False)
    assert res.rows[0][3] == "50%"


def test_dupla_fase_sem_meia_vida_avisa():
    cache = FakeCache({"cedo": imagem({(10, 10, 4): 100.0}), "tarde": imagem({(10, 10, 4): 50.0})})
    r = [quadrado("Nódulo", 10, 10, 4)]
    t = medir([fonte("cedo", "A", "cedo", rois=r), fonte("tarde", "B", "tarde", rois=r)],
              cache, meia=0.0)
    res = nm_multi.dual_phase(t, "cedo", "tarde", ["Nódulo"])
    assert any("meia-vida" in n for n in res.notes)


# ------------------------------------------------------------------ tireoide
def test_captacao_de_tireoide_contra_o_padrao():
    cache = FakeCache({"tir": imagem({(10, 10, 4): 10.0}),
                       "cheia": imagem({(30, 30, 4): 100.0}),
                       "vazia": imagem({(30, 30, 4): 20.0})})
    alvo = [quadrado("Tireoide", 10, 10, 4)]
    padrao = [quadrado("Seringa", 30, 30, 4)]
    t = medir([fonte("tir", "Tireoide", "tir", hora="100000", rois=alvo),
               fonte("cheia", "Seringa cheia", "cheia", hora="100000", rois=padrao),
               fonte("vazia", "Seringa vazia", "vazia", hora="100000", rois=padrao)], cache)
    res = nm_multi.uptake_percent(t, "tir", "Tireoide", "cheia", "vazia", "Seringa")
    # alvo 160; dose = 1600 − 320 = 1280 -> 12,5%
    assert res.rows[-1] == ["Captação", "12.50%"]
    assert "12.50%" in res.text


def test_captacao_corrige_o_decaimento_do_padrao():
    """Seringa medida uma meia-vida antes: sem corrigir, a captação sairia pela metade."""
    cache = FakeCache({"tir": imagem({(10, 10, 4): 10.0}),
                       "cheia": imagem({(30, 30, 4): 200.0})})
    t = medir([fonte("tir", "Tireoide", "tir", hora="160004",
                     rois=[quadrado("Tireoide", 10, 10, 4)]),
               fonte("cheia", "Seringa cheia", "cheia", hora="100000",
                     rois=[quadrado("Seringa", 30, 30, 4)])], cache)
    res = nm_multi.uptake_percent(t, "tir", "Tireoide", "cheia", "", "Seringa")
    # padrão 3200 contado, valendo ~1600 na hora da tireoide; alvo 160 -> ~10%
    assert float(res.rows[-1][1].rstrip("%")) == pytest.approx(10.0, abs=0.05)
    assert any("seringa vazia" in n for n in res.notes)


def test_captacao_com_dose_zero_avisa():
    cache = FakeCache({"tir": imagem({(10, 10, 4): 10.0}), "cheia": imagem({(30, 30, 4): 5.0}),
                       "vazia": imagem({(30, 30, 4): 5.0})})
    padrao = [quadrado("Seringa", 30, 30, 4)]
    t = medir([fonte("tir", "T", "tir", rois=[quadrado("Tireoide", 10, 10, 4)]),
               fonte("cheia", "C", "cheia", rois=padrao), fonte("vazia", "V", "vazia", rois=padrao)],
              cache)
    res = nm_multi.uptake_percent(t, "tir", "Tireoide", "cheia", "vazia", "Seringa")
    assert res.text == ""
    assert any("zero ou negativo" in n for n in res.notes)


# ------------------------------------------------------------------ trânsito colônico
def _transito(cache_map, ordem, fontes):
    cache = FakeCache(cache_map)
    return nm_multi.geometric_center(medir(fontes, cache), ordem, [f.key for f in fontes])


def test_centro_geometrico_avanca_com_o_transito():
    ordem = ["Ascendente", "Transverso", "Descendente", "Retossigmoide"]
    rois = [quadrado(ordem[0], 0, 0, 4), quadrado(ordem[1], 10, 0, 4),
            quadrado(ordem[2], 20, 0, 4), quadrado(ordem[3], 30, 0, 4)]
    cedo = imagem({(0, 0, 4): 100.0})                       # tudo no ascendente
    tarde = imagem({(30, 0, 4): 100.0})                     # tudo no retossigmoide
    res = _transito({"a": cedo, "b": tarde}, ordem,
                    [fonte("a", "24 h", "a", rois=rois), fonte("b", "48 h", "b", rois=rois)])
    assert res.rows[0][-1] == "1.00"
    assert res.rows[1][-1] == "4.00"
    assert "24 h: centro geométrico de 1.00" in res.text


def test_centro_geometrico_com_o_bolo_repartido():
    ordem = ["Ascendente", "Transverso"]
    rois = [quadrado(ordem[0], 0, 0, 4), quadrado(ordem[1], 10, 0, 4)]
    meio = imagem({(0, 0, 4): 50.0, (10, 0, 4): 50.0})
    res = _transito({"a": meio}, ordem, [fonte("a", "24 h", "a", rois=rois)])
    assert res.rows[0][-1] == "1.50"
    assert res.rows[0][1] == "50%" and res.rows[0][2] == "50%"


def test_tempo_sem_contagem_nao_vira_zero_falso():
    ordem = ["Ascendente", "Transverso"]
    rois = [quadrado(ordem[0], 0, 0, 4), quadrado(ordem[1], 10, 0, 4)]
    res = _transito({"a": imagem({})}, ordem, [fonte("a", "72 h", "a", rois=rois)])
    assert res.rows[0][-1] == "—"
    assert any("sem contagem" in n for n in res.notes)


def test_centro_geometrico_precisa_de_duas_regioes():
    rois = [quadrado("Ascendente", 0, 0, 4)]
    res = _transito({"a": imagem({(0, 0, 4): 10.0})}, ["Ascendente"],
                    [fonte("a", "24 h", "a", rois=rois)])
    assert any("pelo menos duas regiões" in n for n in res.notes)


# ------------------------------------------------------------------ tabela crua
def test_tabela_crua_lista_tudo():
    cache = FakeCache({"a": imagem({(10, 10, 4): 5.0}), "b": imagem({(10, 10, 4): 9.0})})
    r = [quadrado("Alvo", 10, 10, 4)]
    t = medir([fonte("a", "Precoce", "a", rois=r), fonte("b", "Tardia", "b", rois=r)], cache)
    res = nm_multi.raw_table(t)
    assert res.headers == ["Imagem", "Alvo"]
    assert res.rows == [["Precoce", "80"], ["Tardia", "144"]]


# ================================================================== na tela
@pytest.fixture()
def win(env, sample_dir):
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1400, 860)
    w.show()
    w.browser.refresh()
    yield app, w
    w.close()


def _dmsa(w):
    from ipe.ui.viewer import nm_view as NMV
    w.handle_external({"accession": "ACC5003"})
    tab = w.tabs.currentWidget()
    return tab, NMV.study_sources(tab)


def test_fontes_do_exame_saem_das_series_e_das_vistas(win):
    _app, w = win
    tab, fontes = _dmsa(w)
    rotulos = [f.label for f in fontes]
    assert any("ANT" in r for r in rotulos) and any("POST" in r for r in rotulos)
    assert any("SERINGA CHEIA" in r for r in rotulos)
    assert any("SERINGA VAZIA" in r for r in rotulos)
    assert len(fontes) == 4                       # ANT, POST, cheia, vazia
    assert all(f.time_s is None or f.time_s > 0 for f in fontes)


def test_captura_da_estacao_nao_entra_como_fonte(win):
    from ipe.ui.viewer import nm_view as NMV
    _app, w = win
    w.handle_external({"accession": "ACC5001"})     # óssea, que tem ScreenCap
    tab = w.tabs.currentWidget()
    fontes = NMV.study_sources(tab)
    assert fontes and all("ScreenCap" not in f.label for f in fontes)


def test_janela_entre_series_abre_e_le_os_horarios(win):
    from ipe.ui.viewer.nm_multi_view import NMMultiDialog
    app, w = win
    tab, fontes = _dmsa(w)
    dlg = NMMultiDialog(fontes, tab.cache, "DMSA", "dmsa", tab, tab)
    app.processEvents()
    assert dlg.lista.rowCount() == 4
    horas = [dlg.lista.item(i, 2).text() for i in range(4)]
    assert "10:30" in horas and "09:00" in horas      # ANT/POST e a seringa cheia
    assert dlg.exame.currentData() == "dmsa"
    assert "Rim direito" in dlg.dica.text()
    dlg.close()


def test_dmsa_na_janela_da_funcao_relativa(win):
    from ipe.ui.viewer.nm_multi_view import NMMultiDialog
    app, w = win
    tab, fontes = _dmsa(w)
    fontes = [f for f in fontes if "ANT" in f.label or "POST" in f.label]
    dlg = NMMultiDialog(fontes, tab.cache, "DMSA", "dmsa", tab, tab)
    app.processEvents()
    # regiões na ANT e depois copiadas espelhadas para a POST
    dlg._mostra(0)
    dlg.canvas.add_roi([(30, 40), (56, 84)])          # rim direito (à esquerda na imagem)
    dlg.canvas.mirror_selected()
    dlg._mostra(1)
    dlg.origem.setCurrentIndex(0)
    dlg._copiar(True)
    app.processEvents()
    assert len(fontes[1].rois) == 2
    res = dlg.resultado
    assert res.headers[-1] == "Função relativa"
    d = float(res.rows[0][4].rstrip("%"))
    e = float(res.rows[1][4].rstrip("%"))
    assert d + e == pytest.approx(100.0, abs=0.2)
    assert d > e                                       # o fantoma tem o rim direito melhor
    assert "Função relativa" in res.text
    dlg.close()


def test_copiar_espelhado_mantem_a_mesma_area(win):
    from ipe.ui.viewer.nm_multi_view import NMMultiDialog
    app, w = win
    tab, fontes = _dmsa(w)
    fontes = [f for f in fontes if "ANT" in f.label or "POST" in f.label]
    dlg = NMMultiDialog(fontes, tab.cache, "DMSA", "dmsa", tab, tab)
    dlg._mostra(0)
    dlg.canvas.add_roi([(30, 40), (56, 84)])
    dlg.canvas.auto_contour(40.0)
    dlg._mostra(1)
    dlg.origem.setCurrentIndex(0)
    dlg._copiar(True)
    app.processEvents()
    a = fontes[0].rois[0]
    b = fontes[1].rois[0]
    assert a.is_auto and b.is_auto
    assert int(a.auto_mask.sum()) == int(b.auto_mask.sum())
    dlg.close()


def test_tireoide_na_janela_usa_a_seringa(win):
    from ipe.ui.viewer.nm_multi_view import NMMultiDialog
    app, w = win
    tab, fontes = _dmsa(w)
    alvo = next(f for f in fontes if "ANT" in f.label)
    cheia = next(f for f in fontes if "CHEIA" in f.label)
    vazia = next(f for f in fontes if "VAZIA" in f.label)
    dlg = NMMultiDialog([alvo, cheia, vazia], tab.cache, "Tireoide", "tireoide", tab, tab)
    app.processEvents()
    dlg._mostra(0)
    dlg.canvas.add_roi([(30, 40), (56, 84)], nome="Tireoide")
    dlg._mostra(1)
    dlg.canvas.add_roi([(48, 48), (80, 80)], nome="Seringa")
    dlg._mostra(2)
    dlg.canvas.add_roi([(48, 48), (80, 80)], nome="Seringa")
    dlg.recalcular()
    app.processEvents()
    linhas = {l[0]: l[1] for l in dlg.resultado.rows}
    assert "Captação" in linhas
    captacao = float(linhas["Captação"].rstrip("%"))
    assert 0 < captacao < 100
    assert "Captação tireoidiana" in dlg.resultado.text
    dlg.close()


def test_sem_papel_marcado_a_janela_diz_o_que_falta(win):
    from ipe.ui.viewer.nm_multi_view import NMMultiDialog, IGNORAR
    app, w = win
    tab, fontes = _dmsa(w)
    dlg = NMMultiDialog(fontes, tab.cache, "DMSA", "dmsa", tab, tab)
    for i in range(dlg.lista.rowCount()):
        dlg.lista.cellWidget(i, 1).setCurrentText(IGNORAR)
    dlg.recalcular()
    app.processEvents()
    assert any("anterior" in n for n in dlg.resultado.notes)
    dlg.close()


def test_exame_livre_mostra_so_as_contagens(win):
    from ipe.ui.viewer.nm_multi_view import NMMultiDialog
    app, w = win
    tab, fontes = _dmsa(w)
    dlg = NMMultiDialog(fontes, tab.cache, "Exame", "livre", tab, tab)
    dlg._mostra(0)
    dlg.canvas.add_roi([(30, 40), (56, 84)])
    dlg.recalcular()
    app.processEvents()
    assert dlg.resultado.headers[0] == "Imagem"
    assert dlg.resultado.rows
    assert dlg.csv_text().startswith("Imagem;")
    dlg.close()
