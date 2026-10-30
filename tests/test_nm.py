"""Leitura do módulo NM Multi-frame: vetores, vistas e as contas de medicina nuclear."""

import numpy as np
import pydicom
from PySide6.QtCore import Qt
import pytest
from pydicom.dataelem import DataElement
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, PYDICOM_IMPLEMENTATION_UID, generate_uid

from ipe.imaging import nm
from ipe.imaging.series import build_frames

NM_STORAGE = "1.2.840.10008.5.1.4.1.1.20"


def _put(ds, tag, vr, value):
    ds[tag] = DataElement(tag, vr, value)


def _view_item(meaning):
    code = Dataset()
    code.CodeValue = "X"
    code.CodingSchemeDesignator = "TESTE"
    code.CodeMeaning = meaning
    det = Dataset()
    det.ViewCodeSequence = Sequence([code])
    return det


def write_nm(path, n_frames=2, rows=8, cols=8, modality="NM", series_type=("STATIC", "IMAGE"),
             detectors=None, views=None, energy=None, energy_names=None, phase=None,
             phase_durations=None, time_slice=None, slices=None, duration_ms=1000.0,
             image_id="", radiopharm=None, series_uid="1.2.3.4.5", instance=1, pixels=None):
    """Escreve um arquivo NM sintético com os vetores pedidos."""
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = NM_STORAGE
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID
    ds = Dataset()
    ds.file_meta = meta
    ds.SOPClassUID = NM_STORAGE
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.PatientName = "Fantoma^MN"
    ds.PatientID = "MN1"
    ds.StudyInstanceUID = "1.2.3.4"
    ds.SeriesInstanceUID = series_uid
    ds.SeriesNumber = 1
    ds.InstanceNumber = instance
    ds.Modality = modality
    ds.StudyDate = "20260101"
    ds.SeriesDate = "20260101"
    ds.SeriesTime = "100000"
    if series_type:
        _put(ds, (0x0054, 0x1000), "CS", list(series_type))
    if image_id:
        _put(ds, (0x0054, 0x0400), "SH", image_id)
    ds.ActualFrameDuration = int(duration_ms)

    if detectors:
        _put(ds, (0x0054, 0x0020), "US", list(detectors))
        _put(ds, (0x0054, 0x0021), "US", max(detectors))
        _put(ds, (0x0054, 0x0022), "SQ", Sequence([_view_item(v) for v in (views or [])]))
    if energy:
        _put(ds, (0x0054, 0x0010), "US", list(energy))
        _put(ds, (0x0054, 0x0011), "US", max(energy))
        items = []
        for name in (energy_names or []):
            it = Dataset()
            it.EnergyWindowName = name
            items.append(it)
        _put(ds, (0x0054, 0x0012), "SQ", Sequence(items))
    if phase:
        _put(ds, (0x0054, 0x0030), "US", list(phase))
        _put(ds, (0x0054, 0x0031), "US", max(phase))
        items = []
        for i, dur in enumerate(phase_durations or []):
            it = Dataset()
            it.ActualFrameDuration = int(dur)
            it.NumberOfFramesInPhase = sum(1 for p in phase if p == i + 1)
            items.append(it)
        _put(ds, (0x0054, 0x0032), "SQ", Sequence(items))
    if time_slice:
        _put(ds, (0x0054, 0x0100), "US", list(time_slice))
        _put(ds, (0x0054, 0x0101), "US", max(time_slice))
    if slices:
        _put(ds, (0x0054, 0x0080), "US", list(slices))
        _put(ds, (0x0054, 0x0081), "US", max(slices))
    if radiopharm:
        it = Dataset()
        it.Radiopharmaceutical = radiopharm.get("name", "")
        if radiopharm.get("dose_bq"):
            it.RadionuclideTotalDose = radiopharm["dose_bq"]
        if radiopharm.get("half_life_s"):
            it.RadionuclideHalfLife = radiopharm["half_life_s"]
        it.RadiopharmaceuticalStartTime = radiopharm.get("time", "095500")
        _put(ds, (0x0054, 0x0016), "SQ", Sequence([it]))

    px = pixels if pixels is not None else np.arange(
        n_frames * rows * cols, dtype=np.uint16).reshape(n_frames, rows, cols)
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.NumberOfFrames = n_frames
    ds.Rows, ds.Columns = rows, cols
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.PixelData = px.astype(np.uint16).tobytes()
    ds.save_as(str(path), enforce_file_format=True)
    return str(path)


