from pathlib import Path
import sys
"""0.99.91 (W0): o visualizador web de ponta a ponta — o Chromium do Playwright abre o site num servidor central de
teste, entra, busca, abre um exame e mexe nos quadros. Pula se o site não foi construído (web_dist) ou se não há
Playwright."""
import json
import time

import numpy as np
import pytest

from ipe.central import web as WEB  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from _web_ui import aba, botoes, espessura, ferramenta, icone, layout, menu, quadros  # noqa: E402,F401

pytestmark = pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")


@pytest.fixture()
def servidor(env, sample_dir, tmp_path):
    from ipe.auth.backend import LocalAuth
    from ipe.central.server import CentralServer
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    pasta = tmp_path / "jls"
    _mamo_jpeg_ls(pasta)
    Importer(db, paths.storage).import_paths([sample_dir, pasta])
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    st = Settings(paths.settings_file)
    st.set("language", "pt-BR")
    st.set("viewer.wl_presets", {"1": ["Pulmão", 1500, -600], "2": ["Mediastino", 400, 40]})
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.settings = st
    srv.start()
    yield repo, srv
    srv.stop()


def _mamo_jpeg_ls(pasta):
    """Uma mamografia em JPEG-LS com VOI LUT sigmoide, como a da GE (ficava branca no carregador)."""
    import pydicom
    from pydicom.uid import JPEGLSLossless, generate_uid

    from ipe.core.sample_data import _base, _mono, _save
    pat = {"name": "JLS^MAMO", "id": "JLS1", "birth": "19700101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20261108", "accession": "JLS1", "description": "MAMOGRAFIA JLS",
             "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 1, "description": "L CC"}
    ds = _base("1.2.840.10008.5.1.4.1.1.1.2", pat, study, series, "MG")
    yy, xx = np.mgrid[0:256, 0:200]
    px = np.where((xx - 200) ** 2 + (yy - 128) ** 2 < 150 ** 2, 2000 + (yy % 40) * 20, 50).astype(np.uint16)
    _mono(ds, px, signed=False)
    ds.BitsStored, ds.HighBit = 12, 11
    ds.WindowCenter, ds.WindowWidth, ds.VOILUTFunction = 2400, 900, "SIGMOID"
    try:
        ds.compress(JPEGLSLossless, encoding_plugin="pyjpegls")
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"sem codificador JPEG-LS: {e}")
    _save(ds, pasta)
    assert pydicom.dcmread(next(pasta.rglob("*.dcm"))).file_meta.TransferSyntaxUID == JPEGLSLossless


def _navegador():
    pw = pytest.importorskip("playwright.sync_api")
    return pw.sync_playwright()


def _pixels(pg, i=0):
    """Média e desvio dos pixels do canvas do quadro i (o que a pessoa vê)."""
    from io import BytesIO

    from PIL import Image
    png = pg.locator(".quadro .tela").nth(i).screenshot()
    a = np.asarray(Image.open(BytesIO(png)).convert("L"), float)
    return a.mean(), a.std()


def _esperar(cond, segundos=20):
    fim = time.time() + segundos
    while time.time() < fim:
        if cond():
            return True
        time.sleep(0.2)
    return False


