"""0.99.56 — onda B2 (perfis por grupo e computador) e B1 (atualização dos clientes pelo servidor)."""
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from ipe.auth.backend import LocalAuth
from ipe.central import atualizacoes as AT
from ipe.central.remote import RemoteClient, RemoteError
from ipe.central.server import CentralServer
from ipe.core import perfis as PF
from ipe.core.config import Settings

PERFIS = [
    {"nome": "Mamografia", "computadores": ["SALA-MAMO*"], "valores": {"viewer.invert_mg": True,
                                                                      "browser.columns": ["patient_name"]},
     "forcados": ["browser.columns"], "canal": "estavel"},
    {"nome": "Teste", "usuarios": ["ana"], "valores": {"viewer.zoom_padrao": 2}, "canal": "teste"},
    {"nome": "Desligado", "ativo": False, "valores": {"viewer.x": 1}},
]


def test_casar_e_juntar():
    j = PF.juntar(PERFIS, "SALA-MAMO2", "ana", "medico")
    assert j["nomes"] == ["Mamografia", "Teste"] and j["canal"] == "teste"
    assert j["valores"]["viewer"] == {"invert_mg": True, "zoom_padrao": 2} and j["forcados"] == ["browser.columns"]
    j2 = PF.juntar(PERFIS, "TC-01", "bia", "medico")
    assert j2["nomes"] == [] and j2["canal"] == "estavel"
    assert PF.casa({"papeis": "tecnico"}, "X", "u", "Tecnico") and not PF.casa({"papeis": "tecnico"}, "X", "u", "medico")
    assert PF.valor_do_texto('{"a": 1}') == {"a": 1} and PF.valor_do_texto("texto") == "texto"


def test_camada_do_perfil_nas_preferencias(tmp_path):
    st = Settings(tmp_path / "s.json")
    st.set("viewer.invert_mg", False)
    st.attach_user({"viewer": {"invert_mg": False, "zoom_padrao": 5}, "browser": {"columns": ["accession"]}})
    j = PF.juntar(PERFIS, "SALA-MAMO2", "ana", "medico")
    st.attach_perfil(j)
    assert st.get("viewer.invert_mg") is False                    # a pessoa ajusta o seu (não forçado)
    assert st.get("viewer.zoom_padrao") == 5
    assert st.get("browser.columns") == ["patient_name"]          # forçado: ninguém troca
    assert st.get("browser")["columns"] == ["patient_name"]       # pedindo o grupo inteiro também
    st.attach_user({})
    assert st.get("viewer.invert_mg") is True                     # sem o da pessoa: vale o perfil (sobre o computador)
    assert st.get("nada.disso", 7) == 7
    st.attach_perfil({})
    assert st.perfil is None and st.get("viewer.invert_mg") is False


def test_loja_de_atualizacoes(tmp_path):
    loja = AT.Atualizacoes(tmp_path / "Atualizacoes")
    pac = tmp_path / "Ipe-setup-0.99.60.exe"
    pac.write_bytes(b"MZ" + b"x" * 1000)
    d = loja.publicar(pac, pac.name, "", "teste", "notas", "Admin")
    assert d["versao"] == "0.99.60" and d["sha256"] == AT.sha256_de(pac) and loja.info("estavel") is None
    e = loja.promover("Admin")
    assert e["canal"] == "estavel" and loja.caminho("estavel").read_bytes() == pac.read_bytes()
    assert AT.ha_versao_nova(e, "0.99.56") and not AT.ha_versao_nova(e, "0.99.60") and not AT.ha_versao_nova(None, "1")
    assert AT.mais_nova("0.100.0", "0.99.99")
    assert loja.retirar("teste") and loja.info("teste") is None
    with pytest.raises(ValueError):
        loja.publicar(pac, "sem-versao.exe", "", "teste")
    with pytest.raises(ValueError):
        loja.info("beta")
    chamado = []
    assert AT.rodar_instalador(pac, popen=lambda args, **k: chamado.append(args))
    assert chamado[0][1:] == ["/SILENT", "/CLOSEAPPLICATIONS", "/NORESTART"]
    assert not AT.rodar_instalador(tmp_path / "x.zip", popen=lambda *a, **k: None)
    ruim = tmp_path / "ruim.exe"
    ruim.write_bytes(b"outro")
    with pytest.raises(ValueError):
        AT.conferir_pacote(ruim, d)


@pytest.fixture()
def central(env, sample_dir):
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    auth = LocalAuth(repo)
    auth.create_first_admin("admin", "Administrador", "admin123")
    repo.save_user({"username": "ana", "full_name": "Ana", "role": "residente", "password": "anaana123"})
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    yield paths, db, repo, srv
    srv.stop()


