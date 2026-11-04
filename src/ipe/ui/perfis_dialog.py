"""Configurações ▸ Usuários ▸ Perfis por grupo e computador (0.99.56, onda B2) e Configurações ▸ Rede ▸
Atualizações pelo servidor central (onda B1)."""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from ipe.core import perfis as PF
from ipe.ui.tabelas import colunas_ajustaveis

log = logging.getLogger(__name__)


class CapturarDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Capturar deste computador")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Quais preferências deste computador (e suas) entram no perfil?"))
        self.caixas = {}
        for k, rot in PF.GRUPOS.items():
            c = QCheckBox(rot)
            self.caixas[k] = c
            lay.addWidget(c)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def escolhidos(self) -> list[str]:
        return [k for k, c in self.caixas.items() if c.isChecked()]


class PerfisDialog(QDialog):
    def __init__(self, repo, settings, parent=None):
        super().__init__(parent)
        self.repo, self.settings = repo, settings
        self.setWindowTitle("Perfis por grupo e computador")
        self.resize(980, 620)
        try:
            self.perfis = [dict(p) for p in (repo.get_app_setting(PF.CHAVE, []) or []) if isinstance(p, dict)]
        except Exception:  # noqa: BLE001
            log.exception("perfis")
            self.perfis = []
        self._atual = -1
        self.lista = QListWidget()
        self.lista.currentRowChanged.connect(self._mostrar)
        bl = QHBoxLayout()
        for texto, fn in (("+ Perfil", self._novo), ("Tirar", self._tirar), ("↑", lambda: self._mover(-1)),
                          ("↓", lambda: self._mover(1))):
            b = QPushButton(texto)
            b.clicked.connect(fn)
            bl.addWidget(b)
        esq = QWidget()
        le = QVBoxLayout(esq)
        le.setContentsMargins(0, 0, 0, 0)
        le.addWidget(QLabel("Na ordem da lista: o de baixo ganha"))
        le.addWidget(self.lista, 1)
        le.addLayout(bl)
        self.nome = QLineEdit()
        self.ativo = QCheckBox("Ativo")
        self.computadores = QLineEdit(placeholderText="vazio = todos · ex.: SALA-MAMO*, TC-01")
        self.usuarios = QLineEdit(placeholderText="vazio = todos · ex.: ana, bia")
        self.papeis = QLineEdit(placeholderText="vazio = todos · ex.: medico, tecnico")
        self.canal = QComboBox()
        for k, v in PF.CANAIS.items():
            self.canal.addItem(v, k)
        self.valores = QTableWidget(0, 3)
        self.valores.setHorizontalHeaderLabels(["Chave", "Valor (JSON)", "Forçar"])
        colunas_ajustaveis(self.valores)
        bv = QHBoxLayout()
        for texto, fn in (("Capturar deste computador…", self._capturar), ("+ Chave", lambda: self._linha("", "", False)),
                          ("Tirar a chave", self._tirar_chave)):
            b = QPushButton(texto)
            b.clicked.connect(fn)
            bv.addWidget(b)
        bv.addStretch(1)
        form = QFormLayout()
        form.addRow("Nome:", self.nome)
        form.addRow("", self.ativo)
        form.addRow("Computadores:", self.computadores)
        form.addRow("Usuários:", self.usuarios)
        form.addRow("Perfis de acesso:", self.papeis)
        form.addRow("Atualizações:", self.canal)
        aqui = QLabel(f"Este computador: <b>{PF.nome_do_computador()}</b>. “Forçar”: a pessoa não troca essa "
                      "preferência; sem forçar, o perfil é o ponto de partida e cada um ainda ajusta o seu.")
        aqui.setWordWrap(True)
        dir_ = QWidget()
        ld = QVBoxLayout(dir_)
        ld.setContentsMargins(0, 0, 0, 0)
        ld.addLayout(form)
        ld.addWidget(self.valores, 1)
        ld.addLayout(bv)
        ld.addWidget(aqui)
        split = QSplitter(Qt.Horizontal)
        split.addWidget(esq)
        split.addWidget(dir_)
        split.setStretchFactor(1, 3)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._salvar)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(split, 1)
        lay.addWidget(bb)
        self._encher_lista()
        if self.perfis:
            self.lista.setCurrentRow(0)
        else:
            self._habilitar(False)

    # ------------------------------------------------------------------ lista
    def _encher_lista(self) -> None:
        self.lista.blockSignals(True)
        self.lista.clear()
        for p in self.perfis:
            self.lista.addItem(QListWidgetItem(p.get("nome") or "(sem nome)"))
        self.lista.blockSignals(False)

    def _habilitar(self, on: bool) -> None:
        for w in (self.nome, self.ativo, self.computadores, self.usuarios, self.papeis, self.canal, self.valores):
            w.setEnabled(on)

    def _novo(self) -> None:
        self._guardar_atual()
        self.perfis.append({"nome": f"Perfil {len(self.perfis) + 1}", "ativo": True, "valores": {}, "forcados": [],
                            "canal": "estavel"})
        self._atual = -1
        self._encher_lista()
        self.lista.setCurrentRow(len(self.perfis) - 1)

    def _tirar(self) -> None:
        r = self.lista.currentRow()
        if 0 <= r < len(self.perfis):
            self.perfis.pop(r)
            self._atual = -1
            self._encher_lista()
            if self.perfis:
                self.lista.setCurrentRow(min(r, len(self.perfis) - 1))
            else:
                self._habilitar(False)

    def _mover(self, d: int) -> None:
        r = self.lista.currentRow()
        alvo = r + d
        if not (0 <= r < len(self.perfis) and 0 <= alvo < len(self.perfis)):
            return
        self._guardar_atual()
        self.perfis[r], self.perfis[alvo] = self.perfis[alvo], self.perfis[r]
        self._atual = -1
        self._encher_lista()
        self.lista.setCurrentRow(alvo)

    # ------------------------------------------------------------------ um perfil
    def _linha(self, chave: str, texto: str, forcar: bool) -> None:
        i = self.valores.rowCount()
        self.valores.insertRow(i)
        self.valores.setItem(i, 0, QTableWidgetItem(chave))
        self.valores.setItem(i, 1, QTableWidgetItem(texto))
        c = QTableWidgetItem("")
        c.setFlags(c.flags() | Qt.ItemIsUserCheckable)
        c.setCheckState(Qt.Checked if forcar else Qt.Unchecked)
        self.valores.setItem(i, 2, c)

    def _tirar_chave(self) -> None:
        r = self.valores.currentRow()
        if r >= 0:
            self.valores.removeRow(r)

    def _mostrar(self, r: int) -> None:
        self._guardar_atual()
        self._atual = r
        if not (0 <= r < len(self.perfis)):
            self._habilitar(False)
            return
        self._habilitar(True)
        p = self.perfis[r]
        self.nome.setText(p.get("nome", ""))
        self.ativo.setChecked(bool(p.get("ativo", True)))
        self.computadores.setText(", ".join(PF._lista(p.get("computadores"))))
        self.usuarios.setText(", ".join(PF._lista(p.get("usuarios"))))
        self.papeis.setText(", ".join(PF._lista(p.get("papeis"))))
        self.canal.setCurrentIndex(max(0, self.canal.findData(p.get("canal") or "estavel")))
        self.valores.setRowCount(0)
        forc = set(p.get("forcados") or [])
        for k, v in (p.get("valores") or {}).items():
            self._linha(k, PF.texto_do_valor(v), k in forc)

    def _ler_atual(self) -> dict:
        valores, forcados = {}, []
        for i in range(self.valores.rowCount()):
            k = (self.valores.item(i, 0).text() if self.valores.item(i, 0) else "").strip()
            if not k:
                continue
            valores[k] = PF.valor_do_texto(self.valores.item(i, 1).text() if self.valores.item(i, 1) else "")
            if self.valores.item(i, 2) is not None and self.valores.item(i, 2).checkState() == Qt.Checked:
                forcados.append(k)
        return {"nome": self.nome.text().strip() or "(sem nome)", "ativo": self.ativo.isChecked(),
                "computadores": PF._lista(self.computadores.text()), "usuarios": PF._lista(self.usuarios.text()),
                "papeis": PF._lista(self.papeis.text()), "canal": self.canal.currentData(),
                "valores": valores, "forcados": forcados}

    def _guardar_atual(self) -> None:
        if 0 <= self._atual < len(self.perfis):
            self.perfis[self._atual] = self._ler_atual()
            it = self.lista.item(self._atual)
            if it is not None:
                it.setText(self.perfis[self._atual]["nome"])

    def _capturar(self, grupos: list[str] | None = None) -> int:
        if grupos is None:
            dlg = CapturarDialog(self)
            if not dlg.exec():
                return 0
            grupos = dlg.escolhidos()
        vals = PF.capturar(self.settings, grupos)
        existentes = {self.valores.item(i, 0).text(): i for i in range(self.valores.rowCount())
                      if self.valores.item(i, 0)}
        for k, v in vals.items():
            if k in existentes:
                self.valores.item(existentes[k], 1).setText(PF.texto_do_valor(v))
            else:
                self._linha(k, PF.texto_do_valor(v), False)
        return len(vals)

    def _salvar(self) -> None:
        self._guardar_atual()
        try:
            self.repo.set_app_setting(PF.CHAVE, self.perfis)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Perfis", f"Não deu para gravar: {e}")
            return
        self.accept()


