"""Exportar modelo 3D: malha correta, cinco formatos, laudo e redução."""
import json
import struct
import zipfile

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.imaging import mesh_io as MX
from ipe.imaging import surface as S
from ipe.importer.scanner import Importer


def _cubo(lado=10, grade=24):
    m = np.zeros((grade, grade, grade), bool)
    a = (grade - lado) // 2
    m[a:a + lado, a:a + lado, a:a + lado] = True
    return m


def _esfera(r=10, grade=40):
    z, y, x = np.mgrid[0:grade, 0:grade, 0:grade]
    c = grade // 2
    return ((z - c) ** 2 + (y - c) ** 2 + (x - c) ** 2) < r * r


# ------------------------------------------------------------------ a malha
def test_cubo_fecha_com_volume_certo():
    """O cubo de 10 voxels vira uma casca de 9 mm: volume exato e faces para fora."""
    v, f = S.mesh_from_mask(_cubo(), (1.0, 1.0, 1.0), smooth=0)
    r = MX.report(v, f)
    assert r.size_mm == pytest.approx((9.0, 9.0, 9.0))
    assert r.volume_ml * 1000 == pytest.approx(729.0, abs=0.5)      # 9³
    assert r.closed is True and r.outward is True and r.pieces == 1
    assert r.open_edges == 0 and r.printable is True


def test_voxel_que_nao_e_cubico_sai_na_escala():
    v, f = S.mesh_from_mask(_cubo(), (3.0, 1.0, 1.0), smooth=0)      # (dz, dy, dx)
    r = MX.report(v, f)
    assert r.size_mm == pytest.approx((9.0, 9.0, 27.0))
    assert r.volume_ml * 1000 == pytest.approx(9 * 9 * 27, abs=1)


def test_duas_pecas_soltas_sao_contadas():
    m = np.zeros((30, 30, 30), bool)
    m[4:10, 4:10, 4:10] = True
    m[20:26, 20:26, 20:26] = True
    v, f = S.mesh_from_mask(m, (1.0, 1.0, 1.0), smooth=0)
    r = MX.report(v, f)
    assert r.pieces == 2 and r.closed is True
    assert "2 peças soltas" in " ".join(r.lines())


def test_laudo_de_malha_vazia():
    r = MX.report(np.zeros((0, 3)), np.zeros((0, 3), int))
    assert r.faces == 0 and r.printable is False


# ------------------------------------------------------------------ redução
def test_reduzir_tira_triangulos_sem_perder_a_peca():
    v, f = S.mesh_from_mask(_esfera(), (1.0, 1.0, 1.0), smooth=2)
    antes = MX.report(v, f)
    v2, f2 = MX.decimate(v, f, 0.3)
    depois = MX.report(v2, f2)
    assert len(f2) < len(f)
    assert depois.volume_ml == pytest.approx(antes.volume_ml, rel=0.15)   # mesma peça
    assert MX.decimate(v, f, 1.0)[1].shape == f.shape                     # 100% não mexe


# ------------------------------------------------------------------ formatos
def _partes():
    v1, f1 = S.mesh_from_mask(_cubo(), (1.0, 1.0, 1.0), smooth=0)
    v2, f2 = S.mesh_from_mask(_esfera(6, 24), (1.0, 1.0, 1.0), smooth=1)
    return [MX.Part("osso", v1, f1, (222, 220, 210)),
            MX.Part("lesão", v2 + 40.0, f2, (200, 70, 60), 0.6)]


def test_stl_com_varias_pecas_vira_um_arquivo_por_peca(tmp_path):
    saida = MX.save(tmp_path / "m.stl", _partes(), "stl", "Teste")
    assert len(saida) == 2
    assert {p.name for p in saida} == {"m_osso.stl", "m_lesão.stl"}
    assert S.read_stl_header(saida[0]) == _partes()[0].n_faces
    um = MX.save(tmp_path / "so.stl", _partes()[:1], "stl", "Teste")
    assert len(um) == 1 and um[0].name == "so.stl"


def test_obj_leva_cor_num_arquivo_ao_lado(tmp_path):
    saida = MX.save(tmp_path / "m.obj", _partes(), "obj", "Teste")
    assert [p.suffix for p in saida] == [".obj", ".mtl"]
    obj = saida[0].read_text(encoding="utf-8")
    assert obj.count("\no ") == 2 and "mtllib m.mtl" in obj
    assert obj.count("\nv ") == sum(p.n_verts for p in _partes())
    assert obj.count("\nf ") == sum(p.n_faces for p in _partes())
    mtl = saida[1].read_text(encoding="utf-8")
    assert mtl.count("newmtl ") == 2 and "d 0.600" in mtl          # a lesão é translúcida


def test_ply_guarda_cor_por_vertice(tmp_path):
    caminho = MX.save(tmp_path / "m.ply", _partes(), "ply")[0]
    dados = caminho.read_bytes()
    fim = dados.index(b"end_header\n") + len(b"end_header\n")
    cab = dados[:fim].decode("utf-8")
    partes = _partes()
    assert f"element vertex {sum(p.n_verts for p in partes)}" in cab
    assert f"element face {sum(p.n_faces for p in partes)}" in cab
    assert "property uchar red" in cab and "binary_little_endian" in cab
    corpo = dados[fim:]                                            # o cabeçalho tem acento: conta bytes
    assert len(corpo) == sum(p.n_verts for p in partes) * 15 + sum(p.n_faces for p in partes) * 13


