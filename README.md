# Ipê

**Visualizador DICOM para pesquisa e ensino**, em Python (PySide6), para Windows e Linux. Nasceu numa
estação de laudo de imagem da mama e cresceu para cobrir TC, RM, PET/CT, medicina nuclear,
ultrassom e radiografia, com rede DICOM, filmes, impressão e laudo.

> **Não destinado a uso diagnóstico.** O Ipê não é dispositivo médico registrado na ANVISA nem em
> outra agência. Não use as imagens, medidas ou resultados dele para laudar, decidir conduta ou
> tratar pacientes.

*Outros idiomas: [English](README.en.md) · [Español](README.es.md) · Histórico de versões:
[CHANGELOG.md](CHANGELOG.md)*

## Por que Ipê?

Em Brasília, no meio da seca, os ipês florescem e a paisagem muda. E há uma coincidência: *ipê* está
em Fil**ipe**. O Ipê foi criado por um radiologista de mama que, como muitos colegas, migrou para o
macOS por causa do OsiriX e do Horos, e sempre quis um programa completo para Windows e Linux. Ele é
escrito com a ajuda do Claude (Anthropic), que trabalha como programador sênior a partir dos pedidos
do autor, e existe graças a bibliotecas abertas de DICOM, cálculo e IA.
[Leia a história completa](HISTORIA.md) · [Créditos e licenças](CREDITOS.md)

---

## Funções

### Banco de exames
- Banco local (SQLite): paciente → exame → série → imagem, com miniaturas e busca por nome, ID,
  accession ou descrição (vários termos com `|`), modalidade e período.
- Importação de pastas, CD/DVD, ZIP e arquivos soltos, inclusive arrastando para a janela; em
  segundo plano, sem duplicar. Copiar para o armazenamento ou só referenciar.
- Vários locais de exames (HD externo, pasta de rede), comentários, listas de casos e listas
  inteligentes, exame protegido, ocultar e apagar séries.
- Anonimizar cópias de exames; corrigir tags gravando cópia (o original nunca é alterado).
- Compressão sem perda, com conferência pixel a pixel, e relatório do acervo.

### Visualizador
- Vários layouts de quadros, vários monitores tratados como **uma** estação, memória de layout por
  monitor e protocolos de exibição.
- Janela/nível, zoom, pan, cine, inverter, girar, espelhar, lupa, filtros de nitidez e suavização,
  escalas de cores editáveis.
- Sincronização automática (mesmo ponto do paciente) ou manual, por modalidade; cursor 3D e linhas
  de corte.
- Anotações da tela em quatro níveis (completa, parcial 1, parcial 2, ausente), configuráveis.
- Ctrl+C copia o quadro como está na tela, em alta resolução.
- Exames anteriores na tira de miniaturas; clique num quadro vazio para escolher a série.
- Barra que se arruma pelo exame: as aplicações (dinâmica, 3D, MN…) aparecem só quando servem ao
  exame aberto; o botão Aplicações lista todas, e cada uma pode ficar sempre, nunca ou automática.
- Menu Configurações com um submenu por assunto e uma janela por item.

### Reconstruções e 3D
- MPR ortogonal, oblíquo e curvo; MIP/MinIP/média em espessura (slab); salvar reconstrução como série.
- Volume rendering, superfície, recorte e escultura; fusão PET/CT.
- Exportar malha 3D em STL, OBJ, PLY, GLB e 3MF.
- Cardíaco 4D e subtração digital (DSA).

### Medidas
- Régua, polilinha, ângulo, Cobb, ROIs (elipse, retângulo, mão livre) com média e desvio, texto,
  seta, curva; calibração manual por imagem ou série.
- Ultrassom calibrado pela região do arquivo, imagem a imagem.
- Painel com todas as medidas do exame; exportar para planilha e gravar como DICOM SR.
- Segmentação 3D por crescimento de região, com volume e três eixos perpendiculares.
- Medidas guiadas (Índices): MRPI e MRPI 2.0, índice de Evans e ângulo calosal, com conferência
  do plano e da espessura do corte.
- Cefalometria do cavum na TC, automática (TotalSegmentator) ou à mão: área mínima da via aérea
  perpendicular ao eixo, palato mole, espaço aéreo posterior, hioide e língua, no formato do laudo.

### Mama
- Mamografia e tomossíntese: protocolo por etapas, distribuição entre monitores, enquadramento da
  mama, quadrantes, incidência certa pelo rótulo do aparelho, 2D sintetizada, implante, indicador
  de profundidade da tomossíntese.
- Densidade mamária por três métodos, com a máscara à vista.
- RM dinâmica: mapas MSI, PEI, SER e mapa cinético de 6 cores (estilo CADstream), em qualquer
  plano; layouts configuráveis; medida da lesão com angiovolume e padrões cinéticos; distância da
  lesão à pele, ao mamilo e ao peitoral.

### Medicina nuclear
- Leitura NM multi-frame (detectores, fases, janelas de energia), ANT/POST e média geométrica com
  janela comum.
- ROIs e curvas atividade-tempo, renograma, esvaziamento gástrico, DISIDA, salivares, DMSA,
  paratireoide, captação de tireoide e trânsito, com correção de decaimento. O programa devolve
  números; não interpreta.

