"""0.88: protocolos de exibição com etapas para TC, RM… — como o da mamografia.

Pedido dele: "criar protocolos de visualização para outros exames (TC, RM…), assim como o da
mamografia. Steps mudando layout, cor, séries preferenciais, planos, podendo ter MIP, MPR."
"""
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.ui.viewer import hanging as H


# ----------------------------------------------------------------------------- modelo
def test_quadro_e_etapa_normalizam():
    q = H.quadro({"series": "T1", "plane": "Obliquo", "recon": "mip", "slab": "12", "sync": "2", "x": 1})
    assert q["plane"] == "" and q["recon"] == "mip" and q["slab"] == 12.0 and q["sync"] == 2 and "x" not in q
    assert H.quadro("T2|STIR")["series"] == "T2|STIR"
    st = H.etapa({"rows": 2, "cols": 2, "cells": ["A"]})
    assert len(st["cells"]) == 4 and st["cells"][0]["series"] == "A" and st["cells"][3]["series"] == ""


def test_protocolo_antigo_vira_uma_etapa_com_o_anterior_ao_lado():
    velho = {"name": "TC", "modality": "CT", "layout": [1, 2], "cells": ["AX", "COR"], "prior": True}
    [st] = H.etapas(velho)
    assert (st["rows"], st["cols"]) == (1, 4)
    assert [(c["series"], c["prior"]) for c in st["cells"]] == [("AX", False), ("COR", False),
                                                                ("AX", True), ("COR", True)]
    novo = H.convertido(velho)
    assert H.tem_etapas(novo) and novo["prior"] is False and "cells" not in novo


def test_serie_por_ordem_de_preferencia():
    cand = [("u1", {"T1"}, "T1"), ("u2", {"T1", "POS"}, "T1 POS"), ("u3", {"T2"}, "T2")]
    assert H.escolher_serie("T1 POS|T1", cand) == "u2"          # a pós ganha, mesmo vindo depois
    assert H.escolher_serie("T1|T1 POS", cand) == "u1"
    assert H.escolher_serie("T1", cand, evitar={"u1"}) == "u2"   # prefere série ainda não usada
    assert H.escolher_serie("T1 POS", cand, evitar={"u2"}) == "u2"   # mas repete se for a única
    assert H.escolher_serie("FLAIR", cand) is None


def test_etapa_repartida_entre_monitores():
    st = H.etapa({"rows": 2, "cols": 2, "cells": ["A", "B", "C", "D"]})
    um, dois = H.parte_da_tela(st, 2, 0), H.parte_da_tela(st, 2, 1)
    assert [c["series"] for c in um["cells"]] == ["A", "B"] and [c["series"] for c in dois["cells"]] == ["C", "D"]
    st2 = H.etapa({"rows": 1, "cols": 3, "cells": [{"series": "A", "monitor": 2}, "B", {"series": "C", "monitor": 2}]})
    assert [c["series"] for c in H.parte_da_tela(st2, 2, 1)["cells"]][:2] == ["A", "C"]
    assert [c["series"] for c in H.parte_da_tela(st2, 2, 0)["cells"]][:1] == ["B"]


def test_os_de_fabrica_entram_uma_vez_para_quem_ja_tinha(env):
    paths, _db, _repo = env
    s = Settings(paths.settings_file)
    s.set("hanging_protocols", [{"name": "RM de mama", "modality": "MR", "layout": [1, 1], "cells": ["T1"]}])
    # 0.90: a RM de mama dele também ganha a etapa nova dos MIPs de meia mama
    assert set(H.acrescentar_os_de_fabrica(s)) == {"TC de tórax", "RM de crânio",
                                                   "RM de mama ▸ MIP das fases (meia mama)",
                                                   "RM de mama ▸ Avaliação dinâmica"}
    nomes = [p["name"] for p in H.protocols(s)]
    assert nomes.count("RM de mama") == 1 and "TC de tórax" in nomes
    s.set("hanging_protocols", nomes and H.protocols(s)[:1])
    assert H.acrescentar_os_de_fabrica(s) == []                    # só uma vez


# ----------------------------------------------------------------------------- no visualizador
@pytest.fixture()
def janela(env, sample_dir):
    paths, db, repo = env
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1200, 800)
    w.show()
    yield app, w, repo
    w.close()


