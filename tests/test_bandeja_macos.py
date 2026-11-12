"""0.100.30: no macOS o Ipê não põe ícone na barra de menus — no macOS 27, clicar nele fechava o programa
(o Qt 6.11 chama `-[NSEvent clickCount]` num evento que não é de mouse e o sistema aborta)."""
import sys

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QWidget

from ipe.ui.main_window import MainWindow


class _Janela(QWidget):
    _setup_tray = MainWindow._setup_tray
    restore_from_tray = open_automation = quit_app = lambda self: None


def test_sem_bandeja_no_macos(monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    monkeypatch.setattr(sys, "platform", "darwin")
    j = _Janela()
    j._setup_tray()
    assert j.tray is None


def test_bandeja_continua_nos_outros(monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    monkeypatch.setattr(sys, "platform", "win32")
    j = _Janela()
    j._setup_tray()
    assert j.tray is not None
    j.tray.hide()
