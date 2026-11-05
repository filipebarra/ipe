"""0.99.75 — mover a pasta do banco na abertura (com o programa aberto o Windows recusa: WinError 32)."""
import errno
import json
import os

import pytest

from ipe.core import mover_banco as MB
from ipe.core.config import Settings, get_paths


def _banco(p):
    (p / "Storage" / "E1").mkdir(parents=True)
    (p / "Storage" / "E1" / "a.dcm").write_bytes(b"dicom")
    (p / "dicomviewer.sqlite").write_bytes(b"sqlite")
    (p / "dicomviewer.sqlite-wal").write_bytes(b"wal")


def test_mover_mesmo_disco_e_outro_disco(tmp_path, monkeypatch):
    de, para = tmp_path / "de", tmp_path / "para"
    _banco(de)
    assert MB.mover(de, para) == ["dicomviewer.sqlite", "dicomviewer.sqlite-wal", "Storage"]
    assert (para / "Storage" / "E1" / "a.dcm").read_bytes() == b"dicom" and not (de / "Storage").exists()
    # outro disco: o rename falha com EXDEV, vai por cópia
    real = os.rename

    def sem_rename(a, b):
        raise OSError(errno.EXDEV, "outro disco")
    monkeypatch.setattr(os, "rename", sem_rename)
    outro = tmp_path / "outro"
    MB.mover(para, outro)
    assert (outro / "dicomviewer.sqlite-wal").read_bytes() == b"wal" and not (para / "dicomviewer.sqlite").exists()
    monkeypatch.setattr(os, "rename", real)


def test_falha_devolve_tudo(tmp_path, monkeypatch):
    de, para = tmp_path / "de", tmp_path / "para"
    _banco(de)
    real = os.rename

    def preso(a, b):
        if str(a).endswith("Storage") and str(b).startswith(str(para)):
            raise PermissionError(32, "The process cannot access the file because it is being used")
        return real(a, b)
    monkeypatch.setattr(os, "rename", preso)
    with pytest.raises(MB.ErroMover, match="Nada mudou"):
        MB.mover(de, para)
    assert MB.itens_de(de) == ["dicomviewer.sqlite", "dicomviewer.sqlite-wal", "Storage"]
    assert MB.itens_de(para) == []
    (para / "dicomviewer.sqlite").write_bytes(b"outro")
    monkeypatch.setattr(os, "rename", real)
    with pytest.raises(MB.ErroMover, match="já tem"):
        MB.mover(de, para)


def test_na_abertura(tmp_path, monkeypatch):
    monkeypatch.setenv("IPE_HOME", str(tmp_path / "home"))
    paths = get_paths().ensure()
    (paths.data / "dicomviewer.sqlite").write_bytes(b"sqlite")
    s = Settings(paths.settings_file)
    nova = tmp_path / "D" / "Banco"
    MB.marcar(s, paths.data, nova)
    ok, msg = MB.executar_pendente(Settings(paths.settings_file), paths)
    assert ok and str(nova) in msg
    assert get_paths().data.resolve() == nova.resolve() and (nova / "dicomviewer.sqlite").exists()
    cfg = json.loads(paths.settings_file.read_text(encoding="utf-8"))
    assert cfg.get(MB.CHAVE) is None
    assert MB.executar_pendente(Settings(paths.settings_file), get_paths()) is None
