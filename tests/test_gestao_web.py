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
            pg.click(".gestao-cfg button.primario")
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


# ---------------------------------------------------------------------- 0.100.65: a aba Automático
class MotorDeMentira:
    """Faz o que o motor da automação faz com a regra (roda `GA.executar`, grava o relatório e o histórico)."""

    def __init__(self, c, eu):
        self.c, self.eu, self.rodando = c, eu, set()

    def gestao_em_curso(self, rid):
        return rid in self.rodando

    def rodar_gestao(self, regra, manual=False):
        import threading
        from datetime import date, datetime

        from ipe.network import gestao_auto as GA
        rid = regra["id"]
        if rid in self.rodando:
            return False
        self.rodando.add(rid)
        inicio = datetime.now()

        def trabalho():
            rel = GA.executar(regra, self.c.repo, self.c.net.client, self.c.net.target, sink=self.c.net.sink,
                              hoje=date(2026, 10, 9), espera=0.2)
            cfg = dict(self.c.repo.rule(rid)["config"])
            cfg["_ultimo"] = rel.para_dict()
            self.c.repo.save_rule({"id": rid, "config": cfg, "last_run": inicio})
            self.c.repo.add_job_run("gestao", regra["name"], {"ok": "ok", "erro": "error", "offline": "offline"}[rel.situacao],
                                    len(rel.enviados), rel.resumo(), rid, inicio)
            self.rodando.discard(rid)
        threading.Thread(target=trabalho, daemon=True).start()
        return True


def _cfg_regra(ids, **kw):
    cfg = {"fontes": [{"node_id": ids["mod"], "identity_id": ids["osirix"]}],
           "destino": {"node_id": ids["pacs"], "identity_id": None}, "periodo": "hoje", "ignorar": "patient protocol",
           "envio": "falta", "modo": "auto",
           "schedule": {"type": "interval", "minutes": 30, "from": "07:00", "to": "20:00", "weekdays": [0, 1, 2, 3, 4]},
           "repetir": {"minutos": 10, "vezes": 2}}
    cfg.update(kw)
    return cfg


