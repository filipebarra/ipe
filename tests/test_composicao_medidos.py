"""0.100.132: Composição corporal e densidade óssea: medidas e confirmações, com a DMO digitada e a análise ROC."""
import csv
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QApplication

from ipe.ai import achados as AC
from ipe.ai import composicao as C
from ipe.ai import composicao_tabela as CT
from ipe.ai import densidade_osso as DO
from ipe.importer.scanner import Importer


def _itens(l1=140.0, l1l4=150.0):
    base = {"series_uid": "1.2", "modelo": "TS", "versao": "t", "local": "L3"}
    return [{**base, "rotulo": "L3", "tipo": C.TIPO_L3,
             "numeros": {"sma_cm2": AC.numero(91.7, "cm²", "SMA"), "vat_cm2": AC.numero(211.0, "cm²", "VAT"),
                         "sat_cm2": AC.numero(113.0, "cm²", "SAT")}},
            {**base, "rotulo": "F", "tipo": C.TIPO_FIGADO,
             "numeros": {"figado_hu": AC.numero(54.5, "HU", "Fígado"), "baco_hu": AC.numero(48.7, "HU", "Baço")}},
            {**base, "rotulo": "O", "tipo": DO.TIPO_OSSO,
             "numeros": {"l1_hu": AC.numero(l1, "HU", "L1"), "l1l4_hu": AC.numero(l1l4, "HU", "L1–L4"),
                         "niveis_n": AC.numero(4, "", "Níveis")}}]


def test_tabela_da_composicao_e_dmo(env, sample_dir, tmp_path):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    uid = repo.search_studies(limit=10)[0].study_uid
    ids = repo.gravar_achados(uid, C.FERRAMENTA, _itens())
    linhas = repo.composicao_medidos()
    assert len(linhas) == 1
    r = linhas[0]
    assert r["sma"] == 91.7 and r["l1"] == 140.0 and r["l1l4"] == 150.0 and r["dmo_coluna"] is None
    assert CT.situacao(r) == "Não revisada" and CT.filtrar(linhas, "sem_dmo") == linhas
    # a DMO digitada fica guardada no exame e volta na tabela
    repo.guardar_dmo(uid, {"coluna": "-2,7", "femur": -1.4})
    assert repo.dmo(uid) == {"coluna": "-2,7", "femur": -1.4}
    r = repo.composicao_medidos()[0]
    assert r["dmo_coluna"] == -2.7 and r["dmo_femur"] == -1.4 and CT.dmo_minima(r) == -2.7
    assert CT.classe_dmo(CT.dmo_minima(r)) == "osteoporose" and CT.filtrar([r], "com_dmo") == [r]
    # revisão: o médico confirma tudo
    for i in ids:
        repo.revisar_achado(i, "confirmado", "dra")
    r = repo.composicao_medidos()[0]
    assert CT.situacao(r) == "Revisada" and r["revisor"] == "dra"

    _app = QApplication.instance() or QApplication([])
    from ipe.ui.composicao_medidos import ComposicaoMedidosJanela
    j = ComposicaoMedidosJanela(SimpleNamespace(repo=repo, settings=None), repo)
    j.de.setDate(QDate(1900, 1, 1))
    j.carregar()
    assert j.tabela.rowCount() == 1
    assert j.tabela.item(0, 9).text() == "140,0" and j.tabela.item(0, 12).text() == "-2,7"
    # digitar a DMO do fêmur na célula grava no exame
    j.tabela.item(0, 13).setText("-2,6")
    assert repo.dmo(uid)["femur"] == -2.6
    j.comparar()
    assert len(j.lb_analise.text().splitlines()) == 4          # L1 e L1–L4 × osteoporose e baixa densidade
    destino = tmp_path / "c.csv"
    j.gravar_csv(str(destino))
    with open(destino, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert rows[0] == CT.CSV_CAB
    assert rows[1][CT.CSV_CAB.index("l1_hu")] == "140.0" and rows[1][CT.CSV_CAB.index("dmo_classe")] == "osteoporose"
    j.close()


def test_analise_roc_do_osso():
    # 6 com osteoporose (HU baixo) e 6 sem (HU alto), um par trocado
    def r(hu1, t):
        return {"l1": hu1, "l1l4": hu1 + 10, "dmo_coluna": t, "dmo_femur": None}
    linhas = [r(h, -3.0) for h in (60, 80, 95, 105, 120, 150)] + [r(h, -0.5) for h in (110, 140, 170, 190, 210, 240)]
    a = CT.analise_osso(linhas, "l1", "osteoporose", {"osteo": 110, "baixa": 135, "normal": 160})
    assert a["n"] == 12 and a["positivos"] == 6 and a["negativos"] == 6
    # pares (doente < sem doença): só o 120 e o 150 perdem para o 110 (e 140 do 150): AUC alta, não perfeita
    assert 0.9 < a["auc"] < 1.0
    assert a["corte"] in (105, 120, 110)           # o corte de Youden fica entre os grupos
    assert a["nos_cortes"]["osteo"]["sens"] == pytest.approx(4 / 6)       # 60, 80, 95, 105 ≤ 110
    assert a["nos_cortes"]["osteo"]["esp"] == pytest.approx(5 / 6)        # só o 110 sem doença cai em ≤ 110
    # sem os dois grupos não há AUC
    so_doentes = CT.analise_osso([r(60, -3.0)], "l1", "osteoporose")
    assert so_doentes["auc"] is None and "precisa" in CT.texto_da_analise(so_doentes)
    assert "sem exames" in CT.texto_da_analise(CT.analise_osso([], "l1"))
    # "baixa" inclui a osteopenia (T < −1)
    mistos = [r(100, -1.5), r(200, -0.2)]
    assert CT.analise_osso(mistos, "l1", "baixa")["positivos"] == 1
    assert CT.analise_osso(mistos, "l1", "osteoporose")["positivos"] == 0
    assert "AUC" in CT.texto_da_analise(a)
