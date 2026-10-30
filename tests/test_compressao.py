"""Compressão sem perda do que está guardado. É a função que reescreve arquivo de paciente:
cada teste aqui existe para garantir que ela só troca o que conferiu."""

import os
from datetime import datetime, timedelta

import numpy as np
import pydicom
import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from ipe.core import compress as K


def _grava(pasta, nome="a.dcm", linhas=128, colunas=128, semente=0, modalidade="CT"):
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.SOPClassUID = ds.file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
    ds.PatientName, ds.PatientID = "COMPRIME^Teste", "CMP001"
    ds.StudyInstanceUID = "1.2.3.4.5.6.7"
    ds.SeriesInstanceUID = generate_uid()
    ds.StudyDate, ds.SeriesNumber, ds.InstanceNumber = "20260101", 1, 1
    ds.Modality = modalidade
    ds.Rows, ds.Columns = linhas, colunas
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit, ds.PixelRepresentation, ds.SamplesPerPixel = 15, 0, 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    y, x = np.mgrid[0:linhas, 0:colunas]
    rng = np.random.default_rng(semente)
    img = 400 + 200 * np.sin(x / 7.0) + 150 * np.cos(y / 9.0) + rng.integers(0, 40, (linhas, colunas))
    ds.PixelData = img.astype(np.uint16).tobytes()
    caminho = pasta / nome
    ds.save_as(str(caminho), enforce_file_format=True)
    return caminho


# ------------------------------------------------------------------ um arquivo
def test_comprime_e_os_pixels_voltam_identicos(tmp_path):
    caminho = _grava(tmp_path)
    antes = pydicom.dcmread(str(caminho)).pixel_array.copy()
    tamanho_antes = caminho.stat().st_size

    r = K.compress_file(caminho)

    assert r.ok and r.depois < r.antes == tamanho_antes
    depois = pydicom.dcmread(str(caminho))
    assert str(depois.file_meta.TransferSyntaxUID) == K.JPEGLS
    assert np.array_equal(depois.pixel_array, antes)      # sem perda é sem perda


def test_o_sop_instance_uid_nao_muda(tmp_path):
    """Trocar só a sintaxe de transferência não cria objeto novo — com perda criaria."""
    caminho = _grava(tmp_path)
    uid = str(pydicom.dcmread(str(caminho)).SOPInstanceUID)
    K.compress_file(caminho)
    assert str(pydicom.dcmread(str(caminho)).SOPInstanceUID) == uid


def test_nao_recomprime_o_que_ja_esta_comprimido(tmp_path):
    caminho = _grava(tmp_path)
    assert K.compress_file(caminho).ok
    depois = caminho.stat().st_size
    r = K.compress_file(caminho)
    assert r.estado == K.PULOU_COMPRIMIDO and caminho.stat().st_size == depois


def test_arquivo_que_sumiu_nao_levanta_excecao(tmp_path):
    assert K.compress_file(tmp_path / "nao_existe.dcm").estado == K.PULOU_SUMIU


def test_arquivo_ilegivel_nao_levanta_excecao(tmp_path):
    ruim = tmp_path / "lixo.dcm"
    ruim.write_bytes(b"isto nao e DICOM" * 100)
    assert K.compress_file(ruim).estado == K.PULOU_SUMIU
    assert ruim.exists()                                   # e continua lá, intacto


def test_arquivo_sem_pixel_e_deixado_em_paz(tmp_path):
    ds = pydicom.dcmread(str(_grava(tmp_path)))
    del ds.PixelData
    ds.save_as(str(tmp_path / "sem.dcm"), enforce_file_format=True)
    assert K.compress_file(tmp_path / "sem.dcm").estado == K.PULOU_SEM_PIXEL


def test_arquivo_pequeno_e_pulado(tmp_path):
    caminho = _grava(tmp_path, linhas=16, colunas=16)
    assert K.compress_file(caminho, minimo_bytes=1 << 20).estado == K.PULOU_PEQUENO


