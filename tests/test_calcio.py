"""0.99.89: escore de cálcio coronariano (Agatston) com os órgãos do TotalSegmentator."""
import numpy as np
import pytest
from pydicom.uid import generate_uid

from ipe.ai import calcio as CA

N, NZ, PX, DZ = 64, 60, 1.0, 1.0


def _serie(pasta, pat, study, desc, vol, numero, extra=None):
    from ipe.core.sample_data import _base, _mono, _save
    series = {"uid": generate_uid(), "number": numero, "description": desc}
    for k in range(vol.shape[0]):
        ds = _base("1.2.840.10008.5.1.4.1.1.2", pat, study, series, "CT")
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [0, 0, DZ * k]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [PX, PX]
        ds.SliceThickness = DZ
        ds.KVP = 120
        ds.RescaleSlope, ds.RescaleIntercept = 1, 0
        for kk, vv in (extra or {}).items():
            setattr(ds, kk, vv)
        _mono(ds, vol[k].astype(np.int16), signed=True)
        _save(ds, pasta / series["uid"])
    return series["uid"]


def _fantoma(contraste=False):
    """Coração (elipsoide, 41 HU), aortas ascendente e descendente (43), esterno (701) e as calcificações:
    DA, CX, CD e TCE na gordura epicárdica, uma dentro do coração (anel?) e uma na parede da aorta."""
    v = np.full((NZ, N, N), -80, np.int16)
    k, j, i = np.mgrid[0:NZ, 0:N, 0:N]
    cor, ao = (341, 343) if contraste else (41, 43)
    v[((k - 25) / 15.0) ** 2 + ((j - 32) / 14.0) ** 2 + ((i - 32) / 14.0) ** 2 <= 1] = cor
    v[((j - 26) ** 2 + (i - 30) ** 2 <= 25) & (k >= 36)] = ao          # ascendente (a raiz em k = 36)
    v[(j - 52) ** 2 + (i - 44) ** 2 <= 25] = ao                        # descendente
    v[:, 9:13, 28:37] = 701                                            # esterno, dentro da margem do coração
    v[21:27, 16:19, 39:42] = 350          # DA: 2 fatias × 9 mm² × peso 3 = 54
    v[18:21, 41:44, 43:46] = 250          # CX: 9 × 2 = 18
    v[24:27, 25:28, 15:18] = 450          # CD: 9 × 4 = 36
    v[33:36, 26:29, 39:42] = 300          # TCE, perto da raiz, à esquerda: 9 × 3 = 27
    v[24:27, 33:36, 33:36] = 451          # dentro do coração: 9 × 4 = 36 (fora do escore)
    v[30:33, 44:47, 43:46] = 500          # parede da aorta descendente: 9 × 4 = 36 (fora do escore)
    v[15, 16, 32] = 300                   # ruído: um pixel só some na fatia de 3 mm
    return v


def _exame(tmp_path, env, nome, desc="ESCORE DE CALCIO", contraste=False, serie="CALCIUM SCORE 1.0"):
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    pat = {"name": f"CALCIO^{nome}", "id": f"CA{nome}", "birth": "19600101", "sex": "M"}
    study = {"uid": generate_uid(), "date": "20261108", "accession": f"CA{nome}", "description": desc,
             "for": generate_uid()}
    _serie(tmp_path / nome, pat, study, serie, _fantoma(contraste), 2)
    Importer(db, paths.storage).import_paths([tmp_path / nome])
    return study["uid"]


def _rodar(env, study, settings=None):
    from ipe.ai import ferramentas as FE
    from ipe.ai import totalseg as TS
    from ipe.imaging.series import FrameCache
    paths, db, repo = env
    serie, motivo = CA.escolher_serie(repo, study, settings)
    assert serie, motivo
    t = TS.Trabalho(repo, FrameCache(64), None, study, serie, simular=True)
    FE.preparar_trabalho(t, CA)
    t.preparar()
    t.rodar_aqui()
    res, versao = FE.rodar_conta(t, CA, settings)
    return t, res, versao


