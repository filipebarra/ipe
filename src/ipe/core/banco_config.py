"""Onde fica o banco principal: arquivo SQLite (padrão) ou servidor PostgreSQL (0.100.34).

`banco.json`, na pasta de configurações deste computador (não no settings.json: a conexão é da máquina, não da
pessoa que entrou):

    {"tipo": "postgresql", "host": "localhost", "porta": 5432, "banco": "ipe", "usuario": "ipe",
     "senha": "<cifrada por core.segredos>", "ssl": "prefer"}
    {"tipo": "embutido", "senha": "<cifrada>"}       # 0.100.35: o PostgreSQL que vem dentro do Ipê (core/pg_embutido)

A variável `IPE_DATABASE_URL` (postgresql://usuario:senha@host:5432/banco) passa na frente — para servidores
montados por roteiro.

Também aqui: `testar` (conecta e diz a versão) e `copiar` (o banco SQLite inteiro para um PostgreSQL vazio, tabela a
tabela, com a contagem conferida no fim).
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
    """Grava cifrando a senha. `cfg` vazio ou tipo "sqlite" volta para o arquivo."""
    from ipe.core import segredos as SG
    p = Path(caminho) if caminho else arquivo()
    p.parent.mkdir(parents=True, exist_ok=True)
    d = dict(cfg or {})
    emb = d.pop("senha_embutido", "") or ""                  # a senha do embutido sobrevive à troca de tipo
    if d.get("tipo") == "embutido":
        d = {"tipo": "embutido", "senha": SG.guardar(d.get("senha") or emb)}
        emb = ""
    elif d.get("tipo") != "postgresql":
        d = {"tipo": "sqlite"}
    else:
        d["porta"] = int(d.get("porta") or 5432)
        d["ssl"] = d.get("ssl") if d.get("ssl") in SSL_MODOS else "prefer"
        d["senha"] = SG.guardar(d.get("senha") or "")
    if emb:
        d["senha_embutido"] = SG.guardar(SG.abrir_ou_vazio(emb) if SG.cifrado(emb) else emb)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)
    return p


def url(cfg: dict, senha: str | None = None) -> str:
    """O endereço do SQLAlchemy, ou "" para SQLite. `senha` em claro passa na frente da gravada (teste na tela).
    No embutido, liga o servidor (se preciso) e guarda a senha nova quando ela muda."""
    if cfg and cfg.get("tipo") == "embutido":
        return url_embutido(cfg)
    if not cfg or cfg.get("tipo") != "postgresql":
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
    """A senha do embutido guardada (em claro), ou "" — vale mesmo com outro tipo escolhido agora."""
    from ipe.core import segredos as SG
    cfg = ler(caminho)
    return SG.abrir_ou_vazio(cfg.get("senha_embutido") or (cfg.get("senha") if cfg.get("tipo") == "embutido" else "")
                             or "")


def url_embutido(cfg: dict | None = None, caminho: Path | None = None, pasta: Path | None = None) -> str:
    """Liga o embutido e devolve o endereço; guarda a senha quando ela muda (o tipo escolhido não muda)."""
    from ipe.core import pg_embutido as PE
    antes = senha_embutido(caminho)
    endereco, senha = PE.garantir(antes, pasta)
    if senha != antes:
        atual = ler(caminho)
        if atual.get("tipo") == "embutido":
            gravar({"tipo": "embutido", "senha": senha}, caminho)
        else:
            gravar(dict(atual, senha_embutido=senha, senha=_abrir(atual.get("senha"))), caminho)
    return endereco


def _abrir(v) -> str:
    from ipe.core import segredos as SG
    return SG.abrir_ou_vazio(v or "")


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


def copiar(origem_sqlite: Path, destino: str, andou=None, apagar_destino: bool = False) -> dict[str, int]:
    """Copia todas as tabelas do banco SQLite para o PostgreSQL. O destino tem que estar **vazio** (ou
    `apagar_destino`, que esvazia as tabelas do Ipê antes). Confere a contagem de cada tabela no fim.
    `andou(tabela, feitas, total_da_tabela)`. Devolve {tabela: linhas}."""
    from sqlalchemy import create_engine, func, select, text
    from sqlalchemy.pool import NullPool

    from ipe.db.models import Base
    from ipe.db.session import Database
    origem_sqlite = Path(origem_sqlite)
    if not origem_sqlite.is_file():
        raise ErroBanco(f"banco de origem não encontrado: {origem_sqlite}")
    src = create_engine(f"sqlite:///{origem_sqlite}", poolclass=NullPool)
    Database(f"sqlite:///{origem_sqlite}").close()          # o de origem com as colunas da versão atual
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
                    cd.execute(t.insert(), [dict(r._mapping) for r in linhas])
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
