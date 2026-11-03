"""0.99.31 — onda A, parte 1: trava de leitura do laudo (A1), abertura IHE IID com filtros (A2) e link
ipe:// cifrado (A3)."""
import time

import pytest
from PySide6.QtWidgets import QApplication

from ipe.auth import session as S
from ipe.network import link_cifrado as LC
from ipe.network.external import ExternalError, filtrar_estudos, parse_url, payload_from_query

SENHA = "uma senha comprida"


@pytest.fixture(autouse=True)
def _sessao_volta():
    antes = S.get()
    yield
    S.set_current(antes)


# ------------------------------------------------------------------ A3: link cifrado
def test_link_cifrado():
    c = LC.montar("accession=123&patientid=FANT001", "segredo")
    assert "FANT001" not in c and "123" not in c
    q = LC.abrir(c, "segredo")
    assert q == {"accession": ["123"], "patientid": ["FANT001"]}
    with pytest.raises(LC.LinkInvalido, match="token"):
        LC.abrir(c, "outro")
    adulterado = c[:30] + ("A" if c[30] != "A" else "B") + c[31:]
    with pytest.raises(LC.LinkInvalido):
        LC.abrir(adulterado, "segredo")
    velho = LC.montar("accession=1", "segredo", agora=time.time() - 25 * 3600)
    with pytest.raises(LC.LinkInvalido, match="venceu"):
        LC.abrir(velho, "segredo")
    p = parse_url(f"ipe://open?c={c}")
    assert p["cifrado"] == c and "accession" not in p


def test_link_cifrado_abre_na_janela_sem_perguntar(env, sample_dir, monkeypatch):
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    cfg = Settings(paths.settings_file)
    cfg.set("dicom", {**(cfg.get("dicom", {}) or {}), "http_token": "tok123", "link_sem_token": "recusar"})
    w = MainWindow(paths, cfg, repo=repo, db=db)
    abertos = []
    monkeypatch.setattr(w, "abrir_exame_do_pedido", lambda uid, so: abertos.append(uid))
    try:
        assert w.handle_external({**parse_url("ipe://open?accession=ACC1001"), "source": "link"}) == "recusado"
        c = LC.montar("accession=ACC1001", "tok123")
        assert w.handle_external({**parse_url(f"ipe://open?c={c}"), "source": "link"}) == "aberto"
        assert abertos == repo.find_study_uids(accession="ACC1001")
        ruim = LC.montar("accession=ACC1001", "outro")
        assert w.handle_external({**parse_url(f"ipe://open?c={ruim}"), "source": "link"}) == "recusado"
    finally:
        w.close()


# ------------------------------------------------------------------ A2: IHE IID e filtros
def test_parametros_do_ihe_iid():
    p = payload_from_query("IHEInvokeImageDisplay", {
        "requestType": ["PATIENT"], "patientID": ["FANT001^^^HOSP,FANT002^^^HOSP"], "mostRecentResults": ["2"],
        "modalitiesInStudy": ["CT,MR"], "lowerDateTime": ["2025-01-01T00:00:00"], "viewerType": ["IHE_BIR"],
        "containsInDescription": ["torax"]})
    assert p == {"command": "open", "tipo": "PATIENT", "patient_id": "FANT001,FANT002", "recentes": "2",
                 "modalidades": "CT,MR", "data_de": "20250101", "descricao": "torax"}
    with pytest.raises(ExternalError):
        payload_from_query("open", {"patientID": ["1"], "requestType": ["SERIES"]})
    estudos = [{"study_date": "20240101", "modalities": "CT", "description": "TC TÓRAX"},
               {"study_date": "20260101", "modalities": "CT\\PT", "description": "PET-CT"},
               {"study_date": "20250601", "modalities": "CT", "description": "TC Tórax"},
               {"study_date": "20250701", "modalities": "MR", "description": "RM mamas"}]
    f = filtrar_estudos(estudos, {"modalidades": "CT", "data_de": "20250101", "descricao": "torax"})
    assert [e["study_date"] for e in f] == ["20250601"]
    assert [e["study_date"] for e in filtrar_estudos(estudos, {"recentes": "2"})] == ["20260101", "20250701"]


