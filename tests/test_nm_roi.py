"""ROI, curva atividade-tempo, imagem condensada e os números do renograma."""

import numpy as np
import pytest

from ipe.imaging import nm, nm_roi, renogram
from ipe.imaging.series import Frame, FrameImage


class FakeCache:
    """Cache que devolve quadros de um array (tempo, linha, coluna)."""

    def __init__(self, vol):
        self.vol = np.asarray(vol, np.float32)

    def get(self, frame):
        return FrameImage(self.vol[frame.frame_index], False, None, (1.0, 1.0), "PixelSpacing",
                          "MONOCHROME2", {})


def frames_for(n, path="x.dcm"):
    return [Frame(path=path, frame_index=i, sop_uid="", instance_number=i + 1) for i in range(n)]


def info_fixo(n, dur_ms=1000.0):
    return nm.NMInfo(path="x.dcm", modality="NM", n_frames=n, frame_duration_ms=dur_ms)


def roi_quadrado(nome, x0, y0, lado, **kw):
    return nm_roi.Roi(name=nome, kind="rect",
                      points=[(x0, y0), (x0 + lado, y0 + lado)], **kw)


# ------------------------------------------------------------------ máscaras
def test_anel_envolve_a_roi_sem_encostar():
    m = np.zeros((20, 20), bool)
    m[8:12, 8:12] = True
    anel = nm_roi.ring_mask(m, width=2, gap=1)
    assert not (anel & m).any()                     # o anel não pega o alvo
    assert anel[6, 10] and anel[13, 10]             # pega em volta
    assert not anel[7, 10]                          # o intervalo de 1 px fica vazio
    assert anel.sum() > 0


# ------------------------------------------------------------------ curvas
def test_curva_segue_a_atividade_da_regiao():
    n = 10
    vol = np.zeros((n, 32, 32), np.float32)
    for i in range(n):
        vol[i, 10:14, 10:14] = i + 1                # alvo cresce
    c = nm_roi.curves(frames_for(n), FakeCache(vol),
                      [roi_quadrado("Alvo", 10, 10, 4)], info_fixo(n))[0]
    assert c.counts.size == n
    assert c.pixels == 16
    assert np.allclose(c.counts, [(i + 1) * 16 for i in range(n)])
    assert c.times_s[0] == pytest.approx(0.5)       # meio do quadro, não o início


def test_tempo_do_ponto_e_o_meio_do_quadro():
    n = 4
    info = nm.NMInfo(path="x", modality="NM", n_frames=n, frame_duration_ms=30000.0)
    c = nm_roi.curves(frames_for(n), FakeCache(np.ones((n, 8, 8), np.float32)),
                      [roi_quadrado("A", 2, 2, 4)], info)[0]
    assert list(c.times_s) == [15.0, 45.0, 75.0, 105.0]
    assert list(c.durations_s) == [30.0] * n


def test_contagens_por_segundo_corrigem_o_degrau_entre_fases():
    """Fluxo de 2 s e dinâmico de 30 s com a mesma atividade real: em cps a curva é plana."""
    n = 4
    vol = np.zeros((n, 16, 16), np.float32)
    vol[0:2, 4:8, 4:8] = 10.0                       # 2 s de quadro
    vol[2:4, 4:8, 4:8] = 150.0                      # 30 s de quadro (15×)
    info = nm.NMInfo(path="x", modality="NM", n_frames=n, frame_duration_ms=2000.0,
                     phase_duration_ms=[2000.0, 30000.0],
                     axes=[nm.NMAxis("phase", "Fase", [1, 1, 2, 2], 2, [])])
    c = nm_roi.curves(frames_for(n), FakeCache(vol), [roi_quadrado("A", 4, 4, 4)], info)[0]
    assert list(c.durations_s) == [2.0, 2.0, 30.0, 30.0]
    cps = c.cps
    assert cps[0] == pytest.approx(cps[2], rel=0.01)   # o degrau some
    assert c.counts[2] > c.counts[0] * 10              # mas nas contagens ele existe


