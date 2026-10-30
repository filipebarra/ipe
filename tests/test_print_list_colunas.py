"""Janela de impressões: colunas e filtros como no banco, e a folha do filme do compositor à vista."""
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings


@pytest.fixture()
def aba_com_filmes(env, sample_dir):
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([sample_dir])
    settings = Settings(paths.settings_file)
    settings.set("dicom", dict(settings.get("dicom", {}), enabled=False, http_enabled=False))
    from ipe.printing.film import Cell, Film, Sheet
    estudo = repo.search_studies()[0]
    serie = repo.series_for_study(estudo.study_uid)[0]
    inst = repo.instances_for_series(serie.series_uid)[0]
    ids = {}
    for nome, paciente, folhas in (("Aula de mama", "ZULEICA", 2), ("Caso do dia", "ANA", 1),
                                   ("Revisão", "MARIA", 1)):
        filme = Film(name=nome, sheets=[Sheet(1, 1, "A4") for _ in range(folhas)])
        for sh in filme.sheets:
            sh.cells[0] = Cell(estudo.study_uid, serie.series_uid, inst["sop_uid"], 0)
        ids[nome] = repo.save_film(nome, filme.to_dict(), [estudo.study_uid], paciente)
    from ipe.ui.prints_tab import PrintsTab
    aba = PrintsTab(repo, settings)
    aba.resize(1200, 700)
    app.processEvents()
    yield app, aba, settings, repo, ids
    aba.deleteLater()


def _visiveis(aba, col):
    return [aba.table.item(i, col).text() for i in range(aba.table.rowCount()) if not aba.table.isRowHidden(i)]


def test_filtro_de_texto_e_por_valores(aba_com_filmes):
    from ipe.ui.prints_tab import CHAVES
    app, aba, _s, _r, _ids = aba_com_filmes
    pac = CHAVES.index("paciente")
    assert sorted(_visiveis(aba, pac)) == ["ANA", "MARIA", "ZULEICA"]
    aba.set_column_filter("paciente", "ana|maria")
    assert sorted(_visiveis(aba, pac)) == ["ANA", "MARIA"]
    assert "2 de 3" in aba.contagem.text() and aba.b_limpar.isEnabled()
    aba.set_column_filter("paciente", "")
    aba.set_value_filter(CHAVES.index("folhas"), {"2"})
    assert _visiveis(aba, pac) == ["ZULEICA"]
    aba.set_column_filter("folhas", ">=1")          # número: compara como número
    assert _visiveis(aba, pac) == ["ZULEICA"]
    aba.clear_filters()
    assert len(_visiveis(aba, pac)) == 3 and not aba.b_limpar.isEnabled()
    # o filtro continua valendo depois de a lista ser recarregada
    aba.set_column_filter("paciente", "maria")
    aba.refresh()
    assert _visiveis(aba, pac) == ["MARIA"]


def test_ordenar_e_escolher_a_linha_certa(aba_com_filmes):
    from ipe.ui.prints_tab import CHAVES
    app, aba, _s, _r, _ids = aba_com_filmes
    pac = CHAVES.index("paciente")
    aba._ordenar_por(pac)
    assert _visiveis(aba, pac) == ["ANA", "MARIA", "ZULEICA"]
    aba.table.selectRow(2)
    assert [r["patient_name"] for r in aba.selected()] == ["ZULEICA"]
    aba._ordenar_por(pac)
    assert _visiveis(aba, pac) == ["ZULEICA", "MARIA", "ANA"]
    aba.refresh()                                   # a ordem escolhida sobrevive à recarga
    assert _visiveis(aba, pac) == ["ZULEICA", "MARIA", "ANA"]
    aba._ordenar_por(pac)                           # terceiro clique: volta à ordem de chegada
    assert aba._ordem is None
    # linha escondida pelo filtro não entra na seleção
    aba.table.selectAll()
    aba.set_column_filter("paciente", "ana")
    assert [r["patient_name"] for r in aba.selected()] == ["ANA"]


def test_colunas_escondidas_e_reordenadas_ficam_salvas(aba_com_filmes):
    from ipe.ui.prints_tab import CHAVES, PrintsTab
    app, aba, settings, repo, _ids = aba_com_filmes
    aba.set_coluna_visivel("destino", False)
    aba.set_coluna_visivel("paciente", False)       # o paciente não some
    assert aba.table.isColumnHidden(CHAVES.index("destino"))
    assert not aba.table.isColumnHidden(CHAVES.index("paciente"))
    aba.cab.moveSection(aba.cab.visualIndex(CHAVES.index("chegada")), 0)
    assert settings.get("impressoes.colunas")[0] == "chegada"
    assert "destino" not in settings.get("impressoes.colunas")
    outra = PrintsTab(repo, settings)
    app.processEvents()
    assert outra.table.isColumnHidden(CHAVES.index("destino"))
    assert outra.cab.visualIndex(CHAVES.index("chegada")) == 0
    outra._restaurar_colunas()
    assert not outra.table.isColumnHidden(CHAVES.index("destino"))
    assert outra.cab.visualIndex(CHAVES.index("origem")) == 0
    outra.deleteLater()


def test_filme_do_compositor_aparece_na_previa_e_o_duplo_clique_abre(aba_com_filmes):
    from ipe.ui.prints_tab import CHAVES
    app, aba, _s, _r, ids = aba_com_filmes
    pac = CHAVES.index("paciente")
    linha = next(i for i in range(aba.table.rowCount()) if aba.table.item(i, pac).text() == "ZULEICA")
    aba.table.selectRow(linha)
    app.processEvents()
    pm = aba.preview.pixmap()
    assert pm is not None and not pm.isNull()
    assert aba.folha_label.text() == "Folha 1 de 2" and aba.b_proxima.isEnabled()
    aba._virar(1)
    assert aba.folha_label.text() == "Folha 2 de 2"
    assert "duplo clique" in aba.detalhes.text()
    abertos = []
    aba.open_film.connect(abertos.append)
    aba.table.doubleClicked.emit(aba.table.model().index(linha, 0))
    assert abertos == [ids["Aula de mama"]]
