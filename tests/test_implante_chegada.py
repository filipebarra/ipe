"""0.97: implante corrigido na chegada — a cópia sem silicone fica pronta no banco local.

Pedido dele: "quando uma mamografia chegar, verifique se existe implante de silicone. Se existir,
aplique o filtro de cortar o implante para agilizar. Salve a imagem sem silicone no banco de dados
local."
"""
from _menus import submenu, todas  # noqa: F401
import hashlib
from types import SimpleNamespace

import numpy as np
import pydicom
import pytest
from pydicom.uid import generate_uid

from ipe.automation import implante as IMP
from ipe.core.sample_data import _base, _mono, _save
from ipe.imaging import mammo as M
from ipe.importer.scanner import Importer
from tests.test_mammo import _mama_com_implante

MG_SOP = "1.2.840.10008.5.1.4.1.1.1.2"


def _exame(env, tmp_path, casos):
    """casos: [(lado, incidência, BreastImplantPresent, com prótese?)] → study_uid."""
    paths, db, repo = env
    pat = {"name": "IMPLANTE^Chegada", "id": "IMPC1", "birth": "19750101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20261023", "accession": "IMPC01",
             "description": "MAMOGRAFIA BILATERAL", "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 1, "description": "2D_PROC"}
    pasta = tmp_path / "chegada"
    pasta.mkdir()
    for k, (lado, vista, tag, com) in enumerate(casos, start=1):
        px, _c, _p = _mama_com_implante(seed=k, implante=com)
        if lado == "L":
            px = px[:, ::-1].copy()
        ds = _base(MG_SOP, pat, study, series, "MG")
        ds.InstanceNumber, ds.ImageLaterality, ds.ViewPosition = k, lado, vista
        ds.AcquisitionTime = f"10{k:02d}00"
        ds.PresentationIntentType = "FOR PRESENTATION"
        if tag:
            ds.BreastImplantPresent = tag
        ds.ImagerPixelSpacing = [0.1, 0.1]
        _mono(ds, px.astype(np.uint16), signed=False)
        _save(ds, pasta)
    Importer(db, paths.storage).import_paths([pasta])
    return study["uid"]


def _md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


def test_grava_a_copia_so_de_quem_tem_implante(env, tmp_path):
    paths, db, repo = env
    uid = _exame(env, tmp_path, [("R", "CC", "YES", True), ("L", "CC", "YES", True),
                                 ("R", "MLO", "NO", True),      # o aparelho diz que não há: não procura
                                 ("L", "MLO", "", False)])      # sem tag e sem prótese: procura e não acha
    antes = {im.sop_uid: (im.path, _md5(im.path)) for im in M.read_images(repo, uid)}
    out = IMP.processar(repo, db, paths.storage, uid)
    assert out["corrigidas"] == 2 and out["sem_implante"] == 1 and out["puladas"] == 1, out

    imagens = M.read_images(repo, uid)
    copias = [im for im in imagens if im.sem_implante]
    assert len(copias) == 2
    assert {c.fonte for c in copias} == {s for s, _ in antes.items()
                                          if pydicom.dcmread(antes[s][0]).get("BreastImplantPresent") == "YES"}
    for sop, (p, h) in antes.items():                                    # a original não muda
        assert _md5(p) == h, "a imagem original foi alterada"
    # uma série nova, no mesmo exame, com o nome que diz o que é
    series = [s for s in repo.series_for_study(uid) if M.serie_sem_implante(s.description)]
    assert len(series) == 1 and series[0].series_number == 1 + IMP.SERIE_MAIS
    # o silicone desceu, e o resto da imagem é o mesmo
    c = copias[0]
    orig = pydicom.dcmread(antes[c.fonte][0]).pixel_array.astype(float)
    nova = pydicom.dcmread(c.path)
    px = nova.pixel_array.astype(float)
    assert nova.SOPInstanceUID != c.fonte and "DERIVED" in list(nova.ImageType)
    assert nova.file_meta.TransferSyntaxUID.is_little_endian and not nova.file_meta.TransferSyntaxUID.is_compressed
    mascara = M.implant_mask(orig)
    miolo = M._erode(mascara, 15)
    assert np.median(px[miolo]) < np.median(orig[miolo]) - 500
    fora = ~M._dilate(mascara, 8)
    assert np.abs(px[fora] - orig[fora]).max() <= 1


def test_nao_corrige_duas_vezes(env, tmp_path):
    paths, db, repo = env
    uid = _exame(env, tmp_path, [("R", "CC", "YES", True)])
    assert IMP.processar(repo, db, paths.storage, uid)["corrigidas"] == 1
    de_novo = IMP.processar(repo, db, paths.storage, uid)        # o exame chegou em mais uma parte
    assert de_novo["corrigidas"] == 0 and de_novo["vistas"] == 0
    assert sum(im.sem_implante for im in M.read_images(repo, uid)) == 1


def test_protocolo_abre_a_copia_e_a_original_fica_atras(env, tmp_path):
    paths, db, repo = env
    uid = _exame(env, tmp_path, [("R", "CC", "YES", True), ("L", "CC", "NO", True)])
    IMP.processar(repo, db, paths.storage, uid)
    imagens = M.read_images(repo, uid)
    ccd = M.pick_image(imagens, M.parse_code("CCD"))
    assert ccd.sem_implante
    lista = M.same_view(imagens, M.parse_code("CCD"))
    assert [im.sem_implante for im in lista] == [False, True]       # a original logo antes da cópia
    assert not M.pick_image(imagens, M.parse_code("CCE")).sem_implante


def test_envio_ao_pacs_deixa_a_copia_de_fora(env, tmp_path):
    from ipe.network.service import NetworkService
    paths, db, repo = env
    uid = _exame(env, tmp_path, [("R", "CC", "YES", True), ("L", "CC", "YES", True)])
    IMP.processar(repo, db, paths.storage, uid)
    fake = SimpleNamespace(repo=repo)
    todos = repo.files_for_study(uid)
    enviados = NetworkService._arquivos_para_enviar(fake, uid, None)
    assert len(todos) == 4 and len(enviados) == 2
    assert not any(M.eh_sem_implante(pydicom.dcmread(f, stop_before_pixels=True)) for f in enviados)
    # escolhida de propósito, a série vai
    locais = sorted(IMP.series_locais(repo, uid))
    assert len(NetworkService._arquivos_para_enviar(fake, uid, locais)) == 2


class _Sinal:
    def connect(self, *_a):
        pass


class _RedeSincrona:
    received = _Sinal()
    job_finished = _Sinal()

    def run_async(self, trabalho, pronto, *_a):
        try:
            pronto(trabalho(), None)
        except Exception as e:  # noqa: BLE001
            pronto(None, e)


@pytest.mark.parametrize("ligado", [True, False])
def test_chegada_dispara_e_preferencia_desliga(env, tmp_path, ligado):
    from PySide6.QtWidgets import QApplication

    from ipe.automation.engine import AutomationEngine
    from ipe.core.config import Settings
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid = _exame(env, tmp_path, [("R", "MLO", "YES", True)])
    settings = Settings(paths.settings_file)
    settings.set(IMP.CHAVE, ligado)
    eng = AutomationEngine(repo, db, _RedeSincrona(), settings, paths)
    avisos = []
    eng.implante_corrigido.connect(avisos.append)
    eng.corrigir_implantes(uid)
    tem = any(im.sem_implante for im in M.read_images(repo, uid))
    assert tem is ligado
    assert avisos == ([uid] if ligado else [])
    if ligado:
        assert any(r["kind"] == "implante" and r["items"] == 1 for r in repo.job_runs())


def test_exame_aberto_troca_para_a_copia_quando_fica_pronta(env, tmp_path):
    from PySide6.QtWidgets import QApplication

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid = _exame(env, tmp_path, [("R", "CC", "YES", True), ("L", "CC", "YES", True),
                                 ("R", "MLO", "YES", True), ("L", "MLO", "YES", True)])
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1400, 900)
    w.show()
    try:
        assert w.handle_external({"accession": "IMPC01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        cheios = [v for v in tab.viewports if v.mg_cell is not None and v._img is not None]
        assert len(cheios) == 4 and not any(M.eh_sem_implante(pydicom.dcmread(v.current_frame().path,
                                                                              stop_before_pixels=True))
                                           for v in cheios)
        IMP.processar(repo, db, paths.storage, uid)
        w._implante_pronto(uid)
        app.processEvents()
        cheios = [v for v in tab.viewports if v.mg_cell is not None and v._img is not None]
        assert len(cheios) == 4
        assert all(M.eh_sem_implante(pydicom.dcmread(v.current_frame().path, stop_before_pixels=True))
                   for v in cheios)
        # a parede torácica continua do lado certo com a cópia
        assert [v.chest_screen_side() for v in cheios] == ["right", "left", "right", "left"]
    finally:
        w.close()


# ------------------------------------------------------------------ 0.97.1
def test_copias_de_origens_diferentes_caem_na_mesma_serie(env, tmp_path):
    """Chegada e botão do visualizador gravam na mesma série " · sem implante", não numa por vez."""
    paths, db, repo = env
    uid = _exame(env, tmp_path, [("R", "CC", "YES", True), ("L", "CC", "NO", True)])
    IMP.processar(repo, db, paths.storage, uid)                 # a CCE (tag NO) fica sem cópia
    cce = next(im for im in M.read_images(repo, uid) if im.side == "L" and not im.sem_implante)
    px = pydicom.dcmread(cce.path).pixel_array.astype(np.float32)
    mascara = M.implant_mask(px)                                 # a prótese achada "à mão"
    assert IMP.salvar_uma(repo, db, paths.storage, uid, cce.path, cce.sop_uid, mascara) == "salva"
    assert IMP.salvar_uma(repo, db, paths.storage, uid, cce.path, cce.sop_uid, mascara) == "já estava salva"
    series = [s for s in repo.series_for_study(uid) if M.serie_sem_implante(s.description)]
    assert len(series) == 1
    assert len(IMP.ja_salvas(repo, uid)) == 2


def _janela(env):
    from PySide6.QtWidgets import QApplication

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    s = Settings(paths.settings_file)
    s.set(IMP.CHAVE, False)                     # o teste decide quando gravar
    w = MainWindow(paths, s, repo=repo, db=db)
    w.resize(1400, 900)
    w.show()
    return app, w


def test_menu_do_banco_apaga_o_implante(env, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    paths, db, repo = env
    uid = _exame(env, tmp_path, [("R", "CC", "YES", True), ("L", "CC", "YES", True),
                                 ("R", "MLO", "YES", True), ("L", "MLO", "YES", True)])
    app, w = _janela(env)
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(msg))
    try:
        b = w.browser
        b.refresh()
        rows = [r for r in repo.search_studies(limit=50) if r.study_uid == uid]
        menu = b.menu_do_exame(rows)
        acao = next(a for a in todas(menu) if a.text().startswith("Apagar implante"))
        assert acao.isEnabled()
        acao.trigger()
        app.processEvents()
        assert len(IMP.ja_salvas(repo, uid)) == 4
        assert "4 imagem(ns) salva(s)" in avisos[-1]
        acao.trigger()                                            # de novo: nada a fazer
        assert len(IMP.ja_salvas(repo, uid)) == 4 and "já tinham" in avisos[-1]
    finally:
        w.close()


def test_botao_implante_salva_se_ainda_nao_tem(env, tmp_path):
    import time
    paths, db, repo = env
    uid = _exame(env, tmp_path, [("R", "CC", "YES", True), ("L", "CC", "YES", True),
                                 ("R", "MLO", "YES", True), ("L", "MLO", "YES", True)])
    app, w = _janela(env)
    try:
        assert w.handle_external({"accession": "IMPC01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        salvas = []
        tab.implante_salvo.connect(salvas.append)

        def esperar(n):
            fim = time.time() + 60
            while len(salvas) < n and time.time() < fim:
                app.processEvents()
                time.sleep(0.05)
            assert len(salvas) >= n, "a gravação não terminou"

        tab.mg_set_implant(True)
        esperar(1)
        assert salvas[-1] == 4 and len(IMP.ja_salvas(repo, uid)) == 4
        tab.mg_set_implant(False)
        tab.mg_set_implant(True)                                  # já está no banco: não grava de novo
        esperar(2)
        assert salvas[-1] == 0 and len(IMP.ja_salvas(repo, uid)) == 4
        series = [s for s in repo.series_for_study(uid) if M.serie_sem_implante(s.description)]
        assert len(series) == 1 and len(repo.instances_for_series(series[0].series_uid)) == 4
    finally:
        w.close()


def test_zoom_com_mouse_so_sincroniza_com_o_botao(env, tmp_path):
    paths, db, repo = env
    _exame(env, tmp_path, [("R", "CC", "YES", False), ("L", "CC", "YES", False),
                           ("R", "MLO", "YES", False), ("L", "MLO", "YES", False)])
    app, w = _janela(env)
    try:
        assert w.handle_external({"accession": "IMPC01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        a, b, c, d = tab.viewports[:4]
        tab.hub.set_flag("sync_zoom", False)
        antes = [v.state.zoom for v in (b, c, d)]
        a.state.zoom = a.state.zoom * 2.5
        a.sig.view_changed.emit(a, "zoom")
        assert [v.state.zoom for v in (b, c, d)] == pytest.approx(antes)
        a.state.pan = (a.state.pan[0] + 40, a.state.pan[1]) if isinstance(a.state.pan, tuple) else a.state.pan
        a.sig.view_changed.emit(a, "pan")
        assert [v.state.zoom for v in (b, c, d)] == pytest.approx(antes)
        tab.hub.set_flag("sync_zoom", True)
        a.sig.view_changed.emit(a, "zoom")
        assert [v.state.zoom for v in (b, c, d)] == pytest.approx([a.state.zoom] * 3)
        # o zoom por quadrante (Q) continua junto, pela opção do protocolo, com o botão desligado
        tab.hub.set_flag("sync_zoom", False)
        a.fit(); b.fit(); c.fit(); d.fit()
        tab.mg_quadrant(a, 0)
        assert all(v.state.zoom >= 2 for v in (a, b, c, d))
    finally:
        w.close()