def test_regras_automaticas(servidor):
    from ipe.network import gestao_auto as GA
    c, ids, cl = servidor.c, servidor.ids, servidor.clinica
    for fn in (GW.regras, ):
        with pytest.raises(PermissionError):
            fn(c, MEDICO)
    for fn in (GW.regra_gravar, GW.regra_ligar, GW.regra_excluir, GW.regra_duplicar, GW.regra_rodar):
        with pytest.raises(PermissionError):
            fn(c, MEDICO, {})
    r = GW.regras(c, ADMIN)
    assert r["regras"] == [] and r["motor"] is False and r["dias"][0] == "Seg" and r["envios"]["falta"]
    # as exigências da janela
    for corpo, msg in (({"nome": "", "cfg": _cfg_regra(ids)}, "nome"),
                       ({"nome": "x", "cfg": _cfg_regra(ids, fontes=[])}, "modalidade"),
                       ({"nome": "x", "cfg": _cfg_regra(ids, destino={})}, "destino"),
                       ({"nome": "x", "cfg": _cfg_regra(ids, destino={"node_id": ids["mod"]})}, "destino não pode"),
                       ({"nome": "x", "cfg": _cfg_regra(ids, schedule={"type": "daily", "at": "06:00", "weekdays": []})}, "dia")):
        with pytest.raises(ValueError, match=msg):
            GW.regra_gravar(c, ADMIN, corpo)
    r = GW.regra_gravar(c, ADMIN, {"nome": "RM no PACS", "ativa": True, "cfg": _cfg_regra(ids, minutos_a_mais=1)}, "10.0.0.5")
    rid = r["id"]
    regra = c.repo.rule(rid)
    assert regra["kind"] == GA.TIPO and regra["active"] and regra["next_run"] is not None
    assert "minutos_a_mais" not in regra["config"] and regra["config"]["schedule"]["minutes"] == 30
    linha = r["regras"][0]
    assert linha["nome"] == "RM no PACS" and linha["ativa"] and linha["destino"] == "PACS" and linha["mandar"] == "Só o que falta"
    assert linha["quando"] == "a cada 30 min, 07:00–20:00 (Seg a Sex)" and linha["texto"] == "ainda não rodou" and linha["ultimo"] is None
    assert linha["cfg"]["fontes"] == [{"node_id": ids["mod"], "identity_id": ids["osirix"]}]
    # sem o motor da automação, rodar agora diz o porquê
    with pytest.raises(RuntimeError):
        GW.regra_rodar(c, ADMIN, {"id": rid})
    c.auto = MotorDeMentira(c, cl["eu"])
    assert GW.regras(c, ADMIN)["motor"] is True
    r = GW.regra_rodar(c, ADMIN, {"id": rid}, "10.0.0.5")
    fim = time.time() + 60
    while c.auto.gestao_em_curso(rid) and time.time() < fim:
        time.sleep(0.05)
    r = GW.rota(c, ADMIN, "GET", "regras", {}, {})
    linha = r["regras"][0]
    assert linha["situacao"] == "ok" and linha["simbolo"] == "✔" and "2 completado(s) agora" in linha["texto"]
    assert sorted(x["accession"] for x in linha["ultimo"]["enviados"]) == ["B1", "C1"] and linha["ultimo"]["inicio_txt"]
    assert r["historico"][0]["regra"] == "RM no PACS" and r["historico"][0]["estado"] == "ok"
    assert cl["pacs"].n_imagens(cl["b"]["uid"]) == 9
    # editar guarda o último relatório; desligar; duplicar (desligada, sem o relatório); excluir
    r = GW.regra_gravar(c, ADMIN, {"id": rid, "nome": "RM no PACS (dia)", "ativa": True,
                                   "cfg": _cfg_regra(ids, schedule={"type": "daily", "at": "25:99", "weekdays": [6, 0]})})
    regra = c.repo.rule(rid)
    assert regra["name"] == "RM no PACS (dia)" and regra["config"]["_ultimo"]["situacao"] == "ok"
    assert regra["config"]["schedule"] == {"type": "daily", "at": "06:00", "weekdays": [0, 6]}
    assert r["regras"][0]["quando"] == "diariamente às 06:00 (Seg, Dom)"
    assert GW.regra_ligar(c, ADMIN, {"id": rid, "on": False})["regras"][0]["proxima"] == "desligada"
    r = GW.regra_duplicar(c, ADMIN, {"id": rid})
    copia = next(x for x in r["regras"] if x["id"] == r["id"])
    assert copia["nome"] == "RM no PACS (dia) (cópia)" and not copia["ativa"] and copia["ultimo"] is None
    assert len(GW.regra_excluir(c, ADMIN, {"id": copia["id"]})["regras"]) == 1
    with pytest.raises(KeyError):
        GW.regra_excluir(c, ADMIN, {"id": 99999})
    aud = [str(a) for a in c.repo.audit_entries(80)]
    assert any("regra automática criada (navegador): RM no PACS" in a for a in aud)
    assert any("rodada agora" in a for a in aud) and any("excluída" in a for a in aud)


