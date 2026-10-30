"""Pedidos de 29/10/2026 (0.99.9): anotações em quatro níveis, Ctrl+C copia o quadro, sincronização
da RM desligada por padrão (e desligar de verdade) e layouts configuráveis da dinâmica da mama."""
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer
from ipe.ui.viewer import anotacoes as AN
from ipe.ui.viewer import dinamica_config as DC


def _sem_protocolos(s):
    from ipe.ui.viewer import hanging as H
    s.set("hanging_protocols", [dict(p, enabled=False) for p in H.DEFAULT_PROTOCOLS])
    s.set("hanging_fabrica", H.FABRICA_VERSAO)
    return s


@pytest.fixture()
def tc(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, _sem_protocolos(Settings(paths.settings_file)))
    w.resize(1200, 800)
    w.show()
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 1)
    app.processEvents()
    yield app, w, tab, tab.viewports[0]
    w.close()


@pytest.fixture()
def rm(env, tmp_path):
    """RM com cinco séries no mesmo plano e no mesmo referencial (a dinâmica de teste)."""
    from test_measure_tools import make_dynamic
    paths, db, repo = env
    uid = make_dynamic(tmp_path / "d", one_series=False)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, _sem_protocolos(Settings(paths.settings_file)))
    w.resize(1200, 800)
    w.show()
    w.open_study(uid)
    tab = w.all_viewer_tabs()[-1]
    app.processEvents()
    yield app, w, tab
    w.close()


# ------------------------------------------------------------------ anotações
def _linhas(vp):
    return [t for canto in vp._text_lines().values() for t, _h in canto]


def test_niveis_de_fabrica():
    assert set(AN.FABRICA["completa"]) == set(AN.CHAVES)
    assert "nome" not in AN.FABRICA["parcial1"] and "janela" in AN.FABRICA["parcial1"]
    assert len(AN.FABRICA["parcial2"]) < len(AN.FABRICA["parcial1"])
    assert AN.proximo("completa") == "parcial1" and AN.proximo("ausente") == "completa"


def test_os_niveis_mudam_o_que_o_quadro_escreve(tc):
    app, w, tab, vp = tc
    nome = vp.study_info.get("patient_name", "")
    assert nome and nome in _linhas(vp)
    tab.set_anotacoes("parcial1")
    assert nome not in _linhas(vp)
    assert any(t.startswith("W ") for t in _linhas(vp))          # a janela continua
    tab.set_anotacoes("ausente")
    assert _linhas(vp) == []
    assert w.settings.get("viewer.anotacoes_nivel") == "ausente"   # fica guardado
    assert tab.anot_actions["ausente"].isChecked()


def test_cada_nivel_e_escolha_dele(tc):
    app, w, tab, vp = tc
    w.settings.set("viewer.anotacoes_itens", {"parcial2": ["nome"]})
    tab.set_anotacoes("parcial2")
    assert _linhas(vp) == [vp.study_info["patient_name"]]


def test_editor_de_anotacoes_grava(tc):
    from PySide6.QtCore import Qt
    from ipe.ui.viewer.anotacoes_editor import AnotacoesEditor
    app, w, tab, vp = tc
    ed = AnotacoesEditor(w.settings)
    r = AN.CHAVES.index("janela")
    col = 2 + AN.EDITAVEIS.index("parcial1")
    ed.tabela.item(r, col).setCheckState(Qt.Unchecked)
    ed.c_nivel.setCurrentIndex(ed.c_nivel.findData("parcial1"))
    ed.save()
    assert "janela" not in AN.itens_do_nivel(w.settings, "parcial1")
    assert AN.nivel_atual(w.settings) == "parcial1"
    assert not any(t.startswith("W ") for t in _linhas(vp))


def test_menu_do_quadro_tem_anotacoes_e_copiar(tc):
    app, w, tab, vp = tc
    menu = vp.build_context_menu()
    textos = [a.text() for a in menu.actions()]
    assert "Anotações" in textos and any(t.startswith("Copiar a imagem") for t in textos)


# ------------------------------------------------------------------ Ctrl+C
def test_ctrl_c_copia_o_quadro_em_boa_resolucao(tc):
    app, w, tab, vp = tc
    QApplication.clipboard().clear()
    assert tab.copy_action.shortcut().toString() == "Ctrl+C"
    tab.copy_action.trigger()
    img = QApplication.clipboard().image()
    assert not img.isNull()
    assert max(img.width(), img.height()) >= vp.COPIA_LADO_MIN
    # proporção do quadro
    assert img.width() / img.height() == pytest.approx(vp.width() / vp.height(), rel=0.02)


