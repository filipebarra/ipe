"""O banco no PostgreSQL: servidor próprio (0.100.34), o que vem com o Ipê (0.100.35) e, desde a 0.100.36, o banco
único — o SQLite antigo é migrado na primeira abertura.

A suíte usa um PostgreSQL só (IPE_TEST_PG, ou o do Ipê numa pasta temporária) com um esquema por banco (conftest).
Os testes com `pg_de_verdade` ligam o PostgreSQL do Ipê de verdade numa pasta do teste.
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
    BC.gravar({"tipo": "sqlite", "senha": "x"}, arq)                  # 0.100.36: não há mais SQLite
    assert BC.ler(arq) == {"tipo": "embutido"} and BC.url(BC.ler(arq)) == "" and not BC.proprio(BC.ler(arq))
    assert SS._normalizar("postgres://a@b/c") == "postgresql+psycopg://a@b/c"


def test_o_sqlite_nao_e_mais_um_banco(tmp_path):
    with pytest.raises(ValueError, match="PostgreSQL"):
        SS.Database(f"sqlite:///{tmp_path / 'x.sqlite'}")


def test_cada_nome_de_banco_e_um_banco_na_pasta():
    assert PE.nome_do_banco("dicomviewer.sqlite") == "ipe"
    assert PE.nome_do_banco("cache.sqlite") == "ipe_cache" and PE.nome_do_banco("diag.sqlite") == "ipe_diag"


def test_so_o_banco_principal_vai_para_o_servidor_proprio(env, tmp_path, monkeypatch):
    paths, _db, _repo = env
    monkeypatch.setattr(SS, "endereco_configurado", lambda: "postgresql+psycopg://u:p@h/b")
    assert SS._e_o_principal(paths.database) and not SS._e_o_principal(tmp_path / "outro.sqlite")
    outro = SS.Database(tmp_path / "outro" / "dicomviewer.sqlite")             # outro local: o PostgreSQL da pasta
    assert outro.e_postgres and outro.embutido and outro.descricao().startswith("PostgreSQL do Ipê")
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
    monkeypatch.delenv("IPE_DATABASE_URL", raising=False)
    assert SS.endereco_configurado() == ""                        # sem banco.json: o PostgreSQL do Ipê
    BC.gravar({"tipo": "postgresql", "host": "h", "banco": "b", "usuario": "u", "senha": "p"})
    assert SS.endereco_configurado() == "postgresql+psycopg://u:p@h:5432/b?sslmode=prefer"
    monkeypatch.setenv("IPE_DATABASE_URL", "postgres://x@y/z")
    assert SS.endereco_configurado() == "postgresql+psycopg://x@y/z"


def test_linha_de_comando(env, capsys, monkeypatch):
    from ipe.__main__ import main
    monkeypatch.delenv("IPE_DATABASE_URL", raising=False)
    with pytest.raises(SystemExit):
        main(["banco", "sqlite"])                                                  # não existe mais
    capsys.readouterr()
    assert main(["banco", "status"]) == 0 and "PostgreSQL do Ipê" in capsys.readouterr().out
    monkeypatch.setenv("IPE_DB_SENHA", "errada")
    rc = main(["banco", "postgres", "--host", "127.0.0.1", "--porta", "1", "--usuario", "x"])
    assert rc == 1 and "Não conectou" in capsys.readouterr().err
    assert not BC.proprio(BC.ler())                                                # não grava o que não conecta


def test_janela(env, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.ui.banco_dialog import BancoDialog
    QApplication.instance() or QApplication([])
    paths, db, _repo = env
    d = BancoDialog(None, paths, db)
    assert d.r_emb.isChecked() and not hasattr(d, "r_sqlite") and not d.grupo.isEnabled()
    d.r_pg.setChecked(True)
    assert d.grupo.isEnabled()
    d.host.setText("127.0.0.1")
    d.porta.setValue(1)
    d.usuario.setText("ana")
    d.senha.setText("x")
    t = d.testar()
    assert not t.ok and "Não conectou" in d.estado.text()
    assert d.cfg()["porta"] == 1 and d.url().startswith("postgresql+psycopg://ana:x@127.0.0.1:1/")
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    d.aceitar()                                                                    # não conectou e disse não
    assert not BC.proprio(BC.ler()) and d.result() == 0


# ---------------------------------------------------------------------------------- a migração do SQLite antigo
def _sqlite_antigo_de(db, arquivo):
    """Um arquivo SQLite como o das versões até a 0.100.35, com o conteúdo do banco `db`."""
    from sqlalchemy import select

    from ipe.db.models import Base
    eng = create_engine(f"sqlite:///{arquivo}", poolclass=NullPool)
    Base.metadata.create_all(eng)
    with db.engine.connect() as cs, eng.begin() as cd:
        for t in Base.metadata.sorted_tables:
            linhas = [dict(r._mapping) for r in cs.execute(select(t))]
            if linhas:
                cd.execute(t.insert(), linhas)
    eng.dispose()


@pytest.fixture()
def banco_antigo(tmp_path, sample_dir):
    """Exames de exemplo num SQLite antigo, no lugar do banco principal de uma pasta de dados."""
    from ipe.db.repository import Repository
    from ipe.importer.scanner import Importer
    rascunho = SS.Database(tmp_path / "rascunho" / "dicomviewer.sqlite")
    Importer(rascunho, tmp_path / "rascunho" / "Storage").import_paths([sample_dir])
    repo = Repository(rascunho)
    uid = repo.search_studies()[0].study_uid
    repo.add_comment("study", uid, "comentário com nulo \x00 no meio")
    dados = tmp_path / "dados"
    dados.mkdir()
    _sqlite_antigo_de(rascunho, dados / "dicomviewer.sqlite")
    rascunho.close()
    return dados / "dicomviewer.sqlite", uid


def test_o_sqlite_antigo_e_migrado_ao_abrir(banco_antigo):
    from ipe.db.repository import Repository
    arquivo, uid = banco_antigo
    assert SS.precisa_migrar(arquivo)
    db = SS.Database(arquivo)
    try:
        r = Repository(db)
        assert len(r.search_studies()) == 8 and uid in {s.study_uid for s in r.search_studies()}
        r.add_comment("study", uid, "depois da migração")              # a sequência continua depois do maior id
        with db.engine.connect() as c:
            textos = {x for (x,) in c.execute(text("SELECT text FROM comment"))}
            assert "comentário com nulo  no meio" in textos               # o nulo do SQLite não passou
            assert isinstance(c.execute(text("SELECT SUM(file_size) FROM instance")).scalar(), int)
    finally:
        db.close()
    assert not arquivo.exists() and arquivo.with_name("dicomviewer.sqlite.migrado").is_file()
    assert not SS.precisa_migrar(arquivo)
    db = SS.Database(arquivo)                                            # de novo: sem migrar outra vez
    try:
        assert len(Repository(db).search_studies()) == 8
    finally:
        db.close()


def test_sqlite_com_postgres_ja_cheio_so_e_guardado(banco_antigo, tmp_path):
    from ipe.db.repository import Repository
    arquivo, _uid = banco_antigo
    SS.Database(arquivo).close()                                         # migrou
    _sqlite_antigo_de(SS.Database(arquivo), arquivo)                     # outro SQLite aparece no lugar
    assert SS.migrar_sqlite(arquivo) == {}                               # o PostgreSQL já tinha exames: não copia
    assert not arquivo.exists()
    assert len(list(tmp_path.joinpath("dados").glob("dicomviewer.sqlite.migrado*"))) == 2
    assert len(Repository(SS.Database(arquivo)).search_studies()) == 8  # nada duplicado


def test_janela_de_espera_da_migracao(banco_antigo):
    from PySide6.QtWidgets import QApplication

    from ipe.db.repository import Repository
    from ipe.ui.abrir_banco import abrir
    QApplication.instance() or QApplication([])
    arquivo, _uid = banco_antigo
    db = abrir(arquivo)
    try:
        assert db is not None and len(Repository(db).search_studies()) == 8
    finally:
        db.close()


def test_programa_abre_com_o_banco_antigo(env, banco_antigo, monkeypatch):
    """A abertura do programa (app.open_main_window) migra antes do login."""
    import shutil

    from PySide6.QtWidgets import QApplication

    from ipe import app as APP
    QApplication.instance() or QApplication([])
    paths, db, _repo = env
    db.close()
    arquivo, _uid = banco_antigo
    shutil.copy2(arquivo, paths.database)
    vistos = []
    monkeypatch.setattr("ipe.db.repository.Repository.__init__",
                        lambda self, d, _o=__import__("ipe.db.repository", fromlist=["x"]).Repository.__init__:
                        (vistos.append(d), _o(self, d))[1])
    monkeypatch.setattr("ipe.ui.login.do_login", lambda *a, **k: None)
    monkeypatch.setattr("ipe.auth.modo.precisa_perguntar", lambda *a, **k: False)
    from ipe.core.config import Settings
    assert APP.open_main_window(paths, Settings(paths.settings_file)) is None   # parou no login
    assert not paths.database.exists() and vistos and vistos[0].e_postgres


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
def test_copiar_de_um_postgres_para_outro(env, sample_dir, esquema_vazio):
    """Do banco em uso para um servidor próprio vazio (o botão Copiar)."""
    from ipe.db.repository import Repository
    from ipe.importer.scanner import Importer
    paths, db, _repo = env
    Importer(db, paths.storage).import_paths([sample_dir])
    t = BC.testar(esquema_vazio)
    assert t.ok and t.vazio and t.versao
    passos = []
    feito = BC.copiar(db.url, esquema_vazio, lambda tb, n, tot: passos.append((tb, n, tot)))
    assert feito["instance"] > 0 and feito["study"] == 8 and ("study", 8, 8) in passos
    pg = SS.Database(esquema_vazio)
    try:
        assert len(Repository(pg).search_studies()) == 8
        with pg.session() as s:
            from ipe.db.models import Tag
            s.add(Tag(name="nova"))
    finally:
        pg.close()
    assert not BC.testar(esquema_vazio).vazio
    with pytest.raises(BC.ErroBanco, match="já tem dados"):
        BC.copiar(db.url, esquema_vazio)
    BC.copiar(db.url, esquema_vazio, apagar_destino=True)
    assert BC.mesmo_banco(db.url, db.url) and not BC.mesmo_banco(db.url, esquema_vazio.replace("ipe_teste", "x"))


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


# ---------------------------------------------------------------------------------- o embutido (0.100.35)
from ipe.core import pg_embutido as PE  # noqa: E402

com_embutido = pytest.mark.skipif(not PE.disponivel(), reason="sem o pixeltable-pgserver")


@pytest.fixture()
def casa(tmp_path, monkeypatch):
    """Uma pasta de dados nova (com espaço no nome, como a do macOS) e o PostgreSQL do Ipê de verdade."""
    monkeypatch.setenv("DICOMVIEWER_HOME", str(tmp_path / "casa com espaço"))
    monkeypatch.delenv("IPE_DATABASE_URL", raising=False)
    yield tmp_path / "casa com espaço"
    PE.desligar_todos()


@com_embutido
@pytest.mark.pg_de_verdade
def test_embutido_liga_cria_o_banco_e_poe_senha(casa, sample_dir):
    from ipe.core.config import get_paths
    from ipe.db.repository import Repository
    from ipe.importer.scanner import Importer
    paths = get_paths()
    assert " " in str(paths.data)
    db = SS.Database(paths.database)                                      # sem banco.json: o do Ipê
    try:
        assert db.e_postgres and db.descricao().startswith("PostgreSQL do Ipê")
        assert (paths.data / "postgres" / "PG_VERSION").read_text().strip() == "16"
        assert not paths.database.exists()                                 # nada de arquivo SQLite
        Importer(db, paths.storage).import_paths([sample_dir])
        assert len(Repository(db).search_studies()) == 8
    finally:
        db.close()
    # a conexão pela rede local (a do Windows) pede senha, guardada com os dados
    assert PE._host_com_senha(paths.data / "postgres")
    senha = PE.senha_da_pasta(paths.data / "postgres")
    assert senha and len(senha) >= 24 and "senha" not in BC.ler()
    # de novo, depois de desligar: a mesma senha, o mesmo banco
    PE.desligar_todos()
    db2 = SS.Database(paths.database)
    try:
        assert len(Repository(db2).search_studies()) == 8 and PE.senha_da_pasta(paths.data / "postgres") == senha
    finally:
        db2.close()


@com_embutido
@pytest.mark.pg_de_verdade
def test_embutido_com_a_senha_perdida_poe_outra(casa):
    from ipe.core.config import get_paths
    pasta = get_paths().data / "postgres"
    url, senha = PE.garantir("", pasta)
    assert PE._conecta(url)
    url2, senha2 = PE.garantir("nao-e-essa", pasta)                      # arquivo da senha apagado, senha trocada…
    assert senha2 != senha and PE._conecta(url2) and PE._host_com_senha(pasta)
    from sqlalchemy.engine import make_url
    errada = make_url(url2).set(password=senha).render_as_string(hide_password=False)
    if make_url(url2).host:                                               # pela rede local (Windows): pede a senha
        assert not PE._conecta(errada)


@com_embutido
@pytest.mark.pg_de_verdade
def test_senha_da_0_100_35_no_banco_json_continua_valendo(casa):
    from ipe.core import segredos as SG
    from ipe.core.config import get_paths
    pasta = get_paths().data / "postgres"
    _url, senha = PE.garantir("", pasta)                                  # como a 0.100.35 deixava
    BC.arquivo().parent.mkdir(parents=True, exist_ok=True)
    BC.arquivo().write_text(json.dumps({"tipo": "embutido", "senha": SG.guardar(senha)}), encoding="utf-8")
    PE.desligar_todos()
    assert PE.senha_da_pasta(pasta) == ""
    PE.endereco_da_pasta(pasta)
    assert PE.senha_da_pasta(pasta) == senha                              # a mesma, agora com os dados


@com_embutido
@pytest.mark.pg_de_verdade
def test_migra_o_sqlite_antigo_para_o_embutido(casa, banco_antigo, monkeypatch):
    import shutil

    from ipe.core.config import get_paths
    from ipe.db.repository import Repository
    paths = get_paths()
    arquivo, _uid = banco_antigo
    shutil.copy2(arquivo, paths.database)
    db = SS.Database(paths.database)
    try:
        assert db.embutido and len(Repository(db).search_studies()) == 8
    finally:
        db.close()
    assert (paths.data / "dicomviewer.sqlite.migrado").is_file() and not paths.database.exists()


@com_embutido
@pytest.mark.pg_de_verdade
def test_janela_com_o_embutido(casa, monkeypatch):
    from PySide6.QtWidgets import QApplication, QMessageBox

    from ipe.core.config import get_paths
    from ipe.ui.banco_dialog import BancoDialog
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    paths = get_paths()
    d = BancoDialog(None, paths, None)
    assert d.r_emb.isChecked() and d.b_testar.isEnabled() and not d.grupo.isEnabled()
    t = d.testar()
    assert t.ok and t.versao.startswith("16") and "Conectou" in d.estado.text()
    d.reject()
    assert BC.ler() == {}                                                  # testar e cancelar não grava nada
    d2 = BancoDialog(None, paths, None)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    d2.aceitar()
    assert BC.ler() == {"tipo": "embutido"}


@com_embutido
@com_pg
@pytest.mark.pg_de_verdade
def test_linha_de_comando_copia_o_embutido_para_um_servidor(casa, sample_dir, esquema_vazio, monkeypatch, capsys):
    from sqlalchemy.engine import make_url

    from ipe.__main__ import main
    from ipe.core.config import get_paths
    from ipe.importer.scanner import Importer
    paths = get_paths()
    db = SS.Database(paths.database)
    Importer(db, paths.storage).import_paths([sample_dir])
    db.close()
    u = make_url(SS._normalizar(esquema_vazio))
    esquema = dict(u.query)["options"].split("=")[-1]
    monkeypatch.setenv("IPE_DB_SENHA", u.password or "")
    # o esquema vai na opção da conexão; pela linha de comando só host/porta/banco/usuário
    monkeypatch.setattr(BC, "url", lambda cfg, senha=None, _o=BC.url: (_o(cfg, senha) + f"&options=-csearch_path%3D{esquema}")
                        if BC.proprio(cfg) else "")
    rc = main(["banco", "postgres", "--host", u.host, "--porta", str(u.port or 5432), "--banco", u.database,
               "--usuario", u.username, "--ssl", "disable", "--copiar"])
    out = capsys.readouterr()
    assert rc == 0, out.err
    assert "Copiadas" in out.out and BC.ler()["tipo"] == "postgresql" and not BC.testar(esquema_vazio).vazio


def test_mover_a_pasta_leva_o_embutido():
    from ipe.core import mover_banco as MB
    assert "postgres" in MB.ITENS and "dicomviewer.sqlite.migrado" in MB.ITENS


def test_pacote_leva_o_embutido():
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1]
    spec = (raiz / "installer" / "ipe.spec").read_text(encoding="utf-8")
    # num .tar.gz (o PyInstaller não analisa), só o 16, e no lugar onde o programa procura
    assert "pg16.tar.gz" in spec and '"ipe/pg"' in spec and "montar_arquivo" in spec
    assert "pginstall18" not in spec and PE.ARQUIVO_PACOTE == "pg16.tar.gz"
    assert "testar-embutido" in (raiz / "installer" / "verifica.py").read_text(encoding="utf-8")


@com_embutido
@pytest.mark.pg_de_verdade
def test_no_pacote_extrai_e_liga_pelos_executaveis_extraidos(tmp_path, monkeypatch):
    """Como no programa empacotado: o .tar.gz montado como o ipe.spec monta, extraído uma vez (a segunda vez reusa),
    e o servidor ligado a partir dos executáveis extraídos."""
    import tarfile
    from pathlib import Path

    import pixeltable_pgserver as P
    from pixeltable_pgserver import utils as U

    from ipe.core import runtime as R
    arq = tmp_path / "pacote" / "ipe" / "pg" / "pg16.tar.gz"
    arq.parent.mkdir(parents=True)
    PE.montar_arquivo(Path(P.__file__).parent, arq)                   # como o ipe.spec
    with tarfile.open(arq) as t:
        nomes = t.getnames()
    assert not any("pginstall18" in n or "/include" in n or n.endswith(".py") for n in nomes)
    assert not any(n.endswith((".so.5.18", ".so.6.18", ".so.3.18")) for n in nomes)
    destino = tmp_path / "local" / "pgbin"
    bin_ = PE.pasta_dos_executaveis(arq, destino)
    assert (bin_ / ("initdb.exe" if os.name == "nt" else "initdb")).is_file()
    if os.name != "nt":
        assert os.access(bin_ / "initdb", os.X_OK)                       # a permissão de executar veio junto
    ok = bin_.parents[2] / ".ok"                                       # no alto da pasta extraída
    marca = ok.stat().st_mtime
    assert PE.pasta_dos_executaveis(arq, destino) == bin_ and ok.stat().st_mtime == marca
    antes = U.POSTGRES_VERSIONS[16]
    monkeypatch.setattr(R, "frozen", lambda: True)
    monkeypatch.setattr(R, "ambiente_do_sistema", lambda env=None: dict(env or os.environ))
    monkeypatch.setattr(PE, "_arquivo_do_pacote", lambda: arq)
    monkeypatch.setattr(PE, "pasta_dos_executaveis", lambda arquivo=None, destino_=None: bin_)
    try:
        assert PE.disponivel()
        versao = PE.testar_pacote(tmp_path / "dados" / "postgres")
        assert versao.startswith("16") and U.POSTGRES_VERSIONS[16] == bin_
    finally:
        U.POSTGRES_VERSIONS[16] = antes
        PE.desligar_todos()


@com_embutido
@pytest.mark.pg_de_verdade
def test_linha_de_comando_testar_embutido(tmp_path, capsys):
    from ipe.__main__ import main
    assert main(["banco", "testar-embutido", str(tmp_path / "pg")]) == 0
    assert "PostgreSQL embutido: ok, 16" in capsys.readouterr().out
