"""0.99.68 — exportar as configurações num computador e importar em outro (Windows ↔ Linux)."""
import json

import pytest

from ipe.core import config_pacote as CP
from ipe.core.config import AppPaths, Settings
from ipe.db.repository import Repository
from ipe.db.session import Database


def _outro(tmp_path, nome):
    base = tmp_path / nome
    paths = AppPaths(base / "data", base / "config", base / "logs").ensure()
    return paths, Settings(paths.settings_file), Repository(Database(paths.database))


def test_ida_e_volta(env, tmp_path):
    paths, db, repo = env
    s = Settings(paths.settings_file)
    s.set("viewer.invert_wheel", True)
    s.set("report.header", "IMEB CENTRO CLÍNICO SUL")
    s.set("export.last_dir", r"C:\Users\filip\Desktop\EXAMES")          # pasta do Windows
    s.set("printing.saida_dir", "/home/filipe/filmes")                    # pasta do Linux
    s.set("dicom.ae_title", "ESTACAO1")                                    # deste computador: não vai
    s.set("dicom.http_token", "segredo-do-pc")
    s.set("data_dir", r"D:\Banco")
    s.set("monitors", {"HDMI|1": {"role": "viewer"}})
    s.set("pacs.geometry", "AdnQ")
    s.set("ia.chave", "enc1:k:xxxx")                                       # cifrado deste computador
    s.set("hanging_protocols", [{"name": "Tórax", "rows": 1}, {"name": "Mama", "rows": 2}])
    s.save()
    repo.set_app_setting("report_templates", [{"name": "TC de tórax", "text": "Pulmões…"}])
    repo.set_app_setting("sla", {"urgente": 2})
    repo.set_app_setting("report_templates_vistos", ["x"])
    nid = repo.save_node({"name": "PACS", "kind": "dimse", "ae_title": "PACS", "host": "10.0.0.5", "port": 104,
                          "password": "s3nha"})
    repo.save_rule({"kind": "query", "name": "Mamografias de ontem", "active": True, "config": {"mod": "MG"}})
    loc = paths.config / "locale"
    loc.mkdir(parents=True, exist_ok=True)
    (loc / "en.json").write_text(json.dumps({"Fígado": "Liver!"}), encoding="utf-8")

    arq = CP.exportar(tmp_path / "x", s, repo, paths)["_arquivo"]
    assert arq.endswith(".ipeconfig")
    texto = open(arq, encoding="utf-8").read()
    assert "s3nha" not in texto and "segredo-do-pc" not in texto and "ESTACAO1" not in texto
    assert "enc1:" not in texto and "AdnQ" not in texto and "HDMI" not in texto
    pac = CP.ler(arq)
    assert pac["listas"]["hanging_protocols"][0]["name"] == "Tórax"
    assert "report_templates_vistos" not in pac["servico"] and pac["servico"]["sla"] == {"urgente": 2}

    # o outro computador é Linux: a pasta C:\ não entra, a /home entra
    p2, s2, r2 = _outro(tmp_path, "linux")
    s2.set("dicom.ae_title", "ESTACAO2")
    s2.set("hanging_protocols", [{"name": "Mama", "rows": 9}, {"name": "Crânio", "rows": 1}])
    r2.save_node({"name": "PACS", "kind": "dimse", "host": "velho", "password": "daqui"})
    feito = CP.aplicar(pac, s2, r2, p2, windows=False)
    assert "export.last_dir" in feito["_caminhos"] and not feito["_erros"]
    s2 = Settings(p2.settings_file)
    assert s2.get("viewer.invert_wheel") is True and s2.get("report.header") == "IMEB CENTRO CLÍNICO SUL"
    assert s2.get("printing.saida_dir") == "/home/filipe/filmes" and s2.get("export.last_dir") in (None, "")
    assert s2.get("dicom.ae_title") == "ESTACAO2" and s2.get("data_dir") == ""
    nomes = [h["name"] for h in s2.get("hanging_protocols")]
    assert nomes == ["Mama", "Crânio", "Tórax"] and s2.get("hanging_protocols")[0]["rows"] == 2
    nos = r2.nodes(todos=True)
    assert len(nos) == 1 and nos[0]["host"] == "10.0.0.5" and nos[0]["password"] == "daqui"   # senha daqui fica
    assert [r["name"] for r in r2.rules()] == ["Mamografias de ontem"]
    assert r2.get_app_setting("report_templates")[0]["name"] == "TC de tórax"
    assert json.loads((p2.config / "locale" / "en.json").read_text(encoding="utf-8")) == {"Fígado": "Liver!"}
    # importar de novo não duplica
    CP.aplicar(pac, Settings(p2.settings_file), r2, p2, windows=False)
    assert len(r2.nodes(todos=True)) == 1 and len(r2.rules()) == 1

    # com as senhas: vão abertas e são cifradas de novo no outro computador
    arq2 = CP.exportar(tmp_path / "com_senha.ipeconfig", s, repo, paths, senhas=True)["_arquivo"]
    assert "s3nha" in open(arq2, encoding="utf-8").read()
    p3, s3, r3 = _outro(tmp_path, "win")
    CP.aplicar(CP.ler(arq2), s3, r3, p3, windows=True)
    assert r3.nodes(todos=True)[0]["password"] == "s3nha"
    assert Settings(p3.settings_file).get("printing.saida_dir") in (None, "")      # /home não vale no Windows
    assert repo.node(nid)["password"] == "s3nha"


def test_arquivo_errado(tmp_path):
    f = tmp_path / "a.ipeconfig"
    f.write_text("{}", encoding="utf-8")
    with pytest.raises(CP.PacoteInvalido):
        CP.ler(f)
    f.write_text(json.dumps({"formato": CP.FORMATO, "versao": 99}), encoding="utf-8")
    with pytest.raises(CP.PacoteInvalido, match="mais nova"):
        CP.ler(f)
    assert CP.caminho_de_outro_sistema(r"C:\x", windows=False) and not CP.caminho_de_outro_sistema("/x", False)
    assert CP.caminho_de_outro_sistema("/home/x", windows=True) and not CP.caminho_de_outro_sistema(r"C:\x", True)


def test_telas(env, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

    from ipe.ui import config_pacote_dialog as D
    from ipe.ui.main_window import MainWindow
    app = QApplication.instance() or QApplication([])
    paths, db, repo = env
    w = MainWindow(paths, Settings(paths.settings_file), repo=repo, db=db)
    try:
        w.settings.set("report.header", "Cabeçalho")
        destino = tmp_path / "cfg.ipeconfig"
        monkeypatch.setattr(D.EscolherPartes, "exec", lambda self: QDialog.Accepted)
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(destino), ""))
        monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: (str(destino), ""))
        msgs = []
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: msgs.append(a[2]))
        assert w.exportar_configuracoes() == str(destino)
        w.settings.set("report.header", "outro")
        feito = w.importar_configuracoes()
        assert feito is not None and w.settings.get("report.header") == "Cabeçalho"
        assert "Feche e abra" in msgs[-1] and list((paths.config / "backups_config").glob("*.ipeconfig"))
        from ipe.ui import configuracoes as C
        textos = [t for nome, itens in C.CATALOGO if nome == "Sistema" for t, _a, _p in itens]
        assert "Exportar as configurações…" in textos and "Importar configurações…" in textos
        app.processEvents()
    finally:
        w.close()
