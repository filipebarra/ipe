"""Menus do botão direito enxugados e ícones próprios das aplicações de IA (0.99.78).

Pedido dele: *"reveja o menu do botão direito tanto no BD quanto no viewer. acho que está muito
poluído, por exemplo, tem segmentação nele ainda"* e *"queria mudar os ícones das aplicações IA"*.
"""
from _menus import submenu, todas

from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication


def _app():
    return QApplication.instance() or QApplication([])


def _janela(env, sample_dir):
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = _app()
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.show()
    w.open_study(repo.search_studies()[0].study_uid)
    app.processEvents()
    return app, w, repo


def test_menu_do_quadro_agrupado(env, sample_dir):
    app, w, _repo = _janela(env, sample_dir)
    try:
        vp = w.all_viewer_tabs()[-1].viewports[0]
        menu = vp.build_context_menu(vp.rect().center())
        topo = [a.text() for a in menu.actions() if not a.isSeparator()]
        for t in ("Imagem", "Quadro", "Anotações", "Ferramenta do botão esquerdo", "Informações DICOM (tags)…"):
            assert t in topo, topo
        # o que antes ficava solto agora está nos grupos
        for solto in ("Janela (presets)", "Cor (tabela de cores)", "Filtro da imagem", "Inverter",
                      "Mouse (botão esquerdo)", "Medidas", "Linhas de corte das outras séries"):
            assert solto not in topo, solto
        assert len(topo) <= 14, topo
        # a segmentação saiu do botão direito (fica nos botões das aplicações)
        textos = [a.text() for a in todas(menu)]
        assert not any("TotalSegmentator" in t for t in textos)
        # DSA só em angiografia
        assert "Subtração digital (DSA)" not in textos
        # o que apaga fica no fim
        assert topo[-1] in ("Apagar medidas deste corte", "Apagar esta imagem…")
        img = [a.text() for a in submenu(menu, "Imagem").actions() if not a.isSeparator()]
        assert img[:3] == ["Janela (presets)", "Cor (tabela de cores)", "Inverter"], img
        assert "Linhas de corte das outras séries" in [a.text() for a in submenu(menu, "Quadro").actions()]
        assert [a.text() for a in submenu(menu, "Ferramenta do botão esquerdo").actions()] == \
            ["Navegar", "Medir", "Desenhar"]
    finally:
        w.close()


def test_cores_principais_e_mais_cores(env, sample_dir):
    from ipe.imaging import colormaps as CM
    app, w, _repo = _janela(env, sample_dir)
    try:
        vp = w.all_viewer_tabs()[-1].viewports[0]
        menu = vp.build_context_menu()
        cor = submenu(menu, "Imagem/Cor (tabela de cores)")
        diretas = [a for a in cor.actions() if not a.isSeparator() and a.menu() is None]
        assert len(diretas) <= 7                       # cinza + as da modalidade (+ a atual)
        mais = submenu(cor, "Mais cores")
        nomes = {a.text() for a in todas(cor) if a.menu() is None and not a.isSeparator()}
        assert {v[0] for v in CM.COLORMAPS.values()} <= nomes, "cor sumiu do menu"
        assert mais.actions()
    finally:
        w.close()


def test_menu_do_banco_agrupado(env, sample_dir):
    app, w, repo = _janela(env, sample_dir)
    try:
        b = w.browser
        b.refresh()
        rows = b.model.rows[:1]
        menu = b.menu_do_exame(rows)
        topo = [a.text() for a in menu.actions() if not a.isSeparator()]
        for t in ("Abrir", "Organizar", "Documentos", "Enviar para", "Ferramentas", "Apagar do banco…"):
            assert t in topo, topo
        for solto in ("Prioridade", "Estado do exame", "Adicionar à lista", "Corrigir tags (nome, lado, data)…",
                      "Remover proteção", "Anexar documento (PDF ou imagem)…"):
            assert solto not in topo, solto
        assert topo[-1] == "Apagar do banco…"
        org = [a.text() for a in submenu(menu, "Organizar").actions()]
        assert {"Adicionar à lista", "Prioridade", "Subespecialidade", "Estado do exame"} <= set(org)
        # proteger é um item só, que alterna
        lock = next(a for a in menu.actions() if a.text() == "Proteger (não apagar)")
        lock.trigger()
        assert repo.study_info(rows[0].study_uid) is not None
        b.refresh()
        rows = [r for r in b.model.rows if r.study_uid == rows[0].study_uid]
        topo2 = [a.text() for a in b.menu_do_exame(rows).actions()]
        assert "Remover proteção" in topo2 and "Proteger (não apagar)" not in topo2
        # sem mamografia não aparece "Apagar implante"
        if not any("MG" in (r.modalities or "") for r in rows):
            assert not any(a.text().startswith("Apagar implante") for a in todas(menu))
    finally:
        w.close()


def test_icones_das_aplicacoes_sao_distintos():
    _app()
    from ipe.ui import icons as I
    imgs = {}
    for n in I._APPS_IA:
        im = I.icon(n).pixmap(64, 64).toImage().convertToFormat(QImage.Format_ARGB32)
        imgs[n] = bytes(im.constBits())
    assert len(set(imgs.values())) == len(imgs), "dois aplicativos com o mesmo desenho"
    medida = I.icon("measure").pixmap(64, 64).toImage().convertToFormat(QImage.Format_ARGB32)
    assert bytes(medida.constBits()) not in imgs.values()
    # o selo ✦ dourado só nas de IA: o canto de cima à direita tem dourado
    for n, ia in I._APPS_IA.items():
        im = I.icon(n).pixmap(64, 64).toImage()
        c = im.pixelColor(54, 10)
        dourado = c.alpha() > 100 and c.red() > 200 and c.green() > 150 and c.blue() < 120
        assert dourado == ia, n


def test_a_barra_usa_os_icones_novos(env, sample_dir):
    app, w, _repo = _janela(env, sample_dir)
    try:
        import pathlib
        fonte = (pathlib.Path(__file__).resolve().parents[1] / "src/ipe/ui/viewer/viewer_tab.py").read_text("utf-8")
        for n in ("app_indices", "app_cefalometria", "app_linfonodos", "app_nodulos", "app_composicao",
                  "app_figado", "app_orgaos", "app_difusao"):
            assert f'icon("{n}")' in fonte, n
        assert 'icon(f"app_{tipo}")' in fonte
    finally:
        w.close()
