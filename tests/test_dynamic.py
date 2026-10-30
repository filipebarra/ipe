"""Avaliação dinâmica: MSI, PEI, SER e painel de curvas."""
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.imaging.dynamic import DynamicMaps, DynamicSet, split_single_series
from ipe.imaging.measure import Annotation
from ipe.imaging.series import FrameCache, build_frames
from ipe.importer.scanner import Importer
from test_measure_tools import make_dynamic


def _sets(repo, study_uid):
    ss = sorted(repo.series_for_study(study_uid), key=lambda s: s.series_number)
    return ss, [build_frames(repo.instances_for_series(s.series_uid), s.series_uid) for s in ss]


def test_maps_values(env, tmp_path):
    paths, db, repo = env
    uid = make_dynamic(tmp_path / "d", one_series=False)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    ss, phases = _sets(repo, uid)
    dset = DynamicSet(phases[::-1], [s.description for s in ss][::-1])      # fora de ordem: reordena
    assert dset.timed and dset.times == [0, 60, 120, 180, 240] and dset.check() == ""
    assert dset.default_early() == 2
    mp = DynamicMaps(dset, FrameCache(64))
    m = mp.compute(1)
    assert m["msi"][32, 32] == pytest.approx(160, rel=1e-3)        # (260−100)/100 por minuto
    assert m["pei"][32, 32] == pytest.approx(550, rel=1e-3)
    assert m["ser"][32, 32] == pytest.approx(1.5, rel=1e-3)         # washout
    assert m["ser"][2, 2] == -1 and m["msi"][2, 2] == 0            # fundo sem realce
    assert m["ttp"][32, 32] == 120
    st = mp.curve_stats(mp.curve(1, point=(32, 32)))
    assert st["ser"] == pytest.approx(1.5) and "III" in st["type"] and st["initial"] == pytest.approx(180)
    img = mp.image("msi", 1)
    assert img.window[0] > 100 and img.pixels.shape == (64, 64)
    abs_maps = DynamicMaps(dset, FrameCache(64), relative=False)
    assert abs_maps.compute(0)["msi"][32, 32] == pytest.approx(160)   # sinal/min (pré = 100)


def test_single_series_split(env, tmp_path):
    paths, db, repo = env
    uid = make_dynamic(tmp_path / "d", one_series=True)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    s = repo.series_for_study(uid)[0]
    ph = split_single_series(build_frames(repo.instances_for_series(s.series_uid), s.series_uid))
    assert ph is not None and len(ph) == 5 and all(len(p) == 3 for p in ph)
    dset = DynamicSet(ph, [f"F{i}" for i in range(5)])
    assert dset.times == [0, 60, 120, 180, 240]


