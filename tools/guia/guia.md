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
- **Um Ipê só** (0.99.79): clicar de novo no atalho, ou abrir um link ipe://, não abre outro programa. O que já está aberto vem para a frente, inclusive quando estava escondido na bandeja (fechar para a bandeja) ou ainda no login. Se o programa caiu, o próximo clique abre normalmente.

## Importar exames

Menu **Arquivo**: **Importar pasta…** (Ctrl+I), **Importar arquivos…** e **Importar compactado (ZIP, RAR, 7z)…**. Também dá para arrastar arquivos, pastas ou compactados para cima da janela.

> **Compactados.** ZIP e TAR (.tar, .tar.gz, .tgz, .tar.bz2, .tar.xz) o programa abre sozinho. RAR, 7z, ISO e CAB ele abre com o **7-Zip**, se estiver instalado (7-zip.org), ou com o **tar que já vem no Windows 10/11**; para RAR, o WinRAR instalado também serve. Se nenhum dos dois existir, o programa avisa. Compactado em partes (.part1.rar, .part2.rar…, ou .7z.001, .7z.002…): mande todas as partes, ou só a primeira, com as outras na mesma pasta. Um compactado dentro de outro também é aberto. Arquivo com senha não abre: o programa avisa, e aí é descompactar fora e importar a pasta.

> **Copiar ou referenciar?** Em Configurações ▸ Banco de dados ▸ Importação, a caixa *Copiar os arquivos para o armazenamento do programa* decide se o DICOM é copiado para a pasta do programa ou apenas referenciado onde está. Desmarcada, o programa nunca escreve no arquivo original — e nunca o apaga.

## Onde ficam os dados

Menu **Ajuda ▸ Abrir pasta de dados** mostra onde estão o banco (SQLite), as imagens copiadas (Storage), as configurações (settings.json) e os registros (logs). Pela linha de comando, `ipe-cli info` imprime os mesmos caminhos.

O programa não roda como administrador, e nunca precisa: tudo o que ele escreve fica no perfil do usuário.

### Versão nova pelo GitHub

Ao abrir (uma vez por dia), o Ipê procura no GitHub se saiu versão nova; **Ajuda ▸ Procurar versão nova (GitHub)…** procura na hora, e **Ajuda ▸ Avisar quando sair versão nova** liga e desliga o aviso. Havendo versão nova, a janela mostra o número (e as novidades, em *Mostrar detalhes*) e oferece:

- **Baixar e instalar** (Windows, instalado pelo instalador): baixa o instalador, confere o SHA-256 que o GitHub publica, fecha o programa, instala sem perguntas e abre a versão nova. A pasta do programa, a do banco, o idioma e o modo de uso continuam como estavam.
- **Baixar** (versão portátil do Windows e Linux): baixa o pacote e abre a pasta; trocar a pasta do programa é à mão (o banco e as configurações ficam fora dela).
- **Pular esta versão**: o aviso automático não volta para ela (a procura pelo menu continua mostrando). **Depois**: pergunta de novo no dia seguinte. **Ver a página**: abre o release no navegador.

Os arquivos do release têm nomes em inglês desde a 0.99.81: `Ipe-<versão>-installer.exe`, `Ipe-<versão>-windows-portable.zip` e `Ipe-<versão>-linux-portable.tar.gz`. Desde a 0.99.86 o release não traz mais a cópia com o nome antigo (`-instalador.exe`): quem ainda está numa versão de 0.99.70 a 0.99.80 instala a nova uma vez à mão.

No modo cliente quem decide a versão é o servidor central (Ajuda ▸ Procurar atualização no servidor central…), e o aviso do GitHub não aparece. A consulta manda ao GitHub só o nome do programa e a versão.

### Levar as configurações para outro computador

**Configurações ▸ Sistema ▸ Exportar as configurações…** grava um arquivo `.ipeconfig` com o que você escolher: as configurações deste computador (janela, mouse, impressão, exportação, rede), as suas preferências, os protocolos de exibição e de mamografia, os modelos de laudo e de folha, perfis, SLA e busca ativa, os nós DICOM, as identidades AE, a automação e as traduções próprias. O arquivo é o mesmo no Windows e no Linux: exporte num e importe no outro.

**Configurações ▸ Sistema ▸ Importar configurações…** abre o arquivo, mostra o que ele tem e importa as partes marcadas. O que já existe aqui com o mesmo nome (um nó, uma regra, um protocolo) é atualizado; o resto continua. Antes de importar, as configurações de agora ficam numa cópia, em `backups_config` na pasta de configurações (para voltar, importe a cópia). Depois, feche e abra o programa.

O que **não** vai, porque é de cada computador: os exames e a pasta do banco, os locais, os monitores, o login guardado, o título AE e o token deste computador, o papel de servidor ou cliente e a posição das janelas. Uma pasta do outro sistema (`C:\...` chegando no Linux, `/home/...` chegando no Windows) não é gravada. As **senhas** dos nós DICOM e da IA do laudo só vão se você marcar *Levar as senhas*: nesse caso o arquivo as leva em texto claro, então guarde-o com cuidado. A parte do serviço, os nós e a automação pedem a permissão de configurar o computador.

### Instalar e desinstalar no Windows

O instalador pergunta duas pastas: a **do programa** (sugere `AppData\Local\Programs\Ipe` do usuário; pode ser outro disco, como `D:\Ipe`, mas não Arquivos de Programas, porque ele instala sem administrador) e a **do banco de dados** (sugere a de agora; pode ser outro disco ou um HD externo, mas fora da pasta do programa). Numa atualização as duas já vêm preenchidas com as de antes. Se o banco de agora já tem exames e a pasta escolhida está vazia, o instalador não troca e avisa: para levar os exames, use **Configurações ▸ Banco de dados ▸ Mudar a pasta do banco deste computador…**, que move os arquivos: com **Mover os arquivos**, o banco é movido na próxima vez que o programa abrir, antes de qualquer outra coisa (com o programa aberto o Windows não deixa mexer no banco); se algo falhar, o que já tinha ido volta e nada muda. **Só apontar** passa a usar o banco que já estiver na pasta escolhida. Pela linha de comando: `ipe-cli set-data-dir PASTA`.

Para desinstalar: **Configurações do Windows ▸ Aplicativos ▸ Aplicativos instalados ▸ Ipê ▸ Desinstalar** (ou o Painel de Controle ▸ Programas e Recursos). Sai o programa, com os atalhos e o link ipe://. O banco, os exames, os laudos e as configurações ficam: são seus. Para apagá-los também, apague a pasta do banco e a pasta `AppData\Local\DicomViewer` depois de desinstalar.

### Instalar no Linux

**Pelos pacotes do release (0.100.6)** — no GitHub, a página de releases tem dois jeitos, os dois sem Python:

- **Pacote `.deb`** (Debian, Ubuntu, Mint…): `sudo apt install ./Ipe-<versão>-linux-amd64.deb`. Instala em `/opt/ipe`, com o comando `ipe-viewer`, o ícone e o atalho **Ipê** no menu de aplicativos; o `apt` instala as bibliotecas da janela que faltarem. Atualizar é instalar o `.deb` novo; remover, `sudo apt remove ipe-viewer`.
- **Portátil** (`Ipe-<versão>-linux-portable.tar.gz`, qualquer distribuição): extraia e rode `Ipe/install.sh`. Ele instala para o seu usuário, sem administrador (o programa em `~/.local/share/ipe/programa`, o comando `ipe-viewer` em `~/.local/bin`, o atalho no menu). `install.sh --system` instala para todos os usuários em `/opt/ipe` (pede a senha do `sudo`); `install.sh --uninstall` remove. Também dá para só rodar `Ipe/Ipe`, sem instalar.

O comando se chama `ipe-viewer` porque `ipe` já é o nome de outro programa (um editor de desenhos) nas distribuições. Instalar, atualizar ou remover o programa não mexe nos exames, no banco nem nas configurações (`~/.local/share/DicomViewer` e `~/.config/DicomViewer`).

Pelo código: na pasta do Ipê, `./instalar.sh` e depois `./executar.sh`. Precisa de um Linux com **glibc 2.34 ou mais nova** (Ubuntu 22.04, Debian 12, Fedora 35 ou depois), porque o Qt do Ipê não tem pacote para sistemas mais antigos — o script avisa e para. Ele procura sozinho um **Python 3.10 ou mais novo do sistema** (não o do Anaconda, que costuma vir antes no caminho e ser mais velho), refaz o ambiente `.venv` se ele foi criado com um Python antigo e instala as bibliotecas da janela que o Ubuntu não traz (`libxcb-cursor0` e companhia, com `sudo`). A versão portátil de Linux dispensa o Python, mas também precisa dessas bibliotecas.

## Ajuda

**F1** (fora de um exame), o botão **Ajuda** da tela inicial ou **Ajuda ▸ Guia do usuário (PDF)** abrem este guia no leitor de PDF do computador. **Ajuda ▸ Sobre o Ipê…** mostra a versão. Dentro de um exame o F1 é do filme (capítulo 12).

As figuras deste guia são telas do próprio programa, refeitas a cada versão, com exames reais **anonimizados** (pacientes EXEMPLO, datas deslocadas, sem instituição). Nas telas de outro sistema (Windows ou Linux) a fonte e o desenho das janelas mudam um pouco; os botões e menus são os mesmos.

## O que o programa nunca faz com o original

- Exportar, empacotar, anonimizar e corrigir etiquetas (tags) geram arquivos novos; o original fica intacto.
- A única função que reescreve um arquivo de paciente é a compressão sem perda, e só depois de conferir pixel a pixel que a imagem é idêntica.
- Apagar exame e apagar série removem arquivos, e só os que estão dentro do Storage do programa. Arquivo apenas referenciado não é tocado.
- O que o programa grava *no* exame (captura da lesão, filme no exame, reconstruções salvas) entra como **série nova**; as séries originais não mudam.

# A tela do banco de dados

## Lista de exames

A tabela central lista os exames do local selecionado. Em cima dela: o campo **Buscar**, o botão **Colunas ▾** (escolhe quais colunas aparecem) e **Limpar filtros**. O painel da direita mostra as séries do exame selecionado.

![A tela do banco de dados com os exames de exemplo (anonimizados). À esquerda, os locais e o banco de casos; à direita, as séries e os comentários do exame escolhido.](banco.png)

Botão direito num exame (ou em vários selecionados), arrumado em grupos desde a 0.99.78:

- **Abrir**, **Abrir escolhendo séries…** e **Laudo…** em cima;
- **Organizar ▸** listas de casos, prioridade, subespecialidade, estado do exame, comentário e o banco (pessoal ou compartilhado);
- **Documentos ▸** anexar PDF ou imagem, os documentos do exame e o histórico;
- **Enviar para ▸** um nó ▸ *como este programa* ou *como* uma das identidades cadastradas (capítulo 9), e **Exportar…**;
- **Filme ▸**, só quando o exame tem imagens-chave ou filme salvo;
- **Ferramentas ▸** **Anonimizar uma cópia deste exame…** (exporta anonimizado ou guarda uma cópia anonimizada no banco, capítulo 14), **Corrigir tags…** e, só em mamografia, **Apagar implante**;
- no fim, **Proteger** (ou **Remover proteção**, se já estiver protegido) e **Apagar do banco…**.

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
- **Histórico do exame…** (botão direito no exame ▸ Documentos) mostra quem fez o quê **neste** exame — abriu, baixou, exportou, enviou, imprimiu, mudou de banco, apagou imagem, assumiu o laudo — e quando os laudos foram criados e assinados.

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

![TC de abdome na fase portal, com os órgãos e os segmentos hepáticos da segmentação de IA (TotalSegmentator) sobrepostos.](visualizador_tc_orgaos.png)

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

A ferramenta do botão esquerdo se escolhe na barra, no menu do botão direito do quadro — em **Ferramenta do botão esquerdo ▸ Navegar** (o que move a imagem), **▸ Medir** (o que mede) e **▸ Desenhar** (seta, texto, lápis, pincel) — ou clicando no canto que mostra a ferramenta atual.

![A barra do visualizador. As aplicações (MPR, 3D, composição, Genant…) aparecem no fim da barra só quando servem ao exame aberto.](barra_ferramentas.png)

### O menu do botão direito no quadro (0.99.78)

Arrumado para caber numa olhada:

- **em cima, o que depende do lugar clicado**: a medida debaixo do mouse (apagar, rascunho, lesão, referência, espelhar, clonar, perfil), *Nódulo pulmonar aqui* (TC de tórax), *Achado BI-RADS aqui* e *Achar o implante* (mamografia), *Eixo de simetria* (RM de mama, ou quando há ROI no corte), *Subtração digital (DSA)* (só angiografia, XA/RF), *Numeração da coluna*, *Cardíaco 4D*, salvar a reconstrução do MPR e *Tirar a mesa da TC*;
- **Marcar imagem-chave ★** e **Copiar a imagem**;
- **Imagem ▸** janela (só os presets da modalidade do quadro), cor (as mais usadas da modalidade e *Mais cores ▸* com as outras), inverter, filtro, girar/espelhar, mosaico de cortes, histograma, ajustar à janela e restaurar;
- **Quadro ▸** fundir este quadro sobre outro, linhas de corte, grupo de sincronização, cine e a lista das medidas da série;
- **Anotações ▸**, **Ferramenta do botão esquerdo ▸** e **Informações DICOM (tags)…**;
- no fim, separado, o que apaga: **Apagar medidas deste corte** e **Apagar esta imagem…**.

As aplicações de IA (órgãos, coluna, nódulos…) ficam só nos botões da barra e no botão **Aplicações**. Cada aplicação tem o seu desenho na barra, e as que usam IA levam um ✦ dourado no canto.

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
- **Selo IA (0.100.14)**: a miniatura ganha um selo lilás **IA** no canto de cima quando a série é resultado de uma IA (SEG, tabelas, imagens de conferência) ou foi analisada por uma (a série de onde saiu a SEG). Passe o mouse para ver quais ferramentas. No navegador, o mesmo selo aparece na tira de séries.
- O canto inferior direito do quadro diz o plano (clicável), a fase da dinâmica, a janela e o FOV.
- **Zoom digitado**: duplo clique no "Zoom N%" do canto abre o menu — *Ajustar à janela*, *1 pixel da imagem = 1 pixel da tela (1:1)*, 50 a 400% e **Digitar o zoom…** (aceita `150`, `150%`, `2x`, `1:1` e `2:1`). O número é o mesmo do canto: 100% é a imagem ajustada ao quadro.
- **Cortes não mostrados**: rolando depressa (roda, arrasto, Shift), a imagem anda vários cortes entre duas pinturas da tela e os do meio nunca aparecem. Quando isso acontece, ao lado da barra de posição aparece por um segundo e meio, em âmbar, "N corte(s) não mostrado(s)". Ir a um corte (clique na barra, duplo clique no número da imagem, sincronia) não avisa.

![RM de crânio no protocolo de exibição: quatro séries, com as linhas de referência de um quadro nos outros.](layout_rm_cranio.png)

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
| Sincronia entre referenciais diferentes | âmbar | o quadro está num grupo de sincronia (corrente) com quadros de outro Frame of Reference — outro exame, ou o paciente reposicionado. Eles andam pelo deslocamento de quando foram ligados, não por registro |

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

![O painel Anteriores (à direita) lista os outros exames do paciente; daqui eles vêm para a aba e se ligam ao exame atual.](anteriores.png)

**Alinhar automaticamente com o outro exame** (menu da sincronização) faz o **registro rígido** — rotação e translação em 3D — entre dois exames do mesmo paciente: abra o outro exame num quadro ao lado (botão Anteriores) e deixe ativo o quadro do exame atual.

- A medida de semelhança é escolhida sozinha: **correlação** para a mesma modalidade e a mesma sequência; **informação mútua** para modalidades ou sequências diferentes (TC × RM, T1 × T2, PET × TC). A barra de status diz a rotação, o deslocamento e a qualidade (boa, razoável, fraca).
- Os quadros passam a rolar juntos pelo deslocamento do centro. Quando o outro exame está **girado 1° ou mais**, o programa oferece **gravá-lo no plano deste**: uma série nova no outro exame ("… · registrada em <data>"), com a geometria e o Frame of Reference deste — aí os dois andam juntos corte a corte, e o cursor 3D, as linhas de referência e as ROIs caem no mesmo lugar. Os arquivos originais não mudam.
- O registro (a matriz inteira) fica guardado para os dois exames; ajustar à mão com **Alt+rodinha** volta a valer só a translação.
- Leva de 5 a 15 s em CPU (para sozinho em 90 s com o melhor achado; o botão Cancelar para antes). Rígido quer dizer o mesmo formato: serve bem para crânio, coluna e ossos; mama e abdome deformam entre exames, e o resultado nesses é aproximado.
- **Conferir o registro** (menu da sincronização ▸ *Conferir o registro com o outro exame*): o outro exame vai por cima do quadro ativo, em cinza e com a janela dele, já com a matriz do registro guardado — **Xadrez** (casas alternadas de um e de outro: a borda não pode ter degrau), **Cortina** (a divisa segue o mouse), **Diferença** (o que sobra claro é o que não alinhou) ou **Mistura 50%**. A série já gravada no plano deste exame entra sem a matriz (já está alinhada). *Desligar* tira.
- **Conferido no acervo**: numa RM de crânio 3D real, com rotação e translação conhecidas aplicadas, o registro acertou com erro médio de 0,4 mm (máximo 0,5 mm) em 6 s; duas sequências da mesma sessão (FLAIR e SWAN) deram 0,5° e 1,6 mm.

## Medidas

O botão **Medidas** abre uma janela com tudo o que foi medido no exame: série, imagem, tipo, valor, lesão e texto. Clicar numa linha leva até a imagem com a medida já selecionada. A lista sai do banco, não dos quadros abertos — medida feita semana passada está lá.

![Régua e elipse na TC: a régua dá o comprimento; a elipse, a média ± desvio-padrão, mínimo, máximo e área.](medidas.png)

