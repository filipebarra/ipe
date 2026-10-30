"""Calibração GSDF do monitor e superfície/STL."""
import numpy as np
from PySide6.QtWidgets import QApplication

from ipe.imaging import gsdf, surface as S


# ---------------------------------------------------------------- GSDF
def test_curva_gsdf_e_tabela():
    # a curva do padrão é crescente e cobre a faixa usada em radiologia
    assert gsdf.luminance(1) < gsdf.luminance(500) < gsdf.luminance(1023)
    assert 0.03 < float(gsdf.luminance(1)) < 0.10 and 3000 < float(gsdf.luminance(1023)) < 5000
    # ida e volta: luminância -> JND -> luminância
    for j in (10, 200, 800):
        assert abs(float(gsdf.jnd_index(gsdf.luminance(j))) - j) < 1.0

    t = gsdf.lut(0.5, 300.0, 2.2)
    assert t.shape == (256,) and t[0] == 0 and t[-1] == 255
    assert np.all(np.diff(t.astype(int)) >= 0)             # não pode inverter tons
    com = gsdf.deviation(t, 0.5, 300.0, 2.2)
    sem = gsdf.deviation(np.arange(256, dtype=np.uint8), 0.5, 300.0, 2.2)
    assert com < 10.0 and sem > 40.0 and com < sem / 5     # corrigido fica muito melhor
    # aplicar a tabela numa imagem não muda o tamanho nem estoura
    img = np.arange(256, dtype=np.uint8).reshape(16, 16)
    saida = gsdf.apply(img, t)
    assert saida.shape == img.shape and saida.dtype == np.uint8


def test_padroes_de_teste():
    p = gsdf.pattern("steps", 320, 200)
    assert p.shape == (200, 320) and p.min() == 0 and p.max() == 255
    # os 16 degraus ficam em ordem crescente
    meio = p[10, :]
    tons = [int(meio[int((i + 0.5) * 320 / 16)]) for i in range(16)]
    assert tons == sorted(tons) and len(set(tons)) == 16
    # o quadrado do meio é 5% mais claro que o degrau
    assert int(p[100, 10]) > int(p[10, 10])
    for nome in gsdf.PATTERNS:
        assert gsdf.pattern(nome, 128, 96).shape == (96, 128)


def test_dialogo_gsdf(env, tmp_path):
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.core.config import Settings
    from ipe.ui.gsdf_dialog import GsdfDialog
    settings = Settings(paths.settings_file)
    dlg = GsdfDialog(settings)
    dlg.on.setChecked(True)
    dlg.lmin.setValue(0.6)
    dlg.lmax.setValue(350.0)
    dlg._salvar()
    app.processEvents()
    chave = dlg._chave()
    cfg = gsdf.config(settings, chave)
    assert cfg["on"] and cfg["lmin"] == 0.6 and cfg["lmax"] == 350.0
    assert gsdf.table_for(settings, chave) is not None
    # desligada, não devolve tabela
    gsdf.save_config(settings, chave, {**cfg, "on": False})
    assert gsdf.table_for(settings, chave) is None
    dlg.deleteLater()


# ---------------------------------------------------------------- superfície / STL
def _esfera(n=40, raio=12.0):
    z, y, x = np.mgrid[0:n, 0:n, 0:n]
    return ((z - n / 2) ** 2 + (y - n / 2) ** 2 + (x - n / 2) ** 2) < raio ** 2


def test_malha_da_esfera_e_stl(tmp_path):
    mask = _esfera()
    v, f = S.mesh_from_mask(mask, (1.0, 1.0, 1.0))
    assert len(v) > 500 and len(f) > 1000
    # a superfície é fechada: cada aresta aparece em exatamente dois triângulos
    arestas = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    arestas = np.sort(arestas, axis=1)
    _u, contagem = np.unique(arestas, axis=0, return_counts=True)
    assert set(np.unique(contagem)) == {2}, "a malha não ficou fechada"
    # e tem o tamanho da esfera (raio 12 -> ~24 de diâmetro)
    tamanho = v.max(axis=0) - v.min(axis=0)
    assert all(21.0 < t < 25.0 for t in tamanho)

    caminho = tmp_path / "esfera.stl"
    S.write_stl(caminho, v, f, "esfera")
    assert caminho.exists() and S.read_stl_header(caminho) == len(f)
    assert caminho.stat().st_size == 84 + 50 * len(f)
    # o passo deixa a malha bem mais leve
    v2, f2 = S.mesh_from_mask(mask, (1.0, 1.0, 1.0), step=2)
    assert 0 < len(f2) < len(f) / 2


def test_limiar_maior_peca_e_espacamento():
    dados = np.zeros((30, 30, 30), np.int16)
    dados[10:20, 10:20, 10:20] = 800          # bloco grande
    dados[2:4, 2:4, 2:4] = 800                # ilha solta
    m = S.mask_from_threshold(dados, 200)
    assert m.sum() == 1000 + 8
    maior = S.keep_largest(m)
    assert maior.sum() == 1000                # a ilha saiu
    assert abs(S.volume_ml(maior, (2.0, 0.5, 0.5)) - 0.5) < 1e-6
    v, f = S.mesh_from_mask(maior, (2.0, 0.5, 0.5), smooth=0)      # (dz, dy, dx)
    tamanho = v.max(axis=0) - v.min(axis=0)
    # o bloco tem 10 voxels em cada eixo: 5 mm em x e y (0,5 mm) e 20 mm em z (2 mm),
    # com a folga de um voxel que a malha tira ao passar pelo meio das células
    assert 4.0 <= tamanho[0] <= 5.5 and 4.0 <= tamanho[1] <= 5.5
    assert 17.5 <= tamanho[2] <= 20.5


def test_dialogo_de_superficie(tmp_path):
    app = QApplication.instance() or QApplication([])
    from dataclasses import dataclass, field

    @dataclass
    class VolFake:
        data: np.ndarray
        origin: np.ndarray = field(default_factory=lambda: np.zeros(3))
        dx: float = 1.0
        dy: float = 1.0
        dz: float = 1.0

        def matrix(self):
            return np.diag([self.dx, self.dy, self.dz])

    dados = np.zeros((30, 30, 30), np.int16)
    dados[8:22, 8:22, 8:22] = 900
    from ipe.ui.surface_dialog import SurfaceDialog
    dlg = SurfaceDialog(VolFake(dados))
    dlg.lo.setValue(200)
    assert dlg.calcular() is True
    app.processEvents()
    peca = dlg.parts[0]
    assert len(peca.faces) > 100
    assert "triângulos" in dlg.info.text()
    caminho = tmp_path / "bloco.stl"
    S.write_stl(caminho, peca.verts, peca.faces)
    assert S.read_stl_header(caminho) == len(peca.faces)
    dlg.deleteLater()
