"""0.99.15: cefalometria do cavum automática — a geometria num fantoma com respostas conhecidas.

O fantoma é desenhado em mm do paciente (LPS: +y posterior, +z superior), com 1 mm por voxel:
via aérea vertical (raio 8 mm, estreitando para 4,5 mm em z = 70), palato mole de 36 mm × 10 mm,
palato duro, língua elipsoide, mandíbula com Me e Go conhecidos, hioide e C2–C4.
"""
import numpy as np
import pytest

from ipe.ai import cefalometria as CF
from ipe.imaging.volume import Volume

X = np.arange(-50, 51)
Y = np.arange(-60, 61)
Z = np.arange(120, -21, -1)                  # k = 0 é o corte de cima, como na TC de cabeça
ME, GO = np.array([-55.0, 25.0]), np.array([10.0, 40.0])


def _grade():
    zz, yy, xx = np.meshgrid(Z, Y, X, indexing="ij")
    return xx.astype(float), yy.astype(float), zz.astype(float)


def _raio(z):
    return np.where(np.abs(z - 70) <= 2, 4.5, np.where(np.abs(z - 70) <= 6, 4.5 + (np.abs(z - 70) - 2) * 3.5 / 4, 8.0))


def _segmento(yy, zz, a, b, meia):
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = b - a
    L = np.linalg.norm(d)
    d /= L
    s = (yy - a[0]) * d[0] + (zz - a[1]) * d[1]
    w = -(yy - a[0]) * d[1] + (zz - a[1]) * d[0]
    return (s >= 0) & (s <= L) & (np.abs(w) <= meia)


def fantoma(inclinar: float = 0.0):
    """(volume, rótulos). `inclinar`: graus da via aérea no sagital (y anda com z)."""
    xx, yy, zz = _grade()
    hu = np.full(xx.shape, 40, np.int16)
    yc = 15.0 + np.tan(np.radians(inclinar)) * (zz - 70)
    r = _raio(zz) / np.cos(np.radians(inclinar))          # o corte perpendicular continua com raio r
    via = (np.hypot(xx, (yy - yc) * np.cos(np.radians(inclinar))) <= _raio(zz)) & (zz >= 20) & (zz <= 110)
    del r
    hu[via] = -1000
    lab1 = np.zeros(xx.shape, np.uint8)                   # head_glands_cavities
    lab1[via & (zz > 95)] = 11
    lab1[via & (zz > 40) & (zz <= 95)] = 12
    lab1[via & (zz <= 40)] = 13
    palato = _segmento(yy, zz, (-20, 95), (0, 65), 5.0) & (np.abs(xx) <= 12)
    lab1[palato] = 18
    hu[palato] = 60
    duro = _segmento(yy, zz, (-60, 95), (-20, 95), 3.0) & (np.abs(xx) <= 20)
    lab1[duro & ~palato] = 19
    lab2 = np.zeros(xx.shape, np.uint8)                   # headneck_bones_vessels
    hioide = (np.abs(xx) <= 15) & (yy >= -20) & (yy <= -10) & (zz >= 10) & (zz <= 14)
    lab2[hioide] = 3
    lab3 = np.zeros(xx.shape, np.uint8)                   # craniofacial_structures
    d = GO - ME
    acima = -(yy - ME[0]) * d[1] / np.linalg.norm(d) + (zz - ME[1]) * d[0] / np.linalg.norm(d)
    s = ((yy - ME[0]) * d[0] + (zz - ME[1]) * d[1]) / np.linalg.norm(d)
    corpo = (acima >= 0) & (acima <= 22) & (s >= 0) & (s <= np.linalg.norm(d))
    ramo = _segmento(yy, zz, (GO[0] - 4, GO[1]), (GO[0] + 1, 90), 5.0)
    lados = (np.abs(xx) >= 36) & (np.abs(xx) <= 44)
    queixo = (yy <= -45)
    lab3[(corpo & (lados | queixo)) | (ramo & lados)] = 1
    lab4 = np.zeros(xx.shape, np.uint8)                   # head_muscles
    lingua = ((xx / 24) ** 2 + ((yy + 25) / 30) ** 2 + ((zz - 50) / 18) ** 2) <= 1
    lab4[lingua] = 9
    lab5 = np.zeros(xx.shape, np.uint8)                   # total (vértebras)
    for cid, (lo, hi) in ((26, (33, 55)), (27, (10.5, 30)), (28, (-10, 8))):   # C2, C3, C4
        lab5[(np.abs(xx) <= 10) & (yy >= 30) & (yy <= 55) & (zz >= lo) & (zz <= hi)] = cid
    vol = Volume(hu, np.array([X[0], Y[0], Z[0]], float), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]),
                 np.array([0, 0, -1.0]), 1.0, 1.0, None, "")
    rot = {
        "head_glands_cavities": (lab1, {11: "nasopharynx", 12: "oropharynx", 13: "hypopharynx",
                                        18: "soft_palate", 19: "hard_palate"}),
        "headneck_bones_vessels": (lab2, {3: "hyoid"}),
        "craniofacial_structures": (lab3, {1: "mandible"}),
        "head_muscles": (lab4, {9: "tongue"}),
        "total": (lab5, {26: "vertebrae_C2", 27: "vertebrae_C3", 28: "vertebrae_C4"}),
    }
    return vol, rot