def test_fundo_por_roi_propria_escala_pela_area():
    n = 3
    vol = np.full((n, 32, 32), 2.0, np.float32)     # fundo uniforme de 2 por pixel
    vol[:, 10:14, 10:14] += 5.0                     # alvo com 5 a mais
    rois = [roi_quadrado("Alvo", 10, 10, 4, background="roi", background_roi="Fundo"),
            roi_quadrado("Fundo", 24, 24, 2, role="fundo")]
    c = nm_roi.curves(frames_for(n), FakeCache(vol), rois, info_fixo(n))[0]
    assert np.allclose(c.raw, 7.0 * 16)
    assert np.allclose(c.background, 2.0 * 16)      # 2 por pixel × 16 pixels do alvo
    assert np.allclose(c.counts, 5.0 * 16)
    assert not c.note


def test_fundo_por_anel():
    n = 2
    vol = np.full((n, 40, 40), 3.0, np.float32)
    vol[:, 18:22, 18:22] += 10.0
    r = roi_quadrado("Alvo", 18, 18, 4, background="ring", ring_px=3)
    c = nm_roi.curves(frames_for(n), FakeCache(vol), [r], info_fixo(n))[0]
    assert np.allclose(c.background, 3.0 * 16, rtol=0.01)
    assert np.allclose(c.counts, 10.0 * 16, rtol=0.01)


def test_fundo_por_fracao_fixa():
    n = 2
    vol = np.full((n, 20, 20), 4.0, np.float32)
    r = roi_quadrado("A", 5, 5, 4, background="fraction", fraction=0.25)
    c = nm_roi.curves(frames_for(n), FakeCache(vol), [r], info_fixo(n))[0]
    assert np.allclose(c.counts, 4.0 * 16 * 0.75)


def test_roi_de_fundo_que_nao_existe_avisa_e_nao_subtrai():
    n = 2
    vol = np.full((n, 20, 20), 5.0, np.float32)
    r = roi_quadrado("A", 5, 5, 4, background="roi", background_roi="Sumiu")
    c = nm_roi.curves(frames_for(n), FakeCache(vol), [r], info_fixo(n))[0]
    assert np.allclose(c.background, 0.0)
    assert "Sumiu" in c.note


def test_roi_fora_da_imagem_nao_derruba():
    n = 2
    vol = np.ones((n, 16, 16), np.float32)
    r = roi_quadrado("Fora", 100, 100, 4)
    c = nm_roi.curves(frames_for(n), FakeCache(vol), [r], info_fixo(n))[0]
    assert c.pixels == 0 and c.note
    assert np.allclose(c.counts, 0.0)


def test_correcao_de_decaimento_usa_a_meia_vida_do_cabecalho():
    n = 3
    vol = np.ones((n, 16, 16), np.float32)
    meia = 100.0
    info = nm.NMInfo(path="x", modality="NM", n_frames=n, frame_duration_ms=100000.0,
                     radiopharm={"half_life_s": meia})
    c = nm_roi.curves(frames_for(n), FakeCache(vol), [roi_quadrado("A", 2, 2, 4)],
                      info, decay=True)[0]
    assert c.decay_corrected
    assert c.counts[1] > c.counts[0]                # atividade constante na tela sobe ao corrigir


def test_sem_meia_vida_avisa_em_vez_de_corrigir_errado():
    n = 2
    c = nm_roi.curves(frames_for(n), FakeCache(np.ones((n, 16, 16), np.float32)),
                      [roi_quadrado("A", 2, 2, 4)], info_fixo(n), decay=True)[0]
    assert not c.decay_corrected and "meia-vida" in c.note


# ------------------------------------------------------------------ números da curva
def _curva(tempos, valores, nome="A"):
    t = np.asarray(tempos, float)
    v = np.asarray(valores, float)
    d = np.full(t.size, 1.0)
    return nm_roi.Curve(nome, t, v, v, np.zeros(t.size), d, 100, "roi")


def test_pico_e_meia_vida_interpolados():
    t = [0, 60, 120, 180, 240, 300]
    v = [0, 50, 100, 75, 50, 25]
    c = _curva(t, v)
    assert nm_roi.peak(c) == (120.0, 100.0)
    assert nm_roi.half_time(c) == pytest.approx(120.0)     # cai a 50 aos 240 s, pico aos 120


