"""0.99.73 — clicar no nome do grupo do menu Configurações abre a janela com as etapas do grupo."""
from PySide6.QtCore import QEvent, QPointF, Qt, QTimer
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QDialog, QMenu

from ipe.core.config import Settings
from ipe.ui import configuracoes as C


def test_janela_do_grupo(env, monkeypatch):
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        d = C.GrupoDialog(w, "Visualizador")
        textos = [d.lista.item(i).text() for i in range(d.lista.count())]
        assert textos[0] == "Barra de ferramentas e aplicações" and "Mouse" in textos and len(textos) == 10
        # página de preferências: aparece ali mesmo
        d.lista.setCurrentRow(textos.index("Mouse"))
        assert d.pilha.currentWidget() is d.prefs and d.prefs.tabs.tabText(d.prefs.tabs.currentIndex()) == "Mouse"
        d.lista.setCurrentRow(textos.index("Texto e marcas sobre a imagem"))
        visiveis = [g.title() for g in d.prefs.tabs.currentWidget().findChildren(__import__(
            "PySide6.QtWidgets", fromlist=["QGroupBox"]).QGroupBox) if g.isVisibleTo(d.prefs.tabs.currentWidget())]
        assert "Texto e marcas sobre a imagem" in visiveis and "Idioma" not in visiveis
        # janela própria: cartão com o botão Abrir
        abertos = []
        monkeypatch.setattr(C, "executar", lambda win, alvo: abertos.append(alvo))
        d.lista.setCurrentRow(0)
        assert d.pilha.currentWidget() is d.cartao
        d.c_botao.click()
        assert abertos == ["f:abrir_config_barra"]
        # OK grava as páginas
        d.prefs.c_wheel.setCurrentIndex((d.prefs.c_wheel.currentIndex() + 1) % d.prefs.c_wheel.count())
        novo = d.prefs.c_wheel.currentData()
        d._ok()
        assert d.result() == QDialog.Accepted and w.settings.get("viewer.mouse")["wheel"] == novo
        # grupo sem páginas de preferências: só Fechar
        r = C.GrupoDialog(w, "Rede")
        assert r.prefs is None and r.pilha.currentWidget() is r.cartao
        # o clique no nome do submenu abre a janela do grupo
        m = QMenu()
        C.montar(w, m, m)
        acao = next(a for a in m.actions() if a.menu() is not None and a.text() == "CAD/IA")
        assert acao.data() == "CAD/IA"
        aberto = []
        monkeypatch.setattr(C, "abrir_grupo", lambda win, nome: aberto.append(nome))
        m.popup(w.mapToGlobal(w.rect().center()))
        app.processEvents()
        pos = QPointF(m.actionGeometry(acao).center())
        ev = QMouseEvent(QEvent.MouseButtonRelease, pos, pos, Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
        assert m._clique_no_grupo.eventFilter(m, ev) is True
        QTimer.singleShot(0, lambda: None)
        for _ in range(5):
            app.processEvents()
        assert aberto == ["CAD/IA"]
    finally:
        w.close()
