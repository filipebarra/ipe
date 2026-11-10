"""0.100.6: os dois jeitos de instalar no Linux — o `install.sh` dentro do portátil (para o usuário, sem
administrador; atualiza no lugar; remove sem tocar nos exames) e o pacote `.deb` (/opt/ipe, /usr/bin/ipe-viewer,
atalho e ícone). Testados com um "portátil" falso: um Ipe que só escreve os argumentos."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
LINUX = RAIZ / "installer" / "linux"

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="só no Linux")


def _portatil(tmp: Path, marca: str = "v1") -> Path:
    d = tmp / "portatil" / "Ipe"
    d.mkdir(parents=True)
    ipe = d / "Ipe"
    ipe.write_text(f'#!/bin/sh\necho "{marca}" "$@"\n')
    ipe.chmod(0o755)
    (d / "_internal").mkdir()
    (d / "_internal" / "lib.so").write_bytes(b"\0" * 10)
    shutil.copy(LINUX / "install.sh", d / "install.sh")
    shutil.copy(LINUX / "ipe.png", d / "ipe.png")
    return d


def _rodar(cmd, home: Path, **kw):
    env = {**os.environ, "HOME": str(home), "XDG_DATA_HOME": str(home / ".local" / "share"),
           "PATH": f"{home / '.local' / 'bin'}:{os.environ.get('PATH', '')}"}
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=60, **kw)


def test_install_sh_instala_atualiza_e_remove(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    dados = home / ".local" / "share" / "DicomViewer"
    dados.mkdir(parents=True)
    (dados / "ipe.db").write_text("exames")                     # o banco do usuário: nunca é tocado
    port = _portatil(tmp_path)
    r = _rodar(["bash", str(port / "install.sh")], home)
    assert r.returncode == 0, r.stderr
    prog = home / ".local" / "share" / "ipe" / "programa"
    assert (prog / "Ipe").is_file() and (prog / "_internal" / "lib.so").is_file()
    link = home / ".local" / "bin" / "ipe-viewer"
    assert link.is_symlink() and os.readlink(link) == str(prog / "Ipe")
    assert _rodar(["ipe-viewer", "open", "x.dcm"], home).stdout.strip() == "v1 open x.dcm"
    desk = (home / ".local" / "share" / "applications" / "ipe-viewer.desktop").read_text()
    assert f'Exec="{prog}/Ipe" open %F' in desk and "Icon=ipe-viewer" in desk and "Name=Ipê" in desk
    assert "GenericName[pt_BR]=Visualizador DICOM" in desk
    assert (home / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "ipe-viewer.png").stat().st_size > 1000
    if shutil.which("desktop-file-validate"):
        assert _rodar(["desktop-file-validate", str(home / ".local/share/applications/ipe-viewer.desktop")], home).returncode == 0
    # atualizar: outro portátil por cima, o programa troca e nada sobra do antigo
    (prog / "_internal" / "velho.so").write_bytes(b"x")
    port2 = _portatil(tmp_path / "b", "v2")
    r = _rodar(["bash", str(port2 / "install.sh")], home)
    assert r.returncode == 0, r.stderr
    assert _rodar(["ipe-viewer"], home).stdout.strip() == "v2"
    assert not (prog / "_internal" / "velho.so").exists() and not Path(f"{prog}.novo").exists()
    # rodar o instalador já instalado não estraga nada
    r = _rodar(["bash", str(prog / "install.sh")], home)
    assert r.returncode == 1 and "já está instalado" in r.stderr
    # remover: o programa, o comando, o atalho e o ícone saem; os exames ficam
    r = _rodar(["bash", str(port2 / "install.sh"), "--uninstall"], home)
    assert r.returncode == 0, r.stderr
    assert not prog.exists() and not link.exists() and not link.is_symlink()
    assert not (home / ".local/share/applications/ipe-viewer.desktop").exists()
    assert (dados / "ipe.db").read_text() == "exames"
    assert "continuam" in r.stdout
    # opção errada
    assert _rodar(["bash", str(port2 / "install.sh"), "--xyz"], home).returncode == 2


@pytest.mark.skipif(not shutil.which("dpkg-deb"), reason="sem dpkg-deb")
def test_pacote_deb(tmp_path):
    port = _portatil(tmp_path)
    saida = tmp_path / "saida"
    r = subprocess.run(["bash", str(LINUX / "build_deb.sh"), str(port), "0.100.6", str(saida)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    deb = saida / "Ipe-0.100.6-linux-amd64.deb"
    assert r.stdout.strip() == str(deb) and deb.is_file()
    info = subprocess.run(["dpkg-deb", "-f", str(deb)], capture_output=True, text=True).stdout
    assert "Package: ipe-viewer" in info and "Version: 0.100.6" in info and "Architecture: amd64" in info
    assert "libxcb-cursor0" in info and "Maintainer: Filipe Barra" in info
    lista = subprocess.run(["dpkg-deb", "-c", str(deb)], capture_output=True, text=True).stdout
    linhas = lista.splitlines()
    assert any(l.endswith("./opt/ipe/Ipe") and l.startswith("-rwxr-xr-x root/root") for l in linhas), lista
    assert any("./usr/bin/ipe-viewer -> /opt/ipe/Ipe" in l for l in linhas)
    assert any(l.endswith("./usr/share/applications/ipe-viewer.desktop") for l in linhas)
    assert any(l.endswith("./usr/share/icons/hicolor/256x256/apps/ipe-viewer.png") for l in linhas)
    assert not any("install.sh" in l for l in linhas)
    # o atalho do pacote abre o programa de /opt/ipe
    x = tmp_path / "x"
    subprocess.run(["dpkg-deb", "-x", str(deb), str(x)], check=True)
    desk = (x / "usr/share/applications/ipe-viewer.desktop").read_text()
    assert "Exec=/opt/ipe/Ipe open %F" in desk
    ctl = tmp_path / "ctl"
    subprocess.run(["dpkg-deb", "-e", str(deb), str(ctl)], check=True)
    assert os.access(ctl / "postinst", os.X_OK) and "update-desktop-database" in (ctl / "postinst").read_text()
