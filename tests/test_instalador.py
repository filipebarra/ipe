"""O empacotamento: receita do PyInstaller, instalador e o que o programa precisa saber
sobre estar empacotado. Roda em qualquer máquina — não empacota nada, confere a receita."""
import struct
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
INST = RAIZ / "installer"


def _texto(nome: str) -> str:
    caminho = INST / nome
    assert caminho.exists(), f"falta {caminho}"
    return caminho.read_text(encoding="utf-8")


# ------------------------------------------------------------------ receita
def test_receita_leva_os_idiomas_e_os_decodificadores():
    spec = _texto("ipe.spec")
    assert '"ipe/locale"' in spec              # o destino tem que ser este
    for chave in ("pylibjpeg", "openjpeg", "gdcm", "sqlalchemy.dialects.sqlite"):
        assert chave in spec, f"{chave} não está nos imports escondidos"
    assert 'collect_submodules("pydicom")' in spec
    idiomas = sorted(p.name for p in (RAIZ / "src" / "ipe" / "locale").glob("*.json"))
    assert idiomas == ["en.json", "es.json", "pt-BR.json"]


def test_receita_gera_os_dois_executaveis():
    spec = _texto("ipe.spec")
    assert spec.count("EXE(") == 2
    assert 'name="Ipe"' in spec and 'name="ipe-cli"' in spec
    assert "console=False" in spec and "console=True" in spec
    assert "exe, exe_cli, a.binaries" in spec          # os dois entram na mesma pasta


def test_receita_nao_leva_o_que_nao_usa():
    spec = _texto("ipe.spec")
    for fora in ("PySide6.QtWebEngineCore", "PySide6.Qt3DRender", "tkinter", "matplotlib"):
        assert fora in spec
    # o que o programa usa de verdade não pode estar na lista de exclusão
    for dentro in ("PySide6.QtPrintSupport", "PySide6.QtNetwork"):
        assert dentro not in spec


# ------------------------------------------------------------------ instalador
def test_instalador_nao_pede_administrador():
    iss = _texto("ipe.iss")
    assert "PrivilegesRequired=lowest" in iss
    assert "{localappdata}\\Programs" in iss
    assert "{pf}" not in iss and "{commonpf}" not in iss


def test_instalador_nao_apaga_os_dados_do_usuario():
    iss = _texto("ipe.iss")
    assert "[UninstallDelete]" not in iss
    assert "banco" in iss.lower()                      # a decisão está escrita no arquivo


def test_instalador_usa_o_executavel_certo_para_cada_coisa():
    iss = _texto("ipe.iss")
    assert 'Parameters: "register-url"' in iss and "{#Cli}" in iss
    assert 'Parameters: "unregister-url"' in iss       # desinstalar tira o registro
    assert 'Filename: "{app}\\{#Exe}"; Description:' in iss   # "abrir agora" usa o de janela


def test_arquivos_do_windows_tem_quebra_de_linha_do_windows():
    """O cmd.exe engasga com .bat de quebra Unix: a janela pisca e fecha sem mensagem.
    Foi exatamente isso que aconteceu na primeira tentativa do usuário."""
    for nome in ("build_windows.bat", "conferir.bat", "ipe.iss"):
        dados = (INST / nome).read_bytes()
        assert b"\r\n" in dados, f"{nome} está com quebra de linha Unix"
        assert b"\n" not in dados.replace(b"\r\n", b""), f"{nome} tem linha sem CR"
    outro = RAIZ / "instalar.bat"          # fora da pasta do instalador, nem sempre copiado
    if outro.exists():
        assert b"\n" not in outro.read_bytes().replace(b"\r\n", b"")


def test_build_nao_deixa_o_cmd_engolir_o_maior_que():
    """`pip install pyinstaller>=6.0` sem aspas vira redirecionamento no cmd:
    o PyInstaller não é instalado e nasce um arquivo chamado `=6.0`."""
    bat = _texto("build_windows.bat")
    assert '"pyinstaller>=6.0"' in bat
    assert "install -e \".\" pyinstaller>" not in bat


def test_build_avisa_em_vez_de_fechar_a_janela():
    bat = _texto("build_windows.bat")
    assert bat.rstrip().endswith("pause")          # duplo clique não fecha calado
    assert bat.count("goto :fim") >= 6             # todo erro passa pelo pause
    assert "where python" in bat                   # sem o py launcher, tenta python


def test_o_harness_copia_as_pastas_que_os_testes_conferem():
    """Já falhou duas vezes: teste que lê arquivo de `installer/` ou `tools/` falha por ausência,
    não por defeito, quando o harness não copia a pasta."""
    for pasta in ("installer", "tools"):
        assert (RAIZ / pasta).is_dir(), f"{pasta} não foi copiada para a máquina de teste"


def test_build_le_a_versao_sem_for_f():
    """`for /f ('"exe" -c "..."')` quebra no cmd quando o comando começa com aspas —
    foi o segundo tropeço na máquina do usuário. Gravar num arquivo e ler é imune."""
    bat = _texto("build_windows.bat")
    assert not [l for l in bat.splitlines() if l.strip().lower().startswith("for /f")]
    assert "set /p VERSAO=<" in bat


