"""Lesão de mama na dinâmica (0.67): barra do limiar, só o mamilo, captura 2×2 e edição.

Pedido dele (10/10/2026): *"retire a distância até o peitoral e pele. mantenha apenas a distância
do mamilo, como está. quero poder ajustar o threshold, em uma barra (...). depois que eu segmentei,
quero ter a opção de salvar a lesão em uma screencapture 2x2 (...). depois que a lesão for
segmentada, quero poder acessá-la no menu de medidas e poder editá-la. se eu editar a lesão e for
salvar o SC, pergunte se eu quero substituir o anterior (se já existir) ou criar novo"*.
"""
import time

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from test_dynamic import _dinamica_na_aba


def _janela_da_lesao(tab):
    vp = tab.viewports[0]
    nz, ny, nx = tab.dyn.volumes_cad()[0].data.shape
    tab.segment_at(vp, float(nx // 2), float(ny // 2))
    jan = [d for d in getattr(tab, "_seg_dialogs", []) if d.isVisible()][-1]
    return vp, jan


def _esperar(app, cond, limite=5.0):
    t0 = time.time()
    while not cond() and time.time() - t0 < limite:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()
    return cond()


@pytest.fixture()
def lesao(env, tmp_path):
    app, w, tab = _dinamica_na_aba(env, tmp_path)
    vp, jan = _janela_da_lesao(tab)
    yield app, w, tab, vp, jan
    jan.close()
    w.close()


# ------------------------------------------------------------------ só o mamilo
def test_a_medida_guardada_so_leva_o_mamilo():
    from ipe.ui.viewer.onco import SegmentDialog
    dlg = SegmentDialog.__new__(SegmentDialog)
    dlg.dist = {"pele": 8.44, "mamilo": 42.2, "mamilo_centro": 50.1, "posterior": 15.0,
                "mamilo_manual": True, "mamilo_ponto": np.array([1.0, 2.0, 3.0]),
                "centro_mm": np.zeros(3)}
    meta = dlg.distancias_meta()
    assert "dist_pele_mm" not in meta and "dist_peitoral_mm" not in meta
    assert meta["dist_mamilo_mm"] == 42.2 and meta["dist_mamilo_centro_mm"] == 50.1
    assert meta["mamilo_marcado"] is True and meta["mamilo_mm"] == [1.0, 2.0, 3.0]
    dlg.dist = {"pele": 3.0, "posterior": 3.0}
    assert dlg.distancias_meta() == {}, "sem mamilo, nada de distância"


def test_a_tela_so_mostra_o_mamilo():
    from ipe.imaging import mama_distancias as MD
    d = {"pele": 8.0, "mamilo": 42.0, "mamilo_centro": 50.0, "posterior": 15.0, "mamilo_manual": False}
    rot = [r for r, _v in MD.linhas_mamilo(d)]
    assert rot == ["Distância ao mamilo"]
    refs = MD.Referencias(np.zeros((0, 3)), np.zeros((0, 3)), np.zeros((0, 3)), np.zeros((0, 3)),
                          avisos=["… a distância ao peitoral não sai.",
                                  "Não achei a pele neste exame: o mamilo tem de ser marcado à mão."])
    assert MD.avisos_do_mamilo(refs) == [refs.avisos[1]]


def test_o_rotulo_da_medida_mostra_o_mamilo():
    from ipe.imaging import measure as M
    a = M.Annotation("seg", ("x", 0), [(1, 1)], "Lesão 1")
    a.meta = {"ml": 1.2, "eixos_mm": [12.0, 10.0, 8.0], "dist_mamilo_mm": 42.4}
    assert "Mamilo 42 mm" in M.labels(a, None, (1.0, 1.0), "MR")


def test_a_janela_nao_fala_mais_de_pele_nem_de_peitoral(lesao):
    app, w, tab, vp, jan = lesao
    assert jan.b_dist.text() == "Distância ao mamilo"
    assert "peitoral" not in jan.b_dist.toolTip() and "pele" not in jan.b_dist.text()


# ------------------------------------------------------------------ barra do limiar
def test_a_barra_mexe_no_limiar_e_refaz_a_lesao(lesao):
    app, w, tab, vp, jan = lesao
    assert jan.method.currentData() == "realce_pct"
    assert jan.barra.isVisibleTo(jan) and jan.barra.value() == int(jan.pct.value())
    antes = jan.res.voxels
    assert antes > 0
    jan.barra.setValue(90)                     # mais apertado: menos tecido
    assert jan.pct.value() == 90
    assert _esperar(app, lambda: jan.res.voxels != antes or not jan._t_barra.isActive())
    apertado = jan.res.voxels
    assert apertado <= antes
    jan.barra.setValue(10)                     # mais solto: mais tecido
    assert _esperar(app, lambda: not jan._t_barra.isActive())
    assert jan.res.voxels >= apertado
    # o campo também move a barra
    jan.pct.setValue(33)
    assert jan.barra.value() == 33


def test_a_barra_segue_o_metodo_fixo(lesao):
    app, w, tab, vp, jan = lesao
    jan.method.setCurrentIndex(jan.method.findData("realce"))
    assert jan.barra.maximum() >= 300, "realce mínimo fixo passa de 100%"
    jan.barra.setValue(120)
    assert jan.limiar.value() == 120


# ------------------------------------------------------------------ captura 2×2
def test_a_curva_da_lesao_e_a_media_dos_voxels(lesao):
    app, w, tab, vp, jan = lesao
    mp = tab.dyn.maps
    curva = mp.curva_da_lesao(jan.res.mask, jan.res.offset)
    k0, j0, i0 = jan.res.offset
    vals = []
    for dk in range(jan.res.mask.shape[0]):
        sl = jan.res.mask[dk]
        st = mp.stack(k0 + dk)[:, j0:j0 + sl.shape[0], i0:i0 + sl.shape[1]]
        vals.append(st[:, sl])
    esperado = np.concatenate(vals, axis=1).mean(axis=1)
    assert curva == pytest.approx(esperado, rel=1e-4)
    assert curva[mp.early] > curva[mp.pre], "a lesão do fantoma realça"


def test_a_captura_tem_os_quatro_quadros_e_o_rodape(lesao, tmp_path):
    from ipe.ui.viewer import lesao_captura as L
    app, w, tab, vp, jan = lesao
    d = jan.dados_da_captura()
    rotulos = [r for r, _v in d.linhas]
    assert {"Volume", "Angiovolume", "Realce de pico", "Eixos perpendiculares",
            "Limiar da segmentação"} <= set(rotulos)
    assert not any("pele" in r.lower() or "peitoral" in r.lower() for r in rotulos)
    assert d.curva is not None and d.tipo_curva
    assert set(L.planos(d.fase)) == {"Sagital", "Coronal", "Axial"}
    assert d.rotulo_fase.startswith("Fase 2"), "a captura usa a 2ª fase (pedido dele)"
    assert d.fase is tab.dyn.maps.volume_da_fase(1)
    img = L.montar(d)
    assert img.width() == 2 * L.LARG + 3 * L.VAO and img.height() > 2 * L.ALT
    img.save(str(tmp_path / "captura.png"))
    # a lesão aparece nos três quadros: a cor dela está dentro de cada um
    from ipe.imaging.derived import qimage_to_rgb
    rgb = qimage_to_rgb(img).astype(int)
    cor = np.array(d.cor)
    cab = 64
    for x, y in ((L.VAO, cab + L.VAO), (2 * L.VAO + L.LARG, cab + L.VAO), (L.VAO, cab + 2 * L.VAO + L.ALT)):
        q = rgb[y:y + L.ALT, x:x + L.LARG]
        assert (np.abs(q - cor).sum(axis=2) < 30).sum() > 20, "a borda da lesão não apareceu no quadro"


def test_o_quadro_mostra_o_plano_inteiro_sem_zoom():
    """Pedido dele (0.68): "não aplique zoom na lesão no SC. mantenha o zoom no objeto todo"."""
    from ipe.imaging.volume import Volume
    from ipe.ui.viewer import lesao_captura as L
    dados = np.zeros((20, 60, 80), np.float32)
    mask = np.ones((4, 6, 6), bool)
    off = (8, 40, 10)
    dados[8:12, 40:46, 10:16] = 100
    vol = Volume(data=dados, origin=np.zeros(3), row_dir=np.array([1.0, 0, 0]),
                 col_dir=np.array([0, 1.0, 0]), slice_vec=np.array([0, 0, 2.0]), dx=1, dy=1,
                 window=None, source_path="")
    centro = L.centro_mm(vol, mask, off)
    assert centro == pytest.approx([12.5, 42.5, 19.0])
    pl = L.planos(vol)
    img, m = L.quadro_do_plano(pl["Axial"], pl["Axial"], centro)
    assert img.shape == (60, 80), "o plano inteiro, não um recorte em volta da lesão"
    assert m.sum() == 36 and img[m].min() == 100, "a máscara cai em cima da lesão"
    larg, alt, _esc = L.encaixe(pl["Axial"], img.shape)
    assert larg == pytest.approx(L.LARG) and alt == pytest.approx(60 / 80 * L.LARG), \
        "cabe no quadro na proporção física"


def test_salvar_a_captura_e_perguntar_ao_salvar_de_novo(lesao):
    app, w, tab, vp, jan = lesao
    repo = tab.repo
    n_series = len(repo.series_for_study(vp.study_uid))
    uid1 = jan.salvar_captura()
    assert uid1, "a captura não foi gravada"
    assert jan.saved_ann is not None and jan.saved_ann.meta["sc_series"] == uid1
    assert len(repo.instances_for_series(uid1)) == 1
    assert len(repo.series_for_study(vp.study_uid)) == n_series + 1
    perguntas = []
    jan.perguntar_substituir = lambda: perguntas.append(1) or "substituir"
    uid2 = jan.salvar_captura()
    assert perguntas, "já havia captura: tinha que perguntar"
    assert uid2 and uid2 != uid1
    assert not repo.instances_for_series(uid1), "substituir apaga a anterior"
    assert jan.saved_ann.meta["sc_series"] == uid2
    jan.perguntar_substituir = lambda: "nova"
    uid3 = jan.salvar_captura()
    assert repo.instances_for_series(uid2) and repo.instances_for_series(uid3), "criar nova guarda as duas"
    jan.perguntar_substituir = lambda: None
    assert jan.salvar_captura() is None, "cancelar não grava nada"


# ------------------------------------------------------------------ editar pelo painel de medidas
def test_editar_a_lesao_pelo_painel_de_medidas(lesao):
    from ipe.ui.viewer.measures_panel import MeasuresPanel
    app, w, tab, vp, jan = lesao
    jan.pct.setValue(60)
    jan.run(keep_range=True)
    jan.name.setText("Lesão QSL")
    jan.save()
    db_id = jan.saved_ann.db_id
    # defeito achado no caminho: no quadro do mapa a medida não tinha imagem do banco e nunca era
    # gravada — por isso a lesão do CAD não aparecia no painel de medidas
    assert db_id, "a lesão da dinâmica tem que ir para o banco"
    assert jan.saved_ann.frame_key[0] and jan.saved_ann.series_uid
    assert jan.saved_ann.meta["pct"] == 60 and jan.saved_ann.meta["semente_mm"]
    jan.close()
    painel = MeasuresPanel(tab)
    painel.refresh()
    linha = next(r for r, d in enumerate(painel.linhas) if d["id"] == db_id)
    painel.table.selectRow(linha)
    assert painel.b_lesao.isEnabled()
    mapa_antes = vp.series_uid
    nova = painel.editar_lesao()
    assert nova is not None and nova.existente is not None
    assert tab.active.series_uid == mapa_antes, "editar não pode trocar o mapa cinético do quadro"
    assert nova.pct.value() == 60 and nova.name.text() == "Lesão QSL"
    assert nova.method.currentData() == "realce_pct"
    nova.pct.setValue(75)
    nova.run(keep_range=True)
    nova.save()
    recs = [r for r in tab.repo.annotations_for_studies([vp.study_uid]) if r.get("kind") == "seg"]
    assert len(recs) == 1, "editar não pode criar outra medida"
    import json
    assert json.loads(recs[0]["data"])["meta"]["pct"] == 75
    nova.close()
    painel.close()


def test_editar_lesao_sem_a_dinamica_aberta_oferece_abrir(lesao, monkeypatch):
    """No primeiro dia ele bateu quatro vezes em "abra a dinâmica e peça de novo" (log de 10/10):
    agora a pergunta é se abre já, com as fases da lesão escolhidas."""
    app, w, tab, vp, jan = lesao
    jan.save()
    ann = jan.saved_ann
    assert ann.meta.get("dyn_uids"), "a lesão guarda as fases da dinâmica em que foi medida"
    jan.close()
    sessao = tab.dyn
    tab.dyn = None
    perguntas, aberturas = [], []
    monkeypatch.setattr(tab, "perguntar_abrir_dinamica", lambda: perguntas.append(1) or False)
    try:
        assert tab.editar_segmentacao(vp, ann) is None, "disse não: não abre nada"
        monkeypatch.setattr(tab, "perguntar_abrir_dinamica", lambda: True)

        def abrir(previous=None):
            aberturas.append(previous)
            tab.dyn = sessao
            return True
        monkeypatch.setattr(tab, "open_dynamic", abrir)
        dlg = tab.editar_segmentacao(vp, ann)
    finally:
        tab.dyn = sessao
    assert perguntas and aberturas and aberturas[0]["uids"] == ann.meta["dyn_uids"]
    assert dlg is not None and dlg.existente is ann
    dlg.close()


def test_aquisicao_sagital_como_a_dele():
    """A RM de mama dele é sagital, corte de 3 mm e pixel de 0,45 mm: os três quadros têm de
    passar pela lesão e se chamar certo (o fantoma da dinâmica é axial)."""
    from ipe.imaging.volume import Volume
    from ipe.ui.viewer import lesao_captura as L
    nz, ny, nx = 40, 200, 200                  # cortes sagitais (x), linhas (z), colunas (y)
    dados = np.zeros((nz, ny, nx), np.float32)
    off = (18, 90, 120)
    mask = np.ones((4, 22, 22), bool)          # ~12 mm em x, ~10 mm em y/z
    dados[18:22, 90:112, 120:142] = 100
    vol = Volume(data=dados, origin=np.array([-60.0, -45.0, 45.0]),
                 row_dir=np.array([0, 1.0, 0]), col_dir=np.array([0, 0, -1.0]),
                 slice_vec=np.array([3.0, 0, 0]), dx=0.45, dy=0.45, window=None, source_path="")
    pl = L.planos(vol)
    assert set(pl) == {"Sagital", "Coronal", "Axial"}
    centro = L.centro_mm(vol, mask, off)
    cheio = np.zeros(dados.shape, np.uint8)
    cheio[18:22, 90:112, 120:142] = 1
    vm = Volume(data=cheio, origin=vol.origin, row_dir=vol.row_dir, col_dir=vol.col_dir,
                slice_vec=vol.slice_vec, dx=vol.dx, dy=vol.dy, window=None, source_path="")
    pm = L.planos(vm)
    for nome, plano in pl.items():
        img, m = L.quadro_do_plano(plano, pm[nome], centro)
        assert m.any() and img[m].min() == 100, f"{nome}: o plano não passou pela lesão"
        larg, alt, _e = L.encaixe(plano, img.shape)
        assert larg <= L.LARG + 1e-6 and alt <= L.ALT + 1e-6


# ------------------------------------------------------------------ 0.68: a lesão em todas as séries
def _mv_simples():
    from ipe.imaging import overlays as O
    from ipe.imaging.volume import Volume
    vol = Volume(data=np.zeros((10, 40, 40), np.float32), origin=np.array([0.0, 0.0, 0.0]),
                 row_dir=np.array([1.0, 0, 0]), col_dir=np.array([0, 1.0, 0]),
                 slice_vec=np.array([0, 0, 3.0]), dx=0.5, dy=0.5, window=None, source_path="")
    mascara = np.ones((2, 10, 10), bool)          # 5 mm × 5 mm × 6 mm, começando em (5, 5, 12) mm
    return O.MaskVolume.do_volume(vol, mascara, (4, 10, 10), (255, 0, 0), "L")


def test_a_mascara_em_mm_corta_qualquer_plano():
    """A lesão segmentada num axial aparece num sagital (plano perpendicular)."""
    mv = _mv_simples()
    # sagital em x = 7 mm: linhas = z para baixo, colunas = y; pixel de 1 mm
    pos = np.array([7.0, 0.0, 30.0])
    row, col = np.array([0, 1.0, 0]), np.array([0, 0, -1.0])
    corte = mv.fatia(pos, row, col, np.cross(row, col), (1.0, 1.0), (40, 40))
    assert corte is not None
    x0, y0, mf = corte
    ys, xs = np.nonzero(mf.mask)
    assert 4 <= x0 + xs.min() <= 6 and 8 <= x0 + xs.max() <= 10, "y da lesão: 5 a 10 mm"
    assert 14 <= y0 + ys.min() <= 16 and 16 <= y0 + ys.max() <= 19, "z da lesão: 12 a 18 mm"
    # um sagital fora da lesão não desenha nada
    assert mv.fatia(np.array([30.0, 0, 30.0]), row, col, np.cross(row, col), (1.0, 1.0), (40, 40)) is None


def test_a_mascara_vai_e_volta_da_medida():
    from ipe.imaging import overlays as O
    mv = _mv_simples()
    d = mv.para_meta()
    import json
    assert len(json.dumps(d)) < 2000, "a máscara cabe na medida sem pesar"
    de_novo = O.MaskVolume.da_meta(json.loads(json.dumps(d)), (0, 255, 0))
    assert (de_novo.mascara == mv.mascara).all()
    assert de_novo.origem == pytest.approx(mv.origem) and de_novo.matriz == pytest.approx(mv.matriz)


def test_salvar_nao_some_com_a_lesao_e_ela_volta_ao_reabrir(lesao):
    """Pedido dele: "quando estou salvando a segmentação, ela está 'sumindo' e um círculo pequeno
    fica no lugar". A máscara vai para a medida e volta desenhada, em todas as séries."""
    app, w, tab, vp, jan = lesao
    jan.save()
    db_id = jan.saved_ann.db_id
    assert jan.saved_ann.meta.get("mascara3d") and jan.saved_ann.meta.get("cor")
    jan.close()
    segs = [o for o in tab.overlay_objects if o.source == "Segmentação"]
    assert len(segs) == 1 and segs[0].key == f"segann:{db_id}", "uma lesão, desenhada uma vez"
    # reabrir o exame: tira tudo da memória e lê do banco
    tab.overlay_objects[:] = []
    assert tab.carregar_segmentacoes() == 1
    obj = next(o for o in tab.overlay_objects if o.key == f"segann:{db_id}")
    assert obj.volumes and obj.volumes[0].mascara.any()
    # e aparece no quadro de outra fase (outra série do exame)
    outro = next(v for v in tab.viewports if v is not vp)
    uid_fase = tab.dyn.maps.dset.phases[0][0].series_uid
    tab.load_series_into(outro, uid_fase)
    outro.go_to(len(outro.frames) // 2)
    pos, row, col, n = outro.plane()
    h, w_ = outro._img.pixels.shape[:2]
    assert obj.volumes[0].fatia(pos, row, col, n, outro._spacing(), (h, w_)) is not None
    # apagar a medida apaga a máscara
    tab.repo.delete_annotation(db_id)
    tab.carregar_segmentacoes()
    assert not [o for o in tab.overlay_objects if o.key == f"segann:{db_id}"]


def test_editar_e_desistir_volta_a_mascara_guardada(lesao):
    app, w, tab, vp, jan = lesao
    jan.save()
    ann = jan.saved_ann
    jan.close()
    dlg = tab.editar_segmentacao(vp, ann)
    chaves = [o.key for o in tab.overlay_objects if o.source == "Segmentação"]
    assert f"segann:{ann.db_id}" not in chaves, "durante a edição só a máscara da janela aparece"
    assert len(chaves) == 1
    dlg.close()
    chaves = [o.key for o in tab.overlay_objects if o.source == "Segmentação"]
    assert chaves == [f"segann:{ann.db_id}"], "desistiu: volta a guardada, e só ela"


# ------------------------------------------------------------------ 0.68: plano na dinâmica
@pytest.fixture()
def dinamica_grossa(env, tmp_path):
    """Dinâmica com 8 cortes (a do fantoma comum tem 3, pouco para oblíquo)."""
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    from ipe.ui.viewer.dynamic import LAYOUTS, DynamicDialog
    from test_measure_tools import make_dynamic
    paths, db, repo = env
    uid = make_dynamic(tmp_path / "d", slices=8, one_series=False)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1200, 800)
    w.show()
    w.open_study(uid)
    tab = w.all_viewer_tabs()[-1]
    app.processEvents()
    dlg = DynamicDialog(tab)
    params = dlg.params()
    params["layout"] = next(i for i, (lab, _k) in enumerate(LAYOUTS)
                            if lab == "Mapa cinético, subtração e fase inicial + curva")
    assert tab.start_dynamic(dlg.dset, params)
    app.processEvents()
    yield app, w, tab
    w.close()


def test_todos_os_quadros_da_dinamica_mudam_de_plano(dinamica_grossa, monkeypatch):
    """Pedido dele: "no dinâmico, permita que eu possa mudar o eixo (sagital, axial, coronal e
    oblíquo)" — antes a fase não virava e o mapa não virava oblíquo."""
    from PySide6.QtWidgets import QMessageBox
    app, w, tab = dinamica_grossa
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: avisos.append(a[2]) or 0))
    for vp in tab.dyn.vps:
        chave = vp.dyn_key
        for nome in ("Coronal", "Sagital", "Oblíquo"):
            assert tab.reformatar(vp, nome), f"{chave} em {nome}: {avisos[-1:]}"
            assert vp.plano_nome() == nome, f"{chave}: pediu {nome}, mostra {vp.plano_nome()}"
            assert tab._dyn_do_quadro(vp) == (tab.dyn, chave), "continua sendo quadro da dinâmica"
        assert tab.girar_plano(vp, 15.0, 0.0), "o oblíquo da dinâmica gira"
        assert tab.reformatar(vp, "Original")
        assert tab.dyn.is_dyn(vp) and vp.dyn_key == chave, "voltou ao plano da aquisição"
    assert not avisos


