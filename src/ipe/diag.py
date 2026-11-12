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


def na_janela(win, app) -> None:
    """IPE_DIAG_JANELA=1: na janela de verdade — importa IPE_DIAG_PASTA pela tela, abre o primeiro exame no
    visualizador, abre Configurações ▸ Modo de uso (cliente) e espera a digitação. Cada etapa deixa um arquivo em
    IPE_DIAG_DIR (etapa_*.txt); no fim, resultado.json. Quem testa digita quando aparecer `digite.txt`."""
    from PySide6.QtCore import QTimer
    d = Path(os.environ.get("IPE_DIAG_DIR") or tempfile.mkdtemp(prefix="ipe_diag_"))
    d.mkdir(parents=True, exist_ok=True)
    res: dict = {"etapas": []}

    def marca(nome: str, **extra) -> None:
        res["etapas"].append(nome)
        res.update(extra)
        (d / f"etapa_{len(res['etapas']):02d}_{nome}.txt").write_text(json.dumps(extra, ensure_ascii=False, default=str))
        (d / "resultado.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        print("DIAG", nome, extra, flush=True)

    def github():
        # 0.100.31: no pacote do macOS a busca de atualização falhava (CERTIFICATE_VERIFY_FAILED)
        import threading

        def consulta():
            try:
                from ipe.core import atualizar_github as AG
                (d / "github.txt").write_text("OK " + AG.consultar(timeout=20)["versao"], encoding="utf-8")
            except Exception as e:  # noqa: BLE001
                (d / "github.txt").write_text("ERRO " + str(e), encoding="utf-8")
        threading.Thread(target=consulta, daemon=True).start()

    github()

    def importar():
        pasta = os.environ.get("IPE_DIAG_PASTA")
        if not pasta:
            return abrir_exame()
        marca("importar_comecou")
        win.start_import([Path(pasta)])
        esperar_importacao(0)

    def esperar_importacao(n: int):
        if getattr(win, "_import_thread", None) is not None and n < 600:
            return QTimer.singleShot(500, lambda: esperar_importacao(n + 1))
        estudos = win.repo.search_studies()
        marca("importar_terminou", estudos=len(estudos), esperas=n)
        QTimer.singleShot(1500, abrir_exame)

    def abrir_exame(k: int = 0, abertos=None):
        abertos = [] if abertos is None else abertos
        try:
            estudos = win.repo.search_studies()
        except Exception as e:  # noqa: BLE001
            estudos = []
            marca("exames_erro", erro=repr(e))
        if k >= min(len(estudos), int(os.environ.get("IPE_DIAG_ABRIR", "3"))):
            marca("exames_abertos", abertos=abertos)
            return QTimer.singleShot(int(float(os.environ.get("IPE_DIAG_VER", "8")) * 1000), modo)
        st = estudos[k]
        marca(f"abrindo_{k}", exame=f"{st.modalities} {st.description}")
        try:
            r = win.handle_external({"study_uid": st.study_uid})
        except Exception as e:  # noqa: BLE001
            r = repr(e)
        abertos.append(f"{st.modalities}:{r}")
        QTimer.singleShot(2500, lambda: abrir_exame(k + 1, abertos))

    def modo():
        from ipe.ui.modo_de_uso import ModoDeUsoDialog
        dlg = ModoDeUsoDialog(win.settings, win.repo, getattr(win, "auth", None), win)
        dlg.radios["cliente"].setChecked(True)

        def pronto():
            if os.environ.get("IPE_DIAG_FOCO", "1") == "1":
                dlg.e_url.setFocus()
            fw = app.focusWidget()
            marca("digite", foco=type(fw).__name__ if fw else None, foco_e_o_campo=fw is dlg.e_url,
                  janela_ativa=type(app.activeWindow()).__name__ if app.activeWindow() else None,
                  estado=str(app.applicationState()))
            (d / "digite.txt").write_text("agora")

        def fim():
            fw = app.focusWidget()
            marca("fim", texto=dlg.e_url.text(), foco=type(fw).__name__ if fw else None,
                  foco_e_o_campo=fw is dlg.e_url)
            dlg.reject()
            QTimer.singleShot(500, app.quit)
        QTimer.singleShot(1500, pronto)
        QTimer.singleShot(int(float(os.environ.get("IPE_DIAG_DIGITAR", "12")) * 1000), fim)
        dlg.exec()

    try:                                    # se o roteiro empacar, de 40 em 40 s fica escrito onde cada linha está
        import faulthandler
        na_janela._pilhas = open(d / "onde_esta.log", "w", encoding="utf-8")      # noqa: SIM115
        faulthandler.dump_traceback_later(40, repeat=True, file=na_janela._pilhas)
    except Exception:  # noqa: BLE001
        pass
    try:
        win.settings.set("viewer.outro_paciente_externo", "manter")      # o roteiro abre vários pacientes
    except Exception:  # noqa: BLE001
        pass
    marca("janela_aberta", plataforma=app.platformName())
    QTimer.singleShot(3000, importar)


def rodar(qual: str) -> int:
    if qual == "teclado":
        return teclado()
    print("IPE_DIAG desconhecido:", qual)
    return 2
