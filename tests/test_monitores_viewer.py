"""Vários monitores com papel "viewer": o exame se divide entre eles, e cada um é uma estação.

O que o usuário relatou: dois monitores marcados como viewer, e o exame abrindo só no primeiro.
Era `screen_with_role` devolvendo **a primeira** tela — "o monitor viewer" em vez de "os monitores
viewer".
"""

import pytest
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer


@pytest.fixture()
def win(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1200, 800)
    w.show_on_configured_screen()
    w.browser.refresh()
    yield app, w
    w.close()


class _Tela:
    """Tela de mentira: só o que `abrir_dividido` pergunta. A janela de verdade abre na real."""

    def __init__(self, nome):
        self._nome = nome

    def name(self):
        return self._nome


def _dois_monitores(w, monkeypatch, layouts=((1, 1), (1, 1))):
    """Faz o programa enxergar dois monitores viewer, com janelas de verdade na tela real."""
    from ipe.ui import main_window as MW
    telas = [_Tela("VIEWER-1"), _Tela("VIEWER-2")]
    monkeypatch.setattr(MW, "screens_with_role", lambda *a, **k: telas)
    monkeypatch.setattr(MW, "layout_for_screen",
                        lambda _s, tela: dict(zip(telas, layouts)).get(tela))
    real = QGuiApplication.primaryScreen()
    janelas = {}

    def janela(tela, restrito=False):
        chave = (tela, bool(restrito))
        if chave not in janelas:
            from ipe.ui.monitors import ScreenWindow
            j = ScreenWindow(w, real, restrito=restrito)
            j.screen_key = tela.name()
            w.detached.append(j)
            janelas[chave] = j
        return janelas[chave]

    monkeypatch.setattr(w, "window_for_screen", janela)
    return telas


def _exame_de_mamografia(w) -> str:
    from ipe.ui.viewer.viewer_tab import _image_series
    for linha in w.repo.search_studies():
        uid = linha.study_uid
        series = _image_series(w.repo.series_for_study(uid))
        if len(series) >= 4 and all((s.modality or "") == "MG" for s in series):
            return uid
    pytest.skip("nenhum exame de mamografia com quatro séries nos fantomas")


def _exame_sem_plano_de_monitores(w) -> str:
    """Exame que cai na divisão das séries na ordem: sem plano por monitor e sem mamografia."""
    from ipe.ui.viewer.hanging import plano_de_monitores
    from ipe.ui.viewer.viewer_tab import _image_series
    for linha in w.repo.search_studies():
        uid = linha.study_uid
        series = _image_series(w.repo.series_for_study(uid))
        mods = {s.modality for s in series if s.modality}
        info = w.repo.study_info(uid) or {}
        if "MG" in mods:                      # mamografia tem caminho próprio, nunca este
            continue
        from ipe.ui.viewer.etapas import achar
        if achar(w.settings, mods, info.get("description", "")) is not None:
            continue                          # 0.88: protocolo com etapas reparte do jeito dele
        if len(series) >= 2 and plano_de_monitores(w.settings, mods, info.get("description", ""), 2) is None:
            return uid
    pytest.skip("todos os fantomas têm plano por monitor")


def _um_exame_com_varias_series(w) -> str:
    from ipe.ui.viewer.viewer_tab import _image_series
    from ipe.ui.viewer.etapas import achar
    for linha in w.repo.search_studies():
        uid = linha.study_uid
        series = _image_series(w.repo.series_for_study(uid))
        info = w.repo.study_info(uid) or {}
        mods = {x.modality for x in series if x.modality}
        if achar(w.settings, mods, info.get("description", "")) is not None:
            continue          # 0.88: com etapas, a sincronia é a que o protocolo marcou
        if len(series) >= 2:
            return uid
    pytest.skip("nenhum exame de teste com duas séries de imagem")


