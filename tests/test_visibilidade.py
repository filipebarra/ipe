"""0.99.26: "Visível para" — nós DICOM, identidades, servidores e regras de impressão do serviço, pessoais
ou compartilhados com usuários escolhidos (etapa 2 do plano do modo de uso).

Decisões dele: o administrador vê o que é dos outros; o resto "faça o que achar melhor". Ficou: na tela
de configuração o administrador vê e edita tudo (marcado "de fulano"); nas escolhas do dia a dia cada um
vê o do serviço, o seu e o que compartilharam com ele.
"""
import pytest
from PySide6.QtWidgets import QApplication

from ipe.auth import session as S
from ipe.auth import visibilidade as V
from ipe.auth.session import UserSession


@pytest.fixture(autouse=True)
def _sessao_volta():
    antes = S.get()
    yield
    S.set_current(antes)


def entra(nome, papel="medico"):
    from ipe.auth.permissions import permissions_for
    S.set_current(UserSession(username=nome, full_name=nome, role=papel, perms=permissions_for(papel)))


def _no(repo, nome, dono="", outros=""):
    return repo.save_node({"name": nome, "kind": "dimse", "ae_title": nome[:16].upper(), "host": "10.0.0.1",
                           "port": 104, "active": True, "dono": dono, "visivel_para": outros})


# ------------------------------------------------------------------ regra
def test_quem_ve_o_que():
    ana, bia, adm = V.Visao("ana"), V.Visao("bia"), V.Visao("adm", admin=True)
    servico = {"dono": ""}
    da_ana = {"dono": "ana"}
    da_ana_com_bia = {"dono": "ana", "visivel_para": "bia"}
    assert all(V.visivel(servico, v) for v in (ana, bia, adm, None))
    assert V.visivel(da_ana, ana) and not V.visivel(da_ana, bia)
    assert V.visivel(da_ana_com_bia, bia) and V.visivel({"dono": "ANA"}, ana)          # sem diferença de maiúscula
    assert not V.visivel(da_ana, adm)                       # no dia a dia, o do outro não aparece para o admin
    assert V.visivel(da_ana, adm, gerenciar=True)           # na configuração, aparece
    assert not V.visivel(da_ana, bia, gerenciar=True)
    assert V.visivel(da_ana, None)                          # "só eu": tudo é de todos
    assert V.rotulo(servico, ana) == "Todos" and V.rotulo(da_ana, ana) == "Só eu"
    assert V.rotulo(da_ana_com_bia, ana) == "Eu + bia" and V.rotulo(da_ana, adm) == "de ana"
    assert V.padrao_novo(ana) == {"dono": "ana", "visivel_para": ""} and V.padrao_novo(adm)["dono"] == ""


def test_sessao_do_sistema_nao_filtra():
    S.set_current(UserSession())                            # "só eu" sem usuário
    assert V.visao_atual() is None


# ------------------------------------------------------------------ banco
def test_nos_filtrados_pela_sessao(env):
    _p, _db, repo = env
    _no(repo, "PACS"), _no(repo, "CASA ANA", "ana"), _no(repo, "ANA BIA", "ana", "bia"), _no(repo, "BIA", "bia")
    nomes = lambda **k: sorted(n["name"] for n in repo.nodes(**k))  # noqa: E731
    entra("ana")
    assert nomes() == ["ANA BIA", "CASA ANA", "PACS"]
    entra("bia")
    assert nomes() == ["ANA BIA", "BIA", "PACS"]
    entra("adm", "admin")
    assert nomes() == ["PACS"]
    assert nomes(gerenciar=True) == ["ANA BIA", "BIA", "CASA ANA", "PACS"]
    # quem trabalha pela máquina (nó que recebe, automação) vê todos, seja quem for o logado
    entra("bia")
    assert len(repo.nodes(todos=True)) == 4
    assert repo.node_by_ae("CASA ANA") is not None


def test_identidades_filtradas(env):
    _p, _db, repo = env
    repo.save_identity({"name": "WS mama", "ae_title": "WSMAMA", "dono": ""})
    repo.save_identity({"name": "Meu AE", "ae_title": "DRANA", "dono": "ana"})
    entra("bia")
    assert [i["name"] for i in repo.identities()] == ["WS mama"]
    entra("ana")
    assert sorted(i["name"] for i in repo.identities()) == ["Meu AE", "WS mama"]


