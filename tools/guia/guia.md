> **Não destinado a uso diagnóstico.** Este programa é um projeto próprio, sem registro sanitário e sem certificação como dispositivo médico. Os números que ele devolve são medidas; a interpretação é sempre do médico.

<!--
Texto-fonte do guia do usuário. Para gerar o PDF:  python tools/guia/gerar_guia.py
A sintaxe aceita está no começo de tools/guia/gerar_guia.py. {versao} vira a versão do código.
Ao mudar uma tela, mude aqui também e gere de novo.
-->

# Primeiros passos

O Ipê é um visualizador DICOM para Windows e Linux, feito para estação de laudo: ele guarda os exames num banco local, recebe e busca exames na rede DICOM, confere se os exames das modalidades chegaram ao PACS, mostra as imagens em vários monitores e sai pelo laudo, pelo filme ou pela exportação.

Este guia descreve a versão {versao}. Onde o programa tem uma limitação, ela está escrita — é mais útil saber o que a ferramenta não faz do que descobrir na frente do exame.

## As duas telas

O programa tem uma aba fixa, **Banco de dados**, e uma aba por exame aberto. Tudo começa no banco: é a lista de exames, a busca, as listas de casos e os botões que abrem as outras janelas (PACS, Gestão, impressões, laudo, configurações).

- **Abrir um exame**: duplo clique na linha, ou botão **Abrir**.
- **Voltar ao banco**: **Ctrl+B**, ou a aba Banco de dados.
- **Fechar um exame**: o ✕ da aba. Com o exame repartido entre monitores, fechar um fecha todos — meio exame aberto num monitor é pior que nenhum.
- **Trocar de aba não rouba o teclado**: ao clicar na aba de um exame, o teclado vai para o quadro. As setas andam nas etapas da mamografia, não nas abas.

## Importar exames

Menu **Arquivo**: **Importar pasta…** (Ctrl+I), **Importar arquivos…** e **Importar ZIP…**. Também dá para arrastar arquivos ou pastas para cima da janela.

> **Copiar ou referenciar?** Em Configurações ▸ Banco de dados ▸ Importação, a caixa *Copiar os arquivos para o armazenamento do programa* decide se o DICOM é copiado para a pasta do programa ou apenas referenciado onde está. Desmarcada, o programa nunca escreve no arquivo original — e nunca o apaga.

## Onde ficam os dados

Menu **Ajuda ▸ Abrir pasta de dados** mostra onde estão o banco (SQLite), as imagens copiadas (Storage), as configurações (settings.json) e os registros (logs). Pela linha de comando, `ipe-cli info` imprime os mesmos caminhos.

O programa não roda como administrador, e nunca precisa: tudo o que ele escreve fica no perfil do usuário.

## Ajuda

**F1** (fora de um exame), o botão **Ajuda** da tela inicial ou **Ajuda ▸ Guia do usuário (PDF)** abrem este guia no leitor de PDF do computador. **Ajuda ▸ Sobre o Ipê…** mostra a versão. Dentro de um exame o F1 é do filme (capítulo 12).

## O que o programa nunca faz com o original

- Exportar, empacotar, anonimizar e corrigir etiquetas (tags) geram arquivos novos; o original fica intacto.
- A única função que reescreve um arquivo de paciente é a compressão sem perda, e só depois de conferir pixel a pixel que a imagem é idêntica.
- Apagar exame e apagar série removem arquivos, e só os que estão dentro do Storage do programa. Arquivo apenas referenciado não é tocado.
- O que o programa grava *no* exame (captura da lesão, filme no exame, reconstruções salvas) entra como **série nova**; as séries originais não mudam.

# A tela do banco de dados

## Lista de exames

A tabela central lista os exames do local selecionado. Em cima dela: o campo **Buscar**, o botão **Colunas ▾** (escolhe quais colunas aparecem) e **Limpar filtros**. O painel da direita mostra as séries do exame selecionado.

Botão direito num exame (ou em vários selecionados):

- **Enviar para ▸** um nó ▸ *como este programa* ou *como* uma das identidades cadastradas (capítulo 9);
- **Anonimizar uma cópia deste exame…** — exporta anonimizado ou guarda uma cópia anonimizada no banco (capítulo 14);
- laudo, listas de casos, proteção, apagar e o resto das ações do exame.

### Recolher os painéis dos lados

Os dois painéis dos lados da lista — **Locais e listas**, à esquerda, e **Séries e comentários**, à direita — recolhem para uma **tira na borda**, como os painéis do Weasis: botão **◂/▸** no título do painel. Recolhido, sobra a tira com o nome escrito de lado; um clique nela (ou na setinha) traz o painel de volta, do tamanho que estava. A lista de exames fica com a largura toda.

O botão **Listas** da barra abre e recolhe o painel da esquerda, e **Exibir ▸ Mostrar Locais e listas / Mostrar Séries e comentários** faz o mesmo no menu. Cada usuário tem o seu estado, e o programa abre como ficou da última vez.

## Painel de séries

- Alterna entre ícone e lista pelo botão do cabeçalho; a escolha fica guardada.
- Botão direito numa série: **Ocultar** (reversível — a série some da lista e do visualizador, e o botão **Ocultas** traz de volta) ou **Apagar** (remove do banco e os arquivos que estão no Storage). O programa recusa apagar a última série de um exame e qualquer série de exame com cadeado.
- **Enviar N série(s) para ▸** um nó ▸ como… — manda **só as séries selecionadas** (Ctrl+clique ou Shift+clique para escolher várias).
- Ainda no botão direito: marcar as séries selecionadas como dinâmica (vale para TC e RM) e separar uma série que traz todas as fases juntas.
- Capturas e séries que o próprio programa gravou (a captura da lesão, mapas e reconstruções salvos) aparecem com miniatura, como as outras.

## Locais

O painel **Locais**, à esquerda, troca entre bancos diferentes (por exemplo, o banco local e um servidor central da intranet). Ele recolhe, e recolhido continua dizendo em que local você está. Um local por vez.

## Banco de casos

Logo abaixo dos locais fica a árvore do **Banco de casos**: pastas e listas. Três tipos de lista, escolhidos na criação — Normal, Reunião e Inteligente (filtro). O capítulo 7 trata das duas últimas.

Botões: **+ Lista**, **+ Pasta**, **▶ Modo reunião**. Botão direito na árvore abre os mesmos itens mais renomear, descrição, mover, exportar e excluir.

## Comentários e proteção

- **Adicionar comentário** escreve uma nota no exame, que aparece na lista.
- O **cadeado** protege o exame: ele não entra na limpeza automática e não pode ser apagado enquanto estiver protegido.
- **Histórico do exame…** (botão direito no exame) mostra quem fez o quê **neste** exame — abriu, baixou, exportou, enviou, imprimiu, mudou de banco, apagou imagem, assumiu o laudo — e quando os laudos foram criados e assinados.

## Botões da tela inicial

| Botão | O que abre |
|---|---|
| Importar | importar pasta, arquivos ou ZIP |
| PACS | busca e download (Ctrl+Shift+F) — capítulo 9 |
| Gestão | conferir se os exames das modalidades estão no PACS — capítulo 10 |
| Abrir / Enviar / Exportar | ações sobre os exames selecionados |
| Imprimir | o compositor de filme (Ctrl+P) — capítulo 12 |
| Impressões | o que as modalidades mandaram imprimir e o que foi montado aqui |
| Laudo | o laudo do exame selecionado — capítulo 11 |
| Listas / Reunião | o banco de casos e o modo reunião |
| Ocultar | esconde os dados do paciente em todo o programa |
| Apagar | apaga os exames selecionados |
| Monitor | as configurações de monitor (não abre exame) |
| Configurações / Usuários / Ajuda | preferências, perfis e este guia |

# O visualizador

Cada exame abre numa aba com a barra de ferramentas em cima, a tira de miniaturas das séries à esquerda e os quadros no centro. No fim da barra fica o bloco das **aplicações do exame** (MPR, 3D, Dinâmica, Fusão, MN): cada uma aparece só quando serve ao exame aberto — pela modalidade, pela região do corpo (do BodyPartExamined e das descrições) e pelo tipo de série (angio, T1 3D, T2 3D, dinâmica, volume). Numa mamografia não há MPR, 3D, Fusão nem MN; numa RM de mama aparece a Dinâmica. O botão **Aplicações** lista todas, inclusive as que ficaram de fora, com o motivo — e elas rodam mesmo assim. Botão direito numa aplicação: **Automático**, **Sempre** ou **Nunca**, em todos os exames ou só nos exames daquela região. A ordem, os modos e o dicionário de regiões ficam em Configurações ▸ Visualizador ▸ *Barra de ferramentas e aplicações* e Configurações ▸ Protocolos de exame ▸ *Regiões do corpo* (com uma caixa para testar descrições).

## Mouse

A ferramenta do botão esquerdo é a que estiver acesa na barra. Os outros botões, a roda e os cliques se configuram em Configurações ▸ Visualizador ▸ Mouse. De fábrica:

| Gesto | O que faz |
|---|---|
| Esquerdo arrastando | a ferramenta escolhida na barra (de fábrica, janela/nível) |
| Direito arrastando | zoom |
| Direito clicando | menu do quadro |
| Meio arrastando | mover a imagem (pan) |
| Meio clicando | ajustar à janela |
| Roda | passar os cortes |
| Shift segurado | o esquerdo vira cursor 3D (sem precisar clicar: mover o mouse já acha o ponto nos outros quadros) |
| Ctrl segurado | o esquerdo vira rolar (sobe e desce os cortes) |

Shift e Ctrl emprestam o botão esquerdo: a ferramenta escolhida na barra não muda, e ao soltar tudo volta ao que era. Qual tecla faz o quê se escolhe em Configurações ▸ Visualizador ▸ Atalhos de teclado (Shift / Ctrl / Alt / Nenhuma).

## As ferramentas

A ferramenta do botão esquerdo se escolhe na barra, no menu do botão direito do quadro — em **Mouse (botão esquerdo)**, o que move a imagem, e em **Medidas**, o que mede — ou clicando no canto que mostra a ferramenta atual.

A coluna *tecla* abaixo é sugestão: quase toda a lista de atalhos vem de fábrica vazia, e cada tecla é escolhida em Configurações ▸ Visualizador ▸ Atalhos de teclado (capítulo 14). Das ferramentas, só o zoom por quadrante tem tecla de fábrica (Q).

| Ferramenta | Tecla | Para que serve |
|---|---|---|
| Janela / nível | W | brilho e contraste |
| Zoom | Z | aproximar e afastar |
| Pan | P | mover a imagem no quadro |
| Rolar | S | passar os cortes |
| Régua | M | distância em mm |
| Ângulo / Cobb | A / Shift+C | ângulo entre duas linhas |
| ROI elíptica / retangular / poligonal | E / Shift+E / G | média, desvio, área |
| Intensidade | V | valor do pixel (HU, SUV, sinal) e curva da dinâmica |
| Seta / Texto / Lápis | Shift+A / T / B | marcar e anotar |
| Cursor 3D | X | o mesmo ponto nos outros quadros |
| Segmentar 3D | Shift+V | cresce a lesão e mede volume, eixos, SUV, TLG |
| Selecionar | — | não cria nada: escolhe, move e edita o que já está desenhado |
| Lupa | U | aumento local, segurando o botão |
| Zoom por quadrante | Q (de fábrica) | percorre os quatro quadrantes em tamanho real |

## Quadros, séries e layout

- Layout na barra, ou menu **Exibir ▸ Layout dos quadros** (de 1×1 a 4×4). O layout inicial fica em Configurações ▸ Sistema ▸ Ao abrir o programa.
- `[` e `]` (sugestão) trocam a série do quadro ativo. Trocar de sequência mantém a posição: o corte novo passa pelo ponto que estava à vista.
- Arrastar uma miniatura da tira para um quadro põe aquela série ali.
- O canto inferior direito do quadro diz o plano (clicável), a fase da dinâmica, a janela e o FOV.

## Selos de integridade

Uma faixa no alto do quadro avisa o que pode tornar a imagem imprópria para ler. Clicar nela explica cada selo.

| Selo | Cor | Quando |
|---|---|---|
| COMPRESSÃO COM PERDAS — imprópria para o laudo | vermelho | mamografia comprimida com perdas (pelo atributo Lossy Image Compression ou pela sintaxe do arquivo), com o método e a taxa. O ACR e a FDA não aceitam para a leitura final |
| Compressão com perdas | âmbar | qualquer outra modalidade comprimida com perdas |
| Modality LUT em tabela | vermelho | o arquivo converte os pixels por tabela; o Ipê aplica só slope/intercept, então HU e densidades podem não ser os reais |
| PACIENTES DIFERENTES NO LAYOUT | vermelho | os quadros da tela têm exames de pacientes diferentes (nome ou ID não batem) |
| Pixel não quadrado | âmbar | espaçamentos diferentes na linha e na coluna |
| Imagem derivada | âmbar | ImageType DERIVED\SECONDARY (reconstrução, captura, mapa) |

A reconstrução (MPR, MIP) herda o selo de compressão da série de origem.

**Na cópia.** Em Configurações ▸ Visualizador ▸ Anotações, *Na cópia (Ctrl+C)* escolhe o nível de anotação da imagem copiada, separado do da tela — por exemplo, Parcial 1 (sem os dados do paciente) para aula, sem precisar anonimizar o arquivo. O *carimbo mínimo* põe no pé da cópia a série, a janela, a escala, o processamento aplicado (MIP 10 mm, subtração, DSA, filtro, fusão) e os selos graves, mesmo com as anotações escondidas. O item *Selos de integridade* fica em Configurações ▸ Visualizador ▸ Anotações; os selos vermelhos aparecem em qualquer nível, menos no Ausente.

## Janela: do arquivo, digitada e presets por modalidade

O menu da janela (seta do botão Janela, ou duplo clique no "W … L …" do canto) traz:

- **Do arquivo (Switch WL)**: todas as janelas gravadas no DICOM, com o nome (a mamografia costuma trazer NORMAL, HARDER, SOFTER) e as VOI LUT. A ação *Switch WL* (sem tecla de fábrica; escolha a sua em Atalhos de teclado) percorre essas janelas em ciclo; na mamografia troca as incidências à vista juntas. O nome da janela aparece ao lado do W/L até você arrastar a janela.
- **Digitar a janela…**: largura e nível, por exemplo `400 40` ou `1500/-600`.
- **Guardar a janela atual como preset…**: grava a janela à vista na lista da modalidade do quadro. RM, mamografia, PET e as outras podem ter lista própria; sem ela vale a lista geral (a de TC). As teclas 1–9 aplicam o preset da modalidade do quadro ativo. As listas também se editam em Configurações ▸ Visualizador ▸ Presets de janela, escolhendo a lista no alto. Os protocolos de exibição continuam usando a lista geral.

## Enviar ao filme: F1 e F2

Com o foco num quadro do exame:

| Tecla | O que faz |
|---|---|
| F1 | manda a imagem do quadro ao filme, com a janela, o zoom e o giro que ela tem na tela |
| F2 | manda a série do quadro — inteira ou um intervalo, escolhido numa janela |

As duas vêm de fábrica e podem ser trocadas em Configurações ▸ Visualizador ▸ Atalhos de teclado. Fora do exame (na lista do banco, por exemplo), o F1 volta a abrir este guia. O botão **Filme** da barra faz o mesmo que o F1, e o menu dele traz *todos os quadros* e *imagens-chave do exame*.

## Sincronizar quadros

Botão **Sincronizar**. A seta ao lado abre as opções: Automática no mesmo estudo, Janela/nível, Zoom e pan, Linhas de referência e Tira de séries. Todas ficam guardadas entre as sessões.

**Alinhar automaticamente com o outro exame** faz um registro por translação entre dois exames do mesmo paciente — útil para comparar com o anterior.

## Medidas

O botão **Medidas** abre uma janela com tudo o que foi medido no exame: série, imagem, tipo, valor, lesão e texto. Clicar numa linha leva até a imagem com a medida já selecionada. A lista sai do banco, não dos quadros abertos — medida feita semana passada está lá.

- A ferramenta **Selecionar** edita o que já existe: clique escolhe, arrastar move, arrastar a ponta redimensiona, Delete apaga.
- **Editar lesão…** (ou duplo clique numa linha de segmentação) reabre a segmentação com o limiar e o mamilo que você usou (capítulo 6).
- As medidas saem para planilha (CSV/Excel) e para DICOM SR.
- **Perfil de intensidade**: botão direito numa régua ou polilinha ▸ *Perfil de intensidade…* mostra o gráfico do valor (HU na TC) ao longo da linha, em mm, com mínimo, máximo e média — a transição de densidade, a parede de uma lesão, o realce de um vaso. O gráfico acompanha a linha quando ela é mexida, e *Copiar valores* leva a tabela para a planilha.
- **Apagar esta imagem…** (botão direito no quadro) tira só aquela imagem do exame — a duplicada, a captura errada. Pede a permissão de apagar, é recusado em exame com cadeado e na última imagem da série, leva junto as medidas e a imagem-chave dela e fica no registro de acesso.

### Régua 3D, incerteza e ROI de referência

- **Régua 3D** (menu Medidas): clique o ponto A num corte e o ponto B em outro corte — ou em outro quadro, como o axial e o sagital. A distância sai em 3D, com as componentes direita-esquerda, ântero-posterior e craniocaudal; nos dois pontos do mesmo corte, o rótulo diz "(2D)". O terceiro clique começa uma régua nova.
- **Cortes grossos**: a régua desenhada numa reconstrução de cortes grossos (o sagital de um axial de 5 mm) avisa quando a direção dela tem pixel de 5 mm — a medida craniocaudal herda esse erro, a ântero-posterior não. Na imagem original, a régua menor que a espessura do corte também avisa.
- **Incerteza** (Configurações ▸ Visualizador ▸ Texto e marcas sobre a imagem): mostra ± o pixel na direção da régua e ± perímetro × pixel ÷ 2 na área da ROI. Desligada de fábrica; os avisos acima aparecem sempre.
- **ROI de referência**: botão direito numa ROI ▸ *Usar como ROI de referência*. As outras ROIs da série passam a mostrar a média delas em % da referência (lesão/fígado, lesão/aorta, lesão/músculo). Só uma por série; ela fica marcada "Referência (100%)" e acompanha se você a mexer.

