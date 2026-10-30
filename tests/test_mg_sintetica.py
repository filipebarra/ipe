"""A 2D sintetizada da tomossíntese (V-Preview/C-View) é uma incidência, não um volume.

O relato: "aceite v-preview como se for a incidencia normal".

Medido no acervo dele antes de mexer no código: a V-Preview vem com a **classe SOP da
tomossíntese** (1.2.840.10008.5.1.4.1.1.13.1.3), sem `ImageLaterality` e sem `ViewPosition` — o
lado está só em `FrameLaterality`, dentro dos grupos funcionais, e a incidência só no
`ViewCodeSequence`. São 22 imagens assim no acervo, todas com um quadro e `GENERATED_2D` no
`ImageType`; os 22 volumes têm 14 a 60 cortes e dizem `MAXIMUM` ou `VOLUME`. Enquanto a classe SOP
decidia sozinha, a V-Preview contava como tomossíntese: a célula 2D do protocolo não a achava, e no
exame interrompido, que só tem V-Preview e volume, o quadro da CC abria o volume.

O fantoma aqui repete esse arranjo de tags — um fantoma com `ImageLaterality` preenchido não
provaria nada, porque o arquivo real não tem.
"""
import numpy as np
import pytest
from pydicom.uid import generate_uid
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.core.sample_data import _base, _mono, _save
from ipe.imaging import mammo as M
from ipe.importer.scanner import Importer

TOMO_SOP = "1.2.840.10008.5.1.4.1.1.13.1.3"
MG_2D_SOP = "1.2.840.10008.5.1.4.1.1.1.2"
CODIGO = {"CC": "cranio-caudal", "MLO": "medio-lateral oblique"}
H, W = 256, 200


def _mama(lado: str, soma: float = 0.0) -> np.ndarray:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx = W if lado == "R" else 0
    dentro = ((xx - cx) / (W * 0.9)) ** 2 + ((yy - H / 2) / (H * 0.45)) ** 2 < 1
    return np.where(dentro, 1500 + soma, 90).astype(np.float32)


def _grupos(ds, lado: str) -> None:
    """Onde o aparelho guarda o lado na V-Preview: nos grupos funcionais, não em ImageLaterality."""
    from pydicom.dataset import Dataset
    anat = Dataset()
    anat.FrameLaterality = lado
    anat.AnatomicRegionSequence = [Dataset()]
    anat.AnatomicRegionSequence[0].CodeValue = "T-04000"
    anat.AnatomicRegionSequence[0].CodingSchemeDesignator = "SRT"
    anat.AnatomicRegionSequence[0].CodeMeaning = "Breast"
    grupo = Dataset()
    grupo.FrameAnatomySequence = [anat]
    ds.SharedFunctionalGroupsSequence = [grupo]


def _codigo(ds, view: str) -> None:
    from pydicom.dataset import Dataset
    it = Dataset()
    it.CodeValue = "R-10226"
    it.CodingSchemeDesignator = "SRT"
    it.CodeMeaning = CODIGO[view]
    ds.ViewCodeSequence = [it]


def _vpreview(out, lado: str, view: str, study, pat, numero: int, nome="V-Preview"):
    series = {"uid": generate_uid(), "number": 1, "description": nome}
    ds = _base(TOMO_SOP, pat, study, series, "MG")
    ds.InstanceNumber = numero
    ds.ImageType = ["DERIVED", "PRIMARY", "TOMOSYNTHESIS", "GENERATED_2D"]
    ds.PixelSpacing = [0.1, 0.1]
    ds.ContentTime = "080000"
    _grupos(ds, lado)
    _codigo(ds, view)
    _mono(ds, _mama(lado), signed=False)
    return _save(ds, out / f"vprev_{lado}{view}")


