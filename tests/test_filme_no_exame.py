"""Filme gravado dentro do exame, no formato da estação AW da GE: SR + imagens soltas + folhas.

A referência é o exame de RM de mama que ele mandou (10/10/2026): série 25749 com o SR
"Electronic Film Presentation" e as 8 imagens soltas; série 25750 com as 2 folhas prontas;
instâncias intercaladas (imagens 1–4, folha 5, imagens 6–9, folha 10).
"""
import pydicom
import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from ipe.core.config import Settings
from ipe.importer.scanner import Importer


@pytest.fixture()
def janela(env, sample_dir):
    paths, db, repo = env
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    Importer(db, paths.storage).import_paths([sample_dir])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1300, 850)
    w.show()
    w.browser.refresh()
    yield app, w, repo
    w.hide()          # fechar perguntaria se descarta o filme não salvo


def _montar(w, repo):
    st = next(r for r in repo.search_studies() if r.accession == "ACC1001")
    comp = w.film_composer()
    se = repo.series_for_study(st.study_uid)[0]
    comp.set_layout(2, 2)
    comp.place_cells([comp._cell_for(se.series_uid, i) for i in range(7)])
    assert len(comp.film.sheets) == 2 and comp.film.image_count() == 7
    return st, se, comp


def _botao(comp, texto):
    return next(b for b in comp.findChildren(QPushButton) if b.text() == texto)


def _series(repo, study_uid):
    return {s.series_uid: s for s in repo.series_for_study(study_uid, ocultas=True)}


def _ler(repo, series_uid, pixels=False):
    out = [pydicom.dcmread(i["path"], stop_before_pixels=not pixels)
           for i in repo.instances_for_series(series_uid)]
    return sorted(out, key=lambda d: int(d.InstanceNumber))


def _codigo(item):
    c = item.ConceptNameCodeSequence[0]
    return c.CodeValue, c.CodingSchemeDesignator


def _num(item, code):
    n = next(x for x in item.ContentSequence if x.ValueType == "NUM" and _codigo(x) == (code, "99GEMS"))
    assert n.MeasuredValueSequence[0].MeasurementUnitsCodeSequence[0].CodeValue == "%"
    return float(n.MeasuredValueSequence[0].NumericValue)


def test_salvar_com_a_caixa_grava_as_tres_series_como_a_aw(janela, monkeypatch):
    """0.78: o botão "No exame" saiu; a gravação no exame é a caixa "também no exame" do Salvar."""
    from PySide6.QtWidgets import QInputDialog
    app, w, repo = janela
    st, se, comp = _montar(w, repo)
    assert not any(b.text() == "No exame" for b in comp.findChildren(QPushButton))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Filme AW", True)))
    msgs = []
    comp.status_message.connect(msgs.append)
    antes = _series(repo, st.study_uid)
    # 0.99.6: o botão "Salvar…" abre a janela (nome, salvar/salvar como novo, também no exame)
    from ipe.ui.film import dialogs as D

    def exec_falso(dlg):
        assert dlg.e_nome.text() and not dlg.b_novo.isVisible()      # filme novo: sem "salvar como novo"
        dlg.e_nome.setText("Filme AW")
        dlg.c_exame.setChecked(True)
        dlg._fim("salvar")
        return 1
    monkeypatch.setattr(D.SalvarFilmeDialog, "exec", exec_falso)
    _botao(comp, "Salvar…").click()
    assert comp.chk_no_exame.isChecked() and comp.film.name == "Filme AW"
    assert any(m.startswith("Filme gravado no exame: 2 folha(s) e 7 imagem(ns).") for m in msgs)

    novas = {u: s for u, s in _series(repo, st.study_uid).items() if u not in antes}
    assert len(novas) == 3, "SR + imagens soltas + folhas"
    por = {(s.description, s.modality): s for s in novas.values()}
    filme = por[("AW electronic film", se.modality)]
    sr = por[("AW electronic film", "SR")]
    folhas = por[("AW electronic pages", se.modality)]
    assert filme.num_images == 7 and sr.num_images == 1 and folhas.num_images == 2
    assert filme.series_number == sr.series_number == folhas.series_number - 1
    assert filme.series_number > max(s.series_number for s in antes.values())
    # o original não mudou
    assert {u: s.num_images for u, s in antes.items()} == \
        {u: s.num_images for u, s in _series(repo, st.study_uid).items() if u in antes}

    # intercalado como na AW: imagens 1–4, folha 5, imagens 6–8, folha 9
    assert [int(d.InstanceNumber) for d in _ler(repo, filme.series_uid)] == [1, 2, 3, 4, 6, 7, 8]
    assert [int(d.InstanceNumber) for d in _ler(repo, folhas.series_uid)] == [5, 9]

    # imagens soltas: Secondary Capture com a modalidade do exame, texto gravado, escala
    for d in _ler(repo, filme.series_uid, pixels=True):
        assert d.SOPClassUID == "1.2.840.10008.5.1.4.1.1.7" and d.Modality == se.modality
        assert list(d.ImageType) == ["DERIVED", "SECONDARY", "SCREEN SAVE"]
        assert d.ConversionType == "WSD" and d.BurnedInAnnotation == "YES"
        assert d.StudyInstanceUID == st.study_uid and str(d.PatientName).startswith("TESTE^")
        # as letras de orientação são amarelas: a célula fica RGB, igual ao que está na folha
        assert d.PhotometricInterpretation == "RGB" and d.SamplesPerPixel == 3
        assert float(d.PixelSpacing[0]) > 0, "dá para medir na imagem solta"
        assert d.pixel_array.max() > 50, "não é uma imagem preta"
    # folhas: RGB, A4 em pé com a altura da AW (~2560)
    for d in _ler(repo, folhas.series_uid, pixels=True):
        assert d.PhotometricInterpretation == "RGB" and d.SamplesPerPixel == 3
        assert 2500 <= d.Rows <= 2600 and abs(d.Rows / d.Columns - 297 / 210) < 0.01
        assert d.pixel_array.shape == (d.Rows, d.Columns, 3)


