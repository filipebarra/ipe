"""0.100.51: calcificações vasculares no Ipê Web — medir no servidor (rede de mentira), prévias, confirmar o grau e
mandar ao laudo. Exames fabricados, nada de paciente."""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_web_mamografia import _abrir, _token, servidor_mg  # noqa: E402,F401
from test_web_mpr import _esperar  # noqa: E402

from ipe.ai import calc_vascular as C  # noqa: E402
from ipe.central import web as WEB  # noqa: E402


@pytest.fixture()
def rede(monkeypatch):
    vezes = []
    monkeypatch.setattr(C, "disponivel", lambda dados=None: (True, ""))

    def mapa(img, dados=None, stop=None):
        vezes.append(img.shape)
        p = np.zeros(img.shape, np.float32)
        p[img.shape[0] // 4:img.shape[0] // 4 + 300, img.shape[1] // 2:img.shape[1] // 2 + 3] = 0.9
        return p
    monkeypatch.setattr(C, "mapa", mapa)
    return vezes


def _api(srv, rota, corpo=None, tok=None, cru=False):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}{rota}", method="POST" if corpo is not None else "GET",
                                 data=json.dumps(corpo).encode() if corpo is not None else None,
                                 headers={"Authorization": f"Bearer {tok or _token(srv)}",
                                          "Content-Type": "application/json"})
    r = urllib.request.urlopen(req).read()
    return r if cru else json.loads(r)


def test_api(servidor_mg, rede):
    srv = servidor_mg
    atual, _ant = srv.estudos
    tk = _token(srv)
    assert _api(srv, f"/api/web/calcvasc?study={atual}", tok=tk)["medida"] is None
    r = _api(srv, "/api/web/calcvasc/medir", {"study": atual}, tk)
    m = r["medida"]
    assert set(m["vistas"]) == {"R-CC", "L-CC", "R-MLO", "L-MLO"} and m["sugestao"] in C.GRAUS
    assert len(m["imagens"]) == 4 and {x["chave"] for x in m["imagens"]} == set(m["vistas"])
    assert all(isinstance(i, int) for i in m["vistas"].values())
    assert set(m["escalas"]) >= {"margolies", "csbi", "loberant", "bacss"}  # 0.100.55
    assert "mascara" not in json.dumps(r)                                    # o navegador não precisa da máscara
    n = len(rede)
    _api(srv, "/api/web/calcvasc/medir", {"study": atual}, tk)
    assert len(rede) == n                                                   # guardada: não mede de novo
    png = _api(srv, f"/api/web/calcvasc/previa?study={atual}&i={m['vistas']['R-CC']}", tok=tk, cru=True)
    assert png[:4] == b"\x89PNG"
    r = _api(srv, "/api/web/calcvasc/confirmar", {"study": atual, "grau": "acentuada"}, tk)
    assert r["medida"]["grau"] == "acentuada" and r["medida"]["revisor"] == "admin"
    assert C.guardada(srv.repo, atual)["grau"] == "acentuada"
    with pytest.raises(urllib.error.HTTPError) as e:
        _api(srv, "/api/web/calcvasc/confirmar", {"study": atual, "grau": "x"}, tk)
    assert e.value.code == 400
    with pytest.raises(urllib.error.HTTPError) as e:
        _api(srv, f"/api/web/calcvasc/previa?study={atual}&i=99", tok=tk, cru=True)
    assert e.value.code == 400


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_no_navegador(servidor_mg, rede):
    pw = pytest.importorskip("playwright.sync_api")
    atual, _ant = servidor_mg.estudos
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        _abrir(pg, servidor_mg, atual)
        pg.click("nav.barra button[aria-label='Calcificações vasculares']")
        assert _esperar(lambda: "Sugestão" in (pg.text_content(".painel-calcvasc .rede") or ""), 60)
        assert _esperar(lambda: pg.evaluate(
            "() => [...document.querySelectorAll('.painel-calcvasc img')].filter(i => i.naturalWidth > 0).length") == 4,
            30)
        # 0.100.55: as quatro escalas
        assert pg.locator(".painel-calcvasc .escalas tr").count() == 4
        assert "Margolies" in pg.text_content(".painel-calcvasc .escalas")
        pg.check(".painel-calcvasc input[value=moderada]")
        pg.click(".painel-calcvasc button:has-text('Confirmar e mandar ao laudo')")
        assert _esperar(lambda: "Confirmado: Moderada" in (pg.text_content(".painel-calcvasc .estado") or ""), 30)
        assert "A frase foi para o laudo" in pg.text_content(".painel-calcvasc .estado")
        b.close()
    assert C.guardada(servidor_mg.repo, atual)["grau"] == "moderada"
    assert not erros, erros


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
@pytest.mark.parametrize("tela", [(1366, 768), (1920, 1080)])
def test_painel_grande_e_redimensionavel(servidor_mg, rede, tela):
    """0.100.55: o painel abria com 260 px e cortava as prévias, os graus e os botões; agora abre grande, cabe na tela,
    nada fica cortado de lado e o médico puxa o canto para mudar o tamanho (lembrado no navegador)."""
    pw = pytest.importorskip("playwright.sync_api")
    atual, _ant = servidor_mg.estudos
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": tela[0], "height": tela[1]})
        _abrir(pg, servidor_mg, atual)

        def abrir():
            bt = pg.locator("nav.barra button[aria-label='Calcificações vasculares']")
            if "transbordou" in (bt.get_attribute("class") or ""):  # tela menor: o botão está no "»"
                pg.click("nav.barra .mais")
                pg.locator(".menu .menu-item:has-text('Calcificações vasculares')").click()
            else:
                bt.click()
            assert _esperar(lambda: "Sugestão" in (pg.text_content(".painel-calcvasc .rede") or ""), 60)
            assert _esperar(lambda: pg.evaluate(
                "() => [...document.querySelectorAll('.painel-calcvasc img')].filter(i => i.naturalWidth > 0).length")
                == 4, 30)

        abrir()
        m = pg.evaluate("""() => { const m = document.querySelector('.menu.painel'); const r = m.getBoundingClientRect();
          const cs = getComputedStyle(m);
          return {w: r.width, h: r.height, l: r.left, r: r.right, b: r.bottom, sw: m.scrollWidth, cw: m.clientWidth,
                  resize: cs.resize, img: document.querySelector('.painel-calcvasc img').getBoundingClientRect().height,
                  radios: [...m.querySelectorAll('input[type=radio]')].filter(x => {
                    const q = x.getBoundingClientRect(); return q.width > 0 && q.right <= r.right; }).length}; }""")
        assert m["w"] >= 600 and m["l"] >= 0 and m["r"] <= tela[0] and m["b"] <= tela[1], m
        assert m["sw"] <= m["cw"] + 1, m  # nada para o lado
        assert m["resize"] == "both" and m["radios"] == 4 and m["img"] >= 150, m

        # o médico puxa o canto: o tamanho fica e volta na próxima vez
        pg.evaluate("() => { const m = document.querySelector('.menu.painel'); m.style.width = '700px';"
                    " m.style.height = '600px'; }")
        pg.wait_for_timeout(600)
        pg.keyboard.press("Escape")
        assert _esperar(lambda: pg.query_selector(".menu.painel") is None, 5)
        abrir()
        w, h = pg.evaluate("() => { const r = document.querySelector('.menu.painel').getBoundingClientRect();"
                           " return [r.width, r.height]; }")
        assert abs(w - 700) <= 2 and abs(h - min(600, tela[1] - 8)) <= 2, (w, h)
        b.close()
