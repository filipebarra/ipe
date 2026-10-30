"""0.84: modalidade do trabalho e regra por modalidade, histórico de envios, reimprimir em lote,
limpeza automática da lista de impressões e módulos que se ligam e desligam."""
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from ipe import modules as MOD
from ipe.core.config import Settings
from ipe.printing import dispatch as D
from ipe.printing import held as H
from ipe.printing import limpeza as LZ
from ipe.printing import origins as O
from ipe.printing import rules as R
from ipe.printing.modalidade import combina, descobrir, lista


# ----------------------------------------------------------------------------- modalidade e regra
def test_combina_e_lista():
    assert lista("CT\\PT") == ["CT", "PT"] and lista("mg/us") == ["MG", "US"]
    assert combina("", "") and combina("MG", "MG") and combina("mg|us", "US")
    assert combina("C*", "CT\\PT") and combina("PT", "CT\\PT")
    assert not combina("MG", "CT") and not combina("MG", "")       # desconhecida não combina


def _settings(paths):
    s = Settings(paths.settings_file)
    O.save_origins(s, [O.Origin(calling_ae="MG1", remote_host="10.0.0.5", server="Mamo", name="Mamógrafo",
                                modality="MG"),
                       O.Origin(calling_ae="CT1", remote_host="10.0.0.6", server="Mamo", name="Tomógrafo")])
    D.save_destinations(s, [D.Destination(name="PDF MG", kind="pdf", folder=str(paths.settings_file.parent / "pdf")),
                            D.Destination(name="PDF outros", kind="pdf",
                                          folder=str(paths.settings_file.parent / "pdf2"))])
    R.save_rules(s, [R.Rule(name="Mamo", modality="MG", destination="PDF MG"),
                     R.Rule(name="TC e RM", modality="CT|MR", destination="PDF outros")])
    s.save()
    return s


def test_regra_por_modalidade(env):
    paths, _db, _repo = env
    s = _settings(paths)
    linha = {"calling_ae": "XX", "server": "Mamo", "received_at": datetime.now(), "sheets": 1}
    assert H.alvos(s, dict(linha, modality="MG")) == [("PDF MG", "")]
    assert H.alvos(s, dict(linha, modality="CT")) == [("PDF outros", "")]
    assert H.alvos(s, dict(linha, modality="US")) == []
    # sem modalidade no trabalho: vale a da origem cadastrada; origem sem modalidade não combina
    assert H.alvos(s, dict(linha, calling_ae="MG1", remote_host="10.0.0.5")) == [("PDF MG", "")]
    assert H.alvos(s, dict(linha, calling_ae="CT1", remote_host="10.0.0.6")) == []
    assert "modalidade MG" in R.all_rules(s)[0].label_text()


def test_modalidade_vem_do_exame_do_paciente(env, sample_dir):
    paths, db, repo = env
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([sample_dir])
    s = _settings(paths)
    from ipe.core.film_stats import hora_do_exame
    e = next(x for x in repo.search_studies() if x.patient_id == "FANT003")
    chegada = hora_do_exame(e.study_date, e.study_time) + timedelta(hours=1)
    # o exame do paciente manda; a origem (MG) só vale sem paciente
    assert descobrir(repo, s, {"patient_id": "FANT003", "received_at": chegada,
                               "calling_ae": "MG1", "remote_host": "10.0.0.5", "server": "Mamo"}) == "NM"
    assert descobrir(repo, s, {"patient_id": "", "received_at": chegada,
                               "calling_ae": "MG1", "remote_host": "10.0.0.5", "server": "Mamo"}) == "MG"
    # exame de 5 dias antes não é o exame deste filme
    assert descobrir(repo, s, {"patient_id": "FANT003", "received_at": chegada + timedelta(days=5)}) == ""
    # gravado no recebimento
    from ipe.printing import jobs as J
    from ipe.printing.receiver import store_job
    job = J.PrintJob(uid="u1", received_at=chegada.isoformat(), calling_ae="MG1", remote_host="10.0.0.5",
                     server="Mamo", patient_id="FANT003", patient_name="CINTILO^PEDRO")
    pasta = paths.settings_file.parent / "job-u1"
    pasta.mkdir()
    row = store_job(repo, None, job, pasta, paths.settings_file.parent, to_db=False, settings=s)
    assert row["modality"] == "NM"


# ----------------------------------------------------------------------------- histórico e reimpressão
@pytest.fixture()
def aba(env, sample_dir):
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([sample_dir])
    s = _settings(paths)
    from ipe.printing.film import Cell, Film, Sheet
    estudo = repo.search_studies()[0]
    serie = repo.series_for_study(estudo.study_uid)[0]
    inst = repo.instances_for_series(serie.series_uid)[0]
    ids = []
    for nome in ("Filme A", "Filme B", "Filme C"):
        f = Film(name=nome, sheets=[Sheet(1, 1, "A4")])
        f.sheets[0].cells[0] = Cell(estudo.study_uid, serie.series_uid, inst["sop_uid"], 0)
        ids.append(repo.save_film(nome, f.to_dict(), [estudo.study_uid], nome.upper()))
    from ipe.ui.prints_tab import PrintsTab
    a = PrintsTab(repo, s)
    app.processEvents()
    yield app, a, s, repo, ids, paths
    a.deleteLater()


