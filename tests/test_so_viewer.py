"""Chamada externa no modo "só visualizador": o exame abre, o banco de dados não aparece.

Pedido dele: "há possibilidade de uma opção de fazer a chamada e abrir somente o visualizador?
Sem abrir o banco de dados? Se o usuário não abrir o programa ele acaba nem sabendo o que tem no
banco de dados." A escolha foi a forte: o banco não fica só escondido, fica **fora de alcance**.
"""
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer


@pytest.fixture()
def janela(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    st = Settings(paths.settings_file)
    st.set("dicom", {**(st.get("dicom", {}) or {}), "external_viewer_only": True})
    w = MainWindow(paths, st)
    w.browser.refresh()
    yield app, w
    for j in list(w.detached):
        j._devolvendo = True
        j.close()
    w.close()


def _acc(w) -> str:
    return next(r.accession for r in w.repo.search_studies() if r.accession)


def test_abre_sem_mostrar_o_banco(janela):
    app, w = janela
    assert w.so_viewer_externo()
    assert w.handle_external({"command": "open", "accession": _acc(w), "source": "http:127.0.0.1"}) == "aberto"
    app.processEvents()
    assert not w.isVisible(), "a janela do banco de dados apareceu"
    assert w.detached and w.detached[0].restrito
    assert w.detached[0].tabs.count() == 1


def test_a_janela_restrita_nao_tem_caminho_para_o_banco(janela):
    app, w = janela
    w.handle_external({"command": "open", "accession": _acc(w), "source": "link"})
    app.processEvents()
    jan = w.detached[0]
    menus = [a.text().replace("&", "") for a in jan.menuBar().actions()]
    assert "Arquivo" not in menus, "o menu Arquivo abre importação e exportação"
    assert "Rede" not in menus, "o menu Rede leva à busca no PACS"
    assert menus == ["Exibir", "Usuário", "Ajuda"], menus
    exibir = next(a.menu() for a in jan.menuBar().actions() if a.text().replace("&", "") == "Exibir")
    itens = [a.text() for a in exibir.actions() if not a.isSeparator()]
    assert "Voltar ao banco de dados" not in itens
    assert "Layout dos quadros" in itens


def test_fechar_deixa_na_bandeja_e_nao_abre_o_banco(janela, monkeypatch):
    app, w = janela
    w.handle_element = None
    w.handle_external({"command": "open", "accession": _acc(w), "source": "cli"})
    app.processEvents()
    jan = w.detached[0]
    jan.close()
    app.processEvents()
    assert not w.isVisible(), "fechar o exame trouxe o banco de dados para a tela"
    assert jan not in w.detached
    # a próxima chamada abre de novo, numa janela nova
    w.handle_external({"command": "open", "accession": _acc(w), "source": "cli"})
    app.processEvents()
    assert w.detached and w.detached[0].restrito and not w.isVisible()


def test_sem_a_opcao_tudo_continua_como_era(env, sample_dir):
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    w.browser.refresh()
    assert not w.so_viewer_externo()
    acc = next(r.accession for r in w.repo.search_studies() if r.accession)
    assert w.handle_external({"command": "open", "accession": acc, "source": "cli"}) == "aberto"
    app.processEvents()
    assert w.isVisible() and w.tabs.count() >= 2, "o modo normal tem de continuar abrindo em aba"
    w.close()


def test_a_caixa_esta_na_tela_de_rede(env):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    from ipe.ui.main_window import MainWindow
    from ipe.ui.network_dialog import NetworkDialog
    w = MainWindow(paths, Settings(paths.settings_file))
    dlg = NetworkDialog(w.settings, w.repo, w.net, w)
    assert hasattr(dlg, "so_viewer") and not dlg.so_viewer.isChecked()
    dlg.so_viewer.setChecked(True)
    dlg._save()
    assert (w.settings.get("dicom", {}) or {}).get("external_viewer_only") is True
    dlg.close()
    w.close()


def test_a_janela_restrita_nao_exporta(janela):
    """Ver o exame não é levar o exame embora."""
    app, w = janela
    w.handle_external({"command": "open", "accession": _acc(w), "source": "http:10.0.0.9"})
    app.processEvents()
    tab = w.detached[0].tabs.widget(0)
    exportar = tab.actions_by_id.get("study.export")
    assert exportar is not None and not exportar.isVisible() and not exportar.isEnabled()
    assert all(not a.isEnabled() for a in tab.acoes_de_saida)


def test_no_modo_normal_a_exportacao_continua(env, sample_dir):
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    w.browser.refresh()
    w.open_study(repo.search_studies()[0].study_uid)
    app.processEvents()
    tab = w.all_viewer_tabs()[-1]
    assert tab.actions_by_id["study.export"].isEnabled()
    w.close()


# ------------------------------------------------------------------ parâmetro da chamada

def test_o_parametro_manda_sobre_a_configuracao(env, sample_dir):
    """A configuração é o padrão; a chamada pode pedir o contrário, nos dois sentidos."""
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    w.browser.refresh()
    acc = next(r.accession for r in repo.search_studies() if r.accession)
    # padrão (programa inteiro) + pedido de só visualizador
    assert not w.so_viewer_externo()
    assert w.so_viewer_do_pedido({"janela": "viewer"})
    w.handle_external({"command": "open", "accession": acc, "janela": "viewer", "source": "link"})
    app.processEvents()
    assert w.detached and w.detached[0].restrito
    assert w.tabs.count() == 1, "abriu aba no banco apesar do janela=viewer"
    for j in list(w.detached):
        j._devolvendo = True
        j.close()
    # padrão invertido + pedido de programa inteiro
    w.settings.set("dicom", {**(w.settings.get("dicom", {}) or {}), "external_viewer_only": True})
    assert w.so_viewer_externo() and not w.so_viewer_do_pedido({"janela": "completo"})
    w.close()


def test_valor_desconhecido_e_recusado_com_motivo():
    """Valor que o programa não entende não vira silêncio."""
    from ipe.network.external import ExternalError, parse_url, payload_from_query
    p = payload_from_query("open", {"accession": ["X1"], "janela": ["viewer"]})
    assert p["janela"] == "viewer"
    assert payload_from_query("open", {"accession": ["X1"], "modo": ["Visualizador"]})["janela"] == "viewer"
    assert payload_from_query("open", {"accession": ["X1"], "window": ["full"]})["janela"] == "completo"
    with pytest.raises(ExternalError) as e:
        payload_from_query("open", {"accession": ["X1"], "janela": ["minimizado"]})
    assert "viewer ou completo" in str(e.value)
    # pelo link, igual
    assert parse_url("dicomviewer://open?accession=X1&janela=viewer")["janela"] == "viewer"


def test_sem_o_parametro_vale_a_configuracao():
    from ipe.network.external import payload_from_query
    p = payload_from_query("open", {"accession": ["X1"]})
    assert "janela" not in p


# ------------------------------------------------------- vários monitores (defeito da 0.60)
def _dois_viewers(w, monkeypatch):
    """Dois monitores viewer, com janelas de verdade na tela real."""
    from PySide6.QtGui import QGuiApplication
    from ipe.ui import main_window as MW
    from ipe.ui.monitors import ScreenWindow

    class _Tela:
        def __init__(self, nome):
            self._nome = nome

        def name(self):
            return self._nome

        def geometry(self):
            return QGuiApplication.primaryScreen().geometry()

    telas = [_Tela("VIEWER-1"), _Tela("VIEWER-2")]
    monkeypatch.setattr(MW, "screens_with_role", lambda *a, **k: telas)
    monkeypatch.setattr(MW, "layout_for_screen", lambda _s, _tela: (1, 1))
    real = QGuiApplication.primaryScreen()
    feitas = {}

    def janela(tela, restrito=False):
        chave = (tela.name(), bool(restrito))
        if chave not in feitas:
            j = ScreenWindow(w, real, restrito=restrito)
            j.screen_key = tela.name()
            w.detached.append(j)
            feitas[chave] = j
        return feitas[chave]

    monkeypatch.setattr(w, "window_for_screen", janela)
    return telas


def test_a_chamada_externa_usa_todos_os_monitores_viewer(janela, monkeypatch):
    """O defeito: no modo só-visualizador o exame abria em `telas[0]` e o segundo monitor ficava
    vazio. Modo só-visualizador não é motivo para usar menos tela."""
    app, w = janela
    _dois_viewers(w, monkeypatch)
    assert w.handle_external({"command": "open", "accession": _acc(w)}) == "aberto"
    app.processEvents()
    restritas = [d for d in w.detached if d.restrito]
    assert len(restritas) == 2, f"abriu em {len(restritas)} janela(s) de visualização"
    for j in restritas:
        assert j.tabs.count() == 1, "monitor de visualização sem exame"
    abas = [j.tabs.widget(0) for j in restritas]
    assert all(t.monitor_group for t in abas), "as abas dos monitores não ficaram amarradas"
    assert {t.monitor_idx for t in abas} == {0, 1}
    assert not w.isVisible(), "o banco de dados apareceu"


def test_fechar_um_monitor_fecha_o_conjunto(janela, monkeypatch):
    app, w = janela
    _dois_viewers(w, monkeypatch)
    assert w.handle_external({"command": "open", "accession": _acc(w)}) == "aberto"
    app.processEvents()
    restritas = [d for d in w.detached if d.restrito]
    assert len(restritas) == 2
    restritas[0].close()
    app.processEvents()
    assert not [d for d in w.detached if d.restrito], "sobrou janela de visualização aberta"
    assert all(not j.isVisible() for j in restritas), "exame aberto em metade das telas"
    assert not w.isVisible(), "o banco de dados apareceu ao fechar"
