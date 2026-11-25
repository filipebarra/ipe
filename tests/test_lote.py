"""Lote a partir de planilha (0.100.97): o motor com dublês, sem rede nem Qt."""
from __future__ import annotations

import threading
import zipfile
from datetime import datetime

import pytest

from ipe.automation import lote as L
from ipe.automation import planilha as P


# ---------------------------------------------------------------------- planilhas
def _ods(caminho, linhas):
    cel = []
    for linha in linhas:
        cs = []
        for v in linha:
            if isinstance(v, (int, float)):
                cs.append(f'<table:table-cell office:value-type="float" office:value="{v}"><text:p>{v}</text:p>'
                          '</table:table-cell>')
            else:
                cs.append(f'<table:table-cell office:value-type="string"><text:p>{v}</text:p></table:table-cell>')
        cel.append("<table:table-row>" + "".join(cs) + '<table:table-cell table:number-columns-repeated="1000"/>'
                   "</table:table-row>")
    xml = ('<?xml version="1.0" encoding="UTF-8"?><office:document-content '
           'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
           'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
           'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"><office:body><office:spreadsheet>'
           '<table:table table:name="Pacientes">' + "".join(cel) +
           '<table:table-row table:number-rows-repeated="1048000"><table:table-cell/></table:table-row>'
           '</table:table></office:spreadsheet></office:body></office:document-content>')
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("content.xml", xml)


def test_planilhas_ods_tsv_e_xls(tmp_path):
    _ods(tmp_path / "a.ods", [["Prontuário", "Data do exame", "Agatston"], ["00123", "15/03/2024", 12.5]])
    assert P.abas(tmp_path / "a.ods") == ["Pacientes"]
    assert P.ler_planilha(tmp_path / "a.ods") == [["Prontuário", "Data do exame", "Agatston"],
                                                  ["00123", "15/03/2024", 12.5]]
    (tmp_path / "b.tsv").write_text("ID\tAcesso\tData\n1,5\tA9\t2024-01-02\n", encoding="utf-8")
    assert P.ler_planilha(tmp_path / "b.tsv")[1] == ["1,5", "A9", "2024-01-02"]
    with pytest.raises(ValueError, match="xlsx"):
        P.ler_planilha(tmp_path / "c.xls")


def test_adivinhar_colunas():
    cab = ["Nome do paciente", "Prontuário", "Nº de acesso", "Data da mamografia", "Data de nascimento",
           "Agatston", "Study Instance UID"]
    assert L.adivinhar_colunas(cab) == ["nome", "id", "acesso", "data", "nascimento", "ignorar", "uid"]
    assert L.adivinhar_colunas(["Patient ID", "Accession", "Study Date", "DOB"]) == ["id", "acesso", "data",
                                                                                    "nascimento"]


def test_criterio_e_linha_sem_data():
    cfg = L.Config(tolerancia_dias=2, modalidades=["MG"])
    l = L.Linha(0, pid="1", data="20240310")
    c = l.criterio(cfg)
    assert c["data_de"] == "20240308" and c["data_ate"] == "20240312" and c["modalidades"] == ["MG"]
    assert L.Linha(0, acesso="A1").criterio(cfg)["acesso"] == "A1"
    assert L.Linha(0, pid="1").criterio(cfg) is None


def test_janela_de_horario():
    assert L.em_janela(datetime(2026, 1, 1, 23, 0), "20:00", "06:00")
    assert L.em_janela(datetime(2026, 1, 1, 5, 59), "20:00", "06:00")
    assert not L.em_janela(datetime(2026, 1, 1, 12, 0), "20:00", "06:00")
    assert L.em_janela(datetime(2026, 1, 1, 12, 0), "", "")


# ---------------------------------------------------------------------- o lote com dublês
def _ex(uid, pid, data, n=10, nasc="19600101", mods="MG", acc=""):
    return {"study_uid": uid, "patient_id": pid, "birth_date": nasc, "accession": acc or uid, "study_date": data,
            "study_time": "100000", "description": "MAMOGRAFIA", "modalities": mods, "num_images": n}