def test_script_de_build_confere_antes_de_empacotar():
    bat = _texto("build_windows.bat")
    for passo in ("make_icon.py", "PyInstaller", "verifica.py", "Compress-Archive", "ISCC"):
        assert passo in bat
    assert bat.index("verifica.py") < bat.index("Compress-Archive")   # confere antes de empacotar


def test_icone_do_windows_esta_pronto():
    dados = (INST / "ipe.ico").read_bytes()
    reservado, tipo, quantos = struct.unpack("<HHH", dados[:6])
    assert reservado == 0 and tipo == 1 and quantos >= 5
    for i in range(quantos):
        entrada = dados[6 + 16 * i:22 + 16 * i]
        _w, _h, _c, _r, _p, _bits, tam, off = struct.unpack("<BBBBHHII", entrada)
        assert dados[off:off + 8] == b"\x89PNG\r\n\x1a\n"    # cada tamanho é um PNG válido
        assert tam > 100


# ------------------------------------------------------------------ o programa empacotado
def test_programa_sabe_quando_esta_empacotado(monkeypatch):
    from ipe.core import runtime as R
    assert R.frozen() is False
    assert " -m ipe" in R.app_command()

    monkeypatch.setattr(R.sys, "frozen", True, raising=False)
    assert R.frozen() is True
    cmd = R.app_command("--minimized")
    assert " -m ipe" not in cmd and cmd.endswith("--minimized")


def test_empacotado_aponta_para_o_executavel_de_janela(monkeypatch, tmp_path):
    from ipe.core import runtime as R
    janela = tmp_path / "Ipe.exe"
    janela.write_text("x")
    monkeypatch.setattr(R.sys, "frozen", True, raising=False)
    monkeypatch.setattr(R.sys, "executable", str(tmp_path / "ipe-cli.exe"))
    assert R.app_exe() == janela        # quem registra link aponta para a interface


def test_idiomas_saem_da_pasta_do_pacote(monkeypatch, tmp_path):
    from ipe.core import i18n
    from ipe.core import runtime as R
    assert sorted(p.name for p in i18n.bundled_dir().glob("*.json")) == \
        ["en.json", "es.json", "pt-BR.json"]
    (tmp_path / "ipe" / "locale").mkdir(parents=True)
    monkeypatch.setattr(R.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert i18n.bundled_dir() == tmp_path / "ipe" / "locale"


def test_desregistrar_o_link_existe_na_linha_de_comando():
    from ipe.__main__ import _parser
    args = _parser().parse_args(["unregister-url"])
    assert args.cmd == "unregister-url"
    from ipe.network.external import unregister_url_scheme
    assert callable(unregister_url_scheme)


# ------------------------------------------- não empacotar a versão de ontem
def test_o_info_diz_a_versao():
    """Sem isso não há como saber qual pacote é qual — e foi assim que se rodou o instalador 0.35."""
    from ipe.__main__ import main as _m          # noqa: F401 - só para garantir o import
    fonte = (RAIZ / "src" / "ipe" / "__main__.py").read_text(encoding="utf-8")
    assert 'print(f"Versão:' in fonte


def test_a_conferencia_recusa_pacote_de_outra_versao():
    import importlib.util
    spec = importlib.util.spec_from_file_location("verifica", RAIZ / "installer" / "verifica.py")
    v = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v)
    from ipe import __version__
    assert v.versao_do_codigo() == __version__
    assert v.versao_confere(f"Versão:        {__version__}\nBanco: x") == 0
    assert v.versao_confere("Versão:        0.0.1\nBanco: x") == 1     # pacote velho
    assert v.versao_confere("Banco: x") == 1                            # não respondeu


def test_o_build_tira_os_pacotes_antigos_da_frente():
    texto = (RAIZ / "installer" / "build_windows.bat").read_text(encoding="utf-8")
    assert "dist\\antigos" in texto
    assert "Ipe-*-instalador.exe" in texto
    assert "del " not in texto.lower().split("dist\\antigos")[1][:400]  # guarda, não apaga


def test_o_build_diz_qual_arquivo_executar():
    texto = (RAIZ / "installer" / "build_windows.bat").read_text(encoding="utf-8")
    assert "Instale executando ESTE arquivo" in texto
    assert "Ipe-%VERSAO%-instalador.exe" in texto


def test_a_receita_leva_o_modelo_de_ia_quando_ele_existe():
    texto = (RAIZ / "installer" / "ipe.spec").read_text(encoding="utf-8")
    assert '"modelos"' in texto and "*.onnx" in texto
    assert "onnxruntime" in texto
    # e o programa procura exatamente onde o pacote põe
    from ipe.ai import densidade_nyu as N
    assert any(p.name == "modelos" for p in N.pastas())


def _verifica():
    import importlib.util
    spec = importlib.util.spec_from_file_location("verifica", RAIZ / "installer" / "verifica.py")
    v = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v)
    return v


