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


# 0.100.36: o banco é sempre PostgreSQL. Nos testes, um servidor só para a sessão inteira e um **esquema novo e
# vazio para cada banco** (cada …/dicomviewer.sqlite de cada tmp_path) — no lugar do PostgreSQL do Ipê em <pasta>/postgres.
#   IPE_TEST_PG=postgresql://usuario:senha@host:5432/banco   usa esse servidor;
#   sem a variável, liga o PostgreSQL do Ipê numa pasta temporária (compartilhada pelos processos de teste).
# Quem testa o PostgreSQL do Ipê de verdade marca `@pytest.mark.pg_de_verdade`.
_PG = os.environ.get("IPE_TEST_PG", "").strip()
_PG_BASE: list[str] = []
_PG_ESQUEMAS: dict[str, str] = {}
_PG_FILA: list[str] = []


def _pg_base() -> str:
    if not _PG_BASE:
        if _PG:
            _PG_BASE.append(_PG.replace("postgresql://", "postgresql+psycopg://", 1))
        else:
            import tempfile

            from ipe.core import pg_embutido as PE
            pasta = Path(tempfile.gettempdir()) / f"ipe_testes_pg_{os.getuid() if hasattr(os, 'getuid') else 0}"
            _PG_BASE.append(PE.endereco_da_pasta(pasta))
    return _PG_BASE[0]


def _esquema_do_banco(arquivo: Path) -> str:
    chave = str(Path(arquivo).resolve())
    if chave not in _PG_ESQUEMAS:
        import uuid

        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import NullPool
        nome = f"t_{os.getpid()}_{len(_PG_ESQUEMAS)}_{uuid.uuid4().hex[:6]}"
        eng = create_engine(_pg_base(), poolclass=NullPool)
        with eng.begin() as c:
            c.execute(text(f'CREATE SCHEMA "{nome}"'))
        eng.dispose()
        _PG_ESQUEMAS[chave] = nome
        _PG_FILA.append(nome)
    return _PG_ESQUEMAS[chave]


def url_de_teste(arquivo: Path) -> str:
    """O endereço do banco de teste `arquivo` (…/dicomviewer.sqlite: um esquema só dele)."""
    base = _pg_base()
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}options=-csearch_path%3D{_esquema_do_banco(arquivo)}"


@pytest.fixture(autouse=True)
def _banco_postgres(request, monkeypatch):
    monkeypatch.setenv("IPE_DB_SEM_POOL", "1")
    if request.node.get_closest_marker("pg_de_verdade"):
        yield
        return
    from ipe.db import session as SS
    monkeypatch.setattr(SS, "endereco_da_pasta", lambda path: url_de_teste(Path(path)))
    yield


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
    # os esquemas só saem no fim: uma janela de um teste (com o seu relógio) pode continuar consultando o banco
    # depois do fim dele
    if not (_PG_BASE and _PG_FILA):
        return
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool
    eng = create_engine(_PG_BASE[0], poolclass=NullPool)
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
    config.addinivalue_line("markers", "pg_de_verdade: o teste liga o PostgreSQL do Ipê de verdade, sem o esquema")


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


@pytest.fixture(autouse=True)
def _caches_do_servidor_limpos():
    """0.100.38: os caches do servidor central são por UID de série/exame, e os exames de exemplo têm os mesmos UIDs
    em todos os testes — sem limpar, um teste recebia caminhos e metadados do anterior."""
    yield
    try:
        from ipe.central import web as WEB
        with WEB.CAMINHOS._lock:
            WEB.CAMINHOS._d.clear()
        with WEB._META_TRAVA:
            WEB._META.clear()
    except Exception:  # noqa: BLE001
        pass
