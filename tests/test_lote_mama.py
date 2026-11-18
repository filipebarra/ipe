"""0.100.69: pesquisa em lote — as mamografias de uma planilha, do PACS, com densidade e calcificações vasculares.
Só dados inventados."""
import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from ipe.automation import lote_mama as L  # noqa: E402

CAB = ["ID", "Paciente", "Nascimento", "Sexo", "Data mamografia", "Densidade", "Data TC", "Agatston"]


# ---------------------------------------------------------------- planilha
def test_xlsx_vai_e_volta_e_abre_no_openpyxl(tmp_path):
    linhas = [CAB, ["0012345", "FANTOMA UM", datetime(1960, 5, 4), "feminino", datetime(2024, 3, 9), "B",
                    datetime(2024, 4, 1), 0],
              ["778", "FANTOMA <DOIS> & \"CIA\"", None, "feminino", "09/03/2024", None, "", 12.5],
              [],
              ["9", "ÚLTIMA\x07 linha", True, "", 20240309, "", "", -3]]
    p = tmp_path / "saida.xlsx"
    L.gravar_xlsx(p, [("Resultados", linhas), ("LEIA-ME", [["uma linha"], ["outra: áéí"]]), ("Aba [ruim]/:*?", [["x", 1]])])
    assert not (tmp_path / "saida.xlsx.gravando").exists()
    assert L.abas(p) == ["Resultados", "LEIA-ME", "Aba  ruim"]
    lido = L.ler_planilha(p)
    assert lido[0] == CAB and lido[1][0] == "0012345" and lido[1][2] == "04/05/1960" and lido[1][7] == 0
    assert lido[2][1] == 'FANTOMA <DOIS> & "CIA"' and lido[2][7] == 12.5 and lido[3] == []
    assert lido[4][1] == "ÚLTIMA  linha" and lido[4][2] == "sim" and lido[4][7] == -3
    assert L.ler_planilha(p, "LEIA-ME") == [["uma linha"], ["outra: áéí"]]
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.load_workbook(p)
    ws = wb["Resultados"]
    assert [c.value for c in ws[1]] == CAB and ws["A2"].value == "0012345" and ws["H3"].value == 12.5
    assert ws["A1"].font.b and ws.freeze_panes == "A2" and wb.sheetnames[2] == "Aba  ruim"


def test_le_planilha_feita_no_excel(tmp_path):
    """Texto compartilhado, datas de verdade, inteiros, células vazias no meio e duas abas."""
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "LEIA-ME"
    ws.append(["Estudo de teste"])
    ws2 = wb.create_sheet("Pareamento")
    ws2.append(CAB)
    ws2.append(["0012345", "FANTOMA UM", datetime(1960, 5, 4), "feminino", datetime(2024, 3, 9), "B",
                datetime(2024, 4, 1), 0])
    ws2.append(["778", "FANTOMA DOIS", datetime(1955, 1, 31), "feminino", datetime(2023, 12, 1), None, None, 431])
    ws2["E3"].number_format = "DD/MM/YYYY"
    p = tmp_path / "lista.xlsx"
    wb.save(p)
    assert L.abas(p) == ["LEIA-ME", "Pareamento"]
    dados = L.ler_planilha(p, "Pareamento")
    assert dados[0] == CAB and dados[1][0] == "0012345" and dados[1][4] == datetime(2024, 3, 9)
    assert dados[2][4] == datetime(2023, 12, 1) and dados[2][7] == 431 and dados[2][5] is None
    col = L.achar_colunas(dados[0])
    assert col == {"id": 0, "data": 4, "nascimento": 2, "nome": 1}
    ls = L.montar_linhas(dados[1:], col)
    assert [(l.pid, l.data, l.nascimento) for l in ls] == [("0012345", "20240309", "19600504"),
                                                           ("778", "20231201", "19550131")]
    assert ls[0].chave == "0012345|20240309" and ls[1].n == 1


