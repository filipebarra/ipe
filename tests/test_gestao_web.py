"""0.100.63: a Gestão DICOM no Ipê Web — o servidor confere as modalidades contra o PACS e manda o que falta, a
pedido do navegador de um administrador. Rede de verdade em loopback (a clínica do test_gestao)."""
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_gestao import clinica  # noqa: E402,F401

from ipe.central import gestao_web as GW  # noqa: E402
from ipe.network.client import DicomClient, Target  # noqa: E402

ADMIN = SimpleNamespace(role="admin", username="chefe", perms=set())
MEDICO = SimpleNamespace(role="medico", username="dra", perms={"query", "send"})


class Prefs(dict):
    def set(self, k, v):
        self[k] = v

    def save(self):
        self["_salvo"] = self.get("_salvo", 0) + 1


@pytest.fixture()
def servidor(clinica):
    """O servidor é "este computador" da clínica, com a modalidade e o PACS cadastrados e a identidade OSIRIX."""
    eu, mod, pacs = clinica["eu"], clinica["mod"], clinica["pacs"]
    ids = {}
    for nome, no in (("mod", mod), ("pacs", pacs)):
        d = no.como_no(use_in_send=nome == "pacs")
        d.pop("id")
        ids[nome] = eu.repo.save_node(d)
    ids["osirix"] = eu.repo.save_identity({"name": "OsiriX da sala", "ae_title": "OSIRIX", "allowed_nodes": ""})
    net = SimpleNamespace(client=DicomClient(timeout=10), sink=eu.sink, local_ae=eu.ae,
                          target=lambda no, ident=None: Target.build(no, eu.ae, ident),
                          identities_for=lambda no: eu.repo.identities(todos=True))
    c = SimpleNamespace(repo=eu.repo, settings=Prefs(), net=net)
    return SimpleNamespace(c=c, ids=ids, clinica=clinica)


def _esperar(c, s=40):
    fim = time.time() + s
    while time.time() < fim:
        e = GW.estado(c, ADMIN)
        if not e["ocupado"]:
            return e
        time.sleep(0.05)
    raise AssertionError("a operação não terminou")


def _pedido(srv, **kw):
    ids = srv.ids
    corpo = {"fontes": [{"no": ids["mod"], "ident": ids["osirix"], "on": True}, {"no": ids["pacs"], "on": False}],
             "pacs": {"no": ids["pacs"]}, "periodo": "datas", "de": "20261009", "ate": "20261009",
             "ignorar": "patient protocol", "modo": "auto"}
    corpo.update(kw)
    return corpo


def test_so_administrador(servidor):
    c = servidor.c
    for fn, args in ((GW.nos, ()), (GW.estado, ()), (GW.conferir, ({},)), (GW.enviar, ({},)), (GW.parar, ()),
                     (GW.eco, ({},)), (GW.reconferir, ({},)), (GW.limpar_fila, ())):
        with pytest.raises(PermissionError):
            fn(c, MEDICO, *args)
    with pytest.raises(PermissionError):
        GW.rota(c, MEDICO, "GET", "nos", {}, {})
    with pytest.raises(LookupError):
        GW.rota(c, ADMIN, "POST", "apagar_tudo", {}, {})
    sem_rede = SimpleNamespace(repo=c.repo, settings=None, net=None)
    with pytest.raises(RuntimeError):
        GW.nos(sem_rede, ADMIN)


def test_nos_do_servidor_todos_e_eco(servidor):
    c, ids = servidor.c, servidor.ids
    r = GW.nos(c, ADMIN)
    # todos os DIMSE ativos do servidor — sem depender do "compartilhar com os clientes"
    assert {n["nome"] for n in r["nos"]} == {"MR01", "PACS"} and r["local_ae"] == "DICOMVIEWER"
    assert all(not c.repo.node(n["id"]).get("compartilhar_clientes") for n in r["nos"])
    assert [i["ae"] for i in r["nos"][0]["identidades"]] == ["OSIRIX"]
    assert [d["nome"] for d in r["destinos"]] == ["PACS"]
    assert {m["k"] for m in r["modos"]} == {"auto", "direto", "computador"} and r["periodos"][0]["k"] == "hoje"
    # a modalidade só aceita o OSIRIX: o eco diz
    assert GW.eco(c, ADMIN, {"no": ids["mod"], "ident": ids["osirix"]})["ok"]
    ruim = GW.eco(c, ADMIN, {"no": ids["mod"]})
    assert not ruim["ok"] and ruim["mensagem"]
    assert GW.eco(c, ADMIN, {"no": ids["pacs"]})["ok"]
    with pytest.raises(KeyError):
        GW.eco(c, ADMIN, {"no": 9999})


