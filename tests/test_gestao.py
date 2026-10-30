"""Gestão de exames: conferir o que as modalidades fizeram contra o PACS, e mandar o que falta.

Rede de verdade em loopback: três instâncias do programa fazem a **modalidade** (que só conversa
com quem ela conhece — o AE do OsiriX dele), o **PACS** e **este computador**. Nada de rede trocada
por mentira: o C-MOVE da modalidade para o PACS é uma associação real entre os dois.
"""
import socket
from pathlib import Path

import numpy as np
import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, MRImageStorage, generate_uid

from ipe.db.repository import Repository
from ipe.db.session import Database
from ipe.importer.scanner import Importer
from ipe.network import gestao as G
from ipe.network.client import DicomClient, DicomError, Target
from ipe.network.server import DicomServer
from ipe.network.sink import IncomingSink

HOJE = "20261009"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class No:
    def __init__(self, base: Path, ae: str, accept: str = "any"):
        self.storage = base / "Storage"
        self.storage.mkdir(parents=True)
        self.db = Database(base / "db.sqlite")
        self.repo = Repository(self.db)
        self.sink = IncomingSink(self.db, self.repo, self.storage)
        self.port = free_port()
        self.ae = ae
        self.server = DicomServer(self.repo, self.sink, {"ae_title": ae, "port": self.port,
                                                         "accept": accept, "timeout": 10})

    def como_no(self, **kw) -> dict:
        d = {"id": abs(hash(self.ae)) % 10000, "name": self.ae, "ae_title": self.ae,
             "host": "127.0.0.1", "port": self.port, "retrieve": "get", "move_destination": "",
             "kind": "dimse"}
        d.update(kw)
        return d

    def conhece(self, outro: "No", ae: str | None = None) -> None:
        d = outro.como_no()
        d.pop("id")
        if ae:
            d["ae_title"] = d["name"] = ae
        self.repo.save_node(d)
        self.server.refresh_acl()

    def importar(self, pasta: Path) -> None:
        Importer(self.db, self.storage).import_paths([pasta])

    def n_imagens(self, study_uid: str) -> int:
        return len(self.repo.files_for_study(study_uid))

    def close(self):
        self.server.stop()
        self.sink.stop()


def _imagem(pasta: Path, st: dict, se_uid: str, se_num: int, desc: str, i: int) -> str:
    ds = Dataset()
    ds.SOPClassUID = MRImageStorage
    ds.SOPInstanceUID = generate_uid()
    ds.StudyInstanceUID, ds.SeriesInstanceUID = st["uid"], se_uid
    ds.PatientName, ds.PatientID = st["nome"], st["pid"]
    ds.StudyDate, ds.StudyTime, ds.AccessionNumber = HOJE, "080000", st["acc"]
    ds.StudyDescription, ds.Modality = st["desc"], "MR"
    ds.SeriesNumber, ds.SeriesDescription, ds.InstanceNumber = se_num, desc, i + 1
    ds.Rows = ds.Columns = 8
    ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
    ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 12, 11, 0
    ds.PixelSpacing, ds.SliceThickness = [1, 1], 1
    ds.ImagePositionPatient, ds.ImageOrientationPatient = [0, 0, i], [1, 0, 0, 0, 1, 0]
    ds.PixelData = (np.full((8, 8), i, np.uint16)).tobytes()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = ds.SOPClassUID
    ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    p = pasta / f"{ds.SOPInstanceUID}.dcm"
    ds.save_as(p, enforce_file_format=True)
    return ds.SOPInstanceUID


def _exame(base: Path, nome: str, acc: str, series: list[tuple[str, int]]) -> dict:
    """Um exame em disco: {'uid', 'series': [(uid, desc, [sops], pasta)]}."""
    st = {"uid": generate_uid(), "nome": nome, "pid": acc + "P", "acc": acc, "desc": "RM CRANIO"}
    out = {"uid": st["uid"], "acc": acc, "series": []}
    for n, (desc, k) in enumerate(series, 1):
        se = generate_uid()
        pasta = base / acc / f"s{n}"
        pasta.mkdir(parents=True)
        sops = [_imagem(pasta, st, se, n, desc, i) for i in range(k)]
        out["series"].append((se, desc, sops, pasta))
    return out


@pytest.fixture()
def clinica(tmp_path):
    """MR01 (modalidade), PACS e este computador (DICOMVIEWER).

    - exame A: está inteiro no PACS;
    - exame B: no PACS falta a série 3 inteira e uma imagem da série 2;
    - exame C: não chegou ao PACS;
    - a modalidade só aceita quem ela conhece: o OsiriX (AE OSIRIX) e o PACS.
    """
    mod = No(tmp_path / "mod", "MR01", accept="known")
    pacs = No(tmp_path / "pacs", "PACS")
    eu = No(tmp_path / "eu", "DICOMVIEWER")
    a = _exame(tmp_path / "dados", "PACIENTE^A", "A1", [("T1", 3), ("T2", 2)])
    b = _exame(tmp_path / "dados", "PACIENTE^B", "B1", [("T1", 3), ("FLAIR", 4), ("DWI", 2)])
    c = _exame(tmp_path / "dados", "PACIENTE^C", "C1", [("T1", 2), ("PATIENT PROTOCOL", 1)])
    for ex in (a, b, c):
        mod.importar(tmp_path / "dados" / ex["acc"])
    pacs.importar(tmp_path / "dados" / "A1")
    pacs.importar(b["series"][0][3])
    falta_uma = b["series"][1][3]
    for f in sorted(falta_uma.iterdir())[1:]:
        pacs.importar(f)
    mod.conhece(pacs)                          # destino do C-MOVE direto
    mod.conhece(eu, ae="OSIRIX")               # o único AE que a modalidade aceita (identidade)
    for n in (mod, pacs, eu):
        assert n.server.start()
    yield {"mod": mod, "pacs": pacs, "eu": eu, "a": a, "b": b, "c": c}
    for n in (mod, pacs, eu):
        n.close()


OSIRIX = {"id": 7, "name": "OsiriX da sala", "ae_title": "OSIRIX", "move_destination": "",
          "allowed_nodes": ""}