# ------------------------------------------------------------------ a divisão
def test_reparte_em_ordem_e_o_mais_igual_possivel():
    from ipe.ui.main_window import MainWindow as M
    assert M.repartir([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]
    assert M.repartir([1, 2, 3, 4, 5], 2) == [[1, 2, 3], [4, 5]]
    assert M.repartir([1], 2) == [[1], []]
    assert M.repartir([1, 2, 3], 3) == [[1], [2], [3]]
    assert M.repartir([], 2) == [[], []]


def test_dois_monitores_viewer_dividem_o_exame(win, monkeypatch):
    """Sem protocolo para duas telas, as séries se repartem na ordem."""
    app, w = win
    _dois_monitores(w, monkeypatch)
    uid = _exame_sem_plano_de_monitores(w)
    w.open_study(uid)
    assert len(w.detached) == 2, "o exame tem que abrir nos dois monitores"
    abas = [t for d in w.detached for t in d.viewer_tabs()]
    assert len(abas) == 2 and all(t.study_uid == uid for t in abas)
    a, b = (set(t.series_filter or []) for t in abas)
    assert a and b and not (a & b)               # partes diferentes, sem repetir
    from ipe.ui.viewer.viewer_tab import _image_series
    todas = {s.series_uid for s in _image_series(w.repo.series_for_study(uid))}
    assert a | b == todas                        # e nada fica de fora


def test_cada_monitor_recebe_o_layout_configurado_nele(win, monkeypatch):
    """Cada aba nasce com o layout do seu monitor.

    O teste confere o que **este** código decide — o layout entregue a cada aba —, e não o que
    ela faz com ele: em mamografia o protocolo de hanging manda, e isso é regra antiga da casa.
    """
    app, w = win
    _dois_monitores(w, monkeypatch, layouts=((1, 1), (2, 2)))
    pedidos = []
    original = w._make_tab

    def espiao(uid, layout=None, series=None, plano=None, mg_monitor=None, mg_telas=1,
               monitor_idx=0):
        pedidos.append(layout)
        return original(uid, layout, series, plano, mg_monitor, mg_telas, monitor_idx)

    monkeypatch.setattr(w, "_make_tab", espiao)
    w.open_study(_exame_sem_plano_de_monitores(w))
    assert pedidos == [(1, 1), (2, 2)]


def test_fechar_uma_parte_fecha_a_outra(win, monkeypatch):
    """Meio exame aberto num monitor e nada no outro é pior do que não ter aberto."""
    app, w = win
    _dois_monitores(w, monkeypatch)
    w.open_study(_um_exame_com_varias_series(w))
    primeira = w.detached[0].viewer_tabs()[0]
    w.fechar_aba(primeira)
    app.processEvents()
    assert not [t for d in w.detached for t in d.viewer_tabs()]


def test_um_monitor_so_continua_como_antes(win, monkeypatch):
    app, w = win
    from ipe.ui import main_window as MW
    monkeypatch.setattr(MW, "screens_with_role", lambda *a, **k: [])
    w.open_study(_um_exame_com_varias_series(w))
    assert not w.detached                        # sem monitor viewer, fica na janela principal


def test_exame_de_uma_serie_so_nao_se_divide(win, monkeypatch):
    app, w = win
    telas = _dois_monitores(w, monkeypatch)
    uid = _um_exame_com_varias_series(w)
    from ipe.ui.viewer.viewer_tab import _image_series
    uma = [_image_series(w.repo.series_for_study(uid))[0].series_uid]
    assert w.abrir_dividido(uid, telas, uma) is False


# --------------------------------------------------------- a janela do monitor
def test_a_janela_do_monitor_tem_a_barra_de_menu_inteira(win):
    app, w = win
    j = w.window_for_screen(QGuiApplication.primaryScreen())
    titulos = [a.text() for a in j.menuBar().actions()]
    for esperado in ("&Arquivo", "&Exibir", "&Rede", "&Usuário", "A&juda"):
        assert esperado in titulos, f"faltou o menu {esperado} na janela do monitor"
    assert any("Voltar estudos" in t for t in titulos)
    assert j.statusBar() is not None


def test_a_janela_ativa_e_quem_da_o_contexto(win, monkeypatch):
    """Quem manda a ação é a janela em que o médico está — o efeito é que vale para todas.

    A distinção importa para o que **não** é do conjunto: exportar, mover o estudo de monitor,
    mostrar o estado. Essas olham `aba_atual`.
    """
    app, w = win
    _dois_monitores(w, monkeypatch)
    w.open_study(_um_exame_com_varias_series(w))
    segunda_janela = w.detached[1]
    alvo = segunda_janela.viewer_tabs()[0]
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: segunda_janela))
    assert w.janela_ativa() is segunda_janela
    assert w.aba_atual() is alvo
    assert w.janela_da_aba(alvo) is segunda_janela


