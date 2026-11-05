"""Ipê — visualizador DICOM para pesquisa e ensino."""

__version__ = "0.99.73"
APP_NAME = "Ipê"
#: o nome sem acento, para onde acento não cabe: arquivos, executáveis e campos DICOM
APP_ASCII = "Ipe"
#: até a 0.99.10 o programa se chamava DicomViewer. A pasta de dados (banco, exames, configurações)
#: continua com esse nome: quem atualiza abre exatamente o que tinha.
DATA_NAME = "DicomViewer"
NOT_FOR_DIAGNOSIS = "Não destinado a uso diagnóstico"
#: o que o programa grava no Manufacturer dos objetos DICOM — o nome novo e o antigo
FABRICANTES_NOSSOS = ("Ipe", "Ipê", "DicomViewer")
#: o fim da descrição das séries que o programa grava ("Medidas (Ipe)", "Medidas (DicomViewer)")
MARCAS_NOSSAS = tuple(f"({n})" for n in FABRICANTES_NOSSOS)
