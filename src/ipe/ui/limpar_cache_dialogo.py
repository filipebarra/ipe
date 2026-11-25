"""0.100.120: Configurações ▸ Banco de dados ▸ Limpar o cache do Ipê… (a lógica está em `ipe.core.limpar_cache`)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QLabel, QMessageBox, QProgressDialog, QVBoxLayout,
)

from ipe.core import limpar_cache as LC
from ipe.core.i18n import tr


class LimparCacheDialog(QDialog):
    def __init__(self, janela, parent=None):
        super().__init__(parent or janela)
        self.janela = janela
        self.setWindowTitle(tr("Limpar o cache do Ipê"))
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        topo = QLabel(tr(
            "Apaga o que o Ipê guarda só de passagem e que ele refaz sozinho. O banco, os exames deste computador, "
            "a lixeira e as configurações <b>nunca</b> são tocados."))
        topo.setWordWrap(True)
        lay.addWidget(topo)
        self.c_mem = QCheckBox()
        self.c_exames = QCheckBox()
        self.c_temp = QCheckBox()
        self.c_atual = QCheckBox()
        for c in (self.c_mem, self.c_exames, self.c_temp, self.c_atual):
            lay.addWidget(c)
        self.nota = QLabel("")
        self.nota.setWordWrap(True)
        self.nota.setStyleSheet("color: gray")
        lay.addWidget(self.nota)
        self.botoes = QDialogButtonBox()
        self.b_limpar = self.botoes.addButton(tr("Limpar o que está marcado"), QDialogButtonBox.AcceptRole)
        self.botoes.addButton(tr("Fechar"), QDialogButtonBox.RejectRole)
        self.botoes.accepted.connect(self.limpar)
        self.botoes.rejected.connect(self.reject)
        lay.addWidget(self.botoes)
        self.atualizar()

    # ------------------------------------------------------------------ o que há para limpar
    def _abertos(self) -> set[str]:
        try:
            return {t.study_uid for t in self.janela.all_viewer_tabs() if getattr(t, "study_uid", None)}
        except Exception:  # noqa: BLE001
            return set()

    def atualizar(self) -> None:
        j = self.janela
        usado = j.cache.usado_bytes() if hasattr(j.cache, "usado_bytes") else 0
        self.c_mem.setText(tr("Memória de imagens do visualizador") + f" — {LC.humano(usado)}")
        self.c_mem.setChecked(True)
        self.c_mem.setToolTip(tr("Imagens já lidas, guardadas na memória para rolar rápido. Elas voltam ao abrir o exame."))
        abertos = self._abertos()
        self.exames = [r for r in LC.exames_do_cache(j.repo) if r.study_uid not in abertos]
        remoto = getattr(j.repo, "remote", False)
        self.c_exames.setVisible(remoto)
        if remoto:
            mb = sum(r.size_mb for r in self.exames)
            self.c_exames.setText(tr("Exames baixados do servidor") + f" — {len(self.exames)} "
                                  + tr("exame(s)") + f", {LC.humano(mb * 1024 * 1024)}")
            self.c_exames.setChecked(False)
            self.c_exames.setEnabled(bool(self.exames))
            self.c_exames.setToolTip(tr(
                "Tira do computador os exames que vieram do servidor; ele continua com eles e baixa de novo na "
                "próxima abertura. Os que estão abertos, os protegidos (cadeado) e os que o servidor não tem "
                "por inteiro ficam."))
        self.temp = LC.pastas_temporarias()
        self.c_temp.setText(tr("Pastas temporárias esquecidas") + f" — {len(self.temp)} "
                            + tr("pasta(s)") + f", {LC.humano(sum(LC.tamanho(p) for p in self.temp))}")
        self.c_temp.setChecked(bool(self.temp))
        self.c_temp.setEnabled(bool(self.temp))
        self.c_temp.setToolTip(tr("Sobras das IAs e dos laudos de quando o programa fechou no meio (paradas há mais de 6 horas)."))
        self.atual = LC.atualizacoes_baixadas(j.paths)
        self.c_atual.setText(tr("Atualizações já baixadas") + f" — {len(self.atual)} "
                             + tr("arquivo(s)") + f", {LC.humano(sum(LC.tamanho(p) for p in self.atual))}")
        self.c_atual.setChecked(bool(self.atual))
        self.c_atual.setEnabled(bool(self.atual))
        self.c_atual.setToolTip(tr("Os instaladores das versões que o Ipê já baixou. Baixa de novo se precisar."))
        self.nota.setText(tr("Exames abertos agora não entram na limpeza.") if remoto else "")

    # ------------------------------------------------------------------ limpar
    def limpar(self) -> None:
        j = self.janela
        linhas: list[str] = []
        livres = 0
        if self.c_exames.isVisible() and self.c_exames.isChecked() and self.exames:
            if QMessageBox.question(self, tr("Limpar o cache do Ipê"), tr(
                    "Tirar {} exame(s) baixados deste computador? O servidor continua com eles.").format(
                    len(self.exames))) != QMessageBox.Yes:
                return
        prog = QProgressDialog(tr("Limpando…"), "", 0, 0, self)
        prog.setWindowModality(Qt.WindowModal)
        prog.setCancelButton(None)
        prog.show()
        QApplication.processEvents()
        try:
            if self.c_mem.isChecked():
                antes = j.cache.usado_bytes()
                j.cache.clear()
                livres += antes
                linhas.append(tr("Memória de imagens esvaziada."))
            if self.c_exames.isVisible() and self.c_exames.isChecked():
                cont = {"ok": 0, "so_aqui": 0, "protegido": 0, "erro": 0}
                for r in self.exames:
                    res = LC.apagar_exame_do_cache(j.repo, r.study_uid)
                    cont[res] += 1
                    if res == "ok":
                        livres += int(r.size_mb * 1024 * 1024)
                    QApplication.processEvents()
                linhas.append(tr("Exames tirados do computador: {}.").format(cont["ok"]))
                resto = cont["so_aqui"] + cont["protegido"] + cont["erro"]
                if resto:
                    linhas.append(tr("Ficaram {} (protegidos, só existem aqui ou o servidor não respondeu).").format(resto))
            if self.c_temp.isChecked() and self.temp:
                n, b, f = LC.apagar(self.temp)
                livres += b
                linhas.append(tr("Pastas temporárias apagadas: {}.").format(n) + (f" ({f} " + tr("não deu") + ")" if f else ""))
            if self.c_atual.isChecked() and self.atual:
                n, b, f = LC.apagar(self.atual)
                livres += b
                linhas.append(tr("Atualizações apagadas: {}.").format(n))
        finally:
            prog.close()
        if hasattr(j, "browser"):
            try:
                j.browser.refresh()
            except Exception:  # noqa: BLE001
                pass
        self.atualizar()
        QMessageBox.information(self, tr("Limpar o cache do Ipê"),
                                "\n".join(linhas or [tr("Nada marcado.")]) + "\n\n" + tr("Espaço liberado: {}").format(LC.humano(livres)))