def test_o_status_aparece_no_monitor_em_que_aconteceu(win, monkeypatch):
    app, w = win
    _dois_monitores(w, monkeypatch)
    w.open_study(_um_exame_com_varias_series(w))
    aba = w.detached[1].viewer_tabs()[0]
    w.mostrar_status("mensagem de teste", aba)
    assert w.detached[1].statusBar().currentMessage() == "mensagem de teste"
    assert w.statusBar().currentMessage() != "mensagem de teste"


# ------------------------------------- os monitores agem como uma estação só
def test_o_menu_vale_para_todos_os_monitores(win, monkeypatch):
    """Dois monitores viewer são uma estação, não duas: o layout do menu vale para o conjunto."""
    app, w = win
    _dois_monitores(w, monkeypatch)
    w.open_study(_um_exame_com_varias_series(w))
    abas = [t for d in w.detached for t in d.viewer_tabs()]
    assert len(abas) == 2
    monkeypatch.setattr(QApplication, "activeWindow", staticmethod(lambda: w.detached[0]))
    w._current_viewer_call(lambda t: t.set_layout(2, 1))
    assert [t._layout for t in abas] == [(2, 1), (2, 1)]


def test_aba_sozinha_nao_arrasta_ninguem(win, monkeypatch):
    app, w = win
    from ipe.ui import main_window as MW
    monkeypatch.setattr(MW, "screens_with_role", lambda *a, **k: [])
    w.open_study(_um_exame_com_varias_series(w))
    tab = w.tabs.currentWidget()
    assert w.abas_do_conjunto(tab) == [tab]


# ------------------------------------------- protocolo por número de telas
def test_a_etapa_e_uma_so_e_se_reparte_entre_as_telas():
    """A etapa é do conjunto, não do monitor.

    O usuário foi explícito: "as etapas são únicas, não variam por monitor… todo o sistema
    funciona como um só". O que varia é o pedaço da etapa que cabe a cada tela.
    """
    from ipe.imaging.mammo import MG_PROTOCOL, passos_do_protocolo, quadro_da_etapa
    passos = passos_do_protocolo(MG_PROTOCOL)
    assert [p["name"] for p in passos][:3] == ["4 incidências", "CC", "MLO"]
    quatro = passos[0]
    # uma tela: a etapa inteira
    assert quadro_da_etapa(quatro, 1, 0)["cells"] == ["CCD", "CCE", "MLOD", "MLOE"]
    # duas telas: as CC numa, as MLO na outra — a repartição que o radiologista faria
    assert [quadro_da_etapa(quatro, 2, i)["cells"] for i in range(2)] == \
        [["CCD", "CCE"], ["MLOD", "MLOE"]]
    # quatro telas: uma incidência em cada
    assert [quadro_da_etapa(quatro, 4, i)["cells"] for i in range(4)] == \
        [["CCD"], ["CCE"], ["MLOD"], ["MLOE"]]
    # nenhuma tela fica em branco quando há menos imagens que telas
    cc = passos[1]
    assert all(quadro_da_etapa(cc, 4, i)["cells"] != [""] for i in range(4))


