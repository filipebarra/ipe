"""0.100.101: Fígado na RM: medidas e confirmações — a tabela da esteatose, do ferro e da rigidez."""
import csv

from PySide6.QtWidgets import QApplication

from ipe.ai import achados as AC
from ipe.ai import figado_rm as F
from ipe.ai import figado_tabela as FT
from ipe.importer.scanner import Importer


def _itens():
    base = {"series_uid": "1.2", "modelo": "TS", "versao": "t", "local": "fígado"}
    return [{**base, "rotulo": "PDFF", "tipo": F.TIPO_GORDURA,
             "numeros": {"pdff_mediana": AC.numero(13.0, "%", "PDFF (mediana)")}},
            {**base, "rotulo": "R2*", "tipo": F.TIPO_FERRO,
             "numeros": {"r2_mediana": AC.numero(87.0, "s⁻¹", "R2*"), "lic": AC.numero(2.41, "mg Fe/g", "LIC")}},
            {**base, "rotulo": "MRE", "tipo": F.TIPO_RIGIDEZ,
             "numeros": {"kpa_media": AC.numero(5.2, "kPa", "Rigidez")}}]


def test_tabela_do_figado(env, sample_dir, tmp_path):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    uid = repo.search_studies(limit=10)[0].study_uid
    ids = repo.gravar_achados(uid, F.FERRAMENTA, _itens())
    linhas = repo.figados_medidos()
    assert len(linhas) == 1
    r = linhas[0]
    assert r["pdff"] == 13.0 and r["grau"] == 1 and r["lic"] == 2.41 and r["kpa"] == 5.2
    assert r["faixa"] and r["faixa"] != "normal"
    assert FT.situacao(r) == "Não revisada"
    assert FT.filtrar(linhas, "esteatose") == linhas and FT.filtrar(linhas, "ferro") == []
    assert FT.filtrar(linhas, "rigidez") == linhas
    # o médico corrige a gordura e confirma o resto: a tabela mostra os números que valem
    repo.revisar_achado(ids[0], "corrigido", "dra", {"pdff_mediana": 4.0})
    repo.revisar_achado(ids[1], "confirmado", "dra")
    repo.revisar_achado(ids[2], "confirmado", "dra")
    r = repo.figados_medidos()[0]
    assert r["pdff"] == 4.0 and r["gordura"].startswith("Sem esteatose")
    assert FT.situacao(r) == "Revisada" and r["revisor"] == "dra"
    c = FT.resumo([r])
    assert c["exames"] == 1 and c["revisados"] == 1 and c["esteatose"] == 0

    _app = QApplication.instance() or QApplication([])
    from types import SimpleNamespace

    from ipe.ui.figados_medidos import FigadosMedidosJanela
    from PySide6.QtCore import QDate
    j = FigadosMedidosJanela(SimpleNamespace(repo=repo), repo)
    j.de.setDate(QDate(1900, 1, 1))
    j.carregar()
    assert j.tabela.rowCount() == 1
    assert j.tabela.item(0, 4).text().startswith("4,0")
    destino = tmp_path / "f.csv"
    j.gravar_csv(str(destino))
    with open(destino, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert rows[0] == FT.CSV_CAB and rows[1][FT.CSV_CAB.index("rigidez_kpa")] == "5.20"
    j.close()