def test_o_sr_tem_a_planta_do_filme(janela, monkeypatch):
    app, w, repo = janela
    st, se, comp = _montar(w, repo)
    monkeypatch.setattr(type(comp), "avisar", lambda self, m: None)
    comp.salvar_no_exame()
    res = comp.ultimo_no_exame
    sr = _ler(repo, res.serie_sr)[0]
    soltas = {d.SOPInstanceUID: d for d in _ler(repo, res.serie_filme)}
    assert sr.SOPClassUID == "1.2.840.10008.5.1.4.1.1.88.22" and sr.Modality == "SR"
    assert _codigo(sr) == ("AWVF-0001", "99GEMS")
    assert sr.ContentTemplateSequence[0].TemplateIdentifier == "AW41 EF TID"
    paginas = [x for x in sr.ContentSequence if x.ValueType == "CONTAINER"]
    assert [_codigo(p) for p in paginas] == [("AWVF-0002", "99GEMS")] * 2
    grupos = [p.ContentSequence[0] for p in paginas]
    assert all(_codigo(g) == ("AWVF-0003", "99GEMS") for g in grupos)
    assert [_num(grupos[0], c) for c in ("AWVF-0005", "AWVF-0006", "AWVF-0007", "AWVF-0008")] == [0, 0, 1, 1]
    vagas = [[x for x in g.ContentSequence if x.ValueType == "CONTAINER"] for g in grupos]
    assert [len(v) for v in vagas] == [4, 3]
    # 2×2: posições 0 / 0,5 e tamanho ~0,5 (um pouco menos por causa do espaço entre células)
    pos = [(round(_num(v, "AWVF-0005"), 1), round(_num(v, "AWVF-0006"), 1)) for v in vagas[0]]
    assert pos == [(0, 0), (0.5, 0), (0, 0.5), (0.5, 0.5)]
    assert all(0.45 < _num(v, "AWVF-0007") <= 0.5 for v in vagas[0])
    # cada vaga aponta para uma imagem solta gravada, na ordem das instâncias
    refs = [next(x for x in v.ContentSequence if x.ValueType == "IMAGE").ReferencedSOPSequence[0]
            for vv in vagas for v in vv]
    assert [r.ReferencedSOPInstanceUID for r in refs] == list(soltas)
    assert all(r.ReferencedSOPClassUID == "1.2.840.10008.5.1.4.1.1.7" for r in refs)
    ev = sr.CurrentRequestedProcedureEvidenceSequence[0]
    assert ev.StudyInstanceUID == st.study_uid
    assert ev.ReferencedSeriesSequence[0].SeriesInstanceUID == res.serie_filme
    assert len(ev.ReferencedSeriesSequence[0].ReferencedSOPSequence) == 7


def test_o_proprio_programa_le_como_filme_da_aw(janela, monkeypatch, tmp_path):
    """O que a AW grava vai para a aba Impressões; o que nós gravamos tem de ir também."""
    app, w, repo = janela
    from ipe.printing import aw_film as AW
    st, se, comp = _montar(w, repo)
    monkeypatch.setattr(type(comp), "avisar", lambda self, m: None)
    comp.salvar_no_exame()
    linha = next(r for r in AW.studies(repo) if r["study_uid"] == st.study_uid)
    assert linha["sheets"] == 2
    job, pasta = AW.to_job(repo, st.study_uid, tmp_path)
    assert job is not None and len(job.films) == 2


def test_filme_vazio_nao_grava_nada(janela, monkeypatch):
    app, w, repo = janela
    comp = w.film_composer()
    from PySide6.QtWidgets import QMessageBox
    vistos = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: vistos.append(a[2]))
    n = sum(len(repo.series_for_study(r.study_uid, ocultas=True)) for r in repo.search_studies())
    comp.salvar_no_exame()
    assert vistos and "vazio" in vistos[0]
    assert sum(len(repo.series_for_study(r.study_uid, ocultas=True)) for r in repo.search_studies()) == n


def test_celula_sem_cor_vira_cinza():
    import numpy as np
    from ipe.ui.film.salvar_dicom import _cinza_se_der
    cinza = np.repeat(np.arange(12, dtype=np.uint8).reshape(3, 4, 1), 3, axis=2)
    assert _cinza_se_der(cinza).shape == (3, 4)
    cor = cinza.copy()
    cor[0, 0] = (200, 180, 40)
    assert _cinza_se_der(cor).shape == (3, 4, 3)
