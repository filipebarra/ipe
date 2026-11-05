"""0.99.63 — estado do exame: não lido, em leitura, revisado, urgente (automático e à mão)."""
from _menus import submenu, todas  # noqa: F401
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core import estado_exame as EST
from ipe.core.config import Settings


def test_regras():
    assert EST.automatico("", "rotina", True) == "nao_lido"
    assert EST.automatico("", "rotina", False) == "em_leitura"
    assert EST.automatico("rascunho", "rotina", True) == "em_leitura"
    assert EST.automatico("", "urgente", False) == "urgente"
    assert EST.automatico("assinado", "emergencia", False) == "revisado"
    assert EST.automatico("retificado", "", True) == "revisado"
    assert EST.estado("revisado", "", "urgente", True) == "revisado"          # à mão manda
    assert EST.estado("xx", "", "", True) == "nao_lido"                       # valor estranho: automático
    assert set(EST.ESTADOS) == set(EST.ORDEM) == set(EST.CORES)


def test_no_banco_na_tela_e_no_visualizador(env, sample_dir):
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    rows = repo.search_studies()
    for r in rows:                                  # sem abrir nem laudar: não lido (ou urgente, pela regra)
        assert r.estado == ("urgente" if r.prioridade in EST.URGENTES else "nao_lido")
    rotina = [r for r in rows if r.prioridade not in EST.URGENTES]
    uid = rotina[0].study_uid
    est = lambda u: next(x for x in repo.search_studies() if x.study_uid == u)  # noqa: E731
    repo.mark_opened(uid)
    assert est(uid).estado == "em_leitura" and repo.estado_do_exame(uid)["estado"] == "em_leitura"
    repo.set_study_priority([uid], "urgente")
    assert est(uid).estado == "urgente"
    rid = repo.save_report({"study_uid": uid, "title": "x", "text": "x"})
    repo.sign_report(rid, "Dr. Teste")
    assert est(uid).estado == "revisado" and repo.estado_do_exame(uid) == {"estado": "revisado", "manual": ""}
    outro = rotina[1].study_uid
    assert repo.set_estado_leitura([outro], "revisado") == 1
    r = est(outro)
    assert r.estado == "revisado" and r.estado_manual == "revisado"
    with pytest.raises(ValueError):
        repo.set_estado_leitura([outro], "lido")
    repo.set_estado_leitura([outro], "")
    assert est(outro).estado == "nao_lido"
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    try:
        br = w.browser
        br.refresh()
        app.processEvents()
        n = br.proxy.rowCount()
        br.filtro_trabalho("nao_revisados")
        assert br.proxy.rowCount() == n - 1 and "estado" in br.visible_columns()
        br.filtro_trabalho("em_leitura")
        assert br.proxy.rowCount() == 0
        menu = br.menu_do_exame([rows[0]])
        sub = submenu(menu, "Organizar/Estado do exame")
        assert [a.text() for a in sub.actions() if a.text()] == ["Automático", "Não lido", "Em leitura", "Revisado",
                                                                 "Urgente"]
        br._trocar_estado([outro], "em_leitura")
        br.filtro_trabalho("em_leitura")
        assert br.proxy.rowCount() == 1
        # o texto da coluna marca o trocado à mão, e a cor vem do estado
        from ipe.ui.browser import KEY_INDEX
        from PySide6.QtCore import Qt
        col = KEY_INDEX["estado"]
        idx = br.proxy.index(0, col)
        assert br.proxy.data(idx, Qt.DisplayRole) == "Em leitura ✎"
        assert br.proxy.data(idx, Qt.ForegroundRole) is not None
        # no visualizador: marcar como revisado e voltar
        info = repo.study_info(outro)
        w.handle_external({"accession": info.get("accession", "")})
        tab = w.tabs.currentWidget()
        app.processEvents()
        assert tab.marcar_revisado(outro) == "revisado"
        assert tab.marcar_revisado(outro) in ("em_leitura", "nao_lido")
    finally:
        w.close()
