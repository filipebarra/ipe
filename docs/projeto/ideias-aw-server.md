# Ideias tiradas de uma estação de pós-processamento comercial (GE AW Server)

Leitura dos manuais em português da AW Server 3.2 (cerca de 30 aplicativos), confrontada com o Ipê da época (então
chamado DicomViewer, versão 0.65). Este texto é a síntese priorizada. Os itens são citados no código pelo código da
tabela (F1, M1, O4…).

Os aplicativos foram lidos em sete grupos: **1** plataforma, 2D Viewer, AutoLaunch · **2** Volume Viewer, 3D,
AutoBone, Bone VCAR, GSI, registro · **3** READY View (RM), DynamicIQ, CT Perfusion 4D · **4** PET VCAR, OncoQuant,
pulmão, tórax, cólon, fígado, LI-RADS · **5** cardíaco, VesselIQ, SmartScore, TAVI · **6** AVC, FlightPlan, VV Innova,
AngioViz, PROView · **7** AdvantageSim (radioterapia), Advantage 4D, GenIQ.

Esforço: P = dias, M = 1–3 semanas, G = mais de um mês.

---

## O que a leitura mostrou

**1. Quatro peças aparecem em quase todos os aplicativos, e o Ipê não tinha nenhuma inteira.** Quase toda
ferramenta avançada se apoia nelas.

- **Registro rígido de verdade** (6 graus de liberdade), citado em 4 dos 7 grupos. O Ipê só fazia translação.
- **Edição de máscaras** (pincel 3D com limiar, interpolação entre cortes, crescimento por clique mantido, bisturi,
  morfologia), citada em 5 grupos. Sem isso nenhuma segmentação automática vira medida confiável.
- **Estado salvo da análise** ("Save State"), citado nos 7 grupos: reabrir o caso como foi deixado e *fundir* o estado
  do exame anterior na sessão atual. É o que alimenta todo o seguimento.
- **Pré-processamento por regra na chegada**, citado em 5 grupos. O Ipê já fazia para a dinâmica de mama; a AW faz
  para qualquer aplicativo, por palavra na descrição da série ou por tag.

**2. Na RM de mama, a maior lacuna era a difusão.** O Ipê tinha cinética no estilo CADstream, mas não tinha ADC. A AW
tem ADC multi-b, DWI sintética, farmacocinética (Ktrans), correção de movimento antes da subtração e uma tabela que
mostra todos os mapas de uma ROI de uma vez.

**3. O seguimento oncológico é onde a AW mais se distancia.** Tabela de achados × datas com RECIST 1.0/1.1/WHO,
assistente "repetir medida / pequena demais / ausente", linha de base e Nadir, PERCIST e Deauville automáticos,
conferência dos parâmetros que alteram o SUV entre exames. Depende das quatro peças acima.

**Cuidados que a leitura pegou** (nomes enganam):
- **DynamicIQ não é mama**: é cinética de FDG em PET dinâmico (Patlak). **GenIQ não é MN**: é farmacocinética de RM
  dinâmica. **CardIQ Flow não é contraste de fase**: é fluxo miocárdico por PET.
- **"MSI" tem duas definições na própria GE**: declive **médio** no CT Perfusion e **máximo** no READY View. O Ipê
  documenta qual usa.
- **GSI** (TC espectral) só *gera* monoenergéticas com o arquivo proprietário da GE; sem ele, o Ipê só exibe e mede o
  que o tomógrafo exportou.
- A **tabela de pesos do Agatston** e a fórmula da massa aparecem como figuras no manual; os pesos 1–4 vêm da
  literatura.
- **Nenhum manual traz** mRECIST, Choi, Lung-RADS ou C-RADS, nem a fórmula do tempo de duplicação.
- Registro: a GE avisa que **TC GE referencia a posição pelo canto do pixel** (meio voxel de diferença para outros
  fabricantes). Conferir em exames reais.
