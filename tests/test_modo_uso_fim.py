"""0.99.36: fecha o plano do modo de uso e das configurações pessoais e compartilhadas.

- regras de automação com dono (Todos / Só eu / com escolhidos), o que a regra baixa vai para o banco
  certo e o anterior herda o banco do exame atual;
- Referências da cefalometria e dos índices do crânio: só minhas ou de todos deste computador;
- a chamada externa não abre o banco pessoal de outro usuário;
- as listas de casos vão junto com os exames entre este computador e o servidor central;
- no modo cliente, o exame novo baixado do PACS respeita "o meu banco neste computador".
"""
import pytest
from PySide6.QtWidgets import QApplication

from ipe.auth import session as S
from ipe.auth import visibilidade as V

SENHA = "uma senha comprida"


@pytest.fixture(autouse=True)
def _sessao_volta():
    antes = S.get()
    yield
    S.set_current(antes)


def entra(nome, papel="medico"):
    from ipe.auth.permissions import permissions_for
    S.set_current(S.UserSession(username=nome, full_name=nome, role=papel, perms=permissions_for(papel)))


# ------------------------------------------------------------------ regras de automação
def test_regras_de_automacao_tem_dono(env):
    _paths, _db, repo = env
    servico = repo.save_rule({"kind": "query", "name": "Do serviço", "config": {"x": 1}})
    da_ana = repo.save_rule({"kind": "query", "name": "Da Ana", "config": {"x": 2}, "dono": "ana"})
    com_bia = repo.save_rule({"kind": "route", "name": "Ana e Bia", "config": {}, "dono": "ana",
                              "visivel_para": "bia"})
    # o motor da automação recebe todas; a tela, só as visíveis
    assert len(repo.rules()) == 3
    entra("bia")
    assert {r["name"] for r in repo.rules(visiveis=True)} == {"Do serviço", "Ana e Bia"}
    entra("ana")
    assert {r["name"] for r in repo.rules(visiveis=True)} == {"Do serviço", "Da Ana", "Ana e Bia"}
    assert repo.rule(da_ana)["dono"] == "ana" and repo.rule(da_ana)["config"]["x"] == 2
    # editar a regra (sem mandar o dono) não perde o dono
    repo.save_rule({"id": da_ana, "config": {"x": 3}})
    assert repo.rule(da_ana)["dono"] == "ana" and repo.rule(da_ana)["config"]["x"] == 3
    # quem vê: só o dono (ou o administrador); pôr para todos pede configurar
    entra("bia")
    with pytest.raises(PermissionError, match="outro usuário"):
        repo.escopo_da_regra(da_ana, "", "")
    entra("ana")
    with pytest.raises(PermissionError, match="configurar"):
        repo.escopo_da_regra(da_ana, "", "")
    repo.escopo_da_regra(da_ana, "ana", "bia")
    assert repo.rule(da_ana)["visivel_para"] == "bia"
    entra("adm", "admin")
    assert len(repo.rules(visiveis=True, gerenciar=True)) == 3
    repo.escopo_da_regra(da_ana, "", "")                 # o administrador põe para todos
    assert repo.rule(da_ana)["dono"] == "" and repo.rule(servico)["dono"] == ""
    assert repo.rule(com_bia)["kind"] == "route"