## Escala das medidas e calibração

Para medir em milímetro o programa precisa saber o tamanho do pixel. Na TC, na RM e na mamografia isso vem do arquivo (PixelSpacing). No ultrassom não: a escala muda a cada imagem, porque a profundidade e o zoom mudam durante o exame, e o aparelho grava uma região calibrada por retângulo da tela. O programa lê essa região e mede em milímetro sem você configurar nada.

O canto inferior esquerdo do quadro diz de onde vem a escala, e é clicável:

| O que aparece | O que significa |
|---|---|
| Escala: região do ultrassom | veio da tag do próprio aparelho, imagem por imagem |
| Escala: calibrada nesta imagem | você calibrou à mão aqui; vale só nesta imagem |
| Escala: calibrada na série | você calibrou à mão e marcou para valer na série toda |
| Sem escala — medidas em pixels | o arquivo não traz o tamanho do pixel e ninguém calibrou; a medida sai em px, dizendo que é px |

Para calibrar à mão: ferramenta **Linha de calibração**, trace sobre uma distância que você conhece (a régua da imagem, por exemplo) e informe o comprimento real. A janela pergunta também até onde a calibração vale — só esta imagem ou toda a série. No ultrassom o padrão é só esta imagem; nas outras modalidades, a série.

- A ordem de confiança é: calibração desta imagem, calibração da série, região do ultrassom, espaçamento do arquivo. Quem calibra à mão já viu que a tag não servia.
- Imagem de painel duplo tem uma região de cada lado: a medida usa a região em que ela está. Medida que atravessa de um painel para o outro volta a pixel — distância entre duas imagens diferentes não é distância.
- A janela do Doppler espectral não calibra distância: os eixos dela são tempo e velocidade, e o programa a recusa de propósito.
- Captura secundária de ultrassom (print da tela do aparelho) costuma vir sem região nenhuma: aí a calibração manual é o caminho.

## Imagens-chave

K (sugestão) marca e desmarca a imagem do quadro como imagem-chave; Shift+K mostra só as marcadas. Elas entram no laudo em PDF e no filme com um clique.

## Reconstruções: MPR, oblíquo, curvo e 3D

- **MPR** monta o volume e abre os três planos. Também dá para reconstruir só o quadro ativo em axial, coronal ou sagital.
- A linha de orientação no canto do quadro é clicável: escolhe o plano, e **Oblíquo** vira o quadro oblíquo sem mudar a imagem — a partir dali a ferramenta **Girar plano** inclina.
- Espessura (slab) na barra do MPR, com média, MIP ou MinIP.
- MPR curvo (clique os pontos ao longo de um vaso) e 3D (renderização de volume, com cortes, escultura e exportação de malha STL/GLB/3MF).
- O plano reconstruído sai sempre na convenção de leitura — axial com anterior em cima e esquerda do paciente à direita — mesmo quando a aquisição foi sagital.
- **Tirar a mesa da TC**: botão direito no MPR ou no 3D de uma TC ▸ *Tirar a mesa da TC (MPR e 3D)*. O programa acha o corpo (o que passa pelo meio do volume) e apaga o que está fora dele, corte a corte — a mesa sai, os pulmões e as vias aéreas ficam. Vale para os volumes montados dali em diante (feche e abra o MPR/3D); a série original não muda.

> **O volume é montado na memória.** Em Configurações ▸ Sistema ▸ Desempenho há um teto; acima dele o programa pergunta antes de montar. O 3D roda na CPU, e o detalhe (lado do volume) também se ajusta ali.

# Vários monitores

O programa trata o conjunto de telas como uma estação, não como vários visualizadores independentes: passar de etapa, trocar de protocolo ou mudar o layout vale para o conjunto.

## Configurar

Configurações ▸ Monitores ▸ Papel, layout e ordem dos monitores. Cada tela recebe um papel:

| Papel | O que vai para lá |
|---|---|
| Banco de dados | a janela principal, com a lista de exames |
| Viewer | os exames abertos |
| Comparação | os exames anteriores, já ligados ao atual |
| Não usar | o programa não põe nada nessa tela |

A coluna **Ordem** diz qual tela é a 1, a 2, a 3 — e é esse número que a mamografia usa quando a etapa diz "com 2 telas, mostrar no Monitor 2". O botão **Ordenar pela posição na mesa (esquerda → direita)** é um bom ponto de partida; número repetido é recusado. **Identificar monitores** pisca o número em cada tela.

Com dois ou mais monitores marcados como Viewer, o exame abre repartido entre eles. Com um só, ele abre como aba, como sempre.

- **Mover estudo atual para o monitor** (menu Exibir) leva o exame aberto para outra tela.
- **Trazer todos os estudos de volta** devolve tudo à janela principal.
- A tira de séries pode ficar só no primeiro monitor — Configurações ▸ Monitores ▸ *Papel, layout e ordem* ▸ *Tira de séries só no primeiro monitor*, com três opções: só na mamografia, sempre que o exame abre repartido, ou nunca.
- A grade de cada tela é lembrada por tipo de exame (capítulo 5, *A memória do layout*).

> **No Linux** o papel dos monitores depende do X11 informar a geometria das telas; em alguns ambientes Wayland a identificação pode falhar.

# Mamografia: protocolos de exibição

Mamografia não usa o protocolo de exibição genérico dos outros exames. Ela tem uma aba própria, com **etapas**: cada etapa é um arranjo de quadros, e passar de etapa muda todos os monitores ao mesmo tempo. É o jeito que a leitura de rastreamento realmente funciona — CC, depois MLO, depois comparação com o anterior.

## Onde fica o editor

- Configurações ▸ Protocolos de exame ▸ **Mamografia**;
- ou, com uma mamografia aberta, a última linha do combo **etapa:** na barra do exame — *Editar protocolos…*.

## Criar um protocolo do zero

À esquerda fica a lista **Protocolos** — o primeiro ativo que combina é usado. Botões **+ Novo**, **Duplicar**, **Remover**, **Padrão**.

1. **+ Novo** e dê um **Nome:** (ex.: "Rastreamento 2 telas").
2. **Descrição do exame contém:** — vazio vale para qualquer mamografia; `RASTREAMENTO|DIAGNOSTICA` casa com qualquer uma das duas palavras. É isto que escolhe o protocolo quando o exame abre.
3. Marque **Ativo**. As outras três caixas são de apresentação: *Parede torácica voltada para o centro* (espelha a imagem quando precisa, para as duas mamas se olharem), *Encostar a imagem na borda da parede torácica* e *Zoom por quadrante em todos os quadros juntos*.
4. No grupo **Etapas**, **+ Etapa**. Dê um **Nome da etapa:** — ele aparece no combo do exame (ex.: "CC atual × anterior").
5. Defina o **Layout** (linhas × colunas) da etapa.
6. Preencha os quadros: ou pelo campo **Em texto:**, ou pela grade de combos, um por quadro.
7. Repita para as outras etapas e use ↑ e ↓ para pôr na ordem em que você lê.

## A sintaxe das células

Cada quadro recebe um código. A ordem é: incidência (opcional) + lado (obrigatório) + marcadores opcionais.

| Parte | Valores | Observação |
|---|---|---|
| Incidência | CC, MLO, ML, LM, XCCL, XCCM, AT, FB, SIO, SPOT, MAG, ANY | sem incidência = qualquer uma. FB, SIO e ANY funcionam mas não aparecem na lista da tela |
| Lado | D (direita) ou E (esquerda) | obrigatório |
| Tomossíntese | tomo ou dbt | pega a pilha da tomo em vez da 2D |
| Contraste (CEM) | rec, recomb, sub ou cem | a imagem recombinada |
| Anterior | ant / ant2 | ant = o exame anterior; ant2 = o anterior do anterior |

No campo **Em texto:**, colunas se separam por `x` e linhas por vírgula:

```
1 × 2   CCD x CCE
2 × 2   CCD, MLOD x CCE, MLOE
2 × 2   CCD, CCD ant x CCE, CCE ant     (atual acima, anterior abaixo)
1 × 2   CCD tomo x CCE tomo             (tomossíntese)
1 × 2   CCD rec x CCE rec               (contrastada, recombinada)
```

Código que o programa não reconhece é recusado na hora, com a mensagem "Código(s) não reconhecido(s): …". Na tela do exame, um quadro sem definição mostra *(quadro vazio no protocolo)*, e uma imagem que não existe mostra "… não encontrada (sem exame anterior)" — em vez de ficar preto sem explicação.

## Repartir a etapa entre monitores

Dentro da etapa: *Nesta etapa, com [1 a 4 telas] mostrar no [Monitor N]*. Você define, para cada número de telas, o que vai em cada monitor. O botão **Repartir sozinho** desfaz isso e devolve a etapa à repartição automática.

Sem arranjo definido, a repartição automática segue esta ordem: se as linhas dividem pelo número de telas, cada tela leva um bloco de linhas (duas linhas em duas telas = CC numa, MLO na outra); senão tenta pelas colunas; senão distribui os quadros em ordem. Com menos imagens que telas, cada tela recebe uma.

## Usar no exame

Com a mamografia aberta, a barra **Mamografia:** traz o combo do protocolo, o combo **etapa:**, e ◀ / ▶ para andar. As teclas de fábrica são **→** (próxima etapa), **←** (etapa anterior) e **Q** (zoom por quadrante). Ainda na barra:

- **Quadrante ↻** (Q) e **1:1** — leitura em tamanho real;
- **Lupa** — segure o botão; a roda muda o aumento;
- **Espessura: fina ▾** — slab da tomossíntese: 1, 5, 10 ou 20 cortes, em MIP ou média;
- **BE ⇄ Recomb.** — alterna baixa energia e recombinada na contrastada;
- **Implante** — corrige a prótese em todos os quadros (Alt+I); veja abaixo;
- **Densidade…** — mede a densidade mamária do que está nos quadros (capítulo 6);
- **2D ⇄ tomo** pula entre a 2D e a tomossíntese na mesma lista;
- **Mama no quadro** reenquadra a mama (veja abaixo);
- **✕** sai do protocolo.

### Implante (0.95; só "corrigir" desde a 0.96)

O botão **Implante** (Alt+I) acha a prótese de cada quadro e a **corrige**: o silicone desce ao nível de cinza do tecido em volta, mas o detalhe fino continua — o tecido que está na frente ou atrás da prótese aparece, e a borda não vira um degrau (método da patente US 8.160.346). **A janela (WW/WL) não muda**: fica a que estava antes de ligar o botão, inclusive se você a tinha ajustado à mão. O antigo "apagar" (área lisa) saiu.

Como a prótese é achada: é a região clara de **borda nítida e forma convexa**, ocupando de 5 a 85% da mama. Antes de procurar, o programa lê o que o aparelho escreve na imagem: com **BreastImplantPresent = NO**, ou numa incidência com o **implante deslocado** (rótulo terminado em ID, como RCCID) ou de **compressão localizada / magnificação** (RSCC, LMSCC…), ele não procura, e a barra de estado diz por quê. Se ainda assim houver prótese, botão direito dentro do silicone → **Achar o implante a partir daqui**.

Conferido no acervo: 28 imagens 2D de 5 exames, 2 com prótese — as 7 imagens com o implante à vista foram achadas, e nenhuma das outras 21. Sem as informações do aparelho, a busca só pela imagem confunde a borda da pá de compressão localizada com uma prótese; num aparelho que não escreva nada disso, use o clique. A cápsula muito calcificada deixa um anel claro e escuro na borda.

### Qual imagem entra no quadro

Para uma célula MLOD, o programa procura a imagem de lado e incidência iguais e prefere, nesta ordem: a que é "para apresentação", a que se chama exatamente aquela incidência, e por fim a mais recente.

- Quem decide a incidência, quando existe, é o rótulo que o aparelho gravou (GE, tag privada 0045,101B): RMLO é a MLO; RSMLO, RSCC, RMSCC e RCCS são variantes dela (complementar, magnificada), e todas trazem o mesmo ViewPosition e o mesmo código de incidência — o padrão DICOM não distingue as duas, o rótulo do serviço distingue.
- Sem esse rótulo (tomossíntese e V-Preview não o trazem), vale o nome da série: CESM_PROC_RMLO nomeia a MLO, CESM_PROC_RSMLO não. Nome que não fala de incidência (2D_PROC) não desempata nada.
- A complementar não fica escondida: um segundo quadro com a mesma incidência a mostra, e o rótulo do quadro passa a trazer o nome da série ("MLO D · CESM_PROC_RSMLO").
- Se o exame só tem a complementar, ela entra — quadro preenchido com aviso no rótulo é melhor que quadro vazio.
- A **2D sintetizada** da tomossíntese (V-Preview na GE) é uma incidência, não um volume: é uma imagem só, com o lado e a incidência nos grupos funcionais. Ela entra na célula 2D; se o exame também tem a 2D adquirida daquela incidência, a adquirida é que abre, e a sintetizada fica atrás dela na mesma lista do quadro. Quando é a sintetizada que está na tela, o rótulo diz "CC D · 2D sintética".

## Ao abrir, enquadrar

Metade do campo de uma mamografia é ar. Enquadrar a imagem inteira é enquadrar o ar — por isso cada etapa do protocolo tem um campo **Ao abrir, enquadrar:**

| Opção | O que faz |
|---|---|
| Mama ao quadro | acha a mama, descarta o ar e a escala para encher o quadro, com a parede torácica encostada na borda. É o padrão |
| Imagem inteira | o ajuste à janela de sempre (o detector todo cabe no quadro) |
| Resolução cheia | 1 pixel da imagem = 1 pixel do monitor; a imagem fica maior que o quadro e se navega com pan |

- O zoom sai do tamanho do quadro, que depende do monitor e do layout da etapa. Não há número fixo.
- As duas mamas da etapa ficam na mesma escala — comparar lado a lado em escalas diferentes não é comparar.
- A mama nunca fica menor do que no ajuste à janela.
- **Mama no quadro** na barra reenquadra na hora — para depois de mexer no zoom à mão.
- Imagem **arrastada** para um quadro (ou aberta nele com duplo clique na lista de séries) também entra enquadrada; num quadro do protocolo o conjunto é reenquadrado junto.
- Se a mama não for encontrada, o quadro abre com a imagem inteira e a barra de estado diz em quantos quadros isso aconteceu.

> **Nenhum protocolo combinou?** O exame cai num arranjo comum (ordenado por incidência e lado, em 2×2 ou 1×2) e o registro diz qual descrição não casou. O protocolo também não sobe se nenhuma imagem tiver lado reconhecível.

## Protocolos de exibição dos outros exames

**Protocolos de exibição** (Configurações ▸ Protocolos de exame) cuida de TC, RM, US e afins — do jeito da mamografia: cada protocolo tem **etapas**, e **← →** passam de uma para a outra.

**Ao abrir o exame**, o primeiro protocolo ativo que combinar (modalidade e "descrição do exame contém") abre na etapa 1. Uma barra aparece em cima dos quadros: o nome do protocolo, a lista das etapas (escolha qualquer uma), ◀ ▶, **Gravar a tela como etapa…**, **Editar protocolos…** e **Sair do protocolo** (deixa os quadros como estão). Vêm três de fábrica para você ajustar: **TC de tórax** (mediastino, pulmão e pulmão em MIP, cada um com axial e coronal), **RM de mama** (sem contraste, dinâmica, MIP da subtração) e **RM de crânio** (T2/FLAIR/difusão e pós-contraste com coronal).

**A aba** tem três partes:

- em cima, os protocolos, um por linha: Ativo, Nome, Modalidade, Descrição do exame contém (`|` = ou), quantas etapas e **Anterior no monitor de comparação**. Novo, Duplicar, Remover, ▲ ▼ (a ordem decide quem vale primeiro) e **Acrescentar os de fábrica**;
- embaixo à esquerda, as etapas do protocolo escolhido (+ Etapa, Duplicar, Remover, ▲ ▼);
- à direita, o desenho da etapa: nome, layout (linhas × colunas) e um botão por quadro. Clique num quadro e edite embaixo:

| Campo | O que faz |
|---|---|
| Série | palavras da descrição da série; com `\|`, alternativas **em ordem de preferência** (`T1 POS\|T1 GD\|T1` quer a pós-contraste antes da simples). A mesma série pode estar em vários quadros (axial num, coronal no outro) |
| Do exame anterior | a série vem do exame anterior da mesma modalidade |
| Plano | como foi adquirida, axial, coronal ou sagital (MPR) |
| Fase da dinâmica | série inteira, pré-contraste, pós-contraste 1 a 9 ou última fase. A série é procurada só entre as que fazem parte de uma dinâmica (▦); a 1ª fase da dinâmica é a pré, então "pós-contraste 1" é a 2ª fase do grupo |
| Reconstrução | nenhuma (como a série), **MPR** (corte fino no plano escolhido), MIP, MinIP ou média com a espessura em mm, **MIP 3D** ou **VR**. Os dois últimos fazem o mesmo que o botão 3D: cada quadro vira um volume próprio, com a barra do 3D inteira (modo, preset, opacidade, cor, Vistas, Cortar, Esculpir, Girar…) valendo para o quadro ativo |
| Metade (meia mama) | paciente inteiro, só a metade direita ou só a metade esquerda. O volume é cortado no centro do campo (direita-esquerda). Com MIP 3D ou VR, o 3D só daquela metade; com MIP/MinIP/média de espessura, o MIP **sagital** da metade inteira |
| Vista | de que lado se olha — as mesmas **Vistas** da barra do 3D: Anterior, Posterior, Direita, Esquerda, Superior, Inferior. No 3D é a câmera; num corte, vale quando o corte é daquele plano (lateral num sagital, frontal num coronal, de cima ou de baixo num axial) |
| Janela | um preset (Pulmão, Mediastino…) ou largura/nível escrito à mão (`1500/-600`); "do arquivo" deixa como veio |
| Cor | cinza ou uma tabela de cores |
| Posição | automática (o mesmo lugar ao trocar de série), primeiro corte, meio da pilha ou o mesmo ponto do quadro ativo da etapa anterior |
| Sincronia | quadros com o mesmo número rolam, ampliam e mudam de janela juntos |
| Com várias telas | em qual monitor o quadro fica; "o programa reparte" divide a etapa como na mamografia (pelas linhas, senão pelas colunas) |

