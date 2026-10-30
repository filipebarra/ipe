"""Funções de cada nó (busca, anteriores, envio) e escolha dos nós da busca por anteriores."""
from sqlalchemy import text
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.network.nodes import (
    prior_candidates, prior_nodes, prior_selection, search_nodes, send_nodes, set_prior_selection,
)


def test_roles_and_selection(env):
    paths, db, repo = env
    a = repo.save_node({"name": "PACS A", "ae_title": "A", "host": "h", "port": 104})
    b = repo.save_node({"name": "PACS B", "ae_title": "B", "host": "h", "port": 104, "use_in_search": False,
                        "use_in_priors": True, "use_in_send": False})
    c = repo.save_node({"name": "Estação", "ae_title": "C", "host": "h", "port": 104, "use_in_priors": False})
    ids = lambda ns: sorted(n["id"] for n in ns)
    assert ids(search_nodes(repo)) == sorted([a, c])
    assert ids(prior_candidates(repo)) == sorted([a, b])
    assert ids(send_nodes(repo)) == sorted([a, c])
    s = Settings(paths.settings_file)
    assert prior_selection(s) is None and ids(prior_nodes(repo, s)) == sorted([a, b])
    set_prior_selection(s, [b])
    assert ids(prior_nodes(repo, Settings(paths.settings_file))) == [b]
    set_prior_selection(s, None)
    assert prior_selection(s) is None
    # banco antigo (colunas nulas): anteriores segue "busca", envio liberado
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE dicom_node SET use_in_priors = NULL, use_in_send = NULL"))
    n = {x["id"]: x for x in repo.nodes()}
    assert n[a]["use_in_priors"] and not n[b]["use_in_priors"] and all(x["use_in_send"] for x in n.values())


def test_dialogs(env, sample_dir):
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    from ipe.ui.network_dialog import NetworkDialog, NodeDialog
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    Importer(db, paths.storage).import_paths([sample_dir])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    d = NodeDialog(None)
    d.name.setText("PACS X")
    d.ae.setText("PACSX")
    d.host.setText("10.0.0.5")
    d.send.setChecked(False)
    d._ok()
    assert d.data["use_in_search"] and d.data["use_in_priors"] and not d.data["use_in_send"]
    x = w.repo.save_node(d.data)
    y = w.repo.save_node({"name": "PACS Y", "ae_title": "Y", "host": "h", "port": 104})
    dlg = NetworkDialog(w.settings, w.repo, w.net, w)
    assert dlg.t_nodes.item(0, 7) is not None and dlg.pr_all.isChecked() and dlg.pr_list.count() == 2
    dlg.pr_sel.setChecked(True)
    for i in range(dlg.pr_list.count()):
        it = dlg.pr_list.item(i)
        it.setCheckState(it.checkState().__class__.Checked if it.data(0x0100) == y else it.checkState().__class__.Unchecked)
    dlg._save()
    assert prior_selection(w.settings) == [y]
    # painel de anteriores: menu dos nós
    w.browser.refresh()
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    tab = w.tabs.currentWidget()
    tab.toggle_priors_panel(True)
    pp = tab.priors_panel
    assert pp.nodes_btn.text() == "Nós: 1 ▾"
    pp.toggle_node(x, True)
    assert prior_selection(w.settings) == sorted([x, y])
    pp.set_nodes(None)
    assert pp.nodes_btn.text() == "Nós: todos ▾"
    w.close()
