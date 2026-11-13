# Ipê

**Visualizador DICOM para pesquisa e ensino**, em Python (PySide6), para Windows, Linux e macOS
(experimental). Nasceu numa
estação de laudo de imagem da mama e cresceu para cobrir TC, RM, PET/CT, medicina nuclear,
ultrassom e radiografia, com rede DICOM, filmes, impressão e laudo.

> **Não destinado a uso diagnóstico.** O Ipê não é dispositivo médico registrado na ANVISA nem em
> outra agência. Não use as imagens, medidas ou resultados dele para laudar, decidir conduta ou
> tratar pacientes.

*Outros idiomas: [English](README.md) · [Español](README.es.md) · Histórico de versões:
[CHANGELOG.md](CHANGELOG.md)*

O programa abre em **inglês** por padrão. O instalador pergunta o idioma (inglês, português ou
espanhol), e dá para mudar depois em Configurações ▸ Sistema ▸ Idioma.

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
  segundo plano, sem duplicar. Copiar para o armazenamento ou só referenciar. Também RAR, 7z e
  outros compactados.
- Vários locais de exames (HD externo, pasta de rede), comentários, listas de casos e listas
  inteligentes, exame protegido, ocultar e apagar séries.
- Marca nos exames que já têm resultado de IA (✦) ou uma IA rodando (⚙).
- Anonimizar cópias de exames; corrigir tags gravando cópia (o original nunca é alterado).
- Compressão sem perda, com conferência pixel a pixel, e relatório do acervo.
- PDFs e imagens anexados ao exame; estado do exame; estado da análise salvo (reabre onde parou).
- Lista de trabalho com prioridade, subespecialidade e prazo; painel de produtividade; busca ativa
  de pacientes e filtros de mamografia.

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
- Mosaico dentro do quadro, zoom digitado, imagens-chave e anotações gravadas em DICOM.
- Barra que se arruma pelo exame: as aplicações (dinâmica, 3D, MN…) aparecem só quando servem ao
  exame aberto; o botão Aplicações lista todas, e cada uma pode ficar sempre, nunca ou automática.
- Menu Configurações com um submenu por assunto e uma janela por item.

### Reconstruções e 3D
- MPR ortogonal, oblíquo e curvo; MIP/MinIP/média em espessura (slab); salvar reconstrução como série.
- Volume rendering, superfície, recorte e escultura; fusão PET/CT.
- Exportar malha 3D em STL, OBJ, PLY, GLB e 3MF.
- Cardíaco 4D e subtração digital (DSA).
- Registro rígido entre exames (com conferência visual) e correção de movimento na dinâmica.
- Estruturas em 3D: editar máscaras e gravar como SEG ou RTSTRUCT.

### Medidas
- Régua, polilinha, ângulo, Cobb, ROIs (elipse, retângulo, mão livre) com média e desvio, texto,
  seta, curva; calibração manual por imagem ou série.
- Ultrassom calibrado pela região do arquivo, imagem a imagem.
- Estatística estendida da ROI, ROI clonada e espelhada, tempo de duplicação; medidas em rascunho.
- Painel com todas as medidas do exame; exportar para planilha e gravar como DICOM SR.
- Segmentação 3D por crescimento de região, com volume e três eixos perpendiculares.
- Medidas guiadas (Índices): MRPI e MRPI 2.0, índice de Evans e ângulo calosal, com conferência
  do plano e da espessura do corte.
- Índices do crânio automáticos (SynthSeg): Evans, 3º ventrículo, ângulo calosal e volumes dos
  hipocampos, em RM de qualquer sequência ou TC.
- Níveis linfonodais cervicais na TC (mapa I a VII em qualquer plano; a lesão segmentada ganha o nível).
- Cefalometria do cavum na TC, automática (TotalSegmentator) ou à mão: área mínima da via aérea
  perpendicular ao eixo, palato mole, espaço aéreo posterior, hioide e língua, no formato do laudo.
- Corpo: composição em L3 (com peso e altura) e atenuação hepática; gordura e ferro hepáticos na RM
  (1,5 T e 3 T); biometria e resultado de esteatose; difusão (ADC) em qualquer RM.
- Tórax e vasos: enfisema por lobo, fraturas vertebrais (Genant), escore de cálcio coronariano
  (Agatston, CAC-DRS) e diâmetros da aorta por segmento, medidos perpendiculares à linha central.

### Mama
- Mamografia e tomossíntese: protocolo por etapas, distribuição entre monitores, enquadramento da
  mama, quadrantes, incidência certa pelo rótulo do aparelho, 2D sintetizada, implante, indicador
  de profundidade da tomossíntese.