def test_csv_e_datas(tmp_path):
    p = tmp_path / "lista.csv"
    p.write_bytes("Prontuário;Nome;Data da mamografia\r\n123;FANTOMA TRÊS;09/03/2024\r\n".encode("cp1252"))
    d = L.ler_planilha(p)
    assert d[0] == ["Prontuário", "Nome", "Data da mamografia"] and L.abas(p) == []
    assert L.achar_colunas(d[0]) == {"id": 0, "data": 2, "nascimento": -1, "nome": 1}
    assert [L.para_data(x) for x in ("09/03/2024", "2024-03-09", "2024-03-09 00:00:00", "20240309", 20240309, 45360,
                                     45360.0, datetime(2024, 3, 9), "9.3.2024", "", None, "ontem", 7)] == \
        ["20240309"] * 9 + ["", "", "", ""]
    assert [L.para_id(x) for x in (123.0, " 0045 ", None, 7)] == ["123", "0045", "", "7"]


# ---------------------------------------------------------------- o lote, com dublês
D = {"versao": 2, "nyu": "c", "nyu_probs": [0.05, 0.15, 0.7, 0.1], "nyu_aviso": "", "avisos": [],
     "aparelho": "Aparelho X", "quando": "2026-11-18 10:00"}
C = {"versao": 4, "sugestao": "moderada", "area_mm2": 41.25, "por_mama": {"R": 41.25, "L": 3.0}, "aviso": "",
     "avisos": ["Faltam incidências: L-MLO."], "aparelho": "Aparelho X", "quando": "2026-11-18 10:01",
     "vistas": {"R-CC": {"area_mm2": 41.25}, "L-CC": {"area_mm2": 3.0}, "R-MLO": {"area_mm2": 12.0}},
     "imagens": [{"protese": False}, {"protese": False}, {"protese": False}],
     "escalas": {"csbi": {"grau": 2, "vasos": 2}, "margolies": {"total": 5, "categoria": "moderada_acentuada"},
                 "loberant": {"grau": 2}, "bacss": {"maior": 4}}}


class Ipe:
    """O Ipê de mentira: o que tem no banco, o que tem no PACS e o que acontece."""

    def __init__(self):
        self.banco = {("L1", "20240101"): [{"study_uid": "1.1", "accession": "A1", "study_date": "20240101",
                                            "description": "MAMOGRAFIA DIGITAL", "num_images": 4}]}
        self.no_pacs = {
            ("P1", "20240102"): [{"study_uid": "2.1", "accession": "B1", "study_date": "20240102",
                                  "birth_date": "19600504", "num_images": 4}],
            ("P2", "20240103"): [{"study_uid": "2.2", "birth_date": "19700101", "num_images": 4}],     # outra pessoa
            ("P3", "20240104"): [{"study_uid": "2.3", "num_images": 4}],                               # não baixa
            ("P4", "20240105"): [{"study_uid": "2.4", "num_images": 1}, {"study_uid": "2.5", "num_images": 5}],
            ("P5", "20240106"): [{"study_uid": "2.6", "num_images": 4}],                               # sem 2D
            ("P6", "20240107"): [{"study_uid": "2.7", "num_images": 4}],                               # estoura
        }
        self.baixados, self.medidos, self.apagados, self.buscas = [], [], [], []
        self.falha_download = {"2.3"}

    def servicos(self):
        def pacs(pid, data):
            self.buscas.append((pid, data))
            return self.no_pacs.get((pid, data), [])

        def baixar(ex, parar=None):
            if ex["study_uid"] in self.falha_download:
                return False, "o PACS recusou"
            self.baixados.append(ex["study_uid"])
            return True, "4 imagens baixadas"

        def medir(uid, parar=None):
            self.medidos.append(uid)
            if uid == "2.7":
                raise RuntimeError("a rede caiu")
            if uid == "2.6":
                return ({"versao": 2, "nyu": None, "nyu_probs": [], "nyu_aviso": "A rede precisa das quatro incidências."},
                        {"versao": 4, "sugestao": None, "area_mm2": None, "aviso": "Nenhuma imagem de mamografia 2D.",
                         "imagens": []})
            return dict(D), dict(C)
        return L.Servicos(local=lambda pid, data: self.banco.get((pid, data), []), pacs=pacs, baixar=baixar,
                          medir=medir, apagar=self.apagados.append)


