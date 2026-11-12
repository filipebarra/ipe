# Histórico de versões do Ipê

*O programa se chamou **DicomViewer** até a versão 0.99.10. [Voltar ao README](README.pt-BR.md) ·
[English](CHANGELOG.en.md) · [Español](CHANGELOG.es.md)*

## 0.100.21 — Navegador: linha de referência e arrasto entre janelas
- Com as janelas ligadas, o corte de uma janela aparece nas outras como **linha de referência** (tracejada), nos
  quadros de outro plano do mesmo exame.
- **Arrastar uma série** da tira de uma janela e soltar num quadro de outra janela, mesmo de outro exame.

## 0.100.20 — Navegador: lista com filtros rápidos e prévia; janelas ligadas
- **Lista**: filtros de um clique (período, modalidade, situação do laudo e da IA), selos de IA e de laudo em cada
  exame, e a **prévia** do exame selecionado à direita (séries, IA, laudo, anteriores) antes de abrir.
- **Janelas ligadas**: rolagem, janela/nível e zoom de uma janela de visualização seguem nas outras (no exame
  anterior, pelos mesmos milímetros).

## 0.100.19 — Navegador: aparência do usuário, modo leitura e configuração de monitores
- **Aparência**: séries à esquerda, embaixo ou em cima; botões em cima ou numa coluna à esquerda; **modo leitura**
  (só as imagens, tecla F). O painel da direita vem recolhido. Guardado no navegador.
- **Monitores**: configuração guardada no navegador, como no Ipê — a ordem das janelas, o que cada uma apresenta (o
  exame ou o exame anterior), o layout e o monitor de cada uma.

## 0.100.18 — Navegador: várias janelas (uma por monitor), celular e tablet
- **Janelas de visualização**: a lista numa janela e os exames em 1, 2 ou 3 janelas separadas, uma por monitor, para
  qualquer exame. As janelas ficam abertas à espera do próximo exame e lembram a posição; na mamografia, a 2ª janela é a
  segunda tela do protocolo.
- **Celular e tablet**: lista em cartões, uma imagem por vez, painéis em gavetas, barra que rola; um dedo faz a função
  da barra (rolar os cortes), dois dedos ampliam e deslocam.
- **Login no celular**: depois de entrar, voltava para o login. A sessão agora fica na aba (sobrevive ao recarregamento
  que o celular faz sozinho), o teclado não põe maiúscula no usuário, e uma falha do motor de imagens não impede mais
  a entrada. Os erros do navegador passam a ir para o registro do servidor.

## 0.100.17 — Mamografia no navegador: o mesmo zoom em toda a pilha
- Ao rolar para outra imagem da incidência (outra 2D, a tomo), o zoom não acompanhava, e ao voltar não era mais o da
  abertura. O navegador não lia o tamanho do pixel da mamografia (ImagerPixelSpacing; na tomo, grupos funcionais) e
  remedia o enquadramento a cada troca, somando erro. Agora o servidor informa o tamanho do pixel e o enquadramento
  da abertura da etapa (ou o seu zoom à mão) é aplicado a cada imagem, como se estivessem empilhadas.
- Publicação no GitHub: ações atualizadas (Node 24) e a versão só é montada depois de o código novo chegar.

## 0.100.16 — Navegador: revisar os achados de IA
- **Achados para revisar** na aba IA do navegador (enfisema, nódulos, Genant, cálcio, aorta, carga tumoral PET,
  composição corporal): Ir até, Confirmar, Corrigir os números, Descartar, Voltar a sugerido e **Mandar ao laudo** (só
  os confirmados e corrigidos). A mesma lista do Ipê; precisa da permissão de escrever laudos.
- "Ir até" e as linhas de referência do navegador acham o corte certo mesmo com a série ainda chegando.

## 0.100.15 — Navegador: Fechar, a busca volta, IA na mesma sessão
- Com o exame aberto, o botão do canto de cima é **Fechar** (em inglês, *Close*; em espanhol, *Cerrar*); na lista
  continua **Sair**.
- **A busca volta**: fechar o exame volta à lista com a busca e os filtros que estavam, com o exame aberto marcado.
- **IA na mesma sessão**: ao terminar uma tarefa de IA, as séries novas entram na tira, a SEG entra no menu (e já
  aparece, se nenhuma estava escolhida), sem fechar e abrir o exame.

## 0.100.14 — IA visível no navegador; selo IA nas miniaturas
- **Navegador:** os **níveis da coluna** e os **níveis linfonodais** pedidos pela aba IA não apareciam (o overlay
  dizia "Sem CAD/IA neste exame"). Agora os nomes aparecem em qualquer série e plano, inclusive no MPR, como no Ipê,
  e já surgem quando a tarefa termina.
- **Overlay do navegador:** item **CAD/IA (achados, segmentações, níveis)** liga e desliga só a IA, lembrado de um
  exame para o outro.
- **Selo IA** nas miniaturas das séries (Ipê e navegador): nas séries que são resultado de IA ou que foram analisadas
  por uma, com as ferramentas na dica.

## 0.100.13 — Instalar a segmentação: Python baixado e idioma
- **O instalador da segmentação falhava** com "os error 448 (ponto de montagem não confiável)" em alguns Windows: o
  uv cria um atalho de pasta para o Python 3.12 que ele baixa, e o Windows bloqueia esse atalho. Agora o ambiente é
  criado direto do Python de verdade (o atalho é apagado); quem já baixou o Python não baixa de novo.
- O instalador fala o **idioma do Ipê** (inglês, espanhol ou português), e a pergunta "Instalar a segmentação" e
  outras mensagens montadas em partes passaram a sair traduzidas.
- O pacote do Windows não levava algumas ferramentas de IA (enfisema, Genant, aorta…), importadas pelo nome: a aba IA
  do navegador ficava vazia com erro. Agora vão todas, e uma ferramenta com problema não derruba a lista.

## 0.100.12 — Visualizador web: aba IA
- O CAD/IA do navegador virou a aba **IA** do painel da direita, como a do filme: todas as ferramentas de IA do Ipê
  (as que servem para o exame primeiro, as outras com o motivo), a série de cada uma (a sugerida ou a do quadro
  ativo) e **Rodar**; no alto da aba, as tarefas do exame com o andamento e **Cancelar**. O botão da barra e **IA** no
  rodapé abrem a aba.

## 0.100.11 — Visualizador web: montar o filme e imprimir
- Aba **Filme** no navegador: os quadros ajustados (janela, zoom, deslocamento, giro) vão para o filme (o quadro, todos
  ou a série a cada N); a prévia é desenhada pelo servidor com o código do compositor do Ipê; editar, reordenar e
  remover células; grade, papel, paisagem, textos, cabeçalho, anonimizar.
- **Imprimir**: baixar o PDF, imprimir no computador de quem está no navegador, nas impressoras do servidor, nas
  impressoras DICOM e nos destinos de impressão do Ipê. Conta no painel de filmes. Só com a permissão de imprimir.
- O servidor sem tela (`ipe server`) passou a usar o Qt de widgets (offscreen), para desenhar as folhas.

## 0.100.10 — Visualizador web: CAD/IA pelo navegador
- **CAD/IA neste exame** no navegador: as ferramentas de IA do Ipê que servem para o exame, com a série sugerida (ou a
  do quadro), rodando na fila de IA do servidor. **IA** no rodapé mostra as tarefas do exame (pedidas e automáticas)
  com a etapa e o tempo, e cancela as suas; ao terminar, **Recarregar o exame** traz as séries novas.
- Permissão nova **Pedir CAD/IA à mão** (de fábrica: administrador e médico).

## 0.100.9 — Visualizador web: enviar a um destino DICOM
- **Enviar a um destino DICOM** no navegador: o exame, as séries marcadas ou a imagem do quadro ativo, para os nós
  do servidor, pela fila de envios do servidor (a mesma do Ipê). Vão junto, se quiser, as medidas (GSPS) e as
  imagens-chave (KO). **Envios** no rodapé mostra o andamento e cancela. Só para quem tem a permissão de enviar.

## 0.100.8 — PET pela borda (gradiente); retomar a sessão; movimento na dinâmica web
- **PET: borda pelo gradiente (como o PET Edge)** na Segmentar 3D: o contorno fica onde o sinal cai mais depressa, com
  a correção do volume parcial pela resolução do PET (medida na própria lesão quando ela é grande; o campo
  *Resolução do PET (FWHM)* nas pequenas). Nas esferas de teste, ±15% do volume real a partir de 1,3 cm, contra o
  dobro ou mais de erro do 41% nas pequenas. Avisa quando a lesão está perto do limite da resolução.
- **Retomar a sessão**: o Ipê anota os exames abertos e guarda o estado da análise a cada 2 minutos; depois de uma
  queda, oferece reabrir o que estava aberto, como estava (Configurações ▸ Visualizador ▸ Estado da análise ao
  abrir: perguntar, reabrir sem perguntar ou não reabrir).
- **Visualizador web — correção de movimento na dinâmica da mama**: translação ou rígida, com a conta do Ipê feita no
  servidor; mapas, curvas, subtrações e a fase que se mexeu saem corrigidos.

## 0.100.7 — RM de mama: fibroglandular e realce de fundo; fim da leitura envia ao PACS
- **Fibroglandular e realce…** (painel da dinâmica da mama): separa o tecido fibroglandular da gordura no T1 sem
  saturação (ou no Dixon, ou na pré-contraste) e dá, em cada mama, a porcentagem e o volume; com a dinâmica aberta,
  a mediana do realce do FGT na primeira fase e quanto dele realça mais de 20%. Tira pele, músculo e parede lateral do
  tórax, corrige o degradê da bobina e deixa um implante fora da conta. **Copiar frases** para o laudo e **Gravar a
  máscara (SEG)** para conferir. Devolve número, não categoria: a categoria fica com o médico.
- **Fim da leitura** (Configurações ▸ Laudos): ao assinar o laudo, o KO das imagens-chave, o GSPS das medidas, o
  laudo desta assinatura (PDF e SR) e as séries do Ipê vão sozinhos ao PACS escolhido, pela fila de envios — também
  quando o laudo é assinado no navegador. Ocultas, cópias locais e séries de outro aparelho não vão.

## 0.100.6 — Linux: pacote .deb e install.sh no portátil
- **Pacote `.deb`** no release (`Ipe-<versão>-linux-amd64.deb`, pacote `ipe-viewer`): `sudo apt install ./…deb`
  instala em `/opt/ipe`, com o comando `ipe-viewer`, o ícone e o atalho **Ipê** no menu; o `apt` traz as bibliotecas
  da janela que faltarem. `sudo apt remove ipe-viewer` remove.
- **`install.sh` no portátil**: instala para o usuário, sem administrador (programa, comando `ipe-viewer`, atalho e
  ícone no menu); `--system` instala para todos em `/opt/ipe`; `--uninstall` remove. Rodar o da versão nova atualiza.
- Instalar, atualizar ou remover não mexe nos exames, no banco nem nas configurações. O nome é `ipe-viewer` porque
  `ipe` já é outro programa nas distribuições.

## 0.100.5 — visualizador web: duplo clique amplia; "Sair" volta à lista
- **Duplo clique** num quadro amplia para 1×1; outro duplo clique volta ao arranjo de antes, cada quadro como estava
  (corte, zoom, janela). Sobre uma medida, o duplo clique continua sendo da medida.
- **Sair**: com um exame aberto, fecha o exame e volta à lista de exames; na lista, sai do Ipê Web.
- Fechar ou recarregar a aba com um exame aberto pede confirmação.

## 0.100.4 — visualizador web: lupa e pilha alinhada na mamografia; laudo com BI-RADS, PDF/SR e busca ativa
- **Mamografia**: ao rolar da 2D para a tomossíntese da mesma incidência, a imagem nova fica na mesma escala em mm e
  com a parede torácica no mesmo lugar (a tomo tem outro tamanho e espaçamento; antes a mama mudava de tamanho e
  saía do lugar). Vale também com o zoom feito à mão.
- **Lupa**: segurar o botão mostra os pixels da própria imagem aumentados em volta do cursor, com a janela do
  quadro; a roda muda o aumento (1,5× a 8×). Botão na barra da mamografia e ferramenta em "Zoom e lupa".
- **Laudo no navegador**: o formulário **BI-RADS®** do Ipê (composição, achados, categoria por mama, recomendação),
  com as mesmas frases no texto; **Baixar PDF** (o PDF do Ipê, com cabeçalho e assinatura); ao assinar, o **PDF** e o
  **SR** gravados no exame e a **busca ativa** (BI-RADS 0 e 3), com os pedidos abertos da paciente no alto do laudo.
- O servidor sem janela (`ipe server`) sobe o Qt de interface sem tela, para gerar o PDF.

## 0.100.3 — visualizador web: os botões do mouse voltam a obedecer
- **Corrigido**: depois de trocar a função de um botão (por exemplo, a janela no direito, que antes era zoom), o
  mouse continuava fazendo a função antiga — o Cornerstone3D somava o botão novo aos antigos e, ao tirar uma função,
  só soltava o botão esquerdo. Agora cada troca deixa em cada botão exatamente a função escolhida.
- **Corrigido**: uma medida começada com um clique só (a régua desenha também em "clique, move, clique") deixava
  todas as ferramentas paradas até terminar a linha. Agora clicar noutro quadro, trocar de ferramenta ou apertar Esc
  desfaz a linha pela metade, e ela não vai para o banco.

## 0.100.2 — visualizador web: overlay, linhas de referência, PET ajustável, dinâmica e mamografia como no Ipê
- **Overlay**: o ícone novo liga e desliga de uma vez o CAD/IA (SR), as anotações de outro sistema (GSPS), os
  contornos RTSTRUCT, os textos dos cantos, as medidas e as linhas de referência; a seta escolhe item por item, e o
  tipo escondido fica escondido nos próximos exames. A SEG escolhida aparece também nos quadros de cortes.
- **Linhas de referência nos cortes**: o plano do quadro ativo aparece como linha nos outros (o axial no scout…);
  com a ferramenta Linhas de referência, clicar num quadro leva os outros ao corte do ponto.
- **PET**: a janela de SUV no arrasto do mouse (topo e piso, em todos os quadros do mesmo PET; Shift na fusão
  ajusta a TC) e o **arranjo** escolhido na aba PET — a grade e o que cada quadro mostra (TC + PET, TC, PET, MIP do
  PET) com o plano —, lembrado para o próximo PET/CT.
- **Dinâmica da mama**: a **curva sob o cursor** (3×3, como no Ipê) e a curva do ponto (valor do pixel); no rótulo
  de cada quadro, ◂ ▸ passam de fase e o menu escolhe a fase, a **subtração** de qualquer fase, a **paisagem**
  (anatomia de volta) e a **cor**; a barra escolhe a cor do mapa por cima da fase.
- **Mamografia**: cada quadro é a pilha da incidência, como no Ipê — a roda passa pelas imagens 2D da mesma mama e
  incidência e pelos cortes da tomossíntese.
- **Lista de exames**: clicar no título da coluna ordena (▲/▼), e a escolha fica lembrada.

## 0.100.1 — cliente do servidor central: o download não para mais ao abrir o exame
- **O download parava logo depois de o exame abrir**: quando as primeiras imagens demoravam mais de 0,4 s (rede de
  verdade), fechar o aviso "Baixando as primeiras imagens…" era lido como "Cancelar" — só as séries que já estavam
  chegando terminavam, e as outras ficavam com uma imagem. Agora só o botão Cancelar para o download.
- **Sinal da rede** na barra de status do cliente: barras (como as do celular), a ida e volta em ms e a vazão em
  Mbit/s até o servidor. Mede ao abrir o programa e a cada exame aberto (aí só a ida e volta; a vazão passa a ser
  a do próprio download); clique para medir de novo.
- Série que falha não é mais silenciosa: a barra de status diz quantas imagens faltaram e por quê.
- O cliente manda ao registro de acesso do servidor a versão dele ao entrar e, no fim de cada download, quantas
  imagens vieram, em quanto tempo, o que faltou (por série) e os erros — dá para conferir pelo servidor.
- Os comentários do exame voltaram a aparecer no cliente (o servidor respondia com erro).

## 0.100.0 — cliente do servidor central: quanto de cada série chegou, e menos dados na rede
- A tira mostra, em cada série, quantas imagens já chegaram (*34/120 im*) com uma barra, e ⬇ na que está
  chegando; o quadro mostra **⬇ 34/120** até a série terminar; a barra de status ganha a porcentagem.
- Pôr uma série num quadro passa ela para a frente do download.
- Duas séries baixam ao mesmo tempo, e a entrada no banco corre numa linha à parte (a rede não para mais
  enquanto o lote entra no banco).
- **HTJ2K sem perda na rede**: o servidor manda ao cliente uma cópia de envio (conferida pixel a pixel; o acervo
  não muda), 2 a 4× menos dados. As cópias dos exames dos últimos 14 dias ficam prontas em segundo plano; a imagem
  sem cópia pronta vai como está. O cliente decodifica pelo OpenJPH (imagecodecs, ~1 ms por corte de TC).
  Configurações ▸ Rede ▸ Servidor central liga e desliga.
- Mandar a um nó DICOM que não aceita a sintaxe do arquivo (HTJ2K, JPEG-LS) agora vai descomprimido.
- Visualizador web: trocar de layout ou de etapa enquanto a imagem carregava às vezes derrubava a página; e o pacote
  do site deixou de depender da ordem dos módulos (um erro na carga que aparecia ao mudar o código).
- Medido num exame de 720 imagens com as cópias prontas: numa rede de ~100 Mbit/s, 4,9 s com HTJ2K contra 16,8 s
  sem; em rede de 1 Gbit/s, 2,6 s contra 2,9 s.

## 0.99.99 — visualizador web: as séries seguintes começam logo
- O navegador pede os metadados de todas as séries juntos (três de cada vez), em vez de um depois do outro; os
  quadros entram na fila na ordem da tira assim que cada série chega.
- O servidor lê os cabeçalhos em paralelo, guarda a resposta (reabrir sai na hora; muda se o arquivo mudar) e lê o
  exame inteiro assim que a primeira série é pedida.
- As cópias de envio (HTJ2K) da série são feitas por um só trabalhador, em fila, e esperam enquanto há quadros
  sendo pedidos — antes, cada série aberta disputava o processador com as imagens que o navegador esperava.
- Num exame de teste com 6 séries de 120 cortes, a última série começava a baixar aos 12,7 s; agora, aos 3,3 s.

## 0.99.98 — visualizador web: mamografia com uma e duas telas, dinâmica da mama e laudo
- **Mamografia** no protocolo do Ipê: etapas (4 incidências, CC, MLO, atual × anterior…), a imagem de cada quadro e
  o exame anterior pelas mesmas regras, mamas costas com costas (espelha quando precisa), a mama enquadrada sem o
  ar, parede encostada na borda, mesmo zoom e mamilos na mesma altura; duplo clique amplia; tomossíntese do quadro.
- **Duas telas**: uma segunda janela (no outro monitor, quando o navegador deixa) com a outra metade da etapa, sem
  pedir a senha; as duas mudam de etapa juntas.
- **Dinâmica da mama**: as fases achadas como no Ipê; mapa cinético, SER, MSI, PEI, realce inicial, subtração, TTP
  e MIP/média temporais **calculados no navegador** com as contas do Ipê; um mapa (calculado ou já gravado pelo
  Ipê) por cima da fase; **curvas tempo-intensidade** das ROIs com a classe, o SER e os descritores.
- **Laudo no navegador**, no mesmo registro do Ipê: modelo sugerido com os campos automáticos, achados de IA
  revisados no cursor, rascunho (com gravação automática), assinar e liberar, retificar, e a trava de quem está
  laudando (só ler ou assumir; o servidor recusa gravar por quem não tem a trava).

## 0.99.97 — visualizador web: interface nova (estilo Weasis)
- **Barra de ícones** e **cada botão do mouse com a sua função, como no Ipê**: clicar no ícone com o botão
  esquerdo, o do meio ou o direito dá a função àquele botão; a marca embaixo do ícone (à esquerda, no meio, à
  direita) mostra qual. A escolha fica gravada.
- **Menu do botão direito** na imagem (clicar e soltar; clicar e segurar faz a função do botão): janela, zoom,
  girar e espelhar, plano, funções dos botões, série, quadros e cine, apagar medidas, restaurar; em cima de uma
  medida, copiar o valor e apagar.
- **Painéis recolhíveis**: séries e exames anteriores à esquerda; abas **Imagem**, **Medidas**, **DICOM** (tags com
  filtro) e **PET** à direita. Layout de 1×1 a 4×4 numa grade, e rodapé com carga e funções dos botões.

## 0.99.96 — visualizador web: carga mais rápida
- As imagens vão para o navegador em **HTJ2K sem perda** (cópia de envio conferida pixel a pixel, em cache; o acervo
  não muda): 2 a 5 vezes menos bytes numa TC, decodificação rápida e **carga progressiva**.
- **Volume intercalado** (o MPR aparece cedo e se completa), **cache do navegador** com revalidação (reabrir quase não
  usa a rede), decodificação em todos os núcleos menos um e metadados comprimidos.
- **Carga** (barra): MB pela rede, MB/s, tempo de decodificação por imagem, formato e o que veio do cache.

## 0.99.95 — visualizador web: arrastar séries e imagens disponíveis
- **Arrastar a série** da tira até qualquer quadro do visualizador web (clicar continua pondo no quadro ativo).
- **Imagens disponíveis**: ao abrir o exame, o navegador baixa as séries em segundo plano (as dos quadros primeiro);
  cada miniatura mostra a porcentagem pronta e o alto da tela, o total do exame. Com memória cheia, a pré-carga para.

## 0.99.94 — visualizador web: PET/CT (fase 4)
- **PET/CT** no visualizador web: fusão (TC + PET), PET em cinza invertido e o MIP do PET, com os axiais andando
  juntos e o clique no MIP levando os cortes ao ponto mais claro.
- O PET chega **em SUV pela conta do Ipê** (peso, dose e horários); a ROI e o valor do pixel no PET trazem SUVmáx e
  SUVméd como no Ipê.
- **Cor da fusão** com as tabelas do Ipê, **opacidade** e **topo da janela de SUV**; abaixo de 8% do topo não pinta.
- **SUV máximo perto do cursor** (esfera de 3 cm) leva os cortes ao voxel mais quente.
- **Segmentações (SEG)** do exame — carga tumoral, órgãos, lesões da IA — como máscaras com as cores do Ipê.

## 0.99.93 — visualizador web: medidas no banco e calibração do ultrassom (fase 3)
- **Medidas no visualizador web**: régua, ângulo, Cobb, ROI elíptica, retangular e livre, pixel, seta e calibração.
  O número é o do Ipê (mesma escala, mesma regra da ROI, mesmo texto).
- As medidas ficam **no banco do servidor**, no formato do Ipê, com quem mediu: o que se mede no navegador aparece no
  Ipê e vice-versa. Mexer numa ponta atualiza; clicar na medida e em **Apagar medida** apaga.
- **Ultrassom**: a distância usa a região calibrada do aparelho (atravessar duas regiões fica em pixels);
  **calibração** à mão vale para aquela imagem (nas outras modalidades, para a série).
- Correção: ao trocar a grade de quadros, a imagem podia aparecer minúscula num canto.

## 0.99.92 — visualizador web: MPR, oblíquo e MIP (fase 2)
- Cada quadro do visualizador web ganhou **A, C, S, MIP e Original** no alto: muda o plano com um clique,
  reconstruindo a série no navegador.
- **MPR** (barra): axial, coronal, sagital e o MIP girando, com as linhas de referência — arrastar o centro leva os
  planos ao ponto; girar uma linha faz os oblíquos.
- **Oblíquo por dois pontos**, **espessura** (3 a 20 mm em MIP, MinIP ou média) e **MIP girando** (botão ou roda do
  mouse); clicar no MIP leva os cortes ao ponto mais claro.
- Série que não dá volume continua em cortes, com o motivo; volumes acima de 1,5 GB não são montados.

## 0.99.91 — visualizador web no servidor central (fase 1)
- O servidor central traz um **visualizador no navegador** em `http(s)://servidor:8043/web/` (Chrome ou Edge), com
  o mesmo login do Ipê: lista de exames com busca e filtros, tira de séries com miniaturas, quadros de 1×1 a 2×3,
  janela, mover, zoom, rolagem, cine, inverter e as janelas prontas do Ipê. Feito com o Cornerstone3D.
- As imagens vão como estão no banco: JPEG-LS, JPEG 2000 e JPEG são decodificados no navegador; a mamografia usa a
  janela do aparelho (inclusive a sigmoide da GE).
- Nada do paciente fica gravado no navegador; cada abertura entra no registro de acesso. O endereço aparece em
  Configurações ▸ Rede ▸ Servidor central.
- No servidor: metadados e quadros do DICOMweb (WADO-RS), miniatura da série e cabeçalhos de segurança.

## 0.99.90 — diâmetro da aorta por segmento
- **Aorta** (botão **Aorta**, ou Aplicações ▸ Aorta) na TC de tórax ou de abdome, com ou sem contraste: o
  TotalSegmentator acha a aorta e os marcos; o programa traça a linha central e mede, em planos perpendiculares a
  cada 2 mm, o diâmetro máximo e o perpendicular. Sai o maior de cada segmento — raiz, ascendente, arco, descendente
  torácica, abdominal suprarrenal e infrarrenal —, da parede externa à externa, com a referência como texto
  (ACC/AHA 2022; aneurisma infrarrenal ≥ 30 mm e o controle do ACR 2013). Um achado por segmento e a SEG com uma cor
  por trecho.

