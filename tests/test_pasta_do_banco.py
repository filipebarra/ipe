"""0.99.67 — o instalador escolhe a pasta do banco (ipe-cli set-data-dir): aponta, nunca move, e não troca um
banco com exames por uma pasta vazia."""
import json

from ipe.__main__ import main
from ipe.core.config import Settings, definir_pasta_do_banco, get_paths


def test_set_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("IPE_HOME", str(tmp_path / "home"))
    paths = get_paths()
    nova = tmp_path / "D" / "Banco Ipê"
    assert main(["set-data-dir", str(nova)]) == 0
    cfg = json.loads(paths.settings_file.read_text(encoding="utf-8"))
    assert cfg["data_dir"] == str(nova.resolve()) and nova.is_dir()
    assert get_paths().data == nova.resolve()
    # o banco novo ganha exames; trocar por uma pasta vazia é recusado (mover é pelo programa)
    (nova / "dicomviewer.sqlite").write_bytes(b"x")
    vazia = tmp_path / "E"
    assert main(["set-data-dir", str(vazia)]) == 3
    assert get_paths().data == nova.resolve()
    # apontar para outra pasta que já tem banco vale
    outra = tmp_path / "F"
    outra.mkdir()
    (outra / "dicomviewer.sqlite").write_bytes(b"y")
    s = Settings(get_paths().settings_file)
    ok, _ = definir_pasta_do_banco(s, get_paths(), outra)
    assert ok and get_paths().data == outra.resolve()
    # voltar para a padrão grava "" (a padrão do sistema)
    (tmp_path / "home" / "data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "home" / "data" / "dicomviewer.sqlite").write_bytes(b"z")
    ok, _ = definir_pasta_do_banco(Settings(get_paths().settings_file), get_paths(), tmp_path / "home" / "data")
    assert ok and json.loads(paths.settings_file.read_text(encoding="utf-8"))["data_dir"] == ""
    assert main(["set-data-dir", str(tmp_path / "home" / "data")]) == 0      # já é: nada muda