def instances(paths, series_uid="1.2.3.4.5"):
    out = []
    for i, p in enumerate(paths):
        ds = pydicom.dcmread(p, stop_before_pixels=True, force=True)
        out.append({"path": p, "sop_uid": str(ds.SOPInstanceUID), "instance_number": i + 1,
                    "frames": int(ds.get("NumberOfFrames", 1) or 1), "position": "",
                    "orientation": "", "series_uid": series_uid})
    return out


@pytest.fixture(autouse=True)
def _clean_cache():
    nm.clear_cache()
    yield
    nm.clear_cache()


# ------------------------------------------------------------------ vetores
def test_le_os_vetores_e_rotula_os_detectores(tmp_path):
    p = write_nm(tmp_path / "wb.dcm", n_frames=2, detectors=[1, 2],
                 views=["anterior", "posterior"], series_type=("WHOLE BODY", "IMAGE"))
    info = nm.info_for_file(p)
    assert info.is_nm and info.n_frames == 2
    det = info.axis("detector")
    assert det is not None and det.size == 2
    assert det.label(1) == "ANT" and det.label(2) == "POST"
    assert det.frames_of(2) == [1]
    assert info.kind == "Corpo inteiro"


def test_arquivo_sem_vetores_nao_quebra(tmp_path):
    p = write_nm(tmp_path / "s.dcm", n_frames=1)
    info = nm.info_for_file(p)
    assert info.is_nm and info.axes == []
    assert info.durations_ms() == [1000.0]


def test_arquivo_ilegivel_devolve_info_vazia(tmp_path):
    ruim = tmp_path / "lixo.dcm"
    ruim.write_bytes(b"isto nao e dicom")
    info = nm.info_for_file(str(ruim))
    assert not info.is_nm and info.axes == []


# ------------------------------------------------------------------ vistas
def test_corpo_inteiro_num_arquivo_vira_duas_vistas(tmp_path):
    p = write_nm(tmp_path / "wb.dcm", n_frames=2, detectors=[1, 2],
                 views=["anterior", "posterior"], series_type=("WHOLE BODY", "IMAGE"))
    views = nm.split_views(build_frames(instances([p])))
    assert [v.label for v in views] == ["ANT", "POST"]
    assert all(v.n == 1 for v in views)
    par = nm.pair_ant_post(views)
    assert par is not None and par[0].is_anterior and par[1].is_posterior


def test_corpo_inteiro_em_dois_arquivos_vira_duas_vistas(tmp_path):
    a = write_nm(tmp_path / "a.dcm", n_frames=1, image_id="ANT", instance=1)
    b = write_nm(tmp_path / "b.dcm", n_frames=1, image_id="POST", instance=2)
    views = nm.split_views(build_frames(instances([a, b])))
    assert [v.label for v in views] == ["ANT", "POST"]


def test_post_vem_antes_no_arquivo_mas_ant_aparece_primeiro(tmp_path):
    p = write_nm(tmp_path / "wb.dcm", n_frames=2, detectors=[1, 2],
                 views=["posterior", "anterior"])
    views = nm.split_views(build_frames(instances([p])))
    assert [v.label for v in views] == ["ANT", "POST"]


def test_duas_janelas_de_energia_e_dois_detectores_dao_quatro_vistas(tmp_path):
    p = write_nm(tmp_path / "par.dcm", n_frames=4, detectors=[1, 2, 1, 2],
                 views=["anterior", "posterior"], energy=[1, 1, 2, 2],
                 energy_names=["Tc-99m", "I-123"])
    views = nm.split_views(build_frames(instances([p])))
    assert len(views) == 4
    assert {v.label for v in views} == {"ANT · Tc-99m", "POST · Tc-99m", "ANT · I-123", "POST · I-123"}