def test_a_fase_reconstruida_e_a_mesma_imagem(dinamica_grossa):
    """Reconstruir não pode inventar: o mesmo ponto do paciente, o mesmo valor."""
    app, w, tab = dinamica_grossa
    vp = next(v for v in tab.dyn.vps if str(v.dyn_key).startswith("ph:"))
    i = int(vp.dyn_key[3:])
    assert tab.reformatar(vp, "Coronal")
    vol = tab.dyn.maps.volume_da_fase(i)
    centro = vol.voxel_to_patient(32, 32, 4)
    idx = vp.mpr_plane.index_for_point(centro)
    vp.go_to(idx)
    img = vp.mpr_plane.image(idx).pixels
    assert float(img.max()) == pytest.approx(float(vol.data[:, :, 32].max()), rel=1e-4)


def test_segmentar_no_quadro_reconstruido_da_dinamica(dinamica_grossa):
    app, w, tab = dinamica_grossa
    vp = next(v for v in tab.dyn.vps if v.dyn_key == "cin")
    assert tab.reformatar(vp, "Coronal")
    vol = tab.dyn.volumes_cad()[0]
    centro = vol.voxel_to_patient(32, 32, 4)
    vp.go_to(vp.mpr_plane.index_for_point(centro))
    pos, row, col, _n = vp.plane()
    rs, cs = vp._spacing()
    d = centro - pos
    u, v = float(d @ row / cs) + 0.5, float(d @ col / rs) + 0.5
    tab.segment_at(vp, u, v)
    jan = [d for d in getattr(tab, "_seg_dialogs", []) if d.isVisible()]
    assert jan and jan[-1].cad is not None and jan[-1].res.voxels > 0
    jan[-1].close()


