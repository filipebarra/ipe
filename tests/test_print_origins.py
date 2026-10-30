"""Cadastro de origens: quem mandou o trabalho, com nome que dá para usar em regra."""

import time

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.printing import config as C
from ipe.printing import dispatch as D
from ipe.printing import origins as O
from ipe.printing import rules as R
from ipe.printing.dicom_print import PageImage, PrinterConfig, dicom_print



def free_port() -> int:
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


def origem(ae="CT1", host="10.0.0.7", server="TC", nome="", **kw):
    return O.Origin(calling_ae=ae, remote_host=host, server=server, name=nome, **kw)


@pytest.fixture()
def cfg(env):
    paths, _db, _repo = env
    return Settings(paths.settings_file)


# ------------------------------------------------------------------ identidade
def test_identidade_e_ae_mais_endereco_mais_servidor():
    a = origem("CT1", "10.0.0.7", "TC")
    assert a.matches("ct1", "10.0.0.7", "TC")            # AE não diferencia maiúscula
    assert not a.matches("CT1", "10.0.0.8", "TC")        # outro endereço
    assert not a.matches("CT1", "10.0.0.7", "RM")        # outro servidor
    assert not a.matches("CT2", "10.0.0.7", "TC")


def test_endereco_alternativo_mantem_a_mesma_origem():
    a = origem("CT1", "10.0.0.7", "TC", nome="TC Sala 1", also_hosts=["10.0.0.9"])
    assert a.matches("CT1", "10.0.0.9", "TC")
    assert "10.0.0.9" in a.hosts()


def test_origem_sem_nome_nao_esta_cadastrada():
    assert not origem().registered
    assert origem(nome="TC Sala 1").registered


def test_nome_sugerido_a_partir_do_ae():
    assert O.suggest_name("CT_SALA2") == "CT Sala 2"
    assert O.suggest_name("mg-selenia") == "Mg Selenia"
    assert O.suggest_name("RM1") == "RM 1"
    assert O.suggest_name("") == ""


# ------------------------------------------------------------------ cadastro
def test_primeira_vez_entra_sem_nome_e_conta_os_trabalhos(cfg):
    o, nova = O.see(cfg, "CT1", "10.0.0.7", "TC")
    assert nova and not o.registered and o.jobs == 1
    o2, nova2 = O.see(cfg, "CT1", "10.0.0.7", "TC")
    assert not nova2 and o2.jobs == 2
    assert len(O.all_origins(cfg)) == 1
    assert [x.id for x in O.pending(cfg)] == [o.id]


def test_aparelho_diferente_vira_origem_diferente(cfg):
    O.see(cfg, "CT1", "10.0.0.7", "TC")
    O.see(cfg, "CT1", "10.0.0.8", "TC")                  # mesmo AE, outro IP
    O.see(cfg, "MG1", "10.0.0.7", "TC")
    assert len(O.all_origins(cfg)) == 3


def test_cadastrar_tira_da_lista_de_pendentes(cfg):
    O.see(cfg, "CT1", "10.0.0.7", "TC")
    todas = O.all_origins(cfg)
    todas[0].name = "TC Sala 1"
    O.save_origins(cfg, todas)
    assert O.pending(cfg) == []
    assert O.find(cfg, "CT1", "10.0.0.7", "TC").name == "TC Sala 1"


def test_mesmo_ae_de_outro_endereco_e_sinalizado(cfg):
    O.save_origins(cfg, [origem("CT1", "10.0.0.7", "TC", nome="TC Sala 1")])
    O.see(cfg, "CT1", "10.0.0.99", "TC")
    parecidas = O.same_ae_elsewhere(cfg, "CT1", "10.0.0.99", "TC")
    assert [p.name for p in parecidas] == ["TC Sala 1"]


def test_juntar_o_endereco_novo_na_origem_que_ja_existe(cfg):
    O.save_origins(cfg, [origem("CT1", "10.0.0.7", "TC", nome="TC Sala 1")])
    O.see(cfg, "CT1", "10.0.0.99", "TC")
    assert len(O.all_origins(cfg)) == 2
    alvo = O.find(cfg, "CT1", "10.0.0.7", "TC")
    assert O.merge_host(cfg, alvo.id, "10.0.0.99")
    assert len(O.all_origins(cfg)) == 1
    achada = O.find(cfg, "CT1", "10.0.0.99", "TC")
    assert achada is not None and achada.name == "TC Sala 1"


def test_esquecer_origem(cfg):
    O.see(cfg, "CT1", "10.0.0.7", "TC")
    ident = O.all_origins(cfg)[0].id
    assert O.remove(cfg, ident)
    assert O.all_origins(cfg) == []
    assert not O.remove(cfg, ident)


# ------------------------------------------------------------------ segurar
def test_trabalho_de_origem_nova_fica_esperando(cfg):
    linha = {"calling_ae": "CT1", "remote_host": "10.0.0.7", "server": "TC"}
    O.register_from_job(cfg, linha)
    pode, motivo = O.may_forward(cfg, linha)
    assert not pode and "não cadastrada" in motivo


def test_origem_cadastrada_libera(cfg):
    O.save_origins(cfg, [origem("CT1", "10.0.0.7", "TC", nome="TC Sala 1")])
    pode, motivo = O.may_forward(cfg, {"calling_ae": "CT1", "remote_host": "10.0.0.7",
                                       "server": "TC"})
    assert pode and motivo == ""


def test_origem_desligada_segura(cfg):
    O.save_origins(cfg, [origem("CT1", "10.0.0.7", "TC", nome="TC Sala 1", enabled=False)])
    pode, motivo = O.may_forward(cfg, {"calling_ae": "CT1", "remote_host": "10.0.0.7",
                                       "server": "TC"})
    assert not pode and "desligada" in motivo