def test_dynamic_in_viewer(env, sample_dir, tmp_path):
    from ipe.ui.viewer.dynamic import DynamicDialog
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    uid = make_dynamic(tmp_path / "d", one_series=False)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1400, 850)
    w.show()
    w.browser.refresh()
    w.open_study(uid)
    tab = w.all_viewer_tabs()[-1]
    app.processEvents()
    dlg = DynamicDialog(tab)                  # detecta as 5 séries sozinho
    assert dlg.dset is not None and len(dlg.dset.phases) == 5
    assert dlg.c_early.currentIndex() == 2 and dlg.c_late.currentIndex() == 4
    params = dlg.params()
    from ipe.ui.viewer.dynamic import LAYOUTS
    params["layout"] = next(i for i, (lab, _k) in enumerate(LAYOUTS) if lab.startswith("MSI, PEI"))
    assert tab.start_dynamic(dlg.dset, params)
    assert tab._layout == (1, 3)
    a, b, c = tab.viewports[:3]
    assert [v.dyn_key for v in (a, b, c)] == ["msi", "pei", "ser"]
    assert a.state.cmap == "rainbow" and c.state.cmap == "ser"
    assert not tab.mpr_bar.isVisibleTo(tab)
    a.go_to(1)
    app.processEvents()
    ann = Annotation("probe", a.frame_key(), [(32.0, 32.0)])
    a.annotations.append(ann)
    a.sig.annotations_changed.emit(a)
    p = tab.dyn.panel
    assert p.table.rowCount() == 1 and p.table.item(0, 4).text() == "1.50"
    assert "III" in p.table.item(0, 5).text() and id(ann) in a.ann_colors
    roi = Annotation("ellipse", b.frame_key(), [(26.0, 26.0), (38.0, 38.0)])
    b.annotations.append(roi)
    b.sig.annotations_changed.emit(b)
    assert p.table.rowCount() == 3                       # ROI + pior pixel dela
    assert "pior pixel" in p.table.item(2, 1).text()
    kinds = {g[0] for g in a.ghosts}
    assert {"ellipse", "star"} <= kinds and c.ghosts and not any(g[0] == "probe" for g in a.ghosts)
    sc_uid = tab.dyn.chart_to_film()
    assert sc_uid and repo.series_info(sc_uid)["study_uid"] == uid
    comp = w.film_composer()
    assert comp.film.image_count() == 1
    comp.dirty = False
    tab.dyn.on_hover(a, 32.5, 32.5)
    assert any(d for _c, _l, _v, d in p.chart.curves)
    # trocar o mapa do quadro ativo para uma fase
    tab._activate(c)
    tab.dyn.set_active_view("ph:2")
    assert c.dyn_key == "ph:2" and not c.frames[0].is_virtual
    tab._activate(a)
    # QMessageBox modal trava o pytest: o aviso do fim é interceptado
    from PySide6.QtWidgets import QMessageBox
    avisos = []
    orig = QMessageBox.information
    QMessageBox.information = staticmethod(lambda *a_, **k_: avisos.append(a_[2]))
    try:
        tab.dyn.save_maps()
    finally:
        QMessageBox.information = orig
    assert avisos and "Séries novas no banco" in avisos[0], avisos
    assert any(k[1].startswith("dyn-msi") for k in tab._derived)
    tab.close_dynamic()
    app.processEvents()
    assert tab.dyn is None and all(v.dyn_key is None for v in tab.viewports)
    assert not a.series_uid.startswith("dyn")
    w.close()


def _make_moving(folder, shift=(3, -2)):
    """5 fases com textura; da fase 2 em diante a paciente "mexeu" (dy, dx) pixels."""
    from pydicom.uid import MRImageStorage, generate_uid
    from ipe.core.sample_data import _base, _mono, _save
    rng = np.random.default_rng(3)
    base = rng.random((16, 72, 72))
    for _ in range(3):               # suaviza para ter estrutura
        base = (base + np.roll(base, 1, 1) + np.roll(base, 1, 2) + np.roll(base, 1, 0)) / 4
    base = base / base.max() * 400 + 50
    pat = {"name": "MOV^Teste", "id": "MOV1", "birth": "19800101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20260101", "accession": "MOV001", "description": "RM", "for": generate_uid()}
    phases = []
    for ph in range(5):
        series = {"uid": generate_uid(), "number": 10 + ph, "description": f"fase {ph}"}
        vol = base * (1 + 0.1 * ph)
        if ph >= 2:
            vol = np.roll(vol, shift, axis=(1, 2))
        for k in range(16):
            ds = _base(MRImageStorage, pat, study, series, "MR")
            ds.InstanceNumber = k + 1
            ds.ImagePositionPatient = [0.0, 0.0, 2.0 * k]
            ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
            ds.PixelSpacing = [1.0, 1.0]
            ds.AcquisitionTime = f"10{ph:02d}00"
            _mono(ds, vol[k], signed=False)
            _save(ds, folder / f"p{ph}")
    return study["uid"]


def test_motion_correction(env, tmp_path):
    paths, db, repo = env
    uid = _make_moving(tmp_path / "m")
    Importer(db, paths.storage).import_paths([tmp_path / "m"])
    ss, phases = _sets(repo, uid)
    dset = DynamicSet(phases, [s.description for s in ss])
    mp = DynamicMaps(dset, FrameCache(256), motion=True)
    dz, dy, dx = mp.shifts[3]
    assert abs(dz) < 0.5 and abs(dy - 3) < 0.5 and abs(dx + 2) < 0.5
    assert mp.shifts[1] == (0.0, 0.0, 0.0)
    st = mp.stack(8)
    ratio = st[3][10:-10, 10:-10] / st[0][10:-10, 10:-10]
    assert abs(float(np.median(ratio)) - 1.3) < 0.02 and float(ratio.std()) < 0.05


