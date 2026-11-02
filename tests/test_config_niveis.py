"""0.99.30: configurações em três níveis — do serviço, compartilhadas com escolhidos, pessoais.

Fecha o plano do modo de uso: protocolos de exibição, de mamografia, layouts da dinâmica, modelos de
folha e de laudo, e as listas de casos.
"""
import pytest
from PySide6.QtWidgets import QApplication

from ipe.auth import session as S
from ipe.auth import visibilidade as V
from ipe.core import itens as IT

SENHA = "uma senha comprida"


@pytest.fixture(autouse=True)
def _sessao_volta():
    antes = S.get()
    yield
    S.set_current(antes)


def entra(nome, papel="medico"):
    from ipe.auth.permissions import permissions_for
    S.set_current(S.UserSession(username=nome, full_name=nome, role=papel, perms=permissions_for(papel)))


P = lambda nome, x=1, **k: {"name": nome, "x": x, **k}  # noqa: E731


# ------------------------------------------------------------------ regras
def test_quem_edita_o_que():
    ana, adm = V.Visao("ana"), V.Visao("adm", admin=True)
    g = [P("TC", dono=""), P("RM", dono="")]
    # médico sem configurar muda um do serviço: vira cópia pessoal; o do serviço fica
    lista, avisos = IT.juntar("hanging_protocols", g, [P("TC", 2), P("RM")], ana, pode_servico=False)
    assert {(x["name"], x["dono"], x["x"]) for x in lista} == {("TC", "ana", 2), ("TC", "", 1), ("RM", "", 1)}
    assert "cópia só sua" in avisos[0]
    assert [x["x"] for x in IT.visiveis("hanging_protocols", lista, ana) if x["name"] == "TC"] == [2]
    assert [x["x"] for x in IT.visiveis("hanging_protocols", lista, V.Visao("bia")) if x["name"] == "TC"] == [1]
    # novo: pessoal para o médico, do serviço para o administrador
    lista, _ = IT.juntar("hanging_protocols", g, [*g, P("PET")], ana, False)
    assert next(x for x in lista if x["name"] == "PET")["dono"] == "ana"
    lista, _ = IT.juntar("hanging_protocols", g, [*g, P("PET")], adm, True)
    assert next(x for x in lista if x["name"] == "PET")["dono"] == ""
    # apagar o do serviço sem permissão: fica
    lista, avisos = IT.juntar("hanging_protocols", g, [P("TC")], ana, False)
    assert {x["name"] for x in lista} == {"TC", "RM"} and "não foi apagado" in avisos[0]
    # com a permissão de configurar muda o do serviço mesmo
    lista, _ = IT.juntar("hanging_protocols", g, [P("TC", 5), P("RM")], ana, True)
    assert [(x["dono"], x["x"]) for x in lista if x["name"] == "TC"] == [("", 5)]
    # o que a Bia tem não some quando a Ana grava
    g2 = [*g, P("Bia", dono="bia")]
    lista, _ = IT.juntar("hanging_protocols", g2, [P("TC"), P("RM")], ana, False)
    assert any(x["name"] == "Bia" for x in lista)
    # mudar quem vê
    with pytest.raises(PermissionError):
        IT.mudar_escopo("hanging_protocols", g2, "Bia", "bia", "", "", ana, True)
    with pytest.raises(PermissionError, match="configurar"):
        IT.mudar_escopo("hanging_protocols", [dict(x) for x in g], "TC", "", "", "", ana, False)
    out = IT.mudar_escopo("hanging_protocols", [dict(x) for x in g2], "Bia", "bia", "bia", "ana", adm, True)
    assert next(x for x in out if x["name"] == "Bia")["visivel_para"] == "ana"


# ------------------------------------------------------------------ settings + banco
def test_protocolo_da_ana_nao_muda_o_da_bia_e_migracao(env):
    from ipe.core.config import Settings
    paths, _db, repo = env
    cfg = Settings(paths.settings_file)
    cfg.set("hanging_protocols", [P("TC"), P("RM")])          # o do computador (antes dos usuários)
    entra("ana")
    cfg.attach_user({"hanging_protocols": [P("TC"), P("RM", 9), P("Meu")]}, lambda p: None)
    migr = cfg.attach_itens(IT.Armazem(repo, cfg.data))
    assert migr == {"hanging_protocols": 2}                    # RM mudado e "Meu"; TC igual ao do serviço
    assert "hanging_protocols" not in cfg.user
    vistos = {x["name"]: x["x"] for x in cfg.get("hanging_protocols")}
    assert vistos == {"TC": 1, "RM": 9, "Meu": 1}
    assert all("dono" not in x for x in cfg.get("hanging_protocols"))   # quem usa não vê os campos
    cfg.set("hanging_protocols", [P("TC", 3), P("RM", 9), P("Meu")])     # médico: TC vira cópia dele
    entra("bia")
    cfg.attach_user({}, lambda p: None)
    cfg.attach_itens(IT.Armazem(repo, cfg.data))
    assert {x["name"]: x["x"] for x in cfg.get("hanging_protocols")} == {"TC": 1, "RM": 1}
    assert cfg.data["hanging_protocols"] == [P("TC"), P("RM")]          # o settings.json não mudou