- Densidade mamária por três métodos, com a máscara à vista.
- RM dinâmica: mapas MSI, PEI, SER e mapa cinético de 6 cores (estilo CADstream), em qualquer
  plano; layouts configuráveis; medida da lesão com angiovolume e padrões cinéticos; distância da
  lesão à pele, ao mamilo e ao peitoral.
- Fusão arrastando uma série sobre a outra, mapas de cores e achados registrados por marcadores.

### Medicina nuclear
- Leitura NM multi-frame (detectores, fases, janelas de energia), ANT/POST e média geométrica com
  janela comum.
- ROIs e curvas atividade-tempo, renograma, esvaziamento gástrico, DISIDA, salivares, DMSA,
  paratireoide, captação de tireoide e trânsito, com correção de decaimento. O programa devolve
  números; não interpreta.
- PET: SUV por peso, massa magra e corrigido pela glicemia; layout de leitura de PET; carga tumoral
  (FDG, PSMA, DOTA: MTV, TLG, número de lesões) e seguimento entre datas.

### Oncologia e IA
- Lesões acompanhadas entre exames; objetos de CAD/IA (SEG, GSPS, SR, RTSTRUCT) que ligam e desligam.
- Segmentação de órgãos abdominais com TotalSegmentator (opcional, instalado à parte) e
  identificação de vértebras e discos.
- Janela Tarefas de IA: o andamento de cada IA (inclusive as que rodam sozinhas quando o exame
  chega), com cancelar.
- Achados de IA revisáveis (confirmar, corrigir ou descartar) que podem ir para o texto do laudo; nódulo
  pulmonar completo; lesões hepáticas por segmento de Couinaud.
- Modelos extras opcionais: SynthSeg, MedSAM2 (segmentação interativa), autoPET e BraTS.

### Rede DICOM
- Nó DICOM (C-ECHO, C-FIND, C-MOVE, C-GET, C-STORE) e cliente DICOMweb (QIDO, WADO, STOW).
- Busca no PACS, download por série, abrir enquanto baixa, pré-busca de anteriores.
- Automação: roteamento, buscas agendadas, regras por modalidade; Gestão DICOM (conferir se os
  exames das modalidades chegaram ao PACS e enviar o que falta).
- Chamada externa por link `ipe://`, linha de comando ou API HTTP local, inclusive abrindo só o
  visualizador.

### Visualizador web (servidor central)
O servidor central também serve um visualizador no navegador, sem instalar nada no computador de
leitura: abra `http(s)://<servidor>:8043/web` (o endereço aparece na janela do servidor) e entre com o
usuário do Ipê. Por enquanto, para a rede interna.
- Tela no estilo do Weasis: uma barra de ícones em que cada botão do mouse ganha a sua função, como no
  Ipê (clique no ícone com o botão que deve fazê-la; uma marca embaixo do ícone mostra qual), menu do
  botão direito na imagem (clicar e soltar; clicar e segurar faz a função do botão), painéis recolhíveis
  com as séries e os exames anteriores à esquerda e as abas Imagem, Medidas, DICOM e PET à direita.
- Lista de exames, tira de séries (clique ou arraste a série até o quadro), quadros de 1×1 a 4×4,
  janelas prontas, cine.
- MPR, oblíquo, espessura e MIP, com troca de plano em um clique, como no Ipê.
- Medidas com o número do Ipê (régua, ângulo, Cobb, ROIs, pixel, seta, calibração), gravadas no banco
  do servidor: o que se mede no navegador aparece no Ipê e vice-versa. Ultrassom calibrado pela
  região do aparelho.
- PET/CT: fusão, PET e MIP do PET com os axiais andando juntos, SUV pela conta do Ipê, tabelas de
  cores do Ipê, SUV máximo perto do cursor e as SEG do exame (carga tumoral, órgãos) como máscaras.
- Carga rápida: as imagens vão pela rede em HTJ2K sem perda (cópia de envio conferida; o acervo não
  muda), chegam de forma progressiva e ficam no cache do navegador; cada miniatura mostra a
  porcentagem já disponível, e o botão **Carga** mostra a velocidade da rede e o tempo de
  decodificação.
- **Mamografia** no protocolo do Ipê em uma ou **duas telas** (segunda janela sincronizada), **dinâmica da mama** (mapa cinético, SER e outros mapas calculados no navegador, curvas tempo-intensidade, mapas salvos como fusão) e o **laudo** no navegador (modelos, achados de IA revisados, trava de quem está laudando, assinar e retificar) — 0.99.98.

