"""0.100.34: o banco principal no PostgreSQL (opcional; o padrão continua o SQLite).

Os testes de conexão de verdade rodam quando há um PostgreSQL em IPE_TEST_PG
(postgresql://usuario:senha@host:5432/banco); sem ele, ficam de fora. A suíte inteira também roda contra o PostgreSQL
com essa variável (conftest: um esquema novo por teste).
"""
import json
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateTable

from ipe.core import banco_config as BC
from ipe.db import session as SS

PG = os.environ.get("IPE_TEST_PG", "").strip()
_ENDERECO_DE_VERDADE = SS.endereco_configurado                 # guardada antes de o conftest trocar
com_pg = pytest.mark.skipif(not PG, reason="sem PostgreSQL (IPE_TEST_PG)")


def test_tipos_no_postgres():
    from ipe.db.models import Instance, Patient
    ddl = str(CreateTable(Instance.__table__).compile(dialect=postgresql.dialect()))
    assert "file_size BIGINT" in ddl and "id SERIAL" in ddl          # tamanho de arquivo > 2 GB; chave SERIAL
    ddl = str(CreateTable(Patient.__table__).compile(dialect=postgresql.dialect()))
    assert "name VARCHAR " in ddl or "name VARCHAR\n" in ddl or "name VARCHAR," in ddl
    assert "VARCHAR(" not in ddl                                      # sem limite: DICOM comprido não derruba


def test_valor_padrao_de_coluna_nova():
    from sqlalchemy import Boolean, Column
    c = Column("x", Boolean, default=True, nullable=False)
    assert SS._default_sql(c) == "1" and SS._default_sql(c, postgres_ddl=True) == "TRUE"
    c = Column("y", Boolean, nullable=False)
    assert SS._default_sql(c, postgres_ddl=True) == "FALSE"


def test_endereco_e_senha_cifrada(tmp_path):
    arq = tmp_path / "banco.json"
    cfg = {"tipo": "postgresql", "host": "db.exemplo", "porta": 6543, "banco": "ipê", "usuario": "ana",
           "senha": "s3nh@:/x", "ssl": "require"}
    BC.gravar(cfg, arq)
    gravado = json.loads(arq.read_text(encoding="utf-8"))
    assert gravado["senha"] != "s3nh@:/x" and gravado["senha"]                  # cifrada
    u = BC.url(BC.ler(arq))
    assert u == "postgresql+psycopg://ana:s3nh%40%3A%2Fx@db.exemplo:6543/ip%C3%AA?sslmode=require"
    assert SS.mascarar(u) == "postgresql+psycopg://ana:***@db.exemplo:6543/ip%C3%AA?sslmode=require"
    from sqlalchemy.engine import make_url
    m = make_url(u)
    assert m.password == "s3nh@:/x" and m.database == "ipê"
    BC.gravar({"tipo": "sqlite", "senha": "x"}, arq)
    assert BC.ler(arq) == {"tipo": "sqlite"} and BC.url(BC.ler(arq)) == ""
    assert SS._normalizar("postgres://a@b/c") == "postgresql+psycopg://a@b/c"


def test_so_o_banco_principal_vai_para_o_postgres(env, tmp_path, monkeypatch):
    paths, _db, _repo = env
    monkeypatch.setattr(SS, "endereco_configurado", lambda: "postgresql+psycopg://u:p@h/b")
    assert SS._e_o_principal(paths.database) and not SS._e_o_principal(tmp_path / "outro.sqlite")
    outro = SS.Database(tmp_path / "outro" / "x.sqlite")                       # outro local: SQLite
    assert not outro.e_postgres and outro.descricao().endswith("x.sqlite")
    outro.close()


def test_abrir_um_banco_nao_cria_a_pasta_de_dados_escolhida(tmp_path, monkeypatch):
    """Saber se o banco é o principal não cria pastas: a pasta de dados escolhida pode estar num disco de rede fora do
    ar (o teste antigo deixava uma pasta "D:\\Banco" no Linux)."""
    from ipe.core.config import Settings, get_paths
    monkeypatch.setenv("DICOMVIEWER_HOME", str(tmp_path / "h"))
    p = get_paths()
    s = Settings(p.settings_file)
    longe = tmp_path / "rede_fora_do_ar" / "Banco"
    s.set("data_dir", str(longe))
    s.save()
    assert get_paths(criar=False).data == longe and not longe.exists()
    db = SS.Database(tmp_path / "outro.sqlite")
    db.close()
    assert not longe.exists()


def test_variavel_passa_na_frente_do_arquivo(tmp_path, monkeypatch):
    monkeypatch.setenv("DICOMVIEWER_HOME", str(tmp_path / "h"))
    real = _ENDERECO_DE_VERDADE                                  # a suíte com PG troca a do módulo
    monkeypatch.delenv("IPE_DATABASE_URL", raising=False)
    assert real() == ""                                          # sem banco.json: SQLite
    BC.gravar({"tipo": "postgresql", "host": "h", "banco": "b", "usuario": "u", "senha": "p"})
    assert real() == "postgresql+psycopg://u:p@h:5432/b?sslmode=prefer"
    monkeypatch.setenv("IPE_DATABASE_URL", "postgres://x@y/z")
    assert real() == "postgresql+psycopg://x@y/z"


