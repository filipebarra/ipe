"""Rodada barata 2 (0.99.45): os itens que sobraram da lista barata do plano AW.

Zoom digitado; selo de sincronia entre referenciais diferentes; exportação de pacientes diferentes
num pacote só; série derivada com os parâmetros e a origem; aviso de cortes pulados na rolagem;
clonar ROI; tempo de duplicação.
"""
import numpy as np
import pydicom
import pytest
from PySide6.QtWidgets import QApplication

from ipe.imaging import lesions as L
from ipe.imaging import measure as M
from ipe.imaging.presets_janela import ler_zoom


@pytest.fixture()
def tc(env, sample_dir):
    from test_pedidos_29_10 import _sem_protocolos
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, _sem_protocolos(Settings(paths.settings_file)))
    w.resize(1300, 800)
    w.show()
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 1)
    app.processEvents()
    yield app, w, tab, repo, paths
    w.close()


def _com_anterior(tab, repo, app):
    prior = repo.find_study_uids(accession="ACC0901")[0]
    tab.add_study(prior)
    puid = repo.series_for_study(prior)[0].series_uid
    tab.set_layout(1, 2)
    app.processEvents()
    a, b = tab.viewports[0], tab.viewports[1]
    tab.load_series_into(b, puid)
    app.processEvents()
    return a, b


# --------------------------------------------------------------- zoom digitado
def test_ler_zoom():
    assert ler_zoom("150") == ("ajuste", 1.5)
    assert ler_zoom("150 %") == ("ajuste", 1.5)
    assert ler_zoom("2x") == ("ajuste", 2.0)
    assert ler_zoom("1:1") == ("pixel", 1.0)
    assert ler_zoom("2:1") == ("pixel", 2.0)
    assert ler_zoom("pixel") == ("pixel", 1.0)
    for ruim in ("", "abc", "0", "1:0", "999999"):
        assert ler_zoom(ruim) is None


def test_zoom_digitado_e_menu(tc):
    app, w, tab, repo, paths = tc
    vp = tab.viewports[0]
    vp.aplicar_zoom("ajuste", 2.0)
    assert vp.state.zoom == pytest.approx(2.0)
    assert "Zoom 200%" in vp._fov_text()
    vp.aplicar_zoom("pixel", 1.0)
    assert vp.state.zoom * vp.fit_scale() == pytest.approx(1.0)
    textos = [a.text() for a in vp.menu_do_zoom().actions()]
    assert "Ajustar à janela" in textos and "Digitar o zoom…" in textos and "200%" in textos


# --------------------------------------------------------------- selo de referencial
def test_selo_de_sincronia_entre_referenciais(tc):
    app, w, tab, repo, paths = tc
    a, b = _com_anterior(tab, repo, app)
    assert a.for_uid and b.for_uid and a.for_uid != b.for_uid
    assert not any(s.chave == "referencial" for s in a.selos())
    tab.hub.link_all([a, b], 1)
    sa = [s for s in a.selos() if s.chave == "referencial"]
    assert sa and not sa[0].grave and "registro" in sa[0].explicacao
    assert any(s.chave == "referencial" for s in b.selos())
    tab.hub.unlink_all()
    assert not any(s.chave == "referencial" for s in a.selos())


# --------------------------------------------------------------- clonar ROI
def test_clonar_roi_mesmo_referencial(tc):
    app, w, tab, repo, paths = tc
    tab.set_layout(1, 2)
    app.processEvents()
    a, b = tab.viewports[0], tab.viewports[1]
    tab.load_series_into(b, a.series_uid)
    app.processEvents()
    b.go_to(0)
    roi = a._new_annotation("ellipse", [(80.0, 90.0), (120.0, 130.0)])
    a._finish(roi)
    res = tab.clonar_roi(a, roi)
    assert [m for _w, m in res] == [""]
    assert b.index == a.index                         # foi ao mesmo corte
    cp = [x for x in b.frame_annotations() if x.kind == "ellipse"]
    assert len(cp) == 1 and cp[0].meta.get("clonada_de") is not None
    for (x0, y0), (x1, y1) in zip(roi.points, cp[0].points):
        assert x1 == pytest.approx(x0) and y1 == pytest.approx(y0)
    stats = M.labels(cp[0], b._img.pixels, b.measure_spacing(cp[0]))
    assert any("Média" in s or "média" in s for s in stats)


