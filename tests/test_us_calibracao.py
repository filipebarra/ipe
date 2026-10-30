"""Calibração do ultrassom: automática pelas regiões do arquivo e manual por imagem."""
import numpy as np
import pytest
from pydicom.dataset import Dataset

from ipe.imaging import measure as M
from ipe.imaging import series as SER
from ipe.imaging import us_regioes as US


def _regiao(x0, y0, x1, y1, dx=0.02, dy=0.02, ux=3, uy=3):
    r = Dataset()
    r.RegionLocationMinX0, r.RegionLocationMinY0 = x0, y0
    r.RegionLocationMaxX1, r.RegionLocationMaxY1 = x1, y1
    r.PhysicalDeltaX, r.PhysicalDeltaY = dx, dy
    r.PhysicalUnitsXDirection, r.PhysicalUnitsYDirection = ux, uy
    r.RegionSpatialFormat, r.RegionDataType = 1, 1
    return r


def _ds(regioes, modality="US", **kw):
    ds = Dataset()
    ds.Modality = modality
    if regioes is not None:
        ds.SequenceOfUltrasoundRegions = regioes
    for k, v in kw.items():
        setattr(ds, k, v)
    return ds


def test_centimetro_virou_milimetro():
    regs = US.regioes(_ds([_regiao(0, 0, 100, 100, 0.00715, 0.00715)]))
    assert len(regs) == 1
    assert regs[0].mm_coluna == pytest.approx(0.0715)
    assert regs[0].espacamento == pytest.approx((0.0715, 0.0715))


def test_janela_do_doppler_nao_e_regua():
    """Eixo em segundos e cm/s não mede distância: a região tem de ser recusada."""
    regs = US.regioes(_ds([_regiao(0, 0, 100, 100), _regiao(0, 120, 100, 140, 0.004, 0.5, 4, 7)]))
    assert len(regs) == 1 and regs[0].y1 == 100
    assert US.regioes(_ds([_regiao(0, 0, 10, 10, ux=3, uy=0)])) == []
    assert US.regioes(_ds([_regiao(0, 0, 10, 10, dx=0, dy=0.02)])) == []
    assert US.regioes(_ds([_regiao(10, 10, 10, 20)])) == []     # caixa vazia
    assert US.regioes(_ds(None)) == []


def test_painel_duplo_cada_lado_com_sua_regiao():
    a, b = _regiao(0, 0, 500, 400, 0.01, 0.01), _regiao(501, 0, 1000, 400, 0.02, 0.02)
    regs = US.regioes(_ds([a, b]))
    assert US.espacamento(regs) == pytest.approx((0.1, 0.1))     # a maior área ganha o empate
    assert US.regiao_do_ponto(regs, 600, 200).mm_coluna == pytest.approx(0.2)
    assert US.regiao_do_ponto(regs, 600, 900) is None
    # medida dentro de um painel: vale; de um painel para o outro: não é distância nenhuma
    assert US.espacamento_dos_pontos(regs, [(10, 10), (400, 300)]) == pytest.approx((0.1, 0.1))
    assert US.espacamento_dos_pontos(regs, [(10, 10), (600, 300)]) is None
    assert US.espacamento_dos_pontos(regs, [(10, 10), (10, 900)]) is None
    assert US.espacamento_dos_pontos([], [(1, 1)]) is None


def test_regiao_vence_o_pixelspacing_no_ultrassom():
    """No US a escala boa é a da região: é ela que o aparelho atualiza a cada imagem."""
    sp, fonte, regs = SER._escala(_ds([_regiao(0, 0, 100, 100)], PixelSpacing=[1.0, 1.0]))
    assert fonte == "RegiaoUS" and sp == pytest.approx((0.2, 0.2)) and len(regs) == 1
    # fora do ultrassom a região só entra se não houver espaçamento no arquivo
    sp, fonte, _ = SER._escala(_ds([_regiao(0, 0, 100, 100)], modality="MR", PixelSpacing=[0.5, 0.5]))
    assert fonte == "PixelSpacing" and sp == pytest.approx((0.5, 0.5))
    # captura de tela, sem região e sem espaçamento: fica sem escala (medida em pixels)
    sp, fonte, regs = SER._escala(_ds(None, PixelSpacing=None))
    assert sp is None and fonte == "" and regs == ()