# ------------------------------------------------------------------ 0.69.1: miniatura da captura
def test_a_captura_tem_miniatura(lesao):
    """Pedido dele: "é possível mostrar a miniatura do SC no banco de dados e na lista de séries
    no viewer?" — a série gravada pelo programa vinha sem miniatura."""
    app, w, tab, vp, jan = lesao
    uid = jan.salvar_captura()
    assert tab.repo.has_thumbnail(uid), "a captura nasce com miniatura"
    linha = next(s for s in tab.series if s.series_uid == uid)
    assert linha.thumbnail, "e aparece na tira do visualizador"


def test_captura_antiga_sem_miniatura_ganha_ao_abrir(lesao):
    """As capturas já salvas (0.67/0.68) ganham a miniatura quando o exame aparece."""
    from ipe.db.models import Series
    from ipe.importer.thumbnails import miniaturas_que_faltam
    app, w, tab, vp, jan = lesao
    uid = jan.salvar_captura()
    from sqlalchemy import select
    with tab.repo.db.session() as s:
        s.scalar(select(Series).where(Series.series_uid == uid)).thumbnail = None
    assert not tab.repo.has_thumbnail(uid)
    assert miniaturas_que_faltam(tab.repo, vp.study_uid) >= 1
    assert tab.repo.has_thumbnail(uid)