@pytest.fixture(scope="module")
def resultado():
    vol, rot = fantoma()
    return CF.calcular(vol, rot)


def test_area_minima_perpendicular_local_e_faixa(resultado):
    a = resultado["area"]
    assert a.valor == pytest.approx(np.pi * 4.5 ** 2, rel=0.15)
    assert CF.classe_da_area(a.valor) == "moderadamente reduzida"
    assert a.texto == "no terço inferior do palato mole (retropalatal)"      # z = 70, palato de 95 a 65
    assert resultado.perfil and max(x for _z, x in resultado.perfil) > 150


def test_via_aerea_inclinada_mede_no_plano_perpendicular():
    """O pedido dele: a área perpendicular ao eixo. Num tubo inclinado 30°, o axial dá a área
    ÷ cos 30° (15% a mais); a perpendicular tem de dar a do círculo."""
    vol, rot = fantoma(inclinar=30.0)
    a = CF.calcular(vol, rot)["area"]
    assert a.valor == pytest.approx(np.pi * 4.5 ** 2, rel=0.15)
    assert a.valor < np.pi * 4.5 ** 2 / np.cos(np.radians(30)) * 0.97


def test_palato_mole(resultado):
    assert resultado["palato_comprimento"].valor == pytest.approx(np.hypot(20, 30), abs=2.5)
    assert resultado["palato_espessura"].valor == pytest.approx(10.0, abs=1.6)


def test_espaco_aereo_posterior(resultado):
    assert resultado["pas_retropalatal"].valor == pytest.approx(10.0, abs=1.5)     # 2 × 4,5 + 1 voxel
    assert resultado["pas_retrolingual"].valor == pytest.approx(17.0, abs=1.5)     # 2 × 8 + 1


def test_hioide_ao_plano_mandibular_e_plano(resultado):
    d = GO - ME
    n = np.array([d[1], -d[0]]) / np.linalg.norm(d)          # para baixo
    esperado = min((np.array([y, 14.0]) - ME) @ n for y in (-20.0, -10.0))
    m = resultado["hioide_mp"]
    assert m.valor == pytest.approx(esperado, abs=1.5)
    go, me = m.linhas[0]
    assert np.allclose(me[1:], ME, atol=2.5) and np.allclose(go[1:], GO, atol=4.0)


def test_lingua(resultado):
    assert resultado["lingua_transversal"].valor == pytest.approx(49.0, abs=2.0)
    assert resultado["lingua_ap"].valor == pytest.approx(61.0, abs=2.0)


def test_nivel_do_hioide(resultado):
    assert resultado["hioide_nivel"].texto == "platô inferior de C3"
    corpos = {"C2": (33, 55), "C3": (10.5, 30), "C4": (-10, 8)}
    assert CF.nivel_na_coluna(20, corpos) == "corpo de C3"
    assert CF.nivel_na_coluna(28, corpos) == "platô superior de C3"
    assert CF.nivel_na_coluna(9, corpos) == "disco C3-C4"


def test_texto_no_formato_do_laudo(resultado):
    t = CF.texto_do_laudo(resultado)
    linhas = t.splitlines()
    assert linhas[0] == "Cefalometria por TC:"
    assert linhas[1].startswith("Área de secção transversal mínima da via aérea: ") and \
        "moderadamente reduzida (> 100 mm²: normal" in linhas[1]
    assert linhas[2].startswith("1. Comprimento do palato mole: ") and linhas[2].endswith("(34 ± 6 mm).")
    assert any(x.startswith("3. Espaço aéreo posterior: retropalatal ") and "retrolingual" in x and
               "(11 ± 2 mm)" in x for x in linhas)
    assert linhas[-1] == "7. Nível do hioide em relação à coluna: platô inferior de C3."


def test_referencias_trocadas_e_medida_editada(resultado):
    class S(dict):
        def get(self, k, d=None):
            return super().get(k, d)
    s = S({CF.CHAVE_REFERENCIAS: {"palato_comprimento": "35 ± 5 mm"}})
    import copy
    r = copy.deepcopy(resultado)
    r["lingua_ap"].valor, r["lingua_ap"].origem = 70.0, "editado"
    t = CF.texto_do_laudo(r, s)
    assert "(35 ± 5 mm)" in t and "anteroposterior da língua: 70,0 mm" in t
    assert "corrigidas à mão: comprimento anteroposterior da língua" in t


