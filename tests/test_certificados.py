"""0.99.74 — certificados da rede interna: AC do Ipê, HTTPS no servidor central e o cliente que confia nele."""
import ssl

import pytest

pytest.importorskip("cryptography")

from ipe.central.remote import RemoteClient, RemoteError  # noqa: E402
from ipe.central.server import CentralServer  # noqa: E402
from ipe.core import certificados as CE  # noqa: E402


def test_gerar_e_conferir(tmp_path):
    r = CE.gerar(tmp_path / "c", ["servidor-imeb", "localhost"], ["127.0.0.1", "192.168.1.216"])
    inf = CE.info(r["certfile"])
    assert inf["nomes"] == ["servidor-imeb", "localhost"] and inf["ips"] == ["127.0.0.1", "192.168.1.216"]
    assert r["impressao_ac"].count(":") == 31 and CE.ac_ao_lado(r["certfile"]).decode() == r["ac_pem"]
    # gerar de novo troca o certificado do servidor, mas a AC é a mesma (os clientes continuam confiando)
    r2 = CE.gerar(tmp_path / "c", ["outro"], ["127.0.0.1"])
    assert r2["impressao_ac"] == r["impressao_ac"] and CE.info(r2["certfile"])["nomes"] == ["outro"]
    # o par cert/chave carrega no ssl do Python, com a cadeia
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(r2["certfile"], r2["keyfile"])


def test_https_com_a_ac_interna(env, tmp_path):
    paths, db, repo = env
    r = CE.gerar(tmp_path / "c", ["localhost"], ["127.0.0.1"])
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1", certfile=r["certfile"],
                        keyfile=r["keyfile"])
    srv.start()
    try:
        url = f"https://127.0.0.1:{srv.port}"
        pem = RemoteClient.buscar_ac(url)
        assert CE.impressao(pem) == r["impressao_ac"]
        assert RemoteClient(url, ca_pem=pem).ping()["ok"]                    # conferido de verdade
        with pytest.raises(RemoteError):                                     # sem a AC: o certificado é recusado
            RemoteClient(url, verify_tls=True).ping()
        outra = CE.gerar(tmp_path / "outra", ["localhost"], ["127.0.0.1"])["ac_pem"]
        with pytest.raises(RemoteError):                                     # AC de outro servidor: recusado
            RemoteClient(url, ca_pem=outra).ping()
        assert RemoteClient(url, verify_tls=False).ping()["ok"]              # o modo antigo continua
        with pytest.raises(RemoteError, match="https"):
            RemoteClient.buscar_ac(f"http://127.0.0.1:{srv.port}")
    finally:
        srv.stop()


def test_tela(env, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.ui.central_dialog import CentralDialog
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    s = Settings(paths.settings_file)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: QMessageBox.Ok)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    d = CentralDialog(s)
    r = d.gerar_certificado()
    assert r and d.cert.text() == r["certfile"] and "Vale para" in d.cert_info.text()
    assert not d.aviso_http.isVisibleTo(d)
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1", certfile=r["certfile"],
                        keyfile=r["keyfile"])
    srv.start()
    try:
        d.r_client.setChecked(True)
        d.url.setText(f"http://127.0.0.1:{srv.port}")
        assert d.confiar_no_servidor() and d.url.text().startswith("https://") and d.verify.isChecked()
        assert d.test()
        d._ok()
        assert s.get("central.ca_pem") == r["ac_pem"]
    finally:
        srv.stop()
    app.processEvents()