# ------------------------------------------------- mapa cinético (estilo CADstream)
def _maps_falso(pre=0, early=1, late=2, **kw):
    """DynamicMaps sem exame: só o que o mapa cinético precisa."""
    from ipe.imaging.dynamic import DynamicMaps
    m = DynamicMaps.__new__(DynamicMaps)
    m.pre, m.early, m.late = pre, early, late
    m.threshold_pct = kw.get("threshold_pct", 50.0)
    m.rapido_pct = kw.get("rapido_pct", 100.0)
    m.tardio_pct = kw.get("tardio_pct", 10.0)
    m.sinal_min_pct = kw.get("sinal_min_pct", 10.0)
    m._ref = kw.get("ref", 1000.0)
    return m


def _classe(m, s0, pico, tardio):
    import numpy as np
    st = np.array([[[float(s0)]], [[float(pico)]], [[float(tardio)]]], dtype=np.float32)
    base = np.maximum(st[0], 1e-6)
    valid = np.ones((1, 1), bool)
    return int(m._cinetica(st, st[0], base, valid)[0, 0])


def test_mapa_cinetico_classifica_como_o_cadstream():
    """Dois eixos: intensidade do realce no pico e comportamento tardio."""
    m = _maps_falso()
    assert _classe(m, 200, 260, 290) == 0        # realce de 30%: abaixo do limiar, sem cor
    assert _classe(m, 200, 340, 400) == 1        # +70% (médio) e tardia subindo: persistente
    assert _classe(m, 200, 340, 345) == 2        # médio, tardia parada: platô
    assert _classe(m, 200, 340, 280) == 3        # médio, tardia caindo: washout
    assert _classe(m, 200, 500, 600) == 4        # +150% (rápido), persistente
    assert _classe(m, 200, 500, 505) == 5        # rápido, platô
    assert _classe(m, 200, 500, 400) == 6        # rápido, washout


def test_o_pico_e_uma_fase_nao_o_maximo_voxel_a_voxel():
    """Com o máximo entre as pós, o tardio nunca supera o pico e "persistente" some.

    A primeira medição no acervo do usuário deu 0,00% de persistente nos três exames — era isso.
    """
    m = _maps_falso()
    assert _classe(m, 200, 340, 420) == 1, "a curva que sobe até o fim tem que ser persistente"
    import numpy as np
    st = np.array([[[200.0]], [[340.0]], [[420.0]]], np.float32)
    pico_errado = st[1:].max(axis=0)             # o que NÃO se deve usar
    assert float(pico_errado[0, 0]) == 420.0 and float(st[m.early][0, 0]) == 340.0


def test_a_mascara_de_tecido_nao_acende_o_fundo():
    """Em porcentagem do pré, onde o pré é quase zero qualquer variação vira centenas por cento.

    Sem máscara, 36 a 44% de todo o campo saía colorido nas RM de mama do acervo.
    """
    m = _maps_falso(ref=1000.0)                  # tecido exige pré ≥ 100
    assert _classe(m, 20, 200, 120) == 0, "pré baixo demais: não é tecido, é fundo"
    assert _classe(m, 300, 700, 500) == 6        # mesmo comportamento, mas em tecido


def test_os_limiares_sao_editaveis_e_mudam_a_classe():
    assert _classe(_maps_falso(), 200, 340, 345) == 2
    assert _classe(_maps_falso(rapido_pct=60), 200, 340, 345) == 5    # 70% já é "rápido"
    assert _classe(_maps_falso(tardio_pct=1), 200, 340, 345) == 1     # ±1%: 1,5% de alta é persistente
    assert _classe(_maps_falso(tardio_pct=1), 200, 340, 335) == 3     # e 1,5% de queda é washout