def _alvo(eu: No):
    return lambda no, ident: Target.build(no, eu.ae, ident)


def _conferir(c, **kw):
    cli = DicomClient(timeout=10)
    conf = G.Conferidor(cli, _alvo(c["eu"]))
    fonte = G.Fonte(c["mod"].como_no(), kw.pop("identidade", OSIRIX))
    pacs = G.Fonte(c["pacs"].como_no())
    res, erros = conf.conferir([fonte], pacs, HOJE, HOJE, **kw)
    return {r.estudo["accession"]: r for r in res}, erros, fonte, pacs


# ---------------------------------------------------------------------- comparação pura
def test_comparar_series_regras():
    o = [{"series_uid": "1", "series_number": 1, "description": "T1", "num_images": 10},
         {"series_uid": "2", "series_number": 2, "description": "T2", "num_images": 10},
         {"series_uid": "3", "series_number": 3, "description": "DWI", "num_images": 5},
         {"series_uid": "4", "series_number": 4, "description": "Patient Protocol", "num_images": 1},
         {"series_uid": "5", "series_number": 5, "description": "SWI", "num_images": 0}]
    p = [{"series_uid": "1", "num_images": 12},             # a mais no PACS não é defeito
         {"series_uid": "2", "num_images": 9},
         {"series_uid": "5", "num_images": 0},
         {"series_uid": "9", "series_number": 9, "description": "KEY", "num_images": 1}]
    r = {s.uid: s for s in G.comparar_series(o, p, ignorar=["protocol"])}
    assert r["1"].situacao == "ok"
    assert r["2"].situacao == "incompleta" and r["2"].faltam == 1
    assert r["3"].situacao == "falta" and r["3"].faltam == 5
    assert r["4"].situacao == "ignorada"
    assert r["5"].situacao == "sem_contagem", "contagem 0 é 'não informou', não 'vazia'"
    assert r["9"].situacao == "so_no_pacs"
    sit, det = G.situacao_do_exame({}, {"study_uid": "x"}, list(r.values()))
    assert sit == "incompleto" and "1 série(s) faltando" in det and "1 imagem(ns) a menos" in det


def test_comparar_pelo_conjunto_diz_quais_faltam():
    o = [{"series_uid": "1", "num_images": 3, "sops": {"a", "b", "c"}}]
    p = [{"series_uid": "1", "num_images": 3, "sops": {"a", "b", "x"}}]
    s = G.comparar_series(o, p)[0]
    assert s.situacao == "incompleta" and s.faltando == ["c"], \
        "mesma contagem e imagem diferente: só o conjunto acha"


def test_situacao_sem_series_usa_o_total_do_exame():
    sit, det = G.situacao_do_exame({"num_images": 10, "num_series": 2},
                                   {"num_images": 10, "num_series": 2}, [])
    assert sit == "completo" and "total do exame" in det
    sit, _ = G.situacao_do_exame({"num_images": 0}, {"num_images": 10}, [])
    assert sit == "sem_contagem"
    assert G.situacao_do_exame({}, None, [])[0] == "ausente"


def test_periodo():
    from datetime import date
    d = date(2026, 10, 9)
    assert G.periodo("hoje", d) == ("20261009", "20261009")
    assert G.periodo("ontem", d) == ("20261008", "20261008")
    assert G.periodo("2dias", d) == ("20261008", "20261009")
    assert G.periodo("7dias", d) == ("20261003", "20261009")


# ---------------------------------------------------------------------- conferir na rede
def test_conferencia_acha_completo_incompleto_e_ausente(clinica):
    r, erros, *_ = _conferir(clinica, ignorar=["patient protocol"])
    assert not erros
    assert set(r) == {"A1", "B1", "C1"}
    assert r["A1"].situacao == "completo"
    b = r["B1"]
    assert b.situacao == "incompleto"
    por = {s.descricao: s for s in b.series}
    assert por["T1"].situacao == "ok"
    assert por["FLAIR"].situacao == "incompleta" and por["FLAIR"].faltam == 1
    assert por["DWI"].situacao == "falta" and por["DWI"].faltam == 2
    assert b.contagem() == ("3 / 2", "9 / 6")
    assert r["C1"].situacao == "ausente"
    assert {s.descricao: s.situacao for s in r["C1"].series}["PATIENT PROTOCOL"] == "ignorada"


def test_sem_a_identidade_a_modalidade_recusa_e_o_erro_diz_quem(clinica):
    """Ele se passa pelo OsiriX porque a modalidade só conversa com quem conhece."""
    r, erros, *_ = _conferir(clinica, identidade=None)
    assert not r
    assert erros and "MR01" in erros[0] and "DICOMVIEWER" in erros[0]


def test_exato_diz_quais_imagens_faltam(clinica):
    r, _e, *_ = _conferir(clinica, exato=True)
    flair = next(s for s in r["B1"].series if s.descricao == "FLAIR")
    falta = sorted(clinica["b"]["series"][1][3].iterdir())[0].stem   # a que não foi para o PACS
    assert flair.faltando == [falta]


def test_pacs_com_o_mesmo_accession_e_outro_uid(clinica, tmp_path):
    """Exame refeito ou corrigido no PACS: não é 'ausente', e mandar criaria duplicata."""
    outro = _exame(tmp_path / "outro", "PACIENTE^C", "C1", [("T1", 2)])
    clinica["pacs"].importar(tmp_path / "outro" / "C1")
    r, *_ = _conferir(clinica)
    assert r["C1"].situacao == "outro_uid" and outro["uid"] in r["C1"].detalhe


# ---------------------------------------------------------------------- mandar
def test_sem_o_pacs_a_serie_incompleta_vai_inteira(clinica):
    """Sem como perguntar ao PACS quais faltam, manda a série inteira (o PACS desduplica)."""
    r, _e, fonte, _p = _conferir(clinica)
    out = G.Remetente(DicomClient(timeout=10), _alvo(clinica["eu"])).direto(fonte, r["B1"], "PACS")
    assert out["imagens"] == 6


