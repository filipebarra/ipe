"""Série que é fase de uma dinâmica abre sempre como a dinâmica (0.69).

Pedido dele (10/10/2026): *"sempre que eu atribuir ou for atribuída automaticamente séries a uma
série dinâmica, se eu abrir qualquer uma delas no visualizador, clicando no canto superior da
janela e escolhendo a sequência, abra automaticamente a série dinâmica. uma vez que a série faça
parte de um grupo dinâmico, trate-a sempre como dinâmica"*.
"""
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer
from test_measure_tools import make_dynamic


@pytest.fixture()
def aba(env, tmp_path):
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    uid = make_dynamic(tmp_path / "d", slices=4, one_series=False)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1200, 800)
    w.show()
    w.open_study(uid)
    tab = w.all_viewer_tabs()[-1]
    app.processEvents()
    fases = [s.series_uid for s in sorted(repo.series_for_study(uid), key=lambda s: s.series_number)]
    yield app, w, tab, fases
    w.close()


def test_a_fase_abre_como_a_dinamica_na_fase_dela(aba):
    app, w, tab, fases = aba
    gid = tab.group_series(fases, "Dinâmica mama")
    vp = tab.viewports[0]
    tab.load_series_into(vp, fases[3])
    assert vp.series_uid == f"group:{gid}", "a série sozinha não abre mais: abre a dinâmica"
    assert vp.phase == 3 and vp.frames[0].series_uid == fases[3], "já na fase escolhida"
    tab.load_series_into(vp, fases[0], como_serie=True)
    assert vp.series_uid == fases[0], "quem precisa da série sozinha ainda consegue"


def test_o_menu_do_canto_abre_a_dinamica(aba):
    """O caminho que ele usa: canto superior do quadro, escolher a sequência."""
    app, w, tab, fases = aba
    gid = tab.group_series(fases, "Dinâmica mama")
    vp = tab.viewports[1] if len(tab.viewports) > 1 else tab.viewports[0]
    menu = tab.menu_de_series(vp)
    acao = next(a for a in menu.actions() if a.text().startswith("  ") is False
                and "▦ fase 2 de Dinâmica mama" in a.text())
    acao.trigger()
    assert vp.series_uid == f"group:{gid}" and vp.phase == 1
    menu = tab.menu_de_series(vp)
    marcadas = [a.text() for a in menu.actions() if a.isChecked()]
    assert any("fase 2 de" in t for t in marcadas), "o menu mostra em que fase o quadro está"


def test_grupo_da_regra_automatica_vale_igual(aba, env):
    """Grupo que a regra de "juntar" gravou no banco: ao reabrir o exame, vale do mesmo jeito."""
    app, w, tab, fases = aba
    paths, db, repo = env
    gid = repo.save_series_group(tab.study_uid, fases, "Juntada pela regra")
    tab.groups = {g["id"]: g for g in repo.series_groups(tab.study_uid)}
    vp = tab.viewports[0]
    tab.load_series_into(vp, fases[2])
    assert vp.series_uid == f"group:{gid}" and vp.phase == 2


def test_serie_separada_em_fases_abre_separada(env, tmp_path):
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    uid = make_dynamic(tmp_path / "d", slices=4, one_series=True)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    w.open_study(uid)
    tab = w.all_viewer_tabs()[-1]
    serie = repo.series_for_study(uid)[0].series_uid
    tab.separar_serie(serie)
    gid = next(k for k, g in tab.groups.items() if g.get("fases"))
    vp = tab.viewports[0]
    tab.load_series_into(vp, serie)
    assert vp.series_uid == f"group:{gid}"
    tab.load_series_into(vp, f"fase:{gid}:2")
    assert vp.series_uid == f"group:{gid}" and vp.phase == 2, "a miniatura da fase também abre a dinâmica"
    tab.ungroup(gid)
    assert vp.series_uid == serie, "desfazer a separação volta a série inteira"
    w.close()


def test_mpr_continua_valendo_no_quadro_da_dinamica(aba):
    """Abrir sempre como dinâmica não pode tirar a reconstrução nem a segmentação."""
    app, w, tab, fases = aba
    gid = tab.group_series(fases, "Dinâmica mama")
    vp = tab.viewports[0]
    tab.load_series_into(vp, fases[1])
    assert tab._source_series(vp) == fases[1]
    assert tab.reformatar(vp, "Coronal") and vp.plano_nome() == "Coronal"
    assert tab.reformatar(vp, "Original")
    assert vp.series_uid == f"group:{gid}" and vp.phase == 1, "voltar ao original volta à dinâmica"
