"""0.99.31 — onda A, parte 2: perfil de intensidade (A4), tirar a mesa da TC (A5), histórico do exame
(A6), apagar imagens soltas (A7), fechar o exame sozinho (A8) e o modelo de laudo OIT (A9)."""
import time
from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from ipe.imaging import measure as M
from ipe.imaging import mesa


# ------------------------------------------------------------------ A4
def test_perfil_ao_longo_da_linha():
    px = np.tile(np.arange(100, dtype=float), (50, 1))          # o valor é a coluna
    d, v = M.perfil(px, [(10.5, 20.5), (30.5, 20.5)], spacing=(0.5, 0.5))
    assert d[-1] == pytest.approx(10.0)                           # 20 px × 0,5 mm
    assert v[0] == pytest.approx(10) and v[-1] == pytest.approx(30)
    assert np.all(np.diff(v) >= 0)
    d2, v2 = M.perfil(px, [(10.5, 5.5), (20.5, 5.5), (20.5, 15.5)])   # polilinha (px)
    assert d2[-1] == pytest.approx(20.0) and v2[-1] == pytest.approx(20)


def test_janela_do_perfil():
    from ipe.ui.viewer.perfil import PerfilDialog
    QApplication.instance() or QApplication([])
    px = np.tile(np.arange(100, dtype=float) - 50, (50, 1))
    ann = M.Annotation("line", ("x", 0), [(10.5, 10.5), (60.5, 10.5)])
    vp = SimpleNamespace(_img=SimpleNamespace(pixels=px, is_color=False), modality="CT",
                         measure_spacing=lambda a=None: (1.0, 1.0))
    d = PerfilDialog(vp, ann)
    assert "Comprimento 50.0 mm" in d.info.text() and "HU" in d.info.text()
    assert d.copiar().splitlines()[1].startswith("0,00\t-40,00")
    ann.points[1] = (20.5, 10.5)                                  # mexeu na régua: o gráfico acompanha
    d._talvez_refresh()
    assert "Comprimento 10.0 mm" in d.info.text()
    d.close()


# ------------------------------------------------------------------ A5
def test_tirar_a_mesa():
    nz, ny, nx = 12, 128, 128
    vol = np.full((nz, ny, nx), -1000, dtype=np.int16)
    yy, xx = np.mgrid[0:ny, 0:nx]
    corpo = ((xx - 64) / 45) ** 2 + ((yy - 55) / 35) ** 2 <= 1
    pulmao = ((xx - 45) / 12) ** 2 + ((yy - 52) / 18) ** 2 <= 1
    vol[:, corpo] = 40
    vol[:, pulmao] = -850
    vol[:, 105:112, 15:113] = 150                                  # a mesa, separada por ar
    out, mexeu = mesa.tirar_a_mesa(vol, dx=1.0, dy=1.0, dz=3.0)
    assert mexeu
    assert (out[:, 105:112, 15:113] == -1000).all()                # mesa saiu
    assert (out[:, pulmao] == -850).all()                          # pulmão (cercado pelo corpo) ficou
    assert (out[:, corpo & ~pulmao] == 40).all()
    assert (vol[:, 105:112, 15:113] == 150).all()                  # o volume original não muda
    vazio = np.full((4, 32, 32), -1000, dtype=np.int16)
    assert mesa.tirar_a_mesa(vazio)[1] is False


