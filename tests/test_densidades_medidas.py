"""0.100.46: a tela das densidades medidas e o modelo da NYU no pacote."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def test_modelo_da_nyu_vai_no_pacote():
    raiz = Path(__file__).resolve().parents[1]
    assert (raiz / "modelos" / "densidade_nyu.onnx").stat().st_size > 20_000_000
    spec = (raiz / "installer" / "ipe.spec").read_text(encoding="utf-8")
    assert '"ipe/modelos"' in spec                 # o mesmo lugar onde o programa procura (resource_dir()/modelos)
    from ipe.ai import densidade_nyu as N
    assert N.caminho() is not None


def test_lista_e_resumo(env):
    from ipe.db.models import Patient, Series, Study  # noqa: F401
    from ipe.ui import densidades_medidas as J
    _paths, db, repo = env
    with db.session() as s:
        p = Patient(patient_id="EX9", name="EXEMPLO^DENSIDADE")
        s.add(p)
        s.flush()
        for k in range(3):
            s.add(Study(study_uid=f"4.{k}", patient_fk=p.id, study_date=f"2026110{k + 1}", modalities="MG",
                        description="MAMOGRAFIA"))
    base = {"versao": 2, "nyu": "c", "nyu_probs": [0.1, 0.2, 0.6, 0.1], "area_pd": 40.0, "area": "b",
            "fcm_pd": 41.0, "fcm": "b", "aparelho": "GE"}
    repo.salvar_revisao_ia("4.0", "densidade", "auto", False, "", json.dumps(base))
    repo.salvar_revisao_ia("4.1", "densidade", "aceito", False, "med", json.dumps(dict(base, categoria="c")))
    repo.salvar_revisao_ia("4.2", "densidade", "editado", True, "med", json.dumps(dict(base, categoria="b")))
    linhas = repo.densidades_medidas("20261101", "20261130")
    assert [r["study_uid"] for r in linhas] == ["4.2", "4.1", "4.0"]
    assert linhas[0]["patient_name"] == "EXEMPLO^DENSIDADE" and linhas[0]["categoria"] == "b"
    assert len(J.filtrar(linhas, "pendentes")) == 1 and len(J.filtrar(linhas, "discordou")) == 1
    txt = J.resumo(linhas)
    assert "3 exame(s) medido(s), 2 confirmado(s)" in txt and "Rede (NYU): 50% iguais" in txt


def test_janela(env, tmp_path):
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QApplication

    from ipe.ui import densidades_medidas as J
    QApplication.instance() or QApplication([])
    _paths, db, repo = env
    from ipe.db.models import Patient, Study
    with db.session() as s:
        p = Patient(patient_id="EX8", name="EXEMPLO^JANELA")
        s.add(p)
        s.flush()
        s.add(Study(study_uid="6.1", patient_fk=p.id, study_date="20261110", modalities="MG"))
    repo.salvar_revisao_ia("6.1", "densidade", "aceito", False, "med",
                           json.dumps({"nyu": "d", "nyu_probs": [0, 0, 0.2, 0.8], "categoria": "d"}))
    abertos = []

    class Main:
        def open_study(self, uid):
            abertos.append(uid)

    j = J.DensidadesMedidasJanela(Main(), repo)
    j.de.setDate(QDate(2026, 11, 1))
    j.ate.setDate(QDate(2026, 11, 30))
    j.carregar()
    assert j.tabela.rowCount() == 1 and j.tabela.item(0, 5).text() == "D (80%)"
    assert j.tabela.item(0, 8).text() == "D" and j.tabela.item(0, 9).text() == "med"
    j.abrir_exame(j.tabela.model().index(0, 0))
    assert abertos == ["6.1"]
    j.gravar_csv(str(tmp_path / "d.csv"))
    assert "EXEMPLO^JANELA" in (tmp_path / "d.csv").read_text(encoding="utf-8-sig")
    j.close()