class Dubles:
    def __init__(self):
        self.banco = {"U1": _ex("U1", "1", "20240310")}
        self.pacs = {"U2": _ex("U2", "002", "20240311"), "U3": _ex("U3", "3", "20240401", n=4),
                     "U4": _ex("U4", "3", "20240401", n=8), "U5": _ex("U5", "5", "20240501", nasc="19700101"),
                     "U6": _ex("U6", "6", "20240601")}
        self.baixados, self.apagados, self.enviados, self.impressos, self.exportados = [], [], [], [], []

    def servicos(self):
        def busca(fonte, crit):
            return [e for e in fonte.values()]
        return L.Servicos(
            local=lambda c: busca(self.banco, c),
            no=lambda no, c: busca(self.pacs, c),
            tem=lambda uid: uid in self.banco,
            baixar=self.baixar,
            ias=lambda uid, tipos, refazer, parar: {
                t: {"titulo": "Densidade" if t == "densidade" else t, "situacao": "feita", "motivo": "",
                    "campos": {"Categoria": "C", "Área (mm²)": 12.0}, "series": [f"{uid}.conf"]} for t in tipos},
            protocolo=lambda uid: {"Situação": "conforme"},
            enviar=lambda uid, no, series: self.enviados.append((uid, no, series)) or "ok",
            imprimir=lambda uid, series, destino, titulo: self.impressos.append((uid, titulo)) or "1 folha",
            exportar=lambda uid, series, pasta, nome, fmt, dicom, anon: self.exportados.append(nome) or "1 PNG",
            apagar=lambda uid: self.apagados.append(uid),
            nome_no=lambda no: {"pacs": "PACS"}.get(no, no))

    def baixar(self, no, ex, parar):
        self.baixados.append(ex["study_uid"])
        if ex["study_uid"] == "U6":
            return False, "C-GET falhou"
        return True, "ok"


def _lote(tmp_path, cfg, linhas_dados, simular=False):
    cab = ["Prontuário", "Nome", "Data do exame", "Nascimento", "Agatston"]
    dados = [list(x) for x in linhas_dados]
    cfg.colunas = L.adivinhar_colunas(cab)
    linhas = L.montar_linhas(dados, cfg.colunas)
    d = Dubles()
    lote = L.Lote(cab, dados, linhas, cfg, d.servicos(), tmp_path / "saida.xlsx", simular=simular)
    return lote, d


DADOS = [
    ["1", "ANA EXEMPLO", "10/03/2024", "01/01/1960", 0],      # já no banco
    ["2", "BIA EXEMPLO", "10/03/2024", "01/01/1960", 5],      # no PACS com zeros (002), um dia depois
    ["3", "CIA EXEMPLO", "01/04/2024", "01/01/1960", 100],    # dois no dia
    ["5", "DIA EXEMPLO", "01/05/2024", "01/01/1960", 7],      # nascimento diferente
    ["6", "EVA EXEMPLO", "01/06/2024", "01/01/1960", 1],      # falha ao baixar
    ["7", "FIA EXEMPLO", "", "01/01/1960", 1],                # sem data
    ["8", "GIA EXEMPLO", "01/08/2024", "01/01/1960", 1],      # não existe
]