DADOS = [["L1", "FANTOMA A", "04/05/1960", "f", "01/01/2024", "B", "", 0],
         ["P1", "FANTOMA B", "04/05/1960", "f", "02/01/2024", "C", "", 10],
         ["P2", "FANTOMA C", "04/05/1960", "f", "03/01/2024", "A", "", 0],
         ["P3", "FANTOMA D", "", "f", "04/01/2024", "", "", 0],
         ["P4", "FANTOMA E", "", "f", "05/01/2024", "", "", 0],
         ["P5", "FANTOMA F", "", "f", "06/01/2024", "", "", 0],
         ["P6", "FANTOMA G", "", "f", "07/01/2024", "", "", 0],
         ["NAO", "FANTOMA H", "", "f", "08/01/2024", "", "", 0],
         ["", "FANTOMA I", "", "f", "", "", "", 0],
         [None, None, None]]


def _lote(tmp_path, ipe, **op):
    linhas = L.montar_linhas(DADOS, L.achar_colunas(CAB))
    return L.Lote(CAB, DADOS, linhas, ipe.servicos(), tmp_path / "saida.xlsx", L.Opcoes(gravar_a_cada=3, **op))


def test_lote_cada_situacao(tmp_path):
    ipe = Ipe()
    lote = _lote(tmp_path, ipe)
    assert len(lote.linhas) == 9 and len(lote.por_fazer()) == 9
    vistos = []
    a = lote.rodar(avisar=lambda a, l, r: vistos.append((l.pid, r["situacao"], a.feitos)))
    assert [v[:2] for v in vistos] == [
        ("L1", L.MEDIDO), ("P1", L.MEDIDO), ("P2", L.OUTRA_PESSOA), ("P3", L.SEM_DOWNLOAD), ("P4", L.MEDIDO),
        ("P5", L.SEM_IMAGENS), ("P6", L.ERRO), ("NAO", L.NAO_ACHADO), ("", L.SEM_ID)]
    assert [v[2] for v in vistos] == list(range(1, 10)) and a.total == 9 and a.feitos == 9
    assert a.contagem == {L.MEDIDO: 3, L.OUTRA_PESSOA: 1, L.SEM_DOWNLOAD: 1, L.SEM_IMAGENS: 1, L.ERRO: 1,
                          L.NAO_ACHADO: 1, L.SEM_ID: 1}
    # o que já estava no Ipê não é buscado no PACS, nem baixado, nem apagado
    assert ("L1", "20240101") not in ipe.buscas and "1.1" not in ipe.baixados + ipe.apagados
    # a outra pessoa não é baixada nem medida; do dia com dois exames, o de mais imagens
    assert "2.2" not in ipe.baixados + ipe.medidos and "2.5" in ipe.medidos and "2.4" not in ipe.medidos
    # tudo o que foi baixado para o lote é apagado — também quando a medida estoura
    assert ipe.baixados == ["2.1", "2.5", "2.6", "2.7"] and ipe.apagados == ["2.1", "2.5", "2.6", "2.7"]
    r = lote.resultados["P1|20240102"]
    assert r["densidade"] == "C" and r["prob_c"] == 0.7 and r["bac_grau"] == "Moderada" and r["bac_area"] == 41.25
    assert r["bac_area_d"] == 41.25 and r["bac_area_e"] == 3.0 and r["bac_R-MLO"] == 12.0 and "bac_L-MLO" not in r
    assert r["csbi"] == 2 and r["margolies_cat"] == "Moderada a acentuada" and r["protese"] == "não"
    assert r["de_onde"] == "baixado do PACS" and r["accession"] == "B1" and r["exames_no_dia"] == 1
    assert "Faltam incidências" in r["bac_aviso"] and r["versoes"] == "densidade 2, calcificações 4"
    assert lote.resultados["L1|20240101"]["de_onde"] == "já estava no Ipê"
    assert "No dia há 2 exames de mamografia" in lote.resultados["P4|20240105"]["observacao"]
    assert lote.resultados["P6|20240107"]["observacao"] == "a rede caiu"
    assert lote.resultados["P3|20240104"]["observacao"] == "o PACS recusou"
    assert "quatro incidências" in lote.resultados["P5|20240106"]["densidade_aviso"]
    # a planilha: as colunas originais, depois as do Ipê; a linha vazia do fim fica de fora
    t = L.ler_planilha(tmp_path / "saida.xlsx")
    assert len(t) == 10 and t[0][:8] == CAB and t[0][8] == "Ipê: situação" and len(t[0]) == 8 + len(L.COLUNAS)
    chaves = [k for k, _t in L.COLUNAS]
    assert t[2][0] == "P1" and t[2][7] == 10 and t[2][8] == L.MEDIDO
    assert t[2][8 + chaves.index("densidade")] == "C" and t[2][8 + chaves.index("bac_area")] == 41.25
    assert t[2][8 + chaves.index("study_uid")] == "2.1" and t[3][8] == L.OUTRA_PESSOA
    assert L.abas(tmp_path / "saida.xlsx") == ["Resultados", "Resumo", "LEIA-ME"]
    resumo = dict((r[0], r[1]) for r in L.ler_planilha(tmp_path / "saida.xlsx", "Resumo") if len(r) > 1)
    assert resumo["Linhas na lista"] == 9 and resumo[L.MEDIDO] == 3 and resumo["C"] == 3 and resumo["Moderada"] == 3
    assert json.loads((tmp_path / "saida.xlsx.andamento.json").read_text(encoding="utf-8"))["versao"] == 1