def test_glb_abre_como_gltf_valido(tmp_path):
    caminho = MX.save(tmp_path / "m.glb", _partes(), "glb", "Teste")[0]
    b = caminho.read_bytes()
    magic, versao, total = struct.unpack("<III", b[:12])
    assert magic == 0x46546C67 and versao == 2 and total == len(b)
    jlen, jtipo = struct.unpack("<II", b[12:20])
    assert jtipo == 0x4E4F534A
    g = json.loads(b[20:20 + jlen])
    assert len(g["meshes"]) == 2 and len(g["materials"]) == 2
    assert [m["name"] for m in g["materials"]] == ["osso", "lesão"]
    assert g["materials"][1]["alphaMode"] == "BLEND"               # opacidade 0,6
    assert all("min" in a and "max" in a for a in g["accessors"] if a["type"] == "VEC3")
    blen, btipo = struct.unpack("<II", b[20 + jlen:28 + jlen])
    assert btipo == 0x004E4942 and g["buffers"][0]["byteLength"] == blen


def test_glb_gira_para_ficar_em_pe():
    v = np.array([[1.0, 2.0, 3.0]])                                 # x, y (posterior), z (superior)
    assert MX.para_gltf(v).tolist() == [[1.0, 3.0, -2.0]]           # Y para cima, Z para o observador


def test_3mf_sai_em_milimetros_e_com_cor(tmp_path):
    caminho = MX.save(tmp_path / "m.3mf", _partes(), "3mf", "Teste")[0]
    with zipfile.ZipFile(caminho) as z:
        assert set(z.namelist()) == {"[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"}
        xml = z.read("3D/3dmodel.model").decode("utf-8")
    assert 'unit="millimeter"' in xml
    assert xml.count("<object ") == 2 and xml.count("<base ") == 2
    assert xml.count("<item ") == 2 and "#DEDCD2FF" in xml          # cor do osso
    assert xml.count("<triangle ") == sum(p.n_faces for p in _partes())


def test_formato_desconhecido_e_malha_vazia(tmp_path):
    with pytest.raises(ValueError):
        MX.save(tmp_path / "m.xyz", _partes(), "xyz")
    vazia = [MX.Part("nada", np.zeros((0, 3)), np.zeros((0, 3), int))]
    with pytest.raises(ValueError):
        MX.save(tmp_path / "m.stl", vazia, "stl")


# ------------------------------------------------------------------ na janela
def test_janela_junta_pecas_e_grava(env, sample_dir, tmp_path):
    from ipe.imaging.series import FrameCache, build_frames
    from ipe.imaging.volume import build_volume
    from ipe.ui.surface_dialog import SurfaceDialog
    paths, db, repo = env
    QApplication.instance() or QApplication([])
    Importer(db, paths.storage).import_paths([sample_dir])
    uid = repo.find_study_uids(accession="ACC1001")[0]
    s = repo.series_for_study(uid)[0]
    vol = build_volume(build_frames(repo.instances_for_series(s.series_uid), s.series_uid),
                       FrameCache(512))
    dlg = SurfaceDialog(vol, None, (0, 0, 0), "Fantoma")
    dlg.lo.setValue(200)
    dlg.passo.setValue(2)
    assert dlg.calcular() is True
    assert len(dlg.parts) == 1 and dlg.tabela.rowCount() == 1
    assert dlg.b_gravar.isEnabled()
    # segunda peça, com outra faixa e outra cor
    dlg.lo.setValue(-300)
    assert dlg.calcular("pele") is True
    assert [p.name for p in dlg.parts] == ["Fantoma", "pele"]
    assert dlg.parts[0].color != dlg.parts[1].color
    assert "peça(s)" in dlg.info.text()
    # tirar peça
    dlg.tabela.setCurrentCell(1, 0)
    dlg._tirar()
    assert len(dlg.parts) == 1
    # gravar sem diálogo de arquivo
    arquivos = MX.save(tmp_path / "saida.glb", dlg.parts, "glb", "Fantoma")
    assert arquivos[0].exists() and arquivos[0].stat().st_size > 1000


def test_modelo_do_que_esta_na_tela_do_3d():
    """O modelo tem que respeitar corte, escultura e maca tirada."""
    from ipe.imaging.render3d import Renderer3D

    class V:
        def __init__(s, d):
            s.data = d.astype(np.float32); s.shape = d.shape
            s.dx = s.dy = s.dz = 1.0
            s.origin = np.zeros(3)
            s.row_dir = np.array([1.0, 0, 0]); s.col_dir = np.array([0, 1.0, 0])
            s.slice_vec = np.array([0, 0, 1.0]); s.window = None; s.source_path = ""

        def matrix(s):
            return np.column_stack([s.row_dir * s.dx, s.col_dir * s.dy, s.slice_vec])

        def voxel_to_patient(s, i, j, k):
            return s.origin + s.matrix() @ np.array([i, j, k], float)

    d = np.full((40, 40, 40), -900.0)
    d[10:30, 10:30, 10:30] = 800.0
    r = Renderer3D(V(d), max_dim=40)
    inteiro = int(r.solid_mask(200).sum())
    assert inteiro > 0
    r.cut_plane(r.point_of((20, 20, 20)), [0, 0, 1], keep="front")
    cortado = int(r.solid_mask(200).sum())
    assert 0 < cortado < inteiro                     # o corte tirou metade
    r.restore_all()
    r.sculpt([(0, 0), (200, 0), (200, 200), (0, 200)], (400, 400), 0, 0)
    assert int(r.solid_mask(200).sum()) < inteiro    # a escultura também conta
