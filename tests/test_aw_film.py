"""Filme da estação AW ("AW electronic film" e "pages"): é impressão, não série do exame."""
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer
from ipe.printing import aw_film as AW

SC = "1.2.840.10008.5.1.4.1.1.7"


def _exame(pasta, com_pages=True, n_film=3, n_pages=2):
    """Exame de RM com uma série normal e as séries de filme da AW."""
    from pydicom.uid import generate_uid
    from ipe.core.sample_data import _base, _mono, _save
    pat = {"name": "AW^Fantoma", "id": "AW1", "birth": "19700101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20260910", "accession": "AWF001",
             "description": "RM CRANIO", "for": generate_uid()}
    yy, xx = np.mgrid[0:96, 0:96].astype(np.float32)
    normal = {"uid": generate_uid(), "number": 3, "description": "AX T2"}
    for k in range(4):
        ds = _base("1.2.840.10008.5.1.4.1.1.4", pat, study, normal, "MR")
        ds.InstanceNumber = k + 1
        ds.PixelSpacing = [1.0, 1.0]
        ds.ImagePositionPatient = [0, 0, k * 5.0]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        _mono(ds, 300 + 400 * np.exp(-(((xx - 48) / 20) ** 2 + ((yy - 48) / 20) ** 2)), signed=False)
        _save(ds, pasta / "mr")

    def filme(desc, numero, n, linhas, colunas):
        se = {"uid": generate_uid(), "number": numero, "description": desc}
        for k in range(n):
            ds = _base(SC, pat, study, se, "MR")
            ds.InstanceNumber = k + 1
            ds.ConversionType = "WSD"
            ds.ImageType = ["DERIVED", "SECONDARY", "SCREEN SAVE"]
            ds.ManufacturerModelName = "FILMER_5.2"
            _mono(ds, np.full((linhas, colunas), 500 + 100 * k, np.float32), signed=False)
            _save(ds, pasta / "aw")
    filme("AW electronic film", 27206, n_film, 120, 90)
    if com_pages:
        filme("AW electronic pages", 27207, n_pages, 200, 141)
    return study["uid"]


# ------------------------------------------------------------------ reconhecimento
def test_reconhece_pelo_nome():
    assert AW.kind_of("AW electronic pages") == "pages"
    assert AW.kind_of("  aw electronic FILM  ") == "film"       # caixa e espaço não contam
    assert AW.kind_of("AW  electronic  film") == "film"
    assert AW.kind_of("AX T2") == "" and AW.kind_of(None) == ""
    assert AW.is_print_series("AW electronic film") is True
    assert AW.is_print_series("Sagital T1") is False


def test_separa_folha_de_imagem():
    class S:
        def __init__(self, d): self.description = d
    pages, film = AW.split([S("AX T2"), S("AW electronic pages"), S("AW electronic film")])
    assert [s.description for s in pages] == ["AW electronic pages"]
    assert [s.description for s in film] == ["AW electronic film"]


# ------------------------------------------------------------------ fora do visualizador
def test_some_do_visualizador(env, tmp_path):
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    pasta = tmp_path / "exame"
    pasta.mkdir()
    uid = _exame(pasta)
    Importer(db, paths.storage).import_paths([pasta])
    assert len(repo.series_for_study(uid)) == 3            # no banco continuam as três
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1000, 700)
    w.show()
    w.browser.refresh()
    assert w.handle_external({"accession": "AWF001"}) == "aberto"
    tab = w.tabs.currentWidget()
    app.processEvents()
    descricoes = [s.description for s in tab.series]
    assert descricoes == ["AX T2"]                         # o visualizador só vê o exame
    assert not any(AW.is_print_series(d) for d in descricoes)
    w.close()


