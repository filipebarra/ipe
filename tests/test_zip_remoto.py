"""Ler um zip grande por faixas de bytes, sem baixar o arquivo inteiro.

Testado contra um servidor HTTP de verdade (o `http.server` da biblioteca padrão, que responde a
`Range`), com um zip de verdade — não contra um dublê. O que se quer provar é que **pouco** é
baixado: por isso os testes contam bytes e pedidos.
"""

import csv
import functools
import http.server
import socketserver
import sys
import threading
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tools"))

import estudo_densidade as E  # noqa: E402
import zip_remoto as Z  # noqa: E402


class _ComFaixa(http.server.SimpleHTTPRequestHandler):
    """Servidor que responde a `Range`, como o S3 — o handler padrão do Python **não** responde:
    ele devolve 200 com o arquivo inteiro, e foi o primeiro teste que denunciou isso."""

    def do_GET(self):  # noqa: N802
        caminho = Path(self.translate_path(self.path))
        faixa = self.headers.get("Range", "")
        if not caminho.is_file() or not faixa.startswith("bytes="):
            return super().do_GET()
        total = caminho.stat().st_size
        ini, _, fim = faixa[len("bytes="):].partition("-")
        i = int(ini or 0)
        f = int(fim) if fim else total - 1
        f = min(f, total - 1)
        with open(caminho, "rb") as fh:
            fh.seek(i)
            dados = fh.read(f - i + 1)
        self.send_response(206)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Content-Range", f"bytes {i}-{f}/{total}")
        self.end_headers()
        self.wfile.write(dados)

    def log_message(self, *a):  # silêncio no relatório do pytest
        pass


@pytest.fixture()
def servidor(tmp_path):
    """Serve `tmp_path` por HTTP **com Range**, como o S3."""
    pasta = tmp_path / "www"
    pasta.mkdir()
    handler = functools.partial(_ComFaixa, directory=str(pasta))
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield pasta, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _zip_grande(pasta, membros=40, tamanho=200_000):
    """Um zip com conteúdo incompressível, para o tamanho do membro ser previsível."""
    import os
    caminho = pasta / "dados.zip"
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_STORED) as z:
        z.writestr("train.csv", "image_id,density\nA,B\n")
        for i in range(membros):
            z.writestr(f"train_images/P{i // 4:03d}/img{i:03d}.dcm", os.urandom(tamanho))
    return caminho


# ------------------------------------------------------------------ o arquivo remoto
def test_descobre_o_tamanho_sem_baixar(servidor):
    pasta, url = servidor
    caminho = _zip_grande(pasta)
    remoto = Z.ArquivoHTTP(f"{url}/dados.zip")
    assert remoto.tamanho == caminho.stat().st_size
    assert remoto.pedidos == 1                       # um pedido de 1 byte, só para ler o total


def test_le_o_indice_com_poucos_pedidos(servidor):
    pasta, url = servidor
    _zip_grande(pasta, membros=40)
    zf, remoto = Z.abrir(f"{url}/dados.zip")
    assert len(zf.namelist()) == 41
    assert remoto.pedidos <= 6                       # índice inteiro em punhado de pedidos


def test_extrai_um_membro_sem_trazer_o_resto(servidor, tmp_path):
    pasta, url = servidor
    tamanho_zip = _zip_grande(pasta, membros=40, tamanho=200_000).stat().st_size
    zf, remoto = Z.abrir(f"{url}/dados.zip")
    destino = tmp_path / "saida"
    feitos, faltando = Z.extrair(zf, ["train.csv"], destino)
    assert feitos == 1 and not faltando
    assert (destino / "train.csv").read_text().startswith("image_id")
    assert remoto.bytes_baixados < tamanho_zip / 4   # bem menos que o arquivo inteiro
    assert remoto.bytes_baixados > 0


def test_seek_e_read_se_comportam_como_arquivo(servidor):
    pasta, url = servidor
    (pasta / "x.bin").write_bytes(bytes(range(256)) * 10)
    r = Z.ArquivoHTTP(f"{url}/x.bin")
    assert r.seekable() and r.readable()
    r.seek(10)
    assert r.tell() == 10 and r.read(4) == bytes([10, 11, 12, 13])
    r.seek(-5, 2)
    assert r.read() == bytes([251, 252, 253, 254, 255])
    r.seek(0)
    assert len(r.read()) == 2560


def test_servidor_que_ignora_faixa_e_denunciado(servidor):
    """Sem `Content-Range` não dá para saber o tamanho — e sem isso o zip não abre."""
    pasta, url = servidor

    class SemFaixa(Z.ArquivoHTTP):
        def _faixa(self, inicio, fim):
            dados, _ = super()._faixa(inicio, fim)
            return dados, ""                          # servidor que devolve tudo e ignora Range

    (pasta / "y.bin").write_bytes(b"0123456789")
    with pytest.raises(OSError, match="faixa de bytes"):
        SemFaixa(f"{url}/y.bin")


# ------------------------------------------------------------------ casar nomes
def test_casa_o_caminho_curto_com_o_de_dentro_do_zip(servidor):
    pasta, url = servidor
    _zip_grande(pasta, membros=8)
    zf, _ = Z.abrir(f"{url}/dados.zip")
    achados, faltando = Z.casar(zf, ["P000/img000.dcm", "P001/img004.dcm", "P999/nada.dcm"])
    assert achados == ["train_images/P000/img000.dcm", "train_images/P001/img004.dcm"]
    assert faltando == ["P999/nada.dcm"]


def test_extrair_nao_baixa_de_novo_o_que_ja_esta_no_disco(servidor, tmp_path):
    pasta, url = servidor
    _zip_grande(pasta, membros=4)
    zf, remoto = Z.abrir(f"{url}/dados.zip")
    destino = tmp_path / "s"
    Z.extrair(zf, ["train.csv"], destino)
    antes = remoto.pedidos
    Z.extrair(zf, ["train.csv"], destino)
    assert remoto.pedidos == antes                    # segunda vez: nenhum pedido novo


# ------------------------------------------------------------------ pelo estudo
def test_planilhas_traz_so_os_csv(servidor, tmp_path, capsys):
    pasta, url = servidor
    _zip_grande(pasta, membros=8)
    saida = tmp_path / "est"
    assert E.main(["planilhas", "--url", f"{url}/dados.zip", "--saida", str(saida)]) == 0
    assert (saida / "train.csv").exists()
    assert not list((saida / "imagens").rglob("*")) if (saida / "imagens").exists() else True
    assert "membros" in capsys.readouterr().out


def test_baixar_traz_so_a_lista_do_escolher(servidor, tmp_path, capsys):
    pasta, url = servidor
    _zip_grande(pasta, membros=12)
    saida = tmp_path / "est"
    saida.mkdir()
    (saida / "arquivos.txt").write_text("P000/img000.dcm\nP000/img001.dcm\n", encoding="utf-8")
    assert E.main(["baixar", "--url", f"{url}/dados.zip", "--saida", str(saida)]) == 0
    baixadas = sorted(p.name for p in (saida / "imagens").rglob("*.dcm"))
    assert baixadas == ["img000.dcm", "img001.dcm"]   # e nenhuma das outras dez
    assert "2 imagens" in capsys.readouterr().out


def test_baixar_sem_lista_manda_rodar_escolher(tmp_path, capsys):
    assert E.main(["baixar", "--url", "http://x/y.zip", "--saida", str(tmp_path)]) == 1
    assert "rode `escolher` antes" in capsys.readouterr().out
