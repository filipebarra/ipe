"""0.99.62 — nódulo pulmonar completo: segmentação por clique (separando o vaso), o mesmo nódulo no exame anterior
(pelo registro, ou provável sem ele), crescimento e tempo de duplicação, e o achado que entra na lesão já
acompanhada."""
from types import SimpleNamespace as NS

import numpy as np
import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.imaging import nodulo_clique as NC
from ipe.importer.scanner import Importer

N, NZ, PX, DZ = 64, 40, 0.8, 1.0


def _volume(raio_mm=5.0, vaso=True, centro=(20, 32, 32)):
    zz, yy, xx = np.mgrid[0:NZ, 0:N, 0:N].astype(float)
    data = np.full((NZ, N, N), -850.0)
    k, j, i = centro
    r = np.sqrt(((zz - k) * DZ) ** 2 + ((yy - j) * PX) ** 2 + ((xx - i) * PX) ** 2)
    data[r <= raio_mm] = 40.0
    if vaso:                                         # vaso fino (raio 0,6 mm) encostado no nódulo, até a borda
        rv = np.sqrt(((zz - k) * DZ) ** 2 + ((yy - j) * PX) ** 2)
        data[(rv <= 0.6) & (xx >= i)] = 30.0
    return data


def _vol(data):
    return NS(data=data, dz=DZ, dy=PX, dx=PX, origin=np.zeros(3), row_dir=np.array([1.0, 0, 0]),
              col_dir=np.array([0, 1.0, 0]), slice_vec=np.array([0, 0, DZ]),
              matrix=lambda: np.column_stack([[PX, 0, 0], [0, PX, 0], [0, 0, DZ]]),
              voxel_to_patient=lambda i, j, k: np.array([i * PX, j * PX, k * DZ]))


def test_segmenta_e_separa_o_vaso():
    v = _vol(_volume(5.0, vaso=True))
    m, off, av = NC.segmentar(v, (20, 32, 34))
    esfera = 4 / 3 * np.pi * 5.0 ** 3
    vol = m.sum() * PX * PX * DZ
    assert vol == pytest.approx(esfera, rel=0.25)                # o vaso ficou de fora
    m2, _off, av2 = NC.segmentar(v, (20, 32, 34), abrir=False)
    assert m2.sum() > m.sum() and any("borda da caixa" in a for a in av2)   # sem abertura vaza pelo vaso
    # o clique ao lado do nódulo (até 3 mm) ainda pega o nódulo
    m3, _o, _a = NC.segmentar(v, (20, 32, 32 - 8))
    assert m3 is not None and m3.sum() * PX * PX * DZ == pytest.approx(esfera, rel=0.3)
    nada, _o, av4 = NC.segmentar(_vol(np.full((NZ, N, N), -850.0)), (20, 32, 32))
    assert nada is None and av4
    from ipe.ai import nodulos as ND
    nums, centro = ND.numeros_do_nodulo(v, m, off)
    assert nums["medio_mm"]["v"] == pytest.approx(10.0, abs=1.5) and nums["consistencia"]["v"] == "sólido"
    assert centro[0] == pytest.approx(32 * PX, abs=1.0)


class _Repo:
    def __init__(self, reg=None):
        self.reg = reg

    def get_registration(self, a, b):
        return self.reg

    def get_registration_matriz(self, a, b):
        return None


def _ach(id_, st, pos, medio, vol, lobo="lobo superior direito", **kw):
    return {"id": id_, "study_uid": st, "posicao": pos, "local": lobo, "ferramenta": "nodulos", "estado": "confirmado",
            "numeros": {"medio_mm": {"v": medio, "u": "mm", "n": "Diâmetro médio"},
                        "volume_mm3": {"v": vol, "u": "mm³", "n": "Volume"}}, "corrigidos": {}, "rotulo": f"N{id_}", **kw}


def test_correspondente_e_crescimento():
    agora = _ach(10, "B", [10.0, 20.0, 30.0], 6.0, 113.0)
    antes = [_ach(1, "A", [12.0, 21.0, 31.0], 5.0, 65.0), _ach(2, "A", [60.0, 20.0, 30.0], 4.0, 30.0)]
    datas = {"A": "20250101", "B": "20250701"}
    c = NC.correspondente(_Repo(reg=([0, 0, 0], 0.0)), agora, antes, datas)
    assert c["achado"]["id"] == 1 and c["como"] == "pelo registro" and c["distancia"] < 3
    c = NC.correspondente(_Repo(), agora, antes, datas)
    assert c["achado"]["id"] == 1 and "sem registro" in c["como"]
    antes[0]["local"] = "lobo médio"
    assert NC.correspondente(_Repo(), agora, antes, datas) is None          # outro lobo, sem registro: não
    assert NC.correspondente(_Repo(reg=([0, 0, 0], 0)), agora, antes, {"A": "20260101", "B": "20250701"}) is None
    cr = NC.crescimento(antes[0], agora, "20250101", "20250701")
    assert cr["dias"] == 181 and cr["pct_vol"] == pytest.approx(73.8, abs=0.5)
    assert cr["td_dias"] == pytest.approx(181 * np.log(2) / np.log(113 / 65), rel=1e-6)
    assert "tempo de duplicação" in cr["partes"] and cr["quando"] == "01/01/2025"
    assert "não se aplica" in NC.crescimento(agora, antes[0], "20250101", "20250701")["partes"]