# ------------------------------------------------------------------ atualizações (onda B1)
class _Remoto:
    """As atualizações do servidor, vistas de um cliente."""

    def __init__(self, client):
        self.c = client

    def todas(self):
        return self.c.rpc("atualizacoes_todas")

    def publicar(self, arq: Path, versao: str, canal: str, notas: str):
        return self.c.publicar_atualizacao(arq, versao, canal, notas)

    def promover(self):
        return self.c.rpc("atualizacao_promover")

    def retirar(self, canal: str):
        return self.c.rpc("atualizacao_retirar", canal)


class _Local:
    """As atualizações vistas do próprio servidor."""

    def __init__(self, loja, quem: str = ""):
        self.loja, self.quem = loja, quem

    def todas(self):
        return self.loja.todas()

    def publicar(self, arq: Path, versao: str, canal: str, notas: str):
        return self.loja.publicar(Path(arq), Path(arq).name, versao, canal, notas, self.quem)

    def promover(self):
        return self.loja.promover(self.quem)

    def retirar(self, canal: str):
        return self.loja.retirar(canal)


class AtualizacoesDialog(QDialog):
    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.b = backend
        self.setWindowTitle("Atualizações pelo servidor central")
        self.resize(640, 360)
        self.texto = QLabel()
        self.texto.setWordWrap(True)
        self.texto.setTextFormat(Qt.RichText)
        h = QHBoxLayout()
        for rot, fn in (("Publicar no teste…", lambda: self.publicar("teste")),
                        ("Publicar no estável…", lambda: self.publicar("estavel")),
                        ("Promover teste → estável", self.promover),
                        ("Retirar o teste", lambda: self.retirar("teste")),
                        ("Retirar o estável", lambda: self.retirar("estavel"))):
            b = QPushButton(rot)
            b.clicked.connect(fn)
            h.addWidget(b)
        nota = QLabel("Publique o instalador do Windows (Ipe-setup-x.y.z.exe): os computadores do canal recebem o "
                      "aviso ao entrar e instalam com um clique. Quem está no canal “teste” se escolhe nos perfis "
                      "(Configurações ▸ Usuários ▸ Perfis por grupo e computador).")
        nota.setWordWrap(True)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(self.texto, 1)
        lay.addLayout(h)
        lay.addWidget(nota)
        lay.addWidget(bb)
        self.recarregar()

    def recarregar(self) -> None:
        from ipe import __version__
        try:
            t = self.b.todas() or {}
        except Exception as e:  # noqa: BLE001
            self.texto.setText(f"Não deu para ler o servidor: {e}")
            return
        linhas = [f"Este computador: versão <b>{__version__}</b>"]
        for canal, rot in (("estavel", "Estável"), ("teste", "Teste")):
            d = t.get(canal)
            if d:
                mb = d.get("tamanho", 0) / 1024 / 1024
                linhas.append(f"<b>{rot}</b>: {d['versao']} — {d['nome']} ({mb:.0f} MB), publicada em "
                              f"{d.get('publicado_em', '')} por {d.get('por', '') or '—'}"
                              + (f"<br><small>{d['notas']}</small>" if d.get("notas") else ""))
            else:
                linhas.append(f"<b>{rot}</b>: nada publicado")
        self.texto.setText("<br><br>".join(linhas))

    def publicar(self, canal: str, arquivo: str = "", versao: str | None = None, notas: str | None = None) -> dict | None:
        from ipe.central import atualizacoes as AT
        if not arquivo:
            arquivo, _f = QFileDialog.getOpenFileName(self, "Pacote da atualização", "",
                                                      "Instalador ou pacote (*.exe *.zip *.tgz *.tar.gz);;Todos (*)")
            if not arquivo:
                return None
        if versao is None:
            versao, ok = QInputDialog.getText(self, "Versão", "Versão do pacote:", text=AT.versao_do_nome(arquivo))
            if not ok:
                return None
        if notas is None:
            notas, ok = QInputDialog.getText(self, "Notas", "O que muda (aparece para quem atualiza):")
            if not ok:
                notas = ""
        try:
            d = self.b.publicar(Path(arquivo), versao.strip(), canal, notas.strip())
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Atualizações", f"Não deu para publicar: {e}")
            return None
        self.recarregar()
        return d

    def promover(self) -> None:
        try:
            self.b.promover()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Atualizações", f"Não deu para promover: {e}")
        self.recarregar()

    def retirar(self, canal: str) -> None:
        try:
            self.b.retirar(canal)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Atualizações", f"Não deu para retirar: {e}")
        self.recarregar()
