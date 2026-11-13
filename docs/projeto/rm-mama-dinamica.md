# RM de mama dinâmica: o que o CADstream fazia e o que o Ipê tem

Linha de trabalho da RM de mama com contraste. Os números citados aqui são faixas medidas num pequeno acervo de
exames reais (só para calibrar o método); nenhum exame é identificado.

## O que o CADstream é

Nasceu na Confirma (spin-off da Universidade de Washington), lançado em **janeiro de 2003**: o primeiro CAD de RM de
mama a virar rotina. Confirma → Merge Healthcare (2009) → IBM Watson Health → **Merative**, que ainda o lista como
"Merge CADstream". O concorrente direto é o **DynaCAD** (Invivo/Philips).

O fluxo do produto:

1. **Processamento automático na chegada**: o exame roda sozinho e as séries derivadas voltam ao PACS.
2. **Registro não rígido** entre as fases (um estudo citado reduziu pseudolesões em 92% dos casos sem criar falso
   negativo).
3. **Subtração** e **MIP da subtração**.
4. **Mapa cinético de 6 cores**, a assinatura do produto. Dois eixos:
   - intensidade do realce na fase de pico: **médio 50–100%**, **rápido > 100%**;
   - comportamento tardio (tardia × pico): **persistente ≥ +10%**, **platô < ±10%**, **washout ≥ −10%**.
   Os limiares se ajustam a dose, velocidade de injeção, resolução temporal e campo.
5. **Angiovolume** (volume do mapa colorido, sem necrose, fibrose e cisto), **realce de pico (%)**, diâmetros
   ortogonais e maior diâmetro 3D, **percentual de cada um dos 6 padrões** e **heterogeneidade cinética**.
6. **Segmentação da lesão** a partir do mapa, depois que o médico aponta onde é, com ajuste em passos.
7. Acessórios: guia de biópsia, chamada do anterior, módulo de próstata.

