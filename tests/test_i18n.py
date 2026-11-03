"""Idiomas: catálogo, tradução de textos e padrões, arquivos do usuário e o gancho do Qt."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from ipe.core import i18n

SRC = Path(i18n.__file__).resolve().parents[2]      # a pasta src em uso


@pytest.fixture(autouse=True)
def _base():
    """Cada teste começa (e termina) em português, sem pasta do usuário."""
    i18n.set_user_dir(None)
    i18n.load(i18n.BASE_LANG)
    yield
    i18n.set_user_dir(None)
    i18n.load(i18n.BASE_LANG)


def test_catalogo_completo_em_ingles_e_espanhol():
    fontes = i18n.all_sources()
    assert len(fontes) > 2000
    for lang in ("en", "es"):
        t = i18n.translations_for(lang)
        faltam = [s for s in fontes if not t.get(s)]
        assert not faltam, f"{lang}: {len(faltam)} sem tradução, ex.: {faltam[:3]}"


def test_padroes_tem_o_mesmo_numero_de_chaves():
    for lang in ("en", "es"):
        t = i18n.translations_for(lang)
        for src, dst in t.items():
            if "{}" in src:
                assert dst.count("{}") == src.count("{}"), f"{lang}: {src!r} -> {dst!r}"


def test_tr_texto_simples_e_pattern():
    i18n.load("en")
    assert i18n.tr("Fechar") == "Close"
    assert i18n.tr("") == ""
    assert i18n.tr(None) is None
    # padrão com partes variáveis
    assert i18n.tr("Série 7") == "Series 7"
    assert i18n.tr("12 imagens") == "12 images"
    # espaços em volta são preservados
    assert i18n.tr("  Fechar  ") == "  Close  "
    # sem tradução: devolve igual e anota em missing()
    assert i18n.tr("zzz texto inexistente") == "zzz texto inexistente"
    assert "zzz texto inexistente" in i18n.missing()


def test_tr_texto_montado_com_pontos_e_marcacao():
    i18n.load("en")
    # barra de status: várias frases juntas com "·" — cada pedaço é traduzido
    junto = "RAM do programa: 161 MB   ·   Cache de imagens: 0 / 978 MB"
    assert i18n.tr(junto) == "Program RAM: 161 MB   ·   Image cache: 0 / 978 MB"
    # um padrão não pode "engolir" o resto da linha
    assert i18n.tr("Cache de imagens: 0 / 978 MB") == "Image cache: 0 / 978 MB"
    # texto dentro de marcação simples
    assert i18n.tr("<i>Não destinado a uso diagnóstico</i>") == "<i>Not intended for diagnostic use</i>"


def test_tr_em_portugues_nao_mexe_no_texto():
    assert i18n.current() == i18n.BASE_LANG and i18n.is_base()
    assert i18n.tr("Fechar") == "Fechar"


def test_espanhol_e_troca_de_idioma():
    i18n.load("es")
    assert i18n.tr("Fechar") == "Cerrar"
    assert i18n.tr("Salvar") == "Guardar"
    i18n.load("en")
    assert i18n.tr("Salvar") == "Save"


def test_arquivo_do_usuario_vale_mais_e_cria_idioma_novo(tmp_path):
    i18n.set_user_dir(tmp_path)
    p = i18n.save_user("en", {"Fechar": "Shut", "Salvar": "Save"})
    assert p and p.exists()
    guardado = json.loads(p.read_text(encoding="utf-8"))
    assert guardado == {"Fechar": "Shut"}       # só o que é diferente do arquivo de fábrica
    i18n.load("en")
    assert i18n.tr("Fechar") == "Shut" and i18n.tr("Salvar") == "Save"
    # idioma novo, só do usuário
    i18n.save_user("fr", {"Fechar": "Fermer"})
    assert "fr" in {c for c, _n in i18n.available()}
    i18n.load("fr")
    assert i18n.tr("Fechar") == "Fermer"


def test_available_comeca_pelo_ingles():
    """0.99.33: o inglês é o padrão e vem primeiro; português e espanhol logo depois."""
    codigos = [c for c, _n in i18n.available()]
    assert codigos[:3] == ["en", "pt-BR", "es"]
    assert i18n.DEFAULT_LANG == "en" and i18n.BASE_LANG == "pt-BR"
    assert i18n.language_name("en") == "English"


def test_system_language():
    assert i18n.system_language() in {"", "pt-BR", "en", "es"}


# ---------------------------------------------------------------- gancho do Qt (em outro processo)
_QT_SCRIPT = r'''
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, sys.argv[1])
from ipe.core import i18n
i18n.load("en")
from ipe.ui.qt_i18n import install
install()
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QComboBox, QTabWidget, QWidget
from PySide6.QtGui import QAction
app = QApplication([])
assert QLabel("Fechar").text() == "Close", QLabel("Fechar").text()
b = QPushButton("Salvar"); assert b.text() == "Save", b.text()
b.setText("Fechar"); assert b.text() == "Close", b.text()
b.setToolTip("Salvar"); assert b.toolTip() == "Save", b.toolTip()
c = QComboBox(); c.addItem("Fechar"); c.addItems(["Salvar"])
# 0.99.34: a tela mostra traduzido; o código lê o original
import ipe.core.i18n as I_
tela = [c.model().index(i, 0).data() for i in range(2)]
assert tela == ["Close", "Save"], tela
assert c.itemText(0) == "Fechar" and c.currentText() == "Fechar", (c.itemText(0), c.currentText())
assert c.findText("Salvar") == 1
c.setCurrentText("Salvar"); assert c.currentIndex() == 1 and c.currentText() == "Salvar"
c.insertItem(0, "Todas"); assert c.model().index(0, 0).data() == "All" and c.itemText(0) == "Todas"
c.setItemText(2, "Fechar"); assert c.itemText(2) == "Fechar" and c.model().index(2, 0).data() == "Close"
ed = QComboBox(); ed.setEditable(True); ed.addItems(["Fechar"]); ed.setEditText("texto livre")
assert ed.currentText() == "texto livre"
# 0.99.35: barra de status, texto de várias linhas e pedaço dentro de frase montada
from PySide6.QtWidgets import QStatusBar
sb = QStatusBar(); sb.showMessage("Fechar"); assert sb.currentMessage() == "Close", sb.currentMessage()
assert I_.tr("Fechar\n   Salvar") == "Close\n   Save", I_.tr("Fechar\n   Salvar")
from ipe.ui.qt_i18n import mesmo
assert I_.original("Close") == "Fechar" and I_.original("xyz não traduzido") == "xyz não traduzido"
assert mesmo("Close", "Fechar") and mesmo("Fechar", "Fechar") and not mesmo("Save", "Fechar")
t = QTabWidget(); t.addTab(QWidget(), "Fechar"); assert t.tabText(0) == "Close", t.tabText(0)
a = QAction("Salvar"); assert a.text() == "Save", a.text()
w = QWidget(); w.setWindowTitle("Fechar"); assert w.windowTitle() == "Close", w.windowTitle()
# QPainter.drawText: overlay do viewer e telas desenhadas à mão
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtCore import QPointF
vistos = []
pm = QPixmap(200, 60); pm.fill()
p = QPainter(pm)
orig = type(p).drawText
p.drawText(QPointF(5, 20), "Fechar")
p.end()
import ipe.core.i18n as I
assert I.tr("Fechar") == "Close"
assert getattr(orig, "_i18n", False), "QPainter.drawText não foi envolvido"
print("ok")
'''


def test_qt_i18n_traduz_os_textos_da_tela(tmp_path):
    script = tmp_path / "qt_check.py"
    script.write_text(_QT_SCRIPT, encoding="utf-8")
    r = subprocess.run([sys.executable, str(script), str(SRC)], capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ok" in r.stdout


def test_normalize():
    for x, y in (("en", "en"), ("en_US", "en"), ("EN-gb", "en"), ("pt", "pt-BR"), ("pt_BR", "pt-BR"),
                 ("Português (Brasil)", "pt-BR"), ("es", "es"), ("es-MX", "es"), ("Español", "es"),
                 ("xx", ""), ("", "")):
        assert i18n.normalize(x) == y, x


def test_set_language_pela_linha_de_comando(tmp_path, monkeypatch):
    """O instalador grava o idioma escolhido: a primeira abertura não pergunta de novo."""
    import json
    from ipe.__main__ import main
    monkeypatch.setenv("IPE_HOME", str(tmp_path))
    assert main(["set-language", "es"]) == 0
    from ipe.core.config import get_paths
    dados = json.loads(get_paths().settings_file.read_text(encoding="utf-8"))
    assert dados["language"] == "es"
    assert main(["set-language", "pt_BR"]) == 0
    assert json.loads(get_paths().settings_file.read_text(encoding="utf-8"))["language"] == "pt-BR"
    assert main(["set-language", "klingon"]) == 2


def test_primeira_abertura_sugere_ingles(tmp_path, monkeypatch):
    """Sem idioma gravado (pacote portátil), a pergunta vem com o inglês marcado, mesmo num Windows em
    português."""
    from PySide6.QtWidgets import QApplication, QComboBox, QDialog
    QApplication.instance() or QApplication([])
    from ipe import app as A
    from ipe.core.config import Settings
    monkeypatch.setattr(i18n, "system_language", lambda: "pt-BR")
    visto = {}

    def exec_(self):
        visto["lang"] = self.findChild(QComboBox).currentData()
        return 1
    monkeypatch.setattr(QDialog, "exec", exec_)
    s = Settings(tmp_path / "settings.json")
    assert A._choose_language(s) == "en" and visto["lang"] == "en" and s.get("language") == "en"
    assert A._choose_language(s) == "en"            # gravado: não pergunta de novo


_BANCO_EM_INGLES = r'''
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["DICOMVIEWER_HOME"] = sys.argv[2]
sys.path.insert(0, sys.argv[1])
from ipe.core import i18n
i18n.load("en")
from ipe.ui.qt_i18n import install
install()
from PySide6.QtWidgets import QApplication
app = QApplication([])
from ipe.core.config import get_paths, Settings
from ipe.core.sample_data import make_sample_data
from ipe.db.repository import Repository
from ipe.db.session import Database
from ipe.importer.scanner import Importer
paths = get_paths()
db = Database(paths.database)
repo = Repository(db)
make_sample_data(sys.argv[3])
Importer(db, paths.storage).import_paths([sys.argv[3]])
n = len(repo.search_studies())
assert n > 0
from ipe.ui.main_window import MainWindow
w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
b = w.browser
b.refresh()
assert b.model.rowCount() == n, (b.model.rowCount(), n, b.modality.currentText())
assert b.modality.model().index(0, 0).data() == "All"
# visualizador em inglês (muitas listas suspensas)
for r in repo.search_studies()[:3]:
    w.open_study(r.study_uid)
    QApplication.processEvents()
assert len(list(w.all_viewer_tabs())) >= 1
# permissões dos menus valem em inglês (o código decide pelo texto original)
from ipe.auth import session as S
from ipe.core.i18n import original
acoes = [x for a in w.menuBar().actions() if a.menu() for x in a.menu().actions()]
imp = [x for x in acoes if original(x.text()).replace("&", "").startswith("Importar")]
assert imp and imp[0].text() != original(imp[0].text()), [x.text() for x in imp]
# mensagem de encerramento traduzida por inteiro
from PySide6.QtWidgets import QMessageBox
vistos = {}
def _exec(self):
    vistos["t"], vistos["i"] = self.text(), self.informativeText()
    vistos["b"] = [b.text() for b in self.buttons()]
    return 0
QMessageBox.exec = _exec
w._confirmar_saida()
assert vistos["t"] == "Close Ipê?" and vistos["i"].startswith("While the program is closed"), vistos
assert "Close" in vistos["b"] and "Cancel" in vistos["b"], vistos
# página de Configurações em inglês: abre a aba certa
from ipe.ui.preferences import PreferencesDialog, PAGINAS
for pg in ("idioma", "mouse", "cad_ia"):
    d = PreferencesDialog(Settings(paths.settings_file), None, pagina=pg)
    _t, aba, _s = PAGINAS[pg]
    assert d.tabs.tabText(d.tabs.currentIndex()) == i18n.tr(aba), (pg, d.tabs.tabText(d.tabs.currentIndex()))
print("ok", n, flush=True)
os._exit(0)                      # sem fechar a janela: o "Sair do programa?" ficaria esperando
'''


def test_banco_nao_fica_vazio_em_ingles(tmp_path):
    """0.99.34, relato dele: em inglês o banco aparecia vazio ("Todas" virava "All" no filtro)."""
    script = tmp_path / "banco_en.py"
    script.write_text(_BANCO_EM_INGLES, encoding="utf-8")
    r = subprocess.run([sys.executable, str(script), str(SRC), str(tmp_path / "home"), str(tmp_path / "s")],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    assert "ok" in r.stdout
