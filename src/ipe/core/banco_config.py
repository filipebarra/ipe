"""Onde fica o banco principal: o PostgreSQL que vem com o Ipê (padrão e, desde a 0.100.36, o banco único) ou um
servidor PostgreSQL próprio (0.100.34). O SQLite só é lido para migrar os bancos antigos.

`banco.json`, na pasta de configurações deste computador (não no settings.json: a conexão é da máquina, não da
pessoa que entrou):

    {"tipo": "postgresql", "host": "localhost", "porta": 5432, "banco": "ipe", "usuario": "ipe",
     "senha": "<cifrada por core.segredos>", "ssl": "prefer"}
    {"tipo": "embutido"}       # o PostgreSQL que vem com o Ipê, na pasta de dados (core/pg_embutido); o padrão

A variável `IPE_DATABASE_URL` (postgresql://usuario:senha@host:5432/banco) passa na frente — para servidores
montados por roteiro.

Também aqui: `testar` (conecta e diz a versão) e `copiar` (o banco inteiro — o SQLite antigo ou outro PostgreSQL —
para um PostgreSQL vazio, tabela a tabela, com a contagem conferida no fim).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

log = logging.getLogger(__name__)

ARQUIVO = "banco.json"
SSL_MODOS = ("disable", "prefer", "require", "verify-full")
LOTE = 2000


class ErroBanco(Exception):
    pass


def arquivo() -> Path:
    from ipe.core.config import get_paths
    return get_paths(criar=False).config / ARQUIVO


def ler(caminho: Path | None = None) -> dict:
    p = Path(caminho) if caminho else arquivo()
    if not p.is_file():
        return {}
    d = json.loads(p.read_text(encoding="utf-8") or "{}")
    return d if isinstance(d, dict) else {}


def gravar(cfg: dict, caminho: Path | None = None) -> Path:
    """Grava cifrando a senha. Tipo "postgresql" (servidor próprio) ou "embutido" (o padrão; qualquer outro valor,
    como o "sqlite" de antes da 0.100.36, vira "embutido"). A senha do embutido fica com os dados (pg_embutido)."""
    from ipe.core import segredos as SG
    p = Path(caminho) if caminho else arquivo()
    p.parent.mkdir(parents=True, exist_ok=True)
    d = dict(cfg or {})
    if d.get("tipo") != "postgresql":
        d = {"tipo": "embutido"}
    else:
        d.pop("senha_embutido", None)
        d["porta"] = int(d.get("porta") or 5432)
        d["ssl"] = d.get("ssl") if d.get("ssl") in SSL_MODOS else "prefer"
        d["senha"] = SG.guardar(d.get("senha") or "")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)
    return p


def proprio(cfg: dict | None) -> bool:
    """O banco principal está num servidor PostgreSQL próprio (e não no que vem com o Ipê)?"""
    return bool(cfg) and cfg.get("tipo") == "postgresql"


def url(cfg: dict, senha: str | None = None) -> str:
    """O endereço do servidor próprio, ou "" (o banco é o PostgreSQL que vem com o Ipê, na pasta de dados).
    `senha` em claro passa na frente da gravada (teste na tela)."""
    if not proprio(cfg):
        return ""
    from ipe.core import segredos as SG
    host = str(cfg.get("host") or "localhost").strip()
    banco = str(cfg.get("banco") or "ipe").strip()
    usuario = str(cfg.get("usuario") or "").strip()
    if senha is None:
        senha = SG.abrir(cfg.get("senha") or "")
    cred = quote(usuario, safe="")
    if senha:
        cred += ":" + quote(senha, safe="")
    alvo = f"{host}:{int(cfg.get('porta') or 5432)}/{quote(banco, safe='')}"
    ssl = cfg.get("ssl") if cfg.get("ssl") in SSL_MODOS else "prefer"
    return f"postgresql+psycopg://{cred + '@' if cred else ''}{alvo}?sslmode={ssl}"


def senha_embutido(caminho: Path | None = None) -> str:
    """A senha do embutido que a 0.100.35 guardava no banco.json (agora ela fica com os dados)."""
    from ipe.core import segredos as SG
    cfg = ler(caminho)
    return SG.abrir_ou_vazio(cfg.get("senha_embutido") or (cfg.get("senha") if cfg.get("tipo") == "embutido" else "")
                             or "")


def url_embutido(pasta: Path | None = None) -> str:
    """Liga o PostgreSQL que vem com o Ipê (o da pasta de dados, se não disser outra) e devolve o endereço."""
    from ipe.core import pg_embutido as PE
    return PE.endereco_da_pasta(Path(pasta) if pasta else PE.pasta_dos_dados())


def origem_atual(database) -> Path | str:
    """De onde copiar "o banco deste computador": o arquivo SQLite que ainda não foi migrado, ou o endereço do
    PostgreSQL em uso agora (o do Ipê ou o servidor próprio)."""
    from ipe.db.session import endereco_para, precisa_migrar
    return Path(database) if precisa_migrar(database) else endereco_para(database)


def mesmo_banco(a: str, b: str) -> bool:
    from sqlalchemy.engine import make_url

    from ipe.db.session import _normalizar
    try:
        ua, ub = make_url(_normalizar(a)), make_url(_normalizar(b))
    except Exception:  # noqa: BLE001
        return False
    return (ua.host, ua.port, ua.database, dict(ua.query).get("host")) == \
        (ub.host, ub.port, ub.database, dict(ub.query).get("host"))


@dataclass
class Teste:
    ok: bool
    versao: str = ""
    vazio: bool = True
    tabelas: int = 0
    erro: str = ""


def testar(endereco: str, timeout: int = 8) -> Teste:
    """Conecta e diz a versão do servidor e se o banco já tem as tabelas do Ipê."""
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.pool import NullPool

    from ipe.db.models import Base
    from ipe.db.session import _normalizar
    try:
        eng = create_engine(_normalizar(endereco), poolclass=NullPool,
                            connect_args={"connect_timeout": timeout, "application_name": "Ipe (teste)"})
        with eng.connect() as c:
            versao = str(c.execute(text("SHOW server_version")).scalar() or "")
            nossas = {t.name for t in Base.metadata.sorted_tables}
            tem = [t for t in inspect(c).get_table_names() if t in nossas]
            vazio = True
            if "study" in tem:
                vazio = not c.execute(text('SELECT 1 FROM "study" LIMIT 1')).first()
        eng.dispose()
        return Teste(True, versao, vazio, len(tem))
    except Exception as e:  # noqa: BLE001
        msg = str(getattr(e, "orig", None) or e).strip().splitlines()
        return Teste(False, erro=(msg[0] if msg else type(e).__name__)[:300])


def _valor_padrao(col):
    """O valor de uma coluna NOT NULL que veio vazia do banco antigo (o SQLite aceitava): o padrão da coluna ou um
    valor neutro pelo tipo."""
    import datetime as _dt
    d = col.default
    if d is not None and getattr(d, "is_scalar", False):
        return d.arg
    if d is not None and getattr(d, "is_callable", False):
        try:
            return d.arg(None)
        except Exception:  # noqa: BLE001
            pass
    try:
        tipo = col.type.python_type
    except NotImplementedError:
        return ""
    if tipo is _dt.datetime:
        return _dt.datetime.now()
    if tipo is _dt.date:
        return _dt.date.today()
    if tipo is bool:
        return False
    if tipo in (int, float):
        return tipo(0)
    if tipo in (dict, list):
        return tipo()
    return ""


def _sem_nulo_proibido(t, linha: dict) -> dict:
    for col in t.columns:
        if linha.get(col.name) is None and not col.nullable and not col.primary_key:
            linha[col.name] = _valor_padrao(col)
    return linha


def copiar(origem, destino: str, andou=None, apagar_destino: bool = False) -> dict[str, int]:
    """Copia todas as tabelas de um banco para um PostgreSQL. `origem`: o arquivo SQLite antigo (Path) ou o endereço
    de outro PostgreSQL (str). O destino tem que estar **vazio** (ou `apagar_destino`, que esvazia as tabelas do Ipê
    antes). Confere a contagem de cada tabela no fim. `andou(tabela, feitas, total_da_tabela)`. Devolve
    {tabela: linhas}."""
    from sqlalchemy import create_engine, func, select, text
    from sqlalchemy.pool import NullPool

    from ipe.db.models import Base
    from ipe.db.session import Database, _normalizar, preparar_sqlite_antigo
    if isinstance(origem, str) and "://" in origem:
        src = create_engine(_normalizar(origem), poolclass=NullPool)
    else:
        origem = Path(origem)
        if not origem.is_file():
            raise ErroBanco(f"banco de origem não encontrado: {origem}")
        preparar_sqlite_antigo(origem)                       # o de origem com as colunas da versão atual
        src = create_engine(f"sqlite:///{origem}", poolclass=NullPool)
    dst_db = Database(destino)                               # cria as tabelas no PostgreSQL
    dst = dst_db.engine
    if dst.dialect.name != "postgresql":
        raise ErroBanco("o destino não é um PostgreSQL")
    tabelas = list(Base.metadata.sorted_tables)
    with dst.begin() as c:
        cheias = [t.name for t in tabelas if c.execute(select(func.count()).select_from(t)).scalar()]
        if cheias and not apagar_destino:
            raise ErroBanco("o banco de destino já tem dados (" + ", ".join(cheias[:5]) + "); "
                            "use um banco vazio")
        if cheias:
            c.execute(text("TRUNCATE " + ", ".join(f'"{t.name}"' for t in tabelas) + " RESTART IDENTITY CASCADE"))
    feito: dict[str, int] = {}
    for t in tabelas:
        with src.connect() as cs:
            total = cs.execute(select(func.count()).select_from(t)).scalar() or 0
            n = 0
            if andou:
                andou(t.name, 0, total)
            resultado = cs.execution_options(stream_results=True).execute(select(t))
            while True:
                linhas = resultado.fetchmany(LOTE)
                if not linhas:
                    break
                with dst.begin() as cd:
                    cd.execute(t.insert(), [_sem_nulo_proibido(t, dict(r._mapping)) for r in linhas])
                n += len(linhas)
                if andou:
                    andou(t.name, n, total)
        feito[t.name] = n
    # as chaves primárias: a sequência continua depois do maior id copiado
    with dst.begin() as c:
        for t in tabelas:
            pk = list(t.primary_key.columns)
            if len(pk) == 1 and pk[0].autoincrement in (True, "auto") and str(pk[0].type).upper().startswith("INT"):
                c.execute(text(f"SELECT setval(pg_get_serial_sequence('\"{t.name}\"', '{pk[0].name}'), "
                               f"COALESCE((SELECT MAX(\"{pk[0].name}\") FROM \"{t.name}\"), 0) + 1, false)"))
    with dst.connect() as c:
        diferentes = [f"{t.name} ({feito[t.name]} → {c.execute(select(func.count()).select_from(t)).scalar()})"
                      for t in tabelas
                      if c.execute(select(func.count()).select_from(t)).scalar() != feito[t.name]]
    src.dispose()
    dst_db.close()
    if diferentes:
        raise ErroBanco("contagem diferente depois da cópia: " + ", ".join(diferentes))
    return feito
