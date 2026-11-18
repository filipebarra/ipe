"""0.100.55: anexar PDF e imagens ao exame pelo Ipê Web (arrastar ou botão) — exame fabricado, nada de paciente."""
import base64
import time
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_web_mamografia import _abrir, _token, servidor_mg  # noqa: F401
from test_web_mpr import _esperar

from ipe.central import web as WEB

PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
       b"trailer<</Root 1 0 R>>\n%%EOF\n")


def _png() -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 30, 30)).save(b, "PNG")
    return b.getvalue()


def _api(srv, rota, corpo=None, tok=None, cru=False):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}{rota}", method="POST" if corpo is not None else "GET",
                                 data=json.dumps(corpo).encode() if corpo is not None else None,
                                 headers={"Authorization": f"Bearer {tok or _token(srv)}",
                                          "Content-Type": "application/json"})
    r = urllib.request.urlopen(req).read()
    return r if cru else json.loads(r)


def test_api(servidor_mg):
    srv = servidor_mg
    atual, _ant = srv.estudos
    tk = _token(srv)
    antes = {x.series_uid for x in srv.repo.series_for_study(atual)}
    assert _api(srv, f"/api/web/documentos?study={atual}", tok=tk)["documentos"] == []
    r = _api(srv, "/api/web/anexos", {"study": atual, "arquivos": [
        {"nome": "pedido médico.pdf", "dados": base64.b64encode(PDF).decode()},
        {"nome": "../../foto.png", "dados": base64.b64encode(_png()).decode()},
        {"nome": "laudo.docx", "dados": base64.b64encode(b"PK").decode()}]}, tok=tk)
    assert r["n"] == 2 and len(r["series"]) == 2, r
    assert len(r["avisos"]) == 1 and "laudo.docx" in r["avisos"][0]
    novas = [x for x in srv.repo.series_for_study(atual) if x.series_uid not in antes]
    assert sorted(x.modality for x in novas) == ["DOC", "OT"]
    docs = _api(srv, f"/api/web/documentos?study={atual}", tok=tk)["documentos"]
    assert len(docs) == 1 and docs[0]["titulo"].startswith("pedido médico")
    pdf = _api(srv, f"/api/web/documento?study={atual}&sop={docs[0]['sop']}", tok=tk, cru=True)
    assert pdf.startswith(b"%PDF") and pdf.rstrip().endswith(b"%%EOF")
    # o nome do arquivo não leva caminho
    ot = next(x for x in novas if x.modality == "OT")
    import pydicom
    ds = pydicom.dcmread(srv.repo.files_for_study(atual, [ot.series_uid])[0])
    assert str(ds.ImageComments) == "foto.png" and ds.PatientID == srv.repo.study_info(atual)["patient_id"]
    with pytest.raises(urllib.error.HTTPError) as e:
        _api(srv, "/api/web/anexos", {"study": "1.2.3.4", "arquivos": [{"nome": "a.pdf", "dados": ""}]}, tok=tk)
    assert e.value.code in (400, 403)  # exame que não existe


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_arrastar_no_navegador(servidor_mg):
    pw = pytest.importorskip("playwright.sync_api")
    atual, _ant = servidor_mg.estudos
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        dialogos = []
        pg.on("dialog", lambda d: (dialogos.append(d.message), d.accept()))
        _abrir(pg, servidor_mg, atual)
        pg.wait_for_selector(".documentos")
        assert pg.locator(".documentos button.doc").count() == 0
        n_series = pg.locator(".tira .series button.serie").count()
        png = base64.b64encode(_png()).decode()
        pdf = base64.b64encode(PDF).decode()
        # 0.100.70: arrastar a miniatura de uma série não é anexar — o navegador põe a imagem da miniatura no
        # arrasto ("Files"), e a capa "Solte para anexar" não pode aparecer nem o arquivo ser enviado
        pedidos = []
        pg.on("request", lambda r: pedidos.append(r.url) if "/api/web/anexos" in r.url and r.method == "POST" else None)
        pg.evaluate("""(png) => {
          const dt = new DataTransfer();
          dt.items.add(new File([Uint8Array.from(atob(png), (c) => c.charCodeAt(0))], 'miniatura.png', {type: 'image/png'}));
          dt.setData('application/x-ipe-serie', '1.2.3');
          const alvo = document.querySelector('.grade');
          alvo.dispatchEvent(new DragEvent('dragover', {dataTransfer: dt, bubbles: true, cancelable: true}));
          if (document.querySelector('.capa-soltar')) throw new Error('capa de anexar ao arrastar uma série');
          alvo.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true}));
          // o arrasto que começou na própria página (qualquer imagem dela) também não é anexo
          const so = new DataTransfer();
          so.items.add(new File([new Uint8Array(4)], 'x.png', {type: 'image/png'}));
          const mini = document.querySelector('.tira .series button.serie');
          mini.dispatchEvent(new DragEvent('dragstart', {dataTransfer: so, bubbles: true, cancelable: true}));
          alvo.dispatchEvent(new DragEvent('dragover', {dataTransfer: so, bubbles: true, cancelable: true}));
          if (document.querySelector('.capa-soltar')) throw new Error('capa de anexar num arrasto da página');
          mini.dispatchEvent(new DragEvent('dragend', {dataTransfer: so, bubbles: true}));
        }""", png)
        time.sleep(0.5)
        assert not pedidos and not dialogos and pg.locator(".tira .series button.serie").count() == n_series
        # de verdade, com o mouse: a miniatura da segunda série vai para o quadro e nada de capa
        if n_series >= 2:
            pg.drag_and_drop(".tira .series button.serie >> nth=1", ".grade")
            assert pg.locator(".capa-soltar").count() == 0 and not pedidos and not dialogos
        # arrastar dois arquivos do computador para cima do exame
        pg.evaluate("""([png, pdf]) => {
          const arq = (b64, nome, tipo) => new File([Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))], nome, {type: tipo});
          const dt = new DataTransfer();
          dt.items.add(arq(png, 'foto.png', 'image/png'));
          dt.items.add(arq(pdf, 'pedido.pdf', 'application/pdf'));
          const alvo = document.querySelector('.grade');
          alvo.dispatchEvent(new DragEvent('dragover', {dataTransfer: dt, bubbles: true, cancelable: true}));
          if (!document.querySelector('.capa-soltar')) throw new Error('sem a capa de soltar');
          alvo.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true}));
        }""", [png, pdf])
        assert _esperar(lambda: "gravado" in (pg.text_content(".area > .estado") or ""), 30), \
            pg.text_content(".area > .estado")
        assert dialogos and "2" in dialogos[0]
        assert pg.locator(".capa-soltar").count() == 0
        assert _esperar(lambda: pg.locator(".tira .series button.serie").count() == n_series + 1, 15)
        assert _esperar(lambda: pg.locator(".documentos button.doc").count() == 1, 15)
        # o PDF abre numa aba nova (o Chromium sem tela baixa o PDF em vez de mostrar: confere a aba e o PDF)
        with pg.context.expect_page() as nova, pg.expect_response(lambda r: "/api/web/documento?" in r.url) as resp:
            pg.click(".documentos button.doc")
        assert nova.value is not None
        assert resp.value.status == 200  # o conteúdo é conferido em test_api
        b.close()
    assert not erros, erros
