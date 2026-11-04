"""0.99.44: limites da edição nas estruturas, estatística ampliada e conferência do registro."""
import sys
from pathlib import Path

import numpy as np
import pytest
from pydicom.uid import generate_uid

from ipe.imaging import estruturas as ES
from ipe.imaging import registro_rigido as RR
from ipe.imaging.fusion import Fusion
from ipe.imaging.volume import Volume

sys.path.insert(0, str(Path(__file__).parent))


def _grade():
    return ES.Grade((20, 64, 64), np.zeros(3), np.diag([1.0, 1.0, 2.0]))


def test_limites_area_faixa_e_sobrescrever():
    g = _grade()
    dados = np.zeros(g.forma, np.float32)
    dados[:, :, 32:] = 100                                   # metade direita "clara"
    orgao = ES.Estrutura("órgão", (1, 1, 1))
    ES.pintar(orgao, g, g.para_mm([32, 32, 10])[0], 12.0, normal=[0, 0, 1])
    les = ES.Estrutura("lesão", (2, 2, 2))
    c = g.para_mm([24, 32, 10])[0]
    # só dentro do órgão
    lim = ES.Limites(area="dentro", alvo=orgao)
    ES.pintar(les, g, c, 10.0, normal=[0, 0, 1], limites=lim)
    assert les.voxels and not (les.cheia(g) & ~orgao.cheia(g)).any()
    # só fora das outras
    fora = ES.Estrutura("fora", (3, 3, 3))
    ES.pintar(fora, g, c, 16.0, normal=[0, 0, 1], limites=ES.Limites(area="fora", outras=[orgao, les]))
    assert fora.voxels and not (fora.cheia(g) & orgao.cheia(g)).any()
    # só na faixa
    clara = ES.Estrutura("clara", (4, 4, 4))
    ES.pintar(clara, g, g.para_mm([32, 32, 10])[0], 10.0, normal=[0, 0, 1],
              limites=ES.Limites(faixa=(50, 150), dados=dados))
    assert clara.voxels and dados[clara.caixa()][clara.mascara].min() == 100
    # crescer respeita a faixa (restringir depois) e sobrescreve o órgão
    clara.guardar_para_desfazer()
    ES.crescer(clara, g, 4.0, so_no_plano=True)
    lim2 = ES.Limites(faixa=(50, 150), dados=dados, sobrescrever=True)
    ES.restringir(clara, clara._desfazer[-1], lim2)
    assert dados[clara.caixa()][clara.mascara].min() == 100
    antes = orgao.voxels
    mudaram = ES.sobrescrever(clara, clara._desfazer[-1], [orgao, clara])
    assert orgao in mudaram and orgao.voxels < antes and orgao.pode_desfazer()
    orgao.travada = True
    assert ES.sobrescrever(clara, clara._desfazer[-1], [orgao]) == []


def test_estatistica_ampliada():
    g = ES.Grade((60, 60, 60), np.zeros(3), np.diag([1.0, 1.0, 1.0]))
    z, y, x = np.mgrid[0:60, 0:60, 0:60]
    bola = ES.Estrutura("bola", (1, 1, 1))
    bola.definir((x - 30) ** 2 + (y - 30) ** 2 + (z - 30) ** 2 < 20 ** 2)
    rng = np.random.default_rng(0)
    dados = rng.normal(100, 10, g.forma).astype(np.float32)
    s = ES.estatisticas(bola, g, dados)
    assert abs(s["mediana"] - 100) < 0.5 and abs(s["assimetria"]) < 0.05 and abs(s["curtose"]) < 0.1
    assert s["p10"] < s["mediana"] < s["p90"] and 0 < s["entropia"] < 6
    assert 0.85 < s["esfericidade"] <= 1.0 and abs(s["feret_mm"] - 39) < 2.5
    assert s["alongamento"] > 0.95 and s["achatamento"] > 0.95
    elip = ES.Estrutura("elipsoide", (1, 1, 1))
    elip.definir(((x - 30) / 25) ** 2 + ((y - 30) / 10) ** 2 + ((z - 30) / 5) ** 2 < 1)
    f = ES.forma(elip, g)
    assert abs(f["alongamento"] - 10 / 25) < 0.05 and abs(f["achatamento"] - 5 / 25) < 0.05
    assert f["esfericidade"] < 0.8


def _cabeca():
    from test_registro_rigido import _cabeca as c
    return c()