def test_continuar_refaz_so_o_que_falhou(tmp_path):
    ipe = Ipe()
    _lote(tmp_path, ipe).rodar()
    # agora o PACS deixa baixar, a rede voltou e o exame que faltava apareceu
    ipe2 = Ipe()
    ipe2.falha_download = set()
    ipe2.no_pacs[("NAO", "20240108")] = [{"study_uid": "2.9", "num_images": 4}]
    ipe2.no_pacs[("P6", "20240107")] = [{"study_uid": "2.8", "num_images": 4}]
    lote = _lote(tmp_path, ipe2)
    assert [l.pid for l in lote.por_fazer()] == ["P3", "P6", "NAO"]
    a = lote.rodar()
    assert ipe2.medidos == ["2.3", "2.8", "2.9"] and a.nesta_rodada == 3 and a.feitos == 9
    assert a.contagem[L.MEDIDO] == 6 and L.ERRO not in a.contagem and L.NAO_ACHADO not in a.contagem
    assert _lote(tmp_path, Ipe()).por_fazer() == []
    # sem "tentar de novo", o que tem resposta fica como está
    (tmp_path / "b").mkdir()
    primeiro = _lote(tmp_path / "b", Ipe())
    primeiro.rodar()
    assert _lote(tmp_path / "b", Ipe(), refazer_erros=False).por_fazer() == []


def test_limite_parar_e_nao_apagar(tmp_path):
    ipe = Ipe()
    lote = _lote(tmp_path, ipe, limite=2, apagar_depois=False)
    a = lote.rodar()
    assert a.nesta_rodada == 2 and a.feitos == 2 and a.total == 9 and ipe.apagados == []
    assert len(L.ler_planilha(tmp_path / "saida.xlsx")) == 10             # a planilha sai inteira, com o que há
    # parar no meio: a linha em curso termina, o resto fica para depois
    ipe = Ipe()
    parar = threading.Event()
    lote = _lote(tmp_path, ipe)
    a = lote.rodar(parar, avisar=lambda a, l, r: parar.set())
    assert a.nesta_rodada == 1 and len(lote.por_fazer()) == 6
    # linha repetida na lista (mesmo ID e data) é feita uma vez e sai nas duas
    ipe = Ipe()
    dados = [DADOS[1], DADOS[1]]
    lote = L.Lote(CAB, dados, L.montar_linhas(dados, L.achar_colunas(CAB)), ipe.servicos(), tmp_path / "rep.xlsx")
    a = lote.rodar()
    assert ipe.medidos == ["2.1"] and a.total == 1
    t = L.ler_planilha(tmp_path / "rep.xlsx")
    assert t[1][8] == t[2][8] == L.MEDIDO


def test_duracao_estimada():
    a = L.Andamento(total=100, feitos=10, nesta_rodada=2, inicio=time.time() - 20)
    assert a.falta_s() is None
    a.nesta_rodada = 10
    assert 150 < a.falta_s() < 220


