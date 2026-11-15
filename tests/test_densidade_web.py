"""0.100.50: a densidade mamária no Ipê Web — medir no servidor (a rede da NYU, aqui de mentira), ver, confirmar
(só com a permissão de laudar) e mandar a composição ao laudo. Exames fabricados, nada de paciente."""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_web_mamografia import _abrir, _token, servidor_mg  # noqa: E402,F401
from test_web_mpr import _esperar  # noqa: E402

from ipe.central import web as WEB  # noqa: E402
from ipe.imaging import densidade_revisao as R  # noqa: E402


@pytest.fixture()
def rede(monkeypatch):
    from ipe.ai import densidade_nyu as N
    vezes = []
    monkeypatch.setattr(N, "disponivel", lambda dados=None: (True, ""))

    def do_exame(vistas, dados=None):
        vezes.append(sorted(vistas))
        return np.array([0.05, 0.15, 0.7, 0.1]), ""
    monkeypatch.setattr(N, "do_exame", do_exame)
    return vezes


def _api(srv, rota, corpo=None, tok=None):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}{rota}", method="POST" if corpo is not None else "GET",
                                 data=json.dumps(corpo).encode() if corpo is not None else None,
                                 headers={"Authorization": f"Bearer {tok or _token(srv)}",
                                          "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def test_medir_ver_e_confirmar(servidor_mg, rede):
    srv = servidor_mg
    atual, _ant = srv.estudos
    tk = _token(srv)
    r = _api(srv, f"/api/web/densidade?study={atual}", tok=tk)
    assert r["medida"] is None and r["pode_confirmar"]
    r = _api(srv, "/api/web/densidade/medir", {"study": atual}, tk)
    m = r["medida"]
    assert m["nyu"] == "c" and m["nyu_probs"] == [0.05, 0.15, 0.7, 0.1] and not m.get("categoria")
    assert len(rede) == 1 and rede[0] == ["L-CC", "L-MLO", "R-CC", "R-MLO"]     # as quatro, sem a tomo
    assert "heterogeneamente" in r["frases"]["c"]
    r = _api(srv, "/api/web/densidade/medir", {"study": atual}, tk)              # guardada: não mede de novo
    assert len(rede) == 1 and r["medida"]["nyu"] == "c"
    r = _api(srv, "/api/web/densidade/confirmar", {"study": atual, "categoria": "d"}, tk)
    assert r["medida"]["categoria"] == "d" and r["medida"]["estado"] == "editado" and r["medida"]["revisor"] == "admin"
    assert R.guardada(srv.repo, atual)["categoria"] == "d"                       # a mesma do Ipê de mesa
    assert srv.repo.revisoes_densidade("admin")[0]["categoria"] == "d"
    r = _api(srv, "/api/web/densidade/medir", {"study": atual, "de_novo": True}, tk)   # medir de novo mantém
    assert len(rede) == 2 and r["medida"]["categoria"] == "d"
    assert srv.repo.access_log(limit=10, action="densidade", study_uid=atual)
    with pytest.raises(urllib.error.HTTPError) as e:
        _api(srv, "/api/web/densidade/confirmar", {"study": atual, "categoria": "x"}, tk)
    assert e.value.code == 400


def test_confirmar_pede_permissao_de_laudar(servidor_mg, rede):
    srv = servidor_mg
    atual, _ant = srv.estudos
    srv.repo.save_user({"username": "tec", "full_name": "Técnica", "role": "tecnico", "password": "tecnico1"})
    srv.repo.set_app_setting("roles", {"tecnico": ["view"]})
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}/api/login", method="POST",
                                 data=json.dumps({"username": "tec", "password": "tecnico1"}).encode(),
                                 headers={"Content-Type": "application/json"})
    tk = json.loads(urllib.request.urlopen(req).read())["token"]
    r = _api(srv, "/api/web/densidade/medir", {"study": atual}, tk)
    assert r["medida"]["nyu"] == "c" and not r["pode_confirmar"]
    with pytest.raises(urllib.error.HTTPError) as e:
        _api(srv, "/api/web/densidade/confirmar", {"study": atual, "categoria": "c"}, tk)
    assert e.value.code == 403


@pytest.mark.skipif(not WEB.site_instalado(), reason="o site (web_dist) não foi construído")
def test_no_navegador(servidor_mg, rede):
    pw = pytest.importorskip("playwright.sync_api")
    atual, _ant = servidor_mg.estudos
    erros = []
    with pw.sync_playwright() as p:
        b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        pg = b.new_page(viewport={"width": 1400, "height": 900})
        pg.on("pageerror", lambda e: erros.append(str(e)))
        _abrir(pg, servidor_mg, atual)
        pg.click("nav.barra button[aria-label='Densidade mamária']")
        assert _esperar(lambda: "C — heterogeneamente densa" in (pg.text_content(".painel-densidade .rede") or ""), 30)
        assert pg.is_checked(".painel-densidade input[value=c]")                # de saída, a da rede
        assert "C 70%" in pg.text_content(".painel-densidade .probs")
        pg.check(".painel-densidade input[value=d]")
        pg.click(".painel-densidade button:has-text('Confirmar e mandar ao laudo')")
        assert _esperar(lambda: "Confirmado: D" in (pg.text_content(".painel-densidade .estado") or ""), 30)
        assert _esperar(lambda: pg.evaluate("() => window.__ipeLaudo?.estadoAtual().campos.composition") == "d", 30)
        assert "composição foi para o laudo" in pg.text_content(".painel-densidade .estado")
        b.close()
    assert R.guardada(servidor_mg.repo, atual)["categoria"] == "d"
    assert not erros, erros
    time.sleep(0.1)
