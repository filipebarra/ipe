"""Banco de versão antiga: colunas novas têm que entrar, inclusive as NOT NULL."""
import sqlite3

import pytest

from ipe.db.repository import Repository
from ipe.db.session import Database

# print_job como era antes dos servidores de impressão e do cadastro de origens
ANTIGA = """CREATE TABLE print_job (
  id INTEGER PRIMARY KEY, uid VARCHAR(64), source VARCHAR(8), received_at DATETIME,
  calling_ae VARCHAR(32), remote_host VARCHAR(64), label VARCHAR(256), medium VARCHAR(32),
  film_size VARCHAR(32), sheets INTEGER, images INTEGER, patient_name VARCHAR(256),
  patient_id VARCHAR(64), id_source VARCHAR(16), study_uid VARCHAR(64), folder TEXT,
  status VARCHAR(16), destination VARCHAR(128), sent_at DATETIME, message TEXT)"""


def _banco_antigo(tmp_path):
    caminho = tmp_path / "antigo.db"
    con = sqlite3.connect(caminho)
    con.execute(ANTIGA)
    con.execute("INSERT INTO print_job (uid, source, label, status) VALUES ('u1','scp','Antigo','new')")
    con.commit()
    con.close()
    return caminho


def _colunas(caminho, tabela):
    con = sqlite3.connect(caminho)
    try:
        return {r[1] for r in con.execute(f"PRAGMA table_info({tabela})")}
    finally:
        con.close()


def test_coluna_not_null_entra_com_valor_inicial(tmp_path):
    caminho = _banco_antigo(tmp_path)
    assert "server" not in _colunas(caminho, "print_job")
    db = Database(caminho)
    assert "server" in _colunas(caminho, "print_job")
    linhas = Repository(db).print_jobs()
    assert len(linhas) == 1 and linhas[0]["label"] == "Antigo"
    assert linhas[0]["server"] == ""              # o que já estava lá ganha o valor padrão
    db.close()


def test_migracao_nao_estraga_o_que_ja_existia(tmp_path):
    caminho = _banco_antigo(tmp_path)
    Database(caminho).close()
    con = sqlite3.connect(caminho)
    try:
        uid, label = con.execute("SELECT uid, label FROM print_job").fetchone()
    finally:
        con.close()
    assert (uid, label) == ("u1", "Antigo")
    Database(caminho).close()                     # abrir de novo não repete nem quebra
    assert len(Repository(Database(caminho)).print_jobs()) == 1


def test_valor_inicial_por_tipo():
    from sqlalchemy import Column, Integer, String
    from ipe.db.session import _default_sql
    assert _default_sql(Column("a", String(8), default="")) == "''"
    assert _default_sql(Column("b", String(8), default="scp")) == "'scp'"
    assert _default_sql(Column("c", Integer, default=3)) == "3"
    assert _default_sql(Column("d", String(8))) == "''"        # sem default, pelo tipo
    assert _default_sql(Column("e", Integer)) == "0"
    aspas = _default_sql(Column("f", String(8), default="d'agua"))
    assert aspas == "'d''agua'"                                # aspas escapadas


def test_aba_de_impressoes_abre_mesmo_com_banco_quebrado(env, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from ipe.core.config import Settings
    from ipe.ui.main_window import MainWindow
    paths, db, repo = env
    QApplication.instance() or QApplication([])
    w = MainWindow(paths, Settings(paths.settings_file))
    w.show()

    def explode(*_a, **_k):
        raise RuntimeError("no such column: print_job.server")
    monkeypatch.setattr(type(w.repo), "print_jobs", explode)
    aba = w.show_prints()
    assert aba is not None                        # a aba abre mesmo assim
    assert w.tabs.indexOf(aba) >= 0
    assert aba.rows == []                         # vazia, e não travada
    w.close()
