"""Painel de filmes e impressões (0.77).

Pedido dele (19/10/2026): *"crie um dashboard com informações sobre os filmes salvos e impressão.
inclua data de criação, modalidade, usuário, se foi impresso ou não, tempo entre exame, filme e
impressão. % de impressão dos filmes feitos"*.
"""
import csv
from datetime import date, datetime, timedelta

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from ipe.core import film_stats as F
from test_printing import _window

AGORA = datetime(2026, 10, 19, 14, 0)


def _row(i, criado, impresso=None, mods=("MG",), user="ana", data="20261019", hora="080000", **kw):
    r = {"id": i, "name": f"F{i}", "patient_name": f"P{i}", "created_at": criado, "printed_at": impresso,
         "created_by": user, "printed_by": user if impresso else "", "print_count": 1 if impresso else 0,
         "print_destination": "DRYVIEW" if impresso else "", "modalities": list(mods), "sheets": 2,
         "images": 8, "study_date": data, "study_time": hora, "study_description": "MAMOGRAFIA",
         "accession": f"A{i}"}
    r.update(kw)
    return r


# ------------------------------------------------------------------ contas
def test_hora_do_exame():
    assert F.hora_do_exame("20261009", "083015.123") == datetime(2026, 10, 9, 8, 30, 15)
    assert F.hora_do_exame("20261009", "") == datetime(2026, 10, 9)
    assert F.hora_do_exame("20261009", "0830") == datetime(2026, 10, 9, 8, 30)
    assert F.hora_do_exame("", "0830") is None and F.hora_do_exame("2026", "") is None


def test_resumo_porcentagem_tempos_e_grupos():
    ls = F.linhas([
        _row(1, datetime(2026, 10, 19, 9, 0), datetime(2026, 10, 19, 10, 0)),            # 1 h / 1 h
        _row(2, datetime(2026, 10, 19, 11, 0), datetime(2026, 10, 19, 14, 0), user="bia"),  # 3 h / 3 h
        _row(3, datetime(2026, 10, 15, 9, 0), mods=("CT", "PT"), data="20261015"),        # parado
        _row(4, datetime(2026, 10, 19, 13, 0), user="bia", mods=("CT",)),                 # recente
        _row(5, datetime(2026, 10, 19, 7, 0), datetime(2026, 10, 20, 9, 0)),              # hora errada
    ])
    r = F.resumo(ls, agora=AGORA, dias_parado=2)
    assert r.filmes == 5 and r.impressos == 3 and r.pct == pytest.approx(60)
    # exame 08:00 -> filme: 1 h, 3 h, 1 h (exame 15/10 08:00 -> 09:00), 5 h, e -1 h fora da conta
    assert r.exame_filme.n == 4 and r.exame_filme.negativos == 1
    assert r.exame_filme.mediana == pytest.approx(2.0)
    assert r.filme_impressao.mediana == pytest.approx(3.0)        # 1 h, 3 h, 26 h
    assert r.impressos_24h == 2, "o de 25 h do exame não entra em 24 h"
    assert [l.id for l in r.parados] == [3], "parado = sem impressão há mais de 2 dias"
    mods = {g.nome: g for g in r.por_modalidade}
    assert mods["MG"].filmes == 3 and mods["MG"].impressos == 3 and mods["MG"].pct == 100
    assert mods["CT"].filmes == 2 and mods["PT"].filmes == 1, "filme com duas modalidades conta nas duas"
    users = {g.nome: g for g in r.por_usuario}
    assert users["ana"].filmes == 3 and users["bia"].impressos == 1
    assert r.por_mes == [("2026-10", 3, 2)]
    assert r.folhas_impressas == 6 and r.por_destino == [("DRYVIEW", 3)]


