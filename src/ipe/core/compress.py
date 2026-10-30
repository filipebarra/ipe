"""Compressão sem perda do que já está guardado — com conferência antes de trocar.

Esta é a função mais perigosa do programa: ela **reescreve arquivo de paciente**. Por isso o
caminho é sempre o mesmo, e não tem atalho:

1. só entra arquivo **sem compressão**, de exame guardado há mais dias que o prazo;
2. comprime numa cópia, em arquivo temporário **na mesma pasta** (a troca precisa ser no mesmo
   sistema de arquivos para ser atômica);
3. **lê o temporário de volta do disco** e compara **pixel a pixel** com o original, além dos
   identificadores — se não for idêntico, apaga o temporário e não troca nada;
4. só então `os.replace`, que é atômico: ou está o antigo, ou está o novo, nunca meio arquivo;
5. atualiza o banco (sintaxe e tamanho).

Sem perda é sem perda: os pixels voltam idênticos e o SOP Instance UID continua o mesmo — pelo
padrão, trocar só a sintaxe de transferência não cria objeto novo. Compressão **com perda** seria
outra coisa (objeto novo, ImageType DERIVED) e não é feita aqui.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

JPEGLS = "1.2.840.10008.1.2.4.80"
J2K = "1.2.840.10008.1.2.4.90"
RLE = "1.2.840.10008.1.2.5"

#: as que este programa aceita usar para guardar — todas sem perda
SINTAXES = (JPEGLS, J2K, RLE)

PADROES = {
    "compress.enabled": False,      # desligada até o usuário ligar
    "compress.days": 5,             # dias desde a entrada no sistema
    "compress.syntax": JPEGLS,
    "compress.skip_locked": True,   # exame protegido não é mexido
    "compress.min_bytes": 64 * 1024,
    "compress.max_per_run": 400,    # por passagem automática, para não ocupar o disco o dia todo
}


@dataclass
class Politica:
    ligada: bool = False
    dias: int = 5
    sintaxe: str = JPEGLS
    pular_protegidos: bool = True
    minimo_bytes: int = 64 * 1024
    por_rodada: int = 400

    @staticmethod
    def from_settings(settings) -> Politica:
        g = settings.get
        sint = str(g("compress.syntax", JPEGLS))
        return Politica(
            ligada=bool(g("compress.enabled", False)),
            dias=max(0, int(g("compress.days", 5) or 0)),
            sintaxe=sint if sint in SINTAXES else JPEGLS,
            pular_protegidos=bool(g("compress.skip_locked", True)),
            minimo_bytes=max(0, int(g("compress.min_bytes", 64 * 1024) or 0)),
            por_rodada=max(1, int(g("compress.max_per_run", 400) or 1)))

    def save(self, settings) -> None:
        settings.set("compress.enabled", self.ligada)
        settings.set("compress.days", int(self.dias))
        settings.set("compress.syntax", self.sintaxe)
        settings.set("compress.skip_locked", self.pular_protegidos)
        settings.set("compress.min_bytes", int(self.minimo_bytes))
        settings.set("compress.max_per_run", int(self.por_rodada))
        settings.save()

    def limite(self, agora: datetime | None = None) -> datetime:
        """Só entra exame guardado **antes** deste instante."""
        return (agora or datetime.now()) - timedelta(days=self.dias)


# ------------------------------------------------------------------ um arquivo
PULOU_COMPRIMIDO = "ja_comprimido"
PULOU_SEM_PIXEL = "sem_pixel"
PULOU_PEQUENO = "pequeno"
PULOU_SUMIU = "sumiu"
FALHOU_COMPRIMIR = "nao_comprimiu"
FALHOU_CONFERIR = "nao_conferiu"
FEITO = "feito"


@dataclass
class Resultado:
    estado: str
    antes: int = 0
    depois: int = 0
    detalhe: str = ""

    @property
    def ok(self) -> bool:
        return self.estado == FEITO

    @property
    def economia(self) -> int:
        return max(0, self.antes - self.depois) if self.ok else 0


def _sem_compressao(uid: str) -> bool:
    from ipe.core import acervo as A
    return A.sintaxe(str(uid or "")).tipo == A.SEM


def compress_file(caminho: str | Path, sintaxe: str = JPEGLS,
                  minimo_bytes: int = 0) -> Resultado:
    """Comprime **um** arquivo no lugar, conferindo antes de trocar. Nunca levanta exceção."""
    import numpy as np
    import pydicom

    caminho = Path(caminho)
    try:
        antes = caminho.stat().st_size
    except OSError:
        return Resultado(PULOU_SUMIU)
    if minimo_bytes and antes < minimo_bytes:
        return Resultado(PULOU_PEQUENO, antes, antes)
    try:
        ds = pydicom.dcmread(str(caminho))
    except Exception as e:  # noqa: BLE001
        return Resultado(PULOU_SUMIU, antes, antes, str(e))
    if not _sem_compressao(getattr(ds.file_meta, "TransferSyntaxUID", "")):
        return Resultado(PULOU_COMPRIMIDO, antes, antes)
    if "PixelData" not in ds:
        return Resultado(PULOU_SEM_PIXEL, antes, antes)
    try:
        # .copy() não é enfeite: `pixel_array` é uma vista do buffer do dataset, e `compress()`
        # troca esse buffer — sem a cópia, a conferência compararia o novo consigo mesmo.
        original = np.asarray(ds.pixel_array).copy()
        sop = str(ds.SOPInstanceUID)
    except Exception as e:  # noqa: BLE001
        return Resultado(PULOU_SEM_PIXEL, antes, antes, str(e))

    temp = caminho.with_name(caminho.name + ".comprimindo")
    try:
        ds.compress(sintaxe)
        # O `compress()` do pydicom **gera um SOP Instance UID novo**, mesmo sem perda. Aqui isso
        # seria um desastre silencioso: o banco indexa por SOP, e imagem-chave, lesão, laudo e
        # segmentação apontam para ele — todos ficariam órfãos. Sem perda os pixels são os mesmos,
        # então pelo padrão o objeto continua sendo o mesmo objeto. Devolvemos o UID original.
        ds.SOPInstanceUID = sop
        ds.file_meta.MediaStorageSOPInstanceUID = sop
        with open(temp, "wb") as f:
            ds.save_as(f, enforce_file_format=True)
            f.flush()
            os.fsync(f.fileno())
    except Exception as e:  # noqa: BLE001 - imagem que este codificador não aceita
        temp.unlink(missing_ok=True)
        return Resultado(FALHOU_COMPRIMIR, antes, antes, str(e))

    # confere lendo do disco, não da memória: o que vale é o arquivo que vai ficar no lugar
    try:
        volta = pydicom.dcmread(str(temp))
        igual = (str(volta.SOPInstanceUID) == sop
                 and str(volta.file_meta.TransferSyntaxUID) == sintaxe
                 and np.array_equal(np.asarray(volta.pixel_array), original))
    except Exception as e:  # noqa: BLE001
        temp.unlink(missing_ok=True)
        return Resultado(FALHOU_CONFERIR, antes, antes, str(e))
    if not igual:
        temp.unlink(missing_ok=True)
        return Resultado(FALHOU_CONFERIR, antes, antes, "os pixels não voltaram idênticos")

    depois = temp.stat().st_size
    if depois >= antes:                       # comprimir e crescer acontece em imagem com ruído
        temp.unlink(missing_ok=True)
        return Resultado(PULOU_PEQUENO, antes, antes, "o comprimido ficou maior que o original")
    try:
        os.replace(temp, caminho)             # atômico: ou o antigo, ou o novo
    except OSError as e:
        temp.unlink(missing_ok=True)
        return Resultado(FALHOU_CONFERIR, antes, antes, str(e))
    return Resultado(FEITO, antes, depois)


# ------------------------------------------------------------------ o lote
@dataclass
class Balanco:
    arquivos: int = 0
    feitos: int = 0
    antes: int = 0
    depois: int = 0
    pulados: dict = field(default_factory=dict)
    falhas: list = field(default_factory=list)

    @property
    def economia(self) -> int:
        return max(0, self.antes - self.depois)

    def conta(self, r: Resultado, caminho: str = "") -> None:
        self.arquivos += 1
        if r.ok:
            self.feitos += 1
            self.antes += r.antes
            self.depois += r.depois
            return
        self.pulados[r.estado] = self.pulados.get(r.estado, 0) + 1
        if r.estado in (FALHOU_COMPRIMIR, FALHOU_CONFERIR) and len(self.falhas) < 20:
            self.falhas.append((caminho, r.detalhe))


def elegiveis(repo, politica: Politica, limite: int = 0, agora=None) -> list[dict]:
    """O que o prazo já liberou: sem compressão, guardado, e do tamanho que vale a pena."""
    return repo.instances_to_compress(
        antes_de=politica.limite(agora), minimo_bytes=politica.minimo_bytes,
        pular_protegidos=politica.pular_protegidos,
        limite=limite or politica.por_rodada)


def run(repo, politica: Politica, limite: int = 0, stop=None, progresso=None,
        pular_exames=()) -> Balanco:
    """Passa o lote. Para na hora em que `stop` for marcado — o que já trocou está trocado e
    conferido, então parar no meio nunca deixa arquivo pela metade."""
    fora = set(pular_exames or ())
    alvos = [a for a in elegiveis(repo, politica, limite) if a.get("study_uid") not in fora]
    b = Balanco()
    for i, alvo in enumerate(alvos):
        if stop is not None and stop.is_set():
            break
        if progresso is not None:
            progresso(i, len(alvos))
        r = compress_file(alvo["path"], politica.sintaxe, politica.minimo_bytes)
        b.conta(r, alvo["path"])
        if r.ok:
            try:
                repo.set_instance_storage(alvo["sop_uid"], politica.sintaxe, r.depois)
            except Exception:  # noqa: BLE001 - o arquivo já trocou; o banco se acerta no próximo
                log.exception("Banco não aceitou a nova sintaxe de %s", alvo["sop_uid"])
    if progresso is not None:
        progresso(len(alvos), len(alvos))
    return b


def resumo(b: Balanco) -> str:
    """Uma frase para a barra de estado."""
    from ipe.core.acervo import tamanho
    if not b.arquivos:
        return "Nada a comprimir: nenhum exame passou do prazo."
    if not b.feitos:
        return f"{b.arquivos} arquivo(s) olhados, nenhum comprimido."
    return f"{b.feitos} de {b.arquivos} arquivo(s) comprimidos, {tamanho(b.economia)} liberados."
