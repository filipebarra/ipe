"""Conexão com o banco: SQLite em modo WAL (padrão) ou PostgreSQL (0.100.34).

O PostgreSQL entra no lugar do banco **principal** quando há um endereço configurado (`banco.json` na pasta de
configurações, feito pela janela *Banco de dados*, ou a variável `IPE_DATABASE_URL`). Os outros locais (bancos em
outras pastas, o cache do modo cliente) continuam arquivos SQLite.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Integer, String, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

from ipe.db.models import Base

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------------------------------- PostgreSQL
# O SQLite não confere o tamanho do texto nem tem inteiro de 32 bits; o PostgreSQL tem os dois. Para o mesmo modelo
# valer nos dois (e um valor DICOM comprido não derrubar a importação), no PostgreSQL:
#   String(n) -> VARCHAR sem limite  ·  Integer -> BIGINT (o tamanho do arquivo passa de 2 GB). As chaves primárias
#   continuam SERIAL (o compilador do PostgreSQL decide por elas antes de chegar aqui).
@compiles(String, "postgresql")
def _texto_sem_limite(tipo, compilador, **kw):  # noqa: ANN001
    return "TEXT" if type(tipo).__name__ in ("Text", "UnicodeText") else "VARCHAR"


@compiles(Integer, "postgresql")
def _inteiro_de_64(tipo, compilador, **kw):  # noqa: ANN001
    return "BIGINT"


def _sem_nul_no_texto(dbapi_conn) -> None:
    """O PostgreSQL recusa texto com o caractere nulo (U+0000), que aparece em valores DICOM mal preenchidos; o SQLite
    guarda. Tira o nulo de todo texto que sai para o banco."""
    from psycopg.types import string as S

    class _SemNul(S.StrDumper):
        def dump(self, obj):  # noqa: ANN001
            return super().dump(obj.replace("\x00", "") if "\x00" in obj else obj)

    class _SemNulDesconhecido(S.StrDumperUnknown):
        def dump(self, obj):  # noqa: ANN001
            return super().dump(obj.replace("\x00", "") if "\x00" in obj else obj)

    class _SemNulBinario(S.StrBinaryDumper):
        def dump(self, obj):  # noqa: ANN001
            return super().dump(obj.replace("\x00", "") if "\x00" in obj else obj)

    ad = dbapi_conn.adapters
    ad.register_dumper(str, _SemNulDesconhecido)      # o que o psycopg usa para str sem tipo (o padrão)
    ad.register_dumper(str, _SemNul)
    ad.register_dumper(str, _SemNulBinario)
    ad.register_dumper(str, _SemNulDesconhecido)      # e de novo, para ser o padrão de str


def _numeros_como_no_sqlite(dbapi_conn) -> None:
    """SUM e AVG de inteiros voltam como NUMERIC no PostgreSQL (Decimal no Python), que não vai para o JSON do
    servidor nem soma com float. Como no SQLite: inteiro quando é inteiro, float quando não é."""
    from psycopg.types import numeric as N

    def _py(d):
        try:
            return int(d) if d == d.to_integral_value() else float(d)
        except Exception:  # noqa: BLE001 - NaN, infinito
            return float(d)

    class _Num(N.NumericLoader):
        def load(self, data):  # noqa: ANN001
            return _py(super().load(data))

    class _NumBin(N.NumericBinaryLoader):
        def load(self, data):  # noqa: ANN001
            return _py(super().load(data))

    dbapi_conn.adapters.register_loader("numeric", _Num)
    dbapi_conn.adapters.register_loader("numeric", _NumBin)


def postgres(url: str) -> bool:
    return str(url or "").lower().startswith(("postgresql", "postgres:"))


def mascarar(url: str) -> str:
    """O endereço sem a senha, para log e tela."""
    import re
    return re.sub(r"(://[^:/@]+):[^@]*@", r"\1:***@", str(url or ""))


def _normalizar(url: str) -> str:
    """postgres:// e postgresql:// -> postgresql+psycopg:// (o driver que vai no pacote)."""
    u = str(url or "").strip()
    for velho in ("postgres://", "postgresql://"):
        if u.lower().startswith(velho):
            return "postgresql+psycopg://" + u[len(velho):]
    return u


def endereco_configurado() -> str:
    """O endereço do PostgreSQL para o banco principal, ou "" (SQLite). Variável IPE_DATABASE_URL ou banco.json."""
    import os
    env = os.environ.get("IPE_DATABASE_URL", "").strip()
    if env:
        return _normalizar(env)
    try:
        from ipe.core import banco_config as BC
        return BC.url(BC.ler())
    except Exception:  # noqa: BLE001
        log.exception("banco.json ilegível: fica o SQLite")
        return ""


def _e_o_principal(path) -> bool:
    try:
        from ipe.core.config import get_paths
        return Path(path).expanduser().resolve() == get_paths(criar=False).database.expanduser().resolve()
    except Exception:  # noqa: BLE001
        return False


def _default_sql(col, postgres_ddl: bool = False) -> str | None:
    """Valor inicial da coluna em SQL, para poder acrescentá-la NOT NULL num banco com dados."""
    padrao = getattr(col, "default", None)
    if padrao is not None and not getattr(padrao, "is_callable", False):
        valor = getattr(padrao, "arg", None)
        if isinstance(valor, bool):
            return ("TRUE" if valor else "FALSE") if postgres_ddl else ("1" if valor else "0")
        if isinstance(valor, (int, float)):
            return str(valor)
        if isinstance(valor, str):
            return "'" + valor.replace("'", "''") + "'"
    tipo = str(col.type).upper()
    if any(k in tipo for k in ("CHAR", "TEXT", "CLOB")):
        return "''"
    if "BOOLEAN" in tipo:
        return "FALSE" if postgres_ddl else "0"
    if any(k in tipo for k in ("INT", "REAL", "FLOAT", "NUMERIC", "DECIMAL")):
        return "0"
    return None