def test_filtro_e_periodo():
    ls = F.linhas([_row(1, datetime(2026, 10, 19, 9)), _row(2, datetime(2026, 9, 1, 9), mods=("CT",)),
                   _row(3, datetime(2026, 10, 18, 9), user="")])
    de, ate = F.periodo("7d", hoje=date(2026, 10, 19))
    assert (de, ate) == (date(2026, 10, 13), date(2026, 10, 19))
    assert [l.id for l in ls if F.Filtro(de, ate).aceita(l)] == [1, 3]
    assert [l.id for l in ls if F.Filtro(modalidade="CT").aceita(l)] == [2]
    assert [l.id for l in ls if F.Filtro(usuario=F.SEM_USUARIO).aceita(l)] == [3], \
        "filme sem usuário gravado (antes da 0.77) aparece como (não registrado)"
    assert F.periodo("tudo") == (None, None)


def test_duracao_em_texto():
    assert F.duracao(None) == "—" and F.duracao(0.5) == "30 min"
    assert F.duracao(5.25) == "5,2 h" and F.duracao(74.4) == "3,1 d"


# ------------------------------------------------------------------ banco
def test_banco_guarda_quem_salvou_e_conta_as_impressoes(env):
    paths, db, repo = env
    fid = repo.save_film("F", {"sheets": []}, [], "P", user="ana")
    repo.save_film("F2", {"sheets": []}, [], "P", film_id=fid, user="bia")
    row = repo.film_stats_rows()[0]
    assert row["created_by"] == "ana", "salvar de novo não troca quem criou"
    assert row["print_count"] == 0 and row["printed_at"] is None
    repo.mark_film_printed(fid, "bia", "Impressora DICOM: DRYVIEW")
    repo.mark_film_printed(fid, "carla", "Impressora do Windows: HP")
    row = repo.film_stats_rows()[0]
    assert row["print_count"] == 2 and row["printed_by"] == "carla"
    assert row["print_destination"] == "Impressora do Windows: HP" and row["printed_at"] is not None


def test_filme_impresso_antes_da_077_conta_como_uma_vez(env):
    from ipe.db.models import SavedFilm
    paths, db, repo = env
    fid = repo.save_film("Velho", {"sheets": []}, [], "P")
    with db.session() as s:
        s.get(SavedFilm, fid).printed_at = datetime(2026, 9, 1)
    assert repo.film_stats_rows()[0]["print_count"] == 1
    repo.mark_film_printed(fid)
    assert repo.film_stats_rows()[0]["print_count"] == 2


# ------------------------------------------------------------------ de ponta a ponta
@pytest.fixture()
def janela(env, sample_dir, monkeypatch):
    app, w, repo = _window(env, sample_dir)
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("Filme X", True)))
    yield app, w, repo
    comp = getattr(w, "_film", None)
    if comp is not None:
        comp.dirty = False
    d = getattr(w, "_film_dashboard", None)
    if d is not None:
        d.close()
    w.close()


def _filme_do_exame(app, w):
    assert w.handle_external({"accession": "ACC1001"}) == "aberto"
    tab = w.tabs.currentWidget()
    app.processEvents()
    tab.film_add_current()
    return tab, w.film_composer()


def test_modalidade_vem_das_imagens_e_o_usuario_e_gravado(janela):
    app, w, repo = janela
    tab, comp = _filme_do_exame(app, w)
    assert comp.save()
    row = next(r for r in repo.film_stats_rows() if r["id"] == comp.film_id)
    serie = repo.series_info(tab.viewports[0].series_uid) or {}
    assert row["modalities"] == [serie.get("modality")]
    from ipe.auth import session as S
    assert row["created_by"] == S.get().username
    assert row["study_date"], "a data do exame vem junto, para o tempo exame → filme"
    assert any(a[2] == "salvar filme" for a in repo.audit_entries(limit=20))


def test_filme_impresso_sem_salvar_e_salvo_e_contado(janela):
    app, w, repo = janela
    _tab, comp = _filme_do_exame(app, w)
    assert comp.film_id is None
    comp._after_print("Impressora DICOM: DRYVIEW")
    assert comp.film_id is not None and not comp.dirty
    row = next(r for r in repo.film_stats_rows() if r["id"] == comp.film_id)
    assert row["print_count"] == 1 and row["print_destination"] == "Impressora DICOM: DRYVIEW"