def test_a_copia_segue_o_nivel_de_anotacao(tc):
    """Ausente = imagem limpa: a cópia não pode ter texto por cima. No canto de cima (onde só há
    o texto do paciente, a imagem é ar) a cópia completa tem pixels claros e a limpa não."""
    app, w, tab, vp = tc

    def claros(q):
        return sum(1 for x in range(0, 200) for y in range(0, 40) if q.pixelColor(x, y).lightness() > 120)

    tab.set_anotacoes("completa")
    com = vp.imagem_da_tela(1.0)
    tab.set_anotacoes("ausente")
    sem = vp.imagem_da_tela(1.0)
    assert com.size() == sem.size()
    assert claros(com) > 50 and claros(sem) == 0
    # sem a moldura amarela do quadro ativo
    assert sem.pixelColor(0, sem.height() // 2).red() < 100


def test_ctrl_c_nao_briga_com_o_filme(tc):
    """O compositor de filmes tem Ctrl+C próprio; o do quadro não pode valer na aba inteira."""
    app, w, tab, vp = tc
    assert tab.copy_action not in tab.actions()
    assert tab.copy_action in tab.grid_host.actions()


def test_ctrl_c_chega_a_quem_ja_tinha_atalhos(tmp_path):
    p = tmp_path / "settings.json"
    import json
    p.write_text(json.dumps({"shortcuts": {"tool.wl": "W"}, "shortcuts_versao": 3}), encoding="utf-8")
    st = Settings(p)
    from ipe.ui.viewer.actions import shortcut_for
    assert shortcut_for(st, "view.copy") == "Ctrl+C"
    assert shortcut_for(st, "tool.wl") == "W"


# ------------------------------------------------------------------ sincronização
def _duas_series(app, tab):
    tab.set_layout(1, 2)
    a, b = tab.viewports[:2]
    uids = [s.series_uid for s in tab.series if s.modality == "MR"]
    tab.load_series_into(a, uids[0])
    tab.load_series_into(b, uids[1])
    tab._activate(a)
    app.processEvents()
    return a, b


def test_rm_nasce_sem_sincronizacao_automatica(rm):
    app, w, tab = rm
    a, b = _duas_series(app, tab)
    assert a.modality == "MR" and a.for_uid == b.for_uid
    b.go_to(0)
    a.go_to(2)
    assert b.index == 0                       # duas séries no mesmo plano: não andam juntas
    assert not tab.link_action.isChecked()
    assert tab.sync_auto_action.isChecked()   # o modo do botão, de fábrica, é o automático


def test_ligar_a_automatica_da_rm_alinha_pelo_quadro_ativo_e_e_guardado(rm):
    """Pedido de 29/10 (0.99.10): ao ligar, a automática já leva os outros quadros ao ponto do quadro
    ativo — antes eles ficavam onde estavam e andavam com a diferença daquele momento."""
    app, w, tab = rm
    a, b = _duas_series(app, tab)
    a.go_to(2)
    b.go_to(0)
    tab._activate(a)
    tab.link_action.setChecked(True)
    assert b.index == 2                       # alinhou na hora, pelo quadro ativo
    assert w.settings.get("viewer.sync_auto_mod")["MR"] is True
    a.go_to(1)
    assert b.index == 1


def test_desligar_e_religar_volta_alinhado(rm):
    """O relato: desligava, ligava de novo, e a sincronização ficava no corte em que cada um estava."""
    app, w, tab = rm
    a, b = _duas_series(app, tab)
    tab._activate(a)
    tab.link_action.setChecked(True)
    a.go_to(1)
    assert b.index == 1
    tab.link_action.setChecked(False)
    a.go_to(2)
    assert b.index == 1                       # desligado: não anda
    assert w.settings.get("viewer.sync_auto_mod")["MR"] is False
    tab._activate(b)                          # agora ele mexe no outro quadro
    tab.link_action.setChecked(True)
    assert a.index == 1                       # o ativo (b) manda
    b.go_to(0)
    assert a.index == 0


def test_modo_manual_mantem_a_diferenca(rm):
    app, w, tab = rm
    a, b = _duas_series(app, tab)
    a.go_to(1)
    b.go_to(0)
    tab._activate(a)
    tab.escolher_modo_sync("manual")
    assert tab.sync_manual_action.isChecked() and tab.link_action.isChecked()
    assert b.index == 0                       # não alinhou
    a.go_to(2)
    assert b.index == 1                       # andou junto, com a diferença de um corte
    tab.link_action.setChecked(False)
    a.go_to(1)
    assert b.index == 1
    tab.link_action.setChecked(True)          # religar no manual: liga de novo com a diferença de agora
    a.go_to(2)
    assert b.index == 2
    assert w.settings.get("viewer.sync_modo") == "manual"


def test_mpr_nao_desliga_a_automatica_da_modalidade(tc):
    app, w, tab, vp = tc
    assert w.sync_hub.auto_da_modalidade("CT")
    tab.mpr_action.setChecked(True)
    app.processEvents()
    assert w.sync_hub.auto_da_modalidade("CT")


def test_tc_continua_com_a_automatica():
    from ipe.ui.viewer.sync import SyncHub
    hub = SyncHub()
    assert hub.auto_da_modalidade("CT") and not hub.auto_da_modalidade("MR")
    assert not hub.auto_da_modalidade("MAP msi")         # o mapa da dinâmica é RM


def test_quem_tinha_desligado_tudo_continua_desligado(tmp_path):
    import json
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"viewer": {"sync_auto": False}}), encoding="utf-8")
    from ipe.ui.viewer.sync import SyncHub
    hub = SyncHub(settings=Settings(p))
    assert not hub.auto_da_modalidade("CT")


