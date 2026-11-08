"""0.99.90: diâmetro da aorta perpendicular ao eixo, por segmento (linha central + planos)."""
import numpy as np
import pytest
from pydicom.uid import generate_uid

from ipe.ai import aorta as AO


def fantoma(r_asc=22.0, r_ai=20.0, r=12.0, ramos=True):
    """Bengala de 1 mm: ascendente em x = 40 (raio r_asc), arco no plano x-z (centro z = 130), descendente em
    x = 90 até z = 0, com aneurisma infrarrenal (raio r_ai) entre z 10 e 30; coração embaixo da ascendente;
    tronco braquiocefálico (x ≈ 52) e subclávia esquerda (x ≈ 80); T12 com a borda de baixo em z = 60; rins
    com o meio em z = 40."""
    N = (170, 90, 130)
    v = np.full(N, -80, np.int16)
    k, j, i = np.mgrid[0:N[0], 0:N[1], 0:N[2]].astype(np.float32)
    y0, zt, xa, xd = 45.0, 130.0, 40.0, 90.0
    xc, rc = (xa + xd) / 2, (xd - xa) / 2

    def tubo(x0, z0, z1, raio):
        return ((i - x0) ** 2 + (j - y0) ** 2 <= raio ** 2) & (k >= z0) & (k <= z1)
    v[tubo(xa, 75, zt, r_asc)] = 45
    rr = np.sqrt((i - xc) ** 2 + (k - zt) ** 2)
    v[((rr - rc) ** 2 + (j - y0) ** 2 <= r ** 2) & (k >= zt)] = 45
    v[tubo(xd, 0, zt, r)] = 45
    v[tubo(xd, 10, 30, r_ai)] = 45
    v[((i - xa) ** 2 + (j - y0) ** 2 + (k - 60) ** 2 <= 20 ** 2) & (v != 45)] = 41
    if ramos:
        for x0, cod in ((52.0, 46), (80.0, 47)):
            ztop = zt + np.sqrt(max(rc ** 2 - (x0 - xc) ** 2, 0))
            m = ((i - x0) ** 2 + (j - y0) ** 2 <= 16) & (k > ztop + r - 2) & (k < ztop + r + 25)
            v[m & (v != 45)] = cod
    v[60:75, 75:88, 80:100] = 702
    v[34:47, 30:40, 105:118] = 49
    v[34:47, 50:60, 105:118] = 50
    return v


def _volume(v):
    from ipe.imaging.volume import Volume
    return Volume(v, np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0]), 1.0, 1.0,
                  None, "")


def _conta(v):
    from types import SimpleNamespace

    from ipe.ai.totalseg_worker import _simular
    t = SimpleNamespace(vol=_volume(v), series_uid="x", descricao_serie="ANGIO", frames=[], versao="")
    return AO.calcular(t, _simular(v, [{"nome": "total", "aorta": True}]), None)


def test_segmentos_e_diametros_no_fantoma():
    res = _conta(fantoma())
    assert res.calculado
    assert list(res.segmentos) == ["RZ", "AA", "AR", "DT", "AS", "AI"]
    d = {g: x.dmax for g, x in res.segmentos.items()}
    assert d["AA"] == pytest.approx(44, abs=2.5) and d["AR"] == pytest.approx(24, abs=2.5)
    assert d["DT"] == pytest.approx(24, abs=2.5) and d["AS"] == pytest.approx(24, abs=2.5)
    assert d["AI"] == pytest.approx(40, abs=2.5)
    assert res.segmentos["AA"].dperp == pytest.approx(44, abs=2.5)          # redonda
    # a linha central vai do meio da ascendente ao meio da descendente, de ponta a ponta
    assert np.allclose(res.linha[0][:2], (40, 45), atol=2) and res.linha[0][2] < 80
    assert np.allclose(res.linha[-1][:2], (90, 45), atol=2) and res.linha[-1][2] < 5
    assert res.comprimento == pytest.approx(55 + np.pi * 25 + 130, abs=15)
    # o maior ponto da infrarrenal fica no aneurisma
    assert 10 <= res.segmentos["AI"].centro[2] <= 30
    assert res.maior.sigla == "AA"
    # referências como texto
    itens = AO.itens_para_o_banco(res, type("T", (), {"series_uid": "x"})(), "")
    por = {x["rotulo"]: x for x in itens}
    assert "aneurisma ≥ 30 mm" in por["AI"]["elegibilidade"] and "controle sugerido pelo ACR" in por["AI"]["elegibilidade"]
    assert "dilatação" in por["AA"]["elegibilidade"]
    assert "Referência" not in por["DT"]["elegibilidade"]                     # 24 mm: nada a lembrar
    assert any("raiz: sem ECG" in a for a in res.avisos)


