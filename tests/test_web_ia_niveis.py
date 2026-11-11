"""0.100.14: a IA aparece no navegador e nas miniaturas.

Relato dele: "cliquei em IA pelo web e processou, porém não está aparecendo; diz que não tem IA no exame". A coluna
grava uma SEG "só rótulo" (os nomes dos níveis) que o overlay do navegador pulava. Agora ela vai como nomes em 3D
(nuvem de pontos em mm) e o navegador põe o nome no centro dos pontos que o plano corta — como o Ipê. E as séries
com IA ganham o selo "IA" nas miniaturas (Ipê e navegador).
"""
import numpy as np

from test_coluna import DZ, _exame, _fantoma, _trabalho

from ipe.ai import coluna as COL
from ipe.ai import series_ia as SIA
from ipe.central import web as WEB


class _Sessao:
    username = "admin"
    perms = {"view"}

    def can(self, p):
        return p in self.perms


def _nomes_no_plano(obj, pos, nrm):
    """O que o navegador faz (overlay.ts `rotulos`): pontos a até `tol` do plano, no mínimo 2."""
    out = []
    for r in obj["rotulos3d"]:
        p = np.asarray(r["pontos"], float)
        d = (p - pos) @ nrm
        if int((np.abs(d) <= r["tol"]).sum()) >= 2:
            out.append(r["texto"])
    return out


def test_coluna_no_overlay_web_e_selo(env, tmp_path):
    paths, db, repo = env
    uid, serie = _exame(env, tmp_path)
    t = _trabalho(env, uid, serie)
    try:
        rotulos, versao, _s = t.ler_rotulos()
        COL.gravar(t, COL.nomear(t.vol, rotulos), versao, db, paths.storage)
    finally:
        t.limpar()
    # selo: a SEG é resultado de IA; a série de onde ela saiu foi analisada
    m = SIA.series_com_ia(repo, uid)
    assert m[serie] == {"resultado": False, "ferramentas": ["Níveis da coluna"]}
    seg = next(k for k, v in m.items() if v["resultado"])
    assert SIA.dica(m[serie]) == "IA nesta série: Níveis da coluna"
    web = WEB.series_ia(repo, _Sessao(), {"study": [uid]}, lambda s, u: True)
    assert set(web["series"]) == {serie, seg}
    # overlay: o objeto da coluna com os nomes em 3D
    ov = WEB.overlays(repo, _Sessao(), {"study": [uid]}, lambda s, u: True, None)
    col = [o for o in ov["objetos"] if o.get("rotulos3d")]
    assert len(col) == 1 and col[0]["fonte"] == "Coluna" and col[0]["ia"]
    assert [r["texto"] for r in col[0]["rotulos3d"]][:3] == ["L1", "L1-L2", "L2"]
    # axial no meio do disco L4-L5: só ele; sagital no meio: todos
    _vol, _f, discos = _fantoma()
    k = discos[3][0] + 1
    assert _nomes_no_plano(col[0], np.array([-24.0, -20.0, 100.0 - k * DZ]), np.array([0, 0, 1.0])) == ["L4-L5"]
    sag = _nomes_no_plano(col[0], np.array([0.0, -20.0, 100.0]), np.array([1.0, 0, 0]))
    assert len(sag) == 11
    # a segunda leitura vem do cache (a mesma lista)
    assert WEB.overlays(repo, _Sessao(), {"study": [uid]}, lambda s, u: True, None)["objetos"] == ov["objetos"]


def test_series_sem_ia_sem_selo(env, tmp_path):
    paths, db, repo = env
    uid, serie = _exame(env, tmp_path)
    assert SIA.series_com_ia(repo, uid) == {}
    assert SIA.e_resultado("SR", "Aorta por segmento · Ipê") and not SIA.e_resultado("CT", "AX OSSO")


