"""0.99.55 — onda B3: OAuth2/OIDC nos nós DICOMweb e senhas cifradas no banco."""
import json

import pytest
from PySide6.QtWidgets import QApplication

from ipe.core import segredos as SG
from ipe.network import oauth


@pytest.fixture(autouse=True)
def _chave(tmp_path, monkeypatch):
    monkeypatch.setattr(SG, "PASTA", tmp_path / "chave")
    monkeypatch.setenv("IPE_SEGREDO_ARQUIVO", "1")


class _Servidor:
    def __init__(self):
        self.pedidos = []
        self.n = 0

    def __call__(self, url, dados, verificar):
        self.pedidos.append((url, dict(dados or {})))
        if url.endswith("/.well-known/openid-configuration"):
            return {"token_endpoint": "https://login/realms/pacs/protocol/openid-connect/token"}
        self.n += 1
        return {"access_token": f"tok{self.n}", "expires_in": 60, "refresh_token": "r1"}


def test_tokens_cliente_descoberta_e_cache():
    srv, agora = _Servidor(), [1000.0]
    T = oauth.Tokens(pedir=srv, relogio=lambda: agora[0])
    cfg = {"auth": "oauth2_cliente", "token_url": "https://login/realms/pacs", "client_id": "ipe",
           "client_secret": "s3", "scope": "dicomweb"}
    assert T.token(cfg) == "tok1"
    assert srv.pedidos[0][0].endswith("/.well-known/openid-configuration")
    assert srv.pedidos[1][1] == {"client_id": "ipe", "client_secret": "s3", "scope": "dicomweb",
                                 "grant_type": "client_credentials"}
    assert T.token(cfg) == "tok1" and len(srv.pedidos) == 2           # na memória
    agora[0] += 40                                                     # perto de vencer: renova
    assert T.token(cfg) == "tok2" and srv.pedidos[-1][1]["grant_type"] == "refresh_token"
    T.esquecer(cfg)
    assert T.token(cfg) == "tok3"
    s2 = {"auth": "oauth2_senha", "token_url": "https://x/token", "client_id": "c", "user": "ana", "password": "p"}
    assert T.token(s2) == "tok4" and srv.pedidos[-1][1]["grant_type"] == "password"
    assert srv.pedidos[-1][0] == "https://x/token"
    assert T.token({"auth": "token", "password": "fixo"}) == "fixo"
    with pytest.raises(oauth.ErroDeToken):
        T.token({"auth": "oauth2_cliente", "token_url": "https://x/token"})
    with pytest.raises(oauth.ErroDeToken):
        oauth.endpoint_do_token("https://sem", pedir=lambda *a: {})


def test_senha_cifrada_no_banco_e_migracao(env):
    from sqlalchemy import select
    from ipe.db.models import DicomNode
    paths, db, repo = env
    nid = repo.save_node({"name": "PACS web", "kind": "dicomweb", "base_url": "http://x/dicom-web",
                          "username": "ana", "password": "segredo", "auth": "oauth2_senha",
                          "token_url": "https://login/token", "client_id": "ipe", "client_secret": "cs"})
    with db.session() as s:
        n = s.get(DicomNode, nid)
        assert n.password.startswith("enc1:") and "segredo" not in n.password
        assert n.client_secret.startswith("enc1:")
        n2 = DicomNode(name="velho", kind="dicomweb", base_url="http://y", username="u", password="claro")
        s.add(n2)
        s.flush()
        velho = n2.id
    d = repo.node(nid)
    assert d["password"] == "segredo" and d["client_secret"] == "cs" and d["auth"] == "oauth2_senha"
    assert repo.node(velho)["password"] == "claro"
    with db.session() as s:                                            # migrou ao ler
        assert s.get(DicomNode, velho).password.startswith("enc1:")
    assert repo.node(velho)["auth"] == "basic"


def test_cliente_dicomweb_manda_bearer_e_tenta_de_novo_no_401(monkeypatch):
    import io
    import urllib.error
    from ipe.network import dicomweb_client as W
    srv = _Servidor()
    monkeypatch.setattr(oauth, "TOKENS", oauth.Tokens(pedir=srv))
    vistos = []

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def abrir(req, timeout=None, context=None):
        vistos.append(req.get_header("Authorization"))
        if len(vistos) == 1:
            raise urllib.error.HTTPError(req.full_url, 401, "x", {}, io.BytesIO(b""))
        return Resp(json.dumps([]).encode())
    monkeypatch.setattr(W.urllib.request, "urlopen", abrir)
    t = W.WebTarget.build({"name": "n", "base_url": "http://pacs/dicom-web", "auth": "oauth2_cliente",
                           "token_url": "https://login/token", "client_id": "c"})
    assert W.DicomWebClient().find_studies(t, name="X") == []
    assert vistos == ["Bearer tok1", "Bearer tok2"]
    tb = W.WebTarget.build({"name": "n", "base_url": "http://pacs", "username": "u", "password": "p"})
    vistos.clear()
    vistos.append("ja")                                                  # sem 401 desta vez
    W.DicomWebClient().find_studies(tb, name="X")
    assert vistos[-1].startswith("Basic ")


def test_tela_do_no(env):
    from ipe.ui.network_dialog import NodeDialog
    QApplication.instance() or QApplication([])
    d = NodeDialog({"name": "w", "kind": "dicomweb", "base_url": "http://x"})
    d.auth.setCurrentIndex(d.auth.findData("oauth2_cliente"))
    assert not d._linhas["user"][1].isVisibleTo(d) and d._linhas["client_id"][1].isVisibleTo(d)
    d.token_url.setText("https://login/realms/pacs")
    d.client_id.setText("ipe")
    d.client_secret.setText("s")
    d._ok()
    assert d.data["auth"] == "oauth2_cliente" and d.data["client_id"] == "ipe" and d.data["client_secret"] == "s"
    d.auth.setCurrentIndex(d.auth.findData("token"))
    assert d.senha.isVisibleTo(d) and not d._linhas["token_url"][1].isVisibleTo(d)
