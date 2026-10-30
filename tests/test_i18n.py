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


def test_available_comeca_pelo_portugues():
    codigos = [c for c, _n in i18n.available()]
    assert codigos[0] == i18n.BASE_LANG
    assert "en" in codigos and "es" in codigos
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
assert c.itemText(0) == "Close" and c.itemText(1) == "Save", (c.itemText(0), c.itemText(1))
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
