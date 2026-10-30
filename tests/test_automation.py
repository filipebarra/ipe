"""Automação: regras (sem rede) e motor com um PACS em loopback."""
from datetime import date, datetime, timedelta

import pytest
from PySide6.QtWidgets import QApplication

from ipe.automation import engine as engine_mod
from ipe.automation import retention
from ipe.automation.rules import (
    StudyStat, date_range, next_run, route_matches, select_for_deletion, select_priors,
)
from test_network_gui import setup, wait  # noqa: F401  (fixture do PACS em loopback)
from test_network import Node


# ------------------------------------------------------------------ regras puras
def test_dates_and_schedule():
    now = datetime(2026, 9, 18, 18, 55)          # sexta-feira
    assert date_range("today", now) == ("20260918", "20260918")
    assert date_range("last_days:7", now) == ("20260911", "20260918")
    assert date_range("last_hours:30", now) == ("20260917", "20260918")
    assert date_range("any", now) == ("", "")
    iv = {"type": "interval", "minutes": 10, "from": "07:00", "to": "19:00", "weekdays": [0, 1, 2, 3, 4]}
    assert next_run(iv, now) == datetime(2026, 9, 18, 19, 5) or next_run(iv, now) == datetime(2026, 9, 21, 7, 0)
    assert next_run(iv, datetime(2026, 9, 18, 18, 45)) == datetime(2026, 9, 18, 18, 55)
    assert next_run(iv, datetime(2026, 9, 18, 18, 55)) == datetime(2026, 9, 21, 7, 0)   # pula o fim de semana
    assert next_run({"type": "daily", "at": "06:00"}, now) == datetime(2026, 9, 19, 6, 0)
    assert next_run({"type": "once", "at": "2026-09-20 22:00"}, now) == datetime(2026, 9, 20, 22, 0)
    assert next_run({"type": "once", "at": "2026-09-10 22:00"}, now) is None


def test_select_priors_breast_mr():
    cfg = {"fetch": ["MR", "MG"], "count": 1, "years": 3, "keywords": ["mama"]}
    cur = {"study_uid": "X", "study_date": "20260901", "modalities": "MR", "description": "RM MAMAS"}
    cands = [
        {"study_uid": "a", "study_date": "20250901", "modalities": "MR", "description": "RM MAMAS"},
        {"study_uid": "b", "study_date": "20251001", "modalities": "MR", "description": "RM CRANIO"},
        {"study_uid": "c", "study_date": "20240901", "modalities": "MR", "description": "RM MAMAS"},
        {"study_uid": "d", "study_date": "20260101", "modalities": "MG", "description": "MAMOGRAFIA"},
        {"study_uid": "e", "study_date": "20250101", "modalities": "MG", "description": "MAMOGRAFIA"},
        {"study_uid": "f", "study_date": "20200101", "modalities": "MG", "description": "MAMOGRAFIA"},
        {"study_uid": "X", "study_date": "20260901", "modalities": "MR", "description": "RM MAMAS"},
    ]
    got = [c["study_uid"] for c in select_priors(cfg, cur, cands, date(2026, 9, 18))]
    assert got == ["d", "a"]            # 1 MG mais recente + 1 RM de mama (crânio fica fora)


def test_route_and_retention_selection():
    cfg = {"modalities": ["MR"], "description_contains": "mama", "origins": ["received"]}
    assert route_matches(cfg, {"modalities": "MR", "description": "RM MAMAS"}, "received")
    assert not route_matches(cfg, {"modalities": "MR", "description": "RM MAMAS"}, "retrieved")
    assert not route_matches(cfg, {"modalities": "CT", "description": "TC MAMA"}, "received")
    now = datetime(2026, 9, 18)
    old, new = now - timedelta(days=40), now - timedelta(days=2)
    stats = [StudyStat("1", "A", "", "CT", "received", old, None, 100),
             StudyStat("2", "B", "", "CT", "received", old, None, 100, ["em lista"]),
             StudyStat("3", "C", "", "MG", "import", old, None, 100),
             StudyStat("4", "D", "", "MG", "prefetch", now - timedelta(days=10), None, 100),
             StudyStat("5", "E", "", "MR", "received", new, new, 5000),
             StudyStat("6", "F", "", "MR", "received", new, now - timedelta(days=1), 5000)]
    pol = {"only_network": True, "max_age_days": 30, "not_opened_days": 0, "prefetch_days": 7,
           "disk_high_pct": 85, "disk_low_pct": 70}
    got = {s.study_uid: r for s, r in select_for_deletion(stats, pol, now, 50.0, 10 ** 6)}
    assert set(got) == {"1", "4"} and "pré-busca" in got["4"]
    # disco cheio: apaga os menos usados até liberar o necessário (90% -> 70% de 100 KB = 20 KB)
    got = {s.study_uid for s, _r in select_for_deletion(stats, pol, now, 90.0, 100_000, open_uids={"6"})}
    assert got == {"1", "4", "5"}


# ------------------------------------------------------------------ motor (com PACS)
def test_scheduled_query_downloads_new_studies(setup):
    app, w, pacs, nid, _ = setup
    rid = w.repo.save_rule({"kind": "query", "name": "RM", "active": True, "config": {
        "node_id": nid, "identity_id": None, "filters": {"modality": "MR"}, "date": "any",
        "schedule": {"type": "interval", "minutes": 5}, "action": "download", "add_to_list": None,
        "max_studies": 10}})
    w.repo.save_rule({"id": rid, "next_run": datetime.now() - timedelta(minutes=1)})
    w.auto.tick()
    assert wait(app, lambda: w.repo.find_study_uids(accession="ACC2001") and not w.net.active_jobs(), 60)
    runs = w.repo.job_runs()
    assert runs[0]["kind"] == "query" and runs[0]["items"] == 1
    rule = w.repo.rule(rid)
    assert rule["last_run"] and rule["next_run"] > datetime.now()
    w.auto.run_query(rule)                      # de novo: nada novo
    assert wait(app, lambda: len(w.repo.job_runs()) >= 2)
    assert w.repo.job_runs()[0]["items"] == 0


