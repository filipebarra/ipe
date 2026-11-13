"""PostgreSQL embutido no Ipê (0.100.35): o servidor vem dentro do pacote, sem instalar nada à parte.

Usa o `pixeltable-pgserver` (Apache-2.0), que traz o PostgreSQL 16 pronto para Windows, macOS e Linux. Os dados ficam
na pasta de dados do Ipê (`<dados>/postgres`, ao lado do Storage). O servidor:

- liga sozinho na primeira vez que o Ipê (ou o `ipe server`) abre o banco, e cria o banco na primeira vez;
- só aceita conexão deste computador: no Linux e no macOS por um arquivo de conexão dentro da pasta dos dados (sem
  porta de rede); no Windows pelo 127.0.0.1 numa porta livre, **com senha** (a criação do banco deixa entrar sem
  senha; aqui a senha é posta e guardada cifrada no `banco.json`);
- é dividido entre os programas do Ipê abertos neste computador e desliga quando o último fecha.
"""
from __future__ import annotations

import contextlib
import logging
import os
import re
import secrets
import time
from pathlib import Path

log = logging.getLogger(__name__)

PASTA = "postgres"
BANCO = "ipe"
_SERVIDOR: dict = {}            # pasta -> PostgresServer (mantido vivo enquanto o programa roda)


class ErroEmbutido(Exception):
    pass


def disponivel() -> bool:
    try:
        import pixeltable_pgserver  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    from ipe.core import runtime as R
    return not R.frozen() or _arquivo_do_pacote().is_file()


ARQUIVO_PACOTE = "pg16.tar.gz"
#: dentro do arquivo, como no site-packages: as rodas do PyPI tiram as bibliotecas dos executáveis para uma pasta
#: vizinha e apontam para ela por caminho relativo — no Linux `pixeltable_pgserver.libs` (auditwheel), no macOS
#: `pixeltable_pgserver/.dylibs` (delocate); no Windows as DLLs ficam junto dos .exe
BIN_NO_ARQUIVO = ("pixeltable_pgserver", "pginstall", "bin")


def montar_arquivo(pasta_do_pacote: Path, arquivo: Path) -> Path:
    """Para o ipe.spec: o PostgreSQL 16 do pixeltable-pgserver num .tar.gz, com a mesma estrutura do site-packages
    (sem o PostgreSQL 18, os cabeçalhos e o código Python)."""
    import tarfile
    pasta_do_pacote = Path(pasta_do_pacote)
    site = pasta_do_pacote.parent
    raizes = [pasta_do_pacote / "pginstall" / p for p in ("bin", "lib", "share")]
    raizes += [pasta_do_pacote / ".dylibs", site / (pasta_do_pacote.name + ".libs")]
    with tarfile.open(arquivo, "w:gz", compresslevel=6) as t:
        for r in raizes:
            if not r.exists():
                continue
            for item in sorted([r, *r.rglob("*")]):
                nome = item.name
                if item.is_file() and re.search(r"\.(so|dylib)[.0-9]*$", nome) and re.search(r"\.18\b|[.-]18\.", nome):
                    continue                           # as bibliotecas do PostgreSQL 18 (ficam de fora)
                t.add(str(item), arcname=str(item.relative_to(site)), recursive=False)
    return Path(arquivo)


def _arquivo_do_pacote() -> Path:
    import sys
    return Path(getattr(sys, "_MEIPASS", ".")) / "ipe" / "pg" / ARQUIVO_PACOTE