def test_a_legenda_diz_quais_limiares_produziram_o_mapa():
    """Mapa colorido sem os limiares à vista é imagem bonita sem medida."""
    from types import SimpleNamespace
    m = _maps_falso()
    m.dset = SimpleNamespace(times=[0.0, 120.0, 300.0])
    texto = m.legenda_cinetica()
    for pedaco in ("50", "100", "10", "120 s", "300 s"):
        assert pedaco in texto


def test_a_classe_da_curva_bate_com_a_cor_do_mapa():
    """O número da tabela e a cor do pixel não podem divergir: mesma régua."""
    import numpy as np
    from ipe.imaging.dynamic import CLASSES
    m = _maps_falso()
    for s0, pico, tardio in ((200, 260, 290), (200, 340, 400), (200, 340, 345),
                             (200, 340, 280), (200, 500, 600), (200, 500, 505), (200, 500, 400)):
        i = _classe(m, s0, pico, tardio)
        assert m.classe_cinetica(np.array([s0, pico, tardio], float)) == CLASSES[i]


def test_a_tabela_de_cores_da_cinetica_e_chapada():
    """Classe é categoria, não escala: a cor não pode interpolar entre duas classes."""
    from ipe.imaging import colormaps as C
    lut = C.lut("cinetico")
    # o valor k (janela 7/3,5) cai no índice 255*k/7; dois pontos dentro da mesma faixa, mesma cor
    for k in range(7):
        a = lut[int(255 * (k + 0.2) / 7)]
        b = lut[int(255 * (k + 0.8) / 7)]
        assert (a == b).all(), f"a classe {k} mudou de cor no meio"
    assert (lut[0] == (0, 0, 0)).all()           # sem cor = preto


# ------------------------------------------- quem pode ser fase (o arquivo manda, não o nome)
def _frames(n=3, dz=1.0):
    import numpy as np
    from ipe.imaging.series import Frame
    return [Frame(path=f"/x/{i}.dcm", frame_index=0, sop_uid=f"s{i}", instance_number=i,
                  position=np.array([0.0, 0.0, i * dz]), orientation=np.array([1., 0, 0, 0, 1, 0]),
                  acquisition_time=f"0900{i:02d}") for i in range(n)]


def test_subtracao_e_projecao_ficam_de_fora_pelo_tipo_da_imagem():
    """A GE nomeia a subtração com a conta que a produziu — "(43798/301/60)-(43798/300/60)".

    Nenhum nome desses tem "SUB" ou "MIP": filtrar por nome deixava a subtração entrar como fase,
    e o pico passava a ser calculado sobre ela. Quem diz o que a série é, é o ImageType.
    """
    from ipe.imaging import phases as P
    assert P.fora_das_fases(["DERIVED", "PRIMARY", "OTHER", "SUBTRACT"]) == "subtração"
    assert P.fora_das_fases(["DERIVED", "SECONDARY", "PJN", "MIP"])
    assert P.fora_das_fases(["DERIVED", "SECONDARY"]) == "série derivada da estação"
    assert P.fora_das_fases(["ORIGINAL", "PRIMARY", "OTHER"]) == ""
    assert P.fora_das_fases(["DERIVED", "PRIMARY", "DIXON", "WATER"]) == "", "água do Dixon é fase"