def test_conferir_enviar_o_que_falta_e_fila(servidor):
    c, ids, cl = servidor.c, servidor.ids, servidor.clinica
    assert GW.estado(c, ADMIN)["linhas"] == [] and GW.estado(c, ADMIN)["resumo"] == ""
    with pytest.raises(ValueError):
        GW.conferir(c, ADMIN, _pedido(servidor, pacs=None))
    with pytest.raises(ValueError):
        GW.conferir(c, ADMIN, _pedido(servidor, fontes=[{"no": ids["pacs"], "on": True}]))
    with pytest.raises(ValueError):
        GW.enviar(c, ADMIN, {"chaves": ["x"]})                       # sem conferência
    r = GW.conferir(c, ADMIN, _pedido(servidor), "10.0.0.5")
    assert r["ocupado"] == "conferindo"
    e = _esperar(c)
    por = {x["accession"]: x for x in e["linhas"]}
    assert set(por) == {"A1", "B1", "C1"} and not e["erros"]
    assert por["A1"]["situacao"] == "completo" and not por["A1"]["problema"]
    b = por["B1"]
    assert b["situacao"] == "incompleto" and b["series_txt"] == "3 / 2" and b["imagens_txt"] == "9 / 6"
    assert {s["descricao"]: s["situacao"] for s in b["series"]} == {"T1": "ok", "FLAIR": "incompleta", "DWI": "falta"}
    assert por["C1"]["situacao"] == "ausente" and por["C1"]["paciente"]
    assert e["resumo"].startswith("3 exame(s)") and "1 incompleto(s)" in e["resumo"] and "1 ausente(s) no PACS" in e["resumo"]
    assert e["pacs"] == "PACS" and e["quem"] == "chefe" and e["periodo"] == ["20261009", "20261009"]
    # o estado só volta inteiro quando muda
    assert GW.estado(c, ADMIN, e["v"]) == {"v": e["v"], "igual": True}
    assert GW.rota(c, ADMIN, "GET", "estado", {"v": [str(e["v"] - 1)]}, {})["linhas"]
    # as escolhas ficam guardadas no mesmo lugar da janela do Ipê de mesa
    cfg = c.settings["gestao"]
    assert cfg["pacs"] == ids["pacs"] and cfg["fontes"][str(ids["mod"])] == {"on": True, "ident": ids["osirix"]}
    assert cfg["fontes"][str(ids["pacs"])]["on"] is False and cfg["ignorar"] == "patient protocol"
    assert GW.nos(c, ADMIN)["cfg"]["periodo"] == "datas"
    # enviar o que falta: só os com problema entram; o completo marcado junto fica de fora
    antes_b = cl["pacs"].n_imagens(cl["b"]["uid"])
    r = GW.enviar(c, ADMIN, {"chaves": [por["A1"]["k"], b["k"], por["C1"]["k"], "nada|1.2"]}, "10.0.0.5", espera=0.2)
    assert r["ocupado"] == "enviando" and len(r["fila"]) == 2 and r["fila"][1]["estado"] == "fila"
    with pytest.raises(ValueError):
        GW.conferir(c, ADMIN, _pedido(servidor))                     # uma operação por vez
    e = _esperar(c)
    por = {x["accession"]: x for x in e["linhas"]}
    assert por["B1"]["situacao"] == "completo" and por["C1"]["situacao"] == "completo", (por["B1"], por["C1"])
    assert cl["pacs"].n_imagens(cl["b"]["uid"]) == 9 > antes_b
    assert cl["pacs"].n_imagens(cl["c"]["uid"]) == 2                 # a série ignorada não foi
    assert [f["estado"] for f in e["fila"]] == ["ok", "ok"] and all(f["destino"] == "PACS" for f in e["fila"])
    assert "2 exame(s)" in e["mensagem"]
    aud = [a for a in c.repo.audit_entries(50) if "navegador" in str(a)]
    assert len(aud) >= 3 and any("chefe" in str(a) for a in aud)
    # nada mais a enviar; a fila limpa
    with pytest.raises(ValueError):
        GW.enviar(c, ADMIN, {"chaves": [por["B1"]["k"]]})
    assert GW.limpar_fila(c, ADMIN)["fila"] == []
    # conferir de novo um exame
    r = GW.reconferir(c, ADMIN, {"chaves": [por["A1"]["k"]]})
    assert _esperar(c)["linhas"][0]["situacao"] == "completo"