def pasta_dos_executaveis(arquivo: Path | None = None, destino: Path | None = None) -> Path:
    """No programa empacotado, os executáveis do PostgreSQL vêm num .tar.gz (o PyInstaller misturava as bibliotecas
    deles com as do programa); na primeira vez, são extraídos para a pasta local do usuário — não para a pasta de
    dados, que pode estar num disco de rede. A pasta leva o tamanho do arquivo no nome: versão nova, extração nova."""
    import tarfile

    import fasteners
    arquivo = Path(arquivo) if arquivo else _arquivo_do_pacote()
    if destino is None:
        import platformdirs
        destino = Path(platformdirs.user_data_dir("DicomViewer", appauthor=False)) / "pgbin"
    alvo = Path(destino) / f"16-{arquivo.stat().st_size}"
    if (alvo / ".ok").exists() and alvo.joinpath(*BIN_NO_ARQUIVO).is_dir():
        return alvo.joinpath(*BIN_NO_ARQUIVO)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    with fasteners.InterProcessLock(str(alvo.parent / ".trava")):
        if (alvo / ".ok").exists() and alvo.joinpath(*BIN_NO_ARQUIVO).is_dir():
            return alvo.joinpath(*BIN_NO_ARQUIVO)
        tmp = alvo.parent / (alvo.name + ".tmp")
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
        t = time.time()
        with tarfile.open(arquivo, "r:gz") as tar:
            try:
                tar.extractall(tmp, filter="data")
            except TypeError:                      # Python sem o filtro
                tar.extractall(tmp)  # noqa: S202 - o arquivo é o do próprio pacote
        shutil.rmtree(alvo, ignore_errors=True)
        tmp.rename(alvo)
        (alvo / ".ok").write_text("ok")
        log.info("PostgreSQL embutido extraído em %.1f s (%s)", time.time() - t, alvo)
    return alvo.joinpath(*BIN_NO_ARQUIVO)


def _apontar_executaveis() -> None:
    """No pacote, o pixeltable-pgserver passa a usar os executáveis extraídos."""
    from ipe.core import runtime as R
    if not R.frozen():
        return
    from pixeltable_pgserver import utils as U
    bin_ = pasta_dos_executaveis()
    if U.POSTGRES_VERSIONS.get(16) != bin_:
        U.POSTGRES_VERSIONS[16] = bin_                 # o mesmo dicionário que o postgres_server usa


def pasta_dos_dados(paths=None) -> Path:
    if paths is None:
        from ipe.core.config import get_paths
        paths = get_paths(criar=False)
    return Path(paths.data) / PASTA


@contextlib.contextmanager
def _ambiente_do_sistema():
    """No programa empacotado do Linux, o LD_LIBRARY_PATH aponta para as bibliotecas do pacote; os executáveis do
    PostgreSQL têm que ver as do sistema (como o terminal da instalação, 0.100.22)."""
    from ipe.core import runtime as R
    if not R.frozen():
        yield
        return
    antes = dict(os.environ)
    try:
        os.environ.clear()
        os.environ.update(R.ambiente_do_sistema(antes))
        yield
    finally:
        os.environ.clear()
        os.environ.update(antes)


def _servidor(pasta: Path):
    pasta = Path(pasta)
    chave = str(pasta.resolve())
    srv = _SERVIDOR.get(chave)
    if srv is not None:
        return srv
    import pixeltable_pgserver as P
    _apontar_executaveis()
    # a pasta já existe (vazia) antes do initdb: no Windows, o initdb criando a pasta falhava ("File exists")
    pasta.mkdir(parents=True, exist_ok=True)
    t = time.time()
    with _ambiente_do_sistema():
        try:
            srv = P.get_server(pasta, cleanup_mode="stop")
        except Exception as e:  # noqa: BLE001
            raise ErroEmbutido(f"o PostgreSQL embutido não ligou: {e}") from e
    log.info("PostgreSQL embutido ligado em %.1f s (%s)", time.time() - t, pasta)
    _SERVIDOR[chave] = srv
    return srv


def _hba(pasta: Path) -> Path:
    return Path(pasta) / "pg_hba.conf"


def _host_com_senha(pasta: Path) -> bool:
    linhas = [ln.split() for ln in _hba(pasta).read_text(encoding="utf-8").splitlines()
              if ln.strip() and not ln.lstrip().startswith("#")]
    return all(ln[-1] == "scram-sha-256" for ln in linhas if ln[0] == "host")


