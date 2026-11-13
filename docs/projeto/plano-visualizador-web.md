# Plano: o Ipê Web, servido pelo servidor central

Pedido original: um visualizador no navegador, ligado ao próprio servidor do Ipê, com MIP, MPR, oblíquo, mudar o
plano com um clique (como no Ipê), fusão de PET, medidas, calibração de ultrassom, protocolo de exibição de
mamografia e dinâmica de mama (aproveitando os mapas salvos no Ipê).

**Situação:** as fases W0 a W6 estão feitas, da 0.99.91 à 0.99.98, e a 0.100.x acrescentou overlay e CAD, linhas de
referência, PET ajustável, botões do mouse, lupa, pilha 2D + tomossíntese alinhada, laudo com BI-RADS, PDF e SR no
exame, busca no PACS pelo servidor e outras. O detalhe de cada versão está no `CHANGELOG.md`. O código fica em
`web/` (fontes) e `src/ipe/central/web.py` (o lado do servidor).

## Decisões

- **D1. Cornerstone3D (CS3D) para o que der.** Comparado com escrever tudo em Rust: o CS3D já traz MPR, oblíquo,
  MIP, 3D, fusão, carga progressiva, os codecs JPEG-LS, J2K e HTJ2K em WebAssembly, ferramentas de medida e SEG.
  É usado **direto, sem o OHIF**, com a interface do Ipê. Rust/WebAssembly ficaria só onde rendesse; na prática, os
  mapas da dinâmica em TypeScript foram rápidos o bastante.
- **D2. Uso só na rede interna por enquanto.** De fora, VPN (ver a seção 5).
- **D3.** As medidas feitas no navegador vão para o banco e aparecem no Ipê, com o nome de quem fez.
- **D4.** O laudo entra, como a última fase (W6).
- **D5.** Mamografia em dois monitores pelo navegador.

## 1. O que já existia e serviu de base

| Peça | Onde | Serve para |
|---|---|---|
| Servidor central (HTTP(S), porta 8043, AC interna) | `central/server.py` | hospedar o site, o login e os dados |
| Login por token, permissões, bloqueio após senhas erradas, auditoria | `central/server.py`, `network/acesso.py` | o mesmo login do Ipê |
| DICOMweb: QIDO, WADO, STOW | `central/server.py`, `central/dicomweb.py` | a lista e as imagens |
| RPC com o repositório | `central/rpc.py` | medidas, laudo e estado do exame |
| Regras de referência | `imaging/volume.py`, `us_regioes.py`, `measure.py`, `suv.py`, `ui/viewer/hanging.py`, `ui/viewer/dynamic.py` | o navegador tem de dar o mesmo número que o Ipê |
| Mapas da dinâmica salvos como séries | `ui/viewer/dynamic.py` | a dinâmica começa por eles |
| Laudo, modelos, achados de IA | `reporting/` | a fase W6 |

O que faltava no servidor, e foi feito na W0: o site estático em `/web`; o `/metadata` e o `/frames/{n}` do WADO-RS;
o `/api/web/config` (protocolos, janelas e arranjo da mamografia do usuário); o fator de SUV por série; os
cabeçalhos de segurança; a auditoria de "abriu no navegador".

## 2. Arquitetura

```
Navegador (Chrome/Edge)                                   Servidor central (Python)
┌──────────────────────────────────────────┐              ┌───────────────────────────────────────┐
│ Interface do Ipê: TypeScript + HTML5     │ HTTPS+token  │ /web/…   site estático (o pacote)      │
│  lista · tira · quadros · menus · laudo  │ ───────────▶ │ /api/login, /api/rpc                   │
│ Cornerstone3D (core, tools, loader)      │              │ /dicomweb QIDO/WADO/STOW               │
│  MPR · oblíquo · MIP · 3D · fusão · SEG  │ ◀─────────── │  + /metadata, /frames/{n}              │
│  codecs JPEG-LS/J2K/HTJ2K em WASM        │              │ /api/web/config  protocolos, janelas   │
│ Módulos Ipê: mamografia, dinâmica, US,   │              │ banco e arquivos do Ipê                │
│  medidas no banco, laudo                 │              └───────────────────────────────────────┘
└──────────────────────────────────────────┘
```

- **Pacotes do CS3D** (`@cornerstonejs/core`, `tools`, `dicom-image-loader`) em versões fixas. Cada atualização
  grande é uma tarefa própria, com os testes.
- **Os arquivos JPEG-LS do banco vão como estão**; o navegador decodifica em WebAssembly. Economiza rede e CPU do
  servidor.
- **Build:** Vite + TypeScript. O site compilado vai no pacote (`src/ipe/web_dist`), e o servidor o serve em
  `/web`. O computador que roda o servidor não precisa de Node.

## 3. Fases

Esforço: P = dias, M = 1–3 semanas, G = mais de um mês.

- **W0, fundação (M), 0.99.91.** No servidor: `/web`, `/metadata` e `/frames`, `/api/web/config`, cabeçalhos
  (`Cache-Control: no-store`, CSP, HSTS) e auditoria. Login com o usuário do Ipê, token só na memória da aba,
  saída por inatividade. Lista de exames com as mesmas permissões, tira de séries, quadros 2D com a sobreposição de
  texto e as janelas do Ipê, layouts, cine, inverter. Tarja "não destinado a uso diagnóstico". Nenhum atalho de
  fábrica.
