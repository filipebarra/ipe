"""A fila dos filmes parados: por que cada um não saiu, e quando dá para soltar em lote."""

import pytest

from ipe.core.config import Settings
from ipe.printing import config as C
from ipe.printing import held as H
from ipe.printing import origins as O
from ipe.printing import rules as R



@pytest.fixture()
def cfg(env):
    paths, _db, _repo = env
    s = Settings(paths.settings_file)
    s.set("printing.hold_unknown_origin", True)
    return s


def linha(uid="j1", ae="CT1", host="10.0.0.7", server="TC", status="new", **kw):
    base = {"uid": uid, "calling_ae": ae, "remote_host": host, "server": server,
            "status": status, "source": "scp", "sheets": 2, "images": 8,
            "received_at": "2026-09-20 08:00", "folder": ""}
    base.update(kw)
    return base


def regra(cfg, destino="PDF", **kw):
    R.save_rules(cfg, [R.Rule(name="tudo", destination=destino, **kw)])


# ------------------------------------------------------------------ o que conta como parado
def test_parado_e_o_que_chegou_e_nao_saiu():
    linhas = [linha("a"), linha("b", status="sent"), linha("c", status="error"),
              linha("d", source="film")]
    assert [r["uid"] for r in H.held(linhas)] == ["a"]


def test_lista_vazia_nao_quebra():
    assert H.held(None) == [] and H.held([]) == []


# ------------------------------------------------------------------ o motivo
def test_origem_sem_cadastro_e_o_motivo_mais_comum(cfg):
    O.see(cfg, "CT1", "10.0.0.7", "TC", "2026-09-20")
    assert H.reason(cfg, linha()) == H.SEM_CADASTRO


def test_origem_desligada_tem_motivo_proprio(cfg):
    o, _ = O.see(cfg, "CT1", "10.0.0.7", "TC", "2026-09-20")
    o.name, o.enabled = "TC sala 1", False
    O.save_origins(cfg, [o])
    assert H.reason(cfg, linha()) == H.DESLIGADA


def test_cadastrada_mas_sem_regra_nao_e_a_mesma_coisa(cfg):
    o, _ = O.see(cfg, "CT1", "10.0.0.7", "TC", "2026-09-20")
    o.name = "TC sala 1"
    O.save_origins(cfg, [o])
    assert H.reason(cfg, linha()) == H.SEM_REGRA       # ninguém disse para onde mandar


def test_cadastrada_e_com_regra_fica_pronto(cfg):
    o, _ = O.see(cfg, "CT1", "10.0.0.7", "TC", "2026-09-20")
    o.name = "TC sala 1"
    O.save_origins(cfg, [o])
    regra(cfg)
    assert H.reason(cfg, linha()) == H.PRONTO


def test_destino_fixo_do_servidor_tambem_libera(cfg):
    o, _ = O.see(cfg, "CT1", "10.0.0.7", "TC", "2026-09-20")
    o.name = "TC sala 1"
    O.save_origins(cfg, [o])
    C.save_servers(cfg, [C.ServerConfig(name="TC", auto_destination="PDF")])
    assert H.reason(cfg, linha()) == H.PRONTO
    assert H.alvos(cfg, linha()) == [("PDF", "")]


# ------------------------------------------------------------------ agrupamento
def test_agrupa_por_aparelho_e_soma_folhas(cfg):
    O.see(cfg, "CT1", "10.0.0.7", "TC", "2026-09-20")
    O.see(cfg, "MG1", "10.0.0.9", "TC", "2026-09-20")
    linhas = [linha("a"), linha("b"), linha("c", ae="MG1", host="10.0.0.9", sheets=5)]
    gs = H.groups(cfg, linhas)
    assert len(gs) == 2
    maior = gs[0]
    assert maior.trabalhos == 2 and maior.folhas == 4 and maior.imagens == 16
    assert maior.calling_ae == "CT1" and not maior.cadastrada
    assert maior.desde() == "2026-09-20 08:00"


def test_o_que_da_para_soltar_vem_na_frente(cfg):
    o, _ = O.see(cfg, "CT1", "10.0.0.7", "TC", "2026-09-20")
    o.name = "TC sala 1"
    O.save_origins(cfg, [o])
    O.see(cfg, "MG1", "10.0.0.9", "TC", "2026-09-20")
    regra(cfg, origin=o.id)
    gs = H.groups(cfg, [linha("a", ae="MG1", host="10.0.0.9"), linha("b"), linha("c")])
    assert gs[0].calling_ae == "CT1" and gs[0].pode_liberar
    assert not gs[1].pode_liberar


def test_rotulo_usa_o_nome_quando_existe(cfg):
    o, _ = O.see(cfg, "CT1", "10.0.0.7", "TC", "2026-09-20")
    o.name = "TC sala 1"
    O.save_origins(cfg, [o])
    assert H.groups(cfg, [linha()])[0].label() == "TC sala 1 — 10.0.0.7"
    O.remove(cfg, o.id)
    assert "AE CT1" in H.groups(cfg, [linha()])[0].label()