## 0.99.89 — escore de cálcio coronariano (Agatston)
- **Cálcio coronariano** (botão **Cálcio**, ou Aplicações ▸ Cálcio coronariano) na TC sem contraste: o
  TotalSegmentator acha o coração, a aorta e os ossos; em volta do coração, o cálcio ≥ 130 HU é pontuado pelo
  Agatston corte a corte (cortes finos somados em fatias de 3 mm), com o volume e o vaso sugerido de cada lesão
  (TCE, DA, CX, CD). Sai o total, o **CAC-DRS** e a categoria da SCCT/STR; a aorta e o que está dentro do coração
  (valva, anel mitral) saem à parte. Um achado por vaso: corrigir ou descartar muda o total do laudo. Com contraste o
  escore não é medido.
- Correção: a SEG da carga tumoral no PET (0.99.88) não aparecia sozinha na aba depois da conta e não era tratada
  como série do próprio computador.

## 0.99.88 — PET: carga tumoral (FDG, PSMA, DOTA), leitura PET e SUV pela glicemia
- **Carga tumoral no PET** (botão **Carga**, ou Aplicações ▸ Carga tumoral): o TotalSegmentator acha os órgãos na
  TC do PET/CT; no PET, os focos acima do limiar do traçador (FDG: PERCIST; PSMA: SUV 3; DOTA: fígado) fora da
  captação fisiológica viram achados, com volume, SUVmáx/médio/peak, TLG e região (próstata, osso, linfonodo pélvico
  ou extrapélvico, víscera). Sai o MTV e a TLG totais; no PSMA, o **miTNM** (PROMISE) e o escore **miPSMA** de cada
  foco. Descartar um foco nos Achados tira ele do total do laudo. A máscara fica numa SEG sobre o PET.
- **Leitura PET** (botão Fusão): fusão, PET e MIP girando em três quadros; clicar num foco do MIP leva os cortes até
  ele. **Ir ao SUV máximo perto do cursor (3 cm)**.
- **Glicemia** na janela PET…: fica guardada no exame, entra no Q.Check (aviso acima de 200 mg/dL) e as medidas no
  PET mostram também o SUVglic (SUV × glicemia ÷ 100).

## 0.99.87 — guia do usuário com telas do programa
- O guia em PDF ganhou 19 figuras: banco de dados, visualizador com a segmentação de IA, barra de ferramentas,
  layout, medidas, MPR, 3D (MIP do PET), mamografia e tomossíntese, RM de mama e a janela da dinâmica, anteriores,
  fusão PET/CT, níveis da coluna, Estruturas, exportar e as configurações (barra, rede, servidor central).
- As telas usam exames reais anonimizados (pacientes EXEMPLO, datas deslocadas, UIDs novos, sem instituição nem
  tags privadas) e são refeitas a cada versão pelo roteiro `tools/guia/capturas.py`, que abre o programa sem
  janela e fotografa cada tela. O gerador do guia aceita `![legenda](arquivo.png)`.

## 0.99.86 — abertura mais rápida (JPEG-LS) e cronômetro da abertura no registro
- As imagens em JPEG-LS (a compressão sem perda do Ipê; toda a mamografia guardada) passam a ser lidas pelo
  pyjpegls (CharLS) em vez do gdcm: numa mamografia 2850×2394 do seu banco, 122 ms em vez de 280 ms, e os quadros
  decodificam em paralelo.
- Os decodificadores e os módulos que o primeiro exame carregava na hora são carregados alguns segundos depois que
  o programa abre.
- Cada abertura deixa no registro o tempo até a primeira imagem, por etapa (banco, barra, tira, protocolo, janela,
  estado, imagem), e quando as sobreposições de IA terminam de entrar.
- Release: sai só o `-installer.exe` (a cópia `-instalador.exe` da transição acabou).

## 0.99.85 — cliente do servidor central abre o exame enquanto baixa; instalação no Linux
- No modo cliente, o exame que ainda não está no computador abria só depois de baixar todas as imagens. Agora
  chega primeiro uma imagem de cada série (o exame abre com a tira completa e o protocolo monta os quadros) e o
  resto de cada série vem em segundo plano, em lotes; os quadros crescem sozinhos. A barra de status mostra
  "N de M imagens", e o registro anota o exame e o total a baixar.
- `instalar.sh`: para com uma mensagem clara em Linux antigo (glibc < 2.34), escolhe um Python 3.10+ do sistema
  em vez do Anaconda (e refaz um `.venv` antigo) e instala as bibliotecas da janela que faltam (`libxcb-cursor0`…).

## 0.99.84 — abertura mais rápida dos exames com SEG de IA
- A SEG de órgãos do TotalSegmentator (milhares de quadros) era lida na tela principal a cada abertura e travava o
  exame por segundos. Agora os quadros saem direto dos bytes do arquivo (2–5× mais rápido), a leitura das SEG
  grandes vai para segundo plano (a imagem aparece antes) e o que já foi lido fica na memória: reabrir o exame é
  imediato.
- O desenho só passa pelas máscaras perto do corte atual, em vez de todas a cada pintura.
- Medido num exame de 300 cortes com SEG de 60 estruturas: abertura de 6,2 s para 1,4 s; reabertura de 2,2 s para
  0,2 s.

## 0.99.83 — MedSAM2, autoPET e BraTS (modelos extras)
- **Segmentar pela caixa (MedSAM2)**: ferramenta do botão esquerdo; a caixa num corte vira máscara 3D, propagada
  para cima e para baixo, e abre na janela da Segmentação 3D (volume, eixos, SUV, lesão, SEG).
- **autoPET**: lesões no PET-FDG pelo nnU-Net do autoPET II, com a TC do PET/CT reamostrada no PET; MTV, TLG,
  SUVmáx e cada lesão como achado.
- **BraTS**: glioma na RM (T1 pós, T1, T2, FLAIR registradas e sem crânio), SegResNet do MONAI; volumes da parte
  captante, necrose e edema.
- **Configurações ▸ CAD/IA ▸ Instalar os modelos extras…**: instala os três no ambiente da segmentação e mostra o
  que já está pronto.

## 0.99.82 — estruturas no 3D e lesões hepáticas por segmento
- **3D ▸ Estruturas**: as segmentações do exame (órgãos da IA, lesões, nódulos, SEG/RTSTRUCT) aparecem como
  superfícies coloridas, junto com o osso do VR ou sobre o MIP, e acompanham giro, cortes e escultura.
- **Lesões hepáticas** (TC e RM): tarefas abertas `liver_lesions` e `liver_segments` do TotalSegmentator; volume,
  maior diâmetro axial e segmento de cada lesão, e a carga tumoral (% do fígado) total e por segmento de Couinaud.
  Cada lesão é um achado revisável.

## 0.99.81 — nomes dos pacotes em inglês
- Os arquivos do release passam a se chamar `Ipe-<versão>-installer.exe`, `-windows-portable.zip` e
  `-linux-portable.tar.gz`. A atualização pelo GitHub acha os nomes novos e os antigos.
- Transição: o release traz também `Ipe-<versão>-instalador.exe` (o mesmo instalador), para as versões 0.99.70 a
  0.99.80 atualizarem com um clique.
- Este release junta a 0.99.79 (um Ipê só por usuário) e a 0.99.80 (altura e peso na composição corporal e o
  resultado da esteatose).

## 0.99.80 — peso e altura na composição corporal, e o resultado da esteatose
- Ao clicar para calcular a composição corporal, uma janela mostra altura, peso e sexo do arquivo para conferir
  ou digitar (vale para o exame; o arquivo não muda). Em Achados de IA, **Altura e peso…** troca depois e refaz o
  índice muscular, o IMC e as referências sem rodar a IA.
- Com o peso: IMC e as referências de Martin et al. (J Clin Oncol 2013) para sarcopenia e mioesteatose.
- Atenuação hepática ganhou um **resultado** em texto (Park 2006, Pickhardt 2012): compatível com esteatose
  moderada a acentuada, esteatose leve possível (fígado/baço < 1,0), sem sinais, ou não classificado com contraste.
  Vai ao laudo e acompanha a correção dos números.