def test_meia_vida_nao_atingida_devolve_none():
    c = _curva([0, 60, 120, 180], [0, 50, 100, 95])
    assert nm_roi.half_time(c) is None


def test_integral_e_retencao():
    c = _curva([0, 60, 120], [10, 10, 10])
    assert nm_roi.integral(c, 0, 120) == pytest.approx(1200.0)
    assert nm_roi.value_at(c, 30) == pytest.approx(10.0)
    c2 = _curva([0, 3600, 7200], [100, 50, 25])
    assert nm_roi.retention(c2, 3600) == pytest.approx(50.0)


# ------------------------------------------------------------------ imagem condensada
def test_imagem_condensada_poe_o_tempo_no_eixo_horizontal():
    n = 6
    vol = np.zeros((n, 20, 20), np.float32)
    for i in range(n):
        vol[i, 2 + 2 * i, :] = 10.0                 # uma faixa que desce com o tempo
    img = nm_roi.condensed(frames_for(n), FakeCache(vol))
    assert img.shape == (20, n)
    for i in range(n):
        assert int(np.argmax(img[:, i])) == 2 + 2 * i


# ------------------------------------------------------------------ renograma
def _rim(nome, pico_s, cai=True, dur=1500):
    t = np.arange(0, dur, 15.0)
    subida = 100 * (1 - np.exp(-t / (pico_s / 2)))
    queda = np.exp(-np.clip(t - pico_s, 0, None) / 200.0) if cai else np.ones_like(t)
    return _curva(t, subida * queda, nome)


def test_funcao_relativa_soma_cem_por_cento():
    d, e = _rim("Rim direito", 180), _rim("Rim esquerdo", 180)
    res = renogram.analyse([d, e])
    assert res.by_name("Rim direito").relative_pct == pytest.approx(50.0, abs=0.5)
    assert sum(k.relative_pct for k in res.kidneys) == pytest.approx(100.0)


def test_rim_com_mais_captacao_fica_com_a_maior_porcentagem():
    d = _rim("Rim direito", 180)
    e = _rim("Rim esquerdo", 180)
    e.counts = e.counts * 0.4
    res = renogram.analyse([d, e])
    assert res.by_name("Rim direito").relative_pct > 65
    assert res.by_name("Rim esquerdo").relative_pct < 35


def test_rim_que_nao_drena_devolve_t_meio_nulo_e_diz_isso():
    obstruido = _rim("Rim esquerdo", 300, cai=False)
    res = renogram.analyse([_rim("Rim direito", 180), obstruido])
    k = res.by_name("Rim esquerdo")
    assert k.half_time_s is None
    assert "não caiu à metade" in k.note.lower()
    texto = renogram.report_text(res)
    assert "T½ não atingido" in texto


def test_uma_curva_so_nao_inventa_funcao_relativa():
    res = renogram.analyse([_rim("Rim único", 180)])
    assert res.kidneys[0].relative_pct is None
    assert any("exatamente duas" in n for n in res.notes)


def test_estudo_curto_avisa():
    curta = _curva([0, 10, 20], [1, 2, 3], "Rim direito")
    outra = _curva([0, 10, 20], [1, 2, 3], "Rim esquerdo")
    res = renogram.analyse([curta, outra])
    assert any("curto" in n for n in res.notes)


def test_tabela_e_texto_do_laudo():
    res = renogram.analyse([_rim("Rim direito", 180), _rim("Rim esquerdo", 180)])
    linhas = renogram.summary_rows(res)
    assert len(linhas) == 2 and len(linhas[0]) == len(renogram.SUMMARY_HEADERS)
    assert "%" in linhas[0][1] and "min" in linhas[0][2]
    assert "função relativa" in renogram.report_text(res)


def test_curva_sem_fundo_avisa_no_resultado():
    c1 = _curva([0, 60, 120, 180], [0, 50, 100, 50], "Rim direito")
    c2 = _curva([0, 60, 120, 180], [0, 50, 100, 50], "Rim esquerdo")
    c1.method = c2.method = "none"
    res = renogram.analyse([c1, c2])
    assert "sem subtração de fundo" in res.by_name("Rim direito").note.lower()