- O OncoQuant em PT-PT escreve "diâmetro axial mínimo" onde quer dizer o **maior**.

---

## Fundação: fazer primeiro, porque o resto depende

| # | Ideia | O que a AW faz | Esforço | Grupo |
|---|---|---|---|---|
| F1 | **Registro rígido 6 GL** | Automático por par de modalidades (TC-TC, TC-RM, TC-PET, corpo ou neuro), modo rápido que para em 5–10 s com o melhor resultado; manual com rotação em torno do cursor; **regional numa caixa de 70 mm em volta do cursor**; por pontos pareados; **validação com pares de pontos e erro médio/máximo em mm**; grupos por Frame of Reference (registrar a T2 leva o ADC junto); conferência em tabuleiro/janela/cortina; grava Spatial Registration Object | M–G | 2, 4, 5 |
| F2 | **Gestor de estruturas + kit de máscaras** | Painel com nome, tipo, cor, volume e origem (manual/semi/auto + parâmetros). Pincel esférico 1–25 mm com faixa de valor e conectividade, com prévia sob o cursor; crescimento enquanto o botão está apertado; **desenhar em poucos cortes e interpolar**; bisturi dentro/fora e "manter o lado da semente"; dilatar/erodir/fechar/remover fragmentos; margens 3D por direção; "remover pontes" de 0–5 voxels | M–G | 2, 5, 6, 7 |
| F3 | **Estado salvo da análise** | Série "Saved State" no exame com layout, ROIs, máscaras, parâmetros dos mapas e etapa do fluxo; salvar ao sair; ao reabrir pergunta **carregar ou fundir**; recusa se a série de referência sumiu; marca "a verificar" quando é salvamento de emergência | M | todos |
| F4 | **Regras na chegada + fila "prontos para ler"** | Regra = palavra na descrição ou tag → aplicativo → série que abre sem recalcular; pré-requisito que falha é **registrado com motivo**; fila com 4 seções, reordenável, com prioridade | M | 1, 3, 5, 6 |
| F5 | **Validador de dados com selo na tela** | Lacuna entre cortes, espessura irregular, fase faltando, pacientes diferentes no mesmo layout, **compressão com perdas** (crítico em mamografia), Frame of Reference diferente com sincronia ligada, Modality LUT, pixel não quadrado, filtro/subtração ativos, kernel ou espessura diferentes entre datas comparadas. A etapa que não serve **fica desativada**, em vez de mostrar resultado errado | P | 1, 2, 4, 5, 6, 7 |

F5 é barato e combina com as regras do projeto ("retorno silencioso é defeito", "a tela diz por quê"). F1 é o que
mais destrava: sem ele, seguimento, clonar ROI, PERCIST, tempo de duplicação e correção de movimento ficam frágeis.

---

## RM de mama