def test_enviar_o_exame_inteiro_para_outro_destino(servidor):
    c, cl = servidor.c, servidor.clinica
    GW.conferir(c, ADMIN, _pedido(servidor))
    e = _esperar(c)
    a = next(x for x in e["linhas"] if x["accession"] == "A1")
    with pytest.raises(KeyError):
        GW.enviar(c, ADMIN, {"chaves": [a["k"]], "para": {"no": servidor.ids["mod"]}})     # não é destino de envio
    GW.enviar(c, ADMIN, {"chaves": [a["k"]], "para": {"no": servidor.ids["pacs"]}}, espera=0.1)
    e = _esperar(c)
    assert e["fila"][-1]["estado"] == "nada" and "já estava completo em PACS" in e["fila"][-1]["resultado"]
    a = next(x for x in e["linhas"] if x["accession"] == "A1")
    assert a["envio"].startswith("→ PACS: já estava completo")
    assert cl["pacs"].n_imagens(cl["a"]["uid"]) == 5


def test_no_que_nao_responde_nao_derruba_e_parar(servidor):
    c, ids = servidor.c, servidor.ids
    # sem a identidade a modalidade recusa: o erro aparece, sem linhas
    GW.conferir(c, ADMIN, _pedido(servidor, fontes=[{"no": ids["mod"], "on": True}]))
    e = _esperar(c)
    assert e["linhas"] == [] and "MR01" in e["erros"] and e["resumo"] == "Nenhum exame conferido."
    assert GW.parar(c, ADMIN)["ocupado"] == ""