# ------------------------------------------------------------- mamilo marcado antes (0.74)
def test_mamilo_marcado_primeiro_da_a_distancia_sem_procurar_a_pele(lesao, monkeypatch):
    """Pedido dele (11/10/2026): marcar o mamilo à mão e depois pedir a distância, mais rápido,
    usando a referência dele. O botão tem de estar lá desde o começo, e com o ponto dele a pele
    (os ~15 s) não é procurada — nem nesta lesão, nem nas outras da mesma mama."""
    from ipe.imaging import mama_distancias as MD
    app, w, tab, vp, jan = lesao
    assert jan.b_mamilo.isVisibleTo(jan), "Marcar o mamilo tem de aparecer antes de medir"
    procurou = []
    monkeypatch.setattr(tab, "referencias_da_mama", lambda s: procurou.append(1))
    nz, ny, nx = tab.dyn.volumes_cad()[0].data.shape
    jan.b_mamilo.click()
    assert tab._mamilo_pendente is jan
    tab.segment_at(vp, 2.0, 2.0)                          # o clique no mamilo, na imagem
    assert jan.dist.get("mamilo_manual") and np.isfinite(jan.dist["mamilo"])
    assert jan.distancias_label.isVisibleTo(jan) and "marcado" in jan.distancias_label.text()
    assert "peitoral" not in jan.distancias_label.text()
    assert "pele" not in jan.distancias_label.text(), "com o ponto dele não há o texto do automático"
    marcado = jan.dist["mamilo_ponto"].copy()
    # pedir a distância depois de marcar também não procura a pele
    jan.refs = None
    jan.medir_distancias()
    assert not procurou and jan.dist["mamilo_ponto"] == pytest.approx(marcado)
    jan.save()
    jan.close()
    # outra lesão do mesmo exame: o mamilo marcado já vale, sem pedir de novo
    _vp, outra = _janela_da_lesao(tab)
    outra.medir_distancias()
    assert not procurou, "a segunda lesão não pode procurar a pele"
    assert outra.dist["mamilo_manual"] and outra.dist["mamilo_ponto"] == pytest.approx(marcado)
    outra.close()
    # reabrir o exame (sessão nova): o mamilo volta das lesões guardadas
    del tab.dyn.maps._mamilos_marcados
    m = tab.mamilos_marcados(tab.dyn, outra.vol)
    assert m.do_lado(marcado) == pytest.approx(marcado)