def _abrir(app, w, repo, mod):
    estudo = next(e for e in repo.search_studies() if e.modalities == mod)
    w.open_study(estudo.study_uid)
    app.processEvents()
    return w.all_viewer_tabs()[-1]


def test_tc_abre_na_etapa_1_e_as_setas_passam(janela):
    app, w, repo = janela
    t = _abrir(app, w, repo, "CT")
    assert t.exib is not None and t.exib.nome == "TC de tórax" and t._layout == (1, 2)
    assert t.etapas_bar.isVisible() and t.etapas_bar.c_step.currentIndex() == 0
    ax, cor = t.viewports[:2]
    assert ax.mpr_plane is None and cor.mpr_plane is not None and cor.mpr_plane.name == "Coronal"
    assert (ax.state.width, ax.state.level) == (400, 40)          # preset Mediastino
    assert t.hub.group_of(ax) is not None and t.hub.group_of(ax) == t.hub.group_of(cor)
    t.mg_next(1)                                                   # → (a mesma tecla da mamografia)
    assert t.exib.indice == 1 and t.viewports[0].state.width == 1500
    t.mg_next(1)
    a, c = t.viewports[:2]
    assert (a.mpr_plane.name, a.mpr_plane.mode, a.mpr_plane.slab_mm) == ("Axial", "mip", 10.0)
    assert (c.mpr_plane.name, c.mpr_plane.mode) == ("Coronal", "mip")
    assert "MIP 10 mm" in a.series_label
    msgs = []
    t.status_message.connect(msgs.append)
    t.mg_next(1)                                                   # não passa da última
    assert t.exib.indice == 2 and "última etapa" in msgs[-1]
    t.mg_next(-1)
    assert t.exib.indice == 1
    t.etapas_bar._escolheu(0)                                      # pela lista da barra
    assert t.exib.indice == 0
    from ipe.ui.viewer import etapas as E
    E.encerrar(t)
    assert t.exib is None and not t.etapas_bar.isVisible()


def test_serie_que_falta_avisa_no_quadro(janela):
    app, w, repo = janela
    t = _abrir(app, w, repo, "MR")
    assert t.exib.nome == "RM de mama" and t._layout == (2, 2)
    assert t.viewports[0].frames and t.viewports[1].frames
    assert "Série não encontrada" in t.viewports[2].empty_note and "DWI" in t.viewports[2].empty_note
    assert not t.viewports[2].frames


def test_mamografia_continua_com_as_etapas_dela(janela):
    app, w, repo = janela
    t = _abrir(app, w, repo, "MG")
    assert t.exib is None and t.mg_session is not None


def test_gravar_a_tela_como_etapa(janela, monkeypatch):
    app, w, repo = janela
    t = _abrir(app, w, repo, "CT")
    t.mg_next(1)
    t.mg_next(1)                                                   # na etapa MIP
    from ipe.ui.viewer import etapas as E
    st = E.gravar_tela(t)
    assert (st["rows"], st["cols"]) == (1, 2)
    q1, q2 = st["cells"]
    assert q1["series"] == "Axial 3mm" and q1["plane"] == "Axial" and q1["recon"] == "mip" and q1["slab"] == 10
    assert q2["plane"] == "Coronal" and q1["window"] == "1"        # reconhece o preset Pulmão
    # pela barra: grava num protocolo novo, como etapa nova
    from PySide6.QtWidgets import QDialog

    def aceitar(dlg):
        combo = dlg.findChildren(type(t.etapas_bar.c_step))[0]
        combo.setCurrentIndex(combo.findData("__novo__"))
        return QDialog.Accepted
    monkeypatch.setattr(QDialog, "exec", aceitar)
    t.gravar_tela_como_etapa()
    novo = next(p for p in H.protocols(w.settings) if p["name"].startswith("CT"))
    assert len(novo["steps"]) == 1 and novo["steps"][0]["cells"][1]["plane"] == "Coronal"
    assert t.exib.nome == novo["name"]
    # de novo, agora acrescentando no mesmo protocolo
    t.gravar_tela_como_etapa()
    assert len(next(p for p in H.protocols(w.settings) if p["name"] == novo["name"])["steps"]) == 2