def test_pedido_de_cliente_no_servidor_usa_a_visao_de_quem_pediu(env):
    """No servidor central cada pedido roda com a visão do cliente (com_visao), não com a de quem
    está logado na tela do servidor."""
    _p, _db, repo = env
    _no(repo, "PACS"), _no(repo, "CASA ANA", "ana")
    entra("adm", "admin")
    with V.com_visao(UserSession(username="ana", role="medico")):
        assert sorted(n["name"] for n in repo.nodes()) == ["CASA ANA", "PACS"]
    with V.com_visao(UserSession(username="bia", role="medico")):
        assert [n["name"] for n in repo.nodes()] == ["PACS"]
    assert [n["name"] for n in repo.nodes()] == ["PACS"]        # de volta à visão da tela (admin)
    import inspect

    from ipe.central import server as SV
    assert "com_visao" in inspect.getsource(SV.CentralServer.rpc)


# ------------------------------------------------------------------ telas
def test_campo_no_editor_do_no(env):
    from ipe.core.config import Settings
    from ipe.ui.network_dialog import NodeDialog
    QApplication.instance() or QApplication([])
    paths, _db, repo = env
    cfg = Settings(paths.settings_file)
    cfg.set("auth.mode", "multi")
    repo.save_user({"username": "bia", "full_name": "Bia", "role": "medico", "active": True,
                    "password": "uma senha comprida"})
    entra("ana")                                             # médico: não configura o computador
    d = NodeDialog(None, None, None, cfg, repo=repo)
    assert d.visivel.isVisibleTo(d)
    assert d.visivel.combo.currentData() == "eu"
    assert not d.visivel.combo.model().item(0).isEnabled()  # "Todos" é de quem configura
    d.name.setText("Casa")
    d.ae.setText("CASA")
    d.host.setText("10.1.1.1")
    d.visivel.outros = ["bia"]
    d.visivel.combo.setCurrentIndex(2)
    d._ok()
    assert d.data["dono"] == "ana" and d.data["visivel_para"] == "bia"
    # no modo "só eu" o campo some
    cfg.set("auth.mode", "single")
    d2 = NodeDialog(None, None, None, cfg, repo=repo)
    assert not d2.visivel.isVisibleTo(d2)


def test_meus_nos_sem_permissao_de_configurar(env, monkeypatch):
    from ipe.core.config import Settings
    from ipe.ui.network_dialog import NetworkDialog
    QApplication.instance() or QApplication([])
    paths, _db, repo = env
    _no(repo, "PACS"), _no(repo, "CASA ANA", "ana"), _no(repo, "BIA", "bia")
    entra("ana")
    d = NetworkDialog(Settings(paths.settings_file), repo, None, so_pessoal=True)
    nomes = sorted(d.t_nodes.item(r, 0).text() for r in range(d.t_nodes.rowCount()))
    assert nomes == ["CASA ANA", "PACS"]                   # o da Bia não aparece
    avisos = []
    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox.information", lambda *a, **k: avisos.append(a[2]))
    pacs = next(n for n in repo.nodes() if n["name"] == "PACS")
    assert not d.pode_mexer(pacs) and "do serviço" in avisos[-1]
    assert d.pode_mexer(next(n for n in repo.nodes() if n["name"] == "CASA ANA"))
    tabs = [d.findChildren(__import__("PySide6.QtWidgets", fromlist=["QTabWidget"]).QTabWidget)[0].tabText(i)
            for i in range(2)]
    assert "Este computador" not in tabs


def test_menu_de_nos_abre_para_quem_nao_configura(env):
    from ipe.ui import configuracoes as C
    item = next(x for nome, lista in C.CATALOGO for x in lista if x[0].startswith("Nós DICOM"))
    assert item[2] == "query"


def test_impressao_guarda_o_dono(env):
    from ipe.printing import config as PC
    from ipe.printing import rules as PR
    from ipe.printing import auto_film as AF
    s = PC.ServerConfig(name="Imp", dono="ana", visivel_para="bia")
    assert PC.ServerConfig.from_dict(s.to_dict()).dono == "ana"
    r = PR.Rule(name="R", dono="ana")
    assert PR.Rule.from_dict(r.to_dict()).dono == "ana"
    a = AF.AutoRule(name="A", visivel_para="bia")
    assert AF.AutoRule.from_dict(a.to_dict()).visivel_para == "bia"