def test_login_lista_exame_e_quadros(servidor):
    repo, srv = servidor
    erros = []
    with _navegador() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1400, "height": 850})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(f"http://127.0.0.1:{srv.port}/web/")
        # senha errada: a mensagem, sem a janela de senha do navegador
        pg.fill("#usuario", "admin")
        pg.fill("#senha", "errada")
        pg.click("button[type=submit]")
        assert _esperar(lambda: pg.inner_text(".erro").strip() != "")      # antes do login, na língua do navegador
        pg.fill("#senha", "admin123")
        pg.click("button[type=submit]")
        pg.wait_for_selector("table.lista tbody tr")
        assert pg.locator("table.lista tbody tr").count() >= 5
        assert "Não destinado a uso diagnóstico" in pg.inner_text("body")          # em português (o do servidor)
        # busca
        pg.fill("#busca", "CINTILO")
        pg.click("button:has-text('Buscar')")
        assert _esperar(lambda: pg.locator("table.lista tbody tr").count() == 3)
        pg.fill("#busca", "")
        pg.select_option("select[title=Modalidade]", "CT")
        pg.click("button:has-text('Buscar')")
        assert _esperar(lambda: all("CT" in t for t in pg.locator("table.lista tbody tr td:nth-child(5)").all_inner_texts()))
        # abrir a TC
        pg.locator("table.lista tbody tr").first.dblclick()
        pg.wait_for_selector(".quadro canvas")
        assert _esperar(lambda: "Im " in pg.locator(".quadro").first.inner_text())
        assert "TESTE" in pg.locator(".quadro").first.inner_text()
        media, dp = _pixels(pg)
        assert dp > 5, "o quadro ficou liso (nada desenhado)"
        # rolar com a roda muda o corte
        antes = pg.locator(".quadro .canto.ie").first.inner_text()
        pg.locator(".quadro .tela").first.hover()
        for _ in range(3):
            pg.mouse.wheel(0, 120)
        assert _esperar(lambda: pg.locator(".quadro .canto.ie").first.inner_text() != antes)
        # janela pronta (do servidor) e inverter
        aba(pg, "Imagem")
        opcoes = pg.locator(".corpo-aba button.linha").all_inner_texts()
        assert any("Pulmão" in o for o in opcoes)
        pg.locator(".corpo-aba button.linha", has_text="Pulmão").first.click()
        assert _esperar(lambda: "1500 / -600" in pg.locator(".quadro .canto.id").first.inner_text())
        icone(pg, 'Inverter')
        assert _esperar(lambda: "Inverter" in pg.locator(".quadro .canto.id").first.inner_text())
        # layout 2×2
        layout(pg, "2x2")
        assert _esperar(lambda: pg.locator(".quadro").count() == 4)
        # cine liga e desliga
        icone(pg, "Cine")
        assert _esperar(lambda: pg.get_attribute("nav.barra button[aria-label='Cine']", "aria-pressed") == "true")
        icone(pg, "Cine")
        assert _esperar(lambda: pg.get_attribute("nav.barra button[aria-label='Cine']", "aria-pressed") == "false")
        # a abertura ficou na auditoria
        assert repo.access_log(user="admin", action="web_abriu")
        # voltar, abrir a mamografia em JPEG-LS (sigmoide): não pode ficar branca
        icone(pg, 'Voltar à lista')
        pg.wait_for_selector("table.lista tbody tr")
        # 0.100.15: a busca anterior (modalidade CT) volta com a lista; a mamografia pede todas
        assert pg.input_value("select[title=Modalidade]") == "CT"
        pg.select_option("select[title=Modalidade]", "")
        pg.fill("#busca", "JLS")
        pg.click("button:has-text('Buscar')")
        assert _esperar(lambda: pg.locator("table.lista tbody tr").count() == 1)
        pg.locator("table.lista tbody tr").first.dblclick()
        # 0.99.98: a mamografia abre no protocolo; sair dele volta ao visualizador comum (a série no quadro 1)
        pg.wait_for_selector(".barra-mg")
        pg.click(".barra-mg button[aria-label='Sair do modo mamografia']")
        assert _esperar(lambda: pg.locator(".barra-mg").count() == 0)
        assert _esperar(lambda: "J " in pg.locator(".quadro .canto.id").first.inner_text())
        info = json.loads(pg.evaluate("""() => { const im = window.__ipeGrade.viewport(0).getCornerstoneImage();
            return JSON.stringify({voi: im.voiLUTFunction, ts: im.transferSyntaxUID, max: im.maxPixelValue}); }"""))
        # 0.99.96: o JPEG-LS guardado vai para a rede como HTJ2K sem perda (a cópia de envio)
        assert info["voi"] == "SIGMOID" and info["ts"] == "1.2.840.10008.1.2.4.202" and info["max"] > 2000
        media, dp = _pixels(pg)
        assert media < 230 and dp > 5, (media, dp)
        # 0.100.5: "Sair" com o exame aberto volta à lista; na lista, sai (volta ao login)
        pg.click("button.sair")
        pg.wait_for_selector("table.lista tbody tr")
        pg.click("button.sair")
        pg.wait_for_selector("#usuario")
        b.close()
    assert not erros, erros