def test_agua_e_gordura_do_dixon_sao_dinamicas_separadas(monkeypatch):
    """VIBRANT FLEX manda água e gordura com a mesma geometria: juntas viram 8 fases de mentira."""
    from ipe.imaging import phases as P
    tipos = {"w0": ["DERIVED", "PRIMARY", "DIXON", "WATER"], "w1": ["DERIVED", "PRIMARY", "DIXON", "WATER"],
             "w2": ["DERIVED", "PRIMARY", "DIXON", "WATER"], "f0": ["DERIVED", "PRIMARY", "DIXON", "FAT"],
             "f1": ["DERIVED", "PRIMARY", "DIXON", "FAT"], "f2": ["DERIVED", "PRIMARY", "DIXON", "FAT"],
             "sub": ["DERIVED", "PRIMARY", "OTHER", "SUBTRACT"]}
    monkeypatch.setattr(P, "image_type", lambda caminho: tipos[caminho.split("/")[-1]])
    cands = [(uid, [f._replace(path=f"/x/{uid}") if hasattr(f, "_replace") else f for f in _frames()],
              i, "MR", uid) for i, uid in enumerate(tipos)]
    for uid, fr, _i, _m, _d in cands:                 # dataclass: ajusta o caminho na mão
        for f in fr:
            f.path = f"/x/{uid}"
    grupos = P.detect(cands)
    assert len(grupos) == 2, "água e gordura têm que sair em grupos diferentes"
    assert {tuple(sorted(g)) for g in grupos} == {("f0", "f1", "f2"), ("w0", "w1", "w2")}
    assert all("sub" not in g for g in grupos)


def test_sem_image_type_legivel_sobra_o_nome(monkeypatch):
    from ipe.imaging import phases as P
    monkeypatch.setattr(P, "image_type", lambda _c: [])
    cands = [(uid, _frames(), i, "MR", desc) for i, (uid, desc) in
             enumerate([("a", "DYN 1"), ("b", "DYN 2"), ("c", "DYN 3"), ("d", "SUB DYN")])]
    grupos = P.detect(cands)
    assert grupos and sorted(grupos[0]) == ["a", "b", "c"]


def test_cada_classe_cai_no_meio_da_sua_cor():
    """A classe tem que sair com a cor dela, não com a da vizinha.

    Com a janela centrada em 3,5 o valor da classe caía bem na emenda entre duas faixas: a lesão
    classificada como "rápido/washout" (vermelho) aparecia verde na tela — e o número da tabela
    dizia uma coisa e a imagem dizia outra.
    """
    import numpy as np
    from ipe.imaging import colormaps as C
    from ipe.imaging.dynamic import DynamicMaps
    from ipe.imaging.windowing import apply_window
    largura, nivel = DynamicMaps.window(type("M", (), {})(), "cin")
    lut = C.lut("cinetico")
    cores = [tuple(lut[int(apply_window(np.array([[float(k)]]), largura, nivel)[0, 0])]) for k in range(7)]
    assert len(set(cores)) == 7, "duas classes com a mesma cor"
    assert cores[0] == (0, 0, 0)                      # sem cor
    assert cores[6][0] > 200 and cores[6][1] < 120    # rápido/washout: vermelho vivo
    assert cores[4][2] > 200                          # rápido/persistente: azul vivo


# ------------------------------------------- medir a lesão na dinâmica (CAD)
def _dinamica_na_aba(env, tmp_path, layout="Mapa cinético + curva"):
    from ipe.ui.main_window import MainWindow
    from ipe.ui.viewer.dynamic import LAYOUTS, DynamicDialog
    paths, db, repo = env
    uid = make_dynamic(tmp_path / "d", one_series=False)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1200, 800)
    w.show()
    w.browser.refresh()
    w.open_study(uid)
    tab = w.all_viewer_tabs()[-1]
    app.processEvents()
    dlg = DynamicDialog(tab)
    params = dlg.params()
    params["layout"] = next(i for i, (lab, _k) in enumerate(LAYOUTS) if lab == layout)
    assert tab.start_dynamic(dlg.dset, params)
    app.processEvents()
    return app, w, tab


