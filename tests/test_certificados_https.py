"""0.100.31: no pacote do macOS toda conexão HTTPS conferida falhava (CERTIFICATE_VERIFY_FAILED): o Python de
dentro do pacote não acha os certificados das autoridades. Onde o sistema não os entrega, valem os do certifi."""
import os
import ssl
import sys
from collections import namedtuple

import ipe

_P = namedtuple("_P", "cafile capath")


def test_sem_certificados_do_sistema_usa_o_certifi(monkeypatch, tmp_path):
    import certifi
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(ssl, "get_default_verify_paths", lambda: _P(None, str(tmp_path / "nao_existe")))
    ipe._certificados_https()
    assert os.environ["SSL_CERT_FILE"] == certifi.where() and os.path.isfile(certifi.where())
    ctx = ssl.create_default_context()                       # é o que o urlopen usa
    assert ctx.cert_store_stats()["x509_ca"] > 50


def test_com_certificados_do_sistema_nao_mexe(monkeypatch, tmp_path):
    (tmp_path / "ca.pem").write_text("x")
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(ssl, "get_default_verify_paths", lambda: _P(str(tmp_path / "ca.pem"), None))
    ipe._certificados_https()
    assert "SSL_CERT_FILE" not in os.environ


def test_windows_e_escolha_do_usuario_ficam_como_estao(monkeypatch, tmp_path):
    monkeypatch.setattr(ssl, "get_default_verify_paths", lambda: _P(None, None))
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    ipe._certificados_https()
    assert "SSL_CERT_FILE" not in os.environ
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("SSL_CERT_FILE", "/o/que/o/usuario/pos.pem")
    ipe._certificados_https()
    assert os.environ["SSL_CERT_FILE"] == "/o/que/o/usuario/pos.pem"


def test_vai_no_pacote():
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1]
    assert '"certifi"' in (raiz / "installer" / "ipe.spec").read_text(encoding="utf-8")
    assert '"certifi"' in (raiz / "pyproject.toml").read_text(encoding="utf-8")