# ------------------------------------------------------------------ na aba de impressões
def test_vira_trabalho_de_impressao(env, tmp_path):
    paths, db, repo = env
    pasta = tmp_path / "exame"
    pasta.mkdir()
    uid = _exame(pasta, n_film=3, n_pages=2)
    Importer(db, paths.storage).import_paths([pasta])
    linhas = AW.studies(repo)
    assert len(linhas) == 1
    r = linhas[0]
    assert r["kind"] == "aw" and r["study_uid"] == uid
    assert r["sheets"] == 2 and r["images"] == 3           # 2 folhas montadas, 3 imagens
    assert r["patient_id"] == "AW1" and r["status"] == "new"
    assert not r["message"]
    from datetime import datetime
    assert isinstance(r["received_at"], datetime)          # a coluna "Chegada" quer datetime
    assert r["received_at"].strftime("%d/%m/%Y") == "10/09/2026"

    job, folder = AW.to_job(repo, uid, tmp_path / "filmes")
    assert job is not None and job.sheets == 2             # uma folha por página
    assert job.study_uid == uid and job.patient_name
    assert all(f.display_format == "STANDARD\\1,1" for f in job.films)
    assert all(f.orientation == "PORTRAIT" for f in job.films)   # 200×141 é em pé
    assert len(list(folder.glob("*.dcm"))) == 2


def test_sem_folha_montada_usa_as_imagens(env, tmp_path):
    paths, db, repo = env
    pasta = tmp_path / "exame"
    pasta.mkdir()
    uid = _exame(pasta, com_pages=False, n_film=4)
    Importer(db, paths.storage).import_paths([pasta])
    r = AW.studies(repo)[0]
    assert r["sheets"] == 4 and r["images"] == 4
    assert "Sem a folha montada" in r["message"]
    job, _folder = AW.to_job(repo, uid, tmp_path / "filmes")
    assert job is not None and job.sheets == 4
    assert job.films[0].orientation == "PORTRAIT"          # 120 linhas × 90 colunas: mais alta que larga


def test_exame_sem_filme_nao_aparece(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    assert AW.studies(repo) == []
    assert AW.to_job(repo, repo.find_study_uids(accession="ACC1001")[0], paths.storage) == (None, None)


def test_aba_de_impressoes_lista_e_preve(env, tmp_path):
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    pasta = tmp_path / "exame"
    pasta.mkdir()
    uid = _exame(pasta)
    Importer(db, paths.storage).import_paths([pasta])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1100, 700)
    w.show()
    aba = w.show_prints()
    app.processEvents()
    linhas = [r for r in aba.rows if r["kind"] == "aw"]
    assert len(linhas) == 1 and linhas[0]["study_uid"] == uid
    assert aba._de_onde(linhas[0]) == "veio no exame (estação AW)"
    job, folder = aba._job(linhas[0])
    assert job is not None and job.sheets == 2
    assert aba._job(linhas[0])[0] is job                   # veio do cache na segunda vez
    # a linha diz que veio no exame, e não "montado aqui"
    coluna = [aba.table.item(i, 0).text() for i in range(aba.table.rowCount())]
    assert "Veio no exame" in coluna
    w.close()


def test_imagem_de_16_bits_vira_oito_sem_escurecer(env, tmp_path):
    """Imagem solta da AW às vezes vem em 16 bits: sem janela, a folha sairia quase preta."""
    import numpy as np
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian
    from ipe.printing.aw_film import _oito_bits

    def meta(d):
        d.file_meta = FileMetaDataset()
        d.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        return d
    ds = Dataset()
    ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit, ds.PixelRepresentation = 15, 0
    ds.Rows, ds.Columns = 8, 8
    px = np.full((8, 8), 300, np.uint16)
    px[2:6, 2:6] = 1200                                    # nada perto do teto de 65535
    ds.PixelData = px.tobytes()
    item = _oito_bits(meta(ds))
    a = np.frombuffer(item.PixelData, np.uint8).reshape(8, 8)
    assert item.BitsStored == 8 and int(a.max()) > 200 and int(a.min()) < 60
    # RGB de 8 bits passa como veio, sem mexer nos pixels
    rgb = Dataset()
    rgb.SamplesPerPixel, rgb.PhotometricInterpretation = 3, "RGB"
    rgb.BitsAllocated = rgb.BitsStored = 8
    rgb.Rows, rgb.Columns, rgb.PlanarConfiguration = 4, 4, 0
    rgb.HighBit, rgb.PixelRepresentation = 7, 0
    rgb.PixelData = bytes(range(48))
    assert _oito_bits(meta(rgb)) is rgb