def test_envio_direto_manda_so_o_que_falta_e_a_reconferencia_fecha(clinica):
    r, _e, fonte, pacs = _conferir(clinica)
    cli = DicomClient(timeout=10)
    rem = G.Remetente(cli, _alvo(clinica["eu"]))
    pedidos = rem.pedidos(r["B1"])
    assert len(pedidos) == 2, "FLAIR (uma imagem) e DWI (série inteira); T1 está completa"
    out = rem.direto(fonte, r["B1"], "PACS", pacs=pacs)
    assert out["modo"] == "direto" and out["imagens"] == 3 and not out["falhas"], out
    assert not clinica["eu"].repo.files_for_study(clinica["b"]["uid"]), \
        "envio direto não passa por este computador"
    clinica["pacs"].sink.flush(30)
    assert clinica["pacs"].n_imagens(clinica["b"]["uid"]) == 9
    novo = G.Conferidor(cli, _alvo(clinica["eu"])).reconferir(fonte, pacs, clinica["b"]["uid"])
    assert novo.situacao == "completo"


def test_exame_ausente_vai_sem_a_serie_ignorada(clinica):
    r, _e, fonte, _p = _conferir(clinica, ignorar=["patient protocol"])
    rem = G.Remetente(DicomClient(timeout=10), _alvo(clinica["eu"]))
    out = rem.direto(fonte, r["C1"], "PACS")
    assert out["imagens"] == 2, "a série ignorada não vai"
    out = rem.direto(fonte, r["C1"], "PACS", inteiro=True)
    assert out["imagens"] == 3, "'exame inteiro' manda tudo"


def test_destino_desconhecido_e_o_caminho_pelo_computador(clinica):
    """A modalidade não conhece o PACS2: direto é 0xA801; no automático vai pelo computador."""
    r, _e, fonte, pacs = _conferir(clinica)
    eu = clinica["eu"]
    cli = DicomClient(timeout=10)
    rem = G.Remetente(cli, _alvo(eu), sink=eu.sink, repo=eu.repo)
    with pytest.raises(G.DestinoDesconhecido, match="PACS2"):
        rem.direto(fonte, r["B1"], "PACS2")
    with pytest.raises(G.DestinoDesconhecido):
        rem.enviar("direto", fonte, pacs, r["B1"], "PACS2")
    out = rem.enviar("auto", fonte, pacs, r["B1"], "PACS2")
    assert out["modo"] == "computador" and out["imagens"] == 3, out
    assert "recusado" in out["mensagem"]
    clinica["pacs"].sink.flush(30)
    assert clinica["pacs"].n_imagens(clinica["b"]["uid"]) == 9
    assert G.Conferidor(cli, _alvo(eu)).reconferir(fonte, pacs, clinica["b"]["uid"]).situacao \
        == "completo"


def test_pelo_computador_entrega_ao_pacs_como_a_identidade(clinica):
    """PACS que só aceita a modalidade: o reenvio vai com o AE dela."""
    r, _e, fonte, _ = _conferir(clinica)
    p = clinica["pacs"]
    p.server.config["accept"] = "known"
    p.repo.save_node({"name": "MR01", "ae_title": "MR01", "host": "127.0.0.1", "port": 1})
    p.server.refresh_acl()
    eu = clinica["eu"]
    rem = G.Remetente(DicomClient(timeout=10), _alvo(eu), sink=eu.sink, repo=eu.repo)
    pacs_sem = G.Fonte(p.como_no())
    with pytest.raises(DicomError):
        rem.pelo_computador(fonte, pacs_sem, r["C1"])
    pacs_como_mr = G.Fonte(p.como_no(), {"id": 8, "name": "como a RM", "ae_title": "MR01",
                                         "move_destination": "", "allowed_nodes": ""})
    out = rem.pelo_computador(fonte, pacs_como_mr, r["C1"])
    assert out["imagens"] == 3 and "como MR01" in out["mensagem"]


def test_teste_de_destino(clinica):
    cli = DicomClient(timeout=10)
    rem = G.Remetente(cli, _alvo(clinica["eu"]))
    fonte = G.Fonte(clinica["mod"].como_no(), OSIRIX)
    ok, msg = rem.testar_destino(fonte, "PACS2")
    assert ok is False and "NÃO conhece" in msg
    ok, msg = rem.testar_destino(fonte, "PACS")
    assert ok is None and "não prova" in msg
    assert clinica["pacs"].n_imagens(clinica["c"]["uid"]) == 0, "o teste não manda nada"


def test_diagnostico(clinica):
    d = G.Conferidor(DicomClient(timeout=10), _alvo(clinica["eu"])).diagnosticar(
        G.Fonte(clinica["mod"].como_no(), OSIRIX), "PACS2", HOJE)
    textos = " | ".join(t for _ok, t in d)
    assert "C-ECHO como OSIRIX" in textos and "3 exame(s)" in textos
    assert "nível imagem" in textos and "NÃO conhece" in textos


# ---------------------------------------------------------------------- a janela
def _esperar(app, w, limite=60.0):
    import time
    t0 = time.time()
    while w.ocupado and time.time() - t0 < limite:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()
    assert not w.ocupado, "a janela não terminou o trabalho"


