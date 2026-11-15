"""0.100.47 — o Mac ligado a um servidor (Ubuntu) baixava o pacote do Linux: um pacote por sistema em cada canal."""
import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from ipe.auth.backend import LocalAuth
from ipe.central import atualizacoes as AT
from ipe.central.remote import RemoteClient
from ipe.central.server import CentralServer
from ipe.core.config import Settings


def _pac(pasta: Path, nome: str, conteudo: bytes = b"x" * 100) -> Path:
    p = pasta / nome
    p.write_bytes(conteudo)
    return p


def test_plataforma_do_nome_e_deste():
    assert AT.plataforma_do_nome("Ipe-0.100.46-installer.exe") == "windows"
    assert AT.plataforma_do_nome("Ipe-setup-0.99.61.exe") == "windows"
    assert AT.plataforma_do_nome("Ipe-0.100.46-windows-portable.zip") == "windows"
    assert AT.plataforma_do_nome("Ipe-0.100.46-linux-portable.tar.gz") == "linux"
    assert AT.plataforma_do_nome("Ipe-0.100.46-linux-amd64.deb") == "linux"
    assert AT.plataforma_do_nome("Ipe-0.100.46-macos-arm64.dmg") == "macos-arm64"
    assert AT.plataforma_do_nome("Ipe-0.100.46-macos-x86_64.dmg") == "macos-x86_64"
    assert AT.plataforma_do_nome("leiame.txt") == ""
    assert AT.plataforma_deste("win32") == "windows" and AT.plataforma_deste("linux") == "linux"
    assert AT.plataforma_deste("darwin", "arm64") == "macos-arm64"
    assert AT.plataforma_deste("darwin", "x86_64") == "macos-x86_64"
    assert AT.serve_para({"nome": "Ipe-1.0.0-macos-arm64.dmg"}, "macos-arm64")
    assert not AT.serve_para({"nome": "Ipe-1.0.0-linux-portable.tar.gz"}, "macos-arm64")
    assert not AT.serve_para({}, "linux")


def test_loja_um_pacote_por_sistema(tmp_path):
    loja = AT.Atualizacoes(tmp_path / "A")
    win = _pac(tmp_path, "Ipe-1.0.1-installer.exe", b"MZ" + b"w" * 50)
    lin = _pac(tmp_path, "Ipe-1.0.1-linux-portable.tar.gz", b"l" * 70)
    mac = _pac(tmp_path, "Ipe-1.0.1-macos-arm64.dmg", b"m" * 90)
    loja.publicar(lin, lin.name, "", "teste")
    assert loja.info("teste", "macos-arm64") is None                     # o Mac não recebe o do Linux
    assert loja.info("teste") is None                                    # cliente antigo: só o do Windows
    loja.publicar(win, win.name, "", "teste")
    d = loja.publicar(mac, mac.name, "", "teste", "notas")
    assert d["plataforma"] == "macos-arm64"
    assert loja.info("teste", "linux")["nome"] == lin.name               # publicar um não mexe nos outros
    assert loja.caminho("teste", "macos-arm64").read_bytes() == mac.read_bytes()
    assert loja.info("teste")["nome"] == win.name
    assert set(loja.plataformas("teste")) == {"windows", "linux", "macos-arm64"}
    assert loja.todas()["teste"]["nome"] == win.name
    p = loja.promover("Admin")
    assert p["canal"] == "estavel" and p["plataformas"] == ["linux", "macos-arm64", "windows"]
    assert loja.info("estavel", "macos-arm64")["sha256"] == AT.sha256_de(mac)
    assert loja.retirar("teste", "linux") and loja.info("teste", "linux") is None
    assert loja.info("teste", "windows") is not None
    assert not loja.retirar("teste", "macos-x86_64")
    assert loja.retirar("teste") and loja.plataformas("teste") == {}
    with pytest.raises(ValueError):
        loja.publicar(_pac(tmp_path, "pacote-1.0.0.bin"), "pacote-1.0.0.bin", "", "teste")
    assert loja.publicar(_pac(tmp_path, "p-1.0.0.bin"), "p-1.0.0.bin", "", "teste", plataforma="linux")


