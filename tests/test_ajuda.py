"""Menu Ajuda (0.75): F1 abre o guia do usuário em PDF; "Sobre" é uma janela curta.

Relato dele (13/10/2026): *"a ajuda não aparece. quando abro tem um menu simples, todo preto. esse
arquivo que você está gerando não era para estar lá como pdf?"* — o F1 abria uma caixa com o texto
da 0.13, de 4.400 px de altura, e o PDF não ia junto com o programa.
"""
import tomllib
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication, QMessageBox

from ipe.core.config import Settings
from ipe.ui import ajuda

RAIZ = Path(__file__).resolve().parents[1]


def test_o_guia_viaja_dentro_do_pacote():
    p = ajuda.caminho_do_guia()
    assert p is not None and p.parent.name == "ajuda" and p.parent.parent.name == "ipe"
    assert p.read_bytes()[:5] == b"%PDF-"


def test_o_empacotamento_leva_o_guia():
    cfg = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    assert "ajuda/*.pdf" in cfg["tool"]["setuptools"]["package-data"]["ipe"]
    spec = (RAIZ / "installer" / "ipe.spec").read_text(encoding="utf-8")
    assert '"ipe/ajuda"' in spec
    assert "ajuda" in (RAIZ / "installer" / "verifica.py").read_text(encoding="utf-8")


def test_abrir_guia_manda_o_pdf_para_o_leitor_do_sistema():
    QApplication.instance() or QApplication([])
    abertos = []
    assert ajuda.abrir_guia(None, abrir=lambda url: abertos.append(url) or True)
    assert len(abertos) == 1 and abertos[0].toLocalFile().endswith(ajuda.GUIA)


def test_sem_leitor_de_pdf_diz_onde_esta_o_guia(monkeypatch):
    QApplication.instance() or QApplication([])
    avisos = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: avisos.append(a[2])))
    assert not ajuda.abrir_guia(None, abrir=lambda url: False)
    assert avisos and ajuda.GUIA in avisos[0] and "leitor de PDF" in avisos[0]


def test_sem_o_arquivo_diz_o_que_fazer(monkeypatch):
    QApplication.instance() or QApplication([])
    avisos = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: avisos.append(a[2])))
    monkeypatch.setattr(ajuda, "caminho_do_guia", lambda: None)
    assert not ajuda.abrir_guia(None, abrir=lambda url: True)
    assert avisos and "não foi encontrado" in avisos[0]


def test_sobre_cabe_na_tela():
    app = QApplication.instance() or QApplication([])
    box = QMessageBox(QMessageBox.NoIcon, "Sobre", ajuda.texto_sobre())
    box.show()
    app.processEvents()
    assert box.height() < 500, f"a janela Sobre tem {box.height()} px (a antiga tinha 4.433)"
    box.close()
    assert "Guia do usuário" in ajuda.texto_sobre() and "0.13" not in ajuda.texto_sobre()


def test_f1_abre_o_guia(env, monkeypatch):
    from PySide6.QtGui import QDesktopServices
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    QApplication.instance() or QApplication([])
    abertos = []
    monkeypatch.setattr(QDesktopServices, "openUrl", staticmethod(lambda url: abertos.append(url) or True))
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        menu = next(a.menu() for a in w.menuBar().actions() if a.text() == "A&juda")
        f1 = next(a for a in menu.actions() if a.shortcut().toString() == "F1")
        assert f1.text() == "Guia do usuário (PDF)"
        assert any(a.text() == "Sobre o Ipê…" for a in menu.actions())
        f1.trigger()
        assert abertos and abertos[-1].toLocalFile().endswith(ajuda.GUIA)
    finally:
        w.close()


def test_o_guia_empacotado_e_da_versao_do_codigo():
    """O guia ficou na 0.65 enquanto o programa chegava à 0.79 (o gerador tinha se perdido).

    Agora o texto e o gerador moram em tools/guia/. Este teste reprova a cada versão nova até o
    guia ser gerado de novo:  python tools/guia/gerar_guia.py
    """
    import re
    from ipe import __version__
    pdf = ajuda.caminho_do_guia().read_bytes()
    # metadado "Subject" que o gerador grava: (Manual de uso, versão X.Y.Z)
    achou = re.search(rb"/Subject \(Manual de uso, vers\S* ([0-9.]+)\)", pdf)
    assert achou, "o PDF não diz de que versão é (gerado fora de tools/guia/gerar_guia.py?)"
    assert achou.group(1).decode() == __version__, \
        f"guia da {achou.group(1).decode()}, programa na {__version__}: rode tools/guia/gerar_guia.py"


def test_o_gerador_do_guia_esta_no_projeto(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("gerar_guia", RAIZ / "tools" / "guia" / "gerar_guia.py")
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    texto = (RAIZ / "tools" / "guia" / "guia.md").read_text(encoding="utf-8")
    assert not g.simbolos_sem_fonte(texto), "há símbolo no guia que a fonte não desenha"
    saida = g.gerar([tmp_path / "guia.pdf"])[0]
    assert saida.read_bytes()[:5] == b"%PDF-"
