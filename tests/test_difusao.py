"""0.99.37: difusão em qualquer RM — ADC dos valores de b, DWI sintética, tabela por ROI e os avisos.

O fantoma repete o arranjo medido no acervo dele (cinco aparelhos GE): uma série com b0 e b1000 (ou
b750) por posição, o b no privado (0043,1039) em todas as imagens e o (0018,9087) só nas de b > 0;
e a variante anonimizada, que perdeu o (0043,1039).
"""
import numpy as np
import pydicom
import pytest
from pydicom.dataset import FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from PySide6.QtWidgets import QApplication

from ipe.imaging import difusao as DF

TECIDO, LIQUIDO = 800.0, 3000.0          # ×10⁻⁶ mm²/s


def _fantoma(pasta, bs=(0, 1000), cortes=4, ge=True, so_9087_nos_b=True, descricao="Ax DWI",
             estudo=None, s0=1000.0, ruido=0.0, extra_series=()):
    """Escreve a série DWI (e, opcionalmente, um ADC "do aparelho"). Devolve (study_uid, series_uid)."""
    pasta.mkdir(parents=True, exist_ok=True)
    estudo = estudo or generate_uid()
    serie, frame_ref = generate_uid(), generate_uid()
    rng = np.random.default_rng(0)
    yy, xx = np.mgrid[0:64, 0:64]
    liquido = (xx - 20) ** 2 + (yy - 32) ** 2 < 100           # um "ventrículo" de ADC alto
    fundo = (xx < 4) | (xx > 59)                                # ar: sinal ~0
    adc = np.where(liquido, LIQUIDO, TECIDO)
    n = 0
    for z in range(cortes):
        for b in bs:
            sinal = s0 * np.exp(-adc * 1e-6 * b)
            sinal = np.where(fundo, 2.0, sinal) + (rng.normal(0, ruido, sinal.shape) if ruido else 0)
            n += 1
            ds = pydicom.Dataset()
            meta = FileMetaDataset()
            meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.4"
            meta.MediaStorageSOPInstanceUID = generate_uid()
            meta.TransferSyntaxUID = ExplicitVRLittleEndian
            ds.file_meta = meta
            ds.SOPClassUID, ds.SOPInstanceUID = meta.MediaStorageSOPClassUID, meta.MediaStorageSOPInstanceUID
            ds.PatientName, ds.PatientID, ds.PatientSex = "DIFUSAO^Teste", "DWI1", "F"
            ds.StudyInstanceUID, ds.SeriesInstanceUID, ds.FrameOfReferenceUID = estudo, serie, frame_ref
            ds.StudyDate, ds.StudyDescription, ds.Modality = "20261103", "RM CRANIO", "MR"
            ds.SeriesDescription, ds.SeriesNumber, ds.InstanceNumber = descricao, 5, n
            ds.Manufacturer = "GE MEDICAL SYSTEMS"
            ds.ImageType = ["ORIGINAL", "PRIMARY", "OTHER"]
            ds.ImagePositionPatient = [-100, -100, z * 5.0]
            ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
            ds.PixelSpacing, ds.SliceThickness = [1.0, 1.0], 5.0
            ds.EchoTime, ds.RepetitionTime = 80, 5000
            if ge:
                ds.add_new((0x0043, 0x0010), "LO", "GEMS_PARM_01")
                ds.add_new((0x0043, 0x1039), "IS", [str(int(b)), "8", "0", "0"])
            if b > 0 or not so_9087_nos_b:
                ds.add_new((0x0018, 0x9087), "FD", float(b))
            px = np.clip(np.round(sinal), 0, 32767).astype(np.uint16)
            ds.Rows, ds.Columns = px.shape
            ds.SamplesPerPixel, ds.PhotometricInterpretation = 1, "MONOCHROME2"
            ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation = 16, 16, 15, 0
            ds.PixelData = px.tobytes()
            ds.save_as(pasta / f"dwi_{n:03d}.dcm", enforce_file_format=True)
    return estudo, serie


def _importar(env, pasta):
    from ipe.importer.scanner import Importer
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([pasta])
    return repo