def test_nomes_repetidos_ficam_distintos():
    a, b = _curva([0, 1], [1, 2], "Rim"), _curva([0, 1], [1, 2], "Rim")
    renogram.normalise_names([a, b])
    assert a.name != b.name


# ------------------------------------------------------------------ exportação
def test_csv_tem_uma_linha_por_quadro():
    n = 5
    vol = np.ones((n, 16, 16), np.float32)
    cs = nm_roi.curves(frames_for(n), FakeCache(vol),
                       [roi_quadrado("A", 2, 2, 4), roi_quadrado("B", 8, 8, 4)], info_fixo(n))
    texto = nm_roi.to_csv(cs)
    linhas = texto.splitlines()
    assert len(linhas) == n + 1
    assert linhas[0].startswith("tempo_s;duracao_s;A_cps;B_cps")


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


def _renal(w):
    """Abre o renograma do fantoma e devolve (aba, série, vista dinâmica de 30 s)."""
    from ipe.ui.viewer import nm_view as NMV
    w.handle_external({"accession": "ACC5002"})
    tab = w.tabs.currentWidget()
    serie = next(s for s in tab.series if (s.modality or "").upper() == "NM")
    views = NMV.views_of(tab, serie.series_uid)
    return tab, serie.series_uid, views[1]          # fase 2: 20 quadros de 30 s


def _dialogo(tab, view, titulo="Renograma"):
    from ipe.ui.viewer.nm_analysis import NMAnalysisDialog
    return NMAnalysisDialog(view.frames, tab.cache, titulo, nm.info_for_file(view.frames[0].path),
                            "renograma", tab, tab)


def test_janela_abre_com_a_soma_dos_quadros(win):
    app, w = win
    tab, _uid, view = _renal(w)
    dlg = _dialogo(tab, view)
    app.processEvents()
    assert dlg.canvas.pixels is not None
    assert dlg.somar.isChecked()
    assert "20 quadros" in dlg.rotulo_quadro.text()
    soma = float(dlg.canvas.pixels.sum())
    dlg.somar.setChecked(False)
    dlg._quadro_mudou(0)
    app.processEvents()
    assert float(dlg.canvas.pixels.sum()) < soma        # um quadro só tem bem menos contagem
    dlg.close()


def test_roi_nasce_com_o_nome_do_preset_e_gera_curva(win):
    app, w = win
    tab, _uid, view = _renal(w)
    dlg = _dialogo(tab, view)
    dlg.canvas.add_roi([(30, 45), (48, 75)])
    app.processEvents()
    assert dlg.canvas.rois[0].name == "Rim direito"
    assert len(dlg.curvas) == 1
    assert dlg.curvas[0].counts.size == 20
    assert dlg.curvas[0].counts.max() > 0
    dlg.close()


def test_espelhar_cria_o_outro_rim(win):
    app, w = win
    tab, _uid, view = _renal(w)
    dlg = _dialogo(tab, view)
    dlg.canvas.add_roi([(30, 45), (48, 75)])
    dlg.canvas.mirror_selected()
    app.processEvents()
    assert [r.name for r in dlg.canvas.rois] == ["Rim direito", "Rim esquerdo"]
    d, e = dlg.canvas.rois
    largura = dlg.canvas.pixels.shape[1]
    assert d.points[0][0] + e.points[0][0] == pytest.approx(largura)
    assert d.points[0][1] == e.points[0][1]              # mesma altura
    dlg.close()


def test_fantoma_obstruido_aparece_nos_numeros(win):
    """No fantoma o rim esquerdo não drena: T½ não atingido e função relativa maior à esquerda."""
    app, w = win
    tab, _uid, view = _renal(w)
    dlg = _dialogo(tab, view)
    dlg.canvas.add_roi([(30, 45), (48, 75)])            # rim direito (à esquerda na imagem)
    dlg.canvas.mirror_selected()
    app.processEvents()
    res = dlg.resultado
    assert res is not None and len(res.rows) == 2
    assert dlg.tabela.rowCount() == 2
    assert "não atingido" in dlg.tabela.item(1, 3).text()
    assert "não caiu à metade" in dlg.aviso.text().lower()
    assert "T½ não atingido" in res.text
    dlg.close()