# ------------------------------------------------------------------ liberação
def test_liberaveis_so_os_prontos_e_so_do_aparelho_pedido(cfg):
    o, _ = O.see(cfg, "CT1", "10.0.0.7", "TC", "2026-09-20")
    o.name = "TC sala 1"
    O.save_origins(cfg, [o])
    O.see(cfg, "MG1", "10.0.0.9", "TC", "2026-09-20")
    regra(cfg)
    linhas = [linha("a"), linha("b", ae="MG1", host="10.0.0.9")]
    assert [r["uid"] for r in H.releasable(cfg, linhas)] == ["a"]
    assert H.releasable(cfg, linhas, origin_id="nao|existe|") == []
    assert [r["uid"] for r in H.releasable(cfg, linhas, origin_id=o.id)] == ["a"]


def test_carregar_que_explode_nao_derruba_a_tela(cfg):
    """O motivo é informação; se o arquivo do trabalho sumiu, ainda assim a fila aparece."""
    O.see(cfg, "CT1", "10.0.0.7", "TC", "2026-09-20")

    def explode(_row):
        raise OSError("sumiu")

    gs = H.groups(cfg, [linha()], explode)
    assert len(gs) == 1 and gs[0].trabalhos == 1


def test_resumo_conta_os_dois_estados(cfg):
    o, _ = O.see(cfg, "CT1", "10.0.0.7", "TC", "2026-09-20")
    o.name = "TC sala 1"
    O.save_origins(cfg, [o])
    O.see(cfg, "MG1", "10.0.0.9", "TC", "2026-09-20")
    regra(cfg)
    texto = H.resumo(H.groups(cfg, [linha("a"), linha("b", ae="MG1", host="10.0.0.9")]))
    assert "1" in texto and "prontos" in texto and "cadastro" in texto
    assert H.resumo([]) == ""


# ------------------------------------------------------------------ a aba (0.34.1)
def _aba(env, cfg):
    from PySide6.QtWidgets import QApplication
    from ipe.ui.prints_tab import PrintsTab
    _paths, _db, repo = env
    QApplication.instance() or QApplication([])
    return PrintsTab(repo, cfg), repo


def test_botao_de_parados_esta_sempre_na_barra(env, cfg):
    """Botão que some quando a lista está vazia é botão que o usuário não acha —
    foi exatamente o que aconteceu na 0.31.1 com a aba de impressões inteira."""
    aba, _repo = _aba(env, cfg)
    assert aba.b_parados.isVisibleTo(aba)
    assert aba.b_parados.text() == "Parados…"


def test_a_faixa_nao_pode_ler_a_lista_da_vez_anterior(env, cfg):
    """`refresh()` montava a faixa antes de gravar `self.rows`: na primeira abertura a
    contagem saía da lista vazia e o aviso nunca aparecia."""
    aba, repo = _aba(env, cfg)
    O.see(cfg, "CT1", "10.0.0.7", "TC", "2026-09-20 08:00")
    repo.add_print_job(uid="j1", source="scp", calling_ae="CT1", remote_host="10.0.0.7",
                       server="TC", sheets=2, images=8, status="new", folder="")
    aba.refresh()
    assert aba.b_parados.text() == "Parados (1)…"     # contou já na primeira passada
    assert aba.faixa_origens.isVisibleTo(aba)


def test_filtro_de_parados_na_lista(env, cfg):
    aba, repo = _aba(env, cfg)
    repo.add_print_job(uid="j1", source="scp", calling_ae="CT1", status="new", folder="")
    repo.add_print_job(uid="j2", source="scp", calling_ae="CT1", status="sent", folder="")
    aba.tipo.setCurrentIndex([aba.tipo.itemData(i) for i in range(aba.tipo.count())].index("held"))
    aba.refresh()
    assert [r["uid"] for r in aba.rows] == ["j1"]


def test_janela_de_parados_abre_vazia_sem_quebrar(env, cfg):
    """Sem nada parado a janela ainda abre e diz que não há nada — em vez de sumir."""
    from ipe.ui.held_dialog import HeldDialog
    dlg = HeldDialog(cfg, [])
    assert dlg.tabela.rowCount() == 0
    assert "Nenhum filme parado" in dlg.resumo.text()
    assert not dlg.b_todos.isEnabled()


def _janela(env):
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    paths, _db, _repo = env
    QApplication.instance() or QApplication([])
    return MainWindow(paths, Settings(paths.settings_file))


def test_aba_de_impressoes_fecha_e_reabre(env):
    """O X da aba existia e não fazia nada: `_close_tab` saía calado em tudo que não fosse
    aba de exame. Clique que não faz nada é o pior defeito possível."""
    janela = _janela(env)
    aba = janela.show_prints()
    assert janela.tabs.indexOf(aba) > 0
    janela._close_tab(janela.tabs.indexOf(aba))
    assert janela.tabs.indexOf(aba) < 0                 # saiu
    assert janela.tabs.currentWidget() is janela.browser
    de_novo = janela.show_prints()
    assert de_novo is aba and janela.tabs.indexOf(aba) > 0   # a mesma aba voltou


def test_banco_de_dados_nao_fecha(env):
    janela = _janela(env)
    janela._close_tab(janela.tabs.indexOf(janela.browser))
    assert janela.tabs.indexOf(janela.browser) == 0