def test_lote_inteiro(tmp_path):
    cfg = L.Config(tolerancia_dias=1, nos=["pacs"], ias=["densidade"], protocolo_rm=True, enviar_nos=["pacs"],
                   enviar_o_que="ambos", imprimir="dest:Papel", exportar_pasta=str(tmp_path / "exp"))
    lote, d = _lote(tmp_path, cfg, DADOS)
    a = lote.rodar()
    sit = {l.pid: lote.resultados[l.chave]["situacao"] for l in lote.linhas}
    assert sit == {"1": L.FEITO, "2": L.FEITO, "3": L.FEITO, "5": L.OUTRA_PESSOA, "6": L.SEM_DOWNLOAD,
                   "7": L.SEM_DATA, "8": L.NAO_ACHADO}
    assert a.feitos == 7
    # o de mais imagens, baixado, usado e apagado; o que já estava no banco não é apagado
    assert "U4" in d.baixados and "U3" not in d.baixados and "U5" not in d.baixados
    assert set(d.apagados) == {"U2", "U4"}
    assert ("U1", "pacs", None) in d.enviados and ("U1", "pacs", ["U1.conf"]) in d.enviados
    assert [x[0] for x in d.impressos] == ["U1", "U2", "U4"]
    # a planilha: original + colunas do Ipê; uma aba por IA e a do protocolo
    abas = P.abas(lote.saida)
    assert abas[:3] == ["Resultados", "IA · Densidade", "IA · Protocolo de RM"] and "Resumo" in abas
    res = P.ler_xlsx(lote.saida, "Resultados")
    assert res[0][:5] == ["Prontuário", "Nome", "Data do exame", "Nascimento", "Agatston"]
    assert "Ipê: situação" in res[0] and len(res) == 8
    ia = P.ler_xlsx(lote.saida, "IA · Densidade")
    assert ia[0][-2:] == ["Categoria", "Área (mm²)"] and len(ia) == 4


def test_todos_os_exames_do_dia(tmp_path):
    cfg = L.Config(nos=["pacs"], varios="todos", apagar_depois=False)
    lote, d = _lote(tmp_path, cfg, [DADOS[2]])
    lote.rodar()
    r = lote.resultados[lote.linhas[0].chave]
    assert [e["study_uid"] for e in r["exames"]] == ["U3", "U4"] and d.apagados == []
    assert len(P.ler_xlsx(lote.saida, "Resultados")) == 3


def test_simular_nao_baixa_nem_grava(tmp_path):
    cfg = L.Config(tolerancia_dias=1, nos=["pacs"], ias=["densidade"])
    lote, d = _lote(tmp_path, cfg, DADOS, simular=True)
    lote.rodar()
    assert d.baixados == [] and not lote.saida.exists() and not lote.arquivo_andamento.exists()
    assert lote.contagem()[L.ACHADO] == 4


def test_anonimizado_tira_os_dados_do_paciente(tmp_path):
    cfg = L.Config(tolerancia_dias=1, nos=["pacs"], ias=["densidade"], anonimizar=True,
                   exportar_pasta=str(tmp_path / "exp"))
    lote, d = _lote(tmp_path, cfg, DADOS[:3])
    lote.rodar()
    texto = ""
    with zipfile.ZipFile(lote.saida) as z:
        for n in z.namelist():
            texto += z.read(n).decode("utf-8")
    for proibido in ("ANA EXEMPLO", "BIA EXEMPLO", "U1", "U2", "U4", "1960"):
        assert proibido not in texto
    assert "Caso 0001" in texto and d.exportados[0].startswith("Caso 0001_")
    chave = P.ler_xlsx(lote.arquivo_chave)
    assert chave[1][:3] == ["Caso 0001", 2, "1"] and chave[1][3] == "ANA EXEMPLO"


def test_retomar_e_parar(tmp_path):
    cfg = L.Config(tolerancia_dias=1, nos=["pacs"])
    lote, d = _lote(tmp_path, cfg, DADOS)
    lote.limite = 2
    lote.rodar()
    assert len(lote.resultados) == 2
    lote2 = L.Lote(lote.cabecalho, lote.dados, lote.linhas, cfg, d.servicos(), lote.saida)
    assert len(lote2.resultados) == 2 and len(lote2.por_fazer()) == 5
    parar = threading.Event()
    parar.set()
    lote2.rodar(parar)
    assert len(lote2.resultados) == 2


def test_fora_da_janela_espera(tmp_path):
    cfg = L.Config(nos=["pacs"], janela_de="20:00", janela_ate="06:00")
    lote, d = _lote(tmp_path, cfg, DADOS[:1])
    parar = threading.Event()
    avisos = []

    def avisar(a, l, r):
        avisos.append(a.esperando)
        parar.set()
    lote.rodar(parar, avisar, agora=lambda: datetime(2026, 1, 1, 12, 0))
    assert avisos and "janela" in avisos[0] and lote.resultados == {}