## 0.99.79 — um Ipê só
- Clicar de novo no atalho (ou num link ipe://) não abre outro programa: o que já está aberto vem para a frente,
  também da bandeja ou do login. A trava é por usuário e se solta sozinha se o programa cair.

## 0.99.78 — menus do botão direito mais limpos e ícones das aplicações de IA
- **Quadro**: em cima, só o que depende do lugar clicado (medida, nódulo, achado BI-RADS, eixo de simetria, DSA);
  depois imagem-chave e copiar; **Imagem ▸** (janela, cor, inverter, filtro, girar, mosaico, histograma),
  **Quadro ▸** (fundir, linhas de corte, sincronização, cine), **Anotações ▸**, **Ferramenta do botão esquerdo ▸**
  (Navegar, Medir, Desenhar) e as tags; o que apaga fica no fim. A cor mostra as mais usadas da modalidade e
  *Mais cores ▸*. A segmentação saiu do botão direito (fica nos botões; *Identificar vértebras e discos* foi para
  a seta do botão Genant). DSA só em angiografia; eixo de simetria na RM de mama ou com ROI no corte.
- **Banco**: Abrir e Laudo em cima; **Organizar ▸** (listas, prioridade, subespecialidade, estado, comentário,
  banco), **Documentos ▸**, Enviar/Exportar, **Ferramentas ▸** (anonimizar, corrigir tags, apagar implante só em
  mamografia); Proteger e Remover proteção viraram um item só.
- **Ícones**: cada aplicação da barra tem o seu desenho (nódulos, enfisema, composição, fígado, órgãos, Genant,
  linfonodos, cefalometria, índices, difusão), com um ✦ dourado nas que usam IA.

## 0.99.77 — enfisema por lobo e fratura vertebral (Genant)
- **Enfisema** (TC de tórax): %LAA−950, Perc15 e volume por lobo, por pulmão e no total, com a distribuição
  (superior, inferior ou homogênea); avisos de corte grosso, filtro duro, contraste e calibração do ar (traqueia).
  As áreas abaixo de −950 HU numa SEG só da série calculada.
- **Genant** (TC ou RM da coluna): altura anterior, média e posterior de cada corpo vertebral e a perda de altura
  (cunha, bicôncava, esmagamento), com o grau de Genant de T4 a L5.
- Os dois resultados entram nos Achados de IA para revisar; só o confirmado vai ao laudo.

## 0.99.76 — mamografia: duplo clique enquadra direito
- No 1×1 do duplo clique numa incidência, a mama ficava alta e com parte escondida: o zoom e o alinhamento pelo
  mamilo vinham dos quadros escondidos. Agora o quadro ampliado é enquadrado sozinho, para o tamanho dele.

## 0.99.75 — mudar a pasta do banco sem o "WinError 32"
- **Mover os arquivos** (Configurações ▸ Banco de dados ▸ Mudar a pasta do banco) falhava no Windows com
  *WinError 32* (o banco aberto pelos serviços de fundo) e deixava o programa na pasta nova só com parte do banco.
  Agora a mudança é feita na próxima abertura, antes de o banco abrir; se algo falhar, o que já tinha ido volta e
  o programa continua na pasta de antes.

## 0.99.74 — HTTPS na rede interna, com certificado do próprio Ipê
- **Servidor central ▸ Gerar certificado para a rede interna…**: o Ipê cria uma AC interna do serviço e o
  certificado do servidor (nome e IPs do computador), e o servidor passa a usar HTTPS.
- **Cliente ▸ Confiar no certificado deste servidor…**: baixa a AC do servidor, mostra a impressão digital para
  conferir e passa a exigir HTTPS conferido com ela. **Salvar a AC (.crt)** para instalar no Windows (navegador e
  outros visualizadores DICOMweb).
- Nova dependência: cryptography.

## 0.99.73 — Configurações: a janela do grupo
- Clicar no nome do grupo do menu Configurações (Visualizador, Protocolos de exame, CAD/IA, Laudos…) abre uma
  janela com todas as etapas daquele grupo, numa lista à esquerda. O item do submenu continua abrindo só ele, e
  *Todas as preferências* continua abrindo tudo.

## 0.99.72 — o instalador avisa do Visual C++
- O instalador do Ipê confere se o Microsoft Visual C++ Redistributable (x64) existe e, faltando, oferece abrir o
  download da Microsoft. Ele só é preciso para a segmentação (PyTorch); o Ipê e o Python não precisam. O
  *Instalar a segmentação* avisa o mesmo antes de abrir.

## 0.99.71 — instalador da segmentação: Visual C++ do PyTorch
- O `instalar_segmentacao.bat` confere se o PyTorch abre. Se não abrir (*WinError 126 … shm.dll*, comum em
  Windows Server e Windows recém-instalado), baixa e instala o Microsoft Visual C++ Redistributable e confere de
  novo, com mensagem clara se ainda faltar reiniciar.

## 0.99.70 — versão nova pelo GitHub, com um clique
- Ao abrir (uma vez por dia) e em **Ajuda ▸ Procurar versão nova (GitHub)…**, o Ipê procura o último release.
  No Windows instalado, **Baixar e instalar** baixa o instalador, confere o SHA-256, fecha, instala sem perguntas
  e abre a versão nova. Na versão portátil e no Linux, baixa o pacote e abre a pasta. *Pular esta versão* e
  **Ajuda ▸ Avisar quando sair versão nova** para desligar.
- A atualização sem perguntas (pelo GitHub ou pelo servidor central) não volta mais o modo de uso para "só eu"
  nem o idioma para o inglês, e o instalador abre o programa no fim.

## 0.99.69 — instalador da segmentação: acha o Python certo
- O `instalar_segmentacao.bat` testa se cada Python **abre de verdade** e responde (antes, um Python quebrado
  ou um comando inexistente podiam passar), lista os Pythons do computador e ignora PYTHONHOME e PYTHONPATH do
  Windows, que quebravam qualquer Python com *No module named 'encodings'*.
- Um ambiente antigo que não abre é apagado e refeito (ou renomeado, se a pasta estiver presa). Se o Python do
  computador não servir, baixa um 3.12 só para a segmentação. Mensagem de rede mais clara.

## 0.99.68 — exportar e importar as configurações
- **Configurações ▸ Sistema ▸ Exportar as configurações…** e **Importar configurações…**: um arquivo `.ipeconfig`
  que vai do Windows para o Linux e ao contrário. Leva as configurações do computador e as pessoais, protocolos,
  modelos de laudo e de folha, perfis, SLA, busca ativa, nós DICOM, identidades AE, automação e traduções.
- Não leva o que é de cada computador (banco, monitores, login, título AE, token, servidor/cliente, janelas) nem
  as pastas do outro sistema. Senhas só se marcar. O mesmo nome é atualizado, não duplicado; antes de importar
  fica uma cópia das configurações de agora.

## 0.99.67 — o instalador pergunta a pasta do programa e a do banco
- O instalador do Windows pergunta sempre a **pasta do programa** e a **pasta do banco de dados** (numa
  atualização, já preenchidas com as de antes). Não aceita Arquivos de Programas (instala sem administrador) nem o
  banco dentro da pasta do programa. Um banco com exames não é trocado por uma pasta vazia: o instalador avisa e o
  programa move, em Configurações ▸ Banco de dados.
- Linha de comando: `ipe-cli set-data-dir PASTA`.
- O guia explica como desinstalar (Aplicativos instalados do Windows) e o que fica no computador.

## 0.99.66 — importar RAR, 7z e outros compactados
- **Arquivo ▸ Importar compactado (ZIP, RAR, 7z)…** e o arrasto também abrem RAR, 7z, TAR (gz/bz2/xz), ISO e CAB.
  RAR, 7z e ISO usam o 7-Zip, se instalado, ou o tar que já vem no Windows 10/11; o WinRAR também serve para RAR.
- ZIP em Deflate64 (o que o Windows faz com arquivos grandes) passa a abrir pelo 7-Zip ou pelo tar do Windows.
- Compactado em partes (.part1.rar, .7z.001): basta mandar todas as partes, ou só a primeira. Compactado dentro
  de compactado também abre. Arquivo com senha avisa, em vez de travar.

## 0.99.65 — órgãos abdominais e níveis linfonodais só na série calculada
- A segmentação dos órgãos abdominais e o mapa dos níveis linfonodais aparecem só na série em que foram
  calculados (e nas reconstruções dela), não mais em todas as séries do exame, onde caíam fora do lugar.

## 0.99.64 — mama: fusão por arrastar, mapas em cor, achados por marcadores
- **Fundir por arrastar**: soltar a série no canto "Fundir por cima" do quadro; e botão direito ▸ Fundir este
  quadro sobre… para qualquer mapa da dinâmica, fase ou ADC sobre outro quadro.
- **Mapas em cor** na dinâmica: *Tempo em cor* (cor = tempo até o pico, brilho = realce) e *Fases em cor* (RGB =
  inicial, intermediária, tardia).
- **Achados BI-RADS por marcadores** na mamografia: marcar na CC e na MLO, tabela com distância ao mamilo,
  quadrante, hora e terço, e mandar ao laudo BI-RADS.

## 0.99.63 — estado do exame
- Coluna **Estado** no banco: não lido, em leitura, urgente, revisado — sozinha, pelo acesso, pelo laudo e pela
  prioridade; troca à mão no botão direito (✎), filtros em **Trabalho ▾** e a ação "marcar como revisado" no
  visualizador.

## 0.99.62 — nódulo pulmonar completo
- **Nódulo por clique** na TC (botão direito ▸ Nódulo pulmonar aqui): segmentação pelo limiar, separando dos
  vasos e da pleura, com vidro fosco opcional; os mesmos números da IA; guardar como achado confirmado ou já
  acompanhar como lesão.
- **O mesmo nódulo no exame anterior** (pelo registro, ou provável pelo lobo e pela distância): crescimento do
  diâmetro médio e do volume e tempo de duplicação, na janela, na lista de Achados e no laudo. A medida nova entra
  na lesão que já era acompanhada.

## 0.99.61 — rodada mama P2
- **Alinhamento pelo mamilo** na mamografia: na mesma linha da tela, as duas mamas com o mamilo na mesma altura
  (opção do protocolo; "pelo meio da mama" como antes). **Zoom e pan** espelhados agora também na barra.
- **Inverter só a mama**: tecido invertido, fundo preto, em todos os quadros.
- **★ Corte**: o corte da tomossíntese como imagem-chave, com o número do corte; atalhos para ir ao próximo
  e ao anterior marcados.
- Quadros **US** e **RM** no protocolo da mamografia: a última ultrassonografia e a última RM do paciente
  (`RM:T2` escolhe a série).
- **Eixo de simetria à mão** para a ROI espelhada (botão direito ▸ Eixo de simetria).

## 0.99.60 — PET no seguimento (item 7, parte 2)
- **SUL** (massa magra de Janmahasatian) guardado em cada medida de PET; o PERCIST usa o SULpeak.
- Botão **PET…** no painel de lesões: referência do **fígado** (esfera de 3 cm, por clique ou automática pela
  segmentação do fígado) e do **mediastino**, **limiar do PERCIST** (1,5 × fígado + 2 DP), aviso de fígado
  não comparável entre exames.
- Critério **Deauville / Lugano**: escore proposto por lesão e por exame (troca no botão direito) e a
  resposta metabólica.
- **Q.Check** do cabeçalho do PET, no exame e contra o de base (captação, peso, dose, unidade, correções,
  reconstrução, aparelho).

## 0.99.59 — seguimento entre datas (item 7, parte 1)
- **Ligação pela posição**: a medida feita no exame de seguimento no lugar de uma lesão (até 10 mm, levada ao
  anterior pelo registro) liga sozinha a ela. Sem registro, ou com duas lesões perto, não liga.
- **Seguimento…** no painel de lesões: as lesões ainda sem medida neste exame, uma a uma — **repetir** a
  medida no lugar estimado (contorno anterior em sombra), **pequena demais** (5 mm), **ausente**, estável ou
  progressão.
- **Nadir** no painel (linha e marca ▼) e as quatro datas (base, nadir, anterior, atual) no resumo.

## 0.99.58 — estado salvo da análise
- O exame **reabre como você deixou**: layout, séries, corte, janela, zoom, pan, giro, cores, quadro ativo,
  anteriores (ligados de novo), painéis e os parâmetros da dinâmica (religa num clique). Por usuário, só no
  Ipê (no servidor central para todas as estações).
- **Exibir ▸ Estado da análise**: reabrir, voltar ao de fábrica, usar a montagem do exame anterior ou abri-lo
  ao lado como estava. Configurações ▸ Visualizador ▸ Estado da análise ao abrir.

## 0.99.57 — PDF e imagens anexados ao exame
- Arrastar um **PDF** ou uma **imagem** sobre o exame aberto, ou no banco de dados com um exame selecionado
  (com confirmação), ou o botão direito ▸ **Anexar documento…**: vira DICOM dentro do exame (PDF encapsulado
  ou imagem de captura secundária) e segue as regras de roteamento do exame. Outros formatos: salve como PDF.
- **Documentos do exame…**: os PDF do exame abrem dentro do programa.

## 0.99.56 — perfis por grupo e computador e atualização pelo servidor (onda B2 e B1)
- **Perfis por grupo e computador** (Configurações ▸ Usuários): preferências mandadas pelo servidor por
  computador (com coringa), usuário ou perfil de acesso; captura do computador arrumado; chaves forçadas.
- **Atualizações pelo servidor central** (Configurações ▸ Rede): publicar o instalador nos canais teste e
  estável, promover e retirar; o cliente avisa ao entrar, baixa, confere o SHA-256 e instala com um clique.

## 0.99.55 — OAuth2/OIDC nos nós DICOMweb e senhas cifradas (onda B3)
- Nó DICOMweb com **OAuth2**: credenciais do cliente, usuário e senha (Keycloak) ou token fixo; o endereço do
  token pode ser o do emissor OIDC (descoberta automática); token renovado sozinho e nova tentativa no 401.
- **Senhas cifradas**: a senha, o token e o segredo do cliente ficam cifrados no banco (DPAPI no Windows;
  chave local nos outros); as antigas em texto claro são cifradas na primeira leitura.

## 0.99.54 — IA no texto do laudo (onda B5)
- Botão **IA ▾** no laudo: **conferência local** (sem rede; campo vazio, medida sem unidade, lateralidade,
  sexo × órgão, BI-RADS do texto × formulário, conduta × categoria, impressão vazia), também **antes de
  assinar**; e, com um modelo configurado (Ollama, servidor compatível com OpenAI ou API da Anthropic),
  **refinar o texto**, **gerar a impressão** e **apontar erros** — sempre como sugestão para aceitar.
- O texto vai sem nome, ID, accession e nascimento do paciente; a chave da API fica cifrada.

## 0.99.53 — painel de produtividade (onda B6)
- **Laudos ▸ Produtividade…**: laudos assinados por médico, modalidade, subespecialidade, prioridade ou dia,
  com retificações, mediana e p90 da chegada à assinatura e parte no prazo; pendentes agora; CSV. Quem não
  gerencia usuários vê só os próprios laudos.

## 0.99.52 — lista de trabalho com prioridade, subespecialidade e prazo (onda B4)
- Colunas **Prioridade**, **Subespecialidade**, **Prazo do laudo** e **SLA** (faltam / vence em / atrasado;
  no prazo ou fora do prazo depois de assinado), por regras do serviço e trocáveis no botão direito.
- **Trabalho ▾**: sem laudo pelo prazo, atrasados, vencendo em 2 h, urgências e minhas subespecialidades.
- Regras em **Configurações ▸ Laudos ▸ Prioridade, subespecialidade e prazos (SLA)…**.

## 0.99.51 — busca ativa e filtros de mamografia (onda B8 e B7)
- **Busca ativa**: o laudo BI-RADS 0 ou 3 assinado gera o pedido de chamar a paciente de volta (30 e 180
  dias, configuráveis; 4 e 5 opcionais). **Laudos ▸ Busca ativa…**: prazos, atrasos, contatada / agendada /
  encerrada com histórico, exportar CSV; a paciente sai sozinha quando chega exame de mama novo dela.
- **Mama ▾** no banco de dados: filtros prontos por BI-RADS, densidade, sem laudo, rastreamento ou
  diagnóstica e busca ativa; colunas novas **BI-RADS**, **Densidade** e **Busca ativa**.

## 0.99.50 — ferro hepático a 3 T e faixa do LIC
- **Fígado na RM**: a 3 T, o R2* hepático é dividido por 2,05 para o equivalente a 1,5 T (Alam et al., JCMR
  2016) e então vai à calibração de Wood — o achado mostra o R2* equivalente e o LIC. Antes, a 3 T não
  estimava.
- **Faixa do LIC** ao lado do número: 3,2–7 leve, 7–15 moderada, > 15 mg Fe/g grave (texto de referência).

## 0.99.49 — gordura e ferro hepáticos na RM
- **Fígado** (RM de abdome): o fígado, o baço e os segmentos vêm do TotalSegmentator e as medidas saem dos
  mapas do aparelho — **PDFF** (mediana, p25–p75 e por segmento) e **R2\*** (com T2\*, o baço e, a 1,5 T, o
  ferro estimado pela calibração de Wood 2005); com a dupla eco em fase / fora de fase, a fração de sinal de
  gordura. Referência de PDFF de Tang 2015 como texto.
- Os números são achados revisáveis (Aplicações ▸ Achados de IA); automático em Configurações ▸ CAD/IA.

## 0.99.48 — fases fora da conta, descritores da curva, ROI espelhada
- **Dinâmica ▸ Parâmetros**: **fases fora da conta** (a que mexeu sai dos mapas e das curvas; não a inicial,
  a tardia nem duas seguidas) e **linha de base pela média das fases pré**; aviso com uma fase pré só.
- **Mapas e colunas novos**: chegada do contraste (BAT), lavagem (maior descida depois do pico), iAUC90 e
  tempo médio do realce (MRT).
- **ROI espelhada** (botão direito na ROI): a ROI do outro lado no espelho do plano mediano — no mesmo
  corte (axial/coronal) ou no corte do outro lado (sagital) —, com a razão lesão / contralateral.

## 0.99.47 — composição corporal em L3 e atenuação hepática
- **Composição** (TC de abdome): no corte axial do meio de L3, área muscular, densidade muscular, gordura
  visceral, subcutânea e intermuscular; com a altura no arquivo, o índice muscular (referência de Prado 2008
  como texto). Fígado e baço: HU médio, fígado − baço e fígado / baço, com aviso quando há contraste.
- Os números são achados revisáveis (Aplicações ▸ Achados de IA); automático em Configurações ▸ CAD/IA.
- O instalador da segmentação passa a baixar *trunk_cavities*.

## 0.99.46 — achados de IA revisáveis; nódulos pulmonares
- **Achados de IA** (Aplicações ▸ Achados de IA): cada candidato que uma IA aponta fica *sugerido*, com posição,
  números, modelo, série e avisos; você **confirma, corrige ou descarta** um a um, com quem e quando. Só o
  confirmado ou corrigido vai ao laudo; o confirmado pode virar **lesão acompanhada**. Rodar de novo não refaz
  o que já foi revisado.
- **Nódulos pulmonares** na TC (botão Nódulos, ou automático em Configurações ▸ CAD/IA): TotalSegmentator
  *lung_nodules* — lobo, diâmetro maior e médio, volume, HU médio, parte sólida e consistência proposta.
- O instalador da segmentação passa a baixar *lung_nodules* e *total*.

## 0.99.45 — zoom digitado, ROI clonada, tempo de duplicação, séries derivadas que dizem de onde vieram
- **Zoom digitado**: duplo clique no "Zoom N%" do canto ▸ ajustar, 1:1, 50 a 400% ou *Digitar o zoom…*
  (`150`, `2x`, `1:1`).
- **Clonar a ROI** (botão direito na ROI): os outros quadros recebem a ROI na mesma posição no paciente, com
  a estatística da imagem deles; entre exames diferentes, só com os quadros ligados ou registrados.
- **Tempo de duplicação** no acompanhamento de lesões, pelo volume ou pelo diâmetro (supondo esfera); sem
  crescimento, "não se aplica".
- **Selo âmbar** quando o quadro está ligado na sincronia a quadros de outro Frame of Reference.
- **Cortes não mostrados**: rolando depressa, aparece por um instante quantos cortes não chegaram à tela.
- **Exportar pacientes diferentes num pacote só** (CD com visualizador ou .zip, identificado) pergunta antes.
- **Séries derivadas** (reconstruções, mapas, capturas) gravam os parâmetros em *Derivation Description* e as
  imagens de origem em *Source Image Sequence*.

## 0.99.44 — limites da edição, estatística ampliada, conferir o registro
- **Estruturas ▸ Limites da edição**: área (em toda parte, só dentro de uma estrutura, só fora das outras),
  faixa de intensidade valendo para todas as ferramentas e **sobrescrever** (o que uma ganha sai das outras).
- **Estatística ampliada** da estrutura: mediana, percentis 10/90, assimetria, curtose, entropia,
  uniformidade, maior diâmetro (Feret), esfericidade, alongamento e achatamento; **Copiar os números**
  (uma linha por estrutura, para a planilha).
- **Conferir o registro** com o outro exame: xadrez, cortina que segue o mouse, diferença e mistura, com a
  matriz do registro rígido.

## 0.99.43 — mosaico no quadro; CAD oculto até revelar
- **Mosaico de cortes** (botão direito ▸ Mosaico, ou atalho): 2 × 2, 3 × 3 ou 4 × 4 cortes seguidos da
  mesma série dentro de um quadro; a roda vira a página; duplo clique volta ao quadro normal na imagem.
- **Ler antes, ver o CAD depois** (Configurações ▸ CAD/IA): as marcas de CAD começam ocultas em cada
  exame; **CAD/IA ▸ Revelar o CAD** (ou o atalho) mostra e diz quanto tempo de leitura houve antes.

## 0.99.42 — perfis de ocultação
- **Ocultar dados do paciente** ganha perfis (seta do botão): **Ocultar tudo** (o de antes), **Tela**
  (pseudônimo, datas reais), **Ensino** (pseudônimo, datas deslocadas pelo mesmo número de dias para todo o
  paciente — o intervalo entre os exames fica) e **Publicação** (sem datas nem aparelho). Valem para o
  quadro, o título da aba e a lista do banco; o canto do quadro mostra o perfil em uso.
- Exportar anonimizado ganha **Deslocar as datas**, marcado sozinho no perfil Ensino.

## 0.99.41 — imagens-chave e anotações em DICOM; medida rascunho
- **Gravar imagens-chave e anotações no exame** (botão Chave): as imagens-chave saem como **KO** e as
  medidas, setas e textos como **GSPS**, com o número de cada medida ao lado; vão ao PACS com o exame e
  abrem em outros visualizadores.
- O **KO que chega** no exame marca as imagens-chave aqui; com vários **GSPS de outros sistemas**, aparece
  só o mais recente; **Trazer as medidas para editar** (botão CAD/IA) transforma as medidas de um SR ou
  GSPS de fora em medidas do Ipê.
- **Medida rascunho** (botão direito ▸ Rascunho, ou preferência para toda medida nova): tracejada, não
  vai ao SR, ao GSPS, ao laudo, à planilha nem ao acompanhamento.
- Corrigido: o **SR** das medidas usava só o tamanho do pixel da tag — a medida calibrada à mão ou no
  ultrassom saía em pixels. Agora usa a mesma escala da tela (conferido no acervo: 10, 20 e 50 mm).

## 0.99.40 — estruturas: editar máscaras e gravar SEG / RTSTRUCT
- Nova janela **Estruturas** (botão 3D, ou CAD/IA): lista das máscaras do exame com nome, cor, tipo
  (lesão, órgão, outro), volume, *travada* e origem; importa lesões guardadas, segmentos de SEG (inclusive
  os das IAs) e contornos de RTSTRUCT.
- **Pincel e borracha** em qualquer quadro e plano do exame (disco no plano ou esfera 3D, raio em mm,
  opção de pintar só na faixa de intensidade do clique, sem passar por cima das estruturas travadas).
- **Crescer / encolher** em mm, **só a maior ilha**, **tirar ilhas pequenas**, **preencher buracos**,
  **interpolar os cortes** entre dois desenhados, **aparar pela faixa**, **unir / subtrair / cruzar**;
  desfazer e refazer.
- **Gravar SEG** (com o tipo de cada segmento) e **gravar RTSTRUCT** (contornos pela borda dos pixels,
  buracos como contorno interno); **atualizar a lesão guardada** com a máscara e o volume corrigidos;
  mandar os volumes ao laudo.
- Medido no acervo: as SEG das IAs (órgãos abdominais, cefalometria, implante) entram, são corrigidas e
  saem como RTSTRUCT em menos de 1 s por estrutura.

## 0.99.39 — correção de movimento rígida na dinâmica
- Na janela da **Dinâmica** (e no editor da dinâmica em Configurações), **Incluir rotação**: além da
  translação, o registro rígido de cada fase sobre a pré-contraste; a fase que girou 0,75° ou mais é
  reamostrada em 3D antes dos mapas, das curvas e da captura da lesão. O título do painel mostra o
  maior deslocamento e a maior rotação corrigidos.
- Medido antes no acervo: em 6 RM de mama (11 fases) a rotação entre as fases ficou entre 0 e 0,5° e a
  translação abaixo de 1,3 mm — por isso a opção vem desligada e, abaixo do limiar, a fase fica só na
  translação (sem a suavização da reamostragem).

## 0.99.38 — registro rígido entre exames
- **Alinhar automaticamente com o outro exame** passa a fazer o registro **rígido** (rotação e
  translação em 3D), com correlação (mesma sequência) ou informação mútua (outra modalidade ou
  sequência), em várias resoluções; a qualidade aparece na barra de status.
- Com o outro exame girado 1° ou mais, o programa oferece **gravá-lo no plano deste** (série nova, com a
  geometria e o Frame of Reference deste): os dois andam juntos corte a corte.
- A matriz do registro fica guardada; validação por pares de pontos (erro médio e máximo em mm).
- Conferido no acervo: crânio 3D real com transformação conhecida, erro médio 0,4 mm em 6 s.

## 0.99.37 — difusão em qualquer RM
- Botão **Difusão** (e em Aplicações): **mapa ADC** a partir dos valores de b da série (regressão em
  todos os b marcados), gravado como série de RM do exame em ×10⁻⁶ mm²/s, com limiar de ruído e R²
  mínimo; **DWI sintética** num b escolhido, marcada como sintética; **ADC numa ROI**, com o ADC do
  aparelho e o sinal de cada b lado a lado, e a frase para o laudo.
- O b sai do arquivo (padrão, GE, Siemens, Philips); na GE anonimizada o b0 é deduzido; sem b no
  arquivo, digita-se. Avisos antes de calcular: só um b, sem b0, b baixo, cortes incompletos, TE diferente.
- Conferido no acervo: no crânio o ADC é o do aparelho (razão 1,0002).

## 0.99.36 — fim do plano do modo de uso
- **Regras de automação com dono**: buscas agendadas, anteriores, roteamento, dinâmica pronta e gestão
  automática ganham *Visível para* (Todos / Só eu / com escolhidos) e a coluna na lista; aba própria em
  Configurações pessoais e compartilhadas, com *Copiar para mim*. Todas continuam rodando.
- **Para onde vão os exames baixados pela automação**: para o compartilhado (antes iam para o banco de
  quem estivesse logado); a busca pessoal pode mandar para o banco do dono. O **anterior** vai para o
  mesmo banco do exame atual.
- **Referências** da cefalometria e dos índices do crânio: só minhas ou de todos deste computador.
- **Chamada externa** (RIS, link, API) não abre mais o banco pessoal de outro usuário (o administrador
  abre, com registro).
- **Listas de casos vão junto** com os exames entre este computador e o servidor central (pasta, lista,
  nome amigável, história, resposta e notas, sem duplicar).
- **Modo cliente**: o exame novo baixado do PACS respeita "o meu banco neste computador".
- Correção: gravar a configuração de uma regra sem o dono não apaga mais o dono.

## 0.99.35 — tradução revisada
- **Textos que ficavam em português** no programa em inglês ou espanhol: cerca de 650 textos novos
  traduzidos, entre eles as telas e mensagens das IAs (CAD/IA, segmentação, coluna, cefalometria,
  linfonodos, índices do crânio, implante, Tarefas de IA), a gestão automática e a mensagem de
  encerramento do programa.
- A barra de status, os avisos da bandeja e as dicas desenhadas à mão passam a ser traduzidos.
- Frases montadas na hora (com números, nomes e etapas no meio) e textos de várias linhas são
  traduzidos por partes; antes, nomes como "Segmentação abdominal" saíam pela metade.
- Conferido abrindo o programa em inglês e em espanhol e passando por menus, botões, janelas de
  Configurações e as IAs.

## 0.99.34 — correções: banco em inglês e cancelar as IAs
- **Banco vazio em inglês**: o filtro de modalidade "Todas" virava "All" e a busca procurava a
  modalidade "All". Corrigido para todas as listas suspensas: a tela mostra traduzido e o programa lê o
  original. Também valiam só em português: as permissões dos menus (importar, exportar, configurar) e a
  aba certa ao abrir uma página de Configurações.
- **Tarefas de IA que não cancelavam**: a segmentação pedida no visualizador era apagada ao fechar o
  exame, mas a tarefa ficava "rodando" para sempre, o exame "ocupado" (nenhuma outra IA rodava) e o
  Cancelar não fazia nada. Agora ela continua com o exame fechado e grava o resultado; o Cancelar
  sempre fecha a tarefa (à força, se o trabalho não parar em 15 s) e solta o exame.

## 0.99.33 — inglês como padrão
- O programa e o README passam a ter o **inglês** como padrão; português e espanhol continuam.
- O **instalador** do Windows pergunta o idioma na primeira tela (inglês marcado) e o grava para o
  programa; `instalar.bat` e `instalar.sh` também perguntam. A versão portátil pergunta ao abrir, com o
  inglês marcado. Quem já usava continua no idioma escolhido.
- Novo comando `ipe set-language en|pt-BR|es`.
- README: `README.md` em inglês (agora completo), `README.pt-BR.md` em português, `README.es.md`.
- As notas dos releases no GitHub saem em inglês.

## 0.99.32 — acompanhar as IAs
- **Tarefas de IA**: andamento (fila, montando, rodando, gravando, pronto, erro) e **cancelar**, também das
  que rodam sozinhas na chegada do exame. Pelo botão Aplicações, por Exibir e pelo aviso "⚙ IA: …" na
  barra de status. Cancelar não grava nada no exame.
- **Banco de dados**: ✦ no exame com resultado de IA (a dica diz quais) e ⚙ quando há IA na fila ou
  rodando; coluna **IA**.
- **Órgãos abdominais** no visualizador (botão próprio na TC/RM de abdome e no botão Aplicações).
- **Janelas de configuração** diminuem e maximizam (antes o mínimo era quase o tamanho da tela).

## 0.99.31 — onda A (ideias do Weasis ViewerHub e da Eden)
- **Laudo em andamento** no servidor central: quem abre o laudo fica com ele; o próximo escolhe só ler
  ou assumir (registrado), e o servidor recusa gravar laudo de quem não está com ele.
- **Abertura IHE IID** (`/IHEInvokeImageDisplay`, `requestType`) e filtros no link e na API:
  exames mais recentes, modalidades, período, descrição; vários IDs e UIDs.
- **Link ipe:// cifrado** (`c=`): sem dado do paciente à vista, montado com o token, vale 24 h.
- **Perfil de intensidade** ao longo de uma régua ou polilinha, com gráfico.
- **Tirar a mesa da TC** no MPR e no 3D.
- **Histórico do exame** no botão direito; **apagar uma imagem só**, com registro.
- **Fechar o exame sozinho** ao assinar o laudo ou depois de um tempo parado.
- **Modelo de laudo OIT** (pneumoconioses).

## 0.99.30 — configurações em três níveis
- **Protocolos de exibição e de mamografia, layouts da dinâmica, modelos de folha, modelos de laudo e
  listas de casos** passam a ser do serviço, compartilhados com escolhidos ou pessoais.
- Mudar um item do serviço sem permissão de configurar cria uma cópia pessoal que vale só para você.
- **Configurações ▸ Usuários ▸ Configurações pessoais e compartilhadas…** mostra e muda quem vê cada
  item; listas de casos têm **Visível para** no botão direito.
- Atalhos, mouse e presets: voltar ao padrão do computador ou tornar os seus o padrão.
- No modo cliente, o servidor guarda e confere tudo (listas pessoais de outro não são entregues).

## 0.99.29 — recolher os painéis do banco (como no Weasis)
- **Locais e listas** (esquerda) e **Séries e comentários** (direita) recolhem para uma tira na borda
  pelo botão ◂/▸ do título; um clique na tira traz de volta, do tamanho de antes. A lista de exames
  fica com a largura toda.
- O botão **Listas** e o menu **Exibir** abrem e recolhem os painéis; o estado fica guardado.

## 0.99.28 — banco pessoal no servidor ou neste computador
- **Modo cliente**: o painel Locais mostra o **Servidor central** e o **Banco deste computador**; o banco
  daqui abre sem rede e serve de banco de casos.
- **Botão direito ▸ Banco**: copiar ou mover do servidor para este computador, e enviar daqui ao servidor
  (no meu banco ou no compartilhado). Laudos, medidas, anotações e imagens-chave vão junto.
- **Exames que eu importo vão para "o meu banco neste computador"** (não sobem) ou para o meu banco no
  servidor (sobem já marcados).
- **Enviar um banco inteiro ao servidor** (migração do computador que virou cliente); o administrador
  manda cada exame para o banco do dono.
- **O servidor confere o banco**: exame pessoal de outro não aparece na busca, no DICOMweb nem nos pedidos.
- Trocar o modo de uso avisa o que muda com os exames.

## 0.99.27 — banco pessoal e compartilhado
- **Locais ▸ Banco**: tudo o que vejo, meu banco, compartilhado e compartilhados comigo; o administrador
  vê também o banco de cada usuário. Coluna **Banco** na lista.
- **Botão direito no exame ▸ Banco**: mover para o meu banco, para o compartilhado, compartilhar com…, e
  (administrador) passar para o banco de outro. O exame continua um só: só a marca muda.
- **Exame que chega no AE de uma identidade pessoal** vai para o banco do dono; o que você importa ou
  baixa segue a sua escolha ("Exames que eu importo ou baixo vão para").
- **Registro de acesso** quando o administrador abre o banco ou um exame pessoal de outro; passar o banco
  inteiro de quem saiu do serviço para outro usuário ou para o compartilhado.

## 0.99.26 — "Visível para" nas configurações
- **Nós DICOM, identidades, servidores de impressão, regras de impressão e do filme automático** ganham o
  campo **Visível para**: todos (do serviço), só eu, ou eu e usuários escolhidos. Item novo do
  administrador nasce do serviço; o dos outros, pessoal.
- Nas escolhas do dia a dia cada um vê o do serviço, o seu e o compartilhado com ele; o administrador vê e
  edita o de todos na tela de configuração ("de fulano"), sem que entre nas escolhas dele.
- Quem não configura o computador abre **Meus nós DICOM** (só nós e identidades, editando os seus).
- No servidor central, cada pedido de cliente enxerga o que aquele usuário vê.

## 0.99.25 — modo de uso no primeiro uso
- **Na primeira abertura o programa pergunta como vai ser usado**: só eu (abre sem login, sem criar
  ninguém), várias pessoas neste computador (cria o administrador ali), este computador é o servidor do
  grupo, ou conectar a um servidor. Vale para o instalador, o portátil, o `executar.bat` e o Linux — até
  aqui só o instalador do Windows perguntava, e o resto exigia criar usuário e senha.
- **Configurações ▸ Usuários ▸ Modo de uso** troca depois. Em "só eu" com usuários cadastrados, o
  programa entra como o escolhido.
- **Entrar com a conta do Windows/Linux**, sem senha, para quem tiver a conta ligada no cadastro do usuário.

## 0.99.24 — revisão de segurança
- **Link `ipe://` sem o token** não abre mais sozinho: pergunta antes (Rede ▸ Chamada externa, também
  "aceitar" ou "recusar"). Com `&token=` no link, abre direto. O token da API passou a ser comparado em
  tempo constante.
- **Nó DICOM**: nova opção "Só nós cadastrados, conferindo o IP do nó" — o AE Title sozinho qualquer
  computador da rede imita.
- **Impressora DICOM**: impressora nova aceita só da rede local (as já cadastradas continuam como estavam).
- **Servidor central**: 5 senhas erradas em 10 min bloqueiam o endereço por 10 min; aviso na tela e no
  console quando roda sem certificado (HTTP).

## 0.99.23.1
- Correção: ajustar a numeração da coluna (ex.: L5 sacralizada) mudava só a aba do clique; as outras telas do
  exame e uma cópia repetida do mesmo SEG continuavam com o nome antigo. Agora todas se refazem.

## 0.99.23 — vértebra de transição e a numeração da coluna
- **Correção:** subir um nível na lombar dava duas S1 (a lista de nomes acabava em S1). Agora a última
  livre vira S1, o sacro vira S2 e o disco S1-S2; renumerar para fora da coluna é recusado com aviso.
- **Numeração pela sequência física**, contada **a partir de C2** (na série ou em outra série do exame que
  pegue da C2 até ela) ou **pela última costela** (T12, na TC); só sem âncora valem os nomes da IA. Dois
  corpos com o mesmo nome viram dois.
- **Vértebra de transição** com os nomes lombarizada / sacralizada: S1 lombarizada (sacro como S2), L5
  sacralizada, L5 fundida ao sacro; transição toracolombar (L1 com costela, T12 sem costela) e contagem
  de pares de costelas. Indícios: disco rudimentar e **Castellvi sugerido** (apófise alta ou encostada
  na asa sacral).
- **Botão direito ▸ Numeração da coluna ▸ Ajustar…**: "esta vértebra é a…", transição, Castellvi e a
  frase para o laudo; grava no exame e avisa no próximo exame do paciente se a numeração sair diferente.

## 0.99.22 — rodada barata do plano AW: selos, mistura de pacientes, janelas, medidas e saída
- **Selos de integridade** no alto do quadro: mamografia comprimida com perdas sai em vermelho
  ("imprópria para o laudo", com método e taxa); compressão com perdas nas outras modalidades,
  Modality LUT em tabela (não aplicada), pixel não quadrado e imagem derivada. Clicar explica. A
  reconstrução herda o selo da série de origem.
- **Mistura de pacientes**: selo vermelho quando os quadros da tela têm pacientes diferentes; a
  chamada externa que traz outro paciente com um já aberto pergunta (fechar o anterior em todos os
  monitores, manter os dois, não abrir) — ou decide sozinha, em Rede ▸ Chamada externa; o filme
  pede confirmação antes de juntar pacientes.
- **Switch WL**: o menu da janela lista as janelas gravadas no arquivo (NORMAL, HARDER, SOFTER, VOI
  LUT) e a ação *Switch WL* percorre em ciclo; na mamografia, as incidências à vista juntas.
- **Janela digitada** e **"Guardar a janela atual como preset"**, com listas de presets por
  modalidade (RM, mamografia, PET…); as teclas 1–9 usam a lista da modalidade do quadro.
- **Paisagem** na subtração da dinâmica e na DSA (10–50% da anatomia de volta, para localizar o
  realce) e dois mapas novos na dinâmica: **MIP temporal** (maior realce em qualquer fase) e
  **média temporal**.
- **ROI de referência**: as outras ROIs da série mostram a média em % dela.
- **Régua 3D** (ponto A num corte, B em outro ou em outro quadro, com D-E/A-P/C-C), aviso de
  cortes grossos na direção da régua e de medida menor que a espessura, e incerteza opcional (±).
- **Estado do resultado de IA** (cefalometria, índices do crânio): automático, editado (\*) ou
  aceito por quem e quando — guardado com o exame, e a janela reabre como ficou.
- **Cópia (Ctrl+C)** com nível de anotação próprio e **carimbo mínimo** (série, janela, escala,
  processamento aplicado e selos graves).
- Correção: resposta do PACS (anteriores, salvar sem o silicone) que chegava depois de a aba fechar
  dava erro; agora é descartada.

## 0.99.21 — níveis linfonodais: base do crânio pelas jugulares
- No primeiro caso real (TC de pescoço, tórax e abdome de 15/09), a base do crânio saiu 9 mm acima
  do hioide: o "crânio" do TotalSegmentator traz a mandíbula. Agora a base do crânio (limite de cima
  dos níveis II e V) é o topo das jugulares internas (forame jugular) ou das carótidas internas; só sem
  elas usa o crânio, e só a parte de trás. Refaça o mapa desse exame.

## 0.99.20 — níveis linfonodais cervicais
- Botão **Linfonodos** (TC de pescoço): o TotalSegmentator acha os marcos (base do crânio, hioide,
  cricoide, manúbrio, clavículas, submandibulares, digástricos, carótidas, jugulares e
  esternocleidomastóideos — tarefas abertas) e o Ipê monta o mapa dos níveis I a VII, direito e
  esquerdo, pelas regras de imagem do estadiamento. O rótulo de cada nível aparece em qualquer plano.
- A lesão segmentada com a ferramenta Segmentar ganha o nível sozinha ("Linfonodo IIA E") e a regra
  que o decidiu.
- CAD/IA: automático na chegada. O mapa e os marcos ficam na SEG do exame e voltam ao reabrir.
- O instalar_segmentacao baixa também o modelo dos músculos do pescoço (headneck_muscles).

## 0.99.19 — bulbos olfatórios
- Novo roteiro em **Índices**: **Bulbos olfatórios**. Contorne o bulbo direito e o esquerdo em cada
  corte coronal T2; o volume é a soma das áreas × a distância entre os cortes (Cavalieri), em mm³.
  Contornar de novo o mesmo corte troca o anterior. Opcional: profundidade do sulco olfatório
  (abaixo de 8 mm sugere hipoplasia ou aplasia — Huart et al., 2011).
- Aviso quando os cortes estão a mais de 3 mm (volume pouco preciso para o bulbo).
- Sem automático: o modelo de IA de bulbo olfatório (Deep-MI) não tem licença publicada e pede T2 de
  0,8 mm do encéfalo inteiro.

## 0.99.18 — índices do crânio medidos na grade fina do SynthSeg
- No primeiro caso real (RM de Parkinson só com 2D de 5 mm), o 3º ventrículo saiu com 0,4 mm e o
  diâmetro do crânio não saiu: a medida era feita na grade da série, onde o 3º ventrículo cabe num
  corte só. Agora as medidas são feitas na segmentação de 1 mm que o SynthSeg produz de qualquer
  série; a SEG continua na grade da série.
- A série preferida não pega mais SWAN, fase, angio, perfusão nem reconstruções (o "3D" da lista
  tinha escolhido a 3D SWAN).

## 0.99.17 — índices do crânio automáticos (SynthSeg)
- No botão **Índices**: **Índices automáticos (IA, SynthSeg)** em RM de qualquer sequência ou TC de
  crânio — índice de Evans, largura do 3º ventrículo (média de três), ângulo calosal e volumes dos
  hipocampos (com assimetria), amígdalas, ventrículos e intracraniano.
- Mesma janela de conferência da cefalometria (agora comum às IAs de medida), com as linhas em
  qualquer plano; trocar os cornos ou o diâmetro refaz o Evans.
- Os roteiros MRPI 2.0, Evans e ângulo calosal já abrem com o que a IA mediu.
- CAD/IA: automático na chegada, com filtros e destinos. SEG e imagem de conferência no exame.
- SynthSeg pela versão em PyTorch da DIPY: o instalar_segmentacao acrescenta a DIPY e os pesos
  (rode uma vez de novo). Créditos: SynthSeg (Billot et al., 2023) e DIPY.

## 0.99.16 — cefalometria automática na chegada e linhas em qualquer plano
- **Configurações ▸ CAD/IA** ganhou a **Cefalometria do cavum**: automática quando a TC chega (pela
  rede ou importada), filtrada pela descrição do exame (CAVUM, RINOFARINGE, APNEIA…), com a série
  preferida, a espessura máxima, o mínimo de cortes e os destinos para mandar o resultado.
- Os números ficam guardados na imagem de conferência: ao abrir o exame, o botão **Cefalometria**
  abre a conferência direto, sem rodar de novo.
- As linhas das medidas aparecem em qualquer plano que as contenha — no sagital reformatado, no
  axial, no oblíquo — como sobreposição 3D, inclusive ao reabrir o exame. **Ver no quadro** (ou duplo
  clique) leva o quadro ativo ao plano e ao corte de cada medida.
- **Toda segmentação e IA em qualquer plano**: SEG (órgãos, cefalometria, CAD de fora) e RTSTRUCT,
  guardados corte a corte, viram um volume em mm na hora de desenhar num plano que não é o da
  aquisição — aparecem no sagital ou coronal reformatado e nas outras séries do exame. Vale para
  o que vier depois, sem fazer nada a mais.
- O submenu CAD/IA ganhou um item por ferramenta (segmentação abdominal, níveis da coluna, implante,
  cefalometria), cada um abrindo a página já na ferramenta.

## 0.99.15 — cefalometria do cavum automática
- Botão **Cefalometria** (TC de face, cavum e pescoço): o TotalSegmentator separa palato, faringe,
  hioide, mandíbula, língua e vértebras cervicais (tarefas abertas, só TC), e o Ipê faz as medidas
  dos laudos de apneia: área de secção transversal mínima **perpendicular ao eixo** da via aérea,
  com o local e a faixa; comprimento e espessura do palato mole; espaço aéreo posterior retropalatal
  e retrolingual; hioide ao plano mandibular (Go–Me); largura e comprimento da língua; nível do
  hioide na coluna.
- Janela de conferência: cada número com a referência e de quem é (automático ou editado); trocar
  digitando ou medindo à mão; referências editáveis; texto no formato do laudo. Sem a IA, a mesma
  janela é o roteiro manual.
- No exame: as estruturas (SEG) e uma imagem de conferência com o sagital mediano, as linhas de cada
  medida e o perfil da área ao longo do eixo.
- O instalar_segmentacao baixa também os modelos de cabeça e pescoço.

## 0.99.14 — medidas guiadas: MRPI, MRPI 2.0, Evans e ângulo calosal
- Botão **Índices** (RM e TC de crânio): um roteiro pede as medidas uma de cada vez, com a ferramenta
  e o plano certos, captura o que foi medido no quadro e faz a conta. MRPI e MRPI 2.0, índice de
  Evans e ângulo calosal.
- Plano e espessura do corte conferidos: medida fora do plano pedido ou em corte acima de 3 mm vira
  observação ao lado do número. O coronal oblíquo é aceito para o pedúnculo cerebelar superior.
- Referências como texto, com a fonte; o resultado vai para o laudo ou para a área de transferência.
- O mesmo motor vai servir à cefalometria do cavum.

## 0.99.13 — a história do Ipê e os créditos
- Ajuda ▸ Sobre o Ipê ganhou a origem do nome (os ipês de Brasília e o "ipe" de Filipe) e dois
  botões: **A história do Ipê** (em português, inglês e espanhol) e **Créditos e licenças**.
- Créditos com cada biblioteca, modelo de IA e ferramenta que o Ipê usa, a licença, o link e, quando
  os autores pedem, a citação (TotalSegmentator, nnU-Net, classificador de densidade da NYU).
- No GitHub: HISTORIA.md e CREDITOS.md; o README ganhou a seção "Por que Ipê?". O guia do usuário
  ganhou o capítulo "Sobre o Ipê".
- Regra daqui em diante: ferramenta nova entra nos créditos junto com o código — um teste reprova
  dependência ou import de terceiros sem crédito.

## 0.99.12 — menu Configurações e barra que se arruma pelo exame
- Novo menu **Configurações**, com um submenu por assunto (Visualizador, Protocolos de exame, CAD/IA,
  Monitores, Rede, Impressão, Banco de dados, Usuários, Sistema). Cada item abre a sua própria
  janela, só com aquele assunto. A janela completa de antes continua em "Todas as preferências"
  (Ctrl+,).
- Os menus Exibir, Rede, Impressão e Usuário ficaram só com ações; o que se configura mudou para o
  menu Configurações. O botão Configurações da tela inicial abre o mesmo menu.
- A barra do visualizador ganhou um bloco de **aplicações do exame** (MPR, 3D, Dinâmica, Fusão, MN),
  que aparecem só quando servem ao exame aberto: pela modalidade, pela região do corpo (do
  BodyPartExamined e das descrições) e pelo tipo de série (angio, T1 3D, T2 3D, dinâmica, volume).
- Botão **Aplicações**: lista todas, inclusive as que ficaram fora da barra, com o motivo, e elas
  rodam mesmo assim.
- Botão direito numa aplicação: Automático, Sempre ou Nunca, em todo exame ou só numa região.
- Configurações ▸ Visualizador ▸ Barra de ferramentas e aplicações: ordem e modos; Configurações ▸
  Protocolos de exame ▸ Regiões do corpo: o dicionário de termos, com caixa de teste.

## 0.99.11 — o DicomViewer passa a se chamar Ipê
- Nome novo, ícone novo (a flor do ipê-amarelo), código publicado no GitHub sob GPL-3.0.
- Compatibilidade com o nome antigo: a pasta de dados, o AE de fábrica `DICOMVIEWER`, os links
  `dicomviewer://` (o novo é `ipe://`), `python -m dicomviewer` e o instalador, que atualiza o
  antigo no lugar.
- Campos DICOM gravados pelo programa passam a dizer "Ipe" (sem acento); os gravados como
  "DicomViewer" continuam reconhecidos.
- Exames anteriores escolhidos em cima da tira de miniaturas (este exame, um anterior ou todos).
- Clique num quadro vazio de protocolo de exibição abre a lista de séries; a escolhida entra só
  naquele quadro, sem mudar o protocolo.

## 0.99.10 — sincronização automática ou manual
- O botão Sincronizar ganhou as linhas **Automática** (mesmo ponto do paciente) e **Manual**
  (mantém a diferença entre os quadros). Religar a automática alinha na hora pelo quadro ativo.

## 0.99.9 — anotações em quatro níveis, Ctrl+C, sincronização da RM e layouts da dinâmica
- Anotações da tela em quatro níveis (completa, parcial 1, parcial 2, ausente), escolhidas item a
  item nas Preferências.
- Ctrl+C copia o quadro como está na tela para a área de transferência, em alta resolução.
- Sincronização automática por modalidade, desligada de fábrica na RM; desligar o botão desliga de
  verdade.
- RM de mama dinâmica: parâmetros pré-configurados e layouts próprios (séries e cor por quadro).

## 0.99.8 — servidor Linux sem janela
- Pacote para servidor Linux (Ubuntu 24.04): o instalador deixa o programa rodando como serviço do sistema, recebendo exames e impressões mesmo sem ninguém conectado.
- Configurações e nós DICOM ajustáveis pela linha de comando (listar, acrescentar e remover nós; mudar uma configuração), sem abrir a interface.
- O serviço fecha de forma limpa quando o sistema o desliga e liga a impressora DICOM se ela estiver ativada.
- Regras de automação, gestão automática e identidades continuam sendo configuradas pela janela.

## 0.99.7 — ajustes depois do uso real
- Coluna: a IA só dá nome às vértebras; as medidas de altura do disco e da vértebra foram desligadas.
- As janelas abrem no centro da tela, com cerca de 80% da área útil do monitor de cada computador.
- Rolar com Ctrl segurado não pula mais vários cortes no primeiro movimento.
- A lista do banco se atualiza quando chegam exames sem perder o exame que estava selecionado.

## 0.99.6 — gestão automática, impressão e janelas
- Gestão DICOM: "Enviar o que falta para…" e "Enviar o exame inteiro para…" outro destino, com uma fila que mostra cada exame do lote com destino, andamento e resultado, e opção de parar.
- Gestão automática: regras com horário que conferem e reenviam o que está incompleto ou ausente, repetem a tentativa quando há erro e mostram o resultado na aba "Automático".
- Impressões DICOM que chegam folha a folha (mesma origem, mesmo paciente, em até 90 s) viram páginas de um trabalho só; há também o botão "Juntar como páginas".
- Novo menu Impressão, com "Acrescentar impressora DICOM…"; a Gestão DICOM também entrou no menu.
- Filme: botões Novo, Abrir, Salvar… e Imprimir…, com as opções reunidas nas janelas de salvar e imprimir; em monitor pequeno, os botões passam para a linha de baixo.
- Nó DICOM ou servidor de impressão novo vale na hora, sem reabrir a janela. Fechar o programa pede confirmação.

## 0.99.5 — coluna: medida mais robusta e duas sagitais
- As medidas da coluna ignoram pedaços soltos que a IA marcou com o nome de uma vértebra e não se encurtam por falhas dentro do corpo vertebral.
- Na RM, a medida pode usar duas sagitais; valores que discordam aparecem em vermelho para conferir.
- Aviso quando as duas sequências contaram os níveis de forma diferente.

## 0.99.4 — altura das vértebras e tira de séries ao vivo
- Altura dos corpos vertebrais (anterior, média e posterior) com graduação de fratura de T4 a L5, em tabela gravada no exame.
- A tira de séries do exame aberto se atualiza sozinha quando chega série nova, já com a miniatura.

## 0.99.3 — medida dos discos
- Altura e volume dos discos intervertebrais em tabela gravada no exame, destacando o disco bem menor que o de cima.
- Ao renumerar os níveis, a tabela é refeita com os nomes novos.

## 0.99.2 — níveis da coluna
- Identificação automática de vértebras e discos (TotalSegmentator) em TC e RM; o nome aparece em qualquer série e plano do exame.
- "Renumerar ±1" no botão direito do quadro, para corrigir a contagem.
- Pode ser pedida pelo banco, pelo quadro ou no automático (aba CAD/IA).

## 0.99.1 — CAD/IA também na importação
- O implante e a segmentação automáticos passam a rodar também em exames importados de pasta, arquivo ou ZIP, não só nos que chegam pela rede.
- A aba CAD/IA e o editor de protocolos de exibição ganharam o layout da aba Mamografia (lista à esquerda, configurações à direita).

## 0.99 — Preferências ▸ CAD/IA
- Aba nova com a segmentação abdominal e o implante de silicone, cada um com suas opções: automático na chegada, quais exames e séries, e para onde enviar o resultado.
- A segmentação pode rodar sozinha quando chega uma TC ou RM de abdome, escolhendo a série pela ordem de preferência.
- Implante: opção de só procurar quando o aparelho marca que há prótese.

## 0.98 — órgãos abdominais com o TotalSegmentator
- Segmentação de fígado, baço, rins, pâncreas, adrenais e vesícula (e outras estruturas opcionais) em TC e RM, pelo banco ou pelo botão direito do quadro.
- O resultado fica no exame: segmentação com um item por órgão e tabela de volumetria (mL, HU médio na TC, segmentos de Couinaud).
- A segmentação se instala à parte, uma vez; o pacote do programa não ficou mais pesado.

## 0.97 a 0.97.1 — implante corrigido na chegada
- Mamografia com prótese que chega ganha uma cópia sem o silicone como série nova do exame. A original não muda, e a cópia não vai ao PACS.
- "Apagar implante" no botão direito do banco, para exames já guardados.
- Na mamografia, zoom e pan só andam juntos com a sincronia ligada, como nos outros exames.

## 0.96 a 0.96.1 — implante: só corrigir; parede torácica
- O botão Implante (Alt+I) só corrige; a janela continua a de antes de tirar o silicone.
- Correção do lado da parede torácica numa linha de quatro incidências: a CCE e a MLOD saíam espelhadas.

## 0.95 — detecção do implante na mamografia
- Busca da prótese pela borda e pela forma, bem mais precisa que a anterior.
- Respeita as marcações do aparelho: não procura implante quando a tag diz que não há, nem em incidência com deslocamento (Eklund), compressão localizada ou magnificação.
- "Achar o implante a partir daqui" no botão direito.

## 0.94 — etapa com a avaliação dinâmica
- Uma etapa do protocolo de exibição pode abrir a avaliação dinâmica da mama (mapas e curvas) com o layout escolhido; ao sair da etapa, a dinâmica fecha.
- A etapa "Avaliação dinâmica" entrou no protocolo de fábrica da RM de mama.

## 0.91 a 0.93 — reconstruções 3D nos protocolos
- O quadro de uma etapa pode ser MIP 3D ou VR, com as vistas do 3D (anterior, direita, esquerda…).
- Os MIPs de meia mama de fábrica passaram a ser 3D, com o mamilo de cada mama virado para fora.
- Toda reconstrução de etapa (MPR, MIP, MinIP, média) vira 3D ao usar a barra do 3D; "Voltar à série" desfaz.

## 0.90 — MIPs de meia mama por fase
- Na etapa, o quadro escolhe a fase da dinâmica (pré, 1ª a 9ª pós ou última) e só metade da mama.
- Etapa de fábrica em 2×2 com MIPs da 1ª e da 3ª fase pós-contraste, mama direita e esquerda.

## 0.89 — OCR no filme montado com as imagens da porta
- O filme montado com imagens mandadas à porta da impressora também é identificado por OCR; sem identificação, fica "Esperando paciente".

## 0.88 — protocolos de exibição com etapas
- Protocolos de exibição com etapas para TC, RM e outros, como na mamografia: layout, séries preferidas, plano, MIP/MPR, janela, cor e sincronia por quadro; ← → passam de etapa.
- Barra com a lista de etapas, "Gravar a tela como etapa…", "Editar protocolos…" e "Sair do protocolo".
- Protocolos de fábrica: TC de tórax, RM de mama e RM de crânio.

## 0.87 — OCR na chegada mais completo
- O OCR lê o nome também no rodapé, na folha inteira e nas caixas de anotação.
- A coluna Situação diz por que o filme está parado: aparelho sem cadastro, origem desligada, nenhuma regra ou esperando paciente.

## 0.86 — filme automático por regras
- A aba Automático (exames mandados pela modalidade) usa regras por origem, AE que recebeu e modalidade, cada uma com grade, destino e modelo.

## 0.85 — regras de impressão por listas
- Regras de impressão montadas marcando listas de origem, servidor que recebeu e modalidade; a aba Regras virou tabela.

## 0.84 — impressão em lote e módulos
- Modalidade em cada impressão recebida e regras por modalidade.
- Histórico de envios por impressão e "Reimprimir…" em lote.
- Limpeza automática da lista de impressões por idade, modalidade e origem.
- Preferências ▸ Módulos: desliga MN, mamografia, 3D, dinâmica ou impressão — a ferramenta some, os dados ficam.

## 0.83 — duplicar configurações
- "Duplicar…" em servidores, destinos, regras, modelos de folha e impressoras DICOM.
- O painel de filmes conta também as impressões que chegaram prontas por DICOM Print.
- Correção: editar um servidor ou destino não apaga mais configurações dele.

## 0.82 — lista de impressões como o banco
- Colunas que se filtram, ordenam, arrastam e escondem; pré-visualização também do filme feito no compositor.

## 0.81 — OCR na chegada da impressão
- A impressão DICOM recebida é identificada por OCR ao chegar e segue a regra; sem paciente identificado, fica "Esperando paciente".
- A porta da impressora aceita também imagens comuns e monta um filme por exame.

## 0.80 — OCR embutido
- OCR dentro do programa, sem internet e sem instalar nada à parte.
- A janela Identificar paciente mostra o texto lido e os pacientes do banco que combinam, com porcentagem.

## 0.79 — correção de queda
- Correção da queda ocasional ao refazer a tira de séries. Guia do usuário em PDF reescrito.

## 0.78 — compositor do filme
- Botão esquerdo no filme como Janela, Mover ou Zoom; trocar imagens de lugar pela alça ⠿.
- Anotações do filme que se movem, editam, mostram e escondem; caixa "também no exame" ao lado de Salvar.

## 0.77 — painel de filmes e impressões
- Filmes, % impressos e tempos (exame → filme → impressão), com filtros, gráficos e exportação para CSV.

## 0.76 — F1/F2 no visualizador
- No visualizador, F1 manda a imagem do quadro ao filme e F2 manda a série.

## 0.75 — guia em PDF
- Ajuda ▸ Guia do usuário (F1) abre o guia em PDF.

## 0.74 — mamilo marcado primeiro
- Na lesão de mama (RM), o mamilo pode ser marcado antes; a distância sai na hora e vale para as outras lesões da mesma mama.

## 0.72 a 0.73 — envio de exames e séries
- "Enviar para… como" no botão direito da tela do PACS; se o exame ainda não estiver aqui, é baixado e enviado sozinho.
- Envio só das séries selecionadas, pelo botão direito no banco.
- Correção: as setas ← → trocavam de aba em vez de passar a etapa.

## 0.71 — filme gravado no exame no formato da AW
- O filme pode ser gravado no exame como na AW: o arranjo, as imagens soltas e as folhas prontas.

## 0.70 — cópia anonimizada no banco
- Ao anonimizar, escolher entre exportar ou criar uma cópia anonimizada no próprio banco, como outro exame. O original não muda.

## 0.69 a 0.69.1 — dinâmica e "Baixar para"
- A série que faz parte de uma dinâmica sempre abre como dinâmica.
- "Baixar para" na tela do PACS: o exame vai do nó direto ao destino escolhido, sem passar por este computador.
- A captura da lesão e outras séries geradas pelo programa aparecem com miniatura.

## 0.68 — a lesão em todas as séries
- A segmentação da lesão de mama aparece em qualquer série e plano do exame e não some ao salvar.
- A captura mostra o plano inteiro, sem zoom, com a 2ª fase da dinâmica.
- Mapa, subtração e fase da dinâmica em axial, coronal, sagital ou oblíquo.

## 0.67 — lesão de mama: limiar, captura e edição
- Na lesão de mama, fica só a distância ao mamilo (pele e peitoral saíram).
- Barra do limiar para incluir mais ou menos na segmentação, com atualização na hora.
- "Salvar captura (SC)…" em 2×2 (sagital, coronal, axial e curva de realce), com as medidas no rodapé.
- A lesão pode ser editada pelo painel de medidas.

## Novidades da 0.66 — Gestão DICOM: os exames das modalidades estão no PACS?

Botão **Gestão** na tela do banco de dados. É a conferência diária feita à mão (exame por exame,
série por série) e o envio que antes passava pelo OsiriX, num lugar só:

1. **Modalidades**: marque os nós que serão conferidos e, para cada um, **como** falar com ele (a
   identidade — por exemplo o AE do OsiriX, quando a modalidade só aceita esse).
2. **PACS**: o nó onde os exames têm de estar, a identidade, o **destino do C-MOVE** (normalmente
   o AE do próprio PACS) e **como enviar**:
   - *Direto*: o programa pede à **modalidade** que mande ao **PACS** (C-MOVE com destino o PACS).
     Nada passa por este computador. A modalidade precisa ter o PACS na tabela de destinos dela —
     quem aceita ou recusa o destino é ela, não este programa.
   - *Pelo computador*: baixa da modalidade para cá (C-GET, ou C-MOVE para este computador) e
     reenvia ao PACS (C-STORE), com a identidade escolhida para o PACS.
   - *Direto; se a modalidade recusar, pelo computador* (padrão).
3. **Conferir** (hoje, ontem, 7 dias ou datas). Cada exame sai como ✔ completo, ◐ incompleto
   (quais séries faltam e quantas imagens), ✖ ausente no PACS, ≠ no PACS com outro UID (mesmo
   accession) ou ? sem contagem. Séries que a modalidade guarda e não manda de propósito (ex.:
   *Patient Protocol*) podem ser ignoradas; *imagem por imagem* diz exatamente quais imagens faltam.
4. **Enviar o que falta ao PACS** manda só as séries e imagens que faltam; depois o exame é
   **conferido de novo** sozinho. **Testar o nó selecionado** diz o que a modalidade sabe fazer —
   inclusive se ela conhece o PACS como destino — sem enviar nada. **Exportar CSV** abre no Excel.

Tudo o que foi escolhido fica guardado para a próxima vez, e cada conferência e cada envio vão para
o registro de auditoria.

## Novidades da 0.37 — você escolhe em que imagens cada análise roda

Em *Arquivo ▸ Análises: onde cada uma roda*. Cada serviço tem aparelho e protocolo diferentes:
"mamografia 2D" num lugar é `ViewPosition = CC`, em outro é uma descrição de série escrita à mão,
em outro a incidência só aparece no texto. Em vez de o programa adivinhar, a regra é sua.

- Uma regra é um conjunto de **critérios ligados por E** (modalidade, descrição da série,
  incidência, lado, parte do corpo, aparelho, estação, tipo de imagem, número de quadros,
  processamento). **Várias regras são um OU** — serve para "as CC e as MLO", ou para acomodar o
  protocolo do aparelho antigo ao lado do novo.
- Comparações: contém, não contém, é igual, é diferente, começa com, é um de (lista) e expressão
  regular. Expressão inválida não derruba a análise: ela só não combina.
- **Os valores oferecidos saem do seu acervo.** O campo "descrição da série" mostra as descrições
  que existem no seu banco, com quantas séries cada uma tem. Você escolhe o que tem, em vez de
  digitar de memória.
- **Prévia honesta**: a janela diz quantas séries e quantos exames a regra pega no seu acervo —
  e, quando a regra olha algo que só existe dentro do arquivo (incidência, número de quadros),
  diz isso e avisa que o número é o **limite de cima**. Contar zero por falta de dado seria pior
  que não contar.
- **Regra sem critério não pega nada**, de propósito: uma regra vazia que pegasse tudo rodaria o
  modelo no acervo inteiro. A janela recusa salvar e explica.
- Dá para desligar uma regra sem apagar, duplicar para variar um detalhe, e **restaurar o padrão**.

**0.37.1 — OU dentro da regra.** Antes o OU só existia *entre* regras, e "é um de" compara
igualdade exata — então "séries que contenham **v-preview OU proc**" não tinha como ser escrito.
Agora cada critério traz uma coluna **E / OU**: o primeiro não se liga a nada, os seguintes
escolhem. O **E amarra mais forte que o OU**, como em qualquer linguagem — "A e B ou C" é
"(A e B) ou C" —, e isso está na dica da coluna, porque regra ambígua em cima de imagem de
paciente não serve. Entrou junto a comparação **contém um de (lista)**, que resolve esse mesmo
caso numa linha só.

A densidade mamária já vem com uma regra de fábrica — mamografia 2D, *For Presentation*, um quadro,
CC ou MLO. Ela é o exemplo, não o limite: o mecanismo é da análise, não do modelo, e a próxima
análise entra na mesma tela.

## Novidades da 0.36 — o instalador pergunta quem usa este computador

Uma pergunta só, durante a instalação: **só eu uso** ou **mais de uma pessoa usa**.

- **Só eu uso**: o programa abre direto, sem pedir login e senha, com todas as permissões.
- **Mais de uma pessoa**: o primeiro acesso cadastra o administrador e daí em diante pede login,
  como antes.

**O cadastro de usuários continua inteiro nos dois casos** — perfis, permissões e registro de
acesso estão lá, em *Usuário ▸ Usuários*. A escolha não é uma chave escondida: ela vale **enquanto
não houver ninguém cadastrado**. No dia em que você cadastrar o primeiro usuário, o login passa a
ser pedido na abertura seguinte, sozinho. É assim que se muda de ideia, e é a única maneira — não
há duas fontes de verdade sobre isso. A tela de usuários avisa em que modo o computador está e diz
exatamente essa frase.

Por baixo: `ipe-cli set-mode single|multi`, que o instalador chama conforme a resposta.
No modo cliente (servidor central) a escolha é ignorada — lá quem manda é o servidor.

## Novidades da 0.35 — compressão automática, sem perda, com conferência

O relatório da 0.34 disse que **100% do acervo está sem compressão** e que JPEG-LS renderia
2,43:1. Esta versão faz a conversão — com as garantias que uma função que reescreve arquivo de
paciente precisa ter.

Em *Arquivo ▸ Relatório do acervo*, no fim da janela: **Comprimir sozinho os exames guardados há
mais de N dias**. O prazo conta da **entrada do exame no sistema**, não da data do exame — senão um
exame de 2019 importado hoje seria comprimido no mesmo dia.

**O caminho de cada arquivo, sem atalho:**

1. só entra arquivo **sem compressão**, de exame que passou do prazo, do tamanho mínimo;
2. comprime numa cópia, em arquivo temporário **na mesma pasta**;
3. **lê o temporário de volta do disco** e compara **pixel a pixel** com o original, mais os
   identificadores — se não for idêntico, apaga o temporário e **não troca nada**;
4. só então substitui, com uma troca atômica: ou está o arquivo antigo, ou o novo, nunca meio;
5. atualiza o banco (formato e tamanho).

**O que a conferência pegou, e que ninguém veria sem ela:** o `compress()` do pydicom **gera um SOP
Instance UID novo**, mesmo sem perda. No seu acervo isso seria um desastre silencioso — o banco
indexa por SOP Instance UID, e imagem-chave, lesão, laudo e segmentação apontam para ele; todos
ficariam órfãos, sem erro nenhum na tela. Sem perda os pixels são os mesmos, então pelo padrão o
objeto continua sendo o mesmo objeto: o programa devolve o UID original antes de gravar, e um teste
trava isso.

**Outras garantias**, todas com teste próprio: exame **aberto numa aba ou ainda baixando** fica de
fora; exame **protegido** fica de fora (dá para desligar); arquivo que o codificador recusa
continua exatamente como estava; ruído puro, que **cresce** ao ser comprimido, mantém o original;
parar no meio nunca deixa arquivo pela metade, e os dois formatos convivem no mesmo acervo sem
problema.

A janela mostra quantos arquivos já passaram do prazo e quanto somam, e o botão **Comprimir agora**
faz o lote do acervo antigo, com barra e botão de parar. Depois disso a passagem acontece sozinha,
90 segundos após abrir o programa e a cada 6 horas, no máximo 400 arquivos por vez para não ocupar
o disco o dia todo. **Desligada até você ligar.** Só sem perda: compressão com perda cria objeto
novo e é outra conversa.

## Novidades da 0.34 — relatório do acervo e fila dos filmes parados

**Relatório do acervo** (menu *Arquivo ▸ Relatório do acervo*). Responde três perguntas antes de
qualquer decisão sobre compressão: o que você tem, em que formato está gravado, e quanto cada
compressão renderia **no seu acervo** — não a média da literatura.

- **O levantamento é instantâneo**: sai de uma agregação no banco, sem abrir arquivo nenhum.
  Arquivos, tamanho e bytes por pixel, por formato de gravação e por modalidade. O número que
  entrega tudo é o **bytes por pixel**: perto de 2,0 é 16 bits crus, sem compressão.
- **A medição abre uma amostra pequena** de arquivos seus — dois ou três por modalidade, de séries
  diferentes — comprime **em memória** e joga fora. Nenhum arquivo é alterado, nada é gravado.
  Dá para parar no meio, e o que já foi medido continua valendo.
- **Só mede o que ainda está sem compressão.** Recomprimir o que já está comprimido mediria o
  trabalho errado.
- **Diz o que este computador não consegue gravar**, e o pacote que falta, em vez de omitir a linha.
- Abaixo da tabela, em texto: compressão com perda **cria um objeto novo** (SOP Instance UID novo,
  ImageType DERIVED) e nunca substitui o original, e no Brasil a taxa aceitável é avaliação do
  radiologista (CFM 2.107/2014). O programa dá o número; quem decide é você.
- Exporta tudo em CSV.

**Medido no acervo real do IMEB** (16.031 arquivos, 10,7 GB) enquanto esta versão era escrita:
**100% está sem compressão**, 1,96 bytes por pixel, nenhum arquivo marcado como comprimido com
perda. RM 37%, TC 32%, mamografia 24% (só 110 arquivos, mas 2,5 GB — é a tomossíntese). Nas amostras:
**JPEG-LS 2,43:1, JPEG 2000 2,41:1, RLE 1,85:1** — ou seja, sem perda nenhuma, **10,7 GB caberiam
em 4,4 GB**. O JPEG-LS entrou como dependência nesta versão (`pyjpegls`): o pydicom lê JPEG-LS com
as bibliotecas que já estavam aqui, mas só **grava** com ela.

**Fila dos filmes parados** (botão *Filmes parados…* na aba de impressões). Filme parado é filme que
a modalidade mandou e ninguém viu sair. Ficar parado é de propósito enquanto o aparelho não tem
cadastro — mas só é aceitável enquanto estiver visível e for fácil de soltar.

- Uma linha **por aparelho**, com trabalhos, folhas, imagens, desde quando está parado e **por que**:
  origem sem cadastro, origem desligada, sem regra nem destino fixo, ou pronto para liberar.
- **Liberar em lote**: os de um aparelho, ou todos os que já estão prontos. Cada um sai pelo mesmo
  caminho do encaminhamento automático — não existem dois jeitos de mandar um filme.
- A faixa âmbar da aba de impressões passou a contar as duas coisas: origens esperando cadastro e
  trabalhos esperando liberação.
- A situação vem com símbolo (**✔** / **⌛**) além da cor, que é o que sobrevive a qualquer tema.

**0.34.1 — o botão que não aparecia.** O usuário não achou a fila. Dois defeitos meus, e o
segundo é o que importa: `refresh()` montava a faixa de aviso **antes** de gravar a lista nova,
então ela contava a lista da vez anterior — na primeira abertura, a lista vazia. A contagem dava
zero, a faixa não aparecia e o botão, que só aparecia quando havia algo parado, também não. E
botão que some quando não há nada é botão que o usuário nunca encontra: agora **Parados…** fica
sempre na barra da aba de impressões, com o número entre parênteses quando há algo
(*Parados (8)…*), e a janela, quando não há nada, abre dizendo que não há nada. O filtro da lista
também ganhou **Parados, esperando liberação**. Três testes travam os três caminhos — inclusive um
que falha se a faixa voltar a ser calculada antes da lista.

**0.34.2 — a aba de impressões não fechava.** O X estava lá e não fazia nada: `_close_tab` sabia
fechar aba de exame e **saía calado** em qualquer outra. Agora fecha qualquer aba que tenha o X — só
o Banco de dados não fecha, e por isso ele nem tem o botão. A aba de Impressões fica guardada e
volta inteira quando você abrir de novo.


## Novidades da 0.33 — instalador do Windows, sem administrador

O programa virou um pacote que se instala sozinho. **Não pede administrador em momento
nenhum**: vai para a pasta do usuário (`%LOCALAPPDATA%\Programs\DicomViewer`), registra o
link `ipe://` só para quem instalou, e por isso funciona em máquina de serviço com
conta limitada.

- **`installer\build_windows.bat` faz tudo**: monta um ambiente separado, gera o ícone,
  empacota com o PyInstaller, **confere o pacote**, compacta o portátil e, se achar o Inno
  Setup, gera o instalador. Duplo clique e esperar.
- **A conferência é o passo que importa.** Antes de gerar qualquer coisa para distribuir, o
  `verifica.py` abre o executável empacotado, exige que os três idiomas estejam dentro, gera
  **180 exames de teste e importa todos num banco novo** — TC, RM, MN, mamografia, tomo. Se
  um decodificador de imagem comprimida tiver ficado de fora do pacote, isso aparece aqui, na
  sua máquina, e não no computador de quem recebeu. Falhou, não sai pacote.
- **Dois executáveis dentro do pacote**: `Ipe.exe` é a interface, sem a janela preta
  de console atrás; `ipe-cli.exe` são os comandos de linha (`info`, `import`,
  `server`, `register-url`). No Windows um programa de janela não tem saída padrão, e um
  `print` sem para onde ir derruba o processo — daí a separação.
- **Sai também um portátil** (`Ipe-<versão>-portatil.zip`): descompactar e rodar, de
  pendrive inclusive, sem instalar nada.
- **Desinstalar não apaga o seu banco, nem exames, nem configurações.** O desinstalador tira
  o programa e o registro do link; os dados ficam na pasta de dados do usuário, porque são
  seus. Quem quiser apagar faz pela tela de locais. Atualizar é rodar o instalador novo por
  cima — o banco migra sozinho na abertura.
- O ícone do Windows é gerado do desenho que já existe dentro do programa, em sete tamanhos,
  então o atalho não fica borrado na barra de tarefas.

O passo a passo está em `installer/LEIAME.md`.

**0.33.1 — o `.bat` não abria.** Na primeira tentativa o usuário rodou
`build_windows.bat` e *nada aconteceu*: a janela piscou e fechou. Dois defeitos meus, os dois
invisíveis em Linux. O arquivo estava com **quebra de linha do Unix**, e o `cmd.exe` do Windows
engasga com isso — não dá erro, só desiste. E `pip install … pyinstaller>=6.0` sem aspas: no
`cmd` o `>` é redirecionamento, então o PyInstaller nunca era instalado e nascia um arquivo
chamado `=6.0`. Corrigidos, junto com: o script agora **avisa e espera** em vez de fechar calado
(todo erro passa por uma mensagem e um `pause`), aceita `python` quando o lançador `py` não está
instalado, e mostra a pasta e a versão do Python logo no começo. **Não precisa de administrador**
— nem para rodar, nem para instalar o Python (escolha *Install for me only*).

**0.33.2 — o terceiro e último tropeço do `cmd`.** `for /f ('"caminho\com aspas" -c "…"')`
quebra o comando no primeiro espaço depois das aspas, e não há quoting que resolva de forma
confiável. A leitura da versão passou a ser: o Python grava num arquivo temporário, o `set /p`
lê. Com isso o build completou na máquina do usuário — **199 MB de pacote, 94 MB de ZIP
portátil**, conferência incluída.

## Novidades da 0.32 — exportar modelo 3D em cinco formatos, com laudo da malha

A janela de superfície virou **Exportar modelo 3D**. Ela junta num modelo só as estruturas
que interessam, cada uma com nome e cor, e diz o que a malha é antes de gravar.

- **Cinco formatos**: **STL** (impressão 3D, universal), **OBJ + MTL** (Blender, MeshLab,
  3D Slicer), **PLY** com cor por vértice, **glTF/GLB** — um arquivo só que abre no
  navegador, no visualizador do Windows e no PowerPoint — e **3MF**, o formato novo de
  impressão, que guarda a escala em milímetros e a cor.
- **Várias peças num arquivo só.** Osso, vaso e lesão, cada uma com nome e cor própria,
  abrindo já separadas no Blender ou no navegador. STL não guarda nome nem cor, então com
  mais de uma peça ele grava um arquivo para cada — e a janela avisa.
- **De onde o modelo sai**: do limiar (osso, pele, metal), da segmentação aberta, das
  segmentações guardadas no exame — uma peça por lesão, com a cor que ela já tem — e do
  **que está na tela do 3D**, já com o corte pelo plano, a maca tirada e a escultura do laço.
- **Laudo da malha antes de gravar**: quantos triângulos e vértices, tamanho em milímetros,
  volume fechado em mL, se a malha está fechada, quantas arestas ficaram sem par, quantas
  peças soltas existem e para que lado as faces olham. No fim, uma frase: *pronto para
  impressão 3D* ou *confira o que está marcado acima*. Exporta de qualquer jeito — quem
  decide é você.
- **Enxugar a malha**: junta vértices vizinhos e reduz a contagem de triângulos para a
  fração que você pedir, sem mudar a peça. É o que torna o arquivo leve o bastante para
  mandar por e-mail ou pôr numa apresentação.

**Correção importante, que vale para quem já exportou STL:** as faces saíam com a
orientação trocada em dois dos três eixos. A malha fechava, mas o volume com sinal dava um
terço do certo e o fatiador via a peça do avesso. Agora um cubo de 10 voxels em voxel de
1 mm dá exatamente 729 mm³, com as normais para fora. **STL exportado antes da 0.32 vale a
pena gerar de novo.**

## Novidades da 0.31 — o filme da estação AW vai para as Impressões

Os exames da GE chegam com duas séries que **não são do exame**: `AW electronic film`, as
imagens que o técnico jogou na folha, e `AW electronic pages`, a folha já montada. Até
agora elas apareciam misturadas com as séries de verdade no visualizador.

- **Somem do visualizador.** O programa reconhece as duas pelo nome da série e tira as duas
  da lista: não entram na tira, não entram no hanging, não contam como série do exame. No
  banco continuam como estavam — nada é apagado.
- **Aparecem na aba Impressões**, como um trabalho por exame: "2 folhas, 3 imagens", com o
  paciente, a data e a coluna de origem dizendo **"veio no exame (estação AW)"**. O filtro
  de cima ganhou a opção **"Filme que veio no exame"**.
- **Dá para ver e reimprimir.** A folha da AW já vem montada, então cada página vira uma
  folha de uma caixa só, com os pixels exatamente como vieram — a pré-visualização, o envio
  para impressora DICOM, o PDF e a impressora do computador passam pelos mesmos caminhos do
  que chega pela impressora DICOM do programa.
- Quando o exame traz só as imagens soltas, sem a folha montada, o trabalho é feito com
  elas e **a lista diz isso** em vez de fingir que tem folha.
- Apagar da lista não mexe nesses: o filme é do exame. O programa explica isso em vez de
  fingir que apagou.

A lista de impressões abre pelo botão **Impressões** na barra do Banco de dados (ao lado de
*Imprimir*), por **Arquivo ▸ Impressões (recebidas e montadas aqui)…** ou por **Ctrl+Shift+P**.
Ela vira uma aba ao lado de *Banco de dados*.

## Novidades da 0.30 — escala de cores editável, barra por modalidade e comparar exames

Três pedidos que mudam o dia a dia.

**Os números da escala de cores agora são campos.** Sempre que a barra de cores aparece,
os valores das duas pontas são clicáveis, onde quer que a barra esteja no quadro. Clicar
abre um campo para digitar o valor; clicar e arrastar ajusta na hora. **Só a ponta que
você pegou se mexe** — a outra fica exatamente onde estava, que é a diferença entre
ajustar a escala e refazer a janela inteira. Em PET com SUV ligado, o valor digitado é o
SUV que está na tela; o programa converte sozinho.

**A barra de ferramentas segue a modalidade.** O botão de MN só aparece em exame de
medicina nuclear; 3D, MPR e Fusão só onde há pilha de cortes (TC, RM, PET, MN); a
avaliação dinâmica só em ressonância. A barra da mamografia já era assim. Quem preferir
a barra cheia liga **"Mostrar todos os botões"** nas preferências — e, num exame sem
modalidade reconhecida, nada é escondido.

**Dois exames abertos juntos, direto da lista.** Selecione dois (ou mais, até seis) e
abra: eles entram **na mesma aba**, o mais recente como atual e os outros como anteriores,
com a série equivalente já ao lado e a sincronização de sempre. O menu do botão direito
tem as duas opções, "Abrir juntos, para comparar" e "Abrir cada um em sua aba".

- **Antes de juntar, o programa confere a identidade.** Nome, ID, data de nascimento e
  sexo. Havendo qualquer diferença, ele mostra **o que difere, lado a lado**, e pergunta
  se você quer continuar mesmo assim. Diferença só de caixa ou do `^` do DICOM não conta
  como diferença — "SOUZA^Ana" e "souza^ana" são a mesma pessoa.
- Cancelando, nada é aberto e a barra de estado diz por quê. Continuando, a barra avisa
  que as identidades diferem — o aviso não some depois do clique.

## Novidades da 0.29 — onde o corte da tomossíntese está dentro da mama

A estação de trabalho mostra num canto um desenho pequeno com o relógio da mama e a mama
comprimida de perfil, marcando onde o corte que está na tela cai entre o detector e a pá.
Agora o programa mostra o mesmo — e com um detalhe a mais: **dá para arrastar o marcador**
e saltar direto para aquela profundidade.

- **Nada é chutado.** A profundidade vem da posição de cada corte gravada no arquivo, a
  espessura vem do `BodyPartThickness`, a força da compressão e a descrição da pá vêm
  junto, e a inclinação do desenho é o ângulo real do braço — 0° na CC, 45° na MLO.
  Conferido nos exames do Pristina: os 19 volumes de tomossíntese testados leram certo o
  lado, o ângulo, a espessura e o passo entre as lajes.
- **O relógio é de frente para a paciente**, que é a convenção do laudo: a hora que
  aparece é a hora que você escreve. Como o significado de 3 h muda de mama para mama, as
  letras **M** e **L** (medial e lateral) ficam escritas ao lado do círculo.
- **Canto externo, sempre.** O indicador fica no canto de baixo do lado oposto à parede
  torácica: à esquerda nas mamas direitas, à direita nas esquerdas. O programa descobre
  isso da própria imagem, então continua certo mesmo se você espelhar o quadro.
- **Arrastar navega.** Clicar em qualquer ponto da faixa leva ao corte daquela
  profundidade; arrastando, a tomo acompanha. É o atalho para ir direto à pele ou ao
  fundo sem rolar a roda, e a barra de estado mostra corte, profundidade, espessura da
  laje, força e pá.
- **A faixa é a reconstrução inteira**, porque é isso que dá para rolar — ela costuma
  passar da mama (80 mm de cortes para 72 mm de compressão é o comum). A **pá ganha uma
  marca tracejada** no lugar certo, então dá para ver quando você já saiu da mama.
- Quando o arquivo não traz a posição de cada corte, a profundidade é distribuída pela
  espessura e o desenho **diz que foi estimada**, em vez de fingir precisão. O indicador
  pode ser desligado nas preferências.

## Novidades da 0.28 — o 3D virou um quadro do layout

O 3D não abre mais em janela separada. Ele passou a ser **um quadro como os outros**: entra
no 1×2 e no 2×2, fica ao lado do axial, vai para o filme, vira imagem-chave e aceita o botão
direito. Quem quiser o 3D em tela cheia usa o layout 1×1, como faria com qualquer série.

- **Esquerdo gira, roda aproxima a câmera, meio move.** No VR e na superfície o direito ajusta
  o limiar; no MIP, MinIP e média o direito continua sendo a janela do quadro, igual ao resto
  do programa. A barra verde em cima mostra modo, preset, opacidade, cor e os botões de vista,
  corte, escultura e giro; o rodapé do quadro diz o ângulo e o que está ligado.
- **Clicar no 3D leva os cortes até o ponto.** O raio sabe onde bateu na superfície, então o
  clique devolve a coordenada em milímetros: o axial, o coronal e o sagital saltam para a
  lesão clicada, e uma cruz azul marca o ponto no próprio 3D. O caminho inverso também vale —
  mover o cursor nos cortes marca o ponto no 3D.
- **Corte oblíquo, arrastado com o mouse.** Além dos seis lados anatômicos que já existiam,
  agora dá para cortar **pelo plano do olhar**: o plano nasce no cursor, perpendicular a como
  você está vendo, e sobe e desce com o botão esquerdo. Como a vista pode estar em qualquer
  ângulo, o corte é oblíquo de verdade — é o que abre uma articulação ou mostra o miolo do
  crânio.
- **Tirar a maca e esculpir à mão.** A mesa da TC é reconhecida pelo desenho que ela tem em
  todo exame — a primeira coisa sólida vindo de trás, fina, com ar entre ela e as costas — e
  sai do volume com um clique. Onde esse desenho não aparece (paciente em pruno, RM, PET) o
  programa **diz que não achou** em vez de apagar o que não devia, e aí vale o laço: desenhe
  em volta e escolha apagar o que está dentro ou guardar só o que está dentro.
- **Mais rápido.** O raio agora começa colado no objeto em vez de atravessar o vazio, e para
  assim que a superfície foi encontrada ou a opacidade fechou; ao arrastar, o quadro é
  desenhado menor e ampliado. Num volume de 200³ a 420 pixels, o VR caiu de 1,11 s para
  0,67 s (0,08 s enquanto gira) e a superfície, de 3,55 s para 1,53 s. Tudo em CPU, sem
  dependência nova.

## Novidades da 0.27 — de onde veio cada impressão

O sistema já recebia trabalhos de impressão de vários aparelhos, mas na lista todos apareciam
do mesmo jeito. Agora cada trabalho traz **a origem de onde ele veio**, e a origem é um cadastro
com nome amigável.

- **A identidade da origem é o trio AE + endereço + servidor que recebeu.** Dois aparelhos com o
  mesmo AE Title em salas diferentes continuam separados, que é o caso comum em serviço com mais
  de uma sala. Se o mesmo aparelho aparecer com um segundo endereço (troca de rede, IP novo), a
  tela oferece **"É o mesmo aparelho"** e junta os dois endereços em um cadastro só.
- **Origem nova entra na lista de pendentes e o trabalho fica parado.** Nada é encaminhado
  sozinho enquanto o aparelho não tiver nome. A aba de impressões mostra uma faixa âmbar com
  quantas origens esperam cadastro e um botão que leva direto para lá. É o mesmo princípio de
  sempre: **nada sai sozinho por padrão**. Quem preferir o comportamento antigo desliga a
  retenção nas configurações.
- **Cadastrar é dar um nome.** A tela já sugere um a partir do AE Title e do endereço; dá para
  trocar, escrever uma observação (a sala, o andar, quem usa) e desligar uma origem sem apagá-la.
  **Esquecer** só some com o cadastro — os trabalhos que já chegaram continuam na lista.
- **As regras de encaminhamento agora podem olhar a origem.** Além de modalidade, servidor e
  descrição, uma regra pode valer só para "Tomógrafo da sala 1" — que é o que permite mandar o
  CT de uma sala para uma impressora e o de outra sala para outra.
- **O que já estava no banco foi aproveitado.** Na primeira abertura o programa varre os
  trabalhos antigos e monta a lista de origens a partir deles, então quem já usa o sistema abre
  a aba com as origens reais do serviço em vez de uma lista vazia.

## Novidades da 0.26 — comparar imagens do exame: DMSA, paratireoide, tireoide e trânsito

Quatro exames não cabem na janela de curvas, porque a conta deles compara **imagens separadas**:
DMSA (anterior × posterior), paratireoide (precoce × tardia), tireoide (tireoide × seringa) e
trânsito colônico (24 h × 48 h × 72 h). Agora existe uma janela para isso —
**MN ▸ Comparar imagens do exame…**

- **Cada imagem é uma linha**, com o **papel** (qual é a anterior, qual é a precoce…) e o
  **horário lido do cabeçalho**. As séries e as vistas do exame entram sozinhas; as capturas de
  tela da estação ficam de fora, porque são a folha do laudo e não imagem de medida.
- **As regiões são desenhadas em cada imagem** — o rim não cai no mesmo pixel na ANT e na POST.
  Os botões **Copiar** e **Copiar espelhado** poupam o retrabalho: o espelhado é o certo para
  ANT/POST, porque mantém as duas regiões com a mesma área. Elipse, retângulo, mão livre e
  contorno automático funcionam igual à janela de curvas.
- **Correção de decaimento entre as imagens**, ligada por padrão. É o que torna comparável uma
  seringa medida às 9 h com a tireoide medida às 11 h — sem isso a captação sai baixa demais, e o
  programa avisa quando falta o horário ou a meia-vida em vez de corrigir errado.

**As contas**

- **DMSA** — função relativa pela média geométrica √(ANT × POST) de cada rim. Avisa quando só uma
  das vistas tem contagem e quando as regiões das duas vistas têm áreas bem diferentes.
- **Paratireoide** — dupla fase: quanto da atividade precoce ainda está na tardia, já corrigido do
  decaimento (sem isso, o decaimento do Tc-99m sozinho daria uma "retenção" de 50% em 6 h).
- **Tireoide** — captação percentual contra o padrão da seringa: `tireoide ÷ (cheia − vazia)`, com
  a seringa trazida por decaimento até a hora da tireoide. Sem a seringa vazia, avisa que o
  resíduo não foi descontado.
- **Trânsito colônico** — centro geométrico em cada tempo, com as regiões na ordem do trânsito
  (ascendente, transverso, descendente, retossigmoide, eliminado). Tempo sem contagem aparece como
  **—**, não como zero.
- **Livre** — só a tabela de contagens de cada região em cada imagem.

Como em toda a parte de medicina nuclear: os valores de referência aparecem em texto, e o programa
não classifica.

**Fantoma novo**: uma cintilografia renal estática (DMSA) com ANT/POST num arquivo e o par de
seringas cheia/vazia em horários diferentes, para testar a média geométrica e a captação sem dado
de paciente.

## Novidades da 0.25 — um exame por receita: gástrico, DISIDA, salivares e razão

A janela de curvas ganhou uma caixa **Exame**. Escolher o exame muda três coisas de uma vez: os
nomes prontos das regiões, a conta que é feita e o que a janela pergunta.

- **Renograma** (como na 0.24) — função relativa, tempo ao pico, T½, relação 20 min/pico.
- **Esvaziamento gástrico** — % de retenção em 30 min, 1 h, 2 h e 4 h, e o T½. Marco que não existe
  na curva aparece como **—**, nunca extrapolado, e um estudo mais curto que as 4 h do guia avisa.
- **Vesícula (DISIDA)** — fração de ejeção: `(máximo antes do estímulo − mínimo depois) ÷ máximo`.
  A janela pergunta **quando a sincalida foi dada**, e a marca aparece tracejada no gráfico. Sem
  esse instante, o programa usa o pico da curva inteira **e diz que usou**.
- **Glândulas salivares** — captação relativa das glândulas (soma 100%) e fração de excreção depois
  do estímulo, com os nomes das quatro glândulas e da cavidade oral já prontos.
- **Razão lesão / lado normal** — para o trifásico ósseo: média por pixel de cada região e a razão
  entre elas. Se as áreas forem diferentes, ele avisa (a razão usa média por pixel, mas regiões do
  mesmo tamanho comparam melhor).
- **Livre** — só os números gerais da curva (pico, T½, área), sem fórmula de exame nenhum.

**Os valores de referência dos guias aparecem embaixo da tabela**, em texto, ao lado do que foi
medido — para você comparar. O programa **não classifica**: não escreve "retardado" nem
"obstruído". Eles mudam com radiofármaco, refeição, protocolo e idade, e são do serviço.

**Imagem condensada**: botão novo na janela de curvas. Cada quadro vira uma coluna e o tempo passa
a ser o eixo horizontal — é como se lê refluxo esofágico e trânsito sem rodar o cine quadro a
quadro. Com uma região escolhida, ela limita a imagem à região. Dá para salvar em PNG.

**Ferramenta de idiomas corrigida**: o extrator colhia os pedaços literais de dentro das f-strings
como se fossem textos de tela (145 entradas falsas no catálogo). Agora o texto é o padrão inteiro.

## Novidades da 0.24.1 — mão livre, contorno automático e duplo clique nas incidências

Três coisas pedidas no primeiro teste da 0.24.

- **Mão livre**: a caixa "Forma" ganhou a opção. Arraste sobre a imagem e o traçado vira a região;
  ele fecha sozinho.
- **Contorno automático**: desenhe uma região grosseira em volta do alvo, escolha-a e clique em
  **Contorno automático**. O contorno segue um limiar em **% do máximo daquela região** (40% é o
  padrão, que é o mais usado em medicina nuclear) e **só pega o que está ligado ao ponto mais
  quente** — dois rins próximos não viram uma região só. O contorno **não escapa da caixa que você
  desenhou**, e mexer no limiar refaz a região dentro da mesma caixa, então dá para subir e descer
  à vontade. O limiar usado fica escrito junto do nome, na imagem.
- **Espelhar D/E funciona com o contorno automático**: a máscara vai espelhada, com a mesma área —
  que é o que a função relativa exige. Se quiser que o outro lado siga o próprio rim em vez de
  repetir a forma, escolha a região espelhada e clique em **Contorno automático** de novo: ela
  recalcula com os pixels daquele lado.
- **Duplo clique numa série de medicina nuclear** abre **todas as incidências lado a lado**, seja
  qual for o nome delas — ANT/POST, OAD/OPE, laterais, janelas de energia. Janela igual nas duas e
  zoom ligado, como antes. O botão **MN ▸ Anterior e posterior lado a lado** continua existindo
  para quando você quiser só esse par.

## Novidades da 0.24 — medicina nuclear fase 2: regiões, curvas e o renograma

A máquina que sete exames usam. Renograma, glândula salivar, dacrio, cistocintilografia, refluxo
gastrointestinal, esvaziamento gástrico e trifásico ósseo são todos a mesma coisa: contar os pixels
de uma região em cada quadro, descontar o fundo, pôr no eixo de tempo certo e aplicar uma fórmula.
Só a fórmula muda.

- **Janela própria de análise** (botão **MN ▸ Curvas atividade-tempo por região…**): a imagem à
  esquerda com as regiões desenhadas por cima, o gráfico e a tabela à direita. A imagem abre com
  **todos os quadros somados** — um quadro de 2 s sozinho é ruído demais para desenhar um rim em
  cima —, e o controle embaixo passa quadro a quadro quando você quiser.
- **Espelhar D/E**: desenhe um rim e o outro sai espelhado no eixo vertical, com o mesmo método de
  fundo. É o jeito de as duas regiões terem o mesmo tamanho, que é o que a função relativa exige.
- **Três jeitos de descontar o fundo**: uma ROI de fundo própria, um **anel em volta da região**
  (com um pixel de folga, para não medir o vazamento da própria captação) ou uma fração fixa. O
  método escolhido fica escrito junto do resultado, porque o mesmo rim dá números diferentes
  conforme o fundo.
- **Contagens por segundo**, ligado por padrão. Num estudo com fluxo de 2 s e dinâmico de 30 s, sem
  dividir pela duração a curva dá um degrau de 15× que não existe no paciente.
- **O tempo de cada ponto é o meio do quadro**, não o começo. Plotar no começo desloca a curva meio
  quadro para a esquerda — é o suficiente para estragar um T½.
- **Renograma completo**: função relativa pelo método da integral (área de 1 a 2,5 min), tempo ao
  pico, T½ depois do pico e relação 20 min/pico. **T½ que não foi atingido aparece como "não
  atingido"**, nunca como um número grande — quem lê precisa ver a diferença entre uma obstrução e
  uma conta que não deu.
- **Correção de decaimento** opcional, com a meia-vida do cabeçalho; sem ela no arquivo, o programa
  diz que não corrigiu em vez de corrigir errado.
- **Exportar CSV** e **Mandar para o laudo** — o texto entra no laudo aberto, com os números e nada
  de interpretação. Nada sai sozinho.
- **Imagem condensada** (tempo no eixo horizontal, anatomia no vertical) já no motor, para o refluxo
  esofágico e o trânsito da próxima etapa.

O programa **não traz valores de referência**: eles dependem de radiofármaco, protocolo, hidratação
e idade, e são do serviço. E não escreve "obstruído" — devolve os números e o que aconteceu com a
curva.

**Também nesta versão:** a **folha de laudo da estação** (a captura de tela que o serviço entrega
ao paciente e ao solicitante) entra como **imagem-chave sozinha** na importação. É reconhecida pelo
que ela é no padrão — exame de MN ou PET gravado como Secondary Capture pela estação de trabalho —
e não pelo nome "ScreenCap", então vale para qualquer fabricante. **Os exames de medicina nuclear
que já estavam no banco também são marcados**, numa passagem em segundo plano quando o programa
abre — não precisa reimportar nada.

## Novidades da 0.23.1 — a medicina nuclear conferida contra exames de verdade

Três coisas que o padrão DICOM manda gravar e as câmaras não gravam. Descobertas ao abrir 146
séries de medicina nuclear reais, e todas viraram ajuste no programa:

- **A vista (ANT, POST, LAT) quase nunca está no cabeçalho.** Só as séries de corpo inteiro trazem
  a `ViewCodeSequence`; nas outras o programa só via "Detector 1" e "Detector 2". Agora ele lê as
  siglas da **descrição da série** — "ANT POST PERF", "LD LE PERF", "ANT/POST 24H" — e só aceita
  quando o número de siglas bate com o número de detectores. Quando a vista vem daí, o rótulo
  aparece como **"ANT (da descrição)"**, em cor diferente na tira, com aviso na barra: trocar
  anterior por posterior inverte direita e esquerda no laudo, então o programa nunca esconde que
  aquilo foi deduzido. (E "POS" de "pós-micção" não é confundido com posterior.)
- **A mesma série pode misturar um arquivo de dois detectores com outro de um só.** Isso partia a
  série em vistas paralelas que não combinavam. Os eixos passaram a ser decididos para a série
  inteira.
- **`SeriesType` vem vazio.** O tipo do exame agora sai dos próprios vetores, e as projeções de
  SPECT passaram a contar como tomografia mesmo sem eixo de corte.

**Sobre SUV em SPECT/CT: não dá, e agora está confirmado.** Nenhuma das 146 séries traz a escala
quantitativa (`Units` ou Real World Value Mapping) — é tudo contagem bruta. No PET, que traz
`Units = BQML`, o SUV continua funcionando normalmente.

Conferido também que espelhar a vista posterior antes de combinar está certo para essas câmaras:
a correlação entre anterior e posterior sobe em todas as séries testadas (óssea 0,670 → 0,845;
pulmonar 0,905 → 0,958).

## Novidades da 0.23 — medicina nuclear: o exame deixa de ser uma pilha de quadros

Primeira etapa do módulo de medicina nuclear. Um arquivo de MN guarda várias imagens no mesmo cubo, e
quem diz o que é cada quadro são os **vetores do grupo 0054** do DICOM: detector, janela de energia,
fase, corte, projeção, tempo. Sem ler esses vetores — que é o que a maioria dos visualizadores genéricos
não faz — um renograma ou um corpo inteiro ANT/POST aparece como uma pilha de quadros sem sentido.

- **A série se abre nas partes que a compõem.** Na tira da esquerda, logo abaixo da série de MN,
  aparece uma linha por vista: `↳ ANT`, `↳ POST`, `↳ Fase 1 · 20 × 2 s`, `↳ Fase 2 · 20 × 30 s`,
  `↳ ANT · Tc-99m`, `↳ POST · I-123`… Cada uma pode ser arrastada para um quadro sozinha. Funciona
  tanto quando o aparelho grava tudo num arquivo só quanto quando grava um arquivo por vista.
- **Botão MN na barra: "Anterior e posterior lado a lado"**. Abre ANT e POST em dois quadros **com a
  mesma janela** — calculada sobre as duas imagens juntas, para que nenhuma sature — e com **janela e
  zoom ligados** entre os quadros. Comparar ANT com POST em janelas diferentes é erro de leitura, então
  o programa não deixa isso acontecer por descuido.
- **Escala de cinza invertida por padrão** em medicina nuclear (captação escura), que é a convenção da
  área. Dá para desligar no menu do botão MN.
- **Média geométrica √(ANT × POST)**, calculada na hora, como uma terceira vista. A posterior é
  espelhada antes de combinar — sem isso a conta soma o fígado com o baço. O espelhamento pode ser
  desligado (câmara que já grava espelhado).
- **Tempo de verdade nos exames dinâmicos**: a duração de cada quadro sai da sequência de fases
  (0054,0032), não de um valor único. Num trifásico de 20 × 2 s + 20 × 30 s, o programa sabe que o
  quadro 21 começa aos 40 s — é o que vai sustentar as curvas atividade-tempo da próxima etapa.
- **Correção de decaimento e contagens por segundo**, com a meia-vida lida do cabeçalho e, se faltar,
  de uma tabela (Tc-99m, I-123, I-131, Ga-67, In-111, Tl-201, Lu-177).
- **Fantomas de medicina nuclear** nos dados de teste (`python -m ipe sample <pasta>`): uma
  **cintilografia óssea de corpo inteiro** com ANT e POST no mesmo arquivo (e um foco quente de um lado
  só, que some se a posterior não for espelhada) e um **renograma** com fluxo de 2 s e dinâmico de 30 s,
  rim direito normal e esquerdo obstruído. Dá para testar tudo sem dados de paciente.

Ainda não: curvas atividade-tempo com ROI, quantificação por exame (função relativa, T½, FEVB, captação
de tireoide), fusão SPECT/CT e cardíaco. Esta versão é a fundação que essas contas precisam.

## Novidades da 0.22 — marcas na lista, download por série, busca do PACS e 3D com cortes

- **Marcas na lista de exames**, ao lado do nome do paciente (como já era o ✎ do comentário):
  **⌛ laudo em rascunho**, **✔ laudo assinado**, **✔↻ laudo retificado** e **▦ filme salvo**. Passar o
  mouse explica cada uma.
- **Exame que ainda está baixando**: as séries que ainda não chegaram aparecem na tira da esquerda,
  **mais claras**, com "na fila", "baixando agora" ou "não vai baixar" — como o Weasis faz. Botão
  direito numa delas: **Não baixar esta série** (ou cancelar o exame inteiro). Para isso, o download
  passou a ser **série por série**: o programa pergunta ao PACS a lista de séries e baixa uma de cada
  vez, então dá para desistir de uma no meio do caminho. Quando o PACS não responde no nível de série,
  continua baixando o exame inteiro (e o programa avisa que aí não dá para pular).
- **Busca do PACS**: o botão **Buscar** vira **Parar** enquanto a busca está em andamento — o C-FIND é
  abortado e fica na tela o que já tinha chegado. A **modalidade** aceita mais de uma (digite `CT, MR`).
  Além dos períodos prontos, agora há **Data exata…** e **Intervalo…** com calendário. E o status
  **"no computador"** (sim / parcial) passou a aparecer **também em cada série** do estudo.
- **3D**: novo modo **Superfície** ao lado de VR, MIP, MinIP e média — primeiro encontro com o limiar,
  com a posição exata da superfície interpolada e a normal calculada no ponto, então o contorno sai
  liso. E o botão **Cortar…**: a partir do **cursor 3D** (ou do meio do volume), corta e deixa só o que
  está atrás, à frente, à direita, à esquerda, acima ou abaixo — a face do corte é desenhada lisa, como
  um corte de verdade. Vale para VR e MIP também, e o volume continua girando normalmente.

## Novidades da 0.21 — seis funções pedidas de uma vez

- **Corrigir tags DICOM**: nome trocado, lado errado, incidência errada, data errada no aparelho.
  Botão direito na imagem (Informações DICOM → **Corrigir**) ou na lista de exames. O programa grava
  uma **cópia corrigida** com UIDs novos e referência à imagem de origem — **o exame original nunca é
  alterado**. Correção de série/imagem fica no mesmo exame; correção de paciente cria um exame novo.
- **Filtros de nitidez e suavização**: três níveis de nitidez (máscara de desfoque) e dois de
  suavização, aplicados **nos valores da imagem**, antes da janela. O filtro escolhido acompanha a
  imagem no filme, no PDF, nas imagens exportadas e no **visualizador HTML** (botão Filtro, tecla S).
  Quem sincroniza janela também sincroniza filtro.
- **Calibração GSDF do monitor** (DICOM PS3.14): informe o preto, o branco e o gama do seu monitor e o
  programa monta a tabela que deixa os passos de cinza **perceptualmente iguais**. Mostra o desvio
  antes e depois (num monitor comum, cai de ~65% para ~5%) e traz quatro padrões de teste —
  16 degraus com quadrado de 5%, rampa, contraste perto do preto e do branco, e pares de linhas —
  para conferir a olho, inclusive em tela cheia. A calibração é **por monitor**.
- **Superfície 3D e STL**: da segmentação que você já fez ou de uma faixa de densidade (osso, osso
  cortical, pele, metal). A malha sai por *surface nets* — fechada e lisa, sem aspecto de cubinhos —
  com opção de só a maior peça, reduzir e suavizar. Grava **STL binário** para impressão 3D ou
  planejamento, mostrando antes quantos triângulos e quantos MB.
- **DSA (subtração digital)**: máscara num quadro escolhido ou na média dos três primeiros, subtração
  **logarítmica** (a que limpa o osso de verdade) ou linear, inversão, e **deslocamento da máscara**
  com setas para tirar o fantasma do movimento. A barra da imagem mostra qual quadro é a máscara.
- **Cardíaco 4D**: séries com os mesmos cortes repetidos em várias fases são reconhecidas sozinhas
  (pela posição, sem depender de tag). A rolagem passa a andar **nos cortes sem sair da fase**; o cine
  das fases toca o ciclo **parado num corte**; dá para **comparar duas fases lado a lado** rolando
  juntas; e a MPR/3D monta o volume **da fase em que você está** (antes usava sempre a primeira).

## Novidades da 0.20.1 — tabela de servidores de impressão

A lista de servidores virou uma **tabela como a dos nós DICOM**, com uma **caixa para ligar e desligar**
na primeira coluna e as colunas que interessam: nome, AE Title, porta, quem aceita, o que faz ao receber,
modelo de folha, se guarda no banco e a situação (*Recebendo*, *Desligado* ou o erro da porta). Tem
também **Testar (C-ECHO)**, que bate no próprio servidor para conferir se a porta está aberta e
respondendo. Marcar ou desmarcar vale quando você clicar em OK.

## Novidades da 0.20 — impressão com vida própria: vários servidores, regras, logo e US automático

- **Botão Impressão na tela inicial** e uma janela só para isso (**Configurações de impressão**), com
  abas de servidores, destinos, regras, modelos de folha e montagem automática. A rede DICOM continua
  onde estava; impressão saiu de lá.
- **Vários servidores de impressão ao mesmo tempo**: um AE e uma porta por aparelho ou por setor
  (mamografia numa, TC/RM noutra…), cada um com o seu destino fixo, o seu modelo de folha e a escolha
  de guardar ou não as folhas no banco. A lista mostra em qual servidor cada trabalho chegou.
- **Regras de encaminhamento** (fase C): *quando* — servidor, AE de origem (aceita `MG*`), texto do
  rótulo, tamanho do filme, número de folhas e faixa de horário (inclusive a que vira a noite, 19h→7h);
  *então* — destino e modelo de folha. São olhadas na ordem, e uma regra pode **deixar continuar**, para
  o mesmo trabalho gravar o PDF *e* sair no filme. Sem regra nenhuma, nada sai sozinho.
- **Modelos de folha com logo** (fase D): logo, nome da clínica, segunda linha, o que mostrar
  (paciente, data, aparelho), rodapé, fundo de filme ou de papel, margens — com **prévia ao vivo** no
  editor. Dois modos: respeitar a folha como veio ou **remontar com a nossa grade** (temos as imagens
  soltas de cada caixa, então dá para refazer 2×2, 3×3…). Vale no PDF, na impressora comum e na
  impressora DICOM.
- **Identificar o paciente ficou mais fácil** (fase E): o programa lista **exames do banco do mesmo
  aparelho e horário** (compara o AE de origem com a estação e a instituição) e um clique preenche nome
  e ID; e, se o Tesseract estiver instalado, o botão **OCR** tenta ler o cabeçalho queimado na folha.
- **Filme automático do ultrassom** (fase E): o US manda as imagens por C-STORE, não por impressão —
  agora, alguns segundos depois de o exame parar de chegar, o programa monta o filme no layout que você
  escolheu (grade, papel, quantas imagens) e deixa pronto na lista; se quiser, já manda para o destino.

## Novidades da 0.19 — o programa como impressora DICOM

O Ipê agora **recebe os filmes das modalidades** (TC, RM, MG, US) como se fosse uma impressora
de filme, guarda tudo numa **lista de impressões** e deixa você mandar cada trabalho para onde quiser.

- **Ligar**: Rede → Rede DICOM → **Impressora DICOM**. Informe na modalidade o AE, o IP e a porta que
  aparecem ali (o padrão é **11113**, porque impressora de filme costuma usar a 104 e o programa **não
  roda como administrador** — no Linux portas abaixo de 1024 exigem isso; quase toda modalidade aceita
  porta diferente).
- **O que chega**: a folha pronta — a grade (`STANDARD\2,2`, `ROW`, `COL`), o tamanho do filme, a
  orientação, a polaridade, o tamanho real pedido em mm e os pixels de cada caixa de imagem, guardados
  **como vieram**. Respondemos ao estado da impressora (N-GET), que é o que muita modalidade pergunta
  antes de mandar a primeira imagem — sem isso ela desiste.
- **Nome e ID do paciente não vêm**: o padrão de impressão DICOM não manda isso (fica queimado nos
  pixels). Quando a modalidade escreve algo no **rótulo da sessão** (Film Session Label) ou no Owner ID,
  o programa aproveita; senão, você escreve na hora com **“Identificar paciente”**.
- **Lista de impressões (Ctrl+Shift+P)**: os filmes recebidos e os **montados aqui no compositor** ficam
  na mesma lista, com pré-visualização folha a folha, os parâmetros do filme e a situação de cada um.
- **Cada folha vira exame no banco** (Secondary Capture), para abrir no visualizador como qualquer
  outro estudo.
- **Enviar para…**: um trabalho ou vários de uma vez, para **PDF numa pasta**, **impressora do
  computador**, **impressora DICOM** (reenviado *como veio*: mesma grade, mesmo tamanho, caixa por
  caixa) ou **imagens PNG/JPEG numa pasta**. Nada sai sozinho — a não ser que você escolha um destino
  fixo em “Ao receber”.
- Nenhum arquivo é sobrescrito: se já existir um com o mesmo nome, o novo sai como “(2)”, “(3)”…

## Novidades da 0.18.2 — editar protocolos junto das etapas

Na barra da mamografia, **"Editar protocolos…" saiu de botão separado e virou a última linha da lista de
etapas** (depois de um separador). Escolher essa linha abre o editor e **não troca a etapa em que você
está**.

## Novidades da 0.18.1 — contorno do implante liso e cinza certo

- **Sem serrilhado**: a prótese é procurada numa imagem reduzida (é rápido), mas a borda agora é **refeita
  na resolução cheia** — numa faixa estreita em volta do contorno grosso, cada pixel é decidido pelo seu
  próprio valor, com o limiar no meio do caminho entre o silicone e o tecido vizinho, e um filtro de
  maioria tira os pontinhos. O contorno sai **igual ao de verdade**, com precisão de 1 pixel (antes subia
  em blocos de ~10 px). A linha da cápsula também ficou mais fina.
- **O cinza da prótese agora é sempre o do meio da janela**: o achatamento passou a usar a janela que está
  **de fato na tela** (antes usava a janela do tecido calculada à parte; quando a janela mostrada era outra
  — o que acontece nos quadros com tomossíntese —, o implante saía escuro demais). Mexendo na janela com o
  mouse, o implante acompanha.

## Novidades da 0.18 — mamografia no visualizador exportado e implante que funciona de verdade

- **Apagar implante refeito**: antes o programa procurava a prótese pela **densidade** — e em exame real
  isso falha, porque mama densa também é clara. Agora procura pela **falta de textura**: o silicone é uma
  área grande, clara e **lisa**, e o tecido fibroglandular tem trama. Funciona em mama densa, gordurosa,
  com o implante saturado e em MONOCHROME1.
- **E se ainda assim não achar**: botão direito dentro do silicone → **"Apagar o implante a partir daqui"**.
  A barra de status avisa quando não achou sozinho, em vez de não fazer nada.
- **O visualizador HTML da exportação ganhou mamografia**:
  - **Mamografia** — monta CC e MLO das duas mamas lado a lado, com a **parede torácica voltada para o
    centro** (espelhando quando precisa) e a **janela do tecido**, igual ao programa;
  - **Quadrante (Q)** — zoom no quadrante posterior e superior, depois no posterior e inferior, e volta à
    imagem inteira, **nos quatro quadros ao mesmo tempo** e encostado no canto, sem perder o alinhamento;
  - **Janela da mama** — refaz a janela só no tecido.
  O lado, a incidência, a caixa da mama, o lado da parede torácica e a janela do tecido são **calculados na
  hora de exportar** e vão junto no arquivo, então o navegador não precisa analisar a imagem.
- **O visualizador exportado sai no idioma em uso** (português, inglês ou espanhol) — o mesmo catálogo do
  programa. Catálogo: **2837 entradas, 100% nos três idiomas**.

## Novidades da 0.17.2 — apagar o implante e quadrante em duas etapas

- **Apagar implante** (botão na barra da mamografia, Alt+I): a prótese vira uma **área lisa, sem textura**
  — só a linha da cápsula continua — e a janela passa a ser calculada **só no tecido mamário**. É como os
  aparelhos mostram a prótese: um disco uniforme, para o olho não se prender ao silicone e o tecido
  aparecer bem. Vale em todos os quadros ao mesmo tempo, e **não altera o arquivo** (é uma cópia na tela).
  Antes o botão só mudava a janela, o que não dava o mesmo efeito.
- **Zoom por quadrante em duas etapas**: posterior e superior → posterior e inferior → imagem inteira
  (eram quatro). Continua encostado no canto, com o alinhamento da mamografia preservado.

## Novidades da 0.17 — pasta do banco e mamografia (zoom junto e quadrantes da mama)

**Pasta do banco deste computador**: dá para mudá-la sem sair do programa — botão direito no *Banco deste
computador* (painel Locais) ou *Configurações → Mudar a pasta do banco deste computador…*. O programa
pergunta se é para **mover o banco e os arquivos** para a pasta nova ou **só apontar** para ela; a escolha
fica gravada e vale ao reabrir (as configurações não se mudam de lugar, então o programa sempre acha o
caminho de volta).

**Mamografia:**

- **Zoom junto (sincronizado)**: o zoom e o deslocamento feitos num quadro aparecem nos outros — e não
  copiando os números, e sim **o mesmo lugar da mama**: na outra mama sai espelhado, e vale entre 2D,
  tomossíntese e recombinada. Liga/desliga em *Editar protocolos… → "zoom junto"*.
- **Quadrantes da mama, em 4 etapas**: o zoom por quadrante agora segue a anatomia — **posterior e
  superior → posterior e inferior → imagem inteira** ("posterior" é o lado da parede torácica). Cada quadro vai para o seu próprio quadrante, então a mama
  direita e a esquerda ficam sempre no mesmo lugar anatômico.
- **O alinhamento da mamografia continua valendo com zoom** (0.17.1): o quadrante fica **encostado no
  canto**, então a parede torácica não sai do lado da tela em que estava — mama direita encostada à
  direita, mama esquerda à esquerda, as duas espelhadas. O zoom é o maior que ainda mostra o quadrante
  inteiro.
- **O quadrante acompanha a tomossíntese e a recombinada**: ao rolar da 2D para os cortes da tomo, a imagem
  **não pula mais** — fica o mesmo zoom e o mesmo ponto da mama. Clicar em *BE ⇄ Recomb.* também mantém o
  quadrante, em vez de voltar para a imagem inteira.
- **Botões da etapa**: o nome da etapa ficou à esquerda e as duas setas (◀ ▶) juntas à direita.

## Novidades da 0.16 — vários locais de exames (HD externo, pasta de rede, outras pastas)

No estilo do painel *Sources* do OsiriX/Horos: a coluna da esquerda do Banco de dados agora traz **Locais**.

- **Um clique troca de local** e a lista de exames passa a ser a daquela pasta. Em negrito, o local em uso;
  em cinza, o que está *fora do ar* (HD desconectado, rede caída) — nada é perdido, volta quando o disco voltar.
- **Cada local carrega o banco inteiro**: dentro da pasta ficam o índice (`dicomviewer.sqlite`), a pasta
  `Storage` e a marca `dicomviewer-local.json`. Leve o HD externo para outro computador, aponte o programa
  para a pasta e **tudo vem junto**: exames, listas de casos, comentários, medidas e laudos.
- **Acrescentar um local não copia nada**: *+ Local…* pergunta a pasta (HD externo, `\\servidor\exames`,
  outra pasta do PC) e **só indexa** os arquivos que já estão lá — nada é copiado, movido ou alterado.
  Botão direito → *Procurar exames novos nesta pasta…* atualiza o índice depois.
- **Copiar exames entre locais**: botão direito no exame → *Copiar para o local* → escolha o destino.
  As imagens são copiadas para dentro daquele local; **os arquivos de origem não são tocados**.
- **Botão direito no local**: usar, abrir a pasta, renomear, procurar exames novos e *Tirar da lista*
  (que não apaga nada — a pasta continua inteira, e basta acrescentá-la de novo).
- **Os nós PACS** aparecem no mesmo painel: clicar abre a busca já naquele nó.
- O local ativo aparece no **título da janela**, e o que chega pela rede (nó DICOM) entra no local em uso.
  Ao trocar, os exames abertos são fechados (com aviso) — como no OsiriX.
- A lista de locais fica nas **configurações do usuário**, nunca dentro de um local: ela sobrevive à troca.

## Novidades da 0.15.1 — ícone do mouse e tradução das telas desenhadas

- **Ícone do mouse no lugar do texto azul**: o canto esquerdo do quadro mostra agora um **desenho pequeno
  de mouse**. Passando o cursor por cima, abre um balão com **o que cada botão faz agora** (esquerdo,
  direito, meio, roda, Ctrl+roda e Shift+roda). Quando há uma ferramenta ligada no botão esquerdo (régua,
  ROI, seta…), o **botão esquerdo do ícone fica aceso em amarelo** — dá para ver de longe que não está no
  janela/nível. Clicando no ícone, abre a lista de ferramentas do botão esquerdo.
- **Tradução do que é desenhado à mão**: o texto sobre a imagem (Im 31/60, Esp 3.0 mm, W/L, FOV, o balão
  do mouse), o filme e os gráficos passam pela tradução — antes só menus, botões e caixas de diálogo
  eram traduzidos.
- **Rótulos de uma palavra**: Arquivo, Exibir, Rede, Ajuda, Janela, Zoom, Rolar, Inverter, Girar,
  Restaurar, Cine e companhia entraram no catálogo (o extrator ignorava palavras soltas sem acento).
  O catálogo foi de 2384 para **2708 entradas**, 100% em inglês e espanhol.
- **Frases montadas**: a barra de status junta pedaços com "·" e o aviso do rodapé vem dentro de `<i>…</i>`;
  a tradução agora trata os dois casos, e um padrão não "engole" mais o resto da linha.

## Novidades da 0.15 — o programa em inglês e espanhol (e em qualquer idioma)

- **Três idiomas prontos**: português, **inglês** e **espanhol**. Na primeira vez que o programa abre, ele
  pergunta o idioma (já sugerindo o do sistema); depois é só *Configurações → Idioma*. A troca vale ao
  reabrir o programa.
- **Tudo traduzido, não só os botões**: menus, avisos, ajuda, **nomes dos protocolos** (mamografia, MPR,
  dinâmica…) e os **modelos de laudo** (TC, mamografia, RM e PET). Os textos que o programa monta na hora
  ("3 medidas exportadas para C:\\...") também, porque são guardados como padrões com `{}` no lugar do que muda.
- **Traduzir para outros idiomas sem programar**: *Configurações → Idioma → Traduzir…* abre uma tabela com o
  texto em português de um lado e o seu de outro (com filtro e a opção *só os que faltam*). O resultado fica em
  `<dados>/locale/<idioma>.json` — um arquivo simples, que dá para mandar para outra pessoa ou de volta para
  o projeto. O mesmo editor serve para corrigir uma palavra do inglês ou do espanhol.
- **Como funciona por dentro**: a tradução acontece no momento em que o texto chega à tela (`ui/qt_i18n.py`),
  com o **português como chave** — nada de códigos tipo `MSG_042`. Assim o programa continua legível em
  português no código, e um idioma novo é só mais um arquivo JSON.
  As ferramentas `tools/i18n_extract.py`, `tools/i18n_merge.py` e `tools/i18n_show.py` cuidam do catálogo
  (2384 textos hoje, 100% em inglês e espanhol).
- **README em inglês e espanhol**: `README.en.md` e `README.es.md`.

## Novidades da 0.14.2 — abrir enquanto baixa, histograma e medidas em planilha

- **Abrir enquanto baixa (streaming)**: em exames grandes, o programa abre o estudo assim que as primeiras
  imagens chegam e vai acrescentando o resto conforme baixa (o corte e a janela em que você está não mudam).
  É **opcional**: no cadastro do nó (Rede → Configurar nós) escolha *Sempre*, *Nunca* ou *Usar o padrão*, e em
  Rede → Este computador ficam o padrão e o aviso. Quando não está definido, o programa **estima o tempo do
  download** e pergunta: “são ~250 imagens (~120 MB); nesta rede leva cerca de 2 min. Abrir enquanto baixa?”,
  com a opção *Fazer sempre assim neste nó*.
- **Teste de rede** no cadastro do nó (botão *Testar rede*): C-ECHO repetido mostra se o nó responde e em quantos
  ms, e avisa quando a rede está lenta. A velocidade (MB/s) e o tamanho médio por imagem são **aprendidos** a cada
  download, por nó, e é isso que alimenta a estimativa.
- **Histograma** (tecla **H**, botão direito na imagem ou Janela ▾): distribuição dos valores da imagem ou de
  dentro da ROI selecionada, com a janela atual marcada, estatísticas (média, DP, mediana, percentis, SUV no PET),
  botões para ajustar a janela pelos percentis e *Copiar dados*.
- **Medidas para planilha** (Medidas ▾ → *Exportar medidas para planilha*): uma linha por medida (paciente, exame,
  série, imagem, tipo, valores, lesão ligada) em CSV que o Excel abre com um duplo clique; respeita o modo de
  ocultar dados do paciente.

## Novidades da 0.14.1 — laudo mais fácil

- **O formulário BI-RADS® muda o texto sozinho**: composição, cada achado (“+ Achado”) e a categoria de cada mama
  entram no laudo na hora (no lugar de “___” e de “Não há nódulos…”). Se você editou o trecho à mão, o botão
  **Levar ao texto do laudo** insere o BI-RADS onde está o cursor.
- **Achar o laudo salvo**: botão **Laudo** na tela inicial (exame selecionado), botão direito no exame → **Laudo…**,
  coluna **Laudo** na lista (rascunho / assinado / retificado; quem já escolheu colunas: *Colunas ▾ → Laudo*) e,
  dentro da janela, a lista **Laudos deste exame** (rascunhos e assinados).
- **Imagens-chave no laudo com as anotações**: medidas, setas, textos e desenhos feitos na imagem aparecem no PDF
  (com régua de escala); a janela/cor é a do quadro aberto no visualizador, se a série estiver aberta.
- **Tomossíntese na mesma lista da incidência** (mamografia): o quadro traz as imagens 2D daquela mama e incidência e,
  em seguida, os cortes da tomo — a roda passa de uma para a outra, sem botão (o canto mostra "2D" ou
  "Tomo corte k/n"). O cine e a espessura (slab) valem só nos cortes da tomo. Shift+T continua como atalho para pular
  entre a 2D e o meio da tomo; o botão "2D ⇄ Tomo" saiu da barra.
- **Janela da tomossíntese**: o programa agora lê a janela que o aparelho grava na tomo (Frame VOI LUT dos arquivos
  multiframe, que antes era ignorada), inclusive a curva **sigmoide** (VOI LUT Function SIGMOID) e a janela em
  tabela (VOI LUT Sequence). Sem janela no arquivo, a automática usa só o tecido mamário (sem o fundo e os letreiros)
  e é a mesma em todos os cortes, calculada no corte do meio. A 2D e a tomo guardam cada uma a sua janela ao rolar.
- **Coluna Comentário**: mostra o comentário mais recente do exame (e "(+n)" se houver outros) e atualiza na hora
  ao adicionar um comentário (antes só mudava depois de F5, e mostrava o primeiro).

## Novidades da 0.14 — lesões, CAD/IA, laudo, segmentação 3D e mama

- **Acompanhamento de lesões** (botão **Lesões**, Ctrl+Shift+L): painel com a tabela lesão × exame do paciente.
  Desenhe a medida (régua; ROI no PET) → botão direito sobre ela → *Ligar a uma lesão* (ou *Nova lesão…*).
  Critério à escolha: **RECIST 1.1** (soma dos diâmetros, menor eixo nos linfonodos; RP ≤ −30% da base,
  DP ≥ +20% do nadir e ≥ 5 mm, lesão nova ou progressão de não alvo), **mRECIST** (parte viável),
  **PERCIST 1.0** (SUVpeak da lesão mais ávida; RMP/DMP com ±30% e ±0,8) ou **livre** (só a tabela).
  Exame de base automático ou escolhido; botão direito na célula marca *desapareceu*, *progressão inequívoca*
  ou *não mensurável*. Duplo clique abre a imagem da medida; **Layout das lesões** abre um quadro por lesão
  (para a reunião); **Copiar texto** leva a tabela e a resposta para o laudo.
- **CAD/IA e anotações de outros sistemas** (botão **CAD/IA**, Shift+I): o programa lê e desenha sobre as
  imagens os objetos do exame — **SR** (inclusive *Mammography CAD SR* e resultados de IA em TID 1500, com o tipo
  do achado e a certeza), **DICOM SEG** (máscaras coloridas por segmento), **RTSTRUCT** (contornos em mm) e
  **GSPS** (textos e desenhos). A seta do botão lista os objetos (liga/desliga cada um) e as imagens com achado.
- **Laudo** (botão **Laudo**, Ctrl+R): modelos prontos de TC (crânio, tórax, angio-TEP, abdome, oncológico),
  mamografia (rastreamento, diagnóstica, tomossíntese, contrastada), US de mamas, RM (mamas, crânio, abdome,
  pelve) e PET/CT (FDG, PSMA). O modelo é escolhido pela modalidade e descrição do exame e os campos se
  preenchem sozinhos: comparação com anteriores, medidas, lesões/RECIST/PERCIST, volumes (TMTV/TLG), curvas,
  imagens-chave. **Formulário BI-RADS®** (mamografia, US e RM): composição/FGT/realce de fundo, achados com
  descritores, categoria por mama e final, conduta automática. *Assinar e liberar* grava o **PDF** (com
  imagens-chave) e, no exame, o **DICOM PDF** e o **DICOM SR** (vão junto ao PACS). Laudo assinado não muda:
  *Retificar* cria um novo. *Modelos…* edita, cria e restaura os modelos (no modo cliente, valem para todos).
  Permissões novas: **Escrever laudos** (residente tem) e **Assinar laudos**.
- **Segmentação 3D** (ferramenta *Segmentar 3D*, Shift+V, no menu de medidas, no 3D ▾ e no CAD/IA): clique na
  lesão. TC/RM: faixa de valores (automática, ajustável); PET: **41% do SUVmáx** ou **SUV fixo** (2,5). Mostra
  volume (mL), maior eixo, SUVmáx/médio/**SUVpeak** e **TLG**; *Guardar* grava como medida (entra no laudo e no
  **TMTV**), pode ligar a uma lesão e *Salvar como DICOM SEG* guarda a máscara no exame.
- **Mamografia**: **zoom por quadrante segue a parede torácica** (quadrantes da mama, não da imagem inteira);
  **máscara de implante** (botão *Implante*, Alt+I: janela calculada só no tecido, sem o implante);
  **tomossíntese com espessura** (*Espessura ▾*: 5, 10 ou 20 cortes, MIP ou média; Shift+J troca);
  **mamografia com contraste (CEM)**: baixa energia e recombinada reconhecidas, código "rec" no protocolo
  (ex.: `CCD, CCD rec x CCE, CCE rec`), botão *BE ⇄ Recomb.* (Shift+B) e protocolo de fábrica para exames com
  "CEM/CESM/contraste" na descrição (quem já tinha protocolos salvos: *Padrão* no editor traz o novo).

## Novidades da 0.13.1 — quadrante em ciclo, rolagem por incidência e tomossíntese

- **Zoom por quadrante em um só comando**: tecla **Q** (ou "Quadrante ↻" na barra, ou a ferramenta de quadrante clicando no quadro) vai para o próximo quadrante a cada clique — sup. esq. → sup. dir. → inf. esq. → inf. dir. → imagem inteira; **Shift+Q** volta. Nos quadros do protocolo, todos juntos e espelhados entre direita e esquerda.
- **Rolagem por incidência**: num quadro da mamografia, a roda passa só pelas imagens da mesma mama e incidência (repetições, séries diferentes), mesmo que o aparelho grave tudo numa série só.
- **Tomossíntese**: reconhecida (Breast Tomosynthesis ou multiframe; lado também pelo FrameLaterality); **Shift+T** (ou "2D ⇄ Tomo") alterna o quadro entre a 2D e os cortes; a roda passa os cortes e **C** liga o cine em vai e volta. No protocolo, use "tomo" no código (ex.: `CCD tomo x CCE tomo`). Projeções brutas da tomo são ignoradas.
- Multiframe mais rápido: cada corte é decodificado sozinho, sem ler o arquivo inteiro a cada imagem.

## Novidades da 0.13 — mamografia (protocolo por etapas, quadrantes, lupa) e botão Monitor

- **Protocolos de mamografia por etapas** (Preferências → Mamografia, ou "Editar protocolos…" na barra roxa): cada etapa tem layout e a incidência de cada quadro, escolhida numa grade ou escrita em texto — colunas separadas por "x", linhas por vírgula: `CCD x CCE` (1×2), `MLOD x MLOE` (1×2), `CCD, MLOD x CCE, MLOE` (2×2), `CCD, CCD ant x CCE, CCE ant` (atual × anterior). Incidências CC, MLO, ML, LM, XCCL, XCCM, AT, SPOT, MAG; D/E = lado; "ant"/"ant2" = exames anteriores.
- Ao abrir uma mamografia, a 1ª etapa é montada sozinha (lado e incidência lidos dos cabeçalhos: ImageLaterality, ViewPosition, ViewCodeSequence, descrição). **N** / **Shift+N** passam as etapas (ou ◀ ▶ na barra). Opções: parede torácica voltada para o centro (espelha se precisar) e imagem encostada na borda da parede torácica.
- **Zoom por quadrante** (ver 0.13.1). **1:1**: 1 pixel da imagem = 1 pixel da tela.
- **Lupa** (tecla U): segure o botão para ver a região em resolução original, aumentada; a roda muda o aumento (1,5× a 8×).
- **Botão Monitor** na tela inicial: abre o exame selecionado em outro monitor (seta: escolher o monitor, trazer de volta, configurar monitores).

## Novidades da 0.12.2 — tela inicial com botões e PACS em janela

- Barra de botões no banco de dados: **Importar** (pasta; seta: arquivos, ZIP, pacote de lista, fantomas), **PACS**, **Abrir** (seta: escolher séries, abrir vários juntos para comparar), **Enviar** (nós de envio, com identidades), **Exportar**, **Imprimir** (filme; seta: filmes salvos, imagens-chave), **Listas** (mostrar/esconder o painel; seta: adicionar os selecionados, nova lista/pasta, importar/exportar pacote), **Reunião**, **Ocultar** (dados do paciente em todo o programa), **Apagar**, **Atualizar** (F5), **Configurações** (preferências, nós DICOM, automação, servidor central…), **Usuários** e **Ajuda**. Os botões seguem as permissões do perfil.
- O **PACS** saiu das abas: abre numa **janela flutuante** (botão PACS ou Ctrl+Shift+F; Esc fecha), que lembra tamanho e posição e pode ficar em outro monitor. O botão mostra o número de transferências em andamento.

## Novidades da 0.12.1 — girar e espelhar a imagem

- Botão **Girar** na barra (clique: 90° à direita; seta: 90° à esquerda, 180°, espelhar esquerda ↔ direita, espelhar cima ↕ baixo, voltar à orientação original, aplicar a todos os quadros). Também no botão direito do quadro ("Girar / espelhar").
- Atalhos: Alt+R (90° à direita), Alt+Shift+R (à esquerda), Alt+H (espelho horizontal), Alt+V (vertical) — mudáveis em Preferências.
- As letras de orientação acompanham o giro; medidas, cursor 3D, fusão e linhas de referência continuam no lugar certo. O canto inferior mostra "↻90° ⇋" (clique para o menu). Ao enviar ao filme, a imagem vai girada. Os arquivos não são alterados.

## Novidades da 0.12 — fase 8: usuários, permissões e servidor central

**Usuários e permissões**
- Login com usuário e senha do programa (senha guardada com PBKDF2). Na primeira abertura, cria-se o administrador.
- Perfis: **Administrador**, **Médico**, **Residente** e **Técnico**; a tabela do que cada perfil pode (abrir, importar, buscar/baixar do PACS, enviar, exportar, exportar sem anonimizar, apagar, listas de casos, filmes, configurar, usuários) é ajustável em Usuário → Usuários e permissões → Perfis.
- Menu **Usuário**: alterar senha, trocar de usuário, usuários e permissões, registro de acesso.
- Preferências por usuário (mouse, atalhos, presets, protocolos de exibição, colunas, exportação); as do computador (rede, monitores, desempenho) continuam na máquina.
- **Registro de acesso**: quem entrou/saiu, abriu, exportou (ou anonimizou), enviou, baixou, buscou, imprimiu, importou ou apagou cada exame, com computador e hora; filtro e exportação CSV.
- Computador pessoal: "Entrar automaticamente como…" (aba Este computador).

**Servidor central na intranet** (Rede → Configurar servidor central)
- **Servidor**: um computador guarda exames, usuários, medidas, imagens-chave, comentários, listas de casos, filmes e o registro de acesso, e atende por HTTP (porta 8043; HTTPS opcional com certificado). Pode rodar com janela ou sem: `servidor.bat` / `./servidor.sh` (na primeira vez: `servidor.bat --create-admin admin`).
- **Cliente**: entra com o usuário do servidor; o banco mostra os exames do servidor; ao abrir, o exame é baixado para um cache local (limite em GB, os mais antigos saem sozinhos). O que o cliente importa, recebe, baixa do PACS ou gera (reconstruções, SR, gráficos, 3D) sobe para o servidor.
- **DICOMweb** no servidor: QIDO-RS (`/dicomweb/studies`, séries, instâncias), WADO-RS e STOW-RS, com login (token ou usuário/senha) — outros visualizadores DICOMweb podem se conectar.
- Servidor fora do ar: o login oferece "Usar sem o servidor (modo local)".

## Novidades da 0.11.1 — funções de cada nó DICOM

- No cadastro do nó (Rede → Configurar nós → Editar), "Usar em:" **Busca**, **Busca de anteriores** e **Envio**. A tabela de nós mostra as três colunas.
- **Busca**: "Todos os nós de busca" no painel PACS, chamada externa e buscas agendadas. **Anteriores**: painel Anteriores do visualizador e pré-busca automática de anteriores. **Envio**: menu "Enviar para".
- Busca por anteriores: **todos** os nós marcados para anteriores ou **só os selecionados** — na aba "Nós remotos" e no botão **Nós ▾** do painel Anteriores.

## Novidades da 0.11 — 3D, fusão PET/CT, MPR curvo e dinâmica completa

- **3D** (botão 3D): janela com **renderização de volume** (presets osso, vasos, pele, pulmão, tecidos moles, automático para RM/PET), **MIP/MinIP/média** giráveis. Esquerdo gira, direito ajusta a janela/limiar, meio move, roda dá zoom; vistas prontas (anterior, lateral, superior…), **Girar 360°**, salvar imagem e enviar ao filme.
- **MPR curvo** (3D ▾ → MPR curvo): clique os pontos do caminho (pode rolar os cortes entre os cliques), duplo clique ou Enter termina (Backspace desfaz, Esc cancela). O corte "esticado" aparece ao lado; rolar gira o corte em volta do caminho (0–180°). Medidas ao longo do caminho em mm.
- **Fusão** (botão Fusão): sobrepõe outra série (ex.: PET sobre a TC, também no MPR) com cor, opacidade, mínimo/máximo (em SUV no PET) e "ocultar abaixo do mínimo"; o valor da série de cima aparece sob o cursor.
- **Dinâmica**: correção de movimento entre as fases (translação 3D), pontos/ROIs repetidos em todos os mapas, **pior pixel** de cada ROI (pior tipo de curva e maior realce, marcado ✳) e **gráfico no filme**.

## Novidades da 0.10 — avaliação dinâmica (RM de mama): MSI, PEI e SER

- Botão **Dinâmica** (Shift+D): escolha as séries da dinâmica (detecção automática; uma série só com todas as fases também serve), a fase pré, a inicial (padrão ≈ 2 min) e a tardia, o limiar de realce e a unidade.
- Mapas calculados corte a corte: **MSI** (maior inclinação de subida, %/min), **PEI** (integral do realce positivo, %·min), **SER** ((inicial − pré)/(tardia − pré): azul < 0,9 persistente, amarelo 0,9–1,1 platô, vermelho > 1,1 washout), realce inicial, subtração e tempo até o pico.
- Layout: MSI + gráfico; MSI, PEI e SER + gráfico; ou MSI, SER, subtração e fase inicial + gráfico. O painel troca o mapa (ou a fase) do quadro ativo.
- Curvas tempo-intensidade: clique com **Intensidade (V)** para pontos (média 3×3) ou desenhe ROIs (elipse, retângulo, polígono); cada curva tem sua cor, e a tabela mostra realce inicial, pico, SER, tipo de curva (I/II/III), MSI e PEI. "Curva sob o cursor" acompanha o mouse.
- Copiar valores (para planilha), salvar o gráfico em PNG e salvar os mapas como séries (vão para o filme e a exportação).

## Novidades da 0.9.2 — cores (pseudocor) e salvar reconstrução pelo botão direito

- Botão **Cor** na barra (e "Cor (tabela de cores)" no botão direito): Cinza inverso, Hot Iron, Gold, Hot Metal Blue, PET, Tálio, Arco-íris, Espectro, Jet, NIH, GE Color, Cardíaco/perfusão, Fluxo e Osso. Barra de cores com os valores da janela no canto direito do quadro.
- "Aplicar a cor do quadro ativo a todos os quadros"; com a janela sincronizada, a cor acompanha os quadros da mesma modalidade. A cor continua nas reconstruções (MPR/oblíquo) da mesma série.
- A cor vai para o filme (e pode ser trocada em cada imagem do filme) e para a exportação JPG/PNG ("Usar a cor do quadro").
- Botão direito num quadro com reconstrução: "Salvar a reconstrução como série nova" e "Salvar só esta imagem reconstruída".

## Novidades da 0.9.1 — MPR oblíquo no programa

- Ferramenta **MPR oblíquo** (tecla O, ou no menu do botão MPR): desenhe uma linha em qualquer quadro (original ou reconstrução). O plano que contém a linha aparece no quadro ao lado (no layout 1×1 abre 1×2); a linha magenta mostra onde ele corta o quadro de origem.
- Role no oblíquo para mover o plano; desenhe outra linha para mudar o ângulo (reaproveita o mesmo quadro). Espessura MIP/Média/MinIP na barra MPR.
- Enviar ao filme ou exportar: vai a imagem atual do oblíquo; "Salvar a reconstrução como série" grava o oblíquo inteiro.

## Novidades da 0.9 — itens menores pendentes

- **Protocolos de exibição** (Preferências → Protocolos de exibição): mamografia abre em 2×2 (D CC, E CC, D MLO, E MLO) com o exame anterior no monitor de comparação ou lado a lado; RM de mama por sequência. Edite, crie, reordene ou restaure os de fábrica.
- **Medidas como DICOM SR** (Mais → Salvar medidas como DICOM SR): guarda no exame ou salva em arquivo (SR Comprehensive, TID 1500 simplificado).
- **SUV no PET**: sonda mostra SUV e Bq/ml; ROI mostra SUVmáx e SUVméd; W/L em unidades de SUV.
- **Alinhamento automático** (Sincronizar ▾ → Alinhar automaticamente): registro por correlação de fase entre o exame atual e o anterior (só translação); o deslocamento fica salvo.
- **Listas inteligentes**: nova lista do tipo "Inteligente (filtro)" — critérios de texto, modalidade, período, descrição, medidas, comentários etc.; atualiza sozinha.
- **Reconstruções vão para o filme e a exportação**: MPR → "Salvar a reconstrução do quadro ativo como série nova"; enviar um quadro MPR ao filme cria a série automaticamente; a exportação tem "Imagem reconstruída" e "Reconstrução inteira".
- **Texto gravado na imagem**: na anonimização, apaga regiões de US e a faixa superior (US/XA/SC…) — modo automático, faixa superior ou nenhum.
- **Visualizador HTML**: MPR oblíquo (tecla O, desenhe a linha), espessura (slab) MIP/Média/MinIP e letras de orientação na mamografia.

Limitações: a exportação JPG/PNG não apaga texto gravado; o registro é só translação.

## Novidades da 0.8.3 — reconstrução num plano, pasta nova ao exportar, visualizador mais rápido

- **Reconstrução num plano só, no visualizador do programa:** botão **MPR ▾** → *Reconstruir no
  quadro ativo: Axial / Coronal / Sagital* (atalhos Alt+1 / Alt+2 / Alt+3). Só o quadro ativo vira o
  plano escolhido; os outros continuam como estão (ex.: axial original de um lado e coronal
  reconstruído do outro, com linhas de referência). Espessura (slab: média, MIP, MinIP) na barra MPR.
  *Voltar o quadro ativo à série original* no mesmo menu (ou arraste a série de novo). O clique no
  botão MPR continua abrindo os 3 planos.
- **Exportar numa pasta nova:** opção *Criar uma pasta nova dentro do destino* (ligada por padrão),
  com o **primeiro nome do paciente** (ou ANONIMO, ao anonimizar); dá para trocar o nome. Se a pasta já
  existir, vira _2, _3… No .zip, o arquivo recebe esse nome.
- **Visualizador no navegador mais rápido:** decodificação nativa dos dados, blocos carregados em
  paralelo, reconstrução otimizada e sem refazer o corte quando só a janela muda.

## Novidades da 0.8.1 — visualizador completo no navegador

- Na exportação DICOM, *Visualizador no navegador*: **Completo** (padrão), **Leve** (só imagens, como
  antes) ou nenhum. O completo leva os **valores originais dos pixels** (sem perda) e funciona offline,
  abrindo o *ABRIR_VISUALIZADOR.html* em Chrome, Edge, Firefox ou Safari atualizados:
  - **janela real** (W/L na unidade do exame; na TC em HU), janelas prontas 1–6 (pulmão, mediastino,
    osso, cérebro, abdome, fígado), 0 = do arquivo, inverter;
  - **valor sob o cursor** (HU na TC) e **medidas**: régua (mm/cm), ângulo (3 cliques), ROI elíptica
    e retangular (área, média, DP, mín./máx.), ponto; Del apaga a última; *Apagar medidas*;
  - **medidas, anotações e imagens-chave feitas no Ipê** aparecem por cima (verde; ★ nas
    imagens-chave), com botão para mostrar/ocultar;
  - **Planos**: *Original* (como foi adquirido), **Axial**, **Coronal** ou **Sagital** — reconstrói só
    o plano escolhido, em tela cheia (com medidas, janela e cine) — ou **MPR 3 planos** (cruz
    sincronizada; clique numa vista move a cruz nas outras; rodinha troca o corte de cada vista).
    No MPR, **duplo clique** numa vista (ou o botão ⤢, ou a tecla F) amplia essa vista para a tela
    toda, mantendo a cruz; de novo volta aos 3 planos. Funciona nas séries volumétricas (cortes
    paralelos e regulares);
  - zoom, mover, cine, letras de orientação, espessura e posição do corte.
  - Tamanho: parecido com o dos arquivos DICOM (pixels em 16 bits compactados). Imagens maiores que
    2048 px (mamografia) vão reduzidas no visualizador (os DICOM exportados não mudam). Séries
    coloridas (US Doppler, fotos) vão como imagem: medem distância, sem valores.
  - O MPR carrega a série inteira na memória do navegador (TC de 400 cortes ≈ 200 MB); séries muito
    grandes são recusadas com aviso.

## Novidades da 0.8 — fase 7: exportação

- **Exportar** (banco: botão direito → *Exportar…*; visualizador: *Mais* → *Exportar…* ou **Ctrl+E**;
  Arquivo → *Exportar…*). Escolha o que exportar: imagem do quadro ativo, série do quadro (numa
  dinâmica, todas as fases), imagens-chave, exame inteiro, todos os exames da aba, exames ou séries
  selecionados no banco.
- **DICOM — pasta, CD ou pendrive:** cópias dos arquivos com **DICOMDIR** (padrão lido por outros
  visualizadores e estações) e, se quiser, um **visualizador simples** que abre em qualquer navegador
  (*ABRIR_VISUALIZADOR.html*: lista de exames e séries, rodinha/setas para rolar, arrastar para
  brilho/contraste, Ctrl+rodinha zoom, cine). Pode compactar tudo num **.zip**. A pasta de destino
  precisa estar vazia (se não estiver, o programa propõe uma subpasta EXAMES).
- **Imagens JPG/PNG:** uma imagem por corte (a cada N, se quiser), com a janela do arquivo ou a do
  quadro atual, no tamanho original ou reduzido; pastas por exame/série, opcionalmente sem o nome do
  paciente.
- **Anonimização configurável** (só nas cópias): nome e ID do paciente à escolha ({n} = número do
  exame), manter ou não sexo, idade, datas, descrições e instituição, remover tags privadas, UIDs
  novos. Sempre saem nascimento, accession, endereço/telefone, médicos, operador, estação e outros
  identificadores. Texto gravado dentro da imagem **não** é removido. No modo reunião a exportação é
  sempre anonimizada.
- A exportação roda em segundo plano, com barra de progresso e *Cancelar*; no fim, *Abrir pasta*.

## Novidades da 0.7 — fase 6: listas de casos e modo reunião

- **Pastas e listas** (à esquerda no Banco de dados): *+ Lista*, *+ Pasta*; botão direito para
  renomear, descrição, duplicar, mover para outra pasta, tornar lista de reunião/normal, exportar e
  excluir (excluir nunca apaga exames; numa pasta, as listas de dentro sobem um nível). Arraste listas
  para dentro de pastas. Clicar numa pasta mostra os casos de todas as listas dela.
- **Adicionar casos:** arraste exames da tabela para uma lista, ou botão direito → *Adicionar à lista*
  (inclui *Nova lista…*). Com uma lista aberta, a tabela ganha as colunas **Nº** e **Caso**, na ordem
  da lista; botão direito → *Editar caso*, *Reunião a partir deste caso*, *Tirar da lista*.
- **Organizar lista** (duplo clique na lista): arraste os casos para mudar a ordem (ou ↑ ↓) e preencha,
  por caso: **nome do caso** (o que aparece na reunião), **tags**, **história**, **resposta**
  (diagnóstico/anatomopatológico, fica oculta), **notas de ensino** e **séries a abrir** (nenhuma
  marcada = todas). *Numerar nomes…* dá “Caso 1, Caso 2…” aos casos sem nome.
- **Modo reunião** (*▶ Modo reunião*, ou botão direito na lista): abre os casos um a um em tela cheia,
  com uma barra: *◀ Anterior* / *Próximo ▶* (Alt+← / Alt+→), *Casos ▾* (pular), *História* (Alt+H),
  *Revelar resposta* (Alt+R, volta a ficar oculta no próximo caso), *Tela cheia* (F11) e *Encerrar*.
  Enquanto a reunião está ativa **nenhum dado do paciente aparece**: quadros mostram o nome do caso,
  o banco mostra o nome do caso no lugar do paciente e “•••” no ID, nascimento, accession,
  instituição e médicos; o botão PACS fica desativado; exames já abertos ou abertos durante a reunião ficam
  ocultos; o filme sai anonimizado; as tags DICOM ficam bloqueadas. Ao encerrar, tudo volta ao normal.
  Os arquivos não são alterados.
- **Exportar / importar lista** (botão direito na lista; Arquivo → Importar lista de casos):
  - *Com imagens (anonimizadas)*: pacote .zip para outro computador, com **cópias** anonimizadas
    (nome vira CASO 001, sem nascimento, instituição, médicos, operador, estação, accession e tags
    privadas; UIDs novos), além de nomes dos casos, histórias, respostas, notas, tags, séries a abrir,
    imagens-chave e medidas. Os arquivos do seu banco não mudam. Texto gravado dentro da imagem
    (burned-in, comum em US) **não** é removido.
  - *Só a lista*: nomes, respostas e notas referenciando os exames originais (para quem já tem os
    mesmos exames, ex.: do mesmo PACS). Ao importar, casos cujo exame não está no banco são avisados.
- Caixas de marcar mais visíveis no tema escuro.

## Novidades da 0.6.2 — anotações no filme

- Na barra do filme, **Anotar: Ajustar · Seta · Texto · Lápis**. Com Seta/Texto/Lápis ligado, o botão
  esquerdo desenha na imagem da célula (seta: arraste da ponta para trás; texto: clique onde começa;
  lápis: desenho livre). *Ajustar* volta o esquerdo para janela/nível.
- As anotações ficam **só no filme** (não vão para as medidas do exame), acompanham zoom, pan, giro e
  espelho da célula (o texto continua de pé) e saem na impressão, no PDF, nas imagens e na
  impressora DICOM. São salvas com o filme e vão junto ao copiar/colar a célula.
- **Ctrl+Z** desfaz a última anotação da célula selecionada; botão direito na célula → *Apagar as
  anotações desta imagem*.

## Novidades da 0.6.1 — filme no visualizador, copiar/colar e botões do mouse

- **Filme como painel do estudo** (não é mais aba): aparece ao lado dos quadros, com divisor
  ajustável. **Duplo clique** no filme (ou o botão ⤢) expande o filme para ocupar tudo, como o 1×1
  do layout; outro duplo clique volta. ✕ fecha o painel (o filme continua guardado). **Ctrl+P**
  mostra/esconde. Ao enviar imagens de outro estudo, o painel vai junto; fechar o estudo não apaga
  o filme. Sem estudo aberto, o filme abre numa janela própria.
- **Copiar, recortar e colar imagens no filme:** Ctrl+clique soma células à seleção, Shift+clique
  seleciona um intervalo, Ctrl+A seleciona a folha. **Ctrl+C**, **Ctrl+X**, **Ctrl+V** (ou botão
  direito na célula). Colar numa célula ocupada insere e empurra as seguintes até a próxima vaga
  (nada se perde; se faltar lugar, cria folha); colar numa vaga só preenche. Recortar deixa a vaga.
  A área de transferência vale entre filmes. Del apaga as selecionadas.
- **Ferramentas nos botões direito e do meio:** clique com o **botão direito** num ícone da barra
  (Janela, Pan, Zoom, Rolar, qualquer medida, Cursor 3D, **Filme**) para usá-lo no botão direito do
  mouse; clique com o **botão do meio** (a rodinha) para usá-lo no botão do meio. Também funciona
  dentro dos menus (ex.: menu das medidas). O ícone ganha um selo **D** ou **M** e o quadro mostra
  "D: …  M: …". O clique esquerdo no ícone continua escolhendo a ferramenta do botão esquerdo.
  A rodinha continua rolando os cortes.
  - Com medida, Cursor 3D ou Filme no botão direito, o menu flutuante abre com **Shift + clique
    direito** (e Shift + clique do meio continua ajustando a imagem).
  - **Ferramenta Filme:** clicar na imagem com o botão que a tem envia aquela imagem ao filme (com
    a janela e o zoom). Para o esquerdo: botão Filme ▾ → "Enviar ao filme (clique na imagem)".
  - A escolha fica salva e também aparece em Preferências → Mouse.

## Novidades da 0.6 — fase 5: filmes e impressão

- **Compositor de filmes** (painel *Filme* no visualizador — veja 0.6.1 —, Arquivo → Filme / impressão, **Ctrl+P**): várias folhas, cada
  uma com sua grade (1×1 a 6×5 ou "Outro…"), papel/filme (A4, A3, Carta, 8×10 a 14×17 pol) e
  orientação. Marque *em todas as folhas* para mudar todas de uma vez. Diminuir a grade não perde
  imagens: o que sobra vai para uma folha nova.
- **Montar o filme a partir do visualizador** (botão **Filme** na barra, com menu):
  - **Ctrl+F** envia a imagem do quadro ativo com a janela, o zoom e o pan atuais;
    Ctrl+Alt+F envia a de todos os quadros;
  - *Série do quadro (inteira / intervalo)…*: todas as imagens, de X a Y a cada N, ou N imagens
    espalhadas por igual; pode escolher o layout das folhas novas;
  - *Imagens-chave do exame*; também no botão direito da tira de séries e no banco de dados;
  - arrastar uma miniatura da tira para uma célula do filme (imagem do meio ou série/intervalo).
- **Editar cada imagem no filme:** esquerdo = janela, direito arrastado = zoom, meio = mover
  (clique do meio = ajustar), rodinha = trocar o corte. Botão direito: girar 90°, espelhar,
  inverter, janelas prontas, mostrar/ocultar medidas, copiar a janela (e o zoom) para a folha toda,
  abrir no visualizador, remover, inserir/remover vaga. Arraste pelo ⠿ para trocar imagens de
  lugar. Del remove.
- **Textos e cabeçalho:** cabeçalho com paciente, exame e instituição; rodapé com a folha e a data.
  Textos nas imagens: nenhum, mínimo ou completo; letras de orientação corrigidas quando a imagem é
  girada ou espelhada; régua de escala; opção *Anonimizar*; fundo branco (papel) ou preto (filme).
- **Saídas:** impressora do sistema (*Imprimir…*), **PDF** (uma página por folha, 200 dpi),
  **imagens** PNG/JPG por folha (resolução à escolha) e **impressora DICOM** (*DICOM…*: cadastre AE,
  IP e porta, tamanho do filme, mídia, destino, ampliação, resolução, cinza ou colorido; *Testar
  conexão* mostra o estado da impressora). Cada folha vai como uma imagem (STANDARD\1,1).
- **Filmes salvos:** *Salvar* guarda o filme no banco (folhas, layouts e ajustes de cada imagem)
  para reabrir e imprimir depois (*Abrir…*, Arquivo → Filmes salvos, ou no banco de dados → botão
  direito → Filme). Exames com filme salvo ficam protegidos da limpeza automática.
- As últimas escolhas (layout, papel, textos, cabeçalho, régua, fundo) viram o padrão dos próximos
  filmes.

## Novidades da 0.5.1 — lista do banco de dados

- **Colunas à escolha:** botão *Colunas ▾* (ou botão direito no cabeçalho) liga/desliga colunas,
  inclusive novas (hora, idade, região, instituição, solicitante, operador/técnico (0008,1070),
  estação, aparelho, tamanho, origem, datas de entrada e acesso, protegido, imagens-chave, medidas,
  dinâmicas, listas, comentário). Arraste o título para mudar a ordem; ordem e larguras ficam salvas.
- **Filtros por coluna:** embaixo de cada título há uma caixa de filtro (combina com a busca de
  cima e entre colunas). Sintaxe:
  - texto: `silva` (contém, sem ligar para acento/maiúscula), `rm*mama`, `=US` (exato);
  - vários: `MG|US` (ou); negar: `!CT`;
  - números: `>10`, `<=3`, `5..20`;
  - datas: `2025`, `03/2025`, `15/03/2025`, `01/01/2025..30/06/2025`, `>=2024`, `hoje`, `30d`, `6m`;
  - Protegido: `sim` / `não`.
- **Filtro por valores (tipo Excel):** botão direito no título → *Filtrar valores de "…"* → marque
  os valores. *Limpar filtros* (botão ao lado de *Colunas*) tira todos. O rodapé mostra
  "N de M estudo(s)" quando há filtro ativo.

## Novidades da 0.5 — automação (Rede → Automação…)

- **Buscas agendadas:** buscas feitas sozinhas num nó (ou em todos os nós de busca), com filtro
  (paciente, ID, accession, descrição, modalidade), período do exame (hoje, últimas N horas, últimos
  N dias) e horário: a cada N minutos numa janela (ex.: 7h–19h, dias úteis), diariamente num horário
  ou uma vez. Ação: baixar os exames novos (só o que ainda não está no computador) ou só avisar;
  opcionalmente pôr numa lista. "Executar agora" testa a regra.
- **Pré-busca de anteriores:** quando um exame chega (recebido ou baixado) ou é aberto, o programa
  procura os anteriores do paciente no PACS e baixa segundo regras por modalidade (ex.: RM de mama →
  1 RM de mama + 1 MG, até 3 anos). Vêm 5 regras de exemplo, **desligadas**: ative as que quiser.
- **Painel de anteriores no viewer:** o botão *Anteriores* agora abre, à direita, a linha do tempo do
  paciente (banco local + PACS), com "no computador", "baixando" ou "só no PACS"; filtros por
  modalidade e região; duplo clique (ou *Baixar / comparar*) baixa e já coloca o exame na comparação.
  A seta do botão mantém o menu rápido de antes.
- **Roteamento:** exames que chegam e batem com o filtro (modalidade, descrição, origem) são
  reenviados para outro nó (ex.: estação de IA). O programa espera o exame terminar de chegar.
- **Limpeza (autodelete)** com simulação, lixeira e restauração: por idade, por falta de uso, por
  modalidade, anteriores da pré-busca com prazo próprio, disco acima de X% (apaga os menos usados até
  voltar a Y%) e teto do armazenamento. Nunca apaga protegidos, em listas, com comentário,
  imagem-chave, medidas ou diagnóstico, nem exames abertos. Por padrão só mexe no que veio da rede.
- **Histórico** de todas as execuções e exclusões.
- **Bandeja do sistema** (Preferências → Geral): fechar a janela pode deixar o programa rodando na
  bandeja (nó DICOM e buscas agendadas continuam) e ele pode iniciar junto com o Windows, minimizado.
  As automações só rodam com o programa aberto (ou na bandeja).

## Novidades da 0.4.2 — fases dinâmicas e escolher séries

- **Juntar fases de uma dinâmica** (cada fase numa série separada), de três jeitos:
  - arraste a miniatura de uma fase para o **canto inferior direito** de um quadro que já mostra outra
    fase ("+ Juntar como fase"); soltar no resto do quadro continua trocando a série;
  - selecione as fases na tira com Ctrl+clique → botão direito → **Agrupar como fases**;
  - botão direito na tira → **Detectar fases dinâmicas…** (acha séries de RM com a mesma geometria;
    você confirma e pode desmarcar).
  As fases são ordenadas pelo horário de aquisição. O grupo fica salvo e aparece na tira como
  "▦ Dinâmica"; ao reabrir o exame, a dinâmica já abre num quadro só.
- **No quadro da dinâmica:** ← → trocam a fase (↑ ↓ e a rodinha continuam trocando o corte, no mesmo
  corte em todas as fases). Clique em "Fase x/y" para escolher a fase, ligar a **subtração**
  (fase − pré-contraste), o **cine das fases**, tirar uma fase do grupo ou desfazer o grupo.
  A curva tempo-intensidade usa as fases do grupo.
- **Escolher quais séries abrir:**
  - no banco, painel de séries: duplo clique abre só aquela série; Ctrl+clique em várias →
    botão direito → **Abrir as séries selecionadas**;
  - botão direito no estudo → **Abrir escolhendo séries…** (marque e arraste para mudar a ordem);
  - Preferências → Geral: perguntar as séries quando o estudo tiver mais que N séries;
  - a tira mostra só as séries escolhidas, com "Mostrar todas as séries" no fim.

## Novidades da 0.4.1 — barra com ícones e mais medidas

- **Barra do viewer com ícones** (texto embaixo, seta ▾ para opções): Janela (presets na seta), Pan,
  Zoom, Rolar, **Medidas** (o botão mostra a última ferramenta; a seta abre todas), Cursor 3D,
  Layout, Inverter, Restaurar, Cine, MPR, Sincronizar, Chave, Anteriores, Monitor, Ocultar e Mais.
- **Medidas novas:** polilinha (Shift+G), ângulo de Cobb (Shift+C: arraste uma reta, depois a outra),
  diferença de altura, ROI retangular (Shift+E), intensidade/valor do pixel (V), curva
  tempo-intensidade, índice cardiotorácico (arraste a largura do coração, depois a do tórax),
  rotular coluna (escolha a 1ª vértebra e clique nas seguintes; Enter, duplo clique ou Esc termina),
  linha de calibração (informe o tamanho real; as medidas da série passam a usar essa escala) e
  lápis (B). Atalhos editáveis em Preferências.
- **Curva tempo-intensidade** (RM dinâmica de mama): desenhe a ROI; o programa procura as fases na
  mesma posição (na mesma série ou uma série por fase), mostra o gráfico de realce relativo, a tabela
  e a classificação (inicial lento/médio/rápido; tardia persistente, platô ou washout).
- **Medição contínua** (menu Medidas): ligada, a ferramenta continua ativa; desligada, volta para
  janela/nível depois de cada medida.
- **Achar as medidas:**
  - a miniatura da série mostra um selo "✎ N" (imagens com medida); botão direito na miniatura →
    abrir direto na primeira medida ou escolher qual;
  - barra fina à direita do quadro: posição na série, medidas (verde) e imagens-chave (dourado);
    clique ou arraste nela para ir à imagem;
  - "N imagem(ns) com medida ▾" embaixo do quadro abre a lista; `.` e `,` vão para a próxima/anterior.
- **Editar e apagar medidas** (já existia, agora também no menu Medidas): clique na medida para
  selecionar; arraste as pontas para editar; arraste a selecionada para mover; Del apaga; botão
  direito sobre ela: apagar, editar texto, ver a curva.

## Novidades da 0.4 — nó DICOM

- **Rede → Configurar nós DICOM…**
  - *Este computador:* AE Title (padrão `DICOMVIEWER`), porta (padrão 11112), aceitar só nós
    cadastrados ou qualquer AE. A tela mostra o AE, o IP e a porta para passar à TI.
  - *Nós remotos:* PACS, modalidades e estações, com botão **Testar (C-ECHO)**. Download por
    **C-GET** (mais simples: não exige que o PACS conheça este computador) ou **C-MOVE**.
  - *Identidades:* outros AE Titles que o programa pode assumir numa busca, download ou envio
    (ex.: buscar como a estação de mama), limitadas aos nós escolhidos. Tudo fica na *Auditoria*.
- **Aba PACS** (Ctrl+Shift+F): busca por nome, ID, accession, descrição, modalidade e período, num nó
  ou em todos os nós de busca. A seta do estudo mostra as séries (marque as que quiser baixar).
  "No computador" diz se o estudo já está no banco. Duplo clique baixa e abre.
- **Transferências** em segundo plano (duas ao mesmo tempo, configurável), com progresso e cancelar.
- **Receber:** estudos enviados por outros nós (C-STORE) entram no banco sozinhos, com miniaturas.
- **Servir:** outros viewers podem consultar e baixar deste programa (C-FIND, C-MOVE, C-GET).
- **Enviar:** banco de dados → botão direito → *Enviar para* (C-STORE), inclusive "como" uma identidade.
- **Chamada externa:**
  - `ipe open --accession 123 [--node PACS]`: se o estudo não estiver no banco, busca nos
    nós, baixa e abre; `ipe retrieve --accession 123` só baixa;
  - link `ipe://open?accession=123` (o `instalar.bat` registra o link; ou Rede → Registrar);
  - API HTTP local: `http://127.0.0.1:8042/api/open?accession=123&token=…` (também `/api/retrieve`
    e `/api/status`). O token está em Rede → Configurar nós → Este computador. Só aceita chamadas
    do próprio computador, a menos que você libere IPs. Apagar e exportar nunca são aceitos por fora.
- **Firewall:** na primeira vez, o Windows pergunta se o Python pode usar a rede. Permita em
  **redes privadas** para receber imagens (C-MOVE/C-STORE). Para C-GET e buscas não é necessário.

## Novidades da 0.3

- **Arrastar e soltar para importar:** arraste arquivos DICOM, pastas (inclusive CD/DVD) ou ZIPs do
  Explorer para qualquer lugar do programa — banco de dados, viewer ou janelas de outros monitores.
  Aparece o aviso "Solte para importar"; ao terminar, os exames abrem sozinhos (até 4; com mais,
  ficam no banco de dados). Soltar um exame que já está no banco só abre o exame. Se já houver
  uma importação em andamento, o novo arrasto entra na fila.
- **Medidas** (menu "Medidas ▾"), todas salvas no banco e reabertas com o exame:
  - régua (M), ângulo (A), ROI elíptica (E), ROI poligonal ou livre (G), seta (Shift+A) e texto (T);
  - ROI mostra média ± desvio-padrão, mínimo, máximo (em HU na TC) e área em mm²/cm²;
  - medidas levam em conta pixel não quadrado; também funcionam nos planos do MPR (só na sessão);
  - clicar seleciona; arrastar as alças edita; arrastar a medida selecionada move; Del apaga; Esc cancela.
- **Sincronização:**
  - grupos coloridos (azul, verde, laranja, rosa): clique no ícone de corrente embaixo do quadro
    (ou Ctrl+L) para pôr o quadro num grupo; vários grupos ao mesmo tempo;
  - ajuste fino: Alt + rodinha (ou Alt + setas) move só um quadro e guarda a nova diferença;
  - o alinhamento entre dois exames fica salvo e é reaplicado quando você volta a compará-los;
  - séries sem geometria (DBT, US) sincronizam pela posição relativa na pilha;
  - modos rápidos (Shift+L): desligado, só mesmo estudo, todos os quadros;
  - a sincronização funciona entre janelas de monitores diferentes.
- **Monitores** (Preferências → Monitores): papel de cada tela (banco de dados, viewer, comparação)
  e layout por tela. Estudos abrem no monitor "viewer"; anteriores abrem no de "comparação",
  já alinhados se houver alinhamento salvo. "Identificar monitores" mostra o número em cada tela.
  Cada janela de monitor tem abas próprias.
- **Layouts** até 4×4. **Botões laterais do mouse** (4 e 5) configuráveis.
- **Desempenho** (Preferências → Desempenho): teto do cache de imagens e do volume de MPR; a barra
  de status mostra a RAM usada pelo programa, o cache e os volumes.

## Novidades da 0.2

- **MPR:** botão MPR (Shift+M) no quadro ativo mostra axial, coronal e sagital com linhas de referência coloridas.
  - Cursor 3D (X): clicar num plano leva os outros ao mesmo ponto.
  - Espessura (slab) de até 40 mm, em Média, MIP ou MinIP.
  - Leva em conta espaçamento irregular e gantry inclinado, e avisa quando há.
- **Sincronização:**
  - automática entre séries do mesmo estudo (mesmo referencial espacial);
  - linhas de referência entre planos diferentes (ex.: T2 axial × T1 sagital);
  - "Ligar quadros" (L): sincronização manual com deslocamento, para comparar com o exame anterior;
  - opcional: janela/nível e zoom/pan sincronizados.
- **Exames anteriores:** "Anteriores ▾" (Shift+P) traz outro exame do mesmo paciente para a mesma aba, já com a série equivalente ao lado.
- **Imagens-chave:** K marca e desmarca a imagem atual (★ no canto).
  - Shift+K ou o item "★ Chave" na tira de séries mostra todas.
  - Estudo com imagem-chave fica protegido contra exclusão.
- **Multimonitor:** "Outro monitor" na barra (ou Exibir → Mover estudo atual para o monitor) abre o estudo maximizado numa janela própria. Fechar essa janela devolve o estudo à janela principal.
- **Preferências (Ctrl+,):**
  - função de cada botão do mouse e da rodinha;
  - tempo e movimento que separam clique de segurar;
  - todos os atalhos de teclado, com aviso de conflito;
  - presets de janela 1–9;
  - copiar ou só referenciar arquivos;
  - layout inicial.
