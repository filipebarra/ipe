"""Cliente DICOMweb: busca (QIDO-RS), download (WADO-RS) e envio (STOW-RS).

O teste sobe um servidor HTTP de verdade na porta local e fala com ele pela rede, em vez de
trocar a função de rede por uma mentira: é o que prova que o cabeçalho, a autenticação básica,
o JSON do QIDO e o multipart do WADO estão certos de ponta a ponta.
"""
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ipe.central import dicomweb as DW
from ipe.network.client import DicomError
from ipe.network.dicomweb_client import DicomWebClient, WebTarget

USUARIO, SENHA = "admin", "orthanc"
ESTUDO = "1.2.3.4"
SERIE = "1.2.3.4.5"

QIDO_ESTUDOS = [{
    "0020000D": {"vr": "UI", "Value": [ESTUDO]},
    "00100010": {"vr": "PN", "Value": [{"Alphabetic": "SILVA^MARIA"}]},
    "00100020": {"vr": "LO", "Value": ["12345"]},
    "00100030": {"vr": "DA", "Value": ["19700201"]},
    "00100040": {"vr": "CS", "Value": ["F"]},
    "00080020": {"vr": "DA", "Value": ["20260115"]},
    "00080030": {"vr": "TM", "Value": ["101500"]},
    "00080050": {"vr": "SH", "Value": ["ACC77"]},
    "00081030": {"vr": "LO", "Value": ["RM MAMAS COM CONTRASTE"]},
    "00080061": {"vr": "CS", "Value": ["MR", "SR"]},
    "00201206": {"vr": "IS", "Value": [4]},
    "00201208": {"vr": "IS", "Value": [448]},
}]
QIDO_SERIES = [{
    "0020000E": {"vr": "UI", "Value": [SERIE]},
    "00080060": {"vr": "CS", "Value": ["MR"]},
    "00200011": {"vr": "IS", "Value": [301]},
    "0008103E": {"vr": "LO", "Value": ["Ph1/VIBRANT"]},
    "00201209": {"vr": "IS", "Value": [112]},
}, {
    "0020000E": {"vr": "UI", "Value": ["1.2.3.4.6"]},
    "00080060": {"vr": "CS", "Value": ["MR"]},
    "00200011": {"vr": "IS", "Value": [1]},
    "0008103E": {"vr": "LO", "Value": ["Localizador"]},
    "00201209": {"vr": "IS", "Value": [3]},
}]


def _dicom_bytes(sop: str) -> bytes:
    """Um arquivo DICOM mínimo, de verdade, para o WADO devolver."""
    import io

    import pydicom
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian
    ds = Dataset()
    ds.PatientName = "SILVA^MARIA"
    ds.PatientID = "12345"
    ds.StudyInstanceUID = ESTUDO
    ds.SeriesInstanceUID = SERIE
    ds.SOPInstanceUID = sop
    ds.SOPClassUID = CTImageStorage
    ds.Modality = "MR"
    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = CTImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = sop
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    buf = io.BytesIO()
    pydicom.dcmwrite(buf, ds, enforce_file_format=True)
    return buf.getvalue()


class _Handler(BaseHTTPRequestHandler):
    exigir_senha = True
    recebidos: list[bytes] = []

    def log_message(self, *a):            # silêncio no pytest
        pass

    def _autorizado(self) -> bool:
        if not self.exigir_senha:
            return True
        esperado = "Basic " + base64.b64encode(f"{USUARIO}:{SENHA}".encode()).decode()
        return self.headers.get("Authorization") == esperado

    def _json(self, dados):
        corpo = json.dumps(dados).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/dicom+json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):                      # noqa: N802
        if not self._autorizado():
            self.send_response(401)
            self.end_headers()
            return
        caminho = self.path.split("?")[0]
        if caminho == "/dicom-web/studies":
            if "PatientID=nada" in self.path:
                self.send_response(204)
                self.end_headers()
                return
            self._json(QIDO_ESTUDOS)
        elif caminho == f"/dicom-web/studies/{ESTUDO}/series":
            self._json(QIDO_SERIES)
        elif caminho.startswith(f"/dicom-web/studies/{ESTUDO}"):
            limite = "LIMITE123"
            partes = [b"--" + limite.encode() + b"\r\nContent-Type: application/dicom\r\n\r\n"
                      + _dicom_bytes(f"1.2.3.4.5.{i}") + b"\r\n" for i in (1, 2)]
            corpo = b"".join(partes) + b"--" + limite.encode() + b"--\r\n"
            self.send_response(200)
            self.send_header("Content-Type",
                             f'multipart/related; type="application/dicom"; boundary={limite}')
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):                     # noqa: N802
        if not self._autorizado():
            self.send_response(401)
            self.end_headers()
            return
        n = int(self.headers.get("Content-Length", 0))
        _Handler.recebidos.append(self.rfile.read(n))
        self._json({"00081199": {"vr": "SQ", "Value": []}})