def test_a_etapa_diz_o_que_vai_em_cada_tela_quando_o_medico_define():
    """O que o médico escreve na etapa manda sobre a repartição automática."""
    from ipe.imaging.mammo import quadro_da_etapa
    etapa = {"name": "x", "rows": 2, "cols": 2, "cells": ["CCD", "CCE", "MLOD", "MLOE"],
             "telas": {"2": [{"rows": 2, "cols": 1, "cells": ["CCD", "MLOD"]},
                             {"rows": 2, "cols": 1, "cells": ["CCE", "MLOE"]}]}}
    assert [quadro_da_etapa(etapa, 2, i)["cells"] for i in range(2)] == \
        [["CCD", "MLOD"], ["CCE", "MLOE"]]
    assert quadro_da_etapa(etapa, 2, 0)["cols"] == 1
    # o que não foi definido continua repartido automaticamente
    assert [quadro_da_etapa(etapa, 4, i)["cells"] for i in range(4)] == \
        [["CCD"], ["CCE"], ["MLOD"], ["MLOE"]]


def test_protocolo_gravado_em_formato_antigo_continua_valendo():
    from ipe.imaging.mammo import passos_do_protocolo
    passos = [{"name": "A", "rows": 1, "cols": 2, "cells": ["CCD", "CCE"]}]
    assert [p["name"] for p in passos_do_protocolo({"steps": passos})] == ["A"]
    # o formato intermediário que chegou a ter etapas por monitor
    por_monitor = {"telas": {"1": [{"nome": "Monitor 1", "steps": passos}],
                             "2": [{"nome": "Monitor 1", "steps": []},
                                   {"nome": "Monitor 2", "steps": []}]}}
    assert [p["name"] for p in passos_do_protocolo(por_monitor)] == ["A"]
    assert passos_do_protocolo({}) == []


def test_mamografia_nao_usa_o_protocolo_de_exibicao(env):
    """Dois lugares decidindo o mesmo arranjo foi o que matou o modo mamografia duas vezes."""
    from ipe.ui.viewer.hanging import DEFAULT_PROTOCOLS, find_protocol, plano_de_monitores
    cfg = Settings(env[0].settings_file)
    assert not [p for p in DEFAULT_PROTOCOLS if p["modality"].upper() == "MG"]
    assert find_protocol(cfg, {"MG"}, "MAMOGRAFIA") is None
    for quantos in (1, 2, 3, 4):
        assert plano_de_monitores(cfg, {"MG"}, "", quantos) is None
    # e protocolo MG gravado por versão antiga também é ignorado
    cfg.set("hanging_protocols", [{"name": "velho", "modality": "MG", "description": "", "enabled": True,
                                   "layout": [2, 2], "cells": ["R CC", "L CC", "R MLO", "L MLO"],
                                   "monitores": {"2": [{"layout": [1, 2], "cells": ["R CC", "L CC"]},
                                                       {"layout": [1, 2], "cells": ["R MLO", "L MLO"]}]}}])
    assert find_protocol(cfg, {"MG"}, "MAMOGRAFIA") is None
    assert plano_de_monitores(cfg, {"MG"}, "", 2) is None


def test_o_plano_por_monitor_continua_para_as_outras_modalidades(env):
    from ipe.ui.viewer.hanging import plano_de_monitores
    cfg = Settings(env[0].settings_file)
    cfg.set("hanging_protocols", [{"name": "TC tórax", "modality": "CT", "description": "", "enabled": True,
                                   "layout": [1, 1], "cells": ["▦"],
                                   "monitores": {"2": [{"layout": [1, 1], "cells": ["A"]},
                                                       {"layout": [1, 1], "cells": ["B"]}]}}])
    assert len(plano_de_monitores(cfg, {"CT"}, "", 2)) == 2
    assert plano_de_monitores(cfg, {"CT"}, "", 3) is None       # não inventa plano