def test_sem_ramos_e_so_abdome():
    res = _conta(fantoma(ramos=False))
    assert res.calculado and "AR" in res.segmentos
    assert any("sem os ramos do arco" in a for a in res.avisos)
    v = fantoma()[:58]                                         # só o abdome: sem arco, sem coração, sem T12
    res2 = _conta(v)
    assert res2.calculado and set(res2.segmentos) == {"AS", "AI"}, list(res2.segmentos)
    assert any("não pega o arco" in a for a in res2.avisos)


def test_controle_acr_e_texto():
    assert [AO.controle_acr(x) for x in (24, 27, 31, 38, 41, 47, 52, 60)] == \
        ["", "5 anos", "3 anos", "2 anos", "1 ano", "6 meses", "3 a 6 meses", ""]
    a = {"tipo": AO.TIPO_SEG, "rotulo": "AI", "local": "aorta abdominal infrarrenal", "estado": "confirmado",
         "numeros": {"dmax": {"v": 41.0, "u": "mm", "n": ""}, "dperp": {"v": 40.0, "u": "mm", "n": ""}}}
    b = dict(a, rotulo="AA", local="aorta ascendente", estado="descartado")
    txt = AO.laudo([b, a])
    assert txt == "- Aorta abdominal infrarrenal: diâmetro máximo 41 × 40 mm (perpendicular ao eixo, parede externa)."


def _serie(pasta, pat, study, desc, vol, numero):
    from ipe.core.sample_data import _base, _mono, _save
    series = {"uid": generate_uid(), "number": numero, "description": desc}
    for k in range(vol.shape[0]):
        ds = _base("1.2.840.10008.5.1.4.1.1.2", pat, study, series, "CT")
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [0, 0, float(k)]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [1.0, 1.0]
        ds.SliceThickness = 1.0
        ds.RescaleSlope, ds.RescaleIntercept = 1, 0
        _mono(ds, vol[k].astype(np.int16), signed=True)
        _save(ds, pasta / series["uid"])
    return series["uid"]


def test_trabalho_grava_seg_e_achados(env, tmp_path):
    from ipe.ai import ferramentas as FE
    from ipe.ai import totalseg as TS
    from ipe.imaging.series import FrameCache
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    pat = {"name": "AORTA^TESTE", "id": "AO1", "birth": "19500101", "sex": "M"}
    study = {"uid": generate_uid(), "date": "20261108", "accession": "AO1", "description": "ANGIOTC DE AORTA",
             "for": generate_uid()}
    _serie(tmp_path / "ao", pat, study, "AORTA ARTERIAL 1.0", fantoma(), 2)
    Importer(db, paths.storage).import_paths([tmp_path / "ao"])
    assert AO.exame_serve({"modalities": "CT", "description": "ANGIOTC DE AORTA"})
    serie, motivo = AO.escolher_serie(repo, study["uid"])
    assert serie, motivo
    t = TS.Trabalho(repo, FrameCache(64), None, study["uid"], serie, simular=True)
    FE.preparar_trabalho(t, AO)
    t.preparar()
    t.rodar_aqui()
    res, versao = FE.rodar_conta(t, AO, None)
    out = FE.gravar(t, AO, res, versao, db, paths.storage, repo, None)
    assert out["seg_path"] and AO.ja_feita(repo, study["uid"]) and len(out["achados"]) == 7
    ach = {a["rotulo"]: a for a in repo.achados(study["uid"], "aorta")}
    assert ach["A"]["local"] == "maior: aorta ascendente"
    repo.revisar_achado(ach["AI"]["id"], "confirmado", "teste")
    assert "infrarrenal: diâmetro máximo" in AO.laudo(repo.achados(study["uid"], "aorta"))
    out2 = FE.gravar(t, AO, res, versao, db, paths.storage, repo, None)
    assert len(out2["achados"]) == 6                                        # o AI revisado fica
    t.limpar()


def test_tela_aorta(env, tmp_path, monkeypatch):
    import time

    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    pat = {"name": "AORTA^TELA", "id": "AO2", "birth": "19500101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20261108", "accession": "AO2", "description": "ANGIOTC DE AORTA",
             "for": generate_uid()}
    _serie(tmp_path / "ao2", pat, study, "AORTA ARTERIAL 1.0", fantoma(), 2)
    Importer(db, paths.storage).import_paths([tmp_path / "ao2"])
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(msg))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, msg, *a, **k: avisos.append("ERRO " + msg))
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1300, 800)
    w.show()
    try:
        assert w.handle_external({"accession": "AO2"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        assert tab.app_na_barra("aorta") and "aorta.auto" in tab.actions_by_id
        vp = next(v for v in tab.viewports if v.frames)
        tab.ferramenta_ia("aorta", vp, simular=True)
        fim = time.time() + 180
        while not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert avisos and avisos[-1].startswith("Aorta pronta"), avisos
        seg = [o for o in tab.overlay_objects if o.source == "SEG" and "Aorta" in (o.label or "")]
        assert seg, [o.label for o in tab.overlay_objects]
        tab.ferramenta_ia_botao("aorta")
        assert tab.achados_painel.isVisible()
    finally:
        w.close()