def test_o_volume_do_realce_so_traz_tecido(env, tmp_path):
    """Fora do tecido o realce em porcentagem explode, e um voxel de ruído vira "a lesão".

    Medido no acervo: com o volume sem máscara, um exame inteiro não segmentava **nada**, porque
    o limiar relativo era calculado a partir de um voxel de 3.234% que era ar.
    """
    app, w, tab = _dinamica_na_aba(env, tmp_path)
    mp = tab.dyn.maps
    cru = mp.volume_do_mapa("ei")
    limpo = mp.volume_do_mapa("ei", so_tecido=True)
    assert float(limpo.data.max()) <= float(cru.data.max())
    fora = mp.stack(mp.n // 2)[mp.pre] < mp.reference_level() * mp.sinal_min_pct / 100.0
    assert float(np.abs(limpo.data[mp.n // 2][fora]).max(initial=0.0)) == 0.0
    w.close()


def test_clicar_na_lesao_da_os_numeros_do_cad(env, tmp_path):
    """Clique na lesão com a dinâmica ativa: volume, angiovolume, realce de pico e os 6 padrões."""
    from ipe.imaging import cad_mama as C
    from ipe.imaging.segment import segment
    app, w, tab = _dinamica_na_aba(env, tmp_path)
    vp = tab.viewports[0]
    assert tab.dyn.is_dyn(vp), "o quadro tem que ser da dinâmica"
    realce, classes = tab.dyn.volumes_cad()
    assert realce.data.shape == classes.shape
    nz, ny, nx = realce.data.shape
    semente = (nz // 2, ny // 2, nx // 2)
    assert realce.data[semente] > 50, "a lesão do fantoma realça"
    res = segment(realce, semente, "realce_pct", None, None, None, 50.0)
    m = C.medir(realce, classes, res)
    assert m.ml > 0 and m.angio_ml > 0
    assert m.realce_pico >= m.realce_medio > 0
    assert m.maior_3d_mm >= max(m.diametros_mm) - 1e-6
    assert sum(m.percentuais.values()) == pytest.approx(100.0, abs=0.01)
    assert any(rot == "Angiovolume" for rot, _v in m.linhas())
    # e o mesmo caminho pela tela, com a janela de medida
    tab.segment_at(vp, float(nx // 2), float(ny // 2))
    janelas = [d for d in getattr(tab, "_seg_dialogs", []) if d.isVisible()]
    assert janelas, "o clique tem que abrir a janela da medida"
    jan = janelas[-1]
    assert jan.cad is not None and jan.medidas is not None
    assert jan.method.currentData() == "realce_pct"
    assert "Angiovolume" in jan.result.text()
    jan.discard()
    w.close()


def test_o_clique_na_lesao_passa_pelo_mouse(env, tmp_path):
    """O mesmo CAD, mas pelo caminho de verdade: ferramenta escolhida e clique com o mouse."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest
    app, w, tab = _dinamica_na_aba(env, tmp_path)
    vp = tab.viewports[0]
    tab.set_left_tool("grow")
    nz, ny, nx = tab.dyn.volumes_cad()[0].data.shape
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier,
                     vp.image_to_widget(QPointF(nx // 2, ny // 2)).toPoint())
    app.processEvents()
    janelas = [d for d in getattr(tab, "_seg_dialogs", []) if d.isVisible()]
    assert janelas, "o clique com o mouse tem que abrir a janela da medida"
    janelas[-1].discard()
    w.close()


def test_a_fase_e_selecionavel_com_o_dinamico_ligado(env, tmp_path):
    """Com o dinâmico ativo o quadro de fase mostra a linha da fase e anda por elas."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    app, w, tab = _dinamica_na_aba(env, tmp_path,
                                   layout="Mapa cinético, subtração e fase inicial + curva")
    vp = next(v for v in tab.dyn.vps if str(v.dyn_key).startswith("ph:"))
    assert vp.phases and len(vp.phases) == len(tab.dyn.maps.dset.phases)
    vp.repaint()
    app.processEvents()
    assert "fase" in vp._hotspots, "a linha da fase tem que aparecer no canto"
    antes = vp.phase
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, vp._hotspots["fase"].center().toPoint())
    app.processEvents()
    assert vp.phase == (antes + 1) % len(vp.phases)
    assert vp.dyn_key == f"ph:{vp.phase}" and f"Fase {vp.phase + 1}" in vp.series_label
    assert tab.dyn.is_dyn(vp), "continua sendo um quadro da dinâmica"
    # botão direito volta uma fase
    QTest.mouseClick(vp, Qt.RightButton, Qt.NoModifier, vp._hotspots["fase"].center().toPoint())
    app.processEvents()
    assert vp.phase == antes
    w.close()
