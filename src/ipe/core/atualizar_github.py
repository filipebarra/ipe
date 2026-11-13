"""Versões novas pelo GitHub (0.99.70): procura o último release de filipebarra/ipe, baixa o pacote certo para
este computador, confere o SHA-256 que o GitHub publica e, no Windows instalado, roda o instalador sem perguntas.

Qual pacote:
- **Windows instalado** (há o desinstalador ``unins000.exe`` ao lado do programa): ``-installer.exe``. Roda com
  ``/SILENT``: mantém a pasta do programa, a do banco, o idioma e o modo de uso; o programa fecha e o instalador
  abre a versão nova;
- **Windows portátil**: ``-windows-portable.zip``, baixado e a pasta aberta (trocar a pasta é à mão);
- **Linux**: ``-linux-portable.tar.gz``, idem;
- **macOS** (0.100.32): ``-macos-arm64.dmg`` ou ``-macos-x86_64.dmg``, conforme o pacote que está rodando. O programa
  fecha, um roteiro monta o ``.dmg``, troca o ``Ipe.app`` pelo novo e abre de novo (`roteiro_mac`). Se a pasta do
  aplicativo não aceita escrita (ou ele roda de dentro do ``.dmg``), o ``.dmg`` abre no Finder para trocar à mão;

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
    """"instalado" (Windows, pelo instalador), "portatil_windows", "linux", "macos" ou "codigo"."""
    from ipe.core.runtime import frozen
    plataforma = plataforma or sys.platform
    congelado = frozen() if congelado is None else congelado
    if not congelado:
        return "codigo"
    if plataforma.startswith("win"):
        pasta = Path(exe or sys.executable).parent
        return "instalado" if any(pasta.glob("unins*.exe")) else "portatil_windows"
    if plataforma == "darwin":
        return "macos"                       # até a 0.100.31 caía em "linux" e oferecia o pacote errado
    return "linux"


def arquitetura_mac(maquina: str | None = None) -> str:
    """"arm64" (chip Apple) ou "x86_64" (Intel) — a do pacote que está rodando (sob o Rosetta, x86_64)."""
    import platform
    m = (maquina or platform.machine() or "").lower()
    return "arm64" if m in ("arm64", "aarch64") else "x86_64"


def app_do_mac(exe: Path | None = None) -> Path | None:
    """…/Ipe.app a partir de …/Ipe.app/Contents/MacOS/Ipe."""
    exe = Path(exe or sys.executable)
    for p in exe.parents:
        if p.suffix == ".app":
            return p
    return None


def mac_troca_sozinho(app: Path | None) -> bool:
    """Dá para trocar o aplicativo sem o usuário? Não, se ele roda do .dmg, de uma cópia transladada pelo macOS
    (aberto sem ter sido movido para Aplicativos) ou numa pasta sem permissão de escrita."""
    import os
    if app is None or not app.is_dir():
        return False
    txt = str(app)
    if txt.startswith("/Volumes/") or "/AppTranslocation/" in txt:
        return False
    return os.access(app.parent, os.W_OK) and os.access(app, os.W_OK)


ROTEIRO_MAC = r"""#!/bin/bash
# Ipê: troca o aplicativo pela versão nova (gerado pelo programa; 0.100.32)
DMG="$1"; APP="$2"; PID="$3"; ABRIR="${4:-1}"
LOG="$(dirname "$DMG")/atualizacao_mac.log"
exec >"$LOG" 2>&1
echo "$(date) dmg=$DMG app=$APP pid=$PID"
for i in $(seq 1 240); do kill -0 "$PID" 2>/dev/null || break; sleep 0.5; done
MNT="$(mktemp -d /tmp/ipe_atualiza.XXXXXX)"
falhou() { echo "FALHOU: $1"; hdiutil detach "$MNT" -quiet 2>/dev/null; [ "$ABRIR" = 1 ] && open "$DMG"; [ "$ABRIR" = 1 ] && open "$APP"; exit 1; }
hdiutil attach "$DMG" -nobrowse -readonly -mountpoint "$MNT" || falhou "não montou o dmg"
NOVO="$(ls -d "$MNT"/*.app 2>/dev/null | head -1)"
[ -d "$NOVO" ] || falhou "o dmg não tem o aplicativo"
rm -rf "$APP.novo" "$APP.antigo"
ditto "$NOVO" "$APP.novo" || falhou "não copiou o aplicativo novo"
mv "$APP" "$APP.antigo" || { rm -rf "$APP.novo"; falhou "não tirou o aplicativo antigo"; }
if ! mv "$APP.novo" "$APP"; then mv "$APP.antigo" "$APP"; falhou "não pôs o aplicativo novo"; fi
rm -rf "$APP.antigo"
xattr -dr com.apple.quarantine "$APP" 2>/dev/null
hdiutil detach "$MNT" -quiet
rmdir "$MNT" 2>/dev/null
echo "TROCADO"
[ "$ABRIR" = 1 ] && open "$APP"
exit 0
"""


def roteiro_mac(dmg: Path, app: Path, pid: int, abrir: bool = True) -> list[str]:
    """Grava o roteiro ao lado do .dmg e devolve o comando que o roda."""
    script = Path(dmg).with_name("atualizar_mac.sh")
    script.write_text(ROTEIRO_MAC, encoding="utf-8")
    script.chmod(0o755)
    return ["/bin/bash", str(script), str(dmg), str(app), str(int(pid)), "1" if abrir else "0"]


def instalar_no_mac(dmg: Path, app: Path | None = None, pid: int | None = None, popen=None) -> None:
    """Solta o roteiro, desligado deste processo (ele espera o programa fechar). Quem chama fecha o programa."""
    import os
    import subprocess
    app = app or app_do_mac()
    if not mac_troca_sozinho(app):
        raise ErroAtualizacao("Não dá para trocar o aplicativo sozinho neste lugar.")
    cmd = roteiro_mac(dmg, app, pid or os.getpid())
    from ipe.core.runtime import ambiente_do_sistema
    (popen or subprocess.Popen)(cmd, start_new_session=True, stdin=subprocess.DEVNULL, env=ambiente_do_sistema(),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)


#: 0.99.81: nomes em inglês; os em português (até a 0.99.80) ainda servem
SUFIXO = {"instalado": ("-installer.exe", "-instalador.exe"),
          "portatil_windows": ("-windows-portable.zip", "-windows-portatil.zip"),
          "linux": ("-linux-portable.tar.gz", "-linux-portatil.tar.gz")}


def pacote_para(info: dict, modo: str, maquina: str | None = None) -> dict | None:
    sufixos = SUFIXO.get(modo) or ()
    if modo == "macos":
        sufixos = (f"-macos-{arquitetura_mac(maquina)}.dmg",)
    for suf in sufixos:
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