**Gravar a tela como etapa…** é o jeito rápido: arrume o exame na tela (layout, séries, um coronal MIP de 10 mm, janela de pulmão, quadros sincronizados) e grave. A janela pergunta em que protocolo (ou um novo, com a modalidade e a descrição deste exame) e se a etapa entra como nova ou substitui a que está na tela. Depois, no editor, troque a série gravada por alternativas (`|`) para servir a outros aparelhos.

**Etapa com a avaliação dinâmica (0.94).** No editor, cada etapa tem **Abrir a avaliação dinâmica (mapas e curvas)**, com o layout dos mapas (os mesmos do botão Dinâmica) e a série da dinâmica (vazio = a dinâmica do exame, detectada sozinha). Ao chegar nessa etapa, o programa faz o que o botão Dinâmica faz, sem a janela: pega as fases, usa os **últimos parâmetros** que você usou no botão (limiares, pré, inicial, tardia, correção de movimento) e abre os mapas com o painel de curvas. Passar para outra etapa fecha a dinâmica; voltar abre de novo. A RM de mama de fábrica tem a etapa **Avaliação dinâmica** no fim — e quem já tinha a RM de mama gravada ganha essa etapa uma vez. Para mudar os parâmetros, use **Parâmetros…** no painel da dinâmica: a próxima vez que a etapa abrir, ela usa os novos.

**Reconstrução da etapa é volume 3D (0.93).** Clique num quadro em que a etapa montou uma reconstrução (MPR, MIP, MinIP ou média de espessura) e a barra **3D — modo** aparece, já no modo dele. Na primeira vez que você mexer nela (trocar o modo, preset, cor, Vistas, Cortar, Esculpir, Girar…), o quadro vira um 3D: o mesmo volume (a mesma fase, na dinâmica), cortado na espessura que estava na tela e olhando do mesmo lado. Os outros quadros continuam como estão. **Voltar à série** desfaz. O 3D é montado numa grade reduzida (Configurações ▸ Sistema ▸ Desempenho), então pode sair menos nítido que o MIP de espessura. A barra do MPR também passou a mostrar a espessura do quadro (62 mm, 165 mm…) em vez de "fino".

**MIPs de meia mama (0.90; em 3D desde a 0.92).** A RM de mama de fábrica tem a etapa **MIP das fases (meia mama)**: 2 × 2, quatro **MIPs 3D**, em cima a pós-contraste 1 e embaixo a pós-contraste 3; à esquerda a mama direita vista da **Esquerda** (mamilo para a esquerda), à direita a mama esquerda vista da **Direita** (mamilo para a direita). Cada quadro é um 3D próprio: clique nele e use a barra do 3D — girar, Vistas, cortar, trocar MIP por VR — sem mexer nos outros. A janela de cada MIP sai da própria projeção. Quem já tinha a RM de mama gravada ganha essa etapa no fim do protocolo uma vez (as outras etapas não mudam). Para outra combinação — a 2ª pós, a subtração, a mama inteira — mude a fase, a metade ou a frente de cada quadro no editor. As duas fases da etapa ficam montadas na memória, então os quatro quadros saem de dois volumes. O meio é o centro do campo de visão: num exame com o paciente fora do centro, a metade pode levar um pedaço da outra mama.

Quando a série de um quadro não existe no exame, o quadro diz **Série não encontrada** com o que procurou, e a barra de estado conta quantos faltaram. A reconstrução que o protocolo pede ao abrir não faz pergunta: volume acima do limite de memória (Configurações ▸ Sistema ▸ Desempenho) fica de fora, com aviso. Com o exame em várias telas, a etapa é da estação: passar de etapa numa passa em todas. Os protocolos feitos antes da 0.88 continuam valendo e viram protocolos de uma etapa ao salvar a aba.

### A memória do layout

Fora da mamografia, o programa aprende a grade sem que ninguém configure: você ajusta o layout de uma ressonância de ombro, e na próxima ressonância de ombro ela abre assim. A etiqueta é modalidade + as palavras da descrição que importam — lado, contraste e números não contam.

- A memória é por monitor e pela quantidade de telas: o arranjo de uma tela não é imposto quando o mesmo exame abre em duas.
- Um protocolo de exibição escrito por você sempre manda sobre a memória.
- Só a grade é guardada, nunca qual série estava em qual quadro.

# Mama: densidade, RM dinâmica e lesões

Este capítulo reúne o que o programa faz de específico para mama — a parte mais desenvolvida dele, e a que tem mais ressalvas escritas.

## Densidade mamária

**Arquivo ▸ Densidade mamária das imagens na tela…**, ou o botão **Densidade…** da barra de mamografia. O item do menu só aparece com exame aberto: a densidade é medida no que está nos quadros, não no exame inteiro.

Três métodos aparecem lado a lado, com a máscara desenhada sobre a imagem. Os dois primeiros (limiar de Otsu e FCM) concordam quase perfeitamente entre si: isso é precisão, não acerto. O terceiro é uma rede neural em ONNX.

> **O que falta para o número entrar no laudo:** a leitura cega — comparar a medida do programa com a sua categoria, sem você ver o número antes. Enquanto isso não for feito, trate o valor como orientação, não como laudo.

## RM de mama dinâmica

O programa reproduz o fluxo do CADstream: detecta as fases, corrige movimento, calcula os mapas paramétricos, classifica a cinética em seis cores e mede a lesão sobre o realce.

### Abrir a dinâmica

Botão **Dinâmica** na barra. A janela de parâmetros mostra as séries que ele reconheceu como fases e deixa escolher:

| Campo | O que é |
|---|---|
| Pré, inicial e tardia | quais fases são a pré-contraste, a de pico e a tardia |
| Realce mínimo (%) | abaixo disso o voxel não entra no mapa cinético |
| Rápido (%) / Tardio (±%) | os limiares das seis classes: médio 50–100%, rápido acima; persistente / platô / washout pela variação da tardia |
| Sinal mínimo do tecido (%) | máscara: pré-contraste de pelo menos N% do sinal de referência |
| Corrigir movimento | registro por translação 3D entre as fases |
| Disposição | quais mapas vão para quais quadros |

Os valores ficam guardados: o próximo exame abre com os últimos que você usou.

### Os mapas

| Mapa | O que mostra |
|---|---|
| MSI | velocidade do realce inicial (sinal/min) |
| PEI | realce de pico, em % sobre o pré-contraste |
| SER | razão de realce: < 0,9 persistente, 0,9–1,1 platô, > 1,1 washout |
| Cinética | as seis classes em cor: o tom diz o comportamento tardio (azul persistente, verde platô, vermelho washout) e o brilho diz a intensidade |
| Subtração | pós menos pré |
| MIP temporal | o maior realce de cada voxel em **qualquer** fase pós-contraste (máximo das subtrações): a lesão aparece no pico dela, mesmo que seja fora da fase inicial |
| Média temporal | o realce médio das fases pós-contraste |

**Paisagem.** Com a subtração ligada no menu da fase (canto do quadro), *Paisagem (anatomia na subtração)* devolve 10, 20, 30 ou 50% da anatomia à subtração — para achar o mamilo, o clipe ou a pele sem trocar de série. Vale para todas as fases e aparece no canto ("subtração + 20% anatomia"). A subtração digital (DSA) tem a mesma opção no menu dela.

Cada mapa guarda a cor que você escolheu por último, separadamente. A legenda ao lado sempre mostra a tabela em uso.

**Mudar o plano**: a caixa **Plano:** no alto do painel, ou o canto do quadro — Aquisição, Axial, Coronal, Sagital e **Oblíquo** (girável). Vale para os mapas, para a subtração e para as fases. Virar o plano calcula todos os cortes de uma vez (alguns segundos, com barra e botão de parar). **Voltar ao plano da aquisição** volta no corte que estava à vista. O quadro reconstruído não entra nas curvas — ROI em corte reconstruído atravessaria vários cortes originais —, mas dá para **segmentar nele**.

### Curvas tempo-intensidade

Com a ferramenta **Intensidade** clique num ponto, ou desenhe uma ROI (elipse, retângulo, polígono) em qualquer quadro da dinâmica. A curva aparece no painel, com a classificação na mesma régua do mapa. **Pior pixel das ROIs** acha, dentro da ROI, o pixel mais suspeito e marca com ✳.

### Medir a lesão

Ferramenta **Segmentar 3D**: clique na lesão e o programa cresce a região em três dimensões sobre o realce, não sobre o sinal bruto — no sinal bruto a gordura é tão clara quanto a lesão.

- **Limiar**: a barra *inclui mais ← → inclui menos* aperta ou solta a região, e ela se refaz sozinha quando você para de arrastar — volume, padrões e distância junto. Os botões − e + fazem o mesmo em passos.
- A lesão aparece desenhada em **todas as séries e planos** do exame: nas reconstruções, nas outras fases, em T2, em difusão. Ela é guardada em milímetros, no espaço do paciente, e volta desenhada quando você reabre o exame.

| Número | O que é |
|---|---|
| Volume | o volume da região crescida, em mL |
| Angiovolume | o volume da parte que realça: exclui necrose, fibrose e cisto |
| Realce de pico | maior aumento percentual na fase de pico, com a média ao lado |
| Eixos perpendiculares | os três maiores eixos perpendiculares entre si — não é a caixa nos eixos da série |
| Maior eixo | o que vai para o laudo |
| Percentual dos seis padrões | a distribuição que o mapa mostra em cor, em número |
| Heterogeneidade cinética | entropia de Shannon das seis classes, normalizada de 0 a 1 (a fórmula do CADstream não é publicada — e a tela diz isso) |

> **Região fina e comprida é vaso, não massa.** Quando o alongamento passa de três vezes o diâmetro da esfera de mesmo volume, o programa avisa. Ele não decide por você: avisa, e o ajuste do limiar é o freio.

Na janela da lesão: **Guardar como medida**, **Guardar e ligar a uma lesão…** (acompanhamento), **Salvar como DICOM SEG**, **Superfície 3D (STL)…** e os dois botões a seguir.

### Distância ao mamilo

O botão **Distância ao mamilo** mede da **borda** e do **centro** da lesão até o mamilo. São dois jeitos de achar o mamilo:

- **Marcar o mamilo** (recomendado): clique no botão e depois no mamilo, na imagem. A distância sai **na hora**, a partir do seu ponto, e o ponto vale para **as outras lesões da mesma mama** no exame — numa aquisição das duas mamas, cada mama tem o seu. Reaberto o exame, o ponto volta das lesões guardadas.
- **Automático**: sem marca, o programa procura o mamilo pela superfície da pele — o ponto mais anterior da pele do lado da lesão. Leva uns 15 segundos na primeira lesão do exame. Erra em mama cortada no campo ou com mamilo retraído; por isso a tela diz se o ponto é seu ou do programa.

A distância entra na medida guardada, no rótulo da medida, no painel de medidas, no laudo e na captura. As distâncias à pele e ao peitoral saíram do programa.

### Captura da lesão (2×2)

**Salvar captura (SC)…** grava no exame uma imagem 2×2 da lesão, como série nova "Captura: <nome>":

- sagital e coronal em cima, axial e a curva de realce embaixo; as imagens são a **2ª fase** da dinâmica (a primeira pós-contraste), com a borda da lesão na cor dela, o **plano inteiro** (sem zoom), letras de orientação e régua de 10 mm;
- a curva é o sinal médio da lesão inteira por fase, com tipo da curva, SER e classe cinética;
- rodapé com volume, angiovolume, realces, eixos, padrão dominante, heterogeneidade, distância ao mamilo, limiar usado e "medida semiautomática — conferir".

Se a lesão já tem captura, o programa pergunta: **Substituir a anterior**, **Criar nova** ou Cancelar.

### Editar uma lesão

No painel **Medidas**, **Editar lesão…** (ou duplo clique na linha) reabre a janela com o nome, o método, o limiar e o mamilo que você usou; **Guardar** atualiza a mesma medida. Se a dinâmica não estiver aberta, o programa oferece abri-la com as fases em que a lesão foi medida.

### Números do exame inteiro

Botão **Números do exame…** no painel da dinâmica. Ele mede sobre a máscara da mama e devolve: volume da mama na máscara, angiovolume do exame, realce de fundo do parênquima (média e mediana) e o percentual de cada um dos seis padrões — com a fórmula escrita ao lado.

> **Até onde esse número vale hoje.** A máscara corta na parede torácica, mas mantém pele, vasos e músculo peitoral. O realce de fundo da literatura é medido sobre o tecido fibroglandular, e essa separação ainda não existe. Então o número serve para comparar a mesma paciente e o mesmo serviço ao longo do tempo — não para virar categoria no laudo nem para comparar com número publicado.

### Dinâmica pronta na chegada

Em **Automação ▸ Dinâmica pronta** dá para mandar o programa, assim que um exame chega e bate com a regra, detectar as fases e decodificar os quadros em segundo plano — o exame abre instantâneo. Nada é gravado como série e nada é enviado.

## Difusão (ADC) em qualquer RM

Botão **Difusão** na barra (aparece na RM que tem uma série de difusão — DWI, DIFUSAO, TRACE… — e está em **Aplicações** nas outras). Abre um painel que não é modal: dá para desenhar no quadro com ele aberto.

- **Série de difusão**: a do exame, escolhida sozinha pela descrição; as outras RM ficam na lista, porque nem todo aparelho escreve "DWI".
- **Valores de b**: lidos do arquivo — o padrão (0018,9087) e os lugares próprios de cada fabricante (GE (0043,1039), Siemens, Philips). Uma caixa por b: desmarque o b que não quer no ajuste. Quando o arquivo não diz o b, digite-os na ordem em que se repetem em cada corte (ex.: *0, 1000*). Na série da GE anonimizada, que perde o privado, a imagem sem b numa série em que as outras têm b > 0 é o b0 — o painel avisa que deduziu.
- **Avisos antes de calcular**: só um b; sem b0; maior b abaixo de 500; cortes sem todos os b; TE diferente entre os b; mais de uma imagem por b no mesmo corte.
- **Calcular e gravar o ADC**: regressão de ln(S) contra b em todos os b marcados (com dois b, é ln(S0/Sb)/b). Unidade **×10⁻⁶ mm²/s**, a mesma do ADC da GE. Pixel com sinal do b0 abaixo do *limiar de ruído* (5% do percentil 99, de fábrica) fica 0; com três b ou mais, o pixel com ajuste pior que o *R² mínimo* (0,25) também. O mapa é gravado como série de RM do exame ("ADC (Ipê) · b0-1000"), com a geometria da DWI — sincroniza, mede com as ROIs de sempre (o valor do pixel é o ADC), vai para o filme, para a exportação e para o PACS — e abre no quadro ativo.
- **DWI sintética**: S(b) = S0·e^(−ADC·b) num b escolhido (50 a 5000), gravada como "DWI sintética b1500 (Ipê)". É uma imagem calculada: não use para calcular ADC.
- **Medir a ROI selecionada**: desenhe uma ROI (elipse, retângulo ou polígono) num quadro com a difusão, o ADC daqui ou o do aparelho; a tabela traz, para a mesma ROI, o **ADC daqui**, o **ADC do aparelho** (quando o exame tem) e o **sinal em cada b**: média, DP, mediana, mínimo e máximo. **Mandar ao laudo** leva a frase com a média, o DP e o mínimo.

**Conferido no acervo** (16 séries de cinco aparelhos GE, b0 e b1000 ou b750): no crânio o ADC daqui é o do aparelho (razão 1,0002, diferença mediana 0). Na mama a diferença é de ruído (mediana de 120 a 330 × 10⁻⁶ mm²/s): o aparelho calcula a mama com médias e direções que não grava na série DWI, e o Pioneer zera 94% da imagem. Por isso a tabela mostra os dois.

## Séries dinâmicas: juntar e separar

Dois problemas opostos, no mesmo lugar — Configurações ▸ Protocolos de exame ▸ **Dinâmicos**:

- **Juntar**: o aparelho grava uma série por fase (RM de mama). As séries que combinam viram uma dinâmica, e isso fica gravado no banco.
- **Separar**: o aparelho grava todas as fases na mesma série (a TC trifásica). A série é repartida em fases só na tela, com uma miniatura por fase na tira, e "Desfazer o grupo" devolve a série inteira. Nada é escrito, nenhum arquivo é tocado.

A regra é modalidade + descrição contém, comparada sem acento e sem caixa, e vale ao abrir o exame. Quando você marca uma dinâmica ou separa uma série na mão, o programa anota a regra como **pendente**: ela aparece na tabela e não age até você confirmar. Três situações — **Confirmada** (vale sempre), **Pendente** (não age) e **Ignorar** (vale só no exame em que nasceu).

# Listas de casos, listas inteligentes e modo reunião

O **Banco de casos**, no painel esquerdo da tela do banco, organiza exames em pastas e listas. Na criação (**+ Lista**) o programa pergunta o tipo:

| Tipo | Para que serve |
|---|---|
| Normal | uma coleção de exames que você monta à mão |
| Reunião | igual à normal, mas cada caso ganha nome amigável, história, resposta, notas e etiquetas — é a lista de uma sessão clínica ou de ensino |
| Inteligente (filtro) | você não põe exames: você escreve um filtro, e os exames que combinam aparecem sozinhos — inclusive os que chegarem depois |

## Criar uma lista inteligente

1. No painel esquerdo, **+ Lista**.
2. Dê o nome e escolha **Inteligente (filtro)**.
3. Preencha o filtro. Só os campos preenchidos entram na conta.

| Campo | O que faz |
|---|---|
| Busca | casa com nome do paciente, ID, accession ou descrição. `\|` separa alternativas |
| Modalidade | Todas, CT, MR, MG, US, CR, DX, PT, NM, XA, OT |
| Exame dos últimos | N dias (0 = qualquer data) |
| Descrição contém | pedaço da descrição do exame |
| Região contém | parte do corpo (body part) |
| Instituição / unidade contém | parte do nome basta |
| Origem | Qualquer, Importado, Recebido pela rede, Baixado do PACS, Pré-busca, Anonimizado |
| Só exames | com imagens-chave · com medidas · com comentário · protegidos · ainda não abertos · que não estão em nenhuma lista |

Exemplos do dia a dia:

```
RM dos últimos 3 dias          Modalidade: MR · Exame dos últimos: 3 dias
RM de mama                     Modalidade: MR · Descrição contém: mama
O que ainda não li             Só exames: ainda não abertos
Casos com medida, para rever   Só exames: com medidas
```