def test_com_dois_monitores_a_mamografia_roda_o_protocolo_inteiro(win, monkeypatch):
    """Com dois monitores, o modo mamografia sobe nas duas telas — e elas são **uma estação**.

    Mesma etapa nas duas, pedaços diferentes dela: as CC numa, as MLO na outra.
    """
    app, w = win
    _dois_monitores(w, monkeypatch)
    w.open_study(_exame_de_mamografia(w))
    abas = [t for d in w.detached for t in d.viewer_tabs()]
    assert len(abas) == 2
    assert all(t.mg_session is not None for t in abas), "o modo mamografia tem que subir nas duas"
    nomes = {t.mg_session.steps[t.mg_session.step].get("name") for t in abas}
    assert len(nomes) == 1, "a etapa é a mesma nas duas telas"
    assert [t.mg_monitor for t in abas] == [0, 1] and all(t.mg_telas == 2 for t in abas)
    from ipe.imaging.mammo import quadro_da_etapa
    celulas = [quadro_da_etapa(t.mg_session.steps[t.mg_session.step], 2, t.mg_monitor)["cells"]
               for t in abas]
    assert celulas == [["CCD", "CCE"], ["MLOD", "MLOE"]]
    assert all(any(v.series_uid for v in t.viewports) for t in abas)
    # e a tira continua com o exame inteiro: dá para trocar o que está num quadro
    assert all(t.series_filter is None for t in abas)


def test_passar_de_etapa_num_monitor_passa_em_todos(win, monkeypatch):
    """"Todo o sistema funciona como um só": a etapa é estado da estação, não da tela."""
    app, w = win
    _dois_monitores(w, monkeypatch)
    w.open_study(_exame_de_mamografia(w))
    a, b = [t for d in w.detached for t in d.viewer_tabs()]
    assert a.mg_session.step == b.mg_session.step == 0
    a.mg_next(1)
    assert a.mg_session.step == 1 and b.mg_session.step == 1
    b.mg_next(1)                                   # e vale nos dois sentidos
    assert a.mg_session.step == 2 and b.mg_session.step == 2
    b.mg_step(0)
    assert a.mg_session.step == 0 and b.mg_session.step == 0


def test_trocar_de_protocolo_num_monitor_troca_em_todos(win, monkeypatch):
    app, w = win
    _dois_monitores(w, monkeypatch)
    w.open_study(_exame_de_mamografia(w))
    a, b = [t for d in w.detached for t in d.viewer_tabs()]
    from ipe.imaging.mammo import mg_protocols
    outro = mg_protocols(w.settings)[0]            # o CEM, que não é o que combinou sozinho
    a.start_mg(outro)
    assert a.mg_session.proto.get("name") == outro["name"]
    assert b.mg_session.proto.get("name") == outro["name"]


def test_os_monitores_do_conjunto_ficam_ligados(win, monkeypatch):
    """"Agir como se fosse um": rolagem, janela e zoom andam juntos entre as telas."""
    app, w = win
    _dois_monitores(w, monkeypatch)
    w.open_study(_um_exame_com_varias_series(w))
    abas = [t for d in w.detached for t in d.viewer_tabs()]
    quadros = [v for t in abas for v in t._shown() if v.frames]
    grupos = {w.sync_hub.group_of(v) for v in quadros}
    assert grupos == {1}, "todos os quadros das duas telas no mesmo grupo"
    assert w.sync_hub.sync_wl and w.sync_hub.sync_zoom
    assert all(t in w.sync_hub.tabs for t in abas)


def test_dá_para_desligar_a_ligação_entre_monitores(win, monkeypatch):
    app, w = win
    w.settings.set("monitors.sync_group", False)
    _dois_monitores(w, monkeypatch)
    w.open_study(_um_exame_com_varias_series(w))
    abas = [t for d in w.detached for t in d.viewer_tabs()]
    quadros = [v for t in abas for v in t._shown() if v.frames]
    assert all(w.sync_hub.group_of(v) is None for v in quadros)