def _linha(aba, nome):
    return next(r for r in aba.rows if r.get("label") == nome)


def test_historico_e_reimpressao_em_lote(aba, monkeypatch):
    app, a, s, repo, ids, paths = aba
    from ipe.auth import session as S
    dest_mg = D.find_destination(s, "PDF MG")
    dest_out = D.find_destination(s, "PDF outros")
    assert a.send_rows([_linha(a, "Filme A")], dest_mg, avisar=False) == (1, 0)
    assert a.send_rows([_linha(a, "Filme B")], dest_out, avisar=False, how="regra") == (1, 0)
    envios = repo.sends("film", ids[0])
    assert len(envios) == 1 and envios[0]["destination"] == "PDF MG" and envios[0]["how"] == "manual"
    assert envios[0]["user"] == (S.get().username or "")
    # detalhes mostram o envio; o histórico abre
    a.table.selectRow(next(i for i, r in enumerate(a.rows) if r.get("label") == "Filme A"))
    assert "Envios (1)" in a.envios_label.text() and "PDF MG" in a.envios_label.text()
    monkeypatch.setattr("PySide6.QtWidgets.QDialog.exec", lambda self: 0)
    a.show_history()
    assert a._dlg_historico.findChildren(type(a.table))[0].rowCount() == 1
    # reimprimir os três: dois voltam ao último destino de cada um, o que nunca saiu fica de fora
    grupos, sem = a.plano_reimpressao([_linha(a, n) for n in ("Filme A", "Filme B", "Filme C")])
    assert {k[0] for k in grupos} == {"PDF MG", "PDF outros"} and [r["label"] for r in sem] == ["Filme C"]
    a.table.selectAll()
    assert a.reprint_selected(confirmar=False) == (2, 0)
    assert [e["how"] for e in repo.sends("film", ids[0])] == ["reimpressão", "manual"]
    assert len(list(Path(dest_mg.folder).glob("*.pdf"))) >= 1
    # apagar o filme leva o histórico junto
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.question",
                        staticmethod(lambda *a_, **k: __import__("PySide6.QtWidgets").QtWidgets.QMessageBox.Yes))
    a.table.clearSelection()
    a.table.selectRow(next(i for i, r in enumerate(a.rows) if r.get("label") == "Filme A"))
    a.delete_selected()
    assert repo.sends("film", ids[0]) == []


def test_impresso_por_no_painel_vem_do_historico(env):
    paths, _db, repo = env
    agora = datetime.now()
    j1 = repo.add_print_job(uid="a", source="scp", calling_ae="MG1", received_at=agora, status="new")
    repo.update_print_job(j1, status="sent", destination="PDF MG")
    repo.add_send("scp", j1, "PDF MG", "ana", "manual")
    j2 = repo.add_print_job(uid="b", source="scp", calling_ae="MG1", received_at=agora, status="new")
    repo.update_print_job(j2, status="sent", destination="PDF MG")
    repo.add_send("scp", j2, "PDF MG", "ana", "regra")
    repo.add_send("scp", j2, "PDF MG", "bia", "reimpressão")
    linhas = {r["id"]: r for r in repo.print_job_stats_rows()}
    assert linhas[j1]["printed_by"] == "ana" and linhas[j1]["print_count"] == 1
    assert linhas[j2]["printed_by"] == "bia" and linhas[j2]["print_count"] == 2


# ----------------------------------------------------------------------------- limpeza
def test_limpeza_por_criterio(env):
    paths, _db, repo = env
    s = _settings(paths)
    agora = datetime(2026, 10, 21, 12, 0)
    base = paths.settings_file.parent

    def job(uid, dias, status, mod, ae="MG1", host="10.0.0.5"):
        pasta = base / f"job-{uid}"
        pasta.mkdir()
        (pasta / "folha.dcm").write_bytes(b"x")
        return repo.add_print_job(uid=uid, source="scp", calling_ae=ae, remote_host=host, server="Mamo",
                                  received_at=agora - timedelta(days=dias), status=status, modality=mod,
                                  folder=str(pasta))
    velho_mg = job("1", 40, "sent", "MG")
    job("2", 40, "new", "MG")                                 # nunca saiu
    job("3", 5, "sent", "MG")                                 # novo demais
    velho_ct = job("4", 40, "sent", "CT", ae="CT1", host="10.0.0.6")
    job("5", 40, "sent", "")                                  # modalidade desconhecida

    def quais(**kw):
        return sorted(r["uid"] for r in LZ.candidatos(repo, s, LZ.Config(**kw), agora))
    assert quais(dias=30) == ["1", "4", "5"]                  # só impressos é o padrão
    assert quais(dias=30, so_impressos=False) == ["1", "2", "4", "5"]
    assert quais(dias=0) == ["1", "3", "4", "5"]
    assert quais(dias=30, modalidades="MG") == ["1"]          # desconhecida não entra
    assert quais(dias=30, modalidades="MG|CT") == ["1", "4"]
    tomografo = O.find(s, "CT1", "10.0.0.6", "Mamo").id
    assert quais(dias=30, origens=[tomografo]) == ["4"]
    # desligada, a automática não faz nada; ligada, apaga linha e pasta
    LZ.save(s, LZ.Config(ligada=False, dias=30, modalidades="MG"))
    assert LZ.automatica(repo, s) == 0
    LZ.save(s, LZ.Config(ligada=True, dias=30, modalidades="MG|CT"))
    assert LZ.limpar(repo, s, agora=agora) == 2
    restantes = {r["id"] for r in repo.print_jobs()}
    assert velho_mg not in restantes and velho_ct not in restantes and len(restantes) == 3
    assert not (base / "job-1").exists() and (base / "job-2").exists()


