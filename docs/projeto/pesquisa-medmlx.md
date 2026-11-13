# MedMLX: o que serve para o Ipê (novembro de 2026)

Pesquisa sobre o [MedMLX](https://github.com/MedMLX/medmlx): o que dá para aproveitar e como fica o TotalSegmentator
que o Ipê usa. As etapas 1 a 5 da lista no fim viraram `src/ipe/ai/extras.py`.

## O que é o MedMLX

- Pacote Apache-2.0 (versão 0.4.2 na época), muito novo.
- Junta numa API Python, numa CLI (`describe` / `readiness` / `run`) e num servidor MCP: TotalSegmentator, nnU-Net,
  MedSAM2, SynthSeg, MRSegmentator, SAM 3, NV-Reason-CT, MedGemma e um adaptador de PET FDG.
- **Só roda em Apple Silicon (Metal, Python 3.13).** Não serve direto para Windows nem Linux. O que vale para o Ipê
  é o catálogo de modelos, que rodam em PyTorch normal.
- Os pesos têm licença própria, e o README diz "para pesquisa e ensino".

## TotalSegmentator no Ipê

- O instalador de segmentação instala `TotalSegmentator>=2.18` e o torch de CPU.
- A 2.18.0 (agosto de 2026) era a mais nova no PyPI, da mesma família "v2" que o MedMLX usa.

## Modelos do catálogo × Ipê

| Modelo | No Ipê |
|---|---|
| TotalSegmentator v2 (órgãos, lobos) | Já temos. As superfícies 3D seriam o T9 "vários objetos no 3D" (ver `ideias-aw-server.md`) |
| SwinUNETR BTCV, VISTA-3D | Redundantes com o TS. O VISTA-3D tem correção por clique; licença NVIDIA a conferir |
| nnU-Net fígado (com tumor) | Candidato para a carga tumoral por Couinaud (O12) |
| UNesT renal (córtex/medula/pelve) | Baixa prioridade |
| RetinaNet nódulo pulmonar (MONAI/LUNA16) | Já há o `lung_nodules` do TS; serviria só como segunda opinião |
| **MedSAM2** (caixa → máscara, propaga nos cortes vizinhos) | **Maior ganho.** Segmentar qualquer lesão por caixa e propagar em 3D: segmentação por diâmetro (O11), nódulos fora do pulmão, seguimento oncológico |
| nnU-Net autoPET | Lesões FDG automáticas → MTV/TLG no seguimento PET. Licença dos pesos a conferir |
| FleXray (radiografia) | Contornos no RX de tórax (índice cardiotorácico automático). Modelo pouco conhecido, a conferir |
| Endoscopia; NV-Generate-MR-Brain (gerativo) | Fora |
| SynthSeg 2.0 | Já temos (índices do crânio) |
| nnU-Net BraTS | Glioma (ET/TC/WT) para seguimento RANO. Precisa de T1, T1c, T2 e FLAIR registrados. Médio–grande |
| MRSegmentator | Alternativa ao `total_mr` do TS na RM; comparar |
| MedGemma, NV-Reason-CT | Laudo por modelo de linguagem com visão: fora do escopo (o Ipê não gera rascunho diagnóstico) |

## Ideias de arquitetura

- O trio `describe` / `readiness` / `run` com argumentos em JSON parece o contrato de `ai/ferramentas.py`. Vale
  copiar o **readiness**: conferir ambiente e pesos sem baixar nada, mostrado em Configurações ▸ CAD/IA.
- O `setup --all` pré-baixa os pesos para uso offline, como um pacote offline do TS.
- O servidor MCP fica fora por enquanto.

## Ordem sugerida

1. MedSAM2, caixa + propagação, no contrato comum. **M**
2. autoPET → MTV/TLG automáticos. **M**
3. nnU-Net fígado/tumor → Couinaud. **M–G**
4. "Readiness" na tela de CAD/IA. **P**
