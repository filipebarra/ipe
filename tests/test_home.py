"""Tela inicial: botões e janela flutuante do PACS."""
from PySide6.QtWidgets import QApplication, QMessageBox

from ipe.auth import session as S
from ipe.auth.permissions import permissions_for
from ipe.core.config import Settings
from ipe.importer.scanner import Importer


def test_home_bar(env, sample_dir, monkeypatch):
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    Importer(db, paths.storage).import_paths([sample_dir])
    st = Settings(paths.settings_file)
    w = MainWindow(paths, st, repo=repo, db=db)
    w.resize(1400, 850)
    w.show()
    w.browser.refresh()
    app.processEvents()
    hb = w.home_bar
    expected = {"import", "pacs", "open", "send", "export", "print", "list", "meeting", "anon", "delete",
                "refresh", "settings", "users", "help"}
    assert expected <= set(hb.buttons)
    assert hb.isVisibleTo(w.browser)
    # PACS em janela própria, com geometria lembrada
    hb.buttons["pacs"].defaultAction().trigger()
    assert w.pacs_window.isVisible() and w.pacs_window.isWindow()
    w.pacs_window.close()
    assert st.get("pacs.geometry")
    # sem seleção: aviso
    msgs = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: msgs.append(a[2]) or 0))
    hb.buttons["open"].defaultAction().trigger()
    assert msgs and "Selecione" in msgs[-1]
    # com seleção: menu de envio lista os nós
    repo.save_node({"name": "PACS X", "ae_title": "PACSX", "host": "h", "port": 104})
    w.browser.table.selectRow(0)
    from PySide6.QtWidgets import QMenu
    m = QMenu()
    hb._send_menu(m)
    assert any(a.text() == "PACS X" for a in m.actions())
    m2 = QMenu()
    hb._list_menu(m2)
    assert m2.actions()[0].isEnabled()
    hb.buttons["open"].defaultAction().trigger()
    assert w.tabs.count() == 2
    w.tabs.setCurrentWidget(w.browser)
    # listas: mostrar/esconder
    hb.buttons["list"].defaultAction().trigger()
    assert w.browser.lists_panel.recolhido and st.get("browser.show_lists") is False   # 0.99.29: recolhe para a borda
    hb.buttons["list"].defaultAction().trigger()
    assert not w.browser.lists_panel.recolhido
    # ocultar dados: PACS indisponível
    hb.buttons["anon"].defaultAction().trigger()
    assert w.browser.model.anonymize and not hb.buttons["pacs"].isEnabled()
    hb.buttons["anon"].defaultAction().trigger()
    assert not w.browser.model.anonymize and hb.buttons["pacs"].isEnabled()
    # permissões: residente
    S.set_current(S.UserSession(username="r", role="residente", perms=permissions_for("residente")))
    w.apply_permissions()
    assert not hb.buttons["send"].isEnabled() and not hb.buttons["delete"].isEnabled()
    assert not hb.buttons["users"].isEnabled() and hb.buttons["export"].isEnabled()
    S.set_current(S.UserSession(username="t", role="tecnico", perms=permissions_for("tecnico")))
    w.apply_permissions()
    assert hb.buttons["list"].isHidden() and hb.buttons["meeting"].isHidden()
    w.close()
