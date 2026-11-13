"""Ipê — visualizador DICOM para pesquisa e ensino."""

__version__ = "0.100.40"
APP_NAME = "Ipê"
#: o nome sem acento, para onde acento não cabe: arquivos, executáveis e campos DICOM
APP_ASCII = "Ipe"
#: até a 0.99.10 o programa se chamava DicomViewer. A pasta de dados (banco, exames, configurações)
#: continua com esse nome: quem atualiza abre exatamente o que tinha.
DATA_NAME = "DicomViewer"
NOT_FOR_DIAGNOSIS = "Não destinado a uso diagnóstico"
#: o que o programa grava no Manufacturer dos objetos DICOM — o nome novo e o antigo
FABRICANTES_NOSSOS = ("Ipe", "Ipê", "DicomViewer")


def _sem_gdcm() -> None:
    """0.100.29: o GDCM não decodifica mais nada dentro do programa.

    O pydicom tentava o GDCM **primeiro** em todo arquivo comprimido, e o GDCM, quando o cabeçalho DICOM não
    combina com o quadro (linhas, colunas, amostras ou fotometria diferentes do que está no JPEG), solta uma
    exceção de C++ que ninguém pega: o processo inteiro é encerrado, sem aviso — foi o "fechou sozinho" do Mac.
    Com 2.200 arquivos estragados de propósito (`tools/diag_fuzz.py`), só o GDCM matou o processo (130 vezes);
    pylibjpeg, pyjpegls e Pillow devolveram erro de Python, que o programa trata.

    Antes do pydicom ser importado basta impedir o `import gdcm`; se ele já foi, tira o GDCM de cada
    decodificador e codificador.
    """
    import sys
    if "pydicom" in sys.modules:
        try:
            from pydicom.pixels.decoders.base import _PIXEL_DATA_DECODERS
            from pydicom.pixels.encoders.base import _PIXEL_DATA_ENCODERS
            for tabela in (_PIXEL_DATA_DECODERS, _PIXEL_DATA_ENCODERS):
                for item in tabela.values():
                    try:
                        item[0].remove_plugin("gdcm")
                    except Exception:  # noqa: BLE001 - já não tinha
                        pass
        except Exception:  # noqa: BLE001 - pydicom de outra versão: fica o bloqueio do import
            pass
    sys.modules["gdcm"] = None        # type: ignore[assignment]  # `import gdcm` passa a dar ImportError


def _certificados_https() -> None:
    """0.100.31: HTTPS no Mac (e no Linux fora do padrão Debian) — o Python que vai dentro do pacote procura os
    certificados das autoridades numa pasta que só existe na máquina que montou o pacote; toda conexão HTTPS conferida
    (procurar atualização no GitHub, baixar modelos, DICOMweb, laudo por IA) falhava com CERTIFICATE_VERIFY_FAILED.
    Quando o sistema não entrega os certificados, valem os do certifi (a lista da Mozilla). No Windows o Python usa
    o repositório do sistema e nada muda; quem definiu SSL_CERT_FILE/SSL_CERT_DIR continua mandando."""
    import os
    import sys
    if sys.platform == "win32" or os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR"):
        return
    try:
        import ssl
        onde = ssl.get_default_verify_paths()
        if onde.cafile and os.path.isfile(onde.cafile):
            return
        if onde.capath and os.path.isdir(onde.capath) and any(os.scandir(onde.capath)):
            return
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
    except Exception:  # noqa: BLE001 - sem certifi: fica como estava
        pass


_sem_gdcm()
_certificados_https()
#: o fim da descrição das séries que o programa grava ("Medidas (Ipe)", "Medidas (DicomViewer)")
MARCAS_NOSSAS = tuple(f"({n})" for n in FABRICANTES_NOSSOS)