@pytest.fixture()
def janela(env, clinica, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    from ipe.network.service import NetworkService
    from ipe.ui.gestao_dialog import GestaoWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    for n in (clinica["mod"], clinica["pacs"]):
        d = n.como_no()
        d.pop("id")
        repo.save_node(d)
    repo.save_node({"name": "Orthanc", "kind": "dicomweb", "base_url": "http://x/dicom-web"})
    repo.save_identity(dict(OSIRIX, id=None))
    st = Settings(paths.settings_file)
    net = NetworkService(db, repo, paths.storage, st)
    w = GestaoWindow(net, st)
    yield app, w, st, repo, clinica
    w.close()
    net.shutdown()


def _linha_do_no(w, nome):
    return next(r for r in range(w.t_fontes.rowCount()) if w.t_fontes.item(r, 1).text() == nome)


def _preparar(w, repo):
    from PySide6.QtCore import Qt
    r = _linha_do_no(w, "MR01")
    w.t_fontes.item(r, 0).setCheckState(Qt.Checked)
    cb = w.t_fontes.cellWidget(r, 3)
    cb.setCurrentIndex(cb.findData(repo.identities()[0]["id"]))
    w.c_pacs.setCurrentIndex(w.c_pacs.findData(next(n["id"] for n in repo.nodes() if n["name"] == "PACS")))


def test_janela_lista_so_dimse_e_avisa_do_dicomweb(janela):
    app, w, st, repo, c = janela
    nomes = [w.t_fontes.item(r, 1).text() for r in range(w.t_fontes.rowCount())]
    assert nomes == ["MR01", "PACS"]
    assert "Orthanc" in w.l_web.text() and "DIMSE" in w.l_web.text()
    assert w.c_pacs.currentText().startswith("PACS"), "o nó chamado PACS vem escolhido"
    assert w.e_destino.placeholderText() == "PACS"


def test_janela_confere_envia_e_lembra(janela, tmp_path, monkeypatch):
    from PySide6.QtCore import QDate
    app, w, st, repo, c = janela
    _preparar(w, repo)
    w.c_periodo.setCurrentIndex(w.c_periodo.findData("datas"))
    w.d_de.setDate(QDate(2026, 10, 9))
    w.d_ate.setDate(QDate(2026, 10, 9))
    w.e_ignorar.setText("patient protocol")
    w.conferir()
    _esperar(app, w)
    sit = {x.estudo["accession"]: x.situacao for x in w.resultados}
    assert sit == {"A1": "completo", "B1": "incompleto", "C1": "ausente"}
    assert "3 exame(s)" in w.l_resumo.text() and "1 completo(s)" in w.l_resumo.text()
    assert w.arvore.topLevelItem(0).text(0).startswith("✖"), "o pior primeiro"
    # só os com problema
    w.c_mostrar.setCurrentIndex(1)
    visiveis = [w.arvore.topLevelItem(i) for i in range(w.arvore.topLevelItemCount())
                if not w.arvore.topLevelItem(i).isHidden()]
    assert len(visiveis) == 2
    # lembra para amanhã
    cfg = st.get("gestao")
    assert cfg["periodo"] == "datas" and cfg["ignorar"] == "patient protocol"
    assert any(v["on"] and v["ident"] for v in cfg["fontes"].values())
    # menu do botão direito
    w.arvore.clearSelection()
    for i in range(w.arvore.topLevelItemCount()):
        it = w.arvore.topLevelItem(i)
        if it.text(5) in ("B1", "C1"):
            it.setSelected(True)
    textos = [a.text() for a in w.menu_da_arvore().actions() if a.text()]
    assert "Enviar o que falta ao PACS" in textos and "Copiar accession" in textos
    # enviar o que falta (direto da modalidade para o PACS) e conferir de novo
    monkeypatch.setattr(w, "_reconferir_um", lambda *a, **k: type(w)._reconferir_um(*a, espera=0.3))
    w.enviar(inteiro=False, confirmar=False)
    _esperar(app, w)
    sit = {x.estudo["accession"]: x for x in w.resultados}
    assert sit["B1"].situacao == "completo" and "direto de MR01" in sit["B1"].envio
    assert sit["C1"].situacao == "completo"
    assert any("envio ao PACS" in d for _a, _u, _ac, d in repo.audit_entries())
    # 0.99.6: a fila de envio mostra os dois, com o destino e o resultado
    assert not w.g_fila.isHidden() and w.estados_da_fila() == ["ok", "ok"]
    linhas = [[w.t_fila.topLevelItem(i).text(k) for k in range(7)] for i in range(w.t_fila.topLevelItemCount())]
    assert {l[2] for l in linhas} == {"B1", "C1"} and all(l[3] == "PACS" for l in linhas)
    assert "2 exame(s) na fila: 2 enviado(s), 0 esperando" in w.l_fila.text()
    w.limpar_fila()
    assert w.estados_da_fila() == []
    # CSV para o Excel do Windows
    p = w.exportar_csv(str(tmp_path / "conf.csv"))
    bruto = open(p, "rb").read()
    assert bruto.startswith(b"\xef\xbb\xbf") and b"\r\n" in bruto and b";" in bruto


def test_botao_na_tela_do_banco_e_privacidade(env, sample_dir, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    hb = w.home_bar
    assert "gestao" in hb.buttons
    hb.buttons["gestao"].defaultAction().trigger()
    assert w.gestao_window.isVisible() and w.gestao_window.isWindow()
    w.set_privacy(True)
    assert not w.gestao_window.isVisible() and not hb.buttons["gestao"].isEnabled()
    msgs = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: msgs.append(a[2]) or 0))
    w.show_gestao()
    assert msgs and "ocultos" in msgs[-1] and not w.gestao_window.isVisible()
    w.set_privacy(False)
    w.close()


# ---------------------------------------------------------------------- PACS que recusa a busca
@pytest.fixture()
def pacs_que_recusa():
    """Como o DASIMEB dele: aceita a conexão de qualquer AE e devolve 0xC001 em toda busca."""
    from pynetdicom import AE, evt
    from pynetdicom.sop_class import StudyRootQueryRetrieveInformationModelFind, Verification
    ae = AE(ae_title="DASIMEB")
    ae.add_supported_context(StudyRootQueryRetrieveInformationModelFind)
    ae.add_supported_context(Verification)
    porta = free_port()

    def recusa(event):
        yield 0xC001, None
    srv = ae.start_server(("127.0.0.1", porta), block=False, evt_handlers=[(evt.EVT_C_FIND, recusa)])
    yield {"id": 99, "name": "DASIMEB", "ae_title": "DASIMEB", "host": "127.0.0.1", "port": porta,
           "retrieve": "get", "move_destination": "", "kind": "dimse"}
    srv.shutdown()