# ------------------------------------------------- o monitor do banco de dados
def test_a_janela_principal_sai_dos_monitores_de_viewer(win, monkeypatch):
    """O exame aparecia no monitor do banco porque a janela principal estava num viewer."""
    from ipe.ui import monitors as M
    app, w = win

    class _T:
        def __init__(self, nome):
            self._n = nome

        def name(self):
            return self._n
        model = lambda self: ""          # noqa: E731
        serialNumber = lambda self: ""   # noqa: E731

    a, b, c = _T("A"), _T("B"), _T("C")
    monkeypatch.setattr(M.QGuiApplication, "screens", staticmethod(lambda: [a, b, c]))
    cfg = w.settings
    cfg.set("monitors", {"A": {"role": "viewer"}, "B": {"role": "viewer"}, "C": {"role": "off"}})
    assert M.tela_da_janela_principal(cfg) is c or M.tela_da_janela_principal(cfg) is not None
    cfg.set("monitors", {"A": {"role": "viewer"}, "B": {"role": "browser"}, "C": {"role": "off"}})
    assert M.tela_da_janela_principal(cfg) is b          # o papel explícito manda
    cfg.set("monitors", {"A": {"role": "viewer"}, "B": {}, "C": {"role": "off"}})
    assert M.tela_da_janela_principal(cfg) is b          # sem papel vale mais que "Não usar"
    assert M.screens_with_role(cfg, "viewer") == [a]


def test_monitor_viewer_continua_viewer_mesmo_com_a_principal_nele(win, monkeypatch):
    """Antes, `exclude` tirava da lista o monitor em que a janela principal estava."""
    from ipe.ui import monitors as M
    app, w = win
    real = QGuiApplication.primaryScreen()
    key = M.screen_key(real)
    w.settings.set("monitors", {key: {"role": "viewer"}})
    assert M.screens_with_role(w.settings, "viewer") == [real]


def test_trocar_o_layout_nao_desfaz_a_ligacao(win, monkeypatch):
    """Quadro novo numa tela entra na ligação — senão a sincronia sumia sem avisar."""
    app, w = win
    _dois_monitores(w, monkeypatch)
    w.open_study(_um_exame_com_varias_series(w))
    abas = [t for d in w.detached for t in d.viewer_tabs()]
    abas[0].set_layout(2, 2)
    quadros = [v for t in abas for v in t._shown() if v.frames]
    assert quadros and all(w.sync_hub.group_of(v) == 1 for v in quadros)


# ------------------------------------------- o que se escolhe num monitor vale nos outros
def test_a_funcao_do_mouse_vale_nos_dois_monitores(win, monkeypatch):
    """"Selecionei os botões do mouse em um monitor, mas isso não funcionou no outro."

    A ferramenta do botão esquerdo era estado **da aba**: cada monitor tinha a sua, e trocar
    numa não dizia nada à outra.
    """
    app, w = win
    _dois_monitores(w, monkeypatch)
    w.open_study(_um_exame_com_varias_series(w))
    a, b = [t for d in w.detached for t in d.viewer_tabs()]
    a.set_left_tool("pan")
    assert b.left_tool == "pan"
    assert all(v.left_tool == "pan" for v in b.viewports)
    b.set_left_tool("zoom")                      # e vale nos dois sentidos
    assert a.left_tool == "zoom"
    a.set_button_tool("right", "measure")
    assert (w.settings.get("viewer.mouse", {}) or {}).get("right") == "measure"


def test_aba_sozinha_nao_tenta_propagar(win, monkeypatch):
    app, w = win
    from ipe.ui import main_window as MW
    monkeypatch.setattr(MW, "screens_with_role", lambda *a, **k: [])
    w.open_study(_um_exame_com_varias_series(w))
    tab = w.tabs.currentWidget()
    assert tab.irmaos() == []
    tab.set_left_tool("pan")                     # não pode explodir sem grupo
    assert tab.left_tool == "pan"