def test_clonar_roi_outro_referencial_pede_ligacao(tc):
    app, w, tab, repo, paths = tc
    a, b = _com_anterior(tab, repo, app)
    roi = a._new_annotation("rect", [(60.0, 60.0), (100.0, 100.0)])
    a._finish(roi)
    res = tab.clonar_roi(a, roi)
    assert "referencial" in res[0][1]
    assert not [x for x in b.annotations if x.kind == "rect"]
    tab.hub.link_all([a, b], 1)                       # ligados: vale o deslocamento do grupo
    res = tab.clonar_roi(a, roi)
    assert res[0][1] == ""
    assert [x for x in b.frame_annotations() if x.kind == "rect"]


def test_clonar_roi_fora_da_cobertura(tc):
    app, w, tab, repo, paths = tc
    a, b = _com_anterior(tab, repo, app)
    tab.hub.link_all([a, b], 1)
    m = tab.hub.members[b]
    m.geo = m.geo + np.array([0, 0, 900.0])           # o grupo diz que o outro está 90 cm acima
    roi = a._new_annotation("ellipse", [(60.0, 60.0), (100.0, 100.0)])
    a._finish(roi)
    assert "fora" in tab.clonar_roi(a, roi)[0][1]


def test_menu_tem_clonar(tc):
    app, w, tab, repo, paths = tc
    vp = tab.viewports[0]
    roi = vp._new_annotation("ellipse", [(80.0, 90.0), (120.0, 130.0)])
    vp._finish(roi)
    from PySide6.QtCore import QPointF
    c = vp.image_to_widget(QPointF(100.0, 90.0))
    textos = [x.text() for x in vp.build_context_menu(c).actions()]
    assert any(t.startswith("Clonar esta ROI") for t in textos)


# --------------------------------------------------------------- cortes pulados
def test_cortes_pulados_na_rolagem(tc):
    app, w, tab, repo, paths = tc
    vp = tab.viewports[0]
    vp.go_to(10)
    vp.grab()
    assert vp.cortes_pulados() == 0
    vp.step(1)
    vp.step(1)
    vp.step(1)                                        # três passos antes de pintar: dois nunca apareceram
    vp.grab()
    assert vp.cortes_pulados() == 2
    vp.step(1)
    vp.grab()
    vp._pulados = (0, 0.0)
    assert vp.cortes_pulados() == 0
    vp.go_to(40)                                      # ir a um corte não é rolar
    vp.grab()
    assert vp.cortes_pulados() == 0


