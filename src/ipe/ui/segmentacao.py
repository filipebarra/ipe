"""Segmentar órgãos abdominais pela tela (0.98): banco ▸ botão direito na série, ou quadro ▸ botão
direito. O TotalSegmentator roda num processo separado (QProcess) — a tela não trava, a barra mostra
a etapa e o tempo, e Cancelar mata o processo. Uma segmentação por vez: em CPU, duas ao mesmo tempo
só deixam as duas mais lentas.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Qt, QTimer, Signal
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from ipe.ai import totalseg as TS

log = logging.getLogger(__name__)

_rodando: list = []            # a segmentação em curso (e a referência que a mantém viva)


def _valido(obj) -> bool:
    """O objeto do Qt ainda existe (não foi apagado junto com a janela que o criou)?"""
    if obj is None:
        return False
    try:
        import shiboken6
        return shiboken6.isValid(obj)
    except Exception:  # noqa: BLE001
        return True


def _limpar_mortas() -> None:
    """Tira da lista as segmentações cujo objeto o Qt já apagou (0.99.34) e libera o exame delas: antes,
    uma segmentação perdida deixava o programa "ocupado" para sempre — nenhuma outra IA rodava."""
    from ipe.ai import tarefas as TA
    for s in list(_rodando):
        if not _valido(s):
            _rodando.remove(s)
            uid = getattr(s, "_study_uid", "")
            TS.EM_CURSO.discard(uid)
            TA.REGISTRO.mudar(getattr(s, "tarefa", None), TA.ERRO, etapa="",
                              mensagem="interrompida (a janela que a rodava foi fechada)")


def ocupado() -> bool:
    _limpar_mortas()
    return bool(_rodando) or bool(TS.EM_CURSO)


# ------------------------------------------------------------------ instalar (versão 1: baixa uma vez)
def instalador() -> Path | None:
    """O instalar_segmentacao.bat (.sh no Linux): no pacote vem junto do programa; rodando do
    código-fonte, está na pasta do projeto."""
    from ipe.core.runtime import resource_dir
    nome = "instalar_segmentacao.bat" if sys.platform == "win32" else "instalar_segmentacao.sh"
    base = resource_dir()
    for c in (base / nome, base.parent.parent / nome, base.parent / nome):
        if c.is_file():
            return c
    return None


URL_VCREDIST = "https://aka.ms/vs/17/release/vc_redist.x64.exe"


def tem_visual_cpp(plataforma: str | None = None) -> bool:
    """0.99.72: o Microsoft Visual C++ Redistributable 2015-2022 x64, que o PyTorch precisa no Windows (o Ipê em
    si e o Python não). Fora do Windows, sempre True."""
    if not (plataforma or sys.platform).startswith("win"):
        return True
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
                            0, winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)) as k:
            if int(winreg.QueryValueEx(k, "Installed")[0]) == 1:
                return True
    except OSError:
        pass
    sistema = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    return (sistema / "vcruntime140_1.dll").is_file() and (sistema / "msvcp140.dll").is_file()


def _comando_do_mac(cmd: list, env: dict | None = None) -> Path:
    """macOS: o Terminal não recebe argumentos; abre um arquivo .command. Grava um, temporário, com o comando
    (e as variáveis que o instalador precisa) e devolve o caminho."""
    import shlex
    import tempfile
    linhas = ["#!/bin/bash"]
    for k in ("IPE_LANG", "IPE_PESOS", "PYTHONIOENCODING"):
        v = (env or os.environ).get(k)
        if v:
            linhas.append(f"export {k}={shlex.quote(str(v))}")
    linhas.append(" ".join(shlex.quote(str(c)) for c in cmd))
    arq = Path(tempfile.mkdtemp(prefix="ipe_")) / "instalar.command"
    arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    arq.chmod(0o755)
    return arq


def abrir_instalador(janela, perguntar: bool = True) -> bool:
    """Abre o instalador numa janela própria (ele mostra o andamento e pede para fechar no fim).
    O programa não precisa ser reiniciado: o menu passa a funcionar quando o ambiente existir."""
    arq = instalador()
    if arq is None:
        QMessageBox.warning(janela, "Instalar a segmentação",
                            "Não achei o instalar_segmentacao junto do programa. Reinstale o Ipê.")
        return False
    if perguntar:
        ja = TS.instalado(None)
        texto = ("A segmentação já está instalada neste computador. Rodar o instalador de novo atualiza o "
                 "TotalSegmentator e confere os modelos." if ja else
                 "A segmentação de órgãos usa o TotalSegmentator, que é instalado uma vez, à parte do "
                 "programa: PyTorch (só CPU), TotalSegmentator e os modelos dos órgãos abdominais.\n\n"
                 "Precisa de internet e de uns 5 GB livres; leva de 10 a 30 minutos. Pode continuar "
                 "usando o programa enquanto instala.")
        if not tem_visual_cpp():
            texto += "\n\n" + (f"Falta neste computador o Microsoft Visual C++ Redistributable (x64), que o PyTorch "
                                 f"precisa. O instalador tenta instalá-lo sozinho; se preferir, instale antes:\n"
                                 f"{URL_VCREDIST}")
        if QMessageBox.question(janela, "Instalar a segmentação", texto + "\n\nAbrir o instalador agora?") \
                != QMessageBox.Yes:
            return False
    try:
        from ipe.core import i18n
        os.environ["IPE_LANG"] = i18n.current()        # 0.100.13: o instalador fala o idioma do Ipê
        if sys.platform == "win32":
            os.startfile(str(arq))                       # noqa: S606 - janela de console própria
        elif sys.platform == "darwin":                   # 0.100.24: o Terminal do macOS roda um .command
            from ipe.core.runtime import ambiente_do_sistema
            subprocess.Popen(["open", "-a", "Terminal", str(_comando_do_mac(["bash", str(arq)]))],
                             env=ambiente_do_sistema())
        else:
            for term in (["x-terminal-emulator", "-e"], ["gnome-terminal", "--"], ["xterm", "-e"]):
                if shutil.which(term[0]):
                    from ipe.core.runtime import ambiente_do_sistema
                    subprocess.Popen([*term, "bash", str(arq)], env=ambiente_do_sistema())
                    break
            else:
                QMessageBox.information(janela, "Instalar a segmentação", f"Rode num terminal:\n\nbash {arq}")
                return False
    except OSError as e:
        QMessageBox.warning(janela, "Instalar a segmentação", f"Não consegui abrir o instalador: {e}\n\n{arq}")
        return False
    return True


def abrir_instalador_extras(janela, modelos=(), settings=None, perguntar: bool = True) -> bool:
    """0.99.83: MedSAM2, autoPET e BraTS — numa janela de console própria, com o Python da segmentação."""
    from ipe.ai import extras as EX
    cmd = EX.comando_do_instalador(modelos, settings)
    if cmd is None:
        if QMessageBox.question(janela, "Modelos extras",
                                "Os modelos extras rodam no ambiente da segmentação, que ainda não está instalado "
                                "neste computador.\n\nInstalar a segmentação primeiro?") == QMessageBox.Yes:
            abrir_instalador(janela, perguntar=False)
        return False
    if perguntar:
        texto = ("Instala no ambiente da segmentação (uma vez, com internet):\n\n"
                 "• MedSAM2 — segmentar qualquer lesão por uma caixa (156 MB);\n"
                 "• autoPET — lesões no PET-FDG, para o volume metabólico (MTV) e a TLG (o modelo do Zenodo);\n"
                 "• BraTS — glioma na RM: captante, necrose e edema (19 MB);\n"
                 "• FLAMeS — lesões de substância branca no FLAIR: número, volume e regiões (2,4 GB);\n"
                 "• Medula — TotalSpineSeg num ambiente próprio: medula, canal e níveis da coluna (cerca de 3 GB).\n\n"
                 "Agora:\n" + EX.texto_prontidao(settings) + "\n\nAbrir o instalador?")
        if QMessageBox.question(janela, "Modelos extras", texto) != QMessageBox.Yes:
            return False
    from ipe.core.runtime import ambiente_do_sistema
    env = ambiente_do_sistema()
    env["IPE_PESOS"] = str(EX.pasta_pesos())
    env["PYTHONIOENCODING"] = "utf-8"
    for k in ("PYTHONPATH", "PYTHONHOME"):
        env.pop(k, None)
    try:
        if sys.platform == "win32":
            subprocess.Popen(cmd, env=env, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0x10))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-a", "Terminal", str(_comando_do_mac(cmd, env))], env=env)
        else:
            for term in (["x-terminal-emulator", "-e"], ["gnome-terminal", "--"], ["xterm", "-e"]):
                if shutil.which(term[0]):
                    subprocess.Popen([*term, *cmd], env=env)
                    break
            else:
                QMessageBox.information(janela, "Modelos extras", "Rode num terminal:\n\n" + " ".join(cmd))
                return False
    except OSError as e:
        QMessageBox.warning(janela, "Modelos extras", f"Não consegui abrir o instalador: {e}")
        return False
    return True


class Segmentacao(QObject):
    """`terminou(saida, mensagem)`: saida = dict de `totalseg_saida.gravar` ou None (falhou/cancelou)."""
    terminou = Signal(object, str)

    def __init__(self, janela, repo, settings, storage_root, study_uid: str, series_uid: str,
                 cache=None, simular: bool = False, tipo: str = "abdome"):
        # 0.99.34, relato dele: *"fechei o exame e quando abri novamente já se passaram 30 minutos e a
        # segmentação ainda não acabou. não consigo cancelar"*. A segmentação era filha da aba do exame:
        # fechar o exame apagava ela e o processo, mas a tarefa ficava "rodando" e o exame "ocupado", e o
        # Cancelar chamava um objeto que já não existia. Agora ela pertence ao programa: continua rodando
        # com o exame fechado e grava o resultado no exame do mesmo jeito.
        super().__init__(QApplication.instance() or janela)
        if cache is None:
            from ipe.imaging.series import FrameCache
            cache = FrameCache(256)
        self._janela, self.repo, self.storage = janela, repo, storage_root
        self._study_uid = study_uid
        self.trabalho = TS.Trabalho(repo, cache, settings, study_uid, series_uid, simular=simular)
        self.tipo = tipo                         # "abdome" (órgãos) | "coluna" (níveis, 0.99.2)
        if tipo == "coluna":
            from ipe.ai import coluna as COL
            self.trabalho.tarefas_proprias = COL.tarefas
            self.trabalho.min_cortes = COL.MIN_CORTES
        if tipo == "cefalometria":
            from ipe.ai import cefalometria as CF
            self.trabalho.tarefas_proprias = CF.tarefas
            self.trabalho.min_cortes = CF.MIN_CORTES
            self.trabalho.modalidades = ("CT",)
            self.trabalho.motivo_modalidade = "A cefalometria automática é só para TC."
        if tipo == "linfonodos":
            from ipe.ai import linfonodos as LN
            self.trabalho.tarefas_proprias = LN.tarefas
            self.trabalho.min_cortes = LN.MIN_CORTES
            self.trabalho.modalidades = ("CT",)
            self.trabalho.motivo_modalidade = "O mapa dos níveis linfonodais é feito na TC."
        if tipo == "neuro":
            from ipe.ai import neuro as N
            self.trabalho.tarefas_proprias = N.tarefas
            self.trabalho.min_cortes = N.MIN_CORTES
            self.trabalho.modalidades = ("MR", "CT")
            self.trabalho.motivo_modalidade = "Os índices do crânio são para RM ou TC."
        if tipo == "medsam2":                     # 0.99.83: a caixa vem da tela (viewer_tab.caixa_ia)
            from ipe.ai import medsam2 as MS
            self.trabalho.min_cortes = 1
            self.trabalho.modalidades = MS.MODALIDADES
            self.trabalho.motivo_modalidade = "O MedSAM2 segmenta TC, RM e PET."
        from ipe.ai import ferramentas as FE
        self._generica = FE.modulo(tipo)          # 0.99.46: as IAs do contrato comum (nódulos…)
        if self._generica is not None:
            FE.preparar_trabalho(self.trabalho, self._generica)
        self.titulo = self._generica.TITULO if self._generica is not None else {
                       "coluna": "Identificar vértebras e discos",
                       "cefalometria": "Cefalometria automática",
                       "neuro": "Índices do crânio (IA)",
                       "linfonodos": "Níveis linfonodais (IA)",
                       "medsam2": "Segmentar pela caixa (MedSAM2)"}.get(tipo, "Segmentar órgãos")
        self.proc: QProcess | None = None
        self._dlg: QProgressDialog | None = None
        self.etapa = "preparando"
        self.fase = "principal"                  # "conferencia": a segunda sagital da coluna (0.99.5)
        self._primeira: dict | None = None
        self._pend_coluna: dict | None = None   # 0.99.23: a principal esperando a série com a C2
        self.inicio = 0.0
        self.cancelado = False
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._atualizar)

    # ------------------------------------------------------------ janela e progresso (podem sumir)
    @property
    def janela(self):
        """A janela de onde veio o pedido; se ela fechou, a janela ativa do programa (ou nenhuma)."""
        if _valido(self._janela):
            return self._janela
        return QApplication.activeWindow()

    def janela_viva(self) -> bool:
        return _valido(self._janela)

    @property
    def dlg(self):
        return self._dlg if _valido(self._dlg) else None

    @dlg.setter
    def dlg(self, valor) -> None:
        self._dlg = valor

    # ------------------------------------------------------------ começo
    def iniciar(self) -> bool:
        if ocupado():
            QMessageBox.information(self.janela, self.titulo,
                                    "Já há uma segmentação rodando. Espere ela terminar, ou veja e cancele em "
                                    "Aplicações ▸ Tarefas de IA… (também no menu Exibir).")
            return False
        if not self.trabalho.simular and not TS.instalado(self.trabalho.settings):
            if QMessageBox.question(
                    self.janela, self.titulo,
                    "A segmentação ainda não está instalada neste computador. Ela é baixada uma vez "
                    "(uns 5 GB, de 10 a 30 minutos) e fica pronta para sempre.\n\nInstalar agora?") \
                    == QMessageBox.Yes:
                abrir_instalador(self.janela, perguntar=False)
            return False
        extra = "medsam2" if self.tipo == "medsam2" else getattr(self._generica, "MODELO_EXTRA", "")
        if extra and not self.trabalho.simular:          # 0.99.83: MedSAM2, autoPET, BraTS
            from ipe.ai import extras as EX
            if not EX.prontidao(extra, self.trabalho.settings).pronto:
                if QMessageBox.question(self.janela, self.titulo, EX.motivo(extra, self.trabalho.settings) +
                                        "\n\nAbrir o instalador agora?") == QMessageBox.Yes:
                    abrir_instalador_extras(self.janela, (extra,), self.trabalho.settings, perguntar=False)
                return False
        _rodando.append(self)
        TS.EM_CURSO.add(self.trabalho.study_uid)
        from ipe.ai import tarefas as TA                   # 0.99.32: aparece em "Tarefas de IA"
        try:
            info = self.repo.study_info(self.trabalho.study_uid) or {}
        except Exception:  # noqa: BLE001
            info = {}
        self.tarefa = TA.REGISTRO.nova(self.titulo, self.trabalho.study_uid,
                                       f"{info.get('patient_name', '')} {info.get('description', '')}".strip(),
                                       "manual", TA.PREPARANDO, cancelar=self.cancelar).id
        eu = self
        TA.REGISTRO.ao_liberar(self.tarefa, lambda: _liberar(eu))
        self.dlg = QProgressDialog("Montando o volume da série…", "Cancelar", 0, 0, self.janela)
        self.dlg.setWindowTitle(self.titulo)
        self.dlg.setWindowModality(Qt.NonModal)          # dá para continuar lendo enquanto roda
        self.dlg.setMinimumDuration(0)
        self.dlg.setMinimumWidth(460)
        self.dlg.canceled.connect(self.cancelar)
        self.dlg.show()
        QApplication.processEvents()
        return self._lancar()

    def _lancar(self) -> bool:
        """Monta o volume do trabalho atual e inicia o processo (a segunda sagital usa o mesmo caminho)."""
        try:
            self.trabalho.preparar(progresso=self._progresso_volume)
            prog, args, env = self.trabalho.comando()
        except Exception as e:  # noqa: BLE001
            if self.fase == "ancora":                 # sem a âncora: segue com a principal
                log.warning("preparar a série âncora da coluna: %s", e)
                self._sem_ancora(f"não deu para montar a série com a C2 ({e})")
                return True
            if self.fase == "conferencia":            # a primeira já está gravada: segue com ela
                log.warning("preparar a segunda sagital: %s", e)
                self._primeira["notas"].append(f"Não deu para conferir na segunda sagital ({e}): as medidas "
                                               "são de uma sequência só.")
                return False
            if not isinstance(e, TS.Falhou):
                log.exception("preparar a segmentação")
            self._fim(None, str(e) if isinstance(e, TS.Falhou) else f"Não deu para preparar a segmentação: {e}")
            return False
        self.proc = QProcess(self)
        q = QProcessEnvironment()
        for k, v in env.items():
            q.insert(k, v)
        self.proc.setProcessEnvironment(q)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._ler_saida)
        self.proc.finished.connect(self._processo_terminou)
        self.proc.errorOccurred.connect(self._erro_processo)
        self.inicio = time.monotonic()
        self.etapa = "iniciando o TotalSegmentator"
        self._timer.start()
        self._atualizar()
        self.proc.start(prog, args)
        from ipe.ai import tarefas as TA
        TA.REGISTRO.mudar(getattr(self, "tarefa", None), TA.RODANDO, etapa=self.etapa)
        return True

    def _progresso_volume(self, feitos: int, total: int) -> bool:
        if self.dlg is not None:
            self.dlg.setLabelText(f"Montando o volume da série… {feitos}/{total}")
            QApplication.processEvents()
        return not self.cancelado

    # ------------------------------------------------------------ andamento
    def _ler_saida(self) -> None:
        dados = bytes(self.proc.readAllStandardOutput()).decode("utf-8", errors="replace")
        for linha in dados.splitlines():
            linha = linha.strip()
            if linha.startswith("ETAPA "):
                self.etapa = linha[6:]
                from ipe.ai import tarefas as TA
                TA.REGISTRO.mudar(getattr(self, "tarefa", None), etapa=self.etapa)
            elif linha:
                log.debug("TotalSegmentator: %s", linha)
        self._atualizar()

    def _atualizar(self) -> None:
        if self.dlg is None:
            return
        s = int(time.monotonic() - self.inicio) if self.inicio else 0
        fase = {"conferencia": "Conferindo na segunda sagital — ",
                "ancora": "Contando a partir de C2 na outra série — "}.get(self.fase, "Segmentando: ")
        self.dlg.setLabelText(f"{fase}{self.etapa}\n{s // 60}:{s % 60:02d} — em CPU leva alguns minutos; "
                              "dá para continuar trabalhando.")

    def cancelar(self) -> None:
        self.cancelado = True
        self.trabalho.cancelado = True
        proc = self.proc if _valido(self.proc) else None
        if proc is not None and proc.state() != QProcess.NotRunning:
            proc.kill()                             # _processo_terminou fecha a tarefa como cancelada
        elif proc is None and self.inicio:
            # o processo já não existe e ninguém vai avisar o fim: fecha aqui
            self._fim(None, "Segmentação cancelada.")
        # (ainda montando o volume: o progresso devolve False e o _lancar fecha)

    def _erro_processo(self, err) -> None:
        if err == QProcess.FailedToStart and self.fase == "ancora":
            self._sem_ancora("não consegui iniciar a contagem na série com a C2")
            return
        if err == QProcess.FailedToStart and self.fase == "conferencia":
            self.fase = "principal"
            self._primeira["notas"].append("Não consegui iniciar a conferência na segunda sagital: as medidas "
                                           "são de uma sequência só.")
            self._fechar_coluna()
            return
        if err == QProcess.FailedToStart:
            self._fim(None, "Não consegui iniciar o Python da segmentação. Rode de novo o "
                            "instalar_segmentacao.bat.")

    # ------------------------------------------------------------ fim
    def _processo_terminou(self, *_a) -> None:
        if self.fase == "ancora":
            self._fim_ancora()
            return
        if self.fase == "conferencia":
            self._fim_conferencia()
            return
        if self.cancelado:
            self._fim(None, "Segmentação cancelada.")
            return
        if self.dlg is not None:
            self.dlg.setLabelText("Gravando as máscaras e a tabela no exame…")
            QApplication.processEvents()
        try:
            if self.tipo == "coluna":
                self._fim_coluna()
                return
            if self.tipo == "cefalometria":
                self._fim_cefalometria()
                return
            if self.tipo == "neuro":
                self._fim_neuro()
                return
            if self.tipo == "linfonodos":
                self._fim_linfonodos()
                return
            if self.tipo == "medsam2":
                rotulos, versao, segundos = self.trabalho.ler_rotulos()
                lab = rotulos.get("medsam2", (None, {}))[0]
                saida = {"medsam2": lab, "vol": self.trabalho.vol, "versao": versao, "series_uid":
                         self.trabalho.series_uid}
                n = int((lab > 0).sum()) if lab is not None else 0
                self._fim(saida, f"MedSAM2 pronto em {segundos:.0f} s: " +
                          ("máscara com %d voxels." % n if n else "nada achado dentro da caixa."))
                return
            if self._generica is not None:
                self._fim_generica()
                return
            from ipe.ai import totalseg_saida as SAIDA
            res = self.trabalho.ler()
            saida = SAIDA.gravar(self.trabalho, res, self.repo.db, self.storage)
            minutos = (time.monotonic() - self.inicio) / 60
            saida["resultado"] = res
            msg = (f"Segmentação pronta em {minutos:.1f} min: {SAIDA.resumo(res)}. As máscaras e a tabela "
                   "estão no exame (séries “· TotalSegmentator”, só neste computador).")
            self._fim(saida, msg)
        except TS.Falhou as e:
            self._fim(None, str(e))
        except Exception as e:  # noqa: BLE001
            log.exception("ler/gravar a segmentação")
            self._fim(None, f"A segmentação terminou, mas não deu para gravar: {e}")

    def _fim_cefalometria(self) -> None:
        from ipe.ai import cefalometria as CF
        from ipe.ai import cefalometria_saida as CS
        rotulos, versao, _s = self.trabalho.ler_rotulos()
        res = CF.calcular(self.trabalho.vol, rotulos, self.trabalho.settings)
        saida = CS.gravar(self.trabalho, res, versao, self.repo.db, self.storage, repo=self.repo,
                          settings=self.trabalho.settings)
        saida["cefalometria"] = res
        saida["series_uid"] = self.trabalho.series_uid
        minutos = (time.monotonic() - self.inicio) / 60
        msg = (f"Cefalometria pronta em {minutos:.1f} min: {CF.resumo(res)}. As estruturas e a imagem de "
               f"conferência estão no exame (séries “{CF.DESC_SEG}” e “{CF.DESC_IMAGEM}”). Confira cada "
               "número na janela da cefalometria antes de mandar para o laudo.")
        if res.avisos:
            msg += "\n\nConfira: " + "; ".join(res.avisos) + "."
        self._fim(saida, msg)

    def _fim_neuro(self) -> None:
        from ipe.ai import neuro as N
        from ipe.ai import neuro_saida as NS
        res = N.calcular_do_trabalho(self.trabalho, self.trabalho.settings)
        versao = getattr(self.trabalho, "versao", "")
        saida = NS.gravar(self.trabalho, res, versao, self.repo.db, self.storage, repo=self.repo,
                          settings=self.trabalho.settings)
        saida["neuro"] = res
        minutos = (time.monotonic() - self.inicio) / 60
        msg = (f"Índices do crânio prontos em {minutos:.1f} min: {N.resumo(res)}. As estruturas e a imagem de "
               f"conferência estão no exame (séries “{N.DESC_SEG}” e “{N.DESC_IMAGEM}”). Confira cada número na "
               "janela dos índices antes de mandar para o laudo.")
        if res.avisos:
            msg += "\n\nConfira: " + "; ".join(res.avisos) + "."
        self._fim(saida, msg)

    def _fim_generica(self) -> None:
        from ipe.ai import ferramentas as FE
        mod = self._generica
        res, versao = FE.rodar_conta(self.trabalho, mod, self.trabalho.settings)
        saida = FE.gravar(self.trabalho, mod, res, versao, self.repo.db, self.storage, self.repo,
                          self.trabalho.settings)
        self._fim(saida, mod.mensagem(res, (time.monotonic() - self.inicio) / 60))

    def _fim_linfonodos(self) -> None:
        from ipe.ai import linfonodos as LN
        rotulos, versao, _s = self.trabalho.ler_rotulos()
        m = LN.marcos(self.trabalho.vol, rotulos)
        vols = LN.mapa(m, self.trabalho.vol)
        saida = LN.gravar(self.trabalho, m, rotulos, versao, self.repo.db, self.storage, repo=self.repo,
                          volumes=vols)
        saida["linfonodos"] = m
        saida["mapa"] = LN.objeto(m, self.trabalho.study_uid, volumes=vols)
        minutos = (time.monotonic() - self.inicio) / 60
        msg = (f"Mapa dos níveis linfonodais pronto em {minutos:.1f} min ({LN.resumo(m)}). Os rótulos dos "
               "níveis aparecem em qualquer plano; segmente um linfonodo com a ferramenta Segmentar e o nível "
               "vem junto.")
        if m.avisos:
            msg += "\n\nConfira: " + "; ".join(m.avisos) + "."
        self._fim(saida, msg)

    def _fim_coluna(self) -> None:
        from ipe.ai import coluna as COL
        rotulos, versao, _s = self.trabalho.ler_rotulos()
        niveis = COL.nomear(self.trabalho.vol, rotulos)
        if not niveis.itens:
            raise TS.Falhou("O TotalSegmentator não achou vértebras nesta série.")
        if niveis.numeracao.ancora == "modelo":
            # 0.99.23: sem C2 nem a última costela nesta série — outra do exame que pegue da C2 até aqui
            outra = COL.serie_ancora(self.repo, self.trabalho.study_uid, self.trabalho.series_uid,
                                     self.trabalho.settings)
            if outra:
                principal = self.trabalho
                self._pend_coluna = {"trabalho": principal, "rotulos": rotulos, "versao": versao,
                                     "niveis": niveis,
                                     "desc": (self.repo.series_meta(outra) or {}).get("description", "")}
                self.trabalho = TS.Trabalho(self.repo, principal.cache, principal.settings, principal.study_uid,
                                            outra, simular=principal.simular)
                self.trabalho.tarefas_proprias = COL.tarefas_ancora
                self.trabalho.min_cortes = COL.MIN_CORTES
                self.fase, self.etapa = "ancora", "montando o volume"
                if self.dlg is not None:
                    self.dlg.setLabelText("Contando a partir de C2 na outra série: montando o volume…")
                    QApplication.processEvents()
                if self._lancar():
                    return
                self._restaurar_principal()
                niveis = self._pend_coluna["niveis"]
        self._seguir_coluna(niveis, versao)

    def _restaurar_principal(self) -> None:
        anc = self.trabalho
        if self._pend_coluna and anc is not self._pend_coluna["trabalho"]:
            anc.limpar()
            self.trabalho = self._pend_coluna["trabalho"]
        self.fase = "principal"

    def _sem_ancora(self, motivo: str) -> None:
        pend = self._pend_coluna
        self._restaurar_principal()
        pend["niveis"].numeracao.evidencias.append(f"não contei pela C2: {motivo}")
        self._seguir_coluna(pend["niveis"], pend["versao"])

    def _fim_ancora(self) -> None:
        from ipe.ai import coluna as COL
        pend = self._pend_coluna
        if self.cancelado:
            self.cancelado = False
            self._sem_ancora("a contagem na série com a C2 foi cancelada")
            return
        try:
            r2, _v2, _s2 = self.trabalho.ler_rotulos()
            anc = COL.nomear(self.trabalho.vol, r2)
            vol_principal = pend["trabalho"].vol
            niveis = COL.com_ancora(vol_principal, pend["rotulos"], pend["niveis"], anc, pend["desc"])
        except Exception as e:  # noqa: BLE001
            log.exception("contagem pela série âncora")
            self._sem_ancora(f"a contagem na outra série falhou ({e})")
            return
        self._restaurar_principal()
        self._seguir_coluna(niveis, pend["versao"])

    def _seguir_coluna(self, niveis, versao) -> None:
        try:
            self._seguir_coluna_(niveis, versao)
        except Exception as e:  # noqa: BLE001
            if not isinstance(e, TS.Falhou):
                log.exception("gravar a coluna")
            self._fim(None, str(e) if isinstance(e, TS.Falhou) else f"Não deu para gravar a coluna: {e}")

    def _seguir_coluna_(self, niveis, versao) -> None:
        from ipe.ai import coluna as COL
        COL.conferir_anteriores(self.repo, self.trabalho.study_uid, niveis)
        saida = COL.gravar(self.trabalho, niveis, versao, self.repo.db, self.storage, repo=self.repo)
        saida["niveis"] = niveis
        minutos = (time.monotonic() - self.inicio) / 60
        discos, vert = niveis.nomes("disco"), niveis.nomes("vertebra")
        msg = (f"Níveis identificados em {minutos:.1f} min: {vert[0]} a {vert[-1]}"
               + (f", {len(discos)} discos ({discos[0]} a {discos[-1]})" if discos else ", nenhum disco")
               + f". Numeração: {COL.ANCORAS.get(niveis.numeracao.ancora, '')}."
               + " Os nomes aparecem em qualquer série e plano do exame; para corrigir a contagem ou marcar "
                 "uma vértebra de transição, botão direito ▸ Numeração da coluna.")
        frase = COL.frase_do_laudo(niveis.numeracao)
        if niveis.numeracao.tipo_lombossacral or niveis.numeracao.toracolombar:
            msg += f"\n\n{frase}"
        self._primeira = {"saida": saida, "msg": msg, "notas": [],
                          "avisos": ("Confira: " + "; ".join(niveis.avisos) + ".") if niveis.avisos else ""}
        medir = COL.config(self.trabalho.settings, COL.CHAVE_MEDIR) and saida.get("seg_path")
        modalidade = getattr(self.trabalho, "modalidade", "") or self._modalidade()
        if medir and COL.quer_conferencia(self.trabalho.settings, modalidade):
            outra = COL.segunda_serie(self.repo, self.trabalho.study_uid, self.trabalho.series_uid,
                                      self.trabalho.settings)
            if outra:
                # 0.99.5: a mesma conta na outra sagital; as tabelas só saem depois, com as duas
                anterior = self.trabalho
                anterior.limpar()
                self.trabalho = TS.Trabalho(self.repo, anterior.cache, anterior.settings, anterior.study_uid,
                                            outra, simular=anterior.simular)
                for k in ("tarefas_proprias", "min_cortes"):
                    setattr(self.trabalho, k, getattr(anterior, k))
                self.fase, self.etapa = "conferencia", "montando o volume"
                if self.dlg is not None:
                    self.dlg.setLabelText("Conferindo na segunda sagital: montando o volume…")
                    QApplication.processEvents()
                if self._lancar():
                    return
                self.fase = "principal"
            else:
                self._primeira["notas"].append("Não há outra sagital neste exame: as medidas são de uma "
                                               "sequência só.")
        self._fechar_coluna()

    def _modalidade(self) -> str:
        try:
            return (self.repo.series_meta(self.trabalho.series_uid) or {}).get("modality", "") or ""
        except Exception:  # noqa: BLE001
            return ""

    def _fim_conferencia(self) -> None:
        """Acabou a segunda sagital: grava a SEG de conferência (se deu certo) e as tabelas com as duas."""
        from ipe.ai import coluna as COL
        nota = ""
        try:
            if self.cancelado:
                nota = "A conferência na segunda sagital foi cancelada: as medidas são de uma sequência só."
            else:
                rotulos, versao, _s = self.trabalho.ler_rotulos()
                niveis = COL.nomear(self.trabalho.vol, rotulos)
                if not niveis.itens:
                    raise TS.Falhou("o TotalSegmentator não achou vértebras na segunda sagital")
                conf = COL.gravar(self.trabalho, niveis, versao, self.repo.db, self.storage, conferencia=True,
                                  repo=self.repo)
                self._primeira["saida"]["series"] = list(self._primeira["saida"].get("series") or []) + \
                    list(conf.get("series") or [])
                desc = (self.repo.series_meta(self.trabalho.series_uid) or {}).get("description", "")
                nota = f"Conferido na segunda sagital ({desc})."
        except Exception as e:  # noqa: BLE001
            log.exception("conferência da coluna")
            nota = f"A conferência na segunda sagital falhou ({e}): as medidas são de uma sequência só."
        self.cancelado = False
        self._primeira["notas"].append(nota)
        self._fechar_coluna()

    def _fechar_coluna(self) -> None:
        from ipe.ai import coluna as COL
        saida, msg = self._primeira["saida"], self._primeira["msg"]
        if COL.config(self.trabalho.settings, COL.CHAVE_MEDIR) and saida.get("seg_path"):
            try:
                tab = COL.gravar_tabela(self.repo, self.repo.db, self.storage, self.trabalho.study_uid,
                                        saida["seg_path"])
                saida["series"] = list(saida.get("series") or []) + tab["series"]
                saida["medidas"], saida["vertebras"] = tab["medidas"], tab["vertebras"]
                txt = COL.resumo_tabelas(tab)
                if txt:
                    msg += (f"\n\nMedidas: {txt}. As tabelas estão no exame (séries “{COL.DESC_TABELA_VERT}” "
                            f"e “{COL.DESC_TABELA}”).")
            except Exception as e:  # noqa: BLE001
                log.exception("tabelas da coluna")
                msg += f"\n\nNão deu para gravar as tabelas: {e}"
        for n in self._primeira["notas"] + [self._primeira["avisos"]]:
            if n:
                msg += "\n\n" + n
        self._fim(saida, msg)

    def _fim(self, saida, msg: str) -> None:
        if getattr(self, "_terminado", False):
            return
        self._terminado = True
        try:
            self._timer.stop()
        except RuntimeError:
            pass
        self.trabalho.limpar()
        if self.dlg is not None:
            self.dlg.blockSignals(True)
            self.dlg.close()
            self.dlg = None
        if self in _rodando:
            _rodando.remove(self)
            TS.EM_CURSO.discard(self.trabalho.study_uid)
        from ipe.ai import tarefas as TA
        estado = TA.PRONTO if saida is not None else (TA.CANCELADO if self.cancelado else TA.ERRO)
        TA.REGISTRO.mudar(getattr(self, "tarefa", None), estado, etapa="", mensagem=msg)
        try:
            self.terminou.emit(saida, msg)
        except RuntimeError:                         # a aba que pediu já fechou: o resultado já está gravado
            log.info("segmentação terminou com a aba fechada: %s", msg)


def _liberar(seg) -> None:
    """Chamado pela janela Tarefas de IA quando a tarefa não responde ao Cancelar: solta o exame."""
    if seg in _rodando:
        _rodando.remove(seg)
    TS.EM_CURSO.discard(getattr(seg, "_study_uid", ""))
    try:
        seg.cancelado = True
        seg.trabalho.cancelado = True
        if _valido(seg.proc) and seg.proc.state() != QProcess.NotRunning:
            seg.proc.kill()
    except Exception:  # noqa: BLE001
        pass


def carregar_na_aba(tab, saida: dict) -> None:
    """Põe a SEG recém-gravada nas sobreposições de uma aba aberta (um item por órgão; a coluna,
    um objeto com os níveis)."""
    from ipe.imaging import overlays as O
    caminho = (saida or {}).get("seg_path")
    if not caminho or not hasattr(tab, "overlay_objects"):
        return
    if (saida or {}).get("niveis") is not None:
        from ipe.ai import coluna as COL
        obj = COL.objeto_do_seg(caminho)
        repo = getattr(tab, "repo", None)
        confs = tuple(COL.conferencias_do_exame(repo, obj.study_uid)) if repo is not None else ()
        COL.anexar_medidas(obj, confs)
        tab.overlay_objects[:] = [o for o in tab.overlay_objects if o.source != "Coluna"]   # a nova vale
        tab.overlay_objects.append(obj)
        if hasattr(tab, "_apply_overlays"):
            tab._apply_overlays()
        return
    obj = O.load_object(caminho)
    if obj is None:
        return
    from ipe.ui.viewer.onco import SO_NA_SERIE
    if obj.label in SO_NA_SERIE and obj.series_ref:
        obj.so_series = obj.series_ref                   # 0.99.65: só na série em que foi calculado
    mapa = (saida or {}).get("mapa")
    if mapa is not None and not getattr(mapa, "so_series", ""):
        mapa.so_series = obj.series_ref
    ja = {o.key for o in tab.overlay_objects}
    novos = [p for p in O.por_segmento(obj) if p.key not in ja]
    tab.overlay_objects.extend(novos)
    if novos and hasattr(tab, "_apply_overlays"):
        tab._apply_overlays()
