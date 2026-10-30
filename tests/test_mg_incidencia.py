"""O quadro mostra a incidência que o protocolo pediu, não uma variante dela.

O relato: *"quando eu configurar uma incidência, mostrar a incidência configurada, por exemplo MLO
direita e não SMLO direita. você está mostrando as incidências complementares primeiro"*.

Medido no acervo dele: `CESM_PROC_RMLO` e `CESM_PROC_RSMLO` têm **o mesmo** `ViewPosition` ("MLO")
e o mesmo `ViewCodeSequence` ("medio-lateral oblique"). O arquivo não distingue as duas; só o nome
da série distingue. Como a escolha era "a mais recente", a complementar ganhava.
"""
import pytest

from ipe.imaging import mammo as M


def _img(serie, view, side, *, hora="100000", n=1, exata=None, rec=False, tomo=False, rotulo=""):
    exata = M.incidencia_exata(rotulo, [serie], view) if exata is None else exata
    return M.MgImage("st", f"se-{serie}-{n}", f"sop-{serie}-{n}", 0, "x.dcm", side, view,
                     False, n, hora, 1, tomo, "rec" if rec else "", exata, serie, rotulo)


def test_o_nome_distingue_a_incidencia_da_variante():
    assert M.nomeia_a_incidencia(["CESM_PROC_RMLO"], "MLO")
    assert M.nomeia_a_incidencia(["CESM_PROC_LMLO"], "MLO")
    assert M.nomeia_a_incidencia(["ROUTINE3D_VOL_RCC"], "CC")
    assert M.nomeia_a_incidencia(["MLO DIREITA"], "MLO")
    assert not M.nomeia_a_incidencia(["CESM_PROC_RSMLO"], "MLO")
    assert not M.nomeia_a_incidencia(["CESM_PROC_LSCC"], "CC")
    # nome que não fala de incidência não desempata nada: não há como afirmar que é variante
    assert M.nomeia_a_incidencia(["2D_PROC"], "CC")
    assert M.nomeia_a_incidencia(["V-Preview"], "MLO")
    assert M.nomeia_a_incidencia([""], "CC") and M.nomeia_a_incidencia(["qualquer"], "ANY")
    # a sigla de outra incidência não torna a imagem variante desta
    assert M.nomeia_a_incidencia(["CESM_PROC_RCC"], "MLO")


def test_a_incidencia_pedida_ganha_da_complementar():
    """Mesmo com a complementar sendo a mais recente, quem vai para o quadro é a pedida."""
    pedida = _img("CESM_PROC_RMLO", "MLO", "R", hora="100500", n=1)
    variante = _img("CESM_PROC_RSMLO", "MLO", "R", hora="101500", n=2)   # adquirida depois
    assert pedida.exata and not variante.exata
    cel = M.Cell("MLO", "R", 0)
    assert M.pick_image([variante, pedida], cel).serie == "CESM_PROC_RMLO"
    assert M.pick_image([pedida, variante], cel).serie == "CESM_PROC_RMLO"


def test_entre_iguais_continua_valendo_a_mais_recente():
    antiga = _img("CESM_PROC_RMLO", "MLO", "R", hora="100000", n=1)
    repetida = _img("CESM_PROC_RMLO", "MLO", "R", hora="103000", n=2)
    im = M.pick_image([antiga, repetida], M.Cell("MLO", "R", 0))
    assert im.time == "103000", "a repetição mais nova deixou de ganhar"


def test_a_complementar_ainda_e_alcancavel():
    """Um segundo quadro com a mesma incidência pega a variante — ela não foi escondida."""
    pedida = _img("CESM_PROC_RMLO", "MLO", "R", hora="100500", n=1)
    variante = _img("CESM_PROC_RSMLO", "MLO", "R", hora="101500", n=2)
    cel = M.Cell("MLO", "R", 0)
    usados = set()
    primeira = M.pick_image([pedida, variante], cel, usados)
    usados.add(primeira.sop_uid)
    segunda = M.pick_image([pedida, variante], cel, usados)
    assert primeira.serie == "CESM_PROC_RMLO" and segunda.serie == "CESM_PROC_RSMLO"


