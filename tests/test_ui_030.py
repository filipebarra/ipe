"""Barra de cores editável, botões por modalidade e abrir exames juntos para comparar."""
import numpy as np
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer
from ipe.ui import compare_studies as CS


def _janela(env, sample_dir, accession="ACC1001"):
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    Importer(db, paths.storage).import_paths([sample_dir])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1200, 800)
    w.show()
    w.browser.refresh()
    assert w.handle_external({"accession": accession}) == "aberto"
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 1)
    app.processEvents()
    return w, tab, tab.viewports[0], app


# ------------------------------------------------------------------ barra de cores
def test_pontas_da_barra_de_cores(env, sample_dir):
    w, tab, vp, app = _janela(env, sample_dir)
    vp.set_colormap("hot")
    vp.state.width, vp.state.level = 400.0, 100.0
    vp.grab()
    assert "cbar_hi" in vp._hotspots and "cbar_lo" in vp._hotspots
    lo, hi = vp.colorbar_ends()
    assert (lo, hi) == pytest.approx((-100.0, 300.0))

    # mexer no topo não move a base
    assert vp.set_colorbar_end("cbar_hi", 500.0)
    assert vp.colorbar_ends() == pytest.approx((-100.0, 500.0))
    # e vice-versa
    assert vp.set_colorbar_end("cbar_lo", 0.0)
    assert vp.colorbar_ends() == pytest.approx((0.0, 500.0))
    assert (vp.state.width, vp.state.level) == pytest.approx((500.0, 250.0))
    assert vp.state.window_set is True

    # arrastar para cima sobe o valor daquela ponta, só
    antes = vp.colorbar_ends()
    vp._colorbar_drag("cbar_hi", -50.0)
    depois = vp.colorbar_ends()
    assert depois[1] > antes[1] and depois[0] == pytest.approx(antes[0])

    # as pontas não se cruzam
    vp.set_colorbar_end("cbar_lo", 1e6)
    assert vp.colorbar_ends()[0] < vp.colorbar_ends()[1]
    assert vp.set_colorbar_end("naoexiste", 3) is False
    w.close()


def test_barra_de_cores_em_suv(env, sample_dir):
    w, tab, vp, app = _janela(env, sample_dir)
    vp.set_colormap("hot")
    vp.state.width, vp.state.level = 100.0, 50.0
    vp.suv_factor = 0.5                      # a tela mostra metade do valor cru
    assert vp.colorbar_ends() == pytest.approx((0.0, 50.0))
    vp.set_colorbar_end("cbar_hi", 100.0)    # digitado em SUV
    assert vp.colorbar_ends() == pytest.approx((0.0, 100.0))
    assert vp.state.level + vp.state.width / 2 == pytest.approx(200.0)   # cru é o dobro
    w.close()


# ------------------------------------------------------------------ botões por modalidade
def test_botoes_seguem_a_modalidade(env, sample_dir):
    w, tab, vp, app = _janela(env, sample_dir)          # ACC1001 é TC
    # 0.99.12: os botões que dependem do exame viraram aplicações, com regra
    assert tab._apps, "nenhuma aplicação registrada"
    assert "CT" in tab.study_modalities()
    assert not tab.app_na_barra("mn")                   # TC não tem medicina nuclear
    assert tab.app_na_barra("3d")                       # mas tem volume

    # a preferência traz tudo de volta
    tab.settings.set("viewer.all_buttons", True)
    tab.update_modality_buttons()
    assert tab.app_na_barra("mn")
    tab.settings.set("viewer.all_buttons", False)
    tab.update_modality_buttons()
    assert not tab.app_na_barra("mn")
    w.close()