def test_se_a_conferencia_falhar_o_original_fica_intacto(tmp_path, monkeypatch):
    """A garantia que sustenta 'substituir na hora': falhou a conferência, não troca nada."""
    caminho = _grava(tmp_path)
    original = caminho.read_bytes()

    import numpy
    monkeypatch.setattr(numpy, "array_equal", lambda *a, **k: False)
    r = K.compress_file(caminho)

    assert r.estado == K.FALHOU_CONFERIR
    assert caminho.read_bytes() == original                # byte a byte
    assert not list(tmp_path.glob("*.comprimindo"))        # nem lixo temporário


def test_codificador_que_recusa_nao_estraga_o_arquivo(tmp_path):
    caminho = _grava(tmp_path)
    original = caminho.read_bytes()
    r = K.compress_file(caminho, sintaxe="1.2.840.10008.1.2.4.999")
    assert r.estado == K.FALHOU_COMPRIMIR
    assert caminho.read_bytes() == original


def test_nao_troca_quando_o_comprimido_fica_maior(tmp_path):
    """Ruído puro cresce ao ser comprimido — e o programa prefere o original."""
    caminho = _grava(tmp_path, nome="ruido.dcm")
    ds = pydicom.dcmread(str(caminho))
    rng = np.random.default_rng(1)
    ds.PixelData = rng.integers(0, 65535, (128, 128)).astype(np.uint16).tobytes()
    ds.save_as(str(caminho), enforce_file_format=True)
    original = caminho.read_bytes()

    r = K.compress_file(caminho)

    assert r.estado == K.PULOU_PEQUENO and "maior" in r.detalhe
    assert caminho.read_bytes() == original
    assert not list(tmp_path.glob("*.comprimindo"))


# ------------------------------------------------------------------ política
def test_politica_le_e_grava_as_preferencias(env):
    from ipe.core.config import Settings
    paths, _db, _repo = env
    s = Settings(paths.settings_file)
    assert K.Politica.from_settings(s).ligada is False        # desligada até mandarem ligar
    K.Politica(ligada=True, dias=5, sintaxe=K.J2K).save(s)
    p = K.Politica.from_settings(Settings(paths.settings_file))
    assert p.ligada and p.dias == 5 and p.sintaxe == K.J2K


def test_sintaxe_estranha_na_preferencia_vira_a_padrao(env):
    from ipe.core.config import Settings
    paths, _db, _repo = env
    s = Settings(paths.settings_file)
    s.set("compress.syntax", "1.2.840.10008.1.2.4.50")        # com perda: não entra aqui
    assert K.Politica.from_settings(s).sintaxe == K.JPEGLS


def test_o_prazo_conta_da_entrada_no_sistema():
    p = K.Politica(dias=5)
    agora = datetime(2026, 9, 22, 12, 0)
    assert p.limite(agora) == datetime(2026, 9, 17, 12, 0)


# ------------------------------------------------------------------ o lote
def _importa(env, tmp_path, n=3, dias_atras=10):
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    pasta = tmp_path / "dcm"
    pasta.mkdir(exist_ok=True)
    for i in range(n):
        _grava(pasta, f"{i}.dcm", semente=i)
    Importer(db, paths.storage).import_paths([pasta])
    from ipe.db.models import Study
    with db.session() as s:
        for st in s.query(Study).all():
            st.date_added = datetime.now() - timedelta(days=dias_atras)
    return repo


def test_lote_comprime_e_o_banco_acompanha(env, tmp_path):
    repo = _importa(env, tmp_path)
    pol = K.Politica(dias=5, minimo_bytes=0)
    b = K.run(repo, pol)
    assert b.feitos == 3 and b.economia > 0
    from ipe.core import acervo as A
    acv = A.levantar(repo)
    assert [l.sintaxe_uid for l in acv.linhas] == [K.JPEGLS]   # o banco sabe do novo formato
    assert acv.bytes == b.depois                               # e do novo tamanho


def test_exame_novo_demais_nao_entra(env, tmp_path):
    repo = _importa(env, tmp_path, dias_atras=1)
    assert K.run(repo, K.Politica(dias=5, minimo_bytes=0)).arquivos == 0