class Database:
    def __init__(self, path: Path | str):
        import os
        if isinstance(path, str) and "://" in path:
            url = _normalizar(path)
        else:
            url = endereco_configurado() if _e_o_principal(path) else ""
            if not url:
                url = f"sqlite:///{Path(path)}"
                Path(path).parent.mkdir(parents=True, exist_ok=True)
        if url.startswith("sqlite"):
            kw = {"connect_args": {"timeout": 30}}
        else:
            kw = {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 20, "pool_recycle": 1800,
                  "connect_args": {"connect_timeout": 10, "application_name": "Ipe"}}
            if os.environ.get("IPE_DB_SEM_POOL"):          # testes e ferramentas de uma vez: sem conexões paradas
                from sqlalchemy.pool import NullPool
                kw = {"poolclass": NullPool, "connect_args": kw["connect_args"]}
        self.url = url
        self.engine: Engine = create_engine(url, future=True, **kw)
        if self.engine.dialect.name == "postgresql":
            log.info("Banco: PostgreSQL %s", mascarar(url))

            @event.listens_for(self.engine, "connect")
            def _pg_conexao(dbapi_conn, _):  # noqa: ANN001
                _sem_nul_no_texto(dbapi_conn)
                _numeros_como_no_sqlite(dbapi_conn)
        if self.engine.dialect.name == "sqlite":
            @event.listens_for(self.engine, "connect")
            def _sqlite_pragmas(dbapi_conn, _):  # noqa: ANN001
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")      # leitura e escrita simultâneas
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.close()
        self._criar_e_migrar()
        self._factory = sessionmaker(self.engine, expire_on_commit=False)

    def _criar_e_migrar(self) -> None:
        """Cria as tabelas que faltam e acrescenta as colunas novas. 0.100.34: uma consulta ao catálogo para tudo (no
        PostgreSQL, perguntar tabela por tabela levava 1,5 s a cada abertura do banco)."""
        from sqlalchemy import inspect
        insp = inspect(self.engine)
        existentes = set(insp.get_table_names())
        if any(t.name not in existentes for t in Base.metadata.sorted_tables):
            Base.metadata.create_all(self.engine)
            insp = inspect(self.engine)
        self._add_missing_columns(insp)

    def _add_missing_columns(self, insp=None) -> None:
        """Migração simples: colunas novas em tabelas que já existiam (bancos de versões antigas).

        Vale também para coluna **NOT NULL**: o SQLite aceita acrescentá-la desde que venha com
        um DEFAULT. Antes só as colunas que aceitavam nulo eram acrescentadas, e as outras eram
        puladas **em silêncio** — o banco continuava velho e a tela que usasse a coluna nova
        quebrava na hora de abrir, sem dizer por quê.
        """
        from sqlalchemy import inspect, text
        insp = insp or inspect(self.engine)
        faltando: list[str] = []
        pg = self.engine.dialect.name == "postgresql"
        try:                                     # todas as colunas de todas as tabelas numa consulta só
            todas = {chave[1]: {c["name"] for c in cols} for chave, cols in insp.get_multi_columns().items()}
        except Exception:  # noqa: BLE001 - dialeto sem a consulta única
            todas = None
        with self.engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                if todas is not None:
                    if table.name not in todas:
                        continue
                    have = todas[table.name]
                else:
                    if not insp.has_table(table.name):
                        continue
                    have = {c["name"] for c in insp.get_columns(table.name)}
                for col in table.columns:
                    if col.name in have or col.primary_key:
                        continue
                    ctype = col.type.compile(dialect=self.engine.dialect)
                    sql = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ctype}'
                    if not col.nullable:
                        padrao = _default_sql(col, postgres_ddl=pg)
                        if padrao is None:      # sem valor inicial, entra aceitando nulo
                            log.warning("Coluna %s.%s entrou aceitando nulo: sem valor padrão",
                                        table.name, col.name)
                        else:
                            sql += f" NOT NULL DEFAULT {padrao}"
                    try:
                        # no PostgreSQL um erro estraga a transação inteira: cada coluna no seu ponto de retorno
                        with conn.begin_nested():
                            conn.execute(text(sql))
                        faltando.append(f"{table.name}.{col.name}")
                    except Exception:  # noqa: BLE001
                        log.exception("Não consegui acrescentar %s.%s", table.name, col.name)
        if faltando:
            log.info("Banco atualizado: %d coluna(s) nova(s) — %s", len(faltando),
                     ", ".join(faltando[:12]))

    @property
    def e_postgres(self) -> bool:
        return self.engine.dialect.name == "postgresql"

    def descricao(self) -> str:
        """"PostgreSQL usuario@host:porta/banco" ou o caminho do arquivo SQLite."""
        if self.e_postgres:
            u = self.engine.url
            return f"PostgreSQL {u.username or ''}@{u.host or 'localhost'}:{u.port or 5432}/{u.database or ''}"
        return str(self.engine.url.database or "")

    def close(self) -> None:
        """Fecha as conexões (usado ao trocar de local)."""
        try:
            self.engine.dispose()
        except Exception:  # noqa: BLE001
            pass

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self._factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()
