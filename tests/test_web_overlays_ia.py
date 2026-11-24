"""0.100.112: o Ipê Web mostra as marcações das IAs como o Ipê de mesa — as linhas da cefalometria e dos índices do
crânio (guardadas na imagem de conferência) e as SEG da IA, já ao abrir o exame."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent))
from test_cefalometria import CF, _exame  # noqa: E402


def _cefalometria(env, tmp_path):
    from PySide6.QtWidgets import QApplication

    from ipe.ai import cefalometria_saida as CS
    from ipe.ai import totalseg as TS
    from ipe.imaging.series import FrameCache
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie = _exame(env, tmp_path)
    t = TS.Trabalho(repo, FrameCache(256), None, uid, serie, simular=True)
    t.tarefas_proprias, t.min_cortes, t.modalidades = CF.tarefas, CF.MIN_CORTES, ("CT",)
    t.preparar()
    try:
        t.rodar_aqui()
        rot, versao, _s = t.ler_rotulos()
        CS.gravar(t, CF.calcular(t.vol, rot), versao, db, paths.storage, repo=repo)
    finally:
        t.limpar()
    return uid, serie


def _s():
    return SimpleNamespace(can=lambda p: True, username="admin")


def test_overlays_do_web_tem_as_linhas_da_cefalometria(env, tmp_path):
    from ipe.central import web as WEB
    paths, db, repo = env
    uid, serie = _cefalometria(env, tmp_path)
    r = WEB.overlays(repo, _s(), {"study": [uid]}, lambda s, u: True, None)
    linhas = [o for o in r["objetos"] if o["fonte"] == CF.FONTE_OVERLAY]
    assert len(linhas) == 1, [o["fonte"] for o in r["objetos"]]
    textos = [p.get("texto") for p in linhas[0]["planos"]]
    assert "Go–Me" in textos and linhas[0]["ia"]
    assert all(len(p["pontos3d"]) == 2 for p in linhas[0]["planos"])


def test_seg_da_cefalometria_vira_mapa_na_serie_de_origem(env, tmp_path):
    from ipe.central import web as WEB
    paths, db, repo = env
    uid, serie = _cefalometria(env, tmp_path)
    seg = next(s for s in repo.series_for_study(uid) if s.description == CF.DESC_SEG)
    r = WEB.seg_mapa(repo, _s(), {"study": [uid], "series": [seg.series_uid]}, lambda s, u: True)
    assert r["ref_series"] == serie and r["fatias"] and r["segmentos"]


def test_no_navegador_as_linhas_e_a_seg_aparecem_ao_abrir(env, tmp_path):
    """Abrir o exame no Ipê Web depois da IA: as linhas da cefalometria no overlay e a SEG da IA já ligada."""
    import time

    import pytest

    from ipe.auth.backend import LocalAuth
    from ipe.central import web as WEB
    from ipe.central.server import CentralServer
    if not WEB.site_instalado():
        pytest.skip("o site (web_dist) não foi construído")
    pw = pytest.importorskip("playwright.sync_api")
    paths, db, repo = env
    uid, serie = _cefalometria(env, tmp_path)
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()

    def esperar(f, t=40):
        fim = time.time() + t
        while time.time() < fim:
            try:
                if f():
                    return True
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.25)
        return False
    erros = []
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            pg.on("pageerror", lambda e: erros.append(str(e)))
            pg.goto(f"http://127.0.0.1:{srv.port}/web/")
            pg.fill("#usuario", "admin")
            pg.fill("#senha", "admin123")
            pg.click("button[type=submit]")
            pg.wait_for_selector("table.lista tbody tr")
            pg.locator("table.lista tbody tr").first.dblclick()
            pg.wait_for_selector(".quadro canvas")
            assert esperar(lambda: pg.evaluate("""() => (window.__ipeOverlay.objetos || [])
                .some((o) => o.fonte === 'Cefalometria' && o.planos.length > 0)""")), "sem as linhas"
            assert esperar(lambda: pg.evaluate("() => !!window.__ipeOverlay.seg")), "a SEG não ligou sozinha"
            b.close()
    finally:
        srv.stop()
    assert not erros, erros
