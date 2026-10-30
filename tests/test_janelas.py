"""0.99.6: toda janela abre maximizada; fechar o programa pergunta antes."""
import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QMessageBox, QWidget

from ipe.core.config import Settings
from ipe.ui import janelas


def _esperar(app, n=20):
    for _ in range(n):
        app.processEvents()


def _oitenta(w):
    from PySide6.QtGui import QGuiApplication
    area = QGuiApplication.primaryScreen().availableGeometry()
    ok_tam = abs(w.width() - int(area.width() * 0.8)) <= 2 and abs(w.height() - int(area.height() * 0.8)) <= 2
    centro = w.frameGeometry().center()
    return ok_tam and abs(centro.x() - area.center().x()) <= 3 and abs(centro.y() - area.center().y()) <= 3


def test_janelas_grandes_abrem_no_centro_com_80_por_cento(tmp_path):
    """0.99.7: no centro, com 80% da área útil do monitor (na 0.99.6 era maximizada e não funcionou)."""
    app = QApplication.instance() or QApplication([])
    st = Settings(tmp_path / "s.json")
    f = janelas.instalar(app, st)
    try:
        grande = QWidget()
        grande.resize(500, 300)
        dlg_grande = QDialog()
        dlg_grande.resize(900, 600)
        dlg_pequeno = QDialog()
        dlg_pequeno.resize(300, 120)
        caixa = QMessageBox(QMessageBox.Information, "t", "texto")
        fixo = QWidget()
        fixo.setFixedSize(700, 500)
        for w in (grande, dlg_grande, dlg_pequeno, caixa, fixo):
            w.show()
        _esperar(app)
        assert _oitenta(grande) and _oitenta(dlg_grande)
        assert not grande.isMaximized()
        assert dlg_pequeno.width() == 300 and fixo.width() == 700 and not _oitenta(caixa)
        # se ele mudar o tamanho, esconder e mostrar de novo não desfaz
        grande.resize(400, 300)
        grande.hide()
        grande.show()
        _esperar(app)
        assert grande.width() == 400
        # a janela do banco (que tem opção própria) não é mexida
        class Banco(QMainWindow):
            def abre_maximizada(self):
                return True
        banco = Banco()
        banco.resize(500, 300)
        banco.show()
        _esperar(app)
        assert banco.width() == 500
        # desligado em Preferências
        st.set("ui.janelas_maximizadas", False)
        outra = QWidget()
        outra.resize(500, 300)
        outra.show()
        _esperar(app)
        assert outra.width() == 500
        for w in (grande, dlg_grande, dlg_pequeno, caixa, fixo, outra, banco):
            w.close()
    finally:
        app.removeEventFilter(f)


@pytest.mark.pergunta_ao_sair
def test_fechar_pergunta_antes(env, monkeypatch):
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.show()
    perguntas = []
    resposta = {"fechar": False}

    def exec_falso(caixa):
        perguntas.append(caixa.text())
        botoes = {b.text(): b for b in caixa.buttons()}
        assert caixa.defaultButton() is botoes["Cancelar"]       # Enter por engano não fecha
        alvo = botoes["Fechar"] if resposta["fechar"] else botoes["Cancelar"]
        monkeypatch.setattr(caixa, "clickedButton", lambda: alvo)
        return 0
    monkeypatch.setattr(QMessageBox, "exec", exec_falso)
    w.close()
    _esperar(app)
    assert perguntas == ["Fechar o Ipê?"] and w.isVisible()          # cancelou: continua aberto
    resposta["fechar"] = True
    w.close()
    _esperar(app)
    assert len(perguntas) == 2 and not w.isVisible()
    # desligado: fecha sem perguntar
    w2 = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w2.settings.set("ui.confirmar_sair", False)
    w2.show()
    w2.close()
    _esperar(app)
    assert len(perguntas) == 2 and not w2.isVisible()
