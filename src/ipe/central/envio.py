"""Cópia de envio para o visualizador web (0.99.96): o quadro vai comprimido SEM PERDA, pronto para a rede.

O arquivo guardado não muda (a regra do programa: guardar como veio). Para o site, cada quadro sem compressão
(ou em JPEG-LS) vira HTJ2K sem perda com ordem RPCL (1.2.840.10008.1.2.4.202) — 2 a 4 vezes menos bytes na rede,
decodificação rápida no navegador e carga progressiva (o navegador mostra uma versão menor enquanto o resto chega).
Sem o imagecodecs (HTJ2K), vai em JPEG-LS sem perda pelo pyjpegls. Cada cópia é conferida pixel a pixel antes de
ser usada; se não bater, vai o original. As cópias ficam numa pasta de cache, descartável, ao lado do acervo.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

HTJ2K_RPCL = "1.2.840.10008.1.2.4.202"
JPEG_LS = "1.2.840.10008.1.2.4.80"
NATIVAS = {"1.2.840.10008.1.2", "1.2.840.10008.1.2.1"}
#: sintaxes que valem a pena passar para HTJ2K: sem compressão e JPEG-LS sem perda (a mamografia do acervo)
CONVERTE = NATIVAS | {JPEG_LS}
VERSAO = "1"            # muda se o jeito de codificar mudar (as cópias velhas deixam de valer)

_pasta: Path | None = None
_lock = threading.Lock()
_ocupadas: set[str] = set()


def configurar(storage_root: Path | str) -> None:
    global _pasta
    _pasta = Path(storage_root).parent / "CacheWeb"


def pasta() -> Path | None:
    return _pasta


def codec() -> str:
    """'htj2k', 'jpegls' ou '' (sem codificador: vai o original)."""
    try:
        import imagecodecs
        if imagecodecs.HTJ2K.available:
            return "htj2k"
    except Exception:  # noqa: BLE001
        pass
    try:
        import jpeg_ls  # noqa: F401
        return "jpegls"
    except Exception:  # noqa: BLE001
        return ""


def _chave(caminho: str, n: int | str) -> str:
    st = os.stat(caminho)
    h = hashlib.sha1(f"{VERSAO}|{caminho}|{st.st_mtime_ns}|{st.st_size}".encode()).hexdigest()
    return f"{h}_{n}"


def etag(caminho: str, quadros: str = "1") -> str:
    """Identidade do conteúdo (arquivo + quadro + jeito de codificar): o navegador revalida e recebe 304."""
    try:
        return f'"{_chave(caminho, 0)}-{quadros.replace(",", ".")}-{codec()}"'
    except OSError:
        return ""


def _monocromatico(ds) -> bool:
    return int(getattr(ds, "SamplesPerPixel", 1) or 1) == 1 and int(getattr(ds, "BitsAllocated", 16)) in (8, 16)


def _array_nativo(ds, dados: bytes) -> np.ndarray:
    bits = int(ds.BitsAllocated)
    sinal = int(getattr(ds, "PixelRepresentation", 0) or 0) == 1
    dt = {(8, False): np.uint8, (8, True): np.int8, (16, False): np.uint16, (16, True): np.int16}[(bits, sinal)]
    return np.frombuffer(dados, dtype=np.dtype(dt).newbyteorder("<")).reshape(int(ds.Rows), int(ds.Columns)).astype(dt)


def _array_jpegls(ds, dados: bytes) -> np.ndarray:
    import jpeg_ls
    a = np.asarray(jpeg_ls.decode(np.frombuffer(dados, np.uint8)))
    if int(getattr(ds, "PixelRepresentation", 0) or 0) == 1 and a.dtype == np.uint16:
        a = a.view(np.int16)
    return a


def codificar(arr: np.ndarray, qual: str) -> tuple[bytes, str] | None:
    """Comprime sem perda e confere a volta. None se o codificador não serve ou a volta não bate."""
    try:
        if qual == "htj2k":
            import imagecodecs
            b = bytes(imagecodecs.htj2k_encode(arr, reversible=True, prog_order="RPCL", tlm=True))
            ok = np.array_equal(np.asarray(imagecodecs.htj2k_decode(b)).reshape(arr.shape).astype(arr.dtype), arr)
            return (b, HTJ2K_RPCL) if ok else None
        if qual == "jpegls":
            import jpeg_ls
            src = arr.view(np.uint16) if arr.dtype == np.int16 else arr
            b = bytes(jpeg_ls.encode(np.ascontiguousarray(src)))
            volta = np.asarray(jpeg_ls.decode(np.frombuffer(b, np.uint8)))
            return (b, JPEG_LS) if np.array_equal(volta.reshape(src.shape), src) else None
    except Exception:  # noqa: BLE001
        log.exception("cópia de envio (%s)", qual)
    return None


def quadro(ds, caminho: str, n: int, original: bytes, ts: str) -> tuple[bytes, str]:
    """O quadro n (1 = o primeiro) para a rede: a cópia comprimida (do cache ou feita agora) ou o original."""
    qual = codec()
    if not qual or _pasta is None or ts not in CONVERTE or not _monocromatico(ds):
        return original, ts
    if ts == JPEG_LS and qual != "htj2k":
        return original, ts                                  # JPEG-LS → JPEG-LS: nada a ganhar
    try:
        chave = _chave(caminho, n)
    except OSError:
        return original, ts
    ext = ".jph" if qual == "htj2k" else ".jls"
    alvo = _pasta / chave[:2] / (chave + ext)
    falha = alvo.with_suffix(".nao")
    if alvo.exists():
        try:
            return alvo.read_bytes(), (HTJ2K_RPCL if qual == "htj2k" else JPEG_LS)
        except OSError:
            pass
    if falha.exists():
        return original, ts
    try:
        arr = _array_jpegls(ds, original) if ts == JPEG_LS else _array_nativo(ds, original)
    except Exception:  # noqa: BLE001
        return original, ts
    r = codificar(arr, qual)
    try:
        alvo.parent.mkdir(parents=True, exist_ok=True)
        if r is None:
            falha.write_bytes(b"")
            return original, ts
        tmp = alvo.with_suffix(f".{threading.get_ident()}.tmp")
        tmp.write_bytes(r[0])
        os.replace(tmp, alvo)
    except OSError:
        log.exception("cache de envio")
    return r if r else (original, ts)


# 0.99.99: as cópias da série inteira são feitas por UM trabalhador, em fila, e só quando nenhum quadro está
# sendo pedido — antes, cada série aberta ganhava uma thread que disputava o processador com os quadros que o
# navegador estava esperando (e as séries seguintes demoravam a começar).
_fila: list[tuple[str, list[str]]] = []
_ativos = 0
_cond = threading.Condition()
_trabalhador: threading.Thread | None = None


class atendendo:
    """`with envio.atendendo():` em volta de um pedido de quadro: o trabalhador de fundo espera."""

    def __enter__(self):
        global _ativos
        with _cond:
            _ativos += 1

    def __exit__(self, *exc):
        global _ativos
        with _cond:
            _ativos -= 1
            _cond.notify_all()


def _esperar_folga(maximo: float = 30.0) -> None:
    import time
    fim = time.time() + maximo
    with _cond:
        while _ativos > 0 and time.time() < fim:
            _cond.wait(0.2)


def _trabalhar() -> None:
    from ipe.central import web as WEB
    while True:
        with _cond:
            if not _fila:
                global _trabalhador
                _trabalhador = None
                return
            chave, caminhos = _fila.pop(0)
        try:
            for c in caminhos:
                _esperar_folga()
                try:
                    WEB.quadros_para_web(c, None)
                except Exception:  # noqa: BLE001
                    pass
        finally:
            with _lock:
                _ocupadas.discard(chave)


def preparar_serie(caminhos: list[str]) -> None:
    """Em segundo plano: faz as cópias de envio da série toda (na fila, quando a rede estiver folgada)."""
    global _trabalhador
    if not codec() or _pasta is None or not caminhos:
        return
    chave = hashlib.sha1("|".join(sorted(caminhos)).encode()).hexdigest()
    with _lock:
        if chave in _ocupadas:
            return
        _ocupadas.add(chave)
    with _cond:
        _fila.append((chave, list(caminhos)))
        if _trabalhador is None:
            _trabalhador = threading.Thread(target=_trabalhar, name="ipe-envio", daemon=True)
            _trabalhador.start()