def test_tela_da_automacao_mostra_e_grava_o_dono(env, monkeypatch):
    from ipe.ui.automation_dialog import AutomationDialog, RouteRuleDialog
    QApplication.instance() or QApplication([])
    paths, _db, repo = env
    repo.save_rule({"kind": "route", "name": "Do serviço", "config": {}})
    repo.save_rule({"kind": "route", "name": "Da Bia", "config": {}, "dono": "bia"})
    entra("ana")

    class _Auto:
        policy = {}

        class changed:  # noqa: N801
            @staticmethod
            def connect(_f):
                pass

    class _Main:
        def __init__(self):
            from ipe.core.config import Settings
            self.repo, self.auto = repo, _Auto()
            self.settings = Settings(paths.settings_file)
            self.settings.set("auth.mode", "multi")
    monkeypatch.setattr(AutomationDialog, "_clean_tab", lambda self: __import__("PySide6.QtWidgets").QtWidgets.QWidget())
    monkeypatch.setattr(AutomationDialog, "_history_tab", lambda self: __import__("PySide6.QtWidgets").QtWidgets.QWidget())
    d = AutomationDialog(_Main())
    t = d.t_route
    nomes = [t.item(r, 0).text() for r in range(t.rowCount())]
    assert nomes == ["Do serviço"]                        # a da Bia não aparece para a Ana
    assert t.horizontalHeaderItem(t.columnCount() - 1).text() == "Visível para"
    # regra nova da Ana: pessoal (ela não configura)
    dlg = RouteRuleDialog(repo, None, d)
    assert not dlg.visivel.isHidden() and dlg.visivel.valor() == {"dono": "ana", "visivel_para": ""}
    r = dlg.result_rule()
    assert r["dono"] == "ana"
    d.close()


def test_busca_e_anteriores_vao_para_o_banco_certo(env, monkeypatch):
    """O que a regra baixa ia para o banco de quem estivesse logado; agora: compartilhado, ou o banco do
    dono quando a regra pessoal pede; e o anterior herda o banco do exame atual."""
    from ipe.network.service import NetworkService
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    from ipe.core.config import Settings
    st = Settings(paths.settings_file)
    st.set("browser.novos_no_banco", "meu")              # a preferência de quem está logado
    net = NetworkService(db, repo, paths.storage, st)
    monkeypatch.setattr(net, "_submit", lambda job: None)
    entra("ana")
    j = net.retrieve({"id": 1}, None, "1.2.3", "x")
    assert j.novo and j.dono_destino == "ana"            # a mão: a preferência de quem pediu
    j = net.retrieve({"id": 1}, None, "1.2.4", "x", banco=("", ""))
    assert j.dono_destino == ""                          # regra do serviço: compartilhado
    j = net.retrieve({"id": 1}, None, "1.2.5", "x", banco=("bia", "ana"))
    assert (j.dono_destino, j.visivel_destino) == ("bia", "ana")
    from ipe.db import banco as B
    assert B.banco_de({"dono": "bia", "visivel_para": "ana"}) == ("bia", "ana")
    net.stop() if hasattr(net, "stop") else None


# ------------------------------------------------------------------ Referências
def test_referencias_so_minhas_ou_de_todos(env):
    from ipe.ai import cefalometria as CF
    from ipe.core.config import Settings
    paths, _db, _repo = env
    st = Settings(paths.settings_file)
    st.attach_user({})
    chave = CF.CHAVE_REFERENCIAS
    k = CF.ORDEM[0] if hasattr(CF, "ORDEM") else next(iter(CF.REFERENCIAS))
    st.set_do_computador(chave, {k: "do serviço"})
    assert CF.referencias(st)[k] == "do serviço"
    st.set(chave, {k: "só minha"})                      # camada do usuário, por cima
    assert CF.referencias(st)[k] == "só minha" and st.tem_pessoal(chave)
    assert st.do_computador(chave)[k] == "do serviço"
    outro = Settings(paths.settings_file)
    outro.data = st.data
    outro.attach_user({})
    assert CF.referencias(outro)[k] == "do serviço"      # o outro usuário vê a do computador
    st.set_do_computador(chave, {k: "nova de todos"})    # de todos: tira a pessoal de quem gravou
    assert not st.tem_pessoal(chave) and CF.referencias(st)[k] == "nova de todos"


