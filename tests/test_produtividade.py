"""0.99.53 — onda B6: painel de produtividade dos laudos."""
from datetime import date, datetime, timedelta

from PySide6.QtWidgets import QApplication

from ipe.core import produtividade as PR


def _it(medico, horas, no_prazo=True, ret=False, mod="MG", dia="2026-11-01"):
    return {"medico": medico, "horas": horas, "no_prazo": no_prazo, "retificacao": ret, "modalidade": mod,
            "subesp": "Mama", "prioridade": "rotina", "dia": dia}


def test_agrupar_e_total():
    itens = [_it("Ana", 2), _it("Ana", 4, False), _it("Ana", 6, ret=True), _it("Bia", 10, mod="CT", dia="2026-11-02")]
    lin = PR.agrupar(itens, "medico")
    assert [x["grupo"] for x in lin] == ["Ana", "Bia"]
    a = lin[0]
    assert a["laudos"] == 3 and a["retificacoes"] == 1 and a["mediana_h"] == 4 and a["no_prazo"] == 2 and a["fora"] == 1
    assert PR.celulas(a)[5] == "2 (67%)"
    assert [x["grupo"] for x in PR.agrupar(itens, "dia")] == ["2026-11-01", "2026-11-02"]
    t = PR.total(itens)
    assert t["laudos"] == 4 and t["p90_h"] == PR._quantil([2, 4, 6, 10], 0.9)
    assert PR.total([])["laudos"] == 0
    assert PR.csv(lin, "Médico").splitlines()[0].startswith("Médico;Laudos")


def test_periodos():
    h = date(2026, 11, 4)
    assert PR.periodo("hoje", h) == ("2026-11-04", "2026-11-04")
    assert PR.periodo("7d", h) == ("2026-10-29", "2026-11-04")
    assert PR.periodo("mes", h) == ("2026-11-01", "2026-11-04")
    assert PR.periodo("mes_passado", h) == ("2026-10-01", "2026-10-31")
    assert PR.periodo("ano", h) == ("2026-01-01", "2026-11-04")


def test_no_banco_e_na_tela(env, sample_dir):
    from sqlalchemy import select
    from ipe.db.models import Report, Study
    from ipe.importer.scanner import Importer
    from ipe.ui.produtividade_dialog import ProdutividadeDialog
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    uids = [r.study_uid for r in repo.search_studies()][:3]
    for i, (uid, quem) in enumerate(zip(uids, ["Dra. Ana", "Dra. Ana", "Dr. Beto"])):
        rid = repo.save_report({"study_uid": uid, "title": "x", "text": "x"})
        repo.sign_report(rid, quem)
    agora = datetime.now()
    with db.session() as s:                                 # o terceiro chegou há 3 dias: fora do prazo de 48 h
        st = s.scalar(select(Study).where(Study.study_uid == uids[2]))
        st.date_added = agora - timedelta(days=3)
        for r in s.scalars(select(Report)):
            r.signed_at = agora
    hoje = date.today().isoformat()
    dados = repo.produtividade_dados(hoje, hoje)
    assert len(dados) == 3 and {d["medico"] for d in dados} == {"Dra. Ana", "Dr. Beto"}
    beto = next(d for d in dados if d["medico"] == "Dr. Beto")
    assert not beto["no_prazo"] and beto["horas"] > 70
    QApplication.instance() or QApplication([])
    dlg = ProdutividadeDialog(repo)
    assert dlg.tabela.rowCount() == 2 and dlg.tabela.item(0, 0).text() == "Dra. Ana"
    assert "3" in dlg.resumo.text() and "sem laudo assinado" in dlg.pendentes.text()
    dlg.c_por.setCurrentIndex(list(PR.AGRUPAR).index("dia"))
    assert dlg.tabela.rowCount() == 1
    so = ProdutividadeDialog(repo, so_eu="Dr. Beto")
    assert so.tabela.rowCount() == 1 and "só os seus" in so.resumo.text()
    dlg.close()
    so.close()
