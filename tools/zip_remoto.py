"""Ler um .zip grande **sem baixar o arquivo inteiro**, por faixas de bytes (HTTP Range).

Um zip guarda o índice no fim do arquivo. Quem consegue pedir "só estes bytes" — e o S3 consegue —
pode ler o índice, escolher os membros que interessam e baixar só eles. É a diferença entre 300 GB
e alguns GB.

Não é específico da RSNA: serve para qualquer zip servido por HTTP que aceite `Range`. Nenhum dado
passa por lugar nenhum além da máquina de quem roda.
"""

from __future__ import annotations

import io
import re
import urllib.request
import zipfile

#: pedaço lido de uma vez; o índice do zip costuma caber num pedido só
BLOCO = 1 << 20


class ArquivoHTTP(io.RawIOBase):
    """Um arquivo remoto que se comporta como arquivo local, lendo por faixas de bytes.

    Guarda um bloco em cache: o `zipfile` lê o índice em muitos pedacinhos vizinhos, e sem cache
    cada um viraria um pedido HTTP.
    """

    def __init__(self, url: str, tempo_limite: int = 60) -> None:
        self.url = url
        self.tempo_limite = tempo_limite
        self.pos = 0
        self.pedidos = 0
        self.bytes_baixados = 0
        self._cache = (0, b"")
        self.tamanho = self._tamanho()

    # ---------------------------------------------------------------- rede
    def _faixa(self, inicio: int, fim: int) -> tuple[bytes, str]:
        """Bytes de `inicio` a `fim` (inclusivo) e o cabeçalho Content-Range."""
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={inicio}-{fim}"})
        self.pedidos += 1
        with urllib.request.urlopen(req, timeout=self.tempo_limite) as r:
            dados = r.read()
        self.bytes_baixados += len(dados)
        return dados, r.headers.get("Content-Range", "")

    def _tamanho(self) -> int:
        """Tamanho total, lido do `Content-Range` de um pedido de 1 byte.

        Não se usa HEAD: uma URL assinada do S3 vale para o método que foi assinado (GET), e o
        HEAD volta 403.
        """
        _dados, faixa = self._faixa(0, 0)
        m = re.search(r"/(\d+)\s*$", faixa or "")
        if not m:
            raise OSError("o servidor não respondeu por faixa de bytes (sem Content-Range)")
        return int(m.group(1))

    # ---------------------------------------------------------------- arquivo
    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, pos: int, de_onde: int = 0) -> int:
        base = {0: 0, 1: self.pos, 2: self.tamanho}[de_onde]
        self.pos = max(0, min(self.tamanho, base + pos))
        return self.pos

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = self.tamanho - self.pos
        n = min(n, self.tamanho - self.pos)
        if n <= 0:
            return b""
        ini, dados = self._cache
        if ini <= self.pos and self.pos + n <= ini + len(dados):
            saida = dados[self.pos - ini: self.pos - ini + n]
        else:
            quanto = max(n, BLOCO)
            fim = min(self.tamanho - 1, self.pos + quanto - 1)
            bloco, _ = self._faixa(self.pos, fim)
            self._cache = (self.pos, bloco)
            saida = bloco[:n]
        self.pos += len(saida)
        return saida

    def readinto(self, b) -> int:
        dados = self.read(len(b))
        b[: len(dados)] = dados
        return len(dados)


def abrir(url: str) -> tuple[zipfile.ZipFile, ArquivoHTTP]:
    """Abre o zip remoto. Devolve também o arquivo, para saber tamanho e quantos pedidos foram."""
    remoto = ArquivoHTTP(url)
    return zipfile.ZipFile(remoto), remoto


def extrair(zf: zipfile.ZipFile, nomes, destino, progresso=None) -> tuple[int, list]:
    """Grava os membros escolhidos em `destino`, mantendo a estrutura de pastas.

    Devolve (quantos gravados, lista dos que não existem no zip).
    """
    from pathlib import Path

    destino = Path(destino)
    dentro = set(zf.namelist())
    feitos, faltando = 0, []
    for i, nome in enumerate(nomes):
        if nome not in dentro:
            faltando.append(nome)
            continue
        alvo = destino / nome
        alvo.parent.mkdir(parents=True, exist_ok=True)
        if alvo.exists():                       # já baixado numa tentativa anterior
            feitos += 1
            continue
        with zf.open(nome) as origem, open(alvo, "wb") as saida:
            while True:
                pedaco = origem.read(1 << 20)
                if not pedaco:
                    break
                saida.write(pedaco)
        feitos += 1
        if progresso is not None:
            progresso(i + 1, len(nomes), nome)
    return feitos, faltando


def casar(zf: zipfile.ZipFile, finais) -> tuple[list, list]:
    """Acha no zip os membros que terminam com cada caminho pedido.

    A lista do `escolher` tem `paciente/imagem.dcm`; dentro do zip o caminho costuma ter uma pasta
    a mais na frente (`train_images/...`). Casar pelo fim resolve sem precisar adivinhar o prefixo.
    """
    por_fim = {}
    for nome in zf.namelist():
        por_fim.setdefault(nome.replace("\\", "/"), nome)
    achados, faltando = [], []
    restos = list(por_fim)
    for pedido in finais:
        p = pedido.replace("\\", "/").lstrip("/")
        exato = por_fim.get(p)
        if exato:
            achados.append(exato)
            continue
        cand = [n for n in restos if n.endswith("/" + p)]
        if cand:
            achados.append(cand[0])
        else:
            faltando.append(pedido)
    return achados, faltando