| # | Ideia | O que a AW faz | Esforço | Grupo |
|---|---|---|---|---|
| M1 | **ADC multi-b** | Regressão de ln(S/S0) em todos os b; **nível de confiança** (padrão 0,25) que zera pixel ruim; escolher quais b entram; digitar os b quando o DICOM não traz; unidade selecionável; até duas DWI na sessão | M | 3 |
| M2 | **DWI sintética** | S(b) = S0·e^(−ADC·b) com b de 100 a 2500; marcada como sintética; o manual proíbe calcular ADC em cima dela | P–M | 3 |
| M3 | **Correção de movimento antes da subtração** | Roda ao carregar a T1 dinâmica; quatro vistas (corrigida, curva, original, subtração corrigida); chave original/corrigido; exporta as séries corrigidas. Rígida num VOI ou no volume; "pixel shift" por ROI propagado a um intervalo de fases | M (rígida) / G (não rígida) | 1, 3, 7 |
| M4 | **Excluir fase e marcar fases pré** | Desmarcar fase com movimento (não duas seguidas) e recalcular; aviso quando há só uma fase pré-contraste | P | 3, 7 |
| M5 | **Tabela multi-mapa por ROI + segmentação partilhada** | Uma ROI mostra numa linha ADC, SER, PEI, MSI, washout, T2 (e Ktrans), exporta CSV. Recortar um mapa por faixa (ex.: ADC < 1,0×10⁻³) e **propagar a máscara a todos os outros mapas** | M | 3, 7 |
| M6 | **Fusão de qualquer mapa por arrastar** | Arrastar uma vista sobre outra: ADC sobre T2, mapa cinético sobre DWI. Pede alinhar a DWI (correção EPI afim por corte) | M | 3, 7 |
| M7 | **Farmacocinética (Tofts)** | Ktrans, kep, ve, vp; AIF automática, semi, manual (alerta se pico > 10 mM) ou populacional; T1 de referência de gordura mamária 296/366 ms e glandular 1266/1444 ms (1,5/3 T); curva ajustada sobre a medida | G | 7 |
| M8 | **Mapas extras da curva** | BAT, TTP, declive máximo de **descida**, tempo médio de realce, linha de base **interpolada** entre pré e pós | P–M | 3, 7 |
| M9 | **Mapa de tempo colorido** | Cor = tempo até o pico, brilho = pico; ou R/G/B = realce em cada fase | P–M | 6 |
| M10 | **MIP temporal** | Máximo/mínimo/média **ao longo das fases** como série nova | P | 1, 7 |
| M11 | **"Paisagem" na subtração** | Cursor 0–100% que mistura a anatomia de volta na subtração | P | 1 |
| M12 | **Semáforo de qualidade do protocolo** | Antes dos mapas: resolução temporal, número de fases pré, flip angle, filtro aplicado diferente entre fases, geometria igual | P | 3, 7 |
| M13 | **Fluxo em etapas da RM mamária** | Revisão → Dinâmico → Subtração → SER → ADC → Água/Gordura, cada etapa com layout e cálculo | M | 3 |
| M14 | **ROI espelhada** | Plano de simetria; ROI espelhada e razão lesão/contralateral (ADC, realce, BPE) | M | 3 |
| M15 | **Percorrer as janelas do cabeçalho na mamografia** | Tecla que passa pelos vários Window Center/Width e VOI LUT gravados no arquivo | P | 1 |

**M1 + M2 + M5** fecham a lacuna da difusão com esforço moderado (feitos; a difusão vale para toda RM desde a
0.99.37); **M3** ataca o defeito que mais gera mapa cinético falso; **M10, M11, M9 e M15** são baratos.

---

## Seguimento oncológico e PET

