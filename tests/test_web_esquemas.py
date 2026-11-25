"""0.100.72: esquemas-guia do laudo no Ipê Web — as rotas (ver o exame para ler, `report` para gravar), o editor
no navegador (ponto, elipse, seta, traço, setor da próstata, ligar à imagem aberta, legenda no laudo) e, ao
assinar, a imagem e o SR no exame e a figura no PDF."""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pydicom
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _web_ui import icone  # noqa: E402
from test_web_laudo import _entrar, _estudo, _token  # noqa: E402
from test_web_mpr import _esperar, servidor  # noqa: E402,F401  (fixture)

from ipe.central import web as WEB  # noqa: E402
from ipe.reporting import esquemas as E  # noqa: E402


def _pedir(srv, caminho, token, corpo=None, bruto=False):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/web/esquemas/{caminho}",
                                 method="POST" if corpo is not None else "GET",
                                 data=json.dumps(corpo).encode() if corpo is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req).read()
    except urllib.error.HTTPError as e:
        return e.code
    return r if bruto else json.loads(r)


def test_rotas(servidor):
    srv, repo = servidor, servidor.repo
    study = _estudo(srv)
    repo.save_user({"username": "tec", "full_name": "Técnico", "role": "tecnico", "active": True, "password": "tec12345"})
    adm, tec = _token(srv), _token(srv, "tec", "tec12345")
    ms = _pedir(srv, "modelos", adm)
    assert len(ms["modelos"]) >= 8 and ms["cores"] == E.CORES and all("png" not in m for m in ms["modelos"])
    assert _pedir(srv, f"exame?study={study}", adm) == {"esquemas": [], "pode": True, "legenda": "", "no_laudo": False,
                                                        "com_desenho": 0}
    assert _pedir(srv, "exame?study=1.2.3.nada", adm) in (403, 404)
    lista = [{"modelo": "tireoide", "marcas": [{"tipo": "ponto", "n": 1, "p": [[0.4, 0.6]], "texto": "nódulo no LD"}]},
             {"modelo": "inventado"}]
    # o técnico vê, mas não grava nem liga imagem
    assert _pedir(srv, "exame", tec, {"study": study, "esquemas": lista}) == 403
    assert _pedir(srv, f"exame?study={study}", tec)["pode"] is False
    r = _pedir(srv, "exame", adm, {"study": study, "esquemas": lista})
    assert r["ok"] and len(r["esquemas"]) == 1 and r["legenda"] == "Tireoide e níveis cervicais:\n1. nódulo no LD"
    eid = r["esquemas"][0]["id"]
    assert _pedir(srv, "exame", adm, {"study": study}) == 400
    png = _pedir(srv, f"figura?study={study}&id={eid}&w=500", tec, bruto=True)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert _pedir(srv, f"figura?study={study}&id=naoexiste", adm) == 404
    assert _pedir(srv, "fundo?id=tireoide", adm) == 404                # os do Ipê são traços, não imagem
    # ligar à imagem: vira imagem-chave
    serie = repo.series_for_study(study)[0]
    inst = repo.instances_for_series(serie.series_uid)[0]
    assert _pedir(srv, "ligar", tec, {"study": study, "series_uid": serie.series_uid, "sop_uid": inst["sop_uid"]}) == 403
    lig = _pedir(srv, "ligar", adm, {"study": study, "series_uid": serie.series_uid, "sop_uid": inst["sop_uid"]})
    assert lig["imagem"]["rotulo"].startswith("série ") and (inst["sop_uid"], 0) in repo.key_image_set(study)
    assert _pedir(srv, "ligar", adm, {"study": study, "series_uid": serie.series_uid, "sop_uid": "9.9"}) == 404
    assert _pedir(srv, "nada", adm) == 404
    # modelo próprio: a imagem vem pelo "fundo"
    import io
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (300, 200), (250, 240, 230)).save(b, "PNG")
    m = E.novo_modelo_de_imagem(repo, "Meu pé", b.getvalue())
    assert any(x["id"] == m["id"] and x["meu"] and x["imagem"] for x in _pedir(srv, "modelos", adm)["modelos"])
    assert _pedir(srv, f"fundo?id={m['id']}", adm, bruto=True)[:4] == b"\x89PNG"
    # ---- 0.100.73: cadastrar e mudar modelos pelo navegador (quem pode configurar)
    import base64
    assert _pedir(srv, "modelos", adm)["pode_modelos"] is True and _pedir(srv, "modelos", tec)["pode_modelos"] is False
    img = base64.b64encode(b.getvalue()).decode()
    assert _pedir(srv, "modelo", tec, {"nome": "Do técnico", "imagem": img}) == 403
    assert _pedir(srv, "modelo_excluir", tec, {"id": m["id"]}) == 403
    assert _pedir(srv, "modelo", adm, {"nome": "", "imagem": img}) == 400
    assert _pedir(srv, "modelo", adm, {"nome": "Ruim", "imagem": "isto não é base64!"}) == 400
    assert _pedir(srv, "modelo", adm, {"nome": "Ruim", "imagem": base64.b64encode(b"texto").decode()}) == 400
    novo = _pedir(srv, "modelo", adm, {"nome": "Mão direita", "grupo": "Pele", "imagem": "data:image/png;base64," + img})["modelo"]
    assert novo["meu"] and novo["imagem"] and (novo["w"], novo["h"]) == (300, 200) and "png" not in novo
    traco = {"tipo": "traco", "p": [[0.1, 0.5], [0.5, 0.5], [0.9, 0.5]], "cor": "#111111", "l": 5}
    mud = _pedir(srv, "modelo", adm, {"id": "tireoide", "nome": "Tireoide (clínica)", "grupo": "Pescoço", "base": [traco],
                                     "oculto": True})["modelo"]
    assert mud["alterado"] and mud["oculto"] and len(mud["base"]) == 1 and len(mud["tracos"]) > 10
    assert next(x for x in _pedir(srv, "modelos", tec)["modelos"] if x["id"] == "tireoide")["oculto"]
    # o esquema antigo, feito com o modelo que foi ocultado, continua desenhando — agora com o traço do modelo
    assert _pedir(srv, f"figura?study={study}&id={eid}&w=400", adm, bruto=True)[:4] == b"\x89PNG"
    copia = _pedir(srv, "modelo", adm, {"nome": "Próstata 2", "origem": "prostata"})["modelo"]
    assert copia["origem"] == "prostata" and len(copia["setores"]) == 41
    assert _pedir(srv, "modelo_excluir", adm, {"id": "tireoide"})["o_que"] == "restaurado"
    assert _pedir(srv, "modelo_excluir", adm, {"id": novo["id"]})["o_que"] == "excluido"
    assert _pedir(srv, "modelo_excluir", adm, {"id": novo["id"]}) == 404
    assert any("modelo de esquema" in a["detail"] for a in repo.access_log(action="config"))
    # ---- gravar no exame sem laudo
    antes = len(repo.series_for_study(study, True))
    assert _pedir(srv, "no_exame", tec, {"study": study}) == 403
    assert _pedir(srv, "no_exame", adm, {"study": study}) == {"ok": True, "imagens": 1}
    assert _pedir(srv, "no_exame", adm, {"study": study}) == {"ok": True, "imagens": 1}       # de novo: troca
    series = repo.series_for_study(study, True)
    assert len(series) == antes + 2 and {"Esquemas do laudo", "Esquemas do laudo (SR)"} <= {s.description for s in series}
    assert not repo.reports(study)                                       # e não há laudo nenhum
    # ---- 0.100.74: "os esquemas entram no laudo" é uma escolha à parte (como as imagens-chave)
    from ipe.reporting import esquemas_saida as ES
    assert _pedir(srv, f"exame?study={study}", adm)["com_desenho"] == 1 and not ES.figuras(repo, study, so_do_laudo=True)
    assert _pedir(srv, "no_laudo", tec, {"study": study, "sim": True}) == 403
    r = _pedir(srv, "no_laudo", adm, {"study": study, "sim": True})
    assert r["no_laudo"] is True and r["legenda"].startswith("Tireoide e níveis cervicais:\n1. nódulo no LD")
    assert _pedir(srv, f"exame?study={study}", tec)["no_laudo"] is True and len(ES.figuras(repo, study, so_do_laudo=True)) == 1
    _pedir(srv, "exame", adm, {"study": study, "esquemas": _pedir(srv, f"exame?study={study}", adm)["esquemas"]})
    assert _pedir(srv, f"exame?study={study}", adm)["no_laudo"] is True          # desenhar de novo não desliga
    assert _pedir(srv, "no_laudo", adm, {"study": study, "sim": False}) == {"ok": True, "no_laudo": False, "legenda": ""}
    _pedir(srv, "exame", adm, {"study": study, "esquemas": []})
    assert _pedir(srv, "no_exame", adm, {"study": study}) == 400