@pytest.fixture()
def servidor():
    _Handler.recebidos = []
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_port}/dicom-web"
    srv.shutdown()
    srv.server_close()


def _alvo(url, **kw):
    return WebTarget("Orthanc", url, USUARIO, SENHA, **kw)


# --------------------------------------------------------------------- alvo

def test_monta_o_alvo_a_partir_do_no():
    t = WebTarget.build({"name": "X", "base_url": "192.168.1.216:8042/dicom-web/",
                         "username": "admin", "password": "orthanc", "verify_tls": False})
    assert t.base_url == "http://192.168.1.216:8042/dicom-web"   # completa o esquema, tira a barra
    assert t.user == "admin" and not t.verify_tls
    with pytest.raises(DicomError) as e:
        WebTarget.build({"name": "Sem URL", "base_url": ""})
    assert "ndereço DICOMweb" in str(e.value)


# --------------------------------------------------------------------- busca

def test_eco_e_busca(servidor):
    cli = DicomWebClient()
    ok, msg = cli.echo(_alvo(servidor))
    assert ok and "DICOMweb respondeu" in msg
    linhas = cli.find_studies(_alvo(servidor), name="Silva")
    assert len(linhas) == 1
    r = linhas[0]
    assert r["study_uid"] == ESTUDO
    assert r["patient_name"] == "SILVA, MARIA"          # mesmo formato do DIMSE
    assert r["accession"] == "ACC77" and r["study_date"] == "20260115"
    assert r["modalities"] == "MR\\SR"
    assert r["num_series"] == 4 and r["num_images"] == 448
    assert set(r) >= {"patient_id", "birth_date", "sex", "study_time", "description"}


def test_busca_sem_resultado_nao_e_erro(servidor):
    """204 sem corpo é resposta legítima do QIDO: nada encontrado."""
    assert DicomWebClient().find_studies(_alvo(servidor), patient_id="nada") == []


def test_series_em_ordem(servidor):
    series = DicomWebClient().find_series(_alvo(servidor), ESTUDO)
    assert [s["series_number"] for s in series] == [1, 301]      # ordenado, como no DIMSE
    assert series[1]["description"] == "Ph1/VIBRANT" and series[1]["num_images"] == 112


def test_senha_errada_diz_o_que_e(servidor):
    with pytest.raises(DicomError) as e:
        DicomWebClient().find_studies(WebTarget("Orthanc", servidor, "admin", "errada"))
    assert "401" in str(e.value) and "usuário ou senha" in str(e.value)


def test_endereco_errado_diz_o_que_e(servidor):
    with pytest.raises(DicomError) as e:
        DicomWebClient().echo(_alvo(servidor + "/errado"))
    assert "404" in str(e.value) and "/dicom-web/" in str(e.value)


def test_servidor_fora_do_ar_nao_estoura_excecao_crua():
    with pytest.raises(DicomError) as e:
        DicomWebClient(timeout=2).echo(_alvo("http://127.0.0.1:9/dicom-web"))
    assert "não consegui falar com o servidor" in str(e.value)


# --------------------------------------------------------------------- download

class _Balde:
    """Faz o papel do sink: guarda o que chegaria ao banco."""

    def __init__(self):
        self.guardados = []

    def store(self, ds, file_meta=None, origin="received"):
        self.guardados.append((str(ds.SOPInstanceUID), origin))


def test_download_entrega_ao_mesmo_sink_do_c_get(servidor):
    balde = _Balde()
    passos = []
    n = DicomWebClient().get(_alvo(servidor), ESTUDO, None, balde,
                             progress=lambda f, t, m: passos.append(m))
    assert n == 2 and len(balde.guardados) == 2
    assert all(origem == "retrieved" for _sop, origem in balde.guardados)
    assert {sop for sop, _o in balde.guardados} == {"1.2.3.4.5.1", "1.2.3.4.5.2"}
    assert passos, "baixou sem relatar progresso"


def test_download_de_series_escolhidas(servidor):
    balde = _Balde()
    assert DicomWebClient().get(_alvo(servidor), ESTUDO, [SERIE], balde) == 2


def test_cancelar_para_no_meio(servidor):
    balde = _Balde()
    cancelar = threading.Event()
    cancelar.set()
    with pytest.raises(DicomError) as e:
        DicomWebClient().get(_alvo(servidor), ESTUDO, None, balde, cancel=cancelar)
    assert "nenhuma imagem" in str(e.value) and not balde.guardados


def test_move_nao_existe_no_dicomweb(servidor):
    with pytest.raises(DicomError) as e:
        DicomWebClient().move(_alvo(servidor), ESTUDO, None)
    assert "C-MOVE não existe" in str(e.value)


# --------------------------------------------------------------------- envio

