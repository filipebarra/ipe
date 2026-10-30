"""0.98: órgãos abdominais com o TotalSegmentator — a ponte do programa com o trabalhador.

O modelo de verdade roda num ambiente próprio, no Windows dele. Aqui o trabalhador roda no modo
"simular": devolve rótulos de geometria conhecida (um bloco claro = "fígado", um cubo = "baço",
metades do bloco = segmentos 7 e 8). Isso confere o que é do programa: a grade (LPS → RAS e de volta),
os volumes, a SEG, a máscara voltando ao lugar certo, a tabela e o envio ao PACS.
"""
from types import SimpleNamespace

import numpy as np
import pydicom
import pytest
from pydicom.uid import generate_uid

from ipe.ai import totalseg as TS
from ipe.core.sample_data import _base, _mono, _save
from ipe.importer.scanner import Importer

CT_SOP = "1.2.840.10008.5.1.4.1.1.2"
DX, DY, DZ = 0.9, 0.8, 2.5                 # anisotrópico de propósito: troca de eixo aparece
NZ, NY, NX = 40, 120, 128                  # linhas ≠ colunas: transposição aparece
BLOCO = (slice(10, 30), slice(20, 50), slice(30, 90))


def _serie(env, tmp_path, modalidade="CT"):
    paths, db, repo = env
    pat = {"name": "ORGAOS^Teste", "id": "ORG1", "birth": "19700101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20261026", "accession": "ORG01",
             "description": "ABDOME", "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 3, "description": "AX PORTAL"}
    vol = np.zeros((NZ, NY, NX), np.int16)
    vol[BLOCO] = 200
    pasta = tmp_path / "serie"
    for k in range(NZ):
        ds = _base(CT_SOP if modalidade == "CT" else "1.2.840.10008.5.1.4.1.1.4", pat, study, series, modalidade)
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [-100.0, -120.0, 50.0 - k * DZ]       # cabeça → pés
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [DY, DX]
        ds.SliceThickness = DZ
        if modalidade == "CT":
            ds.RescaleSlope, ds.RescaleIntercept = 1, 0
        _mono(ds, vol[k], signed=True)
        _save(ds, pasta)
    Importer(db, paths.storage).import_paths([pasta])
    return study["uid"], series["uid"]


def _cache():
    from ipe.imaging.series import FrameCache
    return FrameCache(256)


def test_afim_leva_o_voxel_ao_mesmo_ponto_do_paciente():
    vol = SimpleNamespace(row_dir=np.array([1.0, 0, 0]), col_dir=np.array([0, 1.0, 0]),
                          slice_vec=np.array([0, 0, -DZ]), dx=DX, dy=DY, origin=np.array([-100.0, -120.0, 50.0]))
    a = TS.afim_ras(vol)
    for ijk in ((0, 0, 0), (10, 7, 3), (127, 119, 39)):
        lps = vol.origin + vol.row_dir * DX * ijk[0] + vol.col_dir * DY * ijk[1] + vol.slice_vec * ijk[2]
        ras = a @ np.array([*ijk, 1.0])
        assert np.allclose(ras[:3], [-lps[0], -lps[1], lps[2]])


def test_tarefas_por_modalidade_e_configuracao(env):
    from ipe.core.config import Settings
    paths, _db, _repo = env
    s = Settings(paths.settings_file)
    ct = TS.tarefas("CT", s)
    assert [t["nome"] for t in ct] == ["total", "liver_segments"] and ct[0]["fast"]
    assert set(ct[0]["roi"]) == set(TS.PADRAO)
    mr = TS.tarefas("MR", s)
    assert [t["nome"] for t in mr] == ["total_mr", "liver_segments_mr"] and not mr[0]["fast"]
    s.set(TS.CHAVE_COUINAUD, False)
    s.set(TS.CHAVE_ESTRUTURAS, ["liver", "spleen", "nao_existe"])
    assert [t["nome"] for t in TS.tarefas("CT", s)] == ["total"]
    assert TS.tarefas("CT", s)[0]["roi"] == ["liver", "spleen"]


def test_sem_o_ambiente_diz_como_instalar(env, monkeypatch, tmp_path):
    monkeypatch.setattr(TS, "pasta_base", lambda: tmp_path / "nada")
    assert not TS.instalado(None)
    assert "instalar_segmentacao.bat" in TS.motivo_nao_instalado()


def _rodar(env, uid, serie):
    paths, db, repo = env
    t = TS.Trabalho(repo, _cache(), None, uid, serie, simular=True)
    t.preparar()
    linhas = []
    t.rodar_aqui(linhas.append)
    res = t.ler()
    assert any(x.startswith("ETAPA") for x in linhas)
    return t, res


def test_volumes_e_densidade_na_grade_certa(env, tmp_path):
    uid, serie = _serie(env, tmp_path)
    t, res = _rodar(env, uid, serie)
    try:
        ml_voxel = DX * DY * DZ / 1000
        bloco = 20 * 30 * 60
        assert res.ml("liver") == pytest.approx(bloco * ml_voxel)
        assert res.ml("spleen") == pytest.approx(1000 * ml_voxel)
        figado = next(e for e in res.estruturas if e.nome == "liver")
        assert figado.hu == pytest.approx(200) and figado.offset == (10, 20, 30)
        segs = res.por_grupo("segmentos")
        assert [e.rotulo for e in segs] == ["Segmento 7", "Segmento 8"]
        assert res.soma_segmentos == pytest.approx(res.figado)
        assert sum(e.pct_figado for e in segs) == pytest.approx(100)
    finally:
        t.limpar()


def test_grava_seg_e_tabela_e_a_mascara_volta_ao_lugar(env, tmp_path):
    from PySide6.QtWidgets import QApplication

    from ipe.ai import totalseg_saida as SAIDA
    from ipe.imaging import overlays as O
    from ipe.imaging.mesh_io import masks_from_seg
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie = _serie(env, tmp_path)
    t, res = _rodar(env, uid, serie)
    try:
        out = SAIDA.gravar(t, res, db, paths.storage)
        locais = TS.series_locais(repo, uid)
        assert len(locais) == 2 and set(out["series"]) == locais
        series = {s.series_uid: s for s in repo.series_for_study(uid)}
        seg_s = next(s for u, s in series.items() if u in locais and s.modality == "SEG")
        tab_s = next(s for u, s in series.items() if u in locais and s.modality != "SEG")
        assert seg_s.description == TS.DESC_SEG and tab_s.description == TS.DESC_TABELA
        seg_path = repo.instances_for_series(seg_s.series_uid)[0]["path"]
        ds = pydicom.dcmread(seg_path)
        assert ds.SegmentSequence[0].SegmentAlgorithmType == "AUTOMATIC"
        assert {s.SegmentLabel for s in ds.SegmentSequence} == {"Fígado", "Baço", "Segmento 7", "Segmento 8"}
        # lida de volta (com o recorte da 0.98), a máscara cai exatamente no bloco
        obj = O.load_object(seg_path)
        partes = O.por_segmento(obj)
        assert {p.label for p in partes} == {"Fígado", "Baço", "Segmento 7", "Segmento 8"}
        assert all(mf.mask.shape[0] <= 30 for mf in obj.masks if mf.label == "Fígado")   # recortada
        de_volta = masks_from_seg(t.vol, obj)
        esperado = np.zeros((NZ, NY, NX), bool)
        esperado[BLOCO] = True
        assert np.array_equal(de_volta["Fígado"], esperado)
        # a tabela: imagem RGB, com o aviso de anotação gravada
        tab = pydicom.dcmread(repo.instances_for_series(tab_s.series_uid)[0]["path"])
        assert tab.BurnedInAnnotation == "YES" and tab.Modality == "OT" and tab.Columns == SAIDA.LARGURA
        px = tab.pixel_array
        assert px.ndim == 3 and px.std() > 10
        # não vão ao PACS no envio do exame inteiro
        from ipe.network.service import NetworkService
        enviados = NetworkService._arquivos_para_enviar(SimpleNamespace(repo=repo), uid, None)
        assert len(enviados) == NZ
    finally:
        t.limpar()


def test_rm_marca_adrenal_como_baixa_confianca():
    vol = SimpleNamespace(data=np.zeros((4, 6, 6), np.int16), dx=1.0, dy=1.0, dz=1.0)
    lab = np.zeros((4, 6, 6), np.uint8)
    lab[1:3, 1:3, 1:3] = 9
    lab[0, 0, 0] = 5
    res = TS.medir(vol, {"total_mr": (lab, {9: "adrenal_gland_left", 5: "liver", 10: "lung_left"})}, "MR")
    ad = next(e for e in res.estruturas if e.nome == "adrenal_gland_left")
    assert "baixa confiança" in ad.nota and ad.hu is None
    assert [e.nome for e in res.estruturas] == ["liver", "adrenal_gland_left"]     # pulmão não é da lista


def test_serie_curta_ou_de_outra_modalidade_recusa(env, tmp_path):
    paths, db, repo = env
    uid, serie = _serie(env, tmp_path, modalidade="MR")
    t = TS.Trabalho(repo, _cache(), None, uid, serie, simular=True)
    t.preparar()            # RM serve
    t.limpar()


def _esperar(app, cond, segundos=60):
    import time
    fim = time.time() + segundos
    while not cond() and time.time() < fim:
        app.processEvents()
        time.sleep(0.05)
    assert cond(), "a segmentação não terminou"


def test_tela_banco_e_quadro(env, tmp_path, monkeypatch):
    """Banco ▸ série ▸ Segmentar e quadro ▸ Segmentar: roda num processo à parte (QProcess) e o
    exame aberto ganha um item por órgão nas sobreposições."""
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie = _serie(env, tmp_path)
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(("i", msg)))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, msg, *a, **k: avisos.append(("w", msg)))
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1200, 800)
    w.show()
    try:
        assert w.handle_external({"accession": "ORG01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        # o item aparece no menu da série, no banco e no quadro
        menu = w.browser.series_menu(uid, [serie])
        assert any(a.text().startswith("Segmentar órgãos") and a.isEnabled() for a in menu.actions())
        vp = next(v for v in tab.viewports if v.frames)
        assert any(a.text().startswith("Segmentar órgãos") for a in vp.build_context_menu().actions())

        seg = w.browser.segmentar_orgaos(uid, serie, simular=True)
        _esperar(app, lambda: bool(avisos))
        assert avisos[-1][0] == "i" and "Segmentação pronta" in avisos[-1][1], avisos
        rotulos = {o.label for o in tab.overlay_objects if o.source == "SEG"}
        assert {"Fígado", "Baço", "Segmento 7", "Segmento 8"} <= rotulos
        assert len(TS.series_locais(repo, uid)) == 2
        del seg

        n = len(avisos)
        tab.segmentar_orgaos(vp, simular=True)                   # pelo quadro: mais uma (outra série SEG)
        _esperar(app, lambda: len(avisos) > n)
        assert avisos[-1][0] == "i", avisos[-1]
        assert len(TS.series_locais(repo, uid)) == 4
    finally:
        w.close()


def test_trabalhador_de_verdade_com_um_totalsegmentator_falso(tmp_path):
    """O ramo de verdade do trabalhador (nibabel + totalsegmentator(...)), com um pacote falso que
    tem a mesma interface: confere a transposição (k,j,i) ↔ (i,j,k), a afim e os argumentos."""
    import json
    import subprocess
    import sys
    pytest.importorskip("nibabel")
    falso = tmp_path / "falso" / "totalsegmentator"
    falso.mkdir(parents=True)
    (falso / "__init__.py").write_text("__version__ = '9.9-falso'\n")
    (falso / "map_to_binary.py").write_text(
        "class_map = {'total': {1: 'spleen', 5: 'liver'}, 'liver_segments': {7: 'liver_segment_7'}}\n")
    (falso / "python_api.py").write_text('''
import json, os
import numpy as np, nibabel as nib
def totalsegmentator(img, output=None, **kw):
    with open(os.environ["ARGS_LOG"], "a") as f:
        f.write(json.dumps({"kw": {k: v for k, v in kw.items()}, "afim": img.affine.tolist(),
                            "shape": list(img.shape)}) + "\\n")
    dados = np.asarray(img.dataobj)
    lab = np.zeros(dados.shape, np.uint8)
    lab[dados > 100] = 7 if kw["task"] == "liver_segments" else 5
    return nib.Nifti1Image(lab, img.affine)
''')
    pasta = tmp_path / "job"
    pasta.mkdir()
    vol = np.zeros((NZ, NY, NX), np.int16)
    vol[BLOCO] = 200
    np.save(pasta / "volume.npy", vol)
    afim = np.diag([-DX, -DY, DZ, 1.0])
    job = {"affine": afim.tolist(), "device": "cpu",
           "tarefas": [{"nome": "total", "roi": ["liver", "spleen"], "fast": True},
                       {"nome": "liver_segments"}]}
    (pasta / "job.json").write_text(json.dumps(job))
    log = tmp_path / "args.log"
    import os
    env = dict(os.environ, PYTHONPATH=str(falso.parent), ARGS_LOG=str(log))
    r = subprocess.run([sys.executable, str(TS.caminho_do_trabalhador()), str(pasta)],
                       capture_output=True, text=True, env=env, timeout=120)
    res = json.loads((pasta / "resultado.json").read_text())
    assert res["ok"], res.get("detalhe") or r.stdout + r.stderr
    assert res["versao"]
    lab = np.load(pasta / "rotulos_total.npy")
    assert lab.shape == vol.shape and np.array_equal(lab == 5, vol > 100)    # voltou na mesma grade
    assert np.array_equal(np.load(pasta / "rotulos_liver_segments.npy") == 7, vol > 100)
    chamadas = [json.loads(x) for x in log.read_text().splitlines()]
    assert chamadas[0]["shape"] == [NX, NY, NZ]                                # NIfTI em (i, j, k)
    assert np.allclose(chamadas[0]["afim"], afim)
    kw0, kw1 = chamadas[0]["kw"], chamadas[1]["kw"]
    assert kw0["task"] == "total" and kw0["roi_subset"] == ["liver", "spleen"] and kw0["fast"] is True
    assert kw0["device"] == "cpu" and kw0["ml"] is True
    assert kw1["task"] == "liver_segments" and "fast" not in kw1 and "roi_subset" not in kw1
    assert res["tarefas"]["total"]["classes"] == {"1": "spleen", "5": "liver"}
    assert "ETAPA pronto" in r.stdout


def test_instalador_vem_junto_e_e_oferecido_quando_falta(env, tmp_path, monkeypatch):
    """Versão 1: o pacote leva só o instalador; quem quiser a segmentação baixa uma vez."""
    import sys
    from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

    from ipe.ui import segmentacao as SEG
    QApplication.instance() or QApplication([])
    arq = SEG.instalador()
    assert arq is not None and arq.name.startswith("instalar_segmentacao")
    assert ("pip install torch" in arq.read_text(encoding="utf-8")) and ("TotalSegmentator" in arq.read_text(encoding="utf-8"))
    monkeypatch.setattr(TS, "pasta_base", lambda: tmp_path / "nada")              # não instalado
    perguntas, abertos = [], []
    monkeypatch.setattr(QMessageBox, "question", lambda _p, _t, msg, *a, **k: (perguntas.append(msg), QMessageBox.Yes)[1])
    monkeypatch.setattr(SEG, "abrir_instalador", lambda janela, perguntar=True: abertos.append(perguntar) or True)
    paths, db, repo = env
    uid, serie = _serie(env, tmp_path)
    janela = QWidget()
    s = SEG.Segmentacao(janela, repo, None, paths.storage, uid, serie)
    assert s.iniciar() is False
    assert "Instalar agora?" in perguntas[-1] and abertos == [False]
    assert not SEG.ocupado()
