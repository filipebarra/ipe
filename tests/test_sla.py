"""0.99.52 — onda B4: prioridade, subespecialidade e prazo do laudo (SLA) na lista de exames."""
from datetime import datetime, timedelta

import pytest
from PySide6.QtWidgets import QApplication

from ipe.core import sla as SLA
from ipe.core.config import Settings


class _Repo:
    def __init__(self, v=None):
        self.v = v

    def get_app_setting(self, k, d=None):
        return self.v


def test_regras_de_fabrica():
    c = SLA.config(_Repo())
    assert SLA.subespecialidade("MG", "MAMOGRAFIA DIGITAL", c) == "Mama"
    assert SLA.subespecialidade("US", "US DE MAMAS E AXILAS", c) == "Mama"
    assert SLA.subespecialidade("US", "US DE ABDOME TOTAL", c) == "Abdome"
    assert SLA.subespecialidade("CT", "TC DE CRÂNIO", c) == "Neuro"
    assert SLA.subespecialidade("PT\\CT", "PET-CT FDG", c) == "Medicina nuclear"
    assert SLA.subespecialidade("CR", "RX DO PÉ", c) == "Musculoesquelético"
    assert SLA.subespecialidade("OT", "?", c) == "Geral"
    assert SLA.prioridade("TC CRANIO - PS", c) == "urgente"
    assert SLA.prioridade("Código AVC", c) == "emergencia"
    assert SLA.prioridade("PET PSMA", c) == "rotina"              # "PS" só como palavra
    assert SLA.prioridade("TC CRANIO - PS", c, manual="rotina") == "rotina"


def test_prazo_e_situacao():
    c = SLA.config(_Repo({"horas": {"rotina": 24}, "por_subesp": {"Mama": 72}}))
    t0 = datetime(2026, 11, 4, 8, 0)
    assert SLA.prazo(t0, "rotina", "Neuro", c) == t0 + timedelta(hours=24)
    assert SLA.prazo(t0, "rotina", "Mama", c) == t0 + timedelta(hours=72)
    assert SLA.prazo(t0, "urgente", "Mama", c) == t0 + timedelta(hours=4)
    pz = t0 + timedelta(hours=4)
    assert SLA.situacao(pz, agora=t0) == ("faltam 4 h", "ok")
    assert SLA.situacao(pz, agora=t0 + timedelta(hours=3, minutes=20)) == ("vence em 40 min", "atencao")
    assert SLA.situacao(pz, agora=t0 + timedelta(hours=7)) == ("atrasado 3 h", "atrasado")
    assert SLA.situacao(pz, laudado_em=t0 + timedelta(hours=1)) == ("no prazo", "no_prazo")
    assert SLA.situacao(pz, laudado_em=t0 + timedelta(hours=9))[1] == "fora_do_prazo"
    r = SLA.resolver({"description": "TC CRANIO URGENTE", "modalities": "CT", "chegada": t0}, c, t0)
    assert r["prioridade"] == "urgente" and r["subesp"] == "Neuro" and r["prazo"] == "202611041200"


def test_no_banco_e_na_tela(env, sample_dir):
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    rows = repo.search_studies()
    assert all(r.prioridade and r.subesp and r.prazo and r.sla for r in rows)
    uid = rows[0].study_uid
    assert repo.set_study_priority([uid], "emergencia") == 1
    r = next(x for x in repo.search_studies() if x.study_uid == uid)
    assert r.prioridade == "emergencia"
    repo.set_study_priority([uid], subespecialidade="Mama")
    r = next(x for x in repo.search_studies() if x.study_uid == uid)
    assert r.subesp == "Mama" and r.prioridade == "emergencia"
    # laudo assinado: o SLA vira "no prazo"
    rid = repo.save_report({"study_uid": uid, "title": "x", "text": "x"})
    repo.sign_report(rid, "Dr. Teste")
    r = next(x for x in repo.search_studies() if x.study_uid == uid)
    assert r.sla_estado == "no_prazo"
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    try:
        br = w.browser
        br.refresh()
        app.processEvents()
        n = br.proxy.rowCount()
        br.filtro_trabalho("sem_laudo")
        assert br.proxy.rowCount() == n - 1
        assert all(k in br.visible_columns() for k in ("prioridade", "subesp", "prazo", "sla"))
        br.filtro_trabalho("atrasados")
        assert br.proxy.rowCount() == 0
        br.settings.set("worklist.minhas_subesp", ["Mama"])
        br.filtro_trabalho("minhas")
        esperado = sum(1 for x in repo.search_studies() if x.subesp == "Mama" and x.report in ("", "rascunho"))
        assert br.proxy.rowCount() == esperado               # o que foi trocado para mama já foi laudado
        textos = [a.text() for a in br.menu_trabalho().actions()]
        assert any(t.startswith("Minhas subespecialidades (Mama)") for t in textos)
        sub = [a.text() for a in br.menu_do_exame([rows[0]]).actions() if a.menu() is not None]
        assert "Prioridade" in sub and "Subespecialidade" in sub
        from ipe.ui.sla_dialog import SlaConfigDialog
        dlg = SlaConfigDialog(repo)
        dlg.horas["rotina"].setValue(12)
        dlg.por_subesp.setText("Mama=72; Neuro=6")
        dlg._salvar()
        c = SLA.config(repo)
        assert c["horas"]["rotina"] == 12 and c["por_subesp"] == {"Mama": 72.0, "Neuro": 6.0}
        assert len(c["subesp"]) == len(SLA.PADRAO["subesp"])
        dlg2 = SlaConfigDialog(repo)
        dlg2.por_subesp.setText("Mama=x")
        with pytest.raises(ValueError):
            dlg2.valor()
    finally:
        w.close()
