"""Mover o banco deste computador para outra pasta (0.99.75).

Até a 0.99.74 a mudança era feita com o programa aberto e falhava no Windows ("WinError 32 ... being used by
another process"): o banco continua aberto pelos serviços de fundo (nó DICOM, impressora, automação). Pior: a
falha deixava o programa apontando para a pasta nova com só parte do que tinha ido.

Agora a mudança é marcada nas configurações e feita na **próxima abertura**, antes de o banco ser aberto:

- cada item (o banco, o WAL e o SHM do SQLite, Storage e Lixeira) é renomeado (mesmo disco: instantâneo) ou
  copiado e depois apagado (outro disco);
- se algo falhar, o que já foi é **devolvido** para a pasta de antes e o programa continua na pasta de antes;
- só com tudo movido a pasta nova passa a valer.
"""
from __future__ import annotations

import errno
import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger(__name__)

CHAVE = "banco.mover_ao_abrir"
ITENS = ("postgres", "dicomviewer.sqlite", "dicomviewer.sqlite.migrado", "dicomviewer.sqlite-wal", "dicomviewer.sqlite-shm", "dicomviewer.sqlite-journal",
         "Storage", "Lixeira")


class ErroMover(Exception):
    pass


def itens_de(pasta: Path) -> list[str]:
    return [i for i in ITENS if (Path(pasta) / i).exists()]


def _outro_disco(e: OSError) -> bool:
    return e.errno == errno.EXDEV or getattr(e, "winerror", None) == 17


def _mover_um(origem: Path, destino: Path, andou=None) -> None:
    try:
        os.rename(origem, destino)
        return
    except OSError as e:
        if not _outro_disco(e):
            raise
    if origem.is_dir():
        def copiar(a, b):
            shutil.copy2(a, b)
            if andou:
                andou(Path(a).name)
        shutil.copytree(origem, destino, copy_function=copiar)
        try:
            shutil.rmtree(origem)
        except OSError:
            log.warning("cópia feita, mas sobrou a pasta antiga %s", origem)
    else:
        shutil.copy2(origem, destino)
        if andou:
            andou(origem.name)
        try:
            origem.unlink()
        except OSError:
            log.warning("cópia feita, mas sobrou o arquivo antigo %s", origem)


def mover(de, para, andou=None) -> list[str]:
    """Move os itens do banco de `de` para `para`. Se algo falhar, devolve o que já foi e levanta ErroMover."""
    de, para = Path(de), Path(para)
    itens = itens_de(de)
    if not itens:
        raise ErroMover(f"Não há banco em {de}.")
    conflito = [i for i in itens if (para / i).exists()]
    if conflito:
        raise ErroMover(f"A pasta nova já tem {', '.join(conflito)}; nada foi movido.")
    para.mkdir(parents=True, exist_ok=True)
    feitos: list[str] = []
    try:
        for i in itens:
            _mover_um(de / i, para / i, andou)
            feitos.append(i)
    except Exception as e:  # noqa: BLE001
        log.exception("mover o banco")
        for i in reversed(feitos):
            try:
                _mover_um(para / i, de / i)
            except Exception:  # noqa: BLE001
                log.exception("devolver %s", i)
        raise ErroMover(f"Não foi possível mover o banco ({e}). Nada mudou: o programa continua na pasta de "
                        f"antes.") from e
    return feitos


def marcar(settings, de, para) -> None:
    settings.set(CHAVE, {"de": str(de), "para": str(para)})
    settings.save()


def pendente(settings) -> dict | None:
    p = settings.get(CHAVE)
    return p if isinstance(p, dict) and p.get("de") and p.get("para") else None


def executar_pendente(settings, paths, andou=None) -> tuple[bool, str] | None:
    """Na abertura, antes de abrir o banco. None = nada pendente; (ok, mensagem) depois de tentar."""
    p = pendente(settings)
    if p is None:
        return None
    settings.set(CHAVE, None)
    settings.save()
    de, para = Path(p["de"]), Path(p["para"])
    try:
        if de.resolve() != Path(paths.data).resolve():
            return False, "A mudança da pasta do banco foi cancelada: o banco já não está na pasta marcada."
    except OSError:
        pass
    try:
        from ipe.core import pg_embutido as PE           # o PostgreSQL da pasta parado antes de mover os dados dele
        PE.desligar_todos()
    except Exception:  # noqa: BLE001
        log.debug("desligar o PostgreSQL", exc_info=True)
    try:
        mover(de, para, andou)
    except ErroMover as e:
        return False, str(e)
    from ipe.core.config import default_data_dir, publicar_pasta_do_banco, AppPaths
    try:
        padrao = Path(default_data_dir()).resolve()
    except OSError:
        padrao = Path(default_data_dir())
    settings.set("data_dir", "" if para.resolve() == padrao else str(para))
    settings.save()
    publicar_pasta_do_banco(AppPaths(para, paths.config, paths.logs))
    return True, f"O banco foi movido para {para}."
