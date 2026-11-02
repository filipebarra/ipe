"""Switch WL, janela digitada e presets por modalidade com "guardar a janela atual" (0.99.22)."""
from dataclasses import replace

import pydicom
import pytest
from PySide6.QtWidgets import QApplication, QInputDialog

from ipe.imaging import presets_janela as PJ
from ipe.imaging.series import janelas_do_arquivo


def test_janelas_do_arquivo_com_nomes():
    ds = pydicom.Dataset()
    ds.WindowWidth = [4000, 3000, 5000]
    ds.WindowCenter = [2000, 1800, 2200]
    ds.WindowCenterWidthExplanation = ["NORMAL", "HARDER", "SOFTER"]
    assert janelas_do_arquivo(ds) == (("NORMAL", 4000.0, 2000.0), ("HARDER", 3000.0, 1800.0),
                                      ("SOFTER", 5000.0, 2200.0))


def test_janela_sem_nome_e_voi_lut():
    ds = pydicom.Dataset()
    ds.WindowWidth, ds.WindowCenter = 400, 40
    lut = pydicom.Dataset()
    lut.LUTDescriptor = [4096, 0, 16]
    lut.LUTExplanation = "AUTO"
    ds.VOILUTSequence = [lut]
    js = janelas_do_arquivo(ds)
    assert js[0] == ("Janela 1", 400.0, 40.0)
    assert js[1] == ("AUTO (VOI LUT)", 4096.0, 2048.0)


def test_janela_do_quadro_vence_a_do_arquivo():
    ds = pydicom.Dataset()
    ds.WindowWidth, ds.WindowCenter = 400, 40
    voi = pydicom.Dataset()
    voi.WindowWidth, voi.WindowCenter = [1000, 800], [500, 400]
    fg = pydicom.Dataset()
    fg.FrameVOILUTSequence = [voi]
    ds.PerFrameFunctionalGroupsSequence = [fg]
    assert [j[1] for j in janelas_do_arquivo(ds, 0)] == [1000.0, 800.0]


def test_ler_wl():
    assert PJ.ler_wl("400 40") == (400.0, 40.0)
    assert PJ.ler_wl("W 1500 / L -600") == (1500.0, -600.0)
    assert PJ.ler_wl("80,5; 40") == (80.5, 40.0)
    assert PJ.ler_wl("400") is None and PJ.ler_wl("0 40") is None


def test_presets_por_modalidade(tmp_path):
    from ipe.core.config import Settings
    s = Settings(tmp_path / "s.json")
    geral = PJ.presets(s, "MR")
    assert "1" in geral and geral["1"][0] == "Pulmão"        # sem lista própria: a geral
    PJ.guardar(s, "MR", PJ.tecla_livre(s, "MR"), "T2 cérebro", 900, 450)
    assert PJ.presets(s, "MR") == {"1": ["T2 cérebro", 900.0, 450.0]}
    assert PJ.presets(s, "CT")["1"][0] == "Pulmão"
    PJ.guardar(s, "CT", "7", "Partes moles", 350, 40)        # CT sem lista própria: grava na geral
    assert s.get("viewer.wl_presets")["7"][0] == "Partes moles"


# ------------------------------------------------------------------ na tela
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
    w.resize(1200, 800)
    w.show()
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 1)
    app.processEvents()
    yield app, w, tab, tab.viewports[0]
    w.close()


def _com_janelas(vp, mod="MG"):
    js = (("NORMAL", 4000.0, 2000.0), ("HARDER", 3000.0, 1800.0))
    vp._img = replace(vp._img, janelas=js, header={**vp._img.header, "Modality": mod})
    return js


def test_switch_wl_percorre_e_mostra_o_nome(tc):
    app, w, tab, vp = tc
    _com_janelas(vp)
    msgs = []
    tab.status_message.connect(msgs.append)
    tab.switch_wl()
    assert (vp.state.width, vp.state.level) == (4000.0, 2000.0) and vp.nome_da_janela() == "NORMAL"
    assert any("NORMAL" in t for c in vp._text_lines().values() for t, _h in c)
    tab.switch_wl()
    assert vp.nome_da_janela() == "HARDER" and "2/2" in msgs[-1]
    tab.switch_wl()
    assert vp.nome_da_janela() == "NORMAL"                     # em ciclo
    vp.set_window(500, 100)
    assert vp.nome_da_janela() == ""                           # arrastou: o nome sai


def test_switch_wl_sem_janelas_avisa(tc):
    app, w, tab, vp = tc
    vp._img = replace(vp._img, janelas=())
    msgs = []
    tab.status_message.connect(msgs.append)
    tab.switch_wl()
    assert "não traz" in msgs[-1]


def test_switch_wl_na_mamografia_troca_os_quadros_juntos(tc):
    app, w, tab, vp = tc
    tab.set_layout(1, 2)
    app.processEvents()
    a, b = tab.viewports[0], tab.viewports[1]
    if not b.frames:
        b.set_series(a.series_uid, list(a.frames), a.series_label, a.study_info)
    _com_janelas(a)
    _com_janelas(b)
    tab._activate(a)
    tab.switch_wl()
    tab.switch_wl()
    assert b.nome_da_janela() == "HARDER"


def test_digitar_e_guardar_a_janela(tc, monkeypatch):
    app, w, tab, vp = tc
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("1500 -600", True)))
    vp.digitar_janela()
    assert (vp.state.width, vp.state.level) == (1500.0, -600.0)
    _com_janelas(vp, "MR")
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Meu T1", True)))
    assert vp.guardar_janela_atual()
    assert vp.presets_da_janela() == {"1": ["Meu T1", 1500.0, -600.0]}
    vp.set_window(10, 10)
    vp.apply_preset("1")
    assert (vp.state.width, vp.state.level) == (1500.0, -600.0)
    vp.apply_preset("1", geral=True)                            # protocolo de exibição: a geral
    assert vp.state.width == 1500 and vp.state.level == -600


def test_menu_da_janela_tem_o_arquivo_e_as_acoes(tc):
    app, w, tab, vp = tc
    from PySide6.QtWidgets import QMenu
    _com_janelas(vp)
    m = QMenu()
    vp._add_preset_actions(m)
    textos = [a.text() for a in m.actions()]
    assert any("NORMAL" in t for t in textos) and "Digitar a janela…" in textos
    assert "Guardar a janela atual como preset…" in textos


def test_preferencias_editam_a_lista_da_modalidade(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox, QTableWidgetItem
    from ipe.core.config import Settings
    from ipe.ui import preferences as P
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: pytest.fail(f"aviso: {a[1:3]}"))
    s = Settings(tmp_path / "s.json")
    d = P.PreferencesDialog(s)
    d.c_preset_lista.setCurrentIndex(d.c_preset_lista.findData("MR"))
    for col, v in ((1, "T2"), (2, "900"), (3, "450")):
        d.t_presets.setItem(0, col, QTableWidgetItem(v))
    d.c_preset_lista.setCurrentIndex(0)
    assert d.t_presets.item(0, 1).text() == "Pulmão"           # a geral continua lá
    d._save()
    assert s.get("viewer.wl_presets_mod") == {"MR": {"1": ["T2", 900.0, 450.0]}}
    assert s.get("viewer.wl_presets")["1"][0] == "Pulmão"
