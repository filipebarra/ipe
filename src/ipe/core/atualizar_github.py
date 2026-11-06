"""Versões novas pelo GitHub (0.99.70): procura o último release de filipebarra/ipe, baixa o pacote certo para
este computador, confere o SHA-256 que o GitHub publica e, no Windows instalado, roda o instalador sem perguntas.

Qual pacote:
- **Windows instalado** (há o desinstalador ``unins000.exe`` ao lado do programa): ``-installer.exe``. Roda com
  ``/SILENT``: mantém a pasta do programa, a do banco, o idioma e o modo de uso; o programa fecha e o instalador
  abre a versão nova;
- **Windows portátil**: ``-windows-portable.zip``, baixado e a pasta aberta (trocar a pasta é à mão);
- **Linux**: ``-linux-portable.tar.gz``, idem;

Até a 0.99.80 os nomes eram em português (``-instalador.exe``, ``-windows-portatil.zip``, ``-linux-portatil.tar.gz``):
os dois servem, o inglês primeiro.
- **código-fonte** (o computador de desenvolvimento): só avisa e mostra a página; quem atualiza é o git.

Sem dependência nova (urllib). A consulta manda só o nome do programa e a versão (User-Agent). Sem Qt.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sys
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

REPO = "filipebarra/ipe"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGINA = f"https://github.com/{REPO}/releases/latest"


class ErroAtualizacao(Exception):
    pass


def _agente() -> str:
    from ipe import __version__
    return f"Ipe/{__version__}"


def consultar(timeout: float = 10.0, abrir=None) -> dict:
    """O último release: {versao, tag, nome, notas, pagina, pacotes: [{nome, url, tamanho, sha256}]}."""
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json", "User-Agent": _agente()})
    abrir = abrir or urllib.request.urlopen
    try:
        with abrir(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise ErroAtualizacao(f"Não deu para falar com o GitHub: {e}") from e
    tag = str(d.get("tag_name") or "")
    pacotes = []
    for a in d.get("assets") or []:
        dig = str(a.get("digest") or "")
        pacotes.append({"nome": str(a.get("name") or ""), "url": str(a.get("browser_download_url") or ""),
                        "tamanho": int(a.get("size") or 0),
                        "sha256": dig.split(":", 1)[1] if dig.startswith("sha256:") else ""})
    return {"versao": tag.lstrip("vV"), "tag": tag, "nome": str(d.get("name") or tag),
            "notas": str(d.get("body") or ""), "pagina": str(d.get("html_url") or PAGINA), "pacotes": pacotes}


def modo_desta_instalacao(exe: Path | None = None, plataforma: str | None = None, congelado: bool | None = None) -> str:
    """"instalado" (Windows, pelo instalador), "portatil_windows", "linux" ou "codigo"."""
    from ipe.core.runtime import frozen
    plataforma = plataforma or sys.platform
    congelado = frozen() if congelado is None else congelado
    if not congelado:
        return "codigo"
    if plataforma.startswith("win"):
        pasta = Path(exe or sys.executable).parent
        return "instalado" if any(pasta.glob("unins*.exe")) else "portatil_windows"
    return "linux"


#: 0.99.81: nomes em inglês; os em português (até a 0.99.80) ainda servem
SUFIXO = {"instalado": ("-installer.exe", "-instalador.exe"),
          "portatil_windows": ("-windows-portable.zip", "-windows-portatil.zip"),
          "linux": ("-linux-portable.tar.gz", "-linux-portatil.tar.gz")}


def pacote_para(info: dict, modo: str) -> dict | None:
    for suf in SUFIXO.get(modo) or ():
        p = next((p for p in info.get("pacotes", []) if p["nome"].lower().endswith(suf)), None)
        if p is not None:
            return p
    return None


def ha_nova(info: dict, atual: str) -> bool:
    from ipe.central.atualizacoes import mais_nova
    return bool(info.get("versao")) and mais_nova(info["versao"], atual)


def baixar(pacote: dict, destino: Path, andou=None, abrir=None, timeout: float = 60.0) -> Path:
    """Baixa para `destino` (pasta), conferindo o SHA-256. `andou(feito, total)`."""
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    alvo = destino / Path(pacote["nome"]).name
    parcial = alvo.with_name(alvo.name + ".parcial")
    req = urllib.request.Request(pacote["url"], headers={"User-Agent": _agente()})
    abrir = abrir or urllib.request.urlopen
    h = hashlib.sha256()
    feito = 0
    total = int(pacote.get("tamanho") or 0)
    try:
        with abrir(req, timeout=timeout) as r, open(parcial, "wb") as f:
            total = total or int(r.headers.get("Content-Length") or 0)
            while True:
                bloco = r.read(1024 * 256)
                if not bloco:
                    break
                f.write(bloco)
                h.update(bloco)
                feito += len(bloco)
                if andou:
                    andou(feito, total)
    except Exception as e:  # noqa: BLE001
        parcial.unlink(missing_ok=True)
        raise ErroAtualizacao(f"O download parou: {e}") from e
    if pacote.get("sha256") and h.hexdigest() != pacote["sha256"]:
        parcial.unlink(missing_ok=True)
        raise ErroAtualizacao("O arquivo baixado não confere com o do GitHub (SHA-256 diferente). Tente de novo.")
    parcial.replace(alvo)
    return alvo


def limpar_antigos(destino: Path, manter: Path | None = None) -> None:
    """Os pacotes baixados antes (ocupam centenas de MB)."""
    try:
        for f in Path(destino).glob("Ipe-*"):
            if manter is None or f.resolve() != Path(manter).resolve():
                f.unlink(missing_ok=True)
    except OSError:
        pass