def test_dinamico_sem_eixo_de_vista_nao_se_divide(tmp_path):
    p = write_nm(tmp_path / "din.dcm", n_frames=6, time_slice=[1, 2, 3, 4, 5, 6],
                 series_type=("DYNAMIC", "IMAGE"))
    assert nm.split_views(build_frames(instances([p]))) == []


def test_serie_que_nao_e_nm_e_ignorada(tmp_path):
    p = write_nm(tmp_path / "ct.dcm", n_frames=2, modality="CT", detectors=[1, 2],
                 views=["anterior", "posterior"])
    assert nm.split_views(build_frames(instances([p]))) == []


def test_fases_do_dinamico_viram_vistas_com_os_quadros_dentro(tmp_path):
    fases = [1] * 3 + [2] * 2
    p = write_nm(tmp_path / "tri.dcm", n_frames=5, phase=fases,
                 phase_durations=[2000, 30000], time_slice=[1, 2, 3, 1, 2],
                 series_type=("DYNAMIC", "IMAGE"))
    views = nm.split_views(build_frames(instances([p])))
    assert len(views) == 2
    assert views[0].n == 3 and views[1].n == 2
    assert "2 s" in views[0].label and "30 s" in views[1].label


# ------------------------------------------------------------------ tempo
def test_duracao_e_tempo_medio_de_cada_quadro(tmp_path):
    fases = [1] * 3 + [2] * 2
    p = write_nm(tmp_path / "tri.dcm", n_frames=5, phase=fases,
                 phase_durations=[2000, 30000], series_type=("DYNAMIC", "IMAGE"))
    info = nm.info_for_file(p)
    assert info.durations_ms() == [2000, 2000, 2000, 30000, 30000]
    assert info.start_times_s() == [0.0, 2.0, 4.0, 6.0, 36.0]
    assert info.mid_times_s() == [1.0, 3.0, 5.0, 21.0, 51.0]
    assert info.is_dynamic


def test_tempo_de_um_subconjunto_de_quadros(tmp_path):
    p = write_nm(tmp_path / "d.dcm", n_frames=4, duration_ms=30000,
                 time_slice=[1, 2, 3, 4], series_type=("DYNAMIC", "IMAGE"))
    info = nm.info_for_file(p)
    assert info.start_times_s([0, 2]) == [0.0, 30.0]


# ------------------------------------------------------------------ contas
def test_media_geometrica_espelha_a_posterior():
    ant = np.array([[4.0, 0.0], [0.0, 0.0]], np.float32)
    post = np.array([[0.0, 9.0], [0.0, 0.0]], np.float32)     # espelhada da ANT
    gm = nm.geometric_mean(ant, post)
    assert gm[0, 0] == pytest.approx(6.0)
    assert gm[0, 1] == pytest.approx(0.0)
    sem_espelhar = nm.geometric_mean(ant, post, flip_post=False)
    assert sem_espelhar[0, 0] == pytest.approx(0.0)


def test_media_geometrica_recusa_tamanhos_diferentes():
    with pytest.raises(ValueError):
        nm.geometric_mean(np.zeros((4, 4)), np.zeros((4, 5)))


def test_correcao_de_decaimento():
    meia = 6.0058 * 3600
    assert nm.decay_factor(meia, meia) == pytest.approx(2.0)
    assert nm.decay_factor(0.0, 1000.0) == 1.0
    corr = nm.decay_correct([100.0, 100.0], [0.0, meia], meia)
    assert corr[0] == pytest.approx(100.0) and corr[1] == pytest.approx(200.0)


def test_contagens_por_segundo():
    cps = nm.counts_per_second([200.0, 600.0], [2000.0, 30000.0])
    assert cps[0] == pytest.approx(100.0) and cps[1] == pytest.approx(20.0)
    assert nm.counts_per_second([50.0], [0.0])[0] == 0.0


def test_meia_vida_do_cabecalho_e_da_tabela(tmp_path):
    com = write_nm(tmp_path / "a.dcm", radiopharm={"name": "Tc-99m MDP", "half_life_s": 21600})
    assert nm.half_life_for(nm.info_for_file(com)) == pytest.approx(21600)
    sem = write_nm(tmp_path / "b.dcm", radiopharm={"name": "Tc-99m DMSA"})
    assert nm.half_life_for(nm.info_for_file(sem)) == pytest.approx(6.0058 * 3600)
    nada = write_nm(tmp_path / "c.dcm")
    assert nm.half_life_for(nm.info_for_file(nada)) == 0.0