### Filmes, impressão e laudo
- Compositor de filmes; impressão em impressora comum, PDF e impressora DICOM.
- O programa como impressora DICOM: recebe filmes das modalidades, identifica o paciente e
  encaminha por regras.
- Laudo com modelos (TC, MG, RM, PET) e BI-RADS, em PDF, DICOM PDF e SR.
- Exportação em DICOM, JPG/PNG e um visualizador completo em HTML, com anonimização.

### Usuários e idiomas
- Um usuário ou vários, com perfis e permissões; servidor central opcional.
- Perfis por grupo e por computador, configurações exportadas e importadas, atualização pelo
  servidor ou direto do GitHub em um clique.
- HTTPS na rede interna com certificado próprio do Ipê; OAuth2/OIDC nos nós DICOMweb; senhas
  guardadas cifradas.
- Português, inglês e espanhol, com editor de traduções para outros idiomas.

---

## Instalação

### Windows — instalador
O instalador `Ipe-<versão>-installer.exe` (e o pacote portátil `.zip`) instala no perfil do
usuário, sem pedir administrador. A primeira tela pergunta o idioma, com o inglês marcado; depois, a pasta do programa e a do banco. Para gerá-lo a partir do código, veja
[installer/LEIAME.md](installer/LEIAME.md).

### Windows — a partir do código
1. Instale o **Python 3.12** em <https://www.python.org/downloads/>, marcando **"Add python.exe to
   PATH"**.
2. Dê dois cliques em `instalar.bat` (só na primeira vez; pergunta o idioma e baixa cerca de 300 MB de bibliotecas).
3. Dê dois cliques em `executar.bat`.

### Linux
Pelos [releases](https://github.com/filipebarra/ipe/releases) (sem Python):
- **Debian/Ubuntu:** `sudo apt install ./Ipe-<versão>-linux-amd64.deb` — o comando é `ipe-viewer`, e o **Ipê**
  aparece no menu de aplicativos.
- **Qualquer distribuição:** extraia `Ipe-<versão>-linux-portable.tar.gz` e rode `Ipe/install.sh` (para o seu
  usuário, sem administrador; `--system` para todos, `--uninstall` para remover).

Pelo código:
```bash
./instalar.sh
./executar.sh
```

### macOS (experimental)
Pelos [releases](https://github.com/filipebarra/ipe/releases) (sem Python), desde a 0.100.28:
- `Ipe-<versão>-macos-arm64.dmg` para Mac com chip Apple (M1 em diante); `Ipe-<versão>-macos-x86_64.dmg` para Mac
  com processador Intel.
- Abra o `.dmg` e arraste o **Ipe** para Aplicativos. O programa **não tem assinatura da Apple**: na primeira vez,
  botão direito (ou Control+clique) ▸ **Abrir** ▸ **Abrir**. Se o macOS disser que o app "está danificado", rode
  `xattr -dr com.apple.quarantine /Applications/Ipe.app` no Terminal, ou vá em Ajustes do Sistema ▸ Privacidade e
  Segurança ▸ **Abrir Mesmo Assim**.

O pacote do macOS é novo e foi muito menos usado que os de Windows e Linux. Desde a 0.100.32 os textos mostram as
teclas do Mac (⌘, ⌥), os links `ipe://` abrem o programa e **Procurar atualizações** instala a versão nova sozinho.
Limites conhecidos: não há ícone na barra de menus (o Dock faz esse papel); a segmentação de órgãos não foi testada
num Mac de verdade. Se o programa fechar sozinho, mande o arquivo `~/Library/Logs/DicomViewer/queda.log`.

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
ipe set-language pt-BR                 idioma do programa: en, pt-BR ou es
ipe register-url                       registra os links ipe:// e dicomviewer://
ipe server                             servidor central sem janela
```

## Onde ficam os dados

`ipe info` mostra os caminhos. No Windows ficam em `%LOCALAPPDATA%\DicomViewer` (o nome antigo do
programa, mantido para quem atualiza): banco `dicomviewer.sqlite`, pasta `Storage\` com os
arquivos DICOM, `Impressoes\`, `settings.json` e logs. A variável de ambiente `IPE_HOME` (ou a
antiga `DICOMVIEWER_HOME`) troca a pasta — útil para manter um banco por projeto de pesquisa. No macOS os
dados ficam em `~/Library/Application Support/DicomViewer` e os logs em `~/Library/Logs/DicomViewer`.

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