def test_formato_antigo_continua(tmp_path):
    """Pasta gravada até a 0.100.46: <canal>/<pacote> e <canal>.json com um pacote só."""
    base = tmp_path / "A"
    (base / "estavel").mkdir(parents=True)
    lin = _pac(base / "estavel", "Ipe-1.0.0-linux-portable.tar.gz")
    (base / "estavel.json").write_text(json.dumps({"canal": "estavel", "versao": "1.0.0", "nome": lin.name,
                                                   "sha256": AT.sha256_de(lin), "tamanho": 100}), encoding="utf-8")
    loja = AT.Atualizacoes(base)
    assert loja.info("estavel", "linux")["versao"] == "1.0.0"
    assert loja.info("estavel", "macos-arm64") is None and loja.info("estavel") is None
    mac = _pac(tmp_path, "Ipe-1.0.1-macos-arm64.dmg")
    loja.publicar(mac, mac.name, "", "estavel")                          # o antigo muda para a pasta do sistema
    assert loja.caminho("estavel", "linux") == base / "estavel" / "linux" / lin.name
    assert loja.caminho("estavel", "linux").is_file() and not (base / "estavel" / lin.name).exists()
    assert set(loja.plataformas("estavel")) == {"linux", "macos-arm64"}


@pytest.fixture()
def servidor(env):
    paths, db, repo = env
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    yield srv
    srv.stop()


def test_pelo_servidor_cada_um_o_seu(servidor, tmp_path):
    adm = RemoteClient(f"http://127.0.0.1:{servidor.port}")
    adm.login("admin", "admin123")
    lin = _pac(tmp_path, "Ipe-2.0.0-linux-portable.tar.gz", b"l" * 300)
    mac = _pac(tmp_path, "Ipe-2.0.0-macos-arm64.dmg", b"m" * 400)
    assert adm.publicar_atualizacao(lin, "", "estavel")["plataforma"] == "linux"
    assert adm.info_atualizacao("estavel", "macos-arm64") == {}          # era aqui que o Mac pegava o do Linux
    assert adm.info_atualizacao("estavel") == {}                         # cliente antigo (Windows) também não
    adm.publicar_atualizacao(mac, "", "estavel")
    assert adm.info_atualizacao("estavel", "macos-arm64")["nome"] == mac.name
    arq = adm.baixar_atualizacao("estavel", tmp_path / "b" / mac.name, None, "macos-arm64")
    assert arq.read_bytes() == mac.read_bytes()
    arq = adm.baixar_atualizacao("estavel", tmp_path / "c" / lin.name, None, "linux")
    assert arq.read_bytes() == lin.read_bytes()
    por = adm.rpc("atualizacoes_por_plataforma")
    assert set(por["estavel"]) == {"linux", "macos-arm64"} and por["teste"] == {}
    assert adm.rpc("atualizacao_retirar", "estavel", "linux") is True
    assert adm.info_atualizacao("estavel", "linux") == {}


def test_cliente_nao_baixa_pacote_de_outro_sistema(env, monkeypatch, tmp_path):
    """Servidor antigo (não sabe da plataforma) com o pacote do Linux; o cliente é um Mac."""
    from ipe.ui.main_window import MainWindow
    paths, _db, _repo = env
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(AT, "plataforma_deste", lambda *a, **k: "macos-arm64")
    w = MainWindow(paths, Settings(paths.settings_file))
    baixou, perguntas, github = [], [], []

    class Cli:
        def info_atualizacao(self, canal, plataforma=""):
            assert plataforma == "macos-arm64"
            return {"versao": "9.0.0", "nome": "Ipe-9.0.0-linux-portable.tar.gz", "sha256": ""}

        def baixar_atualizacao(self, *a, **k):
            baixou.append(a)
    try:
        w._central = (None, type("R", (), {"client": Cli()})(), None)
        w._perfil = {"canal": "estavel"}
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: perguntas.append(a[2]) or QMessageBox.Yes)
        monkeypatch.setattr(w, "procurar_versao_github", lambda silencioso=False: github.append(silencioso))
        assert w.procurar_atualizacao(silencioso=True) == "outro_sistema" and not perguntas
        assert w.procurar_atualizacao(silencioso=False) == "outro_sistema"
        assert not baixou and "macOS" in perguntas[0] and "GitHub" in perguntas[0] and github == [False]
    finally:
        w._central = None
        w.close()


def test_tela_mostra_os_sistemas(tmp_path):
    from ipe.ui.perfis_dialog import AtualizacoesDialog, _Local
    QApplication.instance() or QApplication([])
    loja = AT.Atualizacoes(tmp_path / "A")
    a = AtualizacoesDialog(_Local(loja, "Admin"))
    a.publicar("teste", str(_pac(tmp_path, "Ipe-3.0.0-macos-x86_64.dmg")), "", "")
    a.publicar("teste", str(_pac(tmp_path, "Ipe-3.0.0-installer.exe")), "", "")
    t = a.texto.text()
    assert "macOS (Intel): 3.0.0" in t and "Windows: 3.0.0" in t and "Linux: <span" in t