def test_no_navegador(servidor):
    """A tela inteira: só o administrador vê o botão; conferir, abrir as séries, marcar os com problema, enviar o
    que falta (com a confirmação), a fila e o CSV."""
    from ipe.central import web as WEB
    if not WEB.site_instalado():
        pytest.skip("site não construído")
    pw = pytest.importorskip("playwright.sync_api")
    from ipe.auth.backend import LocalAuth
    from ipe.central.server import CentralServer
    cl, eu = servidor.clinica, servidor.clinica["eu"]
    LocalAuth(eu.repo).create_first_admin("admin", "Administrador", "admin123")
    eu.repo.save_user({"username": "dra", "full_name": "Dra. Teste", "role": "medico", "password": "medico123"})
    srv = CentralServer(eu.db, eu.repo, eu.storage, port=0, host="127.0.0.1")
    srv.net, srv.settings = servidor.c.net, servidor.c.settings
    srv.start()
    erros = []
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1500, "height": 950})
            pg.on("pageerror", lambda e: erros.append(str(e)))
            pg.on("dialog", lambda d: d.accept())

            def entrar(usuario, senha):
                pg.goto(f"http://127.0.0.1:{srv.port}/web/")
                pg.fill("#usuario", usuario)
                pg.fill("#senha", senha)
                pg.click("button[type=submit]")
                pg.wait_for_selector("form.filtros")
            entrar("dra", "medico123")
            assert pg.locator("button.gestao-abrir").is_hidden()
            pg.goto(f"http://127.0.0.1:{srv.port}/web/#/gestao")           # pelo endereço: o servidor recusa
            pg.wait_for_selector(".tela-gestao .erro")
            assert "administradores" in pg.inner_text(".tela-gestao .erro")
            pg.evaluate("() => { sessionStorage.clear(); localStorage.clear(); }")
            pg.goto("about:blank")
            entrar("admin", "admin123")
            pg.click("button.gestao-abrir")
            pg.wait_for_selector(".gestao-fontes tbody tr")
            assert pg.locator(".gestao-fontes tbody tr").count() == 2
            linha_mod = pg.locator(".gestao-fontes tbody tr", has_text="MR01")
            linha_mod.locator("input[type=checkbox]").check()
            linha_mod.locator("button", has_text="Testar").click()                # como o servidor: a modalidade recusa
            pg.wait_for_selector(".gestao-fontes .eco.ruim")
            linha_mod.locator("select").select_option(label="OsiriX da sala (OSIRIX)")
            linha_mod.locator("button", has_text="Testar").click()
            pg.wait_for_selector(".gestao-fontes .eco.ok")
            pg.select_option("select[aria-label='PACS']", label=pg.locator("select[aria-label='PACS'] option", has_text="PACS").first.inner_text())
            pg.select_option("select[aria-label='Período']", "datas")
            pg.fill("input[title='De']", "2026-10-09")
            pg.fill("input[title='Até']", "2026-10-09")
            pg.fill("input[aria-label='Ignorar séries']", "patient protocol")
            pg.click("button:has-text('Conferir')")
            pg.wait_for_selector(".gestao-exames tr[data-acc='C1']", timeout=30000)
            pg.wait_for_function("() => window.__ipeGestao.estado() && !window.__ipeGestao.estado().ocupado")
            assert pg.locator(".gestao-exames tbody tr[data-acc]").count() == 3
            assert "3 exame(s)" in pg.inner_text(".gestao-resumo") and "PACS" in pg.inner_text(".gestao-resumo")
            assert "Incompleto" in pg.inner_text(".gestao-exames tr[data-acc='B1']")
            assert pg.locator(".gestao-exames tr.sit-completo").count() == 1
            # as séries do exame incompleto
            pg.click(".gestao-exames tr[data-acc='B1'] td.detalhe")
            assert pg.locator(".gestao-series tbody tr").count() == 3
            assert pg.locator(".gestao-series tr.ser-falta").count() == 1 and "DWI" in pg.inner_text(".gestao-series tr.ser-falta")
            # só os com problema; marcar e mandar o que falta
            pg.select_option("select[aria-label='Mostrar']", "1")
            assert pg.locator(".gestao-exames tbody tr[data-acc]").count() == 2
            assert pg.locator("button:has-text('Enviar o que falta') >> nth=0").is_disabled()
            pg.click("button:has-text('Marcar os com problema')")
            assert len(pg.evaluate("() => window.__ipeGestao.marcadas()")) == 2
            csv = pg.evaluate("() => window.__ipeGestao.csv()")
            assert csv.count("\r\n") == 2 and '"B1"' in csv and '"A1"' not in csv
            pg.click("button:has-text('Enviar o que falta') >> nth=0")
            pg.wait_for_selector(".gestao-fila tbody tr")
            pg.wait_for_function("() => { const e = window.__ipeGestao.estado(); return e && !e.ocupado && e.fila.length === 2; }",
                                 timeout=60000)
            pg.wait_for_function("() => document.querySelectorAll('.gestao-fila tr.fila-ok').length === 2")
            pg.select_option("select[aria-label='Mostrar']", "")
            pg.wait_for_function("() => document.querySelectorAll('.gestao-exames tr.sit-completo').length === 3")
            assert cl["pacs"].n_imagens(cl["b"]["uid"]) == 9 and cl["pacs"].n_imagens(cl["c"]["uid"]) == 2
            import os
            if os.environ.get("IPE_GESTAO_FOTO"):
                pg.click(".gestao-exames tr[data-acc='B1'] td.detalhe") if not pg.locator(".gestao-series").count() else None
                pg.screenshot(path=os.environ["IPE_GESTAO_FOTO"], full_page=True)
            # recarregar a página: o estado está no servidor
            pg.reload()
            entrar("admin", "admin123") if pg.locator("#usuario").count() else None
            pg.goto(f"http://127.0.0.1:{srv.port}/web/#/gestao")
            pg.wait_for_selector(".gestao-exames tr[data-acc='B1']")
            assert pg.locator(".gestao-fila tbody tr").count() == 2
            assert pg.locator(".gestao-fontes tbody tr", has_text="MR01").locator("input[type=checkbox]").is_checked()
            pg.click("button:has-text('Limpar os terminados')")
            pg.wait_for_function("() => document.querySelector('.gestao-fila').hidden")
            b.close()
    finally:
        srv.stop()
    assert not erros, erros