def test_sem_estruturas_diz_o_motivo():
    vol, rot = fantoma()
    lab, cl = rot["head_muscles"]
    rot["head_muscles"] = (np.zeros_like(lab), cl)
    rot.pop("craniofacial_structures")
    r = CF.calcular(vol, rot)
    assert r["lingua_ap"].valor is None and "língua" in r["lingua_ap"].motivo
    assert r["hioide_mp"].valor is None and "mandíbula" in r["hioide_mp"].motivo
    assert r["area"].valor is not None                         # o resto continua
    assert "anteroposterior da língua" not in CF.texto_do_laudo(r)


# ------------------------------------------------------------------ do exame à janela (trabalhador simulado)
def _codificar():
    """O fantoma com cada estrutura num HU próprio — o trabalhador simulado devolve as máscaras por eles."""
    vol, rot = fantoma()
    hu = vol.data.copy()
    for tarefa, codigos in (("head_glands_cavities", {18: 61, 19: 1101}), ("headneck_bones_vessels", {3: 1201}),
                            ("craniofacial_structures", {1: 1301}), ("head_muscles", {9: 62}),
                            ("total", {26: 402, 27: 403, 28: 404})):
        lab = rot[tarefa][0]
        for cid, v in codigos.items():
            hu[lab == cid] = v
    return hu