A lista inteligente fica na mesma árvore das outras, em verde, com a contagem ao lado. O conteúdo é recalculado toda vez que você a abre.

> **O que a lista inteligente não faz.** Não aceita arrastar exame para dentro (o filtro é quem manda), não aparece nos menus "Adicionar à lista", e seus casos não têm nome amigável, história nem resposta — numa reunião eles aparecem como "Caso 1", "Caso 2".

## Modo reunião

Serve para percorrer os casos de uma lista um a um com os dados do paciente ocultos em todo o programa — sessão clínica, aula, revisão por pares.

### Como entrar

- Botão **▶ Modo reunião** no painel esquerdo (apresenta a lista selecionada);
- botão direito na lista → **▶ Iniciar reunião**;
- botão direito num exame da lista → **▶ Reunião a partir deste caso**;
- botão **Reunião** da barra inicial.

### A barra da reunião

| Botão | Atalho | O que faz |
|---|---|---|
| ◀ Anterior / Próximo ▶ | Alt+← / Alt+→ | andar pelos casos |
| Casos ▾ | — | menu com todos, para pular direto |
| História | Alt+H | mostra o texto da história clínica do caso |
| Revelar resposta | Alt+R | mostra resposta, notas e etiquetas |
| Tela cheia | F11 | esconde a moldura da janela |
| Encerrar reunião | — | volta ao normal |

### O que muda enquanto a reunião está ligada

- a tabela do banco fica anonimizada, com o nome amigável do caso no lugar do paciente;
- todas as abas do visualizador ficam com Anonimizar ligado e travado — e o filme também;
- as janelas do PACS, da Gestão e do Painel de filmes ficam indisponíveis, com a explicação na tela;
- só um caso aberto por vez: ao passar para o próximo, o anterior fecha.

O botão **Ocultar** da tela inicial faz o mesmo esconder dos dados fora de uma reunião.

# Chamada externa (RIS, link e API)

A chamada externa é o que faz o RIS, um script ou um botão numa página abrir o exame certo no Ipê. São três portas de entrada — linha de comando, link `ipe://` e API HTTP local — e as três geram o mesmo pedido internamente.

> **O que entra e o que nunca entra.** De fora só são aceitos abrir, baixar e situação. Apagar e exportar não são expostos, em nenhuma das três portas.

## As três portas

1. **Linha de comando** — `ipe-cli.exe`:

```
ipe-cli open --accession 123456
ipe-cli open --study-uid 1.2.840.113619.2...
ipe-cli open --patient-id 00987
ipe-cli open C:\pasta\exame              (importa e abre)
ipe-cli retrieve --accession 123456      (baixa sem abrir)
```

2. **Link ipe://** — para o RIS web, um e-mail ou um atalho:

```
ipe://open?accession=123456
ipe://open?accession=123456&node=PACS&janela=viewer
ipe://retrieve?studyuid=1.2.840...
```

Registre o link uma vez em cada computador: **Rede ▸ Registrar link ipe:// neste computador**, ou `ipe-cli register-url`. O registro é no perfil do usuário e grava o caminho do executável: se o programa mudar de lugar, registre de novo.

3. **API HTTP local** — para scripts e para o RIS na mesma máquina:

```
GET http://127.0.0.1:8042/api/open?accession=123456&token=SEU_TOKEN
GET http://127.0.0.1:8042/api/retrieve?studyuid=1.2.840...&token=SEU_TOKEN
GET http://127.0.0.1:8042/api/status?token=SEU_TOKEN
Resposta: {"ok": true, "resultado": "aberto"}
O token também vale no cabeçalho: Authorization: Bearer SEU_TOKEN  (ou X-Token)
```

## Todos os parâmetros

Valem igualmente no link e na API. Na linha de comando, o mesmo parâmetro aparece como opção com dois traços.

| Parâmetro | Linha de comando | O que faz |
|---|---|---|
| accession | --accession | número do pedido. É o mais usado pelo RIS |
| studyuid ou study_uid | --study-uid | StudyInstanceUID |
| patientid ou patient_id | --patient-id | abre o exame mais recente do paciente (um só) |
| node | --node | onde buscar se o exame não estiver no banco: nome exato do nó ou AE title exato. Sem isto, busca em todos os nós marcados como "usar na busca" |
| janela (ou window, modo) | --janela | viewer = só o visualizador nesta chamada; completo = o programa inteiro. Sem o parâmetro, vale a configuração de Rede |
| token | — | só na API HTTP; obrigatório |
| requestType | — | IHE IID: PATIENT (os exames do paciente) ou STUDY (os exames pedidos) |
| accessionNumber, studyUID, patientID | — | os nomes do IHE IID; vários valores separados por vírgula (ou o parâmetro repetido); patientID aceita `123^^^EMISSOR` |
| mostRecentResults (ou recentes) | — | quantos exames abrir, dos mais recentes (até 4) |
| modalitiesInStudy (ou modalidades) | — | só exames com estas modalidades: `CT,MR` |
| lowerDateTime / upperDateTime (ou data_de / data_ate) | — | período: `2025-01-01` ou `20250101` |
| containsInDescription (ou descricao) | — | só exames cuja descrição contém o texto (sem diferença de acento e maiúscula) |
| c | — | link cifrado (abaixo) |

Valor que o programa não entende é recusado com motivo ("janela=minimizado: use viewer ou completo"), em vez de ser ignorado em silêncio.

### IHE Invoke Image Display

O programa entende o perfil **IHE IID** (o mesmo que o Weasis ViewerHub): `GET http://…:8042/IHEInvokeImageDisplay?requestType=PATIENT&patientID=123&mostRecentResults=2&modalitiesInStudy=CT&token=…` (ou `/display`). Pelo paciente sem filtro abre o exame mais recente; com filtro, os que passam (até 4). Os filtros valem também quando o exame é buscado no PACS. Parâmetros do IID que o programa não usa (viewerType, diagnosticQuality, keyImagesOnly) são aceitos e ignorados.

### Link cifrado

O link comum leva o ID do paciente em texto aberto — e o link fica no histórico do navegador. O **link cifrado** é `ipe://open?c=…`: nada do paciente à vista, só quem tem o **token da API** consegue montar, abre direto (como o link com token) e **vale 24 horas**. Para montar: **Rede ▸ Chamada externa ▸ Montar link cifrado…**, ou `ipe-cli link-cifrado "accession=123&node=PACS"`. O RIS monta igual, com HMAC-SHA256 (biblioteca padrão de qualquer linguagem):

```
chave = SHA256(token);  kc = HMAC(chave, "ipe-cifra");  ks = HMAC(chave, "ipe-selo")
texto = "accession=123&t=<segundos desde 1970>"
nonce = 16 bytes aleatórios;  fluxo = HMAC(kc, nonce + i em 4 bytes) para i = 0, 1, 2…
cifrado = texto XOR fluxo;  selo = HMAC(ks, nonce + cifrado)[:16]
c = base64url(nonce + cifrado + selo), sem "="
```

## O que acontece com o pedido

1. O programa procura no banco local por accession, study UID ou patient ID.
2. Achou: abre até 4 exames (1 quando a busca foi por patient ID). Com `retrieve`, responde `ja_no_banco` e não rebaixa nada.
3. Não achou: busca em todos os nós configurados (ou só no nó nomeado), responde `buscando` na hora e manda baixar os 4 mais recentes.
4. Nada encontrado: a barra de estado mostra o erro de cada nó e a resposta é `nao_encontrado`.

> **O exame chamado de fora abre enquanto baixa.** É o contrário do padrão da busca manual, e de propósito: na chamada externa não há ninguém para responder pergunta. Em Rede ▸ Chamada externa, a caixa *Chamada externa abre o exame enquanto baixa*.

## Modo "só o visualizador"

Quando a chamada abre só o visualizador, o exame aparece numa janela maximizada e o banco de dados não aparece — nem há caminho até ele por essa janela:

- a barra de menu tem apenas Exibir, Usuário e Ajuda;
- Exportar, Salvar medidas como DICOM SR e Enviar ao filme ficam escondidos;
- o exame abre em todos os monitores marcados como viewer, repartido pelo mesmo critério do caminho normal;
- fechar a janela de um monitor fecha o exame em todas;
- ao fechar o exame, o programa continua na bandeja: o nó DICOM segue recebendo e a próxima chamada abre na hora.

**Outro paciente com um já aberto.** Se a chamada traz outro paciente enquanto um ainda está aberto em algum monitor, o Ipê pergunta: fechar o anterior em todos os monitores, manter os dois ou não abrir. Em Rede ▸ Chamada externa, *Chamada com outro paciente aberto* decide sem perguntar. Abrir o seguinte com o anterior à vista é como a imagem de um acaba laudada no nome do outro. O filme faz o mesmo: pôr imagens de outro paciente num filme que já tem imagens pede confirmação.

Liga-se em **Rede ▸ Chamada externa ▸ Abrir só o visualizador (sem o banco de dados)**, ou por chamada com `janela=viewer` / `janela=completo` — o parâmetro manda sobre a configuração.

> **Isto não é controle de usuário.** Quem tiver acesso à máquina ainda pode abrir o programa pelo atalho. Para uma estação em que o operador só veja o que o RIS mandou, combine este modo com um usuário sem permissão de busca e exportação (capítulo 14).

## Configurar a API HTTP

Rede ▸ bloco *Chamada externa*:

| Campo | Observação |
|---|---|
| API HTTP local ligada | de fábrica, ligada |
| Porta HTTP | 8042 de fábrica |
| Token | gerado sozinho na primeira execução; botões Gerar novo e Copiar. Sem token configurado, toda chamada leva 401 |
| Aceitar chamadas de outros computadores | desligada, a API escuta só em 127.0.0.1. Ligada, aceita apenas os IPs da lista |
| IPs permitidos | separados por vírgula |

Só GET é aceito. Todo valor passa por uma peneira de caracteres e tamanho; tudo que chega por link ou HTTP vai para o registro com a origem.

## Instalado e portátil

O pacote traz dois executáveis: `Ipe.exe` (o de janela) e `ipe-cli.exe` (o de console) — no Windows, um programa de janela não tem saída padrão, então os comandos que respondem texto precisam do segundo. Na versão portátil (ZIP), tudo funciona igual, menos o link `ipe://`, que não vem registrado — rode `ipe-cli register-url` uma vez.

### Idioma

Desde a 0.99.33 o padrão é o **inglês**. O instalador do Windows pergunta o idioma na primeira tela (inglês, português ou espanhol, com o inglês marcado) e grava a escolha para o programa; os scripts `instalar.bat` e `instalar.sh` perguntam o mesmo. A versão portátil pergunta na primeira vez que abre. Depois, **Configurações ▸ Sistema ▸ Idioma** muda, e pela linha de comando: `ipe-cli set-language pt-BR` (ou `en`, `es`). Quem já usava o programa continua no idioma que tinha escolhido.

A tradução cobre as telas, menus, mensagens e as IAs. Ficam como estão os nomes que vêm do exame (descrição da série, instituição, paciente) e as siglas. Achou um texto em português na tela em inglês ou espanhol? **Configurações ▸ Sistema ▸ Idioma ▸ Editar traduções** corrige na hora, e vale a pena avisar para entrar na próxima versão.

# Rede DICOM, PACS e automação

## Nós e recebimento

**Configurações ▸ Rede ▸ Nós DICOM…**. A aba *Este computador* define o AE title, a porta e quem pode se conectar — é assim que o aparelho ou o PACS manda exames para cá. As outras abas cadastram os nós remotos.

### Dois tipos de nó: DIMSE e DICOMweb

No cadastro de um nó, o primeiro campo é **Tipo de conexão**, e ele muda os campos seguintes:

| | DICOM clássico (DIMSE) | DICOMweb (HTTP) |
|---|---|---|
| Como fala | C-FIND, C-GET / C-MOVE, C-STORE | QIDO-RS, WADO-RS, STOW-RS |
| Identificação | AE title dos dois lados | usuário e senha |
| Precisa de porta aberta aqui? | só com C-MOVE | não |
| Atravessa firewall e proxy? | difícil | sim, é HTTP |

O endereço do DICOMweb é a base, a que costuma terminar em `/dicom-web` (por exemplo `http://192.168.1.216:8042/dicom-web`). **Testar rede** funciona nos dois.

> **Três coisas sobre o DICOMweb.** Não existe C-MOVE ali: o download volta pela mesma conexão. Identidade de AE não vale num nó DICOMweb — quem identifica é o usuário e a senha. E a senha fica em texto claro no banco deste computador: use um usuário só de leitura quando o PACS permitir.

| Campo do nó | Para que serve |
|---|---|
| Nome / AE Title / Host / Porta | identificação do nó remoto |
| Usar na busca | entra na busca quando nenhum nó é nomeado |
| Usar em anteriores | entra na pré-busca de exames anteriores |
| Usar no envio | aparece na lista de destinos do "Enviar para" |
| Recuperação | C-GET (as imagens voltam pela mesma conexão) ou C-MOVE (o PACS abre conexão de volta e precisa ter este computador cadastrado) |
| Abrir enquanto baixa | por nó; vazio = usa o padrão das preferências |

### Identidades: falar "como" outro aparelho

Algumas modalidades só conversam com quem elas conhecem — o OsiriX da sala, por exemplo. Em **Configurações ▸ Rede ▸ Nós DICOM…**, aba **Identidades**, você cadastra esses AE (nome, AE title, destino do C-MOVE e em quais nós podem ser usados). Depois:

- na busca do PACS, o campo **Como:** escolhe com qual identidade buscar e baixar;
- no **Enviar para ▸ nó ▸ como…**, a identidade escolhida é a que envia.

### Quando o DICOMweb reclama

| Mensagem | O que conferir |
|---|---|
| HTTP 401 — usuário ou senha recusados | o usuário e a senha do nó |
| HTTP 403 — acesso negado | o usuário existe mas não tem permissão para essa operação |
| HTTP 404 — endereço não encontrado | a base: falta ou sobra /dicom-web, ou a porta está errada |
| o certificado não foi aceito | HTTPS com certificado próprio: marque aceitar certificado não verificado |
| não consegui falar com o servidor | endereço, porta ou rota |

## Buscar e baixar

Botão **PACS** (ou Ctrl+Shift+F). Busca por paciente, ID, accession, data e modalidade, em um ou em vários nós ao mesmo tempo. O resultado traz as séries, e dá para baixar série por série — isso depende de o PACS responder ao C-FIND de séries; quando não responde, o download é do exame inteiro.

Botão direito nos resultados da busca:

| Item | O que faz |
|---|---|
| Baixar para ▸ | o exame (ou as séries marcadas) vai **do nó direto para outro destino**, sem passar por este computador: um C-MOVE pedido ao nó de origem, com a identidade de *Como:*. **Outro AE…** aceita um destino não cadastrado. Quem decide se aceita o destino é o nó de origem |
| Enviar para ▸ nó ▸ como… | baixa o exame para cá (se ainda não estiver) e, ao terminar, envia ao nó escolhido com a identidade escolhida. Exame já completo aqui sai na hora |

O download usa a identidade de **Como:** da busca; o envio usa a escolhida no menu — são duas, de propósito. As tarefas aparecem na fila de transferências, com andamento, cancelar e o motivo de cada erro ("X não conhece o destino Y: ele precisa estar cadastrado em X").

## Enviar

**Enviar para** está no botão direito da lista de exames, das séries do banco e dos resultados do PACS, sempre com o mesmo submenu: um item por nó marcado como *usar no envio*, e em cada nó *como este programa* ou *como* uma identidade permitida naquele nó. Nas séries, só as selecionadas vão. A fila e o registro de acesso dizem o que foi, para onde e como.

## Automação

**Rede ▸ Automação…**:

| Aba | O que faz |
|---|---|
| Buscas agendadas | busca sozinha no PACS no horário escolhido e avisa ou baixa |
| Anteriores | ao chegar ou abrir um exame, busca os anteriores do paciente pelas suas regras |
| Roteamento | exame que chega e bate com o filtro é reenviado para outro nó |
| Dinâmica pronta | detecta as fases e decodifica os quadros em segundo plano. Nada é gravado e nada é enviado |
| Limpeza | apaga exames antigos por idade, por modalidade ou por falta de uso — exames protegidos nunca entram, nem cópias anonimizadas |

A aba **Histórico** mostra o que cada regra fez e quando.

## Servidor central (intranet)

**Configurações ▸ Rede ▸ Servidor central…** põe uma instalação no papel de servidor, com login e banco compartilhado; as outras entram como cliente. É para um grupo pequeno na mesma rede — o banco é SQLite.

## Compressão sem perda

**Arquivo ▸ Relatório do acervo (formato e compressão)…** mostra o que o acervo tem e quanto a compressão sem perda economizaria. A compressão troca o arquivo só depois de conferir pixel a pixel, lendo de volta do disco, que a imagem é idêntica.

# Gestão DICOM: os exames das modalidades estão no PACS?

A conferência que se faz à mão — abrir cada modalidade, ver os exames do dia e conferir no PACS exame por exame e série por série — feita num botão. Botão **Gestão** na tela do banco.

## Preparar uma vez

1. Cadastre cada modalidade como nó DIMSE (Configurações ▸ Rede ▸ Nós DICOM).
2. Para a modalidade que só aceita um AE conhecido (o do OsiriX, por exemplo), cadastre esse AE como identidade (capítulo 9).
3. Abra **Gestão**. No quadro **Modalidades**, marque as que quer conferir e, em cada uma, a identidade com que se fala com ela.
4. No quadro **PACS**: o nó do PACS, a identidade (*Como:*), o **Destino do C-MOVE** (normalmente o AE do próprio PACS) e **Como enviar**:

| Como enviar | O que faz |
|---|---|
| Direto; se a modalidade recusar, pelo computador | o padrão: a modalidade manda direto ao PACS; se ela não conhecer o PACS, o exame passa por este computador |
| Só direto | só a modalidade manda ao PACS |
| Só pelo computador | baixa aqui e reenvia ao PACS como a identidade escolhida |

Tudo fica lembrado: a rotina do dia seguinte é um clique.

## Testar o nó