# ----------------------------------------------------------------------------- editor
def test_editor_monta_um_protocolo(env):
    paths, _db, _repo = env
    _app = QApplication.instance() or QApplication([])
    s = Settings(paths.settings_file)
    from ipe.ui.viewer.protocolos_editor import ProtocolosEditor
    e = ProtocolosEditor(s)
    assert [p["name"] for p in e.protocolos()] == ["RM de mama", "TC de tórax", "RM de crânio"]
    e.novo_protocolo()
    i = len(e.protos) - 1
    assert e._pi == i and e.l_protos.currentRow() == i            # o novo fica escolhido na lista
    e.e_p_nome.setText("TC de abdome")                             # 0.99.1: campos à direita, como na Mamografia
    e.e_p_nome.textEdited.emit("TC de abdome")
    e.e_p_desc.setText("ABDOME")
    e.e_p_desc.textEdited.emit("ABDOME")
    assert e.l_protos.item(i).text().startswith("TC de abdome")
    e.e_rows.setValue(2)                                           # etapa 1 vira 2×2
    assert len(e._etapa()["cells"]) == 4 and len(e.botoes_quadro) == 4
    e._escolheu_quadro(3)
    e.q_serie.setText("PORTAL|VENOSA|AXIAL")
    e.q_serie.textEdited.emit(e.q_serie.text())
    e.q_plano.setCurrentIndex(e.q_plano.findData("Coronal"))
    e.q_recon.setCurrentIndex(e.q_recon.findData("mip"))
    assert e.q_slab.value() == 10                                  # MIP sem espessura não é MIP
    e.q_janela.setCurrentIndex(e.q_janela.findData("5"))
    e.q_sync.setValue(1)
    e.nova_etapa()
    e.e_nome.setText("Arterial")
    e.e_nome.textEdited.emit("Arterial")
    p = e.protocolos()[i]
    assert (p["name"], p["description"], len(p["steps"])) == ("TC de abdome", "ABDOME", 2)
    q = p["steps"][0]["cells"][3]
    assert (q["series"], q["plane"], q["recon"], q["slab"], q["window"], q["sync"]) == \
        ("PORTAL|VENOSA|AXIAL", "Coronal", "mip", 10.0, "5", 1)
    assert p["steps"][1]["name"] == "Arterial"
    # a janela escrita à mão também vale
    e.l_etapas.setCurrentRow(0)
    e._escolheu_quadro(0)
    e.q_janela.setEditText("350/50")
    e.q_janela.lineEdit().textEdited.emit("350/50")
    assert e.protocolos()[i]["steps"][0]["cells"][0]["window"] == "350/50"


def test_preferencias_gravam_os_protocolos(env):
    paths, _db, _repo = env
    _app = QApplication.instance() or QApplication([])
    s = Settings(paths.settings_file)
    from ipe.ui.preferences import PreferencesDialog
    d = PreferencesDialog(s)
    d.hp_editor.mover_protocolo(1) if d.hp_editor._pi == 0 else None
    d._save()
    gravados = Settings(paths.settings_file).get("hanging_protocols")
    assert [p["name"] for p in gravados][:2] == ["TC de tórax", "RM de mama"]
    assert all(H.tem_etapas(p) for p in gravados)


def test_duas_telas_cada_uma_com_o_seu_pedaco_e_a_etapa_passa_nas_duas(janela, monkeypatch):
    app, w, repo = janela
    import tests.test_monitores_viewer as TM
    TM._dois_monitores(w, monkeypatch)
    ct = next(e for e in repo.search_studies() if e.modalities == "CT")
    w.open_study(ct.study_uid)
    app.processEvents()
    a, b = [t for d in w.detached for t in d.viewer_tabs()]
    assert a.exib is not None and b.exib is not None
    assert a._layout == (1, 1) and b._layout == (1, 1)            # 1×2 repartida: um quadro em cada tela
    assert a.viewports[0].mpr_plane is None and b.viewports[0].mpr_plane.name == "Coronal"
    a.mg_next(1)
    assert a.exib.indice == 1 and b.exib.indice == 1               # a etapa é da estação
    assert b.viewports[0].state.width == 1500
