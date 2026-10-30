"""0.99.12: menu Configurações (uma janela por item) e barra do visualizador por aplicação."""
import pytest
from PySide6.QtWidgets import QApplication, QGroupBox

from ipe.core.config import Settings
from ipe.importer.scanner import Importer
from ipe.ui import configuracoes as CFG
from ipe.ui.viewer import aplicacoes as AP


@pytest.fixture()
def janela(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    from ipe.ui.viewer import hanging as H
    s = Settings(paths.settings_file)
    s.set("hanging_protocols", [dict(p, enabled=False) for p in H.DEFAULT_PROTOCOLS])
    s.set("hanging_fabrica", H.FABRICA_VERSAO)
    w = MainWindow(paths, s)
    w.resize(1400, 800)
    w.show()
    w.browser.refresh()
    yield app, w
    w.close()


def _menus(w):
    return {a.text().replace("&", ""): a.menu() for a in w.menuBar().actions() if a.menu() is not None}


def _abrir(w, app, acc):
    assert w.handle_external({"accession": acc}) == "aberto"
    app.processEvents()
    return w.tabs.currentWidget()


# ------------------------------------------------------------------ 1. menu Configurações
def test_menu_configuracoes_tem_um_submenu_por_assunto(janela):
    app, w = janela
    conf = _menus(w)["Configurações"]
    subs = [a.text() for a in conf.actions() if a.menu() is not None]
    assert subs == ["Visualizador", "Protocolos de exame", "CAD/IA", "Monitores", "Rede", "Impressão",
                    "Banco de dados", "Usuários", "Sistema"]
    todas = [a for a in conf.actions() if a.text().startswith("Todas as preferências")]
    assert len(todas) == 1 and todas[0].shortcut().toString() == "Ctrl+,"


def test_todo_item_tem_destino(janela):
    app, w = janela
    from ipe.ui.preferences import PAGINAS
    for _sub, texto, alvo in CFG.itens():
        if isinstance(alvo, str) and alvo.startswith("p:"):
            assert alvo[2:] in PAGINAS, texto
        elif isinstance(alvo, str) and alvo.startswith("f:"):
            assert callable(getattr(w, alvo[2:], None)), texto
        else:
            assert callable(alvo), texto


def test_configuracoes_sairam_dos_menus_de_acao(janela):
    """Os menus de ação ficam só com ações; o que se configura continua alcançável — aqui."""
    app, w = janela
    m = _menus(w)
    textos = {nome: [a.text() for a in menu.actions()] for nome, menu in m.items() if nome != "Configurações"}
    w._fill_user_menu(m["Usuário"])
    textos["Usuário"] = [a.text() for a in m["Usuário"].actions()]
    saiu = ["Preferências…", "Calibração GSDF do monitor…", "Configurar nós DICOM…",
            "Configurações de impressão…", "Usuários e permissões…",
            "Instalar a segmentação de órgãos (TotalSegmentator)…"]
    for nome, lista in textos.items():
        for t in saiu:
            assert t not in lista, f"{t} ainda em {nome}"
    conf_textos = [texto for _s, texto, _a in CFG.itens()]
    for t in ("Calibração GSDF do monitor…", "Nós DICOM (PACS, estações)…", "Usuários e permissões…",
              "Instalar a segmentação de órgãos (TotalSegmentator)…", "Mamografia…", "Módulos…"):
        assert t in conf_textos


def test_botao_configuracoes_da_tela_inicial_usa_o_mesmo_menu(janela):
    app, w = janela
    from PySide6.QtWidgets import QMenu
    m = QMenu()
    w.home_bar._settings_menu(m)
    assert [a.text() for a in m.actions() if a.menu() is not None][0] == "Visualizador"


# ------------------------------------------------------------------ 2. janela de um item só
def test_pagina_sozinha_mostra_so_a_secao(env):
    QApplication.instance() or QApplication([])
    paths, _db, _repo = env
    s = Settings(paths.settings_file)
    from ipe.ui.preferences import PreferencesDialog
    d = PreferencesDialog(s, pagina="aparencia")
    assert d.windowTitle() == "Configurações — Texto e marcas sobre a imagem"
    assert not d.tabs.tabBar().isVisibleTo(d)
    visiveis = [g.title() for g in d.tabs.currentWidget().findChildren(QGroupBox) if g.isVisibleTo(d)]
    assert visiveis == ["Texto e marcas sobre a imagem"]
    from PySide6.QtWidgets import QDialogButtonBox
    assert not d.findChild(QDialogButtonBox).button(QDialogButtonBox.RestoreDefaults).isVisibleTo(d)


def test_salvar_uma_pagina_nao_mexe_nas_outras(env):
    QApplication.instance() or QApplication([])
    paths, _db, _repo = env
    s = Settings(paths.settings_file)
    s.set("shortcuts", dict(s.get("shortcuts", {}) or {}, **{"view.fit": "F7"}))
    s.set("viewer.loupe_size", 333)
    from ipe.ui.preferences import PreferencesDialog
    d = PreferencesDialog(s, pagina="idioma")
    d._save()
    assert s.get("shortcuts")["view.fit"] == "F7" and s.get("viewer.loupe_size") == 333


def test_atalho_para_uma_aba_abre_so_a_pagina(janela, monkeypatch):
    app, w = janela
    abertas = []
    monkeypatch.setattr(type(w), "open_config", lambda self, p: abertas.append(p))
    w.open_preferences("Monitores")
    w.open_preferences("Anotações")
    assert abertas == ["monitores", "anotacoes"]


# ------------------------------------------------------------------ 3. regras
def test_regioes_e_tipos_pelo_texto():
    s = None
    pesc = AP.termos(AP.REGIOES_FABRICA["pescoco"][1])
    assert AP.casa("ANGIO TC DOS TRONCOS SUPRA-AÓRTICOS", pesc)
    assert AP.casa("Angio-RM de carótidas", pesc)
    memb = AP.termos(AP.REGIOES_FABRICA["membros"][1])
    assert not AP.casa("SELA TURCA / HIPÓFISE", memb)          # "HIP" não pega hipófise
    assert AP.casa("RM DO PÉ DIREITO", memb)

    class Ser:
        def __init__(self, mod, desc, n=60, bp=""):
            self.modality, self.description, self.num_images, self.body_part = mod, desc, n, bp
    ctx = AP.contexto([Ser("CT", "CTA 0.6 mm"), Ser("CT", "Axial")], [{"description": "ANGIOTC PESCOÇO"}], s)
    assert "pescoco" in ctx.regioes and {"angio", "volume"} <= ctx.tipos
    ctx = AP.contexto([Ser("MR", "Sag T1 MPRAGE", 176, "HEAD")], [{"description": "RM"}], s)
    assert "cranio" in ctx.regioes and "t1_3d" in ctx.tipos
    ctx = AP.contexto([Ser("MG", "L CC", 1)], [{"description": "EXAME"}], s)
    assert ctx.regioes == {"mama"}                               # mamografia é mama


def test_regra_da_dinamica_diz_o_motivo():
    ctx = AP.Contexto({"MR"}, {"cranio"}, {"volume"})
    vale, motivo = AP.avaliar(AP.APLICACOES["dinamica"], ctx)
    assert not vale and "Mama" in motivo and "dinâmica" in motivo
    assert AP.avaliar(AP.APLICACOES["dinamica"], AP.Contexto({"MR"}, {"mama"}, set()))[0]
    assert AP.avaliar(AP.APLICACOES["dinamica"], AP.Contexto({"MR"}, set(), {"dinamica"}))[0]
    assert not AP.avaliar(AP.APLICACOES["mn"], AP.Contexto({"CT"}, set(), set()))[0]


def test_modo_manual_e_excecao_por_regiao(env):
    paths, _db, _repo = env
    s = Settings(paths.settings_file)
    ctx = AP.Contexto({"CT"}, {"pescoco"}, {"volume"})
    assert AP.mostrar(s, "3d", ctx)[0]
    AP.definir_modo(s, "3d", "nunca")
    assert not AP.mostrar(s, "3d", ctx)[0]
    AP.definir_modo(s, "3d", "sempre", "pescoco")               # exceção: no pescoço, sempre
    assert AP.mostrar(s, "3d", ctx)[0]
    assert not AP.mostrar(s, "3d", AP.Contexto({"CT"}, {"torax"}, {"volume"}))[0]
    AP.definir_modo(s, "3d", "auto", "pescoco")
    AP.definir_modo(s, "3d", "auto")
    assert s.get("viewer.barra")["modos"] == {}


# ------------------------------------------------------------------ 4. a barra
def test_tc_mostra_3d_e_esconde_mn_e_dinamica(janela):
    app, w = janela
    tab = _abrir(w, app, "ACC1001")                              # TC de tórax
    assert tab.app_na_barra("3d") and tab.app_na_barra("mpr")
    assert not tab.app_na_barra("mn") and not tab.app_na_barra("dinamica")
    assert not tab.app_na_barra("fusao")


def test_rm_de_mama_mostra_a_dinamica(janela):
    app, w = janela
    tab = _abrir(w, app, "ACC2001")
    assert tab.app_na_barra("dinamica") and not tab.app_na_barra("mn")


def test_mn_mostra_o_botao_de_mn(janela):
    app, w = janela
    tab = _abrir(w, app, "ACC5001")
    assert tab.app_na_barra("mn")


def test_aplicacoes_ficam_num_bloco_antes_do_mais(janela):
    app, w = janela
    tab = _abrir(w, app, "ACC1001")
    acoes = tab.toolbar.actions()
    i_sep = acoes.index(tab._sep_apps)
    pos = {aid: acoes.index(par[1]) for aid, par in tab._apps.items()}
    assert all(p > i_sep for p in pos.values())
    ordem = [aid for aid in AP.ordem(w.settings) if aid in pos]
    assert sorted(pos, key=pos.get) == ordem


def test_todas_as_aplicacoes_lista_as_de_fora_com_motivo(janela):
    app, w = janela
    tab = _abrir(w, app, "ACC1001")
    tab._encher_todas_as_aplicacoes()
    textos = [a.text() for a in tab.todas_menu.actions()]
    assert any(t.startswith("Dinâmica — ") for t in textos), textos     # fora da barra, com motivo
    assert any(t.startswith("MN — ") for t in textos)
    assert all(a.isEnabled() for a in tab.todas_menu.actions() if a.text().startswith("Dinâmica"))


def test_botao_direito_esconde_e_traz_de_volta(janela):
    app, w = janela
    tab = _abrir(w, app, "ACC1001")
    menu = tab.menu_da_aplicacao("3d")
    textos = [a.text() for a in menu.actions()]
    assert "Nunca (só em Todas)" in textos and any(t.startswith("Regra:") for t in textos)
    nunca = next(a for a in menu.actions() if a.text() == "Nunca (só em Todas)")
    nunca.trigger()
    assert not tab.app_na_barra("3d")
    tab._definir_modo_da_aplicacao("3d", "auto", "*")
    assert tab.app_na_barra("3d")


# ------------------------------------------------------------------ 5. janela da barra
def test_janela_da_barra_grava_ordem_modos_e_regioes(env):
    QApplication.instance() or QApplication([])
    paths, _db, _repo = env
    s = Settings(paths.settings_file)
    from ipe.ui.viewer.barra_config import BarraDialog
    d = BarraDialog(s)
    d.t_apps.selectRow(1)
    d._mover(-1)
    primeira = d.ordem_na_tela()[0]
    d.t_apps.cellWidget(0, 2).setCurrentIndex(2)                 # nunca
    # região nova e uma de fábrica removida
    d._nova_regiao()
    r = d.t_reg.rowCount() - 1
    d.t_reg.item(r, 0).setText("Ombro")
    d.t_reg.item(r, 1).setText("OMBRO|SHOULDER")
    ids = [d.t_reg.item(i, 0).data(0x0100) for i in range(d.t_reg.rowCount())]
    d.t_reg.removeRow(ids.index("membros"))
    d.e_teste.setText("RM do ombro direito")
    assert "Ombro" in d.l_teste.text()
    d.save()
    assert AP.ordem(s)[0] == primeira
    assert AP.modo(s, primeira)[0] == "nunca"
    regs = AP.regioes(s)
    assert "membros" not in regs and regs["ombro"][0] == "Ombro"


def test_codec_ignora_campo_que_nao_conhece():
    from ipe.central import codec
    from ipe.db.repository import SeriesRow
    dado = {"__dc__": "SeriesRow", "f": {"series_uid": "1", "study_uid": "2", "modality": "CT",
                                          "series_number": 1, "description": "", "num_images": 3,
                                          "thumbnail": None, "campo_do_futuro": 7}}
    linha = codec.decode(dado)
    assert isinstance(linha, SeriesRow) and linha.body_part == ""