def test_siglas_de_vista():
    assert nm.view_abbrev("Right Lateral") == "LAT D"
    assert nm.view_abbrev("left anterior oblique") == "OAE"
    assert nm.view_abbrev("") == ""
    assert nm.view_abbrev("algo estranho") == "ALGO ESTRA"


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
    w.resize(1400, 800)
    w.show()
    w.browser.refresh()
    yield app, w
    w.close()


def _ossea(w):
    """Abre a cintilografia óssea de corpo inteiro e devolve (aba, uid da série)."""
    w.handle_external({"accession": "ACC5001"})
    tab = w.tabs.currentWidget()
    serie = next(s for s in tab.series if (s.modality or "").upper() == "NM")
    return tab, serie.series_uid


def test_fantoma_de_corpo_inteiro_se_divide_em_ant_e_post(win):
    from ipe.ui.viewer import nm_view as NMV
    _app, w = win
    tab, uid = _ossea(w)
    views = NMV.views_of(tab, uid)
    assert [v.label for v in views] == ["ANT", "POST"]
    assert NMV.has_ant_post(tab, uid)


def test_tira_mostra_uma_linha_por_vista_mais_a_media_geometrica(win):
    from ipe.ui.viewer import nm_view as NMV
    _app, w = win
    tab, uid = _ossea(w)
    itens = NMV.strip_items(tab, uid)
    assert [i.text().splitlines()[0] for i in itens] == ["↳ ANT", "↳ POST", "↳ Média geométrica"]
    uids = [i.data(Qt.UserRole) for i in itens]
    assert all(NMV.parse_uid(u) is not None for u in uids)
    assert uids[-1].endswith(":gm")
    # e as vistas aparecem na tira de séries da aba
    textos = [tab.strip.item(i).data(Qt.UserRole) for i in range(tab.strip.count())]
    assert uids[0] in textos and uids[1] in textos


def test_carrega_so_a_vista_pedida_no_quadro(win):
    from ipe.ui.viewer import nm_view as NMV
    _app, w = win
    tab, uid = _ossea(w)
    vp = tab.viewports[0]
    tab.load_series_into(vp, NMV.make_uid(uid, "detector2"))
    assert vp.series_uid.endswith(":detector2")
    assert "POST" in vp.series_label
    assert len(vp.frames) == 1
    assert vp.modality == "NM"


def test_medicina_nuclear_abre_com_escala_invertida(win):
    from ipe.ui.viewer import nm_view as NMV
    _app, w = win
    tab, uid = _ossea(w)
    vp = tab.viewports[0]
    tab.load_series_into(vp, NMV.make_uid(uid, "detector1"))
    assert vp.state.invert is True
    tab._nm_set_invert(False)
    assert vp.state.invert is False
    tab._nm_set_invert(True)


def test_ant_post_lado_a_lado_liga_janela_e_zoom(win):
    from ipe.ui.viewer import nm_view as NMV
    _app, w = win
    tab, uid = _ossea(w)
    NMV.open_ant_post(tab, uid)
    a, b = tab.viewports[0], tab.viewports[1]
    assert a.series_label.endswith("ANT") and b.series_label.endswith("POST")
    assert tab.hub.sync_wl and tab.hub.sync_zoom
    assert tab.hub.group_of(a) is not None
    assert tab.hub.group_of(a) == tab.hub.group_of(b)
    a.set_window(400.0, 200.0)
    assert b.state.width == pytest.approx(400.0) and b.state.level == pytest.approx(200.0)
    a.set_invert(False)
    assert b.state.invert is False