def test_modelos_de_laudo_e_listas(env):
    paths, _db, repo = env
    entra("ana")
    base = repo.report_templates()
    repo.save_report_templates([*base, {"id": "x", "name": "Meu modelo", "modalities": ["CT"]}])
    assert any(t["name"] == "Meu modelo" for t in repo.report_templates())
    entra("bia")
    assert not any(t["name"] == "Meu modelo" for t in repo.report_templates())
    # listas
    entra("ana")
    lid = repo.create_case_list("Casos da Ana")
    entra("adm", "admin")
    comum = repo.create_case_list("Reunião do serviço")
    entra("bia")
    nomes = {d["name"] for d in repo.case_list_tree()}
    assert "Casos da Ana" not in nomes and "Reunião do serviço" in nomes
    with pytest.raises(PermissionError):
        repo.escopo_da_lista(lid, "")
    with pytest.raises(PermissionError, match="configurar"):
        repo.escopo_da_lista(comum, "bia")
    entra("ana")
    assert repo.escopo_da_lista(lid, "ana", "bia") == 1
    entra("bia")
    assert "Casos da Ana" in {d["name"] for d in repo.case_list_tree()}
    entra("adm", "admin")
    assert "Casos da Ana" in {d["name"] for d in repo.case_list_tree(gerenciar=True)}


def test_servidor_nao_entrega_a_lista_pessoal_de_outro(env, sample_dir):
    from ipe.auth.backend import LocalAuth
    from ipe.central.remote import RemoteClient, RemoteError
    from ipe.central.server import CentralServer
    paths, db, repo = env
    LocalAuth(repo).create_first_admin("adm", "Adm", SENHA)
    for n in ("ana", "bia"):
        repo.save_user({"username": n, "full_name": n, "role": "medico", "password": SENHA})
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    try:
        cli = {}
        for n in ("ana", "bia"):
            cli[n] = RemoteClient(f"http://127.0.0.1:{srv.port}")
            cli[n].login(n, SENHA)
        lid = cli["ana"].rpc("create_case_list", "Só da Ana")
        assert repo.case_list_info(lid)["dono"] == "ana"
        assert lid not in {d["id"] for d in cli["bia"].rpc("case_list_tree")}
        assert lid not in {d["id"] for d in cli["bia"].rpc("case_list_tree", gerenciar=True)}
        with pytest.raises(RemoteError, match="pessoal"):
            cli["bia"].rpc("list_items", lid)
        with pytest.raises(RemoteError, match="pessoal"):
            cli["bia"].rpc("delete_case_list", lid)
        # protocolos pelo servidor: a Ana grava; a Bia não vê o dela
        cli["ana"].rpc("salvar_itens_de_config", "hanging_protocols", [P("TC"), P("Meu")], [P("TC")])
        assert {x["name"] for x in cli["bia"].rpc("itens_de_config", "hanging_protocols")} == {"TC"}
        assert {x["name"] for x in cli["bia"].rpc("itens_de_config", "hanging_protocols", gerenciar=True)} == {"TC"}
    finally:
        srv.stop()


# ------------------------------------------------------------------ tela
def test_janela_pessoais_e_compartilhadas(env, monkeypatch):
    from ipe.core.config import Settings
    from ipe.ui.config_niveis import ConfigNiveisDialog
    QApplication.instance() or QApplication([])
    paths, _db, repo = env
    avisos = []
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.information", lambda *a, **k: avisos.append(a[2]))
    cfg = Settings(paths.settings_file)
    entra("ana")
    cfg.attach_user({}, lambda p: None)
    cfg.attach_itens(IT.Armazem(repo, cfg.data))
    d = ConfigNiveisDialog(repo, cfg)
    tab = d.tabelas["hanging_protocols"]
    assert tab.rowCount() >= 1 and tab.item(0, 1).text() == "Todos"
    tab.selectRow(0)
    nome = tab.item(0, 0).text()
    assert not d.mudar("hanging_protocols", "eu")              # médico não tira do serviço
    assert "configurar" in avisos[-1]
    assert d.copiar("hanging_protocols")                       # mas copia para si
    rotulos = {(tab.item(r, 0).text(), tab.item(r, 1).text()) for r in range(tab.rowCount())}
    assert (nome, "Só eu") in rotulos and (nome, "Todos") in rotulos
    assert sum(1 for x in cfg.get("hanging_protocols") if x["name"] == nome) == 1     # o meu toma o lugar
    # listas de casos
    lid = repo.create_case_list("Minha lista")
    d.recarregar("listas")
    t2 = d.tabelas["listas"]
    r = next(i for i in range(t2.rowCount()) if t2.item(i, 0).text() == "Minha lista")
    assert t2.item(r, 1).text() == "Só eu"
    t2.selectRow(r)
    monkeypatch.setattr("ipe.ui.visivel_para.EscolherUsuarios.exec", lambda self: 1)
    monkeypatch.setattr("ipe.ui.visivel_para.EscolherUsuarios.escolhidos", lambda self: ["bia"])
    assert d.mudar("listas", "escolher")
    assert repo.case_list_info(lid)["visivel_para"] == "bia"
