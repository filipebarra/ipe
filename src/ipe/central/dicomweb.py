"""Partes do DICOMweb usadas pelo servidor central e pelo cliente: modelo JSON do QIDO-RS e
corpo multipart/related do WADO-RS/STOW-RS."""

from __future__ import annotations

import os
import secrets
from pathlib import Path


def _v(vr: str, *values):
    vals = [v for v in values if v not in (None, "")]
    return {"vr": vr, "Value": vals} if vals else {"vr": vr}


def study_json(r) -> dict:
    return {
        "0020000D": _v("UI", r.study_uid),
        "00100010": {"vr": "PN", "Value": [{"Alphabetic": r.patient_name}]} if r.patient_name else {"vr": "PN"},
        "00100020": _v("LO", r.patient_id), "00100030": _v("DA", r.birth_date), "00100040": _v("CS", r.sex),
        "00080020": _v("DA", r.study_date), "00080030": _v("TM", r.study_time),
        "00080050": _v("SH", r.accession), "00081030": _v("LO", r.description),
        "00080061": _v("CS", *[m for m in (r.modalities or "").split("\\") if m]),
        "00201206": _v("IS", r.num_series), "00201208": _v("IS", r.num_images),
    }


def series_json(s) -> dict:
    return {"0020000D": _v("UI", s.study_uid), "0020000E": _v("UI", s.series_uid), "00080060": _v("CS", s.modality),
            "00200011": _v("IS", s.series_number), "0008103E": _v("LO", s.description),
            "00201209": _v("IS", s.num_images)}


def instance_json(study_uid: str, series_uid: str, i: dict) -> dict:
    return {"0020000D": _v("UI", study_uid), "0020000E": _v("UI", series_uid), "00080018": _v("UI", i["sop_uid"]),
            "00200013": _v("IS", i.get("instance_number")), "00280008": _v("IS", i.get("frames") or 1)}


def value(d: dict, tag: str, default=""):
    e = d.get(tag) or {}
    vals = e.get("Value") or []
    if not vals:
        return default
    v = vals[0]
    if isinstance(v, dict):
        return v.get("Alphabetic", default)
    return v


def new_boundary() -> str:
    return "dv" + secrets.token_hex(12)


META = "X-Ipe-Meta"       # 0.100.38: as colunas da imagem (JSON), para o cliente gravar sem reler o arquivo


def multipart_iter(paths: list[str | Path], boundary: str, chunk: int = 1 << 20, final: bool = True,
                   metas: dict | None = None):
    """Gera o corpo multipart/related (application/dicom) lendo os arquivos em pedaços. `final=False` não fecha
    o corpo (quem chama manda o fim depois). `metas`: caminho -> dicionário que vai no cabeçalho da parte."""
    import json
    for p in paths:
        extra = ""
        if metas and metas.get(str(p)) is not None:
            extra = f"{META}: {json.dumps(metas[str(p)], ensure_ascii=True, separators=(',', ':'))}\r\n"
        yield (f"--{boundary}\r\nContent-Type: application/dicom\r\n{extra}"
               f"Content-Length: {Path(p).stat().st_size}\r\n\r\n").encode("ascii")
        with open(p, "rb") as fh:
            while True:
                b = fh.read(chunk)
                if not b:
                    break
                yield b
        yield b"\r\n"
    if final:
        yield f"--{boundary}--\r\n".encode("ascii")


def boundary_of(content_type: str) -> str:
    for part in content_type.split(";"):
        k, _, v = part.strip().partition("=")
        if k.lower() == "boundary":
            return v.strip().strip('"')
    raise ValueError("multipart sem boundary")


def split_multipart(body: bytes, boundary: str) -> list[bytes]:
    """Partes (só o conteúdo) de um corpo multipart/related."""
    sep = b"--" + boundary.encode("ascii")
    out = []
    for chunk in body.split(sep)[1:]:
        if chunk.startswith(b"--"):
            break
        head, _, data = chunk.partition(b"\r\n\r\n")
        if data.endswith(b"\r\n"):
            data = data[:-2]
        out.append(data)
    return out