def test_dá_para_desligar_a_espera(cfg):
    cfg.set("printing.hold_unknown_origin", False)
    pode, _m = O.may_forward(cfg, {"calling_ae": "NOVO", "remote_host": "1.2.3.4", "server": "X"})
    assert pode


# ------------------------------------------------------------------ regras por origem
def _job(ae="CT1", quando=None):
    from ipe.printing.jobs import PrintJob
    j = PrintJob(calling_ae=ae)
    j.received_at = (quando or "2026-09-22T10:00:00")
    return j


def test_regra_presa_a_uma_origem_so_combina_com_ela():
    r = R.Rule(name="TC", origin="CT1|10.0.0.7|TC", destination="PDF")
    assert R.matches(r, _job(), "TC", "CT1|10.0.0.7|TC")
    assert not R.matches(r, _job(), "TC", "CT1|10.0.0.8|TC")
    assert not R.matches(r, _job(), "TC", "")


def test_regra_sem_origem_continua_valendo_para_todas():
    r = R.Rule(name="Tudo", destination="PDF")
    assert R.matches(r, _job(), "TC", "CT1|10.0.0.7|TC")
    assert R.matches(r, _job(), "TC", "")


def test_choose_usa_a_origem(cfg):
    R.save_rules(cfg, [R.Rule(name="Só a sala 1", origin="CT1|10.0.0.7|TC", destination="PDF A"),
                       R.Rule(name="Resto", destination="PDF B")])
    assert R.choose(cfg, _job(), "TC", "CT1|10.0.0.7|TC") == [("PDF A", "")]
    assert R.choose(cfg, _job(), "TC", "CT1|10.0.0.8|TC") == [("PDF B", "")]


def test_texto_da_regra_mostra_o_nome_da_origem():
    r = R.Rule(name="TC", origin="CT1|10.0.0.7|TC", destination="PDF")
    assert "da origem TC Sala 1" in r.label_text("TC Sala 1")


# ------------------------------------------------------------------ recuperação
def test_backfill_monta_o_cadastro_do_que_ja_chegou(cfg):
    linhas = [{"calling_ae": "CT1", "remote_host": "10.0.0.7", "server": "TC",
               "received_at": "2026-09-01T08:00:00"},
              {"calling_ae": "CT1", "remote_host": "10.0.0.7", "server": "TC",
               "received_at": "2026-09-05T08:00:00"},
              {"calling_ae": "MG1", "remote_host": "10.0.0.9", "server": "TC",
               "received_at": "2026-09-03T08:00:00"}]
    assert O.backfill(cfg, linhas) == 2
    todas = {o.calling_ae: o for o in O.all_origins(cfg)}
    assert todas["CT1"].jobs == 2
    assert todas["CT1"].first_seen.startswith("2026-09-01")
    assert todas["CT1"].last_seen.startswith("2026-09-05")
    assert O.backfill(cfg, []) == 0


def test_backfill_nao_duplica_o_que_ja_esta_cadastrado(cfg):
    O.save_origins(cfg, [origem("CT1", "10.0.0.7", "TC", nome="TC Sala 1")])
    assert O.backfill(cfg, [{"calling_ae": "CT1", "remote_host": "10.0.0.7", "server": "TC"}]) == 0
    assert len(O.all_origins(cfg)) == 1
    assert O.all_origins(cfg)[0].name == "TC Sala 1"


# ------------------------------------------------------------------ ponta a ponta
def test_origem_nova_segura_e_depois_de_cadastrada_encaminha(env, tmp_path):
    """Chega de um aparelho desconhecido: fica parado. Cadastrada a origem, o próximo sai."""
    paths, _db, repo = env
    app = QApplication.instance() or QApplication([])
    settings = Settings(paths.settings_file)
    porta = free_port()
    pasta = tmp_path / "pdf-origem"
    C.save_servers(settings, [C.ServerConfig(name="Geral", enabled=True, ae_title="PRNGER",
                                             port=porta, to_database=False)])
    D.save_destinations(settings, [D.Destination(name="PDF", kind="pdf", folder=str(pasta),
                                                 dpi=72)])
    R.save_rules(settings, [R.Rule(name="Tudo", destination="PDF")])
    settings.set("dicom", dict(settings.get("dicom", {}), enabled=False, http_enabled=False))
    settings.save()
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, settings)
    w.start_services()
    try:
        px = np.full((100, 80), 60, np.uint8)
        impressora = PrinterConfig(name="p", ae_title="PRNGER", host="127.0.0.1", port=porta)
        assert dicom_print(impressora, [PageImage(pixels=px)], local_ae="CT_NOVO").pages == 1
        fim = time.monotonic() + 10
        while not repo.print_jobs() and time.monotonic() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert repo.print_jobs(), "o trabalho nem chegou"
        for _ in range(20):
            app.processEvents()
            time.sleep(0.05)
        assert not list(pasta.glob("*.pdf")), "encaminhou sem a origem estar cadastrada"
        assert repo.print_jobs()[0]["status"] == "new"

        vistas = O.all_origins(settings)
        assert len(vistas) == 1 and vistas[0].calling_ae == "CT_NOVO"
        assert not vistas[0].registered

        vistas[0].name = "TC novo"
        O.save_origins(settings, vistas)
        assert dicom_print(impressora, [PageImage(pixels=px)], local_ae="CT_NOVO").pages == 1
        fim = time.monotonic() + 15
        while not list(pasta.glob("*.pdf")) and time.monotonic() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert list(pasta.glob("*.pdf")), "não encaminhou com a origem cadastrada"
        assert O.all_origins(settings)[0].jobs == 2
    finally:
        w.net.shutdown()
        w.close()