# ------------------------------------------------------------------ na tela
def _gravar_ct(pasta, acc, data, raio, study=None):
    pasta.mkdir(parents=True, exist_ok=True)
    study, serie, forr = study or generate_uid(), generate_uid(), generate_uid()
    vol = _volume(raio, vaso=True)
    for k in range(NZ):
        ds = Dataset()
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
        meta.MediaStorageSOPInstanceUID = generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds.file_meta = meta
        ds.SOPClassUID, ds.SOPInstanceUID = meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID
        ds.Modality = "CT"
        ds.PatientName, ds.PatientID, ds.PatientBirthDate, ds.PatientSex = "NODULO^TESTE", "NOD1", "19600101", "M"
        ds.StudyInstanceUID, ds.SeriesInstanceUID, ds.FrameOfReferenceUID = study, serie, forr
        ds.StudyDate, ds.SeriesDate, ds.StudyTime = data, data, "100000"
        ds.AccessionNumber, ds.StudyDescription, ds.SeriesDescription = acc, "TC DE TORAX", "PULMAO 1MM"
        ds.SeriesNumber, ds.InstanceNumber = 2, k + 1
        ds.ImagePositionPatient = [0.0, 0.0, float(k * DZ)]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing, ds.SliceThickness = [PX, PX], DZ
        ds.Rows = ds.Columns = N
        ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
        ds.BitsAllocated = ds.BitsStored = 16
        ds.HighBit, ds.PixelRepresentation = 15, 1
        ds.RescaleSlope, ds.RescaleIntercept = 1.0, 0.0
        ds.PixelData = vol[k].astype(np.int16).tobytes()
        ds.save_as(pasta / f"{acc}_{k:03d}.dcm", enforce_file_format=True)
    return study, serie


@pytest.fixture()
def janela(env, tmp_path):
    from test_pedidos_29_10 import _sem_protocolos
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    ant = _gravar_ct(tmp_path / "ct", "NOD0", "20250101", 4.0)
    atu = _gravar_ct(tmp_path / "ct", "NOD1", "20250701", 5.0)
    Importer(db, paths.storage).import_paths([tmp_path / "ct"])
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, _sem_protocolos(Settings(paths.settings_file)))
    w.resize(1300, 800)
    w.show()
    yield app, w, repo, ant, atu
    w.close()


def test_clique_guarda_e_entra_na_lesao_do_anterior(janela):
    from ipe.ui.viewer import achados_painel as AP
    from ipe.ui.viewer.lesion_panel import patient_key
    app, w, repo, (st_ant, se_ant), (st_atu, se_atu) = janela
    # no anterior: o nódulo já revisado e acompanhado como lesão
    pid = None
    w.handle_external({"accession": "NOD0"})
    tab0 = w.tabs.currentWidget()
    app.processEvents()
    pid = patient_key(tab0.study_info)
    lid = repo.save_lesion({"patient_id": pid, "name": "N1 (IA)", "location": "", "kind": "target"})
    a0 = repo.adicionar_achado(st_ant, "nodulos", {"series_uid": se_ant, "tipo": "Nódulo pulmonar",
                                                   "posicao": [32 * PX, 32 * PX, 20 * DZ],
                                                   "numeros": {"medio_mm": {"v": 8.0, "u": "mm", "n": "x"},
                                                               "volume_mm3": {"v": 268.0, "u": "mm³", "n": "x"}}},
                               "confirmado", "eu")
    assert a0["rotulo"] == "N1"
    repo.revisar_achado(a0["id"], "confirmado", "eu", lesao_id=lid)
    repo.save_registration(st_ant, st_atu, [0.0, 0.0, 0.0])
    # no atual: clique no nódulo
    w.handle_external({"accession": "NOD1"})
    tab = w.tabs.currentWidget()
    tab.set_layout(1, 1)
    app.processEvents()
    vp = tab.viewports[0]
    vp.go_to(20)
    menu = vp.build_context_menu(vp.image_to_widget(__import__("PySide6.QtCore", fromlist=["QPointF"]).QPointF(34, 32)))
    assert any("Nódulo pulmonar aqui" in a.text() for a in menu.actions())
    d = tab.nodulo_no_clique(vp, 34.5, 32.5)
    assert d is not None and d.mascara is not None
    assert d.numeros["medio_mm"]["v"] == pytest.approx(10.0, abs=1.5)
    assert d.obj in tab.overlay_objects and d.obj.volumes
    assert "Mesmo nódulo que N1 de 01/01/2025 (pelo registro)" in d.l_ant.text()
    # vidro fosco: limiar mais baixo
    d.c_vidro.setChecked(True)
    assert d.s_limiar.value() == NC.LIMIAR_VIDRO and d.mascara is not None
    d.c_vidro.setChecked(False)
    lid2 = d.guardar_e_acompanhar()
    assert lid2 == lid                                         # entrou na lesão que já existia
    a1 = [a for a in repo.achados(st_atu, "nodulos")][0]
    assert a1["estado"] == "confirmado" and a1["modelo"] == "Ipê: segmentação por clique" and a1["lesao_id"] == lid
    p = tab.achados_painel
    txt = p.texto_do_laudo()
    assert "Em relação ao exame de 01/01/2025 (N1)" in txt and "tempo de duplicação" in txt
    p.escolher(a1["id"])
    assert "Mesmo nódulo que N1" in p.l_origem.text()
    # rodar a IA de novo não apaga o achado feito à mão (só os sugeridos saem)
    repo.gravar_achados(st_atu, "nodulos", [])
    assert repo.achados(st_atu, "nodulos")
    d.close()
    p.close()
