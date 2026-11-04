"""OAuth2 / OpenID Connect nos nós DICOMweb (0.99.55, onda B3 do plano ViewerHub/Eden).

PACS na nuvem e servidores com Keycloak (dcm4chee-arc, Orthanc com plugin de autorização, Google Cloud
Healthcare, Azure DICOM) não aceitam usuário e senha direto no pedido DICOMweb: pedem um **token**. O nó
DICOMweb passa a ter quatro jeitos de se apresentar:

- ``basic`` — usuário e senha (como antes);
- ``oauth2_cliente`` — credenciais do cliente (*client credentials*): ID e segredo do cliente;
- ``oauth2_senha`` — usuário e senha trocados por token (*password grant*, comum no Keycloak);
- ``token`` — token fixo (Bearer), colado à mão.

O endereço do token pode ser o próprio *token endpoint* ou o do emissor (OIDC): nesse caso o programa lê
``/.well-known/openid-configuration`` e acha o endpoint. O token fica na memória até perto de vencer (30 s
antes); com *refresh token*, renova sem pedir a senha de novo; uma resposta 401 descarta o token e tenta
uma vez com um novo.
"""
from __future__ import annotations

import json
import logging
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

TIPOS = {"basic": "Usuário e senha (Basic)", "oauth2_cliente": "OAuth2 — credenciais do cliente",
         "oauth2_senha": "OAuth2 — usuário e senha (Keycloak)", "token": "Token fixo (Bearer)"}
FOLGA_S = 30


class ErroDeToken(RuntimeError):
    pass


def _ctx(verificar: bool):
    if verificar:
        return None
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def _pedir_json(url: str, dados: dict | None = None, verificar: bool = True, tempo: float = 20):
    corpo = urllib.parse.urlencode(dados).encode("ascii") if dados is not None else None
    req = urllib.request.Request(url, data=corpo, method="POST" if corpo is not None else "GET")
    req.add_header("Accept", "application/json")
    if corpo is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=tempo, context=_ctx(verificar)) as r:  # noqa: S310
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            j = json.loads(e.read().decode("utf-8") or "{}")
            motivo = j.get("error_description") or j.get("error") or e.reason
        except ValueError:
            motivo = e.reason
        raise ErroDeToken(f"o servidor de login respondeu {e.code}: {motivo}") from None
    except urllib.error.URLError as e:
        raise ErroDeToken(f"sem conexão com o servidor de login ({getattr(e, 'reason', e)})") from None


def endpoint_do_token(url: str, verificar: bool = True, pedir=None) -> str:
    """O *token endpoint*: o próprio endereço, ou o que o emissor OIDC anuncia."""
    pedir = pedir or _pedir_json
    u = (url or "").strip().rstrip("/")
    if not u:
        raise ErroDeToken("falta o endereço do token (ou do emissor OIDC)")
    if u.endswith("/token") or "/token?" in u or u.endswith("/oauth2/token"):
        return u
    descoberta = u if u.endswith("/.well-known/openid-configuration") else u + "/.well-known/openid-configuration"
    j = pedir(descoberta, None, verificar)
    ep = (j or {}).get("token_endpoint")
    if not ep:
        raise ErroDeToken(f"o emissor {u} não anuncia o token_endpoint")
    return ep


class Tokens:
    """Guarda os tokens na memória, um por (endpoint, cliente, usuário)."""

    def __init__(self, pedir=None, relogio=time.time):
        self._pedir = pedir or _pedir_json
        self._agora = relogio
        self._cache: dict[tuple, dict] = {}
        self._endpoints: dict[str, str] = {}
        self._trava = threading.Lock()

    def _chave(self, cfg: dict) -> tuple:
        return (cfg.get("token_url", ""), cfg.get("client_id", ""), cfg.get("user", ""), cfg.get("auth", ""))

    def esquecer(self, cfg: dict) -> None:
        with self._trava:
            self._cache.pop(self._chave(cfg), None)

    def token(self, cfg: dict) -> str:
        """Bearer válido para o nó. `cfg`: auth, token_url, client_id, client_secret, scope, user, password,
        verify_tls."""
        auth = cfg.get("auth") or "basic"
        if auth == "token":
            if not cfg.get("password"):
                raise ErroDeToken("falta o token (campo Senha / token)")
            return cfg["password"]
        if auth not in ("oauth2_cliente", "oauth2_senha"):
            raise ErroDeToken(f"autenticação sem token: {auth}")
        k = self._chave(cfg)
        with self._trava:
            atual = self._cache.get(k)
        if atual and atual["vence"] - FOLGA_S > self._agora():
            return atual["access_token"]
        verificar = bool(cfg.get("verify_tls", True))
        url = cfg.get("token_url", "")
        ep = self._endpoints.get(url) or endpoint_do_token(url, verificar, self._pedir)
        self._endpoints[url] = ep
        base = {"client_id": cfg.get("client_id", "")}
        if cfg.get("client_secret"):
            base["client_secret"] = cfg["client_secret"]
        if cfg.get("scope"):
            base["scope"] = cfg["scope"]
        resp = None
        if atual and atual.get("refresh_token"):
            try:
                resp = self._pedir(ep, {**base, "grant_type": "refresh_token",
                                        "refresh_token": atual["refresh_token"]}, verificar)
            except ErroDeToken:
                resp = None
        if resp is None:
            if auth == "oauth2_cliente":
                if not cfg.get("client_id"):
                    raise ErroDeToken("falta o ID do cliente")
                resp = self._pedir(ep, {**base, "grant_type": "client_credentials"}, verificar)
            else:
                if not cfg.get("user"):
                    raise ErroDeToken("falta o usuário")
                resp = self._pedir(ep, {**base, "grant_type": "password", "username": cfg.get("user", ""),
                                        "password": cfg.get("password", "")}, verificar)
        tok = (resp or {}).get("access_token")
        if not tok:
            raise ErroDeToken("o servidor de login não devolveu access_token")
        vence = self._agora() + float((resp or {}).get("expires_in") or 300)
        with self._trava:
            self._cache[k] = {"access_token": tok, "vence": vence, "refresh_token": resp.get("refresh_token", "")}
        return tok


#: um só para o programa (os tokens valem para todas as buscas e downloads)
TOKENS = Tokens()
