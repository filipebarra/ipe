"""0.100.121: avisos ao abrir (IAs não instaladas e versão nova) com "Não me notificar mais"."""
import pytest
from PySide6.QtWidgets import QApplication, QCheckBox, QMessageBox

from ipe.ai import aviso_instalacao as AV
from ipe.core.config import Settings


def _janela(env):
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    return MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)


def _clicar(monkeypatch, texto, marcar=False):
    """Troca o exec() da caixa: marca (ou não) o "Não me notificar mais" e aperta o botão pelo texto."""
    vistos = []

    def fake(self):
        cb = self.checkBox()
        assert isinstance(cb, QCheckBox) and "notificar" in cb.text().lower()
        vistos.append(self.text())
        cb.setChecked(marcar)
        botao = next(b for b in self.buttons() if texto.lower() in b.text().lower())
        botao.click()
        return 0
    monkeypatch.setattr(QMessageBox, "exec", fake)
    return vistos


def test_faltando_sem_segmentacao(monkeypatch):
    from ipe.ai import totalseg as TS
    monkeypatch.setattr(TS, "instalado", lambda s=None: False)
    f = AV.faltando(Settings.__new__(Settings))
    assert f == {"segmentacao": True, "extras": []} and AV.tem_o_que_avisar(f)


def test_faltando_so_extras(monkeypatch):
    from types import SimpleNamespace

    from ipe.ai import extras as EX
    from ipe.ai import totalseg as TS
    monkeypatch.setattr(TS, "instalado", lambda s=None: True)
    monkeypatch.setattr(EX, "prontidao", lambda m, s=None: SimpleNamespace(pronto=(m == "brats"), falta="x"))
    f = AV.faltando(None)
    assert not f["segmentacao"] and len(f["extras"]) == len(EX.MODELOS) - 1
    monkeypatch.setattr(EX, "prontidao", lambda m, s=None: SimpleNamespace(pronto=True, falta=""))
    assert not AV.tem_o_que_avisar(AV.faltando(None))


def test_aviso_depois_nao_desliga(env, monkeypatch):
    from ipe.ui import aviso_ias
    QApplication.instance() or QApplication([])
    w = _janela(env)
    try:
        vistos = _clicar(monkeypatch, "Depois", marcar=False)
        assert aviso_ias.avisar(w, {"segmentacao": True, "extras": []}) == "depois"
        assert vistos and w.settings.get(AV.CHAVE_AVISAR, True) is True
    finally:
        w.close()


def test_aviso_nao_me_notificar_mais_desliga(env, monkeypatch):
    from ipe.ui import aviso_ias
    QApplication.instance() or QApplication([])
    w = _janela(env)
    try:
        _clicar(monkeypatch, "Depois", marcar=True)
        assert aviso_ias.avisar(w, {"segmentacao": False, "extras": ["BraTS"]}) == "nunca"
        assert w.settings.get(AV.CHAVE_AVISAR, True) is False
        monkeypatch.delenv("IPE_SEM_GITHUB", raising=False)
        assert AV.ligado(w.settings) is False
    finally:
        w.close()


def test_aviso_instalar_abre_o_instalador(env, monkeypatch):
    from ipe.ui import aviso_ias
    from ipe.ui import segmentacao as SG
    QApplication.instance() or QApplication([])
    w = _janela(env)
    abriu = []
    monkeypatch.setattr(SG, "abrir_instalador", lambda win, perguntar=True: abriu.append("seg"))
    monkeypatch.setattr(SG, "abrir_instalador_extras", lambda win, **k: abriu.append("extras"))
    try:
        _clicar(monkeypatch, "Instalar a segmentação")
        assert aviso_ias.avisar(w, {"segmentacao": True, "extras": []}) == "instalar"
        _clicar(monkeypatch, "Instalar os modelos extras")
        assert aviso_ias.avisar(w, {"segmentacao": False, "extras": ["BraTS"]}) == "instalar"
        assert abriu == ["seg", "extras"]
        assert aviso_ias.avisar(w, {"segmentacao": False, "extras": []}) == ""        # nada a avisar: nem abre
    finally:
        w.close()


def test_aviso_de_versao_nova_tem_o_checkbox(env, monkeypatch):
    from ipe import __version__
    from ipe.ui import atualizar_github_ui as G
    QApplication.instance() or QApplication([])
    w = _janela(env)
    try:
        info = {"versao": "99.0.0", "notas": "", "pagina": "https://x", "pacotes": []}
        _clicar(monkeypatch, "Depois", marcar=True)
        assert G.responder(w, info, None, True) == "depois"
        assert w.settings.get(G.CHAVE_LIGADO, True) is False and __version__ != "99.0.0"
    finally:
        w.close()