def _trocar_metodo_host(pasta: Path, metodo: str) -> None:
    """As linhas "host" (conexão por rede local) passam a `metodo`; as "local" (arquivo de conexão, só o dono
    acessa a pasta) ficam como estão."""
    p = _hba(pasta)
    novas = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        partes = ln.split()
        if partes and not ln.lstrip().startswith("#") and partes[0] == "host":
            ln = re.sub(r"\S+\s*$", metodo, ln)
        novas.append(ln)
    p.write_text("\n".join(novas) + "\n", encoding="utf-8")


def _recarregar(srv) -> None:
    from pixeltable_pgserver.pgexec import pgexec
    with _ambiente_do_sistema():
        pgexec("pg_ctl", ("-D", str(srv.pgdata), "reload", "-s"), bin_path=srv.bin_path, user=srv.system_user)
    time.sleep(0.5)


def _uri(srv, banco: str, senha: str = "") -> str:
    from sqlalchemy.engine import make_url
    u = make_url(srv.get_uri(database=banco, driver="psycopg"))
    if senha:
        u = u.set(password=senha)
    return u.render_as_string(hide_password=False)


def _conecta(url: str) -> bool:
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool
    try:
        e = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 5})
        with e.connect() as c:
            c.execute(text("SELECT 1"))
        e.dispose()
        return True
    except Exception:  # noqa: BLE001
        return False


def garantir(senha: str = "", pasta: Path | None = None) -> tuple[str, str]:
    """Liga o servidor (se preciso), garante o banco "ipe" e a senha. Devolve (endereço, senha) — a senha é nova
    quando a de antes não existia ou não entrava (quem chama guarda)."""
    pasta = Path(pasta) if pasta else pasta_dos_dados()
    srv = _servidor(pasta)
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool
    if senha and _host_com_senha(pasta) and _conecta(_uri(srv, "postgres", senha)):
        pass                                                     # tudo certo
    else:
        # sem a senha certa: abre por um momento a conexão local sem senha, põe uma senha nova e fecha de novo
        _trocar_metodo_host(pasta, "trust")
        _recarregar(srv)
        senha = secrets.token_urlsafe(24)
        e = create_engine(_uri(srv, "postgres"), poolclass=NullPool)
        try:
            with e.begin() as c:
                c.execute(text("SET password_encryption = 'scram-sha-256'"))
                c.execute(text(f"ALTER USER CURRENT_USER PASSWORD '{senha}'"))
        finally:
            e.dispose()
            _trocar_metodo_host(pasta, "scram-sha-256")
            _recarregar(srv)
    # o banco do Ipê
    e = create_engine(_uri(srv, "postgres", senha), poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with e.connect() as c:
            if not c.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": BANCO}).first():
                c.execute(text(f'CREATE DATABASE "{BANCO}" ENCODING \'UTF8\' TEMPLATE template0'))
    finally:
        e.dispose()
    return _uri(srv, BANCO, senha), senha


def desligar_todos() -> None:
    """Para os testes e para mover a pasta de dados: solta os servidores ligados por este processo."""
    for srv in list(_SERVIDOR.values()):
        with contextlib.suppress(Exception):
            srv.cleanup()
    _SERVIDOR.clear()


def testar_pacote(pasta: Path) -> str:
    """`ipe banco testar-embutido`: liga um servidor numa pasta descartável, cria o banco, lê a versão e desliga.
    É o que o release confere no programa empacotado de cada sistema."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool
    url, _senha = garantir("", pasta)
    e = create_engine(url, poolclass=NullPool)
    try:
        with e.connect() as c:
            versao = str(c.execute(text("SHOW server_version")).scalar())
    finally:
        e.dispose()
        desligar_todos()
    return versao