def test_navegador_mostra_niveis_selo_e_interruptor(env, tmp_path):
    import pytest
    pw = pytest.importorskip("playwright.sync_api")
    from PySide6.QtWidgets import QApplication
    from ipe.auth.backend import LocalAuth
    from ipe.central.server import CentralServer
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie = _exame(env, tmp_path)
    t = _trabalho(env, uid, serie)
    try:
        rotulos, versao, _s = t.ler_rotulos()
        COL.gravar(t, COL.nomear(t.vol, rotulos), versao, db, paths.storage)
    finally:
        t.limpar()
    LocalAuth(repo).create_first_admin("admin", "Administrador", "admin123")
    srv = CentralServer(db, repo, paths.storage, port=0, host="127.0.0.1")
    srv.start()
    erros = []
    try:
        with pw.sync_playwright() as p:
            b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            pg.on("pageerror", lambda e: erros.append(str(e)))
            pg.goto(f"http://127.0.0.1:{srv.port}/web/")
            pg.evaluate("localStorage.clear()")
            pg.fill("#usuario", "admin")
            pg.fill("#senha", "admin123")
            pg.click("button[type=submit]")
            pg.wait_for_selector("table.lista tbody tr")
            pg.locator("table.lista tbody tr").first.dblclick()
            pg.wait_for_selector(".quadro canvas")
            # o selo na miniatura da série analisada (a SEG não vira miniatura no navegador: vai no menu SEG)
            pg.wait_for_selector(f".tira .serie[data-serie='{serie}'] .selo-ia", timeout=15000)
            assert "Níveis da coluna" in pg.get_attribute(f".tira .serie[data-serie='{serie}'] .selo-ia", "title")
            # os nomes dos níveis no axial (no meio do exame há vértebra ou disco)
            pg.locator(f".tira .serie[data-serie='{serie}']").click()
            pg.wait_for_function("() => [...document.querySelectorAll('canvas.camada-ov')]"
                                 ".some(c => Number(c.dataset.desenhados) > 0)", timeout=20000)
            # no sagital reconstruído (MPR): todos os níveis
            pg.locator(".planos button[title='Sagital']").first.click()
            pg.wait_for_function("() => [...document.querySelectorAll('canvas.camada-ov')]"
                                 ".some(c => Number(c.dataset.desenhados) >= 8)", timeout=30000)
            import os
            if os.environ.get("IPE_SHOT_DIR"):
                pg.screenshot(path=os.path.join(os.environ["IPE_SHOT_DIR"], "niveis_web.png"))
            # o interruptor da IA no menu do overlay apaga os nomes (e fica lembrado)
            pg.click("nav.barra button[aria-label='Opções do overlay']")
            pg.locator("button:has-text('CAD/IA (achados, segmentações, níveis)')").click()
            pg.wait_for_function("() => [...document.querySelectorAll('canvas.camada-ov')]"
                                 ".every(c => Number(c.dataset.desenhados) === 0)", timeout=10000)
            assert pg.evaluate("localStorage.getItem('ipe.web.overlayIA')") == "0"
            b.close()
    finally:
        srv.stop()
    assert not erros, erros


def test_selo_ia_na_tira_do_ipe(env, tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    from ipe.ui.viewer import hanging as H
    paths, db, repo = env
    uid, serie = _exame(env, tmp_path)
    t = _trabalho(env, uid, serie)
    try:
        rotulos, versao, _s = t.ler_rotulos()
        COL.gravar(t, COL.nomear(t.vol, rotulos), versao, db, paths.storage)
    finally:
        t.limpar()
    app = QApplication.instance() or QApplication([])
    st = Settings(paths.settings_file)
    st.set("hanging_protocols", [dict(p, enabled=False) for p in H.DEFAULT_PROTOCOLS])
    st.set("hanging_fabrica", H.FABRICA_VERSAO)
    w = MainWindow(paths, st)
    try:
        w.show()
        w.open_study(uid)
        app.processEvents()
        tab = w.tabs.currentWidget()
        tab._fill_strip()
        dicas = {tab.strip.item(i).data(Qt.UserRole): tab.strip.item(i).toolTip() for i in range(tab.strip.count())}
        assert "IA nesta série: Níveis da coluna" in dicas[serie]
        # o selo é pintado no canto de cima, à esquerda da miniatura (lilás)
        it = next(tab.strip.item(i) for i in range(tab.strip.count()) if tab.strip.item(i).data(Qt.UserRole) == serie)
        img = it.icon().pixmap(80, 80).toImage()
        lilas = [(x, y) for x in range(0, 30) for y in range(0, 18)
                 if (lambda c: c.blue() > 200 and 150 < c.red() < 220 and c.green() < 170)(img.pixelColor(x, y))]
        assert len(lilas) > 20
    finally:
        w.close()