class MultipartReader:
    """Lê um multipart/related de um fluxo (resposta HTTP) e grava cada parte num arquivo,
    sem guardar tudo na memória."""

    def __init__(self, stream, boundary: str, dest: Path, progress=None, destino=None):
        """`destino(meta, n) -> Path | None` (0.100.38): onde gravar a parte n, pelo que veio no cabeçalho
        X-Ipe-Meta dela (None = o lugar de sempre, `dest/NNNNNN.dcm`). `self.metas[i]` é o cabeçalho da parte i."""
        self.stream, self.dest, self.progress = stream, Path(dest), progress
        self.delim = b"\r\n--" + boundary.encode("ascii")
        self.first = b"--" + boundary.encode("ascii")
        self.destino = destino
        self.metas: list[dict | None] = []

    @staticmethod
    def _cabecalhos(head: bytes) -> dict:
        out = {}
        for linha in head.split(b"\r\n"):
            k, sep, v = linha.partition(b":")
            if sep:
                out[k.strip().lower().decode("latin-1")] = v.strip().decode("latin-1")
        return out

    def _ler_exato(self, buf: bytes, n: int, fh) -> bytes:
        """Grava em fh exatamente n bytes (do que já está em buf e do fluxo); devolve o que sobrou em buf."""
        if len(buf) >= n:
            fh.write(buf[:n])
            return buf[n:]
        fh.write(buf)
        falta = n - len(buf)
        while falta > 0:
            more = self.stream.read(min(falta, 1 << 20))
            if not more:
                raise EOFError("o servidor fechou a conexão no meio de uma imagem")
            fh.write(more)
            falta -= len(more)
        return b""

    def run(self) -> list[Path]:
        self.dest.mkdir(parents=True, exist_ok=True)
        buf = b""
        files: list[Path] = []
        # até o primeiro delimitador
        while self.first not in buf:
            more = self.stream.read(65536)
            if not more:
                return files
            buf += more
        buf = buf[buf.index(self.first) + len(self.first):]
        while True:
            while b"\r\n\r\n" not in buf:
                more = self.stream.read(65536)
                if not more:
                    return files
                buf += more
            head, buf = buf.split(b"\r\n\r\n", 1)
            if head.startswith(b"--"):
                return files
            cab = self._cabecalhos(head)
            meta = None
            if cab.get("x-ipe-meta"):
                try:
                    import json
                    meta = json.loads(cab["x-ipe-meta"])
                except ValueError:
                    meta = None
            path = (self.destino(meta, len(files)) if self.destino is not None and meta is not None else None) \
                or self.dest / f"{len(files):06d}.dcm"
            self.metas.append(meta)
            tamanho = int(cab["content-length"]) if cab.get("content-length", "").isdigit() else -1
            if tamanho >= 0:
                # 0.100.38: com o tamanho da parte, lê direto os bytes dela (sem procurar o delimitador em cada bloco)
                parcial = Path(str(path) + ".parte")
                try:
                    with open(parcial, "wb") as fh:
                        buf = self._ler_exato(buf, tamanho, fh)
                    os.replace(parcial, path)
                except BaseException:
                    try:
                        parcial.unlink()
                    except OSError:
                        pass
                    raise
                while len(buf) < len(self.delim) + 2:
                    more = self.stream.read(65536)
                    if not more:
                        break
                    buf += more
                files.append(path)
                if self.progress:
                    self.progress(len(files))
                if not buf.startswith(self.delim):
                    return files                       # fim inesperado: o que chegou inteiro fica
                buf = buf[len(self.delim):]
                if buf.startswith(b"--"):
                    return files
                continue
            with open(path, "wb") as fh:
                while True:
                    i = buf.find(self.delim)
                    if i >= 0:
                        fh.write(buf[:i])
                        buf = buf[i + len(self.delim):]
                        break
                    keep = len(self.delim)
                    if len(buf) > keep:
                        fh.write(buf[:-keep])
                        buf = buf[-keep:]
                    more = self.stream.read(1 << 20)
                    if not more:
                        fh.write(buf)
                        files.append(path)
                        return files
                    buf += more
            files.append(path)
            if self.progress:
                self.progress(len(files))
            if buf.startswith(b"--"):
                return files
