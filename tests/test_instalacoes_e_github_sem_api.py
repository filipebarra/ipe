"""0.100.54: o GitHub recusando a API (limite de pedidos) e "instalo outra versão e a versão não muda"."""
import io
import urllib.error
from pathlib import Path

import pytest

from ipe.core import atualizar_github as GH
from ipe.core import instalacoes as I


class _Resp(io.BytesIO):
    def __init__(self, corpo: bytes, url: str):
        super().__init__(corpo)
        self.url = url
        self.headers = {}

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


SOMA = "a" * 64


def _github(req, timeout=0):
    url = req.full_url
    if url == GH.API:
        raise urllib.error.HTTPError(url, 403, "rate limit exceeded", {}, None)
    if url == GH.PAGINA:
        return _Resp(b"<html>", "https://github.com/filipebarra/ipe/releases/tag/v9.1.2")
    if url.endswith("/expanded_assets/v9.1.2"):
        return _Resp(b'<a href="/filipebarra/ipe/releases/download/v9.1.2/Ipe-9.1.2-installer.exe">x</a>'
                     b'<a href="/filipebarra/ipe/releases/download/v9.1.2/Ipe-9.1.2-macos-arm64.dmg">y</a>'
                     b'<a href="/filipebarra/ipe/releases/download/v9.1.2/SHA256SUMS.txt">s</a>', url)
    if url.endswith("/v9.1.2/SHA256SUMS.txt"):
        return _Resp(f"{SOMA}  Ipe-9.1.2-installer.exe\n{'b' * 64}  Ipe-9.1.2-macos-arm64.dmg\n".encode(), url)
    raise AssertionError(url)


def test_sem_a_api_pela_pagina():
    info = GH.consultar(abrir=_github)
    assert info["versao"] == "9.1.2" and info["pela_pagina"]
    p = GH.pacote_para(info, "instalado")
    assert p["nome"] == "Ipe-9.1.2-installer.exe" and p["sha256"] == SOMA
    assert p["url"] == "https://github.com/filipebarra/ipe/releases/download/v9.1.2/Ipe-9.1.2-installer.exe"
    assert GH.pacote_para(info, "macos", "arm64")["sha256"] == "b" * 64
    assert all(x["nome"] != "SHA256SUMS.txt" for x in info["pacotes"])


def test_sem_lista_usa_os_nomes_do_release():
    def abrir(req, timeout=0):
        if "expanded_assets" in req.full_url or "SHA256SUMS" in req.full_url:
            raise OSError("fora")
        return _github(req, timeout)
    info = GH.consultar(abrir=abrir)
    assert GH.pacote_para(info, "instalado")["nome"] == "Ipe-9.1.2-installer.exe"
    assert GH.pacote_para(info, "linux")["nome"] == "Ipe-9.1.2-linux-portable.tar.gz"
    assert GH.pacote_para(info, "instalado")["sha256"] == ""


def test_tudo_fora_continua_erro():
    def abrir(req, timeout=0):
        raise OSError("sem rede")
    with pytest.raises(GH.ErroAtualizacao, match="GitHub"):
        GH.consultar(abrir=abrir)


def _registro(pasta: str, versao: str, onde="HKCU"):
    def leitor(raiz, chave):
        assert chave.endswith("{7B3A9C2E-5D41-4C8A-9E17-DC0F2A6B8E41}_is1")
        return {"InstallLocation": pasta, "DisplayVersion": versao} if raiz == onde else None
    return leitor


def test_copia_aberta_nao_e_a_instalada(tmp_path):
    nova = tmp_path / "Programs" / "Ipe"
    nova.mkdir(parents=True)
    (nova / "Ipe.exe").write_bytes(b"")
    velha = tmp_path / "Desktop" / "Ipe" / "Ipe.exe"
    o = I.outra_mais_nova(velha, "0.100.51", _registro(str(nova), "0.100.53"))
    assert o["versao"] == "0.100.53" and Path(o["exe"]) == nova / "Ipe.exe"
    assert I.outra_mais_nova(nova / "Ipe.exe", "0.100.51", _registro(str(nova), "0.100.53")) is None
    assert I.mesma_pasta_desatualizada(nova / "Ipe.exe", "0.100.51", _registro(str(nova), "0.100.53"))
    assert I.outra_mais_nova(velha, "0.100.53", _registro(str(nova), "0.100.53")) is None   # mesma versão
    assert I.outra_mais_nova(velha, "0.100.51", _registro(str(nova), "0.100.53", "HKLM"))   # de todos os usuários
    assert I.registrada(lambda r, c: None) is None


def test_instalador_espera_o_ipe_fechar():
    iss = (Path(__file__).resolve().parents[1] / "installer" / "ipe.iss").read_text(encoding="utf-8-sig")
    assert "CheckForMutexes('IpeViewerAberto')" in iss and I.MUTEX == "IpeViewerAberto"
    for lingua in ("english", "brazilianportuguese", "spanish"):
        assert f"{lingua}.IpeAberto=" in iss
