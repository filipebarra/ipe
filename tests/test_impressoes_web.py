"""0.100.68: Impressões e Painel de filmes no Ipê Web — a lista, a folha, identificar (OCR), enviar, reimprimir,
juntar, apagar, parados e o painel; só administradores e técnicos. Nomes inventados; nada de paciente real."""
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))

CABECALHO = "MOREIRA LUCIANA BEATRIZ PEREIRA  7781234\nVIBRANT  DFOV 36"
ESTUDOS = [{"study_uid": "1.2.3", "patient_name": "MOREIRA^LUCIANA BEATRIZ PEREIRA", "patient_id": "7781234",
            "when": None, "modalities": "MG", "description": "Mamografia"},
           {"study_uid": "1.2.4", "patient_name": "TAVARES^OTAVIO HENRIQUE", "patient_id": "5512090",
            "when": None, "modalities": "CT", "description": "TC"}]


@pytest.fixture()
def servidor(env, sample_dir, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from test_network import free_port
    from ipe.auth.backend import LocalAuth
    from ipe.central.server import CentralServer
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.network.service import NetworkService
    from ipe.printing import arrival as A
    from ipe.printing import config as C
    from ipe.printing import dispatch as D
    from ipe.printing import ocr
    from ipe.printing import origins as O
    from ipe.printing import rules as R
    from ipe.printing.dicom_print import PageImage, PrinterConfig, dicom_print
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    repo.save_user({"username": "tec", "full_name": "Técnica", "role": "tecnico", "password": "tecnico1"})
    repo.save_user({"username": "res", "full_name": "Residente", "role": "residente", "password": "resid123"})
    st = Settings(paths.settings_file)
    porta = free_port()
    C.save_servers(st, [C.ServerConfig(name="Mamografia", enabled=True, ae_title="PRNMG", port=porta,
                                       to_database=False)])
    D.save_destinations(st, [D.Destination(name="PDF", kind="pdf", folder=str(tmp_path / "pdf"), dpi=72),
                             D.Destination(name="Imagens", kind="images", folder=str(tmp_path / "img"), dpi=40)])
    R.save_rules(st, [R.Rule(name="Mamo", server="Mamografia", destination="PDF")])
    st.set("dicom", dict(st.get("dicom", {}), enabled=False, http_enabled=False))
    st.set("printing.hold_unknown_origin", False)
    st.set(A.CHAVE, True)                         # OCR na chegada ligado: sem paciente, o filme espera
    st.save()
    monkeypatch.setattr(ocr, "available", lambda: False)        # na chegada ninguém lê: os filmes ficam esperando
    net = NetworkService(db, repo, paths.storage, st)
    assert net.start_print_servers() == 1
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.settings, srv.net = st, net
    srv.start()

    def imprimir(n=1, valor=70, ae="MG_SELENIA"):
        antes = len(repo.print_jobs())
        pgs = [PageImage(pixels=np.full((120, 90), valor + 20 * i, np.uint8)) for i in range(n)]
        assert dicom_print(PrinterConfig(name="p", ae_title="PRNMG", host="127.0.0.1", port=porta), pgs,
                           local_ae=ae).pages == n
        assert _esperar(srv, lambda: len(repo.print_jobs()) > antes), "o trabalho não entrou na lista"
        return repo.print_jobs()[0]
    estudo = next(r for r in repo.search_studies() if r.accession == "ACC1001")
    serie = repo.series_for_study(estudo.study_uid)[0]
    insts = sorted(repo.instances_for_series(serie.series_uid), key=lambda i: i["instance_number"])
    srv.app, srv.repo_, srv.tmp, srv.imprimir, srv.st = app, repo, tmp_path, imprimir, st
    srv.estudo, srv.serie, srv.insts = estudo.study_uid, serie.series_uid, insts
    yield srv
    srv.stop()
    net.shutdown()


def _esperar(srv, cond, segundos=45):
    fim = time.monotonic() + segundos
    while not cond() and time.monotonic() < fim:
        srv.app.processEvents()
        time.sleep(0.03)
    return cond()


def _token(srv, u="admin", p="admin123"):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/login", method="POST",
                                 data=json.dumps({"username": u, "password": p}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())["token"]


def _api(srv, rota, corpo=None, tok=None, cru=False):
    """O pedido numa linha à parte; a principal gira o laço (o desenho das folhas roda nela)."""
    tok = tok or _token(srv)
    caixa = {}

    def ir():
        req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/web/impressoes/{rota}",
                                     method="POST" if corpo is not None else "GET",
                                     data=json.dumps(corpo).encode() if corpo is not None else None,
                                     headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        try:
            r = urllib.request.urlopen(req)
            caixa["r"] = (r.read(), r.headers.get("Content-Type"))
        except urllib.error.HTTPError as e:
            caixa["e"] = (e.code, e.read().decode("utf-8", "replace"))
    t = threading.Thread(target=ir)
    t.start()
    while t.is_alive():
        srv.app.processEvents()
        time.sleep(0.01)
    if "e" in caixa:
        raise AssertionError(caixa["e"])
    corpo_r, tipo = caixa["r"]
    return (corpo_r, tipo) if cru else json.loads(corpo_r)


def _erro(srv, rota, corpo=None, tok=None):
    try:
        _api(srv, rota, corpo, tok)
    except AssertionError as e:
        return e.args[0]
    return (200, "")


def _filme_montado(srv, nome="Filme do compositor"):
    cells = [{"study_uid": srv.estudo, "series_uid": srv.serie, "sop_uid": i["sop_uid"], "frame_index": 0,
              "width": 400, "level": 40} for i in srv.insts[:2]]
    dados = {"name": nome, "sheets": [{"rows": 1, "cols": 2, "paper": "A4", "landscape": True, "cells": cells}]}
    return srv.repo_.save_film(nome, dados, [srv.estudo], "FANTOMA^UM", user="admin")


# ---------------------------------------------------------------- quem pode
def test_so_administrador_e_tecnico(servidor):
    srv = servidor
    res = _token(srv, "res", "resid123")
    for rota, corpo in (("lista", None), ("painel", None), ("parados", None), ("folha?k=scp:1&i=0", None),
                        ("enviar", {"ks": ["scp:1"], "destino": "PDF"}), ("apagar", {"ks": ["scp:1"]}),
                        ("ocr", {"k": "scp:1"}), ("identificar", {"k": "scp:1", "nome": "X"})):
        assert _erro(srv, rota, corpo, res)[0] == 403, rota
    tec = _token(srv, "tec", "tecnico1")
    r = _api(srv, "lista", tok=tec)
    assert r["papel"] == "tecnico" and r["pode_apagar"] and r["linhas"] == []
    assert [d["nome"] for d in r["destinos"]] == ["PDF", "Imagens"]           # todos os do servidor
    assert _api(srv, "lista")["papel"] == "admin"
    assert _erro(srv, "nao_existe")[0] == 404 and _erro(srv, "nao_existe", {})[0] == 404


# ---------------------------------------------------------------- lista, folha, detalhes
def test_lista_folha_e_detalhes(servidor):
    srv = servidor
    srv.imprimir(2)
    fid = _filme_montado(srv)
    r = _api(srv, "lista")
    assert r["total"] == 2 and r["de"] == 2 and {x["kind"] for x in r["linhas"]} == {"scp", "film"}
    rec = next(x for x in r["linhas"] if x["kind"] == "scp")
    fil = next(x for x in r["linhas"] if x["kind"] == "film")
    assert rec["tipo"] == "Recebido" and rec["folhas"] == 2 and rec["situacao"] == "Esperando paciente"
    assert rec["pode_identificar"] and "MG_SELENIA" in rec["de_onde"] and rec["quando"]
    assert fil["k"] == f"film:{fid}" and fil["tipo"] == "Montado aqui" and fil["paciente"] == "FANTOMA^UM"
    assert fil["imagens"] == 2 and fil["de_onde"] == "compositor" and not fil["pode_identificar"]
    assert r["parados"] == 1 and any("confirmar o paciente" in f for f in r["faixa"])
    # filtros
    assert [x["kind"] for x in _api(srv, "lista?tipo=film")["linhas"]] == ["film"]
    assert [x["kind"] for x in _api(srv, "lista?tipo=held")["linhas"]] == ["scp"]
    assert _api(srv, "lista?q=fantoma")["total"] == 1 and _api(srv, "lista?q=zzz")["total"] == 0
    # a folha em PNG: do recebido (duas) e do montado
    for k, i in ((rec["k"], 0), (rec["k"], 1), (fil["k"], 0)):
        png, tipo = _api(srv, f"folha?k={k}&i={i}", cru=True)
        assert tipo == "image/png" and png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 300, (k, i)
    grande, _t = _api(srv, f"folha?k={fil['k']}&i=0&grande=1", cru=True)
    assert len(grande) > len(_api(srv, f"folha?k={fil['k']}&i=0", cru=True)[0])
    assert _erro(srv, f"folha?k={rec['k']}&i=9")[0] == 404 and _erro(srv, "folha?k=scp:999&i=0")[0] == 404
    d = _api(srv, f"detalhes?k={rec['k']}")
    assert d["folhas"] == 2 and any("Chegou de MG_SELENIA" in x for x in d["linhas"]) and d["envios"] == []
    assert any(x.startswith("Recebido em: Mamografia") for x in d["linhas"])
    d = _api(srv, f"detalhes?k={fil['k']}")
    assert d["folhas"] == 1 and d["titulo"] == "Filme do compositor" and "Montado no compositor" in d["linhas"]


# ---------------------------------------------------------------- enviar, histórico, reimprimir
def test_enviar_historico_e_reimprimir(servidor):
    srv = servidor
    srv.imprimir(1)
    fid = _filme_montado(srv)
    ks = [x["k"] for x in _api(srv, "lista")["linhas"]]
    tec = _token(srv, "tec", "tecnico1")
    assert _api(srv, "reimprimir", {"ks": ks})["n"] == 0                       # nunca saíram: nada a repetir
    r = _api(srv, "enviar", {"ks": ks, "destino": "PDF"}, tok=tec)
    assert r["ok"] == 2 and r["falhas"] == 0 and "2 trabalho(s) enviados" in r["mensagem"]
    assert len(list((srv.tmp / "pdf").glob("*.pdf"))) == 2
    linhas = {x["k"]: x for x in _api(srv, "lista")["linhas"]}
    assert all(x["situacao"] == "Enviado" for x in linhas.values())
    assert linhas[next(k for k in ks if k.startswith("scp"))]["destino"] == "PDF"
    assert next(f for f in srv.repo_.films() if f["id"] == fid)["printed_at"] is not None
    e = _api(srv, f"detalhes?k=film:{fid}")["envios"]
    assert len(e) == 1 and e[0]["destino"] == "PDF" and e[0]["quem"] == "tec" and e[0]["como"] == "à mão" and e[0]["ok"]
    # reimprimir: primeiro o plano, depois de verdade
    p = _api(srv, "reimprimir", {"ks": ks})
    assert p["n"] == 2 and "para PDF: 2" in p["plano"] and len(list((srv.tmp / "pdf").glob("*.pdf"))) == 2
    r = _api(srv, "reimprimir", {"ks": ks, "confirmar": True})
    assert r["ok"] == 2 and len(list((srv.tmp / "pdf").glob("*.pdf"))) == 4
    e = _api(srv, f"detalhes?k=film:{fid}")["envios"]
    assert [x["como"] for x in e] == ["reimpressão", "à mão"]
    # destino que não existe, modelo que não existe, nada escolhido
    assert _erro(srv, "enviar", {"ks": ks, "destino": "Nenhum"})[0] == 404
    assert _erro(srv, "enviar", {"ks": ks, "destino": "PDF", "modelo": "Nenhum"})[0] == 404
    assert _erro(srv, "enviar", {"ks": [], "destino": "PDF"})[0] == 400
    # imagens numa pasta; e o envio que falha fica anotado (pasta impossível)
    assert _api(srv, "enviar", {"ks": [ks[0]], "destino": "Imagens"})["ok"] == 1
    assert list((srv.tmp / "img").iterdir())
    from ipe.printing import dispatch as D
    arquivo = srv.tmp / "arquivo"
    arquivo.write_text("x")
    D.save_destinations(srv.st, D.all_destinations(srv.st) + [D.Destination(name="Ruim", kind="pdf",
                                                                            folder=str(arquivo / "sub"))])
    r = _api(srv, "enviar", {"ks": [next(k for k in ks if k.startswith("scp"))], "destino": "Ruim"})
    assert r["ok"] == 0 and r["falhas"] == 1 and "com erro" in r["mensagem"]
    assert next(x for x in _api(srv, "lista")["linhas"] if x["kind"] == "scp")["situacao"] == "Erro"
    acoes = [a[2] for a in srv.repo_.audit_entries(50)]
    assert "imprimir" in acoes


# ---------------------------------------------------------------- identificar, OCR e a regra
def test_identificar_com_ocr_segue_a_regra(servidor, monkeypatch):
    from ipe.central import impressoes_web as IW
    from ipe.db.repository import Repository
    from ipe.printing import ocr
    srv = servidor
    srv.imprimir(1)
    k = _api(srv, "lista")["linhas"][0]["k"]
    a = _api(srv, "identificar_abrir", {"k": k})
    assert a["id"] == "" and not a["ocr"] and a["motivo"]       # o nome é só o rótulo da sessão
    assert _erro(srv, "ocr", {"k": k})[0] == 400                               # leitor não instalado: diz o motivo
    monkeypatch.setattr(ocr, "available", lambda: True)
    monkeypatch.setattr(Repository, "studies_for_ocr", lambda self: list(ESTUDOS))
    monkeypatch.setattr(IW, "_ler_cabecalho", lambda c, r: CABECALHO)
    o = _api(srv, "ocr", {"k": k})
    assert "MOREIRA" in o["texto"] and o["certo"] and o["candidatos"][0]["id"] == "7781234"
    assert o["candidatos"][0]["texto"].startswith("OCR ") and o["candidatos"][0]["study_uid"] == "1.2.3"
    monkeypatch.setattr(IW, "_ler_cabecalho", lambda c, r: "SE 3 IM 12")
    o2 = _api(srv, "ocr", {"k": k})
    assert o2["candidatos"] == [] and "Não consegui ler" in o2["mensagem"]
    assert _erro(srv, "identificar", {"k": k, "nome": "", "id": ""})[0] == 400
    # confirmar: grava o paciente e o filme segue pela regra (Mamografia → PDF)
    r = _api(srv, "identificar", {"k": k, "nome": o["candidatos"][0]["nome"], "id": "7781234", "study_uid": "1.2.3"},
             tok=_token(srv, "tec", "tecnico1"))
    assert "seguiu pela regra" in r["mensagem"]
    linha = srv.repo_.print_jobs()[0]
    assert linha["patient_id"] == "7781234" and linha["id_source"] == "exame" and linha["status"] == "sent"
    assert len(list((srv.tmp / "pdf").glob("*.pdf"))) == 1
    e = _api(srv, f"detalhes?k={k}")["envios"]
    assert e[0]["como"] == "pela regra" and e[0]["quem"] == "tec"
    assert "identificar" in [x[2] for x in srv.repo_.audit_entries(50)]
    # filme montado no compositor (sem origem de identificação) não é identificado por aqui
    fid = _filme_montado(srv)
    assert _erro(srv, "identificar_abrir", {"k": f"film:{fid}"})[0] == 400


def test_identificar_a_mao_sem_regra_fica_na_lista(servidor):
    from ipe.printing import rules as R
    srv = servidor
    R.save_rules(srv.st, [])
    srv.imprimir(1)
    k = _api(srv, "lista")["linhas"][0]["k"]
    r = _api(srv, "identificar", {"k": k, "nome": "FANTOMA^DOIS", "id": "F2"})
    assert r["mensagem"] == "Paciente confirmado."
    x = _api(srv, "lista")["linhas"][0]
    assert x["paciente"] == "FANTOMA^DOIS" and x["id"] == "F2" and x["situacao"] == "Na lista (nenhuma regra)"
    assert not x["sem_nome"] and srv.repo_.print_jobs()[0]["id_source"] == "manual"


# ---------------------------------------------------------------- parados e liberar
def test_parados_e_liberar(servidor):
    srv = servidor
    srv.imprimir(1)
    srv.imprimir(1)
    p = _api(srv, "parados")
    assert len(p["grupos"]) == 1 and p["grupos"][0]["trabalhos"] == 2 and not p["grupos"][0]["pode_liberar"]
    assert p["prontos"] == 0 and "confirmar o paciente" in p["resumo"]
    assert _api(srv, "liberar", {})["ok"] == 0
    # com o OCR na chegada desligado, o que estava esperando paciente fica pronto para sair pela regra
    from ipe.printing import arrival as A
    srv.st.set(A.CHAVE, False)
    p = _api(srv, "parados")
    assert p["grupos"][0]["pode_liberar"] and p["prontos"] == 2 and p["grupos"][0]["simbolo"] == "✔"
    r = _api(srv, "liberar", {"id": p["grupos"][0]["id"]})
    assert r["ok"] == 2 and r["falhas"] == 0
    assert len(list((srv.tmp / "pdf").glob("*.pdf"))) == 2 and _api(srv, "lista")["parados"] == 0


# ---------------------------------------------------------------- juntar e apagar
def test_juntar_e_apagar(servidor):
    srv = servidor
    srv.imprimir(1, 60)
    srv.imprimir(1, 120)
    fid = _filme_montado(srv)
    ks = [x["k"] for x in _api(srv, "lista")["linhas"] if x["kind"] == "scp"]
    assert len(ks) == 2
    assert _erro(srv, "juntar", {"ks": ks[:1]})[0] == 400
    p = _api(srv, "juntar", {"ks": ks})
    assert "Juntar 2 trabalhos" in p["plano"] and len(srv.repo_.print_jobs()) == 2
    r = _api(srv, "juntar", {"ks": ks, "confirmar": True})
    assert "2 trabalhos juntados" in r["mensagem"] and len(srv.repo_.print_jobs()) == 1
    um = next(x for x in _api(srv, "lista")["linhas"] if x["kind"] == "scp")
    assert um["folhas"] == 2 and um["k"] == r["k"]
    png, _t = _api(srv, f"folha?k={um['k']}&i=1", cru=True)
    assert png[:4] == b"\x89PNG"
    # apagar: o técnico também pode; some da lista, e a pasta do trabalho some do disco
    pasta = Path(srv.repo_.print_jobs()[0]["folder"])
    assert pasta.exists()
    r = _api(srv, "apagar", {"ks": [um["k"], f"film:{fid}"]}, tok=_token(srv, "tec", "tecnico1"))
    assert r["n"] == 2 and _api(srv, "lista")["de"] == 0 and not pasta.exists()
    assert "apagar" in [x[2] for x in srv.repo_.audit_entries(50)]
    assert _erro(srv, "apagar", {"ks": ["aw:1.2.3"]})[0] == 400


# ---------------------------------------------------------------- painel
def test_painel(servidor):
    srv = servidor
    srv.imprimir(2)
    fid = _filme_montado(srv)
    _filme_montado(srv, "Outro filme")
    _api(srv, "enviar", {"ks": [f"film:{fid}"], "destino": "PDF"})
    p = _api(srv, "painel")
    c = p["cartoes"]
    assert c["filmes"] == 3 and c["compositor"] == 2 and c["dicom"] == 1 and c["impressos"] == 1
    assert c["pct"].startswith("33") and c["folhas_impressas"] == 1 and c["nao_impressos"] == 2
    assert c["destinos"] and "PDF" in c["destinos"][0]["nome"]
    assert len(p["linhas"]) == 3 and p["no_periodo"] == 3 and len(p["por_mes"]) == 1
    assert {g["nome"] for g in p["por_usuario"]} >= {"admin"} and p["periodos"][0]["k"] == "30d"
    assert sum(g["filmes"] for g in p["por_usuario"]) == 3
    imp = next(x for x in p["linhas"] if x["impresso"])
    assert imp["k"] == f"film:{fid}" and imp["impresso_por"] == "admin" and imp["impresso_em"]
    assert _api(srv, "painel?so_nao=1")["total"] == 2
    assert _api(srv, "painel?tipo=dicom")["cartoes"]["filmes"] == 1
    assert _api(srv, "painel?user=admin")["cartoes"]["filmes"] == 2
    assert _api(srv, "painel?periodo=datas&de=2001-01-01&ate=2001-01-31")["cartoes"]["filmes"] == 0
    assert _api(srv, "painel?dias=0")["cartoes"]["parados"] == 2


# ---------------------------------------------------------------- no idioma do navegador
def test_resposta_no_idioma_do_navegador(servidor):
    from ipe.core import i18n as I
    srv = servidor
    srv.imprimir(1)
    antes = I.current()
    en = _api(srv, "lista?lang=en")
    x = en["linhas"][0]
    assert x["tipo"] == "Received" and x["situacao"] == "Waiting for patient", x
    assert en["filtros"][0]["nome"] == "All" and any("confirm the patient" in f for f in en["faixa"])
    assert [d["nome"] for d in en["destinos"]] == ["PDF", "Imagens"]          # nome de destino não se traduz
    d = _api(srv, f"detalhes?k={x['k']}&lang=en")
    assert any(l.startswith("Came from MG_SELENIA") for l in d["linhas"]), d["linhas"]
    es = _api(srv, "lista?lang=es")
    assert es["linhas"][0]["tipo"] == "Recibido"
    pt = _api(srv, "lista")
    assert pt["linhas"][0]["tipo"] == "Recebido" and I.current() == antes
    assert _api(srv, "painel?lang=en")["periodos"][0]["nome"] == "Last 30 days"


# ---------------------------------------------------------------- no navegador
def _ate(srv, f, t=40.0):
    fim = time.time() + t
    while time.time() < fim:
        srv.app.processEvents()
        try:
            if f():
                return True
        except Exception:  # noqa: BLE001 - a página ainda montando
            pass
        time.sleep(0.05)
    return False


def _entrar(pw, srv, b, usuario, senha, erros):
    pg = b.new_page(viewport={"width": 1600, "height": 950})
    pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.goto(f"http://127.0.0.1:{srv.port}/web/")
    pg.fill("#usuario", usuario)
    pg.fill("#senha", senha)
    pg.click("button[type=submit]")
    assert _ate(srv, lambda: pg.locator("form.filtros").count() > 0)
    return pg


def test_no_navegador(servidor, monkeypatch):
    import os

    from ipe.central import impressoes_web as IW
    from ipe.db.repository import Repository
    from ipe.printing import ocr
    pw = pytest.importorskip("playwright.sync_api")
    srv = servidor
    srv.imprimir(2)
    srv.imprimir(1, 120)
    fid = _filme_montado(srv)
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        # o residente não vê o botão; o técnico e o administrador veem
        pg = _entrar(pw, srv, b, "res", "resid123", erros)
        assert pg.locator("button.impressoes-abrir").is_hidden()
        pg.close()
        pg = _entrar(pw, srv, b, "tec", "tecnico1", erros)
        assert pg.locator("button.impressoes-abrir").is_visible() and pg.locator("button.gestao-abrir").is_hidden()
        pg.click("button.impressoes-abrir")
        assert _ate(srv, lambda: pg.locator(".imp-tabela tbody tr[data-k]").count() == 3)
        est = lambda: pg.evaluate("() => window.__ipeImpressoes.estado()")   # noqa: E731
        assert "Parados (2)" in pg.locator(".imp-barra button", has_text="Parados").inner_text()
        assert pg.locator(".imp-faixa").is_visible() and "confirmar o paciente" in pg.locator(".imp-faixa").inner_text()
        assert pg.locator(".imp-barra button", has_text="Enviar para").is_disabled()
        # escolher o trabalho de duas folhas: a folha aparece, ▶ vira, os detalhes vêm
        k2 = next(x["k"] for x in est()["linhas"] if x["folhas"] == 2)
        pg.click(f".imp-tabela tr[data-k='{k2}'] td:nth-child(3)")
        assert _ate(srv, lambda: pg.evaluate("() => document.querySelector('.imp-previa')?.naturalWidth || 0") > 0)
        assert "1" in pg.locator(".imp-folha-n").inner_text() and est()["nFolhas"] == 2
        assert "Chegou de MG_SELENIA" in pg.locator(".imp-detalhes").inner_text()
        assert "Ainda não foi enviado" in pg.locator(".imp-detalhes").inner_text()
        pg.click(".imp-folhas button[aria-label='Próxima folha']")
        assert _ate(srv, lambda: est()["folha"] == 1) and pg.locator(".imp-folhas button[aria-label='Próxima folha']").is_disabled()
        pg.click(".imp-folhas button:has-text('Ampliar')")
        assert _ate(srv, lambda: pg.evaluate("() => document.querySelector('dialog.imp-janela img.imp-grande')?.naturalWidth || 0") > 0)
        pg.click("dialog.imp-janela button:has-text('Fechar')")
        assert _ate(srv, lambda: pg.locator("dialog.imp-janela").count() == 0)
        # identificar com o OCR: lê, sugere o paciente, confirma — e o filme segue pela regra
        monkeypatch.setattr(ocr, "available", lambda: True)
        monkeypatch.setattr(Repository, "studies_for_ocr", lambda self: list(ESTUDOS))
        monkeypatch.setattr(IW, "_ler_cabecalho", lambda c, r: CABECALHO)
        pg.click(".imp-barra button:has-text('Identificar paciente')")
        assert _ate(srv, lambda: pg.locator("dialog.imp-janela button:has-text('Ler o cabeçalho')").is_enabled())
        pg.click("dialog.imp-janela button:has-text('Ler o cabeçalho')")
        assert _ate(srv, lambda: pg.locator(".imp-candidatos button[aria-selected=true]").count() == 1)
        assert "MOREIRA" in pg.locator(".imp-lido").inner_text()
        assert pg.input_value("dialog.imp-janela input[aria-label='ID']") == "7781234"
        if os.environ.get("IPE_IMP_FOTO"):
            pg.screenshot(path=os.environ["IPE_IMP_FOTO"] + "_identificar.png")
        pg.click("dialog.imp-janela button:has-text('Confirmar')")
        assert _ate(srv, lambda: "seguiu pela regra" in pg.locator(".imp-nota").inner_text())
        assert _ate(srv, lambda: next(x for x in est()["linhas"] if x["k"] == k2)["situacao"] == "Enviado")
        assert len(list((srv.tmp / "pdf").glob("*.pdf"))) == 1
        assert _ate(srv, lambda: "pela regra" in pg.locator(".imp-envios").inner_text())
        # enviar o filme montado para "Imagens", pela janela
        pg.click(f".imp-tabela tr[data-k='film:{fid}'] td:nth-child(3)")
        assert _ate(srv, lambda: est()["atual"] == f"film:{fid}" and est()["nFolhas"] == 1)
        pg.click(".imp-barra button:has-text('Enviar para')")
        pg.select_option("dialog.imp-janela select[aria-label='Destino']", "Imagens")
        pg.click("dialog.imp-janela button.primario")
        assert _ate(srv, lambda: "enviados" in pg.locator(".imp-nota").inner_text())
        assert list((srv.tmp / "img").iterdir())
        # reimprimir: o plano na janela, e sai de novo
        pg.click(".imp-barra button:has-text('Reimprimir')")
        assert _ate(srv, lambda: "para Imagens: 1" in pg.locator("dialog.imp-janela").inner_text())
        pg.click("dialog.imp-janela button.primario")
        assert _ate(srv, lambda: "Reimpressos: 1" in pg.locator(".imp-nota").inner_text())
        # filtro e busca
        pg.select_option(".imp-barra select[aria-label='Mostrar']", "held")
        assert _ate(srv, lambda: len(est()["linhas"]) == 1)
        pg.select_option(".imp-barra select[aria-label='Mostrar']", "")
        pg.fill(".imp-barra input[type=search]", "fantoma")
        assert _ate(srv, lambda: [x["kind"] for x in est()["linhas"]] == ["film"])
        pg.fill(".imp-barra input[type=search]", "")
        assert _ate(srv, lambda: len(est()["linhas"]) == 3)
        # parados: a janela, por aparelho
        pg.click(".imp-barra button:has-text('Parados')")
        assert _ate(srv, lambda: pg.locator("dialog.imp-janela .imp-parados tbody tr").count() == 1)
        assert pg.locator("dialog.imp-janela button:has-text('Liberar todos')").is_disabled()
        pg.click("dialog.imp-janela button:has-text('Fechar')")
        if os.environ.get("IPE_IMP_FOTO"):
            pg.click(f".imp-tabela tr[data-k='{k2}'] td:nth-child(3)")
            assert _ate(srv, lambda: est()["atual"] == k2)
            time.sleep(0.6)
            for _ in range(10):
                srv.app.processEvents(); time.sleep(0.05)
            pg.screenshot(path=os.environ["IPE_IMP_FOTO"] + "_lista.png")
        # apagar o que sobrou parado (o técnico pode): pergunta antes
        k1 = next(x["k"] for x in est()["linhas"] if x["status"] == "new")
        pg.click(f".imp-tabela tr[data-k='{k1}'] td:nth-child(3)")
        pg.click(".imp-barra button:has-text('Apagar')")
        assert "Não dá para desfazer" in pg.locator("dialog.imp-janela").inner_text()
        pg.click("dialog.imp-janela button.primario")
        assert _ate(srv, lambda: len(est()["linhas"]) == 2 and est()["parados"] == 0)
        # o painel
        pg.click(".imp-abas button:has-text('Painel')")
        assert _ate(srv, lambda: pg.locator(".imp-cartao").count() == 7)
        dados = pg.evaluate("() => window.__ipePainelFilmes.estado()")
        assert dados["cartoes"]["filmes"] == 2 and dados["cartoes"]["impressos"] == 2
        assert pg.locator(".imp-filmes tbody tr").count() == 2 and pg.locator(".imp-meses .mes").count() == 1
        linhas_csv = pg.evaluate("() => window.__ipePainelFilmes.csv()").split("\r\n")
        assert len(linhas_csv) == 3 and linhas_csv[0].startswith('"Criado em";"Origem"') and '"Sim"' in linhas_csv[1]
        pg.check(".imp-painel input[type=checkbox]")
        assert _ate(srv, lambda: pg.evaluate("() => window.__ipePainelFilmes.estado().total") == 0)
        if os.environ.get("IPE_IMP_FOTO"):
            pg.uncheck(".imp-painel input[type=checkbox]")
            assert _ate(srv, lambda: pg.locator(".imp-filmes tbody tr").count() == 2)
            pg.screenshot(path=os.environ["IPE_IMP_FOTO"] + "_painel.png")
        # voltar à lista de exames
        pg.click("button.link:has-text('Lista de exames')")
        assert _ate(srv, lambda: pg.locator("table.lista").count() > 0 and pg.locator(".impressoes").count() == 0)
        b.close()
    assert not erros, erros