def test_prefetch_on_open(setup):
    app, w, pacs, nid, _ = setup
    tc = next(r for r in w.repo.rules("prior") if r["name"] == "TC")
    w.repo.save_rule({"id": tc["id"], "active": True})
    cur = pacs.repo.find_study_uids(accession="ACC1001")[0]
    w.net.retrieve(w.repo.node(nid), None, cur, "atual")
    assert wait(app, lambda: not w.net.active_jobs() and w.repo.study_info(cur), 60)
    # o fim do download já dispara a pré-busca (regra "ao chegar")
    prior = pacs.repo.find_study_uids(accession="ACC0901")[0]
    assert wait(app, lambda: w.repo.study_info(prior) is not None and not w.net.active_jobs(), 60)
    stats = {s.study_uid: s for s in w.repo.retention_stats()}
    assert stats[prior].origin == "prefetch" and stats[cur].origin == "retrieved"


def test_routing_received_study(setup, tmp_path, monkeypatch):
    app, w, pacs, nid, _ = setup
    monkeypatch.setattr(engine_mod, "QUIET_SECONDS", 0.5)
    pacs2 = Node(tmp_path / "pacs2", "PACS2")
    try:
        assert pacs2.server.start()
        n2 = w.repo.save_node(pacs2.as_node())
        w.repo.save_rule({"kind": "route", "name": "MG para PACS2", "active": True, "config": {
            "modalities": ["MG"], "description_contains": "", "origins": ["received"], "node_id": n2,
            "identity_id": None}})
        # o PACS manda um exame para este programa (C-STORE)
        from ipe.network.client import DicomClient, Target
        uid = pacs.repo.find_study_uids(accession="ACC3001")[0]
        DicomClient(10).store(Target.build({**w.repo.node(nid), "ae_title": "DICOMVIEWER",
                                            "port": w.net.server.port}, "PACS"),
                              pacs.repo.files_for_study(uid))
        assert wait(app, lambda: w.repo.study_info(uid) is not None, 30)
        assert wait(app, lambda: (w.auto.tick() or True) and not w.auto._arriving and not w.net.active_jobs()
                    and any(r["kind"] == "route" for r in w.repo.job_runs()), 30)
        assert pacs2.sink.flush(30) and wait(app, lambda: pacs2.repo.study_info(uid) is not None, 20)
    finally:
        pacs2.close()


def test_retention_trash_restore(setup):
    app, w, pacs, nid, _ = setup
    uid = pacs.repo.find_study_uids(accession="ACC3001")[0]
    w.net.retrieve(w.repo.node(nid), None, uid, "MG")
    assert wait(app, lambda: not w.net.active_jobs() and w.repo.study_info(uid), 60)
    with w.db.session() as s:                 # finge que chegou há 60 dias
        from ipe.db.models import Study
        st = s.query(Study).filter_by(study_uid=uid).one()
        st.date_added = datetime.now() - timedelta(days=60)
    w.settings.set("retention", {"enabled": True, "max_age_days": 30, "disk_high_pct": 0})
    plan = w.auto.preview_retention()
    assert [s.study_uid for s, _r in plan] == [uid]
    n_files = len(w.repo.files_for_study(uid))
    assert w.auto.run_retention() == 1
    assert w.repo.study_info(uid) is None
    entries = retention.trash_entries(w.auto.trash_root)
    assert len(entries) == 1 and entries[0]["files"] == n_files
    assert retention.restore(w.repo, w.db, w.paths.storage, entries[0]) == n_files
    assert w.repo.study_info(uid) is not None and not retention.trash_entries(w.auto.trash_root)
    acts = [d["action"] for d in w.repo.deletion_log()]
    assert acts[:2] == ["restore", "trash"]
    # estudo aberto nunca é apagado
    with w.db.session() as s:
        from ipe.db.models import Study
        s.query(Study).filter_by(study_uid=uid).one().date_added = datetime.now() - timedelta(days=60)
        s.query(Study).filter_by(study_uid=uid).one().origin = "received"
    w.open_study(uid)
    assert w.auto.preview_retention() == []


def test_priors_panel(setup):
    app, w, pacs, nid, _ = setup
    cur = pacs.repo.find_study_uids(accession="ACC1001")[0]
    prior = pacs.repo.find_study_uids(accession="ACC0901")[0]
    w.net.retrieve(w.repo.node(nid), None, cur, "atual", open_after=True)
    assert wait(app, lambda: w.all_viewer_tabs() and not w.net.active_jobs(), 60)
    tab = w.all_viewer_tabs()[0]
    tab.priors_action.setChecked(True)
    panel = tab.priors_panel
    assert wait(app, lambda: any(e["study_uid"] == prior for e in panel.entries()), 30)
    e = next(e for e in panel.entries() if e["study_uid"] == prior)
    assert panel._state(e)[0] == "só no PACS"
    panel.compare(e)
    assert wait(app, lambda: prior in tab.study_order, 60)
    assert panel._state(next(x for x in panel.entries() if x["study_uid"] == prior))[0] == "aberto"