def test_mamilos_por_mama_no_volume_bilateral():
    from ipe.imaging import mama_distancias as MD
    afim = (np.array([-180.0, 0, 0]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 2.0]))
    m = MD.marcados_do_volume(afim, (10, 100, 360))
    assert m.bilateral and m.centro_x == pytest.approx(-0.5)
    m.marcar([-90.0, 10, 5])                               # mama direita do paciente (x < 0)
    assert m.do_lado([-60.0, 40, 5]) is not None
    assert m.do_lado([70.0, 40, 5]) is None, "o mamilo de uma mama não vale para a outra"
    m.marcar([95.0, 12, 5])
    assert m.do_lado([70.0, 40, 5])[0] == pytest.approx(95.0)
    uni = MD.marcados_do_volume(afim, (10, 100, 180))
    assert not uni.bilateral
    uni.marcar([-170.0, 0, 0])
    assert uni.do_lado([-10.0, 0, 0]) is not None, "unilateral: tudo é da mesma mama"


def test_a_mensagem_de_progresso_nao_fala_de_peitoral():
    import inspect
    from ipe.ui.viewer.onco import OncoMixin
    fonte = inspect.getsource(OncoMixin.referencias_da_mama)
    assert "peitoral" not in fonte and "parede torácica…" not in fonte
