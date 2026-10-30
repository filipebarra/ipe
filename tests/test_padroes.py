"""Padrões guardados: a última cor usada e os últimos parâmetros do dinâmico."""
import pytest
from PySide6.QtWidgets import QApplication, QMenu

from ipe.core.config import Settings
from ipe.imaging import colormaps as CM
from ipe.importer.scanner import Importer


def test_a_cor_puh_thalium_e_o_arco_iris_escuro_da_ge():
    """A primeira versão desta tabela era chute meu — e era outra escala.

    O PUH Thallium da GE (Advantage Workstation / FuncTool) é um arco-íris **escurecido**:
    preto → azul → ciano/verde → amarelo → laranja. Os pontos vieram da medição de uma faixa
    da própria GE. Este teste guarda a forma da escala, não os valores exatos.
    """
    assert "puh_thalium" in CM.COLORMAPS
    lut = CM.lut("puh_thalium")
    assert lut.shape == (256, 3)
    assert len({tuple(c) for c in lut}) > 200
    preto, azul, verde, meio_fim, fim = lut[0], lut[45], lut[140], lut[185], lut[255]
    assert sum(int(x) for x in preto) < 30, "começa praticamente preto"
    assert int(azul[2]) > int(azul[1]) > int(azul[0]), "o primeiro terço é azul"
    assert int(verde[1]) > int(verde[0]) and int(verde[1]) > int(verde[2]), "o meio é verde"
    assert int(meio_fim[0]) > 150 and int(meio_fim[1]) > 150 and int(meio_fim[2]) < 40, "depois, amarelo"
    assert int(fim[0]) > int(fim[1]) > int(fim[2]), "termina em laranja"
    # e é mais escuro que um arco-íris comum justamente no verde e no amarelo
    arco = CM.lut("rainbow")
    assert int(verde.sum()) < int(arco[140].sum()) + 60


@pytest.fixture()
def viewer(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1000, 700)
    w.show()
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 1)
    app.processEvents()
    yield app, w, tab, tab.viewports[0]
    w.close()


def test_a_cor_escolhida_no_menu_vira_padrao_da_modalidade(viewer):
    app, w, tab, vp = viewer
    mod = vp.modalidade_atual()
    assert mod
    vp.set_colormap("puh_thalium", lembrar=True)
    assert (vp.settings.get("viewer.cmap_padrao") or {}).get(mod) == "puh_thalium"
    # a próxima série da mesma modalidade já abre nela
    outra = [s for s in tab.series if s.series_uid != vp.series_uid]
    if outra:
        tab.load_series_into(vp, outra[0].series_uid)
        app.processEvents()
        assert vp.state.cmap == "puh_thalium"
    # e o menu diz que é isso que acontece
    m = QMenu()
    vp.add_colormap_actions(m, lembrar=True)
    assert any(mod in a.text() and not a.isEnabled() for a in m.actions())


def test_a_cor_posta_pelo_programa_nao_vira_padrao(viewer):
    app, w, tab, vp = viewer
    vp.set_colormap("pet")
    assert "pet" not in ((vp.settings.get("viewer.cmap_padrao") or {}).values())


def test_o_dinamico_reabre_com_os_ultimos_parametros(env, tmp_path):
    """Protocolo de mama é sempre o mesmo: refazer os ajustes a cada exame é trabalho à toa."""
    from ipe.ui.viewer.dynamic import DynamicDialog
    from test_measure_tools import make_dynamic
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    uid = make_dynamic(tmp_path / "d", one_series=False)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    w.browser.refresh()
    w.open_study(uid)
    tab = w.all_viewer_tabs()[-1]
    app.processEvents()
    dlg = DynamicDialog(tab)
    p = dlg.params()
    p["rapido_pct"], p["tardio_pct"], p["sinal_min_pct"] = 140.0, 15.0, 20.0
    tab.settings.set("dyn.ultimos", {k: v for k, v in p.items() if k != "uids"})
    guardados = dict(tab.settings.get("dyn.ultimos") or {})
    assert "uids" not in guardados
    outro = DynamicDialog(tab, None, guardados)
    assert outro.params()["rapido_pct"] == 140.0
    assert outro.params()["tardio_pct"] == 15.0
    assert outro.params()["sinal_min_pct"] == 20.0
    w.close()


def test_a_cor_de_um_mapa_da_dinamica_fica_guardada(viewer):
    """Mudou na 0.55.2, a pedido dele: ele trocava a cor do mapa em todo exame.

    O argumento antigo (a tabela é a legenda) não para em pé: a barra de cores desenhada ao lado
    **é** a tabela em uso, então acompanha a escolha e não mente. A chave é por mapa, não por
    modalidade, para a cor do MSI não arrastar o SER junto.
    """
    app, w, tab, vp = viewer
    vp.modality = "MAP cin"
    vp.set_colormap("jet", lembrar=True)
    assert (vp.settings.get("viewer.cmap_padrao") or {})["MAP cin"] == "jet"
    assert vp.cor_padrao() == "jet"
    vp.modality = "MAP ser"
    assert vp.cor_padrao() == "", "a cor de um mapa vazou para o outro"
    m = QMenu()
    vp.modality = "MAP cin"
    vp.add_colormap_actions(m, lembrar=True)
    nota = [a.text() for a in m.actions() if not a.isEnabled()]
    assert nota and "MAP cin" in nota[-1]