# ------------------------------------------------------------------ o b no arquivo
def test_valor_b_nos_lugares_de_cada_fabricante():
    ds = pydicom.Dataset()
    assert DF.valor_b(ds) is None
    ds.add_new((0x0043, 0x1039), "IS", ["1000001000", "8", "0", "0"])     # GE: b + 10⁹ (algumas versões)
    assert DF.valor_b(ds) == 1000
    ds.add_new((0x0018, 0x9087), "FD", 750.0)                              # o padrão manda
    assert DF.valor_b(ds) == 750
    s = pydicom.Dataset()
    s.SequenceName = "*ep_b1000t"                                         # Siemens antigo
    assert DF.valor_b(s) == 1000
    assert DF.parece_difusao("Ax DWI") and DF.parece_difusao("A DIFUSAO") and DF.parece_difusao("ep2d_diff_TRACEW")
    assert not DF.parece_difusao("ADC (10^-6 mm²/s)") and not DF.parece_difusao("eADC[No-Q]")
    assert not DF.parece_difusao("T2 FSE")
    assert DF.e_mapa_adc("ADC (10^-6 mm²/s)") and DF.e_mapa_adc("x", ["DERIVED", "PRIMARY", "DIFFUSION", "ADC"])


# ------------------------------------------------------------------ o cálculo
def test_adc_de_dois_b_bate_com_o_valor_conhecido(env, tmp_path):
    _st, serie = _fantoma(tmp_path / "a")
    repo = _importar(env, tmp_path / "a")
    s = DF.ler_serie(repo, serie)
    assert s.bs == [0, 1000] and s.n == 4 and not s.deduzido and not s.avisos
    m = DF.calcular(s)
    k = 1
    assert abs(float(np.median(m.adc[k][30:34, 40:44])) - TECIDO) < 2      # tecido
    assert abs(float(np.median(m.adc[k][30:34, 18:22])) - LIQUIDO) < 15    # líquido
    assert (m.adc[k][:, :3] == 0).all()                                     # ar: abaixo do limiar, 0
    # DWI sintética: S0·e^(−ADC·b), igual ao sinal "medido" no mesmo b
    sint = DF.dwi_sintetica(m, 1000)
    real = DF._pixels(m.cortes[k].imagens[1000])
    assert abs(float(np.median(sint[k][30:34, 40:44] - real[30:34, 40:44]))) <= 1


def test_tres_b_regressao_e_r2(env, tmp_path):
    _st, serie = _fantoma(tmp_path / "a", bs=(0, 500, 1000), ruido=0.5)
    repo = _importar(env, tmp_path / "a")
    s = DF.ler_serie(repo, serie)
    assert s.bs == [0, 500, 1000]
    m = DF.calcular(s)
    assert m.r2 is not None and float(np.median(m.r2[0][30:34, 40:44])) > 0.99
    assert abs(float(np.median(m.adc[0][30:34, 40:44])) - TECIDO) < 10
    # escolher só dois b dá o mesmo ADC (com ruído pequeno)
    m2 = DF.calcular(s, [0, 1000])
    assert abs(float(np.median(m2.adc[0][30:34, 40:44])) - TECIDO) < 10
    with pytest.raises(ValueError):
        DF.calcular(s, [1000])


def test_ge_anonimizada_deduz_o_b0_e_sem_b_pede_para_digitar(env, tmp_path):
    _st, serie = _fantoma(tmp_path / "a", ge=False)                 # só o (0018,9087) nas b>0
    repo = _importar(env, tmp_path / "a")
    s = DF.ler_serie(repo, serie)
    assert s.bs == [0, 1000] and s.deduzido and any("deduzido" in a for a in s.avisos)
    assert abs(float(np.median(DF.calcular(s).adc[0][30:34, 40:44])) - TECIDO) < 2
    _st, serie2 = _fantoma(tmp_path / "b", ge=False, so_9087_nos_b=False, bs=(0, 1000))
    # tira o b de tudo: o arquivo não diz
    for f in (tmp_path / "b").glob("*.dcm"):
        ds = pydicom.dcmread(f)
        del ds[0x0018, 0x9087]
        ds.save_as(f)
    repo = _importar(env, tmp_path / "b")
    s = DF.ler_serie(repo, serie2)
    assert s.sem_b and not s.bs and any("digite" in a for a in s.avisos)
    s = DF.ler_serie(repo, serie2, [0, 1000])                       # digitados, na ordem de cada corte
    assert s.bs == [0, 1000]
    assert abs(float(np.median(DF.calcular(s).adc[0][30:34, 40:44])) - TECIDO) < 2


def test_avisos_de_qualidade():
    s = DF.SerieDifusao("1", "x", [DF.Corte((0, 0, 0), {0: "a", 300: "b"}), DF.Corte((0, 0, 5), {0: "a"})],
                        [0, 300], te_tr={0: (80, 5000), 300: (90, 5000)})
    av = " ".join(DF.avisos_de_qualidade(s))
    assert "pouco confiável" in av and "sem todos os b" in av and "TE muda" in av
    s1 = DF.SerieDifusao("1", "x", [DF.Corte((0, 0, 0), {1000: "a"})], [1000])
    assert "não dá para calcular" in " ".join(DF.avisos_de_qualidade(s1))


