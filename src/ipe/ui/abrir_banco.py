"""Abrir o banco com uma janela de espera (0.100.36).

Na primeira abertura depois da atualização o banco SQLite antigo é migrado para o PostgreSQL (pode levar minutos
num banco grande), e a primeira vez que o PostgreSQL do Ipê liga numa pasta ele cria o banco (alguns segundos).
O trabalho corre numa linha de fundo; a janela mostra a tabela e quantas linhas já foram.
"""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger(__name__)


def abrir(path, parent=None, titulo: str = "Ipê"):
    """Devolve o Database, ou None se não deu (a pessoa já viu a mensagem)."""
    from PySide6.QtCore import QCoreApplication, QEventLoop, Qt
    from PySide6.QtWidgets import QMessageBox, QProgressDialog

    from ipe.db.session import Database, migrar_sqlite, precisa_migrar
    estado = {"tabela": "", "feitas": 0, "total": 0, "fim": False, "erro": None, "db": None}
    migrando = precisa_migrar(path)

    def andou(tabela, feitas, total):
        estado.update(tabela=tabela, feitas=feitas, total=total)

    def rodar():
        try:
            if migrando:
                migrar_sqlite(path, andou=andou)
            estado["db"] = Database(path)
        except Exception as e:  # noqa: BLE001
            log.exception("O banco não abriu")
            estado["erro"] = e
        estado["fim"] = True

    threading.Thread(target=rodar, daemon=True, name="abrir-banco").start()
    prog = None
    inicio = time.monotonic()
    while not estado["fim"]:
        if prog is None and (migrando or time.monotonic() - inicio > 1.0):
            prog = QProgressDialog("Preparando o banco de dados…", None, 0, 0, parent)
            prog.setWindowTitle(titulo)
            prog.setWindowModality(Qt.ApplicationModal)
            prog.setMinimumDuration(0)
            prog.setMinimumWidth(420)
            prog.show()
        if prog is not None:
            if migrando and estado["tabela"]:
                prog.setLabelText("Passando o banco de dados para o PostgreSQL (uma vez só)…\n"
                                  f"{estado['tabela']}: {estado['feitas']} de {estado['total']}")
            elif migrando:
                prog.setLabelText("Passando o banco de dados para o PostgreSQL (uma vez só)…")
        QCoreApplication.processEvents(QEventLoop.AllEvents, 100)
        time.sleep(0.05)
    if prog is not None:
        prog.close()
    if estado["erro"] is not None:
        try:
            from ipe.core.config import get_paths
            registros = str(get_paths(criar=False).logs)
        except Exception:  # noqa: BLE001
            registros = "?"
        QMessageBox.critical(parent, titulo,
                             "O banco de dados não abriu.\n\n"
                             f"{estado['erro']}\n\n"
                             "O banco antigo (se havia) continua guardado na pasta de dados. O registro do que "
                             f"aconteceu está em {registros}.")
        return None
    return estado["db"]
