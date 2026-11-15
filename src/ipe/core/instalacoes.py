"""Qual cópia do Ipê está aberta, e se há outra mais nova instalada neste Windows (0.100.54).

Relato dele (15/11/2026): *"Se baixo manualmente e instalo outra versão, a versão não muda"*. O instalador põe o
programa em ``%LOCALAPPDATA%\\Programs\\Ipe`` (ou na pasta escolhida na primeira vez); o atalho que se clica pode
apontar para outra cópia (o portátil, um instalador antigo de outro lugar) — instala-se uma, abre-se a outra. Ou o
instalador rodou com o Ipê aberto (na bandeja, como servidor) e não conseguiu trocar os arquivos.

- ``registrada()``: a instalação que o instalador gravou no registro (pasta e versão), do usuário ou da máquina.
- ``outra_mais_nova(exe, versao)``: se a registrada é mais nova e é outra pasta, o aviso para mostrar.
- ``marcar_aberto()``: o "mutex" ``IpeViewerAberto``, que o instalador procura para esperar o programa fechar.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

APP_ID = "{7B3A9C2E-5D41-4C8A-9E17-DC0F2A6B8E41}_is1"
CHAVE = r"Software\Microsoft\Windows\CurrentVersion\Uninstall" + "\\" + APP_ID
MUTEX = "IpeViewerAberto"
_mutex = None


def registrada(leitor=None) -> dict | None:
    """{"pasta", "versao", "onde"} da instalação registrada pelo instalador (HKCU primeiro, depois HKLM)."""
    if leitor is None:
        if sys.platform != "win32":
            return None
        leitor = _ler_registro
    for onde in ("HKCU", "HKLM"):
        try:
            d = leitor(onde, CHAVE)
        except Exception:  # noqa: BLE001
            d = None
        if d and d.get("InstallLocation"):
            return {"pasta": str(d["InstallLocation"]).rstrip("\\/"), "versao": str(d.get("DisplayVersion") or ""),
                    "onde": onde}
    return None


def _ler_registro(onde: str, chave: str) -> dict | None:
    import winreg
    raiz = winreg.HKEY_CURRENT_USER if onde == "HKCU" else winreg.HKEY_LOCAL_MACHINE
    out = {}
    try:
        with winreg.OpenKey(raiz, chave) as k:
            for nome in ("InstallLocation", "DisplayVersion"):
                try:
                    out[nome] = winreg.QueryValueEx(k, nome)[0]
                except OSError:
                    pass
    except OSError:
        return None
    return out


def _mesma_pasta(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return str(a).lower().rstrip("\\/") == str(b).lower().rstrip("\\/")


def outra_mais_nova(exe: Path, versao: str, leitor=None) -> dict | None:
    """Se o instalador registrou uma versão mais nova noutra pasta: {"pasta", "versao", "exe"}."""
    from ipe.central.atualizacoes import mais_nova
    r = registrada(leitor)
    if not r or not r["versao"] or not mais_nova(r["versao"], versao):
        return None
    pasta = Path(r["pasta"])
    if _mesma_pasta(pasta, Path(exe).parent):
        return None                                   # mesma pasta: o instalador não conseguiu trocar os arquivos
    alvo = pasta / Path(exe).name
    return {"pasta": str(pasta), "versao": r["versao"], "exe": str(alvo if alvo.exists() else pasta / "Ipe.exe")}


def mesma_pasta_desatualizada(exe: Path, versao: str, leitor=None) -> dict | None:
    """O registro diz versão mais nova NESTA pasta — o instalador rodou, mas os arquivos não foram trocados."""
    from ipe.central.atualizacoes import mais_nova
    r = registrada(leitor)
    if r and r["versao"] and mais_nova(r["versao"], versao) and _mesma_pasta(Path(r["pasta"]), Path(exe).parent):
        return r
    return None


def marcar_aberto() -> None:
    """Cria o mutex com nome que o instalador procura (AppMutex): ele espera o Ipê fechar antes de trocar os
    arquivos, em vez de deixar os antigos no lugar."""
    global _mutex
    if sys.platform != "win32" or _mutex is not None:
        return
    try:
        import ctypes
        k = ctypes.windll.kernel32
        _mutex = [k.CreateMutexW(None, False, MUTEX), k.CreateMutexW(None, False, "Global\\" + MUTEX)]
    except Exception:  # noqa: BLE001
        log.debug("mutex do Ipê", exc_info=True)
