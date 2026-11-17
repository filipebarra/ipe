"""0.100.67: farmacocinética da dinâmica — Tofts e Tofts estendido (Ktrans, ve, kep, vp)."""
import numpy as np
import pytest

from ipe.imaging import tofts as T


def test_aif_de_parker():
    t = np.arange(0, 6, 1 / 600)
    cp = T.aif_parker(t, 0.42)
    assert T.aif_parker([-1.0, 0.0]).tolist() == [0.0, 0.0]            # antes da injeção: nada
    assert 0.15 < t[np.argmax(cp)] < 0.19                              # primeiro pico por volta de 10 s
    assert 9.5 < cp.max() < 11.5                                       # ~6 mM no sangue → ~10,5 mM no plasma
    assert 0.6 < T.aif_parker([5.0])[0] < 0.95                         # a cauda, aos 5 min
    assert T.aif_parker([1.0], 0.30)[0] < T.aif_parker([1.0], 0.50)[0]  # mais hematócrito, menos plasma


@pytest.mark.parametrize("linear", [False, True])
@pytest.mark.parametrize("kt,ve", [(0.1, 0.3), (0.25, 0.4), (0.5, 0.5)])
def test_ajuste_recupera_os_parametros_com_boa_resolucao(linear, kt, ve):
    cfg = T.Config(tr_ms=0 if linear else 5.0, angulo=0 if linear else 12.0, inicio_s=10)
    assert cfg.linear() == linear
    t = np.arange(0, 421, 5) / 60
    s = T.simular(t, kt, ve, cfg)
    r = T.da_curva(s, t, s[0], cfg)
    assert r["ok"] and r["ktrans"] == pytest.approx(kt, rel=0.03) and r["ve"] == pytest.approx(ve, rel=0.03)
    assert r["kep"] == pytest.approx(kt / ve, rel=0.05) and r["vp"] == 0


def test_estendido_recupera_o_vp_e_o_simples_erra_sem_ele():
    cfg = T.Config(tr_ms=5.0, angulo=12.0, inicio_s=10, modelo="estendido")
    t = np.arange(0, 421, 5) / 60
    s = T.simular(t, 0.25, 0.4, cfg, vp=0.05)
    r = T.da_curva(s, t, s[0], cfg)
    assert r["ktrans"] == pytest.approx(0.25, rel=0.03) and r["vp"] == pytest.approx(0.05, rel=0.1)
    simples = T.da_curva(s, t, s[0], T.Config(tr_ms=5.0, angulo=12.0, inicio_s=10))
    assert simples["ktrans"] > 0.25 * 1.1                              # o plasma entra na conta como passagem


def test_uma_fase_por_minuto_da_numero_indicativo_e_avisa():
    cfg = T.Config(tr_ms=5.0, angulo=12.0, inicio_s=30)
    t = np.arange(0, 421, 60) / 60
    for kt, ve in ((0.1, 0.3), (0.25, 0.4)):
        s = T.simular(t, kt, ve, cfg)
        r = T.da_curva(s, t, s[0], cfg)
        assert r["ok"] and r["ktrans"] == pytest.approx(kt, rel=0.15) and r["ve"] == pytest.approx(ve, rel=0.1)
    av = " ".join(T.avisos(cfg, t * 60, 7))
    assert "a cada 60 s" in av and "indicativo" in av and "1400 ms" in av and "Parker" in av
    est = " ".join(T.avisos(T.Config(modelo="estendido"), t * 60, 2))
    assert "vp não é confiável" in est and "Só 2 fases" in est and "aproximação linear" in est
    bom = " ".join(T.avisos(cfg, np.arange(0, 300, 6), 40))
    assert "indicativo" not in bom
    assert T.resolucao_temporal([0, 60, 120, 185]) == 60 and T.resolucao_temporal([5]) == 0


def test_mapas_vetorizados_fundo_e_ajuste_que_nao_fecha():
    cfg = T.Config(tr_ms=5.0, angulo=12.0, inicio_s=10)
    t = np.arange(0, 301, 10) / 60
    pilha = np.full((len(t), 4, 5), 100.0)
    pilha[:, 1, 2] = T.simular(t, 0.3, 0.35, cfg)
    pilha[:, 2, 3] = T.simular(t, 0.08, 0.2, cfg)
    pilha[:, 3, 4] = 100.0 - 20 * t                                    # sinal que cai: não é realce
    m = T.mapas(pilha, t, pilha[0], cfg)
    assert m["ktrans"].shape == (4, 5) and m["ktrans"][1, 2] == pytest.approx(0.3, rel=0.05)
    assert m["ve"][2, 3] == pytest.approx(0.2, rel=0.05) and m["kep"][2, 3] == pytest.approx(0.4, rel=0.08)
    assert m["ktrans"][0, 0] == 0 and not m["ok"][0, 0] and m["ktrans"][3, 4] == 0 and not m["ok"][3, 4]
    assert np.isfinite(m["ktrans"]).all() and np.isfinite(m["ve"]).all()


