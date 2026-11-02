"""Quem pode falar com o programa pela rede (0.99.24, revisão de segurança).

Pedido dele, depois da revisão: corrigir as brechas do link sem token, do servidor central, da
impressora DICOM e do AE Title que se imita.

- **AE + IP** (`ip_do_no_confere`): o AE Title do DICOM é só um nome que o aparelho diz ter —
  qualquer um na rede pode dizer "sou o TC1". Conferir também o endereço do nó cadastrado fecha isso.
- **Rede local** (`ip_da_rede_local`): a impressora DICOM aceitava qualquer AE de qualquer lugar. As
  modalidades estão sempre na rede interna; o que vem de fora dela não é modalidade.
- **Tentativas de login** (`Tentativas`): o servidor central não limitava senha errada.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import threading
import time

log = logging.getLogger(__name__)

#: 100.64.0.0/10 (rede compartilhada de operadora / VPNs como o Tailscale) não é "privada" para o
#: módulo ipaddress, mas é rede de dentro
_DE_DENTRO = (ipaddress.ip_network("100.64.0.0/10"),)


def _ip(texto: str):
    try:
        return ipaddress.ip_address(str(texto or "").strip().replace("::ffff:", ""))
    except ValueError:
        return None


def ip_da_rede_local(ip: str) -> bool:
    """Endereço da rede interna (10/8, 172.16/12, 192.168/16, 100.64/10, link-local) ou do próprio
    computador."""
    a = _ip(ip)
    if a is None:
        return False
    return bool(a.is_private or a.is_loopback or a.is_link_local or any(a in r for r in _DE_DENTRO))


_cache_host: dict[str, tuple[float, set[str]]] = {}
_lock = threading.Lock()


def ips_do_host(host: str, validade_s: float = 300.0) -> set[str]:
    """Os endereços de um nome ou IP (resolvido e guardado por 5 min)."""
    host = str(host or "").strip()
    if not host:
        return set()
    a = _ip(host)
    if a is not None:
        return {str(a)}
    agora = time.monotonic()
    with _lock:
        c = _cache_host.get(host)
        if c is not None and agora - c[0] < validade_s:
            return c[1]
    try:
        _nome, _apelidos, ips = socket.gethostbyname_ex(host)
        out = set(ips)
    except OSError:
        out = set()
    with _lock:
        _cache_host[host] = (agora, out)
    return out


def ip_do_no_confere(nodes: list[dict], ae: str, ip: str) -> bool:
    """O aparelho que diz ser `ae` está no endereço cadastrado para esse AE? Nó com o AE e sem
    endereço não confere (não há o que comparar)."""
    ae = str(ae or "").strip()
    alvo = _ip(ip)
    if alvo is None:
        return False
    if alvo.is_loopback:
        return True                                  # o próprio computador
    for n in nodes:
        if str(n.get("ae_title") or "").strip() != ae:
            continue
        if str(alvo) in ips_do_host(n.get("host", "")):
            return True
    return False


class Tentativas:
    """Senha errada por endereço: `maximo` erros em `janela_s` bloqueiam aquele endereço por
    `bloqueio_s`. Acertar a senha zera a conta."""

    def __init__(self, maximo: int = 5, janela_s: float = 600.0, bloqueio_s: float = 600.0):
        self.maximo, self.janela_s, self.bloqueio_s = maximo, janela_s, bloqueio_s
        self._erros: dict[str, list[float]] = {}
        self._ate: dict[str, float] = {}
        self._lock = threading.Lock()

    def bloqueado(self, ip: str) -> float:
        """Segundos que ainda faltam de bloqueio (0 = liberado)."""
        with self._lock:
            fim = self._ate.get(ip, 0.0)
            falta = fim - time.monotonic()
            if falta <= 0:
                self._ate.pop(ip, None)
                return 0.0
            return falta

    def errou(self, ip: str) -> None:
        agora = time.monotonic()
        with self._lock:
            lista = [t for t in self._erros.get(ip, []) if agora - t < self.janela_s] + [agora]
            self._erros[ip] = lista
            if len(lista) >= self.maximo:
                self._ate[ip] = agora + self.bloqueio_s
                self._erros[ip] = []
                log.warning("servidor central: %s bloqueado por %d s depois de %d senhas erradas",
                            ip, int(self.bloqueio_s), self.maximo)

    def acertou(self, ip: str) -> None:
        with self._lock:
            self._erros.pop(ip, None)
