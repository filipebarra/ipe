"""0.99.98 (W6): laudo no navegador — o modelo do Ipê com os campos automáticos, os achados de IA revisados
(o sugerido não entra), o rascunho no mesmo registro de laudo do Ipê, a trava de "quem está laudando" entre dois
médicos, a assinatura (liberação) e a retificação."""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _web_ui import icone  # noqa: E402
from test_web_mpr import _esperar, servidor  # noqa: E402,F401  (fixture)

from ipe.central import web as WEB  # noqa: E402


def _estudo(srv):
    return srv.repo.search_studies()[0].study_uid


def _token(srv, u="admin", p="admin123"):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/login", method="POST",
                                 data=json.dumps({"username": u, "password": p}).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())["token"]


def _get(srv, caminho, token):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}{caminho}", headers={"Authorization": f"Bearer {token}"})
    return json.loads(urllib.request.urlopen(req).read())


def _preparar(srv):
    repo = srv.repo
    study = _estudo(srv)
    repo.save_user({"username": "medica2", "full_name": "Dra. Segunda", "role": "medico", "active": True,
                    "password": "outra123"})
    repo.save_user({"username": "tec", "full_name": "Técnico", "role": "tecnico", "active": True,
                    "password": "tec12345"})
    # um nódulo confirmado (vai ao laudo) e um sugerido (não vai)
    ids = repo.gravar_achados(study, "nodulos", [
        {"rotulo": "N1", "tipo": "Nódulo", "local": "lobo superior direito",
         "numeros": {"medio_mm": {"v": 7.25, "u": "mm", "n": "Diâmetro médio"}}},
        {"rotulo": "N2", "tipo": "Nódulo", "local": "lobo inferior esquerdo",
         "numeros": {"medio_mm": {"v": 4.0, "u": "mm", "n": "Diâmetro médio"}}}])
    repo.revisar_achado(ids[0], "confirmado", "admin")
    return study


def test_dados_do_laudo_no_servidor(servidor):
    study = _preparar(servidor)
    d = _get(servidor, f"/api/web/laudo?study={study}", _token(servidor))
    assert d["laudos"] == [] and d["pode"] == {"escrever": True, "assinar": True}
    assert d["sugerido"] and any(m["id"] == d["sugerido"] for m in d["modelos"])
    sug = next(m for m in d["modelos"] if m["id"] == d["sugerido"])
    assert "CT" in sug["modalities"]                                     # o exame é uma TC
    assert d["contexto"]["paciente"] == "MPR, FANTOMA" and d["contexto"]["data_exame"] == "08/11/2026"
    assert "N1" in d["ia"] and "7,2" in d["ia"] and "N2" not in d["ia"]  # só o revisado
    assert d["trava"] is None and d["eu"]["usuario"] == "admin"
    # o técnico vê, mas não escreve nem assina
    t = _get(servidor, f"/api/web/laudo?study={study}", _token(servidor, "tec", "tec12345"))
    assert t["pode"] == {"escrever": False, "assinar": False}


def _entrar(pg, srv, u="admin", p="admin123"):
    pg.goto(f"http://127.0.0.1:{srv.port}/web/")
    pg.fill("#usuario", u)
    pg.fill("#senha", p)
    pg.click("button[type=submit]")
    pg.wait_for_selector("table.lista tbody tr")
    pg.locator("table.lista tbody tr").first.dblclick()
    pg.wait_for_selector(".quadro canvas")