### Oncologia e IA
- Lesões acompanhadas entre exames; objetos de CAD/IA (SEG, GSPS, SR, RTSTRUCT) que ligam e desligam.
- Segmentação de órgãos abdominais com TotalSegmentator (opcional, instalado à parte) e
  identificação de vértebras e discos.

### Rede DICOM
- Nó DICOM (C-ECHO, C-FIND, C-MOVE, C-GET, C-STORE) e cliente DICOMweb (QIDO, WADO, STOW).
- Busca no PACS, download por série, abrir enquanto baixa, pré-busca de anteriores.
- Automação: roteamento, buscas agendadas, regras por modalidade; Gestão DICOM (conferir se os
  exames das modalidades chegaram ao PACS e enviar o que falta).
- Chamada externa por link `ipe://`, linha de comando ou API HTTP local, inclusive abrindo só o
  visualizador.

### Filmes, impressão e laudo
- Compositor de filmes; impressão em impressora comum, PDF e impressora DICOM.
- O programa como impressora DICOM: recebe filmes das modalidades, identifica o paciente e
  encaminha por regras.
- Laudo com modelos (TC, MG, RM, PET) e BI-RADS, em PDF, DICOM PDF e SR.
- Exportação em DICOM, JPG/PNG e um visualizador completo em HTML, com anonimização.

### Usuários e idiomas
- Um usuário ou vários, com perfis e permissões; servidor central opcional.
- Português, inglês e espanhol, com editor de traduções para outros idiomas.

---

## Instalação

### Windows — instalador
O instalador `Ipe-<versão>-instalador.exe` (e o pacote portátil `.zip`) instala no perfil do
usuário, sem pedir administrador. Para gerá-lo a partir do código, veja
[installer/LEIAME.md](installer/LEIAME.md).

### Windows — a partir do código
1. Instale o **Python 3.12** em <https://www.python.org/downloads/>, marcando **"Add python.exe to
   PATH"**.
2. Dê dois cliques em `instalar.bat` (só na primeira vez; baixa cerca de 300 MB de bibliotecas).
3. Dê dois cliques em `executar.bat`.

### Linux
```bash
./instalar.sh
./executar.sh
```

Para testar sem exames reais: **Ajuda ▸ Gerar exames de teste (fantomas)**.

A segmentação de órgãos (TotalSegmentator) é opcional e se instala à parte, com
`instalar_segmentacao.bat` / `instalar_segmentacao.sh`.

---

## Linha de comando

No Windows, use `.venv\Scripts\ipe.exe` (ou `ipe-cli.exe`, no programa instalado). No Linux,
`.venv/bin/ipe`.

```
ipe                                    abre a interface
ipe open --accession 123456            abre o exame pelo accession
ipe open --study-uid 1.2.3...          abre pelo StudyInstanceUID
ipe open --patient-id ABC              abre o exame mais recente do paciente
ipe open --accession 123 --node PACS   se não estiver no banco, busca no nó, baixa e abre
ipe open --accession 123 --janela viewer   abre só o visualizador
ipe open C:\pasta\exame                importa a pasta e abre os exames
ipe "ipe://open?accession=123"         o mesmo, pelo link
ipe import D:\ --reference             importa sem copiar (só referencia)
ipe retrieve --accession 123           só baixa do PACS
ipe sample C:\temp\fantomas            gera exames sintéticos de teste
ipe info                               mostra onde ficam banco, arquivos e configurações
ipe register-url                       registra os links ipe:// e dicomviewer://
ipe server                             servidor central sem janela
```

## Onde ficam os dados

`ipe info` mostra os caminhos. No Windows ficam em `%LOCALAPPDATA%\DicomViewer` (o nome antigo do
programa, mantido para quem atualiza): banco `dicomviewer.sqlite`, pasta `Storage\` com os
arquivos DICOM, `Impressoes\`, `settings.json` e logs. A variável de ambiente `IPE_HOME` (ou a
antiga `DICOMVIEWER_HOME`) troca a pasta — útil para manter um banco por projeto de pesquisa.

## Para quem vem do DicomViewer

Até a versão 0.99.10 o programa se chamava **DicomViewer**. Continuam valendo: a pasta de dados, o
AE de fábrica `DICOMVIEWER`, os links `dicomviewer://`, `python -m dicomviewer` e os atalhos antigos.
O instalador novo atualiza o antigo no lugar.

## Desenvolvimento

- Código em `src/ipe/` (`core`, `db`, `importer`, `imaging`, `network`, `printing`, `reporting`,
  `ui`, `ai`, `automation`, `central`, `exporter`, `caselists`); testes em `tests/`; ferramentas de
  tradução e do guia em `tools/`.
- Testes: `python -m pytest` (ou `testar.bat`). Os testes geram exames sintéticos.
- **Nunca envie exames reais, capturas de tela com dados de paciente nem bancos para o
  repositório.**
- Guia do usuário em PDF: `docs/Ipe-guia-do-usuario.pdf` (F1 no programa).

## Licença

[GPL-3.0-or-later](LICENSE). Pode usar, estudar, modificar e redistribuir; quem redistribuir uma
versão modificada tem de publicar o código dela sob a mesma licença. © Filipe Ramos Barra.

As bibliotecas e os modelos que o Ipê usa, com as licenças e os links, estão em
[CREDITOS.md](CREDITOS.md) (e no programa, em Ajuda ▸ Sobre o Ipê ▸ Créditos e licenças).