- A ferramenta **Selecionar** edita o que já existe: clique escolhe, arrastar move, arrastar a ponta redimensiona, Delete apaga.
- **Editar lesão…** (ou duplo clique numa linha de segmentação) reabre a segmentação com o limiar e o mamilo que você usou (capítulo 6).
- As medidas saem para planilha (CSV/Excel) e para DICOM SR.
- **Rascunho**: botão direito na medida ▸ *Rascunho*. A medida fica **tracejada**, na tela e no banco, mas **não sai**: não vai ao SR, ao GSPS, ao laudo, à planilha, ao visualizador exportado nem ao acompanhamento de lesões. Desmarcar faz dela uma medida que vale. Em Configurações ▸ Visualizador ▸ Texto e marcas sobre a imagem, *Medidas novas começam como rascunho* faz toda medida nascer assim (as que viram número; calibração e coluna não).
- **Perfil de intensidade**: botão direito numa régua ou polilinha ▸ *Perfil de intensidade…* mostra o gráfico do valor (HU na TC) ao longo da linha, em mm, com mínimo, máximo e média — a transição de densidade, a parede de uma lesão, o realce de um vaso. O gráfico acompanha a linha quando ela é mexida, e *Copiar valores* leva a tabela para a planilha.
- **Apagar esta imagem…** (botão direito no quadro) tira só aquela imagem do exame — a duplicada, a captura errada. Pede a permissão de apagar, é recusado em exame com cadeado e na última imagem da série, leva junto as medidas e a imagem-chave dela e fica no registro de acesso.

### Régua 3D, incerteza e ROI de referência

- **Régua 3D** (menu Medidas): clique o ponto A num corte e o ponto B em outro corte — ou em outro quadro, como o axial e o sagital. A distância sai em 3D, com as componentes direita-esquerda, ântero-posterior e craniocaudal; nos dois pontos do mesmo corte, o rótulo diz "(2D)". O terceiro clique começa uma régua nova.
- **Cortes grossos**: a régua desenhada numa reconstrução de cortes grossos (o sagital de um axial de 5 mm) avisa quando a direção dela tem pixel de 5 mm — a medida craniocaudal herda esse erro, a ântero-posterior não. Na imagem original, a régua menor que a espessura do corte também avisa.
- **Incerteza** (Configurações ▸ Visualizador ▸ Texto e marcas sobre a imagem): mostra ± o pixel na direção da régua e ± perímetro × pixel ÷ 2 na área da ROI. Desligada de fábrica; os avisos acima aparecem sempre.
- **Clonar a ROI**: botão direito numa ROI ▸ *Clonar esta ROI nos outros quadros*. Cada quadro à vista recebe uma ROI nova **na mesma posição no paciente** (em mm, não no mesmo pixel: série com outra matriz ou outro FOV recebe a ROI do tamanho certo), no corte mais perto do centro dela, com a média, o desvio e a área da imagem de lá — T2 → ADC, pré → pós, atual → anterior. No mesmo exame vale o Frame of Reference; entre exames diferentes, ligue antes os quadros num grupo de sincronia (ou registre): sem referencial comum, a barra de status diz que não copiou e por quê. Também não copia para plano não paralelo nem para série que não cobre aquele ponto.
- **Eixo de simetria à mão** (0.99.61): quando o meio do corpo achado sozinho não serve (paciente rodado, mama muito assimétrica), botão direito no lugar do eixo ▸ *Eixo de simetria (ROI espelhada)* ▸ *Marcar o eixo aqui*. Vale para a série, neste computador, aparece como uma linha tracejada azul no axial e no coronal, e *Voltar ao eixo automático* desfaz.
- **ROI espelhada**: botão direito numa ROI ▸ *Espelhar no outro lado (razão lesão / contralateral)*. A ROI nova ("Contralateral") vai para o espelho no plano sagital mediano: num axial ou coronal, o meio do corpo naquela imagem; numa série sagital (RM de mama bilateral), o meio da faixa de cortes — e o quadro vai ao corte do outro lado. A ROI original passa a mostrar *lesão / contralateral* (a média dela sobre a do outro lado), em qualquer mapa: ADC, realce, BPE. A barra de status diz onde ficou o eixo. Plano oblíquo, série que não cobre o outro lado e imagem colorida não espelham, e a barra diz por quê.
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

## Mosaico de cortes no quadro

Botão direito no quadro ▸ **Imagem ▸ Mosaico de cortes** ▸ 2 × 2, 3 × 3 ou 4 × 4 (ou o atalho *Mosaico de cortes no quadro*, que anda pelos tamanhos): o quadro mostra cortes **seguidos** da mesma série, a partir do atual (o primeiro, em cima à esquerda, tem o número em amarelo). Serve para passar os olhos numa série volumétrica sem rolar corte a corte, com outro quadro ao lado rolando normal.

- A rodinha **vira a página**: o conjunto anda junto (4, 9 ou 16 cortes); os quadros sincronizados acompanham pelo primeiro.
- Janela/nível, inverter e a tabela de cores valem para todas as imagens do mosaico. As imagens-chave aparecem com ★.
- O mosaico é **só para ver**: as ferramentas de medida não agem nele. **Duplo clique** numa imagem volta ao quadro normal **naquela** imagem.

## Imagens-chave

K (sugestão) marca e desmarca a imagem do quadro como imagem-chave; Shift+K mostra só as marcadas. Elas entram no laudo em PDF e no filme com um clique.

**Gravar no exame (KO + GSPS).** Botão **Chave** ▸ *Gravar imagens-chave e anotações no exame*: as imagens-chave viram um objeto DICOM **KO** (Key Object Selection, "Of Interest") e as medidas, setas e textos viram um **GSPS** (estado de apresentação), com o número de cada medida escrito ao lado — calculado com a mesma escala da tela (calibração à mão, região do ultrassom, tag). Os dois ficam no exame, vão ao PACS junto com ele e abrem em outros visualizadores (Weasis, OHIF, a estação do aparelho). Medida **rascunho** fica de fora.

- **KO que chega no exame** (de outro sistema, ou o nosso de volta do PACS) marca as imagens-chave aqui, uma vez: desmarcar depois não as traz de volta.
- **GSPS de outros sistemas**: com mais de um no mesmo exame, aparece só o mais recente; os outros ficam no botão CAD/IA, desligados. O nosso GSPS, ao reabrir, fica desligado — as medidas já estão no banco e seriam desenhadas duas vezes.
- **Trazer as medidas para editar**: no botão CAD/IA, um SR ou GSPS de outro sistema tem *Trazer as medidas para editar* — régua, polilinha, polígono, ponto e texto viram medidas do Ipê (editáveis, no painel de medidas, no laudo). O objeto original fica desligado.

## Reconstruções: MPR, oblíquo, curvo e 3D

- **MPR** monta o volume e abre os três planos. Também dá para reconstruir só o quadro ativo em axial, coronal ou sagital.
- A linha de orientação no canto do quadro é clicável: escolhe o plano, e **Oblíquo** vira o quadro oblíquo sem mudar a imagem — a partir dali a ferramenta **Girar plano** inclina.
- Espessura (slab) na barra do MPR, com média, MIP ou MinIP.
- MPR curvo (clique os pontos ao longo de um vaso) e 3D (renderização de volume, com cortes, escultura e exportação de malha STL/GLB/3MF).
- **Estruturas no 3D** (0.99.82): com o 3D aberto, o botão **Estruturas** da barra do 3D (ou o botão direito ▸ *Estruturas segmentadas*) mostra como superfícies coloridas tudo o que está segmentado no exame e ligado: órgãos da IA, segmentos e lesões do fígado, nódulos, lesões segmentadas à mão, níveis linfonodais, SEG e RTSTRUCT de outros sistemas. As estruturas acompanham o giro, o corte, o plano e a escultura do volume; o que está atrás do osso do VR aparece apagado. Desligar um objeto na lista de CAD/IA tira ele do 3D na próxima vez que ligar.
- O plano reconstruído sai sempre na convenção de leitura — axial com anterior em cima e esquerda do paciente à direita — mesmo quando a aquisição foi sagital.
- **Tirar a mesa da TC**: botão direito no MPR ou no 3D de uma TC ▸ *Tirar a mesa da TC (MPR e 3D)*. O programa acha o corpo (o que passa pelo meio do volume) e apaga o que está fora dele, corte a corte — a mesa sai, os pulmões e as vias aéreas ficam. Vale para os volumes montados dali em diante (feche e abra o MPR/3D); a série original não muda.

![MPR nos três planos, com o cursor 3D e as estruturas da segmentação também nos planos reformatados.](mpr.png)

![3D no próprio quadro: MIP do PET de corpo inteiro (o modo, o preset, a opacidade e as vistas ficam na barra de cima).](3d_mip_pet.png)

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
3. Marque **Ativo**. As outras três caixas são de apresentação: *Parede torácica voltada para o centro* (espelha a imagem quando precisa, para as duas mamas se olharem), *Encostar a imagem na borda da parede torácica* e *Zoom por quadrante em todos os quadros juntos*. **Alinhar na vertical:** (0.99.61) — *pelo mamilo* (de fábrica: na mesma linha da tela, o mamilo das duas mamas fica na mesma altura) ou *pelo meio da mama* (como era antes). **Duplo clique** numa incidência mostra só ela (1×1) e a reenquadra para o quadro grande, sem o alinhamento com a outra mama; outro duplo clique volta à etapa.
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
| Outro exame (0.99.61) | US, RM, RM:texto | o quadro mostra a **última ultrassonografia** ou a **última RM** do paciente (até a data do exame, as da mama primeiro); na RM, a subtração ou o pós-contraste, ou a série cuja descrição tem o texto depois dos dois-pontos (`RM:T2`) |

No campo **Em texto:**, colunas se separam por `x` e linhas por vírgula:

```
1 × 2   CCD x CCE
2 × 2   CCD, MLOD x CCE, MLOE
2 × 2   CCD, CCD ant x CCE, CCE ant     (atual acima, anterior abaixo)
1 × 2   CCD tomo x CCE tomo             (tomossíntese)
1 × 2   CCD rec x CCE rec               (contrastada, recombinada)
2 × 2   CCD, US x CCE, RM               (mamografia com a última US e a última RM)
```

Código que o programa não reconhece é recusado na hora, com a mensagem "Código(s) não reconhecido(s): …". Na tela do exame, um quadro sem definição mostra *(quadro vazio no protocolo)*, e uma imagem que não existe mostra "… não encontrada (sem exame anterior)" — em vez de ficar preto sem explicação.

## Repartir a etapa entre monitores

Dentro da etapa: *Nesta etapa, com [1 a 4 telas] mostrar no [Monitor N]*. Você define, para cada número de telas, o que vai em cada monitor. O botão **Repartir sozinho** desfaz isso e devolve a etapa à repartição automática.

Sem arranjo definido, a repartição automática segue esta ordem: se as linhas dividem pelo número de telas, cada tela leva um bloco de linhas (duas linhas em duas telas = CC numa, MLO na outra); senão tenta pelas colunas; senão distribui os quadros em ordem. Com menos imagens que telas, cada tela recebe uma.

## Usar no exame

Com a mamografia aberta, a barra **Mamografia:** traz o combo do protocolo, o combo **etapa:**, e ◀ / ▶ para andar. As teclas de fábrica são **→** (próxima etapa), **←** (etapa anterior) e **Q** (zoom por quadrante). Ainda na barra:

![Mamografia no protocolo de 4 incidências (CC e MLO, direita e esquerda), com cada mama encostada na borda de fora do quadro.](mamografia.png)

![O mesmo exame com a tomossíntese ligada no primeiro quadro: o mostrador embaixo à esquerda indica o corte e a profundidade.](mamografia_tomo.png)

- **Quadrante ↻** (Q) e **1:1** — leitura em tamanho real;
- **Lupa** — segure o botão; a roda muda o aumento;
- **Espessura: fina ▾** — slab da tomossíntese: 1, 5, 10 ou 20 cortes, em MIP ou média;
- **BE ⇄ Recomb.** — alterna baixa energia e recombinada na contrastada;
- **Implante** — corrige a prótese em todos os quadros (Alt+I); veja abaixo;
- **Densidade…** — mede a densidade mamária do que está nos quadros (capítulo 6);
- **2D ⇄ tomo** pula entre a 2D e a tomossíntese na mesma lista;
- **Mama no quadro** reenquadra a mama (veja abaixo);
- **Zoom e pan** (0.99.61, o mesmo botão de sincronia da barra principal) — ligado, zoom e pan num quadro mostram o mesmo lugar nas outras mamas, espelhado;
- **Inverter só a mama** (0.99.61) — inverte o tecido e deixa o fundo preto, em todos os quadros e nas etapas seguintes;
- **Achados…** (0.99.64) — botão direito na imagem ▸ **Achado BI-RADS aqui** ▸ *Novo achado* põe a marca "A1" e guarda a distância ao mamilo; na outra incidência, *A1* marca o mesmo achado. A tabela mostra, para cada achado, a mama, as vistas, a distância do mamilo (média das duas) e a localização — quadrante (ou união, região central, retroareolar), hora do relógio olhando a paciente de frente e terço (anterior, médio, posterior). Na CC, o lado lateral é o de cima (ou o que o PatientOrientation diz); na MLO, o superior. Escolha o tipo e **Mandar ao laudo BI-RADS** — os achados entram no painel BI-RADS do laudo, para completar descrição, tamanho e categoria; mandar de novo troca os mesmos achados, não duplica;
- **★ Corte** (0.99.61) — marca o corte da tomossíntese (ou a imagem 2D) do quadro ativo como imagem-chave; a barra de status diz qual corte e a espessura. Em Atalhos ▸ Mamografia há *ir ao próximo / anterior corte marcado*, para voltar às estrelas numa tomo de dezenas de cortes;
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

### Estado salvo da análise

Ao fechar o exame (pelo X da aba, ao trocar de exame ou ao sair do programa), o Ipê guarda **como ele estava**, para cada usuário: o layout, o que estava em cada quadro — a série, de qual exame, o corte, a fase e a vista (janela, zoom, pan, inversão, cores, giro, espelhos e filtro) —, o quadro ativo, a ferramenta do botão esquerdo, os anteriores trazidos para a aba (que voltam ligados pelo alinhamento salvo) e os painéis de Medidas e Lesões. Na reabertura, o exame volta assim, e a barra de status diz de quando é o estado. A dinâmica e o MPR não se refazem sozinhos — a conta pode demorar —: **Exibir ▸ Estado da análise ▸ Religar a dinâmica como estava** abre a janela da dinâmica com as mesmas fases e parâmetros, e o MPR religa no botão.

**Exibir ▸ Estado da análise** também tem:
- **Reabrir como deixei** — refaz o estado a qualquer momento;
- **Voltar ao arranjo de fábrica** — esquece o estado deste exame (e não guarda ao fechar desta vez);
- **Usar a montagem do exame anterior** — num controle: o layout e as vistas do exame anterior do paciente, cada quadro com a série equivalente deste exame (mesma modalidade e descrição);
- **Abrir o anterior ao lado, como estava** — o anterior entra na aba com os quadros dele como você deixou, ao lado dos deste exame.

**Retomar a sessão depois de uma queda (0.100.8).** Enquanto o Ipê está aberto, ele anota quais exames estão abertos e guarda o estado da análise de cada um **a cada 2 minutos**, e não só ao fechar. Se o programa (ou o computador) cair, na próxima abertura ele mostra os exames que estavam abertos e pergunta se reabre: **Reabrir** abre cada um como estava da última vez que o estado foi guardado (layout, cortes, medidas, painéis), com o que estava na frente de novo na frente. Fechar o programa direito apaga a anotação. Em **Configurações ▸ Visualizador ▸ Estado da análise ao abrir…**, **Depois de uma queda, os exames que estavam abertos**: perguntar (de fábrica), reabrir sem perguntar ou não reabrir.

**Configurações ▸ Visualizador ▸ Estado da análise ao abrir…**: reabrir como deixei (de fábrica), perguntar ou abrir como de fábrica. O estado fica só no Ipê — no banco deste computador ou, no modo cliente, no servidor central, para todas as estações —, não vai junto com o exame. Não vale quando o exame abre com séries escolhidas, por um protocolo com etapas, repartido entre monitores, no modo mamografia ou em reunião: aí quem manda é o protocolo.

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

![RM de mama: T2 e as fases da dinâmica lado a lado, sincronizadas.](rm_mama.png)

![A janela da dinâmica: as fases detectadas, o pré-contraste, as fases do SER e os parâmetros do mapa cinético.](dinamica_fases.png){70}

### Abrir a dinâmica

Botão **Dinâmica** na barra. A janela de parâmetros mostra as séries que ele reconheceu como fases e deixa escolher:

| Campo | O que é |
|---|---|
| Pré, inicial e tardia | quais fases são a pré-contraste, a de pico e a tardia |
| Realce mínimo (%) | abaixo disso o voxel não entra no mapa cinético |
| Rápido (%) / Tardio (±%) | os limiares das seis classes: médio 50–100%, rápido acima; persistente / platô / washout pela variação da tardia |
| Sinal mínimo do tecido (%) | máscara: pré-contraste de pelo menos N% do sinal de referência |
| Corrigir movimento | registro por translação 3D entre as fases |
| Incluir rotação | registro rígido (rotação + translação) de cada fase sobre a pré, mais lento (até uns 40 s por fase); só reamostra em 3D a fase que girou 0,75° ou mais — nas RM de mama do acervo a rotação entre as fases não passou de 0,5°, e aí fica a translação |
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
| Chegada (BAT) | o tempo (s) até o realce do voxel chegar a 10% do pico dele, interpolado entre as fases |
| Lavagem | a maior inclinação de **descida** depois do pico (unidade do MSI); 0 quando a curva não desce |
| iAUC90 | a área sob a curva de realce nos primeiros 90 s (unidade do PEI) |
| Tempo médio (MRT) | o tempo médio do realce, ∫t·realce / ∫realce (s) |

Os quatro últimos (0.99.48) também saem por curva, nas colunas BAT, Lavagem, iAUC90 e MRT da tabela e em *Copiar valores*.

**Mapas em cor** (0.99.64, como o ColorViz/AngioViz): *Tempo em cor* pinta cada voxel que realça pela hora do pico — vermelho cedo, amarelo e verde no meio, azul tarde — com o brilho pelo realce máximo (o percentil 99 do tecido que realça vale brilho cheio, igual em todos os cortes); mostra a ordem de chegada, que o mapa cinético de 6 cores não mostra. *Fases em cor* põe o realce da fase inicial no vermelho, o da intermediária no verde e o da tardia no azul: o que lava fica avermelhado, o persistente azulado. Fora do tecido que realça (o limiar dos mapas), preto. São imagens coloridas: salvam como série, mas não reformatam nem entram nas contas por ROI.

**Fases fora da conta e linha de base** (botão *Parâmetros…*). Em *Fases fora da conta (movimento)* escreva o número da fase que mexeu (por exemplo `4`, ou `4, 7`): ela sai dos mapas e das contas das curvas, e o resto é recalculado com os tempos de verdade. Não podem sair a fase inicial, a tardia, todas as pré, nem duas fases seguidas (a curva perderia o trecho inteiro). No gráfico a fase continua desenhada, marcada "fora"; na lista das vistas ela aparece "(fora da conta)", e o título do painel e a linha de resumo dizem quais saíram. *Linha de base: média de todas as fases até a pré-contraste escolhida* usa a média das fases pré como linha de base — com duas pré ou mais, menos ruído. Com uma fase pré só, o painel avisa.

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