def test_envio_stow(servidor, tmp_path):
    arq = tmp_path / "a.dcm"
    arq.write_bytes(_dicom_bytes("1.2.3.4.5.9"))
    enviados, falhas = DicomWebClient().store(_alvo(servidor), [str(arq)])
    assert (enviados, falhas) == (1, 0)
    assert _Handler.recebidos, "o servidor não recebeu nada"
    assert b"application/dicom" in _Handler.recebidos[0]


# --------------------------------------------------------------------- integração

def test_o_banco_guarda_o_no_dicomweb(env):
    """Coluna nova em banco que já existia: a migração automática tem de dar conta."""
    paths, db, repo = env
    rid = repo.save_node({"name": "Orthanc SILICONE", "kind": "dicomweb",
                          "base_url": "http://192.168.1.216:8042/dicom-web",
                          "username": "admin", "password": "x", "verify_tls": False,
                          "use_in_search": True, "active": True})
    n = repo.node(rid)
    assert n["kind"] == "dicomweb" and n["base_url"].endswith("/dicom-web")
    assert n["username"] == "admin" and n["verify_tls"] is False


def test_os_nos_de_consulta_incluem_dicomweb(env):
    from ipe.network import nodes as NODES
    paths, db, repo = env
    repo.save_node({"name": "PACS", "kind": "dimse", "ae_title": "P", "host": "h", "port": 104,
                    "use_in_search": True, "active": True})
    repo.save_node({"name": "Web", "kind": "dicomweb", "base_url": "http://x/dicom-web",
                    "use_in_search": True, "active": True})
    assert {n["name"] for n in NODES.search_nodes(repo)} == {"PACS", "Web"}


def test_o_servico_escolhe_o_cliente_pelo_tipo(env, servidor):
    """O resto do programa chama `buscar` sem saber o protocolo: quem decide é o serviço."""
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    web = {"name": "Orthanc", "kind": "dicomweb", "base_url": servidor,
           "username": USUARIO, "password": SENHA, "verify_tls": True}
    dimse = {"name": "PACS", "kind": "dimse", "ae_title": "P", "host": "127.0.0.1", "port": 104}
    assert w.net.eh_web(web) and not w.net.eh_web(dimse)
    assert type(w.net.cliente(web)).__name__ == "DicomWebClient"
    assert type(w.net.cliente(dimse)).__name__ == "DicomClient"
    assert isinstance(w.net.target(web), WebTarget)
    # e a busca de verdade, pelo serviço, chega ao servidor
    resultado = {}
    w.net.search([{**web, "id": 1}], None, {"name": "Silva"},
                 lambda res, err: resultado.update({"res": res, "err": err}))
    for _ in range(100):
        QApplication.processEvents()
        if resultado:
            break
        import time as _t
        _t.sleep(0.05)
    assert resultado.get("err") is None
    linhas, erros = resultado["res"]
    assert not erros and linhas and linhas[0]["accession"] == "ACC77"
    assert linhas[0]["node_name"] == "Orthanc"
    w.close()


def test_identidade_de_ae_nao_vale_no_dicomweb(env, servidor):
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    web = {"name": "Orthanc", "kind": "dicomweb", "base_url": servidor, "id": 1}
    with pytest.raises(DicomError) as e:
        w.net.target(web, {"name": "Dr. X", "ae_title": "DRX"})
    assert "usuário e a senha" in str(e.value)
    w.close()


def test_a_tela_do_no_troca_os_campos(env):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from ipe.ui.network_dialog import NodeDialog
    dlg = NodeDialog(None)
    assert not dlg.eh_web()
    assert dlg.ae.isVisibleTo(dlg) and not dlg.base_url.isVisibleTo(dlg)
    dlg.kind.setCurrentIndex(dlg.kind.findData("dicomweb"))
    assert dlg.eh_web()
    assert dlg.base_url.isVisibleTo(dlg) and dlg.user.isVisibleTo(dlg)
    assert not dlg.ae.isVisibleTo(dlg) and not dlg.retrieve.isVisibleTo(dlg)
    dlg.name.setText("Orthanc SILICONE")
    dlg.base_url.setText("http://192.168.1.216:8042/dicom-web/")
    dlg.user.setText("admin")
    dlg.senha.setText("orthanc")
    dlg.tls.setChecked(True)
    dlg._ok()
    d = dlg.data
    assert d["kind"] == "dicomweb" and d["base_url"] == "http://192.168.1.216:8042/dicom-web"
    assert d["username"] == "admin" and d["password"] == "orthanc"
    assert d["verify_tls"] is False          # marcou "aceitar não verificado"
    dlg.close()


def test_a_tela_recusa_dicomweb_sem_endereco(env, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox
    QApplication.instance() or QApplication([])
    from ipe.ui.network_dialog import NodeDialog
    avisos = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: avisos.append(a[2]))
    dlg = NodeDialog(None)
    dlg.kind.setCurrentIndex(dlg.kind.findData("dicomweb"))
    dlg.name.setText("X")
    dlg._ok()
    assert avisos and "/dicom-web" in avisos[0]
    dlg.close()
