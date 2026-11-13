"""0.100.32: o Ipê no macOS como programa do sistema — teclas do Mac nos textos, links (com apelidos, como
osirix://), atualização que troca o aplicativo sozinha."""
import subprocess
import sys
from pathlib import Path

import pytest

from ipe.core import atualizar_github as GH
from ipe.core import i18n
from ipe.network import external as X


# ---------------------------------------------------------------- teclas
def test_textos_com_as_teclas_do_mac():
    antes = i18n.teclas_do_mac()
    try:
        i18n.teclas_do_mac(False)
        assert i18n.tr("Ctrl+C copia o quadro") == "Ctrl+C copia o quadro"
        i18n.teclas_do_mac(True)
        assert i18n.tr("Ctrl+C copia o quadro") == "⌘C copia o quadro"
        assert i18n.tr("Ctrl/Shift+clique seleciona várias") == "⌘/Shift+clique seleciona várias"
        assert i18n.tr("segure o Ctrl para rolar · Alt+roda") == "segure o ⌘ para rolar · ⌥roda"
        assert i18n.tr("Controle de qualidade") == "Controle de qualidade"        # palavra, não tecla
        assert i18n.tr("") == "" and i18n.tr(None) is None
    finally:
        i18n.teclas_do_mac(antes)


def test_no_mac_a_troca_de_texto_e_instalada_mesmo_em_portugues():
    fonte = (Path(GH.__file__).parents[1] / "app.py").read_text(encoding="utf-8")
    assert "lang != i18n.BASE_LANG or i18n.teclas_do_mac()" in fonte


# ---------------------------------------------------------------- links e apelidos
class _S(dict):
    def get(self, k, d=None):
        return dict.get(self, k, d)


def test_apelidos_validos():
    assert X.apelidos_validos("osirix, Horos; http ipe 9x weasis://") == ["osirix", "horos", "weasis"]
    assert X.apelidos_validos(["osirix", "osirix", "a", "file"]) == ["osirix"]
    s = _S(dicom={"link_apelidos": ["osirix"]})
    assert X.esquemas(s) == ("ipe", "dicomviewer", "osirix")
    assert X.e_link("osirix://?methodName=displayStudy", s) and X.e_link("IPE://open?accession=1", s)
    assert not X.e_link("horos://x", s) and not X.e_link("C:\\pasta\\exame.dcm", s) and not X.e_link("https://x", s)


def test_link_no_formato_do_osirix():
    p = X.parse_url("osirix://?methodName=displayStudy&StudyInstanceUID=1.2.3&PatientID=77", ("osirix",))
    assert p == {"command": "open", "study_uid": "1.2.3", "patient_id": "77"}
    assert X.parse_url("horos://?methodName=DisplayStudy&AccessionNumber=A1", ("horos",))["accession"] == "A1"
    with pytest.raises(X.ExternalError):                      # baixar de uma URL qualquer: nunca
        X.parse_url("osirix://?methodName=downloadURL&URL=http://x/y.zip", ("osirix",))
    with pytest.raises(X.ExternalError):                      # apelido não configurado
        X.parse_url("osirix://?methodName=displayStudy&PatientID=1", ("ipe", "dicomviewer"))
    # o apelido com o formato do Ipê também vale (o aplicativo-ponte do Mac repassa como ipe:)
    assert X.parse_url("ipe://?methodName=displayStudy&PatientID=9", ("ipe",))["patient_id"] == "9"
    assert X.parse_url("osirix://open?accession=Z9&token=abc", ("osirix",))["link_token"] == "abc"


def test_linha_de_comando_reconhece_o_apelido(monkeypatch):
    from ipe import __main__ as M
    assert M._e_link("ipe://open?accession=1") and M._e_link("dicomviewer://open?accession=1")
    assert not M._e_link("info") and not M._e_link("--minimized") and not M._e_link("/tmp/a://b")
    monkeypatch.setattr(X, "esquemas", lambda _s=None: ("ipe", "dicomviewer", "osirix"))
    assert M._e_link("osirix://?methodName=displayStudy&PatientID=1") and not M._e_link("horos://x")