| # | Ideia | O que a AW faz | Esforço | Grupo |
|---|---|---|---|---|
| O1 | **Tabela achados × datas** | Uma linha por achado, uma coluna por exame; medidas de datas diferentes **ligadas sozinhas dentro de 10 mm** (com registro); variação % ou absoluta; clicar leva à imagem | G | 2, 4, 6 |
| O2 | **Motor de critérios** | RECIST 1.0, **RECIST 1.1** (5 lesões, 2/órgão, mínimo 10 mm; linfonodo pelo eixo curto, mínimo 15 mm), WHO; critérios do usuário em JSON; **"!" com a regra violada** em vez de soma errada | M | 4 |
| O3 | **Assistente de seguimento** | Em cada medida antiga: repetir (com a antiga em fantasma), pequena demais, ausente, estável/maior/menor; linha de base e Nadir; relatório com 4 datas | M | 4, 6 |
| O4 | **Métricas PET** | SUVpeak (esfera de 1 cm³), SUL, SUVbsa, **TLG, MTV total**, SUV corrigido por glicose; limiar fixo e "estimado"; avisos de lesão encostada na caixa, volume < 1 cm³ e sobreposição | P–M | 2, 4 |
| O5 | **Referência hepática automática** | Esfera de 1 cm³ no lobo direito (TotalSegmentator: fígado, erosão, ponto de menor variância), pool sanguíneo e fundo | M | 4 |
| O6 | **PERCIST 1.0 e Deauville** | PERCIST com checklist de pré-condições que **explica por que a resposta não saiu**; Deauville 1–5/X automático | P–M | 4 |
| O7 | **Conferência entre exames PET** | Tempo de captação 50–70 min e diferença ≤ 15 min, glicose, atividade, peso, matriz, reconstrução e software iguais | P–M | 4 |
| O8 | **Realce de tudo acima de um SUV** | Componentes acima do limiar, remover por clique, ordenar por SUV/volume | M | 4 |
| O9 | **Propagar lesões para o seguimento** | Cada marcador da base levado à mesma posição no exame novo pelo registro, confirmar um a um | G | 4 |
| O10 | **Nódulo pulmonar** | Tipo e consistência com **volume sólido separado do total**; crescimento e tempo de duplicação; aviso de kernel/espessura diferentes | G (P só o tempo de duplicação) | 4 |
| O11 | **Segmentação por diâmetro** | Desenhar o maior diâmetro e receber o contorno 3D, com ajuste −/+; saem diâmetro, eixo curto e volume | M | 2, 4 |
| O12 | **Fígado** | Segmentos de Couinaud, carga tumoral por fígado e por segmento; depois LI-RADS v2018 | M–G | 4 |
| O13 | **Laudos RADS genéricos** | O motor do BI-RADS estendido: PI-RADS, LI-RADS, Lung-RADS | M–G | 4, 6 |
| O14 | **Saídas** | CSV, copiar tabela para o laudo, XML para o RIS, RTSTRUCT e SEG a partir das máscaras | P–M | 4, 6, 7 |

O1 a O3 são o centro do fluxo oncológico e precisam de F1 e F3. O4, O6 e O7 são em boa parte contas sobre o que já
existe.

---

## TC geral, vasos e 3D

| # | Ideia | O que a AW faz | Esforço | Grupo |
|---|---|---|---|---|
| T1 | **Escore de cálcio** | Agatston com limiar 130 HU, volume, massa com calibração; percentil por idade e sexo. Útil no cálcio incidental da TC de tórax | M | 5 |
| T2 | **Linha central + vista retificada** | Caminho mínimo sobre vesselness; gráfico de área/Dmín/Dmáx ao longo do eixo; estenose | G | 2, 5, 6 |
| T3 | **Roteiro de medidas pré-definidas** | Lista de pontos com tipo e deslocamento em mm; serve como checklist guiado | M | 5, 6 |
| T4 | **Árvore vascular e alimentadores do tumor** | Árvore a partir da raiz; vasos que passam perto de um alvo; território distal | G | 6 |
| T5 | **Trajetória de agulha** | Alvo + entrada, comprimento, margem de ablação, vista ao longo da agulha | M | 6 |
| T6 | **Lote de reformatações** | Loop, rotação, planos radiais, oblíquo em grade; protocolo com nome; saída como série com geometria | M | 2 |
| T7 | **Editor de opacidade do 3D** | Histograma de fundo, rampas prontas, ajuste pelo voxel apontado, presets por anatomia | M | 2 |
| T8 | **Recorte 3D sem segmentar** | Esfera em volta do cursor, caixa, tubo; remoção da mesa; MIP ponderado por profundidade | P–M | 2, 7 |
| T9 | **Vários objetos no 3D** | Até 8 máscaras, cada uma com cor, transparência e visibilidade | M–G | 2, 5 |
| T10 | **Filme com quadros-chave** | Estados da vista com transições interpoladas; MP4 | M | 2 |
| T11 | **Rótulo das vértebras** | Pelos centróides do TotalSegmentator; renomear uma propaga às seguintes | M | 2 |
| T12 | **Enfisema** | % abaixo de −950 HU por pulmão, por lobo e em 3 zonas | M | 4 |
| T13 | **WB-DWI** | Juntar estações de difusão de corpo inteiro com normalização | M–G | 2 |

---

## Medicina nuclear