def test_linha_de_comando(env, capsys, monkeypatch):
    from ipe.__main__ import main
    monkeypatch.delenv("IPE_DATABASE_URL", raising=False)
    assert main(["banco", "sqlite"]) == 0
    assert BC.ler() == {"tipo": "sqlite"}
    monkeypatch.setenv("IPE_DB_SENHA", "errada")
    rc = main(["banco", "postgres", "--host", "127.0.0.1", "--porta", "1", "--usuario", "x"])
    assert rc == 1 and "Não conectou" in capsys.readouterr().err
    assert BC.ler() == {"tipo": "sqlite"}                                          # não grava o que não conecta


def test_janela(env, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.ui.banco_dialog import BancoDialog
    QApplication.instance() or QApplication([])
    paths, db, _repo = env
    d = BancoDialog(None, paths, db)
    assert d.r_sqlite.isChecked() or d.r_pg.isChecked()
    d.r_pg.setChecked(True)
    assert d.grupo.isEnabled()
    d.host.setText("127.0.0.1")
    d.porta.setValue(1)
    d.usuario.setText("ana")
    d.senha.setText("x")
    t = d.testar()
    assert not t.ok and "Não conectou" in d.estado.text()
    assert d.cfg()["porta"] == 1 and d.url().startswith("postgresql+psycopg://ana:x@127.0.0.1:1/")
    d.r_sqlite.setChecked(True)
    assert not d.grupo.isEnabled()
    d.aceitar()
    assert BC.ler() == {"tipo": "sqlite"}
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    d2 = BancoDialog(None, paths, db)
    d2.r_pg.setChecked(True)
    d2.porta.setValue(1)
    d2.aceitar()                                                                   # não conectou e disse não
    assert BC.ler() == {"tipo": "sqlite"} and d2.result() == 0


def test_item_no_menu_configuracoes():
    from ipe.ui import configuracoes as CFG
    itens = dict((n, i) for n, i in CFG.CATALOGO)["Banco de dados"]
    assert ("Servidor de banco de dados (PostgreSQL)…", "f:abrir_banco_postgres", "configure") in itens


# ---------------------------------------------------------------------------------------- com um PostgreSQL
@pytest.fixture()
def esquema_vazio():
    nome = "c_" + uuid.uuid4().hex[:10]
    base = PG.replace("postgresql://", "postgresql+psycopg://", 1)
    eng = create_engine(base, poolclass=NullPool)
    with eng.begin() as c:
        c.execute(text(f'CREATE SCHEMA "{nome}"'))
    sep = "&" if "?" in PG else "?"
    yield f"{PG}{sep}options=-csearch_path%3D{nome}"
    with eng.begin() as c:
        c.execute(text(f'DROP SCHEMA "{nome}" CASCADE'))
    eng.dispose()


@com_pg
def test_copiar_do_sqlite_para_o_postgres(tmp_path, sample_dir, esquema_vazio, monkeypatch):
    from ipe.db.repository import Repository
    from ipe.importer.scanner import Importer
    monkeypatch.setenv("IPE_DB_SEM_POOL", "1")
    origem = tmp_path / "origem.sqlite"
    db = SS.Database(f"sqlite:///{origem}")
    Importer(db, tmp_path / "Storage").import_paths([sample_dir])
    repo = Repository(db)
    uid = repo.search_studies()[0].study_uid
    repo.add_comment("study", uid, "comentário com nulo \x00 no meio")
    db.close()
    t = BC.testar(esquema_vazio)
    assert t.ok and t.vazio and t.versao
    passos = []
    feito = BC.copiar(origem, esquema_vazio, lambda tb, n, tot: passos.append((tb, n, tot)))
    assert feito["instance"] > 0 and feito["study"] == 8 and ("study", 8, 8) in passos
    pg = SS.Database(esquema_vazio)
    try:
        r = Repository(pg)
        assert len(r.search_studies()) == 8
        assert uid in {s.study_uid for s in r.search_studies()}
        # o nulo do SQLite não passou para o PostgreSQL
        with pg.engine.connect() as c:
            assert c.execute(text("SELECT text FROM comment")).scalar() == "comentário com nulo  no meio"
        # a sequência continua depois do maior id copiado: dá para gravar coisa nova
        r.add_comment("study", uid, "depois da cópia")
        with pg.session() as s:
            from ipe.db.models import Tag
            s.add(Tag(name="nova"))
        with pg.engine.connect() as c:
            assert c.execute(text("SELECT SUM(file_size) FROM instance")).scalar() > 0      # int, não Decimal
            assert isinstance(c.execute(text("SELECT SUM(file_size) FROM instance")).scalar(), int)
            assert c.execute(text("SELECT AVG(rows) FROM instance")).scalar().__class__ in (int, float)
    finally:
        pg.close()
    assert not BC.testar(esquema_vazio).vazio
    with pytest.raises(BC.ErroBanco, match="já tem dados"):
        BC.copiar(origem, esquema_vazio)
    BC.copiar(origem, esquema_vazio, apagar_destino=True)


@com_pg
def test_texto_com_nulo_e_valor_comprido(esquema_vazio, monkeypatch, tmp_path):
    from ipe.db.models import Patient
    monkeypatch.setenv("IPE_DB_SEM_POOL", "1")
    db = SS.Database(esquema_vazio)
    try:
        with db.session() as s:
            s.add(Patient(patient_id="P\x001", name="EXEMPLO^" + "X" * 400, birth_date="19700101000000"))
        with db.session() as s:
            p = s.query(Patient).one()
            assert p.patient_id == "P1" and len(p.name) == 408 and p.birth_date == "19700101000000"
    finally:
        db.close()