def test_pelo_servidor(central, tmp_path):
    paths, db, repo, srv = central
    repo.set_app_setting(PF.CHAVE, PERFIS)
    adm = RemoteClient(f"http://127.0.0.1:{srv.port}")
    adm.login("admin", "admin123")
    ana = RemoteClient(f"http://127.0.0.1:{srv.port}")
    ana.login("ana", "anaana123")
    p = ana.rpc("perfil_da_estacao", "SALA-MAMO1")
    assert p["nomes"] == ["Mamografia", "Teste"] and p["canal"] == "teste"
    assert adm.rpc("perfil_da_estacao", "TC-01")["nomes"] == []          # admin não é a "ana"
    # publicar (só quem gerencia usuários) e baixar
    pac = tmp_path / "Ipe-setup-0.99.61.exe"
    pac.write_bytes(b"MZ" + bytes(range(256)) * 4000)
    with pytest.raises(RemoteError):
        ana.publicar_atualizacao(pac, "", "teste")
    d = adm.publicar_atualizacao(pac, "", "teste", "corrige coisas")
    assert d["versao"] == "0.99.61" and d["tamanho"] == pac.stat().st_size
    assert ana.info_atualizacao("teste")["versao"] == "0.99.61" and ana.info_atualizacao("estavel") == {}
    passos = []
    arq = ana.baixar_atualizacao("teste", tmp_path / "baixado" / d["nome"], lambda f, t: passos.append((f, t)))
    assert arq.read_bytes() == pac.read_bytes() and passos[-1] == (pac.stat().st_size, pac.stat().st_size)
    AT.conferir_pacote(arq, d)
    with pytest.raises(RemoteError):
        ana.rpc("atualizacao_promover")
    assert adm.rpc("atualizacao_promover")["canal"] == "estavel"
    assert set(adm.rpc("atualizacoes_todas")) == {"estavel", "teste"}
    assert adm.rpc("atualizacao_retirar", "teste") is True
    assert any(a["action"] == "atualizacao" for a in repo.access_log(limit=50))


def test_telas(env, monkeypatch, tmp_path):
    from ipe.ui.perfis_dialog import AtualizacoesDialog, PerfisDialog, _Local
    paths, db, repo = env
    QApplication.instance() or QApplication([])
    st = Settings(paths.settings_file)
    st.set("viewer.invert_mg", True)
    d = PerfisDialog(repo, st)
    d._novo()
    d.nome.setText("Sala de mamo")
    d.computadores.setText("SALA-MAMO*")
    d.canal.setCurrentIndex(d.canal.findData("teste"))
    assert d._capturar(["viewer"]) == 1
    d.valores.item(0, 2).setCheckState(d.valores.item(0, 2).checkState().__class__.Checked)
    d._salvar()
    salvos = repo.get_app_setting(PF.CHAVE)
    assert salvos[0]["nome"] == "Sala de mamo" and salvos[0]["canal"] == "teste"
    assert salvos[0]["valores"]["viewer"]["invert_mg"] is True and salvos[0]["forcados"] == ["viewer"]
    assert repo.perfil_da_estacao("SALA-MAMO3", "x", "y")["nomes"] == ["Sala de mamo"]
    loja = AT.Atualizacoes(tmp_path / "A")
    pac = tmp_path / "Ipe-setup-0.99.70.exe"
    pac.write_bytes(b"MZ")
    a = AtualizacoesDialog(_Local(loja, "Admin"))
    assert "nada publicado" in a.texto.text()
    assert a.publicar("teste", str(pac), "", "")["versao"] == "0.99.70"
    assert "0.99.70" in a.texto.text()
    a.promover()
    assert loja.info("estavel")["versao"] == "0.99.70"


def test_janela_procura_atualizacao(env, monkeypatch, tmp_path):
    from ipe import __version__
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file))
    try:
        assert w.procurar_atualizacao(silencioso=True) == ""              # sem servidor central
        pac = tmp_path / "Ipe-setup-9.0.0.exe"
        pac.write_bytes(b"MZ123")
        info = {"versao": "9.0.0", "nome": pac.name, "sha256": AT.sha256_de(pac), "notas": "n"}

        class Cli:
            def info_atualizacao(self, canal):
                assert canal == "teste"
                return info

            def baixar_atualizacao(self, canal, dest, progress=None):
                Path(dest).parent.mkdir(parents=True, exist_ok=True)
                Path(dest).write_bytes(pac.read_bytes())
                return Path(dest)
        w._central = (None, type("R", (), {"client": Cli()})(), None)
        w._perfil = {"canal": "teste"}
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
        assert w.procurar_atualizacao(silencioso=True) == "adiada"
        assert w.procurar_atualizacao(silencioso=True) == "adiada"         # não pergunta de novo a mesma
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
        rodou = []
        monkeypatch.setattr(AT, "rodar_instalador", lambda arq, popen=None: rodou.append(arq) or True)
        monkeypatch.setattr(w, "quit_app", lambda: None)
        assert w.procurar_atualizacao(silencioso=False) == "instalando" and rodou[0].name == pac.name
        assert __version__ != "9.0.0"
    finally:
        w._central = None
        w.close()