- **W1, MPR, oblíquo, mudar plano, MIP, 3D (P–M), 0.99.92.** Volume com carga progressiva; linhas de referência e
  cursor 3D; **mudar o plano com um clique** (axial ↔ coronal ↔ sagital no mesmo volume, sem recarregar); oblíquo
  (girar as linhas, oblíquo do plano atual, oblíquo por dois pontos); espessura com MIP, MinIP e média; 3D girando.
- **W2, medidas no banco e calibração do US (M), 0.99.93.** Régua, ângulo, Cobb, elipse, círculo, retângulo,
  polígono com estatística em HU ou SUV, seta e texto. As medidas vão para o banco no formato do Ipê (pixels da
  imagem), com o nome de quem fez. A estatística (média, DP, área) é conferida contra o Ipê; onde difere, vale a
  conta do Ipê. Calibração do ultrassom pelas regras de `us_regioes.py`: por imagem, só a região com os dois eixos
  em cm, o Doppler não vira régua, e à mão com escopo de imagem ou série.
- **W3, fusão PET/CT (P–M), 0.99.94.** Fusão com o fator de SUV do servidor e as tabelas de cores do Ipê (janela
  inicial SUV 0–6); o layout de leitura PET (fusão, PET e MIP girando; o clique no MIP leva aos cortes); "ir ao SUV
  máximo perto do cursor"; SEG do Ipê como máscaras.
- **W4, mamografia com dois monitores (M), 0.99.98.** O arranjo e as etapas do Ipê, lidos de `/api/web/config`;
  espelhamento, alinhamento pela parede torácica, lupa, duplo clique para ampliar, tomossíntese. Dois monitores pela
  *Window Management API* do Chrome/Edge, com as janelas sincronizadas por `BroadcastChannel`; sem a permissão, uma
  janela com as etapas. O navegador não aplica a calibração GSDF do monitor, e o site avisa.
- **W5, dinâmica da mama (M), 0.99.98.** Os mapas salvos no Ipê como fusão sobre a fase; curvas tempo-intensidade
  na ROI, com o tipo (persistente, platô, lavagem) e o realce inicial; mapas calculados no navegador, com as
  fórmulas e os limiares do Ipê (em TypeScript: um corte de 512² com 6 fases sai em milissegundos).
- **W6, laudo no navegador (M), 0.99.98.** Os modelos do Ipê, gravado no mesmo laudo; o aviso "quem está laudando"
  impede dois ao mesmo tempo; achados de IA confirmados vão ao texto; assinatura e liberação seguem o fluxo do Ipê.
- **Depois:** WebGPU e 3D de superfície; celular; compartilhar link de exame (depende do D2).

## 4. Segurança e qualidade

- **Só HTTPS.** Na rede interna, com a AC interna do Ipê.
- **Token só na memória da aba** (sem cookie, sem CSRF). Valem o bloqueio de senhas, as permissões e a auditoria
  do servidor.
- **Nada do paciente fica no disco do navegador**: `no-store`, sem IndexedDB; o cache do CS3D fica na memória.
- **Testes:** medidas, calibração do US, SUV e mapas da dinâmica contra o Python do Ipê; ponta a ponta com
  Playwright e os exames anonimizados do manual.
- **Navegadores:** Chrome e Edge atuais (os dois monitores só existem neles); o Firefox deve funcionar no resto.

## 5. O que muda se for usado fora da rede interna

1. **Endereço e certificado público.** A AC interna só vale nos computadores em que foi instalada. Fora, é preciso
   um domínio e um certificado público (Let's Encrypt), além de abrir a porta no roteador.
2. **Um portão na frente do servidor.** O servidor do Ipê é feito para a rede interna. Na internet ele fica atrás de
   um proxy reverso (Caddy, por exemplo), com limite de tentativas e de tamanho de pedido.
3. **Login mais forte.** Segundo fator (TOTP) para quem entra de fora, senhas mais longas, aviso de login de lugar
   novo.
4. **Rede.** O gargalo vira o upload do serviço: um CT de 500 MB num upload de 50 Mbit/s leva cerca de 80 s. A
   abertura progressiva e o JPEG-LS comprimido ajudam; pode entrar uma prévia com perda enquanto o original chega.
5. **LGPD.** Dado de saúde saindo da rede pede o registro de acesso (já existe), uma política de quem pode acessar
   de fora e, se for o caso, um termo com os médicos de fora.

**Alternativa recomendada: VPN** (Tailscale ou WireGuard). Quem está fora entra na rede do serviço pela VPN e usa o
visualizador como se estivesse lá dentro, sem domínio, porta aberta nem proxy. O esforço é P, contra M para abrir à
internet com segurança.

## 6. Riscos

| Risco | O que fazer |
|---|---|
| Vídeo integrado fraco nos computadores de leitura | testar no W1; reduzir a resolução do 3D e manter a cheia no 2D |
| A API do CS3D muda nas versões grandes | versões fixas; cada atualização grande é uma tarefa com os testes |
| Número diferente do Ipê | testes cruzados; a conta do Ipê nas medidas que contam |
| Muitas abas no servidor ao mesmo tempo | medir com 5 a 10 abas; quadros do WADO com cache |
| Dois monitores dependem do Chrome/Edge | sem a API, uma janela com as etapas |
