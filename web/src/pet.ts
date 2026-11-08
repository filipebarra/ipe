// PET/CT no visualizador web (0.99.94, fase W3): SUV pela conta do Ipê, as tabelas de cores do Ipê, o SUV
// máximo perto do cursor e as SEG do Ipê (carga tumoral, órgãos) como máscaras sobre os quadros de volume.

import { cache, metaData, utilities as csUtils, volumeLoader, type Types } from "@cornerstonejs/core";
import * as csTools from "@cornerstonejs/tools";

import { descomprimir, mapaSeg, type Config, type MapaSeg } from "./api";
import { partesDoImageId } from "./meta";

/** série de PET -> fator de SUV (pelo peso), como no Ipê (imaging/suv.py) */
export const SUV = new Map<string, number>();
/** a tabela da fusão quando nada foi escolhido: a do Ipê para PET */
export const COR_PADRAO = "hot";
/** a janela de SUV quando nada foi escolhido */
export const SUV_PADRAO = 6;
/** o raio da procura do SUV máximo (o "3 cm" do Ipê) */
export const RAIO_MAXIMO_MM = 30;

let tabelas: { chave: string; nome: string }[] = [];

/** O provedor de metadados que faz o carregador entregar o PET em SUV (o "scalingModule" do Cornerstone3D). */
export function registrarEscalaSuv(): void {
  metaData.addProvider((tipo: string, imageId: string) => {
    if (tipo !== "scalingModule") return undefined;
    const p = partesDoImageId(imageId);
    const f = p ? SUV.get(p.series) : undefined;
    return f ? { suvbw: f } : undefined;
  }, 10000);
}

/** As tabelas de cores do Ipê viram colormaps do Cornerstone3D ("ipe-<chave>"). */
export function registrarCores(cfg: Config | null): { chave: string; nome: string }[] {
  tabelas = [];
  for (const [chave, t] of Object.entries(cfg?.tabelas_cores || {})) {
    csUtils.colormap.registerColormap({ ColorSpace: "RGB", Name: `ipe-${chave}`, name: `ipe-${chave}`,
      RGBPoints: t.pontos.flat() });
    tabelas.push({ chave, nome: t.nome });
  }
  return tabelas;
}

export function tabelasDeCores(): { chave: string; nome: string }[] {
  return tabelas;
}

/** Cor e transparência da fusão como no Ipê: some o que está abaixo de 8% do topo da janela. */
export function propriedadesDaFusao(cor: string, opacidade: number, suvMax: number): Types.ViewportProperties {
  const lo = 0.08 * suvMax;
  return {
    colormap: {
      name: `ipe-${cor}`,
      opacity: opacidade,
      // a tabela de opacidade vira uma textura sobre a faixa destes pontos: faixa curta (0 até o topo), senão a
      // resolução não separa o "abaixo de 8%" (fora da faixa, vale o ponto da ponta)
      opacityMapping: [{ value: 0, opacity: 0 }, { value: lo * 0.98, opacity: 0 }, { value: lo, opacity: 1 },
        { value: suvMax, opacity: 1 }],
    },
    voiRange: { lower: 0, upper: suvMax },
  } as Types.ViewportProperties;
}

// ------------------------------------------------------------------ SUV máximo perto do cursor
type V3 = [number, number, number];

/** O voxel de maior valor numa esfera de `raioMm` em volta de `centro` (mm do paciente), como `maximo_perto` do
 * Ipê (imaging/pet_onco.py). Devolve o ponto (centro do voxel) e o valor (em SUV, se a série tem o fator). */
export function maximoPerto(volumeId: string, centro: V3, raioMm = RAIO_MAXIMO_MM): { ponto: V3; valor: number } | null {
  const vol = cache.getVolume(volumeId) as unknown as Types.IImageVolume | undefined;
  if (!vol) return null;
  const im = vol.imageData!;
  const ijk = im.worldToIndex(centro) as unknown as V3;
  const [nx, ny, nz] = vol.dimensions;
  const [sx, sy, sz] = vol.spacing;
  const r = [sx, sy, sz].map((s) => Math.max(1, Math.ceil(raioMm / Math.max(s, 1e-3))));
  const c = ijk.map((v) => Math.round(v));
  const i0 = Math.max(0, c[0] - r[0]), i1 = Math.min(nx, c[0] + r[0] + 1);
  const j0 = Math.max(0, c[1] - r[1]), j1 = Math.min(ny, c[1] + r[1] + 1);
  const k0 = Math.max(0, c[2] - r[2]), k1 = Math.min(nz, c[2] + r[2] + 1);
  if (i0 >= i1 || j0 >= j1 || k0 >= k1) return null;
  const vm = vol.voxelManager as unknown as { getAtIJK: (i: number, j: number, k: number) => number };
  let melhor = -Infinity;
  let onde: V3 | null = null;
  for (let k = k0; k < k1; k++) {
    for (let j = j0; j < j1; j++) {
      for (let i = i0; i < i1; i++) {
        const d2 = ((i - ijk[0]) * sx) ** 2 + ((j - ijk[1]) * sy) ** 2 + ((k - ijk[2]) * sz) ** 2;
        if (d2 > raioMm * raioMm) continue;
        const v = Number(vm.getAtIJK(i, j, k));
        if (v > melhor) { melhor = v; onde = [i, j, k]; }
      }
    }
  }
  if (!onde) return null;
  return { ponto: im.indexToWorld(onde) as unknown as V3, valor: melhor };
}

