"""Perfil de anotação da cópia e carimbo mínimo obrigatório (0.99.22, plano AW 12)."""
import pytest
from PySide6.QtWidgets import QApplication


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


def test_carimbo_tem_janela_escala_e_processamento(tc):
    app, w, tab, vp = tc
    t = vp.carimbo_texto()
    assert "W " in t and "pixel " in t
    from ipe.imaging.filters import FILTERS
    vp.set_filter(next(k for k in FILTERS if k))
    assert vp.processamento_aplicado() and vp.processamento_aplicado()[0] in vp.carimbo_texto()


def test_copia_usa_o_nivel_de_saida(tc):
    app, w, tab, vp = tc
    nome = vp.study_info.get("patient_name", "")
    vistos = []
    orig = vp._text_lines

    def espia():
        r = orig()
        vistos.append([t for c in r.values() for t, _h in c])
        return r
    vp._text_lines = espia
    w.settings.set("viewer.anotacoes_saida", "parcial1")
    vp.imagem_da_tela(1.0)
    assert vistos and nome not in vistos[-1]                 # a cópia sai sem o nome
    assert vp._nivel_forcado is None
    vistos.clear()
    vp.grab()
    assert nome in vistos[-1]                                # a tela continua completa


def test_carimbo_pinta_o_pe_da_imagem(tc):
    app, w, tab, vp = tc
    w.settings.set("viewer.anotacoes_saida", "ausente")
    com = vp.imagem_da_tela(1.0)
    w.settings.set("viewer.carimbo_saida", False)
    sem = vp.imagem_da_tela(1.0)
    y = com.height() - 4
    assert any(com.pixel(x, y) != sem.pixel(x, y) for x in range(0, com.width(), 3))


def test_editor_guarda_a_saida(tmp_path):
    QApplication.instance() or QApplication([])
    from ipe.core.config import Settings
    from ipe.ui.viewer.anotacoes_editor import AnotacoesEditor
    s = Settings(tmp_path / "s.json")
    e = AnotacoesEditor(s)
    e.c_saida.setCurrentIndex(e.c_saida.findData("parcial2"))
    e.cb_carimbo.setChecked(False)
    e.save()
    assert s.get("viewer.anotacoes_saida") == "parcial2" and s.get("viewer.carimbo_saida") is False
