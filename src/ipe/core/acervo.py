"""Relatório do acervo: o que está guardado, em que formato, e quanto cada compressão renderia.

Duas partes, de propósito separadas:

* **O levantamento** sai de uma agregação no banco — não abre arquivo nenhum, então responde
  na hora mesmo com centenas de milhares de instâncias.
* **A medição** abre uma amostra pequena de arquivos reais e comprime **em memória**, para dizer
  a taxa *deste* acervo em vez de repetir a taxa média da literatura. Nenhum arquivo é alterado,
  nada é gravado: o original nunca é tocado.

O programa devolve os números; a decisão sobre comprimir, e com que taxa, é do médico
(no Brasil a CFM 2.107/2014 delega essa avaliação ao radiologista com CRM).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

log = logging.getLogger(__name__)

SEM = "sem"            # sem compressão
LOSSLESS = "lossless"  # comprimido sem perda
LOSSY = "lossy"        # comprimido com perda
DESCONHECIDA = "?"


@dataclass(frozen=True)
class Sintaxe:
    uid: str
    nome: str
    tipo: str
    escreve: bool = False      # o pydicom 3.x sabe gravar nesta sintaxe?


def _s(uid: str, nome: str, tipo: str, escreve: bool = False) -> tuple[str, Sintaxe]:
    return uid, Sintaxe(uid, nome, tipo, escreve)


SINTAXES: dict[str, Sintaxe] = dict([
    _s("1.2.840.10008.1.2", "Implícita, sem compressão", SEM),
    _s("1.2.840.10008.1.2.1", "Explícita, sem compressão", SEM),
    _s("1.2.840.10008.1.2.2", "Explícita big-endian, sem compressão", SEM),
    _s("1.2.840.10008.1.2.1.99", "Deflated (zip do arquivo inteiro)", LOSSLESS),
    _s("1.2.840.10008.1.2.5", "RLE sem perda", LOSSLESS, True),
    _s("1.2.840.10008.1.2.4.50", "JPEG com perda, 8 bits (.50)", LOSSY),
    _s("1.2.840.10008.1.2.4.51", "JPEG com perda, 12 bits (.51)", LOSSY),
    _s("1.2.840.10008.1.2.4.57", "JPEG sem perda (.57)", LOSSLESS),
    _s("1.2.840.10008.1.2.4.70", "JPEG sem perda (.70)", LOSSLESS),
    _s("1.2.840.10008.1.2.4.80", "JPEG-LS sem perda (.80)", LOSSLESS, True),
    _s("1.2.840.10008.1.2.4.81", "JPEG-LS quase sem perda (.81)", LOSSY, True),
    _s("1.2.840.10008.1.2.4.90", "JPEG 2000 sem perda (.90)", LOSSLESS, True),
    _s("1.2.840.10008.1.2.4.91", "JPEG 2000 com perda (.91)", LOSSY, True),
    _s("1.2.840.10008.1.2.4.92", "JPEG 2000 parte 2, sem perda", LOSSLESS),
    _s("1.2.840.10008.1.2.4.93", "JPEG 2000 parte 2, com perda", LOSSY),
    _s("1.2.840.10008.1.2.4.100", "MPEG2", LOSSY),
    _s("1.2.840.10008.1.2.4.101", "MPEG2 alta definição", LOSSY),
    _s("1.2.840.10008.1.2.4.102", "MPEG-4 AVC/H.264", LOSSY),
    _s("1.2.840.10008.1.2.4.103", "MPEG-4 AVC/H.264 estéreo", LOSSY),
    _s("1.2.840.10008.1.2.4.201", "HTJ2K sem perda", LOSSLESS),
    _s("1.2.840.10008.1.2.4.202", "HTJ2K sem perda RPCL", LOSSLESS),
    _s("1.2.840.10008.1.2.4.203", "HTJ2K", LOSSY),
])

#: as que fazem sentido medir, em ordem de compatibilidade com PACS antigo
CANDIDATAS = ("1.2.840.10008.1.2.5", "1.2.840.10008.1.2.4.80", "1.2.840.10008.1.2.4.90")

#: pacote que falta quando o codificador não está instalado
PACOTE = {"1.2.840.10008.1.2.5": "", "1.2.840.10008.1.2.4.80": "pyjpegls",
          "1.2.840.10008.1.2.4.90": "pylibjpeg-openjpeg"}


def sintaxe(uid: str) -> Sintaxe:
    """Nunca devolve None: sintaxe desconhecida volta com o próprio UID como nome."""
    return SINTAXES.get(uid or "", Sintaxe(uid or "", uid or "—", DESCONHECIDA, False))


# --------------------------------------------------------------------- levantamento
@dataclass
class Linha:
    modalidade: str
    sintaxe_uid: str
    arquivos: int
    bytes: int
    pixels: int

    @property
    def nome(self) -> str:
        return sintaxe(self.sintaxe_uid).nome

    @property
    def tipo(self) -> str:
        return sintaxe(self.sintaxe_uid).tipo

    @property
    def bytes_por_pixel(self) -> float:
        return (self.bytes / self.pixels) if self.pixels else 0.0


@dataclass
class Acervo:
    linhas: list[Linha] = field(default_factory=list)

    @property
    def arquivos(self) -> int:
        return sum(l.arquivos for l in self.linhas)

    @property
    def bytes(self) -> int:
        return sum(l.bytes for l in self.linhas)

    def _somar(self, chave) -> list[tuple[str, int, int, int]]:
        acc: dict[str, list[int]] = {}
        for l in self.linhas:
            a = acc.setdefault(chave(l), [0, 0, 0])
            a[0] += l.arquivos
            a[1] += l.bytes
            a[2] += l.pixels
        return sorted(((k, v[0], v[1], v[2]) for k, v in acc.items()), key=lambda r: -r[2])

    def por_sintaxe(self):
        return self._somar(lambda l: l.sintaxe_uid)

    def por_modalidade(self):
        return self._somar(lambda l: l.modalidade or "—")

    def por_tipo(self):
        return self._somar(lambda l: l.tipo)

    def bytes_do_tipo(self, tipo: str) -> int:
        return sum(l.bytes for l in self.linhas if l.tipo == tipo)

    def sem_compressao(self) -> list[Linha]:
        return [l for l in self.linhas if l.tipo == SEM]


def levantar(repo) -> Acervo:
    """Lê a agregação do banco. Barato: uma consulta, nenhum arquivo aberto."""
    return Acervo([Linha(r["modality"], r["syntax"], r["files"], r["bytes"], r["pixels"])
                   for r in repo.storage_rows()])


# --------------------------------------------------------------------- medição
@dataclass
class Medida:
    uid: str
    arquivos: int = 0
    bytes_origem: int = 0
    bytes_saida: int = 0
    erros: int = 0
    disponivel: bool = True
    falta: str = ""

    @property
    def nome(self) -> str:
        return sintaxe(self.uid).nome

    @property
    def razao(self) -> float:
        return (self.bytes_origem / self.bytes_saida) if self.bytes_saida else 0.0


def codificadores() -> dict[str, tuple[bool, str]]:
    """Quais sintaxes esta instalação consegue **gravar**, e o que falta para as outras."""
    try:
        from pydicom.pixels import encoders as E
    except Exception:  # noqa: BLE001
        return {u: (False, PACOTE.get(u, "")) for u in CANDIDATAS}
    mapa = {"1.2.840.10008.1.2.5": "RLELosslessEncoder",
            "1.2.840.10008.1.2.4.80": "JPEGLSLosslessEncoder",
            "1.2.840.10008.1.2.4.90": "JPEG2000LosslessEncoder"}
    out: dict[str, tuple[bool, str]] = {}
    for uid, nome in mapa.items():
        enc = getattr(E, nome, None)
        ok = bool(enc is not None and getattr(enc, "is_available", False))
        out[uid] = (ok, "" if ok else PACOTE.get(uid, ""))
    return out


def _bytes_de(ds) -> int:
    buf = BytesIO()
    ds.save_as(buf, enforce_file_format=True)
    return buf.getbuffer().nbytes


def medir(caminhos, uids=CANDIDATAS, stop=None, progresso=None) -> list[Medida]:
    """Comprime uma amostra **em memória** e devolve quanto cada sintaxe rendeu.

    Só mede arquivo que ainda está sem compressão — recomprimir o que já está comprimido
    mediria o trabalho errado. Nenhum arquivo é gravado nem alterado.
    """
    import pydicom

    disp = codificadores()
    medidas = {u: Medida(u, disponivel=disp.get(u, (False, ""))[0],
                         falta=disp.get(u, (False, ""))[1]) for u in uids}
    caminhos = list(caminhos)
    for i, caminho in enumerate(caminhos):
        if stop is not None and stop.is_set():
            break
        if progresso is not None:
            progresso(i, len(caminhos))
        try:
            ds = pydicom.dcmread(str(caminho))
            if sintaxe(str(ds.file_meta.TransferSyntaxUID)).tipo != SEM:
                continue
            base = _bytes_de(ds)
        except Exception:  # noqa: BLE001
            log.debug("Amostra ilegível: %s", caminho, exc_info=True)
            continue
        for uid in uids:
            m = medidas[uid]
            if not m.disponivel:
                continue
            try:
                copia = pydicom.dcmread(str(caminho))
                copia.compress(uid)
                m.bytes_saida += _bytes_de(copia)
                m.bytes_origem += base
                m.arquivos += 1
            except Exception:  # noqa: BLE001
                m.erros += 1
                log.debug("Falha comprimindo %s em %s", caminho, uid, exc_info=True)
    if progresso is not None:
        progresso(len(caminhos), len(caminhos))
    return [medidas[u] for u in uids]


def projetar(acervo: Acervo, medidas: list[Medida]) -> list[tuple[Medida, int, int]]:
    """(medida, bytes hoje, bytes depois) aplicando a razão medida **só ao que está sem
    compressão** — o que já está comprimido fica como está."""
    hoje = acervo.bytes_do_tipo(SEM)
    out = []
    for m in medidas:
        if m.razao <= 0:
            out.append((m, hoje, hoje))
        else:
            out.append((m, hoje, int(round(hoje / m.razao))))
    return out


def tamanho(n: float) -> str:
    """Bytes em unidade legível, com uma casa."""
    for unidade, passo in (("TB", 1 << 40), ("GB", 1 << 30), ("MB", 1 << 20), ("kB", 1 << 10)):
        if abs(n) >= passo:
            return f"{n / passo:.1f} {unidade}"
    return f"{int(n)} bytes"


def amostra(repo, por_grupo: int = 3, maximo: int = 60) -> list[str]:
    """Arquivos sem compressão, espalhados por modalidade, para medir em cima do acervo real."""
    acv = levantar(repo)
    alvos = sorted(acv.sem_compressao(), key=lambda l: -l.bytes)
    caminhos: list[str] = []
    for l in alvos:
        if len(caminhos) >= maximo:
            break
        for p in repo.storage_samples(l.modalidade, l.sintaxe_uid, por_grupo):
            if p and Path(p).exists():
                caminhos.append(p)
    return caminhos[:maximo]
