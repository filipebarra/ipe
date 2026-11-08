# Créditos e licenças

O Ipê só existe porque muita gente compartilhou seu trabalho em código aberto. Esta é a lista do
que ele usa, para quê, com qual licença e onde encontrar. O Ipê é distribuído sob
[GPL-3.0-or-later](LICENSE).

*Arquivo gerado por `tools/gerar_creditos.py` a partir de `src/ipe/creditos.py` — não edite à mão.*

## Vai com o programa

| Ferramenta | Para que serve | Licença |
|---|---|---|
| [Python](https://www.python.org) | a linguagem do programa | PSF License |
| [Qt / PySide6](https://www.qt.io/qt-for-python) | a interface: janelas, quadros, menus, rede local | LGPL-3.0 (ou GPL-2.0/3.0) |
| [pydicom](https://github.com/pydicom/pydicom) | leitura e gravação dos arquivos DICOM | MIT |
| [pynetdicom](https://github.com/pydicom/pynetdicom) | rede DICOM: C-ECHO, C-FIND, C-MOVE, C-GET, C-STORE, impressora DICOM | MIT |
| [pylibjpeg](https://github.com/pydicom/pylibjpeg) | decodificação de imagens comprimidas no DICOM | MIT |
| [pylibjpeg-libjpeg](https://github.com/pydicom/pylibjpeg-libjpeg) | JPEG e JPEG-LS (biblioteca libjpeg de Thomas Richter) | GPL-3.0 |
| [pylibjpeg-openjpeg](https://github.com/pydicom/pylibjpeg-openjpeg) | JPEG 2000 (OpenJPEG) | MIT (OpenJPEG: BSD-2-Clause) |
| [pyjpegls](https://github.com/pydicom/pyjpegls) | gravação em JPEG-LS (CharLS) na compressão sem perda | MIT (CharLS: BSD-3-Clause) |
| [GDCM / python-gdcm](https://github.com/tfmoraes/python-gdcm) | decodificador de reserva para arquivos DICOM incomuns | BSD-3-Clause (GDCM); Apache-2.0 (pacote Python) |
| [NumPy](https://numpy.org) | todas as contas com as imagens (janela, MPR, 3D, mapas, medidas) | BSD-3-Clause |
| [SQLAlchemy](https://www.sqlalchemy.org) | o banco de dados dos exames (SQLite) | MIT |
| [SQLite](https://www.sqlite.org) | o arquivo do banco de dados | domínio público |
| [platformdirs](https://github.com/tox-dev/platformdirs) | as pastas de dados e de configuração de cada sistema | MIT |
| [RapidOCR](https://github.com/RapidAI/RapidOCR) | OCR das folhas de impressão recebidas (identificar o paciente) | Apache-2.0 |
| [ONNX Runtime](https://onnxruntime.ai) | roda as redes neurais na CPU (OCR, densidade mamária) | MIT |
| [cryptography](https://cryptography.io) | a AC interna e os certificados HTTPS da rede (0.99.74) | Apache-2.0 ou BSD-3-Clause |
| [Cornerstone3D](https://github.com/cornerstonejs/cornerstone3D) | o visualizador web do servidor central: quadros, janela, rolagem, cine (e, nas próximas fases, MPR, MIP, fusão e medidas) | MIT |
| [vtk.js (Kitware)](https://github.com/Kitware/vtk-js) | o desenho em WebGL por baixo do Cornerstone3D | BSD-3-Clause |
| [dicomParser](https://github.com/cornerstonejs/dicomParser) | leitura de DICOM no navegador | MIT |
| [CharLS (WebAssembly)](https://github.com/team-charls/charls) | JPEG-LS no navegador: as imagens do banco vão como estão | BSD-3-Clause |
| [OpenJPEG e OpenJPH (WebAssembly)](https://github.com/uclouvain/openjpeg) | JPEG 2000 e HTJ2K no navegador | BSD-2-Clause |
| [libjpeg-turbo e libjxl (WebAssembly)](https://github.com/libjpeg-turbo/libjpeg-turbo) | JPEG e JPEG XL no navegador | IJG/BSD-3-Clause/zlib e BSD-3-Clause |

## Opcional, instalado à parte

| Ferramenta | Para que serve | Licença |
|---|---|---|
| [Pillow](https://python-pillow.org) | imagens comuns (PNG/JPG) no OCR de reserva | MIT-CMU |
| [Tesseract / pytesseract](https://github.com/tesseract-ocr/tesseract) | OCR de reserva, quando instalado no computador | Apache-2.0 |
| [Ollama](https://ollama.com) | modelo de linguagem local para a IA no texto do laudo (0.99.54), se instalado à parte | MIT |
| [API compatível com OpenAI (LM Studio, vLLM, llama.cpp)](https://platform.openai.com/docs/api-reference) | servidor de modelo de linguagem para a IA no texto do laudo, se o serviço tiver um | conforme o servidor |
| [API da Anthropic (Claude)](https://docs.claude.com) | modelo de linguagem para a IA no texto do laudo, com chave própria do serviço | serviço da Anthropic |
| [7-Zip](https://www.7-zip.org) | abrir RAR, 7z, ISO e ZIP em Deflate64 na importação (0.99.66), se instalado no computador | LGPL-2.1 (código do unRAR com restrição própria) |
| [libarchive (bsdtar, o tar.exe do Windows 10/11)](https://www.libarchive.org) | abrir RAR, 7z e ISO na importação (0.99.66) quando não há 7-Zip | BSD-2-Clause |
| [UnRAR (WinRAR)](https://www.rarlab.com) | abrir RAR na importação (0.99.66), se o WinRAR estiver instalado | licença freeware do UnRAR |

## Ambiente da segmentação, baixado à parte

| Ferramenta | Para que serve | Licença |
|---|---|---|
| [TotalSegmentator](https://github.com/wasserth/TotalSegmentator) | segmentação de órgãos abdominais, vértebras e discos (TC e RM) e das estruturas da cefalometria — palato, faringe, hioide, mandíbula e língua (TC; tarefas abertas head_glands_cavities, headneck_bones_vessels, craniofacial_structures, head_muscles e headneck_muscles), dos marcos dos níveis linfonodais cervicais e dos nódulos pulmonares (tarefa aberta lung_nodules, modelo da BLUEMIND AI treinado em parte com o LIDC-IDRI) e da composição corporal (vértebras, órgãos e a cavidade abdominal da tarefa aberta trunk_cavities) e do fígado, do baço e dos segmentos de Couinaud na RM (total_mr e liver_segments_mr) | Apache-2.0 (algumas tarefas pedem licença, gratuita para uso não comercial) |
| [nnU-Net](https://github.com/MIC-DKFZ/nnUNet) | a rede por trás do TotalSegmentator e do autoPET | Apache-2.0 |
| [PyTorch](https://pytorch.org) | a biblioteca de redes neurais da segmentação | BSD-3-Clause |
| [MONAI](https://monai.io) | o SegResNet do glioma (BraTS) — parte captante, necrose e edema (modelo extra) | Apache-2.0 |
| [DIPY](https://dipy.org) | a versão em PyTorch do SynthSeg, no ambiente da segmentação | BSD-3-Clause |
| [NiBabel](https://nipy.org/nibabel) | troca de volumes (NIfTI) com o ambiente da segmentação | MIT |

## Modelo de IA, baixado à parte

| Ferramenta | Para que serve | Licença |
|---|---|---|
| [PaddleOCR (modelos)](https://github.com/PaddlePaddle/PaddleOCR) | os modelos de leitura de texto que o RapidOCR usa | Apache-2.0 |
| [MedSAM2](https://github.com/bowang-lab/MedSAM2) | segmentar qualquer lesão por uma caixa, propagada aos cortes vizinhos (modelo extra) | Apache-2.0 (código); CC BY-SA 4.0 (pesos) |
| [autoPET II (nnU-Net)](https://zenodo.org/records/8362371) | lesões ávidas no PET-FDG, para o MTV e a TLG (modelo extra) | conferir no registro do Zenodo 8362371 (nnU-Net: Apache-2.0) |
| [SynthSeg](https://github.com/BBillot/SynthSeg) | segmentação do encéfalo em RM de qualquer contraste e resolução e em TC — índices do crânio (Evans, 3º ventrículo, ângulo calosal) e volumes dos hipocampos | Apache-2.0 |
| [Classificador de densidade da NYU](https://github.com/nyukat/breast_density_classifier) | categoria de densidade mamária (BI-RADS a–d) | BSD-2-Clause |

## Só para gerar o instalador

| Ferramenta | Para que serve | Licença |
|---|---|---|
| [PyInstaller](https://pyinstaller.org) | empacota o programa para Windows | GPL-2.0 com exceção do bootloader |
| [Inno Setup](https://jrsoftware.org/isinfo.php) | o instalador do Windows | Inno Setup License (gratuita) |

## Desenvolvimento

| Ferramenta | Para que serve | Licença |
|---|---|---|
| [ReportLab](https://www.reportlab.com/opensource/) | o guia do usuário em PDF | BSD |
| [Vite, TypeScript e Terser](https://vite.dev) | constroem o visualizador web (src/ipe/web_dist) | MIT, Apache-2.0 e BSD-2-Clause |
| [pytest](https://pytest.org) | os testes automáticos | MIT |
| [Claude (Anthropic)](https://www.anthropic.com/claude) | escreve o código a partir dos pedidos do autor, testa e documenta | serviço da Anthropic |

## Como citar

Os autores destas ferramentas pedem que trabalhos que as usam citem:

- **TotalSegmentator:** Wasserthal J, et al. TotalSegmentator: robust segmentation of 104 anatomic structures in CT images. Radiology: Artificial Intelligence. 2023;5(5):e230024.
- **nnU-Net:** Isensee F, et al. nnU-Net: a self-configuring method for deep learning-based biomedical image segmentation. Nature Methods. 2021;18:203–211.
- **MedSAM2:** Ma J, et al. MedSAM2: Segment Anything in 3D Medical Images and Videos. arXiv 2504.03600; 2025.
- **autoPET II (nnU-Net):** Isensee F, et al. Look Ma, no code: fine tuning nnU-Net for the AutoPET II challenge by only adjusting its JSON plans. arXiv 2309.13747; 2023.
- **MONAI:** Myronenko A. 3D MRI brain tumor segmentation using autoencoder regularization. BrainLes (MICCAI) 2018.
- **SynthSeg:** Billot B, et al. SynthSeg: Segmentation of brain MRI scans of any contrast and resolution without retraining. Medical Image Analysis. 2023;86:102789.
- **DIPY:** Garyfallidis E, et al. Dipy, a library for the analysis of diffusion MRI data. Frontiers in Neuroinformatics. 2014;8:8.
- **Classificador de densidade da NYU:** Wu N, et al. Breast density classification with deep convolutional neural networks. ICASSP 2018.

## Inspiração

Programas que inspiraram o Ipê. Nenhum código deles está aqui; os nomes são marcas dos donos.

- [OsiriX](https://www.osirix-viewer.com)
- [Horos](https://horosproject.org)
- [Weasis](https://weasis.org)
- [GE AW Server (manuais)](https://www.gehealthcare.com)