> **Até onde esse número vale hoje.** A máscara corta na parede torácica, mas mantém pele, vasos e músculo peitoral. Então o número serve para comparar a mesma paciente e o mesmo serviço ao longo do tempo — não para virar categoria no laudo nem para comparar com número publicado. O realce medido só no tecido fibroglandular está no botão seguinte.

### Fibroglandular e realce de fundo

Botão **Fibroglandular e realce…** no painel da dinâmica. O programa separa, na mama, o **tecido fibroglandular** (FGT) da gordura e mede quanto ele **realça** na primeira fase pós-contraste.

- **Onde separa**: no **T1 sem saturação** do exame (o "A T1", "Axi T1" ou "Ax T1 FSE"), que é onde gordura e glândula mais se distinguem; sem ele, no **Dixon** (o par FAT:/WATER:, pela fração de gordura); sem os dois, na **pré-contraste da dinâmica**, com o aviso de que o número é menos confiável.
- **Como**: tira a pele (3 mm), corrige o degradê da bobina usando a gordura como referência e separa com um limiar automático (Otsu) em cada mama. Tira também o **músculo** (o escuro encostado na parede torácica, até 25 mm dela) e a parede lateral do tórax (o que fica atrás do ponto mais anterior do pulmão). Um **implante** (bloco escuro, liso e grosso) sai da conta, com aviso.
- **O resultado**: em cada mama, a porcentagem e o volume do FGT; e, com a dinâmica aberta, a **mediana do realce** do FGT e quanto dele realça mais de 20%. A máscara é levada para a grade da dinâmica pela posição no paciente, então a dinâmica pode ter outra resolução.
- **Copiar frases** leva duas frases prontas para o laudo; **Gravar a máscara (SEG)** grava a mama e o FGT como uma série de segmentação (*Mama e fibroglandular · Ipê*), para conferir por cima das imagens.

> **O programa devolve número, não categoria.** A porcentagem em volume sai bem abaixo da impressão visual (um exame laudado como "esparsas" mediu 10%), e o realce medido voxel a voxel ainda não foi aferido contra laudos. A categoria de quantidade (a–d) e a de realce de fundo (mínimo a acentuado) ficam com o médico; o número serve para acompanhar a mesma paciente e para ver assimetria entre as mamas.

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

### Perfis de ocultação

A seta do botão **Ocultar** (no visualizador) escolhe **o que** fica escondido. A escolha vale para todas as abas e para a lista do banco (botão Ocultar da tela inicial); a reunião usa sempre *Ocultar tudo*, com o nome do caso.

| Perfil | Nome | ID | Nascimento | Sexo e idade | Data do exame | Instituição, acesso, médico | Aparelho |
|---|---|---|---|---|---|---|---|
| **Ocultar tudo** (o de sempre) | "Paciente oculto" | — | — | — | — | — | aparece |
| **Tela** | pseudônimo | pseudônimo | — | aparecem | aparece | — | aparece |
| **Ensino** | pseudônimo | — | — | aparecem | **deslocada** | — | aparece |
| **Publicação** | "Paciente" | — | — | aparecem | — | — | — |

- **Pseudônimo**: `PACIENTE-` e seis caracteres, o mesmo para o mesmo paciente enquanto o programa está aberto (o atual e o anterior do mesmo paciente têm o mesmo pseudônimo); não é gravado em lugar nenhum.
- **Data deslocada**: todas as datas do mesmo paciente andam para trás o mesmo número de dias (30 a 329, sorteado por paciente) — a data real some, o intervalo entre os exames fica.
- O canto do quadro mostra o perfil em uso (um cadeado e **Ensino**, por exemplo), e o título da aba também.
- **Ocultar na tela não muda os arquivos.** Para levar o exame, use Exportar: com a tela oculta a exportação sai anonimizada, e no perfil Ensino a opção **Deslocar as datas** já vem marcada (o mesmo deslocamento da tela).

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

Registre o link uma vez em cada computador: **Rede ▸ Registrar link ipe:// neste computador**, ou `ipe-cli register-url`. O registro é no perfil do usuário e grava o caminho do executável: se o programa mudar de lugar, registre de novo. No **macOS** não precisa registrar: `ipe://` e `dicomviewer://` são do próprio aplicativo, e o link abre o Ipê (ou vai para o que já está aberto).

**Apelidos do link** (0.100.32). Se o RIS já tem o botão de outro visualizador, o Ipê pode atender pelo nome dele: em **Rede ▸ Chamada externa ▸ Apelidos do link**, escreva os nomes separados por vírgula (por exemplo `osirix, horos`). Ao salvar, o Ipê se registra no sistema para esses nomes. O apelido aceita o formato do Ipê (`osirix://open?accession=123`) e o do OsiriX/Horos:

```
osirix://?methodName=displayStudy&StudyInstanceUID=1.2.840...
osirix://?methodName=displayStudy&PatientID=12345
osirix://?methodName=displayStudy&AccessionNumber=123456
```

Só abrir e buscar são aceitos; `downloadURL` (baixar de um endereço qualquer) é recusado. Valem as mesmas regras do `ipe://`: com o token abre direto, sem o token vale a escolha *Link ipe:// sem o token*. Se o programa de verdade (o OsiriX) também está instalado, é o sistema que decide quem atende; o Ipê pede para ser o padrão ao registrar. No macOS cada apelido vira um aplicativo mínimo em `~/Applications/Ipe links`, que só repassa o link ao Ipê; tirar o apelido da lista apaga esse aplicativo.

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

![Configurações ▸ Rede ▸ Nós DICOM, aba Este computador: o nó DICOM e a chamada externa.](config_rede.png){75}

### Dois tipos de nó: DIMSE e DICOMweb

No cadastro de um nó, o primeiro campo é **Tipo de conexão**, e ele muda os campos seguintes:

| | DICOM clássico (DIMSE) | DICOMweb (HTTP) |
|---|---|---|
| Como fala | C-FIND, C-GET / C-MOVE, C-STORE | QIDO-RS, WADO-RS, STOW-RS |
| Identificação | AE title dos dois lados | usuário e senha, OAuth2 / OIDC ou token |
| Precisa de porta aberta aqui? | só com C-MOVE | não |
| Atravessa firewall e proxy? | difícil | sim, é HTTP |

O endereço do DICOMweb é a base, a que costuma terminar em `/dicom-web` (por exemplo `http://192.168.1.216:8042/dicom-web`). **Testar rede** funciona nos dois.

> **Três coisas sobre o DICOMweb.** Não existe C-MOVE ali: o download volta pela mesma conexão. Identidade de AE não vale num nó DICOMweb — quem identifica é o login. E a senha, o token e o segredo do cliente ficam **cifrados** neste computador (no Windows pela proteção do próprio sistema; nos outros, por uma chave local da pasta de configuração): o banco copiado para outro computador não abre as senhas — lá, digite de novo. Senhas gravadas antes da 0.99.55 são cifradas na primeira vez que o programa as lê. Use um usuário só de leitura quando o PACS permitir.

**Autenticação** do nó DICOMweb:

| Opção | Quando usar | Campos |
|---|---|---|
| Usuário e senha (Basic) | Orthanc, dcm4chee sem login central | usuário e senha |
| OAuth2 — credenciais do cliente | PACS na nuvem, integração entre sistemas | token / emissor, ID e segredo do cliente, escopo |
| OAuth2 — usuário e senha (Keycloak) | dcm4chee-arc ou Orthanc com Keycloak, cada médico com seu login | token / emissor, ID (e segredo) do cliente, escopo, usuário e senha |
| Token fixo (Bearer) | o PACS entregou um token pronto | o token, no campo Senha / token |

Em **Token / emissor** vai o *token endpoint* (termina em `/token`) ou só o endereço do **emissor OIDC** (no Keycloak, `https://login.exemplo/realms/pacs`): o programa lê `/.well-known/openid-configuration` e acha o endpoint sozinho. O token fica na memória até perto de vencer e é renovado sem pedir a senha de novo; se o PACS recusar (401), o programa pede outro uma vez. **Testar rede** já faz o login.

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

![Configurações ▸ Rede ▸ Servidor central: o modo deste computador (local, servidor ou cliente).](config_servidor_central.png){65}

**Abrir enquanto baixa.** No cliente, o exame que ainda não está no computador abre em poucos segundos: primeiro chega uma imagem de cada série (a tira mostra todas e o protocolo de exibição monta os quadros), depois o resto de cada série vai chegando e os quadros crescem sozinhos. A barra de status mostra *Baixando do servidor central: N de M imagem(ns) (P%)…*. Só o exame aberto (e o anterior que o protocolo pede para comparar) é baixado. Reabrir um exame que já chegou é imediato; o cache tem o limite de **Configurações ▸ Rede ▸ Servidor central**, e os exames abertos há mais tempo saem primeiro.

**Quanto já chegou de cada série (0.100.0).** Enquanto o exame baixa, a miniatura de cada série na tira mostra *34/120 im* com uma barra embaixo: azul e com ⬇ na que está chegando agora, verde nas que esperam a vez (passe o mouse: a posição na fila). O quadro mostra **⬇ 34/120** embaixo do número da imagem até a série dele terminar. **Pôr uma série num quadro** (clicar ou arrastar) passa ela para a frente da fila. Duas séries baixam ao mesmo tempo, e o que chega entra no banco sem parar a rede. Se alguma série não baixar inteira, a barra de status diz quantas imagens faltaram e por quê; e o servidor guarda no registro de acesso (ações *cliente_entrou* e *cliente_download*) a versão de cada cliente e o que cada download fez (0.100.1).

**Sinal da rede (0.100.1).** No cliente, a barra de status mostra a rede até o servidor: **barras** de 0 a 4 (como as do celular), a **ida e volta** em milissegundos e a **vazão** em Mbit/s — por exemplo *3 ms · 870 Mbit/s*. Vale o pior dos dois: quatro barras pedem menos de 10 ms e 300 Mbit/s ou mais; três, menos de 30 ms e 80 Mbit/s; duas, menos de 80 ms e 20 Mbit/s. O programa mede ao abrir (com um teste de 2 MB) e a cada exame aberto (só a ida e volta, para não disputar a rede com o download; a vazão passa a ser a do próprio download). Clique nas barras para medir de novo; *sem conexão*, em vermelho, quando o servidor não responde.

**Menos dados na rede (HTJ2K).** O cliente recebe as imagens comprimidas **sem perda** em HTJ2K (2 a 4 vezes menos dados numa TC; a mesma imagem, conferida pixel a pixel). O acervo do servidor **não muda** — o que vai é uma cópia de envio, que o servidor prepara em segundo plano para os exames dos últimos 14 dias (de 30 em 30 minutos, quando ninguém está pedindo imagens) e guarda na pasta `CacheWeb`, ao lado do acervo (que pode ser apagada à vontade). Imagem que ainda não tem a cópia pronta vai como está, sem esperar. Desligue em **Configurações ▸ Rede ▸ Servidor central ▸ Receber as imagens comprimidas sem perda**. Mandar uma dessas imagens a um nó DICOM que não aceita HTJ2K vai descomprimido.

### Visualizador web (0.99.91)

O servidor central traz um **visualizador no navegador**: em qualquer computador da rede, abra **`http://IP-do-servidor:8043/web/`** (ou `https://…`, com o certificado do Ipê) no Chrome ou no Edge e entre com o mesmo usuário e senha do Ipê. Não precisa instalar nada. O endereço aparece em Configurações ▸ Rede ▸ Servidor central, com o link.

Nesta primeira fase:

- **Lista de exames** com busca por nome, ID ou acesso, por datas e por modalidade; cada um vê só o que pode ver no Ipê (as mesmas permissões e o banco pessoal). Duplo clique abre o exame.
- **Tira de séries** com as miniaturas; clicar põe a série no quadro ativo (contorno amarelo), ou **arraste a miniatura até o quadro** que quiser (0.99.95).
- **Imagens disponíveis** (0.99.95): assim que o exame abre, o navegador baixa as séries em segundo plano — primeiro as que estão nos quadros, depois as outras, na ordem da tira. Cada miniatura mostra a porcentagem e uma barrinha até ficar pronta, e o alto da tela mostra o total do exame; com 100%, somem. Se a memória do navegador encher (exames muito grandes), a pré-carga para e o resto vem quando for mostrado.
- **Carga mais rápida** (0.99.96):
  - **Menos bytes na rede**: o servidor manda cada imagem sem compressão (e a mamografia em JPEG-LS) como **HTJ2K sem perda**. É uma cópia de envio, conferida pixel a pixel e guardada numa pasta de cache (`CacheWeb`, ao lado do acervo, que pode ser apagada à vontade); o arquivo do acervo não muda. Numa TC, vai de 2 a 5 vezes menos.
  - **Carga progressiva**: a imagem grande aparece primeiro numa versão menor e vai ganhando definição enquanto chega. O volume (MPR) vem intercalado: 1 a cada 4 cortes primeiro, e se completa em seguida.
  - **Cache do navegador**: reabrir um exame só confere com o servidor se a imagem mudou (a senha continua valendo); quase nada passa pela rede.
  - A decodificação usa todos os núcleos do computador menos um, e os metadados da série vão comprimidos.
  - **Todas as séries começam logo** (0.99.99): o navegador pede as informações de todas as séries de uma vez (não uma depois da outra), o servidor lê os cabeçalhos em paralelo e já prepara o exame inteiro assim que ele abre; a série seguinte não espera mais a anterior. As cópias de envio feitas em segundo plano esperam enquanto o navegador está pedindo imagens, para não disputar o processador com elas.
  - **Carga** (barra): mostra quantas imagens e quantos MB vieram pela rede, em quanto tempo (MB/s), quanto o navegador levou para decodificar cada uma, em que formato vieram e quantas vieram do cache. Serve para saber se o que pesa é a rede ou o computador.
- **Quadros** de 1×1 até 4×4 (ícone de layout: passe o mouse na grade e clique) e protocolos prontos (MPR, PET/CT). **Janelas prontas** (as suas, por modalidade) na aba **Imagem** e no menu do botão direito.
- **Formatos**: HTJ2K (a cópia de envio), JPEG-LS, JPEG 2000 e JPEG são decodificados no próprio navegador; o que está em outros formatos (cor, JPEG 2000 guardado) vai como está no banco. A mamografia usa a janela do aparelho (inclusive a sigmoide).
- **Segurança**: nada do paciente fica gravado no navegador; recarregar a página pede o login de novo e a sessão parada se encerra sozinha. Cada exame aberto fica no registro de acesso ("abriu no navegador"). Na rede interna, use HTTPS com o certificado do Ipê.

**A tela (0.99.97), no estilo do Weasis.**