def test_pacs_que_recusa_para_cedo_e_diz_o_que_fazer(clinica, pacs_que_recusa):
    """Antes: 39 linhas de "Erro" e o motivo escondido numa coluna fora da tela."""
    cli = DicomClient(timeout=10)
    vistos = []
    with pytest.raises(DicomError) as e:
        G.Conferidor(cli, _alvo(clinica["eu"])).conferir(
            [G.Fonte(clinica["mod"].como_no(), OSIRIX)], G.Fonte(pacs_que_recusa), HOJE, HOJE,
            ao_conferir=vistos.append)
    msg = str(e.value)
    assert len(vistos) == G.REPETIDO, "parou nos primeiros, não foi até o fim"
    assert "DASIMEB" in msg and "0xC001" in msg and "DICOMVIEWER" in msg
    assert "permissão de consulta" in msg and "Como" in msg


def test_erro_que_nao_se_repete_nao_para(clinica):
    r = [G.Conferencia("x", 1, {}, situacao="erro", detalhe="a"),
         G.Conferencia("x", 1, {}, situacao="erro", detalhe="b"),
         G.Conferencia("x", 1, {}, situacao="erro", detalhe="a")]
    assert G._erro_repetido(r) == ""
    assert G._erro_repetido(r[:2]) == ""


def test_janela_mostra_o_motivo_do_erro(janela, pacs_que_recusa, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    app, w, st, repo, c = janela
    repo.save_node({k: v for k, v in pacs_que_recusa.items() if k != "id"})
    w.recarregar_nos()
    _preparar(w, repo)
    w.c_pacs.setCurrentIndex(w.c_pacs.findData(next(n["id"] for n in repo.nodes()
                                                     if n["name"] == "DASIMEB")))
    from PySide6.QtCore import QDate
    w.c_periodo.setCurrentIndex(w.c_periodo.findData("datas"))     # os exames do fantoma são de HOJE
    w.d_de.setDate(QDate(2026, 10, 9))
    w.d_ate.setDate(QDate(2026, 10, 9))
    avisos = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: avisos.append(a[2]) or 0))
    w.conferir()
    _esperar(app, w)
    assert avisos and "0xC001" in avisos[-1] and "permissão de consulta" in avisos[-1]
    w.resultados[0].situacao, w.resultados[0].detalhe = "erro", "motivo X"
    assert "1 exame(s): motivo X" in w.texto_dos_erros([])


def test_mensagem_longa_nao_alarga_a_janela(janela):
    """Defeito (0.66.1): o erro de 300 caracteres ia inteiro para a linha de estado, a etiqueta
    pedia a largura do texto e a janela crescia para fora do monitor, levando os botões junto."""
    app, w, st, repo, c = janela
    w.resize(1100, 700)
    w.show()
    app.processEvents()
    largura = w.width()
    longo = "DASIMEB recusou a busca (status 0xC001): " + "aceitou a conexão mas não processou " * 12
    for lab in (w.l_estado, w.l_resumo):
        lab.setText(longo)
    app.processEvents()
    assert w.width() == largura
    for b in (w.b_conferir, w.b_parar, w.b_csv, w.c_mostrar):
        direita = b.mapTo(w, b.rect().topRight()).x()
        assert direita <= w.width(), f"{b.text() if hasattr(b, 'text') else b} saiu da janela"
    assert w.l_estado.minimumSizeHint().width() < 400, "a etiqueta está pedindo a largura do texto"
    assert w.l_estado.toolTip() == longo, "o texto inteiro continua alcançável"


# ---------------------------------------------------------------------- "Baixar para" (0.69.1)
def test_mover_do_no_direto_para_outro_destino(clinica):
    """Pedido dele: "Baixar para" — o exame vai do nó para o destino escolhido, não para cá."""
    rem = G.Remetente(DicomClient(timeout=10), _alvo(clinica["eu"]))
    fonte = G.Fonte(clinica["mod"].como_no(), OSIRIX)
    vistos = []
    r = rem.mover(fonte, "PACS", clinica["c"]["uid"], progresso=lambda f, t, m: vistos.append((f, t)))
    assert r["imagens"] == 3 and not r["falhas"]
    clinica["pacs"].sink.flush(30)
    assert clinica["pacs"].n_imagens(clinica["c"]["uid"]) == 3
    assert clinica["eu"].n_imagens(clinica["c"]["uid"]) == 0, "nada passa por este programa"
    assert vistos, "o andamento aparece na fila"
    so_t2 = [clinica["a"]["series"][1][0]]
    r = rem.mover(fonte, "PACS", clinica["a"]["uid"], so_t2)
    assert r["imagens"] == 2, "só as séries marcadas"
    with pytest.raises(G.DestinoDesconhecido, match="cadastrado em MR01"):
        rem.mover(fonte, "PACS2", clinica["c"]["uid"])


def test_menu_baixar_para_na_tela_do_pacs(env, clinica):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QTreeWidgetItem
    from ipe.core.config import Settings
    from ipe.network.service import NetworkService
    from ipe.ui.pacs_panel import PacsPanel
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    ids = {}
    for n in (clinica["mod"], clinica["pacs"]):
        d = n.como_no()
        d.pop("id")
        ids[n.ae] = repo.save_node(d)
    repo.save_identity(dict(OSIRIX, id=None))
    st = Settings(paths.settings_file)
    net = NetworkService(db, repo, paths.storage, st)
    painel = PacsPanel(net, repo)
    painel.refresh_nodes()
    painel.identity.setCurrentIndex(painel.identity.findData(repo.identities()[0]["id"]))
    r = {"study_uid": clinica["c"]["uid"], "node_id": ids["MR01"], "patient_name": "PACIENTE, C",
         "study_date": HOJE, "modalities": "MR", "description": "RM CRANIO", "num_images": 3}
    it = QTreeWidgetItem(["PACIENTE, C"])
    it.setData(0, Qt.UserRole, r)
    painel.results.addTopLevelItem(it)
    it.setSelected(True)
    menu = painel.menu_dos_resultados()
    sub = next(a.menu() for a in menu.actions() if a.text() == "Baixar para")
    textos = [a.text() for a in sub.actions() if a.text()]
    assert any("PACS" in t for t in textos) and not any("MR01" in t for t in textos), \
        "os destinos são os outros nós, não o de origem"
    acabou = []
    net.job_finished.connect(acabou.append)
    next(a for a in sub.actions() if "PACS" in a.text()).trigger()
    import time
    t0 = time.time()
    while not acabou and time.time() - t0 < 30:
        app.processEvents()
        time.sleep(0.02)
    job = acabou[0]
    assert job.kind == "moveto" and job.status == "done", job.message
    assert job.destino == "PACS" and "3 imagens" in job.message
    clinica["pacs"].sink.flush(30)
    assert clinica["pacs"].n_imagens(clinica["c"]["uid"]) == 3
    assert not repo.study_info(clinica["c"]["uid"]), "não entrou no banco deste programa"
    net.shutdown()