**Testar o nó selecionado** responde, sem mandar nada: se o C-ECHO passa com a identidade, se a modalidade busca por data, se informa a contagem de imagens por exame e por série, se responde no nível imagem e se conhece o PACS como destino (um C-MOVE de teste de um exame inexistente: a recusa 0xA801 diz com certeza que não conhece; "aceitou" não prova que conhece, e a tela diz isso).

## Conferir

No quadro **O que conferir**: o **Período** (Hoje, Ontem, Ontem e hoje, Últimos 7 dias ou datas), **Ignorar séries** (as que a modalidade guarda e não manda de propósito, como *Patient Protocol*) e *Conferir imagem por imagem* (mais lento; diz quais imagens faltam). Depois, **Conferir**.

| Situação | O que significa |
|---|---|
| ✖ ausente no PACS | o exame não chegou |
| ◐ incompleto | faltam séries, ou séries estão com imagens a menos (diz quais e quantas) |
| ≠ outro UID | no PACS há um exame com o mesmo accession e outro UID — refeito, fundido ou corrigido. Mandar criaria duplicata, e o programa avisa |
| ? sem contagem | o nó não informa número de imagens nem responde no nível imagem |
| ✔ completo | está tudo lá. PACS com imagens a mais não é defeito |

O pior vem primeiro. **Mostrar: Só os com problema** filtra; as séries aparecem abrindo o exame. Se os três primeiros exames dão o mesmo erro, a conferência para e diz o motivo uma vez — erro que se repete em todos é do nó, não do exame (por exemplo, o PACS que aceita a conexão e recusa toda busca: costuma ser falta de permissão do AE; escolha em *Como:* a identidade que funciona).

## Enviar o que falta

- **Enviar o que falta ao PACS** manda só as séries que faltam e, nas incompletas, só as imagens que faltam.
- **Enviar o exame inteiro** manda tudo.
- Depois do envio o exame é **conferido de novo** — "enviado" não é "está no PACS". A coluna Envio diz o que aconteceu, e tudo vai para o registro de acesso.
- **Exportar CSV…** grava a conferência para abrir no Excel.

> **Quem aceita o destino é quem envia.** No C-MOVE, o programa só escolhe o nome do destino; a modalidade decide pela tabela dela. Se ela não tem o PACS cadastrado, o envio direto não existe — por isso o padrão cai para "pelo computador". Nós DICOMweb não entram na Gestão: conferir e mandar direto são C-FIND e C-MOVE.

# Laudo

Botão **Laudo** na tela inicial, ou botão direito no exame → **Laudo…**.

1. Escolha um **Modelo:** e clique **Aplicar modelo**. São 18 de fábrica — mamografia (rastreamento, diagnóstica, tomossíntese, CEM), US de mamas, RM de mamas, crânio, abdome e pelve, TC de crânio, tórax, angio-TEP, abdome e oncológica, PET-FDG, PET-PSMA, radiografia de tórax pela **Classificação da OIT** (pneumoconioses: qualidade, pequenas e grandes opacidades com a profusão na escala de 12 pontos, pleura e símbolos) e laudo livre. Eles preenchem sozinhos campos como paciente, idade, data, comparação e medidas.
2. Escreva o texto. O menu **Inserir ▾** traz para dentro do laudo o que o programa já mediu: medidas do exame, acompanhamento de lesões, segmentações (volume, SUV, TMTV/TLG, distância ao mamilo), curvas tempo-intensidade, comparação com anteriores, composição mamária e achados de CAD/IA.
3. No painel **BI-RADS**, à direita, monte os achados (mama, tipo, descritores, tamanho, localização, distância do mamilo, evolução, categoria) e a conduta; **Levar ao texto do laudo** escreve tudo no corpo.
4. Finalize: **Salvar rascunho**, **Salvar PDF…** ou **Assinar e liberar**.

No rodapé dá para incluir as imagens-chave no PDF, guardar o PDF no exame (como série DICOM) e guardar DICOM SR. Laudo assinado não muda: cria-se uma retificação, que vira um laudo novo e guarda o anterior. Assinar exige a permissão *Assinar (liberar) laudos*.

Os modelos se editam em **Modelos…** (nome, modalidades, palavras-chave, BI-RADS e o texto com campos automáticos entre chaves). Há *Restaurar os de fábrica*.

## Laudo em andamento (servidor central)

No modo cliente, quem abre o laudo de um exame passa a ser **quem está laudando**, até fechar a janela do laudo. Outro médico que abrir o laudo do mesmo exame é avisado ("Dra. Ana está laudando este exame desde 10:05") e escolhe **Só ler** (a janela abre sem poder gravar) ou **Assumir o laudo** (fica no registro de acesso, e o primeiro não grava mais). Quem só abre as imagens vê o aviso na barra de status. O servidor recusa gravar ou assinar o laudo de quem não está com ele. Se o computador de quem laudava travar, a trava cai sozinha em 10 minutos.

## Fechar o exame sozinho

**Configurações ▸ Visualizador ▸ Fechar o exame sozinho…**: fechar o exame (e a janela do laudo) ao **assinar o laudo**, e/ou fechar os exames abertos depois de **N minutos sem mexer** no mouse e no teclado (o rascunho do laudo é salvo antes). Evita que o próximo paciente seja olhado — ou laudado — com o anterior ainda na tela.

# Filme e impressão

## O compositor de filme

Botão **Imprimir** da tela inicial, **Arquivo ▸ Filme / impressão** (Ctrl+P), ou F1/F2 e o botão **Filme** dentro do exame. Com um exame aberto, o filme aparece como painel ao lado dos quadros; o botão de expandir, no canto da barra do filme (ou duplo clique no filme), alterna entre o filme grande e os quadros.

### Montar

- **Folha**: grade (linhas × colunas), papel, retrato ou paisagem, e *em todas as folhas* para aplicar ao conjunto. As folhas ficam à esquerda, com Nova, Duplicar, Subir, Descer, Excluir e Compactar.
- **Preencher**: F1 (a imagem do quadro) e F2 (a série do quadro, inteira ou um intervalo) no visualizador; arrastar miniaturas da tira para uma célula; o menu do botão Filme traz todos os quadros e as imagens-chave.
- **Textos**: o nível de texto nas células, cabeçalho, anonimizar, régua e fundo preto.

### Na célula

| Gesto | O que faz |
|---|---|
| Esquerdo arrastando | a função escolhida em **Mouse (botão esquerdo)**: Janela, Mover (a imagem dentro do quadro dela) ou Zoom |
| Alça ⠿ arrastada (canto da célula) | **troca a imagem de lugar** com a da célula onde você soltar — com qualquer função do mouse; vale entre folhas |
| Direito arrastando / meio arrastando | zoom / mover |
| Roda | passa o corte da série |
| Botão direito | menu: Mouse (botão esquerdo), copiar, recortar, colar, girar, espelhar, inverter, janela, cor, filtro, restaurar, abrir no visualizador, remover, inserir ou remover vaga |
| Ctrl/Shift + clique | seleciona várias |
| Ctrl+C / Ctrl+X / Ctrl+V / Ctrl+A / Del | copiar, recortar, colar, selecionar a folha, apagar |
| Duplo clique | expandir o filme (ou editar o texto, se for em cima de um texto) |

A função do botão esquerdo também está no botão **Mouse: …** da segunda barra, e fica lembrada.

### Anotações do filme

**➚ Seta**, **T Texto** e **✎ Lápis** anotam só no filme — nunca na imagem do exame.

- Depois de uma anotação, o mouse **volta sozinho** à função que estava (janela, mover ou zoom).
- Passando o mouse por cima de uma anotação o cursor muda: arrastar **move** a anotação; arrastar a **ponta ou a cauda da seta** muda o tamanho dela; **duplo clique num texto** edita o texto (texto vazio apaga a anotação).
- **Ctrl+Z** desfaz a última anotação.
- O botão **Anotações** liga e desliga todas as anotações do filme — na tela, na impressão, no PDF e no JPG/PNG. Escolher uma ferramenta de anotação religa.

### Salvar, imprimir e exportar

| Botão | O que faz |
|---|---|
| Salvar / Salvar como… | guarda o filme no banco (Abrir… e Arquivo ▸ Filmes salvos… o reabrem) |
| também no exame | caixa ao lado do Salvar: grava também o filme **dentro do exame**, no formato da estação AW da GE (veja abaixo) |
| Imprimir… | impressora do Windows |
| PDF… | uma página por folha |
| JPG/PNG… | uma imagem por folha |
| DICOM Print… | impressora DICOM (exige a permissão de impressão) |

Filme impresso sem ter sido salvo é salvo na hora da impressão, com o nome que tem — senão a impressão não apareceria no painel de filmes.

### Filme no exame (formato AW)

Com **também no exame** marcada, o Salvar grava no exame da primeira imagem do filme três coisas, como a AW grava:

- um **SR** "AW electronic film" com a planta do filme (páginas, vagas e posições);
- as **imagens soltas** de cada célula, com o texto e as anotações, na modalidade do exame;
- as **folhas prontas** "AW electronic pages", como sairiam impressas.

O filme lembra o que gravou. Se nada mudou desde a última gravação, o Salvar não grava de novo; se mudou, pergunta: **Substituir a anterior**, **Guardar as duas** ou **Agora não**. As séries gravadas aparecem na aba Impressões como filme da estação, como as da própria AW.

## Impressões recebidas

Botão **Impressões** (Ctrl+Shift+P): a lista do que as modalidades mandaram para cá e do que foi montado aqui, com pré-visualização. Em cima ficam a busca, o **Painel…** e as **Configurações…**; embaixo, as ações sobre o trabalho escolhido: abrir, **Enviar para…**, **Reimprimir…**, **Histórico…**, identificar o paciente, ver os **Parados…** e apagar.

### Histórico de envios e reimpressão

Cada envio fica guardado: quando, para onde, quem estava no programa, se foi **à mão**, **pela regra**, **reimpressão** ou **no compositor**, com qual modelo de folha, e se deu certo. Os três últimos aparecem embaixo dos detalhes do trabalho; **Histórico…** mostra todos. É daqui que o Painel tira o "Impresso por" das impressões DICOM (envio pela regra aparece como "regra (automático)"). O histórico começa na 0.84: o que foi enviado antes disso não tem histórico.

**Reimprimir…**: escolha um ou vários trabalhos (Ctrl ou Shift + clique) e cada um volta ao **último destino** em que saiu, com o mesmo modelo de folha. Antes de mandar, a janela diz quantos vão para cada destino; os que nunca foram enviados ficam de fora (para esses, use **Enviar para…**).

### Modalidade do trabalho

A impressão DICOM não diz a modalidade. O programa descobre assim: com o paciente identificado (OCR na chegada ou **Identificar paciente**), é a modalidade do **exame do paciente** feito até a hora da chegada (no mesmo dia ou no anterior); sem paciente, é a modalidade escrita no **cadastro da origem** (Configurações ▸ Impressão ▸ Servidores, destinos, regras e modelos ▸ Origens ▸ Modalidade). A coluna **Modalidade** da lista mostra o resultado. Ela vale para as **regras por modalidade** e para a **limpeza**.

### Colunas e filtros da lista

A lista de impressões funciona como a tabela do banco:

- **filtrar**: a caixa sob cada título filtra aquela coluna, com a mesma escrita do banco (`ana|maria`, `!Enviado`, `>=2` nas Folhas, `hoje` ou `7d` na Chegada); o botão direito no título abre **Filtrar valores de…**, para marcar os valores que ficam;
- **ordenar**: clique no título; o segundo clique inverte e o terceiro volta à ordem de chegada (mais recentes primeiro);
- **arrumar as colunas**: arraste o título para mudar a ordem; o botão direito ▸ **Colunas** esconde e mostra (o Paciente sempre aparece) e **Restaurar colunas padrão** desfaz. A ordem, as larguras e as colunas escondidas ficam salvas.

Embaixo da lista aparece quantos trabalhos estão à vista e o botão **Limpar filtros**.

### Pré-visualização

Clique num trabalho para ver a folha ao lado, com ◀ ▶ para passar as folhas. Vale para o que chegou da modalidade, para o filme que veio no exame e para o filme montado no compositor (este é desenhado na hora, só para olhar). O **duplo clique** abre: o filme do compositor abre no compositor para editar; os outros abrem o exame.

### Identificar o paciente de uma impressão

A impressão DICOM não traz nome nem ID do paciente. **Identificar paciente…** (com um trabalho recebido selecionado) abre uma janela com três caminhos:

- **Exames do mesmo aparelho e horário**: os exames do banco feitos no aparelho que mandou a impressão, perto da hora em que ela chegou — clique para usar;
- **Ler o cabeçalho da folha (OCR)**: o programa lê o texto gravado no alto da primeira folha (uns 2 segundos), mostra o que leu e procura no banco os pacientes cujo nome — ou ID — aparece ali, mesmo com espaço faltando, sem acento ou com letra trocada. Os que combinam entram no alto da lista, com a porcentagem ("OCR 95% · …"); quando o primeiro ganha com folga, ele já vem escolhido;
- escrever **Nome** e **ID** à mão.

> **O OCR é sugestão.** Ele lê o que a modalidade escreveu na folha e erra às vezes — confira o nome antes do OK. Se o paciente não está no banco, os campos são preenchidos com o que foi lido. O leitor vem dentro do programa e funciona sem internet.

### OCR na chegada

Quando um filme chega pela impressora DICOM, o programa procura o paciente no banco sozinho, sem travar a tela. Ele lê, nesta ordem, e para no primeiro que identificar: o **texto que a modalidade mandou à parte** (caixas de anotação e rótulo da sessão — há aparelho que não grava o nome na imagem), o **alto** da primeira folha, o **rodapé** e, por último, a **folha inteira** (uns 2 segundos por leitura):

| O OCR… | O que acontece |
|---|---|
| achou o paciente com folga clara | nome e ID entram no trabalho, o exame das folhas já sai com o nome, e o filme **segue pela regra** |
| não achou (ou ficou em dúvida entre dois) | o filme **fica parado**, com a Situação **Esperando paciente** |

A coluna **Situação** diz por que um filme recebido não saiu: **Esperando paciente** (o OCR não achou), **Parado: aparelho sem cadastro** (o paciente pode até ter sido achado, mas o aparelho ainda não tem nome em Origens — por padrão, filme de aparelho sem cadastro não sai sozinho), **Parado: origem desligada** ou **Na lista (nenhuma regra)**.

Para soltar um filme que ficou esperando: selecione e use **Identificar paciente…**. Depois do OK ele segue pela regra sozinho, pelo mesmo caminho do encaminhamento automático. Passar o mouse sobre o nome mostra de onde ele veio (OCR, confirmado à mão, escolhido entre os exames).

> **O paciente precisa estar no banco.** O OCR compara o que leu com os pacientes que já estão aqui. Filme que chega antes das imagens do exame fica esperando a sua confirmação.

Para desligar: **Configurações ▸ Impressão ▸ Servidores, destinos, regras e modelos ▸ Regras**, caixa "Identificar o paciente pelo OCR quando o filme chegar". Desligada, a regra age assim que o filme chega, como antes da 0.81.

### Imagens mandadas à impressora

Algumas modalidades (o ultrassom, por exemplo) mandam **imagens comuns** para a impressora em vez de um filme pronto. A porta de cada servidor de impressão aceita essas imagens:

- elas entram no banco como qualquer exame recebido;
- quando a modalidade termina de mandar, o programa monta **um filme por exame com todas as imagens**, na ordem em que chegaram (clipe com muitos quadros entra com até 16, espalhados). A grade e o papel vêm da **regra do Automático** que combinar (o "meu AE" é o AE daquela impressora); sem regra que combine, da grade padrão escrita embaixo da aba;
- se a regra do Automático tem destino, o filme vai para lá; senão, segue as **regras de impressão daquele servidor**, como um filme impresso;
- com o **OCR na chegada** ligado (Configurações ▸ Impressão ▸ … ▸ Regras), o programa lê o texto que a modalidade gravou nas primeiras imagens (alto, rodapé e, por último, a imagem inteira) e procura o paciente no banco. O nome que vem no cabeçalho das imagens **não** vale como prova: aparelho que manda nome genérico teria esse mesmo nome no banco. Achando o paciente, o nome e o ID vão para o filme — inclusive no cabeçalho da folha impressa — e ele segue pela regra. Sem achar, o filme fica com a Situação **Esperando paciente**: selecione e use **Identificar paciente…**, e depois do OK ele segue pela regra sozinho. Com o OCR desligado, vale o nome das imagens, como antes da 0.89.

O filme aparece na lista de impressões como "Montado aqui" e pode ser aberto no compositor.

**Configurações ▸ Impressão ▸ Servidores, destinos, regras e modelos de folha** (ou o botão da aba) tem as abas Servidores (cada um é uma impressora que as modalidades enxergam), Destinos, Origens, Regras, Modelos de folha, Automático e Limpeza.

**Automático** (filme montado sozinho, para a modalidade que manda **as imagens** e não o filme pronto, como o ultrassom): também é uma tabela de regras, uma por linha, com Origem (AE), Recebido por, Modalidade, outras condições, grade, quantas imagens, para onde vai depois e o modelo. O editor tem as mesmas três listas de marcar — **Origem (AE title de quem mandou)**, **Recebido por (meu AE chamado)** e **Modalidade** — e, em **Outras condições**, a descrição do exame (`MAMA|AXILA`). Embaixo, **Montar o filme assim**: grade, papel, quantas imagens (0 = todas), depois de montar (deixar na lista ou mandar para um destino) e o modelo de folha. A primeira regra ligada que combinar monta o filme, alguns segundos depois de o exame parar de chegar; um filme por exame.

O "meu AE chamado" é o AE que a modalidade pôs como destino. O nó DICOM aceita qualquer AE chamado na mesma porta, então dá para cadastrar no aparelho dois destinos com AEs diferentes (por exemplo `US_FILME` e `US_ARQUIVO`) e ter uma regra só para o primeiro. A lista mostra o AE do nó, as identidades e os AEs das impressoras; "Outro AE meu…" acrescenta um nome novo. A configuração única de antes da 0.86 virou a primeira regra da tabela.

**Regras** (aba Regras): uma tabela, uma regra por linha, com as colunas **Origem (AE)**, **Recebido por** (o seu AE), **Modalidade**, outras condições, destino, modelo e se para ali. A caixa da primeira coluna liga e desliga a regra; ▲ ▼ mudam a ordem (a primeira que combinar manda); duplo clique edita.