def _arrastar(pg, sel, a, b, passos=6):
    cx = pg.locator(sel).bounding_box()
    x0, y0 = cx["x"] + a[0] * cx["width"], cx["y"] + a[1] * cx["height"]
    x1, y1 = cx["x"] + b[0] * cx["width"], cx["y"] + b[1] * cx["height"]
    pg.mouse.move(x0, y0)
    pg.mouse.down()
    for k in range(1, passos + 1):
        pg.mouse.move(x0 + (x1 - x0) * k / passos, y0 + (y1 - y0) * k / passos)
    pg.mouse.up()


def _tocar(pg, sel, p):
    cx = pg.locator(sel).bounding_box()
    pg.mouse.click(cx["x"] + p[0] * cx["width"], cx["y"] + p[1] * cx["height"])


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_esquemas_no_navegador(servidor):
    """0.100.74: o botão Esquema do visualizador (fora do laudo) e, no laudo, "Esquemas no laudo"."""
    pw = pytest.importorskip("playwright.sync_api")
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])        # o PDF usa o Qt de interface (como no servidor sem tela)
    srv, repo = servidor, servidor.repo
    study = _estudo(srv)
    erros = []
    foto = os.environ.get("IPE_ESQ_FOTO")
    tela = "dialog.esq-janela canvas.esq-tela"
    jan = "dialog.esq-do-exame"
    est = "() => window.__ipeEsquema.estado()"
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1920, "height": 1080}, accept_downloads=True)
        pg.on("pageerror", lambda e: erros.append(str(e)))
        _entrar(pg, srv)
        icone(pg, "Esquema")
        pg.wait_for_selector(jan)
        assert _esperar(lambda: "Nenhum esquema" in pg.inner_text(jan))
        assert pg.locator(f"{jan} button:has-text('Gravar no exame')").is_disabled()
        assert pg.locator("aside.laudo").count() == 0                       # nada de laudo aberto
        # ---- a face: ponto numerado com descrição, elipse, seta, traço e texto
        pg.click(f"{jan} button:has-text('Novo esquema')")
        pg.wait_for_selector("dialog.esq-escolha button[data-modelo=prostata]")
        assert pg.locator("dialog.esq-escolha button.esq-modelo").count() >= 8
        assert pg.locator("dialog.esq-escolha button[data-editar]").count() == 0   # o cadastro mudou-se para Cadastros
        assert pg.locator("dialog.esq-escolha .esq-gerir").is_hidden()
        if foto:
            pg.screenshot(path=foto + "_modelos.png")
        pg.click("dialog.esq-escolha button[data-modelo=face_frente]")
        pg.wait_for_selector(tela)
        assert pg.evaluate(est)["ferramenta"] == "ponto"
        assert pg.locator(".esq-barra button[data-f=setor]").count() == 0      # a face não tem setores
        _tocar(pg, tela, (0.62, 0.50))
        assert _esperar(lambda: len(pg.evaluate(est)["marcas"]) == 1)
        pg.keyboard.type("nódulo hipoecoico de 4 mm")                         # o cursor já está na descrição
        pg.click(".esq-barra button[data-f=elipse]")
        pg.click(".esq-paleta button[data-cor='#1565c0']")
        _arrastar(pg, tela, (0.30, 0.20), (0.42, 0.28))
        pg.keyboard.type("placa")
        pg.click(".esq-barra button[data-f=seta]")
        pg.uncheck("#esq-numerar")
        _arrastar(pg, tela, (0.80, 0.80), (0.62, 0.66))
        pg.click(".esq-barra button[data-f=traco]")
        _arrastar(pg, tela, (0.40, 0.76), (0.56, 0.78), passos=12)
        pg.once("dialog", lambda d: d.accept("lesão actínica"))
        pg.click(".esq-barra button[data-f=texto]")
        _tocar(pg, tela, (0.06, 0.93))
        m = pg.evaluate(est)["marcas"]
        assert [x["tipo"] for x in m] == ["ponto", "elipse", "seta", "traco", "texto"]
        assert [x["n"] for x in m] == [1, 2, 0, 0, 0] and m[0]["texto"] == "nódulo hipoecoico de 4 mm" and m[1]["texto"] == "placa"
        assert m[1]["cor"] == "#1565c0" and abs(m[0]["p"][0][0] - 0.62) < 0.01 and len(m[3]["p"]) > 5
        assert m[4]["texto"] == "lesão actínica"
        pg.click(".esq-barra button[data-f=elipse]")
        _tocar(pg, tela, (0.5, 0.9))                                        # um toque sem arrastar não cria elipse
        assert len(pg.evaluate(est)["marcas"]) == 5
        pg.click(".esq-barra button[data-f=mover]")
        _arrastar(pg, tela, (0.62, 0.50), (0.70, 0.56))
        assert abs(pg.evaluate(est)["marcas"][0]["p"][0][0] - 0.70) < 0.012
        pg.click(".esq-barra button:has-text('Desfazer')")
        assert abs(pg.evaluate(est)["marcas"][0]["p"][0][0] - 0.62) < 0.012
        pg.click(".esq-barra button[data-f=apagar]")
        _tocar(pg, tela, (0.71, 0.73))
        assert [x["tipo"] for x in pg.evaluate(est)["marcas"]] == ["ponto", "elipse", "traco", "texto"]
        # ligar o ponto 1 à imagem aberta no visualizador
        pg.locator(".esq-item[data-i='0'] button.esq-ligar").click()
        assert _esperar(lambda: pg.locator(".esq-item[data-i='0'] button.esq-ligada").count() == 1)
        rot = pg.evaluate(est)["marcas"][0]["imagem"]["rotulo"]
        assert rot.startswith("série ") and len(repo.key_images(study)) == 1
        if foto:
            pg.screenshot(path=foto + "_face.png")
        pg.click("dialog.esq-janela button.primario")
        assert _esperar(lambda: pg.locator(f"{jan} button.esq-cartao").count() == 1)
        guardado = E.ler(repo, study)
        assert len(guardado) == 1 and [x["tipo"] for x in guardado[0]["marcas"]] == ["ponto", "elipse", "traco", "texto"]
        assert pg.evaluate("""() => { const c = document.querySelector('.esq-cartao canvas'); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
            for (let i = 0; i < d.length; i += 4) if (d[i] > 190 && d[i + 1] < 80 && d[i + 2] < 80) return true; return false; }""")
        # ---- a próstata: o clique no setor pinta com a categoria
        pg.click(f"{jan} button:has-text('Novo esquema')")
        pg.click("dialog.esq-escolha button[data-modelo=prostata]")
        pg.wait_for_selector(tela)
        pg.click(".esq-barra button[data-f=setor]")
        assert pg.locator(".esq-cats button[aria-checked=true]").inner_text() == "PI-RADS 4"
        _tocar(pg, tela, pg.evaluate("() => window.__ipeEsquema.setor('medio_PZpl_D')"))
        pg.click(".esq-cats button[data-cat='5']")
        _tocar(pg, tela, pg.evaluate("() => window.__ipeEsquema.setor('apice_PZpm_E')"))
        _tocar(pg, tela, pg.evaluate("() => window.__ipeEsquema.setor('base_CZ_D')"))
        _tocar(pg, tela, pg.evaluate("() => window.__ipeEsquema.setor('base_CZ_D')"))       # outro toque limpa
        assert pg.evaluate(est)["setores"] == {"medio_PZpl_D": "4", "apice_PZpm_E": "5"}
        if foto:
            pg.screenshot(path=foto + "_prostata.png")
        pg.click("dialog.esq-janela button.primario")
        assert _esperar(lambda: pg.locator(f"{jan} button.esq-cartao").count() == 2)
        # ---- gravar no exame, sem laudo nenhum; gravar de novo troca (não duplica)
        series_no_comeco = len(repo.series_for_study(study, ocultas=True))
        for _vez in (1, 2):
            pg.click(f"{jan} button:has-text('Gravar no exame')")
            assert _esperar(lambda: pg.inner_text(f"{jan} .esq-msg").strip().endswith("2"), 30), pg.inner_text(f"{jan} .esq-msg")
            assert _esperar(lambda: not pg.locator(f"{jan} button:has-text('Gravar no exame')").is_disabled())
            assert len(repo.series_for_study(study, ocultas=True)) == series_no_comeco + 2 and not repo.reports(study)
            # 0.100.115: a série das figuras entra na tira na hora (sem fechar e abrir); gravar de novo troca a série
            # na tira também (uma só, a nova)
            figs = next(x for x in repo.series_for_study(study, ocultas=True)
                        if x.modality != "SR" and "squema" in (x.description or ""))
            assert _esperar(lambda: pg.evaluate("""(d) => [...document.querySelectorAll('aside.tira button.serie')]
                .filter((b) => (b.title || '') === d).length""", figs.description) == 1, 15)
        if foto:
            pg.screenshot(path=foto + "_exame.png")
        # reabrir para corrigir e cancelar: nada muda
        pg.locator(f"{jan} button.esq-cartao").first.click()
        pg.wait_for_selector(tela)
        pg.click(".esq-barra button[data-f=ponto]")
        _tocar(pg, tela, (0.2, 0.9))
        pg.click("dialog.esq-janela button:has-text('Cancelar')")
        assert _esperar(lambda: pg.locator("dialog.esq-janela").count() == 0)
        assert len(E.ler(repo, study)[0]["marcas"]) == 4
        pg.click(f"{jan} button:has-text('Fechar')")
        # ---- no laudo: sem marcar, o PDF não leva as figuras; marcando, a legenda entra no texto e as figuras no PDF
        icone(pg, "Laudo")
        pg.wait_for_selector("aside.laudo #esq-no-laudo")
        assert pg.locator("aside.laudo details.esquemas-laudo").count() == 0     # o desenho saiu do laudo
        assert _esperar(lambda: "(2)" in pg.inner_text("aside.laudo .esquemas-no-laudo"))
        assert not pg.is_checked("#esq-no-laudo") and not pg.is_disabled("#esq-no-laudo")
        from ipe.reporting import esquemas_saida as ES
        assert ES.figuras(repo, study, so_do_laudo=True) == []                # fora do laudo: o PDF não leva
        pg.click("aside.laudo details.saidas-laudo > summary")
        pg.click("aside.laudo textarea.texto-laudo")
        pg.keyboard.press("Control+End")
        pg.check("#esq-no-laudo")
        assert _esperar(lambda: "Face — frente:" in pg.input_value("aside.laudo textarea.texto-laudo"))
        texto = pg.input_value("aside.laudo textarea.texto-laudo")
        assert f"Face — frente:\n1. nódulo hipoecoico de 4 mm ({rot})\n2. placa" in texto
        assert "PI-RADS 5: zona periférica posteromedial esquerda, ápice." in texto
        assert "PI-RADS 4: zona periférica posterolateral direita, terço médio." in texto
        assert E.no_laudo(repo, study)
        pg.uncheck("#esq-no-laudo")
        assert _esperar(lambda: not E.no_laudo(repo, study))
        pg.check("#esq-no-laudo")                                              # de novo: a legenda não se repete
        assert _esperar(lambda: E.no_laudo(repo, study))
        assert pg.input_value("aside.laudo textarea.texto-laudo").count("Face — frente:") == 1
        if foto:
            pg.screenshot(path=foto + "_laudo.png")
        with pg.expect_download() as dl:
            pg.click("aside.laudo button:has-text('Baixar PDF')")
        pdf = Path(dl.value.path()).read_bytes()
        assert pdf.startswith(b"%PDF") and len(pdf) > 40_000 and len(ES.figuras(repo, study, so_do_laudo=True)) == 2
        # ---- ao assinar: as figuras gravadas antes são trocadas e os esquemas vão no SR do laudo
        series_antes = len(repo.series_for_study(study, ocultas=True))
        pg.click("aside.laudo button:has-text('Assinar e liberar')")
        pg.click("aside.laudo .confirmar-laudo button:has-text('Assinar')")
        assert _esperar(lambda: repo.reports(study) and repo.reports(study)[0]["status"] == "final")
        assert _esperar(lambda: "4 objeto(s) DICOM guardado(s) no exame" in pg.inner_text("aside.laudo .msg-laudo"), 30), \
            pg.inner_text("aside.laudo .msg-laudo")
        series = repo.series_for_study(study, ocultas=True)
        assert len(series) == series_antes + 1                               # figuras novas, PDF e SR do laudo; sai o SR avulso
        assert not any(s.description == "Esquemas do laudo (SR)" for s in series)
        esq = next(s for s in series if s.description == "Esquemas do laudo")
        assert esq.num_images == 2 and esq.modality == "OT"
        sops = {i["sop_uid"] for i in repo.instances_for_series(esq.series_uid)}
        sr_serie = next(s for s in series if s.modality == "SR")
        sr = pydicom.dcmread(repo.instances_for_series(sr_serie.series_uid)[0]["path"])
        assert sr.SOPClassUID == "1.2.840.10008.5.1.4.1.1.88.22"
        citados = {r.ReferencedSOPInstanceUID for e in sr.CurrentRequestedProcedureEvidenceSequence
                   for se in e.ReferencedSeriesSequence for r in se.ReferencedSOPSequence}
        assert sops <= citados and len(citados) == 3                        # as 2 figuras e a imagem ligada ao ponto 1
        assert _esperar(lambda: pg.is_disabled("#esq-no-laudo"))               # laudo assinado: a escolha não muda
        b.close()
    assert not erros, erros


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_modelos_no_navegador(servidor, tmp_path):
    """0.100.74: os modelos ficam em Cadastros ▸ Modelos de esquema (quem configura): mandar uma imagem, modelo em
    branco, desenhar num modelo que existe, ocultar, restaurar. No exame, só se escolhe."""
    pw = pytest.importorskip("playwright.sync_api")
    from PIL import Image
    srv, repo = servidor, servidor.repo
    study = _estudo(srv)
    repo.save_user({"username": "med", "full_name": "Médica", "role": "medico", "active": True, "password": "medica12"})
    arq = tmp_path / "mao esquerda.png"
    Image.new("RGB", (600, 400), (235, 240, 250)).save(arq)
    erros = []
    foto = os.environ.get("IPE_ESQ_FOTO")
    tela = "dialog.esq-janela canvas.esq-tela"
    grade = ".cadastros .esq-grade-modelos"
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(f"http://127.0.0.1:{srv.port}/web/")
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        pg.wait_for_selector("button.cadastros-abrir")
        pg.click("button.cadastros-abrir")
        pg.click("button[data-aba=modelos]")
        pg.wait_for_selector(f"{grade} button[data-modelo=prostata]")
        assert pg.locator(f"{grade} .esq-gerir").is_visible()
        # mandar uma imagem
        pg.once("dialog", lambda d: d.accept("Mão esquerda"))
        pg.set_input_files(f"{grade} input[type=file]", str(arq))
        assert _esperar(lambda: any(m["nome"] == "Mão esquerda" for m in E.modelos(repo)), 20)
        mao = next(m for m in E.modelos(repo) if m["nome"] == "Mão esquerda")
        assert (mao["w"], mao["h"]) == (600, 400) and mao["png"]
        assert _esperar(lambda: pg.locator(f"{grade} button[data-modelo='{mao['id']}']").count() == 1)
        # desenhar por cima de um modelo do Ipê (a face) e salvar: vale para todos os exames
        pg.click(f"{grade} button[data-editar=face_frente]")
        pg.wait_for_selector(tela)
        assert pg.evaluate("() => window.__ipeEsquema.estado()")["ferramenta"] == "traco"
        assert pg.locator(".esq-barra button[data-f=setor]").count() == 0 and pg.locator("label.esq-numerar").is_hidden()
        _arrastar(pg, tela, (0.2, 0.95), (0.8, 0.95), passos=10)
        pg.fill("#esq-m-nome", "Face da clínica")
        if foto:
            pg.screenshot(path=foto + "_modelo.png")
        pg.click("dialog.esq-janela button:has-text('Salvar o modelo')")
        assert _esperar(lambda: (E.modelo("face_frente", repo) or {}).get("alterado"), 20)
        face = E.modelo("face_frente", repo)
        assert face["nome"] == "Face da clínica" and len(face["base"]) == 1 and face["base"][0]["tipo"] == "traco"
        assert face["base"][0]["cor"] == "#111111"                           # o desenho do modelo começa em preto
        assert _esperar(lambda: "Face da clínica" in pg.inner_text(f"{grade} button[data-modelo=face_frente]"))
        # modelo em branco, e ocultar a tireoide (o clique no cartão também abre o modelo)
        pg.once("dialog", lambda d: d.accept("Couro cabeludo"))
        pg.click(f"{grade} button:has-text('Novo modelo em branco')")
        assert _esperar(lambda: any(m["nome"] == "Couro cabeludo" for m in E.modelos(repo)), 20)
        pg.click(f"{grade} button[data-modelo=tireoide]")
        pg.wait_for_selector(tela)
        pg.check("#esq-m-oculto")
        pg.click("dialog.esq-janela button:has-text('Salvar o modelo')")
        assert _esperar(lambda: "tireoide" not in {m["id"] for m in E.modelos(repo)}, 20)
        assert _esperar(lambda: "(oculto)" in pg.inner_text(f"{grade} button[data-modelo=tireoide]"))
        if foto:
            pg.screenshot(path=foto + "_cadastro.png")
        # restaurar a face
        pg.click(f"{grade} button[data-editar=face_frente]")
        pg.wait_for_selector(tela)
        pg.click("dialog.esq-janela button:has-text('Restaurar o original')")
        pg.click("dialog.imp-janela:not(.esq-janela) button.primario")
        assert _esperar(lambda: not (E.modelo("face_frente", repo) or {}).get("alterado"), 20)
        # no exame: usar o modelo da imagem — o fundo aparece (não é branco puro) e o ponto grava
        pg.evaluate("() => { location.hash = '#/lista'; }")
        pg.wait_for_selector("table.lista tbody tr")
        pg.locator("table.lista tbody tr").first.dblclick()
        pg.wait_for_selector(".quadro canvas")
        icone(pg, "Esquema")
        pg.click("dialog.esq-do-exame button:has-text('Novo esquema')")
        pg.wait_for_selector(f"dialog.esq-escolha button[data-modelo='{mao['id']}']")
        assert pg.locator("dialog.esq-escolha button[data-editar]").count() == 0
        assert pg.locator("dialog.esq-escolha button[data-modelo=tireoide]").count() == 0   # oculto: não se escolhe
        pg.click(f"dialog.esq-escolha button[data-modelo='{mao['id']}']")
        pg.wait_for_selector(tela)
        assert _esperar(lambda: pg.evaluate("""() => { const c = document.querySelector('canvas.esq-tela');
            const d = c.getContext('2d').getImageData(5, 5, 1, 1).data; return d[0] === 235 && d[2] === 250; }"""))
        _tocar(pg, tela, (0.5, 0.5))
        pg.click("dialog.esq-janela button.primario")
        assert _esperar(lambda: len(E.ler(repo, study)) == 1 and E.ler(repo, study)[0]["modelo"] == mao["id"])
        pg.close()
        # a médica: desenha no exame, mas não tem Cadastros
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(f"http://127.0.0.1:{srv.port}/web/")
        pg.fill("#usuario", "med")
        pg.fill("#senha", "medica12")
        pg.click("button[type=submit]")
        pg.wait_for_selector("form.filtros")
        assert pg.locator("button.cadastros-abrir").is_hidden()
        b.close()
    assert not erros, erros


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_esquema_com_o_dedo(servidor):
    """Num tablet, com o dedo: o toque marca o ponto e o arrasto desenha o traço (sem rolar a página)."""
    pw = pytest.importorskip("playwright.sync_api")
    srv = servidor
    study = _estudo(srv)
    E.gravar(srv.repo, study, [{"modelo": "mamas", "marcas": []}], "admin")
    erros = []
    tela = "dialog.esq-janela canvas.esq-tela"
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        ctx = b.new_context(viewport={"width": 1700, "height": 1000}, has_touch=True)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: erros.append(str(e)))
        _entrar(pg, srv)
        # com toque os ícones são maiores e o Laudo pode ir para o menu "mais": o clique vai direto no botão
        pg.evaluate("() => document.querySelector(\"nav.barra button[aria-label='Esquema']\").click()")
        pg.wait_for_selector("dialog.esq-do-exame button.esq-cartao")
        pg.locator("dialog.esq-do-exame button.esq-cartao").first.click()
        pg.wait_for_selector(tela)
        cx = pg.locator(tela).bounding_box()
        assert cx["width"] > 300 and cx["x"] >= 0 and cx["x"] + cx["width"] <= 1700 and cx["y"] + cx["height"] <= 1000
        pg.touchscreen.tap(cx["x"] + 0.27 * cx["width"], cx["y"] + 0.40 * cx["height"])
        assert _esperar(lambda: len(pg.evaluate("() => window.__ipeEsquema.estado()")["marcas"]) == 1)
        m = pg.evaluate("() => window.__ipeEsquema.estado()")["marcas"][0]
        assert m["tipo"] == "ponto" and m["n"] == 1 and abs(m["p"][0][0] - 0.27) < 0.02
        assert pg.evaluate("() => getComputedStyle(document.querySelector('canvas.esq-tela')).touchAction") == "none"
        pg.click("dialog.esq-janela button.primario")
        assert _esperar(lambda: len(E.ler(srv.repo, study)[0]["marcas"]) == 1)
        b.close()
    assert not erros, erros
