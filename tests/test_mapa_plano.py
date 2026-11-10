"""Reorientar os mapas da dinâmica: axial, coronal, sagital e de volta ao plano da aquisição.

Pedido dele: "na tela de dinâmico, os mapas foram criados. quero mudar a orientação deles também".
O mapa é calculado corte a corte na grade da aquisição; virar o plano obriga a montar o volume
inteiro do mapa e reconstruí-lo como qualquer série.
"""
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer
from tests.test_dynamic import make_dynamic


def _tab_com_dinamica(env, tmp_path):
    from ipe.ui.viewer.dynamic import DynamicDialog, LAYOUTS
    paths, db, repo = env
    uid = make_dynamic(tmp_path / "d", one_series=False)
    Importer(db, paths.storage).import_paths([tmp_path / "d"])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1200, 800)
    w.show()
    w.browser.refresh()
    w.open_study(uid)
    tab = w.all_viewer_tabs()[-1]
    app.processEvents()
    dlg = DynamicDialog(tab)
    params = dlg.params()
    params["layout"] = next(i for i, (lab, _k) in enumerate(LAYOUTS) if lab.startswith("MSI, PEI"))
    assert tab.start_dynamic(dlg.dset, params)
    return app, w, tab


def test_mapa_muda_de_plano_e_volta(env, tmp_path):
    app, w, tab = _tab_com_dinamica(env, tmp_path)
    vp = tab.viewports[0]
    tab._activate(vp)
    assert vp.dyn_key == "msi"
    assert tab._mapa_do_quadro(vp) is not None
    plano_de_origem = vp.plano_nome()

    assert tab.dyn.reorientar("Sagital")
    app.processEvents()
    assert vp.series_uid.startswith("dynmpr:")
    assert vp.plano_nome() == "Sagital"
    assert vp.mpr_plane is not None and vp.mpr_plane.n > 1
    assert vp.modality == "MAP msi"             # continua fora da sincronia de janela/cor
    assert tab.dyn.plano_do_quadro_ativo() == "Sagital"
    # o quadro reorientado sai da conta das curvas: a grade não é mais a da aquisição
    assert not tab.dyn.is_dyn(vp)

    assert tab.dyn.reorientar("Coronal")
    app.processEvents()
    assert vp.plano_nome() == "Coronal"

    assert tab.dyn.reorientar("Original")
    app.processEvents()
    assert vp.series_uid.startswith(f"dyn:{id(tab.dyn.maps)}:")
    assert vp.dyn_key == "msi" and tab.dyn.is_dyn(vp)
    assert vp.plano_nome() == plano_de_origem
    assert tab.dyn.plano_do_quadro_ativo() == "Aquisição"
    tab.close_dynamic()
    app.processEvents()
    w.close()


def test_o_volume_do_mapa_e_montado_uma_vez(env, tmp_path):
    app, w, tab = _tab_com_dinamica(env, tmp_path)
    vp = tab.viewports[0]
    tab._activate(vp)
    chamadas = []
    real = tab.dyn.maps.volume_do_mapa
    tab.dyn.maps.volume_do_mapa = lambda kind, prog=None, **k: (chamadas.append(kind) or real(kind, prog))
    tab.dyn.reorientar("Sagital")
    tab.dyn.reorientar("Coronal")
    tab.dyn.reorientar("Original")
    tab.dyn.reorientar("Axial")
    assert chamadas == ["msi"], f"montou o volume mais de uma vez: {chamadas}"
    tab.close_dynamic()
    app.processEvents()
    w.close()


def test_o_quadro_de_fase_tambem_vira(env, tmp_path):
    """Até a 0.67 o quadro de fase ficava preso ao plano da aquisição. Pedido dele (0.68): "no
    dinâmico, permita que eu possa mudar o eixo" — vale para a fase também."""
    app, w, tab = _tab_com_dinamica(env, tmp_path)
    tab.dyn.set_active_view("ph:1")             # quadro de fase, não de mapa
    vp = tab.active
    assert tab._mapa_do_quadro(vp) is None, "não é mapa…"
    assert tab.dyn.reorientar("Sagital"), "…mas vira"
    assert tab.dyn.plano_do_quadro_ativo() == "Sagital"
    assert tab.dyn.reorientar("Original")
    assert tab.dyn.plano_do_quadro_ativo() == "Aquisição"
    tab.close_dynamic()
    app.processEvents()
    w.close()


