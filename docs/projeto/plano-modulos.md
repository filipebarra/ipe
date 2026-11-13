# Plano: separar o programa em módulos

Pedido original (0.36): separar o programa em módulos (medicina nuclear, RM, mamografia, impressão, usuários,
idiomas), escolher na instalação o que se quer e poder acrescentar módulos depois, baixados do GitHub pelo próprio
programa.

**Situação:** o caminho 1 foi feito na 0.84 (`src/ipe/modules.py`): um pacote só, com módulos ligados ou
desligados em Preferências ▸ Módulos. Os caminhos 2 e 3 continuam em plano.

## Por que faz sentido

- O pacote passou de 190 MB. Boa parte é PySide6 e os decodificadores, que ninguém corta, mas o resto cresce a
  cada versão.
- Quem só lê mamografia não precisa do motor de medicina nuclear na tela, nem dos botões dele.
- A barra por modalidade (0.30) já esconde o botão que não serve. Módulo é a mesma ideia no nível do pacote: **o
  que não se usa não se instala**.
- Um serviço que não imprime não deveria ter porta de impressora DICOM nem aba de Impressões.

## O que pesa contra, e precisa ser resolvido antes

1. **A economia real pode ser pequena.** PySide6, Qt, numpy, pydicom e os decodificadores são a maior parte do
   pacote, e todo módulo depende deles. É preciso medir antes. Se o ganho for só de tela e não de disco, o caminho
   é **desligar o módulo**, não **deixar de instalar**.
2. **Combinação de módulos é combinação de defeitos.** Com 6 módulos opcionais há 64 combinações. Testar todas é
   inviável, e testar só a completa é o mesmo que não testar. A saída é limitar as combinações **suportadas**: a
   base mais qualquer conjunto, com um teste de fumaça por módulo isolado e um com todos.
3. **Nada pode quebrar por falta de módulo.** Exames importados com um módulo instalado continuam no banco quando
   ele for removido. A regra é **o dado permanece, a ferramenta some**, e a tela diz "este exame precisa do módulo
   X" em vez de dar erro.
4. **Idiomas não é módulo.** Os arquivos somam poucos KB, e o programa sem eles fica pior sem economizar nada.
   Ficam na base.
5. **Usuários não é módulo opcional.** Auditoria e permissões são o que permite atender exigências de
   rastreabilidade. Ficam na base; o que se escolhe é o modo de acesso (feito na 0.36).

## Divisão proposta

| Módulo | O que leva | Depende de |
|---|---|---|
| **Base** (sempre) | banco, importação, viewer 2D, MPR, medidas, exportação, idiomas, usuários, rede DICOM | — |
| **MN** | `imaging/nm*.py`, `ui/viewer/nm_*.py`, receitas por exame | base |
| **Mamografia** | hanging, quadrantes, implante, tomossíntese, indicador de profundidade | base |
| **3D** | `render3d`, superfície, exportação de modelo, escultura | base |
| **Impressão** | SCP de impressora, filas, origens, regras, modelos de folha | base |
| **Avançado de RM/TC** | dinâmica de mama, perfusão, 4D cardíaco, DSA | base |

MN, 3D e mamografia têm código pesado próprio. A impressão tem **porta de rede** e serviço em segundo plano, por
isso é o mais valioso de poder não instalar.

## Como entregar os módulos

Três caminhos, do mais simples ao mais completo:

1. **Um pacote só, módulos ligados ou desligados** (sem download). O programa esconde o que não está ligado. **Não
   economiza disco**; economiza tela e serviço. É o primeiro passo e o ensaio dos outros dois. *(Feito na 0.84.)*
2. **Pacotes separados no instalador** (`[Components]` do Inno Setup). O instalador já sabe fazer isso, e o
   usuário marca caixinhas. Economiza disco, mas cada versão vira vários arquivos para gerar e conferir.
3. **Módulo baixado de dentro do programa.** Um `modulos.json` no GitHub Releases (nome, versão, tamanho, hash
   SHA-256, URL). O programa baixa, **confere o hash**, descompacta numa pasta de módulos dentro dos dados do
   usuário e carrega dali.

## O que o caminho 3 exige

- **Hash publicado e conferido antes de carregar.** Baixar código e executar sem conferir é a porta de entrada
  clássica. O hash vai no `modulos.json`, servido por HTTPS do repositório oficial.
- **Funcionar sem internet.** Serviço de imagem costuma ter rede fechada. O programa continua inteiro offline, e a
  loja de módulos é um extra que **avisa quando não alcança**.
- **Versão casada.** Um módulo feito para outra versão do programa é recusado com uma frase clara, não com um
  `ImportError`. O `modulos.json` traz a faixa de versões que cada módulo aceita.
- **Sem administrador**: o módulo vai para a pasta de dados do usuário, nunca para a pasta de instalação.
- **Desinstalar módulo não apaga exame.**

## Ordem sugerida

1. **Medir** quanto cada módulo realmente pesa no pacote. Isso decide o resto.
2. **Caminho 1** (feito).
3. **Caminho 2**, se a medição justificar, reaproveitando a mesma lista.
4. **Caminho 3** por último, e só com o hash conferido. Antes dele vem a **assinatura digital do executável**: um
   programa que baixa código e não é assinado é um alvo.

## Ligação com o que já existe

- A **barra por modalidade** (0.30) já esconde o que não serve; o módulo desligado usa o mesmo caminho, com uma
  condição a mais.
- O **modo de acesso** (0.36) criou o lugar para uma pergunta de instalação e o comando de linha `set-mode`. A
  escolha de módulos entra ao lado, com o mesmo desenho.
- A **conferência do pacote** (`verifica.py`) vai precisar rodar uma vez por combinação suportada.