def test_o_painel_mostra_filtra_exporta_e_abre(janela, tmp_path):
    app, w, repo = janela
    _tab, comp = _filme_do_exame(app, w)
    comp.save()
    impresso = comp.film_id
    comp._after_print("Impressora DICOM: DRYVIEW")
    comp.new_film()
    _filme_do_exame(app, w)
    comp.save()                                      # segundo filme, não impresso
    d = w.show_film_dashboard()
    app.processEvents()
    d.c_periodo.setCurrentIndex(d.c_periodo.findData("tudo"))
    assert d.k_filmes.l_valor.text() == "2"
    assert d.k_impressos.l_valor.text() == "50%" and "1 de 2" in d.k_impressos.l_detalhe.text()
    assert d.t_filmes.rowCount() == 2 and d.t_mod.rowCount() >= 1 and d.t_user.rowCount() == 1
    cab = [d.t_filmes.horizontalHeaderItem(j).text() for j in range(d.t_filmes.columnCount())]
    for c in ("Criado em", "Criado por", "Modalidade", "Impresso", "Exame → filme", "Filme → impressão"):
        assert c in cab
    d.k_so_nao.setChecked(True)
    assert d.t_filmes.rowCount() == 1
    d.k_so_nao.setChecked(False)
    i = d.c_mod.findData("XX")
    assert i < 0
    # os gráficos desenham sem erro, com e sem dado
    assert not d.g_meses.grab().isNull() and not d.g_mod.grab().isNull()
    assert d.g_meses._alvos and "impresso" in d.g_meses._alvos[0][1]
    # CSV: ; e BOM, abre no Excel
    p = d.exportar_csv(str(tmp_path / "f.csv"))
    texto = (tmp_path / "f.csv").read_bytes()
    assert p and texto[:3] == b"\xef\xbb\xbf"
    linhas = list(csv.reader(texto.decode("utf-8-sig").splitlines(), delimiter=";"))
    assert linhas[0][0] == "Criado em" and len(linhas) == 3
    # duplo clique abre o filme no compositor
    abertos = []
    d.abrir_filme.connect(abertos.append)
    linha = next(r for r in range(d.t_filmes.rowCount())
                 if d.t_filmes.item(r, 0).data(Qt.UserRole + 1) == impresso)
    d._abrir_linha(d.t_filmes.model().index(linha, 0))
    assert abertos == [impresso]
    # período sem filme: cartões e gráficos dizem que não há nada
    d.c_periodo.setCurrentIndex(d.c_periodo.findData("datas"))
    d.d_de.setDate(d.d_de.date().addYears(-5))
    d.d_ate.setDate(d.d_de.date().addDays(1))
    assert d.k_filmes.l_valor.text() == "0" and d.k_impressos.l_valor.text() == "—"
    assert not d.g_meses.grab().isNull()


def test_painel_some_no_modo_ocultar(janela, monkeypatch):
    app, w, repo = janela
    d = w.show_film_dashboard()
    assert d.isVisible()
    w.set_privacy(True)
    assert not d.isVisible()
    avisos = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: avisos.append(a[2]) or 0))
    assert w.show_film_dashboard() is None and avisos and "ocultos" in avisos[0]
    w.set_privacy(False)


def test_o_menu_e_a_aba_de_impressoes_levam_ao_painel(janela):
    app, w, repo = janela
    menu = next(a.menu() for a in w.menuBar().actions() if a.menu() and
                any(x.text() == "Painel de filmes e impressões…" for x in a.menu().actions()))
    assert menu is not None
    aba = w.show_prints()
    from PySide6.QtWidgets import QPushButton
    b = next(x for x in aba.findChildren(QPushButton) if x.text() == "Painel…")
    b.click()
    app.processEvents()
    assert w._film_dashboard.isVisible()