def test_enviar_para_como_outra_modalidade_na_tela_do_pacs(env, clinica, tmp_path):
    """Busca no PACS → Enviar para → nó, como OSIRIX: baixa o exame e envia com o AE do OsiriX."""
    import time
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QTreeWidgetItem
    from ipe.core.config import Settings
    from ipe.network.service import NetworkService
    from ipe.ui.pacs_panel import PacsPanel
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    # destino que só aceita quem ele conhece — e só conhece o OSIRIX
    sala = No(tmp_path / "sala", "SALA", accept="known")
    sala.conhece(clinica["eu"], ae="OSIRIX")
    assert sala.server.start()
    try:
        d = clinica["mod"].como_no()
        d.pop("id")
        id_mod = repo.save_node(d)
        d = sala.como_no(use_in_send=True)
        d.pop("id")
        repo.save_node(d)
        repo.save_identity(dict(OSIRIX, id=None))
        st = Settings(paths.settings_file)
        net = NetworkService(db, repo, paths.storage, st)
        painel = PacsPanel(net, repo)
        painel.refresh_nodes()
        # a MR01 só deixa o OsiriX baixar (o “Como” da busca vale para o download)
        painel.identity.setCurrentIndex(painel.identity.findData(repo.identities()[0]["id"]))
        r = {"study_uid": clinica["c"]["uid"], "node_id": id_mod, "patient_name": "PACIENTE, C",
             "study_date": HOJE, "modalities": "MR", "description": "RM CRANIO", "num_images": 3}
        it = QTreeWidgetItem(["PACIENTE, C"])
        it.setData(0, Qt.UserRole, r)
        painel.results.addTopLevelItem(it)
        it.setSelected(True)
        menu = painel.menu_dos_resultados()
        envio = next(a.menu() for a in menu.actions() if a.text() == "Enviar para")
        no_sala = next(a.menu() for a in envio.actions() if a.text() == "SALA")
        textos = [a.text() for a in no_sala.actions()]
        assert textos == ["como este programa", "como OsiriX da sala (OSIRIX)"]
        acabou = []
        net.job_finished.connect(acabou.append)
        no_sala.actions()[1].trigger()
        t0 = time.time()
        while not any(j.kind == "send" for j in acabou) and time.time() - t0 < 60:
            app.processEvents()
            time.sleep(0.02)
        kinds = [(j.kind, j.status, j.message) for j in acabou]
        assert [k[:2] for k in kinds] == [("retrieve", "done"), ("send", "done")], kinds
        sala.sink.flush(30)
        assert sala.n_imagens(clinica["c"]["uid"]) == 3, "chegou na sala, enviado como OSIRIX"
        # agora já está aqui: o segundo envio sai direto, sem baixar de novo
        jobs = painel.enviar_para(repo.nodes()[-1]["id"], repo.identities()[0]["id"])
        assert [j.kind for j in jobs] == ["send"]
        net.shutdown()
    finally:
        sala.close()


def test_enviar_so_as_series_escolhidas_no_banco_como_outra_modalidade(env, clinica, tmp_path):
    """Banco → séries → Enviar para → nó, como OSIRIX: só as séries escolhidas chegam."""
    import time
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    b = clinica["b"]                              # T1 (3), FLAIR (4), DWI (2)
    Importer(db, paths.storage).import_paths([tmp_path / "dados" / "B1"])
    sala = No(tmp_path / "sala", "SALA", accept="known")
    sala.conhece(clinica["eu"], ae="OSIRIX")
    assert sala.server.start()
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        d = sala.como_no(use_in_send=True)
        d.pop("id")
        repo.save_node(d)
        repo.save_identity(dict(OSIRIX, id=None))
        escolhidas = [b["series"][0][0], b["series"][2][0]]          # T1 e DWI
        menu = w.browser.series_menu(b["uid"], escolhidas)
        envio = next(a.menu() for a in menu.actions() if a.text() == "Enviar 2 série(s) para")
        no_sala = next(a.menu() for a in envio.actions() if a.text() == "SALA")
        assert [a.text() for a in no_sala.actions()] == ["como este programa", "como OsiriX da sala (OSIRIX)"]
        no_sala.actions()[1].trigger()
        t0 = time.time()
        while (not w.net.jobs or w.net.active_jobs()) and time.time() - t0 < 60:
            app.processEvents()
            time.sleep(0.02)
        job = w.net.jobs[-1]
        assert job.kind == "send" and job.status == "done", job.message
        assert job.series_uids == escolhidas and "2 série(s)" in job.label
        sala.sink.flush(30)
        chegaram = {se.series_uid for se in sala.repo.series_for_study(b["uid"])}
        assert chegaram == set(escolhidas), "a FLAIR não foi"
        assert sala.n_imagens(b["uid"]) == 3 + 2
        um = w.browser.series_menu(b["uid"], escolhidas[:1])
        assert any(a.text() == "Enviar esta série para" for a in um.actions())
    finally:
        w.close()
        sala.close()