- **Mapa polar de 17/20 segmentos** com reversibilidade esforço − repouso e escore por setor.
- **Reorientação cardíaca** com eixo longo arrastável; a edição propaga para gated e dinâmico.
- **Fase do gated pelas tags padrão** quando falta a privada (Number of Time Slots, Trigger Time, Frame Time).
- **Reorientar a TC e aplicar ao PET**, salvando os dois.

---

## Baratos e de valor alto (P, poucos dias cada)

1. Selos de integridade na imagem, sobretudo **compressão com perdas em mamografia** (F5).
2. **Aviso de mistura de pacientes** na chamada externa, no filme e na exportação.
3. Percorrer as janelas do cabeçalho na mamografia (M15).
4. **Paisagem** na subtração (M11) e **MIP temporal** (M10).
5. **Tempo de duplicação** do nódulo, **SUVpeak/TLG/MTV** e **Deauville** (O10, O4, O6).
6. **ROI de referência**: cada ROI mostra a média em % de uma ROI escolhida.
7. **Incerteza ao lado da medida** (comprimento ± pixel; área ± perímetro × pixel²/2).
8. **Régua 3D**: pontos em cortes diferentes, com dx/dy/dz.
9. **Anotações clicáveis**: clicar em "W 400 / L 40" e digitar.
10. **Presets de janela por modalidade** com "capturar a janela atual".
11. **Estado do resultado de IA na anotação**: "auto", "editado", "aceito por fulano".
12. **Perfil de anotação para saída** separado do da tela, com carimbo mínimo obrigatório.
13. **Série derivada carrega os parâmetros** (Derivation Description + Source Image Sequence).
14. **Indicador de quadros pulados** no scroll rápido.
15. **Clonar ROI** para outra série ou exame pela posição do paciente.

---

## Gestão e plataforma

- **Cronologia do paciente**: cartões de exames por data, com filtros e cópia do remoto com um clique.
- **Correspondência de paciente configurável**, dizendo por que casou.
- **Estado de leitura e STAT**: novo → pré-processado → em leitura → laudado → revisado.
- **Limpeza automática do disco** com limites, cadeado e confirmação de que o exame está no PACS.
- **Fim da leitura**: ao concluir o laudo, enviar SR, KOS, estado e mapas ao PACS.
- **Retomar sessão** após fechar ou travar.
- **Listas manuais** ao lado das inteligentes.
- **Imagens-chave como DICOM KOS** e captura secundária com pixel spacing preservado.
- **Anonimização com deslocamento de data igual para todos os exames do paciente.**
- **Partilha de preferências** (protocolos, janelas, atalhos) entre radiologistas.

---

## Fora do perfil (lido e descartado, por ora)

ASPECTS e detecção de oclusão; TAVI e eletrofisiologia; PlaqID e IVUS; função ventricular por TC; fluxo miocárdico
por PET; colonografia; DTI/tratografia, fMRI, perfusão cerebral DSC/ASL, espectroscopia; Patlak; TC 4D respiratória;
DRR de radioterapia; processamentos que dependem de dado bruto do fabricante.

---

## Ordem sugerida

1. **Rodada barata**: os itens "baratos" que não dependem de nada. Prepara o validador (F5).
2. **Difusão**: M1, M2, M5, M12.
3. **Registro rígido** (F1) e **correção de movimento rígida da dinâmica** (M3), com o mesmo motor.
4. **Edição de máscaras + gestor de estruturas** (F2), com gravação de RTSTRUCT/SEG.
5. **Estado salvo** (F3) e, em cima dele, **tabela oncológica + RECIST + assistente** (O1–O3).
6. **Pacote PET** (O4–O7) e **regras na chegada generalizadas** (F4).
7. Depois, conforme demanda: escore de cálcio, linha central, lote de reformatações, editor de opacidade,
   farmacocinética, fígado, mapa polar.

Antes de cada uma vale a regra do projeto: **medir em exames reais antes de fixar número**.