def test_modelos(tmp_path):
    from ipe.core.config import Settings
    st = Settings(tmp_path / "s.json")
    assert "Densidade e calcificações da mama" in L.modelos(st)
    cfg = L.Config(ias=["enfisema"], modalidades=["CT"], colunas=["id"], aba="X")
    L.salvar_modelo(st, "Enfisema", cfg)
    m = L.modelos(Settings(tmp_path / "s.json"))["Enfisema"]
    assert m.ias == ["enfisema"] and m.colunas == [] and m.aba == ""
    L.apagar_modelo(st, "Enfisema")
    assert "Enfisema" not in L.modelos(st)


# ---------------------------------------------------------------------- as IAs da fila (dublê da fila e do banco)
def test_executor_espera_a_fila_e_pega_os_numeros():
    import threading as th
    from types import SimpleNamespace as NS

    from ipe.ai import tarefas as TA
    from ipe.automation import lote_ias as LIA

    class Repo:
        def __init__(self):
            self.series = [NS(series_uid="S1", modality="CT", description="TORAX")]
            self.lista = []

        def series_for_study(self, uid):
            return list(self.series)

        def achados(self, uid, ferramenta=None):
            return [a for a in self.lista if a["ferramenta"] == ferramenta]

    repo = Repo()

    class Engine:
        _seg_simular = True
        _seg_fila = []

        def _ferramenta(self, tipo):
            if tipo == "enfisema":
                return ("Enfisema", lambda r, u, s: ("S1", ""), lambda r, u: False)
            return ("Cálcio coronariano", lambda r, u, s: (None, "sem TC sem contraste"), lambda r, u: False)

        def pedir(self, uid, tipo, serie=None, quem=""):
            t = TA.REGISTRO.nova("Enfisema", uid, "", "manual")

            def roda():
                repo.series.append(NS(series_uid="S2", modality="SC", description="Enfisema (< -950 HU) · Ipê"))
                repo.series.append(NS(series_uid="S3", modality="SEG", description="Enfisema · Ipê"))
                repo.lista.append({"ferramenta": "enfisema", "estado": "sugerido", "rotulo": "Enfisema",
                                   "local": "pulmões", "numeros": {"pct": {"v": 12.345, "u": "%", "n": "LAA-950"}},
                                   "corrigidos": {}})
                TA.REGISTRO.mudar(t.id, TA.PRONTO, mensagem="LAA 12 %")
            th.Timer(0.3, roda).start()
            return t.id

    ex = LIA.Executor(repo, None, "/tmp", None, Engine())
    r = ex.rodar("U1", ["enfisema", "calcio"])
    assert r["enfisema"]["situacao"] == LIA.FEITA and r["enfisema"]["series"] == ["S2"]
    assert r["enfisema"]["campos"] == {"Achado": "Enfisema", "Local": "pulmões", "LAA-950 (%)": 12.345}
    assert r["calcio"]["situacao"] == LIA.NAO_SERVE and "contraste" in r["calcio"]["motivo"]


def test_nao_encontrado_diz_por_que(tmp_path):
    cfg = L.Config(nos=["pacs"])
    lote, d = _lote(tmp_path, cfg, [["9", "X", "10/03/2024", "", 0], ["3", "Y", "05/04/2024", "", 0]])
    lote.rodar()
    r = [lote.resultados[l.chave] for l in lote.linhas]
    assert all(x["situacao"] == L.NAO_ACHADO for x in r)
    # o dublê devolve tudo o que tem: o filtro tira; a observação mostra o que voltou
    assert "PACS devolveu" in r[0]["observacao"]


