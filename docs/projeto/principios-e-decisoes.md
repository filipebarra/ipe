# Princípios e decisões do projeto

Regras que valem para todo o Ipê. Nasceram de defeitos reais, e o código as cita.

## Regras gerais

- **Medir antes de escrever o número.** Limiar, faixa ou constante clínica só entra depois de medida em exames
  reais. A medição costuma achar defeito antes de existir a primeira linha da função.
- **Resultado bonito demais é defeito.** "0,00% em todos os casos" quase sempre é conta errada, não achado.
- **Retorno silencioso é defeito.** Tela que não abre, botão que não age e cálculo que não sai dizem por quê.
- **O arquivo manda sobre o nome.** Série se reconhece pelo conteúdo DICOM (ImageType, tags), não pela descrição.
- **O dado fica, a ferramenta some.** Desligar um módulo ou uma função nunca apaga exame, medida ou laudo.
- **Número que contradiz outro na mesma tela é defeito** (por exemplo, maior diâmetro 3D menor que um lado).
- **Métrica sem fórmula pública vai rotulada com a fórmula usada.**
- **Validar o mecanismo não é validar a acurácia.** O teste prova que a conta faz o que diz; a acurácia clínica
  pede caso marcado por quem lê.
- **Nada de atalho de teclado de fábrica além do pedido.** Tecla que o usuário não escolheu é tecla que dispara
  algo sem ele saber.
- **Sem administrador.** Instala e roda na conta do usuário; dados na pasta do usuário.
- **Funciona sem internet.** O que depende de rede avisa quando não alcança e não derruba o resto.
- **Dados de pacientes não saem do banco.** Manual, site, testes e capturas públicas usam só exames anonimizados
  ou fantomas.

## Decisões pontuais

### Tabela de cores "Tálio PUH (GE AW)" (`imaging/colormaps.py`)

A primeira versão foi um palpite (uma escala quente, vinho → vermelho → laranja → branco), marcada no código como
aproximação. Ela estava errada. Os pontos atuais vêm da **medição dos pixels de uma faixa da própria estação GE**
(padrão do mapa de fluxo na perfusão, comum também em ADC e R2*): um arco-íris escurecido, inspirado nas escalas de
medicina nuclear.

```
preto → azul → ciano/verde → verde → amarelo-esverdeado → amarelo → laranja
#00000C   #0050C1   #00828B    #39B430      #C0D300        #D6EB01   #DC8200
```

O verde e o amarelo são de propósito mais escuros e menos saturados que num arco-íris comum. A tabela tem 17 pontos
de controle.

**Ressalva:** a amostra não mostra o extremo direito inteiro. Na estação, o fim pode continuar até laranja forte ou
vermelho, então a última faixa é a parte menos firme da tabela.