def test_quadros_da_dinamica_andam_juntos_com_a_rm_desligada(rm):
    app, w, tab = rm
    from ipe.ui.viewer.dynamic import DynamicDialog
    dlg = DynamicDialog(tab)
    p = dlg.params()
    p["layout"] = DC.nomes(w.settings).index("MSI, PEI e SER + curva")
    assert tab.start_dynamic(dlg.dset, p)
    a, b, c = tab.viewports[:3]
    a.go_to(0)
    b.go_to(0)
    a.go_to(2)
    assert b.index == 2 and c.index == 2


# ------------------------------------------------------------------ layouts da dinâmica
def test_layouts_de_fabrica_sao_os_de_antes():
    from ipe.ui.viewer.dynamic import LAYOUTS
    assert [n for n, _k in LAYOUTS] == [lay["nome"] for lay in DC.FABRICA]
    assert LAYOUTS[1][1] == ["cin", "sub", "ph:early"]


def test_layout_dele_com_serie_e_cor(rm):
    app, w, tab = rm
    w.settings.set("dyn.layouts", [{"nome": "Meu", "rows": 2, "cols": 2, "quadros": [
        {"vista": "cin"}, {"vista": "ph:pos1", "cor": "gray"},
        {"vista": "msi", "cor": "hot"}, {"vista": "serie", "serie": "fase 4"}]}])
    from ipe.ui.viewer.dynamic import DynamicDialog
    dlg = DynamicDialog(tab, None, DC.parametros_iniciais(w.settings))
    assert dlg.c_layout.count() == 1 and dlg.c_layout.currentText() == "Meu"
    p = dlg.params()
    assert tab.start_dynamic(dlg.dset, p)
    assert tab._layout == (2, 2)
    a, b, c, d = tab.viewports[:4]
    assert a.dyn_key == "cin"
    assert b.dyn_key == f"ph:{tab.dyn.maps.pre + 1}" and b.state.cmap == ""
    assert c.dyn_key == "msi" and c.state.cmap == "hot"
    # as séries da própria dinâmica não contam como "outra série": o quadro avisa
    assert d.dyn_key is None and not d.frames and "não encontrada" in d.empty_note


def test_fase_que_nao_existe_deixa_o_quadro_vazio_com_aviso(rm):
    app, w, tab = rm
    w.settings.set("dyn.layouts", [{"nome": "X", "rows": 1, "cols": 2,
                                    "quadros": [{"vista": "cin"}, {"vista": "ph:pos6"}]}])
    from ipe.ui.viewer.dynamic import DynamicDialog
    dlg = DynamicDialog(tab, None, DC.parametros_iniciais(w.settings))
    assert tab.start_dynamic(dlg.dset, dlg.params())
    vazio = tab.viewports[1]
    assert not vazio.frames and "não tem esta fase" in vazio.empty_note


def test_parametros_pre_configurados_mandam(tmp_path):
    st = Settings(tmp_path / "s.json")
    st.set("dyn.ultimos", {"threshold_pct": 70.0})
    assert DC.parametros_iniciais(st)["threshold_pct"] == 70.0      # sem pré-configuração: os últimos
    st.set("dyn.padrao", {"threshold_pct": 30.0})
    assert DC.parametros_iniciais(st)["threshold_pct"] == 30.0
    st.set("dyn.origem_parametros", "ultimos")
    assert DC.parametros_iniciais(st)["threshold_pct"] == 70.0