def test_agatston_por_vaso_cac_drs_e_laudo(env, tmp_path):
    from ipe.ai import ferramentas as FE
    paths, db, repo = env
    study = _exame(tmp_path, env, "A")
    assert CA.exame_serve({"modalities": "CT", "description": "ESCORE DE CALCIO"})
    t, res, versao = _rodar(env, study)
    assert res.calculado and res.fatia_mm == pytest.approx(3.0)
    ag = {s: round(v["agatston"], 3) for s, v in res.vasos.items()}
    assert ag == {"TCE": 27, "DA": 54, "CX": 18, "CD": 36, "IC": 36, "AO": 36}, \
        [(x.vaso, x.agatston, [round(c) for c in x.centro]) for x in res.lesoes]
    assert res.agatston == pytest.approx(135) and res.n_vasos == 4
    assert res.volume == pytest.approx(9 * 3 * 5)
    assert res.cac_drs == "CAC-DRS A2/N4" and res.categoria == "moderado"
    assert not any("sincronização" in a for a in res.avisos)              # a descrição diz escore de cálcio
    assert any("somados em fatias de 3,0 mm" in a.replace("3.0", "3,0") for a in res.avisos)
    # banco, SEG e o laudo pelos vasos revisados
    out = FE.gravar(t, CA, res, versao, db, paths.storage, repo, None)
    assert CA.ja_feita(repo, study) and len(out["achados"]) == 7 and out["seg_path"]
    achados = {a["rotulo"]: a for a in repo.achados(study, "calcio")}
    assert achados["T"]["local"] == "CAC-DRS A2/N4 · moderado"
    repo.revisar_achado(achados["CX"]["id"], "descartado", "teste")
    repo.revisar_achado(achados["DA"]["id"], "corrigido", "teste", corrigidos={"agatston": 100.0})
    for r in ("TCE", "CD", "AO"):
        repo.revisar_achado(achados[r]["id"], "confirmado", "teste")
    txt = CA.laudo(repo.achados(study, "calcio"))
    assert "(Agatston): 163 — CAC-DRS A2/N3; cálcio coronariano moderado (SCCT/STR)" in txt, txt
    assert "DA (descendente anterior): Agatston 100" in txt and "CX" not in txt
    assert "Calcificação AO" in txt
    # rodar de novo não repete o que o médico revisou
    out2 = FE.gravar(t, CA, res, versao, db, paths.storage, repo, None)
    rot = sorted(a["rotulo"] for a in repo.achados(study, "calcio"))
    assert rot == sorted(["T", "TCE", "DA", "CX", "CD", "IC", "AO"]) and len(out2["achados"]) == 2
    t.limpar()


def test_sem_somar_o_ruido_pontua_e_o_aviso_de_corte_fino(env, tmp_path):
    study = _exame(tmp_path, env, "B", desc="TC DE TORAX", serie="MEDIASTINO 1.0")
    t, res, _v = _rodar(env, study, {CA.CHAVE_SOMAR: 0})
    assert res.fatia_mm == pytest.approx(1.0)
    assert any("sincronização" in a for a in res.avisos)
    assert any("corte fino aumenta" in a for a in res.avisos)
    assert res.agatston > 135                                             # corte fino: o escore sobe
    t.limpar()


def test_com_contraste_nao_mede(env, tmp_path):
    study = _exame(tmp_path, env, "C", contraste=True)
    t, res, _v = _rodar(env, study)
    assert not res.calculado and "contraste" in res.avisos[0]
    assert CA.n_itens(res) == 0 and CA.itens_para_o_banco(res, t, "") == []
    t.limpar()


def test_pesos_categorias_e_vaso_pela_posicao():
    assert [CA.peso(h) for h in (120, 130, 199, 200, 299, 300, 399, 400, 900)] == [0, 1, 1, 2, 2, 3, 3, 4, 4]
    assert CA.cac_drs(0, 0) == "CAC-DRS 0" and CA.cac_drs(50, 1) == "CAC-DRS A1/N1"
    assert CA.cac_drs(450, 6) == "CAC-DRS A3/N4"
    assert [CA.categoria(x) for x in (0, 1, 99, 100, 299, 300)] == ["nenhum", "leve", "leve", "moderado",
                                                                      "moderado", "grave"]
    c = (0.0, 0.0)
    assert CA._vaso(10, -15, 0, *c, None) == "DA"          # anterior e à esquerda
    assert CA._vaso(12, 12, 0, *c, None) == "CX"           # à esquerda e atrás
    assert CA._vaso(-16, -6, 0, *c, None) == "CD"          # à direita
    assert CA._vaso(-3, 16, 0, *c, None) == "CD"           # posteroinferior (descendente posterior)
    assert CA._vaso(10, -2, 30, *c, (0.0, 0.0, 32.0)) == "TCE"


def test_tela_calcio(env, tmp_path, monkeypatch):
    import time

    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    study = _exame(tmp_path, env, "D")
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(msg))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, msg, *a, **k: avisos.append("ERRO " + msg))
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1300, 800)
    w.show()
    try:
        assert w.handle_external({"accession": "CAD"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        assert tab.app_na_barra("calcio") and "calcio.auto" in tab.actions_by_id
        vp = next(v for v in tab.viewports if v.frames)
        tab.ferramenta_ia("calcio", vp, simular=True)
        fim = time.time() + 120
        while not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert avisos and avisos[-1].startswith("Cálcio coronariano pronto"), avisos
        assert "Agatston 135" in avisos[-1] and "CAC-DRS A2/N4" in avisos[-1]
        assert CA.ja_feita(repo, study)
        seg = [o for o in tab.overlay_objects if o.source == "SEG" and "Cálcio" in (o.label or "")]
        assert seg, [o.label for o in tab.overlay_objects]
        tab.ferramenta_ia_botao("calcio")
        assert tab.achados_painel.isVisible()
    finally:
        w.close()