Fontes: [Computer Aided Detection (CAD) for Breast MRI](https://journals.sagepub.com/doi/pdf/10.1177/153303460500400107) ·
[Angiovolume e realce de pico como fatores prognósticos](https://pmc.ncbi.nlm.nih.gov/articles/PMC12736581) ·
[Confirma anuncia as capacidades ampliadas](https://www.biospace.com/confirma-inc-announces-expanded-breast-mri-capabilities-for-cadstream-tm) ·
[Merge CADstream (Merative)](https://www.merative.com/documents/merge-cadstream-data-sheet) ·
[CADstream × DynaCAD](https://pubmed.ncbi.nlm.nih.gov/23589186/)

## O que o Ipê já tinha

`imaging/dynamic.py`: fases em séries separadas ou numa série só, correção de movimento por translação 3D, subtração,
**MSI, PEI, SER, realce inicial, tempo até o pico**, curva tempo-intensidade com classificação BI-RADS, pior pixel
dentro da ROI, janela automática por percentil, mapas como quadro do layout e gravação dos mapas como séries. O SER
(escola Hylton) responde a mesma pergunta do eixo tardio do CADstream por outro caminho.

## 0.46: o mapa cinético de 6 cores, medido antes de ser escrito

A medição no acervo achou três coisas, duas delas defeitos que já afetavam o módulo.

**1. A detecção de fases pegava série derivada.** Em estudos GE, junto com as fases vêm as **subtrações da própria
estação** (com nomes como `(43798/301/60)-(43798/300/60)`), os MIPs e as cópias alinhadas de outra estação. O filtro
era por **nome**, e nenhum desses nomes tem "SUB" ou "MIP". O grupo de "fases" saía com pré + fases + subtrações. Como
a subtração herda o horário da fase que a gerou, dois horários iguais derrubavam o conjunto para "sem horário", e os
mapas eram calculados com 1 minuto por fase, inventado (com aviso, mas inventado).

Conserto: `phases.image_type()` lê o **ImageType (0008,0008) do arquivo**, e `fora_das_fases()` recusa `SUBTRACT`,
`PJN`/`MIP`, `SECONDARY`, `ADC`, `TRACEW`. Sem ImageType legível, o nome volta a valer como último recurso. De
quebra, `componente()` separa **água e gordura** das sequências Dixon, que têm a mesma geometria e eram juntadas.

**2. "Pico" é uma fase, não o máximo voxel a voxel.** A primeira medição deu **0,00% de persistente** em todos os
exames. Com o máximo entre as pós-contraste como pico, o tardio nunca supera o pico, e persistente fica impossível por
construção. O CADstream usa a 2ª pós-contraste como pico; com a fase fixa (a mesma `early` que o SER já usava),
persistente aparece normalmente.

**3. Sem máscara de tecido, a classificação em porcentagem acende o ar.** Onde o pré-contraste é quase zero, qualquer
variação vira centenas por cento. Medido: sem máscara, 36 a 44% de todo o campo saía colorido. Exigir pré ≥ 10% do
sinal de referência (percentil 99,5 do máximo entre as fases) deixa 22–36% do campo, mais ou menos o que a mama ocupa
num axial, e o colorido cai para cerca de 7–8% do campo, consistente entre os exames.

| limiar de tecido | campo usado | colorido |
|---|---|---|
| nenhum | 100% | 36–44% |
| pré ≥ 5% da referência | 33–47% | 34–48% |
| **pré ≥ 10% da referência** | **22–36%** | **7–8%** (com o pico como fase) |
| pré ≥ 30% da referência | 7–14% | 14–23% |

**Protocolos com poucas fases.** Um protocolo comum (GE VIBRANT 1+3) tem uma pré e **três** pós, pico a ~2 min e
tardia a ~5 min. O CADstream usava a 5ª pós-contraste como tardia; com três fases a tardia é a 3ª, e o eixo tardio
fica menos sensível. Isso fica **escrito junto do mapa**. Exames sem as fases originais são recusados, em vez de
montados com séries derivadas.

Achado de caminho: as fases pós-contraste da GE trazem **TriggerTime** em milissegundos desde a primeira pós, que bate
com o AcquisitionTime. É um relógio melhor, ainda não usado.

O que ficou no programa:
- Mapa **`cin`**: 0 = sem cor, 1–3 realce médio, 4–6 realce rápido, cada faixa em persistente/platô/washout. Na
  tabela de cores `cinetico`, **o tom diz o comportamento tardio** (azul persistente, verde platô, vermelho washout) e
  **o brilho diz a intensidade**.
- Limiares **editáveis**; `legenda_cinetica()` escreve quais limiares e quais fases produziram a imagem;
  `classe_cinetica()` dá a classe de uma curva com a mesma régua.
- Defeito pego na conferência de tela: com a janela 7/3,5, o valor da classe caía na emenda entre duas faixas de cor
  e uma lesão *rápido/washout* aparecia verde. A janela 7/3,0 põe cada classe no meio da sua faixa.

## 0.48: medir a lesão pelo mapa

O médico clica na lesão, o programa cresce a região em 3D **sobre o realce** e devolve os números
(`imaging/cad_mama.py`, `DynamicMaps.volume_do_mapa()`, método `realce_pct` em `imaging/segment.py`).

Os números, na ordem de leitura: volume · **angiovolume** (só o que realça de verdade) · **realce de pico** (com a
média) · diâmetros ortogonais · maior diâmetro 3D · padrão dominante · **percentual de cada padrão**, com a cor do
mapa · heterogeneidade cinética.

**Heterogeneidade cinética vai rotulada.** A fórmula do CADstream não é publicada; aqui é a entropia de Shannon da
distribuição dos seis padrões, normalizada de 0 a 1, e a tela diz isso.

Três defeitos pegos na medida:

1. **O maior diâmetro 3D saía menor que um dos lados** (com corte de 10 mm, a soma usada ficava abaixo do próprio
   diâmetro crânio-caudal). O `cad_mama` passou a medir com meio voxel em cada ponta, projetado na direção medida, e
   nunca devolve menos que o maior lado.
2. **O limiar fixo vaza pela mama inteira.** Numa RM de mama tudo o que realça está ligado pelos vasos: com limiar
   fixo de 50% a partir de uma semente em vaso, a "lesão" virou praticamente a mama. O padrão passou a ser o limiar
   **relativo à própria lesão** (50% do realce máximo dela, como o 41% do SUVmáx no PET); o fixo continua disponível.
3. **Fora do tecido o realce em porcentagem explode**, e um voxel de ar vira "a lesão". O volume usado para crescer
   passou a levar a mesma máscara de tecido do mapa cinético.

O que a medida **não** prova: sem lesão marcada no acervo, a semente dos testes foi automática (o voxel de maior realce
rápido) e cai em vaso. Por isso o programa avisa quando a região é **fina e comprida** (alongamento ≥ 3× o diâmetro da
esfera de mesmo volume é forma de vaso). O ajuste em passos (− e +) é o freio, como no CADstream.

## 0.55: a máscara da mama e os números do exame inteiro

A máscara que existia (pré ≥ 10% da referência), medida por faixa no eixo anterior-posterior, tinha **cerca de metade
do volume atrás da mama** (parede torácica, mediastino, coração), e era ali que estava o realce rápido. Para o mapa
cinético pouco importa; para qualquer número do exame inteiro é fatal.

**A primeira tentativa não serviu.** Procurar, linha a linha, a primeira interrupção de 8 mm do corpo cortou 7% do
tecido num exame e 76% noutro: errado nos dois sentidos.

**O que funciona é a forma, não o vão.** O pulmão é a região escura **fechada pelo corpo**; o ar de fora encosta na
borda da imagem. Um alastramento 3D a partir das bordas **do corte** separa um do outro sem depender de quão escuro o
pulmão está. A parede é a primeira coluna de pulmão indo para trás; linhas e cortes sem pulmão herdam dos vizinhos. O
alastramento roda numa grade reduzida (lado máximo 160) com somas acumuladas por eixo. Resultado: corta 38 a 48% do
tecido, de forma consistente entre os exames.

**O músculo peitoral fica dentro, e a máscara diz que fica.** Separar músculo de glândula por sinal não dá em T1 com
saturação de gordura, e chutar uma espessura seria inventar número.

**Os números do exame** (botão no painel da dinâmica): volume da mama na máscara, angiovolume do exame, realce de
fundo (média e mediana) e o percentual de cada padrão. O realce de fundo **separa os exames**, que é o que se espera
de um número útil. Já o angiovolume saiu alto demais em todos (uma fração grande da mama), e "rápido/washout" numa
fração parecida em todos não é fisiologia: é a máscara, que mantém pele, vasos e músculo. O número vai para a tela
**com a fórmula e a limitação escritas junto**. A categoria de realce de fundo continua sendo leitura do médico.

Testes: `test_mama_mascara.py` (fantoma sagital com parede, pulmão fechado e coração) e `test_cad_mama.py`.

## 0.55: dinâmica pronta na chegada (só cache)

Diferente do CADstream, **nada é gravado como série e nada sai**. O programa adianta o trabalho caro (detectar quais
séries formam a dinâmica e decodificar os quadros) para o exame abrir pronto; com os quadros no cache, a conta do mapa
é aritmética de array. A porta é **Automação ▸ Dinâmica pronta**, com regra de modalidade + descrição. Sem regra
ativa, nada acontece. O pré-cálculo para quando ocupa a fatia reservada do cache (40%) e diz quantos quadros
conseguiu. Teste: `test_dinamica_chegada.py`, incluindo que nenhuma série é criada e nada é enviado.

## 0.62–0.63: distâncias à pele, ao mamilo e ao peitoral

Em `imaging/mama_distancias.py`, tudo em coordenadas do paciente (mm).

- **Mamilo** = o ponto mais anterior da pele de cada metade do paciente; um clique do médico manda sobre ele.
- **Parede e pele (0.63)**: numa RM de mama sagital a imagem costuma **acabar dentro do pulmão** (o FOV não pega as
  costas), então o pulmão encosta na borda e a regra da máscara da 0.55 não vale. A parede sai do **perfil da
  linha**: do mamilo para trás, o primeiro trecho escuro de ≥ 2 cm é o pulmão, o último tecido antes dele é a parede
  (`parede_e_pele`), e a pele da mama é a pele na frente dessa parede, na mesma linha. Variar o trecho escuro de 10 a
  40 mm muda a parede em até 9 mm; 2 cm fica fixo.
- `eixo_ap_do_volume` acha qual eixo do array é anterior-posterior (limiar 0,8, uns 37°); acima disso não sai número.
- `menor_distancia` em duas passadas (grossa e fina): a pele de uma RM tem mais de um milhão de voxels.
- Vão para a medida guardada como `dist_pele_mm`, `dist_mamilo_mm`, `dist_mamilo_centro_mm` e `dist_peitoral_mm`.
- **Em aberto**: separar o músculo peitoral da máscara e validar os três números contra a medida à mão numa lesão
  real.

## O que falta do CADstream, em ordem de retorno

1. **Separar fibroglandular de gordura.** A máscara tirou coração e mediastino, mas o que sobra ainda é tudo o que está
   na frente da parede. Sem essa separação, o realce de fundo serve para comparar o mesmo serviço ao longo do tempo,
   não para virar categoria. *(Feito em `imaging/mama_fgt.py`.)*
2. Decidir se vale calcular os números do exame na chegada e guardá-los.
3. **MIP giratório da subtração** gravado como filme.
4. **Registro não rígido** (hoje, translação 3D; o registro rígido 6 GL veio depois, em `imaging/registro_rigido.py`).
5. Usar o **TriggerTime** da GE como relógio preferido das fases.
6. Validar a medida da lesão **numa lesão de verdade**, marcada por um radiologista.

## Decisões desta linha

- **Medir antes de escrever o número.** A medição achou dois defeitos e um erro de definição antes de existir o mapa,
  e mais três na medida da lesão.
- **Resultado bonito demais é defeito**: 0,00% de persistente em todos os exames era o pico errado.
- **O arquivo manda sobre o nome**: série se reconhece pelo ImageType, não pela descrição.
- **Série derivada não é fase**, e subtração que entra como fase envenena o pico em silêncio.
- **Classificação em porcentagem precisa de máscara**, senão classifica ruído.
- **Numa RM de mama tudo o que realça está ligado pelos vasos**: limiar fixo vaza, limiar relativo não; região fina e
  comprida é vaso, e o programa avisa.
- **Número que contradiz outro número na mesma tela é defeito.**
- **Mapa colorido sem os limiares à vista é imagem bonita sem medida.**
- **Classe é categoria, não escala**: a cor não interpola, e o valor cai no meio da faixa.
- **Métrica cuja fórmula não é pública vai rotulada com a fórmula usada.**
- **Os limiares são convenção do CADstream, não valor normal**: ponto de partida editável. O programa devolve número
  e classe; a interpretação é do médico.
- **Validar o mecanismo não é validar a acurácia.**
- **Detector que erra nos dois sentidos é detector errado**; o que vale é a forma.
- **Fantoma que não tem a anatomia não prova nada.**
- **O que a máscara mantém, ela declara.**
- **Número que separa os casos é útil; número alto demais em todos é a máscara.**
