"""0.100.101: botão direito no banco ▸ IA (as IAs do exame, com as opções de cada uma) e a coluna "Neste computador"
do Ipê cliente (o exame do servidor também está no banco daqui, inteiro ou em parte)."""
from types import SimpleNamespace

from _menus import todas
import pytest
from PySide6.QtWidgets import QApplication

from ipe.core.config import Settings
from ipe.importer.scanner import Importer


@pytest.fixture()
def janela(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    app = QApplication.instance() or QApplication([])
    from ipe.ui.main_window import MainWindow
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()
    w.browser.refresh()
    yield app, w, repo
    w.close()


class Motor:
    def __init__(self, serie):
        self.serie = serie
        self.pedidos = []

    def ferramentas_do_exame(self, uid):
        return [{"tipo": "composicao", "titulo": "Composição corporal", "serie": self.serie, "motivo": "",
                 "ja_feita": True, "andando": False},
                {"tipo": "enfisema", "titulo": "Enfisema", "serie": None, "motivo": "o exame não é de tórax",
                 "ja_feita": False, "andando": False}]

    def pedir(self, uid, tipo, serie=None, quem=""):
        self.pedidos.append((uid, tipo, serie))
        return 1


def _menu_ia(b, rows):
    menu = b.menu_do_exame(rows)
    ia = next(a.menu() for a in menu.actions() if a.menu() is not None and a.text() == "IA")
    b._encher_menu_ia(ia, rows)
    return ia


def test_menu_ia_do_banco_lista_as_ias_com_as_opcoes(janela, monkeypatch):
    app, w, repo = janela
    b = w.browser
    b.table.selectRow(0)
    rows = b.selected_rows()
    series = repo.series_for_study(rows[0].study_uid)
    motor = Motor(series[0].series_uid)
    b.motor_ia = motor
    pedidos = []
    monkeypatch.setattr(type(b), "segmentar_orgaos",
                        lambda self, uid, su, simular=False, tipo="abdome": pedidos.append((uid, su, tipo)))
    ia = _menu_ia(b, rows)
    textos = [a.text() for a in todas(ia)]
    assert any(t.startswith("Composição corporal ✔") for t in textos)
    assert any(t.startswith("Enfisema — o exame não é de tórax") for t in textos)
    assert any(t.startswith("Outras IAs") for t in textos)
    assert "Tarefas de IA (andamento e cancelar)…" in textos
    refazer = next(a for a in todas(ia) if a.text().startswith("Refazer na série sugerida"))
    refazer.trigger()
    assert pedidos == [(rows[0].study_uid, series[0].series_uid, "composicao")]


def test_varios_exames_entram_na_fila_de_ia(janela, monkeypatch):
    app, w, repo = janela
    b = w.browser
    b.table.selectAll()
    rows = b.selected_rows()
    assert len(rows) > 1
    motor = Motor("x")
    b.motor_ia = motor
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    ia = _menu_ia(b, rows)
    a = next(x for x in todas(ia) if x.text() == "Composição corporal")
    a.trigger()
    assert sorted(p[0] for p in motor.pedidos) == sorted(r.study_uid for r in rows)
    assert all(p[1] == "composicao" and p[2] is None for p in motor.pedidos)


def test_coluna_neste_computador(env, sample_dir):
    paths, db, repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    from ipe.central.client_repo import ClientRepository
    rows = repo.search_studies(limit=100)
    assert rows
    n = repo.imagens_por_exame([r.study_uid for r in rows])
    assert all(n[r.study_uid] == r.num_images for r in rows)
    falso = SimpleNamespace(local=repo)
    do_servidor = [SimpleNamespace(study_uid=rows[0].study_uid, num_images=rows[0].num_images),
                   SimpleNamespace(study_uid=rows[0].study_uid + ".9", num_images=5)]
    if len(rows) > 1:
        do_servidor.append(SimpleNamespace(study_uid=rows[1].study_uid, num_images=rows[1].num_images + 10))
    est = ClientRepository.no_computador(falso, do_servidor)
    assert est[rows[0].study_uid] == "completo"
    assert est[rows[0].study_uid + ".9"] == ""
    if len(rows) > 1:
        assert est[rows[1].study_uid] == "parcial"
    from PySide6.QtCore import Qt

    from ipe.ui.browser import KEY_INDEX, StudyTableModel
    _app = QApplication.instance() or QApplication([])
    m = StudyTableModel()
    m.locais = {rows[0].study_uid: "parcial"}
    m.set_rows(rows[:1])
    assert m.data(m.index(0, KEY_INDEX["no_computador"]), Qt.DisplayRole) == "◐ parcial"
    assert m.data(m.index(0, KEY_INDEX["no_computador"]), Qt.UserRole) == 1