def test_aba_limpeza_nas_configuracoes(env, monkeypatch):
    paths, _db, repo = env
    _app = QApplication.instance() or QApplication([])
    s = _settings(paths)
    repo.add_print_job(uid="v", source="scp", calling_ae="MG1", remote_host="10.0.0.5", server="Mamo",
                       received_at=datetime.now() - timedelta(days=90), status="sent", modality="MG")
    from ipe.ui.print_settings import PrintSettingsDialog
    j = PrintSettingsDialog(s, None, repo=repo)
    j.lz_on.setChecked(True)
    j.lz_dias.setValue(60)
    j.lz_mod.setText("mg")
    assert j._lz_contar() == 1 and "1 trabalho" in j.lz_conta.text()
    j.lz_imp.setChecked(False)
    assert "nunca saiu" in j.lz_aviso.text()
    j.lz_imp.setChecked(True)
    j._salvar()
    cfg = LZ.config(Settings(paths.settings_file))
    assert (cfg.ligada, cfg.dias, cfg.modalidades, cfg.so_impressos) == (True, 60, "MG", True)
    j2 = PrintSettingsDialog(s, None, repo=repo)
    assert j2._lz_limpar_agora(confirmar=False) == 1 and repo.print_jobs() == []


def test_modalidade_na_origem_e_na_regra_pela_tela(env, monkeypatch):
    paths, _db, _repo = env
    _app = QApplication.instance() or QApplication([])
    s = _settings(paths)
    from ipe.ui import print_settings as PS
    o = O.all_origins(s)[1]
    ed = PS.OriginEditor(o, s)
    ed.modalidade.setText("ct")
    assert ed.origin().modality == "CT"
    re_ = PS.RuleEditor(R.all_rules(s)[0], s)
    assert re_.l_mods.marcados() == ["MG"]                  # 0.85: a modalidade é uma lista de marcar
    re_.l_mods.marcar(["MG", "US"])
    assert re_.rule().modalidades() == ["MG", "US"] and re_.rule().modality == ""


# ----------------------------------------------------------------------------- módulos
def test_modulos_ligam_e_desligam(env, sample_dir):
    paths, db, repo = env
    from ipe.importer.scanner import Importer
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    s = Settings(paths.settings_file)
    assert MOD.desligados(s) == set() and MOD.ligado(s, "mn")
    from ipe.imaging.mammo import find_mg_protocol
    assert find_mg_protocol(s, "MAMOGRAFIA BILATERAL") is not None
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, s)
    w.show()
    try:
        nm = next(e for e in repo.search_studies() if "NM" in (e.modalities or ""))
        w.open_study(nm.study_uid)
        app.processEvents()
        tab = w.all_viewer_tabs()[-1]

        def visivel(acao_alvo):
            return next(a.isVisible() for b, a, _m, _mod in tab._mod_buttons if b.defaultAction() is acao_alvo)
        assert visivel(tab.nm_action)
        assert w.home_bar.acoes["prints"].isVisible()
        # desligar pela tela de preferências
        from ipe.ui.preferences import PreferencesDialog
        dlg = PreferencesDialog(s, w)
        dlg.c_modulos["mn"].setChecked(False)
        dlg.c_modulos["mamografia"].setChecked(False)
        dlg.c_modulos["impressao"].setChecked(False)
        dlg._save()
        assert MOD.desligados(s) == {"mn", "mamografia", "impressao"}
        tab.update_modality_buttons()
        w.aplicar_modulos()
        assert not visivel(tab.nm_action)
        assert not w.home_bar.acoes["prints"].isVisible()
        assert find_mg_protocol(s, "MAMOGRAFIA BILATERAL") is None
        assert w.net.start_print_servers() == 0
        assert w.run_print_cleanup() == 0
        # o exame continua no banco e abre
        assert any(e.study_uid == nm.study_uid for e in repo.search_studies())
        # religar devolve
        MOD.definir(s, {m: True for m in MOD.MODULOS})
        tab.update_modality_buttons()
        w.aplicar_modulos()
        assert visivel(tab.nm_action) and w.home_bar.acoes["prints"].isVisible()
    finally:
        w.close()
