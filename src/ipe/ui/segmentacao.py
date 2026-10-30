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


def ocupado() -> bool:
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
        if QMessageBox.question(janela, "Instalar a segmentação", texto + "\n\nAbrir o instalador agora?") \
                != QMessageBox.Yes:
            return False
    try:
        if sys.platform == "win32":
            os.startfile(str(arq))                       # noqa: S606 - janela de console própria
        else:
            for term in (["x-terminal-emulator", "-e"], ["gnome-terminal", "--"], ["xterm", "-e"]):
                if shutil.which(term[0]):
                    subprocess.Popen([*term, "bash", str(arq)])
                    break
            else:
                QMessageBox.information(janela, "Instalar a segmentação", f"Rode num terminal:\n\nbash {arq}")
                return False
    except OSError as e:
        QMessageBox.warning(janela, "Instalar a segmentação", f"Não consegui abrir o instalador: {e}\n\n{arq}")
        return False
    return True


class Segmentacao(QObject):
    """`terminou(saida, mensagem)`: saida = dict de `totalseg_saida.gravar` ou None (falhou/cancelou)."""
    terminou = Signal(object, str)

    def __init__(self, janela, repo, settings, storage_root, study_uid: str, series_uid: str,
                 cache=None, simular: bool = False, tipo: str = "abdome"):
        super().__init__(janela)
        if cache is None:
            from ipe.imaging.series import FrameCache
            cache = FrameCache(256)
        self.janela, self.repo, self.storage = janela, repo, storage_root
        self.trabalho = TS.Trabalho(repo, cache, settings, study_uid, series_uid, simular=simular)
        self.tipo = tipo                         # "abdome" (órgãos) | "coluna" (níveis, 0.99.2)
        if tipo == "coluna":
            from ipe.ai import coluna as COL
            self.trabalho.tarefas_proprias = COL.tarefas
            self.trabalho.min_cortes = COL.MIN_CORTES
        self.titulo = "Identificar vértebras e discos" if tipo == "coluna" else "Segmentar órgãos"
        self.proc: QProcess | None = None
        self.dlg: QProgressDialog | None = None
        self.etapa = "preparando"
        self.fase = "principal"                  # "conferencia": a segunda sagital da coluna (0.99.5)
        self._primeira: dict | None = None
        self.inicio = 0.0
        self.cancelado = False
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._atualizar)

    # ------------------------------------------------------------ começo
    def iniciar(self) -> bool:
        if ocupado():
            QMessageBox.information(self.janela, self.titulo,
                                    "Já há uma segmentação rodando. Espere ela terminar.")
            return False
        if not self.trabalho.simular and not TS.instalado(self.trabalho.settings):
            if QMessageBox.question(
                    self.janela, self.titulo,
                    "A segmentação ainda não está instalada neste computador. Ela é baixada uma vez "
                    "(uns 5 GB, de 10 a 30 minutos) e fica pronta para sempre.\n\nInstalar agora?") \
                    == QMessageBox.Yes:
                abrir_instalador(self.janela, perguntar=False)
            return False
        _rodando.append(self)
        TS.EM_CURSO.add(self.trabalho.study_uid)
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
            elif linha:
                log.debug("TotalSegmentator: %s", linha)
        self._atualizar()

    def _atualizar(self) -> None:
        if self.dlg is None:
            return
        s = int(time.monotonic() - self.inicio) if self.inicio else 0
        fase = "Conferindo na segunda sagital — " if self.fase == "conferencia" else "Segmentando: "
        self.dlg.setLabelText(f"{fase}{self.etapa}\n{s // 60}:{s % 60:02d} — em CPU leva alguns minutos; "
                              "dá para continuar trabalhando.")

    def cancelar(self) -> None:
        self.cancelado = True
        if self.proc is not None and self.proc.state() != QProcess.NotRunning:
            self.proc.kill()
        elif self.proc is None:
            pass                                    # ainda montando o volume: o progresso devolve False

    def _erro_processo(self, err) -> None:
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

    def _fim_coluna(self) -> None:
        from ipe.ai import coluna as COL
        rotulos, versao, _s = self.trabalho.ler_rotulos()
        niveis = COL.nomear(self.trabalho.vol, rotulos)
        if not niveis.itens:
            raise TS.Falhou("O TotalSegmentator não achou vértebras nesta série.")
        saida = COL.gravar(self.trabalho, niveis, versao, self.repo.db, self.storage, repo=self.repo)
        saida["niveis"] = niveis
        minutos = (time.monotonic() - self.inicio) / 60
        discos, vert = niveis.nomes("disco"), niveis.nomes("vertebra")
        msg = (f"Níveis identificados em {minutos:.1f} min: {vert[0]} a {vert[-1]}"
               + (f", {len(discos)} discos ({discos[0]} a {discos[-1]})" if discos else ", nenhum disco")
               + ". Os nomes aparecem em qualquer série e plano do exame; se a contagem estiver deslocada, "
                 "botão direito ▸ Renumerar os níveis.")
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
        self._timer.stop()
        self.trabalho.limpar()
        if self.dlg is not None:
            self.dlg.blockSignals(True)
            self.dlg.close()
            self.dlg = None
        if self in _rodando:
            _rodando.remove(self)
            TS.EM_CURSO.discard(self.trabalho.study_uid)
        self.terminou.emit(saida, msg)


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
    ja = {o.key for o in tab.overlay_objects}
    novos = [p for p in O.por_segmento(obj) if p.key not in ja]
    tab.overlay_objects.extend(novos)
    if novos and hasattr(tab, "_apply_overlays"):
        tab._apply_overlays()
