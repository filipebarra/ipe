"""Relatório do acervo: o que está guardado, em que formato, e quanto a compressão renderia."""

import numpy as np
import pydicom
import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, JPEG2000Lossless, RLELossless, generate_uid

from ipe.core import acervo as A

EXPL = "1.2.840.10008.1.2.1"


def _grava(pasta, modalidade="CT", linhas=64, colunas=64, semente=0, estudo=None, serie=None):
    """Um arquivo sem compressão, com ruído suave — comprime como imagem médica, não como zero."""
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.SOPClassUID = ds.file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
    ds.PatientName = "ACERVO^Teste"
    ds.PatientID = "ACV001"
    ds.StudyInstanceUID = estudo or "1.2.3.4.5.6.7.8.9"
    ds.SeriesInstanceUID = serie or generate_uid()
    ds.StudyDate = "20260101"
    ds.SeriesNumber = 1
    ds.InstanceNumber = semente + 1
    ds.Modality = modalidade
    ds.Rows, ds.Columns = linhas, colunas
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    y, x = np.mgrid[0:linhas, 0:colunas]
    rng = np.random.default_rng(semente)
    img = (400 + 200 * np.sin(x / 7.0) + 150 * np.cos(y / 9.0) + rng.integers(0, 40, (linhas, colunas)))
    ds.PixelData = img.astype(np.uint16).tobytes()
    caminho = pasta / f"{ds.SOPInstanceUID}.dcm"
    ds.save_as(str(caminho), enforce_file_format=True)
    return str(caminho)


# ------------------------------------------------------------------ tabela de sintaxes
def test_sintaxe_conhecida_sabe_o_que_e():
    assert A.sintaxe(EXPL).tipo == A.SEM
    assert A.sintaxe("1.2.840.10008.1.2.4.70").tipo == A.LOSSLESS
    assert A.sintaxe("1.2.840.10008.1.2.4.50").tipo == A.LOSSY
    assert A.sintaxe("1.2.840.10008.1.2.4.80").escreve          # pydicom 3 grava JPEG-LS
    assert not A.sintaxe("1.2.840.10008.1.2.4.70").escreve      # e não grava o .70


def test_sintaxe_desconhecida_nao_some_do_relatorio():
    s = A.sintaxe("1.2.3.4.inventada")
    assert s.nome == "1.2.3.4.inventada" and s.tipo == A.DESCONHECIDA


def test_sintaxe_vazia_nao_quebra():
    assert A.sintaxe("").nome == "—"


# ------------------------------------------------------------------ levantamento
def test_levantamento_soma_por_sintaxe_modalidade_e_tipo():
    acv = A.Acervo([
        A.Linha("CT", EXPL, 10, 1000, 500),
        A.Linha("MR", EXPL, 5, 500, 250),
        A.Linha("CT", "1.2.840.10008.1.2.4.50", 4, 100, 400),
    ])
    assert acv.arquivos == 19 and acv.bytes == 1600
    assert acv.bytes_do_tipo(A.SEM) == 1500
    assert acv.bytes_do_tipo(A.LOSSY) == 100
    assert [m for m, *_ in acv.por_modalidade()] == ["CT", "MR"]      # maior primeiro
    assert len(acv.por_sintaxe()) == 2
    assert [l.modalidade for l in acv.sem_compressao()] == ["CT", "MR"]


def test_bytes_por_pixel_denuncia_o_que_esta_sem_compressao():
    """Perto de 2 é 16 bits crus: é assim que se vê que o acervo não está comprimido."""
    assert A.Linha("CT", EXPL, 1, 2048, 1024).bytes_por_pixel == pytest.approx(2.0)
    assert A.Linha("CT", EXPL, 1, 0, 0).bytes_por_pixel == 0.0       # sem pixel, sem divisão


def test_levantamento_sai_do_banco(env, tmp_path):
    paths, db, repo = env
    from ipe.importer.scanner import Importer
    pasta = tmp_path / "dcm"
    pasta.mkdir()
    for i in range(3):
        _grava(pasta, "CT", semente=i)
    Importer(db, paths.storage).import_paths([pasta])
    acv = A.levantar(repo)
    assert acv.arquivos == 3
    assert acv.bytes > 0
    assert [l.sintaxe_uid for l in acv.linhas] == [EXPL]
    assert acv.bytes_do_tipo(A.SEM) == acv.bytes