def test_enviar_para_outro_destino_o_que_falta_e_o_inteiro(janela, tmp_path, monkeypatch):
    """0.99.6: "Enviar o que falta para…" e "Enviar o exame inteiro para…" com os destinos do banco.
    O que falta é contado no destino escolhido; a situação da linha continua a do PACS."""
    app, w, st, repo, c = janela
    backup = No(tmp_path / "backup", "BACKUP")
    assert backup.server.start()
    try:
        d = backup.como_no(use_in_send=True)
        d.pop("id")
        repo.save_node(d)
        c["mod"].conhece(backup)                          # para o C-MOVE direto da modalidade
        bid = next(n["id"] for n in repo.nodes() if n["name"] == "BACKUP")
        backup.importar(c["b"]["series"][0][3])           # o BACKUP já tem a série 1 do B1
        from PySide6.QtCore import QDate
        _preparar(w, repo)
        w.c_periodo.setCurrentIndex(w.c_periodo.findData("datas"))
        w.d_de.setDate(QDate.fromString(HOJE, "yyyyMMdd"))
        w.d_ate.setDate(QDate.fromString(HOJE, "yyyyMMdd"))
        w.conferir()
        _esperar(app, w)
        w.arvore.clearSelection()
        for i in range(w.arvore.topLevelItemCount()):
            it = w.arvore.topLevelItem(i)
            if it.text(5) in ("A1", "B1"):
                it.setSelected(True)
        menu = w.menu_da_arvore()
        subs = {m.title(): m for m in menu.findChildren(type(menu))}
        assert {"Enviar o que falta para", "Enviar o exame inteiro para"} <= set(subs)
        assert "BACKUP" in [a.text() for a in subs["Enviar o que falta para"].actions()]
        assert w.b_falta_para.isEnabled() and w.b_inteiro_para.isEnabled()
        # o que falta no BACKUP: A1 inteiro, B1 sem a série 1
        w.enviar_para(bid, None, inteiro=False, confirmar=False)
        _esperar(app, w)
        backup.sink.flush(30)
        assert backup.n_imagens(c["a"]["uid"]) == 5 and backup.n_imagens(c["b"]["uid"]) == 9
        sit = {x.estudo["accession"]: x for x in w.resultados}
        assert sit["B1"].situacao == "incompleto", "a situação continua a do PACS"
        assert sit["A1"].envio.startswith("→ BACKUP") and sit["B1"].envio.startswith("→ BACKUP")
        # de novo: já está completo lá, nada vai
        w.enviar_para(bid, None, inteiro=False, confirmar=False)
        _esperar(app, w)
        assert "já estava completo em BACKUP" in {x.estudo["accession"]: x for x in w.resultados}["A1"].envio
        est = w.estados_da_fila()
        assert est[:2] == ["ok", "ok"] and est[2:] == ["nada", "nada"], est      # quatro entradas, dois lotes
        assert any("envio a BACKUP" in d for _a, _u, _ac, d in repo.audit_entries())
    finally:
        backup.close()


def test_fila_parada_marca_quem_nao_foi(janela):
    """Parar o envio: o que estava na fila fica "Não foi" (não some, não fica esperando para sempre)."""
    app, w, st, repo, c = janela
    from types import SimpleNamespace as NS
    sel = [NS(study_uid=f"1.2.{i}", estudo={"patient_name": f"P{i}", "accession": f"X{i}"}) for i in range(3)]
    lote = w._fila_entrar(sel, "PACS", "o que falta · auto")
    w.sinais.fila.emit(lote, "1.2.0", "enviando", "")
    app.processEvents()
    assert w.estados_da_fila() == ["enviando", "fila", "fila"] and w.b_fila_parar.isEnabled()
    assert "1 indo agora" in w.l_fila.text() and "2 esperando" in w.l_fila.text()
    w.sinais.fila.emit(lote, "1.2.0", "falhou", "recusado")
    app.processEvents()
    w._fila_fechar(lote)
    assert w.estados_da_fila() == ["falhou", "parado", "parado"]
    assert not w.b_fila_parar.isEnabled() and w.b_fila_limpar.isEnabled()
    assert w.t_fila.topLevelItem(0).text(6) == "recusado"


# ------------------------------------------------------------------ 0.99.6: gestão automática
def _regra_auto(repo, c, **cfg):
    mod = next(n for n in repo.nodes() if n["name"] == "MR01")
    pacs = next(n for n in repo.nodes() if n["name"] == "PACS")
    ident = repo.identities()[0]
    base = {"fontes": [{"node_id": mod["id"], "identity_id": ident["id"]}],
            "destino": {"node_id": pacs["id"], "identity_id": None}, "periodo": "hoje",
            "ignorar": "patient protocol", "envio": "falta", "modo": "auto",
            "repetir": {"minutos": 10, "vezes": 2}}
    base.update(cfg)
    return {"id": None, "kind": "gestao", "name": "RM no PACS", "active": True, "config": base}


def test_gestao_automatica_confere_manda_e_relata(janela):
    from datetime import date

    from ipe.network import gestao_auto as GA
    app, w, st, repo, c = janela
    regra = _regra_auto(repo, c)
    rel = GA.executar(regra, repo, DicomClient(timeout=10), _alvo(c["eu"]), hoje=date(2026, 10, 9), espera=0.3)
    assert rel.conferidos == 3 and rel.completos == 1, rel.resumo()
    assert sorted(d["accession"] for d in rel.enviados) == ["B1", "C1"] and not rel.falhas
    assert rel.situacao == "ok" and not rel.precisa_repetir()
    assert "2 completado(s) agora" in rel.resumo()
    # de novo: tudo completo, nada vai
    rel = GA.executar(regra, repo, DicomClient(timeout=10), _alvo(c["eu"]), hoje=date(2026, 10, 9), espera=0.3)
    assert rel.completos == 3 and not rel.enviados and rel.situacao == "ok"