def test_o_sagital_mostra_o_mesmo_mapa(env, tmp_path):
    """Reconstruir não pode inventar: o mesmo ponto do paciente dá o mesmo valor nos dois planos."""
    import numpy as np
    app, w, tab = _tab_com_dinamica(env, tmp_path)
    vp = tab.viewports[0]
    tab._activate(vp)
    nativo = tab.dyn.maps
    vol = tab._volume_do_mapa(tab.dyn, "msi")
    nz, ny, nx = vol.shape
    assert (nz, ny, nx) == (nativo.n, *nativo.shape)
    tab.dyn.reorientar("Sagital")
    plano = vp.mpr_plane
    assert plano.n == nx or plano.n == ny       # um corte por coluna (ou por linha) do volume
    # um ponto qualquer, longe da borda: valor no volume x valor no corte reconstruído
    k, j, i = nz // 2, ny // 2, nx // 3
    p = vol.voxel_to_patient(i, j, k)
    idx = plano.index_for_point(p)
    img = plano.image(idx).pixels
    esperado = float(vol.data[k, j, i])
    assert float(np.abs(img - esperado).min()) < 1e-3, "o valor do mapa não aparece no corte"
    assert np.isfinite(img).all()
    tab.close_dynamic()
    app.processEvents()
    w.close()


def test_numeros_do_exame_saem_pelo_painel(env, tmp_path, monkeypatch):
    """O botão existe, mede e mostra — função sem porta visível é função que não existe."""
    from PySide6.QtWidgets import QMessageBox
    app, w, tab = _tab_com_dinamica(env, tmp_path)
    vistos = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: vistos.append(self.text()) or 0)
    from PySide6.QtWidgets import QPushButton
    botoes = [b.text() for b in tab.dyn.panel.findChildren(QPushButton)]
    assert "Números do exame…" in botoes, f"o botão sumiu do painel: {botoes}"
    # ele não achou o botão porque ele estava **cortado**: oito botões em linhas de
    # quatro, 77 px para um texto de 144. Botão que não dá para ler não existe.
    for b in tab.dyn.panel.findChildren(QPushButton):
        assert b.width() >= b.sizeHint().width(), f"botão cortado: {b.text()!r}"
    tab.dyn.numeros_do_exame()
    assert vistos and "Realce de fundo" in vistos[0] and "Angiovolume do exame" in vistos[0]
    e = tab.dyn.maps.numeros_do_exame()
    assert e.mama_ml > 0 and e.formula and e.avisos
    tab.close_dynamic()
    app.processEvents()
    w.close()


def test_fibroglandular_sai_pelo_painel(env, tmp_path, monkeypatch):
    """0.100.7: o botão do fibroglandular mede (aqui sem T1: na pré da dinâmica, com aviso) e mostra a tabela."""
    from PySide6.QtWidgets import QMessageBox, QPushButton
    app, w, tab = _tab_com_dinamica(env, tmp_path)
    vistos = []
    monkeypatch.setattr(QMessageBox, "exec", lambda self: vistos.append((self.text(), self.informativeText())) or 0)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: vistos.append(("info", a[2])) or 0)
    assert "Fibroglandular e realce…" in [b.text() for b in tab.dyn.panel.findChildren(QPushButton)]
    tab.dyn.fgt_do_exame()
    assert vistos, "nada apareceu"
    texto, info = vistos[0]
    assert texto != "info", info
    assert "Série medida" in texto and "pré-contraste da dinâmica" in texto
    assert "menos confiável" in info
    tab.close_dynamic()
    app.processEvents()
    w.close()