def test_nao_encontrado_busca_so_pelo_id(tmp_path):
    cfg = L.Config(nos=["pacs"])
    cab = ["ID", "Data"]
    dados = [["3", "05/04/2024"], ["77", "05/04/2024"]]
    cfg.colunas = ["id", "data"]
    linhas = L.montar_linhas(dados, cfg.colunas)
    d = Dubles()

    def no(n, crit):
        if crit.get("data_de"):
            return []
        return [e for e in d.pacs.values()]
    serv = d.servicos()
    serv.no = no
    lote = L.Lote(cab, dados, linhas, cfg, serv, tmp_path / "s.xlsx")
    lote.rodar()
    obs = [lote.resultados[l.chave]["observacao"] for l in lote.linhas]
    assert "O ID tem 2 exame(s) em PACS" in obs[0] and "01/04/2024 MG" in obs[0]
    assert "PACS não tem nenhum exame com o ID 77" in obs[1]

    def quebra(n, crit):
        raise ConnectionError("associação recusada")
    serv.no = quebra
    lote2 = L.Lote(cab, dados, linhas, cfg, serv, tmp_path / "s2.xlsx")
    lote2.rodar()
    assert "erro ao buscar em PACS: associação recusada" in lote2.resultados[linhas[0].chave]["observacao"]


def test_tentativas_na_ordem_do_usuario(tmp_path):
    """0.100.99: ele escolhe o que buscar e em que ordem; para na primeira que acha."""
    l = L.Linha(0, pid="3", acesso="ACX", data="20240401", modalidade="MR")
    cfg = L.Config(tentativas=["acesso", "id_data_mod", "id"])
    assert [k for k, _c in l.criterios(cfg)] == ["acesso", "id_data_mod", "id"]
    assert l.criterios(cfg)[1][1]["modalidades"] == ["MR"] and "data_de" not in l.criterios(cfg)[2][1]
    # sem data: só as tentativas que não precisam dela
    sem = L.Linha(0, pid="3")
    assert [k for k, _c in sem.criterios(L.Config(tentativas=["id_data", "id"]))] == ["id"]
    assert sem.criterios(L.Config()) == []
    # o acesso não está no PACS; ID + data + MR não acha (os exames são MG); ID + data acha
    cab, dados = ["ID", "Acesso", "Data", "Modalidade"], [["3", "NAO", "01/04/2024", "MR"]]
    cfg = L.Config(tentativas=["acesso", "id_data_mod", "id_data"], nos=["pacs"], apagar_depois=False)
    cfg.colunas = ["id", "acesso", "data", "modalidade"]
    d = Dubles()
    lote = L.Lote(cab, dados, L.montar_linhas(dados, cfg.colunas), cfg, d.servicos(), tmp_path / "s.xlsx")
    lote.rodar()
    r = lote.resultados[lote.linhas[0].chave]
    assert r["situacao"] == L.FEITO and r["achado_por"] == "id_data" and r["exames"][0]["study_uid"] == "U4"
    t = P.ler_xlsx(lote.saida, "Resultados")
    assert dict(zip(t[0], t[1]))["Ipê: achado por"] == "ID + data"
    # só com o acesso marcado: não acha, e diz por onde procurou
    cfg.tentativas = ["acesso"]
    lote = L.Lote(cab, dados, L.montar_linhas(dados, cfg.colunas), cfg, d.servicos(), tmp_path / "s2.xlsx")
    lote.rodar()
    r = lote.resultados[lote.linhas[0].chave]
    assert r["situacao"] == L.NAO_ACHADO and "por: Nº de acesso" in r["observacao"]


def test_exame_que_ja_estava_passa_pelas_regras_da_chegada(tmp_path):
    """0.100.101: o que já estava no banco passa pelas regras da chegada, como um exame baixado; o baixado não
    (ele passa ao terminar o download)."""
    cfg = L.Config(tolerancia_dias=1, nos=["pacs"])
    lote, d = _lote(tmp_path, cfg, DADOS[:2])
    chegadas = []
    lote.s.chegada = chegadas.append
    lote.rodar()
    assert chegadas == ["U1"]
    cfg2 = L.Config(tolerancia_dias=1, nos=["pacs"], regras_chegada=False)
    (tmp_path / "b").mkdir()
    lote2, _d = _lote(tmp_path / "b", cfg2, DADOS[:1])
    chegadas.clear()
    lote2.s.chegada = chegadas.append
    lote2.rodar()
    assert chegadas == []