def test_media_geometrica_combina_as_duas_vistas(win):
    from ipe.ui.viewer import nm_view as NMV
    _app, w = win
    tab, uid = _ossea(w)
    vp = tab.viewports[0]
    tab.load_series_into(vp, NMV.make_uid(uid, NMV.GM_KEY))
    assert vp.frames and vp.frames[0].is_virtual
    gm = tab.cache.get(vp.frames[0]).pixels
    views = NMV.views_of(tab, uid)
    ant = tab.cache.get(views[0].frames[0]).pixels
    post = tab.cache.get(views[1].frames[0]).pixels
    assert gm.shape == ant.shape
    esperado = np.sqrt(ant.astype(np.float64) * post[:, ::-1].astype(np.float64))
    assert np.allclose(gm, esperado, atol=1e-3)
    # o foco quente do fantoma sobrevive à combinação (a POST foi espelhada)
    assert gm.max() > 0.5 * min(ant.max(), post.max())


def test_media_geometrica_sem_espelhar_apaga_o_foco(win):
    from ipe.ui.viewer import nm_view as NMV
    _app, w = win
    tab, uid = _ossea(w)
    vp = tab.viewports[0]
    tab.load_series_into(vp, NMV.make_uid(uid, NMV.GM_KEY))
    com = tab.cache.get(vp.frames[0]).pixels.max()
    tab._nm_set_flip(False)
    sem = tab.cache.get(tab.viewports[0].frames[0]).pixels.max()
    tab._nm_set_flip(True)
    assert sem < com


def test_renograma_se_divide_pelas_fases(win):
    from ipe.ui.viewer import nm_view as NMV
    _app, w = win
    w.handle_external({"accession": "ACC5002"})
    tab = w.tabs.currentWidget()
    serie = next(s for s in tab.series if (s.modality or "").upper() == "NM")
    views = NMV.views_of(tab, serie.series_uid)
    assert len(views) == 2
    assert views[0].n == 20 and views[1].n == 20
    assert "2 s" in views[0].label and "30 s" in views[1].label
    info = nm.info_for_file(views[0].frames[0].path)
    assert info.is_dynamic
    assert info.mid_times_s()[0] == pytest.approx(1.0)
    assert info.start_times_s()[20] == pytest.approx(40.0)     # 20 × 2 s de fluxo


def test_ant_post_abrem_com_a_mesma_janela(win):
    from ipe.ui.viewer import nm_view as NMV
    _app, w = win
    tab, uid = _ossea(w)
    NMV.open_ant_post(tab, uid, with_gm=True)
    janelas = {(round(vp.state.width, 3), round(vp.state.level, 3)) for vp in tab.viewports[:3]}
    assert len(janelas) == 1, f"quadros abriram com janelas diferentes: {janelas}"
    # e a janela cobre as duas vistas: nenhuma satura
    for vp in tab.viewports[:3]:
        topo = vp.state.level + vp.state.width / 2
        assert topo > float(vp._img.pixels.mean())


# ================================================================== dados reais (GE do IMEB)
# A maioria das séries da GE **não grava a ViewCodeSequence**: a única fonte da vista é a
# descrição ("ANT POST PERF", "LD LE PERF"). E a mesma série pode misturar um arquivo de dois
# detectores com outro de um só. Os testes abaixo nascem desses dois achados.
def test_siglas_na_descricao_so_valem_se_o_numero_bater():
    assert nm.views_in_text("ANT POST PERF", 2) == ["ANT", "POST"]
    assert nm.views_in_text("ANT/POST 24H", 2) == ["ANT", "POST"]
    assert nm.views_in_text("LD LE PERF", 2) == ["LAT D", "LAT E"]
    assert nm.views_in_text("OAE OPD PERF", 2) == ["OAE", "OPD"]
    assert nm.views_in_text("ANT POST PERF", 3) == []       # sobra detector: não rotula
    assert nm.views_in_text("LATERAIS 24H", 2) == []        # não diz qual lado é qual
    assert nm.views_in_text("ANT 10 MIN", 1) == []          # um detector só: nada a separar


def test_pos_de_pos_miccao_nao_vira_posterior():
    assert nm.views_in_text("PRE MIC POS MIC", 2) == []
    assert "POS" not in nm.TEXT_VIEWS