def test_editor_da_dinamica_grava(tmp_path):
    app = QApplication.instance() or QApplication([])
    from ipe.ui.viewer.dinamica_editor import DinamicaMamaEditor
    st = Settings(tmp_path / "s.json")
    ed = DinamicaMamaEditor(st)
    assert ed.l_lays.count() == len(DC.FABRICA)
    ed.novo()
    ed.e_rows.setValue(2)
    ed._escolheu_quadro(3)
    ed.q_vista.setCurrentIndex(ed.q_vista.findData("serie"))
    ed.q_serie.setText("T2|STIR")
    ed.q_serie.textEdited.emit("T2|STIR")
    ed.q_cor.setCurrentIndex(ed.q_cor.findData("gray"))
    ed.s_thr.setValue(80)
    ed.c_padrao.setCurrentText("Novo layout")
    ed.save()
    novo = DC.escolher(st, None, "Novo layout")
    assert (novo["rows"], novo["cols"]) == (2, 2)
    assert novo["quadros"][3] == {"vista": "serie", "serie": "T2|STIR", "cor": "gray"}
    ini = DC.parametros_iniciais(st)
    assert ini["threshold_pct"] == 80 and ini["layout_nome"] == "Novo layout"


def test_protocolo_antigo_pelo_numero_continua_valendo(tmp_path):
    st = Settings(tmp_path / "s.json")
    assert DC.escolher(st, 3)["nome"] == "MSI, PEI e SER + curva"
    assert DC.escolher(st, 99)["nome"] == DC.FABRICA[0]["nome"]


def test_preferencias_abrem_com_as_abas_novas(tc):
    from ipe.ui.preferences import PreferencesDialog
    app, w, tab, vp = tc
    dlg = PreferencesDialog(w.settings, w)
    nomes = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert "Anotações" in nomes and "Dinâmica da mama" in nomes
    assert not dlg.c_sync_mod["MR"].isChecked() and dlg.c_sync_mod["CT"].isChecked()
    dlg.c_sync_mod["MR"].setChecked(True)
    dlg._save()
    assert w.settings.get("viewer.sync_auto_mod")["MR"] is True


def test_quadro_de_outra_serie_abre_a_t2_no_mesmo_corte(env, tmp_path):
    """Layout com a cinética e a T2 lado a lado: a T2 é procurada pela descrição."""
    import pydicom
    from pydicom.uid import generate_uid
    from test_measure_tools import make_dynamic
    paths, db, repo = env
    make_dynamic(tmp_path / "d", one_series=False)
    fase0 = sorted(f for f in (tmp_path / "d").rglob("*") if f.is_file()
                   and pydicom.dcmread(f, stop_before_pixels=True).SeriesDescription == "DYN fase 0")
    t2 = generate_uid()
    (tmp_path / "t2").mkdir()
    for k, f in enumerate(fase0):
        ds = pydicom.dcmread(f)
        ds.SeriesInstanceUID, ds.SOPInstanceUID = t2, generate_uid()
        ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
        ds.SeriesDescription, ds.SeriesNumber = "AX T2 STIR", 5
        ds.save_as(tmp_path / "t2" / f"t2_{k}.dcm")
    Importer(db, paths.storage).import_paths([tmp_path / "d", tmp_path / "t2"])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    s = _sem_protocolos(Settings(paths.settings_file))
    s.set("dyn.layouts", [{"nome": "Cinética e T2", "rows": 1, "cols": 2,
                           "quadros": [{"vista": "cin"}, {"vista": "serie", "serie": "DWI|T2"}]}])
    w = MainWindow(paths, s)
    w.resize(1200, 800)
    w.show()
    study = repo.find_study_uids(accession="DYN001")[0]
    w.open_study(study)
    tab = w.all_viewer_tabs()[-1]
    app.processEvents()
    from ipe.ui.viewer.dynamic import DynamicDialog
    dlg = DynamicDialog(tab, None, DC.parametros_iniciais(s))
    assert len(dlg.dset.phases) == 5           # a T2 não entra como fase
    assert tab.start_dynamic(dlg.dset, dlg.params())
    a, b = tab.viewports[:2]
    assert a.dyn_key == "cin"
    assert "T2" in b.series_label and b.frames
    assert b.index == a.index                  # mesmo corte
    w.close()