def test_baixado_avisa_antes_das_ias(tmp_path):
    """0.100.111: `baixado(uid)` é chamado assim que o exame chega do PACS, antes das IAs (o cliente começa a
    trazer o exame para o banco dele sem esperar a linha terminar)."""
    cfg = L.Config(tolerancia_dias=1, nos=["pacs"], ias=["densidade"])
    lote, d = _lote(tmp_path, cfg, [DADOS[1]])
    ordem = []
    ias = lote.s.ias
    lote.s.baixado = lambda uid: ordem.append(("baixado", uid))
    lote.s.ias = lambda uid, *a: ordem.append(("ias", uid)) or ias(uid, *a)
    lote.rodar()
    assert ordem == [("baixado", "U2"), ("ias", "U2")]


def test_servidor_so_apaga_depois_da_copia_do_fim_da_linha():
    """0.100.111: a cópia de logo depois do download não autoriza apagar; a do fim da linha, com as imagens todas,
    sim; com menos imagens que o servidor, o servidor pede a cópia de novo."""
    from types import SimpleNamespace

    from ipe.central import lote_servidor as LS
    apagados = []
    contagem = {"U1": 12}
    c = SimpleNamespace(repo=SimpleNamespace(instance_counts=lambda uids: {u: contagem.get(u, 0) for u in uids},
                                             delete_study=lambda uid, st: apagados.append(uid)), storage=None)
    s = SimpleNamespace(username="eu")
    e = LS.Execucao("X1", "eu", "x", None)
    LS._LOTES["X1"] = e
    try:
        e.para_copiar.append("U1")                                      # chegou ao servidor
        assert LS.copiado(c, s, "X1", "U1", 10) == {"ok": True, "de_novo": True}   # faltam 2: de novo
        assert "U1" not in e.copiados and "U1" in e.para_copiar
        LS.copiado(c, s, "X1", "U1", 12)                                # a cópia antecipada, inteira
        assert "U1" in e.copiados and not apagados
        e.copiados.discard("U1")                                        # o fim da linha (so_depois_da_copia)
        e.apagar_quando_copiar.add("U1")
        LS.copiado(c, s, "X1", "U1", 12)
        assert apagados == ["U1"]
    finally:
        LS._LOTES.pop("X1", None)


def test_so_baixar_nao_roda_as_regras_da_chegada():
    """0.100.115: o modelo pronto "Só baixar" e o download sem as regras da chegada (nenhuma IA roda)."""
    from types import SimpleNamespace

    from ipe.automation.engine import AutomationEngine
    from ipe.network.service import Job
    so = L.MODELOS_PRONTOS["Só baixar"]
    assert so.ias == [] and not so.apagar_depois and not so.regras_chegada and not so.regras_no_baixado
    assert "sem as regras da chegada no que foi baixado" in so.acoes()
    serv = L.Servicos(local=None, no=None, tem=None, baixar=None, ias=None, protocolo=None, enviar=None,
                      imprimir=None, exportar=None, apagar=None, nome_no=None)
    L.Lote(["ID"], [], [], so, serv, "/tmp/x.xlsx")
    assert serv.sem_regras_no_baixado
    L.Lote(["ID"], [], [], L.Config(), serv, "/tmp/x.xlsx")
    assert not serv.sem_regras_no_baixado
    # o motor não roda nada num download marcado
    chamou = []
    eu = SimpleNamespace(_job_tags={}, study_arrived=lambda *a, **k: chamou.append(a), repo=None, settings=None)
    job = Job("retrieve", "Lote", {}, None, ["1.2.3"])
    job.status, job.sem_regras = "done", True
    AutomationEngine.on_job_finished(eu, job)
    assert not chamou