- **Uma barra de ícones** (passe o mouse para ver o nome). Os ícones com setinha abrem um menu: as ROIs (elíptica, retangular, livre) e os ângulos (ângulo, Cobb) mostram a ferramenta escolhida; clique na setinha para trocar.
- **Cada botão do mouse com a sua função, como no Ipê**: clique no ícone da função **com o botão do mouse que deve fazê-la** — com o esquerdo, ela vai para o esquerdo; com o do meio, para o do meio; com o direito, para o direito. A marca amarela embaixo do ícone mostra qual: à esquerda, no meio ou à direita (uma função pode estar em dois botões). O rodapé resume as três, e a escolha fica gravada no navegador. A roda continua passando os cortes.
- **Botão direito**: **clicar e segurar** (arrastando) faz a função dele — por padrão, o zoom; **clicar e soltar** abre o **menu da imagem**: Janela (as prontas, a do arquivo, inverter), Zoom (ajustar, 1:1, 2×), Girar e espelhar, Plano (Original, A, C, S, MIP), Funções dos botões, Série, Quadros e cine, Apagar medidas da imagem e Restaurar. Em cima de uma medida, o menu começa por ela: copiar o valor, editar o texto (seta) e apagar.
- **Painel da esquerda**: as séries (com a porcentagem baixada) e os **exames anteriores** do paciente (clique para abrir). **Painel da direita**, em abas: **Imagem** (janelas prontas, inverter, girar, espelhar, zoom), **Medidas** (todas as do exame com o valor e quem mediu; clique para ir à imagem; copiar e apagar), **DICOM** (as tags da imagem do quadro ativo, com filtro) e **PET** (SUV, cor, opacidade, topo da janela e segmentações). Os dois painéis recolhem (a seta no alto) e abrem de novo pela tira fina que fica no lugar.
- **Rodapé**: imagens disponíveis, velocidade da rede e decodificação, **Carga** (o painel completo) e a função de cada botão.
- **Medidas em dois cliques (0.100.3)**: a régua e as outras medidas também desenham em "clique, move, clique". Uma linha começada e não terminada é desfeita ao clicar noutro quadro, trocar de ferramenta ou apertar **Esc** — o mouse nunca fica preso.
- **Duplo clique amplia (0.100.5)**: duplo clique num quadro leva-o para 1×1; outro duplo clique volta ao arranjo de antes, com cada quadro como estava (corte, zoom, janela). Um duplo clique sobre uma medida continua sendo da medida.
- **Lista com filtros rápidos e prévia (0.100.20)**: acima da lista, três linhas de botões — **Período** (Hoje, Ontem, 7 dias, 30 dias, Tudo, Outro período…), **Modalidade** e **Situação** (Sem laudo, Rascunho, Assinado, Com IA para revisar) — filtram com um clique e ficam lembrados. Ao lado do nome, o selo **IA** (mais forte quando há achados esperando revisão) e o do laudo (**R** rascunho, **L** assinado). **Um clique** num exame mostra a **prévia** à direita: as séries (com o selo IA), a IA do exame e os achados por estado, o laudo (estado, data e o começo do texto) e os exames anteriores do paciente, com o botão **Abrir o exame**; as setas ↑↓ andam pela lista. **Dois cliques** (ou Enter) abrem, como antes.
- **Janelas ligadas (0.100.20)**: nas janelas de visualização, o ícone de corrente **Ligar as janelas** (ligado de início) faz a rolagem, a janela/nível e o zoom de uma janela seguirem nas outras: no mesmo exame, pela posição no paciente (quadros no mesmo plano); na janela do **exame anterior**, andando os mesmos milímetros — desligue, alinhe os dois exames e ligue de novo. **Desde a 0.100.21**, com as janelas ligadas, o corte que você rola numa janela aparece nas outras como uma **linha de referência tracejada azul-clara** (nos quadros de outro plano do mesmo exame — por exemplo, o axial de uma janela sobre o sagital ou o localizador da outra); e dá para **arrastar uma série da tira de uma janela e soltá-la num quadro de outra janela**, mesmo de outro exame (a janela de comparação).
- **Aparência do visualizador (0.100.19)**: o ícone **Aparência** (fim da barra) escolhe onde ficam as **séries** (à esquerda, embaixo ou em cima — nas duas últimas, uma faixa que rola de lado e deixa a largura toda para as imagens) e os **botões** (em cima, ou numa coluna à esquerda, que devolve a altura da barra à imagem). **Modo leitura** (o ícone ao lado, ou a tecla **F**) esconde barra, painéis e rodapé e deixa só as imagens; **Esc** ou **F** volta. O painel da direita (Imagem, Medidas, DICOM, PET, Filme, IA) vem **recolhido**; a setinha na borda o abre. Tudo fica guardado no navegador.
- **Monitores e janelas (0.100.19)**: o botão **Monitores**, na lista, abre a configuração (guardada no navegador, como a aba Monitores do Ipê): exames **nesta janela** ou em **janelas separadas**; para cada janela, a **ordem** (▲▼ — a Janela 1 começa nas primeiras séries, a 2 nas seguintes), o que **apresenta** (o exame, o **exame anterior** para comparação, ou não usar), o **layout** dos quadros e o **monitor**. *Detectar os monitores* (Chrome e Edge, em HTTPS ou no próprio computador) lista os monitores da esquerda para a direita, e cada janela abre no monitor escolhido; sem isso, arraste cada janela para o lugar uma vez — a posição fica guardada.
- **Várias janelas, uma por monitor (0.100.18)**: na lista, a caixa **Abrir nesta janela / 1, 2 ou 3 janelas de visualização** escolhe onde os exames abrem. Com janelas de visualização, a lista continua na janela dela (monitor 1) e cada exame abre nas outras janelas (monitores 2, 3…), para qualquer exame — como no Ipê. As janelas ficam abertas entre um exame e outro: **Fechar** numa delas fecha o exame em todas, e elas esperam o próximo; **Sair**, na lista, fecha todas. A 2ª janela começa nas séries seguintes às da 1ª; na mamografia, a 2ª janela é a segunda tela do protocolo. **Na primeira vez**: (1) o navegador só deixa abrir uma janela por clique — permita os *pop-ups* do endereço do servidor (o ícone que aparece na barra de endereço); (2) arraste cada janela para o monitor dela: a posição e o tamanho ficam guardados. No Chrome e no Edge, em HTTPS, o navegador pergunta se pode *gerenciar janelas em todas as telas*: aceitando, cada janela nova já abre num monitor, ocupando-o inteiro.
- **Celular e tablet (0.100.18)**: no celular a lista vira cartões (um toque abre o exame) e o visualizador mostra uma imagem por vez, com a barra de ferramentas rolando de lado; **Séries** e **Painel de ferramentas** (os dois primeiros ícones) abrem os painéis como gavetas por cima da imagem. Gestos: **um dedo** faz a função escolhida na barra (de início, rolar os cortes), **dois dedos** em pinça ampliam e deslocam, **três dedos** movem; segurar o dedo abre o menu. No tablet deitado o layout é o do computador, com painéis mais estreitos. A sessão agora sobrevive ao recarregamento da página (o celular recarrega sozinho) e termina ao fechar a aba.
- **Fechar e sair (0.100.5; 0.100.15)**: com um exame aberto, **Fechar** (canto de cima) fecha o exame e volta à lista; na lista, **Sair** sai do Ipê Web. Fechar ou recarregar a aba com um exame aberto pede confirmação.
- **A busca volta (0.100.15)**: ao fechar o exame (Fechar ou ← Voltar), a lista volta com a mesma busca e os mesmos filtros (nome, datas, modalidade), com o exame que estava aberto marcado. Vale para aquela aba do navegador; **Sair** esquece a busca.
- **Lista de exames (0.100.2)**: clique no título de uma coluna (Data, Paciente, ID, Descrição, Modalidade, Imagens) para ordenar; clique de novo para inverter (▲ crescente, ▼ decrescente). A escolha fica lembrada no navegador.
- **Overlay (0.100.2)**: o ícone **Overlay** liga e desliga, de uma vez, tudo o que está por cima da imagem — os achados de **CAD/IA** (SR), as anotações de outro sistema (**GSPS**), os contornos de radioterapia (**RTSTRUCT**), os textos dos cantos, as medidas e as linhas de referência —, como o botão CAD/IA do Ipê. A setinha ao lado escolhe item por item: cada tipo de objeto (o que você esconde fica escondido nos próximos exames), cada objeto, os textos dos cantos, as medidas e as linhas de referência. Os objetos são lidos no servidor pelo mesmo leitor do Ipê; as medidas que o próprio Ipê grava não aparecem duas vezes. A SEG escolhida no ícone de segmentação aparece também nos quadros de cortes.
- **CAD/IA no overlay (0.100.14)**: na setinha do Overlay, **CAD/IA (achados, segmentações, níveis)** liga e desliga só a IA — os achados, a SEG nos cortes e os nomes dos níveis —, sem mexer nos textos e nas medidas; a escolha fica lembrada. Os **níveis da coluna** (C1…S1, vértebras e discos) e os **níveis linfonodais** aparecem como no Ipê: em qualquer série e plano, inclusive no MPR (num sagital, todos; num axial, o nível daquele corte).
- **Linhas de referência nos cortes (0.100.2)**: com dois ou mais quadros de cortes, o plano do quadro **ativo** aparece como linha nos outros (um axial no scout, um sagital no axial…). Com a ferramenta **Linhas de referência** num botão do mouse, clicar (ou arrastar) num quadro de cortes leva os outros quadros ao corte daquele ponto — o localizador do Ipê.

**Volume: MPR, oblíquo e MIP (0.99.92).**

- **Mudar o plano com um clique**: no alto de cada quadro, **A**, **C** e **S** reconstroem a série naquele plano (axial, coronal, sagital), **MIP** põe o MIP girando e **Original** volta aos cortes como foram adquiridos.
- **MPR** (barra): o quadro ativo vira quatro — axial, coronal, sagital e o MIP girando — com as **linhas de referência**. O botão esquerdo passa a ser "Linhas de referência": arrastar o centro leva os outros planos ao ponto; arrastar a ponta de uma linha gira a linha, e os outros quadros viram planos **oblíquos**.
- **Oblíquo** (barra): dois cliques no quadro ativo marcam uma reta; o outro quadro de volume vira o plano que contém essa reta, perpendicular ao plano onde ela foi desenhada (como o oblíquo do Ipê).
- **Espessura**: 3, 5, 10 ou 20 mm, em **MIP**, **MinIP** ou **Média**, no quadro de volume ativo; o canto diz o plano e a espessura.
- **MIP girando**: **Girar MIP** liga o giro em volta do eixo do paciente; a roda do mouse sobre o MIP gira aos poucos. **Clicar num ponto do MIP** leva os outros quadros ao ponto mais claro daquela linha de visão. Na TC o MIP abre com janela larga; no PET, invertido.
- Série que não dá volume (imagem única, cortes com orientações ou tamanhos diferentes, vários quadros num arquivo) fica em cortes, com o aviso do motivo. Volumes maiores que 1,5 GB não são montados no navegador.

**Medidas (0.99.93).** Na barra: régua, ângulo, Cobb, ROI elíptica, retangular e livre, pixel, seta e calibração (em qualquer botão do mouse).

- **O número é o do Ipê**: a mesma escala (calibração desta imagem, depois a da série, a região do ultrassom e o espaçamento do arquivo), a mesma regra da ROI (o pixel conta se o centro está dentro) e o mesmo texto — média ± DP, mínimo e máximo, área.
- **Ficam no banco do servidor**, no formato do Ipê: o que se mede no navegador aparece no Ipê (e o que se mediu no Ipê aparece no navegador), com quem mediu. Mexer numa ponta atualiza a medida; para apagar, clique na medida com o botão direito (menu ▸ Apagar esta medida) ou use a aba **Medidas**. Só vale para os quadros de cortes ("Original"): no MPR as medidas ficam só na tela, como no Ipê.
- **Ultrassom**: a distância usa a região calibrada do próprio aparelho; uma régua que atravessa duas regiões (do 2D para o Doppler, por exemplo) fica em pixels. **Calibração**: trace uma distância conhecida e digite os milímetros — no ultrassom vale só para aquela imagem; nas outras modalidades, para a série.

**PET/CT (0.99.94).**

- **PET/CT** (barra): a leitura de PET como no Ipê — a **fusão** (a TC em partes moles com o PET por cima), o **PET** em cinza invertido e o **MIP do PET**. Os dois axiais andam juntos (corte, zoom e posição); clicar no MIP leva os cortes ao ponto mais claro. O programa escolhe o PET do quadro ativo (ou o maior do exame) e a maior TC.
- **SUV pela conta do Ipê**: o PET chega ao navegador já em SUV (pelo peso, com a dose e os horários do arquivo); sem peso ou sem dados do radiofármaco, o aviso diz o que falta e os valores ficam em Bq/ml. A ROI e o valor do pixel no PET trazem o SUVmáx e o SUVméd como no Ipê.
- **Cor da fusão** (as tabelas do Ipê: Hot Iron, PET, arco-íris…), **opacidade** e **topo da janela de SUV**. O que fica abaixo de 8% da janela não pinta, como no Ipê.
- **Janela do PET no mouse (0.100.2)**: com a janela/nível num botão, arraste no PET, no MIP ou na fusão — **para cima e para baixo muda o topo**, **para os lados o piso** —; a janela vale para todos os quadros do mesmo PET e aparece no canto (*SUV 1–9*). Na fusão, **Shift + arrasto** ajusta a TC de baixo.
- **Arranjo do PET/CT (0.100.2)**: na aba **PET**, escolha a grade (1×1 a 2×3) e o que cada quadro mostra — **TC + PET**, **TC**, **PET** ou o **MIP do PET (3D)** — e o plano (axial, coronal, sagital). O arranjo fica lembrado para o próximo PET/CT; **Arranjo padrão** volta à fusão, PET e MIP.
- **SUV máximo perto do cursor**: escolha o ícone (com o botão do mouse que vai usar) e clique perto da lesão num quadro de volume do PET (a fusão, A, C ou S): o programa acha o voxel mais quente numa esfera de 3 cm e leva os cortes até ele; o valor aparece no canto.
- **Segmentação (SEG)**: as segmentações gravadas no exame (a carga tumoral, os órgãos e as lesões da IA do Ipê) aparecem como máscaras coloridas nos quadros de volume, com as cores do Ipê.

**Mamografia com uma e duas telas (0.99.98).**

- O exame de mamografia **abre no protocolo do Ipê** (o seu, de Configurações ▸ Mamografia, ou o de fábrica): a barra **Mamografia** em cima das imagens diz o protocolo e a etapa (**4 incidências**, CC, MLO, atual × anterior…). As setas passam de etapa; clicar no nome da etapa abre a lista. O protocolo também se troca ali.
- **As mesmas regras do Ipê**: a imagem de cada quadro (a de apresentação, a mais recente), o **exame anterior** do paciente nos quadros "ant" (com a data no canto), as mamas **costas com costas** (espelha quando a parede torácica veio do outro lado), a **mama enquadrada** (o ar fica de fora), a parede encostada na borda, o mesmo zoom nas duas e os **mamilos na mesma altura**.
- **Duplo clique** amplia o quadro; outro duplo clique volta. **Cada quadro é uma pilha da incidência, como no Ipê (0.100.2)**: a roda do mouse passa por todas as imagens 2D daquela mama e incidência e, em seguida, pelos cortes da tomossíntese. **Tomossíntese do quadro** (barra) pula da 2D para o meio da tomo e de volta. **Ao rolar da 2D para a tomo (0.100.4)** a imagem nova fica na mesma escala em milímetros e com a parede torácica no mesmo lugar, mesmo com o zoom à mão — a tomo tem outro tamanho e outro espaçamento. **Desde a 0.100.17** o enquadramento da abertura da etapa vale para todas as imagens da pilha, como se estivessem empilhadas: ir e voltar pela roda devolve exatamente o zoom e a posição de antes (o tamanho do pixel vem do servidor, que lê o ImagerPixelSpacing da 2D e os grupos funcionais da tomo). O zoom à mão passa a ser o novo enquadramento de todas.
- **Lupa (0.100.4)**: **Lupa no botão esquerdo** (barra) — segure o botão e passe sobre a imagem: o círculo mostra os pixels da própria imagem aumentados (não os da tela), com a janela do quadro; a roda, com a lupa aberta, muda o aumento (1,5× a 8×, lembrado). O mesmo botão devolve a função de antes. A lupa também está em **Zoom e lupa**, para qualquer botão do mouse e qualquer exame.
- **Duas telas**: abre uma segunda janela do navegador com a outra metade da etapa — as CC numa tela, as MLO na outra, por exemplo, como o Ipê reparte. A segunda janela entra sem pedir a senha (recebe a sessão da primeira), e as duas mudam de etapa juntas. No Chrome e no Edge com a permissão de "gerenciamento de janelas", ela já abre no outro monitor; sem a permissão, arraste-a até lá. Fechar a segunda volta a uma tela. Se o navegador bloquear a janela, permita janelas do endereço do servidor.
- **Sair do modo mamografia** (barra) volta ao visualizador comum. A leitura no navegador depende do monitor: para laudar, use o monitor calibrado (DICOM GSDF).

**Dinâmica da mama (0.99.98).**

- **Dinâmica da mama** (barra, nos exames de RM): o servidor acha as fases como o Ipê (as séries da dinâmica, ou uma série com todas as fases) e o navegador monta quatro quadros — a **fase inicial**, o **mapa cinético**, o **SER** e a **subtração** — que andam juntos pelos cortes. Cada quadro pode mostrar outro mapa: MSI, PEI, realce inicial, tempo até o pico, MIP e média temporais.
- **Os mapas são calculados no navegador, corte a corte, com as contas do Ipê** (os mesmos limiares, o mesmo ruído e a mesma máscara de tecido; conferidos pixel a pixel nos testes). As fases pré, inicial e tardia se trocam na barra.
- **Sobre a fase**: um mapa calculado ou um mapa que o Ipê **já gravou como série** ("SER (dinâmica)", "Cinética (dinâmica)"…) vai por cima da fase inicial, com a tabela de cores do Ipê e a opacidade da barra; o que não tem valor fica transparente.
- **Curvas tempo-intensidade**: desenhe uma ROI (elipse, retângulo ou polígono) ou marque um **ponto** (valor do pixel, média 3×3) em qualquer quadro; embaixo aparece a curva e a tabela com a **classe** (médio/rápido × persistente/platô/washout), o realce inicial, o SER, o pico, o TTP, o BAT, a lavagem, o iAUC90 e o MRT — os números do Ipê.
- **Curva sob o cursor (0.100.2)**: como no Ipê, passar o mouse sobre a imagem mostra a curva do ponto (3×3 pixels), tracejada, junto das guardadas; a caixa **Curva sob o cursor** na barra desliga.
- **O rótulo de cada quadro (0.100.2)**: nos quadros de fase, **◂ ▸** passam de fase; clicar no texto (ou o botão direito) abre o menu do quadro — o que mostrar (qualquer fase ou mapa), **Subtração (fase − pré-contraste)** de qualquer fase, **Paisagem** (10 a 50% da anatomia de volta na subtração, como no Ipê) e a **cor** (as tabelas do Ipê, ou cinza). A barra escolhe também a **cor do mapa por cima da fase**.
- **Correção de movimento (0.100.8)**: o seletor da correção de movimento na barra — **Sem correção**, **Translação** ou **Rígida** (com rotação), como no Ipê. O servidor faz a conta do Ipê (a translação 3D de cada fase sobre a pré e, na rígida, a rotação da fase que girou) e o navegador aplica ao montar cada corte: os mapas, as curvas, as subtrações e o quadro da fase que se mexeu saem corrigidos. A dica do seletor diz quanto mexeu (o maior deslocamento e a maior rotação). Vem ligada como você a deixou no Ipê; trocar a pré refaz a conta.
- Ficam só no Ipê, por enquanto: fases fora da conta e a linha de base pela média das fases pré.

**Enviar a um destino DICOM (0.100.9).** O botão **Enviar a um destino DICOM** (o avião de papel, ao lado do Laudo) só aparece para quem tem a permissão de enviar para nós DICOM.

- **O que**: o exame inteiro, as séries marcadas (a do quadro ativo já vem marcada) ou só a imagem do quadro ativo.
- **Para**: os nós DICOM ativos do servidor (os do serviço, os seus e os compartilhados com você) e, se o nó tiver, a identidade (o AE) com que o servidor fala com ele.
- **Junto: as medidas (GSPS) e as imagens-chave (KO)**: o que se mediu no exame vira um GSPS e as imagens-chave um KO, gravados no exame e mandados no mesmo envio.
- O envio entra na **fila de envios do servidor**, a mesma do Ipê. **Envios**, no rodapé, mostra os que você pediu, com o andamento (enviadas/total), o resultado e **Cancelar** enquanto anda. Cada envio fica no registro de acesso, com o seu nome.

**CAD/IA no navegador (aba IA, 0.100.12).** A aba **IA** do painel da direita (ao lado de Filme) só aparece para quem tem a permissão **Pedir CAD/IA à mão** (de fábrica: administrador e médico; o administrador ajusta em **Usuários ▸ Perfis e permissões**). O botão **CAD/IA neste exame** da barra e **IA**, no rodapé, abrem a mesma aba.

- **Tarefas deste exame**, no alto: as pedidas e as automáticas, com o estado (na fila, montando o volume, rodando, gravando, pronto), a etapa, o tempo e uma barra enquanto anda. **Cancelar** aparece nas que você pediu (quem configura cancela qualquer uma).
- **Ferramentas**, embaixo: todas as ferramentas de IA do Ipê (órgãos abdominais, coluna, nódulos, composição corporal, enfisema, autoPET, cálcio…). Primeiro as que **servem para este exame**, com a **série sugerida** (a mesma que o automático escolheria); depois as **outras**, com o motivo de não servirem. Em qualquer uma dá para escolher a **série do quadro ativo**.
- Escolha a ferramenta e a série e clique **Rodar** (ou **Refazer**, se o exame já tem o resultado). A IA roda **no servidor**, na mesma fila do automático da chegada, uma por vez; o pacote de segmentação tem de estar instalado no computador do servidor. A janela *Tarefas de IA* do Ipê mostra as mesmas tarefas.
- Quando a tarefa termina, o resultado aparece **na mesma sessão**, sem fechar e abrir o exame (0.100.15): as séries novas entram na tira, a SEG entra no ícone de segmentação (e já aparece pintada, se nenhuma estava escolhida), os nomes da coluna e dos linfonodos entram no overlay e as séries ganham o selo IA.
- **Achados para revisar (0.100.16)**: as IAs que apontam achados para o médico revisar (enfisema, nódulos, Genant, cálcio coronariano, aorta, carga tumoral no PET, composição corporal) aparecem na aba IA, como no painel *Achados de IA* do Ipê. Cada achado mostra os números, o estado (sugerido, confirmado, corrigido, descartado) e quem revisou. **Ir até** leva os quadros ao achado; **Confirmar**, **Corrigir…** (troque os números e grave: o achado fica *corrigido* e o laudo leva os seus números), **Descartar** e **Voltar a sugerido**. **Mandar ao laudo** abre o laudo e põe o texto dos achados confirmados e corrigidos onde está o cursor — nada vai ao laudo sem revisão. Revisar precisa da permissão de escrever laudos (o residente também revisa; a aba IA aparece para ele só com os achados); cada revisão fica no registro de acesso. É a mesma lista do Ipê: o que se revisa num aparece no outro.