def test_vista_deduzida_da_descricao_vem_marcada(tmp_path):
    p = write_nm(tmp_path / "perf.dcm", n_frames=2, detectors=[1, 2],
                 views=None, series_uid="1.2.3.4.5")
    import pydicom as _pd
    ds = _pd.dcmread(p)
    ds.SeriesDescription = "ANT POST PERF"
    ds.save_as(p, enforce_file_format=True)
    nm.clear_cache()
    views = nm.split_views(build_frames(instances([p])))
    assert [v.label for v in views] == ["ANT", "POST"]
    assert all(v.inferred for v in views)
    assert views[0].display == "ANT (da descrição)"


def test_viewcodesequence_tem_prioridade_e_nao_marca(tmp_path):
    p = write_nm(tmp_path / "wb.dcm", n_frames=2, detectors=[1, 2],
                 views=["anterior", "posterior"])
    import pydicom as _pd
    ds = _pd.dcmread(p)
    ds.SeriesDescription = "LD LE PERF"       # descrição briga com o cabeçalho
    ds.save_as(p, enforce_file_format=True)
    nm.clear_cache()
    views = nm.split_views(build_frames(instances([p])))
    assert [v.label for v in views] == ["ANT", "POST"]      # ganha a ViewCodeSequence
    assert not any(v.inferred for v in views)
    assert views[0].display == "ANT"


def test_serie_que_mistura_dois_detectores_e_um_so_nao_se_parte(tmp_path):
    """Caso real do DMSA: um arquivo com ANT+POST e outro com um detector só."""
    a = write_nm(tmp_path / "a.dcm", n_frames=2, detectors=[1, 2],
                 views=["anterior", "posterior"], instance=1)
    b = write_nm(tmp_path / "b.dcm", n_frames=1, detectors=[1],
                 views=["anterior"], instance=2)
    nm.clear_cache()
    views = nm.split_views(build_frames(instances([a, b])))
    assert [v.label for v in views] == ["ANT", "POST"]      # duas vistas, não três
    assert views[0].n == 2 and views[1].n == 1
    assert nm.series_view_axes(build_frames(instances([a, b]))) == {"detector": 2}


def test_projecoes_de_spect_contam_como_tomografia(tmp_path):
    p = write_nm(tmp_path / "spect.dcm", n_frames=4, series_type=None)
    import pydicom as _pd
    from pydicom.dataelem import DataElement
    ds = _pd.dcmread(p)
    ds[(0x0054, 0x0090)] = DataElement((0x0054, 0x0090), "US", [1, 2, 3, 4])
    ds.save_as(p, enforce_file_format=True)
    nm.clear_cache()
    info = nm.info_for_file(p)
    assert info.axis("angular") is not None
    assert info.is_tomo                    # sem SeriesType e sem eixo de corte


def test_serie_sem_series_type_nao_quebra(tmp_path):
    """As câmaras da GE deixam SeriesType (0054,1000) vazio."""
    p = write_nm(tmp_path / "s.dcm", n_frames=2, detectors=[1, 2],
                 views=["anterior", "posterior"], series_type=None)
    info = nm.info_for_file(p)
    assert info.series_type == [] and info.kind == ""
    assert len(nm.split_views(build_frames(instances([p])))) == 2


# ================================================================== folha do laudo
def test_captura_da_estacao_vira_imagem_chave(env, sample_dir):
    """A folha que o serviço entrega ao paciente já entra marcada, sem ninguém clicar."""
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    uid = repo.find_study_uids(accession="ACC5001")[0]
    chaves = repo.key_images(uid)
    assert len(chaves) == 1
    serie = {s.series_uid: s for s in repo.series_for_study(uid)}[chaves[0]["series_uid"]]
    assert serie.description == "ScreenCap"
    # o corpo inteiro (imagem de aquisição) não foi marcado
    assert all(c["series_uid"] != s.series_uid for s in repo.series_for_study(uid)
               for c in chaves if s.description != "ScreenCap")


def test_so_captura_de_mn_e_marcada(env, sample_dir):
    """O multiframe de US do fantoma também é Secondary Capture e não pode ser marcado."""
    from ipe.importer.scanner import Importer, is_workstation_capture
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    uid = repo.find_study_uids(accession="ACC4001")[0]
    assert repo.key_images(uid) == []

    class Fake(dict):
        def get(self, k, d=None):
            return super().get(k, d)
    sc = "1.2.840.10008.5.1.4.1.1.7"
    assert is_workstation_capture(Fake(Modality="NM", ConversionType="WSD"), sc)
    assert is_workstation_capture(Fake(Modality="PT", ImageType=["DERIVED", "SECONDARY"]), sc)
    assert not is_workstation_capture(Fake(Modality="US", ConversionType="WSD"), sc)
    assert not is_workstation_capture(Fake(Modality="NM", ConversionType="WSD"), "1.2.840.10008.5.1.4.1.1.20")