# ------------------------------------------------------------------ A7, A6
def test_apagar_imagem_e_historico(env, sample_dir):
    from ipe.auth import session as S
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    st = next(r for r in repo.search_studies() if r.num_images > 10)
    se = next(s for s in repo.series_for_study(st.study_uid) if s.num_images > 1)
    inst = repo.instances_for_series(se.series_uid)
    alvo = inst[0]["sop_uid"]
    repo.save_annotation(db_id=None, study_uid=st.study_uid, series_uid=se.series_uid, sop_uid=alvo,
                         frame_index=0, kind="line", data="{}")
    repo.set_locked(st.study_uid, True)
    with pytest.raises(PermissionError, match="cadeado"):
        repo.delete_instance(alvo, paths.storage)
    repo.set_locked(st.study_uid, False)
    assert repo.delete_instance(alvo, paths.storage) == 1
    assert len(repo.instances_for_series(se.series_uid)) == len(inst) - 1
    assert repo.count_annotations(st.study_uid) == 0
    S.audit(repo, "apagou_imagem", "teste", study_uid=st.study_uid)
    rid = repo.save_report({"study_uid": st.study_uid, "title": "TC", "text": "x", "author": "Dra"})
    repo.sign_report(rid, "Dra")
    h = repo.historico_do_exame(st.study_uid)
    acoes = [x["action"] for x in h]
    assert {"apagou_imagem", "laudo_criado", "laudo_assinado"} <= set(acoes)
    from ipe.ui.historico_exame import HistoricoDialog
    QApplication.instance() or QApplication([])
    d = HistoricoDialog(repo, st.study_uid)
    textos = {d.tabela.item(r, 2).text() for r in range(d.tabela.rowCount())}
    assert "Apagou imagem" in textos and "Laudo assinado" in textos
    # a última imagem da série não sai sozinha
    um = next((s for s in repo.series_for_study(st.study_uid) if s.num_images == 1), None)
    if um is not None:
        with pytest.raises(PermissionError, match="única imagem"):
            repo.delete_instance(repo.instances_for_series(um.series_uid)[0]["sop_uid"], paths.storage)


def test_na_tela_apagar_imagem_perfil_e_fechar(env, sample_dir, monkeypatch):
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    from ipe.ui.viewer.viewer_tab import ViewerTab
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    cfg = Settings(paths.settings_file)
    w = MainWindow(paths, cfg, repo=repo, db=db)
    try:
        st = next(r for r in repo.search_studies() if (r.modalities or "").startswith("CT") and r.num_images > 10)
        w.open_study(st.study_uid)
        QApplication.processEvents()
        tab = next(t for t in w.all_viewer_tabs())
        assert isinstance(tab, ViewerTab)
        vp = next(v for v in tab.viewports if v.frames and len(v.frames) > 2)
        textos = [a.text() for a in vp.build_context_menu().actions()]
        assert "Apagar esta imagem…" in textos
        antes = len(vp.frames)
        monkeypatch.setattr(tab, "perguntar_apagar_imagem", lambda t: True)
        assert tab.apagar_imagem(vp)
        assert len(vp.frames) == antes - 1
        # régua ▸ Perfil de intensidade
        ann = vp._new_annotation("line", [(5.5, 5.5), (40.5, 5.5)])
        vp.annotations.append(ann) if isinstance(getattr(vp, "annotations", None), list) else None
        d = vp.abrir_perfil(ann)
        assert d.view.v.size > 10
        d.close()
        # fechar sozinho: parado por mais que o tempo escolhido
        cfg.set("viewer.fechar_parado_min", 1)
        w._ultimo_uso = time.monotonic() - 120
        assert w._conferir_parado() == 1 and not list(w.all_viewer_tabs())
        w.open_study(st.study_uid)
        QApplication.processEvents()
        assert w.fechar_exame(st.study_uid, "teste") == 1
    finally:
        w.close()


# ------------------------------------------------------------------ A9
def test_modelo_oit(env):
    paths, _db, repo = env
    from ipe.reporting.templates import default_templates
    assert any(t["id"] == "rx_oit" for t in default_templates())
    # quem já tinha a lista gravada (sem o OIT e sem um de fábrica que apagou) ganha só o OIT
    antigos = [t for t in default_templates() if t["id"] not in ("rx_oit", "livre")]
    repo.set_app_setting("report_templates", antigos)
    ids = [t["id"] for t in repo.report_templates()]
    assert "rx_oit" in ids and "livre" not in ids
    repo.save_report_templates([t for t in repo.report_templates() if t["id"] != "rx_oit"])
    assert "rx_oit" not in [t["id"] for t in repo.report_templates()]        # apagou: não volta
    t = next(t for t in default_templates() if t["id"] == "rx_oit")
    assert "profusão" in t["text"].lower() and "CR" in t["modalities"]