def test_so_a_variante_ainda_preenche_o_quadro():
    """Se o exame não tem a incidência pedida, a variante é melhor que quadro vazio — e o rótulo
    do quadro diz de que série ela veio."""
    variante = _img("CESM_PROC_RSMLO", "MLO", "R")
    im = M.pick_image([variante], M.Cell("MLO", "R", 0))
    assert im is not None and not im.exata and im.serie == "CESM_PROC_RSMLO"


def test_rotulo_do_quadro_avisa_quando_e_variante(env, tmp_path, monkeypatch):
    from ipe.ui.viewer.mammo_view import MgSession
    pedidos = []

    class _Aba:
        study_uid = "st"

        def load_frames_into(self, vp, uid, frames, nome, *a, **k):
            pedidos.append(nome)

    s = MgSession.__new__(MgSession)
    s.tab = _Aba()
    s._frames = {}
    monkeypatch.setattr(MgSession, "cell_frames", lambda self, im, cell: ([object()], 0, None))
    for serie, espera_nome in (("CESM_PROC_RMLO", False), ("CESM_PROC_RSMLO", True)):
        im = _img(serie, "MLO", "R")
        s._load(_Vp(), im, M.Cell("MLO", "R", 0))
    assert pedidos[0].startswith("MLO D") and "·" not in pedidos[0]
    assert "CESM_PROC_RSMLO" in pedidos[1], "o quadro não disse que mostrou a complementar"


class _Vp:
    """Viewport de mentira: só o que `_load` escreve nele."""
    implant_mask = False
    mg_spec = None
    tomo_range = None
    mg_tomo = False
    cine_bounce = False
    _img = None

    def set_tomo_slab(self, *a):
        pass

    def set_implant_mask(self, *a):
        pass


# --------------------------------------------- o rótulo do aparelho (GE 0045,101B), 0.61.2
def _ds(valor, vr="LO"):
    from pydicom.dataelem import DataElement
    from pydicom.dataset import Dataset
    ds = Dataset()
    if valor is not None:
        ds[M.TAG_INCIDENCIA_GE] = DataElement(M.TAG_INCIDENCIA_GE, vr, valor)
    return ds


def test_le_o_rotulo_do_aparelho():
    assert M.rotulo_da_incidencia(_ds("RMLO")) == "RMLO"
    assert M.rotulo_da_incidencia(_ds(" lmlo ")) == "LMLO"
    assert M.rotulo_da_incidencia(_ds("R-CC")) == "RCC"
    assert M.rotulo_da_incidencia(_ds(None)) == ""
    assert M.rotulo_da_incidencia(_ds(b"\x01\x02", "OB")) == "", "valor binário não é rótulo"
    assert M.rotulo_da_incidencia(_ds("")) == ""


def test_o_rotulo_do_aparelho_decide_a_incidencia():
    """Rótulos medidos no acervo dele: RCC, LMLO, RSMLO, LSCC, RMSCC, LMSCC, RCCS, LCCID."""
    for rot, view in (("RCC", "CC"), ("LCC", "CC"), ("RMLO", "MLO"), ("LMLO", "MLO")):
        assert M.incidencia_exata(rot, ["qualquer"], view), rot
    for rot, view in (("RSMLO", "MLO"), ("LSMLO", "MLO"), ("RSCC", "CC"), ("LSCC", "CC"),
                      ("RMSCC", "CC"), ("LMSCC", "CC"), ("RCCS", "CC"), ("LCCID", "CC")):
        assert not M.incidencia_exata(rot, ["qualquer"], view), rot
    # o rótulo manda sobre o nome da série, nos dois sentidos
    assert M.incidencia_exata("RMLO", ["CESM_PROC_RSMLO"], "MLO")
    assert not M.incidencia_exata("RSMLO", ["CESM_PROC_RMLO"], "MLO")
    # sem rótulo, vale o nome da série
    assert M.incidencia_exata("", ["CESM_PROC_RMLO"], "MLO")
    assert not M.incidencia_exata("", ["CESM_PROC_RSMLO"], "MLO")
    assert M.incidencia_exata("", ["2D_PROC"], "CC") and M.incidencia_exata("RSMLO", [], "ANY")


