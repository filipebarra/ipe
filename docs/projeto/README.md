# Documentos de projeto do Ipê

Planos, pesquisas e decisões que guiam o desenvolvimento e que o código cita nos comentários. O guia do
usuário fica em `docs/Ipe-guia-do-usuario.pdf` (fonte em `tools/guia/guia.md`); o que mudou em cada versão, nos
`CHANGELOG*.md` da raiz.

Estes textos são cópias editadas das notas de trabalho: sem dados de pacientes, de clínicas ou de computadores
específicos. Quando um texto fala em "acervo", são exames reais usados para medir antes de fixar um número; aqui
ficam só o método e a conclusão, nunca os exames.

| Documento | Do que trata | Citado em |
|---|---|---|
| [principios-e-decisoes.md](principios-e-decisoes.md) | As regras que valem para o projeto inteiro e algumas decisões pontuais | `imaging/colormaps.py` |
| [plano-modulos.md](plano-modulos.md) | Separar o programa em módulos ligáveis | `modules.py` |
| [plano-visualizador-web.md](plano-visualizador-web.md) | O Ipê Web (Cornerstone3D servido pelo servidor central), fases W0–W6 | `central/web.py`, `web/README.md` |
| [ideias-aw-server.md](ideias-aw-server.md) | Funções de uma estação comercial de pós-processamento, priorizadas para o Ipê | `imaging/difusao.py`, `estruturas.py`, `registro_rigido.py` |
| [rm-mama-dinamica.md](rm-mama-dinamica.md) | RM de mama dinâmica: mapa cinético, máscara da mama, distâncias | `imaging/mama_fgt.py` |
| [pesquisa-medmlx.md](pesquisa-medmlx.md) | Modelos de IA de imagem médica que valem para o Ipê | `ai/extras.py` |

## Visão geral da arquitetura

O Ipê é um programa Python (PySide6/Qt) com três formas de uso, todas no mesmo pacote:

1. **Estação local**: banco, arquivos e visualizador no mesmo computador.
2. **Servidor central**: guarda os exames, fala com o PACS e serve os clientes e o navegador.
3. **Cliente**: o mesmo programa, usando o banco do servidor pela rede (com um cache local).

```
                ┌──────────────── Servidor central (src/ipe/central) ─────────────────┐
 PACS / ───────▶│ rede DICOM (network/)  ·  importação (importer/)                      │
 modalidades    │ banco PostgreSQL embutido (db/)  ·  arquivos (Storage/)              │
                │ HTTP(S): /api (login, RPC), /dicomweb (QIDO/WADO/STOW), /web (site)  │
                └──────┬───────────────────────────────────────────┬────────────────────┘
                       │ RPC + DICOMweb                            │ DICOMweb + /api/web
                ┌──────▼─────────────────┐                ┌────────▼─────────────────────┐
                │ Ipê cliente (Qt)       │                │ Ipê Web (navegador)          │
                │ central/client_repo.py │                │ web/src (TypeScript + CS3D)  │
                └────────────────────────┘                └──────────────────────────────┘
```

### Pastas de `src/ipe`

| Pasta | Papel |
|---|---|
| `core/` | Configuração, caminhos, idiomas, utilidades sem tela |
| `db/` | Banco (PostgreSQL embutido pelo `pixeltable-pgserver`; migração do SQLite antigo), repositório de consultas |
| `importer/` | Leitura de pastas, ZIP e DICOMDIR; cópia para o armazenamento; regras na chegada |
| `network/` | DICOM DIMSE (C-FIND/C-MOVE/C-GET/C-STORE), DICOMweb, fila de downloads, nós |
| `central/` | Servidor HTTP, RPC, DICOMweb do servidor, envio progressivo, cliente remoto, PACS pelo servidor |
| `auth/` | Usuários, perfis, permissões, visibilidade dos bancos pessoais, auditoria |
| `imaging/` | Contas de imagem sem tela: volumes, MPR, medidas, SUV, dinâmica, difusão, registro, máscaras, cores |
| `ai/` | Ferramentas de IA (TotalSegmentator, MedSAM2, SynthSeg…) num contrato comum, instaladas sob demanda |
| `ui/` | Telas Qt; `ui/viewer/` é o visualizador (abas, quadros, barras, painéis) |
| `reporting/` | Laudo, modelos, BI-RADS, PDF e SR |
| `printing/` | Impressora DICOM (SCP), filas, regras, modelos de folha |
| `exporter/` | Exportação (imagens, vídeo, DICOM, anonimização, modelos 3D) |
| `automation/`, `caselists/` | Regras automáticas e listas de casos |
| `web_dist/` | O site do Ipê Web já compilado (gerado a partir de `web/`) |

### Regras de funcionamento que atravessam o código

- **O mesmo número em todo lugar.** Medidas, SUV, calibração de ultrassom e mapas têm uma conta só, em
  `imaging/`; a tela Qt e o navegador são conferidos contra ela nos testes.
- **Nada some calado.** Toda função que não pode rodar diz por quê na tela (ver `principios-e-decisoes.md`).
- **Testes** em `tests/` (pytest; os de ponta a ponta do navegador usam Playwright). Precisam de um PostgreSQL
  (`IPE_TEST_PG`). Os exames usados nos testes e no manual são anonimizados ou fantomas gerados.