def test_nenhum_botao_do_painel_fica_cortado():
    """Na largura mínima do painel, todo botão tem que caber inteiro."""
    from types import SimpleNamespace
    from PySide6.QtWidgets import QPushButton
    from ipe.ui.viewer import dynamic as D
    app = QApplication.instance() or QApplication([])
    vazio = SimpleNamespace(reconfigure=lambda: 0, numeros_do_exame=lambda: 0, fgt_do_exame=lambda: 0, save_maps=lambda: 0,
                            clear_slice=lambda: 0, chart_to_film=lambda: 0, close=lambda: 0,
                            refresh=lambda: 0, maps=None)
    for largura in (320, 360, 480):
        p = D.DynamicPanel(vazio)
        p.resize(largura, 800)
        p.show()
        app.processEvents()
        cortados = [b.text() for b in p.findChildren(QPushButton) if b.width() < b.sizeHint().width()]
        assert not cortados, f"com {largura} px ficaram cortados: {cortados}"
        p.close()


def test_a_cor_do_mapa_fica_guardada(env, tmp_path):
    """Ele trocava a cor do mapa em todo exame: a escolha passa a valer para o próximo."""
    app, w, tab = _tab_com_dinamica(env, tmp_path)
    vp = tab.viewports[0]
    tab._activate(vp)
    assert vp.dyn_key == "msi"
    de_fabrica = vp.state.cmap
    vp.set_colormap("hot", lembrar=True)
    assert w.settings.get("viewer.cmap_padrao", {})["MAP msi"] == "hot"
    # outro mapa não foi arrastado junto
    outro = tab.viewports[1]
    assert outro.dyn_key == "pei" and outro.state.cmap != "hot"
    # fecha e abre de novo: a cor volta a que ele escolheu, não a de fábrica
    tab.dyn.show_view(vp, "msi")
    assert vp.state.cmap == "hot" != de_fabrica
    # e o mapa reorientado nasce com ela também
    tab.dyn.reorientar("Sagital")
    assert vp.state.cmap == "hot"
    tab.close_dynamic()
    app.processEvents()
    w.close()


def test_salvar_mapas_avisa_no_fim(env, tmp_path, monkeypatch):
    """Ele clicou em Salvar mapas, o programa congelou, salvou e não disse nada."""
    from PySide6.QtWidgets import QMessageBox
    from ipe.ui.viewer.dynamic import DynamicSession
    app, w, tab = _tab_com_dinamica(env, tmp_path)
    vistos = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: vistos.append(a[2])))
    tab.dyn.save_maps()
    assert vistos, "salvou sem avisar"
    assert "Séries novas no banco" in vistos[0] and "imagens" in vistos[0]
    tab.close_dynamic()
    app.processEvents()
    w.close()


def test_o_texto_do_aviso_diz_o_que_entrou_e_o_que_nao():
    from ipe.ui.viewer.dynamic import DynamicSession
    t = DynamicSession.resumo_do_salvamento(["MSI: 12 imagens"], ["SER"])
    assert "Séries novas no banco" in t and "MSI: 12 imagens" in t
    assert "Não salvos" in t and "SER" in t
    assert DynamicSession.resumo_do_salvamento([], []) == "Nenhum mapa foi salvo."
    só_bom = DynamicSession.resumo_do_salvamento(["MSI: 3 imagens"], [])
    assert "Não salvos" not in só_bom


def test_salvar_reconstrucao_pode_ser_cancelado(env, tmp_path, monkeypatch):
    """Operação demorada precisa de botão de parar — e parar não pode deixar meia série no banco."""
    from ipe.imaging import derived
    app, w, tab = _tab_com_dinamica(env, tmp_path)
    vp = tab.viewports[0]
    tab._activate(vp)
    antes = len(w.repo.series_for_study(tab.study_uid))
    def cancelado(*a, **k):
        prog = k.get("progresso")
        assert prog is not None, "salvou sem relatar progresso"
        raise derived.Cancelado("Gravação interrompida.")

    monkeypatch.setattr(derived, "save_plane_series", cancelado)
    assert tab.save_reconstruction(vp) is None
    assert len(w.repo.series_for_study(tab.study_uid)) == antes, "deixou série pela metade"
    tab.close_dynamic()
    app.processEvents()
    w.close()
