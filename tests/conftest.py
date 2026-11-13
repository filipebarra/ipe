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


# 0.100.34: IPE_TEST_PG=postgresql://usuario:senha@host:5432/banco roda a suíte com o banco principal no
# PostgreSQL — cada teste num esquema novo e vazio (os bancos de outras pastas continuam SQLite, como no programa).
_PG = os.environ.get("IPE_TEST_PG", "").strip()
_PG_N = [0]
_PG_FILA: list[str] = []


@pytest.fixture(autouse=True)
def _banco_postgres(request, monkeypatch):
    if not _PG or request.node.get_closest_marker("so_sqlite"):
        yield
        return
    import uuid

    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool
    nome = f"t_{os.getpid()}_{_PG_N[0]}_{uuid.uuid4().hex[:6]}"
    _PG_N[0] += 1
    base = _PG.replace("postgresql://", "postgresql+psycopg://", 1)
    eng = create_engine(base, poolclass=NullPool)
    with eng.begin() as c:
        c.execute(text(f'CREATE SCHEMA "{nome}"'))
    sep = "&" if "?" in _PG else "?"
    url = f"{_PG}{sep}options=-csearch_path%3D{nome}"
    monkeypatch.setenv("IPE_DB_SEM_POOL", "1")
    # como num computador com o banco no PostgreSQL: vale para a primeira pasta de dados do teste; outra pasta
    # (o "computador cliente" de um teste com servidor e cliente) continua com o seu SQLite
    from ipe.core.config import get_paths
    from ipe.db import session as SS
    primeira = []

    def endereco():
        dados = get_paths().data.resolve()
        if not primeira:
            primeira.append(dados)
        return SS._normalizar(url) if dados == primeira[0] else ""
    monkeypatch.setattr(SS, "endereco_configurado", endereco)
    yield
    # o esquema só sai no fim da sessão (pytest_sessionfinish): uma janela de um teste (com o seu relógio) pode
    # continuar consultando o banco depois do fim dele — no SQLite o arquivo continua lá, aqui o esquema também
    _PG_FILA.append(nome)
    eng.dispose()


@pytest.fixture(autouse=True)
def _sem_github(monkeypatch):
    """0.99.70: a janela não procura versão nova no GitHub durante os testes."""
    monkeypatch.setenv("IPE_SEM_GITHUB", "1")


@pytest.fixture(autouse=True)
def _system_user():
    """Cada teste começa com o usuário "sistema" (todas as permissões)."""
    from ipe.auth import session as S
    S.set_current(S.UserSession())
    yield
    S.set_current(S.UserSession())


@pytest.fixture(autouse=True)
def _chave_dos_segredos(tmp_path_factory, monkeypatch):
    """0.99.55: a chave local dos segredos cifrados fica numa pasta do teste, não na do usuário."""
    from ipe.core import segredos as SG
    monkeypatch.setattr(SG, "PASTA", tmp_path_factory.getbasetemp() / "chave_dos_segredos")


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


def pytest_sessionfinish(session, exitstatus):
    if not (_PG and _PG_FILA):
        return
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool
    eng = create_engine(_PG.replace("postgresql://", "postgresql+psycopg://", 1), poolclass=NullPool)
    for nome in _PG_FILA:
        try:
            with eng.begin() as c:
                c.execute(text("SET lock_timeout = '5s'"))
                c.execute(text(f'DROP SCHEMA "{nome}" CASCADE'))
        except Exception:  # noqa: BLE001 - uma conexão ainda presa: o esquema fica
            pass
    eng.dispose()


def pytest_configure(config):
    config.addinivalue_line("markers", "pergunta_ao_sair: o teste confere a pergunta ao fechar o programa")
    config.addinivalue_line("markers", "so_sqlite: o teste mexe no arquivo do banco; com IPE_TEST_PG fica no SQLite")


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
