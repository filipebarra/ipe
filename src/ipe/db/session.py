"""Conexão com o banco (SQLite em modo WAL)."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ipe.db.models import Base

log = logging.getLogger(__name__)


def _default_sql(col) -> str | None:
    """Valor inicial da coluna em SQL, para poder acrescentá-la NOT NULL num banco com dados."""
    padrao = getattr(col, "default", None)
    if padrao is not None and not getattr(padrao, "is_callable", False):
        valor = getattr(padrao, "arg", None)
        if isinstance(valor, bool):
            return "1" if valor else "0"
        if isinstance(valor, (int, float)):
            return str(valor)
        if isinstance(valor, str):
            return "'" + valor.replace("'", "''") + "'"
    tipo = str(col.type).upper()
    if any(k in tipo for k in ("CHAR", "TEXT", "CLOB")):
        return "''"
    if any(k in tipo for k in ("INT", "REAL", "FLOAT", "NUMERIC", "DECIMAL", "BOOLEAN")):
        return "0"
    return None


class Database:
    def __init__(self, path: Path | str):
        url = path if isinstance(path, str) and "://" in path else f"sqlite:///{Path(path)}"
        if url.startswith("sqlite:///") and not isinstance(path, str):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        kw = {"connect_args": {"timeout": 30}} if url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(url, future=True, **kw)
        if self.engine.dialect.name == "sqlite":
            @event.listens_for(self.engine, "connect")
            def _sqlite_pragmas(dbapi_conn, _):  # noqa: ANN001
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")      # leitura e escrita simultâneas
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.close()
        Base.metadata.create_all(self.engine)
        self._add_missing_columns()
        self._factory = sessionmaker(self.engine, expire_on_commit=False)

    def _add_missing_columns(self) -> None:
        """Migração simples: colunas novas em tabelas que já existiam (bancos de versões antigas).

        Vale também para coluna **NOT NULL**: o SQLite aceita acrescentá-la desde que venha com
        um DEFAULT. Antes só as colunas que aceitavam nulo eram acrescentadas, e as outras eram
        puladas **em silêncio** — o banco continuava velho e a tela que usasse a coluna nova
        quebrava na hora de abrir, sem dizer por quê.
        """
        from sqlalchemy import inspect, text
        insp = inspect(self.engine)
        faltando: list[str] = []
        with self.engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                if not insp.has_table(table.name):
                    continue
                have = {c["name"] for c in insp.get_columns(table.name)}
                for col in table.columns:
                    if col.name in have or col.primary_key:
                        continue
                    ctype = col.type.compile(dialect=self.engine.dialect)
                    sql = f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {ctype}'
                    if not col.nullable:
                        padrao = _default_sql(col)
                        if padrao is None:      # sem valor inicial, entra aceitando nulo
                            log.warning("Coluna %s.%s entrou aceitando nulo: sem valor padrão",
                                        table.name, col.name)
                        else:
                            sql += f" NOT NULL DEFAULT {padrao}"
                    try:
                        conn.execute(text(sql))
                        faltando.append(f"{table.name}.{col.name}")
                    except Exception:  # noqa: BLE001
                        log.exception("Não consegui acrescentar %s.%s", table.name, col.name)
        if faltando:
            log.info("Banco atualizado: %d coluna(s) nova(s) — %s", len(faltando),
                     ", ".join(faltando[:12]))

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
