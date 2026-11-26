"""0.100.123: exportar em lote os resultados das IAs para Excel."""
import zipfile

from ipe.automation import exportar_ias as EI


class _Repo:
    def __init__(self):
        self.infos = {"u1": {"patient_name": "Ana", "patient_id": "1", "study_date": "20260101",
                             "modalities": "CT", "description": "Tórax", "accession": "A1"},
                      "u2": {"patient_name": "Bia", "patient_id": "2", "study_date": "20260102",
                             "modalities": "MR", "description": "Fígado", "accession": "A2"},
                      "u3": {"patient_name": "Cai", "patient_id": "3", "study_date": "20260103",
                             "modalities": "CT", "description": "x", "accession": "A3"}}
        self.ach = {"u1": [{"ferramenta": "figado", "rotulo": "PDFF", "local": "", "estado": "sugerido",
                            "numeros": {"p": {"n": "PDFF", "u": "%", "v": 12.3456}}, "corrigidos": {}}],
                    "u2": [{"ferramenta": "figado", "rotulo": "PDFF", "local": "", "estado": "confirmado",
                            "numeros": {"p": {"n": "PDFF", "u": "%", "v": 5.0}}, "corrigidos": {"p": 6.0}}]}

    def study_info(self, uid):
        return self.infos.get(uid)

    def achados(self, uid, ferramenta=None):
        return self.ach.get(uid, [])

    def revisao_ia(self, uid, modulo):
        return None


def test_exporta_e_anonimiza(tmp_path):
    repo = _Repo()
    p = tmp_path / "x.xlsx"
    r = EI.exportar(repo, ["u1", "u2", "u3"], p, {"figado": "Fígado (PDFF)"}, anonimizar=True)
    assert r["exames"] == 3 and r["com_resultado"] == 2 and r["ias"] == ["Fígado (PDFF)"]
    z = zipfile.ZipFile(p)
    txt = "".join(z.read(n).decode("utf-8") for n in z.namelist() if n.endswith(".xml"))
    assert "Ana" not in txt and "Tórax" not in txt and "Caso 001" in txt
    assert "6" in txt                                   # o número corrigido vale


def test_com_identificacao(tmp_path):
    repo = _Repo()
    dados = EI.coletar(repo, ["u1", "u3"])
    f = dict(EI.folhas(dados))
    assert f["Exames"][0][0] == "Paciente" and f["Exames"][1][0] == "Ana"
    assert len(f["Exames"]) == 3
