"""Iniciar junto com o sistema (minimizado na bandeja), no Windows e no Linux."""

from __future__ import annotations

import sys
from pathlib import Path

# nome da entrada no "Executar" do Windows: o mesmo de antes, para desligar o que já estava ligado
NAME = "DicomViewer"


def _command() -> str:
    from ipe.core.runtime import app_command
    return app_command("--minimized")


def set_autostart(on: bool) -> str:
    if sys.platform == "win32":
        import winreg
        key = r"Software\Microsoft\Windows\CurrentVersion\Run"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, _command())
            else:
                try:
                    winreg.DeleteValue(k, NAME)
                except FileNotFoundError:
                    pass
        return "ok"
    if sys.platform.startswith("linux"):
        f = Path.home() / ".config/autostart/dicomviewer.desktop"
        if on:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(f"[Desktop Entry]\nType=Application\nName={NAME}\nExec={_command()}\n"
                         "X-GNOME-Autostart-enabled=true\n", encoding="utf-8")
        elif f.exists():
            f.unlink()
        return "ok"
    return "não suportado neste sistema"
