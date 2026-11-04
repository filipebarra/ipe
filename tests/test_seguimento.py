"""0.99.59 — item 7 (parte 1): ligação pela posição (AW O1), assistente do seguimento (O3), nadir e 4 datas."""
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.imaging import lesions as L
from ipe.imaging import seguimento as SG
from ipe.importer.scanner import Importer


class _Repo:
    def __init__(self, reg=None, M=None):
        self.reg, self.M = reg, M

    def get_registration(self, a, b):
        return self.reg

    def get_registration_matriz(self, a, b):
        return self.M


def test_transformar_e_candidatos():
    p = [10.0, 20.0, 30.0]
    assert list(SG.transformar(_Repo(), p, "A", "A")) == p
    assert SG.transformar(_Repo(), p, "A", "B") is None                      # sem registro, não adivinha
    assert list(SG.transformar(_Repo(reg=([1, 2, 3], 0.0)), p, "A", "B")) == [11, 22, 33]
    M = np.eye(4)
    M[:3, 3] = [5, 0, 0]
    assert list(SG.transformar(_Repo(reg=([9, 9, 9], 0), M=M.tolist()), p, "A", "B")) == [15, 20, 30]
    import json
    anns = [{"study_uid": "A", "id": 1, "data": json.dumps({"kind": "line", "meta": {"lesion": 7, "centro": p}})},
            {"study_uid": "A0", "id": 2, "data": json.dumps({"kind": "line", "meta": {"lesion": 8, "centro": [100, 0, 0]}})}]
    lesoes = [{"id": 7, "name": "L1"}, {"id": 8, "name": "L2"}]
    datas = {"A0": "20240101", "A": "20250101", "B": "20260101"}
    c = SG.candidatos(_Repo(reg=([0, 0, 2], 0)), lesoes, anns, datas, "B", [10, 21, 32])
    assert len(c) == 1 and c[0][1]["name"] == "L1" and c[0][0] == pytest.approx(1.0)
    assert SG.escolher(c)[1]["id"] == 7
    assert SG.escolher([(4, {"id": 1}, {}), (5, {"id": 2}, {})]) is None      # dúvida: não liga sozinho
    pend = SG.pendentes(lesoes, anns, datas, "B")
    assert [x["lesao"]["id"] for x in pend] == [7, 8]
    lesoes[1]["data"] = {"status": {"B": "absent"}}
    assert [x["lesao"]["id"] for x in SG.pendentes(lesoes, anns, datas, "B")] == [7]


def test_nadir_quatro_datas_e_pequena():
    lesoes = [{"id": 1, "name": "Fígado", "kind": "target"}, {"id": 2, "name": "Pulmão", "kind": "target",
                                                                  "data": {"status": {"S4": "pequena"}}}]
    import json

    def a(st, lid, mm):
        return {"study_uid": st, "id": hash((st, lid)) % 1000, "series_uid": "x", "sop_uid": "y", "frame_index": 0,
                "data": json.dumps({"meta": {"lesion": lid, "mm": mm}})}
    anns = [a("S1", 1, 40), a("S1", 2, 20), a("S2", 1, 20), a("S2", 2, 10), a("S3", 1, 25), a("S3", 2, 10),
            a("S4", 1, 30)]
    studies = [("S1", "20250101"), ("S2", "20250401"), ("S3", "20250701"), ("S4", "20251001")]
    cells = L.collect_cells(lesoes, anns, "recist")
    assert cells[(2, "S4")].value == 5.0 and "pequena demais" in cells[(2, "S4")].text("recist")
    ev = L.evaluate("recist", lesoes, studies, cells)
    s4 = ev[-1]
    assert s4.total == 35 and s4.nadir_uid == "S2" and s4.nadir_total == 30
    assert s4.pct_nadir == pytest.approx(100 * 5 / 30, rel=1e-6) and s4.response == "RP"   # +16,7% do nadir; −42% da base
    d = L.quatro_datas(ev, "S4")
    assert [r for r, _e in d] == ["base", "nadir", "anterior", "atual"]
    txt = L.summary_text("recist", lesoes, studies, cells, ev, "S4")
    assert "Datas: base 01/01/2025 (60.0 mm); nadir 01/04/2025 (30.0 mm); anterior 01/07/2025 (35.0 mm)" in txt


@pytest.fixture()
def janela(env, sample_dir):
    from test_pedidos_29_10 import _sem_protocolos
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, _sem_protocolos(Settings(paths.settings_file)))
    w.resize(1300, 800)
    w.show()
    yield app, w, repo
    w.close()