# --------------------------------------------------------------- série derivada
def test_serie_derivada_leva_parametros_e_origem(tc):
    app, w, tab, repo, paths = tc
    vp = tab.viewports[0]
    tab._activate(vp)
    from ipe.imaging.derived import plane_datasets
    from ipe.imaging.volume import MPRPlane
    from ipe.imaging.volume import build_volume
    vol = build_volume(vp.frames, vp.cache)
    assert len(vol.origem_sops) == len(vp.frames)
    pl = MPRPlane(vol, 1)
    pl.set_slab(10.0, "mip")
    ds = next(plane_datasets(pl, indices=[pl.n // 2]))
    d = ds.DerivationDescription
    assert d.startswith("Ipe") and "coronal" in d.lower() and "10 mm" in d and "origem: serie 2" in d
    fontes = ds.SourceImageSequence
    assert len(fontes) == len(vp.frames)
    assert {f.ReferencedSOPInstanceUID for f in fontes} == {f.sop_uid for f in vp.frames}


def test_fontes_limitadas():
    from ipe.imaging.derived import sequencia_de_origem
    seq, n = sequencia_de_origem([(f"1.2.{i}", 0) for i in range(1000)], "1.2.840.10008.5.1.4.1.1.2", 300)
    assert n == 300 and len(seq) == 300 and seq[0].ReferencedSOPInstanceUID == "1.2.0"


def test_captura_secundaria_tem_origem(tc):
    app, w, tab, repo, paths = tc
    vp = tab.viewports[0]
    from ipe.imaging.derived import save_secondary_capture
    rgb = np.zeros((32, 32, 3), np.uint8)
    uid, sops = save_secondary_capture(rgb, vp.frames[0].path, repo.db, paths.storage, description="Teste",
                                       parametros="limiar 41%")
    path = repo.instances_for_series(uid)[0]["path"]
    ds = pydicom.dcmread(path)
    assert "limiar 41%" in ds.DerivationDescription
    assert ds.SourceImageSequence[0].ReferencedSOPInstanceUID == vp.frames[0].sop_uid


# --------------------------------------------------------------- exportação misturada
def test_exportar_pacientes_diferentes_num_pacote_pergunta(tc, monkeypatch):
    app, w, tab, repo, paths = tc
    from ipe.exporter.core import ExportItem
    from ipe.ui.export_dialog import ExportDialog
    a = repo.find_study_uids(accession="ACC1001")[0]
    outro = repo.find_study_uids(accession="ACC2001")[0]     # mesma paciente (Ana)
    de_outro = repo.find_study_uids(patient_id="FANT002")[0]
    d = ExportDialog(repo, w.settings, [("dois", [ExportItem(a), ExportItem(de_outro)])], w)
    d.r_dicom.setChecked(True)
    d.g_anon.setChecked(False)
    d.c_zip.setChecked(True)
    assert len(d.pacientes_misturados()) == 2
    perguntas = []
    monkeypatch.setattr(ExportDialog, "confirmar_mistura", lambda self, infos: perguntas.append(infos) or False)
    assert d._mistura_aceita() is False and perguntas
    d.g_anon.setChecked(True)                          # anonimizado não pergunta
    assert d.pacientes_misturados() == []
    d.g_anon.setChecked(False)
    d.c_zip.setChecked(False)
    d.c_viewer.setCurrentIndex(d.c_viewer.findData(""))  # pasta solta, sem visualizador
    assert d.pacientes_misturados() == []
    d2 = ExportDialog(repo, w.settings, [("um", [ExportItem(a), ExportItem(outro)])], w)
    d2.g_anon.setChecked(False)
    d2.c_zip.setChecked(True)
    assert d2.pacientes_misturados() == []           # mesmo paciente
    d.close()
    d2.close()


# --------------------------------------------------------------- tempo de duplicação
def test_tempo_de_duplicacao_contas():
    assert L.tempo_de_duplicacao(1.0, 2.0, 100) == pytest.approx(100)
    # diâmetro × 2^(1/3) dobra o volume
    assert L.tempo_de_duplicacao(10.0, 10.0 * 2 ** (1 / 3), 90, por_diametro=True) == pytest.approx(90)
    assert L.tempo_de_duplicacao(2.0, 1.0, 100) is None        # diminuiu
    assert L.tempo_de_duplicacao(2.0, 2.0, 100) is None        # estável
    assert L.tempo_de_duplicacao(1.0, 2.0, 0) is None          # sem intervalo


def test_duplicacoes_na_tabela():
    lesoes = [{"id": 1, "name": "n1", "kind": "target"}, {"id": 2, "name": "n2", "kind": "target"}]
    estudos = [("a", "20250101"), ("b", "20250411"), ("c", "20250720")]
    cells = {(1, "a"): L.Cell(value=8, long_mm=8.0, ml=0.2), (1, "b"): L.Cell(value=10, long_mm=10.0, ml=0.4),
             (1, "c"): L.Cell(value=9, long_mm=9.0),
             (2, "a"): L.Cell(value=5, long_mm=5.0), (2, "c"): L.Cell(value=6, long_mm=6.0)}
    d = L.duplicacoes(lesoes, estudos, cells)
    td, curto, expl = d[(1, "b")]
    assert td == pytest.approx(100) and curto == "TD 100 d" and "volume" in expl
    assert d[(1, "c")][0] is None and d[(1, "c")][1] == "TD não se aplica"   # diminuiu (pelo diâmetro)
    td2 = d[(2, "c")][0]
    assert td2 == pytest.approx(200 * np.log(2) / (3 * np.log(6 / 5)))      # pelo diâmetro, pulando o "b"
    assert "esfera" in d[(2, "c")][2]
    assert (1, "a") not in d