def test_botao_de_mn_aparece_em_exame_de_mn(env, sample_dir):
    from ipe.db.repository import Repository
    paths, db, repo = env
    w, tab, vp, app = _janela(env, sample_dir)
    uids = [u for u in repo.search_studies() if "NM" in (u.modalities or "")]
    assert uids, "a amostra precisa ter exame de MN"
    w.open_study(uids[0].study_uid)
    app.processEvents()
    aba = w.tabs.currentWidget()
    assert "NM" in aba.study_modalities()
    assert aba.app_na_barra("mn") and not aba.app_na_barra("dinamica")
    w.close()


# ------------------------------------------------------------------ comparar exames
def test_diferencas_de_identidade():
    a = {"study_uid": "1", "patient_name": "SOUZA^Ana", "patient_id": "X1",
         "birth_date": "19800102", "sex": "F", "study_date": "20260101"}
    b = dict(a, study_uid="2", study_date="20250101")
    assert CS.differences([a, b]) == []                      # mesmo paciente: nada a avisar
    assert CS.summary([a, b]) == ""
    c = dict(b, patient_name="souza^ana")                    # só caixa e ^: não é diferença
    assert CS.differences([a, c]) == []
    d = dict(b, patient_id="X2", birth_date="19800103")
    difs = dict(CS.differences([a, d]))
    assert set(difs) == {"ID do paciente", "Data de nascimento"}
    assert difs["Data de nascimento"] == ["02/01/1980", "03/01/1980"]
    assert "ID do paciente" in CS.summary([a, d])
    vazio = dict(b, patient_id="")
    assert dict(CS.differences([a, vazio]))["ID do paciente"][1] == "(em branco)"


def test_ordem_do_mais_recente_para_o_mais_antigo():
    a = {"study_uid": "velho", "study_date": "20240101", "study_time": "100000"}
    b = {"study_uid": "novo", "study_date": "20260101", "study_time": "080000"}
    c = {"study_uid": "meio", "study_date": "20250101", "study_time": ""}
    assert [i["study_uid"] for i in CS.order([a, b, c])] == ["novo", "meio", "velho"]


def test_abrir_dois_exames_juntos(env, sample_dir):
    w, tab, vp, app = _janela(env, sample_dir)
    paths, db, repo = env
    atual = repo.find_study_uids(accession="ACC1001")[0]
    anterior = repo.find_study_uids(accession="ACC0901")[0]
    assert w.open_comparison([atual, anterior]) is True
    app.processEvents()
    aba = w.tabs.currentWidget()
    assert len(aba.study_order) == 2 and set(aba.study_order) == {atual, anterior}
    # o mais recente é o atual da aba
    datas = {u: (repo.study_info(u) or {}).get("study_date") for u in aba.study_order}
    assert datas[aba.study_order[0]] >= datas[aba.study_order[1]]
    assert w.tabs.count() == 2                                   # banco + uma aba de exame só
    w.close()


def test_um_exame_so_abre_normal(env, sample_dir):
    w, tab, vp, app = _janela(env, sample_dir)
    paths, db, repo = env
    uid = repo.find_study_uids(accession="ACC1001")[0]
    assert w.open_comparison([uid]) is True
    assert w.open_comparison([]) is False
    w.close()


def test_identidade_diferente_pergunta_e_respeita_o_nao(env, sample_dir, monkeypatch):
    w, tab, vp, app = _janela(env, sample_dir)
    paths, db, repo = env
    a = repo.find_study_uids(accession="ACC1001")[0]
    outro = next(r.study_uid for r in repo.search_studies()
                 if (repo.study_info(r.study_uid) or {}).get("patient_id")
                 != (repo.study_info(a) or {}).get("patient_id"))
    perguntou = []
    monkeypatch.setattr(CS, "confirm", lambda parent, infos: (perguntou.append(infos), False)[1])
    assert w.open_comparison([a, outro]) is False
    assert perguntou and CS.differences(perguntou[0])          # avisou por causa da identidade
    abas = w.tabs.count()
    monkeypatch.setattr(CS, "confirm", lambda parent, infos: True)
    assert w.open_comparison([a, outro]) is True
    assert w.tabs.count() == abas                                 # continuou na mesma aba
    w.close()