def test_liga_sozinho_e_assistente(janela, monkeypatch):
    app, w, repo = janela
    atual = repo.find_study_uids(accession="ACC1001")[0]
    ant = repo.find_study_uids(accession="ACC0901")[0]
    w.handle_external({"accession": "ACC1001"})
    tab = w.tabs.currentWidget()
    tab.add_study(ant)
    app.processEvents()
    a, b = tab._shown()[0], tab._shown()[1]
    vp_ant = a if a.study_uid == ant else b
    vp_atu = b if vp_ant is a else a
    pid = repo.study_info(atual)["patient_id"]
    lid = repo.save_lesion({"patient_id": pid, "name": "Lesão 1", "location": "pulmão", "kind": "target"})
    # medida no anterior, ligada à lesão: guarda a posição em mm
    vp_ant.go_to(20)
    m0 = vp_ant._new_annotation("line", [(100.0, 100.0), (120.0, 100.0)])
    vp_ant._finish(m0)
    vp_ant.link_lesion(m0, lid, "Lesão 1")
    assert m0.meta["centro"] and len(m0.meta["pontos_mm"]) == 2
    # sem registro entre os exames: a medida nova no atual não liga
    vp_atu.go_to(20)
    m1 = vp_atu._new_annotation("line", [(101.0, 100.0), (121.0, 100.0)])
    vp_atu._finish(m1)
    assert m1.meta.get("lesion") is None
    # com o registro (mesma posição): liga sozinha
    repo.save_registration(ant, atual, [0.0, 0.0, 0.0])
    m2 = vp_atu._new_annotation("line", [(102.0, 101.0), (122.0, 101.0)])
    vp_atu._finish(m2)
    assert m2.meta.get("lesion") == lid and m2.meta.get("mm") == pytest.approx(30.0, abs=0.5)
    # longe demais: não liga
    m3 = vp_atu._new_annotation("line", [(10.0, 10.0), (20.0, 10.0)])
    vp_atu._finish(m3)
    assert m3.meta.get("lesion") is None
    # desligado nas preferências
    w.settings.set("lesoes.ligar_sozinho", False)
    m4 = vp_atu._new_annotation("line", [(102.0, 102.0), (122.0, 102.0)])
    vp_atu._finish(m4)
    assert m4.meta.get("lesion") is None
    w.settings.set("lesoes.ligar_sozinho", True)
    # assistente: uma lesão nova medida só no anterior aparece como pendente
    lid2 = repo.save_lesion({"patient_id": pid, "name": "Lesão 2", "location": "fígado", "kind": "target"})
    m5 = vp_ant._new_annotation("line", [(60.0, 150.0), (75.0, 150.0)])
    vp_ant._finish(m5)
    vp_ant.link_lesion(m5, lid2, "Lesão 2")
    d = tab.assistente_de_seguimento()
    assert [x["lesao"]["name"] for x in d.itens] == ["Lesão 2"]
    tab._activate(vp_atu)
    d.acao("repetir")
    assert tab._ligar_proxima["lesion"] == lid2 and vp_atu.ghosts and tab.left_tool == "measure"
    m6 = tab.active._new_annotation("line", [(61.0, 150.0), (70.0, 150.0)])
    tab.active._finish(m6)
    assert m6.meta.get("lesion") == lid2 and tab._ligar_proxima is None
    d.recarregar()
    assert d.itens == []
    # pequena demais e ausente pelo assistente
    lid3 = repo.save_lesion({"patient_id": pid, "name": "Lesão 3", "location": "osso", "kind": "target"})
    m7 = vp_ant._new_annotation("line", [(30.0, 30.0), (40.0, 30.0)])
    vp_ant._finish(m7)
    vp_ant.link_lesion(m7, lid3, "Lesão 3")
    d.recarregar()
    d.acao("pequena")
    le3 = next(x for x in repo.lesions(pid) if x["id"] == lid3)
    assert le3["data"]["status"][tab.study_uid] == "pequena" and d.itens == []
    tab.lesions_action.trigger()
    app.processEvents()
    p = tab.lesion_panel
    heads = [p.table.horizontalHeaderItem(i).text() for i in range(p.table.columnCount())]
    rows = [p.table.item(r, 0).text() for r in range(p.table.rowCount())]
    assert "Nadir" in rows and any("●" in h for h in heads)
    d.close()