def test_gestao_automatica_avisa_quem_esta_fora_do_ar(janela):
    from datetime import date, datetime

    from ipe.network import gestao_auto as GA
    app, w, st, repo, c = janela
    morto = {"name": "PACS2", "ae_title": "PACS2", "host": "127.0.0.1", "port": free_port(), "retrieve": "get",
             "move_destination": "", "kind": "dimse"}
    mid = repo.save_node(dict(morto))
    regra = _regra_auto(repo, c, destino={"node_id": mid, "identity_id": None})
    rel = GA.executar(regra, repo, DicomClient(timeout=3), _alvo(c["eu"]), hoje=date(2026, 10, 9), espera=0.1)
    assert rel.destino_offline and rel.situacao == "offline" and "PACS2" in rel.resumo()
    # modalidade fora do ar (o destino responde): aparece em "fora do ar"
    mod_morta = repo.save_node(dict(morto, name="CT09", ae_title="CT09", port=free_port()))
    regra = _regra_auto(repo, c)
    regra["config"]["fontes"].append({"node_id": mod_morta, "identity_id": None})
    rel = GA.executar(regra, repo, DicomClient(timeout=3), _alvo(c["eu"]), hoje=date(2026, 10, 9), espera=0.3)
    assert any(o.startswith("CT09") for o in rel.offline) and rel.situacao == "erro"
    assert "fora do ar: CT09" in rel.resumo() and rel.precisa_repetir()
    # repetir em 10 min, até 2 vezes
    agora = datetime(2026, 10, 9, 10, 0)
    assert GA.proxima_tentativa(regra, agora, 0) == datetime(2026, 10, 9, 10, 10)
    assert GA.proxima_tentativa(regra, agora, 2) is None


def test_motor_roda_a_regra_grava_relatorio_e_marca_a_repeticao(janela, env, monkeypatch):
    import functools
    from datetime import date, datetime

    from ipe.automation.engine import AutomationEngine
    from ipe.network import gestao_auto as GA
    app, w, st, repo, c = janela
    paths, _db, _repo = env
    orig = GA.executar
    monkeypatch.setattr(GA, "executar", functools.partial(orig, hoje=date(2026, 10, 9)))
    w.net.target = _alvo(c["eu"])                       # este programa fala como DICOMVIEWER
    eng = AutomationEngine(repo, w.net.db if hasattr(w.net, "db") else _db, w.net, st, paths)
    avisos = []
    eng.notify.connect(lambda t, m: avisos.append(m))
    regra = _regra_auto(repo, c)
    regra.pop("id")
    rid = repo.save_rule(regra)
    assert eng.rodar_gestao(repo.rule(rid), manual=True, espera=0.3)
    import time as _t
    fim = _t.time() + 60
    while eng.gestao_em_curso(rid) and _t.time() < fim:
        app.processEvents()
        _t.sleep(0.05)
    app.processEvents()
    ult = repo.rule(rid)["config"]["_ultimo"]
    assert ult["situacao"] == "ok" and len(ult["enviados"]) == 2 and not avisos
    assert any(j["kind"] == "gestao" and j["status"] == "ok" for j in repo.job_runs())
    # destino fora do ar: avisa e marca a repetição para daqui a 10 min
    morto = repo.save_node({"name": "PACS2", "ae_title": "PACS2", "host": "127.0.0.1", "port": free_port(),
                            "retrieve": "get", "move_destination": "", "kind": "dimse"})
    r2 = _regra_auto(repo, c, destino={"node_id": morto, "identity_id": None},
                     schedule={"type": "daily", "at": "23:59", "weekdays": list(range(7))})
    r2.pop("id")
    r2["name"] = "Backup"
    rid2 = repo.save_rule(r2)
    antes = datetime.now()
    assert eng.rodar_gestao(repo.rule(rid2))
    fim = _t.time() + 60
    while eng.gestao_em_curso(rid2) and _t.time() < fim:
        app.processEvents()
        _t.sleep(0.05)
    app.processEvents()
    regra2 = repo.rule(rid2)
    assert regra2["config"]["_ultimo"]["situacao"] == "offline" and avisos and "PACS2" in avisos[-1]
    assert 9 <= (regra2["next_run"] - antes).total_seconds() / 60 <= 11, regra2["next_run"]
    assert "tentativa 1 de 2" in regra2["config"]["_ultimo"]["repeticao"]
    # o painel mostra as duas regras, com a situação de cada uma
    from ipe.ui.gestao_auto_ui import PainelAutomatico
    p = PainelAutomatico(w.net, eng)
    linhas = {p.t_regras.item(r, 1).text(): p.t_regras.item(r, 6).text() for r in range(p.t_regras.rowCount())}
    assert linhas["RM no PACS"].startswith("✔") and "2 completado(s) agora" in linhas["RM no PACS"]
    assert sum(t.startswith("⛔") for t in linhas.values()) == 1
    assert p.t_hist.rowCount() >= 2


def test_editor_da_regra_e_aba_automatico(janela, monkeypatch):
    from ipe.ui import gestao_auto_ui as UI
    app, w, st, repo, c = janela
    assert [w.abas.tabText(i) for i in range(w.abas.count())] == ["Conferir agora", "Automático"]
    p = w.painel_auto

    def preencher(dlg):
        dlg.e_nome.setText("Noite")
        r = next(i for i in range(dlg.t_fontes.rowCount()) if dlg.t_fontes.item(i, 1).text().startswith("MR01"))
        dlg.t_fontes.item(r, 0).setCheckState(Qt.Checked)
        dlg.c_destino.setCurrentIndex(dlg.c_destino.findData(next(n["id"] for n in repo.nodes() if n["name"] == "PACS")))
        dlg.r_inteiro.setChecked(True)
        dlg.r_diario.setChecked(True)
        dlg.k_repetir.setChecked(True)
        dlg.s_rep_min.setValue(20)
        dlg._ok()
        return dlg.result()
    from PySide6.QtCore import Qt
    monkeypatch.setattr(UI.RegraGestaoDialog, "exec", preencher)
    rid = p.nova()
    regra = repo.rule(rid)
    cfg = regra["config"]
    assert regra["kind"] == "gestao" and regra["active"] and regra["next_run"] is not None
    assert cfg["envio"] == "inteiro" and cfg["schedule"]["type"] == "daily" and cfg["repetir"] == {"minutos": 20, "vezes": 3}
    assert p.t_regras.rowCount() == 1 and "diariamente" in p.t_regras.item(0, 2).text()
    assert p.duplicar() and p.t_regras.rowCount() == 2
    assert not repo.rule(max(r["id"] for r in repo.rules("gestao")))["active"], "a cópia nasce desligada"