def _volume(out, lado: str, view: str, study, pat, cortes: int = 14):
    series = {"uid": generate_uid(), "number": 200, "description": f"ROUTINE3D_VOL_{lado}{view}"}
    ds = _base(TOMO_SOP, pat, study, series, "MG")
    ds.InstanceNumber = 1
    ds.ImageType = ["DERIVED", "PRIMARY", "TOMOSYNTHESIS", "MAXIMUM"]
    ds.PixelSpacing = [0.1, 0.1]
    _grupos(ds, lado)
    _codigo(ds, view)
    vol = np.stack([_mama(lado, 20 * z) for z in range(cortes)]).astype(np.uint16)
    _mono(ds, vol[0], signed=False)
    ds.NumberOfFrames = cortes
    ds.PixelData = vol.tobytes()
    from ipe.core.sample_data import tomo_geometry
    tomo_geometry(ds, cortes, thickness_mm=55.0, force_n=80.0, angle_deg=0.0, side=lado)
    return _save(ds, out / f"vol_{lado}{view}")


def _adquirida(out, lado: str, view: str, study, pat, numero: int):
    """A 2D de verdade: processada pelo serviço, com lado e incidência nos campos padrão."""
    series = {"uid": generate_uid(), "number": 300, "description": "2D_PROC"}
    ds = _base(MG_2D_SOP, pat, study, series, "MG")
    ds.InstanceNumber = numero
    ds.ImageLaterality = lado
    ds.ViewPosition = view
    ds.AcquisitionTime = "081500"
    ds.ImagerPixelSpacing = [0.1, 0.1]
    _mono(ds, _mama(lado, 300), signed=False)
    return _save(ds, out / f"proc_{lado}{view}")


# ------------------------------------------------------------------ a regra, nos números medidos
def test_uma_imagem_nunca_e_volume():
    class Falso(dict):
        def get(self, k, d=None):
            return dict.get(self, k, d)
    gerada = Falso(ImageType=["DERIVED", "PRIMARY", "TOMOSYNTHESIS", "GENERATED_2D"])
    maximo = Falso(ImageType=["DERIVED", "PRIMARY", "TOMOSYNTHESIS", "MAXIMUM"])
    assert M.dois_d_sintetica(gerada, 1) is True
    assert M.dois_d_sintetica(gerada, 14) is False        # com cortes é volume, diga o que disser
    assert M.dois_d_sintetica(maximo, 14) is False
    assert M.dois_d_sintetica(maximo, 1) is False         # sem GENERATED_2D não há o que afirmar
    assert M.dois_d_sintetica(Falso(), 1) is False


@pytest.fixture()
def acervo(env, tmp_path):
    """Exame interrompido, como o dele: V-Preview das duas CC, volume só da esquerda."""
    paths, db, repo = env
    pat = {"name": "SINTETICA^Teste", "id": "SIN1", "birth": "19700101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20260101", "accession": "SIN001",
             "description": "MAMOGRAFIA DIGITAL", "for": generate_uid()}
    d = tmp_path / "sint"
    d.mkdir()
    _vpreview(d, "R", "CC", study, pat, 1)
    _vpreview(d, "L", "CC", study, pat, 2)
    _volume(d, "L", "CC", study, pat)
    Importer(db, paths.storage).import_paths([d])
    return repo, study["uid"]


def test_a_vpreview_entra_como_incidencia_2d(acervo):
    repo, uid = acervo
    imgs = M.read_images(repo, uid)
    sint = sorted([i for i in imgs if i.sintetica], key=lambda i: i.side)
    assert len(sint) == 2, [(i.side, i.view, i.serie) for i in imgs]
    for im, lado in zip(sint, ("L", "R")):
        assert (im.side, im.view) == (lado, "CC")   # lado dos grupos funcionais, incidência do código
        assert im.tomo is False and im.frames == 1
        assert im.exata is True                     # "V-Preview" não nomeia variante nenhuma
    vols = [i for i in imgs if i.tomo]
    assert len(vols) == 1 and vols[0].frames == 14 and vols[0].sintetica is False
    # a célula 2D do protocolo acha a V-Preview das duas mamas
    for code, lado in (("CCD", "R"), ("CCE", "L")):
        im = M.pick_image(imgs, M.parse_code(code))
        assert im is not None and im.side == lado and im.sintetica and not im.tomo


