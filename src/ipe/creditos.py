"""Créditos: o que o Ipê usa, para quê, com qual licença e onde encontrar (0.99.13).

Pedido dele: *"acrescente e continue acrescentando todas as ferramentas que usamos, com créditos,
licenças e links"*. Esta lista é a fonte única: dela saem a janela "Créditos e licenças" (Ajuda ▸
Sobre o Ipê) e o arquivo CREDITOS.md do repositório (`tools/gerar_creditos.py`).

**Regra para as próximas versões:** dependência nova entra aqui junto com o código que a usa. O teste
`test_creditos.py` reprova pacote do pyproject.toml ou `import` de terceiros sem crédito, e
CREDITOS.md desatualizado.

Campos: nome, para que serve no Ipê, licença, link, onde entra e, quando os autores pedem, a
citação. "Onde entra":
- "programa": vai junto com o Ipê;
- "opcional": instalado à parte, só para quem usa aquela função;
- "segmentação": o ambiente separado da segmentação (TotalSegmentator), baixado uma vez;
- "modelo": pesos de rede neural, baixados à parte;
- "instalador": só para gerar o instalador do Windows;
- "desenvolvimento": só para testar e gerar documentação.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Credito:
    nome: str
    uso: str
    licenca: str
    link: str
    onde: str = "programa"
    citacao: str = ""
    pacotes: tuple = ()          # nomes no pip (pyproject.toml)
    modulos: tuple = ()          # nomes no `import`


CREDITOS: tuple[Credito, ...] = (
    # ------------------------------------------------------------------ o programa
    Credito("Python", "a linguagem do programa", "PSF License", "https://www.python.org"),
    Credito("Qt / PySide6", "a interface: janelas, quadros, menus, rede local",
            "LGPL-3.0 (ou GPL-2.0/3.0)", "https://www.qt.io/qt-for-python",
            pacotes=("PySide6",), modulos=("PySide6", "shiboken6")),
    Credito("pydicom", "leitura e gravação dos arquivos DICOM", "MIT",
            "https://github.com/pydicom/pydicom", pacotes=("pydicom",), modulos=("pydicom",)),
    Credito("pynetdicom", "rede DICOM: C-ECHO, C-FIND, C-MOVE, C-GET, C-STORE, impressora DICOM", "MIT",
            "https://github.com/pydicom/pynetdicom", pacotes=("pynetdicom",), modulos=("pynetdicom",)),
    Credito("pylibjpeg", "decodificação de imagens comprimidas no DICOM", "MIT",
            "https://github.com/pydicom/pylibjpeg", pacotes=("pylibjpeg",)),
    Credito("pylibjpeg-libjpeg", "JPEG e JPEG-LS (biblioteca libjpeg de Thomas Richter)", "GPL-3.0",
            "https://github.com/pydicom/pylibjpeg-libjpeg", pacotes=("pylibjpeg-libjpeg",)),
    Credito("pylibjpeg-openjpeg", "JPEG 2000 (OpenJPEG)", "MIT (OpenJPEG: BSD-2-Clause)",
            "https://github.com/pydicom/pylibjpeg-openjpeg", pacotes=("pylibjpeg-openjpeg",)),
    Credito("pyjpegls", "gravação em JPEG-LS (CharLS) na compressão sem perda", "MIT (CharLS: BSD-3-Clause)",
            "https://github.com/pydicom/pyjpegls", pacotes=("pyjpegls",), modulos=("jpeg_ls",)),
    Credito("imagecodecs (OpenJPH)", "HTJ2K sem perda na cópia de envio do visualizador web: menos bytes na rede e "
            "carga progressiva no navegador", "BSD-3-Clause (OpenJPH: BSD-2-Clause)",
            "https://github.com/cgohlke/imagecodecs", pacotes=("imagecodecs",), modulos=("imagecodecs",)),
    Credito("certifi", "certificados das autoridades (lista da Mozilla) para o HTTPS onde o sistema não os entrega",
            "MPL-2.0", "https://github.com/certifi/python-certifi", pacotes=("certifi",), modulos=("certifi",)),
    Credito("NumPy", "todas as contas com as imagens (janela, MPR, 3D, mapas, medidas)", "BSD-3-Clause",
            "https://numpy.org", pacotes=("numpy",), modulos=("numpy",)),
    Credito("SQLAlchemy", "o banco de dados dos exames (SQLite)", "MIT", "https://www.sqlalchemy.org",
            pacotes=("SQLAlchemy",), modulos=("sqlalchemy",)),
    Credito("SQLite", "o arquivo do banco de dados", "domínio público", "https://www.sqlite.org"),
    Credito("platformdirs", "as pastas de dados e de configuração de cada sistema", "MIT",
            "https://github.com/tox-dev/platformdirs", pacotes=("platformdirs",), modulos=("platformdirs",)),
    Credito("RapidOCR", "OCR das folhas de impressão recebidas (identificar o paciente)", "Apache-2.0",
            "https://github.com/RapidAI/RapidOCR", pacotes=("rapidocr_onnxruntime",),
            modulos=("rapidocr_onnxruntime",)),
    Credito("PaddleOCR (modelos)", "os modelos de leitura de texto que o RapidOCR usa", "Apache-2.0",
            "https://github.com/PaddlePaddle/PaddleOCR", onde="modelo"),
    Credito("ONNX Runtime", "roda as redes neurais na CPU (OCR, densidade mamária)", "MIT",
            "https://onnxruntime.ai", pacotes=("onnxruntime",), modulos=("onnxruntime",)),
    Credito("Pillow", "imagens comuns (PNG/JPG) no OCR de reserva", "MIT-CMU", "https://python-pillow.org",
            onde="opcional", modulos=("PIL",)),
    Credito("Tesseract / pytesseract", "OCR de reserva, quando instalado no computador", "Apache-2.0",
            "https://github.com/tesseract-ocr/tesseract", onde="opcional", modulos=("pytesseract",)),
    Credito("Ollama", "modelo de linguagem local para a IA no texto do laudo (0.99.54), se instalado à parte",
            "MIT", "https://ollama.com", onde="opcional"),
    Credito("API compatível com OpenAI (LM Studio, vLLM, llama.cpp)", "servidor de modelo de linguagem para a IA "
            "no texto do laudo, se o serviço tiver um", "conforme o servidor", "https://platform.openai.com/docs/api-reference",
            onde="opcional"),
    Credito("API da Anthropic (Claude)", "modelo de linguagem para a IA no texto do laudo, com chave própria do "
            "serviço", "serviço da Anthropic", "https://docs.claude.com", onde="opcional"),
    Credito("cryptography", "a AC interna e os certificados HTTPS da rede (0.99.74)",
            "Apache-2.0 ou BSD-3-Clause", "https://cryptography.io", pacotes=("cryptography",),
            modulos=("cryptography",)),
    Credito("7-Zip", "abrir RAR, 7z, ISO e ZIP em Deflate64 na importação (0.99.66), se instalado no computador",
            "LGPL-2.1 (código do unRAR com restrição própria)", "https://www.7-zip.org", onde="opcional"),
    Credito("libarchive (bsdtar, o tar.exe do Windows 10/11)", "abrir RAR, 7z e ISO na importação (0.99.66) "
            "quando não há 7-Zip", "BSD-2-Clause", "https://www.libarchive.org", onde="opcional"),
    Credito("UnRAR (WinRAR)", "abrir RAR na importação (0.99.66), se o WinRAR estiver instalado",
            "licença freeware do UnRAR", "https://www.rarlab.com", onde="opcional"),
    Credito("ReportLab", "o guia do usuário em PDF", "BSD", "https://www.reportlab.com/opensource/",
            onde="desenvolvimento", modulos=("reportlab",)),
    # ------------------------------------------------------------------ visualizador web (0.99.91)
    Credito("Cornerstone3D", "o visualizador web do servidor central: quadros, janela, rolagem, cine (e, nas "
            "próximas fases, MPR, MIP, fusão e medidas)", "MIT", "https://github.com/cornerstonejs/cornerstone3D"),
    Credito("vtk.js (Kitware)", "o desenho em WebGL por baixo do Cornerstone3D", "BSD-3-Clause",
            "https://github.com/Kitware/vtk-js"),
    Credito("dicomParser", "leitura de DICOM no navegador", "MIT", "https://github.com/cornerstonejs/dicomParser"),
    Credito("CharLS (WebAssembly)", "JPEG-LS no navegador", "BSD-3-Clause",
            "https://github.com/team-charls/charls"),
    Credito("OpenJPEG e OpenJPH (WebAssembly)", "JPEG 2000 e HTJ2K no navegador", "BSD-2-Clause",
            "https://github.com/uclouvain/openjpeg"),
    Credito("libjpeg-turbo e libjxl (WebAssembly)", "JPEG e JPEG XL no navegador",
            "IJG/BSD-3-Clause/zlib e BSD-3-Clause", "https://github.com/libjpeg-turbo/libjpeg-turbo"),
    Credito("Vite, TypeScript e Terser", "constroem o visualizador web (src/ipe/web_dist)",
            "MIT, Apache-2.0 e BSD-2-Clause", "https://vite.dev", onde="desenvolvimento"),
    # ------------------------------------------------------------------ inteligência artificial
    Credito("TotalSegmentator", "segmentação de órgãos abdominais, vértebras e discos (TC e RM) e das "
            "estruturas da cefalometria — palato, faringe, hioide, mandíbula e língua (TC; tarefas abertas "
            "head_glands_cavities, headneck_bones_vessels, craniofacial_structures, head_muscles e "
            "headneck_muscles), dos marcos dos níveis linfonodais cervicais e dos nódulos pulmonares (tarefa "
            "aberta lung_nodules, modelo da BLUEMIND AI treinado em parte com o LIDC-IDRI) e da composição corporal "
            "(vértebras, órgãos e a cavidade abdominal da tarefa aberta trunk_cavities) e do fígado, do "
            "baço e dos segmentos de Couinaud na RM (total_mr e liver_segments_mr)",
            "Apache-2.0 (algumas tarefas pedem licença, gratuita para uso não comercial)",
            "https://github.com/wasserth/TotalSegmentator", onde="segmentação",
            citacao="Wasserthal J, et al. TotalSegmentator: robust segmentation of 104 anatomic "
                    "structures in CT images. Radiology: Artificial Intelligence. 2023;5(5):e230024.",
            modulos=("totalsegmentator",)),
    Credito("nnU-Net", "a rede por trás do TotalSegmentator e do autoPET", "Apache-2.0",
            "https://github.com/MIC-DKFZ/nnUNet", onde="segmentação",
            citacao="Isensee F, et al. nnU-Net: a self-configuring method for deep learning-based "
                    "biomedical image segmentation. Nature Methods. 2021;18:203–211.", modulos=("nnunetv2",)),
    Credito("PyTorch", "a biblioteca de redes neurais da segmentação", "BSD-3-Clause", "https://pytorch.org",
            onde="segmentação", modulos=("torch",)),
    Credito("MedSAM2", "segmentar qualquer lesão por uma caixa, propagada aos cortes vizinhos (modelo extra)",
            "Apache-2.0 (código); CC BY-SA 4.0 (pesos)", "https://github.com/bowang-lab/MedSAM2", onde="modelo",
            citacao="Ma J, et al. MedSAM2: Segment Anything in 3D Medical Images and Videos. arXiv 2504.03600; 2025.",
            modulos=("sam2",)),
    Credito("autoPET II (nnU-Net)", "lesões ávidas no PET-FDG, para o MTV e a TLG (modelo extra)",
            "conferir no registro do Zenodo 8362371 (nnU-Net: Apache-2.0)", "https://zenodo.org/records/8362371",
            onde="modelo",
            citacao="Isensee F, et al. Look Ma, no code: fine tuning nnU-Net for the AutoPET II challenge by only "
                    "adjusting its JSON plans. arXiv 2309.13747; 2023."),
    Credito("MONAI", "o SegResNet do glioma (BraTS) — parte captante, necrose e edema (modelo extra)", "Apache-2.0",
            "https://monai.io", onde="segmentação", modulos=("monai",),
            citacao="Myronenko A. 3D MRI brain tumor segmentation using autoencoder regularization. BrainLes "
                    "(MICCAI) 2018."),
    Credito("TotalSpineSeg", "medula, canal, discos e vértebras na RM da coluna — área e índices de compressão por "
            "nível (modelo extra, num ambiente próprio)", "LGPL-3.0", "https://github.com/neuropoly/totalspineseg",
            onde="modelo",
            citacao="Warszawer Y, Molinier N, Valošek J, et al. TotalSpineSeg: Robust Spine Segmentation with "
                    "Landmark-Based Labeling in MRI. arXiv 2411.09344 (2024)."),
    Credito("FLAMeS", "lesões de substância branca no FLAIR — número, volume e regiões (modelo extra, nnU-Net)",
            "CC BY 4.0", "https://zenodo.org/records/17955359", onde="modelo",
            citacao="Dereskewicz E, La Rosa F, et al. FLAMeS: A Robust Deep Learning Model for Automated Multiple "
                    "Sclerosis Lesion Segmentation. Journal of Neuroimaging. 2025;35(5):e70085."),
    Credito("SynthSeg", "segmentação do encéfalo em RM de qualquer contraste e resolução e em TC — índices do "
            "crânio (Evans, 3º ventrículo, ângulo calosal) e volumes dos hipocampos", "Apache-2.0",
            "https://github.com/BBillot/SynthSeg", onde="modelo",
            citacao="Billot B, et al. SynthSeg: Segmentation of brain MRI scans of any contrast and resolution "
                    "without retraining. Medical Image Analysis. 2023;86:102789."),
    Credito("SynthSR", "T1 sintético de 1 mm a partir de uma série 2D do crânio, para o MPR e os índices quando "
            "não há T1 3D (rede reescrita em PyTorch no Ipê, com os pesos originais da versão 1.0)", "Apache-2.0",
            "https://github.com/BBillot/SynthSR", onde="modelo",
            citacao="Iglesias JE, et al. Joint super-resolution and synthesis of 1 mm isotropic MP-RAGE volumes "
                    "from clinical MRI exams with scans of different orientation, resolution and contrast. "
                    "NeuroImage. 2021;237:118206. Iglesias JE, et al. SynthSR: A public AI tool to turn "
                    "heterogeneous clinical brain scans into high-resolution T1-weighted images for 3D "
                    "morphometry. Science Advances. 2023;9(5):eadd3607."),
    Credito("DIPY", "a versão em PyTorch do SynthSeg, no ambiente da segmentação", "BSD-3-Clause",
            "https://dipy.org", onde="segmentação", modulos=("dipy",),
            citacao="Garyfallidis E, et al. Dipy, a library for the analysis of diffusion MRI data. "
                    "Frontiers in Neuroinformatics. 2014;8:8."),
    Credito("h5py", "leitura dos pesos originais do SynthSR (arquivo HDF5 do Keras), no ambiente da segmentação",
            "BSD-3-Clause", "https://www.h5py.org", onde="segmentação", modulos=("h5py",)),
    Credito("SciPy", "reamostragem a 1 mm antes do SynthSR, no ambiente da segmentação", "BSD-3-Clause",
            "https://scipy.org", onde="segmentação", modulos=("scipy",),
            citacao="Virtanen P, et al. SciPy 1.0: fundamental algorithms for scientific computing in Python. "
                    "Nature Methods. 2020;17:261-272."),
    Credito("NiBabel", "troca de volumes (NIfTI) com o ambiente da segmentação", "MIT", "https://nipy.org/nibabel",
            onde="segmentação", modulos=("nibabel",)),
    Credito("Classificador de densidade da NYU", "categoria de densidade mamária (BI-RADS a–d)", "BSD-2-Clause",
            "https://github.com/nyukat/breast_density_classifier", onde="modelo",
            citacao="Wu N, et al. Breast density classification with deep convolutional neural "
                    "networks. ICASSP 2018."),
    # ------------------------------------------------------------------ instalador e desenvolvimento
    Credito("PyInstaller", "empacota o programa para Windows", "GPL-2.0 com exceção do bootloader",
            "https://pyinstaller.org", onde="instalador", modulos=("PyInstaller",)),
    Credito("Inno Setup", "o instalador do Windows", "Inno Setup License (gratuita)",
            "https://jrsoftware.org/isinfo.php", onde="instalador"),
    Credito("pytest", "os testes automáticos", "MIT", "https://pytest.org", onde="desenvolvimento",
            pacotes=("pytest",)),
    Credito("Claude (Anthropic)", "escreve o código a partir dos pedidos do autor, testa e documenta",
            "serviço da Anthropic", "https://www.anthropic.com/claude", onde="desenvolvimento"),
)

#: Programas que inspiraram o Ipê. Nenhum código deles está aqui; os nomes são marcas dos donos.
INSPIRACOES: tuple[tuple[str, str], ...] = (
    ("OsiriX", "https://www.osirix-viewer.com"),
    ("Horos", "https://horosproject.org"),
    ("Weasis", "https://weasis.org"),
    ("GE AW Server (manuais)", "https://www.gehealthcare.com"),
)

NOME_DO_ONDE = {
    "programa": "vai com o programa",
    "opcional": "opcional, instalado à parte",
    "segmentação": "ambiente da segmentação, baixado à parte",
    "modelo": "modelo de IA, baixado à parte",
    "instalador": "só para gerar o instalador",
    "desenvolvimento": "desenvolvimento",
}


def markdown() -> str:
    """O CREDITOS.md do repositório (o arquivo é gerado: não editar à mão)."""
    linhas = [
        "# Créditos e licenças",
        "",
        "O Ipê só existe porque muita gente compartilhou seu trabalho em código aberto. Esta é a lista do",
        "que ele usa, para quê, com qual licença e onde encontrar. O Ipê é distribuído sob",
        "[GPL-3.0-or-later](LICENSE).",
        "",
        "*Arquivo gerado por `tools/gerar_creditos.py` a partir de `src/ipe/creditos.py` — não edite à mão.*",
        "",
    ]
    for onde, titulo in NOME_DO_ONDE.items():
        itens = [c for c in CREDITOS if c.onde == onde]
        if not itens:
            continue
        linhas += [f"## {titulo[0].upper() + titulo[1:]}", "", "| Ferramenta | Para que serve | Licença |",
                   "|---|---|---|"]
        for c in itens:
            linhas.append(f"| [{c.nome}]({c.link}) | {c.uso} | {c.licenca} |")
        linhas.append("")
    citadas = [c for c in CREDITOS if c.citacao]
    if citadas:
        linhas += ["## Como citar", "", "Os autores destas ferramentas pedem que trabalhos que as usam citem:", ""]
        linhas += [f"- **{c.nome}:** {c.citacao}" for c in citadas]
        linhas.append("")
    linhas += ["## Inspiração", "",
               "Programas que inspiraram o Ipê. Nenhum código deles está aqui; os nomes são marcas dos donos.", ""]
    linhas += [f"- [{n}]({u})" for n, u in INSPIRACOES]
    linhas.append("")
    return "\n".join(linhas)


def html() -> str:
    """A mesma lista, para a janela do programa."""
    partes = []
    for onde, titulo in NOME_DO_ONDE.items():
        itens = [c for c in CREDITOS if c.onde == onde]
        if not itens:
            continue
        partes.append(f"<h4>{titulo[0].upper() + titulo[1:]}</h4><table cellpadding='3'>")
        for c in itens:
            partes.append(f"<tr><td><a href='{c.link}'>{c.nome}</a></td><td>{c.uso}</td>"
                          f"<td><i>{c.licenca}</i></td></tr>")
        partes.append("</table>")
    citadas = [c for c in CREDITOS if c.citacao]
    if citadas:
        partes.append("<h4>Como citar</h4><ul>")
        partes += [f"<li><b>{c.nome}:</b> {c.citacao}</li>" for c in citadas]
        partes.append("</ul>")
    partes.append("<h4>Inspiração</h4><p>" + " · ".join(f"<a href='{u}'>{n}</a>" for n, u in INSPIRACOES)
                  + "<br><small>Nenhum código deles está no Ipê; os nomes são marcas dos donos.</small></p>")
    return "".join(partes)