**Filme e impressão no navegador (0.100.11).** A aba **Filme** do painel da direita só aparece para quem tem a permissão de imprimir.

- **Montar**: ajuste a imagem no quadro com as ferramentas de sempre (janela, zoom, deslocamento, giro, inverter) e clique **+ Quadro ativo**, **+ Todos os quadros** ou **+ Série do quadro** (a série inteira, uma imagem a cada N, com o ajuste do quadro). Só imagens originais entram (não MPR, MIP ou mapas).
- **A prévia é o que sai**: o servidor desenha a folha com o mesmo código do compositor do Ipê (cabeçalho com paciente e exame, régua, textos, medidas). ◂ ▸ passam de folha.
- **Editar**: clique numa célula da prévia. **Editar no quadro ativo** põe a imagem no quadro com o ajuste dela; mude o que quiser e clique **Atualizar a célula**. **◂ ▸** mudam a ordem e **Remover** tira.
- **Folha**: nome, grade (1×1 a 6×5), papel (A4, A3, Carta, filmes de 8×10 a 14×17 pol), paisagem, textos, cabeçalho, anonimizar, régua e fundo preto. O filme fica guardado no navegador até você limpar.
- **Imprimir**, em **Saída**:
  - **Baixar PDF**;
  - **Imprimir neste computador**: o navegador abre a janela de imprimir dele, com as impressoras do computador de quem está usando;
  - as **impressoras do computador do servidor**, pelo nome;
  - as **impressoras DICOM** cadastradas no servidor;
  - os **destinos de impressão do Ipê** (PDF ou imagens numa pasta, impressora do sistema, impressora DICOM).
- **Só esta folha** imprime a folha da prévia. Cada impressão conta no painel de filmes (o filme fica salvo, com quem imprimiu e para onde) e no registro de acesso.
- O zoom e o deslocamento vão como no Ipê, em relação a "caber na célula". Como a célula do filme tem outra proporção que o quadro da tela, o enquadramento pode mudar um pouco; a prévia mostra como vai sair.

**Laudo no navegador (0.99.98).**

- **Laudo** (barra) abre o laudo ao lado das imagens, no mesmo registro de laudo do Ipê: o que se escreve num aparece no outro.
- Sem laudo, ele começa pelo **modelo sugerido** para o exame, com os **campos automáticos** preenchidos como no Ipê (paciente, idade, data, comparação, medidas, lesões…). **Aplicar modelo** troca o texto pelo de outro modelo.
- **Inserir achados de IA** põe no cursor os achados da IA **confirmados ou corrigidos** (o sugerido não entra), com a frase de cada ferramenta.
- **Salvar rascunho** (e ele também salva sozinho alguns segundos depois de parar de digitar). **Assinar e liberar** pede a confirmação na própria janela; assinado, o laudo não muda mais — **Retificar** cria um rascunho novo com o texto, e o anterior fica guardado.
- **Quem está laudando**: abrir o laudo trava o exame para você. Se outro médico abrir, vê o aviso e escolhe **Só ler** ou **Assumir o laudo** (fica no registro de acesso); o servidor recusa gravar ou assinar por quem não tem a trava. Fechar o laudo (ou sair do exame) solta a trava. Quem não tem permissão de escrever laudos só lê.
- **BI-RADS® (0.100.4)**: o mesmo formulário da janela do laudo do Ipê — o tipo (mamografia, ultrassonografia ou ressonância), a composição (ou o tecido fibroglandular e o realce de fundo na RM), os **achados** (**+ Achado**: lado, tipo, descritores da lista, tamanho, local, distância do mamilo, mudança e categoria), a categoria de cada mama e a recomendação. O texto do laudo muda sozinho, com as mesmas frases do Ipê; num modelo sem os campos do BI-RADS, **Levar ao texto do laudo** põe os blocos onde está o cursor. A categoria final é a mais preocupante.
- **PDF e DICOM (0.100.4)**: **Baixar PDF** gera o PDF do Ipê (rascunho sai marcado), com o **cabeçalho** e a **linha da assinatura** (ficam guardados). Ao assinar, como no Ipê, o PDF (DICOM encapsulado) e o laudo em **SR** entram no exame — as duas caixas escolhem.
- **Busca ativa (0.100.4)**: ao assinar, o BI-RADS 0 ou 3 (as categorias das Configurações ▸ Busca ativa) cria o pedido de chamar a paciente, com o prazo; a retificação troca o pedido. Os pedidos abertos da paciente aparecem no alto do laudo.

Por enquanto é só na rede da clínica; de fora, entre pela VPN.

### HTTPS na rede interna (certificado do Ipê)

Sem certificado, o servidor central usa HTTP e a senha de cada login passa aberta pela rede. Um certificado de autoridade pública não serve para um endereço como 192.168.1.10, então o próprio Ipê faz o papel de **autoridade certificadora (AC) interna**:

1. **No servidor:** Configurações ▸ Rede ▸ Servidor central ▸ **Gerar certificado para a rede interna…**. Na primeira vez ele cria a AC do serviço (vale 10 anos) e, com ela, o certificado do servidor, válido para o nome do computador e todos os IPs dele (825 dias). Os campos Certificado e Chave são preenchidos sozinhos. A janela mostra a **impressão digital** da AC: anote-a. Dê OK e feche e abra o programa: o servidor passa a responder em `https://`.
2. **Em cada cliente:** troque o endereço para `https://…` e clique em **Confiar no certificado deste servidor…**. O Ipê baixa a AC do servidor e mostra a impressão digital: confira que é a mesma do servidor e confirme. Daí em diante o cliente só aceita aquele servidor (outro computador na rede não consegue se passar por ele).
3. **Navegadores e outros visualizadores DICOMweb:** **Salvar a AC (.crt)…** no servidor e, no Windows de cada cliente, duplo clique no arquivo ▸ Instalar certificado ▸ Máquina local (ou Usuário atual) ▸ Autoridades de Certificação Raiz Confiáveis.

Gerar de novo (por exemplo, quando o servidor mudar de IP) troca só o certificado do servidor; a AC continua a mesma e os clientes não precisam fazer nada. A chave da AC fica só no servidor, na pasta `certificados` das configurações; guarde uma cópia dela junto com o backup.

### Perfis por grupo e computador

**Configurações ▸ Usuários ▸ Perfis por grupo e computador…** (quem gerencia usuários) monta perfis de preferências que o servidor manda para as estações: cada perfil diz para quais **computadores** vale (nomes, com coringa: `SALA-MAMO*`, `TC-0?`), para quais **usuários** e quais **perfis de acesso** (vazio = todos), e quais preferências leva — mouse, texto sobre a imagem, atalhos, colunas do banco, monitores, dinâmica da mama, CAD/IA, idioma… O jeito mais fácil é arrumar um computador como deve ficar e usar **Capturar deste computador…**; dá também para escrever chave e valor à mão (o valor em JSON).

Ao entrar, valem os perfis que casam, na ordem da lista (o de baixo ganha). O perfil manda sobre o que vem do computador, e cada pessoa ainda pode ajustar o seu — menos nas chaves marcadas **Forçar**, que ninguém troca. No modo cliente os perfis moram no servidor; num computador com várias pessoas, no banco dele (aí só usuários e perfis de acesso fazem diferença). O nome deste computador aparece na própria janela.

### Atualizações pelo servidor central

**Configurações ▸ Rede ▸ Atualizações pelo servidor central…** (quem gerencia usuários, no servidor ou num cliente) publica o pacote de uma versão — de preferência o instalador do Windows, `Ipe-setup-x.y.z.exe` — num de dois canais: **teste**, que vai primeiro para os computadores e as pessoas dos perfis marcados *Atualizações: Teste*, e **estável**, para todos. **Promover teste → estável** libera para todos o que já foi testado; **Retirar** tira o pacote do canal.

Ao entrar no modo cliente, o programa confere o canal dele; havendo versão mais nova, pergunta se baixa e instala. Com o "sim", baixa, confere o SHA-256 e, sendo o instalador do Windows, fecha o programa e instala sem mais perguntas. Outro tipo de pacote (zip, tgz) é baixado e a pasta abre, para instalar à mão. Com o "não", não pergunta de novo a mesma versão; **Ajuda ▸ Procurar atualização no servidor central…** pergunta na hora. Cada publicação, promoção e retirada fica no registro de acesso.

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

## IA no texto do laudo

O botão **IA ▾**, na janela do laudo, ao lado de **Inserir ▾**:

- **Conferir o laudo (sem rede)** — sempre disponível: aponta campo não preenchido ("___", "{campo}"), medida sem unidade ("medindo 12") ou grande demais (mais de 400 mm ou 60 cm), palavra repetida, "direita esquerda", órgão que não combina com o sexo do paciente (útero no masculino, próstata no feminino), categoria BI-RADS do texto diferente da do formulário, BI-RADS 3 com conduta de rotina, BI-RADS 4 e 5 sem histopatológico, conclusão que cita um lado que o corpo do laudo não cita e impressão vazia. A mesma conferência roda **antes de assinar**: se achar algo, mostra a lista e pergunta se assina mesmo assim (desliga em Configurações).
- **Refinar o texto (IA)…**, **Gerar a impressão (IA)…** e **Apontar erros (IA)…** — com um modelo de linguagem configurado. A resposta abre numa janela editável; nada entra no laudo sem **Trocar o texto do laudo por este** ou **Inserir no laudo (no cursor)**, e Ctrl+Z desfaz.

**Configurações ▸ Laudos ▸ IA no texto do laudo…** escolhe o provedor: **Ollama** (o modelo roda neste computador ou num servidor da rede; o texto não sai do serviço), um servidor **compatível com OpenAI** (LM Studio, vLLM, llama.cpp) ou a **API da Anthropic** (com a chave do serviço; o texto sai para fora). Antes de sair do programa, o texto perde o **nome, o ID, o accession e a data de nascimento** do paciente, que voltam na resposta; para um endereço fora deste computador, o programa pergunta uma vez. **Testar** confere a conexão. A chave da API fica guardada **cifrada**. O modelo só sugere: quem assina é o médico.

## Documentos anexados ao exame (PDF e imagens)

Pedido médico, termo de consentimento, laudo anterior de outro serviço, foto da lesão: o PDF ou a imagem entra **dentro do exame**, convertido para DICOM, e vai junto quando o exame é exportado ou enviado ao PACS. Três caminhos:

- **arrastar sobre o visualizador** — vai para o exame aberto (o do quadro ativo);
- **arrastar no banco de dados com um exame selecionado** — o programa pergunta antes ("Anexar 2 arquivos ao exame de …?"), para não cair no paciente errado;
- **botão direito no exame ▸ Documentos ▸ Anexar documento (PDF ou imagem)…**, ou, no visualizador, o menu de séries do quadro ▸ **Anexar documento…**.

O **PDF** vira um documento PDF encapsulado em DICOM (modalidade DOC), na série **Documentos anexados**, com o nome do arquivo como título. Cada **imagem** (JPG, PNG, TIFF — cada página vira uma —, BMP, GIF, WEBP) vira uma imagem DICOM (captura secundária, modalidade OT) na série **Imagens anexadas**, e aparece no visualizador como qualquer outra série. Os dados do paciente e do exame são os do próprio exame. Word, Excel e outros formatos ficam de fora, com o aviso: salve como PDF antes.

O anexo segue as **regras de roteamento** do exame (Configurações ▸ Rede ▸ Automação): se o exame iria para um nó, o anexo vai também. Quem anexou fica no registro de acesso.

Para ler os PDF do exame — anexados, laudos guardados em PDF ou PDF que vieram de outro sistema —: botão direito no exame ▸ **Documentos ▸ Documentos do exame…**, duplo clique na série de documentos no painel de séries, ou o menu de séries do quadro ▸ **Documentos do exame…**. O PDF abre dentro do programa; há também **Abrir no programa do sistema** e **Salvar o PDF…**.

## Laudo em andamento (servidor central)

No modo cliente, quem abre o laudo de um exame passa a ser **quem está laudando**, até fechar a janela do laudo. Outro médico que abrir o laudo do mesmo exame é avisado ("Dra. Ana está laudando este exame desde 10:05") e escolhe **Só ler** (a janela abre sem poder gravar) ou **Assumir o laudo** (fica no registro de acesso, e o primeiro não grava mais). Quem só abre as imagens vê o aviso na barra de status. O servidor recusa gravar ou assinar o laudo de quem não está com ele. Se o computador de quem laudava travar, a trava cai sozinha em 10 minutos.

## Fim da leitura: enviar ao PACS ao assinar

**Configurações ▸ Laudos ▸ Fim da leitura (enviar ao PACS ao assinar)…** liga o envio e escolhe o **destino** (um dos nós de rede ativos). Ao **assinar** o laudo, o programa grava as imagens-chave como um **KO** e as medidas como um **GSPS** no exame, e manda ao destino, pela fila de envios (a mesma do envio à mão):

- **o laudo** desta assinatura (o PDF e o SR, se você os guarda no exame);
- **as imagens-chave (KO)** e **as medidas e anotações (GSPS)**;
- **as séries do Ipê** no exame (as SEG das análises, mapas, capturas).

Cada item se liga e desliga. Não vão: o laudo de antes, as séries de outro aparelho, as **ocultas** e as cópias que ficam só neste computador (a cópia sem implante, as tabelas da segmentação). A barra de status do laudo diz "enviando ao PACS: …" e o envio fica no registro de acesso. Vale também para o laudo assinado no **navegador**: o servidor central grava e manda sozinho.

## Fechar o exame sozinho

**Configurações ▸ Visualizador ▸ Fechar o exame sozinho…**: fechar o exame (e a janela do laudo) ao **assinar o laudo**, e/ou fechar os exames abertos depois de **N minutos sem mexer** no mouse e no teclado (o rascunho do laudo é salvo antes). Evita que o próximo paciente seja olhado — ou laudado — com o anterior ainda na tela.

## Busca ativa (BI-RADS 0 e 3)

Ao **assinar** um laudo com o formulário BI-RADS, a categoria final decide se a paciente entra na **busca ativa**: de fábrica, **BI-RADS 0** com prazo de **30 dias** e **BI-RADS 3** com **180 dias**, contados da assinatura. A retificação troca o pedido aberto do exame (ou o encerra, se a categoria nova não pede retorno). Em **Configurações ▸ Laudos ▸ Busca ativa (prazos por BI-RADS)…** dá para mudar os dias e ligar também 4A, 4B, 4C e 5 ("aguardando o histopatológico").

**Laudos ▸ Busca ativa…** mostra os pedidos — abertos, atrasados (em vermelho), que retornaram ou encerrados — com o prazo e a situação ("faltam 12 dias", "atrasada 3 dias"). Os botões **Contatada**, **Agendada**, **Retornou**, **Encerrar…** (com o motivo) e **Nota…** vão ao histórico, com quem e quando; **Abrir o exame** abre o exame de origem (ou o de retorno). A paciente **retorna sozinha** quando chega ao banco um exame de mama dela com data igual ou posterior (mamografia, ou US/RM com "mama" na descrição) — o botão **Conferir retornos** refaz essa conferência. **Exportar CSV…** leva a lista para a planilha da recepção. No servidor central, a lista é uma só para todas as estações.

## Lista de trabalho: prioridade, subespecialidade e prazo (SLA)

Cada exame do banco tem uma **prioridade** (rotina, urgente, emergência), uma **subespecialidade** (mama, neuro, cabeça e pescoço, tórax, musculoesquelético, abdome, medicina nuclear ou geral) e um **prazo do laudo**: a chegada ao banco + as horas da prioridade (de fábrica, rotina 48 h, urgente 4 h, emergência 1 h; a rotina pode ter horas próprias por subespecialidade, como "Mama=72"). As colunas **Prioridade**, **Subespecialidade**, **Prazo do laudo** e **SLA** mostram isso; o SLA diz "faltam 5 h", "vence em 40 min" (laranja, a menos de 2 h), "atrasado 3 h" (vermelho) e, depois de assinado, "no prazo" ou "fora do prazo (+5 h)". Urgente aparece em laranja e emergência em vermelho.

A prioridade sai das palavras da descrição do exame (de fábrica "URGENTE", "PS", "PRONTO SOCORRO", "UTI" → urgente; "EMERGÊNCIA", "CÓDIGO AVC", "TRAUMA" → emergência) e a subespecialidade da primeira regra que casar (modalidades + palavras da descrição). Tudo se ajusta em **Configurações ▸ Laudos ▸ Prioridade, subespecialidade e prazos (SLA)…**; em cada exame, **botão direito ▸ Organizar ▸ Prioridade** ou **▸ Subespecialidade** troca à mão ("Da regra" volta ao automático).

O botão **Trabalho ▾**, no banco de dados, filtra e ordena pelo prazo: **sem laudo** (o que vence primeiro em cima), **atrasados**, **vencem em menos de 2 h**, **urgências e emergências** e **minhas subespecialidades** (escolha as suas uma vez em *Escolher minhas subespecialidades…*). No servidor central as regras valem para todas as estações.

**Estado do exame** (0.99.63): a coluna **Estado** (Colunas ▾) mostra *Não lido* (nunca aberto e sem laudo), *Em leitura* (aberto, ou com rascunho), *Urgente* (sem laudo assinado e com prioridade urgente ou emergência) e *Revisado* (laudo assinado), em cores, e ordena nessa ordem. O botão direito ▸ **Organizar ▸ Estado do exame** troca à mão — o revisado sem laudo (segunda leitura, reunião), o que voltou para leitura —, e a coluna marca o trocado com ✎; *Automático* volta ao cálculo. Em **Trabalho ▾**: *Não lidos*, *Em leitura* e *Ainda não revisados*. No visualizador, a ação *Exame: marcar como revisado* (escolha uma tecla em Atalhos ▸ Estudos) marca o exame do quadro ativo; de novo, volta ao automático.

## Produtividade