def test_defeito_volta_se_a_regra_for_desligada(acervo, monkeypatch):
    """Prova do defeito: com a classe SOP decidindo sozinha, não sobra nenhuma 2D no exame.

    A célula 2D do protocolo só podia cair na reserva "sem 2D, usa a tomossíntese" — e o quadro
    abria em modo tomossíntese, com a roda nos cortes, uma imagem que é uma imagem só.
    """
    repo, uid = acervo
    monkeypatch.setattr(M, "dois_d_sintetica", lambda ds, n: False)
    imgs = M.read_images(repo, uid)
    assert imgs and all(i.tomo for i in imgs), "teste inútil: ainda havia 2D no exame"
    for code in ("CCD", "CCE"):
        cell = M.parse_code(code)
        assert not [i for i in M.same_view(imgs, cell) if not i.tomo], code
        im = M.pick_image(imgs, cell)
        assert im is not None and im.tomo is True, code


def test_a_adquirida_ganha_da_sintetizada(env, tmp_path):
    paths, db, repo = env
    pat = {"name": "SINTETICA^Dois", "id": "SIN2", "birth": "19700101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20260102", "accession": "SIN002",
             "description": "MAMOGRAFIA DIGITAL", "for": generate_uid()}
    d = tmp_path / "sint2"
    d.mkdir()
    _vpreview(d, "R", "CC", study, pat, 1)
    _vpreview(d, "R", "MLO", study, pat, 2)
    _adquirida(d, "R", "CC", study, pat, 3)        # só a CC tem a 2D de verdade
    Importer(db, paths.storage).import_paths([d])
    imgs = M.read_images(repo, study["uid"])
    cc = M.pick_image(imgs, M.parse_code("CCD"))
    assert cc is not None and cc.sintetica is False and cc.serie == "2D_PROC"
    # as duas ficam na mesma lista do quadro, a sintetizada atrás da adquirida
    lista = M.same_view(imgs, M.parse_code("CCD"))
    assert [i.sintetica for i in lista] == [True, False]
    mlo = M.pick_image(imgs, M.parse_code("MLOD"))
    assert mlo is not None and mlo.sintetica is True     # sem adquirida, vale a sintetizada


def test_o_quadro_diz_que_a_imagem_e_sintetizada(env, tmp_path):
    """O programa devolve a incidência que o protocolo pediu — e diz qual imagem está na tela.

    Aceitar a V-Preview como a incidência não é fingir que ela é a imagem adquirida: quem lê
    calcificações precisa saber que está vendo a 2D sintetizada.
    """
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    pat = {"name": "SINTETICA^Tres", "id": "SIN3", "birth": "19700101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20260103", "accession": "SIN003",
             "description": "MAMOGRAFIA DIGITAL", "for": generate_uid()}
    d = tmp_path / "sint3"
    d.mkdir()
    for k, (lado, view) in enumerate((("R", "CC"), ("L", "CC"), ("R", "MLO"), ("L", "MLO")), 1):
        _vpreview(d, lado, view, study, pat, k)
    Importer(db, paths.storage).import_paths([d])
    app = QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1400, 900)
    w.show()
    w.open_study(study["uid"])
    tab = w.tabs.currentWidget()
    app.processEvents()
    try:
        assert tab.mg_session is not None
        cheios = [v for v in tab.viewports if v.mg_cell is not None and v._img is not None]
        assert len(cheios) == 4, [v.empty_note for v in tab.viewports]
        for vp in cheios:
            assert "2D sintética" in vp.series_label, vp.series_label
            assert vp.state.zoom > 1.02          # e abre enquadrada na mama, como qualquer outra
    finally:
        w.close()
