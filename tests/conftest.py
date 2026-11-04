import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def sample_dir(tmp_path_factory):
    from ipe.core.sample_data import make_sample_data
    d = tmp_path_factory.mktemp("sample")
    make_sample_data(d)
    return d


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMVIEWER_HOME", str(tmp_path / "home"))
    from ipe.core.config import get_paths
    from ipe.db.repository import Repository
    from ipe.db.session import Database
    paths = get_paths()
    db = Database(paths.database)
    return paths, db, Repository(db)


@pytest.fixture(autouse=True)
def _system_user():
    """Cada teste começa com o usuário "sistema" (todas as permissões)."""
    from ipe.auth import session as S
    S.set_current(S.UserSession())
    yield
    S.set_current(S.UserSession())


@pytest.fixture(autouse=True)
def _sem_ocr_na_chegada(monkeypatch):
    """O OCR na chegada da impressão (0.81) vem desligado nos testes: rodar o leitor de verdade em
    cada impressão de teste pesa (onnxruntime) e não é o que esses testes conferem. Quem testa o
    OCR na chegada liga explicitamente (test_ocr_chegada.py)."""
    from ipe.printing import arrival
    monkeypatch.setattr(arrival, "PADRAO", False)


@pytest.fixture(autouse=True)
def _sair_sem_perguntar(request, monkeypatch):
    """0.99.6: fechar o programa pergunta antes. Nos testes as janelas fecham sem a caixa (ela
    travaria o teste); quem testa a pergunta marca `@pytest.mark.pergunta_ao_sair`."""
    if request.node.get_closest_marker("pergunta_ao_sair"):
        return
    from ipe.ui.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "_confirmar_saida", lambda self: True)


def pytest_configure(config):
    config.addinivalue_line("markers", "pergunta_ao_sair: o teste confere a pergunta ao fechar o programa")


@pytest.fixture(autouse=True)
def _sem_juntar_folhas(monkeypatch):
    """0.99.6: "juntar folhas" segura o encaminhamento por 90 s; nos testes vem desligado. Quem testa
    o juntar liga explicitamente (test_juntar_folhas.py)."""
    from ipe.printing import juntar
    monkeypatch.setattr(juntar, "PADRAO", False)


@pytest.fixture(autouse=True)
def _outro_paciente_sem_perguntar(monkeypatch):
    """A pergunta "outro paciente aberto" (0.99.22) é modal: nos testes antigos de chamada externa
    ela travaria esperando clique. Mantém os dois; os testes dela trocam isto explicitamente."""
    from ipe.ui.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "perguntar_outro_paciente", lambda self, novo, outros: "manter")


@pytest.fixture(autouse=True)
def _exportar_misturado_sem_perguntar(monkeypatch):
    """Exportar pacientes diferentes num pacote só pergunta (0.99.45) — modal trava o teste."""
    from ipe.ui.export_dialog import ExportDialog
    monkeypatch.setattr(ExportDialog, "confirmar_mistura", lambda self, infos: True)


@pytest.fixture(autouse=True)
def _link_sem_perguntar(monkeypatch):
    """O link ipe:// sem token pergunta antes de abrir (0.99.24) — pergunta modal trava o teste. Os
    testes de chamada por link aceitam; os de segurança trocam isto explicitamente."""
    from ipe.ui.main_window import MainWindow
    monkeypatch.setattr(MainWindow, "perguntar_link", lambda self, args, o_que: True)
