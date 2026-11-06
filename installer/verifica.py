"""Confere o pacote recém-gerado antes de empacotar no instalador.

Roda o executável de verdade e exige que ele responda — é o que separa "o PyInstaller não
deu erro" de "o programa abre". Testa também o que costuma faltar em pacote: os arquivos
de idioma e os decodificadores de imagem comprimida.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / "dist" / "Ipe"
SUFIXO = ".exe" if sys.platform == "win32" else ""
EXE = PASTA / f"Ipe{SUFIXO}"
CLI = PASTA / f"ipe-cli{SUFIXO}"

CONFERIR = """
import sys, json
from pathlib import Path
from ipe.core import runtime as R, i18n
from ipe import __version__
saida = {"versao": __version__, "empacotado": R.frozen(), "comando": R.app_command()}
pasta = i18n.bundled_dir()
saida["idiomas"] = sorted(p.name for p in pasta.glob("*.json")) if pasta.exists() else []
try:
    import pydicom, pynetdicom, sqlalchemy, numpy
    saida["bibliotecas"] = True
except Exception as e:
    saida["bibliotecas"] = str(e)
try:
    from pydicom.pixels import decoders
    saida["decodificadores"] = True
except Exception as e:
    saida["decodificadores"] = str(e)
print("RESULTADO " + json.dumps(saida))
"""


BLOQUEADO = 2        # não foi possível conferir — não é o mesmo que reprovar


class Bloqueio(Exception):
    """O sistema operacional não deixou o executável rodar."""


def roda(args: list[str], timeout: int, **extra) -> subprocess.CompletedProcess:
    """Roda o executável do pacote e separa "o programa não presta" de "o Windows não deixou".

    O Controle de Aplicativo do Windows recusa .exe novo, sem assinatura e sem reputação. Isso
    não diz nada sobre o pacote — e, tratado como reprovação, jogava fora um pacote bom.
    """
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, **extra)
    except OSError as e:
        codigo = getattr(e, "winerror", None) or 0
        texto = str(e).lower()
        if codigo in (1260, 4551) or "controle de aplicativo" in texto \
                or "application control" in texto or "blocked by policy" in texto:
            raise Bloqueio(
                "O Windows bloqueou o executável recém-gerado "
                f"(Controle de Aplicativo / Smart App Control): {e}") from e
        raise


def main() -> int:
    for alvo in (EXE, CLI):
        if not alvo.exists():
            print(f"Não achei o executável: {alvo}")
            return 1
    r = roda([str(CLI), "info"], 180)
    if r.returncode != 0 or "banco" not in (r.stdout or "").lower():
        print("O executável de linha de comando não respondeu ao 'info':")
        print(r.stdout[-2000:], r.stderr[-2000:])
        return 1
    print("  'info' respondeu com os caminhos.")
    if versao_confere(r.stdout or "") != 0:
        return 1
    pasta = PASTA
    idiomas = list((pasta / "_internal" / "ipe" / "locale").glob("*.json")) or \
        list((pasta / "ipe" / "locale").glob("*.json"))
    if len(idiomas) < 3:
        print(f"  Faltam arquivos de idioma no pacote: achei {len(idiomas)}, esperava 3.")
        return 1
    print(f"  {len(idiomas)} arquivos de idioma no pacote.")
    guia = list((pasta / "_internal" / "ipe" / "ajuda").glob("*.pdf")) or \
        list((pasta / "ipe" / "ajuda").glob("*.pdf"))
    if not guia:
        print("  Falta o guia do usuário (PDF) no pacote: o F1 não teria o que abrir.")
        return 1
    print("  Guia do usuário no pacote.")
    # segmentação de órgãos (0.98): o trabalhador e o instalador vão junto; o ambiente pesado, não
    inst = "instalar_segmentacao.bat" if sys.platform == "win32" else "instalar_segmentacao.sh"
    for rel in (("ipe", "ai", "totalseg_worker.py"), ("ipe", "ai", "instalar_modelos_extras.py"), ("ipe", inst)):
        if not ((pasta / "_internal").joinpath(*rel).exists() or pasta.joinpath(*rel).exists()):
            print(f"  Falta no pacote: {'/'.join(rel)} — sem ele a segmentação de órgãos não roda/instala.")
            return 1
    print("  Segmentação de órgãos: trabalhador e instalador no pacote.")
    return ida_e_volta()


def versao_do_codigo() -> str:
    fonte = RAIZ / "src" / "ipe" / "__init__.py"
    if not fonte.exists():
        return ""
    texto = fonte.read_text(encoding="utf-8")
    achou = re.search(r'__version__\s*=\s*"([^"]+)"', texto)
    return achou.group(1) if achou else ""


def versao_confere(saida: str) -> int:
    """O pacote tem que ser **o código de agora**.

    Sem isto, um empacotamento que reaproveitou algo antigo passa em tudo e só aparece quando o
    usuário abre o programa e não encontra o que foi feito ontem — que foi exatamente o que
    aconteceu na 0.40: rodou-se um instalador velho, e não havia nada dizendo qual era.
    """
    esperada = versao_do_codigo()
    # \S* no meio do "Versão" de propósito: se a saída do executável vier com o acento
    # estragado por diferença de codificação, a versão continua sendo lida.
    achou = re.search(r"Vers\S*o:\s*([0-9][^\s]*)", saida)
    do_pacote = achou.group(1) if achou else ""
    if not esperada:
        print("  Não consegui ler a versão do código-fonte.")
        return 1
    if do_pacote != esperada:
        print(f"  O pacote diz ser a versão {do_pacote or '(não respondeu)'}, "
              f"mas o código-fonte está na {esperada}.")
        return 1
    print(f"  O pacote é a versão {do_pacote}, a mesma do código.")
    return 0


def explicacao_do_bloqueio() -> str:
    return (
        "\nO pacote pode estar perfeito: o que aconteceu é que o Windows se recusou a executar\n"
        "um programa novo, sem assinatura digital e sem reputação. Isso vai acontecer também com\n"
        "quem instalar o programa num computador com esse controle ligado.\n"
        "\nO que dá para fazer:\n"
        "  1. Ver o estado do controle: Segurança do Windows → Controle de aplicativos e navegador\n"
        "     → Smart App Control (Controle de aplicativo inteligente).\n"
        "  2. Desligá-lo neste computador de desenvolvimento. Atenção: desligar é definitivo —\n"
        "     só volta reinstalando o Windows.\n"
        "  3. Para distribuir de verdade, assinar o executável com um certificado de código\n"
        "     reconhecido pela Microsoft. É o único caminho que resolve na máquina dos outros.\n")


def ida_e_volta() -> int:
    """Gera fantomas e importa, com banco novo: prova que o pacote lê e escreve DICOM.

    É o teste que pega o que falta de verdade num pacote — decodificador de imagem,
    dialeto do SQLite, numpy —, coisas que só quebram quando o programa trabalha.
    """
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        casa = Path(tmp) / "casa"
        amostra = Path(tmp) / "amostra"
        env = dict(os.environ, DICOMVIEWER_HOME=str(casa))
        g = roda([str(CLI), "sample", str(amostra)], 600, env=env)
        if g.returncode != 0 or not list(amostra.rglob("*.dcm")):
            print("  Não consegui gerar os exames de teste:", g.stdout[-800:], g.stderr[-800:])
            return 1
        quantos = len(list(amostra.rglob("*.dcm")))
        print(f"  {quantos} arquivos de teste gerados.")
        i = roda([str(CLI), "import", str(amostra)], 900, env=env)
        saida = (i.stdout or "") + (i.stderr or "")
        if i.returncode != 0 or "com erro" not in saida:
            print("  A importação não terminou bem:", saida[-1200:])
            return 1
        if "0 com erro" not in saida:
            print("  A importação teve erros:", saida[-1200:])
            return 1
        print("  Importação sem erros, com banco novo.")
    print("Pacote conferido.")
    return 0


class _Duplo:
    """Escreve na tela e no arquivo ao mesmo tempo.

    O motivo da reprovação é a única coisa que interessa quando a conferência falha, e era
    justamente o que se perdia: ficava só na tela, rolava, e sobrava o "[ERRO]" sem causa.
    """

    def __init__(self, tela, arquivo):
        self._tela = tela
        self._arquivo = arquivo

    def write(self, texto):
        self._tela.write(texto)
        try:
            self._arquivo.write(texto)
        except Exception:
            pass
        return len(texto)

    def flush(self):
        self._tela.flush()
        try:
            self._arquivo.flush()
        except Exception:
            pass


def com_registro() -> int:
    import datetime
    destino = RAIZ / "dist" / "conferencia.txt"
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8", errors="replace") as f:
        f.write(f"Conferência de {datetime.datetime.now():%d/%m/%Y %H:%M} — "
                f"código na versão {versao_do_codigo()}\n\n")
        antes = sys.stdout
        sys.stdout = _Duplo(antes, f)
        try:
            codigo = main()
        except Bloqueio as e:
            print(f"\nNÃO FOI POSSÍVEL CONFERIR: {e}")
            print(explicacao_do_bloqueio())
            codigo = BLOQUEADO
        except Exception:
            import traceback
            traceback.print_exc(file=sys.stdout)
            codigo = 1
        finally:
            sys.stdout = antes
    print(f"\nO relato completo ficou em: {destino}")
    return codigo


if __name__ == "__main__":
    raise SystemExit(com_registro())