def test_amostra_pega_series_diferentes(env, tmp_path):
    paths, db, repo = env
    from ipe.importer.scanner import Importer
    pasta = tmp_path / "dcm"
    pasta.mkdir()
    for i in range(4):
        _grava(pasta, "CT", semente=i)
    Importer(db, paths.storage).import_paths([pasta])
    assert len(A.amostra(repo, por_grupo=2)) == 2


# ------------------------------------------------------------------ medição
def test_medicao_comprime_em_memoria_e_nao_toca_no_original(tmp_path):
    caminho = _grava(tmp_path)
    antes = open(caminho, "rb").read()
    medidas = A.medir([caminho], uids=("1.2.840.10008.1.2.5",))
    assert open(caminho, "rb").read() == antes          # o original é sagrado
    m = medidas[0]
    assert m.arquivos == 1 and m.razao > 1.0            # RLE sempre rende em imagem suave
    assert pydicom.dcmread(caminho).file_meta.TransferSyntaxUID == ExplicitVRLittleEndian


def test_medicao_pula_o_que_ja_esta_comprimido(tmp_path):
    caminho = _grava(tmp_path)
    ds = pydicom.dcmread(caminho)
    ds.compress(RLELossless)
    ds.save_as(str(tmp_path / "comprimido.dcm"), enforce_file_format=True)
    medidas = A.medir([str(tmp_path / "comprimido.dcm")], uids=("1.2.840.10008.1.2.5",))
    assert medidas[0].arquivos == 0                     # recomprimir mediria o trabalho errado


def test_medicao_diz_quando_o_codificador_falta(monkeypatch, tmp_path):
    monkeypatch.setattr(A, "codificadores", lambda: {"1.2.840.10008.1.2.4.80": (False, "pyjpegls")})
    m = A.medir([_grava(tmp_path)], uids=("1.2.840.10008.1.2.4.80",))[0]
    assert not m.disponivel and m.falta == "pyjpegls" and m.arquivos == 0
    assert m.razao == 0.0                               # sem medida não se inventa número


def test_medicao_para_no_meio_quando_pedido(tmp_path):
    import threading
    stop = threading.Event()
    stop.set()
    assert A.medir([_grava(tmp_path)], stop=stop)[0].arquivos == 0


def test_medicao_ignora_arquivo_ilegivel(tmp_path):
    ruim = tmp_path / "nao_e_dicom.dcm"
    ruim.write_bytes(b"isto nao e DICOM")
    medidas = A.medir([str(ruim), _grava(tmp_path)], uids=("1.2.840.10008.1.2.5",))
    assert medidas[0].arquivos == 1                     # o bom é medido; o ruim é pulado


def test_arquivo_grande_rende_mais_que_o_rle_no_jpeg2000(tmp_path):
    """Confere a ordem que a decisão usa: J2K sem perda rende mais que RLE."""
    if not A.codificadores().get("1.2.840.10008.1.2.4.90", (False, ""))[0]:
        pytest.skip("sem codificador de JPEG 2000 nesta máquina")
    caminho = _grava(tmp_path, linhas=256, colunas=256)
    rle, j2k = A.medir([caminho], uids=("1.2.840.10008.1.2.5", "1.2.840.10008.1.2.4.90"))
    assert j2k.razao > rle.razao > 1.0


# ------------------------------------------------------------------ projeção
def test_projecao_so_mexe_no_que_esta_sem_compressao():
    acv = A.Acervo([A.Linha("CT", EXPL, 1, 1000, 500),
                    A.Linha("CT", "1.2.840.10008.1.2.4.50", 1, 300, 600)])
    m = A.Medida("1.2.840.10008.1.2.5", arquivos=1, bytes_origem=200, bytes_saida=100)
    (medida, hoje, depois), = A.projetar(acv, [m])
    assert hoje == 1000 and depois == 500               # os 300 já comprimidos ficam de fora
    assert medida.razao == 2.0


def test_projecao_sem_medida_nao_promete_nada():
    acv = A.Acervo([A.Linha("CT", EXPL, 1, 1000, 500)])
    (_m, hoje, depois), = A.projetar(acv, [A.Medida("1.2.840.10008.1.2.4.80")])
    assert hoje == depois == 1000


def test_tamanho_legivel():
    assert A.tamanho(512) == "512 bytes"
    assert A.tamanho(1536) == "1.5 kB"
    assert A.tamanho(3 * (1 << 30)) == "3.0 GB"
