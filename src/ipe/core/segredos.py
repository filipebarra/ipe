"""Senhas e chaves guardadas cifradas (0.99.54, onda B3 do plano ViewerHub/Eden).

Até a 0.99.53 a senha dos nós DICOMweb ficava em texto claro no banco. Agora todo segredo que o programa
guarda (senha do DICOMweb, segredo do cliente OAuth2, chave da IA de texto do laudo) passa por aqui:

- **Windows**: DPAPI do sistema (``CryptProtectData``) no escopo da **máquina** — qualquer conta deste
  computador decifra, mas o banco copiado para outro computador não abre as senhas;
- **Linux e outros**: chave aleatória de 32 bytes num arquivo da pasta de configuração (permissão 0600) e
  cifra de fluxo HMAC-SHA256 em modo contador + etiqueta HMAC (cifrar-e-autenticar), só com a biblioteca
  padrão. Protege contra quem só tem o banco; quem tem a conta do usuário tem a chave.

O texto cifrado começa com ``enc1:`` (DPAPI: ``enc1:w:``; arquivo: ``enc1:k:``). ``abrir()`` devolve o
texto claro de um valor antigo (sem prefixo) como está — a migração é gravar de novo.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

PREFIXO = "enc1:"
#: pasta da chave local (Linux); None = a pasta de configuração do programa
PASTA: Path | None = None


class SegredoInvalido(ValueError):
    pass


# ------------------------------------------------------------------ chave em arquivo (Linux e outros)
def _pasta() -> Path:
    if PASTA is not None:
        return Path(PASTA)
    from platformdirs import user_config_dir
    from ipe import DATA_NAME
    return Path(user_config_dir(DATA_NAME, appauthor=False))


def _chave() -> bytes:
    p = _pasta() / "chave_local.bin"
    if p.exists():
        k = p.read_bytes()
        if len(k) == 32:
            return k
    p.parent.mkdir(parents=True, exist_ok=True)
    k = os.urandom(32)
    p.write_bytes(k)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return k


def _fluxo(chave: bytes, nonce: bytes, n: int) -> bytes:
    out = bytearray()
    i = 0
    while len(out) < n:
        out += hmac.new(chave, b"ipe-fluxo" + nonce + i.to_bytes(8, "big"), hashlib.sha256).digest()
        i += 1
    return bytes(out[:n])


def _cifrar_k(dados: bytes) -> bytes:
    k = _chave()
    ke, ka = hashlib.sha256(k + b"enc").digest(), hashlib.sha256(k + b"mac").digest()
    nonce = os.urandom(16)
    c = bytes(a ^ b for a, b in zip(dados, _fluxo(ke, nonce, len(dados))))
    tag = hmac.new(ka, nonce + c, hashlib.sha256).digest()[:16]
    return nonce + c + tag


def _decifrar_k(blob: bytes) -> bytes:
    if len(blob) < 32:
        raise SegredoInvalido("segredo curto demais")
    k = _chave()
    ke, ka = hashlib.sha256(k + b"enc").digest(), hashlib.sha256(k + b"mac").digest()
    nonce, c, tag = blob[:16], blob[16:-16], blob[-16:]
    if not hmac.compare_digest(tag, hmac.new(ka, nonce + c, hashlib.sha256).digest()[:16]):
        raise SegredoInvalido("a senha foi gravada com a chave de outro computador")
    return bytes(a ^ b for a, b in zip(c, _fluxo(ke, nonce, len(c))))


# ------------------------------------------------------------------ DPAPI (Windows)
def _dpapi(dados: bytes, cifrar: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(dados, len(dados))
    ent = BLOB(len(dados), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    sai = BLOB()
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    LOCAL_MACHINE, UI_FORBIDDEN = 0x4, 0x1
    if cifrar:
        ok = crypt32.CryptProtectData(ctypes.byref(ent), ctypes.c_wchar_p("Ipe"), None, None, None,
                                      LOCAL_MACHINE | UI_FORBIDDEN, ctypes.byref(sai))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(ent), None, None, None, None, UI_FORBIDDEN,
                                        ctypes.byref(sai))
    if not ok:
        raise SegredoInvalido("o Windows não abriu a senha (DPAPI)")
    try:
        return ctypes.string_at(sai.pbData, sai.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(sai.pbData, ctypes.c_void_p))


def _usa_dpapi() -> bool:
    return sys.platform == "win32" and os.environ.get("IPE_SEGREDO_ARQUIVO") != "1"


# ------------------------------------------------------------------ interface
def cifrado(valor) -> bool:
    return isinstance(valor, str) and valor.startswith(PREFIXO)


def guardar(texto: str) -> str:
    """Texto claro → texto cifrado para gravar. Vazio continua vazio; já cifrado não cifra de novo."""
    if not texto:
        return ""
    if cifrado(texto):
        return texto
    dados = texto.encode("utf-8")
    if _usa_dpapi():
        try:
            return PREFIXO + "w:" + base64.b64encode(_dpapi(dados, True)).decode()
        except Exception:  # noqa: BLE001
            log.exception("DPAPI; usando a chave em arquivo")
    return PREFIXO + "k:" + base64.b64encode(_cifrar_k(dados)).decode()


def abrir(valor: str) -> str:
    """Texto gravado → texto claro. Valor antigo, sem prefixo, volta como está."""
    if not valor or not cifrado(valor):
        return valor or ""
    tipo, _, corpo = valor[len(PREFIXO):].partition(":")
    blob = base64.b64decode(corpo.encode())
    if tipo == "w":
        if sys.platform != "win32":
            raise SegredoInvalido("senha cifrada pelo Windows: digite de novo neste computador")
        return _dpapi(blob, False).decode("utf-8")
    if tipo == "k":
        return _decifrar_k(blob).decode("utf-8")
    raise SegredoInvalido(f"formato desconhecido: {tipo}")


def abrir_ou_vazio(valor: str) -> str:
    """Como `abrir`, mas sem levantar erro: senha que não abre vira "" (e fica no registro)."""
    try:
        return abrir(valor)
    except Exception:  # noqa: BLE001
        log.warning("segredo que não abre neste computador (digite de novo)")
        return ""
