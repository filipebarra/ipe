"""0.99.51 — onda B8 (BI-RADS 0 e 3 geram a busca ativa) e B7 (filtros de mamografia)."""
from datetime import date, datetime, timedelta

import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.reporting import busca_ativa as BA


def _rep(cat="3", kind="mg", sid="1.2.3", rid=1, composition="c"):
    return {"id": rid, "study_uid": sid, "status": "final", "signed_by": "Dr. Teste",
            "signed_at": "2026-11-04 10:00",
            "fields": {"kind": kind, "composition": composition, "cat_right": cat, "cat_left": "1", "findings": []}}


def test_pedido_do_laudo_e_prazo():
    cfg = {"ligada": True, "dias": {"0": 30, "3": 180}}
    p = BA.pedido_do_laudo(_rep("3"), {"patient_id": "P1", "patient_name": "Ana"}, cfg)
    assert p["categoria"] == "3" and p["prazo"] == (date(2026, 11, 4) + timedelta(days=180)).strftime("%Y%m%d")
    assert p["modalidade"] == "MG" and "curto intervalo" in p["motivo"]
    assert BA.pedido_do_laudo(_rep("0", "us"), {}, cfg)["modalidade"] == "US"
    assert BA.pedido_do_laudo(_rep("2"), {}, cfg) is None
    assert BA.pedido_do_laudo({"fields": {}}, {}, cfg) is None
    assert BA.pedido_do_laudo(_rep("3"), {}, {"ligada": False, "dias": {"3": 180}}) is None


def test_situacao_e_retorno():
    hoje = date(2026, 11, 4)
    assert BA.situacao({"estado": "pendente", "prazo": "20261110"}, hoje) == ("faltam 6 dias", False)
    assert BA.situacao({"estado": "pendente", "prazo": "20261104"}, hoje)[0] == "vence hoje"
    assert BA.situacao({"estado": "agendado", "prazo": "20261101"}, hoje) == ("atrasada 3 dias", True)
    assert BA.situacao({"estado": "retornou", "prazo": "20261101"}, hoje) == ("Retornou", False)
    assert BA.exame_de_retorno({"modalities": "MG"})
    assert BA.exame_de_retorno({"modalities": "US", "description": "US MAMAS"})
    assert not BA.exame_de_retorno({"modalities": "US", "description": "US ABDOME"})
    assert "Ana;P1" in BA.csv_das_buscas([{"patient_name": "Ana", "patient_id": "P1", "estado": "pendente",
                                           "prazo": "20261110"}], hoje)


def test_no_banco_retificacao_e_retorno(env, sample_dir):
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    rows = repo.search_studies()
    base = rows[0]
    info = repo.study_info(base.study_uid)
    assert BA.registrar_do_laudo(repo, _rep("3", sid=base.study_uid), info).startswith("busca ativa")
    abertos = repo.buscas_ativas(BA.ABERTOS)
    assert len(abertos) == 1 and abertos[0]["patient_id"] == info["patient_id"]
    # retificação para 0: troca o pedido aberto, não cria outro
    BA.registrar_do_laudo(repo, _rep("0", sid=base.study_uid, rid=2), info)
    abertos = repo.buscas_ativas(BA.ABERTOS)
    assert len(abertos) == 1 and abertos[0]["categoria"] == "0" and "retificado" in abertos[0]["historico"]
    # retificação para 2: encerra
    assert "encerrada" in BA.registrar_do_laudo(repo, _rep("2", sid=base.study_uid, rid=3), info)
    assert repo.buscas_ativas(BA.ABERTOS) == []
    # estado e nota
    BA.registrar_do_laudo(repo, _rep("3", sid=base.study_uid, rid=4), info)
    bid = repo.buscas_ativas(BA.ABERTOS)[0]["id"]
    d = repo.atualizar_busca_ativa(bid, "contatado", "telefone", "ana")
    assert d["estado"] == "contatado" and "Pendente → Contatada — telefone" in d["historico"]
    # coluna do banco
    row = next(r for r in repo.search_studies() if r.study_uid == base.study_uid)
    assert row.busca == "contatado"
    assert repo.busca_ativa_por_exame([base.study_uid]) == {base.study_uid: "contatado"}


def test_retorno_sozinho(env, sample_dir):
    from sqlalchemy import select
    from ipe.db.models import Patient, Study
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    rows = repo.search_studies()
    # dois exames do mesmo paciente: o primeiro gera a busca; o segundo vira mamografia nova
    with db.session() as s:
        sts = list(s.scalars(select(Study)))
        a, b = sts[0], sts[1]
        b.patient_fk = a.patient_fk
        a.study_date, b.study_date = "20260101", "20260701"
        b.modalities, b.description = "MG", "MAMOGRAFIA BILATERAL"
        a.date_added = datetime(2026, 1, 1)
        b.date_added = datetime(2030, 1, 1)
        uid_a, uid_b = a.study_uid, b.study_uid
    info = repo.study_info(uid_a)
    BA.registrar_do_laudo(repo, _rep("3", sid=uid_a), info)
    assert repo.conferir_retornos_busca_ativa() == 1
    it = repo.buscas_ativas(study_uid=uid_a)[0]
    assert it["estado"] == "retornou" and it["retorno_uid"] == uid_b and "retornou" in it["historico"]
    assert len(rows) >= 2


def test_janela_e_filtros_de_mama(env, sample_dir):
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    from ipe.ui.busca_ativa_dialog import BuscaAtivaDialog, BuscaAtivaConfigDialog
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    try:
        uid = repo.search_studies()[0].study_uid
        rid = repo.save_report({"study_uid": uid, "title": "MG", "text": "x",
                                "fields": _rep("0", composition="d")["fields"]})
        rep = repo.sign_report(rid, "Dr. Teste")
        BA.registrar_do_laudo(repo, rep)
        dlg = BuscaAtivaDialog(repo, w)
        assert dlg.tabela.rowCount() == 1 and dlg.tabela.item(0, 3).text() == "0"
        dlg.tabela.selectRow(0)
        dlg.mudar("agendado")
        assert repo.buscas_ativas()[0]["estado"] == "agendado"
        cfg = BuscaAtivaConfigDialog(repo)
        cfg.linhas["4A"][0].setChecked(True)
        cfg._salvar()
        assert BA.config(repo)["dias"] == {"0": 30, "3": 180, "4A": 30}
        # filtros de mama
        br = w.browser
        br.refresh()
        app.processEvents()
        br.aplicar_filtro_mama({"birads": {"0"}})
        assert br.proxy.rowCount() == 1
        assert "birads" in br.visible_columns()
        br.aplicar_filtro_mama({"densidade": {"c", "d"}})
        assert br.proxy.rowCount() == 1
        br.aplicar_filtro_mama({"busca": {"Pendente", "Contatada", "Agendada"}})
        assert br.proxy.rowCount() == 1
        br.aplicar_filtro_mama({"birads": {"3"}})
        assert br.proxy.rowCount() == 0
        textos = [a.text() for a in br.menu_mama().actions()]
        assert "BI-RADS 0 (incompleto)" in textos and "Mamas densas (ACR c e d)" in textos
        laudos = next(a.menu() for a in w.menuBar().actions() if a.text() == "&Laudos")
        assert any(a.text().startswith("Busca ativa") for a in laudos.actions())
    finally:
        w.close()