def test_a_magnificada_de_nome_generico_perde_da_incidencia():
    """Caso real do acervo: uma série chamada 2D_PROC cujo rótulo é RMSCC (magnificada). Pelo
    nome da série ela passava por CC simples e ganhava por ser mais recente."""
    simples = _img("CESM_PROC_RCC", "CC", "R", hora="100000", n=1, rotulo="RCC")
    magnificada = _img("2D_PROC", "CC", "R", hora="104000", n=2, rotulo="RMSCC")
    assert simples.exata and not magnificada.exata
    im = M.pick_image([magnificada, simples], M.Cell("CC", "R", 0))
    assert im.rotulo == "RCC"


def test_de_ponta_a_ponta_com_arquivo_de_verdade(env, tmp_path):
    """Lê a tag do arquivo pelo caminho de sempre: fantoma com RMLO **e** RSMLO na mesma mama."""
    import numpy as np
    from pydicom.uid import DigitalMammographyXRayImageStorageForPresentation as MG_SOP
    from pydicom.uid import generate_uid
    from ipe.core.sample_data import _base, _elem, _mono, _save
    from ipe.importer.scanner import Importer

    paths, db, repo = env
    pat = {"name": "INCID^Teste", "id": "INC1", "birth": "19700101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20260101", "accession": "INC001",
             "description": "MAMOGRAFIA", "for": generate_uid()}
    d = tmp_path / "mg"
    d.mkdir()
    # a complementar é adquirida **depois** da MLO: antes, era ela que ia para o quadro
    for k, (rotulo, hora) in enumerate((("RMLO", "100500"), ("RSMLO", "101500")), 1):
        series = {"uid": generate_uid(), "number": 10 + k, "description": "MAMOGRAFIA DIGITAL"}
        ds = _base(MG_SOP, pat, study, series, "MG")
        ds.InstanceNumber = k
        ds.ImageLaterality = "R"
        ds.ViewPosition = "MLO"                      # igual nas duas: o arquivo não distingue
        ds.AcquisitionTime = hora
        ds.ImagerPixelSpacing = [0.1, 0.1]
        ds.PresentationIntentType = "FOR PRESENTATION"
        _elem(ds, (0x0045, 0x101B), "LO", rotulo)
        _mono(ds, np.full((256, 200), 1500.0), signed=False)
        _save(ds, d / f"MG_{rotulo}")
    Importer(db, paths.storage).import_paths([d])
    uid = repo.find_study_uids(accession="INC001")[0]
    imgs = M.read_images(repo, uid)
    assert {i.rotulo for i in imgs} == {"RMLO", "RSMLO"}
    assert [i.exata for i in sorted(imgs, key=lambda i: i.rotulo)] == [True, False]
    escolhida = M.pick_image(imgs, M.Cell("MLO", "R", 0))
    assert escolhida.rotulo == "RMLO", "a complementar voltou a ganhar"


def test_o_fantoma_tem_o_rotulo_do_aparelho(tmp_path):
    """Fantoma sem a tag não cobre o caminho que lê a tag."""
    import pydicom
    from ipe.core.sample_data import make_sample_data
    files = make_sample_data(tmp_path)
    rotulos = set()
    for f in files:
        if "MG" not in str(f):
            continue
        ds = pydicom.dcmread(str(f), stop_before_pixels=True, force=True)
        rotulos.add(M.rotulo_da_incidencia(ds))
    assert rotulos == {"RCC", "LCC", "RMLO", "LMLO"}, rotulos