# ------------------------------------------------------------------ chamada externa
def test_chamada_externa_nao_abre_o_banco_de_outro(env, sample_dir, monkeypatch):
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        st = repo.search_studies(banco="todos")[0]
        repo.set_study_scope([st.study_uid], "bia")
        abertos = []
        monkeypatch.setattr(w, "abrir_exame_do_pedido", lambda uid, *_a: abertos.append(uid))
        buscou = []
        monkeypatch.setattr(w.net, "search", lambda *a, **k: buscou.append(a))
        entra("ana")
        assert w.handle_external({"command": "open", "study_uid": st.study_uid}) == "sem_permissao"
        assert not abertos and not buscou                # nem abre, nem vai buscar no PACS
        entra("bia")
        assert w.handle_external({"command": "open", "study_uid": st.study_uid}) == "aberto"
        entra("adm", "admin")
        assert w.handle_external({"command": "open", "study_uid": st.study_uid}) == "aberto"
        assert abertos == [st.study_uid, st.study_uid]
    finally:
        w._really_quit = True
        w.settings.set("ui.confirmar_sair", False)
        w.close()


# ------------------------------------------------------------------ listas de casos viajam
def test_listas_vao_e_voltam_com_os_exames(env, sample_dir, tmp_path):
    from ipe.caselists import viagem as VG
    from ipe.central import transferir as T
    from ipe.central.client_repo import ClientRepository
    from ipe.central.remote import RemoteClient
    from ipe.central.server import CentralServer
    from ipe.db.repository import Repository
    from ipe.db.session import Database
    from ipe.importer.scanner import Importer
    from ipe.auth.backend import LocalAuth
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    LocalAuth(repo).create_first_admin("adm", "Administrador", SENHA)
    repo.save_user({"username": "ana", "full_name": "Ana", "role": "medico", "password": SENHA})
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    try:
        ana = RemoteClient(f"http://127.0.0.1:{srv.port}")
        ana.login("ana", SENHA)
        uids = [r.study_uid for r in repo.search_studies(banco="todos")][:2]
        # no servidor: pasta "Ensino" / lista "Aula de mama", com os dois casos
        pasta = repo.create_case_list("Ensino", kind="folder")
        aula = repo.create_case_list("Aula de mama", parent=pasta, description="para R2")
        repo.add_to_case_list(aula, uids[0], "Caso 1", clinical_summary="nódulo palpável")
        repo.add_to_case_list(aula, uids[1], "Caso 2")
        # trazer um exame para este computador: a lista vem junto, só com ele
        cache_db = Database(tmp_path / "cache.sqlite")
        cliente = ClientRepository(Repository(cache_db), ana, tmp_path / "cache")
        aqui_db = Database(tmp_path / "aqui.sqlite")
        aqui = Repository(aqui_db)
        r = T.trazer(cliente, [uids[0]], aqui_db, tmp_path / "aqui", "ana")
        assert r.exames == 1 and "1 caso(s)" in r.listas, (r.listas, r.erros)
        arv = {d["name"]: d for d in aqui.case_list_tree()}
        assert {"Ensino", "Aula de mama"} <= set(arv) and arv["Aula de mama"]["parent"] == arv["Ensino"]["id"]
        itens = aqui.list_items(arv["Aula de mama"]["id"])
        assert [(i["study_uid"], i["friendly_name"], i["clinical_summary"]) for i in itens] == \
            [(uids[0], "Caso 1", "nódulo palpável")]
        # trazer de novo não duplica lista nem caso
        r = T.trazer(cliente, [uids[0]], aqui_db, tmp_path / "aqui", "ana")
        assert len([d for d in aqui.case_list_tree() if d["name"] == "Aula de mama"]) == 1
        assert len(aqui.list_items(arv["Aula de mama"]["id"])) == 1
        # aqui, a Ana cria a lista "Revisar" e põe o caso; ao enviar, a lista nasce no servidor
        rev = aqui.create_case_list("Revisar")
        aqui.add_to_case_list(rev, uids[0], "Rever margem")
        r = T.enviar(ana, aqui, [uids[0]], False, "ana")
        assert r.exames == 1 and "1 caso(s)" in r.listas, (r.listas, r.erros)
        no_srv = {d["name"]: d for d in repo.case_list_tree()}
        assert "Revisar" in no_srv
        assert [i["friendly_name"] for i in repo.list_items(no_srv["Revisar"]["id"])] == ["Rever margem"]
        assert len(repo.list_items(aula)) == 2                # a lista do servidor não perde nada
        # pertencimentos ignora listas inteligentes e listas sem o exame
        repo.create_case_list("Inteligente", kind="smart", smart_query='{"modality": "CT"}')
        assert {tuple(x["caminho"]) for x in VG.pertencimentos(repo, [uids[1]])} == {("Ensino", "Aula de mama")}
        cache_db.close()
        aqui_db.close()
    finally:
        srv.stop()