def test_texto_do_laudo_sai_da_janela(win):
    app, w = win
    tab, _uid, view = _renal(w)
    dlg = _dialogo(tab, view)
    dlg.canvas.add_roi([(30, 45), (48, 75)])
    dlg.canvas.mirror_selected()
    app.processEvents()
    texto = dlg.report_text()
    assert "Rim direito" in texto and "função relativa" in texto
    assert "T½" in texto
    dlg.close()


def test_manda_para_o_laudo_escreve_na_janela_do_laudo(win):
    app, w = win
    tab, _uid, view = _renal(w)
    dlg = _dialogo(tab, view)
    dlg.canvas.add_roi([(30, 45), (48, 75)])
    dlg.canvas.mirror_selected()
    app.processEvents()
    assert tab.append_to_report(dlg.report_text()) is True
    janela = tab._report_windows[tab.study_uid]
    assert "função relativa" in janela.editor.toPlainText()
    janela.close()
    dlg.close()


def test_mudar_o_fundo_muda_a_curva(win):
    app, w = win
    tab, _uid, view = _renal(w)
    dlg = _dialogo(tab, view)
    dlg.canvas.add_roi([(30, 45), (48, 75)])
    app.processEvents()
    sem = float(dlg.curvas[0].counts.max())
    dlg.canvas.rois[0].background = "ring"
    dlg.recalcular()
    app.processEvents()
    com = float(dlg.curvas[0].counts.max())
    assert com < sem                                   # o anel tira o fundo do abdome
    assert dlg.curvas[0].background.max() > 0
    dlg.close()


# ================================================================== mão livre e contorno automático
def test_mao_livre_vira_poligono(win):
    app, w = win
    tab, _uid, view = _renal(w)
    dlg = _dialogo(tab, view)
    dlg.canvas.kind = "freehand"
    traco = [(40 + i, 50 + (i % 5)) for i in range(20)]
    r = dlg.canvas.add_roi(traco, kind="polygon")
    app.processEvents()
    assert r.kind == "polygon" and len(r.points) == 20
    assert dlg.curvas and dlg.curvas[0].pixels > 0
    dlg.close()


def test_contorno_automatico_segue_o_limiar(win):
    app, w = win
    tab, _uid, view = _renal(w)
    dlg = _dialogo(tab, view)
    dlg.canvas.add_roi([(24, 36), (56, 84)])           # caixa grosseira em volta do rim
    app.processEvents()
    area_caixa = dlg.curvas[0].pixels
    assert dlg.canvas.auto_contour(40.0) == ""
    app.processEvents()
    r = dlg.canvas.rois[0]
    assert r.is_auto and r.auto_mask is not None
    assert 0 < int(r.auto_mask.sum()) < area_caixa     # o contorno é menor que a caixa
    assert dlg.curvas[0].pixels == int(r.auto_mask.sum())
    dlg.close()


def test_limiar_maior_da_contorno_menor(win):
    app, w = win
    tab, _uid, view = _renal(w)
    dlg = _dialogo(tab, view)
    dlg.canvas.add_roi([(24, 36), (56, 84)])
    dlg.canvas.auto_contour(30.0)
    menor_limiar = int(dlg.canvas.rois[0].auto_mask.sum())
    dlg.canvas.auto_contour(70.0)
    maior_limiar = int(dlg.canvas.rois[0].auto_mask.sum())
    assert maior_limiar < menor_limiar
    dlg.canvas.auto_contour(30.0)                      # e volta a crescer: a caixa original é guardada
    assert int(dlg.canvas.rois[0].auto_mask.sum()) == menor_limiar
    dlg.close()


def test_contorno_nao_escapa_da_caixa_desenhada(win):
    app, w = win
    tab, _uid, view = _renal(w)
    dlg = _dialogo(tab, view)
    dlg.canvas.add_roi([(24, 36), (56, 84)])
    dlg.canvas.auto_contour(20.0)
    m = dlg.canvas.rois[0].auto_mask
    ys, xs = np.nonzero(m)
    assert xs.min() >= 24 and xs.max() <= 56
    assert ys.min() >= 36 and ys.max() <= 84
    dlg.close()


