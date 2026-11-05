"""Arquivos compactados na importação (0.99.66): ZIP, RAR, 7z, TAR (gz/bz2/xz), ISO e CAB.

Sem dependência nova. Cada formato tenta, em ordem, o que houver no computador:

- **ZIP**: o zipfile do Python; se o ZIP usar um método que ele não lê (Deflate64, comum nos ZIPs grandes feitos
  pelo Windows), vai para os programas de fora abaixo;
- **TAR** (.tar, .tar.gz/.tgz, .tar.bz2, .tar.xz): o tarfile do Python;
- **RAR, 7z, ISO, CAB** e o que mais falhar: o **7-Zip** (7z.exe no PATH ou em Arquivos de Programas, também o
  do PeaZip e o NanaZip), o **UnRAR** do WinRAR (só RAR) e o **tar do Windows** (bsdtar/libarchive, que vem com
  o Windows 10 de 2018 em diante e lê RAR, 7z e ISO). No Linux, 7z/7za/7zz, unrar e bsdtar.

Arquivo com senha falha com mensagem, sem travar pedindo a senha. Os volumes seguintes de um RAR ou 7z em partes
(.part2.rar, .r00, .7z.002) são pulados quando o primeiro está junto: o programa lê todos a partir dele. Um
compactado dentro de outro também é aberto (até 3 níveis). Nenhum arquivo sai da pasta de destino (zip-slip).
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

log = logging.getLogger(__name__)

TAR = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz", ".tbz2", ".tar.xz", ".txz")
OUTROS = (".rar", ".7z", ".iso", ".cab")
EXTENSOES = (".zip",) + TAR + OUTROS
FILTRO_DIALOGO = "Compactados (*.zip *.rar *.7z *.tar *.tgz *.tar.gz *.tar.bz2 *.tar.xz *.iso *.cab *.001)"
SENHA_FALSA = "ipe-sem-senha"           # o 7-Zip falha em vez de esperar alguém digitar a senha
NIVEIS = 3

_PARTE_RAR = re.compile(r"\.part(\d+)\.rar$", re.I)
_VOLUME_RAR = re.compile(r"\.r(\d\d)$", re.I)
_VOLUME_7Z = re.compile(r"\.(7z|zip)\.(\d{3})$", re.I)


class ErroCompactado(Exception):
    """Não deu para abrir o compactado (a mensagem diz por quê, em português)."""


def _nome(p: Path) -> str:
    return p.name.lower()


def formato(p) -> str:
    """"zip", "tar", "rar", "7z", "iso", "cab" ou "" (não é compactado). Volume dividido (.7z.001) conta como o
    formato dele."""
    n = _nome(Path(p))
    m = _VOLUME_7Z.search(n)
    if m:
        return m.group(1)
    if _VOLUME_RAR.search(n):
        return "rar"
    if n.endswith(TAR):
        return "tar"
    for ext in (".zip",) + OUTROS:
        if n.endswith(ext):
            return ext[1:]
    return ""


def e_compactado(p) -> bool:
    p = Path(p)
    return p.is_file() and bool(formato(p))


def volume_seguinte(p, junto: set[str] | None = None) -> bool:
    """O 2º, 3º… volume de um compactado em partes, cujo primeiro está na mesma pasta (ou em `junto`): pular."""
    p = Path(p)
    n = p.name
    primeiro = None
    m = _PARTE_RAR.search(n)
    if m and int(m.group(1)) > 1:
        larg = len(m.group(1))
        primeiro = n[:m.start()] + f".part{1:0{larg}d}.rar"
    m = _VOLUME_RAR.search(n)
    if m:
        primeiro = n[:m.start()] + ".rar"
    m = _VOLUME_7Z.search(n)
    if m and int(m.group(2)) > 1:
        primeiro = n[:m.start()] + f".{m.group(1)}.001"
    if primeiro is None:
        return False
    alvo = p.with_name(primeiro)
    return alvo.exists() or (junto is not None and str(alvo) in junto)


# ------------------------------------------------------------------ programas de fora
def _sem_janela() -> dict:
    if sys.platform.startswith("win"):
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}


def _bases_windows() -> list[Path]:
    out = []
    for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)", "LOCALAPPDATA"):
        v = os.environ.get(var)
        if v:
            out.append(Path(v))
    return out


def sete_zip() -> str | None:
    """O executável do 7-Zip, se houver."""
    for nome in ("7z", "7zz", "7za", "7zr"):
        w = shutil.which(nome)
        if w and nome != "7zr":
            return w
    if sys.platform.startswith("win"):
        for b in _bases_windows():
            for rel in ("7-Zip/7z.exe", "Programs/7-Zip/7z.exe", "PeaZip/res/bin/7z/7z.exe", "NanaZip/7z.exe"):
                c = b / rel
                if c.is_file():
                    return str(c)
    return None


def unrar() -> str | None:
    w = shutil.which("unrar") or shutil.which("UnRAR")
    if w:
        return w
    if sys.platform.startswith("win"):
        for b in _bases_windows():
            c = b / "WinRAR" / "UnRAR.exe"
            if c.is_file():
                return str(c)
    return None


def bsdtar() -> str | None:
    """O tar que lê RAR/7z/ISO (bsdtar, da libarchive). No Windows é o tar.exe do sistema."""
    if sys.platform.startswith("win"):
        c = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "tar.exe"
        if c.is_file():
            return str(c)
    w = shutil.which("bsdtar")
    if w:
        return w
    t = shutil.which("tar")
    if t:
        try:
            v = subprocess.run([t, "--version"], capture_output=True, text=True, timeout=10, **_sem_janela())
            if "bsdtar" in (v.stdout or "").lower():
                return t
        except Exception:  # noqa: BLE001
            pass
    return None


def programas() -> dict[str, str | None]:
    """O que este computador tem para abrir compactados (para a tela dizer)."""
    return {"7-Zip": sete_zip(), "UnRAR": unrar(), "tar (libarchive)": bsdtar()}


def _rodar(cmd: list[str]) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=4 * 3600, **_sem_janela())
    except Exception as e:  # noqa: BLE001
        return False, str(e)
    saida = (r.stderr or b"") + b"\n" + (r.stdout or b"")
    txt = saida.decode("utf-8", "replace").strip()
    return r.returncode == 0, txt[-600:]


def _com_7zip(exe: str, arq: Path, dest: Path) -> tuple[bool, str]:
    return _rodar([exe, "x", "-y", f"-p{SENHA_FALSA}", f"-o{dest}", "--", str(arq)])


def _com_unrar(exe: str, arq: Path, dest: Path) -> tuple[bool, str]:
    return _rodar([exe, "x", "-y", "-p-", "-idq", str(arq), str(dest) + os.sep])


def _com_bsdtar(exe: str, arq: Path, dest: Path) -> tuple[bool, str]:
    return _rodar([exe, "-x", "-f", str(arq), "-C", str(dest)])


def _senha(txt: str) -> bool:
    t = "\n".join(ln for ln in txt.lower().splitlines() if not re.search(r"encrypted\s*=", ln))   # o "Encrypted = -" do 7-Zip
    return any(k in t for k in ("wrong password", "password", "encrypted", "encryption", "senha", "passphrase"))


# ------------------------------------------------------------------ Python
def _zip(arq: Path, dest: Path) -> None:
    with zipfile.ZipFile(arq) as zf:
        for info in zf.infolist():
            if info.flag_bits & 0x1:
                raise ErroCompactado(f"O ZIP {arq.name} tem senha. Descompacte-o fora do programa e importe a pasta.")
        _extrair_zip_seguro(zf, dest)


def _extrair_zip_seguro(zf: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    for member in zf.infolist():
        target = (dest / member.filename).resolve()
        if dest not in target.parents and target != dest:
            log.warning("Ignorando entrada suspeita no ZIP: %s", member.filename)
            continue
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def _tar(arq: Path, dest: Path) -> None:
    with tarfile.open(arq) as tf:
        try:
            tf.extractall(dest, filter="data")
        except TypeError:                          # Python sem o filtro (3.10/3.11 antigos)
            dest_r = dest.resolve()
            seguros = []
            for m in tf.getmembers():
                alvo = (dest_r / m.name).resolve()
                if (m.isfile() or m.isdir()) and (dest_r in alvo.parents or alvo == dest_r):
                    seguros.append(m)
            tf.extractall(dest, members=seguros)


def _limpar_fugas(dest: Path) -> None:
    """Depois de um programa de fora: tira links que apontam para fora da pasta."""
    d = dest.resolve()
    for root, dirs, files in os.walk(dest):
        for n in dirs + files:
            p = Path(root) / n
            if p.is_symlink():
                try:
                    alvo = p.resolve()
                except OSError:
                    alvo = None
                if alvo is None or d not in alvo.parents:
                    p.unlink(missing_ok=True)


# ------------------------------------------------------------------ extrair
def extrair(arq, dest) -> str:
    """Extrai o compactado `arq` na pasta `dest`. Devolve o que abriu ("zipfile", "tarfile", "7-Zip", "UnRAR",
    "tar"); se nada abrir, ErroCompactado com o motivo."""
    arq, dest = Path(arq), Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    fmt = formato(arq)
    falhas: list[str] = []
    if fmt == "zip" and not _VOLUME_7Z.search(arq.name):
        try:
            _zip(arq, dest)
            return "zipfile"
        except ErroCompactado:
            raise
        except (NotImplementedError, zipfile.BadZipFile, RuntimeError) as e:
            falhas.append(f"zipfile: {e}")
            log.info("ZIP %s não abriu no Python (%s); tentando 7-Zip/tar", arq.name, e)
    if fmt == "tar":
        try:
            _tar(arq, dest)
            return "tarfile"
        except (tarfile.TarError, OSError, EOFError) as e:
            falhas.append(f"tarfile: {e}")
    tentativas = []
    z = sete_zip()
    if z:
        tentativas.append(("7-Zip", _com_7zip, z))
    if fmt == "rar":
        u = unrar()
        if u:
            tentativas.append(("UnRAR", _com_unrar, u))
    b = bsdtar()
    if b:
        tentativas.append(("tar", _com_bsdtar, b))
    for nome, fn, exe in tentativas:
        ok, txt = fn(exe, arq, dest)
        if ok:
            _limpar_fugas(dest)
            return nome
        if _senha(txt):
            raise ErroCompactado(f"O compactado {arq.name} tem senha. Descompacte-o fora do programa e importe "
                                 "a pasta.")
        falhas.append(f"{nome}: {txt.splitlines()[-1] if txt else 'falhou'}")
    if not tentativas and fmt not in ("zip", "tar"):
        raise ErroCompactado(f"Para abrir {arq.name} ({fmt.upper()}) o programa precisa do 7-Zip (7-zip.org) ou do "
                             "tar do Windows 10/11. Instale o 7-Zip e importe de novo.")
    raise ErroCompactado(f"Não consegui abrir o compactado {arq.name} ({'; '.join(falhas) or 'formato'}).")


def expandir(paths, nova_pasta) -> tuple[list[Path], list[Path], list[str]]:
    """Troca os compactados da lista pelas pastas onde foram extraídos (e abre os compactados de dentro deles).

    `nova_pasta()` cria uma pasta temporária. Devolve (caminhos para importar, pastas temporárias, erros)."""
    paths = [Path(p) for p in paths]
    junto = {str(p) for p in paths}
    saida: list[Path] = []
    temps: list[Path] = []
    erros: list[str] = []

    def abrir(arq: Path, nivel: int) -> None:
        tmp = Path(nova_pasta())
        temps.append(tmp)
        try:
            how = extrair(arq, tmp)
            log.info("%s extraído com %s", arq.name, how)
        except ErroCompactado as e:
            erros.append(str(e))
            return
        if nivel < NIVEIS:
            dentro = [Path(r) / n for r, _d, fs in os.walk(tmp) for n in fs if formato(n)]
            jd = {str(p) for p in dentro}
            for d in dentro:
                if volume_seguinte(d, jd):
                    continue
                abrir(d, nivel + 1)
                try:
                    d.unlink()                      # não tentar ler o compactado como DICOM
                except OSError:
                    pass
        saida.append(tmp)

    for p in paths:
        if p.is_file() and formato(p):
            if volume_seguinte(p, junto):
                continue
            abrir(p, 1)
        else:
            saida.append(p)
    return saida, temps, erros
