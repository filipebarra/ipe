"""Link ipe:// cifrado (0.99.31, onda A3 — ideia do Weasis ViewerHub).

O link `ipe://open?accession=123&patientid=456` fica no histórico do navegador, em logs de proxy e no
que o RIS imprime na tela: o ID do paciente vai em texto aberto. Cifrado, o link vira
`ipe://open?c=<texto cifrado>` — sem dado do paciente à vista — e só quem tem o **token da API**
(Rede ▸ Chamada externa) consegue montar um. Por isso o link cifrado abre direto, como o link com
token, e envelhece: passa de 24 h e é recusado (o link copiado de um histórico antigo não abre).

Só biblioteca padrão (hmac + hashlib), para o RIS conseguir montar em qualquer linguagem:

    chave      = SHA-256(token)
    k_cifra    = HMAC-SHA256(chave, "ipe-cifra")
    k_selo     = HMAC-SHA256(chave, "ipe-selo")
    texto      = "accession=123&node=PACS&t=<segundos desde 1970>"     (query de sempre + t)
    nonce      = 16 bytes aleatórios
    fluxo      = HMAC-SHA256(k_cifra, nonce || i) para i = 0, 1, 2… (i em 4 bytes, big-endian)
    cifrado    = texto XOR fluxo
    selo       = HMAC-SHA256(k_selo, nonce || cifrado)[:16]
    c          = base64url(nonce || cifrado || selo), sem "="

`montar(query, token)` faz isso aqui (e `python -m ipe link-cifrado "accession=123" ` na linha de comando).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from urllib.parse import parse_qs

VALIDADE_S = 24 * 3600


class LinkInvalido(ValueError):
    pass


def _chaves(token: str) -> tuple[bytes, bytes]:
    chave = hashlib.sha256(str(token).encode("utf-8")).digest()
    return (hmac.new(chave, b"ipe-cifra", hashlib.sha256).digest(),
            hmac.new(chave, b"ipe-selo", hashlib.sha256).digest())


def _fluxo(k: bytes, nonce: bytes, n: int) -> bytes:
    out = bytearray()
    i = 0
    while len(out) < n:
        out += hmac.new(k, nonce + i.to_bytes(4, "big"), hashlib.sha256).digest()
        i += 1
    return bytes(out[:n])


def montar(query: str, token: str, agora: float | None = None, nonce: bytes | None = None) -> str:
    """O valor de `c=` para a query (sem o `t`, que entra aqui)."""
    if not token:
        raise LinkInvalido("sem o token da API não há como cifrar")
    texto = (query.strip("&?") + f"&t={int(agora if agora is not None else time.time())}").encode("utf-8")
    kc, ks = _chaves(token)
    nonce = nonce or os.urandom(16)
    cif = bytes(a ^ b for a, b in zip(texto, _fluxo(kc, nonce, len(texto))))
    selo = hmac.new(ks, nonce + cif, hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(nonce + cif + selo).decode("ascii").rstrip("=")


def abrir(c: str, token: str, agora: float | None = None, validade_s: int = VALIDADE_S) -> dict[str, list[str]]:
    """A query de dentro do link (parse_qs), conferida e no prazo. Levanta LinkInvalido."""
    if not token:
        raise LinkInvalido("o programa não tem token da API para conferir o link")
    try:
        bruto = base64.urlsafe_b64decode(c + "=" * (-len(c) % 4))
    except (ValueError, TypeError):
        raise LinkInvalido("link cifrado ilegível") from None
    if len(bruto) < 16 + 1 + 16:
        raise LinkInvalido("link cifrado curto demais")
    nonce, cif, selo = bruto[:16], bruto[16:-16], bruto[-16:]
    kc, ks = _chaves(token)
    if not hmac.compare_digest(selo, hmac.new(ks, nonce + cif, hashlib.sha256).digest()[:16]):
        raise LinkInvalido("o link não foi montado com o token deste computador")
    texto = bytes(a ^ b for a, b in zip(cif, _fluxo(kc, nonce, len(cif)))).decode("utf-8", "replace")
    q = parse_qs(texto)
    try:
        t = int((q.pop("t", ["0"]) or ["0"])[0])
    except ValueError:
        t = 0
    agora = agora if agora is not None else time.time()
    if not t or agora - t > validade_s or t - agora > 300:
        raise LinkInvalido("o link venceu (vale 24 horas) — peça outro ao sistema que o montou")
    return q
