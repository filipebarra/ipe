"""Pré-cálculo da dinâmica na chegada: deixa pronto, não grava nada e não manda nada."""
import pytest

from ipe.automation import dinamica as D
from ipe.imaging.series import FrameCache
from ipe.importer.scanner import Importer
from tests.test_dynamic import make_dynamic


def test_regra_serve():
    info = {"modalities": "MR", "description": "RM MAMAS COM CONTRASTE"}
    assert D.regra_serve({"modalities": ["MR"], "description_contains": "mama"}, info)
    assert D.regra_serve({}, info)
    assert not D.regra_serve({"modalities": ["CT"]}, info)
    assert not D.regra_serve({"description_contains": "próstata"}, info)
    assert D.regra_serve({"modalities": ["mr"], "description_contains": "MAMAS"}, info)


def test_aquece_os_quadros_da_dinamica(env, tmp_path):
    paths, db, repo = env
    uid = make_dynamic(tmp_path / "d", one_series=False)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    cache = FrameCache(max_mb=64)
    out = D.aquecer(repo, cache, uid)
    assert out["fases"] == 5 and out["quadros"] > 0 and not out["parou"]
    # de novo não custa nada: o que já está no cache não é relido
    de_novo = D.aquecer(repo, cache, uid)
    assert de_novo["quadros"] == 0 and de_novo["fases"] == 5


def test_para_quando_o_cache_enche(env, tmp_path):
    paths, db, repo = env
    uid = make_dynamic(tmp_path / "d", one_series=False)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    cache = FrameCache(max_mb=0)                 # sem espaço reservado nenhum
    cache.max_bytes = 1024                       # um quadro já estoura
    out = D.aquecer(repo, cache, uid)
    assert out["parou"] == "cache cheio" and out["quadros"] >= 1
    assert "cache cheio" in D.resumo(out)


def test_exame_sem_dinamica_nao_inventa(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    cache = FrameCache(max_mb=64)
    uid = repo.search_studies()[0].study_uid
    out = D.aquecer(repo, cache, uid)
    assert out["fases"] == 0 and out["quadros"] == 0 and out["parou"]


def test_o_motor_so_roda_com_regra_ativa(env, tmp_path, monkeypatch):
    """A regra é a porta: sem ela o programa não sai calculando sozinho."""
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid = make_dynamic(tmp_path / "d", one_series=False)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    feitos = []
    w.net.run_async = lambda trabalho, pronto=None: feitos.append(trabalho())
    info = repo.study_info(uid)
    assert not w.auto.precalcular_dinamica(uid, info)          # nenhuma regra cadastrada
    rid = repo.save_rule({"kind": "dinamica", "name": "RM de mama", "active": True,
                          "config": {"modalities": ["MR"], "description_contains": ""}})
    assert w.auto.precalcular_dinamica(uid, info)
    assert feitos and feitos[0]["fases"] == 5
    repo.save_rule({"id": rid, "kind": "dinamica", "active": False,
                    "config": {"modalities": ["MR"], "description_contains": ""}})
    feitos.clear()
    assert not w.auto.precalcular_dinamica(uid, info)           # pausada é pausada
    assert not feitos
    w.close()


def test_nao_grava_serie_nem_envia(env, tmp_path):
    """O contrato da escolha dele: nada de série nova, nada saindo pela rede."""
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid = make_dynamic(tmp_path / "d", one_series=False)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    antes = len(repo.series_for_study(uid))
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    enviados = []
    w.net.send = lambda *a, **k: enviados.append(a)
    w.net.run_async = lambda trabalho, pronto=None: trabalho()
    repo.save_rule({"kind": "dinamica", "name": "x", "active": True, "config": {}})
    w.auto.precalcular_dinamica(uid, repo.study_info(uid))
    assert len(repo.series_for_study(uid)) == antes, "criou série"
    assert not enviados, "mandou alguma coisa pela rede"
    w.close()


def test_a_janela_de_automacao_tem_a_aba(env):
    """Função sem porta visível é função que não existe."""
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    from ipe.ui.automation_dialog import AutomationDialog, DinamicaRuleDialog
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    dlg = AutomationDialog(w)
    abas = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert "Dinâmica pronta" in abas
    d = DinamicaRuleDialog(None, dlg)
    r = d.result_rule()
    assert r["kind"] == "dinamica" and r["config"]["modalities"] == ["MR"]
    assert "mama" in r["config"]["description_contains"]
    assert "node_id" not in r["config"], "regra de dinâmica não tem destino: nada sai"
    d.close()
    dlg.close()
    w.close()