# ---------------------------------------------------------------- com o PACS de verdade (em laço) e a janela
@pytest.fixture()
def cena(env, tmp_path, monkeypatch):
    import numpy as np
    from PySide6.QtWidgets import QApplication
    from pydicom.uid import generate_uid
    from test_gestao import No
    from test_web_mamografia import _serie
    from ipe.ai import calc_vascular as CV
    from ipe.ai import densidade_nyu as N
    from ipe.core.config import Settings
    from ipe.network.service import NetworkService
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    ex = {"uid": generate_uid(), "date": "20240309", "accession": "MGL1", "description": "MAMOGRAFIA DIGITAL",
          "for": generate_uid()}
    for k, (lado, view) in enumerate((("R", "CC"), ("L", "CC"), ("R", "MLO"), ("L", "MLO"))):
        _serie(tmp_path / "mg", ex, lado, view, k + 1, "right" if lado == "R" else "left")
    pacs = No(tmp_path / "pacs", "PACS")
    pacs.importar(tmp_path / "mg")
    assert pacs.server.start()
    info = pacs.repo.study_info(ex["uid"])
    st = Settings(paths.settings_file)
    st.set("dicom", dict(st.get("dicom", {}), enabled=False, http_enabled=False, ae_title="IPE"))
    net = NetworkService(db, repo, paths.storage, st)
    no = dict(pacs.como_no(), active=True)
    no.pop("id")
    no["id"] = repo.save_node(no)
    monkeypatch.setattr(N, "disponivel", lambda dados=None: (True, ""))
    monkeypatch.setattr(N, "do_exame", lambda vistas, dados=None: (np.array([0.05, 0.15, 0.7, 0.1]), ""))
    monkeypatch.setattr(CV, "disponivel", lambda dados=None: (True, ""))

    def mapa(img, dados=None, stop=None):
        p = np.zeros(img.shape, np.float32)
        p[img.shape[0] // 2: img.shape[0] // 2 + 60, img.shape[1] // 3: img.shape[1] // 3 + 3] = 0.9
        return p
    monkeypatch.setattr(CV, "mapa", mapa)
    yield {"app": app, "repo": repo, "net": net, "st": st, "storage": paths.storage, "no": no, "ex": ex,
           "pid": info["patient_id"], "nasc": info.get("birth_date", ""), "pacs": pacs, "tmp": tmp_path}
    net.shutdown()
    pacs.close()


def _girar(app, cond, s=90):
    fim = time.time() + s
    while time.time() < fim:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_do_pacs_ate_a_planilha_pela_janela(cena, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from ipe.automation import lote_mama_ipe as LI
    from ipe.ui.lote_mama_dialogo import LoteMamaDialog
    c = cena
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: avisos.append(a[2])))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: avisos.append(a[2])))
    assert LI.pronto_para_medir(c["repo"]) == (True, "")
    lista = c["tmp"] / "lista.xlsx"
    L.gravar_xlsx(lista, [("LEIA-ME", [["Lista de teste"]]),
                          ("Pareamento", [["ID", "Paciente", "Nascimento", "Data mamografia", "Agatston"],
                                          [c["pid"], "FANTOMA", "", "09/03/2024", 120],
                                          ["000000", "NINGUEM", "", "09/03/2024", 0],
                                          [c["pid"], "FANTOMA", "", "10/03/2024", 5]])])
    d = LoteMamaDialog(c["repo"], c["net"], c["st"], c["storage"], None)
    d.iniciar()
    assert "Escolha a planilha" in avisos[-1]
    assert d.abrir_arquivo(str(lista))
    assert d.c_aba.currentText() == "Pareamento"                 # a aba com ID e data, não o LEIA-ME
    assert d.c_id.currentText() == "ID" and d.c_data.currentText() == "Data mamografia"
    assert d.c_nasc.currentData() == 2 and d.c_no.count() == 1 and d.e_saida.text().endswith("lista-Ipe.xlsx")
    assert "Na aba: 3 linhas; 3 com ID e data." in d.l_lista.text()
    d.iniciar()
    assert d.b_parar.isEnabled() and not d.b_iniciar.isEnabled()
    assert _girar(c["app"], lambda: d.linha_de_fundo is None), d.diario.toPlainText()
    texto = d.diario.toPlainText()
    assert "Linha 2: medido — densidade C, BAC" in texto and "Linha 3: não encontrado no PACS" in texto, texto
    assert "FANTOMA" not in texto and "Terminado." in d.l_estado.text() and d.barra.value() == 3
    t = L.ler_planilha(d.e_saida.text())
    chaves = [k for k, _t in L.COLUNAS]
    assert t[0][:5] == ["ID", "Paciente", "Nascimento", "Data mamografia", "Agatston"] and t[1][4] == 120
    r = dict(zip(chaves, t[1][5:]))
    assert r["situacao"] == L.MEDIDO and r["study_uid"] == c["ex"]["uid"] and r["accession"] == "MGL1"
    assert r["densidade"] == "C" and r["prob_c"] == 0.7 and r["bac_area"] > 0 and r["bac_grau"]
    assert r["de_onde"] == "baixado do PACS" and r["bac_imagens"] == 4 and r["data_exame"] == "20240309"
    assert t[2][5] == L.NAO_ACHADO and t[3][5] == L.NAO_ACHADO
    # o PACS guarda o ID de outro jeito (zeros à esquerda): acha assim mesmo
    serv = LI.servicos(c["repo"], c["net"], c["st"], c["no"], None, c["storage"])
    assert [e["study_uid"] for e in serv.pacs("000" + c["pid"], "20240309")] == [c["ex"]["uid"]]
    assert serv.pacs("9" + c["pid"], "20240309") == [] and serv.pacs(c["pid"], "20240310") == []
    # o exame foi baixado só para medir: não ficou no Ipê
    assert c["repo"].study_info(c["ex"]["uid"]) is None
    # de novo: nada a fazer, e a janela diz
    d.k_refazer.setChecked(False)
    d.iniciar()
    assert "já têm resposta" in avisos[-1]
    # sem apagar, noutra saída: o exame fica no Ipê; na terceira rodada ele "já estava no Ipê"
    d.e_saida.setText(str(c["tmp"] / "fica.xlsx"))
    d.k_apagar.setChecked(False)
    d.s_limite.setValue(1)
    d.iniciar()
    assert _girar(c["app"], lambda: d.linha_de_fundo is None)
    assert c["repo"].study_info(c["ex"]["uid"]) is not None
    d.e_saida.setText(str(c["tmp"] / "terceira.xlsx"))
    d.k_apagar.setChecked(True)
    d.iniciar()
    assert _girar(c["app"], lambda: d.linha_de_fundo is None)
    r = dict(zip(chaves, L.ler_planilha(c["tmp"] / "terceira.xlsx")[1][5:]))
    assert r["de_onde"] == "já estava no Ipê" and r["situacao"] == L.MEDIDO
    assert c["repo"].study_info(c["ex"]["uid"]) is not None          # o que já estava nunca é apagado
    d.close()


def test_sem_modelo_ou_cliente_nao_comeca(cena, monkeypatch):
    from ipe.ai import calc_vascular as CV
    from ipe.automation import lote_mama_ipe as LI
    monkeypatch.setattr(CV, "disponivel", lambda dados=None: (False, "o arquivo do modelo não está instalado"))
    ok, motivo = LI.pronto_para_medir(cena["repo"])
    assert not ok and "calcificações vasculares" in motivo and "não está instalado" in motivo

    class Cliente:
        def is_cached(self, uid):
            return False
    ok, motivo = LI.pronto_para_medir(Cliente())
    assert not ok and "cliente de um servidor" in motivo
    # zeros à esquerda: o PACS guarda "123" e a lista traz "000123" (e vice-versa); outro paciente fica de fora
    achados = [{"patient_id": "123", "modalities": "MG"}, {"patient_id": "9123", "modalities": "MG"},
               {"patient_id": "0123", "modalities": "US"}]
    assert LI._so_mg(achados, "000123") == [achados[0]]
    assert LI._so_mg([{"patient_id": "123", "modalities": ""}], "123") == [{"patient_id": "123", "modalities": ""}]