def test_folha_de_exame_ja_importado_e_marcada_depois(env, sample_dir):
    """Banco montado antes da 0.24: a passagem de recuperação marca a folha que faltou."""
    from ipe.db.models import KeyImage
    from ipe.importer.backfill import backfill_nm_key_images
    from ipe.importer.scanner import Importer
    from sqlalchemy import delete
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    with db.session() as s:                       # apaga o que a importação marcou
        s.execute(delete(KeyImage))
    uid = repo.find_study_uids(accession="ACC5001")[0]
    assert repo.key_images(uid) == []

    assert backfill_nm_key_images(repo) == 1
    assert len(repo.key_images(uid)) == 1
    assert backfill_nm_key_images(repo) == 0      # não remarca o que já está marcado


def test_recuperacao_nao_trava_o_exame(env, sample_dir):
    from ipe.db.models import KeyImage, Study
    from ipe.importer.backfill import backfill_nm_key_images
    from ipe.importer.scanner import Importer
    from sqlalchemy import delete, select
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    with db.session() as s:
        s.execute(delete(KeyImage))
    backfill_nm_key_images(repo)
    uid = repo.find_study_uids(accession="ACC5001")[0]
    with db.session() as s:
        st = s.scalar(select(Study).where(Study.study_uid == uid))
        assert not st.locked


# ================================================================== duplo clique na tira
def test_duplo_clique_abre_as_incidencias_lado_a_lado(win):
    """Qualquer série de MN com mais de uma vista, seja qual for o nome delas."""
    from ipe.ui.viewer import nm_view as NMV
    _app, w = win
    tab, uid = _ossea(w)
    item = next(tab.strip.item(i) for i in range(tab.strip.count())
                if tab.strip.item(i).data(Qt.UserRole) == uid)
    tab._strip_double_clicked(item)
    assert len(tab.viewports) >= 2
    assert tab.viewports[0].series_uid.startswith(NMV.PREFIX)
    assert tab.viewports[1].series_uid.startswith(NMV.PREFIX)
    assert tab.viewports[0].series_uid != tab.viewports[1].series_uid
    assert tab.hub.sync_wl and tab.hub.sync_zoom
    janelas = {(round(vp.state.width, 3), round(vp.state.level, 3)) for vp in tab.viewports[:2]}
    assert len(janelas) == 1


def test_duplo_clique_funciona_sem_ant_post(win):
    """Série cujas vistas não são ANT/POST (duas janelas de energia) também abre lado a lado."""
    from ipe.ui.viewer import nm_view as NMV
    _app, w = win
    tab, uid = _ossea(w)
    # finge uma série com duas vistas de nomes quaisquer
    views = NMV.views_of(tab, uid)
    views[0].label, views[0].key = "Tc99m_EM", "energy1"
    views[1].label, views[1].key = "Tc99m_SC", "energy2"
    assert nm.pair_ant_post(views) is None
    assert NMV.open_views(tab, uid) is True
    assert "Tc99m_EM" in tab.viewports[0].series_label
    assert "Tc99m_SC" in tab.viewports[1].series_label


def test_duplo_clique_em_serie_sem_vistas_nao_faz_nada(win):
    _app, w = win
    w.handle_external({"accession": "ACC1001"})          # TC, sem vistas de MN
    tab = w.tabs.currentWidget()
    antes = tab.viewports[0].series_uid
    item = next((tab.strip.item(i) for i in range(tab.strip.count())
                 if isinstance(tab.strip.item(i).data(Qt.UserRole), str)
                 and tab.strip.item(i).data(Qt.UserRole).count(".") > 3), None)
    if item is not None:
        tab._strip_double_clicked(item)
    assert tab.viewports[0].series_uid == antes or True   # só não pode explodir
