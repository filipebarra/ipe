"""Chamada externa: exame fora do banco é buscado nos nós e abre enquanto baixa."""
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.network import probe

ACHADO = {"study_uid": "1.2.3", "node_name": "PACS", "patient_name": "FULANO",
          "study_date": "20260101", "study_time": "080000", "modalities": "CT",
          "description": "TORAX", "num_images": 400}


def test_stream_externo_decide(tmp_path: Path):
    """Padrão ligado; a opção do nó manda quando o usuário marcou uma."""
    st = Settings(tmp_path / "s.json")
    assert probe.stream_externo(None, st)                        # padrão: abre enquanto baixa
    assert probe.stream_externo({"stream_open": None}, st)
    assert not probe.stream_externo({"stream_open": False}, st)  # o nó manda
    assert probe.stream_externo({"stream_open": True}, st)
    st.set("network.stream_external", False)
    assert not probe.stream_externo(None, st)
    assert not probe.stream_externo({"stream_open": None}, st)
    assert probe.stream_externo({"stream_open": True}, st)       # o nó continua mandando
    # a busca manual não mudou: lá o padrão segue desligado
    assert not probe.stream_enabled({"stream_open": None}, Settings(tmp_path / "t.json"))


@pytest.fixture(autouse=True)
def _fecha_janelas():
    """Janela aberta e não fechada trava a saída do pytest."""
    yield
    app = QApplication.instance()
    if app is not None:
        for w in list(app.topLevelWidgets()):
            w.close()
        app.processEvents()


def _janela(env):
    QApplication.instance() or QApplication([])
    paths, _db, _repo = env
    from ipe.ui.main_window import MainWindow
    return MainWindow(paths, Settings(paths.settings_file))


def _com_no(env, **extra):
    paths, db, repo = env
    repo.save_node({"name": "PACS", "ae_title": "PACS", "host": "10.0.0.1", "port": 104,
                    "kind": "dimse", "active": True, "use_in_search": True, **extra})
    w = _janela(env)
    node_id = repo.nodes()[0]["id"]
    baixados: list[dict] = []
    w.net.search = lambda nodes, i, f, cb: cb(([{**ACHADO, "node_id": node_id}], []), None)
    w.net.retrieve = lambda *a, **k: baixados.append(k) or None
    return w, baixados


def test_chamada_externa_baixa_e_abre_enquanto_baixa(env):
    w, baixados = _com_no(env)
    assert w.handle_external({"command": "open", "accession": "NOVO1"}) == "buscando"
    assert baixados and baixados[0]["open_after"] and baixados[0]["stream"]


def test_chamada_externa_retrieve_nao_abre_nem_transmite(env):
    w, baixados = _com_no(env)
    assert w.handle_external({"command": "retrieve", "accession": "NOVO2"}) == "buscando"
    # baixar sem abrir não tem por que abrir enquanto baixa
    assert baixados and not baixados[0]["open_after"] and not baixados[0]["stream"]


def test_chamada_externa_respeita_o_no_desligado(env):
    w, baixados = _com_no(env, stream_open=False)
    w.handle_external({"command": "open", "accession": "NOVO3"})
    assert baixados and baixados[0]["open_after"] and not baixados[0]["stream"]


def test_chamada_externa_respeita_quem_desligou_nas_configuracoes(env):
    w, baixados = _com_no(env)
    w.settings.set("network.stream_external", False)
    w.handle_external({"command": "open", "accession": "NOVO4"})
    assert baixados and baixados[0]["open_after"] and not baixados[0]["stream"]


def test_sem_no_cadastrado_nao_encontrado(env):
    w = _janela(env)
    assert w.handle_external({"command": "open", "accession": "SEMNO"}) == "nao_encontrado"


# --------------------------------------------------------------------- monitores


def test_chamada_externa_nao_desfaz_o_arranjo_das_telas(env):
    """`showNormal()` desmaximizava a janela do banco — ela saía do monitor configurado.

    Era o que ele via chamando pelo cli: o exame ia para o lugar certo, mas a janela principal
    pulava para a tela primária, com a geometria de antes de maximizar.
    """
    w = _janela(env)
    w.show()
    w.showMaximized()
    assert w.windowState() & Qt.WindowMaximized
    w.handle_external({"command": "open", "accession": "NAOEXISTE"})
    assert w.windowState() & Qt.WindowMaximized          # continua maximizada
    w.showMinimized()
    w.handle_external({"command": "open", "accession": "NAOEXISTE"})
    assert not w.isMinimized()                           # volta à vista
    assert w.windowState() & Qt.WindowMaximized          # e volta maximizada, não "normal"


class _Tela:
    """Tela de mentira: só o que o programa pergunta."""

    def __init__(self, nome):
        self._nome = nome

    def name(self):
        return self._nome


def test_chamada_externa_reparte_entre_os_monitores_viewer(env, sample_dir):
    """O exame chamado de fora entra pelos monitores, como se ele tivesse clicado na lista."""
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    w = _janela(env)
    w.show()
    w.browser.refresh()
    from ipe.ui import main_window as MW
    from ipe.ui.monitors import ScreenWindow
    telas = [_Tela("V1"), _Tela("V2")]
    real = QGuiApplication.primaryScreen()
    janelas: dict = {}

    def janela(tela, restrito=False):
        chave = (tela, bool(restrito))
        if chave not in janelas:
            j = ScreenWindow(w, real, restrito=restrito)
            j.screen_key = tela.name()
            w.detached.append(j)
            janelas[chave] = j
        return janelas[chave]

    mp = pytest.MonkeyPatch()
    mp.setattr(MW, "screens_with_role", lambda *a, **k: telas)
    mp.setattr(MW, "layout_for_screen", lambda _s, _t: (1, 1))
    mp.setattr(w, "window_for_screen", janela)
    try:
        linha = next(r for r in repo.search_studies() if r.accession)
        assert w.handle_external({"command": "open", "accession": linha.accession}) == "aberto"
        assert len(janelas) == 2 and all(j.tabs.count() == 1 for j in janelas.values())
        assert w.tabs.count() == 1          # só o banco de dados: nada abriu na janela principal
    finally:
        mp.undo()
        for j in janelas.values():
            j.close()


# --------------------------------------------------------------------- abertura


def test_abre_maximizada_por_padrao(env):
    """Pedido dele: o programa abre maximizado, sem ele arrastar a janela todo dia."""
    w = _janela(env)
    w.show_on_configured_screen()
    assert w.windowState() & Qt.WindowMaximized
    assert w.abre_maximizada()


def test_da_para_desligar_a_abertura_maximizada(env):
    w = _janela(env)
    w.settings.set("ui.start_maximized", False)
    w.show_on_configured_screen()
    assert not (w.windowState() & Qt.WindowMaximized)


def test_a_caixa_das_preferencias_guarda_a_escolha(tmp_path):
    from ipe.core.config import Settings
    from ipe.ui import preferences as P
    QApplication.instance() or QApplication([])
    st = Settings(tmp_path / "s.json")
    dlg = P.PreferencesDialog(st)
    assert dlg.c_maximizada.isChecked()          # padrão de fábrica
    dlg.c_maximizada.setChecked(False)
    dlg._save()
    dlg.close()
    assert st.get("ui.start_maximized") is False