def test_tabela_da_roi_com_o_adc_do_aparelho(env, tmp_path):
    _st, serie = _fantoma(tmp_path / "a")
    repo = _importar(env, tmp_path / "a")
    m = DF.calcular(DF.ler_serie(repo, serie))
    mascara = np.zeros(m.adc[0].shape, bool)
    mascara[28:36, 38:46] = True
    aparelho = np.full(mascara.shape, 810.0)
    linhas = DF.tabela_da_roi(m, 0, mascara, aparelho)
    nomes = [ln["mapa"] for ln in linhas]
    assert nomes[0].startswith("ADC (Ipê)") and nomes[1].startswith("ADC do aparelho") and "Sinal b0" in nomes
    assert abs(linhas[0]["media"] - TECIDO) < 2 and linhas[1]["media"] == 810.0


# ------------------------------------------------------------------ gravar e a tela
def test_grava_o_adc_como_serie_de_rm_do_exame(env, tmp_path):
    from ipe.imaging import difusao_saida as SAIDA
    paths, db, _repo = env
    st, serie = _fantoma(tmp_path / "a")
    repo = _importar(env, tmp_path / "a")
    m = DF.calcular(DF.ler_serie(repo, serie))
    uid, sops = SAIDA.gravar(db, paths.storage, m, m.adc, "ADC (Ipê) · b0-1000", "adc")
    assert len(sops) == 4
    meta = repo.series_meta(uid)
    assert meta["study_uid"] == st and meta["modality"] == "MR"
    inst = sorted(repo.instances_for_series(uid), key=lambda i: i["instance_number"])
    ds = pydicom.dcmread(inst[1]["path"])
    assert list(ds.ImageType) == ["DERIVED", "PRIMARY", "DIFFUSION", "ADC"]
    assert abs(float(np.median(ds.pixel_array[30:34, 40:44])) - TECIDO) < 2   # o pixel é o ADC
    assert [float(x) for x in ds.ImagePositionPatient] == [-100, -100, 5.0]
    sint, _ = SAIDA.gravar(db, paths.storage, m, DF.dwi_sintetica(m, 1500), "DWI sintética b1500 (Ipê)",
                           "sintetica", 1500)
    ds2 = pydicom.dcmread(repo.instances_for_series(sint)[0]["path"])
    assert "SYNTHETIC" in ds2.ImageType and float(ds2[0x0018, 0x9087].value) == 1500
    assert not DF.parece_difusao(ds2.SeriesDescription) or "sintética" in ds2.SeriesDescription


def test_painel_no_visualizador(env, tmp_path, monkeypatch):
    from ipe.core.config import Settings
    from ipe.imaging.measure import Annotation
    from ipe.ui.main_window import MainWindow
    from ipe.ui.viewer import aplicacoes as AP
    QApplication.instance() or QApplication([])
    paths, db, _repo = env
    st, serie = _fantoma(tmp_path / "a", descricao="A DIFUSAO")
    repo = _importar(env, tmp_path / "a")
    assert "difusao" in AP.APLICACOES
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        w.open_study(st)
        QApplication.processEvents()
        tab = next(iter(w.all_viewer_tabs()))
        assert "difusao" in tab._apps
        d = tab.abrir_difusao()
        assert d.serie_escolhida() == serie and d.serie.bs == [0, 1000] and d.b_adc.isEnabled()
        uid = d.gravar_adc()
        assert uid and any(s.series_uid == uid for s in tab.series)
        assert tab.active.series_uid == uid                          # aberto no quadro ativo
        # ROI no quadro (o ADC gravado): a tabela mede nos mapas
        vp = tab.active
        vp.set_index(1) if hasattr(vp, "set_index") else None
        QApplication.processEvents()
        f = vp.current_frame()
        ann = Annotation("ellipse", (f.sop_uid, 0), [(38.0, 28.0), (46.0, 36.0)], series_uid=uid)
        vp.annotations.append(ann)
        vp.selected = ann
        linhas = d.medir()
        assert linhas and abs(linhas[0]["media"] - TECIDO) < 3
        assert d.texto().startswith("Difusão (b0, b1000): ADC (Ipê)")
        enviado = []
        monkeypatch.setattr(tab, "mandar_texto_ao_laudo", enviado.append)
        d.ao_laudo()
        assert enviado and "×10⁻⁶ mm²/s" in enviado[0]
        assert d.gravar_sintetica()
        d.close()
    finally:
        w._really_quit = True
        w.settings.set("ui.confirmar_sair", False)
        w.close()