def test_a_versao_e_lida_mesmo_com_o_acento_estragado():
    """Codificação errada na saída do executável não pode virar "pacote reprovado".

    O executável imprime "Versão"; se o console entrega "VersÃ£o", a conferência antiga dizia
    que o pacote não respondeu a versão — reprovava um pacote bom por causa de um acento.
    """
    from ipe import __version__
    v = _verifica()
    assert v.versao_confere(f"VersÃ£o:        {__version__}\nBanco: x") == 0


def test_a_conferencia_guarda_o_motivo_num_arquivo(tmp_path, monkeypatch, capsys):
    """Reprovar sem dizer por quê é o mesmo que não conferir.

    Foi o que aconteceu: sobrou na tela o "[ERRO] nao passou na conferencia" e o motivo,
    impresso uma linha acima, se perdeu.
    """
    v = _verifica()
    monkeypatch.setattr(v, "RAIZ", tmp_path)
    monkeypatch.setattr(v, "main", lambda: (print("  Faltam arquivos de idioma."), 1)[1])
    assert v.com_registro() == 1
    relato = (tmp_path / "dist" / "conferencia.txt").read_text(encoding="utf-8")
    assert "Faltam arquivos de idioma." in relato
    assert v.versao_do_codigo() in relato


def test_a_conferencia_guarda_o_motivo_mesmo_quando_ela_propria_quebra(tmp_path, monkeypatch):
    v = _verifica()
    monkeypatch.setattr(v, "RAIZ", tmp_path)

    def explode():
        raise RuntimeError("faltou o executável")

    monkeypatch.setattr(v, "main", explode)
    assert v.com_registro() == 1
    relato = (tmp_path / "dist" / "conferencia.txt").read_text(encoding="utf-8")
    assert "faltou o executável" in relato


def test_o_build_aponta_para_o_relato_da_conferencia():
    texto = (RAIZ / "installer" / "build_windows.bat").read_text(encoding="utf-8")
    assert "dist\\conferencia.txt" in texto
    conf = (RAIZ / "installer" / "conferir.bat").read_text(encoding="utf-8")
    assert "verifica.py" in conf and "pause" in conf


def test_bloqueio_do_windows_nao_e_pacote_reprovado(tmp_path, monkeypatch):
    """O Windows recusar um .exe novo não diz nada sobre o pacote.

    Tratado como reprovação, jogava fora um pacote bom e ainda escondia a causa: a conferência
    morria com um traceback de OSError.
    """
    v = _verifica()
    monkeypatch.setattr(v, "RAIZ", tmp_path)

    def bloqueia(*a, **k):
        raise OSError(4551, "Uma política de Controle de Aplicativo bloqueou este arquivo")

    monkeypatch.setattr(v.subprocess, "run", bloqueia)
    monkeypatch.setattr(v, "CLI", tmp_path / "ipe-cli.exe")
    monkeypatch.setattr(v, "EXE", tmp_path / "Ipe.exe")
    for alvo in (v.CLI, v.EXE):
        alvo.write_bytes(b"x")
    assert v.com_registro() == v.BLOQUEADO
    relato = (tmp_path / "dist" / "conferencia.txt").read_text(encoding="utf-8")
    assert "NÃO FOI POSSÍVEL CONFERIR" in relato
    assert "assinatura" in relato                      # diz o que resolve
    assert "definitivo" in relato                      # e avisa que desligar não tem volta


def test_outro_erro_do_sistema_continua_reprovando(tmp_path, monkeypatch):
    v = _verifica()
    monkeypatch.setattr(v, "RAIZ", tmp_path)
    monkeypatch.setattr(v.subprocess, "run",
                        lambda *a, **k: (_ for _ in ()).throw(OSError(2, "não achei")))
    monkeypatch.setattr(v, "CLI", tmp_path / "cli.exe")
    monkeypatch.setattr(v, "EXE", tmp_path / "app.exe")
    for alvo in (v.CLI, v.EXE):
        alvo.write_bytes(b"x")
    assert v.com_registro() == 1


def test_o_build_gera_mesmo_quando_nao_consegue_conferir():
    """Avisar e seguir, em vez de só falhar — e deixar o estado na tela."""
    texto = (RAIZ / "installer" / "build_windows.bat").read_text(encoding="utf-8")
    assert '"%CONF%"=="2"' in texto
    assert "SEM conferencia" in texto
    assert "NAO foi conferido" in texto
    # a reprovação de verdade continua impedindo tudo
    assert "Nada foi gerado" in texto


def test_o_log_diz_a_versao_ao_abrir():
    """Relato de defeito sem versão é relato de defeito de versão nenhuma.

    O log registrava só a pasta de dados: não dava para saber se aquilo veio do instalado, do
    portátil ou do código vivo — e a diferença entre eles foi exatamente o que confundiu a 0.43.
    """
    texto = (RAIZ / "src" / "ipe" / "app.py").read_text(encoding="utf-8")
    assert "Ipê %s" in texto and "__version__" in texto
    assert "empacotado" in texto and "código" in texto