def test_apelido_no_mac_vira_aplicativo_ponte(tmp_path):
    import plistlib
    feitos_cmd = []

    def rodar(cmd):
        feitos_cmd.append(cmd)
        if cmd[0].endswith("osacompile"):
            app = Path(cmd[2])
            (app / "Contents").mkdir(parents=True)
            (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps({"CFBundleName": "applet"}))
            assert "open location" in Path(cmd[3]).read_text(encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    (tmp_path / "Ipe-antigo.app").mkdir()
    feitos, falhas = X._mac_apelidos(["osirix"], pasta=tmp_path, rodar=rodar)
    assert feitos == ["osirix"] and not falhas and not (tmp_path / "Ipe-antigo.app").exists()
    d = plistlib.loads((tmp_path / "Ipe-osirix.app" / "Contents" / "Info.plist").read_bytes())
    assert d["CFBundleURLTypes"][0]["CFBundleURLSchemes"] == ["osirix"] and d["LSUIElement"] is True
    assert d["CFBundleIdentifier"] == "br.ipe.link.osirix"
    assert any(c[0].endswith("codesign") for c in feitos_cmd) and any(c[0] == X.LSREGISTER for c in feitos_cmd)
    # o roteiro repassa o que vem depois do nome como ipe:
    assert '"ipe:" & resto' in X.ROTEIRO_MAC


def test_apelido_que_sai_solta_o_registro_no_windows():
    fonte = Path(X.__file__).read_text(encoding="utf-8")
    assert "_nosso_no_registro(winreg, esquema)" in fonte          # só apaga o que é do Ipê ("URL:Ipê")


def test_evento_de_link_do_mac_chega_a_janela():
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QFileOpenEvent
    from PySide6.QtWidgets import QApplication

    from ipe import app as A
    qapp = QApplication.instance() or QApplication([])
    recebidos = []
    filtro = A._ouvir_links_do_sistema(qapp, recebidos.append)
    try:
        QApplication.sendEvent(qapp, QFileOpenEvent(QUrl("ipe://open?accession=MAC1")))
        QApplication.sendEvent(qapp, QFileOpenEvent(QUrl("https://exemplo.invalid/x")))
    finally:
        qapp.removeEventFilter(filtro)
    assert recebidos == [{"command": "open", "accession": "MAC1", "source": "link"}]


# ---------------------------------------------------------------- atualização
INFO = {"versao": "9.9.9", "pacotes": [{"nome": f"Ipe-9.9.9-{n}", "url": "u", "tamanho": 1, "sha256": ""} for n in (
    "installer.exe", "windows-portable.zip", "linux-portable.tar.gz", "linux-amd64.deb", "macos-arm64.dmg",
    "macos-x86_64.dmg")]}


def test_mac_pede_o_dmg_da_sua_arquitetura():
    assert GH.modo_desta_instalacao(plataforma="darwin", congelado=True) == "macos"
    assert GH.modo_desta_instalacao(plataforma="linux", congelado=True) == "linux"
    assert GH.pacote_para(INFO, "macos", maquina="arm64")["nome"].endswith("macos-arm64.dmg")
    assert GH.pacote_para(INFO, "macos", maquina="x86_64")["nome"].endswith("macos-x86_64.dmg")
    assert GH.pacote_para(INFO, "linux")["nome"].endswith("linux-portable.tar.gz")
    assert GH.pacote_para({"pacotes": INFO["pacotes"][:4]}, "macos", maquina="arm64") is None


def test_onde_o_aplicativo_troca_sozinho(tmp_path):
    app = tmp_path / "Aplicativos" / "Ipe.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    assert GH.app_do_mac(app / "Contents" / "MacOS" / "Ipe") == app
    assert GH.mac_troca_sozinho(app)
    assert not GH.mac_troca_sozinho(Path("/Volumes/Ipe/Ipe.app")) and not GH.mac_troca_sozinho(None)
    assert not GH.mac_troca_sozinho(Path("/private/var/folders/x/AppTranslocation/y/d/Ipe.app"))


@pytest.mark.skipif(sys.platform == "win32", reason="roteiro de bash")
def test_roteiro_troca_o_aplicativo_e_desfaz_se_falhar(tmp_path):
    """O roteiro de verdade, com hdiutil/ditto/xattr/open de mentira no PATH."""
    falsos = tmp_path / "bin"
    falsos.mkdir()
    dmg_conteudo = tmp_path / "conteudo_do_dmg"
    (dmg_conteudo / "Ipe.app" / "Contents").mkdir(parents=True)
    (dmg_conteudo / "Ipe.app" / "Contents" / "versao.txt").write_text("nova")
    (falsos / "hdiutil").write_text('#!/bin/bash\nif [ "$1" = attach ]; then cp -R "%s"/. "$6"; fi\nexit 0\n'
                                    % dmg_conteudo)
    (falsos / "ditto").write_text('#!/bin/bash\n[ -n "$DITTO_FALHA" ] && exit 1\ncp -R "$1" "$2"\n')
    (falsos / "xattr").write_text("#!/bin/bash\nexit 0\n")
    (falsos / "open").write_text('#!/bin/bash\necho "$@" >> "%s"\n' % (tmp_path / "abertos.txt"))
    for f in falsos.iterdir():
        f.chmod(0o755)
    app = tmp_path / "Aplicativos" / "Ipe.app"
    (app / "Contents").mkdir(parents=True)
    (app / "Contents" / "versao.txt").write_text("antiga")
    dmg = tmp_path / "baixados" / "Ipe-9.9.9-macos-arm64.dmg"
    dmg.parent.mkdir()
    dmg.write_text("dmg")
    import os
    amb = dict(os.environ, PATH=f"{falsos}{os.pathsep}{os.environ['PATH']}")
    cmd = GH.roteiro_mac(dmg, app, pid=2 ** 22 + 12345)            # processo que não existe: não espera
    # 1) o ditto falha: o aplicativo antigo fica como estava e o .dmg abre para trocar à mão
    r = subprocess.run(cmd, env=dict(amb, DITTO_FALHA="1"), timeout=60)
    assert r.returncode == 1 and (app / "Contents" / "versao.txt").read_text() == "antiga"
    assert "FALHOU" in (dmg.parent / "atualizacao_mac.log").read_text()
    assert str(dmg) in (tmp_path / "abertos.txt").read_text()
    # 2) dá certo: troca, sem sobras, e abre o aplicativo
    (tmp_path / "abertos.txt").unlink()
    r = subprocess.run(cmd, env=amb, timeout=60)
    assert r.returncode == 0 and (app / "Contents" / "versao.txt").read_text() == "nova"
    assert "TROCADO" in (dmg.parent / "atualizacao_mac.log").read_text()
    assert not Path(str(app) + ".novo").exists() and not Path(str(app) + ".antigo").exists()
    assert (tmp_path / "abertos.txt").read_text().strip() == str(app)


def test_instalar_no_mac_solta_o_roteiro_e_recusa_onde_nao_da(tmp_path):
    app = tmp_path / "Ipe.app"
    app.mkdir()
    dmg = tmp_path / "Ipe-9.9.9-macos-arm64.dmg"
    dmg.write_text("x")
    soltos = []
    GH.instalar_no_mac(dmg, app, pid=4321, popen=lambda cmd, **k: soltos.append((cmd, k)))
    cmd, k = soltos[0]
    assert cmd[:2] == ["/bin/bash", str(tmp_path / "atualizar_mac.sh")] and cmd[2:] == [str(dmg), str(app), "4321", "1"]
    assert k["start_new_session"] is True
    with pytest.raises(GH.ErroAtualizacao):
        GH.instalar_no_mac(dmg, Path("/Volumes/Ipe/Ipe.app"), pid=1, popen=lambda *a, **k: None)