No editor da regra, o **Quando** são três listas lado a lado, de marcar:

- **Origem (AE title de quem mandou)**: os AEs que já mandaram trabalho, com o nome dado em Origens. Para um aparelho que ainda não mandou nada, escreva o AE em "Outro AE title…" e clique **+**;
- **Recebido por (meu AE)**: os seus servidores de impressão (AE, porta e nome);
- **Modalidade**: MG, CT, MR, US… (as das origens entram junto; "Outra…" acrescenta). A modalidade é a do exame do paciente identificado ou, sem paciente, a do cadastro da origem; trabalho de modalidade desconhecida não combina com regra que exige modalidade.

Em cada lista dá para marcar vários; lista sem nada marcado é "qualquer". O trabalho precisa combinar com as três. Para tratar diferente cada aparelho, cada AE seu ou cada modalidade, faça uma regra para cada caso (o **Duplicar…** ajuda). **Outras condições** guarda o resto: aparelho cadastrado (AE + endereço), AE com curinga (`MG*`), rótulo, tamanho do filme, número de folhas e horário. Embaixo, o **Resumo** diz em uma linha o que a regra faz. Regras feitas antes da 0.85 continuam valendo como estavam; ao abrir uma delas no editor, o servidor e a modalidade aparecem marcados nas listas.

**Limpeza** (aba própria): apaga sozinho, ao abrir o programa e de hora em hora, os trabalhos recebidos que atendem a **todos** os critérios marcados — mais velhos que N dias (pela chegada), **só os já impressos** (padrão), de uma **modalidade** (`MG`, `MG|US`) e de certas **origens** (nenhuma marcada = todas). **Quantos sairiam?** conta antes; **Limpar agora…** apaga na hora. Nasce desligada. Não apaga filme do compositor, filme que veio no exame nem o exame criado no banco com as folhas.

**Duplicar…**: em Servidores, Destinos, Regras e Modelos de folha, escolha um item e use **Duplicar…** para começar de uma cópia. Abre o editor já preenchido, com o nome "(cópia)", e você muda só o que for diferente; a cópia entra logo abaixo da original (nas regras, a ordem importa). O servidor copiado ganha uma porta livre, porque dois servidores não dividem a porta. A lista de impressoras DICOM (**Filme ▸ Impressoras**) também tem **Duplicar**.

> **Nada sai sozinho por padrão.** Servidor de impressão nasce desligado, destino automático nasce vazio e, sem nenhuma regra, o trabalho fica esperando na lista. Quem manda sair é você — ou uma regra que você escreveu.

## Painel de filmes e impressões

**Arquivo ▸ Painel de filmes e impressões…**, ou **Painel…** na aba Impressões.

- **O que entra**: os filmes montados no compositor **e as impressões que chegaram prontas pela impressora DICOM**. A coluna **Origem** diz qual é qual (Compositor ou Impressão DICOM).
- **Filtros**: período, origem, modalidade, usuário (ou aparelho), "parado há mais de N dias" e só os não impressos.
- **Cartões**: filmes (quantos do compositor e quantos por impressão DICOM), **% impressos**, parados (salvos e não impressos há mais de N dias), e as medianas de **exame → filme**, **filme → impressão** e **exame → impressão** (com o percentil 90 no detalhe e a % impressa em até 24 h), folhas impressas e reimpressões.
- **Gráficos**: filmes por mês (impressos e não impressos) e % impresso por modalidade.
- **Tabelas** por modalidade e por usuário ou aparelho, e a lista de filmes (ordenável; duplo clique abre o filme no compositor ou, na impressão DICOM, o exame com as folhas). **Exportar CSV…** para o Excel.

| Detalhe | Como é contado |
|---|---|
| Modalidade | a das séries das imagens que estão no filme: num PET/CT, filme só de TC conta como TC. Filme com duas modalidades conta nas duas |
| Impressão | impressora do Windows, DICOM Print e envio pela aba Impressões contam; PDF e JPG/PNG não |
| Tempos | exame → filme vai da data/hora do estudo até o filme salvo; filme → impressão, até a última impressão. Tempo negativo (hora errada do aparelho) fica fora da conta |
| Impressão DICOM | conta a partir da chegada; "criado por" é o aparelho (o nome cadastrado em Origens, ou o AE). Fica como impressa quando é encaminhada, pela regra ou à mão. O exame é o do paciente identificado (OCR ou à mão), o mais recente feito até a chegada (no mesmo dia ou no anterior); sem paciente identificado, modalidade e tempos ficam em branco |
| Filmes antigos | usuário e destino só são gravados desde a versão 0.77; antes disso aparecem como "(não registrado)" |

O painel some no modo Ocultar e na reunião: a lista tem nome de paciente.

# Medicina nuclear e oncologia

## Medicina nuclear

Nos exames NM e PET aparece o botão **MN**, com: anterior e posterior lado a lado (com a mesma janela nos dois), inverter a escala, curvas e análise por ROI, renograma e as contas de captação.

SUV funciona no PET (com os dados de dose e decaimento do arquivo). Em SPECT/CT, não: a conversão exige calibração que não está no DICOM. O programa diz isso em vez de devolver um número inventado.

> **Valores normais de medicina nuclear não estão no código.** O programa devolve número; a faixa de referência é texto ao lado, nunca veredito. Quando uma conta não dá, a resposta é "não deu" — não um número grande.

## Acompanhamento de lesões

O painel de lesões dá nome a cada lesão, e as medidas de exames diferentes se ligam a ela. O painel mostra a evolução e calcula a resposta. **Layout das lesões** põe um quadro por lesão.

A segmentação 3D mede volume, SUV máximo e médio, TLG e, somando as lesões, TMTV. Os limiares (percentual do SUVmáx, SUV mínimo, método) ficam guardados, e a barra do limiar vale também para o percentual do SUVmáx.

## Tarefas de IA: andamento e cancelar

As IAs do Ipê (órgãos abdominais, níveis da coluna, cefalometria, índices do crânio, níveis linfonodais, implante na mamografia) rodam pedidas à mão ou **sozinhas quando o exame chega** (Configurações ▸ CAD/IA). Uma por vez; as outras esperam na fila.

- **Tarefas de IA** mostra cada uma: exame, ferramenta, se foi automática ou à mão, situação (na fila, montando o volume, rodando, gravando, pronto, erro, cancelado), a etapa e o tempo. Abre pelo botão **Aplicações** do visualizador, por **Exibir ▸ Tarefas de IA**, e pelo aviso **⚙ IA: 1 rodando, 2 na fila** que aparece na barra de status enquanto há alguma ativa (um clique abre a janela).
- **Cancelar a escolhida** (ou **Cancelar todas**): na fila, ela não começa; rodando, o processo é derrubado e **nada é gravado** no exame. O cancelamento fica no histórico da gestão automática. A janela não é modal: dá para continuar trabalhando com ela aberta.
- **Fechar o exame não interrompe a IA pedida nele**: ela continua rodando e grava o resultado no exame, que aparece ao abrir de novo. Se o trabalho não parar em 15 segundos depois do Cancelar (por exemplo, o processo travou), a tarefa é fechada à força e o exame fica livre para as outras IAs. Com uma só tarefa ativa, Cancelar a escolhida funciona sem escolher a linha.
- **No banco de dados**, o exame que tem resultado de IA ganha **✦** ao lado do nome (a dica diz quais: "IA: órgãos abdominais, coluna"), e o que tem IA na fila ou rodando, **⚙**. A coluna **IA** (Colunas ▾) mostra as duas coisas por escrito.
- **Órgãos abdominais** no visualizador: botão **Órgãos** (TC/RM de abdome ou pelve; nos outros exames, pelo botão **Aplicações**) ▸ *Segmentar órgãos abdominais desta série (IA)*. Grava as máscaras e a tabela de volumes no exame, como pelo botão direito no quadro.

## CAD, IA e anotações de outros sistemas

O botão **CAD/IA** reúne o que outro programa escreveu sobre o exame: SEG (segmentações), GSPS (anotações gráficas do aparelho ou da estação), SR (achados de CAD/IA) e RTSTRUCT (contornos de radioterapia). O número no botão diz quantos objetos o exame tem; o menu lista um por um, com *Ir para a imagem* de cada achado.

**Em qualquer plano.** Segmentações (SEG, inclusive as do TotalSegmentator: órgãos, cefalometria), contornos (RTSTRUCT), níveis da coluna, lesões segmentadas e linhas de medida automática aparecem também quando o quadro é reformatado (MPR sagital, coronal, oblíquo) ou noutra série do mesmo exame em outro plano: a máscara guardada corte a corte é empilhada num volume em milímetros e cortada pelo plano do quadro. O que é só 2D (mamografia, CAD de mamografia, anotações gráficas presas a uma imagem) continua só na imagem de origem.

Clicar no botão mostra ou oculta todos. A escolha fica guardada por tipo: se você desligou as segmentações de uma IA, elas nascem ocultas nos próximos exames — e as anotações que o técnico deixou no aparelho continuam aparecendo. Quando algo nasce oculto, a barra de estado avisa quantos estão escondidos.

> **Desenho gravado no pixel não é overlay.** Quando a IA grava o resultado como uma série de imagens novas, não há como desligá-lo: o caminho é **Ocultar** a série pelo botão direito na lista de séries.

## Fusão

Botão **Fusão**: sobrepõe uma série a outra no quadro ativo (PET sobre a TC, por exemplo), com opacidade, tabela de cores e limites mínimo e máximo, e a opção de ocultar o que está abaixo do mínimo.

# Medidas guiadas

Botão **Índices** (aparece em RM e TC de crânio; em outros exames, pelo botão **Aplicações**). Abre uma janela, por cima do visualizador, com um **roteiro**: a lista de medidas, uma de cada vez, cada uma com a ferramenta certa e o plano em que deve ser feita. Ao clicar em **Medir este passo**, a ferramenta do passo vai para o botão esquerdo; a próxima medida desse tipo, em qualquer quadro, vira o valor do passo, e o roteiro anda sozinho. A medida continua sendo uma medida comum, visível no quadro e no painel de medidas.

Roteiros de fábrica:

| Roteiro | Medidas | Conta |
|---|---|---|
| MRPI e MRPI 2.0 | áreas da ponte e do mesencéfalo (sagital mediano), pedúnculo cerebelar médio (sagital) e superior (coronal oblíquo), e, para o 2.0, o 3º ventrículo (três medidas) e os cornos frontais (axial AC-PC) | MRPI = (ponte ÷ mesencéfalo) × (PCM ÷ PCS); MRPI 2.0 = MRPI × (3º ventrículo ÷ cornos frontais) |
| Índice de Evans | cornos frontais e diâmetro interno do crânio, no mesmo axial | cornos ÷ crânio |
| Ângulo calosal | ângulo no coronal perpendicular ao AC-PC, na comissura posterior | — |
| Bulbos olfatórios | contorno do bulbo direito e do esquerdo em cada corte coronal T2 (planimetria) e, opcional, a profundidade do sulco olfatório no plano tangente à parte posterior dos globos | volume = soma das áreas × distância entre os cortes (Cavalieri), em mm³; contorno de novo no mesmo corte troca o anterior |

O plano e a espessura do corte são conferidos e viram **observação** ao lado do número, não recusa: medida num plano diferente do pedido, ou em corte acima de 3 mm, aparece com ⚠. Em exames com série 3D, use o MPR para chegar ao plano certo. Os valores de referência aparecem como texto ao lado do número, com a fonte — o programa não classifica. **Copiar o texto** e **Mandar para o laudo** levam o resultado no formato de lista, com as referências entre parênteses.

## Índices automáticos do crânio (SynthSeg)

No botão **Índices** (RM e TC de crânio): **Índices automáticos (IA, SynthSeg) desta série…**. A série do quadro ativo (de preferência a 3D T1; serve qualquer sequência, inclusive pós-contraste e 2D, e a TC) vai para o SynthSeg, que separa ventrículos, hipocampos, amígdalas e o resto do encéfalo. As contas são feitas pelo Ipê:

| Medida | Como sai |
|---|---|
| Índice de Evans | maior largura dos cornos frontais (ventrículos laterais à frente do 3º ventrículo, os dois lados no mesmo corte) ÷ maior diâmetro intracraniano no mesmo axial |
| 3º ventrículo | largura transversal a 25%, 50% e 75% do comprimento dele; vale a média |
| Ângulo calosal | no coronal da extremidade posterior do 3º ventrículo (comissura posterior): retas pelas paredes súpero-mediais dos ventrículos laterais |
| Volumes | hipocampos (com a assimetria), amígdalas, ventrículos e volume intracraniano estimado |

A janela de conferência é a mesma da cefalometria: valor, referência, de quem é o número, **Ver no quadro**, **Medir à mão** e o texto para o laudo. Trocar os cornos ou o diâmetro refaz o Evans. As medidas são feitas na segmentação de 1 mm que o SynthSeg produz de qualquer série (mesmo de uma 2D de 5 mm), nos **eixos do aparelho**, não reorientados ao AC-PC: com a cabeça inclinada, confira no plano certo. Ao abrir os roteiros **MRPI e MRPI 2.0**, **Índice de Evans** e **Ângulo calosal**, os passos que a IA mede já vêm preenchidos ("medido automaticamente (SynthSeg)"); **Refazer** mede à mão. Ponte, mesencéfalo e pedúnculos continuam à mão: o SynthSeg não separa a ponte do mesencéfalo.

No exame ficam a SEG **Encéfalo · SynthSeg** e a imagem **Índices do crânio: conferência · SynthSeg** (axial dos cornos, coronal da comissura posterior e a lista). Automático na chegada: **Configurações ▸ CAD/IA ▸ Índices do crânio (SynthSeg)…**. Precisa rodar uma vez de novo o instalar_segmentacao, que acrescenta a DIPY e os pesos do SynthSeg.

## Níveis linfonodais cervicais

Botão **Linfonodos** (TC de pescoço; em outros exames, pelo botão **Aplicações**): **Mapa dos níveis linfonodais (IA)**. A série de TC do quadro ativo vai para o TotalSegmentator, que acha os marcos; o Ipê monta o mapa dos níveis I a VII, direito e esquerdo, pelas regras de imagem do estadiamento:

| Nível | Regra usada |
|---|---|
| IA / IB | acima da borda de baixo do hioide e à frente da borda posterior da submandibular; IA entre as barrigas anteriores dos digástricos |
| IIA / IIB | do hioide à base do crânio, à frente da borda posterior do esternocleidomastóideo e lateral à carótida; IIB atrás da borda posterior da jugular |
| III | do hioide à borda de baixo da cricoide |
| IV | da cricoide à clavícula |
| VA / VB | atrás da borda posterior do esternocleidomastóideo; VB abaixo da cricoide |
| VI | entre as carótidas, do hioide ao topo do manúbrio |
| VII | abaixo do topo do manúbrio, entre as carótidas |
| retrofaríngeo | acima do hioide, medial à carótida |

O rótulo de cada nível ("IIA D") aparece em qualquer plano, no meio do pedaço que o corte atravessa — no axial, no coronal reformatado, no sagital. Com o mapa feito, uma lesão segmentada com a ferramenta **Segmentar** ganha o nível sozinha (nome "Linfonodo IIA E" e a regra que decidiu). Os marcos ficam na SEG **Níveis linfonodais · TotalSegmentator** (hioide, cricoide, carótidas, jugulares, esternocleidomastóideos, submandibulares), para conferir. Marco que não apareceu vira aviso, e o limite dele não é usado. Automático na chegada: **Configurações ▸ CAD/IA ▸ Níveis linfonodais…**.

## Cefalometria do cavum

Botão **Cefalometria** (aparece em TC de face, cavum ou pescoço; em outros exames, pelo botão **Aplicações**). Dois caminhos:

> **Estado do resultado** (vale também para os índices do crânio): a janela diz se o resultado está *automático — ainda não conferido*, *editado (\*)* ou *aceito por fulano em data*. Cada valor trocado leva "editado \*" na coluna De quem. **Aceitar o resultado** grava quem e quando, com o que foi editado; ao reabrir o exame, a janela volta como você deixou.

- **Automática (IA)**: a série de TC do quadro ativo (de preferência axial fina) vai para o TotalSegmentator, que separa palato mole e duro, naso, oro e hipofaringe, hioide, mandíbula, língua e as vértebras cervicais. As contas são feitas pelo Ipê sobre essas estruturas. Leva alguns minutos em CPU, e dá para continuar trabalhando. Usa a mesma instalação da segmentação abdominal; na primeira vez, baixa os modelos de cabeça e pescoço (ou rode de novo o instalar_segmentacao).
- **À mão (roteiro)**: a mesma janela, vazia; escolha a linha, clique em **Medir à mão** e faça a medida num quadro (régua; contorno para a área).

| Medida | Como sai |
|---|---|
| Área de secção transversal mínima | luz da via aérea (abaixo de −400 HU) dentro da faringe; área no plano **perpendicular ao eixo** da via aérea, onde ela é menor, com o local (terço do palato mole ou retrolingual) e a faixa (> 100 mm² normal; 50–100 moderadamente reduzida; < 50 acentuadamente reduzida). Um gráfico mostra a área ao longo do eixo |
| 1. Comprimento do palato mole | sagital mediano, da espinha nasal posterior à ponta da úvula |
| 2. Espessura do palato mole | a maior, perpendicular ao comprimento |
| 3. Espaço aéreo posterior | menor distância ântero-posterior da luz no sagital mediano: retropalatal (na altura do palato mole) e retrolingual (abaixo da úvula) |
| 4. Hioide ao plano mandibular | linha gônio–mento (Go–Me) traçada na mandíbula projetada no sagital; distância perpendicular até a borda superior do hioide |
| 5 e 6. Língua | maior largura laterolateral e comprimento ântero-posterior no sagital mediano |
| 7. Nível do hioide na coluna | linha horizontal pelo corpo do hioide contra os corpos de C1–C7 (ex.: platô inferior de C3) |

A janela mostra cada número com a referência e **de quem é** (automático ou editado). Para corrigir, digite na célula ou use **Medir à mão**; **Voltar ao automático** desfaz. **Referências…** troca os valores entre parênteses (ficam guardados). O texto sai no formato do laudo: a área mínima com o local e a faixa, e a lista numerada com as referências.

