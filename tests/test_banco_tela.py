"""A tela do banco de dados: painel Locais recolhível, séries em ícone ou lista,
ocultar/apagar série e o botão Monitor."""
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QListWidget, QMenu, QMessageBox

from ipe.core.config import Settings
from ipe.importer.scanner import Importer


@pytest.fixture()
def janela(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.resize(1200, 800)
    w.show()
    w.browser.refresh()
    app.processEvents()
    yield app, w, w.browser
    w.close()


def _seleciona_primeiro(app, b):
    b.table.selectRow(0)
    app.processEvents()
    return b.selected_rows()[0]


# ------------------------------------------------------------------ 1. Locais
def test_o_painel_de_locais_recolhe_e_lembra(janela):
    app, w, b = janela
    p = w.locations
    assert p.tree.isVisible()
    p.cabecalho.click()
    app.processEvents()
    assert not p.tree.isVisible()
    assert w.settings.get("browser.locais_recolhido") is True
    assert p.cabecalho.text().startswith("▸")
    p.cabecalho.click()
    assert p.tree.isVisible() and p.cabecalho.text().startswith("▾")
    assert w.settings.get("browser.locais_recolhido") is False


def test_recolhido_o_cabecalho_diz_em_que_local_voce_esta(janela):
    app, w, b = janela
    p = w.locations
    p.recolher(True)
    assert "(" in p.cabecalho.text(), "recolhido tem de dizer o local atual"


# ------------------------------------------------------------------ 2. ícone/lista
def test_series_em_icone_ou_em_lista(janela):
    app, w, b = janela
    _seleciona_primeiro(app, b)
    assert b.series_list.count() > 0
    assert b.series_list.viewMode() == QListWidget.IconMode
    alto = b.series_list.item(0).sizeHint().height()
    b.set_series_view("lista")
    app.processEvents()
    assert b.series_list.viewMode() == QListWidget.ListMode
    assert b.series_list.item(0).sizeHint().height() < alto
    assert "\n" not in b.series_list.item(0).text()
    assert w.settings.get("browser.series_view") == "lista"
    b.set_series_view("icone")
    assert b.series_list.viewMode() == QListWidget.IconMode


def test_a_vista_escolhida_volta_na_proxima_abertura(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    st = Settings(paths.settings_file)
    st.set("browser.series_view", "lista")
    w = MainWindow(paths, st)
    w.show()
    assert w.browser.series_list.viewMode() == QListWidget.ListMode
    w.close()


# ------------------------------------------------------------------ 3. ocultar / apagar
def test_ocultar_tira_a_serie_das_listas_sem_apagar(janela):
    app, w, b = janela
    r = _seleciona_primeiro(app, b)
    antes = b.repo.series_for_study(r.study_uid)
    assert len(antes) >= 2
    uid = antes[0].series_uid
    b._hide_series([uid], True)
    app.processEvents()
    # some da lista do banco e do que o visualizador pede
    assert uid not in [s.series_uid for s in b.repo.series_for_study(r.study_uid)]
    assert uid in [s.series_uid for s in b.repo.series_for_study(r.study_uid, ocultas=True)]
    assert b.repo.count_hidden_series(r.study_uid) == 1
    assert b.btn_ocultas.isVisible(), "tem de haver como trazer de volta"
    # mostrar as ocultas e desfazer
    b.btn_ocultas.setChecked(True)
    app.processEvents()
    assert uid in [b.series_list.item(i).data(Qt.UserRole) for i in range(b.series_list.count())]
    b._hide_series([uid], False)
    assert b.repo.count_hidden_series(r.study_uid) == 0


def test_apagar_serie_apaga_os_arquivos_do_storage(janela, monkeypatch):
    app, w, b = janela
    r = _seleciona_primeiro(app, b)
    series = b.repo.series_for_study(r.study_uid)
    alvo = series[0].series_uid
    arquivos = [i["path"] for i in b.repo.instances_for_series(alvo)]
    assert arquivos
    from pathlib import Path
    assert all(Path(f).exists() for f in arquivos)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    b._delete_series([alvo])
    app.processEvents()
    assert alvo not in [s.series_uid for s in b.repo.series_for_study(r.study_uid, ocultas=True)]
    assert not any(Path(f).exists() for f in arquivos)
    assert len(b.repo.series_for_study(r.study_uid)) == len(series) - 1


def test_a_ultima_serie_do_exame_nao_se_apaga_sozinha(janela):
    """Exame sem série nenhuma é fantasma: para isso existe o apagar exame."""
    app, w, b = janela
    r = _seleciona_primeiro(app, b)
    series = b.repo.series_for_study(r.study_uid)
    for s in series[:-1]:
        b.repo.delete_series(s.series_uid, b.storage_root)
    with pytest.raises(PermissionError):
        b.repo.delete_series(series[-1].series_uid, b.storage_root)


def test_exame_com_cadeado_nao_perde_serie(janela):
    app, w, b = janela
    r = _seleciona_primeiro(app, b)
    b.repo.set_locked(r.study_uid, True)
    uid = b.repo.series_for_study(r.study_uid)[0].series_uid
    with pytest.raises(PermissionError):
        b.repo.delete_series(uid, b.storage_root)
    b.repo.set_locked(r.study_uid, False)


def test_o_menu_da_serie_tem_ocultar_e_apagar(janela):
    app, w, b = janela
    r = _seleciona_primeiro(app, b)
    uid = b.repo.series_for_study(r.study_uid)[0].series_uid
    textos = [a.text() for a in b.series_menu(r.study_uid, [uid]).actions()]
    assert any(t.startswith("Ocultar") for t in textos)
    assert any(t.startswith("Apagar") for t in textos)
    assert not any("Mostrar de novo" in t for t in textos)
    # com a série oculta, o menu passa a oferecer trazer de volta
    b.repo.set_series_hidden([uid], True)
    textos = [a.text() for a in b.series_menu(r.study_uid, [uid]).actions()]
    assert any("Mostrar de novo" in t for t in textos)
    b.repo.set_series_hidden([uid], False)


# ------------------------------------------------------------------ 4. botão Monitor
def test_o_botao_monitor_abre_as_configuracoes(janela, monkeypatch):
    app, w, b = janela
    abas = []
    monkeypatch.setattr(type(w), "open_preferences", lambda self, tab="": abas.append(tab))
    abertos = []
    monkeypatch.setattr(type(w), "open_on_monitor", lambda self, uid, screen=None: abertos.append(uid))
    w.home_bar._monitor_default()
    assert abas == ["Monitores"] and abertos == []


# ------------------------------------------------------------------ 5. dinâmica
def test_marcar_series_como_dinamica(janela, monkeypatch):
    app, w, b = janela
    r = _seleciona_primeiro(app, b)
    uids = [s.series_uid for s in b.repo.series_for_study(r.study_uid)][:3]
    assert len(uids) >= 2
    monkeypatch.setattr("PySide6.QtWidgets.QInputDialog.getText", lambda *a, **k: ("Perfusão", True))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    avisos = []
    b.series_changed.connect(lambda: avisos.append(1))
    b._marcar_dinamica(r.study_uid, uids)
    app.processEvents()
    grupos = b.repo.series_groups(r.study_uid)
    assert len(grupos) == 1
    g = grupos[0]
    assert g["name"] == "Perfusão" and g["kind"] == "dynamic"
    # a ordem é a das séries no exame, não a ordem dos cliques
    ordem = [s.series_uid for s in b.repo.series_for_study(r.study_uid, ocultas=True)]
    assert g["series_uids"] == [u for u in ordem if u in set(uids)]
    assert avisos, "quem mostra séries precisa saber"
    # a marca aparece na lista e o menu oferece desfazer
    textos = [b.series_list.item(i).text() for i in range(b.series_list.count())]
    assert any("Perfusão" in t for t in textos)
    assert any("Desfazer" in a.text() for a in b.series_menu(r.study_uid, uids[:1]).actions())
    b._desfazer_dinamica(r.study_uid, g["id"])
    assert b.repo.series_groups(r.study_uid) == []


def test_uma_serie_so_nao_e_dinamica(janela, monkeypatch):
    app, w, b = janela
    r = _seleciona_primeiro(app, b)
    uid = b.repo.series_for_study(r.study_uid)[0].series_uid
    ditos = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: ditos.append(a[2] if len(a) > 2 else ""))
    b._marcar_dinamica(r.study_uid, [uid])
    assert ditos and not b.repo.series_groups(r.study_uid)
