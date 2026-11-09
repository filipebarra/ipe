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
                    # 0.100.0: o arquivo inteiro (para o cliente) já faz os quadros (para o navegador)
                    if arquivo_para_rede(c) == c:
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


def varrer_recentes(repo, dias: int) -> int:
    """0.100.0: põe na fila (de fundo, que espera a rede folgar) as cópias de envio dos exames dos últimos
    `dias` — quando o médico abrir no cliente ou no navegador, elas já estão prontas. Devolve quantos exames."""
    if dias <= 0 or not codec() or _pasta is None:
        return 0
    from datetime import date, timedelta
    desde = (date.today() - timedelta(days=int(dias))).strftime("%Y%m%d")
    try:
        # numa linha à parte não há usuário na sessão: a busca não filtra por banco
        estudos = repo.search_studies(date_from=desde, limit=500, banco="todos")
    except Exception:  # noqa: BLE001
        log.exception("cópias de envio: exames recentes")
        return 0
    for r in estudos:
        try:
            preparar_serie([f for f in repo.files_for_study(r.study_uid) if f])
        except Exception:  # noqa: BLE001
            log.debug("cópias de envio de %s", r.study_uid, exc_info=True)
    return len(estudos)


# ------------------------------------------------------------------ o arquivo inteiro em HTJ2K (0.100.0)
def pronto_para_rede(caminho: str) -> bool:
    """A cópia do arquivo para o cliente já existe (ou já se sabe que não há o que ganhar)?"""
    if codec() != "htj2k" or _pasta is None:
        return True
    try:
        chave = _chave(caminho, "arquivo")
    except OSError:
        return True
    alvo = _pasta / chave[:2] / (chave + ".dcm")
    return alvo.exists() or alvo.with_suffix(".naoarq").exists()


def arquivo_para_rede(caminho: str) -> str:
    """O arquivo DICOM com os pixels em HTJ2K sem perda, para o programa ligado ao servidor (o cliente).

    O acervo continua como veio; isto é outra cópia de envio (a mesma conferência pixel a pixel, quadro a
    quadro), guardada no cache. Devolve o caminho da cópia, ou o próprio arquivo quando não há o que ganhar
    (já comprimido de outro jeito, cor, sem HTJ2K, ou algum quadro não passou na conferência)."""
    if codec() != "htj2k" or _pasta is None:
        return caminho
    try:
        chave = _chave(caminho, "arquivo")
    except OSError:
        return caminho
    alvo = _pasta / chave[:2] / (chave + ".dcm")
    nao = alvo.with_suffix(".naoarq")
    if alvo.exists():
        return str(alvo)
    if nao.exists():
        return caminho
    import pydicom
    from pydicom.encaps import encapsulate

    from ipe.central import web as WEB
    try:
        ds = pydicom.dcmread(caminho, force=True)
        ts = str(getattr(getattr(ds, "file_meta", None), "TransferSyntaxUID", "") or "")
        if ts not in CONVERTE or not _monocromatico(ds) or "PixelData" not in ds:
            raise _SemGanho
        partes = WEB.quadros_para_web(caminho, None)
        if not partes or any(t != HTJ2K_RPCL for _, t in partes):
            raise _SemGanho
        ds.PixelData = encapsulate([d for d, _ in partes], has_bot=len(partes) > 1)
        ds["PixelData"].VR = "OB"
        ds.file_meta.TransferSyntaxUID = HTJ2K_RPCL
        alvo.parent.mkdir(parents=True, exist_ok=True)
        tmp = alvo.with_suffix(f".{threading.get_ident()}.tmp")
        ds.save_as(tmp, implicit_vr=False, little_endian=True, enforce_file_format=True)
        os.replace(tmp, alvo)
        return str(alvo)
    except _SemGanho:
        pass
    except Exception:  # noqa: BLE001
        log.exception("cópia de envio do arquivo: %s", caminho)
    try:
        nao.parent.mkdir(parents=True, exist_ok=True)
        nao.write_bytes(b"")
    except OSError:
        pass
    return caminho


class _SemGanho(Exception):
    pass