def test_fantoma_de_us_tem_as_duas_regioes(tmp_path):
    """O fantoma precisa ter a anatomia do problema: imagem 2D calibrada + espectro para recusar."""
    import pydicom
    from ipe.core.sample_data import make_sample_data
    files = make_sample_data(tmp_path)
    us = [f for f in files if "US" in str(f) and "cine" not in str(f)]
    assert us
    ds = pydicom.dcmread(str(us[0]), force=True)
    assert len(ds.SequenceOfUltrasoundRegions) == 2
    img = SER.read_frame(SER.Frame(str(us[0]), 0, ds.SOPInstanceUID, 1))
    assert img.spacing_source == "RegiaoUS"
    assert img.pixel_spacing == pytest.approx((0.2, 0.2))
    assert len(img.us_regioes) == 1


# ----------------------------------------------------------------- calibração manual
class _Falso:
    """Só o que a parte de medidas do viewport usa para escolher a escala."""
    from ipe.ui.viewer.annotate import AnnotationMixin as _Mix
    _calibracoes = _Mix._calibracoes
    calibracao_da_imagem = _Mix.calibracao_da_imagem
    calibracao_da_serie = _Mix.calibracao_da_serie
    measure_spacing = _Mix.measure_spacing
    escala_texto = _Mix.escala_texto
    is_calibrated = _Mix.is_calibrated

    def __init__(self, img, chave=("sop1", 0), series="s1"):
        self._img = img
        self.annotations = []
        self.series_uid = series
        self._chave = chave

    def frame_key(self):
        return self._chave

    def current_frame(self):
        return None


def _img(spacing, regs=()):
    return SER.FrameImage(np.zeros((10, 10), np.float32), False, None, spacing, "", "", {}, tuple(regs))


def _cal(mm, chave, escopo, series="s1"):
    a = M.Annotation("calibration", chave, [(0, 0), (0, 10)], text=str(mm), series_uid=series,
                     meta={"escopo": escopo})
    a.done = True
    return a


def test_calibracao_da_imagem_nao_vaza_para_as_outras():
    regs = US.regioes(_ds([_regiao(0, 0, 100, 100)]))
    vp = _Falso(_img((0.2, 0.2), regs))
    assert vp.measure_spacing() == pytest.approx((0.2, 0.2))
    assert vp.escala_texto() == "Escala: região do ultrassom"
    vp.annotations.append(_cal(20, ("sop1", 0), "imagem"))     # 20 mm em 10 pixels = 2 mm/pixel
    assert vp.measure_spacing() == pytest.approx((2.0, 2.0))
    assert vp.is_calibrated() and vp.escala_texto() == "Escala: calibrada nesta imagem"
    vp._chave = ("sop2", 0)                                    # outra imagem da mesma série
    assert vp.measure_spacing() == pytest.approx((0.2, 0.2))
    assert not vp.is_calibrated()


def test_calibracao_da_serie_vale_nas_outras_imagens():
    vp = _Falso(_img(None))
    assert vp.measure_spacing() is None
    assert vp.escala_texto() == "Sem escala — medidas em pixels"
    vp.annotations.append(_cal(50, ("sopX", 0), "serie"))       # 50 mm em 10 pixels
    vp._chave = ("sop9", 0)
    assert vp.measure_spacing() == pytest.approx((5.0, 5.0))
    assert vp.escala_texto() == "Escala: calibrada na série"


def test_medida_pega_a_regiao_onde_ela_esta():
    a, b = _regiao(0, 0, 500, 400, 0.01, 0.01), _regiao(501, 0, 1000, 400, 0.02, 0.02)
    regs = US.regioes(_ds([a, b]))
    vp = _Falso(_img((0.1, 0.1), regs))
    ann = M.Annotation("line", ("sop1", 0), [(600, 10), (600, 110)])
    assert vp.measure_spacing(ann) == pytest.approx((0.2, 0.2))
    atravessa = M.Annotation("line", ("sop1", 0), [(10, 10), (600, 10)])
    assert vp.measure_spacing(atravessa) is None
    # calibração manual na imagem manda em todas as regiões
    vp.annotations.append(_cal(20, ("sop1", 0), "imagem"))
    assert vp.measure_spacing(atravessa) == pytest.approx((2.0, 2.0))


def test_rotulo_diz_o_alcance_da_calibracao():
    so_aqui = _cal(20, ("sop1", 0), "imagem")
    assert M.labels(so_aqui, None, (1, 1)) == ["Calibração: 20 mm (só esta imagem)"]
    serie = _cal(20, ("sop1", 0), "serie")
    assert M.labels(serie, None, (1, 1)) == ["Calibração: 20 mm"]