**Conferir no quadro:** as linhas de cada medida ficam no exame como sobreposição em 3D e aparecem em qualquer plano que as contenha — no sagital mediano reformatado (palato, espaço aéreo, Go–Me e hioide, língua AP, nível do hioide), no axial da altura (largura da língua), no oblíquo perpendicular ao eixo (área mínima). Na janela, **Ver no quadro** (ou duplo clique na linha) reformata o quadro ativo no plano certo e vai ao corte da medida. Medida trocada à mão perde a linha automática. As linhas ligam e desligam no botão CAD/IA, como as outras sobreposições.

**Automática na chegada:** em **Configurações ▸ CAD/IA ▸ Cefalometria do cavum…** (ou na página CAD/IA das Preferências) marque *Fazer automaticamente quando o exame chegar*. Vale para TC que chega pela rede ou é importada, quando a descrição do exame contém um dos pedaços escolhidos (de fábrica: CAVUM, RINOFARINGE, NASOFARINGE, ADENOIDE, APNEIA, RONCO, CEFALOMETRIA, VIA AÉREA). A série é escolhida pela lista de preferência (de fábrica, a axial de partes moles), com espessura até 1,5 mm e pelo menos 40 cortes. Um exame por vez, em segundo plano; o que rodou aparece em Tarefas automáticas. Exame que já tem a cefalometria não é refeito. Ao abrir o exame, o botão **Cefalometria** abre direto os números guardados para conferir — sem rodar de novo. Para refazer, use Cefalometria ▸ Cefalometria automática (IA) desta série.

No exame ficam duas séries, só neste computador: **Cefalometria · TotalSegmentator** (as estruturas, que podem ser ligadas e desligadas como as outras segmentações) e **Cefalometria: conferência · TotalSegmentator**, uma imagem com o sagital mediano, as linhas de cada medida, a lista dos números e o perfil da área. Olhe essa imagem antes de usar os números: se uma linha caiu fora do lugar, aquele número não vale. As distâncias são medidas na posição em que o paciente está na mesa; cabeça muito fletida ou estendida muda o "horizontal" do nível do hioide.

# Configurações, usuários e exportação

Todas as janelas de configuração **diminuem e maximizam** (botões de maximizar e minimizar na barra da janela); o que não cabe rola.

## Níveis da coluna e vértebra de transição

**Identificar vértebras e discos desta série** (botão direito no quadro de uma TC ou RM da coluna) dá nome a cada vértebra e disco. Os nomes aparecem em qualquer série e plano do exame.

**De onde vem a numeração** — a janela final e a lista do objeto dizem qual foi usada:

| Âncora | Quando |
|---|---|
| contando a partir de C2 | a série pega a C2 e não falta vértebra até o sacro |
| pela última costela (T12) | TC sem C2: a vértebra da costela mais baixa é a T12 (supõe 12 pares) |
| C2 em outra série do exame | a série não pega a C2, mas outra do exame (coluna total, mesmo Frame of Reference) pega da C2 até ela |
| pelos nomes da IA | nenhuma das anteriores: confira |

Com C2 e costelas juntas, a costela confere a contagem: a última costela em L1 vira "L1 com costela", e em T11, "T12 sem costela" (transição toracolombar). Se a série pega da C7 à última costela, o número de pares aparece quando não é 12.

**Transição lombossacral** — os nomes seguem lombarizada / sacralizada:

| Na tela | Quer dizer |
|---|---|
| **S1 lombarizada**, sacro como **Sacro (S2)** | seis vértebras de tipo lombar; o disco de baixo é S1-S2 |
| **L5 sacralizada** | L5 ainda separada do sacro, com transição (marcada por você) |
| **Sacro (L5 sacralizada)** | só quatro lombares livres: a L5 está fundida ao sacro; o último disco é L4-L5 |
| **L5 transição?** | cinco lombares, mas com indício: disco L5-S1 rudimentar (menos da metade dos de cima) ou Castellvi sugerido |

**Castellvi** é sugerido pela forma da última vértebra livre: apófise transversa com 19 mm ou mais de altura (I) ou encostada na asa sacral (II; se for fusão óssea, troque para III). Precisa que a série pegue ±45 mm da linha média — a sagital de RM quase nunca pega, e aí a janela diz "não avaliável".

**Botão direito ▸ Numeração da coluna**:
- **Ajustar a numeração e a vértebra de transição…** — a janela abre com a vértebra que estava sob o clique. *Esta vértebra é a…* renumera tudo a partir dela; *Transição lombossacral* (nenhuma, L5 sacralizada, L5 fundida ao sacro, S1 lombarizada) renumera para ficar coerente; *Castellvi* vem com a sugestão e o motivo. A **frase para o laudo** se refaz a cada escolha (Copiar / Mandar para o laudo). **Aplicar** grava no exame e marca quem conferiu.
- **Um nível para baixo / para cima** — todos os nomes andam um nível. Se algum sairia da coluna (antes de C1 ou depois de S2), o programa recusa e diz.

**Exames seguintes do paciente**: a numeração que você aplicou fica guardada. Se o próximo exame do mesmo paciente sair diferente (por exemplo, L5 aqui e S1 lombarizada no anterior), aparece o aviso com a data do exame anterior.

## O menu Configurações