def test_exame_protegido_fica_de_fora(env, tmp_path):
    repo = _importa(env, tmp_path)
    uid = repo.search_studies()[0].study_uid
    repo.set_locked(uid, True)
    assert K.run(repo, K.Politica(dias=5, minimo_bytes=0, pular_protegidos=True)).arquivos == 0
    assert K.run(repo, K.Politica(dias=5, minimo_bytes=0, pular_protegidos=False)).feitos == 3


def test_exame_pedido_para_ficar_de_fora_nao_e_tocado(env, tmp_path):
    repo = _importa(env, tmp_path)
    uid = repo.search_studies()[0].study_uid
    assert K.run(repo, K.Politica(dias=5, minimo_bytes=0), pular_exames=[uid]).arquivos == 0


def test_parar_no_meio_nao_deixa_arquivo_pela_metade(env, tmp_path):
    import threading
    repo = _importa(env, tmp_path)
    stop = threading.Event()

    def marca(i, _n):
        if i >= 1:
            stop.set()
    b = K.run(repo, K.Politica(dias=5, minimo_bytes=0), stop=stop, progresso=marca)
    assert 0 < b.feitos < 3                                     # parou antes do fim
    assert not list(tmp_path.rglob("*.comprimindo"))            # nada pela metade
    from ipe.core import acervo as A
    formatos = {l.sintaxe_uid for l in A.levantar(repo).linhas}
    assert formatos == {K.JPEGLS, "1.2.840.10008.1.2.1"}        # os dois convivem sem problema


def test_limite_por_rodada(env, tmp_path):
    repo = _importa(env, tmp_path)
    assert K.run(repo, K.Politica(dias=5, minimo_bytes=0, por_rodada=2)).arquivos == 2


def test_resumo_em_uma_frase(env, tmp_path):
    repo = _importa(env, tmp_path)
    assert "Nada a comprimir" in K.resumo(K.Balanco())
    assert "comprimidos" in K.resumo(K.run(repo, K.Politica(dias=5, minimo_bytes=0)))


# ------------------------------------------------------------------ tela e passagem automática
def _janela(env):
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    paths, _db, _repo = env
    QApplication.instance() or QApplication([])
    return MainWindow(paths, Settings(paths.settings_file))


def test_exame_aberto_fica_de_fora(env, tmp_path):
    janela = _janela(env)
    _importa(env, tmp_path)
    janela.browser.refresh()
    uid = janela.repo.search_studies()[0].study_uid
    janela.open_study(uid)
    assert uid in janela.studies_in_use()
    b = K.run(janela.repo, K.Politica(dias=5, minimo_bytes=0),
              pular_exames=janela.studies_in_use())
    assert b.arquivos == 0


def test_passagem_automatica_so_roda_se_estiver_ligada(env, tmp_path, monkeypatch):
    janela = _janela(env)
    _importa(env, tmp_path)
    chamou = []
    monkeypatch.setattr(janela.net, "run_async", lambda fn, done: chamou.append(fn))
    janela._comprimindo = False
    janela.compress_pass()
    assert chamou == []                                  # desligada por padrão
    K.Politica(ligada=True, dias=5, minimo_bytes=0).save(janela.settings)
    janela.compress_pass()
    assert len(chamou) == 1


def test_a_tela_mostra_a_fila_e_o_formato(env, tmp_path):
    from ipe.ui.acervo_dialog import AcervoDialog
    janela = _janela(env)
    repo = _importa(env, tmp_path)
    K.Politica(ligada=True, dias=5, minimo_bytes=0).save(janela.settings)
    dlg = AcervoDialog(repo, janela.settings, [], janela)
    assert "3 arquivo(s)" in dlg.l_fila.text()
    assert dlg.b_comprimir.isEnabled()
    assert dlg.politica().sintaxe == K.JPEGLS
    dlg.s_dias.setValue(3650)                            # prazo enorme: fila vazia
    assert "Nenhum arquivo" in dlg.l_fila.text()
    assert not dlg.b_comprimir.isEnabled()