def test_aba_automatico_no_navegador(servidor):
    """Criar uma regra, rodar agora, ver o relatório e o histórico, desligar, duplicar e excluir."""
    from ipe.central import web as WEB
    if not WEB.site_instalado():
        pytest.skip("site não construído")
    pw = pytest.importorskip("playwright.sync_api")
    import os

    from ipe.auth.backend import LocalAuth
    from ipe.central.server import CentralServer
    cl, eu = servidor.clinica, servidor.clinica["eu"]
    LocalAuth(eu.repo).create_first_admin("admin", "Administrador", "admin123")
    srv = CentralServer(eu.db, eu.repo, eu.storage, port=0, host="127.0.0.1")
    srv.net, srv.settings = servidor.c.net, servidor.c.settings
    srv.auto = MotorDeMentira(srv, eu)
    srv.ponte = None                                   # no teste não há laço de eventos na linha principal
    srv.start()
    erros = []
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1500, "height": 1000})
            pg.on("pageerror", lambda e: erros.append(str(e)))
            pg.on("dialog", lambda d: d.accept())
            pg.goto(f"http://127.0.0.1:{srv.port}/web/")
            pg.fill("#usuario", "admin")
            pg.fill("#senha", "admin123")
            pg.click("button[type=submit]")
            pg.wait_for_selector("form.filtros")
            pg.click("button.gestao-abrir")
            pg.wait_for_selector(".gestao-abas")
            pg.click(".gestao-abas button:has-text('Automático')")
            pg.wait_for_selector(".gestao-regras td.vazio")
            assert pg.locator(".gestao-aba >> nth=0").is_hidden()
            pg.click("button:has-text('Nova regra…')")
            pg.wait_for_selector(".gestao-editor h3")
            # as exigências aparecem no próprio editor
            pg.click("button:has-text('Salvar a regra')")
            pg.wait_for_function("() => document.querySelector('.gestao-editor .erro').textContent.length > 0")
            assert "nome" in pg.inner_text(".gestao-editor .erro")
            pg.fill("input[aria-label='Nome da regra']", "RM no PACS")
            linha = pg.locator(".gestao-editor .gestao-fontes tbody tr", has_text="MR01")
            linha.locator("input[type=checkbox]").check()
            linha.locator("select").select_option(label="OsiriX da sala (OSIRIX)")
            pg.select_option(".gestao-editor select[aria-label='Destino']", label=pg.locator(".gestao-editor select[aria-label='Destino'] option", has_text="PACS").first.inner_text())
            pg.fill(".gestao-editor input[aria-label='Ignorar séries']", "patient protocol")
            pg.fill(".gestao-editor input[aria-label='Minutos']", "30")
            pg.click("button:has-text('Salvar a regra')")
            pg.wait_for_selector(".gestao-regras tr.regra")
            assert pg.locator(".gestao-editor").is_hidden()
            txt = pg.inner_text(".gestao-regras tr.regra")
            assert "RM no PACS" in txt and "a cada 30 min" in txt and "ainda não rodou" in txt and "PACS" in txt
            regra = eu.repo.rules("gestao")[0]
            assert regra["active"] and regra["config"]["fontes"][0]["identity_id"] == servidor.ids["osirix"]
            assert regra["config"]["schedule"]["weekdays"] == [0, 1, 2, 3, 4, 5] and regra["config"]["repetir"]["vezes"] == 3
            # rodar agora: o relatório e o histórico
            pg.click("button:has-text('Rodar agora')")
            pg.wait_for_function("() => document.querySelector('.gestao-regras tr.regra.sit-ok')", timeout=60000)
            assert "2 completado(s) agora" in pg.inner_text(".gestao-regras tr.regra")
            assert "Completados agora (2)" in pg.inner_text(".gestao-relatorio")
            pg.wait_for_selector(".gestao-hist tbody tr")
            assert "RM no PACS" in pg.inner_text(".gestao-hist tbody tr >> nth=0")
            assert cl["pacs"].n_imagens(cl["b"]["uid"]) == 9
            if os.environ.get("IPE_GESTAO_FOTO"):
                pg.screenshot(path=os.environ["IPE_GESTAO_FOTO"].replace(".png", "_auto.png"), full_page=True)
                pg.click("button:has-text('Editar…')")
                pg.wait_for_selector(".gestao-editor h3")
                pg.screenshot(path=os.environ["IPE_GESTAO_FOTO"].replace(".png", "_editor.png"), full_page=True)
                pg.click(".gestao-editor button:has-text('Cancelar')")
            # editar: os valores voltam ao editor
            pg.click("button:has-text('Editar…')")
            pg.wait_for_selector(".gestao-editor h3")
            assert pg.input_value("input[aria-label='Nome da regra']") == "RM no PACS"
            assert pg.input_value(".gestao-editor input[aria-label='Minutos']") == "30"
            assert pg.locator(".gestao-editor .gestao-fontes tbody tr", has_text="MR01").locator("input[type=checkbox]").is_checked()
            pg.check(".gestao-editor input[value='daily']")
            pg.click("button:has-text('Salvar a regra')")
            pg.wait_for_function("() => document.querySelector('.gestao-regras tr.regra').textContent.includes('diariamente')")
            assert eu.repo.rules("gestao")[0]["config"]["_ultimo"]["situacao"] == "ok"      # o relatório ficou
            # desligar, duplicar e excluir a cópia
            pg.uncheck(".gestao-regras tr.regra input[type=checkbox]")
            pg.wait_for_function("() => document.querySelector('.gestao-regras tr.regra').textContent.includes('desligada')")
            pg.click("button:has-text('Duplicar')")
            pg.wait_for_function("() => document.querySelectorAll('.gestao-regras tr.regra').length === 2")
            assert "(cópia)" in pg.inner_text(".gestao-regras tr.regra.escolhida")
            pg.click("button:has-text('Excluir')")
            pg.wait_for_function("() => document.querySelectorAll('.gestao-regras tr.regra').length === 1")
            # a outra aba continua lá
            pg.click(".gestao-abas button:has-text('Conferir agora')")
            assert pg.locator(".gestao-cfg >> nth=0").is_visible()
            b.close()
    finally:
        srv.stop()
    assert not erros, erros