# ------------------------------------------------------------------ modo cliente: baixado do PACS
def test_baixado_no_cliente_fica_neste_computador(monkeypatch):
    """No modo cliente com "o meu banco neste computador", o exame novo baixado do PACS não sobe ao
    servidor; o que está aberto numa aba espera a aba fechar."""
    from types import SimpleNamespace as NS
    from ipe.ui.main_window import MainWindow
    cache = object()
    feitos = []
    tab = NS(study_order=["aberto"])
    w = NS(_central=(None, cache, None), repo=cache,
           settings=NS(get=lambda k, d=None: {"central.mode": "client", "browser.novos_no_banco": "computador"}.get(k, d)),
           all_viewer_tabs=lambda: [tab], browser=NS(refresh=lambda: None),
           statusBar=lambda: NS(showMessage=lambda *a: None))
    w._novos_para_este_computador = lambda uids: (feitos.append(set(uids)), set(uids))[1]
    job = NS(novo=True, study_uids=["livre"], open_after=False, opened=False)
    assert MainWindow._baixados_para_este_computador(w, job) == {"livre"} and feitos == [{"livre"}]
    job = NS(novo=True, study_uids=["aberto"], open_after=False, opened=False)
    assert MainWindow._baixados_para_este_computador(w, job) == {"aberto"}     # não sobe, mas espera
    assert feitos == [{"livre"}] and w._pendentes_este_computador == {"aberto"}
    tab.study_order = []                                                       # a aba fechou
    MainWindow._levar_pendentes_para_este_computador(w)
    assert feitos[-1] == {"aberto"} and not w._pendentes_este_computador
    # exame que já estava no banco, ou fora do modo cliente: sobe como sempre
    assert MainWindow._baixados_para_este_computador(w, NS(novo=False, study_uids=["x"], open_after=False,
                                                           opened=False)) == set()


def test_janela_pessoais_e_compartilhadas_tem_as_regras(env):
    from ipe.core.config import Settings
    from ipe.ui.config_niveis import ConfigNiveisDialog
    QApplication.instance() or QApplication([])
    paths, _db, repo = env
    repo.save_rule({"kind": "query", "name": "Mamografias do dia", "active": True, "config": {"x": 1}})
    entra("ana")
    d = ConfigNiveisDialog(repo, Settings(paths.settings_file))
    t = d.tabelas["automacao"]
    assert [t.item(r, 0).text() for r in range(t.rowCount())] == ["Busca agendada: Mamografias do dia"]
    t.selectRow(0)
    assert d.copiar("automacao")                          # cópia pessoal, pausada
    minha = next(r for r in repo.rules() if r["dono"] == "ana")
    assert minha["name"] == "Mamografias do dia (minha)" and not minha["active"] and minha["config"]["x"] == 1
    # sem a permissão de configurar, tirar a do serviço de todos é recusado (com aviso, sem quebrar)
    from PySide6.QtWidgets import QMessageBox
    avisos = []
    import pytest as _pt
    mp = _pt.MonkeyPatch()
    mp.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: avisos.append(a[2])))
    try:
        linha = next(r for r in range(t.rowCount()) if t.item(r, 0).text() == "Busca agendada: Mamografias do dia")
        t.selectRow(linha)
        assert not d.mudar("automacao", "eu") and "configurar" in avisos[-1]
    finally:
        mp.undo()
    d.close()