def _laudo(pg):
    return pg.evaluate("() => window.__ipeLaudo.estadoAtual()")


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_laudo_no_navegador(servidor):
    pw = pytest.importorskip("playwright.sync_api")
    study = _preparar(servidor)
    repo = servidor.repo
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1500, "height": 950})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        _entrar(pg, servidor)
        icone(pg, "Laudo")
        pg.wait_for_selector("aside.laudo")
        # o modelo sugerido, com os campos automáticos preenchidos como no Ipê
        from ipe.reporting.fill import fill
        d = _get(servidor, f"/api/web/laudo?study={study}", _token(servidor))
        sug = next(m for m in d["modelos"] if m["id"] == d["sugerido"])
        assert _esperar(lambda: pg.input_value("aside.laudo textarea.texto-laudo") == fill(sug["text"], d["contexto"]))
        assert "{" not in pg.input_value("aside.laudo textarea.texto-laudo")
        # o preenchimento do site é o do Ipê
        modelo = "Exame: {exame}\n{medidas}\n\n\n\nPaciente {paciente}, {idade}\n{nao_existe}\n"
        ctx = {"exame": "TC TORAX", "medidas": "", "paciente": "X", "idade": "50 anos"}
        assert pg.evaluate("([m, c]) => window.__ipeLaudoPreencher(m, c)", [modelo, ctx]) == fill(modelo, ctx)
        # quem abriu o laudo é quem está laudando
        assert servidor.leituras.quem(study)["usuario"] == "admin"
        # achados de IA revisados no cursor (o fim do texto)
        pg.click("aside.laudo textarea.texto-laudo")
        pg.keyboard.press("Control+End")
        pg.click("aside.laudo button:has-text('Inserir achados de IA')")
        texto = pg.input_value("aside.laudo textarea.texto-laudo")
        assert "N1" in texto and "N2" not in texto
        pg.fill("aside.laudo textarea.texto-laudo", texto + "\nIMPRESSÃO: nódulo pulmonar de 7 mm.\n")
        pg.click("aside.laudo button:has-text('Salvar rascunho')")
        assert _esperar(lambda: len(repo.reports(study)) == 1)
        r = repo.reports(study)[0]
        assert r["status"] == "draft" and "IMPRESSÃO: nódulo pulmonar" in r["text"] and r["author"] == "Administrador"
        # outra médica abre o mesmo exame: o laudo é só leitura (com o aviso de quem está laudando)
        pg2 = b.new_page(viewport={"width": 1500, "height": 950})
        pg2.on("pageerror", lambda e: erros.append("2: " + str(e)))
        _entrar(pg2, servidor, "medica2", "outra123")
        icone(pg2, "Laudo")
        pg2.wait_for_selector("aside.laudo .trava-laudo:visible")
        assert "Administrador está laudando este exame" in pg2.inner_text("aside.laudo .trava-laudo")
        assert _esperar(lambda: _laudo(pg2)["podeEscrever"] is False and _laudo(pg2)["id"] == r["id"])
        assert pg2.locator("aside.laudo button:has-text('Assinar e liberar')").is_disabled()
        # e o servidor recusa gravar por ela, mesmo por fora da tela
        req = urllib.request.Request(f"http://127.0.0.1:{servidor.port}/api/rpc", method="POST",
                                     data=json.dumps({"method": "save_report", "args": [{"id": r["id"], "study_uid": study,
                                                      "text": "outro"}]}).encode(),
                                     headers={"Authorization": f"Bearer {_token(servidor, 'medica2', 'outra123')}",
                                              "Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(req)
        assert e.value.code == 403 and "está laudando" in json.loads(e.value.read())["error"]
        # ela assume: passa a escrever; quem estava perde a trava
        pg2.click("aside.laudo button:has-text('Assumir o laudo')")
        assert _esperar(lambda: _laudo(pg2)["podeEscrever"] is True)
        assert _esperar(lambda: servidor.leituras.quem(study)["usuario"] == "medica2")
        assert repo.access_log(limit=50, action="assumiu_laudo", study_uid=study)
        pg2.click("aside.laudo button.fechar")
        assert _esperar(lambda: servidor.leituras.quem(study) is None)
        pg2.close()
        # a primeira retoma e assina (com a confirmação na própria janela)
        pg.click("aside.laudo button.fechar")
        icone(pg, "Laudo")
        assert _esperar(lambda: _laudo(pg)["id"] == r["id"] and _laudo(pg)["podeEscrever"] is True)
        pg.click("aside.laudo button:has-text('Assinar e liberar')")
        pg.click("aside.laudo .confirmar-laudo button:has-text('Assinar')")
        assert _esperar(lambda: repo.reports(study)[0]["status"] == "final")
        assert repo.reports(study)[0]["signed_by"] == "Administrador"
        assert _esperar(lambda: _laudo(pg)["status"] == "final" and _laudo(pg)["podeEscrever"] is False)
        assert "assinado" in pg.inner_text("aside.laudo .estado-laudo")
        # retificar: rascunho novo com o texto; assinar vira "retificado"; o anterior fica
        pg.click("aside.laudo button:has-text('Retificar')")
        assert _laudo(pg)["amends"] == r["id"] and _laudo(pg)["podeEscrever"] is True
        pg.fill("aside.laudo textarea.texto-laudo", _laudo(pg)["texto"].replace("7 mm", "8 mm"))
        pg.click("aside.laudo button:has-text('Assinar e liberar')")
        pg.click("aside.laudo .confirmar-laudo button:has-text('Assinar')")
        assert _esperar(lambda: [x["status"] for x in repo.reports(study)] == ["final", "amended"])
        assert "8 mm" in repo.reports(study)[1]["text"] and "7 mm" in repo.reports(study)[0]["text"]
        # fechar solta a trava
        pg.click("aside.laudo button.fechar")
        assert _esperar(lambda: servidor.leituras.quem(study) is None)
        b.close()
    assert not erros, erros


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_tecnico_so_le(servidor):
    pw = pytest.importorskip("playwright.sync_api")
    study = _preparar(servidor)
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1500, "height": 950})
        _entrar(pg, servidor, "tec", "tec12345")
        icone(pg, "Laudo")
        pg.wait_for_selector("aside.laudo")
        assert _esperar(lambda: _laudo(pg)["soLeitura"] != "")
        assert pg.locator("aside.laudo textarea.texto-laudo").get_attribute("readonly") is not None
        assert servidor.leituras.quem(study) is None                 # quem só lê não trava o exame
        b.close()


