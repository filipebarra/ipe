"""0.99.66 — importar compactados além do ZIP: RAR, 7z, TAR, ISO; partes, compactado dentro de compactado,
senha e Deflate64 (o ZIP grande do Windows) pelos programas de fora."""
import shutil
import subprocess
import tarfile
import zipfile

import pytest

from ipe.importer import compactados as CP
from ipe.importer.scanner import Importer


def _us(sample_dir):
    return sorted((sample_dir / "US").glob("*.dcm"))


def test_formato_e_volumes(tmp_path):
    assert CP.formato("a.ZIP") == "zip" and CP.formato("a.tar.gz") == "tar" and CP.formato("a.tgz") == "tar"
    assert CP.formato("x.rar") == "rar" and CP.formato("x.7z") == "7z" and CP.formato("cd.iso") == "iso"
    assert CP.formato("x.7z.001") == "7z" and CP.formato("x.r00") == "rar" and CP.formato("x.dcm") == ""
    (tmp_path / "e.part1.rar").write_bytes(b"x")
    (tmp_path / "e.part2.rar").write_bytes(b"x")
    (tmp_path / "f.7z.001").write_bytes(b"x")
    assert CP.volume_seguinte(tmp_path / "e.part2.rar") and not CP.volume_seguinte(tmp_path / "e.part1.rar")
    assert CP.volume_seguinte(tmp_path / "f.7z.002") and not CP.volume_seguinte(tmp_path / "f.7z.001")
    assert CP.volume_seguinte(tmp_path / "g.r00", {str(tmp_path / "g.rar")})
    assert not CP.volume_seguinte(tmp_path / "h.part3.rar")            # sem a primeira parte: tenta assim mesmo


def test_tar_e_zip_no_python(env, sample_dir, tmp_path):
    paths, db, _ = env
    t = tmp_path / "exame.tar.gz"
    with tarfile.open(t, "w:gz") as tf:
        for f in _us(sample_dir):
            tf.add(f, f"pasta/{f.name}")
    assert CP.extrair(t, tmp_path / "x") == "tarfile"
    r = Importer(db, paths.storage, copy_to_storage=False).import_paths([t])
    assert r.added == 1 and r.errors == 0
    # ZIP com senha: mensagem, sem travar
    z = tmp_path / "senha.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a.dcm", b"x")
    raw = bytearray(z.read_bytes())
    i = raw.find(b"PK\x03\x04")
    raw[i + 6] |= 1                                                       # marca "criptografado" no local
    j = raw.find(b"PK\x01\x02")
    raw[j + 8] |= 1                                                       # e no diretório central
    z.write_bytes(bytes(raw))
    with pytest.raises(CP.ErroCompactado, match="senha"):
        CP.extrair(z, tmp_path / "y")


precisa_7z = pytest.mark.skipif(not shutil.which("7z"), reason="sem 7z para criar o arquivo de teste")


@precisa_7z
def test_7z_e_aninhado_pelo_importador(env, sample_dir, tmp_path):
    paths, db, repo = env
    src = tmp_path / "src"
    (src / "pasta").mkdir(parents=True)
    for f in _us(sample_dir):
        shutil.copy(f, src / "pasta" / f.name)
    a7 = tmp_path / "exame.7z"
    subprocess.run(["7z", "a", "-bd", str(a7), "pasta"], cwd=src, check=True, capture_output=True)
    assert CP.extrair(a7, tmp_path / "o7") in ("7-Zip", "tar")
    # o ZIP em Deflate64 (o do Windows para arquivos grandes): o zipfile não lê, o 7-Zip sim
    d64 = tmp_path / "d64.zip"
    subprocess.run(["7z", "a", "-bd", "-tzip", "-mm=Deflate64", str(d64), "pasta"], cwd=src, check=True,
                   capture_output=True)
    assert CP.extrair(d64, tmp_path / "o64") in ("7-Zip", "tar")
    assert len(list((tmp_path / "o64").rglob("*.dcm"))) == len(_us(sample_dir))
    # o 7z dentro de um ZIP
    z = tmp_path / "pacote.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(a7, "dentro/exame.7z")
    r = Importer(db, paths.storage, copy_to_storage=False).import_paths([z])
    assert r.added == 1 and r.errors == 0 and r.not_dicom == 0


@precisa_7z
def test_7z_em_partes_e_senha(env, sample_dir, tmp_path, monkeypatch):
    paths, db, _ = env
    src = tmp_path / "src"
    src.mkdir()
    for f in _us(sample_dir):
        shutil.copy(f, src / f.name)
    (src / "enchimento.bin").write_bytes(bytes(range(256)) * 400)
    subprocess.run(["7z", "a", "-bd", "-mx0", "-v40k", str(tmp_path / "vol.7z"), "."], cwd=src, check=True,
                   capture_output=True)
    partes = sorted(tmp_path.glob("vol.7z.*"))
    assert len(partes) >= 2
    r = Importer(db, paths.storage, copy_to_storage=False).import_paths(partes)       # todas as partes juntas
    assert r.added == 1 and r.errors == 0
    s = tmp_path / "senha.7z"
    subprocess.run(["7z", "a", "-bd", "-pabc", str(s), "."], cwd=src, check=True, capture_output=True)
    with pytest.raises(CP.ErroCompactado, match="senha"):
        CP.extrair(s, tmp_path / "s")
    r = Importer(db, paths.storage).import_paths([s])
    assert r.errors == 1 and "senha" in r.error_files[0]
    # sem nenhum programa de fora: diz o que instalar
    monkeypatch.setattr(CP, "sete_zip", lambda: None)
    monkeypatch.setattr(CP, "bsdtar", lambda: None)
    monkeypatch.setattr(CP, "unrar", lambda: None)
    with pytest.raises(CP.ErroCompactado, match="7-Zip"):
        CP.extrair(tmp_path / "vol.7z.001", tmp_path / "z")


@pytest.mark.skipif(not shutil.which("rar"), reason="sem rar para criar o arquivo de teste")
def test_rar_pelo_7zip_e_pelo_tar(env, sample_dir, tmp_path, monkeypatch):
    paths, db, _ = env
    src = tmp_path / "src"
    src.mkdir()
    for f in _us(sample_dir):
        shutil.copy(f, src / f.name)
    rar = tmp_path / "exame.rar"
    subprocess.run(["rar", "a", "-idq", "-ep1", str(rar), str(src) + "/"], check=True, capture_output=True)
    if CP.bsdtar():
        monkeypatch.setattr(CP, "sete_zip", lambda: None)
        monkeypatch.setattr(CP, "unrar", lambda: None)
        assert CP.extrair(rar, tmp_path / "t") == "tar"                # o caminho do Windows sem 7-Zip
        monkeypatch.undo()
    r = Importer(db, paths.storage, copy_to_storage=False).import_paths([rar])
    assert r.added == 1 and r.errors == 0


def test_descricao_do_arrasto(tmp_path):
    from ipe.ui.file_drop import describe
    for n in ("a.rar", "b.7z", "c.zip"):
        (tmp_path / n).write_bytes(b"x")
    (tmp_path / "d.dcm").write_bytes(b"x")
    assert describe([tmp_path / n for n in ("a.rar", "b.7z", "c.zip", "d.dcm")]) == "3 compactados, 1 arquivo"