def test_contorno_automatico_espelhado_continua_mascara(win):
    app, w = win
    tab, _uid, view = _renal(w)
    dlg = _dialogo(tab, view)
    dlg.canvas.add_roi([(24, 36), (56, 84)])
    dlg.canvas.auto_contour(40.0)
    dlg.canvas.mirror_selected()
    app.processEvents()
    d, e = dlg.canvas.rois
    assert e.is_auto and int(e.auto_mask.sum()) == int(d.auto_mask.sum())
    assert np.array_equal(e.auto_mask, d.auto_mask[:, ::-1])
    assert len(dlg.curvas) == 2 and all(c.pixels > 0 for c in dlg.curvas)
    dlg.close()


def test_contorno_sem_regiao_escolhida_avisa(win):
    app, w = win
    tab, _uid, view = _renal(w)
    dlg = _dialogo(tab, view)
    assert "Desenhe" in dlg.canvas.auto_contour(40.0)
    dlg.close()


# ================================================================== exame na janela
def test_trocar_o_exame_troca_nomes_conta_e_perguntas(win):
    from ipe.imaging import nm_exams
    app, w = win
    tab, _uid, view = _renal(w)
    dlg = _dialogo(tab, view)
    app.processEvents()
    assert dlg.exame.currentData() == "renograma"
    assert dlg.estimulo.isHidden()      # renograma não pergunta estímulo

    dlg.exame.setCurrentIndex(dlg.exame.findData("vesicula"))
    app.processEvents()
    assert dlg.preset == "vesicula" and dlg.canvas.preset == "vesicula"
    assert not dlg.estimulo.isHidden()
    assert dlg.rotulo_estimulo.text() == "Sincalida aos"
    r = dlg.canvas.add_roi([(30, 45), (48, 75)])
    assert r.name == nm_exams.PROTOCOLS["vesicula"].rois[0]
    app.processEvents()
    assert "Fração de ejeção" in dlg.resultado.headers
    assert "38%" in dlg.referencia.text()
    dlg.close()


def test_tabela_acompanha_as_colunas_do_exame(win):
    app, w = win
    tab, _uid, view = _renal(w)
    dlg = _dialogo(tab, view)
    dlg.canvas.add_roi([(30, 45), (48, 75)])
    app.processEvents()
    colunas_renal = dlg.tabela.columnCount()
    dlg.exame.setCurrentIndex(dlg.exame.findData("gastrico"))
    app.processEvents()
    assert dlg.tabela.columnCount() != colunas_renal
    assert dlg.tabela.horizontalHeaderItem(1).text() == "30 min"
    dlg.close()


def test_marca_do_estimulo_aparece_no_grafico(win):
    app, w = win
    tab, _uid, view = _renal(w)
    dlg = _dialogo(tab, view)
    dlg.canvas.add_roi([(30, 45), (48, 75)])
    dlg.exame.setCurrentIndex(dlg.exame.findData("salivar"))
    dlg.estimulo.setValue(3.0)
    app.processEvents()
    assert dlg.chart.marks and dlg.chart.marks[0][0] == pytest.approx(180.0)
    dlg.close()


def test_imagem_condensada_poe_o_tempo_na_horizontal(win):
    from ipe.ui.viewer.nm_analysis import CondensedDialog
    app, w = win
    tab, _uid, view = _renal(w)
    img = nm_roi.condensed(view.frames, tab.cache)
    assert img.shape[1] == len(view.frames)
    d = CondensedDialog(img, nm.info_for_file(view.frames[0].path), view.frames, "", None)
    app.processEvents()
    assert not d.tela._q.isNull()
    assert d.tela._q.width() == len(view.frames)
    d.close()


def test_condensada_limitada_a_uma_regiao(win):
    app, w = win
    tab, _uid, view = _renal(w)
    inteira = nm_roi.condensed(view.frames, tab.cache)
    r = nm_roi.Roi(name="Rim", kind="rect", points=[(30, 45), (48, 75)])
    so_roi = nm_roi.condensed(view.frames, tab.cache, roi=r)
    assert so_roi.shape == inteira.shape
    assert float(so_roi.sum()) < float(inteira.sum())
