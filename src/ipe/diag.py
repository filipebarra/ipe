"""Diagnóstico sem gente olhando (0.100.27): usado pelo workflow do macOS para ver o que o Mac faz.

IPE_DIAG=teclado  abre a janela do Modo de uso com "cliente" escolhido e o cursor no endereço; depois de
                  IPE_DIAG_SEGUNDOS (padrão 12) escreve em IPE_DIAG_SAIDA o que há no campo, quem tem o foco e
                  o estado do aplicativo, e sai. Quem testa digita no meio (osascript).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def teclado() -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from ipe.auth.backend import LocalAuth
    from ipe.core.config import Settings
    from ipe.db.repository import Repository
    from ipe.db.session import Database
    from ipe.ui.modo_de_uso import ModoDeUsoDialog
    app = QApplication.instance() or QApplication(sys.argv)
    d = Path(tempfile.mkdtemp(prefix="ipe_diag_"))
    settings = Settings(d / "settings.json")
    repo = Repository(Database(d / "diag.sqlite"))
    dlg = ModoDeUsoDialog(settings, repo, LocalAuth(repo), primeiro_uso=True)
    dlg.radios["cliente"].setChecked(True)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    dlg.e_url.setFocus()
    saida = Path(os.environ.get("IPE_DIAG_SAIDA") or (d / "saida.json"))

    def fim():
        fw = app.focusWidget()
        aw = app.activeWindow()
        dados = {"texto": dlg.e_url.text(), "foco": type(fw).__name__ if fw else None,
                 "foco_e_o_campo": fw is dlg.e_url, "janela_ativa": type(aw).__name__ if aw else None,
                 "estado_do_app": str(app.applicationState()), "plataforma": app.platformName(),
                 "campo_habilitado": dlg.e_url.isEnabled(), "campo_visivel": dlg.e_url.isVisible(),
                 "janela_modal": dlg.isModal(), "flags": hex(int(dlg.windowFlags()))}
        saida.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
        print("DIAG " + json.dumps(dados, ensure_ascii=False), flush=True)
        app.quit()
    QTimer.singleShot(int(float(os.environ.get("IPE_DIAG_SEGUNDOS", "12")) * 1000), fim)
    return app.exec()


def rodar(qual: str) -> int:
    if qual == "teclado":
        return teclado()
    print("IPE_DIAG desconhecido:", qual)
    return 2