**Laudos ▸ Produtividade…** conta os laudos **assinados** no período (hoje, 7 ou 30 dias, este mês, mês passado, este ano ou datas escolhidas) e agrupa por **médico**, **modalidade**, **subespecialidade**, **prioridade** ou **dia**: quantos laudos, quantas retificações, a **mediana** e o **p90** do tempo da chegada do exame ao banco até a assinatura (em horas) e quantos saíram **no prazo** (pelas regras de prazo do item anterior). As barras mostram no prazo em verde e fora do prazo em laranja. Em cima, o que está **pendente agora**: exames sem laudo assinado, atrasados e vencendo em menos de 2 h. **Exportar CSV…** leva a tabela para a planilha. Quem não gerencia usuários vê só os próprios laudos. Um laudo conta como um laudo (sem pesos por modalidade).

## Filtros de mamografia

O botão **Mama ▾**, ao lado de **Colunas ▾** no banco de dados, aplica filtros prontos e mostra as colunas que eles usam: **BI-RADS 0**, **3**, **4 e 5**, **6**; **mamas densas** (ACR c e d) ou não densas; **mamografias sem laudo assinado**; **rastreamento** ou **diagnóstica** (pela descrição do exame); **busca ativa aberta** ou **que retornou**. As colunas **BI-RADS** e **Densidade** vêm do laudo BI-RADS assinado mais recente do exame; **Busca ativa**, do pedido do exame. Como toda coluna, aceitam também o filtro digitado e o filtro por valores.

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

**Tempo de duplicação**: em cada exame em que a lesão cresceu desde o exame anterior medido, a célula ganha "· TD N d" (fora do PERCIST). A conta é TD = t × ln 2 ÷ ln(V2/V1), supondo crescimento exponencial, pelo **volume** quando os dois exames têm volume segmentado; senão, pelo **maior diâmetro**, supondo esfera (V ∝ d³). Sem crescimento, sai "TD não se aplica" — nunca um número enorme ou negativo. A dica da célula mostra as duas medidas, o intervalo em dias e a base da conta; em lesão pequena, 1 mm de diferença no diâmetro muda muito o resultado.

**Seguimento entre datas** (0.99.59):

- **Ligação pela posição**: cada medida ligada a uma lesão guarda onde ela está no paciente (em mm). Desenhe a medida no exame de seguimento no lugar da lesão: levada ao exame anterior pelo registro (o rígido, ou o alinhamento salvo ao ligar os quadros), se cair a até **10 mm** de onde a lesão estava, a medida **liga sozinha** a ela, e a barra de status diz a qual e a que distância. Sem registro entre os dois exames não liga (não há como saber onde o ponto está no outro); com duas lesões perto, também não — ligue à mão. A caixa e a distância ficam no painel de lesões.
- **Seguimento…** (no painel): as lesões medidas antes e ainda sem medida neste exame, uma por linha. **Repetir a medida** abre a série equivalente no lugar estimado, com o contorno anterior em amarelo e a mesma ferramenta; a próxima medida liga à lesão. **Pequena demais (5 mm)** (alvo; o RECIST 1.1 soma 5 mm), **Ausente (0)**, e, nas não alvo, **Presente / estável** e **Progressão inequívoca**. Medidas feitas antes da 0.99.59 não têm posição: o Repetir abre a série, sem o lugar.
- **Nadir**: a linha *Nadir* mostra, em cada exame, a menor soma até ali, e o cabeçalho marca com ▼ o exame que é o nadir do atual. O resumo do laudo traz as quatro datas — base, nadir, anterior e atual — com a soma de cada uma.

**Contorno da lesão no PET pela borda (0.100.8).** Na **Segmentar 3D** de um PET, o método **PET: borda pelo gradiente (como o PET Edge)** contorna a lesão onde o sinal **cai mais depressa**, e não num valor fixo. O limiar em % do SUVmáx (41%) depende do pico: numa lesão pequena o volume parcial derruba o máximo, o limiar desce até o fundo borrado e o contorno incha. A borda pelo gradiente não depende do pico.

- O programa parte do ponto mais quente perto do clique, lança raios em cerca de 260 direções e, em cada uma, acha a queda mais íngreme antes de o sinal voltar a subir (outra lesão, o coração, a bexiga). A borda de cada direção é conferida com as vizinhas, e a lesão é o que fica dentro dela.
- **Correção do volume parcial**: numa lesão borrada pela resolução do aparelho, a queda mais íngreme fica um pouco para dentro da borda verdadeira — pouco numa lesão de 4 cm, bastante numa de 1,3 cm. O programa leva cada raio de volta à borda verdadeira usando a **resolução do PET (FWHM)**. Numa lesão grande, ele mede a resolução na própria lesão (a largura da queda); nas pequenas, usa o campo **Resolução do PET (FWHM)** da janela (6 mm de fábrica; PET/TC atual, 5–7 mm). O valor fica guardado.
- A nota da janela diz em que porcentagem do máximo ficou a borda e qual resolução foi usada. Abaixo de 1,5 × a resolução, ela avisa que a lesão está **perto do limite** e que o volume é menos confiável.
- Em esferas de teste (resolução de 7 mm, ruído de PET, fundo 4:1 a 8:1), o volume ficou a ±15% do real a partir de 1,3 cm, e o 41% errou o dobro ou mais nas pequenas.

**PET no seguimento** (0.99.60, botão **PET…** do painel de lesões):

- **SUL**: com a altura (PatientSize) e o sexo no arquivo, cada medida de PET guarda também o SUL — o SUV pela massa magra de Janmahasatian (LBM = 9270 × peso / (6680 + 216 × IMC) nos homens, 9270 × peso / (8780 + 244 × IMC) nas mulheres). O PERCIST passa a usar o SULpeak; sem altura ou sexo, continua no SUVpeak e a célula diz qual.
- **Referência do fígado**: *Fígado: clicar* — clique no lobo direito, no PET; a esfera de 3 cm procura, até 2 cm do clique, o lugar mais homogêneo (menor desvio-padrão). *Fígado: automático* — usa a segmentação do fígado do exame (Órgãos/TotalSegmentator na TC do PET/CT), coloca a esfera inteira dentro dele, no lobo direito. **Mediastino**: clique na aorta descendente (esfera de 1 cm). As referências ficam por exame.
- **PERCIST**: limiar de lesão mensurável = 1,5 × SULmédio do fígado + 2 × DP (sem fígado, 2 × pool + 2 × DP). O painel mostra a referência e o limiar em cada exame; avisa quando a lesão mais ávida da base fica abaixo do limiar e quando o fígado varia mais de 20% ou 0,3 entre os exames (não comparáveis).
- **Deauville / Lugano** (critério novo no painel): o escore de cada lesão em cada exame é proposto pelos números — 2 até o mediastino, 3 até o fígado, 4 acima do fígado, 5 acima de 2 × o SUVmáx do fígado (ajustável) ou lesão nova, 1 ausente — e se troca no botão direito ▸ *Deauville neste exame* (inclui o X). A resposta metabólica sai pelo maior escore: 1–3 completa; 4–5 com captação menor que a da base, parcial; igual, sem resposta; maior ou lesão nova, progressão.
- **Q.Check**: o cabeçalho do PET deste exame — tempo de captação (50–70 min), peso, altura e sexo, dose, meia-vida, unidade, correções de decaimento e atenuação, matriz, espessura, reconstrução e aparelho — e a comparação com o exame de base (diferença de captação até 15 min, mesmo aparelho e reconstrução, peso, dose, fígado). A glicemia não vem no DICOM: digite a da ficha no campo **Glicemia** da janela PET… (0.99.88). Ela fica guardada no exame; o Q.Check avisa acima de 200 mg/dL (a EANM recomenda remarcar ou interpretar com cautela, o SUV fica subestimado) e diz que 150–200 é aceitável. Com a glicemia, as medidas no PET mostram também o **SUVglic** = SUV × glicemia ÷ 100 mg/dL (aceita mmol/L: valores abaixo de 35 viram mg/dL × 18).

A segmentação 3D mede volume, SUV máximo e médio, TLG e, somando as lesões, TMTV. Os limiares (percentual do SUVmáx, SUV mínimo, método) ficam guardados, e a barra do limiar vale também para o percentual do SUVmáx.

## Leitura PET e o SUV máximo perto do cursor (0.99.88)

No botão **Fusão** dos exames de PET/CT:

- **Leitura PET: fusão, PET e MIP girando…** monta três quadros: a TC com o PET fundido, o PET sozinho e o MIP do PET em 3D, invertido e girando. **Clique num foco do MIP** para levar os cortes dos outros quadros até ele. O PET corrigido por atenuação é preferido ao NAC.
- **Ir ao SUV máximo perto do cursor (3 cm)** procura o voxel mais ávido numa esfera de 3 cm em volta do cursor de referência e leva os cortes até ele; a barra de status diz o SUV. Útil para cravar o SUVmáx de uma lesão sem caçar o pixel à mão.

## Sessão preparada do PET/CT (0.100.32)

Quando a carga tumoral roda — sozinha na chegada do exame (Configurações ▸ CAD/IA ▸ Carga tumoral ▸ *Fazer automaticamente*) ou pelo botão **Carga** — o exame fica pronto para a leitura:

- **Referências medidas.** O fígado (esfera de 3 cm no lobo direito) e o mediastino (esfera de 1 cm na aorta descendente, achada pelo TotalSegmentator) ficam guardados onde a janela **PET…** guarda as medidas à mão: o limiar do PERCIST, o Deauville e a comparação do fígado com o exame anterior já abrem prontos. Uma referência que você mediu à mão nunca é trocada.
- **Registro com o PET/CT anterior.** A TC é registrada (rotação e translação) com a TC do PET/CT anterior mais recente do paciente. Ao abrir o anterior num quadro ao lado (botão Anteriores), os dois já rolam juntos. Um registro que já existe entre os dois exames não é trocado, e um registro de qualidade fraca não é guardado (o aviso aparece na mensagem).
- **Abre na Leitura PET.** O exame preparado, ainda sem um estado de análise guardado, abre com a TC fundida, o PET e o MIP girando. Se você já deixou o exame de outro jeito, vale o seu.

As duas opções ficam em Configurações ▸ CAD/IA ▸ Carga tumoral: *Sessão preparada…* e *Abrir o exame preparado na Leitura PET*. O registro usa até 60 s.

## Carga tumoral no PET: FDG, PSMA e DOTA (0.99.88)

Botão **Carga** (ou Aplicações ▸ Carga tumoral) num PET/CT. O TotalSegmentator acha os órgãos e os ossos na TC do exame (e, no PSMA, as glândulas salivares); os órgãos são levados à grade do PET. No PET, tudo acima do limiar do traçador que não está num órgão de captação fisiológica (dilatado 1 voxel) vira um **foco**:

- **Traçador**: lido do cabeçalho (radiofármaco, descrição do exame ou da série). Sem ele, as contas são de FDG e o aviso diz isso.
- **Limiar**: FDG — PERCIST (1,5 × fígado + 2 DP, pela esfera de 3 cm no fígado segmentado; sem fígado, SUV 2,5), ou um SUV fixo nas configurações; **PSMA** — SUV 3 (qPSMA); **DOTA** — a média do fígado (Krenning).
- **Captação fisiológica tirada**, por traçador: no FDG, encéfalo, coração, rins e bexiga; no PSMA, glândulas salivares, rins, bexiga, fígado, baço e intestino; no DOTA, fígado, baço, adrenais, rins, bexiga e intestino A lista tirada sai nos avisos — no PSMA e no DOTA uma lesão hepática **não entra** na conta.
- Cada foco (≥ 0,3 mL, ajustável) tem volume, SUVmáx, SUVmédio, SUVpeak, TLG e **região**: próstata, osso (com o nome do osso: L3, 5º arco costal direito…), linfonodo pélvico (abaixo da crista ilíaca), linfonodo/partes moles extrapélvico ou víscera (pulmão, fígado…). Sai o **MTV** e a **TLG** totais.
- **No PSMA**: o **miTNM** (PROMISE: miT pela próstata, miN1 pélvico, miM1a extrapélvico, M1b osso — uni, oligo até 3 ou disseminado —, M1c víscera) e o **escore miPSMA** de cada foco pelas referências do exame: 0 abaixo do pool sanguíneo (aorta), 1 abaixo do fígado, 2 abaixo da parótida, 3 acima.
- Cada foco vira um achado em **Aplicações ▸ Achados de IA**. **Descartar** um foco (inflamação, músculo, gordura marrom, intestino…) tira ele do total: o texto do **laudo** soma só os confirmados e refaz o miTNM. A máscara fica numa SEG sobre o PET (série 987), um segmento por região.

São contas automáticas por limiar: confira cada foco antes de usar o número.

## Tarefas de IA: andamento e cancelar

As IAs do Ipê (órgãos abdominais, níveis da coluna, cefalometria, índices do crânio, níveis linfonodais, implante na mamografia) rodam pedidas à mão ou **sozinhas quando o exame chega** (Configurações ▸ CAD/IA). Uma por vez; as outras esperam na fila.

- **Tarefas de IA** mostra cada uma: exame, ferramenta, se foi automática ou à mão, situação (na fila, montando o volume, rodando, gravando, pronto, erro, cancelado), a etapa e o tempo. Abre pelo botão **Aplicações** do visualizador, por **Exibir ▸ Tarefas de IA**, e pelo aviso **⚙ IA: 1 rodando, 2 na fila** que aparece na barra de status enquanto há alguma ativa (um clique abre a janela).
- **Cancelar a escolhida** (ou **Cancelar todas**): na fila, ela não começa; rodando, o processo é derrubado e **nada é gravado** no exame. O cancelamento fica no histórico da gestão automática. A janela não é modal: dá para continuar trabalhando com ela aberta.
- **Fechar o exame não interrompe a IA pedida nele**: ela continua rodando e grava o resultado no exame, que aparece ao abrir de novo. Se o trabalho não parar em 15 segundos depois do Cancelar (por exemplo, o processo travou), a tarefa é fechada à força e o exame fica livre para as outras IAs. Com uma só tarefa ativa, Cancelar a escolhida funciona sem escolher a linha.
- **No banco de dados**, o exame que tem resultado de IA ganha **✦** ao lado do nome (a dica diz quais: "IA: órgãos abdominais, coluna"), e o que tem IA na fila ou rodando, **⚙**. A coluna **IA** (Colunas ▾) mostra as duas coisas por escrito.
- **Órgãos abdominais** no visualizador: botão **Órgãos** (TC/RM de abdome ou pelve; nos outros exames, pelo botão **Aplicações**) ▸ *Segmentar órgãos abdominais desta série (IA)*. Grava as máscaras e a tabela de volumes no exame.

### Instalar a segmentação (TotalSegmentator)

As IAs de órgãos, coluna, cabeça e pescoço, nódulos e crânio rodam num ambiente Python à parte, instalado uma vez por **Configurações ▸ CAD/IA ▸ Instalar a segmentação de órgãos (TotalSegmentator)…**. Dá também para rodar o instalador fora do Ipê: o arquivo `instalar_segmentacao.bat` fica na pasta do programa, dentro de `_internal\ipe` (na versão do código-fonte, na pasta do projeto). Precisa de internet e de uns 5 GB.

**A janela da instalação.** A instalação (a da segmentação e a dos modelos extras) roda numa janela do próprio Ipê, que não trava o programa: no alto aparecem o passo atual e o tempo decorrido; no meio, tudo o que o instalador escreve, com as linhas de erro em vermelho. No fim a janela volta para a frente com o veredito — **Instalado sem erros**, **terminou com erros** ou **NÃO ficou instalado** — conferido de verdade (o ambiente foi criado? os modelos estão na pasta?), não só pelo que o instalador disse. **Copiar tudo** e **Salvar…** servem para mandar a saída a quem dá suporte; o texto também fica em `instalacao_ia.log`, na pasta dos logs (**Abrir a pasta do log**). Fechar a janela no meio pergunta se é para interromper ou só esconder; escondida, ela volta pelo mesmo menu.