def _exame(env, tmp_path):
    from pydicom.uid import generate_uid

    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    hu = _codificar()
    pat = {"name": "CAVUM^Teste", "id": "CAV1", "birth": "19700101", "sex": "M"}
    study = {"uid": generate_uid(), "date": "20261030", "accession": "CAV01", "description": "TC CAVUM",
             "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 2, "description": "AX PARTES MOLES 1mm"}
    pasta = tmp_path / "cavum"
    for k in range(hu.shape[0]):
        ds = _base("1.2.840.10008.5.1.4.1.1.2", pat, study, series, "CT")
        ds.InstanceNumber = k + 1
        ds.ImagePositionPatient = [float(X[0]), float(Y[0]), float(Z[k])]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [1.0, 1.0]
        ds.SliceThickness = 1.0
        ds.RescaleSlope, ds.RescaleIntercept = 1, 0
        _mono(ds, hu[k], signed=True)
        _save(ds, pasta)
    Importer(db, paths.storage).import_paths([pasta])
    return study["uid"], series["uid"]


def test_trabalhador_simulado_e_gravacao(env, tmp_path):
    from ipe.ai import cefalometria_saida as CS
    from ipe.ai import totalseg as TS
    from ipe.imaging.series import FrameCache
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    uid, serie = _exame(env, tmp_path)
    t = TS.Trabalho(repo, FrameCache(256), None, uid, serie, simular=True)
    t.tarefas_proprias, t.min_cortes, t.modalidades = CF.tarefas, CF.MIN_CORTES, ("CT",)
    t.preparar()
    try:
        t.rodar_aqui()
        rot, versao, _s = t.ler_rotulos()
        assert set(rot) == {"head_glands_cavities", "headneck_bones_vessels", "craniofacial_structures",
                            "head_muscles", "total"}
        r = CF.calcular(t.vol, rot)
        assert r["palato_comprimento"].valor == pytest.approx(np.hypot(20, 30), abs=2.5)
        assert r["hioide_nivel"].texto == "platô inferior de C3"
        assert CF.classe_da_area(r["area"].valor) == "moderadamente reduzida"
        out = CS.gravar(t, r, versao, db, paths.storage, repo=repo)
        descs = [s.description for s in repo.series_for_study(uid)]
        assert CF.DESC_SEG in descs and CF.DESC_IMAGEM in descs
        CS.gravar(t, r, versao, db, paths.storage, repo=repo)                 # refazer troca, não duplica
        descs = [s.description for s in repo.series_for_study(uid)]
        assert descs.count(CF.DESC_SEG) == 1 and descs.count(CF.DESC_IMAGEM) == 1
        assert out["seg_path"]
    finally:
        t.limpar()


def test_imagem_de_conferencia_tem_o_sagital_e_as_linhas():
    vol, rot = fantoma()
    r = CF.calcular(vol, rot)
    from ipe.ai import cefalometria_saida as CS
    img, (y0, ztop) = CS.sagital_mediano(vol, r.x_meio)
    assert img.shape == (int((Z[0] - Z[-1]) / CS.PASSO) + 1, int((Y[-1] - Y[0]) / CS.PASSO) + 1)
    assert img[int((ztop - 70) / CS.PASSO), int((15 - y0) / CS.PASSO)] < -500          # a luz está no lugar
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    rgb = CS.desenhar(vol, r, {"paciente": "X", "data": "30/10/2026", "serie": "AX"})
    assert rgb.ndim == 3 and rgb.shape[2] == 3 and rgb.shape[0] >= 700
    amarelo = (rgb[..., 0] > 230) & (rgb[..., 1] > 200) & (rgb[..., 2] < 110)       # o plano mandibular
    assert amarelo.sum() > 50


def test_tela_automatica_abre_a_conferencia_e_edita(env, tmp_path, monkeypatch):
    import time

    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    from ipe.ui.viewer import aplicacoes as AP
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    _exame(env, tmp_path)
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", lambda _p, _t, msg, *a, **k: avisos.append(msg))
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, msg, *a, **k: avisos.append("ERRO " + msg))
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1300, 800)
    w.show()
    try:
        assert w.handle_external({"accession": "CAV01"}) == "aberto"
        tab = w.tabs.currentWidget()
        app.processEvents()
        assert tab.app_na_barra("cefalometria")                 # TC de cavum: a aplicação aparece
        assert AP.avaliar(AP.APLICACOES["cefalometria"], AP.Contexto({"CT"}, {"cranio"}, set()))[0] is False
        vp = next(v for v in tab.viewports if v.frames)
        tab.cefalometria_automatica(vp, simular=True)
        fim = time.time() + 120
        while not avisos and time.time() < fim:
            app.processEvents()
            time.sleep(0.05)
        assert avisos and avisos[-1].startswith("Cefalometria pronta"), avisos
        p = tab.cefalometria_painel
        assert p.automatica and p.isVisible()
        assert p.tabela.item(1, 2).text().startswith("36,")                   # comprimento do palato
        assert p.tabela.item(1, 4).text() == "automático"
        assert "7. Nível do hioide em relação à coluna: platô inferior de C3." in p.texto()
        # editar digitando: vira "editado" e o texto diz
        p.tabela.item(5, 2).setText("12,5")
        assert p.res["hioide_mp"].valor == pytest.approx(12.5) and p.tabela.item(5, 4).text() == "editado"
        assert "hioide ao plano mandibular: 12,5 mm" in p.texto() and "corrigidas à mão" in p.texto()
        p.tabela.setCurrentCell(5, 2)
        p._voltar_ao_automatico()
        assert p.res["hioide_mp"].origem == "automático"
        # medir à mão: a próxima régua num quadro vira o valor
        from ipe.imaging.measure import Annotation
        p.tabela.setCurrentCell(6, 2)
        p.medir_linha_atual()
        assert tab.left_tool == "measure"
        sp = vp.measure_spacing() or (1.0, 1.0)
        ann = Annotation("line", vp.frame_key(), [(10, 10), (10 + 45 / sp[1], 10)], study_uid=vp.study_uid,
                         series_uid=vp.series_uid, done=False)
        vp.annotations.append(ann)
        vp._finish(ann)
        assert p.res["lingua_transversal"].valor == pytest.approx(45.0, abs=0.5)
        assert p.res["lingua_transversal"].origem == "editado"
        # referências trocadas valem no texto e ficam guardadas
        p.salvar_referencias(dict(CF.REFERENCIAS, lingua_ap="até 80 mm"))
        assert "(até 80 mm)" in p.texto()
        assert tab.settings.get(CF.CHAVE_REFERENCIAS) == {"lingua_ap": "até 80 mm"}
    finally:
        w.close()


def test_a_mao_comeca_vazia_e_anda():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from ipe.ui.viewer.cefalometria_painel import vazio
    r = vazio()
    assert all(m.valor is None for m in r.medidas.values())
    r["palato_comprimento"].valor, r["palato_comprimento"].origem = 33.0, "editado"
    t = CF.texto_do_laudo(r, automatica=False)
    assert "1. Comprimento do palato mole: 33,0 mm (34 ± 6 mm)." in t and "corrigidas" not in t


def test_tarefas_sao_abertas_e_de_tc():
    nomes = [t["nome"] for t in CF.tarefas()]
    assert nomes == ["head_glands_cavities", "headneck_bones_vessels", "craniofacial_structures",
                     "head_muscles", "total"]
    # nenhuma das tarefas comerciais do TotalSegmentator (precisam de licença)
    assert not set(nomes) & {"face", "brain_structures", "tissue_types", "appendicular_bones"}


def test_instalador_baixa_os_modelos_da_cefalometria():
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    for arq in ("instalar_segmentacao.bat", "instalar_segmentacao.sh"):
        texto = (raiz / arq).read_text(encoding="utf-8")
        for t in ("head_glands_cavities", "headneck_bones_vessels", "craniofacial_structures", "head_muscles"):
            assert t in texto, (arq, t)