def test_abrir_pelo_paciente_com_filtros_e_pela_rota_http(env, sample_dir, monkeypatch):
    from PySide6.QtNetwork import QHostAddress
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    abertos = []
    monkeypatch.setattr(w, "abrir_exame_do_pedido", lambda uid, so: abertos.append(uid))
    try:
        pedido = payload_from_query("IHEInvokeImageDisplay", {"requestType": ["PATIENT"], "patientID": ["FANT001"],
                                                               "modalitiesInStudy": ["CT"]})
        uids = w.exames_do_pedido(pedido)
        infos = [repo.study_info(u) for u in uids]
        assert len(uids) == 2 and all("CT" in i["modalities"] for i in infos)
        assert infos[0]["study_date"] > infos[1]["study_date"]                  # do mais recente
        assert len(w.exames_do_pedido({**pedido, "recentes": "1"})) == 1
        assert len(w.exames_do_pedido({"patient_id": "FANT001"})) == 1          # sem filtro: o mais recente
        # a rota HTTP do IHE IID
        w.http.token = "tok"
        raw = b"GET /IHEInvokeImageDisplay?requestType=STUDY&studyUID=" + uids[0].encode() + \
            b"&token=tok HTTP/1.1\r\nHost: x\r\n\r\n"
        codigo, corpo = w.http._handle(raw, QHostAddress("127.0.0.1"))
        assert codigo.startswith("200") and corpo["resultado"] == "aberto" and abertos[-1] == uids[0]
    finally:
        w.close()


# ------------------------------------------------------------------ A1: trava de leitura
def test_trava_de_leitura_no_servidor(env, sample_dir):
    from ipe.auth.backend import LocalAuth
    from ipe.central.remote import RemoteClient, RemoteError
    from ipe.central.server import CentralServer
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    LocalAuth(repo).create_first_admin("adm", "Adm", SENHA)
    for n in ("ana", "bia"):
        repo.save_user({"username": n, "full_name": n.title(), "role": "medico", "password": SENHA})
    uid = repo.search_studies()[0].study_uid
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    try:
        c = {}
        for n in ("ana", "bia"):
            c[n] = RemoteClient(f"http://127.0.0.1:{srv.port}")
            c[n].login(n, SENHA)
        assert c["ana"].rpc("leitura_comecar", uid)["ok"]
        r = c["bia"].rpc("leitura_comecar", uid)
        assert not r["ok"] and r["de"] == "Ana"
        assert c["bia"].rpc("leituras_ativas")[uid]["usuario"] == "ana"
        with pytest.raises(RemoteError, match="laudando"):
            c["bia"].rpc("save_report", {"study_uid": uid, "text": "x"})
        rid = c["ana"].rpc("save_report", {"study_uid": uid, "text": "da Ana"})
        assert c["bia"].rpc("leitura_comecar", uid, True)["ok"]              # a Bia assume
        assert repo.access_log(action="assumiu_laudo")
        with pytest.raises(RemoteError, match="laudando"):
            c["ana"].rpc("sign_report", rid, "Ana")
        assert c["bia"].rpc("leitura_terminar", uid)
        assert c["ana"].rpc("save_report", {"id": rid, "study_uid": uid, "text": "de novo"})
        # sem aviso por mais que a validade, a trava cai
        srv.leituras.validade_s = 0
        assert c["ana"].rpc("leitura_comecar", uid)["ok"]
        time.sleep(0.01)
        assert c["bia"].rpc("leitura_comecar", uid)["ok"]
    finally:
        srv.stop()


def test_janela_do_laudo_so_leitura(env, sample_dir, monkeypatch):
    from ipe.importer.scanner import Importer
    from ipe.ui.report_window import ReportWindow
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    uid = repo.search_studies()[0].study_uid
    terminou = []

    class Ocupado(type(repo)):
        remote = True

        def leitura_comecar(self, study_uid, forcar=False):
            return {"ok": True} if forcar else {"ok": False, "de": "Dra. Ana", "desde": "10:05"}

        def leitura_terminar(self, study_uid):
            terminou.append(study_uid)
            return True
    r2 = Ocupado(db)
    monkeypatch.setattr(ReportWindow, "perguntar_leitura", lambda self, r: "ler")
    w = ReportWindow(r2, uid)
    try:
        assert w.so_leitura.startswith("Dra. Ana") and w.editor.isReadOnly() and not w.b_save.isEnabled()
        assert "Só leitura" in w.status.text()
        assert w.save_draft()                                       # não grava nada
        assert not repo.reports(uid)
    finally:
        w.close()
    assert terminou == []                                           # a trava é da Ana: não solta
    monkeypatch.setattr(ReportWindow, "perguntar_leitura", lambda self, r: "assumir")
    w = ReportWindow(r2, uid)
    try:
        assert not w.so_leitura and not w.editor.isReadOnly()
    finally:
        w.close()
    assert terminou == [uid]