O instalador procura um Python de 3.10 a 3.13 que **abra de verdade** (um Python quebrado ou o atalho da Microsoft Store não contam) e, se não houver, baixa um Python 3.12 só para a segmentação. No começo ele lista os Pythons do computador. As variáveis PYTHONHOME e PYTHONPATH do Windows, que fazem qualquer Python quebrar com *No module named 'encodings'*, são ignoradas e aparecem como aviso. Um ambiente antigo que não abre é apagado e refeito; se a pasta estiver presa, ele a renomeia. O **Visual C++ Redistributable** da Microsoft (x64) só é preciso para a segmentação, por causa do PyTorch; o Ipê e o Python não precisam dele. O instalador do Ipê confere se ele existe e, faltando, oferece abrir o download (https://aka.ms/vs/17/release/vc_redist.x64.exe), e Configurações ▸ CAD/IA ▸ Instalar a segmentação avisa o mesmo. Depois de instalar o PyTorch, o instalador da segmentação confere se ele abre; se não abrir (no Windows, o erro *WinError 126 … shm.dll*), quase sempre falta o **Microsoft Visual C++ Redistributable**, e o instalador o baixa da Microsoft e instala (o Windows pode pedir permissão de administrador e, às vezes, reinício). Se ainda assim falhar, instale o Python 3.12 de python.org (marcando *Add python.exe to PATH*) e rode de novo. Se a falha for de rede (mensagens com *connection*, *timeout*, *SSL* ou *proxy*), libere download.pytorch.org, pypi.org e files.pythonhosted.org.

## Achados de IA e nódulos pulmonares

As IAs que **apontam** alguma coisa (a primeira é a de nódulos pulmonares) não escrevem no laudo: cada candidato vira um **achado sugerido**, revisado um a um na janela **Achados de IA** (botão **Aplicações** ▸ *Achados de IA…*, ou o menu do botão **Nódulos**).

- Cada linha diz o rótulo (N1, N2…), o tipo, o local, as medidas, o **estado** — *sugerido* (âmbar), *confirmado* (verde), *corrigido* (azul) ou *descartado* (cinza) — e quem revisou e quando. Embaixo, de onde veio: o modelo e a versão, a série usada e os avisos (corte grosso, por exemplo).
- **Ir até** (ou duplo clique) leva o quadro com a série usada pela IA ao corte do achado, com o cursor 3D em cima.
- **Confirmar**, **Descartar**, **Voltar a sugerido**. **Corrigir…** abre os números para você trocar (diâmetro, volume, consistência) e uma observação; o achado fica *corrigido* e o laudo leva os seus números.
- **Acompanhar como lesão** (só no confirmado ou corrigido): cria a lesão no acompanhamento ("N1 (IA)", com o lobo como local) e uma medida — um círculo do diâmetro, com o volume — no corte do achado. Daí em diante ele entra no seguimento e no tempo de duplicação, como qualquer lesão.
- **Mandar ao laudo** leva só os confirmados e os corrigidos, uma frase por achado ("Nódulo sólido no lobo inferior direito, diâmetro médio de 6,2 mm e volume de 120 mm³ (N1)."). Sem laudo aberto, o texto vai para a área de transferência.
- Rodar a IA de novo troca só os **sugeridos**. O que você já revisou fica, com o rótulo dele, e não volta como sugestão (o candidato a menos de 5 mm, ou de meio diâmetro, de um achado revisado é o mesmo achado).

**Nódulos pulmonares** (botão **Nódulos**, na TC de tórax; ou Configurações ▸ CAD/IA ▸ Nódulos pulmonares, para rodar sozinho quando o exame chega). Usa a tarefa aberta *lung_nodules* do TotalSegmentator (modelo da BLUEMIND AI, treinado em 1353 TCs, parte do LIDC-IDRI) e os lobos da tarefa *total*. Em cada candidato:

| Número | Como sai |
|---|---|
| Diâmetro maior e eixos | os três eixos perpendiculares da máscara |
| Diâmetro médio | média dos dois maiores eixos (o "diâmetro médio" do Fleischner e do Lung-RADS) |
| Volume | voxels × volume do voxel |
| HU médio e parte sólida | média do HU; parte sólida = voxels a partir de −300 HU |
| Consistência (pelo HU) | proposta: ≥ 80% sólido, ≤ 20% vidro fosco, no meio parcialmente sólido |
| Lobo | o lobo do centro (ou o mais perto, até 10 mm) |

Candidatos menores que o **diâmetro mínimo** (3 mm de fábrica, da esfera de mesmo volume) não entram; ficam no máximo os 30 maiores. A série preferida é a de pulmão de cortes finos; cortes acima de 2,5 mm geram aviso (o Fleischner pede até 1,5 mm para nódulos pequenos). A consistência pelo HU é proposta: em nódulo de poucos milímetros o volume parcial baixa o HU, e um nódulo sólido pode parecer vidro fosco. A SEG "Nódulos pulmonares · TotalSegmentator" fica no exame, um segmento por candidato.

Para quem já tinha instalado a segmentação: rode de novo o *instalar_segmentacao* para baixar os modelos *lung_nodules* e *total* (ou eles baixam sozinhos na primeira vez, com internet).

**Nódulo por clique e crescimento entre exames** (0.99.62). Na TC, botão direito no nódulo ▸ *Nódulo pulmonar aqui (segmentar por clique)…*. Não precisa da IA:

- A janela segmenta a partir do ponto: os voxels ligados acima do limiar (−500 HU, a parte sólida; marque *Incluir o vidro fosco* para −750 HU), numa caixa de 25 mm de raio. *Separar dos vasos e da pleura* faz uma abertura de 1 voxel, que corta a ponte fina entre o nódulo e o vaso. A máscara aparece por cima da imagem, em qualquer plano; se encostar na borda da caixa, a janela avisa que vazou.
- Os números são os mesmos dos candidatos da IA: diâmetro maior e médio, volume, HU médio, parte sólida, consistência pelo HU, eixos; e o lobo, quando o exame tem a segmentação dos lobos.
- **Guardar como achado** põe o nódulo na lista de Achados de IA, já **confirmado** (modelo "Ipê: segmentação por clique"). Rodar a IA de novo não o apaga. **Guardar e acompanhar como lesão** já o põe no acompanhamento.
- **O mesmo nódulo no exame anterior**: os nódulos confirmados ou corrigidos dos outros exames do paciente, levados a este pelo registro, até 10 mm. Sem registro entre os dois exames, vale o mesmo lobo e até 25 mm, marcado "provável, sem registro (confira)". A janela e a lista de Achados mostram o crescimento: diâmetro médio, volume e o **tempo de duplicação do volume** (TD = Δt · ln 2 / ln(V2/V1)).
- Se o nódulo anterior já estava no acompanhamento, *Acompanhar como lesão* põe a medida nova **na mesma lesão**. A tabela das lesões ganha a coluna do exame novo, com o tempo de duplicação. *Mandar ao laudo* acrescenta "Em relação ao exame de dd/mm/aaaa (N1): …".

**Composição corporal em L3 e atenuação hepática** (botão **Composição**, na TC de abdome; ou automático em Configurações ▸ CAD/IA ▸ Composição corporal). Os números aparecem como dois achados na mesma janela — "Composição corporal (L3)" e "Atenuação hepática" —, para conferir, corrigir e mandar ao laudo como os outros.

- **Onde mede**: o corte axial do meio craniocaudal da vértebra L3 (achada pelo TotalSegmentator). A série tem de ser axial; se não for, a composição não sai (o fígado sai assim mesmo). *Ir até* leva ao corte de L3, e a SEG "Composição corporal · TotalSegmentator" mostra os quatro compartimentos nele.
- **Como separa** (limiares clássicos, Mitsiopoulos et al., 1998): músculo de −29 a 150 HU fora da cavidade abdominal, dos órgãos e da vértebra; gordura de −190 a −30 HU — visceral dentro da cavidade (tarefa aberta *trunk_cavities*), subcutânea nas regiões de gordura que encostam na pele, intermuscular o resto. A pele (3 mm de fora) não conta como músculo.
- **Saem**: área muscular (SMA, cm²), densidade muscular (HU médio do músculo), gordura visceral, subcutânea e intermuscular (cm²) e VAT/SAT. Com a altura, o **índice muscular** (SMA/altura², cm²/m²), com a referência de sarcopenia do sexo do paciente ao lado — Prado et al., Lancet Oncol 2008: < 52,4 (homens) e < 38,5 cm²/m² (mulheres) —, como texto, não veredito. Com o peso, o **IMC** e as referências de Martin et al., J Clin Oncol 2013, que dependem dele: sarcopenia com índice < 43 cm²/m² em homens com IMC < 25, < 53 com IMC ≥ 25 e < 41 em mulheres; mioesteatose com densidade muscular < 41 HU (IMC < 25) ou < 33 HU (IMC ≥ 25).
- **Altura, peso e sexo** (0.99.80): ao clicar para calcular, abre uma janela com o que veio do arquivo (PatientSize, PatientWeight, PatientSex) para conferir ou digitar; *Cancelar* não calcula. O digitado vale para aquele exame (o arquivo não muda) e é usado de novo se a IA rodar outra vez. Depois do cálculo, **Achados de IA ▸ Altura e peso…** troca os valores e refaz o índice, o IMC e as referências sem rodar a IA. A caixa *Perguntar sempre antes de calcular* desliga a janela; para religar, marque a caixa de novo em *Altura e peso…*.
- **Fígado e baço**: média e mediana do HU (a borda, 2 voxels, fica de fora), fígado − baço e fígado / baço. Na TC sem contraste vêm as referências como texto, as duas 100% específicas para esteatose de 30% ou mais na biópsia — fígado − baço < −9 HU ou fígado / baço < 0,8 (Park et al., Radiology 2006) e fígado < 48 HU (Pickhardt et al., Eur Radiol 2012). Com contraste (pela tag ContrastBolusAgent ou pela descrição da série) a tela avisa que esses limiares não valem.
- **Resultado da esteatose** (0.99.80), que aparece embaixo da lista em Achados de IA e vai ao laudo junto com os números:
  - *Compatível com esteatose moderada a acentuada (≥ 30%)*, quando um dos critérios acima bate;
  - *Esteatose leve possível*, quando o fígado está menos denso que o baço (fígado / baço < 1,0) sem bater nenhum;
  - *Sem sinais tomográficos de esteatose moderada ou acentuada*, senão — a TC não exclui a leve;
  - *Não classificado* na série com contraste.
  
  Se você corrigir o HU do fígado ou do baço, o resultado acompanha; em *Corrigir…* dá para escrever outro resultado.
- Rode de novo o *instalar_segmentacao* para baixar o modelo *trunk_cavities*.

**Gordura e ferro hepáticos na RM** (botão **Fígado**, na RM de abdome; ou automático em Configurações ▸ CAD/IA ▸ Gordura e ferro hepáticos). O fígado, o baço e os segmentos de Couinaud vêm do TotalSegmentator (*total_mr* e *liver_segments_mr*), rodado numa série anatômica axial do abdome (de fábrica, o "WATER" do LAVA/Dixon; a da pelve fica de fora); a máscara é levada ponto a ponto, pela posição no paciente, para a grade de cada mapa — que costuma ser mais grossa (no IDEAL IQ do acervo, cortes de 16 mm a cada 8 mm). A borda do fígado (1 voxel no plano) fica de fora. Saem até três achados, na janela Achados de IA:

| Achado | De onde | Números |
|---|---|---|
| Gordura hepática (PDFF) | o mapa de fração de gordura do aparelho (IDEAL IQ, mDIXON Quant, LiverLab), reconhecido pela ImageType FAT_FRACTION ou pela descrição | mediana, média, p25 e p75 (%), e a mediana de cada segmento |
| Ferro hepático (R2*) | o mapa de R2* (ou de T2*, convertido: R2* = 1000 / T2*) | R2* mediano (s⁻¹), T2* (ms), R2* do baço; a 1,5 T, o ferro estimado |
| Gordura hepática (dupla eco) | a dupla eco em fase / fora de fase (as duas ecos na mesma série, ou o par InPhase/OutPhase) | fração de **sinal** de gordura = (EF − FF) / (2 · EF), e a razão EF/FF |

- **Ferro estimado**: LIC = 0,0254 · R2* + 0,202 mg Fe/g de peso seco (Wood et al., Blood 2005), calibração de 1,5 T. **A 3 T** (0.99.50) o R2* do fígado é dividido por 2,05 para o equivalente a 1,5 T (Alam et al., JCMR 2016: o R2* hepático a 3 T foi 105% maior) e então entra na fórmula de Wood; o achado mostra também esse R2* equivalente. A 3 T o T2* muito curto mede pior: em sobrecarga grave, prefira 1,5 T. Em outro campo (ou sem o campo no arquivo) não estima.
- **Faixa do LIC** (texto de referência, não veredito): 3,2–7 leve, 7–15 moderada, > 15 mg Fe/g grave.
- **Referência da gordura**, como texto: PDFF ≥ 6,4% grau ≥ 1, ≥ 17,4% grau ≥ 2, ≥ 22,1% grau 3 — limiares de alta especificidade em doença hepática gordurosa (Tang et al., Radiology 2015).
- A fração de sinal da dupla eco **não é PDFF**: não corrige T1 nem T2*. Em fase com sinal menor que fora de fase sugere ferro — e aí a gordura sai subestimada.
- Mapa de gordura em 0–1000 (alguns fabricantes) é lido como décimos de porcento, com aviso. À mão continua valendo: uma ROI no próprio mapa mostra a média em % (ou em s⁻¹ no de R2*).

### Enfisema por lobo (0.99.77)

Na TC de tórax, o botão **Enfisema** (ou Aplicações ▸ Enfisema) separa os cinco lobos pela IA e mede, em cada lobo, em cada pulmão e no total, a **%LAA−950** (fração do volume abaixo de −950 HU), o **Perc15** (o HU do percentil 15) e o volume, e diz a distribuição (predomínio superior, inferior ou homogêneo). O resultado vai para os Achados de IA, como um achado "Enfisema (%LAA−950)", e as áreas abaixo de −950 HU ficam numa SEG que aparece só na série calculada.

O número depende da técnica, e a revisão avisa: corte fino (≤ 1,5 mm), filtro suave (B30, STANDARD; filtro de pulmão ou osso aumenta o ruído e a %LAA), sem contraste e em inspiração plena; a mediana do ar da traqueia confere a calibração (perto de −1000 HU). Use de preferência a série fina de filtro suave, se houver. A referência (limiar de −950 HU validado por Gevenois et al., 1996; %LAA acima de ~5–6% costuma ser tratada como enfisema relevante) vai como texto ao lado, não como veredito.

### Fratura vertebral — Genant (0.99.77)

Na TC ou na RM com a coluna torácica ou lombar, o botão **Genant** (ou Aplicações ▸ Genant) nomeia as vértebras (a mesma regra da Coluna, com a IA em resolução cheia), mede a altura anterior, média e posterior de cada corpo e calcula a perda de altura: **cunha** (anterior contra posterior), **bicôncava** (média contra posterior) ou **esmagamento** (posterior contra a média das duas vizinhas). De T4 a L5, 20–25% é grau 1 (leve), 25–40% grau 2 (moderada) e mais de 40% grau 3 (acentuada), pela classificação semiquantitativa de Genant (1993).

Cada vértebra com grau 1 ou mais vira um achado "Fratura vertebral (Genant)" para confirmar, corrigir ou descartar — deformidade não é sinônimo de fratura (variante, Scheuermann, nódulo de Schmorl, degeneração), então confira na sagital. Um achado de resumo diz quantas vértebras foram medidas; confirmado sem alteradas, ele entra no laudo como "corpos vertebrais sem redução de altura de 20% ou mais". Vértebra já revisada não volta como sugestão quando a IA roda de novo.

### Lesões hepáticas e carga por segmento (0.99.82)

Na TC ou na RM de abdome, o botão **Lesões** (ou Aplicações ▸ Lesões hepáticas) roda duas tarefas abertas do TotalSegmentator — os oito segmentos de Couinaud e as lesões focais do fígado — e mede:

- para cada lesão (até 20, as maiores): volume, maior diâmetro axial, HU médio (TC) e o segmento onde está a maior parte dela; cada uma vira um achado "Lesão hepática" para confirmar, corrigir, descartar ou ligar a uma lesão do acompanhamento;
- no resumo: número de lesões, volume total, **carga** (% do volume do fígado ocupada por lesão), volume do fígado e a carga de cada segmento.

O modelo não diz o que a lesão é (cisto, hemangioma, metástase): é contagem e volume. Funciona melhor em fase com contraste (portal ou hepatobiliar) e corte fino; a revisão avisa quando não é o caso. As máscaras (lesões e segmentos) ficam numa SEG que aparece só na série calculada e no 3D, em *Estruturas*.

### Cálcio coronariano — Agatston (0.99.89)

Na TC **sem contraste** (escore de cálcio ou TC de tórax), o botão **Cálcio** (ou Aplicações ▸ Cálcio coronariano) mede o escore de Agatston:

- **Órgãos**: o TotalSegmentator acha o coração, a aorta e os ossos do tórax (esterno, cartilagens costais, costelas, vértebras). O cálcio é procurado em volta do coração, com 8 mm de margem, que é onde correm as coronárias; o osso fica de fora.
- **Agatston**, corte a corte: pixel ≥ 130 HU, lesão de pelo menos 1 mm² num corte, peso pelo HU máximo (130–199 = 1, 200–299 = 2, 300–399 = 3, ≥ 400 = 4), escore = área × peso × espessura ÷ 3 mm. Sai também o **volume** (mm³). Cortes finos (até 2 mm) são **somados em fatias de ~3 mm** (média dos HU), como a reconstrução em que o escore foi definido: corte fino aumenta o escore. Limiar, menor lesão e a soma dos cortes ficam em Configurações ▸ CAD/IA ▸ Cálcio coronariano.
- **Vaso sugerido** de cada lesão, pela posição: perto da raiz da aorta e à esquerda dela, **TCE**; em volta do coração, anterior e à esquerda **DA**, à esquerda e atrás **CX**, à direita e posteroinferior **CD**. A tarefa das coronárias do TotalSegmentator exige licença, então o vaso é uma sugestão: confira na SEG (uma cor por vaso) e corrija.
- **Fora do escore coronariano**, à parte: o cálcio encostado na **aorta** (inclui a raiz e a valva aórtica) e o que está mais de 5 mm **dentro do coração** (valva, anel mitral).
- **Resultado**: o Agatston e o volume totais e por vaso, o **CAC-DRS** (A0 = 0, A1 = 1–99, A2 = 100–299, A3 ≥ 300, com N = número de vasos com cálcio) e a categoria da SCCT/STR para TC de tórax (nenhum, leve, moderado, grave).
- **Achados de IA**: um resumo e um achado por vaso. Para mudar uma lesão de vaso, corrija o Agatston dos dois vasos; descartar um vaso tira ele do total. O texto do laudo refaz o total, o CAC-DRS e a categoria com os vasos confirmados ou corrigidos.

Avisos: com contraste o escore **não é medido** (o sangue passa de 130 HU); TC sem sincronização com o ECG (o movimento subestima o escore); kV diferente de 120; corte fino sem somar ou corte grosso. O percentil por idade e sexo (MESA) não é calculado.

### Aorta: diâmetro por segmento (0.99.90)

Na TC de tórax ou de abdome, com ou sem contraste, o botão **Aorta** (ou Aplicações ▸ Aorta) mede o diâmetro da aorta **perpendicular ao eixo**, de forma automática:

- **Linha central**: o TotalSegmentator acha a aorta e os marcos (tronco braquiocefálico, subclávia esquerda, T12, rins). O programa traça a linha pelo meio da aorta, da raiz (quando a série pega o coração) até a bifurcação ou o fim da série, e a ajusta ao centro de cada corte perpendicular.
- **Planos perpendiculares** a cada 2 mm: em cada um, o **diâmetro máximo**, o **perpendicular** a ele e o diâmetro pela área.
- **Segmentos** e o maior diâmetro de cada um: **raiz** (os primeiros 15 mm), **ascendente** (até o tronco braquiocefálico), **arco** (até 10 mm depois da subclávia esquerda), **descendente torácica** (até a borda de baixo de T12), **abdominal suprarrenal** (até o meio dos rins) e **infrarrenal**. Sem os ramos do arco, o arco é o trecho de 30 mm de cada lado do ponto mais alto; numa série só do abdome saem só os segmentos abdominais.
- **Achados de IA**: um resumo e um achado por segmento; clicar leva ao ponto do maior diâmetro. A SEG pinta cada segmento de uma cor. O texto do laudo leva os segmentos confirmados ou corrigidos ("Aorta ascendente: diâmetro máximo 46 × 45 mm, perpendicular ao eixo, parede externa").

A medida é **da parede externa à externa** (a máscara pega a parede e o trombo). A ACC/AHA (2022) pede a raiz e a ascendente de borda interna a interna, em TC sincronizada com o ECG; sem ECG, a raiz não vale. As referências aparecem como texto no achado, nunca como veredito: ascendente, arco e descendente ≥ 40 mm costumam ser relatados como dilatação, e ≥ 55 mm é o limiar de cirurgia (ACC/AHA 2022); na infrarrenal, aneurisma é ≥ 30 mm, com o intervalo de controle do ACR (2013) para o tamanho medido.

### Modelos extras: MedSAM2, autoPET, BraTS, FLAMeS e medula

Cinco IAs que não vêm com a segmentação e se instalam uma vez, com internet, em **Configurações ▸ CAD/IA ▸ Instalar os modelos extras (MedSAM2, autoPET, BraTS, FLAMeS, medula)…** (a janela diz o que já está pronto e o que falta). Rodam no mesmo ambiente do TotalSegmentator, em CPU.

- **Segmentar pela caixa (MedSAM2).** Ferramenta do botão esquerdo (*Ferramenta do botão esquerdo ▸ Medir*): desenhe uma caixa em volta da lesão num corte da série original. O MedSAM2 faz o contorno nesse corte e o propaga para cima e para baixo (até 60 cortes de cada lado); fica só a parte contígua ao corte da caixa. A janela que entra no modelo é a da tela — ajuste a janela para a lesão aparecer bem antes de desenhar. O resultado abre na janela da **Segmentação 3D** (método *IA: contorno pela caixa*), com volume, eixos, SUV no PET, ligar a uma lesão do acompanhamento e gravar a SEG. Serve para TC, RM e PET.
- **autoPET (lesões no PET-FDG).** Botão **autoPET** (ou Aplicações ▸ autoPET) no PET de um PET/CT: o nnU-Net do desafio autoPET II acha as lesões ávidas (deixa de fora a captação fisiológica de cérebro, coração, rins e bexiga) usando o PET em SUV e a TC do mesmo exame reamostrada na grade do PET. Sai o **MTV** (volume metabólico total), a **TLG** e o SUVmáx, e cada lesão (até 20) com volume, SUVmáx, SUVmédio, SUVpeak e TLG, como achado para conferir — descarte a captação fisiológica que escapar. Precisa do fator de SUV (peso, dose e horários no arquivo).
- **BraTS (glioma na RM).** Botão **BraTS** na RM de crânio com T1 pós-contraste, T1, T2 e FLAIR: o programa acha as quatro pela descrição, registra a T1, a T2 e a FLAIR na T1 pós (registro rígido), tira o crânio (encéfalo do TotalSegmentator) e o SegResNet do MONAI separa a parte **captante**, a **necrose** e o **edema**, com os volumes e o maior diâmetro axial da parte captante. Um achado para conferir; a revisão avisa quando o registro ficou com semelhança baixa. É o modelo de exemplo do MONAI, treinado no BraTS 2018 — confira cada parte.
- **FLAMeS (lesões de substância branca no FLAIR).** Botão **Lesões SB** na RM de crânio: o programa acha o FLAIR do exame (o de mais cortes; o "T1 FLAIR" não serve), tira o crânio com o SynthSeg e o FLAMeS marca as lesões hiperintensas. Sai um achado com o **número de lesões**, o **volume total**, a contagem por região — **periventriculares** (encostam num ventrículo lateral), **justacorticais/corticais** (encostam no córtex), **infratentoriais** (tronco e cerebelo) e **profundas** — e a maior lesão. Se um exame anterior do mesmo paciente já passou pela ferramenta, o achado e a frase do laudo trazem a comparação de número e volume (não é pareamento lesão a lesão). As lesões ficam na série **Lesões no FLAIR · FLAMeS**, coloridas por região. Modelo de pesquisa feito para esclerose múltipla e para FLAIR 3D: marca qualquer hipersinal da substância branca, sem distinguir a causa, e perde lesões pequenas em FLAIR 2D espesso (o programa avisa). O download é de 2,4 GB; em CPU a análise leva vários minutos.
- **Medula e canal (TotalSpineSeg).** Botão **Medula** na RM da coluna (de preferência o sagital T2; serve qualquer contraste e orientação): o TotalSpineSeg segmenta a medula, o canal, os discos e as vértebras, já com o nome de cada nível. O Ipê traça a linha central da medula e mede em cada disco, no **plano perpendicular à medula**: a **área**, o diâmetro **anteroposterior** e o **transverso**, a **razão de compressão** (AP ÷ transverso), o AP do **canal**, a ocupação do canal pela medula e os índices **MSCC** e **MCC** (Fehlings 1999: 1 − diâmetro no disco ÷ média dos diâmetros nos meios dos corpos de cima e de baixo). Cada disco é um achado para conferir; o resumo diz o nível de maior MSCC. A medula e o canal ficam na série **Medula e canal · TotalSpineSeg**. Em sagital 2D de 3–4 mm, a área e o transverso são aproximados (o programa avisa); o AP, o MSCC e o MCC valem. Confira sempre o nome dos níveis. O TotalSpineSeg é instalado num **ambiente só dele** (cerca de 1 GB) e baixa o modelo (2 GB) no primeiro uso; precisa de uns **8 GB de memória livres** e leva vários minutos em CPU.

## CAD, IA e anotações de outros sistemas

O botão **CAD/IA** reúne o que outro programa escreveu sobre o exame: SEG (segmentações), GSPS (anotações gráficas do aparelho ou da estação), SR (achados de CAD/IA) e RTSTRUCT (contornos de radioterapia). O número no botão diz quantos objetos o exame tem; o menu lista um por um, com *Ir para a imagem* de cada achado.

**Em qualquer plano.** Segmentações (SEG, inclusive as do TotalSegmentator: órgãos, cefalometria), contornos (RTSTRUCT), níveis da coluna, lesões segmentadas e linhas de medida automática aparecem também quando o quadro é reformatado (MPR sagital, coronal, oblíquo) ou noutra série do mesmo exame em outro plano: a máscara guardada corte a corte é empilhada num volume em milímetros e cortada pelo plano do quadro. **Exceção (0.99.65):** os órgãos abdominais e os níveis linfonodais aparecem só na série em que foram calculados (e nas reconstruções dela): em outra série o paciente já se mexeu, e a mesma posição em milímetros não cai no mesmo lugar. O que é só 2D (mamografia, CAD de mamografia, anotações gráficas presas a uma imagem) continua só na imagem de origem.

**Quanto tempo a abertura leva, e onde.** Cada exame aberto deixa uma linha no registro (`Logs\dicomviewer.log`, na pasta de dados), por exemplo *Abertura (MG MAMOGRAFIA DIGITAL): primeira imagem em 0,84 s — banco 0,02 · barra 0,21 · tira 0,05 · protocolo 0,30 · janela 0,03 · estado 0,04 · imagem 0,19*, e uma segunda quando as sobreposições de IA terminam de entrar. É o que dá para mandar quando a abertura parecer lenta. As imagens em JPEG-LS (a compressão sem perda do Ipê, que guarda toda a mamografia) são lidas pelo decodificador CharLS, cerca de duas vezes mais rápido que o anterior numa mamografia, e os decodificadores e módulos da abertura são carregados alguns segundos depois que o programa abre, para o primeiro exame não pagar por eles.

**SEG grandes abrem em segundo plano.** Uma SEG de órgãos do TotalSegmentator tem milhares de quadros. O exame abre primeiro, com a imagem na tela, e a SEG é lida à parte; a barra de status mostra *Lendo as segmentações de IA do exame…* e as cores entram em um ou dois segundos. Reabrir o mesmo exame na mesma sessão do Ipê é imediato: a SEG já lida fica guardada na memória (até ~800 MB de máscaras) enquanto o arquivo não mudar.

**Ler antes, ver o CAD depois.** Em Configurações ▸ CAD/IA, *Ler antes, ver o CAD depois* faz as marcas de CAD (o CAD de mamografia e outros CAD SR) começarem **ocultas** em cada exame. Leia o exame e use **CAD/IA ▸ Revelar o CAD** (ou a tecla do atalho *Revelar o CAD*): as marcas aparecem e a barra de status diz quanto tempo de leitura houve antes. As outras sobreposições (SEG, as IAs do Ipê) não mudam.

Clicar no botão mostra ou oculta todos. A escolha fica guardada por tipo: se você desligou as segmentações de uma IA, elas nascem ocultas nos próximos exames — e as anotações que o técnico deixou no aparelho continuam aparecendo. Quando algo nasce oculto, a barra de estado avisa quantos estão escondidos.

## Estruturas: editar máscaras (SEG / RTSTRUCT)

Botão **3D** ▸ *Estruturas: editar máscaras* (ou o menu do botão **CAD/IA**). Abre uma janela, ao lado do visualizador, para **corrigir e organizar** as máscaras do exame — a lesão que a segmentação 3D ou a captura da dinâmica pegou com um vaso junto, o órgão que a IA contornou mal — e gravá-las no exame.

![O painel Estruturas: a lista, o pincel, os limites da edição e as correções (crescer, encolher, buracos, interpolar).](estruturas_painel.png){60}

- **Série de referência**: a do quadro ativo quando a janela abre. As estruturas são guardadas na grade dela, mas aparecem em **todas as séries e planos** do exame, e o pincel pinta em qualquer quadro do exame, no plano que está na tela (inclusive MPR).
- **Lista**: para cada estrutura, *Ver* (mostrar/ocultar; duplo clique muda a cor), nome (editável), tipo (lesão, órgão, outro), volume em mL, *Travada* e de onde veio. Embaixo, os números da escolhida: volume, voxels, cortes, os três eixos, média ± desvio, mínimo, máximo, **mediana, percentis 10 e 90, assimetria, curtose, entropia e uniformidade** (as definições do pyradiomics/IBSI), **maior diâmetro (Feret), esfericidade, alongamento e achatamento**, e quantas ilhas separadas ela tem. **Copiar os números** põe uma linha por estrutura, separada por tabulação, na área de transferência — cola direto na planilha. A esfericidade é calculada pela malha da superfície; em estrutura pequena (raio de menos de uns 10 voxels) ela é aproximada.
- **Nova** cria uma estrutura vazia; **Importar do exame** traz uma lesão guardada, um segmento de SEG (inclusive os da IA: órgãos, cefalometria, implante), um contorno de RTSTRUCT — ou todos. Enquanto a cópia é editada, o original sai da tela; volta ao fechar.
- **Pincel / Borracha** (botão esquerdo; o direito continua com zoom/pan): o círculo em volta do mouse é o tamanho do pincel (*Raio*, em mm). Por padrão é um disco no plano da tela (só o corte que se vê); **Esfera 3D** pinta também os cortes vizinhos. **Só na faixa do clique ±** pinta só os voxels de intensidade parecida com a do ponto onde o traço começa (a faixa é em % da faixa de intensidades da série): o pincel não sai da lesão para a gordura. O pincel nunca pinta por cima de uma estrutura **travada** — trave o órgão e pinte a lesão encostada nele.
- **Limites da edição** (valem para o pincel, crescer, preencher buracos e interpolar — o que *entra* na estrutura; apagar não é limitado): **Área** em toda parte, *só dentro de* uma estrutura (pinte a lesão sem sair do órgão) ou *só fora das outras* visíveis; **Só intensidades entre** mín e máx (nada entra fora da faixa, em nenhuma ferramenta); **Sobrescrever as outras**: o que a estrutura ganha sai das outras não travadas (cada uma guarda o seu desfazer) — sem isso, as estruturas podem se sobrepor.
- **Corrigir a estrutura escolhida**: **Crescer / Encolher** (margem em mm, numa bola com o espaçamento real; *só nos cortes* não passa para o corte de cima e de baixo); **Só a maior ilha** e **Tirar ilhas menores que** N mL; **Preencher buracos** (corte a corte); **Interpolar cortes** — desenhe a cada 3 ou 4 cortes e os cortes vazios entre dois desenhados saem pela forma intermediária; **Aparar fora de** (tira os voxels com intensidade fora da faixa); **Unir com / Subtrair / Cruzar com** outra estrutura cria uma nova (por exemplo, *lesão menos necrose*). **Desfazer** e **Refazer** (Ctrl+Z / Ctrl+Y), por estrutura.
- **Gravar SEG**: todas as estruturas numa série *Estruturas (Ipe)* do exame, como DICOM SEG (máscara voxel a voxel, com o tipo de cada uma: lesão ou órgão). Vai ao PACS junto com o exame e abre no 3D Slicer e em outros visualizadores — e volta a aparecer aqui, pelo botão CAD/IA.
- **Gravar RTSTRUCT**: os contornos de radioterapia, corte a corte, que o sistema de planejamento lê direto. O contorno segue a borda dos pixels (preenchido pelos centros, como os planejadores fazem, dá a mesma máscara); um buraco vira um segundo contorno dentro do primeiro. Lesão sai como GTV, órgão como ORGAN.
- **Atualizar a lesão guardada**: para a estrutura que veio de uma lesão segmentada, a medida passa a ter a máscara, o volume e os eixos corrigidos — e é esse volume que o acompanhamento de lesões usa.
- **Mandar ao laudo**: uma linha por estrutura, com o volume e os eixos.

Ao fechar com estruturas alteradas e não gravadas, a janela pergunta se grava como SEG.

> **Desenho gravado no pixel não é overlay.** Quando a IA grava o resultado como uma série de imagens novas, não há como desligá-lo: o caminho é **Ocultar** a série pelo botão direito na lista de séries.

## Fusão

Botão **Fusão**: sobrepõe uma série a outra no quadro ativo (PET sobre a TC, por exemplo), com opacidade, tabela de cores e limites mínimo e máximo, e a opção de ocultar o que está abaixo do mínimo.

![PET/CT fundido: o PET (em SUV, cor ferro quente) sobre a TC, com opacidade, cor e janela do PET na barra de cima.](pet_fusao.png)

**Fundir por arrastar** (0.99.64): arraste uma série da tira até o **canto inferior esquerdo** do quadro ("Fundir por cima") — ela entra como fusão, em cores e com transparência, em vez de trocar a série. Para fundir o que outro quadro mostra — um mapa da dinâmica (SER, realce, cinético…), uma fase, o ADC —, botão direito nele ▸ **Quadro ▸ Fundir este quadro sobre…** ▸ o quadro de destino (ADC sobre a T2, cinético sobre a DWI). A fusão usa as coordenadas do paciente: séries de referenciais diferentes ganham o aviso para conferir o alinhamento.

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

## T1 sintético de 1 mm (SynthSR)

Para os exames de crânio **sem T1 3D** (os protocolos de Parkinson costumam ter só 2D de 4–5 mm), em que o MPR sai em degraus. No botão **Índices**: **Criar T1 sintético de 1 mm desta série (IA, SynthSR)…**. A série do quadro ativo (qualquer contraste, orientação e espessura; de preferência um T1 ou um FLAIR) vai para o SynthSR, que devolve um volume isotrópico de 1 mm com contraste de T1. Em alguns minutos o exame ganha a série **T1 sintético 1 mm · SynthSR**, e o programa pergunta se mostra no quadro ativo.

A série nova está na mesma posição do paciente que a original: abre no **MPR**, sincroniza com as outras séries, e aceita as medidas guiadas (**MRPI e MRPI 2.0**, Evans, ângulo calosal) e os **índices automáticos**. Ela fica só neste computador (não é enviada ao PACS) e leva o selo de IA na miniatura.

**É imagem sintética.** A rede só conhece anatomia normal: lesões podem não aparecer ou mudar de aspecto, e o contraste é calculado, não adquirido. Use para **medir a anatomia** (distâncias, áreas, volumes); **nunca para procurar nem caracterizar lesão**, e confira as medidas contra as imagens originais. Com menos de 20 cortes na série de origem, ou a partir de TC, o resultado é pior, e o programa avisa.

Pelo navegador, a ferramenta aparece na aba **IA** como **T1 sintético de 1 mm (IA, SynthSR)**. Automático na chegada: **Configurações ▸ CAD/IA ▸ T1 sintético (SynthSR)…**; nesse modo só roda em exames de crânio que não têm nenhuma série fina (até 1,5 mm). O modelo (53 MB) é baixado uma vez, pelo instalar_segmentacao ou no primeiro uso.

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

**Identificar vértebras e discos desta série** (na seta do botão **Genant** da barra — ou do botão **Aplicações** —, ou no botão direito da série no banco, numa TC ou RM da coluna) dá nome a cada vértebra e disco. Os nomes aparecem em qualquer série e plano do exame.

![RM lombar com os níveis da coluna marcados pela segmentação, incluindo a vértebra de transição (S1 lombarizada).](rm_coluna_niveis.png)

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

![Configurações ▸ Visualizador ▸ Barra e aplicações: em que exames cada aplicação aparece na barra.](config_barra.png){75}

**Clicar no nome do grupo** (Visualizador, Protocolos de exame, CAD/IA, Laudos…) abre uma janela só daquele grupo, com as etapas dele numa lista à esquerda: as páginas de preferências aparecem ali mesmo e são gravadas juntas no OK; as que têm janela própria (Barra de ferramentas, Nós DICOM…) mostram um botão **Abrir…**. Clicar num item do submenu continua abrindo só aquele item.

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
- **Botão direito no exame ▸ Organizar ▸ Banco**: *Mover para o meu banco (pessoal)*, *Mover para o compartilhado*, *Compartilhar com…* (escolher usuários) e, para o administrador, *Passar para o banco de…*. Tirar um exame do compartilhado esconde dos outros, por isso só quem configura o computador faz isso — para juntar casos, use as listas.
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

![Exportar: DICOM (com DICOMDIR e visualizador no navegador) ou imagens, com a anonimização das cópias.](exportar.png){65}

- **DICOM** — pasta, CD ou pendrive, com DICOMDIR e, se quiser, um visualizador que abre no navegador (completo, com medidas, valores, ROIs e MPR; ou leve). Pode sair compactado em .zip.
- **Imagens** — JPG ou PNG, com formato, qualidade, janela (a do arquivo ou a do quadro atual), intervalo e tamanho máximo.

A anonimização é opção da janela — e obrigatória para quem não tem a permissão de exportar com dados do paciente.

**Pacientes diferentes num pacote só**: exportar identificado, num CD/pendrive com visualizador ou num .zip, exames de pacientes diferentes pergunta antes, mostrando onde nome e ID não batem — é o pacote que se entrega a um paciente com o exame de outro dentro. Pasta solta, imagens JPG/PNG e cópias anonimizadas não perguntam (juntar casos para aula ou pesquisa é uso normal).

**Séries derivadas dizem de onde vieram**: toda série que o Ipê grava a partir de outra (reconstrução, MIP, mapa da dinâmica, captura) leva em *Derivation Description* a versão do programa e os parâmetros (plano, espessura e modo, passo, pixel, orientação e série de origem; no mapa, as fases e os limiares) e em *Source Image Sequence* as imagens de origem (até 300 por imagem, espaçadas por igual quando há mais — a descrição diz quantas de quantas).

### Anonimizar

Botão direito num exame — ou em vários — e **Ferramentas ▸ Anonimizar uma cópia deste exame…**. A janela abre já marcada para anonimizar, e há três destinos: DICOM, Imagens, ou **Cópia anonimizada no meu banco** — vira outro exame na lista, e nada sai da máquina.

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
- O registro entre exames é rígido (rotação e translação), não deformável.
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