Tudo o que se configura mora no menu **Configurações** (e no botão Configurações da tela inicial), com um submenu por assunto: **Visualizador** (barra e aplicações, botões extras, mouse, atalhos, presets de janela, anotações, texto sobre a imagem, sincronização), **Protocolos de exame** (protocolos de exibição, mamografia, dinâmica da mama, dinâmicos, regiões do corpo), **CAD/IA**, **Monitores** (papel, layout, ordem e calibração GSDF), **Rede** (nós DICOM, automação, servidor central, link ipe://), **Impressão** (impressoras DICOM e configurações de impressão), **Banco de dados** (importação, pasta do banco), **Usuários** e **Sistema** (ao abrir o programa, desempenho, módulos, idioma). Cada item abre a sua própria janela, só com aquele assunto. Os menus Exibir, Rede, Impressão e Usuário ficam só com ações.

A janela completa, com todas as abas, continua em **Configurações ▸ Todas as preferências** (Ctrl+,):

| Aba | O que tem |
|---|---|
| Mouse | o que cada botão, clique e a roda fazem |
| Atalhos de teclado | as mais de 80 ações, com busca e cabeçalho que ordena por grupo, por ação ou por tecla; de fábrica só Q, ←, →, F1 e F2. E quais teclas (Shift / Ctrl / Alt) emprestam o botão esquerdo |
| Presets de janela | janelas nomeadas por modalidade |
| Monitores | papel, ordem, identificação e a tira de séries |
| Desempenho | cache de imagens, teto do volume de MPR, detalhe do 3D e tamanho da lupa |
| Protocolos de exibição | os protocolos com etapas dos exames que não são mamografia (layout, séries, planos, MIP, janela, cor) |
| Dinâmicos | as regras de juntar e separar séries |
| Mamografia | os protocolos com etapas (capítulo 5) |
| Geral | ao abrir o programa, texto e marcas sobre a imagem, botões na barra do visualizador, importação e idioma |
| Módulos | ligar e desligar Medicina nuclear, Mamografia, 3D, RM/TC avançado e Impressão recebida |

**Módulos**: desligue o que não usa e os botões e serviços daquele módulo somem. **Nenhum exame é apagado**: o exame continua no banco e abre como imagem comum; religar devolve tudo. Medicina nuclear leva os botões de MN e da fusão PET/CT; Mamografia, os protocolos ao abrir (o exame abre sem hanging) e a densidade; 3D, o botão 3D (o MPR fica); RM/TC avançado, o botão da dinâmica; Impressão recebida, os servidores de impressão (as portas param de receber), a lista e as configurações de impressão, o filme automático do ultrassom e a limpeza — o compositor e o painel de filmes continuam. Só quem tem a permissão de configurar muda os módulos.

Em Configurações ▸ Visualizador ▸ *Botões extras na barra*: quatro botões (Inverter, Girar e espelhar, Cine, Ocultar dados do paciente) saem da barra por padrão e vivem no menu **Mais**; desmarcar e marcar ali move entre os dois lugares. A função nunca some: só muda de lugar.

## Modo de uso

Na primeira vez que o programa abre, ele pergunta como vai ser usado. Dá para trocar depois em **Configurações ▸ Usuários ▸ Modo de uso**.

| Modo | Como fica |
|---|---|
| **Só eu uso este computador** | abre direto, sem pedir usuário e senha. Com usuários já cadastrados, entra como o escolhido ("Entrar como") ou, havendo um só, como ele |
| **Várias pessoas usam este computador** | cada um entra com o seu usuário. Na primeira vez você já cria o administrador ali mesmo |
| **Este computador é o servidor do grupo** | guarda os exames, os usuários e as configurações e atende os outros computadores (porta escolhida ali; certificado em Rede ▸ Servidor central) |
| **Conectar a um servidor do grupo** | usa o banco e os usuários do servidor; **Testar** confere o endereço. Entrar ou sair deste modo pede para reabrir o programa |

**Entrar com a conta do sistema.** Nos modos de várias pessoas e de servidor, a caixa *Entrar com a conta do sistema sem digitar senha* deixa quem abriu o programa com a conta do Windows/Linux ligada a um usuário entrar direto como ele. A conta de cada um fica no cadastro do usuário (**Conta do sistema**, com o botão *Usar a deste computador*); conta vazia sempre pede a senha, e usuário desativado não entra. Cada entrada assim fica no registro de acesso.

### Visível para: do serviço, pessoal ou compartilhado

Com várias pessoas (ou servidor), o cadastro de **nós DICOM**, **identidades**, **servidores de impressão**, **regras de impressão** e **regras do filme automático** tem o campo **Visível para**:

| Escolha | Quem vê |
|---|---|
| **Todos (do serviço)** | todo mundo. Só quem tem a permissão de configurar cria ou muda |
| **Só eu** | só você |
| **Eu e usuários escolhidos…** | você e quem você marcar |

- Item novo do administrador nasce **do serviço**; o dos outros nasce **pessoal**.
- Nas escolhas do dia a dia (com que nó buscar, para onde mandar) cada um vê o do serviço, o seu e o que compartilharam com ele.
- O **administrador** vê e edita, na tela de configuração, também o que é pessoal dos outros (coluna *Visível para*: "de fulano") — mas isso não entra nas escolhas dele.
- Quem **não** tem a permissão de configurar abre **Configurações ▸ Rede ▸ Nós DICOM** como **Meus nós DICOM**: só nós e identidades, e só os seus se editam.
- O que trabalha pelo computador — o nó DICOM que recebe, a automação, as regras de impressão — usa todos os itens, de quem forem.
- No modo **Só eu** o campo não aparece.

### Banco pessoal e compartilhado

Com várias pessoas (ou servidor), o painel **Locais** ganha o grupo **Banco**: *Tudo o que vejo*, *Meu banco*, *Compartilhado* e *Compartilhados comigo*. O administrador vê também **Banco de fulano (n)** para cada um que tem exames pessoais.

- O exame existe **uma vez só** no banco do computador: "pessoal" é uma marca. Mover entre os bancos não copia imagem. Laudos, medidas e anotações acompanham o exame.
- **Botão direito no exame ▸ Banco**: *Mover para o meu banco (pessoal)*, *Mover para o compartilhado*, *Compartilhar com…* (escolher usuários) e, para o administrador, *Passar para o banco de…*. Tirar um exame do compartilhado esconde dos outros, por isso só quem configura o computador faz isso — para juntar casos, use as listas.
- **Para onde vão os exames novos**: o que chega pela rede no AE de uma **identidade pessoal** (o "AE do Dr. Fulano", com *Visível para: Só eu*) vai para o banco do dono; o que chega no AE do serviço, para o compartilhado. O que **você** importa ou baixa do PACS segue a sua escolha em **Locais ▸ botão direito num banco ▸ Exames que eu importo ou baixo vão para** (de fábrica, o compartilhado).
- **O administrador** abre o banco pessoal de qualquer um; abrir esse banco e cada exame dele fica no **registro de acesso**. Quando alguém sai do serviço: botão direito em *Banco de fulano ▸ Passar o banco de fulano para* outro usuário ou o compartilhado.
- **Atenção**: no mesmo computador, "pessoal" esconde o exame **dentro do programa**, mas os arquivos continuam na pasta do banco — quem abrir a pasta pelo sistema vê as imagens. Sigilo de verdade só no modo servidor.
- A coluna **Banco** da lista (Colunas ▾) mostra de que banco é cada exame.

### Banco pessoal no servidor ou neste computador

No **modo cliente** o painel **Locais** mostra o **Servidor central** (onde a janela abre) e o **Banco deste computador**. Um clique troca: o banco deste computador abre **sem o servidor** — sem internet, intranet ou VPN — e serve de banco de casos.

- **Botão direito no exame ▸ Banco**, olhando o servidor: *Copiar para este computador* (fica nos dois) e *Mover para este computador* (sai do servidor — só o dono ou o administrador; exame com cadeado fica copiado). Olhando este computador: *Enviar ao servidor central…*, no seu banco pessoal ou no compartilhado.
- **Laudos, medidas, anotações, imagens-chave, comentários, etiquetas e o diagnóstico vão junto**, sem apagar o que já existe do outro lado. Ficam de fora as lesões acompanhadas (são do paciente) e os filmes. **As listas de casos vão junto** (desde a 0.99.36): o exame entra, do outro lado, na mesma lista e na mesma pasta (criadas se não existirem, com o mesmo *Visível para* quando quem leva pode), com nome amigável, história, resposta e notas; trazer de novo não duplica nada. Listas inteligentes não viajam: o filtro roda sozinho do outro lado.
- **Exames que eu importo ou baixo vão para** ganha, no modo cliente, *o meu banco neste computador*: o que você importa vai direto para cá e **não sobe** ao servidor. *O meu banco no servidor* sobe já marcado como seu. Desde a 0.99.36 vale também para o que **você baixa do PACS**: o exame novo fica no banco deste computador e não sobe; se ele estiver aberto numa aba, muda de lugar quando a aba fechar.
- **Levar um banco inteiro ao servidor** (o computador que passou a ser cliente): botão direito no local (este computador, um HD externo…) **▸ Enviar este banco ao servidor central…**. O administrador pode mandar *como estão*: cada exame no banco do dono. Nada é apagado daqui.
- **O servidor confere tudo**: exame do banco pessoal de outro não aparece na busca (nem pelo DICOMweb) e não é entregue a quem pede; tirar do compartilhado pede a permissão de configurar; pôr no banco de outro, só o administrador.
- **Trocar o modo de uso** não apaga nem copia exame: o programa avisa o que muda (por exemplo, de "várias pessoas" para "só eu", os exames pessoais passam a aparecer para quem usar o computador — e voltam a ser pessoais se voltar).

### Configurações pessoais, compartilhadas e do serviço

Com várias pessoas, também as **listas de configuração** têm três níveis — **do serviço** (todos), **compartilhadas com usuários escolhidos** e **pessoais**: protocolos de exibição, protocolos de mamografia, layouts da dinâmica da mama, modelos de folha da impressão, modelos de laudo e as **listas de casos** (inclusive as inteligentes).

- Nas janelas de sempre nada muda: cada um vê os do serviço, os seus e os compartilhados com ele. Item **novo** nasce do serviço quando é o administrador quem cria e pessoal para os outros.
- **Mudar um item do serviço** sem a permissão de configurar cria uma **cópia pessoal** com o mesmo nome, que toma o lugar do do serviço **só para você** — os outros continuam com o original. Com a permissão, muda o do serviço. Apagar o do serviço também pede a permissão.
- **Configurações ▸ Usuários ▸ Configurações pessoais e compartilhadas…** mostra, numa aba por assunto, quem vê cada item, com os botões *Todos (do serviço)*, *Só eu*, *Eu e usuários escolhidos…*, *Copiar para mim* e, para o administrador, *Passar para*. O administrador vê os de todos.
- **Listas de casos**: botão direito na lista ▸ **Visível para**. Numa pasta, vale para tudo o que está dentro. A lista pessoal aparece em itálico.
- A aba **Preferências** trata do que já era de cada um (atalhos, mouse, presets de janela, colunas): *Voltar ao padrão deste computador* ou, para quem configura, *Tornar as minhas o padrão deste computador*.
- Quem já tinha protocolos próprios nas preferências: na primeira entrada eles viram itens pessoais seus.
- No modo cliente tudo isso mora no servidor, que confere as regras; no "só eu" nada muda.
- **Regras de automação** (0.99.36): buscas agendadas, anteriores, roteamento, dinâmica pronta e gestão automática também têm **Visível para** no editor de cada regra, e a coluna na lista. Cada um vê as do serviço, as suas e as compartilhadas com ele; o administrador vê todas. **Todas rodam** — a automação trabalha pelo computador, de quem quer que seja a regra. O que uma busca agendada baixa vai para o **compartilhado**; numa busca pessoal, a caixa *Exames novos baixados por esta busca vão para o banco pessoal do dono* manda para o banco de quem é a regra. O **anterior** baixado por causa de um exame (pré-busca ou pela tira de anteriores) vai para o **mesmo banco** do exame atual. Na janela *Configurações pessoais e compartilhadas*, a aba **Regras de automação** muda quem vê e faz *Copiar para mim* (a cópia nasce pausada, para não rodar duas vezes). A automação é de cada computador: no modo cliente as regras ficam no computador, não no servidor.
- **Referências** da cefalometria e dos índices do crânio (o texto entre parênteses no laudo): no botão **Referências…**, *Vale para*: **Só para mim** (as suas, por cima das do computador) ou **Todos deste computador** (pede a permissão de configurar). A aba *Preferências* da janela de configurações pessoais também as volta ao padrão.
- **Chamada externa** (RIS, link `ipe://`, API): abre só o que quem está logado poderia abrir pela lista. Exame do banco pessoal de outro usuário não abre e nem é buscado de novo no PACS (a barra de status diz por quê); o administrador abre, e fica no registro de acesso.
- O que não tem três níveis, de propósito: as opções de exportação já são de cada usuário (com o padrão do computador por baixo); as listas inteligentes são listas de casos e já têm *Visível para*.

## Usuários e permissões

Botão **Usuários**. Quatro perfis de fábrica — Administrador, Médico, Residente e Técnico — e a tabela de permissões de cada perfil é editável pelo administrador.

| Permissão | O que libera |
|---|---|
| Abrir e ver exames | o básico |
| Importar arquivos | importação |
| Buscar no PACS / Baixar do PACS | consulta e download (e a Gestão DICOM) |
| Enviar para nós DICOM | mandar exames para fora |
| Exportar | CD, pendrive, imagens |
| Exportar com dados do paciente | sem isso, toda exportação sai anonimizada |
| Apagar exames | exclusão |
| Listas de casos e modo reunião | o banco de casos |
| Filmes e impressão | compositor, impressora DICOM e o painel de filmes |
| Escrever laudos / Assinar laudos | rascunho e liberação, separados |
| Configurar rede, automação e preferências | as janelas de configuração |
| Gerenciar usuários e ver o registro de acesso | administração |

## Exportar

**Arquivo ▸ Exportar…** (ou o botão **Exportar**) exporta o exame aberto ou os selecionados no banco:

- **DICOM** — pasta, CD ou pendrive, com DICOMDIR e, se quiser, um visualizador que abre no navegador (completo, com medidas, valores, ROIs e MPR; ou leve). Pode sair compactado em .zip.
- **Imagens** — JPG ou PNG, com formato, qualidade, janela (a do arquivo ou a do quadro atual), intervalo e tamanho máximo.

A anonimização é opção da janela — e obrigatória para quem não tem a permissão de exportar com dados do paciente.

### Anonimizar

Botão direito num exame — ou em vários — e **Anonimizar uma cópia deste exame…**. A janela abre já marcada para anonimizar, e há três destinos: DICOM, Imagens, ou **Cópia anonimizada no meu banco** — vira outro exame na lista, e nada sai da máquina.

| Escolha | O que acontece |
|---|---|
| Nome e ID | texto livre; `{n}` vira o número (ANON001, ANON002…). Na cópia no banco a numeração continua de onde parou, para duas cópias não virarem o mesmo paciente |
| Manter sexo / idade | o nascimento sempre sai; idade e sexo são opcionais |
| Manter datas do exame | sem isso, as datas saem em branco |
| Manter descrições | descrição do exame e da série (em alguns serviços elas contêm nome) |
| Manter instituição | nome e departamento |
| Remover tags privadas | tudo o que o fabricante acrescentou fora do padrão |
| Gerar UIDs novos | obrigatório (e travado) na cópia no banco: com os mesmos UIDs ela cairia dentro do original |
| Texto gravado na imagem | tarja preta: automático (ultrassom e imagens marcadas), faixa superior, ou não mexer nos pixels |

> **Anonimizar é cópia.** Os arquivos do original não são tocados. A cópia no banco aparece como origem *Anonimizado* e a limpeza automática não a apaga — ela só existe aqui. Vale conferir as imagens: em ultrassom o nome às vezes fica dentro da área da imagem.

## As tabelas

Em toda tabela do programa a divisa entre colunas se arrasta, e clicar no cabeçalho ordena onde isso faz sentido.

## Limitações conhecidas

- JPG/PNG exportado não apaga texto gravado na imagem nem aplica giro.
- O registro entre exames é só translação (não deformável).
- O 3D roda na CPU; o servidor central usa SQLite.
- Na mamografia, os anteriores saem só do banco local.
- O streaming não é sob demanda: o resto do exame entra na ordem em que o PACS manda.
- A Gestão DICOM é pelo botão (não é agendada) e não confere nós DICOMweb.
- O realce de fundo da RM de mama ainda não separa tecido fibroglandular de gordura.
- A captura da lesão usa a 2ª fase como imagem anatômica (não a subtração nem o mapa colorido).
- O instalador é só do Windows e ainda não é assinado digitalmente; não há atualização automática.
- A densidade está validada em 17 mamas de um único serviço.

# Receitas

Caminhos completos, do começo ao fim.

## Deixar a mamografia pronta em dois monitores

1. Configurações ▸ Monitores ▸ Papel, layout e ordem: marque duas telas como **Viewer** e ponha a **Ordem** 1 e 2. Confira com **Identificar monitores**.
2. Configurações ▸ Protocolos de exame ▸ Mamografia ▸ **+ Novo**. Nome "Rastreamento", Descrição do exame contém: vazio, **Ativo** marcado.
3. **+ Etapa** "CC": layout 1 × 2, *Em texto:* `CCD x CCE`.
4. **+ Etapa** "MLO": layout 1 × 2, `MLOD x MLOE`.
5. **+ Etapa** "Atual × anterior": layout 2 × 2, `CCD, CCD ant x CCE, CCE ant`.
6. Abra uma mamografia e ande com **→** e **←**; **Q** percorre os quadrantes.

## Conferir no fim do dia se os exames chegaram ao PACS

1. Uma vez: cadastre as modalidades como nós e, se preciso, a identidade com o AE que elas aceitam (capítulo 10).
2. **Gestão** ▸ marque as modalidades ▸ escolha o PACS ▸ **Testar o nó selecionado** na primeira vez.
3. Período **Hoje** ▸ **Conferir**. Mostrar: **Só os com problema**.
4. Selecione os incompletos e ausentes ▸ **Enviar o que falta ao PACS**. O programa confere de novo depois de mandar.
5. **Exportar CSV…** se quiser guardar o registro do dia.

## Mandar só algumas séries como outro aparelho

1. No banco, selecione o exame e, no painel de séries, as séries (Ctrl+clique).
2. Botão direito ▸ **Enviar N série(s) para** ▸ o nó ▸ *como* a identidade (o OsiriX, por exemplo).
3. Acompanhe na fila de transferências. Para um exame que ainda está só no PACS, o mesmo menu existe nos resultados da busca: ele baixa e envia sozinho.

## Fazer o RIS abrir o exame só no visualizador

1. Na estação, rode uma vez `ipe-cli register-url` (ou Rede ▸ Registrar link ipe://).
2. Em Rede, confira a porta e copie o token se for usar a API.
3. Cadastre o PACS como nó, marque *usar na busca* e escolha C-GET.
4. No RIS, monte o link: `ipe://open?accession={ACC}&janela=viewer`.
5. Teste com um accession que não esteja no banco: o exame deve abrir enquanto baixa.

## Ligar num Orthanc por DICOMweb

1. Peça a base do DICOMweb (algo como `http://servidor:8042/dicom-web`) e um usuário só de leitura.
2. Configurações ▸ Rede ▸ Nós DICOM ▸ **+ Novo**. Em **Tipo de conexão**, escolha DICOMweb (HTTP).
3. Preencha Nome, Endereço DICOMweb, Usuário e Senha. HTTPS com certificado próprio: marque *Aceitar certificado não verificado*.
4. Marque em *Usar em* o que fizer sentido e aperte **Testar rede**.
5. Abra o PACS e busque. O download volta pela mesma conexão: nada precisa ser cadastrado do lado do servidor.

## Medir uma lesão na RM de mama e guardar a captura

1. Abra o exame e o botão **Dinâmica**; confira a pré, a de pico e a tardia.
2. Olhe o mapa **Cinética**; desenhe uma ROI na lesão para ver a curva.
3. **Segmentar 3D** e clique na lesão. Ajuste a barra do **Limiar** até a região cobrir a lesão.
4. **Marcar o mamilo** e clique no mamilo: a distância sai na hora, e vale para as outras lesões da mesma mama.
5. Dê um nome e **Guardar como medida**; depois **Salvar captura (SC)…**.
6. No laudo, **Inserir ▾** traz as medidas e as curvas para o texto.

## Montar, imprimir e guardar um filme

1. No exame, **F1** em cada imagem que quer no filme, ou **F2** para uma série (inteira ou intervalo).
2. Escolha a grade da folha. Para trocar duas imagens de lugar, arraste pela alça ⠿.
3. Ajuste cada imagem com o botão esquerdo (Mouse: Janela, Mover ou Zoom, no botão direito da célula).
4. Anote com seta ou texto; o mouse volta sozinho à função anterior.
5. Marque **também no exame** e **Salvar**; depois **DICOM Print…** ou **Imprimir…**.
6. O **Painel de filmes e impressões** mostra o que foi impresso e em quanto tempo.

## Montar uma sessão de casos

1. **+ Lista**, nome da sessão, tipo **Reunião**.
2. Arraste exames do banco para a lista (ou botão direito → adicionar à lista).
3. Duplo clique na lista abre o organizador: dê a cada caso um nome amigável, a história, a resposta, notas e etiquetas.
4. **▶ Modo reunião**. Apresente com Alt+→; Alt+H mostra a história e Alt+R revela a resposta.

## Separar a TC trifásica que vem numa série só

1. Abra o exame, botão direito na série → **separar**.
2. As fases aparecem como miniaturas próprias na tira. Nada foi escrito no banco.
3. Em Configurações ▸ Protocolos de exame ▸ Dinâmicos, a regra nasceu como pendente: confirme para ela valer em todos os exames iguais, ou deixe em Ignorar.

# Apêndice: os atalhos

A lista de atalhos vem quase vazia. Só cinco teclas são de fábrica; todas as outras ações nascem sem tecla, para você escolher as suas em Configurações ▸ Visualizador ▸ Atalhos de teclado. Nada deixa de funcionar sem tecla: toda ação está num menu ou na barra. Atalho repetido é recusado com aviso.

## De fábrica

| Tecla | O que faz |
|---|---|
| Q | Mamografia: zoom por quadrante da mama — cada Q vai para o próximo, em ciclo |
| → | Mamografia: próxima etapa do protocolo |
| ← | Mamografia: etapa anterior |
| F1 | no exame: a imagem do quadro vai ao filme |
| F2 | no exame: a série do quadro vai ao filme (inteira ou intervalo) |

## Fixos (não configuráveis)

### Programa

| Tecla | O que faz |
|---|---|
| Ctrl+I | Importar pasta |
| Ctrl+P | Filme / impressão |
| Ctrl+Shift+P | Impressões |
| Ctrl+Shift+F | Consulta PACS |
| Ctrl+B | Voltar ao banco de dados |
| Ctrl+, | Todas as preferências (janela completa) |
| F1 | Guia do usuário (fora do exame; no exame é do filme) |
| Ctrl+Q | Sair |

### Modo reunião

| Tecla | O que faz |
|---|---|
| Alt+→ / Alt+← | próximo / anterior caso |
| Alt+H | História |
| Alt+R | Revelar resposta |
| F11 | Tela cheia |

### No quadro, sempre

| Tecla | O que faz |
|---|---|
| ↑ ↓ | rolar os cortes |
| PgUp PgDn | rolar 10 cortes |
| Home / End | primeira / última imagem |
| 1–9 | presets de janela |
| 0 | a janela do arquivo |
| Del | apaga a medida selecionada |
| Esc | cancela o que está sendo desenhado |
| Alt + roda ou Alt + ↑↓ | ajuste fino de um quadro ligado |

### No filme

| Tecla | O que faz |
|---|---|
| Ctrl+C / Ctrl+X / Ctrl+V | copiar, recortar, colar células |
| Ctrl+A | selecionar todas da folha |
| Ctrl+Z | desfazer a última anotação |
| Del | apagar as células selecionadas |
| ↑ ↓ ← → | passar o corte da célula |

## Sugestões, por grupo

Era o padrão até a versão 0.64 — está aqui para quem quiser repetir o mesmo mapa, ou parte dele. Os nomes das ações são os que aparecem na janela de preferências.

### Ferramentas e medidas

| Tecla sugerida | O que faz |
|---|---|
| W / Z / P / S | Janela / Zoom / Pan / Rolar cortes |
| M | Régua |
| X | Cursor 3D |
| A / Shift+C | Ângulo / Cobb |
| E / Shift+E / G | ROI elíptica / retangular / poligonal |
| Shift+G | Polilinha |
| Shift+A / T / B | Seta / Texto / Lápis |
| V | Intensidade (valor do pixel) |
| Shift+V | Segmentar 3D |
| , e . | imagem anterior / seguinte com medida |

### Imagem

| Tecla sugerida | O que faz |
|---|---|
| I | Inverter tons |
| F | Ajustar à janela |
| R | Restaurar visualização |
| C | Cine |
| H | Histograma da imagem (ou da ROI) |
| Alt+R / Alt+Shift+R | Girar 90° à direita / à esquerda |
| Alt+H / Alt+V | Espelhar esquerda ↔ direita / cima ↕ baixo |
| U | Lupa |
| Shift+Q | Zoom por quadrante: anterior |
| Shift+H | Ocultar dados do paciente |
| Shift+I | Mostrar/ocultar CAD/IA |

### Séries, MPR e dinâmica

| Tecla sugerida | O que faz |
|---|---|
| [ e ] | série anterior / próxima no quadro |
| K / Shift+K | marcar imagem-chave / mostrar as marcadas |
| Shift+P | Adicionar exame anterior |
| Shift+M | MPR liga/desliga |
| O | MPR oblíquo (desenhe uma linha) |
| Alt+1 / Alt+2 / Alt+3 | reconstruir o quadro ativo: axial / coronal / sagital |
| Shift+D | Avaliação dinâmica |

### Sincronização

| Tecla sugerida | O que faz |
|---|---|
| Shift+S | Sincronização automática (mesmo estudo) |
| L / Shift+L / Ctrl+L | ligar quadros / alternar modo / trocar grupo |
| Shift+W / Shift+Z | sincronizar janela / zoom e pan |
| Shift+R | Linhas de referência |
| Shift+Y | Tira de séries |

### Mamografia, laudo e filme

| Tecla sugerida | O que faz |
|---|---|
| Shift+T | Pular entre 2D e tomossíntese |
| Shift+B | Contrastada: baixa energia ⇄ recombinada |
| Shift+J | Tomossíntese: próxima espessura (slab) |
| Alt+I | Implante (corrigir a prótese) |
| Alt+Q | Enquadrar a mama no quadro |
| Ctrl+R | Laudo do exame |
| Ctrl+Alt+F | Enviar todos os quadros ao filme |
| Ctrl+Shift+L | Acompanhamento de lesões |

## Respostas da chamada externa

| Resposta | Significa |
|---|---|
| aberto | o exame estava no banco e foi aberto |
| buscando | não estava; foi disparada a busca nos nós |
| ja_no_banco | pedido de retrieve para um exame que já está aqui |
| nao_encontrado | nem no banco nem nos nós (ou não há nó configurado) |
| importando | a chamada trouxe caminhos de arquivo |
| erro | falhou; o motivo está no registro |
| recusado | link ipe:// sem o token, recusado (ou você respondeu "não" à pergunta) |

## Segurança na rede

- **Link `ipe://`**: qualquer página aberta no navegador pode montar um link desses. Com o token da API no link (`…&token=<token>`), ele abre direto; sem o token vale **Rede ▸ Chamada externa ▸ Link ipe:// sem o token**: *Perguntar antes de abrir* (padrão), *Aceitar* ou *Recusar*. Ponha o token no link do RIS para ele não perguntar.
- **Nó DICOM**: o AE Title é só um nome que o aparelho diz ter — qualquer computador da rede pode imitá-lo. Em **Aceitar conexões de**, *Só nós cadastrados, conferindo o IP do nó* só aceita a conexão que vem do endereço cadastrado no nó com aquele AE.
- **Impressora DICOM**: impressora nova aceita *qualquer AE da rede local* (10.x, 172.16–31.x, 192.168.x e VPN 100.64.x) — de fora da rede interna não vem modalidade. As impressoras que você já tinha continuam como estavam; troque em Configurações ▸ Impressão ▸ Servidores.
- **Servidor central**: sem certificado ele usa HTTP, e usuário e senha passam pela rede sem criptografia — use só numa rede interna confiável, ou indique um certificado (.pem). Cinco senhas erradas em 10 minutos bloqueiam aquele computador por 10 minutos.

> **Uma última palavra.** Toda função nova deste programa tem modo manual de reserva, avisa quando não conseguiu e mostra o estado na tela. Quando um número não sai, a resposta é "não deu" — nunca um número grande. O programa devolve número; a interpretação é do médico.

# Sobre o Ipê

## Por que Ipê

Em Brasília, no meio da seca, quando a cidade fica parda e o ar fica seco, os ipês florescem. Amarelos, roxos, brancos — e de repente a paisagem muda. Gosto da ideia de um programa com esse nome: algo que nasce no meio do trabalho árido do dia a dia e deixa a rotina mais leve.

E há uma coincidência que só percebi depois: *ipê* está no meu nome. Fil**ipe**.

## Como ele nasceu

Sou radiologista, dedicado à imagem da mama, e entusiasta de tecnologia. Como muitos radiologistas, migrei para o macOS por causa do OsiriX e do Horos, que por anos foram a melhor estação de trabalho ao alcance de quem lauda. Mas sempre quis um programa completo e robusto que rodasse também no Windows e no Linux, os sistemas da maior parte dos serviços onde trabalhamos.

Durante muito tempo, essa vontade ficou nas ideias: eu sabia o que queria na tela, mas não tinha como transformar isso em programa sozinho. A inteligência artificial mudou isso. Hoje descrevo uma necessidade da prática — "na RM de mama, quero o mapa cinético"; "num quadro vazio, me deixe escolher a série" — e o **Claude**, da Anthropic, trabalha como um programador sênior: escreve o código, testa e explica o que fez. As decisões clínicas, o que entra e como deve funcionar continuam sendo minhas, assim como a conferência nos exames reais.

## Sobre ombros de gigantes

O Ipê só existe porque muita gente compartilhou seu trabalho em código aberto: as bibliotecas de interface (Qt/PySide6), de DICOM (pydicom, pynetdicom, GDCM, pylibjpeg), de cálculo (NumPy) e de inteligência artificial, como o **TotalSegmentator**, além de muitas outras listadas em *Créditos e licenças*. Por isso o Ipê também é aberto (GPL-3.0): para que outros possam usar, estudar, melhorar e devolver.

## O que ele não é

O Ipê é uma ferramenta de pesquisa e ensino. **Não é dispositivo médico registrado** e não se destina a uso diagnóstico.

— Filipe Ramos Barra

## Créditos e licenças

A lista completa do que o Ipê usa — bibliotecas, modelos de IA e ferramentas —, com a licença e o link de cada uma, está em **Ajuda ▸ Sobre o Ipê ▸ Créditos e licenças** e no arquivo CREDITOS.md do repositório. Os autores do TotalSegmentator e do nnU-Net pedem que trabalhos que usam essas ferramentas citem os artigos deles; as citações estão na mesma lista.