# ------------------------------------------------------------------ 0.100.4: BI-RADS, PDF/SR e busca ativa
def _post(srv, caminho, token, corpo):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}{caminho}", method="POST", data=json.dumps(corpo).encode(),
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return r.headers.get("Content-Type", ""), r.read()


CAMPOS = {"kind": "mg", "composition": "c", "cat_right": "2", "cat_left": "",
          "findings": [{"side": "E", "type": "Nódulo", "desc": "forma oval, margem circunscrita", "size": "12",
                        "location": "quadrante superolateral", "distance": "3 cm", "change": "novo", "category": "3"}]}


def test_textos_do_birads_sao_os_do_ipe(servidor):
    from ipe.reporting import birads as B
    tok = _token(servidor)
    _ct, corpo = _post(servidor, "/api/web/birads_texto", tok, {"fields": CAMPOS})
    d = json.loads(corpo)
    assert d["final"] == "3" == B.final_category(CAMPOS)
    assert d["blocos"] == {"composicao": B.composition_text(CAMPOS), "achados_birads": B.findings_text(CAMPOS),
                           "birads": B.category_text(CAMPOS), "conduta": B.recommendation(CAMPOS),
                           "bpe_texto": B.bpe_text(CAMPOS)}
    assert d["achados"] == [B.finding_text(CAMPOS["findings"][0])]
    assert "Mama esquerda: nódulo, forma oval" in d["achados"][0] and "BI-RADS® 3" in d["achados"][0]
    # o catálogo vem com o laudo
    study = _estudo(servidor)
    lw = _get(servidor, f"/api/web/laudo?study={study}", tok)
    assert lw["birads"]["categorias"]["4A"] == B.CATEGORIES["4A"] and "quadrante superolateral" in lw["birads"]["locais"]
    assert lw["opcoes"]["pdf"] is True and lw["opcoes"]["sr"] is True and lw["buscas"] == []


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_birads_pdf_sr_e_busca_ativa_no_navegador(servidor):
    pw = pytest.importorskip("playwright.sync_api")
    from PySide6.QtWidgets import QApplication
    from ipe.reporting import birads as B
    QApplication.instance() or QApplication([])        # o PDF usa o Qt de interface (como no servidor sem tela)
    study = _preparar(servidor)
    repo = servidor.repo
    series_antes = len(repo.series_for_study(study, ocultas=True))
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1500, "height": 1000}, accept_downloads=True)
        pg.on("pageerror", lambda e: erros.append(str(e)))
        _entrar(pg, servidor)
        icone(pg, "Laudo")
        pg.wait_for_selector("aside.laudo")
        assert _esperar(lambda: _laudo(pg)["podeEscrever"] is True)
        texto = lambda: pg.input_value("aside.laudo textarea.texto-laudo")  # noqa: E731
        pg.click("aside.laudo details.birads-laudo > summary")
        pg.select_option("select[aria-label='Tipo do BI-RADS']", "mg")
        # o modelo da TC não tem os campos do BI-RADS: "Levar ao texto" põe os blocos no cursor
        pg.click("aside.laudo textarea.texto-laudo")
        pg.keyboard.press("Control+End")
        pg.click("aside.laudo button:has-text('Levar ao texto do laudo')")
        assert _esperar(lambda: "Composição mamária: ___" in texto() and "BI-RADS®: ___" in texto())
        # a composição troca o bloco no texto
        pg.select_option("select[aria-label='Composição']", "c")
        assert _esperar(lambda: B.COMPOSITION["mg"]["c"] in texto() and "Composição mamária: ___" not in texto())
        # um achado pelo formulário (o descritor da lista entra no campo)
        pg.click("aside.laudo button:has-text('+ Achado')")
        pg.select_option("select[aria-label='Lado do achado']", "E")
        pg.select_option("select[aria-label='Tipo do achado']", "Nódulo")
        pg.select_option("select[aria-label='Acrescentar descritor']", "forma oval")
        pg.select_option("select[aria-label='Acrescentar descritor']", "margem circunscrita")
        pg.fill("input[aria-label='Tamanho']", "12")
        pg.select_option("select[aria-label='Local do achado']", "quadrante superolateral")
        pg.fill("input[aria-label='Distância do mamilo']", "3 cm")
        pg.select_option("select[aria-label='Mudança']", "novo")
        pg.select_option("select[aria-label='Categoria do achado']", "3")
        pg.click("aside.laudo .form-achado button:has-text('OK')")
        pg.select_option("select[aria-label='Categoria da mama direita']", "2")
        assert _esperar(lambda: _laudo(pg)["final"] == "3")
        assert _esperar(lambda: B.findings_text(CAMPOS) in texto() and B.category_text(CAMPOS) in texto()), texto()
        pg.click("aside.laudo button:has-text('Salvar rascunho')")
        assert _esperar(lambda: len(repo.reports(study)) == 1)
        r = repo.reports(study)[0]
        assert {k: r["fields"].get(k) for k in CAMPOS} == CAMPOS
        assert B.category_text(CAMPOS) in r["text"]
        # fechar e abrir de novo: o formulário volta, e mudar a categoria ainda troca o bloco no texto
        pg.click("aside.laudo button.fechar")
        icone(pg, "Laudo")
        assert _esperar(lambda: _laudo(pg)["id"] == r["id"] and _laudo(pg)["campos"].get("composition") == "c")
        assert _esperar(lambda: "composicao" in _laudo(pg)["auto"])
        pg.click("aside.laudo details.birads-laudo > summary") if not pg.locator("select[aria-label='Composição']").is_visible() else None
        pg.select_option("select[aria-label='Composição']", "d")
        assert _esperar(lambda: B.COMPOSITION["mg"]["d"] in texto() and B.COMPOSITION["mg"]["c"] not in texto())
        # o PDF, igual ao do Ipê, com o cabeçalho e a assinatura
        pg.click("aside.laudo details.saidas-laudo > summary")
        pg.fill("textarea[aria-label='Cabeçalho do PDF']", "CLÍNICA EXEMPLO")
        pg.fill("input[aria-label='Linha da assinatura']", "CRM-DF 00000")
        with pg.expect_download() as dl:
            pg.click("aside.laudo button:has-text('Baixar PDF')")
        pdf = Path(dl.value.path()).read_bytes()
        assert pdf.startswith(b"%PDF") and len(pdf) > 2000
        assert repo.access_log(limit=20, action="laudo_pdf", study_uid=study)
        # assinar: o PDF e o SR vão para o exame, e o BI-RADS 3 entra na busca ativa (180 dias)
        pg.click("aside.laudo button:has-text('Assinar e liberar')")
        pg.click("aside.laudo .confirmar-laudo button:has-text('Assinar')")
        assert _esperar(lambda: repo.reports(study)[0]["status"] == "final")
        assert _esperar(lambda: "busca ativa" in pg.inner_text("aside.laudo .msg-laudo"), 20), pg.inner_text("aside.laudo .msg-laudo")
        assert "2 objeto(s) DICOM guardado(s) no exame" in pg.inner_text("aside.laudo .msg-laudo")
        series = repo.series_for_study(study, ocultas=True)
        assert len(series) == series_antes + 2
        assert {"SR"} <= {s.modality for s in series}
        bs = repo.buscas_ativas(study_uid=study)
        assert len(bs) == 1 and bs[0]["categoria"] == "3"
        assert _esperar(lambda: "BI-RADS 3" in pg.inner_text("aside.laudo .buscas-laudo"))
        # o formulário do laudo assinado é só leitura
        assert pg.locator("select[aria-label='Categoria da mama direita']").is_disabled()
        b.close()
    assert not erros, erros