def test_entrada_arterial_de_uma_roi():
    cfg = T.Config(tr_ms=0, angulo=0, inicio_s=10, aif="roi", t10_sangue_ms=1500.0)
    t = np.arange(0, 421, 3) / 60
    cb = T.aif_parker(t - 10 / 60, cfg.hematocrito) * (1 - cfg.hematocrito)          # sangue, não plasma
    sinal_aif = 200.0 * (1 + cfg.r1 * cb * 1.5)
    s = T.simular(t, 0.2, 0.3, cfg)
    r = T.da_curva(s, t, s[0], cfg, sinal_aif, 200.0)
    assert r["ok"] and r["ktrans"] == pytest.approx(0.2, rel=0.08) and r["ve"] == pytest.approx(0.3, rel=0.08)
    cp, icp = T.plasma(t, cfg, sinal_aif, 200.0)
    assert cp.max() > 8 and icp[-1] > icp[len(icp) // 2] > 0


def test_config_vai_e_volta_e_t1_por_campo():
    c = T.Config(modelo="estendido", aif="roi", aif_sinal=[1.0, 2.0], t10_ms=1234)
    d = c.para_dict()
    assert d["aif_sinal"] == [1.0, 2.0] and T.Config.de_dict(d) == c and T.Config.de_dict(None) == T.Config()
    assert T.t1_padrao(3.0)[0] > T.t1_padrao(1.5)[0] and T.t1_padrao(0) == T.t1_padrao(1.5)


# ---------------------------------------------------------------- nos mapas da dinâmica e no painel
def _dinamica(env, tmp_path):
    from ipe.imaging.dynamic import DynamicMaps, DynamicSet
    from ipe.imaging.series import FrameCache, build_frames
    from ipe.importer.scanner import Importer
    from test_measure_tools import make_dynamic
    paths, db, repo = env
    uid = make_dynamic(tmp_path / "d", one_series=False)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    ss = sorted(repo.series_for_study(uid), key=lambda s: s.series_number)
    fases = [build_frames(repo.instances_for_series(s.series_uid), s.series_uid) for s in ss]
    return uid, DynamicMaps(DynamicSet(fases, [s.description for s in ss]), FrameCache(64))


def test_mapas_de_tofts_na_dinamica(env, tmp_path):
    from ipe.imaging import dynamic as D
    _uid, mp = _dinamica(env, tmp_path)
    assert "ktrans" not in D.MAPS and "ktrans" in D.TODOS_OS_MAPAS       # o Ipê Web lista MAPS: não oferece Tofts
    m = mp.compute(1)
    assert "ktrans" not in m and mp.curve_stats(mp.curve(1, point=(32, 32)))["tofts"] is None
    mp.set_tofts(T.Config(inicio_s=30))
    m = mp.compute(1)
    assert m["ktrans"].dtype == np.float32 and m["ktrans"][32, 32] > 0.05 and m["ktrans"][2, 2] == 0
    assert 0 < m["ve"][32, 32] <= 1 and m["kep"][32, 32] > 0 and m["vp"][32, 32] == 0
    st = mp.curve_stats(mp.curve(1, point=(32, 32)))
    assert st["tofts"]["ok"] and st["tofts"]["ktrans"] == pytest.approx(float(m["ktrans"][32, 32]), rel=1e-3)
    assert mp.window("ve") == (1.0, 0.5) and mp.window("ktrans")[0] > 0
    assert mp.image("ktrans", 1).pixels.shape == (64, 64)
    # entrada arterial pela ROI: a curva tem de ter uma amostra por fase; senão vale a populacional
    mp.set_tofts(T.Config(aif="roi", aif_sinal=[100, 900, 500, 400, 350]))
    assert mp._aif_reduzida()[0] is not None and mp.compute(1)["ktrans"][32, 32] > 0
    mp.set_tofts(T.Config(aif="roi", aif_sinal=[1, 2]))
    assert mp._aif_reduzida() == (None, None)
    mp.set_tofts(None)
    assert "ktrans" not in mp.compute(1)


def test_tofts_no_visualizador(env, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from ipe.core.config import Settings
    from ipe.imaging.measure import Annotation
    from ipe.ui.main_window import MainWindow
    from ipe.ui.viewer.dynamic import LAYOUTS, DynamicDialog
    from ipe.ui.viewer.tofts_dialogo import ToftsDialog, parametros_do_exame
    uid, _mp = _dinamica(env, tmp_path)
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file))
    try:
        w.resize(1400, 850)
        w.show()
        w.browser.refresh()
        w.open_study(uid)
        tab = w.all_viewer_tabs()[-1]
        app.processEvents()
        dlg = DynamicDialog(tab)
        params = dlg.params()
        params["layout"] = next(i for i, (lab, _k) in enumerate(LAYOUTS) if lab.startswith("MSI, PEI"))
        assert tab.start_dynamic(dlg.dset, params)
        s = tab.dyn
        a = tab.viewports[0]
        a.go_to(1)
        tab._activate(a)
        a.annotations.append(Annotation("probe", a.frame_key(), [(32.0, 32.0)]))
        a.sig.annotations_changed.emit(a)
        assert s.panel.table.rowCount() == 1
        assert s.panel.table.columnCount() == len(s.panel.COLS)
        assert s.panel.c_view.findData("ktrans") < 0
        # a janela: sem TR no exame sintético → aproximação linear, com os avisos à vista
        d = ToftsDialog(s)
        cfg = d.config()
        assert cfg.linear() and cfg.inicio_s == 30 and cfg.aif == "parker" and not d.b_desligar.isEnabled()
        assert "a cada 60 s" in d.l_avisos.text() and "aproximação linear" in d.l_avisos.text()
        d.s_tr.setValue(5.0)
        d.s_ang.setValue(12.0)
        assert "aproximação linear" not in d.l_avisos.text()
        assert s.aplicar_tofts(d.config())
        assert a.dyn_key == "msi" and tab.viewports[2].dyn_key == "ktrans"    # o quadro com ROI não é trocado
        assert s.panel.c_view.findData("ktrans") >= 0 and s.panel.c_view.findData("vp") < 0
        assert "Ktrans indicativo" in s.panel.title.text() and s.params["tofts"]["tr_ms"] == 5.0
        assert s.panel.table.columnCount() == len(s.panel.COLS) + 3
        assert s.panel.table.rowCount() == 1 and float(s.panel.table.item(0, len(s.panel.COLS)).text()) > 0
        # a ROI que já existe é oferecida como entrada arterial
        d3 = ToftsDialog(s)
        i = next(i for i in range(d3.c_aif.count()) if d3.c_aif.itemData(i)[0] == "roi")
        d3.c_aif.setCurrentIndex(i)
        c3 = d3.config()
        assert c3.aif == "roi" and len(c3.aif_sinal) == 5 and "ROI" in d3.l_avisos.text()
        assert not d3.s_inicio.isEnabled() and d3.s_t10s.isEnabled()
        s.panel.copy_values()
        assert "Ktrans (1/min)" in QApplication.clipboard().text()
        # "Parâmetros…" refaz os mapas: a farmacocinética continua
        assert tab.start_dynamic(dlg.dset, dict(s.params))
        s = tab.dyn
        assert s.maps.tofts is not None and s.maps.tofts.tr_ms == 5.0
        tab.viewports[0].go_to(1)
        s.show_view(tab.viewports[0], "ktrans")
        # estendido: o vp entra na lista; desligar: os quadros voltam e as colunas somem
        est = T.Config.de_dict({**s.params["tofts"], "modelo": "estendido"})
        assert s.aplicar_tofts(est) and s.panel.c_view.findData("vp") >= 0
        d2 = ToftsDialog(s)
        assert d2.b_desligar.isEnabled() and d2.c_modelo.currentData() == "estendido"
        d2._desligar()
        assert d2.desligar and s.aplicar_tofts(None)
        assert tab.viewports[0].dyn_key == "ei" and "ktrans" not in [v.dyn_key for v in tab.viewports] \
            and s.panel.table.columnCount() == len(s.panel.COLS)
        assert s.panel.c_view.findData("ktrans") < 0 and s.params["tofts"] is None
        # TR e ângulo do cabeçalho
        import pydicom
        f = s.maps.dset.phases[0][0].path
        ds = pydicom.dcmread(f)
        ds.RepetitionTime, ds.FlipAngle, ds.MagneticFieldStrength = 4.8, 10, 30000
        ds.save_as(tmp_path / "x.dcm")
        assert parametros_do_exame(str(tmp_path / "x.dcm")) == {"tr_ms": 4.8, "angulo": 10.0, "campo_t": 3.0}
        assert parametros_do_exame(str(tmp_path / "nao_existe.dcm"))["tr_ms"] == 0
    finally:
        w.close()
