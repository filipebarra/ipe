"""Certificados para usar o Ipê com HTTPS na rede interna (0.99.74).

Sem certificado, o servidor central fala HTTP e a senha de cada login passa aberta na rede. Um certificado
"de verdade" (de uma autoridade pública) não serve para um endereço como 192.168.1.10. Por isso, aqui o próprio
Ipê vira uma **autoridade certificadora (AC) interna**:

1. no servidor, **Gerar certificado** cria uma vez a AC do serviço (``ac.crt`` + ``ac.key``) e, com ela, o
   certificado do servidor, válido para o nome do computador e os IPs dele (``servidor.crt`` + ``servidor.key``),
   na pasta ``certificados`` das configurações;
2. em cada cliente, **Confiar neste servidor** baixa a AC do servidor (``/api/ac``), mostra a impressão digital
   para conferir e passa a exigir HTTPS conferido com ela: um impostor na rede não consegue se passar pelo
   servidor;
3. para navegadores e outros visualizadores DICOMweb, a AC (``ac.crt``) pode ser instalada no Windows (duplo
   clique ▸ Instalar certificado ▸ Autoridades de Certificação Raiz Confiáveis).

A chave da AC não sai do servidor. O certificado do servidor vale 825 dias (o máximo que os navegadores aceitam);
gerar de novo troca só ele, e os clientes continuam confiando (a AC é a mesma, 10 anos). Usa o pacote
``cryptography``.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import ipaddress
import os
import socket
from pathlib import Path

DIAS_SERVIDOR = 825
ANOS_AC = 10
NOME_AC = "Ipê — AC interna"


class ErroCertificado(Exception):
    pass


def _crypto():
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    except ImportError as e:
        raise ErroCertificado("Falta o pacote \"cryptography\" (pip install cryptography).") from e
    return x509, hashes, serialization, ec, ExtendedKeyUsageOID, NameOID


def pasta(paths) -> Path:
    return Path(paths.config) / "certificados"


def nomes_e_ips() -> tuple[list[str], list[str]]:
    """Os nomes e IPs deste computador, para o certificado valer por qualquer um deles."""
    nomes = []
    for n in (socket.gethostname(), socket.getfqdn(), "localhost"):
        if n and n not in nomes:
            nomes.append(n)
    ips = ["127.0.0.1"]
    try:
        from ipe.ui.network_dialog import local_ips
        for ip in local_ips():
            if ip not in ips:
                ips.append(ip)
    except Exception:  # noqa: BLE001
        pass
    return nomes, ips


def impressao(pem: bytes | str) -> str:
    """SHA-256 do certificado (DER), em grupos, para conferir de olho entre dois computadores."""
    x509 = _crypto()[0]
    from cryptography.hazmat.primitives import serialization
    if isinstance(pem, str):
        pem = pem.encode("ascii")
    der = x509.load_pem_x509_certificate(pem).public_bytes(serialization.Encoding.DER)
    h = hashlib.sha256(der).hexdigest().upper()
    return ":".join(h[i:i + 2] for i in range(0, len(h), 2))


def _gravar_chave(caminho: Path, chave, serialization) -> None:
    caminho.write_bytes(chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                            serialization.NoEncryption()))
    try:
        os.chmod(caminho, 0o600)
    except OSError:
        pass


def _ac(dirx: Path):
    """A AC do serviço: lê, ou cria na primeira vez."""
    x509, hashes, serialization, ec, _eku, NameOID = _crypto()
    crt, key = dirx / "ac.crt", dirx / "ac.key"
    if crt.exists() and key.exists():
        return (x509.load_pem_x509_certificate(crt.read_bytes()),
                serialization.load_pem_private_key(key.read_bytes(), None))
    chave = ec.generate_private_key(ec.SECP256R1())
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"{NOME_AC} ({socket.gethostname()})"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Ipê")])
    agora = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(chave.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(agora - dt.timedelta(minutes=5))
            .not_valid_after(agora + dt.timedelta(days=365 * ANOS_AC))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                         content_commitment=False, key_encipherment=False, data_encipherment=False,
                                         key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(chave.public_key()), critical=False)
            .sign(chave, hashes.SHA256()))
    dirx.mkdir(parents=True, exist_ok=True)
    _gravar_chave(key, chave, serialization)
    crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert, chave


def gerar(dirx, nomes: list[str] | None = None, ips: list[str] | None = None) -> dict:
    """Certificado do servidor assinado pela AC (criada se faltar). Devolve os caminhos e as impressões."""
    x509, hashes, serialization, ec, EKU, NameOID = _crypto()
    dirx = Path(dirx)
    if nomes is None or ips is None:
        n0, i0 = nomes_e_ips()
        nomes = n0 if nomes is None else nomes
        ips = i0 if ips is None else ips
    sans = [x509.DNSName(n) for n in nomes if n]
    for ip in ips:
        try:
            sans.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            continue
    if not sans:
        raise ErroCertificado("Sem nome nem IP para o certificado.")
    ac, chave_ac = _ac(dirx)
    chave = ec.generate_private_key(ec.SECP256R1())
    cn = (nomes or [str(ips[0])])[0]
    agora = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn[:64]),
                                     x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Ipê")]))
            .issuer_name(ac.subject).public_key(chave.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(agora - dt.timedelta(minutes=5))
            .not_valid_after(agora + dt.timedelta(days=DIAS_SERVIDOR))
            .add_extension(x509.SubjectAlternativeName(sans), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=False, key_cert_sign=False,
                                         crl_sign=False, content_commitment=False, data_encipherment=False,
                                         key_agreement=True, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([EKU.SERVER_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(chave_ac.public_key()), critical=False)
            .sign(chave_ac, hashes.SHA256()))
    crt, key = dirx / "servidor.crt", dirx / "servidor.key"
    _gravar_chave(key, chave, serialization)
    ac_pem = ac.public_bytes(serialization.Encoding.PEM)
    crt.write_bytes(cert.public_bytes(serialization.Encoding.PEM) + ac_pem)      # a cadeia: servidor + AC
    return {"certfile": str(crt), "keyfile": str(key), "ac": str(dirx / "ac.crt"), "ac_pem": ac_pem.decode(),
            "impressao_ac": impressao(ac_pem), "nomes": list(nomes), "ips": list(ips),
            "validade": (agora + dt.timedelta(days=DIAS_SERVIDOR)).date().isoformat()}


def ac_ao_lado(certfile: str) -> bytes | None:
    """A AC que fica junto do certificado do servidor (o que /api/ac serve)."""
    if not certfile:
        return None
    p = Path(certfile).with_name("ac.crt")
    try:
        return p.read_bytes() if p.is_file() else None
    except OSError:
        return None


def info(certfile: str) -> dict | None:
    """Nomes, IPs e validade do certificado do servidor (para a tela)."""
    try:
        x509 = _crypto()[0]
        cert = x509.load_pem_x509_certificate(Path(certfile).read_bytes())
    except Exception:  # noqa: BLE001
        return None
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        nomes = san.get_values_for_type(x509.DNSName)
        ips = [str(i) for i in san.get_values_for_type(x509.IPAddress)]
    except x509.ExtensionNotFound:
        nomes, ips = [], []
    fim = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
    return {"nomes": nomes, "ips": ips, "validade": fim.date().isoformat()}
