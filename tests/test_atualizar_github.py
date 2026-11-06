"""0.99.70 — versão nova pelo GitHub: consultar, escolher o pacote, baixar conferindo o SHA-256 e instalar."""
import hashlib
import io
import json

import pytest

from ipe.core import atualizar_github as GH


class _Resp(io.BytesIO):
    def __init__(self, dados: bytes, headers=None):
        super().__init__(dados)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


CONTEUDO = b"instalador de mentira" * 1000
RELEASE = {"tag_name": "v9.9.9", "name": "v9.9.9", "body": "- coisas novas", "html_url": "https://x/rel",
           "assets": [{"name": "Ipe-9.9.9-installer.exe", "browser_download_url": "https://x/inst.exe",
                       "size": len(CONTEUDO), "digest": "sha256:" + hashlib.sha256(CONTEUDO).hexdigest()},
                      {"name": "Ipe-9.9.9-linux-portable.tar.gz", "browser_download_url": "https://x/l.tgz",
                       "size": 10, "digest": ""},
                      {"name": "Ipe-9.9.9-windows-portable.zip", "browser_download_url": "https://x/w.zip",
                       "size": 10, "digest": ""}]}


def _abrir(req, timeout=0):
    url = req.full_url
    assert "Ipe/" in req.get_header("User-agent") and "@" not in req.get_header("User-agent")
    if "api.github.com" in url:
        return _Resp(json.dumps(RELEASE).encode())
    return _Resp(CONTEUDO, {"Content-Length": str(len(CONTEUDO))})


def test_consultar_escolher_e_baixar(tmp_path):
    info = GH.consultar(abrir=_abrir)
    assert info["versao"] == "9.9.9" and GH.ha_nova(info, "0.99.70") and not GH.ha_nova(info, "9.9.9")
    assert GH.pacote_para(info, "instalado")["nome"].endswith("-installer.exe")
    assert GH.pacote_para(info, "linux")["nome"].endswith(".tar.gz")
    assert GH.pacote_para(info, "portatil_windows")["nome"].endswith(".zip")
    assert GH.pacote_para(info, "codigo") is None
    passos = []
    arq = GH.baixar(GH.pacote_para(info, "instalado"), tmp_path, lambda f, t: passos.append((f, t)), abrir=_abrir)
    assert arq.read_bytes() == CONTEUDO and passos[-1] == (len(CONTEUDO), len(CONTEUDO))
    ruim = dict(GH.pacote_para(info, "instalado"), sha256="0" * 64)
    with pytest.raises(GH.ErroAtualizacao, match="SHA-256"):
        GH.baixar(ruim, tmp_path / "b", abrir=_abrir)
    assert not list((tmp_path / "b").glob("*"))                       # o parcial não fica
    (tmp_path / "Ipe-0.1-instalador.exe").write_bytes(b"velho")
    GH.limpar_antigos(tmp_path, manter=arq)
    assert [p.name for p in tmp_path.glob("Ipe-*")] == [arq.name]


def test_modo_da_instalacao(tmp_path):
    exe = tmp_path / "Ipe.exe"
    exe.write_bytes(b"")
    assert GH.modo_desta_instalacao(exe, "win32", True) == "portatil_windows"
    (tmp_path / "unins000.exe").write_bytes(b"")
    assert GH.modo_desta_instalacao(exe, "win32", True) == "instalado"
    assert GH.modo_desta_instalacao(exe, "linux", True) == "linux"
    assert GH.modo_desta_instalacao(exe, "win32", False) == "codigo"


def test_erro_de_rede():
    def falha(req, timeout=0):
        raise OSError("sem rede")
    with pytest.raises(GH.ErroAtualizacao, match="GitHub"):
        GH.consultar(abrir=falha)


def test_tela(env, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.ui import atualizar_github_ui as G
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        info = GH.consultar(abrir=_abrir)
        msgs = []
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: msgs.append(a[2]))
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: msgs.append(a[2]))
        assert G.responder(w, dict(info, versao="0.0.1"), None, False) == ""
        assert "mais nova" in msgs[-1]
        assert G.responder(w, None, GH.ErroAtualizacao("sem rede"), True) == "erro"
        # pular esta versão: o aviso automático não volta
        w.settings.set(G.CHAVE_PULADA, "9.9.9")
        assert G.responder(w, info, None, True) == "pulada"
        # baixar e instalar (o instalador e o fechar são de mentira)
        rodou = []
        monkeypatch.setattr(w, "quit_app", lambda: rodou.append("fechou"))
        r = G.baixar_e_instalar(w, GH.pacote_para(info, "instalado"), "instalado",
                                baixar=lambda p, d, andou: GH.baixar(p, d, andou, abrir=_abrir),
                                rodar=lambda arq: rodou.append(arq.name))
        assert r == "instalando" and rodou[0] == "Ipe-9.9.9-installer.exe"
        app.processEvents()
        assert "fechou" in rodou
        # aviso automático: uma vez por dia, e nunca no modo cliente
        chamadas = []
        monkeypatch.delenv("IPE_SEM_GITHUB")
        G.procurar(w, silencioso=True, consultar=lambda: chamadas.append(1) or dict(info, versao="0.0.1"))
        G.procurar(w, silencioso=True, consultar=lambda: chamadas.append(1) or dict(info, versao="0.0.1"))
        import time
        for _ in range(50):
            app.processEvents()
            time.sleep(0.02)
        assert chamadas == [1]
        textos = [a.text() for m in w.menuBar().findChildren(type(w.menuBar().actions()[0].menu()))
                  for a in m.actions()]
        assert "Procurar versão nova (GitHub)…" in textos and "Avisar quando sair versão nova" in textos
    finally:
        w.close()


def test_nomes_antigos_em_portugues_ainda_servem():
    """0.99.81: os pacotes passaram a ter nomes em inglês; um release antigo (português) continua achado."""
    info = {"pacotes": [{"nome": "Ipe-0.99.78-instalador.exe"}, {"nome": "Ipe-0.99.78-windows-portatil.zip"},
                        {"nome": "Ipe-0.99.78-linux-portatil.tar.gz"}]}
    assert GH.pacote_para(info, "instalado")["nome"] == "Ipe-0.99.78-instalador.exe"
    assert GH.pacote_para(info, "portatil_windows")["nome"].endswith("portatil.zip")
    assert GH.pacote_para(info, "linux")["nome"].endswith("portatil.tar.gz")
    # com os dois nomes no mesmo release, vale o inglês
    info["pacotes"].append({"nome": "Ipe-0.99.81-installer.exe"})
    assert GH.pacote_para(info, "instalado")["nome"] == "Ipe-0.99.81-installer.exe"
    assert GH.pacote_para(info, "codigo") is None
