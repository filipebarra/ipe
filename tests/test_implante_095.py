"""0.95: implante na mamografia — busca pela borda e forma, tags do aparelho e "corrigir".

Pedido dele: "pesquise por melhorias na subtração do implante nas mamografias. O que temos não está
legal." Medido no acervo dele (28 imagens 2D, 5 exames, 2 com prótese): a busca nova achou as 7
próteses visíveis e nenhuma nas incidências com o implante deslocado; as tags do aparelho
(BreastImplantPresent, rótulo 0045,101B) tiram os falsos positivos das mamas sem prótese.
"""
import numpy as np

from ipe.imaging import mammo as MG
from tests.test_mammo import _mama_com_implante


def test_tags_decidem_se_procura():
    assert MG.implante_esperado({}) == ""                                    # aparelho que não escreve nada
    assert MG.implante_esperado({"BreastImplantPresent": "YES", "rotulo": "LMLO"}) == ""
    assert "não há implante" in MG.implante_esperado({"BreastImplantPresent": "NO"})
    assert "deslocado" in MG.implante_esperado({"BreastImplantPresent": "YES", "rotulo": "RCCID"})
    assert "deslocado" in MG.implante_esperado({"modificadores": ["Implant Displaced"]})
    assert "localizada" in MG.implante_esperado({"rotulo": "RSCC"})
    assert "localizada" in MG.implante_esperado({"rotulo": "LMSCC"})
    assert MG.implante_esperado({"rotulo": "RXCCL"}) == ""


def test_acha_a_protese_e_nao_inventa_sem_ela():
    px, corpo, prot = _mama_com_implante()
    m = MG.implant_mask(px)
    assert m is not None
    acerto = (m & prot).sum() / prot.sum()
    sobra = (m & ~prot).sum() / m.sum()
    assert acerto > 0.9 and sobra < 0.1
    for kw in ({"implante": False}, {"implante": False, "densa": True}):
        sem, _c, _p = _mama_com_implante(**kw)
        assert MG.implant_mask(sem) is None, kw


def test_corrigir_desce_o_silicone_e_guarda_o_detalhe():
    px, corpo, prot = _mama_com_implante()
    m = MG.implant_mask(px)
    out = MG.corrige_implante(px, m)
    fora = corpo & ~MG._dilate(m, 6)
    assert np.allclose(out[fora], px[fora], atol=1e-3)                     # o tecido fora não muda
    miolo = MG._erode(m, 15)
    tecido = float(np.median(px[corpo & ~MG._dilate(m, 15)]))
    assert abs(float(np.median(out[miolo])) - tecido) < 0.5 * abs(float(np.median(px[miolo])) - tecido)
    assert float(out[miolo].std()) > 0.8 * float(px[miolo].std())          # o detalhe continua
    # MONOCHROME1: a mesma conta com os valores invertidos
    p1, _c, _p = _mama_com_implante(mono1=True)
    m1 = MG.implant_mask(p1, monochrome1=True)
    o1 = MG.corrige_implante(p1, m1, monochrome1=True)
    assert float(np.median(o1[MG._erode(m1, 15)])) < float(np.median(p1[MG._erode(m1, 15)])) + 1e-3 or \
        float(np.median(-o1[MG._erode(m1, 15)])) < float(np.median(-p1[MG._erode(m1, 15)]))


def test_tag_no_impede_a_busca_no_quadro(env, tmp_path):
    from pydicom.uid import generate_uid
    from PySide6.QtWidgets import QApplication

    from ipe.core.config import Settings
    from ipe.core.sample_data import _base, _mono, _save
    from ipe.importer.scanner import Importer
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    pat = {"name": "IMPLANTE^Tag", "id": "IMP2", "birth": "19750101", "sex": "F"}
    study = {"uid": generate_uid(), "date": "20261023", "accession": "IMP002",
             "description": "MAMOGRAFIA", "for": generate_uid()}
    series = {"uid": generate_uid(), "number": 1, "description": "MG"}
    px, _c, _p = _mama_com_implante()
    for k, (lat, tag) in enumerate((("R", "NO"), ("L", "YES")), start=1):
        ds = _base("1.2.840.10008.5.1.4.1.1.1.2", pat, study, series, "MG")
        ds.InstanceNumber, ds.ImageLaterality, ds.ViewPosition = k, lat, "CC"
        ds.BreastImplantPresent = tag
        ds.ImagerPixelSpacing = [0.1, 0.1]
        _mono(ds, (px if lat == "R" else px[:, ::-1].copy()).astype(np.uint16), signed=False)
        _save(ds, tmp_path / "imp")
    Importer(db, paths.storage).import_paths([tmp_path / "imp"])
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    w.resize(1200, 800)
    w.show()
    w.open_study(study["uid"])
    tab = w.tabs.currentWidget()
    app.processEvents()
    msgs = []
    tab.status_message.connect(msgs.append)
    try:
        tab.mg_set_implant(True)
        app.processEvents()
        com = [v for v in tab.viewports if v.frames and v.implant_found]
        sem = [v for v in tab.viewports if v.frames and not v.implant_found]
        assert len(com) == 1 and len(sem) == 1 and "não há implante" in sem[0].implant_motivo
        assert any("não procurei" in m for m in msgs)
    finally:
        w.close()