// ------------------------------------------------------------------ SEG como máscara
export interface SegCarregada {
  id: string;
  descricao: string;
  segmentos: MapaSeg["segmentos"];
  voxels: number;
}

const SEGS = new Map<string, SegCarregada>();

/** Lê a SEG (série `segSerie`) pelo servidor e monta o mapa de rótulos sobre o volume da série de origem
 * (`volumeDaOrigem` monta esse volume). Devolve a segmentação, pronta para pôr nos quadros. */
export async function carregarSeg(study: string, segSerie: string,
  volumeDaOrigem: (series: string) => Promise<string | null>): Promise<SegCarregada | null> {
  const ja = SEGS.get(segSerie);
  if (ja) return ja;
  const mapa = await mapaSeg(study, segSerie);
  if (!mapa) return null;
  const refId = await volumeDaOrigem(mapa.ref_series);
  if (!refId) return null;
  const ref = cache.getVolume(refId) as unknown as Types.IImageVolume;
  const id = `ipe-seg:${segSerie}`;
  const lab = (cache.getVolume(id) as unknown as Types.IImageVolume | undefined)
    ?? (volumeLoader.createAndCacheDerivedLabelmapVolume(refId, { volumeId: id }) as unknown as Types.IImageVolume);
  const fatiaDoSop = new Map<string, number>();
  ref.imageIds.forEach((imageId, k) => {
    const p = partesDoImageId(imageId);
    if (p) fatiaDoSop.set(p.sop, k);
  });
  const vm = lab.voxelManager as unknown as { setAtIJK: (i: number, j: number, k: number, v: number) => void };
  let voxels = 0;
  for (const f of mapa.fatias) {
    const k = fatiaDoSop.get(f.sop);
    if (k === undefined) continue;
    const dados = await descomprimir(f.dados);
    for (let r = 0; r < f.h; r++) {
      for (let c = 0; c < f.w; c++) {
        const v = dados[r * f.w + c];
        if (v) { vm.setAtIJK(f.c0 + c, f.r0 + r, k, v); voxels++; }
      }
    }
  }
  const segmentos: Record<number, { segmentIndex: number; label: string }> = {};
  for (const s of mapa.segmentos) segmentos[s.n] = { segmentIndex: s.n, label: s.nome };
  csTools.segmentation.addSegmentations([{
    segmentationId: id,
    representation: { type: csTools.Enums.SegmentationRepresentations.Labelmap, data: { volumeId: id } },
    config: { label: mapa.descricao, segments: segmentos },
  } as never]);
  const s: SegCarregada = { id, descricao: mapa.descricao, segmentos: mapa.segmentos, voxels };
  SEGS.set(segSerie, s);
  return s;
}

/** Põe a SEG nos quadros de volume, com as cores do Ipê. */
export function mostrarSeg(s: SegCarregada, viewportIds: string[]): void {
  const lut: number[][] = [[0, 0, 0, 0]];
  const maior = Math.max(0, ...s.segmentos.map((x) => x.n));
  for (let n = 1; n <= maior; n++) {
    const sg = s.segmentos.find((x) => x.n === n);
    lut.push(sg ? [sg.cor[0], sg.cor[1], sg.cor[2], 255] : [255, 255, 255, 255]);
  }
  for (const vp of viewportIds) {
    try { csTools.segmentation.removeSegmentationRepresentations(vp, {}); } catch { /* nada */ }
    csTools.segmentation.addLabelmapRepresentationToViewport(vp, [{ segmentationId: s.id,
      config: { colorLUTOrIndex: lut as unknown as Types.ColorLUT } }]);
  }
}

export function tirarSeg(viewportIds: string[]): void {
  for (const vp of viewportIds) {
    try { csTools.segmentation.removeSegmentationRepresentations(vp, {}); } catch { /* nada */ }
  }
}

export function esquecerSegs(): void {
  for (const s of SEGS.values()) {
    try { csTools.segmentation.removeSegmentation(s.id); } catch { /* nada */ }
  }
  SEGS.clear();
}