def test_fusao_com_matriz_e_modos():
    A = _cabeca()
    from test_registro_rigido import _movido
    M = RR.matriz((0, 0, 8, 5, 0, 0), RR._cantos(A).mean(0))
    B = _movido(A, M)
    k = A.shape[0] // 2
    pos = A.voxel_to_patient(0, 0, k)
    h, w = A.shape[1:]
    fu = Fusion(B, "B")
    sem, _s = fu.values(pos, A.row_dir, A.col_dir, A.dy, A.dx, h, w)
    fu.matriz = M
    com, _s = fu.values(pos, A.row_dir, A.col_dir, A.dy, A.dx, h, w)
    a = A.data[k]
    dentro = a > 0
    erro_sem = np.nanmean(np.abs(sem - a)[dentro])
    erro_com = np.nanmean(np.abs(com - a)[dentro])
    assert erro_com < 0.5 * erro_sem                       # com a matriz, B cai em cima de A
    a8 = fu.cinza(a)
    fu.modo = "diferenca"
    assert fu.conferir(com, a8)[..., 0][dentro].mean() < fu.conferir(sem, a8)[..., 0][dentro].mean()
    fu.modo = "xadrez"
    al = fu.conferir(com, a8)[..., 3]
    assert 0.35 < (al == 255).mean() < 0.65
    fu.modo, fu.cortina = "cortina", 0.25
    al = fu.conferir(com, a8)[..., 3]
    assert (al[:, : w // 4 - 1] == 0).all() and (al[:, w // 4 + 1:][~np.isnan(com[:, w // 4 + 1:])] == 255).all()


def test_conferir_registro_na_tela(env, tmp_path):
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    from test_registro_rigido import _cabeca as cab, _movido, _serie
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    A = cab(48, 4.0)
    M = RR.matriz((0, 0, 8, 5, 0, 0), RR._cantos(A).mean(0))
    ea, eb = generate_uid(), generate_uid()
    _serie(tmp_path / "a", A, ea, generate_uid(), "A T1", "20260731")
    _serie(tmp_path / "b", _movido(A, M), eb, generate_uid(), "A T1", "20220124")
    Importer(db, paths.storage).import_paths([tmp_path / "a", tmp_path / "b"])
    repo.save_registration(ea, eb, [5, 0, 0], 0.0, method="rigido", matriz=M)
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        w.open_study(ea)
        QApplication.processEvents()
        tab = next(iter(w.all_viewer_tabs()))
        tab.add_study(eb)
        QApplication.processEvents()
        va = next(v for v in tab.viewports if v.study_uid == ea)
        tab._activate(va)
        fu = tab.conferir_registro("xadrez")
        assert fu is not None and va.fusion is fu and fu.modo == "xadrez" and np.allclose(fu.matriz, M)
        assert not va.grab().isNull()
        tab.conferir_registro("cortina")
        assert va.fusion.modo == "cortina"
        tab.conferir_registro(None)
        assert va.fusion is None
        assert "registro.conferir.xadrez" in tab.actions_by_id
    finally:
        w._really_quit = True
        w.settings.set("ui.confirmar_sair", False)
        w.close()


def test_painel_limites_e_numeros(env, tmp_path):
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    from test_registro_rigido import _serie
    QApplication.instance() or QApplication([])
    paths, db, repo = env
    d = np.zeros((10, 64, 64), np.float32)
    d[:, 16:48, 16:48] = 300
    v = Volume(d, np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 2.0]), 1.0, 1.0, None, "")
    estudo = generate_uid()
    _serie(tmp_path / "a", v, estudo, generate_uid(), "Ax T1", "20261101")
    Importer(db, paths.storage).import_paths([tmp_path / "a"])
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        w.open_study(estudo)
        QApplication.processEvents()
        tab = next(iter(w.all_viewer_tabs()))
        vp = tab.viewports[0]
        tab._activate(vp)
        p = tab.abrir_estruturas(vp)
        orgao = p.nova("Órgão")
        ES.pintar(orgao, p.grade, p.grade.para_mm([32, 32, 5])[0], 14.0, normal=[0, 0, 1])
        p.nova("Lesão")
        p.c_area.setCurrentIndex(p.c_area.findData("dentro"))
        p.c_area_alvo.setCurrentIndex(p.c_area_alvo.findData(orgao.id))
        p.c_sobre.setChecked(True)
        vp.go_to(5)
        orgao_antes = orgao.cheia(p.grade)
        p.b_pincel.setChecked(True)
        p.pincel(vp, 20.5, 32.5, "ini")
        p.pincel(vp, 20.5, 32.5, "fim")
        les = p.atual()
        assert les.nome == "Lesão" and les.voxels
        assert not (les.cheia(p.grade) & ~orgao_antes).any()                  # só dentro do órgão
        # sobrescrever: o órgão perdeu o que a lesão ganhou
        assert not (les.cheia(p.grade) & orgao.cheia(p.grade)).any()
        tsv = p.tabela_de_numeros().splitlines()
        assert tsv[0].startswith("estrutura\ttipo\tml") and len(tsv) == 3 and "esfericidade" in tsv[0]
        p._numeros()
        assert "mediana" in p.l_num.text() and "Feret" in p.l_num.text()
        p.encerrar()
    finally:
        w._really_quit = True
        w.settings.set("ui.confirmar_sair", False)
        w.close()