# ------------------------------------------- o botão X
def test_o_x_fecha_o_exame_em_todos_os_monitores(win, monkeypatch):
    """"Fecho pelo X e ele não fecha o programa, só a tela, e mantém as outras abertas."

    Com exame aberto o X fecha o exame **em todas as telas** e devolve o banco de dados.
    """
    app, w = win
    _dois_monitores(w, monkeypatch)
    w.open_study(_um_exame_com_varias_series(w))
    assert len(w.detached) == 2
    w.detached[0].close()                        # o X de um monitor
    app.processEvents()
    assert w.all_viewer_tabs() == []
    assert w.detached == []                      # nenhuma janela de monitor sobrou
    assert w.isVisible()                         # e o banco de dados está de volta


def test_o_x_da_janela_principal_tambem_fecha_o_exame(win, monkeypatch):
    app, w = win
    _dois_monitores(w, monkeypatch)
    w.open_study(_um_exame_com_varias_series(w))
    w.close()                                    # o X do banco de dados
    app.processEvents()
    assert w.all_viewer_tabs() == [] and w.detached == []
    assert w.isVisible(), "o programa não pode encerrar enquanto havia exame aberto"


def test_sem_exame_aberto_o_x_nao_tem_o_que_fechar(win, monkeypatch):
    """Sem exame aberto não há o que devolver: o X segue o caminho de encerrar o programa."""
    app, w = win
    assert w.all_viewer_tabs() == []
    assert w.fechar_exames_e_voltar_ao_banco() is False


def test_o_arranjo_aparece_nas_duas_telas(win, monkeypatch):
    """Arranjo que não se anuncia é indistinguível de arranjo que não aconteceu.

    Foi o que fez a mamografia parecer quebrada três vezes: nada na tela dizia qual caminho o
    programa tinha tomado.
    """
    app, w = win
    _dois_monitores(w, monkeypatch)
    w.open_study(_exame_de_mamografia(w))
    msgs = [d.statusBar().currentMessage() for d in w.detached]
    assert len(msgs) == 2 and all("2 monitores" in m for m in msgs)
    assert all("Monitor 1:" in m and "Monitor 2:" in m for m in msgs)
    resumo = w.resumo_do_arranjo([t for d in w.detached for t in d.viewer_tabs()])
    assert "CC" in resumo and "MLO" in resumo


# ------------------------------------------------------------------ a tira entre as mamas
def test_a_tira_some_nas_telas_de_dentro_na_mamografia(win, monkeypatch):
    """Com dois monitores, a tira ficava na borda de dentro do segundo — entre as duas mamas."""
    app, w = win
    _dois_monitores(w, monkeypatch)
    w.open_study(_exame_de_mamografia(w))
    app.processEvents()
    abas = w.all_viewer_tabs()
    assert len(abas) == 2
    assert abas[0].monitor_idx == 0 and abas[1].monitor_idx == 1
    assert not abas[1].strip.isVisibleTo(abas[1]), "na tela de dentro a tira some"
    assert not abas[1].strip_action.isChecked(), "e o menu mostra o estado"
    abas[1].strip_action.setChecked(True)            # modo manual: dá para trazer de volta
    assert abas[1].strip.isVisibleTo(abas[1])


def test_fora_da_mamografia_a_tira_fica_por_padrao(win, monkeypatch):
    app, w = win
    _dois_monitores(w, monkeypatch)
    w.open_study(_exame_sem_plano_de_monitores(w))
    app.processEvents()
    abas = w.all_viewer_tabs()
    assert len(abas) == 2 and all(t.strip_action.isChecked() for t in abas)


def test_a_opcao_sempre_vale_para_qualquer_exame(win, monkeypatch):
    app, w = win
    w.settings.set("viewer.tira_repartida", "sempre")
    _dois_monitores(w, monkeypatch)
    w.open_study(_exame_sem_plano_de_monitores(w))
    app.processEvents()
    abas = w.all_viewer_tabs()
    assert abas[0].strip_action.isChecked() and not abas[1].strip_action.isChecked()
    w.settings.set("viewer.tira_repartida", "mamografia")
